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
python tests/alle_tests.py      # ALLE Tests, ein Aufruf — das vor einem Commit
python tests/alle_tests.py --nur vertrag     # nur die Vertragssuite (schnell)
python tests/alle_tests.py --nur rauch --rauchtest werkzeuge   # eine Ansicht
python tests/alle_tests.py --mutationen      # dazu die Gegenproben (so ruft CI es auf)
python tests/alle_tests.py --nur rauch --rauch-pflicht  # fehlender Browser = rot
python -m flake8                # Linter — Regeln stehen in `.flake8`, kein Argument noetig
python -m flake8 --select=F autoclicker/ market_analysis/ main.py tools/ tests/
                                # dasselbe ausgeschrieben (so ruft CI es auf)

# Die Schichten einzeln, falls man sie direkt braucht:
python tests/test_logic.py      # Vertragssuite — ohne GUI, ohne Windows, ohne Netz
python -m tests.wurzeltests     # Wurzelmodule (--ohne-vertrag laesst den Wrapper weg)
python -m tests.rauch.werkzeuge   # ein Rauchtest im Browser
python tests/mutationspruefung.py      # Gegenproben einzeln (--fall NAME)
python tools/katalog.py         # Item-/Gegner-Katalog aus der Spiel-API holen
                                # (--zeige = nur anzeigen, --ziel = anderer Pfad)

python main.py                  # Startet die App auf Windows oder Linux/X11
python tools/test_llm.py            # Standalone-Verbindungstest für Ollama/LM Studio (nutzt llm_vision)
python tools/test_llm.py screenshot # LLM-Screenshot-Test ohne Editor-Setup
python tools/llm_bench.py           # Misst die LLM-Benennung gegen den eigenen Bestand
                                    # (--bild slot|grund, --modell X, --alle-modelle,
                                    #  --zweistufig, --stimmen 3, --reasoning)
python tools/migrate.py         # Hebt alle JSON-Dateien aufs aktuelle Format (--write zum Schreiben)
                                # Nur fuer Sonderfaelle — die App macht das bei jedem Start selbst
python tools/slot_tester.py     # Debug-Tool für Slot-Erkennung
python tools/log_report.py      # Wertet die Session-Logs aus (welcher Schritt haengt?)
                                # --letzte = nur die neueste Session
python tools/symbol.py          # Schreibt das Programm-Symbol als PNG + ICO
                                # (fuer Verknuepfungen; das Fenstersymbol setzt die App selbst)
