#!/usr/bin/env python3
"""Wertet die Session-Logs aus: welcher Schritt haengt, was wurde gefunden, wie lief die Nacht.

Die Logs wurden bisher nur geschrieben und von nichts gelesen. Sie beantworten aber
genau die Frage, die man nach einem langen Lauf hat und heute nur raten kann:
**welcher Schritt laeuft am haeufigsten in den Timeout?**

    python tools/log_report.py              # alle Logs im logs/-Ordner
    python tools/log_report.py <datei.csv>  # eine bestimmte Session
    python tools/log_report.py --last     # nur die neueste Session

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
_FRAME = {"session_start", "session_end"}

# Ereignisarten, die dieser Bericht wirklich auswertet. Stand als Menge mitten in der
# Ausgabefunktion; als Konstante ist die Kopplung zu `session_log.py` benennbar und
# messbar - ein Test haelt beide Seiten gegeneinander. Wer eine neue Ereignisart
# einfuehrt, traegt sie hier ein; bis dahin meldet der Bericht sie als "nicht
# ausgewertet", statt sie stillschweigend zu verschlucken.
EVALUATED = {
    "click", "key", "timeout", "item_found", "detected",
    "verify_ok", "verify_miss", "wait", "color_wait", "pause",
}


def _read(path: Path) -> tuple[list[dict], str]:
    """Zeilen der Datei und, falls sie nicht lesbar war, der Grund.

    Der Grund wird zurueckgegeben statt gedruckt: `evaluate()` darf nichts
    ausgeben, sonst landet er in der Konsole des Studios statt in seinem
    Bericht-Reiter.
    """
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f)), ""
    except (IOError, OSError, csv.Error) as e:
        return [], str(e)


def _duration(lines: list[dict]) -> float:
    """Laufzeit der Session in Sekunden (aus elapsed_sec der letzten Zeile)."""
    for z in reversed(lines):
        try:
            return float(z.get("elapsed_sec") or 0)
        except ValueError:
            continue
    return 0.0


def _fmt_duration(sec: float) -> str:
    h, remainder = divmod(int(sec), 3600)
    m, s = divmod(remainder, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _extra(line: dict) -> dict:
    """Die Spalte `extra` als Schluessel/Wert: `s=1.50,result=ok`."""
    out = {}
    for part in (line.get("extra") or "").split(","):
        key, _, value = part.partition("=")
        if key.strip():
            out[key.strip()] = value.strip()
    return out


def _seconds(line: dict) -> float:
    try:
        return max(0.0, float(_extra(line).get("s", 0) or 0))
    except ValueError:
        return 0.0


def _rank_waits(table: dict) -> list[list]:
    """`{Name: [Sekunden, Anzahl, laengste, Timeouts]}` absteigend nach Sekunden."""
    rows = [[name, round(v[0], 2), v[1], round(v[2], 2), v[3]]
            for name, v in table.items()]
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


def _rank(counters: Counter) -> list[list]:
    """Counter als absteigend sortierte Paarliste — JSON-tauglich und stabil."""
    return [[name, n] for name, n in counters.most_common()]


def _sequence_name(path: Path, lines: list[dict]) -> str:
    """Welche Sequenz lief — der Name, wie ihn der Nutzer vergeben hat.

    `session_start` traegt ihn im Detail (`worker.py`). Der Dateiname kennt nur
    die bereinigte Form (`all_dayli` statt `All Dayli`) und ist deshalb erst der
    Rueckfall — fuer Logs ohne Startzeile, etwa von Hand gekuerzte.
    """
    for z in lines:
        if z.get("event") == "session_start":
            name = (z.get("detail") or "").strip()
            if name:
                return name
            break
    parts = path.stem.split("_", 2)
    return parts[2] if len(parts) == 3 else path.stem


def evaluate(paths: list[Path]) -> dict:
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
    total_events = Counter()
    counters = {name: Counter() for name, _unnamed in _COUNTED.values()}
    sessions = []
    unreadable = []
    total_duration = 0.0
    # Wartezeiten, getrennt nach dem, der sie bestimmt: `wait` ist eingestellt
    # (Wartezeit am Block), `color_wait` hat das Spiel entschieden (Farb-
    # Trigger), `pause` der Nutzer. Je Block: [Sekunden, Anzahl, laengste,
    # davon Timeouts].
    per_step = {"planned": {}, "color": {}}
    waits = {"planned": 0.0, "color": 0.0, "pause": 0.0,
             "measured_duration": 0.0, "measured_sessions": 0}

    for path in paths:
        lines, error = _read(path)
        if error:
            unreadable.append([path.name, error])
            continue
        if not lines:
            continue
        duration = _duration(lines)
        total_duration += duration
        own = Counter()
        own_waits = {"planned": 0.0, "color": 0.0, "pause": 0.0}
        for z in lines:
            ev = z.get("event", "")
            total_events[ev] += 1
            own[ev] += 1
            _tally_line(z, ev, counters, own_waits, per_step)
        sessions.append(_session_row(path, lines, duration, own, own_waits))
        if sessions[-1]["waits_measured"]:
            for k in ("planned", "color", "pause"):
                waits[k] += own_waits[k]
            waits["measured_duration"] += duration
            waits["measured_sessions"] += 1

    disturbances = {k: v for k, v in total_events.items()
                  if k.startswith(("focus_", "humanize_"))}
    unknown = set(total_events) - _FRAME - EVALUATED - set(disturbances)
    return {
        "sessions": sessions,
        "unreadable": unreadable,
        "duration": total_duration,
        "events": dict(total_events),
        "timeouts": _rank(counters["timeouts"]),
        "items": _rank(counters["items"]),
        "detected": _rank(counters["detected"]),
        "verify_miss": _rank(counters["verify_miss"]),
        "verify_ok": dict(counters["verify_ok"]),
        "disturbances": sorted([k, v] for k, v in disturbances.items()),
        "unknown": sorted(unknown),
        "waits": {k: (round(v, 2) if isinstance(v, float) else v)
                  for k, v in waits.items()},
        "planned_waits": _rank_waits(per_step["planned"]),
        "color_waits": _rank_waits(per_step["color"]),
    }


_UNNAMED = "(ohne Namen)"

# Ereignisse, die nur gezählt werden: Ereignis → (Zähler, ob ein leerer Name
# als „(ohne Namen)" zählt). Ein Item ohne Namen bleibt ohne — es gibt keins.
_COUNTED = {
    "timeout": ("timeouts", True),
    "item_found": ("items", False),
    "detected": ("detected", False),
    "verify_miss": ("verify_miss", True),
    "verify_ok": ("verify_ok", True),
}


def _tally_line(z: dict, ev: str, counters: dict, own_waits: dict, per_step: dict) -> None:
    """Zählt EINE Log-Zeile: in ihren Zähler, ihre Wartezeit oder ihre Pause."""
    detail = (z.get("detail") or "").strip()
    if ev in _COUNTED:
        name, unnamed = _COUNTED[ev]
        counters[name][(detail or _UNNAMED) if unnamed else detail] += 1
    elif ev in ("wait", "color_wait"):
        kind = "planned" if ev == "wait" else "color"
        sec = _seconds(z)
        own_waits[kind] += sec
        row = per_step[kind].setdefault(detail or _UNNAMED, [0.0, 0, 0.0, 0])
        row[0] += sec
        row[1] += 1
        row[2] = max(row[2], sec)
        if _extra(z).get("result") == "timeout":
            row[3] += 1
    elif ev == "pause":
        own_waits["pause"] += _seconds(z)


def _session_row(path: Path, lines: list[dict], duration: float, own: Counter,
                 own_waits: dict) -> dict:
    """Die Zeile einer Sitzung in der Liste des Reiters."""
    return {
        "file": path.name,
        "sequence": _sequence_name(path, lines),
        "begin": (lines[0].get("timestamp") or "").strip(),
        "duration": duration,
        "clicks": own.get("click", 0),
        "timeouts": own.get("timeout", 0),
        "items": own.get("item_found", 0),
        "verify_miss": own.get("verify_miss", 0),
        # Ein Log von vor der Wartezeit-Erfassung hat keine dieser Zeilen.
        # Es zaehlt dann nicht mit, statt seine ganze Laufzeit als „Rest"
        # auszuweisen.
        "waits_measured": bool(own.get("wait") or own.get("color_wait")),
        "planned": round(own_waits["planned"], 2),
        "color": round(own_waits["color"], 2),
    }


_RULE = "-" * 66


def report(paths: list[Path]) -> None:
    data = evaluate(paths)
    for file, error in data["unreadable"]:
        print(f"  ! {file}: nicht lesbar ({error})")

    sessions = len(data["sessions"])
    if not sessions:
        print("Keine lesbaren Logs gefunden.")
        return

    total_events = data["events"]
    total_duration = data["duration"]

    print("=" * 66)
    print(f"  {sessions} Session(s)  |  Laufzeit gesamt: {_fmt_duration(total_duration)}")
    print("=" * 66)

    clicks = total_events.get("click", 0)
    print(f"\nAktionen: {clicks} Klick(s), {total_events.get('key', 0)} Taste(n)")
    if total_duration > 0 and clicks:
        print(f"          {clicks / (total_duration / 3600):.0f} Klicks/Stunde")

    for part in (_report_timeouts, _report_verify, _report_waits, _report_findings):
        part(data)


def _report_timeouts(data: dict) -> None:
    """DIE Frage, fuer die es das Werkzeug gibt."""
    timeouts_per_step = data["timeouts"]
    if not timeouts_per_step:
        print("\nKeine Timeouts — jede Farb-Bedingung ist aufgegangen.")
        return
    print(f"\n{_RULE}\nTIMEOUTS — wo die Sequenz haengt "
          f"({sum(n for _, n in timeouts_per_step)} gesamt):")
    for name, n in timeouts_per_step[:10]:
        print(f"  {n:>5}x  {name}")
    print("       Der oberste Eintrag ist der Schritt, den es zu reparieren lohnt.")


def _report_verify(data: dict) -> None:
    """Nachpruefung: wie oft musste wiederholt werden?"""
    verify_miss, verify_ok = data["verify_miss"], data["verify_ok"]
    if not (verify_ok or verify_miss):
        return
    print(f"\n{_RULE}\nNACHPRUEFUNG:")
    print(f"  {sum(verify_ok.values())}x bestaetigt, "
          f"{sum(n for _, n in verify_miss)}x ohne Wirkung")
    for name, n in verify_miss[:10]:
        good = verify_ok.get(name, 0)
        quote = f"{good}/{good + n}" if (good + n) else "-"
        print(f"  {n:>5}x ohne Wirkung  {name}   (bestaetigt: {quote})")
    if verify_miss:
        print("       Haeufige Fehlschlaege heissen: Klickziel sitzt falsch oder das "
              "Spiel\n       braucht laenger als verify_timeout.")


def _report_waits(data: dict) -> None:
    """Die Laufzeit aufgeteilt — nur über die Sitzungen, die Wartezeiten mitschreiben."""
    waits = data["waits"]
    if not waits["measured_sessions"]:
        return
    span = waits["measured_duration"]
    rest = max(0.0, span - waits["planned"] - waits["color"] - waits["pause"])
    print(f"\n{_RULE}\nWARTEZEITEN ({waits['measured_sessions']} "
          f"Session(s) mit Messung, {_fmt_duration(span)}):")
    for label, sec in (("geplant", waits["planned"]),
                       ("auf Farbe", waits["color"]),
                       ("Pause", waits["pause"]),
                       ("Rest (Aktionen, Scans)", rest)):
        share = f"{sec / span * 100:5.1f} %" if span else "    -"
        print(f"  {_fmt_duration(sec):>9}  {share}  {label}")
    for name, sec, n, longest, timeouts in data["color_waits"][:10]:
        suffix = f", {timeouts}x Timeout" if timeouts else ""
        print(f"  {_fmt_duration(sec):>9}  auf Farbe  {name}  "
              f"({n}x, laengste {longest:.0f}s{suffix})")


def _report_findings(data: dict) -> None:
    """Was gefunden, erkannt und unterbrochen wurde — und was der Bericht nicht kennt."""
    if data["items"]:
        print(f"\n{_RULE}\nGEFUNDENE ITEMS "
              f"({sum(n for _, n in data['items'])} gesamt):")
        for name, n in data["items"][:15]:
            print(f"  {n:>5}x  {name}")

    if data["detected"]:
        print(f"\n{_RULE}\nERKANNT (Boss/Icon):")
        for name, n in data["detected"][:10]:
            print(f"  {n:>5}x  {name}")

    if data["disturbances"]:
        print(f"\n{_RULE}\nUNTERBRECHUNGEN:")
        for k, v in data["disturbances"]:
            print(f"  {v:>5}x  {k}")

    if data["unknown"]:
        # Neue Ereignisarten sollen hier auffallen, nicht stillschweigend fehlen.
        print(f"\n  Nicht ausgewertete Ereignisarten: {', '.join(data['unknown'])}")


def main() -> int:
    args = [a for a in sys.argv[1:] if a]
    if args and args[0] != "--last":
        paths = [Path(a) for a in args]
        missing = [p for p in paths if not p.exists()]
        if missing:
            print(f"Nicht gefunden: {', '.join(str(p) for p in missing)}")
            return 1
    else:
        if not LOGS_DIR.is_dir():
            print(f"Kein Ordner '{LOGS_DIR}' — ist session_log_enabled in der config.json an?")
            return 1
        paths = sorted(LOGS_DIR.glob("*.csv"))
        if not paths:
            print(f"Keine CSV-Dateien in '{LOGS_DIR}'.")
            return 1
        if args:                       # --letzte
            paths = paths[-1:]
            print(f"Neueste Session: {paths[0].name}\n")

    report(paths)
    return 0


if __name__ == "__main__":
    sys.exit(main())
