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
- **Auto-Scan Items**: Alle Slots automatisch scannen und Items in einem Schritt erstellen (`autoscan`)
- **Kategorie-System**: Items gruppieren (z.B. Hosen, Jacken) - nur bestes pro Kategorie klicken
- **Template-Matching**: Items per Screenshot erkennen (OpenCV)
- **Boss-Scan**: Bosse anhand von Templates oder Markern erkennen + Aktion auslösen (Klick, Taste, Item-Scan, Skip)
- **Icon-Scan**: Ein Symbol/Icon (z.B. rotes „!" einer nicht machbaren Mission) per Template/Marker erkennen + Aktion (Klick/Taste/Skip)
- **LLM Vision Boss-Detection**: Lokale LLMs (Ollama / LM Studio) erkennen Bosse per Screenshot, unbekannte Bosse werden auto-gespeichert
- **LLM Reasoning**: Optionaler Reasoning-Modus für bessere Erkennungsgenauigkeit (Ollama: `think: true`, LM Studio: `reasoning_effort: high`)
- **Boss-Watcher**: Step der kontinuierlich auf einen Boss wartet und beim Erscheinen reagiert
- **Window-Fokus-Check**: Klicks gehen nur ins Spielfenster - bei Tab-Out wird pausiert (oder gestoppt)
- **Humanization**: Klick-Jitter, zufällige Mikro-Delays, periodische Pausen für menschlicheres Verhalten
- **Session-Log (CSV)**: Vollständiges Log aller Klicks/Tasten/Events pro Sequenz für Auswertung
- **Import/Export**: Komplettes Setup als ZIP exportieren und auf anderen PCs importieren — Koordinaten werden automatisch an die Spielfenster-Größe angepasst (Fallback: 2-Punkt-Remapping); nach dem Import wird gewarnt, wenn Klick-Ziele außerhalb des Fensters liegen
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

| Paket | Funktion | Erforderlich |
|-------|----------|:---:|
| `pillow` | Screenshots, Farberkennung | Nein |
| `numpy` | Optimierte Farberkennung | Nein |
| `opencv-python` | Template-Matching, Slot-Erkennung | Nein |
| `easyocr` | OCR Texterkennung für Boss-Namen | Nein |
| `torch` | Abhängigkeit von EasyOCR | Nein |
| `torchvision` | Abhängigkeit von EasyOCR | Nein |
| `pytesseract` | Alternative OCR-Engine (+ Tesseract-Binary) | Nein |

## Installation

```bash
git clone https://github.com/r3flexone/Autoclicker-Idleclans.git
cd Autoclicker-Idleclans
python main.py
```

### Minimale Installation (nur Grundfunktionen)

Klicken, Hotkeys, Sequenzen — keine Bilderkennung:

```bash
python main.py
```

Keine zusätzlichen Pakete nötig.

### Empfohlen (Farberkennung + Template-Matching)

```bash
pip install -r requirements-minimal.txt
python main.py
```

### Alle Features (inkl. OCR Boss-Erkennung)

**Ohne GPU (CPU-only):**
```bash
pip install -r requirements.txt
python main.py
```

**Mit NVIDIA GPU (schneller):**

Zuerst CUDA-Version von PyTorch installieren — passend zur CUDA-Version deiner GPU (`nvidia-smi` zeigt sie oben rechts):

| CUDA-Version | Befehl |
|---|---|
| 12.4+ | `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124` |
| 12.1 | `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121` |
| 11.8 | `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118` |

> **Hinweis für Python 3.13**: Nur `cu124` wird unterstützt. `cu121` und älter haben keine Python-3.13-Wheels.

Dann den Rest installieren:
```bash
pip install -r requirements.txt
python main.py
```

**Alternative OCR: Tesseract**
```bash
pip install pytesseract
# + Tesseract-Binary: https://github.com/UB-Mannheim/tesseract/wiki
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
| `CTRL+ALT+I` | Import/Export (Setup teilen mit automatischem Remapping) |

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
- **[4] Boss-Scans bearbeiten** - Bosse erkennen + Aktion auslösen (siehe Boss-Scan-Sektion)
- **[5] Icon-Scans bearbeiten** - Symbol/Icon erkennen + Aktion auslösen (siehe Icon-Scan-Sektion)
- **[6] Auto-Scan** - Slots scannen + Items + Scan in einem Workflow erstellen
- **[7] Import / Export** - Setup als ZIP teilen oder importieren

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
| `autoscan` | **Alle Slots automatisch scannen + Items mit Templates + Markern erstellen** (Duplikate werden via Template-Match übersprungen) |
| `autoscan nocolor` | Auto-Scan nur mit Templates (keine Marker-Farben) |
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

### Auto-Scan (`autoscan`)

Der schnellste Weg, viele Items auf einmal anzulegen — perfekt für ein vollständiges Inventar:

1. Slots vorab definieren (am besten via `auto` im Slot-Editor)
2. `autoscan` im Item-Editor (oder Menü-Punkt 5 im Item-Scan-Menü)
3. Einmalig konfigurieren: Kategorie, Prioritäts-Modus, Bestätigungs-Punkt, Konfidenz, Marker an/aus
4. Programm scannt alle Slots, vergleicht gegen bestehende Items (Duplikate werden übersprungen) und legt für jeden neuen Slot ein Item mit Template + Marker-Farben an
5. Anschließend nur noch via `rename <Nr>` umbenennen

**Modi:**
- `autoscan` — Templates + Marker-Farben (Standard, robust)
- `autoscan nocolor` — Nur Templates, keine Marker (schneller wenn die Items sehr unterschiedlich aussehen)

**Prioritäten:**
- **[1] Automatisch** — Slot-Reihenfolge bestimmt P1, P2, P3, ... (frühere Slots bevorzugt)
- **[2] Alle gleich (P1)** — Bei gleicher Kategorie entscheidet die Scan-Reihenfolge

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
| `boss <Name>` | Boss-Scan ausführen (einmalig prüfen, dann Aktion oder ELSE/Default) |
| `watcher <Name>` | Boss-Watcher: wartet kontinuierlich bis ein Boss erscheint, dann Aktion |
| `icon <Name>` | Icon-Scan: Symbol/Icon (z.B. rotes „!") in Region erkennen → Aktion (Klick/Taste/Skip) |
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

## Boss-Scan System

Boss-Scans erkennen einen Boss in einer fest definierten Region und lösen eine zugeordnete Aktion aus (Klick, Taste, Item-Scan, Skip, Restart). Erstellung über das Item-Scan-Menü → **[4] Boss-Scans bearbeiten**.

### Boss-Profil

Ein `BossProfile` definiert wie ein Boss erkannt wird und was passieren soll:

- **Erkennung**: Marker-Farben (wie bei Items) und/oder Template (Screenshot), optional mit LLM Vision oder OCR-Texterkennung
- **Aktion**: `scan` (Item-Scan starten), `click` (an Position klicken), `key` (Taste drücken), `skip` (Step übergehen), `skip_cycle` (Zyklus abbrechen), `restart` (Sequenz neu starten)
- **Action-Delay**: Wartezeit vor der Aktion

### Verwendung in Sequenzen

| Befehl | Verhalten |
|--------|-----------|
| `boss <Name>` | Einmaliger Scan. Wenn nichts erkannt → ELSE-Action oder Default-Action |
| `watcher <Name>` | Wartet in Schleife (alle `llm_watcher_interval` Sekunden) bis ein Boss erkannt wird, dann Aktion |

**Boss-Watcher Exit-Bedingungen:**
- `llm_watcher_max_scans` — nach N Scans ohne Treffer abbrechen (`0` = unbegrenzt)
- `llm_watcher_timeout` — nach X Sekunden abbrechen (`0` = unbegrenzt)
- `CTRL+ALT+S` (Sequenz stoppen) bricht den Watcher ebenfalls ab

### LLM Vision Boss-Detection

Optional kann ein lokales Vision-LLM (Ollama oder LM Studio) Bosse anhand des Screenshots erkennen — besonders nützlich wenn Templates/Marker zu unzuverlässig sind oder neue Bosse automatisch entdeckt werden sollen.

**Voraussetzungen:**
- **Ollama**: Installation von [ollama.com](https://ollama.com), dann ein Vision-Modell laden:
  ```bash
  ollama pull llava           # Standard, schnell
  ollama pull moondream       # Kleiner, oft schneller
  ollama pull bakllava        # Alternative
  ```
- **LM Studio**: App starten, ein LLaVA-kompatibles Modell laden, lokalen Server aktivieren

**Aktivierung pro Boss-Scan:**
Im Boss-Scan-Editor → SCHRITT 5 (LLM Vision):
- `use_llm: true` aktiviert LLM für diesen Scan
- `llm_fallback: true` → LLM nur wenn Templates/Marker nichts finden (sicher, schnell)
- `llm_fallback: false` → LLM **primär** statt Templates/Marker (langsam, aber flexibel)

**SCHRITT 6 (OCR Texterkennung):**
- `use_ocr: true` aktiviert OCR für diesen Scan (EasyOCR oder Tesseract)
- `ocr_fallback: true` → OCR nur wenn Templates/Marker/LLM nichts finden (Fallback)
- `ocr_fallback: false` → OCR **primär** für Texterkennung (schneller als LLM für reine Texterkennung)

**Globale Einstellungen** (`config.json`):

| Feld | Standard | Beschreibung |
|---|---|---|
| `llm_enabled` | `false` | LLM-Erkennung global aktivieren |
| `llm_provider` | `"lmstudio"` | `"ollama"` oder `"lmstudio"` |
| `llm_model` | `"google/gemma-4-12b-qat"` | Modell-Name (Provider-Fallbacks: `"gemma3n:e4b"` für Ollama / `"google/gemma-4-12b-qat"` für LM Studio) |
| `llm_timeout` | `60` | Timeout pro Anfrage in Sekunden |
| `llm_retry_count` | `2` | Wiederholungen bei `KEIN_BOSS` (0 = kein Retry, 2 = 3 Versuche gesamt) |
| `llm_async` | `false` | Boss-Scan/Watcher im Hintergrund-Thread — Sequenz läuft parallel weiter |
| `llm_boss_prompt` | `null` | Custom-Prompt (null = eingebauter OCR-Analyst-Prompt) |

**`llm_async` — Nicht-blockierender Modus:**
Wenn aktiviert, startet der Boss-Scan/Watcher-Step einen Hintergrund-Thread und kehrt sofort zurück. Die Sequenz läuft parallel weiter — `Warte 20s`-Steps und andere Klicks werden nicht verzögert. Sobald der LLM-Thread die Boss-Aktion ausführt, pausiert der Sequenz-Worker kurz bis die Klicks abgeschlossen sind.

> **Hinweis:** Im async-Modus wird `else_config` (ELSE-Aktion bei "kein Boss") ignoriert, da die Sequenz zu diesem Zeitpunkt bereits weitergelaufen ist.

**Auto-Save unbekannter Bosse**: Wenn das LLM einen Boss-Namen nennt, der noch nicht in der Liste ist, wird er automatisch als neuer Boss mit `action: skip` gespeichert. Du musst nur noch eine Aktion zuweisen.

**Standalone-Test**: `python tools/test_llm.py` testet Bilderkennung ohne den Autoclicker:
```bash
python tools/test_llm.py             # Verbindungstest + interaktiver Screenshot-Modus
python tools/test_llm.py screenshot  # Einmal-Screenshot direkt analysieren
```

### OCR Texterkennung Boss-Detection

Alternative zu LLM Vision: Lokale OCR-Engine (EasyOCR oder Tesseract) für schnelle, deterministische Texterkennung von Boss-Namen. Besonders nützlich wenn Boss-Namen als Text im Screenshot stehen.

**Voraussetzungen:**
- **EasyOCR**: `pip install easyocr` (empfohlen, GPU-Unterstützung möglich)
- **Tesseract**: `pip install pytesseract` + [Tesseract-Installation](https://github.com/UB-Mannheim/tesseract/wiki)

**Vorteile gegenüber LLM:**
- Schneller (kein HTTP-Request, lokal)
- Determinisitsch (gleiche Eingabe = gleiche Ausgabe)
- Ressourcenschonend
- Gut für pure Text-Erkennung

**Vorteile von LLM:**
- Flexibel (versteht Kontext, Symbole, Layouts)
- Kein Trainieren nötig
- Bessere Genauigkeit bei komplizierten Layouts

**Aktivierung pro Boss-Scan:**
Im Boss-Scan-Editor → SCHRITT 6 (OCR Texterkennung):
- `use_ocr: true` aktiviert OCR für diesen Scan
- `ocr_fallback: true` → OCR nur als Fallback wenn Templates/Marker/LLM nichts finden
- `ocr_fallback: false` → OCR **primär** (vor LLM/Templates)

**Globale Einstellungen** (`config.json`):
- `ocr_enabled: true` muss zusätzlich gesetzt sein
- `ocr_backend: null` (Auto-Detect) oder `"easyocr"` / `"tesseract"`
- `ocr_languages: "en"` (kommasepariert, z.B. `"en,de"` für English + Deutsch)
- `ocr_min_confidence: 0.3` (Mindest-Konfidenz 0-1)

**Standalone-Test**: `python tools/test_ocr.py` testet OCR-Backends und Texterkennung:
```bash
python tools/test_ocr.py                        # Backend-Status + Region wählen
python tools/test_ocr.py test                   # Nur Backend-Verfügbarkeit prüfen
python tools/test_ocr.py bild.png               # Bild-Datei analysieren
python tools/test_ocr.py --region 100,200,800,600   # Region direkt angeben
python tools/test_ocr.py --bosses "Dragon,Goblin"   # Gegen Boss-Namen matchen
```

## Icon-Scan System

Icon-Scans erkennen ein **einzelnes Symbol/Icon** in einer Region und lösen eine Aktion aus — gedacht für Status-Marker wie ein rotes „!", das z.B. eine nicht machbare Mission kennzeichnet. Im Gegensatz zum Item-Scan wird nichts „eingesammelt": es ist eine reine *erkennen → handeln*-Logik ohne Slots, Kategorien oder LLM. Erstellung über das Item-Scan-Menü → **[5] Icon-Scans bearbeiten**.

Eine `IconScanConfig` definiert:

- **Region**: wo gesucht wird (eng ums Icon legen — robuster fürs Template-Matching)
- **Erkennung**: Template-Bild (OpenCV) **oder** Farb-Marker (mit `color_tolerance`). Für Farb-Marker empfiehlt sich `scan_marker_min_pixels > 1`, damit einzelne Rausch-Pixel nicht auslösen.
- **Aktion** bei Fund: `click` (Standard, z.B. „Ablehnen"-Button), `key` (Taste), `skip` (nur erkennen), `skip_cycle` (Zyklus abbrechen), `restart` (Sequenz neu starten) — mit optionalem Action-Delay.

### Verwendung in Sequenzen

| Befehl | Verhalten |
|--------|-----------|
| `icon <Name>` | Region prüfen. Icon erkannt → Aktion. Nicht erkannt → ELSE-Action oder Schritt überspringen |

**Beispiel** — eine nicht machbare Mission am roten „!" erkennen und ablehnen:
1. Item-Scan-Menü → **[5] Icon-Scans bearbeiten** → Neuen Icon-Scan erstellen
2. Region eng um das „!" wählen, Template aufnehmen (oder Farb-Marker des Rots setzen)
3. Aktion „Punkt klicken" → auf den „Ablehnen/Abbrechen"-Button
4. Im Sequenz-Editor: `icon MeinIcon`

## Sicherheit & Tarnung

Drei Features für längere unbeaufsichtigte Sessions, alle deaktivierbar.

### Window-Fokus-Check

Verhindert dass Klicks in andere Fenster (Browser, Chat, IDE) gehen wenn man weg-tabbed.

```json
{
  "window_focus_check": true,
  "window_focus_title": "Idle Clans",
  "window_focus_action": "pause"
}
```

- Vor jedem Klick/Tastendruck wird der Titel des aktiven Fensters geprüft (case-insensitive Substring-Match)
- `window_focus_action: "pause"` — wartet bis das Fenster wieder vorne ist
- `window_focus_action: "stop"` — bricht die Sequenz sauber ab

### Humanization

Macht das Klick-Muster für Anti-Bot-Detection schwerer erkennbar.

```json
{
  "humanize_enabled": true,
  "humanize_click_jitter": 3,
  "humanize_micro_delay_min": 0.05,
  "humanize_micro_delay_max": 0.15,
  "humanize_break_interval_min": 45,
  "humanize_break_duration_min": 2,
  "humanize_break_duration_max": 5
}
```

- **Klick-Jitter**: ±N Pixel Zufalls-Offset um die Ziel-Koordinaten
- **Mikro-Delays**: Zufällige Wartezeit (min-max Sekunden) **vor** jedem Klick/Tastendruck
- **Periodische Pausen**: Alle X Minuten eine Pause von Y bis Z Minuten Länge (humanize_break_*)

### Session-Log (CSV)

Schreibt jede Aktion in eine CSV-Datei pro Sequenz-Start.

```json
{
  "session_log_enabled": true,
  "session_log_dir": "logs"
}
```

Pro Session entsteht eine Datei `logs/YYYY-MM-DD_HHMMSS_<Sequenz>.csv` mit Spalten:
`timestamp, elapsed_sec, event, detail, x, y, extra`

**Geloggte Events**: `session_start`, `session_end`, `click`, `key`, `focus_lost_pause`, `focus_lost_stop`, `focus_restored`, `humanize_break_start`, `humanize_break_end`. Auch unerwartete LLM-Boss-Detections werden als Events sichtbar.

Nützlich für: Items/Stunde-Auswertung, "warum hat der Bot heute weniger gemacht als gestern", Debugging von Sequenz-Aussetzern.

## Setup importieren / exportieren (`CTRL+ALT+I`)

Komplettes Setup als ZIP zwischen PCs (oder mit anderen Spielern) teilen. **Koordinaten werden automatisch an den Ziel-Bildschirm angepasst**.

### Export

1. `CTRL+ALT+I` → "Exportieren (alles)" oder "Exportieren (mit Auswahl)"
2. Bei "mit Auswahl": Pro Bereich (Punkte/Sequenzen/Slots/Items/Item-Scans/Boss-Scans/Icon-Scans/Config) Ja/Nein
3. **Referenz für die Koordinaten-Anpassung**:
   - Wird das Spielfenster (Titel aus `window_focus_title`, Standard „Idle Clans") gefunden, wird seine **Client-Größe automatisch** als Referenz genommen — kein manuelles Klicken nötig.
   - Andernfalls (Fenster nicht offen/gefunden): **zwei Referenzpunkte manuell setzen** (Maus an die Stelle bewegen, Enter) — z.B. Oben-Links und Unten-Rechts im Spielfenster.
4. Dateiname vergeben (Default: `autoclicker_export_<timestamp>.zip`)
5. ZIP wird in `exports/` gespeichert
6. Anleitung für den Empfänger wird angezeigt

Das ZIP enthält: `manifest.json` (inkl. Spielfenster-Größe falls erkannt), alle JSON-Daten, gepackte Template-PNGs, optional die Config (gefiltert).

### Import

1. Empfänger legt die ZIP-Datei in `exports/` (oder ins Hauptverzeichnis)
2. `CTRL+ALT+I` → "Importieren"
3. Datei aus der Liste auswählen
4. Inhalt der ZIP wird angezeigt + Referenzpunkte des Exporters
5. **Anpassungs-Modus wählen**:
   - Enthält das Export-Manifest die Spielfenster-Größe **und** das Spielfenster läuft gerade:
     - **[1] Automatisch aus Fenstergröße** (empfohlen) → Skalierung wird aus Export- vs. aktueller Fenstergröße berechnet, kein Klicken nötig
     - **[2] Manuell** (zwei Punkte klicken, gleiche Stellen wie der Exporter)
     - **[3] 1:1** (gleicher Bildschirm)
   - Sonst (kein Fenster-Rect / Fenster nicht gefunden): **[1] Remapping** (zwei Punkte manuell) oder **[2] 1:1**
6. Pro Bereich Ja/Nein wählen was importiert werden soll
7. **Merge** (bestehende Daten behalten + ergänzen) oder **Ersetzen**

### Wie das Remapping funktioniert

Egal ob fenster-basiert (automatisch) oder per Hand: aus zwei Referenzpunkt-Paaren (Quelle → Ziel) berechnet das Programm Skalierung und Verschiebung. Bei der automatischen Variante sind die zwei Punkte die obere-linke und untere-rechte Ecke des Spielfenster-Client-Bereichs.
- `scale_x = (dst2.x - dst1.x) / (src2.x - src1.x)` (analog für Y)
- `offset_x = dst1.x - src1.x * scale_x`

Diese Transformation wird auf **alle** Koordinaten angewendet: Klick-Punkte, Scan-Regionen, Boss-Regionen, Wait-Pixel, Confirm-Points, Screenshot-Regionen, Else-Klick-Positionen.

**Tipp**: Nutze als Referenzpunkte feste UI-Elemente die auf jedem Bildschirm leicht zu finden sind — z.B. die Ecken des Spielfensters oder feste Buttons.

## Sequenzen zwischen PCs teilen (Legacy)

> **Hinweis**: Für komplette Setups bevorzugt das oben beschriebene Import/Export-System (`CTRL+ALT+I`) verwenden. Der hier beschriebene Weg funktioniert weiter, deckt aber nur Sequenzen ab.

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
  "click_per_point": 1,
  "click_max_total": null,
  "click_move_delay": 0.01,
  "click_post_delay": 0.05,
  "failsafe_enabled": true,
  "failsafe_x": 5,
  "failsafe_y": 5,
  "pixel_wait_tolerance": 10,
  "pixel_wait_timeout": 300,
  "pixel_timeout_action": "skip_cycle",
  "pixel_check_interval": 1,
  "pixel_max_consecutive_timeouts": 5,
  "pixel_consecutive_action": "stop",
  "pixel_show_delay": 0.3,
  "scan_reverse": true,
  "scan_click_immediate": false,
  "scan_park_mouse": false,
  "scan_slot_delay": 0.1,
  "scan_item_click_delay": 1.0,
  "scan_marker_count": 5,
  "scan_require_all_markers": true,
  "scan_min_markers_required": 2,
  "scan_marker_min_pixels": 1,
  "scan_slot_hsv_tolerance": 25,
  "scan_slot_inset": 10,
  "scan_slot_color_distance": 25,
  "scan_min_confidence": 0.8,
  "scan_confirm_delay": 0.5,
  "llm_enabled": false,
  "llm_provider": "lmstudio",
  "llm_endpoint": null,
  "llm_model": "google/gemma-4-12b-qat",
  "llm_timeout": 30,
  "llm_reasoning": false,
  "llm_max_tokens": 0,
  "llm_boss_prompt": null,
  "llm_watcher_interval": 5.0,
  "llm_watcher_max_scans": 0,
  "llm_watcher_timeout": 0,
  "ocr_enabled": false,
  "ocr_backend": null,
  "ocr_languages": "en",
  "ocr_min_confidence": 0.3,
  "window_focus_check": false,
  "window_focus_title": "Idle Clans",
  "window_focus_action": "pause",
  "humanize_enabled": false,
  "humanize_click_jitter": 0,
  "humanize_micro_delay_min": 0.0,
  "humanize_micro_delay_max": 0.0,
  "humanize_break_interval_min": 0,
  "humanize_break_duration_min": 0,
  "humanize_break_duration_max": 0,
  "session_log_enabled": false,
  "session_log_dir": "logs",
  "timing_pause_interval": 0.5,
  "debug_mode": false,
  "debug_detection": false,
  "debug_show_pixel_position": false,
  "debug_save_templates": false
}
```

### Klick-Einstellungen

| Option | Beschreibung |
|--------|--------------|
| `click_per_point` | Anzahl Klicks pro Punkt (Standard: 1) |
| `click_max_total` | Maximale Klicks gesamt (`null` = unendlich) |
| `click_move_delay` | Pause zwischen Mausbewegung und Klick in Sekunden (Standard: 0.01) |
| `click_post_delay` | Pause NACH dem Klick bevor Maus weiterbewegt wird (Standard: 0.05) |

### Sicherheit

| Option | Beschreibung |
|--------|--------------|
| `failsafe_enabled` | Fail-Safe: Maus in Ecke stoppt alles |
| `failsafe_x` | Fail-Safe X-Bereich: Maus x <= Wert löst aus (Standard: 5) |
| `failsafe_y` | Fail-Safe Y-Bereich: Maus y <= Wert löst aus (Standard: 5) |

### Farb-/Pixel-Erkennung

| Option | Beschreibung |
|--------|--------------|
| `pixel_wait_tolerance` | Toleranz für Pixel-Trigger (niedriger = genauer) |
| `pixel_wait_timeout` | Timeout in Sekunden für Farb-Trigger (Standard: 300, `0` = unendlich) |
| `pixel_timeout_action` | **Nur Fallback** wenn kein `else` definiert: `skip_cycle` (Standard), `restart`, `stop` |
| `pixel_check_interval` | Wie oft auf Farbe prüfen (Sekunden) |
| `pixel_max_consecutive_timeouts` | Nach X aufeinanderfolgenden Timeouts → Notbremse (`0` = deaktiviert, Standard: 5) |
| `pixel_consecutive_action` | Notbremse-Aktion: `stop` (Sequenz stoppen), `quit` (Menü beenden), `exit` (Prozess killen) |
| `pixel_show_delay` | Wie lange Pixel-Position angezeigt wird in Sekunden (Standard: 0.3) |

### Item-Scan Einstellungen

| Option | Beschreibung |
|--------|--------------|
| `scan_reverse` | Slots von hinten nach vorne scannen |
| `scan_click_immediate` | `true` = Scan→Klick pro Slot (sofort klicken), `false` = alle scannen, dann alle klicken (Standard) |
| `scan_park_mouse` | `true` = Maus zur Bildschirmmitte parken, `[x, y]` = Maus zu bestimmter Position parken, `false` = Maus nicht bewegen (Standard) |
| `scan_slot_delay` | Pause zwischen Slot-Scans in Sekunden (Standard: 0.1) |
| `scan_item_click_delay` | Pause nach Item-Klick in Sekunden (Standard: 1.0) |
| `scan_marker_count` | Anzahl Marker-Farben pro Item (Standard: 5) |
| `scan_require_all_markers` | Alle Marker müssen gefunden werden (true/false) |
| `scan_min_markers_required` | Mindestanzahl Marker wenn `scan_require_all_markers: false` |
| `scan_marker_min_pixels` | Min. passende Pixel pro Marker-Farbe (Standard 1; höher = robuster gegen einzelne Rausch-Pixel, z.B. für ein rotes „!"-Icon) |
| `scan_slot_hsv_tolerance` | HSV-Toleranz für automatische Slot-Erkennung |
| `scan_slot_inset` | Pixel-Einzug vom Slot-Rand für genauere Klick-Position |
| `scan_slot_color_distance` | Farbdistanz für Hintergrund-Ausschluss bei Item-Lernen |
| `scan_min_confidence` | Standard-Konfidenz für Template-Matching (Standard: 0.8 = 80%) |
| `scan_confirm_delay` | Standard-Wartezeit vor Bestätigungs-Klick in Sekunden (Standard: 0.5) |

### LLM Vision (Boss-Erkennung)

| Option | Beschreibung |
|--------|--------------|
| `llm_enabled` | LLM-basierte Boss-Erkennung global aktivieren (zusätzlich pro Boss-Scan `use_llm: true`) |
| `llm_provider` | `"ollama"` oder `"lmstudio"` |
| `llm_endpoint` | API-URL (`null` = Standard: `http://localhost:11434/api/chat` für Ollama, `http://localhost:1234/v1/chat/completions` für LM Studio) |
| `llm_model` | Modell-Name (Standard `"google/gemma-4-12b-qat"`; Provider-Fallback bei `null`: `"gemma3n:e4b"` für Ollama, `"google/gemma-4-12b-qat"` für LM Studio) |
| `llm_timeout` | Timeout für LLM-Anfragen in Sekunden (Standard: 30) |
| `llm_boss_prompt` | Custom-Prompt für Boss-Erkennung (`null` = Standard-Prompt mit bekannten Boss-Namen) |
| `llm_reasoning` | Reasoning-Modus aktivieren — Ollama: `think: true`, LM Studio: `reasoning_effort: high` (Standard: false) |
| `llm_max_tokens` | Token-Limit für Antworten (`0` = automatisch: 50 normal / 2048 mit Reasoning) |
| `llm_watcher_interval` | Prüf-Intervall des Boss-Watchers in Sekunden (Standard: 5.0) |
| `llm_watcher_max_scans` | Max. Scans bis Boss-Watcher abbricht (`0` = unbegrenzt) |
| `llm_watcher_timeout` | Timeout in Sekunden bis Boss-Watcher abbricht (`0` = unbegrenzt) |

### OCR Texterkennung (Boss-Erkennung)

| Option | Beschreibung |
|--------|--------------|
| `ocr_enabled` | OCR-basierte Texterkennung global aktivieren (zusätzlich pro Boss-Scan `use_ocr: true`) |
| `ocr_backend` | `null` (Auto-Detect), `"easyocr"` oder `"tesseract"` |
| `ocr_languages` | Sprach-Codes kommasepariert (Standard: `"en"`, z.B. `"en,de"` für Englisch+Deutsch) |
| `ocr_min_confidence` | Mindest-Konfidenz für OCR-Ergebnisse (0.0-1.0, Standard: 0.3) |

### Window-Fokus-Check

| Option | Beschreibung |
|--------|--------------|
| `window_focus_check` | Vor jedem Klick/Tastendruck prüfen ob Ziel-Fenster aktiv ist (Standard: false) |
| `window_focus_title` | Substring im Fenstertitel (case-insensitive, Standard: `"Idle Clans"`) |
| `window_focus_action` | `"pause"` = warten bis Fenster aktiv, `"stop"` = Sequenz abbrechen |

### Humanization (Anti-Bot-Detection)

| Option | Beschreibung |
|--------|--------------|
| `humanize_enabled` | Master-Switch für alle Humanize-Features (Standard: false) |
| `humanize_click_jitter` | Max. Pixel-Abweichung pro Klick (Standard: 0, sinnvoll: 2-5) |
| `humanize_micro_delay_min` | Zusatz-Delay vor jedem Klick/Taste: Min in Sekunden (Standard: 0) |
| `humanize_micro_delay_max` | Zusatz-Delay vor jedem Klick/Taste: Max in Sekunden (Standard: 0) |
| `humanize_break_interval_min` | Alle N Minuten eine Pause einlegen (`0` = keine Pausen) |
| `humanize_break_duration_min` | Pause-Dauer Min in Minuten |
| `humanize_break_duration_max` | Pause-Dauer Max in Minuten (Varianz) |

### Session-Log

| Option | Beschreibung |
|--------|--------------|
| `session_log_enabled` | CSV-Log aller Aktionen pro Sequenz schreiben (Standard: false) |
| `session_log_dir` | Verzeichnis für CSV-Dateien (Standard: `"logs"`) |

### Timing

| Option | Beschreibung |
|--------|--------------|
| `timing_pause_interval` | Prüf-Intervall während Pause in Sekunden (Standard: 0.5) |

### Debug-Einstellungen

| Option | Beschreibung |
|--------|--------------|
| `debug_mode` | Zeigt Schritte VOR Start und wartet auf Enter |
| `debug_detection` | Alle Ausgaben persistent (nicht überschrieben) |
| `debug_show_pixel_position` | Maus kurz zum Prüf-Pixel bewegen beim Start |
| `debug_save_templates` | Speichert Scan+Template in `items/debug/` für Debugging |

## Dateistruktur

```
Autoclicker-Idleclans/
├── main.py                 # Einstiegspunkt
├── autoclicker/            # Hauptmodul
│   ├── __init__.py
│   ├── config.py           # Konfiguration (Hotkeys, Defaults, AppConfig)
│   ├── models.py           # Datenmodelle (ClickPoint, Sequence, BossScanConfig, etc.)
│   ├── winapi.py           # Windows API (Maus/Tastatur, Window-Fokus)
│   ├── imaging.py          # Bildverarbeitung (Screenshots, OpenCV)
│   ├── llm_vision.py       # LLM Vision (Ollama / LM Studio Boss-Erkennung)
│   ├── ocr.py              # OCR Texterkennung (EasyOCR / Tesseract Boss-Erkennung)
│   ├── session_log.py      # CSV-Session-Logger
│   ├── import_export.py    # ZIP-Bundle Export/Import + Koordinaten-Remapping
│   ├── handlers.py         # Hotkey-Handler
│   ├── execution.py        # Backward-Compat-Shim → runtime/
│   ├── utils/              # Hilfsfunktionen
│   │   ├── console.py      # ANSI-Farben, Status-Tags
│   │   ├── io.py           # safe_input, interactive_select, wait_while_paused
│   │   └── parsing.py      # parse_time_input, format_duration, sanitize_filename
│   ├── persistence/        # Speichern/Laden (JSON)
│   │   ├── paths.py        # Pfad-Konstanten + init_directories
│   │   ├── serialization.py  # Dataclass ↔ JSON-Dict Konverter
│   │   ├── sequences.py    # Sequenz- + Punkte-Persistenz
│   │   ├── item_scans.py   # ItemScanConfig-Persistenz
│   │   ├── boss_scans.py   # BossScanConfig-Persistenz
│   │   ├── globals.py      # Global-Slots, Global-Items, Kategorien
│   │   └── presets.py      # Slot- und Item-Presets
│   ├── runtime/            # Sequenz-Ausführung (Worker-Thread)
│   │   ├── actions.py      # safe_click/safe_key, Humanize, Fokus-Check, Else-Aktion
│   │   ├── item_scan.py    # Item-Scan-Runtime + _check_profile_match
│   │   ├── boss_detection.py  # Boss-Scan, OCR/LLM-Erkennung, Async-Pfad
│   │   ├── steps.py        # Step-Dispatcher (_execute_*_step)
│   │   └── worker.py       # sequence_worker + print_status
│   └── editors/            # Interaktive Editoren
│       ├── __init__.py
│       ├── sequence_editor/  # Sequenz erstellen/bearbeiten
│       ├── item_editor/      # Items definieren (inkl. autoscan-Befehl)
│       ├── item_scan_editor.py
│       ├── slot_editor.py
│       ├── boss_scan_editor.py        # Boss-Scan-Konfiguration + LLM-Aktivierung
│       └── import_export_editor.py    # Wizard für Export/Import + Remapping
├── config.json             # Konfiguration (auto-generiert)
├── CLAUDE.md               # Architektur-Notizen für Claude Code
├── IDEAS.md                # Feature-Backlog mit Tradeoffs
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
├── boss_scans/             # Boss-Scan Konfigurationen (mit optionaler LLM-Aktivierung)
│   └── *.json
├── exports/                # Importier-/Exportier-Bundles (ZIP)
│   └── *.zip
├── logs/                   # Session-Logs als CSV (wenn session_log_enabled=true)
│   └── YYYY-MM-DD_HHMMSS_<seq>.csv
├── screenshots/            # Sequenz-Screenshots (nach Tag gruppiert)
│   └── YYYY-MM-DD/            # Pro Tag ein Unterordner
└── tools/                  # Hilfswerkzeuge
    ├── sync_json.py        # JSON-Dateien synchronisieren/migrieren
    ├── slot_tester.py      # Slot-Erkennung testen
    ├── test_llm.py         # LLM-Verbindungstest + Screenshot-Analyse
    └── test_ocr.py         # OCR-Backend-Test + Texterkennung
```

## Technische Details

### Architektur

Das Programm ist modular aufgebaut:

```
main.py                      Einstiegspunkt, Event-Loop
    │
    └── autoclicker/
        ├── config.py            Konstanten, Hotkey-IDs, AppConfig-Dataclass
        ├── models.py            Datenklassen (ClickPoint, Sequence, BossScanConfig, ...)
        ├── winapi.py            Windows API (Maus, Tastatur, Hotkeys, Window-Fokus)
        ├── imaging.py           Screenshots, Farberkennung, OpenCV
        ├── llm_vision.py        Ollama / LM Studio Integration (+ Reasoning)
        ├── ocr.py               EasyOCR / Tesseract für Boss-Texterkennung
        ├── session_log.py       CSV-Logger für Klick-/Key-Events
        ├── import_export.py     ZIP-Bundle + 2-Punkt-Koordinaten-Remapping
        ├── handlers.py          Hotkey-Callbacks
        ├── utils/               Hilfsfunktionen (console, io, parsing)
        ├── persistence/         JSON-Persistenz, Presets (paths, sequences, items, ...)
        ├── runtime/             Sequenz-Ausführung (actions, item_scan, boss_detection, steps, worker)
        └── editors/
            ├── sequence_editor/          Sequenz erstellen/bearbeiten
            ├── item_editor/              Items definieren (inkl. autoscan-Befehl)
            ├── item_scan_editor.py       Scans konfigurieren (inkl. Auto-Scan)
            ├── slot_editor.py            Slots definieren
            ├── boss_scan_editor.py       Boss-Scans + LLM-Vision-Aktivierung
            └── import_export_editor.py   Wizard für Setup-Export/Import
```

**Datenfluss:**
```
[Hotkey] → handlers.py → editors/*.py → persistence.py (Speichern)
                      ↘ execution.py → safe_click/safe_key → winapi.py
                                     ↘ imaging.py (Screenshots)
                                     ↘ llm_vision.py (HTTP zu Ollama/LM Studio)
                                     ↘ session_log.py (CSV-Append)
```

**Wichtig**: Alle Klicks und Tastendrücke im Worker-Thread laufen über `safe_click(state, x, y, label)` / `safe_key(state, key, label)` (in `execution.py`). Diese Wrapper bündeln Window-Fokus-Check, Humanization (Jitter/Mikro-Delays/Breaks) und Session-Logging. Direkter Aufruf von `send_click` / `send_key` umgeht alle drei.

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

### OCR Test-Tool (`tools/test_ocr.py`)

Testet OCR-Backend-Verfügbarkeit und Texterkennung ohne den Autoclicker:

```bash
python tools/test_ocr.py                        # Backend-Status + Region wählen
python tools/test_ocr.py test                   # Nur Backend-Verfügbarkeit prüfen
python tools/test_ocr.py bild.png               # Bild-Datei analysieren
python tools/test_ocr.py --region 100,200,800,600   # Region direkt angeben
python tools/test_ocr.py --bosses "Dragon,Goblin"   # Gegen Boss-Namen matchen
python tools/test_ocr.py --backend easyocr --languages "en,de"
```

### Slot-Tester (`tools/slot_tester.py`)

Testet die automatische Slot-Erkennung mit Debug-Ausgaben:

```bash
python tools/slot_tester.py
```

## Changelog

### Neueste Änderungen — LLM Reasoning + Codebase-Refactoring

**LLM Reasoning** (`autoclicker/llm_vision.py`, `autoclicker/config.py`)
- Neues Config-Feld `llm_reasoning: false` — aktiviert Reasoning-Modus für unterstützende Modelle
  - Ollama: `think: true` in der Anfrage, Antwort aus `message.thinking`-Feld
  - LM Studio: `reasoning_effort: "high"` in der Anfrage
- `<think>...</think>`-Tags werden automatisch aus Antworten herausgestripped (auch abgeschnittene Tags)
- Neues Config-Feld `llm_max_tokens: 0` — manuelles Token-Limit (`0` = auto: 50 normal / 2048 mit Reasoning)
- `tools/test_llm.py` komplett überarbeitet: nutzt `llm_vision.analyze_image` + `test_connection`, lädt `config.json` wenn vorhanden

**Codebase-Refactoring (Subpackages)**
- `execution.py` (1874 Zeilen) → `autoclicker/runtime/` Subpackage: `actions.py`, `item_scan.py`, `boss_detection.py`, `steps.py`, `worker.py`
- `utils.py` → `autoclicker/utils/` Subpackage: `console.py`, `io.py`, `parsing.py`
- `persistence.py` → `autoclicker/persistence/` Subpackage: `paths.py`, `serialization.py`, `sequences.py`, `item_scans.py`, `boss_scans.py`, `globals.py`, `presets.py`
- `editors/item_editor.py` → `editors/item_editor/` Subpackage
- `editors/sequence_editor.py` → `editors/sequence_editor/` Subpackage
- Alle Shims (`execution.py`, `utils/__init__.py`, etc.) behalten Backward-Compatibility — bestehende Imports unverändert
- `edit_phase()` (470-Zeilen-Monolith) → `_PhaseEditor`-Klasse mit 22 fokussierten Methoden

**Bugfixes (Code-Audit)**
- `editors/sequence_editor/steps.py`: `ins 0`/`ins end` waren toter Code (vom `ins <Nr>`-Prefix überschattet) — Exact-Match-Prüfung jetzt vor Prefix-Prüfung
- `editors/item_editor/commands.py`: `warn` wurde in `handle_rename_command` verwendet aber nie importiert → latenter `NameError`
- `winapi.py`: `HOTKEY_IMPORT_EXPORT` wurde bei `unregister_hotkeys` nicht freigegeben → `_HOTKEY_DEFINITIONS`-Liste geteilt zwischen Register/Unregister
- `config.py`: Zirkulärer Import in `__post_init__` (brauchte Konstanten aus `models.py`) → lokaler Import
- 27 ungenutzte Imports aus 9 Dateien entfernt

---

### LLM Vision — Genauigkeit + Retry + Async-Thread

**Prompt-Verbesserungen** (`autoclicker/llm_vision.py`)
- `temperature: 0.1 → 0.0` — verhindert Halluzinationen, deterministisches Ergebnis
- System-Prompt zu nummerierten Regeln umgebaut: "Ignoriere UI-Texte, Level, Zahlen" verhindert False-Positives durch Spiel-UI
- User-Prompt vereinfacht: `"Extrahiere nur den Boss-Namen:"` statt offener Frage
- `max_tokens: 200 → 50` — ein Name braucht keine 200 Token
- Provider-spezifische Modell-Defaults: `gemma3n:e4b` (Ollama) / `google/gemma-4-12b-qat` (LM Studio)
- Default-Timeout: 30s → 60s (Vision-Inferenz kann länger dauern)

**Retry-Logik bei `KEIN_BOSS`** (`execution.py`, `config.py`)
- Neues Config-Feld `llm_retry_count` (Standard: 2 = 3 Versuche gesamt)
- Bei `KEIN_BOSS`-Antwort: frischer Screenshot + erneuter LLM-Aufruf
- Verbindungsfehler bricht sofort ab, kein sinnloser Retry
- Analog zu `ocr_retry_count`

**Async-Modus** (`llm_async`) (`execution.py`, `models.py`, `config.py`)
- Neues Flag `llm_async: false` in `config.json`
- Bei `llm_async: true` läuft Boss-Scan/Watcher komplett im Hintergrund-Thread
- Sequenz-Worker läuft parallel — Warte-Steps und Klicks werden nicht blockiert
- Klick-Konflikte koordiniert über `llm_action_event`: Sequenz-Worker wartet nur während der eigentlichen Boss-Aktion (nicht während der 60s-Analyse)
- Thread-Check verhindert Deadlock (LLM-Thread wartet nicht auf sich selbst)
- Doppel-Spawn verhindert: neuer Thread nur wenn vorheriger beendet

---

### Neueste Änderungen — Auto-Scan + LLM Vision + Sicherheit + Import/Export

Sammel-Eintrag für die Arbeit auf Branch `claude/auto-scan-items-nCblH`. Reihenfolge entspricht dem Entstehungsverlauf.

**Auto-Scan Items** (Item-Editor)
- Neuer Befehl `autoscan` und `autoscan nocolor` im Item-Editor
- Scannt alle Slots auf einmal, erstellt Items mit Templates + optional Marker-Farben
- Duplikat-Erkennung: bestehende Items werden via Template-Matching übersprungen, nicht doppelt angelegt
- Auch im Item-Scan-Menü als eigener Workflow-Punkt verfügbar

**LLM Vision Boss-Detection** (`autoclicker/llm_vision.py`)
- Neues Modul für lokale Vision-LLMs via Ollama oder LM Studio (HTTP, urllib)
- `analyze_image()` schickt Screenshot + Boss-Namen-Liste an das Modell
- `match_boss_name()` mappt die Antwort auf bekannten Boss oder markiert als neu
- Im Boss-Scan-Editor pro Scan aktivierbar (`use_llm` + `llm_fallback`)
- Globale Config-Werte: `llm_enabled`, `llm_provider`, `llm_endpoint`, `llm_model`, `llm_timeout`, `llm_boss_prompt`
- **Auto-Save unbekannter Bosse**: Erkennt das LLM einen neuen Namen → wird als `BossProfile(action=skip)` gespeichert (unter `state.lock`)
- Standalone-Test-Script `test_llm.py` (Verbindungstest, Screenshot-Analyse, Datei-Analyse)

**Boss-Watcher** (Sequenz-Step)
- Neuer Step-Typ `watcher <Name>` im Sequenz-Editor
- Prüft alle `llm_watcher_interval` Sekunden bis ein Boss erkannt wird, dann Aktion
- Exit-Bedingungen: `llm_watcher_max_scans` (Anzahl) und `llm_watcher_timeout` (Sekunden) — beides `0` = unbegrenzt

**OCR Texterkennung** (`autoclicker/ocr.py`)
- Neues Modul für lokale Texterkennung via EasyOCR oder Tesseract
- `read_text()` extrahiert Text + Konfidenz aus Screenshot
- `detect_boss_name()` matched erkannten Text gegen bekannte Boss-Namen (exact/substring matching)
- Im Boss-Scan-Editor pro Scan aktivierbar (`use_ocr` + `ocr_fallback`)
- Globale Config-Werte: `ocr_enabled`, `ocr_backend` (auto-detect), `ocr_languages`, `ocr_min_confidence`
- Schneller und determinisitischer als LLM für reine Texterkennung
- Standalone-Test-Script `tools/test_ocr.py` (Backend-Test, Screenshot-Analyse, Datei-Analyse, Boss-Matching)

**Config-Field-Renaming**
- Alle Config-Felder systematisch in Gruppen unterteilt mit Präfixen: `click_*`, `scan_*`, `pixel_*`, `llm_*`, `ocr_*`, `humanize_*`, `window_focus_*`, `session_log_*`, `debug_*`, `timing_*`
- Automatische Migration alter config.json-Dateien (`_FIELD_MIGRATION` dictionary in AppConfig)
- Alte Configs werden automatisch auf neue Feldnamen gemappt, keine manuellen Änderungen nötig

**Code-Cleanup**
- Extrahiert `_check_profile_match()` Helper — vereinheitlicht 50 Zeilen Template/Marker-Erkennung in execute_boss_scan() und execute_item_scan()
- Extrahiert `_slot_to_dict()` Helper — standardisiert ItemSlot-Serialisierung über 5 Speicherlokationen
- Extrahiert `_step_status()` Helper — konsolidiert 24 if/debug/else/clear-Muster im Worker
- Ersetzt manuelle pause-Event-Schleifen mit zentraler `wait_while_paused()` Funktion
- Insgesamt -160 Zeilen Net-Reduktion durch Deduplication, keine Verhaltensänderungen

**Window-Fokus-Check** (`autoclicker/winapi.py` + `execution.py`)
- Verhindert dass Klicks in fremde Fenster gehen wenn man weg-tabbed
- Vor jedem Klick/Tastendruck wird `GetForegroundWindow` geprüft
- Config: `window_focus_check`, `window_focus_title` (Substring), `window_focus_action` (`pause` oder `stop`)

**Humanization** (`autoclicker/execution.py`)
- Klick-Jitter (±N Pixel Zufalls-Offset)
- Mikro-Delays vor jeder Aktion (Zufall min-max Sekunden)
- Periodische Pausen alle X Min für Y-Z Min Länge
- Config: `humanize_enabled`, `humanize_click_jitter`, `humanize_micro_delay_min/max`, `humanize_break_interval_min`, `humanize_break_duration_min/max`

**Session-Log** (`autoclicker/session_log.py`)
- Thread-sicherer CSV-Logger pro Sequenz-Session
- Pro Session eine Datei `logs/YYYY-MM-DD_HHMMSS_<seq>.csv`
- Geloggte Events: `session_start/end`, `click`, `key`, `focus_lost_pause/stop`, `focus_restored`, `humanize_break_start/end`
- Config: `session_log_enabled`, `session_log_dir`

**Zentrale safe_click / safe_key Wrapper**
- Neue Wrapper in `execution.py` bündeln Window-Fokus-Check + Humanization + Session-Logging
- **Alle** `send_click`/`send_key`-Aufrufe im Worker wurden auf die Wrapper umgestellt
- Direkt-Aufruf von `send_*` umgeht alle drei Features

**Import / Export-Editor** (`autoclicker/import_export.py` + `editors/import_export_editor.py`)
- Neuer Hotkey **CTRL+ALT+I**
- Komplettes Setup als ZIP exportieren (alles oder mit Auswahl)
- Empfänger importiert die ZIP — **2-Punkt-Koordinaten-Remapping** passt alle Klick-Punkte, Scan-Regionen, Boss-Regionen, Wait-Pixel, Confirm-Points, Screenshot-Regionen automatisch an den neuen Bildschirm an
- Templates (PNG) sind im ZIP enthalten und werden bei Import nach `items/templates/` extrahiert
- Merge- oder Ersetzen-Modus
- Anleitung für den Empfänger wird nach Export angezeigt
- Auch über das Item-Scan-Menü als Punkt 6 erreichbar

**Reviews + Bugfixes** (mehrere Commits, Auswahl der wichtigsten)
- Race Condition bei `config.bosses.append` (Auto-Save neuer Bosse) → Append jetzt unter `state.lock`
- LLM-Fallback-Logik invertiert: bei `llm_fallback=True` lief das LLM doppelt → strikte Entweder-Oder-Logik
- BytesIO-Memory-Leak in `_image_to_base64` → Context Manager
- Boss-Watcher hatte keinen Exit außer Sequenz-Stop → `max_scans` + `timeout` als Exit-Bedingungen
- `save_data` / `save_global_slots` / `save_global_items` iterierten ohne Lock → Snapshot unter `state.lock`
- `state.session_screenshots_dir`-Zuweisung war nicht thread-safe → unter `state.lock`
- `socket.timeout` in LLM-Calls jetzt explizit gefangen
- `screenshot_region` aus JSON wird auf Länge 4 validiert
- `BossScanConfig.default_action` nutzt `BOSS_ACTION_SKIP`-Konstante statt magisch `"skip"`-String

**Doku-Updates**
- `CLAUDE.md` neu — Architektur-Notizen für Claude Code Sessions
- `IDEAS.md` neu — Feature-Backlog mit Tradeoffs (Disconnect-Detection, Webhook-Notifications, Inventory-Full-Detection, HP/Food-Trigger, Session-Zeitlimit, Dry-Run, Auto-Login etc.)
- `README.md` (diese Datei) und `autoclicker/README.md` an alle neuen Features angepasst

### Vorherige Änderungen

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
