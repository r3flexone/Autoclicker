"""
Slot-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Slot-Definitionen für Item-Scans.
"""

import copy
import time
from pathlib import Path
from typing import Optional

from ..models import ItemSlot, AutoClickerState
from ..config import CONFIG
from ..utils import safe_input, sanitize_filename, naechster_freier_name, is_cancel, confirm, interactive_select, col, ok, err, warn, info, hint, header, breadcrumb, suggest_command, coord_context, cancel_hint
from ..winapi import get_cursor_pos
from ..imaging import (
    PILLOW_AVAILABLE, OPENCV_AVAILABLE, NUMPY_AVAILABLE,
    take_screenshot, get_pixel_color, select_region, get_color_name
)
from ..persistence import (
    save_global_slots, list_slot_presets, save_slot_preset,
    load_slot_preset, delete_slot_preset, SCREENSHOTS_DIR
)



def run_global_slot_editor(state: AutoClickerState) -> None:
    """Interaktiver Editor für globale Slot-Definitionen."""
    print(header("SLOT-EDITOR (Globale Slot-Definitionen)"))
    print(f"  {breadcrumb('Hauptmenü', 'Item-Scan', 'Slots')}")

    if not PILLOW_AVAILABLE:
        print(f"\n{err('Pillow nicht installiert!')}")
        print("         Installieren mit: pip install pillow")
        return

    # Transaktional wie der Item-Editor: Snapshot am Start, Änderungen passieren
    # in-memory, gespeichert wird erst bei 'done' — 'cancel' stellt den
    # Originalzustand wieder her (inkl. zwischenzeitlichem Preset-Laden).
    with state.lock:
        slots_backup = copy.deepcopy(state.global_slots)

    # Aktuelle Slots anzeigen
    with state.lock:
        current_slots = list(state.global_slots.items())

    if current_slots:
        print(f"\nAktuelle Slots ({len(current_slots)}):")
        for i, (name, slot) in enumerate(current_slots):
            print(f"  {i+1}. {slot}")
    else:
        print("\n  (Keine Slots vorhanden)")

    # Presets anzeigen
    presets = list_slot_presets()
    if presets:
        print(f"\nVerfügbare Presets ({len(presets)}):")
        for name, path, count in presets:
            print(f"  - {name} ({count} Slots)")

    def _print_slot_help():
        print("\n" + "-" * 60)
        print("Befehle:")
        print("  auto           - AUTOMATISCHE Slot-Erkennung (fragt: Items gleich mitlernen?)")
        print("  repair         - Slots NEU VERMESSEN (Namen bleiben, nur Koordinaten neu)")
        print("  add            - Neuen Slot hinzufügen")
        print("  edit <Nr>      - Slot bearbeiten")
        print("  del <Nr>       - Slot löschen")
        print("  del all        - ALLE Slots löschen")
        print("  show / s       - Alle Slots anzeigen")
        print("  save <Name>    - Als Preset speichern")
        print("  load <Name>    - Preset laden")
        print("  preset del <N> - Preset löschen")
        print(f"  help / ? | done / d | cancel / {cancel_hint()}")
        print("-" * 60)

    _print_slot_help()

    while True:
        try:
            with state.lock:
                slot_count = len(state.global_slots)
            prompt = f"[SLOTS: {slot_count}]"
            user_input = safe_input(f"{prompt} > ").strip()
            cmd = user_input.lower()

            if cmd in ("done", "d"):
                save_global_slots(state)
                print(ok("Slot-Editor beendet."))
                return
            elif is_cancel(cmd):
                with state.lock:
                    state.global_slots = slots_backup
                save_global_slots(state)
                print(col("[ABBRUCH]", "yellow") + " Änderungen verworfen.")
                return
            elif cmd == "":
                continue
            elif cmd in ("help", "?"):
                _print_slot_help()
                continue
            elif cmd in ("show", "s"):
                with state.lock:
                    if state.global_slots:
                        print(f"\nSlots ({len(state.global_slots)}):")
                        for i, (name, slot) in enumerate(state.global_slots.items()):
                            print(f"  {i+1}. {slot}")
                    else:
                        print("  (Keine Slots)")
                continue

            elif cmd == "auto":
                slot_auto_detect(state)  # gespeichert wird bei 'done'
                continue

            elif cmd in ("repair", "reparieren", "fix"):
                # Anders als 'auto' schreibt die Reparatur sofort — und sie fasst
                # optional Punkte und Sequenzdateien mit an, die 'cancel' gar nicht
                # zuruecknehmen koennte. Damit 'cancel' nicht die halbe Aenderung
                # rueckgaengig macht, wird der Snapshot nachgezogen.
                if slot_repair(state):
                    with state.lock:
                        slots_backup = copy.deepcopy(state.global_slots)
                    print(f"  {hint('Bereits gespeichert — cancel nimmt das nicht zurueck.')}")
                continue

            elif cmd == "add":
                slot = create_slot(state)
                if slot:
                    with state.lock:
                        state.global_slots[slot.name] = slot
                    print(f"  + Slot '{slot.name}' hinzugefügt")
                continue

            elif cmd.startswith("edit "):
                try:
                    edit_num = int(cmd[5:])
                except ValueError:
                    print("  -> Format: edit <Nr>")
                    continue
                # Unter Lock nur Slot/Namen auflösen — edit_slot blockiert auf
                # Input und läuft daher AUSSERHALB des Locks.
                with state.lock:
                    slot_list = list(state.global_slots.items())
                    valid = 1 <= edit_num <= len(slot_list)
                    if valid:
                        name, slot = slot_list[edit_num - 1]
                if not valid:
                    print(f"  -> Ungültig! Verfügbar: 1-{len(slot_list)}")
                    continue
                new_slot = edit_slot(state, slot)
                if new_slot:
                    with state.lock:
                        # Falls Name geändert wurde
                        if new_slot.name != name:
                            del state.global_slots[name]
                        state.global_slots[new_slot.name] = new_slot
                    print(f"  + Slot '{new_slot.name}' aktualisiert")
                continue

            elif cmd == "del all":
                with state.lock:
                    if not state.global_slots:
                        print("  -> Keine Slots vorhanden!")
                        continue
                    count = len(state.global_slots)
                if confirm(f"  {count} Slot(s) wirklich löschen?"):
                    with state.lock:
                        state.global_slots.clear()
                    print(f"  + {count} Slot(s) gelöscht!")
                else:
                    print("  -> Abgebrochen")
                continue

            elif cmd.startswith("del "):
                try:
                    del_num = int(cmd[4:])
                except ValueError:
                    print("  -> Format: del <Nr>")
                    continue
                with state.lock:
                    slot_list = list(state.global_slots.keys())
                    valid = 1 <= del_num <= len(slot_list)
                    if valid:
                        name = slot_list[del_num - 1]
                        del state.global_slots[name]
                if not valid:
                    print(f"  -> Ungültig! Verfügbar: 1-{len(slot_list)}")
                    continue
                print(f"  + Slot '{name}' gelöscht")
                continue

            elif cmd.startswith("save "):
                preset_name = user_input[5:].strip()
                if preset_name:
                    save_slot_preset(state, preset_name)
                else:
                    print("  -> Format: save <Name>")
                continue

            elif cmd.startswith("load "):
                preset_name = user_input[5:].strip()
                if preset_name:
                    load_slot_preset(state, preset_name)
                else:
                    print("  -> Format: load <Name>")
                continue

            elif cmd.startswith("preset del "):
                preset_name = user_input[11:].strip()
                if preset_name:
                    delete_slot_preset(preset_name)
                else:
                    print("  -> Format: preset del <Name>")
                continue

            else:
                _known = ["auto", "add", "edit", "del", "show", "save", "load", "preset", "help", "done", "cancel"]
                suggestion = suggest_command(cmd, _known)
                print(f"  -> Unbekannter Befehl.{suggestion} {hint('(? = Hilfe)')}")

        except (KeyboardInterrupt, EOFError):
            with state.lock:
                state.global_slots = slots_backup
            save_global_slots(state)
            print("\n" + col("[ABBRUCH]", "yellow") + " Änderungen verworfen.")
            return