```

**Ein Kommando, drei Schichten: `python tests/alle_tests.py`.**

| Schicht | was sie prüft | braucht |
|---|---|---|
| Vertragssuite (`tests/test_logic.py`) | Logik ohne GUI, ohne Windows, ohne Netz | nichts |
| Wurzelmodule (`tests/wurzel/`) | Import/Export-Sicherheit, Plattformvertrag, Studio-UX, Runtime-Härtung | Pillow (sonst übersprungen) |
| Rauchtests (`tests/rauch/`) | die echte Seite im Browser vor der echten Brücke | Playwright + Chromium |

**Alles Testbare liegt unter `tests/`, und `tools/` enthält nur noch Werkzeuge.**
Vorher lagen die drei Schichten an drei Orten: elf `test_*.py` im
Wurzelverzeichnis, die Vertragssuite in `tools/`, die Rauchtests daneben. Wer
„die Tests" suchte, musste alle drei kennen — und das Wurzelverzeichnis eines
Projekts ist der schlechteste Ort für elf Dateien, die man beim Arbeiten am
Programm nie aufmacht.

| liegt jetzt | war vorher |
|---|---|
| `tests/alle_tests.py`, `tests/mutationspruefung.py`, `tests/wurzeltests.py` | `tools/` |
| `tests/test_logic.py` + `tests/vertrag/` | `tools/test_logic.py` + `tools/tests/` |
| `tests/wurzel/` | die `test_*.py` im Wurzelverzeichnis |
| `tests/rauch/` | `tools/rauchtests/` |

Zwei Dinge, die dabei auffallen sollen:

- **`tools/test_llm.py` und `tools/test_ocr.py` sind mitgezogen — nicht.** Sie
  tragen den `test_`-Präfix, sind aber interaktive Werkzeuge: sie öffnen einen
  Region-Picker und reden mit einem LLM bzw. einer OCR-Engine. Ein Name, der
  etwas Falsches verspricht, ist hier sonst ein Fehler; diese beiden bleiben in
  `tools/`, weil sie **dort** hingehören, und der Baum in der README sagt es
  ausdrücklich dazu.
- **`tests/wurzel/` ist ein flacher Ordner ohne `__init__.py`**, und das ist
  Absicht: `unittest.discover()` legt sein Startverzeichnis selbst in
  `sys.path`, also findet jedes Modul sein `test_support` weiterhin als
  schlichten Nachbarn. Das Repo-Wurzelverzeichnis legt `wurzeltests.py`
  zusätzlich dazu (`autoclicker`, `main`, `market_analysis`) — ohne das liefe
  nur der Aufruf über `-m`, nicht der ausgeschriebene.

**Hier standen einmal ZWEI Kommandos, und das hat einen roten CI-Lauf gekostet:**
`tests/test_logic.py` war grün, gemeldet wurde „alles grün", und die Wurzelmodule
liefen nie. Die Warnung dazu stand an dieser Stelle — eine Regel, an die man sich
erinnern muss, ist keine.

Der Grund für die Trennung ist weg: `test_itemscan_editor_ux` und
`test_scan_services` importierten `PIL` auf Modulebene und starben ohne Pillow
schon beim LADEN, womit `unittest` gar nicht erst sammelte. Beide überspringen
jetzt sauber (`@braucht_pillow`), und damit läuft ein Aufruf überall — 106 Tests
mit Pillow, dieselben 106 mit 23 übersprungenen ohne.

**Was fehlt, wird übersprungen und gesagt, nicht als Fehler gemeldet.** Ein roter
Lauf, der nur die Testumgebung beschreibt, verdeckt echte Fehler im Rauschen —
dieselbe Regel wie bei OpenCV und Pillow im Produktivcode.

**Die Rauchtests sind die Schicht, die die Vertragssuite nicht sehen KANN.** Sie
ruft die Brücken-Methoden direkt auf, also genau so, wie die Seite es *nicht* tut:
ein Tippfehler in einem Methodennamen, ein `appendChild` mit einer Liste, ein
Zustand, der einen Neuaufbau nicht überlebt — nichts davon fällt dort auf, und im
Fenster sofort (der Reiter bleibt leer). Deshalb steht dort ein Chromium mit der
echten `index.html` davor und der echten `StudioBridge` dahinter; `window.pywebview.api`
ist ein Proxy, der jeden Aufruf nach Python weiterreicht. Kein Nachbau — dieselben
zwei Seiten wie im Fenster, nur ohne pywebview dazwischen (`rauchtests/_bruecke.py`).

Ein neuer Reiter bekommt dort eine Datei; das Gerüst (`Fenster`, `sandkasten`,
`stelle_bildschirm`) nimmt einem den Aufbau ab. Sie laufen in CI in einem eigenen
Job, weil dort erst ein Browser installiert werden muss.

**`tests/test_logic.py`** prüft Serialisierung,
Migration, Runtime-Gates, Kalibrierung, Tastenbelegung und die Plattform-Grenze — ohne
GUI, ohne Windows, ohne Netz. `msvcrt` und `ctypes.windll` werden am Dateianfang gestubbt;
deshalb läuft die komplette Logik-Schicht auch hier.

**Und seit `.github/workflows/tests.yml` läuft sie auch, wenn niemand daran denkt.**
Push und Pull Request auf jedem Branch, als Matrix auf Ubuntu und Windows. Dazu
zwei eigene Jobs: die Rauchtests (Browser, nur Linux — es geht um die Seite, nicht
um die Plattform) und `flake8 --select=F` (tote Importe, Tippfehler in Namen).
Jeder Job muss grün sein; ein roter Lauf ist ein Fehler, kein Hinweis.
Geprüft wird auf **Python 3.10**, der unteren Grenze — auf der neuesten Version
zu testen sagt nichts darüber, ob die älteste noch trägt.

**Der Test-Job läuft dreimal: `ohne`, `pillow` und `mit` Bildpaketen.** OpenCV und Pillow sind
optional, und der Code degradiert sauber ohne sie — nur überspringt die Suite dann
**über hundert Tests** (Template-Vergleich, Masken, Slot-Erkennung, die
Grössen-Meldung): 1.154 statt 1.273. Ein Lauf nur ohne Fremdpakete ist also grün,
während der halbe Bilderkennungs-Teil ungeprüft bleibt — und genau dort ist schon
einmal eine kaputte Meldung durchgerutscht, weil die Zusicherung dazu lokal gar
nicht lief. Dieselbe Regel wie bei den Plattform-Stubs: **was das Echte anders macht
als der Ersatz, wird auf beiden Seiten geprüft.** Wer an `imaging.py` arbeitet,
installiert sie deshalb auch lokal (`pip install opencv-python-headless pillow numpy`)
— sonst sagt ein grüner Lauf hier nichts über die Stellen, um die es gerade geht.

**Die dritte Achse (`pillow`) ist eine echte Installation, keine Vollständigkeit
um der Vollständigkeit willen.** Pillow ohne OpenCV ist der Zustand, in dem
Screenshots und Farbmessung gehen, Template-Vergleich aber nicht — und wer nur
`ohne` und `mit` prüft, sieht genau die Zweige nie, die das eine haben und das
andere nicht.

**Ein grüner Exitcode ist kein grüner Lauf.** `vertrag()` verlangt zusätzlich die
Schlusszeile im Muster `N PASS / 0 FAIL` mit N > 0: eine Suite, die vor ihrem
Abschluss stirbt, meldete sonst Erfolg, weil niemand mehr etwas gedruckt hat.
Dasselbe Muster in der Gegenrichtung ist `--rauch-pflicht` — lokal darf ein
fehlender Browser überspringen, im Browser-Job ist genau das ein Fehler.

**`--mutationen` prüft die Tests, nicht den Code** (`tests/mutationspruefung.py`).
Jeder Fall entfernt in einem frischen Prozess **eine** Sicherung im Arbeits\-
speicher und erwartet, dass ein bestimmter Test darüber rot wird. Das ist die
Gegenprobe, die CLAUDE.md an anderer Stelle von Hand verlangt („Fix entschärfen,
Test muss rot werden") — nur automatisiert und für die Stellen, an denen es
schon einmal schiefging. Nur ein Assertion-Fehler zählt als erkannt: ein
Importfehler, ein übersprungener Test oder ein Timeout beweist nichts.

**Das ist eine gezielte Regressionsprüfung, keine vollständige Mutationsanalyse** —
die Fälle stehen als Liste in `FAELLE` und wachsen mit den Fehlern, die auffallen,
nicht mit dem Code.

`tests/wurzeltests.py` gibt es, weil `unittest discover` die Vertragssuite über
ihren Wrapper ein zweites Mal mitzog: im Gesamtlauf lief sie damit doppelt (und
die Zähler standen zweimal da). `--ohne-vertrag` lässt genau diesen Wrapper weg;
einzeln aufgerufen bleibt er drin, sonst fehlte er dort ganz.

**Ein Einstiegspunkt, mehrere Dateien.** `tests/test_logic.py` war mit über 7.000
Zeilen die grösste Datei des Repos — mehr als jedes Produktivmodul —, und die
durchnummerierten Variablennamen (`_b18`, `_sand18`) waren das Symptom: so
benennt man, wenn der Namensraum voll ist. Neue Sektionen kommen deshalb als
eigenes Modul unter **`tests/vertrag/`**, holen Stubs, Zähler und `check`/`section`
aus `tests/vertrag/_harness.py` und werden am Ende von `test_logic.py` importiert
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
in einer Windows- bzw. X11-Sitzung.

**`tests/alle_tests.py` stellt seinen eigenen stdout auf UTF-8** (`reconfigure`,
`errors="replace"`) und braucht deshalb kein `PYTHONIOENCODING` mehr. Vorher riss
ein einziges Kaestchen aus einem Fortschrittsbalken den ganzen Lauf mit
`UnicodeEncodeError` ab — und zwar *nachdem* die Vertragssuite grün durch war:
die Unterprozesse liefen längst auf UTF-8, nur die Konsole des Runners nicht.
Hinter einer Pipe blieb davon ein Traceback und ein Exitcode, den niemand mehr
las. Ein unbekanntes Zeichen ist ein Darstellungsproblem, kein Testergebnis.

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

**Geprüft wird zweimal, und das zweite Mal ist das wichtige** (`_eingabe_freigeben()`).
Zwischen der ersten Prüfung und dem eigentlichen `send_*` liegen die Humanize-Pausen
— Mikro-Delays und periodische Breaks, also bis zu mehrere Sekunden. Wer in diesem
Fenster CTRL+ALT+H drückt oder das Spielfenster verlässt, bekam den Klick trotzdem:
die Antwort auf „darf ich?" war zu dem Zeitpunkt richtig, zum Zeitpunkt des Klicks
nicht mehr. Stop, Pause und Fokus werden deshalb **nach** allen Wartezeiten erneut
gefragt, und zwar in einer Schleife: während man auf die Rückkehr des Fensters
wartet, kann erneut pausiert werden — erst der gleichzeitig freie Zustand lässt die
Eingabe durch.

**Der Worker räumt auch nach einem Fehler auf.** `sequence_worker()` liegt
vollständig in `try/except/finally`: eine Ausnahme in einem Schritt beendete
früher den Thread, ohne den Schedule-Watcher zu stoppen, das Session-Log zu
schliessen oder `.lauf.json` abzuschliessen — zurück blieb ein Lauf, der laut
Statusdatei noch läuft, und ein Timer-Thread als Geist. Gemeldet wird die
Ausnahme, nicht verschluckt.

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
- **Geteilte Feld-Abfragen** stehen in `editors/_item_felder.py`:
  `frage_prioritaet()` und `frage_bestaetigungsklick()`. Sie standen vier- bzw.
  sechsmal ausgeschrieben da (`items.py`, `learn.py`, `autoscan.py`,
  `item_scan_editor.py`) — die staerkste gemessene Duplikation des Repos, und
  sie war schon auseinandergelaufen: **`get_point_by_id()` sperrt nicht selbst,
  und nur EINE der vier Kopien hielt `state.lock`.** Genau dafuer ist so eine
  Zusammenlegung da; ein Test misst die Sperre. Unterstrich-Modul direkt unter
  `editors/`, wie `_detection_capture.py` — so kommen das `item_editor/`-Paket
  und das daneben liegende `item_scan_editor.py` beide daran, ohne dass eines
  vom anderen abhaengt.

  **Abbruch ist nicht `None`.** Beim Bestaetigungs-Klick ist `None` als Punkt-ID
  ein gueltiges Ergebnis („kein Klick danach"), taugt also nicht zugleich als
  Abbruch-Zeichen — dafuer gibt es `ABBRUCH`.
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
Muster: **der Eintrag der Sequenz ist die Wahrheit, aufgelöst beim Laden und vor jedem
Sequenzlauf.** „Punkte" heisst dabei das Feld `points` in `sequences/<name>/sequence.json`;
die IDs gelten nur innerhalb dieser Sequenz.

| wer verweist | worauf | Feld in der Datei | auflösen |
|---|---|---|---|
| `SequenceStep` | Punkte der Sequenz | `point_id` | `aufloesen()` / `resolve_point_references()` |
| `WaitCondition` | Punkte der Sequenz | `wait_point_id` | dito |
| `ElseConfig` | Punkte der Sequenz | `else_point_id` | dito |
| `SequenceStep.verify_condition` | Punkte der Sequenz | `verify_point_id` | dito |
| `ItemProfile` | Punkte der Sequenz | `confirm_point_id` | `resolve_klick_referenzen()` |
| `BossProfile` | Punkte der Sequenz | `action_point_id` | dito |
| `IconScanConfig` | Punkte der Sequenz | `action_point_id` | dito |
| `ItemScanConfig` | Slots/Items **im Scan selbst** | `slot_names`, `item_names` | `resolve_scan_references()` |

Beim Item-Scan sind `config.slots`/`config.items` die **aufgelösten Arbeitslisten** —
Worker und Editoren nutzen sie unverändert, gespeichert werden sie nicht.

**Eine Koordinate steht im Punkt der Sequenz, sonst nirgends.** Das gilt ausnahmslos für alle
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

### Der Item-Katalog (echte Namen und Kategorien aus der Spiel-API)

**Eine Kategorie heisst „diese Items konkurrieren, nimm nur das beste"**
(`_filter_scan_results`, Modus `all`: `cat = item.category or item.name`, pro
Kategorie gewinnt das kleinste `priority`). Sie von Hand zu tippen hat den
Fehler, den man nicht sehen kann — an einem echten Bestand standen 55 von 56
Items ohne Kategorie da und das eine mit trug `"Wafen"`.

`tools/katalog.py` holt die Namen deshalb von dort, wo sie herkommen:
`query.idleclans.com/api/Configuration/game-data`, dieselbe Quelle, aus der auch
die Wiki gespeist wird — **Scraping braucht es dafür nicht.** Heraus kommen 1006
Items mit Kategorie und Grundwert plus rund 50 Gegnernamen.

**Die Verbindung ist eine Datei, kein Import** — genau wie bei `marktwert.json`:
das Werkzeug weiss nichts vom Autoclicker, der Autoclicker nichts vom Werkzeug.
Gelesen wird in `autoclicker/katalog.py` (Cache am Dateistand, kaputte Einträge
fliegen einzeln raus). Es liegt **nicht** unter `runtime/`, weil vor allem
Editoren es brauchen und `runtime/__init__` den Worker samt `imaging` und
`winapi` nachzöge — dieselbe Überlegung wie bei `befehl.py`.

**Zwei Schalter, und sie beantworten verschiedene Fragen.**
`config.scan_catalog_file` sagt, **wo** die Datei liegt (eine je Spiel, also
programmweit); `ItemScanConfig.use_catalog` sagt, **ob** dieser Scan sie
benutzt. Der zweite gehört zum Scan und nicht in die Config — aus demselben
Grund wie `reverse`: wer zwei Spiele betreibt, hat einen Katalog, der nur für
eines von beiden gilt, und global gesetzt ordnete er das andere still falsch
ein. Im Studio steht er in den Scan-Einstellungen direkt neben „Slots
rückwärts", der Pfad im Einstellungen-Reiter — **samt dem Knopf, der die
Datei holt** (`katalog_holen`, angemeldet über `M.aktion` in
`config_meta.py`). Bis dahin konnte nur `python tools/katalog.py` sie
anlegen: ausgerechnet die Datei, ohne die das LLM frei rät und die
Kategorie leer bleibt, liess sich im Fenster nicht beschaffen. Gerechnet
wird weiter im Werkzeug — **die Brücke ruft `tools/katalog.py`, nie
umgekehrt**, dieselbe Richtung wie beim Bericht-Reiter. Ein gesetzter Pfad
wird dabei aktualisiert und nicht überschrieben, und weder ein Netzfehler
noch eine leere Antwort fassen die vorhandene Datei an.

**Das hängt NICHT am LLM.** Die Kategorie folgt aus dem *Namen* — heisst ein
Item „Citadel Helmet", steht im Katalog „Helm", und ob den Namen ein Mensch
getippt oder ein Modell vorgeschlagen hat, ist gleichgültig. „Aus Katalog
einordnen" steht deshalb bei „Items erkennen" und nicht bei den LLM-Sachen;
`llm_enabled` schaltet nur einen der beiden Wege zum Namen frei.

Vier Entscheidungen, die gemessen sind und nicht geraten:

- **Die Kategorie wird ENG gebildet.** Eine zu weite lässt Klicks still
  ausfallen, ist also der gefährliche Fehler. `EquipmentSlot` trägt die
  Bedeutung schon (ein Helm, ein Schild) und wird übernommen; **Slot 7 ist die
  Ausnahme** — dort liegen 200 Waffen *und* Werkzeuge in derselben Hand, und als
  eine Kategorie hiesse das: aus Spitzhacke, Beil und Bogen wird genau eines
  geklickt. Getrennt wird am letzten Wort des Namens (`Godlike Pickaxe` →
  `Pickaxe`), ebenso bei Slot 0 (`Diamond Ore` → `Ore`).
- **`AssociatedSkill` und `WeaponType` taugen dafür nicht**, und das steht hier,
  damit niemand denselben Weg noch einmal einschlägt: alle `godlike_*` tragen
  Skill 7, Bogen wie Spitzhacke; `WeaponType` ist die *Stufe* (normal → refined
  → … → godlike → otherworldly), nicht die Art. Und `Category` ist unbrauchbar —
  662 von 1006 Items stehen auf `0`.
- **Die Priorität steht NICHT in der Datei**, nur der Wert. Ein Rang gilt immer
  relativ zu den Items *eines* Scans; global vergeben bekäme der beste Bogen
  eines Bestands P49, weil 48 teurere im Katalog stehen, die man gar nicht
  besitzt. `raenge()` vergibt sie dicht innerhalb der bearbeiteten Menge.
- **Ein Timeout beendet die Boss-Erkennung nicht mehr** (`ist_timeout()`, die
  Regel an einer Stelle). Dort stand `break`, und `llm_retry_count` daneben
  wiederholte nur bei „kein Boss erkannt" — ausgerechnet der ERSTE Boss-Scan
  eines Laufs fiel damit aus, denn der trifft ein kaltes Modell. Der zweite
  Versuch bekommt mehr Zeit und zählt **nicht** gegen das Wiederholungs-Budget:
  er beantwortet eine andere Frage. Ein Verbindungsfehler wird dagegen nicht
  wiederholt — da ist niemand, und Wiederholen wäre nur Warten.
- **Die Lampe prüft das MODELL, nicht nur den Server** (`test_connection`). Sie
  nahm `model` entgegen und benutzte es nie: „Verbunden!" stand auch dann da,
  wenn `llm_model` gar nicht geladen war, und jeder Aufruf danach scheiterte.
  Ein erreichbarer Server ohne das eingestellte Modell ist deshalb **kein
  Erfolg** — die Frage ist „kann ich das LLM jetzt benutzen", nicht „antwortet
  da wer". Im Scans-Reiter kam dazu, dass `llm_pruefen()` mit einem rohen
  `urlopen(CONFIG.llm_endpoint)` prüfte, und der ist im Normalfall `None`: die
  Lampe meldete einen `NoneType`-Fehler bei laufendem Server.
- **`llm_reasoning` und `llm_max_tokens` gelten auch für die Benennung.** Sie
  wurden nur im Boss-Scan gelesen; wer sie einschaltete, weil die Benennung
  besser werden soll, änderte nichts. Mit Reasoning wird die Antwort-Länge
  dabei **nicht** auf 32 gekürzt (`_namens_tokens()`) — sonst sind die Tokens
  vor dem Namen im Denken aufgebraucht und `content` bleibt leer.
  `llm_retry_count` bleibt bewusst beim Boss-Scan: die Benennung fragt mit
  Temperatur 0 und bekäme zweimal dieselbe Antwort.
- **Gemessen wird mit `tools/llm_bench.py`, nicht geschätzt.** Ob eine
  Änderung am Prompt, am Bild oder am Modell etwas bringt, sieht man nicht —
  und zweimal hintereinander lag die naheliegende Vermutung daneben: die
  Lernmaske (83 % des Bildes durchsichtig) ist **besser** als ein neutraler
  Grund, und der Ausschnitt aus dem gemerkten Screenshot — mit echtem
  Hintergrund, also so wie das Spiel ihn zeigt — ist **nicht besser** als die
  freigestellte Vorlage. Beides klingt falsch herum und ist gemessen.

  Das Werkzeug nimmt die Items des Scans, deren Namen im Katalog stehen, als
  Goldstandard und wärmt vor der Messung auf. **Das Aufwärmen ist der Punkt:**
  an einem warmen Modell traf `gemma-4-12b-qat` 14 von 14 Vorlagen, an einem
  kalten 9 von 14 — und die fünf Ausfälle waren vier Zeitüberschreitungen plus
  ein Treffer, der beim zweiten Lauf sass. Was hier lange wie eine Grenze des
  Modells aussah, war zum grössten Teil der Kaltstart.
- **Ein Timeout ist nicht dasselbe wie „nicht erkannt".** Beides als `None`
  zu melden war der Fehler: an einem echten Bestand brauchten die **ersten
  vier** Aufrufe je über 120 Sekunden (LM Studio lädt das Modell), die
  folgenden 3,5 — mit `llm_timeout` auf 60 fielen genau die ersten Items stumm
  durch und standen als „ohne Vorschlag" da. `suggest_item_name_grund()` gibt
  deshalb `(Name, Grund)` zurück; der Durchgang wiederholt bei `TIMEOUT`
  **einmal** mit mehr Zeit (der zweite Versuch trifft ein warmes Modell) und
  zählt einen bleibenden Timeout getrennt, mit der Abhilfe in der Meldung.
  Genau dieser Kaltstart ist auch die Antwort auf „im Chat geht es besser":
  dort ist das Modell längst geladen.
- **Zwei Slots mit demselben Gegenstand sind EIN Item, kein zweites.** Der
  Durchgang hängte bei einem belegten Namen einen Zähler an, und ein Inventar
  mit zwei Bögen ergab „Godlike Bow" und „Godlike Bow 2". Drei Folgen, und die
  erste sieht man gar nicht: der Zähler-Name steht **nicht im Katalog**, das
  Item blieb also ohne Kategorie neben seinem eingeordneten Zwilling stehen —
  und ohne Kategorie konkurriert es mit niemandem, wird in Modus `all` also
  immer geklickt. Zweitens lägen sie eingeordnet zu zweit in derselben
  Kategorie, wo eines der beiden nie an die Reihe kommt. Und drittens gehört
  die zweite Vorlage ohnehin zum selben Gegenstand: genau dafür gibt es
  `template_variants`. Erkennt das Modell einen Namen, den es schon gibt, wird
  die Vorlage deshalb **angehängt** und das Doppel entfällt — gesagt wird es in
  der Schlussmeldung, und STRG+Z holt den ganzen Durchgang zurück. Irrt sich
  das Modell, hängt eine fremde Vorlage am Item; sie steht in dessen
  Vorlagenliste und ist dort einzeln lösbar.
- **Eine Kategorie benennt man an ihrer Überschrift um, nicht Item für
  Item** (`scan_kategorie_umbenennen`, Feld im `scan-kategorie-kopf`). Sie ist
  kein eigenes Objekt, sondern ein Feld an jedem Item — Zusammenlegen hiess
  deshalb, jede Maske einzeln anzufassen, und weil der Katalog bewusst ENG
  einordnet, ist Zusammenlegen der Normalfall (an einem echten Bestand hatten
  13 von 23 Kategorien genau ein Item). Leerer Zielname = Kategorie weg,
  leerer Quellname = die Gruppe „ohne Kategorie"; beides ist dieselbe
  Bewegung. Zwei Regeln dazu: die Ränge werden danach **dicht** gemacht (zwei
  P1 in einer Kategorie sind eine Rangfolge, die der Zufall entscheidet), und
  **wer dazukommt, kommt hinten an** — über die ganze Gruppe zu sortieren
  verschöbe die handgesetzten Ränge der Zielgruppe, und wer eine Gruppe in
  eine andere schiebt, sagt damit nichts über deren Reihenfolge.
- **Ein Zähler am Namen darf die Kategorie nicht kosten.** `_katalog_name()`
  probiert erst den vollen Namen und dann den ohne Zähler (`ohne_zaehler()` in
  `utils/parsing.py`, die Umkehrung zu `eindeutiger_name()`). Die Reihenfolge
  ist die Regel: was im Katalog steht, gewinnt — „Slot 1" bleibt „Slot 1".
- **Ein Durchgang, den die Seite treibt — sonst gibt es kein Abbrechen.**
  Sechsundfünfzig Vorlagen sind bei drei Sekunden je Modell-Antwort knapp drei
  Minuten; als EIN Brücken-Aufruf kann das niemand stoppen. Ein Abbruch-Flag
  bräuchte einen zweiten Aufruf **neben** dem laufenden: in pywebview kommt der
  durch, im Rauchtest-Prüfstand nicht (dort hält der Python-Callback den
  Dispatcher) — und ein Abbruch, der nur im Fenster funktioniert, ist keiner.
  Deshalb `scan_autoname_start` → `scan_autoname_schritt` (je Item) →
  `scan_autoname_ende`: der Zustand liegt in der Brücke, die Seite fragt nur
  nach dem nächsten Schritt. Das bringt Abbruch, sichtbaren Fortschritt und
  einen Durchgang, den die Vertragssuite Schritt für Schritt durchspielen kann.
  Drei Regeln dazu: die Config wird beim Start **eingefroren** (sonst liest
  `load_config()` je Item die Datei und schreibt eine Konsolenzeile), der
  Rückgängig-Stand entsteht **einmal und erst beim ersten Treffer**, und ein
  Abbruch **behält, was bis dahin benannt wurde** — es wegzuwerfen hiesse,
  zwanzig Modell-Antworten zu verbrennen, weil man die einundzwanzigste nicht
  mehr abwarten wollte.
- **Am Katalog-Feld steht, was dahinter liegt** (`_katalog_stand()`,
  Momentaufnahme `staende`): Umfang und Zeitpunkt der Datei, in **Ortszeit**,
  und „Datei fehlt“, wenn der Pfad ins Leere zeigt. Der Pfad allein beantwortet
  die Frage nicht, die man an eine geholte Liste hat — ohne Antwort holt man
  sie entweder nie wieder oder bei jedem Zweifel neu.
- **Der vorgeschlagene Name ist ein NAME, kein Dateiname.** Beide
  `autoname`-Wege (Studio und Konsole) drückten ihn durch
  `sanitize_filename()` — die macht Kleinbuchstaben und Unterstriche, aus
  „Godlike Bow" also `godlike_bow`. `Katalog.treffer()` vergleicht aber
  `casefold()` und keine Unterstriche: der Name kam wörtlich aus dem Katalog
  und fand sich darin trotzdem nicht wieder, **Kategorie und Priorität blieben
  also immer aus** — ausgerechnet der halbe Zweck der geschlossenen Auswahl.
  Dafür gibt es `bereinige_itemname()` (`utils/parsing.py`); wo aus dem Namen
  wirklich eine Datei wird (`_apply_item_rename`), läuft `sanitize_filename()`
  eine Ebene tiefer ohnehin noch einmal darüber. Ein Test misst die ganze
  Kette bis zur Kategorie — einer, der nur den Namen prüft, sieht es nicht.
- **Der Prompt der geschlossenen Auswahl ist englisch**, und auch das ist
  gemessen: mit dem deutschen antwortet das Modell deutsch („Bogen", „Schwert")
  — in einer Sprache, in der die Liste gar nicht steht — und nennt die *Art*
  statt des Gegenstands. Mit Liste kommt „Godlike Bow" heraus; an 56 echten
  Vorlagen waren 53 wörtliche Katalognamen, die übrigen drei fängt ein
  Fuzzy-Abgleich (`difflib`, Schwelle 0.85). **Lieber kein Name als ein
  falscher**: ein falscher wird gespeichert und zieht Kategorie und Priorität
  mit sich.

Beim Erweitern: `_katalog_pruefen()` unterscheidet **drei** Gründe (kein Scan
offen / Schalter aus / keine Datei). Sie zusammenzufassen wäre der Fall, in dem
man die Datei sucht, obwohl der Schalter fehlt. Und `_merke()` läuft erst, wenn
wirklich etwas geändert wird (`_katalog_plan` vor `_katalog_uebernehmen`) — ein
zweiter Klick auf denselben Knopf darf keinen Rückgängig-Stand ablegen, sonst
tut STRG+Z einmal scheinbar nichts.

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

.lauf.json                               Laufstatus fuer das Sequenz-Studio (transient)
.aufnahme.json                           letzte 3 Ereignisse der Aufnahme (transient)
.nachklick.json                          Stand der Klick-Runde (transient)
.befehl.json                             Briefkasten Studio → Hauptprozess (transient)
.studio-sequenz.json                     zuletzt geoeffnete/gespeicherte Sequenz (transient)
```

