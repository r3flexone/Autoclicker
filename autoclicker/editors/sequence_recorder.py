"""Sequenz-Aufnahme: Zeichnet echtes Spielen auf und baut daraus eine Sequenz.

Start/Stop über CTRL+ALT+J. Aufgezeichnet werden Linksklicks (Position,
Zeitstempel, Pixelfarbe), Tastendrücke, das Mausrad und die Marker (siehe
CLAUDE.md). Alles muss mit EINEM globalen Tastendruck gehen — während der
Aufnahme steht der Nutzer im Spiel, nicht in der Konsole.
"""

import re
import time
from datetime import datetime
from pathlib import Path

from ..models import (
    AutoClickerState, Sequence, LoopPhase, SequenceStep, ClickPoint, WaitCondition,
    RecordEvent, REC_CLICK, REC_KEY, REC_SCROLL, REC_WAIT_COLOR, REC_SCREENSHOT,
    REC_REGION, REC_WATCH, REC_PHASE,
)
from ..winapi import (
    install_mouse_hook, remove_mouse_hook, install_keyboard_hook, remove_keyboard_hook,
    get_cursor_pos, WHEEL_DELTA,
)
from ._klickfenster import geklicktes_fenster
from ..imaging import get_pixel_color
from ..config import RECORD_STATUS_FILE
from ..utils import (
    safe_input, col, ok, err, warn, is_cancel, hint, describe_color,
    atomic_write, compact_json,
)
from ..persistence.sequences import (
    save_sequence_file, ensure_sequences_dir,
    resolve_point_references, sequence_file,
)


# Klicks die schneller als dieser Abstand (Sekunden) aufeinander folgen sind
# fast immer versehentliche Doppel-/Zitterklicks — beim Stoppen wird darauf
# hingewiesen (nicht automatisch gelöscht, um echte Doppelklicks zu erhalten).
_FAST_CLICK_GAP = 0.08

# Mausrad-Ereignisse innerhalb dieses Abstands (Sekunden) gehören zu EINER Drehung
# und werden zu einem Schritt zusammengefasst. Ohne das würde ein einziges Drehen
# um fünf Rasten zu fünf Schritten — das Rad feuert pro Raste ein eigenes Ereignis.
_SCROLL_MERGE_GAP = 0.25
_AUFNAHME_STATUS = Path(RECORD_STATUS_FILE)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Dieselben Griffe zeigt das Studio im Werkzeug „Sequenz aufnehmen". Eine
# zentrale Liste verhindert, dass dort eine Taste fehlt oder anders beschrieben
# ist als in der Konsole, in der die Aufnahme tatsächlich läuft.
AUFNAHME_HOTKEYS = (
    ("CTRL+ALT+J", "starten / beenden",
     "beim Beenden werden die Ereignisse zu Blöcken einer neuen Sequenz"),
    ("CTRL+ALT+H", "pausieren / fortsetzen",
     "im Spiel navigieren, ohne etwas aufzuzeichnen"),
    ("CTRL+ALT+U", "zurücknehmen", "das letzte Ereignis verwerfen"),
    ("CTRL+ALT+SHIFT+M", "auf Farbe warten",
     "der nächste Klick wartet auf die dort aufgenommene Farbe"),
    ("CTRL+ALT+SHIFT+D", "Screenshot", "Vollbild an dieser Stelle im Ablauf"),
    ("CTRL+ALT+SHIFT+R", "Screenshot-Bereich",
     "zweimal drücken: erste und zweite Ecke"),
    ("CTRL+ALT+SHIFT+B", "Pixel beobachten",
     "auf die Farbe unter der Maus warten, ohne dort zu klicken"),
    ("CTRL+ALT+SHIFT+P", "Neue Phase",
     "ab hier die nächste Loop-Phase — beliebig oft"),
)


def aufnahme_datei(seq_name: str):
    """Ziel einer neuen Aufnahme im einheitlichen Sequenzordner."""
    return sequence_file(seq_name)


def _farbtext(farbe) -> str:
    """Farbname ohne Konsolensteuerzeichen für die Weboberfläche."""
    if not farbe:
        return ""
    text = _ANSI.sub("", describe_color(farbe)).strip()
    return text[1:].strip() if text.startswith("█") else text


def _status_ereignisse(events: list) -> list[dict]:
    """Die letzten drei Ereignisse als feste, webtaugliche Ausgabezeilen."""
    start = max(0, len(events) - 3)
    raus = []
    for i in range(start, len(events)):
        event = events[i]
        delay = None if i == 0 else round(event.t - events[i - 1].t, 2)
        raus.append({
            "nummer": i + 1,
            "text": str(event),
            "zeit": "sofort" if delay is None else f"+{delay:.2f}s",
            "farbe": list(event.color) if event.color else None,
            "farbtext": _farbtext(event.color),
        })
    return raus


