#!/usr/bin/env python3
"""Wertet die Session-Logs aus: welcher Schritt haengt, was wurde gefunden, wie lief die Nacht.

Die Logs wurden bisher nur geschrieben und von nichts gelesen. Sie beantworten aber
genau die Frage, die man nach einem langen Lauf hat und heute nur raten kann:
**welcher Schritt laeuft am haeufigsten in den Timeout?**

    python tools/log_report.py              # alle Logs im logs/-Ordner
    python tools/log_report.py <datei.csv>  # eine bestimmte Session
    python tools/log_report.py --letzte     # nur die neueste Session

Laeuft ohne Windows und ohne Abhaengigkeiten (nur csv/pathlib aus der Standardbibliothek):
die Auswertung soll auch dort gehen, wo der Autoclicker gar nicht startet.
"""

import csv
import sys
from collections import Counter
from pathlib import Path

# Ohne Import aus autoclicker/: das Werkzeug liest CSV, sonst nichts. Ein Import
# zoege die Konsolen-Erkennung und ctypes mit rein - auf Linux waere Schluss.
LOGS_DIR = Path("logs")

# Ereignisse, die kein Zaehlwerk brauchen (Rahmen der Session)
_RAHMEN = {"session_start", "session_end"}

# Ereignisarten, die dieser Bericht wirklich auswertet. Stand als Menge mitten in der
# Ausgabefunktion; als Konstante ist die Kopplung zu `session_log.py` benennbar und
# messbar - ein Test haelt beide Seiten gegeneinander. Wer eine neue Ereignisart
# einfuehrt, traegt sie hier ein; bis dahin meldet der Bericht sie als "nicht
# ausgewertet", statt sie stillschweigend zu verschlucken.
AUSGEWERTET = {
    "click", "key", "scroll", "timeout", "item_found", "detected",
    "verify_ok", "verify_miss",
}


def _lies(path: Path) -> tuple[list[dict], str]:
    """Zeilen der Datei und, falls sie nicht lesbar war, der Grund.

    Der Grund wird zurueckgegeben statt gedruckt: `auswerten()` darf nichts
    ausgeben, sonst landet er in der Konsole des Studios statt in seinem
    Bericht-Reiter.
    """
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f)), ""
    except (IOError, OSError, csv.Error) as e:
        return [], str(e)


def _dauer(lines: list[dict]) -> float:
    """Laufzeit der Session in Sekunden (aus elapsed_sec der letzten Zeile)."""
    for z in reversed(lines):
        try:
            return float(z.get("elapsed_sec") or 0)
        except ValueError:
            continue
    return 0.0


