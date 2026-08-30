"""Boss- und Icon-Scans im Scans-Reiter: Region, Erkennung, Aktion, Test.

Bis hierher waren die beiden nur ueber die Konsolen-Editoren erreichbar und
standen in keinem Test. Was jetzt zaehlt, ist dasselbe wie beim Item-Teil: nicht
die Ansicht (die laeuft in keinem Test), sondern was die Bruecke daraus macht —
aus zwei Klicks eine Region, aus einem Klick ein Punkt in `points.json`, aus
einem Verschieben ein Boss, der in jedem Scan gilt.

Zwei Eigenschaften sind wichtiger als alle Feldsetzer zusammen und stehen
deshalb zuerst: **Testen fuehrt die Aktion nicht aus**, und **die Ansicht
erfindet keine Aktionsnamen**.
"""
import json
import os as _os
import re
import tempfile
from pathlib import Path

from ._harness import check, section, studio_web_source
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.editors.sequence_studio.scans import (
    ARTEN as _ARTEN, MIN_REGION as _MIN_REGION, MODI as _MODI,
    MODI_ALLE as _MODI_ALLE, MODUS_AKTION as _M_AKTION,
    MODUS_REGION as _M_REGION, MODUS_WAHL as _M_WAHL,
)
from autoclicker.models import (
    Sequence as _SEQ, VALID_BOSS_ACTIONS as _V_BOSS,
    VALID_ICON_ACTIONS as _V_ICON, VALID_SCAN_MODES as _V_MODI,
)

_web = studio_web_source()

# ---------------------------------------------------------------------------
section("Erkennungs-Scans: die Seite erfindet weder Methoden noch Aktionswerte")

# **Dieselbe Klasse Fehler wie beim `ruf()`-Vertrag, nur eine Ebene tiefer.**
# Boss und Icon beantworten dieselben Fragen mit anderen Methoden; als
# Ternaeroperator ueber ein halbes Dutzend Aufrufstellen verteilt faende der
# Vertragstest in `test_logic.py` keinen einzigen davon (er sucht nach
# `rufScan("name"`). Deshalb stehen sie in EINER Tabelle — und die wird hier
# gemessen.
_tabelle = _web[_web.index("const ERK_BEFEHL = {"):]
_tabelle = _tabelle[:_tabelle.index("};")]
_befehle = sorted(set(re.findall(r':\s*"([a-z_]+)"', _tabelle)))
check("die Befehlstabelle der Erkennungs-Arten ist da", len(_befehle) >= 8)
_fehlend = [n for n in _befehle if not callable(getattr(_SB, n, None))]
check("jeden Namen darin gibt es in der Bruecke", _fehlend == [])
if _fehlend:
    print("        fehlt in der Bruecke: " + ", ".join(_fehlend))

import inspect as _inspect
_unpassend = []
for _name in _befehle:
    try:
        _inspect.signature(getattr(_SB, _name)).bind(None, None)
    except TypeError:
        _unpassend.append(_name)
check("und jede nimmt das eine Argument an, das die Seite schickt", _unpassend == [])

# Die SCAN-ART-Kacheln im HTML gegen die Arten der Bruecke — Zug um Zug, nicht
# als Menge: die Reihenfolge ist die Rangfolge (Items zuerst, das ist der Fall,
# den es am laengsten gibt).
_kacheln = re.findall(r'data-scan-art="([a-z]+)"', _web)
check("jede Scan-Art hat eine Kachel, in der Reihenfolge der Bruecke",
      _kacheln == list(_ARTEN))
_js_arten = re.search(r'const SCAN_ARTEN = \[([^\]]+)\]', _web)
check("und die Seite fuehrt dieselbe Liste",
      _js_arten is not None
      and re.findall(r'"([a-z]+)"', _js_arten.group(1)) == list(_ARTEN))

# ---------------------------------------------------------------------------
section("Boss- und Icon-Scans: anlegen, Region, Felder, Bibliothek")