**Es gibt keinen globalen Bestand mehr.** `sequences/points.json`,
`slots/slots.json`, `items/items.json` und die Scan-Ordner im Wurzelverzeichnis
sind ersatzlos entfallen. In `paths.py` stehen davon nur noch die **Ordner**
(`SLOTS_DIR`, `ITEMS_DIR`) — für genau einen Zweck: der Factory-Reset soll einen
solchen Altbestand wegräumen können, falls er auf einer Platte herumliegt. Die
Dateikonstanten selbst (`SLOTS_FILE`, `ITEMS_FILE`, eine für die Punkte) gibt es
nicht mehr. Wer zwei
Spiele betreibt, hat damit nicht mehr die Slots beider in einer Liste — das war
der Grund für den Umzug.

Daraus folgt, was ein Loader braucht: **eine Scan-Datei kennt ihre Besitzerin**
(`owner_sequence`, aus dem Ordnernamen abgeleitet), und ohne Besitzerin lässt sich
kein Scan speichern (`save_item_scan` wirft). `active_templates_dir(state)` ist
deshalb der einzige Weg zu einer Vorlage — ein fest getippter `items/templates/`
zeigt ins Leere.

**Die Punkte stehen im Feld `points` derselben `sequence.json`**, und ihre IDs
gelten nur innerhalb dieser Sequenz. Eine eigene `points.json` gab es einmal; sie
zwang zwei Dateien in Gleichschritt, die getrennt gespeichert wurden — genau der
Fall, an dem ein Punkt fehlte, sobald man ihn brauchte.

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
  heute `sequences/<name>/sequence.json`. Die tragen `schema_version`, die Kette hebt Schritt für
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

`sweep.py` erfasst **alle** JSON-Dateien und geht dafür über die **Besitzeinheiten**,
nicht über Dateitypen: `config.json`, dann je Sequenzordner die `sequence.json`
(mit ihren Punkten), ihre item-/boss-/icon-Scans und ihre Boss-Bibliothek, zuletzt
die beiden Preset-Ordner. Pro Datei zwei Dinge: Migration/Normalisierung **und**
einen Round-Trip durch Loader + Serializer. Der Round-Trip ist die eigentliche
Reinigung — was der Loader nicht kennt, schreibt der Serializer nicht zurück.
Deshalb werden auch Dateitypen ohne jeden Migrationsschritt sauber.
`tools/migrate.py` ist nur noch die CLI über derselben Funktion.

**Hier stand einmal die flache Struktur, und der Durchgang war dadurch still tot.**
Aufgezählt waren `sequences/*.json`, `points.json` und die Scan-Ordner im
Wurzelverzeichnis — nach dem Umzug auf Besitzeinheiten fand der Glob nichts mehr
und die Wurzelordner gab es nicht: von dreizehn Datendateien erfasste
`sammle_dateien()` noch die `config.json`. Auffallen konnte das nicht, denn die
Tests dazu bauten dieselbe flache Struktur im Temp-Ordner auf und blieben grün.
Wer hier etwas ergänzt, geht deshalb vom Sequenzordner aus — und stellt im Test
die Struktur, die die App wirklich schreibt.

**Die Boss-Bibliothek ist eine Liste, kein Scan.** Sie liegt als `bibliothek.json`
zwischen den Boss-Scan-Konfigurationen und braucht deshalb im Durchgang eine
eigene Fallunterscheidung; mit dem Scan-Loader gelesen wäre sie unlesbar und
würde als „übersprungen" gemeldet — ausgerechnet die Datei, die im Betrieb am
häufigsten dazukommt, denn ein Lauf legt dort entdeckte Bosse ab.

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
  `tools/log_report.py`** (ohne Windows, ohne Abhängigkeiten lauffähig) — auf der
  Kommandozeile und im Reiter „Bericht" des Studios, über **dieselbe** Funktion
  (`auswerten()` rechnet und gibt Daten zurück, `bericht()` druckt sie). Geloggt wird
  nicht nur, *was geklickt* wurde, sondern auch, *was gesehen* wurde: `timeout` (welcher
  Schritt hängt — das diagnostisch wertvollste Ereignis), `item_found`, `detected`,
  `verify_ok`/`verify_miss`. Ohne diese Ereignisse konnte der Bericht die eine Frage
  nicht beantworten, für die man ihn aufmacht. Wer eine neue Ereignisart einführt,
  trägt sie in `log_report.py` ein — der Bericht meldet sonst „nicht ausgewertete
  Ereignisarten" und weist selbst darauf hin.
- `autoclicker/import_export.py` — ZIP-Bundle Export/Import + Koordinaten-Remapping (2-Punkt-Affine: scale + offset). Referenzpunkte automatisch aus der Spielfenster-Client-Grösse (`winapi.get_client_rect_by_title`, Manifest-Feld `source_window`), Fallback = manuelle 2 Punkte.

  **Es gibt genau EINEN Import-Weg.** Ein Bündel ist ein ZIP aus vollständigen
  Sequenzordnern (`sequences/<name>/…` plus optional `config.json`), erkennbar am
  Manifest-Feld `layout: "sequence-folders"`. `_import_sequence_bundle()` packt
  sie in einen Temp-Ordner, rechnet dort die Koordinaten um
  (`_remap_sequence_folder`) und verschiebt den fertigen Ordner an seinen Platz —
  danach lädt `load_sequence_file()` ihn wie jede andere Sequenz.

  **Daneben stand bis zum Aufräumen eine zweite, vollständige Implementierung**
  für Bündel aus der Zeit des globalen Bestands: `_Import` als Durchgangs-Zustand,
  `_imp_templates` … `_imp_config` als Stufen, `_IMPORT_MELDUNG` als
  Meldungstabelle, dazu `_remap_point_ids`/`_referenzierte_punkte` für die
  ID-Kollisionen, die es damals geben konnte. Sie war nicht nur Altlast, sondern
  **kaputt**: Vorlagen landeten in `items/templates/`, wo seit dem Umzug keine
  Sequenz mehr nachsieht, und `_imp_items` schrieb über `save_global_items()`,
  das ohne aktiven Item-Scan folgenlos zurückkehrt. Ein Import, der „hat
  geklappt" meldet und nichts Brauchbares hinterlässt, ist schlechter als eine
  Absage — deshalb wird ein Bündel ohne `layout`-Feld heute abgelehnt, mit dem
  Hinweis, die Sequenz im Studio neu zu bauen. Das Löschen nahm 347 Zeilen und
  22 Importe mit.

  **Punkt-IDs sind sequenzlokal**, und damit ist die ganze ID-Zuordnung
  entfallen: zwei Sequenzen dürfen beide einen Punkt #7 haben, das ist kein
  Konflikt, sondern sind zwei Punkte. Kollidieren können nur noch die
  Ordner*namen*, und dort weicht `merge=True` auf `<name>_2` aus.

  **`_ImportTransaction` sichert weiterhin vor der ersten Änderung** und rollt
  bei jedem Fehler zurück. Gesichert wird `config.json` und **jede** Datei unter
  `sequences/` — nicht nur die JSONs, denn ein Ordner-Bündel ersetzt ganze
  Sequenzordner samt Vorlagen und gemerkten Bildern.

  **Ein Bündel ist eine fremde Datei, also wird jeder Pfad darin geprüft**
  (`_sicherer_bundle_pfad` + eine `resolve()`-Gegenprobe in
  `_import_sequence_bundle`). `PurePosixPath` allein reicht nicht: unter Windows
  ist `sequences\..\..\x` **ein** Segment und damit weder absolut noch mit `..`
  in `parts` — der Backslash, der Doppelpunkt (`C:`) und das Null-Byte werden
  deshalb am rohen Namen geprüft, bevor überhaupt ein Pfad daraus wird. Und weil
  eine Namensprüfung immer nur so gut ist wie die Liste der Tricks, die man
  kennt, muss das Ziel danach zusätzlich **messbar** unterhalb des Temp-Ordners
  liegen; sonst fliegt der Import mit einer Meldung, statt irgendwohin zu
  schreiben.

  **Die Boss-Bibliothek wird beim Umrechnen übersprungen.** Sie enthält Profile
  mit Punkt-IDs und keine eigenen Regionen — ihre Punkte stehen in der
  `sequence.json` und werden dort genau einmal umgerechnet. Mitgerechnet wäre
  jeder Bibliotheks-Klick zweimal verschoben.

- `autoclicker/utils/` — Hilfsfunktionen: `console.py` (ANSI, Tags), `io.py` (safe_input, interactive_select), `parsing.py` (Zeit, Dateinamen).
- `autoclicker/persistence/` — JSON-Persistenz: `migration.py` (Schema-Versionierung, s.o.), `paths.py` (Pfade), `serialization.py` (Dataclass↔Dict; `_*_to_dict`/`_*_from_dict` sind die EINE Quelle der Wahrheit fürs Dateiformat — von Savern UND `import_export.py` genutzt, damit beide dasselbe schreiben), `_scan_store.py` (geteiltes Skelett für item/boss/icon-Scans: ensure_dir/write/list/load_all + `LOAD_EXCEPTIONS`), `sequences.py`, `item_scans.py`, `boss_scans.py`, `icon_scans.py`, `globals.py`, `presets.py`.

  **Ein Saver sagt, ob er gespeichert hat.** `write_scan()` und die `save_*_scan()`
  darüber geben `bool` zurück statt `None`: ein `IOError` wurde zwar gemeldet, aber
  der Aufrufer lief weiter, als sei nichts gewesen — im Studio hiess das „Gespeichert"
  über einer Datei, die nicht geschrieben wurde. Wer speichert, prüft den Rückgabewert
  und sammelt die Fehlschläge (`_erkennung_speichern()` macht es vor). Ein `try/except`
  allein reicht nicht: die Ausnahme wird eine Ebene tiefer schon gefangen.
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
  - `bridge_bericht.py`: Session-Logs und Ertrag im Reiter „Bericht".
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
| `autoclicker/sequence_studio.py` (`handle_sequence_studio`, `handle_scan_studio`) | `editors/sequence_studio/` (pywebview) | `sequences/<name>/` (sequence.json, item_scans/, boss_scans/, icon_scans/, templates/), `config.json` |

**Der Scans-Reiter merkt, wenn der Hauptprozess seine Dateien anfasst.** Er las
`slots.json`, `items.json` und `item_scans/` genau einmal je Sitzung — und ein
Lauf mit `learn_unknown` legt in derselben Zeit neue Items an und **speichert**
sie. Die Konsole meldete „gelernt", im Reiter waren sie nicht da, und man sucht
den Fehler beim Lernen statt bei der Ansicht. `_platte_stand()` merkt sich die
Änderungszeiten beim Laden, `_platte_fremd()` vergleicht sie bei jeder
Momentaufnahme, und die Ansicht bietet „Neu laden" an. Zwei Regeln dazu:

