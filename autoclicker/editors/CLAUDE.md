# editors — Konsolen-Editoren, Aufnahme, Klick-Runde

Details zur `CLAUDE.md` im Wurzelordner — dort stehen Befehle, Architektur
und die Regeln, die überall gelten. Claude Code lädt diese Datei, sobald eine
Datei aus `autoclicker/editors/` gelesen wird. Was hier steht, gilt genauso; neue
Begründungen zu diesem Bereich gehören hierher, nicht in die Wurzel.

## Tests für die Konsolen-Editoren

**Die Konsolen-Editoren sind angefangen, nicht fertig.** Sie standen lange
vollständig ausserhalb der Suite (rund 3.400 Zeilen). Der Einstieg lief über das,
was **geteilt** ist: `editors/_detection_capture.py` gehört dem Boss- *und* dem
Icon-Editor, ein Test deckt dort also zwei Editoren ab — Tastenabfrage,
Region-Eingabe, Marker-Aufnahme, jeweils mit der Eigenschaft, um die es geht
(**Fehleingabe wiederholen statt abbrechen**). Dazu `_apply_item_rename()`, weil
am Namen drei Dinge hängen: Bestand, Template-*Datei* und jede Scan-Referenz.

Der Rest ist offen und soll **einer nach dem anderen** kommen, nicht am Stück:
`item_editor/` (Lernen, Autoscan, Befehle), `boss_scan_editor.py`,
`icon_scan_editor.py`. Der Weg dorthin ist immer derselbe — erst in Stufen
zerlegen, dann mit einer Tastenfolge füttern; die Zerlegung ist der eigentliche
Gewinn, die Tests fallen danach fast von selbst an.

**Erledigt: `sequence_editor/loops.py`** — und zwar in umgekehrter
Reihenfolge, die sich bewährt hat: **erst die Tastenfolgen, dann der Umbau.**
`tests/contract/loop_phase_editor.py` hielt das Verhalten fest (41 Prüfungen,
auf dem alten Code grün), danach wurde `edit_loop_phases()` zerlegt (Komplexität
52 → unter 11): die Schleife liest nur noch und fragt `_command()`, wer
zuständig ist; jeder Befehl ist eine eigene `_cmd_*`-Funktion. Ein Befehl, der
dazukommt, ist eine Funktion und eine Zeile in `_command()` — nicht ein weiterer
Zweig in einer Schleife, die schon 200 Zeilen hat.

## Editor-Konventionen (einheitliche Substanz)
Alle Editoren sollen sich gleich anfühlen — beim Erweitern daran halten:
- **Exit**: `done`/`d` = übernehmen, `cancel`/ESC/`q` = abbrechen (via `is_cancel()`), leere Eingabe meist „zurück". Abbruch immer mit `[ABBRUCH]`-Tag melden (nicht `[CANCEL]`).
- **Transaktional**: Editoren mit Mehrfach-Bearbeitung (Item, Slot) machen `copy.deepcopy`-Snapshot am Start, mutieren in-memory, speichern bei `done`; `cancel` stellt den Snapshot wieder her (und schreibt ihn zurück, falls Unterfunktionen wie Preset-Laden zwischendurch auf Platte geschrieben haben).
- **Fehleingabe wiederholen statt abbrechen**: Zahlen-/Tasten-/Koordinaten-Eingaben fragen bei Tippfehler erneut. Geteilte Helfer in `editors/_detection_capture.py`: `select_scan_region()` (Region), `prompt_key()` (Taste), `capture_markers()` (Farb-Marker).
- **Bearbeiten = aktuellen Wert vorauswählen**: `interactive_select(..., default=<idx>)` bei Edit-Flows, damit Enter nichts überschreibt.
- **Vor Editoren mit Konsolen-Input**: `_block_if_recording(state)` + `_block_if_running(state)` aus `handlers.py` (sonst kollidiert Konsolen-Input mit Worker/Recorder). Beide melden selbst und geben `True` zurück, wenn der Handler abbrechen soll.
- **Feedback-Bausteine** aus `utils/console.py` nutzen: `ok/err/warn/info/hint`, `header`, `breadcrumb`, `cmd_hint`, `describe_color` — keine rohen ANSI-Strings.
- **Geteilte Feld-Abfragen** stehen in `editors/_item_fields.py`:
  `ask_priority()` und `ask_confirm_click()`. Sie standen vier- bzw.
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
  Abbruch-Zeichen — dafuer gibt es `CANCELLED`.
