"""Punkte kalibrieren, indem man sie der Reihe nach von Hand anklickt.

Der Unterschied zu `walk_points`: dort springt der Zeiger hin, ohne zu
klicken — und ein Punkt im dritten Untermenü ist gar nicht sichtbar, solange
die ersten beiden Klicks fehlen. Hier geht jeder Klick ans Spiel und öffnet
damit die Stelle, an der der nächste Punkt liegt.

**Die Runde arbeitet auf PUNKTEN, nicht auf einer Sequenz.** Von der Sequenz
kommt genau eine Sache: die Reihenfolge, in der ihre Punkte geklickt werden —
denn in ihr öffnet ein Klick die Stelle für den nächsten. Danach ist sie
uninteressant: die Sequenzdatei wird nicht angefasst, nicht geladen, nicht
aktiviert. Wartezeiten, Bedingungen, ELSE, Scans und die Reihenfolge bleiben,
wie sie sind; geschrieben wird `x`, `y` und (wenn der Punkt eine hatte) die
Farbe im Punkt-Pool der jeweiligen `sequence.json`.

**Geschrieben wird erst am Schluss, und nur auf ausdrückliches Übernehmen.**
Bis dahin liegen die neuen Stellen in `state.reclick_set` und die Punkte
sind unverändert — auch im Speicher. Das ist der Unterschied zwischen einer
abgebrochenen Runde und einer halb überschriebenen `sequence.json`: wer das
Fenster zumacht, das Programm beendet oder verwirft, verliert die Runde und
nichts sonst.

Was sie nicht erreicht, sagt sie am Ende: beobachtete Pixel, ELSE-Klicks und
Rad-Schritte kommen in einem normalen Durchlauf nicht vor; dafür bleibt
`walk`. Slots und Scan-Regionen repariert `repair` bzw. `fix`.

Sie läuft aus dem Maus-Hook, nicht aus der Konsole — deshalb schliesst der
Punkte-Editor beim Start, und alles Weitere sind globale Hotkeys.
"""

import threading
import time
from pathlib import Path

from ..models import (
    AutoClickerState,
    BLOCK_CLICK,
    BLOCK_WAIT_CLICK,
    Sequence,
    block_type,
)
from ..config import RECLICK_STATUS_FILE
from ..utils import (col, err, hint, info, ok, describe_color, warn,
                     atomic_write, compact_json)
from ..winapi import (
    get_client_rect_by_title,
    install_mouse_hook,
    remove_mouse_hook,
    set_cursor_pos,
)
from ._klickfenster import geklicktes_fenster

# Die beiden Block-Typen, die wirklich klicken. `block_type()` ist die eine
# Klassifikation im Projekt — eine zweite Liste hier wäre die Stelle, an der ein
# neuer Typ vergessen wird.
KLICK_BLOECKE = (BLOCK_CLICK, BLOCK_WAIT_CLICK)

# Wie lange nach einem Klick gewartet wird, bevor der Zeiger auf die nächste
# Stelle springt. **Sofort springen geht nicht**: der Hook meldet den DRUCK, das
# Loslassen kommt erst danach — dazwischen die Maus wegzuziehen macht aus dem
# Klick ein Ziehen. Ein Viertelsekunde reicht dem Loslassen und ist kurz genug,
# dass der Zeiger schon dasteht, wenn man den nächsten Punkt ansieht.
SPRUNG_VERZOEGERUNG = 0.25

# Wie weit ein Klick von der gespeicherten Stelle abweichen darf und trotzdem als
# „bestätigt" gilt. Der Zeiger wird von uns dorthin gesetzt, und trotzdem kommt
# der Klick gelegentlich einen Pixel daneben zurück (DPI-Skalierung, ein Hauch
# Mausbewegung). Ohne die Toleranz schriebe jede Bestätigung den Punkt um einen
# Pixel um und zählte als Änderung — Rauschen in genau der Liste, die sagen soll,
# was sich geändert hat. Absichtlich winzig: eine gewollte Korrektur ist nie 2 px.
PASST_TOLERANZ = 2

