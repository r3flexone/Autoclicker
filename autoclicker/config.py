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
    click_per_point: int = 1                        # Anzahl Klicks pro Punkt
    click_max_total: Optional[int] = None           # None = unendlich
    click_move_delay: float = 0.01                  # Pause zwischen Mausbewegung und Klick (Sekunden)
    click_post_delay: float = 0.05                  # Pause NACH dem Klick bevor Maus weiterbewegt werden darf

    # === SICHERHEIT ===
    failsafe_enabled: bool = True                   # Fail-Safe: Maus in Ecke stoppt alles
    failsafe_x: int = 5                             # Fail-Safe X-Bereich (Maus x <= Wert)
    failsafe_y: int = 5                             # Fail-Safe Y-Bereich (Maus y <= Wert)

    # === PIXEL-ERKENNUNG ===
    pixel_color_tolerance: int = 0                  # Farbtoleranz für Scan (0 = exakt)
    pixel_wait_tolerance: int = 10                  # Toleranz für Pixel-Trigger
    pixel_wait_timeout: int = 300                   # Timeout für Pixel-Trigger in Sekunden (0 = unendlich)
    pixel_timeout_action: str = "skip_cycle"        # Aktion bei Timeout: "skip_cycle", "restart", "stop"
    pixel_check_interval: float = 1                 # Prüf-Intervall für Farbe in Sekunden
    pixel_max_consecutive_timeouts: int = 5         # Nach X aufeinanderfolgenden Timeouts → Notbremse (0 = deaktiviert)
    pixel_consecutive_action: str = "stop"          # Notbremse: "stop", "quit", "exit"
    pixel_scan_step: int = 2                        # Pixel-Schrittweite bei Farbsuche (1=genauer, 2=schneller)
    pixel_show_delay: float = 0.3                   # Wie lange Pixel-Position angezeigt wird (Sekunden)

    # === SCAN-EINSTELLUNGEN ===
    scan_reverse: bool = True                       # True = Slots rückwärts scannen (4,3,2,1)
    scan_click_immediate: bool = False              # True = Scan→Klick pro Slot
    scan_park_mouse: Union[bool, list] = False      # [x, y] = Maus vor Scan parken, False = nicht
    scan_slot_delay: float = 0.1                    # Pause zwischen Slot-Scans in Sekunden
    scan_item_click_delay: float = 1.0              # Pause nach Item-Klick in Sekunden
    scan_marker_count: int = 5                      # Anzahl Marker-Farben beim Item-Lernen
    scan_require_all_markers: bool = True            # True = ALLE Marker müssen gefunden werden
    scan_min_markers_required: int = 2              # Minimum Marker (nur wenn scan_require_all_markers=False)
    scan_slot_hsv_tolerance: int = 25               # HSV-Toleranz für Slot-Erkennung
    scan_slot_inset: int = 10                       # Pixel-Einzug vom Slot-Rand
    scan_slot_color_distance: int = 25              # Farbdistanz für Hintergrund-Ausschluss
    scan_min_confidence: float = 0.8                # Standard-Konfidenz für Template-Matching (80%)
    scan_confirm_delay: float = 0.5                 # Standard-Wartezeit vor Bestätigungs-Klick

    # === LLM VISION (Boss-Erkennung) ===
    llm_enabled: bool = False                       # LLM-basierte Boss-Erkennung aktivieren
    llm_provider: str = "lmstudio"                   # "ollama" oder "lmstudio"
    llm_endpoint: Optional[str] = None              # API-URL (None = Standard-Port)
    llm_model: str = "gemma4:e4b"                   # Modell-Name (Standard: gemma4:e4b)
    llm_timeout: int = 60                           # Timeout für LLM-Anfragen in Sekunden
    llm_retry_count: int = 2                        # Wiederholungen bei KEIN_BOSS (0 = kein Retry)
    llm_async: bool = False                         # Boss-Scan/Watcher im Hintergrund-Thread (Sequenz läuft parallel)
    llm_boss_prompt: Optional[str] = None           # Custom-Prompt für Boss-Erkennung
    llm_reasoning: bool = False                      # Reasoning/Thinking aktivieren wenn Modell es unterstützt
    llm_max_tokens: int = 0                          # Max. Antwort-Tokens (0 = Auto: 128 / 2048 mit Reasoning)
    llm_watcher_interval: float = 5.0               # Boss-Watcher Prüf-Intervall in Sekunden
    llm_watcher_max_scans: int = 0                  # Boss-Watcher: max. Scans (0 = unbegrenzt)
    llm_watcher_timeout: float = 0                  # Boss-Watcher: Timeout in Sekunden (0 = unbegrenzt)

    # === OCR (Texterkennung) ===
    ocr_enabled: bool = False                        # OCR-Texterkennung aktivieren
    ocr_backend: Optional[str] = None                # "easyocr" oder "tesseract" (None = Auto)
    ocr_languages: str = "en"                        # Sprach-Codes kommasepariert (z.B. "en,de")
    ocr_min_confidence: float = 0.3                  # Mindest-Konfidenz für OCR-Ergebnisse (0-1)
    ocr_retry_count: int = 3                         # Wiederholungen bei zu niedriger Konfidenz (0 = kein Retry)

    # === WINDOW-FOKUS-CHECK ===
    window_focus_check: bool = False                # Vor Klick/Taste prüfen ob Ziel-Fenster aktiv ist
    window_focus_title: str = "Idle Clans"          # Substring im Fenstertitel (case-insensitive)
    window_focus_action: str = "pause"              # "pause" (auf Fokus warten) oder "stop"

    # === HUMANIZATION ===
    humanize_enabled: bool = False                  # Zufalls-Jitter + variable Delays aktivieren
    humanize_click_jitter: int = 0                  # Max. Pixel-Abweichung pro Klick (0 = aus, sinnvoll: 2-5)
    humanize_micro_delay_min: float = 0.0           # Zusätzliches Delay vor Klicks/Tasten: Min (Sek.)
    humanize_micro_delay_max: float = 0.0           # Zusätzliches Delay vor Klicks/Tasten: Max (Sek.)
    humanize_break_interval_min: float = 0          # Alle N Minuten Pause einlegen (0 = aus)
    humanize_break_duration_min: float = 0          # Pause-Dauer (Min) bei humanize-Break
    humanize_break_duration_max: float = 0          # Max-Dauer (Sek. Varianz) der humanize-Breaks

    # === SESSION-LOG ===
    session_log_enabled: bool = False               # Schreibt alle Aktionen in CSV
    session_log_dir: str = "logs"                   # Verzeichnis für Log-Dateien

    # === TIMING ===
    timing_pause_interval: float = 0.5              # Prüf-Intervall während Pause (Sekunden)

    # === DEBUG-EINSTELLUNGEN ===
    debug_mode: bool = False                        # Zeigt Schritte VOR Start + wartet auf Enter
    debug_detection: bool = False                   # Alle Ausgaben persistent (nicht überschrieben)
    debug_show_pixel_position: bool = False         # Maus kurz zum Prüf-Pixel bewegen beim Start
    debug_save_templates: bool = False              # Speichert Scan+Template in items/debug/

    def __post_init__(self):
        """Validiert Config-Werte nach Erstellung."""
        # Konstanten lokal importieren — vermeidet Zirkular-Import (models.py importiert
        # bereits AppConfig aus dieser Datei). Single Source of Truth: models.py.
        from .models import (
            TIMEOUT_SKIP_CYCLE, TIMEOUT_RESTART, TIMEOUT_STOP,
            CONSEC_STOP, CONSEC_QUIT, CONSEC_EXIT,
        )
        valid_timeout_actions = {TIMEOUT_SKIP_CYCLE, TIMEOUT_RESTART, TIMEOUT_STOP}
        valid_consec_actions = {CONSEC_STOP, CONSEC_QUIT, CONSEC_EXIT}

        warnings = []
        if self.click_per_point < 1:
            warnings.append(f"click_per_point={self.click_per_point} → 1")
            self.click_per_point = 1
        if self.pixel_wait_timeout < 0:
            warnings.append(f"pixel_wait_timeout={self.pixel_wait_timeout} → 0")
            self.pixel_wait_timeout = 0
        if self.pixel_check_interval <= 0:
            warnings.append(f"pixel_check_interval={self.pixel_check_interval} → 0.1")
            self.pixel_check_interval = 0.1
        if self.timing_pause_interval <= 0:
            warnings.append(f"timing_pause_interval={self.timing_pause_interval} → 0.1")
            self.timing_pause_interval = 0.1
        if self.pixel_max_consecutive_timeouts < 0:
            warnings.append(f"pixel_max_consecutive_timeouts={self.pixel_max_consecutive_timeouts} → 0")
            self.pixel_max_consecutive_timeouts = 0
        if self.scan_min_confidence < 0 or self.scan_min_confidence > 1:
            warnings.append(f"scan_min_confidence={self.scan_min_confidence} → 0.8")
            self.scan_min_confidence = 0.8
        if self.scan_marker_count < 1:
            warnings.append(f"scan_marker_count={self.scan_marker_count} → 1")
            self.scan_marker_count = 1
        if self.pixel_timeout_action not in valid_timeout_actions:
            warnings.append(f"pixel_timeout_action='{self.pixel_timeout_action}' → '{TIMEOUT_SKIP_CYCLE}'")
            self.pixel_timeout_action = TIMEOUT_SKIP_CYCLE
        if self.pixel_consecutive_action not in valid_consec_actions:
            warnings.append(f"pixel_consecutive_action='{self.pixel_consecutive_action}' → '{CONSEC_STOP}'")
            self.pixel_consecutive_action = CONSEC_STOP
        # LLM-Einstellungen validieren
        if self.llm_provider not in ("ollama", "lmstudio"):
            warnings.append(f"llm_provider='{self.llm_provider}' → 'ollama'")
            self.llm_provider = "ollama"
        if self.llm_timeout < 1:
            warnings.append(f"llm_timeout={self.llm_timeout} → 10")
            self.llm_timeout = 10
        if self.llm_watcher_interval < 1:
            warnings.append(f"llm_watcher_interval={self.llm_watcher_interval} → 2.0")
            self.llm_watcher_interval = 2.0
        if self.llm_watcher_max_scans < 0:
            warnings.append(f"llm_watcher_max_scans={self.llm_watcher_max_scans} → 0")
            self.llm_watcher_max_scans = 0
        if self.llm_watcher_timeout < 0:
            warnings.append(f"llm_watcher_timeout={self.llm_watcher_timeout} → 0")
            self.llm_watcher_timeout = 0
        if self.llm_retry_count < 0:
            warnings.append(f"llm_retry_count={self.llm_retry_count} → 0")
            self.llm_retry_count = 0
        if self.llm_max_tokens < 0:
            warnings.append(f"llm_max_tokens={self.llm_max_tokens} → 0")
            self.llm_max_tokens = 0
        # OCR-Einstellungen validieren
        if self.ocr_backend is not None and self.ocr_backend not in ("easyocr", "tesseract"):
            warnings.append(f"ocr_backend='{self.ocr_backend}' → None (Auto)")
            self.ocr_backend = None
        if self.ocr_min_confidence < 0 or self.ocr_min_confidence > 1:
            warnings.append(f"ocr_min_confidence={self.ocr_min_confidence} → 0.3")
            self.ocr_min_confidence = 0.3
        if self.ocr_retry_count < 0:
            warnings.append(f"ocr_retry_count={self.ocr_retry_count} → 0")
            self.ocr_retry_count = 0
        # Window-Fokus-Check
        if self.window_focus_action not in ("pause", "stop"):
            warnings.append(f"window_focus_action='{self.window_focus_action}' → 'pause'")
            self.window_focus_action = "pause"
        # Humanization: min darf nicht > max sein
        if self.humanize_click_jitter < 0:
            warnings.append(f"humanize_click_jitter={self.humanize_click_jitter} → 0")
            self.humanize_click_jitter = 0
        if self.humanize_micro_delay_min < 0:
            self.humanize_micro_delay_min = 0
        if self.humanize_micro_delay_max < self.humanize_micro_delay_min:
            self.humanize_micro_delay_max = self.humanize_micro_delay_min
        if self.humanize_break_interval_min < 0:
            self.humanize_break_interval_min = 0
        if self.humanize_break_duration_min < 0:
            self.humanize_break_duration_min = 0
        if self.humanize_break_duration_max < self.humanize_break_duration_min:
            self.humanize_break_duration_max = self.humanize_break_duration_min
        if warnings:
            for w in warnings:
                print(warn(f"Config-Wert korrigiert: {w}"))

    def to_dict(self) -> dict:
        """Konvertiert zu JSON-serialisierbarem dict."""
        return asdict(self)

    # Alte → Neue Feldnamen (Migration alter config.json Dateien)
    _FIELD_MIGRATION = {
        "clicks_per_point": "click_per_point",
        "max_total_clicks": "click_max_total",
        "post_click_delay": "click_post_delay",
        "color_tolerance": "pixel_color_tolerance",
        "max_consecutive_timeouts": "pixel_max_consecutive_timeouts",
        "consecutive_timeout_action": "pixel_consecutive_action",
        "scan_pixel_step": "pixel_scan_step",
        "show_pixel_delay": "pixel_show_delay",
        "item_click_delay": "scan_item_click_delay",
        "marker_count": "scan_marker_count",
        "require_all_markers": "scan_require_all_markers",
        "min_markers_required": "scan_min_markers_required",
        "slot_hsv_tolerance": "scan_slot_hsv_tolerance",
        "slot_inset": "scan_slot_inset",
        "slot_color_distance": "scan_slot_color_distance",
        "default_min_confidence": "scan_min_confidence",
        "default_confirm_delay": "scan_confirm_delay",
        "show_pixel_position": "debug_show_pixel_position",
        "pause_check_interval": "timing_pause_interval",
    }

    @classmethod
    def from_dict(cls, data: dict) -> 'AppConfig':
        """Erstellt AppConfig aus einem dict. Migriert alte Feldnamen automatisch."""
        migrated = {}
        for k, v in data.items():
            new_key = cls._FIELD_MIGRATION.get(k, k)
            migrated[new_key] = v
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in migrated.items() if k in valid_keys}
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


