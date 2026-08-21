"""Rauchtest Werkzeuge-Reiter: prüfen, kalibrieren, Farbfrage, Klick-Runde."""

from pathlib import Path

from ._bruecke import Fenster, main, sandkasten


def aufbau():
    """Ein kleiner Bestand plus die Brücke darauf — wie im Vertragstest."""
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import (
        AutoClickerState, ClickPoint, ItemProfile, ItemScanConfig, ItemSlot,
        LoopPhase, Sequence, SequenceStep,
    )
    from autoclicker.persistence import (
        list_available_sequences, save_data, save_global_items, save_global_slots,
        save_item_scan, save_points,
    )

    sandkasten("rauch_wz_")
    st = AutoClickerState()
    st.points = [ClickPoint(id=1, x=100, y=100, name="Sammeln", color=(10, 200, 30)),
                 ClickPoint(id=2, x=900, y=600, name="Bestaetigen"),
                 ClickPoint(id=3, x=400, y=300, name="Menue")]
    save_points(st)
    st.global_slots = {"Slot 1": ItemSlot(name="Slot 1", scan_region=(10, 20, 70, 80),
                                          click_pos=(40, 50))}
    save_global_slots(st)
    # Absichtlich kaputt, damit die Pruefung etwas zu melden hat: ohne Befunde
    # saehe man ihre Darstellung nie.
    st.global_items = {"Geist": ItemProfile(name="Geist")}
    save_global_items(st)
    save_item_scan(ItemScanConfig(name="Inventar", slot_names=["Gibt es nicht"],
                                  item_names=["Geist", "Auch weg"]))
    seq = Sequence(name="Farm", loop_phases=[LoopPhase(name="A", steps=[
        SequenceStep(point_id=1, delay_before=3.0), SequenceStep(point_id=2)])])
    st.sequences["Farm"] = seq
    save_data(st)

    b = StudioBridge(seq, Path(dict(list_available_sequences())["Farm"]), "sequences")
    # Maus und Bildschirm gibt es hier nicht: beide werden gestellt, alles andere
    # laeuft wie im Fenster.
    b._stelle_abwarten = lambda: (555, 444, "")
    b._farbe_an = staticmethod(lambda x, y: (200, 10, 30))
    return b


def lauf():
    b = aufbau()
    fehler = []

    def pruefe(bedingung, text):
        if not bedingung:
            fehler.append(text)

    with Fenster(b) as f:
        f.reiter("werkzeuge")
        pruefe(f.anzahl("#wz-links button") == 3, "drei Werkzeuge erwartet")
        pruefe("Farm" in f.text("#wz-links"), "die offene Sequenz fehlt links")

        # --- Pruefen ---
        f.klick_text("#wz-mitte button", "Jetzt prüfen", warten=900)
        pruefe(f.anzahl(".wz-befund") == 3, "drei Befunde erwartet")
        pruefe("Fehler" in f.status(), f"Status nach Pruefen: {f.status()!r}")
        pruefe(bool(f.text("#wz-rechts").strip()), "rechts steht nicht, was geprueft wurde")
        f.bild("wz_pruefen")

        # --- Farbfrage: die Stelle hat eine andere Farbe als der Punkt ---
        f.klick_text("#wz-links button", "Kalibrieren", warten=500)
        pruefe("gesamte gespeicherte Bestand" in f.text("#wz-mitte"),
               "der Bezug fehlt beim Kalibrieren")
        f.klick("#wz-mitte .wz-ref button", warten=900)
        pruefe(f.anzahl(".wz-farbfrage") == 1, "keine Farb-Rueckfrage")
        pruefe(f.anzahl(".wz-farbe") == 2, "beide Farben sollten dastehen")
        pruefe("Verschiebung" not in f.text("#wz-mitte"),
               "trotz Rueckfrage schon gesetzt")
        f.bild("wz_farbfrage")

        f.klick_text(".wz-farbfrage button", "Trotzdem setzen", warten=900)
        pruefe("Verschiebung: +455 X, +344 Y" in f.text("#wz-mitte"),
               f"Versatz falsch: {f.text('#wz-mitte')[:200]!r}")
        pruefe(f.anzahl("#wz-mitte input[type=checkbox]") == 3, "drei Umfang-Haken")
        pruefe("Stelle(n)" in f.text("#wz-rechts"), "keine Vorschau rechts")
        f.bild("wz_kalib")

        f.klick_text("#wz-mitte button", "Umrechnen und speichern", warten=1000)
        pruefe("Kalibriert" in f.status(), f"Anwenden: {f.status()!r}")
        pruefe([p.x for p in b.points] == [555, 1355, 855],
               f"Punkte nicht gewandert: {[(p.id, p.x) for p in b.points]}")

        # --- Nachklicken: starten UND beenden ---
        f.klick_text("#wz-links button", "Punkte nachklicken", warten=500)
        pruefe("die offene Sequenz" in f.text("#wz-mitte"), "Bezug fehlt")
        pruefe("Farm" in f.text("#wz-mitte"), "Sequenzname fehlt")
        knoepfe = [k.inner_text() for k in
                   f.seite.query_selector_all("#wz-mitte button")]
        pruefe(len(knoepfe) == 2, f"starten + beenden erwartet, da: {knoepfe}")
        f.klick_text("#wz-mitte button", "Nachklicken starten", warten=700)
        pruefe("Farm" in f.status(), f"Start nennt die Sequenz nicht: {f.status()!r}")
        f.klick_text("#wz-mitte button", "Nachklicken beenden", warten=700)
        pruefe("Beenden" in f.status(), f"Beenden: {f.status()!r}")
        f.bild("wz_klick")

        fehler.extend(f.fehler)
    return fehler


if __name__ == "__main__":
    main("Werkzeuge", lauf)