def create_slot(state: AutoClickerState) -> Optional[ItemSlot]:
    """Erstellt einen neuen Slot interaktiv."""
    with state.lock:
        slot_num = len(state.global_slots) + 1

    slot_name = safe_input(f"  Slot-Name (Enter = 'Slot {slot_num}', 'cancel'): ").strip()
    if is_cancel(slot_name):
        print("  -> Slot-Erstellung abgebrochen")
        return None
    if not slot_name:
        slot_name = f"Slot {slot_num}"

    # Duplikat-Check (Slots sind per Name indexiert — sonst still überschrieben)
    with state.lock:
        name_exists = slot_name in state.global_slots
    if name_exists:
        if not confirm(f"  '{slot_name}' existiert bereits. Überschreiben?"):
            print("  -> Slot-Erstellung abgebrochen")
            return None

    # Scan-Region auswählen
    print("\n  Scan-Region definieren (Bereich wo das Item angezeigt wird):")
    print("  ('cancel' in Konsole = abbrechen)")
    region = select_region()
    if not region:
        print("  -> Slot-Erstellung abgebrochen")
        return None

    # Sofort Farben in dieser Region anzeigen
    print("\n  Analysiere Farben in diesem Bereich...")
    img = take_screenshot(region)
    if img:
        color_counts = {}
        pixels = img.load()
        width, height = img.size
        for x in range(width):
            for y in range(height):
                pixel = pixels[x, y][:3]
                rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
                color_counts[rounded] = color_counts.get(rounded, 0) + 1
        marker_count = CONFIG.scan_marker_count
        sorted_colors = sorted(color_counts.items(), key=lambda c: c[1], reverse=True)[:marker_count]
        print(f"  Top {marker_count} Farben in {slot_name}:")
        for i, (color, count) in enumerate(sorted_colors):
            color_name = get_color_name(color)
            print(f"    {i+1}. RGB{color} - {color_name} ({count} Pixel)")

    # Slot-Hintergrundfarbe (wird bei Items ausgeschlossen)
    slot_color = None
    print("\n  Hintergrundfarbe des leeren Slots markieren:")
    print("  (Diese Farbe wird bei Item-Erkennung ignoriert)")
    print("  Bewege Maus auf den Slot-Hintergrund, Enter (oder 'skip')...")
    bg_input = safe_input().strip().lower()
    if is_cancel(bg_input):
        print("  -> Slot-Erstellung abgebrochen")
        return None
    elif bg_input != "skip":
        x, y = get_cursor_pos()
        slot_color = get_pixel_color(x, y)
        if slot_color:
            color_name = get_color_name(slot_color)
            print(f"  -> Hintergrundfarbe: RGB{slot_color} ({color_name})")
        else:
            print("  -> Farbe konnte nicht gelesen werden, überspringe...")

    # Klickposition
    print("\n  Klickposition definieren (wo geklickt wird wenn Item gefunden):")
    print("  Bewege Maus zur Klickposition, Enter (oder 'center' für Mitte)...")
    click_input = safe_input().strip().lower()

    if click_input == "center":
        # Mitte der Region berechnen
        x1, y1, x2, y2 = region
        click_x = (x1 + x2) // 2
        click_y = (y1 + y2) // 2
    else:
        click_x, click_y = get_cursor_pos()

    print(f"  -> Klickposition: {coord_context(click_x, click_y)}")

    # Optional: Screenshot speichern
    if img:
        try:
            screenshots_dir = Path(SCREENSHOTS_DIR)
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            safe_name = sanitize_filename(slot_name)
            screenshot_path = screenshots_dir / f"{safe_name}.png"
            img.save(screenshot_path)
            print(f"  -> Screenshot gespeichert: {screenshot_path}")
        except Exception as e:
            print(f"  -> Screenshot speichern fehlgeschlagen: {e}")

    return ItemSlot(
        name=slot_name,
        scan_region=region,
        click_pos=(click_x, click_y),
        slot_color=slot_color
    )


