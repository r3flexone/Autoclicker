# Autoclicker for Idle Clans

Ein Windows-Autoclicker mit Sequenz-Unterstützung, automatischer Item-Erkennung und Farb-Triggern.

## Features

- **Punkte aufnehmen**: Mausposition speichern mit automatischer Benennung
- **Sequenzen erstellen**: Punkte mit Wartezeiten oder Farb-Triggern verknüpfen
- **Dreiphasen-System**:
  - **INIT**: Einmalig vor allen Zyklen (Initialisierung)
  - **LOOP-Phasen**: Mehrere Loops möglich, jeweils mit eigenen Wiederholungen
  - **END**: Einmalig nach allen Zyklen (z.B. für Logout)
- **Farb-Trigger**: Warte bis eine bestimmte Farbe erscheint ODER verschwindet
- **Zufällige Verzögerung**: `1 30-45` = warte 30-45 Sekunden zufällig
- **Tastatureingaben**: Automatische Tastendrücke (Enter, Space, F1-F12, etc.)
- **Automatische Slot-Erkennung**: OpenCV-basierte Erkennung von Item-Slots
- **Item-Scan System**: Items anhand von Marker-Farben oder Templates erkennen
- **Kategorie-System**: Items gruppieren (z.B. Hosen, Jacken) - nur bestes pro Kategorie klicken
- **Template-Matching**: Items per Screenshot erkennen (OpenCV)
- **Preset-System**: Slots und Items als benannte Presets speichern
- **Bedingte Logik**: ELSE-Aktionen wenn Scan/Pixel-Trigger fehlschlägt
- **Zeitgesteuerte Loops**: Loop-Phasen nur zu bestimmter Uhrzeit ausführen (z.B. Loop 3 nur um 12:30)
- **Pause/Resume**: Sequenz pausieren ohne Fortschritt zu verlieren
- **Skip**: Aktuelle Wartezeit überspringen
- **Statistiken**: Laufzeit, Klicks, Items gefunden
- **Quick-Switch**: Schnell zwischen Sequenzen wechseln
- **Zeitplan**: Sequenz zu bestimmter Zeit starten (z.B. 14:30, +30m, 2h)
- **Factory Reset**: Kompletter Reset wie frisch von GitHub
- **Konfigurierbar**: Toleranzen und Einstellungen via `config.json`
- **Fail-Safe**: Maus in obere linke Ecke bewegen stoppt den Klicker
- **IDE-Kompatibel**: Volle Pfeiltasten-Navigation auch in PyCharm/IDE-Konsolen

## Voraussetzungen

- Windows 10/11
- Python 3.10+
- **Optional**: Pillow für Farberkennung (`pip install pillow`)
- **Optional**: OpenCV für automatische Slot-Erkennung (`pip install opencv-python numpy`)

## Installation

```bash
git clone https://github.com/r3flexone/Autoclicker-Idleclans.git
cd Autoclicker-Idleclans
pip install pillow opencv-python numpy  # Optional, für erweiterte Features
python main.py
```

## Schnellstart-Anleitung

### Einfache Klick-Sequenz

1. **Punkte aufnehmen**: Maus auf die gewünschte Stelle bewegen, dann `CTRL+ALT+A` drücken. Für jede Klick-Position wiederholen.
2. **Sequenz erstellen**: `CTRL+ALT+E` öffnet den Editor. Punkte mit Zeiten verknüpfen, z.B.:
   - `1 30` → Punkt 1 klicken nach 30 Sekunden Wartezeit
   - `2 0` → Punkt 2 sofort klicken
   - `3 30-45` → Punkt 3 klicken nach 30-45s zufälliger Wartezeit
3. **Sequenz starten**: `CTRL+ALT+S`

### Mit Item-Erkennung (automatisches Erkennen + Klicken von Items)

1. **Punkte aufnehmen** wie oben (für alle Klick-Positionen)
2. **Item-Scan System einrichten** mit `CTRL+ALT+N`:
   - **Slots** erstellen (Menü 1) → Bereiche wo Items im Spiel erscheinen können
   - **Items** lernen (Menü 2) → Welche Items erkannt werden sollen (`learn <Slot-Nr>`)
   - **Scan** erstellen (Menü 3) → Slots + Items verknüpfen und benennen
3. **Im Sequenz-Editor** (`CTRL+ALT+E`) den Scan als Schritt einfügen: `scan <Name>`
4. **Starten** mit `CTRL+ALT+S`

### Mit Farb-Triggern (warte bis Farbe erscheint/verschwindet)

Im Sequenz-Editor:
- `1 pixel` → Warte bis bestimmte Farbe erscheint, dann Punkt 1 klicken
- `1 gone` → Warte bis Farbe VERSCHWINDET, dann Punkt 1 klicken
- `wait pixel` → Nur auf Farbe warten (kein Klick)

## Hotkeys

### Aufnahme

| Hotkey | Funktion |
|--------|----------|
| `CTRL+ALT+A` | Mausposition als Punkt speichern |
| `CTRL+ALT+U` | Letzten Punkt entfernen (Undo) |
| `CTRL+ALT+C` | Alle Punkte löschen |

### Editoren

| Hotkey | Funktion |
|--------|----------|
| `CTRL+ALT+E` | Sequenz-Editor (Punkte + Zeiten verknüpfen) |
| `CTRL+ALT+N` | Item-Scan Editor (Items erkennen + vergleichen) |
| `CTRL+ALT+L` | Gespeicherte Sequenz laden |
| `CTRL+ALT+P` | Punkte testen/anzeigen/umbenennen |
| `CTRL+ALT+T` | Farb-Analysator (für Bilderkennung) |

### Ausführung

| Hotkey | Funktion |
|--------|----------|
| `CTRL+ALT+S` | Start/Stop der aktiven Sequenz |
| `CTRL+ALT+F` | Sanft beenden (Zyklus abschließen, dann END + Stop) |
| `CTRL+ALT+G` | Pause/Resume |
| `CTRL+ALT+K` | Skip (aktuelle Wartezeit überspringen) |
| `CTRL+ALT+W` | Quick-Switch (schnell Sequenz wechseln) |
| `CTRL+ALT+Z` | Zeitplan (Start zu bestimmter Zeit) |

### System

