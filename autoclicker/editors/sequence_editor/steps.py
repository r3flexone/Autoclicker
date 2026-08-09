"""
Phase-Editor: interaktiver Editor für die Schritt-Liste einer Phase.

edit_phase() ist die öffentliche API — sie delegiert an die _PhaseEditor-Klasse,
die den Zustand (steps, insert_position) hält und für jeden Befehl eine eigene
_handle_*-Methode hat. So bleibt jede Befehlslogik unter ~50 Zeilen und ist
einzeln verständlich, statt einer 470-Zeilen-If-elif-Kette.

Befehle:
  done/d / cancel              — Phase abschließen / verwerfen
  show/s                       — Schritte anzeigen
  help / ? / ??                — Hilfe (kurz/voll)
  del N | del N-M | del all    — Schritt(e) löschen
  ins N | ins 0 | ins end      — Insert-Modus setzen/abbrechen
  points/p | learn [Name]      — Punkt-Verwaltung
  scan/boss/watcher/key/wait/  — Spezielle Step-Typen
    screenshot
  <Nr> [<Zeit>] [color|colorgone] — Direkter Punkt-Klick (Standard)
"""

import copy
from typing import Optional

from ...imaging import PILLOW_AVAILABLE, select_region
from ...models import ClickPoint, WaitCondition, SequenceStep, AutoClickerState
from ...persistence import (
    get_next_point_id, get_point_by_id, save_data,
)
from ...utils import (
    cancel_hint, cmd_hint, col, confirm, coord_context, describe_color, hint,
    is_cancel, ok, err, warn, safe_input, suggest_command,
    parse_non_negative_float, parse_non_negative_range,
)
from ...winapi import get_cursor_pos, VK_CODES
from .helpers import apply_else_to_step, capture_pixel_color


# =============================================================================
# HILFE-AUSGABE + KLEINE PARSER
# =============================================================================

def _print_phase_help(full: bool = False) -> None:
    """Zeigt die Hilfe für den Phase-Editor an (kurz oder vollständig)."""
    if not full:
        print("\n" + "-" * 60)
        print("  Kurzübersicht (?? = ausführliche Hilfe mit Beispielen):")
        print(hint("  <Punkt-Nr> = Punkt aus 'points' | <Schritt-Nr> = Position in der Liste"))
        print(cmd_hint("<Punkt-Nr> <Sek>", "Punkt nach <Sek> Wartezeit klicken (z.B. '1 30')"))
        print(cmd_hint("scan <Scan-Name>", "Item-Scan ausführen"))
        print(cmd_hint("boss <Scan-Name>", "Boss erkennen → hinterlegte Aktion"))
        print(cmd_hint("watcher <Scan-Name>", "Warten bis Boss erscheint → Aktion"))
        print(cmd_hint("icon <Scan-Name>", "Symbol/Icon erkennen → Aktion"))
        print(cmd_hint("key <Taste>", "Taste drücken (z.B. 'key enter')"))
        print(cmd_hint("scroll <Punkt-Nr> <Stufen>", "Mausrad drehen (+ hoch / - runter)"))
        print(cmd_hint("wait <Sek>", "Nur warten, NICHT klicken"))
        print(cmd_hint("edit <Schritt-Nr>", "Schritt ändern (geführtes Menü)"))
        print(cmd_hint("del <Schritt-Nr>", "Schritt löschen"))
        print(cmd_hint("points", "Punkte mit ihren Nummern anzeigen"))
        print(cmd_hint("link", "Schritte mit Punkten verknüpfen (Referenz nachtragen)"))
        print(cmd_hint("screenshot / ss", "Screenshot-Schritt anlegen"))
        print(cmd_hint("verify <Nr> <Punkt-Nr>", "nachpruefen, ob der Schritt gewirkt hat"))
        print(cmd_hint(f"done / d | cancel / {cancel_hint()}", "Phase speichern / verwerfen"))
        print("-" * 60)
        return

    print("\n" + "-" * 60)
    print(hint("Schreibweise: <Punkt-Nr> = Punkt aus 'points' (was geklickt wird) |"))
    print(hint("              <Schritt-Nr> = Position in dieser Schrittliste (was bearbeitet wird) |"))
    print(hint("              <Sek> = Wartezeit in Sekunden, <Min>-<Max> = zufällig dazwischen"))
    print("NEUEN Klick-Schritt anlegen (Logik: erst warten, DANN klicken):")
    print(cmd_hint("<Punkt-Nr> <Sek>", "<Sek> warten, dann den Punkt klicken (z.B. '1 30')"))
    print(cmd_hint("<Punkt-Nr> <Min>-<Max>", "zufällig warten, dann klicken (z.B. '1 30-45')"))
    print(cmd_hint("<Punkt-Nr> 0", "ohne Warten sofort klicken"))
    print(cmd_hint("<Punkt-Nr> color", "warten bis die Punkt-Farbe ERSCHEINT, dann klicken"))
    print(cmd_hint("<Punkt-Nr> <Sek> color", "erst <Sek> warten, dann bis Farbe erscheint, dann klicken"))
    print(cmd_hint("<Punkt-Nr> colorgone", "warten bis die Punkt-Farbe VERSCHWINDET, dann klicken"))
    print(cmd_hint("<Punkt-Nr> checkcolor", "Farbe EINMAL pruefen: passt sie, klicken - sonst Schritt ueberspringen"))
    print(cmd_hint("<Punkt-Nr> checkgone", "einmal pruefen, ob die Farbe WEG ist - sonst ueberspringen"))
    print(cmd_hint("<Punkt-Nr> <Sek> colorgone", "erst <Sek> warten, dann bis Farbe weg, dann klicken"))
    print("NUR warten / Taste / Scan (kein Punkt-Klick):")
    print(cmd_hint("wait <Sek>", "nur <Sek> warten, kein Klick (z.B. 'wait 10')"))
    print(cmd_hint("wait <Min>-<Max>", "zufällig warten, kein Klick (z.B. 'wait 30-45')"))
    print(cmd_hint("wait <Punkt-Nr> color", "warten bis die PUNKT-Farbe ERSCHEINT, kein Klick (z.B. 'wait 3 color')"))
    print(cmd_hint("wait <Punkt-Nr> colorgone", "warten bis die PUNKT-Farbe VERSCHWINDET, kein Klick (z.B. 'wait 3 colorgone')"))
    print(cmd_hint("wait pixel", "warten bis Farbe an der MAUSPOSITION erscheint (kein Klick)"))
    print(cmd_hint("wait pixelgone", "warten bis Farbe an der MAUSPOSITION verschwindet (kein Klick)"))
    print(cmd_hint("key <Taste>", "Taste sofort drücken (z.B. 'key enter')"))
    print(cmd_hint("key <Sek> <Taste>", "erst <Sek> warten, dann Taste (z.B. 'key 5 space')"))
    print(cmd_hint("key <Min>-<Max> <Taste>", "zufällig warten, dann Taste (z.B. 'key 5-10 space')"))
    print(cmd_hint("scroll <Punkt-Nr> <Stufen>", "Mausrad am Punkt drehen, + = hoch, - = runter (z.B. 'scroll 3 -5')"))
    print(cmd_hint("scroll <Punkt-Nr> <Sek> <Stufen>", "erst <Sek> warten, dann scrollen"))
    print(cmd_hint("scan <Scan-Name>", "Item-Scan: je Kategorie das beste Item klicken (Standard)"))
    print(cmd_hint("scan <Scan-Name> best", "Item-Scan: nur EIN Item insgesamt klicken (das beste)"))
    print(cmd_hint("scan <Scan-Name> every", "Item-Scan: ALLE Treffer klicken (auch Duplikate)"))
    print(cmd_hint("boss <Scan-Name>", "Einmal-Scan: Boss erkennen → in Boss-Liste hinterlegte Aktion"))
    print(cmd_hint("watcher <Scan-Name>", "Schleife: wartet bis ein Boss erscheint → dann Aktion"))
    print(cmd_hint("icon <Scan-Name>", "Symbol erkennen (z.B. rotes '!') → hinterlegte Aktion"))
    print("ELSE = was tun, wenn Trigger/Scan NICHT zutrifft (an obige Befehle anhängen):")
    print(cmd_hint("... else skip", "nur DIESEN Schritt überspringen, normal weiter"))
    print(cmd_hint("... else skip_cycle", "Rest des Zyklus abbrechen, nächsten Zyklus starten"))
    print(cmd_hint("... else restart", "ganze Sequenz von vorn (inkl. INIT)"))
    print(cmd_hint("... else <Punkt-Nr> [Sek]", "stattdessen diesen Punkt klicken (z.B. 'scan x else 2 5')"))
    print(cmd_hint("... else key <Taste>", "stattdessen Taste drücken (z.B. '1 pixel else key enter')"))
    print("NACHPRUEFUNG - hat der Schritt gewirkt? (wiederholt die Aktion, sonst else):")
    print(cmd_hint("verify <Schritt-Nr> <Punkt-Nr>", "nach der Aktion muss die Punkt-Farbe DA sein"))
    print(cmd_hint("verify <Schritt-Nr> <Punkt-Nr> gone", "... muss WEG sein"))
    print(cmd_hint("verify <Schritt-Nr> maus [gone]", "Stelle unter der Maus abgreifen"))
    print(cmd_hint("verify <Schritt-Nr> off", "Nachpruefung entfernen"))
    print("BESTEHENDE Schritte bearbeiten (<Schritt-Nr> = Position, siehe 'show'):")
    print(cmd_hint("edit <Schritt-Nr>", "GEFÜHRTES MENÜ: Zeit/Trigger/Klick/Farbe/duplizieren/verschieben/testen/löschen"))
    print(cmd_hint("show <Schritt-Nr>", "alle Felder eines Schritts im Detail anzeigen"))
    print(cmd_hint("scale <Faktor>", "alle Wartezeiten dieser Phase × Faktor (1.5 = länger, 0.5 = halbe Zeit)"))
    print("  " + hint("Kurzbefehle (machen 'edit' überflüssig, wenn man sie kennt):"))
    print(cmd_hint("color/colorgone <Schritt-Nr>", "Schritt wartet auf / bis WEG der aufgenommenen Farbe, dann Klick"))
    print(cmd_hint("noclick/click <Schritt-Nr>", "nur warten (kein Klick) / wieder normaler Klick"))
    print(cmd_hint("recolor <Schritt-Nr>", "Trigger-Farbe per Maus neu setzen (Pixel-Position bleibt)"))
    print(cmd_hint("time <Schritt-Nr> <Sek>", "Wartezeit ändern (z.B. 'time 3 5' oder 'time 3 2-4')"))
    print(cmd_hint("copy <Schritt-Nr>", "Schritt duplizieren (Kopie direkt dahinter)"))
    print(cmd_hint("move <Schritt-Nr> <Ziel>", "Schritt an andere Position schieben (z.B. 'move 5 1')"))
    print(cmd_hint("test <Schritt-Nr>", "Schritt 1× sofort ausführen — ECHTER Klick! (ohne Wartezeit/Trigger)"))
    print("Punkte (die Klick-Ziele):")
    print(cmd_hint("learn <Name>", "neuen Klick-Punkt aufnehmen (Maus positionieren)"))
    print(cmd_hint("points", "alle Punkte mit Nummer, Position und Farbe anzeigen"))
    print("Schritte löschen / einfügen:")
    print(cmd_hint("del <Schritt-Nr>", "einen Schritt löschen"))
    print(cmd_hint("del <Von>-<Bis>", "mehrere Schritte löschen (z.B. 'del 1-5')"))
    print(cmd_hint("del all", "ALLE Schritte dieser Phase löschen"))
    print(cmd_hint("ins <Schritt-Nr>", "nächsten NEUEN Schritt an dieser Position einfügen (statt am Ende)"))
    print("Screenshot-Schritt (wird beim Ausführen automatisch aufgenommen):")
    print(cmd_hint("screenshot / ss", "Bereich mit der Maus aufziehen → Screenshot-Schritt"))
    print(cmd_hint("screenshot full", "Vollbild-Screenshot-Schritt"))
    print(cmd_hint("screenshot x1 y1 x2 y2", "feste Koordinaten (z.B. 'screenshot 0 0 800 600')"))
    print(cmd_hint(f"help / ? | ?? | done / d | cancel / {cancel_hint()}", "Hilfe / diese Vollhilfe / speichern / verwerfen"))
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