def edit_slot(state: AutoClickerState, slot: ItemSlot) -> Optional[ItemSlot]:
    """Bearbeitet einen bestehenden Slot."""
    print(f"\n  Bearbeite Slot: {slot.name}")
    print(f"    Region: {slot.scan_region}")
    print(f"    Klickpos: {slot.click_pos}")
    if slot.slot_color:
        print(f"    Hintergrund: RGB{slot.slot_color}")

    new_name = slot.name
    new_region = slot.scan_region
    new_click = slot.click_pos
    new_color = slot.slot_color

    while True:
        edit_options = ["Name", "Scan-Region", "Klickposition", "Hintergrundfarbe", "Fertig"]
        choice = interactive_select(edit_options, title="\n  Was ändern?", allow_cancel=False)

        if choice == 4:  # Fertig
            break
        elif choice == 0:  # Name
            name_input = safe_input(f"  Neuer Name (Enter = '{new_name}'): ").strip()
            if name_input:
                new_name = name_input
                print(f"  -> Name geändert zu '{new_name}'")
        elif choice == 1:  # Scan-Region
            print("\n  Neue Scan-Region definieren...")
            region = select_region()
            if region:
                new_region = region
                print(f"  -> Region geändert zu {new_region}")
        elif choice == 2:  # Klickposition
            print("  Bewege Maus zur neuen Klickposition, Enter...")
            safe_input()
            new_click = get_cursor_pos()
            print(f"  -> Klickposition geändert zu {new_click}")
        elif choice == 3:  # Hintergrundfarbe
            print("  Bewege Maus zum Slot-Hintergrund, Enter...")
            safe_input()
            x, y = get_cursor_pos()
            color = get_pixel_color(x, y)
            if color:
                new_color = color
                print(f"  -> Hintergrundfarbe geändert zu RGB{new_color}")

    return ItemSlot(
        name=new_name,
        scan_region=new_region,
        click_pos=new_click,
        slot_color=new_color
    )


