# persistence — Dateiformat und Referenzen

Details zur `CLAUDE.md` im Wurzelordner — dort stehen Befehle, Architektur
und die Regeln, die überall gelten. Claude Code lädt diese Datei, sobald eine
Datei aus `autoclicker/persistence/` gelesen wird. Was hier steht, gilt genauso; neue
Begründungen zu diesem Bereich gehören hierher, nicht in die Wurzel.

## Referenzen statt Kopien
Überall dort, wo früher eine Kopie lag und deshalb still veraltete, gilt jetzt dasselbe
Muster: **der Eintrag der Sequenz ist die Wahrheit, aufgelöst beim Laden und vor jedem
Sequenzlauf.** „Punkte" heisst dabei das Feld `points` in `sequences/<name>/sequence.json`;
die IDs gelten nur innerhalb dieser Sequenz.

| wer verweist | worauf | Feld in der Datei | auflösen |
|---|---|---|---|
| `SequenceStep` | Punkte der Sequenz | `point_id` | `resolve()` / `resolve_point_references()` |
| `WaitCondition` | Punkte der Sequenz | `wait_point_id` | dito |
| `ElseConfig` | Punkte der Sequenz | `else_point_id` | dito |
| `SequenceStep.verify_condition` | Punkte der Sequenz | `verify_point_id` | dito |
| `ItemProfile` | Punkte der Sequenz | `confirm_point_id` | `resolve_click_references()` |
| `BossProfile` | Punkte der Sequenz | `action_point_id` | dito |
| `IconScanConfig` | Punkte der Sequenz | `action_point_id` | dito |
| `ItemScanConfig` | eigene Slots und Items | `slots`, `items` (vollständige Objekte) | direkt beim Laden |

Beim Item-Scan sind `config.slots`/`config.items` der **eigene Bestand des Scans**.
Beide Listen werden vollständig gespeichert; `slot_names`/`item_names` sind
abgeleitete Ansichten und keine Referenzen auf einen globalen Bestand.

**Eine Koordinate steht im Punkt der Sequenz, sonst nirgends.** Das gilt ausnahmslos für alle
drei Stellen eines Schritts: den Klick, den Prüf-Pixel und den Else-Klick. `step.x/y`,
`step.name`, `step.recorded_color`, `wait_condition.pixel/color` und `else_config.x/y/name`
sind **abgeleitete Arbeitswerte** — im Speicher gefüllt, in der Datei nicht vorhanden.
Dasselbe Muster wie `ItemScanConfig.slots`, nur konsequenter.

**Auch der Loader liest keine Koordinate am Schritt.** Ein `x`/`y`, `wait_pixel`/
`wait_color`, `verify_pixel`/`verify_color`, `else_x`/`else_y`/`else_name` oder
`recorded_color` in einer Datei ist ein unbekannter Schlüssel: eine Bedingung ohne
`wait_point_id`/`verify_point_id` gibt es nicht (der Loader liefert `None`), ein
Else-Klick ohne `else_point_id` bringt keine Stelle mit. Bis zum 30.10.2026 las er sie
noch als Ersatz für einen Punkt, der Serializer schrieb sie für Schritte ohne Punkt, die
Kalibrierung rechnete sie um (`_unlinked_sequence_clicks`, die `point_id is None`-Zweige
in `_remap_sequence_obj` und `_remap_sequence_data`) und `link` im Sequenz-Editor knüpfte
sie nachträglich an einen Punkt. Der Bestand des Nutzers — drei Sequenzen, 161 Schritte,
alle Schema 4 — trug keine einzige: Wege, die niemand mehr geht, machen nur noch die
Regel oben unwahr. Dass ein Schritt ohne Punkt seinen `name` behält, ist keine Ausnahme:
bei Taste, Scans und Screenshot ist er die Beschriftung des Blocks.

Dieselbe Regel gilt ausserhalb der Sequenzen: `ItemProfile.confirm_point`,
`BossProfile.action_x/y` und `IconScanConfig.action_x/y` sind ebenfalls abgeleitet.
`resolve_click_references()` (in `persistence/item_scans.py`) füllt sie und läuft in
`main.py` **nach** dem Laden aller Scans — `load_all_item_scans()` sieht die Boss- und
Icon-Scans an seiner Stelle noch gar nicht, deren Klicks stünden sonst bis zum ersten
Sequenzlauf auf (0, 0).

Für diese drei gibt es **bewusst keine Migration** — und keine Meldung mehr. Die alten
Koordinaten liessen sich zwar in Punkte heben, aber der Weg dorthin — die Punkte-Liste
durch jeden Item-, Boss- und Icon-Loader reichen — kostet mehr, als das Feld einmal neu
zu setzen. Ein altes `confirm_point` oder `action_x/y` ist deshalb ein unbekannter
Schlüssel wie jeder andere: der Loader liest es nicht, der Start-Durchgang schreibt es
nicht zurück. Hier stand `_legacy_reported`, das es einmal pro Fundstelle meldete — beim
Laden. Der Start-Durchgang schaltet die Loader aber stumm und schreibt die Datei danach
ohne das Feld: die Meldung kam nie an, und das Feld war trotzdem weg. Eine Meldung, die
niemand sieht, rechtfertigt den Umweg nicht, und der Bestand des Nutzers trug keines
dieser Felder mehr.

