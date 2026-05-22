"""
Phase-Editor: interaktiver Editor für die Schritt-Liste einer Phase.

edit_phase ist die zentrale Funktion — sie dispatcht eine Vielzahl von
Befehlen (scan, boss, watcher, key, wait, screenshot, learn, points,
del, ins, plus Punkt-Klick-Direktbefehle wie '1 30' = Punkt #1 nach 30s).
_print_phase_help druckt die Befehls-Übersicht.

Hinweis: edit_phase ist mit ~500 Zeilen die längste Funktion im Subpaket.
Ein interner Split in _handle_*-Funktionen wäre ein eigener Refactor-Pass.
"""

from typing import Optional

from ...imaging import PILLOW_AVAILABLE, select_region
from ...models import ClickPoint, WaitCondition, SequenceStep, AutoClickerState
from ...persistence import (
    get_next_point_id, get_point_by_id, save_data,
)
from ...utils import (
    cancel_hint, cmd_hint, col, coord_context, hint, is_cancel,
    ok, err, safe_input, suggest_command,
    parse_non_negative_float, parse_non_negative_range,
)
from ...winapi import get_cursor_pos, VK_CODES
from .helpers import apply_else_to_step, capture_pixel_color


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
        print(cmd_hint("watcher <Name>", "Boss-Watcher (wartet bis Boss erscheint)"))
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
    print(cmd_hint("watcher <Name>", "Boss-Watcher: wartet bis Boss erscheint → Aktion"))
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


def _split_main_and_else(parts_raw: list[str]) -> tuple[list[str], list[str]]:
    """Trennt 'foo bar else baz qux' in (['foo','bar'], ['baz','qux'])."""
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
    return main_parts, else_parts


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
                main_parts, else_parts = _split_main_and_else(user_input.split()[1:])
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
                main_parts, else_parts = _split_main_and_else(user_input.split()[1:])
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

            # === BOSS-WATCHER-BEFEHL ===
            elif user_input.lower().startswith("watcher "):
                main_parts, else_parts = _split_main_and_else(user_input.split()[1:])
                if not main_parts:
                    print("  -> Format: watcher <Boss-Scan-Name> [else ...]")
                    continue

                watcher_name = main_parts[0]

                step = SequenceStep(
                    x=0, y=0, delay_before=0,
                    name=f"Watcher:{watcher_name}",
                    boss_watcher=watcher_name,
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
                    key_name = parts[1].lower()
                else:
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
                main_parts, else_parts = _split_main_and_else(user_input.split()[1:])
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
                main_parts, else_parts = _split_main_and_else(user_input.split())

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
