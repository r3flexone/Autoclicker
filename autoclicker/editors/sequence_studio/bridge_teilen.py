"""Export und Import im Studio — ein Bündel schreiben, ein Bündel einlesen.

Die Logik liegt in `import_export.py`; hier steht nur, was das Fenster davon
braucht. Beide Wege arbeiten auf einem State, der frisch von Platte kommt:
exportiert wird der gespeicherte Stand, nicht der im Fenster.
"""

import json
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

    def _teilen_init(self) -> None:
        self._teilen_status = ("", "info")
        self._teilen_import: Optional[dict] = None

    # ------------------------------------------------------------ Anzeige

    def _teilen_melde(self, text: str, art: str = "ok") -> dict:
        self._teilen_status = (text, art)
        return self.teilen_daten()

    def teilen_daten(self, daten: Optional[dict] = None) -> dict:
        """Was der Reiter zeichnet. Fragt nur — ändert nichts."""
        text, art = self._teilen_status
        return {
            "teile": [{"key": k, "text": t} for k, t in TEILE],
            "bestand": self._bestand_zaehlen(),
            "fenster": self._fensterlage(),
            "exporte": self._export_liste(),
            "import": self._teilen_import,
            # Was im Fenster noch nicht gespeichert ist, liegt nicht auf Platte
            # und landet deshalb auch nicht im Bündel.
            "offen": bool(getattr(self, "_dirty", False)
                          or getattr(self, "_scan_dirty", False)),
            "status": {"text": text, "art": art},
        }

    @staticmethod
    def _zaehle_json(pfad, art) -> int:
        try:
            daten = json.loads(Path(pfad).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0
        return len(daten) if isinstance(daten, art) else 0

    def _bestand_zaehlen(self) -> dict:
        """Was auf Platte liegt — gezählt, nicht geladen."""
        from ...persistence import list_available_sequences
        return {
            "sequences": len(list_available_sequences()),
            "config": 1,
        }

    @staticmethod
    def _fensterlage() -> Optional[dict]:
        """Das Spielfenster, aus dem die Referenzpunkte kommen — oder None."""
        from ...config import CONFIG
        titel = CONFIG.window_focus_title
        if not titel:
            return None
        try:
            from ...winapi import get_client_rect_by_title
            rechteck = get_client_rect_by_title(titel)
        except Exception:                                        # noqa: BLE001
            rechteck = None
        if not rechteck:
            return {"titel": titel, "gefunden": False}
        l, o, r, u = rechteck
        return {"titel": titel, "gefunden": True, "rechteck": [l, o, r, u],
                "breite": r - l, "hoehe": u - o}

    @staticmethod
    def _export_liste() -> list:
        """Die vorhandenen Bündel, neueste zuerst."""
        ordner = Path("exports")
        if not ordner.is_dir():
            return []
        gefunden = []
        for pfad in ordner.glob("*.zip"):
            try:
                stat = pfad.stat()
            except OSError:
                continue
            gefunden.append({"name": pfad.name, "kb": round(stat.st_size / 1024, 1),
                             "stand": stat.st_mtime})
        return sorted(gefunden, key=lambda e: e["stand"], reverse=True)

    # ------------------------------------------------------------- Bestand

    def _bestand(self) -> AutoClickerState:
        """Alles von Platte in einen frischen State — Export/Import brauchen das Ganze.

        Der Studio-Prozess kennt sonst nur, was seine Reiter geöffnet haben. Die
        Config wird hineingeschrieben statt getauscht: es gibt ein Config-Objekt
        pro Prozess.
        """
        from ...config import CONFIG, uebernehmen
        from ...persistence import list_available_sequences, load_sequence_file
        state = AutoClickerState()
        uebernehmen(state.config, CONFIG)
        for name, pfad in list_available_sequences():
            seq = load_sequence_file(pfad)
            if seq is not None:
                state.sequences[seq.name or name] = seq
        seq = state.sequences.get(self.board.name)
        if seq is not None:
            state.active_sequence = seq
            state.points = seq.points
            from ...persistence import (
                load_all_boss_scans, load_all_icon_scans, load_all_item_scans,
                load_global_bosses, resolve_klick_referenzen,
            )
            load_all_item_scans(state)
            load_all_boss_scans(state)
            load_all_icon_scans(state)
            load_global_bosses(state, seq.name)
            resolve_klick_referenzen(state, seq)
        return state

    @staticmethod
    def _gewaehlte_teile(daten: dict) -> dict:
        """Welche Teile angehakt sind — fehlende gelten als gewählt."""
        roh = (daten or {}).get("teile")
        if not isinstance(roh, dict):
            return {k: True for k, _ in TEILE}
        return {k: bool(roh.get(k, True)) for k, _ in TEILE}

    # -------------------------------------------------------------- Export

    def export_starten(self, daten: Optional[dict] = None) -> dict:
        """Schreibt ein Bündel nach `exports/`.

        Die Referenzpunkte kommen aus der Fenstergrösse, wenn das Spielfenster
        offen ist — dann rechnet der Import die Koordinaten selbst um. Sonst
        bleiben die Ecken des virtuellen Desktops als grobe Bezugsgrösse.
        """
        daten = daten or {}
        teile = self._gewaehlte_teile(daten)
        if not any(teile.values()):
            return self._teilen_melde("Nichts ausgewählt.", "warn")

        lage = self._fensterlage()
        fenster = tuple(lage["rechteck"]) if lage and lage.get("gefunden") else None
        if fenster:
            ref1, ref2 = (fenster[0], fenster[1]), (fenster[2], fenster[3])
        else:
            ref1, ref2 = self._ersatz_referenz()

        name = sanitize_filename(str(daten.get("name") or "").strip())
        if not name:
            name = "autoclicker_export_" + datetime.now().strftime("%Y-%m-%d_%H%M%S")
        Path("exports").mkdir(exist_ok=True)
        pfad = Path("exports") / f"{name}.zip"

        from ...import_export import export_bundle
        erfolg, ergebnis = export_bundle(
            self._bestand(), str(pfad), ref1, ref2,
            include_points=teile["sequences"], include_sequences=teile["sequences"],
            include_slots=teile["sequences"], include_items=teile["sequences"],
            include_item_scans=teile["sequences"],
            include_boss_scans=teile["sequences"],
            include_icon_scans=teile["sequences"],
            include_config=teile["config"], source_window=fenster)
        if not erfolg:
            return self._teilen_melde(f"Export fehlgeschlagen: {ergebnis}", "err")
        kb = os.path.getsize(ergebnis) / 1024
        zusatz = ("" if fenster else
                  "  Ohne offenes Spielfenster: der Empfänger setzt zwei Punkte von Hand.")
        return self._teilen_melde(f"{pfad.name} geschrieben ({kb:.1f} KB)." + zusatz)

    @staticmethod
    def _ersatz_referenz() -> tuple:
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

    def datei_waehlen(self, daten: Optional[dict] = None) -> dict:
        """Öffnet den Dateidialog des Fensters und prüft die Wahl."""
        try:
            import webview
            fenster = webview.windows[0]
            wahl = fenster.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False,
                file_types=("Bündel (*.zip)", "Alle Dateien (*.*)"))
        except Exception:                                        # noqa: BLE001
            return self._teilen_melde(
                "Dateidialog nicht verfügbar — Pfad von Hand eintragen.", "warn")
        if not wahl:
            return self.teilen_daten()
        pfad = wahl[0] if isinstance(wahl, (list, tuple)) else wahl
        return self.import_pruefen({"pfad": pfad})

    def import_pruefen(self, daten: Optional[dict] = None) -> dict:
        """Liest das Manifest und sagt, was drinsteht und wie umgerechnet wird."""
        pfad = str((daten or {}).get("pfad") or "").strip().strip('"')
        if not pfad:
            self._teilen_import = None
            return self.teilen_daten()
        from ...import_export import read_manifest
        erfolg, ergebnis = read_manifest(pfad)
        if not erfolg:
            self._teilen_import = None
            return self._teilen_melde(str(ergebnis), "err")

        quelle = ergebnis.get("source_window")
        lage = self._fensterlage()
        ziel = lage["rechteck"] if lage and lage.get("gefunden") else None
        inhalt = ergebnis.get("contents", {}) or {}
        self._teilen_import = {
            "pfad": pfad,
            "datei": Path(pfad).name,
            "erstellt": ergebnis.get("created", ""),
            "inhalt": {k: self._inhalt_zahl(inhalt.get(k)) for k, _ in TEILE},
            "quelle_fenster": list(quelle) if quelle else None,
            "ziel_fenster": list(ziel) if ziel else None,
            # Automatisch geht nur, wenn beide Seiten ihr Fenster kennen.
            "auto": bool(quelle and ziel),
        }
        return self._teilen_melde(f"{Path(pfad).name} gelesen.")

    @staticmethod
    def _inhalt_zahl(wert) -> int:
        if isinstance(wert, list):
            return len(wert)
        if isinstance(wert, (int, float)):
            return int(wert)
        return 1 if wert else 0

    def import_starten(self, daten: Optional[dict] = None) -> dict:
        """Spielt das geprüfte Bündel ein und lädt den Reiter danach neu."""
        daten = daten or {}
        if not self._teilen_import:
            return self._teilen_melde("Erst eine Datei wählen.", "warn")
        teile = self._gewaehlte_teile(daten)
        if not any(teile.values()):
            return self._teilen_melde("Nichts ausgewählt.", "warn")

        transform = None
        if str(daten.get("modus") or "auto") == "auto" and self._teilen_import["auto"]:
            from ...import_export import transform_from_windows
            transform = transform_from_windows(
                tuple(self._teilen_import["quelle_fenster"]),
                tuple(self._teilen_import["ziel_fenster"]))

        from ...import_export import import_bundle
        state = self._bestand()
        erfolg, ergebnis = import_bundle(
            state, self._teilen_import["pfad"], transform=transform,
            import_points=teile["sequences"], import_sequences=teile["sequences"],
            import_slots=teile["sequences"], import_items=teile["sequences"],
            import_item_scans=teile["sequences"],
            import_boss_scans=teile["sequences"],
            import_icon_scans=teile["sequences"],
            import_config=teile["config"], merge=bool(daten.get("merge", True)))
        if not erfolg:
            return self._teilen_melde(f"Import fehlgeschlagen: {ergebnis}", "err")

        # Der Import hat auf Platte geschrieben — beide Seiten müssen nachlesen.
        self._nach_import()
        return self._teilen_melde(str(ergebnis))

    def _nach_import(self) -> None:
        """Fenster und Hauptprozess auf den neuen Stand bringen."""
        self.points = self._punkte_neu()
        self._scan_geladen = False
        self._scan_dirty = False
        self._undo = []
        self._scan_laden()
        try:
            from ...befehl import sende
            sende("daten")
        except (ImportError, OSError):
            pass

    def _punkte_neu(self) -> list:
        from ...persistence import load_sequence_file
        from .model import palette_from_sequence
        seq = load_sequence_file(self.filepath) if self.filepath.exists() else None
        return palette_from_sequence(seq) if seq is not None else list(self.points)
