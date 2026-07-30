# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Was das ist

Windows-Autoclicker für das Spiel "Idle Clans". Konsolen-getriebene Python-App mit globalen Hotkeys, Sequenz-Editor, OpenCV-basierter Item-Erkennung und optionaler LLM-Vision für Boss-Detection (Ollama / LM Studio). Code-Sprache und alle UI-Texte sind **Deutsch** — neue Strings ebenso.

## Run / Lint / Test

```bash
python main.py                  # Startet die App (Windows only — braucht msvcrt, ctypes.windll)
python tools/test_llm.py            # Standalone-Verbindungstest für Ollama/LM Studio (nutzt llm_vision)
python tools/test_llm.py screenshot # LLM-Screenshot-Test ohne Editor-Setup
python tools/migrate.py         # Hebt alle JSON-Dateien aufs aktuelle Format (--write zum Schreiben)
                                # Nur fuer Sonderfaelle — die App macht das bei jedem Start selbst
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

### Debug-Ausgabe vs. manueller Modus (`runtime/debug.py`)
Drei Dinge, die auseinandergehalten werden müssen — sie hingen früher in einem Flag:

| | wo | was |
|---|---|---|
| Stufe 1 | `config.debug_log` | jeder Schritt als eigene Zeile statt überschreibbarer Status-Zeile |
| Stufe 2 | `config.debug_detail` | zusätzlich Zeiger auf das Ziel + ausschreiben, was kommt (Farbquadrat bei Farb-Bedingungen) |
| manuell | `state.step_mode` (Laufzeit, **keine** Config) | Wartezeiten übersprungen, jeder Schritt wartet auf Bestätigung (`w`/`s`/`c`/`q`) |

Beide Stufen sind im Punkte-Menü (`CTRL+ALT+P` → `log` / `detail`) umschaltbar und werden
sofort in `config.json` persistiert. Regeln:

- **Die Stufen ändern nur Ausgabe, nie den Ablauf.** Kein blockierender Prompt, kein
  Überspringen, keine zusätzliche Wartezeit. Wer bestätigen will, nimmt den manuellen Modus.
- **Stufe 2 zieht persistente Ausgabe mit** (`is_log_debug` ist deshalb `debug_log or
  debug_detail or step_mode`). Kein Design-Wunsch, sondern Technik: die Status-Zeile wird
  ohne `\n` geschrieben, damit sie sich selbst überschreiben kann — sobald darüber
  mehrzeilig ausgegeben wird, klebt die nächste Zeile hinten dran.
- **Nichts doppelt ausgeben.** Ist Stufe 2 an, entfällt die Ankündigungszeile von Stufe 1
  und die Ergebnis-Zeile schrumpft auf das, was die Kopfzeile nicht schon gesagt hat.
- Im Worker nie `state.config.debug_log` direkt lesen, sondern `is_log_debug(state)` —
  sonst schweigt die Stelle in Stufe 2 und im manuellen Modus.

### Hotkey-Flow
1. `winapi.py` definiert `HOTKEY_*` IDs + `register_hotkeys()` → `RegisterHotKey`.
2. `main.py` mappt IDs auf `handle_*`-Funktionen aus `handlers.py`.
3. Handler dispatcht typischerweise zu einem Editor unter `autoclicker/editors/`.
4. Editoren sind **synchron, blockierend** (Console-Input via `safe_input`). Während ein Editor läuft, ist der Main-Thread blockiert — der Worker kann parallel weiterlaufen.

Neuen Hotkey hinzufügen: Konstante in `winapi.py` (`HOTKEY_*` + `VK_*`) → `register_hotkeys()`-Liste → Handler in `handlers.py` → `hotkey_handlers` dict in `main.py` → Hilfetext in `print_help()` von `main.py`.

### Editor-Konventionen (einheitliche Substanz)
Alle Editoren sollen sich gleich anfühlen — beim Erweitern daran halten:
- **Exit**: `done`/`d` = übernehmen, `cancel`/ESC/`q` = abbrechen (via `is_cancel()`), leere Eingabe meist „zurück". Abbruch immer mit `[ABBRUCH]`-Tag melden (nicht `[CANCEL]`).
- **Transaktional**: Editoren mit Mehrfach-Bearbeitung (Item, Slot) machen `copy.deepcopy`-Snapshot am Start, mutieren in-memory, speichern bei `done`; `cancel` stellt den Snapshot wieder her (und schreibt ihn zurück, falls Unterfunktionen wie Preset-Laden zwischendurch auf Platte geschrieben haben).
- **Fehleingabe wiederholen statt abbrechen**: Zahlen-/Tasten-/Koordinaten-Eingaben fragen bei Tippfehler erneut. Geteilte Helfer in `editors/_detection_capture.py`: `select_scan_region()` (Region), `prompt_key()` (Taste), `capture_markers()` (Farb-Marker).
- **Bearbeiten = aktuellen Wert vorauswählen**: `interactive_select(..., default=<idx>)` bei Edit-Flows, damit Enter nichts überschreibt.
- **Vor Editoren mit Konsolen-Input**: `_block_if_recording(state)` + `_block_if_running(state)` aus `handlers.py` (sonst kollidiert Konsolen-Input mit Worker/Recorder). Beide melden selbst und geben `True` zurück, wenn der Handler abbrechen soll.
- **Feedback-Bausteine** aus `utils/console.py` nutzen: `ok/err/warn/info/hint`, `header`, `breadcrumb`, `cmd_hint`, `describe_color` — keine rohen ANSI-Strings.

### Referenzen statt Kopien
Zwei Stellen, an denen früher eine Kopie lag und deshalb still veraltete. Beide folgen
jetzt demselben Muster: **der globale Eintrag ist die Wahrheit, aufgelöst beim Start und
vor jedem Sequenzlauf.**

| wer verweist | worauf | Feld in der Datei | auflösen |
|---|---|---|---|
| `SequenceStep` | `points.json` | `point_id` | `resolve_point_references()` |
| `ItemScanConfig` | `slots.json`, `items.json` | `slot_names`, `item_names` | `resolve_scan_references()` |

Beim Item-Scan sind `config.slots`/`config.items` die **aufgelösten Arbeitslisten** —
Worker und Editoren nutzen sie unverändert, gespeichert werden sie nicht. `_item_scan_to_dict`
leitet die Namen aus den Objekten ab, wenn die Namenslisten leer sind; deshalb musste kein
Editor angefasst werden.

Namen, die global fehlen, werden gemeldet und übersprungen — der Scan läuft mit dem Rest
weiter. Lieber ein Slot weniger als ein toter Scan.

Beim Umbenennen bleibt `update_item_in_scans()` nötig: der Name *ist* die Referenz. Alles
andere (Marker, Template, Priorität) braucht kein Nachziehen mehr.

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
item_scans/<name>.json         eine ItemScanConfig pro Datei (verweist per Name auf slots/items)
boss_scans/<name>.json         eine BossScanConfig pro Datei
boss_scans/global/bosses.json  globale Boss-Bibliothek (state.global_bosses, gilt in jedem Boss-Scan)
icon_scans/<name>.json         eine IconScanConfig pro Datei (Symbol erkennen → Aktion)
exports/<name>.zip             Import/Export-Bundles (manifest.json + alle Daten + templates/)
logs/<timestamp>_<seq>.csv     Session-Log (wenn aktiviert)
```

