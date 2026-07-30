"""
Hotkey-Handler für den Autoclicker.
Verarbeitet Tastenkombinationen und führt entsprechende Aktionen aus.
"""

import os
import shutil
import stat
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import AppConfig, CONFIG_FILE, SEQUENCES_DIR
from .models import AutoClickerState, ClickPoint
from .utils import safe_input, format_duration, parse_time_input, is_cancel, cancel_hint, interactive_select, col, ok, err, info, header, hint, coord_context, dbg, describe_color
from .winapi import get_cursor_pos, set_cursor_pos, get_screen_pixel, user32
from .persistence import (
    save_data, ensure_sequences_dir, list_available_sequences,
    load_sequence_file, get_next_point_id, get_point_by_id, print_points,
    ITEMS_DIR, SLOTS_DIR, ITEM_SCANS_DIR, BOSS_SCANS_DIR, ICON_SCANS_DIR,
    init_directories
)
from .execution import sequence_worker, print_status
from .runtime.actions import is_verbose_debug
from .imaging import run_color_analyzer


def _rmtree_robust(path: Path) -> None:
    """Löscht einen Ordner rekursiv, behandelt Windows-Schreibschutz.

    Auf Windows schlägt shutil.rmtree mit PermissionError (WinError 5) fehl, wenn
    eine Datei das Read-only-Attribut trägt. Der Error-Handler entfernt das Flag
    und versucht die Operation erneut, statt den Factory-Reset mittendrin abzubrechen.
    """
    def _on_error(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    # onerror ist seit Python 3.12 zugunsten von onexc deprecated (gleiche 3 Args).
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_on_error)
    else:
        shutil.rmtree(path, onerror=_on_error)


# Serialisiert den gesamten Start/Stop-Pfad von handle_toggle, damit Countdown-Thread
# und Main-Thread nicht gleichzeitig den is_running-Check passieren und doppelt starten.
_toggle_lock = threading.Lock()


def _block_if_recording(state: AutoClickerState) -> bool:
    """Blockiert Handler mit Konsolen-Eingaben während einer laufenden Aufnahme.

    Der Low-Level-Maus-Hook braucht die Message-Pump des Main-Threads — blockierende
    Editoren würden den Hook still entfernen und Klicks gingen verloren.
    Gibt True zurück, wenn der Handler abbrechen soll.
    """
    with state.lock:
        recording = state.recording_active
    if recording:
        print(f"\n{err('Aufnahme läuft — erst mit CTRL+ALT+J stoppen (sonst gehen Klicks verloren)')}")
        return True
    return False


def handle_record(state: AutoClickerState) -> None:
    """Nimmt die aktuelle Mausposition auf - sofort ohne Eingabe."""
    x, y = get_cursor_pos()
    color = get_screen_pixel(x, y)  # Farbe am Aufnahme-Zeitpunkt mitspeichern

    with state.lock:
        new_id = get_next_point_id(state)
        name = f"P{new_id}"
        point = ClickPoint(x, y, name, new_id, color=color)
        state.points.append(point)

    # Auto-speichern
    save_data(state)

    color_str = f"  {describe_color(color)}" if color else ""
    print(f"\n{col('[RECORD]', 'green')} #{new_id} {name} hinzugefügt: {coord_context(x, y)}{color_str}")
    print_status(state)


def handle_undo(state: AutoClickerState) -> None:
    """Entfernt den letzten Punkt."""
    with state.lock:
        removed = state.points.pop() if state.points else None

    if removed is not None:
        print(f"\n{col('[UNDO]', 'yellow')} Punkt entfernt: {removed}")
        save_data(state)
    else:
        print(f"\n{col('[UNDO]', 'yellow')} Keine Punkte zum Entfernen.")
    print_status(state)


def handle_clear(state: AutoClickerState) -> None:
    """Löscht ALLE Punkte."""
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return

        count = len(state.points)
        if count == 0:
            print(f"\n{col('[CLEAR]', 'yellow')} Keine Punkte vorhanden.")
            return

        state.points.clear()
        state.active_sequence = None

    save_data(state)
    print(f"\n{ok(f'Alle {count} Punkte gelöscht!')}")
    print_status(state)


