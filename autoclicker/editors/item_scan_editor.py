"""
Item-Scan-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Item-Scan-Konfigurationen.
"""

import time
from typing import Optional

from ..models import ItemProfile, ItemScanConfig, AutoClickerState
from ..config import CONFIG
from ..utils import safe_input, sanitize_filename, naechster_freier_name, is_cancel, confirm, interactive_select, col, ok, err, warn, info, header, breadcrumb, suggest_command, cancel_hint, hint
from ..imaging import (
    PILLOW_AVAILABLE, OPENCV_AVAILABLE, take_screenshot,
)
from ..persistence import (
    save_item_scan, list_available_item_scans, load_item_scan_file,
    bind_item_scan_context,
    list_slot_presets, load_slot_preset, list_item_presets, load_item_preset,
    save_global_items, active_templates_dir
)
from ._item_felder import frage_bestaetigungsklick, frage_prioritaet
from .slot_editor import run_global_slot_editor
from .item_editor import run_global_item_editor, select_category
from .boss_scan_editor import run_boss_scan_editor
from .icon_scan_editor import run_icon_scan_editor



# =============================================================================
# GETEILTE BAUSTEINE DES ASSISTENTEN
# =============================================================================
# Schritt 1 (Slots) und Schritt 2 (Items) hatten dieselbe Auswahl-Schleife zweimal
# ausgeschrieben: <Nr>, <Von>-<Bis>, all, clear, show, done, cancel. Zwei Kopien sind
# zwei Verhaltensweisen — eine Korrektur an der einen ging an der anderen vorbei.

def bereich_parsen(eingabe: str, anzahl: int) -> Optional[tuple[int, int]]:
    """'1-5' → (1, 5), aufsteigend normalisiert.

    None, wenn es kein Bereich ist oder eine Grenze ausserhalb 1..anzahl liegt.
    '5-1' ergibt (1, 5) — wer rueckwaerts tippt, meint dasselbe.
    """
    if "-" not in eingabe:
        return None
    teile = eingabe.split("-")
    if len(teile) != 2:
        return None
    try:
        von, bis = int(teile[0]), int(teile[1])
    except ValueError:
        return None
    if not (1 <= von <= anzahl and 1 <= bis <= anzahl):
        return None
    return (min(von, bis), max(von, bis))


def mehrfach_auswahl(prompt: str, eintraege: list, gewaehlt: list,
                     zeile, extra_praefix: str = "", extra_fn=None,
                     leer_fehler: str = "") -> Optional[list]:
    """Mehrfachauswahl aus einer nummerierten Liste. None = Abbruch.

    `eintraege` ist die Namensliste (wird von `extra_fn` ggf. erweitert), `gewaehlt`
    die Vorauswahl. `zeile(index, name, markiert)` liefert die Anzeigezeile.

    `extra_praefix`/`extra_fn` haengen einen zusaetzlichen Befehl an (im Item-Schritt
    'new <Slot-Nr>'): `extra_fn(eingabe)` gibt den Namen des neu angelegten Eintrags
    zurueck oder None. Der wird angehaengt UND ausgewaehlt.

    `leer_fehler` erzwingt mindestens einen Eintrag bei 'done'.
    """
    gewaehlt = list(gewaehlt)
    befehle = ["done", "cancel", "all", "clear", "show"]
    if extra_praefix:
        befehle.append(extra_praefix)

    def _zeige():
        print(f"\n{len(gewaehlt)}/{len(eintraege)} ausgewählt:")
        if not eintraege:
            print("  (nichts vorhanden)")
        for i, name in enumerate(eintraege):
            print(zeile(i, name, name in gewaehlt))

    while True:
        try:
            roh = safe_input(prompt).strip()
            inp = roh.lower()

            if inp in ("done", "d"):
                if leer_fehler and not gewaehlt:
                    print("  " + err(leer_fehler) + " "
                          + hint("('<Nr>' = wählen, 'cancel' = Editor verlassen)"))
                    continue
                return gewaehlt
            if is_cancel(inp):
                return None
            if inp == "all":
                gewaehlt = list(eintraege)
                print(f"  + Alle {len(eintraege)} ausgewählt")
                continue
            if inp == "clear":
                gewaehlt = []
                print("  + Auswahl gelöscht")
                continue
            if inp in ("show", "s"):
                _zeige()
                continue
            if extra_praefix and inp.startswith(extra_praefix):
                neuer = extra_fn(roh)
                if neuer:
                    if neuer not in eintraege:
                        eintraege.append(neuer)
                    if neuer not in gewaehlt:
                        gewaehlt.append(neuer)
                continue

            # Bereich vor Einzelzahl: '1-5' wuerde sonst als Zahl scheitern
            bereich = bereich_parsen(inp, len(eintraege))
            if bereich:
                von, bis = bereich
                for nr in range(von, bis + 1):
                    name = eintraege[nr - 1]
                    if name not in gewaehlt:
                        gewaehlt.append(name)
                print(f"  + {von}-{bis} hinzugefügt")
                continue
            if "-" in inp and not (extra_praefix and inp.startswith(extra_praefix)):
                print(f"  -> Format: <Von>-<Bis> (z.B. 1-5), gültig 1-{len(eintraege)}")
                continue

            try:
                nr = int(inp)
            except ValueError:
                print(f"  -> Unbekannter Befehl.{suggest_command(inp, befehle)}")
                continue
            if not (1 <= nr <= len(eintraege)):
                print(f"  -> Ungültig! 1-{len(eintraege)}")
                continue
            name = eintraege[nr - 1]
            if name in gewaehlt:
                gewaehlt.remove(name)
                print(f"  - {name} entfernt")
            else:
                gewaehlt.append(name)
                print(f"  + {name} hinzugefügt")
        except (KeyboardInterrupt, EOFError):
            return None