Warum so streng: eine Koordinate an zwei Stellen ist eine Koordinate, die an einer der
beiden falsch sein kann. Wer die Sequenzdatei liest, sah dann etwas anderes als das, was
die App klickt — und bei einer Kalibrierung musste jede Kopie einzeln erwischt werden.
`calibrate_inventory()` rechnet deshalb weder Sequenz-Klickstellen noch den
Bestätigungsklick der Items oder die Klicks von Bossen und Icons um: die Punkte sind schon
umgerechnet, ein zweiter Durchgang hiesse doppelt verschoben — und die abgeleiteten Werte
holt `resolve()` bzw. `resolve_click_references()` ohnehin von dort. Umgerechnet wird, was
keinen Punkt haben kann: Slots, Scan-Regionen, Fenster-Anker, Screenshot-Regionen.

**Vier Stellen pro Schritt, zwei Klassen.** `point_id` (Klick) und
`wait_condition.point_id` (Vorbedingung) *sind* der Schritt — fehlt ihr Punkt, darf er
nicht laufen. `verify_condition.point_id` (Nachprüfung) und `else_config.point_id`
(Ersatzaktion) sind Zusatz — fehlt deren Punkt, läuft der Schritt weiter, nur eben
ungeprüft bzw. mit `else = skip`. Gemeldet wird beides.

