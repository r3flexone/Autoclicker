"""
Weitere Item-Editor-Befehle: rename, template, templates.

- rename: Item umbenennen inkl. Template-Datei (ein Item gehört genau einem Scan)
- templates: Listet verfügbare Template-PNGs auf
- template: Setzt/entfernt/captured ein Template für ein Item
"""


from ...imaging import take_screenshot, select_region
from ...models import AutoClickerState
from ...persistence import save_scan_items, active_templates_dir, free_template_file
from ...utils import (confirm, is_cancel, safe_input, sanitize_filename, unique_name,
                      clean_item_name, ok, err, info, hint)
from .._detection_capture import ask_min_confidence
from ..scan_services import save_template


def handle_rename_command(state: AutoClickerState, cmd: str) -> None:
    """Verarbeitet den rename-Befehl im Item-Editor."""
    try:
        rename_num = int(cmd[7:])

        # Daten unter Lock lesen, dann Lock freigeben für User-Input
        with state.lock:
            item_names = list(state.scan_items.keys())
            if rename_num < 1 or rename_num > len(item_names):
                print(f"  -> Ungültiges Item! Verfügbar: 1-{len(item_names)}")
                return
            old_name = item_names[rename_num - 1]
            old_template = state.scan_items[old_name].template

        # User-Input OHNE Lock (blockiert nicht andere Threads)
        print(f"\n  Aktueller Name: '{old_name}'")
        if old_template:
            print(f"  Template: {old_template}")

        new_name = safe_input("  Neuer Name (Enter = abbrechen): ").strip()
        if not new_name or is_cancel(new_name):
            print("  -> Abgebrochen")
            return

        if new_name == old_name:
            print("  -> Name ist identisch, nichts geändert")
            return

        with state.lock:
            name_exists = new_name in state.scan_items
        if name_exists:
            if not confirm(f"  '{new_name}' existiert bereits. Überschreiben?"):
                print("  -> Abgebrochen")
                return

        if _apply_item_rename(state, old_name, new_name, overwrite=name_exists):
            print(f"  + Item umbenannt: '{old_name}' -> '{new_name}' (Übernehmen mit done)")
    except ValueError:
        print("  -> Format: rename <Nr>")


def _apply_item_rename(state: AutoClickerState, old_name: str, new_name: str,
                       *, overwrite: bool = False) -> bool:
    """Benennt ein Item mechanisch um: Template-Datei und scan_items.

    Scan-Configs ziehen nicht mit — ein Item gehört genau einem Scan, der danach
    als Ganzes gespeichert wird.

    Still (keine Prompts) — für programmatische Aufrufe wie 'autoname'. new_name
    muss eindeutig sein, ausser der Aufrufer hat Überschreiben bestätigt.
    Ein Dateifehler lässt den bisherigen Namen und die Referenz unverändert.
    """
    with state.lock:
        if old_name not in state.scan_items:
            return False
        if new_name != old_name and new_name in state.scan_items and not overwrite:
            print(err(f"'{new_name}' existiert bereits — Umbenennen abgebrochen."))
            return False
        item = state.scan_items[old_name]
        old_template = item.template
        # Der Vorlagenordner gehört der Sequenz; andere Scans dürfen dieselbe
        # Datei verwenden. Deren Referenzen bleiben beim Umbenennen erhalten.
        other_items = [*state.scan_items.values(),
                        *(i for cfg in state.item_scans.values() for i in cfg.items)]
        detector = [*state.icon_scans.values(), *state.boss_library,
                    *(b for cfg in state.boss_scans.values() for b in cfg.bosses)]
        shared = old_template and (
            any(i is not item and old_template in i.template_names() for i in other_items)
            or old_template in item.template_variants
            or any(e.template == old_template for e in detector))

    new_template = None
    if old_template:
        old_path = active_templates_dir(state) / old_template
        new_template = old_template if shared else f"{sanitize_filename(new_name)}.png"
        new_path = active_templates_dir(state) / new_template
        try:
            if not old_path.is_file():
                raise OSError(f"Vorlage '{old_template}' fehlt")
            if old_path != new_path:
                if new_path.exists():
                    raise OSError(f"Vorlage '{new_template}' existiert bereits")
                old_path.rename(new_path)
        except OSError as e:
            print(err(f"Umbenennen fehlgeschlagen: {e}"))
            return False

    with state.lock:
        if old_name not in state.scan_items:
            return False
        item = state.scan_items[old_name]
        item.name = new_name
        if new_template is not None:
            item.template = new_template
        del state.scan_items[old_name]
        state.scan_items[new_name] = item
    # Ein Item gehoert genau einem Scan; der wird danach als Ganzes gespeichert.
    # Gleichnamige Items anderer Scans ziehen ausdruecklich nicht mit.
    return True


