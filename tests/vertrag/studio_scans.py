"""Der Scans-Reiter des Studios: Slots, Items, Erkennung, Rueckgaengig.

Das Dear-PyGui-Scan-Studio ist weg; seine Arbeit macht ein Reiter im
Sequenz-Studio. Was dabei zaehlt, ist nicht die Ansicht (die laeuft in keinem
Test), sondern was die Bruecke daraus macht: aus zwei Klicks ein Rechteck, aus
einem Klick eine gemessene Farbe, aus einem Umbenennen eine nachgezogene
Referenz.

Mit ueber 1.200 Zeilen war das der groesste zusammenhaengende Block in
`test_logic.py` — und in sich geschlossen, also der erste, der ein eigenes Modul
verdient hat.
"""
import os as _os
import shutil
import tempfile
from pathlib import Path

from ._harness import check, section, studio_web_source
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB8
from autoclicker.models import Sequence as _SEQ8

# --------------------------- Scans im Studio: Slots, Items, Erkennung
section("Scans: Slot aus zwei Ecken, Farbe gemessen, Referenzen nachgezogen")

# Das Dear-PyGui-Scan-Studio ist weg; seine Arbeit macht ein Reiter im Studio.
# Was dabei zaehlt, ist nicht die Ansicht (die laeuft in keinem Test), sondern
# was die Bruecke daraus macht: aus zwei Klicks ein Rechteck, aus einem Klick
# eine gemessene Farbe, aus einem Umbenennen eine nachgezogene Referenz.
import re as _re13
from autoclicker.editors.sequence_studio.scans import (
    MODUS_KLICK as _MK18, MODUS_MESSEN as _MM18, MODUS_SLOT as _MS18,
    MODUS_WAHL as _MW18, MODUS_BEREICH as _MB18, MODUS_FINDEN as _MF18,
    MODI as _MODI18, MIN_SLOT as _MINSLOT18,
)
from autoclicker.models import (ItemProfile as _ITEM8, ItemSlot as _SLOT8,
                                ItemScanConfig as _ISC8)

_repo17 = Path(__file__).resolve().parent.parent

