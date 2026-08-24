"""
GUI-freier Modell-Layer für Namen, Geometrie und lokale Templates.

Slots und Items gehören vollständig dem geöffneten Item-Scan und werden mit
dessen JSON gespeichert. Dieses Modul enthält deshalb bewusst keinen zweiten
Datei-Zugriff auf einen globalen Bestand.

Lag bis zum Umbau unter `editors/scan_canvas/` neben dem Dear-PyGui-Fenster.
Das Fenster ist weg — der Modell-Layer nicht: er war von Anfang an ohne GUI
geschrieben und wird jetzt vom Scans-Reiter des Sequenz-Studios benutzt
(`scans.py`).
"""

from pathlib import Path

from ...models import ItemSlot, ItemProfile
from ...utils import sanitize_filename, naechster_freier_name
from ..scan_services import crop_screen_region


def next_slot_name(slots: dict[str, ItemSlot]) -> str:
    """Liefert einen freien Standard-Slotnamen ('Slot 1', 'Slot 2', ...)."""
    return naechster_freier_name("Slot", slots)


def normalize_region(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int, int]:
    """Sortiert die Ecken, sodass (links, oben, rechts, unten) gilt."""
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


# =============================================================================
# ITEMS
# =============================================================================

def next_item_name(items: dict[str, ItemProfile]) -> str:
    """Liefert einen freien Standard-Itemnamen ('Item 1', 'Item 2', ...)."""
    return naechster_freier_name("Item", items)


def existing_categories(items: dict[str, ItemProfile]) -> list[str]:
    """Alle vorkommenden Kategorien (sortiert, ohne None)."""
    return sorted({i.category for i in items.values() if i.category})


def crop_region(full_img, region: tuple[int, int, int, int],
                virtual_left: int, virtual_top: int):
    """Schneidet die Slot-Region (Bildschirm-Koordinaten) aus dem Vollbild-Screenshot."""
    return crop_screen_region(full_img, region, (virtual_left, virtual_top))


def save_template(img, name: str, hintergrund=None, *, template_dir) -> str | None:
    """Speichert ein Bild im Template-Ordner der Sequenz. Gibt den Dateinamen zurück.

    Items und Bosse der Sequenz teilen sich diesen Ordner. Existiert die
    Zieldatei bereits (z.B. Boss 'X' nach Item 'X'), wird ein nummeriertes
    Suffix (_2, _3, ...) gewaehlt, statt das fremde Template zu ueberschreiben.
    Der tatsaechlich verwendete Dateiname wird zurueckgegeben, damit die Config
    konsistent darauf verweist.
    """
    if img is None:
        return None
    # Mit bekanntem Hintergrund traegt das Template seine Maske selbst: der
    # Vergleich stimmt sonst zu neun Zehnteln ueber die Slot-Flaeche ab.
    if hintergrund:
        try:
            from ...imaging import mit_hintergrund_maske
            img = mit_hintergrund_maske(img, hintergrund)
        except ImportError:
            pass
    zielordner = Path(template_dir)
    zielordner.mkdir(parents=True, exist_ok=True)
    base = sanitize_filename(name)
    filename = f"{base}.png"
    n = 2
    while (zielordner / filename).exists():
        filename = f"{base}_{n}.png"
        n += 1
    try:
        img.save(zielordner / filename)
        return filename
    except (IOError, OSError, ValueError):
        return None
