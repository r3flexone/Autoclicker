"""Rauchtest Übersicht und Editor: messen sich die Karten ein, klebt der Kopf?

Beides sieht die Vertragssuite nicht: sie kennt keine Kästen und keine
Scrollposition. Ein `subgrid`, das der Browser nicht kann, und ein `sticky`, das
an einem nicht scrollenden Vorfahren hängt, fallen nur hier auf.
"""

import sys

from ._bridge import Window, main, make_expect, sandbox


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
    from autoclicker.models import ClickPoint
    from autoclicker.persistence.sequences import save_sequence_file, sequence_file

    sandbox("rauch_sequenzen_")
    sequences = {}
    # Die MITTLERE Karte ohne Notiz — genau daran rutschte alles darunter hoch.
    for name, note, phases, steps_list in (("Alpha", "Mit einer Notiz", 1, 50),
                                          ("Beta", "", 11, 1),
                                          ("testaufnahme_mit_sehr_langem_namen_v2",
                                           "Auch mit Notiz", 1, 1)):
        sequences[name] = _sequence(name, note, phases, steps_list)
    # Genug Punkte, damit die linke Spalte laenger wird als das Fenster.
    sequences["Alpha"].points = [
        ClickPoint(x=i, y=i, name=f"Punkt {i}", id=i) for i in range(1, 41)
    ]
    for name, seq in sequences.items():
        save_sequence_file(seq, sequence_file(name))
    from autoclicker.persistence import list_available_sequences
    return StudioBridge(sequences["Alpha"],
                        dict(list_available_sequences())["Alpha"], "sequences")