# Welche fremden Fenster schon gemeldet wurden — einmal je Titel. Ohne die Sperre
# stünde bei jedem Klick in einem Menü dieselbe Zeile.
_gemeldete_fenster: set = set()

# Der Rückkanal zum Studio-Fenster: dieselbe Bauart wie `.aufnahme.json` bei der
# Aufnahme und `.lauf.json` beim Lauf. Kein Log — die Datei beschreibt den Stand
# JETZT und wird überschrieben.
_STATUS_DATEI = Path(RECLICK_STATUS_FILE)


def _punkt_json(point) -> dict:
    """Ein Punkt so, wie ihn die Anzeige braucht."""
    if point is None:
        return {}
    return {"id": point.id, "name": point.name or f"Punkt {point.id}",
            "x": point.x, "y": point.y,
            "farbe": list(point.color) if point.color else None}


def _status_daten(state: AutoClickerState) -> dict:
    """Der Stand der Runde als reine Daten — unter Lock gelesen, wie überall."""
    with state.lock:
        active = state.reclick_active
        ids = list(state.reclick_points)
        i = state.reclick_index
        verlauf = list(state.reclick_history)
        gesetzt = {entry[0]: entry for entry in state.reclick_set}
        seq = state.reclick_sequence
        pool = list(seq.points if seq is not None else state.points)
        data = {"aktiv": active, "pausiert": state.reclick_paused and active,
                 "name": state.reclick_name, "ziel": state.reclick_target,
                 "sonstige": state.reclick_other}
    points = {p.id: p for p in pool}
    data["index"] = i
    data["gesamt"] = len(ids)
    data["punkt"] = _punkt_json(points.get(ids[i])) if i < len(ids) else {}
    # Der Verlauf ist das, was die Konsole Zeile für Zeile ausgibt — im Fenster
    # steht er als Liste, damit man ihn beim Klicken überfliegen kann.
    data["verlauf"] = [
        {"id": pid, "art": kind,
         "name": (points[pid].name or f"Punkt {pid}") if pid in points else f"Punkt {pid}",
         "alt": list(gesetzt[pid][1]) if pid in gesetzt else None,
         "neu": list(gesetzt[pid][2]) if pid in gesetzt else None}
        for pid, kind in verlauf]
    data["geaendert"] = len(gesetzt)
    data["stand"] = time.time()
    return data


def _status_schreiben(state: AutoClickerState) -> None:
    """Überschreibt den Live-Stand; Fehler dürfen die Runde nie stören.

    **Das ist bewusst ein Schreibvorgang aus dem Hook heraus**, und der Satz in
    CLAUDE.md („im Hook nicht auf Platte schreiben") meint etwas anderes: das
    vollständige Speichern am Ende (Sequenz plus Punkte serialisieren, mehrere
    Dateien). Hier geht eine knappe JSON-Zeile über `atomic_write` raus —
    dieselbe Grössenordnung, die die Aufnahme bei JEDEM aufgezeichneten Klick
    schreibt (`_status_schreiben` in `sequence_recorder.py`). Ohne den Schreiber
    sähe das Fenster von der Runde nichts als „läuft".
    """
    try:
        atomic_write(_STATUS_DATEI, compact_json(_status_daten(state)))
    except (OSError, TypeError, ValueError, AttributeError):
        pass



