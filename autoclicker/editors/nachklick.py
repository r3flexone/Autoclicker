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
Bis dahin liegen die neuen Stellen in `state.nachklick_gesetzt` und die Punkte
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

from ..models import (
    AutoClickerState,
    BLOCK_CLICK,
    BLOCK_WAIT_CLICK,
    Sequence,
    block_type,
)
from ..utils import col, err, hint, info, ok, describe_color, warn
from ..winapi import (
    get_client_rect_by_title,
    get_foreground_window_title,
    install_mouse_hook,
    is_target_window_active,
    remove_mouse_hook,
    set_cursor_pos,
)

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
        if state.nachklick_aktiv:
            return None
        if seq is None:
            seq = state.active_sequence
        punkte = {p.id: p for p in seq.points} if seq is not None else {}

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

    ziel = _zielfenster(state)
    with state.lock:
        state.nachklick_aktiv = True
        state.nachklick_pausiert = False
        state.nachklick_punkte = ids
        state.nachklick_index = 0
        state.nachklick_gesetzt = []
        state.nachklick_ziel = ziel
        state.nachklick_name = seq.name
        state.nachklick_sequence = seq
    _gemeldete_fenster.clear()
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
        gefunden = get_client_rect_by_title(titel) is not None
    except Exception:
        gefunden = False
    if not gefunden:
        print(f"  {warn(f'Fenster „{titel}“ nicht gefunden')} "
              f"{hint('— es zählt JEDER Klick, auch der auf ein anderes Fenster.')}")
        return ""
    return titel


def _im_zielfenster(ziel: str) -> bool:
    """True, wenn der Klick im Zielfenster passiert ist (oder nicht gefiltert wird)."""
    if not ziel:
        return True
    try:
        return bool(is_target_window_active(ziel))
    except Exception:
        # Lässt sich der Vordergrund nicht bestimmen, gilt der Klick. Lieber ein
        # Punkt zu viel gesetzt als eine Runde, die stumm nichts tut.
        return True


def start_nachklick(state: AutoClickerState, seq: Sequence = None) -> bool:
    """Startet die Runde samt Maus-Hook. False = konnte nicht starten (mit Meldung)."""
    geruestet = ruesten(state, seq)
    if geruestet is None:
        return False
    ids, sonstige = geruestet

    if not install_mouse_hook(_on_click_factory(state), None):
        with state.lock:
            state.nachklick_aktiv = False
            state.nachklick_punkte = []
        print(f"\n{err('Maus-Hook konnte nicht installiert werden!')}")
        print("  Mögliche Ursache: Administratorrechte erforderlich.")
        return False

    with state.lock:
        ziel, name = state.nachklick_ziel, state.nachklick_name
    _banner(name, len(ids), ziel, sonstige)
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


