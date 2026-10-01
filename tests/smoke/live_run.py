"""Rauchtest Live-Run: die Karte „Letzter Item-Scan“.

Die Vertragssuite prüft, was die Laufzeit in den Laufstatus schreibt und dass
die Brücke die Vorlagenbilder anhängt. Was sie nicht sehen kann: ob die Seite
daraus wirklich Kacheln baut, ob die Bilder ankommen und ob die Karte auch in
der Zusammenfassung nach dem Lauf stehen bleibt. Der Laufstatus ist hier eine
gestellte `.run.json` — der Hauptprozess läuft im Rauchtest nicht.
"""

import json
import struct
import time
import zlib
from pathlib import Path

from ._bridge import Window, main, sandbox


def _png(color: tuple, width: int = 8, height: int = 8) -> bytes:
    """Ein einfarbiges PNG — ohne Pillow."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _status(active: bool) -> dict:
    now = time.time()
    last_scan = {
        "name": "Inventar", "at": now - 12, "templates": str(Path("templates").resolve()),
        "slots": 45, "recognized": 23, "clicked": 2,
        "items": [
            {"item": "Godlike Bow", "category": "Bogen", "priority": 1,
             "template": "bow.png", "slots": ["Slot 3"], "clicked": 1},
            {"item": "Diamond Ore", "category": "Ore", "priority": 2,
             "template": "ore.png", "slots": [f"Slot {i}" for i in range(10, 30)],
             "clicked": 1},
            {"item": "Old Boot", "category": "", "priority": 9,
             "template": "", "slots": ["Slot 40", "Slot 41"], "clicked": 0},
        ],
        # Drei Slots nebeneinander: einer geklickt, einer erkannt, einer leer.
        "picture": {"stamp": now, "width": 300, "height": 100, "boxes": [
            {"x": 10, "y": 20, "w": 60, "h": 60, "slot": "Slot 3",
             "item": "Godlike Bow", "clicked": True},
            {"x": 110, "y": 20, "w": 60, "h": 60, "slot": "Slot 10",
             "item": "Diamond Ore", "clicked": False},
            {"x": 210, "y": 20, "w": 60, "h": 60, "slot": "Slot 4",
             "item": "", "clicked": False}]}}
    base = {"sequence": "Farm", "start": now - 300, "cycle": 2, "cycles": 0,
            "stamp": now, "last_scan": last_scan}
    if active:
        base.update({"active": True, "block": 3, "blocks": 8,
                     "block_label": "Item-Scan 'Inventar' (all)",
                     "block_set_type": "item_scan", "block_since": now - 1})
    else:
        base.update({"active": False, "end": now, "reason": "gestoppt",
                     "elapsed_cycles": 2, "duration": 300})
    return base


def setup():
    from autoclicker.config import LAST_SCAN_IMAGE_FILE, RUN_STATUS_FILE
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import LoopPhase, Sequence, SequenceStep
    from autoclicker.persistence import list_available_sequences, save_sequence_file, sequence_file

    sandbox("rauch_live_")
    Path("templates").mkdir()
    Path("templates/bow.png").write_bytes(_png((200, 60, 60)))
    Path("templates/ore.png").write_bytes(_png((60, 110, 230)))
    Path(LAST_SCAN_IMAGE_FILE).write_bytes(_png((40, 44, 52), 300, 100))
    seq = Sequence(name="Farm", loop_phases=[LoopPhase(name="A", steps=[
        SequenceStep(item_scan="Inventar")])])
    save_sequence_file(seq, sequence_file(seq.name))
    Path(RUN_STATUS_FILE).write_text(json.dumps(_status(True)), encoding="utf-8")
    return StudioBridge(seq, Path(dict(list_available_sequences())["Farm"]), "sequences")


def run():
    from autoclicker.config import RUN_STATUS_FILE
    b = setup()
    error = []

    def expect(condition, text):
        if not condition:
            error.append(text)

    with Window(b) as f:
        f.tab("run")
        f.page.wait_for_selector(".last-scan", timeout=5000)
        text = f.text("#view-run")
        expect("LETZTER ITEM-SCAN" in text, f"die Karte fehlt: {text[:300]!r}")
        expect("45 Slots gescannt · 23 erkannt · 22 ohne Treffer · 2 geklickt" in text,
               f"die Zusammenfassung stimmt nicht: {text!r}")
        expect(f.count(".last-scan-item") == 3,
               f"3 Kacheln erwartet, da: {f.count('.last-scan-item')}")
        expect(f.count(".last-scan-item.clicked") == 2,
               f"2 geklickte erwartet, da: {f.count('.last-scan-item.clicked')}")
        # Die Bilder muessen wirklich laden, nicht nur als <img> dastehen.
        loaded = f.page.eval_on_selector_all(
            ".last-scan-item img", "els => els.map(e => e.complete && e.naturalWidth > 0)")
        expect(loaded == [True, True], f"die Vorlagenbilder laden nicht: {loaded!r}")
        # Das Bild, das der Scan gesehen hat, mit einem Rahmen je Slot.
        picture = f.page.eval_on_selector(
            ".last-scan-picture img", "e => e.complete && e.naturalWidth")
        expect(picture == 300, f"das Scan-Bild laedt nicht: {picture!r}")
        expect(f.count(".last-scan-box") == 3
               and f.count(".last-scan-box.clicked") == 1
               and f.count(".last-scan-box.empty") == 1,
               "die Rahmen stimmen nicht (3, davon 1 geklickt, 1 leer)")
        # Die Rahmen sitzen dort, wo die Slots im Bild sind — in Prozent, also
        # auch bei verkleinertem Bild.
        x = f.page.eval_on_selector(
            ".last-scan-picture", "p => Math.round("
            "p.querySelector('.last-scan-box').offsetLeft / p.offsetWidth * 300)")
        expect(x == 10, f"der erste Rahmen sitzt nicht bei x=10: {x!r}")
        expect(f.count(".last-scan-noimg") == 1, "ohne Vorlage fehlt der Platzhalter")
        expect("20× · 1 geklickt · Ore · P2" in text,
               f"die Zeile unter dem Namen stimmt nicht: {text!r}")
        f.image("live_run")

        # Nach dem Ende bleibt sie in der Zusammenfassung stehen.
        Path(RUN_STATUS_FILE).write_text(json.dumps(_status(False)), encoding="utf-8")
        f.page.wait_for_selector(".lamp.done", timeout=5000)
        f.settle()
        expect(f.count(".last-scan-item") == 3,
               "nach dem Ende ist die Karte weg")
        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Live-Run", run)