def run_item_scan_menu(state: AutoClickerState) -> None:
    """Hauptmenü für Item-Scan Konfiguration (Slots, Items, Scans)."""
    print(header("ITEM-SCAN MENÜ"))
    print(f"  {breadcrumb('Hauptmenü', 'Item-Scan')}")

    with state.lock:
        slot_count = len(state.global_slots)
        item_count = len(state.global_items)
        scan_count = len(state.item_scans)
        boss_count = len(state.boss_scans)
        icon_count = len(state.icon_scans)
        aktiver_scan = state.active_item_scan or "keiner"

    menu_options = [
        f"Item-Scan wählen     ({aktiver_scan})",
        f"Slots bearbeiten     ({slot_count} vorhanden)",
        f"Items bearbeiten     ({item_count} vorhanden)",
        f"Scans bearbeiten     ({scan_count} vorhanden)",
        f"Boss-Scans bearbeiten ({boss_count} vorhanden)",
        f"Icon-Scans bearbeiten ({icon_count} vorhanden)",
        "Auto-Scan (Slots scannen + Items + Scan in einem Schritt)",
        "Import / Export (Setup teilen oder importieren)",
    ]

    choice = interactive_select(menu_options)

    if choice == 0:
        run_item_scan_editor(state)
    elif choice in (1, 2, 6) and not state.active_item_scan:
        print(f"\n{info('Zuerst einen Item-Scan wählen oder erstellen.')}" )
        run_item_scan_editor(state)
    elif choice == 1:
        run_global_slot_editor(state)
    elif choice == 2:
        run_global_item_editor(state)
    elif choice == 3:
        run_item_scan_editor(state)
    elif choice == 4:
        run_boss_scan_editor(state)
    elif choice == 5:
        run_icon_scan_editor(state)
    elif choice == 6:
        run_auto_scan_workflow(state)
    elif choice == 7:
        from .import_export_editor import run_import_export_editor
        run_import_export_editor(state)


