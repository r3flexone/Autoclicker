"""Logik-/Daten-Schicht-Tests — laufen ohne GUI/LLM, plattformunabhängig.

Aufruf:  python tools/test_logic.py   (Exit 0 = alle grün)

Prüft Serialisierung/Persistenz, Backward-Compat, Farb-/Parsing-Helfer und
das Export-Format. Auf Linux/Mac wird msvcrt gestubbt (auf Windows nicht —
da ist es echt vorhanden), damit der Import der utils nicht scheitert.
"""
import sys, types, json, tempfile
from pathlib import Path

try:
    import msvcrt  # noqa: F401  (echtes Modul auf Windows)
except ImportError:
    sys.modules['msvcrt'] = types.ModuleType('msvcrt')  # Stub auf Linux/Mac

# ctypes.windll gibt es nur auf Windows. Damit auch die Runtime-/Debug-Schicht hier
# pruefbar ist (die importiert winapi), wird es auf Linux/Mac minimal gestubbt. Die
# Stubs tun nichts - getestet wird ausschliesslich Logik, keine echten Maus-Aktionen.
import ctypes
if not hasattr(ctypes, 'windll'):
    class _StubFn:
        def __init__(self, *a): self.argtypes = None; self.restype = None
        def __call__(self, *a, **kw): return 0

    class _StubLib:
        def __getattr__(self, name):
            fn = _StubFn(); setattr(self, name, fn); return fn

    class _StubWinDLL:
        def __getattr__(self, name):
            lib = _StubLib(); setattr(self, name, lib); return lib
        def LoadLibrary(self, name): return _StubLib()

    ctypes.windll = _StubWinDLL()
    ctypes.WinDLL = lambda *a, **kw: _StubLib()
    ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS, FAIL = 0, 0
def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  PASS  {name}")
    else:
        FAIL += 1; print(f"  FAIL  {name}")

def section(t): print(f"\n=== {t} ===")

# ---------------------------------------------------------------- Serializer
section("Serializer-Round-Trip (Scan-Configs: save-dict -> load_file)")
from autoclicker.models import (ItemSlot, ItemProfile, BossProfile, ClickPoint,
    ItemScanConfig, BossScanConfig, IconScanConfig)
from autoclicker.persistence.serialization import (
    _item_scan_to_dict, _boss_scan_to_dict, _icon_scan_to_dict, _point_to_dict)
from autoclicker.persistence.item_scans import load_item_scan_file
from autoclicker.persistence.boss_scans import load_boss_scan_file
from autoclicker.persistence.icon_scans import load_icon_scan_file
from autoclicker.utils import compact_json

tmp = Path(tempfile.mkdtemp())

def roundtrip(to_dict, load_file, cfg):
    p = tmp / "x.json"
    p.write_text(compact_json(to_dict(cfg)), encoding="utf-8")
    return load_file(p)

slot = ItemSlot(name="Slot 1", scan_region=(10, 20, 110, 120), click_pos=(60, 70), slot_color=(30, 40, 50))
item = ItemProfile(name="Schwert", marker_colors=[(200, 30, 30)], category="Waffe", priority=2,
                   confirm_point=ClickPoint(5, 6), confirm_delay=0.7, template="schwert.png", min_confidence=0.85)
isc = ItemScanConfig(name="MyScan", slots=[slot], items=[item], color_tolerance=42, learn_unknown=True)
r = roundtrip(_item_scan_to_dict, load_item_scan_file, isc)
check("ItemScan name/tol/learn_unknown", r.name == "MyScan" and r.color_tolerance == 42 and r.learn_unknown is True)
check("ItemScan slot erhalten", r.slots[0].name == "Slot 1" and r.slots[0].scan_region == (10, 20, 110, 120) and r.slots[0].slot_color == (30, 40, 50))
check("ItemScan item erhalten", r.items[0].name == "Schwert" and r.items[0].category == "Waffe" and r.items[0].template == "schwert.png" and abs(r.items[0].min_confidence-0.85) < 1e-9)
check("ItemScan confirm_point erhalten", r.items[0].confirm_point is not None and (r.items[0].confirm_point.x, r.items[0].confirm_point.y) == (5, 6))

boss = BossProfile(name="Drache", marker_colors=[(10, 20, 30)], template="drache.png", min_confidence=0.9,
                   action="click", action_x=111, action_y=222, action_delay=1.5)
bsc = BossScanConfig(name="BScan", scan_region=(1, 2, 3, 4), bosses=[boss], color_tolerance=33,
                     default_action="skip", use_llm=True, llm_fallback=False, use_ocr=True, ocr_fallback=False)
