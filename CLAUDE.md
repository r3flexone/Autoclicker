# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Was das ist

Autoclicker für Windows und Linux/X11 für das Spiel "Idle Clans".
Konsolen-getriebene Python-App mit globalen Hotkeys, Sequenz-Editor,
OpenCV-basierter Item-Erkennung und optionaler LLM-Vision für Boss-Detection
(Ollama / LM Studio). Wayland wird nicht unterstützt. Code-Sprache und alle
UI-Texte sind **Deutsch** — neue Strings ebenso.

## Run / Lint / Test

```bash
python tools/test_logic.py      # Die Vertragssuite — laeuft auch auf Linux/Mac, Exit 0 = gruen
python -m unittest test_*.py    # Die unittest-Module im Projektstamm — ZWEITE Suite,
                                # laeuft in CI nur in der Variante MIT Bildpaketen
python -m flake8 --select=F autoclicker/ market_analysis/ main.py tools/ test_*.py
                                # Linter (= pyflakes, aber mit noqa)

python main.py                  # Startet die App auf Windows oder Linux/X11
python tools/test_llm.py            # Standalone-Verbindungstest für Ollama/LM Studio (nutzt llm_vision)
python tools/test_llm.py screenshot # LLM-Screenshot-Test ohne Editor-Setup
python tools/migrate.py         # Hebt alle JSON-Dateien aufs aktuelle Format (--write zum Schreiben)
                                # Nur fuer Sonderfaelle — die App macht das bei jedem Start selbst
python tools/slot_tester.py     # Debug-Tool für Slot-Erkennung
python tools/log_report.py      # Wertet die Session-Logs aus (welcher Schritt haengt?)
                                # --letzte = nur die neueste Session
python tools/symbol.py          # Schreibt das Programm-Symbol als PNG + ICO
                                # (fuer Verknuepfungen; das Fenstersymbol setzt die App selbst)
```

**Es sind ZWEI Suiten, und vor einem Commit laufen beide.** `python tools/test_logic.py`
**und** `python -m unittest test_*.py` — die zweite sind die `test_*.py` im
Projektstamm (Import/Export-Sicherheit, Plattformvertrag, Studio-UX, Runtime-Härtung).

Das steht hier so deutlich, weil genau diese Lücke schon einmal einen roten CI-Lauf
gekostet hat: `tools/test_logic.py` war grün, gemeldet wurde „alles grün", und die
Wurzelmodule liefen nie. In `.github/workflows/tests.yml` hängen sie an der Achse
`bilder: mit` — die `ohne`-Variante startet nur die Vertragssuite, weil zwei
Wurzelmodule PIL schon beim Import brauchen. **Ein grüner Lauf ohne Bildpakete sagt
also nichts über die zweite Suite.**

**`tools/test_logic.py`** prüft Serialisierung,
Migration, Runtime-Gates, Kalibrierung, Tastenbelegung und die Plattform-Grenze — ohne
GUI, ohne Windows, ohne Netz. `msvcrt` und `ctypes.windll` werden am Dateianfang gestubbt;
deshalb läuft die komplette Logik-Schicht auch hier.

**Und seit `.github/workflows/tests.yml` läuft sie auch, wenn niemand daran denkt.**
Push und Pull Request auf jedem Branch, als Matrix auf Ubuntu und Windows. Dazu
kommt ein eigener Job mit `flake8 --select=F` (tote Importe, Tippfehler in Namen).
Alle drei Jobs müssen grün sein; ein roter Lauf ist ein Fehler, kein Hinweis.
Geprüft wird auf **Python 3.10**, der unteren Grenze — auf der neuesten Version
zu testen sagt nichts darüber, ob die älteste noch trägt.

**Der Test-Job läuft zweimal: `ohne` und `mit` Bildpaketen.** OpenCV und Pillow sind
optional, und der Code degradiert sauber ohne sie — nur überspringt die Suite dann
**über hundert Tests** (Template-Vergleich, Masken, Slot-Erkennung, die
Grössen-Meldung): 1.154 statt 1.273. Ein Lauf nur ohne Fremdpakete ist also grün,
während der halbe Bilderkennungs-Teil ungeprüft bleibt — und genau dort ist schon
einmal eine kaputte Meldung durchgerutscht, weil die Zusicherung dazu lokal gar
nicht lief. Dieselbe Regel wie bei den Plattform-Stubs: **was das Echte anders macht
als der Ersatz, wird auf beiden Seiten geprüft.** Wer an `imaging.py` arbeitet,
installiert sie deshalb auch lokal (`pip install opencv-python-headless pillow numpy`)
— sonst sagt ein grüner Lauf hier nichts über die Stellen, um die es gerade geht.

**Ein Einstiegspunkt, mehrere Dateien.** `tools/test_logic.py` war mit über 7.000
Zeilen die grösste Datei des Repos — mehr als jedes Produktivmodul —, und die
durchnummerierten Variablennamen (`_b18`, `_sand18`) waren das Symptom: so
benennt man, wenn der Namensraum voll ist. Neue Sektionen kommen deshalb als
eigenes Modul unter **`tools/tests/`**, holen Stubs, Zähler und `check`/`section`
aus `tools/tests/_harness.py` und werden am Ende von `test_logic.py` importiert
(Import = ausführen, wie im Rest der Datei auch).

Zwei Dinge hängen daran: **die Zähler leben im Harness**, nicht im Aufrufer —
sonst zählte jedes Modul für sich und die Schlusszeile sähe nur den letzten
Stand. Und **die Stubs müssen vor dem ersten `autoclicker`-Import stehen**;
`_harness` setzt sie beim Import, also ist `from ._harness import check` die
erste Zeile eines neuen Moduls, nicht die dritte.

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

**Es gibt nur noch EINEN ungetesteten Rest, und der ist klein.** Bis zum Umbau lag
hier ein Absatz über einen Test, der jeden `dpg.<name>(..., kwarg=...)` gegen die
installierte Dear-PyGui-Version hielt — nötig, weil das Scan-Studio ein Fenster
brauchte und in keinem Test lief (es starb einmal an `add_static_texture(...,
format=...)`, das es in DPG 2.x nur noch bei `add_raw_texture` gibt). Dieses Fenster
gibt es nicht mehr, der Test ist ersatzlos gelöscht, und `dearpygui` steht in keiner
Anforderungsdatei mehr. Die Geschichte steht hier, damit niemand denselben Weg noch
einmal einschlägt: **eine Ansicht, die man nur über die Signaturen ihres Fremdpakets
prüfen kann, ist die falsche Ansicht.**

**Beim Studio stellt sich die Frage deshalb gar nicht.** Seine Oberfläche ist eine
Webseite. `bridge.py` und `scans.py` bleiben stabile Fassaden; die Logik liegt
nach Verantwortung in `bridge_view.py`, `bridge_services.py`,
`bridge_editing.py` sowie den `scan_*.py`-Modulen — ohne Fenster, ohne
Fremdpaket, also im Test. Ungeprüft bleibt nur, was wirklich Anzeige ist
(HTML/CSS/JS). Das ist die Richtung, in die GUI-Code hier gehört: **nicht die
Ansicht testbar machen, sondern die Logik aus ihr heraus.**

Automatisiert geprüft werden beide Plattformverträge. Manuell bleiben die echten
Desktop-Grenzen: globale Hotkeys, Eingabesimulation, Fensterfokus und Screenshots
in einer Windows- bzw. X11-Sitzung. Auf einer cp1252-Konsole kann die Ausgabe mit
`UnicodeEncodeError` abbrechen (Box-Zeichen); unter Windows deshalb bei Bedarf
mit `PYTHONIOENCODING=utf-8` starten.

**Die Konsolen-Editoren sind angefangen, nicht fertig.** Sie standen lange
vollständig ausserhalb der Suite (rund 3.400 Zeilen). Der Einstieg lief über das,
was **geteilt** ist: `editors/_detection_capture.py` gehört dem Boss- *und* dem
Icon-Editor, ein Test deckt dort also zwei Editoren ab — Tastenabfrage,
Region-Eingabe, Marker-Aufnahme, jeweils mit der Eigenschaft, um die es geht
(**Fehleingabe wiederholen statt abbrechen**). Dazu `_apply_item_rename()`, weil
am Namen drei Dinge hängen: Bestand, Template-*Datei* und jede Scan-Referenz.

Der Rest ist offen und soll **einer nach dem anderen** kommen, nicht am Stück:
`item_editor/` (Lernen, Autoscan, Befehle), `boss_scan_editor.py`,
`icon_scan_editor.py`, `sequence_editor/loops.py`. Der Weg dorthin ist immer
derselbe — erst in Stufen zerlegen, dann mit einer Tastenfolge füttern; die
Zerlegung ist der eigentliche Gewinn, die Tests fallen danach fast von selbst an.

## Architektur

### Threading-Modell
- **Main-Thread**: Pumpt die Hotkey-Ereignisse des gewählten Plattform-Backends
  (`main.py`), dispatcht zu Handlern und blockiert beim Editor-Input.
- **Worker-Thread**: `sequence_worker()` in `autoclicker/runtime/worker.py` — führt die aktive Sequenz aus.
- **Geteilter State**: `AutoClickerState` (in `models.py`) mit `state.lock` (threading.Lock) und mehreren Events (`stop_event`, `pause_event`, `skip_event`, `restart_event`, `skip_cycle_event`, `quit_event`, `finish_event`).

**Pattern für State-Mutationen**: Jede Lese-/Schreib-Operation auf `state.global_items`, `state.global_slots`, `state.boss_scans`, `state.item_scans`, `state.sequences`, `state.points`, `state.clicked_categories`, Zähler etc. **muss** unter `with state.lock:` laufen. Persistenz-Funktionen in `autoclicker/persistence/` machen einen Snapshot unter Lock und schreiben die Datei ausserhalb. Datei-Saves laufen crash-sicher über `atomic_write()` (Temp-Datei + `os.replace`, in `utils/parsing.py`) — bei Absturz bleibt die alte Datei intakt statt korrupt.

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

**Die Status-Zeile schreibt sich in EINEM Schreibvorgang** — `status_line()` in
`utils/console.py`, nicht `clear_line()` gefolgt von einem eigenen `print()`. Beides
zusammen ergibt zwar dieselben Zeichen, aber zwei einzeln geflushte Blöcke: ein echtes
Terminal fasst sie zusammen, eine **IDE-Konsole** (PyCharm-Run-Fenster, dort ist
`_REAL_CONSOLE` schon `False`) verarbeitet jeden Flush einzeln und kann die Zeile
dazwischen festschreiben. Dann bleibt mitten im Lauf eine alte Status-Zeile stehen,
statt überschrieben zu werden. Zusammen geschrieben gehört das `\r` untrennbar zu dem
Text, der es benutzt.

Die Löschbreite folgt der **vorher geschriebenen Zeile** (`_letzte_status_laenge`), nicht
mehr festen 80 Spalten: ein langer Punkt-Name liess den Rest der alten Zeile hinter der
neuen stehen. ANSI-Sequenzen zählen dabei nicht mit — sie belegen keine Spalte.

Wer eine Meldung ausgeben will, die **stehen bleiben soll** (Screenshot-Dateiname,
Timeout, Fokus-Verlust), räumt vorher mit `clear_line()` ab oder stellt der Meldung ein
`\n` voran. Ohne das überschreibt sie nur den Anfang der Status-Zeile und lässt den Rest
daneben stehen.

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
einer laufenden Aufnahme.** Der Buchstabe darf derselbe bleiben wie in der Basis-Ebene,
solange die Bedeutung verwandt ist — `M`/`SHIFT+M` sind beide „warte auf eine Farbe",
`D`/`SHIFT+D` beide „Screenshot".

Dass die Marker nicht in der Aufnahme landen, ist kein Zufall: der Tastatur-Hook meldet
nichts bei gedrücktem CTRL oder ALT, und beide sind hier gedrückt.

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
| `SequenceStep.verify_condition` | `points.json` | `verify_point_id` | dito |
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

Dieselbe Regel gilt ausserhalb der Sequenzen: `ItemProfile.confirm_point`,
`BossProfile.action_x/y` und `IconScanConfig.action_x/y` sind ebenfalls abgeleitet.
`resolve_klick_referenzen()` (in `persistence/item_scans.py`) füllt sie und läuft in
`main.py` **nach** dem Laden aller Scans — `load_all_item_scans()` sieht die Boss- und
Icon-Scans an seiner Stelle noch gar nicht, deren Klicks stünden sonst bis zum ersten
Sequenzlauf auf (0, 0).

Für diese drei gibt es **bewusst keine Migration**: die alten Koordinaten liessen sich
zwar in Punkte heben, aber der Weg dorthin — die Punkte-Liste durch jeden Item-, Boss-
und Icon-Loader reichen — kostet mehr, als das Feld einmal neu zu setzen. Der Loader
meldet ein Altfeld stattdessen einmal pro Fundstelle (`_alt_gemeldet` in
`serialization.py`) und nennt den Editor, in dem es neu gesetzt wird. Still verschwinden
darf es nicht.

Warum so streng: eine Koordinate an zwei Stellen ist eine Koordinate, die an einer der
beiden falsch sein kann. Wer die Sequenzdatei liest, sah dann etwas anderes als das, was
die App klickt — und bei einer Kalibrierung musste jede Kopie einzeln erwischt werden.
`kalibriere_bestand()` rechnet Sequenz-Klickstellen deshalb **nicht mehr** um: die Punkte
sind schon umgerechnet, ein zweiter Durchgang hiesse doppelt verschoben.

**Vier Stellen pro Schritt, zwei Klassen.** `point_id` (Klick) und
`wait_condition.point_id` (Vorbedingung) *sind* der Schritt — fehlt ihr Punkt, darf er
nicht laufen. `verify_condition.point_id` (Nachprüfung) und `else_config.point_id`
(Ersatzaktion) sind Zusatz — fehlt deren Punkt, läuft der Schritt weiter, nur eben
ungeprüft bzw. mit `else = skip`. Gemeldet wird beides.

**Es gibt bewusst keinen Rückfallwert.** Zeigt eine `point_id` ins Leere, setzt
`aufloesen()` `step.unresolved = True`; `step_gate()` überspringt den Schritt und sagt
warum. Ein Schritt, der ersatzweise auf eine veraltete Kopie klickt, ist schlimmer als
einer, der stehenbleibt — und ohne Kopie wäre die Alternative ein Klick auf (0, 0).

Regeln beim Erweitern:
- **Wer im Editor eine Stelle erzeugt, legt einen Punkt an**: `punkt_fuer_stelle(state, x,
  y, color, name)` gibt die ID zurück, nie ein Koordinatenpaar. Die Funktion verwendet
  einen vorhandenen Punkt an derselben Stelle wieder — klickt eine Sequenz zweimal
  denselben Knopf, ist das EIN Punkt, sonst wandert beim Nachjustieren nur die Hälfte mit.

  **„Dieselbe Stelle" ist eine eigene Regel, und sie steht an einer Stelle**:
  `punkt_an_stelle()` in `persistence/sequences.py`. Editor und Aufnahme
  (`punkte_fuer_events`) stellten dieselbe Frage und verglichen beide die
  Koordinaten **exakt** — daran entstanden die Doppelten: denselben Knopf trifft
  man nie zweimal pixelgenau. In einer echten Aufnahme lagen so vier Punkte auf
  einem einzigen grünen Knopf (`#2/#13/#24/#40`, 1,4–6,7 px auseinander, Farbe
  identisch); über die ganze Datei waren es 51 Punkte, von denen 14 Dubletten
  sind.

  Zwei Bedingungen, und die zweite ist die wichtigere:

  1. Abstand ≤ `punkt_radius` (0 = nur exakt, das alte Verhalten)
  2. **Die Farbe muss passen** (`punkt_farbtoleranz`). Weicht sie ab, entsteht
     *immer* ein eigener Punkt — auch einen Pixel daneben. An einer Farbgrenze
     klickt man zwei verschiedene Dinge, und zwei Spiele übereinander
     unterscheiden sich in nichts anderem. Genau dafür ist die Farbe da.

  Fehlt einer Seite die Farbe, lässt sich Regel 2 nicht prüfen — dann zählt nur
  die exakte Stelle. Lieber ein Punkt zu viel als zwei zusammengelegte, die es
  nicht sind.

  **Beim Aufnehmen wird nichts verschoben.** Der erste Klick legt den Punkt an,
  die folgenden finden ihn; er behält seine Position. Ihn auf die Mitte der
  Gruppe nachzuziehen wäre genauer und wäre falsch: ein wiederverwendeter Punkt
  gehört womöglich schon einer anderen Sequenz, und die zöge stillschweigend mit.
  Auf die Mitte rücken darf nur ein ausdrücklicher Aufräum-Durchgang mit Vorschau.
- **Aufgelöst wird beim Laden**, nicht erst vor dem Lauf: `load_sequence_file()` holt sich
  die Punkte notfalls selbst. Von den neun Aufrufern haben sechs keinen Punkte-Pool zur
  Hand (Sequenz-Studio, Scan-Studio, Export) — die bekämen sonst lauter Nullen.
- **Eine vierte Stelle** trägt man in `_REF_KEYS` (`import_export.py`) und
  `aufloesen()` ein. Fehlt eine der beiden, überlebt sie den nächsten Import nicht.
  (Der dritte Eintrag war `_STELLEN` in der Migration — mit `_seq_v3_to_v4` entfallen.)

**Die Scan-Richtung gehört zum Scan, nicht zum Programm.** Sie stand als
`config.scan_reverse` in der Config und galt damit für *alle* Item-Scans — die
Richtung hängt aber am Inventar: wer ein Spiel von hinten leert und ein zweites
von vorn, hatte die Wahl zwischen zwei falschen Läufen. Heute ist es
`ItemScanConfig.reverse` (Schalter im Scan-Inspektor, Schritt 5 im
Konsolen-Editor), Voreinstellung **aus**; das Config-Feld ist **ersatzlos
gelöscht**, samt seinem Eintrag in `config_meta.py` und der README-Tabelle. Ein
Test prüft beide Richtungen: das Attribut existiert nicht mehr, und der Name
kommt im Code nicht mehr vor.

Umgeordnet wird an zwei Stellen — `runtime/item_scan.py` und der Immediate-Pfad
in `runtime/steps.py`. Eine davon zu vergessen hiesse, dass derselbe Scan je nach
Modus anders herum läuft; der Wert wird im selben Lock-Snapshot eingefroren wie
die übrigen Flags.

Eine Falle, die dabei aufgefallen ist und für **jedes** weitere Feld gilt: **der
Konsolen-Editor baut die Config NEU auf**, statt die vorhandene zu ändern. Ein
Feld, das in `ItemScanConfig(...)` in `edit_item_scan()` fehlt, ist nach dem
Bearbeiten eines bestehenden Scans still weg. Ein Test hält die übergebenen
Schlüssel gegen die Dataclass (ohne `slot_names`/`item_names` — die leitet
`sync_names()` ab).

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
über `slots`/`items` — die sind erst nach dem Auflösen gefüllt. Wer `config.slots` von aussen
setzt, ruft danach `sync_names()`.

Namen, die global fehlen, werden gemeldet und übersprungen — der Scan läuft mit dem Rest
weiter. Lieber ein Slot weniger als ein toter Scan.

Beim Umbenennen bleibt `update_item_in_scans()` nötig: der Name *ist* die Referenz. Alles
andere (Marker, Template, Priorität) braucht kein Nachziehen mehr.

**Jeder Klick-Schritt wird MIT `point_id` gebaut**, nicht nachträglich verknüpft. Ein Test
(`kein Klick-Schritt wird ohne point_id gebaut`) prüft jede `SequenceStep(...)`-Konstruktion
im Baum; ausgenommen sind Schritte ohne echte Position (Taste, Scan, Wait, Screenshot) und
der Blanko-Block `(0, 0)` des Sequenz-Studios, der noch gar keine Stelle hat.

Darauf zu vertrauen, dass eine Migration das nachträglich verknüpft, reicht **nicht** —
und heute gibt es sie gar nicht mehr: die Sequenz-Kette ist leer (s.u.). Wer einen
Klick-Schritt baut, baut ihn mit `point_id`, sonst hat er keine Stelle. Genau daran hing
einmal der Recorder: er legte Schritte und Punkte unabhängig voneinander an, und jede
aufgenommene Sequenz blieb dauerhaft unverknüpft.

**Die Kette hat ihre Arbeit getan und ist gelöscht.** Vier Schritte hoben den Altbestand
auf Schema 4 — zuletzt `_seq_v3_to_v4`, das jede Koordinate aus der Sequenz nach
`points.json` zog und dafür notfalls einen Punkt anlegte. Seither gilt die Regel
ausnahmslos, es gibt keinen Bestand mehr unterhalb von Schema 4, und damit sind die
Schritte weg. Mit ihnen entfielen `_sichere_neue_punkte()` (sequences.py),
`_punkte_schreibfertig()` (sweep.py) und `_als_dicts()`: sie schrieben die von der
Migration angelegten Punkte zurück, und dieses Ereignis tritt nicht mehr ein.

Was das für eine sehr alte Datei heisst, steht ausdrücklich im Modul-Kopf von
`migration.py` und in einem Test: sie wird **auf 4 gestempelt, aber nicht umgerechnet**.
Der Loader wirft deshalb nicht — er liest mit `data.get(key, default)` —, die Sequenz
kommt aber leer an. Der Weg dorthin ist dann nicht die Wiederbelebung der Schritte,
sondern `git show <commit>:autoclicker/persistence/migration.py` oder die Sequenz im
Studio neu zu bauen.