def run_item_scan_editor(state: AutoClickerState) -> None:
    """Interaktiver Editor für Item-Scan Konfigurationen (verknüpft Slots + Items)."""
    print(header("SCAN-EDITOR (Slots + Items verknüpfen)"))
    print(f"  {breadcrumb('Hauptmenü', 'Item-Scan', 'Scans')}")

    if not PILLOW_AVAILABLE:
        print(f"\n{err('Pillow nicht installiert!')}")
        print("         Installieren mit: pip install pillow")
        return

    # Bestehende Item-Scans einmal laden und cachen
    with state.lock:
        owner = state.active_sequence.name if state.active_sequence else ""
    available_scans = list_available_item_scans(owner)
    loaded_scans = []
    menu_options = ["Neuen Item-Scan erstellen"]
    for name, path in available_scans:
        config = load_item_scan_file(path, owner)
        if config:
            loaded_scans.append(config)
            menu_options.append(str(config))
        else:
            print(warn(f"Item-Scan '{name}' ({path.name}) konnte nicht geladen werden — fehlt im Menü!"))

    if available_scans:
        print("  (Tipp: 'del <Nr>' im Textmodus zum Löschen)")

    choice = interactive_select(menu_options, title="\nWas möchtest du tun?")

    if choice == -1:
        print(f"{col('[ABBRUCH]', 'yellow')} Editor beendet.")
        return
    elif choice == 0:
        scan_name = safe_input("Name des neuen Item-Scans: ").strip()
        if is_cancel(scan_name):
            print(f"{col('[ABBRUCH]', 'yellow')} Kein Scan erstellt.")
            return
        if not scan_name:
            scan_name = f"Scan_{int(time.time())}"
        config = ItemScanConfig(
            name=scan_name,
            owner_sequence=owner,
        )
        with state.lock:
            state.item_scans[scan_name] = config
        bind_item_scan_context(state, scan_name)
        save_item_scan(config)
        print(f"\n{ok(f'Item-Scan {scan_name!r} angelegt.')} ")
        print("         Lege jetzt seine Slots und danach seine Items an.")
        run_global_slot_editor(state)
    elif 1 <= choice < len(menu_options):
        config = loaded_scans[choice - 1]
        with state.lock:
            state.item_scans[config.name] = config
        bind_item_scan_context(state, config.name)
        edit_item_scan(state, config)


def _schritt_presets(state: AutoClickerState) -> bool:
    """Schritt 0: Slot-/Item-Preset laden. False = abgebrochen.

    Laeuft nur, wenn es ueberhaupt Presets gibt — sonst gibt es nichts zu waehlen.
    """
    slot_presets = list_slot_presets()
    item_presets = list_item_presets()
    if not (slot_presets or item_presets):
        return True

    print(header("PRESETS AUSWÄHLEN"))
    with state.lock:
        cur_slots = len(state.global_slots)
        cur_items = len(state.global_items)

    for presets, titel, aktuell, laden in (
        (slot_presets, "Slot-Presets", cur_slots, load_slot_preset),
        (item_presets, "Item-Presets", cur_items, load_item_preset),
    ):
        if not presets:
            continue
        art = titel.split("-")[0]
        print(f"\n{titel}:")
        for i, (name, _pfad, anzahl) in enumerate(presets):
            print(f"  [{i+1}] {name} ({anzahl} {art}s)")
        print(f"  [0] Aktuelle {art}s verwenden ({aktuell} geladen)")

        while True:
            try:
                wahl = safe_input(f"\n{art}-Preset wählen (Enter=0, 'cancel'): ").strip()
                if is_cancel(wahl):
                    print("  -> Abgebrochen")
                    return False
                if not wahl or wahl == "0":
                    break
                nr = int(wahl)
                if 1 <= nr <= len(presets):
                    laden(state, presets[nr - 1][0])
                    break
                print(f"  -> Ungültig! 0-{len(presets)}")
            except ValueError:
                print("  -> Bitte eine Nummer eingeben!")
            except (KeyboardInterrupt, EOFError):
                return False
    return True


