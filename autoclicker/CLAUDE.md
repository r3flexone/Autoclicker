# autoclicker — Bilderkennung, Katalog, Session-Log, Import/Export

Details zur `CLAUDE.md` im Wurzelordner — dort stehen Befehle, Architektur
und die Regeln, die überall gelten. Claude Code lädt diese Datei, sobald eine
Datei aus `autoclicker/` gelesen wird. Was hier steht, gilt genauso; neue
Begründungen zu diesem Bereich gehören hierher, nicht in die Wurzel.

## Der Item-Katalog (echte Namen und Kategorien aus der Spiel-API)

**Eine Kategorie heisst „diese Items konkurrieren, nimm nur das beste"**
(`_filter_scan_results`, Modus `all`: `cat = item.category or item.name`, pro
Kategorie gewinnt das kleinste `priority`). Sie von Hand zu tippen hat den
Fehler, den man nicht sehen kann — an einem echten Bestand standen 55 von 56
Items ohne Kategorie da und das eine mit trug `"Wafen"`.

`tools/catalog.py` holt die Namen deshalb von dort, wo sie herkommen:
`query.idleclans.com/api/Configuration/game-data`, dieselbe Quelle, aus der auch
die Wiki gespeist wird — **Scraping braucht es dafür nicht.** Heraus kommen 1006
Items mit Kategorie und Grundwert plus rund 50 Gegnernamen.

**Die Verbindung ist eine Datei, kein Import** — genau wie bei `marktwert.json`:
das Werkzeug weiss nichts vom Autoclicker, der Autoclicker nichts vom Werkzeug.
Gelesen wird in `autoclicker/catalog.py` (Cache am Dateistand, kaputte Einträge
fliegen einzeln raus). Es liegt **nicht** unter `runtime/`, weil vor allem
Editoren es brauchen und `runtime/__init__` den Worker samt `imaging` und
`winapi` nachzöge — dieselbe Überlegung wie bei `mailbox.py`.

**Zwei Schalter, und sie beantworten verschiedene Fragen.**
`config.scan_catalog_file` sagt, **wo** die Datei liegt (eine je Spiel, also
programmweit); `ItemScanConfig.use_catalog` sagt, **ob** dieser Scan sie
benutzt. Der zweite gehört zum Scan und nicht in die Config — aus demselben
Grund wie `reverse`: wer zwei Spiele betreibt, hat einen Katalog, der nur für
eines von beiden gilt, und global gesetzt ordnete er das andere still falsch
ein. Im Studio steht er in den Scan-Einstellungen direkt neben „Slots
rückwärts", der Pfad im Einstellungen-Reiter — **samt dem Knopf, der die
Datei holt** (`catalog_fetch`, angemeldet über `M.action` in
`config_meta.py`). Bis dahin konnte nur `python tools/catalog.py` sie
anlegen: ausgerechnet die Datei, ohne die das LLM frei rät und die
Kategorie leer bleibt, liess sich im Fenster nicht beschaffen. Gerechnet
wird weiter im Werkzeug — **die Brücke ruft `tools/catalog.py`, nie
umgekehrt**, dieselbe Richtung wie beim Bericht-Reiter. Ein gesetzter Pfad
wird dabei aktualisiert und nicht überschrieben, und weder ein Netzfehler
noch eine leere Antwort fassen die vorhandene Datei an.

**Die API schreibt Mongo-Shell-JSON, und ein Spiel-Update darf das Werkzeug
nicht stoppen.** `Configuration/game-data` kommt mit `ObjectId("…")`,
`NumberLong(0)` und womöglich morgen etwas Drittem. Der Bereiniger war eine
Regex, die genau `ObjectId` kannte, dreimal ausgeschrieben (`tools/catalog.py`,
`market_analysis/analysis.py`, `market_analysis/apicheck.py`) — als die
Achievements `NumberLong` mitbrachten, starben alle drei an einem Feld, das
keiner von ihnen liest, und der Katalog-Knopf im Studio meldete „Nicht
erreichbar". Jetzt ist es ein kleiner Scanner (`clean_extended_json` in
`tools/catalog.py`, Zwilling `market_analysis/extended_json.py` — bewusst
kopiert, die beiden Teile importieren einander nicht): Bekanntes wird
übersetzt, ein unbekanntes `Name(…)` als sein Wert übernommen und **gemeldet**
— das Werkzeug auf stderr, der Studio-Knopf in der Statuszeile (`kind: warn`).
JSON-Strings werden dabei übersprungen; ein `ObjectId(` in einer
Item-Beschreibung bleibt Text. Auf beiden Seiten stehen dieselben Testfälle,
damit die Kopien nicht auseinanderlaufen.

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
  besitzt. `ranks()` vergibt sie dicht innerhalb der bearbeiteten Menge.
