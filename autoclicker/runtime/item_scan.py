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
from typing import Optional
from dataclasses import dataclass

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
from ..utils import col, err, dbg, info, warn
from ..winapi import set_cursor_pos, get_screen_center, resolve_window
from .actions import safe_click, wait_while_paused
from .debug import is_log_debug

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

    is_item = isinstance(profile, ItemProfile)
    if template_root is None and state is not None and getattr(state, "active_sequence", None) is not None:
        from ..persistence.sequences import sequence_dir
        template_root = sequence_dir(state.active_sequence.name) / "templates"
    templates_list = (profile.template_names() if is_item
                 else ([profile.template] if profile.template else []))
    if templates_list:
        if is_item:
            # Ein Item wird nur mit einer fuer diesen Slot gelernten Variante
            # verglichen. Damit gibt es keine halbgültigen Resize-Ergebnisse.
            candidates = [name for name in templates_list
                           if template_size(name, template_root) == tuple(img.size)]
        else:
            # Boss-/Icon-Profile behalten ihr bisheriges Resize-Verhalten.
            candidates = templates_list

        if not candidates:
            template_ok = False
            template_score = 0.0
            template_info = f"für Slot {img.size[0]}×{img.size[1]} nicht gelernt"
        else:
            results_list = [
                match_template_in_image(
                    img, name, profile.min_confidence,
                    resize_template=not is_item,
                    report_size_mismatch=not is_item,
                    template_root=template_root,
                )
                for name in candidates
            ]
            match, confidence, _pos = max(results_list, key=lambda value: value[1])
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
        if templates_list:
            info_parts.append(template_info)
        if profile.marker_colors:
            info_parts.append(marker_info)

        if not info_parts:
            print(dbg(f"  → {profile.name}: kein Template/Marker definiert"))
        elif template_ok and marker_ok:
            print(dbg(f"  → {profile.name} {found_label} ({', '.join(info_parts)})"))
        else:
            print(dbg(f"  → {profile.name}: {', '.join(info_parts)}"))

    matched = template_ok and marker_ok and bool(templates_list or profile.marker_colors)
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


class ScanSession:
    """Was zwischen den Slots EINES Immediate-Durchgangs wiederverwendbar ist.

    Der Immediate-Modus ruft `execute_item_scan` je Slot auf — und jeder Aufruf
    parkte die Maus neu und nahm bei einer Fensterquelle das GANZE Fenster neu
    auf: bei 45 Slots 45 `PrintWindow`-Aufnahmen für einen Durchgang, in dem
    sich meist gar nichts bewegt hat. Bewegt hat sich nur nach einem KLICK etwas
    (das Spiel rückt auf, die Maus steht auf dem Item) — genau dann ruft der
    Durchgang `invalidate()`, und der nächste Slot sieht wieder frische Pixel.
    So bleibt die Semantik des Modus („scan → klick → scan") erhalten, und die
    Aufnahmen zählen nur noch die Klicks, nicht die Slots.
    """

    def __init__(self) -> None:
        self.parked = False
        self.window = None      # (Bild, Client-Rechteck) der letzten Aufnahme

    def invalidate(self) -> None:
        """Nach einem Klick: Maus neu parken, Fenster neu aufnehmen."""
        self.parked = False
        self.window = None