_sand18 = tempfile.mkdtemp(prefix="studioscan_")
_cwd18 = _os.getcwd()
_os.chdir(_sand18)
try:
    Path("sequences").mkdir()
    _b18 = _SB8(_SEQ8(name="S"),
                Path("sequences/s/sequence.json"), "sequences")

    # --- Ohne Bild passiert nichts Dummes ---
    # Der haeufigste Weg in den Reiter ist "aufmachen und draufklicken", und
    # ohne Screenshot gibt es nichts zu messen. Eine Meldung ist die richtige
    # Antwort, ein Slot mit Farbe None waere die falsche.
    _z18 = _b18.scan_daten()
    check("vor der Aufnahme steht die Zielsequenz in den Scan-Daten",
          _z18["sequenz"] == "S")
    check("ohne Bild gibt es kein Foto in der Aufnahme", _z18["foto"] is None)
    check("und keine Slots", _z18["slots"] == [])
    check("der Modus faengt beim Auswaehlen an", _z18["modus"] == _MW18)
    check("ohne Scan ist keine Aufnahmeart bereit",
          _z18["aufnahme_bereit"] == {"item": False, "boss": False, "icon": False})

    # Ein Screenshot und die daraus gebauten Bereiche brauchen zuerst ein
    # eindeutiges Speicherziel. Vorher lagen sie nur in dieser Studio-Sitzung
    # und verschwanden beim Schliessen, ohne je zu einem Scan zu gehoeren.
    for _art18, _name18 in (("item", "Item-Scan"), ("boss", "Boss-Scan"),
                            ("icon", "Icon-Scan")):
        _z18 = _b18.scan_foto({"art": _art18})
        check(f"ohne {_name18} wird kein Screenshot aufgenommen",
              _z18["foto"] is None and _z18["status"]["art"] == "warn"
              and _name18 in _z18["status"]["text"])
    _z18 = _b18.scan_modus_setzen({"modus": _MS18, "art": "item"})
    check("ohne Item-Scan laesst sich auch kein Slot-Werkzeug einschalten",
          _z18["modus"] == _MW18 and _z18["slots"] == [])
    _z18 = _b18.scan_bereich_setzen({"bereich": [10, 10, 100, 100], "art": "item"})
    check("ohne Item-Scan wird auch kein Aufnahmebereich vorgemerkt",
          _z18["bereich"] is None and _z18["status"]["art"] == "warn")

    # Gegenprobe fuer eine noch offene alte Sitzung: ein verwaistes Bild darf
    # beim spaeteren Anlegen nicht still dem neuen Scan zugeschlagen werden.
    _b18._foto = object()
    _b18._foto_bild = "verwaist"
    _b18._foto_info = {"breite": 1, "hoehe": 1}
    _b18.scan_bereich = (1, 2, 3, 4)
    _z18 = _b18.scan_neu({"name": "Weg"})
    check("erst der angelegte Scan schaltet seine Aufnahme frei",
          _z18["aufnahme_bereit"] == {"item": True, "boss": False, "icon": False})
    check("ein verwaistes Sitzungsbild wird dabei nicht uebernommen",
          _z18["foto"] is None and _z18["bereich"] is None
          and _b18._foto is None and not _b18._foto_bild)

    # --- Ein gestelltes Bild unterschieben ---
    # Denselben Weg geht der Browser-Pruefstand: `take_screenshot` gibt es auf
    # dieser Plattform nicht, alles dahinter schon.
    _hat_pil18 = False
    try:
        from PIL import Image as _PILImage18
        _hat_pil18 = True
    except ImportError:
        pass

    if not _hat_pil18:
        print("  ----  Bild-Teil uebersprungen (Pillow nicht installiert)")
    else:
        _bild18 = _PILImage18.new("RGB", (400, 300), (24, 28, 36))
        for _px18 in range(100, 160):
            for _py18 in range(100, 160):
                _bild18.putpixel((_px18, _py18), (48, 54, 68))
        for _px18 in range(112, 148):
            for _py18 in range(112, 148):
                _bild18.putpixel((_px18, _py18), (200, 60, 60))

        import autoclicker.imaging as _img18
        import autoclicker.winapi as _win18
        _echt_shot18 = _img18.take_screenshot
        _echt_org18 = _win18.get_virtual_origin
        # Der Stub schneidet wie das Original: `take_screenshot(region)` liefert
        # den Ausschnitt, nicht den ganzen Schirm. Ohne das koennte der Test die
        # Bereichs-Aufnahme gar nicht messen - sie saehe aus wie Vollbild.
        _img18.take_screenshot = lambda region=None: (
            _bild18.copy() if not region else _bild18.crop(tuple(region)))
        _win18.get_virtual_origin = lambda: (0, 0)
        try:
            _z18 = _b18.scan_foto()
            check("das Foto steht in der Aufnahme",
                  _z18["foto"] and _z18["foto"]["breite"] == 400)
            check("und das Bild selbst kommt getrennt",
                  _b18.scan_bild().startswith("data:image/png;base64,"))
            check("es steht NICHT in der Aufnahme", "bild" not in _z18)

            # --- Zwei Ecken ergeben einen Slot ---
            _b18.scan_modus_setzen({"modus": _MS18})
            _z18 = _b18.scan_klick({"x": 100, "y": 100})
            check("nach der ersten Ecke gibt es noch keinen Slot",
                  _z18["slots"] == [] and _z18["ecke"] == [100, 100])
            _z18 = _b18.scan_klick({"x": 160, "y": 160})
            check("die zweite Ecke legt ihn an", len(_z18["slots"]) == 1)
            _s18 = _z18["slots"][0]
            check("mit der aufgezogenen Flaeche", _s18["region"] == [100, 100, 160, 160])
            check("dem Klickpunkt in der Mitte", _s18["klick"] == [130, 130])
            # Die Farbe wird an der INNEREN Ecke gemessen, nicht in der Mitte -
            # dort liegt das Item, nicht der Hintergrund.
            check("und dem gemessenen Hintergrund", _s18["farbe"] == "#303644")
            check("die Ecke ist danach wieder frei", _z18["ecke"] is None)

            # Ein Werkzeug ist standardmaessig einmalig: nach dem Slot ist wieder
            # Auswaehlen aktiv. Fuer zwanzig Slots laesst es sich anheften.
            check("ein einmaliges Werkzeug kehrt zum Auswaehlen zurueck",
                  _z18["modus"] == _MW18)
            _b18.scan_modus_setzen({"modus": _MS18, "fixiert": True})
            _b18.scan_klick({"x": 260, "y": 260})
            _z18 = _b18.scan_klick({"x": 200, "y": 200})
            check("auch von rechts unten nach links oben",
                  _z18["slots"][1]["region"] == [200, 200, 260, 260])
            check("angeheftet bleibt das Werkzeug fuer Serien aktiv",
                  _z18["modus"] == _MS18 and _z18["werkzeug_fixiert"] is True)

            # --- Zu kleines Rechteck wird abgelehnt ---
            _b18.scan_klick({"x": 300, "y": 300})
            _z18 = _b18.scan_klick({"x": 301, "y": 301})
            check("ein Rechteck von einem Pixel wird abgelehnt",
                  len(_z18["slots"]) == 2 and _z18["status"]["art"] == "warn")

            # --- Ein winziger Slot entsteht gar nicht erst ---
            # Zwei Klicks fast auf dieselbe Stelle ergaben einen Slot von 2x2 px
            # - und der war danach kaum wieder loszuwerden, weil man ihn im Bild
            # nicht mehr traf. Loeschen setzt Auswaehlen voraus.
            _b18.scan_klick({"x": 300, "y": 300})
            _z18 = _b18.scan_klick({"x": 304, "y": 304})
            check("ein Rechteck von vier Pixeln wird abgelehnt",
                  len(_z18["slots"]) == 2 and _z18["status"]["art"] == "warn")
            check("und die Meldung nennt das Mindestmass",
                  str(_MINSLOT18) in _z18["status"]["text"])

            # Vorhandene Winzlinge (aus einer alten Datei, aus getippten Zahlen)
            # gibt es weiterhin - die muessen ANKLICKBAR sein, sonst bleiben sie
            # fuer immer. Der Slot selbst wird dabei nicht angefasst.
            _b18.slots["Winzling"] = _SLOT8(name="Winzling",
                                            scan_region=(340, 40, 342, 42),
                                            click_pos=(341, 41))
            _b18.scan_modus_setzen({"modus": _MW18, "fixiert": False})
            _z18 = _b18.scan_klick({"x": 344, "y": 44})
            check("ein winziger Slot ist auch daneben noch zu treffen",
                  _z18["wahl"]["name"] == "Winzling")
            check("er bleibt dabei so klein, wie er ist",
                  [s for s in _z18["slots"] if s["name"] == "Winzling"][0]["region"]
                  == [340, 40, 342, 42])
            check("und die Liste markiert ihn",
                  [s for s in _z18["slots"] if s["name"] == "Winzling"][0]["winzig"] is True)
            check("ein normaler Slot heisst nicht winzig",
                  [s for s in _z18["slots"] if s["name"] == "Slot 1"][0]["winzig"] is False)

            # Liegt er IN einem grossen, fing der grosse bisher jeden Klick ab.
            # Der KLEINSTE gewinnt, nicht der zuletzt angelegte - deshalb kommt
            # der Umschlag hier NACH dem Zwerg in die Liste: waere die Regel
            # weiterhin "der letzte gewinnt", zeigte dieser Klick auf ihn.
            _b18.slots["Zwerg"] = _SLOT8(name="Zwerg", scan_region=(128, 128, 134, 134),
                                         click_pos=(131, 131))
            _b18.slots["Umschlag"] = _SLOT8(name="Umschlag", scan_region=(120, 120, 200, 200),
                                            click_pos=(160, 160))
            _z18 = _b18.scan_klick({"x": 131, "y": 131})
            check("ein kleiner Slot in einem grossen gewinnt den Klick",
                  _z18["wahl"]["name"] == "Zwerg")
            _z18 = _b18.scan_klick({"x": 190, "y": 190})
            check("und der grosse bleibt ueberall sonst anklickbar",
                  _z18["wahl"]["name"] == "Umschlag")
            # Auch zwischen zwei grossen zaehlt die Flaeche, nicht die Reihenfolge.
            _z18 = _b18.scan_klick({"x": 150, "y": 150})
            check("zwischen zwei Slots gewinnt der kleinere",
                  _z18["wahl"]["name"] == "Slot 1")
            # Der Punkt der ganzen Uebung: anklickbar heisst loeschbar.
            _b18.scan_klick({"x": 131, "y": 131})
            _z18 = _b18.scan_slot_loeschen()
            check("und damit ist er auch zu loeschen",
                  all(s["name"] != "Zwerg" for s in _z18["slots"]))
            _b18.scan_klick({"x": 344, "y": 44})
            _b18.scan_slot_loeschen()
            del _b18.slots["Umschlag"]

            # --- Ein Rechteck neben den Slots waehlt mehrere ---
            # Dreissig Slots einzeln anzuklicken und einzeln zu loeschen ist
            # der Grund, warum es das gibt. Die Sammel-Aktion arbeitet auf der
            # Auswahl, nicht auf einem Slot - dieselbe Regel wie im
            # Sequenz-Editor.
            _b18.scan_modus_setzen({"modus": _MW18})
            _z18 = _b18.scan_klick({"x": 5, "y": 5})
            check("ein Klick neben allen Slots faengt ein Rechteck an",
                  _z18["ecke"] == [5, 5] and _z18["auswahl"] == [])
            _z18 = _b18.scan_klick({"x": 290, "y": 290})
            check("die zweite Ecke waehlt alles darin",
                  sorted(_z18["auswahl"]) == ["Slot 1", "Slot 2"])
            check("und die Ecke ist wieder frei", _z18["ecke"] is None)
            check("einer davon ist der, den der Inspektor bearbeitet",
                  _z18["wahl"]["name"] in _z18["auswahl"])

            # Ganz darin, nicht angeschnitten: "alle die darin sind" heisst
            # genau das, und Ermessen ist bei einer Sammel-Loeschung falsch.
            _b18.scan_klick({"x": 5, "y": 5})
            _z18 = _b18.scan_klick({"x": 130, "y": 130})
            check("ein angeschnittener Slot zaehlt nicht dazu",
                  _z18["auswahl"] == [])
            check("ein leeres Rechteck hebt die Auswahl auf",
                  _z18["wahl"]["name"] == "")

            # STRG nimmt einzelne dazu und wieder heraus. Vorher einen normalen
            # Klick, sonst waere "dazu" von "nur dieser" nicht zu unterscheiden.
            _b18.scan_klick({"x": 210, "y": 210})
            _z18 = _b18.scan_klick({"x": 130, "y": 130, "zusatz": True})
            check("STRG-Klick nimmt einen Slot zur Auswahl DAZU",
                  sorted(_z18["auswahl"]) == ["Slot 1", "Slot 2"])
            _z18 = _b18.scan_klick({"x": 130, "y": 130, "zusatz": True})
            check("nochmal darauf nimmt ihn wieder heraus",
                  _z18["auswahl"] == ["Slot 2"])

            # Ein Klick auf einen Slot ist wieder eine EINZEL-Auswahl - sonst
            # naehme das naechste "loeschen" die alte Menge mit.
            _z18 = _b18.scan_klick({"x": 130, "y": 130})
            check("ein gewoehnlicher Klick waehlt nur diesen einen",
                  _z18["auswahl"] == ["Slot 1"])
            _z18 = _b18.scan_waehlen({"art": "slot", "name": "Slot 2"})
            check("und eine Zeile in der Liste ebenso",
                  _z18["auswahl"] == ["Slot 2"])

            # Loeschen nimmt die ganze Auswahl.
            _b18.scan_klick({"x": 5, "y": 5})
            _b18.scan_klick({"x": 290, "y": 290})
            _z18 = _b18.scan_slot_loeschen()
            check("loeschen nimmt die ganze Auswahl",
                  _z18["slots"] == [] and _z18["auswahl"] == [])
            check("und sagt, wie viele es waren",
                  "2 Slots gelöscht" in _z18["status"]["text"])
            _b18.slots["Slot 1"] = _SLOT8(name="Slot 1", scan_region=(100, 100, 160, 160),
                                          click_pos=(111, 122), slot_color=(48, 54, 68))
            _b18.slots["Slot 2"] = _SLOT8(name="Slot 2", scan_region=(200, 200, 260, 260),
                                          click_pos=(230, 230), slot_color=(48, 54, 68))
            _b18.scan_waehlen({"art": "slot", "name": "Slot 1"})

            # --- Farbe messen: im Item statt im Hintergrund ---
            _b18.scan_waehlen({"art": "slot", "name": _s18["name"]})
            _b18.scan_modus_setzen({"modus": _MM18})
            _z18 = _b18.scan_klick({"x": 130, "y": 130})
            check("die Pipette misst im Originalbild",
                  _z18["slots"][0]["farbe"] == "#C83C3C")
            check("die Pipette ist danach wieder aus",
                  _z18["modus"] == _MW18)
            # Gegenprobe: gemessen wird NICHT im verkleinerten Anzeigebild.
            # Waere es das, ergaebe der Rand des Items eine Mischfarbe.
            _b18.scan_modus_setzen({"modus": _MM18})
            _z18 = _b18.scan_klick({"x": 100, "y": 100})
            check("und trifft auch den Rand genau", _z18["slots"][0]["farbe"] == "#303644")

            # --- Klickpunkt setzen ---
            _b18.scan_modus_setzen({"modus": _MK18})
            _z18 = _b18.scan_klick({"x": 111, "y": 122})
            check("der Klickpunkt folgt dem Zeiger", _z18["slots"][0]["klick"] == [111, 122])

            # --- Auswaehlen ueber das Bild ---
            _b18.scan_modus_setzen({"modus": _MW18})
            _z18 = _b18.scan_klick({"x": 210, "y": 210})
            check("ein Klick waehlt den Slot darunter", _z18["wahl"]["name"] == "Slot 2")
            # Daneben zu klicken waehlt nicht ab, sondern faengt ein
            # Auswahl-Rechteck an: die Abwahl ist das leere Rechteck (oder ESC).
            # Ein einzelner Klick ins Leere darf nichts wegnehmen, sonst kostet
            # ein Verklicker die gerade aufgebaute Auswahl.
            _z18 = _b18.scan_klick({"x": 5, "y": 5})
            check("daneben faengt ein Auswahl-Rechteck an",
                  _z18["ecke"] == [5, 5] and _z18["wahl"]["name"] == "Slot 2")
            _z18 = _b18.scan_klick({"x": 8, "y": 8})
            check("ein Rechteck ohne Slots waehlt nichts",
                  _z18["wahl"]["name"] == "" and _z18["auswahl"] == [])

            # --- Item lernen ---
            _b18.scan_waehlen({"art": "slot", "name": "Slot 1"})
            _z18 = _b18.scan_item_lernen({"slot": "Slot 1"})
            check("aus dem Slot wird ein Item", len(_z18["items"]) == 1)
            _i18 = _z18["items"][0]
            check("es hat Marker-Farben", len(_i18["marker"]) > 0)
            check("und ein Template auf Platte",
                  _i18["template"]
                  and Path("sequences/s/templates", _i18["template"]).exists())
            check("gelernt heisst nicht stumm", _i18["stumm"] is False)
            check("die Vorschau kommt auf Nachfrage",
                  _b18.scan_vorschau({"namen": [_i18["name"]]})[_i18["name"]]
                  .startswith("data:image/png;base64,"))

            # --- Die drei Schritte zu einem Scan ---
            # Der Reiter zeigte alle Bedienelemente gleichzeitig; wer zum ersten
            # Mal einen Scan anlegt, sah eine Wand statt eines Weges.
            _sch18 = _b18.scan_daten()["schritte"]
            check("es sind drei Schritte", [s["nr"] for s in _sch18] == [1, 2, 3])
            check("mit Bild ist der erste erledigt", _sch18[0]["fertig"] is True)
            check("mit angelegten Slots ist auch der zweite erledigt",
                  _sch18[1]["fertig"] is True)
            # Der entscheidende Satz: zwischen Slots und Items liegt das Spiel.
            # Wer auf dem alten Bild lernt, lernt leere Slots.
            check("Schritt 3 sagt, dass neu aufgenommen werden muss",
                  "NEU aufnehmen" in _sch18[2]["was"])
            check("ein fertiger Scan hat keinen offenen Assistent-Schritt",
                  sum(1 for s in _sch18 if s["aktuell"]) == 0)

            # --- Slots finden: Suchbereich, dann ein Klick auf den Hintergrund ---
            # 24 Slots von Hand sind 48 Klicks. Die Erkennung gibt es laengst -
            # dieselbe Funktion, die auch `repair` im Slot-Editor benutzt.
            #
            # Der Koeder unten rechts hat GENAU die Slot-Farbe und ist keiner:
            # ein Menue neben dem Inventar. Ohne Suchbereich wird er mitgefunden,
            # und das faellt erst beim Erkennen auf - dann hat man ihn schon.
            # Jede Zelle bekommt in der Mitte ein eigenes Rauschmuster. Ohne das
            # ist die Zelle einfarbig - und ein Vergleich, der den Hintergrund
            # ausmaskiert, haette dann gar keine Pixel mehr zu vergleichen.
            # (Ausserdem: eine gleichfoermige Flaeche hat keine Varianz, also
            # auch keine Korrelation. Echte Item-Symbole haben beides.)
            import random as _rnd18
            _gitter18 = _PILImage18.new("RGB", (400, 300), (20, 24, 30))
            def _zelle18(ox, oy, saat):
                for _px18 in range(60):
                    for _py18 in range(60):
                        _gitter18.putpixel((ox + _px18, oy + _py18), (48, 54, 68))
                r = _rnd18.Random(saat)
                for _px18 in range(20, 40):
                    for _py18 in range(20, 40):
                        _gitter18.putpixel((ox + _px18, oy + _py18),
                                           (r.randrange(120, 256), r.randrange(120, 256),
                                            r.randrange(120, 256)))
            for _gy18 in range(2):
                for _gx18 in range(3):
                    _zelle18(40 + _gx18 * 80, 40 + _gy18 * 80, _gy18 * 3 + _gx18)
            _zelle18(320, 220, 99)
            _slots_vorher18 = dict(_b18.slots)
            _b18.slots.clear()
            _b18._objekte_angleichen()
            _b18._foto = _gitter18
            _b18._anzeigebild(0, 0, 1.0)

            # Der erste Klick ist keine Farbe mehr, sondern eine Ecke.
            _b18.scan_modus_setzen({"modus": _MF18})
            _z18 = _b18.scan_klick({"x": 20, "y": 20})
            check("der erste Klick beim Finden setzt eine Ecke",
                  _z18["slots"] == [] and _z18["ecke"] == [20, 20])
            _z18 = _b18.scan_klick({"x": 280, "y": 200})
            check("die zweite Ecke ergibt den Suchbereich",
                  _z18["suchbereich"] == [20, 20, 280, 200] and _z18["slots"] == [])
            # Ein Klick daneben legt nichts an, sondern sagt es: sonst suchte man
            # nach der Farbe, die man gerade danebengesetzt hat.
            _z18 = _b18.scan_klick({"x": 350, "y": 250})
            check("eine Farbe ausserhalb des Suchbereichs zaehlt nicht",
                  _z18["slots"] == [] and _z18["status"]["art"] == "warn")

            _z18 = _b18.scan_klick({"x": 42, "y": 42})
            if _b18._hat_opencv():
                check("der Klick auf den Hintergrund legt alle Slots an",
                      len(_z18["slots"]) == 6)
                check("der Koeder ausserhalb ist NICHT dabei",
                      all(s["region"][0] < 300 for s in _z18["slots"]))
                check("der Suchbereich ist danach wieder weg",
                      _z18["suchbereich"] is None)
                check("sie gehoeren gleich zum offenen Scan",
                      all(s["dabei"] for s in _z18["slots"]))
                check("danach ist wieder Auswaehlen aktiv", _z18["modus"] == _MW18)
                # Der Einzug: die Erkennung liefert die ganze Zelle samt Rahmen,
                # gescannt werden soll das Innere. Der Konsolen-Editor rechnet
                # ihn seit jeher, das Studio tat es nicht - und lernte den Rahmen
                # als Item-Merkmal mit.
                import autoclicker.config as _cfg18
                _ein18 = _cfg18.CONFIG.scan_slot_inset
                check("die Zelle wird um scan_slot_inset eingezogen",
                      all(s["breite"] == 60 - 2 * _ein18 for s in _z18["slots"]))
                check("und es steht dabei, dass eingezogen wurde",
                      "Einzug" in _z18["status"]["text"])

                _b18.scan_modus_setzen({"modus": _MF18})
                _b18.scan_klick({"x": 20, "y": 20})
                _b18.scan_klick({"x": 280, "y": 200})
                _z18 = _b18.scan_klick({"x": 42, "y": 42})
                check("ein zweiter Durchgang verdoppelt nichts",
                      len(_z18["slots"]) == 6)
                # Der Panel-Hintergrund liegt bei dunklen Oberflaechen im
                # Standardband mit drin - dann kaeme EIN Rechteck ueber alles
                # heraus. Das enger werdende Band faengt genau das ab.
                check("das Panel wird nicht als ein Riesen-Slot genommen",
                      all(s["breite"] < 200 for s in _z18["slots"]))
                # Gegenprobe zum Suchbereich: derselbe Klick, aber ein Bereich,
                # der auch den Koeder umfasst - dann sind es sieben.
                _b18.slots.clear()
                _b18._objekte_angleichen()
                _b18.scan_modus_setzen({"modus": _MF18})
                _b18.scan_klick({"x": 10, "y": 10})
                _b18.scan_klick({"x": 395, "y": 295})
                _z18 = _b18.scan_klick({"x": 42, "y": 42})
                check("ein weiterer Suchbereich nimmt den Koeder mit",
                      len(_z18["slots"]) == 7)

                # --- Nach dem Finden wird gleich geprueft ---
                # Die Frage nach dem Finden ist nicht "habe ich Slots", sondern
                # "was davon kenne ich schon". Ohne das stehen zwanzig gleich
                # aussehende Rechtecke da, und "Items lernen" lernt stumpf alle.
                _items_vorher18 = dict(_b18.items)
                _b18.items.clear()
                _b18.slots.clear()
                _b18._objekte_angleichen()
                _b18.scan_modus_setzen({"modus": _MF18})
                _b18.scan_klick({"x": 10, "y": 10})
                _b18.scan_klick({"x": 395, "y": 295})
                _z18 = _b18.scan_klick({"x": 42, "y": 42})
                check("ohne Items im Bestand sagt die Probe nichts",
                      "bekanntem Item" not in _z18["status"]["text"]
                      and all(s["treffer"] is None for s in _z18["slots"]))

                # Ein Item aus genau einem dieser Slots lernen, dann nochmal
                # finden: der eine Slot muss gruen sein, die anderen nicht.
                _erster18 = sorted(_b18.slots.values(),
                                   key=lambda s: (s.scan_region[1], s.scan_region[0]))[0]
                _b18.scan_item_lernen({"slot": _erster18.name})
                _b18.slots.clear()
                _b18._objekte_angleichen()
                # Ein Slot ausserhalb des Bildes kann nie einen Treffer haben -
                # der zuverlaessigste Weg, im gestellten Gitter (in dem alle
                # Zellen gleich aussehen) ueberhaupt einen unbekannten zu haben.
                _b18.slots["Draussen"] = _SLOT8(name="Draussen",
                                                scan_region=(2000, 2000, 2060, 2060),
                                                click_pos=(2030, 2030))
                _b18.scan_modus_setzen({"modus": _MF18})
                _b18.scan_klick({"x": 10, "y": 10})
                _b18.scan_klick({"x": 395, "y": 295})
                _z18 = _b18.scan_klick({"x": 42, "y": 42})
                _gruen18 = [s for s in _z18["slots"] if s["treffer"] and s["treffer"]["name"]]
                check("das gelernte Item wird gleich im Slot erkannt",
                      len(_gruen18) >= 1)
                check("und die Meldung sagt, was noch unbekannt ist",
                      "bekanntem Item" in _z18["status"]["text"]
                      and "unbekannt" in _z18["status"]["text"])
                # Der Treffer gehoert zum offenen Scan (das Lernen hat ihn
                # eingetragen), ist also NICHT fremd.
                check("ein Item des offenen Scans gilt nicht als fremd",
                      _gruen18[0]["treffer"].get("fremd") is False)

                # --- Ein neuer Scan faengt leer an, erkannte tauchen auf ---
                # Vorher standen im Inspektor eines frischen Scans alle Slots
                # und alle Items des GESAMTEN Bestands - die eines anderen
                # Spiels also mit. Slots sind Bildschirm-Koordinaten und
                # gehoeren immer genau einem Spiel; Items koennen geteilt sein,
                # und ein Item ein zweites Mal zu lernen ist genau das, was man
                # vermeiden will. Deshalb: dabei ODER gerade erkannt.
                _erk18 = [i for i in _z18["items"] if i["erkannt"]]
                check("ein erkanntes Item ist als solches markiert",
                      len(_erk18) >= 1)
                check("und es ist genau das, was in einem Slot steht",
                      {i["name"] for i in _erk18}
                      == {s["treffer"]["name"] for s in _z18["slots"]
                          if s["treffer"] and s["treffer"]["name"]})
                # Ein Item, das nirgends erkannt wird, traegt das Merkmal nicht -
                # sonst waere die Liste wieder der ganze Bestand.
                _b18.items["Nie gesehen"] = _ITEM8(name="Nie gesehen")
                _z18 = _b18.scan_daten()
                check("ein nirgends erkanntes Item traegt das Merkmal nicht",
                      [i for i in _z18["items"]
                       if i["name"] == "Nie gesehen"][0]["erkannt"] is False)
                _b18.items.pop("Nie gesehen", None)
                _z18 = _b18.scan_daten()

                check("ein Item des Scans braucht keinen Mitgliedschaftsschalter",
                      all(s["treffer"].get("fremd") is False for s in _gruen18))
                _b18.slots.pop("Draussen", None)
                _b18.items.clear()
                _b18.items.update(_items_vorher18)
            else:
                print("  ----  Slots finden uebersprungen (OpenCV fehlt)")
            # ESC raeumt einen halb gesetzten Suchbereich weg - sonst haengt er
            # an einem Bild, das es gleich nicht mehr gibt.
            _b18.scan_modus_setzen({"modus": _MF18})
            _b18.scan_klick({"x": 20, "y": 20})
            _b18.scan_klick({"x": 280, "y": 200})
            _z18 = _b18.scan_abbrechen()
            check("ESC verwirft den Suchbereich",
                  _z18["suchbereich"] is None and _z18["modus"] == _MW18)

            # --- Der Rueckweg ist die markierte Kachel selbst ---
            # Ein Modus, in den man nur hinein kommt, ist eine Falltuer: hinein
            # mit einem Klick, heraus nur mit einer Taste, die man kennen muss.
            # Dieselbe Regel wie bei der ELSE-Kachel im Sequenz-Editor.
            _z18 = _b18.scan_modus_setzen({"modus": _MB18})
            check("eine Kachel schaltet ihren Modus ein", _z18["modus"] == _MB18)
            check("und sagt, wie man wieder herauskommt",
                  "zurück" in _z18["status"]["text"])
            _z18 = _b18.scan_modus_setzen({"modus": _MB18})
            check("nochmal dieselbe Kachel fuehrt zurueck ins Auswaehlen",
                  _z18["modus"] == _MW18)
            # Auch eine halb gesetzte Ecke geht dabei weg - sie gehoert zu einer
            # Absicht, die man gerade aufgegeben hat.
            _b18.scan_modus_setzen({"modus": _MB18})
            _b18.scan_klick({"x": 40, "y": 40})
            _z18 = _b18.scan_modus_setzen({"modus": _MB18})
            check("und nimmt die halb gesetzte Ecke mit",
                  _z18["ecke"] is None and _z18["modus"] == _MW18)
            _z18 = _b18.scan_modus_setzen({"modus": _MW18})
            check("Auswaehlen schaltet sich nicht selbst ab", _z18["modus"] == _MW18)
            # Zustand von vorher zurueck: die naechsten Pruefungen arbeiten
            # weiter auf "Slot 1" und dem gestellten Bild.
            _b18.slots.clear()
            _b18.slots.update(_slots_vorher18)
            _b18.scans.pop("Weg", None)
            _b18.scans["Basis"] = _ISC8(
                name="Basis", slots=list(_b18.slots.values()),
                items=list(_b18.items.values()), owner_sequence="S")
            _b18.scan_offen = "Basis"
            _b18._scan_arbeitsbestand("Basis")
            _b18.scan_waehlen({"art": "slot", "name": "Slot 1"})
            _b18._foto = _bild18
            _b18._anzeigebild(0, 0, 1.0)

            # --- Der Bereich: nicht immer Vollbild ---
            # Wer dasselbe Spiel dreimal offen hat, arbeitet sonst auf einem
            # Bild, in dem drei Viertel stoeren.
            _z18 = _b18.scan_daten()
            check("ohne Angabe ist es Vollbild", _z18["bereich"] is None)
            _b18.scan_modus_setzen({"modus": _MB18})
            _b18.scan_klick({"x": 80, "y": 80})
            _z18 = _b18.scan_klick({"x": 280, "y": 240})
            check("zwei Ecken schneiden das Bild zu",
                  _z18["bereich"] == [80, 80, 280, 240])
            check("und die Flaeche hat genau diese Groesse",
                  (_z18["foto"]["breite"], _z18["foto"]["hoehe"]) == (200, 160))
            check("ihr Ursprung ist die linke obere Ecke",
                  (_z18["foto"]["links"], _z18["foto"]["oben"]) == (80, 80))
            # Zugeschnitten, nicht neu geholt: gemessen wird weiter im Original,
            # und die Farbe an einer Stelle muss dieselbe bleiben.
            _b18.scan_waehlen({"art": "slot", "name": "Slot 1"})
            _b18.scan_modus_setzen({"modus": _MM18})
            _z18 = _b18.scan_klick({"x": 130, "y": 130})
            check("im Ausschnitt wird an derselben Stelle dasselbe gemessen",
                  _b18._foto_farbe(130, 130) == (200, 60, 60))

            # Der Bereich gilt fuer die naechste Aufnahme - sonst waere er ein
            # einmaliger Zuschnitt und man muesste ihn jedes Mal neu ziehen.
            _z18 = _b18.scan_foto()
            check("die naechste Aufnahme nimmt genau ihn",
                  _z18["bereich"] == [80, 80, 280, 240]
                  and _z18["foto"]["breite"] == 200)

            # Ein Slot ausserhalb wird gemeldet, nicht verschwiegen: er steht
            # weiter in der Liste, ist aber im Bild nicht zu sehen.
            check("der gewählte Bereich bleibt nach der Aufnahme erhalten",
                  _z18["bereich"] == [80, 80, 280, 240])

            # **Waehlen nimmt nicht auf.** Das war die verwirrendste Stelle des
            # Reiters: wer ein Fenster aus der Liste waehlte, hatte ploetzlich
            # ein Bild, ohne etwas ausgeloest zu haben - und der Knopf daneben
            # schien danach nichts mehr zu tun (er holte dasselbe Bild noch
            # einmal, und zwei gleiche Bilder sehen gleich aus).
            _alt18 = _b18.scan_daten()["foto"]["stand"]
            _z18 = _b18.scan_bereich_setzen({"bereich": [100, 100, 300, 300]})
            check("ein Bereich laesst sich auch direkt setzen",
                  _z18["bereich"] == [100, 100, 300, 300])
            # Das alte Bild steht unveraendert da: 200x160 vom Zuschnitt vorhin,
            # nicht 200x200 vom gerade gewaehlten Bereich.
            check("aber die Wahl nimmt NICHT gleich auf",
                  _z18["foto"]["stand"] == _alt18
                  and (_z18["foto"]["breite"], _z18["foto"]["hoehe"]) == (200, 160))
            check("sie sagt stattdessen, was als naechstes kommt",
                  "aufnehmen" in _z18["status"]["text"])
            _z18 = _b18.scan_foto()
            check("erst der Knopf holt das Bild",
                  (_z18["foto"]["breite"], _z18["foto"]["hoehe"]) == (200, 200))
            # Und man SIEHT, dass aufgenommen wurde: zwei Aufnahmen desselben
            # Spielstands sehen gleich aus, also muss die Meldung sich unter-
            # scheiden. Sonst wirkt der Knopf kaputt.
            check("die Aufnahme sagt, wann sie gemacht wurde",
                  "aufgenommen um" in _z18["status"]["text"])

            _z18 = _b18.scan_bereich_setzen()
            check("und ohne Angabe geht es zurueck auf Vollbild",
                  _z18["bereich"] is None)
            check("auch das erst nach dem Aufnehmen",
                  _b18.scan_foto()["foto"]["breite"] == 400)
            _z18 = _b18.scan_bereich_setzen({"bereich": [10, 10, 12, 12]})
            check("ein Bereich von zwei Pixeln gilt nicht als Bereich",
                  _z18["bereich"] is None)

            # Die Fensterliste ist der Weg fuer "dasselbe Programm dreimal
            # offen": unterscheidbar sind sie nur an der Lage.
            check("die Fensterliste ist eine Liste",
                  isinstance(_b18.scan_fenster(), list))
        finally:
            _img18.take_screenshot = _echt_shot18
            _win18.get_virtual_origin = _echt_org18


    # Neuer Vertrag: der geöffnete Scan IST der vollständige Bestand. Ein
    # weiterer Scan beginnt leer; es gibt weder Mitgliedschaft noch globale
    # slots.json/items.json, die beide wieder zusammenmischen könnten.
    _b18.scans.clear()
    _b18.scan_offen = ""
    _b18.scan_neu({"name": "Lokal"})
    _b18.slots["Slot 1"] = _SLOT8(
        name="Slot 1", id=1, scan_region=(0, 0, 20, 20), click_pos=(10, 10))
    _b18.items["Item 1"] = _ITEM8(name="Item 1")
    _b18._objekte_angleichen()
    check("ein Scan besitzt seinen vollständigen Slot-Bestand",
          [s.name for s in _b18.scans["Lokal"].slots] == ["Slot 1"])
    check("ein Scan besitzt seinen vollständigen Item-Bestand",
          [i.name for i in _b18.scans["Lokal"].items] == ["Item 1"])

    _b18.scan_neu({"name": "Andere"})
    check("ein anderer Scan beginnt unabhängig und leer",
          _b18.slots == {} and _b18.items == {})
    _b18.scan_oeffnen({"name": "Lokal"})
    check("beim Zurückwechseln kommt genau dessen Bestand wieder",
          sorted(_b18.slots) == ["Slot 1"] and sorted(_b18.items) == ["Item 1"])

    _z_besitz18 = _b18.scan_speichern()
    check("Scan-Bestand wird unter seiner Sequenz gespeichert",
          _z_besitz18["status"]["art"] == "ok"
          and Path("sequences/s/item_scans/lokal.json").exists())
    check("keine globalen Slot-/Item-Dateien entstehen",
          not Path("slots/slots.json").exists()
          and not Path("items/items.json").exists())
