"""
Hauptschleife des Item-Editors: interaktive Befehls-Verarbeitung.

run_global_item_editor zeigt die Übersicht, sammelt User-Befehle und dispatcht
an die passenden Handler in items.py, autoscan.py, learn.py, commands.py.
Backup-Snapshot bei Editor-Start, Restore bei Cancel/Strg+C.
"""

import copy

from ...imaging import PILLOW_AVAILABLE
from ...models import AutoClickerState
from ...persistence import (
    delete_item_preset, list_item_presets, load_item_preset,
    save_global_items, save_item_preset,
)
from ...utils import (
    breadcrumb, cancel_hint, cmd_hint, col, confirm, err, header, hint,
    is_cancel, ok, safe_input, suggest_command,
)
from .autoscan import item_autoscan_command
from .commands import handle_rename_command, handle_template_command, handle_templates_command, handle_autoname_command
from .items import create_item, edit_item
from .learn import item_learn_command
from ...persistence.sequences import active_templates_dir, sequence_dir
from ...utils import atomic_write, sanitize_filename


class _ItemTransaktion:
    """Sichert Scan und Vorlagen auch über zwischendurch speichernde Befehle.

    Preset-Exporte sind ausdrücklich eigene Aktionen. Gesichert werden der
    bearbeitete Scan und der zugehörige Template-Ordner, nicht die Presets.
    """

    def __init__(self, state):
        with state.lock:
            self.name = state.active_item_scan
            cfg = state.item_scans.get(self.name)
            if cfg is None:
                raise ValueError("Bitte zuerst einen Item-Scan wählen.")
            self.scan_items = copy.deepcopy(cfg.items)
            self.datei = (sequence_dir(cfg.owner_sequence) / "item_scans"
                          / f"{sanitize_filename(cfg.name)}.json")
        self.ordner = active_templates_dir(state)
        self.dateien = {p: p.read_bytes() for p in self.ordner.rglob("*") if p.is_file()}
        self.dateien[self.datei] = self.datei.read_bytes() if self.datei.exists() else None

    def verwerfen(self, state):
        # Dateien zuerst: schlägt die Wiederherstellung fehl, bleibt die
        # Sitzung offen und dieselbe Sicherung steht zum Wiederholen bereit.
        for pfad, inhalt in self.dateien.items():
            if inhalt is None:
                pfad.unlink(missing_ok=True)
            elif not pfad.exists() or pfad.read_bytes() != inhalt:
                atomic_write(pfad, inhalt)
        for pfad in self.ordner.rglob("*"):
            if pfad.is_file() and pfad not in self.dateien:
                pfad.unlink()
        with state.lock:
            cfg = state.item_scans.get(self.name)
            if cfg is not None:
                cfg.items = copy.deepcopy(self.scan_items)
                # Die Arbeitsansicht muss dieselben Objekte wie der Scan sehen.
                state.global_items = {item.name: item for item in cfg.items}


def _abbrechen(state, transaktion) -> bool:
    try:
        transaktion.verwerfen(state)
    except OSError as e:
        print(err(f"Abbruch konnte nicht vollständig zurückgesetzt werden: {e}"))
        return False
    print(col("[ABBRUCH]", "yellow") + " Änderungen verworfen.")
    return True


def run_global_item_editor(state: AutoClickerState) -> None:
    """Interaktiver Editor für die Items des gewählten Item-Scans."""
    print(header("ITEM-EDITOR (gewählter Item-Scan)"))
    print(f"  {breadcrumb('Hauptmenü', 'Item-Scan', 'Items')}")

    if not PILLOW_AVAILABLE:
        print(f"\n{err('Pillow nicht installiert!')}")
        print("         Installieren mit: pip install pillow")
        return

    try:
        transaktion = _ItemTransaktion(state)
    except (OSError, ValueError) as e:
        print(err(f"Item-Editor konnte nicht vorbereitet werden: {e}"))
        return

    _print_editor_overview(state)
    _print_item_help()

    while True:
        try:
            with state.lock:
                item_count = len(state.global_items)
            prompt = f"[ITEMS: {item_count}]"
            user_input = safe_input(f"{prompt} > ").strip()
            cmd = user_input.lower()

            if cmd in ("done", "d"):
                if not save_global_items(state):
                    print(err("Speichern fehlgeschlagen — der Editor bleibt offen."))
                    continue
                print(ok("Item-Editor beendet."))
                return
            elif is_cancel(cmd):
                if _abbrechen(state, transaktion):
                    return
                continue
            elif cmd == "":
                continue

            if not _dispatch_command(state, cmd, user_input):
                _known = ["autoscan", "learn", "add", "edit", "rename", "autoname", "del", "show",
                          "template", "templates", "save", "load", "preset",
                          "help", "done", "cancel"]
                suggestion = suggest_command(cmd, _known)
                print(f"  -> Unbekannter Befehl.{suggestion} {hint('(? = Hilfe)')}")

        except (KeyboardInterrupt, EOFError):
            if _abbrechen(state, transaktion):
                return
        except OSError as e:
            print(err(f"Dateioperation fehlgeschlagen: {e}"))


