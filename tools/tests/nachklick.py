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


def _aktiv(state, seq, punkte, zielfenster=""):
    """Bindet den sequenz-eigenen Pool zugleich als Laufzeit-Arbeitsansicht."""
    seq.points = punkte
    state.active_sequence = seq
    state.points = seq.points
    state.config.window_focus_title = zielfenster


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
    _punkte_s = [_punkt(1, 100, 100, (10, 20, 30)), _punkt(2, 200, 200),
                 _punkt(3, 300, 300)]
    _schritt = _STEP(point_id=2, delay_before=7.5,
                     wait_condition=_WAIT(point_id=2, color=(1, 2, 3)),
                     else_config=_ELSE(action="skip"))
    _aktiv(_s, _SEQ(name="Klein", init_steps=[_STEP(point_id=1)],
                    loop_phases=[_PHASE(name="A", steps=[_schritt,
                                                         _STEP(point_id=3)])]),
           _punkte_s)
    _erg = _ruesten(_s)
    check("die Runde lässt sich rüsten", _erg is not None)
    check("und kennt ihre drei Punkte", _s.nachklick_punkte == [1, 2, 3])
    check("sie fängt beim ersten an", _s.nachklick_index == 0)

    # --- Ein Klick merkt die neue Stelle, schreibt sie aber noch nicht ---
    _klick(_s, 150, 160, (44, 55, 66))
    check("der Klick merkt die neue Stelle",
          _s.nachklick_gesetzt[0][:3] == (1, (100, 100), (150, 160)))
    # **Der Punkt bleibt bis zum Schluss unangetastet.** Sonst waere ein Abbruch
    # eine halb ueberschriebene points.json - und genau so sind in einer echten
    # Runde drei Fehlklicks dauerhaft in den Punkten gelandet.
    check("der Punkt selbst ist noch unverändert",
          (_s.points[0].x, _s.points[0].y) == (100, 100))
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
    check("zurück wirft die eben erfasste Stelle weg",
          [e[0] for e in _s.nachklick_gesetzt] == [1])
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

    # Der letzte Punkt beendet die Runde von selbst — und JETZT wird geschrieben.
    check("die Runde endet mit dem letzten Punkt", _s.nachklick_aktiv is False)
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
# Die folgenden Abschnitte übernehmen Punkte und speichern dabei absichtlich.
# Sie dürfen deshalb nie im echten Datenordner des Benutzers laufen.
_sand_mittel = tempfile.mkdtemp(prefix="nachklick_laufzeit_")
_cwd_mittel = _os.getcwd()
_os.chdir(_sand_mittel)
Path("sequences").mkdir()

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
    _aktiv(_s2, _SEQ(name="Zeiger", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=2), _STEP(point_id=3)])]),
           [_punkt(1, 100, 100), _punkt(2, 222, 333), _punkt(3, 300, 300)])
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
_aktiv(_s3, _SEQ(name="Ruhig", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=1), _STEP(point_id=2)])]),
       [_punkt(1, 100, 100), _punkt(2, 200, 200)])
_ruesten(_s3)
_s3.is_running = True
_klick(_s3, 999, 888, None)
check("während eines Laufs setzt ein Klick keinen Punkt",
      (_s3.points[0].x, _s3.points[0].y) == (100, 100))
check("und die Runde rückt nicht vor", _s3.nachklick_index == 0)
_s3.is_running = False
_klick(_s3, 999, 888, None)
check("ohne Lauf zählt derselbe Klick wieder",
      [e[2] for e in _s3.nachklick_gesetzt] == [(999, 888)])
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
    _aktiv(_s4, _SEQ(name="Ruhig", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1)])]), [_punkt(1, 10, 10)])
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
_aktiv(_s5, _SEQ(name="Ruhig", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=1)])]), [_punkt(1, 10, 10)])
_s5.countdown_active = True
check("mit gestelltem Countdown startet keine Runde", _ruesten(_s5) is None)


# ---------------------------------------------------------------------------
section("Nachklicken: nur Klicks im Zielfenster zählen")

