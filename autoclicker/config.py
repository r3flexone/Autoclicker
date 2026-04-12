"""
Konfiguration für den Autoclicker.
Lädt und speichert config.json mit Standard-Werten.
"""

import json
import logging
from dataclasses import dataclass, fields, asdict
from pathlib import Path
from typing import Optional, Union

from .utils import col, ok, warn, err

# Logger
logger = logging.getLogger("autoclicker")

# =============================================================================
# KONFIGURATION
# =============================================================================
CONFIG_FILE = "config.json"
SEQUENCES_DIR: str = "sequences"       # Ordner für gespeicherte Sequenzen


@dataclass
class AppConfig:
    """Typisierte Konfiguration für den Autoclicker.
    Feld-Reihenfolge bestimmt die Reihenfolge in config.json."""
    # === KLICK-EINSTELLUNGEN ===
    clicks_per_point: int = 1                       # Anzahl Klicks pro Punkt
    max_total_clicks: Optional[int] = None          # None = unendlich
    click_move_delay: float = 0.01                  # Pause zwischen Mausbewegung und Klick (Sekunden)
    post_click_delay: float = 0.05                  # Pause NACH dem Klick bevor Maus weiterbewegt werden darf

    # === SICHERHEIT ===
    failsafe_enabled: bool = True                   # Fail-Safe: Maus in Ecke stoppt alles
    failsafe_x: int = 5                             # Fail-Safe X-Bereich (Maus x <= Wert)
    failsafe_y: int = 5                             # Fail-Safe Y-Bereich (Maus y <= Wert)

    # === FARB-/PIXEL-ERKENNUNG ===
    color_tolerance: int = 0                        # Farbtoleranz für Item-Scan (0 = exakt)
    pixel_wait_tolerance: int = 10                  # Toleranz für Pixel-Trigger
    pixel_wait_timeout: int = 300                   # Timeout für Pixel-Trigger in Sekunden (0 = unendlich)
    pixel_timeout_action: str = "skip_cycle"        # Aktion bei Timeout: "skip_cycle", "restart", "stop"
    pixel_check_interval: float = 1                 # Prüf-Intervall für Farbe in Sekunden
    max_consecutive_timeouts: int = 5               # Nach X aufeinanderfolgenden Timeouts → Notbremse (0 = deaktiviert)
    consecutive_timeout_action: str = "stop"        # Notbremse: "stop" = Sequenz stoppen, "quit" = Menü beenden, "exit" = Prozess killen
    scan_pixel_step: int = 2                        # Pixel-Schrittweite bei Farbsuche (1=genauer, 2=schneller)
    show_pixel_delay: float = 0.3                   # Wie lange Pixel-Position angezeigt wird (Sekunden)

    # === ITEM-SCAN EINSTELLUNGEN ===
    scan_reverse: bool = True                       # True = Slots rückwärts scannen (4,3,2,1)
    scan_click_immediate: bool = False              # True = Scan→Klick pro Slot
    scan_park_mouse: Union[bool, list] = False      # [x, y] = Maus vor Scan parken, False = nicht
    scan_slot_delay: float = 0.1                    # Pause zwischen Slot-Scans in Sekunden
    item_click_delay: float = 1.0                   # Pause nach Item-Klick in Sekunden
    marker_count: int = 5                           # Anzahl Marker-Farben beim Item-Lernen
    require_all_markers: bool = True                # True = ALLE Marker müssen gefunden werden
    min_markers_required: int = 2                   # Minimum Marker (nur wenn require_all_markers=False)
    slot_hsv_tolerance: int = 25                    # HSV-Toleranz für Slot-Erkennung
    slot_inset: int = 10                            # Pixel-Einzug vom Slot-Rand
    slot_color_distance: int = 25                   # Farbdistanz für Hintergrund-Ausschluss
    default_min_confidence: float = 0.8             # Standard-Konfidenz für Template-Matching (80%)
    default_confirm_delay: float = 0.5              # Standard-Wartezeit vor Bestätigungs-Klick

    # === TIMING ===
    pause_check_interval: float = 0.5               # Prüf-Intervall während Pause (Sekunden)

    # === DEBUG-EINSTELLUNGEN ===
    debug_mode: bool = False                        # Zeigt Schritte VOR Start + wartet auf Enter
    debug_detection: bool = False                   # Alle Ausgaben persistent (nicht überschrieben)
    show_pixel_position: bool = False               # Maus kurz zum Prüf-Pixel bewegen beim Start
    debug_save_templates: bool = False              # Speichert Scan+Template in items/debug/

    # Erlaubte Werte für String-Optionen
    _VALID_TIMEOUT_ACTIONS = {"skip_cycle", "restart", "stop"}
    _VALID_CONSEC_ACTIONS = {"stop", "quit", "exit"}

    def __post_init__(self):
        """Validiert Config-Werte nach Erstellung."""
        warnings = []
        # Numerische Grenzen (negative Werte korrigieren)
        if self.clicks_per_point < 1:
            warnings.append(f"clicks_per_point={self.clicks_per_point} → 1")
            self.clicks_per_point = 1
        if self.pixel_wait_timeout < 0:
            warnings.append(f"pixel_wait_timeout={self.pixel_wait_timeout} → 0")
            self.pixel_wait_timeout = 0
        if self.pixel_check_interval <= 0:
            warnings.append(f"pixel_check_interval={self.pixel_check_interval} → 0.1")
            self.pixel_check_interval = 0.1
        if self.pause_check_interval <= 0:
            warnings.append(f"pause_check_interval={self.pause_check_interval} → 0.1")
            self.pause_check_interval = 0.1
        if self.max_consecutive_timeouts < 0:
            warnings.append(f"max_consecutive_timeouts={self.max_consecutive_timeouts} → 0")
            self.max_consecutive_timeouts = 0
        if self.default_min_confidence < 0 or self.default_min_confidence > 1:
            warnings.append(f"default_min_confidence={self.default_min_confidence} → 0.8")
            self.default_min_confidence = 0.8
        if self.marker_count < 1:
            warnings.append(f"marker_count={self.marker_count} → 1")
            self.marker_count = 1
        # String-Werte validieren
        if self.pixel_timeout_action not in self._VALID_TIMEOUT_ACTIONS:
            warnings.append(f"pixel_timeout_action='{self.pixel_timeout_action}' → 'skip_cycle'")
            self.pixel_timeout_action = "skip_cycle"
        if self.consecutive_timeout_action not in self._VALID_CONSEC_ACTIONS:
            warnings.append(f"consecutive_timeout_action='{self.consecutive_timeout_action}' → 'stop'")
            self.consecutive_timeout_action = "stop"
        if warnings:
            for w in warnings:
                print(warn(f"Config-Wert korrigiert: {w}"))

    def to_dict(self) -> dict:
        """Konvertiert zu JSON-serialisierbarem dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'AppConfig':
        """Erstellt AppConfig aus einem dict (ignoriert unbekannte Keys)."""
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


# Abwärtskompatibel: DEFAULT_CONFIG als dict (für JSON-Serialisierung)
DEFAULT_CONFIG = AppConfig().to_dict()


def load_config() -> AppConfig:
    """Lädt Konfiguration aus config.json oder erstellt Standard-Config."""
    config_path = Path(CONFIG_FILE)

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                config = AppConfig.from_dict(loaded)

                # Prüfe ob neue Optionen hinzugefügt wurden
                missing_keys = set(DEFAULT_CONFIG.keys()) - set(loaded.keys())
                if missing_keys:
                    save_config(config)
                    print(ok(f"Config geladen + {len(missing_keys)} neue Option(en) ergänzt: {', '.join(missing_keys)}"))
                else:
                    print(col(f"[CONFIG] Geladen aus {CONFIG_FILE}", "green"))
                return config
        except (json.JSONDecodeError, IOError) as e:
            print(warn(f"Config konnte nicht geladen werden: {e}"))
            print(col("[CONFIG] Verwende Standard-Konfiguration", "yellow"))
    else:
        # Erstelle Standard-Config-Datei
        save_config(AppConfig())
        print(ok(f"Standard-Konfiguration erstellt: {CONFIG_FILE}"))

    return AppConfig()


def save_config(config: AppConfig) -> None:
    """Speichert Konfiguration in config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(err(f"Config konnte nicht gespeichert werden: {e}"))


# Konfiguration laden (wird beim Import ausgeführt)
CONFIG: AppConfig = load_config()

# Konfig-Werte als Variablen (nur Werte die sich zur Laufzeit nicht ändern)
# ACHTUNG: Werte die sich durch Factory Reset ändern können, immer über
# state.config abrufen statt über Modul-Variablen!
DEFAULT_MIN_CONFIDENCE: float = CONFIG.default_min_confidence
