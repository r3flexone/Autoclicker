# Autoclicker for Idle Clans

Ein Autoclicker für Windows und Linux/X11 mit Sequenz-Unterstützung,
automatischer Item-Erkennung und Farb-Triggern.

## Features

- **Punkte aufnehmen**: Mausposition speichern mit automatischer Benennung
- **Sequenz-Aufnahme**: Klicks live per Maus-Hook aufnehmen (`CTRL+ALT+J`); aufgenommene Pixel-Farbe wird als Trigger-Standard übernommen
- **Sequenzen erstellen**: Punkte mit Wartezeiten oder Farb-Triggern verknüpfen
- **Sequenz-Studio**: Phasen als Spalten, Schritte per Ziehen umsortieren — auch über Phasengrenzen; dazu Live-Run und ein Reiter für alle Einstellungen (`CTRL+ALT+B`, eigenes Fenster)
- **Scans auf einem Screenshot**: Slots aufziehen, Hintergrundfarbe messen, Items lernen und sehen, was in welchem Slot erkannt wird — Reiter „Scans“ im Studio (`CTRL+ALT+V`)
- **Teilen im Studio**: Bündel schreiben und einlesen im Reiter „Teilen“ — Koordinaten werden aus der Spielfenster-Grösse umgerechnet
- **Boss- und Icon-Scans im selben Reiter**: Region aufziehen statt Koordinaten tippen, Vorlage aufnehmen, Marker messen, folgenlos testen (der Test nennt die Aktion, führt sie aber nicht aus) — umgeschaltet über SCAN-ART (Items · Bosse · Icons)
- **Dreiphasen-System**:
  - **INIT**: Einmalig vor allen Zyklen (Initialisierung)
  - **LOOP-Phasen**: Mehrere Loops möglich, jeweils mit eigenen Wiederholungen
  - **END**: Einmalig nach allen Zyklen (z.B. für Logout)
- **Farb-Trigger**: Warte bis eine bestimmte Farbe erscheint ODER verschwindet
- **Zufällige Verzögerung**: `1 30-45` = warte 30-45 Sekunden zufällig
- **Tastatureingaben**: Automatische Tastendrücke (Enter, Space, F1-F12, etc.)
- **Automatische Slot-Erkennung**: OpenCV-basierte Erkennung von Item-Slots
- **Item-Scan System**: Items anhand von Marker-Farben oder Templates erkennen
- **Fenstergebundene Item-Scans**: Editor und Laufzeit verwenden dieselbe
  Aufnahmequelle; Slots folgen einem verschobenen Spielfenster automatisch
- **Auto-Scan Items**: Alle Slots automatisch scannen und Items in einem Schritt erstellen (`autoscan`)
- **Kategorie-System**: Items gruppieren (z.B. Hosen, Jacken) - nur bestes pro Kategorie klicken
- **Template-Matching**: Items per Screenshot erkennen; ein Item kann automatisch
  passende Vorlagen für mehrere Slot-Grössen besitzen (OpenCV)
