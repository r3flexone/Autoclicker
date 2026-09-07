"""Der Item-Katalog: Laden, Einordnen, geschlossene LLM-Auswahl.

Gemessen wird an beiden Enden — `tools/katalog.py` bildet die Kategorie, der
Autoclicker liest sie. Laufen die auseinander, ist der Katalog stillschweigend
nutzlos: die Namen passen, aber die Einordnung greift nie.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

from ._harness import check, section, studio_web_source as _studio_web_kh

_repo = Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


# =============================================================================
section("Katalog: Nachschlagen und Raenge")
# =============================================================================

from autoclicker.katalog import Katalog, lade_katalog, raenge, LEER  # noqa: E402

_k = Katalog({
    "Citadel Helmet": {"kategorie": "Helm", "wert": 15000},
    "Centaurs Helmet": {"kategorie": "Helm", "wert": 20000},
    "Bronze Helmet": {"kategorie": "Helm", "wert": 32},
    "Godlike Pickaxe": {"kategorie": "Pickaxe", "wert": 500000},
}, ["Black Dragon", "Banshee"])

check("kennt seine Items", len(_k) == 4 and bool(_k))
check("leerer Katalog ist falsy", not Katalog() and not LEER)
check("Kategorie ueber den Namen", _k.kategorie("Citadel Helmet") == "Helm")
# Ein Modell antwortet mal so, mal so — und zwei Schreibweisen desselben Namens
# ergaeben ueber `_kategorie_normalisieren` zwei Kategorien mit demselben Wort.
check("Schreibweise egal beim Nachschlagen", _k.kategorie("citadel HELMET") == "Helm")
check("zurueck kommt die Katalog-Schreibweise", _k.treffer("citadel helmet") == "Citadel Helmet")
check("Leerraum stoert nicht", _k.treffer("  Citadel Helmet  ") == "Citadel Helmet")
check("unbekannter Name -> None", _k.kategorie("Gibtsnicht") is None)
check("unbekannter Name hat keinen Wert", _k.wert("Gibtsnicht") is None)
check("Wert kommt als Zahl", _k.wert("Godlike Pickaxe") == 500000.0)
check("Gegner stehen bereit", _k.gegner == ["Black Dragon", "Banshee"])
check("namen() ist die geschlossene Liste", "Godlike Pickaxe" in _k.namen() and len(_k.namen()) == 4)

# Der Rang gilt INNERHALB des Scans und dicht. Ein globaler Rang aus dem Katalog
# waere unbrauchbar: der beste Bogen eines Bestands bekaeme P49, weil 48 teurere
# im Katalog stehen, die man gar nicht besitzt.
_r = raenge([("Citadel Helmet", "Helm", 15000), ("Centaurs Helmet", "Helm", 20000),
             ("Bronze Helmet", "Helm", 32), ("Godlike Pickaxe", "Pickaxe", 500000)])
check("teuerstes der Kategorie bekommt P1", _r["Centaurs Helmet"] == 1)
check("Raenge sind dicht", sorted(_r[n] for n in ("Centaurs Helmet", "Citadel Helmet",
                                                  "Bronze Helmet")) == [1, 2, 3])
check("jede Kategorie faengt bei 1 an", _r["Godlike Pickaxe"] == 1)
# Zwei Vorlagen desselben Items sind dasselbe Item; zwei verschiedene Zahlen
# dafuer waeren eine Rangfolge, die per Zufall entscheidet.
_rd = raenge([("Citadel Helmet", "Helm", 15000), ("Citadel Helmet", "Helm", 15000),
              ("Bronze Helmet", "Helm", 32)])
check("gleicher Name -> gleicher Rang", _rd["Citadel Helmet"] == 1 and _rd["Bronze Helmet"] == 2)
check("leere Eingabe ergibt leere Raenge", raenge([]) == {})


# =============================================================================
section("Katalog: Datei lesen (Fremdformat, faellt nie um)")
# =============================================================================

_sand = Path(tempfile.mkdtemp(prefix="katalog_test_"))
check("kein Pfad -> leer", not lade_katalog(""))
check("Datei fehlt -> leer", not lade_katalog(str(_sand / "gibtsnicht.json")))

_kaputt = _sand / "kaputt.json"
_kaputt.write_text("{ das ist kein json", encoding="utf-8")
check("kaputte Datei -> leer statt Absturz", not lade_katalog(str(_kaputt)))

_liste = _sand / "liste.json"
_liste.write_text("[1, 2, 3]", encoding="utf-8")
check("Liste statt Objekt -> leer", not lade_katalog(str(_liste)))

_gut = _sand / "gut.json"
_gut.write_text(json.dumps({
    "items": {
        "Citadel Helmet": {"kategorie": "Helm", "wert": 15000},
        "Kaputt": "kein Objekt",
        "Ohne Wert": {"kategorie": "Helm"},
        "Wert ist Text": {"kategorie": "Helm", "wert": "viel"},
    },
    "gegner": ["Black Dragon", ""],
}), encoding="utf-8")
_gl = lade_katalog(str(_gut))
check("gute Eintraege kommen an", _gl.kategorie("Citadel Helmet") == "Helm")
# Ein kaputter Eintrag darf den Katalog nicht mitnehmen — dieselbe Haltung wie
# bei der Marktwert-Datei: einzeln raus, nicht alles weg.
check("kaputter Eintrag fliegt einzeln raus", _gl.treffer("Kaputt") is None)
check("fehlender Wert wird 0", _gl.wert("Ohne Wert") == 0.0)
check("unbrauchbarer Wert wird 0", _gl.wert("Wert ist Text") == 0.0)
check("leerer Gegnername faellt weg", _gl.gegner == ["Black Dragon"])
check("zweimal laden liefert denselben Katalog (Cache am Dateistand)",
      lade_katalog(str(_gut)) is _gl)


# =============================================================================
section("tools/katalog.py: die Kategorie wird ENG gebildet")
# =============================================================================

from tools.katalog import anzeigename, kategorie_fuer, baue_katalog  # noqa: E402

check("Schluessel wird Anzeigename", anzeigename("godlike_bow") == "Godlike Bow")

# EquipmentSlot traegt die Bedeutung schon: ein Helm, ein Schild, ein Paar Stiefel.
check("Slot 11 ist der Helm", kategorie_fuer({"Name": "bronze_helmet", "EquipmentSlot": 11}) == "Helm")
check("Slot 1 sind die Stiefel", kategorie_fuer({"Name": "iron_boots", "EquipmentSlot": 1}) == "Stiefel")
check("Slot 10 ist der Umhang, auch mit Zahl im Namen",
      kategorie_fuer({"Name": "archery_cape_tier_1", "EquipmentSlot": 10}) == "Umhang")

# **Slot 7 MUSS aufgetrennt werden.** Dort liegen 200 Waffen UND Werkzeuge, weil
# das Spiel sie in derselben Hand fuehrt. Als eine Kategorie hiesse das bei
# `SCAN_MODE_ALL`: aus Spitzhacke, Beil und Bogen wird genau eines geklickt.
check("Slot 7 wird am letzten Wort getrennt (Pickaxe)",
      kategorie_fuer({"Name": "godlike_pickaxe", "EquipmentSlot": 7}) == "Pickaxe")
check("Slot 7: Beil ist etwas anderes als Spitzhacke",
      kategorie_fuer({"Name": "godlike_hatchet", "EquipmentSlot": 7}) == "Hatchet")
check("Slot 7: Bogen ist etwas anderes als Werkzeug",
      kategorie_fuer({"Name": "godlike_bow", "EquipmentSlot": 7}) == "Bow")
check("Slot 0 (keine Ausruestung) am letzten Wort",
      kategorie_fuer({"Name": "diamond_ore", "EquipmentSlot": 0}) == "Ore")
check("ohne Slot-Angabe faellt nichts um",
      kategorie_fuer({"Name": "spruce_log"}) == "Log")
check("ohne Namen gibt es eine Auffangkategorie",
      kategorie_fuer({"Name": "", "EquipmentSlot": 0}) == "Sonstiges")

_gebaut = baue_katalog({
    "Items": {"Items": [
        {"Name": "bronze_helmet", "EquipmentSlot": 11, "BaseValue": 32},
        {"Name": "godlike_bow", "EquipmentSlot": 7, "BaseValue": 333000},
        {"Name": "", "EquipmentSlot": 0},
    ]},
    "ClanBossInfos": [{"BossNameLocalizationKey": "malignant_spider"}],
    "Tasks": {"Combat": [{"EnemyName": "black_dragon"},
                         {"MonsterName": "banshee"}]},
})
check("gebauter Katalog nimmt nur benannte Items", len(_gebaut["items"]) == 2)
check("Wert wandert mit", _gebaut["items"]["Godlike Bow"]["wert"] == 333000)
# Gegner stehen verstreut und tragen drei verschiedene Feldnamen. Einen Zweig zu
# vergessen hiesse, dass die Boss-Liste unvollstaendig ist, ohne dass es auffaellt.
check("Gegner aus allen drei Feldnamen",
      _gebaut["gegner"] == ["Banshee", "Black Dragon", "Malignant Spider"])
check("Quelle steht in der Datei", "idleclans" in _gebaut["_quelle"])

# Beide Enden gegeneinander: was das Werkzeug schreibt, muss der Loader lesen.
_rund = _sand / "rund.json"
_rund.write_text(json.dumps(_gebaut), encoding="utf-8")
_rl = lade_katalog(str(_rund))
check("was tools/katalog.py schreibt, liest autoclicker/katalog.py",
      _rl.kategorie("Godlike Bow") == "Bow" and _rl.wert("Bronze Helmet") == 32.0)


# =============================================================================
section("use_catalog gehoert zum Scan, nicht zur Config")
# =============================================================================

from autoclicker.models import ItemScanConfig  # noqa: E402
from autoclicker.persistence.serialization import (  # noqa: E402
    _item_scan_to_dict, _item_scan_from_dict,
)

check("Standard ist aus", ItemScanConfig(name="x").use_catalog is False)
# Aus ist der Normalfall und wird nicht geschrieben (`_ohne_defaults`).
check("aus wird nicht in die Datei geschrieben",
      "use_catalog" not in _item_scan_to_dict(ItemScanConfig(name="x")))
_an = ItemScanConfig(name="x", use_catalog=True)
check("an wird geschrieben", _item_scan_to_dict(_an)["use_catalog"] is True)
check("an ueberlebt den Roundtrip",
      _item_scan_from_dict(_item_scan_to_dict(_an)).use_catalog is True)
check("eine alte Datei ohne das Feld bekommt den Default",
      _item_scan_from_dict({"name": "alt"}).use_catalog is False)

# **Der Konsolen-Editor baut die Config NEU auf.** Ein Feld, das dort fehlt, ist
# nach dem Bearbeiten eines bestehenden Scans still weg — deshalb muss der
# Schalter dort durchgereicht werden.
_editor_src = (_repo / "autoclicker" / "editors" / "item_scan_editor.py").read_text(encoding="utf-8")
check("der Konsolen-Editor reicht use_catalog durch",
      "use_catalog=use_catalog," in _editor_src)
check("und fragt danach", "_schritt_katalog(" in _editor_src)

# Der Schalter darf NICHT in der Config landen — sonst gaelte er fuer alle Spiele
# gleichzeitig, genau der Fehler, wegen dem `scan_reverse` einmal umgezogen ist.
from autoclicker.config import AppConfig  # noqa: E402
check("use_catalog ist KEIN Config-Feld", not hasattr(AppConfig(), "use_catalog"))
check("der Dateipfad dagegen schon (eine Datei je Spiel)",
      hasattr(AppConfig(), "scan_catalog_file"))

shutil.rmtree(_sand, ignore_errors=True)


# =============================================================================
section("Studio: Katalog anwenden (drei Gruende, und sie sind unterscheidbar)")
# =============================================================================

import os as _os                                                   # noqa: E402
from autoclicker.editors.sequence_studio.bridge import StudioBridge  # noqa: E402
from autoclicker.models import ItemProfile, Sequence               # noqa: E402
from autoclicker import config as _cfgmod                          # noqa: E402

_sand2 = tempfile.mkdtemp(prefix="katalog_bridge_")
_cwd2 = _os.getcwd()
_os.chdir(_sand2)
try:
    Path("sequences").mkdir()
    _kat_datei = Path("katalog.json").resolve()
    _kat_datei.write_text(json.dumps({"items": {
        "Citadel Helmet": {"kategorie": "Helm", "wert": 15000},
        "Centaurs Helmet": {"kategorie": "Helm", "wert": 20000},
        "Godlike Pickaxe": {"kategorie": "Pickaxe", "wert": 500000},
    }}), encoding="utf-8")

    _b = StudioBridge(Sequence(name="S"), Path("sequences/s/sequence.json"), "sequences")
    _merker = _cfgmod.CONFIG.scan_catalog_file

    # 1. Kein Scan offen — der Schalter haengt am Scan, also gibt es ohne Scan
    #    gar keine Antwort auf "benutzt du den Katalog?".
    _cfgmod.CONFIG.scan_catalog_file = str(_kat_datei)
    _a = _b.scan_katalog_anwenden()
    check("ohne offenen Scan wird auf den Scan verwiesen",
          "Scan öffnen" in _a["status"]["text"] and _a["status"]["art"] == "err")

    _b.scan_neu({"name": "Inv"})
    _b.scan_oeffnen({"name": "Inv"})
    for _n in ("Citadel Helmet", "Centaurs Helmet", "item_7"):
        _b.items[_n] = ItemProfile(name=_n)
        _b._dazu("item", _n)

    # 2. Scan offen, Schalter aus — hier sucht man sonst die DATEI, obwohl der
    #    Schalter fehlt. Die Meldung muss das unterscheiden.
    _a = _b.scan_katalog_anwenden()
    check("bei ausgeschaltetem Schalter wird der Schalter genannt",
          "benutzt den Katalog nicht" in _a["status"]["text"])
    check("und die Momentaufnahme sagt: Katalog aus", _b.scan_daten()["katalog_an"] is False)

    _b.scan_setzen({"name": "Inv", "feld": "use_catalog", "wert": True})
    check("der Schalter laesst sich setzen", _b.scans["Inv"].use_catalog is True)
    check("und die Momentaufnahme zieht mit", _b.scan_daten()["katalog_an"] is True)

    # 3. Schalter an, aber keine Datei eingetragen.
    _cfgmod.CONFIG.scan_catalog_file = ""
    _a = _b.scan_katalog_anwenden()
    check("ohne Datei wird die Datei genannt", "Katalog-Datei" in _a["status"]["text"])
    check("ohne Datei ist der Knopf in der Ansicht aus",
          _b.scan_daten()["katalog_an"] is False)

    # --- Jetzt greift es ---
    _cfgmod.CONFIG.scan_catalog_file = str(_kat_datei)
    _a = _b.scan_katalog_anwenden()
    check("zwei bekannte Items werden eingeordnet",
          _b.items["Citadel Helmet"].category == "Helm"
          and _b.items["Centaurs Helmet"].category == "Helm")
    # Teuerstes zuerst: Centaurs (20000) vor Citadel (15000).
    check("die Prioritaet folgt dem Wert, dicht ab 1",
          _b.items["Centaurs Helmet"].priority == 1
          and _b.items["Citadel Helmet"].priority == 2)
    # **Ein selbst vergebener Name wird nicht geraten.** Sonst rutschte
    # "item_7" in eine Kategorie, die niemand gemeint hat.
    check("ein Name ausserhalb des Katalogs bleibt unangetastet",
          _b.items["item_7"].category is None)
    check("und es wird gesagt, wie viele uebrig blieben",
          "1 nicht im Katalog" in _a["status"]["text"])
    check("die Aenderung gilt als ungespeichert", _b._scan_dirty is True)

    # Zweiter Lauf aendert nichts mehr und sagt das, statt "0 eingeordnet" zu melden.
    _a2 = _b.scan_katalog_anwenden()
    check("ein zweiter Lauf meldet 'steht schon richtig'",
          "schon richtig" in _a2["status"]["text"])

    # Rueckgaengig nimmt die ganze Einordnung zurueck, nicht die halbe.
    _b.scan_rueckgaengig()
    check("STRG+Z nimmt die Einordnung zurueck",
          _b.items["Citadel Helmet"].category is None)

    # Eine ausdrueckliche Auswahl gewinnt ueber den ganzen Scan.
    _b.scan_katalog_anwenden({"namen": ["Citadel Helmet"]})
    check("mit Auswahl wirkt es nur auf die Auswahl",
          _b.items["Citadel Helmet"].category == "Helm"
          and _b.items["Centaurs Helmet"].category is None)
    # Allein in seiner Kategorie ist es das beste — P1, nicht P2.
    check("die Prioritaet gilt innerhalb der bearbeiteten Menge",
          _b.items["Citadel Helmet"].priority == 1)

    _cfgmod.CONFIG.scan_catalog_file = _merker
finally:
    _os.chdir(_cwd2)
    shutil.rmtree(_sand2, ignore_errors=True)


# =============================================================================
section("Geschlossene LLM-Auswahl: nur echte Namen kommen zurueck")
# =============================================================================

import autoclicker.llm_vision as _lv                               # noqa: E402

_KANDIDATEN = ["Godlike Bow", "Citadel Helmet", "Godlike Pickaxe"]
_gesehen = {}


def _antworte(text):
    """Ersetzt analyze_image durch eine feste Antwort und merkt den Prompt."""
    def _fake(**kw):
        _gesehen.update(kw)
        return True, text, 1.0
    return _fake


_echt = _lv.analyze_image
try:
    _lv.analyze_image = _antworte("Citadel Helmet")
    check("ein woertlicher Treffer kommt durch",
          _lv.suggest_item_name(None, candidates=_KANDIDATEN) == "Citadel Helmet")
    check("die Kandidaten stehen im System-Prompt",
          "Citadel Helmet" in _gesehen["system_prompt"])
    # Die Anweisung steht auf Englisch, und das ist gemessen: mit dem deutschen
    # Prompt antwortet das Modell deutsch ("Bogen") — in einer Sprache, in der
    # die Liste gar nicht steht.
    check("die Anweisung ist englisch, damit die Antwort zur Liste passt",
          "CANDIDATES" in _gesehen["system_prompt"])

    _lv.analyze_image = _antworte("citadel helmet")
    check("Schreibweise egal, zurueck kommt die Katalog-Form",
          _lv.suggest_item_name(None, candidates=_KANDIDATEN) == "Citadel Helmet")

    # Knapp daneben wird einmal herangezogen — das betraf 3 von 56 echten Vorlagen.
    _lv.analyze_image = _antworte("Godlike Pickax")
    check("knapp daneben wird auf den Katalognamen gezogen",
          _lv.suggest_item_name(None, candidates=_KANDIDATEN) == "Godlike Pickaxe")

    # **Lieber kein Name als ein falscher**: ein falscher wird gespeichert und
    # zieht Kategorie und Prioritaet mit sich.
    _lv.analyze_image = _antworte("Irgendein Schwert")
    check("etwas voellig anderes wird verworfen",
          _lv.suggest_item_name(None, candidates=_KANDIDATEN) is None)
    _lv.analyze_image = _antworte("UNKNOWN")
    check("UNKNOWN ist kein Name", _lv.suggest_item_name(None, candidates=_KANDIDATEN) is None)

    # Ohne Liste bleibt alles wie vorher — der Katalog ist Zusatz, nie Voraussetzung.
    _lv.analyze_image = _antworte("Irgendein Schwert")
    check("ohne Kandidaten bleibt der freie Vorschlag",
          _lv.suggest_item_name(None) == "Irgendein Schwert")
    check("und der Prompt ist dann der alte deutsche",
          "Gegenstände" in _gesehen["system_prompt"])
finally:
    _lv.analyze_image = _echt


# =============================================================================
section("LLM-Mitschrift: was rausgeht und was zurueckkommt")
# =============================================================================
# **Eine leere Antwort hat vier Ursachen, und von aussen sehen sie gleich aus:**
# Modell ohne Bild-Faehigkeit, falscher Modellname, alle Tokens im Reasoning
# verbraucht, schwarzes Bild. Bis hierhin gab es dafuer nur
# `_raw_lmstudio_debug()` in `tools/test_llm.py` — einen ZWEITEN HTTP-Aufruf
# mit einer anderen Frage, der also gerade nicht zeigt, was der echte Aufruf
# bekommen hat.
import contextlib as _ctx_mit                                      # noqa: E402
import io as _io_mit                                               # noqa: E402
import json as _json_mit                                           # noqa: E402
from autoclicker.config import CONFIG as _CFG_mit                  # noqa: E402

_ANTWORT_mit = {"choices": [{"message": {
    "content": "Kraken",
    # Das Denk-Feld verwirft `_extract_response_text` — genau deshalb muss es
    # in der Mitschrift stehen: ein Modell, das alle Tokens ins Denken steckt,
    # liefert einen leeren `content` und sieht sonst aus wie ein Fehler.
    "reasoning_content": "Ich sehe einen Tintenfisch",
}}]}


class _FakeAntwort_mit:
    def __init__(self, nutzlast):
        self._roh = _json_mit.dumps(nutzlast).encode("utf-8")

    def read(self):
        return self._roh

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _lauf_mit(debug, nutzlast=None):
    """analyze_image mit gestubbtem HTTP — gibt (Ergebnis, Konsolentext)."""
    _echt_open = _lv.urllib.request.urlopen
    _alt_debug = _CFG_mit.llm_debug
    _CFG_mit.llm_debug = debug
    _lv.urllib.request.urlopen = lambda *a, **kw: _FakeAntwort_mit(
        nutzlast if nutzlast is not None else _ANTWORT_mit)
    puffer = _io_mit.StringIO()
    try:
        with _ctx_mit.redirect_stdout(puffer):
            erg = _lv.analyze_image(img=_BILD_mit, provider="lmstudio",
                                    model="testmodell", prompt="Wer ist das?")
    finally:
        _lv.urllib.request.urlopen = _echt_open
        _CFG_mit.llm_debug = _alt_debug
    return erg, puffer.getvalue()


_hat_pil_mit = False
try:
    from PIL import Image as _PIL_mit
    _BILD_mit = _PIL_mit.new("RGB", (4, 4), (10, 20, 30))
    _hat_pil_mit = True
except ImportError:
    _BILD_mit = None

if not _hat_pil_mit:
    print("  ----  uebersprungen (Pillow nicht installiert)")
else:
    _erg_aus, _text_aus = _lauf_mit(False)
    check("ohne den Schalter aendert sich am Ergebnis nichts",
          _erg_aus[0] is True and _erg_aus[1] == "Kraken")
    check("und die Konsole bleibt still", _text_aus == "")

    _erg_an, _text_an = _lauf_mit(True)
    check("mit Schalter bleibt das Ergebnis dasselbe",
          _erg_an[0] is True and _erg_an[1] == "Kraken")
    check("die Mitschrift nennt Modell und Prompt",
          "testmodell" in _text_an and "Wer ist das?" in _text_an)
    check("und die rohe Antwort steht da", '"content": "Kraken"' in _text_an)
    # Der Punkt der ganzen Mitschrift: das Denk-Feld, das der Code verwirft.
    check("samt dem Denk-Feld, das der Code selbst verwirft",
          "reasoning_content" in _text_an
          and "Tintenfisch" in _text_an)
    check("und daneben, was daraus gelesen wurde", "gelesen:" in _text_an)

    # Eine leere Antwort ist der haeufigste Fall — und der, bei dem man ohne
    # Hinweis die Ursache raet.
    _erg_leer, _text_leer = _lauf_mit(True, {"choices": [{"message": {"content": ""}}]})
    check("bei leerer Antwort nennt die Mitschrift die moeglichen Ursachen",
          "leer" in _text_leer and "Bild-F" in _text_leer)

    # Auch ein Fehlschlag wird mitgeschrieben — sonst fehlt in der Mitschrift
    # ausgerechnet der Aufruf, der nicht funktioniert hat.
    def _wirf_mit(*a, **kw):
        raise _lv.urllib.error.URLError("kein Server")

    _echt_open_mit = _lv.urllib.request.urlopen
    _alt_debug_mit = _CFG_mit.llm_debug
    _CFG_mit.llm_debug = True
    _lv.urllib.request.urlopen = _wirf_mit
    _puffer_mit = _io_mit.StringIO()
    try:
        with _ctx_mit.redirect_stdout(_puffer_mit):
            _erg_fehl = _lv.analyze_image(img=_BILD_mit, provider="lmstudio",
                                          model="testmodell")
    finally:
        _lv.urllib.request.urlopen = _echt_open_mit
        _CFG_mit.llm_debug = _alt_debug_mit
    check("ein Fehlschlag steht ebenfalls in der Mitschrift",
          _erg_fehl[0] is False and "kein Server" in _puffer_mit.getvalue())


# =============================================================================
section("Katalog holen: aus dem Fenster statt von der Kommandozeile")
# =============================================================================
# **Ausgerechnet die Datei, ohne die das LLM frei raet und die Kategorie leer
# bleibt, liess sich im Studio nicht beschaffen** — der Einstellungen-Reiter
# zeigte den Pfad und verwies auf `python tools/katalog.py`. Gerechnet wird
# weiterhin dort; die Bruecke RUFT das Werkzeug, nie umgekehrt.
import shutil as _sh_kh                                            # noqa: E402
import sys as _sys_kh                                              # noqa: E402
import tempfile as _tmp_kh                                         # noqa: E402
from pathlib import Path as _P_kh                                  # noqa: E402

from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB_kh  # noqa: E402
from autoclicker.models import Sequence as _SEQ_kh                 # noqa: E402

_wurzel_kh = _P_kh(__file__).resolve().parents[2]
if str(_wurzel_kh) not in _sys_kh.path:
    _sys_kh.path.insert(0, str(_wurzel_kh))
import tools.katalog as _tk_kh                                     # noqa: E402

_SPIELDATEN_kh = {"Items": {"Items": [
    {"Name": "godlike_bow", "EquipmentSlot": 7, "BaseValue": 900},
    {"Name": "citadel_helmet", "EquipmentSlot": 11, "BaseValue": 500},
]}, "Raids": [{"BossNameLocalizationKey": "kraken"}]}

_sand_kh = _tmp_kh.mkdtemp(prefix="katalogholen_")
_cwd_kh = _os.getcwd()
_echt_hole_kh = _tk_kh.hole_spieldaten
_alt_pfad_kh = _CFG_mit.scan_catalog_file
_os.chdir(_sand_kh)
try:
    def _bau_kh():
        _P_kh("sequences").mkdir(exist_ok=True)
        return _SB_kh(_SEQ_kh(name="S"), _P_kh("sequences/s/sequence.json"), "sequences")

    _CFG_mit.scan_catalog_file = ""
    _tk_kh.hole_spieldaten = lambda *a, **kw: _SPIELDATEN_kh
    _erg_kh = _bau_kh().katalog_holen()
    check("der Knopf holt und schreibt die Datei",
          _erg_kh["ok"] and _P_kh("katalog.json").exists())
    _inhalt_kh = _json_mit.loads(_P_kh("katalog.json").read_text(encoding="utf-8"))
    check("mit den echten Namen aus der API",
          "Godlike Bow" in _inhalt_kh["items"]
          and _inhalt_kh["items"]["Godlike Bow"]["kategorie"] == "Bow")
    # Ohne diesen Schritt hat man die Datei und trotzdem keine Wirkung — der
    # Scan liest den Pfad, nicht den Ordner.
    check("und traegt den Pfad gleich in die Config ein",
          _CFG_mit.scan_catalog_file.endswith("katalog.json"))
    check("die Meldung nennt, was drin ist", "2 Items" in _erg_kh["meldung"])

    # Ein selbst gesetzter Pfad wird AKTUALISIERT, nicht ueberschrieben: wer
    # zwei Spiele betreibt, hat den Katalog bewusst woanders liegen.
    _CFG_mit.scan_catalog_file = "eigener/pfad.json"
    _erg2_kh = _bau_kh().katalog_holen()
    check("ein eigener Pfad bleibt stehen",
          _erg2_kh["ok"] and _CFG_mit.scan_catalog_file == "eigener/pfad.json"
          and _P_kh("eigener/pfad.json").exists())

    # Kein Netz ist der haeufigste Fehlerfall — und darf die vorhandene Datei
    # nicht zerstoeren. Dieselbe Haltung wie beim Start-Durchgang: lieber
    # nichts tun als halb schreiben.
    _vorher_kh = _P_kh("katalog.json").read_text(encoding="utf-8")

    def _wirf_kh(*a, **kw):
        raise OSError("kein Netz")

    _tk_kh.hole_spieldaten = _wirf_kh
    _CFG_mit.scan_catalog_file = str(_P_kh("katalog.json"))
    _erg3_kh = _bau_kh().katalog_holen()
    check("ohne Netz wird nichts geschrieben",
          _erg3_kh["ok"] is False and "kein Netz" in _erg3_kh["meldung"]
          and _P_kh("katalog.json").read_text(encoding="utf-8") == _vorher_kh)

    # Eine Antwort ohne Items ist kein Katalog — eine leere Datei zu schreiben
    # hiesse, die brauchbare gegen eine unbrauchbare zu tauschen.
    _tk_kh.hole_spieldaten = lambda *a, **kw: {"Items": {"Items": []}}
    _erg4_kh = _bau_kh().katalog_holen()
    check("und eine leere Antwort ueberschreibt die gute Datei nicht",
          _erg4_kh["ok"] is False
          and _P_kh("katalog.json").read_text(encoding="utf-8") == _vorher_kh)

    # --- Wie alt ist die Liste? ---------------------------------------------
    # **Der Pfad allein beantwortet die Frage nicht**, die man an eine geholte
    # Liste hat: liegt die Datei ueberhaupt da, und von wann ist sie? Ohne
    # Antwort holt man sie entweder nie wieder oder bei jedem Zweifel neu.
    check("ein fehlender Katalog sagt genau das",
          "fehlt" in _SB_kh._katalog_stand("gibtsnicht.json"))
    _P_kh("kaputt.json").write_text("{nope", encoding="utf-8")
    check("und eine kaputte Datei auch",
          "nicht lesbar" in _SB_kh._katalog_stand("kaputt.json"))
    check("ohne Pfad steht gar nichts da", _SB_kh._katalog_stand("") == "")
    _P_kh("stempel.json").write_text(_json_mit.dumps({
        "_erzeugt": "2026-09-07T16:42:11Z",
        "items": {"a": {}, "b": {}}, "gegner": ["x"]}), encoding="utf-8")
    _stempel_kh = _SB_kh._katalog_stand("stempel.json")
    check("und sonst Umfang und Zeitpunkt",
          "2 Items" in _stempel_kh and "1 Gegner" in _stempel_kh
          and "07.09.2026" in _stempel_kh)
    # **In Ortszeit, nicht in UTC.** Ein Zeitstempel, den man mit der eigenen
    # Uhr vergleichen soll, darf nicht in einer anderen Zone stehen — 16:42Z
    # ist hier 18:42, und im Winter 17:42.
    from datetime import datetime as _dt_kh, timezone as _tz_kh
    _lokal_kh = _dt_kh(2026, 9, 7, 16, 42, 11, tzinfo=_tz_kh.utc).astimezone()
    check("in Ortszeit", _lokal_kh.strftime("um %H:%M") in _stempel_kh)

    # Der Weg bis in die Ansicht: `config_lesen()` liefert ihn, und die Seite
    # zeichnet ihn unter dem Feld.
    _CFG_mit.scan_catalog_file = "stempel.json"
    _staende_kh = _bau_kh().config_lesen()["staende"]
    check("die Einstellungen liefern den Stand mit",
          "2 Items" in _staende_kh.get("scan_catalog_file", ""))
    check("und die Ansicht zeichnet ihn",
          "C.staende" in _studio_web_kh())
finally:
    _tk_kh.hole_spieldaten = _echt_hole_kh
    _CFG_mit.scan_catalog_file = _alt_pfad_kh
    _os.chdir(_cwd_kh)
    _sh_kh.rmtree(_sand_kh, ignore_errors=True)
