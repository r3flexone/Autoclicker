"""
Item-Scan-Runtime: scannt Slots nach bekannten Item-Profilen und liefert eine
Liste von (Klick-Position, Item, Priorität) zurück. Die Step-Dispatcher in
steps.py rufen execute_item_scan an und klicken die Treffer via _click_scan_result.

_check_profile_match wird sowohl von Item- als auch Boss-Erkennung genutzt —
deswegen lebt es hier (Item-Erkennung ist der Haupt-User).
"""

import json
import logging
import os
import time

logger = logging.getLogger("autoclicker")

from ..imaging import (
    take_consistent_window_screenshot, take_screenshot, find_color_in_image,
    match_template_in_image, template_size,
)
from ..models import (
    AutoClickerState, ItemProfile, ItemSlot, SCAN_MODE_ALL, SCAN_MODE_EVERY,
)
from ..editors.scan_services import (
    crop_screen_region, map_point_between_rects, map_region_between_rects,
)
from ..session_log import log_event
from ..utils import col, err, dbg, warn, wait_while_paused, sanitize_filename
from ..winapi import set_cursor_pos, get_screen_center, resolve_window
from .actions import safe_click
from .debug import is_log_debug

# Windows GetSystemMetrics-Indizes für den virtuellen Desktop (Multi-Monitor-Spannweite).
# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getsystemmetrics
# Fallback-Indizes für den Primärbildschirm (wenn Virtual-Screen-Abfrage fehlschlägt)

# Settle-Zeit nach Maus-Park bevor der Scan beginnt — verhindert dass ein noch
# sichtbarer Hover-Tooltip die Erkennung verfälscht.
_MOUSE_PARK_SETTLE = 0.05

# Manche Spiele unterstützen PrintWindow grundsätzlich nicht. Der notwendige
# Desktop-Fallback ist wichtig, aber dieselbe Warnung in jedem Zyklus wäre nur
# Rauschen. Pro Scan und Sitzung genügt einmal.
_window_capture_warnings: set[tuple[str, str]] = set()


# =============================================================================
# PROFIL-MATCHING HELPER (gemeinsam für Item- und Boss-Erkennung)
# =============================================================================

def _check_profile_match(profile, img, color_tolerance: int,
                          state: 'AutoClickerState', debug: bool,
                          found_label: str = "gefunden",
                          return_score: bool = False,
                          template_root=None):
    """Prüft ob ein Profil (Item oder Boss) per Template/Marker im Screenshot erkannt wird.

    Returns: True wenn Template UND Marker OK und mindestens eines definiert ist.
             Mit ``return_score`` zusätzlich eine vergleichbare Trefferqualität.
    """
    template_ok = True
    template_info = ""
    template_score = None
    marker_ok = True
    marker_info = ""
    marker_score = None

    ist_item = isinstance(profile, ItemProfile)
    if template_root is None and state is not None and getattr(state, "active_sequence", None) is not None:
        from ..persistence.sequences import sequence_dir
        template_root = sequence_dir(state.active_sequence.name) / "templates"
    vorlagen = (profile.template_names() if ist_item
                 else ([profile.template] if profile.template else []))
    if vorlagen:
        if ist_item:
            # Ein Item wird nur mit einer fuer diesen Slot gelernten Variante
            # verglichen. Damit gibt es keine halbgültigen Resize-Ergebnisse.
            candidates = [name for name in vorlagen
                           if template_size(name, template_root) == tuple(img.size)]
        else:
            # Boss-/Icon-Profile behalten ihr bisheriges Resize-Verhalten.
            candidates = vorlagen

        if not candidates:
            template_ok = False
            template_score = 0.0
            template_info = f"für Slot {img.size[0]}×{img.size[1]} nicht gelernt"
        else:
            ergebnisse = [
                match_template_in_image(
                    img, name, profile.min_confidence,
                    resize_template=not ist_item,
                    report_size_mismatch=not ist_item,
                    template_root=template_root,
                )
                for name in candidates
            ]
            match, confidence, _pos = max(ergebnisse, key=lambda value: value[1])
            template_ok = match
            template_score = max(0.0, min(1.0, float(confidence)))
            template_info = (f"Template {confidence:.1%}" if match
                             else f"Template {confidence:.1%} "
                                  f"(min: {profile.min_confidence:.0%})")

    if profile.marker_colors:
        markers_total = len(profile.marker_colors)
        min_pixels = state.config.scan_marker_min_pixels
        markers_found = sum(1 for marker in profile.marker_colors
                            if find_color_in_image(img, marker, color_tolerance,
                                                    min_pixels=min_pixels))

        require_all = state.config.scan_require_all_markers
        min_required = state.config.scan_min_markers_required

        marker_ok = (markers_found == markers_total) if require_all else (markers_found >= min_required)
        marker_score = markers_found / markers_total if markers_total else 0.0
        marker_info = f"Marker {markers_found}/{markers_total}"

    if debug:
        info_parts = []
        if vorlagen:
            info_parts.append(template_info)
        if profile.marker_colors:
            info_parts.append(marker_info)

        if not info_parts:
            print(dbg(f"  → {profile.name}: kein Template/Marker definiert"))
        elif template_ok and marker_ok:
            print(dbg(f"  → {profile.name} {found_label} ({', '.join(info_parts)})"))
        else:
            print(dbg(f"  → {profile.name}: {', '.join(info_parts)}"))

    matched = template_ok and marker_ok and bool(vorlagen or profile.marker_colors)
    scores = [score for score in (template_score, marker_score) if score is not None]
    score = sum(scores) / len(scores) if scores else 0.0
    return (matched, score) if return_score else matched