def _neues_item_per_template(state: AutoClickerState, eingabe: str,
                             slot_list: list, available_slots: dict,
                             available_items: dict) -> Optional[str]:
    """Legt ein Item aus einem Slot-Screenshot an. Gibt den Namen zurück, oder None.

    Der 'new'-Zweig des Item-Schritts — mit Abstand der laengste, und der einzige,
    der etwas anlegt statt nur auszuwaehlen.
    """
    if not OPENCV_AVAILABLE:
        print("  -> OpenCV nicht installiert! (pip install opencv-python)")
        return None

    slot_num = None
    if eingabe.lower().startswith("new "):
        try:
            slot_num = int(eingabe[4:])
        except ValueError:
            pass
    if slot_num is None:
        print(f"\n  Von welchem Slot Screenshot machen? (1-{len(slot_list)})")
        try:
            slot_num = int(safe_input("  Slot-Nr: ").strip())
        except ValueError:
            print("  -> Ungültige Eingabe!")
            return None
    if slot_num < 1 or slot_num > len(slot_list):
        print(f"  -> Ungültiger Slot! Verfügbar: 1-{len(slot_list)}")
        return None

    slot_name = slot_list[slot_num - 1]
    slot = available_slots[slot_name]
    print(f"\n  Mache Screenshot von {slot_name}...")
    template_img = take_screenshot(slot.scan_region)
    if not template_img:
        print("  -> Screenshot fehlgeschlagen!")
        return None

    item_name = safe_input("  Item-Name: ").strip()
    if not item_name:
        item_name = naechster_freier_name("Item", available_items)
    if item_name in available_items:
        if not confirm(f"  '{item_name}' existiert bereits. Überschreiben?"):
            print("  -> Abgebrochen")
            return None
        print(f"  -> '{item_name}' wird überschrieben")

    safe_name = sanitize_filename(item_name)
    template_file = f"{safe_name}.png"
    template_path = active_templates_dir(state) / template_file
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_img.save(template_path)

    category = select_category(state)      # zuerst: die Prioritaets-Verschiebung braucht sie

    priority = frage_prioritaet(state, category)

    min_confidence = state.config.scan_min_confidence
    try:
        conf_input = safe_input(
            f"  Min. Konfidenz % (Enter={int(min_confidence * 100)}): ").strip()
        if conf_input:
            min_confidence = max(0.1, min(1.0, float(conf_input) / 100))
    except ValueError:
        print(f"  -> '{conf_input}' ungültig — behalte {int(min_confidence * 100)}")

    confirm_point_id, confirm_delay = frage_bestaetigungsklick(
        state, CONFIG.scan_confirm_delay,
        frage="  Bestätigungs-Punkt-ID (Enter = keiner): ")

    new_item = ItemProfile(
        name=item_name, marker_colors=[], category=category, priority=priority,
        confirm_point_id=confirm_point_id, confirm_delay=confirm_delay,
        template=template_file, min_confidence=min_confidence,
    )
    with state.lock:
        state.global_items[item_name] = new_item
    save_global_items(state)
    available_items[item_name] = new_item

    cat_str = f" [{category}]" if category else ""
    print(f"  + Item '{item_name}'{cat_str} erstellt mit Template "
          f"'{template_file}' ({min_confidence:.0%})")
    print("  + Automatisch zum Scan hinzugefügt")
    return item_name


def _schritt_toleranz(tolerance: int) -> int:
    """Schritt 3: Farbtoleranz. Fehleingabe behaelt den alten Wert."""
    print(header("SCHRITT 3: FARBTOLERANZ"))
    print(f"\nAktuelle Toleranz: {tolerance}")
    print("(Höher = mehr Farben werden als 'gleich' erkannt)")
    tol_input = ""
    try:
        tol_input = safe_input(f"Neue Toleranz (Enter = {tolerance}): ").strip()
        if tol_input:
            tolerance = max(1, min(100, int(tol_input)))
    except ValueError:
        print(f"  -> '{tol_input}' ungültig — behalte {tolerance}")
    return tolerance


def _schritt_auto_lernen(learn_unknown: bool) -> bool:
    """Schritt 4: Auto-Lernen unbekannter Slot-Inhalte (opt-in)."""
    print(header("SCHRITT 4: AUTO-LERNEN (optional)"))
    print("\n  Lernt beim Scannen unbekannte Slot-Inhalte automatisch als neue")
    print("  globale Items (Kategorie 'Auto'). Diese werden NICHT geklickt —")
    print("  Aktion/Kategorie ordnest du später im Item-Editor zu.")
    print(f"  Aktuell: {'AN' if learn_unknown else 'AUS'}")
    learn_unknown = confirm("  Unbekannte Items automatisch lernen?", default=learn_unknown)
    if learn_unknown:
        print("\n  " + hint("Gelernte Items heissen erst 'Auto <Slot>'. Sinnvolle Namen per LLM"))
        print("  " + hint("vergibst du danach im Item-Editor mit 'autoname' — das läuft"))
        print("  " + hint("NICHT während des Scans (würde ihn ausbremsen)."))
    return learn_unknown


