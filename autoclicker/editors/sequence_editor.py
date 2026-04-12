"""
Sequenz-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Klick-Sequenzen.
"""

import re
import time
from pathlib import Path
from typing import Optional

from ..models import ClickPoint, ElseConfig, WaitCondition, SequenceStep, LoopPhase, Sequence, AutoClickerState, ELSE_CLICK
from ..utils import safe_input, is_cancel, confirm, interactive_select, col, ok, err, info, warn, header, hint, cmd_hint, breadcrumb, suggest_command, coord_context, cancel_hint, parse_non_negative_float, parse_non_negative_range
from ..winapi import get_cursor_pos, VK_CODES
from ..persistence import (
    save_data, save_sequence_file, list_available_sequences, load_sequence_file,
    get_next_point_id, get_point_by_id, SCREENSHOTS_DIR
)
from ..imaging import PILLOW_AVAILABLE, get_pixel_color, select_region



def apply_else_to_step(step: SequenceStep, else_parts: list, state: AutoClickerState) -> None:
    """Wendet eine geparste ELSE-Bedingung auf einen SequenceStep an.

    Vermeidet die 3-fache Duplizierung des Else-Anwendungscodes.
    """
    if not else_parts:
        return
    if not step.wait_condition and not step.item_scan:
        print(warn("  -> 'else' hat keine Wirkung ohne 'pixel'/'gone' oder 'scan'-Bedingung!"))
        return
    else_result = parse_else_condition(else_parts, state)
    if else_result:
        step.else_config = ElseConfig(
            action=else_result["else_action"],
            x=else_result.get("else_x", 0),
            y=else_result.get("else_y", 0),
            delay=else_result.get("else_delay", 0),
            key=else_result.get("else_key"),
            name=else_result.get("else_name", "")
        )


def capture_pixel_color() -> tuple:
    """Erfasst eine Pixelfarbe an der aktuellen Mausposition.

    Zeigt Anweisung an, wartet auf Enter, liest Farbe.

    Returns:
        (x, y, color) oder (None, None, None) wenn fehlgeschlagen.
    """
    if not PILLOW_AVAILABLE:
        print("  -> Pillow nicht installiert!")
        return None, None, None
    print("  Bewege Maus zum Pixel, dann Enter...")
    safe_input()
    x, y = get_cursor_pos()
    color = get_pixel_color(x, y)
    if not color:
        print("  -> Farbe konnte nicht gelesen werden!")
        return None, None, None
    return x, y, color


def run_sequence_editor(state: AutoClickerState) -> None:
    """Interaktiver Sequenz-Editor - neu erstellen oder bestehende bearbeiten."""
    print(header("SEQUENZ-EDITOR"))
    print(f"  {breadcrumb('Hauptmenü', 'Sequenz-Editor')}")

    with state.lock:
        if not state.points:
            print(f"\n{err('Erst Punkte aufnehmen')} {hint('(CTRL+ALT+A)')}")
            return

    # Bestehende Sequenzen einmal laden und cachen
    available_sequences = list_available_sequences()
    loaded_sequences = []
    menu_options = ["Neue Sequenz erstellen"]
    for name, path in available_sequences:
        seq = load_sequence_file(path)
        if seq:
            loaded_sequences.append(seq)
            menu_options.append(str(seq))

    choice = interactive_select(menu_options, title="\nWas möchtest du tun?")

    if choice == -1:
        print(f"{col('[CANCEL]', 'yellow')} Editor beendet.")
        return
    elif choice == 0:
        edit_sequence(state, None)
    elif 1 <= choice < len(menu_options):
        edit_sequence(state, loaded_sequences[choice - 1])


def _remap_sequence_to_local_points(state: AutoClickerState, sequence: Sequence,
                                    filepath: 'Path') -> None:
    """Mappt Sequenz-Koordinaten auf lokale Punkte (nach Name).

    Nützlich wenn eine Sequenz von einem anderen PC kopiert wurde und die
    Koordinaten an den lokalen Bildschirm angepasst werden müssen.
    Speichert direkt in die Originaldatei.
    """
    # Lokale Punkte nach Name indexieren
    with state.lock:
        local_by_name = {p.name: p for p in state.points if p.name}

    if not local_by_name:
        return

    all_steps = (
        sequence.init_steps +
        [s for lp in sequence.loop_phases for s in lp.steps] +
        sequence.end_steps
    )

    # Erst analysieren: was würde sich ändern, was fehlt?
    updates = []  # (step, attr_prefix, old_x, old_y, new_x, new_y, name)
    missing = set()

    for step in all_steps:
        # Haupt-Klick-Punkt
        if not step.wait_only and not step.key_press and not step.item_scan:
            if step.name and (step.x != 0 or step.y != 0):
                if step.name in local_by_name:
                    lp = local_by_name[step.name]
                    if step.x != lp.x or step.y != lp.y:
                        updates.append((step, "main", step.x, step.y, lp.x, lp.y, step.name))
                else:
                    missing.add(step.name)

        # Else-Klick-Punkt
        ec = step.else_config
        if ec and ec.action == ELSE_CLICK and ec.name:
            if ec.name in local_by_name:
                lp = local_by_name[ec.name]
                if ec.x != lp.x or ec.y != lp.y:
                    updates.append((step, "else", ec.x, ec.y, lp.x, lp.y, ec.name))
            elif ec.x != 0 or ec.y != 0:
                missing.add(ec.name)

    if not updates and not missing:
        return

    # Fehlende Punkte melden
    if missing:
        print(f"\n{warn(f'{len(missing)} Punkt(e) fehlen lokal (bitte erst aufnehmen):')}")
        for name in sorted(missing):
            print(f"    - '{name}'")

    # Automatisch auf lokale Koordinaten aktualisieren
    if updates:
        unique_names = {u[6] for u in updates}
        print(f"\n{info(f'{len(unique_names)} Punkt(e) auf lokale Koordinaten aktualisiert:')}")
        shown = set()
        for _, _, old_x, old_y, new_x, new_y, name in updates:
            if name not in shown:
                shown.add(name)
                print(f"    '{name}': ({old_x},{old_y}) -> ({new_x},{new_y})")

        for step, prefix, _, _, new_x, new_y, _ in updates:
            if prefix == "main":
                step.x = new_x
                step.y = new_y
            else:
                step.else_config.x = new_x
                step.else_config.y = new_y
        # Direkt in die Originaldatei speichern
        save_sequence_file(sequence, filepath)
        print(f"    {ok('Gespeichert in')} {filepath.name}")


