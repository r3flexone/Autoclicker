"""
Datenklassen für den Autoclicker.
Definiert alle Datenstrukturen wie ClickPoint, SequenceStep, Sequence, etc.
"""

import random
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import AppConfig

# Der DATEI-Default fuer min_confidence: was gilt, wenn das Feld in der JSON fehlt.
# Konstant und NICHT aus der Config abgeleitet - sonst kaeme ein weggelassenes Feld
# mit einem anderen Wert zurueck, sobald jemand die Config anfasst.
# `AppConfig.scan_min_confidence` ist etwas anderes: die Voreinstellung fuer NEUE Profile.
DEFAULT_MIN_CONFIDENCE: float = 0.8


# =============================================================================
# STRING-KONSTANTEN (zentral definiert, verhindert Tippfehler)
# =============================================================================
# Aktions-Typen (zentral, eine Quelle der Wahrheit).
# ElseConfig, BossProfile und IconScanConfig teilen sich dieselben Aktionswerte —
# die familienspezifischen Namen unten sind nur Aliase für Lesbarkeit/Kompat.
ACTION_CLICK = "click"              # Punkt klicken
ACTION_KEY = "key"                  # Taste drücken
ACTION_SKIP = "skip"                # Schritt überspringen
ACTION_SKIP_CYCLE = "skip_cycle"    # Zyklus überspringen
ACTION_RESTART = "restart"          # Sequenz neustarten
ACTION_ITEM_SCAN = "item_scan"      # Item-Scan ausführen (nur Boss)

# ElseConfig.action
ELSE_SKIP = ACTION_SKIP
ELSE_SKIP_CYCLE = ACTION_SKIP_CYCLE
ELSE_RESTART = ACTION_RESTART
ELSE_CLICK = ACTION_CLICK
ELSE_KEY = ACTION_KEY
VALID_ELSE_ACTIONS = {ELSE_SKIP, ELSE_SKIP_CYCLE, ELSE_RESTART, ELSE_CLICK, ELSE_KEY}

# Was eine Aktion tut, als Satzteil. Steht hier und nicht bei den Anzeigen, weil
# es zwei davon gibt, die es brauchen und sich nicht kennen dürfen: die Karte im
# Sequenz-Studio (eigener Prozess, sieht `runtime/` nicht) und der Laufstatus,
# den die Laufzeit schreibt. Zwei Übersetzungstabellen für dieselben fünf Werte
# wären zwei Stellen, an denen ein neuer Aktionstyp vergessen werden kann.
ACTION_TEXT = {
    ACTION_CLICK: "Punkt klicken",
    ACTION_KEY: "Taste drücken",
    ACTION_SKIP: "Schritt überspringen",
    ACTION_SKIP_CYCLE: "Zyklus abbrechen",
    ACTION_RESTART: "Sequenz neu starten",
    ACTION_ITEM_SCAN: "Item-Scan ausführen",
}

# pixel_timeout_action (Config)
TIMEOUT_SKIP_CYCLE = "skip_cycle"
TIMEOUT_RESTART = "restart"
TIMEOUT_STOP = "stop"

# Was die Timeout-Aktion tut, als Satzteil — aus demselben Grund hier wie
# ACTION_TEXT: die Laufzeit schreibt sie in den Laufstatus, das Studio zeigt sie
# im Inspektor an, und die beiden duerfen sich nicht kennen.
TIMEOUT_TEXT = {
    TIMEOUT_SKIP_CYCLE: "Zyklus abbrechen, nächster Zyklus",
    TIMEOUT_RESTART: "Sequenz neu starten",
    TIMEOUT_STOP: "Sequenz stoppen",
}

# consecutive_timeout_action (Config)
CONSEC_STOP = "stop"
CONSEC_QUIT = "quit"
CONSEC_EXIT = "exit"

# SequenceStep.item_scan_mode
SCAN_MODE_ALL = "all"         # Bestes pro Kategorie
SCAN_MODE_BEST = "best"       # Nur 1 bestes Item total
SCAN_MODE_EVERY = "every"     # Jedes gefundene Item
VALID_SCAN_MODES = {SCAN_MODE_ALL, SCAN_MODE_BEST, SCAN_MODE_EVERY}

# BossProfile.action
BOSS_ACTION_SCAN = ACTION_ITEM_SCAN
BOSS_ACTION_CLICK = ACTION_CLICK
BOSS_ACTION_KEY = ACTION_KEY
BOSS_ACTION_SKIP = ACTION_SKIP
BOSS_ACTION_SKIP_CYCLE = ACTION_SKIP_CYCLE
BOSS_ACTION_RESTART = ACTION_RESTART
VALID_BOSS_ACTIONS = {BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY,
                      BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART}

# IconScanConfig.action — Aktion wenn ein Icon (z.B. rotes "!") erkannt wird
ICON_ACTION_CLICK = ACTION_CLICK
ICON_ACTION_KEY = ACTION_KEY
ICON_ACTION_SKIP = ACTION_SKIP
ICON_ACTION_SKIP_CYCLE = ACTION_SKIP_CYCLE
ICON_ACTION_RESTART = ACTION_RESTART
VALID_ICON_ACTIONS = {ICON_ACTION_CLICK, ICON_ACTION_KEY, ICON_ACTION_SKIP,
                      ICON_ACTION_SKIP_CYCLE, ICON_ACTION_RESTART}


# =============================================================================
# DATENKLASSEN
# =============================================================================
@dataclass
class ClickPoint:
    """Ein Klickpunkt mit x,y Koordinaten und stabiler ID."""
    x: int
    y: int
    name: str = ""  # Optionaler Name für den Punkt
    id: int = 0     # Stabile ID für Referenzierung (bleibt bei Umsortierung erhalten)
    # Pixelfarbe an der Position zum Aufnahme-Zeitpunkt (r,g,b) oder None.
    # Wird beim Erstellen eines Schritts aus diesem Punkt als recorded_color
    # übernommen — zuverlässiger als ein Live-Abgriff im Editor, da das Spiel
    # bei der Aufnahme im richtigen Zustand war.
    color: Optional[tuple[int, int, int]] = None
    # Herkunfts-Kommentar, z.B. "Aufnahme 'Bossfarm'" — bleibt auch nach
    # Umbenennen des Punkts sichtbar, damit klar bleibt woher er stammt.
    source: str = ""

    def __str__(self) -> str:
        src = f"  [{self.source}]" if self.source else ""
        if self.name:
            return f"#{self.id} {self.name} ({self.x}, {self.y}){src}"
        return f"#{self.id} ({self.x}, {self.y}){src}"


