"""Rauchtest Teilen-Reiter: Bündel schreiben und wieder einlesen."""

from pathlib import Path

from ._bridge import Window, main, make_expect, sandbox


def setup():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import (
        AutoClickerState, ClickPoint, LoopPhase, Sequence, SequenceStep,
    )
    from autoclicker.persistence import (
        list_available_sequences, save_sequence_file, sequence_file,
    )

    sandbox("rauch_teilen_")
    st = AutoClickerState()
    seq = Sequence(name="Farm", loop_phases=[LoopPhase(name="A", steps=[
        SequenceStep(point_id=1, delay_before=3.0), SequenceStep(point_id=2)])],
        points=[ClickPoint(id=1, x=100, y=100, name="A"),
                ClickPoint(id=2, x=200, y=200, name="B")])
    st.active_sequence = seq
    st.points = seq.points
    save_sequence_file(seq, sequence_file(seq.name))
    # Eine zweite Sequenz, damit „nur die offene" etwas abzuwählen hat.
    save_sequence_file(Sequence(name="Raid", points=[ClickPoint(id=1, x=5, y=5)]),
                       sequence_file("Raid"))
    Path("onedrive").mkdir()
    return StudioBridge(seq, Path(dict(list_available_sequences())["Farm"]),
                        "sequences")


def run():
    b = setup()
    error = []
    expect = make_expect(error)

    # Erst ein Buendel schreiben, damit der Reiter etwas zu zeigen hat.
    z = b.share_data()
    z = b.export_start({"parts": {k: True for k in z["inventory"]}, "name": "probe"})
    expect(z["status"]["kind"] == "ok", f"Export: {z['status']}")

    with Window(b) as f:
        f.tab("share")
        # **Gegen die Tabelle gemessen, nicht gegen eine getippte Zahl.** Hier
        # stand einmal `>= 6` — aus der Zeit, als Punkte, Slots, Items und die
        # drei Scan-Arten je eine eigene Kachel hatten. Seit sie im
        # Sequenzordner liegen, sind es zwei, und die Zahl war nur noch ein
        # Pin auf einen Stand, den es nicht mehr gibt.
        from autoclicker.editors.sequence_studio.bridge_share import PARTS
        checkbox = f.count("#share-export .growing > .share-row input[type=checkbox]")
        expect(checkbox == len(PARTS),
               f"{len(PARTS)} Haken erwartet (je einer pro TEILE), da: {checkbox}")
        # Je Sequenz ein Haken darunter — eingerückt, nicht als weiterer TEIL.
        seqs = f.count("#share-export .share-seqs input[type=checkbox]")
        expect(seqs == 2, f"2 Sequenz-Haken erwartet, da: {seqs}")
        expect("probe.zip" in f.text("#share-middle"), "das Buendel fehlt in der Liste")
        f.image("share")

        # **Über den Text, nicht über die Position**: der erste Knopf der Mitte
        # ist seit dem Teilen-Ordner „Ordner wählen …", und ein Klick darauf
        # öffnete im Prüfstand keinen Dialog, sondern eine Warnung.
        f.click_text("#share-middle button", "einlesen")
        expect("gelesen" in f.status(), f"Einlesen: {f.status()!r}")
        expect(bool(f.text("#share-import").strip()), "rechts steht nichts zum Import")
        f.image("teilen_import")

        # Nur die offene Sequenz, in den Teilen-Ordner — der Name ist ihrer.
        f.click_text("#share-export button", "Nur die offene")
        on = f.count("#share-export .share-seqs input:checked")
        expect(on == 1, f"nach „Nur die offene“ ein Haken erwartet, da: {on}")
        f.page.fill("#share-folder", "onedrive")
        f.page.press("#share-folder", "Enter")
        f.settle()
        expect("Teilen-Ordner" in f.status(), f"Ordner setzen: {f.status()!r}")
        f.click_text("#share-export button", "Bündel schreiben")
        expect(Path("onedrive/farm.zip").exists(),
               f"farm.zip fehlt im Teilen-Ordner: {f.status()!r}")
        # Gemessen an der Marke der Zeile, nicht am Text der Spalte: dort steht
        # „Teilen-Ordner" auch in den Erklärungen.
        badges = [k.inner_text() for k in
                  f.page.query_selector_all("#share-middle .share-list .num")]
        expect("Teilen-Ordner" in badges and "exports" in badges,
               f"die Liste sagt nicht, woher die Bündel kommen: {badges}")
        f.image("teilen_ordner")
        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Teilen", run)