- **Kein eigener Schreibvorgang zählt mit** (`_platte_nachziehen()`). Für das
  Speichern war das von Anfang an klar; für zwei andere nicht, und dort log der
  Hinweis: das gemerkte Bild liegt unter `sequences/<name>/bilder/`, und das **Anlegen
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

**Acht Ansichten, ein Fenster** (Umschaltleiste im Kopf). Welche offen ist, ist
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
| Bericht | was die vergangenen Läufe hinterlassen haben | `bericht_daten()` |
| Einstellungen | `config.json` bearbeiten | `config_lesen()` / `config_schreiben()` |

**Welche Sequenz offen ist, gilt in JEDEM Reiter — also steht die Auswahl
überall.** Sie war früher zusammen mit dem Speichern-Knopf ausgeblendet, und das
verwechselte zwei Dinge: die Falle sind zwei **Speichern**-Knöpfe für zwei
Dateien in einer Leiste, nicht die Auswahl. Für einen Wechsel musste man
deshalb erst in den Editor zurück — ausgerechnet aus den Reitern, die am
stärksten an der Sequenz hängen (Scans, Teilen und Werkzeuge arbeiten alle in
`sequences/<name>/`). Nebenbei behält der Kopf damit in jedem Reiter dieselbe
Gestalt, statt beim Umschalten drei Gruppen zu verlieren.

Zwei Dinge hängen daran, und ohne sie wäre es ein Rückschritt:

- **Der offene Reiter folgt dem Wechsel** (`ruf()` ruft danach `setzeAnsicht`
  erneut). Scans, Teilen und Werkzeuge hängen an eigenem Zustand (`SC`, `T`,
  `W`), den `zeichne()` nicht anfasst — sonst stünden dort die Slots, Zahlen und
  Punkte der **vorigen** Sequenz unter dem Namen der neuen. Nicht bei einer
  Rückfrage (`S.frage`): dann ist noch gar nichts geladen.
- **Offene Scan-Änderungen werden vorher weggeschrieben** (`sequenzWechseln()`).
  Die Rückfrage nach ungespeicherten Änderungen kennt nur die Sequenz
  (`_dirty`); die Scans haben ihren eigenen Merker (`_scan_dirty`), und `laden`
  wirft sie über `_scan_init()` wortlos weg. Gefragt wird trotzdem nicht — der
  Reiter speichert ohnehin von selbst, ein Verwerfen-Modell gibt es dort gar
  nicht. Scheitert das Schreiben, bleibt es beim bisherigen Stand.

Speichern und Starten bleiben dagegen bei der Sequenz: sie meinen die Sequenz,
nicht den Reiter.

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