# KOORDINATEN GEHOEREN IN DIE PUNKTLISTE IHRER SEQUENZ - NIRGENDWO SONST.
# Ein Schritt speichert nur die `point_id`; x/y/Farbe stehen einmalig unter
# `points` in derselben Sequenzdatei. Dadurch darf dieselbe ID in zwei
# Sequenzen bewusst zwei verschiedene Stellen bezeichnen.
# Eine Koordinate an zwei Stellen ist eine, die an einer der beiden falsch sein
# kann - und bei einer Kalibrierung muesste jede Kopie einzeln erwischt werden.
# Es gibt bewusst KEINEN Rueckfallwert: eine tote `point_id` laesst den Schritt
# uebersprungen und gemeldet werden.
# `pixel`/`color` bzw. `x`/`y`/`name` unten sind die AUFGELOESTEN Arbeitswerte,
# gefuellt von `resolve_point_references()` - gelesen, aber nie gespeichert.

@dataclass
class ElseConfig:
    """Fallback-Aktion wenn eine Bedingung (Farbe/Scan) fehlschlägt."""
    action: str                          # "skip", "skip_cycle", "restart", "click", "key"
    # Referenz auf den Fallback-Punkt (nur bei action="click"). DAS ist der
    # gespeicherte Wert — x/y/name darunter werden daraus abgeleitet.
    point_id: Optional[int] = None
    x: int = 0                           # abgeleitet: X für Fallback-Klick
    y: int = 0                           # abgeleitet: Y für Fallback-Klick
    delay: float = 0                     # Delay vor Fallback
    key: Optional[str] = None            # Taste für Fallback
    name: str = ""                       # abgeleitet: Name des Fallback-Punkts


@dataclass
class WaitCondition:
    """Farb-Bedingung an einer Pixel-Position: warten oder einmal prüfen."""
    # Referenz auf den Punkt, dessen Position UND Farbe geprueft werden; pixel/color
    # darunter sind daraus abgeleitet. Soll an derselben Stelle auf eine ANDERE Farbe
    # geprueft werden, ist das ein eigener Punkt.
    point_id: Optional[int] = None
    pixel: tuple[int, int] = (0, 0)      # abgeleitet: (x, y) Position zum Prüfen
    color: tuple[int, int, int] = (0, 0, 0)  # abgeleitet: (r,g,b) die erscheinen soll
    until_gone: bool = False             # True = warte bis Farbe WEG ist
    # True = NICHT warten, sondern einmal prüfen. Passt die Farbe nicht, greift sofort
    # else_config (Standard: Schritt überspringen) statt bis zum Timeout zu blockieren.
    check_only: bool = False


