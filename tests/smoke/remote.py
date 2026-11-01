"""Rauchtest Fernstart-Reiter: Freigaben im Fenster setzen, ohne den Token zu zeigen.

Die Vertragssuite ruft `remote_*` direkt auf. Was sie nicht sehen kann: ob der
Reiter aufgeht, ob „erlauben“ unter „Zuletzt im Kanal“ wirklich in die Liste
der Mitte schreibt, ob ein neues Wort über Feld und Auswahl ankommt — und ob
der Token irgendwo in der Seite landet, und sei es in einem `value`.
"""

import json
import time
from pathlib import Path

from ._bridge import Window, main, sandbox

OWNER = "111111111111111111"
STRANGER = "333333333333333333"
TOKEN = "MTIz" + "a" * 20 + ".Gh1234." + "b" * 30


def setup():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import LoopPhase, Sequence, SequenceStep
    from autoclicker.persistence import find_sequence_path, save_sequence_file, sequence_file
    from autoclicker.remote.settings import (
        STATUS_FILE, RemoteSettings, RemoteUser, RemoteWord, save_settings,
    )

    sandbox("rauch_fernstart_")
    seq = Sequence(name="Raid", loop_phases=[LoopPhase(name="L", steps=[
        SequenceStep(key_press="a")])])
    save_sequence_file(seq, sequence_file(seq.name))
    Path("config.json").write_text('{"window_focus_check": false}', encoding="utf-8")
    save_settings(RemoteSettings(
        enabled=True, token=TOKEN, channel_id="444444444444444444", pc_name="Alex",
        users=[RemoteUser(OWNER, "Alex")], words=[RemoteWord("raid", "Raid")]))
    now = time.time()
    Path(STATUS_FILE).write_text(json.dumps({
        "enabled": True, "ready": True, "connected": True, "bot_name": "Clicker",
        "channel_name": "start", "error": "", "last_poll": now - 2, "clock_offset": 0.2,
        "content_missing": False, "stamp": now,
        "seen": [{"id": STRANGER, "name": "Ben", "at": now - 30},
                 {"id": OWNER, "name": "Alex", "at": now - 90}],
        "log": [{"at": now - 30, "who": "Ben", "text": "!start raid ignoriert — nicht "
                 "freigegeben", "ok": False}],
    }), encoding="utf-8")
    return StudioBridge(seq, find_sequence_path("Raid"), "sequences")


def run():
    from autoclicker.remote.settings import load_settings

    b = setup()
    error = []

    def expect(condition, text):
        if not condition:
            error.append(text)

    with Window(b) as f:
        f.tab("remote")
        expect(TOKEN not in f.page.content(), "der Token steht in der Seite")

        left = f.text("#rem-left")
        expect("VERBINDUNG" in left and "eingetragen" in left,
               f"links fehlt der eingetragene Token: {left[:200]!r}")
        expect("BEREIT?" in left, "die Hakenliste fehlt")
        # Alles ausser der Fensterfokus-Prüfung — genau die eine Lücke muss offen stehen.
        expect(f.count("#rem-ready .rem-check.ok") == 6,
               f"6 von 7 erfüllt erwartet (alles ausser Fokus), da: "
               f"{f.count('#rem-ready .rem-check.ok')}")

        middle = f.text("#rem-middle")
        expect("!start raid" in middle, f"das freigegebene Wort fehlt: {middle[:200]!r}")
        expect("Fensterfokus-Prüfung einschalten" in middle,
               "der Hinweis auf die fehlende Fokus-Prüfung fehlt")

        right = f.text("#rem-right")
        expect("Clicker" in right and "#start" in right,
               f"die Verbindung steht nicht da: {right[:200]!r}")
        expect("ZULETZT IM KANAL" in right and "Ben" in right, "„Zuletzt im Kanal“ fehlt")
        expect("nicht freigegeben" in right, "die letzten Befehle fehlen")
        f.image("fernstart")

        # „erlauben“ unter „Zuletzt im Kanal“ schreibt die Person in die Liste.
        f.click_text("#rem-seen button", "erlauben")
        expect(any(u.id == STRANGER for u in load_settings().users),
               "„erlauben“ hat die Person nicht eingetragen")
        expect("Ben" in f.text("#rem-users"), "die Person steht nicht in der Mitte")

        # Ein neues Wort über Feld und Auswahl.
        f.page.fill("#rem-word-add input", "Farm")
        f.page.select_option("#rem-word-add select", "Raid")
        f.click_text("#rem-word-add button", "freigeben")
        expect(any(w.word == "farm" for w in load_settings().words),
               "das neue Wort ist nicht in remote.json angekommen")
        expect("!start farm" in f.text("#rem-words"), "das neue Wort steht nicht in der Liste")

        # Und wieder weg — über den Papierkorb seiner Zeile.
        rows = f.page.query_selector_all("#rem-words .rem-row")
        farm = [r for r in rows if "!start farm" in (r.inner_text() or "")]
        expect(len(farm) == 1, "die Zeile des neuen Worts fehlt")
        if farm:
            farm[0].query_selector("button").click()
            f.settle()
        expect(all(w.word != "farm" for w in load_settings().words),
               "das Wort ist nicht entfernt worden")

        # Der Schalter schaltet.
        f.page.uncheck("#rem-left label.on input[type=checkbox]")
        f.settle()
        expect(load_settings().enabled is False, "der Schalter hat remote.json nicht geändert")
        expect("Fernstart aus" in f.text("#rem-left"), "der Schalter sagt nicht, dass er aus ist")
        expect(TOKEN not in f.page.content(), "nach dem Bedienen steht der Token in der Seite")
        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Fernstart", run)