Das ist der vorgesehene Lebenslauf: **neue Daten entstehen korrekt, Altlasten gehen
einmal durch die Schleuse — und dann verschwindet die Schleuse.** `link` im
Sequenz-Editor bleibt für Sonderfälle, nicht als Teil des normalen Wegs.

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
backups/<pfad>.bak             Sicherungen des Start-Durchgangs (Struktur gespiegelt)
logs/<timestamp>_<seq>.csv     Session-Log (wenn aktiviert)
.lauf.json                     Laufstatus fuer das Sequenz-Studio (transient)
```

**`.lauf.json` ist kein Bestand** und steht deshalb nicht in der Migration: es
beschreibt den Zustand JETZT und wird überschrieben statt angehängt
(`runtime/status.py`). Am Sequenz-Ende bleibt genau **ein** Eintrag stehen — die
Zusammenfassung des letzten Laufs —, bis der nächste Start sie überschreibt. Dass es **oben** liegt und nicht in
`sequences/`, ist kein Zufall: `Path.glob("*.json")` erfasst auch Dateien mit
führendem Punkt. Dort abgelegt stünde es als Sequenz im Studio-Menü, im
Konsolen-Menü und im Start-Durchgang — und weil es sich sekündlich ändert,
gewänne es jedes Mal `zuletzt_bearbeitet()`. Dieselbe Falle, wegen der die
`.bak`-Sicherungen unter `backups/` liegen statt neben dem Original.

**Neue Formatänderungen brauchen KEINEN Migrationsschritt mehr.** Das ist eine
ausdrückliche Entscheidung des Nutzers und die wichtigste Regel dieses
Abschnitts: **es darf alles aufs heutige Optimum gebaut werden.** Fällt ein Feld
weg oder ändert sich seine Bedeutung, bekommt eine Bestandsdatei eben den
Default — „dann ist es halt so, das gibt Altlasten, ohne dass viel kaputtgeht."

Der Grund ist nicht Bequemlichkeit, sondern dass sich die Kosten verschoben
haben: einen Scan oder eine Sequenz im Studio **neu zu bauen ist inzwischen
billiger**, als einen Migrationsschritt zu schreiben, zu testen und später wieder
zu löschen. Slots findet man mit zwei Ecken und einem Klick, Items lernt ein
Knopf, und was schon bekannt ist, steht sofort grün da.

Was das **nicht** heisst:

- **Nicht: eine alte Datei darf abstürzen.** Der Loader liest weiter mit
  `data.get(key, default)`, unbekannte Keys fliegen raus, `LOAD_EXCEPTIONS`
  fängt Kaputtes ab. Eine Datei, die den Loader wirft, ist ein Fehler — eine
  Datei, die ein Feld auf dem Standardwert bekommt, ist es nicht.
- **Nicht: der Start-Durchgang entfällt.** `sweep.py` räumt weiterhin auf
  (Round-Trip durch Loader + Serializer, `.bak` vor der ersten Änderung). Genau
  darüber verschwindet ein gelöschtes Config-Feld von selbst aus der
  `config.json`, ohne dass jemand etwas anfassen muss.
- **Nicht: `_CHAINS` wird jetzt egal.** Die vorhandenen Schritte laufen weiter,
  bis der Altbestand durch ist, und werden dann ersatzlos gelöscht. Das Modul
  soll schrumpfen — es soll nur eben auch nicht mehr wachsen.

Die bisherige Regel „Bestandsdateien werden über die Migration gehoben, nicht
fallengelassen" gilt damit **nur noch für das, was schon eine Migration hat**.
Für alles Neue ist die Antwort: Default in der Dataclass, fertig.

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

Die Sicherungen liegen unter **`backups/`** mit **gespiegelter Ordnerstruktur**
(`sequences/all_dayli.json` → `backups/sequences/all_dayli.json.bak`, `sicherungspfad()`).
Beides ist nötig: neben dem Original verstellten sie den Blick auf die Daten und ein
`*.json`-Glob über `sequences/` konnte sie erwischen — und ohne den Unterordner
überschriebe die Sicherung von `item_scans/foo.json` die von `boss_scans/foo.json`,
gleicher Dateiname, andere Datei. Der Ordner entsteht **erst beim ersten Sichern**, nicht
in `init_directories()`: ein leeres `backups/` bei jeder frischen Installation wäre
Rauschen. Wie bisher gilt `if not backup.exists()` — die **erste** Sicherung bleibt die
älteste und wird nie überschrieben.

„Still, wenn nichts zu tun ist" gilt auch für **Zahlentypen**: JSON kennt nur eine Zahl,
`600` und `600.0` sind dieselbe. `_gleich()` zieht beide Seiten deshalb durch
`_zahlen_normalisieren()`, bevor es vergleicht. Ohne das galt eine von Hand auf `600`
getippte Wartezeit als aufzuräumen — der Loader macht `600.0` daraus —, und der Durchgang
schrieb die Datei um, legte ein `.bak` an und meldete eine Migration, die inhaltlich nichts
tat. `bool` bleibt dabei ausgenommen: `True` darf nicht als `1.0` durchgehen, sonst wäre
ein umgekipptes Flag unsichtbar.

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
über `state.config` vorschlagen. Beides war früher derselbe Name — dadurch liess der
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

Dieselbe Regel gilt für **Identität ausserhalb der Persistenz**: Loop-Phasen-Namen sind
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
- `autoclicker/winapi.py` — **Fassade** über das Plattform-Backend (Maus, Tastatur, Hotkeys, Fenster, Bildschirm-Geometrie); die Implementierungen liegen in `platforms/` (s.u.). `safe_click`/`safe_key` liegen in `runtime/actions.py`.
- `autoclicker/symbol.py` — das Programm-Symbol als Geometrie (s.u. beim Studio). Kennt weder Windows noch Pillow: es rechnet nur, wie viel Farbe auf einen Pixel fällt.
**Ein Template vergleicht nur das Item, nicht den Slot.** Gemessen an einem
echten Bestand: von 62×60 Pixeln eines Slots sind **10–40 % das Item**, der Rest
ist die immer gleiche Slot-Fläche. Ein Vergleich über das ganze Rechteck stimmt
damit hauptsächlich darüber ab, dass beide denselben Hintergrund haben — und nur
zu einem Zehntel darüber, ob es dasselbe Item ist. `mit_hintergrund_maske()`
legt deshalb beim Lernen einen Alpha-Kanal an (Hintergrund durchsichtig), und
`match_template_in_image()` rechnet nur über die deckenden Pixel.

Vier Entscheidungen dahinter:

- **Die Maske merkt sich Stellen, nicht Farben.** Deshalb trägt sie auch, wenn
  dasselbe Item später vor einem anders gefärbten Menü steht: verglichen werden
  die Pixel, an denen beim Lernen das Item sass. Welche Farbe der Hintergrund
  dort *heute* hat, geht gar nicht mehr in die Rechnung ein — ein Test misst
  genau das (dasselbe Symbol auf grünem und auf violettem Grund).
- **Sie steckt IM Template-PNG**, nicht in einer Datei daneben. Zwei Dateien, die
  zusammengehören, laufen irgendwann auseinander — dieselbe Entscheidung wie beim
  Ursprung im Screenshot-PNG des Scans-Reiters.
- **Gerechnet wird von Hand statt mit `cv2.matchTemplate(..., mask=)`.** Mit
  Maske kann OpenCV nur `TM_SQDIFF` und `TM_CCORR_NORMED`, und deren Zahlen
  bedeuten etwas anderes als `TM_CCOEFF_NORMED`. `min_confidence` steht an jedem
  Item auf einem Wert, der für CCOEFF gedacht ist; ein Methodenwechsel würde jede
  gespeicherte Schwelle still verschieben. Template und Ausschnitt sind ohnehin
  immer gleich gross (`_template_in_groesse`), also ist es genau eine Korrelation
  und keine Suche.
- **Ohne Alpha bleibt alles beim Alten.** Ein Template aus der Zeit davor hat
  keine Maske und wird wie bisher verglichen — es muss also nichts umgestellt
  werden, nur neu Gelerntes ist besser. `_load_template` liest deshalb
  `IMREAD_UNCHANGED` statt `IMREAD_COLOR`; mit `COLOR` fiele der Alpha-Kanal beim
  Laden weg und niemand würde es merken.

**Die Marker-Farben sehen dieselbe Fläche.** `_collect_markers_silent()` liest
den Alpha-Kanal, wenn das Bild einen hat — dann ist der Hintergrund schon
entschieden, und es gibt nicht zwei Regeln nebeneinander. Der Unterschied ist
nicht nur Kosmetik: die Farbregel vergleicht **gerundete** Farben (`//5`), die
Maske die echten; an der Grenze kommen verschiedene Ergebnisse heraus.

Der Wert dahinter ist gemessen, nicht geraten: `scan_slot_color_distance` stand
auf 25, der dunklere **Rand** des Slots liegt aber 44 vom gemessenen
Hintergrund entfernt — und blieb deshalb als Marker in **19 von 19** Items
stehen. Eine Farbe, die jedes Item hat, unterscheidet nichts; mit
`scan_require_all_markers` muss sie zusätzlich immer gefunden werden. Bei 45
verschwindet sie, bei 55 ändert sich nichts mehr. Deshalb 45.