**Backward Compatibility läuft über Migration, nicht über Sonderfälle im Loader**:
`persistence/migration.py` hebt geladene Dicts aufs aktuelle Schema (`schema_version`),
bevor ein Loader sie liest. Loader kennen deshalb **nur das aktuelle Format** — neue
Umstellungen kosten einen Migrationsschritt statt einer weiteren Verzweigung.

Zwei Wege, je nach Dateiform:

- **Versioniert** (`_CHAINS`) — nur Dateien mit einem Dict als oberstem Knoten, also
  heute `sequences/<name>.json`. Die tragen `schema_version`, die Kette hebt Schritt für
  Schritt (Eintrag i: Version i → i+1), Saver stempeln mit `stamp()`.
- **Normalisiert** (`_NORMALIZER`) — alles andere: `points.json` ist eine Liste,
  `items.json`/`slots.json`/Presets sind Name→Eintrag-Dicts. Da ist kein Platz für ein
  `schema_version` ohne Struktur-Umbau (ein Key „schema_version" zwischen lauter
  Item-Namen wäre ein Fremdkörper). Statt einer Kette gibt es eine **idempotente**
  Funktion: erkennt die Altform, hebt sie, zweiter Lauf ändert nichts.

Beide Wege haben denselben Zweck und dasselbe Ende: Loader lesen nur das aktuelle Format,
und sobald keine Altbestände mehr existieren, wird der Schritt bzw. Normalisierer
**ersatzlos gelöscht** — samt dem Alt-Code, den er ersetzt hat. Das Modul soll schrumpfen,
nicht wachsen. `SCHEMA_VERSION` dabei nie zurückdrehen.

