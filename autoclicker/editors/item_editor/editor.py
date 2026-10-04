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


class _ItemTransaction:
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
            self.file = (sequence_dir(cfg.owner_sequence) / "item_scans"
                          / f"{sanitize_filename(cfg.name)}.json")
        self.folder = active_templates_dir(state)
        self.files = {p: p.read_bytes() for p in self.folder.rglob("*") if p.is_file()}
        self.files[self.file] = self.file.read_bytes() if self.file.exists() else None

    def discard(self, state):
        # Dateien zuerst: schlägt die Wiederherstellung fehl, bleibt die
        # Sitzung offen und dieselbe Sicherung steht zum Wiederholen bereit.
        for path, content in self.files.items():
            if content is None:
                path.unlink(missing_ok=True)
            elif not path.exists() or path.read_bytes() != content:
                atomic_write(path, content)
        for path in self.folder.rglob("*"):
            if path.is_file() and path not in self.files:
                path.unlink()
        with state.lock:
            cfg = state.item_scans.get(self.name)
            if cfg is not None:
                cfg.items = copy.deepcopy(self.scan_items)
                # Die Arbeitsansicht muss dieselben Objekte wie der Scan sehen.
                state.global_items = {item.name: item for item in cfg.items}


def _cancel(state, transaction) -> bool:
    try:
        transaction.discard(state)
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
        transaction = _ItemTransaction(state)
    except (OSError, ValueError) as e:
        print(err(f"Item-Editor konnte nicht vorbereitet werden: {e}"))
        return

    _print_editor_overview(state)
    _print_item_help()

    while True:
        try:
            if _editor_step(state, transaction):
                return
        except (KeyboardInterrupt, EOFError):
            if _cancel(state, transaction):
                return
        except OSError as e:
            print(err(f"Dateioperation fehlgeschlagen: {e}"))


_KNOWN = ["autoscan", "learn", "add", "edit", "rename", "autoname", "del", "show",
          "template", "templates", "save", "load", "preset", "help", "done", "cancel"]


def _editor_step(state: AutoClickerState, transaction: _ItemTransaction) -> bool:
    """Eine Eingabe des Item-Editors. True = der Editor ist beendet."""
    with state.lock:
        item_count = len(state.global_items)
    user_input = safe_input(f"[ITEMS: {item_count}] > ").strip()
    cmd = user_input.lower()

    if cmd in ("done", "d"):
        if not save_global_items(state):
            print(err("Speichern fehlgeschlagen — der Editor bleibt offen."))
            return False
        print(ok("Item-Editor beendet."))
        return True
    if is_cancel(cmd):
        return _cancel(state, transaction)
    if cmd and not _dispatch_command(state, cmd, user_input):
        suggestion = suggest_command(cmd, _KNOWN)
        print(f"  -> Unbekannter Befehl.{suggestion} {hint('(? = Hilfe)')}")
    return False


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
    """Verarbeitet einen Editor-Befehl. Gibt False zurück wenn der Befehl unbekannt ist.

    Ganze Befehle zuerst (`del all` vor `del <Nr>`, `templates` vor
    `template <Nr>`), dann die Präfixe in fester Reihenfolge. `autoscan` und
    `learn` bekommen die ganze Eingabe — sie lesen ihre Modi selbst.
    """
    handler = _EXACT.get(cmd)
    if handler is None:
        handler = next((h for prefix, h in _PREFIXED if cmd.startswith(prefix)), None)
    if handler is None:
        return False
    handler(state, cmd, user_input)
    return True


def _cmd_help(state, cmd, user_input) -> None:
    _print_item_help()


def _cmd_help_full(state, cmd, user_input) -> None:
    _print_item_help(full=True)


def _cmd_show(state, cmd, user_input) -> None:
    with state.lock:
        if not state.global_items:
            print("  (Keine Items)")
            return
        print(f"\nItems ({len(state.global_items)}):")
        # Alle Nummernbefehle verwenden dieselbe Einfügereihenfolge.
        for i, item in enumerate(state.global_items.values()):
            print(f"  {i+1}. {item}")


def _cmd_autoscan(state, cmd, user_input) -> None:
    item_autoscan_command(state, cmd)


def _cmd_learn(state, cmd, user_input) -> None:
    item_learn_command(state, cmd)


def _cmd_add(state, cmd, user_input) -> None:
    item = create_item(state)
    if item:
        with state.lock:
            state.global_items[item.name] = item
        print(f"  + Item '{item.name}' hinzugefügt")


def _cmd_edit(state, cmd, user_input) -> None:
    _handle_edit(state, cmd)


def _cmd_delete_all(state, cmd, user_input) -> None:
    _handle_delete_all(state)


def _cmd_delete_one(state, cmd, user_input) -> None:
    _handle_delete_single(state, cmd)


def _cmd_rename(state, cmd, user_input) -> None:
    handle_rename_command(state, cmd)


def _cmd_autoname(state, cmd, user_input) -> None:
    handle_autoname_command(state)


def _cmd_templates(state, cmd, user_input) -> None:
    handle_templates_command(state)


def _cmd_template(state, cmd, user_input) -> None:
    handle_template_command(state, cmd)


def _preset_command(user_input: str, prefix: str, action, usage: str) -> None:
    """Preset-Befehle: der Name behält die getippte Schreibweise."""
    preset_name = user_input[len(prefix):].strip()
    if preset_name:
        action(preset_name)
    else:
        print(f"  -> Format: {usage}")


def _cmd_preset_save(state, cmd, user_input) -> None:
    _preset_command(user_input, "save ", lambda name: save_item_preset(state, name),
                    "save <Name>")


def _cmd_preset_load(state, cmd, user_input) -> None:
    _preset_command(user_input, "load ", lambda name: load_item_preset(state, name),
                    "load <Name>")


def _cmd_preset_delete(state, cmd, user_input) -> None:
    _preset_command(user_input, "preset del ", delete_item_preset, "preset del <Name>")


_EXACT = {
    "help": _cmd_help,
    "?": _cmd_help_full, "help full": _cmd_help_full, "??": _cmd_help_full,
    "show": _cmd_show, "s": _cmd_show,
    "add": _cmd_add,
    "del all": _cmd_delete_all,
    "autoname": _cmd_autoname,
    "templates": _cmd_templates,
}
_PREFIXED = [
    ("autoscan", _cmd_autoscan),
    ("learn", _cmd_learn),
    ("edit ", _cmd_edit),
    ("del ", _cmd_delete_one),
    ("rename ", _cmd_rename),
    ("template ", _cmd_template),
    ("save ", _cmd_preset_save),
    ("load ", _cmd_preset_load),
    ("preset del ", _cmd_preset_delete),
]


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
                collision = new_item.name != name and new_item.name in state.global_items
            if collision and not confirm(f"  '{new_item.name}' existiert bereits. Überschreiben?"):
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
