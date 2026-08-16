"""
Sequenz-Aufnahme: Zeichnet echtes Spielen auf und baut daraus eine Sequenz.

Start/Stop über CTRL+ALT+J. Aufgezeichnet werden Linksklicks (mit Position,
Zeitstempel und Pixelfarbe), Tastendrücke, das Mausrad und — per CTRL+ALT+M —
Warte-Marker auf eine Farbe. Nach dem Stoppen wird eine Sequenz daraus erstellt
und direkt geladen.

Alles muss mit EINEM globalen Tastendruck gehen: während der Aufnahme steht der
Nutzer im Spiel, nicht in der Konsole. Nachfragen sind erst beim Stoppen möglich.
"""

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
from ..imaging import get_pixel_color
from ..utils import safe_input, col, ok, err, warn, is_cancel, hint, describe_color
from ..persistence.sequences import (
    save_sequence_file, ensure_sequences_dir, save_points, get_next_point_id,
    resolve_point_references,
)
from ..utils import sanitize_filename
from ..config import SEQUENCES_DIR


# Klicks die schneller als dieser Abstand (Sekunden) aufeinander folgen sind
# fast immer versehentliche Doppel-/Zitterklicks — beim Stoppen wird darauf
# hingewiesen (nicht automatisch gelöscht, um echte Doppelklicks zu erhalten).
_FAST_CLICK_GAP = 0.08

# Mausrad-Ereignisse innerhalb dieses Abstands (Sekunden) gehören zu EINER Drehung
# und werden zu einem Schritt zusammengefasst. Ohne das würde ein einziges Drehen
# um fünf Rasten zu fünf Schritten — das Rad feuert pro Raste ein eigenes Ereignis.
_SCROLL_MERGE_GAP = 0.25


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
    _melde(ereignis, idx, delay)
    return True


def _on_click_factory(state: AutoClickerState):
    """Erstellt den Klick-Callback für den Maus-Hook."""
    def _on_click(x: int, y: int, color) -> None:
        _anhaengen(state, RecordEvent(REC_CLICK, time.monotonic(), x, y, color))
    return _on_click


def _on_wheel_factory(state: AutoClickerState):
    """Erstellt den Mausrad-Callback. `delta` ist die rohe Windows-Distanz.

    Gibt `None` zurück, wenn `record_scroll` aus ist — `install_mouse_hook` ignoriert
    das Rad dann bereits in der Hook-Prozedur. Absichtlich hier und nicht erst in
    `_anhaengen`: ein Callback, der jedes Ereignis entgegennimmt, um es wegzuwerfen,
    liefe bei jeder Radbewegung mit, auch wenn niemand aufnimmt.
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

    Der Marker hat **keine eigene Stelle**. Beim Drücken parkt die Maus irgendwo —
    diese Position wäre reiner Zufall, und ein Punkt darauf wäre Müll in points.json.
    Gewartet wird stattdessen auf die Farbe DES Klicks, der als nächstes kommt: genau
    dort, wo das Erwartete auftaucht, klickt man ja hin.

    Damit hält der Marker nur die Uhr an: die Zeit bis zu seinem Drücken bleibt echte
    Wartezeit, die Zeit danach ersetzt die Farb-Bedingung.

    Wer auf eine Stelle warten will, die er NICHT klickt, nimmt `merke_beobachten()`
    (`CTRL+ALT+SHIFT+M`) — dort ist die Mausposition dann bewusst gewählt.
    """
    if not _aufnahme_laeuft(state):
        return
    _anhaengen(state, RecordEvent(REC_WAIT_COLOR, time.monotonic()))