**Gelöscht wird dort auch — mit Rückfrage und nach `backups/`.** Eine Sequenz ist
eine Besitzeinheit: Punkte stehen in ihrer `sequence.json`, Scans, Vorlagen und
gemerkte Bildschirme liegen daneben. Nur die JSON zu entfernen liesse einen Ordner
voller Vorlagen zurück, den nie wieder jemand ansieht — also geht der **ganze
Ordner**, und die Rückfrage nennt, was daran hängt („samt 3 Item-Scans, 12
Vorlagen"). Ohne diese Angabe löscht man einen Nachmittag Arbeit an Item-Vorlagen
mit, weil man „nur die Sequenz" wegräumen wollte.

**Verschoben statt entfernt** (`sequenz_loeschen()`): der Ordner landet unter
`backups/sequences/<ordner>/`, ein vorhandener Stand dort bekommt einen Zeitstempel
statt überschrieben zu werden. Dieselbe Regel wie beim Start-Durchgang, und aus
demselben Grund — samt der gespiegelten Struktur, also unter dem **Ordner**namen.

**Und der Ordner heisst nicht wie die Sequenz.** `save_data()` legt ihn unter
`sanitize_filename(name)` an: aus „Raid" wird `sequences/raid`, aus „Mein Lauf"
wird `mein_lauf`. Der angezeigte Name steht **in** der Datei — wer ihn an
`sequences/` hängt, greift ins Leere, und wenn zufällig ein Ordner so heisst,
daneben: der wanderte nach `backups/`, während die echte Sequenz stehenblieb und
das Löschen „hat geklappt" meldete. Gesucht wird deshalb wie beim Laden über
`list_available_sequences()`, mit dem Ordnernamen als zweitem Weg (eine defekte
Datei steht dort nicht, und genau die will man am häufigsten löschen).
`_sequenz_ordner()` ist die eine Stelle dafür; sie schliesst nebenbei den Pfad,
denn `name` kommt aus dem Fenster.

**Auf Windows war das unsichtbar.** Das Dateisystem ist dort nicht
gross-/kleinschreibungsempfindlich, also *ist* `sequences/Raid` derselbe Ordner
wie `sequences/raid` — die CI-Matrix stand mit drei grünen Windows-Jobs neben
drei roten Ubuntu-Jobs. Dieselbe Klasse Falle wie bei den Plattform-Stubs: wer
Pfade nur auf einer Seite prüft, prüft die Hälfte.

Zwei Absagen gehören dazu: **die offene Sequenz nicht** (der Editor hält sie im
Speicher — der nächste Druck auf Speichern legte den Ordner wieder an, und das
Löschen sähe aus, als hätte es nicht gewirkt) und **nicht während eines Laufs**
(der Worker liest genau aus diesen Ordnern). Eine *defekte* Datei lässt sich
dagegen sehr wohl löschen — sie ist der häufigste Grund, es zu wollen, und
deshalb bekommt auch sie ihren Umfang in der Übersicht.

**Die Mehrzahl steht in den Daten, nicht in der Ansicht** (`_UMFANG` trägt beide
Formen). Ein angehängtes „n" ergab „2× Item-Scann" und „3× gemerkter
Bildschirmn" — bei drei von fünf Wörtern falsch. Aufgefallen ist es erst am
gerenderten Dialog; deutsche Mehrzahl ist keine Regel für eine Zeile JavaScript.

Zwei Eigenschaften der Übersicht, die man kennen muss: sie sieht den Ordner **selbst**
durch statt `list_available_sequences()` zu fragen (die überspringt unlesbare Dateien
stillschweigend — richtig für ein Menü, falsch für eine Übersicht: genau dann sucht
man die Datei im Explorer), und geöffnet wird über den vorhandenen `laden`-Befehl,
damit die Rückfrage bei ungespeicherten Änderungen greift.

**Der Scans-Reiter arbeitet auf einem eingefrorenen Screenshot** (`ScanTeil`-
Fassade in `scans.py`, Aufnahme in `scan_capture.py`, Zustands-/Interaktionslogik
in den übrigen `scan_*.py`-Modulen). Slots werden dort aufgezogen, wo sie im
Spiel liegen; Koordinaten tippt niemand. Er bearbeitet `sequences/<name>/item_scans/<n>.json` — Slots und Items stehen
darin, es gibt keine globalen Listen daneben — also wieder andere Dateien
als der Editor, weshalb auch hier das Sequenz-**Speichern** im Kopf verschwindet
und ein eigener Speichern-Knopf rechts steht. Die **Auswahl** bleibt (s. u.).

**Der Item-Scan ist das Übergeordnete, nicht die Auswahl.** Wer mehrere Spiele
betreibt, hat alle Slots und Items aller Spiele in einer Liste — und keiner davon
gehört sichtbar irgendwohin. Deshalb gibt es `scan_offen` **neben**
`scan_art`/`scan_name`: der offene Scan ist der Zusammenhang, die Auswahl ist das
Ding, das man gerade bearbeitet. Beides an einer Variable hiesse, dass ein Klick
auf einen Slot den Zusammenhang verliert (so war es zuerst gebaut). Am offenen
Scan hängen: was im Bild gezeichnet wird, welche Items `scan_erkennen()`
prüft und welche Toleranz dabei gilt.

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

**Jeder Scan merkt sich seinen Bildschirm.** `sequences/<name>/bilder/<scan>.png`, beim
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

- **Scan, Slot und Item sind Masken — dieselbe Bauform** (`maskeBauen()`, dazu
  `scanScanMaske` / `scanSlotMaske` / `scanItemMaske`). Sie unterscheiden sich
  in dem, was drinsteht, nicht darin, wie man sie anfasst: Haken (gehört zu
  diesem Scan), Vorschau bzw. Farbe, Name, darunter die zweite Zeile — beim
  Item Kategorie und Priorität, bei Slot und Scan der Stand.

  Vorher war ein Item eine Maske und ein Slot eine Knopfzeile mit vier
  Zahlenfeldern in einer anderen Spalte: **dieselbe Frage („wie benenne ich das
  um") hatte zwei Antworten.** Der Name steht seither in genau einer — dieselbe
  Auflösung wie beim Klick-Block im Sequenz-Editor.

- **Der ganze Listen-Block steht RECHTS: Reiter, Filter und Masken zusammen**
  (`scanListenBlock()`, gerufen aus `scanInspektor()`). Der Schnitt geht nach
  Verantwortung, nicht nach Scan-Art: **links, wie der Scan entsteht** (Auswahl,
  Assistent, Modus-Kacheln), **rechts, was drin ist.**

  Es gab einen Zwischenzustand, in dem nur die Item-Masken rechts standen und
  Reiter und Filter links blieben. Der kostete zweierlei: beim Umschalten
  schrumpfte links ein Abschnitt zusammen, während rechts etwas erschien — die
  linke Spalte **änderte bei jedem Reiterwechsel ihre Grösse** —, und ein
  Hinweistext musste erklären, wohin der Inhalt verschwunden ist. Beides ist mit
  dem Umzug weg; `#ab-listen` und `nur-reiter` sind ersatzlos gelöscht.

  Als **Masken** kommen dabei nur die Item-Listen (`scanMaskenRechts()`): dort
  stehen Dutzende gleichartiger Dinge nebeneinander. Ein Boss- oder Icon-Scan
  ist **eines** — Region, Erkennung, Aktion —, das trägt keine Maske; seine
  Liste steht am selben Ort, und was zum Gewählten gehört, darunter (`.erk-insp`,
  durch eine Linie abgesetzt).

  Dazu gehört, dass **die Spalte den Platz für ihre Bildlaufleiste reserviert**
  (`scrollbar-gutter: stable`). Ohne das ändert jede Liste, die eine Zeile länger
  wird, die Innenbreite um rund 15 px — dasselbe Springen, nur feiner.

- **Was man selten ändert, klappt IN der Maske auf** (`scanItemDetails()`,
  `scanSlotDetails()`, `scanScanDetails()`) — und zwar nur beim gewählten, denn
  sechzig aufgeklappte Blöcke wären keine Liste mehr. In eine eigene Spalte
  gelegt hiesse es, beim Arbeiten an einem Ding zwischen zwei Orten hin und her
  zu sehen; die Maske trägt seine Identität ohnehin schon. **Eine** Funktion je
  Art baut den Block.

  **Hier lag die Lücke, durch die ein Scan gar nicht mehr zu löschen war**: ein
  Klick auf ihn öffnete ihn, das Öffnen schaltete auf die Item-Liste um, und
  seine Einstellungen standen in einer Spalte, die man damit gerade verlassen
  hatte. Deshalb bleibt der Reiter stehen, wenn man einen Scan **aus der
  Scan-Liste heraus** öffnet (`scanReiterNachOeffnen`).

- **Sortiert wird beim Laden und auf Knopfdruck, nicht beim Tippen**
  (`scanOrdnung`, Knopf „↕ Sortieren"). Sortierte sich die Liste nach *jeder*
  Änderung neu, springt genau die Zeile weg, an der man gerade arbeitet: man
  tippt eine 2, die Zeile rutscht drei Plätze, und der nächste TAB landet im
  Feld eines anderen Items. Gemerkt wird deshalb die Reihenfolge des letzten
  Sortierens; aufgefrischt beim Laden (`scan_neu_laden`, Lernen,
  `scan_oeffnen`), beim Reiterwechsel und durch den Knopf.

  **Kein Feld eines Items verschiebt seine Zeile** — auch die Kategorie nicht.
  Sie war der erste Sortierschlüssel und damit das letzte Feld, das noch
  sprang; eingefroren wird sie deshalb zusammen mit dem Rang
  (`scanOrdnungGruppe()`), und die Gruppenüberschriften kommen aus dieser
  Momentaufnahme statt aus dem aktuellen Wert. Sonst risse ein gerade
  geändertes Item eine zweite Überschrift mitten in die Liste. Wohin es beim
  nächsten Sortieren wandert, sagt seine Zustandszeile („→ Helme").

  **Umbenennen ändert den Namen, nicht den Rang** (`scanOrdnungUmbenennen()`).
  Der Merkposten hängt am Namen — ohne das Nachziehen galt ein gerade
  umbenanntes Item als neu und rutschte ans Ende seiner Gruppe, und genau beim
  Namen tippt man. Eingetragen werden beide Namen: lehnt die Brücke den neuen
  ab, behält das Item trotzdem seinen Platz.

- **Der Kopf der rechten Spalte klebt oben** (`.scan-kopf`, `position: sticky`).
  Dort stehen Speichern, Rückgängig, „Items erkennen", die Reiterleiste und die
  Filterzeile — bei sechzig Masken war all das nach drei Umdrehungen weg, und
  mit ihm der Weg in eine andere Liste. Er braucht einen eigenen Hintergrund,
  sonst scrollen die Masken sichtbar dahinter durch. Die Reiterleiste nimmt die
  **ganze** Breite (`.tabs.breit`, gleiche Spalten): drei Reiter links
  zusammengedrängt liessen zwei Drittel der Leiste leer, und gleiche Spalten
  verhindern, dass die Zahlen dahinter („Slots 72/85") die Aufteilung bei jedem
  Filterwechsel verschieben.

  **Der Kopf ist eine Spalte, kein Fliesstext.** Jedes Bedienelement nimmt die
  volle Breite (`.scan-filter` als einspaltiges Raster); nur der Schalter dehnt
  sich nicht, denn er ist Text mit Kästchen davor. Vorher stand „alle dazu" als
  kurzer Stummel neben dem Schalter, „Sortieren" als noch kürzerer darunter und
  die Klappliste dazwischen über die ganze Breite — drei verschiedene Breiten
  untereinander lesen sich wie drei Rangstufen, obwohl es dreimal dasselbe ist.
  Wo zwei Knöpfe eine Zeile teilen (`.knopfpaar`), bekommen sie **gleiche**
  Spalten: „Items erkennen" nahm sonst den Rest der Zeile und „Rückgängig" nur
  seine Textbreite, und weil dessen Beschriftung den letzten Schritt nennt,
  kippte das Verhältnis bei jeder Änderung.

  **Für „nebeneinander" gibt es genau zwei Klassen**, und sie gelten überall:
  `btn breit` ist EIN Knopf über die volle Breite, `knopfpaar` sind mehrere zu
  gleichen Teilen. Vorher stand an jeder Zeile eine eigene Mischung aus
  `wachse`, Abstandhaltern und Textbreite — dieselbe Frage, ein Dutzend
  Antworten. Ein Test hält fest, dass kein `btn wachse` mehr existiert.

  Gleiche Spalten dürfen dabei nichts kosten, was man lesen muss: bei fester
  Spaltenzahl schnitten drei Knöpfe in 290 px die Beschriftung ab („Item ler…").
  `auto-fit` bricht deshalb um, sobald eine Spalte unter 118 px fiele — ein
  abgeschnittenes Wort ist schlimmer als eine zweite Zeile.

- **Ein Knopf sagt, was er TUT — nicht, worauf er sich bezieht.** Das
  Rückgängig trug den letzten Schritt im Namen („↶ 'Bogen Zeus': Priorität"):
  die genauere Auskunft und die schlechtere Beschriftung. Sie wurde zweizeilig,
  wechselte bei jeder Änderung ihre Länge, und was der Knopf tut, musste man
  aus ihr heraussuchen. Er heisst jetzt „↶ Zurück"; was zurückgenommen wird,
  liest im Tooltip, wer nachfragt, und *dass* es etwas gibt, sagt der aktive
  Zustand. Dieselbe Trennung wie sonst zwischen Text und ⓘ.
- **Ein Attribut, das allein durch sein DASEIN wirkt, braucht einen Boolean.**
  `el()` setzte jeden nicht-falsy Wert per `setAttribute` — und
  `disabled="0"` sperrt genauso wie `disabled="1"`. Im Werkzeug „Punkte
  verwalten" stand `disabled: punkt.verwendungen.length`: bei 0 Verwendungen
  (also genau dann, wenn man löschen DARF) war der Knopf gesperrt, bei 3
  ebenso — er war **immer** tot, in einem Werkzeug, das „sicher löschen"
  verspricht. `NUR_DASEIN` in `el()` lässt solche Attribute bei falsy Werten
  jetzt weg; die 27 anderen Aufrufstellen übergaben ohnehin schon Booleans.
- **Ein verzögerter Schreiber darf keine frischere Meldung begraben.**
  `briefkastenNachfassen()` meldet nach zwei Sekunden „Kein Hauptprozess
  erreichbar" — und überschrieb dabei, was der Nutzer inzwischen getan hatte.
  Es merkt sich deshalb `statusStand` und schweigt, wenn seither jemand anders
  etwas gemeldet hat.
- **Wer die Mitte neu zeichnet, zeichnet auch die rechte Spalte.** `wzPruefen()`
  rief nur `wzMitteZeichnen()`: der Bericht stand in der Mitte, rechts blieb
  „Noch nichts geprüft." — ausgerechnet die Spalte, die auflistet, WAS geprüft
  wurde, und ohne die „Alles in Ordnung" eine Behauptung ist. Jeder andere
  Werkzeug-Befehl geht über `rufWerkzeug` → `zeichneWerkzeuge()` und zeichnet
  alle drei Spalten; dieser eine ging seinen eigenen Weg, weil er `frage()`
  direkt ruft.
- **Ein ⓘ hängt an einer Beschriftung, nicht im Leeren.** `wzInfo()` im
  Werkzeuge-Reiter warf seinen Titel ins `title`-Attribut; sichtbar blieb ein
  nackter Kreis in der Fläche — an zwölf Stellen, in „prüfen" und „kalibrieren"
  mitten im Nichts, wo er wie ein Rest aussah. Die Beschriftung ist es, die
  sagt, worüber nachzufragen sich lohnt; sie kostet eine Zeile kleiner Schrift
  und nicht die Breite, um die es beim Kompakt-Umbau ging (ein Kasten wäre das
  gewesen).
- **Zustandsklassen bekommen ein Präfix — auch dort, wo es niemand sieht.** Der
  Hinweiskasten hiess `wz-info-kompakt info`, und `.info` ist der runde
  ⓘ-Knopf: 13 px, `flex:none`, zentriert. Der Kasten erbte dessen Gestalt.
  Solange er NUR das ⓘ enthielt, sahen 13 px richtig aus — mit einer
  Beschriftung darin stand der Text mittig über den Kasten hinaus, nach links
  aus dem Fenster heraus. Dieselbe Falle wie einmal beim Status, nur jahrelang
  unsichtbar. Das `art`-Argument ist dabei **ersatzlos gelöscht** statt auf
  `art-…` umgeschrieben: zwölf Aufrufe, kein einziger mit drittem Argument, und
  in der CSS-Datei keine einzige Variante — ein Präfix hätte einen toten Zweig
  gepflegt.
- **Eine Klasse, die das Layout setzt, darf keine andere überschreiben.**
  `.wz-aktion{display:flex}` steht später im Stylesheet als `.gitter2`/
  `.gitter3` und gewann bei gleicher Spezifität: die beiden Stellen, die
  ausdrücklich `wz-aktion gitter2` bzw. `gitter3 wz-aktion` schreiben, bekamen
  nie ihre gleichen Spalten, und die Knopfreihen standen in Textbreite da. Die
  Klasse trägt jetzt nur noch ihren Abstand; wer eine Reihe will, schreibt
  `reihe` dazu.
- **Ein Kästchen heisst „gehört dazu", nicht „ist gewählt".** Die Blockkarten
  trugen eines für die Auswahl — es sagte dasselbe wie der Amber-Ring um die
  Karte, nur kleiner, und konnte nichts, was STRG+Klick nicht auch kann („dazu"
  ist derselbe Befehl). Schlimmer war die Zweideutigkeit über den ganzen Baum:
  im Scans-Reiter bedeutet ein Kästchen „gehört zu diesem Scan" bzw. „ist an",
  hier bedeutete es „ist gerade markiert" — und eine gewählte Karte trug beide
  Zeichen gleichzeitig. Das Kästchen ist ersatzlos weg; **der Zustand wird
  ringsum markiert** (dieselbe Regel wie überall sonst), und was die Gesten
  sind, steht am Titel der Karte statt in einem Bedienelement, das man erst
  anfassen muss, um es zu verstehen.
- **Ein „×" am ENDE einer Beschriftung heisst „wegmachen".** Im Phasenkopf
  hiess der Skalieren-Knopf „Wartezeiten ×" und stand zwischen Wiederholungen
  und Startzeit — daneben das „×", das die Wiederholungen beschriftet. Zwei
  gleiche Zeichen in einer Zeile, eines als Vorsatz („mal N") und eines am
  Wortende, wo jede andere Oberfläche ein Schliesskreuz hat: der Kopf sah aus,
  als liesse sich dort etwas entfernen. Das Multiplikationszeichen darf
  beschriften, aber nur **vor** dem Wert und nur einmal je Zeile; ein Knopf
  nennt seine Tätigkeit („Zeiten skalieren …", Auslassungspunkte für „fragt
  noch nach").
- **Eigenschaften und Sammel-Aktionen stehen nicht in derselben Zeile.** Im
  Phasenkopf beschreiben „Läufe je Zyklus" und „Start ab Uhrzeit" die Phase;
  „Alle Blöcke wählen" und „Zeiten skalieren" ändern jeden Block darin.
  Dazwischen gemischt liest sich das Skalieren wie eine dritte Eigenschaft. Die
  Sammel-Aktionen stehen deshalb unten beieinander als `knopfpaar` — und nur,
  wenn die Phase überhaupt Blöcke hat.
- **Untereinander stehende Zeilen liegen auf DEMSELBEN Raster.** Der Phasenkopf
  hatte oben ein `flex` mit fest getippten 70 und 74 px und darunter ein
  `knopfpaar`: die Eigenschaften-Zeile endete bei 470 px, die Knopfzeile bei
  584 — und die beiden Felder waren *fast* gleich breit, nah genug, dass es wie
  ein Rundungsfehler aussieht statt wie Absicht. Beide Zeilen benutzen jetzt
  dieselbe `auto-fit`-Regel (min. 118 px), also gleiche Spalten, gleiche Kanten
  und derselbe Umbruchpunkt. Gemessen wird so etwas an den **Zellen**, nicht am
  Zeilen-Container: der ist als Kind einer Spalten-Flexbox ohnehin immer so
  breit wie der Kopf, und ein Test darauf bleibt grün, während der Inhalt auf
  halber Strecke aufhört.
- **Ein Feld auf halber Breite braucht eine Beschriftung, keinen Tooltip.**
  Solange die Zeile eng war, mussten „× 1" und ein leeres „HH:MM" sich selbst
  erklären — das „×" war der Ersatz für das fehlende Wort. Mit der halben
  Spalte ist Platz für „Läufe je Zyklus" und „Start ab Uhrzeit", und damit
  entfällt das „×" ersatzlos: es sagt nichts mehr, was nicht dasteht. Nebenbei
  sind die beiden Eingabefelder dadurch exakt gleich breit — ein Vorsatz vor
  nur einem der beiden hätte sie um seine eigene Breite gegeneinander
  verschoben.
- **Auch ein Schalter bekommt seine Fläche** (`.kachel`). Aufgefallen ist das
  an einem Filter, der als loser Text zwischen lauter Kacheln stand —
  Reiterleiste darüber, Knopfreihe darunter — und sich las, als gehöre er nicht
  dazu. Den Filter gibt es nicht mehr (s. u.), die Regel schon.
- **Ein Knopf sieht aus wie ein Knopf.** `.btn.still` hiess einmal „ohne
  Rahmen" (`border-color: transparent`) — damit war „+ neuer Scan" oder „alle
  dazu" ein Stück Text, dem man nicht ansieht, dass man es anklicken kann. Der
  Ton bleibt zurückhaltend (kein Hintergrund, gedämpfte Schrift), die **Fläche**
  ist da.

- **Die Kachel zeigt eine stabile ID, keine Stelle im Scan.** Der erste Anlauf
  zeigte dort `nummer` — die Stelle in `slot_names`, mit der Begründung „das
  ist die Zahl, die man an einer Nummer sucht: wann ist dieser Slot dran".
  Das stimmt, ist aber genau deshalb die falsche Zahl für EINE Kachel: die
  Stelle ändert sich mit Absicht, sobald ein Slot ab- und wieder angeschaltet
  wird (`scan_mitglied()` entfernt ihn aus `slot_names` und hängt ihn beim
  Wiedereinschalten ans Ende an) — eine Kennung, die beim Ausschalten verloren
  geht, ist für eine ID unbrauchbar. `ItemSlot` trägt deshalb ein eigenes,
  stabiles `id`-Feld (`models.py`), vergeben von `_naechste_slot_id()` bei der
  Entstehung — dieselbe Rechnung wie bei `ClickPoint`/`PalettePoint`
  (`max(vorhandene) + 1`), aber **keine Referenz**: der Name bleibt der
  Schlüssel in `slot_names`/`item_names`, die ID ist reine Anzeige.

  **Zwei Zahlen bleiben nötig, weil sie zwei verschiedene Fragen beantworten.**
  `nummer`/`lauf`/`gesamt` stehen weiterhin in der Momentaufnahme — sie
  entscheiden die Vorsortierung („in welcher Reihenfolge lernt/scannt das hier")
  und stehen im Tooltip der Kachel; angezeigt wird aber `id`. Wer nicht zum
  offenen Scan gehört, hat keine `nummer` (dort gibt es keine Stelle), aber
  jeder Slot hat eine `id` — unabhängig davon, ob er gerade irgendeinem Scan
  angehört.

  **Für Altbestand ohne das Feld gibt es keine Migration, sondern einen
  Backfill beim ersten Laden** (`_slot_ids_vergeben()`, aufgerufen aus
  `_scan_laden()`): jeder Slot mit `id == 0` bekommt eine frische, in stabiler
  Reihenfolge (Name, nicht Dict-Zufall) — und der Scan gilt danach als
  ungespeichert, denn ohne einen Schreibzugriff würde bei jedem Start neu
  gewürfelt, und die gerade zugesicherte Stabilität wäre eine Lüge. Genau der
  Fall, für den „Neue Formatänderungen brauchen keinen Migrationsschritt" da
  ist: Default `0` in der Dataclass, `data.get("id", 0)` im Loader, fertig.

  **Stabil heisst dabei natürlich sortiert, nicht Zeichen für Zeichen**
  (`_natuerlich()` in `scan_state.py`). Ein reiner String-Vergleich stellt
  „Slot 10" zwischen „Slot 1" und „Slot 2" — bei sechzig durchnummerierten
  Slots bekam „Slot 2" damit die ID 12 und „Slot 3" die 23. Die IDs waren
  stabil und trotzdem unbrauchbar: eine Kennung, die in Sprüngen dasteht,
  liest niemand als Kennung, sondern als Fehler. Dieselbe Regel wie bei
  `nachNamen()` in der Ansicht, nur eine Ebene tiefer — und sie muss an beiden
  Stellen stehen, denn die Vergabe entscheidet die Zahl, die Sortierung nur
  die Zeile.

  **Sie steht unter dem Schalter, in der ersten Spalte** (`.scan-marke`), nicht
  vor dem Namensfeld: dort nahm sie ihm die Breite, liess die Namen ohne ID
  an einer anderen Kante beginnen — und beim Bearbeiten schob sich das Feld
  darüber. In der ersten Spalte steht sie ausserhalb von allem, was sich beim
  Tippen ändert.

  Gezeichnet wird sie als `.zahl` — dieselbe Kachel wie überall sonst, keine
  eigene daneben —, und die **Grösse** in der Zustandszeile ebenso: sie ist ein
  gemessener Wert, kein Satz. Was daneben steht („Item 1", „unbekannt",
  „→ Helme"), ist eine Aussage und bleibt Text. Beide Kacheln stehen auf einer
  Höhe, weil die erste Spalte `align-self: stretch` trägt und ihren Inhalt
  auseinanderzieht; ein Rauchtest misst die Unterkanten.

  **Die ID-Kachel hat eine feste Mindestbreite** (`.scan-marke .zahl`). Ohne
  sie schob sich „#3" weniger als „#55" und „#123" nochmal anders — jede
  Ziffernzahl saugte sich auf ihre eigene Textbreite zusammen, und in einer
  Liste mit gemischten ein-, zwei- und dreistelligen IDs sprang die Kachel bei
  jeder Zeile ein Stück. `min-width: 34px` (Platz für „#999") und
  `text-align: center` halten sie an derselben Stelle, unabhängig davon, wie
  viele Ziffern eine ID gerade hat.

  **Die Vorschau daneben (Hintergrundfarbe bzw. Item-Thumbnail) ist ein
  Quadrat mit FESTER Kantenlänge** (56 × 56 px) — kein Rechteck und nichts,
  was mitwächst. Feste 30 px Höhe liess sie neben einer zweizeiligen Spalte
  (Name + Zustandszeile) wie einen Briefmarken-Rest wirken; nur die Höhe zu
  stretchen machte daraus einen schmalen Turm.

  Mitwachsen zu lassen war der zweite Anlauf und ebenfalls falsch: eine
  Item-Maske hat DREI Zeilen (Name, Kategorie + Priorität, Zustand), eine
  Slot-Maske zwei — dieselbe Vorschau wurde damit beim Item 76 px gross und
  beim Slot 52. Zwei Grössen für dieselbe Sache, und die grössere frass die
  halbe Maskenbreite. Ein festes Mass ist die Antwort auf beides: weder das
  Bildmass des Templates noch der Inhalt der Nachbarfelder darf die Vorschau
  oder die gemeinsame Rasterspalte aufziehen.

  **Sortiert wird nach der ID — also nach der Zahl, die auch dasteht.** Vorher
  war es die Scan-Stelle (`nummer`): eine Zahl, die die Liste gar nicht zeigt,
  womit die Reihenfolge willkürlich aussah. Die ID gilt dabei **über die
  Grenze „gehört zum offenen Scan" hinweg** — sie bezeichnet den Slot
  dauerhaft, und eine Ordnung, die bei jedem Häkchen umspringt, wäre wieder
  die bewegliche Zahl von vorher. Slots ohne ID (Altbestand, den der Backfill
  noch nicht gesehen hat) landen am **Ende** und werden dort nach Namen
  geordnet: vorn stünde der ungepflegte Rest über allem anderen, und die
  Ansicht erfindet keine Reparatur für Bestandsdaten.

  Bei gleicher Lage entscheidet der Name **natürlich sortiert**
  (`nachNamen()`, `numeric: true`) — ein reiner Zeichenvergleich stellt
  „Slot 10" zwischen „Slot 1" und „Slot 2", und bei fünfundvierzig
  durchnummerierten Slots ist die Liste damit sortiert und trotzdem unlesbar.
  Die Items bleiben bei Kategorie und Rang: sie haben keine ID.

- **Welche Priorität frei ist, steht da** (`prioritaetsBelegung()`). Die
  Übersicht zeigte nur die vergebenen Ränge; ob P2 belegt ist oder fehlt, sah
  man erst, wenn man P1, P3, P4 las und selbst nachzählte. Sie spannt deshalb
  jeden Rang von 1 bis zum höchsten belegten plus eins auf — der nächste freie
  steht immer da —, und eine Lücke ist gestrichelt statt beschriftet. Eine
  getippte P99 spannt das nicht auf hundert Kacheln auf (`PRIO_MAX_ZEIGEN`).

  **Eine doppelte Priorität fällt schon in der Liste auf**, nicht erst im
  aufgeklappten Detail: getippt wird in der Maske. Bei gleicher Zahl entscheidet
  die Scan-Reihenfolge, also der Zufall — das ist kein Fehler, aber fast immer
  ein Versehen.

  **Wer ein Item in eine Kategorie schiebt, hat über seine Priorität nichts
  gesagt** — dann rückt es auf den nächsten freien Rang (`_freie_prioritaet()`,
  erste Lücke, nicht ans Ende) und es wird gesagt. Eine ausdrücklich getippte
  Zahl fasst dagegen niemand an, auch keine doppelte: sie kann gewollt sein, und
  ungefragt zu verschieben wäre schlimmer als die Doppelung.

- **Der Fokus hängt an der `id` der Maske** (`maskeId()`, gelesen von
  `fokusMerken()`). Ohne sie klettert `closest("[id]")` bis zur ganzen Spalte,
  und die gemerkte Position zählt über **alle** Masken hinweg — bei sechzig
  Items rund zweihundert Felder. Genau die drei Angaben, die man dort tippt,
  sortieren die Liste aber um (Kategorie, Priorität, Name): nach dem Neuaufbau
  stand an derselben Position das Feld eines **fremden** Items, der Cursor
  sprang weg, und wer weitertippte, änderte das falsche. Ein Umbenennen ändert
  die id selbst — `fokusUmbenennung()` sagt sie vorher an, und die alte bleibt
  als Rückfall, falls die Brücke den Namen ablehnt. Gemessen wird das im
  **Rauchtest**: einen Fokus sieht die Vertragssuite nicht.

  **Der Schutz sitzt in `scanInspektor()`, nicht bei den Aufrufern.**
  `zeichneScans()` hatte ihn, aber es gibt einen zweiten Weg: sobald ein
  nachgeladenes Template ankommt, baut `scanVorschauenHolen()` die Spalte
  direkt neu. Genau das passiert beim Umbenennen — unter dem neuen Namen gibt
  es noch keine Vorschau —, und dort ging der Fokus verloren, während er beim
  Tippen einer Priorität stehen blieb. Ein Schutz, an den jeder Aufrufer denken
  muss, ist einer, den einer vergisst.

- **Ein Item hat einen Klick DANACH** (`scanItemBestaetigung()`,
  `ItemProfile.confirm_point_id`). Manche Spiele fragen nach („wirklich
  verkaufen?"); ohne die Bestätigung bleibt das Popup stehen, und der Scan
  erreicht den nächsten Slot gar nicht mehr. Das Feld gibt es im Modell und in
  den Konsolen-Editoren seit jeher — im Studio war es die einzige
  Item-Eigenschaft ohne Bedienelement, und wer es suchte, fand nichts.

  Gesetzt wird es über einen **Punkt**, nie über zwei Zahlen. Zwei Wege dorthin,
  und der zweite ist dasselbe Werkzeug, das Boss und Icon schon benutzen:
  `_ziel_pruefen("item")` gibt das gewählte Item zurück, `_klick_aktion()` legt
  den Punkt an und schreibt ihn nach `confirm_point_id` statt nach
  `action_point_id`. Ein zweites Werkzeug daneben wäre dieselbe Frage mit einer
  zweiten Antwort.

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
  er gerade angeklickt hatte, ein zweites Mal und musste erst auf „Items"
  klicken. `scanListe = null` heisst „noch nicht entschieden" — dann gilt
  `scanListeAktiv()` (bei offenem Scan: Items). Sobald jemand einen Reiter
  anfasst, steht dort seine Entscheidung; **das Öffnen eines Scans setzt sie
  zurück**, denn das ist ein Wechsel des Zusammenhangs. Dieselbe Mechanik wie
  `klappZu`.

  **Mit einer Ausnahme, und die ist der Grund für `scanReiterNachOeffnen`:** wer
  einen Scan aus der Scan-Liste heraus öffnet, arbeitet gerade an Scans. Springt
  der Reiter dann auf „Items", verschwindet genau die Maske, die sich soeben mit
  seinen Einstellungen aufgeklappt hat — und damit war der Scan **nicht mehr zu
  löschen**. Der Wunsch gilt genau einmal und wird danach gelöscht.

- **Der Reiter folgt der Auswahl, aber nur beim Wechsel** (`scanReiterFolgen()`).
  Ein Klick INS BILD wählt einen Slot, und der steht in der Slot-Liste; ist
  gerade die Item-Liste offen, geschieht rechts sonst nichts und der Klick sieht
  wirkungslos aus. Beim blossen Neuzeichnen darf dagegen nichts umschalten —
  sonst wäre der Weg aus der Slot-Liste heraus versperrt, solange ein Slot
  gewählt ist. Verglichen wird deshalb Art **und** Name der Auswahl.

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
Listen zeigen deshalb nur, was zu diesem Scan gehört.

**Der Filter dafür ist mit dem globalen Bestand verschwunden**, und das ist
kein Verlust: seit eine Sequenz eine Besitzeinheit ist, IST der offene Scan der
vollständige Bestand — es gibt nichts, wovon man ihn abgrenzen müsste. Übrig
blieben davon `scan_filter()` und `nur_dabei` in der Brücke, ohne dass die
Ansicht beides je gerufen oder gelesen hätte; beides ist gelöscht. Dieselbe
Sorte Rest wie `points.json`, nur eine Ebene höher.

**Und es gibt dafür genau EIN Bedienelement.** Bis zum Masken-Umbau gab es drei
Wege zur selben Frage: den Haken in der Maske, „alle dazu/raus" in der
Filterzeile und eine dritte Liste im Scan-Inspektor (`hakenListe()` mit einem
„N weitere im Bestand zeigen"). Die dritte ist **ersatzlos gelöscht** — samt dem
Mischzustand des `alle`-Schalters (`indeterminate`), der nur dort gebraucht
wurde. Ein Schalter, der bei „23 von 56" nicht zu beschriften ist, war das
Problem und nicht die Lösung; der Knopf **sagt**, was er tut.

**Und „ausschalten" ist etwas anderes als „nicht dazugehören."** Die
Slot-Maske trägt einen eigenen Ein-Aus-Schalter (`scan_slot_setzen`, Feld
`aktiv`), keinen Mitgliedschaftshaken: ein ausgeschalteter Slot behält seine
Daten und bekommt nur keine laufende Nummer mehr. Das ist der Unterschied, an
dem die alte Fassung scheiterte — ohne offenen Scan gab es keine
Mitgliedschaft, also stand dort gar kein Bedienelement, und „ich kann die
Slots nicht mehr ausschalten" war die Folge. Ein Schalter, der eine Eigenschaft
des Slots setzt, braucht keinen Scan als Bezug und ist deshalb immer da.

**„Alle raus" ist nicht „alle löschen".** Der eine nimmt aus der Mitgliedschaft
— Slot bzw. Item bleibt im Bestand —, der andere (`scan_alle_loeschen()`)
nimmt ihn wirklich weg. Fünfzig Slots einzeln durchzuklicken war der Grund,
warum man diesen Knopf sucht; er steht als `.btn.gefahr` direkt neben „alle
raus", mit derselben Bezugsregel wie überall (`_scan_slots()`/`_kandidaten()`:
der offene Scan, sonst der Bestand) — ein Slot eines *anderen* Scans bleibt
unangetastet. Kein Bestätigungsdialog: STRG+Z holt den ganzen Abzug zurück,
genau wie beim einzelnen Löschen.

**Der geöffnete Scan IST der vollständige Bestand** — und damit stellt sich die
Frage „gehört das hierher" gar nicht mehr. `scanSichtbar()` filtert nur noch nach
Kategorie; Slots und Items einer Sequenz gehören ihrem Scan, fremde gibt es dort
nicht zu sehen.

Hier stand einmal die Regel **„gehört dazu ODER wird gerade gesehen"**
(`dabei || erkannt`), und sie war die Antwort auf ein Problem, das der globale
Bestand hatte: Slots zweier Spiele lagen in einer Liste, also musste die Ansicht
entscheiden, welche sie anbietet. Mit dem Umzug auf Besitzeinheiten ist die Frage
verschwunden, und mit ihr die Regel — samt `_slot_im_bild()` und dem Slot-Feld
`erkannt`, das zuletzt berechnet und von niemandem mehr gelesen wurde.

Beim **Item** bleibt `erkannt` dagegen echt (`_erkannte_items()`, Feld
`erkannt_in`): es sagt nicht „gehört dazu", sondern **wo** das Item gerade
gefunden wurde. Das ist die nützlichste Auskunft der Erkennung und der Grund,
warum ein Treffer ein Vorschlag ist und keine Festlegung — „erkannt" ohne Beleg
wäre eine Behauptung.

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
Items, Item-Scans, Boss-Scans, Icon-Scans, die Bibliothek **und die Punkte
der Sequenz** —
ein Klickpunkt einer Boss- oder Icon-Aktion ist ein Punkt, und die Koordinate steht
dort und sonst nirgends. Der Rückgängig-Abzug (`_erkennung_zustand()`) nimmt sie
ebenso mit: ein Zurück, das die Slots zurückdreht und den Boss-Scan stehen lässt,
wäre ein halbes Zurück, und das ist schlimmer als gar keins.

**Der Konsolen-Editor bleibt** (`CTRL+ALT+N`). Er schreibt dieselben Dateien —
deshalb zählen die `boss_scans/`- und `icon_scans/`-Ordner der Sequenz samt ihrer
`boss_scans/bibliothek.json`
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

**Und weil sie drüben läuft, gibt es einen Rückkanal** (`.nachklick.json`,
`NACHKLICK_STATUS_FILE`). Ohne ihn stand im Fenster nur „gestartet", während die
Konsole jeden Schritt einzeln meldete — und *welcher Punkt gerade dran ist* ist
genau die Frage, die man beim Klicken hat. Dieselbe Bauart wie `.lauf.json` und
`.aufnahme.json`: kein Log, sondern der Stand JETZT, überschrieben bei jeder
Bewegung der Runde. Gelesen wird er über `nachklick_status()` im `frage()`-Kanal.

Drei Regeln dazu:

- **Der Verlauf ist ein eigenes Feld, kein abgeleiteter Wert**
  (`state.nachklick_verlauf`, Einträge `(Punkt-ID, Art)`). Naheliegend wäre,
  ihn aus `nachklick_gesetzt` zu rechnen — das geht nicht: ein **bestätigter**
  Punkt (innerhalb `PASST_TOLERANZ`) landet dort bewusst nicht, und im Fenster
  sähe er damit genauso aus wie ein übersprungener. Beide ändern nichts, aber
  nur einer heisst „ich habe hingesehen".
- **Die Zusammenfassung wird eingesammelt, BEVOR `stop_nachklick()` die Listen
  leert.** Danach ist der Verlauf weg, und das Fenster zeigte eine leere Runde
  — ausgerechnet in dem Moment, in dem man nachsieht, was sie ergeben hat.
  Dieselbe Regel und derselbe Grund wie bei `status.beende()`.
- **Geschrieben wird aus dem Hook heraus**, und das widerspricht dem Satz oben
  nur scheinbar: gemeint ist dort das vollständige Speichern am Ende (Sequenz
  plus Punkte serialisieren, mehrere Dateien). Hier geht eine knappe JSON-Zeile
  über `atomic_write` raus — dieselbe Grössenordnung, die die Aufnahme bei
  **jedem** aufgezeichneten Klick schreibt.

Ein Stand, der `aktiv` behauptet und älter als 5 s ist, gilt als **verwaist** —
dieselbe Rechnung wie beim Laufstatus, und aus demselben Grund: ein abgestürzter
Hauptprozess hinterlässt sonst eine Runde, der niemand mehr zusieht.


**Ein Griff mit der Maus sagt, dass er wartet** (`WARTE_GRIFFE` in `app.js`,
`WARTE_TIMEOUT` in `bridge_contract.py`). Acht Aufrufe der Seite warten über
`_stelle_abwarten()` bzw. `bereich_aufnehmen()` **global auf ENTER** — und der
Brücken-Aufruf blockiert dabei bis zu einer Minute. Die Seite bekommt in dieser
Zeit keine Antwort, kann also nichts anzeigen, was von drüben käme; ohne einen
Hinweis **vor** dem Aufruf sah es aus, als tue das Fenster nichts. Betroffen sind
Stelle und Bereich im Editor, „Punkt aufnehmen" und „Neu messen", das Messen im
Farben-Werkzeug, der Referenzpunkt der Kalibrierung und die Parkposition in den
Einstellungen.

`mitWarten(art, name, daten)` legt den Kasten davor und ruft darunter den Kanal,
den der Aufruf ohnehin hätte (`ruf` / `frage` / `rufWerkzeug`). Drei Regeln:

- **Die Zeitgrenze steht an EINER Stelle** und wird mitgeliefert
  (`warte_timeout` in Momentaufnahme und Werkzeug-Daten). Ein Countdown, der
  neben dem echten Zeitablauf der Brücke läuft, ist schlechter als keiner.
- **Der Fortschritt wird nicht erfunden.** `bereich_aufnehmen()` will zwei
  Tastendrücke, aber beide Ecken sind EIN Aufruf (die Hand soll zwischendurch
  nicht zum Fenster zurück) — die Seite erfährt vom ersten ENTER nichts. Sie
  sagt deshalb vorher, wie viele kommen, statt eine Ecke 1/2 zu behaupten, die
  sie nicht sehen kann.
- **Ein Test hält beide Seiten gegeneinander**: welche Methoden warten, steht in
  der Brücke; dass die Seite sie über `mitWarten` ruft, in `app.js`. Er prüft
  beide Richtungen — eine wartende Methode ohne Eintrag ist genau die, bei der
  das Fenster wieder stumm ist, und ein Eintrag für etwas, das gar nicht wartet,
  verspricht einen Kasten, den niemand je sieht.

Dabei ist aufgefallen: **`kalib_referenz` wartet auch bei „Trotzdem setzen"**
erneut auf ENTER, misst die Stelle also neu. Das ist so gewollt (bestätigt wird
die abweichende Farbe, nicht eine schon erfasste Stelle) — ohne den Kasten sah
der Knopf aber aus, als täte er nichts.


**Jedes Werkzeug sagt, WORAUF es wirkt** — und „jedes" heisst jedes: „Farben
analysieren" trug als einziges keine Bezugszeile, während in `WZ_WERKZEUGE`
`bezug: "bestand"` stand. Das wäre die falsche Auskunft gewesen (es misst nur
den Bildschirm und schreibt nirgends hin), und weil die Zeile gar nicht
gezeichnet wurde, fiel die Unwahrheit nicht auf. Dafür gibt es die vierte Art
**`nichts`** — kein fehlender Wert, sondern eine eigene Aussage, und bei einem
Werkzeug neben `kalibrieren` und `nachklicken` die beruhigende.

Die Kopfleiste blendet hier ihr
Sequenz-Speichern aus (der Reiter bearbeitet andere Dateien) — und blendete
lange auch die Auswahl mit aus, womit der Sequenzname weg war; bei der
Klick-Runde ist das genau die Frage, die man sich stellt. Seit die Auswahl
überall steht, ist der frühere Ersatz („offene Sequenz <Name>" links) wieder
**weg**: er liess den Namen dreimal gleichzeitig dastehen. Ein einzelner Name
oben wäre trotzdem falsch gewesen: Prüfen und
Kalibrieren gehen über den **ganzen Bestand**, nur die Klick-Runde meint **eine**
Sequenz. Deshalb trägt jedes Werkzeug seine eigene Bezugszeile (`wzBezug()`), und
links steht die offene Sequenz als Einordnung.

Daran hing ein echter Fehler: `befehl_nachklick` nahm `state.active_sequence` aus
dem Hauptprozess — der hat womöglich eine ganz andere geladen als die im Studio
offene. Man klickt dann eine Runde lang die Punkte einer fremden Sequenz nach und
merkt es nicht, weil jeder Klick im Spiel ja etwas tut. Die Datei kommt jetzt mit,
wie bei `befehl_start`; ohne sie passiert gar nichts.

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
Briefkasten-Befehl `daten` — der zieht dabei auch die Punkte der Sequenz
nach, denn bei einer Kalibrierung wandert **jede** gespeicherte Stelle.

**Der Reiter „Bericht" liest `logs/`** (`bridge_bericht.py`). Der Live-Run zeigt das
Jetzt, dieser Reiter das Gestern — und er beantwortet die Frage, die man nach einer
langen Nacht hat und bis dahin nur auf der Kommandozeile stellen konnte: **welcher
Schritt läuft am häufigsten in den Timeout?**

Fünf Regeln, an denen er hängt:

- **Gerechnet wird in `tools/log_report.py`**, mit derselben Funktion, die die
  Kommandozeile benutzt. Dafür ist die Auswertung dort in zwei Hälften zerlegt:
  `auswerten()` gibt **Daten** zurück und druckt keine Zeile, `bericht()` druckt sie.
  Eine zweite Auswertung „fürs Fenster" wäre eine, die andere Zahlen nennt als der
  Weg, den die README beschreibt. Ein Test misst beides — die Zahlen *und* dass
  `auswerten()` schweigt: eine übrig gebliebene `print`-Zeile landete in der Konsole
  des Studios, wo sie niemand sieht.
- **Die Richtung des Imports ist Absicht.** `tools/log_report.py` importiert nichts
  aus `autoclicker/` — **die Brücke ruft das Werkzeug**, nie umgekehrt. Der Import
  steht deshalb in der Methode und in einem `try`: `tools/` gehört zum Repo, nicht
  zum Programm. Fehlt es, erklärt sich der Reiter, statt das Fenster beim Start
  umfallen zu lassen.
- **Der Ertrag ist eine Obergrenze, keine Abrechnung.** `item_found` mal
  `marktwert.json` (`scan_market_value_file`) ist der tatsächliche Ertrag eines Laufs
  — aber „erkannt" heisst nicht „eingesammelt und verkauft". Das steht **am Wert**
  und nicht im ⓘ: wer die Zahl liest, muss den Vorbehalt lesen, ohne danach zu
  fragen. Ohne Wertetabelle gibt es Stückzahlen und sonst nichts; das ist kein
  Fehlerfall, sondern der Normalfall ohne Marktanalyse. Die Trennung zu
  `market_analysis/` bleibt eine Datei — importiert wird nichts.
- **Gelesen werden die neuesten 50 Dateien**, und was wegfällt, wird gesagt. `logs/`
  wächst mit jedem Start, und der Reiter wird bei jedem Öffnen gezeichnet; ohne
  Deckel liest ein halbes Jahr Betrieb bei jedem Klick mit. Eine stillschweigend
  gekürzte Auswertung wäre schlimmer als eine kurze.
- **Er baut mit dem, was da ist.** Kennzahlen sind `wz-kennzahlen` (dieselben
  Kacheln wie im Werkzeuge-Reiter), Karten sind `teilen-karte`, die Spalten sind
  `abschnitt` — eigene Klassen gibt es nur für die Rangzeile und die
  Sitzungsauswahl, und **eine** Rangzeile trägt alle vier Listen plus den Ertrag.
  Ein achter Reiter, der sich seine eigene Gestalt gibt, kostet mehr als er
  einbringt. Dazu gehört, dass untereinander stehende Blöcke auf **derselben**
  Kante liegen: die Kennzahlen dürfen 880 px, die Karten kamen mit 720 — gestapelt
  waren das zwei rechte Kanten, 160 px auseinander und damit nah genug, dass es wie
  ein Rundungsfehler aussieht statt wie Absicht.

Zwei Tests halten die Verdrahtung fest, und beide prüfen **beide** Richtungen: jeder
`data-ansicht`-Knopf braucht seine Umschalt-Zeile in `setzeAnsicht()` (und keine
Zeile bleibt ohne Knopf), und jeder Rauchtest unter `tests/rauch/` muss in
`RAUCHTESTS` (`tests/alle_tests.py`) stehen — eine getippte Liste ist genau die
Stelle, an der eine neue Datei vergessen wird, und der Lauf bleibt dabei grün.

**Die Einstellungen bearbeiten eine andere Datei als der Rest des Fensters.** Das ist
der ganze Grund, warum das Sequenz-Speichern im Kopf dort verschwindet: zwei
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

**Und der Schreiber lädt sich selbst mit.** `config_schreiben()` ruft
`uebernehmen(CONFIG, neu)` auf dem eigenen Prozess — das fehlte, und damit war
ausgerechnet das Fenster, das die Datei geschrieben hat, das einzige, das den neuen
Stand nicht kannte: der Hauptprozess bekam den Briefkasten-Befehl, der Studio-Prozess
blieb bis zum Neustart auf den Werten vom Programmstart sitzen. Aufgefallen ist es am
Bericht-Reiter („session_log_enabled ist aus", direkt nachdem man es eingeschaltet
hatte); betroffen war jeder Reiter, der `CONFIG` liest — OCR/LLM-Lampen und
Marker-Schwellen im Scans-Reiter, die Farbtoleranz im Werkzeuge-Reiter, der
Fenstertitel im Teilen-Reiter. Der Einstellungen-Reiter selbst blieb richtig, weil er
die **Datei** liest; genau daran sah man den Widerspruch. Ein Test misst beide Hälften:
der Wert kommt an, und das Objekt bleibt dasselbe.

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
  wie beim Klick-Block, nur ohne Punkt anzulegen. Eine Parkposition gehört nicht
  zu den Punkten der Sequenz.

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

**Geleert wird durch Umbenennen, nicht durch Lesen-und-dann-Löschen** (`hole()`).
Der Briefkasten wird alle 250 ms abgefragt und vom anderen Prozess jederzeit
beschrieben; wer erst liest und danach löscht, wirft einen Befehl weg, der in
genau diesem Zeitfenster ankam. `Path.replace()` auf einen privaten Namen ist
atomar: was entnommen ist, ist entnommen, und was danach geschrieben wird, liegt
beim nächsten Durchgang noch da. Dieselbe Überlegung wie bei `atomic_write()`,
nur in die andere Richtung.

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
Das Studio merkt sich beim Laden den Zeitstempel der Sequenzdatei
(`_stand_merken()`) — die Punkte stehen darin, es ist also EIN Stand für
beides; hat sie sich beim Speichern geändert, fragt es
nach, statt zu überschreiben. Der Fall ist Alltag: eine Aufnahme im Hauptprozess
legt Punkte an, `save_data()` schreibt die Sequenz. Die Rückfrage ist derselbe
Dialog wie bei ungespeicherten Änderungen — er trägt Titel, Text und
Knopfbeschriftung jetzt aus der Brücke, weil sich die Fälle zu sehr
unterscheiden (bei „ausserhalb geändert" gibt es nichts zu verwerfen).

**Gefragt wird VOR dem Umbenennen, und gefragt wird nach der GELADENEN Datei.**
Beides war einmal andersherum, und beides machte die Rückfrage genau dann
wirkungslos, wenn sie zählt: der Ordner wurde zuerst verschoben, und danach
prüfte `_fremd_geaendert()` den *neuen* Pfad — den es vorher gar nicht gab, also
war dort nie etwas „fremd geändert". Beim Umbenennen wurde deshalb kommentarlos
überschrieben, obwohl gerade dort eine Aufnahme des Hauptprozesses im alten
Ordner liegen kann. Geprüft wird jetzt die Datei, deren Inhalt gleich ersetzt
wird — also die geladene, vor jeder Bewegung auf der Platte.

**Und die Notsicherung nimmt die Punkte mit.** `_ungespeichert_sichern()`
schrieb `board_to_sequence(self.board)` ohne `palette_to_points(self.points)`:
die Sicherung, die man beim Absturz aufmacht, enthielt jeden Schritt mit einer
`point_id`, die ins Leere zeigt. Ein Rettungsanker, der die halbe Sequenz
rettet, ist schlimmer als keiner — man merkt den Verlust erst beim Laden.

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
  (`copy.deepcopy`), **und die Kopie bekommt eigene Punkte**.

  Hier stand einmal das Gegenteil („ein Duplikat ist erst mal derselbe Klick"),
  mit dem Argument, ein zweiter Punkt an derselben Stelle sei die Doppelung, die
  `punkt_an_stelle()` überall sonst vermeidet. Das Argument stimmt für
  *unabsichtliche* Dubletten aus einer Aufnahme — hier war es falsch: **man
  dupliziert einen Block, um ihn zu ändern.** Zeigten beide auf denselben Punkt,
  verstellte jede Korrektur an der Kopie auch das Original, und auffallen würde
  es erst viel später an einer Stelle, an der man es nicht mehr sucht. Der Preis
  sind zwei Punkte auf einer Stelle, bis einer umzieht.

  `_punkte_mitkopieren()` führt dafür **eine Abbildung für den ganzen
  Durchgang**, und die hat zwei Wirkungen: innerhalb eines Blocks bleibt
  zusammen, was zusammengehört (bei FARBE+KLICK sind Klick und Prüf-Pixel
  derselbe Punkt — sonst wartete die Kopie auf eine andere Stelle, als sie
  klickt), und zwischen mehreren kopierten Blöcken bleibt die Beziehung erhalten
  (zwei Gewählte auf einem Knopf ergeben zwei Kopien auf **einem** neuen, nicht
  auf zweien). Eine Referenz ins Leere wird nicht wiederbelebt: sie bleibt, wie
  sie ist, statt still zu einem Klick auf (0, 0) zu werden.

  **Das Verschieben bleibt davon unberührt**: `punkt_setzen()` ändert weiterhin
  den PUNKT, und jeder Schritt darauf zieht mit. Genau das will man, wenn zwei
  Blöcke wirklich denselben Knopf klicken und der Knopf umzieht — ohne das wäre
  jede Kalibrierung eine halbe. Ein Anlauf, das im Inspektor per Copy-on-Write
  zu lösen, kurierte nur das Symptom und nahm dabei diese Regel mit.
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
  in der Datei, also eine Koordinaten-Kopie neben dem Punkt, die
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

  **Dieselbe Regel gilt im Scans-Reiter, und sie wurde dort zweimal korrigiert.**
  Zuerst stand der Name des Item-Scans im Inspektor ganz rechts, während man den
  Scan oben links wählte — man suchte ihn in der einen Spalte und benannte ihn
  drei Spalten weiter. Er wanderte deshalb unter die Klappliste. Seit der Scan
  eine **Maske** hat, ist das die zweite Wahrheit: der Name steht in der Maske,
  wie bei Slot und Item auch, und das Feld links ist ersatzlos weg. Die
  Klappliste bleibt — sie **wählt** nur, sie benennt nicht. Aus demselben Grund
  nennt die Überschrift im Detailteil den Scan nicht noch einmal: sein Name steht
  in derselben Maske eine Zeile darüber. Ein Test misst beide Hälften.
- **Erklärungen stehen im ⓘ, Zustand und nächster Schritt im Text.** Ein
  `hinweis`-Absatz sagt, was JETZT gilt („62×60 px", „Zeigt ins Leere: …") oder
  was als Nächstes zu tun ist („Noch keine Slots. …"). Alles, was erklärt, WARUM
  etwas so ist, gehört ins ⓘ — es gilt immer, ändert sich nie und steht deshalb
  bei jedem Blick im Weg; `offeneHilfen` merkt sich, welche aufgeklappt sind.
  `schalter()`, `zahlfeld()`, `farbfeld()`, `auswahl()` und `ueberschrift()`
  nehmen dafür alle `hilfe, schluessel` entgegen — ein Erklärungsabsatz **unter**
  einem dieser Bedienelemente ist deshalb fast immer ein Fehler.
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
per `CTRL+ALT+SHIFT+M` ein **Warte-Marker auf eine Farbe** und per
`CTRL+ALT+SHIFT+D` ein **Screenshot-Marker**. Jedes Ereignis ist ein
`RecordEvent` (`models.py`, `REC_*`) —
rein transient, wird nie gespeichert; `stop_recording()` baut daraus Schritte und
wirft die Liste weg.

**Alles muss mit EINEM globalen Tastendruck gehen.** Während der Aufnahme steht der
Nutzer im Spiel, nicht in der Konsole — ein blockierender Prompt käme nie an. Nachfragen
sind erst beim Stoppen möglich, und dort passieren sie auch (Name, Zyklen, Beschreibung).

Drei Regeln, an denen die Aufnahme hängt:

- **Der Warte-Marker hat keine eigene Stelle.** Er wird gedrückt, sobald man anfängt zu
  warten — die Maus parkt dabei irgendwo, und diese Position wäre reiner Zufall. Ein
  erster Entwurf legte darauf einen Punkt an; in einer echten Aufnahme stand da dann
  `Warte auf Farbe bei (4483, 1038) Schwarz (3,4,5)`, also Müll in den Punkten.
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
| Warte auf Farbe | `CTRL+ALT+SHIFT+M` | nein — geht in den nächsten Klick ein | nein | **zufällig**, wird ignoriert |
| Screenshot Vollbild | `CTRL+ALT+SHIFT+D` | ja | nein | irrelevant |
| Screenshot Bereich | `CTRL+ALT+SHIFT+R` | ja (aus **zwei** Drücken) | nein | **bewusst** — die Ecken |
| Beobachten ohne Klick | `CTRL+ALT+SHIFT+B` | ja (`wait_only`) | **ja** | **bewusst** — das Beobachtete |
| Neue Phase | `CTRL+ALT+SHIFT+P` | nein — schneidet nur | nein | irrelevant |

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

**Jeder Druck macht eine neue Loop-Phase auf, ohne Obergrenze** (`phasen_bauen()`).
Vorher trennte der erste Druck INIT von LOOP und der zweite LOOP von END; beim
dritten stand da „mehr Phasen kann die Aufnahme nicht", und wer vier Abschnitte
gespielt hatte, zog sie hinterher im Studio von Hand auseinander — also genau die
Arbeit, die der Marker sparen soll. Leere Abschnitte fallen weg (zweimal
hintereinander gedrückt ist derselbe Wunsch, zweimal geäussert); bleibt gar nichts
übrig, kommt trotzdem eine leere Phase zurück, denn eine Sequenz ohne jede
Loop-Phase hat keine Stelle, an der man danach etwas einfügen könnte.

**INIT und END befüllt die Aufnahme nicht mehr.** Sie kann nicht sehen, welcher
Abschnitt nur einmal laufen soll — das ist eine Aussage über die Absicht, und die
steht im Studio an der Phase. Vorher war die erste Grenze stillschweigend „ab hier
der Zyklus", was bei einer Aufnahme ohne INIT-Absicht einen Abschnitt aus der
Wiederholung nahm, ohne dass es jemand gesagt hätte.

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

**Ein noch antwortender LLM-Aufruf gehört zum BEENDETEN Lauf.** Mit `llm_async`
läuft die Erkennung in einem eigenen Thread, und der hängt bis zu `llm_timeout`
(Standard 60 s) in einer HTTP-Antwort — ein Stopp beendet ihn nicht, er merkt es
erst danach. `handle_toggle()` lehnt einen Neustart deshalb ab, solange
`state.llm_thread` noch lebt, und sagt warum. Ohne die Sperre feuerte die
verspätete Aktion des alten Laufs in den neuen hinein: ein Klick auf eine Stelle,
die zu einem Boss gehört, den es in diesem Durchgang gar nicht gibt.

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

**Die Runde arbeitet auf PUNKTEN, nicht auf einer Sequenz.** Aus der Sequenz
kommt genau eine Sache: die Reihenfolge, in der ihre Punkte geklickt werden.
Danach ist sie uninteressant — die Datei wird nicht angefasst, und die im
Hauptprozess **geladene** Sequenz wechselt ausdrücklich nicht (`ruesten(state,
seq)` nimmt sie als Argument). Sie zu aktivieren hiesse, dass ein Druck auf
`CTRL+ALT+S` nach der Runde etwas anderes startet als vorher.

**Geschrieben wird erst am Schluss, und nur auf ausdrückliches Übernehmen**
(`CTRL+ALT+J`, „Übernehmen" im Studio). Bis dahin stehen die neuen Stellen in
`state.nachklick_gesetzt` und die Punkte sind unverändert — auch im Speicher.
Damit ist ein Abbruch folgenlos: `stop_nachklick(..., uebernehmen=False)` wirft
die Liste weg, es gibt nichts zurückzudrehen. Verworfen wird beim Schliessen des
Studio-Fensters (`nachklick_beim_schliessen()` — die Runde gehört dem Fenster,
das sie gestartet hat) und beim Beenden des Programms.

Vorher schrieb **jeder** Ausgang. In einer echten Runde hat das drei Punkte auf
Fensterdekoration gesetzt und beim Beenden gespeichert.

Fünf Regeln, an denen die Klick-Runde hängt:

- **Geändert wird nur die Stelle.** Wartezeiten, Farb-Bedingungen,
  Nachprüfungen, ELSE, Scans und die Reihenfolge bleiben — die Runde fasst die
  Reihenfolge und die Schritte überhaupt nicht an, sie schreibt `x`, `y` und (nur
  wenn der Punkt schon eine hatte) die Farbe in den Punkt.
- **Jeder Punkt einmal, in der Reihenfolge des Laufs** (INIT → Loop-Phasen →
  END). Klickt eine Sequenz zweimal denselben Knopf, ist das ein Punkt; ihn
  zweimal zu setzen hiesse, den ersten Griff wieder zu verwerfen.
- **Was sie nicht erreicht, sagt sie** (`klickpunkte()` gibt zwei Listen
  zurück): beobachtete Pixel, ELSE-Klicks, Nachprüfungen und Rad-Schritte kommen
  in einem normalen Durchlauf nicht vor. Dafür bleibt `walk`. Wer beides ist —
  erst beobachtet, später geklickt — zählt als Klick; deshalb sammelt die
  Funktion **erst alle Klicks und dann den Rest**, in einem Durchgang fiel so
  ein Punkt aus der Runde heraus.
- **Nur Klicks im Zielfenster zählen** (`window_focus_title`, unabhängig von
  `window_focus_check` — das Flag entscheidet über das Verhalten des *Workers*).
  Der Hook ist systemweit: ohne den Filter zählte auch der Klick auf das
  Studio-Fenster, die Konsole oder ein Schliessen-Kreuz, und dessen Stelle landete
  im Punkt. Gemeldet wird einmal je fremdem Fenstertitel; gibt es das Zielfenster
  gerade nicht, wird **nicht** gefiltert und gesagt, warum — ein Filter, der alles
  wegwirft, sähe aus wie ein kaputter Hook.

  **Gefragt wird, in WELCHES Fenster geklickt wurde — nicht, welches vorn ist**
  (`get_window_title_at()`, Rückfall auf den Vordergrund). Windows liefert den
  Button-Down an das Fenster unter dem Zeiger; war das nicht das aktive, wird es
  durch genau diesen Klick erst aktiv. Im Hook steht damit noch das **vorige**
  Fenster im Vordergrund, und die Frage „bin ich im Zielfenster?" wird für den
  Klick davor beantwortet. Ein Klick, der ein anderes Fenster nach vorn holt,
  zählte deshalb als Klick ins Ziel — in einer echten Runde ist so ein Punkt auf
  eine Stelle im Studio-Fenster gewandert (Farbe `#1C2333`, dessen eigenes
  Panel-Grau), unmittelbar nachdem derselbe Filter den Klick davor korrekt
  abgewiesen hatte. Nachmessbar ohne jede Runde: `get_window_title_at(10, 10)`
  meldet das Fenster an dieser Stelle, `get_foreground_window_title()` das
  aktive — auf einem Rechner mit offenem Spiel sind das verschiedene.

  **Mehrere Fenster desselben Spiels sind ausdrücklich in Ordnung.** Geprüft
  wird der Titel, und drei Instanzen tragen denselben; welche gemeint ist,
  entscheidet der Nutzer mit dem Klick.
- **Ein Pixel Abweichung ist keine Korrektur** (`PASST_TOLERANZ`). Der Zeiger wird
  von uns auf die Stelle gesetzt, und trotzdem kommt der Klick gelegentlich einen
  Pixel daneben zurück (DPI-Skalierung). Ohne die Toleranz schriebe jede
  Bestätigung den Punkt um einen Pixel um und zählte als Änderung — Rauschen in
  genau der Liste, die sagen soll, was sich geändert hat.
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
  Bedeutung wie sonst, nur einen anderen Gegenstand. Die Liste steht als
  `TASTEN` in `editors/nachklick.py`; das Studio zeigt sie als **Tabelle**
  (`WZ_TASTEN` in `app.js`), und ein Test hält beide gegeneinander. Was man
  mitten im Klicken nachschlägt, muss man finden — ein Fliesstext zwingt zum
  Lesen von vorn, und dann liest ihn niemand.

**Der Zeiger steht immer schon auf der gespeicherten Stelle** — vor jedem Punkt,
auch nach einem echten Klick. Das ist der Griff, der die Runde billig macht:
stimmt die Stelle noch, ist der Punkt ein einziger Klick, und nur die
verrutschten kosten eine Mausbewegung. Nach einem Bildschirm-Umbau sind das die
wenigsten.

Hier stand einmal das Gegenteil („springt **nicht** nach einem echten Klick"),
und der Grund war nicht falsch: der Hook meldet den **Druck**, das Loslassen
kommt erst danach — dazwischen die Maus wegzuziehen macht aus dem Klick ein
Ziehen. Nur war die Antwort darauf falsch. Statt gar nicht zu springen, springt
er nach `SPRUNG_VERZOEGERUNG` (0,25 s, `_springe(..., verzoegert=True)`); die
alte Fassung liess die Stelle als Zahlenpaar in der Konsole stehen, und man
musste sie auf dem Schirm suchen, statt sie zu sehen.

**Und es läuft nichts von selbst.** Ein Start während der Runde wird abgelehnt —
`handle_toggle()` prüft `nachklick_aktiv` genau wie `recording_active`, und
`ruesten()` lehnt umgekehrt ab, solange ein Countdown gestellt ist. Der Grund ist
derselbe wie bei der Aufnahme, eine Stufe schlimmer: **der Maus-Hook kann die
Klicks des Workers nicht von Handgriffen unterscheiden.** Lief eine Sequenz mit,
verbrauchte sie die Punkte der Runde selbst und schrieb ihre eigenen Ziele
hinein — von aussen sah das aus, als sei die Sequenz „von allein weitergelaufen",
und beim nächsten Start standen die Punkte woanders. `_setze_punkt()` ignoriert
zusätzlich jeden Klick, solange `is_running` steht; die zweite Tür kostet nichts
und fängt das Rennen zwischen Worker-Ende und Hook.

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
`tests/test_logic.py` (`PLATTFORM_MODULE`) hält das fest: greift ein anderes Modul auf
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
- **`import_bundle()` schreibt sofort auf Platte, `export_bundle()` nicht.** Der Import kopiert ganze Sequenzordner an ihren Platz und ruft **`save_config()`** — er befüllt also nicht bloss den State. Mit einem frischen `AutoClickerState()` schreibt `save_config()` die Default-Config über die vorhandene `config.json`; die Tests in `test_logic.py` übergeben deshalb `import_config=False`. Für einen vollen Roundtrip die Pfad-Relativität nutzen: Datenordner + `config.json` in einen Temp-Ordner kopieren und vorher dorthin `os.chdir()` — die Konstanten in `persistence/paths.py` sind bewusst CWD-relativ.
- **Race-Condition-Sensibel**: Lange-laufende Loops im Worker (Boss-Watcher, Item-Scan) iterieren über shared dicts — Mutationen aus Editoren können während des Laufens passieren. Im Zweifel `dict(state.x)`-Snapshot unter Lock.
