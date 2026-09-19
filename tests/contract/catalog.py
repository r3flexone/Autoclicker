"""Der Item-Katalog: Laden, Einordnen, geschlossene LLM-Auswahl.

Gemessen wird an beiden Enden — `tools/catalog.py` bildet die Kategorie, der
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

from autoclicker.catalog import Catalog, load_catalog, ranks, EMPTY  # noqa: E402

_k = Catalog({
    "Citadel Helmet": {"kategorie": "Helm", "wert": 15000},
    "Centaurs Helmet": {"kategorie": "Helm", "wert": 20000},
    "Bronze Helmet": {"kategorie": "Helm", "wert": 32},
    "Godlike Pickaxe": {"kategorie": "Pickaxe", "wert": 500000},
}, ["Black Dragon", "Banshee"])

check("kennt seine Items", len(_k) == 4 and bool(_k))
check("leerer Katalog ist falsy", not Catalog() and not EMPTY)
check("Kategorie ueber den Namen", _k.category("Citadel Helmet") == "Helm")
# Ein Modell antwortet mal so, mal so — und zwei Schreibweisen desselben Namens
# ergaeben ueber `_category_normalize` zwei Kategorien mit demselben Wort.
check("Schreibweise egal beim Nachschlagen", _k.category("citadel HELMET") == "Helm")
check("zurueck kommt die Katalog-Schreibweise", _k.match("citadel helmet") == "Citadel Helmet")
check("Leerraum stoert nicht", _k.match("  Citadel Helmet  ") == "Citadel Helmet")
check("unbekannter Name -> None", _k.category("Gibtsnicht") is None)
check("unbekannter Name hat keinen Wert", _k.value("Gibtsnicht") is None)
check("Wert kommt als Zahl", _k.value("Godlike Pickaxe") == 500000.0)
check("Gegner stehen bereit", _k.enemy == ["Black Dragon", "Banshee"])
check("names() ist die geschlossene Liste", "Godlike Pickaxe" in _k.names() and len(_k.names()) == 4)

# Der Rang gilt INNERHALB des Scans und dicht. Ein globaler Rang aus dem Katalog
# waere unbrauchbar: der beste Bogen eines Bestands bekaeme P49, weil 48 teurere
# im Katalog stehen, die man gar nicht besitzt.
_r = ranks([("Citadel Helmet", "Helm", 15000), ("Centaurs Helmet", "Helm", 20000),
             ("Bronze Helmet", "Helm", 32), ("Godlike Pickaxe", "Pickaxe", 500000)])
check("teuerstes der Kategorie bekommt P1", _r["Centaurs Helmet"] == 1)
check("Raenge sind dicht", sorted(_r[n] for n in ("Centaurs Helmet", "Citadel Helmet",
                                                  "Bronze Helmet")) == [1, 2, 3])
check("jede Kategorie faengt bei 1 an", _r["Godlike Pickaxe"] == 1)
# Zwei Vorlagen desselben Items sind dasselbe Item; zwei verschiedene Zahlen
# dafuer waeren eine Rangfolge, die per Zufall entscheidet.
_rd = ranks([("Citadel Helmet", "Helm", 15000), ("Citadel Helmet", "Helm", 15000),
              ("Bronze Helmet", "Helm", 32)])
check("gleicher Name -> gleicher Rang", _rd["Citadel Helmet"] == 1 and _rd["Bronze Helmet"] == 2)
check("leere Eingabe ergibt leere Raenge", ranks([]) == {})


# =============================================================================
section("Katalog: Datei lesen (Fremdformat, faellt nie um)")
# =============================================================================

_sandbox = Path(tempfile.mkdtemp(prefix="katalog_test_"))
check("kein Pfad -> leer", not load_catalog(""))
check("Datei fehlt -> leer", not load_catalog(str(_sandbox / "gibtsnicht.json")))

_broken = _sandbox / "kaputt.json"
_broken.write_text("{ das ist kein json", encoding="utf-8")
check("kaputte Datei -> leer statt Absturz", not load_catalog(str(_broken)))

_list = _sandbox / "liste.json"
_list.write_text("[1, 2, 3]", encoding="utf-8")
check("Liste statt Objekt -> leer", not load_catalog(str(_list)))

_good = _sandbox / "gut.json"
_good.write_text(json.dumps({
    "items": {
        "Citadel Helmet": {"kategorie": "Helm", "wert": 15000},
        "Kaputt": "kein Objekt",
        "Ohne Wert": {"kategorie": "Helm"},
        "Wert ist Text": {"kategorie": "Helm", "wert": "viel"},
    },
    "gegner": ["Black Dragon", ""],
}), encoding="utf-8")
_gl = load_catalog(str(_good))
check("gute Eintraege kommen an", _gl.category("Citadel Helmet") == "Helm")
# Ein kaputter Eintrag darf den Katalog nicht mitnehmen — dieselbe Haltung wie
# bei der Marktwert-Datei: einzeln raus, nicht alles weg.
check("kaputter Eintrag fliegt einzeln raus", _gl.match("Kaputt") is None)
check("fehlender Wert wird 0", _gl.value("Ohne Wert") == 0.0)
check("unbrauchbarer Wert wird 0", _gl.value("Wert ist Text") == 0.0)
check("leerer Gegnername faellt weg", _gl.enemy == ["Black Dragon"])
check("zweimal laden liefert denselben Katalog (Cache am Dateistand)",
      load_catalog(str(_good)) is _gl)


# =============================================================================
section("tools/catalog.py: die Kategorie wird ENG gebildet")
# =============================================================================

from tools.catalog import display_name, category_for, build_catalog  # noqa: E402

check("Schluessel wird Anzeigename", display_name("godlike_bow") == "Godlike Bow")

# EquipmentSlot traegt die Bedeutung schon: ein Helm, ein Schild, ein Paar Stiefel.
check("Slot 11 ist der Helm", category_for({"Name": "bronze_helmet", "EquipmentSlot": 11}) == "Helm")
check("Slot 1 sind die Stiefel", category_for({"Name": "iron_boots", "EquipmentSlot": 1}) == "Stiefel")
check("Slot 10 ist der Umhang, auch mit Zahl im Namen",
      category_for({"Name": "archery_cape_tier_1", "EquipmentSlot": 10}) == "Umhang")

# **Slot 7 MUSS aufgetrennt werden.** Dort liegen 200 Waffen UND Werkzeuge, weil
# das Spiel sie in derselben Hand fuehrt. Als eine Kategorie hiesse das bei
# `SCAN_MODE_ALL`: aus Spitzhacke, Beil und Bogen wird genau eines geklickt.
check("Slot 7 wird am letzten Wort getrennt (Pickaxe)",
      category_for({"Name": "godlike_pickaxe", "EquipmentSlot": 7}) == "Pickaxe")
check("Slot 7: Beil ist etwas anderes als Spitzhacke",
      category_for({"Name": "godlike_hatchet", "EquipmentSlot": 7}) == "Hatchet")
check("Slot 7: Bogen ist etwas anderes als Werkzeug",
      category_for({"Name": "godlike_bow", "EquipmentSlot": 7}) == "Bow")
check("Slot 0 (keine Ausruestung) am letzten Wort",
      category_for({"Name": "diamond_ore", "EquipmentSlot": 0}) == "Ore")
check("ohne Slot-Angabe faellt nichts um",
      category_for({"Name": "spruce_log"}) == "Log")
check("ohne Namen gibt es eine Auffangkategorie",
      category_for({"Name": "", "EquipmentSlot": 0}) == "Sonstiges")

_built = build_catalog({
    "Items": {"Items": [
        {"Name": "bronze_helmet", "EquipmentSlot": 11, "BaseValue": 32},
        {"Name": "godlike_bow", "EquipmentSlot": 7, "BaseValue": 333000},
        {"Name": "", "EquipmentSlot": 0},
    ]},
    "ClanBossInfos": [{"BossNameLocalizationKey": "malignant_spider"}],
    "Tasks": {"Combat": [{"EnemyName": "black_dragon"},
                         {"MonsterName": "banshee"}]},
})
check("gebauter Katalog nimmt nur benannte Items", len(_built["items"]) == 2)
check("Wert wandert mit", _built["items"]["Godlike Bow"]["wert"] == 333000)
# Gegner stehen verstreut und tragen drei verschiedene Feldnamen. Einen Zweig zu
# vergessen hiesse, dass die Boss-Liste unvollstaendig ist, ohne dass es auffaellt.
check("Gegner aus allen drei Feldnamen",
      _built["gegner"] == ["Banshee", "Black Dragon", "Malignant Spider"])
check("Quelle steht in der Datei", "idleclans" in _built["_source"])

# Beide Enden gegeneinander: was das Werkzeug schreibt, muss der Loader lesen.
_round_file = _sandbox / "rund.json"
_round_file.write_text(json.dumps(_built), encoding="utf-8")
_rl = load_catalog(str(_round_file))
check("was tools/catalog.py schreibt, liest autoclicker/catalog.py",
      _rl.category("Godlike Bow") == "Bow" and _rl.value("Bronze Helmet") == 32.0)


# =============================================================================
section("use_catalog gehoert zum Scan, nicht zur Config")
# =============================================================================

from autoclicker.models import ItemScanConfig  # noqa: E402
from autoclicker.persistence.serialization import (  # noqa: E402
    _item_scan_to_dict, _item_scan_from_dict,
)

check("Standard ist aus", ItemScanConfig(name="x").use_catalog is False)
# Aus ist der Normalfall und wird nicht geschrieben (`_without_defaults`).
check("aus wird nicht in die Datei geschrieben",
      "use_catalog" not in _item_scan_to_dict(ItemScanConfig(name="x")))
_on = ItemScanConfig(name="x", use_catalog=True)
check("an wird geschrieben", _item_scan_to_dict(_on)["use_catalog"] is True)
check("an ueberlebt den Roundtrip",
      _item_scan_from_dict(_item_scan_to_dict(_on)).use_catalog is True)
check("eine alte Datei ohne das Feld bekommt den Default",
      _item_scan_from_dict({"name": "alt"}).use_catalog is False)

# **Der Konsolen-Editor baut die Config NEU auf.** Ein Feld, das dort fehlt, ist
# nach dem Bearbeiten eines bestehenden Scans still weg — deshalb muss der
# Schalter dort durchgereicht werden.
_editor_src = (_repo / "autoclicker" / "editors" / "item_scan_editor.py").read_text(encoding="utf-8")
check("der Konsolen-Editor reicht use_catalog durch",
      "use_catalog=use_catalog," in _editor_src)
check("und fragt danach", "_step_catalog(" in _editor_src)

# Der Schalter darf NICHT in der Config landen — sonst gaelte er fuer alle Spiele
# gleichzeitig, genau der Fehler, wegen dem `scan_reverse` einmal umgezogen ist.
from autoclicker.config import AppConfig  # noqa: E402
check("use_catalog ist KEIN Config-Feld", not hasattr(AppConfig(), "use_catalog"))
check("der Dateipfad dagegen schon (eine Datei je Spiel)",
      hasattr(AppConfig(), "scan_catalog_file"))

shutil.rmtree(_sandbox, ignore_errors=True)


# =============================================================================
section("Studio: Katalog anwenden (drei Gruende, und sie sind unterscheidbar)")
# =============================================================================

import os as _os                                                   # noqa: E402
from autoclicker.editors.sequence_studio.bridge import StudioBridge  # noqa: E402
from autoclicker.models import ItemProfile, Sequence               # noqa: E402
from autoclicker import config as _cfgmod                          # noqa: E402

_sandbox2 = tempfile.mkdtemp(prefix="katalog_bridge_")
_cwd2 = _os.getcwd()
_os.chdir(_sandbox2)
try:
    Path("sequences").mkdir()
    _cat_file = Path("catalog.json").resolve()
    _cat_file.write_text(json.dumps({"items": {
        "Citadel Helmet": {"kategorie": "Helm", "wert": 15000},
        "Centaurs Helmet": {"kategorie": "Helm", "wert": 20000},
        "Godlike Pickaxe": {"kategorie": "Pickaxe", "wert": 500000},
    }}), encoding="utf-8")

    _b = StudioBridge(Sequence(name="S"), Path("sequences/s/sequence.json"), "sequences")
    _memo = _cfgmod.CONFIG.scan_catalog_file

    # 1. Kein Scan offen — der Schalter haengt am Scan, also gibt es ohne Scan
    #    gar keine Antwort auf "benutzt du den Katalog?".
    _cfgmod.CONFIG.scan_catalog_file = str(_cat_file)
    _a = _b.scan_catalog_apply()
    check("ohne offenen Scan wird auf den Scan verwiesen",
          "Scan öffnen" in _a["status"]["text"] and _a["status"]["kind"] == "err")

    _b.scan_new({"name": "Inv"})
    _b.scan_open({"name": "Inv"})
    for _n in ("Citadel Helmet", "Centaurs Helmet", "item_7"):
        _b.items[_n] = ItemProfile(name=_n)
        _b._add_to_scan("item", _n)

    # 2. Scan offen, Schalter aus — hier sucht man sonst die DATEI, obwohl der
    #    Schalter fehlt. Die Meldung muss das unterscheiden.
    _a = _b.scan_catalog_apply()
    check("bei ausgeschaltetem Schalter wird der Schalter genannt",
          "benutzt den Katalog nicht" in _a["status"]["text"])
    check("und die Momentaufnahme sagt: Katalog aus", _b.scan_data()["catalog_on"] is False)

    _b.scan_set({"name": "Inv", "field": "use_catalog", "value": True})
    check("der Schalter laesst sich setzen", _b.scans["Inv"].use_catalog is True)
    check("und die Momentaufnahme zieht mit", _b.scan_data()["catalog_on"] is True)

    # 3. Schalter an, aber keine Datei eingetragen.
    _cfgmod.CONFIG.scan_catalog_file = ""
    _a = _b.scan_catalog_apply()
    check("ohne Datei wird die Datei genannt", "Katalog-Datei" in _a["status"]["text"])
    check("ohne Datei ist der Knopf in der Ansicht aus",
          _b.scan_data()["catalog_on"] is False)

    # --- Jetzt greift es ---
    _cfgmod.CONFIG.scan_catalog_file = str(_cat_file)
    _a = _b.scan_catalog_apply()
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
    _a2 = _b.scan_catalog_apply()
    check("ein zweiter Lauf meldet 'steht schon richtig'",
          "schon richtig" in _a2["status"]["text"])

    # Rueckgaengig nimmt die ganze Einordnung zurueck, nicht die halbe.
    _b.scan_undo()
    check("STRG+Z nimmt die Einordnung zurueck",
          _b.items["Citadel Helmet"].category is None)

    # Eine ausdrueckliche Auswahl gewinnt ueber den ganzen Scan.
    _b.scan_catalog_apply({"names": ["Citadel Helmet"]})
    check("mit Auswahl wirkt es nur auf die Auswahl",
          _b.items["Citadel Helmet"].category == "Helm"
          and _b.items["Centaurs Helmet"].category is None)
    # Allein in seiner Kategorie ist es das beste — P1, nicht P2.
    check("die Prioritaet gilt innerhalb der bearbeiteten Menge",
          _b.items["Citadel Helmet"].priority == 1)

    _cfgmod.CONFIG.scan_catalog_file = _memo
finally:
    _os.chdir(_cwd2)
    shutil.rmtree(_sandbox2, ignore_errors=True)


# =============================================================================
section("Geschlossene LLM-Auswahl: nur echte Namen kommen zurueck")
# =============================================================================

import autoclicker.llm_vision as _lv                               # noqa: E402

_CANDIDATES = ["Godlike Bow", "Citadel Helmet", "Godlike Pickaxe"]
_seen = {}


def _answer(text):
    """Ersetzt analyze_image durch eine feste Antwort und merkt den Prompt."""
    def _fake(**kw):
        _seen.update(kw)
        return True, text, 1.0
    return _fake


_real = _lv.analyze_image
try:
    _lv.analyze_image = _answer("Citadel Helmet")
    check("ein woertlicher Treffer kommt durch",
          _lv.suggest_item_name(None, candidates=_CANDIDATES) == "Citadel Helmet")
    check("die Kandidaten stehen im System-Prompt",
          "Citadel Helmet" in _seen["system_prompt"])
    # Die Anweisung steht auf Englisch, und das ist gemessen: mit dem deutschen
    # Prompt antwortet das Modell deutsch ("Bogen") — in einer Sprache, in der
    # die Liste gar nicht steht.
    check("die Anweisung ist englisch, damit die Antwort zur Liste passt",
          "CANDIDATES" in _seen["system_prompt"])

    _lv.analyze_image = _answer("citadel helmet")
    check("Schreibweise egal, zurueck kommt die Katalog-Form",
          _lv.suggest_item_name(None, candidates=_CANDIDATES) == "Citadel Helmet")

    # Knapp daneben wird einmal herangezogen — das betraf 3 von 56 echten Vorlagen.
    _lv.analyze_image = _answer("Godlike Pickax")
    check("knapp daneben wird auf den Katalognamen gezogen",
          _lv.suggest_item_name(None, candidates=_CANDIDATES) == "Godlike Pickaxe")

    # **Lieber kein Name als ein falscher**: ein falscher wird gespeichert und
    # zieht Kategorie und Prioritaet mit sich.
    _lv.analyze_image = _answer("Irgendein Schwert")
    check("etwas voellig anderes wird verworfen",
          _lv.suggest_item_name(None, candidates=_CANDIDATES) is None)
    _lv.analyze_image = _answer("UNKNOWN")
    check("UNKNOWN ist kein Name", _lv.suggest_item_name(None, candidates=_CANDIDATES) is None)

    # Ohne Liste bleibt alles wie vorher — der Katalog ist Zusatz, nie Voraussetzung.
    _lv.analyze_image = _answer("Irgendein Schwert")
    check("ohne Kandidaten bleibt der freie Vorschlag",
          _lv.suggest_item_name(None) == "Irgendein Schwert")
    check("und der Prompt ist dann der alte deutsche",
          "Gegenstände" in _seen["system_prompt"])
finally:
    _lv.analyze_image = _real


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

_ANSWER_with = {"choices": [{"message": {
    "content": "Kraken",
    # Das Denk-Feld verwirft `_extract_response_text` — genau deshalb muss es
    # in der Mitschrift stehen: ein Modell, das alle Tokens ins Denken steckt,
    # liefert einen leeren `content` und sieht sonst aus wie ein Fehler.
    "reasoning_content": "Ich sehe einen Tintenfisch",
}}]}


class _FakeAnswer_with:
    def __init__(self, payload):
        self._raw = _json_mit.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _run_with(debug, payload=None):
    """analyze_image mit gestubbtem HTTP — gibt (Ergebnis, Konsolentext)."""
    _real_open = _lv.urllib.request.urlopen
    _old_debug = _CFG_mit.llm_debug
    _CFG_mit.llm_debug = debug
    _lv.urllib.request.urlopen = lambda *a, **kw: _FakeAnswer_with(
        payload if payload is not None else _ANSWER_with)
    buffer = _io_mit.StringIO()
    try:
        with _ctx_mit.redirect_stdout(buffer):
            res = _lv.analyze_image(img=_IMAGE_with, provider="lmstudio",
                                    model="testmodell", prompt="Wer ist das?")
    finally:
        _lv.urllib.request.urlopen = _real_open
        _CFG_mit.llm_debug = _old_debug
    return res, buffer.getvalue()


_has_pil_with = False
try:
    from PIL import Image as _PIL_mit
    _IMAGE_with = _PIL_mit.new("RGB", (4, 4), (10, 20, 30))
    _has_pil_with = True
except ImportError:
    _IMAGE_with = None

if not _has_pil_with:
    print("  ----  uebersprungen (Pillow nicht installiert)")
else:
    _res_off, _text_off = _run_with(False)
    check("ohne den Schalter aendert sich am Ergebnis nichts",
          _res_off[0] is True and _res_off[1] == "Kraken")
    check("und die Konsole bleibt still", _text_off == "")

    _res_on, _text_on = _run_with(True)
    check("mit Schalter bleibt das Ergebnis dasselbe",
          _res_on[0] is True and _res_on[1] == "Kraken")
    check("die Mitschrift nennt Modell und Prompt",
          "testmodell" in _text_on and "Wer ist das?" in _text_on)
    check("und die rohe Antwort steht da", '"content": "Kraken"' in _text_on)
    # Der Punkt der ganzen Mitschrift: das Denk-Feld, das der Code verwirft.
    check("samt dem Denk-Feld, das der Code selbst verwirft",
          "reasoning_content" in _text_on
          and "Tintenfisch" in _text_on)
    check("und daneben, was daraus gelesen wurde", "gelesen:" in _text_on)

    # Eine leere Antwort ist der haeufigste Fall — und der, bei dem man ohne
    # Hinweis die Ursache raet.
    _res_empty, _text_empty = _run_with(True, {"choices": [{"message": {"content": ""}}]})
    check("bei leerer Antwort nennt die Mitschrift die moeglichen Ursachen",
          "leer" in _text_empty and "Bild-F" in _text_empty)

    # Auch ein Fehlschlag wird mitgeschrieben — sonst fehlt in der Mitschrift
    # ausgerechnet der Aufruf, der nicht funktioniert hat.
    def _throw_with(*a, **kw):
        raise _lv.urllib.error.URLError("kein Server")

    _real_open_with = _lv.urllib.request.urlopen
    _old_debug_with = _CFG_mit.llm_debug
    _CFG_mit.llm_debug = True
    _lv.urllib.request.urlopen = _throw_with
    _buffer_with = _io_mit.StringIO()
    try:
        with _ctx_mit.redirect_stdout(_buffer_with):
            _res_miss = _lv.analyze_image(img=_IMAGE_with, provider="lmstudio",
                                          model="testmodell")
    finally:
        _lv.urllib.request.urlopen = _real_open_with
        _CFG_mit.llm_debug = _old_debug_with
    check("ein Fehlschlag steht ebenfalls in der Mitschrift",
          _res_miss[0] is False and "kein Server" in _buffer_with.getvalue())


# =============================================================================
section("Katalog holen: aus dem Fenster statt von der Kommandozeile")
# =============================================================================
# **Ausgerechnet die Datei, ohne die das LLM frei raet und die Kategorie leer
# bleibt, liess sich im Studio nicht beschaffen** — der Einstellungen-Reiter
# zeigte den Pfad und verwies auf `python tools/catalog.py`. Gerechnet wird
# weiterhin dort; die Bruecke RUFT das Werkzeug, nie umgekehrt.
import shutil as _sh_kh                                            # noqa: E402
import sys as _sys_kh                                              # noqa: E402
import tempfile as _tmp_kh                                         # noqa: E402
from pathlib import Path as _P_kh                                  # noqa: E402

from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB_kh  # noqa: E402
from autoclicker.models import Sequence as _SEQ_kh                 # noqa: E402

_root_kh = _P_kh(__file__).resolve().parents[2]
if str(_root_kh) not in _sys_kh.path:
    _sys_kh.path.insert(0, str(_root_kh))
import tools.catalog as _tk_kh                                     # noqa: E402

_GAME_DATA_kh = {"Items": {"Items": [
    {"Name": "godlike_bow", "EquipmentSlot": 7, "BaseValue": 900},
    {"Name": "citadel_helmet", "EquipmentSlot": 11, "BaseValue": 500},
]}, "Raids": [{"BossNameLocalizationKey": "kraken"}]}

_sandbox_kh = _tmp_kh.mkdtemp(prefix="katalogholen_")
_cwd_kh = _os.getcwd()
_real_fetch_kh = _tk_kh.fetch_game_data
_old_path_kh = _CFG_mit.scan_catalog_file
_os.chdir(_sandbox_kh)
try:
    def _build_kh():
        _P_kh("sequences").mkdir(exist_ok=True)
        return _SB_kh(_SEQ_kh(name="S"), _P_kh("sequences/s/sequence.json"), "sequences")

    _CFG_mit.scan_catalog_file = ""
    _tk_kh.fetch_game_data = lambda *a, **kw: _GAME_DATA_kh
    _res_kh = _build_kh().catalog_fetch()
    check("der Knopf holt und schreibt die Datei",
          _res_kh["ok"] and _P_kh("catalog.json").exists())
    _content_kh = _json_mit.loads(_P_kh("catalog.json").read_text(encoding="utf-8"))
    check("mit den echten Namen aus der API",
          "Godlike Bow" in _content_kh["items"]
          and _content_kh["items"]["Godlike Bow"]["kategorie"] == "Bow")
    # Ohne diesen Schritt hat man die Datei und trotzdem keine Wirkung — der
    # Scan liest den Pfad, nicht den Ordner.
    check("und traegt den Pfad gleich in die Config ein",
          _CFG_mit.scan_catalog_file.endswith("catalog.json"))
    check("die Meldung nennt, was drin ist", "2 Items" in _res_kh["message"])

    # Ein selbst gesetzter Pfad wird AKTUALISIERT, nicht ueberschrieben: wer
    # zwei Spiele betreibt, hat den Katalog bewusst woanders liegen.
    _CFG_mit.scan_catalog_file = "eigener/pfad.json"
    _res2_kh = _build_kh().catalog_fetch()
    check("ein eigener Pfad bleibt stehen",
          _res2_kh["ok"] and _CFG_mit.scan_catalog_file == "eigener/pfad.json"
          and _P_kh("eigener/pfad.json").exists())

    # Kein Netz ist der haeufigste Fehlerfall — und darf die vorhandene Datei
    # nicht zerstoeren. Dieselbe Haltung wie beim Start-Durchgang: lieber
    # nichts tun als halb schreiben.
    _before_kh = _P_kh("catalog.json").read_text(encoding="utf-8")

    def _throw_kh(*a, **kw):
        raise OSError("kein Netz")

    _tk_kh.fetch_game_data = _throw_kh
    _CFG_mit.scan_catalog_file = str(_P_kh("catalog.json"))
    _res3_kh = _build_kh().catalog_fetch()
    check("ohne Netz wird nichts geschrieben",
          _res3_kh["ok"] is False and "kein Netz" in _res3_kh["message"]
          and _P_kh("catalog.json").read_text(encoding="utf-8") == _before_kh)

    # Eine Antwort ohne Items ist kein Katalog — eine leere Datei zu schreiben
    # hiesse, die brauchbare gegen eine unbrauchbare zu tauschen.
    _tk_kh.fetch_game_data = lambda *a, **kw: {"Items": {"Items": []}}
    _res4_kh = _build_kh().catalog_fetch()
    check("und eine leere Antwort ueberschreibt die gute Datei nicht",
          _res4_kh["ok"] is False
          and _P_kh("catalog.json").read_text(encoding="utf-8") == _before_kh)

    # --- Ein Spiel-Update darf den Knopf nicht stoppen ---------------------
    # Die API schreibt Mongo-Shell-JSON, und der Bereiniger kannte genau EIN
    # Konstrukt: als `NumberLong(0)` in den Achievements auftauchte, starb der
    # Knopf an einem Feld, das er nie liest. Bekanntes wird uebersetzt,
    # Unbekanntes uebernommen und GEMELDET — dieselben Faelle wie beim
    # Zwilling `market_analysis/extended_json.py`, damit die beiden Kopien
    # nicht auseinanderlaufen.
    _raw_kh = ('{"_id": ObjectId("61e2b1b0"), "n": NumberLong(0), "m": NumberLong("42"),'
               ' "d": NumberDecimal("1.5"), "t": "nutze ObjectId(\\"x\\") hier",'
               ' "u": NumberFoo(3), "w": Timestamp(1, 2), "leer": ISODate()}')
    _json_kh, _unk_kh = _tk_kh.clean_extended_json(_raw_kh)
    _data_kh = _json_mit.loads(_json_kh)
    check("ObjectId wird Text, NumberLong Zahl — mit und ohne Anfuehrungszeichen",
          _data_kh["_id"] == "61e2b1b0" and _data_kh["n"] == 0
          and _data_kh["m"] == 42 and _data_kh["d"] == 1.5)
    check("ein Konstrukt IN einem String bleibt, was es ist",
          _data_kh["t"] == 'nutze ObjectId("x") hier')
    check("ein unbekanntes mit einem Skalar wird der Skalar", _data_kh["u"] == 3)
    check("eines mit mehreren Argumenten wird Text statt Abbruch",
          _data_kh["w"] == "Timestamp(1, 2)" and _data_kh["leer"] is None)
    check("und nur das Unbekannte wird gemeldet",
          _unk_kh == {"NumberFoo": 1, "Timestamp": 1})

    # Der Knopf reicht die Meldung in die Statuszeile — auf stderr saehe sie
    # im Studio niemand — und schreibt die Datei trotzdem.
    def _with_hint_kh(*a, hints=None, **kw):
        if hints is not None:
            hints.extend(_tk_kh.extended_json_hints({"NumberFoo": 3}))
        return _GAME_DATA_kh

    _tk_kh.fetch_game_data = _with_hint_kh
    _res5_kh = _build_kh().catalog_fetch()
    check("der Knopf schreibt trotzdem und sagt, was fremd war",
          _res5_kh["ok"] and _res5_kh.get("kind") == "warn"
          and "NumberFoo" in _res5_kh["message"] and "2 Items" in _res5_kh["message"])

    # --- Ein Zaehler am Namen darf die Kategorie nicht kosten ---------------
    # **"Godlike Bow 2" steht nicht im Katalog**, sein Gegenstand aber schon.
    # An einem echten Bestand standen so acht Items ohne Kategorie neben ihrem
    # eingeordneten Zwilling — und ohne Kategorie konkurriert ein Item mit
    # niemandem, wird also in Modus `all` immer geklickt.
    from autoclicker.utils import without_counter as _oz_kh
    check("der Zaehler faellt weg", _oz_kh("Godlike Bow 2") == "Godlike Bow")
    # Eine Zahl, die zum Namen gehoert, bleibt — der Aufrufer probiert ohnehin
    # ERST den vollen Namen.
    check("aber nur der angehaengte", _oz_kh("Bogen") == "Bogen"
          and _oz_kh("Iron Helmet 12") == "Iron Helmet")

    from autoclicker.catalog import Catalog as _Kat_kh
    _cat_kh = _Kat_kh({"Godlike Bow": {"kategorie": "Bow", "wert": 9},
                       "Slot 1": {"kategorie": "Sonder", "wert": 1}})
    check("ein Item mit Zaehler findet seinen Katalog-Eintrag",
          _SB_kh._catalog_name("Godlike Bow 2", _cat_kh) == "Godlike Bow")
    # Was im Katalog steht, gewinnt: "Slot 1" ist dort ein eigener Eintrag und
    # wird nicht auf "Slot" zurechtgestutzt.
    check("und ein echter Name mit Zahl bleibt, wie er ist",
          _SB_kh._catalog_name("Slot 1", _cat_kh) == "Slot 1")
    check("Unbekanntes bleibt unbekannt",
          _SB_kh._catalog_name("Irgendwas 2", _cat_kh) == "")

    # --- Wie alt ist die Liste? ---------------------------------------------
    # **Der Pfad allein beantwortet die Frage nicht**, die man an eine geholte
    # Liste hat: liegt die Datei ueberhaupt da, und von wann ist sie? Ohne
    # Antwort holt man sie entweder nie wieder oder bei jedem Zweifel neu.
    check("ein fehlender Katalog sagt genau das",
          "fehlt" in _SB_kh._catalog_state("gibtsnicht.json"))
    _P_kh("kaputt.json").write_text("{nope", encoding="utf-8")
    check("und eine kaputte Datei auch",
          "nicht lesbar" in _SB_kh._catalog_state("kaputt.json"))
    check("ohne Pfad steht gar nichts da", _SB_kh._catalog_state("") == "")
    _P_kh("stempel.json").write_text(_json_mit.dumps({
        "_erzeugt": "2026-09-07T16:42:11Z",
        "items": {"a": {}, "b": {}}, "gegner": ["x"]}), encoding="utf-8")
    _stamp_kh = _SB_kh._catalog_state("stempel.json")
    check("und sonst Umfang und Zeitpunkt",
          "2 Items" in _stamp_kh and "1 Gegner" in _stamp_kh
          and "07.09.2026" in _stamp_kh)
    # **In Ortszeit, nicht in UTC.** Ein Zeitstempel, den man mit der eigenen
    # Uhr vergleichen soll, darf nicht in einer anderen Zone stehen — 16:42Z
    # ist hier 18:42, und im Winter 17:42.
    from datetime import datetime as _dt_kh, timezone as _tz_kh
    _local_kh = _dt_kh(2026, 9, 7, 16, 42, 11, tzinfo=_tz_kh.utc).astimezone()
    check("in Ortszeit", _local_kh.strftime("um %H:%M") in _stamp_kh)

    # Der Weg bis in die Ansicht: `config_read()` liefert ihn, und die Seite
    # zeichnet ihn unter dem Feld.
    _CFG_mit.scan_catalog_file = "stempel.json"
    _states_kh = _build_kh().config_read()["states"]
    check("die Einstellungen liefern den Stand mit",
          "2 Items" in _states_kh.get("scan_catalog_file", ""))
    check("und die Ansicht zeichnet ihn",
          "C.states" in _studio_web_kh())
finally:
    _tk_kh.fetch_game_data = _real_fetch_kh
    _CFG_mit.scan_catalog_file = _old_path_kh
    _os.chdir(_cwd_kh)
    _sh_kh.rmtree(_sandbox_kh, ignore_errors=True)


# =============================================================================
section("LLM: Kaltstart, Modellpruefung und die Config-Felder")
# =============================================================================
# Vier Befunde aus einer Durchsicht des LLM-Pfades — jeder eine Stelle, an der
# etwas STILL nicht passierte: der Worker gab bei einer Zeitueberschreitung auf,
# die Lampe pruefte einen Endpunkt, den es im Normalfall gar nicht gibt, sie
# sah nie nach, ob das eingestellte Modell geladen ist, und zwei Config-Felder
# galten nur fuer den Boss-Scan.
import autoclicker.runtime.boss_detection as _bd_llm                # noqa: E402
from autoclicker.llm_vision import (                                # noqa: E402
    _model_known as _bekannt_llm, _name_tokens as _tokens_llm,
    is_timeout as _ist_to_llm,
)
from autoclicker.models import (                                    # noqa: E402
    AutoClickerState as _ST_llm, BossProfile as _BP_llm,
    BossScanConfig as _BSC_llm,
)

# --- Die Regel, an der alles haengt -----------------------------------------
check("ein Timeout wird als solcher erkannt", _ist_to_llm("Timeout nach 60s"))
# Ein Verbindungsfehler ist KEIN Timeout: da ist niemand, und Wiederholen waere
# nur Warten.
check("ein Verbindungsfehler nicht",
      not _ist_to_llm("Verbindungsfehler: [Errno 111]")
      and not _ist_to_llm("") and not _ist_to_llm(None))

# --- Der Worker gibt bei einem kalten Modell nicht mehr auf ------------------
_state_llm = _ST_llm()
_state_llm.config.llm_enabled = True
_state_llm.config.llm_timeout = 30
_state_llm.config.llm_retry_count = 0        # KEIN Wiederholungs-Budget
_cfg_llm = _BSC_llm(name="B", scan_region=(0, 0, 10, 10))
_bosses_llm = [_BP_llm(name="Kraken")]

_attempts_llm = []


def _answer_llm(**kw):
    """Erst ein Timeout, dann die Antwort — der gemessene Kaltstart."""
    _attempts_llm.append(kw.get("timeout"))
    if len(_attempts_llm) == 1:
        return False, "Timeout nach 30s", 30000.0
    return True, "Kraken", 3500.0


import autoclicker.llm_vision as _lv_llm                            # noqa: E402
_real_analyze_llm = _lv_llm.analyze_image
try:
    _lv_llm.analyze_image = _answer_llm
    _hits_llm = _bd_llm._execute_llm_boss_detection(
        _state_llm, _cfg_llm, object(), False, _bosses_llm)
    # **Hier stand `break`.** Ausgerechnet der ERSTE Boss-Scan eines Laufs
    # trifft ein kaltes Modell — und fiel damit aus, waehrend `llm_retry_count`
    # daneben stand und nur bei „kein Boss erkannt" wiederholte.
    check("eine Zeitueberschreitung beendet die Erkennung nicht mehr",
          len(_attempts_llm) == 2)
    check("und der zweite Versuch bekommt mehr Zeit",
          _attempts_llm[1] > _attempts_llm[0])
    check("danach wird der Boss erkannt",
          _hits_llm is not None and _hits_llm.name == "Kraken")

    # Ein Verbindungsfehler wiederholt NICHT: da antwortet niemand, und ein
    # zweiter Aufruf kostet nur die Wartezeit noch einmal.
    _attempts_llm.clear()
    _lv_llm.analyze_image = lambda **kw: (
        _attempts_llm.append(kw.get("timeout")) or (False, "Verbindungsfehler: tot", 5.0))
    _bd_llm._execute_llm_boss_detection(
        _state_llm, _cfg_llm, object(), False, _bosses_llm)
    check("ein Verbindungsfehler wird nicht wiederholt", len(_attempts_llm) == 1)
finally:
    _lv_llm.analyze_image = _real_analyze_llm

# --- Die Lampe sagt, ob das MODELL da ist -----------------------------------
check("ein geladenes Modell wird gefunden",
      _bekannt_llm("google/gemma-4-12b-qat", ["a", "google/gemma-4-12b-qat"]))
check("ein fehlendes nicht", not _bekannt_llm("gibts/nicht", ["a", "b"]))
# Ollama haengt ein Tag an: wer den Stamm eintraegt, meint dasselbe Modell.
check("der Stamm eines Ollama-Namens zaehlt", _bekannt_llm("gemma3n", ["gemma3n:e4b"]))
# Aber nur in diese Richtung — zwei Tags sind zwei Modelle.
check("zwei Tags sind aber zwei Modelle",
      not _bekannt_llm("gemma3n:e4b", ["gemma3n:e2b"]))
check("ohne eingestelltes Modell wird nichts behauptet", _bekannt_llm("", ["x"]))

# --- Die Token-Grenze der Benennung -----------------------------------------
# Mit Liste reichen 32 (ein Katalogname ist kurz), mit Reasoning NIE kuerzen:
# das Modell verbraucht sie erst fuers Denken, und `content` bliebe leer.
check("mit Liste genuegen 32 Tokens", _tokens_llm(0, False, True) == 32)
check("mit Reasoning wird nicht gekuerzt", _tokens_llm(0, True, True) == 0)
check("ein gesetzter Wert gewinnt immer", _tokens_llm(777, True, True) == 777)
check("ohne Liste gilt der Automatik-Wert", _tokens_llm(0, False, False) == 0)

# --- …und die Benennung reicht die Felder ueberhaupt durch -------------------
# `llm_reasoning` und `llm_max_tokens` galten nur fuer den Boss-Scan: wer sie
# einschaltete, weil die BENENNUNG besser werden soll, aenderte nichts.
_source_llm = (_P_kh(__file__).resolve().parents[2]
               / "autoclicker" / "editors" / "sequence_studio"
               / "scan_learning.py").read_text(encoding="utf-8")
check("der Durchgang gibt Reasoning und Token-Grenze mit",
      "reasoning=config.llm_reasoning" in _source_llm
      and "max_tokens=config.llm_max_tokens" in _source_llm)
_console_llm = (_P_kh(__file__).resolve().parents[2] / "autoclicker" / "editors"
                / "item_editor" / "commands.py").read_text(encoding="utf-8")
check("und der Konsolen-Weg ebenso",
      "reasoning=state.config.llm_reasoning" in _console_llm)