def klickpunkte(seq: Sequence) -> tuple[list, list]:
    """(Punkt-IDs zum Nachklicken, IDs die eine Runde nicht erreicht).

    Reihenfolge des Laufs (INIT, Loop-Phasen, END), denn genau so öffnet ein
    Klick die Stelle für den nächsten. Jeder Punkt kommt einmal vor.

    Der zweite Wert sind die Stellen, an denen in einem normalen Durchlauf
    niemand klickt — sie zu verschweigen hiesse, die Sequenz für repariert zu halten.
    """
    schritte = list(seq.init_steps)
    for phase in seq.loop_phases:
        schritte += list(phase.steps)
    schritte += list(seq.end_steps)

    klicks, sonstige = [], []

    def merke(target: list, punkt_id) -> None:
        if punkt_id is not None and punkt_id not in klicks and punkt_id not in sonstige:
            target.append(punkt_id)

    # **Erst alle Klicks, dann der Rest.** In einem Durchgang landete eine
    # Stelle, die ein früher Schritt nur BEOBACHTET und ein späterer klickt,
    # unter „unerreichbar" — und war damit aus der Runde draussen, obwohl man
    # sie gleich anklicken wird. Wer beides ist, ist ein Klick.
    for step in schritte:
        if block_type(step) in KLICK_BLOECKE and step.scroll is None:
            merke(klicks, step.point_id)
    for step in schritte:
        merke(sonstige, step.point_id)
        for bedingung in (step.wait_condition, step.verify_condition, step.else_config):
            if bedingung is not None:
                merke(sonstige, bedingung.point_id)
    return klicks, sonstige


def nachklick_laeuft(state: AutoClickerState) -> bool:
    with state.lock:
        return state.reclick_active


def ruesten(state: AutoClickerState, seq: Sequence = None) -> tuple:
    """Prüft die Lage und legt die Runde in den State. `(ids, sonstige)` oder `None`.

    `seq` liefert **nur die Reihenfolge**. Ohne Angabe wird die geladene Sequenz
    genommen — der Weg aus dem Punkte-Menü. Das Studio reicht ihre eigene herein,
    ohne dass die geladene dadurch wechselt: welche Sequenz der Hauptprozess
    gerade scharf hat, geht eine Kalibrier-Runde nichts an.

    Getrennt vom Hook, weil alles daran messbar ist ausser dem Hook selbst: was
    geklickt werden kann, in welcher Reihenfolge, und was eine Runde nicht
    erreicht. Der Hook ist die Plattform-Grenze und bleibt in `start_nachklick`.
    """
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return None
        if state.recording_active:
            print(f"\n{err('Aufnahme läuft')} {hint('(CTRL+ALT+J beendet sie)')}")
            return None
        # Ein gestellter Countdown ist ein Start mit Verzögerung — mitten in der
        # Runde wäre er genau der Zeitablauf, der hier nichts verloren hat. Er
        # wird abgelehnt statt still abgeräumt: wer ihn gestellt hat, soll es
        # entscheiden.
        if state.countdown_active:
            print(f"\n{err('Ein Countdown läuft — er würde mitten in die Runde starten')} "
                  f"{hint('(CTRL+ALT+S bricht ihn ab)')}")
            return None
        if state.reclick_active:
            return None
        if seq is None:
            seq = state.active_sequence
        points = {p.id: p for p in seq.points} if seq is not None else {}

    if seq is None:
        print(f"\n{err('Keine Sequenz geladen.')} "
              f"{hint('CTRL+ALT+L lädt eine — die Reihenfolge kommt aus ihr.')}")
        return None

    ids, sonstige = klickpunkte(seq)
    # Ein Punkt, den es nicht mehr gibt, ist kein Ziel — der Schritt zeigt ins
    # Leere und wird beim Lauf ohnehin übersprungen.
    ids = [i for i in ids if i in points]
    if not ids:
        print(f"\n{info('Diese Sequenz hat keinen einzigen Klick-Schritt mit Punkt.')}")
        return None

    target = _zielfenster(state)
    with state.lock:
        state.reclick_active = True
        state.reclick_paused = False
        state.reclick_points = ids
        state.reclick_index = 0
        state.reclick_set = []
        state.reclick_history = []
        state.reclick_other = len(sonstige)
        state.reclick_target = target
        state.reclick_name = seq.name
        state.reclick_sequence = seq
    _gemeldete_fenster.clear()
    _status_schreiben(state)
    return ids, sonstige