| Hotkey | Funktion |
|--------|----------|
| `CTRL+ALT+X` | Factory Reset (Punkte + Sequenzen) |
| `CTRL+ALT+Q` | Programm beenden |

## Item-Scan System (`CTRL+ALT+N`)

Das Item-Scan System bietet ein Menü mit folgenden Optionen:
- **[1] Slots bearbeiten** - Bereiche wo Items erscheinen können
- **[2] Items bearbeiten** - Item-Profile für die Erkennung
- **[3] Scans bearbeiten** - Slots und Items verknüpfen

### Slot-Editor (Menü → 1)

Verwaltet Bereiche wo Items erscheinen können. Arbeitet mit **Presets** - wie beim Sequenz-Editor wird am Anfang nach einem Namen gefragt.

**Ablauf:**
1. [0] Neues Preset erstellen → Name eingeben
2. [1-n] Bestehendes Preset bearbeiten
3. Slots hinzufügen/bearbeiten/löschen
4. `done` → Preset wird gespeichert
5. `cancel` → Änderungen werden verworfen

**Befehle im Editor:**

| Befehl | Beschreibung |
|--------|--------------|
| `auto` | Automatische Slot-Erkennung mit OpenCV |
| `add` | Manuell einen Slot hinzufügen |
| `del <Nr>` | Slot löschen |
| `del <Start>-<Ende>` | Mehrere Slots löschen (z.B. `del 1-7`) |
| `del all` | Alle Slots löschen |
| `edit <Nr>` | Slot bearbeiten |
| `show` | Alle Slots anzeigen |
| `done` | Preset speichern und Editor verlassen |
| `cancel` | Änderungen verwerfen und Editor verlassen |

### Automatische Erkennung

Mit `auto` werden Slots automatisch per Farbe erkannt:
1. Region markieren (oben-links, unten-rechts)
2. Screenshot wird erstellt
3. Hintergrundfarbe des Slots angeben
4. Slots werden automatisch erkannt und nummeriert
5. Screenshot und Vorschau werden in `Screenshots/` gespeichert

### Item-Editor (Menü → 2)

Verwaltet Item-Profile für die Erkennung. Arbeitet mit **Presets** - wie beim Sequenz-Editor wird am Anfang nach einem Namen gefragt.

**Ablauf:**
1. [0] Neues Preset erstellen → Name eingeben
2. [1-n] Bestehendes Preset bearbeiten
3. Items lernen/hinzufügen/bearbeiten/löschen
4. `done` → Preset wird gespeichert
5. `cancel` → Änderungen werden verworfen

**Befehle im Editor:**

| Befehl | Beschreibung |
|--------|--------------|
| `learn <Nr>` | Item von Slot Nr. lernen (scannt Marker-Farben + Template) |
| `add` | Manuell ein Item hinzufügen |
| `edit <Nr>` | Item bearbeiten (Priorität, Farben, Bestätigung) |
| `rename <Nr>` | Item umbenennen (inkl. Template-Datei) |
| `del <Nr>` | Item löschen |
| `del <Start>-<Ende>` | Mehrere Items löschen (z.B. `del 1-5`) |
| `del all` | Alle Items löschen |
| `template <Nr>` | Template für Item setzen/entfernen |
| `templates` | Verfügbare Templates anzeigen |
| `show` | Alle Items anzeigen |
| `done` | Preset speichern und Editor verlassen |
| `cancel` | Änderungen verwerfen und Editor verlassen |

### Item lernen

Mit `learn <Nr>` wird ein Item vom entsprechenden Slot gelernt:
1. Slot-Nummer eingeben
2. 1 Sekunde warten (Item muss sichtbar sein)
3. Marker-Farben werden automatisch gescannt
4. Name, Priorität und **Kategorie** eingeben
5. Template-Screenshot wird automatisch erstellt
6. Optional: Bestätigungs-Klick konfigurieren

### Bulk-Learn (mehrere Items auf einmal)

Mit `learn <Start>-<Ende>` können mehrere Items gleichzeitig gelernt werden:

```
learn 1-5               # Lernt Items von Slot 1 bis 5
```

**Ablauf:**
1. Gemeinsame Einstellungen eingeben (Name-Prefix, Kategorie, Template)
2. Für jeden Slot wird automatisch:
   - Screenshot erstellt
   - Marker-Farben gescannt
   - Item mit fortlaufender Nummer gespeichert (z.B. "Juwel_1", "Juwel_2", ...)
   - Template erstellt (falls gewählt)

### Kategorie-System

Items können einer **Kategorie** zugeordnet werden (z.B. "Hosen", "Jacken", "Juwelen"):

- Items **derselben Kategorie** konkurrieren - nur das mit der niedrigsten Priorität wird geklickt
- Items **verschiedener Kategorien** konkurrieren nicht - alle werden geklickt
- Ohne Kategorie ist jedes Item seine eigene Kategorie

**Beispiel:**
```
Pinkes Juwel   [Kategorie: Juwelen]  Priorität 1  ← wird geklickt
Blaues Juwel   [Kategorie: Juwelen]  Priorität 2  ← wird NICHT geklickt (P1 ist besser)
Rote Jacke     [Kategorie: Jacken]   Priorität 1  ← wird geklickt (andere Kategorie)
```

**JSON-Format:**
```json
{
  "Pinkes Juwel": {
    "name": "Pinkes Juwel",
    "priority": 1,
    "template": "pinkes_juwel.png",
    "min_confidence": 0.8,
    "category": "Juwelen"
  }
}
```

### Template-Matching

Items können per **Template-Matching** (Screenshot-Vergleich) erkannt werden:

1. Bei `learn` wird automatisch ein Template erstellt
2. Mit `template <Nr>` kann ein Template nachträglich gesetzt werden
3. Templates werden in `items/templates/` gespeichert
4. `min_confidence` (0.0-1.0) bestimmt wie genau das Match sein muss

Template-Matching ist genauer als Marker-Farben, besonders bei ähnlichen Items.

## Sequenz-Editor (`CTRL+ALT+E`)

### Phasen

Eine Sequenz besteht aus drei Phasen:

1. **INIT**: Einmalig vor allen Zyklen (Initialisierung, optional)
2. **LOOP**: Wird wiederholt (konfigurierbare Anzahl, mehrere Loops möglich)
3. **END**: Einmalig nach allen Zyklen (optional)

