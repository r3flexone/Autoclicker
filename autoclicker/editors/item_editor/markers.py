"""
Marker-Farben-Sammlung und Template-Duplikat-Erkennung.

collect_marker_colors: interaktive Variante mit Region-Selektion und Konsolen-Output.
_collect_markers_silent: für den Auto-Scan — keine User-Interaktion, keine Ausgabe.
_find_matching_existing_item: prüft ob ein neu gescanntes Bild schon als Item existiert.
"""

from typing import TYPE_CHECKING

from ...config import CONFIG
from ...imaging import (
    OPENCV_AVAILABLE, take_screenshot, select_region,
    get_color_name, color_distance,
)

if TYPE_CHECKING:
    from PIL import Image


def collect_marker_colors(region: tuple = None, exclude_color: tuple = None) -> list[tuple]:
    """Sammelt Marker-Farben für ein Item-Profil durch Region-Scan."""
    if not region:
        print("\n  Wähle einen Bereich auf dem Item aus:")
        print("  (Die 5 häufigsten Farben werden automatisch genommen)")
        region = select_region()
        if not region:
            return []

    print(f"\n  Scanne Region ({region[0]},{region[1]}) - ({region[2]},{region[3]})...")
    img = take_screenshot(region)
    if img is None:
        print("  -> Fehler beim Screenshot!")
        return []

    color_counts = rounded_color_counts(img)
    if exclude_color:
        _drop_background(color_counts, exclude_color)

    # Top N häufigste Farben (aus Config)
    marker_count = CONFIG.scan_marker_count
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:marker_count]
    colors = [color for color, count in sorted_colors]

    print(f"\n  Top {marker_count} Farben gefunden:")
    for i, (color, count) in enumerate(sorted_colors):
        color_name = get_color_name(color)
        print(f"    {i+1}. RGB{color} - {color_name} ({count} Pixel)")

    return colors


