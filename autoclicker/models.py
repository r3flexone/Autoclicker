"""
Datenklassen für den Autoclicker.
Definiert alle Datenstrukturen wie ClickPoint, SequenceStep, Sequence, etc.
"""

import random
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import AppConfig, DEFAULT_MIN_CONFIDENCE


# =============================================================================
# STRING-KONSTANTEN (zentral definiert, verhindert Tippfehler)
# =============================================================================
# ElseConfig.action
ELSE_SKIP = "skip"
ELSE_SKIP_CYCLE = "skip_cycle"
ELSE_RESTART = "restart"
ELSE_CLICK = "click"
ELSE_KEY = "key"
VALID_ELSE_ACTIONS = {ELSE_SKIP, ELSE_SKIP_CYCLE, ELSE_RESTART, ELSE_CLICK, ELSE_KEY}

# pixel_timeout_action (Config)
TIMEOUT_SKIP_CYCLE = "skip_cycle"
TIMEOUT_RESTART = "restart"
TIMEOUT_STOP = "stop"

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
BOSS_ACTION_SCAN = "item_scan"      # Item-Scan ausführen
BOSS_ACTION_CLICK = "click"          # Punkt klicken
BOSS_ACTION_KEY = "key"              # Taste drücken
BOSS_ACTION_SKIP = "skip"            # Schritt überspringen
BOSS_ACTION_SKIP_CYCLE = "skip_cycle"  # Zyklus überspringen
BOSS_ACTION_RESTART = "restart"      # Sequenz neustarten
VALID_BOSS_ACTIONS = {BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY,
                      BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART}


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

    def __str__(self) -> str:
        if self.name:
            return f"#{self.id} {self.name} ({self.x}, {self.y})"
        return f"#{self.id} ({self.x}, {self.y})"


@dataclass
class ElseConfig:
    """Fallback-Aktion wenn eine Bedingung (Farbe/Scan) fehlschlägt."""
    action: str                          # "skip", "skip_cycle", "restart", "click", "key"
    x: int = 0                           # X für Fallback-Klick
    y: int = 0                           # Y für Fallback-Klick
    delay: float = 0                     # Delay vor Fallback
    key: Optional[str] = None            # Taste für Fallback
    name: str = ""                       # Name des Fallback-Punkts


@dataclass
class WaitCondition:
    """Warten auf eine Farbe an einer Pixel-Position."""
    pixel: tuple[int, int]               # (x, y) Position zum Prüfen
    color: tuple[int, int, int]          # (r, g, b) Farbe die erscheinen soll
    until_gone: bool = False             # True = warte bis Farbe WEG ist


@dataclass
class SequenceStep:
    """Ein Schritt in einer Sequenz: Erst warten/prüfen, DANN klicken."""
    x: int                # X-Koordinate (direkt gespeichert)
    y: int                # Y-Koordinate (direkt gespeichert)
    delay_before: float   # Wartezeit in Sekunden VOR diesem Klick (0 = sofort)
    name: str = ""        # Optionaler Name des Punktes
    # Optional: Warten auf Farbe statt Zeit (VOR dem Klick)
    wait_condition: Optional[WaitCondition] = None
    # Optional: Item-Scan ausführen statt direktem Klick
    item_scan: Optional[str] = None      # Name des Item-Scans
    item_scan_mode: str = "all"          # "all" = bestes pro Kategorie, "best" = nur 1 Item total
    # Optional: Nur warten, nicht klicken
    wait_only: bool = False              # True = nur warten, kein Klick
    # Optional: Zufällige Verzögerung (delay_before bis delay_max)
    delay_max: Optional[float] = None    # None = feste Zeit, sonst Bereich
    # Optional: Tastendruck statt Mausklick
    key_press: Optional[str] = None      # z.B. "enter", "space", "f1"
    # Optional: Fallback/Else-Aktion wenn Bedingung fehlschlägt
    else_config: Optional[ElseConfig] = None
    # Optional: Boss-Scan ausführen (erkennt Boss → bedingte Aktion)
    boss_scan: Optional[str] = None      # Name der BossScanConfig
    # Optional: Screenshot machen (kein Klick, kein Scan)
    screenshot_only: bool = False        # True = nur Screenshot, kein Klick
    screenshot_region: Optional[tuple[int, int, int, int]] = None  # (x1,y1,x2,y2) oder None = Vollbild

    def __str__(self) -> str:
        else_str = self._else_str()
        if self.screenshot_only:
            region = self.screenshot_region
            if region:
                return f"SCREENSHOT ({region[0]},{region[1]})→({region[2]},{region[3]})"
            return "SCREENSHOT (Vollbild)"
        if self.key_press:
            delay_str = self._delay_str()
            return f"{delay_str} → drücke Taste '{self.key_press}'{else_str}"
        if self.boss_scan:
            return f"BOSS-SCAN '{self.boss_scan}'{else_str}"
        if self.item_scan:
            mode_strs = {SCAN_MODE_ALL: "bestes/Kategorie", SCAN_MODE_BEST: "1 bestes", SCAN_MODE_EVERY: "JEDES"}
            mode_str = mode_strs.get(self.item_scan_mode, self.item_scan_mode)
            return f"SCAN '{self.item_scan}' → klicke {mode_str}{else_str}"
        wc = self.wait_condition
        if self.wait_only:
            if wc:
                gone_str = "WEG ist" if wc.until_gone else "DA ist"
                return f"WARTE bis Farbe {gone_str} bei ({wc.pixel[0]},{wc.pixel[1]}) (kein Klick){else_str}"
            return f"WARTE {self._delay_str()} (kein Klick)"
        pos_str = f"{self.name} ({self.x}, {self.y})" if self.name else f"({self.x}, {self.y})"
        if wc:
            gone_str = "bis Farbe WEG" if wc.until_gone else "auf Farbe"
            delay_str = self._delay_str()
            if self.delay_before > 0:
                return f"warte {delay_str}, dann {gone_str} bei ({wc.pixel[0]},{wc.pixel[1]}) → klicke {pos_str}{else_str}"
            return f"warte {gone_str} bei ({wc.pixel[0]},{wc.pixel[1]}) → klicke {pos_str}{else_str}"
        elif self.delay_before > 0:
            return f"warte {self._delay_str()} → klicke {pos_str}"
        else:
            return f"sofort → klicke {pos_str}"

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
    confirm_point: Optional[ClickPoint] = None  # ClickPoint für Bestätigung nach Klick
    confirm_delay: float = 0.5  # Wartezeit vor Bestätigungs-Klick
    # Template Matching (optional - überschreibt marker_colors wenn gesetzt)
    template: Optional[str] = None  # Dateiname des Template-Bildes (in items/templates/)
    min_confidence: float = DEFAULT_MIN_CONFIDENCE  # Mindest-Konfidenz für Template-Match

    def __str__(self) -> str:
        if self.template:
            template_str = f"Template: {self.template} (≥{self.min_confidence:.0%})"
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

    def __str__(self) -> str:
        r = self.scan_region
        color_str = f", Hintergrund: RGB{self.slot_color}" if self.slot_color else ""
        return f"{self.name}: Scan ({r[0]},{r[1]})-({r[2]},{r[3]}){color_str}"