def _status_schreiben(state: AutoClickerState, events: list | None = None,
                       aktiv: bool | None = None) -> None:
    """Überschreibt den Live-Stand; Fehler dürfen die Aufnahme nie stören."""
    try:
        with state.lock:
            liste = list(state.recording_events) if events is None else list(events)
            laeuft = state.recording_active if aktiv is None else aktiv
            pausiert = state.recording_paused
            name = state.recording_ui_name
        atomic_write(_AUFNAHME_STATUS, compact_json({
            "aktiv": bool(laeuft),
            "pausiert": bool(pausiert and laeuft),
            "name": name,
            "anzahl": len(liste),
            "ereignisse": _status_ereignisse(liste),
            "stand": time.time(),
        }))
    except (OSError, TypeError, ValueError, AttributeError):
        pass


def _melde(ereignis: RecordEvent, idx: int, delay: float | None) -> None:
    """Eine Zeile pro aufgezeichnetem Ereignis — der Nutzer sieht nur die Konsole."""
    farbe = f" {describe_color(ereignis.color)}" if ereignis.color else ""
    zeit = "sofort" if delay is None else f"+{delay:.2f}s"
    print(f"  {col('[REC]', 'red')} #{idx} {ereignis}  {zeit}{farbe}")


def _anhaengen(state: AutoClickerState, ereignis: RecordEvent) -> bool:
    """Hängt ein Ereignis an die Aufnahme. False = Aufnahme aus oder pausiert.

    Mausrad-Ereignisse werden mit dem direkt davor verschmolzen (siehe
    _SCROLL_MERGE_GAP); dann wird die vorhandene Zeile aktualisiert statt einer neuen.
    """
    with state.lock:
        if not state.recording_active or state.recording_paused:
            return False
        vorherige = state.recording_events[-1] if state.recording_events else None
        delay = None if vorherige is None else round(ereignis.t - vorherige.t, 2)
        if (ereignis.kind == REC_SCROLL and vorherige is not None
                and vorherige.kind == REC_SCROLL
                and ereignis.t - vorherige.t <= _SCROLL_MERGE_GAP):
            vorherige.scroll += ereignis.scroll
            vorherige.t = ereignis.t
            idx, ereignis = len(state.recording_events), vorherige
        else:
            state.recording_events.append(ereignis)
            idx = len(state.recording_events)
        events = list(state.recording_events)
    _status_schreiben(state, events)
    _melde(ereignis, idx, delay)
    return True


def _on_click_factory(state: AutoClickerState):
    """Erstellt den Klick-Callback für den Maus-Hook."""
    def _on_click(x: int, y: int, color) -> None:
        # Start/Stopp sind im Studio echte Knöpfe. Deren Klick darf nicht als
        # Spielaktion im Ergebnis landen. Andere Fenster werden bewusst nicht
        # pauschal gefiltert, damit der freie TUI-Weg unverändert bleibt.
        #
        # **Gefragt wird das Fenster UNTER dem Klick, nicht der Vordergrund.**
        # Hier stand `get_foreground_window_title()`, und damit fehlte in
        # JEDER Studio-Aufnahme der erste Klick: der Knopf „Aufnahme starten"
        # liegt im Studio, also ist das Studio vorn — und der erste Klick ins
        # Spiel holt es erst nach vorn. Im Hook steht zu dem Zeitpunkt noch das
        # Studio als Vordergrund, der Klick galt als Studio-Klick und flog raus.
        # Am Ende dasselbe umgekehrt: „Aufnahme stoppen" bei vorn stehendem
        # Spiel kam als Spielklick in die Sequenz (gemessen an einer echten
        # Aufnahme: letzter Schritt `(1347, 709)`, Farbe `#1C2333` = das
        # Panel-Grau des Studios). Derselbe Fehler wie einmal in der
        # Klick-Runde, deshalb derselbe Helfer.
        if "sequenz-studio" in geklicktes_fenster(x, y).casefold():
            return
        _anhaengen(state, RecordEvent(REC_CLICK, time.monotonic(), x, y, color))
    return _on_click


def _on_wheel_factory(state: AutoClickerState):
    """Erstellt den Mausrad-Callback. `delta` ist die rohe Windows-Distanz.

    `None` bei ausgeschaltetem `record_scroll` — dann ignoriert schon die
    Hook-Prozedur das Rad, statt jedes Ereignis nur zum Wegwerfen anzunehmen.
    """
    if not state.config.record_scroll:
        return None

    def _on_wheel(x: int, y: int, delta: int) -> None:
        stufen = int(delta / WHEEL_DELTA)  # Richtung TRUNKIEREN, nicht abrunden
        if stufen:
            _anhaengen(state, RecordEvent(REC_SCROLL, time.monotonic(), x, y,
                                          scroll=stufen))
    return _on_wheel