def execute_item_scan(state: AutoClickerState, scan_name: str, mode: str = SCAN_MODE_ALL,
                      slots_override: list = None, session: ScanSession = None,
                      report=None) -> list:
    """Führt einen Item-Scan aus und gibt Liste von (position, item, priority) zurück.

    slots_override: Nur diese Slots scannen, Reverse-Reihenfolge ignorieren.
                    Wird vom Immediate-Modus genutzt (ein Slot pro Aufruf).
    session:        Parkstand und Fensteraufnahme über mehrere Aufrufe hinweg
                    (Immediate-Modus); ohne Session gilt jeder Aufruf für sich.
    report:         Sammelt für den Live-Run (`_ScanReport` in steps.py): `seen`
                    bekommt je gescanntem Slot `(Slot, Item oder None, Ausschnitt)`
                    — auch was der Modus danach wegfiltert —, `frame` einmal je
                    Block den Bereich um alle Slots als Bild.

    Die Stufen: Config einfrieren (`_plan_scan`), Reihenfolge (`_slot_order`),
    Maus parken, Bildquelle (`_window_source` → `_slots_in_window`), dann je
    Slot Bild (`_slot_image`) und Treffer (`_best_item`), zuletzt der Filter
    nach Modus. Jede Stufe, die scheitern kann, meldet selbst und gibt None
    zurück — hier steht nur noch die Reihenfolge."""
    plan = _plan_scan(state, scan_name)
    if plan is None:
        return []
    slots_to_scan = _slot_order(plan, slots_override)
    debug = is_log_debug(state)
    _park_once(state, session)

    source = _window_source(state, scan_name, plan, session, debug)
    if source is None:
        return []
    window_image, window_rect = source
    if window_image is not None:
        slots_to_scan = _slots_in_window(
            scan_name, slots_to_scan, plan.window_reference or window_rect, window_rect)
        if slots_to_scan is None:
            return []

    if report is not None and report.frame is None:
        # EINMAL je Block und VOR dem ersten Slot: im Immediate-Modus ruft der
        # Block diese Funktion je Slot, und nach dem ersten Klick sähe das Bild
        # anders aus als das, was gescannt wurde. Die Maus ist schon geparkt.
        report.frame = _scan_frame(_frame_regions(
            plan.slots, plan.window_reference, window_rect), window_image, window_rect)

    found_items = _scan_slots(state, scan_name, plan, slots_to_scan, source, report, debug)
    if not found_items:
        return []
    return _filter_scan_results(state, found_items, mode, debug)


def _scan_slots(state: AutoClickerState, scan_name: str, plan: '_ScanPlan',
                slots: list, source: tuple, report, debug: bool) -> list:
    """Der Durchgang über die Slots: je Slot `(Slot, Item, Priorität)` für jeden Treffer.

    Zwischen zwei Desktop-Aufnahmen liegt `scan_slot_delay`; ein Fensterbild
    ist schon aufgenommen und braucht keine Pause.
    """
    window_image, window_rect = source
    found_items = []
    scan_delay = state.config.scan_slot_delay
    for idx, slot in enumerate(slots):
        if _scan_interrupted(state, scan_name):
            break
        if window_image is None and scan_delay > 0 and idx > 0:
            if state.stop_event.wait(scan_delay):
                break

        img = _slot_image(slot, window_image, window_rect, debug)
        if img is None:
            continue
        item = _best_item(state, plan.items, img, plan.color_tolerance, debug)
        if item is not None:
            found_items.append((slot, item, item.priority))
        if report is not None:
            report.seen.append((slot, item, img))
        if item is None and plan.learn_unknown:
            _learn_unknown_slot_item(state, slot, img, debug, plan.config)
    return found_items


@dataclass
class _ScanPlan:
    """Was ein Durchgang aus der Config braucht — unter EINEM Lock eingefroren.

    Snapshot statt Live-Zugriff: ein Editor kann die Listen während des
    Durchgangs ändern (RuntimeError bei „list changed during iteration"), und
    wer ein Flag zweimal frisch liest, kann ihn dazwischen umschalten sehen.
    """
    config: object                   # die Config selbst — Auto-Lernen schreibt hinein
    slots: list                      # eingeschaltete Slots, gespeicherte Reihenfolge
    items: list                      # eingeschaltete Items
    color_tolerance: int
    learn_unknown: bool
    backwards: bool
    window_title: str | None
    window_index: int
    window_reference: tuple | None   # Fensterlage, in der die Slots vermessen wurden


def _plan_scan(state: AutoClickerState, scan_name: str) -> _ScanPlan | None:
    """Der eingefrorene Stand des Scans, oder None (gemeldet), wenn er nicht laufen kann."""
    with state.lock:
        config = runnable_scan_config(state, scan_name)
        if config is None:
            return None
        return _ScanPlan(
            config=config,
            slots=[slot for slot in config.slots if slot.enabled],
            items=[item for item in config.items if item.enabled],
            color_tolerance=config.color_tolerance,
            learn_unknown=config.learn_unknown,
            backwards=config.reverse,
            window_title=config.capture_window_title,
            window_index=config.capture_window_index,
            window_reference=(tuple(config.capture_window_rect)
                              if config.capture_window_rect else None),
        )


