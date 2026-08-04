# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Was das ist

Windows-Autoclicker für das Spiel "Idle Clans". Konsolen-getriebene Python-App mit globalen Hotkeys, Sequenz-Editor, OpenCV-basierter Item-Erkennung und optionaler LLM-Vision für Boss-Detection (Ollama / LM Studio). Code-Sprache und alle UI-Texte sind **Deutsch** — neue Strings ebenso.

## Run / Lint / Test

```bash
python tools/test_logic.py      # DIE Test-Suite — laeuft auch auf Linux/Mac, Exit 0 = gruen
python3 -m pyflakes autoclicker/ main.py tools/    # Linter

python main.py                  # Startet die App (Windows only — braucht msvcrt, ctypes.windll)
python tools/test_llm.py            # Standalone-Verbindungstest für Ollama/LM Studio (nutzt llm_vision)
python tools/test_llm.py screenshot # LLM-Screenshot-Test ohne Editor-Setup
python tools/migrate.py         # Hebt alle JSON-Dateien aufs aktuelle Format (--write zum Schreiben)
                                # Nur fuer Sonderfaelle — die App macht das bei jedem Start selbst
python tools/slot_tester.py     # Debug-Tool für Slot-Erkennung
```

**`tools/test_logic.py` vor jedem Commit laufen lassen.** Es prüft Serialisierung,
Migration, Runtime-Gates, Kalibrierung, Tastenbelegung und die Plattform-Grenze — ohne
GUI, ohne Windows, ohne Netz. `msvcrt` und `ctypes.windll` werden am Dateianfang gestubbt;
deshalb läuft die komplette Logik-Schicht auch hier.

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

Nur was echtes Windows braucht (Klicks, Screenshots, Hotkeys) bleibt ungetestet. Die Suite
läuft auch dort — sie prüft dann die Windows-Seite der plattformabhängigen Checks. Auf einer
cp1252-Konsole bricht sie allerdings mit `UnicodeEncodeError` ab (die Ausgabe nutzt
Box-Zeichen); unter Windows deshalb mit `PYTHONIOENCODING=utf-8` starten, falls die Konsole
nicht ohnehin auf UTF-8 steht.

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

Beim Start läuft nur `print_banner()` (vier Zeilen). Die volle Hilfe zeigt `print_help()` — automatisch beim allerersten Start (keine Punkte, keine Sequenzen, keine Items) und sonst auf `CTRL+ALT+O`. Neue Hotkeys gehören trotzdem in `print_help()`, nicht in den Banner: der bleibt kurz.

### Editor-Konventionen (einheitliche Substanz)
Alle Editoren sollen sich gleich anfühlen — beim Erweitern daran halten:
- **Exit**: `done`/`d` = übernehmen, `cancel`/ESC/`q` = abbrechen (via `is_cancel()`), leere Eingabe meist „zurück". Abbruch immer mit `[ABBRUCH]`-Tag melden (nicht `[CANCEL]`).
- **Transaktional**: Editoren mit Mehrfach-Bearbeitung (Item, Slot) machen `copy.deepcopy`-Snapshot am Start, mutieren in-memory, speichern bei `done`; `cancel` stellt den Snapshot wieder her (und schreibt ihn zurück, falls Unterfunktionen wie Preset-Laden zwischendurch auf Platte geschrieben haben).
- **Fehleingabe wiederholen statt abbrechen**: Zahlen-/Tasten-/Koordinaten-Eingaben fragen bei Tippfehler erneut. Geteilte Helfer in `editors/_detection_capture.py`: `select_scan_region()` (Region), `prompt_key()` (Taste), `capture_markers()` (Farb-Marker).
- **Bearbeiten = aktuellen Wert vorauswählen**: `interactive_select(..., default=<idx>)` bei Edit-Flows, damit Enter nichts überschreibt.
- **Vor Editoren mit Konsolen-Input**: `_block_if_recording(state)` + `_block_if_running(state)` aus `handlers.py` (sonst kollidiert Konsolen-Input mit Worker/Recorder). Beide melden selbst und geben `True` zurück, wenn der Handler abbrechen soll.
- **Feedback-Bausteine** aus `utils/console.py` nutzen: `ok/err/warn/info/hint`, `header`, `breadcrumb`, `cmd_hint`, `describe_color` — keine rohen ANSI-Strings.
- **Mehrfachauswahl aus einer Liste**: `mehrfach_auswahl()` aus `editors/item_scan_editor.py`
  (`<Nr>`, `<Von>-<Bis>`, `all`, `clear`, `show`, `done`, `cancel`, optional ein eigener
  Befehl wie `new <Slot-Nr>`). Sie stand vorher zweimal ausgeschrieben da — für Slots und
  für Items —, und eine Korrektur an der einen ging an der anderen vorbei.

**Assistenten in Stufen zerlegen, nicht am Stück schreiben.** `edit_item_scan()` war
450 Zeilen mit 125 Verzweigungen; jetzt ruft sie `_schritt_presets` → Auswahl → Auswahl →
`_schritt_toleranz` → `_schritt_auto_lernen` und speichert. Jede Stufe gibt ihr Ergebnis
zurück oder signalisiert Abbruch (`None` bzw. `False`). Das ist auch der einzige Weg, an
Editor-Code überhaupt Tests zu bekommen: was nur `safe_input` braucht, lässt sich mit
einer Tastenfolge füttern — `mehrfach_auswahl` hat so 24 Tests, wo vorher keiner war.