### Loop-Phasen

Jede Sequenz kann mehrere Loop-Phasen haben, die nacheinander durchlaufen werden. Beim Erstellen einer Loop-Phase werden Name und Wiederholungen abgefragt.

**Befehle im Loop-Editor:**

| Befehl | Beschreibung |
|--------|--------------|
| `add` | Neue Loop-Phase hinzufügen |
| `edit <Nr>` | Schritte einer Loop-Phase bearbeiten |
| `del <Nr>` | Loop-Phase löschen |
| `time <Nr>` | Startzeit für Loop-Phase setzen/entfernen (z.B. `12:30`) |
| `show` | Alle Loop-Phasen anzeigen |
| `done` | Weiter zur END-Phase |

### Zeitgesteuerte Loops

Loop-Phasen können an eine bestimmte **Uhrzeit** gebunden werden (z.B. "Loop 3 startet nur um 12:30"):

- **Normale Loops** (ohne Zeit) laufen im Zyklus wie gewohnt
- **Zeitgesteuerte Loops** werden übersprungen, bis ihre Startzeit erreicht ist
- Die Zeit wird **nie verpasst**: Ein Hintergrund-Thread überwacht die Uhr und setzt ein Pending-Flag
- Die Ausführung erfolgt an der **natürlichen Position** im Zyklus (nicht als Interrupt)
- Der **Failsafe-Timer** wird durch das Warten nicht ausgelöst

**Einrichten:**
- Beim Erstellen: `Startzeit (HH:MM, leer = immer):` eingeben
- Nachträglich: `time <Nr>` im Loop-Editor (z.B. `time 3`)
- Entfernen: `time <Nr>` und dann `0` eingeben

**Beispiel:**
```
Loop 1: Ressourcen sammeln x5         ← läuft immer
Loop 2: Items verkaufen x3            ← läuft immer
Loop 3: Boss-Fight x1 [Start: 12:30] ← nur um 12:30
```

Loops 1 und 2 laufen im Zyklus weiter. Wenn 12:30 erreicht wird, führt der nächste Zyklus auch Loop 3 aus – danach wird Loop 3 wieder übersprungen bis zum nächsten Tag um 12:30.

### Editor-Befehle

| Befehl | Beschreibung |
|--------|--------------|
| `<Nr> <Zeit>` | Warte X Sekunden, dann klicke Punkt (z.B. `1 30`) |
| `<Nr> <Min>-<Max>` | Zufällige Wartezeit (z.B. `1 30-45`) |
| `<Nr> 0` | Sofort klicken ohne Wartezeit |
| `<Nr> pixel` | Warte auf Farbe, dann klicke |
| `<Nr> gone` | Warte bis Farbe VERSCHWINDET, dann klicke |
| `<Nr> <Zeit> pixel` | Warte X Sek, dann auf Farbe warten, dann klicke |
| `wait <Zeit>` | Nur warten, KEIN Klick (z.B. `wait 30`, `wait 30m`, `wait 2h`) |
| `wait <Min>-<Max>` | Zufällig warten, KEIN Klick (z.B. `wait 30-45`) |
| `wait 14:30` | Warte bis 14:30 Uhr (heute oder morgen), KEIN Klick |
| `wait pixel` | Auf Farbe warten, KEIN Klick |
| `wait gone` | Warten bis Farbe VERSCHWINDET, KEIN Klick |
| `key <Taste>` | Taste sofort drücken (z.B. `key enter`) |
| `key <Zeit> <Taste>` | Warten, dann Taste drücken (z.B. `key 5 space`) |
| `key <Min>-<Max> <Taste>` | Zufällig warten, dann Taste (z.B. `key 30-45 enter`) |
| `scan <Name>` | Item-Scan ausführen (bestes pro Kategorie) |
| `scan <Name> best` | Item-Scan: nur 1 Item total (das absolute Beste) |
| `scan <Name> every` | Item-Scan: alle Treffer ohne Filter (für Duplikate) |
| `... else skip` | Bei Fehlschlag **diesen Schritt** überspringen (nächster Schritt läuft weiter) |
| `... else skip_cycle` | Bei Fehlschlag **ganzen Zyklus** abbrechen (nächster Zyklus startet) |
| `... else restart` | Bei Fehlschlag **komplett neu starten** (inkl. INIT) |
| `... else <Nr> [s]` | Bei Fehlschlag anderen Punkt klicken (optional mit Wartezeit) |
| `... else key <T>` | Bei Fehlschlag Taste drücken |
| `ins <Nr>` | Nächsten Schritt an Position einfügen (statt am Ende) |
| `ins 0` / `ins end` | Insert-Modus beenden |
| `learn <Name>` | Neuen Punkt erstellen (direkt im Editor) |
| `points` | Alle verfügbaren Punkte anzeigen |
| `del <Nr>` | Schritt löschen |
| `clear` | Alle Schritte löschen |
| `show` | Aktuelle Schritte anzeigen |
| `done` | Phase abschließen und speichern |
| `cancel` | Editor abbrechen (ohne Speichern) |

### Verfügbare Tasten

`enter`, `space`, `tab`, `escape`, `backspace`, `delete`,
`left`, `up`, `right`, `down`,
`f1`-`f12`,
`0`-`9`, `a`-`z`

### Beispiel-Sequenz

```
[INIT: 0] > 1 5           # Punkt 1 klicken, 5s warten
[INIT: 1] > 2 pixel       # Warten bis Farbe erscheint, dann Punkt 2 klicken
[INIT: 2] > key enter     # Enter-Taste drücken
[INIT: 3] > done

[Loop 1: 0] > 3 30-45      # Punkt 3 klicken, 30-45s zufällig warten
[Loop 1: 1] > scan items   # Item-Scan ausführen (bestes pro Kategorie)
[Loop 1: 2] > wait 10-15   # 10-15s zufällig warten ohne Klick
[Loop 1: 3] > 4 gone       # Warten bis Farbe verschwindet, dann Punkt 4 klicken
[Loop 1: 4] > done

Zyklen: 10                 # 10 Durchläufe

[END: 0] > 5 0             # Am Ende: Punkt 5 klicken (z.B. Logout)
[END: 1] > key enter       # Enter drücken
[END: 2] > done
```