def run_sequence_loader(state: AutoClickerState) -> None:
    """Lädt eine gespeicherte Sequenz."""
    sequences = list_available_sequences()

    if not sequences:
        print(f"\n{info('Keine Sequenzen gefunden!')}")
        print(f"       Erstelle eine mit {col('CTRL+ALT+E', 'yellow')} (Sequenz-Editor)")
        return

    # Sequenzen einmal laden und cachen
    with state.lock:
        active_name = state.active_sequence.name if state.active_sequence else None
    loaded_sequences = []  # (seq, filepath) Paare
    menu_options = []
    for name, path in sequences:
        seq = load_sequence_file(path)
        if seq:
            loaded_sequences.append((seq, path))
            active_marker = " *AKTIV*" if active_name and active_name == seq.name else ""
            menu_options.append(f"{seq}{active_marker}")

    choice = interactive_select(menu_options, title="\nSEQUENZ LADEN:")

    if choice == -1 or choice >= len(loaded_sequences):
        return

    seq, seq_path = loaded_sequences[choice]

    # Koordinaten auf lokale Punkte anpassen (z.B. nach Kopie von anderem PC)
    _remap_sequence_to_local_points(state, seq, seq_path)

    with state.lock:
        state.active_sequence = seq
    print(f"\n{col('[ERFOLG]', 'green')} Sequenz '{seq.name}' geladen!\n")


def edit_sequence(state: AutoClickerState, existing: Optional[Sequence]) -> None:
    """Bearbeitet eine Sequenz (neu oder bestehend) mit Start + mehreren Loop-Phasen."""

    if existing:
        print(f"\n--- Bearbeite Sequenz: {existing.name} ---")
        seq_name = existing.name
        init_steps = list(existing.init_steps)
        loop_phases = [LoopPhase(lp.name, list(lp.steps), lp.repeat, lp.scheduled_start) for lp in existing.loop_phases]
        end_steps = list(existing.end_steps)
        total_cycles = existing.total_cycles
    else:
        print("\n--- Neue Sequenz erstellen ---")
        seq_name = safe_input("Name der Sequenz: ").strip()
        if not seq_name:
            seq_name = f"Sequenz_{int(time.time())}"
        init_steps = []
        loop_phases = []
        end_steps = []
        total_cycles = 1

    # Verfügbare Punkte anzeigen
    with state.lock:
        print("\nVerfügbare Punkte:")
        for p in state.points:
            print(f"  {p}")

    # INIT-Phase bearbeiten (einmalig vor allen Zyklen)
    print(header("PHASE 0: INIT-SEQUENZ (wird einmalig vor allen Zyklen ausgeführt)"))
    print("  (Optional: Login, Vorbereitung, etc. – läuft nur beim allerersten Start)")
    result = edit_phase(state, init_steps, "INIT")
    if result is None:
        print(f"{col('[ABBRUCH]', 'yellow')} Sequenz nicht gespeichert.")
        return
    init_steps = result

    # LOOP-Phasen bearbeiten (mehrere möglich)
    print(header("PHASE 1: LOOP-PHASEN (können mehrere sein)"))
    loop_phases = edit_loop_phases(state, loop_phases)
    if loop_phases is None:
        print(f"{col('[ABBRUCH]', 'yellow')} Sequenz nicht gespeichert.")
        return

    # Gesamt-Zyklen abfragen
    if loop_phases:
        print(header("GESAMT-WIEDERHOLUNGEN"))
        print("\nAblauf: INIT (1x) -> Loop1 -> Loop2 -> ... -> (wieder von vorne?) -> END (1x)")
        print("\nWie oft soll der GESAMTE Ablauf wiederholt werden?")
        print("  0 = Unendlich (manuell stoppen)")
        print("  1 = Einmal durchlaufen und stoppen")
        print("  >1 = X-mal wiederholen (Loop1 -> Loop2 -> ... -> Loop1 -> ...)")
        try:
            cycles_input = safe_input(f"\nAnzahl Zyklen (Enter = {total_cycles}): ").strip()
            if cycles_input:
                total_cycles = int(cycles_input)
                if total_cycles < 0:
                    total_cycles = 0
        except ValueError:
            print(f"Ungültige Eingabe, behalte {total_cycles}.")

    # END-Phase bearbeiten (optional)
    print("\n" + "=" * 60)
    print("  PHASE 3: END-SEQUENZ (wird einmal am Ende ausgeführt)")
    print("=" * 60)
    print("\n  (Optional: Aufräumen, Logout, etc.)")
    result = edit_phase(state, end_steps, "END")
    if result is None:
        print(f"{col('[ABBRUCH]', 'yellow')} Sequenz nicht gespeichert.")
        return
    end_steps = result

    # Pre-Save Summary: Zeige was sich geändert hat
    print(f"\n{col('Zusammenfassung:', 'bold')}")
    if existing:
        changes = []
        old_i, new_i = len(existing.init_steps), len(init_steps)
        if old_i != new_i:
            changes.append(f"  Init: {old_i} → {new_i} Schritte")

        old_l, new_l = len(existing.loop_phases), len(loop_phases)
        if old_l != new_l:
            changes.append(f"  Loop-Phasen: {old_l} → {new_l}")
        for i, lp in enumerate(loop_phases):
            if i < len(existing.loop_phases):
                old_lp = existing.loop_phases[i]
                if len(lp.steps) != len(old_lp.steps) or lp.repeat != old_lp.repeat:
                    changes.append(f"    {lp.name}: {len(old_lp.steps)}x{old_lp.repeat} → {len(lp.steps)}x{lp.repeat}")
            else:
                changes.append(f"    {lp.name}: {col('NEU', 'green')} ({len(lp.steps)} Schritte x{lp.repeat})")

        old_e, new_e = len(existing.end_steps), len(end_steps)
        if old_e != new_e:
            changes.append(f"  End: {old_e} → {new_e} Schritte")

        if existing.total_cycles != total_cycles:
            changes.append(f"  Zyklen: {existing.total_cycles} → {total_cycles}")

        if changes:
            print(col("  Änderungen:", "yellow"))
            for c in changes:
                print(f"  {c}")
        else:
            print(f"  {hint('Keine Änderungen')}")
    else:
        print(f"  {col('Neue Sequenz:', 'green')} '{seq_name}'")
        if init_steps:
            print(f"    Init: {len(init_steps)} Schritte (einmalig)")
        for lp in loop_phases:
            print(f"    {lp.name}: {len(lp.steps)} Schritte x{lp.repeat}")
        if end_steps:
            print(f"    End: {len(end_steps)} Schritte")
        cycles_desc = "Unendlich" if total_cycles == 0 else f"{total_cycles}x"
        print(f"    Zyklen: {cycles_desc}")

    # Sequenz erstellen und speichern
    new_sequence = Sequence(
        name=seq_name,
        init_steps=init_steps,
        loop_phases=loop_phases,
        end_steps=end_steps,
        total_cycles=total_cycles
    )

    with state.lock:
        state.sequences[seq_name] = new_sequence
        state.active_sequence = new_sequence

    save_data(state)

    # Zusammenfassung
    all_steps = init_steps + [s for lp in loop_phases for s in lp.steps] + end_steps
    pixel_triggers = sum(1 for s in all_steps if s.wait_condition)

    print(f"\n{col('[ERFOLG]', 'green')} Sequenz '{seq_name}' gespeichert!")
    for i, lp in enumerate(loop_phases):
        print(f"         {lp.name}: {len(lp.steps)} Schritte x{lp.repeat}")
    if end_steps:
        print(f"         End: {len(end_steps)} Schritte (einmal am Ende)")
    if total_cycles == 0:
        print(f"         Gesamt: Unendlich wiederholen")
    elif total_cycles == 1:
        print(f"         Gesamt: Einmal durchlaufen")
    else:
        print(f"         Gesamt: {total_cycles}x wiederholen")
    if pixel_triggers > 0:
        print(f"         Farb-Trigger: {pixel_triggers} Schritt(e)")
    print()


