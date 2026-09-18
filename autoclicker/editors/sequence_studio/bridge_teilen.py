"""Export und Import im Studio — ein Bündel schreiben, ein Bündel einlesen.

Die Logik liegt in `import_export.py`; hier steht nur, was das Fenster davon
braucht. Beide Wege arbeiten auf einem State, der frisch von Platte kommt:
exportiert wird der gespeicherte Stand, nicht der im Fenster.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from ...models import AutoClickerState
from ...utils import sanitize_filename

# Was ein Bündel enthalten kann. Reihenfolge = Anzeige; die Schlüssel sind die
# Argumentnamen von `export_bundle`/`import_bundle` ohne Präfix.
TEILE = (
    ("sequences", "Sequenzordner (inkl. Punkte, Scans und Vorlagen)"),
    ("config", "Einstellungen"),
)


class BridgeTeilenMixin:
    """Der Reiter „Teilen": Bündel schreiben und einlesen."""

    def _share_init(self) -> None:
        self._teilen_status = ("", "info")
        self._teilen_import: Optional[dict] = None

    # ------------------------------------------------------------ Anzeige

    def _share_report(self, text: str, kind: str = "ok") -> dict:
        self._teilen_status = (text, kind)
        return self.share_data()

    def share_data(self, data: Optional[dict] = None) -> dict:
        """Was der Reiter zeichnet. Fragt nur — ändert nichts."""
        text, kind = self._teilen_status
        return {
            "teile": [{"key": k, "text": t} for k, t in TEILE],
            "bestand": self._inventory_count(),
            "window": self._window_layout(),
            "exporte": self._export_list(),
            "import": self._teilen_import,
            # Was im Fenster noch nicht gespeichert ist, liegt nicht auf Platte
            # und landet deshalb auch nicht im Bündel.
            "open": bool(getattr(self, "_dirty", False)
                          or getattr(self, "_scan_dirty", False)),
            "status": {"text": text, "kind": kind},
        }

    def _inventory_count(self) -> dict:
        """Was auf Platte liegt — gezählt, nicht geladen."""
        from ...persistence import list_available_sequences
        return {
            "sequences": len(list_available_sequences()),
            "config": 1,
        }

    @staticmethod
    def _window_layout() -> Optional[dict]:
        """Das Spielfenster, aus dem die Referenzpunkte kommen — oder None."""
        from ...config import CONFIG
        title = CONFIG.window_focus_title
        if not title:
            return None
        try:
            from ...winapi import get_client_rect_by_title
            rechteck = get_client_rect_by_title(title)
        except Exception:                                        # noqa: BLE001
            rechteck = None
        if not rechteck:
            return {"title": title, "gefunden": False}
        l, o, r, u = rechteck
        return {"title": title, "gefunden": True, "rechteck": [l, o, r, u],
                "width": r - l, "height": u - o}

    @staticmethod
    def _export_list() -> list:
        """Die vorhandenen Bündel, neueste zuerst."""
        folder = Path("exports")
        if not folder.is_dir():
            return []
        found = []
        for path in folder.glob("*.zip"):
            try:
                stat = path.stat()
            except OSError:
                continue
            found.append({"name": path.name, "kb": round(stat.st_size / 1024, 1),
                             "stamp": stat.st_mtime})
        return sorted(found, key=lambda e: e["stamp"], reverse=True)

    # ------------------------------------------------------------- Bestand

    def _inventory(self) -> AutoClickerState:
        """Alles von Platte in einen frischen State — Export/Import brauchen das Ganze.

        Der Studio-Prozess kennt sonst nur, was seine Reiter geöffnet haben. Die
        Config wird hineingeschrieben statt getauscht: es gibt ein Config-Objekt
        pro Prozess.
        """
        from ...config import CONFIG, apply_config
        from ...persistence import list_available_sequences, load_sequence_file
        state = AutoClickerState()
        apply_config(state.config, CONFIG)
        for name, path in list_available_sequences():
            seq = load_sequence_file(path)
            if seq is not None:
                state.sequences[seq.name or name] = seq
        seq = state.sequences.get(self.board.name)
        if seq is not None:
            state.active_sequence = seq
            state.points = seq.points
            from ...persistence import (
                load_all_boss_scans, load_all_icon_scans, load_all_item_scans,
                load_global_bosses, resolve_click_references,
            )
            load_all_item_scans(state)
            load_all_boss_scans(state)
            load_all_icon_scans(state)
            load_global_bosses(state, seq.name)
            resolve_click_references(state, seq)
        return state

    @staticmethod
    def _selected_parts(data: dict) -> dict:
        """Welche Teile angehakt sind — fehlende gelten als gewählt."""
        raw = (data or {}).get("teile")
        if not isinstance(raw, dict):
            return {k: True for k, _ in TEILE}
        return {k: bool(raw.get(k, True)) for k, _ in TEILE}

    # -------------------------------------------------------------- Export

    def export_start(self, data: Optional[dict] = None) -> dict:
        """Schreibt ein Bündel nach `exports/`.

        Die Referenzpunkte kommen aus der Fenstergrösse, wenn das Spielfenster
        offen ist — dann rechnet der Import die Koordinaten selbst um. Sonst
        bleiben die Ecken des virtuellen Desktops als grobe Bezugsgrösse.
        """
        data = data or {}
        parts = self._selected_parts(data)
        if not any(parts.values()):
            return self._share_report("Nichts ausgewählt.", "warn")

        lage = self._window_layout()
        window = tuple(lage["rechteck"]) if lage and lage.get("gefunden") else None
        if window:
            ref1, ref2 = (window[0], window[1]), (window[2], window[3])
        else:
            ref1, ref2 = self._fallback_reference()

        name = sanitize_filename(str(data.get("name") or "").strip())
        if not name:
            name = "autoclicker_export_" + datetime.now().strftime("%Y-%m-%d_%H%M%S")
        Path("exports").mkdir(exist_ok=True)
        path = Path("exports") / f"{name}.zip"

        from ...import_export import export_bundle
        erfolg, result = export_bundle(
            self._inventory(), str(path), ref1, ref2,
            include_points=parts["sequences"], include_sequences=parts["sequences"],
            include_slots=parts["sequences"], include_items=parts["sequences"],
            include_item_scans=parts["sequences"],
            include_boss_scans=parts["sequences"],
            include_icon_scans=parts["sequences"],
            include_config=parts["config"], source_window=window)
        if not erfolg:
            return self._share_report(f"Export fehlgeschlagen: {result}", "err")
        kb = os.path.getsize(result) / 1024
        zusatz = ("" if window else
                  "  Ohne offenes Spielfenster: der Empfänger setzt zwei Punkte von Hand.")
        return self._share_report(f"{path.name} geschrieben ({kb:.1f} KB)." + zusatz)

    @staticmethod
    def _fallback_reference() -> tuple:
        """Zwei Ecken, wenn kein Spielfenster gefunden wurde."""
        try:
            from ...winapi import get_virtual_desktop
            rechteck = get_virtual_desktop()
        except Exception:                                        # noqa: BLE001
            rechteck = None
        if not rechteck:
            return (0, 0), (1920, 1080)
        return (rechteck[0], rechteck[1]), (rechteck[2], rechteck[3])

    # -------------------------------------------------------------- Import

    def file_choose(self, data: Optional[dict] = None) -> dict:
        """Öffnet den Dateidialog des Fensters und prüft die Wahl."""
        try:
            import webview
            window = webview.windows[0]
            wahl = window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False,
                file_types=("Bündel (*.zip)", "Alle Dateien (*.*)"))
        except Exception:                                        # noqa: BLE001
            return self._share_report(
                "Dateidialog nicht verfügbar — Pfad von Hand eintragen.", "warn")
        if not wahl:
            return self.share_data()
        path = wahl[0] if isinstance(wahl, (list, tuple)) else wahl
        return self.import_check({"pfad": path})

    def import_check(self, data: Optional[dict] = None) -> dict:
        """Liest das Manifest und sagt, was drinsteht und wie umgerechnet wird."""
        path = str((data or {}).get("pfad") or "").strip().strip('"')
        if not path:
            self._teilen_import = None
            return self.share_data()
        from ...import_export import read_manifest
        erfolg, result = read_manifest(path)
        if not erfolg:
            self._teilen_import = None
            return self._share_report(str(result), "err")

        source = result.get("source_window")
        lage = self._window_layout()
        target = lage["rechteck"] if lage and lage.get("gefunden") else None
        content = result.get("contents", {}) or {}
        self._teilen_import = {
            "pfad": path,
            "file": Path(path).name,
            "erstellt": result.get("created", ""),
            "inhalt": {k: self._content_number(content.get(k)) for k, _ in TEILE},
            "source_window": list(source) if source else None,
            "target_window": list(target) if target else None,
            # Automatisch geht nur, wenn beide Seiten ihr Fenster kennen.
            "auto": bool(source and target),
        }
        return self._share_report(f"{Path(path).name} gelesen.")

    @staticmethod
    def _content_number(value) -> int:
        if isinstance(value, list):
            return len(value)
        if isinstance(value, (int, float)):
            return int(value)
        return 1 if value else 0

    def import_start(self, data: Optional[dict] = None) -> dict:
        """Spielt das geprüfte Bündel ein und lädt den Reiter danach neu."""
        data = data or {}
        if not self._teilen_import:
            return self._share_report("Erst eine Datei wählen.", "warn")
        parts = self._selected_parts(data)
        if not any(parts.values()):
            return self._share_report("Nichts ausgewählt.", "warn")

        transform = None
        if str(data.get("modus") or "auto") == "auto" and self._teilen_import["auto"]:
            from ...import_export import transform_from_windows
            transform = transform_from_windows(
                tuple(self._teilen_import["source_window"]),
                tuple(self._teilen_import["target_window"]))

        from ...import_export import import_bundle
        state = self._inventory()
        erfolg, result = import_bundle(
            state, self._teilen_import["pfad"], transform=transform,
            import_points=parts["sequences"], import_sequences=parts["sequences"],
            import_slots=parts["sequences"], import_items=parts["sequences"],
            import_item_scans=parts["sequences"],
            import_boss_scans=parts["sequences"],
            import_icon_scans=parts["sequences"],
            import_config=parts["config"], merge=bool(data.get("merge", True)))
        if not erfolg:
            return self._share_report(f"Import fehlgeschlagen: {result}", "err")

        # Der Import hat auf Platte geschrieben — beide Seiten müssen nachlesen.
        self._after_import()
        return self._share_report(str(result))

    def _after_import(self) -> None:
        """Fenster und Hauptprozess auf den neuen Stand bringen."""
        self.points = self._points_new()
        self._scan_geladen = False
        self._scan_dirty = False
        self._undo = []
        self._scan_load()
        try:
            from ...mailbox import send_command
            send_command("daten")
        except (ImportError, OSError):
            pass

    def _points_new(self) -> list:
        from ...persistence import load_sequence_file
        from .model import palette_from_sequence
        seq = load_sequence_file(self.filepath) if self.filepath.exists() else None
        return palette_from_sequence(seq) if seq is not None else list(self.points)
