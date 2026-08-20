"""
Konfiguration für den Autoclicker.
Lädt und speichert config.json mit Standard-Werten.
"""

import json
import logging
from dataclasses import dataclass, fields, asdict
from pathlib import Path
from typing import Optional, Union, get_args

from .utils import col, ok, warn, err, atomic_write

# Logger
logger = logging.getLogger("autoclicker")

# =============================================================================
# KONFIGURATION
# =============================================================================
CONFIG_FILE = "config.json"
SEQUENCES_DIR: str = "sequences"       # Ordner für gespeicherte Sequenzen

# Laufstatus für Beobachter ausserhalb des Prozesses (runtime/status.py).
# Bewusst im Wurzelverzeichnis neben config.json und NICHT in sequences/:
# `Path.glob("*.json")` erfasst auch Dateien mit führendem Punkt, die Datei
# stünde also als Sequenz im Studio-Menü, im Konsolen-Menü und in der
# Start-Migration — und weil sie sich sekündlich ändert, gewänne sie jedes Mal
# `zuletzt_bearbeitet()`. Dieselbe Falle, wegen der die `.bak`-Sicherungen
# unter backups/ liegen statt neben dem Original.
RUN_STATUS_FILE: str = ".lauf.json"

# Der Rückweg: Befehle von aussen an den Hauptprozess (befehl.py). Liegt aus
# denselben Gründen hier oben wie die Statusdatei — und ist wie sie kein Bestand,
# sondern ein Briefkasten, der beim Lesen geleert wird.
COMMAND_FILE: str = ".befehl.json"


