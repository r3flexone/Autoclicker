"""
Sequenz-Studio: Phasen und Schritte visuell bearbeiten (Weboberfläche).

Läuft als separater Subprocess (siehe autoclicker/sequence_studio.py), damit der
Fenster-Event-Loop nicht mit der Windows-Hotkey-Message-Pump im Hauptprozess
kollidiert. Liest/schreibt dieselben Dateien unter sequences/<name>/ wie die
Konsolen-Editoren — der Executor bemerkt keinen Unterschied.

Modul-Aufteilung (Details in der CLAUDE.md dieses Ordners):
    model.py        GUI-freier Layer: Sequence ↔ Lanes/Blöcke (verlustfreier Round-Trip)
    bridge.py       StudioBridge: die einzige Verbindung zur Oberfläche (testbar)
    bridge_*.py     Protokoll, Darstellung, Dienste, Editor-Kommandos und die Reiter
                    Teilen, Werkzeuge und Bericht
    scans.py        ScanPart: Slots, Items, Erkennung und Lernablauf
    scan_*.py       Scan-Protokoll, Zustand, Interaktion, Lernen, Bibliothek,
                    Boss-/Icon-Scans und die Aufnahme
    web/index.html  semantischer Aufbau — ohne Framework, ohne Netz
    web/styles.css  Darstellung und responsive Layoutregeln
    web/app.js      Interaktion und Brückenaufrufe
"""