### Beispiel mit zeitgesteuertem Loop

```
[INIT: 0] > 1 5            # Login
[INIT: 1] > done

[Loop 1: Sammeln x5]       # Läuft immer (5 Wiederholungen)
  > 2 30-45                 # Ressourcen sammeln
  > 3 0                     # Inventar öffnen
  > done

[Loop 2: Boss x1 [Start: 12:30]]  # Nur um 12:30 Uhr
  > 4 pixel                 # Warte auf Boss-Spawn
  > 5 0                     # Angreifen
  > done

Zyklen: 100

[END: 0] > 6 0              # Logout
[END: 1] > done
```

Loop 1 läuft in jedem Zyklus. Loop 2 wird übersprungen bis 12:30 erreicht ist – dann wird es einmal ausgeführt und danach wieder übersprungen bis zum nächsten Tag.

## Sequenzen zwischen PCs teilen

Sequenzen können auf einen anderen PC kopiert werden (`sequences/`-Ordner). Beim Laden werden die Koordinaten automatisch anhand der **Punkt-Namen** abgeglichen:

- Stimmt ein Name mit einem lokalen Punkt überein → Koordinaten werden aktualisiert
- Fehlt ein Name lokal → Warnung mit Hinweis, den Punkt erst aufzunehmen (CTRL+ALT+A)

So muss man Sequenzen nicht neu erstellen, sondern nur die Punkte einmal lokal aufnehmen.

## Laufzeit-Steuerung

Während eine Sequenz läuft:

- **CTRL+ALT+S** - Stoppt die Sequenz komplett
- **CTRL+ALT+F** - Sanfter Abbruch (aktuellen Zyklus abschließen, dann END-Phase + Stop)
- **CTRL+ALT+G** - Pausiert/Setzt fort (Fortschritt bleibt erhalten)
- **CTRL+ALT+K** - Überspringt die aktuelle Wartezeit

### Timeout-Verhalten bei Farb-Triggern

Wenn ein Farb-Trigger die eingestellte Zeit (`pixel_wait_timeout`, Standard: 300s) überschreitet:

1. **Hat der Schritt ein `else`?** → Das `else` wird ausgeführt (z.B. `else skip`, `else skip_cycle`)
2. **Kein `else` definiert?** → Die globale Fallback-Einstellung `pixel_timeout_action` aus der Config greift

**`pixel_wait_timeout: 0`** deaktiviert den Timeout komplett → wartet unendlich auf die Farbe (nur manueller Skip/Stop beendet)

### Notbremse (Consecutive Timeout)

Wenn ein Farb-Trigger **mehrfach hintereinander** in den Timeout läuft (z.B. weil das Spiel abgestürzt ist), greift die **Notbremse**. Das verhindert, dass der Autoclicker 200x sinnlos den Zyklus neu startet.

**Konfiguration:**
```json
{
  "max_consecutive_timeouts": 5,
  "consecutive_timeout_action": "stop"
}
```

| Option | Beschreibung |
|--------|--------------|
| `max_consecutive_timeouts` | Nach X Timeouts in Folge → Notbremse (`0` = deaktiviert) |
| `consecutive_timeout_action` | Was passiert bei Auslösung (siehe unten) |

**Eskalationsstufen:**

| Wert | Verhalten |
|------|-----------|
| `stop` (Standard) | Sequenz wird gestoppt, Menü bleibt offen |
| `quit` | Menü wird sauber beendet (END-Phase übersprungen) |
| `exit` | Python-Prozess wird sofort beendet (`os._exit`), muss manuell neu gestartet werden |

**Verhalten:**
- Bei jedem Timeout wird der Zähler hochgezählt: `[TIMEOUT] Farbe nicht erkannt nach 300s! (3/5 in Folge)`
- Bei **erfolgreicher** Farberkennung wird der Zähler auf 0 zurückgesetzt
- Die Notbremse greift **vor** der normalen Timeout-Aktion (`pixel_timeout_action`)
- In den Statistiken wird angezeigt ob die Notbremse ausgelöst wurde

### Restart vs. Skip Cycle

| Aktion | Beschreibung |
|--------|-------------|
| `skip` | Überspringt nur **diesen einen Schritt**, nächster Schritt im selben Zyklus läuft weiter |
| `skip_cycle` | Überspringt den **gesamten Zyklus**, nächster Zyklus startet (INIT wird nicht wiederholt) |
| `restart` | **Kompletter Neustart**: INIT-Phase wird erneut ausgeführt, dann Loops von vorne |

### Statistiken

Nach Sequenz-Ende werden Statistiken angezeigt (Einträge erscheinen nur wenn > 0):
```
STATISTIKEN:
  Laufzeit:       1h 23m 45s
  Zyklen:         5
  Klicks:         1234
  Items:          56
  Tasten:         12
  Timeouts:       3
  Notbremse:      Ja (5x in Folge)
  Übersprungen:   2
  Neustarts:      1
```
(Einträge erscheinen nur wenn > 0, Notbremse nur wenn ausgelöst)

### Zeitplan (`CTRL+ALT+Z`)

Startet eine Sequenz zu einem bestimmten Zeitpunkt. Unterstützte Formate:

| Format | Beschreibung |
|--------|-------------|
| `14:30` | Startet um 14:30 Uhr (heute, oder morgen wenn Zeit vorbei) |
| `+30m` | Startet in 30 Minuten (relativ) |
| `+2h` | Startet in 2 Stunden |
| `30m` | Wartet 30 Minuten |
| `2h` | Wartet 2 Stunden |

Der Countdown kann mit `CTRL+ALT+S` abgebrochen werden.

## Item-Scan System

Das Item-Scan System erkennt Items anhand ihrer Marker-Farben oder Templates:

1. **Slots erstellen** (`CTRL+ALT+N` → Menü 1): Bereiche wo Items erscheinen können
2. **Items lernen** (`CTRL+ALT+N` → Menü 2): Mit `learn <Nr>` Marker-Farben + Template scannen
3. **Kategorien zuweisen**: Items gruppieren (z.B. "Hosen", "Jacken")
4. **Scan konfigurieren** (`CTRL+ALT+N` → Menü 3): Slots und Items verknüpfen
5. **In Sequenz nutzen**: `scan <Name>`, `scan <Name> best` oder `scan <Name> every`

