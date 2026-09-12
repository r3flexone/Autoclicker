"""
Weitere Item-Editor-Befehle: rename, template, templates.

- rename: Item umbenennen inkl. Template-Datei und Aktualisierung aller Scan-Configs
- templates: Listet verfügbare Template-PNGs auf
- template: Setzt/entfernt/captured ein Template für ein Item
"""


from ...imaging import take_screenshot, select_region
from ...models import AutoClickerState
from ...persistence import update_item_in_scans, save_global_items, active_templates_dir
from ...utils import (confirm, is_cancel, safe_input, sanitize_filename,
                      bereinige_itemname, ok, err, info, hint)


def handle_rename_command(state: AutoClickerState, cmd: str) -> None:
    """Verarbeitet den rename-Befehl im Item-Editor."""
    try:
        rename_num = int(cmd[7:])

        # Daten unter Lock lesen, dann Lock freigeben für User-Input
        with state.lock:
            item_names = list(state.global_items.keys())
            if rename_num < 1 or rename_num > len(item_names):
                print(f"  -> Ungültiges Item! Verfügbar: 1-{len(item_names)}")
                return
            old_name = item_names[rename_num - 1]
            old_template = state.global_items[old_name].template

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
            name_exists = new_name in state.global_items
        if name_exists:
            if not confirm(f"  '{new_name}' existiert bereits. Überschreiben?"):
                print("  -> Abgebrochen")
                return

        if _apply_item_rename(state, old_name, new_name, ueberschreiben=name_exists):
            print(f"  + Item umbenannt: '{old_name}' -> '{new_name}' (Übernehmen mit done)")
    except ValueError:
        print("  -> Format: rename <Nr>")


def _apply_item_rename(state: AutoClickerState, old_name: str, new_name: str,
                       *, ueberschreiben: bool = False) -> bool:
    """Benennt ein Item mechanisch um: Template-Datei, global_items, Scan-Configs.

    Still (keine Prompts) — für programmatische Aufrufe wie 'autoname'. new_name
    muss eindeutig sein, ausser der Aufrufer hat Überschreiben bestätigt.
    Ein Dateifehler lässt den bisherigen Namen und die Referenz unverändert.
    """
    with state.lock:
        if old_name not in state.global_items:
            return False
        if new_name != old_name and new_name in state.global_items and not ueberschreiben:
            print(err(f"'{new_name}' existiert bereits — Umbenennen abgebrochen."))
            return False
        item = state.global_items[old_name]
        old_template = item.template
        # Der Vorlagenordner gehört der Sequenz; andere Scans dürfen dieselbe
        # Datei verwenden. Deren Referenzen bleiben beim Umbenennen erhalten.
        andere_items = [*state.global_items.values(),
                        *(i for cfg in state.item_scans.values() for i in cfg.items)]
        erkenner = [*state.icon_scans.values(), *state.global_bosses,
                    *(b for cfg in state.boss_scans.values() for b in cfg.bosses)]
        geteilt = old_template and (
            any(i is not item and old_template in i.template_names() for i in andere_items)
            or old_template in item.template_variants
            or any(e.template == old_template for e in erkenner))

    new_template = None
    if old_template:
        old_path = active_templates_dir(state) / old_template
        new_template = old_template if geteilt else f"{sanitize_filename(new_name)}.png"
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
        if old_name not in state.global_items:
            return False
        item = state.global_items[old_name]
        item.name = new_name
        if new_template is not None:
            item.template = new_template
        del state.global_items[old_name]
        state.global_items[new_name] = item

    update_item_in_scans(old_name, new_name)
    return True