def _slot_order(plan: _ScanPlan, slots_override: list | None) -> list:
    """Welche Slots in welcher Reihenfolge — ein Override gilt wie übergeben."""
    if slots_override is not None:
        return [slot for slot in slots_override if slot.enabled]
    return list(reversed(plan.slots)) if plan.backwards else plan.slots


def _park_once(state: AutoClickerState, session: ScanSession | None) -> None:
    """Maus parken — im Immediate-Modus nur bis zum nächsten Klick einmal."""
    if session is None or not session.parked:
        _park_mouse_for_scan(state.config.scan_park_mouse)
        if session is not None:
            session.parked = True


def _window_source(state: AutoClickerState, scan_name: str, plan: _ScanPlan,
                   session: ScanSession | None, debug: bool):
    """Woher die Pixel kommen: `(Bild, Client-Rechteck)` des Fensters.

    `(None, None)` heisst Desktop (kein Fenster gewählt), None heisst Fehler —
    schon gemeldet, der Scan endet. Ein Fenster-Scan arbeitet auf EINEM
    eingefrorenen Bild, genau wie der Editor: Items können sich nicht mitten im
    Durchgang verschieben, und beide Wege sehen dieselben Pixel aus derselben
    Aufnahmemethode.
    """
    title = plan.window_title
    if not title:
        return None, None
    if session is not None and session.window is not None:
        # Immediate-Modus, seit der letzten Aufnahme kein Klick: dieselben Pixel.
        return session.window
    window = resolve_window(title, plan.window_index, plan.window_reference)
    if window is None:
        print(err(f"Item-Scan '{scan_name}': Fenster '{title}' nicht "
                  "gefunden. Spiel öffnen oder die Aufnahmequelle im Studio "
                  "neu wählen."))
        return None
    started = time.time()
    capture = take_consistent_window_screenshot(window[2])
    if capture is None:
        print(err(f"Item-Scan '{scan_name}': Fenster '{title}' konnte "
                  "nicht aufgenommen werden."))
        return None
    image, rect, hint = capture
    if hint and (scan_name, hint) not in _window_capture_warnings:
        _window_capture_warnings.add((scan_name, hint))
        print(warn(f"Item-Scan '{scan_name}':{hint}"))
    if debug:
        print(dbg(f"Fenster '{title}' einmal aufgenommen: "
                  f"{image.size[0]}x{image.size[1]}px "
                  f"in {(time.time() - started) * 1000:.0f}ms"))
    if session is not None:
        session.window = (image, rect)
    return image, rect


def _slots_in_window(scan_name: str, slots: list, reference, window_rect) -> list | None:
    """Die Slots auf die heutige Fensterlage umgerechnet — Klickpunkt inklusive.

    None (gemeldet), wenn die gespeicherte Geometrie keine Fläche hat.
    """
    try:
        return [ItemSlot(
            name=slot.name,
            scan_region=map_region_between_rects(slot.scan_region, reference, window_rect),
            click_pos=map_point_between_rects(slot.click_pos, reference, window_rect),
            slot_color=slot.slot_color,
            enabled=slot.enabled,
            id=slot.id,
        ) for slot in slots]
    except (TypeError, ValueError):
        print(err(f"Item-Scan '{scan_name}': gespeicherte Fenstergeometrie ist "
                  "ungültig. Aufnahmequelle im Studio neu wählen."))
        return None