### Scan-Modi

| Modus | Beschreibung |
|-------|-------------|
| `scan items` | Bestes Item pro Kategorie (Standard) |
| `scan items best` | Nur 1 Item total (das absolute Beste) |
| `scan items every` | Alle Treffer ohne Filter (für Duplikate) |

**Wann welchen Modus?**
- **all** (Standard): Für Spiele wo jedes Item nur 1x im Inventar erscheint
- **best**: Wenn nur das allerbeste Item geklickt werden soll
- **every**: Für Spiele wo dasselbe Item in mehreren Slots liegen kann

### Beispiel mit Kategorien

Gefundene Items:
- Pinkes Juwel (Kategorie: Juwelen, P1)
- Blaues Juwel (Kategorie: Juwelen, P2)
- Rote Jacke (Kategorie: Jacken, P1)

Ergebnis von `scan items`:
- ✓ Pinkes Juwel wird geklickt (bestes Juwel)
- ✗ Blaues Juwel wird NICHT geklickt (P2 < P1)
- ✓ Rote Jacke wird geklickt (bestes/einziges bei Jacken)

## Bedingte Logik (ELSE)

Für Schritte mit Bedingungen (Scan, Pixel-Trigger) können Fallback-Aktionen definiert werden.

### ELSE-Syntax

| Befehl | Beschreibung |
|--------|--------------|
| `else skip` | **Nur diesen Schritt** überspringen → nächster Schritt läuft normal weiter |
| `else skip_cycle` | **Ganzen Zyklus** abbrechen → nächster Zyklus startet von vorne (ohne INIT) |
| `else restart` | **Komplett neu starten** → inkl. INIT-Phase |
| `else <Nr>` | Anderen Punkt klicken |
| `else <Nr> <Sek>` | Warten, dann anderen Punkt klicken |
| `else key <Taste>` | Taste drücken |

### Unterschied: skip vs. skip_cycle vs. restart

Beispiel-Sequenz mit 3 Schritten in einem Loop:
```
Schritt 1: 1 pixel else ???    ← Farbe wird NICHT erkannt
Schritt 2: 2 5                 ← Punkt 2 klicken nach 5s
Schritt 3: 3 0                 ← Punkt 3 klicken
```

| ELSE-Aktion | Was passiert |
|-------------|-------------|
| `else skip` | Schritt 1 wird übersprungen → **Schritt 2 und 3 laufen trotzdem** |
| `else skip_cycle` | Schritt 1, 2 und 3 werden alle abgebrochen → **nächster Zyklus startet** |
| `else restart` | Alles wird abgebrochen → **INIT wird erneut ausgeführt**, dann Loops von vorne |

### Beispiele

```
scan items else skip           # Wenn kein Item: Schritt überspringen, weiter mit nächstem
scan items else skip_cycle     # Wenn kein Item: ganzen Zyklus abbrechen, nächster startet
scan items else restart        # Wenn kein Item: Sequenz komplett neu starten (inkl. INIT)
scan items else 2              # Wenn kein Item: Punkt 2 klicken
scan items else 2 5            # Wenn kein Item: 5s warten, dann Punkt 2 klicken
1 pixel else skip              # Wenn Timeout: nur diesen Schritt überspringen
1 pixel else skip_cycle        # Wenn Timeout: ganzen Zyklus abbrechen
1 pixel else restart           # Wenn Timeout: von vorne beginnen (inkl. INIT)
1 pixel else key enter         # Wenn Timeout: Enter drücken
wait gone else skip            # Wenn Farbe nicht verschwindet: überspringen
```

### Wann wird ELSE ausgelöst?

- **Item-Scan**: Wenn kein Item gefunden wird
- **Pixel-Trigger**: Wenn Timeout erreicht wird (Standard: 300s, `0` = deaktiviert)
- **Wait Gone**: Wenn Farbe nicht verschwindet

### Was passiert OHNE `else`?

Wenn ein Pixel-Schritt **kein** `else` definiert hat und der Timeout abläuft, greift die **globale Fallback-Einstellung** `pixel_timeout_action` aus der `config.json`:

| Wert | Verhalten |
|------|-----------|
| `skip_cycle` (Standard) | Ganzen Zyklus abbrechen, nächster startet |
| `restart` | Komplett neu starten inkl. INIT |
| `stop` | Sequenz komplett stoppen |

**Wichtig:** Diese Einstellung ist nur ein Sicherheitsnetz. Wenn du bei deinen Pixel-Schritten immer ein `else` definierst (z.B. `else skip` oder `else skip_cycle`), wird `pixel_timeout_action` **nie** verwendet.

## IDE-Kompatibilität (PyCharm, VS Code, etc.)

Das Programm erkennt automatisch die Konsolen-Umgebung und passt sich an:

| Umgebung | Menü-Navigation | Hotkeys | Eingabe |
|----------|----------------|---------|---------|
| **cmd / PowerShell** | Pfeiltasten via `msvcrt.getch()` | Funktionieren | `input()` |
| **PyCharm Run-Konsole** | Pfeiltasten via `GetAsyncKeyState` | Funktionieren | `input()` |
| **Andere IDEs** | Nummern-Eingabe (Fallback) | Funktionieren | `input()` |

Die Hotkeys (`CTRL+ALT+...`) funktionieren **immer**, da sie über `RegisterHotKey` (Windows Messages) laufen.
Die Pfeiltasten-Navigation nutzt in PyCharm `GetAsyncKeyState` aus `user32.dll` - die gleiche Windows API.

## Konfiguration (`config.json`)

Wird beim ersten Start automatisch erstellt:

