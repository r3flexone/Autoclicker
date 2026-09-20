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
import shutil
import tempfile
from pathlib import Path

from ._harness import check, section
from autoclicker.editors.reclick import (
    click_points as _klickpunkte,
    reclick_pause as _pause,
    reclick_skip as _skip,
    reclick_back as _returned,
    prepare_reclick as _ruesten,
    stop_reclick as _stop,
    _set_point as _click,
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


def _point(pid, x, y, color=None, name=""):
    return _CP(id=pid, x=x, y=y, name=name or f"P{pid}", color=color)


def _active(state, seq, points, target_window=""):
    """Bindet den sequenz-eigenen Pool zugleich als Laufzeit-Arbeitsansicht."""
    seq.points = points
    state.active_sequence = seq
    state.points = seq.points
    state.config.window_focus_title = target_window


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
            _STEP(item_scan="Inventar"),
        ]),
    ],
    end_steps=[_STEP(point_id=8, verify_condition=_WAIT(point_id=9))],
)
_clicks, _others = _klickpunkte(_seq)
check("die Klick-Punkte stehen in der Reihenfolge des Laufs",
      _clicks == [1, 2, 3, 5, 8])
check("ein Punkt kommt nur EINMAL vor, auch wenn zweimal geklickt",
      _clicks.count(2) == 1)
check("ein Wait-only-Schritt klickt nicht", 4 not in _clicks)
# **Was eine Runde nicht erreicht, wird gesagt.** Es zu verschweigen wäre die
# schlimmere Hälfte: man hielte die Sequenz für repariert.
check("beobachtete Stellen stehen als unerreichbar da", 4 in _others)
check("ELSE-Klicks ebenso", 6 in _others)
check("Nachprüfungen ebenso", 9 in _others)
check("eine Stelle steht in genau einer der beiden Listen",
      not (set(_clicks) & set(_others)))
# Der Trigger-Punkt eines Farb-Trigger-Klicks IST der Klickpunkt — er darf nicht
# zusätzlich als unerreichbar gelten, sonst zählte die Meldung ihn doppelt.
check("der Trigger am eigenen Klick zählt nicht als unerreichbar",
      2 not in _others)

# **Wer beides ist, ist ein Klick.** Eine Stelle, die ein frueher Schritt nur
# BEOBACHTET und ein spaeterer klickt, landete in einem Durchgang unter
# „unerreichbar" — und war damit aus der Runde draussen, obwohl man sie gleich
# anklicken wird.
_late = _SEQ(name="Spaet", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=10, wait_only=True, wait_condition=_WAIT(point_id=11)),
    _STEP(point_id=11),
])])
_k2, _s2 = _klickpunkte(_late)
check("erst beobachtet, dann geklickt = klickbar", _k2 == [11])
check("und nicht zusätzlich als unerreichbar", 11 not in _s2)
check("das nur Beobachtete bleibt unerreichbar", 10 in _s2)


# ---------------------------------------------------------------------------
section("Nachklicken: die Runde setzt Stellen — und sonst nichts")