def _zielfenster(state: AutoClickerState) -> str:
    """Der Fenstertitel, in dem ein Klick als Punkt zählt — "" heisst kein Filter.

    **Warum es den Filter gibt.** Der Maus-Hook ist systemweit: ohne ihn zählt
    jeder Klick, auch der auf das Studio-Fenster, die Konsole oder ein
    Schliessen-Kreuz — und dessen Stelle landet im Punkt. Genau so sind in einer
    echten Runde drei Punkte auf Fensterdekoration gewandert (ein Punkt auf
    (3030, 16), also die Titelleiste), und gespeichert wurde es beim Beenden.

    Gefiltert wird nach `window_focus_title` und **unabhängig von**
    `window_focus_check`: das Flag entscheidet, wie sich der *Worker* bei
    verlorenem Fokus verhält. Hier geht es um etwas anderes — welcher Klick
    überhaupt gemeint ist.

    Gibt es das Fenster gerade nicht, wird nicht gefiltert. Ein Filter, der alles
    wegwirft, sähe aus wie ein kaputter Hook; lieber sagt die Runde, dass sie
    jeden Klick nimmt.
    """
    titel = (getattr(state.config, "window_focus_title", "") or "").strip()
    if not titel:
        return ""
    try:
        found = get_client_rect_by_title(titel) is not None
    except Exception:
        found = False
    if not found:
        print(f"  {warn(f'Fenster „{titel}“ nicht gefunden')} "
              f"{hint('— es zählt JEDER Klick, auch der auf ein anderes Fenster.')}")
        return ""
    return titel


def _im_zielfenster(target: str, x: int, y: int) -> bool:
    """True, wenn der Klick im Zielfenster passiert ist (oder nicht gefiltert wird).

    Welches Fenster den Klick bekommen hat, sagt `geklicktes_fenster()` — das
    Fenster UNTER dem Zeiger, nicht der Vordergrund; die Begründung steht dort,
    denn die Aufnahme stellt dieselbe Frage.

    Mehrere Fenster desselben Spiels sind ausdrücklich in Ordnung: geprüft wird
    der Titel, und drei Instanzen tragen denselben. Welche davon gemeint ist,
    entscheidet der Nutzer mit dem Klick.
    """
    if not target:
        return True
    fenster = geklicktes_fenster(x, y)
    if not fenster:
        # Lässt sich weder Fenster noch Vordergrund bestimmen, gilt der Klick.
        # Lieber ein Punkt zu viel als eine Runde, die stumm nichts tut.
        return True
    return target.casefold() in fenster.casefold()


def start_nachklick(state: AutoClickerState, seq: Sequence = None) -> bool:
    """Startet die Runde samt Maus-Hook. False = konnte nicht starten (mit Meldung)."""
    geruestet = ruesten(state, seq)
    if geruestet is None:
        return False
    ids, sonstige = geruestet

    if not install_mouse_hook(_on_click_factory(state), None):
        with state.lock:
            state.reclick_active = False
            state.reclick_points = []
        print(f"\n{err('Maus-Hook konnte nicht installiert werden!')}")
        print("  Mögliche Ursache: Administratorrechte erforderlich.")
        return False

    with state.lock:
        target, name = state.reclick_target, state.reclick_name
    _banner(name, len(ids), target, sonstige)
    _zeige_aktuellen(state)
    return True


# Die vier Griffe während der Runde. Als Tabelle und nicht als fünf Fliesstext-
# Zeilen: was man während des Klickens nachschlägt, muss man FINDEN, und ein
# Absatz zwingt zum Lesen von vorn. Dieselbe Liste steht im Studio.
TASTEN = (
    ("CTRL+ALT+K", "überspringen", "Punkt bleibt, wo er ist"),
    ("CTRL+ALT+U", "zurück",       "einen Punkt zurück, noch mal"),
    ("CTRL+ALT+H", "pausieren",    "navigieren, ohne einen Punkt zu verbrauchen"),
    ("CTRL+ALT+J", "übernehmen",   "fertig — JETZT werden die Punkte geschrieben"),
)