_sand = tempfile.mkdtemp(prefix="studioerk_")
_cwd = _os.getcwd()
_os.chdir(_sand)
try:
    Path("sequences/s/templates").mkdir(parents=True)
    _b = _SB(_SEQ(name="S"), Path("sequences/s/sequence.json"), "sequences")

    _z = _b.scan_daten()
    check("ohne Bestand ist die Boss-Liste leer", _z["boss_scans"] == [])
    check("und die Bibliothek auch", _z["global_bosses"] == [])
    check("die Aktionskacheln kommen aus models.py — Bosse",
          {a["wert"] for a in _z["aktionen"]["boss"]} == _V_BOSS)
    check("die Aktionskacheln kommen aus models.py — Icons",
          {a["wert"] for a in _z["aktionen"]["icon"]} == _V_ICON)
    check("und die Scan-Modi ebenso",
          {m["wert"] for m in _z["aktionen"]["scan_modi"]} == _V_MODI)
    check("ein Item-Scan taucht als Aktionsziel gar nicht bei Icons auf",
          "item_scan" not in {a["wert"] for a in _z["aktionen"]["icon"]})

    _z = _b.boss_scan_neu({"name": "Bossfarm"})
    check("ein neuer Boss-Scan ist sofort offen", _z["boss"]["offen"] == "Bossfarm")
    check("und ungespeichert", _z["dirty"] is True)
    _b.boss_scan_neu({"name": "Bossfarm"})
    check("ein zweiter mit demselben Namen bekommt einen eigenen",
          sorted(_b.boss_scans) == ["Bossfarm", "Bossfarm 2"])

    # Der zuletzt angelegte ist der offene — zurueck auf den ersten.
    _z = _b.boss_scan_oeffnen({"name": "Bossfarm"})
    check("ein anderer Scan laesst sich oeffnen", _z["boss"]["offen"] == "Bossfarm")

    # --- Region ---
    _z = _b.boss_scan_setzen({"name": "Bossfarm", "feld": "region",
                              "wert": [1164, 296, 742, 188]})
    _region = _b.boss_scans["Bossfarm"].scan_region
    check("eine verdrehte Region wird normalisiert", _region == (742, 188, 1164, 296))
    _vorher = dict(_b.boss_scans["Bossfarm"].__dict__)
    _z = _b.boss_scan_setzen({"name": "Bossfarm", "feld": "region",
                              "wert": [10, 10, 10 + _MIN_REGION - 1, 40]})
    check("eine zu schmale Region wird abgelehnt statt gesetzt",
          _b.boss_scans["Bossfarm"].scan_region == (742, 188, 1164, 296))
    check("und sie sagt warum", _z["status"]["art"] == "warn")
    _z = _b.boss_scan_setzen({"name": "Bossfarm", "feld": "region", "wert": ["a", 1, 2, 3]})
    check("Buchstaben in einer Region sind ein Fehler", _z["status"]["art"] == "err")

    # --- Bosse ---
    _b.boss_neu({"name": "Ancient Dragon"})
    _boss = _b.boss_scans["Bossfarm"].bosses[0]
    check("ein neuer Boss haengt im offenen Scan", _boss.name == "Ancient Dragon")
    check("er ist gleich gewaehlt", _b.boss_wahl == "Ancient Dragon")
    check("und faengt mit 'ueberspringen' an — erkannt, aber noch nichts entschieden",
          _boss.action == "skip")

    _z = _b.boss_setzen({"feld": "konfidenz", "wert": 0.85})
    check("die Konfidenz laesst sich einzeln setzen", _boss.min_confidence == 0.85)
    _z = _b.boss_setzen({"feld": "konfidenz", "wert": 1.4})
    check("eine Konfidenz ueber 1 wird abgelehnt", _boss.min_confidence == 0.85)
    check("und begruendet", _z["status"]["art"] == "err")
    _z = _b.boss_setzen({"feld": "aktion", "wert": "gibtsnicht"})
    check("ein erfundener Aktionswert wird abgelehnt", _boss.action == "skip")
    _b.boss_setzen({"feld": "aktion", "wert": "item_scan"})
    _b.boss_setzen({"feld": "scan", "wert": "Inventar"})
    _b.boss_setzen({"feld": "verzoegerung", "wert": 1.5})
    check("Aktion, Ziel und Verzoegerung stehen einzeln",
          (_boss.action, _boss.action_scan, _boss.action_delay)
          == ("item_scan", "Inventar", 1.5))
    _z = _b.boss_setzen({"feld": "verzoegerung", "wert": -1})
    check("eine negative Verzoegerung wird abgelehnt", _boss.action_delay == 1.5)

    # **Der Name IST die Referenz** — und ein zweiter gleichen Namens verdeckt
    # den ersten, ohne dass man es sieht. Deshalb kollidiert er auch gegen die
    # Bibliothek, nicht nur gegen den eigenen Scan.
    _b.boss_neu({"name": "Ancient Dragon"})
    check("ein zweiter Boss bekommt einen eigenen Namen",
          [x.name for x in _b.boss_scans["Bossfarm"].bosses]
          == ["Ancient Dragon", "Ancient Dragon 2"])
    _b.boss_loeschen({"name": "Ancient Dragon 2"})
    check("und laesst sich wieder entfernen",
          len(_b.boss_scans["Bossfarm"].bosses) == 1)

    # --- Bibliothek ---
    _b.boss_waehlen({"name": "Ancient Dragon"})
    _b.boss_global_verschieben({})
    check("verschoben liegt er in der Bibliothek",
          [x.name for x in _b.global_bosses] == ["Ancient Dragon"])
    check("und nicht mehr im Scan", _b.boss_scans["Bossfarm"].bosses == [])
    check("die Wahl wandert mit — sonst zeigt die rechte Spalte ins Leere",
          _b.boss_wahl_global is True)
    check("er gilt trotzdem in diesem Scan",
          [x.name for x in _b._gemergte_bosse(_b.boss_scans["Bossfarm"])]
          == ["Ancient Dragon"])
    # Ein lokaler gleichen Namens gewinnt — so merged auch `execute_boss_scan`.
    _b.boss_scans["Bossfarm"].bosses.append(
        type(_b.global_bosses[0])(name="Ancient Dragon", min_confidence=0.5))
    _gemergt = _b._gemergte_bosse(_b.boss_scans["Bossfarm"])
    check("bei Namensgleichheit gewinnt der lokale",
          len(_gemergt) == 1 and _gemergt[0].min_confidence == 0.5)
    _b.boss_scans["Bossfarm"].bosses.clear()

    # --- Icon-Scan ---
    _b.icon_scan_neu({"name": "Mission nicht machbar"})
    check("ein Icon-Scan ist sofort offen", _b.icon_offen == "Mission nicht machbar")
    _icon = _b.icon_scans["Mission nicht machbar"]
    _b.icon_setzen({"feld": "region", "wert": [100, 100, 158, 158]})
    _b.icon_setzen({"feld": "aktion", "wert": "click"})
    _b.icon_setzen({"feld": "toleranz", "wert": 18})
    check("Region, Aktion und Toleranz stehen einzeln",
          (_icon.scan_region, _icon.action, _icon.color_tolerance)
          == ((100, 100, 158, 158), "click", 18))
    _z = _b.icon_setzen({"feld": "aktion", "wert": "item_scan"})
    check("ein Item-Scan ist als Icon-Aktion nicht erlaubt", _icon.action == "click")

    # --- Werkzeuge ---
    section("Region und Klickpunkt: zwei Werkzeuge, ein Rueckweg")
    check("die Modi der Item-Ansicht bleiben unter sich",
          _M_REGION not in _MODI and _M_AKTION not in _MODI)
    check("angenommen werden sie trotzdem",
          _M_REGION in _MODI_ALLE and _M_AKTION in _MODI_ALLE)
    _z = _b.scan_modus_setzen({"modus": _M_REGION})
    check("ohne Ziel schaltet der Buchstabe nicht scharf", _b.scan_modus != _M_REGION)
    check("und sagt, was fehlt", _z["status"]["art"] == "warn")

    # Ohne Bild gibt es nichts anzuklicken — dann bleibt das Werkzeug aus.
    _z = _b.region_modus({"art": "icon", "modus": _M_REGION})
    check("ohne Screenshot kein Aufziehen", _b.scan_modus == _M_WAHL)
    check("und es steht dabei, warum", "Screenshot" in _z["status"]["text"])

    # -----------------------------------------------------------------------
    # Alles Weitere braucht ein Bild. Denselben Weg geht der Item-Teil: die
    # Aufnahme wird gestellt, alles dahinter ist echt.
    _hat_pil = False
    try:
        from PIL import Image as _PILImage
        _hat_pil = True
    except ImportError:
        pass

    if not _hat_pil:
        print("  ----  Bild-Teil uebersprungen (Pillow nicht installiert)")
    else:
        section("Erkennungs-Scans auf einem gestellten Bild")
        # Ein grauer Schirm mit einem roten Ausrufezeichen-Fleck bei (300,200).
        _bild = _PILImage.new("RGB", (800, 600), (24, 28, 36))
        for _x in range(300, 340):
            for _y in range(200, 240):
                _bild.putpixel((_x, _y), (60, 64, 78))
        for _x in range(312, 328):
            for _y in range(206, 234):
                _bild.putpixel((_x, _y), (220, 50, 60))

        import autoclicker.imaging as _img
        import autoclicker.winapi as _win
        _echt_shot, _echt_org = _img.take_screenshot, _win.get_virtual_origin
        _img.take_screenshot = lambda region=None: (
            _bild.copy() if not region else _bild.crop(tuple(region)))
        _win.get_virtual_origin = lambda: (0, 0)
        try:
            _z = _b.scan_foto()
            check("das gestellte Bild steht in der Aufnahme",
                  _z["foto"] and _z["foto"]["breite"] == 800)

            # --- Region aus zwei Klicks ---
            _b.icon_scan_oeffnen({"name": "Mission nicht machbar"})
            _z = _b.region_modus({"art": "icon", "modus": _M_REGION})
            check("mit Bild und Ziel schaltet das Werkzeug scharf",
                  _z["modus"] == _M_REGION)
            check("und die Bruecke merkt sich, WORAUF es wirkt",
                  _z["region_ziel"] == ["icon", "Mission nicht machbar"])
            _z = _b.scan_klick({"x": 300, "y": 200})
            check("die erste Ecke legt noch nichts an",
                  _z["ecke"] == [300, 200]
                  and _b.icon_scans["Mission nicht machbar"].scan_region
                      == (100, 100, 158, 158))
            _z = _b.scan_klick({"x": 340, "y": 240})
            check("die zweite Ecke setzt die Region",
                  _b.icon_scans["Mission nicht machbar"].scan_region == (300, 200, 340, 240))
            check("und das Werkzeug faellt ins Auswaehlen zurueck", _z["modus"] == _M_WAHL)
            check("das Ziel ist danach weg — es gehoerte zu diesem einen Durchgang",
                  _z["region_ziel"] is None)

            # --- Der Ausschnitt zeigt, was der Scan sieht ---
            _ic = [c for c in _z["icon_scans"] if c["name"] == "Mission nicht machbar"][0]
            check("der offene Icon-Scan bringt seinen Ausschnitt mit",
                  _ic["ausschnitt"].startswith("data:image/png;base64,"))

            # --- Marker messen und testen ---
            _z = _b.marker_messen({"art": "icon"})
            _ic = _b.icon_scans["Mission nicht machbar"]
            check("die Marker kommen aus der Region", len(_ic.marker_colors) > 0)
            check("und die auffaelligste Farbe ist das Symbol",
                  (220 // 5 * 5, 50 // 5 * 5, 60 // 5 * 5) in _ic.marker_colors)

            _dirty_vorher = _b._scan_dirty
            _z = _b.icon_testen({})
            _t = _z["icon"]["test"]
            check("der Test erkennt das Icon", _t["ok"] is True)
            check("er nennt die Methode", _t["methode"] == "Marker")
            check("und er zaehlt die Marker", _t["marker_gesamt"] == len(_ic.marker_colors))
            # **Testen ist folgenlos.** Ein Testknopf, der im Editor eines
            # Autoclickers wirklich klickt, ist die schlechteste denkbare
            # Ueberraschung — deshalb steht die Aktion nur als Satz da.
            check("er benennt die Aktion, statt sie auszufuehren",
                  "klicken" in _t["aktion"] or "Punkt" in _t["aktion"])
            check("und er aendert nichts an den Daten",
                  _b._scan_dirty == _dirty_vorher)

            # --- Der Vorschlag ist der Kern des Fehlerfalls ---
            _b.icon_setzen({"feld": "toleranz", "wert": 0})
            _b.icon_setzen({"feld": "region", "wert": [400, 400, 460, 460]})
            _z = _b.icon_testen({})
            _t = _z["icon"]["test"]
            check("ausserhalb des Symbols wird nichts erkannt", _t["ok"] is False)
            check("und der Grund steht dabei", "Marker" in _t["grund"])

            # --- Vorlage aufnehmen ---
            _b.icon_setzen({"feld": "region", "wert": [300, 200, 340, 240]})
            _z = _b.vorlage_aufnehmen({"art": "icon"})
            _ic = _b.icon_scans["Mission nicht machbar"]
            check("die Vorlage wird als Datei angelegt", bool(_ic.template))
            check("und liegt bei den Templates",
                  (Path("sequences/s/templates") / _ic.template).exists())

            # --- Klickpunkt ueber einen Punkt, nie ueber Zahlen ---
            _b.icon_setzen({"feld": "aktion", "wert": "click"})
            _b.region_modus({"art": "icon", "modus": _M_AKTION})
            _z = _b.scan_klick({"x": 500, "y": 320})
            _ic = _b.icon_scans["Mission nicht machbar"]
            check("der Klick legt einen Punkt an", len(_b.points) == 1)
            check("und der Scan verweist auf ihn per ID",
                  _ic.action_point_id == _b.points[0].id)
            check("die Koordinate steht im Punkt", (_b.points[0].x, _b.points[0].y)
                  == (500, 320))
            # **Ein vorhandener Punkt wird wiederverwendet** — sonst laege
            # derselbe Knopf zweimal in points.json, und beim Nachjustieren
            # wanderte die Haelfte.
            _b.boss_scan_oeffnen({"name": "Bossfarm"})
            _b.boss_neu({"name": "Hydra"})
            _b.boss_setzen({"feld": "aktion", "wert": "click"})
            _b.region_modus({"art": "boss", "modus": _M_AKTION})
            _b.scan_klick({"x": 500, "y": 320})
            check("ein zweiter Klick auf dieselbe Stelle legt keinen zweiten Punkt an",
                  len(_b.points) == 1)

            # --- Boss testen, alle testen ---
            _b.boss_scan_setzen({"name": "Bossfarm", "feld": "region",
                                 "wert": [300, 200, 340, 240]})
            _b.marker_messen({"art": "boss"})
            _z = _b.boss_testen({})
            check("der Boss-Test laeuft auf der Region des SCANS",
                  _z["boss"]["test"]["ok"] is True)
            _z = _b.boss_alle_testen({})
            # Getestet wird die GEMERGTE Liste — lokal plus Bibliothek. Nur
            # die lokalen zu pruefen hiesse, die Haelfte der Erkennung zu
            # verschweigen: der Lauf sieht beide.
            check("alle testen fuellt eine Zeile je Boss — auch fuer die Bibliothek",
                  set(_z["boss"]["tests"]) == {"Hydra", "Ancient Dragon"})

            # --- Rueckgaengig nimmt den ganzen Stand zurueck ---
            section("Rueckgaengig und Speichern umfassen alle drei Scan-Arten")
            _vor = len(_b.icon_scans)
            _b.icon_scan_neu({"name": "Wegwerf"})
            check("der neue Icon-Scan ist da", len(_b.icon_scans) == _vor + 1)
            _z = _b.scan_rueckgaengig()
            check("STRG+Z nimmt ihn zurueck", len(_b.icon_scans) == _vor)
            check("und sagt, was es war", "Icon-Scan" in _z["status"]["text"])

            # --- Speichern und wieder laden ---
            _z = _b.scan_speichern()
            check("das Speichern meldet alle drei Arten",
                  "Boss-Scan" in _z["status"]["text"]
                  and "Icon-Scan" in _z["status"]["text"])
            check("die Boss-Scan-Datei steht da",
                  Path("sequences/s/boss_scans/bossfarm.json").exists())
            check("die Icon-Scan-Datei auch",
                  Path("sequences/s/icon_scans/mission_nicht_machbar.json").exists())
            check("und die Bibliothek",
                  Path("sequences/s/boss_scans/bibliothek.json").exists())
            # **Die Punkte gehen mit.** Ein Klickpunkt ist ein Punkt in
            # points.json — bliebe er ungeschrieben, zeigte die gespeicherte
            # Aktion beim naechsten Start ins Leere.
            check("und die Punkte, an denen die Aktionen haengen",
                  Path("sequences/s/sequence.json").exists()
                  and "points" in json.loads(
                      Path("sequences/s/sequence.json").read_text("utf-8")))
            _gespeichert = json.loads(
                Path("sequences/s/boss_scans/bossfarm.json").read_text("utf-8"))
            check("die Region steht in der Datei",
                  list(_gespeichert["scan_region"]) == [300, 200, 340, 240])

            _b2 = _SB(_SEQ(name="S"), Path("sequences/s/sequence.json"), "sequences")
            _z2 = _b2.scan_daten()
            check("ein frisches Studio liest alles zurueck",
                  {c["name"] for c in _z2["boss_scans"]} == {"Bossfarm", "Bossfarm 2"})
            check("samt Icon-Scans",
                  {c["name"] for c in _z2["icon_scans"]} == {"Mission nicht machbar"})
            check("samt Bibliothek",
                  [b["name"] for b in _z2["global_bosses"]] == ["Ancient Dragon"])
            check("und die Bibliothek ist als global markiert",
                  _z2["global_bosses"][0]["global"] is True)

            # --- Fremdaenderung ---
            # Der Konsolen-Editor bleibt der zweite Weg, und ein Lauf legt per
            # LLM entdeckte Bosse in der Bibliothek ab. Ohne diesen Hinweis
            # sucht man sie im Reiter vergeblich.
            check("frisch geladen ist nichts fremd", _z2["fremd"] is False)
            import time as _time
            _time.sleep(0.01)
            _p = Path("sequences/s/icon_scans/mission_nicht_machbar.json")
            _p.write_text(_p.read_text("utf-8"), encoding="utf-8")
            _os.utime(_p, (_p.stat().st_atime + 5, _p.stat().st_mtime + 5))
            check("eine fremde Aenderung an einem Icon-Scan faellt auf",
                  _b2.scan_daten()["fremd"] is True)
        finally:
            _img.take_screenshot = _echt_shot
            _win.get_virtual_origin = _echt_org
finally:
    _os.chdir(_cwd)


# ---------------------------------------------------------------------------
section("Slot-Farben, ELSE und die Werkzeugleiste")

# **Amber gehoert der Auswahl.** „Nichts erkannt" stand auf #FF9500 und war
# damit kaum vom Akzent #F59E0B zu unterscheiden — „hier ist zu tun" und
# „gewaehlt" sahen gleich aus. Und --slot-ok/--slot-fremd lagen als
# #00FF9C/#2DD4BF so dicht beieinander, dass man sie im Bild nicht trennen
# konnte. Die drei Familien stehen hier fest, damit sie nicht zurueckwandern.
_soll_farben = {"--slot-ok": "#00E58A", "--slot-fremd": "#22D3EE",
                "--slot-offen": "#F43F5E"}
for _var, _wert in _soll_farben.items():
    _treffer = re.search(re.escape(_var) + r":\s*(#[0-9A-Fa-f]{6})", _web)
    check(f"{_var} ist {_wert}",
          _treffer is not None and _treffer.group(1).upper() == _wert)
    _f = re.search(re.escape(_var) + r"-f:\s*(#[0-9A-Fa-f]{8})", _web)
    check(f"und {_var}-f traegt dieselbe Farbe",
          _f is not None and _f.group(1)[:7].upper() == _wert)
check("der Akzent gehoert weiterhin der Auswahl — keine Slot-Farbe liegt darauf",
      "#F59E0B" not in _soll_farben.values())

# **Die Kachel traegt ein Schlagwort, der Tooltip den Satz.** Zwei Tabellen fuer
# dieselben Werte laufen auseinander, sobald eine Aktion dazukommt — hier stehen
# sie auf denselben Schluesseln.
from autoclicker.editors.sequence_studio.scan_detect import (
    _AKTION_KURZ as _KURZ, _BOSS_AKTIONEN as _ORDNUNG,
)
from autoclicker.models import ACTION_TEXT as _TEXT
check("jede angebotene Aktion hat eine Kurzbeschriftung",
      set(_KURZ) == set(_ORDNUNG))
check("und einen Satz dazu", set(_ORDNUNG) <= set(_TEXT))
check("die Reihenfolge deckt genau die gueltigen Boss-Aktionen ab",
      set(_ORDNUNG) == _V_BOSS)

# **Was etwas kostet, wird gefragt und nicht mitgeliefert.** `autoclicker.ocr`
# importiert EasyOCR beim Laden und zieht damit Torch nach — Sekunden, in denen
# der Reiter stuende. Eine Momentaufnahme entsteht nach JEDEM Klick neu.
check("die Momentaufnahme importiert kein OCR-Backend",
      "from ... import ocr" not in
      re.split(r"def ocr_pruefen", (Path(__file__).resolve().parent.parent.parent
               / "autoclicker/editors/sequence_studio/scan_detect.py")
              .read_text("utf-8"))[0])
check("dafuer gibt es einen eigenen Knopf", callable(getattr(_SB, "ocr_pruefen", None)))
check("und die Seite drueckt ihn", 'rufScan("ocr_pruefen")' in _web)

# **Das ELSE gehoert dem Block, nicht dem Scan.** `IconScanConfig` hat kein
# else-Feld; eins hier einzufuehren hiesse, dieselbe Sache an zwei Stellen zu
# haben — der Sequenz-Editor setzt sie am Block, wo sie fuer alle drei
# Scan-Arten an derselben Stelle steht. Die Ansicht sagt genau das.
from autoclicker.models import IconScanConfig as _ICFG
check("ein Icon-Scan traegt keine eigene ELSE-Aktion",
      not any(f.startswith("else") for f in _ICFG("x").__dict__))
check("und die Ansicht verweist dafuer auf den Block",
      "Die Ersatzaktion gehört dem Block" in _web)

# Die beiden Werkzeuge stehen in derselben Leiste wie „Auswaehlen": sie
# beantworten dieselbe Frage — was tut ein Klick jetzt.
check("die Werkzeugleiste kennt das Region-Werkzeug",
      'data-erk-tool="region"' in _web)
check("und den Klickpunkt", 'data-erk-tool="aktion"' in _web)
check("beide sind bei der Item-Art versteckt statt umgedeutet",
      "knopf.hidden = item;" in _web)

# **Jede Stelle, die die Seite anspricht, muss es auch geben.** `$("x")` auf ein
# fehlendes Element ergibt `null`, und der naechste Zugriff darauf reisst den
# ganzen Aufbau ab — das Fenster bleibt leer, mit einer Zeile in der Konsole,
# die niemand sieht. Dieselbe Klasse Fehler wie ein Methodenname, den es in der
# Bruecke nicht gibt; nur eine Schicht weiter aussen.
_html = (Path(__file__).resolve().parent.parent.parent
         / "autoclicker/editors/sequence_studio/web/index.html").read_text("utf-8")
_js = (Path(__file__).resolve().parent.parent.parent
       / "autoclicker/editors/sequence_studio/web/app.js").read_text("utf-8")
_gefragt = set(re.findall(r'\$\("([a-zA-Z0-9_-]+)"\)', _js))
_vorhanden = set(re.findall(r'id="([a-zA-Z0-9_-]+)"', _html))
# Was die Seite selbst anlegt, zaehlt mit: im Aufbau (`id: "x"`) und als
# Konstante daneben (`const xId = "y"`).
_vorhanden |= set(re.findall(r'\bid:\s*"([a-zA-Z0-9_-]+)"', _js))
_vorhanden |= set(re.findall(r'Id\s*=\s*"([a-zA-Z0-9_-]+)"', _js))
_ohne = sorted(_gefragt - _vorhanden)
check("jede von der Seite angesprochene Stelle gibt es auch", _ohne == [])
if _ohne:
    print("        fehlt in index.html: " + ", ".join(_ohne))
check("die neuen Bloecke der Erkennungs-Arten sind darunter",
      {"ab-erk-wahl", "ab-erk-weg", "scan-bibliothek"} <= _gefragt)
check("und der Umschalter steht im Dokument", 'id="scan-art"' in _html)