# Bekannte Befehle für Tippfehler-Vorschläge (suggest_command)
_KNOWN_COMMANDS = [
    "done", "cancel", "help", "show", "edit", "del", "ins", "points", "learn",
    "scan", "boss", "watcher", "icon", "key", "wait", "screenshot", "ss",
    "color", "colorgone", "checkcolor", "checkgone", "scroll", "link", "verify",
    "recolor", "noclick", "click", "time", "copy", "move", "scale", "test",
]

# Schlüsselwörter für 'wait <Punkt-Nr> ...': bei einem Punkt geht es nur um die
# Farbe, daher 'color' (Farbe DA) / 'colorgone' (Farbe WEG). Wert = interner
# _apply_trigger-Modus.
_WAIT_POINT_TRIGGER_ALIASES = {
    "color": "pixel",
    "colorgone": "gone",
}

# Schlüsselwörter für 'wait pixel|pixelgone' (Mausposition, kein Punkt). Hier
# wird ein Pixel an der Maus abgegriffen, daher 'pixel' (DA) / 'pixelgone' (WEG).
# Wie _WAIT_POINT_TRIGGER_ALIASES, aber OHNE Warten: einmal pruefen und bei
# Nichttreffer den Schritt ueberspringen (WaitCondition.check_only). Wert = until_gone.
_CHECK_POINT_TRIGGER_ALIASES = {
    "checkcolor": False,
    "checkgone": True,
}

_WAIT_MOUSE_TRIGGER_ALIASES = {
    "pixel": False,
    "pixelgone": True,
}


# =============================================================================
# PHASE-EDITOR (interaktive Schleife + Handler-Methoden)
# =============================================================================

