# Autoclicker-Paket

Das Paket ist in Datenmodell, Laufzeit, Persistenz, Plattformadapter und Editoren
getrennt. Einstiegspunkt der Anwendung ist weiterhin `main.py` im Projektwurzelordner.

## Kern

| Modul | Aufgabe |
|---|---|
| `config.py`, `config_meta.py` | Konfiguration, Laden/Speichern und UI-Metadaten |
| `models.py` | Persistierte Datenklassen und gemeinsamer Laufzeitzustand |
| `handlers.py` | Hotkeys und Orchestrierung der Benutzeraktionen |
| `diagnose.py` | Verständliche Prüfung des gesamten Setups |
| `befehl.py` | Dateibasierte Befehle vom Studio an den Hauptprozess |
| `session_log.py` | Threadsicheres CSV-Protokoll pro Lauf |
| `import_export.py` | Validierte ZIP-Bundles, Remapping und transaktionaler Import |

## Laufzeit

`runtime/` enthält ausschließlich die Ausführung:

- `actions.py`: einzige Grenze für Klick, Taste und Scrollen; Fokusprüfung,
  Humanisierung und Logging werden hier gebündelt.
- `worker.py`: Sequenz-, Phasen- und Zeitsteuerung.
- `steps.py`: Dispatcher für Sequenzschritte, Trigger und Verifikation.
- `item_scan.py`: Item- und Iconerkennung; bei mehreren Treffern gewinnt die
  höchste gemessene Trefferqualität.
- `boss_detection.py`: Template-, OCR- und LLM-Erkennung, synchron und asynchron.
- `debug.py`, `status.py`: Diagnose und atomarer Laufstatus für das Studio.

Direkte `send_click`-/`send_key`-Aufrufe gehören nicht in Worker oder Editoren,
sondern müssen über `runtime.actions.safe_click` bzw. `safe_key` laufen.

## Persistenz

`persistence/` ist nach Datentypen aufgeteilt:

- `paths.py`, `serialization.py`, `_scan_store.py`: gemeinsame Grundlagen.
- `sequences.py`, `item_scans.py`, `boss_scans.py`, `icon_scans.py`: Dateien der
  jeweiligen Domäne.
- `globals.py`, `presets.py`: globale Slots/Items und Presets.
- `migration.py`, `sweep.py`: Schema-Migration, Sicherungen und Bestandsprüfung.

Schreibvorgänge verwenden möglichst `atomic_write`; Referenzen werden nach dem
Laden zentral aufgelöst.

## Bilderkennung und Plattform

- `winapi.py`: Windows-Eingabe, Hooks, Fenster, DPI und Bildschirmgeometrie.
- `imaging.py`: Screenshots, Farben und abgesichertes Template-Matching.
- `ocr.py`: EasyOCR/Tesseract; EasyOCR-Reader werden je Sprachkombination gecacht.
- `llm_vision.py`: optionale lokale oder benutzerdefinierte Vision-Endpunkte.

Pillow, OpenCV, OCR und LLM sind optionale Fähigkeiten. Fehlende Pakete werden
abgefangen und als Diagnose gemeldet.

## Editoren

- `editors/sequence_editor/`: Konsoleneditor für Sequenzen.
- `editors/item_editor/`: Items, Marker, Lernen und Autoscan.
- `editors/sequence_studio/`: GUI-freie Brücke und Scanlogik für pywebview.
- `editors/sequence_studio/scan_capture.py`: Screenshot- und Fensteraufnahme
  getrennt von Itemlernen und Erkennung. Die dauerhafte Fensterquelle wird über
  Titel/Instanz wiedergefunden; Editor und Runtime verwenden denselben
  Aufnahmehelfer und rechnen Slots relativ zum Client-Bereich um.
- `editors/scan_services.py`: gemeinsame Geometrie und Slot-Erkennung für
  Konsoleneditor und Studio.
- Die übrigen Dateien enthalten die Assistenten für Slots, Item-/Boss-/Icon-Scans,
  Aufnahme sowie Import/Export.

Die Weboberfläche des Studios ist bewusst ohne Framework und ohne Netzwerk:

| Datei | Inhalt |
|---|---|
| `web/index.html` | Semantischer Aufbau |
| `web/styles.css` | Layout, Größen und Farben |
| `web/app.js` | Interaktion und Aufrufe der Python-Brücke |

## Tests

Die vollständige lokale und CI-Prüfung lautet:

```bash
python -m unittest discover -v
```

`test_regression.py` bindet dabei die große, plattformunabhängige Vertragssuite
`tools/test_logic.py` ein. Weitere `test_*.py`-Dateien prüfen Sicherheitsgrenzen,
Editor-UX, Marktberechnung und Laufzeit-Härtungen.
