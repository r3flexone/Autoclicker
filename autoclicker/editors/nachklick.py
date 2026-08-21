"""Punkte kalibrieren, indem man die Sequenz einmal von Hand nachklickt.

Der Unterschied zu `walk_points`: dort springt der Zeiger hin, ohne zu
klicken — und ein Punkt im dritten Untermenü ist gar nicht sichtbar, solange
die ersten beiden Klicks fehlen. Hier geht jeder Klick ans Spiel und öffnet
damit die Stelle, an der der nächste Punkt liegt.

Geändert wird nur die Stelle: `x`, `y` und (wenn der Punkt eine hatte) die
Farbe. Wartezeiten, Bedingungen, ELSE, Scans und die Reihenfolge bleiben —
die Runde fasst die Sequenzdatei überhaupt nicht an.

Was sie nicht erreicht, sagt sie am Ende: beobachtete Pixel, ELSE-Klicks und
Rad-Schritte kommen in einem normalen Durchlauf nicht vor; dafür bleibt
`walk`. Slots und Scan-Regionen repariert `repair` bzw. `fix`.

Sie läuft aus dem Maus-Hook, nicht aus der Konsole — deshalb schliesst der
Punkte-Editor beim Start, und alles Weitere sind globale Hotkeys.
"""

from ..models import (
    AutoClickerState,
    BLOCK_CLICK,
    BLOCK_WAIT_CLICK,
    Sequence,
    block_type,
)
from ..utils import col, err, hint, info, describe_color
from ..winapi import install_mouse_hook, remove_mouse_hook, set_cursor_pos

# Die beiden Block-Typen, die wirklich klicken. `block_type()` ist die eine
# Klassifikation im Projekt — eine zweite Liste hier wäre die Stelle, an der ein
# neuer Typ vergessen wird.
KLICK_BLOECKE = (BLOCK_CLICK, BLOCK_WAIT_CLICK)


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

    def merke(ziel: list, punkt_id) -> None:
        if punkt_id is not None and punkt_id not in klicks and punkt_id not in sonstige:
            ziel.append(punkt_id)

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
        return state.nachklick_aktiv


def ruesten(state: AutoClickerState) -> tuple:
    """Prüft die Lage und legt die Runde in den State. `(ids, sonstige)` oder `None`.

    Getrennt vom Hook, weil alles daran messbar ist ausser dem Hook selbst: was
    geklickt werden kann, in welcher Reihenfolge, und was eine Klick-Runde nicht
    erreicht. Der Hook ist die Plattform-Grenze und bleibt in `start_nachklick`.
    """
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return None
        if state.recording_active:
            print(f"\n{err('Aufnahme läuft')} {hint('(CTRL+ALT+J beendet sie)')}")
            return None
        if state.nachklick_aktiv:
            return None
        seq = state.active_sequence
        punkte = {p.id: p for p in state.points}

    if seq is None:
        print(f"\n{err('Keine Sequenz geladen.')} "
              f"{hint('CTRL+ALT+L lädt eine — die Reihenfolge kommt aus ihr.')}")
        return None

    ids, sonstige = klickpunkte(seq)
    # Ein Punkt, den es nicht mehr gibt, ist kein Ziel — der Schritt zeigt ins
    # Leere und wird beim Lauf ohnehin übersprungen.
    ids = [i for i in ids if i in punkte]
    if not ids:
        print(f"\n{info('Diese Sequenz hat keinen einzigen Klick-Schritt mit Punkt.')}")
        return None

    with state.lock:
        state.nachklick_aktiv = True
        state.nachklick_pausiert = False
        state.nachklick_punkte = ids
        state.nachklick_index = 0
        state.nachklick_gesetzt = []
    return ids, sonstige