def _on_key_factory(state: AutoClickerState):
    """Erstellt den Tasten-Callback. `name` ist bereits ein send_key()-Name."""
    def _on_key(name: str) -> None:
        _anhaengen(state, RecordEvent(REC_KEY, time.monotonic(), key=name))
    return _on_key


def merke_farbe(state: AutoClickerState) -> None:
    """Setzt einen Warte-Marker (CTRL+ALT+M): "ab hier warte ich".

    Er hat keine eigene Stelle — beim Drücken parkt die Maus zufällig irgendwo.
    Gewartet wird auf die Farbe des Klicks, der als nächstes kommt; der Marker
    hält also nur die Uhr an. Für eine Stelle, die man NICHT klickt:
    `merke_beobachten()`.
    """
    if not _aufnahme_laeuft(state):
        return
    _anhaengen(state, RecordEvent(REC_WAIT_COLOR, time.monotonic()))


def merke_screenshot(state: AutoClickerState) -> None:
    """Setzt einen Screenshot-Marker (CTRL+ALT+D): Vollbild an dieser Stelle.

    Wird ein eigener Schritt (anders als der Warte-Marker): keine Folge-Aktion,
    an die er sich hängen könnte. Für einen Bereich: `merke_bereich()`.
    """
    if not _aufnahme_laeuft(state):
        return
    _anhaengen(state, RecordEvent(REC_SCREENSHOT, time.monotonic()))


def _aufnahme_laeuft(state: AutoClickerState) -> bool:
    """True = es wird gerade aufgezeichnet. Meldet selbst, wenn nicht.

    Jeder Marker braucht dieselbe Vorprüfung: keine Aufnahme heisst, es gibt nichts zu
    markieren, und pausiert heisst, der Nutzer navigiert gerade absichtlich vorbei.
    """
    with state.lock:
        if not state.recording_active:
            print(f"\n{hint('Keine Aufnahme aktiv — CTRL+ALT+J startet eine.')}")
            return False
        pausiert = state.recording_paused
    if pausiert:
        print(f"\n{hint('Aufnahme pausiert — CTRL+ALT+H setzt sie fort.')}")
        return False
    return True


def merke_bereich(state: AutoClickerState) -> None:
    """Setzt eine Bereichs-Ecke (CTRL+ALT+SHIFT+D). Zwei Ecken = ein Rechteck.

    Die Mausposition ist hier — anders als beim Warte-Marker — bewusst
    angefahren und darf deshalb verwendet werden. Gefaltet wird beim Stoppen
    in `bereiche_zusammenfassen()`.
    """
    if not _aufnahme_laeuft(state):
        return
    x, y = get_cursor_pos()
    _anhaengen(state, RecordEvent(REC_REGION, time.monotonic(), x, y))


def merke_beobachten(state: AutoClickerState) -> None:
    """Warten auf die Farbe UNTER der Maus, ohne dorthin zu klicken (CTRL+ALT+SHIFT+M).

    Entspricht `wait pixel` im Editor. Unterschied zu CTRL+ALT+M: dort steht die
    Maus zufällig, hier legt man sie absichtlich auf das Beobachtete.
    """
    if not _aufnahme_laeuft(state):
        return
    x, y = get_cursor_pos()
    farbe = get_pixel_color(x, y)
    if farbe is None:
        print(f"\n{err('Farbe an der Mausposition nicht lesbar — nichts aufgezeichnet.')}")
        return
    _anhaengen(state, RecordEvent(REC_WATCH, time.monotonic(), x, y, farbe))


def merke_phase(state: AutoClickerState) -> None:
    """Setzt eine Phasengrenze (CTRL+ALT+SHIFT+P): ab hier die nächste Phase.

    Jeder Druck macht eine neue Loop-Phase auf, ohne Obergrenze. Vorher trennte
    der erste Druck INIT von LOOP und der zweite LOOP von END; beim dritten
    stand da "mehr Phasen kann die Aufnahme nicht", und wer vier Abschnitte
    gespielt hatte, musste sie hinterher im Studio von Hand auseinanderziehen.
    Genau der Marker, der sich am wenigsten nachholen lässt — der
    Konsolen-Editor kann keinen Schritt in eine andere Phase verschieben.

    INIT und END befüllt die Aufnahme nicht mehr. Beide waren an dieser Stelle
    eine Vermutung darüber, was gemeint ist; welche Phase einmalig laufen soll,
    sagt man im Studio an der Phase selbst.
    """
    if not _aufnahme_laeuft(state):
        return
    with state.lock:
        gesetzt = sum(1 for ev in state.recording_events if ev.kind == REC_PHASE)
    _anhaengen(state, RecordEvent(REC_PHASE, time.monotonic()))
    print(f"       {hint(f'ab hier: Phase {gesetzt + 2}')}")


