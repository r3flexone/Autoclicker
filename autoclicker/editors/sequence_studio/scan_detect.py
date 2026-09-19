"""Boss- und Icon-Scans im Scans-Reiter: Region, Erkennung, Aktion, Test.

Die Konsolen-Editoren führen linear durch Schritt 1–6, und jede spätere
Änderung lief denselben Ablauf noch einmal. Die Sache, um die es geht, ist
aber ein Rechteck auf einem Bild.

Zwei Regeln tragen das Modul:

- Der Assistent ist der Weg beim ersten Einrichten, die Eigenschaften-Spalte
  der für jede spätere Änderung: jedes Feld ist einzeln setzbar.
- Testen ist folgenlos — `boss_test`/`icon_test` benennen die Aktion nur.

Gerechnet wird mit `_check_profile_match()` aus `runtime/item_scan.py`, also
der Funktion, die im Lauf entscheidet.
"""

import threading
import time
from pathlib import Path
from typing import Optional

from ...models import (
    ACTION_TEXT,
    BOSS_ACTION_CLICK,
    BOSS_ACTION_KEY,
    BOSS_ACTION_RESTART,
    BOSS_ACTION_SCAN,
    BOSS_ACTION_SKIP,
    BOSS_ACTION_SKIP_CYCLE,
    BossProfile,
    BossScanConfig,
    IconScanConfig,
    SCAN_MODE_ALL,
    SCAN_MODE_BEST,
    SCAN_MODE_EVERY,
    VALID_BOSS_ACTIONS,
    VALID_ICON_ACTIONS,
    VALID_SCAN_MODES,
)
from ...utils import unique_name, sanitize_filename
from ...persistence.boss_scans import boss_scan_name_allowed
from .model import hex_color, rgb_value
from .scan_contract import (
    KIND_ITEM,
    rename_references,
    MIN_REGION,
    MODE_ACTION,
    MODE_REGION,
    MODE_CHOICE,
)
from .scan_model import normalize_region

# **Die Kacheln kommen aus `models.py`, nicht aus dem JavaScript.** Die Ansicht
# soll keine Aktionswerte erfinden — ein getipptes "skipcycle" wäre ein Wert, den
# `__post_init__` beim Speichern still auf den Standard hebt, und der Klick sähe
# aus, als hätte er gewirkt. Hier steht nur die REIHENFOLGE (die Menge prüft ein
# Test gegen `VALID_*_ACTIONS`); die Beschriftung kommt aus `ACTION_TEXT`.
_BOSS_ACTIONS = (BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY,
                  BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART)
_ICON_ACTIONS = tuple(a for a in _BOSS_ACTIONS if a != BOSS_ACTION_SCAN)
# **Die Kachel traegt ein Schlagwort, der Tooltip den Satz.** `ACTION_TEXT` ist
# fuer Prosa gemacht („Punkt klicken", „Zyklus abbrechen") und steht so in
# Meldungen und im Laufstatus; auf einer 9,5-px-Kachel in einem Sechser-Raster
# ist derselbe Satz zweizeilig und unlesbar. Zwei Verwendungen, zwei Laengen —
# ein Test haelt beide Tabellen auf denselben Schluesseln.
_ACTION_SHORT = {
    BOSS_ACTION_SCAN: "ITEM-SCAN",
    BOSS_ACTION_CLICK: "KLICK",
    BOSS_ACTION_KEY: "TASTE",
    BOSS_ACTION_SKIP: "SKIP",
    BOSS_ACTION_SKIP_CYCLE: "SKIP CYCLE",
    BOSS_ACTION_RESTART: "RESTART",
}
_SCAN_MODES_TEXT = (
    (SCAN_MODE_ALL, "bestes pro Kategorie"),
    (SCAN_MODE_BEST, "nur bestes"),
    (SCAN_MODE_EVERY, "alle Treffer"),
)


class _LibraryState:
    """Ein `AutoClickerState`-Stellvertreter für die Boss-Bibliothek.

    `save_global_bosses()`/`load_global_bosses()` nehmen einen State, benutzen
    davon aber nur `lock` und `global_bosses`. Diesen Prozess einen echten State
    bauen zu lassen hiesse, den halben Hauptprozess mitzuziehen — für eine
    Liste. Dieselbe Entscheidung wie bei `_ConfigOnly` in `scan_learning.py`.
    """

    def __init__(self, bosses=None):
        self.lock = threading.Lock()
        self.global_bosses = list(bosses or [])


