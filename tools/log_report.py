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


def _lies(pfad: Path) -> list[dict]:
    try:
        with open(pfad, "r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except (IOError, OSError, csv.Error) as e:
        print(f"  ! {pfad.name}: nicht lesbar ({e})")
        return []


def _dauer(zeilen: list[dict]) -> float:
    """Laufzeit der Session in Sekunden (aus elapsed_sec der letzten Zeile)."""
    for z in reversed(zeilen):
        try:
            return float(z.get("elapsed_sec") or 0)
        except ValueError:
            continue
    return 0.0


def _fmt_dauer(sek: float) -> str:
    h, rest = divmod(int(sek), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def bericht(pfade: list[Path]) -> None:
    gesamt_events = Counter()
    timeouts_je_schritt = Counter()
    items = Counter()
    erkannt = Counter()
    verify_miss = Counter()
    verify_ok = Counter()
    sessions = 0
    gesamt_dauer = 0.0

    for pfad in pfade:
        zeilen = _lies(pfad)
        if not zeilen:
            continue
        sessions += 1
        gesamt_dauer += _dauer(zeilen)
        for z in zeilen:
            ev = z.get("event", "")
            gesamt_events[ev] += 1
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

    if not sessions:
        print("Keine lesbaren Logs gefunden.")
        return

    print("=" * 66)
    print(f"  {sessions} Session(s)  |  Laufzeit gesamt: {_fmt_dauer(gesamt_dauer)}")
    print("=" * 66)

    klicks = gesamt_events.get("click", 0)
    print(f"\nAktionen: {klicks} Klick(s), {gesamt_events.get('key', 0)} Taste(n), "
          f"{gesamt_events.get('scroll', 0)} Scroll(s)")
    if gesamt_dauer > 0 and klicks:
        print(f"          {klicks / (gesamt_dauer / 3600):.0f} Klicks/Stunde")

    # DIE Frage, fuer die es das Werkzeug gibt
    if timeouts_je_schritt:
        print(f"\n{'-' * 66}\nTIMEOUTS — wo die Sequenz haengt "
              f"({sum(timeouts_je_schritt.values())} gesamt):")
        for name, n in timeouts_je_schritt.most_common(10):
            print(f"  {n:>5}x  {name}")
        print("       Der oberste Eintrag ist der Schritt, den es zu reparieren lohnt.")
    else:
        print("\nKeine Timeouts — jede Farb-Bedingung ist aufgegangen.")

    # Nachpruefung: wie oft musste wiederholt werden?
    if verify_ok or verify_miss:
        print(f"\n{'-' * 66}\nNACHPRUEFUNG:")
        print(f"  {sum(verify_ok.values())}x bestaetigt, "
              f"{sum(verify_miss.values())}x ohne Wirkung")
        for name, n in verify_miss.most_common(10):
            gut = verify_ok.get(name, 0)
            quote = f"{gut}/{gut + n}" if (gut + n) else "-"
            print(f"  {n:>5}x ohne Wirkung  {name}   (bestaetigt: {quote})")
        if verify_miss:
            print("       Haeufige Fehlschlaege heissen: Klickziel sitzt falsch oder das "
                  "Spiel\n       braucht laenger als verify_timeout.")

    if items:
        print(f"\n{'-' * 66}\nGEFUNDENE ITEMS ({sum(items.values())} gesamt):")
        for name, n in items.most_common(15):
            print(f"  {n:>5}x  {name}")

    if erkannt:
        print(f"\n{'-' * 66}\nERKANNT (Boss/Icon):")
        for name, n in erkannt.most_common(10):
            print(f"  {n:>5}x  {name}")

    stoerungen = {k: v for k, v in gesamt_events.items()
                  if k.startswith(("focus_", "humanize_"))}
    if stoerungen:
        print(f"\n{'-' * 66}\nUNTERBRECHUNGEN:")
        for k, v in sorted(stoerungen.items()):
            print(f"  {v:>5}x  {k}")

    unbekannt = set(gesamt_events) - _RAHMEN - {
        "click", "key", "scroll", "timeout", "item_found", "detected",
        "verify_ok", "verify_miss"} - set(stoerungen)
    if unbekannt:
        # Neue Ereignisarten sollen hier auffallen, nicht stillschweigend fehlen.
        print(f"\n  Nicht ausgewertete Ereignisarten: {', '.join(sorted(unbekannt))}")


def main() -> int:
    args = [a for a in sys.argv[1:] if a]
    if args and args[0] not in ("--letzte", "--last"):
        pfade = [Path(a) for a in args]
        fehlend = [p for p in pfade if not p.exists()]
        if fehlend:
            print(f"Nicht gefunden: {', '.join(str(p) for p in fehlend)}")
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

    bericht(pfade)
    return 0


if __name__ == "__main__":
    sys.exit(main())