class _PhaseEditor:
    """Interaktiver Editor für die Schritt-Liste einer Phase.

    Hält den Zustand (steps, insert_position) und dispatcht User-Befehle an
    spezialisierte _handle_*-Methoden. add_step() ist die zentrale Stelle
    für Step-Hinzufügen — respektiert insert_position oder hängt am Ende an.
    """

    def __init__(self, state: AutoClickerState, steps: list[SequenceStep],
                 phase_name: str) -> None:
        self.state = state
        self.steps = steps
        self.phase_name = phase_name
        self.insert_position: Optional[int] = None

    # ---- Hauptschleife ----

    def run(self) -> Optional[list[SequenceStep]]:
        """Startet die interaktive Schleife. Returns steps (done) oder None (cancel)."""
        if self.steps:
            print(f"\nAktuelle {self.phase_name}-Schritte ({len(self.steps)}):")
            for i, step in enumerate(self.steps):
                print(self._format_step_line(i, step))

        _print_phase_help()

        while True:
            try:
                user_input = safe_input(f"{self._prompt()} > ").strip()
                cmd = user_input.lower()

                if cmd in ("done", "d"):
                    return self.steps
                if is_cancel(user_input):
                    print(col("[ABBRUCH]", "yellow") + " Phase abgebrochen.")
                    return None
                if cmd == "":
                    continue

                self._dispatch(user_input, cmd)
            except (KeyboardInterrupt, EOFError):
                raise

    def _prompt(self) -> str:
        """Erzeugt den Eingabe-Prompt — zeigt Insert-Modus an wenn aktiv."""
        base = f"[{self.phase_name}: {len(self.steps)}]"
        if self.insert_position is not None:
            return f"{base} (ins->{self.insert_position})"
        return base

    def _dispatch(self, user_input: str, cmd: str) -> None:
        """Routet einen Befehl an die passende Handler-Methode.

        Reihenfolge wichtig: exakte Matches (ins 0/ins end, del all) müssen VOR
        Präfix-Matches (ins , del ) stehen, sonst werden sie geschluckt.
        """
        if cmd == "help":
            _print_phase_help()
            return
        if cmd in ("?", "help full", "??"):
            _print_phase_help(full=True)
            return
        if cmd in ("show", "s"):
            self._handle_show()
            return
        if cmd.startswith("show "):
            self._handle_show_detail(user_input)
            return

        # Lösch-Befehle (exakt zuerst, dann Range, dann Single)
        if cmd == "del all":
            self._handle_del_all()
            return
        if cmd.startswith("del ") and "-" in user_input[4:]:
            self._handle_del_range(user_input)
            return
        if cmd.startswith("del "):
            self._handle_del_single(user_input)
            return

        # Insert-Modus (exakt zuerst — sonst schluckt startswith("ins ") "ins 0"/"ins end")
        if cmd in ("ins 0", "ins end"):
            self._handle_ins_clear()
            return
        if cmd.startswith("ins "):
            self._handle_ins_set(user_input)
            return

        # Punkt-Verwaltung
        if cmd in ("points", "p"):
            self._handle_points()
            return
        if cmd.startswith("learn"):
            self._handle_learn(user_input)
            return

        # Step-hinzufügen-Befehle
        if cmd.startswith("scan "):
            self._handle_scan(user_input)
            return
        if cmd.startswith("boss "):
            self._handle_boss(user_input)
            return
        if cmd.startswith("watcher "):
            self._handle_watcher(user_input)
            return
        if cmd.startswith("icon "):
            self._handle_icon(user_input)
            return
        if cmd in ("link", "link all"):
            self._handle_link()
            return

        if cmd.startswith("scroll "):
            self._handle_scroll(user_input)
            return

        if cmd.startswith("key "):
            self._handle_key(user_input)
            return
        if cmd.startswith("wait "):
            self._handle_wait(user_input)
            return
        if (cmd == "ss" or cmd == "screenshot"
                or cmd.startswith("screenshot ") or cmd.startswith("ss ")):
            self._handle_screenshot(user_input)
            return
        if cmd.startswith("verify "):
            self._handle_verify(user_input)
            return

        # Geführtes Bearbeiten (empfohlen): ein Menü statt vieler Verben
        if cmd.startswith("edit ") or cmd.startswith("e "):
            self._handle_edit_menu(user_input)
            return

        # Bestehenden Schritt nachträglich umbauen (z.B. aufgenommenen Klick)
        if cmd.startswith("colorgone "):
            self._handle_make_pixel(user_input, until_gone=True)
            return
        if cmd.startswith("color "):
            self._handle_make_pixel(user_input, until_gone=False)
            return
        if cmd.startswith("noclick "):
            self._handle_make_noclick(user_input)
            return
        if cmd.startswith("click "):
            self._handle_make_click(user_input)
            return
        if cmd.startswith("recolor "):
            self._handle_set_color(user_input)
            return
        if cmd.startswith("time "):
            self._handle_set_time(user_input)
            return
        if cmd.startswith("copy "):
            self._handle_copy(user_input)
            return
        if cmd.startswith("move "):
            self._handle_move(user_input)
            return
        if cmd.startswith("scale "):
            self._handle_scale(user_input)
            return
        if cmd.startswith("test "):
            self._handle_test(user_input)
            return

        # Default: Punkt-ID + Optionen (z.B. "1 30 pixel")
        self._handle_point_click(user_input)

    def add_step(self, step: SequenceStep) -> None:
        """Fügt einen Schritt hinzu — an insert_position oder am Ende.

        Setzt insert_position nach dem Einfügen zurück (Einmal-Modus).
        """
        if self.insert_position is not None:
            self.steps.insert(self.insert_position - 1, step)
            print(f"  + Eingefügt an Position {self.insert_position}: {step}")
            self.insert_position = None
        else:
            self.steps.append(step)
            print(f"  + Hinzugefügt: {step}")

    # ---- Generische Befehle ----

    def _handle_show(self) -> None:
        if self.steps:
            print(f"\n{self.phase_name}-Schritte:")
            for i, step in enumerate(self.steps):
                print(self._format_step_line(i, step))
        else:
            print("  (Keine Schritte)")

    def _format_step_line(self, i: int, step: SequenceStep) -> str:
        """Formatiert eine Schritt-Zeile, hängt einen Farb-Hinweis an wenn eine
        aufgenommene Farbe vorliegt aber noch kein Farb-Trigger gesetzt ist."""
        line = f"  {i+1}. {step}"
        if step.recorded_color and not step.wait_condition:
            line += col(f"   [aufgenommen: RGB{step.recorded_color} → 'color {i+1}']", "gray")
        return line

    def _handle_del_all(self) -> None:
        if not self.steps:
            print("  -> Keine Schritte vorhanden!")
            return
        count = len(self.steps)
        self.steps.clear()
        print(f"  + Alle {count} Schritte gelöscht")

    def _handle_del_range(self, user_input: str) -> None:
        try:
            range_str = user_input[4:].strip()
            parts = range_str.split("-")
            start = int(parts[0])
            end = int(parts[1])
            if start < 1 or end > len(self.steps) or start > end:
                print(f"  -> Ungültiger Bereich! Verfügbar: 1-{len(self.steps)}")
                return
            # Von hinten löschen um Indexe nicht zu verschieben
            removed_count = 0
            for i in range(end, start - 1, -1):
                self.steps.pop(i - 1)
                removed_count += 1
            print(f"  + {removed_count} Schritte gelöscht ({start}-{end})")
        except (ValueError, IndexError):
            print("  -> Format: del <start>-<end> (z.B. del 1-5)")

    def _handle_del_single(self, user_input: str) -> None:
        try:
            del_num = int(user_input[4:])
            if 1 <= del_num <= len(self.steps):
                removed = self.steps.pop(del_num - 1)
                print(f"  + Schritt {del_num} gelöscht: {removed}")
            else:
                print(f"  -> Ungültiger Schritt! Verfügbar: 1-{len(self.steps)}")
        except ValueError:
            print("  -> Format: del <Nr>")

    def _handle_ins_set(self, user_input: str) -> None:
        try:
            pos = int(user_input[4:])
            if pos < 1:
                print("  -> Position muss >= 1 sein!")
                return
            if pos > len(self.steps) + 1:
                print(f"  -> Position zu groß! Max: {len(self.steps) + 1}")
                return
            self.insert_position = pos
            print(f"  + Insert-Modus: Nächster Schritt wird an Position {pos} eingefügt")
            print("    (Abbrechen mit 'ins 0' oder 'ins end')")
        except ValueError:
            print("  -> Format: ins <Nr>")

    def _handle_ins_clear(self) -> None:
        if self.insert_position is not None:
            self.insert_position = None
            print("  + Insert-Modus beendet - Schritte werden wieder am Ende angefügt")
        else:
            print("  -> Insert-Modus war nicht aktiv")

    # ---- Punkt-Verwaltung ----

    def _handle_points(self) -> None:
        with self.state.lock:
            if self.state.points:
                print("\n  Verfügbare Punkte:")
                for p in self.state.points:
                    color_str = f"  {describe_color(p.color)}" if p.color else ""
                    print(f"    {p}{color_str}")
            else:
                print("  (Keine Punkte vorhanden)")

    def _handle_learn(self, user_input: str) -> None:
        """Format: 'learn' oder 'learn <Name>' — neuen Punkt an Mauspos. anlegen."""
        parts = user_input.split(maxsplit=1)
        if len(parts) > 1:
            point_name = parts[1].strip()
        else:
            point_name = safe_input("  Punkt-Name: ").strip()
            if not point_name or is_cancel(point_name):
                print("  -> Abgebrochen")
                return

        print(f"\n  Bewege die Maus zur Position für '{point_name}'")
        print("  Drücke Enter...")
        safe_input()
        x, y = get_cursor_pos()

        with self.state.lock:
            new_id = get_next_point_id(self.state)
            new_point = ClickPoint(x, y, point_name, new_id)
            self.state.points.append(new_point)

        save_data(self.state)
        print(f"  + Punkt #{new_id} '{point_name}' erstellt bei {coord_context(x, y)}")

    # ---- Step-hinzufügen ----

    def _handle_scan(self, user_input: str) -> None:
        """Format: scan <Name> [best|every] [else ...]"""
        main_parts, else_parts = _split_main_and_else(user_input.split()[1:])
        if not main_parts:
            print("  -> Format: scan <Name> [best|every] [else ...]")
            return

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
            item_scan_mode=mode,
        )
        apply_else_to_step(step, else_parts, self.state)
        self.add_step(step)

    def _handle_boss(self, user_input: str) -> None:
        """Format: boss <Name> [else ...]"""
        main_parts, else_parts = _split_main_and_else(user_input.split()[1:])
        if not main_parts:
            print("  -> Format: boss <Name> [else ...]")
            return

        boss_name = main_parts[0]
        step = SequenceStep(
            x=0, y=0, delay_before=0,
            name=f"Boss:{boss_name}",
            boss_scan=boss_name,
        )
        apply_else_to_step(step, else_parts, self.state)
        self.add_step(step)

    def _handle_watcher(self, user_input: str) -> None:
        """Format: watcher <Boss-Scan-Name> [else ...]"""
        main_parts, else_parts = _split_main_and_else(user_input.split()[1:])
        if not main_parts:
            print("  -> Format: watcher <Boss-Scan-Name> [else ...]")
            return

        watcher_name = main_parts[0]
        step = SequenceStep(
            x=0, y=0, delay_before=0,
            name=f"Watcher:{watcher_name}",
            boss_watcher=watcher_name,
        )
        apply_else_to_step(step, else_parts, self.state)
        self.add_step(step)

    def _handle_icon(self, user_input: str) -> None:
        """Format: icon <Icon-Scan-Name> [else ...]"""
        main_parts, else_parts = _split_main_and_else(user_input.split()[1:])
        if not main_parts:
            print("  -> Format: icon <Icon-Scan-Name> [else ...]")
            return

        icon_name = main_parts[0]
        step = SequenceStep(
            x=0, y=0, delay_before=0,
            name=f"Icon:{icon_name}",
            icon_scan=icon_name,
        )
        apply_else_to_step(step, else_parts, self.state)
        self.add_step(step)

    def _handle_key(self, user_input: str) -> None:
        """Format: key <Taste> | key <Zeit> <Taste> | key <Min>-<Max> <Taste>"""
        parts = user_input.split()
        if len(parts) < 2:
            print("  -> Format: key <Taste> oder key <Zeit> <Taste> oder key <Min>-<Max> <Taste>")
            return

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
                    return
                delay, delay_max = range_val
            else:
                delay_val, delay_err = parse_non_negative_float(parts[1], "Verzögerung")
                if delay_err:
                    print(f"  -> {delay_err}")
                    print("     Format: key <Taste> oder key <Zeit> <Taste>")
                    return
                delay = delay_val
            key_name = parts[2].lower()

        if key_name not in VK_CODES:
            print(f"  -> Unbekannte Taste: '{key_name}'")
            print(f"     Verfügbar: {', '.join(sorted(VK_CODES.keys())[:20])}...")
            return

        step = SequenceStep(
            x=0, y=0, delay_before=delay, delay_max=delay_max,
            name=f"Key:{key_name}",
            key_press=key_name,
        )
        self.add_step(step)

    def _handle_link(self) -> None:
        """Verknüpft Schritte ohne point_id nachträglich mit Punkten aus dem Pool.

        Zugeordnet wird über exakt übereinstimmende Koordinaten - das ist die einzige
        verlässliche Brücke für Sequenzen, die vor der Referenz-Umstellung entstanden
        sind. Mehrdeutige Fälle (zwei Punkte auf derselben Stelle) werden gemeldet und
        NICHT verknüpft, damit nicht stillschweigend der falsche Punkt gewinnt.
        """
        with self.state.lock:
            punkte = list(self.state.points)

        if not punkte:
            print("  -> Keine Punkte im Pool - nichts zu verknüpfen.")
            return

        # Koordinate -> Punkte (mehrere = mehrdeutig)
        nach_pos = {}
        for p in punkte:
            nach_pos.setdefault((p.x, p.y), []).append(p)

        verknuepft, mehrdeutig, ohne_punkt, schon_ok = [], [], [], 0
        for i, step in enumerate(self.steps, 1):
            if step.point_id is not None:
                schon_ok += 1
                continue
            # Schritte ohne echte Position (Taste/Scan/Wait) haben keinen Punkt
            if step.key_press or step.item_scan or step.boss_scan or step.boss_watcher \
                    or step.icon_scan or step.screenshot_only or step.wait_only:
                continue
            treffer = nach_pos.get((step.x, step.y), [])
            if len(treffer) == 1:
                step.point_id = treffer[0].id
                verknuepft.append(f"[{i}] '{step.name}' -> Punkt #{treffer[0].id} "
                                  f"'{treffer[0].name or '(ohne Name)'}'")
            elif len(treffer) > 1:
                ids = ", ".join(f"#{p.id}" for p in treffer)
                mehrdeutig.append(f"[{i}] '{step.name}' ({step.x}, {step.y}): "
                                  f"mehrere Punkte passen ({ids}) - nicht verknüpft")
            else:
                ohne_punkt.append(f"[{i}] '{step.name}' ({step.x}, {step.y}): "
                                  "kein Punkt an dieser Stelle")

        if verknuepft:
            print(f"  {ok(f'{len(verknuepft)} Schritt(e) verknüpft:')}")
            for z in verknuepft:
                print(f"    {z}")
        if mehrdeutig:
            print(f"  {warn(f'{len(mehrdeutig)} mehrdeutig:')}")
            for z in mehrdeutig:
                print(f"    {z}")
        if ohne_punkt:
            print(f"  {warn(f'{len(ohne_punkt)} ohne passenden Punkt:')}")
            for z in ohne_punkt:
                print(f"    {z}")
            print(f"    {hint('Diese Schritte behalten ihre eigenen Koordinaten - das ist ok.')}")
        if schon_ok:
            print(f"  {hint(f'{schon_ok} Schritt(e) waren schon verknüpft.')}")
        if not (verknuepft or mehrdeutig or ohne_punkt):
            print("  -> Nichts zu tun.")
        elif verknuepft:
            print(f"  {hint('Mit done speichern - danach folgen diese Schritte ihrem Punkt.')}")

    def _handle_scroll(self, user_input: str) -> None:
        """Format: scroll <Punkt-Nr> <Stufen> | scroll <Punkt-Nr> <Sek> <Stufen>

        Gescrollt wird AN der Punkt-Position, weil Windows das Mausrad-Event an das
        Fenster unter dem Cursor liefert - ein Punkt ist also Pflicht, kein Extra.
        Stufen: positiv = hoch, negativ = runter, Betrag = Rasterstufen.
        """
        parts, else_parts = _split_main_and_else(user_input.split()[1:])
        if len(parts) < 2:
            print("  -> Format: scroll <Punkt-Nr> <Stufen> oder scroll <Punkt-Nr> <Sek> <Stufen>")
            print("     Beispiel: 'scroll 3 -5' = am Punkt 3 fuenf Stufen runter")
            return

        try:
            point_id = int(parts[0])
        except ValueError:
            print(f"  -> '{parts[0]}' ist keine Punkt-Nr. Format: scroll <Punkt-Nr> <Stufen>")
            return
        point = get_point_by_id(self.state, point_id)
        if not point:
            print(f"  -> Punkt #{point_id} nicht gefunden!")
            return

        delay = 0
        delay_max = None
        if len(parts) >= 3:
            # Wartezeit dazwischen. Achtung: "-5" ist ein negativer Stufenwert, kein
            # Bereich - deshalb erst pruefen, ob es ueberhaupt wie ein Bereich aussieht.
            zeit_arg = parts[1]
            if "-" in zeit_arg.lstrip("-") :
                range_val, range_err = parse_non_negative_range(zeit_arg, "Wartezeit")
                if range_err:
                    print(f"  -> {range_err}")
                    return
                delay, delay_max = range_val
            else:
                delay_val, delay_err = parse_non_negative_float(zeit_arg, "Wartezeit")
                if delay_err:
                    print(f"  -> {delay_err}")
                    return
                delay = delay_val
            stufen_raw = parts[2]
        else:
            stufen_raw = parts[1]

        try:
            stufen = int(stufen_raw)
        except ValueError:
            print(f"  -> '{stufen_raw}' ist keine ganze Zahl. Beispiel: -5 (runter), 3 (hoch)")
            return
        if stufen == 0:
            print("  -> 0 Stufen waere ein Schritt ohne Wirkung.")
            return

        richtung = "hoch" if stufen > 0 else "runter"
        step = SequenceStep(
            x=point.x, y=point.y, delay_before=delay, delay_max=delay_max,
            name=f"Scroll {richtung} x{abs(stufen)} @ {point.name or f'#{point_id}'}",
            point_id=point_id,
            scroll=stufen,
        )
        apply_else_to_step(step, else_parts, self.state)
        self.add_step(step)

    def _handle_wait(self, user_input: str) -> None:
        """Format: wait <Zeit> | wait <Min>-<Max> | wait <Punkt-Nr> color|colorgone | wait pixel|pixelgone [else ...]

        Mit <Punkt-Nr> wird die Position + aufgenommene Farbe dieses Punkts als
        Farb-Trigger genutzt (color = bis DA, colorgone = bis WEG; kein Klick).
        Ohne Punkt-Nr: Farbe an der aktuellen Mausposition (pixel/pixelgone).
        """
        main_parts, else_parts = _split_main_and_else(user_input.split()[1:])
        if not main_parts:
            print("  -> Format: wait <Zeit> | wait pixel|pixelgone | wait <Punkt-Nr> color|colorgone")
            return

        arg = main_parts[0].lower()
        step = SequenceStep(x=0, y=0, delay_before=0, name="Wait", wait_only=True)

        # wait <Punkt-Nr> color|colorgone → Farbe vom aufgenommenen Punkt (kein Klick)
        if len(main_parts) >= 2 and main_parts[1].lower() in _WAIT_POINT_TRIGGER_ALIASES:
            try:
                point_id = int(arg)
            except ValueError:
                print("  -> Format: wait <Punkt-Nr> color|colorgone (z.B. 'wait 3 colorgone')")
                return
            with self.state.lock:
                point = get_point_by_id(self.state, point_id)
            if not point:
                print(f"  -> Punkt #{point_id} nicht gefunden! {hint('(siehe points)')}")
                return
            mode = _WAIT_POINT_TRIGGER_ALIASES[main_parts[1].lower()]
            # Punkt-Position + Farbe in den Schritt übernehmen, dann Trigger setzen.
            # _apply_trigger nutzt recorded_color (sonst Live-Abgriff) und lässt
            # wait_only=True unangetastet.
            step.x, step.y = point.x, point.y
            step.recorded_color = point.color
            if not self._apply_trigger(step, mode):
                return
            label = point.name or f"#{point_id}"
            step.name = f"Wait:Gone {label}" if mode == "gone" else f"Wait:Pixel {label}"
            apply_else_to_step(step, else_parts, self.state)
            self.add_step(step)
            return

        if arg in _WAIT_MOUSE_TRIGGER_ALIASES:
            until_gone = _WAIT_MOUSE_TRIGGER_ALIASES[arg]
            px, py, color = capture_pixel_color()
            if color is None:
                return
            step.wait_condition = WaitCondition(
                point_id=self._punkt_fuer(px, py, color, "Prüf-Pixel"),
                pixel=(px, py), color=color,
                until_gone=until_gone,
            )
            step.name = "Wait:Gone" if until_gone else "Wait:Pixel"
        elif "-" in arg:
            range_val, range_err = parse_non_negative_range(arg, "Wartezeit")
            if range_err:
                print(f"  -> {range_err}")
                print("     Format: wait <Min>-<Max> (z.B. wait 1-5)")
                return
            min_val, max_val = range_val
            step.delay_before = min_val
            step.delay_max = max_val
            step.name = f"Wait:{min_val:g}-{max_val:g}s"
        else:
            delay_val, delay_err = parse_non_negative_float(arg, "Wartezeit")
            if delay_err:
                print(f"  -> {delay_err}")
                print("     Format: wait <Zeit> (z.B. wait 5)")
                return
            step.delay_before = delay_val
            step.name = f"Wait:{arg}s"

        apply_else_to_step(step, else_parts, self.state)
        self.add_step(step)

    def _handle_screenshot(self, user_input: str) -> None:
        """Format: screenshot [full | <x1> <y1> <x2> <y2>] (sonst interaktiv)"""
        rest = user_input.split()[1:]  # alles nach dem Befehl

        if rest and rest[0].lower() == "full":
            step = SequenceStep(x=0, y=0, delay_before=0.0,
                                screenshot_only=True, screenshot_region=None,
                                name="Screenshot (Vollbild)")
            self.add_step(step)
            print(ok("Screenshot-Schritt (Vollbild) hinzugefügt"))
            return

        if len(rest) == 4 and all(r.lstrip("-").isdigit() for r in rest):
            x1, y1, x2, y2 = (int(v) for v in rest)
            region = (x1, y1, x2, y2)
            step = SequenceStep(x=0, y=0, delay_before=0.0,
                                screenshot_only=True, screenshot_region=region,
                                name=f"Screenshot ({x1},{y1})→({x2},{y2})")
            self.add_step(step)
            print(ok(f"Screenshot-Schritt ({x1},{y1})→({x2},{y2}) hinzugefügt"))
            return

        # Interaktiv Bereich wählen
        if not PILLOW_AVAILABLE:
            print(f"  -> {err('Pillow nicht installiert!')} pip install pillow")
            return
        print("  Bereich für Screenshot-Schritt wählen:")
        region = select_region()
        if region is None:
            return
        step = SequenceStep(x=0, y=0, delay_before=0.0,
                            screenshot_only=True, screenshot_region=region,
                            name=f"Screenshot ({region[0]},{region[1]})→({region[2]},{region[3]})")
        self.add_step(step)
        print(ok(f"Screenshot-Schritt ({region[0]},{region[1]})→({region[2]},{region[3]}) hinzugefügt"))

    # ---- Bestehende Schritte umbauen (für Nachbearbeitung von Aufnahmen) ----

    def _get_step_by_num(self, num_str: str):
        """Validiert eine 1-basierte Schritt-Nummer. Returns Step oder None."""
        idx = self._get_step_index_by_num(num_str)
        if idx is None:
            return None
        return self.steps[idx]

    def _get_step_index_by_num(self, num_str: str):
        """Validiert eine 1-basierte Schritt-Nummer. Returns 0-basierten Index oder None.

        Index statt Step, weil SequenceStep eq=True ist: bei Duplikaten würde
        self.steps.index(step) den ERSTEN inhaltsgleichen Schritt finden, nicht
        den gemeinten. Wer die Position braucht (copy/move/show/test), nutzt das.
        """
        try:
            num = int(num_str)
        except ValueError:
            print("  -> Format erwartet eine Schritt-Nummer (z.B. 'color 3')")
            return None
        if not (1 <= num <= len(self.steps)):
            print(f"  -> Ungültiger Schritt! Verfügbar: 1-{len(self.steps)}")
            return None
        return num - 1

    def _apply_trigger(self, step: SequenceStep, mode: str) -> bool:
        """Setzt/entfernt den Farb-Trigger eines Schritts. mode: 'none'|'pixel'|'gone'.

        Lässt wait_only bewusst unangetastet — Trigger (warten-auf-was) und Klick
        (klicken-oder-nicht) sind getrennte Achsen. Nutzt die aufgenommene Farbe
        (recorded_color), sonst Live-Abgriff an der Mausposition. Returns True bei
        Erfolg, False wenn keine Farbe lesbar war (Trigger nicht gesetzt).
        """
        if mode == "none":
            step.wait_condition = None
            return True
        until_gone = (mode == "gone")
        if step.wait_condition is not None and step.wait_condition.point_id is not None:
            # Schon eine Bedingung da (z.B. ein Warte-Marker aus der Aufnahme): nur die
            # Richtung drehen. Sonst griffe der Zweig unten eine LIVE-Farbe an der
            # Mausposition ab und ueberschriebe damit genau das, was gemerkt wurde.
            step.wait_condition.until_gone = until_gone
            return True
        if step.recorded_color:
            # Der Schritt prüft seinen EIGENEN Klickpunkt - also dieselbe Referenz, kein
            # zweiter Punkt. Genau der Fall, den das alte "Prüf-Pixel zieht mit" per
            # Koordinatenvergleich erraten musste; jetzt steht er in der Datei.
            pixel = (step.x, step.y)
            color = step.recorded_color
            punkt_id = step.point_id
            print(f"  Nutze aufgenommene Farbe RGB{color} bei ({step.x}, {step.y})")
        else:
            px, py, color = capture_pixel_color()
            if color is None:
                return False
            pixel = (px, py)
            punkt_id = self._punkt_fuer(px, py, color, "Prüf-Pixel")
        step.wait_condition = WaitCondition(point_id=punkt_id, pixel=pixel, color=color,
                                            until_gone=until_gone)
        return True

    def _handle_make_pixel(self, user_input: str, until_gone: bool) -> None:
        """Wandelt einen bestehenden Schritt in einen Farb-Trigger um.

        Nutzt recorded_color des Schritts (wird bei jeder Schritterstellung
        automatisch erfasst). Fehlt sie ausnahmsweise, wird die Farbe live an
        der aktuellen Mausposition abgegriffen.

        Format: color <Nr> | colorgone <Nr>
        """
        step = self._get_step_by_num(user_input.split()[1] if len(user_input.split()) > 1 else "")
        if step is None:
            return
        if not self._apply_trigger(step, "gone" if until_gone else "pixel"):
            return
        if step.point_id is not None:
            step.wait_only = False  # Trigger + Klick (nicht nur warten)
        # Ohne point_id gibt es nichts zu klicken — ein Warte-Marker aus der Aufnahme
        # bleibt reines Warten. `wait_only = False` haette ihn auf (0, 0) zeigen lassen.
        gone_str = "bis Farbe WEG" if until_gone else "auf Farbe"
        print(f"  + Schritt umgebaut: warte {gone_str} → {step}")

    def _handle_make_noclick(self, user_input: str) -> None:
        """Macht aus einem Schritt einen reinen Warte-Schritt (kein Klick).

        Format: noclick <Nr>
        """
        step = self._get_step_by_num(user_input.split()[1] if len(user_input.split()) > 1 else "")
        if step is None:
            return
        step.wait_only = True
        print(f"  + Schritt klickt nicht mehr (nur warten): {step}")

    def _handle_make_click(self, user_input: str) -> None:
        """Setzt einen Schritt auf reinen Klick zurück (entfernt Farb-Trigger / Warte-nur).

        Format: click <Nr>
        """
        step = self._get_step_by_num(user_input.split()[1] if len(user_input.split()) > 1 else "")
        if step is None:
            return
        step.wait_only = False
        step.wait_condition = None
        print(f"  + Schritt klickt wieder direkt: {step}")

    def _delay_str(self, step: SequenceStep) -> str:
        """Lesbare Wartezeit eines Schritts (fix oder Zufallsbereich)."""
        if step.delay_max and step.delay_max > step.delay_before:
            return f"{step.delay_before:g}-{step.delay_max:g}s (zufällig)"
        return f"{step.delay_before:g}s"

    def _handle_edit_menu(self, user_input: str) -> None:
        """Geführtes Bearbeiten eines Schritts über ein nummeriertes Menü.

        Ein einziger Einstieg für alle Schritt-Änderungen — man muss sich keine
        Verben (color/colorgone/noclick/time/recolor/...) merken, sondern wählt Schritt
        und Aktion per Nummer. Die Kurzbefehle bleiben als Shortcuts erhalten.

        Format: edit <Nr> | e <Nr>
        """
        idx = self._get_step_index_by_num(user_input.split()[1] if len(user_input.split()) > 1 else "")
        if idx is None:
            return
        num = idx + 1

        while True:
            step = self.steps[idx]
            wc = step.wait_condition
            trig = ("bis Farbe WEG" if wc.until_gone else "auf Farbe") if wc else "keiner"
            klick = "nur warten (kein Klick)" if step.wait_only else "klicken"

            def _opt(n: str, label: str) -> str:
                return f"    {col(f'[{n}]', 'yellow')} {label}"

            print(f"\n  {col(f'Schritt {num} bearbeiten:', 'bold')} {step}")
            print(_opt("1", f"Wartezeit    (aktuell: {self._delay_str(step)})"))
            print(_opt("2", f"Trigger      (aktuell: {trig})"))
            print(_opt("3", f"Klick an/aus (aktuell: {klick})"))
            print(_opt("4", "Trigger-Farbe neu abgreifen"))
            print(_opt("5", "Details anzeigen"))
            print(_opt("6", "Duplizieren"))
            print(_opt("7", "Verschieben"))
            print(_opt("8", "Testen (echter Klick!)"))
            print(_opt("9", "Löschen"))
            print(_opt("0", "Menü schließen (oder 'zurück')"))

            choice = safe_input("  edit> ").strip().lower()
            if choice in ("0", "", "zurück", "zurueck", "back", "done", "d", "q") or is_cancel(choice):
                return

            if choice == "1":
                val = safe_input("  Neue Wartezeit (Sek., oder Min-Max wie 2-4): ").strip()
                if val and not is_cancel(val):
                    self._handle_set_time(f"time {num} {val}")
            elif choice == "2":
                self._edit_trigger_submenu(step)
            elif choice == "3":
                step.wait_only = not step.wait_only
                print(f"  + Jetzt: {'nur warten (kein Klick)' if step.wait_only else 'klicken'}")
            elif choice == "4":
                self._handle_set_color(f"recolor {num}")
            elif choice == "5":
                self._handle_show_detail(f"show {num}")
            elif choice == "6":
                self._handle_copy(f"copy {num}")
                return  # Positionen verschoben — Menü schließen
            elif choice == "7":
                target = safe_input(f"  Neue Position (1-{len(self.steps)}): ").strip()
                if target and not is_cancel(target):
                    self._handle_move(f"move {num} {target}")
                return  # Positionen verschoben — Menü schließen
            elif choice == "8":
                self._handle_test(f"test {num}")
            elif choice == "9":
                if confirm(f"  Schritt {num} wirklich löschen?"):
                    self._handle_del_single(f"del {num}")
                    return  # Schritt weg — Menü schließen
            else:
                print(f"  -> {hint('Bitte 0-9 wählen.')}")

    def _edit_trigger_submenu(self, step: SequenceStep) -> None:
        """Untermenü: Trigger-Richtung wählen (lässt Klick-Einstellung unberührt)."""
        print(f"\n  {col('Trigger wählen:', 'bold')}")
        print(f"    {col('[1]', 'yellow')} Kein Trigger (Wartezeit allein)")
        print(f"    {col('[2]', 'yellow')} Warte bis Farbe DA ist")
        print(f"    {col('[3]', 'yellow')} Warte bis Farbe WEG ist")
        c = safe_input("  trigger> ").strip().lower()
        if c in ("0", "", "zurück", "zurueck") or is_cancel(c):
            return
        mode = {"1": "none", "2": "pixel", "3": "gone"}.get(c)
        if mode is None:
            print(f"  -> {hint('Bitte 1-3 wählen.')}")
            return
        if self._apply_trigger(step, mode):
            if mode == "none":
                print("  + Trigger entfernt.")
            else:
                print(f"  + Trigger: warte {'bis Farbe WEG' if mode == 'gone' else 'auf Farbe'}.")

    def _handle_set_color(self, user_input: str) -> None:
        """Ändert die Trigger-Farbe eines Schritts per Live-Abgriff (Override).

        Für die Ausnahmefälle, in denen die Punkt-Farbe nicht passt. Greift die
        Farbe an der aktuellen Mausposition ab und setzt sie als Trigger-Farbe.
        Die Pixel-Position des Triggers bleibt unverändert.

        Format: recolor <Nr>
        """
        step = self._get_step_by_num(user_input.split()[1] if len(user_input.split()) > 1 else "")
        if step is None:
            return
        if not step.wait_condition:
            print(warn("  -> Schritt hat keinen Farb-Trigger. Erst 'color <Nr>' oder 'colorgone <Nr>'."))
            return
        _, _, color = capture_pixel_color()
        if color is None:
            return
        step.wait_condition.color = color
        step.recorded_color = color
        print(f"  + Trigger-Farbe geändert: RGB{color} bei {step.wait_condition.pixel}")

    def _handle_set_time(self, user_input: str) -> None:
        """Ändert die Wartezeit eines bestehenden Schritts.

        Format: time <Nr> <Zeit> | time <Nr> <Min>-<Max>
        """
        parts = user_input.split()
        if len(parts) < 3:
            print("  -> Format: time <Nr> <Zeit> (z.B. 'time 3 5' oder 'time 3 2-4')")
            return
        step = self._get_step_by_num(parts[1])
        if step is None:
            return
        arg = parts[2]
        if "-" in arg:
            range_val, range_err = parse_non_negative_range(arg, "Wartezeit")
            if range_err:
                print(f"  -> {range_err}")
                return
            step.delay_before, step.delay_max = range_val
        else:
            delay_val, delay_err = parse_non_negative_float(arg, "Wartezeit")
            if delay_err:
                print(f"  -> {delay_err}")
                return
            step.delay_before = delay_val
            step.delay_max = None
        print(f"  + Zeit geändert: {step}")

    def _handle_show_detail(self, user_input: str) -> None:
        """Zeigt alle Felder eines Schritts im Detail.

        Format: show <Nr>
        """
        idx = self._get_step_index_by_num(user_input.split()[1] if len(user_input.split()) > 1 else "")
        if idx is None:
            return
        step = self.steps[idx]
        num = idx + 1
        print(f"\n  {col(f'Schritt {num} — Details:', 'bold')}")
        print(f"    Zusammenfassung: {step}")
        print(f"    Name:            {step.name or '(keiner)'}")
        print(f"    Position:        ({step.x}, {step.y})")
        if step.delay_max and step.delay_max > step.delay_before:
            print(f"    Wartezeit:       {step.delay_before:g}-{step.delay_max:g}s (zufällig)")
        else:
            print(f"    Wartezeit:       {step.delay_before:g}s")
        print(f"    Nur warten:      {'ja' if step.wait_only else 'nein'}")
        wc = step.wait_condition
        if wc:
            mode = "bis Farbe WEG" if wc.until_gone else "auf Farbe"
            print(f"    Farb-Trigger:    {mode} RGB{wc.color} bei ({wc.pixel[0]},{wc.pixel[1]})")
        else:
            print("    Farb-Trigger:    (keiner)")
        if step.recorded_color:
            tip = hint(f"   → 'color {num}' nutzt sie")
            print(f"    Aufgen. Farbe:   RGB{step.recorded_color}{tip}")
        if step.key_press:
            print(f"    Taste:           {step.key_press}")
        if step.item_scan:
            print(f"    Item-Scan:       {step.item_scan} ({step.item_scan_mode})")
        if step.boss_scan:
            print(f"    Boss-Scan:       {step.boss_scan}")
        if step.boss_watcher:
            print(f"    Boss-Watcher:    {step.boss_watcher}")
        if step.icon_scan:
            print(f"    Icon-Scan:       {step.icon_scan}")
        if step.screenshot_only:
            print(f"    Screenshot:      {step.screenshot_region or 'Vollbild'}")
        ec = step.else_config
        if ec:
            print(f"    ELSE:            {step._else_str().replace(' | ELSE: ', '')}")

    def _handle_copy(self, user_input: str) -> None:
        """Dupliziert einen Schritt und fügt die Kopie direkt dahinter ein.

        Format: copy <Nr>
        """
        idx = self._get_step_index_by_num(user_input.split()[1] if len(user_input.split()) > 1 else "")
        if idx is None:
            return
        step = self.steps[idx]
        clone = copy.deepcopy(step)
        self.steps.insert(idx + 1, clone)
        print(f"  + Schritt {idx + 1} dupliziert → neue Position {idx + 2}: {clone}")

    def _handle_move(self, user_input: str) -> None:
        """Verschiebt einen Schritt an eine neue Position.

        Format: move <Nr> <Ziel>
        """
        parts = user_input.split()
        if len(parts) < 3:
            print("  -> Format: move <Nr> <Ziel> (z.B. 'move 5 1')")
            return
        src = self._get_step_index_by_num(parts[1])
        if src is None:
            return
        try:
            target = int(parts[2])
        except ValueError:
            print("  -> Ziel muss eine Zahl sein (z.B. 'move 5 1')")
            return
        if not (1 <= target <= len(self.steps)):
            print(f"  -> Ungültiges Ziel! Verfügbar: 1-{len(self.steps)}")
            return
        step = self.steps.pop(src)
        self.steps.insert(target - 1, step)
        print(f"  + Schritt von Position {src + 1} → {target} verschoben: {step}")

    def _handle_scale(self, user_input: str) -> None:
        """Skaliert alle Wartezeiten dieser Phase mit einem Faktor.

        Format: scale <Faktor> (z.B. 'scale 1.5' = 50% länger, 'scale 0.5' = halbe Zeit)
        """
        parts = user_input.split()
        if len(parts) < 2:
            print("  -> Format: scale <Faktor> (z.B. 'scale 1.5' oder 'scale 0.5')")
            return
        try:
            factor = float(parts[1].replace(",", "."))
        except ValueError:
            print("  -> Faktor muss eine Zahl sein (z.B. 'scale 1.5')")
            return
        if factor <= 0:
            print("  -> Faktor muss größer als 0 sein!")
            return
        changed = 0
        for step in self.steps:
            if step.delay_before > 0:
                step.delay_before = round(step.delay_before * factor, 2)
                changed += 1
            if step.delay_max:
                step.delay_max = round(step.delay_max * factor, 2)
        print(f"  + Wartezeiten dieser Phase mit Faktor {factor:g} skaliert ({changed} Schritt(e) betroffen)")

    def _handle_test(self, user_input: str) -> None:
        """Führt EINEN Schritt sofort aus (Probelauf für Koordinaten-Check).

        Format: test <Nr>
        Achtung: führt einen echten Klick/Tastendruck aus. Wartezeit und
        Farb-Trigger werden für den Test übersprungen — es geht nur darum zu
        sehen ob die Aktion (Klick/Taste/Scan) am richtigen Ort landet.
        """
        idx = self._get_step_index_by_num(user_input.split()[1] if len(user_input.split()) > 1 else "")
        if idx is None:
            return
        step = self.steps[idx]
        with self.state.lock:
            if self.state.is_running:
                print(f"  -> {err('Sequenz läuft gerade — erst stoppen (CTRL+ALT+S)')}")
                return
        num = idx + 1
        print(f"  {col('[TEST]', 'cyan')} Führe Schritt {num} aus: {step}")
        print(hint("        (echter Klick/Tastendruck — Spielfenster muss aktiv sein,"))
        print(hint("         Wartezeit + Farb-Trigger werden für den Test übersprungen)"))
        # Auf einer Kopie testen: Wartezeit + Farb-Trigger nullen, damit die
        # Aktion sofort feuert (sonst würde der Test z.B. 30s warten)
        test_step = copy.deepcopy(step)
        test_step.delay_before = 0.0
        test_step.delay_max = None
        test_step.wait_condition = None
        from ...runtime.steps import execute_step
        # Events sauber halten, damit der Test-Lauf nicht durch Altzustände abbricht
        self.state.stop_event.clear()
        self.state.skip_event.clear()
        ok_run = False
        try:
            ok_run = execute_step(self.state, test_step, num, len(self.steps), "TEST")
        except Exception as e:  # Test soll den Editor nie crashen
            print(f"\n  -> {err(f'Test-Fehler: {e}')}")
            return
        finally:
            # Ein Test darf keine Events (Stop/Skip/Restart) in einen echten Lauf tragen
            self.state.stop_event.clear()
            self.state.skip_event.clear()
            self.state.skip_cycle_event.clear()
            self.state.restart_event.clear()
        print(f"\n  {ok('Test fertig.') if ok_run else col('Test abgebrochen.', 'yellow')}")

    def _handle_point_click(self, user_input: str) -> None:
        """Default-Befehl: <Nr> [<Zeit>] [color|colorgone] [else ...]"""
        main_parts, else_parts = _split_main_and_else(user_input.split())
        if not main_parts:
            self._print_unknown_command(user_input)
            return

        try:
            point_id = int(main_parts[0])
        except ValueError:
            self._print_unknown_command(user_input)
            return

        with self.state.lock:
            point = get_point_by_id(self.state, point_id)
        if not point:
            print(f"  -> Punkt #{point_id} nicht gefunden!")
            return

        wait_cond, delay, delay_max = self._parse_point_options(main_parts, point)
        if wait_cond is False:  # Sentinel: Parse-Fehler, schon ausgegeben
            return

        step = SequenceStep(
            x=point.x, y=point.y, delay_before=delay,
            name=point.name or f"#{point_id}",
            point_id=point_id,          # Referenz statt blosser Kopie
            wait_condition=wait_cond,
            delay_max=delay_max,
        )
        # Farbe übernehmen: bevorzugt die bei der Punkt-Aufnahme gespeicherte
        # (Spiel war da im richtigen Zustand), sonst Live-Abgriff als Fallback.
        if point.color:
            step.recorded_color = point.color
        else:
            try:
                from ...winapi import get_screen_pixel
                step.recorded_color = get_screen_pixel(point.x, point.y)
            except Exception:
                pass
        apply_else_to_step(step, else_parts, self.state)
        self.add_step(step)

    def _handle_verify(self, user_input: str) -> None:
        """Nachprüfung setzen/entfernen: "hat dieser Schritt gewirkt?".

        Formate:
          verify <Schritt-Nr> <Punkt-Nr> [gone]   — Punkt aus der Punkte-Liste prüfen
          verify <Schritt-Nr> maus [gone]         — Stelle unter der Maus abgreifen
          verify <Schritt-Nr> off                 — Nachprüfung entfernen

        Warum ein eigener Punkt statt des Klickziels: geprüft wird meist NICHT dort,
        wo geklickt wurde, sondern die Wirkung woanders (Fenster geht auf, Zähler
        springt). Deshalb eine freie Stelle — dieselbe Mechanik wie `wait <Punkt-Nr>`.
        """
        teile = user_input.split()
        if len(teile) < 3:
            print("  -> Format: verify <Schritt-Nr> <Punkt-Nr>|maus|off [gone]")
            print(f"     {hint('prueft NACH der Aktion, ob sie gewirkt hat')}")
            return
        step = self._get_step_by_num(teile[1])
        if step is None:
            return
        ziel = teile[2].lower()
        until_gone = len(teile) > 3 and teile[3].lower() in ("gone", "weg")

        if ziel in ("off", "aus", "none"):
            step.verify_condition = None
            print(ok("Nachprüfung entfernt"))
            return

        if ziel in ("maus", "mouse"):
            px, py, color = capture_pixel_color()
            if color is None:
                return
            punkt_id = self._punkt_fuer(px, py, color, "Nachprüfung")
        else:
            try:
                punkt_id = int(ziel)
            except ValueError:
                print("  -> Format: verify <Schritt-Nr> <Punkt-Nr>|maus|off [gone]")
                return
            with self.state.lock:
                punkt = get_point_by_id(self.state, punkt_id)
            if not punkt:
                print(f"  -> Punkt #{punkt_id} nicht gefunden! {hint('(siehe points)')}")
                return
            if not punkt.color:
                print(warn(f"  -> Punkt #{punkt_id} hat keine Farbe — es gäbe nichts zu vergleichen."))
                print(hint("     Im Punkte-Menü mit 'walk' die Farbe nachtragen."))
                return
            px, py = punkt.x, punkt.y

        step.verify_condition = WaitCondition(point_id=punkt_id, pixel=(px, py),
                                              until_gone=until_gone)
        # Farbe direkt aus dem Punkt mitnehmen, damit die Anzeige sofort stimmt;
        # gespeichert wird nur die Referenz.
        with self.state.lock:
            p = get_point_by_id(self.state, punkt_id)
        if p and p.color:
            step.verify_condition.color = p.color
        zustand = "WEG ist" if until_gone else "DA ist"
        print(ok(f"Nachprüfung gesetzt: nach der Aktion muss die Farbe bei "
                 f"({px},{py}) {zustand}"))
        n = max(0, self.state.config.verify_retries)
        print(hint(f"       Bleibt sie aus, wird die Aktion {n}× wiederholt "
                   f"(config: verify_retries), dann greift else."))

    def _punkt_fuer(self, x, y, color, name):
        """Punkt-ID für eine frisch abgegriffene Stelle - legt sie notfalls an.

        Jede Stelle, die ein Editor erzeugt, muss als Punkt existieren; sonst hätte
        der Schritt eine Koordinate, die nirgends sonst steht.
        """
        from ...persistence import punkt_fuer_stelle
        with self.state.lock:
            return punkt_fuer_stelle(self.state, x, y, color, name,
                                     source="Sequenz-Editor")

    def _resolve_trigger_color(self, until_gone: bool, point):
        """Liefert (pixel, color, punkt_id, until_gone) für einen color|colorgone-Trigger.

        Standard: die bei der Punkt-Aufnahme gespeicherte Farbe an der Punkt-
        Position (stimmt meistens). Nur wenn der Punkt keine Farbe hat, wird
        live an der Mausposition abgegriffen. Override später per 'recolor <Nr>'.

        Im Normalfall ist die Punkt-ID die des übergebenen Punkts - geprüft wird ja
        genau dort, wo geklickt wird. Nur beim Live-Abgriff entsteht ein eigener Punkt.
        """
        if point.color:
            print(f"  Nutze Punkt-Farbe RGB{point.color} bei ({point.x}, {point.y}) "
                  f"{hint('(mit recolor <Nr> änderbar)')}")
            return (point.x, point.y), point.color, point.id, until_gone
        px, py, color = capture_pixel_color()
        if color:
            return (px, py), color, self._punkt_fuer(px, py, color, "Prüf-Pixel"), until_gone
        return None, None, None, until_gone

    def _parse_point_options(self, main_parts: list[str], point):
        """Parst die Optionen nach der Punkt-ID. Returns (wait_condition, delay, delay_max).

        Bei Parse-Fehler: (False, 0, None) — der Caller bricht ab, Fehler ist
        bereits ausgegeben.
        """
        delay = 0
        delay_max = None
        wait_pixel = None
        wait_color = None
        wait_punkt_id = None
        wait_until_gone = False
        check_only = False

        if len(main_parts) > 1:
            arg = main_parts[1].lower()

            if arg in _CHECK_POINT_TRIGGER_ALIASES:
                # <Nr> checkcolor / <Nr> checkgone - einmal pruefen, sonst ueberspringen
                check_only = True
                wait_until_gone = _CHECK_POINT_TRIGGER_ALIASES[arg]
                wait_pixel, wait_color, wait_punkt_id, _ = \
                    self._resolve_trigger_color(wait_until_gone, point)
                if wait_color is None:
                    print(f"  -> {err('Keine Farbe lesbar - Farbpruefung nicht erstellt.')}")
                    return False, 0, None
            elif arg in _WAIT_POINT_TRIGGER_ALIASES:
                # <Nr> color / <Nr> colorgone
                wait_until_gone = (_WAIT_POINT_TRIGGER_ALIASES[arg] == "gone")
                wait_pixel, wait_color, wait_punkt_id, _ = \
                    self._resolve_trigger_color(wait_until_gone, point)
                if wait_color is None:
                    # Keine Farbe lesbar — Farb-Trigger gewünscht, kann aber
                    # nicht erstellt werden. Lieber abbrechen als kommentarlos
                    # einen normalen Klick anzulegen.
                    print(f"  -> {err('Keine Farbe lesbar — Farb-Trigger nicht erstellt.')}")
                    return False, 0, None
            elif "-" in arg:
                # <Nr> <Min>-<Max>
                range_val, range_err = parse_non_negative_range(arg, "Wartezeit")
                if range_err:
                    print(f"  -> {range_err}")
                    print("     Format: <Nr> <Min>-<Max> (z.B. 1 5-10)")
                    return False, 0, None
                delay, delay_max = range_val
            else:
                # <Nr> <Zeit>
                delay_val, delay_err = parse_non_negative_float(arg, "Wartezeit")
                if delay_err:
                    print(f"  -> {delay_err}")
                    print("     Format: <Nr> <Zeit> (z.B. 1 5)")
                    return False, 0, None
                delay = delay_val

                # Optional: <Nr> <Zeit> color/colorgone/checkcolor/checkgone
                if len(main_parts) > 2:
                    opt = main_parts[2].lower()
                    if opt in _CHECK_POINT_TRIGGER_ALIASES:
                        check_only = True
                        wait_until_gone = _CHECK_POINT_TRIGGER_ALIASES[opt]
                        wait_pixel, wait_color, wait_punkt_id, _ = \
                            self._resolve_trigger_color(wait_until_gone, point)
                        if wait_color is None:
                            print(f"  -> {err('Keine Farbe lesbar - Farbpruefung nicht erstellt.')}")
                            return False, 0, None
                    elif opt in _WAIT_POINT_TRIGGER_ALIASES:
                        opt_until_gone = (_WAIT_POINT_TRIGGER_ALIASES[opt] == "gone")
                        wait_pixel, wait_color, wait_punkt_id, wait_until_gone = \
                            self._resolve_trigger_color(opt_until_gone, point)
                        if wait_color is None:
                            print(f"  -> {err('Keine Farbe lesbar — Farb-Trigger nicht erstellt.')}")
                            return False, 0, None

        wait_cond = None
        if wait_pixel and wait_color:
            wait_cond = WaitCondition(point_id=wait_punkt_id,
                                      pixel=wait_pixel, color=wait_color,
                                      until_gone=wait_until_gone,
                                      check_only=check_only)
        return wait_cond, delay, delay_max

    def _print_unknown_command(self, user_input: str) -> None:
        """Druckt 'Unbekannter Befehl' + Tippfehler-Vorschlag."""
        suggestion = suggest_command(user_input, _KNOWN_COMMANDS)
        print(f"  -> Unbekannter Befehl.{suggestion} {hint('(? = Hilfe)')}")


# =============================================================================
# ÖFFENTLICHE API
# =============================================================================

def edit_phase(state: AutoClickerState, steps: list[SequenceStep],
               phase_name: str) -> Optional[list[SequenceStep]]:
    """Bearbeitet eine Phase (Init/Loop/End) der Sequenz interaktiv.

    Returns:
        Liste der Schritte bei 'done', None bei 'cancel'.
    """
    return _PhaseEditor(state, steps, phase_name).run()