_sandbox = tempfile.mkdtemp(prefix="nachklick_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    Path("sequences").mkdir()
    _s = _ST()
    _points_s = [_point(1, 100, 100, (10, 20, 30)), _point(2, 200, 200),
                 _point(3, 300, 300)]
    _step_local = _STEP(point_id=2, delay_before=7.5,
                     wait_condition=_WAIT(point_id=2, color=(1, 2, 3)),
                     else_config=_ELSE(action="skip"))
    _active(_s, _SEQ(name="Klein", init_steps=[_STEP(point_id=1)],
                    loop_phases=[_PHASE(name="A", steps=[_step_local,
                                                         _STEP(point_id=3)])]),
           _points_s)
    _res = _ruesten(_s)
    check("die Runde lässt sich rüsten", _res is not None)
    check("und kennt ihre drei Punkte", _s.reclick_points == [1, 2, 3])
    check("sie fängt beim ersten an", _s.reclick_index == 0)

    # --- Ein Klick merkt die neue Stelle, schreibt sie aber noch nicht ---
    _click(_s, 150, 160, (44, 55, 66))
    check("der Klick merkt die neue Stelle",
          _s.reclick_set[0][:3] == (1, (100, 100), (150, 160)))
    # **Der Punkt bleibt bis zum Schluss unangetastet.** Sonst waere ein Abbruch
    # eine halb ueberschriebene points.json - und genau so sind in einer echten
    # Runde drei Fehlklicks dauerhaft in den Punkten gelandet.
    check("der Punkt selbst ist noch unverändert",
          (_s.points[0].x, _s.points[0].y) == (100, 100))
    check("die Runde ist beim zweiten Punkt", _s.reclick_index == 1)

    _click(_s, 250, 260, (77, 88, 99))
    check("ein Punkt ohne Farbe bekommt keine", _s.points[1].color is None)

    # **Der Kern: die Sequenz wird nicht angefasst.**
    check("die Wartezeit des Schritts ist unverändert", _step_local.delay_before == 7.5)
    check("die Farb-Bedingung auch",
          _step_local.wait_condition.point_id == 2
          and _step_local.wait_condition.color == (1, 2, 3))
    check("und das ELSE", _step_local.else_config.action == "skip")

    # --- Zurück holt die alte Stelle zurück ---
    # Nur den Zeiger zurückzusetzen liesse die eben geschriebene Koordinate
    # stehen; wer sich verklickt hat, merkte es erst beim nächsten Lauf.
    _returned(_s)
    check("zurück wirft die eben erfasste Stelle weg",
          [e[0] for e in _s.reclick_set] == [1])
    check("und steht wieder auf diesem Punkt", _s.reclick_index == 1)

    # --- Überspringen lässt den Punkt, wo er ist ---
    _skip(_s)
    check("überspringen ändert nichts an der Stelle",
          (_s.points[1].x, _s.points[1].y) == (200, 200))
    check("geht aber weiter", _s.reclick_index == 2)

    # --- Pause: Klicks gehen durch, ohne zu setzen ---
    _pause(_s)
    _click(_s, 999, 999, None)
    check("pausiert setzt ein Klick keinen Punkt",
          (_s.points[2].x, _s.points[2].y) == (300, 300))
    _pause(_s)
    _click(_s, 350, 360, None)
    check("nach der Pause wieder", (_s.points[2].x, _s.points[2].y) == (350, 360))

    # Der letzte Punkt beendet die Runde von selbst — und JETZT wird geschrieben.
    check("die Runde endet mit dem letzten Punkt", _s.reclick_active is False)
    check("erst dabei wandert die Stelle in den Punkt",
          (_s.points[0].x, _s.points[0].y) == (150, 160))
    # Die Farbe gehört zur Position — aber nur, wenn der Punkt vorher eine hatte.
    # Sonst schliche sich ein Farb-Trigger ein, den niemand gesetzt hat.
    check("und die Farbe mit, weil der Punkt eine hatte",
          _s.points[0].color == (44, 55, 66))
    check("ein Punkt ohne Farbe bekommt auch am Ende keine",
          _s.points[1].color is None)
    check("und schreibt die Punkte auf Platte",
          Path("sequences/klein/sequence.json").exists())

    # --- Ein zweiter Lauf: derselbe Klick zweimal ist keine Änderung ---
    _s.reclick_set = []
    _ruesten(_s)
    _click(_s, 150, 160, (44, 55, 66))
    check("ein Klick auf dieselbe Stelle zählt nicht als Änderung",
          _s.reclick_set == [])
    _stop(_s, "Test")
    check("beenden räumt die Runde ab",
          _s.reclick_active is False and _s.reclick_points == [])
finally:
    _os.chdir(_cwd)


# ---------------------------------------------------------------------------
# Die folgenden Abschnitte übernehmen Punkte und speichern dabei absichtlich.
# Sie dürfen deshalb nie im echten Datenordner des Benutzers laufen.
_sandbox_middle = tempfile.mkdtemp(prefix="nachklick_laufzeit_")
_cwd_middle = _os.getcwd()
_os.chdir(_sandbox_middle)
Path("sequences").mkdir()

section("Nachklicken: der Zeiger steht auf der Stelle, bevor man klickt")

# **Warum das der Kern der Runde ist**: steht der Zeiger schon dort, wo der Punkt
# gespeichert ist, kostet ein Punkt, der noch stimmt, genau einen Klick — und nur
# die verrutschten eine Mausbewegung. Ohne den Sprung stand die alte Stelle nur
# als Zahlenpaar in der Konsole, und man musste sie auf dem Schirm suchen.
import autoclicker.editors.reclick as _nk

_jumped = []
_real_jump = _nk._jump
_nk._jump = lambda x, y, delayed=False: _jumped.append((x, y, delayed))
try:
    _s2 = _ST()
    _active(_s2, _SEQ(name="Zeiger", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=2), _STEP(point_id=3)])]),
           [_point(1, 100, 100), _point(2, 222, 333), _point(3, 300, 300)])
    _ruesten(_s2)

    _jumped.clear()
    _nk._show_current(_s2)
    check("der erste Punkt wird angefahren", _jumped == [(100, 100, False)])

    # Der Fall, um den es geht: NACH einem echten Klick muss der Zeiger auf den
    # naechsten Punkt springen. Genau das tat er vorher nicht.
    _jumped.clear()
    _click(_s2, 111, 112, None)
    check("nach einem Klick steht der Zeiger auf dem NÄCHSTEN Punkt",
          [(x, y) for x, y, _v in _jumped] == [(222, 333)])
    # **Und zwar erst nach kurzer Frist.** Der Hook meldet den DRUCK; sofort zu
    # springen zoege die Maus zwischen Druck und Loslassen weg und machte aus
    # dem Klick ein Ziehen.
    check("und zwar verzögert, damit aus dem Klick kein Ziehen wird",
          _jumped[0][2] is True)

    # Überspringen und Zurück sind keine Klicks — dort darf er sofort springen.
    _jumped.clear()
    _skip(_s2)
    check("beim Überspringen springt er sofort",
          _jumped and _jumped[0][2] is False)
    _jumped.clear()
    _returned(_s2)
    check("beim Zurückgehen ebenso",
          _jumped and _jumped[0][2] is False)
    _stop(_s2, "Test")
