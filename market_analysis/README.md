# Idle Clans – Gold/h Farming-Analyse

Zieht Marktpreise und Rezepte aus der Idle-Clans-API, rechnet für jedes farmbare Item
Gold/h unter Berücksichtigung der Account-Upgrades und exportiert das Ergebnis nach
Excel. Läuft eigenständig – kein Import aus `autoclicker/`, kein Windows nötig.

```bash
pip install -r market_analysis/requirements.txt
python market_analysis/analyse.py
```

`matplotlib` ist optional (nur für den Chart). Alles Generierte landet in
`market_analysis/output/` und ist gitignored.

## Die Module

| Datei | Zweck |
|---|---|
| `analyse.py` | Hauptlauf: API → Rechnung → Excel + Chart |
| `pricing.py` | Verkaufsweg, Zutatenpreise, Ketten – die rechnende Schicht |
| `recipes.py` | Reine, separat getestete Rezept-Normalisierung |
| `orderbook.py` | Reine Orderbuch-, Geduld- und Trendberechnungen |
| `history.py` | Laufhistorie in SQLite: was das Überschreiben der Excel-Datei verliert |
| `verify.py` | Einzelne Items nachrechnen: jeder Zwischenschritt, dazu eine Ingame-Checkliste |
| `apicheck.py` | Prüft, ob die API noch die erwarteten Felder liefert |

`config.py` enthält alles Einstellbare – Skills, Upgrades, Schwellenwerte. Die anderen
Dateien musst du normalerweise nicht anfassen.

**Warum `pricing.py` und `history.py` eigene Module sind:** dort stehen die
Entscheidungen, an denen der ganze Lauf hängt – an wen wird verkauft, was kostet eine
Zutat, was kostet eine Kette. Solange sie in `analyse.py` zwischen DataFrames und
Excel-Formatierung lagen, waren sie nur prüfbar, wenn pandas installiert ist; die CI
installiert es nicht, also lief genau der rechnende Teil in keinem Test. Beide Module
kommen ohne pandas, Excel und Netz aus und stehen deshalb in `test_market_analysis.py`.

```bash
python market_analysis/verify.py oak titanium_bar tuna   # beliebige Rezeptnamen
python market_analysis/apicheck.py                       # nach Game-Updates
```

## Die Excel-Sheets

| Sheet | Bedeutung |
|---|---|
| **Empfehlung** | **Die Antwort:** was bringt am meisten Gold pro Zeit, und geht es an Spieler oder NPC. Eine Zeile pro Item, nach Gold/h sortiert |
| **Begründung** | **Warum** ist ein Item gut oder nicht: eine Stunde Produktion durch die echten Kaufgebot-Stufen im Player Shop gerechnet. Nur die Top 10 |
| **Ketten** | Alles selbst gefarmt, nichts zugekauft. **Das ist die Zahl, die zählt.** |
| **Realistisch_Farmbar** | Nur Ketten mit `FullySelfSufficient` – keine Zutat muss gekauft werden |
| **Nach_Skill_Level** | Verkaufbare Items sortiert nach Skill und Level |
| **Rohdaten** | Jedes Rezept einzeln, Zutaten zum Ask-Preis gekauft. Ungefiltert |
| **Preis_Sensitivität** | Gold/h über die 10 aktuellen Orderbook-Preispunkte je Item, plus NPC-Vergleichswert |

### Empfehlung lesen

| Spalte | Bedeutung |
|---|---|
| `Gold/h gewichtet` | **Sortierspalte:** Gold/h mal Verlässlichkeit |
| `Gold/h` | der echte Ertrag pro Stunde, alles selbst gefarmt |
| `Verlässlichkeit` | 1,0 = planbar farmbar, kleiner = Nachschub nur zufällig |
| `Hinweis` | warum abgewertet wurde |
| `Sek pro Stück` | wie lange ein Stück von Grund auf dauert |
| `Verkauf an` | Spieler oder NPC-Vendor – der bessere der beiden Wege |
| `Erlös pro Stück` | was wirklich ankommt, beim Player Shop **nach** 1 % Marktsteuer |
| `Spieler-Gebot (brutto)` / `NPC-Preis` | beide Wege nebeneinander, leer wenn nicht möglich |
| `Vorteil` | wie deutlich der gewählte Weg besser ist |
| `Alles selbst farmbar` | `False` heisst: eine Zutat muss gekauft werden |
| `Warnung` | knapper Absatz, breiter Spread, untypischer Preis |