```json
{
  "clicks_per_point": 1,
  "max_total_clicks": null,
  "click_move_delay": 0.01,
  "post_click_delay": 0.05,
  "failsafe_enabled": true,
  "failsafe_x": 5,
  "failsafe_y": 5,
  "color_tolerance": 0,
  "pixel_wait_tolerance": 10,
  "pixel_wait_timeout": 300,
  "pixel_timeout_action": "skip_cycle",
  "pixel_check_interval": 1,
  "max_consecutive_timeouts": 5,
  "consecutive_timeout_action": "stop",
  "scan_pixel_step": 2,
  "show_pixel_delay": 0.3,
  "scan_reverse": true,
  "scan_click_immediate": false,
  "scan_park_mouse": false,
  "scan_slot_delay": 0.1,
  "item_click_delay": 1.0,
  "marker_count": 5,
  "require_all_markers": true,
  "min_markers_required": 2,
  "slot_hsv_tolerance": 25,
  "slot_inset": 10,
  "slot_color_distance": 25,
  "default_min_confidence": 0.8,
  "default_confirm_delay": 0.5,
  "pause_check_interval": 0.5,
  "debug_mode": false,
  "debug_detection": false,
  "show_pixel_position": false,
  "debug_save_templates": false
}
```

### Klick-Einstellungen

| Option | Beschreibung |
|--------|--------------|
| `clicks_per_point` | Anzahl Klicks pro Punkt (Standard: 1) |
| `max_total_clicks` | Maximale Klicks gesamt (`null` = unendlich) |
| `click_move_delay` | Pause zwischen Mausbewegung und Klick in Sekunden (Standard: 0.01) |
| `post_click_delay` | Pause NACH dem Klick bevor Maus weiterbewegt wird (Standard: 0.05) |

### Sicherheit

| Option | Beschreibung |
|--------|--------------|
| `failsafe_enabled` | Fail-Safe: Maus in Ecke stoppt alles |
| `failsafe_x` | Fail-Safe X-Bereich: Maus x <= Wert löst aus (Standard: 5) |
| `failsafe_y` | Fail-Safe Y-Bereich: Maus y <= Wert löst aus (Standard: 5) |

### Farb-/Pixel-Erkennung

| Option | Beschreibung |
|--------|--------------|
| `color_tolerance` | Toleranz für Item-Scan (0 = exakt, höher = toleranter) |
| `pixel_wait_tolerance` | Toleranz für Pixel-Trigger (niedriger = genauer) |
| `pixel_wait_timeout` | Timeout in Sekunden für Farb-Trigger (Standard: 300, `0` = unendlich) |
| `pixel_timeout_action` | **Nur Fallback** wenn kein `else` definiert: `skip_cycle` (Standard), `restart`, `stop` |
| `pixel_check_interval` | Wie oft auf Farbe prüfen (Sekunden) |
| `max_consecutive_timeouts` | Nach X aufeinanderfolgenden Timeouts → Notbremse (`0` = deaktiviert, Standard: 5) |
| `consecutive_timeout_action` | Notbremse-Aktion: `stop` (Sequenz stoppen), `quit` (Menü beenden), `exit` (Prozess killen) |
| `scan_pixel_step` | Pixel-Schrittweite bei Farbsuche (1=genauer, 2=schneller) |
| `show_pixel_delay` | Wie lange Pixel-Position angezeigt wird in Sekunden (Standard: 0.3) |

### Item-Scan Einstellungen

| Option | Beschreibung |
|--------|--------------|
| `scan_reverse` | Slots von hinten nach vorne scannen |
| `scan_click_immediate` | `true` = Scan→Klick pro Slot (sofort klicken), `false` = alle scannen, dann alle klicken (Standard) |
| `scan_park_mouse` | `true` = Maus zur Bildschirmmitte parken, `[x, y]` = Maus zu bestimmter Position parken, `false` = Maus nicht bewegen (Standard) |
| `scan_slot_delay` | Pause zwischen Slot-Scans in Sekunden (Standard: 0.1) |
| `item_click_delay` | Pause nach Item-Klick in Sekunden (Standard: 1.0) |
| `marker_count` | Anzahl Marker-Farben pro Item (Standard: 5) |
| `require_all_markers` | Alle Marker müssen gefunden werden (true/false) |
| `min_markers_required` | Mindestanzahl Marker wenn `require_all_markers: false` |
| `slot_hsv_tolerance` | HSV-Toleranz für automatische Slot-Erkennung |
| `slot_inset` | Pixel-Einzug vom Slot-Rand für genauere Klick-Position |
| `slot_color_distance` | Farbdistanz für Hintergrund-Ausschluss bei Item-Lernen |
| `default_min_confidence` | Standard-Konfidenz für Template-Matching (Standard: 0.8 = 80%) |
| `default_confirm_delay` | Standard-Wartezeit vor Bestätigungs-Klick in Sekunden (Standard: 0.5) |

### Timing

| Option | Beschreibung |
|--------|--------------|
| `pause_check_interval` | Prüf-Intervall während Pause in Sekunden (Standard: 0.5) |

### Debug-Einstellungen

| Option | Beschreibung |
|--------|--------------|
| `debug_mode` | Zeigt Schritte VOR Start und wartet auf Enter |
| `debug_detection` | Alle Ausgaben persistent (nicht überschrieben) |
| `show_pixel_position` | Maus kurz zum Prüf-Pixel bewegen beim Start |
| `debug_save_templates` | Speichert Scan+Template in `items/debug/` für Debugging |

## Dateistruktur

```
Autoclicker-Idleclans/
├── main.py                 # Einstiegspunkt
├── autoclicker/            # Hauptmodul (~7600 Zeilen)
│   ├── __init__.py
│   ├── config.py           # Konfiguration (Hotkeys, Defaults)
│   ├── models.py           # Datenmodelle (ClickPoint, Sequence, etc.)
│   ├── utils.py            # Hilfsfunktionen (Input, Zeit-Parsing)
│   ├── winapi.py           # Windows API (Maus/Tastatur)
│   ├── imaging.py          # Bildverarbeitung (Screenshots, OpenCV)
│   ├── persistence.py      # Speichern/Laden (JSON)
│   ├── handlers.py         # Hotkey-Handler
│   ├── execution.py        # Sequenz-Ausführung
│   └── editors/            # Interaktive Editoren
│       ├── __init__.py
│       ├── sequence_editor.py
│       ├── item_scan_editor.py
│       ├── item_editor.py
│       └── slot_editor.py
├── config.json             # Konfiguration (auto-generiert)
├── README.md               # Diese Datei
├── sequences/              # Gespeicherte Sequenzen
│   ├── points.json         # Aufgenommene Punkte (mit ID und Name)
│   └── *.json              # Sequenz-Dateien
├── slots/                  # Slot-Konfigurationen
│   ├── slots.json          # Aktive Slots
│   ├── Screenshots/        # Screenshots und Vorschau-Bilder
│   └── presets/            # Slot-Presets
├── items/                  # Item-Konfigurationen
│   ├── items.json          # Aktive Items
│   ├── templates/          # Template-Bilder für Matching
│   ├── debug/              # Debug-Bilder (wenn debug_save_templates=true)
│   └── presets/            # Item-Presets
├── item_scans/             # Item-Scan Konfigurationen
│   └── *.json              # Scan-Konfigurationen (verknüpft Slots + Items)
├── screenshots/            # Sequenz-Screenshots (nach Tag gruppiert)
│   └── YYYY-MM-DD/            # Pro Tag ein Unterordner
└── tools/                  # Hilfswerkzeuge
    ├── sync_json.py        # JSON-Dateien synchronisieren/migrieren
    └── slot_tester.py      # Slot-Erkennung testen
```

