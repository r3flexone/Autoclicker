"""Rauchtest Übersicht und Editor: messen sich die Karten ein, klebt der Kopf?

Beides sieht die Vertragssuite nicht: sie kennt keine Kästen und keine
Scrollposition. Ein `subgrid`, das der Browser nicht kann, und ein `sticky`, das
an einem nicht scrollenden Vorfahren hängt, fallen nur hier auf.
"""

from ._bridge import Window, main, sandbox


def _sequence(name: str, note: str, phases: int, steps_list: int):
    from autoclicker.models import LoopPhase, Sequence, SequenceStep

    s = Sequence(name=name, description=note, total_cycles=1)
    s.loop_phases = [
        LoopPhase(name=f"P{i}", steps=[SequenceStep(name="x", x=1, y=1, point_id=1)
                                       for _ in range(steps_list)])
        for i in range(phases)
    ]
    return s


def setup():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import AutoClickerState, ClickPoint
    from autoclicker.persistence.sequences import save_data

    sandbox("rauch_sequenzen_")
    state_value = AutoClickerState()
    # Die MITTLERE Karte ohne Notiz — genau daran rutschte alles darunter hoch.
    for name, note, phases, steps_list in (("Alpha", "Mit einer Notiz", 1, 50),
                                          ("Beta", "", 11, 1),
                                          ("testaufnahme_mit_sehr_langem_namen_v2",
                                           "Auch mit Notiz", 1, 1)):
        state_value.sequences[name] = _sequence(name, note, phases, steps_list)
    # Genug Punkte, damit die linke Spalte laenger wird als das Fenster.
    state_value.sequences["Alpha"].points = [
        ClickPoint(x=i, y=i, name=f"Punkt {i}", id=i) for i in range(1, 41)
    ]
    save_data(state_value)
    from autoclicker.persistence import list_available_sequences
    return StudioBridge(state_value.sequences["Alpha"],
                        dict(list_available_sequences())["Alpha"], "sequences")


