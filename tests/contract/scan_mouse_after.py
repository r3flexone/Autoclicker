"""Nach einem Scan-Block steht die Maus nicht mehr auf dem letzten Treffer.

Ein Scan klickt, was er findet, und der Zeiger blieb dort stehen — das Spiel
zeigt dann den Infotext des Items, und der liegt womöglich über dem Ziel des
nächsten Blocks. Zwei Fragen, zwei Stellen: OB die Maus danach abgesetzt
wird, schaltet der Scan-Block (`mouse_return`, an ist Standard); WOHIN, sagt
`scan_mouse_after` in den Einstellungen — zurück an die Stelle von vor dem
Scan (Voreinstellung) oder auf die Parkposition. Nie aber gegen den Nutzer:
nach einem Stopp und in der Pause bleibt die Maus, wo sie ist.
"""
import contextlib as _cl
import io as _io

from ._harness import check, section
from autoclicker.config import AppConfig as _AC, SCAN_MOUSE_AFTER as _MODES
from autoclicker.config_meta import META as _META
from autoclicker.models import AutoClickerState as _ST, SequenceStep as _STEP
import autoclicker.runtime.steps as _S

# =============================================================================
section("Config: Maus nach dem Scan")
# =============================================================================
check("Voreinstellung ist zurück an die Stelle davor", _AC().scan_mouse_after == "back")
with _cl.redirect_stdout(_io.StringIO()):
    _fixed = _AC(scan_mouse_after="weg")
check("ein unbekannter Wert fällt auf zurück", _fixed.scan_mouse_after == "back")
check("die Einstellungen bieten genau die beiden Ziele an",
      tuple(k for k, _ in _META["scan_mouse_after"].options) == _MODES)

# =============================================================================
section("Laufzeit: welcher Block zählt als Scan")
# =============================================================================
check("Item-, Boss-, Icon-Scan und Boss-Watcher",
      [_S._scan_handler(s) is not None for s in (
          _STEP(item_scan="a"), _STEP(boss_scan="a"), _STEP(icon_scan="a"),
          _STEP(boss_watcher="a"))] == [True] * 4)
check("ein Klick nicht", _S._scan_handler(_STEP(x=1, y=1, point_id=1)) is None)

# =============================================================================
section("Laufzeit: wohin die Maus nach dem Scan geht")
# =============================================================================
_cursor = [(0, 0)]
_moves = []


def _set(x, y):
    _moves.append((x, y))
    _cursor[0] = (x, y)
    return True


_orig = (_S.get_cursor_pos, _S.set_cursor_pos)
_S.get_cursor_pos = lambda: _cursor[0]
_S.set_cursor_pos = _set


def _run(mode, park=False, during=None, on=True):
    """Ein Scan, der die Maus auf einen Treffer (500, 500) klickt."""
    st = _ST()
    st.config.scan_mouse_after = mode
    st.config.scan_park_mouse = park
    _cursor[0] = (10, 20)
    _moves.clear()

    def scan(state, step, n, total, phase):
        _set(500, 500)
        if during:
            during(state)
        return True

    result = _S._with_mouse_return(st, scan, _STEP(item_scan="a", mouse_return=on),
                                   1, 1, "L")
    return result, _cursor[0]


try:
    check("zurück: die Maus steht wieder, wo sie vor dem Scan stand",
          _run("back") == (True, (10, 20)))
    check("Parkposition: die Maus geht dorthin",
          _run("park", park=[7, 8])[1] == (7, 8))
    check("Parkposition ohne gesetzte Stelle: zurück an die Stelle davor",
          _run("park", park=False)[1] == (10, 20))
    _run("back", on=False)
    check("Schalter am Block aus: nach dem Treffer wird die Maus nicht bewegt",
          _moves == [(500, 500)] and _cursor[0] == (500, 500))
    _run("back", during=lambda st: st.stop_event.set())
    check("nach einem Stopp bleibt sie, wo sie ist", _cursor[0] == (500, 500))
    _run("back", during=lambda st: st.pause_event.set())
    check("in der Pause ebenso", _cursor[0] == (500, 500))
finally:
    _S.get_cursor_pos, _S.set_cursor_pos = _orig


# =============================================================================
section("Schalter am Scan-Block: Datei und Studio")
# =============================================================================
from autoclicker.persistence.serialization import _parse_steps as _parse, _step_to_dict as _dump  # noqa: E402
from autoclicker.editors.sequence_studio.model import set_block_type as _set_type  # noqa: E402
from autoclicker.models import BLOCK_CLICK as _CLICK, BLOCK_ITEM_SCAN as _ITEM  # noqa: E402

check("an (Standard) steht nicht in der Datei", "mouse_return" not in _dump(_STEP(item_scan="a")))
_off = _dump(_STEP(item_scan="a", mouse_return=False))
check("aus steht drin", _off.get("mouse_return") is False)
check("und kommt zurück", _parse([_off])[0].mouse_return is False)
check("eine Datei ohne das Feld ist an", _parse([{"item_scan": "a"}])[0].mouse_return is True)
_typed = _STEP(item_scan="a", mouse_return=False)
_set_type(_typed, _ITEM)
check("ein Wechsel zwischen Scan-Arten behält den Schalter", _typed.mouse_return is False)
_set_type(_typed, _CLICK)
check("ein Klick-Block trägt kein Aus mit sich herum", _typed.mouse_return is True)
