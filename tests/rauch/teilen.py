"""Rauchtest Teilen-Reiter: Bündel schreiben und wieder einlesen."""

from pathlib import Path

from ._bruecke import Fenster, main, sandkasten


def aufbau():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import (
        AutoClickerState, ClickPoint, LoopPhase, Sequence, SequenceStep,
    )
    from autoclicker.persistence import (
        list_available_sequences, save_data,
    )

    sandkasten("rauch_teilen_")
    st = AutoClickerState()
    seq = Sequence(name="Farm", loop_phases=[LoopPhase(name="A", steps=[
        SequenceStep(point_id=1, delay_before=3.0), SequenceStep(point_id=2)])],
        points=[ClickPoint(id=1, x=100, y=100, name="A"),
                ClickPoint(id=2, x=200, y=200, name="B")])
    st.sequences["Farm"] = seq
    st.active_sequence = seq
    st.points = seq.points
    save_data(st)
    return StudioBridge(seq, Path(dict(list_available_sequences())["Farm"]),
                        "sequences")


def run():
    b = aufbau()
    error = []

    def pruefe(condition, text):
        if not condition:
            error.append(text)

    # Erst ein Buendel schreiben, damit der Reiter etwas zu zeigen hat.
    z = b.share_data()
    z = b.export_start({"parts": {k: True for k in z["inventory"]}, "name": "probe"})
    pruefe(z["status"]["kind"] == "ok", f"Export: {z['status']}")

    with Fenster(b) as f:
        f.reiter("teilen")
        # **Gegen die Tabelle gemessen, nicht gegen eine getippte Zahl.** Hier
        # stand einmal `>= 6` — aus der Zeit, als Punkte, Slots, Items und die
        # drei Scan-Arten je eine eigene Kachel hatten. Seit sie im
        # Sequenzordner liegen, sind es zwei, und die Zahl war nur noch ein
        # Pin auf einen Stand, den es nicht mehr gibt.
        from autoclicker.editors.sequence_studio.bridge_teilen import PARTS
        haken = f.count("#share-export input[type=checkbox]")
        pruefe(haken == len(PARTS),
               f"{len(PARTS)} Haken erwartet (je einer pro TEILE), da: {haken}")
        pruefe("probe.zip" in f.text("#share-middle"), "das Buendel fehlt in der Liste")
        f.image("teilen")
        f.click_value("#share-middle button")
        pruefe("gelesen" in f.status(), f"Einlesen: {f.status()!r}")
        pruefe(bool(f.text("#share-import").strip()), "rechts steht nichts zum Import")
        f.image("teilen_import")
        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Teilen", run)