def handle_reset(state: AutoClickerState) -> None:
    """Löscht ALLES - kompletter Factory Reset wie frisch von GitHub."""
    if _block_if_recording(state):
        return
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return

    with state.lock:
        num_points = len(state.points)
        num_slots = len(state.global_slots)
        num_items = len(state.global_items)
        num_item_scans = len(state.item_scans)
        num_boss_scans = len(state.boss_scans)
        num_icon_scans = len(state.icon_scans)

    print(header("FACTORY RESET - ALLES WIRD GELÖSCHT!"))
    print(f"\n{col('Folgendes wird gelöscht:', 'red')}")
    print(f"  {col('-', 'red')} {num_points} Punkt(e)")
    print(f"  {col('-', 'red')} {len(list_available_sequences())} Sequenz-Datei(en)")
    print(f"  {col('-', 'red')} {num_slots} Slot(s)")
    print(f"  {col('-', 'red')} {num_items} Item(s)")
    print(f"  {col('-', 'red')} {num_item_scans} Item-Scan(s)")
    print(f"  {col('-', 'red')} {num_boss_scans} Boss-Scan(s)")
    print(f"  {col('-', 'red')} {num_icon_scans} Icon-Scan(s)")
    print(f"  {col('-', 'red')} Config-Einstellungen")
    print(f"\n{col('Das Programm wird danach wie frisch von GitHub sein!', 'yellow')}")
    print(f"\nBist du sicher? Tippe {col('JA', 'red')} zum Bestätigen:")

    try:
        confirm_text = safe_input("> ").strip().upper()
        if confirm_text != "JA":
            print(f"{col('[ABBRUCH]', 'yellow')} Nichts wurde gelöscht.")
            return

        # Speicher löschen
        with state.lock:
            state.points.clear()
            state.sequences.clear()
            state.active_sequence = None
            state.global_slots.clear()
            state.global_items.clear()
            state.item_scans.clear()
            state.boss_scans.clear()
            state.icon_scans.clear()

        # Alle Ordner löschen
        folders_to_delete = [SEQUENCES_DIR, ITEMS_DIR, SLOTS_DIR, ITEM_SCANS_DIR,
                             BOSS_SCANS_DIR, ICON_SCANS_DIR]
        for folder in folders_to_delete:
            folder_path = Path(folder)
            if folder_path.exists():
                _rmtree_robust(folder_path)
                print(f"  {col('-', 'red')} {folder}/ {col('gelöscht', 'red')}")

        # Config löschen
        config_path = Path(CONFIG_FILE)
        if config_path.exists():
            config_path.unlink()
            print(f"  {col('-', 'red')} {CONFIG_FILE} {col('gelöscht', 'red')}")

        # Ordner neu erstellen
        ensure_sequences_dir()
        init_directories()

        # Config auf Standard zurücksetzen
        with state.lock:
            state.config = AppConfig()

        print(f"\n{ok('Factory Reset abgeschlossen!')}")
        print(ok("Das Programm ist jetzt wie frisch von GitHub."))
        print_status(state)

    except (KeyboardInterrupt, EOFError):
        print(f"\n{col('[ABBRUCH]', 'yellow')} Nichts wurde gelöscht.")


def handle_editor(state: AutoClickerState) -> None:
    """Öffnet den Sequenz-Editor."""
    if _block_if_recording(state):
        return
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
    from .editors.sequence_editor import run_sequence_editor
    run_sequence_editor(state)


def handle_item_scan_editor(state: AutoClickerState) -> None:
    """Öffnet das Item-Scan Menü (Slots, Items, Scans)."""
    if _block_if_recording(state):
        return
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
    from .editors.item_scan_editor import run_item_scan_menu
    run_item_scan_menu(state)


def handle_load(state: AutoClickerState) -> None:
    """Lädt eine Sequenz."""
    if _block_if_recording(state):
        return
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
    from .editors.sequence_editor import run_sequence_loader
    run_sequence_loader(state)