_CONFIG_SECTIONS = [
    ("KLICK-EINSTELLUNGEN", [
        "click_per_point", "click_max_total",
        "click_move_delay", "click_post_delay",
    ]),
    ("SICHERHEIT", [
        "failsafe_enabled", "failsafe_x", "failsafe_y",
    ]),
    ("PIXEL-ERKENNUNG", [
        "pixel_color_tolerance", "pixel_wait_tolerance", "pixel_wait_timeout",
        "pixel_timeout_action", "pixel_check_interval",
        "pixel_max_consecutive_timeouts", "pixel_consecutive_action",
        "pixel_scan_step", "pixel_show_delay",
    ]),
    ("SCAN-EINSTELLUNGEN", [
        "scan_reverse", "scan_click_immediate", "scan_park_mouse",
        "scan_slot_delay", "scan_item_click_delay",
        "scan_marker_count", "scan_require_all_markers", "scan_min_markers_required",
        "scan_slot_hsv_tolerance", "scan_slot_inset", "scan_slot_color_distance",
        "scan_min_confidence", "scan_confirm_delay",
    ]),
    ("LLM VISION (Boss-Erkennung)", [
        "llm_enabled", "llm_provider", "llm_endpoint", "llm_model",
        "llm_timeout", "llm_retry_count", "llm_async", "llm_reasoning", "llm_max_tokens", "llm_boss_prompt",
        "llm_watcher_interval", "llm_watcher_max_scans", "llm_watcher_timeout",
    ]),
    ("OCR (Texterkennung)", [
        "ocr_enabled", "ocr_backend", "ocr_languages", "ocr_min_confidence", "ocr_retry_count",
    ]),
    ("WINDOW-FOKUS-CHECK", [
        "window_focus_check", "window_focus_title", "window_focus_action",
    ]),
    ("HUMANIZATION", [
        "humanize_enabled", "humanize_click_jitter",
        "humanize_micro_delay_min", "humanize_micro_delay_max",
        "humanize_break_interval_min",
        "humanize_break_duration_min", "humanize_break_duration_max",
    ]),
    ("SESSION-LOG", [
        "session_log_enabled", "session_log_dir",
    ]),
    ("TIMING", [
        "timing_pause_interval",
    ]),
    ("DEBUG", [
        "debug_mode", "debug_detection",
        "debug_show_pixel_position", "debug_save_templates",
    ]),
]