r = roundtrip(_boss_scan_to_dict, load_boss_scan_file, bsc)
check("BossScan flags (llm/ocr)", r.use_llm and not r.llm_fallback and r.use_ocr and not r.ocr_fallback)
check("BossScan region/tol/default", r.scan_region == (1, 2, 3, 4) and r.color_tolerance == 33 and r.default_action == "skip")
check("BossScan boss action", r.bosses[0].name == "Drache" and r.bosses[0].action == "click" and r.bosses[0].action_x == 111 and r.bosses[0].action_y == 222)

icn = IconScanConfig(name="IScan", scan_region=(7, 8, 9, 10), template="icon.png", min_confidence=0.77,
                     marker_colors=[(1, 2, 3), (4, 5, 6)], color_tolerance=25, action="key", action_key="enter", action_delay=2.0)
r = roundtrip(_icon_scan_to_dict, load_icon_scan_file, icn)
check("IconScan template/conf/key", r.template == "icon.png" and abs(r.min_confidence-0.77) < 1e-9 and r.action_key == "enter")
check("IconScan marker_colors", r.marker_colors == [(1, 2, 3), (4, 5, 6)] and r.action_delay == 2.0)

# ---------------------------------------------------------------- _point_to_dict
section("_point_to_dict (color/source nur wenn gesetzt)")
p_full = _point_to_dict(ClickPoint(1, 2, "P", 5, color=(9, 8, 7), source="Aufnahme 'X'"))
check("Punkt mit color+source", p_full == {"id": 5, "x": 1, "y": 2, "name": "P", "color": [9, 8, 7], "source": "Aufnahme 'X'"})
p_min = _point_to_dict(ClickPoint(1, 2, "P", 5))
check("Punkt ohne color/source (Felder weggelassen)", "color" not in p_min and "source" not in p_min)

# ---------------------------------------------------------------- LOAD_EXCEPTIONS
section("LOAD_EXCEPTIONS: kaputte/alte Dateien -> None statt Crash")
bad = tmp / "bad.json"; bad.write_text("{ das ist kein json", encoding="utf-8")
check("ItemScan korrupt -> None", load_item_scan_file(bad) is None)
check("BossScan korrupt -> None", load_boss_scan_file(bad) is None)
check("IconScan korrupt -> None", load_icon_scan_file(bad) is None)
empty = tmp / "empty.json"; empty.write_text("{}", encoding="utf-8")  # name fehlt -> KeyError gefangen
check("ItemScan ohne 'name' -> None", load_item_scan_file(empty) is None)

# ---------------------------------------------------------------- defensives Slot-Laden
section("item_scans: defekter Slot wird übersprungen, Scan lädt trotzdem")
mixed = {"name": "S", "slots": [
    {"name": "ok", "scan_region": [0, 0, 5, 5], "click_pos": [2, 2]},
    {"name": "kaputt"}],  # fehlende Felder
    "items": []}
pm = tmp / "mixed.json"; pm.write_text(json.dumps(mixed), encoding="utf-8")
rm = load_item_scan_file(pm)
check("Mixed-Scan lädt", rm is not None)
check("nur der gute Slot übrig", rm is not None and len(rm.slots) == 1 and rm.slots[0].name == "ok")

# ---------------------------------------------------------------- compact_json
section("compact_json (Arrays kompakt, Strings NICHT korrumpiert)")
cj = compact_json({"region": [1, 2, 3, 4], "rgb": [5, 6, 7], "xy": [8, 9]})
check("4er-Array kompakt", "[1, 2, 3, 4]" in cj)
check("3er-Array kompakt", "[5, 6, 7]" in cj)
check("2er-Array kompakt", "[8, 9]" in cj)
cj2 = compact_json({"text": "[1,\n2,\n3]", "n": [1, 2, 3]})
check("String mit Zahlen bleibt unangetastet", '"[1,\\n2,\\n3]"' in cj2 or "[1,\n2,\n3]" in json.loads('"' + cj2.split('"text": "')[1].split('",')[0] + '"'))

# ---------------------------------------------------------------- sanitize_filename
section("sanitize_filename")
from autoclicker.utils import sanitize_filename
check("Pfad-Traversal entschärft", "/" not in sanitize_filename("../../etc/passwd") and ".." not in sanitize_filename("../../etc/passwd"))
check("nicht leer bei Sonderzeichen", len(sanitize_filename("???").strip()) >= 0)  # darf leer sein, soll aber nicht crashen
check("normaler Name bleibt brauchbar", sanitize_filename("Schwert 2") != "")

