"""Sicherungen der Laufzeit, die bis zum Umbau keine Prüfung hatten.

Aufgefallen bei der Gegenprobe nach dem Zerlegen von `runtime/`: an diesen
fünf Stellen konnte man die Sicherung entfernen, und die ganze Suite blieb
grün. Jede Prüfung hier wird auf der entschärften Fassung rot.
"""
import contextlib as _cl
import io as _io

from ._harness import check, section

import autoclicker.runtime.actions as _RA
import autoclicker.runtime.debug as _DBG
import autoclicker.runtime.item_scan as _RI
from autoclicker.models import (
    AutoClickerState as _ST, ClickPoint as _CP, ItemProfile as _IP, ItemScanConfig as _ISC,
    ItemSlot as _SLOT,
)


@_cl.contextmanager
def _patched(*stubs):
    saved = [(module, name, getattr(module, name)) for module, name, _ in stubs]
    for module, name, value in stubs:
        setattr(module, name, value)
    try:
        with _cl.redirect_stdout(_io.StringIO()):
            yield
    finally:
        for module, name, value in reversed(saved):
            setattr(module, name, value)


# =============================================================================
section("Wartezeit: CTRL+ALT+K beendet sie und wird verbraucht")
# =============================================================================
# Bliebe K gesetzt, übersprange es die NÄCHSTE Wartezeit gleich mit — ein
# Tastendruck, zwei übersprungene Blöcke.
_st = _ST()
_st.skip_event.set()
with _patched((_RA, "log_event", lambda *a, **k: None)):
    _done = _RA.wait_with_pause_skip(_st, 30, "LOOP", 1, 1, "warte")
check("die Wartezeit endet sofort und gilt als erledigt", _done is True)
check("und K ist danach verbraucht", not _st.skip_event.is_set())

# =============================================================================
section("Item-Scan: eine schon geklickte Kategorie")
# =============================================================================
# Eine Kategorie heisst „nimm nur das beste". Hat dieser Zyklus darin schon
# P2 geklickt, ist ein weiteres P2 nicht besser — es fällt weg wie ein P3.
_st = _ST()
_st.clicked_categories["Waffe"] = 2
_slot = _SLOT("S1", (0, 0, 10, 10), (5, 5))
_found = [(_slot, _IP("Bogen", [], category="Waffe", priority=2), 2),
          (_slot, _IP("Axt", [], category="Waffe", priority=1), 1)]
with _patched((_RI, "load_market_values", lambda path: {})):
    _left = _RI._filter_scan_results(_st, _found, "all", False)
check("gleich gut wie das schon Geklickte: fällt weg, nur das bessere bleibt",
      [item.name for _pos, item, _p in _left] == ["Axt"])
with _patched((_RI, "load_market_values", lambda path: {})):
    _left = _RI._filter_scan_results(_st, _found[:1], "all", False)
check("allein gefunden wird es nicht geklickt", _left == [])

# =============================================================================
section("Item-Klick: der Klick danach (Bestätigung)")
# =============================================================================
_st = _ST()
_st.config.scan_item_click_delay = 0
_clicks = []
_item = _IP("Bogen", [], confirm_delay=0)
_item.confirm_point = _CP(70, 80, "Ja", 3)
with _patched((_RI, "safe_click", lambda s, x, y, label="": _clicks.append((x, y, label)) or True),
              (_RI, "log_event", lambda *a, **k: None)):
    _ok = _RI._click_scan_result(_st, (5, 6), _item, 1, False)
check("erst das Item, dann die Bestätigung",
      _ok is True and [(x, y) for x, y, _l in _clicks] == [(5, 6), (70, 80)])
check("beide Klicks gezählt", _st.total_clicks == 2 and _st.items_found == 1)
_clicks.clear()
with _patched((_RI, "safe_click", lambda s, x, y, label="": _clicks.append((x, y)) or label.startswith("item")),
              (_RI, "log_event", lambda *a, **k: None)):
    _ok = _RI._click_scan_result(_ST(), (5, 6), _item, 1, False)
check("eine verweigerte Bestätigung bricht ab", _ok is False and len(_clicks) == 2)

# =============================================================================
section("Auto-Lernen: eine Vorlage, die nicht geschrieben werden kann")
# =============================================================================
# Das Item ist dann schon reserviert (im Scan sichtbar). Ohne Vorlage taugt
# es nichts — es muss wieder verschwinden, sonst steht ein Item ohne Bild im Scan.


class _Unwritable:
    def save(self, path):
        raise OSError("Platte voll")


_st = _ST()
_cfg = _ISC("inv", items=[_IP("Alt", [])])
_learned = _IP("Auto S1", [], template="auto_s1.png")
_cfg.items.append(_learned)
_st.active_item_scan = "inv"
_st.global_items = {"Alt": _cfg.items[0], "Auto S1": _learned}
import tempfile as _tmp
from pathlib import Path as _Path
with _patched():
    _kept = _RI._store_learned_template(_st, _cfg, _learned, _Unwritable(),
                                        _Path(_tmp.mkdtemp(prefix="lernen_")))
check("das reservierte Item fällt wieder heraus",
      _kept is False and [it.name for it in _cfg.items] == ["Alt"])
check("auch aus der Arbeitsansicht der Konsole", "Auto S1" not in _st.global_items)

# =============================================================================
section("Punkte-Durchgang: 'n' setzt und geht zum nächsten Punkt")
# =============================================================================
_st = _ST()
_st.points = [_CP(10, 10, "P1", 1), _CP(20, 20, "P2", 2)]
_visited, _keys = [], ["n", "q"]
import autoclicker.persistence as _PERS
with _patched((_DBG, "read_command", lambda *a, **k: _keys.pop(0) if _keys else "q"),
              (_DBG, "set_cursor_pos", lambda x, y: _visited.append((x, y))),
              (_DBG, "get_cursor_pos", lambda: (55, 66)),
              (_PERS, "save_points", lambda state: True)):
    _DBG.walk_points(_st)
check("nach 'n' steht der Zeiger auf dem nächsten Punkt",
      _visited == [(10, 10), (20, 20)] and (_st.points[0].x, _st.points[0].y) == (55, 66))