def _banner(name: str, count: int, target: str, sonstige: list) -> None:
    """Was die Runde tut, was sie nicht tut, und womit man sie bedient."""
    print(f"\n{col('╔══ PUNKTE NACHKLICKEN ══╗', 'cyan')}")
    print(f"  {count} Punkt(e) aus „{name}“, in der Reihenfolge des Laufs.")
    print(f"  {col('So geht es:', 'cyan')} der Zeiger steht jedes Mal schon auf der "
          "gespeicherten")
    print("  Stelle. Stimmt sie noch — klicken. Stimmt sie nicht — hinfahren und "
          "dort klicken.")
    if target:
        print(f"  Gezählt wird nur, was in {col(target, 'cyan')} geklickt wird; in "
              "jedem anderen")
        print("  Fenster kannst du klicken, ohne einen Punkt zu verbrauchen.")
    print()
    for key, was, warum in TASTEN:
        print(f"    {col(key.ljust(11), 'yellow')} {was.ljust(13)}"
              f"{hint(warum)}")
    print()
    # **Der wichtigste Satz steht allein.** Alles bleibt in der Schwebe, bis
    # jemand übernimmt — wer das nicht weiss, hält eine abgebrochene Runde für
    # gespeichert oder umgekehrt.
    print(f"  {warn('Nichts wird geschrieben, bis du übernimmst')} "
          f"({col('CTRL+ALT+J', 'yellow')}).")
    print("  Studio-Fenster zu, Programm aus oder „Verwerfen“ im Studio = die "
          "Runde ist")
    print("  weg und sequence.json bleibt, wie sie war.")
    print(hint("  Es läuft nichts von selbst: kein Zeitablauf, keine Wartezeit, "
               "kein Scan."))
    if sonstige:
        print(f"  {info(f'{len(sonstige)} Stelle(n) erreicht die Runde nicht')} "
              f"{hint('(beobachtete Pixel, ELSE, Rad) — dafür bleibt walk.')}")


def stop_nachklick(state: AutoClickerState, reason: str = "beendet",
                   apply_config: bool = True) -> None:
    """Beendet die Runde und schreibt das Ergebnis — oder wirft es weg.

    **Erst hier wird überhaupt etwas geändert.** Während der Runde stehen die
    neuen Stellen in `reclick_set`; die Punkte selbst sind unangetastet,
    auch im Speicher. `uebernehmen=False` heisst deshalb schlicht: Liste weg,
    fertig — es gibt nichts zurückzudrehen.

    Das ist der Unterschied zwischen einer abgebrochenen Runde und einer halb
    überschriebenen `sequence.json`. Vorher schrieb jeder Ausgang, auch das
    Beenden des Programms: in einer echten Runde landeten so drei Klicks auf
    Fensterdekoration dauerhaft in den Punkten.
    """
    # **Der Abschluss wird eingesammelt, bevor die Listen geleert werden.**
    # Danach ist der Verlauf weg, und das Fenster zeigte eine leere Runde —
    # ausgerechnet in dem Moment, in dem man nachsieht, was sie ergeben hat.
    # Dieselbe Regel wie `status.finish_run()`: die Zusammenfassung bleibt stehen.
    abschluss = _status_daten(state) if nachklick_laeuft(state) else None
    with state.lock:
        if not state.reclick_active:
            return
        state.reclick_active = False
        state.reclick_paused = False
        gesetzt = list(state.reclick_set)
        offen = len(state.reclick_points) - state.reclick_index
        ziel_sequence = state.reclick_sequence
        points = {p.id: p for p in (
            ziel_sequence.points if ziel_sequence is not None else state.points)}
        if apply_config:
            for punkt_id, _alt, new, neue_farbe in gesetzt:
                point = points.get(punkt_id)
                if point is None:
                    continue
                point.x, point.y = new
                # Die Farbe gehört zur Position — aber nur, wenn der Punkt vorher
                # eine hatte. Sonst schliche sich ein Farb-Trigger ein, den
                # niemand gesetzt hat. Dieselbe Regel wie in `walk_points`.
                if point.color and neue_farbe:
                    point.color = neue_farbe
        state.reclick_points = []
        state.reclick_index = 0
        state.reclick_set = []
        state.reclick_history = []
        state.reclick_other = 0
        state.reclick_target = ""
        state.reclick_name = ""
        state.reclick_sequence = None
    remove_mouse_hook()
    _gemeldete_fenster.clear()
    # Der abgeschlossene Stand bleibt stehen, statt geloescht zu werden —
    # dieselbe Regel wie bei `status.finish_run()`: sonst ist das Fenster genau
    # in dem Moment leer, in dem man nachsieht, was die Runde ergeben hat.
    if abschluss is not None:
        abschluss.update({"aktiv": False, "pausiert": False, "punkt": {},
                          "grund": reason, "uebernommen": bool(apply_config),
                          "stand": time.time()})
        try:
            atomic_write(_STATUS_DATEI, compact_json(abschluss))
        except (OSError, TypeError, ValueError):
            pass

    # **Geschrieben wird hier, nicht im Hook.** Ein Low-Level-Maus-Hook muss
    # schnell zurückkommen — Windows hängt ihn sonst aus, und dann fehlen
    # Klicks mitten in der Runde. Eine Datei zu schreiben ist meistens schnell,
    # aber „meistens" ist für den Pfad, an dem die ganze Eingabe hängt, zu wenig.
    if gesetzt and apply_config:
        from ..persistence import save_sequence_file, sequence_file
        if ziel_sequence is not None:
            save_sequence_file(ziel_sequence, sequence_file(ziel_sequence.name))

    print(f"\n{col('[NACHKLICK]', 'cyan')} {reason}.")
    if not gesetzt:
        print("  Nichts geändert.")
    elif apply_config:
        print(f"  {ok(f'{len(gesetzt)} Punkt(e) neu gesetzt und gespeichert.')}")
        for punkt_id, altpos, new, _f in gesetzt[:12]:
            print(hint(f"     #{punkt_id}  ({altpos[0]}, {altpos[1]}) → "
                       f"({new[0]}, {new[1]})"))
        if len(gesetzt) > 12:
            print(hint(f"     … und {len(gesetzt) - 12} weitere"))
        print(hint("  Jeder Schritt, der sie benutzt, zieht beim nächsten Lauf mit —"))
        print(hint("  Wartezeiten und Bedingungen sind unverändert."))
    else:
        print(f"  {warn(f'{len(gesetzt)} gesetzte Stelle(n) verworfen')} "
              f"{hint('— sequence.json ist unverändert.')}")
    if offen > 0 and apply_config:
        print(hint(f"  {offen} Punkt(e) standen noch aus — sie blieben, wo sie waren."))