def start_nachklick(state: AutoClickerState) -> bool:
    """Startet die Runde samt Maus-Hook. False = konnte nicht starten (mit Meldung)."""
    geruestet = ruesten(state)
    if geruestet is None:
        return False
    ids, sonstige = geruestet
    with state.lock:
        seq = state.active_sequence

    if not install_mouse_hook(_on_click_factory(state), None):
        with state.lock:
            state.nachklick_aktiv = False
            state.nachklick_punkte = []
        print(f"\n{err('Maus-Hook konnte nicht installiert werden!')}")
        print("  Mögliche Ursache: Administratorrechte erforderlich.")
        return False

    print(f"\n{col('╔══ PUNKTE NACHKLICKEN ══╗', 'cyan')}")
    print(f"  Sequenz „{seq.name}“ — {len(ids)} Klick-Punkt(e) der Reihe nach.")
    print("  Klicke im Spiel die Stelle an, die dieser Punkt treffen soll.")
    print(hint("  Dein Klick geht ans Spiel: die Oberfläche geht dabei genau so"))
    print(hint("  auf wie im Lauf, und der nächste Punkt liegt dann vor dir."))
    print(hint("  Geändert wird nur die Stelle — Wartezeiten, Bedingungen und"))
    print(hint("  ELSE bleiben unangetastet."))
    print(f"  Überspringen:  {col('CTRL+ALT+K', 'yellow')} "
          f"{hint('(Punkt bleibt, wo er ist)')}")
    print(f"  Zurück:        {col('CTRL+ALT+U', 'yellow')} "
          f"{hint('(einen Punkt zurück, noch mal)')}")
    print(f"  Pausieren:     {col('CTRL+ALT+H', 'yellow')} "
          f"{hint('(navigieren, ohne einen Punkt zu setzen)')}")
    print(f"  Beenden:       {col('CTRL+ALT+J', 'yellow')} "
          f"{hint('(speichert, was bis dahin gesetzt ist)')}")
    if sonstige:
        print(f"  {info(f'{len(sonstige)} Stelle(n) erreicht eine Klick-Runde nicht')} "
              f"{hint('(beobachtete Pixel, ELSE, Rad) — dafür bleibt walk.')}")
    _zeige_aktuellen(state, springen=True)
    return True


def stop_nachklick(state: AutoClickerState, grund: str = "beendet") -> None:
    """Beendet die Runde, entfernt den Hook und speichert das Ergebnis."""
    with state.lock:
        if not state.nachklick_aktiv:
            return
        state.nachklick_aktiv = False
        state.nachklick_pausiert = False
        gesetzt = list(state.nachklick_gesetzt)
        offen = len(state.nachklick_punkte) - state.nachklick_index
        state.nachklick_punkte = []
        state.nachklick_index = 0
        state.nachklick_gesetzt = []
    remove_mouse_hook()

    # **Geschrieben wird hier, nicht im Hook.** Ein Low-Level-Maus-Hook muss
    # schnell zurückkommen — Windows hängt ihn sonst aus, und dann fehlen
    # Klicks mitten in der Runde. Eine Datei zu schreiben ist meistens schnell,
    # aber „meistens" ist für den Pfad, an dem die ganze Eingabe hängt, zu wenig.
    if gesetzt:
        from ..persistence import save_points
        save_points(state)

    print(f"\n{col('[NACHKLICK]', 'cyan')} {grund}.")
    if gesetzt:
        print(f"  {len(gesetzt)} Punkt(e) neu gesetzt und gespeichert.")
        print(hint("  Jeder Schritt, der sie benutzt, zieht beim nächsten Lauf mit —"))
        print(hint("  Wartezeiten und Bedingungen sind unverändert."))
    else:
        print("  Nichts geändert.")
    if offen > 0:
        print(hint(f"  {offen} Punkt(e) standen noch aus — sie blieben, wo sie waren."))


def nachklick_pause(state: AutoClickerState) -> None:
    """Klicks gehen durch, ohne einen Punkt zu setzen — und zurück."""
    with state.lock:
        if not state.nachklick_aktiv:
            return
        state.nachklick_pausiert = not state.nachklick_pausiert
        pausiert = state.nachklick_pausiert
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
        if not state.nachklick_aktiv:
            return
        if state.nachklick_index >= len(state.nachklick_punkte):
            return
        punkt_id = state.nachklick_punkte[state.nachklick_index]
        state.nachklick_index += 1
        fertig = state.nachklick_index >= len(state.nachklick_punkte)
    print(f"  {col('[ÜBERSPRUNGEN]', 'yellow')} #{punkt_id} bleibt, wo er ist.")
    if fertig:
        stop_nachklick(state, "alle Punkte durch")
    else:
        _zeige_aktuellen(state, springen=True)


