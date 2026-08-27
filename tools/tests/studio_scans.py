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

    # Der folgende historische Block prüfte den inzwischen entfernten globalen
    # Slot-/Item-Bestand samt Mitgliedschaftshäkchen. Er bleibt als lesbare
    # Fehlergeschichte erhalten, ist aber kein ausführbarer Produktvertrag mehr.
    """
    # --- Umbenennen zieht die Referenz nach ---
    # Der Name IST die Referenz (slots/items werden per Name in Scans
    # eingetragen). Ohne Nachziehen zeigte der Scan danach ins Leere - und zwar
    # still: er liefe mit einem Slot weniger weiter.
    _b18.slots.clear()
    _b18.items.clear()
    _b18.scans.clear()
    _b18.slots["Slot 1"] = _SLOT8(name="Slot 1", scan_region=(0, 0, 10, 10), click_pos=(5, 5))
    _b18.items["Item 1"] = _ITEM8(name="Item 1")
    _b18.scan_neu({"name": "Test"})
    _b18.scan_mitglied({"scan": "Test", "art": "slot", "name": "Slot 1"})
    _z18 = _b18.scan_mitglied({"scan": "Test", "art": "item", "name": "Item 1"})
    check("Haken setzen traegt in den Scan ein",
          _z18["scans"][0]["slots"] == ["Slot 1"] and _z18["scans"][0]["items"] == ["Item 1"])
    _z18 = _b18.scan_mitglied({"scan": "Test", "art": "item", "name": "Item 1"})
    check("nochmal klicken nimmt wieder raus", _z18["scans"][0]["items"] == [])

    # --- Der Reiter merkt, wenn der Hauptprozess die Dateien anfasst ---
    # Der Fall aus dem Alltag: ein Lauf mit `learn_unknown` legt Items an und
    # speichert sie. Der Reiter hatte items.json beim Oeffnen gelesen und danach
    # nie wieder - die Konsole meldete "gelernt", im Studio waren sie nicht da,
    # und man sucht den Fehler beim Lernen.
    check("frisch geladen gilt nichts als fremd geaendert",
          _b18.scan_daten()["fremd"] is False)
    import time as _t18
    _t18.sleep(0.01)
    # Der Ordner entsteht sonst erst beim Speichern - hier wird aber von
    # AUSSEN geschrieben, also gibt es noch keinen.
    Path("items").mkdir(exist_ok=True)
    Path("items/items.json").write_text(
        '{"Von aussen": {"marker_colors": [[1, 2, 3]]}}', encoding="utf-8")
    check("eine Aenderung von aussen faellt auf",
          _b18.scan_daten()["fremd"] is True)
    check("und sie wird nicht stillschweigend uebernommen",
          "Von aussen" not in _b18.items)

    # Ungespeichertes wird nicht kommentarlos verworfen.
    _b18._scan_dirty = True
    _z18 = _b18.scan_neu_laden()
    check("mit offenen Aenderungen wird erst gewarnt",
          _z18["status"]["art"] == "warn" and "Von aussen" not in _b18.items)
    _z18 = _b18.scan_neu_laden({"verwerfen": True})
    check("mit verwerfen wird geladen", "Von aussen" in _b18.items)
    check("und danach gilt der Stand wieder als aktuell",
          _z18["fremd"] is False and _z18["dirty"] is False)
    # Das EIGENE Speichern darf sich nicht selbst als Fremdaenderung melden -
    # sonst stuende der Hinweis nach jedem Klick auf "Speichern" da, und man
    # gewoehnt sich an, ihn zu uebersehen.
    _t18.sleep(0.01)
    _z18 = _b18.scan_speichern()
    check("das eigene Speichern gilt nicht als Fremdaenderung",
          _z18["fremd"] is False)

    # --- Alles rein, alles raus ---
    # Der Weg in einen frischen Scan waren 56 Haekchen.
    _b18.slots.clear(); _b18.items.clear(); _b18.scans.clear()
    for _n18 in ("S1", "S2", "S3"):
        _b18.slots[_n18] = _SLOT8(name=_n18, scan_region=(0, 0, 9, 9), click_pos=(4, 4))
    _b18.items["I1"] = _ITEM8(name="I1")
    _b18.scan_neu({"name": "Alle"})
    _z18 = _b18.scan_alle({"art": "slot", "wert": True})
    check("alle Slots auf einmal dazu",
          sorted(_z18["scans"][0]["slots"]) == ["S1", "S2", "S3"])
    _z18 = _b18.scan_alle({"art": "slot", "wert": False})
    check("und alle wieder raus", _z18["scans"][0]["slots"] == [])
    _z18 = _b18.scan_alle({"art": "item", "wert": True})
    check("Items genauso", _z18["scans"][0]["items"] == ["I1"])
    # Der Inspektor arbeitet am GEWAEHLTEN Scan, der nicht der offene sein muss -
    # ohne den Parameter traefe „alle" den falschen.
    _b18.scan_neu({"name": "Zweiter"})
    _z18 = _b18.scan_alle({"scan": "Alle", "art": "slot", "wert": True})
    _nach_name18 = {c["name"]: c for c in _z18["scans"]}
    check("„alle“ trifft den benannten Scan, nicht den offenen",
          sorted(_nach_name18["Alle"]["slots"]) == ["S1", "S2", "S3"]
          and _nach_name18["Zweiter"]["slots"] == [])
    _b18.scans.pop("Zweiter", None)
    _b18.scan_offen = "Alle"
    _b18.scan_offen = ""
    check("ohne offenen Scan passiert nichts",
          _b18.scan_alle({"art": "slot", "wert": True})["status"]["art"] == "warn")
    _b18.slots.clear(); _b18.items.clear(); _b18.scans.clear()
    _b18.slots["Slot 1"] = _SLOT8(name="Slot 1", scan_region=(0, 0, 10, 10), click_pos=(5, 5))
    _b18.items["Item 1"] = _ITEM8(name="Item 1")
    _b18.scan_neu({"name": "Test"})
    _b18.scan_mitglied({"scan": "Test", "art": "slot", "name": "Slot 1"})

    # --- Die Scan-Richtung im Studio ---
    _z18 = _b18.scan_daten()
    check("frisch angelegt laufen die Slots vorwaerts",
          _z18["scans"][0]["reverse"] is False)
    _z18 = _b18.scan_setzen({"name": "Test", "feld": "reverse", "wert": True})
    check("der Schalter stellt auf rueckwaerts",
          _z18["scans"][0]["reverse"] is True
          and _b18.scans["Test"].reverse is True)
    _z18 = _b18.scan_setzen({"name": "Test", "feld": "reverse", "wert": False})
    check("und wieder zurueck", _z18["scans"][0]["reverse"] is False)

    _b18.scan_waehlen({"art": "slot", "name": "Slot 1"})
    _z18 = _b18.scan_slot_setzen({"name": "Slot 1", "feld": "name", "wert": "Beutel oben"})
    check("der Slot heisst neu", [s["name"] for s in _z18["slots"]] == ["Beutel oben"])
    check("und der Scan zeigt weiter auf ihn", _z18["scans"][0]["slots"] == ["Beutel oben"])
    check("die Auswahl wandert mit", _z18["wahl"]["name"] == "Beutel oben")

    _z18 = _b18.scan_slot_setzen({"name": "Beutel oben", "feld": "name", "wert": "Beutel oben"})
    check("derselbe Name ist keine Aenderung", len(_z18["slots"]) == 1)

    # --- Loeschen raeumt die Referenz weg ---
    _b18.scan_mitglied({"scan": "Test", "art": "item", "name": "Item 1"})
    _b18.scan_waehlen({"art": "item", "name": "Item 1"})
    _z18 = _b18.scan_item_loeschen()
    check("ein geloeschtes Item verschwindet auch aus dem Scan",
          _z18["items"] == [] and _z18["scans"][0]["items"] == [])
    _b18.scan_waehlen({"art": "slot", "name": "Beutel oben"})
    _z18 = _b18.scan_slot_loeschen()
    check("und ein geloeschter Slot ebenso",
          _z18["slots"] == [] and _z18["scans"][0]["slots"] == [])

    # --- Der Scan ist die Klammer, nicht die Auswahl ---
    # Mit mehreren Spielen liegen sonst alle Slots und Items aller Spiele in
    # einer Liste. Der offene Scan sagt, woran gerade gearbeitet wird - und ist
    # bewusst NICHT dasselbe wie die Auswahl: wer einen Slot anklickt, um ihn zu
    # bearbeiten, arbeitet weiter an demselben Scan.
    _b18.slots.clear()
    _b18.items.clear()
    _b18.scans.clear()
    for _n18 in ("A1", "A2", "B1"):
        _b18.slots[_n18] = _SLOT8(name=_n18, scan_region=(0, 0, 9, 9), click_pos=(4, 4))
        _b18.items[_n18] = _ITEM8(name=_n18)
    _b18.scan_neu({"name": "Spiel A"})
    check("ein neuer Scan ist gleich offen", _b18.scan_offen == "Spiel A")
    for _n18 in ("A1", "A2"):
        _b18.scan_mitglied({"art": "slot", "name": _n18})
        _b18.scan_mitglied({"art": "item", "name": _n18})
    _b18.scan_neu({"name": "Spiel B"})
    _b18.scan_mitglied({"art": "slot", "name": "B1"})

    _z18 = _b18.scan_oeffnen({"name": "Spiel A"})
    check("der offene Scan steht in der Aufnahme", _z18["offen"] == "Spiel A")
    check("und markiert seine Mitglieder",
          sorted(s["name"] for s in _z18["slots"] if s["dabei"]) == ["A1", "A2"])
    check("Items ebenso",
          sorted(i["name"] for i in _z18["items"] if i["dabei"]) == ["A1", "A2"])
    _z18 = _b18.scan_oeffnen({"name": "Spiel B"})
    check("beim Wechsel wandert die Markierung mit",
          [s["name"] for s in _z18["slots"] if s["dabei"]] == ["B1"])

    # Wer IN einem offenen Scan etwas anlegt, legt es FUER ihn an. Ohne das war
    # ein frisch aufgezogener Slot sofort wieder weg: die Listen zeigen nur die
    # Mitglieder, und er war keines.
    _b18.slots["B2"] = _SLOT8(name="B2", scan_region=(0, 0, 9, 9), click_pos=(4, 4))
    _b18.scan_waehlen({"art": "slot", "name": "B2"})
    _b18._dazu("slot", "B2")
    _z18 = _b18.scan_daten()
    check("ein im offenen Scan angelegter Slot gehoert gleich dazu",
          sorted(s["name"] for s in _z18["slots"] if s["dabei"]) == ["B1", "B2"])
    _b18._dazu("slot", "B2")
    check("und zweimal dazulegen legt ihn nicht doppelt an",
          _b18.scans["Spiel B"].slot_names.count("B2") == 1)
    _b18.scans["Spiel B"].slot_names.remove("B2")
    del _b18.slots["B2"]
    _b18._objekte_angleichen()

    # Ein Slot anklicken darf den Zusammenhang nicht verlieren - genau das war
    # der Fehler, als "offen" noch an der Auswahl hing.
    _b18.scan_waehlen({"art": "slot", "name": "A1"})
    check("ein Klick auf einen Slot laesst den Scan offen",
          _b18.scan_daten()["offen"] == "Spiel B")
    _z18 = _b18.scan_oeffnen({"name": ""})
    check("kein Scan offen heisst: nichts ist dabei",
          _z18["offen"] == "" and not any(s["dabei"] for s in _z18["slots"]))
    check("ein Scan, den es nicht gibt, wird gemeldet",
          _b18.scan_oeffnen({"name": "Gibt es nicht"})["status"]["art"] == "err")

    # Die Erkennung fragt den OFFENEN Scan, nicht die Auswahl.
    _b18.scan_oeffnen({"name": "Spiel A"})
    _b18.scan_waehlen({"art": "item", "name": "B1"})
    check("geprueft werden die Items des offenen Scans",
          sorted(i.name for i in _b18._kandidaten()) == ["A1", "A2"])

    # --- Der Suchdurchgang nimmt auch schon vorhandene Slots in den Scan ---
    # Bei zwei Spielen liegen die Slots des einen laengst im Bestand. Ein NEUER
    # Scan ueber demselben Inventar legte deshalb nichts an ("alle schon da") -
    # nahm aber auch nichts auf, und weil die Listen nur Mitglieder zeigen,
    # blieb er leer: kein Slot in der Liste, keine Marke im Bild.
    _merk18 = (dict(_b18.slots), dict(_b18.scans), _b18.scan_offen)
    _b18.slots.clear()
    _b18.scans.clear()
    _b18.scan_offen = ""
    _b18.slots["Alt 1"] = _SLOT8(name="Alt 1", scan_region=(100, 100, 160, 160),
                                 click_pos=(130, 130))
    check("ein Slot an der Stelle wird beim NAMEN genannt",
          _b18._slot_an_stelle((105, 105, 155, 155)) == "Alt 1"
          and _b18._slot_an_stelle((300, 300, 340, 340)) is None)
    _b18.scan_neu({"name": "Zweites Spiel"})
    # Nur die Teile stellen, die einen Bildschirm braeuchten - gemessen wird die
    # Schleife, die aus Rechtecken Slots und Mitglieder macht.
    _b18._foto = object()
    _b18._foto_info = {"links": 0, "oben": 0, "skala": 1.0, "breite": 500,
                       "hoehe": 500, "stand": 0.0}
    _b18._suchbereich = (90, 90, 400, 400)
    _b18._hat_opencv = lambda: True
    _b18._foto_farbe = lambda x, y: (10, 20, 30)
    _b18._foto_crop = lambda bereich: object()
    _b18._slots_suchen = lambda bild, farbe: [(10, 10, 60, 60), (80, 10, 60, 60)]
    _z18 = _b18._klick_finden(100, 100)
    check("ein schon vorhandener Slot gehoert danach zum offenen Scan",
          "Alt 1" in _b18.scans["Zweites Spiel"].slot_names)
    check("und der wirklich neue ebenfalls",
          len(_b18.scans["Zweites Spiel"].slot_names) == 2
          and len(_b18.slots) == 2)
    check("beide stehen als dabei in der Aufnahme",
          len([s for s in _z18["slots"] if s["dabei"]]) == 2)
    check("und die Aufnahme gilt als Aenderung", _z18["dirty"] is True)
    # Gegenprobe: was schon dabei WAR, wird nicht noch einmal angehaengt.
    _b18._suchbereich = (90, 90, 400, 400)
    _b18._klick_finden(100, 100)
    check("ein zweiter Durchgang haengt nichts doppelt an",
          _b18.scans["Zweites Spiel"].slot_names.count("Alt 1") == 1
          and len(_b18.slots) == 2)

    # --- Ein zweiter Suchlauf raet die Groesse nicht neu ---
    # `erkenne_slots_im_bild()` normalisiert auf den Median EINES Durchgangs; ein
    # zweiter Lauf ueber demselben Raster weicht deshalb ein paar Pixel ab,
    # obwohl die Slots im Spiel gleich gross sind. Genau diese Differenz liess
    # gelernte Templates als "passt nicht zur Scan-Region" auffallen.
    _b18._suchbereich = (90, 90, 400, 400)
    # Der Einzug kommt aus der Config - die Groesse wird deshalb so gestellt,
    # dass NACH dem Einzug 57x57 uebrig bleibt: 3 px neben den 60x60, die schon
    # dastehen, also innerhalb der Toleranz und damit angeglichen.
    from autoclicker.config import CONFIG as _CFG18
    _ein18 = max(0, int(_CFG18.scan_slot_inset))
    _b18._slots_suchen = lambda bild, farbe: [(200, 200, 57 + 2 * _ein18,
                                               57 + 2 * _ein18)]
    _b18._klick_finden(100, 100)
    _drift18 = [s for s in _b18.slots.values()
                if s.scan_region and s.scan_region[0] >= 250][0].scan_region
    check("ein knapp abweichender Fund bekommt die Groesse der vorhandenen",
          (_drift18[2] - _drift18[0], _drift18[3] - _drift18[1]) == (60, 60))
    # Gegenprobe: ein Slot, der WIRKLICH anders gross ist, wird nicht verbogen.
    _b18._suchbereich = (90, 90, 400, 400)
    _b18._slots_suchen = lambda bild, farbe: [(280, 200, 20 + 2 * _ein18,
                                               20 + 2 * _ein18)]
    _b18._klick_finden(100, 100)
    _klein18 = [s for s in _b18.slots.values()
                if s.scan_region and s.scan_region[0] >= 370][0].scan_region
    check("ein deutlich kleinerer Fund behaelt seine Groesse",
          (_klein18[2] - _klein18[0], _klein18[3] - _klein18[1]) == (20, 20))
    # Und der Bezug ist der offene Scan, NICHT der Bestand: zwei Bedienflaechen
    # desselben Spiels sind nicht gleich gross (gemessen: Raster 64 Zeilen,
    # Ausruestungsreihe 61). Ein leerer Scan hat keinen Bezug - dann bleibt der
    # Fund, wie er gemessen wurde, statt der Groesse eines fremden Rasters zu
    # folgen.
    _b18.scan_neu({"name": "Andere Flaeche"})
    check("ein leerer Scan gibt keine Zielgroesse vor",
          _b18._bestehende_slot_groesse() is None)
    _b18.scans.pop("Andere Flaeche", None)
    _b18.scan_offen = "Zweites Spiel"
    check("der offene Scan mit Slots schon",
          _b18._bestehende_slot_groesse() == (60, 60))
    _b18.slots.clear(), _b18.scans.clear()
    _b18.slots.update(_merk18[0])
    _b18.scans.update(_merk18[1])
    _b18.scan_offen = _merk18[2]
    for _feld18 in ("_hat_opencv", "_foto_farbe", "_foto_crop", "_slots_suchen"):
        _b18.__dict__.pop(_feld18, None)
    _b18._foto = _b18._foto_info = None
    _b18._objekte_angleichen()

    # --- Fehlende Namen werden gemeldet, nicht verschwiegen ---
    _b18.scans.clear()
    _b18.scan_offen = ""
    _b18.scan_neu({"name": "Test"})
    _b18.scan_mitglied({"art": "slot", "name": "A1"})
    _b18.scans["Test"].slot_names.append("Gibt es nicht")
    check("ein toter Verweis steht in der Aufnahme",
          _b18.scan_daten()["scans"][0]["fehlend"] == ["Gibt es nicht"])

    # --- Speichern schreibt alle drei Dateiarten ---
    _b18.scans["Test"].slot_names.remove("Gibt es nicht")
    _z18 = _b18.scan_speichern()
    check("gespeichert wird ohne Fehler", _z18["status"]["art"] == "ok")
    check("slots.json ist da", Path("slots/slots.json").exists())
    check("items.json auch", Path("items/items.json").exists())
    check("und die Scan-Konfiguration als eigene Datei",
          list(Path("item_scans").glob("*.json")) != [])
    check("danach ist nichts mehr offen", _z18["dirty"] is False)

    # Der Hauptprozess erfaehrt davon - sonst arbeitete er bis zum naechsten
    # CTRL+ALT+L mit dem alten Stand.
    import autoclicker.befehl as _bf18
    _auftrag18 = _bf18.hole()
    check("der Hauptprozess bekommt Bescheid",
          _auftrag18 is not None and _auftrag18["befehl"] == "daten")

    # --- Was auf Platte steht, liest der Loader wieder ---
    from autoclicker.persistence import load_item_scan_file as _lif18
    _wieder18 = _lif18(list(Path("item_scans").glob("*.json"))[0])
    check("der Loader findet den Scan wieder", _wieder18 is not None)
    check("mit denselben Namen darin", _wieder18.item_names == [])
    from autoclicker.editors.sequence_studio.scan_model import load_slots as _ls18
    check("und die Slots kommen unveraendert zurueck",
          sorted(_ls18("slots/slots.json")) == sorted(_b18.slots))

    # --- Ein aelterer Scan hat Slots, aber kein gemerktes Bild ---
    # Die Mitte des Reiters stand dann leer, obwohl die Slots laengst da waren:
    # das gemerkte Bild gibt es erst, seit der Reiter eines ablegt. Die Flaeche
    # wird deshalb notfalls aus dem Rechteck um die Slots gerechnet.
    _alt18 = _SB8(_SEQ8(name="S"), Path("sequences/S.json"), "sequences")
    _z18 = _alt18.scan_daten()
    check("ein Scan ohne Bild bekommt trotzdem eine Flaeche", _z18["foto"] is not None)
    check("sie sagt von sich, dass sie kein Bild ist", _z18["foto"]["bild"] is False)
    # Slot A1 liegt auf (0,0,9,9); die Flaeche legt 40 px Rand darum.
    check("und sie liegt um die Slots herum",
          (_z18["foto"]["links"], _z18["foto"]["oben"]) == (-40, -40)
          and (_z18["foto"]["breite"], _z18["foto"]["hoehe"]) == (89, 89))
    # Gegenprobe: ein Scan ohne Slots hat auch nichts, worum eine Flaeche
    # laege - dort bleibt die leere Mitte richtig.
    check("ein Scan ohne Slots bekommt keine Flaeche",
          _alt18.scan_neu({"name": "Leerer"})["foto"] is None)
    check("die Auswahl davor hatte eine", _z18["foto"] is not None)

    # --- Beim Oeffnen steht der zuletzt bearbeitete Scan vorn ---
    # Vorher nur bei GENAU EINEM Scan: wer einen zweiten anlegte, sah beim
    # naechsten Start eine leere Mitte und musste erst merken, dass oben links
    # eine Auswahl steht.
    _erste18 = list(Path("item_scans").glob("*.json"))[0]
    _zweite18 = _erste18.parent / "Zweiter.json"
    _zweite18.write_text(
        _erste18.read_text(encoding="utf-8").replace('"Test"', '"Zweiter"'),
        encoding="utf-8")
    _os.utime(_erste18, (1_000_000, 1_000_000))
    _os.utime(_zweite18, (2_000_000, 2_000_000))
    check("der juengere Scan ist offen",
          _SB8(_SEQ8(name="S"), Path("sequences/S.json"), "sequences")
          .scan_daten()["offen"] == "Zweiter")
    _os.utime(_erste18, (3_000_000, 3_000_000))
    check("und nach einer Aenderung am anderen dieser",
          _SB8(_SEQ8(name="S"), Path("sequences/S.json"), "sequences")
          .scan_daten()["offen"] == "Test")
    _zweite18.unlink()

    # ------------------------------------------------------------------------
    # Der Bezug ist der OFFENE SCAN, nicht der Bestand
    # ------------------------------------------------------------------------
    # Wer zwei Spiele betreibt, hat die Slots beider in einer Datei. Alles, was
    # "alle Slots" sagte, meinte bis hierher wirklich alle - und das war an drei
    # Stellen falsch. Zwei davon fielen nur als seltsame Zahl auf ("11 ohne
    # Bild", "13 von 56 erkannt"), und man sucht den Fehler beim Screenshot.
    _bz18 = _SB8(_SEQ8(name="S"), Path("sequences/S.json"), "sequences")
    _bz18.scan_daten()          # laedt von Platte - erst DANN stellen
    _bz18.slots.clear(), _bz18.items.clear(), _bz18.scans.clear()
    for _n18 in ("A1", "A2", "Fremd1"):
        _bz18.slots[_n18] = _SLOT8(name=_n18, scan_region=(0, 0, 20, 20),
                                   click_pos=(10, 10))
    _bz18.scan_neu({"name": "Spiel A"})
    _bz18.scan_mitglied({"art": "slot", "name": "A1"})
    _bz18.scan_mitglied({"art": "slot", "name": "A2"})
    check("die Slots des offenen Scans sind der Bezug",
          sorted(s.name for s in _bz18._scan_slots()) == ["A1", "A2"])
    _bz18.scan_offen = ""
    check("ohne offenen Scan ist es der ganze Bestand",
          len(_bz18._scan_slots()) == 3)
    _bz18.scan_offen = "Spiel A"

    # Gemessen an der Zaehlung: der Nenner muss der Scan sein. Ohne den Fix
    # steht hier 3 - also auch der Slot des anderen Spiels, der gar nicht im
    # Bild liegt und nie erkannt werden koennte.
    _bz18._foto = object()
    _bz18._foto_info = {"links": 0, "oben": 0, "skala": 1.0, "breite": 100,
                        "hoehe": 100, "stand": 0.0}
    _bz18._foto_crop = lambda bereich: None
    _z18 = _bz18.scan_erkennen()
    check("die Erkennung zaehlt die Slots des offenen Scans als Nenner",
          "von 2 Slot(s)" in _z18["status"]["text"])
    check("und sie prueft auch nur diese", sorted(_bz18._treffer) == ["A1", "A2"])

    # Dasselbe beim Lernen: "aus allen Slots" hiess der ganze Bestand, also lief
    # der Durchgang auch ueber das andere Spiel.
    _gelernt18 = []
    _bz18._lerne_aus_slot = lambda slot, dedup=False: (_gelernt18.append(slot.name)
                                                       or "Neu " + slot.name)
    _bz18.scan_items_lernen()
    check("gelernt wird aus den Slots des offenen Scans",
          sorted(_gelernt18) == ["A1", "A2"])
    _bz18.__dict__.pop("_lerne_aus_slot", None)

    # ------------------------------------------------------------------------
    # Rueckgaengig
    # ------------------------------------------------------------------------
    # Die groesste Luecke des Reiters: ein Rechteck ueber dreissig Slots und ein
    # Druck auf Entf waren endgueltig. Der einzige Ausweg hiess "Neu laden" -
    # und der wirft ALLES seit dem letzten Speichern weg.
    _bu18 = _SB8(_SEQ8(name="S"), Path("sequences/S.json"), "sequences")
    _bu18.scan_daten()          # laedt von Platte - erst DANN stellen
    _bu18.slots.clear(), _bu18.items.clear(), _bu18.scans.clear()
    for _n18 in ("S1", "S2", "S3"):
        _bu18.slots[_n18] = _SLOT8(name=_n18, scan_region=(0, 0, 20, 20),
                                   click_pos=(10, 10))
    check("frisch gibt es nichts zurueckzunehmen",
          _bu18.scan_daten()["undo"]["tiefe"] == 0)
    check("und der Versuch sagt das, statt etwas zu tun",
          _bu18.scan_rueckgaengig()["status"]["art"] == "info")

    _bu18._auswahl = ["S1", "S2"]
    _bu18.scan_art, _bu18.scan_name = "slot", "S1"
    _z18 = _bu18.scan_slot_loeschen()
    check("zwei Slots sind weg", sorted(_bu18.slots) == ["S3"])
    check("der Stapel weiss, was es war",
          _z18["undo"]["tiefe"] == 1 and "gelöscht" in _z18["undo"]["was"])
    _z18 = _bu18.scan_rueckgaengig()
    check("Rueckgaengig holt beide zurueck", sorted(_bu18.slots) == ["S1", "S2", "S3"])
    check("und der Stapel ist wieder leer", _z18["undo"]["tiefe"] == 0)

    # Ein geloeschter Slot verschwindet aus JEDEM Scan - genau deshalb wird der
    # ganze Stand gemerkt und nicht ein Rueckwaerts-Schritt je Feld: eine
    # vergessene Nebenwirkung waere ein Rueckgaengig, das halb zurueckdreht.
    _bu18.scan_neu({"name": "Mit Slots"})
    _bu18.scan_mitglied({"art": "slot", "name": "S1"})
    _bu18.scan_mitglied({"art": "slot", "name": "S2"})
    _bu18._auswahl = ["S1"]
    _bu18.scan_art, _bu18.scan_name = "slot", "S1"
    _bu18.scan_slot_loeschen()
    check("der Scan verliert den geloeschten Slot mit",
          _bu18.scans["Mit Slots"].slot_names == ["S2"])
    _bu18.scan_rueckgaengig()
    check("und bekommt ihn beim Rueckgaengig zurueck",
          _bu18.scans["Mit Slots"].slot_names == ["S1", "S2"])
    check("die abgeleiteten Objektlisten zeigen wieder auf den Bestand",
          [s is _bu18.slots[s.name] for s in _bu18.scans["Mit Slots"].slots]
          == [True, True])

    # Ein abgelehnter oder wirkungsloser Griff darf NICHTS auf den Stapel legen:
    # sonst taete STRG+Z einmal scheinbar gar nichts, und einem Rueckgaengig,
    # dem man nicht trauen kann, traut man gar nicht.
    _tiefe18 = _bu18.scan_daten()["undo"]["tiefe"]
    _bu18.scan_slot_setzen({"name": "S1", "feld": "gibtsnicht", "wert": 1})
    _bu18.scan_slot_setzen({"name": "S1", "feld": "name", "wert": "S1"})
    _bu18.scan_slot_setzen({"name": "S1", "feld": "name", "wert": "S2"})
    check("weder ein unbekanntes Feld noch ein Namens-Nichtwechsel zaehlen",
          _bu18.scan_daten()["undo"]["tiefe"] == _tiefe18)
    _bu18.scan_slot_setzen({"name": "S1", "feld": "x1", "wert": 5})
    check("eine echte Aenderung dagegen schon",
          _bu18.scan_daten()["undo"]["tiefe"] == _tiefe18 + 1)

    # Tiefer als UNDO_TIEFE waechst der Stapel nicht - sonst haelt ein Fenster,
    # das den Tag ueber offensteht, jeden Zwischenstand im Speicher.
    from autoclicker.editors.sequence_studio.scans import UNDO_TIEFE as _UT18
    for _i18 in range(_UT18 + 5):
        _bu18.scan_slot_setzen({"name": "S1", "feld": "y1", "wert": _i18})
    check("der Stapel bleibt bei UNDO_TIEFE stehen",
          _bu18.scan_daten()["undo"]["tiefe"] == _UT18)

    # Nach dem Neuladen beschreibt der Stapel Staende, die es nicht mehr gibt.
    _bu18._scan_dirty = False
    _bu18.scan_neu_laden()
    check("Neu laden leert den Stapel",
          _bu18.scan_daten()["undo"]["tiefe"] == 0)

    # ------------------------------------------------------------------------
    # Verschieben, Angleichen, Sammel-Aktionen
    # ------------------------------------------------------------------------
    # Ein Slot, der drei Pixel daneben liegt, war nur ueber vier Zahlenfelder zu
    # retten - und dreissig gar nicht.
    _bv18 = _SB8(_SEQ8(name="S"), Path("sequences/S.json"), "sequences")
    _bv18.scan_daten()          # laedt von Platte - erst DANN stellen
    _bv18.slots.clear(), _bv18.items.clear(), _bv18.scans.clear()
    _bv18.slots["V1"] = _SLOT8(name="V1", scan_region=(100, 100, 160, 160),
                               click_pos=(110, 150))
    _bv18.slots["V2"] = _SLOT8(name="V2", scan_region=(200, 100, 254, 154),
                               click_pos=(227, 127))
    _bv18._auswahl = ["V1", "V2"]
    _bv18.scan_art, _bv18.scan_name = "slot", "V1"
    _bv18.scan_verschieben({"dx": 3, "dy": -2})
    check("beide Flaechen wandern", _bv18.slots["V1"].scan_region == (103, 98, 163, 158)
          and _bv18.slots["V2"].scan_region == (203, 98, 257, 152))
    # Der Klickpunkt geht MIT, statt neu aus der Mitte gerechnet zu werden: er
    # ist womoeglich bewusst aus der Mitte gesetzt.
    check("und der Klickpunkt behaelt seine Lage im Slot",
          _bv18.slots["V1"].click_pos == (113, 148))
    _bv18.scan_rueckgaengig()
    check("Verschieben laesst sich zuruecknehmen",
          _bv18.slots["V1"].scan_region == (100, 100, 160, 160))

    # Eine GEHALTENE Pfeiltaste ist EIN Verschieben, nicht dreissig.
    _tiefe18 = _bv18.scan_daten()["undo"]["tiefe"]
    _bv18.scan_verschieben({"dx": 1, "dy": 0})
    for _i18 in range(9):
        _bv18.scan_verschieben({"dx": 1, "dy": 0, "zaehlt": False})
    check("eine Serie legt nur einen Schritt auf den Stapel",
          _bv18.scan_daten()["undo"]["tiefe"] == _tiefe18 + 1)
    _bv18.scan_rueckgaengig()
    check("und STRG+Z nimmt die ganze Serie zurueck",
          _bv18.slots["V1"].scan_region == (100, 100, 160, 160))
    check("ein Verschieben um nichts aendert nichts",
          _bv18.scan_verschieben({"dx": 0, "dy": 0})["undo"]["tiefe"]
          == _bv18.scan_daten()["undo"]["tiefe"])

    # Angleichen: Median der Auswahl, Mitte bleibt stehen.
    _bv18.scan_groesse_angleichen()
    check("V2 wird auf die mittlere Groesse gezogen",
          _bv18.slots["V2"].scan_region[2] - _bv18.slots["V2"].scan_region[0] == 60)
    check("und seine Mitte bleibt, wo sie war",
          (_bv18.slots["V2"].scan_region[0] + _bv18.slots["V2"].scan_region[2]) // 2
          == 227)
    _bv18.scan_waehlen({"art": "slot", "name": "V1"})     # Einzelauswahl
    check("mit weniger als zwei Slots gibt es nichts anzugleichen",
          _bv18.scan_groesse_angleichen()["status"]["art"] == "warn")

    # Ohne Auswahl wirkt eine Sammel-Aktion auf den EINEN Gewaehlten - dieselbe
    # Regel wie beim Loeschen, und sie steht jetzt an einer Stelle.
    check("ohne Rechteck zaehlt der eine Gewaehlte",
          [s.name for s in _bv18._auswahl_slots()] == ["V1"])
    _bv18.scan_art, _bv18.scan_name = "item", ""
    _bv18._auswahl = []
    check("ohne alles ist die Menge leer", _bv18._auswahl_slots() == [])

    # Die Auswahl in den offenen Scan - zwischen "einer" und "alle" lag nichts.
    _bv18.scan_neu({"name": "Sammel"})
    _bv18._auswahl = ["V1", "V2"]
    _bv18.scan_art, _bv18.scan_name = "slot", "V1"
    _bv18.scan_auswahl_mitglied({"wert": True})
    check("die ganze Auswahl kommt in den Scan",
          _bv18.scans["Sammel"].slot_names == ["V1", "V2"])
    _bv18.scan_auswahl_mitglied({"wert": True})
    check("und zweimal dazu legt sie nicht doppelt an",
          _bv18.scans["Sammel"].slot_names == ["V1", "V2"])
    _bv18.scan_auswahl_mitglied({"wert": False})
    check("heraus nimmt sie wieder weg", _bv18.scans["Sammel"].slot_names == [])

    # Aus der Auswahl lernen: der Fall nach dem Erkennen, wo fuenf Slots orange
    # dastehen und genau die gelernt werden sollen.
    _gelernt18 = []
    _bv18._lerne_aus_slot = lambda slot, dedup=False: (_gelernt18.append(slot.name)
                                                       or "Neu " + slot.name)
    _bv18._auswahl = ["V2"]
    _bv18.scan_art, _bv18.scan_name = "slot", "V2"
    _bv18.scan_auswahl_lernen()
    check("gelernt wird nur aus der Auswahl", _gelernt18 == ["V2"])
    _bv18.__dict__.pop("_lerne_aus_slot", None)

    # Hintergrund neu messen: jeder Slot an SICH SELBST, nicht eine Farbe fuer
    # alle - Inventare sind selten gleichmaessig ausgeleuchtet.
    _bv18._foto = object()
    _bv18._foto_info = {"links": 0, "oben": 0, "skala": 1.0, "breite": 500,
                        "hoehe": 500, "stand": 0.0}
    _bv18._foto_farbe = lambda x, y: (x % 256, y % 256, 7)
    _bv18._auswahl = ["V1", "V2"]
    _bv18.scan_auswahl_farbe()
    check("jeder Slot bekommt die Farbe seiner eigenen inneren Ecke",
          _bv18.slots["V1"].slot_color != _bv18.slots["V2"].slot_color)
    check("und zwar die an (x1+2, y1+2)",
          _bv18.slots["V1"].slot_color
          == (_bv18.slots["V1"].scan_region[0] + 2,
              _bv18.slots["V1"].scan_region[1] + 2, 7))

    # ------------------------------------------------------------------------
    # Handgriffe ohne Moduswechsel
    # ------------------------------------------------------------------------
    # Fuer eine Korrektur zwischendurch erst eine Kachel anzuklicken ist ein
    # Handgriff zu viel. Die Modi bleiben - sie beantworten "was tut ein Klick
    # gerade" -, aber diese beiden gelten dem Slot unter dem Zeiger.
    _bv18.scan_waehlen({"art": "item", "name": ""})
    _z18 = _bv18.scan_direkt({"x": 130, "y": 130, "was": "messen"})
    check("ALT-Klick waehlt den Slot unter dem Zeiger",
          _z18["wahl"] == {"art": "slot", "name": "V1"})
    check("und misst dort die Farbe", _bv18.slots["V1"].slot_color == (130, 130, 7))
    check("der Modus bleibt dabei unangetastet", _bv18.scan_modus == _MW18)
    _bv18.scan_direkt({"x": 141, "y": 133, "was": "klick"})
    check("Doppelklick setzt den Klickpunkt", _bv18.slots["V1"].click_pos == (141, 133))
    check("beides laesst sich zuruecknehmen",
          _bv18.scan_rueckgaengig() and _bv18.slots["V1"].click_pos != (141, 133))
    check("neben jedem Slot passiert nichts",
          _bv18.scan_direkt({"x": 9000, "y": 9000, "was": "messen"})["status"]["art"]
          == "info")
    check("und ein unbekannter Handgriff wird gemeldet",
          _bv18.scan_direkt({"x": 130, "y": 130, "was": "quatsch"})["status"]["art"]
          == "err")

    # Der kleinste Slot gewinnt - dieselbe Regel wie beim Auswaehlen, und sie
    # steht jetzt an EINER Stelle (`_slot_unter`), weil es drei Anlaesse gibt,
    # sie zu stellen.
    # Der grosse Slot kommt NACH dem kleinen in die Liste: sonst gaebe auch ein
    # "der zuletzt eingetragene gewinnt" die richtige Antwort, und der Test
    # pruefte etwas anderes, als er behauptet.
    _bv18.slots["Winzig"] = _SLOT8(name="Winzig", scan_region=(120, 120, 140, 140),
                                   click_pos=(130, 130))
    _bv18.slots["Gross"] = _SLOT8(name="Gross", scan_region=(60, 60, 300, 300),
                                  click_pos=(130, 130))
    check("unter dem Zeiger gewinnt der kleinste Slot, nicht der letzte",
          _bv18._slot_unter(130, 130) == "Winzig")
    """

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
      and ".scan-maske.scan-item-maske{grid-template-columns:56px minmax(0,1fr)}"
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
"""
section("Ein abgeschalteter Slot bleibt erreichbar")

_sandS = tempfile.mkdtemp(prefix="studioslotaus_")
_cwdS = _os.getcwd()
_os.chdir(_sandS)
try:
    Path("sequences").mkdir()
    Path("item_scans").mkdir()
    _bS = _SB8(_SEQ8(name="S"), Path("sequences/S.json"), "sequences")
    _bS.scan_daten()
    # Zwei Spiele: das eine Raster bei (100,100), das andere weit rechts.
    _bS.slots["Hier"] = _SLOT8(name="Hier", scan_region=(100, 100, 160, 160),
                                click_pos=(130, 130))
    _bS.slots["Fremd"] = _SLOT8(name="Fremd", scan_region=(4000, 900, 4060, 960),
                                 click_pos=(4030, 930))
    _bS.scan_neu({"name": "Inv"})
    _bS.scan_mitglied({"scan": "Inv", "art": "slot", "name": "Hier"})
    # Ein aufgenommenes Bild statt eines echten Screenshots: „zu sehen" hat
    # ohne Aufnahme keine Bedeutung, und die Aufnahme selbst braucht Pillow.
    _bS._foto_info = {"links": 0, "oben": 0, "breite": 800, "hoehe": 600,
                      "skala": 1.0, "stand": 0.0}
    _zS = _bS.scan_daten()
    _slotsS = {s["name"]: s for s in _zS["slots"]}

    # **„Gehört dazu ODER ist gerade zu sehen"** — dieselbe Regel wie beim Item,
    # nur heisst „zu sehen" hier: der Slot liegt im aufgenommenen Bild. Ohne das
    # war ein abgehakter Slot endgültig weg, sobald man den Reiter wechselte:
    # er erfüllt den Filter nicht mehr, und anders als ein Item hatte er keinen
    # zweiten Grund, trotzdem dazustehen. Wieder anhaken kann man nur, was man
    # sieht.
    check("ein Slot im Bild gilt als sichtbar", _slotsS["Hier"]["erkannt"] is True)
    check("und einer des anderen Spiels nicht", _slotsS["Fremd"]["erkannt"] is False)

    # Abgehakt bleibt er sichtbar — genau darum geht es.
    _bS.scan_mitglied({"scan": "Inv", "art": "slot", "name": "Hier"})
    _slotsS = {s["name"]: s for s in _bS.scan_daten()["slots"]}
    check("abgehakt gehoert er nicht mehr dazu", _slotsS["Hier"]["dabei"] is False)
    check("bleibt aber sichtbar und damit anklickbar",
          _slotsS["Hier"]["erkannt"] is True)

    # Die Ansicht filtert auf genau diese beiden Merkmale — an EINER Stelle.
    check("und die Ansicht filtert auf beide",
          "e.dabei || e.erkannt" in _html18)
finally:
    _os.chdir(_cwdS)
    shutil.rmtree(_sandS, ignore_errors=True)
"""


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
    Path("item_scans").mkdir()
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
    Path("item_scans").mkdir()
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
    Path("item_scans").mkdir()
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
          and "scan_items_autoname" in studio_web_source())
finally:
    _os.chdir(_cwd_vorlage)