def _schritt_richtung(reverse: bool) -> bool:
    """Schritt 5: In welcher Richtung die Slots abgearbeitet werden."""
    print(header("SCHRITT 5: REIHENFOLGE (optional)"))
    print("\n  Rückwärts heisst von hinten nach vorn (4, 3, 2, 1). Sinnvoll,")
    print("  wenn das Spiel den Bestand nach vorn aufrückt: dann verschiebt ein")
    print("  Klick nicht die noch nicht besuchten Slots.")
    print(f"  Aktuell: {'rückwärts' if reverse else 'vorwärts'}")
    return confirm("  Slots rückwärts abarbeiten?", default=reverse)


def _schritt_katalog(use_catalog: bool, state: AutoClickerState) -> bool:
    """Schritt 6: Ob dieser Scan den Item-Katalog benutzt.

    Der Schalter gehoert zum Scan und nicht in die Config: wer zwei Spiele
    betreibt, hat einen Katalog, der nur fuer eines von beiden gilt — dieselbe
    Ueberlegung wie bei der Laufrichtung.
    """
    print(header("SCHRITT 6: ITEM-KATALOG (optional)"))
    pfad = state.config.scan_catalog_file
    print("\n  Mit Katalog kennt der Editor die echten Item-Namen des Spiels:")
    print("  Kategorie und Priorität lassen sich daraus setzen, und die")
    print("  LLM-Benennung wählt aus den echten Namen statt frei zu raten.")
    if not pfad:
        print("  " + warn("Noch keine Katalog-Datei eingetragen."))
        print("  " + hint("Anlegen mit: python tools/katalog.py"))
        print("  " + hint("Eintragen unter scan_catalog_file (Studio: Einstellungen)."))
    else:
        print(f"  Katalog: {pfad}")
    print(f"  Aktuell: {'an' if use_catalog else 'aus'}")
    return confirm("  Katalog für diesen Scan benutzen?", default=use_catalog)