def _rounded(color) -> tuple:
    """Auf 5er-Stufen gerundet — so fallen ähnliche Farben zusammen."""
    return (color[0] // 5 * 5, color[1] // 5 * 5, color[2] // 5 * 5)


def rounded_color_counts(img) -> dict:
    """Wie oft jede (gerundete) Farbe im Bild vorkommt.

    Geteilt mit dem Slot-Editor, der beim Anlegen die häufigsten Farben zeigt —
    dieselbe Zählung stand dort ein zweites Mal.
    """
    color_counts = {}
    pixels = img.load()
    width, height = img.size
    for x in range(width):
        for y in range(height):
            rounded = _rounded(pixels[x, y][:3])
            color_counts[rounded] = color_counts.get(rounded, 0) + 1
    return color_counts


def _drop_background(color_counts: dict, exclude_color: tuple) -> None:
    """Nimmt alle Farbtöne nahe der Slot-Hintergrundfarbe heraus und sagt, wie viele."""
    exclude_rounded = _rounded(exclude_color)
    slot_color_dist = CONFIG.scan_slot_color_distance
    colors_to_remove = [color for color in color_counts
                        if color_distance(color, exclude_rounded) <= slot_color_dist]
    total_excluded = sum(color_counts.pop(color) for color in colors_to_remove)
    if total_excluded > 0:
        color_name = get_color_name(exclude_color)
        print(f"  -> Slot-Hintergrund ~RGB{exclude_color} ({color_name}) ausgeschlossen "
              f"({total_excluded} Pixel, {len(colors_to_remove)} Farbtöne)")


def _collect_markers_silent(img: 'Image.Image', slot_color: tuple = None) -> list[tuple]:
    """Sammelt Marker-Farben aus einem PIL-Bild ohne Benutzer-Interaktion.

    **Traegt das Bild eine Maske (RGBA), gilt sie.** Dann ist der Hintergrund
    schon entschieden - dieselbe Entscheidung wie beim Template, und nicht eine
    zweite daneben. Der Unterschied ist nicht nur Kosmetik: die Farbregel unten
    vergleicht GERUNDETE Farben (//5), die Maske die echten. An der Grenze
    kommen dabei verschiedene Ergebnisse heraus.
    """
    color_counts = {}
    masked = img.mode == "RGBA"
    pixels = img.load()
    width, height = img.size

    for x in range(width):
        for y in range(height):
            raw = pixels[x, y]
            if masked and len(raw) > 3 and raw[3] <= 127:
                continue                      # Hintergrund, schon ausmaskiert
            pixel = raw[:3]
            rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
            color_counts[rounded] = color_counts.get(rounded, 0) + 1

    if slot_color and not masked:
        exclude_rounded = (slot_color[0] // 5 * 5, slot_color[1] // 5 * 5, slot_color[2] // 5 * 5)
        slot_color_dist = CONFIG.scan_slot_color_distance
        colors_to_remove = [c for c in color_counts if color_distance(c, exclude_rounded) <= slot_color_dist]
        for color in colors_to_remove:
            del color_counts[color]

    marker_count = CONFIG.scan_marker_count
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:marker_count]
    return [color for color, count in sorted_colors]


def _prepare_learning_image(img: 'Image.Image', slot_color: tuple = None):
    """Maskiertes Lernbild, Marker und die gemeinsame Leer-Entscheidung.

    Studio und Laufzeit duerfen einen leeren Slot nicht unterschiedlich
    beurteilen: Sonst bietet die Vorschau ein Item an, das Auto-Lernen spaeter
    ueberspringt. Ohne gemessene Slot-Farbe ist keine sichere Leer-Erkennung
    moeglich; dann bleibt das Bild bewusst lernbar.

    **Leer heisst auch: der Slot ist gar nicht da.** Manche Ansichten zeichnen
    einen Slot nur, solange ein Item darin liegt — ohne Item steht an der
    Stelle der Spielhintergrund, und die Regel „nur Slotfarbe, keine Marker"
    griff nie, denn dort ist GAR KEINE Slotfarbe. An einem echten Bestand
    lernte das Auto-Lernen so sechs dunkle Hintergründe und drei
    abgeschnittene Ausschnitte (zu viele Items, die Reihe verrutscht) als
    „Items". Gemessen am Rand (`_slot_visible`): echte Items zeigen dort
    mindestens 64 % Slotfarbe — auch Edelsteine, die den Slot sonst füllen —,
    die neun Fehlgriffe höchstens 13 %.
    """
    from ...imaging import with_background_mask

    masked = with_background_mask(img, slot_color)
    marker = _collect_markers_silent(masked, slot_color)
    empty = bool(slot_color) and (not marker or not _slot_visible(img, slot_color))
    return masked, marker, empty


# Wie nah ein Randpixel an der Slotfarbe liegen muss und wie viel vom Rand
# sie zeigen muss, damit an der Stelle ein Slot zu sehen ist. Gemessen: echte
# Items >= 64 %, Hintergrund und abgeschnittene Ausschnitte <= 13 %.
SLOT_RIM = 3
SLOT_RIM_DISTANCE = 45
SLOT_RIM_SHARE = 0.4


def _slot_visible(img: 'Image.Image', slot_color: tuple) -> bool:
    """Zeigt der Rand des Ausschnitts die Slotfarbe — ist dort ein Slot?

    Ohne Slotfarbe oder bei einem Winzling ohne echten Rand lässt sich das
    nicht sagen; dann gilt der Slot als sichtbar (lieber ein Item zu viel
    anbieten als ein echtes verschweigen).
    """
    if img is None or not slot_color:
        return True
    rgb = img.convert("RGB")
    width, height = rgb.size
    if width <= 2 * SLOT_RIM + 2 or height <= 2 * SLOT_RIM + 2:
        return True
    pixel = rgb.load()
    hr, hg, hb = slot_color[:3]
    limit = SLOT_RIM_DISTANCE ** 2
    total = near = 0
    for y in range(height):
        inner_row = SLOT_RIM <= y < height - SLOT_RIM
        for x in range(width):
            if inner_row and SLOT_RIM <= x < width - SLOT_RIM:
                continue
            r, g, b = pixel[x, y]
            total += 1
            if (r - hr) ** 2 + (g - hg) ** 2 + (b - hb) ** 2 <= limit:
                near += 1
    return near >= SLOT_RIM_SHARE * total


def _find_matching_existing_item(img: 'Image.Image', existing_items: list,
                                  min_confidence: float,
                                  template_root=None) -> str | None:
    """Vergleicht ein Slot-Bild gegen alle bestehenden Item-Templates.

    Args:
        img: PIL Image des aktuellen Slots
        existing_items: Liste von (name, ItemProfile) Tupeln mit Templates
        min_confidence: Mindest-Konfidenz für einen Match

    Returns:
        Name des gematchten Items oder None wenn kein Duplikat.
    """
    if not OPENCV_AVAILABLE or not existing_items:
        return None

    from ...imaging import match_template_in_image, template_size

    # Eine echte Vorlage derselben Slot-Groesse ist aussagekraeftiger als eine
    # hoch-/herunterskalierte. Erst wenn keine davon passt, darf die zweite Runde
    # ein Item aus einem anderen Slot-Typ als moegliche Identitaet erkennen.
    for same_size in (True, False):
        best_name = None
        best_confidence = -1.0
        for name, item in existing_items:
            templates_list = (item.template_names() if hasattr(item, "template_names")
                         else ([item.template] if item.template else []))
            for template_value in templates_list:
                size_fits = template_size(template_value, template_root) == tuple(img.size)
                if size_fits != same_size:
                    continue
                match, confidence, _pos = match_template_in_image(
                    img, template_value, min_confidence,
                    resize_template=not same_size,
                    report_size_mismatch=False,
                    template_root=template_root,
                )
                if match and confidence > best_confidence:
                    best_name, best_confidence = name, confidence
        if best_name is not None:
            return best_name

    return None


def _item_has_compatible_template(item, img: 'Image.Image', template_root=None) -> bool:
    """Hat das Item bereits eine Vorlage exakt fuer diese Slot-Groesse?"""
    from ...imaging import template_size
    templates_list = (item.template_names() if hasattr(item, "template_names")
                 else ([item.template] if item.template else []))
    return any(template_size(template_value, template_root) == tuple(img.size)
               for template_value in templates_list)