def handle_step_mode(state: AutoClickerState) -> None:
    """Schaltet den manuellen Modus um (CTRL+ALT+M).

    Läuft gerade eine Sequenz, greift die Umschaltung ab dem nächsten Schritt - man kann
    also mitten im Lauf auf manuell gehen, wenn etwas nicht stimmt, und danach mit 'c'
    im Gate oder erneutem Hotkey zurück in den Normalbetrieb.
    """
    with state.lock:
        state.step_mode = not state.step_mode
        aktiv = state.step_mode
        laeuft = state.is_running

    if aktiv:
        print(f"\n{col('[MANUELL]', 'yellow')} Manueller Modus AN — Wartezeiten werden "
              f"übersprungen, jeder Schritt wartet auf Bestätigung.")
        print(f"           Im Schritt: {col('w', 'yellow')} ausführen | "
              f"{col('s', 'yellow')} überspringen | "
              f"{col('c', 'yellow')} normal weiter | {col('q', 'yellow')} abbrechen")
        if not laeuft:
            print(f"           {hint('Greift beim nächsten Start (CTRL+ALT+S).')}")
    else:
        print(f"\n{col('[MANUELL]', 'cyan')} Manueller Modus AUS — normaler Ablauf.")


def handle_show(state: AutoClickerState) -> None:
    """Zeigt alle Punkte an, ermöglicht Testen und Umbenennen."""
    # Wie die anderen Editoren: nicht während Aufnahme/Lauf öffnen — sonst
    # können Punkt-Mutationen mit dem Worker/Recorder kollidieren.
    if _block_if_recording(state):
        return
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return

    print_points(state)

    with state.lock:
        if not state.points:
            return
        num_points = len(state.points)

    print(col("-" * 50, 'gray'))
    print(col("Optionen:", 'bold'))
    print(f"  {col('<Nr>', 'yellow')}        - Punkt testen (Maus hinbewegen, dann Umbenennen-Abfrage)")
    print(f"  {col('show <Nr>', 'yellow')}   - Punkt zeigen (Maus hinbewegen + Details, ohne Abfrage)")
    print(f"  {col('<Nr> <Name>', 'yellow')} - Punkt umbenennen")
    print(f"  {col('del <Nr>', 'yellow')}    - Punkt löschen")
    print(f"  {col('walk / w', 'yellow')}    - alle Punkte einzeln durchgehen (Maus springt hin, Taste = weiter)")
    print(f"  {col('list', 'yellow')}        - Punktliste erneut anzeigen")
    print(f"  {col('done / d', 'yellow')}    - Zurück {hint(f'(auch {cancel_hint()} oder Enter)')}")
    print(col("-" * 50, 'gray'))

    while True:
        try:
            user_input = safe_input("> ").strip()
            if not user_input or user_input.lower() in ("done", "d") or is_cancel(user_input):
                print(f"{col('[PUNKTE]', 'cyan')} Editor geschlossen — Hotkeys wieder aktiv.")
                return

            if user_input.lower() in ("walk", "w"):
                from .runtime.debug import walk_points
                walk_points(state)
                continue

            if user_input.lower() in ("list", "l"):
                print_points(state)
                continue

            # Zeigen-Befehl: Maus hinbewegen + Details, ohne Umbenennen-Abfrage
            if user_input.lower().startswith("show "):
                try:
                    show_id = int(user_input[5:])
                except ValueError:
                    print(err("Format: show <Nr>"))
                    continue
                with state.lock:
                    point = get_point_by_id(state, show_id)
                if not point:
                    print(f"{err(f'Punkt #{show_id} nicht gefunden!')} {hint('(list = Punkte anzeigen)')}")
                    continue
                set_cursor_pos(point.x, point.y)
                print(f"{col('[SHOW]', 'cyan')} #{point.id} {point.name} {coord_context(point.x, point.y)}")
                if point.color:
                    print(f"       Farbe:    {describe_color(point.color)}")
                if point.source:
                    print(f"       Herkunft: {point.source}")
                print(hint("       Maus steht jetzt auf dem Punkt."))
                continue

            # Löschen-Befehl (per ID)
            if user_input.lower().startswith("del "):
                try:
                    del_id = int(user_input[4:])
                    with state.lock:
                        point_to_del = get_point_by_id(state, del_id)
                        if not point_to_del:
                            print(f"{err(f'Punkt #{del_id} nicht gefunden!')} {hint('(list = Punkte anzeigen)')}")
                            continue
                        state.points.remove(point_to_del)
                        num_points = len(state.points)
                    save_data(state)
                    print(f"{ok(f'Punkt #{del_id} gelöscht: {point_to_del}')}")
                    if num_points == 0:
                        print(info("Keine Punkte mehr vorhanden."))
                        return
                except ValueError:
                    print(err("Format: del <ID>"))
                continue

            parts = user_input.split(maxsplit=1)
            point_id = int(parts[0])

            with state.lock:
                point = get_point_by_id(state, point_id)
                if not point:
                    print(err(f"Punkt #{point_id} nicht gefunden!"))
                    continue

            if len(parts) == 1:
                # Nur ID → Testen (Maus hinbewegen)
                print(f"{col('[TEST]', 'cyan')} Bewege Maus zu {point.name} {coord_context(point.x, point.y)}...")
                set_cursor_pos(point.x, point.y)
                print(f"{col('[TEST]', 'cyan')} Maus ist jetzt bei {point.name}. Neuer Name? (Enter = behalten)")

                new_name = safe_input("> ").strip()
                if is_cancel(new_name):  # ESC/q darf nicht zum Namen werden
                    new_name = ""
                if new_name:
                    with state.lock:
                        point.name = new_name
                    save_data(state)
                    print(ok(f"Punkt #{point_id} umbenannt zu '{new_name}'"))
                else:
                    print(ok(f"Name '{point.name}' beibehalten."))

            else:
                # ID + Name → Direkt umbenennen
                new_name = parts[1]
                with state.lock:
                    point.name = new_name
                save_data(state)
                print(ok(f"Punkt #{point_id} umbenannt zu '{new_name}'"))

        except ValueError:
            print(f"{err('Ungültige Eingabe!')} {hint('(Zahl = testen, <Nr> <Name> = umbenennen, del <Nr> = löschen)')}")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{col('[PUNKTE]', 'cyan')} Editor geschlossen — Hotkeys wieder aktiv.")
            return