def save_config(config: AppConfig) -> None:
    """Speichert Konfiguration in config.json — gruppiert nach Sektionen."""
    data = config.to_dict()

    entries = []
    written_keys = set()

    for section_name, keys in _CONFIG_SECTIONS:
        for key in keys:
            if key not in data:
                continue
            val = json.dumps(data[key], ensure_ascii=False)
            written_keys.add(key)
            entries.append((section_name, key, val))

    remaining = [(k, v) for k, v in data.items() if k not in written_keys]
    for k, v in remaining:
        entries.append(("SONSTIGE", k, json.dumps(v, ensure_ascii=False)))

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write("{\n")
            last_section = None
            for i, (section, key, val) in enumerate(entries):
                if section != last_section:
                    if last_section is not None:
                        f.write("\n")
                    last_section = section
                comma = "," if i < len(entries) - 1 else ""
                f.write(f'  "{key}": {val}{comma}\n')
            f.write("}\n")
    except IOError as e:
        print(err(f"Config konnte nicht gespeichert werden: {e}"))


# Konfiguration laden (wird beim Import ausgeführt)
CONFIG: AppConfig = load_config()

# Konfig-Werte als Variablen (nur Werte die sich zur Laufzeit nicht ändern)
# ACHTUNG: Werte die sich durch Factory Reset ändern können, immer über
# state.config abrufen statt über Modul-Variablen!
DEFAULT_MIN_CONFIDENCE: float = CONFIG.scan_min_confidence
