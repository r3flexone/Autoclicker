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
    RecordEvent, REC_CLICK, REC_KEY, REC_SCROLL, REC_WAIT_COLOR,
)
from ..winapi import (
    install_mouse_hook, remove_mouse_hook, install_keyboard_hook, remove_keyboard_hook,
    WHEEL_DELTA,
)
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
    """Erstellt den Mausrad-Callback. `delta` ist die rohe Windows-Distanz."""
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
    """
    with state.lock:
        if not state.recording_active:
            print(f"\n{hint('Keine Aufnahme aktiv — CTRL+ALT+J startet eine.')}")
            return
        pausiert = state.recording_paused
    if pausiert:
        print(f"\n{hint('Aufnahme pausiert — CTRL+ALT+H setzt sie fort.')}")
        return

    _anhaengen(state, RecordEvent(REC_WAIT_COLOR, time.monotonic()))


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

    if install_mouse_hook(_on_click_factory(state), _on_wheel_factory(state)):
        # Die Tastatur ist die Kür: klappt sie nicht, laeuft die Aufnahme trotzdem —
        # nur eben ohne Tastendrücke. Umgekehrt waere eine Aufnahme ohne Klicks sinnlos.
        tasten = install_keyboard_hook(_on_key_factory(state))
        print(f"\n{col('╔══ AUFNAHME GESTARTET ══╗', 'red')}")
        print("  Klicke die gewünschten Positionen im Spiel.")
        print(f"  Aufgezeichnet: Linksklick, Mausrad{', Tastendruck' if tasten else ''}")
        print(f"  Auf Farbe warten: {col('CTRL+ALT+M', 'yellow')} "
              f"{hint('(drücken, sobald du anfängst zu warten)')}")
        print(hint("                    Dein NÄCHSTER Klick wartet dann erst auf die"))
        print(hint("                    Farbe, die er beim Klicken vorfindet. Die Maus"))
        print(hint("                    darf beim Drücken irgendwo stehen."))
        print(f"  Zurücknehmen:     {col('CTRL+ALT+U', 'yellow')} (letztes Ereignis verwerfen)")
        print(f"  Pausieren:        {col('CTRL+ALT+H', 'yellow')} (navigieren ohne aufzuzeichnen)")
        print(f"  Stoppen:          {col('CTRL+ALT+J', 'yellow')} erneut drücken")
        if not tasten:
            print(f"  {warn('Tastatur-Hook nicht installierbar — Tastendrücke fehlen.')}")
        else:
            print(hint("  Tasten mit CTRL oder ALT werden nicht aufgezeichnet —"))
            print(hint("  dort liegen die Hotkeys der App."))
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
    """
    nach_stelle: dict[tuple[int, int], int] = {}
    punkt_id_fuer: dict[int, int] = {}
    neu = 0
    with state.lock:
        for p in state.points:
            nach_stelle.setdefault((p.x, p.y), p.id)
        for i, ev in enumerate(events):
            if ev.kind in (REC_KEY, REC_WAIT_COLOR):
                continue
            treffer = nach_stelle.get((ev.x, ev.y))
            if treffer is not None:
                punkt_id_fuer[i] = treffer
                continue
            pid = get_next_point_id(state)
            state.points.append(
                ClickPoint(ev.x, ev.y, f"{seq_name} {i + 1}", pid, color=ev.color,
                           source=f"Aufnahme '{seq_name}'")
            )
            nach_stelle[(ev.x, ev.y)] = pid
            punkt_id_fuer[i] = pid
            neu += 1
    return punkt_id_fuer, neu


def marker_pruefen(events: list) -> tuple[list, int]:
    """Wirft Warte-Marker weg, die sich an nichts hängen können.

    Ein Marker braucht einen Klick (oder ein Scroll) nach sich — von dem holt er
    Stelle und Farbe. Folgt ein Tastendruck oder gar nichts mehr, gibt es nichts zu
    warten; der Marker wird verworfen statt stillschweigend zu verschwinden.

    Zwei Marker hintereinander sind derselbe Wunsch, zweimal geäußert: der erste
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

    Erwartet bereits durch `marker_pruefen()` bereinigte Ereignisse.
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

    # Ein Marker braucht einen Klick nach sich, von dem er Stelle und Farbe holt.
    events, verworfen = marker_pruefen(events)
    if verworfen:
        print(f"\n{warn(f'{verworfen} Warte-Marker verworfen — danach kam kein Klick.')}")
        print(hint("       Ein Marker wartet auf die Farbe DES Klicks, der ihm folgt."))
        if not events:
            print(f"{col('[AUFNAHME]', 'yellow')} Nichts Verwertbares übrig.")
            return

    print(f"\n{col('╚══ AUFNAHME GESTOPPT ══╝', 'green')} "
          f"{len(events)} Ereignis(se) aufgezeichnet.")

    # Aufgezeichnetes zeigen
    print(f"\n{col('Aufgezeichnet:', 'bold')}")
    fast_clicks = 0
    for i, ev in enumerate(events):
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

    loop_phase = LoopPhase(name="Loop", steps=steps, repeat=1)
    seq = Sequence(name=seq_name, loop_phases=[loop_phase], total_cycles=total_cycles,
                   description=description)

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
        print(f"  {len(steps)} Schritte  |  Zyklen: {cycles_str}")
        if added:
            print(f"  {added} neue(r) Punkt(e) global gespeichert {hint('(im Editor + Node-Palette nutzbar)')}")
        print(f"  Starten:    {col('CTRL+ALT+S', 'yellow')}")
        print(f"  Bearbeiten: {col('CTRL+ALT+E', 'yellow')}")
        print(hint("  Tipp: Im Editor wandelt 'color <Nr>' einen Klick in einen"))
        print(hint("        Farb-Trigger um (nutzt die aufgenommene Farbe),"))
        print(hint("        'noclick <Nr>' macht reines Warten daraus."))
        if any(e.kind == REC_WAIT_COLOR for e in events):
            print(hint("        'colorgone <Nr>' dreht einen Warte-Marker um:"))
            print(hint("        warten bis die Farbe WEG ist statt bis sie da ist."))
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