### Referenzen statt Kopien
Überall dort, wo früher eine Kopie lag und deshalb still veraltete, gilt jetzt dasselbe
Muster: **der globale Eintrag ist die Wahrheit, aufgelöst beim Start und vor jedem
Sequenzlauf.**

| wer verweist | worauf | Feld in der Datei | auflösen |
|---|---|---|---|
| `SequenceStep` | `points.json` | `point_id` | `aufloesen()` / `resolve_point_references()` |
| `WaitCondition` | `points.json` | `wait_point_id` | dito |
| `ElseConfig` | `points.json` | `else_point_id` | dito |
| `ItemProfile` | `points.json` | `confirm_point_id` | `resolve_klick_referenzen()` |
| `BossProfile` | `points.json` | `action_point_id` | dito |
| `IconScanConfig` | `points.json` | `action_point_id` | dito |
| `ItemScanConfig` | `slots.json`, `items.json` | `slot_names`, `item_names` | `resolve_scan_references()` |

Beim Item-Scan sind `config.slots`/`config.items` die **aufgelösten Arbeitslisten** —
Worker und Editoren nutzen sie unverändert, gespeichert werden sie nicht.

**Eine Koordinate steht in `points.json`, sonst nirgends.** Das gilt ausnahmslos für alle
drei Stellen eines Schritts: den Klick, den Prüf-Pixel und den Else-Klick. `step.x/y`,
`step.name`, `step.recorded_color`, `wait_condition.pixel/color` und `else_config.x/y/name`
sind **abgeleitete Arbeitswerte** — im Speicher gefüllt, in der Datei nicht vorhanden.
Dasselbe Muster wie `ItemScanConfig.slots`, nur konsequenter.

Dieselbe Regel gilt außerhalb der Sequenzen: `ItemProfile.confirm_point`,
`BossProfile.action_x/y` und `IconScanConfig.action_x/y` sind ebenfalls abgeleitet.
`resolve_klick_referenzen()` (in `persistence/item_scans.py`) füllt sie und läuft in
`main.py` **nach** dem Laden aller Scans — `load_all_item_scans()` sieht die Boss- und
Icon-Scans an seiner Stelle noch gar nicht, deren Klicks stünden sonst bis zum ersten
Sequenzlauf auf (0, 0).

Für diese drei gibt es **bewusst keine Migration**: die alten Koordinaten ließen sich
zwar in Punkte heben, aber der Weg dorthin — die Punkte-Liste durch jeden Item-, Boss-
und Icon-Loader reichen — kostet mehr, als das Feld einmal neu zu setzen. Der Loader
meldet ein Altfeld stattdessen einmal pro Fundstelle (`_alt_gemeldet` in
`serialization.py`) und nennt den Editor, in dem es neu gesetzt wird. Still verschwinden
darf es nicht.

Warum so streng: eine Koordinate an zwei Stellen ist eine Koordinate, die an einer der
beiden falsch sein kann. Wer die Sequenzdatei liest, sah dann etwas anderes als das, was
die App klickt — und bei einer Kalibrierung musste jede Kopie einzeln erwischt werden.
`kalibriere_bestand()` rechnet Sequenz-Klickstellen deshalb **nicht mehr** um: die Punkte
sind schon umgerechnet, ein zweiter Durchgang hieße doppelt verschoben.

**Es gibt bewusst keinen Rückfallwert.** Zeigt eine `point_id` ins Leere, setzt
`aufloesen()` `step.unresolved = True`; `step_gate()` überspringt den Schritt und sagt
warum. Ein Schritt, der ersatzweise auf eine veraltete Kopie klickt, ist schlimmer als
einer, der stehenbleibt — und ohne Kopie wäre die Alternative ein Klick auf (0, 0).

Regeln beim Erweitern:
- **Wer im Editor eine Stelle erzeugt, legt einen Punkt an**: `punkt_fuer_stelle(state, x,
  y, color, name)` gibt die ID zurück, nie ein Koordinatenpaar. Die Funktion verwendet
  einen vorhandenen Punkt an derselben Stelle wieder — klickt eine Sequenz zweimal
  denselben Knopf, ist das EIN Punkt, sonst wandert beim Nachjustieren nur die Hälfte mit.
- **Aufgelöst wird beim Laden**, nicht erst vor dem Lauf: `load_sequence_file()` holt sich
  die Punkte notfalls selbst. Von den neun Aufrufern haben sechs keinen Punkte-Pool zur
  Hand (Node-Editor, Canvas, Export) — die bekämen sonst lauter Nullen.
- **Eine vierte Stelle** trägt man in `_STELLEN` (Migration), `_REF_KEYS`
  (`import_export.py`) und `aufloesen()` ein. Fehlt einer der drei, überlebt sie den
  nächsten Import oder die nächste Migration nicht.

**Die Namen sind die Wahrheit, die Objekte werden abgeleitet.** `ItemScanConfig.sync_names()`
(aufgerufen in `__post_init__` und in `resolve_scan_references()`) füllt fehlende
Namenslisten aus den Objekten. Ohne das hinterlässt jede Seite eine halbe Config, und beide
Richtungen gehen kaputt:

- Editoren und Scan-Studio bauen die Config aus **Objekten** → ohne Namen leerte
  `resolve_scan_references()` beim nächsten Sequenzstart die Objekte wieder. Ein gerade
  bearbeiteter Scan lief bis zum Neustart ins Leere.
