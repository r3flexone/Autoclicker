"""Punkte nachklicken: die Sequenz einmal von Hand spielen, nur die Stellen ändern.

**Warum es das neben `walk` gibt** — und warum genau das hier geprüft wird: `walk`
setzt Punkte, ohne zu klicken, und scheitert deshalb an jedem Punkt, der erst
nach einem anderen sichtbar wird. Die Klick-Runde klickt wirklich, das Spiel geht
dabei auf, und der nächste Punkt liegt vor einem.

Gemessen wird alles ausser dem Maus-Hook: was geklickt werden kann, in welcher
Reihenfolge, was eine Runde NICHT erreicht — und vor allem, dass sie die
Sequenz nicht anfasst.
"""
import os as _os
import tempfile
from pathlib import Path

from ._harness import check, section
from autoclicker.editors.nachklick import (
    klickpunkte as _klickpunkte,
    nachklick_pause as _pause,
    nachklick_ueberspringen as _skip,
    nachklick_zurueck as _zurueck,
    ruesten as _ruesten,
    stop_nachklick as _stop,
    _setze_punkt as _klick,
)
from autoclicker.models import (
    AutoClickerState as _ST,
    ClickPoint as _CP,
    ElseConfig as _ELSE,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
    WaitCondition as _WAIT,
)


def _punkt(pid, x, y, farbe=None, name=""):
    return _CP(id=pid, x=x, y=y, name=name or f"P{pid}", color=farbe)


# ---------------------------------------------------------------------------
section("Nachklicken: welche Punkte, in welcher Reihenfolge")

# **Die Reihenfolge ist die des Laufs.** Genau in ihr öffnet ein Klick die
# Stelle für den nächsten — das ist der ganze Grund, warum die Runde etwas kann,
# was `walk` nicht kann.
_seq = _SEQ(
    name="Farm",
    init_steps=[_STEP(point_id=1)],
    loop_phases=[
        _PHASE(name="A", steps=[
            _STEP(point_id=2, wait_condition=_WAIT(point_id=2)),
            _STEP(key_press="enter"),                       # Taste: keine Stelle
            _STEP(point_id=3, delay_before=5.0),
            _STEP(point_id=2),                              # derselbe Punkt nochmal
        ]),
        _PHASE(name="B", steps=[
            _STEP(point_id=4, wait_only=True),              # beobachtet, klickt nicht
            _STEP(point_id=5, else_config=_ELSE(action="click", point_id=6)),
            _STEP(point_id=7, scroll=-3),                   # Rad, kein Klick
            _STEP(item_scan="Inventar"),
        ]),
    ],
    end_steps=[_STEP(point_id=8, verify_condition=_WAIT(point_id=9))],
)
_klicks, _sonstige = _klickpunkte(_seq)
check("die Klick-Punkte stehen in der Reihenfolge des Laufs",
      _klicks == [1, 2, 3, 5, 8])
check("ein Punkt kommt nur EINMAL vor, auch wenn zweimal geklickt",
      _klicks.count(2) == 1)
check("ein Wait-only-Schritt klickt nicht", 4 not in _klicks)
check("ein Rad-Schritt auch nicht", 7 not in _klicks)
# **Was eine Runde nicht erreicht, wird gesagt.** Es zu verschweigen wäre die
# schlimmere Hälfte: man hielte die Sequenz für repariert.
check("beobachtete Stellen stehen als unerreichbar da", 4 in _sonstige)
check("ELSE-Klicks ebenso", 6 in _sonstige)
check("Nachprüfungen ebenso", 9 in _sonstige)
check("und der Rad-Schritt", 7 in _sonstige)
check("eine Stelle steht in genau einer der beiden Listen",
      not (set(_klicks) & set(_sonstige)))
# Der Trigger-Punkt eines Farb-Trigger-Klicks IST der Klickpunkt — er darf nicht
# zusätzlich als unerreichbar gelten, sonst zählte die Meldung ihn doppelt.
check("der Trigger am eigenen Klick zählt nicht als unerreichbar",
      2 not in _sonstige)

# **Wer beides ist, ist ein Klick.** Eine Stelle, die ein frueher Schritt nur
# BEOBACHTET und ein spaeterer klickt, landete in einem Durchgang unter
# „unerreichbar" — und war damit aus der Runde draussen, obwohl man sie gleich
# anklicken wird.
_spaet = _SEQ(name="Spaet", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=10, wait_only=True, wait_condition=_WAIT(point_id=11)),
    _STEP(point_id=11),
])])
_k2, _s2 = _klickpunkte(_spaet)
check("erst beobachtet, dann geklickt = klickbar", _k2 == [11])
check("und nicht zusätzlich als unerreichbar", 11 not in _s2)
check("das nur Beobachtete bleibt unerreichbar", 10 in _s2)