@dataclass
class ItemScanConfig:
    """Konfiguration für Item-Erkennung und -Vergleich."""
    name: str
    slots: list[ItemSlot] = field(default_factory=list)      # Wo gescannt wird
    items: list[ItemProfile] = field(default_factory=list)   # Welche Items erkannt werden
    color_tolerance: int = 40  # Farbtoleranz für Erkennung

    def __str__(self) -> str:
        return f"{self.name} ({len(self.slots)} Slots, {len(self.items)} Items)"


# =============================================================================
# BOSS-SCAN DATENKLASSEN
# =============================================================================
@dataclass
class BossProfile:
    """Ein Boss-Typ mit Erkennungsmethode und zugeordneter Aktion."""
    name: str
    marker_colors: list[tuple[int, int, int]] = field(default_factory=list)  # Farb-Marker
    template: Optional[str] = None              # Template-Bild (in items/templates/)
    min_confidence: float = DEFAULT_MIN_CONFIDENCE  # Für Template-Matching
    # Aktion wenn dieser Boss erkannt wird:
    action: str = BOSS_ACTION_SCAN              # "item_scan", "click", "key", "skip", "skip_cycle", "restart"
    action_scan: Optional[str] = None           # Name des Item-Scans (wenn action="item_scan")
    action_scan_mode: str = SCAN_MODE_ALL       # Scan-Modus ("all", "best", "every")
    action_x: int = 0                           # Klick-X (wenn action="click")
    action_y: int = 0                           # Klick-Y (wenn action="click")
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

    def __str__(self) -> str:
        r = self.scan_region
        return f"{self.name} ({len(self.bosses)} Bosse, Region ({r[0]},{r[1]})-({r[2]},{r[3]}))"


# =============================================================================
# AUTOCLICKER STATE
# =============================================================================
@dataclass
class AutoClickerState:
    """Zustand des Autoclickers."""
    # Punkte-Pool (wiederverwendbar)
    points: list[ClickPoint] = field(default_factory=list)

    # Gespeicherte Sequenzen
    sequences: dict[str, Sequence] = field(default_factory=dict)

    # Globale Slots und Items (wiederverwendbar)
    global_slots: dict[str, ItemSlot] = field(default_factory=dict)
    global_items: dict[str, ItemProfile] = field(default_factory=dict)

    # Item-Scan Konfigurationen (verknüpft Slots + Items)
    item_scans: dict[str, ItemScanConfig] = field(default_factory=dict)

    # Boss-Scan Konfigurationen (Boss erkennen → bedingte Aktion)
    boss_scans: dict[str, BossScanConfig] = field(default_factory=dict)

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
    restart_event: threading.Event = field(default_factory=threading.Event)
    skip_cycle_event: threading.Event = field(default_factory=threading.Event)
    finish_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # Flag für geplanten Start (überspringt Debug-Enter-Prompt)
    scheduled_start: bool = False

    # Flag für aktiven Countdown (verhindert Sequenz-Start durch CTRL+ALT+S)
    countdown_active: bool = False

    # Screenshot-Ordner für die aktuelle Sequenz-Session (z.B. "slots/Screenshots/2025-01-15_14-30-00")
    session_screenshots_dir: Optional[Path] = None

    # Konfiguration (thread-safe über lock)
    config: AppConfig = field(default_factory=AppConfig)