def llm_name_items(state: AutoClickerState, targets: list[tuple[str, str]]) -> int:
    """Benennt die (name, template)-Items per LLM aus ihren gespeicherten Templates.

    Blockierend (LLM-Antworten dauern) — daher NUR ausserhalb eines laufenden
    Scans aufrufen (Editor/Setup). Speichert NICHT selbst; der Aufrufer macht
    save_global_items, wenn der Rückgabewert > 0 ist. Gibt die Anzahl
    umbenannter Items zurück.
    """
    try:
        from ...llm_vision import suggest_item_name
    except ImportError:
        print(f"  {err('LLM-Vision-Modul nicht verfügbar.')}")
        return 0
    try:
        from PIL import Image
    except ImportError:
        print(f"  {err('Pillow nicht installiert.')}")
        return 0

    renamed = 0
    for old_name, template in targets:
        tpl_path = active_templates_dir(state) / template
        if not tpl_path.exists():
            print(f"    {old_name}: Template fehlt — übersprungen.")
            continue
        try:
            img = Image.open(tpl_path)
        except (OSError, ValueError):
            print(f"    {old_name}: Template nicht lesbar — übersprungen.")
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
        base = bereinige_itemname(suggestion) if suggestion else ""
        if not base:
            print(f"    {old_name}: kein Name vom LLM — bleibt.")
            continue

        # Eindeutigen Namen sicherstellen
        with state.lock:
            new_name = base
            counter = 1
            while new_name in state.global_items and new_name != old_name:
                counter += 1
                new_name = f"{base} {counter}"
        if new_name == old_name:
            continue
        if _apply_item_rename(state, old_name, new_name):
            print(f"    + '{old_name}' → '{new_name}'")
            renamed += 1
    return renamed


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
        targets = [(n, it.template) for n, it in state.global_items.items()
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
        save_global_items(state)
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
    """Verarbeitet den template-Befehl im Item-Editor (setzen/entfernen/capturen)."""
    templates_dir = active_templates_dir(state)
    try:
        item_num = int(cmd[9:])
        with state.lock:
            item_names = list(state.global_items.keys())
            if 1 <= item_num <= len(item_names):
                name = item_names[item_num - 1]
                item = state.global_items[name]

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
                    item.template = None
                    item.template_variants.clear()
                    print("  + Alle Vorlagen entfernt!")
                elif template_input.lower() == "capture":
                    _capture_template_for_item(state, item)
                else:
                    _assign_template_to_item(item, template_input, templates)
            else:
                print("  -> Ungültiges Item!")
    except ValueError:
        print("  -> Format: template <Nr>")


def _capture_template_for_item(state: AutoClickerState, item) -> None:
    """Capture-Variante: Screenshot von Slot oder freier Region als Template speichern."""
    with state.lock:
        slot_list = list(state.global_slots.values())

    region = None
    if slot_list:
        print("\n  Screenshot von:")
        print("    0. Freie Region wählen")
        for i, slot in enumerate(slot_list):
            print(f"    {i+1}. {slot.name}")
        try:
            slot_choice = safe_input("  Auswahl: ").strip()
            if slot_choice == "0":
                region = select_region()
            else:
                slot_idx = int(slot_choice) - 1
                if 0 <= slot_idx < len(slot_list):
                    region = slot_list[slot_idx].scan_region
                else:
                    print("  -> Ungültiger Slot!")
                    return
        except ValueError:
            region = select_region()
    else:
        region = select_region()

    if not region:
        return

    img = take_screenshot(region)
    if img is None:
        print("  -> Screenshot fehlgeschlagen!")
        return

    from ...imaging import template_size
    passende = [name for name in item.template_names()
                if template_size(name, active_templates_dir(state)) == tuple(img.size)]
    safe_name = sanitize_filename(item.name)
    if passende:
        # Dieselbe Slot-Groesse wird bewusst aktualisiert.
        template_file = passende[0]
    elif item.template_names():
        breite, hoehe = img.size
        basis = f"{safe_name}_{breite}x{hoehe}"
        template_file = f"{basis}.png"
        nummer = 2
        while (active_templates_dir(state) / template_file).exists():
            template_file = f"{basis}_{nummer}.png"
            nummer += 1
    else:
        template_file = f"{safe_name}.png"
    template_path = active_templates_dir(state) / template_file
    template_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(template_path)
    if not item.template:
        item.template = template_file
    elif template_file != item.template and template_file not in item.template_variants:
        item.template_variants.append(template_file)

    conf_input = safe_input(f"  Min. Konfidenz (Enter={item.min_confidence:.0%}): ").strip()
    if conf_input:
        try:
            conf = float(conf_input.replace("%", "")) / 100
            item.min_confidence = max(0.1, min(1.0, conf))
        except ValueError:
            pass

    print(f"  + Vorlage für {img.size[0]}x{img.size[1]} gespeichert: {template_file}")


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

    conf_input = safe_input(f"  Min. Konfidenz (aktuell {item.min_confidence:.0%}, Enter=behalten): ").strip()
    if conf_input:
        try:
            conf = float(conf_input.replace("%", "")) / 100
            item.min_confidence = max(0.1, min(1.0, conf))
        except ValueError:
            pass

    print(f"  + Template gesetzt: {item.template} (>={item.min_confidence:.0%})")
