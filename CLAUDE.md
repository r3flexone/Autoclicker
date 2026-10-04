# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Was das ist

Autoclicker für Windows und Linux/X11 für das Spiel "Idle Clans".
Konsolen-getriebene Python-App mit globalen Hotkeys, Sequenz-Editor,
OpenCV-basierter Item-Erkennung und optionaler LLM-Vision für Boss-Detection
(Ollama / LM Studio). Wayland wird nicht unterstützt. **Bezeichner im Code sind
Englisch, alles Gelesene ist Deutsch** — Kommentare, Docstrings, UI-Texte,
Meldungen, Testbeschreibungen; neue Strings ebenso (s. „Bezeichner auf
Englisch" bei den Konventionen).

## Wo die Details stehen

Diese Datei ist der Kern: Befehle, Architektur und die Regeln, die überall
gelten. Die Begründungen — warum etwas so gebaut ist und welcher Weg schon
einmal schiefging — stehen in `CLAUDE.md`-Dateien der Unterordner. Claude Code
lädt sie selbst, sobald eine Datei aus diesem Ordner gelesen wird; wer dort
etwas ändert, ohne vorher eine Datei daraus gelesen zu haben (etwa nur per
Suche), liest sie vorher.

| Datei | worum es geht |
|---|---|
| `tests/CLAUDE.md` | wie die Testschichten gebaut sind, CI-Matrix, Gegenproben, Rauchtest-Prüfstand |
| `autoclicker/CLAUDE.md` | Template-Vergleich mit Lernmaske, Item-Katalog und LLM-Benennung, Session-Log, Import/Export |
| `autoclicker/runtime/CLAUDE.md` | Aktions-Wrapper, Debug-Stufen und manueller Modus, Sequenz-Modell und ELSE, Nachprüfung, Laufstatus und Lebenszeichen, Boss-Erkennung, „Ab hier starten“, Folgesequenz |
| `autoclicker/persistence/CLAUDE.md` | Referenzen statt Kopien, Dateiformat, Start-Durchgang, Namen als Schlüssel, Sequenzwechsel |
| `autoclicker/editors/CLAUDE.md` | Konsolen-Editoren, Aufnahme und ihre Marker, Klick-Runde, Koordinaten nach einem Bildschirm-Umbau |
| `autoclicker/editors/sequence_studio/CLAUDE.md` | das Sequenz-Studio: Brücke, Reiter, Bedien- und Gestaltungsregeln |
| `autoclicker/platforms/CLAUDE.md` | Plattform-Schicht Windows/X11 |

**Was dort steht, gilt genauso wie das hier.** Ausgelagert ist es, weil man es
nur braucht, wenn man an der Stelle arbeitet: vorher stand alles in dieser einen
Datei, über 300 KB, die jede Sitzung vollständig lud. Neue Begründungen gehören
in die Datei des Ordners, um den es geht — hierher nur, was überall gilt. Ein
Test hält die Tabelle gegen die vorhandenen Dateien, in beide Richtungen.

## Run / Lint / Test

```bash
python tests/all_tests.py      # ALLE Tests, ein Aufruf — das vor einem Commit
python tests/all_tests.py --only contract    # nur die Vertragssuite (schnell)
python tests/all_tests.py --only smoke --smoke-test tools   # eine Ansicht
python tests/all_tests.py --mutations      # dazu die Gegenproben (so ruft CI es auf)
python tests/all_tests.py --only smoke --smoke-required  # fehlender Browser = rot
python -m flake8                # Linter — Regeln stehen in `.flake8`, kein Argument noetig
python -m flake8 --select=F,C90 autoclicker/ market_analysis/ main.py tools/ tests/
                                # dasselbe ausgeschrieben (so ruft CI es auf)

# Die Schichten einzeln, falls man sie direkt braucht:
python tests/test_logic.py      # Vertragssuite — ohne GUI, ohne Windows, ohne Netz
python -m tests.root_tests      # Wurzelmodule (--without-contract laesst den Wrapper weg)
python -m tests.smoke.tools     # ein Rauchtest im Browser
python tests/mutation_check.py         # Gegenproben einzeln (--case NAME)
python tools/catalog.py         # Item-/Gegner-Katalog aus der Spiel-API holen
                                # (--show = nur anzeigen, --target = anderer Pfad)

python main.py                  # Startet die App auf Windows oder Linux/X11
python tools/test_llm.py            # Standalone-Verbindungstest für Ollama/LM Studio (nutzt llm_vision)
python tools/test_llm.py screenshot # LLM-Screenshot-Test ohne Editor-Setup
python tools/llm_bench.py           # Misst die LLM-Benennung gegen den eigenen Bestand
                                    # (--image slot|background, --model X, --all-models,
                                    #  --two-stage, --votes 3, --reasoning)
python tools/migrate.py         # Hebt alle JSON-Dateien aufs aktuelle Format (--write zum Schreiben)
                                # Nur fuer Sonderfaelle — die App macht das bei jedem Start selbst
python tools/slot_tester.py     # Debug-Tool für Slot-Erkennung
python tools/log_report.py      # Wertet die Session-Logs aus (welcher Schritt haengt?)
                                # --last = nur die neueste Session
python tools/symbol.py          # Schreibt das Programm-Symbol als PNG + ICO
                                # (fuer Verknuepfungen; das Fenstersymbol setzt die App selbst)
```

**Ein Kommando, drei Schichten: `python tests/all_tests.py`.**

| Schicht | was sie prüft | braucht |
|---|---|---|
| Vertragssuite (`tests/test_logic.py`) | Logik ohne GUI, ohne Windows, ohne Netz | nichts |
| Wurzelmodule (`tests/root/`) | Import/Export-Sicherheit, Plattformvertrag, Studio-UX, Runtime-Härtung | Pillow (sonst übersprungen) |
| Rauchtests (`tests/smoke/`) | die echte Seite im Browser vor der echten Brücke | Playwright + Chromium |

Was man beim Schreiben von Tests wissen muss (Begründungen in `tests/CLAUDE.md`):

- **Alle Schichten laufen in einem eigenen Ordner, nie im Repo** (auch die
  Gegenproben) — die Pfade der App sind CWD-relativ. Repo-Dateien liest ein
  Test über `REPO` bzw. `ROOT`, nie über einen relativen Pfad, und ein
  Wurzelmodul startet man über `python -m tests.root_tests`, nicht mit einem
  nackten `unittest discover` aus dem Repo.
- **Was fehlt, wird übersprungen und gesagt**, nicht als Fehler gemeldet
  (OpenCV, Pillow, Browser) — ausser mit `--smoke-required`.
- **Ein grüner Exitcode ist kein grüner Lauf**: die Vertragssuite muss mit
  `N PASS / 0 FAIL` (N > 0) enden.
- **Neue Vertragssektionen** kommen als Modul nach `tests/contract/`; die erste
  Zeile ist `from ._harness import check, section`, importiert wird es am Ende
  von `tests/test_logic.py`. **Neue Rauchtests** bekommen eine Datei unter
  `tests/smoke/` und einen Eintrag in `SMOKE_TESTS`; gewartet wird mit
  `settle()` auf die Seite, nicht auf die Uhr.
- **CI** (`.github/workflows/tests.yml`, Push und PR auf jedem Branch): Ubuntu
  und Windows, Python 3.14, der Test-Job in drei Achsen (`ohne`/`pillow`/`mit`
  Bildpaketen), dazu Rauchtests und `flake8 --select=F,C90`. Jeder Job muss grün
  sein. Wer an `imaging.py` arbeitet, installiert die Bildpakete auch lokal.
- **`--mutations` prüft die Tests, nicht den Code**: jeder Fall in
  `tests/mutation_check.py` entschärft eine Sicherung und erwartet, dass ein
  bestimmter Test darüber rot wird.

Regeln beim Erweitern:
- **Jeder Bugfix bekommt einen Test**, der ohne den Fix umfällt. Gegenprobe: Fix
  entschärfen, Test muss rot werden. Ein Test, der auch ohne den Fix grün bleibt,
  prüft etwas anderes als er behauptet.
- **Nicht die Implementierung abschreiben, sondern beide Seiten messen.** Wo Editor und
  Runtime dieselbe Regel kennen müssen, fragt der Test beide und vergleicht.
- **Was der Stub anders macht als Windows, wird auf beiden Seiten geprüft** — mit
  `if sys.platform == "win32":` und einem `else`-Zweig, nie nur die eine Hälfte. Die
  Geometrie-Helfer (`get_virtual_desktop` & Co.) liefern gestubbt `None`/`(0,0)`/`(960,540)`
  und auf echtem Windows reale Werte; als der Test nur den Stub-Fall festschrieb, stand die
  Suite auf der *Zielplattform* dauerhaft auf 4× FAIL. Eine Suite, die dort rot ist, wo die
  App läuft, verdeckt echte Regressionen im Rauschen. Unter Windows prüft man deshalb die
  Eigenschaft (Rechteck hat Fläche, Mitte liegt darin), nicht den konkreten Wert — der hängt
  am Monitor-Setup.

## Architektur

### Threading-Modell
- **Main-Thread**: Pumpt die Hotkey-Ereignisse des gewählten Plattform-Backends
  (`main.py`), dispatcht zu Handlern und blockiert beim Editor-Input.
- **Worker-Thread**: `sequence_worker()` in `autoclicker/runtime/worker.py` — führt die aktive Sequenz aus.
- **Geteilter State**: `AutoClickerState` (in `models.py`) mit `state.lock` (threading.Lock) und mehreren Events (`stop_event`, `pause_event`, `skip_event`, `restart_event`, `skip_cycle_event`, `quit_event`, `finish_event`).

**Pattern für State-Mutationen**: Jede Lese-/Schreib-Operation auf `state.global_items`, `state.global_slots`, `state.boss_scans`, `state.item_scans`, `state.points`, `state.clicked_categories`, Zähler etc. **muss** unter `with state.lock:` laufen. Persistenz-Funktionen in `autoclicker/persistence/` machen einen Snapshot unter Lock und schreiben die Datei ausserhalb. Datei-Saves laufen crash-sicher über `atomic_write()` (Temp-Datei + `os.replace`, in `utils/parsing.py`) — bei Absturz bleibt die alte Datei intakt statt korrupt.

### Aktions-Wrapper (zentral)
Alle Klicks und Tastendrücke im Worker laufen über `safe_click(state, x, y, label)` und `safe_key(state, key, label)` in `autoclicker/runtime/actions.py`. Diese bündeln:
1. **Window-Fokus-Check** (`window_focus_check` in Config — pausiert oder stoppt wenn Ziel-Fenster nicht aktiv)
2. **Humanization** (Mikro-Delays, Klick-Jitter, periodische Breaks)
3. **Session-Logging** (CSV-Event)

Beim Hinzufügen neuer Klick/Key-Aktionen im Worker: **immer** über die Wrapper gehen, nie direkt `send_click`/`send_key` aufrufen. Sonst umgehen sie Fokus-Check + Humanize + Log.

Was im Worker sonst noch gilt (Begründungen in `autoclicker/runtime/CLAUDE.md`):

- `safe_click`/`safe_key` fragen Stopp, Pause und Fokus **nach** allen
  Wartezeiten noch einmal (`_input_allowed()`). Ein `False` heisst verweigert
  **oder** vom System nicht angenommen — `input_refused()` trennt beides. **Den
  Block-Skip verbraucht nur `execute_step`**, nie ein Handler darunter.
- **Jede Schleife, die den Worker länger aufhält**, ruft `status.heartbeat(state)`
  oder `status.waiting_for()` — sonst sieht ein wartender Lauf im Studio tot aus.
- **Debug-Stufen ändern nur die Ausgabe, nie den Ablauf**; wer bestätigen will,
  nimmt den manuellen Modus (`state.step_mode`). Im Worker `is_log_debug(state)`
  lesen, nie `config.debug_log` direkt. Die Status-Zeile schreibt
  `status_line()` in einem Zug.
- **Sequenz-Modell**: `init_steps` (einmal), `loop_phases` (je mit `repeat`,
  optional `scheduled_start`), `end_steps` (einmal danach). **`else` ist ein
  *stattdessen*** und feuert nur bei einer nicht erfüllten Bedingung (Farbe,
  Nachprüfung, Scan ohne Treffer). Vorab-Entscheidungen geben
  `GATE_RUN`/`GATE_SKIP`/`GATE_STOP` zurück; wer eine else-Aktion auslöst, gibt
  `GATE_SKIP` zurück.

### Hotkey-Flow
1. `winapi.py` definiert `HOTKEY_*` IDs + `register_hotkeys()` → `RegisterHotKey`.
2. `main.py` mappt IDs auf `handle_*`-Funktionen aus `handlers.py`.
3. Handler dispatcht typischerweise zu einem Editor unter `autoclicker/editors/`.
4. Editoren sind **synchron, blockierend** (Console-Input via `safe_input`). Während ein Editor läuft, ist der Main-Thread blockiert — der Worker kann parallel weiterlaufen.

Neuen Hotkey hinzufügen: ID in `platforms/common.py` (`HOTKEY_*`, betriebssystemneutral), Tastencode im jeweiligen Backend (`VK_*` in `platforms/windows.py`) → `register_hotkeys()`-Liste **beider** Backends → Handler in `handlers.py` → `hotkey_handlers` dict in `main.py` → Hilfetext in `print_help()` von `main.py`.

**`CTRL+ALT+<Buchstabe>` ist voll.** 24 der 26 Buchstaben sind vergeben, frei blieben
nur R (oft vom System belegt) und Y. Wer eine neue Taste braucht, nimmt **nicht** die
letzten zwei, sondern eine Ebene mit `MOD_SHIFT`. Dafür gibt es `MOD_REC`
(`CTRL+ALT+SHIFT+…`), und die trägt eine Bedeutung: **was dort liegt, wirkt nur während
eines laufenden Vorgangs** — die Marker während einer Aufnahme, `SHIFT+K` während
eines Laufs. Der Buchstabe darf derselbe bleiben wie in der Basis-Ebene,
solange die Bedeutung verwandt ist — `M`/`SHIFT+M` sind beide „warte auf eine Farbe",
`D`/`SHIFT+D` beide „Screenshot", `K`/`SHIFT+K` beide „überspringen" (die Wartezeit
bzw. den ganzen Block). Der Block-Skip hatte vorher nur den Studio-Knopf und den
Briefkasten-Befehl `skip_step`; wer aus der Konsole lief, konnte einen hängenden
Block nur mit dem ganzen Lauf abbrechen. Der Hotkey ruft **denselben**
`handle_skip_step()` wie der Knopf — ein Ereignis, zwei Wege.

Dass die Marker nicht in der Aufnahme landen, ist kein Zufall: der Tastatur-Hook meldet
nichts bei gedrücktem CTRL oder ALT, und beide sind hier gedrückt.

Beim Start läuft nur `print_banner()` (vier Zeilen). Die volle Hilfe zeigt `print_help()` — automatisch beim allerersten Start (keine Punkte, keine Sequenzen, keine Items) und sonst auf `CTRL+ALT+O`. Neue Hotkeys gehören trotzdem in `print_help()`, nicht in den Banner: der bleibt kurz.

### Konsolen-Editoren, Aufnahme, Klick-Runde (Kurzfassung)

Alle Editoren sollen sich gleich anfühlen: `done`/`d` übernimmt, `cancel`/ESC/`q`
bricht ab (`is_cancel()`, gemeldet als `[ABBRUCH]`), Fehleingaben werden
wiederholt statt abzubrechen, Mehrfach-Bearbeitung ist transaktional (Snapshot
am Start). Vor einem Editor mit Konsolen-Eingabe stehen `_block_if_recording()`
und `_block_if_running()`. Menüs lesen Tasten mit `read_command()`, nicht mit
`read_key()`. Lange Assistenten werden in Stufen zerlegt — nur so bekommen sie
Tests.

Aufnahme (`sequence_recorder.py`) und Klick-Runde (`reclick.py`) laufen aus dem
Maus-Hook: alles geht mit EINEM globalen Tastendruck, gespeichert wird erst am
Ende und nicht im Hook, und welches Fenster einen Klick bekam, sagt
`clicked_window()` (das Fenster unter dem Zeiger, nicht das vorderste).
Begründungen, die Marker-Tabelle und die Wege nach einem Bildschirm-Umbau:
`autoclicker/editors/CLAUDE.md`.

### Referenzen statt Kopien (Kurzfassung)

**Eine Koordinate steht im Punkt der Sequenz, sonst nirgends.** Schritte (Klick,
Vorbedingung, Nachprüfung, ELSE-Klick) sowie die Klicks von Items, Bossen und
Icons zeigen per ID auf einen Punkt im Feld `points` der `sequence.json`; die IDs
gelten nur innerhalb dieser Sequenz. `x/y`, Name und Farbe an Schritt,
Bedingung und Profil sind abgeleitete Arbeitswerte und stehen nicht in der
Datei. Daraus folgt:

- **Wer im Editor eine Stelle erzeugt, legt einen Punkt an**:
  `point_for_position()` gibt eine ID zurück und nimmt einen vorhandenen Punkt
  an derselben Stelle wieder (`point_at_position()`: Radius **und** Farbe).
- **Aufgelöst wird beim Laden** (`resolve()`), und `resolve()` ändert nie das
  Modell, nur das Arbeits-Flag `unresolved`. **Es gibt keinen Rückfallwert**:
  ein Schritt, dessen Punkt fehlt, wird übersprungen und gemeldet — nie auf
  (0, 0) geklickt.
- **Jeder Klick-Schritt wird MIT `point_id` gebaut**, ein Block ohne Stelle
  (`POSITIONLESS_BLOCKS`) hat keinen.
- **Ein Scan besitzt seine Slots und Items** und wird selbst per Namen gerufen,
  an fünf Stellen (`_REF_FIELDS` in `scan_contract.py`); wer umbenennt, zieht
  alle nach.

Details und die Tabelle aller Verweise: `autoclicker/persistence/CLAUDE.md`.

### Persistenz-Layout

**Eine Sequenz ist eine Besitzeinheit, kein Bündel von Dateitypen.** Alles, was zu
ihr gehört — Punkte, Scans, Vorlagen, gemerkte Bildschirme —, liegt unter
`sequences/<name>/`. Programmweit bleibt nur, was wirklich keiner Sequenz gehört:
Config, Presets, Exporte, Sicherungen, Logs.

```
config.json                              AppConfig (alle Settings)

sequences/<name>/sequence.json           die Sequenz SAMT ihrer Punkte (Feld `points`)
sequences/<name>/item_scans/<n>.json     ItemScanConfig — Slots und Items stehen DARIN
sequences/<name>/boss_scans/<n>.json     BossScanConfig
sequences/<name>/boss_scans/bibliothek.json   Boss-Bibliothek (gilt in jedem Boss-Scan
                                              DIESER Sequenz), Liste statt Scan
sequences/<name>/icon_scans/<n>.json     IconScanConfig (Symbol erkennen → Aktion)
sequences/<name>/templates/<n>.png       Item-Vorlagen (per Dateiname referenziert)
sequences/<name>/bilder/<n>.png          je Item-Scan ein eingefrorener Bildschirm

presets/slots/<name>.json                Slot-Presets      (programmweit)
presets/items/<name>.json                Item-Presets      (programmweit)
exports/<name>.zip                       Import/Export-Bündel (manifest.json + Sequenzordner)
backups/<pfad>.bak                       Sicherungen des Start-Durchgangs (Struktur gespiegelt)
screenshots/                             Screenshot-Schritte zur Laufzeit
logs/<timestamp>_<seq>.csv               Session-Log (wenn aktiviert)

.run.json                               Laufstatus fuer das Sequenz-Studio (transient)
.recording.json                           letzte 3 Ereignisse der Aufnahme (transient)
.reclick.json                          Stand der Klick-Runde (transient)
.command.json                             Briefkasten Studio → Hauptprozess (transient)
.studio-sequence.json                     zuletzt geoeffnete/gespeicherte Sequenz (transient)
.last-scan.png                            was der letzte Item-Scan gesehen hat (transient)
```

Die Regeln dazu (Begründungen in `autoclicker/persistence/CLAUDE.md`):

- **Neue Formatänderungen brauchen KEINEN Migrationsschritt** — eine
  ausdrückliche Entscheidung des Nutzers. Default in der Dataclass,
  `data.get(key, default)` im Loader, fertig. Eine alte Datei darf ein Feld auf
  dem Standardwert bekommen, den Loader aber nie werfen.
- **Speichern schreibt das optimale Format**: nur gesetzte Felder
  (`_without_defaults()`; die `_*_DEFAULTS`-Tabellen müssen mit den
  Dataclass-Defaults übereinstimmen), nur Referenzen, nie Kopien.
- **Der Start-Durchgang** (`persistence/sweep.py`) bringt alle Dateien über
  Loader + Serializer auf den heutigen Stand: still, wenn nichts zu tun ist,
  `.bak` unter `backups/` vor der ersten Änderung.
- **Ein Name, der Schlüssel ist, wird nie doppelt vergeben**: `next_free_name()`
  für Serien, `unique_name()` für einen kollidierenden Namen. Bei Sequenzen ist
  der Schlüssel der **Ordner** — `sanitize_filename()` gehört an den Pfad, nie
  an den Anzeigenamen.
- **Wer die Sequenz wechselt, ruft `activate_sequence(state, seq)`** — Sequenz,
  Punkte und Scans in einem Zug; ein Test verbietet jede andere Zuweisung an
  `.active_sequence`.
- **Ein Saver sagt, ob er gespeichert hat** (`bool`); wer danach „gespeichert“
  meldet, prüft den Rückgabewert.

### Bilderkennung, Katalog und LLM (Kurzfassung)

- **Ein Template vergleicht nur das Item, nicht den Slot**: beim Lernen entsteht
  eine Hintergrundmaske im Alpha-Kanal des Template-PNG, verglichen wird nur über
  die deckenden Pixel. Templates ohne Alpha bleiben, wie sie sind.
- **Namen und Kategorien kommen aus dem Item-Katalog** (`tools/catalog.py` holt
  ihn aus der Spiel-API, `autoclicker/catalog.py` liest die Datei — kein Import
  zwischen beiden). Ob ein Scan ihn benutzt, entscheidet
  `ItemScanConfig.use_catalog`; die Kategorie wird ENG gebildet, und der Katalog
  trägt keine Priorität, nur den Wert.
- **Ein LLM-Aufruf kann lange dauern** (Kaltstart): ein Timeout ist nicht „nicht
  erkannt“ und wird einmal mit mehr Zeit wiederholt. Im laufenden Item-Scan wird
  nie per LLM benannt. Ob eine Änderung etwas bringt, misst `tools/llm_bench.py`.

Details: `autoclicker/CLAUDE.md`.

### Module — wer macht was
- `main.py` — Einstiegspunkt, Hotkey-Loop, Help-Text
- `autoclicker/winapi.py` — **Fassade** über das Plattform-Backend (Maus, Tastatur, Hotkeys, Fenster, Bildschirm-Geometrie); die Implementierungen liegen in `platforms/` (s.u.). `safe_click`/`safe_key` liegen in `runtime/actions.py`.
- `autoclicker/symbol.py` — das Programm-Symbol als Geometrie (s. `editors/sequence_studio/CLAUDE.md`). Kennt weder Windows noch Pillow: es rechnet nur, wie viel Farbe auf einen Pixel fällt.
- `autoclicker/imaging.py` — Screenshot über das Plattform-Backend, OpenCV-Template-Matching, Farb-Erkennung, Region-Selektion. Templates liegen im `_template_cache` (Schlüssel: mtime+Grösse der Datei), sonst würde jedes Template pro Item × Slot × Zyklus neu von Platte gelesen. Neu gelernte Templates greifen trotzdem sofort — der Schlüssel ändert sich mit.
- `autoclicker/config_meta.py` — was `AppConfig` über ein Feld nicht sagt: Beschriftung, Erklärung, Art des Bedienelements, Abhängigkeit. Einzige Quelle für den Einstellungen-Reiter des Sequenz-Studios; ein Test hält sie gegen die Dataclass (s. `editors/sequence_studio/CLAUDE.md`).
- `autoclicker/llm_vision.py` — HTTP-Calls (urllib) an Ollama/LM Studio, Reasoning-Support, `<think>`-Strip, Boss-Name-Extraktion + Matching.
- `autoclicker/ocr.py` — Texterkennung über EasyOCR oder Tesseract (`ocr_backend`, `None` = automatisch). Wie OpenCV/Pillow **optional**: `is_available()` prüfen, sauber degradieren. Liefert `detect_boss_name()` für `runtime/boss_detection.py`.
- `autoclicker/diagnostics.py` — Selbstdiagnose: fehlende Templates, Profile ohne jede Erkennungsmethode, tote Slot-/Item-/Scan-Verweise, Punkte ausserhalb aller Monitore. Beim Start ohne Sequenzdateien und still wenn sauber (`check_on_start`), auf Zuruf vollständig (Punkte-Menü → `check`).
- `autoclicker/session_log.py` — CSV-Logger, thread-safe. Ausgewertet mit `tools/log_report.py`, auf der Kommandozeile und im Reiter „Bericht“ über dieselbe `evaluate()`; wer eine neue Ereignisart einführt, trägt sie dort ein.
- `autoclicker/catalog.py` — liest den Item-Katalog, den `tools/catalog.py` aus der Spiel-API holt (Verbindung über eine Datei, kein Import).
- `autoclicker/import_export.py` — ZIP-Bundle Export/Import + Koordinaten-Remapping (2-Punkt-Affine: scale + offset). Referenzpunkte automatisch aus der Spielfenster-Client-Grösse (`winapi.get_client_rect_by_title`, Manifest-Feld `source_window`), Fallback = manuelle 2 Punkte.
- `autoclicker/utils/` — Hilfsfunktionen: `console.py` (ANSI, Tags), `io.py` (safe_input, interactive_select), `parsing.py` (Zeit, Dateinamen).
- `autoclicker/persistence/` — JSON-Persistenz: `migration.py` (Schema-Versionierung, s. `persistence/CLAUDE.md`), `paths.py` (Pfade), `serialization.py` (Dataclass↔Dict; `_*_to_dict`/`_*_from_dict` sind die EINE Quelle der Wahrheit fürs Dateiformat — von Savern UND `import_export.py` genutzt, damit beide dasselbe schreiben), `_scan_store.py` (geteiltes Skelett für item/boss/icon-Scans: ensure_dir/write/list/load_all + `LOAD_EXCEPTIONS`), `sequences.py`, `item_scans.py`, `boss_scans.py`, `icon_scans.py`, `globals.py`, `presets.py`.
- `autoclicker/runtime/` — Sequenz-Ausführung: `actions.py` (safe_click/safe_key, Humanize, `execute_else_action`), `item_scan.py` (inkl. `execute_icon_scan`), `boss_detection.py` (inkl. `_execute_detection_action` — geteilte Aktions-Ausführung für Boss + Icon), `steps.py` (Step-Dispatcher), `worker.py` (sequence_worker), `status.py` (Laufstatus für
  Beobachter ausserhalb des Prozesses).
- `autoclicker/mailbox.py` — der Briefkasten Studio → Hauptprozess (`.command.json`); `runtime/status.py` ist der Rückweg (`.run.json`). Liegt bewusst nicht unter `runtime/`, damit das Fenster den Worker nicht nachzieht.
- `autoclicker/editors/sequence_studio/` — das Studio-Fenster (pywebview, eigener Prozess); seine Module stehen in seiner `CLAUDE.md`.
- Editor-Capture-Helfer: `editors/_detection_capture.py` (`capture_markers`, geteilt von Boss- und Icon-Editor). `editors/_click_window.py` (`clicked_window`, geteilt von Aufnahme und Klick-Runde — den beiden Editoren, die aus dem Maus-Hook laufen). Aktions-Konstanten zentral in `models.py` (`ACTION_*`), Familien-Namen (`ELSE_*`/`BOSS_ACTION_*`/`ICON_ACTION_*`) sind Aliase.
- `autoclicker/handlers.py` — Hotkey-Handler (Glue-Code zwischen Hotkey und Editor/Action).
- `autoclicker/editors/` — Interaktive Console-Editoren. `sequence_editor/` und `item_editor/` sind Subpackages. Zwei Ausnahmen laufen aus den Hook-Callbacks statt aus Konsolen-Eingaben: `sequence_recorder.py` (die Aufnahme) und `reclick.py` (die Klick-Runde, die Punkte durch Nachklicken kalibriert) — beide in `editors/CLAUDE.md`.
- `market_analysis/` — **eigenständiges Subsystem, nicht Teil des Autoclickers.** Zieht Marktpreise und Rezepte aus der Idle-Clans-API und rechnet Gold/h pro Item (`analysis.py`, `verify.py`, `apicheck.py`, `config.py`). Importiert **nichts** aus `autoclicker/`, braucht kein Windows, hat eigene Abhängigkeiten (pandas/requests/openpyxl) und ein eigenes `market_analysis/README.md` — das ist dort die Wahrheit, nicht diese Datei. Generiertes landet in `market_analysis/output/` (gitignored). Wer am Autoclicker arbeitet, fasst den Ordner nicht an; wer an der Analyse arbeitet, umgekehrt.

  **Die eine Verbindung ist eine Datei, kein Import.** `export_market_values()` schreibt
  `output/marktwert.json` (Item-Name → Verkaufswert je Stück, `sale_values()` in
  `market_analysis/pricing.py`); trägt man den Pfad in der
  `config.json` des Autoclickers unter `scan_market_value_file` ein, sortiert der
  Item-Scan seine Klicks danach statt nach der von Hand getippten `priority`
  (`load_market_values()` in `runtime/item_scan.py`, zwischengespeichert am mtime — eine
  neu gerechnete Analyse greift ohne Neustart). Zwei Tests messen die Trennung im
  **Import-Baum** (nicht im Text: in Kommentaren darf stehen, woher die Datei kommt).

  **Nachgeschlagen wird mit `market_value()`, nie mit `.get()`.** Die Analyse schreibt
  die Namen der Spiel-API (`oak_log`), der Autoclicker kennt dasselbe Item als
  `Oak Log`; `market_key()` vergleicht ohne Gross-/Kleinschreibung, Unterstrich gleich
  Leerzeichen. Bis zum 04.10.2026 stand in der Datei die Marge der Rohdaten unter dem
  Rezeptnamen (`oak`, `titanium_platebody: -2430`) und wurde exakt verglichen — sie
  traf kein Item, und hätte sie getroffen, wären die wertvollsten zuletzt geklickt
  worden.

  Zwei Eigenschaften, die man kennen muss: die gespeicherte `item.priority` wird
  **nicht** überschrieben — die Sortierung gilt nur für den Lauf, `items.json` bleibt
  unberührt. Und **jedes Item mit Marktwert gewinnt gegen jedes ohne**, weil der Wert
  negiert einsortiert wird. Das ist gewollt (ein gemessener Wert schlägt eine getippte
  Zahl), heisst aber: was nicht in der Tabelle steht, rutscht nach hinten. Wer das nicht
  will, lässt `scan_market_value_file` leer — dann ändert sich gar nichts.

### Sequenz-Studio (Kurzfassung)

Das Studio ist EIN Fenster in einem eigenen Prozess (pywebview; `CTRL+ALT+B`, mit
`CTRL+ALT+V` direkt im Scans-Reiter) — ein Fenster-Event-Loop und die
Hotkey-Message-Pump vertragen sich nicht im selben Thread. Seine Oberfläche ist
eine Webseite ohne Build-Schritt und ohne Nachladen von aussen. Sie hält
**keinen** Sequenz-Zustand, sondern zeichnet die Momentaufnahme der Brücke
(`StudioBridge`) und schickt jede Änderung als Befehl zurück: `call()` ersetzt die
Momentaufnahme, `ask()` fragt nur. Gemeinsamer Nenner mit dem Hauptprozess ist
die **Datei**; Start, Pause und Stopp gehen über den Briefkasten.

**Neue Bedienelemente kommen als Methode ins zuständige Bridge-Mixin**, nicht
als Logik ins JavaScript — nur so bleiben sie messbar; die Oberfläche ist der
ungetestete Teil und soll klein bleiben. Die Regeln für Bedienung und Gestaltung
(gleiche Spalten statt Textbreite, ⓘ statt Erklärungsabsatz, Zustand ringsum
markieren, Kacheln für feste Auswahl, Listen für Wachsendes, Rückgängig über
vollständige Abzüge) stehen in `autoclicker/editors/sequence_studio/CLAUDE.md`.

## Wichtige Konventionen

- **Keine neuen Dateien anlegen ohne Grund**, bestehende erweitern bevorzugt.
- **Keine neuen Markdown-Dateien**, ausser explizit gefragt. `IDEAS.md` ist das Backlog für noch nicht gebaute Features mit Nutzen+Tradeoff.
- **Commit-Messages auf Deutsch**, knapper Imperativ-Stil, mehrzeilig erlaubt für Begründung.
- **Branch-Konvention**: Feature-Branches `claude/<thema>-<hash>`, Push direkt auf den Branch (kein PR ohne expliziten Auftrag).

### Bezeichner auf Englisch, Sprache auf Deutsch

**Was der Rechner liest, ist Englisch; was der Mensch liest, ist Deutsch.**
Funktionen, Klassen, Variablen, Parameter, Modul- und Dateinamen, JS-Funktionen,
CSS-Klassen, die Methoden und JSON-Schlüssel der Brücke, die Befehle des
Briefkastens, Konsolenbefehle und CLI-Flags — Englisch. Kommentare, Docstrings,
UI-Texte, Meldungen, Hilfetexte, Testbeschreibungen (`check("…")`,
`section("…")`), Commit-Messages und diese Datei — Deutsch. Ein String, der
angezeigt wird, ist Sprache; ein String, der etwas *adressiert*
(`call("block_set")`, `"start_manual"`, ein Dispatch-Schlüssel), ist Code.

**Wer eine Stelle anfasst und dort noch einen deutschen Namen findet, benennt
ihn um — samt allen Aufrufern.** Eine halb umbenannte Funktion (Definition
englisch, drei Aufrufer deutsch) gibt es nicht; flake8 `--select=F` findet
den Rest, die Suite den Rest vom Rest. Drei Stellen, an denen ein Name mehr
ist als ein Name und deshalb auf beiden Seiten geändert werden muss:

- **Keyword-Argumente, die zu JSON-Schlüsseln werden**: `send_command("show",
  point=…)` schreibt `{"point": …}` in den Briefkasten, und der Empfänger liest
  `.get("point")`.
- **Die Seite hängt am DOM**: `t.dataset.view` ist das Attribut `data-view` in
  `index.html`; `S.question` ist zugleich der JSON-Schlüssel, den die Brücke
  schreibt. Ein Klick, der ins Leere geht, ohne `pageerror` — alle acht
  Rauchtests rot —, ist fast immer dieser Fall.
- **Tests, die JS-Quelltext als Python-String tragen** (`… in _html18`,
  `page.evaluate(…)` in den Rauchtests) zitieren den Namen wörtlich.

**Bewusst deutsch** — weil es gelesen wird, nicht gerufen:

- Testmethoden-Namen (`def test_sequenzwechsel_entfernt_fremden_bestand`) —
  sie sind die Beschreibung, die im Lauf ausgegeben wird, dasselbe wie
  `check("…")`.
- Die Matrix-Achsen `ohne`/`pillow`/`mit` in `tests.yml` — Beschriftungen
  der CI-Jobs, und diese Datei nennt sie so.
- Konsolen-Eingabewörter, die neben dem englischen weiter gelten (`klick`,
  `weg`, `maus`): sie werden getippt, nicht gerufen.
- Schlüssel gespeicherter Dateien (s. u.) und die Spaltennamen der
  SQLite-Historie in `market_analysis/` — Daten, kein Code.

**Schlüssel in gespeicherten Dateien bleiben, wie sie sind** —
`config.json`, `sequence.json`, `catalog.json`, `marktwert.json`. Das sind
Daten, kein Code; wer sie umbenennt, verstellt den Bestand des Nutzers. Sie
bleiben, bis eine Formatänderung sie ohnehin anfasst — und dann gilt die Regel
von oben: Default in der Dataclass, kein Migrationsschritt.

**Ein Begriff, ein Wort.** Damit nicht jede Stelle ihre eigene Vokabel
erfindet, gilt dieses Glossar; wer ein neues Wort braucht, trägt es hier ein:

| deutsch | englisch | | deutsch | englisch |
|---|---|---|---|---|
| Punkt | point | | Momentaufnahme | snapshot |
| Stelle | position | | Briefkasten | mailbox |
| Sequenz / Phase / Block | sequence / phase / step | | Befehl (Briefkasten) | command |
| Bestand | inventory | | Lauf / Laufstatus | run / run status |
| Vorlage | template | | Haltepunkt | breakpoint |
| Aufnahme | recording | | Klick-Runde | reclick round |
| Scan / Slot / Item | scan / slot / item | | Werkzeuge / Bericht / Teilen | tools / report / share |
| Brücke | bridge | | Einstellungen | settings |
| Maske (Listeneintrag) | card | | Kachel | tile |
| Rückgängig | undo | | Marke | badge |
| laden / speichern | load / save | | zeichnen | render |
| setzen / anlegen / löschen | set / create / delete | | prüfen | check |
| holen | fetch | | melden | report |
| wählen / Auswahl | select / selection | | Treffer | match |
| Verwendung | usage | | Ertrag | yield |

### Altlasten werden entfernt, nicht mitgeschleppt

**Wer etwas umbaut, räumt das Alte weg — im selben Zug.** Rückwärtskompatibilität
„für alle Fälle" ist hier ausdrücklich *kein* Wert. Das Projekt wird von einer Person
benutzt, es gibt keine fremden Abhängigkeiten und keine API-Zusagen; ein
Kompatibilitätspfad kostet also nur, ohne je etwas einzubringen.

Diese Haltung steckt schon in mehreren Regeln oben — hier steht sie als das, was sie
ist: **die allgemeine Regel, von der jene die Sonderfälle sind.**

- Migration: „Das Modul soll schrumpfen, nicht wachsen." Ein Schritt wird
  **ersatzlos gelöscht**, sobald keine Altbestände mehr existieren — samt dem
  Alt-Code, den er ersetzt hat. **Das ist einmal vollständig passiert:** die
  Sequenz-Kette ist leer, und mit ihren vier Schritten fielen `_sichere_neue_punkte`,
  `_punkte_schreibfertig`, `_als_dicts`, `_STELLEN`, `_DEAD_STEP_KEYS` sowie rund
  vierzig Tests weg. Die Regel ist also nicht nur aufgeschrieben, sondern eingelöst.
- Serializer: „Speichern wird geschrieben, als gäbe es keine Altbestände."
- `tools/sync_json.py` wurde gelöscht statt gepflegt; die Normalisierer der
  Migration, `_FIELD_MIGRATION` der Config, `reload_points`, `_REF_KEYS`, die
  sieben Import-Flags und das Mausrad sind ihm gefolgt.

Drei Sorten Altlast, die auffallen sollen:

| Sorte | Beispiel aus diesem Repo | warum weg |
|---|---|---|
| **Weiterleitung ohne Inhalt** | `execution.py` — reiner Re-Export, Docstring sagte selbst „damit main.py und handlers.py ihre Imports unverändert lassen können" | eine Datei, deren einziger Zweck ist, zwei Zeilen nicht anzufassen |
| **Name eines Paradigmas, das es nicht mehr gibt** | `node_editor`, `node_canvas`, `BlockGraph`, `rebuild_canvas` nach dem Umbau auf Listen | ein Name, der etwas Falsches verspricht, ist dieselbe Sorte Fehler wie eine Oberfläche, die es tut — er führt den nächsten Leser in die Irre |
| **Totes Feld / toter Zweig** | `_sichere_neue_punkte()` nach dem Löschen der Migrationskette — es wartete auf ein Ereignis, das nicht mehr eintritt | Pflegeaufwand für etwas, das nie passiert |

Zwei Einschränkungen, damit daraus keine Zerstörungswut wird:

- **Daten dürfen einen Default bekommen, aber nicht den Loader werfen.** Früher
  stand hier „Bestandsdateien werden über die Migration gehoben, nicht
  fallengelassen". Das gilt nur noch für das, was schon eine Migration hat: für
  Neues ist ein Migrationsschritt ausdrücklich **nicht** mehr nötig (s. o. bei
  der Persistenz). Ein Feld, das eine alte Datei nicht kennt, bekommt seinen
  Standardwert — einen Scan im Studio neu zu bauen ist billiger als ein
  Migrationsschritt. Kaputtgehen darf trotzdem nichts: unlesbar ist ein Fehler,
  auf dem Standardwert ist keiner.
- **Eine Begründung ist keine Altlast.** Steht irgendwo, *warum* etwas nicht mehr so
  gebaut ist (z. B. „war mal ein `dpg.node_editor`, deshalb …"), bleibt das stehen.
  Genau diese Sätze verhindern, dass jemand den alten Weg noch einmal einschlägt.

Umbenennungen mit `git mv` machen — dann erkennt Git sie als Rename und die Historie
der Datei bleibt lesbar.

### Plattform-Schicht (Kurzfassung)

Das Betriebssystem steht in einem Backend (`platforms/windows.py`,
`platforms/linux_x11.py`), gewählt in `platforms/load_backend()`; alles andere
importiert die Fassade `autoclicker.winapi`. Windows-spezifischer Code steht nur
in `platforms/windows.py`, `utils/io.py` und `utils/console.py` — ein Test hält
das in beide Richtungen fest. Wer einen Systemaufruf braucht, erweitert den
Vertrag in `platforms/base.py` und implementiert ihn in **beiden** Backends.
Bildschirm-Geometrie kommt aus `winapi.get_virtual_desktop()` und seinen
Geschwistern, nie aus einem eigenen `GetSystemMetrics`. Details:
`autoclicker/platforms/CLAUDE.md`.

## Bekannte Stolperfallen

- **Headless Linux**: Der vollständige Import und die automatischen
  Plattformverträge laufen. Echte Hotkeys, Eingabe, Fenster und Screenshots
  brauchen für den manuellen Test eine X11-Sitzung. Wayland wird bewusst
  abgelehnt.
- **DPI-Awareness**: `platforms/windows.py` setzt früh `SetProcessDpiAwareness(2)` — Skalierung ≠ 100% sollte korrekt funktionieren. **Multi-Monitor mit unterschiedlichen DPIs ist weiterhin nicht getestet.** Verifiziert ist dagegen der Fall, über den man zuerst stolpert: Monitore mit **negativen** Koordinaten (links vom bzw. über dem primären). BitBlt, der ImageGrab-Fallback, `get_pixel_color` und Regionen quer über Monitorgrenzen liefern dort korrekt — die Offset-Rechnung über `SM_XVIRTUALSCREEN`/`SM_YVIRTUALSCREEN` stimmt. Beim Debuggen beachten: `get_virtual_desktop()` gibt ein **Rechteck** (links, oben, rechts, unten) zurück, keine Breite/Höhe — die Breite ist `rechts - links`, und bei negativem Ursprung ist das nicht dasselbe.
- **Nicht-DPI-aware Werkzeuge lügen über die Monitor-Geometrie.** Koordinaten aus PowerShell (`System.Windows.Forms.Screen`) oder anderen Prozessen ohne DPI-Awareness sind skaliert und passen nicht zu denen, die die App sieht. Zum Nachmessen einen Prozess nehmen, der `autoclicker.winapi` importiert hat.
- **OpenCV / Pillow optional**: Code prüft `OPENCV_AVAILABLE` / `PILLOW_AVAILABLE` und degradiert sauber. Neue Features die diese brauchen → Verfügbarkeit prüfen.
- **Der erste OCR-Aufruf lädt Modelle aus dem Netz.** EasyOCR holt beim allerersten `read_text()` Detection- und Recognition-Modell per Download — Sekunden bis Minuten, und es kann mit HTTP-Fehler scheitern; danach liegt ein Aufruf bei ~300 ms. Passiert das im Worker, steht die Sequenz so lange. Dieselbe Klasse Problem wie beim LLM, weshalb die LLM-Benennung bewusst nicht im Scan läuft (s.o.). Wer `ocr_enabled` neu einschaltet, sollte den ersten Aufruf nicht in einen laufenden Scan legen.
- **`import_bundle()` schreibt sofort auf Platte, `export_bundle()` nicht.** Der Import kopiert ganze Sequenzordner an ihren Platz und ruft **`save_config()`** — er befüllt also nicht bloss den State. Mit einem frischen `AutoClickerState()` schreibt `save_config()` die Default-Config über die vorhandene `config.json`; die Tests in `test_logic.py` übergeben deshalb `import_config=False`. Für einen vollen Roundtrip die Pfad-Relativität nutzen: Datenordner + `config.json` in einen Temp-Ordner kopieren und vorher dorthin `os.chdir()` — die Konstanten in `persistence/paths.py` sind bewusst CWD-relativ.
- **Race-Condition-Sensibel**: Lange-laufende Loops im Worker (Boss-Watcher, Item-Scan) iterieren über shared dicts — Mutationen aus Editoren können während des Laufens passieren. Im Zweifel `dict(state.x)`-Snapshot unter Lock.