- **Mehrfachauswahl aus einer Liste**: `multi_select()` aus `editors/item_scan_editor.py`
  (`<Nr>`, `<Von>-<Bis>`, `all`, `clear`, `show`, `done`, `cancel`, optional ein eigener
  Befehl wie `new <Slot-Nr>`). Sie stand vorher zweimal ausgeschrieben da — für Slots und
  für Items —, und eine Korrektur an der einen ging an der anderen vorbei.

**Assistenten in Stufen zerlegen, nicht am Stück schreiben.** `edit_item_scan()` war
450 Zeilen mit 125 Verzweigungen; jetzt ruft sie `_step_presets` → Auswahl → Auswahl →
`_step_tolerance` → `_step_auto_learn` und speichert. Jede Stufe gibt ihr Ergebnis
zurück oder signalisiert Abbruch (`None` bzw. `False`). Das ist auch der einzige Weg, an
Editor-Code überhaupt Tests zu bekommen: was nur `safe_input` braucht, lässt sich mit
einer Tastenfolge füttern — `multi_select` hat so 24 Tests, wo vorher keiner war.

## Einfüge-Aufnahme („Ab hier aufnehmen“)

**„Ab hier aufnehmen" ist eine Aufnahme mit Ziel, kein zweiter Recorder**
(`block_record_start` → Briefkasten `record_from` → `command_record_from`).
Derselbe Hook, dieselben Marker; nur `stop_recording()` biegt am Ende ab
(`state.recording_insert`) und spleisst die Schritte über
`_finish_insert_recording` hinter den gewählten Block der **Datei** — Punkte mit
dem Bestand der Zielsequenz als Dedup-Kontext (`points_for_events(existing=…)`),
eine geladene Fassung derselben Sequenz über `activate_sequence`. Eine neue
Phase (`CTRL+ALT+SHIFT+P`) wird abgelehnt: eingefügt wird in genau eine. Die
Tafel im Inspektor zeigt dieselbe Live-Ausgabe wie der Werkzeuge-Reiter
(`wzFillRecordingOutput`, zweiter Einbauort), und ihr Wächter liest „nicht
aktiv" erst nach einem ersten Lebenszeichen als „fertig" — beim ersten Blick
nach dem Start hat der Hauptprozess den Briefkasten oft noch gar nicht geholt.
Nach dem Neuladen sind die eingefügten Blöcke **gewählt** (`select_range`, aus
der Blockzahl vor und nach der Aufnahme): an einer echten Einfügung ging der
erste Klick nach der Rückkehr aus dem Spiel verloren, und von drei neuen
Blöcken wurden nur die letzten zwei gelöscht.

## Sequenz-Aufnahme (`editors/sequence_recorder.py`)
Aufgezeichnet wird, was das Spielen ausmacht: **Linksklick, Tastendruck**,
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
  eine Taste oder gar nichts), wird er verworfen und gemeldet — `check_markers()`.
- **Der Marker hält nur die Uhr an.** Die Zeit *bis* zu seinem Drücken bleibt echte
  Wartezeit, die Zeit *danach* fällt weg — sie ist genau das Warten, das die Bedingung
  ersetzt. Bliebe sie stehen, würde die Sequenz erst auf die Farbe warten UND danach
  nochmal die volle Zeit schlafen (in der echten Aufnahme: 434 s).