finally:
    _nk._jump = _real_jump

# Die Frist selbst: ohne sie waere die Trennung oben eine Behauptung.
check("die Sprung-Frist ist gesetzt und kurz",
      0 < _nk.JUMP_DELAY <= 1.0)
_set_ones = []
_real_cursor = _nk.set_cursor_pos
_nk.set_cursor_pos = lambda x, y: _set_ones.append((x, y))
try:
    _nk._jump(5, 6)
    check("ohne Frist setzt _jump den Zeiger direkt", _set_ones == [(5, 6)])
finally:
    _nk.set_cursor_pos = _real_cursor


# ---------------------------------------------------------------------------
section("Nachklicken: es läuft nichts von selbst")

# **Der Fehler, den das hier festhält**: der Maus-Hook kann die Klicks des
# Workers nicht von Handgriffen unterscheiden. Lief eine Sequenz mit, verbrauchte
# sie die Punkte der Runde selbst und schrieb ihre eigenen Ziele hinein — von
# aussen sah es aus, als sei die Sequenz „von allein weitergelaufen".
_s3 = _ST()
_active(_s3, _SEQ(name="Ruhig", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=1), _STEP(point_id=2)])]),
       [_point(1, 100, 100), _point(2, 200, 200)])
_ruesten(_s3)
_s3.is_running = True
_click(_s3, 999, 888, None)
check("während eines Laufs setzt ein Klick keinen Punkt",
      (_s3.points[0].x, _s3.points[0].y) == (100, 100))
check("und die Runde rückt nicht vor", _s3.reclick_index == 0)
_s3.is_running = False
_click(_s3, 999, 888, None)
check("ohne Lauf zählt derselbe Klick wieder",
      [e[2] for e in _s3.reclick_set] == [(999, 888)])
_stop(_s3, "Test")

# Die zweite Tür ist die wichtigere: gar nicht erst starten lassen. Gemessen wird
# am WORKER und nicht an `is_running` — der Worker setzt es beim Ende selbst
# zurück, ein gestarteter Lauf wäre also je nach Zeitpunkt unsichtbar.
import autoclicker.handlers as _hd