# **Der Fehler, den das hier festhält.** Der Maus-Hook ist systemweit: ohne
# Filter zählt jeder Klick — auch der auf das Studio-Fenster, die Konsole oder
# ein Schliessen-Kreuz. In einer echten Runde sind so drei Punkte auf
# Fensterdekoration gewandert (einer auf (3030, 16), also die Titelleiste), und
# beim Beenden wurde es gespeichert.
_vordergrund = ["Idle Clans"]
_echt_aktiv = _nk.is_target_window_active
_echt_titel = _nk.get_foreground_window_title
_echt_rect = _nk.get_client_rect_by_title
_nk.is_target_window_active = lambda t: t.lower() in _vordergrund[0].lower()
_nk.get_foreground_window_title = lambda: _vordergrund[0]
_nk.get_client_rect_by_title = lambda t: (0, 0, 800, 600)
try:
    _s6 = _ST()
    _aktiv(_s6, _SEQ(name="Fokus", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=2)])]),
           [_punkt(1, 100, 100), _punkt(2, 200, 200)], "Idle Clans")
    _ruesten(_s6)
    check("das Zielfenster steht in der Runde", _s6.nachklick_ziel == "Idle Clans")

    _vordergrund[0] = "Sequenz-Studio"
    _klick(_s6, 3030, 16, None)
    check("ein Klick in einem fremden Fenster setzt nichts",
          (_s6.points[0].x, _s6.points[0].y) == (100, 100))
    check("und verbraucht den Punkt nicht", _s6.nachklick_index == 0)

    _vordergrund[0] = "Idle Clans"
    _klick(_s6, 640, 480, None)
    check("im Zielfenster zählt derselbe Klick",
          [e[2] for e in _s6.nachklick_gesetzt] == [(640, 480)])
    _stop(_s6, "Test")

    # Ohne auffindbares Fenster wird NICHT gefiltert: ein Filter, der alles
    # wegwirft, sieht aus wie ein kaputter Hook.
    _nk.get_client_rect_by_title = lambda t: None
    _s7 = _ST()
    _aktiv(_s7, _SEQ(name="Ohne", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1)])]), [_punkt(1, 100, 100)], "Gibt Es Nicht")
    _ruesten(_s7)
    check("ohne auffindbares Fenster wird nicht gefiltert", _s7.nachklick_ziel == "")
    _vordergrund[0] = "Irgendwas"
    _klick(_s7, 55, 66, None)
    # Der einzige Punkt beendet die Runde, also ist er danach schon geschrieben.
    check("und jeder Klick zählt", (_s7.points[0].x, _s7.points[0].y) == (55, 66))
finally:
    _nk.is_target_window_active = _echt_aktiv
    _nk.get_foreground_window_title = _echt_titel
    _nk.get_client_rect_by_title = _echt_rect


# ---------------------------------------------------------------------------
section("Nachklicken: ein Pixel Abweichung ist keine Korrektur")

# Der Zeiger wird von uns auf die Stelle gesetzt — und trotzdem kommt der Klick
# gelegentlich einen Pixel daneben zurück (DPI-Skalierung, ein Hauch Bewegung).
# Ohne Toleranz schriebe jede Bestätigung den Punkt um einen Pixel um und zählte
# als Änderung: Rauschen in genau der Liste, die sagen soll, was sich geändert hat.
_s8 = _ST()
_aktiv(_s8, _SEQ(name="Pixel", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=1), _STEP(point_id=2)])]),
       [_punkt(1, 6233, 412, (33, 140, 116)), _punkt(2, 200, 200)])
_ruesten(_s8)
_klick(_s8, 6233, 411, (200, 10, 10))
check("ein Pixel daneben zählt als bestätigt, nicht als Änderung",
      _s8.nachklick_gesetzt == [])
check("die Stelle bleibt exakt stehen",
      (_s8.points[0].x, _s8.points[0].y) == (6233, 412))
check("und die Farbe wird nicht überschrieben",
      _s8.points[0].color == (33, 140, 116))
check("die Toleranz ist winzig — eine gewollte Korrektur ist nie so klein",
      _nk.PASST_TOLERANZ <= 2)
# Gegenprobe: eine echte Korrektur geht durch.
_klick(_s8, 900, 950, None)
check("eine echte Korrektur wird erfasst und am Ende geschrieben",
      (_s8.points[1].x, _s8.points[1].y) == (900, 950))
_stop(_s8, "Test")

_os.chdir(_cwd_mittel)


# ---------------------------------------------------------------------------
section("Nachklicken: geschrieben wird erst am Schluss — und nur auf Übernehmen")