**Verschiedene Flächen desselben Spiels haben verschiedene Slot-Höhen — und die
Meldung darüber darf nicht wie ein Defekt klingen.** Am echten Bestand: das
Inventar-Raster hat 64 Hintergrund-Zeilen, die Ausrüstungsreihe 61, nach dem Einzug
also 60 und 57. Der Scan hält jedes Item auch gegen die Slots der jeweils anderen
Fläche (dafür ist „erkannt, aber nicht in diesem Scan" da), und dort kann es nicht
passen. Das ist **richtig** und kein Fehler des Nutzers.

`_groessen_hinweis()` in `imaging.py` schreibt den Text dazu. Drei Regeln, die er
einlöst — die alte Fassung („passt nicht zur Scan-Region … Template neu aufnehmen")
verletzte alle drei und schickte den Leser einen Fehler suchen, den er nicht gemacht
hat:

- **Der häufige Fall steht zuerst und beim Namen** (Ausrüstungsreihe vs.
  Inventar-Raster), nicht als zweite von zwei gleichrangigen Ursachen.
- **Statt zweier Ursachen die Frage, die sie trennt**: findet der Scan seine übrigen
  Items noch? Das kann der Code nicht wissen — der Nutzer sieht es in derselben
  Sekunde. Die Reparatur („neu vermessen, neu lernen") hängt an dieser Antwort und
  steht deshalb erst dahinter.
- **Kein negativer Prozentwert.** `TM_CCOEFF_NORMED` läuft von −1 bis +1; unter 0
  heisst „die beiden Bilder haben nichts gemeinsam". Als „−51 % Übereinstimmung"
  gelesen wirkt das wie eine kaputte Zahl, und man sucht den Fehler in der Rechnung.
  Unter 0 steht deshalb „keine Ähnlichkeit".

Die Sperre bleibt: gemeldet wird **einmal je Grössenpaarung** (`_gemeldete_groessen`),
sonst stehen zwei Dutzend gleichlautende Zeilen da und die Meldung ist so gut wie
keine.

Eine Grenze, die man kennen muss: **eine völlig gleichförmige Fläche hat keine
Varianz und damit keine Korrelation.** Ein Item, dessen sichtbarer Teil eine
einzige Farbe ist, kommt maskiert auf 0 — vorher lieferte der Hintergrund die
Varianz und es „funktionierte". Echte Symbole haben Struktur; für den Rest gibt
es die Marker-Farben.

- `autoclicker/imaging.py` — Screenshot über das Plattform-Backend, OpenCV-Template-Matching, Farb-Erkennung, Region-Selektion. Templates liegen im `_template_cache` (Schlüssel: mtime+Grösse der Datei), sonst würde jedes Template pro Item × Slot × Zyklus neu von Platte gelesen. Neu gelernte Templates greifen trotzdem sofort — der Schlüssel ändert sich mit.
- `autoclicker/config_meta.py` — was `AppConfig` über ein Feld nicht sagt: Beschriftung, Erklärung, Art des Bedienelements, Abhängigkeit. Einzige Quelle für den Einstellungen-Reiter des Sequenz-Studios; ein Test hält sie gegen die Dataclass (s.u.).
- `autoclicker/llm_vision.py` — HTTP-Calls (urllib) an Ollama/LM Studio, Reasoning-Support, `<think>`-Strip, Boss-Name-Extraktion + Matching.
- `autoclicker/ocr.py` — Texterkennung über EasyOCR oder Tesseract (`ocr_backend`, `None` = automatisch). Wie OpenCV/Pillow **optional**: `is_available()` prüfen, sauber degradieren. Liefert `detect_boss_name()` für `runtime/boss_detection.py`.
- `autoclicker/diagnose.py` — Selbstdiagnose: fehlende Templates, Profile ohne jede Erkennungsmethode, tote Slot-/Item-/Scan-Verweise, Punkte ausserhalb aller Monitore. Beim Start ohne Sequenzdateien und still wenn sauber (`check_beim_start`), auf Zuruf vollständig (Punkte-Menü → `check`).
- `autoclicker/session_log.py` — CSV-Logger, thread-safe. **Ausgewertet wird er mit
  `tools/log_report.py`** (ohne Windows, ohne Abhängigkeiten lauffähig). Geloggt wird
  nicht nur, *was geklickt* wurde, sondern auch, *was gesehen* wurde: `timeout` (welcher
  Schritt hängt — das diagnostisch wertvollste Ereignis), `item_found`, `detected`,
  `verify_ok`/`verify_miss`. Ohne diese Ereignisse konnte der Bericht die eine Frage
  nicht beantworten, für die man ihn aufmacht. Wer eine neue Ereignisart einführt,
  trägt sie in `log_report.py` ein — der Bericht meldet sonst „nicht ausgewertete
  Ereignisarten" und weist selbst darauf hin.
- `autoclicker/import_export.py` — ZIP-Bundle Export/Import + Koordinaten-Remapping (2-Punkt-Affine: scale + offset). Referenzpunkte automatisch aus der Spielfenster-Client-Grösse (`winapi.get_client_rect_by_title`, Manifest-Feld `source_window`), Fallback = manuelle 2 Punkte.

  **Der Import läuft in Stufen, nicht am Stück.** `import_bundle()` war eine
  Funktion mit 292 Zeilen und 69 Verzweigungen — und zugleich die Stelle, die am
  meisten auf Platte schreibt (Templates, Slots, Items, drei Scan-Arten,
  Sequenzen, Punkte, Config). Diese beiden Eigenschaften zusammen sind die
  unangenehmste Kombination, die eine Codebasis haben kann: die Tests konnten
  unmöglich alle Pfade treffen, und jeder ungetroffene Pfad schrieb Dateien.
  Heute trägt `_Import` den Zustand eines Durchgangs (ZIP, State, Transform,
  `stats`, `id_map`), und `_imp_templates` … `_imp_config` sind einzeln prüfbar;
  `import_bundle()` ist nur noch der Ablauf.

  **Die Reihenfolge ist die eigentliche Aussage** und nicht beliebig: Templates
  zuerst (Items verweisen darauf), dann Punkte (Sequenzen verweisen darauf), dann
  die Sequenzen; Slots und Items vor den Item-Scans, weil die per Namen auf sie
  zeigen und am Ende aufgelöst werden. Was in der Abschlussmeldung steht, steht
  als Tabelle (`_IMPORT_MELDUNG`) — ein Test hält sie gegen die Schlüssel in
  `stats`, sonst importiert man etwas, das die Meldung verschweigt.
- `autoclicker/utils/` — Hilfsfunktionen: `console.py` (ANSI, Tags), `io.py` (safe_input, interactive_select), `parsing.py` (Zeit, Dateinamen).
- `autoclicker/persistence/` — JSON-Persistenz: `migration.py` (Schema-Versionierung, s.o.), `paths.py` (Pfade), `serialization.py` (Dataclass↔Dict; `_*_to_dict`/`_*_from_dict` sind die EINE Quelle der Wahrheit fürs Dateiformat — von Savern UND `import_export.py` genutzt, damit beide dasselbe schreiben), `_scan_store.py` (geteiltes Skelett für item/boss/icon-Scans: ensure_dir/write/list/load_all + `LOAD_EXCEPTIONS`), `sequences.py`, `item_scans.py`, `boss_scans.py`, `icon_scans.py`, `globals.py`, `presets.py`.
- `autoclicker/runtime/` — Sequenz-Ausführung: `actions.py` (safe_click/safe_key, Humanize, `execute_else_action`), `item_scan.py` (inkl. `execute_icon_scan`), `boss_detection.py` (inkl. `_execute_detection_action` — geteilte Aktions-Ausführung für Boss + Icon), `steps.py` (Step-Dispatcher), `worker.py` (sequence_worker), `status.py` (Laufstatus für
  Beobachter ausserhalb des Prozesses).

- `autoclicker/befehl.py` — der **Rückweg** zu `runtime/status.py`: dort schreibt der
  Hauptprozess, was läuft, hier legt das Studio ab, was passieren soll. Ein Briefkasten,
  kein Log — wer liest, leert ihn, und zu alte Befehle fliegen weg (siehe unten beim
  Sequenz-Studio). Liegt bewusst **nicht** unter `runtime/`: dessen `__init__` zieht den
  Worker samt `imaging` und `winapi` nach, und das Fenster braucht nichts davon.

  **`status.py` ist reine Anzeige und darf den Lauf nie stören** — jeder Schreibfehler
  wird geschluckt. Drei Schreiber führen ihren Teil ein, statt ihn zu ersetzen: der
  Worker kennt Zyklus und Phase, `execute_step` den Block, die Warteschleifen
  (`wartet()`) das, worauf gerade gewartet wird — keiner das Ganze.
  Geschrieben wird höchstens alle 200 ms; Phasen- und Zykluswechsel umgehen die
  Drossel (`sofort=True`), weil ein übersprungener Sprung nicht nachgeholt wird.

  **Ein wartender Lauf ist kein toter Lauf.** Der Leser erkennt einen abgestürzten
  Lauf am Alter des Zeitstempels (älter als 5 s = verwaist), und das geht nur, wenn
  ein lebender Lauf ihn frisch hält. Geschrieben wird sonst pro Schritt — aber ein
  Schritt kann minutenlang dauern (Farb-Trigger bis `pixel_wait_timeout`,
  Boss-Watcher bis `llm_watcher_timeout`). Deshalb ruft **jede Schleife, die den
  Worker länger aufhält**, `status.lebenszeichen(state)` — oder `status.wartet()`,
  das über dieselbe Funktion schreibt und dabei noch sagt, worauf gewartet wird.
  Heute: `_warte_schleife`, `_farb_schleife` und der Boss-Watcher. Ein Test hält das
  fest — ohne die Aufrufe sähe genau der Lauf tot aus, der gerade wartet, und das ist
  der Fall, für den man die Ansicht aufmacht.
- `autoclicker/editors/sequence_studio/` — das Studio-Fenster:
  - `bridge.py`: stabile `StudioBridge`-Fassade und Initialisierung.
  - `bridge_contract.py`: öffentliches Protokoll, Konstanten und reine Helfer.
  - `bridge_view.py`: Momentaufnahme und JSON-Projektionen.
  - `bridge_services.py`: Persistenz, Laufsteuerung und Konfiguration.
  - `bridge_editing.py`: Phasen-, Block-, Auswahl- und Punkt-Kommandos.
  - `bridge_teilen.py`: Export/Import im Reiter „Teilen".
  - `bridge_werkzeuge.py`: prüfen, kalibrieren, Klick-Runde im Reiter „Werkzeuge".
  - `scans.py`: stabile `ScanTeil`-Fassade.
  - `scan_contract.py`, `scan_state.py`, `scan_interaction.py`,
    `scan_learning.py`, `scan_library.py`: Scan-Protokoll und getrennte
    Verantwortlichkeiten.
  - `scan_detect.py`: Boss- und Icon-Scans (Region, Erkennung, Aktion, Test,
    Boss-Bibliothek). Getrennt von den Item-Modulen, weil es eine andere Frage
    ist: der Item-Scan sucht *viele* Dinge in *vielen* Flächen, ein
    Erkennungs-Scan **ein** Ding in **einer**.
  - `scan_capture.py`: Screenshot-/Fensteraufnahme; `scan_model.py`:
    GUI-freies Laden/Speichern; `model.py`: Board und Farbhelfer.
  - `web/`: HTML, CSS, JavaScript und Logo.
- Editor-Capture-Helfer: `editors/_detection_capture.py` (`capture_markers`, geteilt von Boss- und Icon-Editor). Aktions-Konstanten zentral in `models.py` (`ACTION_*`), Familien-Namen (`ELSE_*`/`BOSS_ACTION_*`/`ICON_ACTION_*`) sind Aliase.
- `autoclicker/handlers.py` — Hotkey-Handler (Glue-Code zwischen Hotkey und Editor/Action).
- `autoclicker/editors/` — Interaktive Console-Editoren. `sequence_editor/` und `item_editor/` sind Subpackages. Zwei Ausnahmen laufen aus den Hook-Callbacks statt aus Konsolen-Eingaben: `sequence_recorder.py` (die Aufnahme, s.o.) und `nachklick.py` (die Klick-Runde, die Punkte durch Nachklicken kalibriert — s.u. bei „Koordinaten nach einem Bildschirm-Umbau“).
- `market_analysis/` — **eigenständiges Subsystem, nicht Teil des Autoclickers.** Zieht Marktpreise und Rezepte aus der Idle-Clans-API und rechnet Gold/h pro Item (`analyse.py`, `verify.py`, `apicheck.py`, `config.py`). Importiert **nichts** aus `autoclicker/`, braucht kein Windows, hat eigene Abhängigkeiten (pandas/requests/openpyxl) und ein eigenes `market_analysis/README.md` — das ist dort die Wahrheit, nicht diese Datei. Generiertes landet in `market_analysis/output/` (gitignored). Wer am Autoclicker arbeitet, fasst den Ordner nicht an; wer an der Analyse arbeitet, umgekehrt.

  **Die eine Verbindung ist eine Datei, kein Import.** `export_market_values()` schreibt
  `output/marktwert.json` (Item-Name → Gold pro Stück); trägt man den Pfad in der
  `config.json` des Autoclickers unter `scan_market_value_file` ein, sortiert der
  Item-Scan seine Klicks danach statt nach der von Hand getippten `priority`
  (`lade_marktwerte()` in `runtime/item_scan.py`, zwischengespeichert am mtime — eine
  neu gerechnete Analyse greift ohne Neustart). Zwei Tests messen die Trennung im
  **Import-Baum** (nicht im Text: in Kommentaren darf stehen, woher die Datei kommt).

  Zwei Eigenschaften, die man kennen muss: die gespeicherte `item.priority` wird
  **nicht** überschrieben — die Sortierung gilt nur für den Lauf, `items.json` bleibt
  unberührt. Und **jedes Item mit Marktwert gewinnt gegen jedes ohne**, weil der Wert
  negiert einsortiert wird. Das ist gewollt (ein gemessener Wert schlägt eine getippte
  Zahl), heisst aber: was nicht in der Tabelle steht, rutscht nach hinten. Wer das nicht
  will, lässt `scan_market_value_file` leer — dann ändert sich gar nichts.

**Das Studio läuft als eigener Prozess**, nicht im Hauptprozess: ein
Fenster-Event-Loop und die Windows-Hotkey-Message-Pump vertragen sich nicht im selben
Thread. Gestartet wird es vom Handler per `subprocess.Popen([sys.executable, "-m", ...])`;
`pywebview` ist optional und wird beim Start des Subprozesses geprüft.

**Es ist EIN Fenster, nicht mehr zwei.** Daneben stand bis zum Umbau ein zweites in
Dear PyGui (`autoclicker/scan_studio.py` + `editors/scan_canvas/`) für Slots, Items
und Scans. Es ist ersatzlos gelöscht: zwei Fenster mit zwei Bedienkonzepten für
dieselben Dateien waren eines zu viel, und die Scans gehören dorthin, wo die Sequenz
steht, die sie benutzt. `CTRL+ALT+V` startet deshalb denselben Prozess wie
`CTRL+ALT+B`, nur mit vorgewähltem Reiter (`--scans` → `bridge.start_ansicht`).

| Einstiegspunkt | Oberfläche | arbeitet auf |
|---|---|---|
| `autoclicker/sequence_studio.py` (`handle_sequence_studio`, `handle_scan_studio`) | `editors/sequence_studio/` (pywebview) | `sequences/<name>.json`, `config.json`, `slots/`+`items/`+`item_scans/` |

**Der Scans-Reiter merkt, wenn der Hauptprozess seine Dateien anfasst.** Er las
`slots.json`, `items.json` und `item_scans/` genau einmal je Sitzung — und ein
Lauf mit `learn_unknown` legt in derselben Zeit neue Items an und **speichert**
sie. Die Konsole meldete „gelernt", im Reiter waren sie nicht da, und man sucht
den Fehler beim Lernen statt bei der Ansicht. `_platte_stand()` merkt sich die
Änderungszeiten beim Laden, `_platte_fremd()` vergleicht sie bei jeder
Momentaufnahme, und die Ansicht bietet „Neu laden" an. Zwei Regeln dazu:

- **Kein eigener Schreibvorgang zählt mit** (`_platte_nachziehen()`). Für das
  Speichern war das von Anfang an klar; für zwei andere nicht, und dort log der
  Hinweis: das gemerkte Bild liegt unter `item_scans/bilder/`, und das **Anlegen
  des Unterordners** dreht die Änderungszeit von `item_scans/` weiter — der
  Reiter meldete also direkt nach der eigenen ersten Aufnahme eine
  Fremdänderung. Dasselbe beim Löschen einer Scan-Datei. Ein Hinweis, der nach
  der eigenen Aktion kommt, ist genau der, den man sich abgewöhnt zu lesen.
  Nachgezogen wird deshalb **gezielt** (nur die berührten Pfade); ein Rundum-
  Nachziehen verschluckte eine fremde Änderung, die in derselben Sekunde kam.
- **Ungespeichertes wird nicht kommentarlos verworfen.** Bei offenen Änderungen
  stehen zwei Knöpfe („Speichern & neu laden", „Verwerfen & neu laden") statt
  einer Rückfrage: was passiert, steht dann *vor* dem Klick da.

Daraus folgt: **beide Seiten kennen die Änderungen der anderen erst nach dem Neuladen.**
Der Subprozess liest die Dateien beim Start und schreibt sie beim Speichern; der
Hauptprozess hält seinen eigenen Stand im Speicher. Für Config und Scan-Daten holt er
sie inzwischen selbst nach (Briefkasten-Befehle `config` und `daten`), für Sequenzen
weiterhin auf `CTRL+ALT+L`. Wer im Hauptprozess speichert, während der Subprozess offen
ist, verliert eine der beiden Fassungen. Beim Erweitern also nichts einbauen, das auf
gemeinsamen State setzt — der gemeinsame Nenner ist die Datei.

**Das Sequenz-Studio zeigt Listen, keinen Node-Graph.** Es *war* ein
`dpg.node_editor`, und daran hing seine Unbedienbarkeit: ein Node-Graph verspricht
mit jedem Pixel, dass man Verbindungen ziehen darf. Es gab aber keinen einzigen
Link-Callback (die Pfeile waren Dekoration), die Block-Positionen wurden bei jedem
Neuaufbau aus `(Spalte, Zeile)` neu gerechnet (verschobene Blöcke sprangen zurück),
und umsortiert wurde mit `^`/`v` einzeln — bei einer 50-Schritt-Aufnahme unbenutzbar.

**Eine Sequenz ist kein Graph.** Pro Phase ist sie eine lineare Liste, und die
einzige Verzweigung (`else_config`) ist ein *Attribut*, keine Kante. Die Liste
verspricht deshalb nur, was sie einlösen kann — dafür kann sie es richtig: Ziehen
sortiert um, auch **über Phasengrenzen** (das kann der Konsolen-Editor bis heute
nicht), Mehrfachauswahl mit STRG, Sammel-Aktionen auf der Auswahl.

**Die Oberfläche ist seit dem zweiten Umbau eine Webseite** (`web/index.html` in einem
pywebview-Fenster). Dear PyGui gab die Listen zwar her, aber jede Zeile war Text: was
ein Block tut, stand in einer Zeichenkette, und alles Weitere lag in einer Seitenleiste
oder in einer aufgeklappten Zeile darunter. Karten können zeigen, was Text beschreiben
muss — Typ als Marke, Farb-Trigger als Farbfeld, ELSE als eigene Zeile. Das ist der
ganze Grund für den Wechsel; die Datenschicht (`model.py`) ist dieselbe geblieben.

**Die Oberfläche hält keinen Sequenz-Zustand.** Sie bekommt über
`StudioBridge.snapshot()` (implementiert im `BridgeViewMixin`) eine
Momentaufnahme, zeichnet sie, und schickt jede Änderung als Befehl zurück, der die
nächste Momentaufnahme liefert. Zwei Wahrheiten gäbe es sonst, und die gespeicherte
wäre nicht zwingend die angezeigte.

**Sieben Ansichten, ein Fenster** (Umschaltleiste im Kopf). Welche offen ist, ist
reiner Oberflächenzustand — er steht nicht in der Momentaufnahme und nicht in der
Brücke, denn er ändert nichts an der Sequenz. Der Editor bleibt beim Umschalten im
Dokument stehen (nur `hidden`), damit Scrollstand und ungespeicherte Eingaben den
Ausflug überleben.

| Ansicht | was | Brücke |
|---|---|---|
| Editor | Phasen und Blöcke bearbeiten | `snapshot()` + Befehle |
| Sequenzen | Übersicht, Kennzahlen, Öffnen | `sequenz_liste()` |
| Live-Run | was gerade läuft | `lauf_status()` |
| Scans | Slots, Items, Item-Scans auf einem Screenshot | `scan_daten()` + `scan_*` |
| Teilen | Bündel schreiben und einlesen | `teilen_daten()` + `export_/import_*` |
| Werkzeuge | prüfen, kalibrieren, Klick-Runde | `werkzeug_daten()` + `werkzeug_/kalib_*` |
| Einstellungen | `config.json` bearbeiten | `config_lesen()` / `config_schreiben()` |

**Zwei Kanäle zur Brücke, und die Unterscheidung ist keine Kosmetik.** `ruf()`
befiehlt und **ersetzt** mit der Antwort die Momentaufnahme `S`; `frage()` fragt nur
und lässt `S` in Ruhe. Übersicht, Laufstatus und die Einstellungen geben keine
Momentaufnahme zurück, sondern einen eigenen Gegenstand — über `ruf()` geholt
zerschösse ihre Antwort den Editor-Zustand, und ein Blick in die Übersicht wäre ein
Datenverlust. Wer eine Methode ergänzt, entscheidet zuerst, welcher der beiden Kanäle
gemeint ist. Der Test `jeder Aufruf der Seite passt zur Brücke` erfasst **beide**
Schreibweisen.

`config_schreiben()` ist der Sonderfall, der die Regel bestätigt: sie **ändert** etwas
und gehört trotzdem zu `frage()`. Geändert wird die Config, nicht die Sequenz — eine
Momentaufnahme wäre dafür der falsche Gegenstand. Der Kanal richtet sich also danach,
was zurückkommt, nicht danach, ob etwas passiert.

Zwei Eigenschaften der Übersicht, die man kennen muss: sie sieht den Ordner **selbst**
durch statt `list_available_sequences()` zu fragen (die überspringt unlesbare Dateien
stillschweigend — richtig für ein Menü, falsch für eine Übersicht: genau dann sucht
man die Datei im Explorer), und geöffnet wird über den vorhandenen `laden`-Befehl,
damit die Rückfrage bei ungespeicherten Änderungen greift.

**Der Scans-Reiter arbeitet auf einem eingefrorenen Screenshot** (`ScanTeil`-
Fassade in `scans.py`, Aufnahme in `scan_capture.py`, Zustands-/Interaktionslogik
in den übrigen `scan_*.py`-Modulen). Slots werden dort aufgezogen, wo sie im
Spiel liegen; Koordinaten tippt niemand. Er bearbeitet `slots/slots.json`,
`items/items.json` und `item_scans/<name>.json` — also wieder andere Dateien
als der Editor, weshalb auch hier die Sequenz-Bedienelemente im Kopf verschwinden
und ein eigener Speichern-Knopf rechts steht.

**Der Item-Scan ist das Übergeordnete, nicht die Auswahl.** Wer mehrere Spiele
betreibt, hat alle Slots und Items aller Spiele in einer Liste — und keiner davon
gehört sichtbar irgendwohin. Deshalb gibt es `scan_offen` **neben**
`scan_art`/`scan_name`: der offene Scan ist der Zusammenhang, die Auswahl ist das
Ding, das man gerade bearbeitet. Beides an einer Variable hiesse, dass ein Klick
auf einen Slot den Zusammenhang verliert (so war es zuerst gebaut). Am offenen
Scan hängen: die Filter der Listen (`nur_dabei`), was im Bild gezeichnet wird,
welche Items `scan_erkennen()` prüft und welche Toleranz dabei gilt.

**Die Reihenfolge der Reiter ist die Rangfolge**: Scans, dann Slots, dann Items —
und beim Öffnen steht der Scan-Reiter vorn. Eine Liste, die vor ihrer Klammer
steht, liest sich wie das Hauptding; genau das war der Zustand, aus dem heraus
„alle Items aller Spiele in einer Liste" überhaupt entstand.

**Beim Öffnen ist der zuletzt bearbeitete Scan offen** — dieselbe Regel wie
`zuletzt_bearbeitet()` bei den Sequenzen und aus demselben Grund: ein echtes
„zuletzt geöffnet" müsste jemand mitschreiben, und das Dateisystem weiss es
schon. Vorher öffnete sich nur bei *genau einem* Scan etwas; wer einen zweiten
anlegte, sah eine leere Mitte und musste erst merken, dass oben links eine
Auswahl steht.

**Ein Scan ohne Bild ist nicht dasselbe wie ein Scan ohne Inhalt.** Ein älterer
Scan bringt seine Slots mit, aber kein gemerktes Bild — das gibt es erst, seit
der Reiter eines ablegt. `_flaeche()` rechnet die Arbeitsfläche deshalb notfalls
aus dem umschliessenden Rechteck der Slots (mit Rand); alle Umrechnungen laufen
über `links`/`oben`/`skala` und stimmen genauso, nur ist der Hintergrund leer.
Ein späterer Screenshot legt sich dahinter, ohne dass sich etwas verschiebt.
Das Feld `bild` sagt, was von beidem dasteht — ohne das forderte die Seite ein
Bild nach, das es nicht gibt, und alles, was ein Bild *braucht* (Erkennen,
Item lernen, Farbe messen), stünde offen. Die Ersatzfläche darf als einzige über
100 % hinaus (bis 400 %): sie hat keine Pixel, die man fälschen könnte, und ein
Inventar von 300 px hinge sonst verloren in einer Ecke.

**Die alten Screenshots unter `slots/Screenshots/` sind kein Ersatz dafür.** Sie
stammen aus dem Konsolen-Slot-Editor und sind **Ausschnitte** (`take_screenshot(region)`),
deren Ursprung nirgends steht — als Arbeitsfläche benutzt, läge jeder Slot still
falsch. Genau der Fehler, gegen den der Ursprung im PNG steht.

**Jeder Scan merkt sich seinen Bildschirm.** `item_scans/bilder/<name>.png`, beim
Öffnen sofort wieder da — vorher war die Mitte des Reiters leer, bis man einen
neuen Screenshot machte. Der **Ursprung des virtuellen Desktops steht IM PNG**
(Text-Chunk `links`/`oben`), nicht in einer Datei daneben: zwei Dateien, die
zusammengehören, laufen irgendwann auseinander, und dann sind alle Koordinaten
still um einen Monitor verschoben.

Sechs Regeln, an denen der Reiter hängt:

- **Der Screenshot bleibt in Python.** Die Seite bekommt ihn einmal als
  verkleinertes Bild (`scan_bild()`, getrennt von `scan_daten()`, weil er der
  grosse Brocken ist); **gemessen wird nie darauf**, sondern immer im
  Originalbild (`_foto_farbe`). Eine Farbe aus einem skalierten Bild wäre
  interpoliert — und genau diese Farbe soll der Worker später wiederfinden.
- **Ein Rechteck entsteht aus zwei Klicks, nicht aus einem Zug.** Beim Ziehen
  verrutscht die Ecke um ein paar Pixel, und bei einem Slot von 60 px schneidet
  das schon das Symbol an. Zwischen den beiden Klicks zeigt die Ansicht das
  entstehende Rechteck.
- **Daneben klicken zieht ein Auswahl-Rechteck auf**, und die Sammel-Aktion
  arbeitet auf der Auswahl — dieselbe Regel wie im Sequenz-Editor. Ein einzelner
  Slot ist ein Klick; dreissig wären sonst dreissig Klicks und dreissig
  Löschungen. Gewählt ist, was **ganz** im Rechteck liegt: „alle, die darin
  sind" heisst genau das, und ein angeschnittener Slot wäre eine Ermessensfrage
  — bei einer Sammel-Löschung das Falsche. STRG-Klick nimmt einzelne dazu oder
  heraus. `_auswahl` (die Menge) steht neben `scan_name` (der eine, den der
  Inspektor bearbeitet): zwei Dinge, zwei Felder, sonst hätte „Farbe messen"
  bei dreissig Gewählten keine Bedeutung.

  **Das Rechteck wählt, es löscht nicht.** Direkt zu löschen wäre der kürzere
  Weg und der falsche: ein um fünfzig Pixel zu weit gezogenes Rechteck nähme
  wortlos dreissig Slots mit. Gewählt sieht man erst, was man verliert; der
  zweite Griff (Entf oder „N löschen") kostet einen Klick.
  Aus demselben Grund wählt ein einzelner Klick ins Leere **nicht** mehr ab —
  er fängt das Rechteck an, und die Abwahl ist das leere Rechteck oder ESC.
- **Es gibt ein Rückgängig, und es merkt sich den ganzen Stand** (`_merke()` /
  `scan_rueckgaengig()`, STRG+Z). Das war lange die grösste Lücke des Reiters:
  ein Rechteck über dreissig Slots und ein Druck auf Entf waren endgültig, und
  der einzige Ausweg hiess „Neu laden" — der wirft *alles* seit dem letzten
  Speichern weg. Zwischen „ich habe mich um einen Slot vertan" und „ich werfe
  den Nachmittag weg" lag nichts.

  **Ein vollständiger Abzug statt einzelner Rückwärts-Schritte.** Eine Aktion
  hier rührt fast immer an mehrere Stellen gleichzeitig: ein gelöschter Slot
  verschwindet aus jedem Scan, ein umbenanntes Item wird überall nachgezogen.
  Rückwärts-Schritte müssten jede dieser Nebenwirkungen einzeln kennen — und
  ein vergessener wäre ein Rückgängig, das die Daten *halb* zurückdreht. Das ist
  schlimmer als keins. Ein Abzug kostet bei einem echten Bestand rund 30 KB,
  `UNDO_TIEFE` (30) deckelt den Speicher.

  Drei Regeln beim Erweitern:
  - **`_merke()` ruft die Methode, die ändert** — nicht die Oberfläche. Sonst
    hinge das Rückgängig daran, dass jeder Knopf daran denkt.
  - **Nur bei einer echten Änderung.** Ein abgelehntes Feld oder ein Name, der
    derselbe bleibt, legt nichts auf den Stapel; deshalb steht `_merke()` in den
    einzelnen Zweigen und nicht oben am Eingang. Ein STRG+Z, das einmal
    scheinbar gar nichts tut, ist ein Rückgängig, dem man nicht mehr traut.
  - **Was auf Platte passiert ist, kommt nicht zurück.** Ein gelöschter Scan
    kehrt als Konfiguration wieder (und wird beim nächsten Speichern neu
    geschrieben), sein gemerkter Screenshot ist weg. Das steht in der Meldung,
    statt ein vollständiges Zurück zu versprechen, das es nicht gibt.
    `scan_neu_laden()` leert den Stapel — er beschreibt Stände, die es nach dem
    Neulesen nicht mehr gibt.
- **Was man nicht treffen kann, kann man nicht löschen.** Ein Slot von 2×2 px
  entsteht aus zwei Klicks fast auf dieselbe Stelle — und war danach kaum wieder
  loszuwerden, weil Löschen Auswählen voraussetzt. Drei Stellen zusammen lösen
  das: `MIN_SLOT` (8) lässt ihn gar nicht erst entstehen, `TREFFER_MIN` (14)
  weitet die *Trefferfläche* vorhandener Winzlinge auf (den Slot selbst nie —
  gemessen wird, was dasteht), und `_slot_unter()` nimmt den **kleinsten**
  Slot unter dem Zeiger statt des obersten, damit ein Winzling in einem grossen
  Slot überhaupt erreichbar ist. Dazu markiert die Liste ihn (`winzig`): dort ist
  er so gross wie jeder andere, und das ist der zweite Weg zum Löschen.
- **Was ein Klick bedeutet, sagt ein Modus** (`MODI` in `scan_contract.py`,
  über `scans.py` weiterhin öffentlich importierbar: wählen, neuer
  Slot, Hintergrundfarbe, Klickpunkt) — ein Klick, dessen Bedeutung man raten
  muss, ist schlimmer als ein Modus-Knopf. Jeder Modus liegt zusätzlich auf
  seinem Anfangsbuchstaben; ein Test hält Kacheln und `MODI` gegeneinander —
  **Zug um Zug, nicht als Menge**, denn die Reihenfolge ist die Rangfolge:
  „Slots finden" steht direkt hinter „Auswählen", weil es das ist, was man
  *zuerst* macht. Das Automatische ist der Normalfall, das Aufziehen von Hand
  der Ausweichweg. Als vorletzte Kachel stand es da, wo man den Notnagel sucht —
  und wer der Liste folgte, hatte 45 Slots einzeln aufgezogen, bevor er es fand.
- **Jeder Modus hat einen Rückweg, und der ist die markierte Kachel selbst.**
  Nochmal darauf klicken (bzw. den Buchstaben nochmal drücken) führt zurück ins
  Auswählen und räumt eine halb gesetzte Ecke mit weg — dieselbe Regel wie bei
  der ELSE-Kachel im Sequenz-Editor, und aus demselben Grund: ein Modus, in den
  man nur hinein kommt, ist eine Falltür. ESC allein reicht nicht, denn ESC
  sieht man einem Bild nicht an; das Umschalten steht deshalb im Tooltip der
  markierten Kachel **und** im Hinweis unter dem Raster. `MODUS_WAHL` ist
  ausgenommen — er *ist* der Rückweg.

  **Der Modus bleibt dagegen stehen, solange man in ihm arbeitet**: wer zwanzig
  Slots aufzieht, fasst die Kachel einmal an. Von selbst endet nur ein Modus,
  der einen Durchgang hat statt einer Tätigkeit — `finden` schaltet nach der
  Suche zurück, und zwar auch dann, wenn nichts Neues dabei war. Sonst liesse
  derselbe Klick einen mal im Modus stehen und mal nicht, je nach Ergebnis.

  **Was man ZWISCHENDURCH tut, braucht keinen Modus** (`scan_direkt()`).
  ALT-Klick misst den Hintergrund des Slots unter dem Zeiger, Doppelklick setzt
  seinen Klickpunkt — beides ohne den Umweg über die Kachel und beides wählt den
  Slot gleich mit aus. Der Unterschied zu den Modi ist nicht Bequemlichkeit,
  sondern die Frage, die dahintersteht: ein Modus beantwortet „was tut ein Klick
  **jetzt**" und lohnt sich, solange man dasselbe zwanzigmal tut. Eine einzelne
  Korrektur an einem Slot, den man vor sich sieht, ist das Gegenteil davon — dort
  ist der Moduswechsel hin und zurück teurer als der Handgriff selbst.
- **Ein Slot lässt sich verschieben, ohne vier Zahlen zu tippen.** Ziehen im
  Bild oder Pfeiltasten (SHIFT = 10 px), beides über `scan_verschieben()` und
  beides auf der ganzen Auswahl. Der Fall ist Alltag: das Spielfenster ist
  umgezogen, die Erkennung sass eine Zeile zu hoch. Über die Zahlenfelder war
  das bei einem Slot mühsam und bei dreissig ausgeschlossen.

  Drei Regeln dazu:
  - **Der Klickpunkt geht mit**, statt neu aus der Mitte gerechnet zu werden —
    er ist womöglich bewusst aus der Mitte gesetzt.
  - **Gepackt wird nur, was schon gewählt ist.** Damit braucht die Seite keine
    eigene Trefferregel: welcher Slot unter dem Zeiger liegt, entscheidet
    weiterhin `_slot_unter()` in Python. Zwei Trefferregeln wären zwei
    Antworten auf dieselbe Frage.
  - **Eine gehaltene Pfeiltaste ist EIN Verschieben.** Nur der erste Schritt
    einer Serie kommt auf den Rückgängig-Stapel (`zaehlt`), sonst läge er nach
    zwei Sekunden Halten voll mit Ein-Pixel-Schritten und der Schritt davor wäre
    herausgefallen.
- **Sammel-Aktionen arbeiten auf der Auswahl** — und zwar auf mehr als
  „löschen". Bis hierher konnte eine Mehrfachauswahl genau das, womit das
  Rechteck ein Werkzeug zum Wegräumen war und sonst nichts. Dabei betreffen
  gerade die Handgriffe nach dem Finden fast immer viele Slots auf einmal:
  Grösse angleichen, Hintergrund neu messen, aus der Auswahl lernen, die
  Auswahl in den Scan aufnehmen. Worauf sie wirken, beantwortet
  `_auswahl_slots()` an **einer** Stelle (Auswahl, sonst der eine Gewählte) —
  sonst nähme „löschen" dreissig Slots und „angleichen" einen.

  Zwei davon hätten eine naheliegende und falsche Fassung: „Hintergrund messen"
  misst **jeden Slot an sich selbst** statt eine Farbe für alle zu setzen
  (Inventare sind selten gleichmässig ausgeleuchtet, und eine gemeinsame Farbe
  verschöbe die Lernmaske an jedem Slot ein bisschen), und „Grösse angleichen"
  nimmt den **Median** statt des grössten oder kleinsten — ein einzelner
  Verklicker soll nicht alle anderen verbiegen.
- **Die Erkennung fragt die Laufzeit, nicht sich selbst.** `scan_erkennen()`
  ruft `_check_profile_match()` aus `runtime/item_scan.py` — dieselbe Funktion,
  die im Lauf entscheidet, mit einem `state`-Stellvertreter, der nichts als die
  Config trägt. Eine zweite Rechnung „nur für die Vorschau" wäre eine Vorschau,
  die etwas anderes zeigt als das, was passiert.

  **Nach dem Finden läuft sie von selbst** (`_gleich_erkennen()`). Die Frage
  nach dem Finden ist nicht „habe ich Slots", sondern **„was davon kenne ich
  schon"**: sonst stehen zwanzig gleich aussehende Rechtecke da, und der
  nächste Schritt lernt stumpf alle zwanzig — auch die neunzehn, die längst im
  Bestand liegen. Grün heisst „erledigt, kümmere dich um den Rest"; der Treffer
  ist dabei ein **Vorschlag, keine Festlegung** (stimmt er nicht, lernt man aus
  demselben Slot ein weiteres Item).

  Gemessen an einem vollen Inventar (45 Slots gegen 45 Items) kostet das
  ~310 ms und damit weniger als das Finden davor; ohne Items im Bestand ist es
  augenblicklich und sagt gar nichts. Dass es nicht teurer wird, wenn der
  Bestand wächst, liegt an `_kandidaten()`: bei offenem Scan werden nur dessen
  Items geprüft.

  Die **Rechnung gibt es nur einmal** — `_erkennen_lauf()` füllt `_treffer`,
  die Meldung baut jeder Anlass selbst (der Knopf sagt das Ergebnis, das Finden
  hängt es an seine eigene Meldung). Zwei Erkennungen wären zwei Ergebnisse.
- **Die Slot-Zustände liegen auf einem SPIELBILD, nicht auf dem Panel.** Deshalb
  haben sie eine eigene, grellere Farbfamilie (`--slot-ok` `#00E58A` =
  erkannt und im Scan, `--slot-fremd` `#22D3EE` = erkannt, aber nicht in diesem
  Scan, `--slot-offen` `#F43F5E` = nichts erkannt, hier ist zu tun) und
  **jeweils eine Füllung** dazu (Suffix `-f`).

  Die drei Werte sind gemessen, nicht geraten, und stehen in einem Test fest.
  `--slot-offen` war `#FF9500` und damit fast der Akzent `#F59E0B`: „zu tun" und
  „gewählt" sahen gleich aus — **Amber gehört der Auswahl**, sonst markiert die
  Markierung nichts. `--slot-ok`/`--slot-fremd` lagen als `#00FF9C`/`#2DD4BF` zu
  dicht beieinander, um sie im Bild zu trennen. Die Klassenlogik
  (`.scan-slot.treffer` / `.fremditem` / `.leer`, `SLOT_FARBE` in `app.js`)
  blieb dabei unverändert — nur die Variablen. Ein 1,5-px-Umriss in `var(--dim)` verschwindet
  zwischen bunten Item-Symbolen restlos — genau das war „nichts erkannt" vorher,
  also ausgerechnet der Zustand, den man sucht. Die Fläche trägt die Aussage,
  der Strich schärft sie.

  Marke im Bild und Zeile in der Liste lesen **dieselben** Variablen
  (`SLOT_FARBE` liest sie einmal aus `getComputedStyle`), statt Hexwerte zu
  wiederholen. Drei Tests halten das zusammen: jeder Zustand braucht Umriss
  *und* Füllung, jede benutzte `--slot-*`-Variable muss definiert sein, und
  `SLOT_FARBE` muss genau die Zustände abdecken.
- **Erkannt ist nicht dasselbe wie im Scan** (`treffer.fremd`, türkis statt
  grün). Der Fall entsteht bei einem Scan ohne Items, denn dann prüft
  `_kandidaten()` den ganzen Bestand — und dort ist es die nützlichste Auskunft
  überhaupt: das Item kennst du schon aus einem anderen Spiel, es fehlt nur das
  Häkchen (ein Knopf im Inspektor). Grün zu färben hiesse behaupten, der Scan
  finde es; er sieht dieses Item gar nicht an. Ein Häkchen ändert nicht, WAS
  erkannt wurde — `_treffer_mitgliedschaft()` zieht deshalb nur das Merkmal
  nach, statt neu zu rechnen.

- **Ein Item ist mehr als ein Haken** (`scanItemMaske()`). Die Item-Liste konnte
  nur „gehört dazu / gehört nicht dazu"; Name, Kategorie und Priorität kosteten
  je einen Klick in die Liste, einen Blick in die rechte Spalte und einen Weg
  zurück — bei sechzig Items sechzig Mal. Genau diese vier Angaben ändert man,
  und sie passen nebeneinander: Haken, Vorschau, Name, darunter Kategorie und
  Priorität.

  Sie stehen deshalb **nur** dort: der Inspektor hat die drei Felder abgegeben
  und sagt, wo sie sind. Dieselbe Sache an zwei Stellen wären zwei Wahrheiten,
  und man müsste raten, welche führt — dieselbe Auflösung wie beim Namen des
  Scans und beim Klick-Block im Sequenz-Editor.
- **Die Item-Masken stehen in der RECHTEN Spalte** (`scanItemsRechts()`). Die
  breitere Spalte war die leerere: links sind 290 px und darin fünf Blöcke
  übereinander — die Liste, mit der man arbeitet, fängt ganz unten an —, rechts
  sind 370 px, und die standen seit dem Umbau fast leer, weil die drei Felder in
  die Maske gewandert sind. Eine Maske braucht Breite: Name, Kategorie und
  Priorität nebeneinander.

  **Nur die Items.** Scans und Slots bleiben links: der Scan ist Navigation (man
  wählt ihn und arbeitet dann woanders), und einen Slot zieht man im **Bild**
  auf — seine Liste ist der zweite Weg dorthin, nicht die Arbeitsfläche. Der
  Preis dafür ist, dass eine Reiterleiste Inhalt in zwei Spalten steuert; deshalb
  **sagt der Reiter es** („Die Item-Masken stehen rechts …") und der leere
  Abschnitt hört auf zu wachsen (`nur-reiter`), statt als leeres Feld dazustehen.
- **Was man an einem Item selten ändert, klappt IN seiner Maske auf**
  (`scanItemDetails()`): das grosse Bild, Vorlagen, Marker, Konfidenz, Löschen —
  und zwar nur beim gewählten, denn sechzig aufgeklappte Blöcke wären keine
  Liste mehr. Sie in eine eigene Spalte zu legen hiesse, beim Arbeiten an einem
  Ding zwischen zwei Orten hin und her zu sehen; die Maske trägt seine Identität
  ohnehin schon. **Eine** Funktion baut den Block — der Rückweg (ein Item ist
  gewählt, während eine andere Liste offen steht) ruft dieselbe, sonst wären es
  zwei Stellen, an denen ein Feld fehlen kann.

- **Die Kategorie wird gewählt, nicht getippt** (`kategorieWahl()`). Ein freies
  Textfeld allein hat das Problem, das man nicht sehen kann: „Helme", „helme"
  und „Helmr" sind drei Kategorien — und Items derselben Kategorie konkurrieren
  miteinander (das kleinere P gewinnt), eine vertippte trennt ein Item still von
  seiner Gruppe. Ein `<select>` allein wäre zu streng: neue Kategorien müssen
  ohne einen zweiten Bedienweg entstehen können. Also **beides in einem
  Bedienelement**, mit dem Auswählen als Normalfall und `＋ neue Kategorie …`
  als Ausweg; was dort übernommen wird, steht beim nächsten Item in der Liste.

  Vorher war Tippen der einzige Weg und die `<datalist>` daneben ein Angebot,
  das man kennen musste. Sie ist ersatzlos weg — mit ihr `kategorienListe()`,
  denn sie hing an einer `id`, und sechzig Masken mit derselben `id` wären
  neunundfünfzig gewesen, die der Browser ignoriert.

  Drei Regeln dazu:
  - **Der Tipp-Modus überlebt den Neuaufbau** (`kategorieFrei`, Schlüssel je
    Stelle). Die Ansicht wird nach jeder Brücken-Antwort neu gebaut, und der
    Entwurf speichert 900 ms nach der letzten Änderung von selbst: sonst würde
    das Feld mitten im Wort wieder zur Auswahlliste. Dieselbe Mechanik wie
    `offeneHilfen` und `klappZu`, derselbe Grund wie bei `fokusMerken()`.
  - **Der Rückweg ist ESC**, solange es etwas zu wählen gibt — hinein mit einem
    Klick, heraus auch. Ein Modus, in den man nur hinein kommt, ist eine
    Falltür; dieselbe Regel wie bei den Modus-Kacheln und der ELSE-Kachel.
  - **Geraten wird nicht.** `_kategorie_normalisieren()` zieht Leerraum zusammen
    und übernimmt eine bekannte Schreibweise bei gleicher Klein-/Grossschreibung
    — mehr nicht. Ein getipptes Wort stillschweigend in ein ähnliches zu ändern
    ist schlimmer als der Tippfehler.

  Dasselbe Bedienelement steht in der Lern-Vorschau: dort entstehen die
  Kategorien, und dort tippte man sie zwanzigmal. Damit eine in Zeile 1
  angelegte in Zeile 2 wählbar ist, zieht `kategorieOptionenAktualisieren()`
  die Listen aller offenen Felder nach.

  Und weil die Kategorie dort jetzt eine Auswahlliste sein kann, liest
  `scanReviewUebernehmen()` die Zeilen **über Klassen statt über Positionen**.
  Vorher wurden die Felder durchnummeriert gegriffen; wer eines dazwischen
  einbaut, verschiebt still alle folgenden — ein Import, der die Priorität als
  Kategorie liest, fällt niemandem auf.
- **„Items erkennen" muss man in der Item-Liste sehen.** Der Knopf färbte die
  Rechtecke im Bild und füllte die Ergebnisleiste — wer aber in der Item-Liste
  stand (und das ist die Liste, in der man arbeitet), sah nach dem Klick nichts
  und hielt ihn für wirkungslos. `_erkannte_items()` liefert deshalb nicht mehr
  eine Menge von Namen, sondern **Name → Slots**; an jeder Maske steht, wo das
  Item gefunden wurde. „Erkannt" ohne Beleg wäre eine Behauptung, und bei einem
  Fehlgriff (zwei Items sehen sich ähnlich) fehlte genau die Angabe, an der man
  ihn bemerkt.
- **Ein Befehl hat einen Namen.** `scan_erkennen` stand im Assistenten als
  „Erkennung testen" und im Inspektor als „Items erkennen" — zwei Namen für
  einen Knopf, und man probiert beide aus, weil man annimmt, sie täten
  Verschiedenes. Beide heissen jetzt gleich und tragen denselben Tooltip.
- **Mit offenem Scan sind die Items die Arbeit, nicht sein Name.** Die
  Listen-Leiste stand immer auf „Scans": wer einen Scan lud, sah den Namen, den
  er gerade angeklickt hatte, ein zweites Mal und musste erst unten links auf
  „Items" klicken. `scanListe = null` heisst „noch nicht entschieden" — dann
  gilt `scanListeAktiv()` (bei offenem Scan: Items). Sobald jemand einen Reiter
  anfasst, steht dort seine Entscheidung; **das Öffnen eines Scans setzt sie
  zurück**, denn das ist ein Wechsel des Zusammenhangs. Dieselbe Mechanik wie
  `klappZu`.

**Der offene Scan ist der Bezug, nicht der Bestand** (`_scan_slots()`). Wer zwei
Spiele betreibt, hat die Slots beider in einer Datei — und alles, was „alle
Slots" sagte, meinte wirklich *alle*. An drei Stellen war das falsch, und zwei
davon fielen nur als seltsame Zahl auf:

| wo | was man sah |
|---|---|
| „aus allen Slots lernen" | lief über den ganzen Bestand; die Slots des anderen Spiels liegen ausserhalb des Bildes, gemeldet wurde „11 ohne Bild" — und man sucht den Fehler beim Screenshot |
| „X von 56 erkannt" | nannte den Bestand als Nenner, obwohl der Scan 45 hat: elf konnten gar nicht erkannt werden |
| Ersatzfläche ohne Bild | legte sich um beide Spiele und war doppelt so gross wie nötig |

Ohne offenen Scan ist der Bestand die richtige Antwort — dann gibt es keine
engere Menge. Regel beim Erweitern: **wer „alle Slots" meint, fragt
`_scan_slots()`**, nie `self.slots` direkt.

**Ein neuer Scan fängt leer an.** Im Scan-Inspektor standen alle Slots und alle
Items des *gesamten* Bestands — bei zwei Spielen also die des anderen mit. Die
Listen zeigen deshalb nur, was zu diesem Scan gehört; der Rest ist ein Knopf
entfernt („N weitere im Bestand zeigen"), nicht weg.

Slots und Items unterscheiden sich dabei, und der Unterschied ist der Punkt:

- **Slots sind Bildschirm-Koordinaten** und damit immer genau einem Spiel
  zugeordnet. In einem fremden Scan angeboten zu werden ist reines Rauschen.
- **Items können geteilt sein**, und dasselbe Item ein zweites Mal zu lernen ist
  genau das, was man vermeiden will. Deshalb erscheint ein Item auch dann, wenn
  es **gerade in einem Slot erkannt wird** (`_erkannte_items()`, Feld `erkannt`)
  — es steht da, bevor jemand auf die Idee kommt, es neu zu lernen, und ein
  Haken genügt. Gezeichnet wird es türkis, wie sein Rechteck im Bild.

Die Regel „gehört dazu ODER wird gerade gesehen" steht in der **Brücke**, nicht
im JavaScript: sonst wäre sie nicht messbar. Die Ansicht filtert nur noch auf
`dabei || erkannt`.

**Der Name ist die Referenz — also zieht Umbenennen sie nach.** Slots und Items
stehen in Scans per Name; `_slot_umbenennen`/`_item_umbenennen` ändern jede
Fundstelle mit und sagen in der Statuszeile, wie viele es waren. Löschen räumt
sie ebenso weg. Und weil `ItemScanConfig.sync_names()` eine **leere** Namensliste
aus den Objekten wieder auffüllt, muss nach jeder Änderung an den Namen
`_objekte_angleichen()` laufen — sonst kommt ein gelöschtes Item beim nächsten
Speichern zurück. Ein Test pinnt genau das fest.

**Der Weg steht als Weg da, nicht als Wand aus Knöpfen** (`_schritte()`).
Bereich → Slots → Items, mit dem Stand aus den Daten abgeleitet; nur der aktuelle
Schritt trägt einen Knopf. Ein mitgeschriebener Fortschritt könnte von den Daten
abweichen, deshalb heisst „erledigt" schlicht: es ist da.

**Zwischen Schritt 2 und 3 liegt das Spiel.** Slots nimmt man oft an einem
*leeren* Inventar auf — dann gibt es noch nichts zu lernen. Man füllt es, nimmt
**neu** auf und lernt erst dann. Das steht in Schritt 3, weil es sonst niemand
ahnt: „Items lernen" auf dem alten Bild lernt leere Slots.

**Und die Anleitung klappt sich weg, wenn sie erledigt ist.** Der Weg, das Bild
und die Modus-Kacheln sind zusammenklappbare Abschnitte (`klapp-kopf` /
`klapp-rumpf`); untereinander waren sie länger als die Spalte hoch ist, und die
Listen ganz unten — also das, womit man dauernd arbeitet — erreichte man nur
über die Bildlaufleiste. „So entsteht ein Scan" klappt sich von selbst zu,
sobald alle drei Schritte erledigt sind: beim ersten Mal ist es das Wichtigste
auf der Seite, beim zwanzigsten sind es drei Zeilen im Weg.

Zwei Regeln, ohne die es ein Rückschritt wäre:

- **Zugeklappt bleibt die Auskunft stehen**, nur die Bedienelemente gehen weg —
  im Kopf steht dann der offene Schritt, die Bildgrösse bzw. der aktuelle Modus.
  Platz sparen darf nichts kosten, was man beim Arbeiten braucht.
- **Die Automatik überstimmt keine Entscheidung.** `klappZu[…] === null` heisst
  „noch nichts entschieden" und lässt `klappVorgabe()` gelten; sobald jemand
  einen Kopf anfasst, steht dort true/false und die Vorgabe schweigt. Ein
  Bedienelement, das zurückspringt, ist keine Hilfe.

**Die Bühne springt zum gewählten Slot** (`scanZeigeGewaehlten()`). Liste und
Bild waren zwei getrennte Welten: einen Slot in der Liste anzuklicken markierte
ihn im Bild — nur sah man das nicht, wenn er gerade ausserhalb lag, und bei 45
Slots auf 1:1 ist das der Normalfall. Gescrollt wird **nur beim Wechsel der
Auswahl und nur, wenn er wirklich draussen liegt**: eine Bühne, die bei jedem
Neuzeichnen springt, nimmt einem die Stelle weg, die man gerade ansieht.

**Die Slot-Erkennung ist dieselbe wie im Konsolen-Editor** —
`detect_slots_in_image()` aus `editors/scan_services.py`. Der Konsolen-Editor
ruft sie über seinen deutschen Namen `erkenne_slots_im_bild()`, den auch
`repair` benutzt; das Studio nimmt den Dienst direkt. Modus `finden`: zwei Ecken um das Inventar, dann ein Klick auf einen
leeren Slot-Hintergrund, und alle liegen da; ein volles Inventar von Hand wären
90 Klicks. Zwei Erkennungen wären zwei Ergebnisse.

**Gesucht wird in einem Bereich, nicht im ganzen Bild.** Eine Farbe ist kein Ort:
liegt neben dem Inventar ein Menü in genau demselben Grau, wird es mitgefunden,
und heraus kommen zwanzig Slots, von denen acht keine sind — was erst beim
Erkennen auffällt, wenn man sie schon alle einzeln wegzuräumen hat. Der
`_suchbereich` schränkt deshalb die **Suche** ein, nicht das Bild: anders als
Modus `bereich` schneidet er nichts zu, gilt nur für diesen einen Durchgang und
ist danach weg (jeder Moduswechsel, ESC und jede neue Aufnahme räumen ihn ab).
Er wird gezeichnet, solange er steht — ein zu eng gezogener Bereich sähe sonst
aus wie ein zu weiter.

**Die Zelle wird um `scan_slot_inset` eingezogen** (`_mit_einzug()`) — dieselbe
Rechnung, die `slot_auto_detect()` im Konsolen-Editor seit jeher macht und die
hier fehlte: die Erkennung liefert die ganze Zelle samt Rahmen und Schatten, und
ohne Einzug lernt jedes Item den Rahmen als Merkmal mit. Abgezogen wird nie mehr,
als übrig bleiben darf. **Von Hand aufgezogene Slots bleiben unangetastet** —
dort ist das Rechteck genau das, was gemeint war.

Neu daran ist nur der Regler: `sv_toleranz` (Sättigung/Helligkeit) war fest auf
±50 verdrahtet, und **bei dunklen Oberflächen liegt der Panel-Hintergrund darin**
— dann verschmilzt alles zu einer Fläche und heraus kommt EIN Rechteck über dem
ganzen Inventar. Der Konsolen-Weg umgeht das, indem der Nutzer vorher eine enge
Region markiert; im Studio klickt man nur. `_slots_suchen()` probiert deshalb ein
enger werdendes Band und nimmt das Ergebnis mit den **meisten** Rechtecken —
gemessen an vier gestellten Panel-Farben lag der Umschlag bei 35, 25, 18 und 8,
also nicht bei einem Wert, den man fest eintragen könnte. Ein Rechteck über mehr
als der halben Fläche zählt nie mit: das ist das Panel, kein Slot.

**Vollbild ist die Voreinstellung, nicht die einzige Möglichkeit.** Wer dasselbe
Spiel mehrmals offen hat, arbeitet sonst auf einem Bild, in dem drei Viertel
stören. Der Aufnahmebereich lässt sich auf drei Wegen setzen — Fensterliste
(`winapi.liste_fenster()`), zwei Ecken im Bild (Modus `bereich`) oder direkt
(`scan_bereich_setzen`) — und der Rückweg ist ein Knopf.

Vier Eigenschaften, an denen das hängt:

- **Wählen und Aufnehmen sind zwei Dinge, also sind es zwei Klicks.**
  `scan_bereich_setzen()` setzt nur das Ziel und sagt, was als Nächstes kommt;
  das Bild holt der Knopf. Vorher nahm die Methode gleich mit auf, und das war
  die verwirrendste Stelle des Reiters: wer ein Fenster aus der Liste wählte,
  hatte plötzlich ein Bild, ohne etwas ausgelöst zu haben — und der Knopf
  „Fenster aufnehmen" daneben schien danach nichts mehr zu tun, weil er dasselbe
  Bild noch einmal holte. Ein Bedienelement, das von selbst handelt, und eines,
  das scheinbar nicht handelt, sind derselbe Fehler von zwei Seiten. Aus
  demselben Grund steht die **Uhrzeit** in der Aufnahme-Meldung: zwei Aufnahmen
  desselben Spielstands sehen gleich aus, und eine Wort für Wort gleiche Meldung
  lässt den Knopf kaputt wirken.
- **Der Bereich steht IM gemerkten Bild**, nicht in der Scan-Datei: Ursprung und
  Grösse des PNG *sind* der Bereich. Ein zweites Feld daneben wäre eine zweite
  Wahrheit, und beim nächsten Öffnen fragte sich, welche gilt. Deckt das Bild
  den ganzen virtuellen Desktop ab, ist es kein Bereich, sondern Vollbild —
  sonst stünde „Bereich" für etwas, das keine Einschränkung ist.
- **Zwei Ecken schneiden zu, sie nehmen nicht neu auf** — die Ausnahme zur ersten
  Regel, denn hier ist der Zuschnitt das Ergebnis und nicht die Vorbereitung.
  Zwischen den Klicks vergeht Zeit; was man zugeschnitten hat, soll man auch
  bekommen. Gemerkt wird der Bereich trotzdem — die *nächste* Aufnahme holt
  genau ihn.
- **Slots ausserhalb werden gezählt und gesagt** (`_draussen_hinweis()`). Ein zu
  eng gesetzter Bereich ist sonst still: die Slots stehen weiter in der Liste,
  sind aber nicht zu sehen, und man sucht den Fehler bei der Erkennung.

**Das Bild passt sich der Fenstergrösse an — aber nur, wenn niemand gezoomt
hat.** Die Bühne ändert ihre Grösse mit dem Fenster, das Bild tat es nicht: wer
klein aufnahm und dann gross zog, sah es in einer Ecke kleben, und ein Bereich
liess sich bei 31 % kaum noch treffen. `scanZoomHand` unterscheidet die beiden
Fälle: 1:1 und STRG+Rad sind eine Ansage und bleiben stehen, die Fenstergrösse
ist keine. Der Aufruf ist gebündelt (120 ms), sonst baut jedes Ziehen am
Fensterrand das Overlay ein Dutzend Mal neu.

**Den Bereich zieht man dort auf, wo er steht** — als Knopf in BILD, neben
Fensterliste und „Vollbild". Die Modus-Kachel gibt es weiterhin; beide schicken
denselben Befehl, es gibt also keinen zweiten Zustand. Als *nur* sechste Kachel
in der Modus-Liste war er da, wo niemand ihn sucht: die Kacheln beantworten
„was tut ein Klick gerade", nicht „wie schränke ich das Bild ein".

**Ein gewähltes Fenster wird DIREKT abgebildet — verdeckt oder nicht.**
`imaging.take_window_screenshot(hwnd)` über `PrintWindow` mit
`PW_RENDERFULLCONTENT`; ein Ausschnitt vom Desktop zeigt dagegen, was auf dem
Schirm zu sehen ist, also auch das Studio-Fenster davor. Genau deshalb kommt die
Fenster-**Kennung** aus `liste_fenster()` mit: über den Titel ginge es nicht, der
ist bei drei Fassungen desselben Spiels dreimal derselbe.

Vier Regeln dazu:

- **Nur für die Sitzung.** Ein Fenster-Handle überlebt keinen Neustart; ein
  gespeichertes zeigte beim nächsten Mal irgendwohin. Gemerkt wird im PNG
  weiterhin nur der Bereich.
- **Geliefert wird der Client-Bereich**, aus dem gerenderten Gesamtfenster
  geschnitten — `PrintWindow` malt Rahmen und Titelleiste mit, und die gehören
  nicht zum Spielfeld. Damit bleiben alle Koordinaten Bildschirm-Koordinaten,
  und alles Weitere rechnet wie bei einem Ausschnitt.
- **Ein schwarzes Bild ist kein Ergebnis.** Manche Vollbild-Spiele geben trotz
  des Flags eine leere Fläche zurück. `ist_leer()` erkennt das, und dann wird
  auf den Desktop-Ausschnitt zurückgefallen **und es gesagt** — sonst arbeiteten
  Slot-Suche und Farbmessung auf Nichts, ohne dass es jemand merkt.
- **Ein Zuschnitt von Hand löst die Bindung.** Wer im Fensterbild zwei Ecken
  aufzieht, will diesen Ausschnitt; die nächste Aufnahme holte sonst wieder das
  ganze Fenster.

**Die Fensterliste liefert den Client-Bereich, sortiert nach Lage.** Für
„dasselbe Programm dreimal offen" hilft `get_client_rect_by_title()` nicht: der
Titel ist dreimal derselbe. Unterscheidbar sind sie nur an der Position — die
steht deshalb in jeder Zeile, und die Liste ist danach sortiert (oben vor unten,
links vor rechts), also in der Reihenfolge, in der man sie auf dem Bildschirm
sucht.

**Wer in einem offenen Scan etwas anlegt, legt es FÜR ihn an** (`_dazu()`). Ohne
das war ein frisch aufgezogener Slot sofort wieder weg: die Listen zeigen
standardmässig nur die Mitglieder, und er war keines — man musste den Filter
ausschalten, ihn suchen und ein Häkchen setzen. Gilt für neue Slots, gedoppelte
und gelernte Items.

**Und gefunden ist gefunden, auch wenn der Slot schon existiert.** Bei zwei
Spielen liegen die Slots des einen längst im Bestand; ein **neuer** Scan über
demselben Inventar legte deshalb nichts an — nahm aber auch nichts auf, und weil
die Listen nur Mitglieder zeigen, blieb er leer: „45 Slot(s) gefunden, alle schon
da" und keine einzige Marke im Bild. Genau der Fall, in dem man den Fehler bei
der Erkennung sucht, obwohl sie funktioniert hat. `_slot_an_stelle()` gibt
deshalb den **Namen** zurück statt ja/nein, und der Durchgang zählt drei Sorten
getrennt: angelegt, aufgenommen, war schon dabei.

**Ein zweiter Suchlauf rät die Grösse nicht neu.** `erkenne_slots_im_bild()`
normalisiert auf den Median **eines** Durchgangs — ein zweiter Lauf über
demselben Raster bekommt seinen eigenen und weicht ein paar Pixel ab, obwohl die
Slots im Spiel gleich gross sind. Ein Fund innerhalb von `_GROESSE_TOLERANZ`
(6 px) übernimmt deshalb die Grösse, die schon feststeht
(`_bestehende_slot_groesse()`, zentriert über `_auf_groesse()`). Was
**deutlich** anders gross ist, bleibt, wie es gefunden wurde: das ist dann kein
Median-Versatz, sondern eine andere Fläche.

**Bezug ist der offene Scan, nie der ganze Bestand.** Zwei Bedienflächen
desselben Spiels sind nicht gleich gross — an einem echten Bestand gemessen hat
das Inventar-Raster 64 Hintergrund-Zeilen, die Ausrüstungsreihe 61. Genau diese
3 px fielen als „Template 62×60, Slot 62×57" auf, und sie sind **richtig**: die
Erkennung misst den sichtbaren Hintergrund, und der ist dort tatsächlich
flacher. Der Bestand als Bezug hätte die Reihe auf die Höhe des Rasters gezogen
und ein Template erzeugt, das drei Pixel Fremdes mitlernt. Ein leerer Scan gibt
deshalb gar keine Zielgrösse vor — und braucht auch keine: ein Slot, der schon
im Bestand liegt, wird übernommen statt neu angelegt.

**Was in Schirm-Pixeln rechnet, muss den Zoom aushalten.** Marken und Hinweise
werden gegen den Zoom gerechnet (`px = 1 / scanZoom`), damit sie in jeder
Vergrösserung gleich gross dastehen — die Slots dagegen stehen in Bild-Pixeln.
Bei einem vollen Inventar (45 Slots) passt das Bild nur klein ins Fenster, und
dann läuft beides auseinander:

- **Der Hinweis „kein Bild gemerkt" steht UNTER der Fläche**, nicht darin. Sein
  Abstand zählte in Schirm-Pixeln, der Rand der Ersatzfläche in Bild-Pixeln mal
  Zoom — bei 30 % sind 40 Bild-Pixel Rand noch zwölf Schirm-Pixel, und der Text
  sass mitten in der untersten Slot-Reihe.
- **Ein Name wird nur gezeichnet, wenn er in seinen Slot passt** (ab 34 px
  Slot-Breite auf dem Schirm). Sonst standen 45 Marken übereinander, aus denen
  keine mehr lesbar war. Der **gewählte** behält seinen immer: welcher es ist,
  ist die eine Frage, die auch bei 20 % beantwortet sein muss.
- Der gestrichelte Rand der Ersatzfläche ist ein `outline`, kein `border`: bei
  `box-sizing: border-box` frässe ein Rahmen zwei Pixel von der Breite, die das
  Overlay als Bezug nimmt.

**Boss- und Icon-Scans liegen im selben Reiter** (`scan_detect.py`), umgeschaltet
über SCAN-ART oben links (Items · Bosse · Icons). Sie waren vorher nur über die
Konsolen-Editoren erreichbar: linear durch Schritt 1–6, und für **jede** spätere
Änderung derselbe Ablauf noch einmal — auch für eine Konfidenz. Die Sache, um die
es geht, ist aber ein Rechteck auf einem Bild.

Der Aufbau ist derselbe wie beim Item-Scan, und das ist der Punkt: **der Assistent
ist der Weg beim ersten Einrichten, die rechte Spalte der Weg für jede spätere
Änderung.** Jedes Feld ist einzeln setzbar (`boss_setzen`, `icon_setzen`), keins
nur über einen Durchlauf erreichbar.

| | Item | Boss | Icon |
|---|---|---|---|
| Schritte | 3 (Bild, Slots, Items) | 5 (Bild, Region, Bosse, LLM/OCR, Fallback) | 4 (Bild, Region, Erkennung, Aktion) |
| Werkzeuge | Slot, Finden, Farbe, Klickpunkt, Bereich | Region, Klickpunkt | Region, Klickpunkt |
| gesucht wird | viele Dinge in vielen Flächen | ein Boss in **einer** Region | ein Symbol in **einer** Region |

Acht Regeln, an denen der Teil hängt:

- **Die Scan-Art ist Oberflächenzustand** (`scanArt` in `app.js`), wie `ansicht`
  und `scanListe`: sie steht nicht in der Momentaufnahme und nicht in der Brücke.
  Die Bühne (Aufnahme, Zoom, Scrollstand) bleibt beim Umschalten stehen — es ist
  dasselbe Bild, nur eine andere Frage daran. Wo ein Befehl trotzdem wissen muss,
  worauf er wirkt, **sagt der Aufruf es** (`{art: "boss"}`); nur solange ein
  Werkzeug scharf ist, merkt sich die Brücke das Ziel (`_region_ziel`) — und
  `_werkzeug_fertig()` räumt es mit weg.
- **Die Aufnahme ist EIN Schritt und gehört allen drei Arten.** Die Karte
  existiert genau einmal im Dokument und **wandert** in den Assistenten der
  offenen Art (`scanArtPflegen()`). Zwei Fassungen davon wären zwei Stellen, an
  denen eine Änderung an der Aufnahme vergessen werden kann — sie muss deshalb
  auch wieder zurückwandern, sonst fehlt dem Item-Assistenten sein erster Schritt.
- **Testen ist folgenlos.** `boss_testen`/`icon_testen` erkennen, zeigen und
  *benennen* die Aktion — ausgeführt wird sie nie, und das steht in der
  Testleiste dabei. Ein Testknopf, der im Editor eines Autoclickers wirklich
  klickt, ist die schlechteste denkbare Überraschung. Ein Test misst es.
- **Gerechnet wird mit `_check_profile_match()`** aus `runtime/item_scan.py` —
  derselben Funktion, die im Lauf entscheidet, mit `_NurConfig` als
  `state`-Stellvertreter. Eine zweite Rechnung „nur für die Vorschau" wäre eine
  Vorschau, die etwas anderes zeigt als das, was passiert.
- **Der Vorschlag ist der Kern des Fehlerfalls.** Findet ein Icon-Scan zu wenige
  Marker, nennt die Testleiste die kleinste Toleranz, bei der es klappt
  (`_toleranz_vorschlag()`) — ein Klick. Ein Test, der nur „fehlgeschlagen" sagt,
  lässt einen genau dort stehen, wo man vorher war.
- **Die Aktionswerte kommen aus `models.py`**, über die Momentaufnahme
  (`aktionen.boss` / `aktionen.icon` / `aktionen.scan_modi`). Die Ansicht erfindet
  keine Namen: ein getipptes `"skipcycle"` wäre ein Wert, den `__post_init__`
  beim Speichern still auf den Standard hebt — der Klick sähe aus, als hätte er
  gewirkt. Ein Test hält die Listen gegen `VALID_*_ACTIONS`.
- **Die Bibliothek gilt zusätzlich in JEDEM Boss-Scan**, lokale Bosse gewinnen bei
  Namensgleichheit (so merged auch `execute_boss_scan`). Deshalb testet
  „alle testen" die **gemergte** Liste, deshalb kollidiert ein neuer Boss-Name
  gegen beide Mengen, und deshalb steht ein verdeckter globaler Boss blass in der
  Liste statt so zu tun, als würde er benutzt. Angezeigt wird sie als Kartenraster
  an der Stelle der Bühne — sie ist kein Rechteck auf dem Bild, sondern eine
  Sammlung.
- **Das ELSE gehört dem Block, nicht dem Scan.** `IconScanConfig` hat kein
  else-Feld, und eins einzuführen hiesse, dieselbe Sache an zwei Stellen zu haben:
  der Sequenz-Editor setzt sie am Block, wo sie für alle drei Scan-Arten an
  derselben Stelle steht. Die rechte Spalte sagt genau das und nennt den
  Konsolen-Befehl (`icon <Name> else skip`).

**Speichern und Rückgängig umfassen alle drei Arten.** Ein Knopf schreibt Slots,
Items, Item-Scans, Boss-Scans, Icon-Scans, die Bibliothek **und `points.json`** —
ein Klickpunkt einer Boss- oder Icon-Aktion ist ein Punkt, und die Koordinate steht
dort und sonst nirgends. Der Rückgängig-Abzug (`_erkennung_zustand()`) nimmt sie
ebenso mit: ein Zurück, das die Slots zurückdreht und den Boss-Scan stehen lässt,
wäre ein halbes Zurück, und das ist schlimmer als gar keins.

**Der Konsolen-Editor bleibt** (`CTRL+ALT+N`). Er schreibt dieselben Dateien —
deshalb zählen `boss_scans/`, `icon_scans/` und `boss_scans/global/bosses.json`
seit dem Umbau beim „auf Platte hat sich etwas geändert"-Vergleich mit
(`_erkennung_pfade()`). Ohne sie meldete der Hinweis ausgerechnet das nicht, woran
man gerade arbeitet: ein Lauf legt per LLM entdeckte Bosse in der Bibliothek ab.

**Was fehlt:** der Boss-Watcher hat keine eigene Ansicht (er benutzt denselben
Scan, nur ein anderer Block-Typ), und OCR/LLM lassen sich hier ein- und
ausschalten, aber nicht *ausprobieren* — der Testknopf misst Template und Marker.
Für das LLM gibt es nur die Erreichbarkeitslampe (`llm_pruefen`); ein echter
Probelauf kostet bis `llm_timeout` und hat im Zeichnen einer Momentaufnahme
nichts verloren.

**Der Reiter „Teilen" arbeitet auf dem GESPEICHERTEN Stand** (`bridge_teilen.py`).
Export und Import bauen sich dafür einen frischen `AutoClickerState` aus den
Dateien — der Studio-Prozess kennt sonst nur, was seine Reiter geöffnet haben.
Vier Regeln:

- **Gezählt wird, was auf Platte liegt.** Ungespeichertes im Fenster kommt nicht
  ins Bündel, und der Reiter sagt das, statt es zu verschweigen.
- **Die Referenzpunkte kommen aus dem Spielfenster** (`window_focus_title`). Ist
  es offen, rechnet der Empfänger automatisch um; sonst stehen die Ecken des
  virtuellen Desktops im Manifest und er setzt zwei Punkte von Hand
  (`CTRL+ALT+I`). Das Fenster sieht den Bildschirm nicht — zwei Punkte
  anzuklicken kann es nicht anbieten.
- **Eine Kachel, die nichts tut, gibt es nicht.** Ohne beidseitig bekanntes
  Fenster bietet der Import nur „1:1 übernehmen" an.
- **Die Config wird hineingeschrieben, nicht getauscht** (`uebernehmen()`): auch
  im Subprozess gibt es ein Config-Objekt.

Nach dem Import lesen beide Seiten neu — der Reiter selbst und, über den
Briefkasten-Befehl `daten`, der Hauptprozess.

**Der Reiter „Werkzeuge" holt nach, was nur die Konsole konnte** (`bridge_werkzeuge.py`).
Prüfen (`check`), kalibrieren (`fix`) und die Klick-Runde (`klick`) lagen im
Punkte-Menü — also ausgerechnet die Handgriffe, die man nach einem Bildschirm-Umbau
braucht, und die man dann in einem Fenster sucht, das schon offen ist.

**Zwei davon laufen HIER, eines drüben — und die Grenze ist nicht der Bildschirm.**
Der Studio-Prozess sieht `AutoClickerState` nicht, aber sehr wohl das
Betriebssystem: der Scans-Reiter nimmt Screenshots auf, `punkt_aufnehmen()` liest
die Mausposition über eine globale Taste. Genau diese zwei Griffe braucht eine
Kalibrierung, also läuft sie im Fenster. Die Klick-Runde braucht dagegen einen
**systemweiten Maus-Hook**, und der gehört dem Prozess, der auch die Hotkeys pumpt
— sonst gingen `CTRL+ALT+K`/`U`/`H`/`J` ins Leere. Nur dafür gibt es den
Briefkasten-Befehl `nachklick`.

Vier Regeln, an denen der Reiter hängt:

- **Gerechnet wird mit denselben Funktionen wie in der Konsole**
  (`import_export.kalibriere_bestand`, `diagnose.pruefe_setup`), auf einem frischen
  State von Platte (`_bestand()`). Eine zweite Rechnung „fürs Fenster" wäre eine,
  die etwas anderes tut als der Weg, den die README beschreibt — und ein Bericht
  über das, was die Reiter zufällig offen haben, meldete „sauber", weil er die
  halben Daten gar nicht kennt.
- **Die Vorschau ist der Grund, warum es im Fenster besser ist.** In der Konsole
  scrollt die Liste weg, hier steht sie neben dem Knopf. Dafür musste
  `collect_click_positions()` erst aufhören, doppelt zu zählen: Sequenz-Schritte
  mit `point_id` haben keine eigene Stelle mehr (`_remap_sequence_obj` lässt sie
  in Ruhe), standen aber neben ihrem Punkt in der Liste — jede Änderung erschien
  zweimal, und die zweite Zeile versprach eine Umrechnung, die nicht stattfindet.
- **Geschrieben wird erst beim Anwenden.** Referenzpunkte, Versatz und Vorschau
  leben in `self._kalib` und sind nach `kalib_abbrechen()` spurlos weg. Davor
  entsteht ein vollständiges Export-ZIP (`sichere_vor_kalibrierung`), und ein
  laufender Lauf blockiert — er klickt sonst mitten im Umbau auf halb verschobene
  Stellen.
- **`mit_slots` ist AUS.** Eine aus einer Mausposition abgeleitete Verschiebung ist
  für ein Klickziel gut genug, für eine Scan-Region nur eine Näherung. Dafür gibt
  es `repair` im Konsolen-Slot-Editor, das die Slots **misst** — und nach einer
  Reparatur dürfen sie kein zweites Mal wandern. Der Reiter sagt das dazu, statt
  den Weg zu verschweigen.

Danach lesen beide Seiten neu: der Reiter seine Punkte, der Hauptprozess über den
Briefkasten-Befehl `daten` — der zieht seit dieser Umstellung auch `points.json`
nach, denn bei einer Kalibrierung wandert **jede** gespeicherte Stelle.

**Die Einstellungen bearbeiten eine andere Datei als der Rest des Fensters.** Das ist
der ganze Grund, warum die Sequenz-Bedienelemente im Kopf dort verschwinden: zwei
Speichern-Knöpfe für zwei Dateien in einer Leiste sind eine Falle. Gespeichert wird
auf Knopfdruck und nicht bei jedem Tastendruck — die Werte greifen in einen laufenden
Lauf, und eine halb getippte Zahl darf nicht schon gelten.

**Das Schema liegt in `config_meta.py`, nicht im HTML.** `AppConfig` kennt Name, Typ
und Standardwert, `_CONFIG_SECTIONS` kennt Gruppe und Reihenfolge; was fehlt, ist
Beschriftung, Erklärung, Art des Bedienelements und Abhängigkeit. Stünde das in der
Ansicht, fiele ein neues Config-Feld erst auf, wenn jemand es sucht — so hält ein
Test die Tabelle gegen die Dataclass (`jedes Config-Feld hat eine Beschreibung`),
in **beide** Richtungen. Zwei weitere Tests messen, was man sonst erst beim Benutzen
merkt: jede angebotene Enum-Kachel muss `__post_init__` überleben (sonst klickt man
einen Wert an, der beim Speichern still verworfen wird), und jede `dep`-Angabe muss
auf ein existierendes Feld zeigen (sonst ist ein Feld dauerhaft blass, ohne Grund).

**Geschickt werden nur die geänderten Schlüssel**, gemischt gegen die Datei, wie sie
JETZT aussieht. Der Hauptprozess schreibt dieselbe Datei (Debug-Stufen, Import,
Factory Reset) — ein Fenster, das seit einer Stunde offensteht, darf dessen Änderungen
nicht mit seinem alten Stand überbügeln. Eine **unlesbare** `config.json` wird nicht
überschrieben, sondern gemeldet: kaputt ist nicht leer.

**Korrekturen werden zurückgemeldet, nicht verschluckt.** `AppConfig.__post_init__`
hebt ungültige Werte auf den Standard (Konfidenz über 1, max unter min, unbekannte
Aktion) und schreibt dazu eine Konsolenzeile — die sieht im Studio niemand. Deshalb
vergleicht `config_schreiben()` den geschriebenen Stand mit dem Gesendeten und gibt
die Abweichungen zurück; sie stehen rechts, bis der nächste Wert angefasst wird. Der
Vergleich zieht Zahlen normalisiert (`_gleicher_wert`: `600` und `600.0` sind dieselbe
Einstellung), lässt `bool` aber ausgenommen — dieselbe Rechnung wie `_gleich()` im
Start-Durchgang.

**Es gibt EIN Config-Objekt pro Prozess.** `state.config` **ist** das Modul-`CONFIG`
(gesetzt in `main.py`), und wer die Werte ändert, schreibt mit `config.uebernehmen()`
hinein, statt das Objekt auszutauschen. Vorher war `state.config` eine Kopie — womit
jedes Modul mit `from .config import CONFIG` (`imaging`, mehrere Item-Editoren)
dauerhaft die Werte vom Programmstart las. Ein Test prüft die Quelle: eine Zuweisung
an `.config` ausserhalb von `main.py` ist ein Fehler.

Damit die Datei auch im Speicher ankommt, gibt es den Briefkasten-Befehl `config`:
das Studio legt ihn nach dem Schreiben ab, `befehl_config()` lädt `config.json` neu
und schreibt sie in dasselbe Objekt. Ein laufender Lauf zieht sofort mit — der Worker
liest `state.config` bei jedem Schritt neu.

Regeln für die Ansicht:

- **Abhängige Felder werden blass, nicht unsichtbar.** Dass unter `llm_enabled`
  dreizehn Felder hängen, ist die halbe Information; ausgeblendete sucht man in der
  Datei. Sie sagen auch, woran sie hängen.
- **Der Schlüssel steht mit** (`scan_slot_hsv_tolerance` unter der Beschriftung). Er
  kommt in Logs, README und der Datei vor — wer das Feld hier sieht, soll es dort
  wiedererkennen.
- **Was leer bzw. 0 bedeutet, steht am Wert**, nicht in der Erklärung: eine 0 liest
  sich wie „aus", und bei `click_max_total` heisst sie das Gegenteil. Leer heisst
  `null`, wo die Dataclass das erlaubt (`optionale_felder()`), sonst 0.
- **Enums als Kacheln, alles Wachsende als Liste** — dieselbe Regel wie beim
  Block-Typ. Die Auswahl ist im Code festgelegt und kurz.
- **Die Suche zeigt alle Abschnitte mit Treffern**, nicht nur den gewählten: wer
  sucht, weiss ja gerade nicht, wo der Wert steht.
- **Eine Stelle fährt man an** (`scan_park_mouse`): Maus hin, ENTER — derselbe Weg
  wie beim Klick-Block, nur ohne Punkt anzulegen. Eine Parkposition gehört nicht in
  `points.json`.

**Start, Pause und Stopp gehen über einen Briefkasten** (`befehl.py`), nicht direkt:
dieser Subprozess hat keinen Zugriff auf `state.stop_event`. Er legt eine Datei ab,
und der Hauptprozess holt sie **im Main-Thread, in derselben Schleife, in der auch
seine Hotkeys ankommen** (`_pruefe_befehle` in `main.py`, alle 250 ms im Leerlauf).
Damit ist ein Studio-Knopf exakt so viel wert wie ein Tastendruck: dieselbe
Reihenfolge, dieselben Sperren, kein zweiter nebenläufiger Pfad. Ein Watcher-Thread
hätte genau den gebracht — für eine Datei, die niemand eilig braucht.

Die Regeln des Briefkastens stehen im Modul-Docstring; eine ist wichtiger als die
anderen: **ein Befehl darf nie nachfeuern.** Wer im Studio auf „Starten" drückt,
während gar kein Hauptprozess läuft, bekommt keine Wirkung — und darf sie auch nicht
bekommen, sobald einer startet. Dafür sorgen `MAX_ALTER` und das Leeren beim Start.

Über denselben Weg läuft **„Stelle zeigen"**: der Knopf unter einem Klick-Block
setzt die Maus im Hauptprozess auf dessen Punkt. Das Fenster kann das nicht selbst
— es sieht den Bildschirm nicht —, und genau deshalb steht auch die Auswertung
dort: der Hauptprozess misst die Farbe an der Stelle und vergleicht sie mit der
gespeicherten. Ein Studio, das „passt" behauptet, ohne gemessen zu haben, wäre
schlimmer als der Blick ins andere Fenster.

Zwei Dinge bleiben trotzdem beim Hauptprozess: die **Sequenz kommt von Platte**
(`befehl_start` lädt die mitgeschickte Datei; das Studio speichert vorher, sonst liefe
etwas anderes als das Angezeigte), und **`handle_toggle()` wird nicht für „stopp"
benutzt** — es ist ein Umschalter und würde starten, wenn gerade nichts läuft.

**Die Phasen stehen alle nebeneinander**, die laufende breit (`_phasen_uebersicht()`
im Worker, Feld `phasen`). Sie aus der geöffneten Sequenz zu holen wäre geraten —
laufen kann eine ganz andere —, deshalb schreibt der Worker sie einmal beim Start
mit. Dazu die Position der laufenden (`phase_pos`): `phase_index` (−1 für INIT/END)
reicht der Ansicht nicht, sie kennt nur diese eine Liste. Die Rechnung steht in
`_phase_pos()` und nicht dreimal an den Schreibstellen — ein Versatz, der an einer
davon fehlt, markiert die falsche Kachel als laufend.

Die Leiste ist ein **Raster, keine Reihe**: acht Loop-Phasen sind zehn Kacheln, und
nebeneinander wäre jede 140 px breit — Name abgeschnitten, Fortschritt unlesbar. Sie
bricht deshalb um (`auto-fit`, damit sich wenige Kacheln trotzdem über die Breite
dehnen), die laufende belegt drei Spalten. Aus demselben Grund bricht auch die
Kopfleiste um: bei 900 px Fensterbreite stand „Speichern" halb ausserhalb, und ein
Knopf, den man nicht erreicht, ist schlimmer als eine zweite Zeile.

„Abgeschlossen" gilt dabei **innerhalb des Zyklus**: im nächsten Durchgang sind
dieselben Loop-Phasen wieder ausstehend. Und eine zeitgesteuerte Phase sagt, worauf
sie wartet („wartet auf 07:00") — sie wartet nicht auf ihren Vorgänger, sondern auf
die Uhr.

**Der laufende Block trägt seine Typfarbe** — dieselbe, die seine Karte im Board
hat. Die Farbe ist die Legende; stünde sie nur im Editor, müsste man beim Blick in
den Live-Run raten, welcher der neun Typen gerade läuft. Damit das geht, liegen die
`BLOCK_*`-Schlüssel und `block_type()` in **`models.py`**: die Laufzeit schreibt den
Schlüssel in den Laufstatus (`block_typ`), die Brücke übersetzt ihn in Farbe und
Marke. `runtime/` darf die Ansicht nicht importieren, und zwei Kopien der
Klassifikation wären zwei Stellen, an denen ein neuer Block-Typ vergessen wird —
`BLOCK_LABELS`/`BLOCK_COLORS` bleiben bei der Ansicht, das ist Anzeige.

**Beim aktuellen Block steht, worauf er wartet** (`status.wartet()`, Feld `warten`).
„seit 12 s" allein beantwortet die Frage nicht: bei einer Wartezeit von 15 s sind
zwölf Sekunden fast geschafft, bei einem Farb-Trigger mit 300 s Timeout haben sie
gerade erst angefangen. Der Kasten zeigt deshalb Restzeit bzw. Timeout-Countdown,
und beim Farb-Trigger zusätzlich Soll gegen gemessenes Ist, den Abstand samt
Toleranz und **was nach dem Timeout passiert** (`_timeout_folge()` — dieselbe Kette
wie `_handle_color_wait_timeout`).

Drei Eigenschaften, an denen das hängt:

- **Der Live-Ausschnitt beantwortet die Anschlussfrage.** „RGB(30, 32, 34)" sagt
  nicht, WAS an der Stelle zu sehen ist — ein 49×49-Ausschnitt tut es (grauer
  Knopf, Ladebildschirm, Popup davor). Die Laufzeit nimmt ihn höchstens einmal pro
  Sekunde auf (`_LIVE_ABSTAND`) und schreibt ihn als Data-URL mit; das sind rund
  3 KB in einer Datei, die sonst 400 Byte hat. Ohne Pillow gibt es kein Bild und
  entsprechend keinen leeren Rahmen.
- **Zeiten stehen absolut in der Datei** (`seit`, `bis`), nicht als Restwerte. Der
  Worker tickt im Sekundentakt, die Ansicht fragt alle 500 ms — mit Restwerten
  ruckelte der Countdown im Raster des Workers. Beide Prozesse laufen auf derselben
  Maschine, also auf derselben Uhr.
- **Jede Warteschleife meldet sich selbst wieder ab**, in einem `finally` und
  ungedrosselt. Deshalb liegen die Schleifenrümpfe in eigenen Funktionen
  (`_warte_schleife`, `_farb_schleife`) — sonst stünde nach „Farbe erkannt" noch
  „wartet auf Farbe" da, während der Klick längst raus ist. Der Blockwechsel räumt
  zusätzlich ab (`"warten": None` in `execute_step`).
- **`wartet()` ersetzt das Lebenszeichen**, es kommt nicht dazu: es schreibt über
  dieselbe Funktion und schiebt `stand` genauso vor.

**Am Ende bleibt die Zusammenfassung stehen.** Hier wurde die Statusdatei
früher gelöscht, und damit war die Live-Ansicht genau in dem Moment leer, in dem
man sie ansieht: direkt nachdem etwas fertig geworden ist. `beende()` schreibt
jetzt einen **abgeschlossenen** Lauf (`aktiv: False` plus `ende`, Grund, Dauer,
gelaufene Zyklen, Zähler), bis der nächste Start ihn überschreibt. Drei Fälle
unterscheidet der Leser am Inhalt, nicht am Vorhandensein der Datei:

| Datei | bedeutet |
|---|---|
| `aktiv: True`, `stand` frisch | läuft |
| `aktiv: True`, `stand` älter als 5 s | abgestürzt (verwaist) |
| `aktiv: False` mit `ende` | fertig, Zusammenfassung |

Die Altersregel gilt **nur für den ersten Fall** — eine Zusammenfassung ist
Vergangenheit und darf alt sein. Was einen *Moment* beschreibt (Block, Warten),
fällt dabei weg; wo Schluss war (`phase_pos`), bleibt: das ist die zweite Frage
nach „warum". Ohne `state` — ein Lauf, der gar nicht erst anlief — wird
weiterhin gelöscht, denn eine Zusammenfassung ohne Zahlen wäre keine.

**In die Live-Ansicht wird nur auf der Flanke gesprungen** (nichts → läuft). Solange
etwas läuft, bleibt die gewählte Ansicht stehen; sonst käme man während eines
Durchgangs nicht mehr in den Editor zurück.

**Zwei Prozesse, ein Ordner — und der Zweite gewinnt nicht mehr kommentarlos.**
Das Studio merkt sich beim Laden den Zeitstempel von Sequenzdatei und
`points.json` (`_stand_merken()`); hat sie sich beim Speichern geändert, fragt es
nach, statt zu überschreiben. Der Fall ist Alltag: eine Aufnahme im Hauptprozess
legt Punkte an, `save_data()` schreibt die Sequenz. Die Rückfrage ist derselbe
Dialog wie bei ungespeicherten Änderungen — er trägt Titel, Text und
Knopfbeschriftung jetzt aus der Brücke, weil sich die Fälle zu sehr
unterscheiden (bei „ausserhalb geändert" gibt es nichts zu verwerfen).

**Das eigene Symbol braucht zwei Dinge, nicht eins.** Titelleiste und ALT+TAB
nehmen es aus `WM_SETICON` (`setze_fenster_symbol()`) — aber erst, wenn es das
Fenster gibt: `webview.start(func)` ruft seinen Callback davor auf, deshalb die
Frist (`warten=`). Die **Taskleiste** ignoriert das Fenstersymbol, solange sie
das Fenster unter der ausführenden Datei einsortiert, und die heisst `python.exe`;
dafür gibt es `setze_app_id()`, und die muss **vor dem ersten Fenster** laufen.
Zwei Mechanismen, zwei Aufrufe, zwei Tests — wer nur einen setzt, sieht das
Ergebnis an genau einer der beiden Stellen.

Gezeichnet wird das Symbol **aus Geometrie, nicht aus einem getippten Raster**
und nicht aus einer Binärdatei im Repo: `autoclicker/symbol.py` beschreibt das
Motiv als Liste von Formen (`rr` / `kreis` / `strich` / `zug`, alle im 24er-Raster
des SVG-viewBox) und rechnet daraus jede Grösse — gerundete Ecken über den
Alpha-Kanal, Kantenglättung über `PROBEN`² Abtastungen je Pixel. Das vorherige
16×16-Raster aus Nullen und Einsen hatte alle Fehler eines handgesetzten Rasters
(Motiv bis an die Kante, scharfe Ecken, Treppen).

**Eine Geometrie, drei Verwendungen** — und deshalb liegt sie nicht in
`winapi.py`, sondern in einem Modul, das weder Windows noch Pillow kennt:

| wer | wozu |
|---|---|
| `winapi._symbol_bits()` | ICO-Bits für `WM_SETICON` (16 und 32) |
| `tools/symbol.py` | PNG-Dateien und eine `.ico` für Verknüpfungen |
| `web/index.html` | das SVG im Kopf der Oberfläche |

Das SVG ist die einzige der drei, die von Hand nachgezogen wird — ein Test hält
es **Zahl für Zahl** gegen `MOTIV_KLEIN` (nicht „kommt vor": ein verschobener
Balken fiele sonst nicht auf).

**Zwei Fassungen, nicht eine skalierte.** `MOTIV` ist das volle Motiv,
`MOTIV_KLEIN` hat weniger Teile, dickere Striche und eine *gefüllte* statt
umrandete Fahne. Der Grund ist gemessen: die Fahne der grossen Fassung hat 0,6
Einheiten Strichstärke — bei 16 px sind das vier Zehntel Pixel, also ein grauer
Fleck, und die Punktkette ist Krümel. `KLEIN_BIS = 32` liegt genau dort, wo
Windows aufhört zu fragen: Titelleiste (16) und ALT+TAB/Taskleiste (32) bekommen
die kleine, die grosse fängt bei der Verknüpfungsgrösse an.

**Die Bilddateien werden geschrieben, nicht eingecheckt.** `python tools/symbol.py`
legt PNGs und eine `.ico` an (ohne Pillow — beide Formate sind von Hand
zusammensetzbar, wenn man sich auf unkomprimierte Zeilen bzw. eingebettete PNGs
beschränkt). Eine Binärdatei im Repo wäre eine Kopie des Motivs, die niemand
mitzieht — dasselbe Argument wie bei „Referenzen statt Kopien".

**Wer eine Sequenz von Platte lädt, holt die Punkte mit** (`punkte_nachladen()`
in `persistence/sequences.py`). Das Studio schreibt beim Speichern *beide*
Dateien; der Hauptprozess nahm die Sequenz von Platte und die Punkte aus seinem
Speicher — ein dort angelegter Punkt fehlte deshalb genau dann, wenn man ihn
braucht („[Punkt #51 FEHLT]", Schritt übersprungen). Zwei Hälften aus zwei
Zeitpunkten. Betroffen sind alle drei Wege: `befehl_start` (Studio-Knopf),
`handle_switch` und `run_sequence_loader` (CTRL+ALT+L, der Weg, auf den die
Schlussmeldung des Studios selbst verweist); ein Test hält sie zusammen.
Zusammengeführt wird über die ID, **Platte gewinnt**, und gelöscht wird nichts —
Boss- und Icon-Editor legen Punkte an, ohne sofort zu speichern.

**Eine Stelle fährt man an, statt sie zu tippen** (`punkt_aufnehmen()`): Maus hin,
ENTER — derselbe Weg wie `bereich_aufnehmen()` für Screenshot-Bereiche, nur mit
einer Ecke. Die Farbe wird dabei gleich mitgemessen, denn der Bildschirm zeigt in
diesem Moment genau das Richtige. Gesetzt wird über `punkt_setzen`/`punkt_anlegen`,
damit die Regeln gelten, die überall gelten (vorhandener Punkt an derselben Stelle
wird wiederverwendet).

Regeln beim Erweitern:

- **Neue Bedienelemente kommen als Methode in das zuständige Bridge-Mixin**, nicht
  als Logik ins JavaScript: Darstellung in `bridge_view.py`, Datei/Lauf/Config in
  `bridge_services.py`, Editor-Kommandos in `bridge_editing.py`. Die Methode
  bleibt über `StudioBridge` öffentlich. Nur so bleibt sie messbar; die Oberfläche
  ist der ungetestete Teil und soll klein bleiben.
- **Sammel-Aktionen arbeiten auf der Auswahl, nicht auf einem Block.**
  Verschieben, Löschen und Duplizieren nehmen alle gewählten Zeilen; beim
  Duplizieren landen die Kopien **hinter der letzten** Gewählten und werden zur
  neuen Auswahl. Jede Kopie einzeln hinter ihr Original zu setzen zerrisse eine
  Mehrfachauswahl in abwechselnd Original/Kopie. Kopiert wird tief
  (`copy.deepcopy`) und **auf denselben Punkt** — ein Duplikat ist erst mal
  derselbe Klick, und ein zweiter Punkt an derselben Stelle wäre die Doppelung,
  die `punkt_fuer_stelle()` überall sonst vermeidet.
- **Die Auswahl lebt in genau einer Phase** (`sel_lane` + `sel_rows`). Eine Auswahl
  quer über INIT und END hätte bei „eine Position hoch" keine Bedeutung, und die
  Sammelaktionen wären nicht mehr eindeutig.
- **Die Karte zeigt wenig, der Inspektor alles.** Auf die Karte gehört, was man beim
  Überfliegen von 50 Blöcken braucht (Typ, Ziel, Wartezeit, Trigger, ELSE, Warnung);
  alles Weitere steht rechts. Eine Wartezeit von 0 kommt gar nicht erst auf die Karte —
  „sofort" unter jedem zweiten Block ist Rauschen.
- **Diskrete Bedienelemente melden sofort, Tipp-Felder erst beim Verlassen** (`change`,
  nicht `input`). Jede Meldung baut die Ansicht neu, und ein Neuaufbau mitten in der
  Eingabe nimmt das Feld weg, in das gerade getippt wird. Dieselbe Regel galt schon in
  der DPG-Fassung. Folge davon: `STRG+S` muss vorher `blur()` auslösen, sonst geht der
  zuletzt getippte Wert verloren.

  **Und jeder Neuaufbau rettet den Fokus hinüber** (`fokusMerken()` /
  `fokusHerstellen()`). Weil Tipp-Felder beim *Verlassen* melden, ist es genau der
  TAB-Sprung, der den Neuaufbau auslöst — bis die Brücke antwortet, steht der
  Fokus schon im nächsten Feld, und `replaceChildren()` wirft es weg. Sichtbar
  wurde das beim Item: Namen tippen, TAB nach Kategorie, Cursor weg, nochmal
  klicken. Gemerkt wird die **Position** unter den Eingabefeldern des nächsten
  Elements mit `id`, nicht das Element selbst (das gibt es danach nicht mehr) und
  auch kein eigener Schlüssel je Feld — den müsste jeder Feld-Bauer mitschleppen,
  und ein vergessener fiele nicht auf. Ein Test hält fest, dass **alle drei**
  Neuaufbauten (`zeichne`, `zeichneScans`, `zeichneEinstellungen`) es tun.
- **Ein Trigger ohne Punkt wird abgelehnt**, statt eine Bedingung auf (0, 0) anzulegen —
  dieselbe Haltung wie „es gibt bewusst keinen Rückfallwert" bei `point_id`. Das gilt
  auch für den *Typwechsel*: **`set_block_type()` legt die Bedingung selbst am Punkt an**
  (`WaitCondition(point_id=step.point_id)`) und ohne Punkt gar nicht; `block_typ()` lehnt
  FARBE+KLICK ohne Punkt ab und begründet es.

  Vorher entstand die Bedingung dort auf den rohen `step.x/y` samt
  `recorded_color`, und die Brücke bog sie **hinterher** auf den Punkt um. Das war
  eine Reparatur, keine Regel: wer `set_block_type()` direkt aufruft — oder die
  Reparatur beim nächsten Umbau vergisst — bekam wieder `wait_pixel`/`wait_color`
  in der Datei, also eine Koordinaten-Kopie ausserhalb von `points.json`, die
  keine Kalibrierung je einholt. Ein Test misst deshalb die **Funktion**, nicht
  nur den Weg über die Brücke.
- **Der Typ ist das Ergebnis zweier Eigenschaften, nicht umgekehrt.** KLICK,
  FARBE+KLICK und WARTEN unterscheiden sich in genau zwei Fragen: klickt der Schritt,
  wartet er auf eine Farbe. Der Abschnitt AKTION zeigt beide als Schalter und schreibt
  darunter, was dabei herauskommt; die Kacheln bleiben als Abkürzung für den, der die
  Typen kennt. Zwei Bedienelemente für einen Zustand sind hier **bewusst** in Ordnung,
  weil beide über dieselben Befehle schreiben (`block_typ`, `block_trigger`) — es gibt
  keinen zweiten Zustand, der auseinanderlaufen könnte.

  Der gelöschte Schalter „nur warten (kein Klick)" war der Gegenfall: **einer** statt
  zweier, er setzte `wait_only` (also dasselbe wie die Kachel WARTEN), und er blendete
  sich bei „warten" selbst aus. Wer ihn eingeschaltet hatte, fand nichts mehr, um ihn
  auszuschalten. Genau diese Falltür darf es hier nicht geben — und deshalb bleibt auch
  ein Farb-Trigger sichtbar, der an einem Typ hängt, der ihn gar nicht auswertet.
- **Ein Bedienelement steht nur da, wo die Laufzeit es auswertet.** Den Farb-Trigger
  gibt es bei Klick, Warten und **Taste**: `runtime/steps.py` wartet für die drei an
  genau einer Stelle, und dass die Taste dazugehört, war einmal ein Fehler und ist
  ausdrücklich repariert. Scans und Screenshot kehren vorher um — dort fehlt der
  Abschnitt. Die **Nachprüfung** bleibt dagegen bei jedem Typ: „hat die Aktion
  gewirkt?" ergibt auch bei einer Taste und einem Scan Sinn.
- **Was aktiv oder gewählt ist, wird ringsum markiert** — nie nur an einer Kante.
  Ein Streifen links liest sich als Verzierung, ein Ring als Zustand; und im
  Board, wo die Phasen nebeneinander stehen, scheint ein linker Streifen an der
  falschen Spalte zu kleben. Umgesetzt über `box-shadow: 0 0 0 1px <farbe>` und
  nicht über einen dickeren Rahmen: der liesse das Element um einen Pixel
  wachsen und verschöbe bei jedem Wechsel das ganze Raster. Betrifft die
  gewählte Karte, die Phasenköpfe im Board, die laufende Phase im Live-Run und
  die Typ-Kacheln im Inspektor. Bei den Kacheln ist die Farbe **Legende** statt
  Zustand — sie tragen sie deshalb alle, und nur die gewählte ist zusätzlich
  ausgefüllt.
- **Alle Typ-Kacheln tragen ihre Farbe**, nicht nur die gewählte — damit ist das
  Raster zugleich die Legende zu den Farben im Board. Ringsum als Rahmen (dieselbe
  Regel wie oben), die gewählte zusätzlich ausgefüllt. `border-color` steht im
  `style`-Attribut und damit *nach* dem `border`-Kurzformat aus `.typ-chip`;
  andersherum räumte die Kurzform die Farbe wieder weg.
- **Was ohne ELSE passiert, steht in der Config — also wird sie gelesen, nicht
  behauptet.** Im Inspektor stand „Ohne ELSE läuft der Schritt in seinen Timeout
  und die Sequenz macht weiter", und das war falsch: die Voreinstellung
  `pixel_timeout_action: "skip_cycle"` bricht den **ganzen Zyklus** ab. Genau
  dieser Unterschied entscheidet, ob man ELSE braucht. `_ohne_else()` liest
  deshalb `pixel_wait_timeout`, `pixel_timeout_action` und die Notbremse aus
  `config.json` und schreibt sie in die Momentaufnahme; scheitert das Lesen,
  sagt die Oberfläche nichts, statt zu raten. Die Übersetzung Wert→Text steht in
  `models.TIMEOUT_TEXT`, damit Editor und Laufzeit dieselbe Folge nennen — ein
  Test hält beide gegeneinander.
- **Der Aus-Zustand bekommt keine eigene Kachel, sondern einen Rückweg.** Bei ELSE
  stand „(keine)" als sechste Kachel im Raster und sah aus wie eine weitere
  Aktion, obwohl sie deren Abwesenheit ist. Jetzt ist bei „kein ELSE" schlicht
  keine Kachel markiert, und der Rückweg ist die markierte Kachel selbst: ein
  zweiter Klick darauf hebt sie auf. Fehlen darf er nicht — das wäre die Falltür
  des gelöschten Schalters „nur warten": wer die Aktion einmal gesetzt hat, findet
  nichts mehr, um sie loszuwerden.

  **Ein Umschalten sieht man einem Bedienelement nicht an**, deshalb steht es im
  Tooltip der markierten Kachel *und* im Hinweis darunter („Nochmal auf die
  markierte Kachel klicken = kein ELSE"). Ungesagt fände es nur, wer es zufällig
  probiert — und dann wäre es dieselbe Falltür, nur mit einem Ausweg, den niemand
  kennt. Für ein Segment mit drei Werten (Nachprüfung: kein / bis Farbe DA / bis
  Farbe WEG) stellt sich die Frage nicht: dort ist „kein" eine Zeile breit und
  liest sich als Zustand, nicht als Aktion.
- **Jede Stelle wird über einen Punkt gesetzt**, auch die des ELSE-Klicks und der
  Nachprüfung. Die DPG-Fassung liess dort Zahlen eintippen — `_step_to_dict` schreibt
  die aber nicht, solange eine Referenz danebensteht, und die Eingabe war beim nächsten
  Öffnen weg.
- **`_verschiebe()` ist der eine Weg** für Umsortieren *und* Phasenwechsel. Der
  Index-Ausgleich (`at -= Anzahl entfernter Schritte davor`) gilt nur, wenn Quelle
  und Ziel dieselbe Phase sind — sonst verschiebt sich beim Ziel nichts.
- **Was dem Punkt gehört, steht beim Punkt.** Name und Farbe eines Klick-Blocks
  gehören nicht dem Schritt, sondern dem Punkt — sie stehen deshalb im Abschnitt
  KLICK-POSITION, zusammen mit Auswahl und Koordinaten. Vorher stand oben „Name
  (Punkt #1)" und weiter unten nochmal „Punkt": dieselbe Sache an zwei Stellen,
  und man musste raten, welche die führende ist. Nur Blöcke **ohne** Punkt (Taste,
  Scans) haben einen eigenen Namen im Abschnitt ALLGEMEIN.

  **Dieselbe Regel gilt im Scans-Reiter, und dort war sie länger verletzt.** Der
  Item-Scan wird oben links gewählt (Klappliste), hiess aber im Inspektor ganz
  rechts — man suchte den Scan in der einen Spalte und benannte ihn in der
  anderen, drei Spalten weiter. Der Name ist **Identität**: er steht jetzt direkt
  unter der Auswahl, und rechts bleibt nur, was man am Scan *einstellt*
  (Toleranz, Auto-Lernen, Richtung, Mitgliedschaft). Die Überschrift dort nennt
  den Scan weiterhin — sonst hängen Regler da, von denen man nicht weiss, woran
  sie hängen. Ein Test misst beide Hälften: der Inspektor baut kein Namensfeld
  mehr, und das Feld links meldet auf `SC.offen`.
- **Feste kurze Auswahl als Kacheln, alles Wachsende als Liste.** Block-Typ (neun)
  und ELSE-Aktion (fünf) sind Kacheln: die Menge ist im Code festgelegt und ändert
  sich nicht, und ein Klappmenü versteckte vier von fünf Möglichkeiten hinter
  einem Klick. Punkte, Sequenzen und Scan-Namen bleiben Listen — die wachsen mit
  den Daten, und fünfzig Kacheln sind kein Bedienelement mehr.
- **Die Farbe eines Punkts ist einstellbar, aber keine Anzeige-Eigenschaft.** Ein
  Farb-Trigger prüft genau diesen Wert; wer ihn ändert, ändert mit, worauf
  gewartet wird. Das Feld sagt das dazu. Ohne gemessene Farbe bleibt es leer,
  statt Schwarz zu behaupten.
- **Neun Typen, neun unterscheidbare Farben** (`BLOCK_COLORS` in `model.py`).
  Taste, Item-Scan und Icon-Scan lagen alle im Bereich Orange/Gelb und waren
  nebeneinander nicht auseinanderzuhalten — womit die Farbe ihren Zweck verlor.
  Verwandte Typen dürfen verwandt aussehen (die beiden Boss-Blöcke), müssen sich
  dann aber deutlich in der Helligkeit trennen.
- **Der Akzent gehört dem Zustand, nicht der Art.** Amber heisst „gewählt"
  (Karte), „läuft gerade" (Kachel im Live-Run) und „Hauptknopf" — deshalb tragen
  die Loop-Phasen ihn nicht mehr, sondern `--loop` (Violett). Jeder Loop-Kopf sah
  vorher aus wie der eine, der gerade dran ist; eine Markierung, die immer an ist,
  markiert nichts. Die Phasenfarben (`--init`/`--loop`/`--end`) gelten überall
  gleich: Board, Live-Run-Kacheln, Phasenbalken der Übersicht.
- **Der Status steht unten, nicht im Kopf.** Oben nahm er den Platz weg, den die
  Bedienelemente brauchen; unten hat er die volle Breite und liegt da, wo sonst
  nichts passiert. Dass er dorthin gehört, merkt man an der Gegenprobe: eine
  lange Meldung im Kopf war immer abgeschnitten.
- **Zustandsklassen bekommen ein Präfix** (`art-ok`, `art-warn`, `art-info`).
  Ohne das hiess die Statusklasse für „Hinweis" schlicht `info` — und `.info` ist
  der runde ⓘ-Knopf. Der Status erbte dessen Gestalt: ein leerer 13-px-Kreis
  neben dem Start-Knopf, den niemand zuordnen konnte. Eine Klasse ohne Präfix ist
  in einer Datei mit einem einzigen Stylesheet ein Namensraum, den alle teilen.
- **Die Seite lädt nichts nach.** Kein Framework, keine Schrift, kein Bild von aussen:
  das Fenster läuft ohne Netz, und alles Nachgeladene wäre beim Start eine leere Fläche.
  Es gibt auch keinen Build-Schritt — was in der Datei steht, ist was läuft.

Getestet ist alles, was in der Brücke liegt: Umsortieren über Phasengrenzen,
Mehrfachauswahl, jeder Block-Typ, die Feldsetzer und das Speicher-Veto bei einem Scan
ohne Namen (`Sequenz-Studio sortiert per Ziehen um`, `was der Inspektor setzt, überlebt
das Speichern`). Ungeprüft bleibt die Anzeige selbst.

### Sequenz-Modell
Eine `Sequence` hat 3 Phasen: `init_steps` (einmalig), `loop_phases` (mehrere `LoopPhase`s je mit eigenem `repeat`-Counter, optional `scheduled_start` für Uhrzeit-Trigger), `end_steps` (einmalig nach allen Zyklen). Jeder `SequenceStep` ist polymorph: kann Klick, Key-Press, Wait-Pixel-Trigger, Item-Scan, Boss-Scan, Boss-Watcher (kontinuierliche Überwachung), Wait-only oder Screenshot sein — gesteuert über die gesetzten Felder. `else_config` definiert Fallback bei Trigger-Miss.

**`else` ist ein *stattdessen*, kein *zusätzlich*.** Greift die else-Aktion, entfällt die
eigene Aktion des Schritts — so steht es in der Editor-Hilfe (`else skip` = „nur DIESEN
Schritt überspringen", `else <Punkt-Nr>` = „**stattdessen** diesen Punkt klicken").

**`else` ist die Antwort auf eine nicht erfüllte Bedingung — hat ein Schritt keine,
feuert es nie.** Ausgelöst wird es an genau diesen Stellen:

| Auslöser | wann |
|---|---|
| Farb-Bedingung | Timeout erreicht, „nur prüfen" nicht erfüllt, Pillow fehlt |
| Nachprüfung | keine Wirkung nach allen `verify_retries` |
| Item-Scan | kein Item gefunden |
| Boss-Scan | kein Boss erkannt |
| Icon-Scan | kein Icon erkannt |

Ein reiner Klick, eine Taste, ein Warten, ein Screenshot und auch der
Boss-**Watcher** lösen es nicht aus: der Watcher läuft in seine eigenen Grenzen
(max. Scans, Timeout) und macht danach weiter. `else_greift()` in
`bridge_contract.py` (über `bridge.py` weiterhin exportiert) hält
dieselbe Liste für die Anzeige: **ohne Auslöser gibt es den ELSE-Abschnitt gar
nicht** — dieselbe Regel wie beim Farb-Trigger, den es bei Scans und Screenshot
auch nicht gibt.

**Fällt der Auslöser weg, fällt das ELSE mit** (`_else_aufraeumen()`): wer den
Trigger entfernt oder den Typ umstellt, hat den einzigen Auslöser genommen — die
Ersatzaktion ist damit wirkungslos. Sie stehenzulassen hiesse, sie unsichtbar in
der Datei zu behalten, denn der Abschnitt fällt ja mit dem Auslöser weg. Stellt man
den Typ zurück, steht er wieder da — leer, zum frischen Auswählen. Die Statuszeile
sagt, dass geräumt wurde.

**Nur bei einer Änderung, nie beim Laden.** Bringt eine Datei ein wirkungsloses ELSE
mit (von Hand geschrieben, importiert, aus einer älteren Fassung), wird sie nicht
stillschweigend beschnitten: dort bleibt der Abschnitt samt Warnung stehen (auf der
Karte „greift nie"), und der Nutzer entscheidet. Ein Aufräumer, der ungefragt an
fremden Daten arbeitet, wäre der stille Datenverlust, den das Projekt an anderer
Stelle mühsam abgeschafft hat.

Damit das durchsetzbar ist, reicht ein bool nicht: er kann „Schritt erledigt, weiter zum
nächsten" nicht von „Sequenz abbrechen" unterscheiden. Beides als `False` zu melden riss
den Rest der Phase mit ab, beides als `True` liess den Schritt nach der else-Aktion noch
sein eigenes Ziel klicken. Deshalb geben Vorab-Entscheidungen über einen Schritt
`GATE_RUN` / `GATE_SKIP` / `GATE_STOP` zurück (Konstanten in `runtime/debug.py`,
genutzt von `step_gate` und `_execute_wait_for_color`).

### Nachprüfung: „hat die Aktion gewirkt?"

`wait_condition` fragt **vor** dem Schritt, ob er dran ist. `verify_condition` fragt
**danach**, ob er etwas bewirkt hat — bis dahin war jeder Klick ein Schuss ins Dunkle:
ging er ins Leere (Lag, Fenster nicht vorn, Popup davor), lief die Sequenz weiter und
alles Folgende traf daneben.

Dieselbe `WaitCondition` wie die Vorbedingung — die kann schon alles Nötige. Gesetzt
wird sie im Sequenz-Editor mit `verify <Schritt-Nr> <Punkt-Nr> [gone]`.

Drei Regeln:

- **Der Gewinn ist die Wiederholung, nicht die Meldung.** Bleibt die Wirkung aus, wird
  die Aktion bis zu `verify_retries` mal neu ausgeführt. Der häufigste Grund für einen
  wirkungslosen Klick ist vorübergehend, und ein zweiter Klick löst ihn.
- **Ohne `verify_condition` kostet es nichts.** Kein Screenshot, kein Zweig — ein Test
  pinnt fest, dass der Normalfall unverändert bleibt.
- **Eine ausgebliebene Wirkung reisst die Sequenz nicht.** Nach dem letzten Versuch
  entscheidet `else_config`; ohne else gilt der Schritt als erledigt. Das ist ein
  Hinweis, kein Abbruchgrund — anders als eine nicht erfüllte *Vor*bedingung.

Regel beim Erweitern: **wer eine else-Aktion auslöst, gibt `GATE_SKIP` zurück** — nie
`GATE_RUN` und nie stumpf `True`. Die Übersetzung macht `_gate_nach_else()`; nur
`restart`/`skip_cycle` werden zu `GATE_STOP`. Step-Handler, die die else-Aktion als
Letztes tun und danach nichts mehr ausführen (Item-/Boss-/Icon-Scan), dürfen weiterhin
`return execute_else_action(...)` — dort gibt es keine nachgelagerte eigene Aktion, die
irrtümlich noch feuern könnte.

### Sequenz-Aufnahme (`editors/sequence_recorder.py`)
Aufgezeichnet wird, was das Spielen ausmacht: **Linksklick, Tastendruck, Mausrad**,
per `CTRL+ALT+M` ein **Warte-Marker auf eine Farbe** und per `CTRL+ALT+D` ein
**Screenshot-Marker**. Jedes Ereignis ist ein `RecordEvent` (`models.py`, `REC_*`) —
rein transient, wird nie gespeichert; `stop_recording()` baut daraus Schritte und
wirft die Liste weg.

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

#### Die fünf Marker

Alles ausser Klick/Taste/Rad ist ein **Marker**: ein globaler Tastendruck ohne
Rückfrage, der beim Stoppen zu Struktur wird. Sie unterscheiden sich in genau drei
Fragen, und daran hängt der jeweilige Bau:

| Marker | Taste | eigener Schritt? | eigener Punkt? | Mausposition |
|---|---|---|---|---|
| Warte auf Farbe | `CTRL+ALT+M` | nein — geht in den nächsten Klick ein | nein | **zufällig**, wird ignoriert |
| Screenshot Vollbild | `CTRL+ALT+D` | ja | nein | irrelevant |
| Screenshot Bereich | `CTRL+ALT+SHIFT+D` | ja (aus **zwei** Drücken) | nein | **bewusst** — die Ecken |
| Beobachten ohne Klick | `CTRL+ALT+SHIFT+M` | ja (`wait_only`) | **ja** | **bewusst** — das Beobachtete |
| Phasengrenze | `CTRL+ALT+SHIFT+P` | nein — schneidet nur | nein | irrelevant |

**Die Mausposition ist die entscheidende Unterscheidung.** Beim Warte-Marker parkt die
Maus irgendwo, deshalb wird sie verworfen (ein früher Entwurf legte dort einen Punkt an
— in einer echten Aufnahme stand dann `Warte auf Farbe bei (4483, 1038) Schwarz` in
points.json). Bei Bereichs-Ecke und Beobachten fährt der Nutzer die Stelle *an* und
drückt dort — dieselbe Geste, aber bewusst, also darf sie verwendet werden. Wer einen
neuen Marker baut, beantwortet zuerst diese Frage; sie entscheidet über `punkte_fuer_events`.

**Aufbereitet wird in fester Reihenfolge**, jede Stufe entfernt eine Sonderform, damit
die nächste sie nicht mehr kennen muss:

1. `bereiche_zusammenfassen()` — zwei `REC_REGION`-Ecken → **ein** `REC_SCREENSHOT`
   mit Rechteck. Danach existiert `REC_REGION` nicht mehr. Eine einzelne Ecke wird
   verworfen und gemeldet, **nicht** still zu Vollbild degradiert — das wäre etwas
   anderes als das Gewollte.
2. `phasen_grenzen()` — Grenzen **raus** aus dem Strom, gemerkt als Schritt-Indizes.
   Sie zu überspringen statt zu entfernen reichte nicht: eine Grenze wäre dann das
   „vorherige Ereignis" des nächsten Schritts, und dessen Wartezeit würde ab dem
   Tastendruck statt ab der letzten echten Aktion gemessen (aus 6 s würde 1 s).
3. `marker_pruefen()` — haltlose Warte-Marker weg.

Danach ist `schritte_aus_events()` frei von Sonderfällen, und `phasen_aufteilen()`
schneidet die fertige Liste in INIT/LOOP/END.

**Die Aufnahme erfindet keine Zeit und wirft keine weg.** Die Sekunden zwischen den
beiden Bereichs-Ecken bleiben in der Wartezeit des *nächsten* Schritts stehen. Bedienzeit
von Spielzeit zu trennen kann die Aufnahme nicht (Nachdenken sieht genauso aus), und für
„das soll nicht zählen" gibt es `CTRL+ALT+H`. Einzige Ausnahme ist der Warte-Marker —
dort ersetzt eine *Bedingung* die Zeit, sie geht also nicht verloren, sondern über.

**Die Phasengrenze ist der Marker, der sich am wenigsten nachholen lässt.** Der
Sequenz-Editor bearbeitet jede Phase für sich (`edit_phase`); einen Befehl, einen
Schritt in eine *andere* Phase zu verschieben, gibt es nicht. Nachträglich aufteilen
hiesse löschen und neu anlegen — bei 50 aufgenommenen Schritten fällt das aus. Ohne
Marker bleibt alles in einer Loop-Phase, also im bisherigen Verhalten.

#### Was NICHT in die Aufnahme gehört

Der Filter ist nicht „geht das mit einem Tastendruck", sondern: **ist es hinterher
verloren?**

- **Nein → Editor.** `noclick`, `checkcolor`/`checkgone`, Wartezeit ändern,
  Zufallsbereiche, `else …` sind Umformungen *eines einzelnen Schritts*, und `edit <Nr>`
  führt durch alle. Dafür einen Hotkey zu verbrennen spart zehn Zeichen Tipparbeit und
  kostet Bedienoberfläche.
- **Geht gar nicht → Editor.** Item-/Boss-/Icon-Scan verweisen **per Namen** auf eine
  Konfiguration; ohne Auswahl gibt es nichts aufzunehmen. Ein Platzhalter-Schritt wäre
  ein Schritt, der zur Laufzeit nichts tut — dasselbe Problem wie ein Rückfallwert.

Das allgemeine Muster für alles Neue: **beim Aufnehmen die Stelle im Ablauf markieren,
im Editor konfigurieren.** Ein blockierender Prompt während der Aufnahme kommt nie an.

`CTRL+ALT+U` nimmt während der Aufnahme das letzte Ereignis zurück, sonst den letzten
Punkt — gleiche Bedeutung, der Gegenstand hängt am Zustand. Kein eigener Buchstabe: in
der Basis-Ebene sind nur noch R/Y frei (D ging an den Screenshot-Marker). Es nimmt
**jedes** Ereignis zurück, auch Marker — eine versehentlich gesetzte Phasengrenze oder
eine falsch angefahrene Bereichs-Ecke räumt man damit weg.

Der **Tastatur-Hook** meldet nichts bei gedrücktem CTRL oder ALT (dort liegen die
Hotkeys — sonst stünde ein `j` in der Sequenz, sobald man mit `CTRL+ALT+J` stoppt),
nichts, was `send_key()` nicht abspielen kann, und keine Wiederholung einer
festgehaltenen Taste. Er ist die Kür: schlägt er fehl, läuft die Aufnahme ohne ihn
weiter — eine Aufnahme ohne Klicks wäre dagegen sinnlos. Beide Hooks werden auch beim
Beenden entfernt (`handle_quit`), sonst hängt ein Tastatur-Hook systemweit weiter.

**Rechtsklick wird bewusst nicht aufgezeichnet**: der Autoclicker kann gar keinen
ausführen (`send_click` ist auf `LEFTDOWN`/`LEFTUP` festgelegt, es gibt kein Modellfeld
und keinen Editor-Befehl). Ihn mitzuschneiden hiesse, etwas aufzunehmen, das beim
Abspielen zum Linksklick wird. Wer ihn nachrüstet, braucht die ganze Kette:
`winapi` → Modellfeld → `safe_click` → Serializer-Default → Editor-Anzeige.

Der Hook liefert beim Mausrad die **rohe** Windows-Distanz, nicht schon Rasterstufen:
hochauflösende Räder senden Bruchteile, und einzeln abgerundet ergäben die null. Der
Recorder summiert erst (eine Drehung = ein Ereignis, `_SCROLL_MERGE_GAP`) und teilt dann.

Das Rad lässt sich per `record_scroll: false` (Config) ganz abschalten — für Spiele, in
denen es nur die Ansicht dreht und solche Drehungen die Sequenz bloss aufblähen.
Abgeschaltet gibt `_on_wheel_factory()` **`None`** zurück, und `install_mouse_hook`
ignoriert das Rad schon in der Hook-Prozedur. Absichtlich dort und nicht in
`_anhaengen`: ein Callback, der jedes Ereignis nur entgegennimmt, um es wegzuwerfen,
liefe bei jeder Radbewegung mit — auch wenn gerade niemand aufnimmt.

### Boss-Scan vs. Boss-Watcher
- **Boss-Scan**: Einmaliger Scan in einem Step. Wenn nichts erkannt → `else_config` oder Default-Action.
- **Boss-Watcher**: Schleife im Step, prüft alle `llm_watcher_interval` Sekunden bis ein Boss erkannt wird (mit `llm_watcher_max_scans` und `llm_watcher_timeout` als Exit-Bedingungen). Erst dann `_execute_boss_action`.

**Zwei Zusatz-Erkenner, gleiche Bauart**: OCR (`use_ocr` + `ocr_fallback`) und LLM
(`use_llm` + `llm_fallback`), beide in `BossScanConfig`, beide zusätzlich per Config
scharfgeschaltet (`ocr_enabled` / `llm_enabled`). `*_fallback=False` heisst **vor**
Template/Marker-Matching, `*_fallback=True` heisst **nur wenn** Template/Marker nichts
findet. Bei gleicher Einstellung läuft **OCR vor LLM** — OCR ist lokal und schnell, das
LLM kostet bis `llm_timeout`.

Zwei Regeln, an denen `execute_boss_scan()` in `runtime/boss_detection.py` hängt:
- **Kein Erkenner darf doppelt laufen.** Primär- und Fallback-Zweig schliessen sich über
  `not cfg_*_fallback` / `cfg_*_fallback` gegenseitig aus.
- **Alle Flags im selben Lock-Snapshot einfrieren.** Wer sie zweimal frisch liest, kann
  einen Editor dazwischen umschalten sehen und läuft dann doch doppelt.

Beide Erkenner bekommen die **gemergte** Boss-Liste (lokal + global) als
`bosses_snapshot` übergeben und dürfen nicht auf `config.bosses` zurückgreifen — sonst
findet der Treffer die Bibliotheks-Bosse nicht wieder.

Unbekannte Bosse (OCR/LLM erkennt einen Namen der nicht in der Liste ist) werden automatisch als `BossProfile(action=BOSS_ACTION_SKIP)` gespeichert — Prüfung und Append im selben `state.lock`-Block, sonst hängt ein Sync-Scan neben dem Async-Watcher denselben Boss doppelt an.

**Globale Boss-Bibliothek**: `state.global_bosses` (Editor: Boss-Scan-Menü → "Boss-Bibliothek verwalten") gilt zusätzlich in jedem Boss-Scan. `execute_boss_scan()` merged lokal + global im Lock-Snapshot; lokale Bosse gewinnen bei Namensgleichheit. Mit `boss_learn_global=true` (Config, umschaltbar im Boss-Scan-Menü) landen neu entdeckte Bosse in der Bibliothek statt im Scan.

**Item-Auto-Lernen** (opt-in pro Scan, `ItemScanConfig.learn_unknown`): `execute_item_scan()` lernt unbekannte, nicht-leere Slot-Inhalte als neue globale Items (Kategorie 'Auto', Template + Marker) — nur nach `state.global_items`, nie in die Scan-Config, damit sie nicht ungeprüft geklickt werden. Dedup per Template-Match gegen alle globalen Items. Die Items heissen erst 'Auto <Slot>'; **die LLM-Benennung läuft bewusst NICHT im Scan** (würde den Worker pro Item bis `llm_timeout` blockieren), sondern manuell über den Item-Editor-Befehl `autoname` (`editors/item_editor/commands.py::handle_autoname_command`), der `llm_vision.suggest_item_name()` aus den gespeicherten Templates aufruft.

### Koordinaten nach einem Bildschirm-Umbau

Ändert Windows die Monitor-Anordnung, sind alle gespeicherten Koordinaten um denselben
Betrag verschoben. Zwei Wege, und die Reihenfolge zählt:

| Weg | wo | Genauigkeit |
|---|---|---|
| `repair` | Slot-Editor | **misst** die Slots neu — pixelgenau |
| Kalibrieren | Studio → Werkzeuge | Referenzpunkt mit der Maus, **mit Vorschau** |
| `fix` | Punkte-Menü (`CTRL+ALT+P`) | dasselbe in der Konsole |

**Zuerst `repair`**, dann dessen gemessenen Versatz auf den Rest anwenden lassen: eine
Maus-Position trifft den Pixel nie genau, und bei einer Scan-Region schneiden drei Pixel
das Item-Icon an. `fix` bleibt für den Fall ohne Slots.

**Hat sich nicht alles um denselben Betrag verschoben, hilft kein Versatz.** Ein
Spiel-Update legt Knöpfe um, ein anderes Fenster hat eine andere Grösse — dann
stimmt jede Stelle einzeln nicht mehr, und beide Wege oben rechnen etwas
Falsches gleichmässig hoch. Dafür gibt es zwei Runden, die Punkt für Punkt
gehen:

| Runde | wo | wie |
|---|---|---|
| `walk` | Punkte-Menü | Zeiger springt hin, `n` setzt auf die Mausposition — **ohne Klick** |
| `klick` | Punkte-Menü **oder** Studio → Werkzeuge | die Sequenz einmal von Hand **nachklicken** (`editors/nachklick.py`) |

**Der Unterschied ist der Klick, und er entscheidet.** `walk` fasst nichts an —
also bleibt das Spiel stehen, wo es steht, und ein Punkt im dritten Untermenü
ist gar nicht sichtbar: man sieht den Desktop und rät. Bei `klick` geht jeder
Klick ans Spiel, die Oberfläche öffnet sich genau wie im Lauf, und **der nächste
Punkt liegt dann vor einem**. Man spielt die Sequenz einmal von Hand durch, und
hinter jedem Klick steht die neue Stelle im Punkt.

Fünf Regeln, an denen die Klick-Runde hängt:

- **Geändert wird nur die Stelle.** Wartezeiten, Farb-Bedingungen,
  Nachprüfungen, ELSE, Scans und die Reihenfolge bleiben — die Runde fasst die
  Sequenzdatei überhaupt nicht an, sie schreibt `x`, `y` und (nur wenn der Punkt
  schon eine hatte) die Farbe in `points.json`.
- **Jeder Punkt einmal, in der Reihenfolge des Laufs** (INIT → Loop-Phasen →
  END). Klickt eine Sequenz zweimal denselben Knopf, ist das ein Punkt; ihn
  zweimal zu setzen hiesse, den ersten Griff wieder zu verwerfen.
- **Was sie nicht erreicht, sagt sie** (`klickpunkte()` gibt zwei Listen
  zurück): beobachtete Pixel, ELSE-Klicks, Nachprüfungen und Rad-Schritte kommen
  in einem normalen Durchlauf nicht vor. Dafür bleibt `walk`. Wer beides ist —
  erst beobachtet, später geklickt — zählt als Klick; deshalb sammelt die
  Funktion **erst alle Klicks und dann den Rest**, in einem Durchgang fiel so
  ein Punkt aus der Runde heraus.
- **Sie läuft aus dem Maus-Hook**, wie die Aufnahme. Deshalb schliesst der
  Punkte-Editor beim Start (ein blockierendes `input()` hielte die Message-Pump
  an, und der Hook sähe keinen Klick), deshalb sind alle weiteren Griffe globale
  Hotkeys — und deshalb wird **im Hook nicht auf Platte geschrieben**: ein
  Low-Level-Hook, der zu lange braucht, wird von Windows ausgehängt, und dann
  fehlen Klicks mitten in der Runde. Gespeichert wird am Ende (`stop_nachklick`,
  auch beim Beenden des Programms).
- **Die vier Hotkeys sind geliehen, nicht neu**: `CTRL+ALT+J` beendet (dieselbe
  Bedeutung wie bei der Aufnahme), `CTRL+ALT+H` pausiert (navigieren, ohne einen
  Punkt zu verbrauchen), `CTRL+ALT+K` überspringt, `CTRL+ALT+U` geht zurück —
  und **zurück heisst zurück**: der eben gesetzte Punkt bekommt seine alte
  Stelle wieder, sonst behielte ein Verklicker sie bis zum nächsten Lauf. Die
  Basis-Ebene ist voll (s. o. beim Hotkey-Flow); alle vier tragen hier dieselbe
  Bedeutung wie sonst, nur einen anderen Gegenstand.

Der Zeiger springt dabei **nicht** nach einem echten Klick auf den nächsten
Punkt, nur beim Start, beim Überspringen und beim Zurückgehen: die Maus direkt
nach einem Klick wegzuziehen kann ein Ziehen abbrechen oder einen Tooltip
verschlucken, und das Spiel verarbeitet den Klick womöglich noch.

**Einzelne Punkte statt aller**: Punkte-Menü → `walk`, dann `n` (Maus an die richtige
Stelle) bzw. `f` (nur Farbe neu lesen). Das ist der Weg, wenn nicht alles gleichmässig
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
- `repair` übernimmt nur bei **eindeutiger Zuordnung**: gleiche Anzahl, gleiche Grösse,
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
- **Keine neuen Markdown-Dateien**, ausser explizit gefragt. `IDEAS.md` ist das Backlog für noch nicht gebaute Features mit Nutzen+Tradeoff.
- **Commit-Messages auf Deutsch**, knapper Imperativ-Stil, mehrzeilig erlaubt für Begründung.
- **Branch-Konvention**: Feature-Branches `claude/<thema>-<hash>`, Push direkt auf den Branch (kein PR ohne expliziten Auftrag).

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
- `tools/sync_json.py` wurde gelöscht statt gepflegt; `_norm_items` steht als
  `_norm_noop` da, weil es ein totes Feld in ein anderes totes Format hob.

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

### Plattform-Schicht (Windows und Linux/X11)

**Das Betriebssystem steht in einem Backend, nicht im Rest des Baums.**
`platforms/load_backend()` wählt es einmal anhand von `sys.platform`; alles andere
importiert weiterhin `autoclicker.winapi` und merkt nichts davon. Ein nicht
unterstütztes System (Wayland, macOS) fliegt dort mit `RuntimeError` auf, statt
sich später als stiller Fehlschlag zu zeigen.

| Modul | was |
|---|---|
| `winapi.py` | **stabile Fassade** — 24 Zeilen, reicht an das Backend durch. Kein Systemcode mehr. |
| `platforms/base.py` | der Vertrag (`PlatformBackend`-Protocol): Eingabe, Fenster, Hotkeys, Bildschirm |
| `platforms/common.py` | betriebssystemneutral: Tastennamen, `HOTKEY_*`-IDs, `PlatformError`, `APP_ID` |
| `platforms/windows.py` | WinAPI-Backend (ctypes: Maus, Tastatur, Hotkeys, GDI, Hooks, Fenster-Symbol) |
| `platforms/linux_x11.py` | X11-Backend (`python-xlib`, `pynput`, `mss`) |
| `utils/io.py` | Tastendruck-Erfassung (`msvcrt` / `GetAsyncKeyState`) |
| `utils/console.py` | Konsolen-Erkennung, Fenstertitel, ANSI-Freischaltung |

Windows-spezifischer Code darf nur noch in **drei** Dateien stehen —
`platforms/windows.py`, `utils/io.py`, `utils/console.py`. Ein Test in
`tools/test_logic.py` (`PLATTFORM_MODULE`) hält das fest: greift ein anderes Modul auf
`ctypes.windll`, `ctypes.WinDLL`, `wintypes` oder `msvcrt` zu, schlägt er fehl und nennt
die Datei. Er prüft **beide** Richtungen — kein Windows-Aufruf ausserhalb der Liste, und
kein Eintrag auf der Liste, der gar nichts Plattformspezifisches mehr enthält, sonst
wächst sie zur Fiktion.

**Wer einen Systemaufruf braucht, erweitert den Vertrag, nicht die Fassade.** Neue
Funktion in `base.py` eintragen, in *beiden* Backends implementieren, über `winapi`
exportieren. Nur eine Hälfte zu bauen ist der Fehler, den die Matrix in
`.github/workflows/tests.yml` fängt: die Suite läuft auf Ubuntu **und** Windows gegen
denselben Testvertrag (`test_platforms.py`).

Das gilt auch für `imaging.py`: es ist seit dem Umbau plattformneutral und holt sich
den Screenshot über das Backend, statt selbst BitBlt zu rufen.

**Bildschirm-Geometrie gehört in `winapi.py`, nicht in den Aufrufer.** `GetSystemMetrics`
lag vorher fünfmal im Baum (`imaging`, `runtime/item_scan`, `diagnose`, `scan_studio`,
`utils/console`), jedes Mal mit eigenen `SM_*`-Konstanten und eigenem `try/except`. Wer
die Fenstergrösse oder den virtuellen Desktop braucht, nimmt:

- `get_virtual_desktop()` → `(l, t, r, b)` über alle Monitore, oder `None`
- `get_virtual_origin()` → linke/obere Kante, `(0, 0)` als Rückfall
- `get_screen_size()` → Primärmonitor, oder `None`
- `get_screen_center()` → Mitte, mit Rückfallkette bis `(960, 540)`

`None` statt `(0, 0, 0, 0)` ist Absicht: eine Fläche von 0×0 würde jede Koordinate als
„ausserhalb aller Monitore" melden — genau der Fehler, den `diagnose.py` sonst produziert
hätte.

## Bekannte Stolperfallen

- **Headless Linux**: Der vollständige Import und die automatischen
  Plattformverträge laufen. Echte Hotkeys, Eingabe, Fenster und Screenshots
  brauchen für den manuellen Test eine X11-Sitzung. Wayland wird bewusst
  abgelehnt.
- **DPI-Awareness**: `platforms/windows.py` setzt früh `SetProcessDpiAwareness(2)` — Skalierung ≠ 100% sollte korrekt funktionieren. **Multi-Monitor mit unterschiedlichen DPIs ist weiterhin nicht getestet.** Verifiziert ist dagegen der Fall, über den man zuerst stolpert: Monitore mit **negativen** Koordinaten (links vom bzw. über dem primären). BitBlt, der ImageGrab-Fallback, `get_pixel_color` und Regionen quer über Monitorgrenzen liefern dort korrekt — die Offset-Rechnung über `SM_XVIRTUALSCREEN`/`SM_YVIRTUALSCREEN` stimmt. Beim Debuggen beachten: `get_virtual_desktop()` gibt ein **Rechteck** (links, oben, rechts, unten) zurück, keine Breite/Höhe — die Breite ist `rechts - links`, und bei negativem Ursprung ist das nicht dasselbe.
- **Nicht-DPI-aware Werkzeuge lügen über die Monitor-Geometrie.** Koordinaten aus PowerShell (`System.Windows.Forms.Screen`) oder anderen Prozessen ohne DPI-Awareness sind skaliert und passen nicht zu denen, die die App sieht. Zum Nachmessen einen Prozess nehmen, der `autoclicker.winapi` importiert hat.
- **OpenCV / Pillow optional**: Code prüft `OPENCV_AVAILABLE` / `PILLOW_AVAILABLE` und degradiert sauber. Neue Features die diese brauchen → Verfügbarkeit prüfen.
- **Der erste OCR-Aufruf lädt Modelle aus dem Netz.** EasyOCR holt beim allerersten `read_text()` Detection- und Recognition-Modell per Download — Sekunden bis Minuten, und es kann mit HTTP-Fehler scheitern; danach liegt ein Aufruf bei ~300 ms. Passiert das im Worker, steht die Sequenz so lange. Dieselbe Klasse Problem wie beim LLM, weshalb die LLM-Benennung bewusst nicht im Scan läuft (s.o.). Wer `ocr_enabled` neu einschaltet, sollte den ersten Aufruf nicht in einen laufenden Scan legen.
- **`import_bundle()` schreibt sofort auf Platte, `export_bundle()` nicht.** Der Import legt Templates an und ruft `save_global_slots`, `save_global_items`, `save_item_scan`, `save_boss_scan`, `save_global_bosses`, `save_data` **und `save_config`** — er befüllt also nicht bloss den State. Mit einem frischen `AutoClickerState()` schreibt `save_config()` die Default-Config über die vorhandene `config.json`; die Tests in `test_logic.py` übergeben deshalb `import_config=False`. Für einen vollen Roundtrip die Pfad-Relativität nutzen: Datenordner + `config.json` in einen Temp-Ordner kopieren und vorher dorthin `os.chdir()` — die Konstanten in `persistence/paths.py` sind bewusst CWD-relativ.
- **Race-Condition-Sensibel**: Lange-laufende Loops im Worker (Boss-Watcher, Item-Scan) iterieren über shared dicts — Mutationen aus Editoren können während des Laufens passieren. Im Zweifel `dict(state.x)`-Snapshot unter Lock.