def run():
    b = setup()
    error = []
    expect = make_expect(error)

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
        expect(f.count(".recording-row .info") == 0,
               "der reine Werkzeug-Verweis hat noch ein ueberfluessiges i")
        field_heights = f.page.eval_on_selector_all(
            "#seq-cycles, #seq-blocks",
            "ns => ns.map(n => Math.round(n.getBoundingClientRect().height))")
        expect(len(field_heights) == 2 and field_heights[0] == field_heights[1],
               f"Zyklen und Bloecke haben verschiedene Kachelhoehen: {field_heights}")
        # Eine Kachel ja — aber gestrichelt: mit derselben durchgezogenen wie
        # „Zyklen" daneben sah die Anzahl aus wie ein Feld zum Tippen.
        expect(f.page.eval_on_selector(
            "#seq-blocks", "e => getComputedStyle(e).borderTopStyle") == "dashed",
            "die berechnete Blockanzahl sieht aus wie ein Eingabefeld")
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
        scrolled = f.page.eval_on_selector(".page.left", "e => e.scrollTop")
        expect(scrolled > 0, "die linke Spalte scrollt gar nicht — Test misst nichts")
        expect(before == after,
               f"der Block scrollt mit: {before} -> {after}")
        f.image("sequenzen_editor")

        # ------------------------------------------------ Der Phasenkopf
        # In voller Breite: unter 1400 px zeigt der Kopf nur Name und
        # Zusammenfassung (s. „Kleines Fenster" unten).
        f.page.set_viewport_size({"width": 1500, "height": 560})
        f.tab("editor")
        # **Kein „×" am ENDE einer Beschriftung.** Der Skalieren-Knopf hiess
        # „Wartezeiten ×" — dort, wo jede andere Oberflaeche ein Schliesskreuz
        # hat, las sich das als „wegmachen" statt als „mal". Daneben stand ein
        # zweites × als Vorsatz der Wiederholungen, und der Kopf sah aus, als
        # liesse sich dort etwas entfernen.
        button_texts = f.page.eval_on_selector_all(
            ".phase-header.loop button", "ns => ns.map(n => n.textContent.trim())")
        expect(not any("×" in t for t in button_texts),
               f"ein Knopf im Phasenkopf traegt ein ×: {button_texts}")
        # **Eigenschaften und Sammel-Aktionen sind getrennt.** In der
        # Werkzeugzeile stehen nur die beiden Felder, die die Phase
        # BESCHREIBEN; was auf alle Bloecke wirkt, steht unten beieinander.
        expect(f.count(".phase-tool button") == 0,
               "in der Eigenschaften-Zeile der Phase steht ein Knopf")
        # **Beide Zeilen liegen auf demselben Raster.** Vorher war oben ein
        # `flex` mit fest getippten 70/74 px und unten ein `button-pair`: die
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
          const span = (r) => [Math.round(r[0].left),
                               Math.round(r[r.length - 1].right)];
          const cells = boxEl('.phase-tool > *');
          const buttons = boxEl('.phase-all > .btn');
          return {props: span(cells), actions: span(buttons),
                  cellWidths: cells.map(r => Math.round(r.width)),
                  fields: boxEl('.phase-tool input').map(r => Math.round(r.width)),
                  buttons: buttons.map(r => Math.round(r.width)),
                  buttonTops: buttons.map(r => Math.round(r.top))};
        }""")
        expect(grid["props"] == grid["actions"],
               f"Eigenschaften und Sammel-Aktionen haben verschiedene Kanten: {grid}")
        expect(len(set(grid["fields"])) == 1,
               f"die beiden Felder sind verschieden breit: {grid}")
        # Ein Feld ist so breit wie ein Knopf — dasselbe Raster, nicht nur
        # zufaellig dieselbe Aussenkante.
        expect(set(grid["fields"]) == set(grid["buttons"]),
               f"Felder und Knoepfe liegen nicht auf demselben Raster: {grid}")
        expect(len(grid["buttons"]) == 2 and len(set(grid["buttons"])) == 1,
               f"zwei gleich breite Sammel-Knoepfe erwartet: {grid}")
        expect(len(set(grid["buttonTops"])) == 1,
               f"die Sammel-Knoepfe stehen nicht auf einer Zeile: {grid}")
        # Und die Felder sagen selbst, was sie sind — vorher stand das nur im
        # Tooltip, und ein Tooltip ist keine Beschriftung.
        head_text = f.text(".phase-header.loop")
        for word in ("Läufe je Zyklus", "Start ab Uhrzeit"):
            expect(word in head_text, f"'{word}' fehlt im Phasenkopf: {head_text!r}")
        f.image("sequenzen_phasenkopf")
        f.page.set_viewport_size({"width": 1300, "height": 560})
        f.settle()

        # ------------------------------------------- Die Auswahl gilt ueberall
        # **Welche Sequenz offen ist, gilt in JEDEM Reiter.** Sie war frueher
        # mit dem Speichern-Knopf zusammen ausgeblendet — und damit musste man
        # fuer einen Wechsel erst in den Editor zurueck, ausgerechnet aus den
        # Reitern, die am staerksten an der Sequenz haengen.
        for tab in ("editor", "sequences", "run", "scans",
                       "share", "tools", "settings"):
            f.tab(tab)
            visible = f.page.eval_on_selector_all(
                "#seq-select, #btn-new",
                "ns => ns.filter(n => n.offsetParent !== null).length")
            expect(visible == 2,
                   f"im Reiter '{tab}' fehlt die Sequenz-Auswahl "
                   f"({visible}/2 sichtbar)")
        # Das Speichern bleibt dagegen bei der Sequenz: zwei Speichern-Knoepfe
        # fuer zwei Dateien in einer Leiste sind die Falle, um die es ging.
        # Unsichtbar heisst `visibility`, nicht weg: der Platz bleibt (s. u.).
        f.tab("scans")
        expect(f.page.eval_on_selector(
            "#btn-save", "e => e.offsetParent === null "
                         "|| getComputedStyle(e).visibility === 'hidden'"),
            "der Sequenz-Speichern-Knopf steht im Scans-Reiter")

        # ------------------------------------------ Der Kopf springt nicht
        # **Der Kopf hat in jedem Reiter dieselbe Gestalt.** Die Sequenz-Knoepfe
        # verschwanden ausserhalb von Editor, Uebersicht und Live-Run ganz: im
        # Editor brach der Kopf bis gut 1550 px in zwei Zeilen um, in den Scans
        # nicht, und bei jedem Wechsel sprang die Seite um 35 px; „?" wanderte
        # von rechts oben nach links in die zweite Zeile.
        def head_shape():
            return f.page.evaluate("""() => {
              const r = (s) => document.querySelector(s).getBoundingClientRect();
              return [Math.round(r('header').height), Math.round(r('#btn-help').left),
                      Math.round(r('#btn-help').top), Math.round(r('.seq-chip').left)];
            }""")

        shapes = {}
        for tab in ("editor", "sequences", "scans", "run", "report",
                    "tools", "share", "remote", "settings"):
            f.tab(tab)
            shapes[tab] = head_shape()
        expect(len({tuple(s) for s in shapes.values()}) == 1,
               f"der Kopf hat je Reiter eine andere Gestalt: {shapes}")

        # **Und er passt in eine Zeile.** Die Grenze haengt an der Schrift:
        # unter Windows (Segoe UI) bei 1300 px, wie es die Regel verlangt; die
        # Schriften der Linux-CI laufen breiter, dort wird an der Standardgroesse
        # des Fensters gemessen (1600 px, `sequence_studio.py`).
        f.tab("editor")
        if sys.platform == "win32":
            width = 1300
        else:
            width = 1600
        f.page.set_viewport_size({"width": width, "height": 560})
        f.settle()
        one_row = f.page.evaluate("""() => {
          const top = (s) => document.querySelector(s).getBoundingClientRect().top;
          return Math.abs(top('#btn-run') - top('.tabs')) < 20
              && Math.abs(top('#btn-help') - top('.tabs')) < 20;
        }""")
        expect(one_row, f"der Kopf bricht bei {width} px im Editor um")
        f.page.set_viewport_size({"width": 1300, "height": 560})
        f.settle()

        # **Der offene Reiter folgt dem Wechsel.** Scans, Teilen und Werkzeuge
        # lesen aus `sequences/<name>/`, haengen aber an eigenem Zustand, den
        # `render()` nicht anfasst — ohne das Nachziehen stuenden dort die
        # Daten der VORIGEN Sequenz unter dem Namen der neuen.
        f.tab("tools")
        f.click_text("#tools-left button", "Punkte nachklicken")
        expect("Alpha" in f.text("#tools-middle"),
               f"der Bezug nennt nicht die offene Sequenz: {f.text('#tools-middle')[:120]!r}")
        # Die Auswahl laedt selbst - einen Laden-Knopf gibt es nicht mehr.
        f.page.select_option("#seq-select", "Beta")
        f.settle()
        expect(f.page.eval_on_selector("#seq-select", "e => e.value") == "Beta",
               "die Auswahl steht nach dem Laden nicht auf 'Beta'")
        expect("Beta" in f.text("#tools-middle"),
               f"der Werkzeuge-Reiter zeigt nach dem Wechsel die alte Sequenz: "
               f"{f.text('#tools-middle')[:120]!r}")

        # ------------------------------------------------- Kleines Fenster
        # **Ein Viertel eines 16:9-Bildschirms muss gehen** (960×540, ohne
        # Titelleiste gut 510). Die Seitenspalten standen fest bei 290 und
        # 370 px, und für das Board blieben gut 300 px — der Arbeitsbereich
        # wurde als erster gequetscht.
        f.tab("editor")
        f.page.set_viewport_size({"width": 960, "height": 510})
        f.settle()
        small = f.page.evaluate("""() => {
          const width = (s) => document.querySelector(s).getBoundingClientRect().width;
          const shown = (s) => [...document.querySelectorAll(s)]
            .some(n => n.offsetParent !== null);
          return {board: Math.round(width('#editor-body .board-wrap')),
                  body: shown('.phase .card-body'),
                  tool: shown('.phase-header .phase-tool'),
                  text: shown('#btn-save .btn-text')};
        }""")
        expect(small["board"] >= 0.4 * 960,
               f"das Board bekommt bei 960 px keine 40 % der Breite: {small}")
        # Die Blöcke zeigen nur ihre Kopfzeile: man sieht, wie die Sequenz
        # aussieht; Einzelheiten stehen rechts, sobald man etwas anklickt.
        expect(not small["body"] and not small["tool"],
               f"Karten oder Phasenköpfe zeigen bei 960 px alle Einzelheiten: {small}")
        expect(not small["text"], f"Speichern trägt bei 960 px seine Beschriftung: {small}")
        # Ob der Kopf dabei in EINE Zeile passt, hängt an der Schrift (s. o.):
        # unter Windows wird es gemessen, sonst nur, dass er zusammenrückt.
        if sys.platform == "win32":
            one_row = f.page.evaluate("""() => {
              const top = (s) => document.querySelector(s).getBoundingClientRect().top;
              return Math.abs(top('#btn-help') - top('.tabs')) < 20;
            }""")
            expect(one_row, "der Kopf bricht bei 960 px um")
        else:
            label = f.page.eval_on_selector(
                ".seq-chip-label", "e => getComputedStyle(e).display")
            expect(label == "none", f"der Kopf rückt bei 960 px nicht zusammen: {label}")
        # **Was der Phasenkopf nicht mehr zeigt, steht im Phasen-Menü.** Sonst
        # liessen sich Wiederholungen und Startzeit im kleinen Fenster gar nicht
        # mehr setzen.
        f.page.click(".phase-header.loop .row > .small")
        f.settle()
        fields = f.page.eval_on_selector_all(
            "#inspector .compact-only input", "ns => ns.filter(n => n.offsetParent).length")
        expect(fields == 2, f"Läufe/Startzeit fehlen im Phasen-Menü bei 960 px: {fields}")
        # Und bei voller Breite stehen sie wieder im Kopf — nur dort, nicht doppelt.
        f.page.set_viewport_size({"width": 1500, "height": 560})
        f.settle()
        doubled = f.page.eval_on_selector_all(
            "#inspector .compact-only", "ns => ns.filter(n => n.offsetParent).length")
        in_head = f.page.eval_on_selector_all(
            ".phase-header .phase-tool", "ns => ns.filter(n => n.offsetParent).length")
        expect(doubled == 0 and in_head > 0,
               f"bei voller Breite stehen die Phasenwerte doppelt oder gar nicht: "
               f"Menü {doubled}, Köpfe {in_head}")
        # **Die Einstellungen stapeln bei schmaler Spalte.** Text links und
        # Bedienelement rechts liessen der Erklärung bei 960 px ein Wort je Zeile.
        f.page.set_viewport_size({"width": 960, "height": 510})
        f.tab("settings")
        tracks = f.page.eval_on_selector(
            ".cfg-row", "e => getComputedStyle(e).gridTemplateColumns.split(' ').length")
        expect(tracks == 1, f"Einstellungen bei 960 px nicht gestapelt: {tracks} Spalten")
        f.image("sequenzen_klein")
        f.page.set_viewport_size({"width": 1300, "height": 560})
        f.settle()

        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Sequenzen", run)