- Der Loader baut sie aus **Namen** → ohne Objekte zeigte das Menü „0 Slots, 0 Items" und
  beim Bearbeiten war nichts vorausgewählt.

Regel beim Erweitern: **Anzeige und Vorauswahl immer über `slot_names`/`item_names`**, nie
über `slots`/`items` — die sind erst nach dem Auflösen gefüllt. Wer `config.slots` von außen
setzt, ruft danach `sync_names()`.

Namen, die global fehlen, werden gemeldet und übersprungen — der Scan läuft mit dem Rest
weiter. Lieber ein Slot weniger als ein toter Scan.

Beim Umbenennen bleibt `update_item_in_scans()` nötig: der Name *ist* die Referenz. Alles
andere (Marker, Template, Priorität) braucht kein Nachziehen mehr.

**Jeder Klick-Schritt wird MIT `point_id` gebaut**, nicht nachträglich verknüpft. Ein Test
(`kein Klick-Schritt wird ohne point_id gebaut`) prüft jede `SequenceStep(...)`-Konstruktion
im Baum; ausgenommen sind Schritte ohne echte Position (Taste, Scan, Wait, Screenshot) und
der Blanko-Block `(0, 0)` des Node-Editors, der noch gar keine Stelle hat.

Darauf zu vertrauen, dass die Migration schon nachverknüpft, reicht **nicht**: sie läuft nur
auf Dateien mit altem Schema. Frisch Gespeichertes trägt bereits die aktuelle Version und
wird nie angefasst. Genau daran hing der Recorder — er legte Schritte und Punkte unabhängig
voneinander an, und jede aufgenommene Sequenz blieb dauerhaft unverknüpft.

**Den Altbestand holt die Migration nach, nicht der Nutzer.** `_seq_v2_to_v3` verknüpft
Aufnahmen von vor dem Fix beim nächsten Start automatisch — sie standen ja schon auf
Schema 2 und wurden von der Kette nie angefasst.

`_seq_v3_to_v4` geht einen Schritt weiter: es **legt notfalls einen Punkt an**. Bliebe auch
nur ein Schritt unverknüpft, müsste seine Koordinate weiterhin in der Sequenz stehen — und
die ganze Regel hätte wieder eine Ausnahme. Deshalb gilt hier auch nicht mehr „mehrdeutige
Stellen bleiben unverknüpft": liegen zwei Punkte übereinander, gewinnt der erste. Dieselbe
Stelle ist derselbe Ort; unverknüpft hieße jetzt *Koordinate weg*.

**Angelegte Punkte müssen auf Platte.** Die Migration hängt sie an die Liste in
`context["points"]`, und der Aufrufer schreibt sie: `sweep.py` am Ende des Durchgangs
(points.json zuletzt, erst dann steht die Zahl fest), `load_sequence_file()` über
`_sichere_neue_punkte()` für alle anderen Wege. Die Liste wird deshalb **durchgereicht,
nicht kopiert** (`_als_dicts`) — mit einer Kopie sähe die zweite Sequenz die Punkte der
ersten nicht, vergäbe dieselben IDs erneut, und points.json hätte zwei Einträge mit
derselben ID. Drei Tests pinnen das fest.

Das ist der vorgesehene Weg für so etwas: **neue Daten entstehen korrekt, Altlasten gehen
einmal durch die Schleuse.** `link` im Sequenz-Editor bleibt für die Fälle, die die
Migration nicht eindeutig auflösen kann — nicht Teil des normalen Wegs. Sobald keine
Altbestände mehr existieren, werden `_seq_v2_to_v3` und `_seq_v3_to_v4` ersatzlos gelöscht.

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

Genau das ist mit `_norm_items` passiert (steht heute als `_norm_noop`): es hob
`confirm_point` von `[x, y]` auf `{x, y}` — ein Feld, das der Loader seit der Umstellung
auf `confirm_point_id` gar nicht mehr liest. Einen Normalisierer zu pflegen, der ein
totes Feld in ein anderes totes Format bringt, ist das Anwachsen, das hier vermieden
werden soll.

Regeln beim Format-Ändern:
1. Versioniert: `SCHEMA_VERSION` hochzählen, Schritt in `_CHAINS` eintragen.
   Unversioniert: Normalisierer in `_NORMALIZER` erweitern — muss idempotent bleiben.
2. Entfallene Felder in `_DEAD_STEP_KEYS` (Schritte) bzw. `_POINT_KEYS` (Punkte)
   eintragen — dann räumt die Migration sie weg.
3. Saver stempeln mit `stamp()`, damit frisch geschriebene Dateien sauber sind.
4. `python tools/migrate.py --write` hebt alle Bestandsdateien in einem Rutsch.

**Ein Migrationsschritt läuft genau so lange, wie es etwas zu heben gibt.** `migrate()`
ruft zwar jeder Loader auf (ein Test erzwingt das), aber die Schleife
`while version < SCHEMA_VERSION` ist bei einer aktuellen Datei leer: kein Schritt, keine
Änderung, kein Schreibzugriff. Gemessen an einer Sequenz auf Schema 2:

| | Kette läuft |
|---|---|
| 1. Start | ja — Datei wird gehoben und zurückgeschrieben |
| 2./3. Start | **nein** |
| 20× Sequenz laden | **nein** |

Ein Test pinnt das fest (`weitere Starts rufen keinen Migrationsschritt mehr auf`).

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