@dataclass
class SequenceStep:
    """Ein Schritt in einer Sequenz: Erst warten/prüfen, DANN klicken."""
    # x/y/name sind abgeleitet (siehe Block oben) und deshalb optional: Pflicht ist die
    # `point_id`, nicht die Koordinate. Frueher war es umgekehrt - da MUSSTE jeder
    # Aufrufer x und y angeben, und genau das hat die Kopien erzeugt.
    x: int = 0
    y: int = 0
    delay_before: float = 0.0   # Wartezeit in Sekunden VOR diesem Klick (0 = sofort)
    name: str = ""              # abgeleitet: Name des Punktes
    # Referenz auf den Punkt im Punkte-Pool - der gespeicherte Wert; x/y/name und
    # recorded_color werden daraus geholt. Ein Schritt mit Stelle MUSS eine haben;
    # `None` bleibt Tastendruck, Wait-only, Scans, Screenshot und dem Blanko-Block.
    point_id: Optional[int] = None
    # Optional: Warten auf Farbe statt Zeit (VOR dem Klick)
    wait_condition: Optional[WaitCondition] = None
    # Optional: Nachpruefung NACH der Aktion - "hat der Klick gewirkt?". Dieselbe
    # WaitCondition wie oben; `verify_retries` sagt, wie oft die Aktion wiederholt
    # wird, bevor `else_config` greift.
    verify_condition: Optional[WaitCondition] = None
    # Optional: Item-Scan ausführen statt direktem Klick
    item_scan: Optional[str] = None      # Name des Item-Scans
    item_scan_mode: str = "all"          # "all" = bestes pro Kategorie, "best" = nur 1 Item total
    # Optional: Nur warten, nicht klicken
    wait_only: bool = False              # True = nur warten, kein Klick
    # Optional: Zufällige Verzögerung (delay_before bis delay_max)
    delay_max: Optional[float] = None    # None = feste Zeit, sonst Bereich
    # Optional: Tastendruck statt Mausklick
    key_press: Optional[str] = None      # z.B. "enter", "space", "f1"
    # Optional: Mausrad drehen statt klicken. Positiv = hoch, negativ = runter,
    # Betrag = Rasterstufen. Gescrollt wird an (x, y), weil Windows das Rad-Event an
    # das Fenster UNTER dem Cursor liefert.
    scroll: Optional[int] = None
    # Optional: Fallback/Else-Aktion wenn Bedingung fehlschlägt
    else_config: Optional[ElseConfig] = None
    # Optional: Boss-Scan ausführen (erkennt Boss → bedingte Aktion)
    boss_scan: Optional[str] = None      # Name der BossScanConfig
    # Optional: Boss-Watcher (wartet bis Boss erkannt, dann Aktion)
    boss_watcher: Optional[str] = None   # Name der BossScanConfig für Watcher-Modus
    # Optional: Icon-Scan (erkennt Symbol/Icon in Region → Aktion)
    icon_scan: Optional[str] = None      # Name der IconScanConfig
    # Optional: Screenshot machen (kein Klick, kein Scan)
    screenshot_only: bool = False        # True = nur Screenshot, kein Klick
    screenshot_region: Optional[tuple[int, int, int, int]] = None  # (x1,y1,x2,y2) oder None = Vollbild
    # Abgeleitet aus `ClickPoint.color`: die bei der Aufnahme erfasste Pixelfarbe am
    # Klickpunkt (r,g,b). Reines Hilfs-/Referenzdatum für die Nachbearbeitung — erlaubt,
    # einen aufgenommenen Klick nachträglich in einen Farb-Trigger umzuwandeln, ohne die
    # Farbe erneut abgreifen zu müssen. Beeinflusst die Ausführung NICHT.
    recorded_color: Optional[tuple[int, int, int]] = None
    # Arbeitswert, wird nie gespeichert: True = die point_id zeigt ins Leere, der Punkt
    # wurde geloescht. `step_gate()` ueberspringt den Schritt dann und meldet es. Ohne
    # dieses Flag wuerde er auf (0, 0) klicken - es gibt ja keine Rueckfall-Koordinate
    # mehr, und das ist genau so gewollt.
    unresolved: bool = False

    def __str__(self) -> str:
        else_str = self._verify_str() + self._else_str()
        if self.boss_watcher:
            return f"BOSS-WATCHER '{self.boss_watcher}' (wartet auf Boss){else_str}"
        if self.screenshot_only:
            region = self.screenshot_region
            if region:
                return f"SCREENSHOT ({region[0]},{region[1]})→({region[2]},{region[3]})"
            return "SCREENSHOT (Vollbild)"
        if self.key_press:
            return (f"{self._trigger_str()} → drücke Taste '{self.key_press}'{else_str}")
        if self.scroll:
            richtung = "hoch" if self.scroll > 0 else "runter"
            ziel = f"{self.name} " if self.name else ""
            return (f"{self._trigger_str()} → scrolle {richtung} x{abs(self.scroll)} "
                    f"bei {ziel}({self.x}, {self.y}){else_str}")
        if self.boss_scan:
            return f"BOSS-SCAN '{self.boss_scan}'{else_str}"
        if self.icon_scan:
            # Fehlte hier komplett: ein Icon-Scan-Schritt fiel bis ans Ende durch und
            # wurde in der Schritt-Liste als "sofort → klicke (0, 0)" angezeigt.
            return f"ICON-SCAN '{self.icon_scan}'{else_str}"
        if self.item_scan:
            mode_strs = {SCAN_MODE_ALL: "bestes/Kategorie", SCAN_MODE_BEST: "1 bestes", SCAN_MODE_EVERY: "JEDES"}
            mode_str = mode_strs.get(self.item_scan_mode, self.item_scan_mode)
            return f"SCAN '{self.item_scan}' → klicke {mode_str}{else_str}"
        wc = self.wait_condition
        if self.wait_only:
            if wc:
                gone_str = "WEG ist" if wc.until_gone else "DA ist"
                if wc.check_only:
                    return (f"PRÜFE einmal ob Farbe {gone_str} bei "
                            f"({wc.pixel[0]},{wc.pixel[1]}) (kein Klick){else_str}")
                return f"WARTE bis Farbe {gone_str} bei ({wc.pixel[0]},{wc.pixel[1]}) (kein Klick){else_str}"
            return f"WARTE {self._delay_str()} (kein Klick)"
        ref = f" #{self.point_id}" if self.point_id is not None else ""
        pos_str = (f"{self.name}{ref} ({self.x}, {self.y})" if self.name
                   else f"{ref.strip()} ({self.x}, {self.y})".strip())
        if wc:
            if wc.check_only:
                zustand = "WEG" if wc.until_gone else "DA"
                vorlauf = f"warte {self._delay_str()}, dann " if self.delay_before > 0 else ""
                return (f"{vorlauf}prüfe einmal ob Farbe {zustand} bei "
                        f"({wc.pixel[0]},{wc.pixel[1]}) → klicke {pos_str}"
                        f"{else_str or ' | sonst: überspringen'}")
            gone_str = "bis Farbe WEG" if wc.until_gone else "auf Farbe"
            delay_str = self._delay_str()
            if self.delay_before > 0:
                return f"warte {delay_str}, dann {gone_str} bei ({wc.pixel[0]},{wc.pixel[1]}) → klicke {pos_str}{else_str}"
            return f"warte {gone_str} bei ({wc.pixel[0]},{wc.pixel[1]}) → klicke {pos_str}{else_str}"
        elif self.delay_before > 0:
            return f"warte {self._delay_str()} → klicke {pos_str}"
        else:
            return f"sofort → klicke {pos_str}"

    def _trigger_str(self) -> str:
        """Was VOR der Aktion passiert: Farb-Bedingung und/oder Wartezeit.

        Taste und Scroll zeigten hier früher nur die Wartezeit. Eine Farb-Bedingung
        an so einem Schritt war damit unsichtbar — man konnte sie im edit-Menü setzen
        und sah sie in der Schritt-Liste nirgends wieder.
        """
        wc = self.wait_condition
        if not wc:
            return self._delay_str()
        zustand = "WEG" if wc.until_gone else "DA"
        pixel = f"({wc.pixel[0]},{wc.pixel[1]})"
        if wc.check_only:
            art = f"prüfe einmal ob Farbe {zustand} bei {pixel}"
        else:
            art = f"warte bis Farbe {zustand} bei {pixel}"
        if self.delay_before > 0:
            # "warte 2s, dann warte bis..." doppelt sich — die Vorlaufzeit sagt das schon.
            return f"warte {self._delay_str()}, dann {art.removeprefix('warte ')}"
        return art

    def _verify_str(self) -> str:
        """Was NACH der Aktion geprüft wird — leer, wenn nichts geprüft wird.

        Steht vor dem else-Teil: erst was nachgeprüft wird, dann was passiert, wenn
        die Prüfung scheitert. In der Reihenfolge liest man es auch.
        """
        vc = self.verify_condition
        if not vc:
            return ""
        zustand = "WEG" if vc.until_gone else "DA"
        return f" | PRUEF: ({vc.pixel[0]},{vc.pixel[1]}) {zustand}"

    def _else_str(self) -> str:
        """Hilfsfunktion für Else-Anzeige."""
        ec = self.else_config
        if not ec:
            return ""
        if ec.action == ELSE_SKIP:
            return " | ELSE: skip"
        elif ec.action == ELSE_SKIP_CYCLE:
            return " | ELSE: skip_cycle"
        elif ec.action == ELSE_RESTART:
            return " | ELSE: restart"
        elif ec.action == ELSE_CLICK:
            name = ec.name or f"({ec.x},{ec.y})"
            return f" | ELSE: klicke {name}"
        elif ec.action == ELSE_KEY:
            return f" | ELSE: Taste '{ec.key}'"
        return ""

    def _delay_str(self) -> str:
        """Hilfsfunktion für Delay-Anzeige (fest oder Bereich)."""
        if self.delay_max and self.delay_max > self.delay_before:
            return f"{self.delay_before:.0f}-{self.delay_max:.0f}s"
        return f"{self.delay_before:.0f}s"

    def get_actual_delay(self) -> float:
        """Gibt die tatsächliche Verzögerung zurück (bei Bereich: zufällig)."""
        if self.delay_max and self.delay_max > self.delay_before:
            return random.uniform(self.delay_before, self.delay_max)
        return self.delay_before