def handle_finish(state: AutoClickerState) -> None:
    """Sanfter Abbruch: aktuellen Zyklus zu Ende führen, dann END-Phase und Stop."""
    with state.lock:
        if not state.is_running:
            print(f"\n{info('Kein Zyklus läuft.')}")
            return
        if state.finish_event.is_set():
            print(f"\n{col('[FINISH]', 'yellow')} Sanfter Abbruch bereits aktiv...")
            return
    state.finish_event.set()
    print(f"\n{col('[FINISH]', 'yellow')} Zyklus wird abgeschlossen, dann END-Phase und Stop.")


def handle_toggle(state: AutoClickerState) -> None:
    """Startet oder stoppt die Sequenz."""
    # _toggle_lock serialisiert den gesamten Start/Stop-Pfad, damit Countdown-Thread
    # und Main-Thread nicht beide den is_running-Check passieren und doppelt starten.
    with _toggle_lock:
        # Während einer laufenden Aufnahme nicht starten — sonst zeichnet der
        # Maus-Hook die synthetischen Klicks des Workers mit auf.
        with state.lock:
            if state.recording_active:
                print(f"\n{err('Aufnahme läuft')} {hint('(CTRL+ALT+J zum Stoppen)')}")
                return

        # Prüfe ob Countdown aktiv → nur abbrechen, nicht starten
        with state.lock:
            if state.countdown_active:
                state.stop_event.set()
                print(f"\n{col('[TOGGLE]', 'yellow')} Countdown abgebrochen.")
                return

        # Prüfe ob bereits läuft → stoppen
        with state.lock:
            if state.is_running:
                state.stop_event.set()
                print(f"\n{col('[TOGGLE]', 'yellow')} Stoppe Sequenz...")
                return

        # Keine Sequenz geladen → automatisch Lade-Menü öffnen
        with state.lock:
            has_sequence = state.active_sequence is not None
        if not has_sequence:
            print(f"\n{info('Keine Sequenz geladen - öffne Lade-Menü...')}")
            from .editors.sequence_editor import run_sequence_loader
            run_sequence_loader(state)
            # Nach dem Laden prüfen ob jetzt eine Sequenz da ist
            with state.lock:
                has_sequence = state.active_sequence is not None
            if not has_sequence:
                return  # Nichts geladen

        # Jetzt starten
        with state.lock:
            state.is_running = True
            state.stop_event.clear()
            state.pause_event.clear()
            state.skip_event.clear()

            worker = threading.Thread(target=sequence_worker, args=(state,), daemon=True)
            worker.start()