# ---------------------------------------------------------------------------
section("Nachklicken: die Runde setzt Stellen — und sonst nichts")

_sand = tempfile.mkdtemp(prefix="nachklick_")
_cwd = _os.getcwd()
_os.chdir(_sand)
try:
    Path("sequences").mkdir()
    _s = _ST()
    _s.points = [_punkt(1, 100, 100, (10, 20, 30)), _punkt(2, 200, 200),
                 _punkt(3, 300, 300)]
    _schritt = _STEP(point_id=2, delay_before=7.5,
                     wait_condition=_WAIT(point_id=2, color=(1, 2, 3)),
                     else_config=_ELSE(action="skip"))
    _s.active_sequence = _SEQ(name="Klein",
                              init_steps=[_STEP(point_id=1)],
                              loop_phases=[_PHASE(name="A", steps=[_schritt,
                                                                   _STEP(point_id=3)])])
    _erg = _ruesten(_s)
    check("die Runde lässt sich rüsten", _erg is not None)
    check("und kennt ihre drei Punkte", _s.nachklick_punkte == [1, 2, 3])
    check("sie fängt beim ersten an", _s.nachklick_index == 0)

    # --- Ein Klick setzt den aktuellen Punkt ---
    _klick(_s, 150, 160, (44, 55, 66))
    check("der Klick setzt die neue Stelle", (_s.points[0].x, _s.points[0].y) == (150, 160))
    # Die Farbe gehört zur Position — aber nur, wenn der Punkt vorher eine hatte.
    # Sonst schliche sich ein Farb-Trigger ein, den niemand gesetzt hat.
    check("und zieht die Farbe mit, weil der Punkt eine hatte",
          _s.points[0].color == (44, 55, 66))
    check("die Runde ist beim zweiten Punkt", _s.nachklick_index == 1)

    _klick(_s, 250, 260, (77, 88, 99))
    check("ein Punkt ohne Farbe bekommt keine", _s.points[1].color is None)

    # **Der Kern: die Sequenz wird nicht angefasst.**
    check("die Wartezeit des Schritts ist unverändert", _schritt.delay_before == 7.5)
    check("die Farb-Bedingung auch",
          _schritt.wait_condition.point_id == 2
          and _schritt.wait_condition.color == (1, 2, 3))
    check("und das ELSE", _schritt.else_config.action == "skip")

    # --- Zurück holt die alte Stelle zurück ---
    # Nur den Zeiger zurückzusetzen liesse die eben geschriebene Koordinate
    # stehen; wer sich verklickt hat, merkte es erst beim nächsten Lauf.
    _zurueck(_s)
    check("zurück stellt die alte Stelle wieder her",
          (_s.points[1].x, _s.points[1].y) == (200, 200))
    check("und steht wieder auf diesem Punkt", _s.nachklick_index == 1)

    # --- Überspringen lässt den Punkt, wo er ist ---
    _skip(_s)
    check("überspringen ändert nichts an der Stelle",
          (_s.points[1].x, _s.points[1].y) == (200, 200))
    check("geht aber weiter", _s.nachklick_index == 2)

    # --- Pause: Klicks gehen durch, ohne zu setzen ---
    _pause(_s)
    _klick(_s, 999, 999, None)
    check("pausiert setzt ein Klick keinen Punkt",
          (_s.points[2].x, _s.points[2].y) == (300, 300))
    _pause(_s)
    _klick(_s, 350, 360, None)
    check("nach der Pause wieder", (_s.points[2].x, _s.points[2].y) == (350, 360))

    # Der letzte Punkt beendet die Runde von selbst.
    check("die Runde endet mit dem letzten Punkt", _s.nachklick_aktiv is False)
    check("und schreibt die Punkte auf Platte",
          Path("sequences/points.json").exists())

    # --- Ein zweiter Lauf: derselbe Klick zweimal ist keine Änderung ---
    _s.nachklick_gesetzt = []
    _ruesten(_s)
    _klick(_s, 150, 160, (44, 55, 66))
    check("ein Klick auf dieselbe Stelle zählt nicht als Änderung",
          _s.nachklick_gesetzt == [])
    _stop(_s, "Test")
    check("beenden räumt die Runde ab",
          _s.nachklick_aktiv is False and _s.nachklick_punkte == [])
finally:
    _os.chdir(_cwd)