def _scan_interrupted(state: AutoClickerState, scan_name: str) -> bool:
    """True, wenn der Durchgang vor dem nächsten Slot enden muss."""
    if state.stop_event.is_set():
        return True
    if state.skip_event.is_set():
        # Skip konsumieren — sonst überspringt ein Skip zwei Dinge
        # (diesen Scan und den nächsten skip-fähigen Schritt).
        state.skip_event.clear()
        return True
    if state.skip_step_event.is_set():
        # NICHT verbrauchen: der Block-Skip gehoert dem Dispatcher. Hier
        # geleert, klickte der normale Modus die bis dahin gefundenen Items
        # trotzdem, und im Immediate-Modus (ein Aufruf je Slot) fiel nur
        # EIN Slot weg — der Rest des Blocks lief weiter.
        return True
    return not wait_while_paused(state, f"Scan '{scan_name}' pausiert...")


def _slot_image(slot, window_image, window_rect, debug: bool):
    """Der Ausschnitt eines Slots: aus dem Fensterbild oder als eigene Aufnahme."""
    started = time.time()
    if window_image is not None:
        img = crop_screen_region(window_image, slot.scan_region,
                                 (window_rect[0], window_rect[1]))
    else:
        img = take_screenshot(slot.scan_region)
    if img is not None and debug:
        print(dbg(f"Scanne {slot.name}... (Screenshot: "
                  f"{(time.time() - started) * 1000:.0f}ms, "
                  f"{img.size[0]}x{img.size[1]}px)"))
    return img


def _best_item(state: AutoClickerState, items: list, img, color_tolerance: int,
               debug: bool):
    """Das Item, das am besten passt, oder None.

    Gewertet wird die Trefferqualität aus `_check_profile_match`; bei gleicher
    Qualität gewinnt das Item, das in der Liste weiter vorn steht.
    """
    candidates = []
    for order, item in enumerate(items):
        fits, quality = _check_profile_match(
            item, img, color_tolerance, state, debug, "gefunden!", return_score=True)
        if fits:
            candidates.append((quality, -order, item))
    if not candidates:
        return None
    quality, _neg_order, best = max(candidates, key=lambda c: (c[0], c[1]))
    if debug and len(candidates) > 1:
        print(dbg(f"  → {best.name}: bester von {len(candidates)} Treffern "
                  f"({quality:.1%})"))
    return best


# Rand um die Slots im Bild des letzten Scans: ohne ihn stösst der äusserste
# Rahmen an die Bildkante, und man sieht nicht, wo das Inventar aufhört.
FRAME_MARGIN = 12


def _frame_regions(slots: list, reference, window_rect) -> list:
    """Die Regionen aller Slots in Bildschirm-Koordinaten — im Fenster-Modus
    auf die heutige Fensterlage umgerechnet, wie beim Scannen selbst."""
    if window_rect is None:
        return [slot.scan_region for slot in slots]
    reference = reference or window_rect
    try:
        return [map_region_between_rects(slot.scan_region, reference, window_rect)
                for slot in slots]
    except (TypeError, ValueError):
        return []


def _scan_frame(regions: list, window_image, window_rect):
    """Der Bereich um alle Slots als ein Bild — `(Bild, (l, o, r, u))` oder None.

    Kein Beiwerk zum Scan, sondern das, was der Nutzer beim Hinsehen erwartet:
    ein echter Screenshot der Stelle. Im Fenster-Modus aus der Fensteraufnahme
    (die gibt es ohnehin), sonst eine Aufnahme mehr — ein kleiner Ausschnitt,
    wenige Millisekunden. Schlägt sie fehl, setzt `_scan_picture` die
    Slot-Ausschnitte zusammen.
    """
    if not regions:
        return None
    left = min(r[0] for r in regions) - FRAME_MARGIN
    top = min(r[1] for r in regions) - FRAME_MARGIN
    right = max(r[2] for r in regions) + FRAME_MARGIN
    bottom = max(r[3] for r in regions) + FRAME_MARGIN
    if window_image is not None and window_rect is not None:
        wl, wt = int(window_rect[0]), int(window_rect[1])
        left, top = max(left, wl), max(top, wt)
        right = min(right, wl + window_image.size[0])
        bottom = min(bottom, wt + window_image.size[1])
        if right <= left or bottom <= top:
            return None
        return (window_image.crop((left - wl, top - wt, right - wl, bottom - wt)),
                (left, top, right, bottom))
    image = take_screenshot((left, top, right, bottom))
    return None if image is None else (image, (left, top, right, bottom))