def handle_pause(state: AutoClickerState) -> None:
    """Pausiert oder setzt die Sequenz fort."""
    with state.lock:
        if not state.is_running:
            print(f"\n{info('Keine Sequenz läuft.')}")
            return

        if state.pause_event.is_set():
            state.pause_event.clear()
            print(f"\n{col('[RESUME]', 'green')} Sequenz fortgesetzt.")
        else:
            state.pause_event.set()
            print(f"\n{col('[PAUSE]', 'yellow')} Sequenz pausiert. Fortsetzen: {col('CTRL+ALT+G', 'yellow')}")


def handle_skip(state: AutoClickerState) -> None:
    """Überspringt die aktuelle Wartezeit."""
    with state.lock:
        if not state.is_running:
            print(f"\n{info('Keine Sequenz läuft.')}")
            return

        state.skip_event.set()
        print(f"\n{col('[SKIP]', 'cyan')} Wartezeit übersprungen!")


def handle_switch(state: AutoClickerState) -> None:
    """Schneller Wechsel zwischen gespeicherten Sequenzen."""
    if _block_if_recording(state):
        return
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return

    sequences = list_available_sequences()

    if not sequences:
        print(f"\n{info('Keine Sequenzen vorhanden!')} Erstelle eine mit {col('CTRL+ALT+E', 'yellow')}")
        return

    # Sequenzen einmal laden und cachen
    with state.lock:
        active_name = state.active_sequence.name if state.active_sequence else None
    loaded_sequences = []
    menu_options = []
    for name, path in sequences:
        # Punkte mitgeben: die Migration verknüpft damit Alt-Schritte über ihre
        # Koordinaten mit dem Punkte-Pool (point_id).
        with state.lock:
            punkte = list(state.points)
        seq = load_sequence_file(path, punkte)
        if seq:
            loaded_sequences.append(seq)
            active_marker = " *AKTIV*" if active_name and active_name == seq.name else ""
            menu_options.append(f"{seq.name}{active_marker}")

    choice = interactive_select(menu_options, title="\nQUICK-SWITCH: Sequenz wählen")

    if choice == -1 or choice >= len(loaded_sequences):
        return

    seq = loaded_sequences[choice]
    with state.lock:
        state.active_sequence = seq
    print(f"\n{ok(f'Gewechselt zu: {seq.name}')}")
    print(f"     Starten mit {col('CTRL+ALT+S', 'yellow')}")


