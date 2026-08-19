"""Gemeinsame, GUI-freie Dienste für alle Scan-Editoren.

Konsolen-Editor und Sequence Studio dürfen unterschiedliche Oberflächen haben,
aber Geometrie und Bilderkennung müssen dieselben Ergebnisse liefern.
"""


def map_point_between_rects(point: tuple[int, int], source_rect: tuple,
                            target_rect: tuple) -> tuple[int, int]:
    """Überträgt einen Punkt proportional von einem Fensterrechteck ins andere.

    Bei gleicher Grösse ist das eine reine Verschiebung. Ändert sich die
    Fenstergrösse, bleibt die relative Lage im Client-Bereich erhalten.
    """
    sx1, sy1, sx2, sy2 = (int(v) for v in source_rect)
    tx1, ty1, tx2, ty2 = (int(v) for v in target_rect)
    sw, sh = sx2 - sx1, sy2 - sy1
    tw, th = tx2 - tx1, ty2 - ty1
    if sw <= 0 or sh <= 0 or tw <= 0 or th <= 0:
        raise ValueError("Fensterrechteck ohne Fläche")
    x, y = int(point[0]), int(point[1])
    return (
        tx1 + round((x - sx1) * tw / sw),
        ty1 + round((y - sy1) * th / sh),
    )


def map_region_between_rects(region: tuple[int, int, int, int], source_rect: tuple,
                             target_rect: tuple) -> tuple[int, int, int, int]:
    """Überträgt beide Ecken einer Bildschirmregion zwischen Fensterlagen."""
    links, oben = map_point_between_rects((region[0], region[1]), source_rect, target_rect)
    rechts, unten = map_point_between_rects((region[2], region[3]), source_rect, target_rect)
    return (min(links, rechts), min(oben, unten),
            max(links, rechts), max(oben, unten))


def crop_screen_region(source_img, region: tuple[int, int, int, int],
                       origin: tuple[int, int]):
    """Schneidet eine Bildschirmregion sicher aus einem aufgenommenen Bild."""
    left, top = origin
    x1 = max(0, region[0] - left)
    y1 = max(0, region[1] - top)
    x2 = min(source_img.width, region[2] - left)
    y2 = min(source_img.height, region[3] - top)
    if x2 <= x1 or y2 <= y1:
        return None
    return source_img.crop((x1, y1, x2, y2))


def detect_slots_in_image(img, slot_color_rgb: tuple, hsv_tolerance: int,
                          verbose: bool = False, sv_tolerance: int = 50):
    """Findet Slot-Rechtecke anhand ihrer Hintergrundfarbe.

    Das Ergebnis sind ``(x, y, width, height)`` relativ zum Bild, auf die
    Median-Grösse normalisiert und zeilenweise sortiert.
    """
    import cv2
    import numpy as np

    r, g, b = slot_color_rgb
    r_n, g_n, b_n = r / 255, g / 255, b / 255
    max_c, min_c = max(r_n, g_n, b_n), min(r_n, g_n, b_n)
    diff = max_c - min_c

    if diff == 0:
        hue = 0
    elif max_c == r_n:
        hue = (60 * ((g_n - b_n) / diff) + 360) % 360
    elif max_c == g_n:
        hue = (60 * ((b_n - r_n) / diff) + 120) % 360
    else:
        hue = (60 * ((r_n - g_n) / diff) + 240) % 360

    saturation = 0 if max_c == 0 else (diff / max_c) * 255
    value = max_c * 255
    hue /= 2  # OpenCV Hue: 0-180

    if verbose:
        print(f"  HSV: ({int(hue)}, {int(saturation)}, {int(value)})")

    img_array = np.array(img)
    img_bgr = img_array[:, :, ::-1].copy()
    hsv_img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    tol, sv = hsv_tolerance, sv_tolerance
    lower = np.array([
        max(0, int(hue) - tol),
        max(0, int(saturation) - sv),
        max(0, int(value) - sv),
    ])
    upper = np.array([
        min(180, int(hue) + tol),
        min(255, int(saturation) + sv),
        min(255, int(value) + sv),
    ])

    mask = cv2.inRange(hsv_img, lower, upper)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detected = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width >= 40 and height >= 40 and 0.5 < width / height < 2.0:
            detected.append((x, y, width, height))

    detected.sort(key=lambda slot: (slot[1] // 50, slot[0]))
    if len(detected) >= 2:
        median_width = sorted(slot[2] for slot in detected)[len(detected) // 2]
        median_height = sorted(slot[3] for slot in detected)[len(detected) // 2]
        normalized = []
        for x, y, width, height in detected:
            if 0.7 * median_width <= width <= 1.3 * median_width:
                new_x = x + (width - median_width) // 2
                new_y = y + (height - median_height) // 2
                normalized.append((new_x, new_y, median_width, median_height))
        detected = normalized

    return detected, img_bgr