def _learn_unknown_slot_item(state: AutoClickerState, slot, img, debug: bool,
                             config=None) -> None:
    """Lernt einen unbekannten Slot-Inhalt als neues Item des LAUFENDEN Scans (opt-in).

    **In den Scan, der gerade laeuft — nicht in die Arbeitsansicht der Konsole.**
    Hier stand `state.global_items`, und das ist seit dem Umzug auf
    Besitzeinheiten nur noch die Ansicht auf `state.active_item_scan`, also den
    Scan, den der Konsolen-Editor zuletzt offen hatte. Mit zwei Item-Scans in
    einer Sequenz landete ein aus Scan B gelerntes Item damit in Scan A — samt
    Dedup gegen die falsche Liste —, und ohne offenen Scan meldete jeder Zyklus
    „Kein Item-Scan zum Speichern gewaehlt".

    **Gelernt heisst geparkt** (`enabled=False`): das Item steht im Scan, wird
    im Studio gezeigt und laesst sich dort einschalten — geklickt wird es erst
    dann. Das ist das „wird NICHT geklickt", das die Zeit des globalen Bestands
    versprach; dort lag das Item ausserhalb jedes Scans, heute gibt es dieses
    Ausserhalb nicht mehr.

    **Und das gilt fuer JEDE Vorlage, nicht nur fuer neue Items.** Findet die
    Dedup-Pruefung ein bekanntes Item nur ueber eine skalierte Vorlage (anderer
    Slot-Typ), wurde die neue Groesse als Variante an dieses Item gehaengt — und
    war es eingeschaltet, klickte der naechste Zyklus sie ungeprueft. Genau das
    Ergebnis, das `_check_profile_match()` fuer Items ausdruecklich verweigert
    („keine halbgueltigen Resize-Ergebnisse"). An ein EINGESCHALTETES Item wird
    deshalb nichts gehaengt; die Vorlage wird ein eigenes, geparktes Item, und
    die Meldung nennt, wem es aehnelt. Zusammenlegen ist dann eine Entscheidung
    im Studio („Namen vorschlagen" haengt ein gleichnamiges Doppel als Variante
    an). An ein GEPARKTES Item darf die Variante direkt — es wird ja ohnehin
    erst nach dem Hinsehen eingeschaltet.

    **Auto-Lernen aendert also nie, was geklickt wird.**

    Dedup per Template-Matching gegen alle Items des Scans (auch geparkte);
    Slots, die nur die Hintergrundfarbe zeigen, gelten als leer.
    """
    from ..imaging import OPENCV_AVAILABLE
    if not OPENCV_AVAILABLE or config is None:
        return
    # Editor-Helfer lazy importieren (markers.py hängt nur an imaging/config,
    # kein Import-Zyklus mit runtime/)
    from ..editors.item_editor.markers import _prepare_learning_image
    from ..persistence import active_templates_dir

    # Dieselbe Leer-Regel wie im Studio: komplett ausmaskiert = kein Item.
    masked, marker_colors, is_blank = _prepare_learning_image(img, slot.slot_color)
    if is_blank:
        if debug:
            print(dbg(f"  → {slot.name}: leer (nur Hintergrund bzw. kein Slot zu sehen) — kein Auto-Lernen"))
        return

    # **Der Vorlagenordner MUSS mit.** Ohne ihn faellt `_template_path()` auf den
    # globalen `items/templates/` zurueck, den es seit dem Umzug auf
    # Besitzeinheiten nicht mehr gibt: `template_size()` liefert dann fuer JEDE
    # Vorlage None, die Dedup-Pruefung findet nie einen Treffer - und
    # `learn_unknown` legt denselben Slot in jedem Zyklus erneut als neues Item
    # an. Vier Zeilen tiefer stand der richtige Ordner laengst da.
    templates_folder = active_templates_dir(state)
    done, resembles = _learn_against_known(state, slot, img, masked, config,
                                           templates_folder, debug)
    if done:
        return
    item = _reserve_learned_item(state, config, slot, marker_colors, templates_folder)
    if not _store_learned_template(state, config, item, masked, templates_folder):
        return

    _save_learned(config)
    print(col(f"[AUTO-LERNEN] Neues Item '{item.name}' aus {slot.name} in Scan "
              f"'{config.name}' geparkt (Kategorie 'Auto', aus — im Studio "
              "einschalten)", "green"))
    if resembles:
        width, height = img.size
        print(info(f"Ähnelt '{resembles}' (dort keine {width}×{height}-Vorlage) — "
                   f"nicht angehängt, weil '{resembles}' eingeschaltet ist und "
                   "sonst ungeprüft geklickt würde. Im Studio ansehen, dann "
                   "einschalten oder löschen."))


