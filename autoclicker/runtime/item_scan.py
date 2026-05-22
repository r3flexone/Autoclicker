"""
Item-Scan-Runtime: scannt Slots nach bekannten Item-Profilen und liefert eine
Liste von (Klick-Position, Item, Priorität) zurück. Die Step-Dispatcher in
steps.py rufen execute_item_scan an und klicken die Treffer via _click_scan_result.

_check_profile_match wird sowohl von Item- als auch Boss-Erkennung genutzt —
deswegen lebt es hier (Item-Erkennung ist der Haupt-User).
"""

import ctypes
import time

from ..imaging import take_screenshot, find_color_in_image, match_template_in_image
from ..models import (
    AutoClickerState, SCAN_MODE_ALL, SCAN_MODE_BEST, SCAN_MODE_EVERY,
)
from ..utils import col, err, dbg, wait_while_paused
from ..winapi import set_cursor_pos
from .actions import safe_click


# =============================================================================
# PROFIL-MATCHING HELPER (gemeinsam für Item- und Boss-Erkennung)
# =============================================================================

def _check_profile_match(profile, img, color_tolerance: int,
                          state: 'AutoClickerState', debug: bool,
                          found_label: str = "gefunden") -> bool:
    """Prüft ob ein Profil (Item oder Boss) per Template/Marker im Screenshot erkannt wird.

    Returns: True wenn Template UND Marker OK und mindestens eines definiert ist.
    """
    template_ok = True
    template_info = ""
    marker_ok = True
    marker_info = ""

    if profile.template:
        match, confidence, _pos = match_template_in_image(
            img, profile.template, profile.min_confidence
        )
        template_ok = match
        template_info = (f"Template {confidence:.1%}" if match
                         else f"Template {confidence:.1%} (min: {profile.min_confidence:.0%})")

    if profile.marker_colors:
        markers_total = len(profile.marker_colors)
        markers_found = sum(1 for marker in profile.marker_colors
                            if find_color_in_image(img, marker, color_tolerance))

        require_all = state.config.scan_require_all_markers
        min_required = state.config.scan_min_markers_required

        marker_ok = (markers_found == markers_total) if require_all else (markers_found >= min_required)
        marker_info = f"Marker {markers_found}/{markers_total}"

    if debug:
        info_parts = []
        if profile.template:
            info_parts.append(template_info)
        if profile.marker_colors:
            info_parts.append(marker_info)

        if not info_parts:
            print(dbg(f"  → {profile.name}: kein Template/Marker definiert"))
        elif template_ok and marker_ok:
            print(dbg(f"  → {profile.name} {found_label} ({', '.join(info_parts)})"))
        else:
            print(dbg(f"  → {profile.name}: {', '.join(info_parts)}"))

    return template_ok and marker_ok and bool(profile.template or profile.marker_colors)


# =============================================================================
# ITEM-SCAN (Hauptfunktion)
# =============================================================================

def execute_item_scan(state: AutoClickerState, scan_name: str, mode: str = SCAN_MODE_ALL,
                      slots_override: list = None) -> list:
    """Führt einen Item-Scan aus und gibt Liste von (position, item, priority) zurück.

    slots_override: Nur diese Slots scannen, Reverse-Reihenfolge ignorieren.
                    Wird vom Immediate-Modus genutzt (ein Slot pro Aufruf)."""
    # Snapshot der Config und ihrer Listen unter Lock — verhindert Mutation durch Editoren
    # während wir iterieren (RuntimeError bei dict/list changed during iteration).
    with state.lock:
        config = state.item_scans.get(scan_name)
        if config is None:
            print(err(f"Item-Scan '{scan_name}' nicht gefunden!"))
            return []
        if not config.slots or not config.items:
            print(err(f"Item-Scan '{scan_name}' hat keine Slots oder Items!"))
            return []
        slots_snapshot = list(config.slots)
        items_snapshot = list(config.items)
        color_tolerance = config.color_tolerance

    found_items = []

    if slots_override is not None:
        slots_to_scan = list(slots_override)
    else:
        slots_to_scan = slots_snapshot
        if state.config.scan_reverse:
            slots_to_scan = list(reversed(slots_to_scan))

    scan_delay = state.config.scan_slot_delay
    debug = state.config.debug_detection

    _park_mouse_for_scan(state.config.scan_park_mouse)

    for idx, slot in enumerate(slots_to_scan):
        if state.stop_event.is_set() or state.skip_event.is_set():
            break

        if not wait_while_paused(state, f"Scan '{scan_name}' pausiert..."):
            break

        if scan_delay > 0 and idx > 0:
            if state.stop_event.wait(scan_delay):
                break

        if debug:
            screenshot_start = time.time()
        img = take_screenshot(slot.scan_region)

        if img is None:
            continue

        if debug:
            screenshot_ms = (time.time() - screenshot_start) * 1000
            size_info = f"{img.size[0]}x{img.size[1]}"
            print(dbg(f"Scanne {slot.name}... (Screenshot: {screenshot_ms:.0f}ms, {size_info}px)"))

        for item in items_snapshot:
            if _check_profile_match(item, img, color_tolerance, state, debug, "gefunden!"):
                found_items.append((slot, item, item.priority))
                break

    if not found_items:
        return []

    return _filter_scan_results(state, found_items, mode, debug)


