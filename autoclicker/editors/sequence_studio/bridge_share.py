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
from .model import palette_from_sequence

# Was ein Bündel enthalten kann. Reihenfolge = Anzeige; die Schlüssel sind die
# Argumentnamen von `export_bundle`/`import_bundle` ohne Präfix.
PARTS = (
    ("sequences", "Sequenzordner (inkl. Punkte, Scans und Vorlagen)"),
    ("config", "Einstellungen"),
)


class BridgeShareMixin:
    """Der Reiter „Teilen": Bündel schreiben und einlesen."""

    def _share_init(self) -> None:
        self._share_status = ("", "info")
        self._share_import: Optional[dict] = None

    # ------------------------------------------------------------ Anzeige

    def _share_report(self, text: str, kind: str = "ok") -> dict:
        self._share_status = (text, kind)
        return self.share_data()

    def share_data(self, data: Optional[dict] = None) -> dict:
        """Was der Reiter zeichnet. Fragt nur — ändert nichts."""
        from ...config import CONFIG
        from ...import_export import list_bundles
        text, kind = self._share_status
        names = self._sequence_names()
        return {
            "parts": [{"key": k, "text": t} for k, t in PARTS],
            "inventory": {"sequences": len(names), "config": 1},
            # Zum Anhaken beim Export; die offene steht dabei, damit „nur die
            # offene“ ein Griff ist und kein Suchen in der Liste.
            "sequences": [{"name": n, "open": n == self.board.name} for n in names],
            "folder": self._folder_state(),
            "window": self._window_layout(),
            "exports": list_bundles(CONFIG),
            "import": self._share_import,
            # Was im Fenster noch nicht gespeichert ist, liegt nicht auf Platte
            # und landet deshalb auch nicht im Bündel.
            "open": bool(self._dirty or self._scan_dirty),
            "status": {"text": text, "kind": kind},
        }

    @staticmethod
    def _sequence_names() -> list:
        """Was auf Platte liegt — gezählt, nicht geladen."""
        from ...persistence import list_available_sequences
        return [name for name, _ in list_available_sequences()]

    @staticmethod
    def _folder_state() -> dict:
        """Wohin der Export schreibt: der Teilen-Ordner oder `exports/`.

        `found` ist die eigentliche Auskunft: ein eingestellter Ordner, den es
        gerade nicht gibt (USB-Platte ab, OneDrive umgezogen), sperrt den
        Export — und das soll man sehen, bevor man auf den Knopf drückt.
        """
        from ...config import CONFIG
        from ...import_export import EXPORT_DIR, share_folder
        folder = share_folder(CONFIG)
        if folder is None:
            return {"set": False, "path": str(EXPORT_DIR.resolve()), "found": True}
        return {"set": True, "path": str(folder), "found": folder.is_dir()}

    @staticmethod
    def _window_layout() -> Optional[dict]:
        """Das Spielfenster, aus dem die Referenzpunkte kommen — oder None."""
        from ...config import CONFIG
        title = CONFIG.window_focus_title
        if not title:
            return None
        try:
            from ...winapi import get_client_rect_by_title
            rect_value = get_client_rect_by_title(title)
        except Exception:                                        # noqa: BLE001
            rect_value = None
        if not rect_value:
            return {"title": title, "found": False}
        l, o, r, u = rect_value
        return {"title": title, "found": True, "rect": [l, o, r, u],
                "width": r - l, "height": u - o}

    # ------------------------------------------------------------- Bestand

    def _inventory(self) -> AutoClickerState:
        """Alles von Platte in einen frischen State — Export/Import brauchen das Ganze.

        Der Studio-Prozess kennt sonst nur, was seine Reiter geöffnet haben. Die
        Config wird hineingeschrieben statt getauscht: es gibt ein Config-Objekt
        pro Prozess.
        """
        from ...config import CONFIG, apply_config
        from ...persistence import (
            activate_sequence, list_available_sequences, load_sequence_file,
        )
        state = AutoClickerState()
        apply_config(state.config, CONFIG)
        path = next((p for n, p in list_available_sequences() if n == self.board.name), None)
        seq = load_sequence_file(path) if path is not None else None
        if seq is not None:
            # Der EINE Weg — Punkte, Scans und Bibliothek gemeinsam. Hier standen
            # dieselben sechs Zeilen noch einmal von Hand.
            activate_sequence(state, seq)
        return state

    @staticmethod
    def _selected_parts(data: dict) -> dict:
        """Welche Teile angehakt sind — fehlende gelten als gewählt."""
        raw = (data or {}).get("parts")
        if not isinstance(raw, dict):
            return {k: True for k, _ in PARTS}
        return {k: bool(raw.get(k, True)) for k, _ in PARTS}

    def _selected_sequences(self, data: dict) -> Optional[list]:
        """Welche Sequenzen ins Bündel kommen — None heisst alle.

        Was die Seite schickt, ist eine Liste von Namen. Ein Name, den es auf
        Platte nicht (mehr) gibt, fällt weg: die Seite zeigt einen Stand von
        vor ihrem letzten Neuaufbau, und eine inzwischen gelöschte Sequenz ist
        kein Grund, den ganzen Export abzulehnen.
        """
        raw = (data or {}).get("sequences")
        if not isinstance(raw, list):
            return None
        known = self._sequence_names()
        wanted = {str(n) for n in raw}
        return [n for n in known if n in wanted]

    # -------------------------------------------------------------- Export

    def export_start(self, data: Optional[dict] = None) -> dict:
        """Schreibt ein Bündel in den Teilen-Ordner, ohne einen nach `exports/`.

        Die Referenzpunkte kommen aus der Fenstergrösse, wenn das Spielfenster
        offen ist — dann rechnet der Import die Koordinaten selbst um. Sonst
        bleiben die Ecken des virtuellen Desktops als grobe Bezugsgrösse.
        """
        from ...config import CONFIG
        from ...import_export import export_bundle, export_target
        data = data or {}
        parts = self._selected_parts(data)
        if not any(parts.values()):
            return self._share_report("Nichts ausgewählt.", "warn")
        chosen = self._selected_sequences(data) if parts["sequences"] else None
        if chosen == []:
            return self._share_report("Keine Sequenz angehakt.", "warn")
        folder, problem = export_target(CONFIG)
        if folder is None:
            return self._share_report(problem + " — nichts geschrieben.", "err")

        layout = self._window_layout()
        window = tuple(layout["rect"]) if layout and layout.get("found") else None
        if window:
            ref1, ref2 = (window[0], window[1]), (window[2], window[3])
        else:
            ref1, ref2 = self._fallback_reference()

        path = folder / f"{self._bundle_name(data, chosen)}.zip"
        existed = path.exists()
        success, result = export_bundle(
            self._inventory(), str(path), ref1, ref2,
            include_sequences=parts["sequences"],
            include_config=parts["config"], source_window=window,
            sequences=chosen)
        if not success:
            return self._share_report(f"Export fehlgeschlagen: {result}", "err")
        kb = os.path.getsize(result) / 1024
        where = "im Teilen-Ordner" if self._folder_state()["set"] else "unter exports/"
        verb = "ersetzt" if existed else "geschrieben"
        extra = ("" if window else
                  "  Ohne offenes Spielfenster: der Empfänger setzt zwei Punkte von Hand.")
        return self._share_report(f"{path.name} {where} {verb} ({kb:.1f} KB)." + extra)

    @staticmethod
    def _bundle_name(data: dict, chosen: Optional[list]) -> str:
        """Der Dateiname ohne Endung: getippt, sonst aus dem Inhalt.

        **Eine einzelne Sequenz heisst wie sie, ohne Zeitstempel.** Im
        Teilen-Ordner ersetzt ein neuer Export damit den alten, und die anderen
        PCs finden unter demselben Namen immer die neueste Fassung — statt einer
        wachsenden Reihe `raid_2026-11-09_…`, von der nur die letzte gilt. Wer
        mehrere Sequenzen zusammen exportiert, bekommt den Zeitstempel weiter.

        **Geprüft wird die Eingabe, nicht das bereinigte Ergebnis.**
        `sanitize_filename("")` gibt „unbenannt“ zurück — hier stand
        `if not sanitize_filename(…)`, und der Zeitstempel kam deshalb nie: jeder
        Export ohne Namen hiess `unbenannt.zip` und ersetzte den vorigen, obwohl
        das Feld „leer = mit Zeitstempel“ versprach.
        """
        typed = str(data.get("name") or "").strip()
        if typed:
            return sanitize_filename(typed)
        if chosen and len(chosen) == 1:
            return sanitize_filename(chosen[0])
        return "autoclicker_export_" + datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # --------------------------------------------------------- Teilen-Ordner

    def share_folder_choose(self, data: Optional[dict] = None) -> dict:
        """Öffnet den Ordnerdialog des Fensters und setzt die Wahl."""
        try:
            import webview
            window = webview.windows[0]
            choice = window.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception:                                        # noqa: BLE001
            return self._share_report(
                "Ordnerdialog nicht verfügbar — Pfad von Hand eintragen.", "warn")
        if not choice:
            return self.share_data()
        path = choice[0] if isinstance(choice, (list, tuple)) else choice
        return self.share_folder_set({"path": path})

    def share_folder_set(self, data: Optional[dict] = None) -> dict:
        """Setzt den Teilen-Ordner (leer = zurück auf `exports/`) in `config.json`.

        **Angelegt wird nichts.** Ein vertippter Pfad legte sonst irgendwo einen
        Ordner an, und das Bündel käme auf keinem anderen PC an — genau das, was
        man mit dem Ordner erreichen wollte. Geschrieben wird über
        `config_write()`, damit der Hauptprozess (Konsolen-Export) mitzieht.
        """
        raw = str((data or {}).get("path") or "").strip().strip('"')
        if raw and not Path(raw).expanduser().is_dir():
            return self._share_report(f"Ordner nicht gefunden: {raw}", "err")
        result = self.config_write({"values": {"share_folder": raw}})
        if not result.get("ok"):
            return self._share_report(str(result.get("message") or "Nicht gespeichert."), "err")
        if raw:
            return self._share_report(f"Teilen-Ordner: {raw}. Bündel landen jetzt dort.")
        return self._share_report("Kein Teilen-Ordner mehr — Bündel landen wieder unter exports/.")

    @staticmethod
    def _fallback_reference() -> tuple:
        """Zwei Ecken, wenn kein Spielfenster gefunden wurde."""
        try:
            from ...winapi import get_virtual_desktop
            rect_value = get_virtual_desktop()
        except Exception:                                        # noqa: BLE001
            rect_value = None
        if not rect_value:
            return (0, 0), (1920, 1080)
        return (rect_value[0], rect_value[1]), (rect_value[2], rect_value[3])

    # -------------------------------------------------------------- Import

    def file_choose(self, data: Optional[dict] = None) -> dict:
        """Öffnet den Dateidialog des Fensters und prüft die Wahl.

        Er fängt im Teilen-Ordner an, wenn einer da ist — dort liegt, was die
        anderen PCs abgelegt haben.
        """
        folder = self._folder_state()
        start = folder["path"] if folder["set"] and folder["found"] else ""
        try:
            import webview
            window = webview.windows[0]
            choice = window.create_file_dialog(
                webview.OPEN_DIALOG, directory=start, allow_multiple=False,
                file_types=("Bündel (*.zip)", "Alle Dateien (*.*)"))
        except Exception:                                        # noqa: BLE001
            return self._share_report(
                "Dateidialog nicht verfügbar — Pfad von Hand eintragen.", "warn")
        if not choice:
            return self.share_data()
        path = choice[0] if isinstance(choice, (list, tuple)) else choice
        return self.import_check({"path": path})

    def import_check(self, data: Optional[dict] = None) -> dict:
        """Liest das Manifest und sagt, was drinsteht und wie umgerechnet wird."""
        path = str((data or {}).get("path") or "").strip().strip('"')
        if not path:
            self._share_import = None
            return self.share_data()
        from ...import_export import read_manifest
        success, result = read_manifest(path)
        if not success:
            self._share_import = None
            return self._share_report(str(result), "err")

        source = result.get("source_window")
        layout = self._window_layout()
        target = layout["rect"] if layout and layout.get("found") else None
        content = result.get("contents", {}) or {}
        self._share_import = {
            "path": path,
            "file": Path(path).name,
            "created": self._created_text(result.get("created")),
            "content": {k: self._content_number(content.get(k)) for k, _ in PARTS},
            "source_window": list(source) if source else None,
            "target_window": list(target) if target else None,
            # Automatisch geht nur, wenn beide Seiten ihr Fenster kennen.
            "auto": bool(source and target),
        }
        return self._share_report(f"{Path(path).name} gelesen.")

    @staticmethod
    def _created_text(raw) -> str:
        """Wann das Bündel geschrieben wurde, als Ortszeit zum Lesen — oder leer.

        Hier stand der rohe Wert aus dem Manifest, nur schrieb der Export nie
        einen hinein: das Feld war seit dem ersten Tag leer. Ein Bündel ohne
        `created` (älterer Export) bleibt leer, statt ein Datum zu erfinden.
        """
        try:
            return "erstellt " + datetime.fromisoformat(str(raw)).strftime("%d.%m.%Y %H:%M")
        except (TypeError, ValueError):
            return ""

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
        if not self._share_import:
            return self._share_report("Erst eine Datei wählen.", "warn")
        parts = self._selected_parts(data)
        if not any(parts.values()):
            return self._share_report("Nichts ausgewählt.", "warn")

        transform = None
        if str(data.get("mode") or "auto") == "auto" and self._share_import["auto"]:
            from ...import_export import transform_from_windows
            transform = transform_from_windows(
                tuple(self._share_import["source_window"]),
                tuple(self._share_import["target_window"]))

        from ...import_export import import_bundle
        state = self._inventory()
        success, result = import_bundle(
            state, self._share_import["path"], transform=transform,
            import_sequences=parts["sequences"],
            import_config=parts["config"], merge=bool(data.get("merge", True)))
        if not success:
            return self._share_report(f"Import fehlgeschlagen: {result}", "err")

        # Der Import hat auf Platte geschrieben — beide Seiten müssen nachlesen.
        self._after_import()
        return self._share_report(str(result))

    def _after_import(self) -> None:
        """Fenster und Hauptprozess auf den neuen Stand bringen."""
        self.points = self._points_new()
        self._scan_unload()
        self._scan_dirty = False
        self._undo = []
        self._edit_reset()
        self._scan_load()
        try:
            from ...mailbox import send_command
            send_command("data_reload")
        except (ImportError, OSError):
            pass

    def _points_new(self) -> list:
        from ...persistence import load_sequence_file
        seq = load_sequence_file(self.filepath) if self.filepath.exists() else None
        return palette_from_sequence(seq) if seq is not None else list(self.points)
