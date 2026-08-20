"""Boss- und Icon-Scans im Scans-Reiter: Region, Erkennung, Aktion, Test.

**Warum das hier liegt und nicht in der Konsole.** Boss- und Icon-Scans waren
nur über `boss_scan_editor.py` / `icon_scan_editor.py` erreichbar: man klickte
sich linear durch Schritt 1–6, und für jede spätere Änderung — eine Konfidenz,
eine andere Aktion — lief derselbe Ablauf noch einmal von vorn. Die Sache, um
die es geht, ist aber ein Rechteck auf einem Bild; sie gehört dorthin, wo das
Bild steht.

Zwei Regeln tragen das Modul:

- **Der Assistent ist der Weg beim ersten Einrichten, die Eigenschaften-Spalte
  der Weg für jede spätere Änderung.** Jedes Feld ist einzeln setzbar
  (`boss_setzen`, `icon_setzen`), keins nur über einen Durchlauf erreichbar.
- **Testen ist folgenlos.** `boss_testen`/`icon_testen` erkennen, zeigen und
  *benennen* die Aktion — ausgeführt wird sie nie. Ein Testknopf, der klickt,
  ist im Editor eines Autoclickers die schlechteste denkbare Überraschung.

Gerechnet wird mit `_check_profile_match()` aus `runtime/item_scan.py` — genau
der Funktion, die im Lauf entscheidet. Eine zweite Rechnung „nur für die
Vorschau" wäre eine Vorschau, die etwas anderes zeigt als das, was passiert.
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
from ...utils import eindeutiger_name, sanitize_filename
from .model import hexfarbe, rgbwert
from .scan_contract import (
    MIN_REGION,
    MODUS_AKTION,
    MODUS_REGION,
    MODUS_WAHL,
)
from .scan_model import normalize_region

# **Die Kacheln kommen aus `models.py`, nicht aus dem JavaScript.** Die Ansicht
# soll keine Aktionswerte erfinden — ein getipptes "skipcycle" wäre ein Wert, den
# `__post_init__` beim Speichern still auf den Standard hebt, und der Klick sähe
# aus, als hätte er gewirkt. Hier steht nur die REIHENFOLGE (die Menge prüft ein
# Test gegen `VALID_*_ACTIONS`); die Beschriftung kommt aus `ACTION_TEXT`.
_BOSS_AKTIONEN = (BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY,
                  BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART)
_ICON_AKTIONEN = tuple(a for a in _BOSS_AKTIONEN if a != BOSS_ACTION_SCAN)
# **Die Kachel traegt ein Schlagwort, der Tooltip den Satz.** `ACTION_TEXT` ist
# fuer Prosa gemacht („Punkt klicken", „Zyklus abbrechen") und steht so in
# Meldungen und im Laufstatus; auf einer 9,5-px-Kachel in einem Sechser-Raster
# ist derselbe Satz zweizeilig und unlesbar. Zwei Verwendungen, zwei Laengen —
# ein Test haelt beide Tabellen auf denselben Schluesseln.
_AKTION_KURZ = {
    BOSS_ACTION_SCAN: "ITEM-SCAN",
    BOSS_ACTION_CLICK: "KLICK",
    BOSS_ACTION_KEY: "TASTE",
    BOSS_ACTION_SKIP: "SKIP",
    BOSS_ACTION_SKIP_CYCLE: "SKIP CYCLE",
    BOSS_ACTION_RESTART: "RESTART",
}
_SCAN_MODI_TEXT = (
    (SCAN_MODE_ALL, "bestes pro Kategorie"),
    (SCAN_MODE_BEST, "nur bestes"),
    (SCAN_MODE_EVERY, "alle Treffer"),
)

# Wie lange ein Erreichbarkeitstest des LLM-Endpunkts warten darf. Kurz: die
# Frage ist „antwortet da überhaupt jemand", nicht „was sagt das Modell".
_LLM_PROBE_TIMEOUT = 4


class _BibliothekState:
    """Ein `AutoClickerState`-Stellvertreter für die Boss-Bibliothek.

    `save_global_bosses()`/`load_global_bosses()` nehmen einen State, benutzen
    davon aber nur `lock` und `global_bosses`. Diesen Prozess einen echten State
    bauen zu lassen hiesse, den halben Hauptprozess mitzuziehen — für eine
    Liste. Dieselbe Entscheidung wie bei `_NurConfig` in `scan_learning.py`.
    """

    def __init__(self, bosse=None):
        self.lock = threading.Lock()
        self.global_bosses = list(bosse or [])


class ScanDetectMixin:
    """Boss- und Icon-Scans: Bestand, Bearbeitung, Test."""

    # ------------------------------------------------------------- Zustand

    def _erkennung_init(self) -> None:
        """Wird aus `_scan_init()` gerufen."""
        self.boss_scans: dict = {}
        self.icon_scans: dict = {}
        self.global_bosses: list = []
        # Der offene Scan ist der Zusammenhang, die Wahl das bearbeitete Ding —
        # dieselbe Trennung wie `scan_offen` neben `scan_name` bei den Items.
        self.boss_offen: str = ""
        self.boss_wahl: str = ""
        self.boss_wahl_global: bool = False
        self.icon_offen: str = ""
        # Worauf das Region- bzw. Aktions-Werkzeug wirkt: ("boss"|"icon", Name).
        # Der Modus allein reicht nicht — dieselbe Geste setzt je nach Art eine
        # andere Region, und die Scan-Art selbst ist Oberflächenzustand.
        self._region_ziel: Optional[tuple] = None
        self._boss_test: Optional[dict] = None
        self._boss_tests: dict = {}
        self._icon_test: Optional[dict] = None
        # Ergebnis des letzten Erreichbarkeitstests: None = nie gefragt. Für
        # beide gilt dasselbe — die Antwort kostet (Netz bzw. ein schwerer
        # Import) und gehört deshalb nicht in jede Momentaufnahme.
        self._llm_stand: Optional[dict] = None
        self._ocr_stand: Optional[dict] = None

    def _erkennung_laden(self) -> None:
        """Boss-Scans, Icon-Scans und die Bibliothek von Platte.

        Läuft aus `_scan_laden()` mit, also einmal je Sitzung und danach nur
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
        for name, pfad in list_available_boss_scans():
            cfg = load_boss_scan_file(pfad)
            if cfg is not None:
                self.boss_scans[cfg.name or name] = cfg
        self.icon_scans = {}
        for name, pfad in list_available_icon_scans():
            cfg = load_icon_scan_file(pfad)
            if cfg is not None:
                self.icon_scans[cfg.name or name] = cfg
        stellvertreter = _BibliothekState()
        load_global_bosses(stellvertreter)
        self.global_bosses = stellvertreter.global_bosses
        if self.boss_offen not in self.boss_scans:
            self.boss_offen = next(iter(self.boss_scans), "")
        if self.icon_offen not in self.icon_scans:
            self.icon_offen = next(iter(self.icon_scans), "")
        self.boss_wahl, self.boss_wahl_global = "", False

    @staticmethod
    def _erkennung_pfade() -> list:
        """Was der Reiter an Boss-/Icon-Dateien liest — für den Fremd-Vergleich.

        Der Hauptprozess schreibt dieselben Dateien: der Konsolen-Editor bleibt
        als zweiter Weg bestehen, und ein Boss, den ein Lauf per LLM entdeckt
        hat, landet in der Bibliothek. Ohne diese Pfade meldete der Reiter „auf
        Platte hat sich etwas geändert" nur für Items — also ausgerechnet nicht
        für das, was hier gerade bearbeitet wird.
        """
        from ...persistence.paths import BOSS_SCANS_DIR, ICON_SCANS_DIR
        pfade = [Path(BOSS_SCANS_DIR), Path(ICON_SCANS_DIR),
                 Path(BOSS_SCANS_DIR) / "global" / "bosses.json"]
        for ordner in (BOSS_SCANS_DIR, ICON_SCANS_DIR):
            if Path(ordner).is_dir():
                pfade += sorted(Path(ordner).glob("*.json"))
        return pfade

    def _erkennung_zustand(self) -> dict:
        """Der Teil des Rückgängig-Abzugs, der diesem Modul gehört."""
        import copy
        return {
            "boss_scans": copy.deepcopy(self.boss_scans),
            "icon_scans": copy.deepcopy(self.icon_scans),
            "global_bosses": copy.deepcopy(self.global_bosses),
            "boss_offen": self.boss_offen,
            "boss_wahl": self.boss_wahl,
            "boss_wahl_global": self.boss_wahl_global,
            "icon_offen": self.icon_offen,
        }

    def _erkennung_zurueck(self, stand: dict) -> None:
        self.boss_scans = stand.get("boss_scans", {})
        self.icon_scans = stand.get("icon_scans", {})
        self.global_bosses = stand.get("global_bosses", [])
        self.boss_offen = stand.get("boss_offen", "")
        self.boss_wahl = stand.get("boss_wahl", "")
        self.boss_wahl_global = stand.get("boss_wahl_global", False)
        self.icon_offen = stand.get("icon_offen", "")
        # Ein Testergebnis gehört zu dem Stand, in dem es gemessen wurde.
        self._boss_test = self._icon_test = None
        self._boss_tests = {}

    # ------------------------------------------------------- Momentaufnahme

    def _erkennung_json(self) -> dict:
        """Was der Reiter über Boss- und Icon-Scans zu wissen braucht."""
        return {
            "boss_scans": [self._boss_scan_json(c) for c in self.boss_scans.values()],
            "icon_scans": [self._icon_scan_json(c) for c in self.icon_scans.values()],
            "global_bosses": [self._boss_json(b, True) for b in self.global_bosses],
            "boss": {
                "offen": self.boss_offen,
                "wahl": self.boss_wahl,
                "wahl_global": self.boss_wahl_global,
                "test": self._boss_test,
                "tests": self._boss_tests,
            },
            "icon": {"offen": self.icon_offen, "test": self._icon_test},
            "region_ziel": (list(self._region_ziel) if self._region_ziel else None),
            # Was die Aktionen brauchen: die Punkte kennt die Sequenz-Seite der
            # Brücke, die Item-Scan-Namen der Item-Teil. Beides steht hier
            # nochmal, weil der Reiter sonst zwei Kanäle bräuchte.
            "punkte": [{"id": p.id, "name": p.name or f"Punkt {p.id}",
                        "x": p.x, "y": p.y} for p in self.points],
            "item_scan_namen": sorted(self.scans, key=str.casefold),
            "aktionen": {
                "boss": [{"wert": a, "text": ACTION_TEXT[a], "kurz": _AKTION_KURZ[a]}
                         for a in _BOSS_AKTIONEN],
                "icon": [{"wert": a, "text": ACTION_TEXT[a], "kurz": _AKTION_KURZ[a]}
                         for a in _ICON_AKTIONEN],
                "scan_modi": [{"wert": w, "text": t} for w, t in _SCAN_MODI_TEXT],
            },
            "bereit": self._bereit(),
        }

    def _boss_scan_json(self, cfg: BossScanConfig) -> dict:
        return {
            "name": cfg.name,
            "region": list(cfg.scan_region),
            "toleranz": cfg.color_tolerance,
            "default_action": cfg.default_action,
            "default_scan": cfg.default_scan,
            "use_llm": bool(cfg.use_llm),
            "llm_fallback": bool(cfg.llm_fallback),
            "use_ocr": bool(cfg.use_ocr),
            "ocr_fallback": bool(cfg.ocr_fallback),
            "bosse": [self._boss_json(b, False) for b in cfg.bosses],
        }

    def _boss_json(self, b: BossProfile, aus_bibliothek: bool) -> dict:
        return {
            "name": b.name,
            "global": aus_bibliothek,
            "template": b.template,
            "vorschau": self._template_url(b.template) if b.template else "",
            "konfidenz": b.min_confidence,
            "marker": [hexfarbe(c) for c in b.marker_colors],
            "aktion": b.action,
            "scan": b.action_scan,
            "scan_modus": b.action_scan_mode,
            "punkt_id": b.action_point_id,
            "taste": b.action_key,
            "verzoegerung": b.action_delay,
            # Ein Profil ohne Template UND ohne Marker wird nie per Bild
            # erkannt — nur noch per OCR/LLM. Das ist keine Warnung, sondern
            # eine Auskunft: der Reiter sagt daneben, ob OCR überhaupt an ist.
            "erkennung": ("template" if b.template
                          else ("marker" if b.marker_colors else "keine")),
        }

    def _icon_scan_json(self, cfg: IconScanConfig) -> dict:
        offen = cfg.name == self.icon_offen
        return {
            "name": cfg.name,
            "region": list(cfg.scan_region),
            "template": cfg.template,
            "vorschau": self._template_url(cfg.template) if cfg.template else "",
            "konfidenz": cfg.min_confidence,
            "marker": [hexfarbe(c) for c in cfg.marker_colors],
            "toleranz": cfg.color_tolerance,
            "aktion": cfg.action,
            "punkt_id": cfg.action_point_id,
            "taste": cfg.action_key,
            "verzoegerung": cfg.action_delay,
            "erkennung": ("template" if cfg.template
                          else ("marker" if cfg.marker_colors else "keine")),
            # **Der Ausschnitt zeigt, was der Scan sieht.** Nur für den offenen:
            # bei zwanzig Icon-Scans wären das zwanzig Bilder in jeder
            # Momentaufnahme, und neunzehn davon sieht niemand an.
            "ausschnitt": self._region_bild(cfg.scan_region) if offen else "",
        }

    def _region_bild(self, region) -> str:
        """Der Bildausschnitt einer Region als data:-URL — leer ohne Bild."""
        crop = self._foto_crop(tuple(region))
        if crop is None:
            return ""
        from .scan_capture import _als_datenurl
        return _als_datenurl(crop)

    def _bereit(self) -> dict:
        """Welche Erkennungswege überhaupt zur Verfügung stehen.

        **Fehlende Voraussetzungen blenden nichts aus, sie erklären sich.** Ohne
        OpenCV ist Template-Erkennung aus — Farb-Marker, OCR und LLM gehen
        trotzdem. Der Reiter setzt die betroffene Wahl auf inaktiv und nennt den
        pip-Befehl; ein verstecktes Bedienelement liesse den Nutzer suchen.

        **Was etwas kostet, wird gefragt und nicht mitgeliefert.** OCR und LLM
        stehen deshalb als `None`, bis jemand `ocr_pruefen()` bzw.
        `llm_pruefen()` drückt: `import easyocr` zieht Torch nach und dauert
        Sekunden — in einer Momentaufnahme, die nach jedem Klick neu entsteht,
        hat das nichts verloren. Dieselbe Entscheidung wie beim LLM, nur dass
        dort das Netz wartet statt der Import.
        """
        from ...config import CONFIG
        return {
            "opencv": self._hat_opencv(),
            "pillow": self._hat_pillow(),
            "ocr_stand": self._ocr_stand,
            "ocr_an": bool(CONFIG.ocr_enabled),
            "ocr_backend": CONFIG.ocr_backend or "automatisch",
            "ocr_sprachen": list(CONFIG.ocr_languages or []),
            "ocr_min": CONFIG.ocr_min_confidence,
            "llm_an": bool(CONFIG.llm_enabled),
            "llm_endpunkt": CONFIG.llm_endpoint,
            "llm_modell": CONFIG.llm_model or "",
            "llm_stand": self._llm_stand,
            "boss_learn_global": bool(CONFIG.boss_learn_global),
            "marker_alle": bool(CONFIG.scan_require_all_markers),
            "marker_noetig": int(CONFIG.scan_min_markers_required),
            "marker_min_pixel": int(CONFIG.scan_marker_min_pixels),
        }

    # ------------------------------------------------------------ Boss-Scans

    def boss_scan_neu(self, daten: Optional[dict] = None) -> dict:
        """Ein neuer Boss-Scan — leer, mit eindeutigem Namen, sofort offen."""
        self._scan_laden()
        name = eindeutiger_name(str((daten or {}).get("name") or "Neuer Boss-Scan"),
                                self.boss_scans)
        self._merke("Boss-Scan angelegt")
        self.boss_scans[name] = BossScanConfig(name=name)
        self.boss_offen, self.boss_wahl = name, ""
        return self._scan_geaendert(
            f"Boss-Scan '{name}' angelegt. Region aufziehen, dann Bosse anlegen.")

    def boss_scan_oeffnen(self, daten: Optional[dict] = None) -> dict:
        """Wählt den Boss-Scan, in dessen Zusammenhang gearbeitet wird."""
        self._scan_laden()
        name = str((daten or {}).get("name") or "")
        if name and name not in self.boss_scans:
            return self._scan_melde(f"Boss-Scan '{name}' gibt es nicht.", "err")
        self.boss_offen, self.boss_wahl, self.boss_wahl_global = name, "", False
        self._boss_test, self._boss_tests = None, {}
        self._region_ziel = None
        if not name:
            return self._scan_melde("Kein Boss-Scan offen.", "info")
        return self._scan_melde(f"Boss-Scan '{name}' geöffnet.")

    def boss_scan_setzen(self, daten: Optional[dict] = None) -> dict:
        """Ein Feld eines Boss-Scans — jedes einzeln, ohne Durchlauf."""
        self._scan_laden()
        daten = daten or {}
        cfg = self.boss_scans.get(str(daten.get("name") or self.boss_offen))
        if cfg is None:
            return self._scan_melde("Kein Boss-Scan gewählt.", "warn")
        feld, wert = str(daten.get("feld") or ""), daten.get("wert")

        if feld == "name":
            return self._erkennung_umbenennen(self.boss_scans, cfg, wert, "Boss-Scan")
        if feld == "region":
            return self._region_setzen(cfg, wert, f"Boss-Scan '{cfg.name}'")
        if feld == "toleranz":
            zahl = self._ganzzahl(wert)
            if zahl is None:
                return self._scan_melde("Die Farb-Toleranz muss eine Zahl sein.", "err")
            self._merke(f"'{cfg.name}': Farb-Toleranz")
            cfg.color_tolerance = max(0, zahl)
            return self._scan_geaendert()
        if feld == "default_action":
            if wert not in VALID_BOSS_ACTIONS:
                return self._scan_melde(f"Unbekannte Aktion '{wert}'.", "err")
            self._merke(f"'{cfg.name}': Fallback-Aktion")
            cfg.default_action = str(wert)
            return self._scan_geaendert(
                f"Ohne erkannten Boss: {ACTION_TEXT.get(cfg.default_action, cfg.default_action)}.")
        if feld == "default_scan":
            self._merke(f"'{cfg.name}': Fallback-Scan")
            cfg.default_scan = str(wert) or None
            return self._scan_geaendert()
        if feld in ("use_llm", "llm_fallback", "use_ocr", "ocr_fallback"):
            self._merke(f"'{cfg.name}': {feld}")
            setattr(cfg, feld, bool(wert))
            return self._scan_geaendert(self._wege_text(cfg), "info")
        return self._scan_melde(f"Unbekanntes Feld '{feld}'.", "err")

    @staticmethod
    def _wege_text(cfg: BossScanConfig) -> str:
        """In welcher Reihenfolge erkannt wird — als ein Satz.

        Bei gleicher Einstellung läuft **OCR vor LLM**: OCR ist lokal und
        schnell, das LLM kostet bis `llm_timeout`. Das steht in
        `runtime/boss_detection.py` genauso — hier wird es nur vorgelesen.
        """
        vorn = [name for name, an, fallback in
                (("OCR", cfg.use_ocr, cfg.ocr_fallback), ("LLM", cfg.use_llm, cfg.llm_fallback))
                if an and not fallback]
        hinten = [name for name, an, fallback in
                  (("OCR", cfg.use_ocr, cfg.ocr_fallback), ("LLM", cfg.use_llm, cfg.llm_fallback))
                  if an and fallback]
        teile = vorn + ["Template/Marker"] + hinten
        return "Reihenfolge: " + " → ".join(teile)

    def boss_scan_loeschen(self, daten: Optional[dict] = None) -> dict:
        """Löscht den offenen Boss-Scan samt Datei."""
        self._scan_laden()
        name = str((daten or {}).get("name") or self.boss_offen)
        if name not in self.boss_scans:
            return self._scan_melde("Kein Boss-Scan gewählt.", "warn")
        self._merke(f"Boss-Scan '{name}' gelöscht")
        del self.boss_scans[name]
        self.boss_offen = next(iter(self.boss_scans), "")
        self.boss_wahl = ""
        from ...persistence.paths import BOSS_SCANS_DIR
        return self._datei_weg(Path(BOSS_SCANS_DIR) / f"{sanitize_filename(name)}.json",
                               f"Boss-Scan '{name}'")

    # ----------------------------------------------------------- Einzelbosse

    def boss_waehlen(self, daten: Optional[dict] = None) -> dict:
        """Wählt einen Boss zum Bearbeiten — lokal oder aus der Bibliothek."""
        self._scan_laden()
        daten = daten or {}
        name = str(daten.get("name") or "")
        aus_bibliothek = bool(daten.get("global"))
        if name and self._boss_finden(name, aus_bibliothek) is None:
            return self._scan_melde(f"Boss '{name}' gibt es nicht.", "err")
        self.boss_wahl, self.boss_wahl_global = name, aus_bibliothek
        self._region_ziel = None
        return self.scan_daten()

    def _boss_finden(self, name: str, aus_bibliothek: bool) -> Optional[BossProfile]:
        if aus_bibliothek:
            return next((b for b in self.global_bosses if b.name == name), None)
        cfg = self.boss_scans.get(self.boss_offen)
        if cfg is None:
            return None
        return next((b for b in cfg.bosses if b.name == name), None)

    def _boss_gewaehlt(self) -> Optional[BossProfile]:
        return (self._boss_finden(self.boss_wahl, self.boss_wahl_global)
                if self.boss_wahl else None)

    def _boss_namen(self) -> list:
        """Alle Namen, die kollidieren könnten — lokal plus Bibliothek.

        Bei Namensgleichheit gewinnt der lokale Boss (so merged
        `execute_boss_scan`). Ein zweiter mit demselben Namen ist deshalb kein
        Fehler, aber eine Falle: der eine verdeckt den anderen, ohne dass man es
        sieht. Der Namensvorschlag geht ihr aus dem Weg.
        """
        cfg = self.boss_scans.get(self.boss_offen)
        namen = [b.name for b in (cfg.bosses if cfg else [])]
        return namen + [b.name for b in self.global_bosses]

    def boss_neu(self, daten: Optional[dict] = None) -> dict:
        """Legt einen Boss an — im offenen Scan oder in der Bibliothek."""
        self._scan_laden()
        daten = daten or {}
        in_bibliothek = bool(daten.get("global"))
        cfg = self.boss_scans.get(self.boss_offen)
        if cfg is None and not in_bibliothek:
            return self._scan_melde("Erst einen Boss-Scan anlegen oder öffnen.", "warn")
        name = eindeutiger_name(str(daten.get("name") or "Neuer Boss"), self._boss_namen())
        self._merke(f"Boss '{name}' angelegt")
        boss = BossProfile(name=name, action=BOSS_ACTION_SKIP)
        if in_bibliothek:
            self.global_bosses.append(boss)
        else:
            cfg.bosses.append(boss)
        self.boss_wahl, self.boss_wahl_global = name, in_bibliothek
        return self._scan_geaendert(
            f"Boss '{name}' angelegt — jetzt Vorlage aufnehmen oder Marker messen.")

    def boss_setzen(self, daten: Optional[dict] = None) -> dict:
        """Ein Feld eines Bosses. Jedes einzeln — das ist der Punkt der Ansicht."""
        self._scan_laden()
        daten = daten or {}
        name = str(daten.get("name") or self.boss_wahl)
        aus_bibliothek = bool(daten.get("global", self.boss_wahl_global))
        boss = self._boss_finden(name, aus_bibliothek)
        if boss is None:
            return self._scan_melde("Kein Boss gewählt.", "warn")
        feld, wert = str(daten.get("feld") or ""), daten.get("wert")

        if feld == "name":
            neu = str(wert or "").strip()
            if not neu or neu == boss.name:
                return self.scan_daten()
            if neu in self._boss_namen():
                return self._scan_melde(f"'{neu}' gibt es schon.", "warn")
            self._merke(f"Boss '{boss.name}' umbenannt")
            boss.name = neu
            self.boss_wahl = neu
            return self._scan_geaendert(f"Boss heisst jetzt '{neu}'.")
        if feld == "aktion":
            if wert not in VALID_BOSS_ACTIONS:
                return self._scan_melde(f"Unbekannte Aktion '{wert}'.", "err")
            self._merke(f"Boss '{boss.name}': Aktion")
            boss.action = str(wert)
            return self._scan_geaendert(
                f"Bei Treffer: {ACTION_TEXT.get(boss.action, boss.action)}.")
        if feld == "scan":
            self._merke(f"Boss '{boss.name}': Item-Scan")
            boss.action_scan = str(wert) or None
            return self._scan_geaendert()
        if feld == "scan_modus":
            if wert not in VALID_SCAN_MODES:
                return self._scan_melde(f"Unbekannter Scan-Modus '{wert}'.", "err")
            self._merke(f"Boss '{boss.name}': Scan-Modus")
            boss.action_scan_mode = str(wert)
            return self._scan_geaendert()
        return self._profil_feld(boss, feld, wert, f"Boss '{boss.name}'")

    def boss_loeschen(self, daten: Optional[dict] = None) -> dict:
        """Entfernt einen Boss aus seinem Scan bzw. aus der Bibliothek."""
        self._scan_laden()
        daten = daten or {}
        name = str(daten.get("name") or self.boss_wahl)
        aus_bibliothek = bool(daten.get("global", self.boss_wahl_global))
        boss = self._boss_finden(name, aus_bibliothek)
        if boss is None:
            return self._scan_melde("Kein Boss gewählt.", "warn")
        self._merke(f"Boss '{name}' gelöscht")
        if aus_bibliothek:
            self.global_bosses = [b for b in self.global_bosses if b is not boss]
        else:
            cfg = self.boss_scans[self.boss_offen]
            cfg.bosses = [b for b in cfg.bosses if b is not boss]
        if self.boss_wahl == name:
            self.boss_wahl = ""
        self._boss_tests.pop(name, None)
        # Das Template bleibt liegen: `items/templates/` teilen sich Items,
        # Bosse und Icons, und eine Datei zu löschen, die einem anderen gehört,
        # ist der stille Datenverlust, den es hier nicht gibt.
        return self._scan_geaendert(f"Boss '{name}' entfernt (Vorlage bleibt liegen).", "warn")

    def boss_global_verschieben(self, daten: Optional[dict] = None) -> dict:
        """Schiebt einen Boss zwischen Scan und Bibliothek hin und her.

        **Die Bibliothek gilt zusätzlich in JEDEM Boss-Scan.** Wer denselben
        Boss in drei Scans braucht, pflegt ihn sonst dreimal — und ändert beim
        vierten Mal nur zwei davon.
        """
        self._scan_laden()
        daten = daten or {}
        name = str(daten.get("name") or self.boss_wahl)
        aus_bibliothek = bool(daten.get("global", self.boss_wahl_global))
        boss = self._boss_finden(name, aus_bibliothek)
        if boss is None:
            return self._scan_melde("Kein Boss gewählt.", "warn")
        cfg = self.boss_scans.get(self.boss_offen)
        if cfg is None and aus_bibliothek:
            return self._scan_melde("Erst einen Boss-Scan öffnen.", "warn")
        self._merke(f"Boss '{name}' verschoben")
        if aus_bibliothek:
            self.global_bosses = [b for b in self.global_bosses if b is not boss]
            cfg.bosses.append(boss)
            self.boss_wahl_global = False
            text = f"'{name}' gilt jetzt nur noch in '{cfg.name}'."
        else:
            cfg.bosses = [b for b in cfg.bosses if b is not boss]
            self.global_bosses.append(boss)
            self.boss_wahl_global = True
            text = f"'{name}' liegt jetzt in der Bibliothek und gilt in jedem Boss-Scan."
        return self._scan_geaendert(text)

    # ------------------------------------------------------------ Icon-Scans

    def icon_scan_neu(self, daten: Optional[dict] = None) -> dict:
        """Ein neuer Icon-Scan — das kleinste Modell: Region, Erkennung, Aktion."""
        self._scan_laden()
        name = eindeutiger_name(str((daten or {}).get("name") or "Neuer Icon-Scan"),
                                self.icon_scans)
        self._merke("Icon-Scan angelegt")
        self.icon_scans[name] = IconScanConfig(name=name)
        self.icon_offen = name
        return self._scan_geaendert(
            f"Icon-Scan '{name}' angelegt. Region eng um das Symbol aufziehen.")

    def icon_scan_oeffnen(self, daten: Optional[dict] = None) -> dict:
        self._scan_laden()
        name = str((daten or {}).get("name") or "")
        if name and name not in self.icon_scans:
            return self._scan_melde(f"Icon-Scan '{name}' gibt es nicht.", "err")
        self.icon_offen = name
        self._icon_test = None
        self._region_ziel = None
        return self._scan_melde(f"Icon-Scan '{name}' geöffnet." if name
                                else "Kein Icon-Scan offen.", "ok" if name else "info")

    def icon_setzen(self, daten: Optional[dict] = None) -> dict:
        """Ein Feld eines Icon-Scans."""
        self._scan_laden()
        daten = daten or {}
        cfg = self.icon_scans.get(str(daten.get("name") or self.icon_offen))
        if cfg is None:
            return self._scan_melde("Kein Icon-Scan gewählt.", "warn")
        feld, wert = str(daten.get("feld") or ""), daten.get("wert")
        if feld == "name":
            return self._erkennung_umbenennen(self.icon_scans, cfg, wert, "Icon-Scan")
        if feld == "region":
            return self._region_setzen(cfg, wert, f"Icon-Scan '{cfg.name}'")
        if feld == "aktion":
            if wert not in VALID_ICON_ACTIONS:
                return self._scan_melde(f"Unbekannte Aktion '{wert}'.", "err")
            self._merke(f"'{cfg.name}': Aktion")
            cfg.action = str(wert)
            return self._scan_geaendert(
                f"Bei Fund: {ACTION_TEXT.get(cfg.action, cfg.action)}.")
        return self._profil_feld(cfg, feld, wert, f"Icon-Scan '{cfg.name}'")

    def icon_scan_loeschen(self, daten: Optional[dict] = None) -> dict:
        self._scan_laden()
        name = str((daten or {}).get("name") or self.icon_offen)
        if name not in self.icon_scans:
            return self._scan_melde("Kein Icon-Scan gewählt.", "warn")
        self._merke(f"Icon-Scan '{name}' gelöscht")
        del self.icon_scans[name]
        self.icon_offen = next(iter(self.icon_scans), "")
        from ...persistence.paths import ICON_SCANS_DIR
        return self._datei_weg(Path(ICON_SCANS_DIR) / f"{sanitize_filename(name)}.json",
                               f"Icon-Scan '{name}'")

    # ------------------------------------------------- Geteilte Feld-Setzer

    def _profil_feld(self, objekt, feld: str, wert, wer: str) -> dict:
        """Die Felder, die Boss und Icon gemeinsam haben.

        Beide erkennen über Template **oder** Farb-Marker und handeln danach —
        das sind dieselben sechs Felder. Zwei Setzer dafür wären zwei Stellen,
        an denen eine Prüfung fehlen kann.
        """
        if feld == "konfidenz":
            zahl = self._kommazahl(wert)
            if zahl is None or not 0 < zahl <= 1:
                return self._scan_melde("Konfidenz muss zwischen 0 und 1 liegen.", "err")
            self._merke(f"{wer}: Konfidenz")
            objekt.min_confidence = zahl
            return self._scan_geaendert()
        if feld == "toleranz":
            zahl = self._ganzzahl(wert)
            if zahl is None:
                return self._scan_melde("Die Toleranz muss eine ganze Zahl sein.", "err")
            self._merke(f"{wer}: Toleranz")
            objekt.color_tolerance = max(0, zahl)
            return self._scan_geaendert()
        if feld == "template":
            self._merke(f"{wer}: Vorlage")
            objekt.template = str(wert) or None
            return self._scan_geaendert()
        if feld == "marker":
            farben = [rgbwert(h) for h in (wert or [])]
            self._merke(f"{wer}: Marker")
            objekt.marker_colors = [f for f in farben if f]
            return self._scan_geaendert(f"{len(objekt.marker_colors)} Marker-Farbe(n).")
        if feld == "punkt":
            punkt_id = self._ganzzahl(wert)
            self._merke(f"{wer}: Klickpunkt")
            objekt.action_point_id = punkt_id
            self._aktion_punkt_anwenden(objekt)
            return self._scan_geaendert()
        if feld == "taste":
            self._merke(f"{wer}: Taste")
            objekt.action_key = str(wert) or None
            return self._scan_geaendert()
        if feld == "verzoegerung":
            zahl = self._kommazahl(wert)
            if zahl is None or zahl < 0:
                return self._scan_melde("Die Verzögerung muss eine Zahl ≥ 0 sein.", "err")
            self._merke(f"{wer}: Verzögerung")
            objekt.action_delay = zahl
            return self._scan_geaendert()
        return self._scan_melde(f"Unbekanntes Feld '{feld}'.", "err")

    def _aktion_punkt_anwenden(self, objekt) -> None:
        """Zieht `action_x/y` an der Referenz nach.

        Die Koordinate steht in `points.json`, sonst nirgends — `action_x/y`
        sind abgeleitete Arbeitswerte, genau wie `step.x/y`. Der Serializer
        schreibt sie nicht; gefüllt werden sie, damit die Anzeige etwas zu
        zeigen hat.
        """
        punkt = next((p for p in self.points if p.id == objekt.action_point_id), None)
        objekt.action_x = punkt.x if punkt else 0
        objekt.action_y = punkt.y if punkt else 0

    def _erkennung_umbenennen(self, bestand: dict, cfg, wert, wort: str) -> dict:
        """Umbenennen eines Boss-/Icon-Scans — Schlüssel und Datei ziehen mit.

        Die alte Datei bleibt liegen, wie beim Item-Scan: eine Sequenz, die noch
        auf den alten Namen zeigt, verlöre ihren Scan sonst kommentarlos.
        """
        neu = sanitize_filename(str(wert or "").strip())
        if not neu or neu == cfg.name:
            return self.scan_daten()
        if neu in bestand:
            return self._scan_melde(f"'{neu}' gibt es schon.", "warn")
        self._merke(f"{wort} '{cfg.name}' umbenannt")
        alt = cfg.name
        neuer_bestand = {(neu if k == alt else k): v for k, v in bestand.items()}
        bestand.clear()
        bestand.update(neuer_bestand)
        cfg.name = neu
        if self.boss_offen == alt and bestand is self.boss_scans:
            self.boss_offen = neu
        if self.icon_offen == alt and bestand is self.icon_scans:
            self.icon_offen = neu
        return self._scan_geaendert(
            f"'{alt}' heisst jetzt '{neu}' — die alte Datei bleibt liegen.", "warn")

    def _region_setzen(self, cfg, wert, wer: str) -> dict:
        """Eine Region aus vier getippten Zahlen.

        Die Zahlenfelder bleiben neben dem Aufziehen bestehen: eine Region um
        drei Pixel zu korrigieren ist über zwei Klicks im Bild schlechter zu
        treffen als über ein Zahlenfeld.
        """
        try:
            l, o, r, u = (int(v) for v in (wert or [])[:4])
        except (TypeError, ValueError):
            return self._scan_melde("Eine Region braucht vier ganze Zahlen.", "err")
        region = normalize_region(l, o, r, u)
        if region[2] - region[0] < MIN_REGION or region[3] - region[1] < MIN_REGION:
            return self._scan_melde(
                f"Zu klein — mindestens {MIN_REGION}×{MIN_REGION} Pixel.", "warn")
        self._merke(f"{wer}: Region")
        cfg.scan_region = region
        return self._scan_geaendert(
            f"Region {region[2] - region[0]}×{region[3] - region[1]} "
            f"ab ({region[0]}, {region[1]}).")

    @staticmethod
    def _ganzzahl(wert):
        try:
            return int(wert)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _kommazahl(wert):
        try:
            return float(wert)
        except (TypeError, ValueError):
            return None

    def _datei_weg(self, pfad: Path, wer: str) -> dict:
        try:
            pfad.unlink(missing_ok=True)
        except OSError:
            return self._scan_melde(f"{wer} entfernt, die Datei blieb liegen.", "warn")
        # Der eigene Schreibvorgang zählt nicht als Fremdänderung — Löschen
        # dreht die Änderungszeit des Ordners genauso weiter wie Schreiben.
        self._platte_nachziehen(pfad.parent)
        return self._scan_melde(f"{wer} gelöscht.", "warn")

    # ------------------------------------------------------------ Werkzeuge

    def region_modus(self, daten: Optional[dict] = None) -> dict:
        """Schaltet das Region- bzw. Aktionspunkt-Werkzeug scharf.

        **Der Modus allein reicht nicht.** Dieselbe Geste setzt je nach Scan-Art
        eine andere Region, und die Art ist Oberflächenzustand — sie steht
        bewusst nicht in der Brücke. Deshalb sagt der Befehl, worauf er wirkt;
        gemerkt wird es nur, solange das Werkzeug an ist.

        Der Rückweg ist wie überall die markierte Kachel selbst: nochmal
        derselbe Modus schaltet zurück ins Auswählen.
        """
        self._scan_laden()
        daten = daten or {}
        modus = str(daten.get("modus") or MODUS_REGION)
        if modus not in (MODUS_REGION, MODUS_AKTION, MODUS_WAHL):
            return self._scan_melde(f"Unbekannter Modus '{modus}'.", "err")
        art = str(daten.get("art") or "")
        if modus == MODUS_WAHL or (modus == self.scan_modus and self._region_ziel):
            self.scan_modus, self._region_ziel, self._ecke = MODUS_WAHL, None, None
            return self._scan_melde("Zurück zum Auswählen.", "info")
        ziel = self._ziel_pruefen(art)
        if ziel is None:
            return self._scan_melde(
                "Erst einen Boss- bzw. Icon-Scan anlegen oder öffnen.", "warn")
        if not self._flaeche():
            return self._scan_melde("Erst einen Screenshot aufnehmen.", "warn")
        self.scan_modus, self._region_ziel, self._ecke = modus, ziel, None
        if modus == MODUS_REGION:
            return self._scan_melde(
                "Region: zwei Ecken anklicken — eng um das, was erkannt werden "
                "soll.  ·  ESC oder nochmal die Kachel = zurück", "info")
        return self._scan_melde(
            "Klickpunkt: die Stelle anklicken, die bei einem Treffer geklickt "
            "wird.  ·  ESC oder nochmal die Kachel = zurück", "info")

    def _ziel_pruefen(self, art: str) -> Optional[tuple]:
        if art == "boss" and self.boss_offen in self.boss_scans:
            return ("boss", self.boss_offen)
        if art == "icon" and self.icon_offen in self.icon_scans:
            return ("icon", self.icon_offen)
        return None

    def _region_objekt(self):
        """Die Konfiguration, auf die das aktive Werkzeug wirkt."""
        if not self._region_ziel:
            return None
        art, name = self._region_ziel
        return (self.boss_scans if art == "boss" else self.icon_scans).get(name)

    def _klick_region(self, x: int, y: int) -> dict:
        """Zwei Ecken ergeben die Scan-Region — dieselbe Geste wie beim Slot."""
        cfg = self._region_objekt()
        if cfg is None:
            self.scan_modus = MODUS_WAHL
            return self._scan_melde("Kein Ziel für die Region.", "warn")
        if self._ecke is None:
            self._ecke = (x, y)
            return self._scan_melde("Erste Ecke gesetzt — zweite Ecke anklicken.", "info")
        erste, self._ecke = self._ecke, None
        antwort = self._region_setzen(cfg, [erste[0], erste[1], x, y],
                                      f"'{cfg.name}'")
        # **Ein zu kleines Rechteck laesst das Werkzeug an.** Sonst muesste man
        # nach jedem Verklicken erst wieder die Kachel suchen — und genau dieses
        # Verklicken ist der Grund, warum es zwei Klicks und kein Ziehen sind.
        if antwort["status"]["art"] in ("warn", "err"):
            return antwort
        self._werkzeug_fertig()
        # Nochmal melden: die Antwort von oben traegt den Modus von VOR dem
        # Aufraeumen, und die Werkzeugleiste liest ihn aus der Momentaufnahme.
        return self._scan_melde(antwort["status"]["text"])

    def _klick_aktion(self, x: int, y: int) -> dict:
        """Setzt den Klickpunkt der Aktion — über einen Punkt, nie über Zahlen.

        **Wer im Editor eine Stelle erzeugt, legt einen Punkt an.** Ein
        vorhandener an derselben Stelle wird wiederverwendet
        (`punkt_an_stelle()` — die eine Regel dafür); sonst wäre derselbe Knopf
        zweimal in `points.json` und beim Nachjustieren wanderte die Hälfte.
        """
        cfg = self._region_objekt()
        if cfg is None:
            self.scan_modus = MODUS_WAHL
            return self._scan_melde("Kein Ziel für den Klickpunkt.", "warn")
        objekt = cfg
        if self._region_ziel[0] == "boss":
            objekt = self._boss_gewaehlt()
            if objekt is None:
                return self._scan_melde(
                    "Erst einen Boss wählen — der Klickpunkt gehört ihm, nicht dem Scan.",
                    "warn")
        farbe = self._foto_farbe(x, y)
        punkt = self._punkt_fuer_aktion(x, y, farbe, objekt.name)
        self._merke(f"'{objekt.name}': Klickpunkt")
        objekt.action_point_id = punkt.id
        self._aktion_punkt_anwenden(objekt)
        self._scan_dirty = True
        self._werkzeug_fertig()
        return self._scan_melde(
            f"Punkt #{punkt.id} als Klickpunkt von '{objekt.name}' gesetzt.")

    def _punkt_fuer_aktion(self, x: int, y: int, farbe, name: str):
        """Der Punkt an dieser Stelle — vorhandener oder neuer."""
        from ...persistence.sequences import punkt_an_stelle
        from .model import PalettePoint
        punkt = punkt_an_stelle(self.points, x, y, farbe)
        if punkt is None:
            punkt = PalettePoint(
                id=max([p.id for p in self.points], default=0) + 1,
                x=x, y=y, name=name or "Scan-Aktion",
                color=tuple(farbe) if farbe else None,
                source="Scans-Reiter")
            self.points.append(punkt)
        return punkt

    def vorlage_aufnehmen(self, daten: Optional[dict] = None) -> dict:
        """Lernt die Region als Template — der Griff, der heute den ganzen Ablauf kostet.

        Eine Vorlage neu aufzunehmen war bisher nur über einen kompletten
        Durchlauf des Konsolen-Editors möglich. Es ist aber genau das, was man
        nach einem Spiel-Update als Erstes tut.
        """
        self._scan_laden()
        daten = daten or {}
        objekt, cfg = self._erkennungsziel(daten)
        if objekt is None:
            return self._scan_melde("Kein Boss bzw. Icon-Scan gewählt.", "warn")
        crop = self._foto_crop(tuple(cfg.scan_region))
        if crop is None:
            return self._scan_melde(
                "Die Region liegt ausserhalb des Bildes — erst neu aufnehmen.", "warn")
        from .scan_model import save_template
        dateiname = save_template(crop, objekt.name)
        if not dateiname:
            return self._scan_melde("Vorlage konnte nicht geschrieben werden.", "err")
        self._merke(f"'{objekt.name}': Vorlage aufgenommen")
        objekt.template = dateiname
        # Die Vorschau hängt am Dateinamen und der wurde gerade überschrieben.
        self._vorschau.pop(dateiname, None)
        return self._scan_geaendert(
            f"Vorlage '{dateiname}' aufgenommen "
            f"({crop.size[0]}×{crop.size[1]}).")

    def marker_messen(self, daten: Optional[dict] = None) -> dict:
        """Misst die auffälligsten Farben der Region als Marker.

        Dieselbe Rechnung wie beim Item-Lernen (`_collect_markers_silent`) —
        eine zweite Fassung „für Bosse" wäre eine zweite Antwort auf dieselbe
        Frage, und die beiden liefen auseinander.
        """
        self._scan_laden()
        daten = daten or {}
        objekt, cfg = self._erkennungsziel(daten)
        if objekt is None:
            return self._scan_melde("Kein Boss bzw. Icon-Scan gewählt.", "warn")
        crop = self._foto_crop(tuple(cfg.scan_region))
        if crop is None:
            return self._scan_melde(
                "Die Region liegt ausserhalb des Bildes — erst neu aufnehmen.", "warn")
        from ..item_editor.markers import _collect_markers_silent
        farben = _collect_markers_silent(crop)
        if not farben:
            return self._scan_melde("Keine Farben gefunden.", "warn")
        self._merke(f"'{objekt.name}': Marker gemessen")
        objekt.marker_colors = farben
        return self._scan_geaendert(
            f"{len(farben)} Marker-Farbe(n) aus der Region gemessen.")

    def _erkennungsziel(self, daten: dict):
        """(Profil, Scan-Konfiguration) für Vorlage/Marker/Test.

        Beim Icon ist beides dasselbe Objekt, beim Boss nicht: die Region gehört
        dem Scan, Vorlage und Marker gehören dem einzelnen Boss.
        """
        art = str(daten.get("art") or "")
        if art == "icon":
            cfg = self.icon_scans.get(str(daten.get("name") or self.icon_offen))
            return cfg, cfg
        cfg = self.boss_scans.get(self.boss_offen)
        if cfg is None:
            return None, None
        boss = self._boss_finden(str(daten.get("name") or self.boss_wahl),
                                 bool(daten.get("global", self.boss_wahl_global)))
        return boss, cfg

    # ---------------------------------------------------------------- Tests

    def boss_testen(self, daten: Optional[dict] = None) -> dict:
        """Hält den gewählten Boss gegen das eingefrorene Bild.

        **Folgenlos.** Erkennen, anzeigen, die Aktion nur benennen — sie wird
        nie ausgeführt.
        """
        self._scan_laden()
        boss, cfg = self._erkennungsziel(daten or {})
        if boss is None or cfg is None:
            return self._scan_melde("Kein Boss gewählt.", "warn")
        ergebnis = self._profil_pruefen(boss, cfg.scan_region, cfg.color_tolerance)
        ergebnis["aktion"] = self._aktion_text(boss)
        self._boss_test = ergebnis
        self._boss_tests[boss.name] = ergebnis
        return self._scan_melde(
            (f"'{boss.name}' erkannt ({ergebnis['grund']})." if ergebnis["ok"]
             else f"'{boss.name}' nicht erkannt: {ergebnis['grund']}."),
            "ok" if ergebnis["ok"] else "warn")

    def boss_alle_testen(self, daten: Optional[dict] = None) -> dict:
        """Hält jeden Boss des Scans gegen dieses Bild — lokal plus Bibliothek.

        Getestet wird die **gemergte** Liste, denn genau die sieht der Lauf
        (`execute_boss_scan` merged lokal + global, lokale gewinnen bei
        Namensgleichheit). Nur die lokalen zu prüfen hiesse, die Hälfte der
        Erkennung zu verschweigen.
        """
        self._scan_laden()
        cfg = self.boss_scans.get(self.boss_offen)
        if cfg is None:
            return self._scan_melde("Kein Boss-Scan offen.", "warn")
        bosse = self._gemergte_bosse(cfg)
        if not bosse:
            return self._scan_melde("Dieser Scan kennt noch keinen Boss.", "info")
        self._boss_tests = {}
        for boss in bosse:
            ergebnis = self._profil_pruefen(boss, cfg.scan_region, cfg.color_tolerance)
            ergebnis["aktion"] = self._aktion_text(boss)
            self._boss_tests[boss.name] = ergebnis
        treffer = [n for n, e in self._boss_tests.items() if e["ok"]]
        # Die Reihenfolge IST die Priorität: der erste Treffer gewinnt im Lauf.
        self._boss_test = self._boss_tests[treffer[0]] if treffer else None
        return self._scan_melde(
            (f"{treffer[0]} würde erkannt ({len(treffer)} von {len(bosse)} passen)."
             if treffer else f"Keiner von {len(bosse)} Bossen passt auf dieses Bild."),
            "ok" if treffer else "warn")

    def _gemergte_bosse(self, cfg: BossScanConfig) -> list:
        """Lokale Bosse plus Bibliothek — lokale gewinnen bei Namensgleichheit."""
        namen = {b.name for b in cfg.bosses}
        return list(cfg.bosses) + [b for b in self.global_bosses if b.name not in namen]

    def icon_testen(self, daten: Optional[dict] = None) -> dict:
        """Hält den offenen Icon-Scan gegen das Bild — samt Vorschlag, was hilft.

        **Der Vorschlag ist der Kern.** Ein Test, der nur „fehlgeschlagen" sagt,
        lässt einen genau dort stehen, wo man vorher war; einer, der die
        Toleranz nennt, bei der es klappt, ist ein Klick von der Lösung
        entfernt.
        """
        self._scan_laden()
        cfg = self.icon_scans.get(str((daten or {}).get("name") or self.icon_offen))
        if cfg is None:
            return self._scan_melde("Kein Icon-Scan gewählt.", "warn")
        ergebnis = self._profil_pruefen(cfg, cfg.scan_region, cfg.color_tolerance)
        ergebnis["aktion"] = self._aktion_text(cfg)
        if not ergebnis["ok"] and cfg.marker_colors:
            ergebnis["vorschlag"] = self._toleranz_vorschlag(cfg)
        self._icon_test = ergebnis
        return self._scan_melde(
            (f"Icon erkannt ({ergebnis['grund']})." if ergebnis["ok"]
             else f"Icon nicht erkannt: {ergebnis['grund']}."),
            "ok" if ergebnis["ok"] else "warn")

    def _profil_pruefen(self, profil, region, toleranz: int) -> dict:
        """Ein Profil gegen die Region halten — mit der Rechnung der Laufzeit."""
        crop = self._foto_crop(tuple(region))
        if crop is None:
            return self._testergebnis(profil, False, "Region liegt ausserhalb des Bildes")
        if profil.template and not self._hat_opencv():
            return self._testergebnis(profil, False, "braucht Template — OpenCV fehlt")
        if not profil.template and not profil.marker_colors:
            return self._testergebnis(profil, False, "weder Vorlage noch Marker gesetzt")

        from ...config import CONFIG
        from ...runtime.item_scan import _check_profile_match
        from .scan_learning import _NurConfig
        beginn = time.perf_counter()
        ok, wert = _check_profile_match(profil, crop, toleranz, _NurConfig(CONFIG),
                                        False, return_score=True)
        dauer = (time.perf_counter() - beginn) * 1000
        gefunden, gesamt, noetig = self._marker_zaehlen(profil, crop, toleranz)
        if profil.template:
            grund = (f"Template {wert:.0%}" if ok
                     else f"Template {wert:.0%} (nötig {profil.min_confidence:.0%})")
        else:
            grund = (f"{gefunden} von {gesamt} Markern" if ok
                     else f"{gefunden} von {gesamt} Markern · nötig {noetig}")
        ergebnis = self._testergebnis(profil, ok, grund)
        ergebnis.update({"konfidenz": round(wert, 4), "dauer": round(dauer),
                         "marker_gefunden": gefunden, "marker_gesamt": gesamt,
                         "marker_noetig": noetig, "toleranz": toleranz,
                         "methode": "Template" if profil.template else "Marker"})
        return ergebnis

    @staticmethod
    def _testergebnis(profil, ok: bool, grund: str) -> dict:
        return {"name": profil.name, "ok": ok, "grund": grund, "methode": None,
                "konfidenz": None, "dauer": 0, "marker_gefunden": 0,
                "marker_gesamt": len(profil.marker_colors), "marker_noetig": 0,
                "toleranz": 0, "aktion": "", "vorschlag": None}

    @staticmethod
    def _marker_zaehlen(profil, crop, toleranz: int) -> tuple:
        """(gefunden, gesamt, nötig) — dieselben Regeln wie `_check_profile_match`."""
        if not profil.marker_colors:
            return 0, 0, 0
        from ...config import CONFIG
        from ...imaging import find_color_in_image
        gesamt = len(profil.marker_colors)
        gefunden = sum(1 for farbe in profil.marker_colors
                       if find_color_in_image(crop, farbe, toleranz,
                                              min_pixels=CONFIG.scan_marker_min_pixels))
        noetig = gesamt if CONFIG.scan_require_all_markers else min(
            gesamt, CONFIG.scan_min_markers_required)
        return gefunden, gesamt, noetig

    def _toleranz_vorschlag(self, cfg) -> Optional[dict]:
        """Die kleinste Toleranz, bei der genug Marker gefunden würden.

        Gesucht wird von der aktuellen aufwärts und in Schritten: eine Toleranz
        pixelgenau zu bestimmen wäre eine Genauigkeit, die die Zahl gar nicht
        hat — und jeder Schritt kostet einen Durchgang durch das Bild.
        """
        crop = self._foto_crop(tuple(cfg.scan_region))
        if crop is None:
            return None
        for toleranz in range(cfg.color_tolerance + 4, 121, 4):
            gefunden, gesamt, noetig = self._marker_zaehlen(cfg, crop, toleranz)
            if gesamt and gefunden >= noetig:
                return {"feld": "toleranz", "wert": toleranz,
                        "text": f"Toleranz auf {toleranz} setzen"}
        return None

    def _aktion_text(self, objekt) -> str:
        """Was bei einem Treffer passieren WÜRDE — als Satz, nicht als Tat."""
        aktion = objekt.action
        verzoegerung = getattr(objekt, "action_delay", 0) or 0
        nachsatz = f" nach {verzoegerung:g} s" if verzoegerung else ""
        if aktion == BOSS_ACTION_SCAN:
            return f"Item-Scan „{getattr(objekt, 'action_scan', None) or '—'}“{nachsatz}"
        if aktion == BOSS_ACTION_CLICK:
            punkt = next((p for p in self.points
                          if p.id == objekt.action_point_id), None)
            wohin = (f"Punkt #{punkt.id} ({punkt.name})" if punkt
                     else "Punkt fehlt — nichts würde geklickt")
            return f"{wohin} klicken{nachsatz}"
        if aktion == BOSS_ACTION_KEY:
            return f"Taste „{objekt.action_key or '—'}“{nachsatz}"
        return ACTION_TEXT.get(aktion, aktion) + nachsatz

    def ocr_pruefen(self, daten: Optional[dict] = None) -> dict:
        """Ist überhaupt ein OCR-Backend installiert?

        Auf Knopfdruck und nicht bei jeder Momentaufnahme: `autoclicker.ocr`
        importiert EasyOCR beim Laden, und das zieht Torch nach — Sekunden, in
        denen der Reiter stünde. Danach ist das Modul geladen und die Antwort
        kostet nichts mehr; gemerkt wird sie trotzdem, damit die Anzeige nicht
        vom Zufall abhängt.
        """
        from ...config import CONFIG
        beginn = time.perf_counter()
        try:
            from ... import ocr
            backends = ocr.available_backends()
        except ImportError as fehler:
            self._ocr_stand = {"da": False, "backends": [], "grund": str(fehler)}
            return self._scan_melde(f"OCR nicht verfügbar: {fehler}", "warn")
        self._ocr_stand = {
            "da": bool(backends), "backends": backends, "grund": "",
            "dauer": round((time.perf_counter() - beginn) * 1000),
        }
        if not backends:
            return self._scan_melde(
                "Kein OCR-Backend installiert: pip install easyocr "
                "(oder pytesseract).", "warn")
        return self._scan_melde(
            f"OCR bereit: {', '.join(backends)} "
            f"(eingestellt: {CONFIG.ocr_backend or 'automatisch'}).")

    def llm_pruefen(self, daten: Optional[dict] = None) -> dict:
        """Antwortet der LLM-Endpunkt überhaupt?

        Eine Lampe, die „nicht erreichbar" sagt, spart die halbe Stunde, in der
        man sonst die Prompts verdächtigt. Gefragt wird nur auf Knopfdruck: eine
        Momentaufnahme darf nicht auf ein Netzwerk warten.
        """
        from ...config import CONFIG
        endpunkt = CONFIG.llm_endpoint
        beginn = time.perf_counter()
        try:
            import urllib.request
            urllib.request.urlopen(endpunkt, timeout=_LLM_PROBE_TIMEOUT).read(1)
            erreichbar, grund = True, ""
        except Exception as fehler:                                   # noqa: BLE001
            # Was da schiefgeht, ist nicht unsere Sache — dass es schiefgeht,
            # schon. Jede Ausnahme heisst hier dasselbe: da antwortet niemand.
            erreichbar, grund = False, str(fehler)
        self._llm_stand = {
            "erreichbar": erreichbar, "grund": grund, "endpunkt": endpunkt,
            "dauer": round((time.perf_counter() - beginn) * 1000),
        }
        return self._scan_melde(
            f"{CONFIG.llm_provider} erreichbar ({self._llm_stand['dauer']} ms)."
            if erreichbar else f"{CONFIG.llm_provider} nicht erreichbar: {grund}",
            "ok" if erreichbar else "warn")

    # ------------------------------------------------------------- Speichern

    def _erkennung_speichern(self) -> list:
        """Schreibt Boss-Scans, Icon-Scans und die Bibliothek. Fehler als Liste."""
        from ...persistence import save_boss_scan, save_global_bosses, save_icon_scan
        fehler = []
        for cfg in self.boss_scans.values():
            try:
                save_boss_scan(cfg)
            except OSError:
                fehler.append(f"boss_scans/{cfg.name}.json")
        for cfg in self.icon_scans.values():
            try:
                save_icon_scan(cfg)
            except OSError:
                fehler.append(f"icon_scans/{cfg.name}.json")
        try:
            save_global_bosses(_BibliothekState(self.global_bosses))
        except OSError:
            fehler.append("boss_scans/global/bosses.json")
        return fehler