@dataclass
class AppConfig:
    """Typisierte Konfiguration für den Autoclicker.
    Feld-Reihenfolge bestimmt die Reihenfolge in config.json."""
    # === PROGRAMMSTART ===
    # Das Studio ist die Hauptoberflaeche. False behaelt den bisherigen reinen
    # Konsolenstart; die Hotkeys zum manuellen Oeffnen funktionieren weiterhin.
    studio_open_on_start: bool = True                # Sequenz-Studio mit main.py öffnen

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
    # Wann zwei Stellen derselbe Punkt sind. Radius 0 = nur exakt gleiche
    # Koordinate (das Verhalten vor der Einfuehrung).
    punkt_radius: int = 8                           # Abstand in px, bis zu dem wiederverwendet wird
    punkt_farbtoleranz: int = 10                    # ...aber nur, wenn auch die Farbe passt
    pixel_wait_tolerance: int = 10                  # Toleranz für Pixel-Trigger
    pixel_wait_timeout: int = 300                   # Timeout für Pixel-Trigger in Sekunden (0 = unendlich)
    pixel_timeout_action: str = "skip_cycle"        # Aktion bei Timeout: "skip_cycle", "restart", "stop"
    pixel_check_interval: float = 1                 # Prüf-Intervall für Farbe in Sekunden
    pixel_max_consecutive_timeouts: int = 5         # Nach X aufeinanderfolgenden Timeouts → Notbremse (0 = deaktiviert)
    pixel_consecutive_action: str = "stop"          # Notbremse: "stop", "quit", "exit"
    pixel_show_delay: float = 0.3                   # Wie lange Pixel-Position angezeigt wird (Sekunden)

    # === NACHPRUEFUNG ("hat der Klick gewirkt?") ===
    # Greift nur bei Schritten mit gesetzter verify_condition — ohne die passiert nichts.
    verify_timeout: float = 3.0                     # Sekunden auf die erwartete Wirkung warten
    verify_retries: int = 1                         # Wiederholungen der Aktion, bevor else greift (0 = keine)
    verify_interval: float = 0.2                    # Prüf-Intervall der Nachprüfung in Sekunden

    # === SCAN-EINSTELLUNGEN ===
    scan_click_immediate: bool = False              # True = Scan→Klick pro Slot
    scan_park_mouse: Union[bool, list] = False      # [x, y] = Maus vor Scan parken, False = nicht
    scan_slot_delay: float = 0.1                    # Pause zwischen Slot-Scans in Sekunden
    scan_item_click_delay: float = 1.0              # Pause nach Item-Klick in Sekunden
    scan_marker_count: int = 5                      # Anzahl Marker-Farben beim Item-Lernen
    scan_require_all_markers: bool = True            # True = ALLE Marker müssen gefunden werden
    scan_min_markers_required: int = 2              # Minimum Marker (nur wenn scan_require_all_markers=False)
    scan_marker_min_pixels: int = 1                 # Min. passende (abgetastete) Pixel pro Marker-Farbe (>1 = robuster gegen Rausch-Pixel)
    # Pfad zu einer Item-Name -> Gold-pro-Stueck-JSON (schreibt market_analysis).
    # Leer = aus: dann entscheidet wie bisher die von Hand gesetzte Item-Prioritaet.
    scan_market_value_file: str = ""
    scan_slot_hsv_tolerance: int = 25               # HSV-Toleranz für Slot-Erkennung
    scan_slot_inset: int = 10                       # Pixel-Einzug vom Slot-Rand
    # Gemessen an einem echten Bestand: der Slot-Hintergrund ist nicht EINE
    # Farbe - sein dunklerer Rand lag 44 entfernt und blieb bei 25 als Marker
    # in 19 von 19 Items stehen. Bei 45 verschwindet er, bei 55 aendert sich
    # nichts mehr.
    scan_slot_color_distance: int = 45              # Farbdistanz für Hintergrund-Ausschluss
    scan_min_confidence: float = 0.8                # Standard-Konfidenz für Template-Matching (80%)
    scan_confirm_delay: float = 0.5                 # Standard-Wartezeit vor Bestätigungs-Klick

    # === LLM VISION (Boss-Erkennung) ===
    llm_enabled: bool = False                       # LLM-basierte Boss-Erkennung aktivieren
    llm_provider: str = "lmstudio"                   # "ollama" oder "lmstudio"
    llm_endpoint: Optional[str] = None              # API-URL (None = Standard-Port)
    llm_model: str = "google/gemma-4-12b-qat"       # Modell-Name (Standard: google/gemma-4-12b-qat)
    llm_timeout: int = 60                           # Timeout für LLM-Anfragen in Sekunden
    llm_retry_count: int = 2                        # Wiederholungen bei KEIN_BOSS (0 = kein Retry)
    llm_async: bool = False                         # Boss-Scan/Watcher im Hintergrund-Thread (Sequenz läuft parallel)
    llm_boss_prompt: Optional[str] = None           # Custom-Prompt für Boss-Erkennung
    llm_reasoning: bool = False                      # Reasoning/Thinking aktivieren wenn Modell es unterstützt
    llm_max_tokens: int = 0                          # Max. Antwort-Tokens (0 = Auto: 128 / 2048 mit Reasoning)
    llm_watcher_interval: float = 5.0               # Boss-Watcher Prüf-Intervall in Sekunden
    llm_watcher_max_scans: int = 0                  # Boss-Watcher: max. Scans (0 = unbegrenzt)
    llm_watcher_timeout: float = 0                  # Boss-Watcher: Timeout in Sekunden (0 = unbegrenzt)
    boss_learn_global: bool = False                 # Neu entdeckte Bosse (LLM/OCR) in die globale Bibliothek statt in den Scan lernen

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

    # === AUFNAHME ===
    # False = das Mausrad wird beim Aufnehmen ignoriert. Gedacht für Spiele, in denen
    # das Rad nur die Ansicht dreht: solche Drehungen gehören nicht in die Sequenz,
    # blähen sie aber auf. Der Hook lässt das Rad dann schon in winapi liegen.
    record_scroll: bool = True                      # Mausrad mit aufzeichnen

    # === SESSION-LOG ===
    session_log_enabled: bool = False               # Schreibt alle Aktionen in CSV
    session_log_dir: str = "logs"                   # Verzeichnis für Log-Dateien

    # === TIMING ===
    timing_pause_interval: float = 0.5              # Prüf-Intervall während Pause (Sekunden)

    # === DATEIEN ===
    # Beim Start alle JSON-Dateien aufs aktuelle Format heben (persistence/sweep.py).
    # Nur ausschalten, wenn man Altbestand absichtlich einfrieren will - dann hebt
    # tools/migrate.py von Hand.
    migrate_on_start: bool = True

    # === DEBUG-EINSTELLUNGEN ===
    # Zwei getrennt schaltbare Ausgabe-Stufen, jede Kombination erlaubt (s. runtime/debug.py).
    # Keine der beiden verändert den Ablauf - nur wie viel du zu sehen bekommst.
    #   debug_log    = alles ausgeben, nichts überschreiben
    #   debug_detail = zusätzlich Zeiger auf den Zielpunkt + ausschreiben, was dort
    #                  passieren soll (mit Farbquadrat bei Farb-Bedingungen)
    # debug_detail gibt mehrzeilig aus und zieht die persistente Ausgabe damit zwangsläufig
    # mit - eine Status-Zeile, die sich selbst überschreibt, wäre sonst überklebt.
    # Der MANUELLE Modus (Schritt für Schritt auf Bestätigung) ist bewusst KEINE Config,
    # sondern Laufzeit-Zustand: Punkte-Menü (CTRL+ALT+P) -> 'manuell'.
    debug_log: bool = False                         # Stufe 1: persistente Schritt-Ausgabe
    debug_detail: bool = False                      # Stufe 2: Zeiger + Detailausgabe
    debug_show_pixel_position: bool = False         # Zeiger kurz zum Prüf-Pixel beim Farbwarten
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
        if self.scan_marker_min_pixels < 1:
            warnings.append(f"scan_marker_min_pixels={self.scan_marker_min_pixels} → 1")
            self.scan_marker_min_pixels = 1
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
        "max_consecutive_timeouts": "pixel_max_consecutive_timeouts",
        "consecutive_timeout_action": "pixel_consecutive_action",
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
        # Alte Sammelflags: debug_detection war die reine Log-Variante, debug_mode die
        # ausführlichere. debug_step war eine Zwischenstufe, die beides vermischte.
        "debug_detection": "debug_log",
        "debug_mode": "debug_detail",
        "debug_step": "debug_detail",
        "pause_check_interval": "timing_pause_interval",
    }

    @classmethod
    def from_dict(cls, data: dict) -> 'AppConfig':
        """Erstellt AppConfig aus einem dict. Migriert alte Feldnamen automatisch."""
        migrated = {}
        for k, v in data.items():
            new_key = cls._FIELD_MIGRATION.get(k, k)
            # Migrierten Alt-Key nur übernehmen wenn der neue Key NICHT bereits
            # (direkt oder durch eine frühere Migration) gesetzt ist — sonst
            # hängt das Ergebnis von der dict-Reihenfolge ab und ein alter
            # Default könnte einen aktuellen Nutzerwert überschreiben.
            if new_key != k and (new_key in migrated or new_key in data):
                continue
            migrated[new_key] = v
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in migrated.items() if k in valid_keys}
        return cls(**filtered)