# =============================================================================
# ICON-SCAN (Symbol/Icon in einer Region erkennen)
# =============================================================================

def execute_icon_scan(state: AutoClickerState, scan_name: str) -> bool:
    """Prüft ob das in der IconScanConfig definierte Icon in seiner Region sichtbar ist.

    Nutzt dieselbe Template/Marker-Erkennung wie der Item-Scan (_check_profile_match),
    aber als reines Ja/Nein — die Aktion bei Fund liegt im Step-Handler.
    """
    with state.lock:
        config = state.icon_scans.get(scan_name)
        if config is None:
            print(err(f"Icon-Scan '{scan_name}' nicht gefunden!"))
            return False
        scan_region = config.scan_region
        color_tolerance = config.color_tolerance

    img = take_screenshot(scan_region)
    if img is None:
        return False

    debug = is_log_debug(state)
    return _check_profile_match(config, img, color_tolerance, state, debug, "Icon erkannt!")


# =============================================================================
# ITEM-SCAN (Hauptfunktion)
# =============================================================================

def runnable_scan_config(state: AutoClickerState, scan_name: str):
    """Gibt die Scan-Config zurück, oder None samt Meldung wenn sie nicht laufen kann.

    Aufrufer MUSS state.lock halten.

    Eine Stelle für beide Scan-Pfade (normal und Immediate). Vorher hatte der
    Immediate-Modus seine eigene, stillschweigende Abbruchbedingung — ein Tippfehler
    im Scan-Namen war dort unsichtbar, während der normale Pfad ihn meldete.
    """
    config = state.item_scans.get(scan_name)
    if config is None:
        print(err(f"Item-Scan '{scan_name}' nicht gefunden!"))
        return None
    if not any(slot.enabled for slot in config.slots):
        print(err(f"Item-Scan '{scan_name}' hat keine aktiven Slots!"))
        return None
    # Ohne Items ist ein Scan nur sinnvoll, wenn er unbekannte Inhalte lernen soll.
    if not any(item.enabled for item in config.items) and not config.learn_unknown:
        print(err(f"Item-Scan '{scan_name}' hat keine aktiven Items "
                  f"(und Auto-Lernen ist aus)!"))
        return None
    return config