def _print_editor_overview(state: AutoClickerState) -> None:
    """Druckt den Status-Block beim Editor-Start (Items, Slots, Presets)."""
    with state.lock:
        current_items = list(state.global_items.items())

    if current_items:
        print(f"\nAktuelle Items ({len(current_items)}):")
        for i, (name, item) in enumerate(current_items):
            print(f"  {i+1}. {item}")
    else:
        print("\n  (Keine Items vorhanden)")

    with state.lock:
        slots = dict(state.global_slots)
    if slots:
        print(f"\nVerfügbare Slots für Item-Lernen ({len(slots)}):")
        for i, (name, slot) in enumerate(slots.items()):
            print(f"  {i+1}. {slot.name}")

    presets = list_item_presets()
    if presets:
        print(f"\nVerfügbare Presets ({len(presets)}):")
        for name, path, count in presets:
            print(f"  - {name} ({count} Items)")


def _print_item_help(full: bool = False) -> None:
    """Druckt die Befehls-Übersicht (kurz oder vollständig)."""
    if not full:
        print("\n  Kurzübersicht (? / ?? = vollständige Hilfe):")
        print("    autoscan         ALLE Slots automatisch scannen + Items erstellen")
        print("    learn <Nr>       Item aus Slot lernen")
        print("    add              Neues Item manuell")
        print("    edit <Nr>        Item bearbeiten")
        print("    del <Nr>         Item löschen")
        print("    show / s         Alle Items anzeigen")
        print(f"    done / d | cancel / {cancel_hint()}  Fertig / Abbrechen")
    else:
        print("\n" + "-" * 60)
        print("Befehle:")
        print(cmd_hint("autoscan", "ALLE Slots automatisch scannen + Items erstellen"))
        print(cmd_hint("autoscan nocolor", "Auto-Scan nur mit Templates (ohne Marker)"))
        print(cmd_hint("learn <Nr>", "Item aus Slot lernen (automatisch!)"))
        print(cmd_hint("learn <Nr>-<Nr>", "Bulk: Items für Slot-Bereich (mit Template)"))
        print(cmd_hint("learn <Nr>-<Nr> simple", "Bulk: ohne Template"))
        print(cmd_hint("add", "Neues Item manuell hinzufügen"))
        print(cmd_hint("edit <Nr>", "Item bearbeiten"))
        print(cmd_hint("rename <Nr>", "Item umbenennen (inkl. Template)"))
        print(cmd_hint("autoname", "Auto-gelernte 'Auto …'-Items per LLM benennen (manuell, nicht im Scan)"))
        print(cmd_hint("del <Nr>", "Item löschen"))
        print(cmd_hint("del all", "Alle Items löschen"))
        print(cmd_hint("show / s", "Alle Items anzeigen"))
        print(cmd_hint("template <Nr>", "Template für Item setzen/entfernen"))
        print(cmd_hint("templates", "Verfügbare Templates anzeigen"))
        print(cmd_hint("save <Name>", "Als Preset speichern"))
        print(cmd_hint("load <Name>", "Preset laden"))
        print(cmd_hint("preset del <N>", "Preset löschen"))
        print(cmd_hint("help", "Kurzübersicht"))
        print(cmd_hint("? / help full / ??", "Vollständige Hilfe"))
        print(cmd_hint("done / d", "Fertig"))
        print(cmd_hint(f"cancel / {cancel_hint()}", "Abbrechen"))
        print("-" * 60)


