"""Rauchtest Übersicht und Editor: messen sich die Karten ein, klebt der Kopf?

Beides sieht die Vertragssuite nicht: sie kennt keine Kästen und keine
Scrollposition. Ein `subgrid`, das der Browser nicht kann, und ein `sticky`, das
an einem nicht scrollenden Vorfahren hängt, fallen nur hier auf.
"""

from ._bruecke import Fenster, main, sandkasten


def _sequenz(name: str, notiz: str, phasen: int, schritte: int):
    from autoclicker.models import LoopPhase, Sequence, SequenceStep

    s = Sequence(name=name, description=notiz, total_cycles=1)
    s.loop_phases = [
        LoopPhase(name=f"P{i}", steps=[SequenceStep(name="x", x=1, y=1, point_id=1)
                                       for _ in range(schritte)])
        for i in range(phasen)
    ]
    return s


def aufbau():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import AutoClickerState, ClickPoint
    from autoclicker.persistence.sequences import save_data

    sandkasten("rauch_sequenzen_")
    zustand = AutoClickerState()
    # Die MITTLERE Karte ohne Notiz — genau daran rutschte alles darunter hoch.
    for name, notiz, phasen, schritte in (("Alpha", "Mit einer Notiz", 1, 50),
                                          ("Beta", "", 11, 1),
                                          ("testaufnahme_mit_sehr_langem_namen_v2",
                                           "Auch mit Notiz", 1, 1)):
        zustand.sequences[name] = _sequenz(name, notiz, phasen, schritte)
    # Genug Punkte, damit die linke Spalte laenger wird als das Fenster.
    zustand.sequences["Alpha"].points = [
        ClickPoint(x=i, y=i, name=f"Punkt {i}", id=i) for i in range(1, 41)
    ]
    save_data(zustand)
    from autoclicker.persistence import list_available_sequences
    return StudioBridge(zustand.sequences["Alpha"],
                        dict(list_available_sequences())["Alpha"], "sequences")


def lauf():
    b = aufbau()
    fehler = []

    def pruefe(bedingung, text):
        if not bedingung:
            fehler.append(text)

    with Fenster(b, breite=1300, hoehe=560) as f:
        # ---------------------------------------------------------- Übersicht
        f.reiter("sequenzen", 900)
        karten = f.anzahl(".seq-karte")
        pruefe(karten == 3, f"3 Karten erwartet, da: {karten}")
        # **Die Karten messen sich aneinander ein.** Fehlt einer die Notiz,
        # rutschte alles darunter hoch: der Phasenbalken der einen lag auf Höhe
        # der Kennzahlen der anderen, und die Übersicht war keine mehr.
        for teil in ("seq-balken", "seq-zahlen", "seq-fuss"):
            kanten = f.seite.eval_on_selector_all(
                f".seq-karte .{teil}",
                "ns => ns.map(n => Math.round(n.getBoundingClientRect().top))")
            pruefe(len(set(kanten)) == 1,
                   f".{teil} liegt nicht auf einer Linie: {kanten}")
        # Der Pfad der langen dritten Sequenz darf nicht über den Öffnen-Knopf
        # und in die Nachbarkarte malen. `min-width:0` allein reicht dafür nicht:
        # der Text schrumpft rechnerisch, bleibt bei overflow:visible aber sichtbar.
        pfad_overflow = f.seite.eval_on_selector_all(
            ".seq-fuss .wachse",
            "ns => ns.map(n => getComputedStyle(n).overflowX)")
        pruefe(pfad_overflow and all(wert != "visible" for wert in pfad_overflow),
               f"Sequenzpfade laufen aus ihren Karten: {pfad_overflow}")
        knopf_in_karte = f.seite.eval_on_selector_all(
            ".seq-karte",
            "ns => ns.every(k => { const b=k.querySelector('.seq-fuss .btn'); "
            "if (!b) return true; const kr=k.getBoundingClientRect(); "
            "const br=b.getBoundingClientRect(); return br.right <= kr.right + 1; })")
        pruefe(knopf_in_karte, "ein Öffnen-Knopf ragt aus seiner Karte")
        f.bild("sequenzen_karten")

        # ------------------------------------------------------------- Editor
        f.reiter("editor", 700)
        pruefe(f.anzahl("#btn-aufnahme") == 1,
               "Verweis auf das Aufnahme-Werkzeug fehlt")
        kopf = ".seite.links .abschnitt.klebt"
        pruefe(f.anzahl(kopf) == 1, "kein klebender Abschnitt in der linken Spalte")
        pruefe(f.anzahl(kopf + " #btn-aufnahme") == 1,
               "Aufnahme-Verweis steht nicht unter der festgehaltenen Notiz")
        pruefe(f.anzahl("#aufnahme-info, .aufnahme-zeile .info") == 0,
               "der reine Werkzeug-Verweis hat noch ein ueberfluessiges i")
        feldhoehen = f.seite.eval_on_selector_all(
            "#seq-zyklen, #seq-bloecke",
            "ns => ns.map(n => Math.round(n.getBoundingClientRect().height))")
        pruefe(len(feldhoehen) == 2 and feldhoehen[0] == feldhoehen[1],
               f"Zyklen und Bloecke haben verschiedene Kachelhoehen: {feldhoehen}")
        pruefe(f.seite.eval_on_selector(
            "#seq-bloecke", "e => getComputedStyle(e).borderTopStyle") == "solid",
            "der berechneten Blockanzahl fehlt die sichtbare Kachel")
        klebt = f.seite.eval_on_selector(kopf, "e => getComputedStyle(e).position")
        pruefe(klebt == "sticky", f"der oberste Block klebt nicht: {klebt}")
        # Und er klebt an der SPALTE: hinge er an einem nicht scrollenden
        # Vorfahren, wäre `position:sticky` gesetzt und trotzdem wirkungslos.
        vorher = f.seite.eval_on_selector(
            kopf, "e => Math.round(e.getBoundingClientRect().top)")
        f.seite.eval_on_selector(".seite.links", "e => { e.scrollTop = 400; }")
        f.seite.wait_for_timeout(200)
        nachher = f.seite.eval_on_selector(
            kopf, "e => Math.round(e.getBoundingClientRect().top)")
        gescrollt = f.seite.eval_on_selector(".seite.links", "e => e.scrollTop")
        pruefe(gescrollt > 0, "die linke Spalte scrollt gar nicht — Test misst nichts")
        pruefe(vorher == nachher,
               f"der Block scrollt mit: {vorher} -> {nachher}")
        f.bild("sequenzen_editor")

        fehler.extend(f.fehler)
    return fehler


if __name__ == "__main__":
    main("Sequenzen", lauf)