# **Der Fehler, den das hier festhält.** Jeder Ausgang schrieb: das Beenden des
# Programms, das geschlossene Studio-Fenster, alles. In einer echten Runde
# landeten so drei Klicks auf Fensterdekoration dauerhaft in points.json — es
# gab keinen Weg mehr zurück, weil der Punkt im Speicher schon umgeschrieben war.
_sand2 = tempfile.mkdtemp(prefix="nachklick_verwerfen_")
_os.chdir(_sand2)
try:
    Path("sequences").mkdir()
    _s9 = _ST()
    _aktiv(_s9, _SEQ(name="Weg", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=2)])]),
           [_punkt(1, 100, 100, (1, 2, 3)), _punkt(2, 200, 200)])
    _ruesten(_s9)
    _klick(_s9, 3030, 16, (99, 99, 99))       # Titelleiste erwischt
    check("die Stelle ist erfasst", len(_s9.nachklick_gesetzt) == 1)
    _stop(_s9, "Fenster zu", uebernehmen=False)
    check("verworfen lässt den Punkt in Ruhe",
          (_s9.points[0].x, _s9.points[0].y) == (100, 100))
    check("und die Farbe auch", _s9.points[0].color == (1, 2, 3))
    check("und schreibt nichts auf Platte",
          not Path("sequences/weg/sequence.json").exists())

    # Gegenprobe: dieselbe Runde, uebernommen.
    _ruesten(_s9)
    _klick(_s9, 640, 480, (99, 99, 99))
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
_aktiv(_s10, _SEQ(name="Quit", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=1), _STEP(point_id=2)])]),
       [_punkt(1, 100, 100), _punkt(2, 200, 200)])
_ruesten(_s10)
_klick(_s10, 4444, 55, None)          # etwas gesetzt, aber nicht übernommen
_hd.handle_quit(_s10, 0)
check("das Beenden des Programms verwirft die Runde", _s10.nachklick_aktiv is False)
check("und lässt die Punkte stehen", (_s10.points[0].x, _s10.points[0].y) == (100, 100))

# Und der Weg des geschlossenen Fensters: verwerfen=1 im Briefkasten-Befehl.
from autoclicker.handlers import befehl_nachklick_stop as _bns

_s11 = _ST()
_aktiv(_s11, _SEQ(name="Studio", loop_phases=[_PHASE(name="A", steps=[
    _STEP(point_id=1), _STEP(point_id=2)])]),
       [_punkt(1, 100, 100), _punkt(2, 200, 200)])
_ruesten(_s11)
_klick(_s11, 700, 700, None)
_bns(_s11, {"verwerfen": "1"})
check("der Studio-Abbruch verwirft", (_s11.points[0].x, _s11.points[0].y) == (100, 100))
check("und beendet die Runde", _s11.nachklick_aktiv is False)


# ---------------------------------------------------------------------------
section("Nachklicken: Konsole und Studio nennen dieselben Tasten")

# Zwei Listen derselben Griffe sind zwei Stellen, an denen eine Änderung
# vergessen wird — und die Runde wird an beiden Orten nachgeschlagen.
import re as _re_nk
_appjs = (Path(_nk.__file__).resolve().parent
          / "sequence_studio" / "web" / "app.js").read_text(encoding="utf-8")
_js_block = _appjs[_appjs.index("const WZ_TASTEN"):_appjs.index("const WZ_SCHRITTE")]
_js_tasten = _re_nk.findall(r'\["(CTRL\+ALT\+\w)",\s*"([^"]+)"', _js_block)
check("das Studio nennt dieselben vier Tasten in derselben Reihenfolge",
      _js_tasten == [(t_[0], t_[1]) for t_ in _nk.TASTEN])
check("und CTRL+ALT+J ist das Übernehmen",
      _nk.TASTEN[-1][0] == "CTRL+ALT+J" and "übernehm" in _nk.TASTEN[-1][1])


# ---------------------------------------------------------------------------
section("Nachklicken: das Studio sieht, was die Runde gerade macht")

# Die Runde laeuft im HAUPTPROZESS (dort haengt der Maus-Hook), bedient wird sie
# oft aus dem Studio. Ohne den Rueckkanal stand dort nur "gestartet", waehrend
# die Konsole jeden Schritt einzeln meldete — und genau waehrend des Klickens
# will man wissen, welcher Punkt dran ist.
import json as _json_nk