def _dispatch_command(state: AutoClickerState, cmd: str, user_input: str) -> bool:
    """Verarbeitet einen Editor-Befehl. Gibt False zurück wenn der Befehl unbekannt ist."""
    if cmd == "help":
        _print_item_help()
        return True

    if cmd in ("?", "help full", "??"):
        _print_item_help(full=True)
        return True

    if cmd in ("show", "s"):
        with state.lock:
            if state.global_items:
                print(f"\nItems ({len(state.global_items)}):")
                # Alle Nummernbefehle verwenden dieselbe Einfügereihenfolge.
                for i, item in enumerate(state.global_items.values()):
                    print(f"  {i+1}. {item}")
            else:
                print("  (Keine Items)")
        return True

    if cmd.startswith("autoscan"):
        item_autoscan_command(state, cmd)
        return True

    if cmd.startswith("learn"):
        item_learn_command(state, cmd)
        return True

    if cmd == "add":
        item = create_item(state)
        if item:
            with state.lock:
                state.global_items[item.name] = item
            print(f"  + Item '{item.name}' hinzugefügt")
        return True

    if cmd.startswith("edit "):
        _handle_edit(state, cmd)
        return True

    if cmd == "del all":
        _handle_delete_all(state)
        return True

    if cmd.startswith("del "):
        _handle_delete_single(state, cmd)
        return True

    if cmd.startswith("rename "):
        handle_rename_command(state, cmd)
        return True

    if cmd == "autoname":
        handle_autoname_command(state)
        return True

    if cmd == "templates":
        handle_templates_command(state)
        return True

    if cmd.startswith("template "):
        handle_template_command(state, cmd)
        return True

    if cmd.startswith("save "):
        preset_name = user_input[5:].strip()
        if preset_name:
            save_item_preset(state, preset_name)
        else:
            print("  -> Format: save <Name>")
        return True

    if cmd.startswith("load "):
        preset_name = user_input[5:].strip()
        if preset_name:
            load_item_preset(state, preset_name)
        else:
            print("  -> Format: load <Name>")
        return True

    if cmd.startswith("preset del "):
        preset_name = user_input[11:].strip()
        if preset_name:
            delete_item_preset(preset_name)
        else:
            print("  -> Format: preset del <Name>")
        return True

    return False


def _handle_edit(state: AutoClickerState, cmd: str) -> None:
    """Edit-Befehl: Item bearbeiten."""
    try:
        edit_num = int(cmd[5:])
        with state.lock:
            item_list = list(state.global_items.items())
            if not (1 <= edit_num <= len(item_list)):
                print(f"  -> Ungültig! Verfügbar: 1-{len(item_list)}")
                return
            name, item = item_list[edit_num - 1]
        # edit_item OHNE Lock (User-Input)
        new_item = edit_item(state, item)
        if new_item:
            with state.lock:
                kollision = new_item.name != name and new_item.name in state.global_items
            if kollision and not confirm(f"  '{new_item.name}' existiert bereits. Überschreiben?"):
                print(col("[ABBRUCH]", "yellow") + " Item unverändert.")
                return
            with state.lock:
                # Falls Name geändert wurde, alten Eintrag entfernen
                if new_item.name != name:
                    state.global_items.pop(name, None)
                state.global_items[new_item.name] = new_item
            print(f"  + Item '{new_item.name}' aktualisiert")
    except ValueError:
        print("  -> Format: edit <Nr>")


def _handle_delete_all(state: AutoClickerState) -> None:
    """`del all` — alle Items mit Bestätigung löschen."""
    with state.lock:
        if not state.global_items:
            print("  -> Keine Items vorhanden!")
            return
        count = len(state.global_items)
    if confirm(f"  {count} Item(s) wirklich löschen?"):
        with state.lock:
            state.global_items.clear()
        print(f"  + {count} Item(s) gelöscht!")
    else:
        print("  -> Abgebrochen")


def _handle_delete_single(state: AutoClickerState, cmd: str) -> None:
    """`del <Nr>` — ein einzelnes Item löschen."""
    try:
        del_num = int(cmd[4:])
        with state.lock:
            item_list = list(state.global_items.keys())
            if 1 <= del_num <= len(item_list):
                name = item_list[del_num - 1]
                del state.global_items[name]
                print(f"  + Item '{name}' gelöscht")
            else:
                print(f"  -> Ungültig! Verfügbar: 1-{len(item_list)}")
    except ValueError:
        print("  -> Format: del <Nr>")