def _learn_against_known(state: AutoClickerState, slot, img, masked, config,
                         templates_folder, debug: bool) -> tuple[bool, Optional[str]]:
    """Dedup gegen die Items DIESES Scans (auch geparkte, z.B. in einem früheren
    Zyklus gelernte). `(erledigt, ähnelt)`: erledigt = bekannt bzw. als Variante
    an ein geparktes Item gehängt; ähnelt = ein eingeschaltetes Item, das nur
    über eine skalierte Vorlage passt — dann wird ein eigenes Item gelernt."""
    from ..editors.item_editor.markers import (
        _find_matching_existing_item, _item_has_compatible_template,
    )
    with state.lock:
        existing = [(it.name, it) for it in config.items if it.template_names()]
    known = _find_matching_existing_item(img, existing, state.config.scan_min_confidence,
                                         templates_folder)
    if not known:
        return False, None
    known_item = next((it for name, it in existing if name == known), None)
    needs_variant = known_item is not None and not _item_has_compatible_template(
        known_item, img, templates_folder)
    if not needs_variant:
        if debug:
            print(dbg(f"  → {slot.name}: bekannt als '{known}' — kein Auto-Lernen"))
        return True, None
    with state.lock:
        known_active = known_item.enabled
    if known_active:
        # Nur ueber eine skalierte Vorlage erkannt — ungeprueft an ein
        # Item gehaengt, das geklickt wird, waere es sofort scharf.
        return False, known
    _add_learned_variant(state, config, known_item, img, masked, templates_folder)
    return True, None


def _add_learned_variant(state: AutoClickerState, config, known_item, img, masked,
                         templates_folder) -> None:
    """Eine neue Grössenvariante an ein GEPARKTES Item hängen — es wird ohnehin
    erst nach dem Hinsehen eingeschaltet."""
    from ..persistence import free_template_file
    width, height = img.size
    template_file = free_template_file(templates_folder, f"{known_item.name}_{width}x{height}")
    template_path = templates_folder / template_file
    try:
        template_path.parent.mkdir(parents=True, exist_ok=True)
        masked.save(template_path)
    except (OSError, ValueError) as e:
        print(warn(f"Auto-Lernen: Vorlage für '{known_item.name}' konnte nicht "
                   f"gespeichert werden: {e}"))
        return
    with state.lock:
        if template_file not in known_item.template_variants:
            known_item.template_variants.append(template_file)
    _save_learned(config)
    print(col(f"[AUTO-LERNEN] '{known_item.name}' (geparkt) kann jetzt auch in "
              f"{width}×{height}-Slots erkannt werden", "green"))


