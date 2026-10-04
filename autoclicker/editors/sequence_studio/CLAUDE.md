# Sequenz-Studio

Details zur `CLAUDE.md` im Wurzelordner — dort stehen Befehle, Architektur
und die Regeln, die überall gelten. Claude Code lädt diese Datei, sobald eine
Datei aus `autoclicker/editors/sequence_studio/` gelesen wird. Was hier steht, gilt genauso; neue
Begründungen zu diesem Bereich gehören hierher, nicht in die Wurzel.

## Module

- `autoclicker/editors/sequence_studio/` — das Studio-Fenster:
  - `bridge.py`: stabile `StudioBridge`-Fassade und Initialisierung.
  - `bridge_contract.py`: öffentliches Protokoll, Konstanten und reine Helfer.
  - `bridge_view.py`: Momentaufnahme und JSON-Projektionen.
  - `bridge_services.py`: Persistenz, Laufsteuerung und Konfiguration.
  - `bridge_editing.py`: Phasen-, Block-, Auswahl- und Punkt-Kommandos.
  - `bridge_share.py`: Export/Import im Reiter „Teilen".
  - `bridge_tools.py`: prüfen, kalibrieren, Klick-Runde im Reiter „Werkzeuge".
  - `bridge_report.py`: Session-Logs und Ertrag im Reiter „Bericht".
  - `scans.py`: stabile `ScanPart`-Fassade.
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

## Fenster, Prozess und Reiter

**Das Studio läuft als eigener Prozess**, nicht im Hauptprozess: ein
Fenster-Event-Loop und die Windows-Hotkey-Message-Pump vertragen sich nicht im selben
Thread. Gestartet wird es vom Handler per `subprocess.Popen([sys.executable, "-m", ...])`;
`pywebview` ist optional und wird beim Start des Subprozesses geprüft.

**Es ist EIN Fenster, nicht mehr zwei.** Daneben stand bis zum Umbau ein zweites in
Dear PyGui (`autoclicker/scan_studio.py` + `editors/scan_canvas/`) für Slots, Items
und Scans. Es ist ersatzlos gelöscht: zwei Fenster mit zwei Bedienkonzepten für
dieselben Dateien waren eines zu viel, und die Scans gehören dorthin, wo die Sequenz
steht, die sie benutzt. `CTRL+ALT+V` startet deshalb denselben Prozess wie
`CTRL+ALT+B`, nur mit vorgewähltem Reiter (`--scans` → `bridge.start_view`).

| Einstiegspunkt | Oberfläche | arbeitet auf |
|---|---|---|
| `autoclicker/sequence_studio.py` (`handle_sequence_studio`, `handle_scan_studio`) | `editors/sequence_studio/` (pywebview) | `sequences/<name>/` (sequence.json, item_scans/, boss_scans/, icon_scans/, templates/), `config.json` |

**Der Scans-Reiter merkt, wenn der Hauptprozess seine Dateien anfasst.** Er las
`slots.json`, `items.json` und `item_scans/` genau einmal je Sitzung — und ein
Lauf mit `learn_unknown` legt in derselben Zeit neue Items an und **speichert**
sie. Die Konsole meldete „gelernt", im Reiter waren sie nicht da, und man sucht
den Fehler beim Lernen statt bei der Ansicht. `_disk_state()` merkt sich die
Änderungszeiten beim Laden, `_disk_changed_externally()` vergleicht sie bei jeder
Momentaufnahme, und die Ansicht bietet „Neu laden" an. Zwei Regeln dazu:

- **Kein eigener Schreibvorgang zählt mit** (`_disk_track()`). Für das
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
sie inzwischen selbst nach (Briefkasten-Befehle `config` und `data_reload`), für Sequenzen
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
| Sequenzen | Übersicht, Kennzahlen, Öffnen | `sequence_list()` |
| Live-Run | was gerade läuft | `run_status()` |
| Scans | Slots, Items, Item-Scans auf einem Screenshot | `scan_data()` + `scan_*` |
| Teilen | Bündel schreiben und einlesen | `share_data()` + `export_/import_*` |
| Werkzeuge | prüfen, kalibrieren, Klick-Runde | `tool_data()` + `tool_/calib_*` |
| Bericht | was die vergangenen Läufe hinterlassen haben | `report_data()` |
| Einstellungen | `config.json` bearbeiten | `config_read()` / `config_write()` |

**Welche Sequenz offen ist, gilt in JEDEM Reiter — also steht die Auswahl
überall.** Sie war früher zusammen mit dem Speichern-Knopf ausgeblendet, und das
verwechselte zwei Dinge: die Falle sind zwei **Speichern**-Knöpfe für zwei
Dateien in einer Leiste, nicht die Auswahl. Für einen Wechsel musste man
deshalb erst in den Editor zurück — ausgerechnet aus den Reitern, die am
stärksten an der Sequenz hängen (Scans, Teilen und Werkzeuge arbeiten alle in
`sequences/<name>/`). Nebenbei behält der Kopf damit in jedem Reiter dieselbe
Gestalt, statt beim Umschalten drei Gruppen zu verlieren.

Zwei Dinge hängen daran, und ohne sie wäre es ein Rückschritt:

- **Der offene Reiter folgt dem Wechsel** (`call()` ruft danach `setView`
  erneut). Scans, Teilen und Werkzeuge hängen an eigenem Zustand (`SC`, `T`,
  `W`), den `render()` nicht anfasst — sonst stünden dort die Slots, Zahlen und
  Punkte der **vorigen** Sequenz unter dem Namen der neuen. Nicht bei einer
  Rückfrage (`S.question`): dann ist noch gar nichts geladen.
- **Offene Scan-Änderungen werden vorher weggeschrieben** (`switchSequence()`).
  Die Rückfrage nach ungespeicherten Änderungen kennt nur die Sequenz
  (`_dirty`); die Scans haben ihren eigenen Merker (`_scan_dirty`), und `load`
  wirft sie über `_scan_init()` wortlos weg. Gefragt wird trotzdem nicht — der
  Reiter speichert ohnehin von selbst, ein Verwerfen-Modell gibt es dort gar
  nicht. Scheitert das Schreiben, bleibt es beim bisherigen Stand.

Speichern und Starten bleiben dagegen bei der Sequenz: sie meinen die Sequenz,
nicht den Reiter.

**Zwei Kanäle zur Brücke, und die Unterscheidung ist keine Kosmetik.** `call()`
befiehlt und **ersetzt** mit der Antwort die Momentaufnahme `S`; `ask()` fragt nur
und lässt `S` in Ruhe. Übersicht, Laufstatus und die Einstellungen geben keine
Momentaufnahme zurück, sondern einen eigenen Gegenstand — über `call()` geholt
zerschösse ihre Antwort den Editor-Zustand, und ein Blick in die Übersicht wäre ein
Datenverlust. Wer eine Methode ergänzt, entscheidet zuerst, welcher der beiden Kanäle
gemeint ist. Der Test `jeder Aufruf der Seite passt zur Brücke` erfasst **beide**
Schreibweisen.

`config_write()` ist der Sonderfall, der die Regel bestätigt: sie **ändert** etwas
und gehört trotzdem zu `ask()`. Geändert wird die Config, nicht die Sequenz — eine
Momentaufnahme wäre dafür der falsche Gegenstand. Der Kanal richtet sich also danach,
was zurückkommt, nicht danach, ob etwas passiert.