def nachklick_zurueck(state: AutoClickerState) -> None:
    """Einen Punkt zurück — der eben gesetzte wird auf seine alte Stelle geholt.

    **Zurück heisst zurück.** Nur den Zeiger zurückzusetzen liesse die eben
    geschriebene Koordinate stehen; wer sich verklickt hat, hätte sie dann
    weiterhin — und merkt es erst beim nächsten Lauf.
    """
    with state.lock:
        if not state.nachklick_aktiv:
            return
        if state.nachklick_index <= 0:
            print(f"  {hint('Schon beim ersten Punkt.')}")
            return
        state.nachklick_index -= 1
        punkt_id = state.nachklick_punkte[state.nachklick_index]
        zurueckgeholt = None
        if state.nachklick_gesetzt and state.nachklick_gesetzt[-1][0] == punkt_id:
            _, alt, _neu = state.nachklick_gesetzt.pop()
            for p in state.points:
                if p.id == punkt_id:
                    p.x, p.y = alt[0], alt[1]
                    zurueckgeholt = alt
                    break
    if zurueckgeholt:
        print(f"  {col('[ZURÜCK]', 'yellow')} #{punkt_id} steht wieder auf "
              f"({zurueckgeholt[0]}, {zurueckgeholt[1]}).")
    _zeige_aktuellen(state, springen=True)


def _on_click_factory(state: AutoClickerState):
    """Der Klick-Callback für den Maus-Hook."""
    def _on_click(x: int, y: int, color) -> None:
        _setze_punkt(state, x, y, color)
    return _on_click


def _setze_punkt(state: AutoClickerState, x: int, y: int, color) -> None:
    """Ein Klick im Spiel: die neue Stelle des aktuellen Punktes."""
    with state.lock:
        if not state.nachklick_aktiv or state.nachklick_pausiert:
            return
        if state.nachklick_index >= len(state.nachklick_punkte):
            return
        punkt_id = state.nachklick_punkte[state.nachklick_index]
        punkt = next((p for p in state.points if p.id == punkt_id), None)
        if punkt is None:
            state.nachklick_index += 1
            fertig = state.nachklick_index >= len(state.nachklick_punkte)
            name, alt, gleich = "", None, False
        else:
            alt = (punkt.x, punkt.y)
            gleich = alt == (x, y)
            punkt.x, punkt.y = x, y
            # Die Farbe gehört zur Position — aber nur, wenn der Punkt vorher
            # eine hatte. Sonst schliche sich ein Farb-Trigger ein, den niemand
            # gesetzt hat. Dieselbe Regel wie in `walk_points`.
            if punkt.color and color:
                punkt.color = color
            name = punkt.name or f"Punkt {punkt.id}"
            if not gleich:
                state.nachklick_gesetzt.append((punkt_id, alt, (x, y)))
            state.nachklick_index += 1
            fertig = state.nachklick_index >= len(state.nachklick_punkte)

    if punkt is not None:
        farbe = f"  {describe_color(color)}" if punkt.color and color else ""
        if gleich:
            print(f"  {col('[GLEICH]', 'gray')} #{punkt_id} {name} — "
                  f"dieselbe Stelle wie vorher.{farbe}")
        else:
            print(f"  {col('[GESETZT]', 'green')} #{punkt_id} {name}  "
                  f"({alt[0]}, {alt[1]}) → ({x}, {y}){farbe}")
    if fertig:
        stop_nachklick(state, "alle Punkte durch")
    else:
        _zeige_aktuellen(state)


def _zeige_aktuellen(state: AutoClickerState, springen: bool = False) -> None:
    """Sagt, welcher Punkt als Nächstes dran ist — und wo er bisher liegt.

    **Der Zeiger springt nur, wenn gerade nicht geklickt wurde.** Nach einem
    echten Klick die Maus wegzuziehen ist gefährlich: das Spiel verarbeitet den
    Klick womöglich noch, und ein Ziehen oder ein Tooltip hängt daran. Beim
    Start, beim Überspringen und beim Zurückgehen hat niemand geklickt — dort
    hilft der Sprung, weil man die alte Stelle dann sieht statt sie zu lesen.
    """
    with state.lock:
        if not state.nachklick_aktiv:
            return
        i, gesamt = state.nachklick_index, len(state.nachklick_punkte)
        if i >= gesamt:
            return
        punkt_id = state.nachklick_punkte[i]
        punkt = next((p for p in state.points if p.id == punkt_id), None)
    if punkt is None:
        return
    farbe = f"  {describe_color(punkt.color)}" if punkt.color else ""
    print(f"  {col(f'→ {i + 1}/{gesamt}', 'cyan')}  #{punkt.id} "
          f"{punkt.name or '(ohne Name)'}   bisher ({punkt.x}, {punkt.y}){farbe}")
    if springen:
        set_cursor_pos(punkt.x, punkt.y)
