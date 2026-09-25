"""Blöcke aus einer anderen Sequenz einfügen — die billige Fassung von „Bausteine".

Eine bewusste, einmalige Kopie: `block_import` holt alle Blöcke der Quelle
(INIT, Loop-Phasen, END in Laufreihenfolge) und setzt sie hinter den gewählten
Block. Punkt-IDs sind sequenzlokal, also bekommen die Kopien eigene Punkte;
Scans gehören der Quelle und werden nur genannt.
"""
import os as _os
import re as _re
import shutil as _sh
import tempfile as _tmp

from ._harness import check, section, studio_web_source
from autoclicker.models import (
    ClickPoint as _CP,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
    WaitCondition as _WC,
)
from autoclicker.persistence import save_sequence_file, sequence_file
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB


def _save(seq):
    path = sequence_file(seq.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(seq, path)
    return path


# =============================================================================
section("Blöcke aus Sequenz X einfügen: hinter dem gewählten, mit eigenen Punkten")
# =============================================================================
_sandbox = _tmp.mkdtemp(prefix="bausteine_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    # Ziel: zwei Klicks auf #1 und #2.
    _target = _SEQ("ziel", loop_phases=[_PHASE("L1", steps=[
        _STEP(x=10, y=10, point_id=1), _STEP(x=20, y=20, point_id=2)])],
        points=[_CP(10, 10, "P1", 1), _CP(20, 20, "P2", 2)])
    _path = _save(_target)
    # Quelle: dieselben IDs, aber ANDERE Stellen — genau der Fall, an dem eine
    # uebernommene ID auf den falschen Knopf zeigte. Dazu ein FARBE+KLICK
    # (Klick und Pruef-Pixel derselbe Punkt), ein Block auf einen Punkt, den es
    # in der Quelle nicht gibt, und ein Scan-Verweis.
    _source = _SEQ("bank",
                   init_steps=[_STEP(x=300, y=300, point_id=1)],
                   loop_phases=[_PHASE("L1", steps=[
                       _STEP(x=400, y=400, point_id=2,
                             wait_condition=_WC(point_id=2)),
                       _STEP(x=0, y=0, point_id=99),
                       _STEP(item_scan="truhe")])],
                   end_steps=[_STEP(key_press="esc")],
                   points=[_CP(300, 300, "Tor", 1, color=(1, 2, 3)),
                           _CP(400, 400, "Kasse", 2, color=(4, 5, 6))])
    _save(_source)

    _b = _SB(_target, _path, "sequences")
    _loop = next(i for i, ln in enumerate(_b.board.lanes) if ln.kind == "loop")
    _lane = _b.board.lanes[_loop]

    _res = _b.block_import({"name": "bank"})
    check("ohne Auswahl wird nichts eingefügt",
          _res["status"]["kind"] == "warn" and len(_lane.steps) == 2)

    _b.select({"phase": _loop, "row": 0})
    _res = _b.block_import({"name": "ziel"})
    check("die offene Sequenz in sich selbst einzufügen wird abgelehnt",
          _res["status"]["kind"] == "warn" and len(_lane.steps) == 2)

    _b.select({"phase": _loop, "row": 0})
    _res = _b.block_import({"name": "bank"})
    _steps = _b.board.lanes[_loop].steps
    check("vier Blöcke kommen mit, in Laufreihenfolge, HINTER dem gewählten",
          len(_steps) == 6 and _steps[0].point_id == 1 and _steps[5].point_id == 2
          and _steps[4].key_press == "esc" and _steps[3].item_scan == "truhe")
    check("die Kopien bekommen eigene Punkte mit neuen IDs",
          _steps[1].point_id not in (1, 2) and _steps[2].point_id not in (1, 2))
    _by_id = {p.id: p for p in _b.points}
    check("an den Stellen der QUELLE, nicht an denen gleicher ID im Ziel",
          (_by_id[_steps[1].point_id].x, _by_id[_steps[1].point_id].y) == (300, 300)
          and (_by_id[_steps[2].point_id].x, _by_id[_steps[2].point_id].y) == (400, 400))
    check("Klick und Pruef-Pixel eines FARBE+KLICK bleiben EIN Punkt",
          _steps[2].wait_condition.point_id == _steps[2].point_id)
    check("die Punkte des Ziels bleiben unberuehrt",
          (_by_id[1].x, _by_id[2].x) == (10, 20) and len(_b.points) == 4)
    _text = _res["status"]["text"]
    check("der Block mit fehlendem Punkt wird ausgelassen und gezaehlt",
          "ausgelassen" in _text and _res["status"]["kind"] == "warn")
    check("der fehlende Scan wird beim Namen genannt", "'truhe'" in _text)
    check("die eingefügten Blöcke sind die neue Auswahl",
          _b.sel_rows == {1, 2, 3, 4})

    _b.undo()
    check("STRG+Z nimmt den ganzen Durchgang zurück — Blöcke UND Punkte",
          len(_b.board.lanes[_loop].steps) == 2 and len(_b.points) == 2)
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)

_web = studio_web_source()
check("der Inspektor ruft block_import mit dem gewählten Namen",
      'call("block_import", {name: source.value})' in _web)

# Aufgeklappte Auswahllisten malt der Browser selbst. Ohne `color-scheme:
# dark` malte er sie hell, und die Eintraege erbten die helle Schrift der
# Seite: weiss auf weiss, nur der gewaehlte Eintrag lesbar. Das betrifft jede
# Klappliste — die Sequenz-Auswahl im Kopf ebenso wie „aus Sequenz …" hier.
check("die Seite erklaert sich dem Browser als dunkel",
      _re.search(r":root\s*\{[^}]*color-scheme\s*:\s*dark", _web) is not None)
check("Eintraege einer Klappliste haben eigene Flaeche UND Schrift",
      _re.search(r"option[^{]*\{[^}]*background:var\(--panel\)[^}]*color:var\(--text\)",
                 _web) is not None)
