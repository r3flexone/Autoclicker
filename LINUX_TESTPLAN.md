# Manueller Plattform-Testplan

Stand: 2026-08-19, Branch `agent/studio-cleanup`.

Die automatischen Tests laufen ohne grafische Sitzung. Dieser Plan deckt die
Systemgrenzen ab, die nur auf echten Desktops sinnvoll prüfbar sind.

## Automatisierter Stand

- `python -m unittest -v test_*.py`: 64 Tests erfolgreich.
- `python tools/test_logic.py`: 1275 Prüfungen, 0 Fehler.
- Pyflakes-Lint erfolgreich.
- GitHub Actions auf Ubuntu und Windows erfolgreich.

## Linux/X11

Voraussetzung: Python 3.10+, auf Debian/Ubuntu gegebenenfalls `build-essential`
und `python3-dev`, danach `pip install -r requirements.txt` sowie eine echte
X11-Sitzung (`echo $XDG_SESSION_TYPE` gibt `x11` aus).

1. `python main.py` starten. Der Banner nennt `LINUX/X11`; es erscheint keine
   Plattform- oder Abhängigkeitswarnung.
2. `CTRL+ALT+A` drücken. Mausposition und Pixel-Farbe werden plausibel erfasst.
3. Eine kurze Sequenz mit Klick, Taste und Mausrad aufnehmen und abspielen.
4. Pause, Skip, Start/Stop und Beenden über globale Hotkeys prüfen.
5. Mit zwei Monitoren je einen Punkt aufnehmen, auch links/oberhalb des
   Primärmonitors. Screenshot und Klick müssen dieselben Koordinaten verwenden.
6. Im Scan-Studio ein sichtbares Spielfenster auswählen, verschieben und erneut
   scannen. Fensterrechteck und Slots müssen dem Fenster folgen.
7. Fokusprüfung aktivieren, zu einem fremden Fenster wechseln und verifizieren,
   dass die konfigurierte Pause-/Stop-Aktion greift.
8. Maus in die konfigurierte obere linke Fail-safe-Ecke bewegen; der Lauf muss
   stoppen.

Linux/X11 kann verdeckte Fenster nicht wie Windows per `PrintWindow` direkt
rendern. Die Anwendung meldet den sichtbaren Desktop-Fallback; beim Scan darf
dann kein anderes Fenster vor dem Ziel liegen.

## Wayland (negativer Test)

1. In einer Wayland-Sitzung `python main.py` starten.
2. Der Start muss Wayland ausdrücklich als nicht unterstützt melden.
3. Globale Hotkeys und Eingabesimulation dürfen nicht als erfolgreich gemeldet
   werden. Wechsel für den produktiven Betrieb am Login-Bildschirm zu X11.

## Windows 10/11 (Regression)

1. `pip install -r requirements.txt` und `python main.py` ausführen.
2. Aufnahme und Wiedergabe für Klick, Taste und Mausrad prüfen.
3. Alle globalen Hotkeys, Fokusprüfung, Fail-safe und Multi-Monitor prüfen.
4. Vollbild-, Bereichs- und direkte Fensteraufnahme im Scan-Studio prüfen.
5. `python -m unittest -v test_*.py` ausführen.