_started = []
_real_worker = _hd.sequence_worker
_hd.sequence_worker = lambda *a, **k: _started.append(a)
try:
    _s4 = _ST()
    _active(_s4, _SEQ(name="Ruhig", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1)])]), [_point(1, 10, 10)])
    _ruesten(_s4)
    _hd.handle_toggle(_s4)
    check("ein Start während der Runde startet keinen Worker", _started == [])
    _stop(_s4, "Test")

    # Gegenprobe: ohne laufende Runde startet derselbe Griff sehr wohl.
    _hd.handle_toggle(_s4)
    _s4.stop_event.set()
    check("ohne Runde startet er", len(_started) == 1)
finally:
    _hd.sequence_worker = _real_worker
    _s4.is_running = False

# Umgekehrt: ein gestellter Countdown ist ein Start mit Verzoegerung und wuerde
# mitten in die Runde feuern. Deshalb faengt sie gar nicht erst an.
_s5 = _ST()
_active(_s5, _SEQ(name="Ruhig", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=1)])]), [_point(1, 10, 10)])
_s5.countdown_active = True
check("mit gestelltem Countdown startet keine Runde", _ruesten(_s5) is None)


# ---------------------------------------------------------------------------
section("Nachklicken: nur Klicks im Zielfenster zählen")

# **Der Fehler, den das hier festhält.** Der Maus-Hook ist systemweit: ohne
# Filter zählt jeder Klick — auch der auf das Studio-Fenster, die Konsole oder
# ein Schliessen-Kreuz. In einer echten Runde sind so drei Punkte auf
# Fensterdekoration gewandert (einer auf (3030, 16), also die Titelleiste), und
# beim Beenden wurde es gespeichert.
# **Gefragt wird, in WELCHES Fenster geklickt wurde — nicht, welches vorn ist.**
# Windows liefert den Button-Down an das Fenster unter dem Zeiger; war das nicht
# das aktive, wird es durch genau diesen Klick erst aktiv. Im Hook steht damit
# noch das VORIGE Fenster im Vordergrund, und ein Klick, der ein anderes Fenster
# nach vorn holt, zaehlte als Klick ins Ziel. Genau so ist in einer echten Runde
# ein Punkt auf eine Stelle im Studio-Fenster gewandert (Farbe #1C2333, dessen
# eigenes Panel-Grau) — unmittelbar nachdem derselbe Filter den Klick davor
# korrekt abgewiesen hatte.
_foreground = ["Idle Clans"]
_clicked = [None]          # None = dieselbe Antwort wie der Vordergrund
# Die Frage „welches Fenster hat den Klick" beantwortet `_click_window` —
# fuer die Runde UND die Aufnahme. Gestubbt wird deshalb dort.
import autoclicker.editors._click_window as _kf
_real_title = _kf.get_foreground_window_title
_real_under = _kf.get_window_title_at
_real_rect = _nk.get_client_rect_by_title
_kf.get_foreground_window_title = lambda: _foreground[0]
_kf.get_window_title_at = lambda x, y: (
    _foreground[0] if _clicked[0] is None else _clicked[0])
