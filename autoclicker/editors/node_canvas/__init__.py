"""
Visueller Node-Editor für Sequenzen (Dear PyGui).

Läuft als separater Subprocess (siehe autoclicker/node_editor.py), damit der
GUI-Event-Loop nicht mit der Windows-Hotkey-Message-Pump im Hauptprozess
kollidiert. Liest/schreibt dieselben sequences/<name>.json Dateien wie der
Konsolen-Editor — der Executor bemerkt keinen Unterschied.

Modul-Aufteilung:
    model.py       GUI-freier Layer: Sequence ↔ Lanes/Blöcke (verlustfreier Round-Trip)
    canvas_dpg.py  Dear PyGui Renderer (Lanes, Blöcke, Pfeile, Punkte-Palette)
    panels.py      Eigenschaften-Formulare je Block-Typ
"""