def handle_schedule(state: AutoClickerState) -> None:
    """Plant den Start einer Sequenz zu einem bestimmten Zeitpunkt."""
    if _block_if_recording(state):
        return
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
        if state.countdown_active:
            print(f"\n{err('Es läuft bereits ein Countdown')} {hint('(CTRL+ALT+S zum Abbrechen)')}")
            return

    # Keine Sequenz geladen → automatisch Lade-Menü öffnen
    with state.lock:
        has_sequence = state.active_sequence is not None
    if not has_sequence:
        print(f"\n{info('Keine Sequenz geladen - öffne Lade-Menü...')}")
        from .editors.sequence_editor import run_sequence_loader
        run_sequence_loader(state)
        with state.lock:
            has_sequence = state.active_sequence is not None
        if not has_sequence:
            return  # Nichts geladen

    with state.lock:
        seq_name = state.active_sequence.name if state.active_sequence else "?"
    print("\n" + col("=" * 50, 'cyan'))
    print(f"  {col('ZEITPLAN: Sequenz zu bestimmter Zeit starten', 'bold')}")
    print(col("=" * 50, 'cyan'))
    print(f"\nAktive Sequenz: {col(seq_name, 'cyan')}")
    print(f"\n{col('Zeit-Formate:', 'bold')}")
    print(f"  {col('14:30', 'yellow')}    - Startet um 14:30 Uhr")
    print(f"  {col('1430', 'yellow')}     - Startet um 14:30 Uhr (4-stellig, 0000-2359)")
    print(f"  {col('+30s', 'yellow')}     - Startet in 30 Sekunden")
    print(f"  {col('+30m', 'yellow')}     - Startet in 30 Minuten (+5 = +5m)")
    print(f"  {col('+2h', 'yellow')}      - Startet in 2 Stunden")
    print(f"  {col('30s/30m/2h', 'yellow')} - Wartet (Einheit s/m/h erforderlich!)")
    print(f"\nZeit eingeben (oder {col('cancel', 'yellow')}):")

    try:
        time_input = safe_input("> ").strip()

        if not time_input or is_cancel(time_input):
            print(col("[ABBRUCH]", "yellow"))
            return

        seconds, desc, target_timestamp = parse_time_input(time_input)

        # Debug: Zeige was geparst wurde
        if is_verbose_debug(state):
            print(dbg(f"Eingabe: '{time_input}' -> seconds={seconds}, desc='{desc}', target_timestamp={target_timestamp}"))

        if seconds < 0:
            print(err(desc))
            return

        if seconds < 1:
            print(info("Zeit zu kurz - starte sofort..."))
            # Starte sofort
            handle_toggle(state)
            return

        # Zeige Countdown-Info und warte auf Bestätigung
        # Bei absoluten Zeiten: target_timestamp enthält die Zielzeit
        # Bei relativen Zeiten: target_timestamp ist None, wird nach Enter berechnet
        if target_timestamp is not None:
            target_time = target_timestamp
            target_dt = datetime.fromtimestamp(target_time)
            print(f"\n{col('[GEPLANT]', 'cyan')} Sequenz '{seq_name}' startet {desc}")
            print(f"          {col('Zielzeit:', 'cyan')} {target_dt.strftime('%H:%M:%S')}")
            print(f"          {col('Wartezeit:', 'cyan')} {format_duration(seconds)}")
        else:
            target_time = datetime.now().timestamp() + seconds  # Nur für Vorschau
            print(f"\n{col('[GEPLANT]', 'cyan')} Sequenz '{seq_name}' startet {desc}")
            print(f"          {col('Wartezeit:', 'cyan')} {format_duration(seconds)} (ab Enter-Bestätigung)")
        print(f"\n          {col('Enter', 'yellow')} drücken zum Starten, {col('cancel', 'yellow')} zum Abbrechen")

        # Bestätigung abwarten
        confirm_input = safe_input("> ").strip()
        if is_cancel(confirm_input):
            print(col("[ABBRUCH]", "yellow"))
            return

        # Nach Enter: Bei relativen Zeiten jetzt die Zielzeit berechnen
        # Bei absoluten Zeiten bleibt target_time unverändert (das ist der Fix!)
        if target_timestamp is None:
            # Relative Zeit: Jetzt erst die tatsächliche Zielzeit setzen
            target_time = time.time() + seconds

        # Countdown in separatem Thread starten, damit Hotkeys weiter funktionieren
        def countdown_worker():
            nonlocal target_time  # Zugriff auf target_time aus dem äußeren Scope
            with state.lock:
                state.countdown_active = True

            try:
                while not state.stop_event.is_set() and not state.quit_event.is_set():
                    # Verbleibende Zeit dynamisch berechnen (funktioniert für beide Fälle)
                    remaining = target_time - time.time()

                    if remaining <= 0:
                        break

                    # Zeige Countdown
                    print(f"\r{col('[COUNTDOWN]', 'cyan')} Noch {format_duration(remaining)}... ({col('CTRL+ALT+S', 'yellow')} zum Abbrechen)    ", end="", flush=True)

                    # Kurz warten
                    if state.stop_event.wait(0.5):
                        break  # Stop-Event wurde gesetzt

                if state.stop_event.is_set():
                    print(f"\n{col('[ABBRUCH]', 'yellow')} Zeitplan abgebrochen.")
                    state.stop_event.clear()  # Reset für nächsten Start
                    return

                if state.quit_event.is_set():
                    return

                # Zeit erreicht - starte Sequenz
                print(f"\n{col('[START]', 'green')} Zeit erreicht - starte Sequenz!")
                state.stop_event.clear()  # Reset falls gesetzt
                with state.lock:
                    state.scheduled_start = True  # Überspringt Debug-Enter-Prompt
            finally:
                with state.lock:
                    state.countdown_active = False

            # Sequenz starten (außerhalb von finally, damit countdown_active schon False ist)
            handle_toggle(state)

        print(f"\n{col('[COUNTDOWN]', 'cyan')} Warte auf Startzeit... (Abbrechen mit {col('CTRL+ALT+S', 'yellow')})")
        countdown_thread = threading.Thread(target=countdown_worker, daemon=True)
        countdown_thread.start()
        # Kehre zur Haupt-Event-Loop zurück, damit Hotkeys funktionieren
        return

    except (KeyboardInterrupt, EOFError):
        print(f"\n{col('[ABBRUCH]', 'yellow')}")
    except ValueError as e:
        print(err(str(e)))