_nk.get_client_rect_by_title = lambda t: (0, 0, 800, 600)
try:
    _s6 = _ST()
    _active(_s6, _SEQ(name="Fokus", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=2)])]),
           [_point(1, 100, 100), _point(2, 200, 200)], "Idle Clans")
    _ruesten(_s6)
    check("das Zielfenster steht in der Runde", _s6.reclick_target == "Idle Clans")

    _foreground[0] = "Sequenz-Studio"
    _click(_s6, 3030, 16, None)
    check("ein Klick in einem fremden Fenster setzt nichts",
          (_s6.points[0].x, _s6.points[0].y) == (100, 100))
    check("und verbraucht den Punkt nicht", _s6.reclick_index == 0)

    _foreground[0] = "Idle Clans"
    _click(_s6, 640, 480, None)
    check("im Zielfenster zählt derselbe Klick",
          [e[2] for e in _s6.reclick_set] == [(640, 480)])

    # Der Fall, der in der echten Runde durchgerutscht ist: das Spiel ist noch
    # VORN, geklickt wird aber ins Studio — der Klick holt es gerade erst nach
    # vorn. Wer den Vordergrund fragt, bekommt „Idle Clans" und setzt den Punkt
    # auf eine Stelle im Studio.
    _clicked[0] = "Sequenz-Studio"
    _before = list(_s6.reclick_set)
    _index_before = _s6.reclick_index
    _click(_s6, 757, 634, None)
    check("ein Klick, der ein fremdes Fenster erst nach vorn holt, zählt nicht",
          list(_s6.reclick_set) == _before)
    check("und verbraucht auch dann den Punkt nicht",
          _s6.reclick_index == _index_before)

    # Umgekehrt: das Studio ist vorn, geklickt wird ins Spiel. Der Klick gilt.
    # Mit diesem zweiten Punkt ist die Runde durch und schreibt sofort — die
    # Liste der offenen Stellen ist danach leer, geprüft wird also der Punkt.
    _foreground[0] = "Sequenz-Studio"
    _clicked[0] = "Idle Clans"
    _click(_s6, 321, 123, None)
    check("ein Klick, der das Spiel erst nach vorn holt, zählt",
          (_s6.points[1].x, _s6.points[1].y) == (321, 123))
    _clicked[0] = None

    # Ohne auffindbares Fenster wird NICHT gefiltert: ein Filter, der alles
    # wegwirft, sieht aus wie ein kaputter Hook.
    _nk.get_client_rect_by_title = lambda t: None
    _s7 = _ST()
    _active(_s7, _SEQ(name="Ohne", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1)])]), [_point(1, 100, 100)], "Gibt Es Nicht")
    _ruesten(_s7)
    check("ohne auffindbares Fenster wird nicht gefiltert", _s7.reclick_target == "")
    _foreground[0] = "Irgendwas"
    _click(_s7, 55, 66, None)
    # Der einzige Punkt beendet die Runde, also ist er danach schon geschrieben.
    check("und jeder Klick zählt", (_s7.points[0].x, _s7.points[0].y) == (55, 66))
finally:
    _kf.get_foreground_window_title = _real_title
    _kf.get_window_title_at = _real_under
    _nk.get_client_rect_by_title = _real_rect


# ---------------------------------------------------------------------------
section("Nachklicken: ein Pixel Abweichung ist keine Korrektur")

# Der Zeiger wird von uns auf die Stelle gesetzt — und trotzdem kommt der Klick
# gelegentlich einen Pixel daneben zurück (DPI-Skalierung, ein Hauch Bewegung).
# Ohne Toleranz schriebe jede Bestätigung den Punkt um einen Pixel um und zählte
# als Änderung: Rauschen in genau der Liste, die sagen soll, was sich geändert hat.
_s8 = _ST()
_active(_s8, _SEQ(name="Pixel", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=1), _STEP(point_id=2)])]),
       [_point(1, 6233, 412, (33, 140, 116)), _point(2, 200, 200)])
_ruesten(_s8)
_click(_s8, 6233, 411, (200, 10, 10))
check("ein Pixel daneben zählt als bestätigt, nicht als Änderung",
      _s8.reclick_set == [])
check("die Stelle bleibt exakt stehen",
      (_s8.points[0].x, _s8.points[0].y) == (6233, 412))
check("und die Farbe wird nicht überschrieben",
      _s8.points[0].color == (33, 140, 116))
check("die Toleranz ist winzig — eine gewollte Korrektur ist nie so klein",
      _nk.MATCH_TOLERANCE <= 2)
# Gegenprobe: eine echte Korrektur geht durch.
_click(_s8, 900, 950, None)
check("eine echte Korrektur wird erfasst und am Ende geschrieben",
      (_s8.points[1].x, _s8.points[1].y) == (900, 950))
_stop(_s8, "Test")

_os.chdir(_cwd_middle)


# ---------------------------------------------------------------------------
section("Nachklicken: geschrieben wird erst am Schluss — und nur auf Übernehmen")

