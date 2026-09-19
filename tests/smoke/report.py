"""Rauchtest Bericht-Reiter: Session-Logs im Fenster lesen.

Die Vertragssuite ruft `report_data()` direkt auf — also genau so, wie die
Seite es *nicht* tut. Was sie nicht sehen kann: ob der Reiter sich überhaupt
öffnet, ob die drei Spalten etwas enthalten, und ob ein Klick auf eine Sitzung
den Bericht wirklich austauscht. Genau dort liegen die Fehler, die im Fenster
sofort auffallen (der Reiter bleibt leer) und im Test gar nicht.
"""

import csv
from pathlib import Path

from ._bridge import Fenster, main, sandkasten

SPALTEN = ["timestamp", "elapsed_sec", "event", "detail", "x", "y", "extra"]


def _log(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SPALTEN)
        w.writerows(lines)


def aufbau():
    from autoclicker.config import CONFIG
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import (
        AutoClickerState, ClickPoint, LoopPhase, Sequence, SequenceStep,
    )
    from autoclicker.persistence import list_available_sequences, save_data

    sandkasten("rauch_bericht_")
    st = AutoClickerState()
    seq = Sequence(name="Farm", loop_phases=[LoopPhase(name="A", steps=[
        SequenceStep(point_id=1)])],
        points=[ClickPoint(id=1, x=100, y=100, name="A")])
    st.sequences["Farm"] = seq
    st.active_sequence = seq
    st.points = seq.points
    save_data(st)

    _log(Path("logs/20260101_000000_farm.csv"), [
        ("2026-01-01 00:00:00", 0, "session_start", "Farm", "", "", ""),
        ("2026-01-01 00:00:01", 1, "click", "Bank", 10, 20, ""),
        ("2026-01-01 00:00:03", 3, "timeout", "Bank oeffnen", "", "", ""),
        ("2026-01-01 00:00:04", 4, "timeout", "Bank oeffnen", "", "", ""),
        ("2026-01-01 00:00:06", 6, "item_found", "Erz", "", "", ""),
        ("2026-01-01 00:00:07", 7, "item_found", "Erz", "", "", ""),
        ("2026-01-01 01:00:00", 3600, "session_end", "Farm", "", "", ""),
    ])
    _log(Path("logs/20260102_000000_farm.csv"), [
        ("2026-01-02 00:00:00", 0, "session_start", "Farm", "", "", ""),
        ("2026-01-02 00:00:01", 1, "click", "Bank", 10, 20, ""),
        ("2026-01-02 00:30:00", 1800, "session_end", "Farm", "", "", ""),
    ])
    Path("marktwert.json").write_text('{"Erz": 100}', encoding="utf-8")
    CONFIG.session_log_dir = "logs"
    CONFIG.scan_market_value_file = "marktwert.json"

    return StudioBridge(seq, Path(dict(list_available_sequences())["Farm"]),
                        "sequences")


def run():
    b = aufbau()
    error = []

    def pruefe(condition, text):
        if not condition:
            error.append(text)

    with Fenster(b) as f:
        f.reiter("report")

        left = f.text("#rep-left")
        pruefe("Alle zusammen" in left, f"links fehlt die Sammelzeile: {left!r}")
        pruefe(f.count(".rep-session") == 3,
               f"3 Zeilen erwartet (alle + 2 Sitzungen), da: {f.count('.rep-session')}")

        center = f.text("#rep-middle")
        pruefe("TIMEOUTS" in center, f"die Timeout-Liste fehlt: {center[:120]!r}")
        pruefe("Bank oeffnen" in center, "der haengende Schritt wird nicht genannt")
        # Fuenf Kennzahlen-Kacheln, dieselben wie im Werkzeuge-Reiter.
        pruefe(f.count("#rep-middle .wz-metric") == 5,
               f"5 Kennzahlen erwartet, da: {f.count('#rep-middle .wz-metric')}")
        # Jede Rangzeile hat ihren Balken — sonst steht die Liste ohne
        # Verhaeltnis da, und genau das ist der Unterschied zur Konsole.
        pruefe(f.count("#rep-middle .rep-rank") == f.count("#rep-middle .rep-bar"),
               "nicht jede Rangzeile hat einen Balken")

        right = f.text("#rep-right")
        pruefe("ERTRAG" in right, f"rechts steht kein Ertrag: {right[:120]!r}")
        # 2x Erz a 100 = 200 Gold. Die Tausendertrennung macht daraus nichts
        # anderes, solange es unter 1000 bleibt.
        pruefe("200" in right, f"die Goldsumme fehlt: {right[:200]!r}")
        pruefe("Obergrenze" in right,
               "der Vorbehalt fehlt — die Zahl waere sonst eine Behauptung")
        f.image("report")

        # **Eine Sitzung waehlen tauscht den Bericht aus.** Die zweite Zeile ist
        # die neueste Sitzung: eine Klick, ein Timeout weniger.
        f.click_value(".rep-session:nth-of-type(2)")
        pruefe(f.count(".rep-session.on") == 1,
               "genau eine Sitzung muss markiert sein")
        center = f.text("#rep-middle")
        pruefe("Keine Timeouts" in center,
               f"die gewaehlte Sitzung hat keine Timeouts: {center[:160]!r}")
        pruefe(f.count(".rep-session") == 3,
               "die Liste links muss vollstaendig bleiben")
        f.image("bericht_eine")

        # Und zurueck auf alles zusammen.
        f.click_value(".rep-session:nth-of-type(1)")
        pruefe("Bank oeffnen" in f.text("#rep-middle"),
               "zurueck auf „alle zusammen“ fehlt der Timeout wieder")

        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Bericht", run)