def edit_item_scan(state: AutoClickerState, existing: Optional[ItemScanConfig]) -> None:
    """Bearbeitet eine Item-Scan-Konfiguration (verknüpft globale Slots + Items).

    Ein Assistent in sechs Stufen. Jede Stufe steckt in einer eigenen Funktion und gibt
    ihr Ergebnis zurück oder signalisiert Abbruch — vorher waren es 450 Zeilen am Stück,
    und die Auswahl-Schleife stand zweimal darin.
    """
    if not _schritt_presets(state):
        return

    with state.lock:
        available_slots = dict(state.global_slots)
        available_items = dict(state.global_items)

    if not available_slots:
        print(f"\n{err('Keine Slots im gewählten Preset!')}")
        print("         Erstelle zuerst Slots im Slot-Editor (Option 1)")
        return
    if not available_items:
        print(f"\n{info('Keine Items im gewählten Preset.')}")
        print("       Du kannst sie gleich per Template erstellen!")

    if existing:
        print(f"\n--- Bearbeite Scan: {existing.name} ---")
        scan_name = existing.name
        # Namen, nicht Objekte: load_item_scan_file() liefert nur die Namen, die
        # Objekte werden erst von resolve_scan_references() aufgeloest.
        selected_slot_names = [slot.name for slot in existing.slots if slot.enabled]
        selected_item_names = list(existing.item_names)
        tolerance = existing.color_tolerance
        learn_unknown = existing.learn_unknown
        reverse = existing.reverse
        use_catalog = existing.use_catalog
        capture_window_title = existing.capture_window_title
        capture_window_index = existing.capture_window_index
        capture_window_rect = existing.capture_window_rect
    else:
        print("\n--- Neuen Scan erstellen ---")
        scan_name = safe_input("Name des Scans: ").strip()
        if not scan_name:
            scan_name = f"Scan_{int(time.time())}"
        selected_slot_names = []
        selected_item_names = []
        tolerance = ItemScanConfig.color_tolerance
        learn_unknown = False
        reverse = False
        use_catalog = False
        capture_window_title = None
        capture_window_index = 0
        capture_window_rect = None

    # --- Schritt 1: Slots ---------------------------------------------------------
    print(header("SCHRITT 1: SLOTS AUSWÄHLEN"))
    slot_list = list(available_slots.keys())
    print("\nVerfügbare Slots:")
    for i, name in enumerate(slot_list):
        markiert = "X" if name in selected_slot_names else " "
        print(f"  [{markiert}] {i+1}. {available_slots[name]}")
    print(f"\nBefehle: '<Nr>', '<Von>-<Bis>' (z.B. 1-5), 'all', 'clear', "
          f"'show / s', 'done / d', 'cancel / {cancel_hint()}")

    gewaehlt = mehrfach_auswahl(
        "[Slots] > ", slot_list, selected_slot_names,
        lambda i, name, an: f"  [{'X' if an else ' '}] {i+1}. {available_slots[name]}",
        leer_fehler="Mindestens 1 Slot erforderlich!")
    if gewaehlt is None:
        return
    selected_slot_names = gewaehlt

    # --- Schritt 2: Items ---------------------------------------------------------
    print(header("SCHRITT 2: ITEMS AUSWÄHLEN / ERSTELLEN"))
    templates_dir = active_templates_dir(state)
    templates = list(templates_dir.glob("*.png")) if templates_dir.exists() else []
    if templates:
        print(f"\nVerfügbare Templates ({len(templates)}):")
        for t in sorted(templates)[:10]:
            print(f"    {t.name}")
        if len(templates) > 10:
            print(f"    ... und {len(templates) - 10} weitere")

    with state.lock:
        available_items = dict(state.global_items)
    item_list = list(available_items.keys())

    print("\nVerfügbare Items:")
    if item_list:
        for i, name in enumerate(item_list):
            markiert = "X" if name in selected_item_names else " "
            print(f"  [{markiert}] {i+1}. {available_items[name]}")
    else:
        print("  (Keine Items - erstelle welche mit 'new')")

    print("\n" + "-" * 40)
    print("Befehle:")
    print("  <Nr>              - Item auswählen/abwählen")
    print("  <Von>-<Bis>       - Bereich auswählen (z.B. 1-5)")
    print("  all | clear       - Alle auswählen / Auswahl löschen")
    print("  new <Slot-Nr>     - Neues Item per Template von Slot erstellen")
    print(f"  show / s | done / d | cancel / {cancel_hint()}")
    print("-" * 40)

    gewaehlt = mehrfach_auswahl(
        "[Items] > ", item_list, selected_item_names,
        lambda i, name, an: f"  [{'X' if an else ' '}] {i+1}. {available_items[name]}",
        extra_praefix="new",
        extra_fn=lambda roh: _neues_item_per_template(
            state, roh, slot_list, available_slots, available_items))
    if gewaehlt is None:
        return
    selected_item_names = gewaehlt

    if not selected_item_names:
        print(f"\n{info('Keine Items ausgewählt.')}")
        if not confirm("Trotzdem speichern?"):
            print(f"{col('[ABBRUCH]', 'yellow')} Scan nicht gespeichert.")
            return

    # --- Schritt 3 + 4 ------------------------------------------------------------
    tolerance = _schritt_toleranz(tolerance)
    learn_unknown = _schritt_auto_lernen(learn_unknown)
    reverse = _schritt_richtung(reverse)
    use_catalog = _schritt_katalog(use_catalog, state)

    # --- Speichern ----------------------------------------------------------------
    with state.lock:
        # Alle Slot-Geometrien bleiben Eigentum dieses Scans. Die Auswahl
        # schaltet sie für den Lauf ein oder aus, statt die abgewählten samt
        # Fläche und ID aus der Datei zu löschen.
        slots = list(state.global_slots.values())
        aktiv = set(selected_slot_names)
        for slot in slots:
            slot.enabled = slot.name in aktiv
        items = [state.global_items[n] for n in selected_item_names if n in state.global_items]

    # **Jedes Feld muss hier stehen.** Der Editor baut die Config NEU auf,
    # statt die vorhandene zu ändern — ein vergessenes Feld ist beim Bearbeiten
    # eines bestehenden Scans still weg. Ein Test hält die Liste gegen die
    # Dataclass.
    config = ItemScanConfig(
        name=scan_name, slots=slots, items=items,
        color_tolerance=tolerance, learn_unknown=learn_unknown,
        reverse=reverse,
        use_catalog=use_catalog,
        capture_window_title=capture_window_title,
        capture_window_index=capture_window_index,
        capture_window_rect=capture_window_rect,
        owner_sequence=(state.active_sequence.name if state.active_sequence else ""),
    )
    with state.lock:
        state.item_scans[scan_name] = config
        state.active_item_scan = scan_name
        state.global_slots = {slot.name: slot for slot in slots}
        state.global_items = {item.name: item for item in items}
    save_item_scan(config)

    print(f"\n{ok(f'Scan {scan_name!r} gespeichert!')}")
    print(f"         {sum(slot.enabled for slot in slots)}/{len(slots)} Slots aktiv, "
          f"{len(items)} Items")
    print(f"         Nutze im Sequenz-Editor: 'scan {scan_name}'")