finally:
    _os.chdir(_cwd18)

# --- Jeder Modus hat eine Kachel in der Oberflaeche ---
# Ein Modus ohne Knopf ist ein Modus, den niemand erreicht; ein Knopf ohne Modus
# meldet "Unbekannter Modus". Beide Seiten messen, nicht eine abschreiben.
_html18 = studio_web_source()
_block18 = _html18[_html18.index("const SCAN_MODI = ["):]
_block18 = _block18[:_block18.index("];")]
_kacheln18 = _re13.findall(r'key:\s*"(\w+)"', _block18)
check("jeder Modus der Bruecke hat eine Kachel", sorted(_kacheln18) == sorted(_MODI18))
# Zug um Zug, nicht als Menge: **die Reihenfolge ist die Rangfolge.** „Slots
# finden" steht direkt hinter „Auswaehlen", weil es das ist, was man ZUERST
# macht - das Automatische ist der Normalfall, das Aufziehen von Hand der
# Ausweichweg. Als vorletzte Kachel stand es da, wo man den Notnagel sucht.
check("und die Kacheln stehen in der Reihenfolge von MODI",
      _kacheln18 == list(_MODI18))
check("Slots finden steht gleich hinter Auswaehlen",
      _kacheln18[:2] == [_MW18, _MF18])
_tasten18 = _re13.findall(r'taste:\s*"(\w)"', _block18)
check("und jede Kachel eine eigene Taste",
      len(_tasten18) == len(_kacheln18) == len(set(_tasten18)))

# --- Die verbleibenden zusammenklappbaren Abschnitte haengen zusammen ---
# Kopf (`data-klapp`), Rahmen (`id="ab-…"`) und Zustand (`klappZu`) muessen
# denselben Schluessel tragen. Ein Tippfehler in einem davon ist kein Fehler,
# den man sieht: der Abschnitt laesst sich dann einfach nicht mehr zuklappen,
# oder er bleibt zu und der Kopf reagiert nicht. Genau die Sorte stiller
# Defekt, gegen die hier sonst auch gemessen wird.
_klapp18 = sorted(set(_re13.findall(r'data-klapp="(\w+)"', _html18)))
check("es gibt ueberhaupt Klapp-Koepfe", len(_klapp18) >= 1)
check("jeder Kopf sitzt in einem Abschnitt mit passender id",
      all(f'id="ab-{_k18}"' in _html18 for _k18 in _klapp18))
_zustand18 = _re13.search(r'let klappZu = \{([^}]*)\}', _html18)
check("und jeder hat einen Zustand in klappZu",
      _zustand18 is not None
      and sorted(_re13.findall(r'(\w+):', _zustand18.group(1))) == _klapp18)
# Gegenrichtung: ein Abschnitt, der als klappbar ausgezeichnet ist, aber keinen
# Rumpf hat, klappt zwar zu - nur bleibt dann alles stehen.
check("jeder klappbare Abschnitt hat auch einen Rumpf",
      _html18.count('class="abschnitt klappbar"') == _html18.count('class="klapp-rumpf'))

# Die drei Hauptaufgaben sind kein zweiter Satz Klapp-Panels mehr. Sie bilden
# einen eigenen Assistenten: genau drei feste Karten, von denen jede ueber ihren
# Kopf erneut erreichbar bleibt. So verschwindet die Aufnahmequelle nicht,
# sobald bereits ein Bild vorhanden ist.
_assistent18 = sorted(set(_re13.findall(r'data-scan-schritt="(\d+)"', _html18)))
check("der Scan-Assistent hat genau drei erreichbare Schritte",
      _assistent18 == ["1", "2", "3"])
check("jeder Assistent-Schritt hat einen Inhalt",
      all(f'id="scan-schritt-{_n18}-inhalt"' in _html18 for _n18 in _assistent18))
check("die Fensterliste hat einen sichtbaren Aktualisieren-Knopf",
      'id="scan-fenster-neu"' in _html18
      and '$("scan-fenster-neu").addEventListener("click", scanFensterPflegen)' in _html18)