def _parse_time_input(time_str: str) -> Optional[str]:
    """Parst eine Uhrzeit-Eingabe (z.B. '12:30', '9:05') und gibt 'HH:MM' zurück oder None."""
    match = re.match(r'^(\d{1,2}):(\d{2})$', time_str.strip())
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    print(err(f"  Ungültige Zeit '{time_str}' – Format: HH:MM (z.B. 12:30)"))
    return None


def edit_loop_phases(state: AutoClickerState, loop_phases: list[LoopPhase]) -> Optional[list[LoopPhase]]:
    """Bearbeitet mehrere Loop-Phasen.

    Returns:
        Liste der Loop-Phasen bei 'fertig', None bei 'cancel'.
    """

    if loop_phases:
        print(f"\nAktuelle Loop-Phasen ({len(loop_phases)}):")
        for i, lp in enumerate(loop_phases):
            print(f"  {i+1}. {lp}")

    def _print_loops_help():
        print("\n" + "-" * 60)
        print("Befehle:")
        print("  add            - Neue Loop-Phase hinzufügen")
        print("  edit <Nr>      - Loop-Phase bearbeiten (z.B. 'edit 1')")
        print("  del <Nr>       - Loop-Phase löschen")
        print("  del <Nr>-<Nr>  - Bereich löschen (z.B. del 1-3)")
        print("  del all        - ALLE Loop-Phasen löschen")
        print("  time <Nr>      - Startzeit setzen/ändern (z.B. 'time 1')")
        print("  show / s       - Alle Loop-Phasen anzeigen")
        print(f"  help / ? | done / d | cancel / {cancel_hint()}")
        print("-" * 60)

    _print_loops_help()

    while True:
        try:
            prompt = f"[LOOPS: {len(loop_phases)}]"
            user_input = safe_input(f"{prompt} > ").strip().lower()

            if user_input in ("done", "d"):
                return loop_phases
            elif is_cancel(user_input):
                return None  # Abbruch signalisieren
            elif user_input == "":
                continue
            elif user_input in ("help", "?"):
                _print_loops_help()
                continue
            elif user_input in ("show", "s"):
                if loop_phases:
                    print(f"\nLoop-Phasen:")
                    for i, lp in enumerate(loop_phases):
                        print(f"  {i+1}. {lp}")
                        for j, step in enumerate(lp.steps):
                            print(f"       {j+1}. {step}")
                else:
                    print("  (Keine Loop-Phasen)")
                continue
            elif user_input == "add":
                # Neue Loop-Phase
                loop_num = len(loop_phases) + 1
                loop_name = safe_input(f"  Name der Loop-Phase (Enter = 'Loop {loop_num}'): ").strip()
                if not loop_name:
                    loop_name = f"Loop {loop_num}"

                print(f"\n  Schritte für {loop_name} hinzufügen:")
                steps = edit_phase(state, [], loop_name)
                if steps is None:
                    return None  # Abbruch durchreichen

                repeat = 1
                try:
                    repeat_input = safe_input(f"  Wie oft soll {loop_name} wiederholt werden? (Enter = 1): ").strip()
                    if repeat_input:
                        repeat = max(1, int(repeat_input))
                except ValueError:
                    repeat = 1

                # Geplante Startzeit abfragen
                scheduled_start = None
                print(hint("  (Phase wird nur zur angegebenen Uhrzeit ausgeführt, sonst übersprungen)"))
                time_input = safe_input(f"  Startzeit? (z.B. '12:30', Enter = sofort): ").strip()
                if time_input:
                    scheduled_start = _parse_time_input(time_input)

                loop_phases.append(LoopPhase(loop_name, steps, repeat, scheduled_start=scheduled_start))
                time_info = f", Start: {scheduled_start}" if scheduled_start else ""
                print(f"  + {loop_name} hinzugefügt ({len(steps)} Schritte x{repeat}{time_info})")
                continue

            elif user_input.startswith("edit "):
                try:
                    edit_num = int(user_input[5:])
                    if 1 <= edit_num <= len(loop_phases):
                        lp = loop_phases[edit_num - 1]
                        print(f"\n  Bearbeite {lp.name}:")
                        new_steps = edit_phase(state, lp.steps, lp.name)
                        if new_steps is None:
                            return None  # Abbruch durchreichen
                        lp.steps = new_steps
                        try:
                            repeat_input = safe_input(f"  Wiederholungen (aktuell {lp.repeat}, Enter = behalten): ").strip()
                            if repeat_input:
                                lp.repeat = max(1, int(repeat_input))
                        except ValueError:
                            pass
                        # Geplante Startzeit bearbeiten
                        current_time = lp.scheduled_start or "sofort"
                        time_input = safe_input(f"  Startzeit (aktuell {current_time}, Enter = behalten, '0' = entfernen): ").strip()
                        if time_input == "0":
                            lp.scheduled_start = None
                        elif time_input:
                            lp.scheduled_start = _parse_time_input(time_input)
                        print(f"  + {lp.name} aktualisiert")
                    else:
                        print(f"  -> Ungültige Nr! Verfügbar: 1-{len(loop_phases)}")
                except ValueError:
                    print("  -> Format: edit <Nr>")
                continue

            elif user_input == "del all":
                if not loop_phases:
                    print("  -> Keine Loop-Phasen vorhanden!")
                    continue
                if confirm(f"  {len(loop_phases)} Loop-Phase(n) wirklich löschen?"):
                    count = len(loop_phases)
                    loop_phases.clear()
                    print(f"  + {count} Loop-Phase(n) gelöscht!")
                else:
                    print("  -> Abgebrochen")
                continue

            elif user_input.startswith("del ") and "-" in user_input[4:]:
                # Bereich löschen: del 1-3
                try:
                    range_part = user_input[4:]
                    start, end = map(int, range_part.split("-"))
                    if start < 1 or end > len(loop_phases) or start > end:
                        print(f"  -> Ungültiger Bereich! Verfügbar: 1-{len(loop_phases)}")
                        continue
                    count = end - start + 1
                    if confirm(f"  {count} Loop-Phase(n) ({start}-{end}) wirklich löschen?"):
                        del loop_phases[start-1:end]
                        print(f"  + {count} Loop-Phase(n) gelöscht!")
                    else:
                        print("  -> Abgebrochen")
                except ValueError:
                    print("  -> Format: del <Nr>-<Nr>")
                continue

            elif user_input.startswith("del "):
                try:
                    del_num = int(user_input[4:])
                    if 1 <= del_num <= len(loop_phases):
                        removed = loop_phases.pop(del_num - 1)
                        print(f"  + {removed.name} gelöscht")
                    else:
                        print(f"  -> Ungültige Nr! Verfügbar: 1-{len(loop_phases)}")
                except ValueError:
                    print("  -> Format: del <Nr>")
                continue

            elif user_input.startswith("time "):
                try:
                    time_num = int(user_input[5:])
                    if 1 <= time_num <= len(loop_phases):
                        lp = loop_phases[time_num - 1]
                        current_time = lp.scheduled_start or "sofort"
                        time_input = safe_input(f"  Startzeit für '{lp.name}' (aktuell {current_time}, '0' = entfernen): ").strip()
                        if time_input == "0":
                            lp.scheduled_start = None
                            print(f"  + Startzeit für '{lp.name}' entfernt")
                        elif time_input:
                            parsed = _parse_time_input(time_input)
                            if parsed:
                                lp.scheduled_start = parsed
                                print(f"  + '{lp.name}' startet ab jetzt um {parsed}")
                    else:
                        print(f"  -> Ungültige Nr! Verfügbar: 1-{len(loop_phases)}")
                except ValueError:
                    print("  -> Format: time <Nr>")
                continue

            else:
                _known = ["add", "edit", "del", "show", "time", "help", "done", "cancel"]
                suggestion = suggest_command(user_input, _known)
                print(f"  -> Unbekannter Befehl.{suggestion} {hint('(? = Hilfe)')}")

        except (KeyboardInterrupt, EOFError):
            raise