**Weil der Name der Schlüssel ist, darf er nie doppelt vergeben werden.** Ein zweiter
Eintrag mit demselben Namen ersetzt den ersten kommentarlos — und weil Scans ihre Slots
und Items *per Name* referenzieren, zeigt der Scan danach nicht ins Leere, sondern auf den
neuen Eintrag: er läuft weiter und tut etwas anderes. `len(...) + 1` als Namensvorschlag
trägt das nicht, sobald einmal gelöscht oder umbenannt wurde. Wer einen Namen automatisch
vergibt, nimmt einen der beiden Helfer aus `utils/parsing.py`; wer einen vom Nutzer
eingegebenen Namen übernimmt, fragt vor dem Überschreiben (`create_slot`, `create_item`
machen das vor).

| Helfer | wofür | Beispiel |
|---|---|---|
| `naechster_freier_name(praefix, vorhandene)` | durchnummerierte **Serien** — füllt Lücken | `Slot 1`, `Slot 2`, … |
| `eindeutiger_name(basis, vorhandene)` | ein **vorgegebener** Name, der kollidiert | `Beutel oben` → `Beutel oben 2` |

Für Serien immer den ersten: ein angehängter Zähler ergäbe `Slot 3 2`, und das liest
niemand gern.

Dieselbe Regel gilt für **Identität außerhalb der Persistenz**: Loop-Phasen-Namen sind
frei wählbar und doppelt vergebbar, deshalb hängt der Zeitplan-Zustand im Worker an der
*Position* der Phase, nicht an ihrem Namen (`_schedule_watcher`). Ein Name ist eine
Beschriftung — als Schlüssel taugt er nur da, wo etwas ihn erzwingt.

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
- `autoclicker/ocr.py` — Texterkennung über EasyOCR oder Tesseract (`ocr_backend`, `None` = automatisch). Wie OpenCV/Pillow **optional**: `is_available()` prüfen, sauber degradieren. Liefert `detect_boss_name()` für `runtime/boss_detection.py`.
- `autoclicker/diagnose.py` — Selbstdiagnose: fehlende Templates, Profile ohne jede Erkennungsmethode, tote Slot-/Item-/Scan-Verweise, Punkte ausserhalb aller Monitore. Beim Start ohne Sequenzdateien und still wenn sauber (`check_beim_start`), auf Zuruf vollständig (Punkte-Menü → `check`).
- `autoclicker/session_log.py` — CSV-Logger, thread-safe.
- `autoclicker/import_export.py` — ZIP-Bundle Export/Import + Koordinaten-Remapping (2-Punkt-Affine: scale + offset). Referenzpunkte automatisch aus der Spielfenster-Client-Größe (`winapi.get_client_rect_by_title`, Manifest-Feld `source_window`), Fallback = manuelle 2 Punkte.
- `autoclicker/execution.py` — Backward-Compat-Shim, re-exportiert `sequence_worker`/`print_status` aus `runtime/`.
- `autoclicker/utils/` — Hilfsfunktionen: `console.py` (ANSI, Tags), `io.py` (safe_input, interactive_select), `parsing.py` (Zeit, Dateinamen).
- `autoclicker/persistence/` — JSON-Persistenz: `migration.py` (Schema-Versionierung, s.o.), `paths.py` (Pfade), `serialization.py` (Dataclass↔Dict; `_*_to_dict`/`_*_from_dict` sind die EINE Quelle der Wahrheit fürs Dateiformat — von Savern UND `import_export.py` genutzt, damit beide dasselbe schreiben), `_scan_store.py` (geteiltes Skelett für item/boss/icon-Scans: ensure_dir/write/list/load_all + `LOAD_EXCEPTIONS`), `sequences.py`, `item_scans.py`, `boss_scans.py`, `icon_scans.py`, `globals.py`, `presets.py`.
- `autoclicker/runtime/` — Sequenz-Ausführung: `actions.py` (safe_click/safe_key, Humanize, `execute_else_action`), `item_scan.py` (inkl. `execute_icon_scan`), `boss_detection.py` (inkl. `_execute_detection_action` — geteilte Aktions-Ausführung für Boss + Icon), `steps.py` (Step-Dispatcher), `worker.py` (sequence_worker).
- Editor-Capture-Helfer: `editors/_detection_capture.py` (`capture_markers`, geteilt von Boss- und Icon-Editor). Aktions-Konstanten zentral in `models.py` (`ACTION_*`), Familien-Namen (`ELSE_*`/`BOSS_ACTION_*`/`ICON_ACTION_*`) sind Aliase.
- `autoclicker/handlers.py` — Hotkey-Handler (Glue-Code zwischen Hotkey und Editor/Action).
- `autoclicker/editors/` — Interaktive Console-Editoren. `sequence_editor/` und `item_editor/` sind Subpackages. `sequence_recorder.py` ist die Ausnahme: kein Editor, sondern die Aufnahme (s.o.) — sie läuft aus den Hook-Callbacks, nicht aus Konsolen-Eingaben.
- `market_analysis/` — **eigenständiges Subsystem, nicht Teil des Autoclickers.** Zieht Marktpreise und Rezepte aus der Idle-Clans-API und rechnet Gold/h pro Item (`analyse.py`, `verify.py`, `apicheck.py`, `config.py`). Importiert **nichts** aus `autoclicker/`, braucht kein Windows, hat eigene Abhängigkeiten (pandas/requests/openpyxl) und ein eigenes `market_analysis/README.md` — das ist dort die Wahrheit, nicht diese Datei. Generiertes landet in `market_analysis/output/` (gitignored). Wer am Autoclicker arbeitet, fasst den Ordner nicht an; wer an der Analyse arbeitet, umgekehrt.