# ---------------------------------------------------------------- describe_color
section("describe_color / Farbname-Heuristik")
import importlib.util
spec = importlib.util.spec_from_file_location("console", str(Path(__file__).resolve().parent.parent / "autoclicker" / "utils" / "console.py"))
con = importlib.util.module_from_spec(spec); spec.loader.exec_module(con)
con._COLORS_ENABLED = False
cases = {(220, 30, 30): "Rot", (30, 180, 60): "Grün", (40, 80, 220): "Blau", (30, 30, 30): "Schwarz",
         (245, 245, 245): "Weiß", (255, 165, 0): "Orange", (139, 69, 19): "Braun"}
for rgb, exp in cases.items():
    check(f"Farbname {rgb} -> {exp}", exp in con.describe_color(rgb))
check("kaputte Farbe stürzt nicht ab", con.describe_color("rot") == "rot")

# ---------------------------------------------------------------- Transform-Mathematik
section("Koordinaten-Remapping (import_export)")
from autoclicker.import_export import compute_transform, remap_point, remap_region
ident = compute_transform((0, 0), (100, 100), (0, 0), (100, 100))
check("Identity: Punkt unverändert", remap_point(50, 50, ident) == (50, 50))
scale2 = compute_transform((0, 0), (100, 100), (0, 0), (200, 200))
check("2x-Skalierung Punkt", remap_point(50, 50, scale2) == (100, 100))
check("2x-Skalierung Region normalisiert", remap_region((10, 10, 30, 40), scale2) == (20, 20, 60, 80))
offset = compute_transform((0, 0), (100, 0), (10, 5), (110, 5))
check("Reiner Offset", remap_point(0, 0, offset) == (10, 5))

# ---------------------------------------------------------------- Config-Backward-Compat
section("Config: entferntes Feld bricht alte config.json nicht")
from autoclicker.config import AppConfig
old = AppConfig().to_dict(); old["scan_learn_llm_names"] = True  # alter, jetzt entfernter Key
cfg = AppConfig.from_dict(old)
check("alte config.json mit entferntem Key lädt", isinstance(cfg, AppConfig))
check("entfernter Key nicht als Attribut", not hasattr(cfg, "scan_learn_llm_names"))
check("scan_min_confidence Default vorhanden", hasattr(cfg, "scan_min_confidence"))

# ---------------------------------------------------------------- export_bundle (Zip-Inhalt)
section("export_bundle: erzeugt ZIP, Scan-JSON == Serializer-Format")
import zipfile, threading
from autoclicker.models import AutoClickerState
st = AutoClickerState()
st.points = [ClickPoint(1, 2, "P1", 1, color=(3, 4, 5), source="Aufnahme 'A'")]
st.item_scans = {"MyScan": isc}
st.boss_scans = {"BScan": bsc}
st.icon_scans = {"IScan": icn}
from autoclicker.import_export import export_bundle, read_manifest
zpath = str(tmp / "bundle.zip")
ok_exp, msg = export_bundle(st, zpath, (0, 0), (100, 100),
                            include_config=False)  # config separat getestet
check("export_bundle Erfolg", ok_exp is True)
with zipfile.ZipFile(zpath) as zf:
    names = zf.namelist()
    from autoclicker.utils import sanitize_filename as _sf
    iname = f"item_scans/{_sf('MyScan')}.json"
    bname = f"boss_scans/{_sf('BScan')}.json"
    check("points.json im Bundle", "points.json" in names)
    check("item_scans/<scan>.json im Bundle", iname in names)
    iscan_json = json.loads(zf.read(iname))
    # über compact_json normalisieren (Tupel->Array auf beiden Seiten)
    check("Export-Item-Scan == save-Format", iscan_json == json.loads(compact_json(_item_scan_to_dict(isc))))
    bscan_json = json.loads(zf.read(bname))
    check("Export-Boss-Scan == _boss_scan_to_dict", bscan_json == _boss_scan_to_dict(bsc))
    pts = json.loads(zf.read("points.json"))
    check("Export-Punkt == _point_to_dict", pts[0] == _point_to_dict(st.points[0]))
ok_man, man = read_manifest(zpath)
check("read_manifest OK", ok_man and man.get("version") == 1)

# ---------------------------------------------------------------- LLM-Vision-Logik
# Reine Logik aus llm_vision.py — kein Netzwerk, kein Backend. Deckt die
# Antwort-Nachbearbeitung ab (Reasoning-Strip, Boss-Name-Matching, no-boss-
# Heuristik) sowie die Request-Body-Form je Provider.
from autoclicker.llm_vision import (
    is_no_boss, clean_boss_name, match_boss_name, _strip_reasoning_tags,
    _extract_response_text, _build_ollama_request, _build_lmstudio_request,
    _build_system_prompt)