def execute_item_scan(state: AutoClickerState, scan_name: str, mode: str = SCAN_MODE_ALL,
                      slots_override: list = None) -> list:
    """Führt einen Item-Scan aus und gibt Liste von (position, item, priority) zurück.

    slots_override: Nur diese Slots scannen, Reverse-Reihenfolge ignorieren.
                    Wird vom Immediate-Modus genutzt (ein Slot pro Aufruf)."""
    # Snapshot der Config und ihrer Listen unter Lock — verhindert Mutation durch Editoren
    # während wir iterieren (RuntimeError bei dict/list changed during iteration).
    with state.lock:
        config = runnable_scan_config(state, scan_name)
        if config is None:
            return []
        slots_snapshot = [slot for slot in config.slots if slot.enabled]
        items_snapshot = [item for item in config.items if item.enabled]
        color_tolerance = config.color_tolerance
        learn_unknown = config.learn_unknown
        # Im selben Lock-Snapshot wie die übrigen Flags: wer die Richtung
        # zweimal frisch liest, kann einen Editor dazwischen umschalten sehen.
        rueckwaerts = config.reverse
        window_title = config.capture_window_title
        fenster_index = config.capture_window_index
        window_reference = (tuple(config.capture_window_rect)
                            if config.capture_window_rect else None)

    found_items = []

    if slots_override is not None:
        slots_to_scan = [slot for slot in slots_override if slot.enabled]
    else:
        slots_to_scan = slots_snapshot
        if rueckwaerts:
            slots_to_scan = list(reversed(slots_to_scan))

    scan_delay = state.config.scan_slot_delay
    debug = is_log_debug(state)

    _park_mouse_for_scan(state.config.scan_park_mouse)

    # Ein Fenster-Scan arbeitet auf EINEM eingefrorenen Bild — genau wie der
    # Editor. Damit können sich Items nicht mitten im Durchgang verschieben, und
    # beide Wege sehen wirklich dieselben Pixel aus derselben Aufnahmemethode.
    fensterbild = None
    window_rect = None
    if window_title:
        window = resolve_window(window_title, fenster_index, window_reference)
        if window is None:
            print(err(f"Item-Scan '{scan_name}': Fenster '{window_title}' nicht "
                      "gefunden. Spiel öffnen oder die Aufnahmequelle im Studio "
                      "neu wählen."))
            return []
        if debug:
            screenshot_start = time.time()
        aufnahme = take_consistent_window_screenshot(window[2])
        if aufnahme is None:
            print(err(f"Item-Scan '{scan_name}': Fenster '{window_title}' konnte "
                      "nicht aufgenommen werden."))
            return []
        fensterbild, window_rect, hinweis = aufnahme
        if hinweis:
            key_name = (scan_name, hinweis)
            if key_name not in _window_capture_warnings:
                _window_capture_warnings.add(key_name)
                print(warn(f"Item-Scan '{scan_name}':{hinweis}"))
        if debug:
            screenshot_ms = (time.time() - screenshot_start) * 1000
            print(dbg(f"Fenster '{window_title}' einmal aufgenommen: "
                      f"{fensterbild.size[0]}x{fensterbild.size[1]}px "
                      f"in {screenshot_ms:.0f}ms"))

        referenz = window_reference or window_rect
        try:
            slots_to_scan = [ItemSlot(
                name=slot.name,
                scan_region=map_region_between_rects(
                    slot.scan_region, referenz, window_rect),
                click_pos=map_point_between_rects(
                    slot.click_pos, referenz, window_rect),
                slot_color=slot.slot_color,
                enabled=slot.enabled,
                id=slot.id,
            ) for slot in slots_to_scan]
        except (TypeError, ValueError):
            print(err(f"Item-Scan '{scan_name}': gespeicherte Fenstergeometrie ist "
                      "ungültig. Aufnahmequelle im Studio neu wählen."))
            return []

    for idx, slot in enumerate(slots_to_scan):
        if state.stop_event.is_set():
            break
        if state.skip_event.is_set():
            # Skip konsumieren — sonst überspringt ein Skip zwei Dinge
            # (diesen Scan und den nächsten skip-fähigen Schritt).
            state.skip_event.clear()
            break
        if state.skip_step_event.is_set():
            state.skip_step_event.clear()
            break

        if not wait_while_paused(state, f"Scan '{scan_name}' pausiert..."):
            break

        if fensterbild is None and scan_delay > 0 and idx > 0:
            if state.stop_event.wait(scan_delay):
                break

        if debug:
            screenshot_start = time.time()
        if fensterbild is not None:
            img = crop_screen_region(
                fensterbild, slot.scan_region,
                (window_rect[0], window_rect[1]))
        else:
            img = take_screenshot(slot.scan_region)

        if img is None:
            continue

        if debug:
            screenshot_ms = (time.time() - screenshot_start) * 1000
            size_info = f"{img.size[0]}x{img.size[1]}"
            print(dbg(f"Scanne {slot.name}... (Screenshot: {screenshot_ms:.0f}ms, {size_info}px)"))

        candidates = []
        for reihenfolge, item in enumerate(items_snapshot):
            result = _check_profile_match(
                item, img, color_tolerance, state, debug, "gefunden!",
                return_score=True,
            )
            # Kompatibel mit Tests/Erweiterungen, die den internen Bool-Helfer
            # ersetzen: ein einfaches True ist ein vollwertiger Treffer.
            if isinstance(result, tuple):
                passt, qualitaet = result
            else:
                passt, qualitaet = bool(result), 1.0 if result else 0.0
            if passt:
                candidates.append((qualitaet, -reihenfolge, item))

        matched = bool(candidates)
        if matched:
            qualitaet, _neg_reihenfolge, item = max(
                candidates, key=lambda kandidat: (kandidat[0], kandidat[1]))
            found_items.append((slot, item, item.priority))
            if debug and len(candidates) > 1:
                print(dbg(f"  → {item.name}: bester von {len(candidates)} Treffern "
                          f"({qualitaet:.1%})"))

        if not matched and learn_unknown:
            _learn_unknown_slot_item(state, slot, img, debug)

    if not found_items:
        return []

    return _filter_scan_results(state, found_items, mode, debug)