# Block-Typ eines Schritts: ein `SequenceStep` ist polymorph, welche Art er ist,
# steht in den gesetzten Feldern. Die Klassifikation liegt hier, weil Studio und
# Laufzeit sie brauchen und sich nicht kennen duerfen. Beschriftung und Farbe
# bleiben Anzeige (`BLOCK_LABELS`, `BLOCK_COLORS`).
BLOCK_SCREENSHOT = "screenshot"
BLOCK_BOSS_WATCHER = "boss_watcher"
BLOCK_BOSS_SCAN = "boss_scan"
BLOCK_ITEM_SCAN = "item_scan"
BLOCK_ICON_SCAN = "icon_scan"
BLOCK_KEY = "key"
BLOCK_WAIT = "wait"              # wait_only ohne Klick
BLOCK_WAIT_CLICK = "wait_click"  # wait_condition + Klick
BLOCK_CLICK = "click"            # einfacher Klick (evtl. mit Zeit-Delay)


def block_type(step: "SequenceStep") -> str:
    """Bestimmt den Block-Typ eines Schritts (gleiche Priorität wie der Executor).

    Die String-Diskriminatoren werden mit `is not None` geprüft, nicht per
    Truthiness: ein frisch gewählter Scan-/Tasten-Block hat zunächst einen leeren
    Namen und soll trotzdem als sein Typ angezeigt werden.
    """
    if step.screenshot_only:
        return BLOCK_SCREENSHOT
    if step.boss_watcher is not None:
        return BLOCK_BOSS_WATCHER
    if step.boss_scan is not None:
        return BLOCK_BOSS_SCAN
    if step.icon_scan is not None:
        return BLOCK_ICON_SCAN
    if step.item_scan is not None:
        return BLOCK_ITEM_SCAN
    if step.key_press is not None:
        return BLOCK_KEY
    if step.wait_only:
        return BLOCK_WAIT
    if step.wait_condition is not None:
        return BLOCK_WAIT_CLICK
    return BLOCK_CLICK


@dataclass
class LoopPhase:
    """Eine Loop-Phase mit eigenen Schritten und Wiederholungen."""
    name: str
    steps: list[SequenceStep] = field(default_factory=list)
    repeat: int = 1  # Wie oft diese Phase wiederholt wird
    scheduled_start: Optional[str] = None  # Startzeit z.B. "12:30" – wartet bis diese Uhrzeit

    def __str__(self) -> str:
        step_count = len(self.steps)
        pixel_triggers = sum(1 for s in self.steps if s.wait_condition)
        trigger_str = f" [Farb: {pixel_triggers}]" if pixel_triggers > 0 else ""
        time_str = f" [Start: {self.scheduled_start}]" if self.scheduled_start else ""
        return f"{self.name}: {step_count} Schritte x{self.repeat}{trigger_str}{time_str}"


@dataclass
class Sequence:
    """Eine Klick-Sequenz mit Init-, Loop- und End-Phase."""
    name: str
    init_steps: list[SequenceStep] = field(default_factory=list)   # Einmalig vor allen Zyklen
    loop_phases: list[LoopPhase] = field(default_factory=list)     # Mehrere Loop-Phasen
    end_steps: list[SequenceStep] = field(default_factory=list)    # Einmalig nach allen Zyklen
    total_cycles: int = 1  # 0 = unendlich, >0 = wie oft alle Loops durchlaufen werden
    # Freitext-Beschreibung (was macht die Sequenz?) — wird beim Laden/Listen und
    # beim Export angezeigt, damit man/Empfänger weiss worum es geht. Reines
    # Hilfsdatum, beeinflusst die Ausführung NICHT.
    description: str = ""
    # Eigener Punkt-Pool dieser Sequenz. Scans, die aus der Sequenz laufen,
    # loesen ihre Punkt-IDs ebenfalls gegen genau diesen Pool auf.
    points: list[ClickPoint] = field(default_factory=list)

    def __str__(self) -> str:
        init_count = len(self.init_steps)
        end_count = len(self.end_steps)
        loop_info = f"{len(self.loop_phases)} Loop(s)"
        if self.total_cycles == 0:
            loop_info += " ∞"
        elif self.total_cycles == 1:
            loop_info += " (1x)"
        else:
            loop_info += f" (x{self.total_cycles})"
        all_steps = self.init_steps + [s for lp in self.loop_phases for s in lp.steps] + self.end_steps
        pixel_triggers = sum(1 for s in all_steps if s.wait_condition)
        trigger_str = f" [Farb-Trigger: {pixel_triggers}]" if pixel_triggers > 0 else ""
        init_str = f"Init: {init_count}, " if init_count > 0 else ""
        end_str = f", End: {end_count}" if end_count > 0 else ""
        return f"{self.name} ({init_str}{loop_info}{end_str}){trigger_str}"

    def total_steps(self) -> int:
        return len(self.init_steps) + sum(len(lp.steps) for lp in self.loop_phases) + len(self.end_steps)