def nachklick_pause(state: AutoClickerState) -> None:
    """Klicks gehen durch, ohne einen Punkt zu setzen — und zurück."""
    with state.lock:
        if not state.reclick_active:
            return
        state.reclick_paused = not state.reclick_paused
        pausiert = state.reclick_paused
    _status_schreiben(state)
    if pausiert:
        print(f"\n{col('[PAUSE]', 'yellow')} Klicks setzen KEINEN Punkt — "
              "navigiere, wie du willst.")
        print(f"  Fortsetzen: {col('CTRL+ALT+H', 'yellow')} erneut drücken")
    else:
        print(f"\n{col('[NACHKLICK]', 'cyan')} Weiter — der nächste Klick setzt wieder.")
        _zeige_aktuellen(state)


def nachklick_ueberspringen(state: AutoClickerState) -> None:
    """Diesen Punkt lassen, wo er ist, und zum nächsten."""
    with state.lock:
        if not state.reclick_active:
            return
        if state.reclick_index >= len(state.reclick_points):
            return
        punkt_id = state.reclick_points[state.reclick_index]
        state.reclick_history.append((punkt_id, "uebersprungen"))
        state.reclick_index += 1
        fertig = state.reclick_index >= len(state.reclick_points)
    print(f"  {col('[ÜBERSPRUNGEN]', 'yellow')} #{punkt_id} bleibt, wo er ist.")
    if fertig:
        stop_nachklick(state, "alle Punkte durch")
    else:
        _zeige_aktuellen(state)