def _learn_unknown_slot_item(state: AutoClickerState, slot, img, debug: bool) -> None:
    """Lernt einen unbekannten Slot-Inhalt als neues globales Item (opt-in).

    Dedup per Template-Matching gegen alle globalen Items; Slots die nur die
    Hintergrundfarbe zeigen gelten als leer und werden übersprungen. Neue Items
    landen NUR in state.global_items (Kategorie 'Auto') — nicht in der
    Scan-Config, damit sie nicht ungeprüft geklickt werden.
    """
    from ..imaging import OPENCV_AVAILABLE
    if not OPENCV_AVAILABLE:
        return
    # Editor-Helfer lazy importieren (markers.py hängt nur an imaging/config,
    # kein Import-Zyklus mit runtime/)
    from ..editors.item_editor.markers import (
        _find_matching_existing_item, _item_has_compatible_template,
        _prepare_learning_image,
    )
    from ..persistence import save_global_items, active_templates_dir

    # Dieselbe Leer-Regel wie im Studio: komplett ausmaskiert = kein Item.
    maskiert, marker_colors, is_blank = _prepare_learning_image(img, slot.slot_color)
    if is_blank:
        if debug:
            print(dbg(f"  → {slot.name}: leer (nur Hintergrund) — kein Auto-Lernen"))
        return

    # Dedup: schon als globales Item bekannt (z.B. in früherem Zyklus gelernt)?
    with state.lock:
        existing = [(n, it) for n, it in state.global_items.items()
                    if it.template_names()]
    min_confidence = state.config.scan_min_confidence
    # **Der Vorlagenordner MUSS mit.** Ohne ihn faellt `_template_path()` auf den
    # globalen `items/templates/` zurueck, den es seit dem Umzug auf
    # Besitzeinheiten nicht mehr gibt: `template_size()` liefert dann fuer JEDE
    # Vorlage None, die Dedup-Pruefung findet nie einen Treffer - und
    # `learn_unknown` legt denselben Slot in jedem Zyklus erneut als neues Item
    # an. Vier Zeilen tiefer stand der richtige Ordner laengst da.
    vorlagen_ordner = active_templates_dir(state)
    known = _find_matching_existing_item(img, existing, min_confidence,
                                         vorlagen_ordner)
    if known:
        with state.lock:
            known_item = state.global_items.get(known)
        if known_item is not None and not _item_has_compatible_template(
                known_item, img, vorlagen_ordner):
            width, height = img.size
            basis = f"{sanitize_filename(known)}_{width}x{height}"
            template_file = f"{basis}.png"
            number = 2
            while (active_templates_dir(state) / template_file).exists():
                template_file = f"{basis}_{number}.png"
                number += 1
            template_path = active_templates_dir(state) / template_file
            try:
                template_path.parent.mkdir(parents=True, exist_ok=True)
                maskiert.save(template_path)
            except (OSError, ValueError) as e:
                print(warn(f"Auto-Lernen: Vorlage für '{known}' konnte nicht "
                           f"gespeichert werden: {e}"))
                return
            with state.lock:
                if template_file not in known_item.template_variants:
                    known_item.template_variants.append(template_file)
            save_global_items(state)
            print(col(f"[AUTO-LERNEN] '{known}' kann jetzt auch in "
                      f"{width}×{height}-Slots erkannt werden", "green"))
            return
        if debug:
            print(dbg(f"  → {slot.name}: bekannt als '{known}' — kein Auto-Lernen"))
        return

    # Schnellen Namen vergeben — KEIN LLM während des Scans (würde den Worker
    # pro Item bis zu llm_timeout Sekunden blockieren). Sinnvolle Namen vergibt
    # man danach manuell im Item-Editor ('autoname'), das die LLM-Benennung aus
    # den gespeicherten Templates macht — wann man will, ohne den Lauf zu bremsen.
    base = f"Auto {slot.name}"

    # Eindeutigen Namen vergeben + sofort reservieren (Worker/Editor-Race)
    item = ItemProfile(
        name="", marker_colors=marker_colors, category="Auto",
        priority=99, template=None, min_confidence=min_confidence,
    )
    with state.lock:
        name = base
        counter = 1
        while name in state.global_items:
            counter += 1
            name = f"{base} {counter}"
        item.name = name
        # Das Objekt wird ab hier für Editor und Worker sichtbar. Deshalb muss
        # es schon vollständig initialisiert sein; insbesondere darf
        # ``template`` nicht erst ausserhalb des Locks gesetzt werden.
        template_file = f"{sanitize_filename(name)}.png"
        item.template = template_file
        state.global_items[name] = item

    template_path = active_templates_dir(state) / template_file
    try:
        template_path.parent.mkdir(parents=True, exist_ok=True)
        maskiert.save(template_path)
    except (OSError, ValueError) as e:
        with state.lock:
            state.global_items.pop(name, None)
        print(warn(f"Auto-Lernen: Template für '{name}' konnte nicht gespeichert werden: {e}"))
        return

    save_global_items(state)
    print(col(f"[AUTO-LERNEN] Neues Item '{name}' aus {slot.name} gespeichert "
              "(Kategorie 'Auto', wird nicht geklickt)", "green"))