def _fmt_dauer(sek: float) -> str:
    h, remainder = divmod(int(sek), 3600)
    m, s = divmod(remainder, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _rang(zaehler: Counter) -> list[list]:
    """Counter als absteigend sortierte Paarliste — JSON-tauglich und stabil."""
    return [[name, n] for name, n in zaehler.most_common()]


def auswerten(pfade: list[Path]) -> dict:
    """Wertet Session-Logs aus und gibt reine Daten zurueck — ohne eine Zeile Ausgabe.

    Getrennt von `report()`, weil der Bericht-Reiter des Studios dieselbe
    Auswertung braucht und mit gedrucktem Text nichts anfangen kann. Die
    Richtung bleibt dabei, wie sie war: dieses Werkzeug importiert nichts aus
    `autoclicker/` — die Bruecke ruft es, nicht umgekehrt.

    Die Zahlen kommen doppelt zurueck: einmal ueber alle Dateien zusammen (das,
    was der Bericht zeigt) und einmal je Sitzung (die Liste, aus der man eine
    auswaehlt). Zweimal zu lesen waere der naheliegende Weg und der falsche —
    bei einer Nacht voller Logs liest man dann jede Datei doppelt.
    """
    gesamt_events = Counter()
    timeouts_je_schritt = Counter()
    items = Counter()
    erkannt = Counter()
    verify_miss = Counter()
    verify_ok = Counter()
    sitzungen = []
    nicht_lesbar = []
    gesamt_dauer = 0.0

    for path in pfade:
        lines, fehler = _lies(path)
        if fehler:
            nicht_lesbar.append([path.name, fehler])
            continue
        if not lines:
            continue
        duration = _dauer(lines)
        gesamt_dauer += duration
        eigen = Counter()
        for z in lines:
            ev = z.get("event", "")
            gesamt_events[ev] += 1
            eigen[ev] += 1
            detail = (z.get("detail") or "").strip()
            if ev == "timeout":
                timeouts_je_schritt[detail or "(ohne Namen)"] += 1
            elif ev == "item_found":
                items[detail] += 1
            elif ev == "detected":
                erkannt[detail] += 1
            elif ev == "verify_miss":
                verify_miss[detail or "(ohne Namen)"] += 1
            elif ev == "verify_ok":
                verify_ok[detail or "(ohne Namen)"] += 1
        sitzungen.append({
            "datei": path.name,
            "beginn": (lines[0].get("timestamp") or "").strip(),
            "dauer": duration,
            "klicks": eigen.get("click", 0),
            "timeouts": eigen.get("timeout", 0),
            "items": eigen.get("item_found", 0),
            "verify_miss": eigen.get("verify_miss", 0),
        })

    stoerungen = {k: v for k, v in gesamt_events.items()
                  if k.startswith(("focus_", "humanize_"))}
    unbekannt = set(gesamt_events) - _RAHMEN - AUSGEWERTET - set(stoerungen)
    return {
        "sitzungen": sitzungen,
        "nicht_lesbar": nicht_lesbar,
        "dauer": gesamt_dauer,
        "ereignisse": dict(gesamt_events),
        "timeouts": _rang(timeouts_je_schritt),
        "items": _rang(items),
        "erkannt": _rang(erkannt),
        "verify_miss": _rang(verify_miss),
        "verify_ok": dict(verify_ok),
        "stoerungen": sorted([k, v] for k, v in stoerungen.items()),
        "unbekannt": sorted(unbekannt),
    }


def report(pfade: list[Path]) -> None:
    data = auswerten(pfade)
    for file, fehler in data["nicht_lesbar"]:
        print(f"  ! {file}: nicht lesbar ({fehler})")

    sessions = len(data["sitzungen"])
    if not sessions:
        print("Keine lesbaren Logs gefunden.")
        return

    gesamt_events = data["ereignisse"]
    timeouts_je_schritt = data["timeouts"]
    verify_miss = data["verify_miss"]
    verify_ok = data["verify_ok"]
    gesamt_dauer = data["dauer"]

    print("=" * 66)
    print(f"  {sessions} Session(s)  |  Laufzeit gesamt: {_fmt_dauer(gesamt_dauer)}")
    print("=" * 66)

    clicks = gesamt_events.get("click", 0)
    print(f"\nAktionen: {clicks} Klick(s), {gesamt_events.get('key', 0)} Taste(n), "
          f"{gesamt_events.get('scroll', 0)} Scroll(s)")
    if gesamt_dauer > 0 and clicks:
        print(f"          {clicks / (gesamt_dauer / 3600):.0f} Klicks/Stunde")

    # DIE Frage, fuer die es das Werkzeug gibt
    if timeouts_je_schritt:
        print(f"\n{'-' * 66}\nTIMEOUTS — wo die Sequenz haengt "
              f"({sum(n for _, n in timeouts_je_schritt)} gesamt):")
        for name, n in timeouts_je_schritt[:10]:
            print(f"  {n:>5}x  {name}")
        print("       Der oberste Eintrag ist der Schritt, den es zu reparieren lohnt.")
    else:
        print("\nKeine Timeouts — jede Farb-Bedingung ist aufgegangen.")

    # Nachpruefung: wie oft musste wiederholt werden?
    if verify_ok or verify_miss:
        print(f"\n{'-' * 66}\nNACHPRUEFUNG:")
        print(f"  {sum(verify_ok.values())}x bestaetigt, "
              f"{sum(n for _, n in verify_miss)}x ohne Wirkung")
        for name, n in verify_miss[:10]:
            gut = verify_ok.get(name, 0)
            quote = f"{gut}/{gut + n}" if (gut + n) else "-"
            print(f"  {n:>5}x ohne Wirkung  {name}   (bestaetigt: {quote})")
        if verify_miss:
            print("       Haeufige Fehlschlaege heissen: Klickziel sitzt falsch oder das "
                  "Spiel\n       braucht laenger als verify_timeout.")

    if data["items"]:
        print(f"\n{'-' * 66}\nGEFUNDENE ITEMS "
              f"({sum(n for _, n in data['items'])} gesamt):")
        for name, n in data["items"][:15]:
            print(f"  {n:>5}x  {name}")

    if data["erkannt"]:
        print(f"\n{'-' * 66}\nERKANNT (Boss/Icon):")
        for name, n in data["erkannt"][:10]:
            print(f"  {n:>5}x  {name}")

    if data["stoerungen"]:
        print(f"\n{'-' * 66}\nUNTERBRECHUNGEN:")
        for k, v in data["stoerungen"]:
            print(f"  {v:>5}x  {k}")

    if data["unbekannt"]:
        # Neue Ereignisarten sollen hier auffallen, nicht stillschweigend fehlen.
        print(f"\n  Nicht ausgewertete Ereignisarten: {', '.join(data['unbekannt'])}")


def main() -> int:
    args = [a for a in sys.argv[1:] if a]
    if args and args[0] not in ("--letzte", "--last"):
        pfade = [Path(a) for a in args]
        missing = [p for p in pfade if not p.exists()]
        if missing:
            print(f"Nicht gefunden: {', '.join(str(p) for p in missing)}")
            return 1
    else:
        if not LOGS_DIR.is_dir():
            print(f"Kein Ordner '{LOGS_DIR}' — ist session_log_enabled in der config.json an?")
            return 1
        pfade = sorted(LOGS_DIR.glob("*.csv"))
        if not pfade:
            print(f"Keine CSV-Dateien in '{LOGS_DIR}'.")
            return 1
        if args:                       # --letzte
            pfade = pfade[-1:]
            print(f"Neueste Session: {pfade[0].name}\n")

    report(pfade)
    return 0


if __name__ == "__main__":
    sys.exit(main())