def _banner(name: str, anzahl: int, ziel: str, sonstige: list) -> None:
    """Was die Runde tut, was sie nicht tut, und womit man sie bedient."""
    print(f"\n{col('╔══ PUNKTE NACHKLICKEN ══╗', 'cyan')}")
    print(f"  {anzahl} Punkt(e) aus „{name}“, in der Reihenfolge des Laufs.")
    print(f"  {col('So geht es:', 'cyan')} der Zeiger steht jedes Mal schon auf der "
          "gespeicherten")
    print("  Stelle. Stimmt sie noch — klicken. Stimmt sie nicht — hinfahren und "
          "dort klicken.")
    if ziel:
        print(f"  Gezählt wird nur, was in {col(ziel, 'cyan')} geklickt wird; in "
              "jedem anderen")
        print("  Fenster kannst du klicken, ohne einen Punkt zu verbrauchen.")
    print()
    for taste, was, warum in TASTEN:
        print(f"    {col(taste.ljust(11), 'yellow')} {was.ljust(13)}"
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


def stop_nachklick(state: AutoClickerState, grund: str = "beendet",
                   uebernehmen: bool = True) -> None:
    """Beendet die Runde und schreibt das Ergebnis — oder wirft es weg.

    **Erst hier wird überhaupt etwas geändert.** Während der Runde stehen die
    neuen Stellen in `nachklick_gesetzt`; die Punkte selbst sind unangetastet,
    auch im Speicher. `uebernehmen=False` heisst deshalb schlicht: Liste weg,
    fertig — es gibt nichts zurückzudrehen.

    Das ist der Unterschied zwischen einer abgebrochenen Runde und einer halb
    überschriebenen `sequence.json`. Vorher schrieb jeder Ausgang, auch das
    Beenden des Programms: in einer echten Runde landeten so drei Klicks auf
    Fensterdekoration dauerhaft in den Punkten.
    """
    with state.lock:
        if not state.nachklick_aktiv:
            return
        state.nachklick_aktiv = False
        state.nachklick_pausiert = False
        gesetzt = list(state.nachklick_gesetzt)
        offen = len(state.nachklick_punkte) - state.nachklick_index
        ziel_sequence = state.nachklick_sequence
        punkte = {p.id: p for p in (
            ziel_sequence.points if ziel_sequence is not None else state.points)}
        if uebernehmen:
            for punkt_id, _alt, neu, neue_farbe in gesetzt:
                punkt = punkte.get(punkt_id)
                if punkt is None:
                    continue
                punkt.x, punkt.y = neu
                # Die Farbe gehört zur Position — aber nur, wenn der Punkt vorher
                # eine hatte. Sonst schliche sich ein Farb-Trigger ein, den
                # niemand gesetzt hat. Dieselbe Regel wie in `walk_points`.
                if punkt.color and neue_farbe:
                    punkt.color = neue_farbe
        state.nachklick_punkte = []
        state.nachklick_index = 0
        state.nachklick_gesetzt = []
        state.nachklick_ziel = ""
        state.nachklick_name = ""
        state.nachklick_sequence = None
    remove_mouse_hook()
    _gemeldete_fenster.clear()

    # **Geschrieben wird hier, nicht im Hook.** Ein Low-Level-Maus-Hook muss
    # schnell zurückkommen — Windows hängt ihn sonst aus, und dann fehlen
    # Klicks mitten in der Runde. Eine Datei zu schreiben ist meistens schnell,
    # aber „meistens" ist für den Pfad, an dem die ganze Eingabe hängt, zu wenig.
    if gesetzt and uebernehmen:
        from ..persistence import save_sequence_file, sequence_file
        if ziel_sequence is not None:
            save_sequence_file(ziel_sequence, sequence_file(ziel_sequence.name))

    print(f"\n{col('[NACHKLICK]', 'cyan')} {grund}.")
    if not gesetzt:
        print("  Nichts geändert.")
    elif uebernehmen:
        print(f"  {ok(f'{len(gesetzt)} Punkt(e) neu gesetzt und gespeichert.')}")
        for punkt_id, altpos, neu, _f in gesetzt[:12]:
            print(hint(f"     #{punkt_id}  ({altpos[0]}, {altpos[1]}) → "
                       f"({neu[0]}, {neu[1]})"))
        if len(gesetzt) > 12:
            print(hint(f"     … und {len(gesetzt) - 12} weitere"))
        print(hint("  Jeder Schritt, der sie benutzt, zieht beim nächsten Lauf mit —"))
        print(hint("  Wartezeiten und Bedingungen sind unverändert."))
    else:
        print(f"  {warn(f'{len(gesetzt)} gesetzte Stelle(n) verworfen')} "
              f"{hint('— sequence.json ist unverändert.')}")
    if offen > 0 and uebernehmen:
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
        if not state.nachklick_aktiv:
            return
        if state.nachklick_index <= 0:
            print(f"  {hint('Schon beim ersten Punkt.')}")
            return
        state.nachklick_index -= 1
        punkt_id = state.nachklick_punkte[state.nachklick_index]
        verworfen = None
        for i, eintrag in enumerate(state.nachklick_gesetzt):
            if eintrag[0] == punkt_id:
                verworfen = state.nachklick_gesetzt.pop(i)[1]
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
        if not state.nachklick_aktiv or state.nachklick_pausiert:
            return
        # **Nur echte Klicks zählen.** Läuft der Worker, sind seine eigenen
        # Klicks für den Hook nicht von einem Handgriff zu unterscheiden — die
        # Runde raste dann von selbst durch die Punkte und schriebe überall die
        # Stellen hin, die der Lauf gerade anfährt. `handle_toggle()` lässt es
        # gar nicht erst so weit kommen; das hier ist die zweite Tür.
        if state.is_running:
            return
        if state.nachklick_index >= len(state.nachklick_punkte):
            return
        ziel = state.nachklick_ziel
        punkt_id = state.nachklick_punkte[state.nachklick_index]
        seq = state.nachklick_sequence
        pool = seq.points if seq is not None else state.points
        punkt = next((p for p in pool if p.id == punkt_id), None)

    # **Ein Klick ausserhalb des Spiels ist kein Punkt.** Ausserhalb des Locks,
    # weil `is_target_window_active()` das Betriebssystem fragt und der Hook
    # schnell zurück muss.
    if not _im_zielfenster(ziel):
        fremd = (get_foreground_window_title() or "?").strip()
        if fremd not in _gemeldete_fenster:
            _gemeldete_fenster.add(fremd)
            print(f"\n  {warn('[IGNORIERT]')} Klick in „{fremd}“ — Punkte werden "
                  f"nur in „{ziel}“ gesetzt.")
            print(hint("     Fenster wechseln und weiterklicken; der Punkt ist "
                       "noch derselbe."))
        return

    with state.lock:
        # Zwischen den beiden Locks kann die Runde beendet oder weitergerückt
        # sein (CTRL+ALT+K, CTRL+ALT+J) — dann gilt dieser Klick nicht mehr.
        if (not state.nachklick_aktiv
                or state.nachklick_index >= len(state.nachklick_punkte)
                or state.nachklick_punkte[state.nachklick_index] != punkt_id):
            return
        if punkt is None:
            state.nachklick_index += 1
            fertig = state.nachklick_index >= len(state.nachklick_punkte)
            name, alt, gleich = "", None, False
        else:
            # **Der Punkt wird NICHT angefasst.** Die neue Stelle kommt auf die
            # Liste; geschrieben wird sie erst beim Übernehmen. Damit ist ein
            # Abbruch wirklich ein Abbruch — es gibt nichts zurückzudrehen.
            alt = (punkt.x, punkt.y)
            # Ein Pixel Abweichung ist keine Korrektur — siehe PASST_TOLERANZ.
            gleich = (abs(alt[0] - x) <= PASST_TOLERANZ
                      and abs(alt[1] - y) <= PASST_TOLERANZ)
            name = punkt.name or f"Punkt {punkt.id}"
            if not gleich:
                state.nachklick_gesetzt = [
                    e for e in state.nachklick_gesetzt if e[0] != punkt_id]
                state.nachklick_gesetzt.append((punkt_id, alt, (x, y), color))
            state.nachklick_index += 1
            fertig = state.nachklick_index >= len(state.nachklick_punkte)

    if punkt is not None:
        farbe = f"  {describe_color(color)}" if punkt.color and color else ""
        if gleich:
            # Der Normalfall, seit der Zeiger vorher dort steht: hinsehen,
            # klicken, weiter. Deshalb liest es sich als Bestätigung und nicht
            # als „nichts passiert".
            print(f"  {col('[PASST]', 'green')} #{punkt_id} {name} — "
                  f"bestätigt, bleibt wo er ist.{farbe}")
        else:
            print(f"  {col('[GESETZT]', 'green')} #{punkt_id} {name}  "
                  f"({alt[0]}, {alt[1]}) → ({x}, {y}){farbe}")
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
    with state.lock:
        if not state.nachklick_aktiv:
            return
        i, gesamt = state.nachklick_index, len(state.nachklick_punkte)
        if i >= gesamt:
            return
        punkt_id = state.nachklick_punkte[i]
        seq = state.nachklick_sequence
        pool = seq.points if seq is not None else state.points
        punkt = next((p for p in pool if p.id == punkt_id), None)
    if punkt is None:
        return
    farbe = f"  {describe_color(punkt.color)}" if punkt.color else ""
    print(f"  {col(f'→ {i + 1}/{gesamt}', 'cyan')}  #{punkt.id} "
          f"{punkt.name or '(ohne Name)'}   Zeiger steht auf "
          f"({punkt.x}, {punkt.y}){farbe}")
    _springe(punkt.x, punkt.y, verzoegert)
