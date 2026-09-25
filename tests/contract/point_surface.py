"""Aufnahme: derselbe Knopf bekommt denselben Punkt — auch bei Klicks von Hand.

Gemessen an einer echten Einfüge-Aufnahme ("Ab hier aufnehmen"): 18 Klicks
auf DREI Knöpfe ergaben 7 neue Punkte, und die Blöcke für denselben Knopf
zeigten auf fünf verschiedene (P8, P48, P49, P50, P53). Die Klicks auf einen
breiten Knopf streuten 55 px, der Punkt-Radius ist 8 px — und wer einmal einen
zweiten Punkt auf dem Knopf hatte, sprang danach je nach Zufall zwischen den
beiden hin und her. Im Studio sah das aus wie „es sortiert komisch".

Den Radius hochzudrehen war keine Antwort: in derselben Sequenz liegen zwei
gleichfarbige Ziele 20 px übereinander. Was „derselbe Knopf" heisst, sagt die
zusammenhängende Farbfläche um den Klick (`imaging.click_surface`), und
innerhalb eines Durchgangs gewinnt der Punkt, den er für diese Fläche schon
vergeben hat (`prefer`).

Das Bild ist hier ein Nachbau mit `size`/`convert`/`tobytes` — so läuft der
Test auch ohne Pillow, und geprüft wird die Rechnung, nicht die Bibliothek.
"""
import contextlib as _cl
import io as _io
import os as _os
import shutil as _sh
import tempfile as _tmp