**Die zwei GUI-Werkzeuge laufen als eigener Prozess**, nicht im Hauptprozess: der
Dear-PyGui-Event-Loop und die Windows-Hotkey-Message-Pump vertragen sich nicht im selben
Thread. Gestartet werden sie vom Handler per `subprocess.Popen([sys.executable, "-m", ...])`,
Dear PyGui ist optional und wird beim Start des Subprozesses geprüft.

| Einstiegspunkt | Canvas | arbeitet auf |
|---|---|---|
| `autoclicker/scan_studio.py` (`handle_scan_studio`) | `editors/scan_canvas/` | `slots/slots.json` |
| `autoclicker/node_editor.py` (`handle_node_editor`) | `editors/node_canvas/` | `sequences/<name>.json` |

Daraus folgt: **beide Seiten kennen die Änderungen der anderen erst nach dem Neuladen.**
Der Subprozess liest die Datei beim Start und schreibt sie beim Speichern; der
Hauptprozess hält seinen eigenen Stand im Speicher und lädt mit `CTRL+ALT+L` nach. Wer im
Hauptprozess speichert, während der Subprozess offen ist, verliert eine der beiden
Fassungen. Beim Erweitern also nichts einbauen, das auf gemeinsamen State setzt — der
gemeinsame Nenner ist die Datei.

### Sequenz-Modell
Eine `Sequence` hat 3 Phasen: `init_steps` (einmalig), `loop_phases` (mehrere `LoopPhase`s je mit eigenem `repeat`-Counter, optional `scheduled_start` für Uhrzeit-Trigger), `end_steps` (einmalig nach allen Zyklen). Jeder `SequenceStep` ist polymorph: kann Klick, Key-Press, Wait-Pixel-Trigger, Item-Scan, Boss-Scan, Boss-Watcher (kontinuierliche Überwachung), Wait-only oder Screenshot sein — gesteuert über die gesetzten Felder. `else_config` definiert Fallback bei Trigger-Miss.

**`else` ist ein *stattdessen*, kein *zusätzlich*.** Greift die else-Aktion, entfällt die
eigene Aktion des Schritts — so steht es in der Editor-Hilfe (`else skip` = „nur DIESEN
Schritt überspringen", `else <Punkt-Nr>` = „**stattdessen** diesen Punkt klicken").

Damit das durchsetzbar ist, reicht ein bool nicht: er kann „Schritt erledigt, weiter zum
nächsten" nicht von „Sequenz abbrechen" unterscheiden. Beides als `False` zu melden riss
den Rest der Phase mit ab, beides als `True` ließ den Schritt nach der else-Aktion noch
sein eigenes Ziel klicken. Deshalb geben Vorab-Entscheidungen über einen Schritt
`GATE_RUN` / `GATE_SKIP` / `GATE_STOP` zurück (Konstanten in `runtime/debug.py`,
genutzt von `step_gate` und `_execute_wait_for_color`).

Regel beim Erweitern: **wer eine else-Aktion auslöst, gibt `GATE_SKIP` zurück** — nie
`GATE_RUN` und nie stumpf `True`. Die Übersetzung macht `_gate_nach_else()`; nur
`restart`/`skip_cycle` werden zu `GATE_STOP`. Step-Handler, die die else-Aktion als
Letztes tun und danach nichts mehr ausführen (Item-/Boss-/Icon-Scan), dürfen weiterhin
`return execute_else_action(...)` — dort gibt es keine nachgelagerte eigene Aktion, die
irrtümlich noch feuern könnte.

### Sequenz-Aufnahme (`editors/sequence_recorder.py`)
Aufgezeichnet wird, was das Spielen ausmacht: **Linksklick, Tastendruck, Mausrad** und
per `CTRL+ALT+M` ein **Warte-Marker auf eine Farbe**. Jedes Ereignis ist ein
`RecordEvent` (`models.py`, `REC_*`) — rein transient, wird nie gespeichert;
`stop_recording()` baut daraus Schritte und wirft die Liste weg.

**Alles muss mit EINEM globalen Tastendruck gehen.** Während der Aufnahme steht der
Nutzer im Spiel, nicht in der Konsole — ein blockierender Prompt käme nie an. Nachfragen
sind erst beim Stoppen möglich, und dort passieren sie auch (Name, Zyklen, Beschreibung).

Drei Regeln, an denen die Aufnahme hängt:

- **Der Warte-Marker hat keine eigene Stelle.** Er wird gedrückt, sobald man anfängt zu
  warten — die Maus parkt dabei irgendwo, und diese Position wäre reiner Zufall. Ein
  erster Entwurf legte darauf einen Punkt an; in einer echten Aufnahme stand da dann
  `Warte auf Farbe bei (4483, 1038) Schwarz (3,4,5)`, also Müll in `points.json`.
- **Gewartet wird auf die Farbe DES Klicks, der folgt.** Der Marker hängt sich an ihn
  und macht daraus einen Schritt: „warte auf die Farbe dieser Stelle, dann klicke sie" —
  ein Punkt, zweimal referenziert (`point_id` + `wait_point_id`), exakt das, was
  `color <Nr>` im Editor baut. Die beim Klick erfasste Farbe ist die richtige: geklickt
  wird ja erst, wenn das Erwartete zu sehen ist. Folgt dem Marker kein Klick (sondern
  eine Taste oder gar nichts), wird er verworfen und gemeldet — `marker_pruefen()`.