def llm_name_items(state: AutoClickerState, targets: list[tuple[str, str]]) -> int:
    """Benennt die (name, template)-Items per LLM aus ihren gespeicherten Templates.

    Blockierend (LLM-Antworten dauern) — daher NUR ausserhalb eines laufenden
    Scans aufrufen (Editor/Setup). Speichert NICHT selbst; der Aufrufer macht
    save_scan_items, wenn der Rückgabewert > 0 ist. Gibt die Anzahl
    umbenannter Items zurück.
    """
    from ...llm_vision import suggest_item_name
    try:
        from PIL import Image
    except ImportError:
        print(f"  {err('Pillow nicht installiert.')}")
        return 0

    renamed = 0
    for old_name, template in targets:
        img = _open_template_copy(state, old_name, template, Image)
        if img is None:
            continue
        suggestion = suggest_item_name(
            img,
            provider=state.config.llm_provider,
            endpoint=state.config.llm_endpoint,
            model=state.config.llm_model,
            timeout=state.config.llm_timeout,
            reasoning=state.config.llm_reasoning,
            max_tokens=state.config.llm_max_tokens,
        )
        base = clean_item_name(suggestion) if suggestion else ""
        if not base:
            print(f"    {old_name}: kein Name vom LLM — bleibt.")
            continue
        # Eindeutig — wobei der eigene, alte Name nicht als belegt zählt.
        with state.lock:
            new_name = unique_name(base, set(state.scan_items) - {old_name})
        if new_name != old_name and _apply_item_rename(state, old_name, new_name):
            print(f"    + '{old_name}' → '{new_name}'")
            renamed += 1
    return renamed


def _open_template_copy(state: AutoClickerState, item_name: str, template: str, image_module):
    """Die Vorlage als Kopie im Speicher — oder None (fehlt/unlesbar, gesagt).

    Als Kopie gelesen und die Datei sofort geschlossen: `Image.open()` liest
    träge und hält die Datei offen — unter Windows scheiterte das Umbenennen
    danach mit WinError 32.
    """
    tpl_path = active_templates_dir(state) / template
    if not tpl_path.exists():
        print(f"    {item_name}: Template fehlt — übersprungen.")
        return None
    try:
        with image_module.open(tpl_path) as opened:
            return opened.copy()
    except (OSError, ValueError):
        print(f"    {item_name}: Template nicht lesbar — übersprungen.")
        return None


def handle_autoname_command(state: AutoClickerState) -> None:
    """Benennt auto-gelernte Items ('Auto …') per LLM aus ihren gespeicherten Templates.

    Läuft NUR auf Befehl — bewusst nicht während eines Scans, weil LLM-Antworten
    je Item mehrere Sekunden dauern können und den Lauf ausbremsen würden.
    """
    if not state.config.llm_enabled:
        print(f"  {err('LLM ist nicht aktiviert')} {hint('(llm_enabled=false in config.json)')}")
        return

    # Auto-gelernte Items mit Template (Kategorie 'Auto')
    with state.lock:
        targets = [(n, it.template) for n, it in state.scan_items.items()
                   if it.category == "Auto" and it.template]
    if not targets:
        print("  " + info("Keine auto-gelernten Items (Kategorie 'Auto') mit Template gefunden."))
        return

    print(f"\n  {len(targets)} Item(s) werden per LLM benannt.")
    print(f"  {hint('Das kann je Item ein paar Sekunden dauern (LLM).')}")
    if not confirm("  Jetzt starten?"):
        print("  -> Abgebrochen")
        return

    renamed = llm_name_items(state, targets)
    if renamed:
        save_scan_items(state)
    print(f"  {ok(f'{renamed} Item(s) benannt.')}")


def handle_templates_command(state: AutoClickerState) -> None:
    """Zeigt verfügbare Templates an."""
    templates_dir = active_templates_dir(state)
    if not templates_dir.exists():
        print("  -> Keine Templates vorhanden")
        return
    templates = list(templates_dir.glob("*.png"))
    if not templates:
        print("  -> Keine Templates vorhanden")
        print(f"    (Ordner: {templates_dir})")
    else:
        print(f"\n  Verfügbare Templates ({len(templates)}):")
        for t in sorted(templates):
            print(f"    - {t.name}")