check("der Quellenstand wird nicht neben dem Vollbild-Knopf eingequetscht",
      'class="scan-quelleninfo"' in _html18
      and '.scan-quellenstand{display:flex;flex-direction:column' in _html18
      and 'id="scan-quellenname"' in _html18)
check("die Slot-Suche nimmt Ecken in der mittleren Buehne an",
      'function scanSuchStelleAusBuehne(e)' in _html18
      and 'SC.modus !== "finden"' in _html18
      and 'buehne.addEventListener("click"' in _html18)
check("und begrenzt sie auf die vorhandenen Bildpixel",
      'bx = Math.max(0, Math.min(SC.foto.breite, bx));' in _html18
      and 'by = Math.max(0, Math.min(SC.foto.hoehe, by));' in _html18)
check("Aufnahmequelle und Bildwerkzeuge bleiben bis zum Scan gesperrt",
      "function scanKonfigurationOffen()" in _html18
      and "neu.disabled = !SC.pillow || !bereit" in _html18
      and "wahl.disabled = !bereit" in _html18
      and "Zuerst einen Scan anlegen oder auswählen" in _html18)
check("jeder Screenshot nennt der Bruecke seine Scan-Art",
      'rufScan("scan_foto", {art: scanArt})' in _html18)


# ============================================================================
section("Die Item-Maske: vier Angaben in der Liste statt eines Ein-Aus-Knopfs")

# **Ein Haken war zu wenig.** Die Liste konnte nur „gehoert dazu / gehoert nicht
# dazu"; Name, Kategorie und Prioritaet kosteten je einen Klick in die Liste,
# einen Blick nach rechts und einen Weg zurueck — bei sechzig Items sechzig Mal.
_maske18 = _html18[_html18.index("function scanItemMaske("):]
_maske18 = _maske18[:_maske18.index("\n/** Die Zustandszeile einer Item-Maske")]
for _feld18, _was18 in (('maskeName("item"', "Name"), ('setze("kategorie"', "Kategorie"),
                        ('setze("prioritaet"', "Prioritaet")):
    check(f"die Maske setzt {_was18}", _feld18 in _maske18)

# Und dieselbe Sache steht NICHT zweimal da. Der Inspektor als eigener Ort ist
# ganz entfallen: es gibt keine zweite Spalte mehr, in der ein Item stehen
# koennte — die rechte Spalte IST die Liste.
check("es gibt keinen zweiten Bauplan fuer ein Item",
      "function scanInspItem(" not in _html18)

# **Alle drei Listen stehen rechts, als Masken — Reiter, Filter und Eintraege
# zusammen.** Vorher standen Reiter und Filter links und nur die Item-Masken
# rechts: beim Umschalten schrumpfte links ein Abschnitt zusammen, waehrend
# rechts etwas erschien, und ein Hinweistext musste erklaeren, wohin der Inhalt
# verschwunden ist. Jetzt wandert der Block als Ganzes, und die linke Spalte
# steht still.
check("es gibt eine Regel, wo die Masken stehen",
      "function scanMaskenRechts()" in _html18)
check("und sie gilt fuer alle Item-Listen",
      'function scanMaskenRechts() {\n  return scanArt === "item";' in _html18)
check("Reiter, Filter und Liste baut EINE Funktion",
      "function scanListenBlock(tabs, filter, ziel)" in _html18)
# Und der zweite Listen-Block in der linken Spalte ist ersatzlos weg — samt
# der Funktion, die je Reiter entschied, welcher der beiden ihn fuellt.
check("und links bleibt gar nichts mehr stehen",
      'id="ab-listen"' not in _html18
      and "scanListeZeichnen" not in _html18)
check("der Hinweis, wohin der Inhalt umgezogen ist, entfaellt damit",
      "Die Item-Masken stehen rechts" not in _html18
      and "nur-reiter" not in _html18)

# Beide Item-Darstellungen bestehen optisch aus dem, was wirklich da ist. Die
# Lernvorschau setzt den Status ueber Bild und Felder; nach der Uebernahme gibt
# es keine leere ehemalige Haken-Spalte mehr.
check("die Lernvorschau ist als symmetrisches Raster gebaut",
      'grid-template-areas:". status status" "haken bild felder"' in _html18
      and 'class: "klein mono scan-review-status"' in _html18
      and 'class: "scan-review-bild"' in _html18
      and ".scan-review-bild{grid-area:bild;width:82px;height:82px" in _html18)
check("gelernte Items haben nur Bild und Felder als Spalten",
      'maske.classList.add("scan-item-maske")' in _html18
      and ".scan-maske.scan-item-maske{grid-template-columns:34px 56px minmax(0,1fr)}"
          in _html18)
check("ein zweiter Klick klappt ein geoeffnetes Item wieder zu",
      'if (gewaehlt && art === "item")' in _html18
      and 'rufScan("scan_waehlen", {art: "item", name: ""})' in _html18)
check("Bedienelemente klappen das Item beim Bearbeiten nicht zu",
      'e.target.closest("input, label, button, select, summary, details")' in _html18)

# **Dieselbe Bauform fuer Scans, Slots und Items.** Sie unterscheiden sich in
# dem, was drinsteht — nicht darin, wie man sie anfasst. Vorher war ein Slot
# eine Knopfzeile mit vier Zahlenfeldern in einer anderen Spalte, ein Item eine
# Maske; dieselbe Frage („wie benenne ich das um") hatte zwei Antworten.
check("Slots werden als Maske gebaut", "function scanSlotMaske(" in _html18)
check("Scans werden als Maske gebaut", "function scanScanMaske(" in _html18)
check("der gefuehrte Bereich hat ein klar beschriftetes Scan-Namensfeld",
      'id="scan-name"' in _html18
      and 'rufScan("scan_setzen", {name: SC.offen, feld: "name"' in _html18
      and 'namensfeld.disabled = !offen;' in _html18)
_bauform18 = [_n18 for _n18 in ("scanItemMaske", "scanSlotMaske", "scanScanMaske")
              if "maskeBauen(" not in _html18[_html18.index(f"function {_n18}("):
                                              _html18.index(f"function {_n18}(") + 3000]]
check(f"und alle drei ueber dieselbe Bauform ({_bauform18 or 'alle'})", not _bauform18)
# Der Fokus-Anker haengt an der id; ohne sie zaehlt `fokusMerken()` die
# Position ueber die ganze Spalte (s. u.).
check("die Bauform vergibt die id", 'id: maskeId(art, name)' in _html18)

# **Die alte Zeilen-Darstellung ist weg, nicht danebengestellt.** Zwei
# Darstellungen fuer dieselbe Liste waeren zwei Stellen, an denen ein Feld
# fehlen kann.
check("es gibt keine Slot-Zeile mehr neben der Slot-Maske",
      'class: "scan-zeile"' not in _html18[_html18.index("function scanListeSlots("):
                                           _html18.index("function scanListeItems(")])
check("Slots werden nach ihrer stabilen ID geordnet",
      "Number(a.id) > 0 ? Number(a.id)" in _html18
      and "(a.nummer || 0) - (b.nummer || 0)" not in _html18)
check("ID-Kachel und Vorschaubild haben feste einheitliche Breiten",
      ".scan-marke{width:34px;min-width:34px}" in _html18
      and "grid-template-columns:34px 56px minmax(0,1fr)" in _html18
      and ".scan-maske > .mini,.scan-maske > .kugel{width:56px;height:56px" in _html18)

# **Die Haken-Listen im Scan-Inspektor sind ersatzlos entfallen.** Sie waren der
# DRITTE Weg zur selben Frage: der Haken in jeder Maske sagt „gehoert zu diesem
# Scan", die Filterzeile kann „alle dazu/raus" — eine dritte Liste daneben ist
# eine Stelle mehr, an der eine Korrektur vorbeigeht.
check("keine dritte Liste fuer die Mitgliedschaft",
      "hakenListe(" not in _html18 and "hakenZeile(" not in _html18)
check("die Maske braucht keinen Mitgliedschaftshaken mehr",
      "function maskeHaken(art, name, dabei, marke)" not in _html18)
# Die Regel „gehoert dazu ODER wird gerade gesehen" stand in `hakenListe` — sie
# muss den Umzug ueberlebt haben, sonst verschwindet genau die Auskunft, fuer
# die es das Merkmal gibt: das Item kennt ein anderes Spiel schon, lerne es
# nicht ein zweites Mal.
check("Items kommen vollständig aus dem geöffneten Scan",
      "e.dabei || e.erkannt" not in _html18)
# **Was man GERADE abhakt, bleibt stehen.** Der Filter zeigt die Mitglieder —
# nimmt man dort einen Haken weg, faellt der Eintrag aus seiner eigenen
# Bedingung und verschwindet im selben Moment. Ein Verklicker war damit nicht
# zurueckzunehmen: das Ding, das man wieder anhaken will, ist weg.
check("es gibt keinen Merker für eine entfernte Mitgliedschaft",
      "scanZuletztAbgewaehlt" not in _html18)
check("es gibt keinen Mitgliedschaftsruf",
      "scanAbwahlMerken(art, name, dabei);" not in _html18)
# Und es wird wieder vergessen, sobald der Zusammenhang wechselt — sonst
# waechst die Liste ueber eine Sitzung hinweg zu genau dem Bestand an, den der
# Filter fernhalten soll.
check("beim Wechsel ist kein Mitgliedschaftszustand aufzuräumen",
      "scanAbwahlVergessen" not in _html18)
# Sichtbar bleiben heisst nicht: aussehen wie ein Mitglied.
check("kein scanfremder Eintrag wird blass dargestellt",
      "maske.classList.add(\"nicht-dabei\")" not in _html18
      and ".scan-maske.nicht-dabei{opacity:" not in _html18)

# **Die Einstellungen des gewaehlten Items stehen IN seiner Maske.** Zwei
# Bauplaene dafuer waeren zwei Stellen, an denen ein Feld fehlen kann — es gibt
# genau eine Funktion, und beide Wege rufen sie.
check("Vorlage, Marker und Konfidenz baut EINE Funktion",
      _html18.count("function scanItemDetails(") == 1)
check("die Maske klappt sie beim Gewaehlten auf",
      "(kasten) => scanItemDetails(kasten, i)" in _html18)
# Dasselbe fuer Slot und Scan: EIN Detailteil je Art, gerufen aus der Bauform.
for _art18, _bau18 in (("scanSlotDetails", "s"), ("scanScanDetails", "c")):
    check(f"{_art18} gibt es genau einmal",
          _html18.count(f"function {_art18}(") == 1)
    check(f"und die Maske klappt {_art18} auf",
          f"(kasten) => {_art18}(kasten, {_bau18})" in _html18)

# **Waehlen ist der Normalfall, tippen die Ausnahme.** Ein freies Textfeld
# allein macht aus „Helme" und „helme" zwei Kategorien - und Items derselben
# Kategorie konkurrieren miteinander, eine vertippte trennt ein Item still von
# seiner Gruppe. Eine `<datalist>` daneben war ein Angebot, das man kennen
# musste; sechzig Masken haetten sich ausserdem eine id teilen muessen.
check("die Maske waehlt die Kategorie ueber das gemeinsame Bedienelement",
      "kategorieWahl(i.kategorie" in _maske18)
check("und baut kein eigenes Textfeld mehr dafuer",
      "list: listenId" not in _html18 and "kategorienListe(" not in _html18)

# **Der Tipp-Modus muss den Neuaufbau ueberleben.** Die Ansicht wird nach jeder
# Bruecken-Antwort neu gebaut, und der Entwurf speichert 900 ms nach der letzten
# Aenderung von selbst: wer „+ neue Kategorie" waehlt und anfaengt zu tippen,
# saehe sein Feld sonst mitten im Wort wieder zur Auswahlliste werden. Dieselbe
# Mechanik wie bei `offeneHilfen` und `klappZu`.
check("es gibt einen Merker fuer offene Tipp-Felder",
      "const kategorieFrei = new Set()" in _html18)
check("und jede Stelle bringt ihren Schluessel mit",
      _html18.count("schluessel:") >= 3)
check("ein uebernommener Name beendet das Tippen",
      "if (schluessel && v) kategorieFrei.delete(schluessel);" in _html18)

# Dieselbe Rueckweg-Regel wie ueberall: hinein mit einem Klick, heraus auch.
check("ESC fuehrt aus dem Tippen zurueck in die Liste",
      'ev.key === "Escape" && werte().length' in _html18)

# **Derselbe Befehl heisst ueberall gleich.** Er stand im Assistenten als
# „Erkennung testen" und im Inspektor als „Items erkennen" — zwei Namen fuer
# einen Knopf, und man probiert beide aus, weil man annimmt, sie taeten
# Verschiedenes.
_erkenn18 = _re13.findall(r'>(Items erkennen|Erkennung testen)<', _html18)
_erkenn18 += _re13.findall(r'\}, "(Items erkennen|Erkennung testen)"\)', _html18)
check("beide Knoepfe fuer scan_erkennen heissen gleich",
      len(_erkenn18) >= 2 and set(_erkenn18) == {"Items erkennen"})

# **Mit offenem Scan sind die Items die Arbeit, nicht sein Name.** Wer einen
# Scan lud, landete auf der Scan-Liste und sah den Namen, den er gerade
# angeklickt hatte, ein zweites Mal.
check("die Listen-Vorgabe haengt am offenen Scan",
      'return SC && SC.offen ? "items" : "scans";' in _html18)
check("und eine eigene Entscheidung ueberstimmt sie",
      "if (scanListe) return scanListe;" in _html18)
check("das Oeffnen eines Scans setzt sie zurueck",
      "scanListe = scanReiterNachOeffnen;" in _html18)
# **Mit einer Ausnahme, und die ist der Grund fuer die Variable.** Wer einen
# Scan aus der Scan-Liste heraus oeffnet, arbeitet an Scans — springt der
# Reiter dann auf „Items", verschwindet genau die Maske, die sich soeben mit
# seinen Einstellungen aufgeklappt hat. Und damit war er nicht mehr zu
# loeschen: der Knopf stand in einer Spalte, die man mit dem Klick verliess.
check("aus der Scan-Liste heraus bleibt er stehen",
      'scanReiterNachOeffnen = "scans";' in _html18)
check("und der Wunsch gilt genau einmal",
      "scanReiterNachOeffnen = null;" in _html18)
check("der Loesch-Knopf liegt im Detailteil des Scans",
      '"scan_loeschen"' in _html18[_html18.index("function scanScanDetails("):
                                   _html18.index("function scanScanDetails(") + 3000])