def _park_mouse_for_scan(park_pos) -> None:
    """Parkt die Maus an einer Position bevor gescannt wird (verhindert Tooltip/Hover-Störungen)."""
    if not park_pos:
        return
    if isinstance(park_pos, (list, tuple)) and len(park_pos) == 2:
        px, py = int(park_pos[0]), int(park_pos[1])
    else:
        # true = Bildschirmmitte (virtueller Desktop für Multi-Monitor)
        px, py = get_screen_center()
    set_cursor_pos(px, py)
    time.sleep(_MOUSE_PARK_SETTLE)


# Marktwerte aus market_analysis. Schluessel: (Pfad, mtime) - eine neu gerechnete
# Analyse greift damit beim naechsten Scan, ohne Neustart. Wie beim Template-Cache
# ohne Lock: Dict-Zugriffe sind unter dem GIL atomar, und zweimal dieselbe kleine
# JSON zu lesen kostet nichts.
_marktwert_cache: dict = {}


def load_market_values(path: str) -> dict:
    """Item-Name -> Gold pro Stueck. Leeres Dict, wenn aus oder nicht lesbar.

    Die Datei schreibt `market_analysis` (dort `export_market_values`). Sie ist die
    EINZIGE Verbindung zwischen den beiden Teilprojekten, und zwar in genau eine
    Richtung: die Analyse weiss nichts vom Autoclicker, der Autoclicker importiert
    nichts aus der Analyse. Fehlt die Datei, laeuft alles wie vorher.
    """
    if not path:
        return {}
    try:
        st = os.stat(path)
    except OSError:
        return {}
    stamp = (st.st_mtime, st.st_size)
    entry = _marktwert_cache.get(path)
    if entry is not None and entry["stamp"] == stamp:
        return entry["values"]
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, IOError, OSError, UnicodeDecodeError) as e:
        logger.error(f"Marktwert-Datei nicht lesbar ({path}): {e}")
        return {}
    if not isinstance(raw, dict):
        logger.error(f"Marktwert-Datei ist kein Name->Wert-Objekt: {path}")
        return {}
    values = {}
    for name, value in raw.items():
        try:
            values[str(name)] = float(value)
        except (TypeError, ValueError):
            continue
    _marktwert_cache[path] = {"stamp": stamp, "values": values}
    return values


