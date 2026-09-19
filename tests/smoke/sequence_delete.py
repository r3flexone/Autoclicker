"""Rauchtest: eine Sequenz im Übersichts-Reiter löschen.

Die Vertragssuite ruft `sequence_delete()` direkt auf. Was sie nicht sehen
kann: ob der Knopf den Dialog aufmacht, ob dort steht, *was* weggeht, und ob die
Übersicht danach wirklich eine Karte weniger hat. Dazu die Symmetrie der beiden
Knöpfe — gleiche Spalten heisst gleiche gemessene Breite, nicht „sieht ähnlich
aus".
"""

from pathlib import Path

from ._bridge import Window, main, sandbox


def setup():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import (
        AutoClickerState, ClickPoint, ItemProfile, ItemScanConfig, ItemSlot,
        LoopPhase, Sequence, SequenceStep,
    )
    from autoclicker.persistence import (
        list_available_sequences, save_data, save_item_scan, sequence_dir,
        sequence_templates_dir,
    )

    sandbox("rauch_seqloesch_")

    def create_one(name):
        st = AutoClickerState()
        seq = Sequence(name=name, loop_phases=[LoopPhase(name="A", steps=[
            SequenceStep(point_id=1)])], points=[ClickPoint(id=1, x=10, y=20)])
        st.sequences[name] = seq
        st.active_sequence = seq
        st.points = seq.points
        save_data(st)
        return seq

    farm = create_one("Farm")
    create_one("Raid")
    save_item_scan(ItemScanConfig(
        name="Inventar", owner_sequence="Raid",
        slots=[ItemSlot(name="Slot 1", scan_region=(0, 0, 10, 10), click_pos=(5, 5))],
        items=[ItemProfile(name="Erz")]))
    # Der Ordner heisst NICHT wie die Sequenz: aus „Raid" macht
    # `sanitize_filename()` das Verzeichnis `sequences/raid`. Die Pfade kommen
    # deshalb aus der Persistenz — hier stand einmal der Anzeigename, und der
    # Rauchtest lief damit an einem Ordner vorbei, den das Studio gar nicht
    # anfasst.
    templates_list = sequence_templates_dir("Raid")
    templates_list.mkdir(parents=True, exist_ok=True)
    (templates_list / "erz.png").write_bytes(b"x")

    b = StudioBridge(farm, Path(dict(list_available_sequences())["Farm"]), "sequences")
    b._running = lambda: False
    return b, sequence_dir("Raid")


def run():
    b, ordner_raid = setup()
    error = []

    def expect(condition, text):
        if not condition:
            error.append(text)

    with Window(b) as f:
        f.tab("sequences")
        expect(f.count(".seq-card") == 2,
               f"2 Karten erwartet, da: {f.count('.seq-card')}")

        # **Gleiche Spalten heisst gleiche BREITE.** Genau dafuer ist der
        # Rauchtest da: die Vertragssuite sieht die Klasse, nicht das Ergebnis.
        widths = f.page.eval_on_selector_all(
            ".seq-card .button-pair .btn", "ns => ns.map(n => n.getBoundingClientRect().width)")
        expect(len(widths) == 4, f"4 Knoepfe erwartet, da: {len(widths)}")
        expect(widths and max(widths) - min(widths) < 0.5,
               f"die Knoepfe sind verschieden breit: {widths}")
        # Und jede Karte gibt dem Paar dieselbe Breite. Gemessen wird die
        # BREITE, nicht die rechte Kante: die Karten stehen nebeneinander in
        # einem Raster, ihre Fusszeilen enden also zwangslaeufig an
        # verschiedenen Stellen. Hier stand erst die Kante, und der Rauchtest
        # meldete prompt „360 gegen 725" — richtig gemessen, falsch gefragt.
        pairs = f.page.eval_on_selector_all(
            ".seq-card .button-pair",
            "ns => ns.map(n => Math.round(n.getBoundingClientRect().width))")
        expect(len(set(pairs)) == 1, f"die Knopfpaare sind verschieden breit: {pairs}")
        f.image("sequenzen_loeschen")

        # Der Dialog muss sagen, WAS weggeht — der Umfang ist der halbe Grund
        # fuer die Rueckfrage.
        f.click_text(".seq-card:nth-of-type(2) .button-pair .btn", "Löschen")
        expect(not f.page.is_hidden("#veil"), "der Dialog geht nicht auf")
        text = f.text("#veil")
        expect("Raid" in text, f"der Name fehlt im Dialog: {text!r}")
        expect("Item-Scan" in text and "Vorlage" in text,
               f"der Umfang fehlt im Dialog: {text!r}")
        expect("backups" in text, "der Dialog verschweigt, dass es eine Sicherung gibt")
        f.image("sequenzen_loeschen_dialog")

        # Abbrechen laesst alles stehen — sonst waere die Rueckfrage Dekoration.
        f.click("#dialog-cancel")
        expect(f.count(".seq-card") == 2, "Abbrechen hat trotzdem geloescht")
        expect(ordner_raid.is_dir(), "der Ordner ist trotz Abbruch weg")

        f.click_text(".seq-card:nth-of-type(2) .button-pair .btn", "Löschen")
        f.click("#dialog-discard")
        expect(f.count(".seq-card") == 1,
               f"nach dem Loeschen 1 Karte erwartet, da: {f.count('.seq-card')}")
        expect(not ordner_raid.exists(), "der Ordner steht noch")
        # Gespiegelte Struktur: `sequences/raid` -> `backups/sequences/raid`.
        backup = Path("backups/sequences") / ordner_raid.name
        expect((backup / "templates/erz.png").exists(),
               "die Vorlage fehlt in der Sicherung")
        expect("backups" in f.status(), f"die Meldung nennt den Ort nicht: {f.status()!r}")
        f.image("sequenzen_geloescht")

        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Sequenz löschen", run)
