# runtime — Sequenz-Ausführung

Details zur `CLAUDE.md` im Wurzelordner — dort stehen Befehle, Architektur
und die Regeln, die überall gelten. Claude Code lädt diese Datei, sobald eine
Datei aus `autoclicker/runtime/` gelesen wird. Was hier steht, gilt genauso; neue
Begründungen zu diesem Bereich gehören hierher, nicht in die Wurzel.

## Aktions-Wrapper: was über den Kern hinaus gilt

**Geprüft wird zweimal, und das zweite Mal ist das wichtige** (`_input_allowed()`).
Zwischen der ersten Prüfung und dem eigentlichen `send_*` liegen die Humanize-Pausen
— Mikro-Delays und periodische Breaks, also bis zu mehrere Sekunden. Wer in diesem
Fenster CTRL+ALT+H drückt oder das Spielfenster verlässt, bekam den Klick trotzdem:
die Antwort auf „darf ich?" war zu dem Zeitpunkt richtig, zum Zeitpunkt des Klicks
nicht mehr. Stop, Pause und Fokus werden deshalb **nach** allen Wartezeiten erneut
gefragt, und zwar in einer Schleife: während man auf die Rückkehr des Fensters
wartet, kann erneut pausiert werden — erst der gleichzeitig freie Zustand lässt die
Eingabe durch.

**Ein `False` von `safe_click`/`safe_key` heisst zweierlei** — verweigert (Stopp,
Block-Skip) oder vom System nicht angenommen (unbekannte Taste). `input_refused()`
trennt beides. Wer eine verweigerte Eingabe als „erledigt" meldet, lässt einen
Block-Skip gesetzt, und der **nächste** Block wird verschluckt: so stand es bei
der Taste, der ELSE-Taste und der Taste einer Boss-/Icon-Erkennung. Regel beim
Erweitern: **den Block-Skip verbraucht nur `execute_step`** (`_block_skip`), nie
ein Handler darunter. Der Item-Scan tat es selbst — im normalen Modus wurden die
bis dahin gefundenen Items trotzdem geklickt, im Immediate-Modus (ein Aufruf je
Slot) fiel nur EIN Slot weg. Ein Handler, der den Skip sieht, gibt `False`
zurück; `execute_step` macht daraus „übersprungen".

**Der Worker räumt auch nach einem Fehler auf.** `sequence_worker()` liegt
vollständig in `try/except/finally`: eine Ausnahme in einem Schritt beendete
früher den Thread, ohne den Schedule-Watcher zu stoppen, das Session-Log zu
schliessen oder `.run.json` abzuschliessen — zurück blieb ein Lauf, der laut
Statusdatei noch läuft, und ein Timer-Thread als Geist. Gemeldet wird die
Ausnahme, nicht verschluckt.

**Die END-Phase gehört zum sanften Ende, nicht zum Stopp.** CTRL+ALT+F und
das Zeitlimit laufen durch END; nach einem harten Stopp (CTRL+ALT+S,
Notbremse, `click_max_total`) entfällt sie, und ein Stopp mitten in END
beendet sie. `_run_end_phase` prüfte nur `quit_event`: nach CTRL+ALT+S stand
„Führe End-Sequenz aus … abgeschlossen" in der Konsole, Klicks verweigerte
`safe_click`, aber Erkennungs-Blöcke liefen — ein Boss-Scan samt LLM-Aufruf,
eine Minute nachdem gestoppt war.

**Ein Fehler in einem Handler beendet nicht den Hauptprozess.** Hotkeys und
Briefkasten-Befehle laufen über `run_safely()` in `main.py`. Gefangen war nur
`PlatformError`; jede andere Ausnahme lief aus der Hauptschleife, die Hotkeys
wurden abgemeldet und ein laufender Worker (Daemon-Thread) starb mitten im
Klick — ohne Aufräumen, ohne Zusammenfassung. Gemeldet wird mit Stack im
Logger; `KeyboardInterrupt` und `SystemExit` gehen weiter durch.

## Debug-Ausgabe vs. manueller Modus (`runtime/debug.py`)
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

