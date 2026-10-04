"""Leer heisst auch: an der Stelle ist gar kein Slot zu sehen.

Gemeldet an einem echten Bestand: in dieser Ansicht des Spiels verschwindet
ein Slot mit seinem Item — ohne Item steht an der Stelle der Spielhintergrund,
und bei zu vielen Items verrutscht die Reihe, sodass abgeschnittene Ausschnitte
entstehen. Die Leer-Regel („nur Slotfarbe, keine Marker") griff dort nie, denn
es gibt gar keine Slotfarbe mehr. Das Auto-Lernen legte so sechs dunkle
Hintergründe und drei abgeschnittene Ausschnitte als „Items" an.

Gemessen wird am RAND des Ausschnitts: echte Items zeigen dort mindestens 64 %
Slotfarbe (auch Edelsteine, die den Slot sonst ganz füllen), die Fehlgriffe
höchstens 13 %.
"""
import random as _random

from ._harness import check, section

try:
    from PIL import Image as _Image
except ImportError:
    _Image = None

section("Leer heisst auch: kein Slot zu sehen")

if _Image is None:
    print("  ----  uebersprungen (Pillow fehlt)")
else:
    from autoclicker.editors.item_editor.markers import (
        _prepare_learning_image, _slot_visible,
    )

    _SLOT = (30, 127, 106)

    def _slot_with_item(fill_share: float, seed: int = 1):
        """Ein Slot in Slotfarbe, in der Mitte ein buntes Symbol."""
        img = _Image.new("RGB", (62, 57), _SLOT)
        r = _random.Random(seed)
        margin_x = int(62 * (1 - fill_share) / 2)
        margin_y = int(57 * (1 - fill_share) / 2)
        for x in range(margin_x, 62 - margin_x):
            for y in range(margin_y, 57 - margin_y):
                img.putpixel((x, y), (r.randrange(120, 256), r.randrange(0, 80),
                                      r.randrange(120, 256)))
        return img

    def _game_background(seed: int = 2):
        """Dunkler, leicht gemusterter Spielhintergrund — kein Slot."""
        img = _Image.new("RGB", (62, 57))
        r = _random.Random(seed)
        for x in range(62):
            for y in range(57):
                v = r.randrange(-8, 9)
                img.putpixel((x, y), (25 + v, 45 + v, 45 + v))
        return img

    _item = _slot_with_item(0.5)
    _gem = _slot_with_item(0.86)          # fuellt den Slot fast ganz
    _bg = _game_background()
    check("ein Item im Slot: der Slot ist zu sehen", _slot_visible(_item, _SLOT))
    check("ein Edelstein, der den Slot fast fuellt: am Rand trotzdem Slotfarbe",
          _slot_visible(_gem, _SLOT))
    check("Spielhintergrund ohne Slot: kein Slot zu sehen",
          not _slot_visible(_bg, _SLOT))

    check("das Item wird gelernt", _prepare_learning_image(_item, _SLOT)[2] is False)
    check("der Edelstein wird gelernt", _prepare_learning_image(_gem, _SLOT)[2] is False)
    # Die eigentliche Probe: der Hintergrund HAT Marker (er ist ja nicht
    # slotfarben) — die alte Regel liess ihn deshalb als Item durch.
    _masked, _markers, _empty = _prepare_learning_image(_bg, _SLOT)
    check("der Spielhintergrund hat Marker (die alte Regel hielt ihn fuer ein Item)",
          bool(_markers))
    check("und gilt trotzdem als leer — kein Auto-Lernen", _empty is True)

    # Ohne Slotfarbe laesst sich nichts sagen: dann bleibt es lernbar, wie
    # bisher — lieber ein Item zu viel anbieten als ein echtes verschweigen.
    check("ohne Slotfarbe gilt der Slot als sichtbar", _slot_visible(_bg, None))
    check("ein Winzling ohne echten Rand ebenso",
          _slot_visible(_Image.new("RGB", (6, 6), (0, 0, 0)), _SLOT))
