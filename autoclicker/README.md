# Autoclicker Module

Diese Verzeichnisstruktur enthält die modulare Aufteilung des Autoclickers.

## Modulstruktur

```
autoclicker/
├── __init__.py         # Paket-Initialisierung
├── config.py           # Konfiguration (config.json)
├── models.py           # Datenklassen (ClickPoint, Sequence, BossScanConfig, etc.)
├── winapi.py           # Windows API (Maus, Tastatur, Hotkeys, Window-Fokus)
├── utils.py            # Hilfsfunktionen (JSON, Input, Zeit)
├── imaging.py          # Bildverarbeitung (Screenshots, Farben, OpenCV)
├── persistence.py      # Speichern/Laden (Sequenzen, Slots, Items, Boss-Scans)
├── execution.py        # Sequenz-Ausführung + safe_click/safe_key Wrapper
├── handlers.py         # Hotkey-Handler
├── llm_vision.py       # LLM Vision (Ollama / LM Studio Boss-Detection)
├── ocr.py              # OCR Texterkennung (EasyOCR / Tesseract Boss-Detection)
├── session_log.py      # CSV-Session-Logger
├── import_export.py    # ZIP-Bundle Export/Import + Koordinaten-Remapping
└── editors/
    ├── __init__.py
    ├── slot_editor.py             # Slot-Editor
    ├── item_editor.py             # Item-Editor (inkl. autoscan-Befehl)
    ├── sequence_editor.py         # Sequenz-Editor (inkl. boss/watcher-Steps)
    ├── item_scan_editor.py        # Item-Scan-Editor + Auto-Scan-Workflow
    ├── boss_scan_editor.py        # Boss-Scan-Editor mit LLM-Vision-Konfiguration
    └── import_export_editor.py    # Wizard für Setup-Export/Import
```

## Module im Detail

### config.py
- `DEFAULT_CONFIG` - Standard-Konfiguration
- `load_config()` - Lädt config.json
- `save_config()` - Speichert config.json
- `CONFIG` - Globale Konfiguration
- `AppConfig` - Dataclass mit allen Settings, gruppiert nach Funktion:
  - `click_*` - Klick-Einstellungen (Anzahl, Delays)
  - `scan_*` - Item-Scan-Einstellungen (Marker, Templates, Slots)
  - `pixel_*` - Farb-/Pixel-Erkennung (Toleranz, Timeout, Notbremse)
  - `llm_*` - LLM Vision Boss-Detection (Provider, Modell, Timeout)
  - `ocr_*` - OCR Texterkennung (Backend, Sprachen, Konfidenz)
  - `humanize_*` - Anti-Bot-Detection (Jitter, Delays, Pausen)
  - `window_focus_*` - Fenster-Fokus-Check (Titel, Aktion)
  - `session_log_*` - CSV-Logging (Aktivierung, Verzeichnis)
  - `debug_*` - Debug-Optionen (Mode, Detection, Templates)
  - `timing_*` - Timing-Einstellungen (Pause-Intervall)
- Automatische Config-Migration via `_FIELD_MIGRATION` dictionary

### models.py
- `ClickPoint` - Klickpunkt mit x,y Koordinaten
- `SequenceStep` - Schritt in einer Sequenz (inkl. `boss_scan` und `boss_watcher`)
- `LoopPhase` / `Sequence` - Loop-Phasen + komplette Sequenz
- `ItemProfile` / `ItemSlot` / `ItemScanConfig` - Item-Erkennung
- `BossProfile` / `BossScanConfig` - Boss-Erkennung mit `use_llm`/`llm_fallback` (LLM) und `use_ocr`/`ocr_fallback` (OCR)
- `AutoClickerState` - Globaler Zustand inkl. `state.lock` für Thread-Safety

### winapi.py
- Hotkey-Konstanten (`VK_A`, `VK_S`, ..., `VK_I` für Import/Export)
- `HOTKEY_*` IDs inkl. `HOTKEY_IMPORT_EXPORT`
- Windows-Strukturen (INPUT, MOUSEINPUT, etc.)
- `get_cursor_pos()` / `set_cursor_pos()` - Mausposition
- `send_click()` / `send_key()` - Low-Level Input (im Worker via `safe_click`/`safe_key` aus execution.py wrappen!)
- `check_failsafe()` - Fail-Safe prüfen
- `get_foreground_window_title()` / `is_target_window_active()` - Window-Fokus-Check
- `register_hotkeys()` / `unregister_hotkeys()`