def verwirf_letztes(state: AutoClickerState) -> None:
    """Nimmt das zuletzt aufgezeichnete Ereignis zurück (CTRL+ALT+U während Aufnahme).

    Derselbe Hotkey wie das Zurücknehmen eines Punktes: die Bedeutung ist dieselbe
    ("das eben war nichts"), nur der Gegenstand hängt am Zustand. Das spart einen
    eigenen Buchstaben — und es sind ohnehin nur noch vier frei.
    """
    with state.lock:
        entfernt = state.recording_events.pop() if state.recording_events else None
        rest = len(state.recording_events)
        events = list(state.recording_events)
    if entfernt is None:
        print(f"\n{col('[UNDO]', 'yellow')} Nichts aufgezeichnet, nichts zurückzunehmen.")
        return
    _status_schreiben(state, events)
    print(f"\n{col('[UNDO]', 'yellow')} Verworfen: {entfernt}  "
          f"{hint(f'({rest} übrig)')}")


def start_recording(state: AutoClickerState, *, name: str = "", cycles: int = 0,
                    description: str = "") -> None:
    """Startet die Aufnahme; mit Namen ohne spätere Konsolen-Rückfragen."""
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
        if state.recording_active:
            return
        state.recording_active = True
        state.recording_paused = False
        state.recording_events = []
        state.recording_ui_name = str(name or "").strip()
        state.recording_ui_cycles = max(0, int(cycles or 0))
        state.recording_ui_description = str(description or "").strip()

    # None = Mausrad abgeschaltet (record_scroll). Der Hook laeuft dann ohne Rad-Zweig.
    rad = _on_wheel_factory(state)

    if install_mouse_hook(_on_click_factory(state), rad):
        # Die Tastatur ist die Kür: klappt sie nicht, laeuft die Aufnahme trotzdem —
        # nur eben ohne Tastendrücke. Umgekehrt waere eine Aufnahme ohne Klicks sinnlos.
        tasten = install_keyboard_hook(_on_key_factory(state))
        arten = "Linksklick"
        if rad:
            arten += ", Mausrad"
        if tasten:
            arten += ", Tastendruck"
        print(f"\n{col('╔══ AUFNAHME GESTARTET ══╗', 'red')}")
        print("  Klicke die gewünschten Positionen im Spiel.")
        print(f"  Aufgezeichnet: {arten}")
        for taste, aktion, beschreibung in AUFNAHME_HOTKEYS:
            print(f"  {aktion + ':':24} {col(taste, 'yellow')} "
                  f"{hint('(' + beschreibung + ')')}")
        if not tasten:
            print(f"  {warn('Tastatur-Hook nicht installierbar — Tastendrücke fehlen.')}")
        else:
            print(hint("  Tasten mit CTRL oder ALT werden nicht aufgezeichnet —"))
            print(hint("  dort liegen die Hotkeys der App."))
        # Abgeschaltet wird per Config, nicht per Hotkey — dann muss die Aufnahme aber
        # sagen, dass Drehen folgenlos bleibt. Sonst sucht man den Fehler beim Hook.
        if not rad:
            print(hint("  Mausrad wird nicht aufgezeichnet (record_scroll=false)."))
        _status_schreiben(state)
    else:
        with state.lock:
            state.recording_active = False
            state.recording_paused = False
            state.recording_events = []
            state.recording_ui_name = ""
            state.recording_ui_cycles = 0
            state.recording_ui_description = ""
        print(f"\n{err('Maus-Hook konnte nicht installiert werden!')}")
        print("  Mögliche Ursache: Administratorrechte erforderlich.")
        _status_schreiben(state, [], aktiv=False)