def nachklick_zurueck(state: AutoClickerState) -> None:
    """Einen Punkt zurück — die eben gesetzte Stelle wird wieder vergessen.

    **Zurück heisst zurück.** Nur den Zeiger zurückzusetzen liesse die eben
    erfasste Koordinate auf der Liste stehen; wer sich verklickt hat, hätte sie
    dann weiterhin — und merkt es erst beim Übernehmen. Der Punkt selbst ist
    unverändert (geschrieben wird ja erst am Schluss), es fliegt also nur der
    Eintrag raus.
    """
    with state.lock:
        if not state.reclick_active:
            return
        if state.reclick_index <= 0:
            print(f"  {hint('Schon beim ersten Punkt.')}")
            return
        state.reclick_index -= 1
        # Zurueck heisst zurueck — auch in der Anzeige. Bliebe der
        # Eintrag stehen, zeigte das Fenster einen Punkt als erledigt,
        # den die Runde gleich noch einmal abfragt.
        if state.reclick_history:
            state.reclick_history.pop()
        punkt_id = state.reclick_points[state.reclick_index]
        verworfen = None
        for i, entry in enumerate(state.reclick_set):
            if entry[0] == punkt_id:
                verworfen = state.reclick_set.pop(i)[1]
                break
    if verworfen:
        print(f"  {col('[ZURÜCK]', 'yellow')} #{punkt_id} zählt wieder als "
              f"({verworfen[0]}, {verworfen[1]}).")
    _zeige_aktuellen(state)


def _on_click_factory(state: AutoClickerState):
    """Der Klick-Callback für den Maus-Hook."""
    def _on_click(x: int, y: int, color) -> None:
        _setze_punkt(state, x, y, color)
    return _on_click


def _setze_punkt(state: AutoClickerState, x: int, y: int, color) -> None:
    """Ein Klick im Spiel: die neue Stelle des aktuellen Punktes."""
    with state.lock:
        if not state.reclick_active or state.reclick_paused:
            return
        # **Nur echte Klicks zählen.** Läuft der Worker, sind seine eigenen
        # Klicks für den Hook nicht von einem Handgriff zu unterscheiden — die
        # Runde raste dann von selbst durch die Punkte und schriebe überall die
        # Stellen hin, die der Lauf gerade anfährt. `handle_toggle()` lässt es
        # gar nicht erst so weit kommen; das hier ist die zweite Tür.
        if state.is_running:
            return
        if state.reclick_index >= len(state.reclick_points):
            return
        target = state.reclick_target
        punkt_id = state.reclick_points[state.reclick_index]
        seq = state.reclick_sequence
        pool = seq.points if seq is not None else state.points
        point = next((p for p in pool if p.id == punkt_id), None)

    # **Ein Klick ausserhalb des Spiels ist kein Punkt.** Ausserhalb des Locks,
    # weil `is_target_window_active()` das Betriebssystem fragt und der Hook
    # schnell zurück muss.
    if not _im_zielfenster(target, x, y):
        fremd = geklicktes_fenster(x, y) or "?"
        if fremd not in _gemeldete_fenster:
            _gemeldete_fenster.add(fremd)
            print(f"\n  {warn('[IGNORIERT]')} Klick in „{fremd}“ — Punkte werden "
                  f"nur in „{target}“ gesetzt.")
            print(hint("     Fenster wechseln und weiterklicken; der Punkt ist "
                       "noch derselbe."))
        return

    with state.lock:
        # Zwischen den beiden Locks kann die Runde beendet oder weitergerückt
        # sein (CTRL+ALT+K, CTRL+ALT+J) — dann gilt dieser Klick nicht mehr.
        if (not state.reclick_active
                or state.reclick_index >= len(state.reclick_points)
                or state.reclick_points[state.reclick_index] != punkt_id):
            return
        if point is None:
            state.reclick_history.append((punkt_id, "fehlt"))
            state.reclick_index += 1
            fertig = state.reclick_index >= len(state.reclick_points)
            name, old, gleich = "", None, False
        else:
            # **Der Punkt wird NICHT angefasst.** Die neue Stelle kommt auf die
            # Liste; geschrieben wird sie erst beim Übernehmen. Damit ist ein
            # Abbruch wirklich ein Abbruch — es gibt nichts zurückzudrehen.
            old = (point.x, point.y)
            # Ein Pixel Abweichung ist keine Korrektur — siehe PASST_TOLERANZ.
            gleich = (abs(old[0] - x) <= PASST_TOLERANZ
                      and abs(old[1] - y) <= PASST_TOLERANZ)
            name = point.name or f"Punkt {point.id}"
            if not gleich:
                state.reclick_set = [
                    e for e in state.reclick_set if e[0] != punkt_id]
                state.reclick_set.append((punkt_id, old, (x, y), color))
            state.reclick_history.append(
                (punkt_id, "passt" if gleich else "gesetzt"))
            state.reclick_index += 1
            fertig = state.reclick_index >= len(state.reclick_points)

    if point is not None:
        color_text = f"  {describe_color(color)}" if point.color and color else ""
        if gleich:
            # Der Normalfall, seit der Zeiger vorher dort steht: hinsehen,
            # klicken, weiter. Deshalb liest es sich als Bestätigung und nicht
            # als „nichts passiert".
            print(f"  {col('[PASST]', 'green')} #{punkt_id} {name} — "
                  f"bestätigt, bleibt wo er ist.{color_text}")
        else:
            print(f"  {col('[GESETZT]', 'green')} #{punkt_id} {name}  "
                  f"({old[0]}, {old[1]}) → ({x}, {y}){color_text}")
    if fertig:
        stop_nachklick(state, "alle Punkte durch")
    else:
        _zeige_aktuellen(state, verzoegert=True)