def parse_else_condition(else_parts: list[str], state: AutoClickerState) -> dict:
    """Parst eine ELSE-Bedingung und gibt ein Dict mit den Else-Feldern zurück.

    Formate:
    - else skip          -> überspringen
    - else skip_cycle    -> aktuellen Zyklus abbrechen, nächster startet
    - else restart       -> Sequenz neu starten
    - else <Nr> [delay]  -> Punkt klicken (optional mit Verzögerung)
    - else key <Taste>   -> Taste drücken

    Gibt leeres Dict zurück wenn Parsing fehlschlägt.
    """
    if not else_parts:
        return {}

    first = else_parts[0].lower()

    # else skip
    if first == "skip":
        return {"else_action": "skip"}

    # else skip_cycle
    if first == "skip_cycle":
        return {"else_action": "skip_cycle"}

    # else restart
    if first == "restart":
        return {"else_action": "restart"}

    # else key <Taste>
    if first == "key" and len(else_parts) >= 2:
        key_name = else_parts[1].lower()
        if key_name in VK_CODES:
            return {"else_action": "key", "else_key": key_name}
        print(f"  -> Unbekannte Taste: '{key_name}'")
        return {}

    # else <ID> [delay] - Punkt klicken (per ID)
    try:
        point_id = int(first)
        with state.lock:
            point = get_point_by_id(state, point_id)
            if point:
                result = {
                    "else_action": "click",
                    "else_x": point.x,
                    "else_y": point.y,
                    "else_name": point.name or f"Punkt #{point_id}"
                }
                # Optional: Delay
                if len(else_parts) >= 2:
                    try:
                        result["else_delay"] = float(else_parts[1])
                    except ValueError:
                        pass
                return result
            else:
                print(f"  -> Punkt #{point_id} nicht gefunden!")
                return {}
    except ValueError:
        pass

    print(f"  -> Unbekanntes ELSE-Format: {' '.join(else_parts)}")
    print("     Formate: else skip | else skip_cycle | else restart | else <Nr> [delay] | else key <Taste>")
    return {}