# **Der Fehler, den das hier festhält.** Jeder Ausgang schrieb: das Beenden des
# Programms, das geschlossene Studio-Fenster, alles. In einer echten Runde
# landeten so drei Klicks auf Fensterdekoration dauerhaft in points.json — es
# gab keinen Weg mehr zurück, weil der Punkt im Speicher schon umgeschrieben war.
_sandbox2 = tempfile.mkdtemp(prefix="nachklick_verwerfen_")
_os.chdir(_sandbox2)
try:
    Path("sequences").mkdir()
    _s9 = _ST()
    _active(_s9, _SEQ(name="Weg", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=2)])]),
           [_point(1, 100, 100, (1, 2, 3)), _point(2, 200, 200)])
    _ruesten(_s9)
    _click(_s9, 3030, 16, (99, 99, 99))       # Titelleiste erwischt
    check("die Stelle ist erfasst", len(_s9.reclick_set) == 1)
    _stop(_s9, "Fenster zu", apply_config=False)
    check("verworfen lässt den Punkt in Ruhe",
          (_s9.points[0].x, _s9.points[0].y) == (100, 100))
    check("und die Farbe auch", _s9.points[0].color == (1, 2, 3))
    check("und schreibt nichts auf Platte",
          not Path("sequences/weg/sequence.json").exists())

    # Gegenprobe: dieselbe Runde, uebernommen.
    _ruesten(_s9)
    _click(_s9, 640, 480, (99, 99, 99))
    _stop(_s9, "übernommen")
    check("übernommen wandert die Stelle in den Punkt",
          (_s9.points[0].x, _s9.points[0].y) == (640, 480))
    check("und JETZT steht sie auf Platte",
          Path("sequences/weg/sequence.json").exists())
finally:
    _os.chdir(_cwd)

# Das Beenden des Programms ist kein Übernehmen — sonst schriebe genau der
# Ausgang, den man nimmt, wenn etwas schiefgelaufen ist.
_s10 = _ST()
_active(_s10, _SEQ(name="Quit", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=1), _STEP(point_id=2)])]),
       [_point(1, 100, 100), _point(2, 200, 200)])
_ruesten(_s10)
_click(_s10, 4444, 55, None)          # etwas gesetzt, aber nicht übernommen
_hd.handle_quit(_s10, 0)
check("das Beenden des Programms verwirft die Runde", _s10.reclick_active is False)
check("und lässt die Punkte stehen", (_s10.points[0].x, _s10.points[0].y) == (100, 100))

# Und der Weg des geschlossenen Fensters: verwerfen=1 im Briefkasten-Befehl.
from autoclicker.handlers import command_reclick_stop as _bns

_s11 = _ST()
_active(_s11, _SEQ(name="Studio", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=1), _STEP(point_id=2)])]),
       [_point(1, 100, 100), _point(2, 200, 200)])
_ruesten(_s11)
_click(_s11, 700, 700, None)
_bns(_s11, {"discard": "1", "reason": "window"})
check("der Studio-Abbruch verwirft", (_s11.points[0].x, _s11.points[0].y) == (100, 100))
check("und beendet die Runde", _s11.reclick_active is False)

# **Die Meldung sagt, was passiert ist.** Sie lautete fuer JEDES Verwerfen
# „Studio geschlossen — Runde verworfen" — auch beim Druck auf „Verwerfen" im
# offenen Fenster. Wer das liest und weiss, dass er nichts geschlossen hat,
# sucht den Fehler an der falschen Stelle: es sieht aus, als haette sich die
# Runde von selbst beendet.
import io as _io_nk
import contextlib as _cl_nk


def _discard_text(reason):
    st = _ST()
    _active(st, _SEQ(name="Grund", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=2)])]),
           [_point(1, 10, 10), _point(2, 20, 20)])
    _ruesten(st)
    buffer = _io_nk.StringIO()
    with _cl_nk.redirect_stdout(buffer):
        _bns(st, dict({"discard": "1"}, **({"reason": reason} if reason else {})))
    return buffer.getvalue()


_txt_button = _discard_text("button")
_txt_window = _discard_text("window")
check("der Verwerfen-Knopf behauptet kein geschlossenes Fenster",
      "geschlossen" not in _txt_button and "verworfen" in _txt_button.lower())
check("das geschlossene Fenster sagt genau das",
      "Studio geschlossen" in _txt_window)
check("ohne Grund gilt der Knopf, nicht das Fenster",
      "geschlossen" not in _discard_text(None))


# ---------------------------------------------------------------------------
section("Nachklicken: Konsole und Studio nennen dieselben Tasten")

# Zwei Listen derselben Griffe sind zwei Stellen, an denen eine Änderung
# vergessen wird — und die Runde wird an beiden Orten nachgeschlagen.
import re as _re_nk
_appjs = (Path(_nk.__file__).resolve().parent
          / "sequence_studio" / "web" / "app.js").read_text(encoding="utf-8")
