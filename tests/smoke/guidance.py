"""Rauchtest Orientierung: sieht man, wo man ist und was als Nächstes geht?

Die Vertragssuite hält die Regeln am Quelltext fest (`tests/contract/
studio_guidance.py`). Was sie nicht sehen kann, ist das, worum es beim ganzen
Durchgang ging: ob eine Phase, die rechts aus dem Board ragt, in der Leiste
wirklich blass steht, ob der Weiter-Knopf wirklich scrollt, ob die Meldung der
Scans unter dem Live-Run wirklich verschwindet — und ob eine Sprungmarke in
die Einstellungen wirklich im Feld landet.
"""

from pathlib import Path

from ._bridge import Window, main, sandbox


def setup():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import ClickPoint, LoopPhase, Sequence, SequenceStep
    from autoclicker.persistence import list_available_sequences, save_sequence_file, sequence_file
    from autoclicker.persistence.sequences import load_sequence_file

    sandbox("rauch_orientierung_")
    seq = Sequence(name="Runde", total_cycles=0,
                   points=[ClickPoint(x=10 * i, y=10, id=i, name=f"P{i}", color=(200, 60, 60))
                           for i in range(1, 5)])
    seq.init_steps = [SequenceStep(point_id=1)]
    seq.loop_phases = [LoopPhase(name=f"Phase {n}", repeat=2 if n == 1 else 1,
                                 steps=[SequenceStep(point_id=2), SequenceStep(point_id=3)])
                       for n in range(1, 5)]
    seq.end_steps = [SequenceStep(point_id=2)]
    save_sequence_file(seq, sequence_file(seq.name))
    path = Path(dict(list_available_sequences())[seq.name])
    # Punkt 4 benutzt keiner — der Überblick muss ihn melden.
    return StudioBridge(load_sequence_file(path), path, "sequences")


def run():
    b = setup()
    error = []

    def expect(condition, text):
        if not condition:
            error.append(text)

    with Window(b, width=1100, height=760) as f:
        # ------------------------------------------------ Phasenleiste und Kanten
        chips = f.page.eval_on_selector_all(
            ".phase-nav-chip[data-phase]", "ns => ns.map(n => n.textContent)")
        expect(len(chips) == 6, f"sechs Phasen erwartet (START, 4 Loops, ABSCHLUSS): {chips}")
        off = f.count(".phase-nav-chip.off")
        expect(off >= 2, f"bei 1100 px muessen Phasen ausser Sicht blass stehen, blass: {off}")
        expect(f.page.is_visible("#board-edge-right"),
               "rechts liegen Phasen ausser Sicht, aber die Kante sagt es nicht")
        expect(not f.page.is_visible("#board-edge-left"),
               "ganz links gibt es nichts mehr, trotzdem steht die linke Kante")
        before = f.page.eval_on_selector("#board", "e => e.scrollLeft")
        f.click("#board-step-right")
        f.page.wait_for_function(
            "(x) => document.getElementById('board').scrollLeft > x", arg=before,
            timeout=3000)   # weiches Scrollen: wartet auf die Position, nicht auf eine Uhr
        f.click('.phase-nav-chip[data-kind="end"]')
        # Angekommen ist die Spalte, wenn sie vorn im Board steht — oder das
        # Board nicht weiter kann (dahinter steht noch „+ Phase").
        f.page.wait_for_function(
            "() => { const b = document.getElementById('board');"
            " const cols = document.querySelectorAll('#phases > .phase[data-phase]');"
            " const c = cols[cols.length - 1];"
            " const atEnd = b.scrollLeft + b.clientWidth >= b.scrollWidth - 2;"
            " return atEnd || (c && c.getBoundingClientRect().left"
            "   - b.getBoundingClientRect().left < 40); }", timeout=3000)
        f.page.evaluate("() => updateBoardEdges()")
        expect(f.page.eval_on_selector('.phase-nav-chip[data-kind="end"]',
                                       "e => !e.classList.contains('off')"),
               "nach dem Klick auf ABSCHLUSS steht er immer noch als ausser Sicht da")

        # -------------------------------------------------- Seitenleiste weg / her
        f.click(".phase-nav .sidebar-toggle")
        expect(f.page.eval_on_selector("#editor-body .page.left", "e => e.offsetWidth") == 0,
               "die Seitenleiste laesst sich nicht wegklappen")
        f.click(".phase-nav .sidebar-toggle")
        expect(f.page.eval_on_selector("#editor-body .page.left", "e => e.offsetWidth") > 200,
               "die Seitenleiste kommt nicht zurueck")

        # ------------------------------------------------------------- Ueberblick
        overview = f.text("#inspector")
        expect("BLOCKTYPEN" in overview and "1 Punkt" in overview,
               f"der Ueberblick nennt Typen und den ungenutzten Punkt nicht: {overview!r}")
        expect(not f.page.is_visible("#btn-block-delete"),
               "im Ueberblick steht ein gesperrter Loeschen-Knopf")

        # ------------------------------------------------ Meldung gehoert dem Reiter
        f.click(".card")
        f.page.keyboard.press("Delete")
        f.settle()
        own = f.status()
        expect(bool(own.strip()), "Loeschen meldet nichts")
        f.tab("run")
        expect(not f.status().strip(),
               f"die Editor-Meldung steht unter dem Live-Run: {f.status()!r}")
        expect(not f.page.is_visible("#status-action"),
               "der Rueckgaengig-Knopf steht neben einer fremden (leeren) Meldung")
        f.tab("editor")
        expect(f.status() == own, f"der Editor bekommt seine Meldung nicht zurueck: {f.status()!r}")
        # Ein Klick auf eine Karte holt keine alte Meldung aus einem anderen
        # Reiter zurueck — und keine, die schon weggeraeumt war.
        f.tab("run")
        f.tab("sequences")
        expect(not f.status().strip(), "beim zweiten Reiterwechsel kam die Meldung wieder")

        # --------------------------------------------------- Live-Run-Vorschau
        f.tab("run")
        # Gegen die Momentaufnahme gezaehlt: oben wurde der einzige START-Block
        # geloescht, und eine leere Phase laeuft nicht — sie steht auch nicht da.
        tiles = f.count(".run-preview .phase-tile")
        want = f.page.evaluate("S.phases.filter((p) => p.blocks.length).length")
        expect(tiles == want == 5,
               f"die Vorschau zeigt nicht genau die Phasen mit Bloecken: {tiles} statt {want}")
        expect(f.count("#view-run .btn.launch") == 1,
               "Starten im Live-Run sieht anders aus als oben im Kopf")

        # ------------------------------------ Sprungmarke Bericht -> Einstellungen
        f.page.set_viewport_size({"width": 1500, "height": 900})
        f.tab("report")
        f.click_text("#rep-right button", "Marktwert-Datei eintragen")
        f.page.wait_for_function(
            "() => { const a = document.activeElement;"
            " return !!(a && a.closest && a.closest('#cfg-row-scan_market_value_file')); }",
            timeout=3000)
        expect(f.page.eval_on_selector(".tab.on", "e => e.dataset.view") == "settings",
               "die Sprungmarke oeffnet die Einstellungen nicht")
        on = f.page.eval_on_selector(".cfg-nav.on", "e => e.textContent")
        expect(on.startswith("Scans"), f"die Liste zeigt nicht den Abschnitt des Felds: {on!r}")
        groups = f.count(".cfg-group")
        expect(groups >= 10, f"die Einstellungen stehen nicht auf einer Seite: {groups} Abschnitte")

        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Orientierung", run)