def merke_screenshot(state: AutoClickerState) -> None:
    """Setzt einen Screenshot-Marker (CTRL+ALT+D): "hier einen Screenshot machen".

    Anders als der Warte-Marker braucht der Screenshot-Marker keine Folge-Aktion und
    keine eigene Stelle: er wird selbst zu einem eigenständigen Screenshot-Step an
    genau dieser Stelle der Zeitachse (`schritte_aus_events`).

    Vollbild. Wer einen **Bereich** will, nimmt `merke_bereich()`
    (`CTRL+ALT+SHIFT+D`, zweimal drücken = zwei Ecken).
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

    Ein Rechteck aufzuziehen braucht zwei Stellen — und während der Aufnahme gibt es
    nichts als Tastendrücke. Also zweimal derselbe Druck an zwei Mauspositionen; das
    Falten zum Screenshot-Schritt macht `bereiche_zusammenfassen()` beim Stoppen.

    Die Mausposition ist hier — anders als beim Warte-Marker — **bewusst gewählt**:
    man fährt die Ecke an und drückt. Deshalb darf sie verwendet werden.
    """
    if not _aufnahme_laeuft(state):
        return
    x, y = get_cursor_pos()
    _anhaengen(state, RecordEvent(REC_REGION, time.monotonic(), x, y))


def merke_beobachten(state: AutoClickerState) -> None:
    """Warten auf die Farbe UNTER der Maus, ohne dorthin zu klicken (CTRL+ALT+SHIFT+M).

    Der Unterschied zum Warte-Marker (`CTRL+ALT+M`) ist der Vertrag über die
    Mausposition: dort steht sie zufällig irgendwo und der Marker hängt sich an den
    nächsten Klick; hier legt man die Maus absichtlich auf das, was man beobachtet, und
    geklickt wird gar nicht. Entspricht `wait pixel` im Sequenz-Editor — was die
    Aufnahme bisher nicht konnte.
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

    Erster Druck trennt INIT von LOOP, zweiter LOOP von END — in genau der Reihenfolge,
    in der man beim Spielen darauf stösst. Ohne Marker bleibt alles in einer Loop-Phase
    (das bisherige Verhalten).

    Das ist der Marker, der sich am wenigsten nachholen lässt: der Sequenz-Editor
    bearbeitet jede Phase für sich (`edit_phase`), einen Befehl zum Verschieben eines
    Schritts in eine ANDERE Phase gibt es nicht. Nachträglich aufteilen hiesse löschen
    und neu anlegen — bei 50 aufgenommenen Schritten fällt das aus.
    """
    if not _aufnahme_laeuft(state):
        return
    with state.lock:
        gesetzt = sum(1 for e in state.recording_events if e.kind == REC_PHASE)
    if gesetzt >= 2:
        print(f"\n{hint('Beide Grenzen stehen schon (INIT|LOOP|END) — mehr Phasen kann die Aufnahme nicht.')}")
        print(hint("       Weitere Loop-Phasen legt der Sequenz-Editor an."))
        return
    _anhaengen(state, RecordEvent(REC_PHASE, time.monotonic()))
    print(f"       {hint('ab hier: ' + ('LOOP' if gesetzt == 0 else 'END'))}")


def verwirf_letztes(state: AutoClickerState) -> None:
    """Nimmt das zuletzt aufgezeichnete Ereignis zurück (CTRL+ALT+U während Aufnahme).

    Derselbe Hotkey wie das Zurücknehmen eines Punktes: die Bedeutung ist dieselbe
    ("das eben war nichts"), nur der Gegenstand hängt am Zustand. Das spart einen
    eigenen Buchstaben — und es sind ohnehin nur noch vier frei.
    """
    with state.lock:
        entfernt = state.recording_events.pop() if state.recording_events else None
        rest = len(state.recording_events)
    if entfernt is None:
        print(f"\n{col('[UNDO]', 'yellow')} Nichts aufgezeichnet, nichts zurückzunehmen.")
        return
    print(f"\n{col('[UNDO]', 'yellow')} Verworfen: {entfernt}  "
          f"{hint(f'({rest} übrig)')}")