**Ein Haltepunkt ist das Gate des manuellen Modus an genau EINER Stelle**
(`SequenceStep.breakpoint`, im Studio der Schalter „Haltepunkt" am Block, in der
Konsole `break <Nr>`, auf der Karte die Marke „⏸ halt"). Der manuelle Modus hält
vor jedem Block; der Haltepunkt hält vor diesem einen, und danach läuft die
Sequenz normal weiter. Es ist bewusst **kein** zweiter Mechanismus neben
`step_gate()`: dieselbe Rückfrage, dieselbe Tafel im Live-Run, dieselben
Entscheidungen — nur die dritte Kachel wechselt die Richtung („Normal weiter"
schaltet den Schrittmodus aus, „Ab hier schrittweise" schaltet ihn ein). Die
fünf Entscheidungen stehen als `GATE_COMMANDS` an einer Stelle; Konsole und
Studio sind zwei Wege zu einer Entscheidung, nicht zwei Gates.

Drei Dinge hängen daran:

- **CTRL+ALT+G gibt jedes Gate frei.** „Fortsetzen" ist die Taste, nach der man
  greift, wenn etwas steht — und vorher setzte sie die *Pause*, während der
  Worker im Gate stand: zwei Zustände übereinander, und nach dem Gate blieb der
  Lauf in der Pause hängen. `handle_pause()` prüft deshalb `state.gate_waiting`
  zuerst. Damit die Konsolenschleife das mitbekommt, liest `read_command()` mit
  einer Zeitgrenze (0,2 s) und sieht dazwischen auf das Befehls-Event — es war
  vorher ein blockierender `getch()`.
- **Wo gefragt wird, entscheidet der Start.** `handle_toggle(from_studio=…)`
  schreibt `state.run_from_studio`: ein Studio-Start bekommt die Tafel, ein
  Hotkey-Start die Konsole, der Countdown-Thread lässt stehen, was der
  Zeitplan gesetzt hat. Die Tafel steht dabei in **beiden** Fällen im
  Laufstatus — auch ein Konsolen-Lauf soll dem Studio zeigen, warum er steht,
  und seine Knöpfe kommen über denselben Briefkasten, den die Konsolenschleife
  ebenfalls abfragt. Nur die Tastatur liest ausschliesslich der Konsolenweg.
- **Der Briefkasten nimmt Befehle, solange ein Gate wartet** — nicht nur im
  Schrittmodus (`command_manual_action` prüft `gate_waiting`). Ein Haltepunkt
  hält einen Lauf an, der sonst gar nicht manuell ist.

Gespeichert wird das Feld, weil das Studio es setzt und der Hauptprozess die
Datei liest; in einer Loop-Phase hält es in jedem Zyklus. Neu-Format ohne
Migration, wie überall: fehlt das Feld, gibt es keinen Haltepunkt.

**Die Status-Zeile schreibt sich in EINEM Schreibvorgang** — `status_line()` in
`utils/console.py`, nicht `clear_line()` gefolgt von einem eigenen `print()`. Beides
zusammen ergibt zwar dieselben Zeichen, aber zwei einzeln geflushte Blöcke: ein echtes
Terminal fasst sie zusammen, eine **IDE-Konsole** (PyCharm-Run-Fenster, dort ist
`_REAL_CONSOLE` schon `False`) verarbeitet jeden Flush einzeln und kann die Zeile
dazwischen festschreiben. Dann bleibt mitten im Lauf eine alte Status-Zeile stehen,
statt überschrieben zu werden. Zusammen geschrieben gehört das `\r` untrennbar zu dem
Text, der es benutzt.

Die Löschbreite folgt der **vorher geschriebenen Zeile** (`_last_status_length`), nicht
mehr festen 80 Spalten: ein langer Punkt-Name liess den Rest der alten Zeile hinter der
neuen stehen. ANSI-Sequenzen zählen dabei nicht mit — sie belegen keine Spalte.

Wer eine Meldung ausgeben will, die **stehen bleiben soll** (Screenshot-Dateiname,
Timeout, Fokus-Verlust), räumt vorher mit `clear_line()` ab oder stellt der Meldung ein
`\n` voran. Ohne das überschreibt sie nur den Anfang der Status-Zeile und lässt den Rest
daneben stehen.

## Briefkasten und Laufstatus

- `autoclicker/mailbox.py` — der **Rückweg** zu `runtime/status.py`: dort schreibt der
  Hauptprozess, was läuft, hier legt das Studio ab, was passieren soll. Ein Briefkasten,
  kein Log — wer liest, leert ihn, und zu alte Befehle fliegen weg (siehe
  `editors/sequence_studio/CLAUDE.md`). Liegt bewusst **nicht** unter `runtime/`: dessen `__init__` zieht den
  Worker samt `imaging` und `winapi` nach, und das Fenster braucht nichts davon.

  **`status.py` ist reine Anzeige und darf den Lauf nie stören** — jeder Schreibfehler
  wird geschluckt. Drei Schreiber führen ihren Teil ein, statt ihn zu ersetzen: der
  Worker kennt Zyklus und Phase, `execute_step` den Block, die Warteschleifen
  (`waiting_for()`) das, worauf gerade gewartet wird — keiner das Ganze.
  Geschrieben wird höchstens alle 200 ms; Phasen- und Zykluswechsel umgehen die
  Drossel (`immediately=True`), weil ein übersprungener Sprung nicht nachgeholt wird.

  **Ein wartender Lauf ist kein toter Lauf.** Der Leser erkennt einen abgestürzten
  Lauf am Alter des Zeitstempels (älter als 5 s = verwaist), und das geht nur, wenn
  ein lebender Lauf ihn frisch hält. Geschrieben wird sonst pro Schritt — aber ein
  Schritt kann minutenlang dauern (Farb-Trigger bis `pixel_wait_timeout`,
  Boss-Watcher bis `llm_watcher_timeout`). Deshalb ruft **jede Schleife, die den
  Worker länger aufhält**, `status.heartbeat(state)` — oder `status.waiting_for()`,
  das über dieselbe Funktion schreibt und dabei noch sagt, worauf gewartet wird.
  Heute: `_wait_loop`, `_color_loop`, der Boss-Watcher, das Warten auf einen
  Zeitplan (`_wait_for_schedule`) **und die Pause** (`wait_while_paused` in
  `runtime/actions.py`). Die Pause fehlte zuletzt: sie schlief in `utils/io.py`
  mit `time.sleep`, ohne Lebenszeichen — nach fünf Sekunden CTRL+ALT+G stand
  „KEIN HAUPTPROZESS" im Studio. Sie schreibt jetzt `kind: pause` **über** den
  Warte-Zustand des Blocks und stellt ihn danach wieder her (`status.current_waiting()`),
  und sie wartet auf `stop_event` statt zu schlafen. Ein Test hält das fest — ohne
  die Aufrufe sähe genau der Lauf tot aus, der gerade wartet, und das ist der Fall,
  für den man die Ansicht aufmacht.

  **Ein einzelner Aufruf kann länger dauern als jede Schleife** — deshalb hält
  zusätzlich ein eigener Thread den Stempel frisch (`status.start_heartbeat()`,
  einmal pro Sekunde, gestartet und gestoppt von `sequence_worker`). Ein
  synchroner LLM-Boss-Scan (`llm_async` ist aus) steckt an einem kalten Modell
  über eine Minute in EINER HTTP-Antwort, ein erster OCR-Aufruf lädt Modelle
  nach; dazwischen ruft niemand `heartbeat()`, und das Studio zeigte „kein
  Hauptprozess" über einem Lauf, der nur wartete. „Verwaist" heisst „der Prozess
  ist weg" — und mit dem Prozess stirbt auch dieser Thread. Die Aufrufe in den
  Schleifen bleiben: sie schreiben zugleich, **worauf** gewartet wird. Zwei
  Regeln: der Takt stoppt **nach** dem Warten auf den LLM-Thread und **vor**
  `finish_run()` (sonst schriebe ein letzter Takt über die Zusammenfassung), und
  weil jetzt mehrere Threads schreiben, liegt alles in `status.py` hinter
  `_lock` — nie unter `state.lock` nehmen, `_counters()` sperrt ihn darin.

## Einstieg mitten in der Sequenz und Folgesequenz

**„Ab hier starten" ist ein Start mit Einstieg, kein zweiter Lauf-Modus**
(`block_start` → Briefkasten `start_from` → `command_start_from`). Geschickt
werden Datei und Position — derselbe Helfer wie beim Block-Test
(`_selected_position()` im Studio, `locate_step()` in `persistence`) —, der
Handler legt `state.start_from = (Art, Phasen-Index, Block)` ab und ruft dann
`command_start`, also denselben Weg wie der Start-Knopf. Der Worker holt den
Einstieg **einmal** ab (`_take_start_from`, verbraucht ihn und prüft, ob es den
Block noch gibt — sonst Meldung und Start von vorn) und reicht ihn an
`_run_main_loop`/`_run_loop_phases`/`_run_end_phase`: alles davor wird
übersprungen, bei einem Loop-Block auch INIT; eine zeitgesteuerte Einstiegsphase
läuft sofort (wer dort einsteigt, meint jetzt). Ab dort ist es ein normaler Lauf
— die weiteren Durchläufe der Phase, alle folgenden Phasen und der nächste
Zyklus vollständig, ein Neustart bei INIT. Drei Regeln: **ein abgelehnter Start
räumt den Einstieg weg** (sonst spränge der nächste Hotkey-Druck mitten in die
Sequenz), **der Laufstatus sagt, wo eingestiegen wurde** (`started_from`, im
Kopf des Live-Runs), und ein Einstieg in END lässt INIT und alle Zyklen aus —
`_run_main_loop` gibt dann 0 Zyklen zurück.

**Eine Folgesequenz ist ein verzögerter Start, keine Verkettung im Worker**
(`Sequence.next_sequence` + `next_delay`, im Studio „Danach starten“ /
„Pause davor“ unter SEQUENZ). Der Worker führt weiterhin genau EINE Sequenz
aus; er legt beim Aufräumen nur `state.next_start = (Name, Pause, vorige)`
ab — im selben Lock wie `is_running = False`, sonst gäbe es einen Moment mit
freiem Hauptprozess ohne die schon feststehende Folge. Abgeholt wird im
Main-Thread (`start_next_if_pending()` aus `_check_commands`, neben
`reload_if_pending`): Datei laden, `activate_sequence`, `_start_countdown` —
also derselbe Countdown wie beim Zeitplan und am Ende derselbe
`handle_toggle()` wie CTRL+ALT+S. Deshalb bleiben beide Sequenzen
eigenständig: eigener Laufstatus, eigenes Session-Log, eigene Zusammenfassung.
Die Alternative (ein Block „Sequenz X ausführen“) steht weiter in `IDEAS.md`
und ist etwas anderes.

Vier Regeln:

- **Nur nach einem regulären Ende** (`_ended_regularly()` in `worker.py`, dieselbe
  Reihenfolge wie `_end_reason()`): alle Zyklen durch und CTRL+ALT+F ja — bei
  endlosen Zyklen ist F der einzige Weg zum Ende. Stopp, Notbremse, Fehler,
  Programmende nein, und das **Zeitlimit** auch nicht: `session_max_hours` ist
  eine Obergrenze der Sitzung, eine Folgesequenz danach hebelte sie aus. Entfällt
  sie, sagt die Konsole es.
- **Was dazwischenkommt, gewinnt.** Läuft beim Abholen schon etwas oder steht ein
  Countdown, fällt die Folge weg; in der Pause bricht CTRL+ALT+S ab wie jeden
  Countdown.
- **Referenz per Namen, gesucht wie beim Laden** (`find_sequence_path()`, der
  Ordner heißt nicht wie die Sequenz). Ein toter Name wird am Laufende gemeldet,
  von der Diagnose vorher (mit Sprungmarke `field: "seq-next"`), und in der
  Studio-Auswahl bleibt er als „(fehlt)“ stehen statt still auf „keine“ zu
  springen. Nur „danach diese nochmal“ zieht beim Umbenennen mit.
- **`_start_countdown()` leert `stop_event`.** Der Worker hinterlässt es gesetzt;
  ungeleert brach jeder Countdown nach einem Lauf sofort mit „Zeitplan
  abgebrochen“ ab. Das war schon vorher ein Fehler des Zeitplans, er fiel nur
  nicht auf, solange man ihn vor dem ersten Lauf stellte.

## Laufstatus im Live-Run

**Die Phasen stehen alle nebeneinander**, die laufende breit (`_phase_overview()`
im Worker, Feld `phases`). Sie aus der geöffneten Sequenz zu holen wäre geraten —
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
Schlüssel in den Laufstatus (`block_set_type`), die Brücke übersetzt ihn in Farbe und
Marke. `runtime/` darf die Ansicht nicht importieren, und zwei Kopien der
Klassifikation wären zwei Stellen, an denen ein neuer Block-Typ vergessen wird —
`BLOCK_LABELS`/`BLOCK_COLORS` bleiben bei der Ansicht, das ist Anzeige.

**Beim aktuellen Block steht, worauf er wartet** (`status.waiting_for()`, Feld `waiting`).
„seit 12 s" allein beantwortet die Frage nicht: bei einer Wartezeit von 15 s sind
zwölf Sekunden fast geschafft, bei einem Farb-Trigger mit 300 s Timeout haben sie
gerade erst angefangen. Der Kasten zeigt deshalb Restzeit bzw. Timeout-Countdown,
und beim Farb-Trigger zusätzlich Soll gegen gemessenes Ist, den Abstand samt
Toleranz und **was nach dem Timeout passiert** (`_timeout_consequence()` — dieselbe Kette
wie `_handle_color_wait_timeout`).

Drei Eigenschaften, an denen das hängt:

- **Der Live-Ausschnitt beantwortet die Anschlussfrage.** „RGB(30, 32, 34)" sagt
  nicht, WAS an der Stelle zu sehen ist — ein 49×49-Ausschnitt tut es (grauer
  Knopf, Ladebildschirm, Popup davor). Die Laufzeit nimmt ihn höchstens einmal pro
  Sekunde auf (`_LIVE_INTERVAL`) und schreibt ihn als Data-URL mit; das sind rund
  3 KB in einer Datei, die sonst 400 Byte hat. Ohne Pillow gibt es kein Bild und
  entsprechend keinen leeren Rahmen.
- **Zeiten stehen absolut in der Datei** (`since`, `until`), nicht als Restwerte. Der
  Worker tickt im Sekundentakt, die Ansicht fragt alle 500 ms — mit Restwerten
  ruckelte der Countdown im Raster des Workers. Beide Prozesse laufen auf derselben
  Maschine, also auf derselben Uhr.
- **Jede Warteschleife meldet sich selbst wieder ab**, in einem `finally` und
  ungedrosselt. Deshalb liegen die Schleifenrümpfe in eigenen Funktionen
  (`_wait_loop`, `_color_loop`) — sonst stünde nach „Farbe erkannt" noch
  „wartet auf Farbe" da, während der Klick längst raus ist. Der Blockwechsel räumt
  zusätzlich ab (`"warten": None` in `execute_step`).
- **`waiting_for()` ersetzt das Lebenszeichen**, es kommt nicht dazu: es schreibt über
  dieselbe Funktion und schiebt `stamp` genauso vor.
- **Auch eine reine Wartezeit zeigt den Ausschnitt** — um die Stelle, die danach
  dran ist (`wait_with_pause_skip(..., point=)`, `_live_target()` in
  `runtime/steps.py`; bei ELSE-Klick und „Vor Farbprüfung" deren Stelle). Die
  Frage beim Hinsehen ist dieselbe wie beim Farb-Warten: steht da, wo gleich
  geklickt wird, das Richtige? `_live_point()` schreibt dieselben Felder wie
  `_color_wait_status()`, und die Seite zeichnet beide mit **einer** Funktion
  (`livePixelBox`) — ein Test hält die Namen gegeneinander. Eine Taste und ein
  Punkt ins Leere bringen keine Stelle mit, also kein Bild statt eines von (0, 0).

**Unter dem Block steht, was der letzte Item-Scan gesehen hat** (`last_scan`,
geschrieben von `_report_last_scan()` in `runtime/steps.py`, überschrieben vom
nächsten Scan, stehen gelassen in der Zusammenfassung). Je Item EINE Kachel mit
Anzahl, Klicks, Kategorie und Priorität — gezählt wird auch, was der Modus
danach wegfiltert, denn „erkennt er das?" ist die Frage beim Hinsehen; geklickt
ist grün umrandet. `execute_item_scan(report=…)` liefert dafür je Slot
`(Slot, Item oder None, Ausschnitt)`. **Das Bild steht nicht im Laufstatus**, nur Ordner und
Dateiname: die Datei wird fünfmal pro Sekunde geschrieben. Die Brücke hängt es
an (`_last_scan_images`, gemerkt am mtime) und nimmt vom Dateinamen nur den
Namen — er kommt aus einer Datei.

Daneben steht **ein Screenshot der gescannten Stelle**: der Bereich um alle
Slots plus `FRAME_MARGIN`, aufgenommen **einmal je Block und vor dem ersten
Slot** (`report.frame`, `_scan_frame()` in `runtime/item_scan.py`) — im
Immediate-Modus also vor dem ersten Klick, danach sähe das Inventar anders aus
als das, was gescannt wurde. Im Fenster-Modus kommt er aus der
Fensteraufnahme, die der Scan ohnehin macht, sonst ist es eine kleine
Aufnahme mehr. Hier stand zuerst ein Bild aus den zusammengesetzten
Slot-Ausschnitten auf dunklem Grund (`imaging.compose_regions`) — genau das,
was ausgewertet wurde, aber es las sich nicht als Screenshot, und „den
Screenshot sehe ich nicht" war die Rückmeldung. Es bleibt der Rückfall, wenn
die Aufnahme scheitert. Das Bild liegt als `.last-scan.png` neben `.run.json`
(längere Kante höchstens 900 px); die Seite legt je Slot einen Rahmen in
Prozent darüber — in den Farben des Scans-Reiters (`--slot-ok`/`--slot-empty`,
dieselbe Frage auf demselben Spielbild), geklickt gefüllt. „Geklickt" gilt dem
**Slot**, nicht dem Item: gemerkt wird die Klickstelle.

**Am Ende bleibt die Zusammenfassung stehen.** Hier wurde die Statusdatei
früher gelöscht, und damit war die Live-Ansicht genau in dem Moment leer, in dem
man sie ansieht: direkt nachdem etwas fertig geworden ist. `finish_run()` schreibt
jetzt einen **abgeschlossenen** Lauf (`active: False` plus `end`, Grund, Dauer,
gelaufene Zyklen, Zähler), bis der nächste Start ihn überschreibt. Drei Fälle
unterscheidet der Leser am Inhalt, nicht am Vorhandensein der Datei:

| Datei | bedeutet |
|---|---|
| `active: True`, `stamp` frisch | läuft |
| `active: True`, `stamp` älter als 5 s | abgestürzt (verwaist) |
| `active: False` mit `end` | fertig, Zusammenfassung |

Die Altersregel gilt **nur für den ersten Fall** — eine Zusammenfassung ist
Vergangenheit und darf alt sein. Was einen *Moment* beschreibt (Block, Warten),
fällt dabei weg; wo Schluss war (`phase_pos`), bleibt: das ist die zweite Frage
nach „warum". Ohne `state` — ein Lauf, der gar nicht erst anlief — wird
weiterhin gelöscht, denn eine Zusammenfassung ohne Zahlen wäre keine.

**In die Live-Ansicht wird nur auf der Flanke gesprungen** (nichts → läuft). Solange
etwas läuft, bleibt die gewählte Ansicht stehen; sonst käme man während eines
Durchgangs nicht mehr in den Editor zurück.

## Sequenz-Modell
Eine `Sequence` hat 3 Phasen: `init_steps` (einmalig), `loop_phases` (mehrere `LoopPhase`s je mit eigenem `repeat`-Counter, optional `scheduled_start` für Uhrzeit-Trigger), `end_steps` (einmalig nach allen Zyklen). Jeder `SequenceStep` ist polymorph: kann Klick, Key-Press, Wait-Pixel-Trigger, Item-Scan, Boss-Scan, Boss-Watcher (kontinuierliche Überwachung), Wait-only oder Screenshot sein — gesteuert über die gesetzten Felder. `else_config` definiert Fallback bei Trigger-Miss.

**Ein Zyklus ohne Schritt ist kein Zyklus.** Eine Sequenz, deren Phasen ALLE
auf eine Uhrzeit warten („täglich um 07:00"), drehte vorher in `_run_main_loop`
ohne einen einzigen Schritt — gemessen 133 Umläufe in einer halben Sekunde,
jeder mit einer Statusdatei —, und mit `total_cycles=5` war sie vorbei, bevor
die Uhrzeit je erreicht wurde. Dasselbe bei leeren Phasen (das Studio legt genau
so eine an). `_run_loop_phases` sagt jetzt, wie viele Phasen liefen; bei null
zählt der Zyklus nicht, und `_wait_for_schedule` schläft in Sekundenschritten
bis zum nächsten Termin (mit `waiting_for` für die Live-Ansicht, Stopp/Pause/
sanftes Ende greifen weiter) — oder beendet den Lauf mit Ansage, wenn es gar
keinen Zeitplan gibt.

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
(max. Scans, Timeout) und macht danach weiter. `else_applies()` in
`bridge_contract.py` (über `bridge.py` weiterhin exportiert) hält
dieselbe Liste für die Anzeige: **ohne Auslöser gibt es den ELSE-Abschnitt gar
nicht** — dieselbe Regel wie beim Farb-Trigger, den es bei Scans und Screenshot
auch nicht gibt.

**Fällt der Auslöser weg, fällt das ELSE mit** (`_else_cleanup()`): wer den
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

## Nachprüfung: „hat die Aktion gewirkt?"

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
`GATE_RUN` und nie stumpf `True`. Die Übersetzung macht `_gate_after_else()`; nur
`restart`/`skip_cycle` werden zu `GATE_STOP`. Step-Handler, die die else-Aktion als
Letztes tun und danach nichts mehr ausführen (Item-/Boss-/Icon-Scan), dürfen weiterhin
`return execute_else_action(...)` — dort gibt es keine nachgelagerte eigene Aktion, die
irrtümlich noch feuern könnte.

## Boss-Scan vs. Boss-Watcher
- **Boss-Scan**: Einmaliger Scan in einem Step. Wenn nichts erkannt → `else_config` oder Default-Action.
  Die Default-Action kann **weniger als ein Boss**: `VALID_BOSS_DEFAULT_ACTIONS`
  (`models.py`) sind skip, skip_cycle, restart und Item-Scan — ohne erkannten Boss
  gibt es keinen Punkt und keine Taste, die Felder dafür sitzen am Boss. Das Studio
  bot trotzdem alle sechs Kacheln an, und „Punkt klicken" liess sich speichern und
  tat zur Laufzeit nichts. Laufzeit, Konsole und Studio lesen jetzt dieselbe Liste;
  ein Altwert in einer Datei wird einmal je Lauf gemeldet.
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

**Item-Auto-Lernen** (opt-in pro Scan, `ItemScanConfig.learn_unknown`): `execute_item_scan()` lernt unbekannte, nicht-leere Slot-Inhalte als neue Items **des Scans, der gerade läuft** (`config.items`, Kategorie 'Auto', Template + Marker) — **geparkt** mit `enabled=False`, damit sie nicht ungeprüft geklickt werden; das Studio zeigt sie mit ihrem Schalter. Dedup per Template-Match gegen alle Items dieses Scans, auch die geparkten.

**Auto-Lernen ändert nie, was geklickt wird — auch nicht über eine Grössenvariante.** Erkennt die Dedup-Prüfung ein bekanntes Item nur über eine *skalierte* Vorlage (anderer Slot-Typ), hing der Lauf die neue Grösse als Variante an dieses Item — war es eingeschaltet, klickte der nächste Zyklus sie ungeprüft. Genau das Ergebnis, das `_check_profile_match()` für Items ausdrücklich verweigert (nur Vorlagen in Slot-Grösse, keine halbgültigen Resize-Treffer). Heute: an ein **geparktes** Item darf die Variante direkt (es wird erst nach dem Hinsehen eingeschaltet), bei einem **eingeschalteten** wird sie ein eigenes, geparktes Item, und die Konsole nennt, wem es ähnelt. Eine Gegenprobe in `tests/mutation_check.py` (`auto-learn-active-variant`) hält das fest.

Hier stand einmal „nur nach `state.global_items`, nie in die Scan-Config" — aus der Zeit des globalen Bestands. Seit der Scan seine Items besitzt, ist `state.global_items` nur noch die Konsolen-Ansicht auf `state.active_item_scan`, also den Scan, den der Item-Editor zuletzt offen hatte: mit zwei Item-Scans in einer Sequenz landete ein aus Scan B gelerntes Item in Scan A (und wurde gegen dessen Items dedupliziert), ohne offenen Scan meldete jeder Zyklus „Kein Item-Scan zum Speichern gewählt". Zeigt die Ansicht zufällig auf den laufenden Scan, wird sie mitgezogen — sonst schriebe ihr nächstes `done` die Liste ohne das Item zurück (`flush_item_scan_context` ersetzt `cfg.items`).

Die Items heissen erst 'Auto <Slot>'; **die LLM-Benennung läuft bewusst NICHT im Scan** (würde den Worker pro Item bis `llm_timeout` blockieren), sondern manuell über den Item-Editor-Befehl `autoname` (`editors/item_editor/commands.py::handle_autoname_command`), der `llm_vision.suggest_item_name()` aus den gespeicherten Templates aufruft.
