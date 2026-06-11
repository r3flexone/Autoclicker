"""
Screenshot ↔ Dear-PyGui-Textur und Koordinaten-Mapping.

Die kritische Komponente des Scan-Studios: ein eingefrorener Vollbild-Screenshot
wird als Textur angezeigt; alles Zeichnen passiert in Anzeige-Koordinaten, die
exakt auf echte Bildschirm-Koordinaten zurückgerechnet werden müssen, damit
Slots/Regionen später an der richtigen Stelle klicken.

Koordinaten-Modell
------------------
Ein Vollbild-Screenshot (take_screenshot(None)) erfasst den gesamten virtuellen
Desktop ab (virtual_left, virtual_top). Damit gilt:

    screen_x = virtual_left + img_x
    screen_y = virtual_top  + img_y

Im Canvas wird das Bild mit einem festen Faktor `scale` skaliert dargestellt.
Eine Zeichen-Koordinate (draw_x, draw_y) im Drawlist (Ursprung oben-links am
Bild) rechnet sich:

    img_x = draw_x / scale          screen_x = virtual_left + draw_x / scale
    img_y = draw_y / scale          screen_y = virtual_top  + draw_y / scale

ViewTransform kapselt diese Umrechnung in beide Richtungen.
"""

from dataclasses import dataclass

try:
    import numpy as np
    _NUMPY = True
except ImportError:  # pragma: no cover - nur falls numpy fehlt
    _NUMPY = False


def fit_scale(img_w: int, img_h: int, max_w: int, max_h: int) -> float:
    """Skalierungsfaktor, damit das Bild in (max_w, max_h) passt (nie > 1.0)."""
    if img_w <= 0 or img_h <= 0:
        return 1.0
    return min(1.0, max_w / img_w, max_h / img_h)


def pil_to_texture(img):
    """PIL-Image → (width, height, flache RGBA-Float-Daten für add_raw_texture).

    Dear PyGui erwartet RGBA als Floats 0..1, zeilenweise (row-major), Länge
    width*height*4. Gibt None zurück wenn numpy fehlt.
    """
    if not _NUMPY:
        return None
    rgba = img.convert("RGBA")
    arr = np.frombuffer(rgba.tobytes(), dtype=np.uint8).astype(np.float32) / 255.0
    return rgba.width, rgba.height, arr


@dataclass
class ViewTransform:
    """Rechnet zwischen Anzeige- (draw) und Bildschirm- (screen) Koordinaten um."""
    scale: float            # Anzeige-Pixel pro Bild-Pixel
    virtual_left: int       # X-Ursprung des Screenshots auf dem virtuellen Desktop
    virtual_top: int        # Y-Ursprung des Screenshots
    img_w: int              # Bildbreite in Bild-Pixeln
    img_h: int              # Bildhöhe in Bild-Pixeln

    # --- draw → screen ---
    def draw_to_screen(self, dx: float, dy: float) -> tuple[int, int]:
        return (
            int(round(self.virtual_left + dx / self.scale)),
            int(round(self.virtual_top + dy / self.scale)),
        )

    # --- screen → draw ---
    def screen_to_draw(self, sx: int, sy: int) -> tuple[float, float]:
        return (
            (sx - self.virtual_left) * self.scale,
            (sy - self.virtual_top) * self.scale,
        )

    # --- draw → image (Pixel im Screenshot) ---
    def draw_to_image(self, dx: float, dy: float) -> tuple[int, int]:
        ix = int(round(dx / self.scale))
        iy = int(round(dy / self.scale))
        ix = max(0, min(self.img_w - 1, ix))
        iy = max(0, min(self.img_h - 1, iy))
        return ix, iy

    def screen_region_to_draw(self, region: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
        """(x1,y1,x2,y2) Bildschirm → (x1,y1,x2,y2) Anzeige."""
        x1, y1 = self.screen_to_draw(region[0], region[1])
        x2, y2 = self.screen_to_draw(region[2], region[3])
        return x1, y1, x2, y2

    @property
    def display_size(self) -> tuple[int, int]:
        return int(self.img_w * self.scale), int(self.img_h * self.scale)