_scan_details18 = _html18[_html18.index("function scanScanDetails("):
                          _html18.index("function scanScanDetails(") + 3000]
check("der Loesch-Knopf nennt den Scan seiner sichtbaren Maske",
      'rufScan("scan_loeschen", {name: c.name})' in _scan_details18)


# ============================================================================
section("Einen Item-Scan direkt aus seiner Maske löschen")

_sandL18 = tempfile.mkdtemp(prefix="studioscanloeschen_")
_cwdL18 = _os.getcwd()
_os.chdir(_sandL18)
try:
    Path("sequences/s").mkdir(parents=True)
    _bL18 = _SB8(_SEQ8(name="S"), Path("sequences/s/sequence.json"), "sequences")
    _bL18.scan_neu({"name": "Erster"})
    _bL18.scan_neu({"name": "Zweiter"})
    # Genau der Fehler aus der Ansicht: Der zweite Scan ist offen, aber der
    # allgemeine Auswahlzustand zeigt nicht mehr auf einen Scan. Der Knopf der
    # ersten Maske muss trotzdem genau den ersten löschen.
    _bL18.scan_art, _bL18.scan_name = "item", ""
    _zL18 = _bL18.scan_loeschen({"name": "Erster"})
    check("der mitgeschickte Maskenname entscheidet, was gelöscht wird",
          "Erster" not in _bL18.scans and "Zweiter" in _bL18.scans
          and "Erster" in _zL18["status"]["text"])
    _zL18 = _bL18.scan_loeschen()
    check("ohne Maskenname bleibt der offene Scan der Rückfall",
          not _bL18.scans and "Zweiter" in _zL18["status"]["text"])
finally:
    _os.chdir(_cwdL18)
    shutil.rmtree(_sandL18, ignore_errors=True)


# ============================================================================
section("Die Slot-ID ist stabil — die Stelle im Scan ist es nicht")

# **Zwei verschiedene Zahlen, zwei verschiedene Fragen.** Die Stelle im Lauf
# beantwortet „wann ist dieser aktive Slot dran". Die stabile ID bezeichnet
# dagegen auch einen ausgeschalteten Slot weiter. `ItemSlot` traegt
# deshalb jetzt eine eigene, stabile `id` — anders als beim Namen keine
# Referenz (der bleibt der Schluessel in slot_names), nur eine Kachel, die sich
# nicht mit der Mitgliedschaft mitbewegt.
import dataclasses as _dcN
check("ein Slot traegt jetzt eine eigene stabile ID",
      "id" in {f.name for f in _dcN.fields(_SLOT8)})

_sandN = tempfile.mkdtemp(prefix="studionummer_")
_cwdN = _os.getcwd()
_os.chdir(_sandN)
try:
    Path("sequences/s").mkdir(parents=True)
    _bN = _SB8(_SEQ8(name="S"), Path("sequences/s/sequence.json"), "sequences")
    _bN.scan_daten()
    _bN.scan_neu({"name": "Inv"})
    # Ueber den echten Weg anlegen (zwei Klicks), damit jeder Slot seine ID aus
    # `_naechste_slot_id()` bekommt — genau wie im Studio.
    for _i in range(3):
        _bN.scan_modus_setzen({"modus": "slot"})
        _bN.scan_klick({"x": _i * 100, "y": 0})
        _bN.scan_klick({"x": _i * 100 + 60, "y": 60})
    _namenN = [s.name for s in _bN.slots.values()]
    _slotsN = {s["name"]: s for s in _bN.scan_daten()["slots"]}

    check("jeder Slot des Scans kennt seine Stelle",
          [_slotsN[n]["nummer"] for n in _namenN] == [1, 2, 3])
    check("und wieviele es insgesamt sind", _slotsN[_namenN[1]]["gesamt"] == 3)
    check("und je eine eigene ID, keine doppelt",
          len({_slotsN[n]["id"] for n in _namenN}) == 3)

    # **Die Stelle im Scan und die Stelle im LAUF gehen auseinander**, sobald
    # „Slots rückwärts" an ist.
    check("vorwaerts sind beide gleich", _slotsN[_namenN[0]]["lauf"] == 1)
    _bN.scan_setzen({"name": "Inv", "feld": "reverse", "wert": True})
    _slotsN = {s["name"]: s for s in _bN.scan_daten()["slots"]}
    check("rueckwaerts dreht sich die Lauf-Stelle um",
          [_slotsN[n]["lauf"] for n in _namenN] == [3, 2, 1])
    check("die Stelle im Scan bleibt dieselbe",
          [_slotsN[n]["nummer"] for n in _namenN] == [1, 2, 3])

    _zN = _bN.scan_slot_setzen({"name": _namenN[1], "feld": "aktiv", "wert": False})
    _slotsN = {s["name"]: s for s in _zN["slots"]}
    check("ein Slot lässt sich ausschalten, ohne seine Daten zu löschen",
          _slotsN[_namenN[1]]["aktiv"] is False
          and _namenN[1] in _bN.slots and len(_bN.scans["Inv"].slots) == 3)
    check("nur aktive Slots bekommen eine laufende Nummer",
          [_slotsN[n]["nummer"] for n in _namenN] == [1, None, 2])
    _bN.scan_slot_setzen({"name": _namenN[1], "feld": "aktiv", "wert": True})
    _slotsN = {s["name"]: s for s in _bN.scan_daten()["slots"]}
    check("und derselbe Schalter schaltet ihn wieder ein",
          _slotsN[_namenN[1]]["aktiv"] is True
          and [_slotsN[n]["nummer"] for n in _namenN] == [1, 2, 3])

    # Die ID übersteht echte Bearbeitung; eine Mitgliedschaft gibt es nicht mehr.
    _idN = _slotsN[_namenN[1]]["id"]
    _bN.scan_slot_setzen({"name": _namenN[1], "feld": "name", "wert": "Mitte"})
    _slotsN = {s["name"]: s for s in _bN.scan_daten()["slots"]}
    check("die ID bleibt beim Umbenennen gleich", _slotsN["Mitte"]["id"] == _idN)
    check("die Stelle im Scan bleibt beim Umbenennen gleich",
          _slotsN["Mitte"]["nummer"] == 2)

    # Ein weiterer Slot gehört automatisch demselben Scan und bekommt beides.
    _bN.slots["Weiter"] = _SLOT8(name="Weiter", scan_region=(0, 0, 10, 10),
                                 click_pos=(5, 5), id=_bN._naechste_slot_id())
    _bN._objekte_angleichen()
    _slotsN = {s["name"]: s for s in _bN.scan_daten()["slots"]}
    check("ein neuer Slot hat sofort eine Stelle", _slotsN["Weiter"]["nummer"] == 4)
    check("und eine stabile ID", _slotsN["Weiter"]["id"] > 0)
    _slot_maskeN = _html18[_html18.index("function scanSlotMaske("):
                            _html18.index("function scanSlotStand(")]
    check("jede Slot-Kachel baut einen echten Ein-Aus-Schalter",
          'type: "checkbox"' in _slot_maskeN
          and 'setze("aktiv", box.checked)' in _slot_maskeN
          and '"aria-label": s.name + " ein- oder ausschalten"' in _slot_maskeN)
    check("der nutzlose Daneben-Knopf ist vollständig entfernt",
          "scan_slot_doppeln" not in _html18)

    _itemN = _ITEM8(name="Parkbar", marker_colors=[(1, 2, 3)])
    _bN.items[_itemN.name] = _itemN
    _bN._objekte_angleichen()
    _zN = _bN.scan_item_setzen({"name": "Parkbar", "feld": "aktiv", "wert": False})
    _itemsN = {i["name"]: i for i in _zN["items"]}
    check("ein Item lässt sich ausschalten, ohne seine Daten zu löschen",
          _itemsN["Parkbar"]["aktiv"] is False
          and "Parkbar" in _bN.items and len(_bN.scans["Inv"].items) == 1)
    _bN.scan_item_setzen({"name": "Parkbar", "feld": "aktiv", "wert": True})
    check("und dasselbe Item lässt sich wieder einschalten",
          _bN.items["Parkbar"].enabled is True)
    _item_maskeN = _html18[_html18.index("function scanItemMaske("):
                            _html18.index("function scanItemStand(")]
    check("jede Item-Kachel baut einen echten Ein-Aus-Schalter",
          'type: "checkbox"' in _item_maskeN
          and 'setze("aktiv", box.checked)' in _item_maskeN
          and '"aria-label": i.name + " ein- oder ausschalten"' in _item_maskeN)
    _bN.scan_alle_schalten({"art": "slot", "aktiv": False})
    check("Alle aus schaltet wirklich jeden Slot aus",
          not any(s.enabled for s in _bN.slots.values()))
    _bN.scan_alle_schalten({"art": "slot", "aktiv": True})
    check("Alle ein schaltet wirklich jeden Slot ein",
          all(s.enabled for s in _bN.slots.values()))
    _bN.scan_alle_schalten({"art": "item", "aktiv": False})
    check("Alle aus schaltet wirklich jedes Item aus",
          not any(i.enabled for i in _bN.items.values()))
    check("ausgeschaltete Items sind auch im Studio-Test keine Kandidaten",
          _bN._kandidaten() == [])
    check("und der Assistent nennt Items dann wieder als offenen Schritt",
          not next(s for s in _bN._schritte() if s["nr"] == 3)["fertig"])
    _bN.scan_alle_schalten({"art": "item", "aktiv": True})
    check("Alle ein schaltet wirklich jedes Item ein",
          all(i.enabled for i in _bN.items.values()))
    check("der wechselnde Sammelknopf steht direkt bei der Sortierung",
          '"↕ Sortieren"' in _html18
          and 'irgendAn ? "Alle aus" : "Alle ein"' in _html18
          and 'const irgendAn = eintraege.some((e) => !!e.aktiv)' in _html18
          and '{art: art, aktiv: !irgendAn}' in _html18)
finally:
    _os.chdir(_cwdN)
    shutil.rmtree(_sandN, ignore_errors=True)


# ============================================================================
section("Altbestand ohne ID wird einmalig nachgezogen")

# **Kein Migrationsschritt — Backfill beim ersten Laden im Studio.** Eine alte
# `slots.json` kennt das Feld nicht; `_slot_from_dict` liest dann `id=0`. Damit
# die Anzeige nicht dauerhaft „#0" fuer den halben Bestand zeigt, vergibt
# `_slot_ids_vergeben()` beim ersten Laden frische IDs — in stabiler Reihenfolge
# (Name), sonst hinge die Zuteilung von der Dict-Reihenfolge der JSON-Datei ab.
_sandA = tempfile.mkdtemp(prefix="studioaltid_")
_cwdA = _os.getcwd()
_os.chdir(_sandA)
try:
    Path("sequences/s/item_scans").mkdir(parents=True)
    import json as _jsonA
    Path("sequences/s/item_scans/inv.json").write_text(_jsonA.dumps({
        "name": "Inv", "items": {}, "slots": {
            "Slot B": {"scan_region": [0, 0, 60, 60], "click_pos": [30, 30]},
            "Slot A": {"scan_region": [100, 0, 160, 60], "click_pos": [130, 30]},
        }}), encoding="utf-8")
    _bA = _SB8(_SEQ8(name="S"), Path("sequences/s/sequence.json"), "sequences")
    _zA = _bA.scan_daten()
    _idsA = {s["name"]: s["id"] for s in _zA["slots"]}
    check("beide bekommen eine ID", all(_idsA.values()))
    check("keine doppelt", len(set(_idsA.values())) == 2)
    check("vergeben in Namens-Reihenfolge — nicht nach Dict-Zufall",
          _idsA["Slot A"] < _idsA["Slot B"])
    # Das ist ein Schreibzugriff wert: ohne ihn wuerde bei jedem Start neu
    # gewuerfelt, und die gerade zugesicherte Stabilitaet waere eine Luege.
    check("und der Stand gilt als ungespeichert, bis es geschrieben ist",
          _zA["dirty"] is True)

    # Zweiter Lauf auf derselben (jetzt im Speicher befindlichen) Bruecke:
    # kein erneutes Wuerfeln, dieselben IDs.
    _zA2 = _bA.scan_daten()
    check("ein zweiter Aufruf vergibt nichts neu",
          {s["name"]: s["id"] for s in _zA2["slots"]} == _idsA)
finally:
    _os.chdir(_cwdA)
    shutil.rmtree(_sandA, ignore_errors=True)

# **Und zwar NATUERLICH sortiert, nicht Zeichen fuer Zeichen.** Ein reiner
# String-Vergleich stellt „Slot 10" zwischen „Slot 1" und „Slot 2" — bei
# sechzig durchnummerierten Slots bekam „Slot 2" dann die ID 12 und „Slot 3"
# die 23. Die IDs waren stabil und trotzdem unbrauchbar, weil sie in Spruengen
# dastanden.
_sandA2 = tempfile.mkdtemp(prefix="studioaltid2_")
_cwdA2 = _os.getcwd()
_os.chdir(_sandA2)
try:
    Path("sequences/s/item_scans").mkdir(parents=True)
    import json as _jsonA2
    _jsonA2_slots = {f"Slot {_i}": {"scan_region": [0, _i * 3, 60, _i * 3 + 60],
                                    "click_pos": [30, _i * 3 + 30]}
                     for _i in range(1, 21)}
    Path("sequences/s/item_scans/inv.json").write_text(
        _jsonA2.dumps({"name": "Inv", "items": {}, "slots": _jsonA2_slots}),
        encoding="utf-8")
    _bA2 = _SB8(_SEQ8(name="S"), Path("sequences/s/sequence.json"), "sequences")
    _idsA2 = {s["name"]: s["id"] for s in _bA2.scan_daten()["slots"]}
    check("'Slot 2' bekommt die 2, nicht die 12",
          _idsA2["Slot 2"] == 2 and _idsA2["Slot 3"] == 3)
    check("und 'Slot 20' die 20", _idsA2["Slot 20"] == 20)
    check("lueckenlos von 1 bis 20",
          sorted(_idsA2.values()) == list(range(1, 21)))
finally:
    _os.chdir(_cwdA2)
    shutil.rmtree(_sandA2, ignore_errors=True)


# ============================================================================
section("Die Slot-Kachel zeigt die ID, nicht die (bewegliche) Stelle")

