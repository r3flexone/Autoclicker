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


# ---------------------------------------------------------------------------
section("Nachklicken: der Zeiger steht auf der Stelle, bevor man klickt")

# **Warum das der Kern der Runde ist**: steht der Zeiger schon dort, wo der Punkt
# gespeichert ist, kostet ein Punkt, der noch stimmt, genau einen Klick — und nur
# die verrutschten eine Mausbewegung. Ohne den Sprung stand die alte Stelle nur
# als Zahlenpaar in der Konsole, und man musste sie auf dem Schirm suchen.
import autoclicker.editors.nachklick as _nk

_gesprungen = []
_echt_springe = _nk._springe
_nk._springe = lambda x, y, verzoegert=False: _gesprungen.append((x, y, verzoegert))
try:
    _s2 = _ST()
    _s2.points = [_punkt(1, 100, 100), _punkt(2, 222, 333), _punkt(3, 300, 300)]
    _s2.active_sequence = _SEQ(name="Zeiger", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=2), _STEP(point_id=3)])])
    _ruesten(_s2)

    _gesprungen.clear()
    _nk._zeige_aktuellen(_s2)
    check("der erste Punkt wird angefahren", _gesprungen == [(100, 100, False)])

    # Der Fall, um den es geht: NACH einem echten Klick muss der Zeiger auf den
    # naechsten Punkt springen. Genau das tat er vorher nicht.
    _gesprungen.clear()
    _klick(_s2, 111, 112, None)
    check("nach einem Klick steht der Zeiger auf dem NÄCHSTEN Punkt",
          [(x, y) for x, y, _v in _gesprungen] == [(222, 333)])
    # **Und zwar erst nach kurzer Frist.** Der Hook meldet den DRUCK; sofort zu
    # springen zoege die Maus zwischen Druck und Loslassen weg und machte aus
    # dem Klick ein Ziehen.
    check("und zwar verzögert, damit aus dem Klick kein Ziehen wird",
          _gesprungen[0][2] is True)

    # Überspringen und Zurück sind keine Klicks — dort darf er sofort springen.
    _gesprungen.clear()
    _skip(_s2)
    check("beim Überspringen springt er sofort",
          _gesprungen and _gesprungen[0][2] is False)
    _gesprungen.clear()
    _zurueck(_s2)
    check("beim Zurückgehen ebenso",
          _gesprungen and _gesprungen[0][2] is False)
    _stop(_s2, "Test")
finally:
    _nk._springe = _echt_springe

# Die Frist selbst: ohne sie waere die Trennung oben eine Behauptung.
check("die Sprung-Frist ist gesetzt und kurz",
      0 < _nk.SPRUNG_VERZOEGERUNG <= 1.0)
_gesetzt = []
_echt_cursor = _nk.set_cursor_pos
_nk.set_cursor_pos = lambda x, y: _gesetzt.append((x, y))
try:
    _nk._springe(5, 6)
    check("ohne Frist setzt _springe den Zeiger direkt", _gesetzt == [(5, 6)])
finally:
    _nk.set_cursor_pos = _echt_cursor


# ---------------------------------------------------------------------------
section("Nachklicken: es läuft nichts von selbst")

# **Der Fehler, den das hier festhält**: der Maus-Hook kann die Klicks des
# Workers nicht von Handgriffen unterscheiden. Lief eine Sequenz mit, verbrauchte
# sie die Punkte der Runde selbst und schrieb ihre eigenen Ziele hinein — von
# aussen sah es aus, als sei die Sequenz „von allein weitergelaufen".
_s3 = _ST()
_s3.points = [_punkt(1, 100, 100), _punkt(2, 200, 200)]
_s3.active_sequence = _SEQ(name="Ruhig", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=1), _STEP(point_id=2)])])
_ruesten(_s3)
_s3.is_running = True
_klick(_s3, 999, 888, None)
check("während eines Laufs setzt ein Klick keinen Punkt",
      (_s3.points[0].x, _s3.points[0].y) == (100, 100))
check("und die Runde rückt nicht vor", _s3.nachklick_index == 0)
_s3.is_running = False
_klick(_s3, 999, 888, None)
check("ohne Lauf setzt derselbe Klick wieder",
      (_s3.points[0].x, _s3.points[0].y) == (999, 888))
_stop(_s3, "Test")

# Die zweite Tür ist die wichtigere: gar nicht erst starten lassen. Gemessen wird
# am WORKER und nicht an `is_running` — der Worker setzt es beim Ende selbst
# zurück, ein gestarteter Lauf wäre also je nach Zeitpunkt unsichtbar.
import autoclicker.handlers as _hd

_gestartet = []
_echt_worker = _hd.sequence_worker
_hd.sequence_worker = lambda *a, **k: _gestartet.append(a)
try:
    _s4 = _ST()
    _s4.points = [_punkt(1, 10, 10)]
    _s4.active_sequence = _SEQ(name="Ruhig", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1)])])
    _ruesten(_s4)
    _hd.handle_toggle(_s4)
    check("ein Start während der Runde startet keinen Worker", _gestartet == [])
    _stop(_s4, "Test")

    # Gegenprobe: ohne laufende Runde startet derselbe Griff sehr wohl.
    _hd.handle_toggle(_s4)
    _s4.stop_event.set()
    check("ohne Runde startet er", len(_gestartet) == 1)
finally:
    _hd.sequence_worker = _echt_worker
    _s4.is_running = False

# Umgekehrt: ein gestellter Countdown ist ein Start mit Verzoegerung und wuerde
# mitten in die Runde feuern. Deshalb faengt sie gar nicht erst an.
_s5 = _ST()
_s5.points = [_punkt(1, 10, 10)]
_s5.active_sequence = _SEQ(name="Ruhig", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=1)])])
_s5.countdown_active = True
check("mit gestelltem Countdown startet keine Runde", _ruesten(_s5) is None)