# =============================================================================
# ITEM-SCAN DATENKLASSEN
# =============================================================================
@dataclass
class ItemProfile:
    """Ein Item-Typ mit Marker-Farben und/oder Template-Matching."""
    name: str
    marker_colors: list[tuple[int, int, int]] = field(default_factory=list)  # Liste von (r,g,b) Marker-Farben
    # Kategorie für Prioritäts-Vergleich (z.B. "Hosen", "Jacken", "Juwelen")
    category: Optional[str] = None  # Wenn None, ist jedes Item seine eigene Kategorie
    priority: int = 1  # 1 = beste, höher = schlechter (innerhalb der Kategorie)
    # Referenz auf den Punkt, der nach dem Klick bestaetigt (Popup o.ae.);
    # `confirm_point` darunter ist der abgeleitete Wert aus resolve_scan_references().
    confirm_point_id: Optional[int] = None
    confirm_point: Optional[ClickPoint] = None  # abgeleitet: Punkt für die Bestätigung
    confirm_delay: float = 0.5  # Wartezeit vor Bestätigungs-Klick
    # Template Matching (optional - überschreibt marker_colors wenn gesetzt)
    template: Optional[str] = None  # Dateiname im Template-Ordner der Sequenz
    min_confidence: float = DEFAULT_MIN_CONFIDENCE  # Mindest-Konfidenz für Template-Match
    # Dasselbe Item kann in verschiedenen Inventar-Bereichen in unterschiedlich
    # grossen Slots vorkommen. `template` bleibt fuer bestehende JSON-Dateien und
    # Editoren die erste Vorlage; weitere, groessenpassende Aufnahmen stehen hier.
    template_variants: list[str] = field(default_factory=list)
    # Das Profil bleibt vollständig im Scan gespeichert, kann für den Lauf aber
    # vorübergehend geparkt werden. Hinter allen bisherigen Feldern, damit alte
    # positionale Konstruktionen ihre Bedeutung behalten.
    enabled: bool = True

    def template_names(self) -> list[str]:
        """Alle Vorlagen ohne leere oder doppelte Dateinamen."""
        ergebnis = []
        for name in [self.template, *self.template_variants]:
            if isinstance(name, str) and name and name not in ergebnis:
                ergebnis.append(name)
        return ergebnis

    def __str__(self) -> str:
        vorlagen = self.template_names()
        if vorlagen:
            anzahl = f" +{len(vorlagen) - 1} Variante(n)" if len(vorlagen) > 1 else ""
            template_str = f"Template: {vorlagen[0]}{anzahl} (≥{self.min_confidence:.0%})"
        else:
            colors_str = ", ".join([f"RGB{c}" for c in self.marker_colors[:3]])
            if len(self.marker_colors) > 3:
                colors_str += f" (+{len(self.marker_colors)-3})"
            template_str = colors_str if colors_str else "keine Marker"
        confirm_str = f" → ({self.confirm_point.x},{self.confirm_point.y})" if self.confirm_point else ""
        category_str = f" [{self.category}]" if self.category else ""
        return f"[P{self.priority}]{category_str} {self.name}: {template_str}{confirm_str}"


@dataclass
class ItemSlot:
    """Ein Slot wo Items erscheinen können."""
    name: str
    scan_region: tuple[int, int, int, int]  # (x1, y1, x2, y2) Bereich zum Scannen
    click_pos: tuple[int, int]              # (x, y) Wo geklickt werden soll
    slot_color: Optional[tuple[int, int, int]] = None  # RGB-Farbe des leeren Slots
    # Stabile Anzeige-ID — anders als bei ClickPoint KEINE Referenz (der Name
    # bleibt der Schlüssel in slot_names/item_names), nur damit die Nummer im
    # Studio beim Aus- und Wieder-Einschalten nicht auf einen anderen Slot
    # springt. 0 heißt „noch nicht vergeben" (Altbestand);
    # vergeben wird beim ersten Laden im Studio.
    id: int = 0
    # Der Slot bleibt mit Fläche, Klickpunkt und ID im Scan erhalten, kann für
    # den Lauf aber gezielt geparkt werden. Das ist kein zweiter Besitzbegriff:
    # er gehört weiterhin genau diesem Scan, nur `enabled=False` überspringt ihn.
    # Hinter `id`, damit bestehende positionale Aufrufe kompatibel bleiben.
    enabled: bool = True

    def __str__(self) -> str:
        r = self.scan_region
        color_str = f", Hintergrund: RGB{self.slot_color}" if self.slot_color else ""
        return f"{self.name}: Scan ({r[0]},{r[1]})-({r[2]},{r[3]}){color_str}"


@dataclass
class ItemScanConfig:
    """Konfiguration für Item-Erkennung und -Vergleich.

    Slots und Items gehören diesem Scan und werden vollständig in seiner Datei
    gespeichert. Gleichnamige Einträge anderer Scans sind andere Objekte.
    """
    name: str
    slots: list[ItemSlot] = field(default_factory=list)
    items: list[ItemProfile] = field(default_factory=list)
    color_tolerance: int = 40  # Farbtoleranz für Erkennung
    # Opt-in: unbekannte Slot-Inhalte beim Scannen automatisch als neue globale
    # Items lernen (Kategorie 'Auto', wird NICHT geklickt).
    learn_unknown: bool = False
    # Slots von hinten nach vorn abarbeiten. Sinnvoll, wenn das Spiel den Bestand
    # nach vorn aufrueckt. Gehoert zum Scan, nicht in die Config: sonst gaelte die
    # Richtung fuer alle Spiele gleichzeitig.
    reverse: bool = False
    # Aufnahmequelle des Inventars. Kein HWND: der gilt nur bis zum Schliessen des
    # Fensters. Titel + Instanz finden es beim naechsten Start wieder, das
    # Referenzrechteck macht die Slot-Koordinaten dazu relativ.
    capture_window_title: Optional[str] = None
    capture_window_index: int = 0
    capture_window_rect: Optional[tuple[int, int, int, int]] = None
    owner_sequence: str = field(default="", repr=False, compare=False)

    @property
    def slot_names(self) -> list[str]:
        """Abgeleitete Namen; die Objekte selbst sind die einzige Wahrheit."""
        return [slot.name for slot in self.slots]

    @slot_names.setter
    def slot_names(self, names) -> None:
        wanted = set(names or [])
        self.slots = [slot for slot in self.slots if slot.name in wanted]

    @property
    def item_names(self) -> list[str]:
        """Abgeleitete Namen; die Objekte selbst sind die einzige Wahrheit."""
        return [item.name for item in self.items]

    @item_names.setter
    def item_names(self, names) -> None:
        wanted = set(names or [])
        self.items = [item for item in self.items if item.name in wanted]

    def sync_names(self) -> None:
        """Kompatibler No-op: es gibt keine zweite Namens-Wahrheit mehr."""

    def __str__(self) -> str:
        learn_str = " [Auto-Lernen]" if self.learn_unknown else ""
        return (f"{self.name} ({len(self.slots)} Slots, "
                f"{len(self.items)} Items){learn_str}")