# **Sie steht UNTER dem Schalter, als eigene Kachel.** Vor dem Namensfeld nahm
# sie ihm die Breite, liess die Namen ohne Nummer an einer anderen Kante
# beginnen — und beim Bearbeiten schob sich das Feld darueber.
# Und zwar in DERSELBEN Kachel-Klasse wie ueberall sonst (`zahl`) — eine
# eigene daneben waere ein zweiter Bauplan fuer dasselbe Aussehen.
check("die Ansicht zeigt die ID als Kachel",
      '"#" + s.id' in _html18 and 'el("span", {class: "zahl",' in _html18)
# Die Stelle im Scan steht nur noch im TOOLTIP — sie ist die Zusatzauskunft,
# nicht mehr die angezeigte Zahl selbst.
check("die Stelle im Scan steht nur noch im Tooltip",
      '". von " + s.gesamt' in _html18 and '"#" + s.nummer' not in _html18)
# Die Groesse ist ein gemessener WERT, kein Satz — also dieselbe Kachel.
check("und die Groesse daneben ebenso",
      'el("span", {class: "zahl"}, s.breite + "×" + s.hoehe)' in _html18)
# Beide auf einer Hoehe: der Schalter oben, die ID unten, und die Spalte
# so hoch wie die Zeile. Ohne `stretch` waere sie nur so hoch wie ihr Inhalt.
check("und beide auf einer Hoehe",
      "align-self:stretch;justify-content:space-between}" in _html18)
# Und die Vorschau daneben ist ein QUADRAT, das mit der Zeile waechst — nicht
# ein Rechteck, das nur in der Hoehe stretcht. `aspect-ratio:1` haelt die
# Breite an die (gestretchte) Hoehe gebunden; die Spalte braucht dafuer `auto`
# statt einer festen Breite, sonst gaebe es keinen Spielraum zum Mitwachsen.
check("die Vorschau ist ein Quadrat, kein Rechteck",
      ".scan-maske > .mini,.scan-maske > .kugel{width:56px;height:56px"
      in _html18)
check("und die Spalten bleiben bei jeder Ziffernzahl gleich",
      "grid-template-columns:34px 56px minmax(0,1fr)" in _html18)

# Zwei Eigenschaften, die der Pin weiter oben nicht nennt: wohin der Altbestand
# faellt, und was bei gleicher Lage entscheidet. Slots ohne ID landen am ENDE —
# vorn stuende der ungepflegte Rest ueber allem anderen.
_sort18 = _html18[_html18.index("function scanListeSlots("):]
_sort18 = _sort18[:_sort18.index("\nfunction ", 10)]
check("Slots ohne ID stehen hinten, nicht vorn",
      "Number.MAX_SAFE_INTEGER" in _sort18)
check("und bei gleicher Lage entscheidet der Name natuerlich sortiert",
      "nachNamen(a.name, b.name)" in _sort18)


# ============================================================================
section("Alle Slots / alle Items dieses Scans loeschen")

# **Nicht dasselbe wie „alle raus".** Das nimmt nur aus der Mitgliedschaft
# heraus - die Slots/Items bleiben im Bestand. `scan_alle_loeschen` loescht sie
# wirklich; einzeln durchklicken war bei fuenfzig Stueck der Grund, warum man
# diesen Knopf sucht.
_sandL = tempfile.mkdtemp(prefix="studioallelöschen_")
_cwdL = _os.getcwd()
_os.chdir(_sandL)
try:
    Path("sequences/s").mkdir(parents=True)
    _bL = _SB8(_SEQ8(name="S"), Path("sequences/s/sequence.json"), "sequences")
    _bL.scan_daten()
    _bL.scan_neu({"name": "Inv"})
    for _i in range(1, 4):
        _bL.slots[f"Slot {_i}"] = _SLOT8(
            name=f"Slot {_i}", scan_region=(_i * 70, 0, _i * 70 + 60, 60),
            click_pos=(_i * 70 + 30, 30), id=_i)
        _bL._dazu("slot", f"Slot {_i}")
        _bL.items[f"Item {_i}"] = _ITEM8(name=f"Item {_i}")
        _bL._dazu("item", f"Item {_i}")
    # Ein Slot eines ANDEREN Scans - darf beim Loeschen von "Inv" nicht
    # verschwinden, sonst waere der Bezug nicht der Scan, sondern der Bestand.
    _bL.scan_neu({"name": "Anderes"})
    _bL.slots["Fremd"] = _SLOT8(name="Fremd", scan_region=(0, 200, 60, 260),
                                click_pos=(30, 230), id=99)
    _bL._objekte_angleichen()
    _bL.scan_oeffnen({"name": "Inv"})

    check("unbekannte Art wird abgelehnt",
          _bL.scan_alle_loeschen({"art": "quatsch"})["status"]["art"] == "err")

    _zL = _bL.scan_alle_loeschen({"art": "slot"})
    check("alle drei Slots dieses Scans sind weg",
          all(f"Slot {i}" not in _bL.slots for i in (1, 2, 3)))
    check("der Slot des ANDEREN Scans bleibt",
          [s.name for s in _bL.scans["Anderes"].slots] == ["Fremd"])
    check("und die Meldung nennt die Anzahl", "3 Slots gelöscht" in _zL["status"]["text"])

    _zL = _bL.scan_alle_loeschen({"art": "item"})
    check("alle drei Items dieses Scans sind weg",
          all(f"Item {i}" not in _bL.items for i in (1, 2, 3)))

    # **Ein Griff, ein Rueckgaengig** — dieselbe Regel wie beim einzelnen
    # Loeschen: STRG+Z holt den ganzen Abzug zurueck, nicht nur einen Slot.
    _bL.scan_rueckgaengig()
    check("ein STRG+Z holt alle Items zurueck",
          all(f"Item {i}" in _bL.items for i in (1, 2, 3)))
    _bL.scan_rueckgaengig()
    check("ein zweites STRG+Z holt alle Slots zurueck",
          all(f"Slot {i}" in _bL.slots for i in (1, 2, 3)))

    # Nichts zu loeschen wird gesagt, nicht stillschweigend hingenommen.
    _bL.slots.clear()
    _bL.items.clear()
    check("ohne Slots wird das gesagt",
          _bL.scan_alle_loeschen({"art": "slot"})["status"]["art"] == "warn")
    check("ohne Items ebenso",
          _bL.scan_alle_loeschen({"art": "item"})["status"]["art"] == "warn")
finally:
    _os.chdir(_cwdL)
    shutil.rmtree(_sandL, ignore_errors=True)

check("die Ansicht bietet den Knopf pro Art an",
      'rufScan("scan_alle_loeschen", {art: art})' in _html18)
check("und er ist deutlich als gefaehrlich markiert",
      'class: "btn gefahr", disabled: !gesamt.length' in _html18)


# ============================================================================
section("Die Zahlen-Kachel hat eine feste Breite, egal wie viele Ziffern")

# **„#3" schob sich sonst weniger als „#55" und „#123" nochmal anders** — die
# Kachel soll bei jeder Ziffernzahl an derselben Stelle stehen.
check("die Zahlen-Kachel in der Marke hat eine feste Mindestbreite",
      ".scan-marke{width:34px;min-width:34px}" in _html18)


# ============================================================================
section("Der Fokus ueberlebt ein Umbenennen")

# **Ein Umbenennen aendert die Identitaet — und damit die id, an der der Fokus
# haengt.** Ohne den Hinweis suchte `fokusHerstellen()` nach dem alten Namen und
# fand nichts; genau beim Namen tippt man aber, und genau dort faellt es auf.
check("wer umbenennt, sagt die neue id an",
      "function fokusUmbenennung(von, nach)" in _html18)
check("und maskeName() tut es fuer alle drei Arten",
      "fokusUmbenennung(maskeId(art, name), maskeId(art, neu));" in _html18)
# **Umbenennen aendert den Namen, nicht den Rang.** Die gemerkte Reihenfolge
# haengt am Namen — ohne das Nachziehen galt ein gerade umbenanntes Item als
# neu und rutschte ans Ende seiner Gruppe. Genau beim Namen tippt man aber.
check("und der Rang wird ebenfalls nachgezogen",
      "scanOrdnungUmbenennen(art, name, neu);" in _html18
      and "function scanOrdnungUmbenennen(art, alt, neu)" in _html18)
# Lehnt die Bruecke den neuen Namen ab, heisst das Item weiter wie vorher —
# und behaelt trotzdem seinen Platz.
check("beide Namen stehen dafuer im Merkposten",
      "merk.splice(i, 1, {name: neu, gruppe: merk[i].gruppe}, merk[i]);" in _html18)
check("fokusMerken loest den Hinweis genau einmal ein",
      "const umbenannt = fokusUmbenannt;" in _html18
      and "fokusUmbenannt = null;" in _html18)
# Lehnt die Bruecke den neuen Namen ab (schon vergeben), heisst die Maske
# danach weiter wie vorher — und der Fokus soll trotzdem stehen bleiben.
check("und die alte id bleibt als Rueckfall",
      "alt: kasten.id" in _html18
      and "document.getElementById(merk.id)\n              || document.getElementById(merk.alt)" in _html18)


# ============================================================================
section("Prioritaeten: welche vergeben sind, und was ein neues Item bekommt")

# **„Welche Prioritaet ist noch frei" war aus einer Zahl im Feld nicht zu
# beantworten.** Die Uebersicht zeigte nur die vergebenen Raenge; ob P2 belegt
# ist oder fehlt, sah man erst, wenn man P1, P3, P4 las und selbst nachzaehlte.
check("die Uebersicht spannt jeden Rang auf, nicht nur die belegten",
      "function prioritaetsBelegung(kategorie)" in _html18
      and "for (let p = 1; p <= hoechste + 1; p += 1)" in _html18)
check("ein freier Rang wird als Luecke gezeichnet",
      '"P" + r.prio + " · " + (frei ? "frei" : r.namen.join(", "))' in _html18
      and ".prioritaets-chip.frei{border:1px dashed" in _html18)
# Eine getippte P99 darf das nicht auf hundert Kacheln aufspannen.
check("und eine Ausreisser-Zahl spannt sie nicht auf",
      "PRIO_MAX_ZEIGEN" in _html18)
# Zwei Items auf demselben Rang entscheidet die Scan-Reihenfolge — also der
# Zufall. Das steht AM FELD, nicht erst im aufgeklappten Detail: getippt wird
# in der Maske.
check("eine doppelte Prioritaet faellt schon in der Liste auf",
      "function prioritaetDoppelt(item)" in _html18
      and '"P" + i.prioritaet + " doppelt"' in _html18)
check("und das Feld selbst ist markiert",
      'class: kollision.length ? "doppelt" : ""' in _html18
      and ".scan-maske input.doppelt{" in _html18)

_sandP = tempfile.mkdtemp(prefix="studioprio_")
_cwdP = _os.getcwd()
_os.chdir(_sandP)
try:
    Path("sequences").mkdir()
    _bP = _SB8(_SEQ8(name="S"), Path("sequences/s/sequence.json"), "sequences")
    _bP.scan_daten()
    for _n, _k, _p in (("Helm A", "Helme", 1), ("Helm B", "Helme", 2),
                       ("Neu", None, 1)):
        _bP.items[_n] = _ITEM8(name=_n, category=_k, priority=_p)

    # **Ein Rang, den es schon gibt, ist kein Rang.** Wer ein Item in eine
    # Kategorie schiebt, hat ueber seine Prioritaet nichts gesagt — dann ist der
    # naechste freie Platz die einzige Antwort, die nicht raet.
    _zP = _bP.scan_item_setzen({"name": "Neu", "feld": "kategorie", "wert": "Helme"})
    check("ein Item in einer besetzten Kategorie ruecht auf den freien Rang",
          _bP.items["Neu"].priority == 3)
    check("und es wird gesagt, statt still zu passieren",
          "P1 war in 'Helme' vergeben" in _zP["status"]["text"])

    # Eine LUECKE wird gefuellt, nicht ans Ende gehaengt.
    _bP.items["Helm B"].priority = 3
    _bP.items["Neu"].category = None
    _bP.items["Neu"].priority = 1
    _zP = _bP.scan_item_setzen({"name": "Neu", "feld": "kategorie", "wert": "Helme"})
    check("und zwar auf die erste Luecke", _bP.items["Neu"].priority == 2)

    # Sitzt es allein auf seiner Zahl, wird nichts verschoben.
    _bP.items["Frei"] = _ITEM8(name="Frei", category=None, priority=9)
    _bP.scan_item_setzen({"name": "Frei", "feld": "kategorie", "wert": "Helme"})
    check("eine freie Zahl bleibt, wie sie ist", _bP.items["Frei"].priority == 9)

    # Eine ausdruecklich getippte Zahl fasst niemand an — auch keine doppelte:
    # sie kann gewollt sein, und ungefragt zu verschieben waere schlimmer.
    _bP.scan_item_setzen({"name": "Frei", "feld": "prioritaet", "wert": 1})
    check("eine getippte Zahl gilt, auch wenn sie doppelt ist",
          _bP.items["Frei"].priority == 1)

    # Ohne Kategorie gibt es keine Konkurrenz und damit nichts einzuordnen.
    _bP.items["Solo"] = _ITEM8(name="Solo", category=None, priority=1)
    _bP.scan_item_setzen({"name": "Solo", "feld": "kategorie", "wert": ""})
    check("ohne Kategorie bleibt alles, wie es ist",
          _bP.items["Solo"].priority == 1)
finally:
    _os.chdir(_cwdP)
    shutil.rmtree(_sandP, ignore_errors=True)


# ============================================================================
section("Die Liste sortiert sich beim Laden, nicht beim Tippen")

# **Sortierte sich die Liste nach JEDER Aenderung neu, springt genau das Item
# weg, an dem man gerade tippt**: man tippt eine 2, die Zeile rutscht drei
# Plaetze hoch, und das naechste Feld ist ein anderes.
check("die Reihenfolge wird gemerkt", "let scanOrdnung = {item: null, slot: null}"
      in _html18)
check("und beim Zeichnen angewandt statt neu gerechnet",
      "const rang = scanOrdnungRang(\"item\");" in _html18
      and "rang ? (rang(a.name) - rang(b.name)) || frisch(a, b)" in _html18)
# **Die Kategorie war der erste Sortierschluessel und damit das letzte Feld,
# das die Zeile noch wegspringen liess.** Steht eine gemerkte Reihenfolge, gilt
# ausschliesslich sie — auch fuer die Gruppen.
check("mit Merkposten entscheidet nur er",
      "function scanOrdnungGruppe(art)" in _html18
      and "const gruppe = scanOrdnungGruppe(\"item\");" in _html18)
check("die Ueberschrift kommt aus der eingefrorenen Gruppe",
      "const gefroren = gruppe ? gruppe(i.name) : null;" in _html18)