**Ein Block ohne Stelle hat keinen Klick-Punkt** (`POSITIONLESS_BLOCKS` in
`models.py`: Item-, Boss-, Icon-Scan, Boss-Watcher, Taste, Screenshot). Ein Scan
klickt, was er findet — seine Punkte hängen an Items, Bossen und Icons, nicht am
Block. `set_block_type()` liess die `point_id` beim Wechsel in einen solchen Typ
stehen („damit der Punkt seine Position behält"), und der Rest landete in der
Datei: an einem echten Item-Scan-Block, entstanden aus einem duplizierten Klick,
stand ein Farbfeld vor dem Scan-Namen, der Punkt galt als „verwendet“, die
Live-Ansicht zeigte vor dem Scan dessen Pixel, und hätte er gefehlt, wäre der
ganze Scan übersprungen worden. Heute: der Typwechsel gibt den Punkt ab
(`drop_position()`, der Name bleibt als eigener des Blocks, STRG+Z holt ihn
zurück), `block_point`/`point_capture`/`point_create` lehnen bei solchen Blöcken
ab, und der Loader nimmt einen Rest aus dem Altbestand ab
(`drop_position_leftovers()`, jede Stelle gemeldet). Nachprüfung und ELSE-Klick
sind eigene Referenzen und bleiben — die darf jeder Typ haben.

**Das ist die eine Ausnahme von „nie beim Laden“** (s. u. bei `resolve()`), und
sie ist es, weil der Rest wirkte statt nur dazustehen. Ein wirkungsloses ELSE
schadet niemandem und bleibt stehen, bis der Nutzer entscheidet; eine
Punkt-Referenz an einem Scan zählte, zeigte und übersprang.

Am selben Ort sass ein zweiter Fehler: die **schon markierte** Typ-Kachel noch
einmal anzuklicken löschte den Scan-Namen (bzw. setzte eine Taste auf „enter“),
weil die Diskriminatoren erst zurückgesetzt und danach „erhalten“ wurden.
`set_block_type()` merkt sie sich jetzt vorher, und `block_set_type()` tut bei
gleichem Typ gar nichts — kein Abzug auf dem Rückgängig-Stapel.

**Es gibt bewusst keinen Rückfallwert.** Zeigt eine `point_id` ins Leere, setzt
`resolve()` `step.unresolved = True`; `step_gate()` überspringt den Schritt und sagt
warum. Ein Schritt, der ersatzweise auf eine veraltete Kopie klickt, ist schlimmer als
einer, der stehenbleibt — und ohne Kopie wäre die Alternative ein Klick auf (0, 0).

Regeln beim Erweitern:
- **Wer im Editor eine Stelle erzeugt, legt einen Punkt an**: `point_for_position(state, x,
  y, color, name)` gibt die ID zurück, nie ein Koordinatenpaar. Die Funktion verwendet
  einen vorhandenen Punkt an derselben Stelle wieder — klickt eine Sequenz zweimal
  denselben Knopf, ist das EIN Punkt, sonst wandert beim Nachjustieren nur die Hälfte mit.

  **„Dieselbe Stelle" ist eine eigene Regel, und sie steht an einer Stelle**:
  `point_at_position()` in `persistence/sequences.py`. Editor und Aufnahme
  (`points_for_events`) stellten dieselbe Frage und verglichen beide die
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

  **Bei der Aufnahme reicht der Radius nicht — dort entscheidet die Fläche.**
  Gemessen an einer echten Einfüge-Aufnahme: 18 Klicks auf drei Knöpfe ergaben
  7 neue Punkte, und die Blöcke für denselben Knopf zeigten auf fünf
  verschiedene. Klicks von Hand auf einen breiten Knopf streuten 55 px. Den
  Radius hochzudrehen wäre falsch gewesen: in derselben Sequenz liegen zwei
  gleichfarbige Ziele 20 px übereinander, und was sie trennt, ist nur der Rand
  dazwischen. Deshalb nimmt der Maus-Hook bei jedem Klick einen Ausschnitt
  (`imaging.capture_surface`, ±64 px, ~12 ms) mit, und `points_for_events()`
  füllt daraus die zusammenhängende Fläche in Klickfarbe
  (`imaging.click_surface`). Ein vorhandener Punkt passt, wenn er im Radius
  **oder** auf dieser Fläche liegt — Farbe immer vorausgesetzt, Radius 0
  schaltet beides ab. Passen mehrere, gewinnt der, den derselbe Durchgang
  schon vergeben hat (`prefer`), dann der nächste; sonst sprang ein Knopf mit
  zwei alten Punkten zwischen beiden hin und her. Editor-Wege
  (`point_for_position`) haben keinen Ausschnitt und bleiben beim Radius.

  **Beim Aufnehmen wird nichts verschoben.** Der erste Klick legt den Punkt an,
  die folgenden finden ihn; er behält seine Position. Ihn auf die Mitte der
  Gruppe nachzuziehen wäre genauer und wäre falsch: ein wiederverwendeter Punkt
  gehört womöglich schon einer anderen Sequenz, und die zöge stillschweigend mit.
  Auf die Mitte rücken darf nur ein ausdrücklicher Aufräum-Durchgang mit Vorschau.

  **Ein erfundener Punktname heisst `P<ID>` — nie nach seiner Sequenz.** Drei
  Wege legen Punkte an, ohne dass jemand einen Namen tippt, und sie standen auf
  drei Schemata: die Aufnahme auf `<Sequenzname> <Ereignis-Index>`, `CTRL+ALT+A`
  auf `P<ID>`, der Rückfall in `point_for_position()` auf `Punkt <ID>`. In einer
  Liste standen damit „P3" und „Punkt 4" untereinander — dieselbe Frage, drei
  Antworten.

  Der Sequenzname war dabei nicht nur uneinheitlich, sondern **falsch**: seit
  eine Sequenz eine Besitzeinheit ist, liegt der Punkt ohnehin in ihrer
  `sequence.json` — der Vorsatz sagt nichts, den man nicht schon weiss, und beim
  Umbenennen der Sequenz wird er unwahr. Richtigstellen hiesse dann, **jeden
  Punkt einzeln** anzufassen (an einer echten Aufnahme: 51 Stück).

  Zwei Regeln dazu: die Nummer ist die **Punkt-ID** und nicht die Stelle im
  Ereignisstrom (sonst hiesse der dritte Punkt einer Aufnahme mit Tastendrücken
  `P7`, während die Liste `#3` daneben schreibt), und ein **übergebener** Name
  gewinnt immer — `P<ID>` ist der Rückfall, nicht die Vorschrift. Die Herkunft
  steht getrennt davon in `source` („Aufnahme", „Sequenz-Studio"); auch dort ist
  der Sequenzname entfallen, aus demselben Grund.
- **Aufgelöst wird beim Laden**, nicht erst vor dem Lauf: `load_sequence_file()` liest die
  Punkte aus dem Feld `points` derselben Datei und füllt die Arbeitswerte selbst. Ein
  zweiter Punkte-Pool, den ein Aufrufer mitbringen müsste, existiert nicht — und die gut
  zwanzig Aufrufer (Hotkey-Handler, Sequenz-Studio, Export, Diagnose, Start-Durchgang)
  hätten ihn auch nicht zur Hand: sie bekämen sonst lauter Nullen.
- **Eine fünfte Stelle** trägt man in `resolve()` ein — und in `_step_to_dict`
  /`_parse_steps`. (`_REF_KEYS` in `import_export.py` war der dritte Ort und ist
  gelöscht: seit Punkt-IDs sequenzlokal sind, rechnet der Import keine IDs mehr
  um, und die Liste hatte nur noch einen Test als Leser. `_STELLEN` in der
  Migration ging mit `_seq_v3_to_v4`.)
- **`resolve()` ändert nie das Modell, nur das Arbeits-Flag `unresolved`.** Es
  setzte beim Laden `verify_condition = None` bzw. `else.action = skip` — und das
  nächste Speichern schrieb die Sequenz ohne Nachprüfung bzw. ohne Else-Klick.
  Stiller Datenverlust, ausgerechnet durch die Regel „nur bei einer Änderung, nie
  beim Laden". Heute tragen `WaitCondition` und `ElseConfig` ein `unresolved`;
  `_with_verification` prüft dann nicht, `execute_else_action` klickt dann nicht
  (wie `skip`) — und die Datei behält beides. Dasselbe gilt für einen Else-Klick, für
  den noch gar kein Punkt gewählt ist (das Studio legt ihn so an, bis man einen
  wählt): er hat kein `unresolved`, aber auch keine Stelle. Beide Klickwege — der
  synchrone und der Async-Pfad des Boss-Watchers — fragen deshalb
  `ElseConfig.has_click_target`; der Async-Pfad fragte bis zum 31.10.2026 nicht
  einmal `unresolved` und klickte einen toten Else-Klick auf (0, 0).

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
Schlüssel gegen die Dataclass (ohne `slot_names`/`item_names` — das sind
Properties über den Objekten).

## Scans als Referenzen; Klick-Schritte mit Punkt

**Der Scan besitzt seine Slots und Items.** `slots`/`items` sind die Wahrheit;
`slot_names`/`item_names` werden daraus abgeleitet. Gleichnamige Items anderer
Scans bleiben unabhängig. `resolve_click_references()` löst die Klick-Punkte
der Scans auf — mehr gibt es an einem Scan nicht mehr aufzulösen. Die
Rest-Helfer aus der Zeit des globalen Bestands (`sync_names()` als No-op,
`update_item_in_scans()` mit festem `(0, 0)`, die Weiterleitung
`resolve_scan_references()`) sind ersatzlos gelöscht.

**Die Konsolen-Ansichten heissen nach dem, was sie sind.** `state.scan_slots`
und `state.scan_items` sind Dicts auf die Slots und Items des Scans
`state.active_item_scan`: `bind_item_scan_context()` bindet sie,
`flush_item_scan_context()` schreibt sie zurück, `save_scan_slots()` und
`save_scan_items()` (`persistence/scan_views.py`) speichern sie. Bis zum
31.10.2026 hiessen sie `global_slots`/`global_items` (und das Modul, das sie
speichert, `globals`) — ein Name aus der Zeit des globalen Bestands, der eine
Liste versprach, die es nicht mehr gibt. Dasselbe galt für die Boss-Bibliothek einer Sequenz
(`global_bosses`, heute `state.boss_library`): sie gilt in jedem Boss-Scan
**dieser** Sequenz, nicht programmweit. Der Config-Schlüssel `boss_learn_global`
bleibt, wie er ist — er steht in gespeicherten Dateien.

Beim Sequenzwechsel werden die geladenen Scan-Dictionaries vollständig ersetzt.
Eine fehlende Boss-Bibliothek bedeutet eine leere Liste. Der Dateiname
`bibliothek.json` ist für die Bibliothek reserviert und darf keinem Boss-Scan
gehören (`boss_scan_name_allowed()`); die Prüfung erfolgt auch beim Speichern.

**Und ein Scan wird ebenfalls per Namen gerufen — an FÜNF Stellen.** Sie stehen
in `rename_references()` (`scan_contract.py`), damit sie nicht wieder
auseinanderlaufen:

| wer verweist | Feld | wo |
|---|---|---|
| `SequenceStep` | `item_scan` | im Schritt |
| `SequenceStep` | `boss_scan` | im Schritt |
| `SequenceStep` | `boss_watcher` | im Schritt (dieselbe Datei wie `boss_scan`) |
| `SequenceStep` | `icon_scan` | im Schritt |
| `BossScanConfig` | `default_scan` | in der **Boss-Scan-Datei** — ein *Item*-Scan-Name |

Gemessen an einem echten Umbenenn-Durchgang zog **eine von sechs** Referenzen
nach (die fünf oben plus die Beschriftung): nur der Item-Scan. Boss, Watcher und
Icon liefen über `_detection_rename()`, und das zog gar nichts nach — es
liess stattdessen die **alte Datei liegen**, mit der Begründung, eine Sequenz auf
dem alten Namen verlöre ihren Scan sonst. Das kurierte das Symptom und machte den
Schaden grösser:

- Der Block zeigte weiter auf den alten Namen und lief gegen die
  liegengebliebene Datei — **jede spätere Änderung am umbenannten Scan wirkte im
  Lauf nicht.**
- `_scan_load()` sieht den Ordner durch, also stand der Scan nach dem nächsten
  Öffnen **zweimal** da (aus `wache` wurden `['drache', 'wache']`). Ein
  Umbenennen, das klont, ist kein Umbenennen.

Zwei Regeln beim Erweitern: **eine sechste Stelle trägt man in `_REF_FIELDS`
ein** (eine Tabelle, nicht drei `if`), und **die Beschriftung
zieht nur mit, wenn sie abgeleitet ist** — `step.name == f"Boss:{alt}"` wird
nachgezogen, ein selbst getippter Blockname nicht. Er gehört dem Nutzer, und ihn
stillschweigend umzuschreiben wäre schlimmer als eine veraltete Beschriftung.

**`default_scan` steht zusätzlich in der Diagnose.** Sie prüft tote Scan-Verweise
über die vier Felder *im Schritt* (`_check_sequences`) — die fünfte steht in
einer Scan-Datei und fiel deshalb durch, obwohl `runtime/steps.py` sie bei „kein
Boss erkannt" wirklich ausführt (`execute_item_scan(state, config.default_scan)`).
Zeigt sie ins Leere, tut der Fallback nichts und sagt es nicht.

**Jeder Klick-Schritt wird MIT `point_id` gebaut**, nicht nachträglich verknüpft. Ein Test
(`kein Klick-Schritt wird ohne point_id gebaut`) prüft jede `SequenceStep(...)`-Konstruktion
im Baum; ausgenommen sind Schritte ohne echte Position (Taste, Scan, Wait, Screenshot) und
der Blanko-Block `(0, 0)` des Sequenz-Studios, der noch gar keine Stelle hat.

Darauf zu vertrauen, dass eine Migration das nachträglich verknüpft, reicht **nicht** —
und heute gibt es sie gar nicht mehr: die Kette ist samt Schleuse gelöscht (s.u.), und
auch der Konsolenbefehl `link`, der Schritte ohne Punkt nachträglich verknüpfte, ist
weg. Wer einen Klick-Schritt baut, baut ihn mit `point_id`, sonst hat er keine Stelle. Genau daran hing
einmal der Recorder: er legte Schritte und Punkte unabhängig voneinander an, und jede
aufgenommene Sequenz blieb dauerhaft unverknüpft.

**Die Kette hat ihre Arbeit getan und ist gelöscht — und die Schleuse mit ihr.** Vier
Schritte hoben den Altbestand auf Schema 4 — zuletzt `_seq_v3_to_v4`, das jede Koordinate
aus der Sequenz nach `points.json` zog und dafür notfalls einen Punkt anlegte. Seither
gilt die Regel ausnahmslos, es gibt keinen Bestand mehr unterhalb von Schema 4, und damit
sind die Schritte weg. Mit ihnen entfielen `_sichere_neue_punkte()` (sequences.py),
`_punkte_schreibfertig()` (sweep.py) und `_als_dicts()`: sie schrieben die von der
Migration angelegten Punkte zurück, und dieses Ereignis tritt nicht mehr ein.

Die leere Hülle blieb danach noch eine Weile stehen: `_CHAINS` mit einem leeren Eintrag,
`MigrationStep`, `migrate()` in jedem Loader und im Start-Durchgang, `needs_migration`,
`ALL_KINDS` und eine `KIND_*`-Konstante je Dateityp — „damit die Schleuse sitzt, wenn die
nächste Umstellung kommt". Sie ist am 30.10.2026 ersatzlos gegangen: die nächste
Umstellung bekommt ausdrücklich **keinen** Schritt (s. u.), und eine Schleuse, durch die
nichts mehr geht, ist ein Platzhalter, den jeder Loader mitschleppte. Das Modul hiess
danach nach etwas, das es nicht mehr tat — es heisst jetzt `schema.py` und trägt, was kein
Loader ersetzen kann: `SCHEMA_VERSION`, `stamp()` und die Erkennung einer **neueren**
Fassung (`from_newer_version()`, s. u.).

Was das für eine sehr alte Datei heisst, steht im Modul-Kopf von `schema.py` und in einem
Test: sie wird **gelesen, nicht umgerechnet**. Der Loader wirft deshalb nicht — er liest mit
`data.get(key, default)` —, die Sequenz kommt aber leer an. Der Weg dorthin ist dann nicht
die Wiederbelebung der Schritte, sondern `git show <commit>:autoclicker/persistence/migration.py`
oder die Sequenz im Studio neu zu bauen.

Das ist der vorgesehene Lebenslauf: **neue Daten entstehen korrekt, Altlasten gehen einmal
durch den Start-Durchgang — und dann gibt es nichts mehr, wofür man eine Schleuse bräuchte.**

## Persistenz-Layout (der Baum steht in der Wurzel-`CLAUDE.md`)

**Es gibt keinen globalen Bestand mehr.** `sequences/points.json`,
`slots/slots.json`, `items/items.json` und die Scan-Ordner im Wurzelverzeichnis
sind ersatzlos entfallen — auch ihre Pfade: `paths.py` kennt weder die Dateien noch
die Ordner (`SLOTS_DIR`, `ITEMS_DIR`, `ITEM_SCANS_DIR`, `BOSS_SCANS_DIR`, `ICON_SCANS_DIR`).
Die Ordner hielt es noch für genau einen Zweck, den Factory-Reset, der einen
solchen Altbestand wegräumen sollte, falls er auf einer Platte herumliegt; der Nutzer hat
entschieden, dass er das nicht mehr muss (sein Bestand liegt ohnehin in `sequences/`),
und mit den Konstanten gingen ihre Einträge in `handlers.handle_reset` und die
Altlayout-Muster in der `.gitignore`. Der Reset löscht `sequences/` — und damit alles,
was einer Sequenz gehört — und die Config. Wer zwei Spiele betreibt, hat nicht mehr die
Slots beider in einer Liste — das war der Grund für den Umzug.

Daraus folgt, was ein Loader braucht: **eine Scan-Datei kennt ihre Besitzerin**
(`owner_sequence`, aus dem Ordnernamen abgeleitet), und ohne Besitzerin lässt sich
kein Scan speichern (`save_item_scan` wirft). `active_templates_dir(state)` ist
deshalb der einzige Weg zu einer Vorlage — ein fest getippter `items/templates/`
zeigt ins Leere.

**Die Punkte stehen im Feld `points` derselben `sequence.json`**, und ihre IDs
gelten nur innerhalb dieser Sequenz. Eine eigene `points.json` gab es einmal; sie
zwang zwei Dateien in Gleichschritt, die getrennt gespeichert wurden — genau der
Fall, an dem ein Punkt fehlte, sobald man ihn brauchte.

**Wer eine Sequenz WECHSELT, wechselt ihre Punkte mit — in beide Richtungen.**
Der Umzug auf sequenzlokale Punkte hat an zwei Stellen genau eine Zeile
hinterlassen bzw. vermissen lassen, und die Fehler sind spiegelbildlich:

| wo | was fehlte | was man sah |
|---|---|---|
| `new()` (Studio) | `self.points` wurde nicht geleert | eine frisch angelegte Sequenz kam mit dem **ganzen Punktebestand der vorher offenen** auf die Platte — `save()` schreibt `self.points` |
| `edit_sequence()` (Konsole) | `new_sequence.points` wurde nicht gefüllt | die gespeicherte Sequenz hatte **gar keine Punkte**, während jeder Schritt weiter seine `point_id` trug |
| `edit_sequence()` (Konsole, **neue** Sequenz) | sie wurde erst beim Speichern die aktive | `learn` im Editor schrieb seinen Punkt in die **vorher aktive** Sequenz (deren Liste war `state.points`, und `save_points` speichert die aktive), und die neue bekam deren ganzen Bestand |

Der dritte Fall hat dieselbe Antwort wie der erste, nur früher im Ablauf: die
neue Sequenz wird **beim Anlegen** die aktive, mit einer **Kopie** des
bisherigen Bestands (`_work_on_copy`) — die Konsole braucht die Punkte, denn
CTRL+ALT+A legt sie in der aktiven Sequenz an. Gespeichert werden davon nur
die, die ein Schritt benutzt; ein Abbruch macht die vorige wieder aktiv. Und
`learn` speichert nicht mehr selbst: wie jede Änderung im Editor gilt der
Punkt mit `done`.

Alle drei sind derselbe Denkfehler aus der Zeit des globalen Bestands: dort war
`state.points` die eine Liste für alles, und ein Sequenzwechsel liess sie
zurecht in Ruhe. Seither ist die Frage bei **jedem** Wechsel des Gegenstands zu
beantworten — `load()`, `new()`, Import, Kalibrierung und der Konsolen-Editor
tun es heute alle. Regel beim Erweitern: **wer `self.board` bzw.
`state.active_sequence` setzt, setzt in derselben Zeilengruppe die Punkte.**
Zwei Tests messen beide Richtungen bis auf die **Platte** — einer, der nur die
Liste im Speicher prüft, sieht die Wirkung nicht, denn geschrieben wird erst
beim Speichern.

**`.run.json` ist kein Bestand** und steht deshalb nicht im Start-Durchgang: es
beschreibt den Zustand JETZT und wird überschrieben statt angehängt
(`runtime/status.py`). Am Sequenz-Ende bleibt genau **ein** Eintrag stehen — die
Zusammenfassung des letzten Laufs —, bis der nächste Start sie überschreibt. Dass es **oben** liegt und nicht in
`sequences/`, ist kein Zufall: `Path.glob("*.json")` erfasst auch Dateien mit
führendem Punkt. Dort abgelegt stünde es als Sequenz im Studio-Menü, im
Konsolen-Menü und im Start-Durchgang — und weil es sich sekündlich ändert,
gewänne es jedes Mal `last_edited()`. Dieselbe Falle, wegen der die
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
- **Nicht: eine Datei aus einer neueren Fassung darf überschrieben werden.** Sie
  wird gelesen, aber der Start-Durchgang lässt sie, wie sie ist (s. u.).

Die frühere Regel „Bestandsdateien werden über die Migration gehoben, nicht
fallengelassen" gibt es nicht mehr: es gibt keine Migration. Die Antwort ist immer:
Default in der Dataclass, fertig.

**Loader lesen das aktuelle Format**, verwenden Defaults für fehlende Felder und melden
falsche JSON-Strukturen als Ladefehler (`TypeError` in den `_*_from_dict`-Lesern, gefangen
von `LOAD_EXCEPTIONS`). Versioniert ist nur, was ein Dict als obersten Knoten hat und
einen Stempel braucht — heute `sequences/<name>/sequence.json`. Die trägt
`schema_version`, Saver stempeln mit `stamp()`. Alle anderen Typen (Presets, Scans, die
Boss-Bibliothek) tragen kein Versionsfeld.

**Eine Datei aus einer neueren Fassung bleibt, wie sie ist.** `schema.from_newer_version()`
erkennt ein Schema über `SCHEMA_VERSION` — etwa weil jemand zwischen zwei Ständen des
Programms hin- und herwechselt. Der Round-Trip des Start-Durchgangs liesse alles fallen,
was nur die neuere Fassung kennt, und stempelte das alte Schema darüber: aus der Datei
würde still eine Datei des alten Programms. Deshalb schreibt `sweep()` sie nicht zurück
(`SweepResult.newer`, gemeldet als „stammt aus einer neueren Fassung … bleibt
unverändert"), und `load_sequence_file()` sagt beim Laden ehrlich, dass beim **Speichern**
Felder verloren gehen. Hier stand beides falsch: der Loader meldete „auf Schema 4
gehoben", obwohl nichts gehoben wurde, und der Durchgang schrieb die Datei um.

**Die Normalisierer sind Geschichte.** Es gab einen zweiten Weg (`_NORMALIZER`,
idempotente Funktionen für Dateien ohne Versionsfeld); `_norm_points` hob
eine `points.json`, die es seit den sequenzlokalen Punkten gar nicht mehr gibt,
und die übrigen waren No-ops mit der Begründung „damit der Haken sitzt". Ein
Modul voller Haken für Dateien, die niemand mehr schreibt, ist genau das
Anwachsen, das hier vermieden werden soll — sie sind samt `KIND_POINTS` gelöscht.
Dasselbe Ende hat `AppConfig._FIELD_MIGRATION` (die Tabelle alter Config-Schlüssel)
genommen: der Start-Durchgang schreibt `config.json` seit langem im aktuellen
Format, die Tabelle war nach dem ersten Start wirkungslos. Ein alter Schlüssel ist
heute ein unbekannter — er fällt weg, das Feld bekommt seinen Default.

Regeln beim Format-Ändern:
1. Dataclass, Loader und Serializer gemeinsam anpassen; fehlende Felder bekommen Defaults.
2. Entfallene Felder im Serializer entfernen; der Start-Durchgang bereinigt die Dateien.
3. Keine Ketten, Normalisierer oder Schleusen ergänzen — es gibt keine.
4. Saver stempeln weiterhin mit `stamp()`; `SCHEMA_VERSION` nicht zurückdrehen.

**Der Durchgang schreibt eine Datei genau so lange um, wie es etwas aufzuräumen gibt.**
Eine aktuelle Datei ist ihr eigener Round-Trip: kein Schreibzugriff, kein `.bak`. Gemessen
an einer Sequenz ohne Stempel:

| | Datei wird geschrieben |
|---|---|
| 1. Start | ja — gestempelt und zurückgeschrieben |
| 2./3. Start | **nein** |
| 20× Sequenz laden | **nein** |

Ein Test pinnt das fest (`weitere Starts schreiben nichts mehr`).

**Der Durchgang läuft beim Programmstart**, nicht beim Speichern: `persistence/sweep.py`,
aufgerufen in `main.py` nach `init_directories()` und vor dem Laden (abschaltbar über
`migrate_on_start` — der Schlüssel in der `config.json` heisst so, die Beschriftung im
Studio „Beim Start aufräumen"). Speichern schreibt sowieso aktuelles Format — das Problem
sind Dateien, die man *nicht* anfasst. Nach dem ersten Start mit einer neuen Version sind
alle Dateien aktuell.

`sweep.py` erfasst **alle** JSON-Dateien und geht dafür über die **Besitzeinheiten**,
nicht über Dateitypen: `config.json`, dann je Sequenzordner die `sequence.json`
(mit ihren Punkten), ihre item-/boss-/icon-Scans und ihre Boss-Bibliothek, zuletzt
die beiden Preset-Ordner. Pro Datei ein Round-Trip durch Loader + Serializer. Der
Round-Trip ist die ganze Reinigung — was der Loader nicht kennt, schreibt der Serializer
nicht zurück. `tools/migrate.py` ist nur die CLI über derselben Funktion (der
Trockenlauf des Start-Durchgangs; der Name stammt aus der Zeit der Migrationsschritte).

**Hier stand einmal die flache Struktur, und der Durchgang war dadurch still tot.**
Aufgezählt waren `sequences/*.json`, `points.json` und die Scan-Ordner im
Wurzelverzeichnis — nach dem Umzug auf Besitzeinheiten fand der Glob nichts mehr
und die Wurzelordner gab es nicht: von dreizehn Datendateien erfasste
`collect_files()` noch die `config.json`. Auffallen konnte das nicht, denn die
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
bleiben unangetastet; eine Datei aus einer neueren Fassung ebenfalls). Zweiter Start
muss „0 geändert" ergeben; tut er das nicht, ist Loader oder Serializer nicht idempotent.

Die Sicherungen liegen unter **`backups/`** mit **gespiegelter Ordnerstruktur**
(`sequences/all_dayli.json` → `backups/sequences/all_dayli.json.bak`, `backup_path()`).
Beides ist nötig: neben dem Original verstellten sie den Blick auf die Daten und ein
`*.json`-Glob über `sequences/` konnte sie erwischen — und ohne den Unterordner
überschriebe die Sicherung von `item_scans/foo.json` die von `boss_scans/foo.json`,
gleicher Dateiname, andere Datei. Der Ordner entsteht **erst beim ersten Sichern**, nicht
in `init_directories()`: ein leeres `backups/` bei jeder frischen Installation wäre
Rauschen. Wie bisher gilt `if not backup.exists()` — die **erste** Sicherung bleibt die
älteste und wird nie überschrieben.

„Still, wenn nichts zu tun ist" gilt auch für **Zahlentypen**: JSON kennt nur eine Zahl,
`600` und `600.0` sind dieselbe. `_equal()` zieht beide Seiten deshalb durch
`_normalize_numbers()`, bevor es vergleicht. Ohne das galt eine von Hand auf `600`
getippte Wartezeit als aufzuräumen — der Loader macht `600.0` daraus —, und der Durchgang
schrieb die Datei um, legte ein `.bak` an und meldete eine Aufräumarbeit, die inhaltlich
nichts tat. `bool` bleibt dabei ausgenommen: `True` darf nicht als `1.0` durchgehen, sonst wäre
ein umgekipptes Flag unsichtbar.

**Nur gesetzte Felder werden geschrieben.** Jeder Serializer läuft durch
`_without_defaults(data, defaults)`; die Tabellen (`_ITEM_DEFAULTS`, `_SLOT_DEFAULTS`,
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

Der Name steht in Name→Eintrag-Dicts nur noch im Schlüssel (`slots` und `items` in der
Item-Scan-Datei, die Presets). `_item_from_dict(data, name)` und `_slot_from_dict(name, data)`
bekommen ihn von dort. In Listen (Bosse, wo die Reihenfolge Priorität ist) bleibt `name` im Eintrag.

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
| `next_free_name(prefix, assigned)` | durchnummerierte **Serien** — füllt Lücken | `Slot 1`, `Slot 2`, … |
| `unique_name(base_name, assigned)` | ein **vorgegebener** Name, der kollidiert | `Beutel oben` → `Beutel oben 2` |

Für Serien immer den ersten: ein angehängter Zähler ergäbe `Slot 3 2`, und das liest
niemand gern.

**Dieselbe Regel gilt für Sequenzen — und dort ist der Schlüssel der ORDNER.**
„Raid" und „raid" landen beide in `sequences/raid`. Drei Wege legen eine neue
Sequenz unter einem getippten Namen an, und alle drei schrieben über die
`sequence.json` einer vorhandenen: das Studio („Neu", Namen eintippen,
Speichern — die Ordnerprüfung stand nur im Zweig „alte Datei existiert"), die
Konsolen-Aufnahme und „Neue Sequenz erstellen" im Konsolen-Editor. Schritte und
Punkte waren weg, die Scans blieben daneben liegen. Heute:

| wo | was bei einem vergebenen Namen passiert |
|---|---|
| Studio `save()` | abgelehnt („Ordner existiert bereits") — bei **jedem** Umbenennen |
| Konsole (Aufnahme, Editor) | `confirm_new_sequence_name()`: überschreiben? sonst anderer Name |
| Aufnahme aus dem Studio | `free_sequence_name()`: ausweichen auf `Raid 2` — fragen geht dort nicht |

Beide Helfer stehen in `persistence/sequences.py`. Verschoben wird beim
Umbenennen, sobald es den alten **Ordner** gibt, nicht erst die Datei: auch eine
nie gespeicherte Sequenz kann dort schon gemerkte Bildschirme und gelernte
Vorlagen haben (der Reiter schreibt nach `self.filepath.parent`) — sie blieben
sonst im alten Ordner zurück. Danach wird der Scans-Reiter **nicht** neu
aufgebaut, nur sein gemerkter Plattenstand nachgezogen (`_disk_track()`): alle
Pfade leiten sich ohnehin aus `self.filepath` ab. Der frühere Neuaufbau warf
Screenshot, Auswahl, Rückgängig und ungespeicherte Scan-Änderungen weg, und die
rechte Spalte sprang mitten in der Arbeit auf „Slots".

Dieselbe Regel gilt für **Identität ausserhalb der Persistenz**: Loop-Phasen-Namen sind
frei wählbar und doppelt vergebbar, deshalb hängt der Zeitplan-Zustand im Worker an der
*Position* der Phase, nicht an ihrem Namen (`_schedule_watcher`). Ein Name ist eine
Beschriftung — als Schlüssel taugt er nur da, wo etwas ihn erzwingt.

**Speichern wird geschrieben, als gäbe es keine Altbestände.** Die Serializer schreiben
das optimale Format, nicht das kompatible: nur gesetzte Felder (`_STEP_DEFAULTS`), nur
Referenzen statt Kopien. Alles Alte räumt der Start-Durchgang beim nächsten Start weg —
was der Loader nicht kennt, kommt nicht zurück. Das ist die bewusste Entscheidung: lieber
ein optimales Format, dessen Altdatei ein Feld auf dem Standardwert bekommt, als ein
Format, das für immer seine Vorgeschichte mitträgt.

Für neue *optionale* Felder gilt weiterhin: Default in der Dataclass, `data.get(key,
default)` im Loader. Das ist kein Altlast-Fall und braucht keine Migration.
`AppConfig.from_dict()` filtert unbekannte Keys raus.

Das frühere `tools/sync_json.py` ist **gelöscht**: es pflegte fehlende Felder mit ihren
Standardwerten nach — also genau die Felder, die heute absichtlich weggelassen werden. Es
hätte jede Sequenz beim nächsten Lauf wieder aufgebläht. Alles, was es konnte, macht der
Start-Durchgang besser, weil er über Loader + Serializer geht statt über eine
handgepflegte Feldliste. (`git show <commit>^:tools/sync_json.py`, falls es je gebraucht
wird.)

## Saver melden, ob sie gespeichert haben

  **Ein Saver sagt, ob er gespeichert hat.** `write_scan()` und die `save_*_scan()`
  darüber geben `bool` zurück statt `None`: ein `IOError` wurde zwar gemeldet, aber
  der Aufrufer lief weiter, als sei nichts gewesen — im Studio hiess das „Gespeichert"
  über einer Datei, die nicht geschrieben wurde. Wer speichert, prüft den Rückgabewert
  und sammelt die Fehlschläge (`_detection_save()` macht es vor). Ein `try/except`
  allein reicht nicht: die Ausnahme wird eine Ebene tiefer schon gefangen.

  Das gilt seit dem Audit für **alle** Saver, auch `save_config()` und
  `save_points()` — die gaben `None` zurück, und genau dort stand es wieder:
  `config_write()` im Studio meldete `ok: True`, übernahm den Wert in den eigenen
  Prozess und schickte den Briefkasten-Befehl, während `config.json` unverändert
  war. Ein Aufrufer, der nach dem Speichern „gespeichert" sagt, prüft; wer nur
  zwischendurch sichert (Item-Editor vor `done`), darf die Meldung des Savers
  reichen lassen.

## Sequenzwechsel

**Wer eine Sequenz wechselt, ruft `activate_sequence(state, seq)`**
(`persistence/sequences.py`) — die EINE Stelle, die aktive Sequenz, Punkte
UND Scans (Item-, Boss-, Icon-Scans, Boss-Bibliothek) gemeinsam umstellt. Die
drei Zeilen dafür standen an fünf Stellen in `handlers.py` und im
Konsolen-Editor, und zweimal fehlte ein Teil: das Punkte-Menü (CTRL+ALT+P)
wechselte die Sequenz, liess aber die Scans der vorigen im Speicher — ein Start
danach lief mit B-Schritten gegen A-Scans; und der Konsolen-Editor bearbeitete B
mit den Punkten der gerade aktiven A und schrieb B mit A's Pool zurück. Regel
beim Erweitern: **wer `state.active_sequence` setzt, ruft `activate_sequence`**,
nichts anderes.

Und die Regel reichte als Regel nicht: der Konsolen-Loader (CTRL+ALT+L, dazu
CTRL+ALT+S und CTRL+ALT+T ohne geladene Sequenz) und das Ende einer Aufnahme
setzten die Sequenz trotzdem von Hand. Nach einem frischen Start hatte ein Lauf
damit **gar keine** Scans („Item-Scan nicht gefunden"), nach einem Wechsel die
der vorigen Sequenz. Seither misst ein Test den Quelltext: eine Zuweisung an
`.active_sequence` außerhalb von `persistence/sequences.py` ist rot (nur
`= None` beim Factory-Reset ist kein Wechsel). (Ein früheres `reload_points()` für einen separaten Punkte-Pool
ist gelöscht — die Punkte kommen mit der `sequence.json`, und ein Test verlangt,
dass kein Ladeweg sie separat nachlädt.)

**Es gibt EINE geladene Sequenz: `state.active_sequence`.** Daneben stand
`state.sequences`, ein Dict, das nur ein Teil der Ladewege pflegte
(Konsolen-Editor, Aufnahme, Import; Quick-Switch und Studio-Start nicht), und
`save_data()` schrieb es **komplett** zurück — auch eine Aufnahme von vorhin,
die das Studio inzwischen geändert hatte; die kam aus dem Speicher zurück auf
die Platte, ohne dass jemand an ihr gearbeitet hätte. Beides ist gelöscht.
Geschrieben wird die aktive Sequenz (`save_points`), alles andere liegt auf der
Platte und wird von dort gelesen (`list_available_sequences`, `load_sequence_file`).