_js_block = _appjs[_appjs.index("const WZ_KEYS"):_appjs.index("const WZ_STEPS")]
_js_keys = _re_nk.findall(r'\["(CTRL\+ALT\+\w)",\s*"([^"]+)"', _js_block)
check("das Studio nennt dieselben vier Tasten in derselben Reihenfolge",
      _js_keys == [(t_[0], t_[1]) for t_ in _nk.KEYS])
check("und CTRL+ALT+J ist das Übernehmen",
      _nk.KEYS[-1][0] == "CTRL+ALT+J" and "übernehm" in _nk.KEYS[-1][1])


# ---------------------------------------------------------------------------
section("Nachklicken: das Studio sieht, was die Runde gerade macht")

# Die Runde laeuft im HAUPTPROZESS (dort haengt der Maus-Hook), bedient wird sie
# oft aus dem Studio. Ohne den Rueckkanal stand dort nur "gestartet", waehrend
# die Konsole jeden Schritt einzeln meldete — und genau waehrend des Klickens
# will man wissen, welcher Punkt dran ist.
import json as _json_nk

_sandbox_st = tempfile.mkdtemp(prefix="nachklick_status_")
_cwd_st = _os.getcwd()
_os.chdir(_sandbox_st)
try:
    Path("sequences").mkdir()
    _s12 = _ST()
    _active(_s12, _SEQ(name="Sicht", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=2), _STEP(point_id=3)])]),
           [_point(1, 100, 100, (10, 20, 30)), _point(2, 200, 200),
            _point(3, 300, 300)])
    _ruesten(_s12)

    def _state():
        with open(_nk.RECLICK_STATUS_FILE if hasattr(_nk, "RECLICK_STATUS_FILE")
                  else ".reclick.json", "r", encoding="utf-8") as f:
            return _json_nk.load(f)

    _st0 = _state()
    check("das Ruesten schreibt sofort einen Stand", _st0["active"] is True)
    check("mit Gesamtzahl und Startindex",
          _st0["total"] == 3 and _st0["index"] == 0)
    check("und dem Punkt, der als Naechstes dran ist",
          _st0["point"]["id"] == 1 and _st0["point"]["x"] == 100)
    check("die Farbe kommt mit, wenn der Punkt eine hat",
          _st0["point"]["color"] == [10, 20, 30])

    # --- Ein Klick weit daneben ist "gesetzt", einer daneben-daneben "passt" ---
    _click(_s12, 150, 160, (44, 55, 66))
    _st1 = _state()
    check("nach dem Klick steht der naechste Punkt da", _st1["point"]["id"] == 2)
    check("und der erledigte im Verlauf",
          [v["kind"] for v in _st1["history"]] == ["placed"])
    check("mit alter und neuer Stelle",
          _st1["history"][0]["old"] == [100, 100]
          and _st1["history"][0]["new"] == [150, 160])

    # **Das ist der Grund fuer `reclick_history`**: ein bestaetigter Punkt
    # (innerhalb MATCH_TOLERANCE) landet bewusst NICHT in `reclick_set`.
    # Ableiten liesse sich "passt" also nicht — im Fenster saehe er genauso aus
    # wie ein uebersprungener, und das ist die eine Auskunft, die zaehlt.
    _click(_s12, 200, 200, None)
    _st2 = _state()
    check("ein bestaetigter Punkt heisst 'passt', nicht 'uebersprungen'",
          [v["kind"] for v in _st2["history"]] == ["placed", "fits"])
    check("und zaehlt trotzdem nicht als Aenderung", _st2["changed"] == 1)

    _skip(_s12)
    _st3 = _state()
    check("ein uebersprungener steht als solcher im Verlauf",
          [v["kind"] for v in _st3["history"]]
          == ["placed", "fits", "skipped"])

    # Der dritte Punkt WAR der letzte — die Runde endet damit von selbst, und
    # der Abschluss traegt den vollstaendigen Verlauf. Wuerde er erst nach dem
    # Leeren geschrieben, staende hier eine leere Runde: ausgerechnet in dem
    # Moment, in dem man nachsieht, was sie ergeben hat.
    check("die abgeschlossene Runde bleibt lesbar", _st3["active"] is False)
    check("und sagt, wie viele Stellen sich geaendert haben",
          _st3["changed"] == 1)
    check("und warum sie zu Ende ist", "alle Punkte durch" in _st3.get("reason", ""))
    check("der Verlauf ueberlebt das Ende vollstaendig", len(_st3["history"]) == 3)
    check("waehrend der State selbst geraeumt ist",
          _s12.reclick_history == [] and _s12.reclick_active is False)