- **Ein Timeout beendet die Boss-Erkennung nicht mehr** (`is_timeout()`, die
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
  da wer". Im Scans-Reiter kam dazu, dass `llm_check()` mit einem rohen
  `urlopen(CONFIG.llm_endpoint)` prüfte, und der ist im Normalfall `None`: die
  Lampe meldete einen `NoneType`-Fehler bei laufendem Server.
- **`llm_reasoning` und `llm_max_tokens` gelten auch für die Benennung.** Sie
  wurden nur im Boss-Scan gelesen; wer sie einschaltete, weil die Benennung
  besser werden soll, änderte nichts. Mit Reasoning wird die Antwort-Länge
  dabei **nicht** auf 32 gekürzt (`_name_tokens()`) — sonst sind die Tokens
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
  durch und standen als „ohne Vorschlag" da. `suggest_item_name_with_reason()` gibt
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
  Item** (`scan_category_rename`, Feld im `scan-category-header`). Sie ist
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
- **Ein Zähler am Namen darf die Kategorie nicht kosten.** `_catalog_name()`
  probiert erst den vollen Namen und dann den ohne Zähler (`without_counter()` in
  `utils/parsing.py`, die Umkehrung zu `unique_name()`). Die Reihenfolge
  ist die Regel: was im Katalog steht, gewinnt — „Slot 1" bleibt „Slot 1".
- **Ein Durchgang, den die Seite treibt — sonst gibt es kein Abbrechen.**
  Sechsundfünfzig Vorlagen sind bei drei Sekunden je Modell-Antwort knapp drei
  Minuten; als EIN Brücken-Aufruf kann das niemand stoppen. Ein Abbruch-Flag
  bräuchte einen zweiten Aufruf **neben** dem laufenden: in pywebview kommt der
  durch, im Rauchtest-Prüfstand nicht (dort hält der Python-Callback den
  Dispatcher) — und ein Abbruch, der nur im Fenster funktioniert, ist keiner.
  Deshalb `scan_autoname_start` → `scan_autoname_step` (je Item) →
  `scan_autoname_end`: der Zustand liegt in der Brücke, die Seite fragt nur
  nach dem nächsten Schritt. Das bringt Abbruch, sichtbaren Fortschritt und
  einen Durchgang, den die Vertragssuite Schritt für Schritt durchspielen kann.
  Drei Regeln dazu: die Config wird beim Start **eingefroren** (sonst liest
  `load_config()` je Item die Datei und schreibt eine Konsolenzeile), der
  Rückgängig-Stand entsteht **einmal und erst beim ersten Treffer**, und ein
  Abbruch **behält, was bis dahin benannt wurde** — es wegzuwerfen hiesse,
  zwanzig Modell-Antworten zu verbrennen, weil man die einundzwanzigste nicht
  mehr abwarten wollte.
- **Am Katalog-Feld steht, was dahinter liegt** (`_catalog_state()`,
  Momentaufnahme `states`): Umfang und Zeitpunkt der Datei, in **Ortszeit**,
  und „Datei fehlt“, wenn der Pfad ins Leere zeigt. Der Pfad allein beantwortet
  die Frage nicht, die man an eine geholte Liste hat — ohne Antwort holt man
  sie entweder nie wieder oder bei jedem Zweifel neu.
- **Der vorgeschlagene Name ist ein NAME, kein Dateiname.** Beide
  `autoname`-Wege (Studio und Konsole) drückten ihn durch
  `sanitize_filename()` — die macht Kleinbuchstaben und Unterstriche, aus
  „Godlike Bow" also `godlike_bow`. `Catalog.match()` vergleicht aber
  `casefold()` und keine Unterstriche: der Name kam wörtlich aus dem Katalog
  und fand sich darin trotzdem nicht wieder, **Kategorie und Priorität blieben
  also immer aus** — ausgerechnet der halbe Zweck der geschlossenen Auswahl.
  Dafür gibt es `clean_item_name()` (`utils/parsing.py`); wo aus dem Namen
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

Beim Erweitern: `_catalog_check()` unterscheidet **drei** Gründe (kein Scan
offen / Schalter aus / keine Datei). Sie zusammenzufassen wäre der Fall, in dem
man die Datei sucht, obwohl der Schalter fehlt. Und `_remember()` läuft erst, wenn
wirklich etwas geändert wird (`_catalog_plan` vor `_catalog_apply`) — ein
zweiter Klick auf denselben Knopf darf keinen Rückgängig-Stand ablegen, sonst
tut STRG+Z einmal scheinbar nichts.

## Template-Vergleich mit Lernmaske (`imaging.py`)

**Ein Template vergleicht nur das Item, nicht den Slot.** Gemessen an einem
echten Bestand: von 62×60 Pixeln eines Slots sind **10–40 % das Item**, der Rest
ist die immer gleiche Slot-Fläche. Ein Vergleich über das ganze Rechteck stimmt
damit hauptsächlich darüber ab, dass beide denselben Hintergrund haben — und nur
zu einem Zehntel darüber, ob es dasselbe Item ist. `with_background_mask()`
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
  immer gleich gross (`_template_at_size`), also ist es genau eine Korrelation
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

`_size_hint()` in `imaging.py` schreibt den Text dazu. Drei Regeln, die er
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

Die Sperre bleibt: gemeldet wird **einmal je Grössenpaarung** (`_reported_sizes`),
sonst stehen zwei Dutzend gleichlautende Zeilen da und die Meldung ist so gut wie
keine.

Eine Grenze, die man kennen muss: **eine völlig gleichförmige Fläche hat keine
Varianz und damit keine Korrelation.** Ein Item, dessen sichtbarer Teil eine
einzige Farbe ist, kommt maskiert auf 0 — vorher lieferte der Hintergrund die
Varianz und es „funktionierte". Echte Symbole haben Struktur; für den Rest gibt
es die Marker-Farben.

## Session-Log (`session_log.py`)

- `autoclicker/session_log.py` — CSV-Logger, thread-safe. **Ausgewertet wird er mit
  `tools/log_report.py`** (ohne Windows, ohne Abhängigkeiten lauffähig) — auf der
  Kommandozeile und im Reiter „Bericht" des Studios, über **dieselbe** Funktion
  (`evaluate()` rechnet und gibt Daten zurück, `report()` druckt sie). Geloggt wird
  nicht nur, *was geklickt* wurde, sondern auch, *was gesehen* wurde: `timeout` (welcher
  Schritt hängt — das diagnostisch wertvollste Ereignis), `item_found`, `detected`,
  `verify_ok`/`verify_miss`. Ohne diese Ereignisse konnte der Bericht die eine Frage
  nicht beantworten, für die man ihn aufmacht. Dazu die Wartezeiten, **getrennt
  nach dem, der sie bestimmt**: `wait` (am Block eingestellt, aus
  `wait_with_pause_skip`), `color_wait` (bis der Farb-Trigger aufging, mit
  `result=ok|timeout|abort`) und `pause` (CTRL+ALT+H) — Sekunden jeweils als
  `s=` in `extra`, und die Pause ist aus den beiden anderen herausgerechnet
  (`net_seconds`), sonst stünde eine halbe Stunde Pause als „auf Farbe" da. Ein
  Log ohne diese Zeilen zählt im Bericht nicht mit, statt seine ganze Laufzeit
  als „Rest" auszuweisen. Wer eine neue Ereignisart einführt,
  trägt sie in `log_report.py` ein — der Bericht meldet sonst „nicht ausgewertete
  Ereignisarten" und weist selbst darauf hin.

## Import und Export (`import_export.py`)

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
  (`_safe_bundle_path` + eine `resolve()`-Gegenprobe in
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