- **Der Marker hält nur die Uhr an.** Die Zeit *bis* zu seinem Drücken bleibt echte
  Wartezeit, die Zeit *danach* fällt weg — sie ist genau das Warten, das die Bedingung
  ersetzt. Bliebe sie stehen, würde die Sequenz erst auf die Farbe warten UND danach
  nochmal die volle Zeit schlafen (in der echten Aufnahme: 434 s).

Warten an einer **anderen** Stelle als der geklickten kann die Aufnahme bewusst nicht —
dafür gibt es `wait <Punkt-Nr> color` im Editor. Der Marker wäre sonst wieder auf eine
Position angewiesen, die beim Drücken niemand bewusst wählt.

`CTRL+ALT+U` nimmt während der Aufnahme das letzte Ereignis zurück, sonst den letzten
Punkt — gleiche Bedeutung, der Gegenstand hängt am Zustand. Kein eigener Buchstabe: von
den 26 sind nur noch D/R/Y frei.

Der **Tastatur-Hook** meldet nichts bei gedrücktem CTRL oder ALT (dort liegen die
Hotkeys — sonst stünde ein `j` in der Sequenz, sobald man mit `CTRL+ALT+J` stoppt),
nichts, was `send_key()` nicht abspielen kann, und keine Wiederholung einer
festgehaltenen Taste. Er ist die Kür: schlägt er fehl, läuft die Aufnahme ohne ihn
weiter — eine Aufnahme ohne Klicks wäre dagegen sinnlos. Beide Hooks werden auch beim
Beenden entfernt (`handle_quit`), sonst hängt ein Tastatur-Hook systemweit weiter.

**Rechtsklick wird bewusst nicht aufgezeichnet**: der Autoclicker kann gar keinen
ausführen (`send_click` ist auf `LEFTDOWN`/`LEFTUP` festgelegt, es gibt kein Modellfeld
und keinen Editor-Befehl). Ihn mitzuschneiden hieße, etwas aufzunehmen, das beim
Abspielen zum Linksklick wird. Wer ihn nachrüstet, braucht die ganze Kette:
`winapi` → Modellfeld → `safe_click` → Serializer-Default → Editor-Anzeige.

Der Hook liefert beim Mausrad die **rohe** Windows-Distanz, nicht schon Rasterstufen:
hochauflösende Räder senden Bruchteile, und einzeln abgerundet ergäben die null. Der
Recorder summiert erst (eine Drehung = ein Ereignis, `_SCROLL_MERGE_GAP`) und teilt dann.

### Boss-Scan vs. Boss-Watcher
- **Boss-Scan**: Einmaliger Scan in einem Step. Wenn nichts erkannt → `else_config` oder Default-Action.
- **Boss-Watcher**: Schleife im Step, prüft alle `llm_watcher_interval` Sekunden bis ein Boss erkannt wird (mit `llm_watcher_max_scans` und `llm_watcher_timeout` als Exit-Bedingungen). Erst dann `_execute_boss_action`.

**Zwei Zusatz-Erkenner, gleiche Bauart**: OCR (`use_ocr` + `ocr_fallback`) und LLM
(`use_llm` + `llm_fallback`), beide in `BossScanConfig`, beide zusätzlich per Config
scharfgeschaltet (`ocr_enabled` / `llm_enabled`). `*_fallback=False` heißt **vor**
Template/Marker-Matching, `*_fallback=True` heißt **nur wenn** Template/Marker nichts
findet. Bei gleicher Einstellung läuft **OCR vor LLM** — OCR ist lokal und schnell, das
LLM kostet bis `llm_timeout`.

Zwei Regeln, an denen `execute_boss_scan()` in `runtime/boss_detection.py` hängt:
- **Kein Erkenner darf doppelt laufen.** Primär- und Fallback-Zweig schließen sich über
  `not cfg_*_fallback` / `cfg_*_fallback` gegenseitig aus.
- **Alle Flags im selben Lock-Snapshot einfrieren.** Wer sie zweimal frisch liest, kann
  einen Editor dazwischen umschalten sehen und läuft dann doch doppelt.

Beide Erkenner bekommen die **gemergte** Boss-Liste (lokal + global) als
`bosses_snapshot` übergeben und dürfen nicht auf `config.bosses` zurückgreifen — sonst
findet der Treffer die Bibliotheks-Bosse nicht wieder.

Unbekannte Bosse (OCR/LLM erkennt einen Namen der nicht in der Liste ist) werden automatisch als `BossProfile(action=BOSS_ACTION_SKIP)` gespeichert — Prüfung und Append im selben `state.lock`-Block, sonst hängt ein Sync-Scan neben dem Async-Watcher denselben Boss doppelt an.

**Globale Boss-Bibliothek**: `state.global_bosses` (Editor: Boss-Scan-Menü → "Boss-Bibliothek verwalten") gilt zusätzlich in jedem Boss-Scan. `execute_boss_scan()` merged lokal + global im Lock-Snapshot; lokale Bosse gewinnen bei Namensgleichheit. Mit `boss_learn_global=true` (Config, umschaltbar im Boss-Scan-Menü) landen neu entdeckte Bosse in der Bibliothek statt im Scan.