def punkte_fuer_events(events: list) -> tuple[dict, list[ClickPoint]]:
    """Sorgt dafür, dass jedes aufgenommene Ereignis mit Stelle einen Punkt hat.

    Gibt `({event_index: point_id}, Punkte)` zurück; ein Punkt an
    derselben Stelle wird wiederverwendet. Muss VOR dem Bauen der Schritte
    laufen, damit die über `point_id` referenzieren statt eigene Koordinaten zu
    halten.

    Keinen Punkt bekommen: Tastendrücke, Warte-Marker (benutzen den Punkt des
    folgenden Klicks), Screenshot-Marker und Phasengrenzen. Der
    Beobachtungs-Marker bekommt einen — seine Stelle ist bewusst gewählt.

    **Ein Punkt heisst `P<ID>`, nicht nach seiner Sequenz.** Er trug einmal den
    Sequenznamen als Vorsatz (`aufnahme_214638 3`), und das war schon vor dem
    Umzug auf Besitzeinheiten nur halb richtig: seither liegt er ohnehin IN
    dieser Sequenz, der Vorsatz sagt also nichts — er wird beim Umbenennen der
    Sequenz falsch, und richtigstellen hiesse, jeden Punkt einzeln anzufassen.
    Die Nummer ist die **Punkt-ID**, nicht der Ereignis-Index: sonst hiesse der
    dritte Punkt einer Aufnahme mit Tastendrücken `P7`, während die Liste `#3`
    daneben schreibt.

    Weder `state` noch der Sequenzname kommen hier noch vor, und das ist die
    Zusicherung: der Punkt-Pool entsteht **allein aus den Ereignissen**. Ein
    `state` in der Signatur war der Weg, auf dem die Punkte einer anderen
    Sequenz hineinlecken konnten.
    """
    from ..persistence.sequences import punkt_an_stelle
    punkt_id_fuer: dict[int, int] = {}
    punkte: list[ClickPoint] = []
    for i, ev in enumerate(events):
        if ev.kind in (REC_KEY, REC_WAIT_COLOR, REC_SCREENSHOT, REC_PHASE):
            continue
        treffer = punkt_an_stelle(punkte, ev.x, ev.y, ev.color)
        if treffer is not None:
            punkt_id_fuer[i] = treffer.id
            continue
        pid = max((p.id for p in punkte), default=0) + 1
        punkt = ClickPoint(ev.x, ev.y, f"P{pid}", pid,
                           color=ev.color, source="Aufnahme")
        punkte.append(punkt)
        punkt_id_fuer[i] = pid
    return punkt_id_fuer, punkte


def bereiche_zusammenfassen(events: list) -> tuple[list, int]:
    """Faltet je zwei Bereichs-Ecken zu EINEM Screenshot-Ereignis mit Rechteck.

    Läuft als erster Schritt beim Stoppen; danach kennt niemand mehr
    `REC_REGION`. Zeitstempel ist der der ersten Ecke, das Rechteck wird
    normalisiert. Eine einzelne Ecke wird verworfen und gemeldet — still zu
    Vollbild zu degradieren wäre etwas anderes als das Gewollte.

    Gibt `(bereinigte Ereignisse, Anzahl verworfener Einzel-Ecken)` zurück.
    """
    behalten, verworfen = [], 0
    offen = None
    for ev in events:
        if ev.kind != REC_REGION:
            behalten.append(ev)
            continue
        if offen is None:
            offen = ev
            continue
        x1, x2 = sorted((offen.x, ev.x))
        y1, y2 = sorted((offen.y, ev.y))
        behalten.append(RecordEvent(REC_SCREENSHOT, offen.t, region=(x1, y1, x2, y2)))
        offen = None
    if offen is not None:
        verworfen = 1
    return behalten, verworfen


def phasen_grenzen(events: list) -> tuple[list, list[int]]:
    """Zieht die Phasengrenzen aus dem Ereignisstrom heraus.

    Gibt `(Ereignisse OHNE Grenzen, Schnittstellen als Schritt-Indizes)` zurück.
    Entfernt statt übersprungen: sonst wäre eine Grenze das „vorherige Ereignis"
    des nächsten Schritts und dessen Wartezeit begänne am Tastendruck. Gezählt
    wird in Schritten, denn Warte-Marker erzeugen keinen eigenen.
    """
    behalten, grenzen = [], []
    erzeugte = 0
    for ev in events:
        if ev.kind == REC_PHASE:
            grenzen.append(erzeugte)
            continue
        if ev.kind != REC_WAIT_COLOR:
            erzeugte += 1
        behalten.append(ev)
    return behalten, grenzen


def phasen_bauen(steps: list, grenzen: list[int]) -> list:
    """Schneidet die fertige Schrittliste an den Grenzen in Loop-Phasen.

    Ohne Grenze bleibt alles in EINER Phase — exakt das bisherige Verhalten.
    Jede Grenze macht eine weitere auf; eine Obergrenze gibt es nicht.

    Leere Abschnitte fallen weg: zweimal hintereinander gedrückt ist derselbe
    Wunsch, zweimal geäussert — dieselbe Regel wie bei zwei Warte-Markern
    hintereinander. Bleibt gar nichts übrig, kommt trotzdem eine leere Phase
    zurück; eine Sequenz ohne jede Loop-Phase hat keine Stelle, an der man
    danach etwas einfügen könnte.
    """
    schnitte = [0] + [min(g, len(steps)) for g in grenzen] + [len(steps)]
    phasen = []
    for anfang, ende_ in zip(schnitte, schnitte[1:]):
        teil = list(steps[anfang:ende_])
        if not teil:
            continue
        nummer = len(phasen) + 1
        name = "Loop" if nummer == 1 else f"Loop {nummer}"
        phasen.append(LoopPhase(name=name, steps=teil, repeat=1))
    if not phasen:
        phasen.append(LoopPhase(name="Loop", steps=[], repeat=1))
    return phasen