# =============================================================================
# BOSS-SCAN DATENKLASSEN
# =============================================================================
@dataclass
class BossProfile:
    """Ein Boss-Typ mit Erkennungsmethode und zugeordneter Aktion."""
    name: str
    marker_colors: list[tuple[int, int, int]] = field(default_factory=list)  # Farb-Marker
    template: Optional[str] = None              # Template-Bild der Sequenz
    min_confidence: float = DEFAULT_MIN_CONFIDENCE  # Für Template-Matching
    # Aktion wenn dieser Boss erkannt wird:
    action: str = BOSS_ACTION_SCAN              # "item_scan", "click", "key", "skip", "skip_cycle", "restart"
    action_scan: Optional[str] = None           # Name des Item-Scans (wenn action="item_scan")
    action_scan_mode: str = SCAN_MODE_ALL       # Scan-Modus ("all", "best", "every")
    # Referenz auf den Klick-Punkt (wenn action="click"). Gespeichert wird die ID,
    # action_x/y sind abgeleitet — siehe Block bei ElseConfig.
    action_point_id: Optional[int] = None
    action_x: int = 0                           # abgeleitet: Klick-X
    action_y: int = 0                           # abgeleitet: Klick-Y
    action_key: Optional[str] = None            # Taste (wenn action="key")
    action_delay: float = 0                     # Verzögerung vor Aktion

    def __str__(self) -> str:
        detect_parts = []
        if self.template:
            detect_parts.append(f"Template: {self.template} (≥{self.min_confidence:.0%})")
        if self.marker_colors:
            colors_str = ", ".join([f"RGB{c}" for c in self.marker_colors[:2]])
            if len(self.marker_colors) > 2:
                colors_str += f" (+{len(self.marker_colors)-2})"
            detect_parts.append(colors_str)
        detect_str = " + ".join(detect_parts) if detect_parts else "keine Erkennung"

        if self.action == BOSS_ACTION_SCAN:
            mode_strs = {SCAN_MODE_ALL: "alle", SCAN_MODE_BEST: "bestes", SCAN_MODE_EVERY: "jedes"}
            action_str = f"→ Scan '{self.action_scan}' ({mode_strs.get(self.action_scan_mode, self.action_scan_mode)})"
        elif self.action == BOSS_ACTION_CLICK:
            action_str = f"→ Klick ({self.action_x},{self.action_y})"
        elif self.action == BOSS_ACTION_KEY:
            action_str = f"→ Taste '{self.action_key}'"
        elif self.action == BOSS_ACTION_SKIP:
            action_str = "→ überspringen"
        elif self.action == BOSS_ACTION_SKIP_CYCLE:
            action_str = "→ Zyklus überspringen"
        elif self.action == BOSS_ACTION_RESTART:
            action_str = "→ Neustart"
        else:
            action_str = f"→ {self.action}"
        return f"{self.name}: {detect_str} {action_str}"


@dataclass
class BossScanConfig:
    """Konfiguration für Boss-Erkennung mit bedingten Aktionen."""
    name: str
    scan_region: tuple[int, int, int, int] = (0, 0, 100, 100)  # Feste Region wo der Boss erscheint
    bosses: list[BossProfile] = field(default_factory=list)      # Erkennbare Bosse (Reihenfolge = Priorität)
    color_tolerance: int = 30                                     # Farbtoleranz für Marker
    default_action: str = BOSS_ACTION_SKIP                        # Fallback wenn kein Boss erkannt
    default_scan: Optional[str] = None                            # Fallback Item-Scan
    # LLM Vision Erkennung (optional, zusätzlich zu Template/Marker)
    use_llm: bool = False                                         # LLM für Erkennung verwenden
    llm_fallback: bool = True                                     # LLM nur als Fallback (wenn Template/Marker nichts finden)
    # OCR-Texterkennung (optional, schnelle Alternative zu LLM)
    use_ocr: bool = False                                         # OCR für Boss-Name-Erkennung
    ocr_fallback: bool = True                                     # OCR nur als Fallback
    owner_sequence: str = field(default="", repr=False, compare=False)

    def __str__(self) -> str:
        r = self.scan_region
        tags = []
        if self.use_llm:
            tags.append("LLM")
        if self.use_ocr:
            tags.append("OCR")
        tag_str = f" [{'+'.join(tags)}]" if tags else ""
        return f"{self.name} ({len(self.bosses)} Bosse, Region ({r[0]},{r[1]})-({r[2]},{r[3]})){tag_str}"


@dataclass
class IconScanConfig:
    """Konfiguration für Icon-Erkennung in einer Region → Aktion.

    Erkennt EIN Symbol per Template-Matching oder Farb-Marker und führt bei Fund
    eine Aktion aus. Kein Item-Sammeln, kein LLM — bewusst schlank.
    """
    name: str
    scan_region: tuple[int, int, int, int] = (0, 0, 100, 100)  # Region in der gesucht wird
    template: Optional[str] = None                              # Template-Bild der Sequenz
    min_confidence: float = DEFAULT_MIN_CONFIDENCE              # Mindest-Konfidenz für Template-Match
    marker_colors: list[tuple[int, int, int]] = field(default_factory=list)  # Alternativ: Farb-Marker
    color_tolerance: int = 30                                   # Farbtoleranz für Marker
    action: str = ICON_ACTION_CLICK                            # Aktion bei Fund (Standard: klicken)
    # Referenz auf den Klick-Punkt (wenn action="click"); action_x/y sind abgeleitet.
    action_point_id: Optional[int] = None
    action_x: int = 0                                          # abgeleitet: Klick-X
    action_y: int = 0                                          # abgeleitet: Klick-Y
    action_key: Optional[str] = None                           # Taste (wenn action="key")
    action_delay: float = 0                                    # Verzögerung vor der Aktion
    owner_sequence: str = field(default="", repr=False, compare=False)

    def __str__(self) -> str:
        r = self.scan_region
        if self.template:
            detect = f"Template: {self.template} (≥{self.min_confidence:.0%})"
        elif self.marker_colors:
            detect = f"{len(self.marker_colors)} Marker"
        else:
            detect = "keine Erkennung"
        if self.action == ICON_ACTION_CLICK:
            act = f"→ Klick ({self.action_x},{self.action_y})"
        elif self.action == ICON_ACTION_KEY:
            act = f"→ Taste '{self.action_key}'"
        else:
            act = f"→ {self.action}"
        return f"{self.name} ({detect}, Region ({r[0]},{r[1]})-({r[2]},{r[3]})) {act}"