def erkenne_slots_im_bild(img, slot_color_rgb: tuple, hsv_toleranz: int,
                          verbose: bool = False):
    """Findet die Slot-Rechtecke in einem Bild anhand der Hintergrundfarbe.

    Gibt `(rechtecke, img_bgr)` zurück; die Rechtecke sind `(x, y, w, h)` relativ
    zum Bild, auf die Median-Größe normalisiert und zeilenweise sortiert.

    Die Normalisierung ist der Grund, warum die Erkennung für die Reparatur taugt:
    sie liefert für jeden Slot dieselbe Größe und Kantenlage, unabhängig davon, wie
    grob der Bereich markiert wurde. Eine Maus-Position kann das nicht.

    Getrennt von `slot_auto_detect`, damit die Reparatur exakt dieselbe Erkennung
    benutzt — zwei Kopien wären zwei Ergebnisse.
    """
    import numpy as np
    import cv2

    r, g, b = slot_color_rgb

    # RGB zu HSV
    r_n, g_n, b_n = r / 255, g / 255, b / 255
    max_c, min_c = max(r_n, g_n, b_n), min(r_n, g_n, b_n)
    diff = max_c - min_c

    if diff == 0:
        h = 0
    elif max_c == r_n:
        h = (60 * ((g_n - b_n) / diff) + 360) % 360
    elif max_c == g_n:
        h = (60 * ((b_n - r_n) / diff) + 120) % 360
    else:
        h = (60 * ((r_n - g_n) / diff) + 240) % 360

    s = 0 if max_c == 0 else (diff / max_c) * 255
    v = max_c * 255
    h = h / 2  # OpenCV Hue: 0-180

    if verbose:
        print(f"  HSV: ({int(h)}, {int(s)}, {int(v)})")

    img_array = np.array(img)
    img_bgr = img_array[:, :, ::-1].copy()

    hsv_img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    tol = hsv_toleranz
    lower = np.array([max(0, int(h) - tol), max(0, int(s) - 50), max(0, int(v) - 50)])
    upper = np.array([min(180, int(h) + tol), min(255, int(s) + 50), min(255, int(v) + 50)])

    mask = cv2.inRange(hsv_img, lower, upper)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    detected = []
    for contour in contours:
        x, y, w, h_box = cv2.boundingRect(contour)
        if w >= 40 and h_box >= 40:
            aspect = w / h_box
            if 0.5 < aspect < 2.0:
                detected.append((x, y, w, h_box))

    detected.sort(key=lambda s: (s[1] // 50, s[0]))

    # Groessen normalisieren
    if len(detected) >= 2:
        widths = [s[2] for s in detected]
        heights = [s[3] for s in detected]
        median_w = sorted(widths)[len(widths) // 2]
        median_h = sorted(heights)[len(heights) // 2]

        normalized = []
        for x, y, w, h_box in detected:
            if 0.7 * median_w <= w <= 1.3 * median_w:
                new_x = x + (w - median_w) // 2
                new_y = y + (h_box - median_h) // 2
                normalized.append((new_x, new_y, median_w, median_h))
        detected = normalized

    return detected, img_bgr


def slot_auto_detect(state: AutoClickerState) -> bool:
    """Automatische Slot-Erkennung mit OpenCV. Gibt True zurück wenn erfolgreich."""
    if not OPENCV_AVAILABLE:
        print(f"  {err('OpenCV nicht installiert!')} pip install opencv-python")
        return False
    if not NUMPY_AVAILABLE:
        print(f"  {err('NumPy nicht installiert!')} pip install numpy")
        return False

    import cv2   # nur noch fuer die Vorschau-Grafik am Ende

    print(header("AUTOMATISCHE SLOT-ERKENNUNG", width=50))
    print("\nMarkiere den Bereich mit den Slots:")
    print("  1. Maus auf OBEN-LINKS, ENTER")
    print("  2. Maus auf UNTEN-RECHTS, ENTER")

    region = select_region()
    if not region:
        print("  -> Keine Region ausgewählt")
        return False

    offset_x, offset_y = region[0], region[1]
    print(f"\n  Region: {region}")
    print("  Mache Screenshot in 2 Sekunden...")
    time.sleep(2)

    img = take_screenshot(region)
    if img is None:
        print(f"  {err('Screenshot fehlgeschlagen!')}")
        return False

    print(f"  Screenshot: {img.size[0]}x{img.size[1]}")

    # Farbe für Slot-Erkennung scannen
    print("\n  Bewege Maus auf den SLOT-HINTERGRUND...")
    safe_input("  ENTER wenn bereit...")
    mx, my = get_cursor_pos()

    slot_color_rgb = get_pixel_color(mx, my)
    if not slot_color_rgb:
        print(f"  {err('Konnte Farbe nicht lesen!')}")
        return False

    r, g, b = slot_color_rgb
    print(f"  Farbe: RGB({r}, {g}, {b})")

    detected_slots, img_bgr = erkenne_slots_im_bild(
        img, slot_color_rgb, state.config.scan_slot_hsv_tolerance, verbose=True)

    if not detected_slots:
        print(f"\n  {err('Keine Slots erkannt!')}")
        print("  Versuche es mit einer anderen Farbe.")
        return False

    print(f"\n  {len(detected_slots)} Slots erkannt!")

    slot_color = (r, g, b)

    # Slots hinzufügen
    inset = state.config.scan_slot_inset
    added = 0
    created_slots = []

    for i, (x, y, w, h_box) in enumerate(detected_slots):
        abs_x = x + offset_x + inset
        abs_y = y + offset_y + inset
        abs_w = w - (2 * inset)
        abs_h = h_box - (2 * inset)

        scan_region = (abs_x, abs_y, abs_x + abs_w, abs_y + abs_h)
        click_pos = (abs_x + abs_w // 2, abs_y + abs_h // 2)

        # Namen erst im Lock vergeben, direkt vor dem Einfügen: 'Slot <len+1>'
        # trifft nach einem gelöschten oder umbenannten Slot einen bestehenden
        # Namen, und das Dict überschreibt ihn kommentarlos. 'add' und der
        # Item-Lernpfad sichern das längst ab — hier fehlte es.
        with state.lock:
            slot_name = naechster_freier_name("Slot", state.global_slots)
            new_slot = ItemSlot(
                name=slot_name,
                scan_region=scan_region,
                click_pos=click_pos,
                slot_color=slot_color
            )
            state.global_slots[slot_name] = new_slot
        added += 1
        created_slots.append(new_slot)
        print(f"    + {slot_name}: {scan_region}")

    print(f"\n  {ok(f'{added} Slots hinzugefügt!')}")

    # Optional: Items direkt aus DEMSELBEN Screenshot lernen (Templates werden
    # aus img geschnitten, kein zweiter Screenshot nötig → garantiert konsistent).
    if created_slots and OPENCV_AVAILABLE:
        if confirm("\n  Items gleich aus diesem Screenshot mitlernen?"):
            from .item_editor.autoscan import item_autoscan_from_image
            item_autoscan_from_image(state, created_slots, img, (offset_x, offset_y))

    # Screenshots speichern
    try:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        screenshots_dir = Path(SCREENSHOTS_DIR)
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        screenshot_path = screenshots_dir / f"screenshot_{timestamp}.png"
        img.save(str(screenshot_path))
        print(f"  Screenshot: {screenshot_path}")

        # Vorschau mit Markierungen
        preview_path = screenshots_dir / f"preview_{timestamp}.png"
        preview = img_bgr.copy()
        for i, (dx, dy, dw, dh) in enumerate(detected_slots):
            cv2.rectangle(preview, (dx, dy), (dx + dw, dy + dh), (0, 255, 0), 2)
            cv2.rectangle(preview, (dx + inset, dy + inset),
                          (dx + dw - inset, dy + dh - inset), (0, 255, 255), 1)

            click_x = dx + dw // 2
            click_y = dy + dh // 2
            cross_size = 8
            cv2.line(preview, (click_x - cross_size, click_y), (click_x + cross_size, click_y), (0, 0, 255), 2)
            cv2.line(preview, (click_x, click_y - cross_size), (click_x, click_y + cross_size), (0, 0, 255), 2)

            # Der tatsächlich vergebene Name, nicht die laufende Nummer: die beiden
            # gehen auseinander, sobald ein Name schon belegt war.
            slot_num_text = created_slots[i].name if i < len(created_slots) else str(i + 1)
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            thickness = 2
            text_x = dx + 5
            text_y = dy + 20
            (text_w, text_h), _ = cv2.getTextSize(slot_num_text, font, font_scale, thickness)
            cv2.rectangle(preview, (text_x - 2, text_y - text_h - 2),
                          (text_x + text_w + 2, text_y + 2), (0, 0, 0), -1)
            cv2.putText(preview, slot_num_text, (text_x, text_y), font, font_scale, (255, 255, 255), thickness)
        cv2.imwrite(str(preview_path), preview)
        print(f"  Vorschau: {preview_path}")
    except (OSError, IOError, ValueError) as e:
        print(f"  {warn(f'Screenshots speichern: {e}')}")

    return True


# =============================================================================
# REPARATUR (Slots neu vermessen, Identität behalten)
# =============================================================================

def _zuordnung_pruefen(alte_slots: list, neue_rects: list[tuple],
                       inset: int, offset: tuple[int, int]) -> tuple:
    """Prüft, ob die neu erkannten Rechtecke zu den bestehenden Slots passen.

    Gibt `(paare, versatz, meldungen)` zurück; `paare` ist leer, wenn die Zuordnung
    nicht eindeutig ist.

    Die Prüfung ist der ganze Punkt: übernommen wird nur, wenn die Verschiebung für
    ALLE Slots dieselbe ist. Streuen die Einzelversätze, stimmt die Zuordnung nicht
    (andere Reihenfolge, ein Slot mehr erkannt, halb verdeckt) — dann lieber nichts
    tun als 20 Regionen falsch überschreiben.
    """
    meldungen = []
    if len(neue_rects) != len(alte_slots):
        meldungen.append(
            f"{len(neue_rects)} Slot(s) erkannt, aber {len(alte_slots)} gespeichert — "
            f"die Zuordnung waere geraten.")
        return [], None, meldungen

    ox, oy = offset
    paare = []
    for slot, (x, y, w, h) in zip(alte_slots, neue_rects):
        neue_region = (x + ox + inset, y + oy + inset,
                       x + ox + w - inset, y + oy + h - inset)
        paare.append((slot, neue_region))

    # Einzelversaetze: bei einer reinen Verschiebung sind alle gleich
    versaetze = [(neu[0] - slot.scan_region[0], neu[1] - slot.scan_region[1])
                 for slot, neu in paare]
    xs = [v[0] for v in versaetze]
    ys = [v[1] for v in versaetze]
    streuung = max(max(xs) - min(xs), max(ys) - min(ys))

    # Groessen muessen ebenfalls passen — sonst hat sich die Aufloesung geaendert
    # und eine reine Verschiebung waere die falsche Antwort.
    groessen_diff = 0
    for slot, neu in paare:
        alt_b = slot.scan_region[2] - slot.scan_region[0]
        alt_h = slot.scan_region[3] - slot.scan_region[1]
        groessen_diff = max(groessen_diff,
                            abs((neu[2] - neu[0]) - alt_b),
                            abs((neu[3] - neu[1]) - alt_h))

    if groessen_diff > _REPAIR_MAX_GROESSEN_DIFF:
        meldungen.append(
            f"Die Slot-Groesse weicht um bis zu {groessen_diff} px ab — sieht nach einer "
            f"anderen Aufloesung aus, nicht nach einer Verschiebung.")
    if streuung > _REPAIR_MAX_STREUUNG:
        meldungen.append(
            f"Die Einzelversaetze streuen um {streuung} px — die Zuordnung ist nicht "
            f"eindeutig (andere Reihenfolge? ein Slot verdeckt?).")

    if meldungen:
        return [], None, meldungen

    # Mittlerer Versatz nur zur Anzeige/Weitergabe
    versatz = (round(sum(xs) / len(xs)), round(sum(ys) / len(ys)))
    return paare, versatz, meldungen


_REPAIR_MAX_STREUUNG = 4          # px, die die Einzelversaetze auseinanderliegen duerfen
_REPAIR_MAX_GROESSEN_DIFF = 4     # px, die die Slot-Groesse abweichen darf


def slot_repair(state: AutoClickerState) -> bool:
    """Vermisst die bestehenden Slots neu und übernimmt die Koordinaten.

    Namen, Reihenfolge und alles, was per Namen darauf verweist, bleiben —
    ersetzt werden nur `scan_region` und `click_pos`. Eine Maus-Position trifft
    den Pixel nie genau; die Erkennung schon.
    """
    if not OPENCV_AVAILABLE or not NUMPY_AVAILABLE:
        print(f"  {err('OpenCV/NumPy nicht installiert!')} pip install opencv-python numpy")
        return False

    with state.lock:
        alte_slots = list(state.global_slots.values())
    if not alte_slots:
        print(f"  {err('Keine Slots gespeichert — es gibt nichts zu reparieren.')}")
        return False

    print(header("SLOTS REPARIEREN", width=50))
    print(f"\n  {len(alte_slots)} gespeicherte Slots werden neu vermessen.")
    print(f"  {hint('Namen und Verweise bleiben — nur die Koordinaten werden ersetzt.')}")
    print("\nMarkiere den Bereich mit den Slots (grosszuegig ist ok):")
    print("  1. Maus auf OBEN-LINKS, ENTER")
    print("  2. Maus auf UNTEN-RECHTS, ENTER")

    region = select_region()
    if not region:
        print(f"  {info('[ABBRUCH] Keine Region ausgewaehlt.')}")
        return False

    # Die gespeicherte Slot-Farbe wiederverwenden — die haengt nicht am Bildschirm-
    # Layout, und nochmal picken zu lassen waere eine Fehlerquelle ohne Gewinn.
    farben = [s.slot_color for s in alte_slots if s.slot_color]
    if farben:
        slot_color = max(set(farben), key=farben.count)
        print(f"\n  Slot-Farbe aus dem Bestand: RGB{slot_color}")
    else:
        print("\n  Keine Farbe gespeichert — bitte einmalig picken.")
        print("  Bewege Maus auf den SLOT-HINTERGRUND...")
        safe_input("  ENTER wenn bereit...")
        mx, my = get_cursor_pos()
        slot_color = get_pixel_color(mx, my)
        if not slot_color:
            print(f"  {err('Konnte Farbe nicht lesen!')}")
            return False

    print("  Mache Screenshot in 2 Sekunden...")
    time.sleep(2)
    img = take_screenshot(region)
    if img is None:
        print(f"  {err('Screenshot fehlgeschlagen!')}")
        return False

    neue_rects, _ = erkenne_slots_im_bild(img, slot_color,
                                          state.config.scan_slot_hsv_tolerance)
    print(f"  {len(neue_rects)} Slot(s) erkannt.")

    inset = state.config.scan_slot_inset
    paare, versatz, meldungen = _zuordnung_pruefen(
        alte_slots, neue_rects, inset, (region[0], region[1]))

    if not paare:
        print()
        for m in meldungen:
            print(f"  {err(m)}")
        print(f"  {info('Nichts geaendert.')}")
        print(f"  {hint('Tipp: Bereich enger markieren, oder die Slots muessen alle')}")
        print(f"  {hint('sichtbar und unverdeckt sein (kein Tooltip daruber).')}")
        return False

    print()
    print(col("  VORSCHAU:", 'bold'))
    for slot, neu in paare[:12]:
        print(f"    {slot.name:<18} {slot.scan_region}  ->  {neu}")
    if len(paare) > 12:
        print(f"    {info(f'... und {len(paare) - 12} weitere')}")
    print()
    print(f"  Versatz durchgaengig: {col(f'{versatz[0]:+} X, {versatz[1]:+} Y', 'yellow')}")

    if versatz == (0, 0):
        print(f"  {info('Die Slots sitzen schon richtig — nichts zu tun.')}")
        return False

    if not confirm("\n  Neue Koordinaten uebernehmen?", default=False):
        print(f"  {info('[ABBRUCH] Nichts geaendert.')}")
        return False

    from ..import_export import sichere_vor_kalibrierung
    sicherung = sichere_vor_kalibrierung(state)
    if sicherung:
        print(f"  {ok('Sicherung angelegt:')} {sicherung}")
    else:
        print(f"  {warn('Sicherung fehlgeschlagen — es wird trotzdem geschrieben.')}")

    with state.lock:
        for slot, neu in paare:
            slot.scan_region = neu
            slot.click_pos = ((neu[0] + neu[2]) // 2, (neu[1] + neu[3]) // 2)
            if not slot.slot_color:
                slot.slot_color = slot_color
    save_global_slots(state)
    print(f"  {ok(f'{len(paare)} Slot(s) neu vermessen.')}")

    # Der hier gemessene Versatz ist pixelgenau — deutlich besser als eine
    # Maus-Position. Deshalb anbieten, ihn gleich auf den Rest anzuwenden.
    print()
    print(f"  {info('Dieser Versatz wurde gemessen, nicht mit der Maus gesetzt —')}")
    print(f"  {info('er ist genauer als eine Kalibrierung von Hand.')}")
    if confirm("  Denselben Versatz auf Punkte/Scans/Sequenzen anwenden?", default=False):
        from ..import_export import (transform_aus_verschiebung, kalibriere_bestand,
                                     kalibrier_vorschau)
        from .import_export_editor import _ausserhalb_der_monitore
        t = transform_aus_verschiebung((0, 0), versatz)

        # Dieselbe Vorschau + Warnung wie im Punkte-Menue. Der Versatz ist zwar
        # genauer gemessen, aber er stammt von EINEM Bildschirm: liegen Punkte auf
        # einem anderen, stimmt er fuer die nicht. Gleiche Schreiboperation,
        # gleiche Absicherung.
        vorschau = kalibrier_vorschau(state, t)
        print()
        print(col("  VORSCHAU (Auszug):", 'bold'))
        for label, alt, neu in vorschau[:8]:
            print(f"    {label:<32} ({alt[0]:>5}, {alt[1]:>5})  ->  ({neu[0]:>5}, {neu[1]:>5})")
        if len(vorschau) > 8:
            print(f"    {info(f'... und {len(vorschau) - 8} weitere')}")
        draussen = _ausserhalb_der_monitore([n for _, _, n in vorschau])
        if draussen:
            print(f"  {warn(f'{draussen} Ziel(e) laegen danach ausserhalb aller Monitore —')}")
            print(f"  {info('die liegen vermutlich auf einem anderen Bildschirm als die Slots.')}")
        if not confirm("  Wirklich uebernehmen?", default=False):
            print(f"  {info('[ABBRUCH] Nur die Slots wurden geaendert.')}")
            return True

        # mit_slots=False: die Slots sind gerade exakt vermessen worden und duerfen
        # kein zweites Mal wandern. Boss-/Icon-Scan-Regionen und die
        # Item-Bestaetigungsklicks brauchen den Versatz dagegen sehr wohl.
        zahl = kalibriere_bestand(state, t, mit_scans=True, mit_sequenzen=True,
                                  mit_slots=False)
        print(f"  {ok('Uebernommen:')} "
              + ", ".join(f"{v} {k}" for k, v in zahl.items() if v))
        print(f"  {info('Sequenzdateien geaendert — mit CTRL+ALT+L neu laden.')}")
    return True