#### Verlässlichkeit

Manche Ketten rechnen sich auf dem Papier hervorragend, lassen sich aber nicht auf Zuruf
farmen. Papaya ist das Musterbeispiel: die Samen fallen nur als Zufallsdrop an, du kannst
also nicht einfach „eine Stunde Papaya machen".

`SKILL_RELIABILITY` in `config.py` dämpft solche Skills:

```python
SKILL_RELIABILITY = {
    "Farming": (0.5, "Samen nur als Zufallsdrop"),
}
```

Das wirkt **ausschliesslich auf die Rangfolge der Empfehlung**. `Gold/h` bleibt der echte
Wert, und Ketten, Rohdaten, Begründung und der Chart bleiben unverändert – dort willst du
ja die ungeschönte Zahl sehen. Bei mehrstufigen Ketten zählt der unverlässlichste Schritt
(Minimum, nicht Produkt): zwei zufallsabhängige Skills machen eine Kette nicht doppelt so
unplanbar.

Der Lauf druckt dieselbe Top-Liste auch in die Konsole – für die schnelle Antwort
braucht man die Excel gar nicht zu öffnen. Abgewertete Ketten zeigen dort beide Zahlen:
`3.227.359 (6.454.719)`.

### Preis-Sensitivität und Chart

`output/price_sensitivity_chart.png` zeigt für die Top-N-Items den Gold/h-Verlauf über
die zehn aktuellen Orderbook-Preispunkte – links die fünf Kaufgebote, rechts die fünf
Verkaufsangebote. Alles netto: Materialkosten und die 1 % Marktsteuer sind abgezogen.

**Rote Punkte** markieren Preisstufen, auf denen der NPC-Vendor mindestens genauso viel
bringt – dort lohnt der Player Shop nicht mehr. Verglichen wird gegen `NPC_Gold_h`,
also den NPC-Erlös desselben Items bei gleichem Zeitaufwand. Items ohne NPC-Verkauf
haben keine roten Punkte.

### Begründung lesen

Die Gold/h-Werte aller anderen Sheets unterstellen, dass du beliebig viel zum **besten**
Gebot los wirst. Das stimmt nur, solange dort genug Volumen liegt. Dieses Sheet verkauft
eine Stunde Produktion tatsächlich durchs Orderbuch.

| Spalte | Bedeutung |
|---|---|
| `Bestes Gebot` / `Menge am besten Gebot` | oberste Stufe im Player Shop |
| `Deckt Stunden` | wie lange deine Produktion auf dieser Stufe Platz hat |
| `Schnitt bei 1h Produktion` | Durchschnittspreis, wenn du eine Stunde Ertrag ins Buch verkaufst |
| `Preisverlust` | wie weit das unter dem Listenpreis liegt |
| `Gold/h realistisch` | Gold/h mit diesem Schnitt statt mit dem Top-Gebot |
| `NPC besser` | der Vendor zahlt mehr als der Schnitt |
| `Kaufgebote (Stufen)` | die obersten fünf Stufen als Text |
| `Bewertung` | ein Satz Klartext, warum das Item taugt oder nicht |

Deckt das Top-Gebot mehrere Stunden, kannst du sofort verkaufen. Ist es nach Minuten
leer, rutschst du auf die nächste Stufe – dann steht die Wahrheit in `Gold/h realistisch`.
Weicht das Orderbuch stark vom Listenpreis ab, sagt die Bewertung das dazu: Bulk-Endpoint
und Orderbuch sind zwei Momentaufnahmen.

Umfang über `REASON_TOP_N` in `config.py`, abschalten mit `SHOW_REASON_ANALYSIS = False`.

### Steuer

Der Player Shop zieht **1 % vom Verkaufserlös** ab, aber **erst ab 100 Gold
Gesamtwert** eines Angebots; der NPC-Vendor nie. Beides ist überall eingerechnet: im
Gold/h, in den Ø-Preis-Spalten, in der Preis-Sensitivität und beim Durchrechnen des
Orderbuchs. Materialkosten bleiben unberührt – Kaufangebote sind steuerfrei.