# =============================================================================
# SEQUENZ-AUFNAHME
# =============================================================================
# Ereignisarten der Aufnahme. Frueher war jedes Ereignis ein Linksklick und lag als
# nacktes (t, x, y, color)-Tupel in der Liste; seit auch Tastendruck, Mausrad und
# Farb-Warten mitgeschnitten werden, muss die Art mitgefuehrt werden.
REC_CLICK = "click"         # Linksklick an (x, y)
REC_KEY = "key"             # Tastendruck (key)
REC_SCROLL = "scroll"       # Mausrad an (x, y), scroll = Rasterstufen (+ = hoch)
# Warte-Marker: "ab hier warte ich". Hat BEWUSST keine eigene Stelle — beim Drücken
# parkt die Maus irgendwo, und diese Stelle waere Zufall. Er haengt sich an den
# naechsten Klick und laesst DEN auf seine eigene Farbe warten.
REC_WAIT_COLOR = "wait"
# Screenshot-Marker: "hier einen Screenshot machen". Anders als der Warte-Marker
# braucht er KEINE Folge-Aktion — er wird selbst zu einem eigenstaendigen
# Screenshot-Step an genau dieser Stelle der Zeitachse. `region` ist None
# (Vollbild) oder das aus zwei Ecken zusammengesetzte Rechteck.
REC_SCREENSHOT = "screenshot"
# Bereichs-Ecke: zwei davon ergeben EIN Rechteck. Ein Rechteck aufzuziehen braucht
# zwei Stellen, und mehr als einen Tastendruck gibt es waehrend der Aufnahme nicht —
# also zweimal derselbe Druck an zwei Mauspositionen. `bereiche_zusammenfassen()`
# faltet die Paare zu REC_SCREENSHOT-Ereignissen; danach existiert diese Art nicht mehr.
REC_REGION = "region"
# Beobachten ohne Klick: "warte, bis die Farbe UNTER der Maus da ist" — und dann NICHT
# hinklicken. Anders als beim Warte-Marker ist die Mausposition hier bewusst gewaehlt
# (man legt die Maus auf das Ding, das man beobachtet), deshalb bekommt er einen Punkt.
# Entspricht `wait pixel` im Sequenz-Editor.
REC_WATCH = "watch"
# Phasengrenze: "ab hier beginnt die naechste Phase". Erster Marker trennt INIT von
# LOOP, zweiter LOOP von END. Er wird selbst kein Schritt — er schneidet die fertige
# Schrittliste. Ohne ihn landet alles wie bisher in einer einzigen Loop-Phase.
REC_PHASE = "phase"


@dataclass
class RecordEvent:
    """Ein aufgezeichnetes Ereignis der Sequenz-Aufnahme.

    Rein transient: lebt nur in `AutoClickerState.recording_events` und wird nie
    gespeichert — `stop_recording()` baut daraus SequenceSteps und wirft die Liste weg.
    Deshalb steht das hier auch ohne Serialisierer und ohne Default-Tabelle.
    """
    kind: str
    t: float                                    # time.monotonic() beim Auslösen
    x: int = 0
    y: int = 0
    color: Optional[tuple[int, int, int]] = None
    key: Optional[str] = None                   # nur REC_KEY
    scroll: int = 0                             # nur REC_SCROLL, Rasterstufen
    # nur REC_SCREENSHOT: (x1, y1, x2, y2) oder None = Vollbild
    region: Optional[tuple[int, int, int, int]] = None

    def __str__(self) -> str:
        if self.kind == REC_KEY:
            return f"Taste '{self.key}'"
        if self.kind == REC_SCROLL:
            richtung = "hoch" if self.scroll > 0 else "runter"
            return f"Scroll {richtung} x{abs(self.scroll)} bei ({self.x}, {self.y})"
        if self.kind == REC_WAIT_COLOR:
            return "Warte-Marker (nächster Klick wartet auf seine Farbe)"
        if self.kind == REC_SCREENSHOT:
            if self.region:
                r = self.region
                return f"Screenshot ({r[0]},{r[1]})→({r[2]},{r[3]})"
            return "Screenshot (Vollbild)"
        if self.kind == REC_REGION:
            return f"Bereichs-Ecke ({self.x}, {self.y})"
        if self.kind == REC_WATCH:
            return f"Beobachte ({self.x}, {self.y}) ohne Klick"
        if self.kind == REC_PHASE:
            return "Phasengrenze (ab hier die nächste Phase)"
        return f"Klick ({self.x}, {self.y})"