def _print_phase_help(full: bool = False) -> None:
    """Zeigt die Hilfe für den Phase-Editor an.

    Args:
        full: Wenn True, vollständige Hilfe anzeigen. Sonst Kurzübersicht.
    """
    if not full:
        print("\n" + "-" * 60)
        print("  Kurzübersicht (? / ?? = vollständige Hilfe):")
        print(cmd_hint("<Nr> <Zeit>", "Warte Xs, klicke Punkt    (z.B. '1 30')"))
        print(cmd_hint("scan <Name>", "Item-Scan ausführen"))
        print(cmd_hint("boss <Name>", "Boss-Scan (erkennt Boss → Aktion)"))
        print(cmd_hint("key <Taste>", "Taste drücken              (z.B. 'key enter')"))
        print(cmd_hint("wait <Zeit>", "Nur warten, kein Klick"))
        print(cmd_hint("del <Nr>", "Schritt löschen"))
        print(cmd_hint("screenshot / ss", "Screenshot-Schritt (Bereich wählen)"))
        print(cmd_hint(f"done / d | cancel / {cancel_hint()}", "Fertig / Abbrechen"))
        print("-" * 60)
        return

    print("\n" + "-" * 60)
    print("Befehle (Logik: erst warten, DANN klicken):")
    print(cmd_hint("<Nr> <Zeit>", "Warte Xs, dann klicke (z.B. '1 30')"))
    print(cmd_hint("<Nr> <Min>-<Max>", "Zufällig warten (z.B. '1 30-45')"))
    print(cmd_hint("<Nr> 0", "Sofort klicken"))
    print(cmd_hint("<Nr> pixel", "Warte auf Farbe, dann klicke"))
    print(cmd_hint("<Nr> <Zeit> pixel", "Erst Xs warten, dann auf Farbe"))
    print(cmd_hint("<Nr> gone", "Warte bis Farbe WEG, dann klicke"))
    print(cmd_hint("<Nr> <Zeit> gone", "Erst Xs warten, dann bis Farbe WEG"))
    print(cmd_hint("wait <Zeit>", "Nur warten, KEIN Klick (z.B. 'wait 10')"))
    print(cmd_hint("wait <Min>-<Max>", "Zufällig warten (z.B. 'wait 30-45')"))
    print(cmd_hint("wait pixel", "Auf Farbe warten, KEIN Klick"))
    print(cmd_hint("wait gone", "Warten bis Farbe WEG ist, KEIN Klick"))
    print(cmd_hint("key <Taste>", "Taste sofort drücken (z.B. 'key enter')"))
    print(cmd_hint("key <Zeit> <Taste>", "Warten, dann Taste (z.B. 'key 5 space')"))
    print(cmd_hint("key <Min>-<Max> <Taste>", "Zufällig warten, dann Taste (z.B. 'key 5-10 space')"))
    print(cmd_hint("scan <Name>", "Item-Scan: bestes pro Kategorie (Standard)"))
    print(cmd_hint("scan <Name> best", "Item-Scan: nur 1 Item total"))
    print(cmd_hint("scan <Name> every", "Item-Scan: alle Treffer (für Duplikate)"))
    print(cmd_hint("boss <Name>", "Boss-Scan: Boss erkennen → bedingte Aktion"))
    print("ELSE-Bedingungen (falls Scan/Pixel/Boss fehlschlägt):")
    print(cmd_hint("... else skip", "Schritt überspringen, weiter (z.B. 'scan items else skip')"))
    print(cmd_hint("... else skip_cycle", "Zyklus abbrechen, nächster startet (z.B. 'scan items else skip_cycle')"))
    print(cmd_hint("... else restart", "Sequenz neu starten (z.B. 'scan items else restart')"))
    print(cmd_hint("... else <Nr> [s]", "Punkt klicken (z.B. 'scan items else 2 5')"))
    print(cmd_hint("... else key <T>", "Taste drücken (z.B. '1 pixel else key enter')"))
    print("Punkte verwalten:")
    print(cmd_hint("learn <Name>", "Neuen Punkt erstellen"))
    print(cmd_hint("points", "Alle Punkte anzeigen"))
    print(cmd_hint("del <Nr>", "Schritt löschen"))
    print(cmd_hint("del <Nr>-<Nr>", "Bereich löschen (z.B. del 1-5)"))
    print(cmd_hint("del all", "ALLE Schritte löschen"))
    print(cmd_hint("ins <Nr>", "Nächsten Schritt an Position einfügen"))
    print("Screenshot-Schritt (wird bei Ausführung automatisch gemacht):")
    print(cmd_hint("screenshot / ss", "Bereich interaktiv wählen → Schritt erstellen"))
    print(cmd_hint("screenshot full", "Vollbild-Screenshot-Schritt erstellen"))
    print(cmd_hint("screenshot x1 y1 x2 y2", "Direkte Koordinaten (z.B. 'screenshot 0 0 800 600')"))
    print(cmd_hint(f"help | ? / ?? | show | done | cancel | {cancel_hint()}", ""))
    print("-" * 60)


