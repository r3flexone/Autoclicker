"""Rauchtest Folgesequenz: „Danach starten" und „Pause davor" im Editor.

Die Vertragssuite ruft `sequence_set` direkt auf. Was sie nicht sieht: ob die
Auswahl die vorhandenen Sequenzen anbietet, ob eine Änderung darin wirklich
bei der Brücke ankommt (Feldname, Listener) und ob der Stand den Neuaufbau
überlebt. Dazu ein Name, den es nicht mehr gibt — er muss als „(fehlt)"
stehen bleiben, statt still auf „keine" zu springen.
"""

from pathlib import Path

from ._bridge import Window, main, sandbox


def setup():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import LoopPhase, Sequence, SequenceStep
    from autoclicker.persistence import list_available_sequences, save_sequence_file, sequence_file

    sandbox("rauch_danach_")
    for name in ("Holz", "Bank"):
        seq = Sequence(name=name, loop_phases=[LoopPhase(name="A", steps=[
            SequenceStep(key_press="a")])])
        save_sequence_file(seq, sequence_file(name))
    seq = Sequence(name="Holz", next_sequence="Weg", loop_phases=[LoopPhase(
        name="A", steps=[SequenceStep(key_press="a")])])
    return StudioBridge(seq, Path(dict(list_available_sequences())["Holz"]), "sequences")


def run():
    b = setup()
    error = []

    def expect(condition, text):
        if not condition:
            error.append(text)

    with Window(b) as f:
        f.tab("editor")
        options = f.page.eval_on_selector_all("#seq-next option", "os => os.map(o => o.textContent)")
        expect(options[:1] == ["(keine)"], f"„(keine)“ fehlt vorn: {options!r}")
        expect("Bank" in options, f"Bank fehlt in der Auswahl: {options!r}")
        expect("Holz (diese nochmal)" in options, f"die eigene fehlt: {options!r}")
        expect("Weg (fehlt)" in options and f.page.input_value("#seq-next") == "Weg",
               f"ein toter Name springt weg: {options!r}")

        f.page.select_option("#seq-next", "Bank")
        f.settle()
        expect(b.board.next_sequence == "Bank",
               f"die Wahl kommt nicht an: {b.board.next_sequence!r}")
        expect(f.page.input_value("#seq-next") == "Bank", "die Wahl übersteht den Neuaufbau nicht")
        expect(not f.page.is_disabled("#seq-next-delay"), "die Pause bleibt gesperrt")

        f.page.fill("#seq-next-delay", "90")
        f.page.press("#seq-next-delay", "Tab")
        f.settle()
        expect(b.board.next_delay == 90.0, f"die Pause kommt nicht an: {b.board.next_delay!r}")
        f.image("next_sequence")

        f.page.select_option("#seq-next", "")
        f.settle()
        expect(b.board.next_sequence == "" and f.page.is_disabled("#seq-next-delay"),
               "„(keine)“ nimmt die Folgesequenz nicht weg")
        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Folgesequenz", run)