Regeln beim Format-Ändern:
1. Versioniert: `SCHEMA_VERSION` hochzählen, Schritt in `_CHAINS` eintragen.
   Unversioniert: Normalisierer in `_NORMALIZER` erweitern — muss idempotent bleiben.
2. Entfallene Felder in `_DEAD_STEP_KEYS` (Schritte) bzw. `_POINT_KEYS` (Punkte)
   eintragen — dann räumt die Migration sie weg.
3. Saver stempeln mit `stamp()`, damit frisch geschriebene Dateien sauber sind.
4. `python tools/migrate.py --write` hebt alle Bestandsdateien in einem Rutsch.

**Der Durchgang läuft beim Programmstart**, nicht beim Speichern: `persistence/sweep.py`,
aufgerufen in `main.py` nach `init_directories()` und vor dem Laden (abschaltbar über
`migrate_on_start`). Speichern schreibt sowieso aktuelles Format — das Problem sind
Dateien, die man *nicht* anfasst. Nach dem ersten Start mit einer neuen Version sind alle
Dateien aktuell, und der Migrationsschritt darf gelöscht werden. Genau so schrumpft das
Modul.

`sweep.py` erfasst **alle** JSON-Dateien (config, points, sequences, item/boss/icon-Scans,
globale Bosse, items, slots, beide Preset-Ordner) und macht zwei Dinge pro Datei:
Migration/Normalisierung **und** einen Round-Trip durch Loader + Serializer. Der
Round-Trip ist die eigentliche Reinigung — was der Loader nicht kennt, schreibt der
Serializer nicht zurück. Deshalb werden auch Dateitypen ohne jeden Migrationsschritt
sauber. `tools/migrate.py` ist nur noch die CLI über derselben Funktion.

Zwei Regeln für den Start-Durchgang: **still, wenn nichts zu tun ist** (Normalfall — kein
Wort), und **nie Daten verlieren** (`.bak` vor der ersten Änderung, nicht ladbare Dateien
bleiben unangetastet). Zweiter Start muss „0 geändert" ergeben; tut er das nicht, ist ein
Schritt nicht idempotent.

**Nur gesetzte Felder werden geschrieben.** Jeder Serializer läuft durch
`_ohne_defaults(daten, tabelle)`; die Tabellen (`_ITEM_DEFAULTS`, `_SLOT_DEFAULTS`,
`_BOSS_DEFAULTS`, `_BOSS_SCAN_DEFAULTS`, `_ICON_SCAN_DEFAULTS`, `_ITEM_SCAN_DEFAULTS`,
`_STEP_DEFAULTS`) **müssen
mit den Dataclass-Defaults übereinstimmen** — sonst verschwindet ein Feld beim Speichern
und kommt beim Laden mit einem anderen Wert zurück. Ein Test prüft das gegen die
Dataclasses; beim Ändern eines Defaults immer beide Stellen anfassen.

**Ein Default darf nie aus der Config kommen.** `models.DEFAULT_MIN_CONFIDENCE` (konstant
0.8) ist der *Datei*-Default: was gilt, wenn das Feld in der JSON fehlt.
`AppConfig.scan_min_confidence` ist die *Voreinstellung für neue Profile*, die die Editoren
über `state.config` vorschlagen. Beides war früher derselbe Name — dadurch ließ der
Serializer ein Feld weg, das gerade auf dem Config-Wert stand, und beim nächsten Ändern der
Config kam es mit einem anderen Wert zurück. Zwei Dinge, zwei Namen.

Der Name steht in Name→Eintrag-Dicts nur noch im Schlüssel (`items.json`, `slots.json`,
Presets). `_item_from_dict(data, name)` und `_slot_from_dict(name, data)` bekommen ihn von
dort. In Listen (Bosse, wo die Reihenfolge Priorität ist) bleibt `name` im Eintrag.

**Speichern wird geschrieben, als gäbe es keine Altbestände.** Die Serializer schreiben
das optimale Format, nicht das kompatible: nur gesetzte Felder (`_STEP_DEFAULTS`), nur
Referenzen statt Kopien. Alles Alte hebt die Migration beim Start — und was sie nicht
heben kann, ist verloren. Das ist die bewusste Entscheidung: lieber ein optimales Format
mit einem Migrationsschritt als ein Format, das für immer seine Vorgeschichte mitträgt.

Für neue *optionale* Felder gilt weiterhin: Default in der Dataclass, `data.get(key,
default)` im Loader. Das ist kein Altlast-Fall und braucht keine Migration.
`AppConfig.from_dict()` filtert unbekannte Keys raus.

