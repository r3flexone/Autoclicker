"""
Sequenz-Studio: Phasen und Schritte visuell bearbeiten (Weboberfläche).

Läuft als separater Subprocess (siehe autoclicker/sequence_studio.py), damit der
Fenster-Event-Loop nicht mit der Windows-Hotkey-Message-Pump im Hauptprozess
kollidiert. Liest/schreibt dieselben sequences/<name>.json Dateien wie der
Konsolen-Editor — der Executor bemerkt keinen Unterschied.

Modul-Aufteilung:
    model.py        GUI-freier Layer: Sequence ↔ Lanes/Blöcke (verlustfreier Round-Trip)
    bridge.py       Editor-Logik + die einzige Verbindung zur Oberfläche (testbar)
    scans.py        Slots, Items, Erkennung und Lernablauf
    scan_capture.py Screenshot-, Fenster- und Aufnahmezustand
    web/index.html  semantischer Aufbau — ohne Framework, ohne Netz
    web/styles.css  Darstellung und responsive Layoutregeln
    web/app.js       Interaktion und Brückenaufrufe
"""