def _springe(x: int, y: int, verzoegert: bool = False) -> None:
    """Setzt den Zeiger auf eine Stelle — nach einem Klick erst nach kurzer Frist.

    Die Frist ist der ganze Grund, warum das eine eigene Funktion ist: der
    Maus-Hook meldet den DRUCK, das Loslassen kommt erst danach. Sofort zu
    springen machte aus jedem Klick ein Ziehen.
    """
    if not verzoegert:
        set_cursor_pos(x, y)
        return
    zeit = threading.Timer(SPRUNG_VERZOEGERUNG, set_cursor_pos, args=(x, y))
    zeit.daemon = True
    zeit.start()


def _zeige_aktuellen(state: AutoClickerState, verzoegert: bool = False) -> None:
    """Sagt, welcher Punkt als Nächstes dran ist — und fährt ihn an.

    **Der Zeiger steht immer schon auf der gespeicherten Stelle.** Damit ist ein
    Punkt, der noch stimmt, ein einziger Klick: hinsehen, klicken, weiter. Nur
    die, die verrutscht sind, kosten eine Mausbewegung — und das sind nach einem
    Bildschirm-Umbau die wenigsten.

    Vorher sprang er nach einem echten Klick nicht (aus Sorge um Ziehen und
    Tooltips), und dann stand die alte Stelle nur als Zahlenpaar in der Konsole:
    man musste sie suchen, statt sie zu sehen. Die Sorge löst `SPRUNG_VERZOEGERUNG`
    besser als das Nicht-Springen — `verzoegert=True` sagt „der Klick ist gerade
    erst passiert".
    """
    # Jede Bewegung der Runde geht hier durch — also steht hier auch der
    # eine Schreibvorgang fuer das Studio-Fenster.
    _status_schreiben(state)
    with state.lock:
        if not state.reclick_active:
            return
        i, total = state.reclick_index, len(state.reclick_points)
        if i >= total:
            return
        punkt_id = state.reclick_points[i]
        seq = state.reclick_sequence
        pool = seq.points if seq is not None else state.points
        point = next((p for p in pool if p.id == punkt_id), None)
    if point is None:
        return
    color_text = f"  {describe_color(point.color)}" if point.color else ""
    print(f"  {col(f'→ {i + 1}/{total}', 'cyan')}  #{point.id} "
          f"{point.name or '(ohne Name)'}   Zeiger steht auf "
          f"({point.x}, {point.y}){color_text}")
    _springe(point.x, point.y, verzoegert)
