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
    get_cursor_pos, get_screen_pixel, WHEEL_DELTA,
)
from ..utils import safe_input, col, ok, err, warn, is_cancel, hint, describe_color
from ..persistence.sequences import (
    save_sequence_file, ensure_sequences_dir, save_points, get_next_point_id,
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


def _melde(ereignis: RecordEvent, idx: int) -> None:
    """Eine Zeile pro aufgezeichnetem Ereignis — der Nutzer sieht nur die Konsole."""
    farbe = f" {describe_color(ereignis.color)}" if ereignis.color else ""
    print(f"  {col('[REC]', 'red')} #{idx} {ereignis}{farbe}")


def farben_nachlesen(state: AutoClickerState) -> None:
    """Liest die Farbe offener Warte-Marker JETZT nach.

    Der Marker wird gesetzt, BEVOR das Erwartete da ist — genau das ist der Sinn:
    "ab hier warten". Zu diesem Zeitpunkt liegt an der Stelle aber noch der
    Hintergrund, und auf den zu warten wäre ab der ersten Sekunde erfüllt.

    Deshalb wird die Farbe nicht beim Drücken gelesen, sondern beim nächsten
    Ereignis: klickt der Nutzer weiter, ist ja da, worauf er gewartet hat. Die
    Position steht seit dem Drücken fest, die Maus darf inzwischen weiterziehen.

    Nebeneffekt, der uns entgegenkommt: die Maus hängt beim Nachlesen meist nicht
    mehr über der Stelle. Ein Hover-Effekt des Spiels landet damit NICHT in der
    Bedingung — beim Abspielen steht der Zeiger dort ja auch nicht.
    """
    with state.lock:
        offen = [e for e in state.recording_events
                 if e.kind == REC_WAIT_COLOR and e.color is None]
    for ereignis in offen:
        farbe = get_screen_pixel(ereignis.x, ereignis.y)
        with state.lock:
            ereignis.color = farbe
        if farbe is not None:
            print(f"  {col('[REC]', 'red')} Warte-Marker bei "
                  f"({ereignis.x}, {ereignis.y}): {describe_color(farbe)}")


def _anhaengen(state: AutoClickerState, ereignis: RecordEvent) -> bool:
    """Hängt ein Ereignis an die Aufnahme. False = Aufnahme aus oder pausiert.

    Mausrad-Ereignisse werden mit dem direkt davor verschmolzen (siehe
    _SCROLL_MERGE_GAP); dann wird die vorhandene Zeile aktualisiert statt einer neuen.
    """
    with state.lock:
        if not state.recording_active or state.recording_paused:
            return False
        vorherige = state.recording_events[-1] if state.recording_events else None
        if (ereignis.kind == REC_SCROLL and vorherige is not None
                and vorherige.kind == REC_SCROLL
                and ereignis.t - vorherige.t <= _SCROLL_MERGE_GAP):
            vorherige.scroll += ereignis.scroll
            vorherige.t = ereignis.t
            idx, ereignis = len(state.recording_events), vorherige
        else:
            state.recording_events.append(ereignis)
            idx = len(state.recording_events)
    # Erst melden, dann nachlesen: die Farbzeile gehoert unter das Ereignis, das sie
    # ausgeloest hat. Ein Marker liest sich nicht selbst nach - er ist ja der Anlass.
    _melde(ereignis, idx)
    if ereignis.kind != REC_WAIT_COLOR:
        farben_nachlesen(state)
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
    """Setzt an der Mausposition einen Warte-Marker (CTRL+ALT+M).

    Gedrückt wird, BEVOR das Erwartete da ist: "bis hierher lief es normal, ab hier
    warte ich". Die Zeit davor bleibt deshalb als echte Wartezeit stehen — nur die
    Zeit DANACH ersetzt die Farb-Bedingung.

    Die Farbe kommt später (siehe `farben_nachlesen`); jetzt stünde hier ja noch der
    Hintergrund.
    """
    with state.lock:
        if not state.recording_active:
            print(f"\n{hint('Keine Aufnahme aktiv — CTRL+ALT+J startet eine.')}")
            return
        pausiert = state.recording_paused
    if pausiert:
        print(f"\n{hint('Aufnahme pausiert — CTRL+ALT+H setzt sie fort.')}")
        return

    x, y = get_cursor_pos()
    _anhaengen(state, RecordEvent(REC_WAIT_COLOR, time.monotonic(), x, y))


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
              f"{hint('(Maus auf die Stelle, BEVOR dort etwas kommt)')}")
        print(hint("                    Ab da wartet die Sequenz, statt stur die Zeit"))
        print(hint("                    abzusitzen. Die Farbe wird beim nächsten Klick"))
        print(hint("                    nachgelesen — dann ist ja da, worauf du wartest."))
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

    Ein Warte-Marker teilt sich einen Punkt nur bei GLEICHER FARBE. Die erwartete
    Farbe kommt aus dem Punkt (`WaitCondition` leitet sie ab); an derselben Stelle auf
    etwas anderes zu warten ist deshalb ein eigener Punkt, sonst überschriebe der
    zweite Marker die Bedingung des ersten.
    """
    nach_stelle: dict[tuple[int, int], int] = {}          # Klick / Scroll: nur die Stelle
    nach_stelle_farbe: dict[tuple, int] = {}              # Warte-Marker: Stelle + Farbe
    punkt_id_fuer: dict[int, int] = {}
    neu = 0

    def merken(x, y, color, pid):
        nach_stelle.setdefault((x, y), pid)
        if color:
            nach_stelle_farbe.setdefault((x, y, tuple(color)), pid)

    with state.lock:
        for p in state.points:
            merken(p.x, p.y, p.color, p.id)
        for i, ev in enumerate(events):
            if ev.kind == REC_KEY:
                continue
            if ev.kind == REC_WAIT_COLOR:
                treffer = nach_stelle_farbe.get((ev.x, ev.y, tuple(ev.color)))
            else:
                treffer = nach_stelle.get((ev.x, ev.y))
            if treffer is not None:
                punkt_id_fuer[i] = treffer
                continue
            pid = get_next_point_id(state)
            state.points.append(
                ClickPoint(ev.x, ev.y, f"{seq_name} {i + 1}", pid, color=ev.color,
                           source=f"Aufnahme '{seq_name}'")
            )
            merken(ev.x, ev.y, ev.color, pid)
            punkt_id_fuer[i] = pid
            neu += 1
    return punkt_id_fuer, neu


def schritte_aus_events(events: list, punkt_id_fuer: dict) -> list:
    """Baut die SequenceSteps. Jedes Ereignis wird genau ein Schritt.

    Die Wartezeit eines Schritts ist der Abstand zum vorherigen Ereignis — mit einer
    Ausnahme: **der Schritt NACH einem Warte-Marker bekommt keine.**

    Denn genau diese Spanne — vom Drücken des Markers bis zur nächsten Handlung — ist
    das Warten, das die Farb-Bedingung ersetzt. Bliebe sie stehen, würde die Sequenz
    erst auf die Farbe warten UND danach nochmal die volle Zeit schlafen.

    Der Marker selbst behält seine Wartezeit: bis zum Drücken lief ja normal etwas ab.
    """
    steps = []
    for i, ev in enumerate(events):
        delay = 0.0 if i == 0 else round(ev.t - events[i - 1].t, 2)
        if i > 0 and events[i - 1].kind == REC_WAIT_COLOR:
            delay = 0.0
        pid = punkt_id_fuer.get(i)

        if ev.kind == REC_KEY:
            steps.append(SequenceStep(delay_before=delay, key_press=ev.key))
        elif ev.kind == REC_SCROLL:
            steps.append(SequenceStep(x=ev.x, y=ev.y, delay_before=delay, scroll=ev.scroll,
                                      point_id=pid, recorded_color=ev.color))
        elif ev.kind == REC_WAIT_COLOR:
            # wait_only: der Marker wartet nur, er klickt nichts. Deshalb hat der
            # SCHRITT keine point_id (er zeigt nirgendwohin) — die Referenz sitzt an
            # der Bedingung, die den Prüf-Pixel und die erwartete Farbe daraus ableitet.
            steps.append(SequenceStep(delay_before=delay, wait_only=True,
                                      wait_condition=WaitCondition(point_id=pid)))
        else:
            steps.append(SequenceStep(x=ev.x, y=ev.y, delay_before=delay,
                                      name=f"Klick {i + 1}", recorded_color=ev.color,
                                      point_id=pid))
    return steps


def stop_recording(state: AutoClickerState) -> None:
    """Stoppt die Aufnahme und baut eine Sequenz aus den Ereignissen."""
    # Ein Marker als LETZTES Ereignis hat noch keine Farbe — nach ihm kam ja nichts
    # mehr. Jetzt ist der letzte Moment, in dem der Bildschirm noch das zeigt, worauf
    # gewartet wurde. Muss VOR dem Abraeumen laufen, solange die Liste noch steht.
    farben_nachlesen(state)

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

    # Marker ohne Farbe koennen keine Bedingung tragen (der Pixel war nicht lesbar).
    # Lieber raus als ein Warte-Schritt, der auf Schwarz wartet und nie weiterkommt.
    ohne_farbe = [e for e in events if e.kind == REC_WAIT_COLOR and e.color is None]
    if ohne_farbe:
        # Identitaet, nicht Gleichheit: RecordEvent ist eine Dataclass, und zwei Marker
        # mit denselben Werten wuerden sich sonst gegenseitig mitloeschen.
        verworfen = {id(e) for e in ohne_farbe}
        events = [e for e in events if id(e) not in verworfen]
        print(f"\n{warn(f'{len(ohne_farbe)} Warte-Marker ohne lesbare Farbe verworfen.')}")
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
                delay_str = col("wartet auf Farbe", "cyan")
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