# Sonst reisst ein gerade geaendertes Item eine zweite Ueberschrift mitten in
# die Liste — wohin es wandert, sagt stattdessen seine Zustandszeile.
check("und der Wechsel wird an der Maske angesagt",
      '"→ " + (i.kategorie || "ohne Kategorie")' in _html18)
# Ohne Merkposten (erster Aufbau, „Sortieren", Neu laden) wird frisch geordnet,
# und dort ist die Kategorie wieder der erste Schluessel.
check("frisch geordnet gruppiert wieder nach Kategorie",
      ': ((a.kategorie || "").localeCompare(b.kategorie || "", "de")' in _html18)
check("es gibt einen Knopf dafuer", '"↕ Sortieren"' in _html18)
# Der Phasen-Papierkorb stand früher in einer zu breiten Werkzeugzeile und lief
# optisch unter END. Loop-Phasen werden wie Blöcke ausgewählt und mit Entf
# gelöscht; ein zweiter Löschweg in der Kachel wäre nur wieder uneindeutig.
_phase_funktion18 = _html18[_html18.index("function zeichnePhase("):
                            _html18.index("function ablage(")]
check("Loop-Phasen lassen sich im Kopf auswählen",
      "gewaehltePhase = phase.index" in _phase_funktion18
      and '" gewaehlt"' in _phase_funktion18)
check("der Phasen-Papierkorb ist vollständig entfernt",
      "papierkorb()" not in _html18 and "phase-loeschen" not in _html18)
check("Entf löscht die ausgewählte Loop-Phase",
      'e.key === "Delete" && gewaehltePhase !== null' in _html18
      and 'ruf("phase_loeschen", {phase: phase})' in _html18)
_frisch18 = ["scan_neu_laden", "scan_lernvorschau_uebernehmen", "scan_oeffnen"]
check("und beim Laden sortiert es von selbst",
      all(n in _html18[_html18.index("async function rufScan("):
                       _html18.index("async function rufScan(") + 1400]
          for n in _frisch18))

# **Der Kopf bleibt beim Scrollen stehen.** Bei sechzig Masken war die
# Reiterleiste nach drei Umdrehungen weg — und mit ihr der Weg in eine andere
# Liste, der Speichern-Knopf und das Rueckgaengig.
check("Reiter und Filter stehen im Kopf, nicht in der Liste",
      "kopf.appendChild(tabs);" in _html18)
check("und der Kopf klebt oben",
      ".scan-kopf{position:sticky;top:0" in _html18
      and 'class: "abschnitt scan-kopf"' in _html18)
# Ohne eigenen Hintergrund scrollen die Masken sichtbar dahinter durch.
check("mit eigenem Hintergrund", "background:var(--panel)}" in
      _html18[_html18.index(".scan-kopf{"):_html18.index(".scan-kopf{") + 120])
# **Der Rueckgaengig-Knopf heisst „Zurück", nicht „'Bogen Zeus': Prioritaet".**
# Der letzte Schritt IM Namen ist die genauere Auskunft und die schlechtere
# Beschriftung: sie wurde zweizeilig, wechselte bei jeder Aenderung ihre Laenge,
# und was der Knopf TUT, musste man aus ihr heraussuchen.
check("der Rueckgaengig-Knopf traegt einen festen Namen",
      '"↶ Zurück")));' in _html18)
check("und die Beschreibung steht im Tooltip",
      '"STRG+Z — nimmt zurück: " + SC.undo.was' in _html18)
# Der Schalter bekommt dieselbe Flaeche wie seine Nachbarn — sonst haengt er als
# loser Text zwischen Reiterleiste und Knopfreihe.
check("ein Mitgliedschafts-Filterschalter ist ersatzlos weg",
      "nurDabei" not in _html18)
check("die Reiterleiste nimmt die ganze Breite",
      ".tabs.breit .tab{flex:1 1 0" in _html18 and '"tabs klein breit"' in _html18)
# **Der Kopf ist eine Spalte, kein Fliesstext.** „alle dazu" stand als kurzer
# Stummel neben dem Schalter, „Sortieren" als noch kuerzerer darunter, und die
# Klappliste dazwischen zog sich ueber alles — drei Breiten untereinander lesen
# sich wie drei Ranguebergaenge, obwohl es dreimal dasselbe ist.
check("die Filterzeile ist ein Raster mit voller Breite",
      ".scan-filter{display:grid;grid-template-columns:1fr" in _html18
      and ".scan-filter > *{min-width:0;width:100%}" in _html18)
# Ein Schalter ist Text mit Kaestchen davor — als Kachel bekommt er dieselbe
# Flaeche wie seine Nachbarn, statt als loser Text dazwischen zu haengen.
check("und der Schalter traegt seine eigene Kachel",
      ".scan-filter > label.an.kachel{width:100%;justify-self:stretch;" in _html18)
# Zwei Knoepfe in einer Zeile teilen sie sich zu gleichen Teilen: vorher nahm
# „Items erkennen" den Rest und „Rueckgaengig" seine Textbreite — bei einem
# langen Rueckgaengig-Namen kippte das Verhaeltnis von Zeile zu Zeile.
check("zwei Knoepfe teilen sich die Zeile gleichmaessig",
      "grid-template-columns:repeat(auto-fit,minmax(min(100%,118px),1fr))" in _html18
      and '"knopfpaar"' in _html18)
# **Gleiche Spalten duerfen nichts kosten, was man lesen muss.** Mit fester
# Spaltenzahl schnitten drei Knoepfe in 290 px die Beschriftung ab
# („Item ler…") — ein abgeschnittenes Wort ist schlimmer als eine zweite Zeile.
check("und schneiden dabei keine Beschriftung ab",
      "white-space:normal}" in _html18[_html18.index(".knopfpaar > .btn{"):
                                       _html18.index(".knopfpaar > .btn{") + 90])
# Der Wortschatz ist zu zweit vollstaendig: EIN Knopf ueber die volle Breite
# ist `btn breit`, mehrere nebeneinander sind ein `knopfpaar`. Ein `wachse` in
# einer Knopfzeile waere die dritte Antwort auf dieselbe Frage.
_knopfzeilen18 = _html18.count('class: "knopfpaar"')
check(f"und die Regel gilt ueberall ({_knopfzeilen18} Zeilen)",
      _knopfzeilen18 >= 6)
check("kein Knopf dehnt sich mehr auf Kosten seiner Nachbarn",
      '"btn wachse"' not in _html18)
check("und keiner davon dehnt sich mehr auf Kosten des anderen",
      "wachse" not in _html18[_html18.index('el("div", {class: "knopfpaar"}'):
                              _html18.index('el("div", {class: "knopfpaar"}') + 1200])


# ============================================================================
section("Der Bestaetigungsklick eines Items")

_sandB = tempfile.mkdtemp(prefix="studiobestaetigung_")
_cwdB = _os.getcwd()
_os.chdir(_sandB)
try:
    Path("sequences").mkdir()
    _bB = _SB8(_SEQ8(name="S"), Path("sequences/s/sequence.json"), "sequences")
    _bB.scan_daten()          # erst laden, dann anlegen — sonst raeumt der
    _bB.items["Trank"] = _ITEM8(name="Trank")   # Loader das Item wieder weg
    from autoclicker.editors.sequence_studio.model import PalettePoint as _PPB
    _bB.points.append(_PPB(id=7, x=400, y=300, name="OK-Knopf"))
    _pidB = 7

    # **Das Feld gab es im Modell und in den Konsolen-Editoren seit jeher** — im
    # Studio war es die einzige Item-Eigenschaft ohne Bedienelement. Ohne die
    # Bestaetigung bleibt das Popup stehen, und der Scan erreicht den naechsten
    # Slot gar nicht mehr.
    _zB = _bB.scan_daten()
    _itemB = next(i for i in _zB["items"] if i["name"] == "Trank")
    check("ohne Bestaetigung steht dort nichts", _itemB["bestaetigung"] is None)

    _zB = _bB.scan_item_setzen({"name": "Trank", "feld": "bestaetigung", "wert": _pidB})
    check("ein Punkt laesst sich setzen",
          _bB.items["Trank"].confirm_point_id == _pidB)
    _itemB = next(i for i in _bB.scan_daten()["items"] if i["name"] == "Trank")
    check("und die Ansicht nennt ihn beim Namen",
          _itemB["bestaetigung"]["punkt_id"] == _pidB
          and "OK-Knopf" in _itemB["bestaetigung"]["text"])
    # **Die Koordinate steht in points.json, sonst nirgends.** `confirm_point`
    # ist der abgeleitete Arbeitswert — dieselbe Rolle wie `action_x/y`.
    check("der abgeleitete Arbeitswert wird mitgezogen",
          _bB.items["Trank"].confirm_point is not None
          and (_bB.items["Trank"].confirm_point.x,
               _bB.items["Trank"].confirm_point.y) == (400, 300))

    # Ein Punkt, den es nicht gibt, wird ABGELEHNT statt still gesetzt: sonst
    # klickte der Lauf auf (0, 0).
    _zB = _bB.scan_item_setzen({"name": "Trank", "feld": "bestaetigung", "wert": 999})
    check("ein unbekannter Punkt wird abgelehnt", _zB["status"]["art"] == "err")
    check("und der alte bleibt stehen", _bB.items["Trank"].confirm_point_id == _pidB)

    _bB.scan_item_setzen({"name": "Trank", "feld": "bestaetigung_verzoegerung",
                          "wert": 1.25})
    check("die Wartezeit davor ist einstellbar",
          _bB.items["Trank"].confirm_delay == 1.25)
    check("eine negative wird abgelehnt",
          _bB.scan_item_setzen({"name": "Trank", "feld": "bestaetigung_verzoegerung",
                                "wert": -1})["status"]["art"] == "err")

    # Leer heisst „keine Bestaetigung" und ist etwas anderes als Punkt 0.
    _bB.scan_item_setzen({"name": "Trank", "feld": "bestaetigung", "wert": ""})
    check("und sie laesst sich wieder abschalten",
          _bB.items["Trank"].confirm_point_id is None
          and _bB.items["Trank"].confirm_point is None)

    # **Die Stelle zieht man im Bild, statt zwei Zahlen zu tippen** — dasselbe
    # Werkzeug, das Boss und Icon schon benutzen. Ein zweites daneben waere
    # dieselbe Frage mit einer zweiten Antwort.
    _bB.scan_waehlen({"art": "item", "name": "Trank"})
    check("das Klickpunkt-Werkzeug kennt jetzt auch Items",
          _bB._ziel_pruefen("item") == ("item", "Trank"))
    check("und ohne gewaehltes Item nicht", _bB._ziel_pruefen("scan") is None)
finally:
    _os.chdir(_cwdB)
    shutil.rmtree(_sandB, ignore_errors=True)


# ============================================================================
section("Was der eigene Schreibvorgang NICHT ist: eine Fremdaenderung")

_sand19 = tempfile.mkdtemp(prefix="studioeigen_")
_cwd19 = _os.getcwd()
_os.chdir(_sand19)
try:
    Path("sequences").mkdir()
    _b19 = _SB8(_SEQ8(name="S"), Path("sequences/s/sequence.json"), "sequences")

    # **Erst laden, dann anlegen.** `_scan_laden()` ersetzt `self.scans`
    # komplett durch das, was auf Platte steht - passiert es NACH dem Anlegen,
    # ist der frische Scan wieder weg.
    _z19 = _b19.scan_neu({"name": "Inventar"})
    check("ein neu angelegter Scan ueberlebt das Laden von Platte",
          [c["name"] for c in _z19["scans"]] == ["Inventar"])
    check("und ist offen", _z19["offen"] == "Inventar")

    if not _hat_pil18:
        print("  ----  Bild-Teil uebersprungen (Pillow nicht installiert)")
    else:
        _bild19 = _PILImage18.new("RGB", (200, 150), (20, 24, 30))
        _echt19 = _img18.take_screenshot
        _echtorg19 = _win18.get_virtual_origin
        _img18.take_screenshot = lambda region=None: (
            _bild19.copy() if not region else _bild19.crop(tuple(region)))
        _win18.get_virtual_origin = lambda: (0, 0)
        try:
            check("frisch geladen ist nichts fremd", _b19.scan_daten()["fremd"] is False)
            # Das gemerkte Bild liegt UNTER item_scans/ - das Anlegen des
            # Unterordners dreht die Aenderungszeit des Elternordners weiter.
            # Ohne Nachziehen meldete der Reiter direkt nach der EIGENEN
            # Aufnahme "auf Platte hat sich etwas geaendert", und einen Hinweis,
            # der nach der eigenen Aktion kommt, gewoehnt man sich ab zu lesen.
            _z19 = _b19.scan_foto()
            check("die eigene Aufnahme meldet keine Fremdaenderung",
                  _z19["fremd"] is False)
            check("das Bild ist trotzdem da", _z19["foto"]["bild"] is True)
            # Gegenprobe: eine ECHTE Fremdaenderung faellt weiterhin auf.
            import time as _time19
            _time19.sleep(0.01)
            Path("sequences/s/item_scans").mkdir(parents=True, exist_ok=True)
            Path("sequences/s/item_scans/fremd.json").write_text(
                "{}", encoding="utf-8")
            check("eine fremde Datei im selben Ordner faellt weiterhin auf",
                  _b19.scan_daten()["fremd"] is True)

            # --- Erkennen wird in der Item-Liste sichtbar ---
            section("Was das Erkennen der Item-Liste sagt")
            _b19.slots["Slot 1"] = _SLOT8(name="Slot 1", scan_region=(10, 10, 60, 60),
                                          click_pos=(35, 35), slot_color=(20, 24, 30))
            _b19.scans["Inventar"].slot_names = ["Slot 1"]
            _b19.items["Sicheres"] = _ITEM8(name="Sicheres",
                                            marker_colors=[(20, 24, 30)])
            _b19.scans["Inventar"].item_names = ["Sicheres"]
            _b19._objekte_angleichen()
            _z19 = _b19.scan_erkennen()
            _item19 = [i for i in _z19["items"] if i["name"] == "Sicheres"][0]
            # **„erkannt" allein ist eine Behauptung ohne Beleg.** Der Knopf
            # faerbte nur die Rechtecke im Bild; wer in der Item-Liste stand -
            # und das ist die Liste, in der man arbeitet - sah nach dem Klick
            # nichts und hielt ihn fuer wirkungslos.
            check("das Item weiss, dass es erkannt wurde", _item19["erkannt"] is True)
            check("und in WELCHEM Slot", _item19["erkannt_in"] == ["Slot 1"])
            _b19._treffer = {}
            _item19 = [i for i in _b19.scan_daten()["items"]
                       if i["name"] == "Sicheres"][0]
            check("ohne Erkennungslauf steht dort nichts",
                  _item19["erkannt"] is False and _item19["erkannt_in"] == [])
        finally:
            _img18.take_screenshot = _echt19
            _win18.get_virtual_origin = _echtorg19
