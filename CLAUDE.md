# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Was das ist

Windows-Autoclicker für das Spiel "Idle Clans". Konsolen-getriebene Python-App mit globalen Hotkeys, Sequenz-Editor, OpenCV-basierter Item-Erkennung und optionaler LLM-Vision für Boss-Detection (Ollama / LM Studio). Code-Sprache und alle UI-Texte sind **Deutsch** — neue Strings ebenso.

## Run / Lint / Test

```bash
python main.py                  # Startet die App (Windows only — braucht msvcrt, ctypes.windll)
python tools/test_llm.py            # Standalone-Verbindungstest für Ollama/LM Studio (nutzt llm_vision)
python tools/test_llm.py screenshot # LLM-Screenshot-Test ohne Editor-Setup
python tools/sync_json.py       # Migriert alte JSON-Dateien aufs aktuelle Schema
python tools/slot_tester.py     # Debug-Tool für Slot-Erkennung
```

Es gibt **keine Test-Suite und keinen Linter**. Vor Commits stattdessen:
```bash
python3 -c "import ast; [ast.parse(open(f).read()) for f in <changed-files>]"
```
Voller Import scheitert auf Linux an `msvcrt` — das ist normal, nicht reparieren.

## Architektur

### Threading-Modell
- **Main-Thread**: Pumpt die Windows-Hotkey-Message-Loop (`main.py`), dispatcht zu Handlern, blockiert beim Editor-Input.
- **Worker-Thread**: `sequence_worker()` in `autoclicker/runtime/worker.py` — führt die aktive Sequenz aus. `execution.py` ist nur ein Backward-Compat-Shim.
- **Geteilter State**: `AutoClickerState` (in `models.py`) mit `state.lock` (threading.Lock) und mehreren Events (`stop_event`, `pause_event`, `skip_event`, `restart_event`, `skip_cycle_event`, `quit_event`, `finish_event`).

**Pattern für State-Mutationen**: Jede Lese-/Schreib-Operation auf `state.global_items`, `state.global_slots`, `state.boss_scans`, `state.item_scans`, `state.sequences`, `state.points`, `state.clicked_categories`, Zähler etc. **muss** unter `with state.lock:` laufen. Persistenz-Funktionen in `autoclicker/persistence/` machen einen Snapshot unter Lock und schreiben die Datei außerhalb. Datei-Saves laufen crash-sicher über `atomic_write()` (Temp-Datei + `os.replace`, in `utils/parsing.py`) — bei Absturz bleibt die alte Datei intakt statt korrupt.

### Aktions-Wrapper (zentral)
Alle Klicks und Tastendrücke im Worker laufen über `safe_click(state, x, y, label)` und `safe_key(state, key, label)` in `autoclicker/runtime/actions.py`. Diese bündeln:
1. **Window-Fokus-Check** (`window_focus_check` in Config — pausiert oder stoppt wenn Ziel-Fenster nicht aktiv)
2. **Humanization** (Mikro-Delays, Klick-Jitter, periodische Breaks)
3. **Session-Logging** (CSV-Event)

Beim Hinzufügen neuer Klick/Key-Aktionen im Worker: **immer** über die Wrapper gehen, nie direkt `send_click`/`send_key` aufrufen. Sonst umgehen sie Fokus-Check + Humanize + Log.

### Hotkey-Flow
1. `winapi.py` definiert `HOTKEY_*` IDs + `register_hotkeys()` → `RegisterHotKey`.
2. `main.py` mappt IDs auf `handle_*`-Funktionen aus `handlers.py`.
3. Handler dispatcht typischerweise zu einem Editor unter `autoclicker/editors/`.
4. Editoren sind **synchron, blockierend** (Console-Input via `safe_input`). Während ein Editor läuft, ist der Main-Thread blockiert — der Worker kann parallel weiterlaufen.

Neuen Hotkey hinzufügen: Konstante in `winapi.py` (`HOTKEY_*` + `VK_*`) → `register_hotkeys()`-Liste → Handler in `handlers.py` → `hotkey_handlers` dict in `main.py` → Hilfetext in `print_help()` von `main.py`.

### Persistenz-Layout
Mehrere JSON-Dateien an festen Orten (Konstanten in `autoclicker/persistence/paths.py` + `config.py`):
```
config.json                    AppConfig (alle Settings)
sequences/points.json          state.points (ClickPoints)
sequences/<name>.json          eine Sequence pro Datei
slots/slots.json               state.global_slots
slots/presets/<name>.json      Slot-Presets
items/items.json               state.global_items
items/templates/<name>.png     Item-Templates (PNG, referenziert per Dateiname-only)
items/presets/<name>.json      Item-Presets
item_scans/<name>.json         eine ItemScanConfig pro Datei
boss_scans/<name>.json         eine BossScanConfig pro Datei
icon_scans/<name>.json         eine IconScanConfig pro Datei (Symbol erkennen → Aktion)
exports/<name>.zip             Import/Export-Bundles (manifest.json + alle Daten + templates/)
logs/<timestamp>_<seq>.csv     Session-Log (wenn aktiviert)
```

**Backward Compatibility ist kritisch**: Alle Loader nutzen `data.get(key, default)`. Beim Hinzufügen neuer Felder zu Dataclasses **immer** Default-Wert setzen, **nie** `data[key]` direkt verwenden. `AppConfig.from_dict()` filtert unbekannte Keys raus, sodass alte Configs gegen neuen Code laden. `tools/sync_json.py` migriert ältere Dateien wenn nötig.

