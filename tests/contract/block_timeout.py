"""Eine eigene Zeitgrenze je Block für das Warten auf eine Farbe.

Bis hierhin galt EINE Grenze für alle (`pixel_wait_timeout`): ein Block, der
auf das Ende eines langen Kampfs wartet, und einer, der auf einen Knopf wartet,
bekamen dieselbe Zeit — passend war sie immer nur für einen von beiden.
`WaitCondition.timeout`: None = die Einstellung, 0 = ohne Grenze, sonst Sekunden.
"""
import contextlib as _cl
import io as _io
import os as _os
import shutil as _sh
import tempfile as _tmp
import time as _time
from pathlib import Path as _P

from ._harness import check, section, studio_web_source
from autoclicker.models import (
    AutoClickerState as _ST,
    ClickPoint as _CP,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
    WaitCondition as _WC,
)
from autoclicker.persistence.serialization import _parse_steps, _step_to_dict
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
import autoclicker.runtime.steps as _S


# =============================================================================
section("Dateiformat: 'wait_timeout' nur, wenn gesetzt")
# =============================================================================
_own = _STEP(x=1, y=1, point_id=1, wait_condition=_WC(point_id=1, timeout=600))
_plain = _STEP(x=1, y=1, point_id=1, wait_condition=_WC(point_id=1))
check("eine eigene Grenze steht in der Datei",
      _step_to_dict(_own).get("wait_timeout") == 600)
check("ohne eigene Grenze steht nichts da (die Einstellung gilt)",
      "wait_timeout" not in _step_to_dict(_plain))
_back = _parse_steps([_step_to_dict(_own), _step_to_dict(_plain),
                      {"point_id": 1, "wait_point_id": 1, "wait_timeout": "abc"},
                      {"point_id": 1, "wait_point_id": 1, "wait_timeout": -5},
                      {"point_id": 1, "wait_point_id": 1, "wait_timeout": 0}])
check("zurückgelesen: 600, keine, kaputt → keine, negativ → 0, 0 bleibt 0",
      [s.wait_condition.timeout for s in _back] == [600.0, None, None, 0.0, 0.0])

# =============================================================================
section("Laufzeit: der Block wartet SEINE Zeit, nicht die der Einstellung")
# =============================================================================
_st = _ST()
_st.config.pixel_wait_timeout = 60
check("eigene Grenze gewinnt", _S.effective_timeout(_WC(timeout=5), _st.config) == 5)
check("0 heisst ohne Grenze — auch gegen eine gesetzte Einstellung",
      _S.effective_timeout(_WC(timeout=0), _st.config) == 0)
check("ohne eigene Grenze gilt die Einstellung",
      _S.effective_timeout(_WC(), _st.config) == 60)


class _Img:
    def getpixel(self, _xy):
        return (0, 0, 0)            # nie die gesuchte Farbe


_seen = []
_orig = (_S.take_screenshot, _S._handle_color_wait_timeout, _S.status.waiting_for,
         _S.pixel_crop, _S.PILLOW_AVAILABLE)
_S.take_screenshot = lambda region: _Img()
_S._handle_color_wait_timeout = lambda state, step, phase, n, t, timeout: (
    _seen.append(timeout) or "stop")
_S.status.waiting_for = lambda *a, **k: None
_S.pixel_crop = lambda x, y: None
_S.PILLOW_AVAILABLE = True
try:
    _st.config.pixel_check_interval = 0.01
    _st.config.pixel_wait_timeout = 1.0
    _step = _STEP(x=5, y=5, point_id=1,
                  wait_condition=_WC(point_id=1, pixel=(5, 5), color=(200, 0, 0), timeout=0.05))
    _t0 = _time.time()
    with _cl.redirect_stdout(_io.StringIO()):
        _S._execute_wait_for_color(_st, _step, 1, 1, "L")
    check("mit 0,05 s eigener Grenze endet das Warten sofort — trotz 1 s Einstellung",
          _seen == [0.05] and _time.time() - _t0 < 0.8)
finally:
    (_S.take_screenshot, _S._handle_color_wait_timeout, _S.status.waiting_for,
     _S.pixel_crop, _S.PILLOW_AVAILABLE) = _orig

# =============================================================================
section("Studio: setzen, zurücksetzen, anzeigen")
# =============================================================================
_sandbox = _tmp.mkdtemp(prefix="block_timeout_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    _seq = _SEQ("T", loop_phases=[_PHASE("L", [
        _STEP(x=1, y=1, point_id=1, wait_condition=_WC(point_id=1))])],
        points=[_CP(1, 1, "Gold", 1, color=(239, 196, 24))])
    with _cl.redirect_stdout(_io.StringIO()):
        _b = _SB(_seq, _P("sequences/t/sequence.json"), "sequences")
    _b.select({"phase": 1, "row": 0})
    _snap = _b.block_trigger({"choice": "present", "timeout": "600"})
    _step = _b.board.lanes[1].steps[0]
    check("600 gesetzt — am Block und im Inspektor",
          _step.wait_condition.timeout == 600 and _snap["block"]["trigger_timeout"] == 600)
    _text = _snap["phases"][1]["blocks"][0]["color_text"]
    check("die Karte sagt es beim Überfliegen",
          "max 600 s" in _text)
    # Die Kartenspalte ist schmal: mit gewöhnlichen Leerzeichen stand das „s"
    # allein in der nächsten Zeile. Werte und Einheiten reissen nicht.
    _value = _text.split("RGB(", 1)[-1]
    check("die FARBE-Zeile reisst weder im RGB-Wert noch zwischen Zahl und Einheit",
          _text.startswith("wartet bis RGB(")
          and all(" " not in part for part in _value.split(" · "))
          and _text.count(" · ") == 1)
    _snap = _b.block_trigger({"choice": "present", "timeout": "0"})
    check("0 heisst ohne Timeout — und so steht es auch auf der Karte",
          _step.wait_condition.timeout == 0
          and "ohne Timeout" in _snap["phases"][1]["blocks"][0]["color_text"])
    _snap = _b.block_trigger({"choice": "present", "timeout": ""})
    check("leer: zurück auf die Einstellung, und die Karte schweigt",
          _step.wait_condition.timeout is None
          and "max" not in _snap["phases"][1]["blocks"][0]["color_text"])
    _snap = _b.block_trigger({"choice": "present", "timeout": "-3"})
    check("negativ wird abgelehnt", _snap["status"]["kind"] == "warn"
          and _step.wait_condition.timeout is None)
    _b.block_trigger({"which": "verify", "choice": "present", "point": 1})
    _b.block_trigger({"which": "verify", "choice": "present", "timeout": "9"})
    check("die Nachprüfung nimmt keine eigene Grenze an (sie hat verify_timeout)",
          _step.verify_condition.timeout is None)
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)

_web = studio_web_source()
check("der Inspektor hat das Feld unter dem Farb-Trigger",
      'field("Timeout (s)", b.trigger_timeout' in _web
      and "call(\"block_trigger\", {choice: b.trigger, timeout:" in _web)
check("„Ohne ELSE“ rechnet mit der Grenze des Blocks",
      "withoutElseText(b.trigger_timeout)" in _web)
