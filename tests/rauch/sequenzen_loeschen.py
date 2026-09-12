"""Rauchtest: eine Sequenz im Übersichts-Reiter löschen.

Die Vertragssuite ruft `sequenz_loeschen()` direkt auf. Was sie nicht sehen
kann: ob der Knopf den Dialog aufmacht, ob dort steht, *was* weggeht, und ob die
Übersicht danach wirklich eine Karte weniger hat. Dazu die Symmetrie der beiden
Knöpfe — gleiche Spalten heisst gleiche gemessene Breite, nicht „sieht ähnlich
aus".
"""

from pathlib import Path

from ._bruecke import Fenster, main, sandkasten


def aufbau():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import (
        AutoClickerState, ClickPoint, ItemProfile, ItemScanConfig, ItemSlot,
        LoopPhase, Sequence, SequenceStep,
    )
    from autoclicker.persistence import (
        list_available_sequences, save_data, save_item_scan, sequence_dir,
        sequence_templates_dir,
    )

    sandkasten("rauch_seqloesch_")

    def anlegen(name):
        st = AutoClickerState()
        seq = Sequence(name=name, loop_phases=[LoopPhase(name="A", steps=[
            SequenceStep(point_id=1)])], points=[ClickPoint(id=1, x=10, y=20)])
        st.sequences[name] = seq
        st.active_sequence = seq
        st.points = seq.points
        save_data(st)
        return seq

    farm = anlegen("Farm")
    anlegen("Raid")
    save_item_scan(ItemScanConfig(
        name="Inventar", owner_sequence="Raid",
        slots=[ItemSlot(name="Slot 1", scan_region=(0, 0, 10, 10), click_pos=(5, 5))],
        items=[ItemProfile(name="Erz")]))
    # Der Ordner heisst NICHT wie die Sequenz: aus „Raid" macht
    # `sanitize_filename()` das Verzeichnis `sequences/raid`. Die Pfade kommen
    # deshalb aus der Persistenz — hier stand einmal der Anzeigename, und der
    # Rauchtest lief damit an einem Ordner vorbei, den das Studio gar nicht
    # anfasst.
    vorlagen = sequence_templates_dir("Raid")
    vorlagen.mkdir(parents=True, exist_ok=True)
    (vorlagen / "erz.png").write_bytes(b"x")

    b = StudioBridge(farm, Path(dict(list_available_sequences())["Farm"]), "sequences")
    b._laeuft = lambda: False
    return b, sequence_dir("Raid")


def lauf():
    b, ordner_raid = aufbau()
    fehler = []

    def pruefe(bedingung, text):
        if not bedingung:
            fehler.append(text)

    with Fenster(b) as f:
        f.reiter("sequenzen")
        pruefe(f.anzahl(".seq-karte") == 2,
               f"2 Karten erwartet, da: {f.anzahl('.seq-karte')}")

        # **Gleiche Spalten heisst gleiche BREITE.** Genau dafuer ist der
        # Rauchtest da: die Vertragssuite sieht die Klasse, nicht das Ergebnis.
        breiten = f.seite.eval_on_selector_all(
            ".seq-karte .knopfpaar .btn", "ns => ns.map(n => n.getBoundingClientRect().width)")
        pruefe(len(breiten) == 4, f"4 Knoepfe erwartet, da: {len(breiten)}")
        pruefe(breiten and max(breiten) - min(breiten) < 0.5,
               f"die Knoepfe sind verschieden breit: {breiten}")
        # Und jede Karte gibt dem Paar dieselbe Breite. Gemessen wird die
        # BREITE, nicht die rechte Kante: die Karten stehen nebeneinander in
        # einem Raster, ihre Fusszeilen enden also zwangslaeufig an
        # verschiedenen Stellen. Hier stand erst die Kante, und der Rauchtest
        # meldete prompt „360 gegen 725" — richtig gemessen, falsch gefragt.
        paare = f.seite.eval_on_selector_all(
            ".seq-karte .knopfpaar",
            "ns => ns.map(n => Math.round(n.getBoundingClientRect().width))")
        pruefe(len(set(paare)) == 1, f"die Knopfpaare sind verschieden breit: {paare}")
        f.bild("sequenzen_loeschen")

        # Der Dialog muss sagen, WAS weggeht — der Umfang ist der halbe Grund
        # fuer die Rueckfrage.
        f.klick_text(".seq-karte:nth-of-type(2) .knopfpaar .btn", "Löschen")
        pruefe(not f.seite.is_hidden("#schleier"), "der Dialog geht nicht auf")
        text = f.text("#schleier")
        pruefe("Raid" in text, f"der Name fehlt im Dialog: {text!r}")
        pruefe("Item-Scan" in text and "Vorlage" in text,
               f"der Umfang fehlt im Dialog: {text!r}")
        pruefe("backups" in text, "der Dialog verschweigt, dass es eine Sicherung gibt")
        f.bild("sequenzen_loeschen_dialog")

        # Abbrechen laesst alles stehen — sonst waere die Rueckfrage Dekoration.
        f.klick("#dialog-ab")
        pruefe(f.anzahl(".seq-karte") == 2, "Abbrechen hat trotzdem geloescht")
        pruefe(ordner_raid.is_dir(), "der Ordner ist trotz Abbruch weg")

        f.klick_text(".seq-karte:nth-of-type(2) .knopfpaar .btn", "Löschen")
        f.klick("#dialog-weg")
        pruefe(f.anzahl(".seq-karte") == 1,
               f"nach dem Loeschen 1 Karte erwartet, da: {f.anzahl('.seq-karte')}")
        pruefe(not ordner_raid.exists(), "der Ordner steht noch")
        # Gespiegelte Struktur: `sequences/raid` -> `backups/sequences/raid`.
        sicherung = Path("backups/sequences") / ordner_raid.name
        pruefe((sicherung / "templates/erz.png").exists(),
               "die Vorlage fehlt in der Sicherung")
        pruefe("backups" in f.status(), f"die Meldung nennt den Ort nicht: {f.status()!r}")
        f.bild("sequenzen_geloescht")

        fehler.extend(f.fehler)
    return fehler


if __name__ == "__main__":
    main("Sequenz löschen", lauf)