**Item-Auto-Lernen** (opt-in pro Scan, `ItemScanConfig.learn_unknown`): `execute_item_scan()` lernt unbekannte, nicht-leere Slot-Inhalte als neue globale Items (Kategorie 'Auto', Template + Marker) — nur nach `state.global_items`, nie in die Scan-Config, damit sie nicht ungeprüft geklickt werden. Dedup per Template-Match gegen alle globalen Items. Die Items heißen erst 'Auto <Slot>'; **die LLM-Benennung läuft bewusst NICHT im Scan** (würde den Worker pro Item bis `llm_timeout` blockieren), sondern manuell über den Item-Editor-Befehl `autoname` (`editors/item_editor/commands.py::handle_autoname_command`), der `llm_vision.suggest_item_name()` aus den gespeicherten Templates aufruft.

### Koordinaten nach einem Bildschirm-Umbau

Ändert Windows die Monitor-Anordnung, sind alle gespeicherten Koordinaten um denselben
Betrag verschoben. Zwei Wege, und die Reihenfolge zählt:

| Weg | wo | Genauigkeit |
|---|---|---|
| `repair` | Slot-Editor | **misst** die Slots neu — pixelgenau |
| `fix` | Punkte-Menü (`CTRL+ALT+P`) | Referenzpunkt mit der Maus — ein paar Pixel Streuung |

**Zuerst `repair`**, dann dessen gemessenen Versatz auf den Rest anwenden lassen: eine
Maus-Position trifft den Pixel nie genau, und bei einer Scan-Region schneiden drei Pixel
das Item-Icon an. `fix` bleibt für den Fall ohne Slots.

**Einzelne Punkte statt aller**: Punkte-Menü → `walk`, dann `n` (Maus an die richtige
Stelle) bzw. `f` (nur Farbe neu lesen). Das ist der Weg, wenn nicht alles gleichmäßig
verschoben ist, sondern einzelne Ziele umgezogen sind. Weil Schritte über `point_id` auf
Punkte zeigen und ihre Koordinaten vor jedem Lauf von dort holen, repariert das jeden
Schritt, der den Punkt benutzt — **auch dessen Prüf-Pixel und else-Klick**, denn die
hängen seit Schema 4 ebenfalls an Punkten. Die Farbe wird beim Neusetzen mitgezogen, aber
nur wenn der Punkt schon eine hatte — sonst schliche sich ein Trigger ein, den niemand
gesetzt hat.

Kern in `import_export.py` (dort liegt das Remapping schon für den Import):
`kalibriere_bestand()` rechnet Punkte, Slots, Item-Bestätigungsklicks, Boss-/Icon-Scans
und die Screenshot-Regionen in den Sequenz-**Dateien** um. Regeln:

- **`mit_slots` steht getrennt von `mit_scans`.** Nach einer Reparatur dürfen die Slots
  kein zweites Mal wandern, die übrigen Scan-Regionen aber schon.
- **Nichts anfassen, was eine Punkt-Referenz hat.** Der Punkt ist schon umgerechnet; ein
  zweiter Durchgang über den abgeleiteten Wert verschöbe ihn doppelt. `_remap_sequence_obj`
  und `_remap_sequence_data` prüfen deshalb `point_id is None`, bevor sie rechnen.
- **Geladene Sequenzen im selben Lock mitziehen**, nicht nur die Dateien — sonst schreibt
  der nächste `save_data()` den alten Stand aus dem Speicher zurück.
- **Vorher sichern**: `sichere_vor_kalibrierung()` legt ein Export-ZIP an. Kein eigenes
  Backup-Format — der Export kann das, der Import spielt es zurück.
- `repair` übernimmt nur bei **eindeutiger Zuordnung**: gleiche Anzahl, gleiche Größe,
  durchgängiger Versatz. Streuen die Einzelversätze, passiert nichts.

### Tastendruck in Menüs

`read_command()` aus `utils/io.py`, **nicht** `read_key()`. Das Polling für IDE-Konsolen
kennt nur die Tasten aus `_VK_MAP` (Pfeile, Enter, Escape, Ziffern) — ein getipptes `a`
fiel dort durch, und jede Taste landete auf demselben Zweig. `read_command()` schaltet die
Buchstaben für diesen einen Aufruf dazu.

Buchstaben gehören **nicht** dauerhaft in `_VK_MAP`: das gilt auch für
`interactive_select`, wo mit Pfeilen navigiert und mit Ziffern gewählt wird.

Menüs nehmen Buchstabe **und** Pfeiltaste (`_KEYS_VOR`/`_KEYS_ZURUECK` in
`runtime/debug.py`). Eine unbekannte Taste blättert nicht weiter, sondern bleibt stehen.

### Region-Auswahl (Scan-Editoren)
Boss-/Icon-Scan-Editor wählen ihre Scan-Region über `editors/_detection_capture.select_scan_region()` (Maus / manuelle Koordinaten / beibehalten). Die manuelle Eingabe wiederholt bei Fehleingabe statt den Editor abzubrechen; `None` = Abbruch (beim Bearbeiten bleibt die alte Region).

## Wichtige Konventionen

- **Keine neuen Dateien anlegen ohne Grund**, bestehende erweitern bevorzugt.
- **Keine neuen Markdown-Dateien**, außer explizit gefragt. `IDEAS.md` ist das Backlog für noch nicht gebaute Features mit Nutzen+Tradeoff.
- **Commit-Messages auf Deutsch**, knapper Imperativ-Stil, mehrzeilig erlaubt für Begründung.
- **Branch-Konvention**: Feature-Branches `claude/<thema>-<hash>`, Push direkt auf den Branch (kein PR ohne expliziten Auftrag).

### Plattform-Schicht (Windows-Abhängigkeiten)