## Technische Details

### Architektur

Das Programm ist modular aufgebaut (~7600 Zeilen in 15 Dateien):

```
main.py                      Einstiegspunkt, Event-Loop
    │
    └── autoclicker/
        ├── config.py        Konstanten, Hotkey-IDs
        ├── models.py        Datenklassen (ClickPoint, Sequence, ...)
        ├── utils.py         Hilfsfunktionen (Input, Zeit-Parsing)
        ├── winapi.py        Windows API (Maus, Tastatur, Hotkeys)
        ├── imaging.py       Screenshots, Farberkennung, OpenCV
        ├── persistence.py   JSON-Persistenz, Presets
        ├── handlers.py      Hotkey-Callbacks
        ├── execution.py     Sequenz-Ausführung, Item-Scans
        └── editors/
            ├── sequence_editor.py    Sequenz erstellen/bearbeiten
            ├── item_scan_editor.py   Scans konfigurieren
            ├── item_editor.py        Items definieren
            └── slot_editor.py        Slots definieren
```

**Datenfluss:**
```
[Hotkey] → handlers.py → execution.py → winapi.py (Klicks/Tasten)
                │                   └──→ imaging.py (Screenshots)
                └──→ editors/*.py → persistence.py (Speichern)
```

### Thread-Modell

```
┌──────────────────┐     ┌──────────────────────────────────┐
│   Main Thread    │     │       Worker Thread              │
│                  │     │                                  │
│  Event-Loop:     │     │  sequence_worker():              │
│  - Hotkey-Check  │────►│  - INIT-Phase ausführen (1x)     │
│  - Handler rufen │     │  - LOOP-Phasen wiederholen       │
│                  │◄────│  - END-Phase ausführen           │
│  Events:         │     │                                  │
│  - stop_event    │     │  Prüft Events:                   │
│  - pause_event   │     │  - stop_event → Abbruch          │
│  - skip_event    │     │  - pause_event → Warten          │
│  - quit_event    │     │  - skip_event → Wartezeit skip   │
└──────────────────┘     └──────────────────────────────────┘
                               │
                               │ (nur bei zeitgesteuerten Loops)
                               ▼
                         ┌──────────────────────────────────┐
                         │       Timer Thread (Daemon)      │
                         │                                  │
                         │  _schedule_watcher():             │
                         │  - Prüft alle 10s die Uhrzeit    │
                         │  - Setzt pending-Flag wenn Zeit  │
                         │    erreicht (thread-safe)         │
                         │  - Verhindert Doppel-Ausführung   │
                         │    pro Tag                        │
                         │  - Stoppt mit stop_event          │
                         └──────────────────────────────────┘
```

### Abhängigkeiten

| Paket | Funktion | Erforderlich |
|-------|----------|--------------|
| ctypes (builtin) | Windows API, Hotkeys, Maus/Tastatur | Ja |
| Pillow | Screenshots, Farberkennung | Optional |
| NumPy | Optimierte Farberkennung | Optional |
| OpenCV | Template Matching, Slot-Erkennung | Optional |

### Technologien

- Windows API via `ctypes` (keine externen Abhängigkeiten für Basis-Funktionen)
- Pillow für Screenshot und Farberkennung (optional)
- OpenCV für automatische Slot-Erkennung und Template Matching (optional)
- Globale Hotkeys über `RegisterHotKey`
- Mausklicks und Tastatureingaben über `SendInput`
- BitBlt für Game-Screenshots (funktioniert mit Hardware-Beschleunigung/DirectX)
- Thread-basierte Ausführung mit Events für Synchronisation
- JSON-Persistenz für alle Daten
- Multi-Monitor Unterstützung (DPI-aware)
- Sichere Dateinamen (Path-Traversal-Schutz)
- IDE-Kompatibel: `GetAsyncKeyState`-Polling als Fallback für Pfeiltasten in PyCharm/IDE-Konsolen

## Tools

### Sync-Tool (`tools/sync_json.py`)

Bringt alle JSON-Dateien auf den aktuellen Code-Stand:

```bash
python tools/sync_json.py
```

- Fehlende Felder mit Standardwerten ergänzen
- Alte Formate konvertieren (z.B. `confirm_point` int → Koordinaten)
- Presets erben Werte von globalen Dateien

### Slot-Tester (`tools/slot_tester.py`)

Testet die automatische Slot-Erkennung mit Debug-Ausgaben:

```bash
python tools/slot_tester.py
```

## Changelog

### Neueste Änderungen

- **Zeitgesteuerte Loops**: Loop-Phasen können an eine Uhrzeit gebunden werden (z.B. `12:30`). Ein Daemon-Thread überwacht die Zeit im Hintergrund und setzt ein Pending-Flag – normale Loops laufen weiter, der zeitgesteuerte Loop wird nur an seiner natürlichen Position ausgeführt. Neuer `time <Nr>` Befehl im Loop-Editor.

### Vorherige Änderungen