Das frühere `tools/sync_json.py` ist **gelöscht**: es pflegte fehlende Felder mit ihren
Standardwerten nach — also genau die Felder, die heute absichtlich weggelassen werden. Es
hätte jede Sequenz beim nächsten Lauf wieder aufgebläht. Alles, was es konnte, macht der
Start-Durchgang besser, weil er über Loader + Serializer geht statt über eine
handgepflegte Feldliste. (`git show <commit>^:tools/sync_json.py`, falls es je gebraucht
wird.)

### Module — wer macht was
- `main.py` — Einstiegspunkt, Hotkey-Loop, Help-Text
- `autoclicker/winapi.py` — ctypes-Bindings (Maus, Tastatur, Hotkeys, GDI). `safe_click`/`safe_key` liegen in `runtime/actions.py`.
- `autoclicker/imaging.py` — Screenshot via GDI BitBlt, OpenCV-Template-Matching, Farb-Erkennung, Region-Selektion. Templates liegen im `_template_cache` (Schlüssel: mtime+Größe der Datei), sonst würde jedes Template pro Item × Slot × Zyklus neu von Platte gelesen. Neu gelernte Templates greifen trotzdem sofort — der Schlüssel ändert sich mit.
- `autoclicker/llm_vision.py` — HTTP-Calls (urllib) an Ollama/LM Studio, Reasoning-Support, `<think>`-Strip, Boss-Name-Extraktion + Matching.
- `autoclicker/session_log.py` — CSV-Logger, thread-safe.
- `autoclicker/import_export.py` — ZIP-Bundle Export/Import + Koordinaten-Remapping (2-Punkt-Affine: scale + offset). Referenzpunkte automatisch aus der Spielfenster-Client-Größe (`winapi.get_client_rect_by_title`, Manifest-Feld `source_window`), Fallback = manuelle 2 Punkte.
- `autoclicker/execution.py` — Backward-Compat-Shim, re-exportiert `sequence_worker`/`print_status` aus `runtime/`.
- `autoclicker/utils/` — Hilfsfunktionen: `console.py` (ANSI, Tags), `io.py` (safe_input, interactive_select), `parsing.py` (Zeit, Dateinamen).
- `autoclicker/persistence/` — JSON-Persistenz: `migration.py` (Schema-Versionierung, s.o.), `paths.py` (Pfade), `serialization.py` (Dataclass↔Dict; `_*_to_dict`/`_*_from_dict` sind die EINE Quelle der Wahrheit fürs Dateiformat — von Savern UND `import_export.py` genutzt, damit beide dasselbe schreiben), `_scan_store.py` (geteiltes Skelett für item/boss/icon-Scans: ensure_dir/write/list/load_all + `LOAD_EXCEPTIONS`), `sequences.py`, `item_scans.py`, `boss_scans.py`, `icon_scans.py`, `globals.py`, `presets.py`.
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

**Globale Boss-Bibliothek**: `state.global_bosses` (Editor: Boss-Scan-Menü → "Boss-Bibliothek verwalten") gilt zusätzlich in jedem Boss-Scan. `execute_boss_scan()` merged lokal + global im Lock-Snapshot; lokale Bosse gewinnen bei Namensgleichheit. Mit `boss_learn_global=true` (Config, umschaltbar im Boss-Scan-Menü) landen neu entdeckte Bosse in der Bibliothek statt im Scan.

**Item-Auto-Lernen** (opt-in pro Scan, `ItemScanConfig.learn_unknown`): `execute_item_scan()` lernt unbekannte, nicht-leere Slot-Inhalte als neue globale Items (Kategorie 'Auto', Template + Marker) — nur nach `state.global_items`, nie in die Scan-Config, damit sie nicht ungeprüft geklickt werden. Dedup per Template-Match gegen alle globalen Items. Die Items heißen erst 'Auto <Slot>'; **die LLM-Benennung läuft bewusst NICHT im Scan** (würde den Worker pro Item bis `llm_timeout` blockieren), sondern manuell über den Item-Editor-Befehl `autoname` (`editors/item_editor/commands.py::handle_autoname_command`), der `llm_vision.suggest_item_name()` aus den gespeicherten Templates aufruft.

### Region-Auswahl (Scan-Editoren)
Boss-/Icon-Scan-Editor wählen ihre Scan-Region über `editors/_detection_capture.select_scan_region()` (Maus / manuelle Koordinaten / beibehalten). Die manuelle Eingabe wiederholt bei Fehleingabe statt den Editor abzubrechen; `None` = Abbruch (beim Bearbeiten bleibt die alte Region).

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