# Abwärtskompatibel: DEFAULT_CONFIG als dict (für JSON-Serialisierung)
DEFAULT_CONFIG = AppConfig().to_dict()


def uebernehmen(ziel: AppConfig, quelle: AppConfig) -> None:
    """Schreibt alle Werte aus `quelle` in `ziel` — ohne das Objekt zu tauschen.

    Im Prozess gibt es **ein** Config-Objekt: `state.config` IST das
    Modul-`CONFIG` (gesetzt in `main.py`). Wer es gegen ein neues austauscht,
    lässt jeden zurück, der noch die alte Referenz hält — und das sind alle
    Module mit `from .config import CONFIG` (imaging, die Item-Editoren). Die
    sähen ab dem Austausch dauerhaft die Werte vom Programmstart.

    Deshalb wird hier hineingeschrieben statt ersetzt. Drei Stellen tun das:
    Factory Reset, Bundle-Import und das Neuladen nach einem Speichern im
    Sequenz-Studio.
    """
    for f in fields(AppConfig):
        setattr(ziel, f.name, getattr(quelle, f.name))


def load_config() -> AppConfig:
    """Lädt Konfiguration aus config.json oder erstellt Standard-Config."""
    config_path = Path(CONFIG_FILE)

    if config_path.exists():
        try:
            # Nur das Lesen im with-Block — Handle MUSS geschlossen sein, bevor
            # save_config() schreibt. Auf Windows scheitert os.replace sonst mit
            # WinError 5, weil die Datei noch offen ist (open() setzt kein
            # FILE_SHARE_DELETE). Auf POSIX ginge das Ersetzen offener Dateien.
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            # config.json muss ein Objekt sein — ein Top-Level-Array/Skalar
            # würde sonst bei from_dict / loaded.keys() crashen und damit den
            # gesamten App-Start (CONFIG = load_config() auf Modulebene) killen.
            if not isinstance(loaded, dict):
                raise ValueError(f"config.json ist kein Objekt (gefunden: {type(loaded).__name__})")

            config = AppConfig.from_dict(loaded)

            # Absoluten Pfad anzeigen: config.json wird relativ zum Arbeits-
            # verzeichnis geladen. Wird die App aus einem anderen Ordner gestartet,
            # greift eine andere Datei — der volle Pfad macht das sofort sichtbar.
            abs_path = config_path.resolve()

            # Prüfe ob neue Optionen hinzugefügt wurden
            missing_keys = set(DEFAULT_CONFIG.keys()) - set(loaded.keys())
            if missing_keys:
                save_config(config)
                print(ok(f"Config geladen + {len(missing_keys)} neue Option(en) ergänzt: {', '.join(missing_keys)}"))
            else:
                print(col(f"[CONFIG] Geladen aus {abs_path}", "green"))
            return config
        except (json.JSONDecodeError, IOError, OSError, TypeError, AttributeError, ValueError, UnicodeDecodeError) as e:
            print(warn(f"Config konnte nicht geladen werden: {e}"))
            print(col("[CONFIG] Verwende Standard-Konfiguration", "yellow"))
    else:
        # Erstelle Standard-Config-Datei. Absoluten Pfad zeigen, damit klar ist
        # WO sie landet (= Arbeitsverzeichnis, evtl. nicht der Projektordner).
        save_config(AppConfig())
        print(ok(f"Standard-Konfiguration erstellt: {config_path.resolve()}"))

    return AppConfig()