**Die Untergrenze hängt an der Menge, nicht am Stückpreis.** `net_player_price(preis,
menge)` bekommt deshalb die Stückzahl mit – typisch eine Stunde Produktion, denn das
ist die Menge, die man am Stück anbietet. Ein einzelner Eichenstamm zu 76 g ist
steuerfrei, dieselben 76 g mal 500 Stück in einem Angebot nicht. Vorher wurde die
Grenze schlicht ignoriert („ein Stundenertrag liegt immer darüber"), und damit verlor
jedes billige Item bei jedem Vergleich 1 %, die es im Spiel nie zahlt.

**Netto wird nur mit Netto verglichen und Brutto nur mit Brutto.** Spalten mit
`(brutto)` zeigen den Preis wie im Spiel, alles andere ist der Nettoerlös. Der
Vergleich Spieler gegen NPC läuft netto gegen netto, sonst wäre er zugunsten des Player
Shops verzerrt. Umgekehrt sind die 1-/7-/30-Tage-Durchschnitte aus der API **Brutto**
– `price_position()` bekommt deshalb den Bruttopreis. Mit dem Nettoerlös gefüttert
meldete es bei jedem Item dieselben −1 %, also einen Messfehler, der wie eine Marktlage
aussieht.

Satz und Untergrenze änderbar über `PLAYER_MARKET_TAX` und
`PLAYER_MARKET_TAX_MIN_TOTAL` in `config.py`.

**Rohdaten vs. Ketten:** Rohdaten kauft Zutaten am Markt, Ketten farmt sie selbst. Für
`titanium_bar` heisst das: Rohdaten zieht 3 Erz + 9 Kohle vom Umsatz ab, Ketten rechnet
stattdessen die Minenzeit dazu. Beim echten Farmen zählt die Kette.

**Rohdaten filtert nichts weg.** Fällt ein Item aus den anderen Sheets, steht der Grund
im Klartext in `AusschlussGrund`, die Zeile ist orange markiert, das verantwortliche
Feld rot.

**`InKetten` heisst nur „verkaufbar".** Ein Item kann `InKetten=True` haben und trotzdem
im Ketten-Tab fehlen – nämlich wenn ein anderes, schnelleres Rezept desselben Items den
Platz belegt (pro ItemId kennt die Kettenanalyse nur einen Weg).

**Best/Worst-Case (`_Worst`-Spalten):** betrifft nur die Reichweite von Smelting Magic,
siehe unten. Wo Best = Worst, ist nichts unklar.

## Ingame verifiziert

Speed-Formel, per Anzeige im Skill-Panel gegengeprüft – Clan- und Equipment-Boost wirken
**multiplikativ**, nicht additiv:

| Aktion | Basiszeit | gerechnet | additiv wäre | ingame |
|---|---|---|---|---|
| oak | 6,0 s | 2,223 s | 2,040 s | **2,2 s** |
| coal_ore | 7,5 s | 2,779 s | 2,550 s | **2,8 s** |
| titanium_ore | 35,0 s | 12,967 s | 11,900 s | **13 s** |
| titanium_bar | 30,0 s | 13,500 s | *(gleich)* | **13,5 s** |

Weiter bestätigt:

- **`BaseTime` kommt in Millisekunden** (Median 12000 = 12 s/Aktion)
- **1 % Marktsteuer** auf Verkaufsangebote ab 100 Gold Gesamtwert im Player Shop;
  Kaufangebote und der NPC-Vendor sind steuerfrei
- **NPC-Verkaufsboost 1,155x** – „An offer they can't refuse" (+10 %) × Potion of
  negotiation (+5 %), laut Wiki exakt dieser Wert
- **Gatherers +5 %** auf Gathering-Skills, **Clan house + House = 50 %** XP
- **XP-Faktor 1,50** für Mining und Smithing (coal_ore 36, titanium_ore 270,
  titanium_bar 337,5 – jeweils auf die Kommastelle)
- **Equipment: 55 % Grundausrüstung, +6 % durch das Werkzeug des aktiven Skills.** Die
  Loadouts wechseln automatisch mit der Tätigkeit, deshalb zählt `has_tool`
  (= Werkzeug vorhanden) und nicht der Momentanwert im Boosts-Screen – der kann immer
  nur einen Skill auf 61 % zeigen.

### Per Wiki gegengeprüft (Juli 2026)

Abgleich der Config gegen das offizielle Wiki – alles unten **stimmt mit dem Code überein**:

| Wert | Config | Wiki |
|---|---|---|
| Gatherers | `CLAN_GATHERERS_SPEED_BOOST = 0.05` | +5 % Speed auf alle Gathering-Skills |
| NPC-Boost | `1.10 × 1.05 = 1.155` | „An offer they can't refuse" +10 %, Potion of negotiation +5 % |
| Marktsteuer | `PLAYER_MARKET_TAX = 0.01`, nur beim Verkauf | 1 % ab 100 Gold, Kaufangebote steuerfrei |
| Skilling-Handschuhe | `GLOVES_DOUBLE_CHANCE = 0.05`, multiplikativ zum `yield_multiplier` | 5 % doppelte Beute, **stapelt auf** Fisherman/Lumberjack; gibt **keine** XP |
| Smelting Magic | `SMELTING_MAGIC_SAVE = 0.30` (höchster Tier) | 10–30 % je Tier, Tiers stapeln **nicht**, neuester überschreibt |
| Astronomical ore | `SMELTING_MAGIC_EXCLUDED_ITEM_NAMES` | vom Perk ausgenommen |
| Fisherman/Lumberjack | XP wird **nicht** mit `yield_factor` multipliziert | „XP is only given for ONE fish/log" |

**Nicht per Wiki belegbar** (Seiten liefern 403, Werte sind account-/tierabhängig): die
Tier-Prozente von The fisherman / The lumberjack / Power forager (Config nimmt
100 %/100 %/50 %) sowie `AUTO_COOK_CHANCE`.

### Material-Ersparnisse (Stand 18.08.2026)

Drei Upgrades sparen Material, und **jedes ist ein eigener Schalter** – wer Trickery
hat, hat deshalb noch lange kein Seed Storage. Ein gemeinsamer „Materialkosten"-Prozent
wäre kürzer und liesse sich für den eigenen Account nicht mehr richtig einstellen.

| Upgrade | Schalter | spart | wirkt auf |
|---|---|---|---|
| Potion of Trickery | `POTION_OF_TRICKERY_ACTIVE` | 25 % (vorher 50 %) | Saatgut beim Farming |
| Seed Storage | `SEED_STORAGE_ACTIVE` | 10 % | Saatgut beim Farming |
| Ore Storage | `ORE_STORAGE_ACTIVE` | 10 % | Erz-Zeile der `*_bar`-Rezepte |
| Smelting Magic | `SMELTING_MAGIC_ACTIVE` | 30 % | Erz-Zeile der `*_bar`-Rezepte |

**Kombiniert wird multiplikativ** (`spar_faktor`): zwei Upgrades, die je 10 % sparen,
sparen zusammen 19 %, nicht 20 % – jedes greift auf das, was nach dem vorigen noch
übrig ist. Dieselbe Regel wie bei Clan- und Equipment-Boost auf der Zeitseite, und dort
per Stoppuhr bestätigt.

- Trickery + Seed Storage → **0,675** der Samen (`FARMING_COST_MULTIPLIER`)
- Smelting Magic + Ore Storage → **0,63** des Erzes (`SMITHING_SMELTING_COST_MULTIPLIER`)

**Wo Smelting Magic nicht greift, greift das Lager trotzdem.** Astronomical ore ist vom
Perk ausgenommen, und im Worst Case wirkt er womöglich nur auf die erste Kostenzeile –
Ore Storage ist ein eigenes Upgrade und hört dort nicht auf zu wirken
(`ORE_STORAGE_COST_MULTIPLIER`, siehe `kosten_faktor` in `recipes.py`).

### „Better fisherman" / „Better lumberjack"

Diese Perks geben **25 % XP für die zusätzlich erbeutete Ware** zurück – genau die XP, die
Fisherman/Lumberjack sonst unterschlagen. Schalter: `extra_yield_xp=True` beim jeweiligen
Skill in `SKILLS`, Anteil über `EXTRA_YIELD_XP_SHARE`.

**Standardmässig aus**, weil es ein eigener Kauf ist – wer The fisherman hat, hat nicht
zwangsläufig auch Better fisherman. Der Zuschlag hängt am `yield_multiplier`, nicht an den
Handschuhen (der Perk ist laut Wiki an The fisherman/The lumberjack gekoppelt):

| Skill | `yield_multiplier` | XP-Faktor mit Schalter |
|---|---|---|
| Fishing, Woodcutting | 2,0 | ×1,25 |
| Foraging | 1,5 | ×1,125 |

Betrifft **nur die XP-Spalten, nicht Gold/h.**

### Wonach die Top-10 sortiert ist

Nicht nach dem gerechneten Gold/h, sondern nach **`Gold/h realistisch`**: eine Stunde
Produktion wird durch das echte Orderbuch verkauft, Marktsteuer abgezogen, der Rest an den
NPC. Gemessen werden `REASON_CANDIDATES` (30) Kandidaten, angezeigt die besten
`REASON_TOP_N` (10).

Der Unterschied ist keine Kosmetik – das gerechnete Gold/h unterstellt, dass du beliebig
viel zum besten Gebot los wirst:

| | Papier | realistisch | Buch |
|---|---|---|---|
| dünnes Top-Gebot | 1.000.000 | **332.145** | nach 3 min leer |
| tiefes Buch | 700.000 | **699.930** | trägt 5 h |

Vorher wurde `Gold/h realistisch` erst **nach** der Rangfolge für die schon feststehende
Top-10 berechnet und konnte die Reihenfolge gar nicht mehr beeinflussen.

Items ohne Messung behalten ihre Position hinter den gemessenen und lassen die Spalte leer
– eine Zahl dort wäre eine Behauptung, die niemand geprüft hat.

### Was du verlangen kannst, wenn du warten kannst

Der Rest der Analyse rechnet mit dem **Sofortverkauf** ins beste Gebot. Wer das Gold nicht
sofort braucht, stellt stattdessen ein eigenes Angebot ein und bekommt die Spanne zwischen
Gebot und Angebot:

| Spalte | Bedeutung |
|---|---|
| `Ansetzbarer Preis` | tiefstes fremdes Angebot −1 (unterbieten), nie unter dem besten Gebot |
| `Erlös dabei (netto)` | davon nach 1 % Marktsteuer |
| `Gold/h mit Geduld` | Stück/h × (Erlös − Materialkosten) |
| `Aufschlag vs Sofort` | wie viel mehr als beim Reinverkaufen ins Gebot |
| `Wartezeit (h)` | wie lange der Markt braucht, um **eine Stunde** Produktion aufzunehmen |
| `Angebot im Buch` | wie viele Stück schon auf Käufer warten |

Der Unterschied kann die Rangfolge umdrehen:

```
Item              sofort      mit Geduld    Aufschlag   Wartezeit
dünnes Gebot     332.145      1.385.010        +39 %        20 h
tiefes Buch      699.930        703.890         +1 %       2,7 h
```

Beim ersten Item ist Geduld viermal so viel wert – aber eine Stunde Produktion liegt dann
20 Stunden im Buch. Sortieren lässt sich nach beidem: `RANKING_BASIS = "sofort"` (Standard)
oder `"geduld"` in `config.py`.

**Was die Wartezeit nicht modelliert:** Warteschlangen. Wer unterbietet, liegt vorn – aber
der Nächste unterbietet zurück. Übrig bleibt die belastbare Frage, ob der Tagesumsatz die
Menge überhaupt hergibt. `Angebot im Buch` steht als rohe Zahl daneben, ohne Modell.

### Preis-Position: ist die Momentaufnahme repräsentativ?

Gold/h sagt nur, was der Markt **heute** zahlt. Die Spalten `Preis vs 30-Tage-Schnitt` und
`Markt-Trend` ordnen das ein: liegt der Kurs 23 % unter seinem 30-Tage-Schnitt, verkauft
man in eine Delle; liegt er darüber, ist der ausgewiesene Wert eher die Ausnahme.

Das ist **keine Prognose**, nur Kontext. Der Trend wird nur ausgesprochen, wenn 1-, 7- und
30-Tage-Schnitt in dieselbe Richtung zeigen – zwei Stützstellen sind wenig, ein Wackler
soll nicht wie ein Trend aussehen. Beides kommt aus derselben Antwort wie das Orderbuch
und kostet keinen zusätzlichen Request.

## Historie

Excel und Chart werden bei **jedem Lauf überschrieben** – das bleibt so, sie beantworten
„was farme ich jetzt", und dafür ist ein Stand genug. Was dabei verloren ging, ist die
zweite Frage: **„war das gestern auch schon so?"** Ein Preissturz sieht in einer
Momentaufnahme genauso aus wie ein dauerhaft schlechtes Item.

Deshalb liegt neben den Dateien eine SQLite-Datenbank, `output/market_history.sqlite`.
Datierte Excel-Kopien wären der naheliegende und der falsche Weg: hundert `.xlsx` im
Ordner beantworten keine einzige Frage, ohne dass man sie alle öffnet.

| Tabelle | Inhalt |
|---|---|
| `runs` | ein Eintrag je Lauf: Zeitpunkt, Codeversion, Config-Hash, Anzahl Items |
| `items` | je Item und Lauf: Preise, Volumen, NPC-Preis, Kosten, Gold/h, gemessenes Gold/h, Verkaufsweg, Rang, Warnungen |
| `orderbook` | Gebots- und Angebotsstufen – nur für die `HISTORY_ORDERBOOK_TOP_N` besten Kandidaten |
| `daily` | verdichtete Tageswerte, wenn die Detailzeilen zu alt geworden sind |

Drei Regeln tragen das:

- **Nur erfolgreiche Läufe.** Geschrieben wird ganz am Ende, nach dem Excel-Export, in
  **einer Transaktion**. Bricht der Lauf vorher ab, steht nichts in der Datenbank – ein
  halber Lauf sähe in der Zeitreihe wie ein Markteinbruch aus. Keine Statusspalte, die
  jemand auswerten müsste, sondern gar kein Eintrag.
- **Jeder Lauf trägt Codeversion und Config-Hash.** Der Hash geht über die rechen­
  relevanten Werte (`CONFIG_HASH_KEYS`), nicht über die ganze Datei – Pfade und Farben
  ändern keine Zahl. Ohne die beiden vergleicht man Zahlen, die unter verschiedenen
  Annahmen entstanden sind, und hält eine geänderte Ersparnis für eine Marktbewegung.
- **Alte Details werden zu Tageswerten und verschwinden.** Erst zusammenfassen, dann
  löschen – in der anderen Reihenfolge wären die Tageswerte für genau die Tage leer,
  die man aufhebt, und aufgefallen wäre es nach 90 Tagen.

| Was | Wie lange | Schalter |
|---|---|---|
| Detailzeilen je Item | 90 Tage, danach zu Tageswerten verdichtet | `HISTORY_DETAIL_DAYS` |
| Orderbuchstufen | 30 Tage | `HISTORY_ORDERBOOK_DAYS` |
| Tageswerte | 365 Tage | `HISTORY_DAILY_DAYS` |
| Laufprotokolle | die jüngsten 100 | `HISTORY_RUN_LIMIT` |

Das Orderbuch kostet **keinen zusätzlichen Request**: gespeichert wird, was das Sheet
„Begründung" ohnehin schon abgerufen hat. Abschalten mit `HISTORY_ENABLED = False`;
schlägt das Schreiben fehl, kostet das nur die Historie – die Excel-Datei steht da schon.

```python
from market_analysis import history
conn = history.oeffne()
history.verlauf(conn, "yew_log")      # Preise und Gold/h über die Zeit
history.letzte_laeufe(conn, 5)        # wann, mit welchem Code, welcher Config
```

## Offene Punkte

**Reichweite von Smelting Magic.** Der Perk spart 30 % Erz beim Ore→Bar-Schmelzen. Unklar
ist, ob der Rabatt auch auf Nebenzutaten wirkt. Beide Varianten laufen parallel, die
Differenz steht in den `_Worst`-Spalten. Bei `titanium_bar` sind das 41 % Unterschied.

> Auflösen: 100 Bars schmelzen und den Verbrauch notieren. Bei titanium_bar wären es
> 210 Erz + **630** Kohle (best) gegen 210 Erz + **900** Kohle (worst).

**Auto-Cook-Chance.** `AUTO_COOK_CHANCE = 0.5` ist eine Annahme.

> Auflösen: 100 Fischzüge, roh und gekocht zählen.

**XP bei Woodcutting.** oak zeigt ingame 27,2 statt der gerechneten 26,25 – Faktor 1,554
statt 1,50. Da wirkt eine Woodcutting-spezifische Quelle, die das Modell nicht kennt.
Betrifft nur `XP/h` und `Gold per XP`, **nicht** Gold/h.

**Daily Boost.** Das Wiki nennt +30 % XP für 2 h, gemessen wurden +4 %. Steht auf
`DAILY_BOOST_ACTIVE = False` und betrifft ebenfalls nur die XP-Spalten.

**Brewing-Werkzeug.** Erledigt (18.08.2026): Brewing hat ein eigenes Werkzeug,
`has_tool=True`, also 61 % statt 55 %.

## Bekannte Vereinfachungen

**„Handelbar" und „liquide genug" sind zwei verschiedene Dinge.** Ob ein Item im Player
Shop gehandelt werden *darf*, sagt das API-Flag `CanNotBeTraded`. Ob sich ein
Sofortverkauf *lohnt*, hängt am Volumen am besten Gebot. Die Empfehlung zeigt deshalb das
Spielergebot immer an, wenn der Handel erlaubt ist – auch wenn die Preiswahl am Ende auf
den NPC fällt. Ein dünnes Top-Gebot erscheint als Warnung `Top-Gebot dünn (N Stk)`, nicht
als „kein Spielerverkauf".

> Beispiel Titanium platebody: Top-Gebot 18.006 g für **6** Stück, eine Stufe tiefer
> 53.139 Stück zu 18.005 g. Der NPC gewinnt hier trotzdem knapp (18.018 g gegen 17.826 g
> netto) – aber eben mit 1 % Vorsprung, nicht weil Spielerverkauf unmöglich wäre.

Die Flags einzelner Items prüfst du mit `python market_analysis/apicheck.py`
(Abschnitt 2b, Liste in `ITEM_FLAG_CHECKS`).

**Ein dünnes Top-Gebot ist eine Warnung, kein Ausschluss** (war einmal umgekehrt).
Das API-Feld `buyVol` ist die Menge *am besten Gebot*, nicht die Tiefe des Buchs.
Beispiel Oak: bestes Gebot 76 g für 6.178 Stück, während direkt darunter 327.915 Stück
zu 70 g liegen und das Tagesvolumen bei 174.303 steht.

Früher verlangte `MIN_SELL_VOLUME = 10000` genau diese Spitze und warf alles darunter
auf den NPC-Preis – Oak fiel damit von 258.462 auf 51.063 Gold/h, `yew_log` und
`yew_plank` genauso, obwohl alle drei bestens handelbar sind. Die Grenze war ausserdem
eine feste Stückzahl ohne Bezug zur Produktion: 10.000 Stück sind bei 200 Stk/h zwei
Tage Vorrat und bei 40.000 Stk/h eine Viertelstunde.

Heute gilt: **verkauft wird ins Gebot, also zählt nur die Gebotsseite** – `buy` und
`buyVol`, nie `sell`/`sellVol` (`valid_sell_market`). Es muss überhaupt ein Gebot geben
(`MIN_SELL_BID_VOLUME`), mehr nicht. Deckt das Top-Gebot weniger als `THIN_BID_HOURS`
Stunden Produktion, steht das als Warnung `Top-Gebot dünn` in Empfehlung und Rohdaten.
Wie tief das Buch wirklich ist, weiss der Bulk-Endpoint gar nicht – das misst das Sheet
**Begründung**, indem es eine Stunde Produktion durch die echten Gebotsstufen verkauft.

Umgekehrt zählt beim **Einkauf** von Zutaten nur die Angebotsseite
(`valid_buy_market`, `MIN_BUY_ASK_VOLUME`). Beides in einem Filter zu vermischen war
der eigentliche Fehler.

**Auto-Cook verkauft den rohen Rest mit** (war einmal umgekehrt). Ein Fischzug liefert
je zur Hälfte gekochten und rohen Fisch. Die Kette rechnete lange nur eine Hälfte und
war damit rund ein Drittel zu pessimistisch – bei tuna 154.170 statt ~198.800 Gold/h.

Der rohe Rest geht jetzt als `Nebenertrag/h` in die Kette ein, über denselben
Verkaufsweg wie jedes andere Item (Gebot oder NPC, je nachdem was mehr bringt). Auf
`AUTO_COOK_SELL_RAW_REST = False` steht wieder die alte Rechnung da.

**Gold ist ein Item, kein Sonderfall der Rechnung.** Die API führt Gold als
`ItemId 19`, und Carpentry-Rezepte zahlen damit (Nägel, Leim). Ein Markteintrag
existiert dafür natürlich nicht – die Zeile fiel deshalb unter „Preis unbekannt" und
kostete **nichts**, womit die betroffenen Rezepte billiger aussahen, als sie sind. Ein
Gold kostet ein Gold (`GOLD_ITEM_ID`, `GOLD_ITEM_PRICE`).

Es zählt voll in die Kosten, lässt die Kette aber **autark**: Gold kauft man nicht am
Markt und farmt es auch nicht als Zutat. Sonst trüge jedes Carpentry-Rezept die Warnung
„Zutat muss gekauft werden" für seine Nägel – und eine Warnung, die immer ansteht,
warnt nicht mehr.

**Ein unbekannter Zutatenpreis ist keine kostenlose Zutat.** Findet sich für eine
Kostenzeile kein Preis (kein Markteintrag, kein Angebot), bleibt `Gold/h` **leer** statt
0, und die fehlende Zutat steht beim Namen in `FehlendeZutaten` und in
`AusschlussGrund`. Vorher rutschte die Zeile stillschweigend mit 0 durch, und das
Rezept stand mit vollem Gewinn in der Rangliste – genau dort, wo man am wenigsten
nachrechnet. Solche Items können nicht ranken und fehlen deshalb in **Empfehlung** und
**Begründung**; im Ketten- und Rohdaten-Sheet stehen sie mit Grund.

**Rezeptauswahl rein nach Zeit.** Produzieren mehrere Skills dasselbe Item, nimmt die
Kettenanalyse den schnellsten Weg – der kann teurer und in Summe schlechter sein. Im
Rohdaten-Tab sind alle Wege einzeln sichtbar.

**Nur der letzte Schritt zählt XP.** `XP/h (letzter Schritt)` ignoriert die XP der
Vorstufen. Bei Auto-Cook ist der letzte Schritt das *Fischen*, nicht das Kochen – der
Kochschritt findet ja nie statt. `FinalSkill` und `Level` kommen dort deshalb ebenfalls
vom Fisch-Rezept, sonst stünde „FinalSkill: Cooking" neben „ChainSkills: Fishing".

## Wenn etwas nicht stimmt

Der Lauf meldet sich selbst, wenn Annahmen brechen:

- Unplausible Aktionszeiten → `BaseTime` kommt nicht mehr in Millisekunden
- Fehlende Avg-Felder → API hat Feldnamen geändert, die echten Keys stehen in der Meldung
- API-Skills ohne Eintrag in `SKILLS` → laufen sonst still ohne Boosts mit
- Kennzahlen-Einbruch gegenüber dem letzten Lauf (`output/run_stats_history.json`)

Bei Verdacht auf ein Game-Update: `python market_analysis/apicheck.py` prüft alle
Feldnamen und Strukturannahmen gegen die Live-API.

## Anpassen

Neues Werkzeug für einen Skill:

```python
"Brewing": SkillConfig(equipment_speed_boost=equip(), has_tool=True),
```

Skill komplett ignorieren: `excluded=True`. Andere Smelting-Magic-Stufe:
`SMELTING_MAGIC_SAVE`. Material-Ersparnisse ein- und ausschalten:
`POTION_OF_TRICKERY_ACTIVE`, `SEED_STORAGE_ACTIVE`, `ORE_STORAGE_ACTIVE`.
Langzeit-Durchschnitte in den Rohdaten: `SHOW_LONGTERM_AVERAGES = True` – kostet einen
Request pro Item, also Minuten.

Die Ersparnis-Schalter sind der Teil, den man nach jedem Upgrade-Kauf anfasst; sie
gehen in den Config-Hash der Historie ein, damit ein Sprung im Gold/h später als
Config-Änderung erkennbar bleibt und nicht als Marktbewegung.