### utils.py
- `sanitize_filename()` - Sichere Dateinamen
- `compact_json()` - Kompakte JSON-Formatierung
- `safe_input()` / `confirm()` / `interactive_select()` - Input-Helfer
- `parse_time_input()` / `format_duration()` - Zeit-Tools

### imaging.py
- `get_pixel_color()` / `take_screenshot()` - Screenshot/Pixel
- `find_color_in_image()` / `match_template_in_image()` - Erkennung
- `run_color_analyzer()` / `select_region()` - Tooling

### persistence.py
- `save_data()` / `load_points()` - Punkte (Snapshot unter `state.lock`)
- `save_item_scan()` / `load_item_scan_file()` - Item-Scans mit use_ocr/ocr_fallback Support
- `save_boss_scan()` / `load_boss_scan_file()` - Boss-Scans mit use_ocr/ocr_fallback Support
- `save_global_slots()` / `load_global_slots()` - Slots
- `save_global_items()` / `load_global_items()` - Items
- Preset-Funktionen für Slots und Items
- `_slot_to_dict()` - Extrahierter Helper für standardisierte ItemSlot-Serialisierung (5 Speicherlokationen)
- `_step_to_dict` / `_item_to_dict` / `_boss_profile_to_dict` - Serialisierungshelfer (auch von `import_export.py` genutzt)

### execution.py
- `sequence_worker()` - Worker-Thread Hauptschleife
- `safe_click(state, x, y, label)` / `safe_key(state, key, label)` - **Zentrale Wrapper** für alle Klicks/Tasten im Worker. Bündelt Window-Fokus-Check, Humanization (Jitter/Mikro-Delays/Breaks) und Session-Logging.
- `execute_step()` / `execute_item_scan()` / `execute_boss_scan()` - Step-Dispatcher mit LLM/OCR-Unterstützung
- `_execute_boss_watcher_step()` - Kontinuierliches Boss-Polling
- `_execute_ocr_boss_detection()` - OCR-Texterkennung für Bosse (spiegelt `_execute_llm_boss_detection()`)
- `_check_profile_match()` - Extrahierter Helper für Template/Marker-Matching (beide Scan-Typen)
- `_step_status()` - Extrahierter Helper für einheitliche Debug-Ausgaben
- `wait_while_paused()` - Zentraler Helper für Pause-Event-Loops

### llm_vision.py
- `analyze_image()` - Sendet Bild + Prompt an Ollama / LM Studio
- `match_boss_name()` - Mappt LLM-Antwort auf bekannten Boss-Namen oder markiert als neu (`is_new=True`)
- `clean_boss_name()` / `is_no_boss()` - Antwort-Postprocessing
- `test_connection()` - Verbindungstest zu Ollama / LM Studio
- Provider-Konstanten: `PROVIDER_OLLAMA`, `PROVIDER_LMSTUDIO`

### ocr.py
- `available_backends()` - Gibt Liste verfügbarer OCR-Backends zurück (EasyOCR, Tesseract)
- `read_text(img, backend, languages, min_confidence)` - Extrahiert Text aus Bild mit Konfidenz-Scores
- `detect_boss_name(img, boss_names, backend, languages, min_confidence)` - Erkennt Boss-Namen mit Substring/Exact-Matching
- `get_status()` - String-Status der verfügbaren OCR-Backends
- Backend-Konstanten: `BACKEND_EASYOCR`, `BACKEND_TESSERACT`

### session_log.py
- `SessionLog` - Thread-sicherer CSV-Writer pro Sequenz-Session
- `start_session_log(state)` / `log_event(state, event, ...)` - High-Level API
- Eine Datei pro Session: `logs/YYYY-MM-DD_HHMMSS_<seq>.csv`

### import_export.py
- `export_bundle()` - Packt Setup als ZIP (inkl. Templates) + Manifest mit Referenzpunkten
- `import_bundle()` - Liest ZIP, remappt Koordinaten, lädt in State
- `compute_transform()` - Berechnet Skalierung + Offset aus 2 Referenzpunkt-Paaren
- `remap_point()` / `remap_region()` - Wendet Transformation an
- `read_manifest()` - Liest nur das Manifest aus einem ZIP

## Verwendung

```python
from autoclicker import CONFIG, AutoClickerState
from autoclicker.winapi import get_cursor_pos
from autoclicker.persistence import save_data, load_points
from autoclicker.llm_vision import analyze_image, test_connection
from autoclicker.ocr import detect_boss_name, available_backends, read_text
from autoclicker.import_export import export_bundle, import_bundle, compute_transform
```