finally:
    _os.chdir(_cwd_st)
    shutil.rmtree(_sandbox_st, ignore_errors=True)


# Zurueck heisst zurueck — auch in der Anzeige. Bliebe der Verlaufseintrag
# stehen, zeigte das Fenster einen Punkt als erledigt, den die Runde gleich
# noch einmal abfragt.
_sandbox_zk = tempfile.mkdtemp(prefix="nachklick_zurueck_")
_cwd_zk = _os.getcwd()
_os.chdir(_sandbox_zk)
try:
    Path("sequences").mkdir()
    _s13 = _ST()
    _active(_s13, _SEQ(name="Zurueck", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=2)])]),
           [_point(1, 100, 100), _point(2, 200, 200)])
    _ruesten(_s13)
    _click(_s13, 400, 400, None)
    check("ein Eintrag steht im Verlauf", len(_s13.reclick_history) == 1)
    _returned(_s13)
    check("zurueck nimmt ihn wieder heraus", _s13.reclick_history == [])
    check("und die Runde steht wieder auf dem ersten Punkt",
          _s13.reclick_index == 0)
finally:
    _os.chdir(_cwd_zk)
    shutil.rmtree(_sandbox_zk, ignore_errors=True)


# ---------------------------------------------------------------------------
section("Nachklicken: ein gescheitertes Speichern heisst nicht „gespeichert“")

# `save_sequence_file` meldet seinen Fehler selbst — aber darunter stand
# trotzdem „N Punkt(e) neu gesetzt und gespeichert", und `.reclick.json` sagte
# dem Studio `applied: True` ueber einer Datei, die nie geschrieben wurde. Im
# Speicher sind die Punkte dann gesetzt, auf der Platte nicht: der naechste
# Start klickt daneben, und niemand hat es gesagt.
import json as _json_sv
import io as _io_sv
import contextlib as _cl_sv
import autoclicker.persistence.sequences as _pseq

_sandbox_sv = tempfile.mkdtemp(prefix="nachklick_speichern_")
_cwd_sv = _os.getcwd()
_os.chdir(_sandbox_sv)
try:
    Path("sequences").mkdir()

    def _round(save_ok: bool):
        st = _ST()
        _active(st, _SEQ(name="Platte", loop_phases=[_PHASE(name="A", steps=[
            _STEP(point_id=1), _STEP(point_id=2)])]),
               [_point(1, 100, 100), _point(2, 200, 200)])
        _ruesten(st)
        _click(st, 640, 480, None)
        old_write = _pseq.atomic_write
        if not save_ok:
            def _broken(*a, **k):
                raise OSError("Platte voll")
            _pseq.atomic_write = _broken
        buffer = _io_sv.StringIO()
        try:
            with _cl_sv.redirect_stdout(buffer):
                _stop(st, "übernommen")
        finally:
            _pseq.atomic_write = old_write
        with open(_nk.RECLICK_STATUS_FILE, "r", encoding="utf-8") as f:
            status = _json_sv.load(f)
        return buffer.getvalue(), status

    _txt_ok, _st_ok = _round(True)
    check("geglueckt: die Meldung sagt gespeichert", "gespeichert." in _txt_ok)
    check("und der Stand fuer das Studio sagt applied",
          _st_ok["active"] is False and _st_ok["applied"] is True)

    _txt_bad, _st_bad = _round(False)
    check("gescheitert: die Meldung sagt NICHT gespeichert",
          "NICHT gespeichert" in _txt_bad and "und gespeichert." not in _txt_bad)
    check("und nennt den Weg, es nachzuholen", "CTRL+ALT+E" in _txt_bad)
    check("der Stand fuer das Studio sagt applied: False",
          _st_bad["active"] is False and _st_bad["applied"] is False)
finally:
    _os.chdir(_cwd_sv)