def _reserve_learned_item(state: AutoClickerState, config, slot, marker_colors,
                          templates_folder) -> ItemProfile:
    """Das neue Item unter einem freien Namen anlegen und sofort reservieren.

    Schnellen Namen vergeben — KEIN LLM während des Scans (würde den Worker
    pro Item bis zu llm_timeout Sekunden blockieren). Sinnvolle Namen vergibt
    man danach im Studio („Namen vorschlagen") oder im Item-Editor ('autoname').
    Eindeutig vergeben + sofort reservieren (Worker/Editor-Race).
    """
    from ..persistence import free_template_file
    base = f"Auto {slot.name}"
    item = ItemProfile(
        name="", marker_colors=marker_colors, category="Auto",
        priority=99, template=None, min_confidence=state.config.scan_min_confidence,
        enabled=False,
    )
    with state.lock:
        taken = {it.name for it in config.items}
        name = base
        counter = 1
        while name in taken:
            counter += 1
            name = f"{base} {counter}"
        item.name = name
        # Das Objekt wird ab hier für Editor und Worker sichtbar. Deshalb muss
        # es schon vollständig initialisiert sein; insbesondere darf
        # ``template`` nicht erst ausserhalb des Locks gesetzt werden.
        # Frei auf der PLATTE, nicht nur im Namen: ein umbenanntes Item behält
        # seine Vorlage `auto_slot_19_2.png`, und „Auto Slot 19 2" ist dann
        # wieder frei — die Datei aber nicht (s. `free_template_file`).
        item.template = free_template_file(templates_folder, name)
        config.items.append(item)
        # Die Konsolen-Arbeitsansicht zeigt auf denselben Scan? Dann muss sie
        # das Item auch sehen — sonst schriebe ihr naechstes `done` die Liste
        # ohne das Item zurueck (flush_item_scan_context ersetzt cfg.items).
        if state.active_item_scan == config.name:
            state.global_items[name] = item
    return item


def _store_learned_template(state: AutoClickerState, config, item, masked,
                            templates_folder) -> bool:
    """Die Vorlage schreiben; scheitert das, verschwindet das reservierte Item wieder."""
    template_path = templates_folder / item.template
    try:
        template_path.parent.mkdir(parents=True, exist_ok=True)
        masked.save(template_path)
        return True
    except (OSError, ValueError) as e:
        with state.lock:
            config.items = [it for it in config.items if it is not item]
            if state.active_item_scan == config.name:
                state.global_items.pop(item.name, None)
        print(warn(f"Auto-Lernen: Template für '{item.name}' konnte nicht gespeichert werden: {e}"))
        return False


def _save_learned(config) -> bool:
    """Schreibt den Scan nach dem Lernen — ein Fehler bremst den Lauf nicht.

    `save_item_scan` wirft ohne Besitzer-Sequenz; im Worker riss das sonst den
    ganzen Lauf ab, wegen eines Items, das nur nebenbei gelernt wurde.
    """
    from ..persistence import save_item_scan
    try:
        return bool(save_item_scan(config))
    except (ValueError, OSError) as e:
        print(warn(f"Auto-Lernen: Scan '{config.name}' konnte nicht gespeichert werden: {e}"))
        return False


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


def _effective_priority(item, saved: int, values: dict) -> float:
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
    return -value if value is not None else float(saved)


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

    filtered_items = _best_per_category(state, found_items, debug)
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


def _best_per_category(state: AutoClickerState, found_items: list, debug: bool) -> list:
    """Je Kategorie der Treffer mit der kleinsten Priorität, in Scan-Reihenfolge.

    Eine Kategorie, in der dieser Zyklus schon etwas mindestens so Gutes
    geklickt hat, fällt ganz weg.
    """
    best_per_category = {}
    for slot, item, priority in found_items:
        cat = item.category or item.name
        with state.lock:
            best_clicked = state.clicked_categories.get(cat)
        if best_clicked is not None and priority >= best_clicked:
            if debug:
                print(dbg(f"  → {item.name} übersprungen ('{cat}' bereits geklickt)"))
            continue
        # Ein dict behält die Einfügereihenfolge — die Kategorie bleibt an der
        # Stelle ihres ersten Treffers, auch wenn ein besserer sie ersetzt.
        if cat not in best_per_category or priority < best_per_category[cat][2]:
            best_per_category[cat] = (slot, item, priority)
    return list(best_per_category.values())


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

    if item.confirm_point is not None and not _confirm_click(state, item, debug):
        return False
    click_delay = state.config.scan_item_click_delay
    return not (click_delay > 0 and state.stop_event.wait(click_delay))


def _confirm_click(state: AutoClickerState, item, debug: bool) -> bool:
    """Der Klick DANACH (z.B. „wirklich verkaufen?"). False = gestoppt/verweigert."""
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
    return True
