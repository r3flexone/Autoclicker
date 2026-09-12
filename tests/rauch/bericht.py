"""Rauchtest Bericht-Reiter: Session-Logs im Fenster lesen.

Die Vertragssuite ruft `bericht_daten()` direkt auf — also genau so, wie die
Seite es *nicht* tut. Was sie nicht sehen kann: ob der Reiter sich überhaupt
öffnet, ob die drei Spalten etwas enthalten, und ob ein Klick auf eine Sitzung
den Bericht wirklich austauscht. Genau dort liegen die Fehler, die im Fenster
sofort auffallen (der Reiter bleibt leer) und im Test gar nicht.
"""

import csv
from pathlib import Path

from ._bruecke import Fenster, main, sandkasten

SPALTEN = ["timestamp", "elapsed_sec", "event", "detail", "x", "y", "extra"]


def _log(pfad: Path, zeilen: list) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SPALTEN)
        w.writerows(zeilen)


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


def lauf():
    b = aufbau()
    fehler = []

    def pruefe(bedingung, text):
        if not bedingung:
            fehler.append(text)

    with Fenster(b) as f:
        f.reiter("bericht")

        links = f.text("#ber-links")
        pruefe("Alle zusammen" in links, f"links fehlt die Sammelzeile: {links!r}")
        pruefe(f.anzahl(".ber-sitzung") == 3,
               f"3 Zeilen erwartet (alle + 2 Sitzungen), da: {f.anzahl('.ber-sitzung')}")

        mitte = f.text("#ber-mitte")
        pruefe("TIMEOUTS" in mitte, f"die Timeout-Liste fehlt: {mitte[:120]!r}")
        pruefe("Bank oeffnen" in mitte, "der haengende Schritt wird nicht genannt")
        # Fuenf Kennzahlen-Kacheln, dieselben wie im Werkzeuge-Reiter.
        pruefe(f.anzahl("#ber-mitte .wz-kennzahl") == 5,
               f"5 Kennzahlen erwartet, da: {f.anzahl('#ber-mitte .wz-kennzahl')}")
        # Jede Rangzeile hat ihren Balken — sonst steht die Liste ohne
        # Verhaeltnis da, und genau das ist der Unterschied zur Konsole.
        pruefe(f.anzahl("#ber-mitte .ber-rang") == f.anzahl("#ber-mitte .ber-balken"),
               "nicht jede Rangzeile hat einen Balken")

        rechts = f.text("#ber-rechts")
        pruefe("ERTRAG" in rechts, f"rechts steht kein Ertrag: {rechts[:120]!r}")
        # 2x Erz a 100 = 200 Gold. Die Tausendertrennung macht daraus nichts
        # anderes, solange es unter 1000 bleibt.
        pruefe("200" in rechts, f"die Goldsumme fehlt: {rechts[:200]!r}")
        pruefe("Obergrenze" in rechts,
               "der Vorbehalt fehlt — die Zahl waere sonst eine Behauptung")
        f.bild("bericht")

        # **Eine Sitzung waehlen tauscht den Bericht aus.** Die zweite Zeile ist
        # die neueste Sitzung: eine Klick, ein Timeout weniger.
        f.klick(".ber-sitzung:nth-of-type(2)")
        pruefe(f.anzahl(".ber-sitzung.an") == 1,
               "genau eine Sitzung muss markiert sein")
        mitte = f.text("#ber-mitte")
        pruefe("Keine Timeouts" in mitte,
               f"die gewaehlte Sitzung hat keine Timeouts: {mitte[:160]!r}")
        pruefe(f.anzahl(".ber-sitzung") == 3,
               "die Liste links muss vollstaendig bleiben")
        f.bild("bericht_eine")

        # Und zurueck auf alles zusammen.
        f.klick(".ber-sitzung:nth-of-type(1)")
        pruefe("Bank oeffnen" in f.text("#ber-mitte"),
               "zurueck auf „alle zusammen“ fehlt der Timeout wieder")

        fehler.extend(f.fehler)
    return fehler


if __name__ == "__main__":
    main("Bericht", lauf)