**Gelöscht wird dort auch — mit Rückfrage und nach `backups/`.** Eine Sequenz ist
eine Besitzeinheit: Punkte stehen in ihrer `sequence.json`, Scans, Vorlagen und
gemerkte Bildschirme liegen daneben. Nur die JSON zu entfernen liesse einen Ordner
voller Vorlagen zurück, den nie wieder jemand ansieht — also geht der **ganze
Ordner**, und die Rückfrage nennt, was daran hängt („samt 3 Item-Scans, 12
Vorlagen"). Ohne diese Angabe löscht man einen Nachmittag Arbeit an Item-Vorlagen
mit, weil man „nur die Sequenz" wegräumen wollte.

**Verschoben statt entfernt** (`sequence_delete()`): der Ordner landet unter
`backups/sequences/<ordner>/`, ein vorhandener Stand dort bekommt einen Zeitstempel
statt überschrieben zu werden. Dieselbe Regel wie beim Start-Durchgang, und aus
demselben Grund — samt der gespiegelten Struktur, also unter dem **Ordner**namen.

**Und der Ordner heisst nicht wie die Sequenz.** `sequence_file()` legt ihn unter
`sanitize_filename(name)` an: aus „Raid" wird `sequences/raid`, aus „Mein Lauf"
wird `mein_lauf`. Der angezeigte Name steht **in** der Datei — wer ihn an
`sequences/` hängt, greift ins Leere, und wenn zufällig ein Ordner so heisst,
daneben: der wanderte nach `backups/`, während die echte Sequenz stehenblieb und
das Löschen „hat geklappt" meldete. Gesucht wird deshalb wie beim Laden über
`list_available_sequences()`, mit dem Ordnernamen als zweitem Weg (eine defekte
Datei steht dort nicht, und genau die will man am häufigsten löschen).
`_sequence_folder()` ist die eine Stelle dafür; sie schliesst nebenbei den Pfad,
denn `name` kommt aus dem Fenster.

**Umgekehrt ist der Name kein Ordnername — `sanitize_filename()` gehört an den
Pfad, nie an den Anzeigenamen.** Drei Wege hatten das vertauscht, und heraus
kamen Namen wie `abrechnung_mit_den_göttern` und `item_scan_raid` in jeder
Liste: der Aufnahme-Start im Studio (`recording_start` schickte den bereinigten
Namen an den Hauptprozess, und der speicherte ihn als Namen) und das Umbenennen
von Item-, Boss- und Icon-Scans. Dazu vorgeschlagene Namen mit Unterstrich
(`Sequenz_1727…`, `aufnahme_214638`); heute heissen sie „Neue Sequenz“ bzw.
„Aufnahme 21:46:38“. Bei Scans heisst das eine zweite Regel: **belegt ist, was
in DIESELBE Datei schriebe** (`scan_name_taken()` in `scan_contract.py`) — „Raid
Scan“ und „raid scan“ sind zwei Namen, aber eine Datei. Und ein Umbenennen, das
nur die Schreibweise ändert, darf die alte Datei nicht löschen: es ist dieselbe.

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

**Die Mehrzahl steht in den Daten, nicht in der Ansicht** (`_EXTENT` trägt beide
Formen). Ein angehängtes „n" ergab „2× Item-Scann" und „3× gemerkter
Bildschirmn" — bei drei von fünf Wörtern falsch. Aufgefallen ist es erst am
gerenderten Dialog; deutsche Mehrzahl ist keine Regel für eine Zeile JavaScript.

Zwei Eigenschaften der Übersicht, die man kennen muss: sie sieht den Ordner **selbst**
durch statt `list_available_sequences()` zu fragen (die überspringt unlesbare Dateien
stillschweigend — richtig für ein Menü, falsch für eine Übersicht: genau dann sucht
man die Datei im Explorer), und geöffnet wird über den vorhandenen `load`-Befehl,
damit die Rückfrage bei ungespeicherten Änderungen greift.

**Der Scans-Reiter arbeitet auf einem eingefrorenen Screenshot** (`ScanPart`-
Fassade in `scans.py`, Aufnahme in `scan_capture.py`, Zustands-/Interaktionslogik
in den übrigen `scan_*.py`-Modulen). Slots werden dort aufgezogen, wo sie im
Spiel liegen; Koordinaten tippt niemand. Er bearbeitet `sequences/<name>/item_scans/<n>.json` — Slots und Items stehen
darin, es gibt keine globalen Listen daneben — also wieder andere Dateien
als der Editor, weshalb auch hier das Sequenz-**Speichern** im Kopf verschwindet
und ein eigener Speichern-Knopf rechts steht. Die **Auswahl** bleibt (s. u.).

**Der Item-Scan ist das Übergeordnete, nicht die Auswahl.** Wer mehrere Spiele
betreibt, hat alle Slots und Items aller Spiele in einer Liste — und keiner davon
gehört sichtbar irgendwohin. Deshalb gibt es `open_scan` **neben**
`scan_kind`/`scan_name`: der offene Scan ist der Zusammenhang, die Auswahl ist das
Ding, das man gerade bearbeitet. Beides an einer Variable hiesse, dass ein Klick
auf einen Slot den Zusammenhang verliert (so war es zuerst gebaut). Am offenen
Scan hängen: was im Bild gezeichnet wird, welche Items `scan_recognize()`
prüft und welche Toleranz dabei gilt.

**Die Reihenfolge der Reiter ist die Rangfolge**: Scans, dann Slots, dann Items —
und beim Öffnen steht der Scan-Reiter vorn. Eine Liste, die vor ihrer Klammer
steht, liest sich wie das Hauptding; genau das war der Zustand, aus dem heraus
„alle Items aller Spiele in einer Liste" überhaupt entstand.

**Beim Öffnen ist der zuletzt bearbeitete Scan offen** — dieselbe Regel wie
`last_edited()` bei den Sequenzen und aus demselben Grund: ein echtes
„zuletzt geöffnet" müsste jemand mitschreiben, und das Dateisystem weiss es
schon. Vorher öffnete sich nur bei *genau einem* Scan etwas; wer einen zweiten
anlegte, sah eine leere Mitte und musste erst merken, dass oben links eine
Auswahl steht.

**Ein Scan ohne Bild ist nicht dasselbe wie ein Scan ohne Inhalt.** Ein älterer
Scan bringt seine Slots mit, aber kein gemerktes Bild — das gibt es erst, seit
der Reiter eines ablegt. `_canvas_area()` rechnet die Arbeitsfläche deshalb notfalls
aus dem umschliessenden Rechteck der Slots (mit Rand); alle Umrechnungen laufen
über `left`/`top`/`scale` und stimmen genauso, nur ist der Hintergrund leer.
Ein späterer Screenshot legt sich dahinter, ohne dass sich etwas verschiebt.
Das Feld `image` sagt, was von beidem dasteht — ohne das forderte die Seite ein
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
(Text-Chunk `left`/`top`), nicht in einer Datei daneben: zwei Dateien, die
zusammengehören, laufen irgendwann auseinander, und dann sind alle Koordinaten
still um einen Monitor verschoben.

Sechs Regeln, an denen der Reiter hängt:

- **Der Screenshot bleibt in Python.** Die Seite bekommt ihn einmal als
  verkleinertes Bild (`scan_image()`, getrennt von `scan_data()`, weil er der
  grosse Brocken ist); **gemessen wird nie darauf**, sondern immer im
  Originalbild (`_photo_color`). Eine Farbe aus einem skalierten Bild wäre
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
  heraus. `_selection` (die Menge) steht neben `scan_name` (der eine, den der
  Inspektor bearbeitet): zwei Dinge, zwei Felder, sonst hätte „Farbe messen"
  bei dreissig Gewählten keine Bedeutung.

  **Das Rechteck wählt, es löscht nicht.** Direkt zu löschen wäre der kürzere
  Weg und der falsche: ein um fünfzig Pixel zu weit gezogenes Rechteck nähme
  wortlos dreissig Slots mit. Gewählt sieht man erst, was man verliert; der
  zweite Griff (Entf oder „N löschen") kostet einen Klick.
  Aus demselben Grund wählt ein einzelner Klick ins Leere **nicht** mehr ab —
  er fängt das Rechteck an, und die Abwahl ist das leere Rechteck oder ESC.
- **Es gibt ein Rückgängig, und es merkt sich den ganzen Stand** (`_remember()` /
  `scan_undo()`, STRG+Z). Das war lange die grösste Lücke des Reiters:
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
  `UNDO_DEPTH` (30) deckelt den Speicher.

  Drei Regeln beim Erweitern:
  - **`_remember()` ruft die Methode, die ändert** — nicht die Oberfläche. Sonst
    hinge das Rückgängig daran, dass jeder Knopf daran denkt.
  - **Nur bei einer echten Änderung.** Ein abgelehntes Feld oder ein Name, der
    derselbe bleibt, legt nichts auf den Stapel; deshalb steht `_remember()` in den
    einzelnen Zweigen und nicht oben am Eingang. Ein STRG+Z, das einmal
    scheinbar gar nichts tut, ist ein Rückgängig, dem man nicht mehr traut.
  - **Was auf Platte passiert ist, kommt nicht zurück.** Ein gelöschter Scan
    kehrt als Konfiguration wieder (und wird beim nächsten Speichern neu
    geschrieben), sein gemerkter Screenshot ist weg. Das steht in der Meldung,
    statt ein vollständiges Zurück zu versprechen, das es nicht gibt.
    `scan_reload()` leert den Stapel — er beschreibt Stände, die es nach dem
    Neulesen nicht mehr gibt.
- **Was man nicht treffen kann, kann man nicht löschen.** Ein Slot von 2×2 px
  entsteht aus zwei Klicks fast auf dieselbe Stelle — und war danach kaum wieder
  loszuwerden, weil Löschen Auswählen voraussetzt. Drei Stellen zusammen lösen
  das: `MIN_SLOT` (8) lässt ihn gar nicht erst entstehen, `HIT_MIN` (14)
  weitet die *Trefferfläche* vorhandener Winzlinge auf (den Slot selbst nie —
  gemessen wird, was dasteht), und `_slot_under()` nimmt den **kleinsten**
  Slot unter dem Zeiger statt des obersten, damit ein Winzling in einem grossen
  Slot überhaupt erreichbar ist. Dazu markiert die Liste ihn (`tiny`): dort ist
  er so gross wie jeder andere, und das ist der zweite Weg zum Löschen.
- **Was ein Klick bedeutet, sagt ein Modus** (`MODES` in `scan_contract.py`,
  über `scans.py` weiterhin öffentlich importierbar: wählen, neuer
  Slot, Hintergrundfarbe, Klickpunkt) — ein Klick, dessen Bedeutung man raten
  muss, ist schlimmer als ein Modus-Knopf. Jeder Modus liegt zusätzlich auf
  seinem Anfangsbuchstaben; ein Test hält Kacheln und `MODES` gegeneinander —
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
  markierten Kachel **und** im Hinweis unter dem Raster. `MODE_CHOICE` ist
  ausgenommen — er *ist* der Rückweg.

  **Der Modus bleibt dagegen stehen, solange man in ihm arbeitet**: wer zwanzig
  Slots aufzieht, fasst die Kachel einmal an. Von selbst endet nur ein Modus,
  der einen Durchgang hat statt einer Tätigkeit — `finden` schaltet nach der
  Suche zurück, und zwar auch dann, wenn nichts Neues dabei war. Sonst liesse
  derselbe Klick einen mal im Modus stehen und mal nicht, je nach Ergebnis.

  **Was man ZWISCHENDURCH tut, braucht keinen Modus** (`scan_direct()`).
  ALT-Klick misst den Hintergrund des Slots unter dem Zeiger, Doppelklick setzt
  seinen Klickpunkt — beides ohne den Umweg über die Kachel und beides wählt den
  Slot gleich mit aus. Der Unterschied zu den Modi ist nicht Bequemlichkeit,
  sondern die Frage, die dahintersteht: ein Modus beantwortet „was tut ein Klick
  **jetzt**" und lohnt sich, solange man dasselbe zwanzigmal tut. Eine einzelne
  Korrektur an einem Slot, den man vor sich sieht, ist das Gegenteil davon — dort
  ist der Moduswechsel hin und zurück teurer als der Handgriff selbst.
- **Ein Slot lässt sich verschieben, ohne vier Zahlen zu tippen.** Ziehen im
  Bild oder Pfeiltasten (SHIFT = 10 px), beides über `scan_move()` und
  beides auf der ganzen Auswahl. Der Fall ist Alltag: das Spielfenster ist
  umgezogen, die Erkennung sass eine Zeile zu hoch. Über die Zahlenfelder war
  das bei einem Slot mühsam und bei dreissig ausgeschlossen.

  Drei Regeln dazu:
  - **Der Klickpunkt geht mit**, statt neu aus der Mitte gerechnet zu werden —
    er ist womöglich bewusst aus der Mitte gesetzt.
  - **Gepackt wird nur, was schon gewählt ist.** Damit braucht die Seite keine
    eigene Trefferregel: welcher Slot unter dem Zeiger liegt, entscheidet
    weiterhin `_slot_under()` in Python. Zwei Trefferregeln wären zwei
    Antworten auf dieselbe Frage.
  - **Eine gehaltene Pfeiltaste ist EIN Verschieben.** Nur der erste Schritt
    einer Serie kommt auf den Rückgängig-Stapel (`counts`), sonst läge er nach
    zwei Sekunden Halten voll mit Ein-Pixel-Schritten und der Schritt davor wäre
    herausgefallen.
- **Sammel-Aktionen arbeiten auf der Auswahl** — und zwar auf mehr als
  „löschen". Bis hierher konnte eine Mehrfachauswahl genau das, womit das
  Rechteck ein Werkzeug zum Wegräumen war und sonst nichts. Dabei betreffen
  gerade die Handgriffe nach dem Finden fast immer viele Slots auf einmal:
  Grösse angleichen, Hintergrund neu messen, aus der Auswahl lernen, die
  Auswahl in den Scan aufnehmen. Worauf sie wirken, beantwortet
  `_selection_slots()` an **einer** Stelle (Auswahl, sonst der eine Gewählte) —
  sonst nähme „löschen" dreissig Slots und „angleichen" einen.

  Zwei davon hätten eine naheliegende und falsche Fassung: „Hintergrund messen"
  misst **jeden Slot an sich selbst** statt eine Farbe für alle zu setzen
  (Inventare sind selten gleichmässig ausgeleuchtet, und eine gemeinsame Farbe
  verschöbe die Lernmaske an jedem Slot ein bisschen), und „Grösse angleichen"
  nimmt den **Median** statt des grössten oder kleinsten — ein einzelner
  Verklicker soll nicht alle anderen verbiegen.
- **Die Erkennung fragt die Laufzeit, nicht sich selbst.** `scan_recognize()`
  ruft `_check_profile_match()` aus `runtime/item_scan.py` — dieselbe Funktion,
  die im Lauf entscheidet, mit einem `state`-Stellvertreter, der nichts als die
  Config trägt. Eine zweite Rechnung „nur für die Vorschau" wäre eine Vorschau,
  die etwas anderes zeigt als das, was passiert.

  **Nach dem Finden läuft sie von selbst** (`_detect_immediately()`). Die Frage
  nach dem Finden ist nicht „habe ich Slots", sondern **„was davon kenne ich
  schon"**: sonst stehen zwanzig gleich aussehende Rechtecke da, und der
  nächste Schritt lernt stumpf alle zwanzig — auch die neunzehn, die längst im
  Bestand liegen. Grün heisst „erledigt, kümmere dich um den Rest"; der Treffer
  ist dabei ein **Vorschlag, keine Festlegung** (stimmt er nicht, lernt man aus
  demselben Slot ein weiteres Item).

  Gemessen an einem vollen Inventar (45 Slots gegen 45 Items) kostet das
  ~310 ms und damit weniger als das Finden davor; ohne Items im Bestand ist es
  augenblicklich und sagt gar nichts. Dass es nicht teurer wird, wenn der
  Bestand wächst, liegt an `_candidates()`: bei offenem Scan werden nur dessen
  Items geprüft.

  Die **Rechnung gibt es nur einmal** — `_detect_run()` füllt `_matches`,
  die Meldung baut jeder Anlass selbst (der Knopf sagt das Ergebnis, das Finden
  hängt es an seine eigene Meldung). Zwei Erkennungen wären zwei Ergebnisse.
- **Die Slot-Zustände liegen auf einem SPIELBILD, nicht auf dem Panel.** Deshalb
  haben sie eine eigene, grellere Farbfamilie (`--slot-ok` `#00E58A` =
  erkannt und im Scan, `--slot-empty` `#F43F5E` = nichts erkannt, hier ist zu
  tun) und **jeweils eine Füllung** dazu (Suffix `-f`).

  Die Werte sind gemessen, nicht geraten, und stehen in einem Test fest.
  `--slot-empty` war `#FF9500` und damit fast der Akzent `#F59E0B`: „zu tun" und
  „gewählt" sahen gleich aus — **Amber gehört der Auswahl**, sonst markiert die
  Markierung nichts. Die Klassenlogik
  (`.scan-slot.match` / `.empty`, `SLOT_COLOR` in `app.js`)
  blieb dabei unverändert — nur die Variablen. Ein 1,5-px-Umriss in `var(--dim)` verschwindet
  zwischen bunten Item-Symbolen restlos — genau das war „nichts erkannt" vorher,
  also ausgerechnet der Zustand, den man sucht. Die Fläche trägt die Aussage,
  der Strich schärft sie.

  Marke im Bild und Zeile in der Liste lesen **dieselben** Variablen
  (`SLOT_COLOR` liest sie einmal aus `getComputedStyle`), statt Hexwerte zu
  wiederholen. Drei Tests halten das zusammen: jeder Zustand braucht Umriss
  *und* Füllung, jede benutzte `--slot-*`-Variable muss definiert sein, und
  `SLOT_COLOR` muss genau die Zustände abdecken.
- **Es gab einmal einen dritten Zustand, „erkannt, aber nicht in diesem
  Scan"** (`match.foreign`, türkis) — aus der Zeit des globalen Bestands: bei
  einem Scan ohne Items prüfte `_candidates()` alle Items aller Spiele, und ein
  Treffer aus dem *anderen* Spiel durfte nicht grün werden. Seit der Scan seine
  Items selbst besitzt, gibt es nichts, was erkannt und trotzdem fremd wäre;
  `_detect_run()` meldete `foreign` deshalb immer als `False`, und Farbe,
  Klasse, `SLOT_COLOR`-Eintrag und das Feld selbst sind **ersatzlos gelöscht**.
  Ein Test hält fest, dass nichts davon zurückkommt.

- **Scan, Slot und Item sind Masken — dieselbe Bauform** (`buildCard()`, dazu
  `scanScanCard` / `scanSlotCard` / `scanItemCard`). Sie unterscheiden sich
  in dem, was drinsteht, nicht darin, wie man sie anfasst: Haken (gehört zu
  diesem Scan), Vorschau bzw. Farbe, Name, darunter die zweite Zeile — beim
  Item Kategorie und Priorität, bei Slot und Scan der Stand.

  Vorher war ein Item eine Maske und ein Slot eine Knopfzeile mit vier
  Zahlenfeldern in einer anderen Spalte: **dieselbe Frage („wie benenne ich das
  um") hatte zwei Antworten.** Der Name steht seither in genau einer — dieselbe
  Auflösung wie beim Klick-Block im Sequenz-Editor.

- **Der ganze Listen-Block steht RECHTS: Reiter, Filter und Masken zusammen**
  (`scanListBlock()`, gerufen aus `scanInspector()`). Der Schnitt geht nach
  Verantwortung, nicht nach Scan-Art: **links, wie der Scan entsteht** (Auswahl,
  Assistent, Modus-Kacheln), **rechts, was drin ist.**

  Es gab einen Zwischenzustand, in dem nur die Item-Masken rechts standen und
  Reiter und Filter links blieben. Der kostete zweierlei: beim Umschalten
  schrumpfte links ein Abschnitt zusammen, während rechts etwas erschien — die
  linke Spalte **änderte bei jedem Reiterwechsel ihre Grösse** —, und ein
  Hinweistext musste erklären, wohin der Inhalt verschwunden ist. Beides ist mit
  dem Umzug weg; `#ab-listen` und `nur-reiter` sind ersatzlos gelöscht.

  Als **Masken** kommen dabei nur die Item-Listen (`scanCardsRight()`): dort
  stehen Dutzende gleichartiger Dinge nebeneinander. Ein Boss- oder Icon-Scan
  ist **eines** — Region, Erkennung, Aktion —, das trägt keine Maske; seine
  Liste steht am selben Ort, und was zum Gewählten gehört, darunter (`.det-insp`,
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
  Scan-Liste heraus** öffnet (`scanTabAfterOpen`).

- **Sortiert wird beim Laden und auf Knopfdruck, nicht beim Tippen**
  (`scanOrder`, Knopf „↕ Sortieren"). Sortierte sich die Liste nach *jeder*
  Änderung neu, springt genau die Zeile weg, an der man gerade arbeitet: man
  tippt eine 2, die Zeile rutscht drei Plätze, und der nächste TAB landet im
  Feld eines anderen Items. Gemerkt wird deshalb die Reihenfolge des letzten
  Sortierens; aufgefrischt beim Laden (`scan_reload`, Lernen,
  `scan_open`), beim Reiterwechsel und durch den Knopf.

  **Kein Feld eines Items verschiebt seine Zeile** — auch die Kategorie nicht.
  Sie war der erste Sortierschlüssel und damit das letzte Feld, das noch
  sprang; eingefroren wird sie deshalb zusammen mit dem Rang
  (`scanOrderGroup()`), und die Gruppenüberschriften kommen aus dieser
  Momentaufnahme statt aus dem aktuellen Wert. Sonst risse ein gerade
  geändertes Item eine zweite Überschrift mitten in die Liste. Wohin es beim
  nächsten Sortieren wandert, sagt seine Zustandszeile („→ Helme").

  **Umbenennen ändert den Namen, nicht den Rang** (`scanOrderRename()`).
  Der Merkposten hängt am Namen — ohne das Nachziehen galt ein gerade
  umbenanntes Item als neu und rutschte ans Ende seiner Gruppe, und genau beim
  Namen tippt man. Eingetragen werden beide Namen: lehnt die Brücke den neuen
  ab, behält das Item trotzdem seinen Platz.

- **Der Kopf der rechten Spalte klebt oben** (`.scan-header`, `position: sticky`).
  Dort stehen Speichern, Rückgängig, „Items erkennen", die Reiterleiste und die
  Filterzeile — bei sechzig Masken war all das nach drei Umdrehungen weg, und
  mit ihm der Weg in eine andere Liste. Er braucht einen eigenen Hintergrund,
  sonst scrollen die Masken sichtbar dahinter durch. Die Reiterleiste nimmt die
  **ganze** Breite (`.tabs.wide`, gleiche Spalten): drei Reiter links
  zusammengedrängt liessen zwei Drittel der Leiste leer, und gleiche Spalten
  verhindern, dass die Zahlen dahinter („Slots 72/85") die Aufteilung bei jedem
  Filterwechsel verschieben.

  **Weil er klebt, muss er kurz sein.** Gemessen waren es sieben Zeilen
  Bedienung (Speichern allein, „Items erkennen | Zurück", Katalog, „Alle mit LLM
  benennen", Reiter, „N Items löschen", „Sortieren", „Alle aus") — rund 330 von
  830 px, bevor die erste Maske kam, und genau so viel fehlte der Liste bei
  jedem Scrollen. Heute: `Speichern | Zurück`, `Items erkennen | Alle
  benennen` (Katalog in derselben Zeile, sonst in einer eigenen), Reiter,
  `Sortieren | Alle aus`. „Alle benennen" ist kurz beschriftet, damit es in die
  halbe Zeile passt; ob der Name aus dem Katalog oder frei vom Modell kommt,
  sagt der Tooltip.

  **Der Kopf ist eine Spalte, kein Fliesstext.** Jedes Bedienelement nimmt die
  volle Breite (`.scan-filter` als einspaltiges Raster); nur der Schalter dehnt
  sich nicht, denn er ist Text mit Kästchen davor. Vorher stand „alle dazu" als
  kurzer Stummel neben dem Schalter, „Sortieren" als noch kürzerer darunter und
  die Klappliste dazwischen über die ganze Breite — drei verschiedene Breiten
  untereinander lesen sich wie drei Rangstufen, obwohl es dreimal dasselbe ist.
  Wo zwei Knöpfe eine Zeile teilen (`.button-pair`), bekommen sie **gleiche**
  Spalten: „Items erkennen" nahm sonst den Rest der Zeile und „Rückgängig" nur
  seine Textbreite, und weil dessen Beschriftung den letzten Schritt nennt,
  kippte das Verhältnis bei jeder Änderung.

  **Für „nebeneinander" gibt es genau zwei Klassen**, und sie gelten überall:
  `btn wide` ist EIN Knopf über die volle Breite, `button-pair` sind mehrere zu
  gleichen Teilen. Vorher stand an jeder Zeile eine eigene Mischung aus
  `grow`, Abstandhaltern und Textbreite — dieselbe Frage, ein Dutzend
  Antworten. Ein Test hält fest, dass kein `btn grow` mehr existiert.

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
- **Neben einem Auto-Speichern zeigt der Speichern-Knopf seinen Zustand**
  (`scanSaveButton()`): amber „Speichern“, solange etwas offen ist, sonst
  ruhig „✓ Gespeichert“. Der Reiter schreibt 900 ms nach jeder Änderung von
  selbst und meldet dabei unten „… gespeichert.“ — ein Klick danach schrieb
  dieselbe Meldung noch einmal, der Knopf blieb amber, und vorher und nachher
  sahen gleich aus: gemeldet als „Speichern geht nicht“, obwohl die Datei
  jedes Mal geschrieben war. Den Zustand trug bis dahin ein Stempel in der
  Bildleiste, der ab 900 px Bühnenbreite ausgeblendet war — also bei jeder
  gewöhnlichen Fenstergröße; er ist ersatzlos weg. Gesperrt wird der Knopf
  nie: ein zweites Schreiben schadet nicht, und ein gesperrter Knopf liest
  sich wie ein kaputter. Der Kopf-Knopf des Editors bleibt immer amber — dort
  gibt es kein Auto-Speichern, und eine nie gespeicherte neue Sequenz ist
  nicht `dirty`, hätte also fälschlich „Gespeichert“ gezeigt.
- **Ein Attribut, das allein durch sein DASEIN wirkt, braucht einen Boolean.**
  `el()` setzte jeden nicht-falsy Wert per `setAttribute` — und
  `disabled="0"` sperrt genauso wie `disabled="1"`. Im Werkzeug „Punkte
  verwalten" stand `disabled: punkt.verwendungen.length`: bei 0 Verwendungen
  (also genau dann, wenn man löschen DARF) war der Knopf gesperrt, bei 3
  ebenso — er war **immer** tot, in einem Werkzeug, das „sicher löschen"
  verspricht. `PRESENCE_ONLY` in `el()` lässt solche Attribute bei falsy Werten
  jetzt weg; die 27 anderen Aufrufstellen übergaben ohnehin schon Booleans.
- **Ein verzögerter Schreiber darf keine frischere Meldung begraben.**
  `mailboxFollowUp()` meldet nach zwei Sekunden „Kein Hauptprozess
  erreichbar" — und überschrieb dabei, was der Nutzer inzwischen getan hatte.
  Es merkt sich deshalb `statusStamp` und schweigt, wenn seither jemand anders
  etwas gemeldet hat.
- **Wer die Mitte neu zeichnet, zeichnet auch die rechte Spalte.** `wzCheck()`
  rief nur `wzRenderMiddle()`: der Bericht stand in der Mitte, rechts blieb
  „Noch nichts geprüft." — ausgerechnet die Spalte, die auflistet, WAS geprüft
  wurde, und ohne die „Alles in Ordnung" eine Behauptung ist. Jeder andere
  Werkzeug-Befehl geht über `callTool` → `renderTools()` und zeichnet
  alle drei Spalten; dieser eine ging seinen eigenen Weg, weil er `ask()`
  direkt ruft.
- **Ein ⓘ hängt an einer Beschriftung, nicht im Leeren.** `wzInfo()` im
  Werkzeuge-Reiter warf seinen Titel ins `title`-Attribut; sichtbar blieb ein
  nackter Kreis in der Fläche — an zwölf Stellen, in „prüfen" und „kalibrieren"
  mitten im Nichts, wo er wie ein Rest aussah. Die Beschriftung ist es, die
  sagt, worüber nachzufragen sich lohnt; sie kostet eine Zeile kleiner Schrift
  und nicht die Breite, um die es beim Kompakt-Umbau ging (ein Kasten wäre das
  gewesen).
- **Zustandsklassen bekommen ein Präfix — auch dort, wo es niemand sieht.** Der
  Hinweiskasten hiess `wz-info-compact info`, und `.info` ist der runde
  ⓘ-Knopf: 13 px, `flex:none`, zentriert. Der Kasten erbte dessen Gestalt.
  Solange er NUR das ⓘ enthielt, sahen 13 px richtig aus — mit einer
  Beschriftung darin stand der Text mittig über den Kasten hinaus, nach links
  aus dem Fenster heraus. Dieselbe Falle wie einmal beim Status, nur jahrelang
  unsichtbar. Das `kind`-Argument ist dabei **ersatzlos gelöscht** statt auf
  `art-…` umgeschrieben: zwölf Aufrufe, kein einziger mit drittem Argument, und
  in der CSS-Datei keine einzige Variante — ein Präfix hätte einen toten Zweig
  gepflegt.
- **Eine Klasse, die das Layout setzt, darf keine andere überschreiben.**
  `.wz-action{display:flex}` steht später im Stylesheet als `.grid2`/
  `.grid3` und gewann bei gleicher Spezifität: die beiden Stellen, die
  ausdrücklich `wz-action gitter2` bzw. `gitter3 wz-action` schreiben, bekamen
  nie ihre gleichen Spalten, und die Knopfreihen standen in Textbreite da. Die
  Klasse trägt jetzt nur noch ihren Abstand; wer eine Reihe will, schreibt
  `row` dazu.
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
  Sammel-Aktionen stehen deshalb unten beieinander als `button-pair` — und nur,
  wenn die Phase überhaupt Blöcke hat.
- **Untereinander stehende Zeilen liegen auf DEMSELBEN Raster.** Der Phasenkopf
  hatte oben ein `flex` mit fest getippten 70 und 74 px und darunter ein
  `button-pair`: die Eigenschaften-Zeile endete bei 470 px, die Knopfzeile bei
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
- **Auch ein Schalter bekommt seine Fläche** (`.tile`). Aufgefallen ist das
  an einem Filter, der als loser Text zwischen lauter Kacheln stand —
  Reiterleiste darüber, Knopfreihe darunter — und sich las, als gehöre er nicht
  dazu. Den Filter gibt es nicht mehr (s. u.), die Regel schon.
- **Ein Knopf sieht aus wie ein Knopf.** `.btn.quiet` hiess einmal „ohne
  Rahmen" (`border-color: transparent`) — damit war „+ neuer Scan" oder „alle
  dazu" ein Stück Text, dem man nicht ansieht, dass man es anklicken kann. Der
  Ton bleibt zurückhaltend (kein Hintergrund, gedämpfte Schrift), die **Fläche**
  ist da.

- **Die Kachel zeigt eine stabile ID, keine Stelle im Scan.** Der erste Anlauf
  zeigte dort `number` — die Stelle in `slot_names`, mit der Begründung „das
  ist die Zahl, die man an einer Nummer sucht: wann ist dieser Slot dran".
  Das stimmt, ist aber genau deshalb die falsche Zahl für EINE Kachel: die
  Stelle ändert sich mit Absicht, sobald ein Slot ab- und wieder angeschaltet
  wird (`scan_slot_set` schaltet `enabled` um, und die Nummer zählt nur die
  eingeschalteten durch) — eine Kennung, die beim Ausschalten verloren
  geht, ist für eine ID unbrauchbar. `ItemSlot` trägt deshalb ein eigenes,
  stabiles `id`-Feld (`models.py`), vergeben von `_next_slot_id()` bei der
  Entstehung — dieselbe Rechnung wie bei `ClickPoint`/`PalettePoint`
  (`max(vorhandene) + 1`), aber **keine Referenz**: der Name bleibt der
  Schlüssel in `slot_names`/`item_names`, die ID ist reine Anzeige.

  **Zwei Zahlen bleiben nötig, weil sie zwei verschiedene Fragen beantworten.**
  `number`/`run_index`/`total` stehen weiterhin in der Momentaufnahme — sie
  entscheiden die Vorsortierung („in welcher Reihenfolge lernt/scannt das hier")
  und stehen im Tooltip der Kachel; angezeigt wird aber `id`. Wer nicht zum
  offenen Scan gehört, hat keine `number` (dort gibt es keine Stelle), aber
  jeder Slot hat eine `id` — unabhängig davon, ob er gerade irgendeinem Scan
  angehört.

  **Für Altbestand ohne das Feld gibt es keine Migration, sondern einen
  Backfill beim ersten Laden** (`_slot_ids_assign()`, aufgerufen aus
  `_scan_load()`): jeder Slot mit `id == 0` bekommt eine frische, in stabiler
  Reihenfolge (Name, nicht Dict-Zufall) — und der Scan gilt danach als
  ungespeichert, denn ohne einen Schreibzugriff würde bei jedem Start neu
  gewürfelt, und die gerade zugesicherte Stabilität wäre eine Lüge. Genau der
  Fall, für den „Neue Formatänderungen brauchen keinen Migrationsschritt" da
  ist: Default `0` in der Dataclass, `data.get("id", 0)` im Loader, fertig.

  **Stabil heisst dabei natürlich sortiert, nicht Zeichen für Zeichen**
  (`_natural_key()` in `scan_state.py`). Ein reiner String-Vergleich stellt
  „Slot 10" zwischen „Slot 1" und „Slot 2" — bei sechzig durchnummerierten
  Slots bekam „Slot 2" damit die ID 12 und „Slot 3" die 23. Die IDs waren
  stabil und trotzdem unbrauchbar: eine Kennung, die in Sprüngen dasteht,
  liest niemand als Kennung, sondern als Fehler. Dieselbe Regel wie bei
  `byName()` in der Ansicht, nur eine Ebene tiefer — und sie muss an beiden
  Stellen stehen, denn die Vergabe entscheidet die Zahl, die Sortierung nur
  die Zeile.

  **Sie steht unter dem Schalter, in der ersten Spalte** (`.scan-badge`), nicht
  vor dem Namensfeld: dort nahm sie ihm die Breite, liess die Namen ohne ID
  an einer anderen Kante beginnen — und beim Bearbeiten schob sich das Feld
  darüber. In der ersten Spalte steht sie ausserhalb von allem, was sich beim
  Tippen ändert.

  Gezeichnet wird sie als `.num` — dieselbe Kachel wie überall sonst, keine
  eigene daneben —, und die **Grösse** in der Zustandszeile ebenso: sie ist ein
  gemessener Wert, kein Satz. Was daneben steht („Item 1", „unbekannt",
  „→ Helme"), ist eine Aussage und bleibt Text. Beide Kacheln stehen auf einer
  Höhe, weil die erste Spalte `align-self: stretch` trägt und ihren Inhalt
  auseinanderzieht; ein Rauchtest misst die Unterkanten.

  **Die ID-Kachel hat eine feste Mindestbreite** (`.scan-badge .num`). Ohne
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
  war es die Scan-Stelle (`number`): eine Zahl, die die Liste gar nicht zeigt,
  womit die Reihenfolge willkürlich aussah. Die ID gilt dabei **über die
  Grenze „gehört zum offenen Scan" hinweg** — sie bezeichnet den Slot
  dauerhaft, und eine Ordnung, die bei jedem Häkchen umspringt, wäre wieder
  die bewegliche Zahl von vorher. Slots ohne ID (Altbestand, den der Backfill
  noch nicht gesehen hat) landen am **Ende** und werden dort nach Namen
  geordnet: vorn stünde der ungepflegte Rest über allem anderen, und die
  Ansicht erfindet keine Reparatur für Bestandsdaten.

  Bei gleicher Lage entscheidet der Name **natürlich sortiert**
  (`byName()`, `numeric: true`) — ein reiner Zeichenvergleich stellt
  „Slot 10" zwischen „Slot 1" und „Slot 2", und bei fünfundvierzig
  durchnummerierten Slots ist die Liste damit sortiert und trotzdem unlesbar.
  Die Items bleiben bei Kategorie und Rang: sie haben keine ID.

- **Welche Priorität frei ist, steht da** (`priorityAllocation()`). Die
  Übersicht zeigte nur die vergebenen Ränge; ob P2 belegt ist oder fehlt, sah
  man erst, wenn man P1, P3, P4 las und selbst nachzählte. Sie spannt deshalb
  jeden Rang von 1 bis zum höchsten belegten plus eins auf — der nächste freie
  steht immer da —, und eine Lücke ist gestrichelt statt beschriftet. Eine
  getippte P99 spannt das nicht auf hundert Kacheln auf (`PRIO_MAX_SHOW`).

  **Eine doppelte Priorität fällt schon in der Liste auf**, nicht erst im
  aufgeklappten Detail: getippt wird in der Maske. Bei gleicher Zahl entscheidet
  die Scan-Reihenfolge, also der Zufall — das ist kein Fehler, aber fast immer
  ein Versehen.

  **Wer ein Item in eine Kategorie schiebt, hat über seine Priorität nichts
  gesagt** — dann rückt es auf den nächsten freien Rang (`_free_priority()`,
  erste Lücke, nicht ans Ende) und es wird gesagt. Eine ausdrücklich getippte
  Zahl fasst dagegen niemand an, auch keine doppelte: sie kann gewollt sein, und
  ungefragt zu verschieben wäre schlimmer als die Doppelung.

- **Der Fokus hängt an der `id` der Maske** (`cardId()`, gelesen von
  `rememberFocus()`). Ohne sie klettert `closest("[id]")` bis zur ganzen Spalte,
  und die gemerkte Position zählt über **alle** Masken hinweg — bei sechzig
  Items rund zweihundert Felder. Genau die drei Angaben, die man dort tippt,
  sortieren die Liste aber um (Kategorie, Priorität, Name): nach dem Neuaufbau
  stand an derselben Position das Feld eines **fremden** Items, der Cursor
  sprang weg, und wer weitertippte, änderte das falsche. Ein Umbenennen ändert
  die id selbst — `focusRename()` sagt sie vorher an, und die alte bleibt
  als Rückfall, falls die Brücke den Namen ablehnt. Gemessen wird das im
  **Rauchtest**: einen Fokus sieht die Vertragssuite nicht.

  **Der Schutz sitzt in `scanInspector()`, nicht bei den Aufrufern.**
  `renderScans()` hatte ihn, aber es gibt einen zweiten Weg: sobald ein
  nachgeladenes Template ankommt, baut `scanFetchPreviews()` die Spalte
  direkt neu. Genau das passiert beim Umbenennen — unter dem neuen Namen gibt
  es noch keine Vorschau —, und dort ging der Fokus verloren, während er beim
  Tippen einer Priorität stehen blieb. Ein Schutz, an den jeder Aufrufer denken
  muss, ist einer, den einer vergisst.

- **Ein Item hat einen Klick DANACH** (`scanItemConfirmation()`,
  `ItemProfile.confirm_point_id`). Manche Spiele fragen nach („wirklich
  verkaufen?"); ohne die Bestätigung bleibt das Popup stehen, und der Scan
  erreicht den nächsten Slot gar nicht mehr. Das Feld gibt es im Modell und in
  den Konsolen-Editoren seit jeher — im Studio war es die einzige
  Item-Eigenschaft ohne Bedienelement, und wer es suchte, fand nichts.

  Gesetzt wird es über einen **Punkt**, nie über zwei Zahlen. Zwei Wege dorthin,
  und der zweite ist dasselbe Werkzeug, das Boss und Icon schon benutzen:
  `_target_check("item")` gibt das gewählte Item zurück, `_click_action()` legt
  den Punkt an und schreibt ihn nach `confirm_point_id` statt nach
  `action_point_id`. Ein zweites Werkzeug daneben wäre dieselbe Frage mit einer
  zweiten Antwort.

- **Die Kategorie wird gewählt, nicht getippt** (`categoryChooser()`). Ein freies
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
  - **Der Tipp-Modus überlebt den Neuaufbau** (`categoryFree`, Schlüssel je
    Stelle). Die Ansicht wird nach jeder Brücken-Antwort neu gebaut, und der
    Entwurf speichert 900 ms nach der letzten Änderung von selbst: sonst würde
    das Feld mitten im Wort wieder zur Auswahlliste. Dieselbe Mechanik wie
    `openHelps` und `collapsed`, derselbe Grund wie bei `rememberFocus()`.
  - **Der Rückweg ist ESC**, solange es etwas zu wählen gibt — hinein mit einem
    Klick, heraus auch. Ein Modus, in den man nur hinein kommt, ist eine
    Falltür; dieselbe Regel wie bei den Modus-Kacheln und der ELSE-Kachel.
  - **Geraten wird nicht.** `_category_normalize()` zieht Leerraum zusammen
    und übernimmt eine bekannte Schreibweise bei gleicher Klein-/Grossschreibung
    — mehr nicht. Ein getipptes Wort stillschweigend in ein ähnliches zu ändern
    ist schlimmer als der Tippfehler.

  Dasselbe Bedienelement steht in der Lern-Vorschau: dort entstehen die
  Kategorien, und dort tippte man sie zwanzigmal. Damit eine in Zeile 1
  angelegte in Zeile 2 wählbar ist, zieht `refreshCategoryOptions()`
  die Listen aller offenen Felder nach.

  Und weil die Kategorie dort jetzt eine Auswahlliste sein kann, liest
  `scanReviewApply()` die Zeilen **über Klassen statt über Positionen**.
  Vorher wurden die Felder durchnummeriert gegriffen; wer eines dazwischen
  einbaut, verschiebt still alle folgenden — ein Import, der die Priorität als
  Kategorie liest, fällt niemandem auf.
- **„Items erkennen" muss man in der Item-Liste sehen.** Der Knopf färbte die
  Rechtecke im Bild und füllte die Ergebnisleiste — wer aber in der Item-Liste
  stand (und das ist die Liste, in der man arbeitet), sah nach dem Klick nichts
  und hielt ihn für wirkungslos. `_detected_items()` liefert deshalb nicht mehr
  eine Menge von Namen, sondern **Name → Slots**; an jeder Maske steht, wo das
  Item gefunden wurde. „Erkannt" ohne Beleg wäre eine Behauptung, und bei einem
  Fehlgriff (zwei Items sehen sich ähnlich) fehlte genau die Angabe, an der man
  ihn bemerkt.
- **Ein Befehl hat einen Namen.** `scan_recognize` stand im Assistenten als
  „Erkennung testen" und im Inspektor als „Items erkennen" — zwei Namen für
  einen Knopf, und man probiert beide aus, weil man annimmt, sie täten
  Verschiedenes. Beide heissen jetzt gleich und tragen denselben Tooltip.
- **Mit offenem Scan sind die Items die Arbeit, nicht sein Name.** Die
  Listen-Leiste stand immer auf „Scans": wer einen Scan lud, sah den Namen, den
  er gerade angeklickt hatte, ein zweites Mal und musste erst auf „Items"
  klicken. `scanList = null` heisst „noch nicht entschieden" — dann gilt
  `scanActiveList()` (bei offenem Scan: Items). Sobald jemand einen Reiter
  anfasst, steht dort seine Entscheidung; **das Öffnen eines Scans setzt sie
  zurück**, denn das ist ein Wechsel des Zusammenhangs. Dieselbe Mechanik wie
  `collapsed`.

  **Mit einer Ausnahme, und die ist der Grund für `scanTabAfterOpen`:** wer
  einen Scan aus der Scan-Liste heraus öffnet, arbeitet gerade an Scans. Springt
  der Reiter dann auf „Items", verschwindet genau die Maske, die sich soeben mit
  seinen Einstellungen aufgeklappt hat — und damit war der Scan **nicht mehr zu
  löschen**. Der Wunsch gilt genau einmal und wird danach gelöscht.

- **Der Reiter folgt der Auswahl, aber nur beim Wechsel** (`scanFollowTab()`).
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
Slot-Maske trägt einen eigenen Ein-Aus-Schalter (`scan_slot_set`, Feld
`active`), keinen Mitgliedschaftshaken: ein ausgeschalteter Slot behält seine
Daten und bekommt nur keine laufende Nummer mehr. Das ist der Unterschied, an
dem die alte Fassung scheiterte — ohne offenen Scan gab es keine
Mitgliedschaft, also stand dort gar kein Bedienelement, und „ich kann die
Slots nicht mehr ausschalten" war die Folge. Ein Schalter, der eine Eigenschaft
des Slots setzt, braucht keinen Scan als Bezug und ist deshalb immer da.

**„Alle raus" ist nicht „alle löschen".** Der eine nimmt aus der Mitgliedschaft
— Slot bzw. Item bleibt im Bestand —, der andere (`scan_delete_all()`)
nimmt ihn wirklich weg. Fünfzig Slots einzeln durchzuklicken war der Grund,
warum man diesen Knopf sucht; mit derselben Bezugsregel wie überall
(`_scan_slots()`/`_candidates()`: der offene Scan, sonst der Bestand) — ein
Slot eines *anderen* Scans bleibt unangetastet. Kein Bestätigungsdialog:
STRG+Z holt den ganzen Abzug zurück, genau wie beim einzelnen Löschen.

**Er steht am Ende der Liste, nicht im Kopf** (`scanDeleteAll()`). Im Kopf
stand er zwischen den Reitern und „Sortieren" und sah aus wie Sortieren —
`.btn.danger` wurde erst beim Zeigen rot. Der gefährlichste Knopf der Spalte
lag damit dort, wo man am häufigsten klickt, und sah aus wie der harmloseste.
Man braucht ihn selten, und wer ihn braucht, hat die Liste davor gesehen.
Dazu gilt seither überall: **ein gefährlicher Knopf ist auch in Ruhe getönt**
(`.btn.danger,.btn.quiet.danger`), nicht erst beim Zeigen. Die Ausnahme bleibt
das × an der Punktzeile — in einer Liste mit vierzig Zeilen wäre es lauter als
alles, woran man arbeitet.

**Der geöffnete Scan IST der vollständige Bestand** — und damit stellt sich die
Frage „gehört das hierher" gar nicht mehr. `scanVisible()` filtert nur noch nach
Kategorie; Slots und Items einer Sequenz gehören ihrem Scan, fremde gibt es dort
nicht zu sehen.

Hier stand einmal die Regel **„gehört dazu ODER wird gerade gesehen"**
(`dabei || erkannt`), und sie war die Antwort auf ein Problem, das der globale
Bestand hatte: Slots zweier Spiele lagen in einer Liste, also musste die Ansicht
entscheiden, welche sie anbietet. Mit dem Umzug auf Besitzeinheiten ist die Frage
verschwunden, und mit ihr die Regel — samt `_slot_im_bild()` und dem Slot-Feld
`detected`, das zuletzt berechnet und von niemandem mehr gelesen wurde.

Beim **Item** bleibt `detected` dagegen echt (`_detected_items()`, Feld
`detected_in`): es sagt nicht „gehört dazu", sondern **wo** das Item gerade
gefunden wurde. Das ist die nützlichste Auskunft der Erkennung und der Grund,
warum ein Treffer ein Vorschlag ist und keine Festlegung — „erkannt" ohne Beleg
wäre eine Behauptung.

**Der Name ist die Referenz — also zieht Umbenennen sie nach.** Slots und Items
stehen in Scans per Name; `_slot_rename`/`_item_rename` ändern jede
Fundstelle mit und sagen in der Statuszeile, wie viele es waren. Löschen räumt
sie ebenso weg. Und weil gespeichert wird, was **im Scan** steht
(`cfg.slots`/`cfg.items`), nicht der Arbeitsbestand des Reiters, muss nach jeder
Änderung `_sync_objects()` laufen — sonst steht ein gelöschtes Item beim
nächsten Speichern noch im Scan. Ein Test pinnt genau das fest.

**Der Weg steht als Weg da, nicht als Wand aus Knöpfen** (`_steps()`).
Bereich → Slots → Items, mit dem Stand aus den Daten abgeleitet; nur der aktuelle
Schritt trägt einen Knopf. Ein mitgeschriebener Fortschritt könnte von den Daten
abweichen, deshalb heisst „erledigt" schlicht: es ist da.

**Zwischen Schritt 2 und 3 liegt das Spiel.** Slots nimmt man oft an einem
*leeren* Inventar auf — dann gibt es noch nichts zu lernen. Man füllt es, nimmt
**neu** auf und lernt erst dann. Das steht in Schritt 3, weil es sonst niemand
ahnt: „Items lernen" auf dem alten Bild lernt leere Slots.

**Und die Anleitung klappt sich weg, wenn sie erledigt ist.** Der Weg, das Bild
und die Modus-Kacheln sind zusammenklappbare Abschnitte (`collapse-header` /
`collapse-body`); untereinander waren sie länger als die Spalte hoch ist, und die
Listen ganz unten — also das, womit man dauernd arbeitet — erreichte man nur
über die Bildlaufleiste. „So entsteht ein Scan" klappt sich von selbst zu,
sobald alle drei Schritte erledigt sind: beim ersten Mal ist es das Wichtigste
auf der Seite, beim zwanzigsten sind es drei Zeilen im Weg.

Zwei Regeln, ohne die es ein Rückschritt wäre:

- **Zugeklappt bleibt die Auskunft stehen**, nur die Bedienelemente gehen weg —
  im Kopf steht dann der offene Schritt, die Bildgrösse bzw. der aktuelle Modus.
  Platz sparen darf nichts kosten, was man beim Arbeiten braucht.
- **Die Automatik überstimmt keine Entscheidung.** `collapsed[…] === null` heisst
  „noch nichts entschieden" und lässt `collapseDefault()` gelten; sobald jemand
  einen Kopf anfasst, steht dort true/false und die Vorgabe schweigt. Ein
  Bedienelement, das zurückspringt, ist keine Hilfe.

**Die Bühne springt zum gewählten Slot** (`scanShowSelected()`). Liste und
Bild waren zwei getrennte Welten: einen Slot in der Liste anzuklicken markierte
ihn im Bild — nur sah man das nicht, wenn er gerade ausserhalb lag, und bei 45
Slots auf 1:1 ist das der Normalfall. Gescrollt wird **nur beim Wechsel der
Auswahl und nur, wenn er wirklich draussen liegt**: eine Bühne, die bei jedem
Neuzeichnen springt, nimmt einem die Stelle weg, die man gerade ansieht.

**Die Slot-Erkennung ist dieselbe wie im Konsolen-Editor** —
`detect_slots_in_image()` aus `editors/scan_services.py`, gerufen von
`slot_auto_detect`, `repair` und dem Studio (der Konsolen-Editor hatte dafür
einmal einen eigenen deutschen Namen — eine reine Weiterleitung, gelöscht). Modus `finden`: zwei Ecken um das Inventar, dann ein Klick auf einen
leeren Slot-Hintergrund, und alle liegen da; ein volles Inventar von Hand wären
90 Klicks. Zwei Erkennungen wären zwei Ergebnisse.

**Gesucht wird in einem Bereich, nicht im ganzen Bild.** Eine Farbe ist kein Ort:
liegt neben dem Inventar ein Menü in genau demselben Grau, wird es mitgefunden,
und heraus kommen zwanzig Slots, von denen acht keine sind — was erst beim
Erkennen auffällt, wenn man sie schon alle einzeln wegzuräumen hat. Der
`_search_area` schränkt deshalb die **Suche** ein, nicht das Bild: anders als
Modus `area` schneidet er nichts zu, gilt nur für diesen einen Durchgang und
ist danach weg (jeder Moduswechsel, ESC und jede neue Aufnahme räumen ihn ab).
Er wird gezeichnet, solange er steht — ein zu eng gezogener Bereich sähe sonst
aus wie ein zu weiter.

**Die Zelle wird um `scan_slot_inset` eingezogen** (`_with_inset()`) — dieselbe
Rechnung, die `slot_auto_detect()` im Konsolen-Editor seit jeher macht und die
hier fehlte: die Erkennung liefert die ganze Zelle samt Rahmen und Schatten, und
ohne Einzug lernt jedes Item den Rahmen als Merkmal mit. Abgezogen wird nie mehr,
als übrig bleiben darf. **Von Hand aufgezogene Slots bleiben unangetastet** —
dort ist das Rechteck genau das, was gemeint war.

Neu daran ist nur der Regler: `sv_tolerance` (Sättigung/Helligkeit) war fest auf
±50 verdrahtet, und **bei dunklen Oberflächen liegt der Panel-Hintergrund darin**
— dann verschmilzt alles zu einer Fläche und heraus kommt EIN Rechteck über dem
ganzen Inventar. Der Konsolen-Weg umgeht das, indem der Nutzer vorher eine enge
Region markiert; im Studio klickt man nur. `_slots_search()` probiert deshalb ein
enger werdendes Band und nimmt das Ergebnis mit den **meisten** Rechtecken —
gemessen an vier gestellten Panel-Farben lag der Umschlag bei 35, 25, 18 und 8,
also nicht bei einem Wert, den man fest eintragen könnte. Ein Rechteck über mehr
als der halben Fläche zählt nie mit: das ist das Panel, kein Slot.

**Vollbild ist die Voreinstellung, nicht die einzige Möglichkeit.** Wer dasselbe
Spiel mehrmals offen hat, arbeitet sonst auf einem Bild, in dem drei Viertel
stören. Der Aufnahmebereich lässt sich auf drei Wegen setzen — Fensterliste
(`winapi.list_windows()`), zwei Ecken im Bild (Modus `area`) oder direkt
(`scan_area_set`) — und der Rückweg ist ein Knopf.

Vier Eigenschaften, an denen das hängt:

- **Wählen und Aufnehmen sind zwei Dinge, also sind es zwei Klicks.**
  `scan_area_set()` setzt nur das Ziel und sagt, was als Nächstes kommt;
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
- **Slots ausserhalb werden gezählt und gesagt** (`_outside_hint()`). Ein zu
  eng gesetzter Bereich ist sonst still: die Slots stehen weiter in der Liste,
  sind aber nicht zu sehen, und man sucht den Fehler bei der Erkennung.

**Das Bild passt sich der Fenstergrösse an — aber nur, wenn niemand gezoomt
hat.** Die Bühne ändert ihre Grösse mit dem Fenster, das Bild tat es nicht: wer
klein aufnahm und dann gross zog, sah es in einer Ecke kleben, und ein Bereich
liess sich bei 31 % kaum noch treffen. `scanZoomManual` unterscheidet die beiden
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
Fenster-**Kennung** aus `list_windows()` mit: über den Titel ginge es nicht, der
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
  des Flags eine leere Fläche zurück. `is_blank()` erkennt das, und dann wird
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

**Wer in einem offenen Scan etwas anlegt, legt es FÜR ihn an** (`_add_to_scan()`). Ohne
das war ein frisch aufgezogener Slot sofort wieder weg: die Listen zeigen
standardmässig nur die Mitglieder, und er war keines — man musste den Filter
ausschalten, ihn suchen und ein Häkchen setzen. Gilt für neue Slots, gedoppelte
und gelernte Items.

**Und gefunden ist gefunden, auch wenn der Slot schon existiert.** Bei zwei
Spielen liegen die Slots des einen längst im Bestand; ein **neuer** Scan über
demselben Inventar legte deshalb nichts an — nahm aber auch nichts auf, und weil
die Listen nur Mitglieder zeigen, blieb er leer: „45 Slot(s) gefunden, alle schon
da" und keine einzige Marke im Bild. Genau der Fall, in dem man den Fehler bei
der Erkennung sucht, obwohl sie funktioniert hat. `_slot_at_position()` gibt
deshalb den **Namen** zurück statt ja/nein.

**Mit den Besitzeinheiten ist daraus wieder EINE Frage geworden: gibt es den
Slot schon?** Der Durchgang zählte drei Sorten (angelegt, aufgenommen, war schon
dabei), aber seit ein Scan seine Slots selbst besitzt, gibt es keinen Slot im
Bestand, der nicht dazugehört — `_add_to_scan()` meldete deshalb bei jedem
vorhandenen Slot „aufgenommen“, und ein zweiter Suchlauf über dasselbe Inventar
sagte „45 schon vorhandene in den Scan aufgenommen“ statt „alle schon da“. Die
Gegenprobe fand den toten Zweig („war schon dabei“ war nie mehr erreichbar).
Heute: angelegt oder schon dabei, und `_add_to_scan()` gibt nichts mehr zurück.

**Ein zweiter Suchlauf rät die Grösse nicht neu.** `detect_slots_in_image()`
normalisiert auf den Median **eines** Durchgangs — ein zweiter Lauf über
demselben Raster bekommt seinen eigenen und weicht ein paar Pixel ab, obwohl die
Slots im Spiel gleich gross sind. Ein Fund innerhalb von `_SIZE_TOLERANCE`
(6 px) übernimmt deshalb die Grösse, die schon feststeht
(`_existing_slot_size()`, zentriert über `_to_size()`). Was
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
Änderung.** Jedes Feld ist einzeln setzbar (`boss_set`, `icon_set`), keins
nur über einen Durchlauf erreichbar.

| | Item | Boss | Icon |
|---|---|---|---|
| Schritte | 3 (Bild, Slots, Items) | 5 (Bild, Region, Bosse, LLM/OCR, Fallback) | 4 (Bild, Region, Erkennung, Aktion) |
| Werkzeuge | Slot, Finden, Farbe, Klickpunkt, Bereich | Region, Klickpunkt | Region, Klickpunkt |
| gesucht wird | viele Dinge in vielen Flächen | ein Boss in **einer** Region | ein Symbol in **einer** Region |

Acht Regeln, an denen der Teil hängt:

- **Die Scan-Art ist Oberflächenzustand** (`scanKind` in `app.js`), wie `view`
  und `scanList`: sie steht nicht in der Momentaufnahme und nicht in der Brücke.
  Die Bühne (Aufnahme, Zoom, Scrollstand) bleibt beim Umschalten stehen — es ist
  dasselbe Bild, nur eine andere Frage daran. Wo ein Befehl trotzdem wissen muss,
  worauf er wirkt, **sagt der Aufruf es** (`{kind: "boss"}`); nur solange ein
  Werkzeug scharf ist, merkt sich die Brücke das Ziel (`_region_target`) — und
  `_tool_done()` räumt es mit weg.
- **Die Aufnahme ist EIN Schritt und gehört allen drei Arten.** Die Karte
  existiert genau einmal im Dokument und **wandert** in den Assistenten der
  offenen Art (`scanMaintainKind()`). Zwei Fassungen davon wären zwei Stellen, an
  denen eine Änderung an der Aufnahme vergessen werden kann — sie muss deshalb
  auch wieder zurückwandern, sonst fehlt dem Item-Assistenten sein erster Schritt.
- **Testen ist folgenlos.** `boss_test`/`icon_test` erkennen, zeigen und
  *benennen* die Aktion — ausgeführt wird sie nie, und das steht in der
  Testleiste dabei. Ein Testknopf, der im Editor eines Autoclickers wirklich
  klickt, ist die schlechteste denkbare Überraschung. Ein Test misst es.
- **Gerechnet wird mit `_check_profile_match()`** aus `runtime/item_scan.py` —
  derselben Funktion, die im Lauf entscheidet, mit `_ConfigOnly` als
  `state`-Stellvertreter. Eine zweite Rechnung „nur für die Vorschau" wäre eine
  Vorschau, die etwas anderes zeigt als das, was passiert.
- **Der Vorschlag ist der Kern des Fehlerfalls.** Findet ein Icon-Scan zu wenige
  Marker, nennt die Testleiste die kleinste Toleranz, bei der es klappt
  (`_tolerance_proposal()`) — ein Klick. Ein Test, der nur „fehlgeschlagen" sagt,
  lässt einen genau dort stehen, wo man vorher war.
- **Die Aktionswerte kommen aus `models.py`**, über die Momentaufnahme
  (`actions.boss` / `actions.icon` / `actions.scan_modes`). Die Ansicht erfindet
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
dort und sonst nirgends. Der Rückgängig-Abzug (`_detection_state()`) nimmt sie
ebenso mit: ein Zurück, das die Slots zurückdreht und den Boss-Scan stehen lässt,
wäre ein halbes Zurück, und das ist schlimmer als gar keins.

**Der Konsolen-Editor bleibt** (`CTRL+ALT+N`). Er schreibt dieselben Dateien —
deshalb zählen die `boss_scans/`- und `icon_scans/`-Ordner der Sequenz samt ihrer
`boss_scans/bibliothek.json`
seit dem Umbau beim „auf Platte hat sich etwas geändert"-Vergleich mit
(`_detection_paths()`). Ohne sie meldete der Hinweis ausgerechnet das nicht, woran
man gerade arbeitet: ein Lauf legt per LLM entdeckte Bosse in der Bibliothek ab.

**Was fehlt:** der Boss-Watcher hat keine eigene Ansicht (er benutzt denselben
Scan, nur ein anderer Block-Typ), und OCR/LLM lassen sich hier ein- und
ausschalten, aber nicht *ausprobieren* — der Testknopf misst Template und Marker.
Für das LLM gibt es nur die Erreichbarkeitslampe (`llm_check`); ein echter
Probelauf kostet bis `llm_timeout` und hat im Zeichnen einer Momentaufnahme
nichts verloren.

**Der Reiter „Teilen" arbeitet auf dem GESPEICHERTEN Stand** (`bridge_share.py`).
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
- **Die Config wird hineingeschrieben, nicht getauscht** (`apply_config()`): auch
  im Subprozess gibt es ein Config-Objekt.

Nach dem Import lesen beide Seiten neu — der Reiter selbst und, über den
Briefkasten-Befehl `data_reload`, der Hauptprozess.

**Der Reiter „Werkzeuge" holt nach, was nur die Konsole konnte** (`bridge_tools.py`).
Prüfen (`check`), kalibrieren (`fix`) und die Klick-Runde (`reclick`) lagen im
Punkte-Menü — also ausgerechnet die Handgriffe, die man nach einem Bildschirm-Umbau
braucht, und die man dann in einem Fenster sucht, das schon offen ist.

**Zwei davon laufen HIER, eines drüben — und die Grenze ist nicht der Bildschirm.**
Der Studio-Prozess sieht `AutoClickerState` nicht, aber sehr wohl das
Betriebssystem: der Scans-Reiter nimmt Screenshots auf, `point_capture()` liest
die Mausposition über eine globale Taste. Genau diese zwei Griffe braucht eine
Kalibrierung, also läuft sie im Fenster. Die Klick-Runde braucht dagegen einen
**systemweiten Maus-Hook**, und der gehört dem Prozess, der auch die Hotkeys pumpt
— sonst gingen `CTRL+ALT+K`/`U`/`H`/`J` ins Leere. Nur dafür gibt es den
Briefkasten-Befehl `reclick`.

**Und weil sie drüben läuft, gibt es einen Rückkanal** (`.reclick.json`,
`RECLICK_STATUS_FILE`). Ohne ihn stand im Fenster nur „gestartet", während die
Konsole jeden Schritt einzeln meldete — und *welcher Punkt gerade dran ist* ist
genau die Frage, die man beim Klicken hat. Dieselbe Bauart wie `.run.json` und
`.recording.json`: kein Log, sondern der Stand JETZT, überschrieben bei jeder
Bewegung der Runde. Gelesen wird er über `reclick_status()` im `ask()`-Kanal.

Drei Regeln dazu:

- **Der Verlauf ist ein eigenes Feld, kein abgeleiteter Wert**
  (`state.reclick_history`, Einträge `(Punkt-ID, Art)`). Naheliegend wäre,
  ihn aus `reclick_set` zu rechnen — das geht nicht: ein **bestätigter**
  Punkt (innerhalb `MATCH_TOLERANCE`) landet dort bewusst nicht, und im Fenster
  sähe er damit genauso aus wie ein übersprungener. Beide ändern nichts, aber
  nur einer heisst „ich habe hingesehen".
- **Die Zusammenfassung wird eingesammelt, BEVOR `stop_reclick()` die Listen
  leert.** Danach ist der Verlauf weg, und das Fenster zeigte eine leere Runde
  — ausgerechnet in dem Moment, in dem man nachsieht, was sie ergeben hat.
  Dieselbe Regel und derselbe Grund wie bei `status.finish_run()`.
- **Geschrieben wird aus dem Hook heraus**, und das widerspricht dem Satz oben
  nur scheinbar: gemeint ist dort das vollständige Speichern am Ende (Sequenz
  plus Punkte serialisieren, mehrere Dateien). Hier geht eine knappe JSON-Zeile
  über `atomic_write` raus — dieselbe Grössenordnung, die die Aufnahme bei
  **jedem** aufgezeichneten Klick schreibt.

Ein Stand, der `active` behauptet und älter als 5 s ist, gilt als **verwaist** —
dieselbe Rechnung wie beim Laufstatus, und aus demselben Grund: ein abgestürzter
Hauptprozess hinterlässt sonst eine Runde, der niemand mehr zusieht.


**Ein Griff mit der Maus sagt, dass er wartet** (`WAIT_ACTIONS` in `app.js`,
`WAIT_TIMEOUT` in `bridge_contract.py`). Acht Aufrufe der Seite warten über
`_await_position()` bzw. `area_capture()` **global auf ENTER** — und der
Brücken-Aufruf blockiert dabei bis zu einer Minute. Die Seite bekommt in dieser
Zeit keine Antwort, kann also nichts anzeigen, was von drüben käme; ohne einen
Hinweis **vor** dem Aufruf sah es aus, als tue das Fenster nichts. Betroffen sind
Stelle und Bereich im Editor, „Punkt aufnehmen" und „Neu messen", das Messen im
Farben-Werkzeug, der Referenzpunkt der Kalibrierung und die Parkposition in den
Einstellungen.

`withWait(kind, name, daten)` legt den Kasten davor und ruft darunter den Kanal,
den der Aufruf ohnehin hätte (`"call"` / `"ask"` / `"tool"`). Drei Regeln:

- **Die Zeitgrenze steht an EINER Stelle** und wird mitgeliefert
  (`wait_timeout` in Momentaufnahme und Werkzeug-Daten). Ein Countdown, der
  neben dem echten Zeitablauf der Brücke läuft, ist schlechter als keiner.
- **Der Fortschritt wird nicht erfunden.** `area_capture()` will zwei
  Tastendrücke, aber beide Ecken sind EIN Aufruf (die Hand soll zwischendurch
  nicht zum Fenster zurück) — die Seite erfährt vom ersten ENTER nichts. Sie
  sagt deshalb vorher, wie viele kommen, statt eine Ecke 1/2 zu behaupten, die
  sie nicht sehen kann.
- **Ein Test hält beide Seiten gegeneinander**: welche Methoden warten, steht in
  der Brücke; dass die Seite sie über `withWait` ruft, in `app.js`. Er prüft
  beide Richtungen — eine wartende Methode ohne Eintrag ist genau die, bei der
  das Fenster wieder stumm ist, und ein Eintrag für etwas, das gar nicht wartet,
  verspricht einen Kasten, den niemand je sieht.

Dabei ist aufgefallen: **`calib_reference` wartet auch bei „Trotzdem setzen"**
erneut auf ENTER, misst die Stelle also neu. Das ist so gewollt (bestätigt wird
die abweichende Farbe, nicht eine schon erfasste Stelle) — ohne den Kasten sah
der Knopf aber aus, als täte er nichts.


**Jedes Werkzeug sagt, WORAUF es wirkt** — und „jedes" heisst jedes: „Farben
analysieren" trug als einziges keine Bezugszeile, während in `WZ_TOOLS`
`scopeKind: "inventory"` stand. Das wäre die falsche Auskunft gewesen (es misst nur
den Bildschirm und schreibt nirgends hin), und weil die Zeile gar nicht
gezeichnet wurde, fiel die Unwahrheit nicht auf. Dafür gibt es die vierte Art
**`none`** — kein fehlender Wert, sondern eine eigene Aussage, und bei einem
Werkzeug neben `kalibrieren` und `nachklicken` die beruhigende.

Die Kopfleiste blendet hier ihr
Sequenz-Speichern aus (der Reiter bearbeitet andere Dateien) — und blendete
lange auch die Auswahl mit aus, womit der Sequenzname weg war; bei der
Klick-Runde ist das genau die Frage, die man sich stellt. Seit die Auswahl
überall steht, ist der frühere Ersatz („offene Sequenz <Name>" links) wieder
**weg**: er liess den Namen dreimal gleichzeitig dastehen. Ein einzelner Name
oben wäre trotzdem falsch gewesen: Prüfen und
Kalibrieren gehen über den **ganzen Bestand**, nur die Klick-Runde meint **eine**
Sequenz. Deshalb trägt jedes Werkzeug seine eigene Bezugszeile (`wzScope()`), und
links steht die offene Sequenz als Einordnung.

Daran hing ein echter Fehler: `command_reclick` nahm `state.active_sequence` aus
dem Hauptprozess — der hat womöglich eine ganz andere geladen als die im Studio
offene. Man klickt dann eine Runde lang die Punkte einer fremden Sequenz nach und
merkt es nicht, weil jeder Klick im Spiel ja etwas tut. Die Datei kommt jetzt mit,
wie bei `command_start`; ohne sie passiert gar nichts.

Vier Regeln, an denen der Reiter hängt:

- **Gerechnet wird mit denselben Funktionen wie in der Konsole**
  (`import_export.calibrate_inventory`, `diagnostics.check_setup`), auf einem frischen
  State von Platte (`_inventory()`). Eine zweite Rechnung „fürs Fenster" wäre eine,
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
  leben in `self._calib` und sind nach `calib_cancel()` spurlos weg. Davor
  entsteht ein vollständiges Export-ZIP (`backup_before_calibration`), und ein
  laufender Lauf blockiert — er klickt sonst mitten im Umbau auf halb verschobene
  Stellen.
- **`with_slots` ist AUS.** Eine aus einer Mausposition abgeleitete Verschiebung ist
  für ein Klickziel gut genug, für eine Scan-Region nur eine Näherung. Dafür gibt
  es `repair` im Konsolen-Slot-Editor, das die Slots **misst** — und nach einer
  Reparatur dürfen sie kein zweites Mal wandern. Der Reiter sagt das dazu, statt
  den Weg zu verschweigen.

Danach lesen beide Seiten neu: der Reiter seine Punkte, der Hauptprozess über den
Briefkasten-Befehl `data_reload` — der zieht dabei auch die Punkte der Sequenz
nach, denn bei einer Kalibrierung wandert **jede** gespeicherte Stelle.

**Der Reiter „Bericht" liest `logs/`** (`bridge_report.py`). Der Live-Run zeigt das
Jetzt, dieser Reiter das Gestern — und er beantwortet die Frage, die man nach einer
langen Nacht hat und bis dahin nur auf der Kommandozeile stellen konnte: **welcher
Schritt läuft am häufigsten in den Timeout?**

Fünf Regeln, an denen er hängt:

- **Gerechnet wird in `tools/log_report.py`**, mit derselben Funktion, die die
  Kommandozeile benutzt. Dafür ist die Auswertung dort in zwei Hälften zerlegt:
  `evaluate()` gibt **Daten** zurück und druckt keine Zeile, `report()` druckt sie.
  Eine zweite Auswertung „fürs Fenster" wäre eine, die andere Zahlen nennt als der
  Weg, den die README beschreibt. Ein Test misst beides — die Zahlen *und* dass
  `evaluate()` schweigt: eine übrig gebliebene `print`-Zeile landete in der Konsole
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
- **Er baut mit dem, was da ist.** Kennzahlen sind `wz-metrics` (dieselben
  Kacheln wie im Werkzeuge-Reiter), Karten sind `share-card`, die Spalten sind
  `section` — eigene Klassen gibt es nur für die Rangzeile und die
  Sitzungsauswahl, und **eine** Rangzeile trägt alle vier Listen plus den Ertrag.
  Ein achter Reiter, der sich seine eigene Gestalt gibt, kostet mehr als er
  einbringt. Dazu gehört, dass untereinander stehende Blöcke auf **derselben**
  Kante liegen: die Kennzahlen dürfen 880 px, die Karten kamen mit 720 — gestapelt
  waren das zwei rechte Kanten, 160 px auseinander und damit nah genug, dass es wie
  ein Rundungsfehler aussieht statt wie Absicht.

Zwei Tests halten die Verdrahtung fest, und beide prüfen **beide** Richtungen: jeder
`data-view`-Knopf braucht seine Umschalt-Zeile in `setView()` (und keine
Zeile bleibt ohne Knopf), und jeder Rauchtest unter `tests/smoke/` muss in
`SMOKE_TESTS` (`tests/all_tests.py`) stehen — eine getippte Liste ist genau die
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
vergleicht `config_write()` den geschriebenen Stand mit dem Gesendeten und gibt
die Abweichungen zurück; sie stehen rechts, bis der nächste Wert angefasst wird. Der
Vergleich zieht Zahlen normalisiert (`_same_value`: `600` und `600.0` sind dieselbe
Einstellung), lässt `bool` aber ausgenommen — dieselbe Rechnung wie `_equal()` im
Start-Durchgang.

**Es gibt EIN Config-Objekt pro Prozess.** `state.config` **ist** das Modul-`CONFIG`
(gesetzt in `main.py`), und wer die Werte ändert, schreibt mit `config.apply_config()`
hinein, statt das Objekt auszutauschen. Vorher war `state.config` eine Kopie — womit
jedes Modul mit `from .config import CONFIG` (`imaging`, mehrere Item-Editoren)
dauerhaft die Werte vom Programmstart las. Ein Test prüft die Quelle: eine Zuweisung
an `.config` ausserhalb von `main.py` ist ein Fehler.

Damit die Datei auch im Speicher ankommt, gibt es den Briefkasten-Befehl `config`:
das Studio legt ihn nach dem Schreiben ab, `command_config()` lädt `config.json` neu
und schreibt sie in dasselbe Objekt. Ein laufender Lauf zieht sofort mit — der Worker
liest `state.config` bei jedem Schritt neu.

**Und der Schreiber lädt sich selbst mit.** `config_write()` ruft
`apply_config(CONFIG, neu)` auf dem eigenen Prozess — das fehlte, und damit war
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
  `null`, wo die Dataclass das erlaubt (`optional_fields()`), sonst 0.
- **Enums als Kacheln, alles Wachsende als Liste** — dieselbe Regel wie beim
  Block-Typ. Die Auswahl ist im Code festgelegt und kurz.
- **Alle Abschnitte stehen auf EINER Seite, die Liste links springt nur**
  (`cfgScrollTo()`, und beim Scrollen zeigt sie mit, wo man steht:
  `cfgSpy()`). Vorher zeigte die Mitte genau einen Abschnitt — bei
  „Programmstart" ein einziges Feld über einer leeren Fläche —, und wer einen
  Wert suchte, klickte sich durch vierzehn Seiten. Die Suche lässt nur die
  Abschnitte mit Treffern stehen. Ein Neuaufbau nach einer Änderung behält die
  Scrollposition; gelesen wird sie **vor** `replaceChildren()`, danach ist die
  Mitte kurz leer und `scrollTop` steht auf 0.
- **Die Abschnittstitel sind Anzeige, keine Schlüssel** — deutsch, ein Stil
  (`_CONFIG_SECTIONS` in `config.py`). Dort standen GROSSBUCHSTABEN mit „ue"
  (NACHPRUEFUNG) neben englischen (HUMANIZATION, TIMING, DEBUG). In der Datei
  steht zwischen den Gruppen nur eine Leerzeile, der Titel kommt dort nicht vor.
- **Eine Einstellung ist ein Sprungziel** (`goTo({view: "settings", key})`):
  scrollt hin, lässt die Zeile aufleuchten, setzt den Fokus ins Feld. Leere
  Zustände anderer Reiter nennen deshalb keinen Config-Schlüssel mehr, sondern
  bieten den Sprung an („Marktwert-Datei eintragen" im Bericht). Die
  Änderungskarten rechts springen ebenso zu ihrem Feld.
- **Ein abhängiges Feld heisst `.faded`** — `cfgRow()` setzte `blass`, das CSS
  kannte nur `.cfg-row.faded`, und abhängige Felder waren seit dem
  Englisch-Umbau nie blass. Wer eine Zustandsklasse umbenennt, sucht sie auch in
  den Strings, die sie zusammensetzen (`" faded"`).
- **Eine Stelle fährt man an** (`scan_park_mouse`): Maus hin, ENTER — derselbe Weg
  wie beim Klick-Block, nur ohne Punkt anzulegen. Eine Parkposition gehört nicht
  zu den Punkten der Sequenz.

**Start, Pause und Stopp gehen über einen Briefkasten** (`mailbox.py`), nicht direkt:
dieser Subprozess hat keinen Zugriff auf `state.stop_event`. Er legt eine Datei ab,
und der Hauptprozess holt sie **im Main-Thread, in derselben Schleife, in der auch
seine Hotkeys ankommen** (`_check_commands` in `main.py`, alle 250 ms im Leerlauf).
Damit ist ein Studio-Knopf exakt so viel wert wie ein Tastendruck: dieselbe
Reihenfolge, dieselben Sperren, kein zweiter nebenläufiger Pfad. Ein Watcher-Thread
hätte genau den gebracht — für eine Datei, die niemand eilig braucht.

Die Regeln des Briefkastens stehen im Modul-Docstring; eine ist wichtiger als die
anderen: **ein Befehl darf nie nachfeuern.** Wer im Studio auf „Starten" drückt,
während gar kein Hauptprozess läuft, bekommt keine Wirkung — und darf sie auch nicht
bekommen, sobald einer startet. Dafür sorgen `MAX_AGE` und das Leeren beim Start.

**Geleert wird durch Umbenennen, nicht durch Lesen-und-dann-Löschen** (`fetch_command()`).
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
(`command_start` lädt die mitgeschickte Datei; das Studio speichert vorher, sonst liefe
etwas anderes als das Angezeigte), und **`handle_toggle()` wird nicht für „stopp"
benutzt** — es ist ein Umschalter und würde starten, wenn gerade nichts läuft.

## Blöcke aus einer anderen Sequenz

**„Blöcke einfügen" (aus einer anderen Sequenz) ist eine Kopie, kein Aufruf**
(`block_import`). Die billige Fassung der Bausteine-Idee: alle Blöcke der
Quelle in Laufreihenfolge hinter den gewählten, mit **eigenen Punkten**
(`_points_copy_along(…, source=…)`, Punkt-IDs sind sequenzlokal). Ein Block,
dessen Punkt schon in der Quelle fehlt, bleibt draussen, und Scans kommen nicht
mit — beides steht in der Meldung, STRG+Z nimmt den ganzen Durchgang zurück.

## Zwei Prozesse, ein Ordner; das Programm-Symbol

**Zwei Prozesse, ein Ordner — und der Zweite gewinnt nicht mehr kommentarlos.**
Das Studio merkt sich beim Laden den Zeitstempel der Sequenzdatei
(`_state_remember()`) — die Punkte stehen darin, es ist also EIN Stand für
beides; hat sie sich beim Speichern geändert, fragt es
nach, statt zu überschreiben. Der Fall ist Alltag: eine Aufnahme im Hauptprozess
legt Punkte an, `save_points()` schreibt die Sequenz. Die Rückfrage ist derselbe
Dialog wie bei ungespeicherten Änderungen — er trägt Titel, Text und
Knopfbeschriftung jetzt aus der Brücke, weil sich die Fälle zu sehr
unterscheiden (bei „ausserhalb geändert" gibt es nichts zu verwerfen).

**Gefragt wird VOR dem Umbenennen, und gefragt wird nach der GELADENEN Datei.**
Beides war einmal andersherum, und beides machte die Rückfrage genau dann
wirkungslos, wenn sie zählt: der Ordner wurde zuerst verschoben, und danach
prüfte `_changed_externally()` den *neuen* Pfad — den es vorher gar nicht gab, also
war dort nie etwas „fremd geändert". Beim Umbenennen wurde deshalb kommentarlos
überschrieben, obwohl gerade dort eine Aufnahme des Hauptprozesses im alten
Ordner liegen kann. Geprüft wird jetzt die Datei, deren Inhalt gleich ersetzt
wird — also die geladene, vor jeder Bewegung auf der Platte.

**Und die Notsicherung nimmt die Punkte mit.** `rescue_write()` (beim
Schliessen des Fensters, nach `backups/`) schrieb einmal
`board_to_sequence(self.board)` ohne `palette_to_points(self.points)`:
die Sicherung, die man beim Absturz aufmacht, enthielt jeden Schritt mit einer
`point_id`, die ins Leere zeigt. Ein Rettungsanker, der die halbe Sequenz
rettet, ist schlimmer als keiner — man merkt den Verlust erst beim Laden.

**Das eigene Symbol braucht zwei Dinge, nicht eins.** Titelleiste und ALT+TAB
nehmen es aus `WM_SETICON` (`set_window_icon()`) — aber erst, wenn es das
Fenster gibt: `webview.start(func)` ruft seinen Callback davor auf, deshalb die
Frist (`warten=`). Die **Taskleiste** ignoriert das Fenstersymbol, solange sie
das Fenster unter der ausführenden Datei einsortiert, und die heisst `python.exe`;
dafür gibt es `set_app_id()`, und die muss **vor dem ersten Fenster** laufen.
Zwei Mechanismen, zwei Aufrufe, zwei Tests — wer nur einen setzt, sieht das
Ergebnis an genau einer der beiden Stellen.

Gezeichnet wird das Symbol **aus den SVG-Dateien der Oberfläche, nicht aus
einem getippten Raster** und nicht aus einer Binärdatei im Repo. Der Browser
lädt sie direkt, `autoclicker/symbol.py` liest sie mit der Standardbibliothek —
nur gefüllte Pfade aus `M`/`L`/`C`/`Z` plus eine optionale Rotation — und
rastert sie zeilenweise mit Kantenglättung (`SAMPLES`² Abtastungen je Pixel);
die Aussparungen bleiben echte Transparenz statt einer dunklen Ersatzfarbe.
Hier stand einmal eine Liste von Formen in Python, die das SVG von Hand
nachzog, und davor ein 16×16-Raster aus Nullen und Einsen — beides Kopien des
Motivs, die beim nächsten Entwurf veralten.

**Zwei Dateien, weil es zwei Grössen sind — nicht zwei Motive.**
`web/sequenz-studio-logo.svg` ist das Logo; bei 16 px aber war es graues
Rauschen (seine Linien sind dort schmaler als ein Pixel), und das genau dort,
wo man das Symbol am häufigsten sieht: Browser-Tab und kleines Fenstersymbol.
`web/sequenz-studio-logo-small.svg` ist dieselbe Kette mit vier statt neun
Knoten, jede Kante auf dem 16er-Raster. `symbol.logo_path(kante)` wählt: bis
`SMALL_UP_TO` (24) das kleine, darüber das grosse. Ab 32 px ist das grosse
lesbar genug, und der Nutzer will dort das Original sehen — das kleine springt
nur ein, wo vom grossen nichts übrig bleibt, nicht darüber hinaus.

Zwei Einzelheiten des kleinen, die man leicht wieder verliert: **das Dreieck
endet stumpf**, genau so hoch wie die Linie, die dort anschliesst (mit Spitze
stach die dickere Linie seitlich aus ihr heraus), und es ist **höher als die
übrigen Knoten** — sonst bleibt bei 16 px von der Keilform nur ein Stummel.

**Zwei Dateien, drei Verwendungen** — und der Rasterer liegt deshalb nicht in
`winapi.py`, sondern in einem Modul, das weder Windows noch Pillow kennt:

| wer | wozu |
|---|---|
| `winapi._icon_bits()` | ICO-Bits für `WM_SETICON` (16 klein, 32 gross) |
| `tools/symbol.py` | PNG-Dateien und eine `.ico` für Verknüpfungen |
| `web/index.html` | Favicon (klein) und Kopf (gross, 30 CSS-Pixel) |

Alle gehen über `symbol.pixel_rows(kante)` bzw. die Datei selbst; Tests halten
fest, welche Grösse welche Datei nimmt, dass Favicon und Kopf die richtige
nennen, dass beide dieselbe Farbe tragen, und dass jedes SVG nur die Befehle
benutzt, die `_path_polygons()` lesen kann — ein `A` aus einem CAD-Export fiele
sonst erst beim Rastern mit `ValueError` um. Geprüft wird dabei die
**Eigenschaft** (Maske vorhanden, erste Farbfläche ist eine flache Hex-Farbe,
Befehlsmenge), nicht die Zeichnung: ein Detail eines Motivs fällt beim nächsten
Entwurf um, ohne dass etwas kaputt wäre.

**Die flache Farbfläche muss die ERSTE im Dokument bleiben.** `symbol.py`
nimmt das erste `rect` mit Maske und will dort sechs Hex-Ziffern; Verlauf,
Rand und Innenschatten liegen **darüber** und werden beim Rastern nicht gesehen
— genau darauf beruht die Plakette, und deshalb bleibt das 16-px-Symbol eine
lesbare flache Fläche.

**Die Bilddateien werden geschrieben, nicht eingecheckt.** `python tools/symbol.py`
legt PNGs und eine `.ico` an (ohne Pillow — beide Formate sind von Hand
zusammensetzbar, wenn man sich auf unkomprimierte Zeilen bzw. eingebettete PNGs
beschränkt). Eine Binärdatei im Repo wäre eine Kopie des Motivs, die niemand
mitzieht — dasselbe Argument wie bei „Referenzen statt Kopien".

## Stellen anfahren; Regeln beim Erweitern der Oberfläche

**Eine Stelle fährt man an, statt sie zu tippen** (`point_capture()`): Maus hin,
ENTER — derselbe Weg wie `area_capture()` für Screenshot-Bereiche, nur mit
einer Ecke. Die Farbe wird dabei gleich mitgemessen, denn der Bildschirm zeigt in
diesem Moment genau das Richtige. Gesetzt wird über `point_set`/`point_create`,
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
  Duplizieren landen die Kopien **hinter der letzten** Gewählten (je Phase) und
  werden zur neuen Auswahl. Jede Kopie einzeln hinter ihr Original zu setzen zerrisse eine
  Mehrfachauswahl in abwechselnd Original/Kopie. Kopiert wird tief
  (`copy.deepcopy`), **und die Kopie bekommt eigene Punkte**.

  Hier stand einmal das Gegenteil („ein Duplikat ist erst mal derselbe Klick"),
  mit dem Argument, ein zweiter Punkt an derselben Stelle sei die Doppelung, die
  `point_at_position()` überall sonst vermeidet. Das Argument stimmt für
  *unabsichtliche* Dubletten aus einer Aufnahme — hier war es falsch: **man
  dupliziert einen Block, um ihn zu ändern.** Zeigten beide auf denselben Punkt,
  verstellte jede Korrektur an der Kopie auch das Original, und auffallen würde
  es erst viel später an einer Stelle, an der man es nicht mehr sucht. Der Preis
  sind zwei Punkte auf einer Stelle, bis einer umzieht.

  `_points_copy_along()` führt dafür **eine Abbildung für den ganzen
  Durchgang**, und die hat zwei Wirkungen: innerhalb eines Blocks bleibt
  zusammen, was zusammengehört (bei FARBE+KLICK sind Klick und Prüf-Pixel
  derselbe Punkt — sonst wartete die Kopie auf eine andere Stelle, als sie
  klickt), und zwischen mehreren kopierten Blöcken bleibt die Beziehung erhalten
  (zwei Gewählte auf einem Knopf ergeben zwei Kopien auf **einem** neuen, nicht
  auf zweien). Eine Referenz ins Leere wird nicht wiederbelebt: sie bleibt, wie
  sie ist, statt still zu einem Klick auf (0, 0) zu werden.

  **Das Verschieben bleibt davon unberührt**: `point_set()` ändert weiterhin
  den PUNKT, und jeder Schritt darauf zieht mit. Genau das will man, wenn zwei
  Blöcke wirklich denselben Knopf klicken und der Knopf umzieht — ohne das wäre
  jede Kalibrierung eine halbe. Ein Anlauf, das im Inspektor per Copy-on-Write
  zu lösen, kurierte nur das Symptom und nahm dabei diese Regel mit.

  **Aber ein geteilter Punkt sagt, dass er geteilt ist** — sonst ist die Regel
  eine Falle. An einer echten Aufnahme hatte `point_at_position()` den Klick auf
  denselben Knopf in Loop 1 und Loop 4 zu EINEM Punkt zusammengelegt (richtig
  so). Wer dann Loop 1 per „Stelle mit der Maus setzen" eine andere Stelle gab,
  verstellte Loop 4 mit — und suchte den Fehler in der Aufnahme: „der Punkt war
  im Loop 4 an einer völlig falschen Stelle". Dass die beiden denselben Punkt
  teilen, stand nirgends; die Regel dazu stand nur im ⓘ. Drei Dinge dagegen,
  und keins davon ändert die Regel:

  - Der Inspektor nennt die **anderen** Verwendungen des Punkts (`point_others`,
    `_point_usages(…, ausser=step)`) — als offener `hint`, denn das ist
    Zustand; das Warum bleibt im ⓘ. **Gebündelt, nicht aufgezählt**
    (`_point_usage_groups()`): eine Zeile je Phase, jeder Block einmal,
    Folgen ab drei als Bereich („Blöcke 1–5, 7–24"), und eine Rolle nur, wenn
    sie etwas sagt (Nachprüfung, ELSE) — Stelle und Prüf-Pixel sind bei
    FARBE+KLICK derselbe Punkt. Als Fliesstext standen neun Blöcke als
    achtzehn Einträge da, die Phase bei jedem wiederholt. Gezählt wird für
    Löschschutz und Punkte-Liste weiter über `_point_usages()` (jede Rolle).
  - Das Verschieben **sagt, wer mitzieht** („zieht 1 weitere Verwendung mit:
    Loop 4 · Block 2 · Stelle", `_moved_along()`), und zwar ohne den Block, an dem
    man gerade sitzt: der zählt nicht als „weiterer".
  - **`point_detach()`** gibt dem gewählten Block einen eigenen Punkt und
    lässt die anderen auf dem alten — das Gegenstück zur Verschiebe-Regel für den
    Fall „dieser eine Block soll einen *anderen* Knopf klicken". Dieselbe Bauart
    wie beim Duplizieren (`_points_copy_along`): Klick und Prüf-Pixel eines
    FARBE+KLICK-Blocks wandern gemeinsam.
- **Die Auswahl darf über Phasen reichen, die Sammelaktionen arbeiten je Phase.**
  Hier stand „die Auswahl lebt in genau einer Phase", weil „eine Position hoch"
  quer über Phasen keine Bedeutung hätte. Das kostete genau den Fall, für den man
  sie braucht: nach einer Aufnahme mit vier Loops dieselbe Wartezeit an zehn
  Blöcke setzen — viermal, Phase für Phase. Heute nimmt STRG+Klick in einer
  anderen Phase dazu (`sel_lane`/`sel_rows` = die Phase des letzten Klicks,
  `sel_other` = die übrigen), und **jede Sammelaktion fragt
  `_selection_groups()`** statt `sel_lane` direkt: Wartezeit und Löschen
  wirken auf alle, ALT+↑/↓ schiebt jede Phase in sich (wer an der Kante steht,
  bleibt stehen, ohne die anderen aufzuhalten), Duplikate landen hinter der
  letzten Gewählten **ihrer** Phase, Ziehen sammelt alles in Board-Reihenfolge
  am Ziel ein. Umschalt+Klick bleibt ein Bereich **innerhalb** einer Phase — die
  Phasen stehen nebeneinander, ein Bereich quer darüber hätte keine sichtbare
  Reihenfolge. Die Seite zählt `S.selection.count`, nie `rows.length` (das sind
  nur die Zeilen der letzten Phase). Phasen werden an der **Identität** erkannt
  (`_lane_index()`), nicht mit `lanes.index()`: `Lane` ist eine Dataclass, und
  zwei gleich aussehende Phasen fand `index()` immer als die erste.
- **Die Karte zeigt wenig, der Inspektor alles.** Auf die Karte gehört, was man beim
  Überfliegen von 50 Blöcken braucht (Typ, Ziel, Wartezeit, Trigger, ELSE, Warnung);
  alles Weitere steht rechts. Eine Wartezeit von 0 kommt gar nicht erst auf die Karte —
  „sofort" unter jedem zweiten Block ist Rauschen.

  **Zum Ziel gehört die Farbe des Punkts** (`point_color`, das Feldchen vor der
  Stelle) — bei jedem Block mit einer STELLE-Zeile (Klick, Farbe+Klick), nicht
  nur an der Farb-Bedingung. Dort stand sie zuerst allein („wartet bis RGB(…)
  da"), und ein reiner Klick zeigte nur Koordinaten: beim Umsortieren einer
  Aufnahme unterscheidet niemand `(4405,555)` von `(4419,550)`, den grünen Knopf
  vom roten schon. Ohne gemessene Farbe kein Feldchen — ein leeres Kästchen sagt
  nichts, was der Inspektor nicht besser sagt. Die Stelle ist bei diesen Blöcken
  die **erste** Zeile (`_lines`); daran hängt die Ansicht das Feldchen, mit
  derselben CSS-Regel wie das an der Bedingung. Hier stand „jeder Block, der
  einen Punkt hat" — und ein Warten-Block trug das Feldchen vor seiner
  Wartezeit, ein Item-Scan mit einem Rest-Punkt vor seinem Scan-Namen. Deshalb
  prüft `_block_json` jetzt, dass die erste Zeile wirklich STELLE heisst.
- **Diskrete Bedienelemente melden sofort, Tipp-Felder erst beim Verlassen** (`change`,
  nicht `input`). Jede Meldung baut die Ansicht neu, und ein Neuaufbau mitten in der
  Eingabe nimmt das Feld weg, in das gerade getippt wird. Dieselbe Regel galt schon in
  der DPG-Fassung. Folge davon: `STRG+S` muss vorher `blur()` auslösen, sonst geht der
  zuletzt getippte Wert verloren.

  **Und jeder Neuaufbau rettet den Fokus hinüber** (`rememberFocus()` /
  `restoreFocus()`). Weil Tipp-Felder beim *Verlassen* melden, ist es genau der
  TAB-Sprung, der den Neuaufbau auslöst — bis die Brücke antwortet, steht der
  Fokus schon im nächsten Feld, und `replaceChildren()` wirft es weg. Sichtbar
  wurde das beim Item: Namen tippen, TAB nach Kategorie, Cursor weg, nochmal
  klicken. Gemerkt wird die **Position** unter den Eingabefeldern des nächsten
  Elements mit `id`, nicht das Element selbst (das gibt es danach nicht mehr) und
  auch kein eigener Schlüssel je Feld — den müsste jeder Feld-Bauer mitschleppen,
  und ein vergessener fiele nicht auf. Ein Test hält fest, dass **alle drei**
  Neuaufbauten (`render`, `renderScans`, `renderSettings`) es tun.
- **Ein Trigger ohne Punkt wird abgelehnt**, statt eine Bedingung auf (0, 0) anzulegen —
  dieselbe Haltung wie „es gibt bewusst keinen Rückfallwert" bei `point_id`. Das gilt
  auch für den *Typwechsel*: **`set_block_type()` legt die Bedingung selbst am Punkt an**
  (`WaitCondition(point_id=step.point_id)`) und ohne Punkt gar nicht; `block_set_type()` lehnt
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
  weil beide über dieselben Befehle schreiben (`block_set_type`, `block_trigger`) — es gibt
  keinen zweiten Zustand, der auseinanderlaufen könnte.

  Der gelöschte Schalter „nur warten (kein Klick)" war der Gegenfall: **einer** statt
  zweier, er setzte `wait_only` (also dasselbe wie die Kachel WARTEN), und er blendete
  sich bei „warten" selbst aus. Wer ihn eingeschaltet hatte, fand nichts mehr, um ihn
  auszuschalten. Genau diese Falltür darf es hier nicht geben — und deshalb bleibt auch
  ein Farb-Trigger sichtbar, der an einem Typ hängt, der ihn gar nicht auswertet.
- **Ein Farb-Warten kann seine eigene Zeitgrenze haben** (`WaitCondition.timeout`,
  in der Datei `wait_timeout`, Feld „Timeout (s)“ unter dem Farb-Trigger).
  Leer = `pixel_wait_timeout` aus der Config, 0 = ohne Grenze — dieselbe
  Bedeutung wie dort, damit „0“ nicht zweierlei heisst. Vorher galt EINE Grenze
  für alle Blöcke, und ein Block, der auf das Ende eines Kampfs wartet, bekam
  dieselbe Zeit wie einer, der auf einen Knopf wartet. Gelesen wird an einer
  Stelle (`effective_timeout()` in `runtime/steps.py`); die Karte nennt eine
  eigene Grenze („max 600 s“), und der ELSE-Hinweis rechnet mit ihr. Nur für
  die VORbedingung: die Nachprüfung hat `verify_timeout` und nimmt keine
  eigene an. Ein unlesbarer Wert in der Datei fällt auf die Config zurück
  statt den Block ohne Grenze zu lassen.
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
  `style`-Attribut und damit *nach* dem `border`-Kurzformat aus `.type-chip`;
  andersherum räumte die Kurzform die Farbe wieder weg.
- **Was ohne ELSE passiert, steht in der Config — also wird sie gelesen, nicht
  behauptet.** Im Inspektor stand „Ohne ELSE läuft der Schritt in seinen Timeout
  und die Sequenz macht weiter", und das war falsch: die Voreinstellung
  `pixel_timeout_action: "skip_cycle"` bricht den **ganzen Zyklus** ab. Genau
  dieser Unterschied entscheidet, ob man ELSE braucht. `_without_else()` liest
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
- **`_move()` ist der eine Weg** für Umsortieren *und* Phasenwechsel. Der
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
  eine **Maske** hat, steht der Name dort, wie bei Slot und Item auch.

  **Das Feld links (`#scan-name`) ist trotzdem wieder da**, und zwar mit
  Absicht: im geführten Arbeitsweg steht rechts die Item-Liste, die Scan-Maske
  ist also nicht zu sehen — ohne das Feld liess sich der offene Scan dort gar
  nicht umbenennen. Hier stand „das Feld links ist ersatzlos weg", während
  `index.html` es enthielt und `tests/smoke/items.py` es verlangte; eine der
  beiden Fassungen war also falsch, und es war diese. Die Klappliste darüber
  **wählt**, das Feld darunter **benennt** — zwei Aufgaben, zwei Bedienelemente.
  Die Überschrift im Detailteil der Maske nennt den Scan nicht noch einmal.
- **Erklärungen stehen im ⓘ, Zustand und nächster Schritt im Text.** Ein
  `hint`-Absatz sagt, was JETZT gilt („62×60 px", „Zeigt ins Leere: …") oder
  was als Nächstes zu tun ist („Noch keine Slots. …"). Alles, was erklärt, WARUM
  etwas so ist, gehört ins ⓘ — es gilt immer, ändert sich nie und steht deshalb
  bei jedem Blick im Weg; `openHelps` merkt sich, welche aufgeklappt sind.
  `toggle()`, `numberField()`, `color_swatch()`, `selection()` und `heading()`
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

  **Und keine Phasenfarbe ist eine Zustandsfarbe.** `--init` war Byte für Byte
  dasselbe wie `--ok` (`#3ED07A`): im Live-Run stand die INIT-Kachel damit
  neben einem grünen ok-Zähler, und Grün hatte drei Bedeutungen (in Ordnung ·
  INIT · erkannter Slot). INIT ist jetzt Pink (`#F472B6`) — die einzige Hue,
  die sonst nirgends im Studio vorkommt; die Phasen sind damit eine kühle
  Dreiergruppe (Pink · Violett · Himmelblau). Ein Test hält die drei
  Phasenfarben gegen die drei Zustandsfarben.
- **Die Schrift auf der Typfarbe folgt der Typfarbe** (`ink_color()` in
  `model.py`, Feld `ink` an Karte, Typ-Kachel und Laufstatus). Die Kopfzeile
  einer Karte trägt die Typfarbe über die volle Breite, und die Schrift darauf
  war fest dunkel — auf Boss-Watcher (140, 40, 45) sind das 2,2:1, auf
  Boss-Scan 3,9, auf Klick/Warten/Screenshot rund 4,2. Die Schwelle liegt bei
  einer relativen Leuchtdichte von 0,2: darunter helle Schrift, darüber dunkle;
  Grau und Blau sind dafür ein paar Stufen dunkler geworden, weil beide
  Schriftfarben auf dem alten Wert bei 4,4 lagen. Ein Test rechnet den Kontrast
  für jede der neun Typfarben nach — Mindestmass 4,5:1. Der Typ sitzt dabei als
  umrandete **Marke** in der Kopfzeile, nicht als Wort im Fluss.
- **Jede Kartenzeile trägt ein Etikett** (`_lines()` liefert `{label, text}`:
  STELLE, WARTE, TASTE, SCAN, RAD, BEREICH, FARBE, ELSE), und der Kartenkörper
  ist ein zweispaltiges Raster, damit die Etiketten bündig stehen. Bei fünfzig
  Karten untereinander findet das Auge „WARTE" schneller als „1.5s" — und ohne
  Etikett musste man das Vorzeichen als Wartezeit erkennen (das `+` ist
  deshalb weg).
- **Symbole sind Inline-SVG** (`ICONS` / `icon()` in `app.js`), keine
  Unicode-Glyphen: „▶", „●", „↶", „↻" kommen aus der Systemschrift und stehen
  je nach Fenster verschieden gross und hoch — das ⓘ war aus demselben Grund
  längst ein SVG. Sie erben `currentColor`; `.btn` ist dafür `inline-flex`.
  Wer ein neues braucht, trägt es in `ICONS` ein, nicht als Zeichen in den
  Text.
- **Die Reiter stehen in drei Gruppen** (Bauen · Beobachten · Verwalten, durch
  `.tab-gap` getrennt), der Live-Run-Reiter trägt die Lampe des laufenden Laufs
  (`#tab-run-lamp`). Die **Sequenz ist EIN Bedienelement** (`.seq-chip`:
  Kürzel, Auswahl, Ungespeichert-Punkt, „Neu"); einen Laden-Knopf gibt es
  nicht mehr — die Auswahl lädt, mit derselben Rückfrage wie vorher, und
  `closeQuestion()` stellt sie beim Abbrechen auf das zurück, was wirklich
  offen ist. Starten ist grün umrandet (`.btn.launch`, **nicht** `.run` — das
  ist die Live-Run-Ansicht, und der Knopf erbte deren Polster). Der Kopf muss
  bei 1300 px in eine Zeile passen; umbrechen darf er, nur nicht bei jeder
  gewöhnlichen Fensterbreite.
- **Der Tastaturfokus ist sichtbar — überall** (`:focus-visible`-Ring in
  Akzentfarbe auf Knöpfen, Kacheln, Feldern). Eingabefelder wechselten nur die
  Rahmenfarbe, Knöpfe gar nichts: wer mit TAB durch den Inspektor ging, sah
  nicht, wo er steht.
- **Die leere Bühne trägt ihre Aktion selbst** (`emptyStageArt()` plus ein
  Knopf, der denselben Befehl schickt wie Schritt 1 des Assistenten). Vorher
  nannte der Text einen Knopf, der 400 px weiter links lag.
- **Der Editor hat ein Rückgängig** (`_edit_commit()` / `undo()` / `redo()` in
  `bridge_editing.py`, STRG+Z / STRG+Y, „Zurück"/„Wieder" im Kopf). Der
  Scans-Reiter hatte es mit 30 Abzügen, der Editor nichts: Entf auf einer
  Auswahl war endgültig, der einzige Ausweg „Verwerfen & neu laden". Dieselbe
  Bauart wie `_remember()` — ein **vollständiger Abzug** von Board, Punkten
  und Auswahl, kein Rückwärts-Schritt —, aber an einer Stelle: `_changed()`
  legt ihn ab, kein Kommando muss daran denken. Drei Regeln:
  - **`_edit_current` ist der Stand nach dem letzten Abzug**, und
    `snapshot()` merkt sich darin die Auswahl: Auswählen legt keinen Abzug
    ab, und nach dem Zurück soll man auf dem stehen, was man gerade gelöscht
    hatte. Ein Abzug hält Indizes, keine Lane-Objekte.
  - **Speichern, Laden, Anlegen, Import und Kalibrierung leeren den Stapel**
    (`_edit_reset()` in `_state_remember()`, `_after_import()`,
    `_after_calibration()`): ein Zurück über einen Ladevorgang hinweg
    beschriebe einen Stand, den es nicht mehr gibt, und was auf Platte
    geschrieben ist, holt kein STRG+Z zurück.
  - **`offer=True` hängt den Rückgängig-Knopf an die Meldung** (`#status-action`)
    — nur bei löschen, Typwechsel und verschieben, nicht bei jedem Tippfeld;
    `group="move"` fasst eine gehaltene Pfeiltaste zu EINEM Abzug zusammen
    (`EDIT_GROUP_SECONDS`), dieselbe Regel wie `counts` bei den Slots. Die
    Punkt-Werkzeuge (`tool_point_*`, `tool_points_prune`) rufen `_edit_commit()`
    selbst — sie gehen nicht über `_changed()`.
- **Befunde sind Sprungmarken.** `Finding.target` (`diagnostics.py`),
  `targets` im Bericht (`_report_targets()`: Timeout-Name → Block der offenen
  Sequenz, über `step.name` oder `Phase[n]`) und die Warnmarke auf der Karte
  tragen ein Ziel; `goTo(target)` in `app.js` ist die EINE Funktion, die alle
  kennt: `{"view":"scans","kind","name"}`, `{"view":"editor","phase","row"}`
  (Lane-Index wie im Board, 0 = INIT), `{"view":"editor","point"}`. Ein Ziel in
  einer anderen Sequenz lädt sie erst — mit derselben Rückfrage. Ein Befund
  ohne Ziel (unlesbare Datei) bekommt keinen Knopf statt eines, der nirgendwohin
  führt. `selection()` schreibt seinen `key` als `data-key` ans Feld, damit
  die Warnmarke „Name fehlt" den Fokus in die Scan-Auswahl stellen kann.
- **Die Übersicht kennt den letzten Lauf** (`_last_run()`: neueste
  `logs/<stamp>_<sanitize(name)>.csv`, gerechnet mit `evaluate()` aus dem
  Werkzeug, gemerkt am Dateistand), **kann duplizieren**
  (`sequence_duplicate()`: Ordner kopieren samt Scans und Vorlagen, Name per
  `unique_name()` — die Punkte sind sequenzlokal, es gibt nichts umzuhängen)
  und hat Filter und Sortierung (`seqSorted()`, Oberflächenzustand). Das
  Datum steht als Spanne („vor 2 Stunden", `sinceText()`) mit dem Stempel im
  Tooltip — vorher stand es HINTER dem Pfad, also hinter dem „…". Und „1
  Zyklen" gibt es nicht mehr: der Plural sass im Code.
- **Die Punkte-Liste zeigt die Verwendung** (`usages` an jedem Punkt,
  `points` an jedem Block). Ein Klick auf die Zeile markiert im Board jeden
  Block, der den Punkt benutzt (`pointHighlight`, Ring in Punktfarbe — keine
  Auswahl), ein gewählter Block hebt seine Punkte hervor (`in-use`);
  ungenutzte sind blass, „ungenutzt" ist ein Filterwort, und
  `tool_points_prune()` löscht sie in einem Griff (mit Abzug). Die Zieh-Geste
  steht als Zeile unter der Liste — `cursor: grab` liest niemand.

  **Ein ungenutzter Punkt lässt sich direkt in der Liste löschen** (× am
  Zeilenende, `point_delete`, `call()`-Kanal mit Rückgängig). Vorher ging
  das nur im Werkzeuge-Reiter, und der zog die Editor-Liste nicht nach: der
  Punkt stand weiter da, der Ungespeichert-Punkt fehlte, und weil der Reiter
  keinen Speichern-Knopf hat, sah das Löschen wirkungslos aus — beim
  Schliessen landete es nur in der Notsicherung. Drei Regeln: **eine
  Löschregel** für beide Wege (`_point_remove()`: nur unbenutzte, Referenzen
  nie still brechen), **das × gibt es nur, wo es wirkt** (verwendete Zeilen
  halten mit `.point-delete-slot` nur den Platz frei, damit Zähler und
  Koordinaten auf einer Kante bleiben), und **Punkt-Werkzeuge ziehen die
  Momentaufnahme nach** (`TOOL_POINT_COMMANDS` in `callTool`, ein Test hält
  die Liste gegen die `tool_point*`-Methoden der Brücke).

  **Die Scans zählen mit, auch wenn ihr Reiter nie offen war.** Das Studio
  lädt sie verzögert (`_scan_load()`, wegen des gemerkten Bildes), und bis
  dahin zählte die Liste nur Blöcke: ein Punkt, den nur Bestätigungsklicks von
  Items benutzen, stand als „0× ungenutzt“ mit Lösch-× da — an einer echten
  Sequenz drei Items auf einem Punkt. `_scan_configs_load()` holt deshalb nur
  die Konfigurationen (1 ms statt 147 ms mit Bild), und `_all_items()` zählt
  ALLE Item-Scans, nicht nur den offenen. Wer `_scan_loaded` zurücksetzt,
  nimmt `_scan_unload()` — sonst bleiben die früh geladenen Konfigurationen
  beim Neuladen stehen.
- **Jede Phase hat ein Menü rechts** (`renderPhaseInspector()`): ein Klick auf
  den Phasenkopf — auch START und ABSCHLUSS — wählt sie, und statt „KEIN
  BLOCK“ stehen dort Art, Reihenfolge und oben „duplizieren“/„löschen“
  (dieselben Knöpfe wie beim Block, STRG+D und Entf ebenso). Die Art stand
  kurz als Auswahl IM Kopf und nahm dem Namen den Platz („Sammeln Ev…“); was
  man selten tut, gehört in den Inspektor, nicht in jede Spalte. Nach einem
  Phasen-Befehl ändern sich die Indizes — die Brücke sagt deshalb, welche
  Phase gewählt bleibt (`phase_focus`, einmal ausgeliefert wie `question`).

  **Duplizieren** (`phase_duplicate`) legt die Kopie hinter das Original, mit
  eigenen Punkten nach derselben Regel wie beim Block-Duplikat (EINE
  Abbildung für die ganze Phase), Name „… (Kopie)“ — ein Zähler machte aus
  „Loop 1“ ein „Loop 1 2“. Eine Kopie von START oder ABSCHLUSS ist eine
  Loop-Phase. **Löschen** geht auch bei START und ABSCHLUSS und heisst dort
  leeren (mit Rückgängig): im Modell gibt es beide immer, „keine Startphase“
  IST eine leere, und die Ansicht blendet sie aus (`openSpecialPhases`). Hier
  stand „INIT und END lassen sich nicht löschen“ — eine über „+ Startphase“
  eingeblendete leere START-Phase liess sich damit nicht mehr loswerden.
  **Verschieben** (`phase_move`, `move_loop_lane()`) geht nur unter
  den Loop-Phasen: START ist der Anfang, ABSCHLUSS das Ende. Gesucht wird eine
  Phase dabei über ihre Identität (`position()`), nicht über `lanes.index()`:
  nach einem Duplikat gibt es gleich aussehende.
- **Jede Phase kann ihre Art wechseln — START ↔ Loop-Phase ↔ ABSCHLUSS, hin
  und zurück** (`phase_convert`, Kacheln „Art“ im Phasen-Menü,
  `convert_lane()` in `model.py`). Von Hand ging das nicht: eine neue
  Loop-Phase entsteht immer hinten, und Phasen liessen sich nicht umsortieren.
  Vier Regeln:
  - **→ Loop** legt eine neue Phase an **derselben Stelle** im Ablauf an: aus
    START die erste, aus ABSCHLUSS die letzte; die Sonderphase bleibt leer für
    einen neuen Aufbau.
  - **→ START / ABSCHLUSS nur, wenn das Ziel leer ist.** Beide gibt es genau
    einmal, und zwei Blockfolgen zusammenzulegen hiesse zu raten, welche zuerst
    läuft. In der Auswahl steht ein belegtes Ziel als „(belegt)“ gesperrt da.
  - **Was eine Sonderphase nicht kennt, wird gesagt**: Läufe je Zyklus und
    Startzeit einer Loop-Phase fallen weg, und die Meldung nennt sie (`warn`).
  - **Umbenannt wird nichts.** `delete_loop_lane()` zählt Namen wie „Loop 2“
    neu durch; eine Umstellung ist kein Löschen, und die übrigen Phasen
    behalten ihre Namen.

  Namen und Laufzeitpunkt der drei Arten stehen in `PHASE_KIND_NAMES` /
  `PHASE_KIND_WHEN` und kommen über die Momentaufnahme (`phase_kinds`) — die
  Seite erfindet sie nicht. Die Knopfzeile im Kopf ist in allen Phasen
  dieselbe: „Zeiten skalieren …“ gibt es auch bei START und ABSCHLUSS.
- **Ein leeres Board sagt, wie man anfängt** (`startCard()`: Aufnehmen oder
  von Hand bauen, dazu der Import), und die Tastenkürzel stehen in EINER Tafel
  (`shortcutTable()`, Taste `?` und `#btn-help`). Die Scan-Modi nehmen ihre
  Buchstaben aus `SCAN_MODES`; ein Test hält die Tafel gegen `keyboard()`.
- **Der Status steht unten, nicht im Kopf.** Oben nahm er den Platz weg, den die
  Bedienelemente brauchen; unten hat er die volle Breite und liegt da, wo sonst
  nichts passiert. **Die Art steht als Kachel VOR dem Text** (`#status-kind`,
  `STATUS_KIND` in `app.js`: Symbol + Wort für ok/warn/err, nichts für info),
  der Text selbst in Grundfarbe und mit zwei Zeilen Platz statt „…" — die eine
  Meldung, die man lesen MUSS, ist die lange. `#status` bleibt reiner Text,
  damit `f.status()` in den Rauchtests weiter nur die Meldung liest. Dass er dorthin gehört, merkt man an der Gegenprobe: eine
  lange Meldung im Kopf war immer abgeschnitten.
- **Eine Meldung gehört dem Reiter, in dem sie entstand.** Die Leiste liegt
  unter allen Reitern, und dort blieb stehen, was zuletzt irgendwo gemeldet
  wurde: „15 von 15 Slot(s) erkannt" stand unter Live-Run, Bericht und
  Werkzeuge und las sich wie eine Aussage über DIESEN Reiter. Zwei Regeln:
  - **Reine Navigation räumt auf** (`setView(…, navigated)`: ein Reiter, „Zum
    Live-Run", ein Werkzeug öffnen, eine Sprungmarke). Ein Wechsel als FOLGE
    einer Aktion (Starten springt in den Live-Run, „Öffnen" in der Übersicht
    lädt und springt in den Editor, eine fertige Aufnahme ebenso) nimmt die
    Meldung mit — sie ist das Ergebnis genau dieses Wechsels. Wer einen neuen
    `setView()`-Aufruf schreibt, entscheidet, welcher der beiden Fälle es ist.
    Ein erster Anlauf entschied nach der Uhr („jünger als 1,5 s
    geht mit"), und wer schnell durch die Reiter klickte, nahm die Meldung
    trotzdem mit. Scans und Teilen zeichnen ihre eigene beim Öffnen neu, der
    Editor bekommt seine in `setView()` zurück.
  - **Die Seite zeichnet nur NEUE Editor-Meldungen** (`S.status.id`, gezählt in
    `_report()`). Die Momentaufnahme trägt die letzte Meldung bei jedem Befehl
    wieder mit; sie jedes Mal zu zeichnen hiess, dass ein Klick auf eine Karte
    die weggeräumte Meldung zurückholt. Der Rückgängig-Knopf an der Meldung
    steht nur neben einer Editor-Meldung im Editor (`statusFromEditor`).
- **Über dem Board steht die Phasenleiste** (`renderPhaseNav()`): jede
  sichtbare Phase mit Blockzahl, ein Klick scrollt hin (`scrollToPhase()`),
  und was außer Sicht liegt, ist gestrichelt (`.off`, gerechnet in
  `updateBoardEdges()` bei Scrollen und Fenstergröße). Bei 1500 px Fensterbreite
  waren drei von fünf Phasen zu sehen, bei 1100 px anderthalb — der Rest lag
  rechts, ohne Bildlaufleiste, die man bemerkt. Dazu dunkle Kanten, solange
  links bzw. rechts noch Phasen liegen, mit einem runden Knopf darin; die Kante
  selbst nimmt **keine** Klicks an, sie liegt über den Karten. Ganz links in
  der Leiste klappt die Seitenleiste weg (`.left-closed`, gemerkt in
  `localStorage` — mit `try`, ohne Speicher bleibt sie einfach offen).
- **Ohne gewählten Block zeigt der Inspektor einen Überblick**
  (`renderOverview()`): die Blocktypen der Sequenz mit Anzahl (zugleich die
  Legende), was Aufmerksamkeit braucht (Block mit Warnung, ELSE das nie greift,
  ungenutzte Punkte — jeder Eintrag springt hin) und die vier Gesten. Vorher
  stand dort ein Satz über 700 px leerer Fläche, daneben zwei gesperrte
  Knöpfe; die sind im Überblick jetzt ausgeblendet.
- **Live-Run im Leerlauf: ein Start-Knopf, ein Satz, eine Vorschau**
  (`runPreview()`). Starten trug dort Amber, oben im Kopf Grün — zwei Gestalten
  für einen Befehl; es ist jetzt überall `launch`. Neben dem Knopf stand fast
  derselbe Satz ein zweites Mal. Und wo im Lauf die Phasenleiste steht, stehen
  im Leerlauf dieselben Kacheln als Vorschau der offenen Sequenz.
- **Ein Leerzustand bietet den Handgriff an, nicht den Config-Schlüssel**
  (`emptyState()`). „session_log_enabled ist aus" ist richtig und ein Satz, mit
  dem man suchen geht; der Bericht hat dafür „Session-Log einschalten". Teilen
  sagte „erst speichern" in einem Reiter ohne Speichern-Knopf — die Warnung
  trägt ihn jetzt selbst (`saveEverythingForShare()`).
- **Ein Werkzeug hat einen Namen, und er kommt aus `WZ_TOOLS`** (`wzHeader(key,
  text)`). Links stand „Bestand prüfen", im Kopf „Setup prüfen", und
  „Kalibrieren" hiess drüben „Koordinaten kalibrieren". Der Konsolenbefehl
  steht im Tooltip und nur, wo es ihn gibt (check, fix, reclick) — als Marke
  drückte er jeden Titel auf zwei Zeilen, und „rec", „points", „color" kannte
  die Konsole gar nicht.
- **Eine gerechnete Zahl sieht nicht aus wie ein Eingabefeld.** „Blöcke" hatte
  dieselbe durchgezogene Kachel wie „Zyklen" daneben, und ein Klick darauf tat
  nichts. Gleiche Höhe bleibt, aber gestrichelt und ohne Feldgrund —
  gestrichelt heisst im Studio „steht da, ist aber nicht anzufassen".
- **Im Scan-Bild steht ein Name je Slot, und zwar IN seinem Rechteck.**
  Slot-Name darüber und Item darunter ergab in einem Raster „Item 1" (unter
  Reihe 1) direkt auf „Slot 6" (über Reihe 2). Das erkannte Item steht unten
  im Slot, gekürzt auf dessen Breite; der Slot-Name nur beim gewählten und beim
  Slot unter dem Zeiger (`scanHover`, neu gezeichnet nur beim Wechsel).
- **Zustandsklassen bekommen ein Präfix** (`kind-ok`, `kind-warn`, `kind-info`).
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