from ._harness import check, section
from autoclicker.config import CONFIG as _CFG
from autoclicker.imaging import click_surface as _surface, SURFACE_RADIUS as _RADIUS
from autoclicker.models import (
    AutoClickerState as _ST,
    ClickPoint as _CP,
    LoopPhase as _PHASE,
    RecordEvent as _RE,
    REC_CLICK as _R_CLICK,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
from autoclicker.persistence import (
    load_sequence_file, save_sequence_file, sequence_file,
)
from autoclicker.persistence.sequences import point_at_position as _at
import autoclicker.editors.sequence_recorder as _rec


class _Scene:
    """Ein Bild aus Rechtecken — genau das, was `click_surface` davon liest."""

    def __init__(self, width, height, background):
        self.size = (width, height)
        self._px = [background] * (width * height)

    def fill(self, x1, y1, x2, y2, color):
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                self._px[y * self.size[0] + x] = color
        return self

    def convert(self, _mode):
        return self

    def tobytes(self):
        return bytes(v for p in self._px for v in p)


_TEAL, _TEAL2, _GRAY, _WHITE = (33, 140, 116), (32, 135, 111), (40, 40, 40), (250, 250, 250)
_LEFT, _TOP = 1000, 500
# Knopf A oben (120 px breit, Beschriftung darin), 3 px Rand, Knopf D direkt
# darunter in fast derselben Farbe, Knopf E daneben in derselben Zeile.
_scene = (_Scene(200, 100, _GRAY)
          .fill(10, 10, 129, 29, _TEAL)
          .fill(60, 16, 74, 23, _WHITE)
          .fill(10, 33, 129, 52, _TEAL2)
          .fill(150, 10, 190, 29, _TEAL))
_patch = (_LEFT, _TOP, _scene)


def _click(t, x, y, color, patch=_patch):
    return _RE(_R_CLICK, float(t), _LEFT + x, _TOP + y, color, patch=patch)


_old_radius, _old_tol = _CFG.punkt_radius, _CFG.punkt_farbtoleranz
_CFG.punkt_radius, _CFG.punkt_farbtoleranz = 8, 10
try:
    # =========================================================================
    section("Die Fläche um einen Klick: ein Knopf, nicht sein Nachbar")
    # =========================================================================
    _a = _surface(_patch, _LEFT + 15, _TOP + 20, _TEAL, 10)
    check("die Fläche reicht über den ganzen Knopf — auch 110 px weit",
          _a is not None and (_LEFT + 125, _TOP + 12) in _a)
    check("um die Beschriftung herum, aber nicht in sie hinein",
          (_LEFT + 80, _TOP + 20) in _a and (_LEFT + 65, _TOP + 20) not in _a)
    check("der gleichfarbige Knopf darunter gehört NICHT dazu (3 px Rand dazwischen)",
          (_LEFT + 50, _TOP + 40) not in _a)
    check("der gleichfarbige Knopf daneben auch nicht", (_LEFT + 170, _TOP + 20) not in _a)
    check("die Koordinaten sind Bildschirm-Koordinaten, nicht Bild-Koordinaten",
          (15, 20) not in _a)
    check("ohne Bild gibt es keine Fläche", _surface(None, 1, 1, _TEAL, 10) is None)
    check("liegt der Klick auf anderer Farbe als gemeldet, auch nicht",
          _surface(_patch, _LEFT + 15, _TOP + 20, _WHITE, 10) is None)
    check("der Ausschnitt im Hook reicht für die gemessene Streuung (55 px)",
          _RADIUS >= 55)

    # =========================================================================
    section("point_at_position: Fläche ODER Radius, Farbe immer")
    # =========================================================================
    _p8 = _CP(_LEFT + 100, _TOP + 20, "P8", 8, color=_TEAL)
    check("85 px entfernt, aber auf derselben Fläche: derselbe Punkt",
          _at([_p8], _LEFT + 15, _TOP + 20, _TEAL, surface=_a) is _p8)
    check("ohne Fläche bleibt es beim Radius — dann ein neuer",
          _at([_p8], _LEFT + 15, _TOP + 20, _TEAL) is None)
    check("Radius 0 heisst weiter „nur exakt“ — auch mit Fläche",
          _at([_p8], _LEFT + 15, _TOP + 20, _TEAL, radius=0, surface=_a) is None)
    _p8_red = _CP(_LEFT + 100, _TOP + 20, "rot", 8, color=(200, 30, 30))
    check("eine andere Farbe am Punkt trennt trotz Fläche",
          _at([_p8_red], _LEFT + 15, _TOP + 20, _TEAL, surface=_a) is None)
    # Zwei alte Punkte auf demselben Knopf: der Durchgang bleibt bei dem, den
    # er schon vergeben hat — sonst trugen die Blöcke abwechselnd zwei Namen.
    _p20 = _CP(_LEFT + 20, _TOP + 20, "P20", 20, color=_TEAL)
    check("ohne Vorgabe gewinnt der nächste",
          _at([_p8, _p20], _LEFT + 98, _TOP + 20, _TEAL, surface=_a) is _p8)
    check("mit Vorgabe der schon vergebene — auch wenn ein anderer näher liegt",
          _at([_p8, _p20], _LEFT + 98, _TOP + 20, _TEAL, surface=_a, prefer=[20]) is _p20)

    # =========================================================================
    section("points_for_events: drei Knöpfe, drei Punkte")
    # =========================================================================
    _p9 = _CP(_LEFT + 50, _TOP + 43, "P9", 9, color=_TEAL2)
    _events = [
        _click(0, 15, 18, _TEAL),          # A links
        _click(1, 125, 22, _TEAL),         # A rechts, 110 px weiter
        _click(2, 80, 12, _TEAL2),         # A oben, leicht andere Farbe (Hover)
        _click(3, 100, 44, _TEAL2),        # D — 24 px unter P8, gleiche Farbe
        _click(4, 160, 20, _TEAL),         # E — neu
        _click(5, 185, 15, _TEAL),         # E wieder, 25 px daneben
    ]
    _ids, _new = _rec.points_for_events(_events, existing=[_p8, _p9])
    check("alle Klicks auf A landen auf dem vorhandenen P8",
          [_ids[i] for i in (0, 1, 2)] == [8, 8, 8])
    check("der Knopf darunter behält SEINEN Punkt — obwohl P8 nur 24 px entfernt ist",
          _ids[3] == 9)
    check("der neue Knopf bekommt genau EINEN neuen Punkt",
          len(_new) == 1 and _ids[4] == _ids[5] == _new[0].id)

    # Der echte Bestand hatte schon zwei Punkte auf Knopf B (P17, P43); je
    # nachdem, welcher näher lag, bekam ein Block den einen oder den anderen.
    _ids_p, _ = _rec.points_for_events([_click(0, 25, 20, _TEAL), _click(1, 98, 20, _TEAL)],
                                       existing=[_p8, _p20])
    check("liegen schon zwei alte Punkte auf dem Knopf, bleibt die Aufnahme bei EINEM",
          _ids_p[0] == _ids_p[1] == 20)

    # Gegenprobe: dieselben Klicks ohne Bild — das alte Verhalten, und genau
    # der Zustand aus der echten Aufnahme.
    _blind = [_click(e.t, e.x - _LEFT, e.y - _TOP, e.color, patch=None) for e in _events]
    _ids_b, _new_b = _rec.points_for_events(_blind, existing=[_p8, _p9])
    check("ohne Bild entstehen für dieselben Klicks mehrere Punkte je Knopf",
          len(_new_b) >= 4 and len({_ids_b[i] for i in (0, 1, 2)}) > 1)

    # =========================================================================
    section("Der Hook nimmt den Ausschnitt auf — und nur, wenn aufgezeichnet wird")
    # =========================================================================
    _sandbox = _tmp.mkdtemp(prefix="punkt_flaeche_")
    _cwd = _os.getcwd()
    _os.chdir(_sandbox)
    _orig_capture, _orig_window = _rec.capture_surface, _rec.clicked_window
    _captured = []
    _rec.capture_surface = lambda x, y: _captured.append((x, y)) or _patch
    _rec.clicked_window = lambda x, y: "Idle Clans"
    try:
        _st = _ST()
        _st.recording_active = True
        _on_click = _rec._on_click_factory(_st)
        with _cl.redirect_stdout(_io.StringIO()):
            _on_click(1015, 518, _TEAL)
        check("der Klick trägt seinen Ausschnitt",
              len(_st.recording_events) == 1 and _st.recording_events[0].patch is _patch)
        _st.recording_paused = True
        with _cl.redirect_stdout(_io.StringIO()):
            _on_click(1020, 518, _TEAL)
        check("pausiert wird gar nicht erst aufgenommen", _captured == [(1015, 518)])

        # =====================================================================
        section("Einfüge-Aufnahme: der echte Fall bis auf die Platte")
        # =====================================================================
        _seq = _SEQ("ziel", total_cycles=1,
                    loop_phases=[_PHASE("L1", steps=[_STEP(point_id=8), _STEP(point_id=9)])],
                    points=[_CP(_p8.x, _p8.y, "P8", 8, color=_TEAL),
                            _CP(_p9.x, _p9.y, "P9", 9, color=_TEAL2)])
        _path = sequence_file(_seq.name)
        _path.parent.mkdir(parents=True, exist_ok=True)
        save_sequence_file(_seq, _path)
        _target = {"file": str(_path), "phase": "loop", "phase_index": 0, "block": 0}
        # Sechsmal dasselbe Muster wie in der echten Aufnahme: A, E, D.
        _pattern = [(15, 18, _TEAL), (170, 20, _TEAL), (40, 45, _TEAL2)]
        _many = [_click(i, x + (i // 3) * 3, y, c)
                 for i, (x, y, c) in enumerate(_pattern * 6)]
        _buf = _io.StringIO()
        with _cl.redirect_stdout(_buf):
            _rec._finish_insert_recording(_ST(), _many, _target)
        _loaded = load_sequence_file(_path)
        _inserted = _loaded.loop_phases[0].steps[1:-1]
        check("18 Blöcke eingefügt", len(_inserted) == 18)
        check("sie zeigen auf genau drei Punkte — einen je Knopf",
              len({s.point_id for s in _inserted}) == 3)
        check("A und D behalten ihre alten Punkte, nur E ist neu",
              {_inserted[0].point_id, _inserted[2].point_id} == {8, 9}
              and len(_loaded.points) == 3)
        check("die Meldung nennt den einen neuen Punkt", "1 neue(r) Punkt(e)" in _buf.getvalue())
    finally:
        _rec.capture_surface, _rec.clicked_window = _orig_capture, _orig_window
        _os.chdir(_cwd)
        _sh.rmtree(_sandbox, ignore_errors=True)
finally:
    _CFG.punkt_radius, _CFG.punkt_farbtoleranz = _old_radius, _old_tol