_CONFIG_SECTIONS = [
    ("PROGRAMMSTART", [
        "studio_open_on_start",
    ]),
    ("KLICK-EINSTELLUNGEN", [
        "click_per_point", "click_max_total",
        "click_move_delay", "click_post_delay",
    ]),
    ("SICHERHEIT", [
        "failsafe_enabled", "failsafe_x", "failsafe_y",
    ]),
    ("PIXEL-ERKENNUNG", [
        "punkt_radius", "punkt_farbtoleranz",
        "pixel_wait_tolerance", "pixel_wait_timeout",
        "pixel_timeout_action", "pixel_check_interval",
        "pixel_max_consecutive_timeouts", "pixel_consecutive_action",
        "pixel_show_delay",
    ]),
    ("NACHPRUEFUNG", [
        "verify_timeout", "verify_retries", "verify_interval",
    ]),
    ("SCAN-EINSTELLUNGEN", [
        "scan_click_immediate", "scan_park_mouse",
        "scan_slot_delay", "scan_item_click_delay",
        "scan_marker_count", "scan_require_all_markers", "scan_min_markers_required",
        "scan_marker_min_pixels", "scan_market_value_file",
        "scan_slot_hsv_tolerance", "scan_slot_inset", "scan_slot_color_distance",
        "scan_min_confidence", "scan_confirm_delay",
    ]),
    ("LLM VISION (Boss-Erkennung)", [
        "llm_enabled", "llm_provider", "llm_endpoint", "llm_model",
        "llm_timeout", "llm_retry_count", "llm_async", "llm_reasoning", "llm_max_tokens", "llm_boss_prompt",
        "llm_watcher_interval", "llm_watcher_max_scans", "llm_watcher_timeout",
        "boss_learn_global",
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
    ("AUFNAHME", [
        "record_scroll",
    ]),
    ("SESSION-LOG", [
        "session_log_enabled", "session_log_dir",
    ]),
    ("TIMING", [
        "timing_pause_interval",
    ]),
    ("DATEIEN", [
        "migrate_on_start",
    ]),
    ("DEBUG", [
        "debug_log", "debug_detail",
        "debug_show_pixel_position", "debug_save_templates",
    ]),
]


def config_abschnitte() -> list:
    """Die Abschnitte in Datei-Reihenfolge, inklusive noch nicht zugeordneter Felder.

    Genau die Einteilung, die `save_config()` in die Datei schreibt — und
    deshalb steht sie hier und nicht im Studio: sonst stünden die Felder im
    Fenster in einer anderen Ordnung als in der Datei, die man daneben aufmacht.

    Der Nachzügler-Abschnitt ist kein Schmuck: ein Feld, das jemand der
    Dataclass hinzufügt und in `_CONFIG_SECTIONS` vergisst, ist damit in beiden
    Ansichten sichtbar statt unsichtbar. (Ein Test verlangt trotzdem, dass er
    leer bleibt.)
    """
    zugeordnet = {k for _, keys in _CONFIG_SECTIONS for k in keys}
    alle = [f.name for f in fields(AppConfig)]
    abschnitte = [(titel, [k for k in keys if k in alle])
                  for titel, keys in _CONFIG_SECTIONS]
    rest = [k for k in alle if k not in zugeordnet]
    if rest:
        abschnitte.append(("SONSTIGE", rest))
    return abschnitte


def optionale_felder() -> list:
    """Felder, die `None` erlauben — dort heisst ein leeres Eingabefeld `null`.

    Bei allen anderen heisst leer `0` bzw. `""`, und der Unterschied ist nicht
    kosmetisch: `click_max_total = 0` wäre „nach null Klicks stoppen", `None`
    dagegen „unbegrenzt". Ein Eingabefeld kann das nicht wissen, also sagt es
    ihm diese Liste.
    """
    return [f.name for f in fields(AppConfig) if type(None) in get_args(f.type)]


def save_config(config: AppConfig) -> None:
    """Speichert Konfiguration in config.json — gruppiert nach Sektionen."""
    data = config.to_dict()

    entries = []
    for section_name, keys in config_abschnitte():
        for key in keys:
            if key in data:
                entries.append((section_name, key, json.dumps(data[key], ensure_ascii=False)))

    lines = ["{\n"]
    last_section = None
    for i, (section, key, val) in enumerate(entries):
        if section != last_section:
            if last_section is not None:
                lines.append("\n")
            last_section = section
        comma = "," if i < len(entries) - 1 else ""
        lines.append(f'  "{key}": {val}{comma}\n')
    lines.append("}\n")

    try:
        atomic_write(CONFIG_FILE, "".join(lines))
    except (IOError, OSError) as e:
        print(err(f"Config konnte nicht gespeichert werden: {e}"))


# Konfiguration laden (wird beim Import ausgeführt)
CONFIG: AppConfig = load_config()

# Hier stand früher `DEFAULT_MIN_CONFIDENCE = CONFIG.scan_min_confidence` — ein Name für
# zwei verschiedene Dinge, und damit die Ursache stillen Datenverlusts:
#
#   * der DATEI-Default (was gilt, wenn min_confidence in der JSON fehlt) ist konstant
#     und liegt jetzt als models.DEFAULT_MIN_CONFIDENCE bei den Dataclasses,
#   * die VOREINSTELLUNG für neu angelegte Profile ist `scan_min_confidence` und wird
#     über state.config gelesen (Factory Reset wirkt dann sofort).
#
# Solange beides derselbe Wert war, liess der Serializer ein Feld weg, das exakt auf dem
# Config-Wert stand - und beim naechsten Aendern der Config kam es mit einem anderen Wert
# zurueck. Nicht wieder zusammenlegen.