def run():
    b = setup()
    error = []

    def expect(condition, text):
        if not condition:
            error.append(text)

    with Window(b, width=1300, height=560) as f:
        # ---------------------------------------------------------- Übersicht
        f.tab("sequences")
        cards = f.count(".seq-card")
        expect(cards == 3, f"3 Karten erwartet, da: {cards}")
        # **Die Karten messen sich aneinander ein.** Fehlt einer die Notiz,
        # rutschte alles darunter hoch: der Phasenbalken der einen lag auf Höhe
        # der Kennzahlen der anderen, und die Übersicht war keine mehr.
        for part in ("seq-bar", "seq-numbers", "seq-footer"):
            edges = f.page.eval_on_selector_all(
                f".seq-card .{part}",
                "ns => ns.map(n => Math.round(n.getBoundingClientRect().top))")
            expect(len(set(edges)) == 1,
                   f".{part} liegt nicht auf einer Linie: {edges}")
        # Der Pfad der langen dritten Sequenz darf nicht über den Öffnen-Knopf
        # und in die Nachbarkarte malen. `min-width:0` allein reicht dafür nicht:
        # der Text schrumpft rechnerisch, bleibt bei overflow:visible aber sichtbar.
        path_overflow = f.page.eval_on_selector_all(
            ".seq-footer .grow",
            "ns => ns.map(n => getComputedStyle(n).overflowX)")
        expect(path_overflow and all(value != "visible" for value in path_overflow),
               f"Sequenzpfade laufen aus ihren Karten: {path_overflow}")
        button_in_card = f.page.eval_on_selector_all(
            ".seq-card",
            "ns => ns.every(k => { const b=k.querySelector('.seq-footer .btn'); "
            "if (!b) return true; const kr=k.getBoundingClientRect(); "
            "const br=b.getBoundingClientRect(); return br.right <= kr.right + 1; })")
        expect(button_in_card, "ein Öffnen-Knopf ragt aus seiner Karte")
        f.image("sequenzen_karten")

        # ------------------------------------------------------------- Editor
        f.tab("editor")
        expect(f.count("#btn-recording") == 1,
               "Verweis auf das Aufnahme-Werkzeug fehlt")
        head = ".page.left .section.sticky"
        expect(f.count(head) == 1, "kein klebender Abschnitt in der linken Spalte")
        expect(f.count(head + " #btn-recording") == 1,
               "Aufnahme-Verweis steht nicht unter der festgehaltenen Notiz")
        expect(f.count("#aufnahme-info, .recording-row .info") == 0,
               "der reine Werkzeug-Verweis hat noch ein ueberfluessiges i")
        field_heights = f.page.eval_on_selector_all(
            "#seq-cycles, #seq-blocks",
            "ns => ns.map(n => Math.round(n.getBoundingClientRect().height))")
        expect(len(field_heights) == 2 and field_heights[0] == field_heights[1],
               f"Zyklen und Bloecke haben verschiedene Kachelhoehen: {field_heights}")
        expect(f.page.eval_on_selector(
            "#seq-blocks", "e => getComputedStyle(e).borderTopStyle") == "solid",
            "der berechneten Blockanzahl fehlt die sichtbare Kachel")
        sticky = f.page.eval_on_selector(head, "e => getComputedStyle(e).position")
        expect(sticky == "sticky", f"der oberste Block klebt nicht: {sticky}")
        # Und er klebt an der SPALTE: hinge er an einem nicht scrollenden
        # Vorfahren, wäre `position:sticky` gesetzt und trotzdem wirkungslos.
        before = f.page.eval_on_selector(
            head, "e => Math.round(e.getBoundingClientRect().top)")
        f.page.eval_on_selector(".page.left", "e => { e.scrollTop = 400; }")
        f.settle()
        after = f.page.eval_on_selector(
            head, "e => Math.round(e.getBoundingClientRect().top)")
        gescrollt = f.page.eval_on_selector(".page.left", "e => e.scrollTop")
        expect(gescrollt > 0, "die linke Spalte scrollt gar nicht — Test misst nichts")
        expect(before == after,
               f"der Block scrollt mit: {before} -> {after}")
        f.image("sequenzen_editor")

        # ------------------------------------------------ Der Phasenkopf
        f.tab("editor")
        # **Kein „×" am ENDE einer Beschriftung.** Der Skalieren-Knopf hiess
        # „Wartezeiten ×" — dort, wo jede andere Oberflaeche ein Schliesskreuz
        # hat, las sich das als „wegmachen" statt als „mal". Daneben stand ein
        # zweites × als Vorsatz der Wiederholungen, und der Kopf sah aus, als
        # liesse sich dort etwas entfernen.
        knopftexte = f.page.eval_on_selector_all(
            ".phase-header.loop button", "ns => ns.map(n => n.textContent.trim())")
        expect(not any("×" in t for t in knopftexte),
               f"ein Knopf im Phasenkopf traegt ein ×: {knopftexte}")
        # **Eigenschaften und Sammel-Aktionen sind getrennt.** In der
        # Werkzeugzeile stehen nur die beiden Felder, die die Phase
        # BESCHREIBEN; was auf alle Bloecke wirkt, steht unten beieinander.
        expect(f.count(".phase-tool button") == 0,
               "in der Eigenschaften-Zeile der Phase steht ein Knopf")
        # **Beide Zeilen liegen auf demselben Raster.** Vorher war oben ein
        # `flex` mit fest getippten 70/74 px und unten ein `knopfpaar`: die
        # Eigenschaften-Zeile hoerte bei rund 60 % auf, die Knopfzeile ging
        # ueber die volle Breite. Zwei Kanten uebereinander, die fast, aber
        # nicht ganz zusammenfallen, lesen sich als Versehen.
        # Gemessen werden die ZELLEN, nicht die Zeilen-Container: die sind als
        # Kinder einer Spalten-Flexbox ohnehin immer so breit wie der Kopf —
        # daran haette ein zu schmaler Inhalt nichts geaendert, und der Test
        # waere gruen geblieben, ohne die Kante zu sehen, um die es geht.
        grid = f.page.eval_on_selector(".phase-header.loop", """e => {
          const boxEl = (s) => [...e.querySelectorAll(s)]
            .map(n => n.getBoundingClientRect());
          const spanne = (r) => [Math.round(r[0].left),
                                 Math.round(r[r.length - 1].right)];
          const zellen = boxEl('.phase-tool > *');
          const knoepfe = boxEl('.phase-all > .btn');
          return {eig: spanne(zellen), akt: spanne(knoepfe),
                  zellbreiten: zellen.map(r => Math.round(r.width)),
                  fields: boxEl('.phase-tool input').map(r => Math.round(r.width)),
                  knoepfe: knoepfe.map(r => Math.round(r.width)),
                  knopfoben: knoepfe.map(r => Math.round(r.top))};
        }""")
        expect(grid["eig"] == grid["akt"],
               f"Eigenschaften und Sammel-Aktionen haben verschiedene Kanten: {grid}")
        expect(len(set(grid["fields"])) == 1,
               f"die beiden Felder sind verschieden breit: {grid}")
        # Ein Feld ist so breit wie ein Knopf — dasselbe Raster, nicht nur
        # zufaellig dieselbe Aussenkante.
        expect(set(grid["fields"]) == set(grid["knoepfe"]),
               f"Felder und Knoepfe liegen nicht auf demselben Raster: {grid}")
        expect(len(grid["knoepfe"]) == 2 and len(set(grid["knoepfe"])) == 1,
               f"zwei gleich breite Sammel-Knoepfe erwartet: {grid}")
        expect(len(set(grid["knopfoben"])) == 1,
               f"die Sammel-Knoepfe stehen nicht auf einer Zeile: {grid}")
        # Und die Felder sagen selbst, was sie sind — vorher stand das nur im
        # Tooltip, und ein Tooltip ist keine Beschriftung.
        head_text = f.text(".phase-header.loop")
        for word in ("Läufe je Zyklus", "Start ab Uhrzeit"):
            expect(word in head_text, f"'{word}' fehlt im Phasenkopf: {head_text!r}")
        f.image("sequenzen_phasenkopf")

        # ------------------------------------------- Die Auswahl gilt ueberall
        # **Welche Sequenz offen ist, gilt in JEDEM Reiter.** Sie war frueher
        # mit dem Speichern-Knopf zusammen ausgeblendet — und damit musste man
        # fuer einen Wechsel erst in den Editor zurueck, ausgerechnet aus den
        # Reitern, die am staerksten an der Sequenz haengen.
        for tab in ("editor", "sequences", "run", "scans",
                       "share", "tools", "settings"):
            f.tab(tab)
            visible = f.page.eval_on_selector_all(
                "#seq-select, #btn-load, #btn-new",
                "ns => ns.filter(n => n.offsetParent !== null).length")
            expect(visible == 3,
                   f"im Reiter '{tab}' fehlt die Sequenz-Auswahl "
                   f"({visible}/3 sichtbar)")
        # Das Speichern bleibt dagegen bei der Sequenz: zwei Speichern-Knoepfe
        # fuer zwei Dateien in einer Leiste sind die Falle, um die es ging.
        f.tab("scans")
        expect(not f.page.eval_on_selector(
            "#btn-save", "e => e.offsetParent !== null"),
            "der Sequenz-Speichern-Knopf steht im Scans-Reiter")

        # **Der offene Reiter folgt dem Wechsel.** Scans, Teilen und Werkzeuge
        # lesen aus `sequences/<name>/`, haengen aber an eigenem Zustand, den
        # `render()` nicht anfasst — ohne das Nachziehen stuenden dort die
        # Daten der VORIGEN Sequenz unter dem Namen der neuen.
        f.tab("tools")
        f.click_text("#wz-left button", "Punkte nachklicken")
        expect("Alpha" in f.text("#wz-middle"),
               f"der Bezug nennt nicht die offene Sequenz: {f.text('#wz-middle')[:120]!r}")
        f.page.select_option("#seq-select", "Beta")
        f.click("#btn-load")
        expect(f.page.eval_on_selector("#seq-select", "e => e.value") == "Beta",
               "die Auswahl steht nach dem Laden nicht auf 'Beta'")
        expect("Beta" in f.text("#wz-middle"),
               f"der Werkzeuge-Reiter zeigt nach dem Wechsel die alte Sequenz: "
               f"{f.text('#wz-middle')[:120]!r}")

        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Sequenzen", run)