### Module — wer macht was
- `main.py` — Einstiegspunkt, Hotkey-Loop, Help-Text
- `autoclicker/winapi.py` — ctypes-Bindings (Maus, Tastatur, Hotkeys, GDI). `safe_click`/`safe_key` liegen in `runtime/actions.py`.
- `autoclicker/imaging.py` — Screenshot via GDI BitBlt, OpenCV-Template-Matching, Farb-Erkennung, Region-Selektion.
- `autoclicker/llm_vision.py` — HTTP-Calls (urllib) an Ollama/LM Studio, Reasoning-Support, `<think>`-Strip, Boss-Name-Extraktion + Matching.
- `autoclicker/session_log.py` — CSV-Logger, thread-safe.
- `autoclicker/import_export.py` — ZIP-Bundle Export/Import + Koordinaten-Remapping (2-Punkt-Affine: scale + offset).
- `autoclicker/execution.py` — Backward-Compat-Shim, re-exportiert `sequence_worker`/`print_status` aus `runtime/`.
- `autoclicker/utils/` — Hilfsfunktionen: `console.py` (ANSI, Tags), `io.py` (safe_input, interactive_select), `parsing.py` (Zeit, Dateinamen).
- `autoclicker/persistence/` — JSON-Persistenz: `paths.py` (Pfade), `serialization.py` (Dataclass↔Dict), `_scan_store.py` (geteiltes Skelett für item/boss/icon-Scans: ensure_dir/write/list/load_all), `sequences.py`, `item_scans.py`, `boss_scans.py`, `icon_scans.py`, `globals.py`, `presets.py`.
- `autoclicker/runtime/` — Sequenz-Ausführung: `actions.py` (safe_click/safe_key, Humanize, `execute_else_action`), `item_scan.py` (inkl. `execute_icon_scan`), `boss_detection.py` (inkl. `_execute_detection_action` — geteilte Aktions-Ausführung für Boss + Icon), `steps.py` (Step-Dispatcher), `worker.py` (sequence_worker).
- Editor-Capture-Helfer: `editors/_detection_capture.py` (`capture_markers`, geteilt von Boss- und Icon-Editor). Aktions-Konstanten zentral in `models.py` (`ACTION_*`), Familien-Namen (`ELSE_*`/`BOSS_ACTION_*`/`ICON_ACTION_*`) sind Aliase.
- `autoclicker/handlers.py` — Hotkey-Handler (Glue-Code zwischen Hotkey und Editor/Action).
- `autoclicker/editors/` — Interaktive Console-Editoren. `sequence_editor/` und `item_editor/` sind Subpackages.

### Sequenz-Modell
Eine `Sequence` hat 3 Phasen: `init_steps` (einmalig), `loop_phases` (mehrere `LoopPhase`s je mit eigenem `repeat`-Counter, optional `scheduled_start` für Uhrzeit-Trigger), `end_steps` (einmalig nach allen Zyklen). Jeder `SequenceStep` ist polymorph: kann Klick, Key-Press, Wait-Pixel-Trigger, Item-Scan, Boss-Scan, Boss-Watcher (kontinuierliche Überwachung), Wait-only oder Screenshot sein — gesteuert über die gesetzten Felder. `else_config` definiert Fallback bei Trigger-Miss.

### Boss-Scan vs. Boss-Watcher
- **Boss-Scan**: Einmaliger Scan in einem Step. Wenn nichts erkannt → `else_config` oder Default-Action.
- **Boss-Watcher**: Schleife im Step, prüft alle `llm_watcher_interval` Sekunden bis ein Boss erkannt wird (mit `llm_watcher_max_scans` und `llm_watcher_timeout` als Exit-Bedingungen). Erst dann `_execute_boss_action`.

LLM-Modi (`use_llm` + `llm_fallback` in `BossScanConfig`):
- `llm_fallback=False` → LLM läuft **vor** Template/Marker-Matching (primär)
- `llm_fallback=True` → LLM läuft **nur wenn** Template/Marker nichts findet (Fallback)
- Bug-Sensibilität: Beide Modi dürfen LLM nicht doppelt aufrufen — siehe `execute_boss_scan()` in `runtime/boss_detection.py`.

Unbekannte Bosse (LLM erkennt einen Namen der nicht in der Liste ist) werden automatisch als `BossProfile(action=BOSS_ACTION_SKIP)` gespeichert — Append unter `state.lock`.

## Wichtige Konventionen

- **Keine neuen Dateien anlegen ohne Grund**, bestehende erweitern bevorzugt.
- **Keine neuen Markdown-Dateien**, außer explizit gefragt. `IDEAS.md` ist das Backlog für noch nicht gebaute Features mit Nutzen+Tradeoff.
- **Commit-Messages auf Deutsch**, knapper Imperativ-Stil, mehrzeilig erlaubt für Begründung.
- **Branch-Konvention**: Feature-Branches `claude/<thema>-<hash>`, Push direkt auf den Branch (kein PR ohne expliziten Auftrag).

## Bekannte Stolperfallen

- **Linux-Sandbox**: Voller Import scheitert an `msvcrt`/`ctypes.windll`. Für Korrektheits-Checks reicht `ast.parse`.
- **DPI-Awareness**: `winapi.py` setzt früh `SetProcessDpiAwareness(2)` — Skalierung ≠ 100% sollte korrekt funktionieren, aber Multi-Monitor mit unterschiedlichen DPIs ist nicht getestet.
- **OpenCV / Pillow optional**: Code prüft `OPENCV_AVAILABLE` / `PILLOW_AVAILABLE` und degradiert sauber. Neue Features die diese brauchen → Verfügbarkeit prüfen.
- **Race-Condition-Sensibel**: Lange-laufende Loops im Worker (Boss-Watcher, Item-Scan) iterieren über shared dicts — Mutationen aus Editoren können während des Laufens passieren. Im Zweifel `dict(state.x)`-Snapshot unter Lock.