def handle_analyze(state: AutoClickerState) -> None:
    """Startet den Farb-Analysator."""
    if _block_if_recording(state):
        return
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
    run_color_analyzer()


def handle_import_export(state: AutoClickerState) -> None:
    """Öffnet den Import/Export-Editor."""
    if _block_if_recording(state):
        return
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
    from .editors.import_export_editor import run_import_export_editor
    run_import_export_editor(state)


def handle_record_sequence(state: AutoClickerState) -> None:
    """Startet oder stoppt die Sequenz-Aufnahme via Maus-Hook."""
    from .editors.sequence_recorder import handle_record_sequence as _rec
    _rec(state)


def handle_record_pause(state: AutoClickerState) -> None:
    """Pausiert/Setzt die laufende Sequenz-Aufnahme fort."""
    from .editors.sequence_recorder import handle_record_pause as _pause
    _pause(state)


def handle_node_editor(state: AutoClickerState) -> None:
    """Öffnet den visuellen Node-Editor als separaten Subprocess.

    Der Editor läuft in einem eigenen Prozess (Dear PyGui), damit sein Event-Loop
    nicht mit der Hotkey-Message-Pump kollidiert. Er bearbeitet die aktive Sequenz
    direkt auf Disk; nach dem Speichern mit CTRL+ALT+L neu laden.
    """
    import subprocess

    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
        seq_name = state.active_sequence.name if state.active_sequence else ""

    args = [sys.executable, "-m", "autoclicker.node_editor"]
    if seq_name:
        args.append(seq_name)

    try:
        subprocess.Popen(args)
    except OSError as e:
        print(f"\n{err(f'Konnte Node-Editor nicht starten: {e}')}")
        return

    target = f"'{seq_name}'" if seq_name else "neue Sequenz"
    print(f"\n{col('[NODE-EDITOR]', 'cyan')} Visueller Editor geöffnet ({target}).")
    print(f"     Nach dem Speichern mit {col('CTRL+ALT+L', 'yellow')} neu laden.")


def handle_scan_studio(state: AutoClickerState) -> None:
    """Öffnet das visuelle Scan-Studio als separaten Subprocess.

    Nimmt einen Screenshot auf und lässt Slots (perspektivisch auch Items/Scans)
    direkt darauf anlegen. Bearbeitet slots/slots.json auf Disk — dieselbe Datei
    wie der Konsolen-Slot-Editor; danach im Hauptprozess Item-Scan-Menü neu
    aufrufen, um die geänderten Slots zu sehen.
    """
    import subprocess

    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return

    try:
        subprocess.Popen([sys.executable, "-m", "autoclicker.scan_studio"])
    except OSError as e:
        print(f"\n{err(f'Konnte Scan-Studio nicht starten: {e}')}")
        return

    print(f"\n{col('[SCAN-STUDIO]', 'cyan')} Visuelles Scan-Studio geöffnet.")
    print(f"     Slots werden in {col('slots/slots.json', 'yellow')} gespeichert.")


def handle_quit(state: AutoClickerState, main_thread_id: int) -> None:
    """Beendet das Programm."""
    print(f"\n{col('[QUIT]', 'red')} Beende Programm...")

    # Falls noch eine Aufnahme läuft, den Maus-Hook sauber entfernen.
    with state.lock:
        was_recording = state.recording_active
        state.recording_active = False
    if was_recording:
        from .winapi import remove_mouse_hook
        remove_mouse_hook()

    state.stop_event.set()
    state.quit_event.set()

    WM_QUIT = 0x0012
    user32.PostThreadMessageW(main_thread_id, WM_QUIT, 0, 0)
