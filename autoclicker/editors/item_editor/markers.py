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

    # Farben zählen (mit Rundung für Gruppierung)
    color_counts = {}
    pixels = img.load()
    width, height = img.size

    for x in range(width):
        for y in range(height):
            pixel = pixels[x, y][:3]
            # Runde auf 5er-Schritte für Gruppierung ähnlicher Farben
            rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
            color_counts[rounded] = color_counts.get(rounded, 0) + 1

    # Slot-Hintergrundfarbe ausschliessen (falls vorhanden)
    if exclude_color:
        exclude_rounded = (exclude_color[0] // 5 * 5, exclude_color[1] // 5 * 5, exclude_color[2] // 5 * 5)

        slot_color_dist = CONFIG.scan_slot_color_distance
        colors_to_remove = []
        for color in color_counts.keys():
            if color_distance(color, exclude_rounded) <= slot_color_dist:
                colors_to_remove.append(color)

        total_excluded = 0
        for color in colors_to_remove:
            total_excluded += color_counts.pop(color)

        if total_excluded > 0:
            color_name = get_color_name(exclude_color)
            print(f"  -> Slot-Hintergrund ~RGB{exclude_color} ({color_name}) ausgeschlossen ({total_excluded} Pixel, {len(colors_to_remove)} Farbtöne)")

    # Top N häufigste Farben (aus Config)
    marker_count = CONFIG.scan_marker_count
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:marker_count]
    colors = [color for color, count in sorted_colors]

    print(f"\n  Top {marker_count} Farben gefunden:")
    for i, (color, count) in enumerate(sorted_colors):
        color_name = get_color_name(color)
        print(f"    {i+1}. RGB{color} - {color_name} ({count} Pixel)")

    return colors


def _collect_markers_silent(img: 'Image.Image', slot_color: tuple = None) -> list[tuple]:
    """Sammelt Marker-Farben aus einem PIL-Bild ohne Benutzer-Interaktion.

    **Traegt das Bild eine Maske (RGBA), gilt sie.** Dann ist der Hintergrund
    schon entschieden - dieselbe Entscheidung wie beim Template, und nicht eine
    zweite daneben. Der Unterschied ist nicht nur Kosmetik: die Farbregel unten
    vergleicht GERUNDETE Farben (//5), die Maske die echten. An der Grenze
    kommen dabei verschiedene Ergebnisse heraus.
    """
    color_counts = {}
    maskiert = img.mode == "RGBA"
    pixels = img.load()
    width, height = img.size

    for x in range(width):
        for y in range(height):
            roh = pixels[x, y]
            if maskiert and len(roh) > 3 and roh[3] <= 127:
                continue                      # Hintergrund, schon ausmaskiert
            pixel = roh[:3]
            rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
            color_counts[rounded] = color_counts.get(rounded, 0) + 1

    if slot_color and not maskiert:
        exclude_rounded = (slot_color[0] // 5 * 5, slot_color[1] // 5 * 5, slot_color[2] // 5 * 5)
        slot_color_dist = CONFIG.scan_slot_color_distance
        colors_to_remove = [c for c in color_counts if color_distance(c, exclude_rounded) <= slot_color_dist]
        for color in colors_to_remove:
            del color_counts[color]

    marker_count = CONFIG.scan_marker_count
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:marker_count]
    return [color for color, count in sorted_colors]


def _find_matching_existing_item(img: 'Image.Image', existing_items: list,
                                  min_confidence: float) -> str | None:
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

    from ...imaging import match_template_in_image

    for name, item in existing_items:
        if not item.template:
            continue

        match, confidence, pos = match_template_in_image(
            img, item.template, min_confidence
        )
        if match:
            return name

    return None