def handle_template_command(state: AutoClickerState, cmd: str) -> None:
    """Verarbeitet den template-Befehl im Item-Editor (setzen/entfernen/capturen).

    **Der Lock wird nur zum Nachschlagen gehalten, nicht während der Eingabe.**
    `state.lock` ist ein `threading.Lock`, kein RLock: hier lag vorher der
    ganze Dialog samt `safe_input()` darunter — und `capture` rief
    `_capture_template_for_item()`, das den Lock ein zweites Mal nimmt. Der
    Main-Thread stand damit auf sich selbst, und mit ihm jeder Hotkey: das
    Programm liess sich nur noch von aussen beenden.
    """
    templates_dir = active_templates_dir(state)
    try:
        item_num = int(cmd[9:])
    except ValueError:
        print("  -> Format: template <Nr>")
        return
    with state.lock:
        item_names = list(state.scan_items.keys())
        item = (state.scan_items[item_names[item_num - 1]]
                if 1 <= item_num <= len(item_names) else None)
    if item is None:
        print("  -> Ungültiges Item!")
        return

    templates = list(templates_dir.glob("*.png")) if templates_dir.exists() else []
    if templates:
        print("\n  Verfügbare Templates:")
        for i, t in enumerate(sorted(templates)):
            print(f"    {i+1}. {t.name}")

    current = ", ".join(item.template_names()) or "Keins"
    print(f"\n  Item: {item.name}")
    print(f"  Aktuelles Template: {current}")
    print(f"  Aktuelle Konfidenz: {item.min_confidence:.0%}")

    print("\n  Optionen:")
    print("    <Dateiname.png> - Template setzen")
    print("    <Nr>            - Template aus Liste wählen")
    print("    capture         - Screenshot als Template speichern")
    print("    remove          - Template entfernen")
    print("    Enter           - Abbrechen")

    template_input = safe_input("  Template: ").strip()
    if not template_input:
        return

    if template_input.lower() == "remove":
        with state.lock:
            item.template = None
            item.template_variants.clear()
        print("  + Alle Vorlagen entfernt!")
    elif template_input.lower() == "capture":
        _capture_template_for_item(state, item)
    else:
        # Fragt selbst nach der Konfidenz — also nicht unter dem Lock. Der
        # Worker laeuft waehrend des Editors ohnehin nicht (_block_if_running).
        _assign_template_to_item(item, template_input, templates)


def _capture_template_for_item(state: AutoClickerState, item) -> None:
    """Capture-Variante: Screenshot von Slot oder freier Region als Template speichern."""
    region = _ask_capture_region(state)
    if not region:
        return
    img = take_screenshot(region)
    if img is None:
        print("  -> Screenshot fehlgeschlagen!")
        return

    template_file = _template_file_for(state, item, img.size)
    save_template(state, img, template_file)
    if not item.template:
        item.template = template_file
    elif template_file != item.template and template_file not in item.template_variants:
        item.template_variants.append(template_file)

    item.min_confidence = ask_min_confidence(
        item.min_confidence, f"  Min. Konfidenz (Enter={item.min_confidence:.0%}): ")
    print(f"  + Vorlage für {img.size[0]}x{img.size[1]} gespeichert: {template_file}")


def _ask_capture_region(state: AutoClickerState):
    """Woher das Bild kommt: ein Slot oder eine freie Region. None = nichts (ggf. gesagt).

    Ohne Slots und bei einer Eingabe, die keine Zahl ist, wird direkt eine
    Region gewählt; eine Slot-Nummer ausserhalb wird gesagt.
    """
    with state.lock:
        slot_list = list(state.scan_slots.values())
    if not slot_list:
        return select_region()

    print("\n  Screenshot von:")
    print("    0. Freie Region wählen")
    for i, slot in enumerate(slot_list):
        print(f"    {i+1}. {slot.name}")
    slot_choice = safe_input("  Auswahl: ").strip()
    if slot_choice == "0":
        return select_region()
    try:
        slot_idx = int(slot_choice) - 1
    except ValueError:
        return select_region()
    if 0 <= slot_idx < len(slot_list):
        return slot_list[slot_idx].scan_region
    print("  -> Ungültiger Slot!")
    return None


def _template_file_for(state: AutoClickerState, item, size: tuple) -> str:
    """Welche Datei das neue Bild wird.

    Dieselbe Slot-Groesse wird bewusst aktualisiert — die Datei gehoert diesem
    Item. Eine andere Groesse wird eine Variante `<Name>_<B>x<H>`, das erste Bild
    heisst wie das Item.
    """
    from ...imaging import template_size
    folder = active_templates_dir(state)
    matching = [name for name in item.template_names()
                if template_size(name, folder) == tuple(size)]
    if matching:
        return matching[0]
    if item.template_names():
        return free_template_file(folder, f"{item.name}_{size[0]}x{size[1]}")
    return free_template_file(folder, item.name)


def _assign_template_to_item(item, template_input: str, templates: list) -> None:
    """Weist dem Item ein bestehendes Template zu (per Nummer oder Dateiname)."""
    try:
        template_num = int(template_input)
        if 1 <= template_num <= len(templates):
            item.template = sorted(templates)[template_num - 1].name
        else:
            print("  -> Ungültige Nummer!")
            return
    except ValueError:
        if not template_input.endswith(".png"):
            template_input += ".png"
        item.template = template_input

    item.min_confidence = ask_min_confidence(
        item.min_confidence,
        f"  Min. Konfidenz (aktuell {item.min_confidence:.0%}, Enter=behalten): ")
    print(f"  + Template gesetzt: {item.template} (>={item.min_confidence:.0%})")