finally:
    _os.chdir(_cwd19)


section("Studio-Items: fehlerhafte Vorlagen lassen sich gezielt lösen")
_sand_vorlage = tempfile.mkdtemp(prefix="studiovorlage_")
_cwd_vorlage = _os.getcwd()
_os.chdir(_sand_vorlage)
try:
    Path("sequences/s/templates").mkdir(parents=True)
    _bv = _SB8(_SEQ8(name="S"), Path("sequences/s/sequence.json"), "sequences")
    _item_v = _ITEM8(name="Auto 1", category="Auto", template="a.png",
                     template_variants=["b.png"])
    _bv.items = {_item_v.name: _item_v}
    _bv.scan_art, _bv.scan_name = "item", _item_v.name
    _zv = _bv.scan_item_vorlage_entfernen({"name": "Auto 1", "datei": "a.png"})
    check("die gewählte Vorlage wird gelöst", _zv["status"]["art"] == "warn")
    check("eine vorhandene Variante rückt als Hauptvorlage nach",
          _item_v.template == "b.png" and _item_v.template_variants == [])
    check("die Ansicht bietet Vorlagenpflege und LLM-Namen an",
          "scan_item_vorlage_entfernen" in studio_web_source()
          and "scanAutonameLauf" in studio_web_source())
finally:
    _os.chdir(_cwd_vorlage)


# =============================================================================
section("Studio-Items: alle auf einmal per LLM benennen")
# =============================================================================
# Den Knopf gab es nur AM einzelnen Item — richtig fuer die Korrektur eines
# Namens, falsch fuer den Normalfall: nach dem Lernen heissen sie "Item 1" …
# "Item 56", und einzeln waeren das sechsundfuenfzig Masken zum Aufklappen.
import json as _json_an                                            # noqa: E402
import autoclicker.llm_vision as _lv_an                            # noqa: E402

_sand_an = tempfile.mkdtemp(prefix="studioautoname_")
_cwd_an = _os.getcwd()
_echt_an = _lv_an.suggest_item_name
_os.chdir(_sand_an)
try:
    _hat_pil_an = False
    try:
        from PIL import Image as _PILImage_an
        _hat_pil_an = True
    except ImportError:
        pass

    if not _hat_pil_an:
        print("  ----  uebersprungen (Pillow nicht installiert)")
    else:
        Path("sequences/s/templates").mkdir(parents=True)
        for _datei_an in ("a.png", "b.png"):
            _PILImage_an.new("RGB", (8, 8), (200, 60, 60)).save(
                Path("sequences/s/templates") / _datei_an)
        # `scan_items_autoname` liest die Config von PLATTE (`load_config`) und
        # nicht das Modul-CONFIG: ohne Datei greift der Default und der Befehl
        # lehnt mit "nicht aktiviert" ab, bevor er irgendetwas tut.
        Path("config.json").write_text(
            _json_an.dumps({"llm_enabled": True}), encoding="utf-8")

        def _bau_an():
            _b = _SB8(_SEQ8(name="S"), Path("sequences/s/sequence.json"), "sequences")
            # **Erst laden, dann stellen.** `_scan_laden()` laeuft beim ersten
            # `scan_daten()` und holt Slots, Items und Scans von Platte — was
            # der Test vorher ins Objekt schreibt, waere danach weg. Frueher
            # fiel das nicht auf, weil der Durchgang EIN Aufruf war und seine
            # Arbeit vor der ersten Momentaufnahme erledigt hatte.
            _b.scan_daten()
            _b.items = {
                "Item 1": _ITEM8(name="Item 1", template="a.png"),
                "Item 2": _ITEM8(name="Item 2", template="b.png"),
                "Ohne Vorlage": _ITEM8(name="Ohne Vorlage"),
            }
            return _b

        def _durchlauf_an(b, daten, schritte=None):
            """Der Durchgang, wie die Seite ihn treibt: Start, Schritte, Ende.

            `schritte` bricht nach so vielen ab — genau das, was der
            Abbrechen-Knopf im Arbeits-Kasten tut.
            """
            erg = b.scan_autoname_start(daten)
            if not getattr(b, "_autoname", None):
                return erg                      # abgelehnt, die Meldung sagt warum
            n = 0
            while (getattr(b, "_autoname", None) or {}).get("offen"):
                if schritte is not None and n >= schritte:
                    return b.scan_autoname_ende({"abgebrochen": True})
                b.scan_autoname_schritt()
                n += 1
            return b.scan_autoname_ende()

        _namen_an = iter(["Godlike Bow", "Citadel Helmet"])
        _lv_an.suggest_item_name = lambda *a, **kw: next(_namen_an, None)

        _ba = _bau_an()
        _vorher_an = _ba.scan_daten()["undo"]["tiefe"]
        _erg_an = _durchlauf_an(_ba, {"alle": True})
        check("'alle' benennt jedes Item mit Vorlage, nicht nur die Kategorie 'Auto'",
              "Godlike Bow" in _ba.items and "Citadel Helmet" in _ba.items)
        # Ein Item ohne Vorlage hat nichts, was man dem Modell zeigen koennte —
        # es faellt heraus, statt mit einem geratenen Namen dazustehen.
        check("ein Item ohne Vorlage bleibt unberuehrt", "Ohne Vorlage" in _ba.items)
        check("und die Meldung nennt beide Zahlen",
              "2 von 2" in _erg_an["status"]["text"])
        # **Ohne Katalog raet das Modell frei** und antwortet auf die deutsche
        # Frage deutsch: heraus kommt die Art ("Bogen") statt des Gegenstands.
        # Das sieht in der Liste wie ein Ergebnis aus und ist keins.
        check("und sagt dazu, dass ohne Katalog geraten wurde",
              "ohne Katalog" in _erg_an["status"]["text"])
        # **Ein Stand fuer den ganzen Durchgang.** Je Item abgelegt waere der
        # Zustand von VOR dem Durchgang nach dreissig Items aus dem Stapel
        # gefallen — also genau der, auf den man zurueck will.
        check("der ganze Durchgang ist EIN Rueckgaengig-Schritt",
              _ba.scan_daten()["undo"]["tiefe"] == _vorher_an + 1)
        _ba.scan_rueckgaengig()
        check("und ein Zurueck holt alle Namen auf einmal wieder",
              "Item 1" in _ba.items and "Item 2" in _ba.items
              and "Godlike Bow" not in _ba.items)

        # Ohne Treffer darf kein Stand entstehen: ein STRG+Z, das nichts
        # zurueckdreht, ist eins, dem man danach nicht mehr traut.
        _lv_an.suggest_item_name = lambda *a, **kw: None
        _bl = _bau_an()
        _leer_an = _bl.scan_daten()["undo"]["tiefe"]
        _erg_leer = _durchlauf_an(_bl, {"alle": True})
        check("erkennt das Modell nichts, entsteht kein Rueckgaengig-Stand",
              _bl.scan_daten()["undo"]["tiefe"] == _leer_an)
        check("und die Meldung sagt, wie viele ohne Vorschlag blieben",
              "2 ohne Vorschlag" in _erg_leer["status"]["text"])

        # Ohne `alle` und ohne Auswahl bleibt es beim vorsichtigen Standard —
        # sonst benennt ein Fehlgriff den ganzen von Hand gepflegten Bestand um.
        _lv_an.suggest_item_name = lambda *a, **kw: "Godlike Bow"
        _bs = _bau_an()
        _erg_std = _durchlauf_an(_bs, {})
        check("ohne 'alle' bleibt es bei den auto-gelernten Items",
              _erg_std["status"]["art"] == "warn" and "Item 1" in _bs.items)

        # --- Der Grund, warum die Kategorie nie kam ---------------------------
        # **`sanitize_filename()` stand hier und war die falsche Funktion.** Sie
        # macht Kleinbuchstaben und Unterstriche: aus "Godlike Bow" wurde
        # `godlike_bow` — und `Katalog.treffer()` vergleicht `casefold()`, nicht
        # Unterstriche. Der Name kam also woertlich aus dem Katalog und fand
        # sich darin trotzdem nicht wieder; Kategorie und Prioritaet blieben
        # IMMER aus. Ein Test, der nur den Namen prueft, sieht das nicht — es
        # muss die ganze Kette sein.
        from autoclicker.config import CONFIG as _CFG_an
        Path("katalog.json").write_text(_json_an.dumps({"items": {
            "Godlike Bow": {"kategorie": "Bogen", "wert": 900},
            "Citadel Helmet": {"kategorie": "Helm", "wert": 500},
        }}), encoding="utf-8")
        _altkat_an = _CFG_an.scan_catalog_file
        _CFG_an.scan_catalog_file = str(Path("katalog.json").resolve())
        try:
            _bk = _bau_an()
            # `item_names` gehoert NICHT in den Konstruktor: die Namen sind
            # die Wahrheit, aber abgeleitet — `sync_names()` fuellt sie aus den
            # Objekten (`__post_init__`).
            _bk.scans = {"S": _ISC8(name="S", use_catalog=True,
                                    items=[_bk.items["Item 1"], _bk.items["Item 2"]])}
            _bk.scan_offen = "S"
            _kat_namen = iter(["Godlike Bow", "Citadel Helmet"])
            _lv_an.suggest_item_name = lambda *a, **kw: next(_kat_namen, None)
            _erg_kat = _durchlauf_an(_bk, {"alle": True})
            check("ein Katalogname bleibt woertlich stehen",
                  "Godlike Bow" in _bk.items and "godlike_bow" not in _bk.items)
            # Ueber `.get()`, damit ein roter erster Check die restliche Suite
            # nicht mit einem KeyError abreisst — die Gegenprobe ("Fix
            # entschaerfen, Test muss rot werden") laeuft sonst nur bis hierhin.
            _gb_an = _bk.items.get("Godlike Bow")
            _ch_an = _bk.items.get("Citadel Helmet")
            check("und wird deshalb auch eingeordnet",
                  _gb_an is not None and _ch_an is not None
                  and _gb_an.category == "Bogen" and _ch_an.category == "Helm")
            check("die Meldung nennt das Einordnen mit",
                  "eingeordnet" in _erg_kat["status"]["text"])
            # Der teurere von beiden bekommt den ersten Rang — aber innerhalb
            # SEINER Kategorie, und die haben hier je ein Item.
            check("und die Prioritaet steht dicht innerhalb der Kategorie",
                  _gb_an is not None and _ch_an is not None
                  and _gb_an.priority == 1 and _ch_an.priority == 1)
        finally:
            _CFG_an.scan_catalog_file = _altkat_an

        # --- Abbrechen -------------------------------------------------------
        _abb_namen = iter(["Godlike Bow", "Citadel Helmet"])
        _lv_an.suggest_item_name = lambda *a, **kw: next(_abb_namen, None)
        _bab = _bau_an()
        _erg_abb = _durchlauf_an(_bab, {"alle": True}, schritte=1)
        # Was bis dahin benannt wurde, bleibt stehen: es wegzuwerfen hiesse,
        # eine Modell-Antwort zu verbrennen, weil man die zweite nicht mehr
        # abwarten wollte — und STRG+Z holt den ganzen Durchgang zurueck.
        check("ein Abbruch behaelt, was bis dahin benannt wurde",
              "Godlike Bow" in _bab.items and "Item 2" in _bab.items)
        check("und die Meldung sagt, wie viele nicht angesehen wurden",
              "abgebrochen" in _erg_abb["status"]["text"]
              and "1 nicht angesehen" in _erg_abb["status"]["text"])
        check("danach laeuft kein Durchgang mehr",
              _bab.scan_daten()["autoname"] is None)
        check("und ein weiterer Schritt sagt das, statt etwas zu tun",
              _bab.scan_autoname_schritt()["status"]["art"] == "warn")

        # Der Fortschritt steht in der MOMENTAUFNAHME, nicht nur in der Antwort
        # des Schritts: die Seite baut sich nach jeder Bruecken-Antwort neu auf.
        _lv_an.suggest_item_name = lambda *a, **kw: "Godlike Bow"
        _bfs = _bau_an()
        _bfs.scan_autoname_start({"alle": True})
        _stand_an = _bfs.scan_daten()["autoname"]
        check("die Momentaufnahme traegt den Fortschritt",
              _stand_an and _stand_an["gesamt"] == 2 and _stand_an["fertig"] == 0)
        _bfs.scan_autoname_schritt()
        check("und er waechst mit jedem Schritt",
              _bfs.scan_daten()["autoname"]["fertig"] == 1)
        _bfs.scan_autoname_ende()

        # Der Knopf steht im Kopf der rechten Spalte und schickt genau dieses
        # Feld; die Momentaufnahme sagt ihm, ob das LLM ueberhaupt an ist.
        _quelle_an = studio_web_source()
        check("die Seite treibt den Durchgang selbst",
              "scanAutonameLauf({alle: true})" in _quelle_an
              and 'rufScan("scan_autoname_start"' in _quelle_an
              and 'rufScan("scan_autoname_schritt"' in _quelle_an
              and 'rufScan("scan_autoname_ende"' in _quelle_an)
        # **Ein Aufruf, der drei Minuten blockiert, laesst sich nicht abbrechen.**
        # Deshalb steht die Schleife in der Ansicht — und deshalb muss dort auch
        # der Knopf sein, der sie stoppt.
        check("und laesst sich dabei abbrechen",
              "autonameAbbruch" in _quelle_an and "Abbrechen" in _quelle_an)
        check("und fragt vorher, ob das LLM eingeschaltet ist",
              "SC.llm_an" in _quelle_an
              and "llm_an" in _bau_an().scan_daten())
        # Ein Aufruf, der eine Minute lang rechnet, braucht einen Hinweis —
        # sonst sieht das Fenster tot aus. `mitWarten` passt nicht: dort wartet
        # die Bruecke auf ENTER und hat eine feste Grenze.
        check("und zeigt so lange, dass gearbeitet wird",
              "mitArbeit(" in _quelle_an and "arbeitZeigen" in _quelle_an)
finally:
    _lv_an.suggest_item_name = _echt_an
    _os.chdir(_cwd_an)
    shutil.rmtree(_sand_an, ignore_errors=True)