def marker_pruefen(events: list) -> tuple[list, int]:
    """Wirft Warte-Marker weg, die sich an nichts hängen können.

    Ein Marker braucht einen Klick oder ein Scroll nach sich — von dort holt er
    Stelle und Farbe. Zwei hintereinander sind derselbe Wunsch, zweimal geäussert.

    Gibt `(bereinigte Ereignisse, Anzahl verworfener)` zurück.
    """
    behalten, verworfen = [], 0
    for i, ev in enumerate(events):
        if ev.kind == REC_WAIT_COLOR:
            naechster = events[i + 1] if i + 1 < len(events) else None
            if naechster is None or naechster.kind not in (REC_CLICK, REC_SCROLL):
                verworfen += 1
                continue
        behalten.append(ev)
    return behalten, verworfen


def schritte_aus_events(events: list, punkt_id_fuer: dict) -> list:
    """Baut die SequenceSteps.

    Ein Warte-Marker wird kein eigener Schritt: er hängt sich an den folgenden
    Klick und macht daraus „warte auf die Farbe dieser Stelle, dann klicke sie"
    (ein Punkt, zweimal referenziert). Die Zeit bis zum Marker bleibt Wartezeit,
    die Zeit danach fällt weg — sie ist genau das, was die Bedingung ersetzt.

    Screenshot- und Beobachtungs-Marker werden dagegen eigene Schritte.

    Erwartet Ereignisse, die `bereiche_zusammenfassen()`, `phasen_grenzen()` und
    `marker_pruefen()` schon durchlaufen haben.
    """
    steps = []
    for i, ev in enumerate(events):
        if ev.kind == REC_WAIT_COLOR:
            continue                      # geht in den naechsten Schritt ein
        delay = 0.0 if i == 0 else round(ev.t - events[i - 1].t, 2)
        bedingung = None
        vorher = events[i - 1] if i > 0 else None
        if vorher is not None and vorher.kind == REC_WAIT_COLOR:
            pid = punkt_id_fuer.get(i)
            bedingung = WaitCondition(point_id=pid)
            # Uhr anhalten: die Zeit bis zum MARKER zaehlt, die danach ist das Warten.
            davor = events[i - 2] if i > 1 else None
            delay = 0.0 if davor is None else round(vorher.t - davor.t, 2)

        pid = punkt_id_fuer.get(i)
        if ev.kind == REC_KEY:
            steps.append(SequenceStep(delay_before=delay, key_press=ev.key))
        elif ev.kind == REC_SCREENSHOT:
            # Kein Klick, keine Stelle. `region` ist None (CTRL+ALT+D = Vollbild) oder
            # das aus zwei Ecken gefaltete Rechteck (CTRL+ALT+SHIFT+D).
            r = ev.region
            steps.append(SequenceStep(
                delay_before=delay, screenshot_only=True, screenshot_region=r,
                name=(f"Screenshot ({r[0]},{r[1]})→({r[2]},{r[3]})" if r
                      else "Screenshot (Vollbild)")))
        elif ev.kind == REC_WATCH:
            # Warten, bis die Farbe an DIESER Stelle da ist — ohne hinzuklicken.
            # `wait_only=True` und kein `point_id` am Schritt: das Ziel ist ein
            # Prüf-Pixel, kein Klickziel. Genau das baut `wait pixel` im Editor.
            steps.append(SequenceStep(
                delay_before=delay, wait_only=True, name="Beobachten",
                recorded_color=ev.color,
                wait_condition=WaitCondition(point_id=punkt_id_fuer.get(i))))
        elif ev.kind == REC_SCROLL:
            steps.append(SequenceStep(x=ev.x, y=ev.y, delay_before=delay, scroll=ev.scroll,
                                      point_id=pid, recorded_color=ev.color,
                                      wait_condition=bedingung))
        else:
            steps.append(SequenceStep(x=ev.x, y=ev.y, delay_before=delay,
                                      name=f"Klick {len(steps) + 1}",
                                      recorded_color=ev.color, point_id=pid,
                                      wait_condition=bedingung))
    return steps


