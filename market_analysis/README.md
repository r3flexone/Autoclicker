# Idle Clans – Gold/h Farming-Analyse

Zieht Marktpreise und Rezepte aus der Idle-Clans-API, rechnet für jedes farmbare Item
Gold/h unter Berücksichtigung der Account-Upgrades und exportiert das Ergebnis nach
Excel. Läuft eigenständig – kein Import aus `autoclicker/`, kein Windows nötig.

```bash
pip install pandas requests openpyxl matplotlib
python market_analysis/analyse.py
```

`matplotlib` ist optional (nur für den Chart). Alles Generierte landet in
`market_analysis/output/` und ist gitignored.

## Die drei Skripte

| Datei | Zweck |
|---|---|
| `analyse.py` | Hauptlauf: API → Rechnung → Excel + Chart |
| `verify.py` | Einzelne Items nachrechnen: jeder Zwischenschritt, dazu eine Ingame-Checkliste |
| `apicheck.py` | Prüft, ob die API noch die erwarteten Felder liefert |

`config.py` enthält alles Einstellbare – Skills, Upgrades, Schwellenwerte. Die anderen
Dateien musst du normalerweise nicht anfassen.

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
| `Gold/h` | Ertrag pro Stunde, alles selbst gefarmt |
| `Sek pro Stück` | wie lange ein Stück von Grund auf dauert |
| `Verkauf an` | Spieler oder NPC-Vendor – der bessere der beiden Wege |
| `Erlös pro Stück` | was wirklich ankommt, beim Player Shop **nach** 1 % Marktsteuer |
| `Spieler-Gebot (brutto)` / `NPC-Preis` | beide Wege nebeneinander, leer wenn nicht möglich |
| `Vorteil` | wie deutlich der gewählte Weg besser ist |
| `Alles selbst farmbar` | `False` heißt: eine Zutat muss gekauft werden |
| `Warnung` | knapper Absatz, breiter Spread, untypischer Preis |

Der Lauf druckt dieselbe Top-Liste auch in die Konsole – für die schnelle Antwort
braucht man die Excel gar nicht zu öffnen.

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

Der Player Shop zieht **1 % vom Verkaufserlös** ab (ab 100 Gold Gesamtwert), der
NPC-Vendor nicht. Das ist überall eingerechnet: im Gold/h, in den Ø-Preis-Spalten, in der
Preis-Sensitivität und beim Durchrechnen des Orderbuchs. Materialkosten bleiben
unberührt – Kaufangebote sind steuerfrei.

Spalten mit `(brutto)` zeigen den Preis wie im Spiel, alles andere ist der Nettoerlös.
Der Vergleich Spieler gegen NPC läuft netto gegen netto, sonst wäre er systematisch
zugunsten des Player Shops verzerrt. Bei knappen Fällen kippt das die Entscheidung
Richtung NPC. Satz änderbar über `PLAYER_MARKET_TAX` in `config.py`.

**Rohdaten vs. Ketten:** Rohdaten kauft Zutaten am Markt, Ketten farmt sie selbst. Für
`titanium_bar` heißt das: Rohdaten zieht 3 Erz + 9 Kohle vom Umsatz ab, Ketten rechnet
stattdessen die Minenzeit dazu. Beim echten Farmen zählt die Kette.

**Rohdaten filtert nichts weg.** Fällt ein Item aus den anderen Sheets, steht der Grund
im Klartext in `AusschlussGrund`, die Zeile ist orange markiert, das verantwortliche
Feld rot.

**`InKetten` heißt nur „verkaufbar".** Ein Item kann `InKetten=True` haben und trotzdem
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

**Brewing-Werkzeug.** Unbekannt, ob es eins gibt → konservativ ohne (55 %). Falls doch:
`has_tool=True` setzen.

## Bekannte Vereinfachungen

**`MIN_SELL_VOLUME` misst nur die Spitze des Orderbuchs.** Das API-Feld `buyVol` ist die
Menge *am besten Gebot*, nicht die Tiefe. Beispiel Oak: bestes Gebot 76 g für 6.178 Stück
– unter der Schwelle von 10.000 –, während direkt darunter 327.915 Stück zu 70 g liegen
und das Tagesvolumen bei 174.303 steht. Das Item kippt dann auf den NPC-Preis und fällt
von 258.462 auf 51.063 Gold/h, obwohl es bestens handelbar ist.

Der Lauf warnt inzwischen bei solchen Grenzfällen. Wer per Sell-Order statt Sofortverkauf
handelt, sollte die Schwelle deutlich senken und sich stattdessen an den Ø-Preis-Spalten
und `LiquidityWarning` orientieren.

**Auto-Cook wirft den rohen Rest weg.** Ein Fischzug liefert je zur Hälfte gekochten und
rohen Fisch; die Kette rechnet immer nur eine Hälfte. Bei tuna: 154.170 Gold/h
ausgewiesen, mit beiden Hälften wären es ~198.800. Die Ketten sind hier also eher
zu pessimistisch.

**Rezeptauswahl rein nach Zeit.** Produzieren mehrere Skills dasselbe Item, nimmt die
Kettenanalyse den schnellsten Weg – der kann teurer und in Summe schlechter sein. Im
Rohdaten-Tab sind alle Wege einzeln sichtbar.

**Nur der letzte Schritt zählt XP.** `XP/h (letzter Schritt)` ignoriert die XP der
Vorstufen.

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
`SMITHING_SMELTING_COST_MULTIPLIER`. Langzeit-Durchschnitte in den Rohdaten:
`SHOW_LONGTERM_AVERAGES = True` – kostet einen Request pro Item, also Minuten.