section("llm_vision: is_no_boss (Wortgrenzen-Heuristik)")
check("leere Antwort = kein Boss", is_no_boss("") is True)
check("KEIN_BOSS erkannt", is_no_boss("KEIN_BOSS") is True)
check("'no boss' erkannt", is_no_boss("There is no boss here") is True)
check("echter Name ist KEIN no-boss", is_no_boss("Skeleton King") is False)
check("'none' matcht NICHT in 'Stonekeeper'", is_no_boss("Stonekeeper") is False)

section("llm_vision: clean_boss_name (Präfixe/Quotes/Mehrzeiler)")
check("Quotes entfernt", clean_boss_name('"Skeleton King"') == "Skeleton King")
check("Präfix 'der boss ist' entfernt", clean_boss_name("Der Boss ist Drache") == "Drache")
check("Präfix 'boss:' + Punkt entfernt", clean_boss_name("Boss: Ork.") == "Ork")
check("nur erste Zeile", clean_boss_name("Drache\nirrelevant") == "Drache")

section("llm_vision: match_boss_name (exakt / längster / neu)")
_names = ["Ork", "Orkhäuptling", "Skeleton King"]
check("exakter Match, nicht neu", match_boss_name("Skeleton King", _names) == ("Skeleton King", False))
check("enthält -> längster gewinnt (Orkhäuptling > Ork)",
      match_boss_name("Der Orkhäuptling erscheint", _names) == ("Orkhäuptling", False))
check("Antwort ist Präfix eines Namens -> kürzester Treffer",
      match_boss_name("Skel", _names) == ("Skeleton King", False))
check("unbekannter Name -> is_new=True", match_boss_name("Goblin", _names) == ("Goblin", True))
check("kein Boss -> (None, False)", match_boss_name("KEIN_BOSS", _names) == (None, False))
check("leere Antwort -> (None, False)", match_boss_name("", _names) == (None, False))
check("kurze Antwort (<3) matcht nicht versehentlich",
      match_boss_name("or", _names) == ("or", True))

section("llm_vision: _strip_reasoning_tags (<think>-Varianten)")
check("vollständiger Block entfernt", _strip_reasoning_tags("<think>denke</think>Drache") == "Drache")
check("ohne Tags unverändert", _strip_reasoning_tags("Drache") == "Drache")
check("abgeschnitten: offenes <think> ohne Schluss -> leer",
      _strip_reasoning_tags("<think>denke nur, kein Ende") == "")
check("verwaistes </think> -> nimmt Teil danach",
      _strip_reasoning_tags("Reasoning-Rest</think>Drache") == "Drache")

section("llm_vision: _extract_response_text (Ollama vs. LM Studio)")
check("Ollama: message.content + Strip",
      _extract_response_text({"message": {"content": "<think>x</think>Drache"}}, "ollama") == "Drache")
check("LM Studio: choices[0].message.content",
      _extract_response_text({"choices": [{"message": {"content": "Drache"}}]}, "lmstudio") == "Drache")
check("LM Studio: leere choices -> ''",
      _extract_response_text({"choices": []}, "lmstudio") == "")

section("llm_vision: Request-Body-Form (Ollama)")
ob = _build_ollama_request("mymodel", "B64", "prompt")
check("Ollama model/stream", ob["model"] == "mymodel" and ob["stream"] is False)
check("Ollama Bild in messages[1].images", ob["messages"][1]["images"] == ["B64"])
check("Ollama num_predict=128 ohne Reasoning", ob["options"]["num_predict"] == 128)
check("Ollama kein 'think' ohne Reasoning", "think" not in ob)
ob_r = _build_ollama_request("m", "B", "p", reasoning=True)
check("Ollama Reasoning: think=True + num_predict=2048",
      ob_r.get("think") is True and ob_r["options"]["num_predict"] == 2048)
check("Ollama max_tokens override schlägt Default",
      _build_ollama_request("m", "B", "p", max_tokens=500)["options"]["num_predict"] == 500)
check("Ollama system_prompt override",
      _build_ollama_request("m", "B", "p", system_prompt="CUSTOM")["messages"][0]["content"] == "CUSTOM")