# =============================================================================
# AUTOCLICKER STATE
# =============================================================================
@dataclass
class AutoClickerState:
    """Zustand des Autoclickers."""
    # Arbeitsansicht auf `active_sequence.points`; kein eigener Datenbestand.
    points: list[ClickPoint] = field(default_factory=list)

    # Manueller Modus: Sequenz Schritt für Schritt auf Bestätigung, Wartezeiten
    # übersprungen. Bewusst Laufzeit-Zustand statt Config - im Punkte-Menü
    # (CTRL+ALT+P -> 'manuell') umschaltbar. Mutation unter state.lock.
    step_mode: bool = False
    # Wurde der manuelle Modus im Studio eingeschaltet, kommen die vier
    # Entscheidungen über den Befehls-Briefkasten statt von stdin. Das Event
    # weckt den Worker; der String wird immer unter `state.lock` gelesen und
    # geschrieben. Der TUI-Modus bleibt davon unberührt.
    step_via_studio: bool = False
    step_command: str = ""
    step_command_event: threading.Event = field(default_factory=threading.Event)

    # Gespeicherte Sequenzen
    sequences: dict[str, Sequence] = field(default_factory=dict)

    # Globale Slots und Items (wiederverwendbar)
    global_slots: dict[str, ItemSlot] = field(default_factory=dict)
    global_items: dict[str, ItemProfile] = field(default_factory=dict)

    # Item-Scan Konfigurationen (verknüpft Slots + Items)
    item_scans: dict[str, ItemScanConfig] = field(default_factory=dict)
    # TUI-Arbeitskontext. `global_slots/items` sind nur Ansichten auf diesen Scan.
    active_item_scan: str = ""

    # Boss-Scan Konfigurationen (Boss erkennen → bedingte Aktion)
    boss_scans: dict[str, BossScanConfig] = field(default_factory=dict)

    # Globale Boss-Bibliothek: gilt zusätzlich in JEDEM Boss-Scan.
    # Lokale Bosse eines Scans haben bei Namensgleichheit Vorrang.
    global_bosses: list[BossProfile] = field(default_factory=list)

    # Icon-Scan Konfigurationen (Symbol/Icon erkennen → Aktion)
    icon_scans: dict[str, IconScanConfig] = field(default_factory=dict)

    # Aktive Sequenz
    active_sequence: Optional[Sequence] = None

    # Laufzeit-Status
    is_running: bool = False
    total_clicks: int = 0

    # Statistiken
    items_found: int = 0
    key_presses: int = 0
    skipped_cycles: int = 0
    restarts: int = 0
    timeouts: int = 0
    consecutive_timeouts: int = 0
    start_time: Optional[float] = None

    # Bereits geklickte Kategorien im aktuellen Zyklus mit bester Priorität
    # Dict: {kategorie: beste_priorität} - verhindert schlechtere Items derselben Kategorie
    clicked_categories: dict[str, int] = field(default_factory=dict)

    # Thread-sichere Events
    stop_event: threading.Event = field(default_factory=threading.Event)
    quit_event: threading.Event = field(default_factory=threading.Event)
    pause_event: threading.Event = field(default_factory=threading.Event)
    skip_event: threading.Event = field(default_factory=threading.Event)
    # Anders als skip_event (nur die laufende Wartezeit) verwirft dieses Event
    # den kompletten aktuellen Block samt Klick/Taste/Scan.
    skip_step_event: threading.Event = field(default_factory=threading.Event)
    restart_event: threading.Event = field(default_factory=threading.Event)
    skip_cycle_event: threading.Event = field(default_factory=threading.Event)
    finish_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    # Eigener Lock NUR für Maus/Tastatur-Eingaben (SetCursorPos + SendInput).
    # Garantiert echte Mutual-Exclusion zwischen Sequenz-Worker und dem
    # asynchronen LLM-Boss-Thread — verhindert interleaved Klicks an falscher
    # Position. WICHTIG: input_lock niemals nehmen während state.lock gehalten
    # wird (Deadlock-Gefahr — strikte Lock-Reihenfolge).
    input_lock: threading.Lock = field(default_factory=threading.Lock)

    # Flag für aktiven Countdown (verhindert Sequenz-Start durch CTRL+ALT+S)
    countdown_active: bool = False

    # Screenshot-Ordner für die aktuelle Sequenz-Session (z.B. "slots/Screenshots/2025-01-15_14-30-00")
    session_screenshots_dir: Optional[Path] = None

    # Session-Log (CSV) für die aktuelle Sequenz (None wenn deaktiviert)
    session_log: Optional[object] = None

    # Neu entdeckte Boss-Namen in dieser Session (zur Bestätigung am Ende)
    # Liste von (config_name, boss_name, quelle) Tupeln — quelle z.B. "LLM" oder "OCR"
    pending_new_bosses: list = field(default_factory=list)

    # Zeitpunkt der letzten Humanize-Break (Monotone Zeit)
    humanize_last_break: float = 0.0

    # LLM Async-Thread (Boss-Scan/Watcher läuft im Hintergrund)
    llm_thread: Optional[threading.Thread] = None
    llm_action_event: threading.Event = field(default_factory=threading.Event)

    # Set für einmalige Konfigurations-Warnungen pro Worker-Lauf (z.B. "use_llm aber !llm_enabled").
    # Wird beim Sequenz-Start in sequence_worker geleert. Zugriff unter state.lock.
    warned_inconsistencies: set = field(default_factory=set)

    # Konfiguration (thread-safe über lock)
    config: AppConfig = field(default_factory=AppConfig)

    # Sequenz-Aufnahme (Maus-Hook + Tastatur-Hook)
    recording_active: bool = False
    # Pausiert die laufende Aufnahme: Ereignisse werden ignoriert, ohne die Aufnahme
    # zu beenden (z.B. um im Spiel zu navigieren). Toggle via CTRL+ALT+H.
    recording_paused: bool = False
    # Liste von RecordEvent. Zugriff unter state.lock - der Maus- und der
    # Tastatur-Hook schreiben aus der Message-Pump, die Hotkey-Handler lesen.
    recording_events: list = field(default_factory=list)
    # Vorgaben einer im Studio gestarteten Aufnahme. Leer bedeutet: klassischer
    # TUI-Weg mit den bisherigen Konsolenfragen beim Stoppen.
    recording_ui_name: str = ""
    recording_ui_cycles: int = 0
    recording_ui_description: str = ""

    # Punkte nachklicken (Kalibrier-Runde, Maus-Hook wie bei der Aufnahme).
    # Rein transient: die Runde beschreibt einen Vorgang, keinen Bestand — sie
    # wird nie gespeichert. Was sie ERGIBT, steht danach in sequence.json.
    nachklick_aktiv: bool = False
    # Pausiert: Klicks gehen durch, ohne einen Punkt zu setzen. Dafür da, dass
    # man zwischendurch im Spiel navigieren kann (Dialog wegklicken, scrollen),
    # ohne dass die Runde einen Punkt verbraucht.
    nachklick_pausiert: bool = False
    # Die Punkt-IDs in der Reihenfolge, in der die Sequenz sie klickt.
    nachklick_punkte: list = field(default_factory=list)
    nachklick_index: int = 0
    # Was die Runde ERGEBEN hat: (Punkt-ID, alt, neu, Farbe) je gesetztem Punkt.
    # Das ist kein Protokoll, sondern das Ergebnis selbst — die Punkte werden
    # erst beim Übernehmen daraus geschrieben. Bis dahin ist ein Abbruch
    # folgenlos, und „nichts passiert" bleibt von „alles gleich geblieben"
    # unterscheidbar.
    nachklick_gesetzt: list = field(default_factory=list)
    # Was die Runde GETAN hat: (Punkt-ID, Art) je erledigtem Punkt, in der
    # Reihenfolge des Durchgangs. Art ist "passt", "gesetzt", "uebersprungen"
    # oder "fehlt". Ableiten liesse sich das NICHT: ein bestaetigter Punkt
    # (innerhalb PASST_TOLERANZ) landet bewusst nicht in `nachklick_gesetzt`,
    # und ohne diese Liste saehe er im Fenster genauso aus wie ein
    # uebersprungener. Reine Anzeige — das Ergebnis steht weiterhin in
    # `nachklick_gesetzt`.
    nachklick_verlauf: list = field(default_factory=list)
    # Wie viele Stellen die Runde NICHT erreicht (beobachtete Pixel, ELSE,
    # Rad). Steht im Banner und im Studio — eine Runde, die schweigt, was sie
    # auslaesst, sieht vollstaendiger aus als sie ist.
    nachklick_sonstige: int = 0
    # Der Fenstertitel, in dem ein Klick als Punkt zählt (aus
    # `window_focus_title`). **Ohne den frisst die Runde jeden Klick** — auch den
    # auf das Studio-Fenster, die Konsole oder ein Schliessen-Kreuz, und schreibt
    # dessen Stelle in den Punkt. Leer = kein Filter (Fenster nicht gefunden).
    nachklick_ziel: str = ""
    # Woher die Reihenfolge kam — nur für die Anzeige. Die Runde arbeitet auf
    # Punkten; welche Sequenz sie sortiert hat, ändert daran nichts (und die
    # geladene Sequenz wechselt dadurch ausdrücklich NICHT).
    nachklick_name: str = ""
    # Die Runde darf aus dem Studio eine andere als die aktive Sequenz erhalten.
    # Ihr eigener Punkt-Pool bleibt deshalb als expliziter Laufzeitkontext hier.
    nachklick_sequence: Optional[Sequence] = None