def start_recording(state: AutoClickerState) -> None:
    """Startet die Sequenz-Aufnahme."""
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
        if state.recording_active:
            return
        state.recording_active = True
        state.recording_paused = False
        state.recording_events = []

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
        print(f"  Auf Farbe warten: {col('CTRL+ALT+M', 'yellow')} "
              f"{hint('(drücken, sobald du anfängst zu warten)')}")
        print(hint("                    Dein NÄCHSTER Klick wartet dann erst auf die"))
        print(hint("                    Farbe, die er beim Klicken vorfindet. Die Maus"))
        print(hint("                    darf beim Drücken irgendwo stehen."))
        print(f"  Screenshot:       {col('CTRL+ALT+D', 'yellow')} (Vollbild)  |  "
              f"{col('+SHIFT', 'yellow')} = Bereich {hint('(2× drücken: Ecke, Ecke)')}")
        print(f"  Beobachten:       {col('CTRL+ALT+SHIFT+M', 'yellow')} "
              f"{hint('(warten auf die Farbe UNTER der Maus, ohne Klick)')}")
        print(f"  Phasengrenze:     {col('CTRL+ALT+SHIFT+P', 'yellow')} "
              f"{hint('(1× = ab hier LOOP, 2× = ab hier END)')}")
        print(f"  Zurücknehmen:     {col('CTRL+ALT+U', 'yellow')} (letztes Ereignis verwerfen)")
        print(f"  Pausieren:        {col('CTRL+ALT+H', 'yellow')} (navigieren ohne aufzuzeichnen)")
        print(f"  Stoppen:          {col('CTRL+ALT+J', 'yellow')} erneut drücken")
        if not tasten:
            print(f"  {warn('Tastatur-Hook nicht installierbar — Tastendrücke fehlen.')}")
        else:
            print(hint("  Tasten mit CTRL oder ALT werden nicht aufgezeichnet —"))
            print(hint("  dort liegen die Hotkeys der App."))
        # Abgeschaltet wird per Config, nicht per Hotkey — dann muss die Aufnahme aber
        # sagen, dass Drehen folgenlos bleibt. Sonst sucht man den Fehler beim Hook.
        if not rad:
            print(hint("  Mausrad wird nicht aufgezeichnet (record_scroll=false)."))
    else:
        with state.lock:
            state.recording_active = False
            state.recording_paused = False
            state.recording_events = []
        print(f"\n{err('Maus-Hook konnte nicht installiert werden!')}")
        print("  Mögliche Ursache: Administratorrechte erforderlich.")


def punkte_fuer_events(state: AutoClickerState, events: list,
                       seq_name: str) -> tuple[dict, int]:
    """Sorgt dafür, dass jedes aufgenommene Ereignis mit Stelle einen Punkt hat.

    Gibt `({event_index: point_id}, Anzahl neu angelegter)` zurück. Bestehende Punkte
    gewinnen: liegt schon einer auf der Stelle, wird er referenziert statt ein
    zweiter danebengelegt. Tastendrücke haben keine Stelle und bekommen keinen Punkt.

    Warum das VOR dem Bauen der Schritte laufen muss: die Schritte sollen den Punkt
    über `point_id` referenzieren, statt ihre Koordinaten selbst zu halten. Vorher
    entstanden beide unabhängig voneinander — die Punkte wurden erst hinterher
    angelegt, und nichts verband sie. Die Migration verknüpft zwar nach Koordinaten,
    läuft aber nur auf Dateien mit ALTEM Schema; eine frisch aufgenommene Sequenz ist
    bereits auf dem aktuellen Stand gestempelt und wurde deshalb nie verknüpft.

    Folge war: ein später verschobener Punkt zog die Aufnahme nicht mit, obwohl beide
    auf derselben Stelle sassen — genau die Unstimmigkeit, die `point_id` verhindern soll.

    Warte-Marker bekommen **keinen** Punkt: sie haben keine eigene Stelle. Sie warten
    auf die Farbe des Klicks, der ihnen folgt, und benutzen dessen Punkt.

    Screenshot-Marker und Phasengrenzen bekommen ebenfalls **keinen** Punkt: der eine
    ist ein Vollbild-/Bereichs-Schritt ohne Ziel-Koordinate, die andere gar kein Schritt.

    Der Beobachtungs-Marker (`REC_WATCH`) bekommt dagegen **sehr wohl** einen: seine
    Stelle ist bewusst gewählt (Maus auf das beobachtete Ding), und sie muss in
    points.json stehen — der Schritt referenziert sie über `wait_point_id`, wie jede
    andere Prüf-Stelle auch.
    """
    from ..persistence.sequences import punkt_an_stelle
    punkt_id_fuer: dict[int, int] = {}
    neu = 0
    with state.lock:
        # **Nicht mehr auf die exakte Koordinate.** Denselben Knopf trifft man
        # beim Aufnehmen nie zweimal pixelgenau, und mit exaktem Vergleich
        # entstand pro Klick ein eigener Punkt - in einer echten Aufnahme lagen
        # so vier Punkte auf einem einzigen gruenen Knopf. `punkt_an_stelle()`
        # ist dieselbe Regel, die auch der Editor benutzt: Radius UND Farbe.
        bekannt = list(state.points)
        for i, ev in enumerate(events):
            if ev.kind in (REC_KEY, REC_WAIT_COLOR, REC_SCREENSHOT, REC_PHASE):
                continue
            treffer = punkt_an_stelle(bekannt, ev.x, ev.y, ev.color)
            if treffer is not None:
                punkt_id_fuer[i] = treffer.id
                continue
            pid = get_next_point_id(state)
            state.points.append(
                ClickPoint(ev.x, ev.y, f"{seq_name} {i + 1}", pid, color=ev.color,
                           source=f"Aufnahme '{seq_name}'")
            )
            # Der frische Punkt zaehlt sofort mit: der naechste Klick auf
            # denselben Knopf soll IHN finden, nicht einen dritten anlegen.
            bekannt.append(state.points[-1])
            punkt_id_fuer[i] = pid
            neu += 1
    return punkt_id_fuer, neu


