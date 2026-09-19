#!/usr/bin/env python3
"""EIN Kommando für alle Tests: `python tests/alle_tests.py`.

**Warum es das gibt.** Es waren zwei Kommandos, und das stand als Warnung in
CLAUDE.md, weil genau diese Lücke schon einmal einen roten CI-Lauf gekostet hat:
`tests/test_logic.py` war grün, gemeldet wurde „alles grün", und die
Wurzelmodule liefen nie. Eine Regel, an die man sich erinnern muss, ist keine.

Der Grund für die Trennung ist inzwischen weg: die beiden Wurzelmodule, die
Pillow schon beim Import brauchten, überspringen jetzt sauber. Damit läuft alles
mit jedem Interpreter, und es braucht nur noch einen Aufruf.

Drei Schichten, von innen nach aussen:

| Schicht | was sie prüft | braucht |
|---|---|---|
| Vertragssuite (`test_logic.py`) | Logik ohne GUI, ohne Windows, ohne Netz | nichts |
| Wurzelmodule (`tests/wurzel/`) | Import/Export, Plattformvertrag, Studio-UX | Pillow (sonst übersprungen) |
| Rauchtests (`tests/rauch/`) | die echte Seite im Browser vor der echten Brücke | Playwright + Chromium |

Jede Schicht ist einzeln aufrufbar (`--nur vertrag|wurzel|rauch`) — beim
Arbeiten an einer Sache will man nicht auf die anderen warten. Der Volllauf ist
der vor dem Commit.

Was fehlt, wird ÜBERSPRUNGEN und gesagt, nicht als Fehler gemeldet: ein roter
Lauf, der nur die Testumgebung beschreibt, verdeckt echte Fehler im Rauschen.
Im Browser-CI macht --rauch-pflicht diese Schicht verbindlich.
--mutationen ergänzt gezielte Gegenproben in getrennten Prozessen.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]

# **Der Runner darf nicht an der Konsole sterben, an der er berichtet.** Die
# Unterprozesse laufen laengst auf UTF-8 (`_lauf`), ihre Ausgabe wird hier aber
# auf STDOUT DIESES Prozesses durchgereicht - und der ist auf einer deutschen
# Windows-Konsole cp1252. Ein einziges Kaestchen aus einem Fortschrittsbalken
# riss damit den ganzen Lauf mit `UnicodeEncodeError` ab, nachdem die
# Vertragssuite bereits gruen durchgelaufen war: hinter einer Pipe blieb davon
# nur ein Traceback und ein Exitcode, den niemand mehr las. `errors="replace"`
# statt eines harten Fehlers - ein unbekanntes Zeichen ist ein Darstellungs-
# problem, kein Testergebnis.
for _strom in (sys.stdout, sys.stderr):
    if hasattr(_strom, "reconfigure"):
        _strom.reconfigure(encoding="utf-8", errors="replace")

# Die Rauchtests, in der Reihenfolge, in der sie aufeinander aufbauen: erst was
# die Scans zeigen, dann die Reiter darum herum.
RAUCHTESTS = ("items", "erkennung", "sequences", "teilen", "werkzeuge",
              "bericht", "sequenzen_loeschen", "catalog")

SCHICHTEN = ("vertrag", "wurzel", "rauch")


class Ergebnis:
    """Was eine Schicht ergeben hat. `skipped` ist kein Fehlschlag."""

    def __init__(self, name: str):
        self.name = name
        self.ok = True
        self.skipped = ""
        self.zusammenfassung = ""
        self.duration = 0.0

    def __str__(self) -> str:
        if self.skipped:
            return f"  ÜBERSPRUNGEN  {self.name:<14} {self.skipped}"
        badge = "OK  " if self.ok else "FAIL"
        return (f"  {badge}          {self.name:<14} {self.zusammenfassung}"
                f"  ({self.duration:.1f}s)")


def _lauf(command: list[str], umgebung: dict | None = None) -> tuple[int, str]:
    """Ein Unterprozess mit geerbter Ausgabe — und dem Text zum Auswerten.

    Warum als Unterprozess und nicht per Import: die Vertragssuite stubbt
    `msvcrt` und `ctypes.windll` beim Import und wechselt das Arbeitsverzeichnis.
    In denselben Interpreter geladen faerbte sie damit alles, was danach kommt.
    """
    umw = os.environ.copy()
    umw["PYTHONUTF8"] = "1"
    umw["PYTHONIOENCODING"] = "utf-8"
    umw.update(umgebung or {})
    done = subprocess.run(command, cwd=WURZEL, env=umw, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    sys.stdout.write(done.stdout)
    sys.stderr.write(done.stderr)
    return done.returncode, done.stdout + done.stderr


def vertrag() -> Ergebnis:
    e = Ergebnis("Vertragssuite")
    start = time.monotonic()
    code, text = _lauf([sys.executable, str(WURZEL / "tests" / "test_logic.py")])
    e.duration = time.monotonic() - start
    e.ok = code == 0
    for line in reversed(text.splitlines()):
        if " PASS / " in line:
            e.zusammenfassung = line.strip().strip("= ")
            break
    statistik = re.fullmatch(r"([1-9][0-9]*) PASS / 0 FAIL", e.zusammenfassung)
    e.ok = e.ok and statistik is not None
    if not e.zusammenfassung:
        e.zusammenfassung = "Abschluss der Vertragssuite fehlt"
    return e


def root_dir(vertrag_separat: bool = False) -> Ergebnis:
    """Die Wurzeltests; im Gesamtlauf wurde der Vertragswrapper schon ausgeführt.

    `discover` statt eines Glob-Musters: die Shell expandiert `test_*.py` auf
    Linux und Windows verschieden, und PowerShell reicht es woertlich weiter.
    """
    e = Ergebnis("Wurzelmodule")
    start = time.monotonic()
    command = [sys.executable, "-m", "tests.wurzeltests"]
    if vertrag_separat:
        command.append("--ohne-vertrag")
    code, text = _lauf(command)
    e.duration = time.monotonic() - start
    e.ok = code == 0
    for line in reversed(text.splitlines()):
        if line.startswith("Ran ") or line.startswith("OK") or "FAILED" in line:
            e.zusammenfassung = line.strip()
            break
    return e


def rauch(nur: tuple[str, ...] = RAUCHTESTS, pflicht: bool = False) -> Ergebnis:
    e = Ergebnis("Rauchtests")
    sys.path.insert(0, str(WURZEL))
    from tests.rauch._bruecke import playwright_da

    da, reason = playwright_da()
    if not da:
        if pflicht:
            e.ok = False
            e.zusammenfassung = f"Pflichtprüfung nicht ausführbar: {reason}"
        else:
            e.skipped = reason
        return e

    start = time.monotonic()
    fehlgeschlagen = []
    for name in nur:
        code, _ = _lauf([sys.executable, "-m", f"tests.rauch.{name}"])
        if code != 0:
            fehlgeschlagen.append(name)
    e.duration = time.monotonic() - start
    e.ok = not fehlgeschlagen
    e.zusammenfassung = (f"{len(nur)} Ansichten"
                         + (f", rot: {', '.join(fehlgeschlagen)}" if fehlgeschlagen else ""))
    return e


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--nur", choices=SCHICHTEN, action="append",
                   help="nur diese Schicht (mehrfach erlaubt)")
    p.add_argument("--rauchtest", action="append", choices=RAUCHTESTS,
                   help="nur diesen Rauchtest")
    p.add_argument("--rauch-pflicht", action="store_true",
                   help="fehlenden Browser als Fehler melden (Browser-CI)")
    p.add_argument("--mutationen", action="store_true",
                   help="zusätzlich gezielte Fehler einschleusen und ihre Erkennung prüfen")
    args = p.parse_args(argv[1:])
    schichten = tuple(args.nur) if args.nur else SCHICHTEN
    if args.rauch_pflicht and "rauch" not in schichten:
        p.error("--rauch-pflicht braucht die Schicht rauch")

    results_list = []
    if "vertrag" in schichten:
        results_list.append(vertrag())
    if "wurzel" in schichten:
        results_list.append(root_dir(vertrag_separat="vertrag" in schichten))
    if "rauch" in schichten:
        results_list.append(rauch(tuple(args.rauchtest) if args.rauchtest else RAUCHTESTS,
                                 pflicht=args.rauch_pflicht))
    if args.mutationen:
        e = Ergebnis("Gegenproben")
        start = time.monotonic()
        code, _ = _lauf([sys.executable, str(WURZEL / "tests" / "mutationspruefung.py")])
        e.ok = code == 0
        e.duration = time.monotonic() - start
        e.zusammenfassung = "gezielte Mutationsprüfung"
        results_list.append(e)

    width = 78
    print("\n" + "=" * width)
    for e in results_list:
        print(e)
    print("=" * width)

    rot = [e.name for e in results_list if not e.ok]
    if rot:
        print(f"  {len(rot)} Schicht(en) rot: {', '.join(rot)}")
        return 1
    fehlt = [e for e in results_list if e.skipped]
    print("  alles grün"
          + (f" ({len(fehlt)} Schicht übersprungen)" if fehlt else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