Alles Windows-Spezifische liegt in **genau vier Modulen**. Ein Test in `tools/test_logic.py`
(`PLATTFORM_MODULE`) hält das fest: greift ein anderes Modul auf `ctypes.windll`,
`ctypes.WinDLL`, `wintypes` oder `msvcrt` zu, schlägt er fehl und nennt die Datei.

| Modul | was |
|---|---|
| `winapi.py` | Maus, Tastatur, Fenster, Hotkeys, **Bildschirm-Geometrie**, Maus-/Tastatur-Hooks |
| `imaging.py` | Screenshot über GDI BitBlt |
| `utils/io.py` | Tastendruck-Erfassung (`msvcrt` / `GetAsyncKeyState`) |
| `utils/console.py` | Konsolen-Erkennung, Fenstertitel, ANSI-Freischaltung |

Der Test prüft **beide** Richtungen: kein Windows-Aufruf außerhalb der Liste, und kein
Eintrag auf der Liste, der gar nichts Plattformspezifisches mehr enthält — sonst wächst
sie zur Fiktion.

**Bildschirm-Geometrie gehört in `winapi.py`, nicht in den Aufrufer.** `GetSystemMetrics`
lag vorher fünfmal im Baum (`imaging`, `runtime/item_scan`, `diagnose`, `scan_studio`,
`utils/console`), jedes Mal mit eigenen `SM_*`-Konstanten und eigenem `try/except`. Wer
die Fenstergröße oder den virtuellen Desktop braucht, nimmt:

- `get_virtual_desktop()` → `(l, t, r, b)` über alle Monitore, oder `None`
- `get_virtual_origin()` → linke/obere Kante, `(0, 0)` als Rückfall
- `get_screen_size()` → Primärmonitor, oder `None`
- `get_screen_center()` → Mitte, mit Rückfallkette bis `(960, 540)`

`None` statt `(0, 0, 0, 0)` ist Absicht: eine Fläche von 0×0 würde jede Koordinate als
„außerhalb aller Monitore" melden — genau der Fehler, den `diagnose.py` sonst produziert
hätte.

## Bekannte Stolperfallen

- **Linux-Sandbox**: Voller Import scheitert an `msvcrt`/`ctypes.windll`. Für Korrektheits-Checks reicht `ast.parse`.
- **DPI-Awareness**: `winapi.py` setzt früh `SetProcessDpiAwareness(2)` — Skalierung ≠ 100% sollte korrekt funktionieren. **Multi-Monitor mit unterschiedlichen DPIs ist weiterhin nicht getestet.** Verifiziert ist dagegen der Fall, über den man zuerst stolpert: Monitore mit **negativen** Koordinaten (links vom bzw. über dem primären). BitBlt, der ImageGrab-Fallback, `get_pixel_color` und Regionen quer über Monitorgrenzen liefern dort korrekt — die Offset-Rechnung über `SM_XVIRTUALSCREEN`/`SM_YVIRTUALSCREEN` stimmt. Beim Debuggen beachten: `get_virtual_desktop()` gibt ein **Rechteck** (links, oben, rechts, unten) zurück, keine Breite/Höhe — die Breite ist `rechts - links`, und bei negativem Ursprung ist das nicht dasselbe.
- **Nicht-DPI-aware Werkzeuge lügen über die Monitor-Geometrie.** Koordinaten aus PowerShell (`System.Windows.Forms.Screen`) oder anderen Prozessen ohne DPI-Awareness sind skaliert und passen nicht zu denen, die die App sieht. Zum Nachmessen einen Prozess nehmen, der `autoclicker.winapi` importiert hat.
- **OpenCV / Pillow optional**: Code prüft `OPENCV_AVAILABLE` / `PILLOW_AVAILABLE` und degradiert sauber. Neue Features die diese brauchen → Verfügbarkeit prüfen.
- **Der erste OCR-Aufruf lädt Modelle aus dem Netz.** EasyOCR holt beim allerersten `read_text()` Detection- und Recognition-Modell per Download — Sekunden bis Minuten, und es kann mit HTTP-Fehler scheitern; danach liegt ein Aufruf bei ~300 ms. Passiert das im Worker, steht die Sequenz so lange. Dieselbe Klasse Problem wie beim LLM, weshalb die LLM-Benennung bewusst nicht im Scan läuft (s.o.). Wer `ocr_enabled` neu einschaltet, sollte den ersten Aufruf nicht in einen laufenden Scan legen.
- **`import_bundle()` schreibt sofort auf Platte, `export_bundle()` nicht.** Der Import legt Templates an und ruft `save_global_slots`, `save_global_items`, `save_item_scan`, `save_boss_scan`, `save_global_bosses`, `save_data` **und `save_config`** — er befüllt also nicht bloß den State. Mit einem frischen `AutoClickerState()` schreibt `save_config()` die Default-Config über die vorhandene `config.json`; die Tests in `test_logic.py` übergeben deshalb `import_config=False`. Für einen vollen Roundtrip die Pfad-Relativität nutzen: Datenordner + `config.json` in einen Temp-Ordner kopieren und vorher dorthin `os.chdir()` — die Konstanten in `persistence/paths.py` sind bewusst CWD-relativ.
- **Race-Condition-Sensibel**: Lange-laufende Loops im Worker (Boss-Watcher, Item-Scan) iterieren über shared dicts — Mutationen aus Editoren können während des Laufens passieren. Im Zweifel `dict(state.x)`-Snapshot unter Lock.