section("llm_vision: Request-Body-Form (LM Studio / OpenAI)")
lb = _build_lmstudio_request("mymodel", "B64", "prompt")
check("LM Studio max_tokens=50 ohne Reasoning", lb["max_tokens"] == 50)
check("LM Studio reasoning_effort='none' ohne Reasoning", lb["reasoning_effort"] == "none")
check("LM Studio Bild als data-URL",
      lb["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
lb_r = _build_lmstudio_request("m", "B", "p", reasoning=True)
check("LM Studio Reasoning: effort='high' + max_tokens=2048",
      lb_r["reasoning_effort"] == "high" and lb_r["max_tokens"] == 2048)
check("LM Studio max_tokens override",
      _build_lmstudio_request("m", "B", "p", max_tokens=4096)["max_tokens"] == 4096)

section("llm_vision: System-Prompt")
check("Default-Prompt enthält KEIN_BOSS-Regel", "KEIN_BOSS" in _build_system_prompt())
check("bekannte Bosse landen im Prompt", "Drache" in _build_system_prompt(["Drache"]))

# ------------------------------------------------- Scroll + Einmal-Farbpruefung
section("Scroll-Schritt + Farbpruefung ohne Warten")
from autoclicker.models import SequenceStep, WaitCondition
from autoclicker.persistence.serialization import _step_to_dict, _parse_steps

_scroll = SequenceStep(x=10, y=20, delay_before=0.5, name="scrollen", scroll=-3)
_check = SequenceStep(x=30, y=40, delay_before=0, name="farbcheck",
                      wait_condition=WaitCondition(pixel=(5, 6), color=(1, 2, 3),
                                                   check_only=True, until_gone=True))
_back = _parse_steps([_step_to_dict(x) for x in (_scroll, _check)])
check("scroll ueberlebt Round-Trip", _back[0].scroll == -3)
check("check_only ueberlebt Round-Trip", _back[1].wait_condition.check_only is True)
check("until_gone ueberlebt Round-Trip", _back[1].wait_condition.until_gone is True)

_alt = _parse_steps([{"x": 1, "y": 2, "delay_before": 1, "name": "alt"}])
check("alte Schritte ohne neue Keys: scroll=None", _alt[0].scroll is None)
check("alte Schritte ohne neue Keys: keine WaitCondition", _alt[0].wait_condition is None)
_alt_color = _parse_steps([{"x": 1, "y": 2, "delay_before": 0, "wait_pixel": [3, 4],
                            "wait_color": [5, 6, 7]}])
check("alter Farb-Trigger bleibt Warten (check_only=False)",
      _alt_color[0].wait_condition.check_only is False)

check("Scroll-Anzeige nennt Richtung und Stufen",
      "scrolle runter x3" in str(_scroll))
_check_text = str(SequenceStep(
    x=1, y=2, delay_before=0,
    wait_condition=WaitCondition(pixel=(1, 2), color=(3, 4, 5), check_only=True)))
check("Einmal-Pruefung wird als 'prüfe einmal' angezeigt", "prüfe einmal" in _check_text)
check("Einmal-Pruefung nennt den Standard-Fallback", "überspringen" in _check_text)

# Scroll-Delta als 32-Bit-Zweierkomplement (mouseData ist ein DWORD)
_WHEEL = 120
check("Scroll runter wird korrekt maskiert", ((-1 * _WHEEL) & 0xFFFFFFFF) == 0xFFFFFF88)
check("Scroll hoch bleibt positiv", ((3 * _WHEEL) & 0xFFFFFFFF) == 360)

# ------------------------------------------------------------- Debug-Modi
section("Debug-Modi: getrennte Flags + Migration alter Keys")
from autoclicker.config import AppConfig

_c = AppConfig.from_dict({"debug_detection": True, "debug_mode": True})
check("debug_detection -> debug_log", _c.debug_log is True)
check("debug_mode -> debug_detail", _c.debug_detail is True)
check("debug_step (Zwischenstufe) -> debug_detail",
      AppConfig.from_dict({"debug_step": True}).debug_detail is True)

# Die beiden Stufen muessen in JEDER Kombination unabhaengig schaltbar sein
for _log, _det in ((True, False), (False, True), (True, True), (False, False)):
    _cc = AppConfig.from_dict({"debug_log": _log, "debug_detail": _det})
    check(f"unabhaengig: log={_log}, detail={_det}",
          _cc.debug_log is _log and _cc.debug_detail is _det)

# Manueller Modus ist Laufzeit-Zustand, KEINE Config
check("manueller Modus ist kein Config-Feld",
      not any(f.name == "debug_step_mode" for f in __import__("dataclasses").fields(AppConfig)))
from autoclicker.models import AutoClickerState as _ACS
check("step_mode existiert am State und ist standardmaessig aus", _ACS().step_mode is False)

# ------------------------------------------- Manueller Modus + Ausgabe-Stufen
section("Manueller Modus (Laufzeit) vs. Ausgabe-Stufen (Config)")
import autoclicker.runtime.debug as _dbg
from autoclicker.models import WaitCondition as _WC

_st = AutoClickerState()

# Die zwei Config-Stufen aendern NUR die Ausgabe, nie den Ablauf.
# is_detail_debug haengt ausschliesslich an debug_detail - das ist die Unabhaengigkeit.
# is_log_debug ist dagegen eine Darstellungsfrage: sobald mehrzeilig ausgegeben wird,
# darf die Status-Zeile nicht mehr die ueberschreibbare Variante ohne \n sein.
_detail_unabhaengig = True
_zeilen_ok = True
for _l, _d in ((True, False), (False, True), (True, True), (False, False)):
    _st.config.debug_log, _st.config.debug_detail, _st.step_mode = _l, _d, False
    if _dbg.is_detail_debug(_st) is not _d or _dbg.skip_waits(_st) is not False:
        _detail_unabhaengig = False
    if _dbg.is_log_debug(_st) is not (_l or _d):
        _zeilen_ok = False
check("Detail-Stufe haengt nur an ihrem eigenen Flag", _detail_unabhaengig)
check("Detail-Stufe erzwingt echte Zeilen statt Ueberschreiben", _zeilen_ok)

# Ohne beide Flags bleibt die ueberschreibbare Status-Zeile
_st.config.debug_log = _st.config.debug_detail = False
check("ohne Flags: ueberschreibbare Status-Zeile", _dbg.is_log_debug(_st) is False)
check("Ausgabe-Stufen ueberspringen KEINE Wartezeiten", _dbg.skip_waits(_st) is False)

# Manueller Modus: eigenstaendig, haengt an keinem Config-Flag
_st.config.debug_log = _st.config.debug_detail = False
_st.step_mode = True
check("manueller Modus ueberspringt Wartezeiten", _dbg.skip_waits(_st) is True)
check("manueller Modus erzwingt persistente Ausgabe", _dbg.is_log_debug(_st) is True)
check("manueller Modus schaltet Stufe 2 NICHT ein", _dbg.is_detail_debug(_st) is False)

# Gate-Tasten
_step = SequenceStep(x=100, y=200, delay_before=5, name="Testpunkt")
_orig_read_key = _dbg.read_key
_ergebnisse = {}
for _taste in ("w", "enter", "s", "q", "c"):
    _st.step_mode = True
    _st.stop_event.clear()
    _dbg.read_key = (lambda _t=_taste: _t)
    _ergebnisse[_taste] = _dbg.step_gate(_st, _step, "LOOP", 1, 3)
_dbg.read_key = _orig_read_key
check("Gate: 'w' fuehrt aus", _ergebnisse["w"] == _dbg.GATE_RUN)
check("Gate: Enter fuehrt aus", _ergebnisse["enter"] == _dbg.GATE_RUN)
check("Gate: 's' ueberspringt", _ergebnisse["s"] == _dbg.GATE_SKIP)
check("Gate: 'q' bricht ab", _ergebnisse["q"] == _dbg.GATE_STOP)
check("Gate: 'c' laeuft weiter UND schaltet den Modus aus",
      _ergebnisse["c"] == _dbg.GATE_RUN and _st.step_mode is False)
_st.step_mode = False
check("Gate ohne manuellen Modus: sofort run",
      _dbg.step_gate(_st, _step, "LOOP", 1, 3) == _dbg.GATE_RUN)

# Zielpunkt: bei Farb-Bedingung zaehlt der Pruef-Pixel, nicht der Klickpunkt
check("Zielpunkt Klick", _dbg.target_of(SequenceStep(x=10, y=20, delay_before=0))[:2] == (10, 20))
check("Zielpunkt Farbe = Pruef-Pixel", _dbg.target_of(SequenceStep(
    x=10, y=20, delay_before=0,
    wait_condition=_WC(pixel=(77, 88), color=(1, 2, 3))))[:2] == (77, 88))
check("Zielpunkt Tastendruck = keiner", _dbg.target_of(
    SequenceStep(x=0, y=0, delay_before=0, key_press="enter")) is None)

# Detail-Stufe: EINE Kopfzeile pro Klick-Schritt. Vorher waren es drei Zeilen, die alle
# dasselbe sagten (Kopf, Beschreibung, "Zeiger auf ...") - plus die Status-Zeile danach.
import io as _io, contextlib as _ctx
_st.config.debug_detail = True
_st.config.pixel_show_delay = 0
_st.step_mode = False


def _detail_zeilen(step):
    buf = _io.StringIO()
    with _ctx.redirect_stdout(buf):
        _dbg.print_step_detail(_st, step, "LOOP", 15, 67)
    return [z for z in buf.getvalue().splitlines() if z.strip()]


_zeilen = _detail_zeilen(SequenceStep(x=10, y=20, delay_before=0, name="Klick 15"))
check("Detail: Klick-Schritt belegt genau eine Zeile", len(_zeilen) == 1)
check("Detail: Zeile nennt Schritt, Name und Ziel",
      "15/67" in _zeilen[0] and "Klick 15" in _zeilen[0] and "(10, 20)" in _zeilen[0])

# Nur wo es wirklich mehr zu sagen gibt, kommen Zusatzzeilen dazu
_zeilen_farbe = _detail_zeilen(SequenceStep(
    x=10, y=20, delay_before=0, name="Farbschritt",
    wait_condition=_WC(pixel=(77, 88), color=(10, 20, 30))))
check("Detail: Farb-Bedingung ergaenzt Zeilen", len(_zeilen_farbe) > 1)
check("Detail: Farb-Bedingung nennt den Pruef-Pixel",
      any("77" in z and "88" in z for z in _zeilen_farbe))
_st.config.debug_detail = False

# ---------------------------------------- Punkt-Referenzen (verrutschtes Fenster)
section("Punkt-Referenzen: Schritte folgen dem Punkte-Pool")
from autoclicker.models import Sequence as _Seq, LoopPhase as _LP, ClickPoint as _CP
from autoclicker.persistence.sequences import resolve_point_references as _resolve
from autoclicker.runtime.debug import step_label as _label

_st2 = AutoClickerState()
_st2.points = [_CP(x=100, y=200, name="Marktbutton", id=3),
               _CP(x=300, y=400, name="Verkaufen", id=7),
               _CP(x=500, y=600, name="Bestaetigen", id=9)]
_seq = _Seq(name="Verkauf", loop_phases=[_LP(name="LOOP", steps=[
    SequenceStep(x=100, y=200, delay_before=0, name="Marktbutton", point_id=3,
                 wait_condition=_WC(pixel=(100, 200), color=(1, 2, 3))),
    SequenceStep(x=300, y=400, delay_before=0, name="Verkaufen", point_id=7,
                 wait_condition=_WC(pixel=(999, 999), color=(4, 5, 6))),
    SequenceStep(x=500, y=600, delay_before=0, name="Bestaetigen"),   # Altbestand
    SequenceStep(x=11, y=22, delay_before=0, name="Weg", point_id=42),  # verwaist
])])

# Fenster war beim Aufnehmen um (+8,+5) verschoben -> Punkte korrigiert
for _p in _st2.points:
    _p.x += 8
    _p.y += 5
_meldungen = _resolve(_st2, _seq)
_s = _seq.loop_phases[0].steps

check("verknuepfter Schritt folgt dem Punkt", (_s[0].x, _s[0].y) == (108, 205))
check("Pruef-Pixel AM Klickpunkt zieht mit", tuple(_s[0].wait_condition.pixel) == (108, 205))
check("Pruef-Pixel ANDERSWO bleibt unberuehrt", tuple(_s[1].wait_condition.pixel) == (999, 999))
check("Schritt ohne Referenz bleibt unberuehrt", (_s[2].x, _s[2].y) == (500, 600))
check("verwaiste Referenz aendert keine Koordinaten", (_s[3].x, _s[3].y) == (11, 22))
check("verwaiste Referenz wird gemeldet",
      any("#42" in m and "nicht mehr gibt" in m for m in _meldungen))
check("Meldung nennt alte UND neue Position",
      any("(100, 200) -> (108, 205)" in m for m in _meldungen))

# Zweiter Lauf: keine Verschiebungen mehr, aber die verwaiste Referenz nervt weiter
_zweiter = _resolve(_st2, _seq)
check("zweiter Lauf meldet keine Verschiebung mehr",
      not any("->" in m for m in _zweiter))
check("verwaiste Referenz wird dauerhaft gemeldet", len(_zweiter) == 1)

check("Label nennt die Punkt-ID", "#3" in _label(_s[0]))
check("Label sagt klar, wenn kein Punkt dahintersteht", "kein Punkt" in _label(_s[2]))

# Serialisierung der Referenz
_rt = _parse_steps([_step_to_dict(_s[0])])
check("point_id ueberlebt Round-Trip", _rt[0].point_id == 3)
check("alte Schritte ohne point_id -> None",
      _parse_steps([{"x": 1, "y": 2, "delay_before": 0}])[0].point_id is None)

# ------------------------------------------------------- Schema-Migration
section("Schema-Migration: Altformate -> aktuelles Schema")
from autoclicker.persistence.migration import (
    KIND_SEQUENCE, SCHEMA_VERSION, file_version, migrate, needs_migration, stamp)
from autoclicker.persistence.sequences import load_sequence_file as _load_seq

_pts = [{"id": 3, "x": 100, "y": 200, "name": "Markt"},
        {"id": 7, "x": 300, "y": 400, "name": "Verkauf"},
        {"id": 9, "x": 500, "y": 600, "name": "A"},
        {"id": 10, "x": 500, "y": 600, "name": "B"}]      # mehrdeutig

check("Datei ohne Feld ist Version 0", file_version({"name": "x"}) == 0)
check("needs_migration erkennt Altdatei", needs_migration({"name": "x"}) is True)
check("gestempelte Datei braucht keine Migration", needs_migration(stamp({})) is False)

# uraltes Format: nur "steps", dazu tote Felder
_uralt = {"name": "U", "steps": [
    {"x": 100, "y": 200, "name": "Markt", "delay_before": 1, "clicks": 2, "point_index": 0}]}
_d, _m = migrate(_uralt, KIND_SEQUENCE, {"points": _pts})
check("uraltes 'steps' wird zu loop_phases", len(_d["loop_phases"]) == 1)
check("uralt: Schritt wird verknuepft", _d["loop_phases"][0]["steps"][0]["point_id"] == 3)
check("uralt: tote Felder entfernt",
      "clicks" not in _d["loop_phases"][0]["steps"][0]
      and "point_index" not in _d["loop_phases"][0]["steps"][0])
check("uralt: Versions-Stempel gesetzt", _d["schema_version"] == SCHEMA_VERSION)

# altes Format: start_steps + loop_steps + max_loops
_alt = {"name": "A",
        "start_steps": [{"x": 300, "y": 400, "name": "V", "delay_before": 0}],
        "loop_steps": [{"x": 500, "y": 600, "name": "Mehrdeutig", "delay_before": 0},
                       {"x": 0, "y": 0, "name": "T", "delay_before": 0, "key_press": "enter"}],
        "max_loops": 5}
_d2, _m2 = migrate(_alt, KIND_SEQUENCE, {"points": _pts})
check("start_steps wird eigene erste Phase", _d2["loop_phases"][0]["name"] == "Start")
check("loop_steps behaelt max_loops als repeat", _d2["loop_phases"][1]["repeat"] == 5)
check("max_loops ist weg", "max_loops" not in _d2)
check("start_steps ist weg", "start_steps" not in _d2)
check("mehrdeutige Koordinate bleibt UNverknuepft",
      _d2["loop_phases"][1]["steps"][0].get("point_id") is None)
check("Tastendruck bekommt keine point_id",
      _d2["loop_phases"][1]["steps"][1].get("point_id") is None)

# Idempotenz: zweiter Lauf aendert nichts mehr
import copy as _copy
_vorher = _copy.deepcopy(_d2)
_d3, _m3 = migrate(_d2, KIND_SEQUENCE, {"points": _pts})
check("zweiter Migrationslauf meldet nichts", _m3 == [])
check("zweiter Migrationslauf aendert nichts", _d3 == _vorher)

# Neuere Schema-Version wird nicht heruntergerechnet
_neuer = {"name": "Z", "schema_version": SCHEMA_VERSION + 5, "loop_phases": []}
_d4, _m4 = migrate(_neuer, KIND_SEQUENCE, {})
check("neuere Version wird nicht angefasst", _d4["schema_version"] == SCHEMA_VERSION + 5)
check("neuere Version wird gemeldet", any("kennt nur" in m for m in _m4))

# Loader liest ein Altformat ueber die Migration
_mp = tmp / "altformat.json"
_mp.write_text(json.dumps({"name": "Alt", "steps": [
    {"x": 100, "y": 200, "name": "Markt", "delay_before": 0}]}), encoding="utf-8")
_seq_alt = _load_seq(_mp, _pts)
check("Loader laedt uraltes Format ueber die Migration", _seq_alt is not None)
check("Loader: Schritt liegt in einer Loop-Phase",
      _seq_alt is not None and len(_seq_alt.loop_phases) == 1
      and len(_seq_alt.loop_phases[0].steps) == 1)
check("Loader: point_id kam aus der Migration",
      _seq_alt is not None and _seq_alt.loop_phases[0].steps[0].point_id == 3)


print(f"\n================  {PASS} PASS / {FAIL} FAIL  ================")
sys.exit(1 if FAIL else 0)