def run_auto_scan_workflow(state: AutoClickerState) -> None:
    """Kompletter Auto-Scan Workflow: Alle Slots scannen, Items erstellen, Scan-Config speichern."""
    print(header("AUTO-SCAN WORKFLOW"))
    print(f"  {breadcrumb('Hauptmenü', 'Item-Scan', 'Auto-Scan')}")
    print("\n  Scannt automatisch alle Slots, erstellt Items und eine Scan-Konfiguration.")

    if not PILLOW_AVAILABLE:
        print(f"\n{err('Pillow nicht installiert!')}")
        return

    if not OPENCV_AVAILABLE:
        print(f"\n{err('OpenCV nicht installiert!')} (pip install opencv-python)")
        return

    with state.lock:
        slot_count = len(state.global_slots)

    if slot_count == 0:
        print(f"\n{err('Keine Slots vorhanden!')}")
        print("         Erstelle zuerst Slots mit dem Slot-Editor (Option 1, dann 'auto')")
        return

    # Items automatisch erstellen via item_editor
    from .item_editor import item_autoscan_command
    item_autoscan_command(state, "autoscan")

    # Prüfen ob Items erstellt wurden
    with state.lock:
        item_count = len(state.global_items)

    if item_count == 0:
        print(f"\n{err('Keine Items erstellt - Scan-Konfiguration wird nicht erstellt.')}")
        return

    # Scan-Config erstellen
    print(header("SCAN-KONFIGURATION ERSTELLEN"))

    scan_name = safe_input("\nName für den Scan (Enter = 'AutoScan'): ").strip()
    if is_cancel(scan_name):
        print("  -> Scan-Config wird nicht erstellt (Items bleiben erhalten)")
        return
    if not scan_name:
        scan_name = "AutoScan"

    # Toleranz
    tolerance = ItemScanConfig.color_tolerance
    try:
        tol_input = safe_input(f"Farbtoleranz (Enter = {tolerance}): ").strip()
        if tol_input:
            tolerance = max(1, min(100, int(tol_input)))
    except ValueError:
        pass

    # Alle Slots und Items verwenden
    with state.lock:
        slots = list(state.global_slots.values())
        items = list(state.global_items.values())

    config = ItemScanConfig(
        name=scan_name,
        slots=slots,
        items=items,
        color_tolerance=tolerance,
        owner_sequence=(state.active_sequence.name if state.active_sequence else ""),
    )

    with state.lock:
        state.item_scans[scan_name] = config

    save_item_scan(config)

    print(f"\n{ok(f'Auto-Scan komplett!')}")
    print(f"         Scan '{scan_name}': {len(slots)} Slots, {len(items)} Items")
    print(f"         Nutze im Sequenz-Editor: 'scan {scan_name}'")