def bereiche_zusammenfassen(events: list) -> tuple[list, int]:
    """Faltet je zwei Bereichs-Ecken zu EINEM Screenshot-Ereignis mit Rechteck.

    Läuft als erster Schritt beim Stoppen — danach existiert `REC_REGION` nicht mehr,
    und alles Weitere (Punkte, Schritte, Phasen) sieht nur noch ein gewöhnliches
    `REC_SCREENSHOT`. Ohne diese Trennung müsste jede nachgelagerte Stelle wissen,
    dass zwei Ereignisse manchmal einen Schritt ergeben.

    Der Zeitstempel des Paares ist der der **ersten** Ecke: dort hat der Nutzer
    entschieden „hier", und dort soll der Screenshot im Ablauf sitzen.

    Die Sekunden fürs Mausbewegen zur zweiten Ecke bleiben damit in der Wartezeit des
    **nächsten** Schritts stehen. Das ist Absicht: die Aufnahme erfindet keine Zeit und
    wirft keine weg — sie gibt wieder, was verstrichen ist. Bedienzeit von Spielzeit zu
    trennen kann sie ohnehin nicht (Nachdenken sieht genauso aus), und wer eine Pause
    wirklich raushaben will, hat dafür `CTRL+ALT+H`.

    Das Rechteck wird normalisiert (links/oben zuerst), damit es egal ist, in welcher
    Reihenfolge die Ecken angefahren wurden.

    Eine einzelne Ecke am Ende wird verworfen und gemeldet — ein halbes Rechteck ist
    kein Bereich, und ein stillschweigend zu Vollbild degradierter Screenshot wäre
    etwas anderes als das, was der Nutzer wollte.

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

    Die Grenzen werden **entfernt**, nicht bloss übersprungen — genau wie die
    Bereichs-Ecken. Sonst wäre eine Grenze das „vorherige Ereignis" des nächsten
    Schritts, und dessen Wartezeit würde ab dem Tastendruck statt ab der letzten
    echten Aktion gemessen: aus 6 Sekunden Warten würde 1 Sekunde, weil 5 davon vor
    dem Drücken lagen. Ein Marker verbraucht keine Zeit, also darf er in der
    Zeitrechnung auch nicht vorkommen.

    Gezählt wird in Schritten, nicht in Ereignissen: Warte-Marker erzeugen keinen
    eigenen Schritt (sie gehen im nächsten auf) und dürfen den Schnitt nicht verschieben.
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


def phasen_aufteilen(steps: list, grenzen: list[int]) -> tuple[list, list, list]:
    """Schneidet die fertige Schrittliste in (INIT, LOOP, END).

    Ohne Grenze bleibt alles in LOOP — exakt das bisherige Verhalten. Eine Grenze
    trennt INIT von LOOP, zwei zusätzlich LOOP von END.
    """
    if not grenzen:
        return [], list(steps), []
    a = min(grenzen[0], len(steps))
    b = min(grenzen[1], len(steps)) if len(grenzen) > 1 else len(steps)
    return list(steps[:a]), list(steps[a:b]), list(steps[b:])


def marker_pruefen(events: list) -> tuple[list, int]:
    """Wirft Warte-Marker weg, die sich an nichts hängen können.

    Ein Marker braucht einen Klick (oder ein Scroll) nach sich — von dem holt er
    Stelle und Farbe. Folgt ein Tastendruck oder gar nichts mehr, gibt es nichts zu
    warten; der Marker wird verworfen statt stillschweigend zu verschwinden.

    Zwei Marker hintereinander sind derselbe Wunsch, zweimal geäussert: der erste
    fällt weg, der zweite hält die Uhr an.

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

    Ein **Warte-Marker wird kein eigener Schritt**. Er hängt sich an den Klick, der
    ihm folgt, und macht daraus „warte auf die Farbe DIESER Stelle, dann klicke sie" —
    genau das, was der Editor mit `color <Nr>` baut: ein Schritt, ein Punkt, zweimal
    referenziert (einmal als Klickziel, einmal als Prüf-Pixel).

    Die Farbe ist die beim Klick erfasste. Das ist die richtige: geklickt wird ja
    erst, wenn das Erwartete zu sehen ist.

    Bei den Wartezeiten hält der Marker nur die Uhr an:

    - Die Zeit **bis** zum Marker bleibt am Schritt — bis dahin lief normal etwas ab.
    - Die Zeit **vom** Marker bis zum Klick fällt weg. Genau sie ist das Warten, das
      die Bedingung ersetzt; bliebe sie stehen, würde die Sequenz erst auf die Farbe
      warten UND danach nochmal die volle Zeit schlafen.

    Ein **Screenshot-Marker wird sein eigener Schritt** (anders als der Warte-Marker):
    er hat keine Folge-Aktion, an die er sich hängen könnte, und keine eigene Stelle.
    Dasselbe gilt für den Beobachtungs-Marker — der wird ein `wait_only`-Schritt.

    Erwartet Ereignisse, die `bereiche_zusammenfassen()`, `phasen_grenzen()` und
    `marker_pruefen()` bereits durchlaufen haben: Bereichs-Ecken sind zu Screenshots
    gefaltet, Phasengrenzen entfernt, haltlose Warte-Marker verworfen.
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