def edit_phase(state: AutoClickerState, steps: list[SequenceStep], phase_name: str) -> Optional[list[SequenceStep]]:
    """Bearbeitet eine Phase (Start oder Loop) der Sequenz.

    Returns:
        Liste der Schritte bei 'fertig', None bei 'cancel'.
    """

    if steps:
        print(f"\nAktuelle {phase_name}-Schritte ({len(steps)}):")
        for i, step in enumerate(steps):
            print(f"  {i+1}. {step}")

    _print_phase_help()

    insert_position = None     # None = am Ende anfügen, Zahl = an Position einfügen

    def add_step(step):
        """Fügt Schritt hinzu - entweder an insert_position oder am Ende."""
        nonlocal insert_position
        if insert_position is not None:
            steps.insert(insert_position - 1, step)
            print(f"  + Eingefügt an Position {insert_position}: {step}")
            insert_position = None  # Reset nach Einfügen
        else:
            steps.append(step)
            print(f"  + Hinzugefügt: {step}")

    while True:
        try:
            # Zeige Insert-Modus im Prompt an
            if insert_position is not None:
                prompt = f"[{phase_name}: {len(steps)}] (ins->{insert_position})"
            else:
                prompt = f"[{phase_name}: {len(steps)}]"
            user_input = safe_input(f"{prompt} > ").strip()

            if user_input.lower() in ("done", "d"):
                return steps
            elif is_cancel(user_input):
                print(col("[CANCEL]", "yellow") + " Phase abgebrochen.")
                return None
            elif user_input.lower() == "":
                continue
            elif user_input.lower() == "help":
                _print_phase_help()
                continue
            elif user_input.lower() in ("?", "help full", "??"):
                _print_phase_help(full=True)
                continue
            elif user_input.lower() in ("show", "s"):
                if steps:
                    print(f"\n{phase_name}-Schritte:")
                    for i, step in enumerate(steps):
                        print(f"  {i+1}. {step}")
                else:
                    print("  (Keine Schritte)")
                continue
            elif user_input.lower() == "del all":
                if not steps:
                    print("  -> Keine Schritte vorhanden!")
                    continue
                count = len(steps)
                steps.clear()
                print(f"  + Alle {count} Schritte gelöscht")
                continue
            elif user_input.lower().startswith("del ") and "-" in user_input[4:]:
                # Bereich löschen: del 1-5
                try:
                    range_str = user_input[4:].strip()
                    parts = range_str.split("-")
                    start = int(parts[0])
                    end = int(parts[1])
                    if start < 1 or end > len(steps) or start > end:
                        print(f"  -> Ungültiger Bereich! Verfügbar: 1-{len(steps)}")
                        continue
                    # Von hinten löschen um Indexe nicht zu verschieben
                    removed_count = 0
                    for i in range(end, start - 1, -1):
                        steps.pop(i - 1)
                        removed_count += 1
                    print(f"  + {removed_count} Schritte gelöscht ({start}-{end})")
                except (ValueError, IndexError):
                    print("  -> Format: del <start>-<end> (z.B. del 1-5)")
                continue
            elif user_input.lower().startswith("del "):
                try:
                    del_num = int(user_input[4:])
                    if 1 <= del_num <= len(steps):
                        removed = steps.pop(del_num - 1)
                        print(f"  + Schritt {del_num} gelöscht: {removed}")
                    else:
                        print(f"  -> Ungültiger Schritt! Verfügbar: 1-{len(steps)}")
                except ValueError:
                    print("  -> Format: del <Nr>")
                continue

            elif user_input.lower().startswith("ins "):
                # Insert-Modus: nächster Schritt wird an Position eingefügt
                try:
                    pos = int(user_input[4:])
                    if pos < 1:
                        print("  -> Position muss >= 1 sein!")
                        continue
                    if pos > len(steps) + 1:
                        print(f"  -> Position zu groß! Max: {len(steps) + 1}")
                        continue
                    insert_position = pos
                    print(f"  + Insert-Modus: Nächster Schritt wird an Position {pos} eingefügt")
                    print(f"    (Abbrechen mit 'ins 0' oder 'ins end')")
                except ValueError:
                    print("  -> Format: ins <Nr>")
                continue

            elif user_input.lower() in ("ins 0", "ins end"):
                if insert_position is not None:
                    insert_position = None
                    print("  + Insert-Modus beendet - Schritte werden wieder am Ende angefügt")
                else:
                    print("  -> Insert-Modus war nicht aktiv")
                continue

            elif user_input.lower() in ("points", "p"):
                # Alle Punkte anzeigen
                with state.lock:
                    if state.points:
                        print("\n  Verfügbare Punkte:")
                        for p in state.points:
                            print(f"    {p}")
                    else:
                        print("  (Keine Punkte vorhanden)")
                continue

            elif user_input.lower().startswith("learn"):
                # Neuen Punkt erstellen
                # Format: "learn" oder "learn <Name>"
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    point_name = parts[1].strip()
                else:
                    point_name = safe_input("  Punkt-Name: ").strip()
                    if not point_name or is_cancel(point_name):
                        print("  -> Abgebrochen")
                        continue

                print(f"\n  Bewege die Maus zur Position für '{point_name}'")
                print("  Drücke Enter...")
                safe_input()
                x, y = get_cursor_pos()

                with state.lock:
                    new_id = get_next_point_id(state)
                    new_point = ClickPoint(x, y, point_name, new_id)
                    state.points.append(new_point)

                save_data(state)
                print(f"  + Punkt #{new_id} '{point_name}' erstellt bei {coord_context(x, y)}")
                continue

            # === SCAN-BEFEHL ===
            elif user_input.lower().startswith("scan "):
                parts_raw = user_input.split()
                # Parse else-Bedingung
                else_parts = []
                main_parts = []
                in_else = False
                for p in parts_raw[1:]:  # Skip "scan"
                    if p.lower() == "else":
                        in_else = True
                        continue
                    if in_else:
                        else_parts.append(p)
                    else:
                        main_parts.append(p)

                if not main_parts:
                    print("  -> Format: scan <Name> [best|every] [else ...]")
                    continue

                scan_name = main_parts[0]
                mode = "all"
                if len(main_parts) > 1:
                    mode_str = main_parts[1].lower()
                    if mode_str in ("best", "every"):
                        mode = mode_str

                step = SequenceStep(
                    x=0, y=0, delay_before=0,
                    name=f"Scan:{scan_name}",
                    item_scan=scan_name,
                    item_scan_mode=mode
                )

                apply_else_to_step(step, else_parts, state)
                add_step(step)
                continue

            # === BOSS-SCAN-BEFEHL ===
            elif user_input.lower().startswith("boss "):
                parts_raw = user_input.split()
                # Parse else-Bedingung
                else_parts = []
                main_parts = []
                in_else = False
                for p in parts_raw[1:]:  # Skip "boss"
                    if p.lower() == "else":
                        in_else = True
                        continue
                    if in_else:
                        else_parts.append(p)
                    else:
                        main_parts.append(p)

                if not main_parts:
                    print("  -> Format: boss <Name> [else ...]")
                    continue

                boss_name = main_parts[0]

                step = SequenceStep(
                    x=0, y=0, delay_before=0,
                    name=f"Boss:{boss_name}",
                    boss_scan=boss_name,
                )

                apply_else_to_step(step, else_parts, state)
                add_step(step)
                continue

            # === KEY-BEFEHL ===
            elif user_input.lower().startswith("key "):
                parts = user_input.split()
                if len(parts) < 2:
                    print("  -> Format: key <Taste> oder key <Zeit> <Taste> oder key <Min>-<Max> <Taste>")
                    continue

                # key <Taste> oder key <Zeit> <Taste> oder key <Min>-<Max> <Taste>
                delay = 0
                delay_max = None
                key_name = None

                if len(parts) == 2:
                    # key <Taste>
                    key_name = parts[1].lower()
                else:
                    # key <Zeit> <Taste> oder key <Min>-<Max> <Taste>
                    if "-" in parts[1]:
                        range_val, range_err = parse_non_negative_range(parts[1], "Verzögerung")
                        if range_err:
                            print(f"  -> {range_err}")
                            print("     Format: key <Min>-<Max> <Taste> (z.B. key 5-10 enter)")
                            continue
                        delay, delay_max = range_val
                    else:
                        delay_val, delay_err = parse_non_negative_float(parts[1], "Verzögerung")
                        if delay_err:
                            print(f"  -> {delay_err}")
                            print("     Format: key <Taste> oder key <Zeit> <Taste>")
                            continue
                        delay = delay_val
                    key_name = parts[2].lower()

                if key_name not in VK_CODES:
                    print(f"  -> Unbekannte Taste: '{key_name}'")
                    print(f"     Verfügbar: {', '.join(sorted(VK_CODES.keys())[:20])}...")
                    continue

                step = SequenceStep(
                    x=0, y=0, delay_before=delay, delay_max=delay_max,
                    name=f"Key:{key_name}",
                    key_press=key_name
                )
                add_step(step)
                continue

            # === WAIT-BEFEHL ===
            elif user_input.lower().startswith("wait "):
                parts_raw = user_input.split()
                # Parse else-Bedingung
                else_parts = []
                main_parts = []
                in_else = False
                for p in parts_raw[1:]:  # Skip "wait"
                    if p.lower() == "else":
                        in_else = True
                        continue
                    if in_else:
                        else_parts.append(p)
                    else:
                        main_parts.append(p)

                if not main_parts:
                    print("  -> Format: wait <Zeit> oder wait pixel oder wait gone")
                    continue

                arg = main_parts[0].lower()
                step = SequenceStep(x=0, y=0, delay_before=0, name="Wait", wait_only=True)

                if arg in ("pixel", "gone"):
                    px, py, color = capture_pixel_color()
                    if color is None:
                        continue
                    step.wait_condition = WaitCondition(
                        pixel=(px, py), color=color,
                        until_gone=(arg == "gone")
                    )
                    step.name = "Wait:Gone" if arg == "gone" else "Wait:Pixel"
                else:
                    # wait <Zeit> oder wait <Min>-<Max>
                    if "-" in arg:
                        range_val, range_err = parse_non_negative_range(arg, "Wartezeit")
                        if range_err:
                            print(f"  -> {range_err}")
                            print("     Format: wait <Min>-<Max> (z.B. wait 1-5)")
                            continue
                        min_val, max_val = range_val
                        step.delay_before = min_val
                        step.delay_max = max_val
                        step.name = f"Wait:{min_val:g}-{max_val:g}s"
                    else:
                        delay_val, delay_err = parse_non_negative_float(arg, "Wartezeit")
                        if delay_err:
                            print(f"  -> {delay_err}")
                            print("     Format: wait <Zeit> (z.B. wait 5)")
                            continue
                        step.delay_before = delay_val
                        step.name = f"Wait:{arg}s"

                apply_else_to_step(step, else_parts, state)
                add_step(step)
                continue

            # === SCREENSHOT-SCHRITT ===
            elif user_input.lower().startswith(("screenshot", "ss")):
                parts_ss = user_input.split()
                # parts_ss[0] = "screenshot" oder "ss"
                rest = parts_ss[1:]  # alles nach dem Befehl

                if rest and rest[0].lower() == "full":
                    step = SequenceStep(x=0, y=0, delay_before=0.0,
                                       screenshot_only=True, screenshot_region=None,
                                       name="Screenshot (Vollbild)")
                    add_step(step)
                    print(ok("Screenshot-Schritt (Vollbild) hinzugefügt"))
                elif len(rest) == 4 and all(r.lstrip("-").isdigit() for r in rest):
                    x1, y1, x2, y2 = (int(v) for v in rest)
                    region = (x1, y1, x2, y2)
                    step = SequenceStep(x=0, y=0, delay_before=0.0,
                                       screenshot_only=True, screenshot_region=region,
                                       name=f"Screenshot ({x1},{y1})→({x2},{y2})")
                    add_step(step)
                    print(ok(f"Screenshot-Schritt ({x1},{y1})→({x2},{y2}) hinzugefügt"))
                else:
                    # Interaktiv Bereich wählen
                    if not PILLOW_AVAILABLE:
                        print(f"  -> {err('Pillow nicht installiert!')} pip install pillow")
                        continue
                    print("  Bereich für Screenshot-Schritt wählen:")
                    region = select_region()
                    if region is None:
                        continue
                    step = SequenceStep(x=0, y=0, delay_before=0.0,
                                       screenshot_only=True, screenshot_region=region,
                                       name=f"Screenshot ({region[0]},{region[1]})→({region[2]},{region[3]})")
                    add_step(step)
                    print(ok(f"Screenshot-Schritt ({region[0]},{region[1]})→({region[2]},{region[3]}) hinzugefügt"))
                continue

            # === PUNKT-BEFEHL (Standard) ===
            else:
                parts_raw = user_input.split()
                # Parse else-Bedingung
                else_parts = []
                main_parts = []
                in_else = False
                for p in parts_raw:
                    if p.lower() == "else":
                        in_else = True
                        continue
                    if in_else:
                        else_parts.append(p)
                    else:
                        main_parts.append(p)

                if not main_parts:
                    _known = ["done", "cancel", "help", "show", "del", "ins", "points", "learn", "scan", "key", "wait", "screenshot", "ss"]
                    suggestion = suggest_command(user_input, _known)
                    print(f"  -> Unbekannter Befehl.{suggestion} {hint('(? = Hilfe)')}")
                    continue

                # Punkt-ID
                try:
                    point_id = int(main_parts[0])
                except ValueError:
                    _known = ["done", "cancel", "help", "show", "del", "ins", "points", "learn", "scan", "key", "wait", "screenshot", "ss"]
                    suggestion = suggest_command(user_input, _known)
                    print(f"  -> Unbekannter Befehl.{suggestion} {hint('(? = Hilfe)')}")
                    continue

                with state.lock:
                    point = get_point_by_id(state, point_id)
                    if not point:
                        print(f"  -> Punkt #{point_id} nicht gefunden!")
                        continue

                # Delay und Optionen
                delay = 0
                delay_max = None
                wait_pixel = None
                wait_color = None
                wait_until_gone = False

                if len(main_parts) > 1:
                    arg = main_parts[1].lower()

                    if arg in ("pixel", "gone"):
                        # <Nr> pixel / <Nr> gone
                        px, py, color = capture_pixel_color()
                        if color:
                            wait_pixel = (px, py)
                            wait_color = color
                            if arg == "gone":
                                wait_until_gone = True
                    elif "-" in arg:
                        # <Nr> <Min>-<Max>
                        range_val, range_err = parse_non_negative_range(arg, "Wartezeit")
                        if range_err:
                            print(f"  -> {range_err}")
                            print("     Format: <Nr> <Min>-<Max> (z.B. 1 5-10)")
                            continue
                        delay, delay_max = range_val
                    else:
                        # <Nr> <Zeit>
                        delay_val, delay_err = parse_non_negative_float(arg, "Wartezeit")
                        if delay_err:
                            print(f"  -> {delay_err}")
                            print("     Format: <Nr> <Zeit> (z.B. 1 5)")
                            continue
                        delay = delay_val

                        # Optional: <Nr> <Zeit> pixel/gone
                        if len(main_parts) > 2:
                            opt = main_parts[2].lower()
                            if opt in ("pixel", "gone"):
                                px, py, color = capture_pixel_color()
                                if color:
                                    wait_pixel = (px, py)
                                    wait_color = color
                                    if opt == "gone":
                                        wait_until_gone = True

                wait_cond = None
                if wait_pixel and wait_color:
                    wait_cond = WaitCondition(pixel=wait_pixel, color=wait_color,
                                              until_gone=wait_until_gone)
                step = SequenceStep(
                    x=point.x, y=point.y, delay_before=delay,
                    name=point.name or f"#{point_id}",
                    wait_condition=wait_cond,
                    delay_max=delay_max
                )

                apply_else_to_step(step, else_parts, state)
                add_step(step)
                continue

        except (KeyboardInterrupt, EOFError):
            raise