def _park_mouse_for_scan(park_pos) -> None:
    """Parkt die Maus an einer Position bevor gescannt wird (verhindert Tooltip/Hover-Störungen)."""
    if not park_pos:
        return
    if isinstance(park_pos, (list, tuple)) and len(park_pos) == 2:
        px, py = int(park_pos[0]), int(park_pos[1])
    else:
        # true = Bildschirmmitte (virtueller Desktop für Multi-Monitor)
        try:
            SM_CXVIRTUALSCREEN = 78
            SM_CYVIRTUALSCREEN = 79
            SM_XVIRTUALSCREEN = 76
            SM_YVIRTUALSCREEN = 77
            vw = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
            vh = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
            vx = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            vy = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
            px = vx + vw // 2
            py = vy + vh // 2
        except (AttributeError, OSError):
            px = ctypes.windll.user32.GetSystemMetrics(0) // 2 if hasattr(ctypes, 'windll') else 960
            py = ctypes.windll.user32.GetSystemMetrics(1) // 2 if hasattr(ctypes, 'windll') else 540
    set_cursor_pos(px, py)
    time.sleep(0.05)  # Kurz warten bis Maus angekommen & Tooltip weg


def _filter_scan_results(state: AutoClickerState, found_items: list, mode: str, debug: bool) -> list:
    """Filtert Scan-Treffer nach Modus (every / all / best) und Kategorie-Konflikt."""
    if mode == SCAN_MODE_EVERY:
        print(col(f"[SCAN] {len(found_items)} Item(s) gefunden - klicke alle!", "cyan"))
        return [(slot.click_pos, item, priority) for slot, item, priority in found_items]

    # Gruppiere nach Kategorie, aber behalte die Scan-Reihenfolge
    best_per_category = {}
    ordered_categories = []
    for slot, item, priority in found_items:
        cat = item.category or item.name

        with state.lock:
            if cat in state.clicked_categories:
                best_clicked_prio = state.clicked_categories[cat]
                if priority >= best_clicked_prio:
                    if debug:
                        print(dbg(f"  → {item.name} übersprungen ('{cat}' bereits geklickt)"))
                    continue

        if cat not in best_per_category:
            ordered_categories.append(cat)
            best_per_category[cat] = (slot, item, priority)
        elif priority < best_per_category[cat][2]:
            best_per_category[cat] = (slot, item, priority)

    filtered_items = [best_per_category[cat] for cat in ordered_categories]

    if mode == SCAN_MODE_ALL:
        print(col(f"[SCAN] {len(filtered_items)} Item(s) gefunden - klicke alle!", "cyan"))
        return [(slot.click_pos, item, priority) for slot, item, priority in filtered_items]

    # SCAN_MODE_BEST: nur das beste Item insgesamt
    if not filtered_items:
        return []
    filtered_items.sort(key=lambda x: x[2])
    best_slot, best_item, best_priority = filtered_items[0]
    print(col(f"[SCAN] Bestes Item: {best_item.name} (P{best_priority})", "cyan"))
    return [(best_slot.click_pos, best_item, best_priority)]


# =============================================================================
# KLICK-AUSFÜHRUNG FÜR EIN GEFUNDENES ITEM
# =============================================================================

def _click_scan_result(state: AutoClickerState, pos, item, priority, debug: bool) -> bool:
    """Klickt ein gefundenes Item (inkl. Confirm-Klick und Delays).
    Gibt False zurück wenn stop_event während Warten feuert."""
    if debug:
        print(dbg(f"Item-Klick: '{item.name}' (P{priority}) @ ({pos[0]}, {pos[1]})"))

    if not safe_click(state, pos[0], pos[1], label=f"item:{item.name}"):
        return False
    with state.lock:
        state.total_clicks += 1
        state.items_found += 1
        cat = item.category or item.name
        if cat not in state.clicked_categories or priority < state.clicked_categories[cat]:
            state.clicked_categories[cat] = priority

    if item.confirm_point is not None:
        if item.confirm_delay > 0:
            if debug:
                print(dbg(f"Warte {item.confirm_delay}s vor Confirm..."))
            if state.stop_event.wait(item.confirm_delay):
                return False

        if debug:
            print(dbg(f"Confirm-Klick @ ({item.confirm_point.x}, {item.confirm_point.y})"))

        if not safe_click(state, item.confirm_point.x, item.confirm_point.y,
                          label=f"confirm:{item.name}"):
            return False
        with state.lock:
            state.total_clicks += 1

    click_delay = state.config.scan_item_click_delay
    if click_delay > 0:
        if state.stop_event.wait(click_delay):
            return False
    return True