def _effective_priority(item, gespeichert: int, values: dict) -> float:
    """Wonach sortiert wird - kleiner gewinnt, wie bei der gespeicherten Prioritaet.

    Hat das Item einen Marktwert, zaehlt der (negiert, damit "wertvoller" = "kleiner").
    Hat es keinen, bleibt seine gesetzte Prioritaet stehen.

    Folge, die man kennen muss: **jedes Item mit Marktwert gewinnt gegen jedes ohne**,
    weil negative Zahlen unter allen Prioritaeten liegen. Das ist gewollt - ein
    gemessener Wert ist eine staerkere Aussage als eine von Hand getippte Zahl - aber
    es heisst auch, dass ein Item ohne Eintrag in der Wertetabelle nach hinten rutscht.
    Wer das nicht will, laesst `scan_market_value_file` leer.

    Die gespeicherte `item.priority` wird dabei NICHT ueberschrieben: items.json
    bleibt unberuehrt, die Sortierung gilt nur fuer diesen Lauf.
    """
    value = values.get(item.name)
    return -value if value is not None else float(gespeichert)


def _filter_scan_results(state: AutoClickerState, found_items: list, mode: str, debug: bool) -> list:
    """Filtert Scan-Treffer nach Modus (every / all / best) und Kategorie-Konflikt."""
    values = load_market_values(state.config.scan_market_value_file)
    if values:
        # Prioritaet fuer diesen Lauf ersetzen - die Liste traegt sie als drittes Element.
        found_items = [(slot, item, _effective_priority(item, prio, values))
                       for slot, item, prio in found_items]
        if debug:
            print(dbg(f"  → Sortierung nach Marktwert ({len(values)} Items bekannt)"))
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

    # WAS gefunden wurde, nicht nur DASS geklickt wurde: der Klick-Eintrag daneben
    # nennt nur Koordinaten. Ohne diese Zeile kann kein Auswerter je sagen, welches
    # Item wie oft kam — die Zahl steht dann nur als Summe in der Endstatistik.
    log_event(state, "item_found", detail=item.name,
              x=pos[0], y=pos[1],
              extra=f"kategorie={item.category or ''},prio={priority}")

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