def stop_recording(state: AutoClickerState) -> str | None:
    """Stoppt die Aufnahme und baut eine Sequenz aus den Ereignissen."""
    with state.lock:
        if not state.recording_active:
            return
        state.recording_active = False
        state.recording_paused = False
        events = list(state.recording_events)
        state.recording_events = []
        ui_name = state.recording_ui_name
        ui_cycles = state.recording_ui_cycles
        ui_description = state.recording_ui_description
        state.recording_ui_name = ""
        state.recording_ui_cycles = 0
        state.recording_ui_description = ""

    remove_mouse_hook()
    remove_keyboard_hook()
    _status_schreiben(state, events, aktiv=False)

    if not events:
        print(f"\n{col('[AUFNAHME]', 'yellow')} Gestoppt — nichts aufgezeichnet.")
        return None

    # Feste Reihenfolge - jede Stufe entfernt eine Sonderform: Bereichs-Ecken
    # falten, Phasengrenzen herausziehen, haltlose Warte-Marker verwerfen.
    events, halbe_ecke = bereiche_zusammenfassen(events)
    if halbe_ecke:
        print(f"\n{warn('Einzelne Bereichs-Ecke verworfen — die zweite fehlt.')}")
        print(hint("       Ein Bereich braucht ZWEI Drücke: eine Ecke, dann die andere."))

    events, grenzen = phasen_grenzen(events)

    events, verworfen = marker_pruefen(events)
    if verworfen:
        print(f"\n{warn(f'{verworfen} Warte-Marker verworfen — danach kam kein Klick.')}")
        print(hint("       Ein Marker wartet auf die Farbe DES Klicks, der ihm folgt."))

    if not events:
        print(f"{col('[AUFNAHME]', 'yellow')} Nichts Verwertbares übrig.")
        return None

    print(f"\n{col('╚══ AUFNAHME GESTOPPT ══╝', 'green')} "
          f"{len(events)} Ereignis(se) aufgezeichnet.")

    # Aufgezeichnetes zeigen. Die Phasengrenzen stehen nicht mehr im Strom (sie wurden
    # oben herausgezogen), muessen hier aber sichtbar sein — sonst sieht der Nutzer die
    # Aufteilung erst im Editor und kann sie beim Benennen nicht mehr einordnen.
    # Namen wie in phasen_bauen(), damit hier dasselbe steht wie danach in der
    # Datei. Der Schnitt liegt VOR dem Schritt mit diesem Index.
    def _phasenname(nummer):
        return "Loop" if nummer == 1 else f"Loop {nummer}"

    _schnitt = {g: _phasenname(nr + 2) for nr, g in enumerate(grenzen)}
    if grenzen:
        print(f"\n{col('Aufgezeichnet:', 'bold')} {hint('(Phasen sind markiert)')}")
        print(f"  {col('┌─ ' + _phasenname(1), 'magenta')}")
    else:
        print(f"\n{col('Aufgezeichnet:', 'bold')}")
    fast_clicks = 0
    erzeugte = 0
    for i, ev in enumerate(events):
        if ev.kind != REC_WAIT_COLOR:
            if erzeugte in _schnitt:
                print(f"  {col('├─ ' + _schnitt.pop(erzeugte), 'magenta')}")
            erzeugte += 1
        color_str = f"  {describe_color(ev.color)}" if ev.color else ""
        if i == 0:
            delay_str = "sofort"
        else:
            d = ev.t - events[i - 1].t
            delay_str = f"+{d:.2f}s"
            if events[i - 1].kind == REC_WAIT_COLOR:
                # Diese Spanne ersetzt die Farb-Bedingung (siehe schritte_aus_events);
                # sie als Wartezeit oder gar als Doppelklick zu zeigen waere falsch.
                delay_str = col(f"wartet auf {describe_color(ev.color)}", "cyan") \
                    if ev.color else col("wartet auf die Farbe hier", "cyan")
            elif d < _FAST_CLICK_GAP and ev.kind == REC_CLICK and events[i - 1].kind == REC_CLICK:
                fast_clicks += 1
                delay_str = col(delay_str + " ⚡", "yellow")
        print(f"  {col(str(i+1), 'cyan'):>4}  {str(ev):<38}  {delay_str}{color_str}")

    if fast_clicks:
        print(f"\n{col('Hinweis:', 'yellow')} {fast_clicks} sehr schnelle(r) Klick(s) (⚡, < {_FAST_CLICK_GAP:.2f}s Abstand).")
        print(hint("        Falls das versehentliche Doppelklicks waren: im Editor mit 'del <Nr>' entfernen."))

    if ui_name:
        # UI-Aufnahme: alle Angaben stehen schon vor dem ersten Klick fest. So
        # wartet der Abschluss nie unsichtbar in der Konsole auf eine Eingabe.
        seq_name = ui_name
        total_cycles = ui_cycles
        description = ui_description
    else:
        # Klassischer TUI-Weg — absichtlich als zweite Bedienart erhalten.
        auto_name = f"Aufnahme_{datetime.now().strftime('%H%M%S')}"
        print(f"\nSequenz-Name (Enter = {col(auto_name, 'cyan')}, {col('cancel', 'yellow')} = verwerfen):")
        try:
            name_input = safe_input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{col('[VERWORFEN]', 'yellow')}")
            return None

        if is_cancel(name_input):
            print(f"{col('[VERWORFEN]', 'yellow')} Aufnahme nicht gespeichert.")
            return None

        seq_name = name_input if name_input else auto_name
        print(f"\nZyklen (0 = unendlich, Enter = {col('unendlich', 'cyan')}):")
        try:
            cycles_input = safe_input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            cycles_input = ""
        total_cycles = 0
        if cycles_input:
            try:
                total_cycles = max(0, int(cycles_input))
            except ValueError:
                print(f"  -> '{cycles_input}' ungültig — nutze unendlich")
        print(f"\nBeschreibung (optional, Enter = {col('keine', 'cyan')}):")
        try:
            description = safe_input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            description = ""
        if is_cancel(description):
            description = ""

    # ERST die Punkte, DANN die Schritte — die Reihenfolge ist der Punkt.
    punkt_id_fuer, punkte = punkte_fuer_events(events)

    # SequenceSteps aus den Events bauen — jeder mit Referenz auf seinen Punkt
    steps = schritte_aus_events(events, punkt_id_fuer)
    # INIT und END bleiben leer: eine Aufnahme sieht nicht, welcher Abschnitt
    # nur einmal laufen soll. Das steht im Studio an der Phase.
    loop_phases = phasen_bauen(steps, grenzen)
    seq = Sequence(name=seq_name, loop_phases=loop_phases, total_cycles=total_cycles,
                   description=description, points=punkte)

    # Speichern
    ensure_sequences_dir()
    # Eine Aufnahme ist eine vollständige Sequenz und bekommt deshalb dieselbe
    # Besitzeinheit wie jede im Studio angelegte: sequences/<name>/sequence.json.
    # Direkte JSON-Dateien unter sequences/ waeren wieder das alte Mischlayout,
    # in dem Scans und Vorlagen nicht eindeutig zugeordnet werden konnten.
    filepath = aufnahme_datei(seq_name)

    if save_sequence_file(seq, filepath):
        with state.lock:
            # Sofort aufloesen: sonst zeigt der Editor direkt nach der Aufnahme
            # "(0,0)" statt der Stelle, auf die gewartet wird.
            resolve_point_references(state, seq)
            state.sequences[seq_name] = seq
            state.active_sequence = seq
            state.points = seq.points

        cycles_str = "unendlich" if total_cycles == 0 else str(total_cycles)
        saved_msg = ok(f'Sequenz "{seq_name}" gespeichert!')
        print(f"\n{saved_msg}")
        if len(loop_phases) > 1:
            aufteilung = "  |  ".join(f"{len(lp.steps)} {lp.name}" for lp in loop_phases)
            print(f"  {aufteilung}  |  Zyklen: {cycles_str}")
        else:
            print(f"  {len(steps)} Schritte  |  Zyklen: {cycles_str}")
        if punkte:
            print(f"  {len(punkte)} Punkt(e) in dieser Sequenz gespeichert "
                  f"{hint('(im Editor + Studio-Palette nutzbar)')}")
        print(f"  Starten:    {col('CTRL+ALT+S', 'yellow')}")
        print(f"  Bearbeiten: {col('CTRL+ALT+E', 'yellow')}")
        print(hint("  Tipp: Im Editor wandelt 'color <Nr>' einen Klick in einen"))
        print(hint("        Farb-Trigger um (nutzt die aufgenommene Farbe),"))
        print(hint("        'noclick <Nr>' macht reines Warten daraus."))
        if any(e.kind == REC_WAIT_COLOR for e in events):
            print(hint("        'colorgone <Nr>' dreht einen Warte-Marker um:"))
            print(hint("        warten bis die Farbe WEG ist statt bis sie da ist."))
        if any(e.kind == REC_SCREENSHOT and not e.region for e in events):
            print(hint("        'screenshot x1 y1 x2 y2' bzw. 'ss' grenzt einen"))
            print(hint("        Vollbild-Screenshot nachträglich auf einen Bereich ein."))
        return seq_name
    else:
        print(f"\n{err('Sequenz konnte nicht gespeichert werden!')}")
        return None


def handle_record_sequence(state: AutoClickerState) -> None:
    """Togglet die Sequenz-Aufnahme: erstes Drücken = Start, zweites = Stop."""
    with state.lock:
        is_recording = state.recording_active

    if is_recording:
        stop_recording(state)
    else:
        start_recording(state)


def handle_record_pause(state: AutoClickerState) -> None:
    """Togglet die Pause der laufenden Aufnahme (nur während einer Aufnahme aktiv)."""
    with state.lock:
        if not state.recording_active:
            print(f"\n{hint('Keine Aufnahme aktiv — CTRL+ALT+J startet eine.')}")
            return
        state.recording_paused = not state.recording_paused
        paused = state.recording_paused

    if paused:
        print(f"\n{col('[PAUSE]', 'yellow')} Aufnahme pausiert — Klicks werden NICHT aufgezeichnet.")
        print(f"  Fortsetzen: {col('CTRL+ALT+H', 'yellow')} erneut drücken")
    else:
        print(f"\n{col('[REC]', 'red')} Aufnahme fortgesetzt — Klicks werden wieder aufgezeichnet.")
    _status_schreiben(state)