class ScanDetectMixin:
    """Boss- und Icon-Scans: Bestand, Bearbeitung, Test."""

    # ------------------------------------------------------------- Zustand

    def _detection_init(self) -> None:
        """Wird aus `_scan_init()` gerufen."""
        self.boss_scans: dict = {}
        self.icon_scans: dict = {}
        self.global_bosses: list = []
        # Der offene Scan ist der Zusammenhang, die Wahl das bearbeitete Ding —
        # dieselbe Trennung wie `open_scan` neben `scan_name` bei den Items.
        self.boss_open: str = ""
        self.boss_choice: str = ""
        self.boss_choice_global: bool = False
        self.icon_open: str = ""
        # Worauf das Region- bzw. Aktions-Werkzeug wirkt: ("boss"|"icon", Name).
        # Der Modus allein reicht nicht — dieselbe Geste setzt je nach Art eine
        # andere Region, und die Scan-Art selbst ist Oberflächenzustand.
        self._region_target: Optional[tuple] = None
        self._boss_test_result: Optional[dict] = None
        self._boss_test_results: dict = {}
        self._icon_test_result: Optional[dict] = None
        # Ergebnis des letzten Erreichbarkeitstests: None = nie gefragt. Für
        # beide gilt dasselbe — die Antwort kostet (Netz bzw. ein schwerer
        # Import) und gehört deshalb nicht in jede Momentaufnahme.
        self._llm_state: Optional[dict] = None
        self._ocr_state: Optional[dict] = None

    def _detection_load(self) -> None:
        """Boss-Scans, Icon-Scans und die Bibliothek von Platte.

        Läuft aus `_scan_load()` mit, also einmal je Sitzung und danach nur
        wieder auf „Neu laden" — dieselbe Regel wie bei Slots und Items.
        """
        from ...persistence import (
            list_available_boss_scans,
            list_available_icon_scans,
            load_boss_scan_file,
            load_global_bosses,
            load_icon_scan_file,
        )
        self.boss_scans = {}
        for name, path in list_available_boss_scans(self.board.name):
            cfg = load_boss_scan_file(path, self.board.name)
            if cfg is not None:
                self.boss_scans[cfg.name or name] = cfg
        self.icon_scans = {}
        for name, path in list_available_icon_scans(self.board.name):
            cfg = load_icon_scan_file(path, self.board.name)
            if cfg is not None:
                self.icon_scans[cfg.name or name] = cfg
        stand_in = _LibraryState()
        load_global_bosses(stand_in, self.board.name)
        self.global_bosses = stand_in.global_bosses
        if self.boss_open not in self.boss_scans:
            self.boss_open = next(iter(self.boss_scans), "")
        if self.icon_open not in self.icon_scans:
            self.icon_open = next(iter(self.icon_scans), "")
        self.boss_choice, self.boss_choice_global = "", False

    def _detection_paths(self) -> list:
        """Was der Reiter an Boss-/Icon-Dateien liest — für den Fremd-Vergleich.

        Der Hauptprozess schreibt dieselben Dateien: der Konsolen-Editor bleibt
        als zweiter Weg bestehen, und ein Boss, den ein Lauf per LLM entdeckt
        hat, landet in der Bibliothek. Ohne diese Pfade meldete der Reiter „auf
        Platte hat sich etwas geändert" nur für Items — also ausgerechnet nicht
        für das, was hier gerade bearbeitet wird.
        """
        wurzel = self.filepath.parent
        folder_list = (wurzel / "boss_scans", wurzel / "icon_scans")
        paths = [*folder_list, wurzel / "boss_scans" / "bibliothek.json"]
        for folder in folder_list:
            if folder.is_dir():
                paths += sorted(folder.glob("*.json"))
        return paths

    def _detection_state(self) -> dict:
        """Der Teil des Rückgängig-Abzugs, der diesem Modul gehört."""
        import copy
        return {
            "boss_scans": copy.deepcopy(self.boss_scans),
            "icon_scans": copy.deepcopy(self.icon_scans),
            "global_bosses": copy.deepcopy(self.global_bosses),
            "boss_open": self.boss_open,
            "boss_choice": self.boss_choice,
            "boss_choice_global": self.boss_choice_global,
            "icon_open": self.icon_open,
        }

    def _detection_undo(self, stamp: dict) -> None:
        self.boss_scans = stamp.get("boss_scans", {})
        self.icon_scans = stamp.get("icon_scans", {})
        self.global_bosses = stamp.get("global_bosses", [])
        self.boss_open = stamp.get("boss_open", "")
        self.boss_choice = stamp.get("boss_choice", "")
        self.boss_choice_global = stamp.get("boss_choice_global", False)
        self.icon_open = stamp.get("icon_open", "")
        # Ein Testergebnis gehört zu dem Stand, in dem es gemessen wurde.
        self._boss_test_result = self._icon_test_result = None
        self._boss_test_results = {}

    # ------------------------------------------------------- Momentaufnahme

    def _detection_json(self) -> dict:
        """Was der Reiter über Boss- und Icon-Scans zu wissen braucht."""
        return {
            "boss_scans": [self._boss_scan_json(c) for c in self.boss_scans.values()],
            "icon_scans": [self._icon_scan_json(c) for c in self.icon_scans.values()],
            "global_bosses": [self._boss_json(b, True) for b in self.global_bosses],
            "boss": {
                "open": self.boss_open,
                "choice": self.boss_choice,
                "choice_global": self.boss_choice_global,
                "test": self._boss_test_result,
                "tests": self._boss_test_results,
            },
            "icon": {"open": self.icon_open, "test": self._icon_test_result},
            "region_target": (list(self._region_target) if self._region_target else None),
            # Was die Aktionen brauchen: die Punkte kennt die Sequenz-Seite der
            # Brücke, die Item-Scan-Namen der Item-Teil. Beides steht hier
            # nochmal, weil der Reiter sonst zwei Kanäle bräuchte.
            "points": [{"id": p.id, "name": p.name or f"Punkt {p.id}",
                        "x": p.x, "y": p.y} for p in self.points],
            "item_scan_names": sorted(self.scans, key=str.casefold),
            "actions": {
                "boss": [{"value": a, "text": ACTION_TEXT[a], "short": _ACTION_SHORT[a]}
                         for a in _BOSS_ACTIONS],
                "icon": [{"value": a, "text": ACTION_TEXT[a], "short": _ACTION_SHORT[a]}
                         for a in _ICON_ACTIONS],
                "scan_modes": [{"value": w, "text": t} for w, t in _SCAN_MODES_TEXT],
            },
            "ready": self._ready(),
        }

    def _boss_scan_json(self, cfg: BossScanConfig) -> dict:
        return {
            "name": cfg.name,
            "region": list(cfg.scan_region),
            "tolerance": cfg.color_tolerance,
            "default_action": cfg.default_action,
            "default_scan": cfg.default_scan,
            "use_llm": bool(cfg.use_llm),
            "llm_fallback": bool(cfg.llm_fallback),
            "use_ocr": bool(cfg.use_ocr),
            "ocr_fallback": bool(cfg.ocr_fallback),
            "bosses": [self._boss_json(b, False) for b in cfg.bosses],
        }

    def _boss_json(self, b: BossProfile, from_library: bool) -> dict:
        return {
            "name": b.name,
            "global": from_library,
            "template": b.template,
            "preview": self._template_url(b.template) if b.template else "",
            "confidence": b.min_confidence,
            "marker": [hex_color(c) for c in b.marker_colors],
            "action": b.action,
            "scan": b.action_scan,
            "scan_mode": b.action_scan_mode,
            "point_id": b.action_point_id,
            "action_key": b.action_key,
            "delay": b.action_delay,
            # Ein Profil ohne Template UND ohne Marker wird nie per Bild
            # erkannt — nur noch per OCR/LLM. Das ist keine Warnung, sondern
            # eine Auskunft: der Reiter sagt daneben, ob OCR überhaupt an ist.
            "detection": ("template" if b.template
                          else ("marker" if b.marker_colors else "none")),
        }

    def _icon_scan_json(self, cfg: IconScanConfig) -> dict:
        remaining = cfg.name == self.icon_open
        return {
            "name": cfg.name,
            "region": list(cfg.scan_region),
            "template": cfg.template,
            "preview": self._template_url(cfg.template) if cfg.template else "",
            "confidence": cfg.min_confidence,
            "marker": [hex_color(c) for c in cfg.marker_colors],
            "tolerance": cfg.color_tolerance,
            "action": cfg.action,
            "point_id": cfg.action_point_id,
            "action_key": cfg.action_key,
            "delay": cfg.action_delay,
            "detection": ("template" if cfg.template
                          else ("marker" if cfg.marker_colors else "none")),
            # **Der Ausschnitt zeigt, was der Scan sieht.** Nur für den offenen:
            # bei zwanzig Icon-Scans wären das zwanzig Bilder in jeder
            # Momentaufnahme, und neunzehn davon sieht niemand an.
            "crop_image": self._region_image(cfg.scan_region) if remaining else "",
        }

    def _region_image(self, region) -> str:
        """Der Bildausschnitt einer Region als data:-URL — leer ohne Bild."""
        crop = self._photo_crop(tuple(region))
        if crop is None:
            return ""
        from .scan_capture import _as_data_url
        return _as_data_url(crop)

    def _ready(self) -> dict:
        """Welche Erkennungswege überhaupt zur Verfügung stehen.

        Fehlende Voraussetzungen blenden nichts aus, sie erklären sich: ohne OpenCV
        wird die Template-Wahl inaktiv und nennt den pip-Befehl.

        OCR und LLM stehen als `None`, bis jemand `ocr_check()` bzw. `llm_check()`
        drückt — `import easyocr` zieht Torch nach und dauert Sekunden, das hat in
        einer Momentaufnahme nichts verloren.
        """
        from ...config import CONFIG
        return {
            "opencv": self._has_opencv(),
            "pillow": self._has_pillow(),
            "ocr_state": self._ocr_state,
            "ocr_on": bool(CONFIG.ocr_enabled),
            "ocr_backend": CONFIG.ocr_backend or "automatisch",
            "ocr_languages": list(CONFIG.ocr_languages or []),
            "ocr_min": CONFIG.ocr_min_confidence,
            "llm_on": bool(CONFIG.llm_enabled),
            "llm_endpoint": CONFIG.llm_endpoint,
            "llm_model": CONFIG.llm_model or "",
            "llm_state": self._llm_state,
            "boss_learn_global": bool(CONFIG.boss_learn_global),
            "marker_all": bool(CONFIG.scan_require_all_markers),
            "marker_required": int(CONFIG.scan_min_markers_required),
            "marker_min_pixel": int(CONFIG.scan_marker_min_pixels),
        }

    # ------------------------------------------------------------ Boss-Scans

    def boss_scan_new(self, data: Optional[dict] = None) -> dict:
        """Ein neuer Boss-Scan — leer, mit eindeutigem Namen, sofort offen."""
        self._scan_load()
        name = unique_name(str((data or {}).get("name") or "Neuer Boss-Scan"),
                                self.boss_scans)
        if not boss_scan_name_allowed(name):
            return self._scan_report("'bibliothek' ist für die Boss-Bibliothek reserviert.", "err")
        self._remember("Boss-Scan angelegt")
        self.boss_scans[name] = BossScanConfig(name=name, owner_sequence=self.board.name)
        self.boss_open, self.boss_choice = name, ""
        return self._scan_changed(
            f"Boss-Scan '{name}' angelegt. Region aufziehen, dann Bosse anlegen.")

    def boss_scan_open(self, data: Optional[dict] = None) -> dict:
        """Wählt den Boss-Scan, in dessen Zusammenhang gearbeitet wird."""
        self._scan_load()
        name = str((data or {}).get("name") or "")
        if name and name not in self.boss_scans:
            return self._scan_report(f"Boss-Scan '{name}' gibt es nicht.", "err")
        self.boss_open, self.boss_choice, self.boss_choice_global = name, "", False
        self._boss_test_result, self._boss_test_results = None, {}
        self._region_target = None
        if not name:
            return self._scan_report("Kein Boss-Scan offen.", "info")
        return self._scan_report(f"Boss-Scan '{name}' geöffnet.")

    def boss_scan_set(self, data: Optional[dict] = None) -> dict:
        """Ein Feld eines Boss-Scans — jedes einzeln, ohne Durchlauf."""
        self._scan_load()
        data = data or {}
        cfg = self.boss_scans.get(str(data.get("name") or self.boss_open))
        if cfg is None:
            return self._scan_report("Kein Boss-Scan gewählt.", "warn")
        field, value = str(data.get("field") or ""), data.get("value")

        if field == "name":
            return self._detection_rename(self.boss_scans, cfg, value, "Boss-Scan")
        if field == "region":
            return self._region_set(cfg, value, f"Boss-Scan '{cfg.name}'")
        if field == "tolerance":
            number = self._integer(value)
            if number is None:
                return self._scan_report("Die Farb-Toleranz muss eine Zahl sein.", "err")
            self._remember(f"'{cfg.name}': Farb-Toleranz")
            cfg.color_tolerance = max(0, number)
            return self._scan_changed()
        if field == "default_action":
            if value not in VALID_BOSS_ACTIONS:
                return self._scan_report(f"Unbekannte Aktion '{value}'.", "err")
            self._remember(f"'{cfg.name}': Fallback-Aktion")
            cfg.default_action = str(value)
            return self._scan_changed(
                f"Ohne erkannten Boss: {ACTION_TEXT.get(cfg.default_action, cfg.default_action)}.")
        if field == "default_scan":
            self._remember(f"'{cfg.name}': Fallback-Scan")
            cfg.default_scan = str(value) or None
            return self._scan_changed()
        if field in ("use_llm", "llm_fallback", "use_ocr", "ocr_fallback"):
            self._remember(f"'{cfg.name}': {field}")
            setattr(cfg, field, bool(value))
            return self._scan_changed(self._ways_text(cfg), "info")
        return self._scan_report(f"Unbekanntes Feld '{field}'.", "err")

    @staticmethod
    def _ways_text(cfg: BossScanConfig) -> str:
        """In welcher Reihenfolge erkannt wird — als ein Satz.

        Bei gleicher Einstellung läuft **OCR vor LLM**: OCR ist lokal und
        schnell, das LLM kostet bis `llm_timeout`. Das steht in
        `runtime/boss_detection.py` genauso — hier wird es nur vorgelesen.
        """
        front = [name for name, an, fallback in
                (("OCR", cfg.use_ocr, cfg.ocr_fallback), ("LLM", cfg.use_llm, cfg.llm_fallback))
                if an and not fallback]
        back = [name for name, an, fallback in
                  (("OCR", cfg.use_ocr, cfg.ocr_fallback), ("LLM", cfg.use_llm, cfg.llm_fallback))
                  if an and fallback]
        parts = front + ["Template/Marker"] + back
        return "Reihenfolge: " + " → ".join(parts)

    def boss_scan_delete(self, data: Optional[dict] = None) -> dict:
        """Löscht den offenen Boss-Scan samt Datei."""
        self._scan_load()
        name = str((data or {}).get("name") or self.boss_open)
        if name not in self.boss_scans:
            return self._scan_report("Kein Boss-Scan gewählt.", "warn")
        self._remember(f"Boss-Scan '{name}' gelöscht")
        del self.boss_scans[name]
        self.boss_open = next(iter(self.boss_scans), "")
        self.boss_choice = ""
        return self._file_gone(self.filepath.parent / "boss_scans"
                               / f"{sanitize_filename(name)}.json",
                               f"Boss-Scan '{name}'")

    # ----------------------------------------------------------- Einzelbosse

    def boss_select(self, data: Optional[dict] = None) -> dict:
        """Wählt einen Boss zum Bearbeiten — lokal oder aus der Bibliothek."""
        self._scan_load()
        data = data or {}
        name = str(data.get("name") or "")
        from_library = bool(data.get("global"))
        if name and self._boss_find(name, from_library) is None:
            return self._scan_report(f"Boss '{name}' gibt es nicht.", "err")
        self.boss_choice, self.boss_choice_global = name, from_library
        self._region_target = None
        return self.scan_data()

    def _boss_find(self, name: str, from_library: bool) -> Optional[BossProfile]:
        if from_library:
            return next((b for b in self.global_bosses if b.name == name), None)
        cfg = self.boss_scans.get(self.boss_open)
        if cfg is None:
            return None
        return next((b for b in cfg.bosses if b.name == name), None)

    def _boss_selected(self) -> Optional[BossProfile]:
        return (self._boss_find(self.boss_choice, self.boss_choice_global)
                if self.boss_choice else None)

    def _boss_names(self) -> list:
        """Alle Namen, die kollidieren könnten — lokal plus Bibliothek.

        Bei Namensgleichheit gewinnt der lokale Boss (so merged
        `execute_boss_scan`). Ein zweiter mit demselben Namen ist deshalb kein
        Fehler, aber eine Falle: der eine verdeckt den anderen, ohne dass man es
        sieht. Der Namensvorschlag geht ihr aus dem Weg.
        """
        cfg = self.boss_scans.get(self.boss_open)
        names = [b.name for b in (cfg.bosses if cfg else [])]
        return names + [b.name for b in self.global_bosses]

    def boss_new(self, data: Optional[dict] = None) -> dict:
        """Legt einen Boss an — im offenen Scan oder in der Bibliothek."""
        self._scan_load()
        data = data or {}
        in_library = bool(data.get("global"))
        cfg = self.boss_scans.get(self.boss_open)
        if cfg is None and not in_library:
            return self._scan_report("Erst einen Boss-Scan anlegen oder öffnen.", "warn")
        name = unique_name(str(data.get("name") or "Neuer Boss"), self._boss_names())
        self._remember(f"Boss '{name}' angelegt")
        boss = BossProfile(name=name, action=BOSS_ACTION_SKIP)
        if in_library:
            self.global_bosses.append(boss)
        else:
            cfg.bosses.append(boss)
        self.boss_choice, self.boss_choice_global = name, in_library
        return self._scan_changed(
            f"Boss '{name}' angelegt — jetzt Vorlage aufnehmen oder Marker messen.")

    def boss_set(self, data: Optional[dict] = None) -> dict:
        """Ein Feld eines Bosses. Jedes einzeln — das ist der Punkt der Ansicht."""
        self._scan_load()
        data = data or {}
        name = str(data.get("name") or self.boss_choice)
        from_library = bool(data.get("global", self.boss_choice_global))
        boss = self._boss_find(name, from_library)
        if boss is None:
            return self._scan_report("Kein Boss gewählt.", "warn")
        field, value = str(data.get("field") or ""), data.get("value")

        if field == "name":
            new = str(value or "").strip()
            if not new or new == boss.name:
                return self.scan_data()
            if new in self._boss_names():
                return self._scan_report(f"'{new}' gibt es schon.", "warn")
            self._remember(f"Boss '{boss.name}' umbenannt")
            boss.name = new
            self.boss_choice = new
            return self._scan_changed(f"Boss heisst jetzt '{new}'.")
        if field == "action":
            if value not in VALID_BOSS_ACTIONS:
                return self._scan_report(f"Unbekannte Aktion '{value}'.", "err")
            self._remember(f"Boss '{boss.name}': Aktion")
            boss.action = str(value)
            return self._scan_changed(
                f"Bei Treffer: {ACTION_TEXT.get(boss.action, boss.action)}.")
        if field == "scan":
            self._remember(f"Boss '{boss.name}': Item-Scan")
            boss.action_scan = str(value) or None
            return self._scan_changed()
        if field == "scan_mode":
            if value not in VALID_SCAN_MODES:
                return self._scan_report(f"Unbekannter Scan-Modus '{value}'.", "err")
            self._remember(f"Boss '{boss.name}': Scan-Modus")
            boss.action_scan_mode = str(value)
            return self._scan_changed()
        return self._profile_field(boss, field, value, f"Boss '{boss.name}'")

    def boss_delete(self, data: Optional[dict] = None) -> dict:
        """Entfernt einen Boss aus seinem Scan bzw. aus der Bibliothek."""
        self._scan_load()
        data = data or {}
        name = str(data.get("name") or self.boss_choice)
        from_library = bool(data.get("global", self.boss_choice_global))
        boss = self._boss_find(name, from_library)
        if boss is None:
            return self._scan_report("Kein Boss gewählt.", "warn")
        self._remember(f"Boss '{name}' gelöscht")
        if from_library:
            self.global_bosses = [b for b in self.global_bosses if b is not boss]
        else:
            cfg = self.boss_scans[self.boss_open]
            cfg.bosses = [b for b in cfg.bosses if b is not boss]
        if self.boss_choice == name:
            self.boss_choice = ""
        self._boss_test_results.pop(name, None)
        # Das Template bleibt liegen: den lokalen Template-Ordner teilen sich Items,
        # Bosse und Icons, und eine Datei zu löschen, die einem anderen gehört,
        # ist der stille Datenverlust, den es hier nicht gibt.
        return self._scan_changed(f"Boss '{name}' entfernt (Vorlage bleibt liegen).", "warn")

    def boss_move_global(self, data: Optional[dict] = None) -> dict:
        """Schiebt einen Boss zwischen Scan und Bibliothek hin und her.

        **Die Bibliothek gilt zusätzlich in JEDEM Boss-Scan.** Wer denselben
        Boss in drei Scans braucht, pflegt ihn sonst dreimal — und ändert beim
        vierten Mal nur zwei davon.
        """
        self._scan_load()
        data = data or {}
        name = str(data.get("name") or self.boss_choice)
        from_library = bool(data.get("global", self.boss_choice_global))
        boss = self._boss_find(name, from_library)
        if boss is None:
            return self._scan_report("Kein Boss gewählt.", "warn")
        cfg = self.boss_scans.get(self.boss_open)
        if cfg is None and from_library:
            return self._scan_report("Erst einen Boss-Scan öffnen.", "warn")
        self._remember(f"Boss '{name}' verschoben")
        if from_library:
            self.global_bosses = [b for b in self.global_bosses if b is not boss]
            cfg.bosses.append(boss)
            self.boss_choice_global = False
            text = f"'{name}' gilt jetzt nur noch in '{cfg.name}'."
        else:
            cfg.bosses = [b for b in cfg.bosses if b is not boss]
            self.global_bosses.append(boss)
            self.boss_choice_global = True
            text = f"'{name}' liegt jetzt in der Bibliothek und gilt in jedem Boss-Scan."
        return self._scan_changed(text)

    # ------------------------------------------------------------ Icon-Scans

    def icon_scan_new(self, data: Optional[dict] = None) -> dict:
        """Ein neuer Icon-Scan — das kleinste Modell: Region, Erkennung, Aktion."""
        self._scan_load()
        name = unique_name(str((data or {}).get("name") or "Neuer Icon-Scan"),
                                self.icon_scans)
        self._remember("Icon-Scan angelegt")
        self.icon_scans[name] = IconScanConfig(name=name, owner_sequence=self.board.name)
        self.icon_open = name
        return self._scan_changed(
            f"Icon-Scan '{name}' angelegt. Region eng um das Symbol aufziehen.")

    def icon_scan_open(self, data: Optional[dict] = None) -> dict:
        self._scan_load()
        name = str((data or {}).get("name") or "")
        if name and name not in self.icon_scans:
            return self._scan_report(f"Icon-Scan '{name}' gibt es nicht.", "err")
        self.icon_open = name
        self._icon_test_result = None
        self._region_target = None
        return self._scan_report(f"Icon-Scan '{name}' geöffnet." if name
                                else "Kein Icon-Scan offen.", "ok" if name else "info")

    def icon_set(self, data: Optional[dict] = None) -> dict:
        """Ein Feld eines Icon-Scans."""
        self._scan_load()
        data = data or {}
        cfg = self.icon_scans.get(str(data.get("name") or self.icon_open))
        if cfg is None:
            return self._scan_report("Kein Icon-Scan gewählt.", "warn")
        field, value = str(data.get("field") or ""), data.get("value")
        if field == "name":
            return self._detection_rename(self.icon_scans, cfg, value, "Icon-Scan")
        if field == "region":
            return self._region_set(cfg, value, f"Icon-Scan '{cfg.name}'")
        if field == "action":
            if value not in VALID_ICON_ACTIONS:
                return self._scan_report(f"Unbekannte Aktion '{value}'.", "err")
            self._remember(f"'{cfg.name}': Aktion")
            cfg.action = str(value)
            return self._scan_changed(
                f"Bei Fund: {ACTION_TEXT.get(cfg.action, cfg.action)}.")
        return self._profile_field(cfg, field, value, f"Icon-Scan '{cfg.name}'")

    def icon_scan_delete(self, data: Optional[dict] = None) -> dict:
        self._scan_load()
        name = str((data or {}).get("name") or self.icon_open)
        if name not in self.icon_scans:
            return self._scan_report("Kein Icon-Scan gewählt.", "warn")
        self._remember(f"Icon-Scan '{name}' gelöscht")
        del self.icon_scans[name]
        self.icon_open = next(iter(self.icon_scans), "")
        return self._file_gone(self.filepath.parent / "icon_scans"
                               / f"{sanitize_filename(name)}.json",
                               f"Icon-Scan '{name}'")

    # ------------------------------------------------- Geteilte Feld-Setzer

    def _profile_field(self, obj, field: str, value, who: str) -> dict:
        """Die Felder, die Boss und Icon gemeinsam haben.

        Beide erkennen über Template **oder** Farb-Marker und handeln danach —
        das sind dieselben sechs Felder. Zwei Setzer dafür wären zwei Stellen,
        an denen eine Prüfung fehlen kann.
        """
        if field == "confidence":
            number = self._decimal(value)
            if number is None or not 0 < number <= 1:
                return self._scan_report("Konfidenz muss zwischen 0 und 1 liegen.", "err")
            self._remember(f"{who}: Konfidenz")
            obj.min_confidence = number
            return self._scan_changed()
        if field == "tolerance":
            number = self._integer(value)
            if number is None:
                return self._scan_report("Die Toleranz muss eine ganze Zahl sein.", "err")
            self._remember(f"{who}: Toleranz")
            obj.color_tolerance = max(0, number)
            return self._scan_changed()
        if field == "template":
            self._remember(f"{who}: Vorlage")
            obj.template = str(value) or None
            return self._scan_changed()
        if field == "marker":
            colors = [rgb_value(h) for h in (value or [])]
            self._remember(f"{who}: Marker")
            obj.marker_colors = [f for f in colors if f]
            return self._scan_changed(f"{len(obj.marker_colors)} Marker-Farbe(n).")
        if field == "point":
            point_id = self._integer(value)
            self._remember(f"{who}: Klickpunkt")
            obj.action_point_id = point_id
            self._action_point_apply(obj)
            return self._scan_changed()
        if field == "action_key":
            self._remember(f"{who}: Taste")
            obj.action_key = str(value) or None
            return self._scan_changed()
        if field == "delay":
            number = self._decimal(value)
            if number is None or number < 0:
                return self._scan_report("Die Verzögerung muss eine Zahl ≥ 0 sein.", "err")
            self._remember(f"{who}: Verzögerung")
            obj.action_delay = number
            return self._scan_changed()
        return self._scan_report(f"Unbekanntes Feld '{field}'.", "err")

    def _action_point_apply(self, obj) -> None:
        """Zieht `action_x/y` an der Referenz nach.

        Die Koordinate steht in der Punktliste der `sequence.json`, sonst nirgends — `action_x/y`
        sind abgeleitete Arbeitswerte, genau wie `step.x/y`. Der Serializer
        schreibt sie nicht; gefüllt werden sie, damit die Anzeige etwas zu
        zeigen hat.
        """
        point = next((p for p in self.points if p.id == obj.action_point_id), None)
        obj.action_x = point.x if point else 0
        obj.action_y = point.y if point else 0

    def _detection_rename(self, inventory: dict, cfg, value, word: str) -> dict:
        """Umbenennen eines Boss-/Icon-Scans — Schlüssel, Referenzen und Datei.

        **Hier stand einmal das Gegenteil**, und die Begründung war „die alte
        Datei bleibt liegen, sonst verlöre eine Sequenz, die noch auf den alten
        Namen zeigt, ihren Scan kommentarlos". Das kurierte das Symptom und
        machte den Schaden grösser: die Referenzen wurden nicht nachgezogen,
        also zeigte der Block weiter auf den ALTEN Namen und lief gegen die
        liegengebliebene Datei — jede spätere Änderung am umbenannten Scan
        wirkte im Lauf nicht. Und weil `_scan_load()` den Ordner durchsieht,
        stand der Scan nach dem nächsten Öffnen ZWEIMAL da (gemessen: aus
        `wache` wurden `['drache', 'wache']`). Ein Umbenennen, das klont, ist
        kein Umbenennen.

        Es läuft deshalb wie beim Item-Scan: Referenzen nachziehen, dann die
        alte Datei entfernen.
        """
        new = sanitize_filename(str(value or "").strip())
        if inventory is self.boss_scans and not boss_scan_name_allowed(new):
            return self._scan_report("'bibliothek' ist für die Boss-Bibliothek reserviert.", "err")
        if not new or new == cfg.name:
            return self.scan_data()
        if new in inventory:
            return self._scan_report(f"'{new}' gibt es schon.", "warn")
        self._remember(f"{word} '{cfg.name}' umbenannt")
        old = cfg.name
        new_inventory = {(new if k == old else k): v for k, v in inventory.items()}
        inventory.clear()
        inventory.update(new_inventory)
        cfg.name = new
        is_boss = inventory is self.boss_scans
        if self.boss_open == old and is_boss:
            self.boss_open = new
        if self.icon_open == old and not is_boss:
            self.icon_open = new
        # Der Name IST die Referenz — Blöcke und Beschriftungen ziehen mit.
        hit = rename_references(self.board, "boss" if is_boss else "icon",
                                          old, new)
        subfolder = "boss_scans" if is_boss else "icon_scans"
        old_path = (self.filepath.parent / subfolder
                    / f"{sanitize_filename(old)}.json")
        try:
            old_path.unlink(missing_ok=True)
        except OSError:
            return self._scan_report(
                f"'{old}' wurde umbenannt, die alte Datei blieb liegen.", "warn")
        extra = f" ({hit}× in der Sequenz nachgezogen)" if hit else ""
        return self._scan_changed(f"'{old}' heisst jetzt '{new}'.{extra}")

    def _region_set(self, cfg, value, who: str) -> dict:
        """Eine Region aus vier getippten Zahlen.

        Die Zahlenfelder bleiben neben dem Aufziehen bestehen: eine Region um
        drei Pixel zu korrigieren ist über zwei Klicks im Bild schlechter zu
        treffen als über ein Zahlenfeld.
        """
        try:
            l, o, r, u = (int(v) for v in (value or [])[:4])
        except (TypeError, ValueError):
            return self._scan_report("Eine Region braucht vier ganze Zahlen.", "err")
        region = normalize_region(l, o, r, u)
        if region[2] - region[0] < MIN_REGION or region[3] - region[1] < MIN_REGION:
            return self._scan_report(
                f"Zu klein — mindestens {MIN_REGION}×{MIN_REGION} Pixel.", "warn")
        self._remember(f"{who}: Region")
        cfg.scan_region = region
        return self._scan_changed(
            f"Region {region[2] - region[0]}×{region[3] - region[1]} "
            f"ab ({region[0]}, {region[1]}).")

    @staticmethod
    def _integer(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _decimal(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _file_gone(self, path: Path, who: str) -> dict:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return self._scan_report(f"{who} entfernt, die Datei blieb liegen.", "warn")
        # Der eigene Schreibvorgang zählt nicht als Fremdänderung — Löschen
        # dreht die Änderungszeit des Ordners genauso weiter wie Schreiben.
        self._disk_track(path.parent)
        return self._scan_report(f"{who} gelöscht.", "warn")

    # ------------------------------------------------------------ Werkzeuge

    def region_mode(self, data: Optional[dict] = None) -> dict:
        """Schaltet das Region- bzw. Aktionspunkt-Werkzeug scharf.

        Dieselbe Geste setzt je nach Scan-Art eine andere Region, und die Art ist
        Oberflächenzustand — deshalb sagt der Befehl, worauf er wirkt, und gemerkt
        wird es nur, solange das Werkzeug an ist. Rückweg ist wie überall die
        markierte Kachel selbst.
        """
        self._scan_load()
        data = data or {}
        mode = str(data.get("mode") or MODE_REGION)
        if mode not in (MODE_REGION, MODE_ACTION, MODE_CHOICE):
            return self._scan_report(f"Unbekannter Modus '{mode}'.", "err")
        kind = str(data.get("kind") or "")
        if mode == MODE_CHOICE or (mode == self.scan_mode and self._region_target):
            self.scan_mode, self._region_target, self._corner = MODE_CHOICE, None, None
            return self._scan_report("Zurück zum Auswählen.", "info")
        locked = self._scan_requirement({"kind": kind})
        if locked is not None:
            return locked
        target = self._target_check(kind)
        if target is None:
            return self._scan_report(
                "Erst ein Item wählen bzw. einen Boss- oder Icon-Scan öffnen.",
                "warn")
        if not self._canvas_area():
            return self._scan_report("Erst einen Screenshot aufnehmen.", "warn")
        self.scan_mode, self._region_target, self._corner = mode, target, None
        if mode == MODE_REGION:
            return self._scan_report(
                "Region: zwei Ecken anklicken — eng um das, was erkannt werden "
                "soll.  ·  ESC oder nochmal die Kachel = zurück", "info")
        if target[0] == "item":
            return self._scan_report(
                f"Bestätigungsklick für '{target[1]}': die Stelle anklicken, die "
                "nach dem Item-Klick bestätigt.  ·  ESC = zurück", "info")
        return self._scan_report(
            "Klickpunkt: die Stelle anklicken, die bei einem Treffer geklickt "
            "wird.  ·  ESC oder nochmal die Kachel = zurück", "info")

    def _target_check(self, kind: str) -> Optional[tuple]:
        if kind == "boss" and self.boss_open in self.boss_scans:
            return ("boss", self.boss_open)
        if kind == "icon" and self.icon_open in self.icon_scans:
            return ("icon", self.icon_open)
        # **Der Bestätigungsklick eines Items ist dieselbe Geste.** Eine Stelle
        # zieht man im Bild, statt zwei Zahlen zu tippen — dafür gibt es das
        # Werkzeug schon, es kannte nur Boss und Icon. Ein zweites daneben wäre
        # dieselbe Frage mit einer zweiten Antwort.
        if kind == "item" and self.scan_kind == KIND_ITEM and self.scan_name in self.items:
            return ("item", self.scan_name)
        return None

    def _region_object(self):
        """Die Konfiguration, auf die das aktive Werkzeug wirkt."""
        if not self._region_target:
            return None
        kind, name = self._region_target
        if kind == "item":
            return self.items.get(name)
        return (self.boss_scans if kind == "boss" else self.icon_scans).get(name)

    def _click_region(self, x: int, y: int) -> dict:
        """Zwei Ecken ergeben die Scan-Region — dieselbe Geste wie beim Slot."""
        cfg = self._region_object()
        if cfg is None:
            self.scan_mode = MODE_CHOICE
            return self._scan_report("Kein Ziel für die Region.", "warn")
        if self._corner is None:
            self._corner = (x, y)
            return self._scan_report("Erste Ecke gesetzt — zweite Ecke anklicken.", "info")
        first, self._corner = self._corner, None
        answer = self._region_set(cfg, [first[0], first[1], x, y],
                                      f"'{cfg.name}'")
        # **Ein zu kleines Rechteck laesst das Werkzeug an.** Sonst muesste man
        # nach jedem Verklicken erst wieder die Kachel suchen — und genau dieses
        # Verklicken ist der Grund, warum es zwei Klicks und kein Ziehen sind.
        if answer["status"]["kind"] in ("warn", "err"):
            return answer
        self._tool_done()
        # Nochmal melden: die Antwort von oben traegt den Modus von VOR dem
        # Aufraeumen, und die Werkzeugleiste liest ihn aus der Momentaufnahme.
        return self._scan_report(answer["status"]["text"])

    def _click_action(self, x: int, y: int) -> dict:
        """Setzt den Klickpunkt der Aktion — über einen Punkt, nie über Zahlen.

        **Wer im Editor eine Stelle erzeugt, legt einen Punkt an.** Ein
        vorhandener an derselben Stelle wird wiederverwendet
        (`point_at_position()` — die eine Regel dafür); sonst wäre derselbe Knopf
        zweimal in der Punktliste und beim Nachjustieren wanderte die Hälfte.
        """
        cfg = self._region_object()
        if cfg is None:
            self.scan_mode = MODE_CHOICE
            return self._scan_report("Kein Ziel für den Klickpunkt.", "warn")
        obj = cfg
        if self._region_target[0] == "boss":
            obj = self._boss_selected()
            if obj is None:
                return self._scan_report(
                    "Erst einen Boss wählen — der Klickpunkt gehört ihm, nicht dem Scan.",
                    "warn")
        color = self._photo_color(x, y)
        point = self._point_for_action(x, y, color, obj.name)
        # Beim Item heisst dasselbe Werkzeug etwas anderes: nicht „wohin geklickt
        # wird, wenn erkannt", sondern „was danach bestätigt wird". Zwei Felder,
        # zwei Wörter — sonst liest man im Item die Boss-Bedeutung mit.
        if self._region_target[0] == "item":
            self._remember(f"'{obj.name}': Bestätigungsklick")
            obj.confirm_point_id = point.id
            self._confirmation_apply(obj)
            self._scan_dirty = True
            self._tool_done()
            return self._scan_report(
                f"Punkt #{point.id} bestätigt den Klick auf '{obj.name}'.")
        self._remember(f"'{obj.name}': Klickpunkt")
        obj.action_point_id = point.id
        self._action_point_apply(obj)
        self._scan_dirty = True
        self._tool_done()
        return self._scan_report(
            f"Punkt #{point.id} als Klickpunkt von '{obj.name}' gesetzt.")

    def _point_for_action(self, x: int, y: int, color, name: str):
        """Der Punkt an dieser Stelle — vorhandener oder neuer."""
        from ...persistence.sequences import point_at_position
        from .model import PalettePoint
        point = point_at_position(self.points, x, y, color)
        if point is None:
            point = PalettePoint(
                id=max([p.id for p in self.points], default=0) + 1,
                x=x, y=y, name=name or "Scan-Aktion",
                color=tuple(color) if color else None,
                source="Scans-Reiter")
            self.points.append(point)
        return point

    def template_capture(self, data: Optional[dict] = None) -> dict:
        """Lernt die Region als Template — der Griff, der heute den ganzen Ablauf kostet.

        Eine Vorlage neu aufzunehmen war bisher nur über einen kompletten
        Durchlauf des Konsolen-Editors möglich. Es ist aber genau das, was man
        nach einem Spiel-Update als Erstes tut.
        """
        self._scan_load()
        data = data or {}
        obj, cfg = self._detection_target(data)
        if obj is None:
            return self._scan_report("Kein Boss bzw. Icon-Scan gewählt.", "warn")
        crop = self._photo_crop(tuple(cfg.scan_region))
        if crop is None:
            return self._scan_report(
                "Die Region liegt ausserhalb des Bildes — erst neu aufnehmen.", "warn")
        from .scan_model import save_template
        file_name = save_template(crop, obj.name,
                                  template_dir=self.filepath.parent / "templates")
        if not file_name:
            return self._scan_report("Vorlage konnte nicht geschrieben werden.", "err")
        self._remember(f"'{obj.name}': Vorlage aufgenommen")
        obj.template = file_name
        # Die Vorschau hängt am Dateinamen und der wurde gerade überschrieben.
        self._preview.pop(file_name, None)
        return self._scan_changed(
            f"Vorlage '{file_name}' aufgenommen "
            f"({crop.size[0]}×{crop.size[1]}).")

    def marker_measure(self, data: Optional[dict] = None) -> dict:
        """Misst die auffälligsten Farben der Region als Marker.

        Dieselbe Rechnung wie beim Item-Lernen (`_collect_markers_silent`) —
        eine zweite Fassung „für Bosse" wäre eine zweite Antwort auf dieselbe
        Frage, und die beiden liefen auseinander.
        """
        self._scan_load()
        data = data or {}
        obj, cfg = self._detection_target(data)
        if obj is None:
            return self._scan_report("Kein Boss bzw. Icon-Scan gewählt.", "warn")
        crop = self._photo_crop(tuple(cfg.scan_region))
        if crop is None:
            return self._scan_report(
                "Die Region liegt ausserhalb des Bildes — erst neu aufnehmen.", "warn")
        from ..item_editor.markers import _collect_markers_silent
        colors = _collect_markers_silent(crop)
        if not colors:
            return self._scan_report("Keine Farben gefunden.", "warn")
        self._remember(f"'{obj.name}': Marker gemessen")
        obj.marker_colors = colors
        return self._scan_changed(
            f"{len(colors)} Marker-Farbe(n) aus der Region gemessen.")

    def _detection_target(self, data: dict):
        """(Profil, Scan-Konfiguration) für Vorlage/Marker/Test.

        Beim Icon ist beides dasselbe Objekt, beim Boss nicht: die Region gehört
        dem Scan, Vorlage und Marker gehören dem einzelnen Boss.
        """
        kind = str(data.get("kind") or "")
        if kind == "icon":
            cfg = self.icon_scans.get(str(data.get("name") or self.icon_open))
            return cfg, cfg
        cfg = self.boss_scans.get(self.boss_open)
        if cfg is None:
            return None, None
        boss = self._boss_find(str(data.get("name") or self.boss_choice),
                                 bool(data.get("global", self.boss_choice_global)))
        return boss, cfg

    # ---------------------------------------------------------------- Tests

    def boss_test(self, data: Optional[dict] = None) -> dict:
        """Hält den gewählten Boss gegen das eingefrorene Bild.

        **Folgenlos.** Erkennen, anzeigen, die Aktion nur benennen — sie wird
        nie ausgeführt.
        """
        self._scan_load()
        boss, cfg = self._detection_target(data or {})
        if boss is None or cfg is None:
            return self._scan_report("Kein Boss gewählt.", "warn")
        result = self._profile_check(boss, cfg.scan_region, cfg.color_tolerance)
        result["action"] = self._action_text(boss)
        self._boss_test_result = result
        self._boss_test_results[boss.name] = result
        return self._scan_report(
            (f"'{boss.name}' erkannt ({result['reason']})." if result["ok"]
             else f"'{boss.name}' nicht erkannt: {result['reason']}."),
            "ok" if result["ok"] else "warn")

    def boss_test_all(self, data: Optional[dict] = None) -> dict:
        """Hält jeden Boss des Scans gegen dieses Bild — lokal plus Bibliothek.

        Getestet wird die **gemergte** Liste, denn genau die sieht der Lauf
        (`execute_boss_scan` merged lokal + global, lokale gewinnen bei
        Namensgleichheit). Nur die lokalen zu prüfen hiesse, die Hälfte der
        Erkennung zu verschweigen.
        """
        self._scan_load()
        cfg = self.boss_scans.get(self.boss_open)
        if cfg is None:
            return self._scan_report("Kein Boss-Scan offen.", "warn")
        bosses = self._merged_bosses(cfg)
        if not bosses:
            return self._scan_report("Dieser Scan kennt noch keinen Boss.", "info")
        self._boss_test_results = {}
        for boss in bosses:
            result = self._profile_check(boss, cfg.scan_region, cfg.color_tolerance)
            result["action"] = self._action_text(boss)
            self._boss_test_results[boss.name] = result
        match = [n for n, e in self._boss_test_results.items() if e["ok"]]
        # Die Reihenfolge IST die Priorität: der erste Treffer gewinnt im Lauf.
        self._boss_test_result = self._boss_test_results[match[0]] if match else None
        return self._scan_report(
            (f"{match[0]} würde erkannt ({len(match)} von {len(bosses)} passen)."
             if match else f"Keiner von {len(bosses)} Bossen passt auf dieses Bild."),
            "ok" if match else "warn")

    def _merged_bosses(self, cfg: BossScanConfig) -> list:
        """Lokale Bosse plus Bibliothek — lokale gewinnen bei Namensgleichheit."""
        names = {b.name for b in cfg.bosses}
        return list(cfg.bosses) + [b for b in self.global_bosses if b.name not in names]

    def icon_test(self, data: Optional[dict] = None) -> dict:
        """Hält den offenen Icon-Scan gegen das Bild — samt Vorschlag, was hilft.

        **Der Vorschlag ist der Kern.** Ein Test, der nur „fehlgeschlagen" sagt,
        lässt einen genau dort stehen, wo man vorher war; einer, der die
        Toleranz nennt, bei der es klappt, ist ein Klick von der Lösung
        entfernt.
        """
        self._scan_load()
        cfg = self.icon_scans.get(str((data or {}).get("name") or self.icon_open))
        if cfg is None:
            return self._scan_report("Kein Icon-Scan gewählt.", "warn")
        result = self._profile_check(cfg, cfg.scan_region, cfg.color_tolerance)
        result["action"] = self._action_text(cfg)
        if not result["ok"] and cfg.marker_colors:
            result["proposal"] = self._tolerance_proposal(cfg)
        self._icon_test_result = result
        return self._scan_report(
            (f"Icon erkannt ({result['reason']})." if result["ok"]
             else f"Icon nicht erkannt: {result['reason']}."),
            "ok" if result["ok"] else "warn")

    def _profile_check(self, profile, region, tolerance: int) -> dict:
        """Ein Profil gegen die Region halten — mit der Rechnung der Laufzeit."""
        crop = self._photo_crop(tuple(region))
        if crop is None:
            return self._test_result(profile, False, "Region liegt ausserhalb des Bildes")
        if profile.template and not self._has_opencv():
            return self._test_result(profile, False, "braucht Template — OpenCV fehlt")
        if not profile.template and not profile.marker_colors:
            return self._test_result(profile, False, "weder Vorlage noch Marker gesetzt")

        from ...config import CONFIG
        from ...runtime.item_scan import _check_profile_match
        from .scan_learning import _ConfigOnly
        begin = time.perf_counter()
        ok, value = _check_profile_match(profile, crop, tolerance, _ConfigOnly(CONFIG),
                                        False, return_score=True,
                                        template_root=self.filepath.parent / "templates")
        duration = (time.perf_counter() - begin) * 1000
        found, total, needed = self._marker_count(profile, crop, tolerance)
        if profile.template:
            reason = (f"Template {value:.0%}" if ok
                     else f"Template {value:.0%} (nötig {profile.min_confidence:.0%})")
        else:
            reason = (f"{found} von {total} Markern" if ok
                     else f"{found} von {total} Markern · nötig {needed}")
        result = self._test_result(profile, ok, reason)
        result.update({"confidence": round(value, 4), "duration": round(duration),
                         "marker_found": found, "marker_total": total,
                         "marker_required": needed, "tolerance": tolerance,
                         "method": "Template" if profile.template else "Marker"})
        return result

    @staticmethod
    def _test_result(profile, ok: bool, reason: str) -> dict:
        return {"name": profile.name, "ok": ok, "reason": reason, "method": None,
                "confidence": None, "duration": 0, "marker_found": 0,
                "marker_total": len(profile.marker_colors), "marker_required": 0,
                "tolerance": 0, "action": "", "proposal": None}

    @staticmethod
    def _marker_count(profile, crop, tolerance: int) -> tuple:
        """(gefunden, gesamt, nötig) — dieselben Regeln wie `_check_profile_match`."""
        if not profile.marker_colors:
            return 0, 0, 0
        from ...config import CONFIG
        from ...imaging import find_color_in_image
        total = len(profile.marker_colors)
        found = sum(1 for color in profile.marker_colors
                       if find_color_in_image(crop, color, tolerance,
                                              min_pixels=CONFIG.scan_marker_min_pixels))
        needed = total if CONFIG.scan_require_all_markers else min(
            total, CONFIG.scan_min_markers_required)
        return found, total, needed

    def _tolerance_proposal(self, cfg) -> Optional[dict]:
        """Die kleinste Toleranz, bei der genug Marker gefunden würden.

        Gesucht wird von der aktuellen aufwärts und in Schritten: eine Toleranz
        pixelgenau zu bestimmen wäre eine Genauigkeit, die die Zahl gar nicht
        hat — und jeder Schritt kostet einen Durchgang durch das Bild.
        """
        crop = self._photo_crop(tuple(cfg.scan_region))
        if crop is None:
            return None
        for tolerance in range(cfg.color_tolerance + 4, 121, 4):
            found, total, needed = self._marker_count(cfg, crop, tolerance)
            if total and found >= needed:
                return {"field": "tolerance", "value": tolerance,
                        "text": f"Toleranz auf {tolerance} setzen"}
        return None

    def _action_text(self, obj) -> str:
        """Was bei einem Treffer passieren WÜRDE — als Satz, nicht als Tat."""
        action = obj.action
        delay = getattr(obj, "action_delay", 0) or 0
        suffix_text = f" nach {delay:g} s" if delay else ""
        if action == BOSS_ACTION_SCAN:
            return f"Item-Scan „{getattr(obj, 'action_scan', None) or '—'}“{suffix_text}"
        if action == BOSS_ACTION_CLICK:
            point = next((p for p in self.points
                          if p.id == obj.action_point_id), None)
            where_to = (f"Punkt #{point.id} ({point.name})" if point
                     else "Punkt fehlt — nichts würde geklickt")
            return f"{where_to} klicken{suffix_text}"
        if action == BOSS_ACTION_KEY:
            return f"Taste „{obj.action_key or '—'}“{suffix_text}"
        return ACTION_TEXT.get(action, action) + suffix_text

    def ocr_check(self, data: Optional[dict] = None) -> dict:
        """Ist überhaupt ein OCR-Backend installiert?

        Auf Knopfdruck und nicht bei jeder Momentaufnahme: `autoclicker.ocr`
        importiert EasyOCR beim Laden, und das zieht Torch nach — Sekunden, in
        denen der Reiter stünde. Danach ist das Modul geladen und die Antwort
        kostet nichts mehr; gemerkt wird sie trotzdem, damit die Anzeige nicht
        vom Zufall abhängt.
        """
        from ...config import CONFIG
        begin = time.perf_counter()
        try:
            from ... import ocr
            backends = ocr.available_backends()
        except ImportError as error:
            self._ocr_state = {"present": False, "backends": [], "reason": str(error)}
            return self._scan_report(f"OCR nicht verfügbar: {error}", "warn")
        self._ocr_state = {
            "present": bool(backends), "backends": backends, "reason": "",
            "duration": round((time.perf_counter() - begin) * 1000),
        }
        if not backends:
            return self._scan_report(
                "Kein OCR-Backend installiert: pip install easyocr "
                "(oder pytesseract).", "warn")
        return self._scan_report(
            f"OCR bereit: {', '.join(backends)} "
            f"(eingestellt: {CONFIG.ocr_backend or 'automatisch'}).")

    def llm_check(self, data: Optional[dict] = None) -> dict:
        """Antwortet der LLM-Endpunkt überhaupt?

        Eine Lampe, die „nicht erreichbar" sagt, spart die halbe Stunde, in der
        man sonst die Prompts verdächtigt. Gefragt wird nur auf Knopfdruck: eine
        Momentaufnahme darf nicht auf ein Netzwerk warten.
        """
        from ...config import CONFIG
        from ...llm_vision import chat_endpoint, test_connection

        begin = time.perf_counter()
        # **Gefragt wird ueber `test_connection()`, nicht mit einem rohen
        # `urlopen`.** Zwei Fehler hingen daran: der Endpunkt ist im Normalfall
        # `None` (dann gilt der Standard-Port des Anbieters) — `urlopen(None)`
        # warf einen `AttributeError`, und die Lampe meldete „nicht
        # erreichbar: 'NoneType' object has no attribute 'timeout'" bei einem
        # laufenden Server. Und selbst wenn jemand antwortete, sagte das nichts
        # darueber, ob das EINGESTELLTE Modell geladen ist; genau daran
        # scheitert danach jeder Aufruf.
        reachable, message = test_connection(
            CONFIG.llm_provider, CONFIG.llm_endpoint, CONFIG.llm_model)
        self._llm_state = {
            "reachable": reachable, "reason": "" if reachable else message,
            "endpoint": CONFIG.llm_endpoint or chat_endpoint(CONFIG.llm_provider),
            "duration": round((time.perf_counter() - begin) * 1000),
        }
        return self._scan_report(
            f"{message} ({self._llm_state['duration']} ms)",
            "ok" if reachable else "warn")

    # ------------------------------------------------------------- Speichern

    def _detection_save(self) -> list:
        """Schreibt Boss-Scans, Icon-Scans und die Bibliothek. Fehler als Liste."""
        from ...persistence import save_boss_scan, save_global_bosses, save_icon_scan
        error = []
        for cfg in self.boss_scans.values():
            try:
                cfg.owner_sequence = self.board.name
                if not save_boss_scan(cfg):
                    error.append(f"boss_scans/{cfg.name}.json")
            except (OSError, ValueError):
                error.append(f"boss_scans/{cfg.name}.json")
        for cfg in self.icon_scans.values():
            try:
                cfg.owner_sequence = self.board.name
                if not save_icon_scan(cfg):
                    error.append(f"icon_scans/{cfg.name}.json")
            except (OSError, ValueError):
                error.append(f"icon_scans/{cfg.name}.json")
        try:
            if not save_global_bosses(_LibraryState(self.global_bosses), self.board.name):
                error.append("boss_scans/bibliothek.json")
        except OSError:
            error.append("boss_scans/bibliothek.json")
        return error