- **Notbremse (Consecutive Timeout)**: Stoppt automatisch nach X aufeinanderfolgenden Timeouts (`max_consecutive_timeouts`). Drei Eskalationsstufen: `stop`, `quit`, `exit` (Prozess killen)
- **Config-Validierung**: Ungültige Werte in `config.json` werden automatisch korrigiert mit Warnung (z.B. negative Timeouts, unbekannte Aktions-Strings)
- **Race Condition Fix**: Alle Zugriffe auf `state.active_sequence` sind jetzt thread-safe unter Lock
- **PILLOW-Guard**: Farb-Trigger bricht sofort ab wenn Pillow nicht installiert ist (statt sinnlos zu loopen)
- **Bounds-Checks**: Region-Validierung bei Screenshots (BitBlt, ImageGrab, Region-Auswahl)
- **GDI Cleanup**: Jeder GDI-Resource-Cleanup einzeln abgesichert (kein Überspringen bei Fehler)
- **String-Konstanten**: `ELSE_SKIP`, `SCAN_MODE_ALL` etc. zentral definiert (verhindert Tippfehler)
- **Screenshot-Ordner**: Session-Start-Datum statt `datetime.now()` (ein Ordner pro Session, auch über Mitternacht)
- **scan_park_mouse**: Nutzt Virtual Screen Metrics für echte Bildschirmmitte (Multi-Monitor-kompatibel)
- **NumPy-Optimierung**: `np.asarray` (Zero-Copy) + quadrierte Distanz ohne `sqrt`

### Vorherige Änderungen

- **Checkbox-Ansicht**: `show`/`s` im Scan-Editor zeigt `[X]`/`[ ]` für zugewiesene Slots/Items
- **Screenshots nach Tag**: Sequenz-Screenshots werden nach Tag gruppiert (`YYYY-MM-DD/`) statt pro Session
- **Auto-Template**: `learn` erstellt Templates automatisch (kein manuelles Bestätigen mehr)
- **Maus parken: true**: `scan_park_mouse: true` parkt die Maus zur Bildschirmmitte (zusätzlich zu `[x, y]`)
- **Immediate Scan-Modus**: `scan_click_immediate: true` scannt und klickt jeden Slot einzeln (Scan→Klick→Scan→Klick) statt alle zu scannen und dann zu klicken
- **Maus parken vor Scan**: `scan_park_mouse: [x, y]` bewegt die Maus vor dem Scannen weg, damit Tooltips/Hover-Effekte den Screenshot nicht stören
- **Farbige Ausgaben überall**: Alle `[DEBUG]`-, `[PAUSE]`- und Menü-Ausgaben sind jetzt farbig (nicht nur der Worker)
- **Restart = Kompletter Neustart**: `restart` führt jetzt INIT-Phase erneut aus (nicht nur Loops)
- **Erweiterte Statistiken**: Timeouts, übersprungene Zyklen und Neustarts werden gezählt und angezeigt
- **Unendliches Warten**: `pixel_wait_timeout: 0` deaktiviert den Timeout (wartet unendlich auf Farbe)
- **Standard-Timeout-Aktion**: `pixel_timeout_action` Default von `stop` auf `skip_cycle` geändert
- **Verbesserte Konsolen-Hilfe**: Ausführliche Schritt-für-Schritt-Anleitung beim Programmstart

### Vorherige Änderungen

- **INIT-Phase**: Einmalige Initialisierung vor allen Zyklen (ersetzt START-Phase)
- **Sanfter Abbruch** (`CTRL+ALT+F`): Aktuellen Zyklus abschließen, dann END-Phase ausführen und stoppen
- **Item-Sortierung**: Items werden nach Priorität (aufsteigend) innerhalb jeder Kategorie sortiert
- **Save-on-Done**: Item-Editor speichert nur bei `done`, verwirft Änderungen bei `cancel`/Abbruch
- **Separate Screenshot-Ordner**: Slot-Screenshots in `slots/Screenshots/`, Sequenz-Screenshots in `screenshots/<Session>/`
- **Bug-Fix**: `IndexError` wenn alle Items durch Kategorie-Filter herausgefiltert wurden

### Vorherige Änderungen

- **Sequenz-Remap**: Koordinaten werden beim Laden automatisch anhand der Punkt-Namen abgeglichen — ideal für PC-Wechsel
- **Auto-Start nach Laden**: CTRL+ALT+S startet die Sequenz direkt nach dem Laden (kein zweiter Tastendruck nötig)
- **Insert-Modus**: `ins <Nr>` im Sequenz-Editor fügt Schritte an beliebiger Position ein
- **ESC-Abbruch**: ESC-Taste funktioniert als Abbruch in allen Editoren (auch in PyCharm)
- **ANSI-Farben**: Farbige Tags in der Konsole ([FEHLER] rot, [INFO] cyan, [OK] grün)
- **Einheitliche Delay-Validierung**: Wartezeiten werden in allen Editoren gleich geprüft
- **Template Auto-Resize**: Templates werden bei Größenunterschied automatisch skaliert
- **Bug-Fixes**: Buchstaben-Verdoppelung in PyCharm, Debug-Mode Inkonsistenzen, Wartezeit-Anzeige

### Vorherige Änderungen

- **PyCharm/IDE-Support**: Pfeiltasten-Navigation funktioniert jetzt auch in IDE-Konsolen
- **Verbesserte Benutzereingabe**: Robustes Input-Handling für alle Konsolen-Typen
- **Modulare Architektur**: Code in 15 Dateien aufgeteilt
- **Code-Qualität**: Duplizierung entfernt, toter Code bereinigt

### Ältere Änderungen

- **Bulk-Learn**: `learn 1-5` lernt mehrere Items auf einmal mit gemeinsamen Einstellungen
- **Kategorie-System**: Items gruppieren (Hosen, Jacken, Juwelen) - nur bestes pro Kategorie klicken
- **Template-Matching**: Items per Screenshot erkennen (OpenCV)
- **Scan-Modi**: `all` (Standard), `best` (nur 1 Item), `every` (alle Treffer)
- **ELSE-Aktionen**: `else skip`, `else restart`, `else key` bei Fehlschlag
- **Preset-System**: Slots und Items als benannte Presets speichern
- **Step-Editor**: `learn` und `points` Befehle direkt im Sequenz-Editor
- **Konfigurierbare Delays**: `scan_slot_delay`, `item_click_delay`, Fail-Safe Zone
- **Screenshot-Optimierung**: BitBlt für DirectX-Spiele
- **Sicherheit**: Path-Traversal-Schutz, Bounds-Checking
- **Unicode-Support**: Templates mit Umlauten (ü, ä, ö)

## Lizenz

MIT License