Warten an einer **anderen** Stelle als der geklickten kann die Aufnahme bewusst nicht —
dafür gibt es `wait <Punkt-Nr> color` im Editor. Der Marker wäre sonst wieder auf eine
Position angewiesen, die beim Drücken niemand bewusst wählt.

### Die fünf Marker

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
neuen Marker baut, beantwortet zuerst diese Frage; sie entscheidet über `points_for_events`.

**Aufbereitet wird in fester Reihenfolge**, jede Stufe entfernt eine Sonderform, damit
die nächste sie nicht mehr kennen muss:

1. `merge_regions()` — zwei `REC_REGION`-Ecken → **ein** `REC_SCREENSHOT`
   mit Rechteck. Danach existiert `REC_REGION` nicht mehr. Eine einzelne Ecke wird
   verworfen und gemeldet, **nicht** still zu Vollbild degradiert — das wäre etwas
   anderes als das Gewollte.
2. `phase_boundaries()` — Grenzen **raus** aus dem Strom, gemerkt als Schritt-Indizes.
   Sie zu überspringen statt zu entfernen reichte nicht: eine Grenze wäre dann das
   „vorherige Ereignis" des nächsten Schritts, und dessen Wartezeit würde ab dem
   Tastendruck statt ab der letzten echten Aktion gemessen (aus 6 s würde 1 s).
3. `check_markers()` — haltlose Warte-Marker weg.

Danach ist `steps_from_events()` frei von Sonderfällen, und `build_phases()`
schneidet die fertige Liste an den gemerkten Grenzen in Loop-Phasen.

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

**Jeder Druck macht eine neue Loop-Phase auf, ohne Obergrenze** (`build_phases()`).
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

### Was NICHT in die Aufnahme gehört

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

**Der Klick auf einen Studio-Knopf ist keine Spielaktion — und welches Fenster
den Klick bekam, sagt `clicked_window()`** (`editors/_click_window.py`, geteilt
mit der Klick-Runde). Start und Stopp sind im Studio echte Knöpfe; ihr Klick darf
nicht als Block in der Sequenz landen. Gefiltert wird deshalb, was im
Studio-Fenster ankommt — und zwar am Fenster **unter dem Zeiger**, nicht am
Vordergrund. Hier stand `get_foreground_window_title()`, und damit fehlte in
**jeder** Studio-Aufnahme der erste Schritt: „Aufnahme starten" liegt im Studio,
also ist das Studio vorn, und der erste Klick ins Spiel holt es erst nach vorn.
Im Hook steht zu diesem Zeitpunkt noch das Studio als Vordergrund — der Klick
galt als Studio-Klick und flog raus. Am Ende dasselbe umgekehrt: „Aufnahme
stoppen" bei vorn stehendem Spiel kam als Spielklick in die Sequenz. Gemessen an
einer echten Aufnahme (`all_dayli`): Loop 1 beginnt ohne den Öffner-Klick, den
jede andere Phase hat, und der letzte Schritt `(1347, 709)` trägt `#1C2333` — das
Panel-Grau des Studios.