def stop_recording(state: AutoClickerState) -> None:
    """Stoppt die Aufnahme und baut eine Sequenz aus den Ereignissen."""
    with state.lock:
        if not state.recording_active:
            return
        state.recording_active = False
        state.recording_paused = False
        events = list(state.recording_events)
        state.recording_events = []

    remove_mouse_hook()
    remove_keyboard_hook()

    if not events:
        print(f"\n{col('[AUFNAHME]', 'yellow')} Gestoppt — nichts aufgezeichnet.")
        return

    # Aufbereiten in fester Reihenfolge — jede Stufe entfernt eine Sonderform, damit
    # die naechste sie nicht mehr kennen muss:
    #   1. zwei Bereichs-Ecken  -> ein Screenshot-Ereignis mit Rechteck
    #   2. Phasengrenzen        -> raus aus dem Strom, gemerkt als Schnittstellen
    #   3. haltlose Warte-Marker-> verworfen
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
        return

    print(f"\n{col('╚══ AUFNAHME GESTOPPT ══╝', 'green')} "
          f"{len(events)} Ereignis(se) aufgezeichnet.")

    # Aufgezeichnetes zeigen. Die Phasengrenzen stehen nicht mehr im Strom (sie wurden
    # oben herausgezogen), muessen hier aber sichtbar sein — sonst sieht der Nutzer die
    # Aufteilung erst im Editor und kann sie beim Benennen nicht mehr einordnen.
    _phasen_namen = ["INIT", "LOOP", "END"]
    _schnitt = {g: _phasen_namen[k + 1] for k, g in enumerate(grenzen[:2])}
    if grenzen:
        print(f"\n{col('Aufgezeichnet:', 'bold')} {hint('(Phasen sind markiert)')}")
        print(f"  {col('┌─ ' + (_phasen_namen[0] if grenzen else 'LOOP'), 'magenta')}")
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

    # Sequenzname eingeben
    auto_name = f"Aufnahme_{datetime.now().strftime('%H%M%S')}"
    print(f"\nSequenz-Name (Enter = {col(auto_name, 'cyan')}, {col('cancel', 'yellow')} = verwerfen):")
    try:
        name_input = safe_input("> ").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{col('[VERWORFEN]', 'yellow')}")
        return

    if is_cancel(name_input):
        print(f"{col('[VERWORFEN]', 'yellow')} Aufnahme nicht gespeichert.")
        return

    seq_name = name_input if name_input else auto_name

    # Frage nach total_cycles
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

    # Optionale Beschreibung (hilfreich beim späteren Wiederfinden / Weitergeben)
    print(f"\nBeschreibung (optional, Enter = {col('keine', 'cyan')}):")
    try:
        description = safe_input("> ").strip()
    except (KeyboardInterrupt, EOFError):
        description = ""
    if is_cancel(description):
        description = ""

    # ERST die Punkte, DANN die Schritte — die Reihenfolge ist der Punkt.
    punkt_id_fuer, added = punkte_fuer_events(state, events, seq_name)
    if added:
        save_points(state)

    # SequenceSteps aus den Events bauen — jeder mit Referenz auf seinen Punkt
    steps = schritte_aus_events(events, punkt_id_fuer)
    init_steps, loop_steps, end_steps = phasen_aufteilen(steps, grenzen)

    loop_phase = LoopPhase(name="Loop", steps=loop_steps, repeat=1)
    seq = Sequence(name=seq_name, loop_phases=[loop_phase], total_cycles=total_cycles,
                   description=description, init_steps=init_steps, end_steps=end_steps)

    # Speichern
    ensure_sequences_dir()
    filename = sanitize_filename(seq_name) + ".json"
    filepath = Path(SEQUENCES_DIR) / filename

    if save_sequence_file(seq, filepath):
        with state.lock:
            # Die frisch gebauten Schritte tragen nur Referenzen; Prüf-Pixel und Farbe
            # der Warte-Bedingung sind noch leer. Der Worker löst zwar vor jedem Lauf
            # selbst auf — wer aber direkt nach der Aufnahme in den Editor geht, sähe
            # sonst "(0,0)" statt der Stelle, auf die gewartet wird.
            resolve_point_references(state, seq)
            state.sequences[seq_name] = seq
            state.active_sequence = seq

        cycles_str = "unendlich" if total_cycles == 0 else str(total_cycles)
        saved_msg = ok(f'Sequenz "{seq_name}" gespeichert!')
        print(f"\n{saved_msg}")
        if grenzen:
            print(f"  {len(init_steps)} INIT  |  {len(loop_steps)} LOOP  |  "
                  f"{len(end_steps)} END  |  Zyklen: {cycles_str}")
        else:
            print(f"  {len(steps)} Schritte  |  Zyklen: {cycles_str}")
        if added:
            print(f"  {added} neue(r) Punkt(e) global gespeichert {hint('(im Editor + Studio-Palette nutzbar)')}")
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
    else:
        print(f"\n{err('Sequenz konnte nicht gespeichert werden!')}")


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