_sand_st = tempfile.mkdtemp(prefix="nachklick_status_")
_cwd_st = _os.getcwd()
_os.chdir(_sand_st)
try:
    Path("sequences").mkdir()
    _s12 = _ST()
    _aktiv(_s12, _SEQ(name="Sicht", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=2), _STEP(point_id=3)])]),
           [_punkt(1, 100, 100, (10, 20, 30)), _punkt(2, 200, 200),
            _punkt(3, 300, 300)])
    _ruesten(_s12)

    def _stand():
        with open(_nk.NACHKLICK_STATUS_FILE if hasattr(_nk, "NACHKLICK_STATUS_FILE")
                  else ".nachklick.json", "r", encoding="utf-8") as f:
            return _json_nk.load(f)

    _st0 = _stand()
    check("das Ruesten schreibt sofort einen Stand", _st0["aktiv"] is True)
    check("mit Gesamtzahl und Startindex",
          _st0["gesamt"] == 3 and _st0["index"] == 0)
    check("und dem Punkt, der als Naechstes dran ist",
          _st0["punkt"]["id"] == 1 and _st0["punkt"]["x"] == 100)
    check("die Farbe kommt mit, wenn der Punkt eine hat",
          _st0["punkt"]["farbe"] == [10, 20, 30])

    # --- Ein Klick weit daneben ist "gesetzt", einer daneben-daneben "passt" ---
    _klick(_s12, 150, 160, (44, 55, 66))
    _st1 = _stand()
    check("nach dem Klick steht der naechste Punkt da", _st1["punkt"]["id"] == 2)
    check("und der erledigte im Verlauf",
          [v["art"] for v in _st1["verlauf"]] == ["gesetzt"])
    check("mit alter und neuer Stelle",
          _st1["verlauf"][0]["alt"] == [100, 100]
          and _st1["verlauf"][0]["neu"] == [150, 160])

    # **Das ist der Grund fuer `nachklick_verlauf`**: ein bestaetigter Punkt
    # (innerhalb PASST_TOLERANZ) landet bewusst NICHT in `nachklick_gesetzt`.
    # Ableiten liesse sich "passt" also nicht — im Fenster saehe er genauso aus
    # wie ein uebersprungener, und das ist die eine Auskunft, die zaehlt.
    _klick(_s12, 200, 200, None)
    _st2 = _stand()
    check("ein bestaetigter Punkt heisst 'passt', nicht 'uebersprungen'",
          [v["art"] for v in _st2["verlauf"]] == ["gesetzt", "passt"])
    check("und zaehlt trotzdem nicht als Aenderung", _st2["geaendert"] == 1)

    _skip(_s12)
    _st3 = _stand()
    check("ein uebersprungener steht als solcher im Verlauf",
          [v["art"] for v in _st3["verlauf"]]
          == ["gesetzt", "passt", "uebersprungen"])

    # Der dritte Punkt WAR der letzte — die Runde endet damit von selbst, und
    # der Abschluss traegt den vollstaendigen Verlauf. Wuerde er erst nach dem
    # Leeren geschrieben, staende hier eine leere Runde: ausgerechnet in dem
    # Moment, in dem man nachsieht, was sie ergeben hat.
    check("die abgeschlossene Runde bleibt lesbar", _st3["aktiv"] is False)
    check("und sagt, wie viele Stellen sich geaendert haben",
          _st3["geaendert"] == 1)
    check("und warum sie zu Ende ist", "alle Punkte durch" in _st3.get("grund", ""))
    check("der Verlauf ueberlebt das Ende vollstaendig", len(_st3["verlauf"]) == 3)
    check("waehrend der State selbst geraeumt ist",
          _s12.nachklick_verlauf == [] and _s12.nachklick_aktiv is False)
finally:
    _os.chdir(_cwd_st)
    shutil.rmtree(_sand_st, ignore_errors=True)


# Zurueck heisst zurueck — auch in der Anzeige. Bliebe der Verlaufseintrag
# stehen, zeigte das Fenster einen Punkt als erledigt, den die Runde gleich
# noch einmal abfragt.
_sand_zk = tempfile.mkdtemp(prefix="nachklick_zurueck_")
_cwd_zk = _os.getcwd()
_os.chdir(_sand_zk)
try:
    Path("sequences").mkdir()
    _s13 = _ST()
    _aktiv(_s13, _SEQ(name="Zurueck", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=2)])]),
           [_punkt(1, 100, 100), _punkt(2, 200, 200)])
    _ruesten(_s13)
    _klick(_s13, 400, 400, None)
    check("ein Eintrag steht im Verlauf", len(_s13.nachklick_verlauf) == 1)
    _zurueck(_s13)
    check("zurueck nimmt ihn wieder heraus", _s13.nachklick_verlauf == [])
    check("und die Runde steht wieder auf dem ersten Punkt",
          _s13.nachklick_index == 0)
finally:
    _os.chdir(_cwd_zk)
    shutil.rmtree(_sand_zk, ignore_errors=True)