Es ist derselbe Fehler, der einmal in der Klick-Runde steckte (s. u. bei
„Koordinaten nach einem Bildschirm-Umbau"), und er stand zweimal im Baum, weil
die Frage zweimal beantwortet war — die Runde richtig, die Aufnahme nicht.
Deshalb **ein** Helfer für beide Hook-Editoren; wer einen dritten Maus-Hook baut,
fragt dort. Der Rückfall auf den Vordergrund bleibt: liefert die geometrische
Frage nichts, ist die alte Antwort besser als gar keine. Vier Fälle stehen im
Test — beide Richtungen des Fensterwechsels, dazu Vordergrund gleich und
Vordergrund als Rückfall.

**Rechtsklick wird bewusst nicht aufgezeichnet — aber gezählt**: der Autoclicker
kann gar keinen ausführen (`send_click` ist auf `LEFTDOWN`/`LEFTUP` festgelegt, es
gibt kein Modellfeld und keinen Editor-Befehl). Ihn mitzuschneiden hiesse, etwas
aufzunehmen, das beim Abspielen zum Linksklick wird. Ihn zu **verschweigen** war
aber der schlechtere Fehler: wer im Spiel rechts geklickt hat, bekam eine Sequenz,
der still ein Schritt fehlt. Der Hook meldet ihn deshalb über einen zweiten
Callback (`install_mouse_hook(on_lbutton_down, on_rbutton_down)`), der Recorder
zählt ihn in `state.recording_right_clicks` — nach denselben Regeln wie den
Linksklick (nicht pausiert, nicht im Studio-Fenster) — und sagt beim Stoppen, wie
viele fehlen; das Studio zeigt den Zähler in der Aufnahme-Tafel (`right_clicks`
in `.recording.json`). Gemeldet wird **vor** der Auswertung: eine Aufnahme aus
lauter Rechtsklicks ist „nichts aufgezeichnet", und genau dann muss der Grund
dastehen. Wer das Abspielen nachrüstet, braucht die ganze Kette:
`winapi` → Modellfeld → `safe_click` → Serializer-Default → Editor-Anzeige.

**Das Mausrad ist ersatzlos gestrichen** — Hook-Zweig, `REC_SCROLL`,
`SequenceStep.scroll`, `safe_scroll`/`send_scroll`, der Editor-Befehl `scroll`,
das Studio-Feld und der Config-Schalter `record_scroll`. Es drehte in Idle Clans
nur die Ansicht und blähte jede Aufnahme mit Schritten auf, die nichts tun; im
Studio war es ausserdem ein Fremdkörper (kein eigener Typ, das Feld nur
sichtbar, wenn eine Aufnahme es mitgebracht hatte). Ein `"scroll"` in einer
alten `sequence.json` ist ein unbekannter Schlüssel wie jeder andere: der Loader
ignoriert ihn, der Schritt wird zum Klick auf seinen Punkt. Wer es je wieder
braucht, holt die ganze Kette aus der Historie (`git log -S send_scroll`).

## Koordinaten nach einem Bildschirm-Umbau

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
| `reclick` | Punkte-Menü **oder** Studio → Werkzeuge | die Sequenz einmal von Hand **nachklicken** (`editors/reclick.py`) |

**Der Unterschied ist der Klick, und er entscheidet.** `walk` fasst nichts an —
also bleibt das Spiel stehen, wo es steht, und ein Punkt im dritten Untermenü
ist gar nicht sichtbar: man sieht den Desktop und rät. Bei `reclick` geht jeder
Klick ans Spiel, die Oberfläche öffnet sich genau wie im Lauf, und **der nächste
Punkt liegt dann vor einem**. Man spielt die Sequenz einmal von Hand durch, und
hinter jedem Klick steht die neue Stelle im Punkt.

**Die Runde arbeitet auf PUNKTEN, nicht auf einer Sequenz.** Aus der Sequenz
kommt genau eine Sache: die Reihenfolge, in der ihre Punkte geklickt werden.
Danach ist sie uninteressant — die Datei wird nicht angefasst, und die im
Hauptprozess **geladene** Sequenz wechselt ausdrücklich nicht (`prepare_reclick(state,
seq)` nimmt sie als Argument). Sie zu aktivieren hiesse, dass ein Druck auf
`CTRL+ALT+S` nach der Runde etwas anderes startet als vorher.

**Geschrieben wird erst am Schluss, und nur auf ausdrückliches Übernehmen**
(`CTRL+ALT+J`, „Übernehmen" im Studio). Bis dahin stehen die neuen Stellen in
`state.reclick_set` und die Punkte sind unverändert — auch im Speicher.
Damit ist ein Abbruch folgenlos: `stop_reclick(..., apply_result=False)` wirft
die Liste weg, es gibt nichts zurückzudrehen. Verworfen wird beim Schliessen des
Studio-Fensters (`reclick_on_close()` — die Runde gehört dem Fenster,
das sie gestartet hat) und beim Beenden des Programms.

Vorher schrieb **jeder** Ausgang. In einer echten Runde hat das drei Punkte auf
Fensterdekoration gesetzt und beim Beenden gespeichert.

**Und nach dem Übernehmen zieht der Hauptprozess nach.** Eine Runde aus dem
Studio arbeitet auf einer eigenen Kopie von der Platte. Hatte der Hauptprozess
dieselbe Sequenz geladen, hielt sein Speicher danach die ALTEN Stellen: ein
Start per Hotkey klickte daneben, und das nächste `save_points()` (CTRL+ALT+A,
CTRL+ALT+U, Editor `done`) schrieb sie zurück — die Runde war verloren, ohne dass
es jemand sagte. `stop_reclick()` aktiviert die gespeicherte Kopie deshalb, wenn
sie dieselbe Sequenz ist wie die geladene.

Fünf Regeln, an denen die Klick-Runde hängt:

- **Geändert wird nur die Stelle.** Wartezeiten, Farb-Bedingungen,
  Nachprüfungen, ELSE, Scans und die Reihenfolge bleiben — die Runde fasst die
  Reihenfolge und die Schritte überhaupt nicht an, sie schreibt `x`, `y` und (nur
  wenn der Punkt schon eine hatte) die Farbe in den Punkt.
- **Jeder Punkt einmal, in der Reihenfolge des Laufs** (INIT → Loop-Phasen →
  END). Klickt eine Sequenz zweimal denselben Knopf, ist das ein Punkt; ihn
  zweimal zu setzen hiesse, den ersten Griff wieder zu verwerfen.
- **Was sie nicht erreicht, sagt sie** (`click_points()` gibt zwei Listen
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
  (`clicked_window()` in `editors/_click_window.py`: `get_window_title_at()`,
  Rückfall auf den Vordergrund — dieselbe Funktion, die die Aufnahme benutzt,
  seit ihr an genau dieser Frage der erste Klick fehlte). Windows liefert den
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
- **Ein Pixel Abweichung ist keine Korrektur** (`MATCH_TOLERANCE`). Der Zeiger wird
  von uns auf die Stelle gesetzt, und trotzdem kommt der Klick gelegentlich einen
  Pixel daneben zurück (DPI-Skalierung). Ohne die Toleranz schriebe jede
  Bestätigung den Punkt um einen Pixel um und zählte als Änderung — Rauschen in
  genau der Liste, die sagen soll, was sich geändert hat.
- **Sie läuft aus dem Maus-Hook**, wie die Aufnahme. Deshalb schliesst der
  Punkte-Editor beim Start (ein blockierendes `input()` hielte die Message-Pump
  an, und der Hook sähe keinen Klick), deshalb sind alle weiteren Griffe globale
  Hotkeys — und deshalb wird **im Hook nicht auf Platte geschrieben**: ein
  Low-Level-Hook, der zu lange braucht, wird von Windows ausgehängt, und dann
  fehlen Klicks mitten in der Runde. Gespeichert wird am Ende (`stop_reclick`,
  auch beim Beenden des Programms).
- **Die vier Hotkeys sind geliehen, nicht neu**: `CTRL+ALT+J` beendet (dieselbe
  Bedeutung wie bei der Aufnahme), `CTRL+ALT+H` pausiert (navigieren, ohne einen
  Punkt zu verbrauchen), `CTRL+ALT+K` überspringt, `CTRL+ALT+U` geht zurück —
  und **zurück heisst zurück**: der eben gesetzte Punkt bekommt seine alte
  Stelle wieder, sonst behielte ein Verklicker sie bis zum nächsten Lauf. Die
  Basis-Ebene ist voll (s. Hotkey-Flow in der Wurzel-`CLAUDE.md`); alle vier tragen hier dieselbe
  Bedeutung wie sonst, nur einen anderen Gegenstand. Die Liste steht als
  `KEYS` in `editors/reclick.py`; das Studio zeigt sie als **Tabelle**
  (`WZ_KEYS` in `app.js`), und ein Test hält beide gegeneinander. Was man
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
er nach `JUMP_DELAY` (0,25 s, `_jump(..., verzoegert=True)`); die
alte Fassung liess die Stelle als Zahlenpaar in der Konsole stehen, und man
musste sie auf dem Schirm suchen, statt sie zu sehen.

**Und es läuft nichts von selbst.** Ein Start während der Runde wird abgelehnt —
`handle_toggle()` prüft `reclick_active` genau wie `recording_active`, und
`prepare_reclick()` lehnt umgekehrt ab, solange ein Countdown gestellt ist. Der Grund ist
derselbe wie bei der Aufnahme, eine Stufe schlimmer: **der Maus-Hook kann die
Klicks des Workers nicht von Handgriffen unterscheiden.** Lief eine Sequenz mit,
verbrauchte sie die Punkte der Runde selbst und schrieb ihre eigenen Ziele
hinein — von aussen sah das aus, als sei die Sequenz „von allein weitergelaufen",
und beim nächsten Start standen die Punkte woanders. `_set_point()` ignoriert
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
`calibrate_inventory()` rechnet Punkte, Slots, Item-Bestätigungsklicks, Boss-/Icon-Scans
und die Screenshot-Regionen in den Sequenz-**Dateien** um. Regeln:

- **`with_slots` steht getrennt von `with_scans`.** Nach einer Reparatur dürfen die Slots
  kein zweites Mal wandern, die übrigen Scan-Regionen aber schon.
- **Nichts anfassen, was eine Punkt-Referenz hat.** Der Punkt ist schon umgerechnet; ein
  zweiter Durchgang über den abgeleiteten Wert verschöbe ihn doppelt. `_remap_sequence_obj`
  und `_remap_sequence_data` prüfen deshalb `point_id is None`, bevor sie rechnen.
- **Die geladene Sequenz im selben Lock mitziehen**, nicht nur die Dateien — sonst schreibt
  das nächste `save_points()` den alten Stand aus dem Speicher zurück. Ihre Datei wird
  danach **nicht** ein zweites Mal über die Platte umgerechnet.
- **Vorher sichern**: `backup_before_calibration()` legt ein Export-ZIP an. Kein eigenes
  Backup-Format — der Export kann das, der Import spielt es zurück.
- `repair` übernimmt nur bei **eindeutiger Zuordnung**: gleiche Anzahl, gleiche Grösse,
  durchgängiger Versatz. Streuen die Einzelversätze, passiert nichts.

## Tastendruck in Menüs

`read_command()` aus `utils/io.py`, **nicht** `read_key()`. Das Polling für IDE-Konsolen
kennt nur die Tasten aus `_VK_MAP` (Pfeile, Enter, Escape, Ziffern) — ein getipptes `a`
fiel dort durch, und jede Taste landete auf demselben Zweig. `read_command()` schaltet die
Buchstaben für diesen einen Aufruf dazu.

Buchstaben gehören **nicht** dauerhaft in `_VK_MAP`: das gilt auch für
`interactive_select`, wo mit Pfeilen navigiert und mit Ziffern gewählt wird.

Menüs nehmen Buchstabe **und** Pfeiltaste (`_KEYS_NEXT`/`_KEYS_BACK` in
`runtime/debug.py`). Eine unbekannte Taste blättert nicht weiter, sondern bleibt stehen.

## Region-Auswahl (Scan-Editoren)
Boss-/Icon-Scan-Editor wählen ihre Scan-Region über `editors/_detection_capture.select_scan_region()` (Maus / manuelle Koordinaten / beibehalten). Die manuelle Eingabe wiederholt bei Fehleingabe statt den Editor abzubrechen; `None` = Abbruch (beim Bearbeiten bleibt die alte Region).