- **Boss-Scan**: Bosse anhand von Templates oder Markern erkennen + Aktion auslösen (Klick, Taste, Item-Scan, Skip)
- **Icon-Scan**: Ein Symbol/Icon (z.B. rotes „!" einer nicht machbaren Mission) per Template/Marker erkennen + Aktion (Klick/Taste/Skip)
- **LLM Vision Boss-Detection**: Lokale LLMs (Ollama / LM Studio) erkennen Bosse per Screenshot, unbekannte Bosse werden auto-gespeichert
- **LLM Reasoning**: Optionaler Reasoning-Modus für bessere Erkennungsgenauigkeit (Ollama: `think: true`, LM Studio: `reasoning_effort: high`)
- **Boss-Watcher**: Step der kontinuierlich auf einen Boss wartet und beim Erscheinen reagiert
- **Window-Fokus-Check**: Klicks gehen nur ins Spielfenster - bei Tab-Out wird pausiert (oder gestoppt)
- **Humanization**: Klick-Jitter, zufällige Mikro-Delays, periodische Pausen für menschlicheres Verhalten
- **Session-Log (CSV)**: Vollständiges Log aller Klicks/Tasten/Events pro Sequenz für Auswertung
- **Import/Export**: Komplettes Setup als ZIP exportieren und auf anderen PCs importieren — Koordinaten werden automatisch an die Spielfenster-Grösse angepasst (Fallback: 2-Punkt-Remapping); nach dem Import wird gewarnt, wenn Klick-Ziele ausserhalb des Fensters liegen
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

- Windows 10/11 **oder** Linux mit einer X11-Sitzung
- Python 3.10+

Wayland wird derzeit nicht unterstützt. Der Start erkennt Wayland, nennt die
fehlenden X11-Funktionen und beendet sich mit Status 2, statt fälschlich
„Bereit“ zu melden. Unter Linux lässt sich der Sitzungstyp mit
`echo $XDG_SESSION_TYPE` prüfen.

| Paket | Funktion | Erforderlich |
|-------|----------|:---:|
| `pillow` | Screenshots, Farberkennung | Nein |
| `numpy` | Optimierte Farberkennung | Nein |
| `opencv-python` | Template-Matching, Slot-Erkennung | Nein |
| `pynput` | Globale Eingabe und Hotkeys unter Linux/X11 | Linux |
| `python-xlib` | Fensterliste und Fokusprüfung unter Linux/X11 | Linux |
| `mss` | Multi-Monitor-Screenshots unter Linux/X11 | Linux |
| `easyocr` | OCR Texterkennung für Boss-Namen | Nein |
| `torch` | Abhängigkeit von EasyOCR | Nein |
| `torchvision` | Abhängigkeit von EasyOCR | Nein |
| `pytesseract` | Alternative OCR-Engine (+ Tesseract-Binary) | Nein |

## Installation

Auf Debian/Ubuntu benötigt `pynput` bei Python-Versionen ohne fertiges `evdev`-
Wheel einmalig einen Compiler:

```bash
sudo apt install build-essential python3-dev
```

```bash
git clone https://github.com/r3flexone/Autoclicker.git
cd Autoclicker
pip install pillow opencv-python numpy
python main.py
```

Unter Linux/X11 kommen drei kleine Plattformpakete dazu — unter Windows kommt
das aus der WinAPI:

```bash
pip install pynput python-xlib mss
```

### Minimale Installation unter Windows (nur Grundfunktionen)

Klicken, Hotkeys, Sequenzen — keine Bilderkennung:

```bash
python main.py
```

Unter Windows sind dafür keine zusätzlichen Pakete nötig. Linux/X11 benötigt
auch für die Grundfunktionen `pynput`, `python-xlib` und `mss`.

### Empfohlen (Farberkennung + Template-Matching)

```bash
pip install pillow opencv-python numpy
python main.py
```

Rund 70 MB. Das ist alles, was der normale Betrieb braucht. Der Code meldet beim
Start konkret, welches Paket fehlt.

### Optionale Extras (OCR, visuelle Editoren)

Drei Extras: `easyocr`, `pytesseract` und `pywebview`. Alle drei gehören zu
Features, die per Default **abgeschaltet** sind oder nur auf Zuruf starten —
installiere sie nur, wenn du sie benutzt. **`easyocr` zieht PyTorch nach:
mehrere GB Download.** `pywebview` ist dagegen klein: es öffnet das Studio-Fenster
(Sequenzen, Scans, Einstellungen) unter Windows über WebView2, das bei Windows
10/11 in der Regel schon vorhanden ist. Unter Linux braucht `pywebview` ein GTK-
oder Qt-Backend, auf Debian/Ubuntu etwa
`sudo apt install python3-gi gir1.2-webkit2-4.1`.

**Ohne GPU (CPU-only):**
```bash
pip install easyocr pytesseract pywebview
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
pip install easyocr pytesseract pywebview
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
- `1 color` → Warte bis die Farbe von Punkt 1 ERSCHEINT, dann Punkt 1 klicken
- `1 colorgone` → Warte bis die Farbe von Punkt 1 VERSCHWINDET, dann Punkt 1 klicken
- `wait 1 color` → Nur auf die Punkt-Farbe warten (kein Klick)
- `wait pixel` → Auf eine Farbe an der aktuellen Mausposition warten (kein Punkt, kein Klick)

## Hotkeys

### Aufnahme

| Hotkey | Funktion |
|--------|----------|
| `CTRL+ALT+A` | Mausposition als Punkt speichern |
| `CTRL+ALT+U` | Letzten Punkt entfernen (Undo) |
| `CTRL+ALT+C` | Alle Punkte löschen |
| `CTRL+ALT+J` | Sequenz aufnehmen (Klicks per Maus-Hook) |
| `CTRL+ALT+SHIFT+M` | Aufnahme: Marker „auf Farbe warten" (Maus über die Stelle) |
| `CTRL+ALT+SHIFT+D` | Aufnahme: Screenshot-Marker (Vollbild) |
| `CTRL+ALT+SHIFT+R` | Aufnahme: Screenshot-Bereich (2× drücken = zwei Ecken) |
| `CTRL+ALT+SHIFT+B` | Aufnahme: beobachten ohne Klick (Maus auf die Stelle) |
| `CTRL+ALT+SHIFT+P` | Aufnahme: neue Phase (beliebig oft — jede Grenze eine Loop-Phase) |
| `CTRL+ALT+H` | Aufnahme pausieren/fortsetzen |

### Editoren

| Hotkey | Funktion |
|--------|----------|
| `CTRL+ALT+E` | Sequenz-Editor (Punkte + Zeiten verknüpfen) |
| `CTRL+ALT+B` | Sequenz-Studio (Phasen + Schritte visuell, braucht `pywebview`) |
| `CTRL+ALT+N` | Item-Scan Editor (Items erkennen + vergleichen) |
| `CTRL+ALT+V` | Studio mit vorgewähltem Reiter „Scans“ (Item-, Boss- und Icon-Scans auf einem Screenshot) |
| `CTRL+ALT+L` | Gespeicherte Sequenz laden |
| `CTRL+ALT+P` | Punkte testen/anzeigen/umbenennen |
| `CTRL+ALT+T` | Farb-Analysator (für Bilderkennung) |
| `CTRL+ALT+I` | Import/Export (Setup teilen mit automatischem Remapping) |

### Ausführung

| Hotkey | Funktion |
|--------|----------|
| `CTRL+ALT+S` | Start/Stop der aktiven Sequenz |
| `CTRL+ALT+F` | Sanft beenden (Zyklus abschliessen, dann END + Stop) |
| `CTRL+ALT+G` | Pause/Resume |
| `CTRL+ALT+K` | Skip (aktuelle Wartezeit überspringen) |
| `CTRL+ALT+W` | Quick-Switch (schnell Sequenz wechseln) |
| `CTRL+ALT+Z` | Zeitplan (Start zu bestimmter Zeit) |

### System

| Hotkey | Funktion |
|--------|----------|
| `CTRL+ALT+O` | Hilfe / Hotkey-Übersicht anzeigen |
| `CTRL+ALT+X` | Factory Reset (Punkte + Sequenzen) |
| `CTRL+ALT+Q` | Programm beenden |

## Item-Scan System (`CTRL+ALT+N`)

Das Item-Scan System bietet ein Menü mit folgenden Optionen:
- **[1] Slots bearbeiten** - Bereiche wo Items erscheinen können
- **[2] Items bearbeiten** - Item-Profile für die Erkennung
- **[3] Scans bearbeiten** - Slots und Items verknüpfen
- **[4] Boss-Scans bearbeiten** - Bosse erkennen + Aktion auslösen (siehe Boss-Scan-Sektion)
- **[5] Icon-Scans bearbeiten** - Symbol/Icon erkennen + Aktion auslösen (siehe Icon-Scan-Sektion)

Im visuellen Scan-Reiter kann ein Spielfenster als dauerhafte Aufnahmequelle
gewählt werden. Items werden aus dem eingefrorenen Editor-Screenshot gelernt.
Beim Lauf wird dasselbe Fenster über denselben Aufnahmeweg frisch aufgenommen;
die gelernten Templates bleiben unverändert, während Slot- und Klickpositionen
relativ zum Fenster verschoben werden. Nach reinem Verschieben müssen Slots und
Items nicht neu gelernt werden. Bei einer neuen Fenstergrösse werden die Slots
proportional angepasst; für dadurch neue Slotgrössen wird einmal eine zusätzliche
Item-Vorlage gelernt.
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
4. Programm scannt alle Slots und vergleicht gegen bestehende Items. Bereits vollständig
   gelernte Duplikate werden übersprungen; bei demselben Item in einer neuen Slot-Grösse
   wird eine zusätzliche Vorlage ergänzt. Nur wirklich neue Inhalte werden neue Items.
5. Anschliessend nur noch via `rename <Nr>` umbenennen

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
    "template_variants": ["pinkes_juwel_62x57.png"],
    "min_confidence": 0.8,
    "category": "Juwelen"
  }
}
```

### Template-Matching

Items können per **Template-Matching** (Screenshot-Vergleich) erkannt werden:

1. Bei `learn` wird automatisch ein Template erstellt
2. Mit `template <Nr>` kann ein Template nachträglich gesetzt werden
3. Templates werden im `templates/`-Ordner der jeweiligen Sequenz gespeichert
4. `min_confidence` (0.0-1.0) bestimmt wie genau das Match sein muss
5. Pro Slot-Grösse wird eine passende Vorlage verwendet. Fehlt sie, zeigt das Studio
   „für diesen Scan noch nicht gelernt“; beim Lernen kann derselbe Item-Name gewählt
   werden, um die Grösse zu ergänzen.

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
| `<Nr> color` | Warte bis die Punkt-Farbe ERSCHEINT, dann klicke |
| `<Nr> colorgone` | Warte bis die Punkt-Farbe VERSCHWINDET, dann klicke |
| `<Nr> <Zeit> color` | Warte X Sek, dann auf die Punkt-Farbe warten, dann klicke |
| `wait <Zeit>` | Nur warten, KEIN Klick (z.B. `wait 30`, `wait 30m`, `wait 2h`) |
| `wait <Min>-<Max>` | Zufällig warten, KEIN Klick (z.B. `wait 30-45`) |
| `wait 14:30` | Warte bis 14:30 Uhr (heute oder morgen), KEIN Klick |
| `wait <Nr> color` | Auf die Farbe eines Punktes warten, KEIN Klick |
| `wait <Nr> colorgone` | Warten bis die Punkt-Farbe VERSCHWINDET, KEIN Klick |
| `wait pixel` | Auf Farbe an der aktuellen Mausposition warten, KEIN Klick |
| `wait pixelgone` | Warten bis Farbe an der Mausposition VERSCHWINDET, KEIN Klick |
| `scroll <Punkt-Nr> <Stufen>` | Mausrad am Punkt drehen, `+` hoch / `-` runter (z.B. `scroll 3 -5`) |
| `<Punkt-Nr> checkcolor` | Farbe **einmal** prüfen: passt sie → klicken, sonst Schritt überspringen |
| `<Punkt-Nr> checkgone` | einmal prüfen, ob die Farbe **weg** ist – sonst überspringen |
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
| `edit <Nr>` | Geführtes Menü zum Bearbeiten eines bestehenden Schritts |
| `color <Nr>` / `colorgone <Nr>` | Bestehenden Schritt auf Farb-Trigger umstellen (auf/bis WEG der aufgenommenen Farbe), dann Klick |
| `recolor <Nr>` | Trigger-Farbe eines Schritts per Maus neu setzen (Pixel-Position bleibt) |
| `time <Nr> <Zeit>` | Wartezeit eines bestehenden Schritts ändern |
| `noclick <Nr>` / `click <Nr>` | Schritt auf „nur warten" bzw. wieder auf Klick umstellen |
| `del <Nr>` | Schritt löschen |
| `clear` | Alle Schritte löschen |
| `show` | Aktuelle Schritte anzeigen |
| `done` | Phase abschliessen und speichern |
| `cancel` | Editor abbrechen (ohne Speichern) |

### Verfügbare Tasten

`enter`, `space`, `tab`, `escape`, `backspace`, `delete`,
`left`, `up`, `right`, `down`,
`f1`-`f12`,
`0`-`9`, `a`-`z`

### Beispiel-Sequenz

```
[INIT: 0] > 1 5           # Punkt 1 klicken, 5s warten
[INIT: 1] > 2 color       # Warten bis Punkt-Farbe erscheint, dann Punkt 2 klicken
[INIT: 2] > key enter     # Enter-Taste drücken
[INIT: 3] > done

[Loop 1: 0] > 3 30-45      # Punkt 3 klicken, 30-45s zufällig warten
[Loop 1: 1] > scan items   # Item-Scan ausführen (bestes pro Kategorie)
[Loop 1: 2] > wait 10-15   # 10-15s zufällig warten ohne Klick
[Loop 1: 3] > 4 colorgone  # Warten bis Punkt-Farbe verschwindet, dann Punkt 4 klicken
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
  > 4 color                 # Warte auf Boss-Spawn (Punkt-Farbe erscheint)
  > 5 0                     # Angreifen
  > done

Zyklen: 100

[END: 0] > 6 0              # Logout
[END: 1] > done
```

Loop 1 läuft in jedem Zyklus. Loop 2 wird übersprungen bis 12:30 erreicht ist – dann wird es einmal ausgeführt und danach wieder übersprungen bis zum nächsten Tag.

## Boss-Scan System

Boss-Scans erkennen einen Boss in einer fest definierten Region und lösen eine zugeordnete Aktion aus (Klick, Taste, Item-Scan, Skip, Restart).

Zwei Wege dorthin:

- **Studio** (`CTRL+ALT+V` → SCAN-ART „Bosse“) — Region mit zwei Klicks im Bild, Vorlage per Knopf, Test mit Ergebnis und Konfidenz. Für jede spätere Änderung der kürzere Weg: jedes Feld steht rechts und ist einzeln setzbar.
- **Konsole** (Item-Scan-Menü → **[4] Boss-Scans bearbeiten**) — der lineare Assistent, unverändert. Beide schreiben dieselben Dateien.

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

**Wie gut trifft die Benennung?** `python tools/llm_bench.py` misst es gegen
den eigenen Bestand: Items, deren Namen im Katalog stehen, sind der
Goldstandard, und jede Variante bekommt dieselben Proben.

```bash
python tools/llm_bench.py                        # Standard: gelernte Vorlagen
python tools/llm_bench.py --bild slot            # Ausschnitt aus dem gemerkten Bild
python tools/llm_bench.py --alle-modelle         # jedes Modell des Servers
python tools/llm_bench.py --zweistufig           # erst die Art, dann der Name
python tools/llm_bench.py --stimmen 3            # dreimal fragen, Mehrheit
```

Vor der Messung wird aufgewärmt — der erste Aufruf an einen kalten Server lädt
das Modell und dauert über zwei Minuten, die folgenden knapp drei Sekunden.
Geschrieben wird nichts.

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
- `ocr_retry_count: 0` (Wiederholungen bei „kein Text erkannt“; 0 = nicht wiederholen)

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
   - Wird das Spielfenster (Titel aus `window_focus_title`, Standard „Idle Clans") gefunden, wird seine **Client-Grösse automatisch** als Referenz genommen — kein manuelles Klicken nötig.
   - Andernfalls (Fenster nicht offen/gefunden): **zwei Referenzpunkte manuell setzen** (Maus an die Stelle bewegen, Enter) — z.B. Oben-Links und Unten-Rechts im Spielfenster.
4. Dateiname vergeben (Default: `autoclicker_export_<timestamp>.zip`)
5. ZIP wird in `exports/` gespeichert
6. Anleitung für den Empfänger wird angezeigt

Das ZIP enthält: `manifest.json` (inkl. Spielfenster-Grösse falls erkannt), alle JSON-Daten, gepackte Template-PNGs, optional die Config (gefiltert).

### Import

1. Empfänger legt die ZIP-Datei in `exports/` (oder ins Hauptverzeichnis)
2. `CTRL+ALT+I` → "Importieren"
3. Datei aus der Liste auswählen
4. Inhalt der ZIP wird angezeigt + Referenzpunkte des Exporters
5. **Anpassungs-Modus wählen**:
   - Enthält das Export-Manifest die Spielfenster-Grösse **und** das Spielfenster läuft gerade:
     - **[1] Automatisch aus Fenstergrösse** (empfohlen) → Skalierung wird aus Export- vs. aktueller Fenstergrösse berechnet, kein Klicken nötig
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

## Sequenzen zwischen PCs teilen

Eine Sequenz ist eine **vollständige Besitzeinheit**: `sequences/<name>/` enthält
den Ablauf, die sequenzlokalen Punkte, alle Scans, die Vorlagen und die
gemerkten Bilder. Den Ordner zu kopieren reicht deshalb — es gibt nichts
daneben, das mitmüsste.

Was dabei **nicht** passiert: die Koordinaten werden beim Laden nicht angepasst.
Früher glich der Loader Schritte über ihren **Namen** mit lokalen Punkten ab,
schrieb sie um und speicherte die Datei sofort. Das ist ersatzlos entfallen, und
zwar aus einem handfesten Grund: aufgenommene Punkte heissen per Default `P<id>`
— eine fremde Sequenz bringt also einen Schritt namens „P3" mit, und der lokale
„P3" liegt garantiert woanders. Der Abgleich hat solche Schritte stillschweigend
verschoben.

Geblieben ist die **Diagnose**: passt die Koordinate eines Schritts nicht zum
gleichnamigen lokalen Punkt, wird das gemeldet — geändert wird nichts.

Für einen anderen Bildschirm gibt es die zwei Wege, die wirklich rechnen:

| Weg | wofür |
|---|---|
| Import mit Fenster-Remapping (`CTRL+ALT+I`) | anderer Bildschirm, anderes Fenster — rechnet alle Koordinaten um |
| Studio → Werkzeuge → Kalibrieren | derselbe Bestand, verschobene Anordnung — mit Vorschau vor dem Anwenden |

Passt gar nichts mehr zusammen (Spiel-Update, neue Fensterlage pro Element),
hilft kein Versatz: dann die **Klick-Runde** nehmen (Studio → Werkzeuge oder
Punkte-Menü → `klick`) und die Sequenz einmal von Hand nachklicken.

## Laufzeit-Steuerung

Während eine Sequenz läuft:

- **CTRL+ALT+S** - Stoppt die Sequenz komplett
- **CTRL+ALT+F** - Sanfter Abbruch (aktuellen Zyklus abschliessen, dann END-Phase + Stop)
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
Schritt 1: 1 color else ???    ← Farbe wird NICHT erkannt
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
1 color else skip              # Wenn Timeout: nur diesen Schritt überspringen
1 color else skip_cycle        # Wenn Timeout: ganzen Zyklus abbrechen
1 color else restart           # Wenn Timeout: von vorne beginnen (inkl. INIT)
1 color else key enter         # Wenn Timeout: Enter drücken
wait 1 colorgone else skip     # Wenn Punkt-Farbe nicht verschwindet: überspringen
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

Unter Windows laufen globale Hotkeys über `RegisterHotKey`; Linux/X11 verwendet
`pynput`. Eine Tastenkombination kann trotzdem bereits vom Betriebssystem oder
Desktop belegt sein. Die Pfeiltasten-Navigation nutzt unter Windows in PyCharm
`GetAsyncKeyState`, unter Linux denselben X11-Eingabeadapter wie die Hotkeys.

## Konfiguration (`config.json`)

Wird beim ersten Start automatisch erstellt:

```json
{
  "studio_open_on_start": true,
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
  "llm_debug": false,
  "llm_boss_prompt": null,
  "llm_watcher_interval": 5.0,
  "llm_watcher_max_scans": 0,
  "llm_watcher_timeout": 0,
  "ocr_enabled": false,
  "ocr_backend": null,
  "ocr_languages": "en",
  "ocr_min_confidence": 0.3,
  "ocr_retry_count": 0,
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
  "debug_log": false,
  "debug_detail": false,
  "debug_show_pixel_position": false,
  "debug_save_templates": false
}
```

`studio_open_on_start` wählt die Startoberfläche. Ist die Option an, startet das
Sequenz-Studio ohne zusätzlichen TUI-Banner, Anleitung und Bereitschaftsblock; die
Konsole bleibt nur technisches Log und Rückfallweg für noch vorhandene
Konsolenwerkzeuge. Ist die Option aus, startet das Programm mit der TUI. Das Studio
bleibt dort über den Hotkey erreichbar. Beide Oberflächen verwenden denselben
Hauptprozess, dieselben Funktionen und dieselben Dateien.

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
| `punkt_radius` | Bis zu diesem Abstand (px) gilt eine Stelle als derselbe Punkt und wird wiederverwendet, statt einen zweiten anzulegen (0 = nur exakt) |
| `punkt_farbtoleranz` | ...aber nur, wenn auch die Farbe passt — sonst entsteht immer ein eigener Punkt |
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
| `llm_debug` | Jede LLM-Anfrage in die Konsole mitschreiben: Modell, Endpunkt, Bildmass, beide Prompts, die **rohe JSON-Antwort** (samt `reasoning_content`, das der Code sonst verwirft) und den daraus gelesenen Text. Der Weg, um eine leere Antwort einzuordnen — ein Modell ohne Bild-Fähigkeit, ein falscher Modellname und ein Reasoning-Modell ohne Token-Reserve sehen von aussen gleich aus. (Standard: false) |
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
| `ocr_retry_count` | Wiederholungen bei „kein Text erkannt“ — mit frischem Screenshot, denn im Spiel kann sich inzwischen etwas geändert haben (`0` = nicht wiederholen) |

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

### Nachprüfung („hat die Aktion gewirkt?")

| Option | Beschreibung |
|--------|--------------|
| `verify_retries` | Wie oft die Aktion wiederholt wird, wenn die Nachprüfung nicht greift (Standard: 2) |
| `verify_timeout` | Wie lange pro Versuch auf die erwartete Farbe gewartet wird (Sekunden) |
| `verify_interval` | Prüf-Intervall innerhalb eines Versuchs (Sekunden) |

### Session-Log

| Option | Beschreibung |
|--------|--------------|
| `session_log_enabled` | CSV-Log aller Aktionen pro Sequenz schreiben (Standard: false) |
| `session_log_dir` | Verzeichnis für CSV-Dateien (Standard: `"logs"`) |

### Timing

| Option | Beschreibung |
|--------|--------------|
| `timing_pause_interval` | Prüf-Intervall während Pause in Sekunden (Standard: 0.5) |

### Aufnahme, Boss-Bibliothek, Marktwerte

| Option | Beschreibung |
|--------|--------------|
| `record_scroll` | Mausrad mit aufnehmen (Standard: true). Aus für Spiele, in denen das Rad nur die Ansicht dreht |
| `boss_learn_global` | Neu entdeckte Bosse in die globale Bibliothek schreiben statt in den einzelnen Scan (im Boss-Scan-Menü umschaltbar) |
| `scan_market_value_file` | Pfad zu `marktwert.json` aus `market_analysis` — sortiert Item-Klicks nach Gold statt nach getippter `priority` (leer = aus) |
| `scan_catalog_file` | Pfad zu `katalog.json` aus der Spiel-API — im Studio holt der Knopf **Katalog aus der Spiel-API holen** direkt unter diesem Feld die Datei und trägt den Pfad ein; auf der Kommandozeile `python tools/katalog.py`. Echte Item-Namen für Kategorie, Priorität und LLM-Benennung. Sagt nur, **wo** die Datei liegt; **ob** ein Scan sie benutzt, steht als `use_catalog` am Scan (leer = aus) |

### Debug-Einstellungen

| Option | Beschreibung |
|--------|--------------|
| `debug_log` | **Beobachten.** Alle Schritt-Ausgaben persistent (Status-Zeile wird nicht überschrieben) + Erkennungs-Details bei Item/Boss/Icon-Scans. Läuft ohne Eingriff durch |
| `debug_detail` | **Stufe 2.** Zusätzlich springt der Zeiger vor jedem Schritt auf den Zielpunkt (ohne Klick) und es wird ausgeschrieben, *was* dort passieren soll — mit Farbquadrat bei Farb-Bedingungen. Läuft weiter durch |
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
│   ├── winapi.py           # Stabile Fassade zur aktuellen Plattform
│   ├── platforms/          # Windows- und Linux/X11-Backends
│   ├── imaging.py          # Bildverarbeitung (Screenshots, OpenCV)
│   ├── llm_vision.py       # LLM Vision (Ollama / LM Studio Boss-Erkennung)
│   ├── ocr.py              # OCR Texterkennung (EasyOCR / Tesseract Boss-Erkennung)
│   ├── session_log.py      # CSV-Session-Logger
│   ├── import_export.py    # ZIP-Bundle Export/Import + Koordinaten-Remapping
│   ├── handlers.py         # Hotkey-Handler
│   ├── befehl.py           # Briefkasten Studio -> Hauptprozess
│   ├── config_meta.py      # Beschriftung/Erklärung je Config-Feld (Studio)
│   ├── diagnose.py         # Selbstdiagnose (fehlende Templates, tote Verweise)
│   ├── symbol.py           # Programm-Symbol als Geometrie
│   ├── sequence_studio.py  # Einstiegspunkt des Studio-Subprozesses
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
│   │   ├── icon_scans.py   # IconScanConfig-Persistenz
│   │   ├── globals.py      # Global-Slots, Global-Items, Kategorien
│   │   ├── presets.py      # Slot- und Item-Presets
│   │   ├── migration.py    # Schema-Migrationen
│   │   └── sweep.py        # Bestandsprüfung und Sicherungen
│   ├── runtime/            # Sequenz-Ausführung (Worker-Thread)
│   │   ├── actions.py      # safe_click/safe_key, Humanize, Fokus-Check, Else-Aktion
│   │   ├── item_scan.py    # Item-Scan-Runtime + _check_profile_match
│   │   ├── boss_detection.py  # Boss-Scan, OCR/LLM-Erkennung, Async-Pfad
│   │   ├── steps.py        # Step-Dispatcher (_execute_*_step)
│   │   ├── worker.py       # sequence_worker + print_status
│   │   ├── debug.py        # Schritt- und Erkennungsdiagnose
│   │   └── status.py       # Laufstatus für externe Prozesse
│   └── editors/            # Interaktive Editoren
│       ├── __init__.py
│       ├── sequence_editor/  # Sequenz erstellen/bearbeiten
│       ├── item_editor/      # Items definieren (inkl. autoscan-Befehl)
│       ├── sequence_studio/  # pywebview-Studio
│       │   ├── bridge.py     # stabile StudioBridge-Fassade
│       │   ├── bridge_contract.py, bridge_view.py
│       │   ├── bridge_services.py, bridge_editing.py
│       │   ├── scans.py      # stabile ScanTeil-Fassade
│       │   ├── scan_contract.py, scan_state.py
│       │   ├── scan_interaction.py, scan_learning.py
│       │   ├── scan_library.py, scan_capture.py, scan_model.py
│       │   ├── scan_detect.py  # Boss- und Icon-Scans im Studio
│       │   ├── bridge_teilen.py, bridge_werkzeuge.py, model.py
│       │   └── web/          # HTML, CSS, JavaScript und Logo
│       ├── scan_services.py  # gemeinsame Slot-Erkennung und Bildgeometrie
│       ├── item_scan_editor.py
│       ├── slot_editor.py
│       ├── boss_scan_editor.py        # Boss-Scan-Konfiguration + LLM-Aktivierung
│       └── import_export_editor.py    # Wizard für Export/Import + Remapping
├── config.json             # Konfiguration (auto-generiert)
├── CLAUDE.md               # Architektur-Notizen für Claude Code
├── AGENTS.md               # dasselbe für Codex (inhaltsgleich zu CLAUDE.md)
├── IDEAS.md                # Feature-Backlog mit Tradeoffs
├── README.md               # Diese Datei
├── sequences/              # Jede Sequenz ist eine vollständige Besitzeinheit
│   └── <name>/
│       ├── sequence.json   # Ablauf und sequenzlokale Punkte
│       ├── item_scans/     # Item-Scans mit vollständig eingebetteten Slots/Items
│       ├── boss_scans/     # Boss-Scans + bibliothek.json (gilt in jedem Boss-Scan)
│       ├── icon_scans/     # Icon-Scans
│       ├── templates/      # Lokale Template-Bilder aller Scans
│       └── bilder/         # Je Item-Scan ein eingefrorener Bildschirm
├── presets/                # Wiederverwendbare Slot-/Item-Presets
├── exports/                # Importier-/Exportier-Bundles (ZIP)
│   └── *.zip
├── logs/                   # Session-Logs als CSV (wenn session_log_enabled=true)
│   └── YYYY-MM-DD_HHMMSS_<seq>.csv
├── screenshots/            # Sequenz-Screenshots (nach Tag gruppiert)
│   └── YYYY-MM-DD/            # Pro Tag ein Unterordner
├── tests/                  # ALLE Tests — drei Schichten und ihre Läufer
│   ├── alle_tests.py       # EIN Aufruf für alles — das vor einem Commit
│   ├── test_logic.py       # Vertragssuite (ohne GUI, Windows, Netz)
│   ├── vertrag/            # weitere Sektionen der Vertragssuite
│   ├── wurzel/             # Wurzelmodule (unittest): Import/Export, Plattform, Studio
│   ├── rauch/              # die echte Seite im Browser vor der echten Brücke
│   ├── wurzeltests.py      # Discovery der Wurzelmodule ohne doppelten Vertragslauf
│   └── mutationspruefung.py # Gegenproben: entfernte Sicherung muss auffallen
└── tools/                  # Hilfswerkzeuge — hier steht kein Test mehr
    ├── katalog.py          # Item-/Gegner-Katalog aus der Spiel-API holen
    ├── migrate.py          # JSON-Dateien aufs aktuelle Format heben (macht die App beim Start selbst)
    ├── log_report.py       # Session-Logs auswerten (welcher Schritt hängt?)
    ├── symbol.py           # Programm-Symbol als PNG + ICO schreiben
    ├── slot_tester.py      # Slot-Erkennung testen
    ├── test_llm.py         # LLM-Verbindungstest + Screenshot-Analyse (Werkzeug, kein Test)
    └── test_ocr.py         # OCR-Backend-Test + Texterkennung (Werkzeug, kein Test)
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
        ├── winapi.py            Stabile Plattform-Fassade
        ├── platforms/           Windows- und Linux/X11-Backends
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
            ├── sequence_studio/          pywebview-Studio; Bridge- und Scan-Mixins
            ├── item_scan_editor.py       Scans konfigurieren (inkl. Auto-Scan)
            ├── slot_editor.py            Slots definieren
            ├── boss_scan_editor.py       Boss-Scans + LLM-Vision-Aktivierung
            └── import_export_editor.py   Wizard für Setup-Export/Import
```

**Datenfluss:**
```
[Hotkey] → handlers.py → editors/*.py → persistence/ (Speichern)
                      ↘ runtime/actions.py → safe_click/safe_key → winapi.py → platforms/
                                     ↘ imaging.py (Screenshots)
                                     ↘ llm_vision.py (HTTP zu Ollama/LM Studio)
                                     ↘ session_log.py (CSV-Append)
```

**Wichtig**: Alle Klicks und Tastendrücke im Worker-Thread laufen über `safe_click(state, x, y, label)` / `safe_key(state, key, label)` (in `runtime/actions.py`). Diese Wrapper bündeln Window-Fokus-Check, Humanization (Jitter/Mikro-Delays/Breaks) und Session-Logging. Direkter Aufruf von `send_click` / `send_key` umgeht alle drei.

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
| ctypes (builtin) | Windows API, Hotkeys, Maus/Tastatur | Windows |
| pynput | Globale Eingabe und Hotkeys | Linux/X11 |
| python-xlib | Fensterliste und Fokusprüfung | Linux/X11 |
| mss | Bildschirmaufnahme | Linux/X11 |
| Pillow | Screenshots, Farberkennung | Optional |
| NumPy | Optimierte Farberkennung | Optional |
| OpenCV | Template Matching, Slot-Erkennung | Optional |

### Technologien

- Windows API via `ctypes`; Linux/X11 über `pynput`, `python-xlib` und `mss`
- Pillow für Screenshot und Farberkennung (optional)
- OpenCV für automatische Slot-Erkennung und Template Matching (optional)
- Globale Hotkeys über `RegisterHotKey` (Windows) oder `pynput` (Linux/X11)
- Eingabesimulation über `SendInput` (Windows) oder `pynput` (Linux/X11)
- BitBlt für Windows-Screenshots, MSS für Linux/X11
- Thread-basierte Ausführung mit Events für Synchronisation
- JSON-Persistenz für alle Daten
- Multi-Monitor Unterstützung (DPI-aware)
- Sichere Dateinamen (Path-Traversal-Schutz)
- IDE-Kompatibel: `GetAsyncKeyState`-Polling als Fallback für Pfeiltasten in PyCharm/IDE-Konsolen

## Tools

### Tests (`tests/alle_tests.py`)

**Ein Kommando, drei Schichten** — das vor einem Commit:

```bash
python tests/alle_tests.py                      # alles
python tests/alle_tests.py --nur vertrag        # nur die Vertragssuite (schnell)
python tests/alle_tests.py --nur rauch --rauchtest werkzeuge   # eine Ansicht
python tests/alle_tests.py --mutationen         # zusätzlich gezielte Gegenproben
python -m flake8 --select=F autoclicker/ market_analysis/ main.py tools/
```

| Schicht | was sie prüft | braucht |
|---|---|---|
| Vertragssuite (`tests/test_logic.py`) | Logik ohne GUI, ohne Windows, ohne Netz | nichts |
| Wurzelmodule (`tests/wurzel/`) | Import/Export, Plattformvertrag, Studio-UX, Runtime-Härtung | Pillow |
| Rauchtests (`tests/rauch/`) | die echte Seite im Browser vor der echten Brücke | Playwright + Chromium |

Was fehlt, wird **übersprungen und gesagt**, nicht als Fehler gemeldet. Für die
volle Abdeckung lohnen sich die optionalen Pakete — ohne OpenCV/Pillow
überspringt die Suite über hundert Tests rund um Bilderkennung:

```bash
pip install opencv-python-headless pillow numpy
pip install playwright && python -m playwright install chromium
```

Im Browser-CI gilt `--rauch-pflicht`: Ein fehlender Browser macht diesen Job rot.
Im Gesamtlauf läuft die Vertragssuite genau einmal; `--nur wurzel` und normale
Unittest-Discovery behalten den Vertragswrapper. Die PASS-Zahl der Vertragssuite
zählt einzelne Zusicherungen, nicht unabhängige Testszenarien.

Die CI führt auch `--mutationen` aus: Zehn gezielt entfernte Sicherungen müssen
durch Assertions auffallen, jeweils nach einem grünen unveränderten Kontrolllauf.
Die Änderungen existieren nur im Speicher separater Prozesse. Ein Importfehler,
Skip oder Timeout zählt nicht als Erkennung. Einzelne Gegenproben lassen sich mit
`python tests/mutationspruefung.py --fall pause-nach-fokus` wiederholen. Das ist
eine begrenzte Auswahl kritischer Regressionen, keine vollständige Mutationsabdeckung.

Die Rauchtests sind die Schicht, die die Vertragssuite nicht sehen **kann**: sie
ruft die Brücken-Methoden direkt auf, also genau so, wie die Seite es *nicht*
tut. Ein Tippfehler in einem Methodennamen oder ein Zustand, der einen Neuaufbau
nicht überlebt, fällt erst im Browser auf.

### Migrations-Tool (`tools/migrate.py`)

Hebt alle JSON-Dateien aufs aktuelle Format. **Normalerweise brauchst du das nicht** —
der Autoclicker macht denselben Durchgang bei jedem Start (Einstellung
`migrate_on_start`, Standard an) und meldet sich nur, wenn es etwas zu tun gab.

```bash
python tools/migrate.py            # zeigt nur an, was passieren würde
python tools/migrate.py --write    # schreibt (Sicherungen als *.bak)
```

- Tote Felder entfernen, die es im Code nicht mehr gibt (das ist inzwischen die
  Hauptarbeit: der Durchgang liest jede Datei mit dem Loader und schreibt sie mit dem
  Serializer zurück — was der Loader nicht kennt, kommt nicht wieder)
- Erfasst alle Dateien, und zwar über die **Besitzeinheiten**: `config.json`,
  dann je Sequenzordner die `sequence.json` (mit ihren Punkten), ihre item-,
  boss- und icon-Scans und ihre Boss-Bibliothek, zuletzt beide Preset-Ordner

> **Sequenzen werden nicht mehr umgerechnet.** Die Schritte, die alte Sequenz-Formate
> aufs heutige Schema hoben (`steps`/`loop_steps` → `loop_phases`, `delay_after`,
> Koordinaten → Punktliste in `sequence.json`), sind gelöscht — es gibt keine Dateien mehr, die sie
> bräuchten. Eine sehr alte Sicherung wird deshalb zwar gelesen und gestempelt, kommt
> aber **leer** an. In dem Fall die Sequenz im Studio neu bauen; das geht inzwischen
> schneller, als es das Zurückholen der Migrationsschritte täte.

Ein zweiter Lauf muss „0 angepasst" melden — daran erkennst du, dass alles sauber ist.

### Symbol-Tool (`tools/symbol.py`)

Schreibt das Programm-Symbol als PNG und als `.ico`.

```bash
python tools/symbol.py                      # legt symbol/ an: PNGs + autoclicker.ico
python tools/symbol.py --ziel C:\Bilder     # woanders hin
python tools/symbol.py --groessen 256,512   # nur diese Kantenlängen
```

**Für das Fenster brauchst du das nicht** — Titelleiste, ALT+TAB und Taskleiste
setzt das Studio selbst. Die Dateien sind für alles, was Windows aus einer Datei
nimmt: eine Verknüpfung auf dem Desktop (Rechtsklick → Eigenschaften → Anderes
Symbol → `autoclicker.ico`), ein angehefteter Eintrag, ein Ordnerbild.

Gezeichnet wird aus derselben Geometrie wie das Fenstersymbol
(`autoclicker/symbol.py`) — deshalb liegt keine fertige Bilddatei im Repo, die
beim nächsten Umzeichnen zurückbliebe. Pillow wird nicht gebraucht.

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

## Änderungen

Die Historie steht in `git log` — dort ist sie vollständig, datiert und mit
dem Code verbunden, der sie ausgelöst hat. Hier stand sie als handgepflegte
Liste daneben: fast ein Viertel dieser Datei, das beim Lesen niemand braucht
und bei jeder Änderung mitgepflegt werden wollte.

```bash
git log --oneline            # was zuletzt passiert ist
git log -p CLAUDE.md         # warum eine Regel so lautet, wie sie lautet
```

## Lizenz

MIT License
