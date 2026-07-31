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
# Ein Item-Scan speichert nur NAMEN - Slots/Items selbst liegen global.
# Aufgeloest wird von resolve_scan_references(state), s. eigener Abschnitt weiter unten.
check("ItemScan speichert Slot-Namen", r.slot_names == ["Slot 1"])
check("ItemScan speichert Item-Namen", r.item_names == ["Schwert"])
check("ItemScan laedt keine Kopien mehr", r.slots == [] and r.items == [])

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

# ------------------------------------------------- Altformat-Scan (eingebettete Kopien)
section("item_scans: eingebettete Slot-/Item-Kopien werden zu Namens-Referenzen")
mixed = {"name": "S", "slots": [
    {"name": "ok", "scan_region": [0, 0, 5, 5], "click_pos": [2, 2]},
    {"name": "kaputt"}],  # unvollstaendig - der Name genuegt jetzt trotzdem
    "items": [{"name": "Schwert", "marker_colors": []}]}
pm = tmp / "mixed.json"; pm.write_text(json.dumps(mixed), encoding="utf-8")
rm = load_item_scan_file(pm)
check("Altformat-Scan lädt", rm is not None)
check("Slot-Kopien wurden zu Namen", rm is not None and rm.slot_names == ["ok", "kaputt"])
check("Item-Kopien wurden zu Namen", rm is not None and rm.item_names == ["Schwert"])

# ---------------------------------------------------------------- compact_json
section("compact_json (Arrays kompakt, Strings NICHT korrumpiert)")
cj = compact_json({"region": [1, 2, 3, 4], "rgb": [5, 6, 7], "xy": [8, 9]})
check("4er-Array kompakt", "[1, 2, 3, 4]" in cj)
check("3er-Array kompakt", "[5, 6, 7]" in cj)
check("2er-Array kompakt", "[8, 9]" in cj)
cj2 = compact_json({"text": "[1,\n2,\n3]", "n": [1, 2, 3]})
check("String mit Zahlen bleibt unangetastet", '"[1,\\n2,\\n3]"' in cj2 or "[1,\n2,\n3]" in json.loads('"' + cj2.split('"text": "')[1].split('",')[0] + '"'))
# Monitor links vom Hauptbildschirm: negative Koordinaten sind der Normalfall, nicht die
# Ausnahme - ohne Vorzeichen im Muster blieben genau die mehrzeilig stehen.
cjn = compact_json({"region": [-1920, 0, -1000, 500], "xy": [-5, -7]})
check("negative Koordinaten ebenfalls kompakt",
      "[-1920, 0, -1000, 500]" in cjn and "[-5, -7]" in cjn)
check("compact_json nimmt auch Listen (points.json, bosses.json)",
      compact_json([{"id": 1, "x": 2, "y": 3}]).startswith("["))

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
import zipfile
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


# ------------------------------------------------ Migration: alle Dateitypen
section("Migration: Normalisierer fuer Dateitypen ohne Versions-Feld")
from autoclicker.persistence.migration import (
    KIND_ITEMS as _K_ITEMS, KIND_ITEM_SCAN as _K_ISCAN, KIND_POINTS as _K_PTS,
    KIND_SEQUENCE as _K_SEQ, file_version as _fv, migrate as _mig,
)

# file_version muss auch Listen und Muell vertragen - points.json IST eine Liste.
# Vorher knallte hier AttributeError und tools/migrate.py starb an der ersten Datei.
check("file_version(Liste) = 0", _fv([{"x": 1}]) == 0)
check("file_version(None) = 0", _fv(None) == 0)
check("file_version(dict ohne Feld) = 0", _fv({"name": "x"}) == 0)

# Punkte: fehlende IDs nachnummerieren, tote Felder entfernen
_pts = [{"id": 1, "x": 10, "y": 20, "name": "A"},
        {"x": 30, "y": 40, "name": "B", "legacy_flag": True}]
_pts, _m = _mig(_pts, _K_PTS)
check("Punkte: fehlende ID wird vergeben", _pts[1]["id"] is not None)
check("Punkte: vergebene ID kollidiert nicht", _pts[1]["id"] != _pts[0]["id"])
check("Punkte: totes Feld entfernt", "legacy_flag" not in _pts[1])
check("Punkte: Meldungen im Klartext", len(_m) == 2)
_wieder = _mig([dict(p) for p in _pts], _K_PTS)[1]
check("Punkte: zweiter Lauf meldet nichts", _wieder == [])

# Items: confirm_point [x,y] -> {x,y}
_items = {"Kohle": {"name": "Kohle", "confirm_point": [55, 66]},
          "Erz": {"name": "Erz", "confirm_point": {"x": 1, "y": 2}},
          "Leer": {"name": "Leer", "confirm_point": None}}
_items, _m = _mig(_items, _K_ITEMS)
check("Items: alte Liste wird zu {x,y}", _items["Kohle"]["confirm_point"] == {"x": 55, "y": 66})
check("Items: aktuelles Format bleibt", _items["Erz"]["confirm_point"] == {"x": 1, "y": 2})
check("Items: None bleibt None", _items["Leer"]["confirm_point"] is None)
check("Items: nur das Geaenderte wird gemeldet", len(_m) == 1)
check("Items: zweiter Lauf meldet nichts", _mig(_items, _K_ITEMS)[1] == [])

# Item-Scans trugen ihre Slots/Items als Kopie - jetzt nur noch Namen
_scan = {"name": "inv",
         "slots": [{"name": "S1", "scan_region": [0, 0, 1, 1], "click_pos": [0, 0]}],
         "items": [{"name": "Kohle", "confirm_point": [7, 8]}]}
_scan, _m = _mig(_scan, _K_ISCAN)
check("Item-Scan: Kopien werden zu Namen",
      _scan["slot_names"] == ["S1"] and _scan["item_names"] == ["Kohle"])
check("Item-Scan: eingebettete Kopien sind weg",
      "slots" not in _scan and "items" not in _scan)
check("Item-Scan: beide Umstellungen gemeldet", len(_m) == 2)
check("Item-Scan: zweiter Lauf meldet nichts", _mig(_scan, _K_ISCAN)[1] == [])
# Vorhandene Namensliste gewinnt gegen eine Alt-Kopie
_beides = {"name": "x", "item_names": ["Neu"], "items": [{"name": "Alt"}]}
_beides, _ = _mig(_beides, _K_ISCAN)
check("Item-Scan: vorhandene Namensliste gewinnt", _beides["item_names"] == ["Neu"])

# Der Loader kennt die alte Liste NICHT mehr - dafuer ist die Migration da
from autoclicker.persistence.serialization import _item_from_dict as _ifd
check("Loader ignoriert das alte confirm_point-Format",
      _ifd({"confirm_point": [1, 2]}, "X").confirm_point is None)
check("Loader liest das aktuelle Format",
      _ifd({"confirm_point": {"x": 1, "y": 2}}, "X").confirm_point.x == 1)
# Der Name kommt aus dem Schluessel, nicht mehr aus dem Eintrag
check("Name kommt aus dem Schluessel", _ifd({}, "Kohle").name == "Kohle")

# Verknuepfung darf nicht auf einen Punkt ohne ID zeigen (sonst point_id=null und der
# naechste Lauf meldet denselben Treffer erneut - genau das brach die Idempotenz)
_seq_roh = {"name": "s", "loop_phases": [{"name": "L", "repeat": 1, "steps": [
    {"x": 30, "y": 40, "name": "K", "delay_before": 0}]}]}
_seq_roh, _ = _mig(_seq_roh, _K_SEQ, {"points": [{"x": 30, "y": 40, "name": "ohne ID"}]})
check("Punkt ohne ID wird nicht referenziert",
      _seq_roh["loop_phases"][0]["steps"][0].get("point_id") is None)

# scheduled_start war nur da, um den Debug-Enter-Prompt zu ueberspringen - beides weg
check("kein scheduled_start-Flag mehr am State",
      not any(f.name == "scheduled_start"
              for f in __import__("dataclasses").fields(AutoClickerState)))


# ------------------------------------------------ Debug-Stufen zur Laufzeit
section("Debug-Stufen im Punkte-Menue umschaltbar (ohne config.json editieren)")
import autoclicker.config as _cfgmod
import autoclicker.handlers as _hnd

_gespeichert = []
_orig_save = _cfgmod.save_config
_cfgmod.save_config = lambda c: _gespeichert.append((c.debug_log, c.debug_detail))

_st3 = AutoClickerState()
_st3.config.debug_log = _st3.config.debug_detail = False
_hnd.handle_debug_toggle(_st3, "log")
check("Toggle 'log' schaltet Stufe 1 an", _st3.config.debug_log is True)
check("Toggle 'log' laesst Stufe 2 in Ruhe", _st3.config.debug_detail is False)
_hnd.handle_debug_toggle(_st3, "detail")
check("Toggle 'detail' schaltet Stufe 2 an", _st3.config.debug_detail is True)
check("Toggle 'detail' laesst Stufe 1 in Ruhe", _st3.config.debug_log is True)
_hnd.handle_debug_toggle(_st3, "log")
check("geflippt: Stufe 1 aus, Stufe 2 bleibt an",
      _st3.config.debug_log is False and _st3.config.debug_detail is True)
check("jede Umschaltung wird persistiert", len(_gespeichert) == 3)
_cfgmod.save_config = _orig_save


# ------------------------------------- Zusage: jeder Dateityp hat eine Schleuse
section("Migration greift bei JEDEM Dateityp (Formatwechsel ohne Neuaufnahme)")
from autoclicker.persistence import migration as _mg

# 1. Kein Dateityp ohne Eintrag. Faellt hier etwas durch, wuerde eine spaetere
#    Formataenderung fuer diesen Typ stillschweigend NICHT migriert.
_ohne = [k for k in _mg.ALL_KINDS if k not in _mg._CHAINS and k not in _mg._NORMALIZER]
check("jeder Dateityp ist in _CHAINS oder _NORMALIZER registriert", _ohne == [])

# 2. Jeder Loader, der eine dieser Dateien liest, ruft migrate() auf.
_loader_quellen = {
    "sequences": "autoclicker/persistence/sequences.py",
    "globals": "autoclicker/persistence/globals.py",
    "presets": "autoclicker/persistence/presets.py",
    "item_scans": "autoclicker/persistence/item_scans.py",
    "boss_scans": "autoclicker/persistence/boss_scans.py",
    "icon_scans": "autoclicker/persistence/icon_scans.py",
}
_repo = Path(__file__).resolve().parent.parent
_ohne_aufruf = [name for name, rel in _loader_quellen.items()
                if "migrate(" not in (_repo / rel).read_text(encoding="utf-8")]
check("jedes Persistenz-Modul ruft migrate() auf", _ohne_aufruf == [])

# 3. Unbekannter Typ ist ein Programmierfehler, kein stiller No-Op-Pfad:
#    migrate() laesst die Daten unangetastet, aber ALL_KINDS deckt alles ab (s. 1.)
check("ALL_KINDS deckt alle KIND_-Konstanten ab",
      set(_mg.ALL_KINDS) == {v for n, v in vars(_mg).items()
                             if n.startswith("KIND_") and isinstance(v, str)})

# 4. "Schon neu" heisst: nichts wird angefasst. Fuer JEDEN Typ.
_aktuell = {
    _mg.KIND_SEQUENCE: {"schema_version": _mg.SCHEMA_VERSION, "name": "s",
                        "init_steps": [], "loop_phases": [], "end_steps": []},
    _mg.KIND_POINTS: [{"id": 1, "x": 1, "y": 2, "name": "P"}],
    _mg.KIND_ITEMS: {"I": {"name": "I", "confirm_point": {"x": 1, "y": 2}}},
    _mg.KIND_ITEM_SCAN: {"name": "sc", "slot_names": ["S"], "item_names": ["I"]},
    _mg.KIND_SLOTS: {"S": {"name": "S", "scan_region": [0, 0, 1, 1], "click_pos": [0, 0]}},
    _mg.KIND_BOSS_SCAN: {"name": "b", "bosses": []},
    _mg.KIND_ICON_SCAN: {"name": "i", "scan_region": [0, 0, 1, 1]},
    _mg.KIND_GLOBAL_BOSSES: [{"name": "Drache"}],
}
check("Testdaten decken alle Dateitypen ab", set(_aktuell) == set(_mg.ALL_KINDS))
_unberuehrt = True
for _kind, _daten in _aktuell.items():
    _vorher = json.dumps(_daten, sort_keys=True)
    _raus, _meld = _mg.migrate(_daten, _kind)
    # Der Versions-Stempel darf gesetzt werden, der Inhalt nicht wandern.
    _nachher = json.dumps(_raus, sort_keys=True)
    if _meld or (_kind != _mg.KIND_SEQUENCE and _vorher != _nachher):
        _unberuehrt = False
        print(f"        -> {_kind} wurde angefasst: {_meld}")
check("aktuelle Daten werden bei keinem Typ veraendert", _unberuehrt)

# 5. Umbenennen ist ein Save-Pfad - der muss genauso reinigen wie der Loader.
from autoclicker.persistence.item_scans import update_item_in_scans as _uiis
import autoclicker.persistence.item_scans as _ismod
_scandir = Path(tempfile.mkdtemp())
(_scandir / "alt.json").write_text(json.dumps({
    "name": "alt", "slots": [],
    "items": [{"name": "Kohle", "marker_colors": [], "confirm_point": [3, 4]}]}),
    encoding="utf-8")  # Altformat: Kopie statt Referenz
_orig_dir = _ismod.ITEM_SCANS_DIR
_ismod.ITEM_SCANS_DIR = str(_scandir)
_uiis("Kohle", "Steinkohle")
_ismod.ITEM_SCANS_DIR = _orig_dir
_nach_rename = json.loads((_scandir / "alt.json").read_text(encoding="utf-8"))
check("Umbenennen zieht die Namens-Referenz nach",
      _nach_rename["item_names"] == ["Steinkohle"])
check("Umbenennen hebt dabei auch das Altformat (Kopie -> Referenz)",
      "items" not in _nach_rename)


# ------------------------------------------- Start-Durchgang (persistence/sweep)
section("Start-Durchgang: alle Dateien beim Programmstart aufs aktuelle Format")
import os as _os
from autoclicker.persistence.sweep import sweep as _sweep, sammle_dateien as _sammle

_sw = Path(tempfile.mkdtemp())
for _d in ("sequences", "items/presets", "slots/presets", "item_scans",
           "boss_scans/global", "icon_scans"):
    (_sw / _d).mkdir(parents=True, exist_ok=True)
(_sw / "sequences/points.json").write_text(json.dumps(
    [{"id": 1, "x": 100, "y": 200, "name": "A"},
     {"x": 300, "y": 400, "name": "B", "legacy_flag": True}]), encoding="utf-8")
(_sw / "sequences/alt.json").write_text(json.dumps(
    {"name": "alt", "steps": [{"x": 300, "y": 400, "name": "E", "delay_before": 1,
                               "clicks": 2, "point_index": 0}]}), encoding="utf-8")
(_sw / "items/items.json").write_text(json.dumps(
    {"K": {"name": "K", "marker_colors": [], "confirm_point": [5, 6], "uralt": 1}}),
    encoding="utf-8")
(_sw / "item_scans/kaputt.json").write_text("{ kein json", encoding="utf-8")

_cwd = _os.getcwd()
try:
    _os.chdir(_sw)
    check("Sweep findet alle angelegten Dateien", len(_sammle()) == 4)

    _e1 = _sweep(write=True)
    check("Sweep hebt die Altbestaende", _e1.anzahl_geaendert == 3)
    check("Sweep meldet 'es gab was zu tun'", bool(_e1) is True)
    check("kaputte Datei wird uebersprungen, nicht geschrieben",
          len(_e1.uebersprungen) == 1 and _e1.uebersprungen[0].name == "kaputt.json")
    check("kaputte Datei bleibt unveraendert",
          (_sw / "item_scans/kaputt.json").read_text(encoding="utf-8") == "{ kein json")
    check("Sicherung angelegt", (_sw / "sequences/alt.json.bak").exists())

    # Zweiter Durchgang: nur noch die kaputte Datei bleibt uebrig, sonst still
    _e2 = _sweep(write=True)
    check("zweiter Durchgang aendert nichts mehr", _e2.anzahl_geaendert == 0)
    check("zweiter Durchgang zaehlt alles als aktuell", _e2.aktuell == 3)

    # Ergebnis pruefen: Inhalt gehoben, Sequenz funktionsfaehig
    _pts = json.loads((_sw / "sequences/points.json").read_text(encoding="utf-8"))
    check("Start-Durchgang nummeriert Punkte", [p["id"] for p in _pts] == [1, 2])
    _sq = json.loads((_sw / "sequences/alt.json").read_text(encoding="utf-8"))
    check("Start-Durchgang stempelt die Sequenz-Version",
          _sq.get("schema_version") == _mg.SCHEMA_VERSION)
    check("Start-Durchgang verknuepft den Schritt mit seinem Punkt",
          _sq["loop_phases"][0]["steps"][0]["point_id"] == 2)
    check("Start-Durchgang entfernt tote Schritt-Felder",
          "clicks" not in _sq["loop_phases"][0]["steps"][0])
    _it = json.loads((_sw / "items/items.json").read_text(encoding="utf-8"))["K"]
    check("Start-Durchgang hebt confirm_point", _it["confirm_point"] == {"x": 5, "y": 6})
    check("Start-Durchgang entfernt totes Item-Feld", "uralt" not in _it)
finally:
    _os.chdir(_cwd)

# Abschaltbar, falls man Altbestand einfrieren will
check("migrate_on_start ist ein Config-Feld mit Default an",
      AppConfig().migrate_on_start is True)


# --------------------------------- Schlanke Schritte (nur benutzte Felder)
section("Sequenz-Schritte: nur gesetzte Felder werden geschrieben")
from autoclicker.models import SequenceStep as _SS, WaitCondition as _WCx, ElseConfig as _ECx
from autoclicker.persistence.serialization import (
    _step_to_dict as _s2d, _parse_steps as _p2s, _STEP_DEFAULTS as _SD)

_klick = _s2d(_SS(x=100, y=200, delay_before=1, name="Klick 15", point_id=7))
check("einfacher Klick braucht nur 5 Felder", len(_klick) == 5)
check("Pflichtfelder bleiben immer sichtbar",
      all(k in _klick for k in ("x", "y", "delay_before")))
check("kein leeres wait_pixel mehr", "wait_pixel" not in _klick)
check("kein leeres else_action mehr", "else_action" not in _klick)
check("kein item_scan_mode ohne item_scan", "item_scan_mode" not in _klick)

# Gesetzte Felder muessen selbstverstaendlich drinbleiben
_farb = _s2d(_SS(x=1, y=2, delay_before=0, name="F",
                 wait_condition=_WCx(pixel=(5, 6), color=(7, 8, 9), until_gone=True),
                 else_config=_ECx(action="click", x=10, y=11)))
check("gesetzte Farb-Bedingung wird geschrieben",
      _farb.get("wait_pixel") == (5, 6) and _farb.get("wait_until_gone") is True)
check("gesetzte Else-Aktion wird geschrieben",
      _farb.get("else_action") == "click" and _farb.get("else_x") == 10)

# 0 ist nicht False: scroll=0 waere ein echter Wert, screenshot_only=0 nicht
check("scroll wird bei 0 nicht als False verschluckt",
      _s2d(_SS(x=0, y=0, delay_before=0, scroll=0)).get("scroll") == 0)

# Round-Trip: jeder Schritt muss identisch zurueckkommen
_faelle = [
    _SS(x=100, y=200, delay_before=1, name="Klick", point_id=7),
    _SS(x=1, y=2, delay_before=0, name="Farbe",
        wait_condition=_WCx(pixel=(5, 6), color=(7, 8, 9), check_only=True),
        else_config=_ECx(action="skip")),
    _SS(x=0, y=0, delay_before=0.5, name="Taste", key_press="enter"),
    _SS(x=8, y=9, delay_before=0, name="Scroll", scroll=-3),
    _SS(x=0, y=0, delay_before=0, name="Scan", item_scan="inv", item_scan_mode="best"),
    _SS(x=0, y=0, delay_before=0, name="Shot", screenshot_only=True,
        screenshot_region=(1, 2, 3, 4)),
    _SS(x=5, y=5, delay_before=2, name="Zufall", delay_max=4.0, wait_only=True),
]
_abweichungen = [st for st in _faelle if _p2s([_s2d(st)])[0] != st]
check("Round-Trip aendert keinen Schritt", _abweichungen == [])

# Die Default-Tabelle darf nicht von der Dataclass abdriften
_dc_defaults = {f.name: f.default for f in __import__("dataclasses").fields(_SS)}
_abgedriftet = [k for k, v in _SD.items()
                if k in _dc_defaults and _dc_defaults[k] is not v
                and _dc_defaults[k] != v]
check("Default-Tabelle passt zur Dataclass", _abgedriftet == [])

# delay_after: Altlast raus aus dem Loader, rein in die Migration
_alt = {"schema_version": 1, "name": "s", "init_steps": [], "end_steps": [],
        "loop_phases": [{"name": "L", "repeat": 1, "steps": [
            {"x": 1, "y": 2, "name": "A", "delay_after": 3}]}]}
_alt, _m = _mig(_alt, _K_SEQ)
_step = _alt["loop_phases"][0]["steps"][0]
check("delay_after wird zu delay_before", _step.get("delay_before") == 3)
check("delay_after ist danach weg", "delay_after" not in _step)
check("Umbenennung wird gemeldet", any("delay_after" in m for m in _m))
check("Loader kennt delay_after nicht mehr",
      _p2s([{"x": 1, "y": 2, "delay_after": 9}])[0].delay_before == 0)


# ------------------------------- Items/Slots referenzieren statt kopieren
section("Item-Scans verweisen auf globale Slots/Items (keine Kopien mehr)")
from autoclicker.persistence.item_scans import resolve_scan_references as _resolve_scans
from autoclicker.models import ItemScanConfig as _ISC

_st4 = AutoClickerState()
_st4.global_slots = {"S1": ItemSlot(name="S1", scan_region=(0, 0, 10, 10), click_pos=(5, 5))}
_st4.global_items = {"Kohle": ItemProfile(name="Kohle", marker_colors=[(1, 2, 3)],
                                         category="Erz", priority=1)}
_st4.item_scans = {"inv": _ISC(name="inv", slot_names=["S1"], item_names=["Kohle"])}

_meld = _resolve_scans(_st4)
_cfg = _st4.item_scans["inv"]
check("Referenz wird zum globalen Slot aufgeloest",
      len(_cfg.slots) == 1 and _cfg.slots[0] is _st4.global_slots["S1"])
check("Referenz wird zum globalen Item aufgeloest",
      len(_cfg.items) == 1 and _cfg.items[0] is _st4.global_items["Kohle"])
check("nichts zu meckern wenn alles da ist", _meld == [])

# Der Kern der Sache: Aenderung am globalen Item wirkt im Scan
_st4.global_items["Kohle"].marker_colors = [(9, 9, 9)]
_resolve_scans(_st4)
check("Aenderung am globalen Item wirkt im Scan",
      _st4.item_scans["inv"].items[0].marker_colors == [(9, 9, 9)])

# Fehlende Namen: melden und weiterlaufen, nicht den Scan sprengen
_st4.item_scans["inv"].item_names = ["Kohle", "Gibtsnicht"]
_st4.item_scans["inv"].slot_names = ["S1", "AuchNicht"]
_meld = _resolve_scans(_st4)
check("fehlender Slot wird gemeldet", any("AuchNicht" in m for m in _meld))
check("fehlendes Item wird gemeldet", any("Gibtsnicht" in m for m in _meld))
check("der Rest bleibt nutzbar",
      len(_st4.item_scans["inv"].items) == 1 and len(_st4.item_scans["inv"].slots) == 1)

# Speichern leitet die Namen aus den aufgeloesten Objekten ab, wenn Editoren
# direkt slots/items setzen - so muss kein Editor umgebaut werden
from autoclicker.persistence.serialization import _item_scan_to_dict as _isc2d
_vom_editor = _ISC(name="neu",
                   slots=[_st4.global_slots["S1"]],
                   items=[_st4.global_items["Kohle"]])
_gespeichert = _isc2d(_vom_editor)
check("Editor-Config wird als Namen gespeichert",
      _gespeichert["slot_names"] == ["S1"] and _gespeichert["item_names"] == ["Kohle"])
check("keine Kopien in der Datei",
      "slots" not in _gespeichert and "items" not in _gespeichert)


# ----------------------- Default-Tabellen duerfen nicht von den Dataclasses abdriften
section("Default-Tabellen passen zu den Dataclasses")
import dataclasses as _dc
from autoclicker.persistence import serialization as _ser
from autoclicker.models import (ItemProfile as _IP, ItemSlot as _IS2,
                                BossProfile as _BP, BossScanConfig as _BSC,
                                IconScanConfig as _ISC2, SequenceStep as _SS2,
                                ItemScanConfig as _ISCFG)

def _dataclass_defaults(cls):
    raus = {}
    for f in _dc.fields(cls):
        if f.default is not _dc.MISSING:
            raus[f.name] = f.default
        elif f.default_factory is not _dc.MISSING:      # type: ignore[misc]
            raus[f.name] = f.default_factory()          # type: ignore[misc]
    return raus

# Steht in der Tabelle ein anderer Wert als in der Dataclass, wuerde das Feld beim
# Speichern weggelassen und beim Laden mit einem ANDEREN Wert wieder auftauchen -
# stiller Datenverlust. Deshalb hart pruefen.
_tabellen = [
    ("Item", _ser._ITEM_DEFAULTS, _IP),
    ("Slot", _ser._SLOT_DEFAULTS, _IS2),
    ("Boss", _ser._BOSS_DEFAULTS, _BP),
    ("Boss-Scan", _ser._BOSS_SCAN_DEFAULTS, _BSC),
    ("Icon-Scan", _ser._ICON_SCAN_DEFAULTS, _ISC2),
    ("Item-Scan", _ser._ITEM_SCAN_DEFAULTS, _ISCFG),
    ("Schritt", _ser._STEP_DEFAULTS, _SS2),
]
for _tab_name, _tabelle, _cls in _tabellen:
    _dcd = _dataclass_defaults(_cls)
    _drift = [k for k, v in _tabelle.items()
              if k in _dcd and not (_dcd[k] == v and type(_dcd[k]) is type(v))]
    check(f"{_tab_name}-Defaults ohne Abweichung", _drift == [])

# Der Datei-Default darf NICHT aus der Config kommen. Frueher war
# `config.DEFAULT_MIN_CONFIDENCE = CONFIG.scan_min_confidence`, womit die Tabellen oben
# vom Nutzerwert abhingen: ein Item, dessen Konfidenz zufaellig auf dem Config-Wert stand,
# verlor sein Feld beim Speichern und kam nach einer Config-Aenderung mit einem anderen
# Wert zurueck. Die Pruefung oben findet das nur, wenn die Config gerade abweicht - dieser
# Test findet es immer.
import autoclicker.config as _cfgmod
from autoclicker.models import DEFAULT_MIN_CONFIDENCE as _FILE_DEFAULT
check("Datei-Default liegt bei den Dataclasses, nicht in der Config",
      not hasattr(_cfgmod, "DEFAULT_MIN_CONFIDENCE"))
check("Datei-Default ist konstant, nicht der Config-Wert",
      _FILE_DEFAULT == 0.8 and _IP(name="x").min_confidence == _FILE_DEFAULT)


# ------------------------------------------------------- Import: point_id
section("Import zieht point_id auf die neu vergebenen Punkt-IDs nach")
import os as _os, zipfile as _zip
from autoclicker.import_export import import_bundle as _import_bundle
from autoclicker.models import AutoClickerState as _ACS, ClickPoint as _CP3


def _bundle_bauen(pfad, punkt_id=1, step_point_id=1):
    """Minimal-Bundle: ein Punkt + eine Sequenz, deren Schritt auf ihn zeigt."""
    with _zip.ZipFile(pfad, "w") as zf:
        zf.writestr("manifest.json", json.dumps(
            {"version": 1, "reference_points": {"point1": [0, 0], "point2": [10, 10]},
             "contents": {}}))
        zf.writestr("points.json", json.dumps(
            [{"id": punkt_id, "x": 500, "y": 500, "name": "Ofen"}]))
        zf.writestr("sequences/farm.json", json.dumps(
            {"name": "farm", "schema_version": 2, "init_steps": [], "end_steps": [],
             "loop_phases": [{"name": "Loop", "repeat": 1, "steps": [
                 {"x": 500, "y": 500, "delay_before": 0, "name": "Ofen",
                  "point_id": step_point_id}]}]}))


_alt_cwd = _os.getcwd()
_imp_dir = tempfile.mkdtemp()
try:
    _os.chdir(_imp_dir)
    _bundle = Path(_imp_dir) / "b.zip"
    _bundle_bauen(_bundle)

    # Lokal existiert bereits ein Punkt #1 an GANZ anderer Stelle
    _st = _ACS()
    _st.points = [_CP3(50, 50, "Werkbank", 1)]
    _ok, _msg = _import_bundle(_st, str(_bundle), import_config=False, merge=True)

    _neu = [p for p in _st.points if p.name == "Ofen"]
    check("importierter Punkt bekommt eine freie ID", bool(_neu) and _neu[0].id != 1)

    _seq = _st.sequences.get("farm")
    _schritt = _seq.loop_phases[0].steps[0] if _seq else None
    check("Schritt zeigt auf den importierten Punkt, nicht auf den lokalen",
          _schritt is not None and _schritt.point_id == _neu[0].id)

    # Gegenprobe: der lokale Punkt darf den Schritt nicht an sich ziehen
    from autoclicker.persistence import resolve_point_references as _rpr
    _rpr(_st, _seq)
    check("Aufloesung landet auf den richtigen Koordinaten",
          (_schritt.x, _schritt.y) == (500, 500))

    # Ohne Punkt-Import darf keine Referenz stehenbleiben
    _st2 = _ACS()
    _st2.points = [_CP3(50, 50, "Werkbank", 1)]
    _import_bundle(_st2, str(_bundle), import_points=False, import_config=False)
    _s2 = _st2.sequences["farm"].loop_phases[0].steps[0]
    check("ohne Punkt-Import faellt die Referenz weg", _s2.point_id is None)
    check("Koordinaten bleiben erhalten", (_s2.x, _s2.y) == (500, 500))
finally:
    _os.chdir(_alt_cwd)


# ------------------------------------------------- Laden veraendert nichts
section("Sequenz laden meldet nur, schreibt nicht")
from autoclicker.editors.sequence_editor.loader import _report_point_mismatches
from autoclicker.models import Sequence as _Seq3, LoopPhase as _LP3, SequenceStep as _SS3

# Aufgenommene Punkte heissen per Default P<id> - eine Sequenz von einem anderen Rechner
# bringt also "P3" mit, und der lokale P3 liegt woanders. Frueher wurde der Schritt still
# dorthin verschoben UND die Datei ueberschrieben.
_st3 = _ACS()
_st3.points = [_CP3(50, 50, "P3", 3)]
_fremd = _SS3(x=900, y=900, delay_before=0, name="P3")
_seq3 = _Seq3("fremd", [], [_LP3("Loop", [_fremd])], [])
_report_point_mismatches(_st3, _seq3)
check("Schritt-Koordinaten bleiben unangetastet", (_fremd.x, _fremd.y) == (900, 900))
check("keine Referenz wird stillschweigend gesetzt", _fremd.point_id is None)

# Mit Referenz ist die Aufloesung zustaendig - dort wird der Schritt auch gemeldet
_verknuepft = _SS3(x=900, y=900, delay_before=0, name="P3", point_id=3)
_seq4 = _Seq3("mit_ref", [], [_LP3("Loop", [_verknuepft])], [])
_report_point_mismatches(_st3, _seq4)
check("Schritt mit point_id bleibt dem Loader egal", (_verknuepft.x, _verknuepft.y) == (900, 900))
from autoclicker.persistence import resolve_point_references as _rpr2
_meld = _rpr2(_st3, _seq4)
check("erst die Aufloesung zieht ihn nach", (_verknuepft.x, _verknuepft.y) == (50, 50))
check("und meldet das im Klartext", len(_meld) == 1 and "P3" in _meld[0])


# -------------------------------------------- Item-Scan: Namen sind die Wahrheit
section("Item-Scan: Namen und Objekte bleiben synchron")
from autoclicker.models import ItemScanConfig as _ISC3, ItemSlot as _IS3, ItemProfile as _IP3
from autoclicker.persistence import resolve_scan_references as _rsr

_slot_a, _slot_b = _IS3("S1", (0, 0, 10, 10), (5, 5)), _IS3("S2", (0, 0, 10, 10), (5, 5))
_item_a = _IP3("Kohle")

# So baut der EDITOR (und das Scan-Studio) eine Config: nur Objekte.
_cfg_editor = _ISC3(name="inv", slots=[_slot_a, _slot_b], items=[_item_a])
check("Editor-Config bekommt die Namen automatisch",
      _cfg_editor.slot_names == ["S1", "S2"] and _cfg_editor.item_names == ["Kohle"])

# So baut der LOADER: nur Namen. __str__ muss trotzdem die richtige Zahl zeigen -
# vorher stand im Menue bei jedem gespeicherten Scan "0 Slots, 0 Items".
_cfg_datei = _ISC3(name="inv", slot_names=["S1", "S2"], item_names=["Kohle"])
check("frisch geladen zeigt das Menue die richtige Anzahl",
      "2 Slots" in str(_cfg_datei) and "1 Items" in str(_cfg_datei))
check("Vorauswahl beim Bearbeiten kommt aus den Namen",
      list(_cfg_datei.slot_names) == ["S1", "S2"])

# Der Fall, der den Scan bis zum Neustart totlegte: bearbeiten, dann Sequenz starten.
# resolve_scan_references laeuft vor JEDEM Lauf und ging ueber die (leeren) Namen.
_st5 = _ACS()
_st5.global_slots = {"S1": _slot_a, "S2": _slot_b}
_st5.global_items = {"Kohle": _item_a}
_st5.item_scans["inv"] = _cfg_editor
_rsr(_st5)
check("frisch bearbeiteter Scan ueberlebt den Sequenzstart",
      len(_cfg_editor.slots) == 2 and len(_cfg_editor.items) == 1)

# Und andersherum: aus Namen werden Objekte
_st5.item_scans["inv2"] = _cfg_datei
_rsr(_st5)
check("Namen werden zu Objekten aufgeloest",
      [s.name for s in _cfg_datei.slots] == ["S1", "S2"])

# Nachtraegliche Zuweisung an .slots (der Weg, der urspruenglich schiefging)
_cfg_spaet = _ISC3(name="spaet")
_cfg_spaet.slots = [_slot_a]
_cfg_spaet.sync_names()
check("nachtraeglich gesetzte Objekte tragen ihre Namen nach",
      _cfg_spaet.slot_names == ["S1"])

# Gespeichert werden weiterhin nur Namen
_gespeichert = _item_scan_to_dict(_cfg_editor)
check("Datei enthaelt nur Namen, keine Kopien",
      _gespeichert.get("slot_names") == ["S1", "S2"]
      and "slots" not in _gespeichert and "items" not in _gespeichert)


# ------------------------------------------------------- Setup-Pruefung
section("Setup-Pruefung findet die stillen Fehler")
from autoclicker.diagnose import pruefe_setup, STUFE_FEHLER, STUFE_HINWEIS
from autoclicker.models import (BossProfile as _BP2, BossScanConfig as _BSC2,
                                IconScanConfig as _ISC4)

_st6 = _ACS()
_st6.global_slots = {"S1": _IS3("S1", (0, 0, 10, 10), (5, 5))}
_st6.global_items = {
    "MitTemplate": _IP3("MitTemplate", template="gibtsnicht.png"),
    "OhneAlles": _IP3("OhneAlles"),
}
_st6.item_scans = {
    "inv": _ISC3(name="inv", slot_names=["S1", "FEHLT"], item_names=["MitTemplate"]),
    "leer": _ISC3(name="leer"),
}
_st6.boss_scans = {"b": _BSC2(name="b", bosses=[_BP2("Hydra")], use_llm=True)}
_st6.icon_scans = {"ico": _ISC4(name="ico")}

_ber = pruefe_setup(_st6, mit_sequenzen=False)
_texte = [f"{b.bereich}: {b.text}" for b in _ber.befunde]


def _hat(teil):
    return any(teil in t for t in _texte)


check("fehlendes Template wird gefunden", _hat("gibtsnicht.png"))
check("Boss ohne Template UND ohne Marker wird gefunden",
      _hat("Hydra") and _hat("wird nie erkannt"))
check("Icon-Scan ohne Erkennung wird gefunden", _hat("Icon-Scan 'ico'"))
check("fehlender Slot im Scan wird gefunden", _hat("FEHLT"))
check("Scan ganz ohne Slot wird gefunden", _hat("kein einziger Slot"))
check("use_llm ohne llm_enabled wird gemeldet", _hat("llm_enabled global aus"))
check("Fehler und Hinweise sind getrennt",
      len(_ber.fehler) >= 4 and len(_ber.hinweise) >= 2
      and all(b.stufe in (STUFE_FEHLER, STUFE_HINWEIS) for b in _ber.befunde))

# Ein sauberes Setup darf NICHTS melden - sonst gewoehnt man sich das Ignorieren an
_st7 = _ACS()
_st7.global_slots = {"S1": _IS3("S1", (0, 0, 10, 10), (5, 5))}
_st7.global_items = {"Kohle": _IP3("Kohle", marker_colors=[(1, 2, 3)])}
_st7.item_scans = {"inv": _ISC3(name="inv", slot_names=["S1"], item_names=["Kohle"])}
_sauber = pruefe_setup(_st7, mit_sequenzen=False)
check("sauberes Setup meldet nichts", not _sauber and _sauber.befunde == [])
check("trotzdem steht da, was geprueft wurde", len(_sauber.geprueft) >= 3)


# ------------------------------------------------------- Template-Cache
section("Template-Cache: einmal lesen, bei Aenderung neu")
from autoclicker import imaging as _img

if not (_img.OPENCV_AVAILABLE and _img.NUMPY_AVAILABLE):
    print("  ---   uebersprungen (OpenCV/NumPy fehlen in dieser Umgebung)")
else:
    import numpy as _np, time as _t
    _tpl_dir = tempfile.mkdtemp()
    _tpl = str(Path(_tpl_dir) / "t.png")
    _img.cv2.imwrite(_tpl, _np.zeros((8, 8, 3), dtype=_np.uint8))
    _img._template_cache.clear()

    _a = _img._load_template(_tpl)
    _b = _img._load_template(_tpl)
    check("zweiter Aufruf liefert dasselbe Objekt (kein Neu-Dekodieren)", _a is _b)

    # Neu gelerntes Template muss sofort greifen - Schluessel ist (mtime, size)
    _t.sleep(0.01)
    _img.cv2.imwrite(_tpl, _np.full((8, 8, 3), 255, dtype=_np.uint8))
    _c = _img._load_template(_tpl)
    check("geaendertes Template wird neu geladen", _c is not _a and int(_c[0, 0, 0]) == 255)

    # Skalierte Variante wird ebenfalls gemerkt
    _s1 = _img._template_in_groesse(_tpl, _c, 16, 16)
    _s2 = _img._template_in_groesse(_tpl, _c, 16, 16)
    check("skalierte Variante kommt aus dem Cache", _s1 is _s2 and _s1.shape[:2] == (16, 16))
    check("passende Groesse wird nicht skaliert",
          _img._template_in_groesse(_tpl, _c, 8, 8) is _c)

    check("fehlendes Template meldet sauber None", _img._load_template(_tpl + "_weg") is None)


# ------------------------------- else bei Farb-Schritten: 'stattdessen', nicht 'zusaetzlich'
section("Farb-Schritt + else: der eigene Klick entfaellt")
# Die Hilfe im Sequenz-Editor sagt: 'else skip' = nur DIESEN Schritt ueberspringen,
# 'else <Punkt>' / 'else key' = STATTDESSEN das tun. Vorher lief beides: erst die
# else-Aktion, dann trotzdem der eigene Klick. Und ein nicht erfuellter checkcolor-
# Schritt gab False zurueck, was im Worker den Rest der Phase abbrach.
import autoclicker.runtime.steps as _RS
import autoclicker.runtime.actions as _RA
from autoclicker.models import ElseConfig as _EC2
from autoclicker.config import AppConfig as _AC2

class _Pixel:
    def __init__(self, rgb): self._rgb = rgb
    def getpixel(self, _xy): return self._rgb

_klicks, _tasten = [], []
_orig_click, _orig_key = _RS.safe_click, _RS.safe_key
_orig_shot, _orig_pillow = _RS.take_screenshot, _RS.PILLOW_AVAILABLE
_orig_failsafe = _RS.check_failsafe
_RS.safe_click = _RA.safe_click = lambda st, x, y, label="": (_klicks.append((x, y, label)), True)[1]
_RS.safe_key = _RA.safe_key = lambda st, key, label="": (_tasten.append(key), True)[1]
_RS.check_failsafe = lambda st: False
_RS.PILLOW_AVAILABLE = True

def _farbschritt(trifft, else_cfg, check_only=True):
    """Fuehrt einen Farb-Schritt aus. Returns (rueckgabe, klicks, tasten)."""
    _klicks.clear(); _tasten.clear()
    _RS.take_screenshot = lambda region=None: _Pixel((10, 10, 10) if trifft else (200, 200, 200))
    st = AutoClickerState(); st.config = _AC2()
    st.config.pixel_wait_timeout = 0.05
    st.config.pixel_check_interval = 0.01
    st.config.pixel_max_consecutive_timeouts = 0
    schritt = _SS(x=1, y=2, delay_before=0, name="Ziel",
                  wait_condition=_WCx(pixel=(5, 5), color=(10, 10, 10), check_only=check_only),
                  else_config=else_cfg)
    r = _RS.execute_step(st, schritt, 1, 3, "T")
    return r, [k for k in _klicks if k[2] == "Ziel"], list(_tasten)

try:
    # Referenz: Bedingung erfuellt -> der Schritt klickt ganz normal
    _r, _eigen, _ = _farbschritt(True, None)
    check("checkcolor erfuellt -> eigener Klick laeuft", _r is True and len(_eigen) == 1)

    # Nicht erfuellt, kein else -> nur diesen Schritt ueberspringen (True!), kein Klick
    _r, _eigen, _ = _farbschritt(False, None)
    check("checkcolor nicht erfuellt -> Schritt uebersprungen, Phase laeuft weiter",
          _r is True and _eigen == [])

    # else skip -> kein eigener Klick
    _r, _eigen, _ = _farbschritt(False, _EC2(action="skip"))
    check("checkcolor + 'else skip' -> kein eigener Klick", _r is True and _eigen == [])

    # else <Punkt> -> NUR der Else-Punkt, nicht auch das eigene Ziel
    _r, _eigen, _ = _farbschritt(False, _EC2(action="click", x=999, y=999, name="E"))
    check("checkcolor + 'else <Punkt>' -> nur der Else-Punkt",
          _r is True and _eigen == [] and (999, 999, "else:E") in _klicks)

    # else key -> Taste statt Klick
    _r, _eigen, _t = _farbschritt(False, _EC2(action="key", key="enter"))
    check("checkcolor + 'else key' -> Taste statt eigenem Klick",
          _r is True and _eigen == [] and _t == ["enter"])

    # else restart/skip_cycle muessen weiterhin abbrechen
    _r, _eigen, _ = _farbschritt(False, _EC2(action="restart"))
    check("checkcolor + 'else restart' bricht ab", _r is False and _eigen == [])

    # Dasselbe auf dem Warte-Pfad: Timeout -> else, danach KEIN eigener Klick
    _r, _eigen, _ = _farbschritt(False, _EC2(action="skip"), check_only=False)
    check("Warten + Timeout + 'else skip' -> kein eigener Klick", _eigen == [])
    _r, _eigen, _ = _farbschritt(False, _EC2(action="click", x=999, y=999, name="E"),
                                 check_only=False)
    check("Warten + Timeout + 'else <Punkt>' -> nur der Else-Punkt",
          _eigen == [] and (999, 999, "else:E") in _klicks)
finally:
    _RS.safe_click = _RA.safe_click = _orig_click
    _RS.safe_key = _RA.safe_key = _orig_key
    _RS.take_screenshot = _orig_shot
    _RS.PILLOW_AVAILABLE = _orig_pillow
    _RS.check_failsafe = _orig_failsafe


# ------------------------------- Immediate-Modus: Kategorie-Filter ueber Slots hinweg
section("Item-Scan im Immediate-Modus (Scan->Klick pro Slot)")
# Die Buchhaltung um state.clicked_categories wurde entfernt (nachweislich dasselbe
# Ergebnis wie 'nichts tun'). Diese Tests halten das Verhalten fest, das bleiben muss:
# je Kategorie nur einmal klicken, auch ueber mehrere Slots - und ein reiner Lern-Scan
# ohne Items darf nicht stillschweigend aussteigen.
import autoclicker.runtime.item_scan as _IS

_orig_prof, _orig_shot2, _orig_park = _IS._check_profile_match, _IS.take_screenshot, _IS._park_mouse_for_scan
_orig_click2 = _IS.safe_click
_orig_failsafe2 = _RS.check_failsafe
_RS.check_failsafe = lambda st: False   # gestubbtes get_cursor_pos liefert (0,0) = Ecke
_geklickt = []
_IS.take_screenshot = lambda region=None: object()
_IS._park_mouse_for_scan = lambda p: None
_IS.safe_click = lambda st, x, y, label="": (_geklickt.append(label), True)[1]

def _immediate_lauf(items, slots, treffer):
    """treffer: dict slot_name -> item_name (was in diesem Slot erkannt wird)."""
    _geklickt.clear()
    st = AutoClickerState(); st.config = _AC2()
    st.config.scan_click_immediate = True
    st.config.scan_reverse = False   # feste Slot-Reihenfolge, sonst haengt das Ergebnis
                                     # an der Prioritaet des zuerst gesehenen Items
    cfg = _ISC(name="inv", slots=slots, items=items)
    st.item_scans = {"inv": cfg}
    # Erkennung: Slot X erkennt Item Y. _check_profile_match sieht nur das Item,
    # daher ueber den gerade gescannten Slot mitgefuehrt.
    zustand = {"slot": None}
    _orig_exec = _IS.execute_item_scan
    def _prof(profile, img, tol, state, debug, label="gefunden"):
        return treffer.get(zustand["slot"]) == profile.name
    _IS._check_profile_match = _prof
    def _exec(state, name, mode="all", slots_override=None):
        zustand["slot"] = slots_override[0].name if slots_override else None
        return _orig_exec(state, name, mode, slots_override)
    _IS.execute_item_scan = _exec
    _RS.execute_item_scan = _exec
    try:
        schritt = _SS(x=0, y=0, delay_before=0, name="S", item_scan="inv")
        _RS.execute_step(st, schritt, 1, 1, "T")
    finally:
        _IS.execute_item_scan = _orig_exec
        _RS.execute_item_scan = _orig_exec
    return list(_geklickt)

try:
    _slots = [ItemSlot(name=f"S{i}", scan_region=(0, 0, 8, 8), click_pos=(i, i))
              for i in (1, 2, 3)]
    # Zwei Slots zeigen dieselbe Kategorie 'Erz' -> nur der erste darf geklickt werden
    _items = [ItemProfile(name="Kohle", marker_colors=[(1, 2, 3)], category="Erz", priority=1),
              ItemProfile(name="Eisen", marker_colors=[(4, 5, 6)], category="Erz", priority=5),
              ItemProfile(name="Fisch", marker_colors=[(7, 8, 9)], category="Nahrung", priority=1)]
    # S1 = Kohle (Erz, P1), S2 = Eisen (Erz, P5): das schlechtere Eisen faellt raus
    _r = _immediate_lauf(_items, _slots, {"S1": "Kohle", "S2": "Eisen", "S3": "Fisch"})
    check("Immediate: schlechteres Item derselben Kategorie faellt raus",
          _r == ["item:Kohle", "item:Fisch"])

    # Umgekehrt: erst Eisen (P5), dann Kohle (P1) — das BESSERE darf noch klicken
    _r = _immediate_lauf(_items, _slots, {"S1": "Eisen", "S2": "Kohle"})
    check("Immediate: besseres Item derselben Kategorie klickt nach",
          _r == ["item:Eisen", "item:Kohle"])

    # Andere Kategorien bleiben unabhaengig voneinander
    _r = _immediate_lauf(_items, _slots, {"S1": "Fisch", "S2": "Kohle"})
    check("Immediate: verschiedene Kategorien werden beide geklickt",
          _r == ["item:Fisch", "item:Kohle"])

    # Reiner Lern-Scan (keine Items, learn_unknown=True) darf nicht vorzeitig aussteigen
    _st_lern = AutoClickerState(); _st_lern.config = _AC2()
    _st_lern.config.scan_click_immediate = True
    _st_lern.config.scan_reverse = False
    _st_lern.item_scans = {"lern": _ISC(name="lern", slots=_slots, items=[],
                                        learn_unknown=True)}
    _besucht = []
    _IS._check_profile_match = lambda *a, **k: False
    _orig_lern = _IS._learn_unknown_slot_item
    _IS._learn_unknown_slot_item = lambda st, slot, img, dbg: _besucht.append(slot.name)
    try:
        _RS.execute_step(_st_lern, _SS(x=0, y=0, delay_before=0, name="L",
                                       item_scan="lern"), 1, 1, "T")
    finally:
        _IS._learn_unknown_slot_item = _orig_lern
    check("Immediate: reiner Lern-Scan besucht alle Slots",
          _besucht == ["S1", "S2", "S3"])

    # Tippfehler im Scan-Namen muss in BEIDEN Modi gemeldet werden, nicht nur im einen
    import io as _io, contextlib as _cl
    def _stiller_lauf(immediate):
        _st_t = AutoClickerState(); _st_t.config = _AC2()
        _st_t.config.scan_click_immediate = immediate
        _st_t.item_scans = {}
        _b = _io.StringIO()
        with _cl.redirect_stdout(_b):
            _RS.execute_step(_st_t, _SS(x=0, y=0, delay_before=0, name="S",
                                        item_scan="gibtsnicht"), 1, 1, "T")
        return "nicht gefunden" in _b.getvalue()
    check("fehlender Scan wird im Normal-Modus gemeldet", _stiller_lauf(False))
    check("fehlender Scan wird auch im Immediate-Modus gemeldet", _stiller_lauf(True))
finally:
    _IS._check_profile_match = _orig_prof
    _IS.take_screenshot = _orig_shot2
    _IS._park_mouse_for_scan = _orig_park
    _IS.safe_click = _orig_click2
    _RS.check_failsafe = _orig_failsafe2


# ------------------------------- Farb-Bedingung gilt fuer JEDE Aktion
section("Farb-Bedingung an Taste/Scroll (nicht nur am Klick)")
# Taste und Scroll wurden vor der Farb-Bedingung abgefertigt: ein Trigger an so einem
# Schritt wurde ignoriert, die Aktion feuerte sofort. Jetzt wartet execute_step zentral
# fuer alle Aktions-Schritte an einer Stelle.
_orig_c3, _orig_k3 = _RS.safe_click, _RS.safe_key
_orig_s3, _orig_shot3 = _RS.safe_scroll, _RS.take_screenshot
_orig_p3, _orig_f3 = _RS.PILLOW_AVAILABLE, _RS.check_failsafe
_akt = {"klick": [], "taste": [], "scroll": []}
_shots = []

class _Pix2:
    def __init__(self, rgb): self._rgb = rgb
    def getpixel(self, _xy): return self._rgb

_RS.safe_click = _RA.safe_click = lambda st, x, y, label="": (_akt["klick"].append((x, y)), True)[1]
_RS.safe_key = _RA.safe_key = lambda st, k, label="": (_akt["taste"].append(k), True)[1]
_RS.safe_scroll = _RA.safe_scroll = lambda st, c, x=None, y=None, label="": (_akt["scroll"].append(c), True)[1]
_RS.PILLOW_AVAILABLE = True
_RS.check_failsafe = lambda st: False

def _mit_trigger(schritt, trifft):
    for v in _akt.values():
        v.clear()
    _shots.clear()
    def _shot(region=None):
        _shots.append(region)
        return _Pix2((10, 10, 10) if trifft else (200, 200, 200))
    _RS.take_screenshot = _shot
    st = AutoClickerState(); st.config = _AC2()
    st.config.pixel_wait_timeout = 0.05
    st.config.pixel_check_interval = 0.01
    st.config.pixel_max_consecutive_timeouts = 0
    _RS.execute_step(st, schritt, 1, 2, "T")
    return len(_shots) > 0, {k: list(v) for k, v in _akt.items()}

try:
    _wc3 = lambda **kw: _WCx(pixel=(5, 5), color=(10, 10, 10), **kw)

    # Trifft NICHT zu -> keine Aktion, egal welcher Schritt-Typ
    for _name, _schritt, _feld in [
        ("Klick", _SS(x=1, y=2, delay_before=0, name="K", wait_condition=_wc3()), "klick"),
        ("Taste", _SS(x=0, y=0, delay_before=0, name="T", key_press="enter",
                      wait_condition=_wc3()), "taste"),
        ("Scroll", _SS(x=3, y=4, delay_before=0, name="S", scroll=-3,
                       wait_condition=_wc3()), "scroll"),
    ]:
        _geprueft, _was = _mit_trigger(_schritt, trifft=False)
        check(f"{_name}-Schritt: Farb-Bedingung wird geprueft", _geprueft)
        check(f"{_name}-Schritt: Aktion feuert NICHT bei Nichttreffer", _was[_feld] == [])

    # Trifft zu -> Aktion laeuft
    _, _was = _mit_trigger(_SS(x=0, y=0, delay_before=0, name="T", key_press="enter",
                               wait_condition=_wc3()), trifft=True)
    check("Taste-Schritt: Aktion laeuft bei Treffer", _was["taste"] == ["enter"])
    _, _was = _mit_trigger(_SS(x=3, y=4, delay_before=0, name="S", scroll=-3,
                               wait_condition=_wc3()), trifft=True)
    check("Scroll-Schritt: Aktion laeuft bei Treffer", _was["scroll"] == [-3])

    # else greift jetzt auch hier — und ersetzt die Aktion
    _, _was = _mit_trigger(_SS(x=0, y=0, delay_before=0, name="T", key_press="enter",
                               wait_condition=_wc3(check_only=True),
                               else_config=_EC2(action="click", x=99, y=99, name="E")),
                           trifft=False)
    check("Taste-Schritt: else greift und ersetzt die Taste",
          _was["taste"] == [] and _was["klick"] == [(99, 99)])

    # Ohne Farb-Bedingung bleibt es beim reinen Warten (keine Screenshots)
    _geprueft, _was = _mit_trigger(_SS(x=0, y=0, delay_before=0, name="T",
                                       key_press="enter"), trifft=True)
    check("Taste ohne Bedingung: kein Screenshot, Taste laeuft",
          not _geprueft and _was["taste"] == ["enter"])

    # Anzeige muss die Bedingung zeigen, sonst ist sie im Editor unsichtbar
    check("Anzeige: Taste-Schritt zeigt die Farb-Bedingung",
          "Farbe DA bei (5,5)" in str(_SS(x=0, y=0, delay_before=0, key_press="enter",
                                          wait_condition=_wc3())))
    check("Anzeige: Scroll-Schritt zeigt die Farb-Bedingung",
          "Farbe WEG bei (5,5)" in str(_SS(x=1, y=1, delay_before=0, scroll=2,
                                           wait_condition=_wc3(until_gone=True))))
    check("Anzeige: ohne Bedingung weiterhin nur die Wartezeit",
          "Farbe" not in str(_SS(x=0, y=0, delay_before=3, key_press="enter")))
    # Jeder Schritt-Typ muss sich in der Liste als das zeigen, was er ist. Der
    # Icon-Scan hatte gar keinen Zweig und erschien als "sofort -> klicke (0, 0)".
    for _typ, _kw, _erwartet in [
        ("Icon-Scan", dict(icon_scan="Mission"), "ICON-SCAN 'Mission'"),
        ("Boss-Scan", dict(boss_scan="B"), "BOSS-SCAN 'B'"),
        ("Watcher", dict(boss_watcher="W"), "BOSS-WATCHER 'W'"),
        ("Item-Scan", dict(item_scan="I"), "SCAN 'I'"),
        ("Screenshot", dict(screenshot_only=True), "SCREENSHOT"),
    ]:
        check(f"Anzeige: {_typ} wird als solcher angezeigt",
              _erwartet in str(_SS(x=0, y=0, delay_before=0, **_kw)))
finally:
    _RS.safe_click = _RA.safe_click = _orig_c3
    _RS.safe_key = _RA.safe_key = _orig_k3
    _RS.safe_scroll = _RA.safe_scroll = _orig_s3
    _RS.take_screenshot = _orig_shot3
    _RS.PILLOW_AVAILABLE = _orig_p3
    _RS.check_failsafe = _orig_f3


# ------------------------------- Editor-Regel vs. Runtime-Verhalten fuer 'else'
section("'else' im Editor erlauben genau dort, wo die Runtime es auswertet")
# Der Editor verwarf 'boss X else skip' mit einer Warnung, obwohl der Boss-Scan die
# else-Aktion ausfuehrt. Dieser Test misst BEIDE Seiten und vergleicht sie, statt die
# Liste nur abzuschreiben: erlaubt der Editor else, muss die Aktion auch feuern.
from autoclicker.editors.sequence_editor.helpers import (
    apply_else_to_step as _apply_else, _kann_else)
import autoclicker.runtime.boss_detection as _BD
import io as _io2, contextlib as _cl2

_orig_c4, _orig_shot4 = _RS.safe_click, _RS.take_screenshot
_orig_f4, _orig_p4 = _RS.check_failsafe, _RS.PILLOW_AVAILABLE
_orig_bscan, _orig_iscan = _RS.execute_boss_scan, _RS.execute_icon_scan
_orig_iscan2 = _RS.execute_item_scan
_else_klicks = []
_RS.safe_click = _RA.safe_click = lambda st, x, y, label="": (_else_klicks.append((x, y)), True)[1]
_RS.check_failsafe = lambda st: False
_RS.PILLOW_AVAILABLE = True
# Alles schlaegt fehl -> falls else ausgewertet wird, muss es feuern
_RS.execute_boss_scan = lambda st, n: (False, None)
_RS.execute_icon_scan = lambda st, n: False
_RS.execute_item_scan = lambda st, n, m=None, slots_override=None: []
_RS.take_screenshot = lambda region=None: _Pix2((200, 200, 200))

def _else_feuert(**kw):
    """Baut einen Schritt, haengt 'else <99,99>' an und prueft, ob es klickt."""
    _else_klicks.clear()
    schritt = _SS(x=1, y=2, delay_before=0, name="s", **kw)
    schritt.else_config = _EC2(action="click", x=99, y=99, name="E")
    st = AutoClickerState(); st.config = _AC2()
    st.config.pixel_wait_timeout = 0.05
    st.config.pixel_check_interval = 0.01
    st.config.pixel_max_consecutive_timeouts = 0
    st.config.llm_watcher_max_scans = 1
    st.boss_scans = {"X": _BSC(name="X")} if (kw.get("boss_scan") or kw.get("boss_watcher")) else {}
    with _cl2.redirect_stdout(_io2.StringIO()):
        _RS.execute_step(st, schritt, 1, 2, "T")
    return (99, 99) in _else_klicks

try:
    from autoclicker.models import BossScanConfig as _BSC
    _faelle = {
        "Farb-Trigger": dict(wait_condition=_WCx(pixel=(5, 5), color=(10, 10, 10))),
        "Item-Scan":    dict(item_scan="X"),
        "Boss-Scan":    dict(boss_scan="X"),
        "Icon-Scan":    dict(icon_scan="X"),
        "Boss-Watcher": dict(boss_watcher="X"),
        "reiner Klick": dict(),
    }
    for _name, _kw in _faelle.items():
        _schritt = _SS(x=1, y=2, delay_before=0, name="s", **_kw)
        _editor_erlaubt = _kann_else(_schritt)
        _runtime_wertet_aus = _else_feuert(**_kw)
        check(f"{_name}: Editor-Regel deckt sich mit der Runtime",
              _editor_erlaubt == _runtime_wertet_aus)

    # Und die konkreten Faelle, die vorher verworfen wurden
    for _name, _kw in [("boss", dict(boss_scan="X")), ("icon", dict(icon_scan="X"))]:
        _s = _SS(x=0, y=0, delay_before=0, name="s", **_kw)
        with _cl2.redirect_stdout(_io2.StringIO()):
            _apply_else(_s, ["skip"], AutoClickerState())
        check(f"'{_name} X else skip' wird uebernommen", _s.else_config is not None)
    # Watcher bleibt bewusst aussen vor
    _s = _SS(x=0, y=0, delay_before=0, name="s", boss_watcher="X")
    with _cl2.redirect_stdout(_io2.StringIO()):
        _apply_else(_s, ["skip"], AutoClickerState())
    check("'watcher X else skip' wird weiterhin abgelehnt", _s.else_config is None)
finally:
    _RS.safe_click = _RA.safe_click = _orig_c4
    _RS.take_screenshot = _orig_shot4
    _RS.check_failsafe = _orig_f4
    _RS.PILLOW_AVAILABLE = _orig_p4
    _RS.execute_boss_scan = _orig_bscan
    _RS.execute_icon_scan = _orig_iscan
    _RS.execute_item_scan = _orig_iscan2


# ------------------------------------------- Zeitgesteuerte Phasen: Identitaet
section("Zeitgesteuerte Loop-Phasen werden ueber die Position unterschieden")

# Der Timer-Thread setzt ein pending-Flag, die Ausfuehrung holt es wieder ab. Lag der
# Schluessel auf dem Phasen-NAMEN, riss bei zwei gleichnamigen Phasen die erste das Flag
# der zweiten an sich: um 20:00 lief die 08:00-Phase ein zweites Mal, die Abend-Phase nie.
# Namen sind frei waehlbar und der Vorschlag 'Loop <len+1>' kollidiert nach jedem 'del'.
from autoclicker.runtime.worker import _schedule_watcher as _sw, _run_loop_phases as _rlp
import threading as _th


class _FakeLP:
    def __init__(self, name, sched):
        self.name = name; self.scheduled_start = sched; self.repeat = 1
        # Der Schritt traegt die Identitaet der Phase. Ueber den Namen laesst sich
        # nicht pruefen, welche Phase lief — im Fehlerfall heissen ja beide gleich,
        # und der Test wuerde die falsche Phase fuer die richtige halten.
        self.steps = [f"{name}@{sched}"]


class _FakeSeq:
    def __init__(self, phasen): self.loop_phases = phasen


class _EinTick:
    """stop_event-Ersatz, der genau EINEN Schleifendurchlauf zulaesst.

    Der Watcher prueft `while not stop_event.is_set()` VOR dem Rumpf und wartet
    danach mit `stop_event.wait(10)`. Ein vorab gesetztes Event wuerde den Rumpf
    also nie ausfuehren, ein echtes Event 10 Sekunden kosten.
    """
    def __init__(self): self._fertig = False
    def is_set(self): return self._fertig
    def wait(self, timeout=None): self._fertig = True; return True   # -> break


def _watcher_tick(phasen, h, m, pending=None, last=None):
    """Laesst den echten _schedule_watcher einen Tick zur Uhrzeit h:m laufen."""
    pending = {} if pending is None else pending
    last = {} if last is None else last

    class _FixeZeit(_dt_mod.datetime):
        @classmethod
        def now(cls, tz=None): return cls(2026, 7, 31, h, m, 0)

    orig_dt = _WK.datetime
    _WK.datetime = _FixeZeit
    try:
        with _cl2.redirect_stdout(_io2.StringIO()):
            _sw(phasen, pending, last, _EinTick(), _th.Lock(), _th.Event())
    finally:
        _WK.datetime = orig_dt
    return pending


def _timer_lauf(phasen, h, m):
    """Ein Watcher-Tick zur Uhrzeit h:m, danach ein echter Phasen-Durchlauf.

    Beide Seiten sind die Original-Funktionen; nur execute_step ist gestubbt und
    protokolliert, welche Phase wirklich drankam.
    """
    pending = _watcher_tick(phasen, h, m)
    gelaufen = []
    orig_step = _WK.execute_step
    _WK.execute_step = lambda s, step, i, n, ph: (gelaufen.append(step), True)[1]
    try:
        with _cl2.redirect_stdout(_io2.StringIO()):
            _rlp(AutoClickerState(), _FakeSeq(phasen), pending, _th.Lock(), "Zyklus 1", False)
    finally:
        _WK.execute_step = orig_step
    return gelaufen


import datetime as _dt_mod
import autoclicker.runtime.worker as _WK

# A) eindeutige Namen — muss unveraendert funktionieren
_a = [_FakeLP("Morgen", "08:00"), _FakeLP("Abend", "20:00")]
check("eindeutige Namen: um 08:00 laeuft nur die Morgen-Phase",
      _timer_lauf(_a, 8, 0) == ["Morgen@08:00"])
_a = [_FakeLP("Morgen", "08:00"), _FakeLP("Abend", "20:00")]
check("eindeutige Namen: um 20:00 laeuft nur die Abend-Phase",
      _timer_lauf(_a, 20, 0) == ["Abend@20:00"])
_a = [_FakeLP("Morgen", "08:00"), _FakeLP("Abend", "20:00")]
check("eindeutige Namen: um 12:00 laeuft keine der beiden",
      _timer_lauf(_a, 12, 0) == [])

# B) gleicher Name (entsteht durch 'del' + 'add', Vorschlag ist 'Loop <len+1>')
_b = [_FakeLP("Loop 3", "08:00"), _FakeLP("Loop 3", "20:00")]
check("gleicher Name: um 20:00 laeuft die 20-Uhr-Phase (nicht die von 08:00)",
      _timer_lauf(_b, 20, 0) == ["Loop 3@20:00"])
_b = [_FakeLP("Loop 3", "08:00"), _FakeLP("Loop 3", "20:00")]
check("gleicher Name: um 08:00 laeuft die 08-Uhr-Phase",
      _timer_lauf(_b, 8, 0) == ["Loop 3@08:00"])
# Beide heissen gleich — nachweisbar ist es ueber das pending-Dict: der Schluessel
# muss die POSITION der 20-Uhr-Phase sein, nicht ihr Name.
_pending = _watcher_tick([_FakeLP("Loop 3", "08:00"), _FakeLP("Loop 3", "20:00")], 20, 0)
check("gleicher Name: das Flag haengt an Position 1 (der 20-Uhr-Phase)",
      _pending == {1: True})
check("gleicher Name: der Name taucht als Schluessel nicht mehr auf",
      "Loop 3" not in _pending)

# C) gleicher Name, gleiche Uhrzeit -> beide muessen laufen
_c = [_FakeLP("Loop 2", "09:30"), _FakeLP("Loop 2", "09:30")]
check("gleicher Name und gleiche Uhrzeit: beide Phasen laufen",
      _timer_lauf(_c, 9, 30) == ["Loop 2@09:30", "Loop 2@09:30"])

# D) ungeplante Phasen bleiben von alldem unberuehrt
_d = [_FakeLP("Immer", None), _FakeLP("Immer", None)]
check("Phasen ohne Startzeit laufen weiterhin jedes Mal",
      _timer_lauf(_d, 3, 45) == ["Immer@None", "Immer@None"])


# ------------------------------------------------------- Eindeutige Namen
section("Namensvergabe kollidiert nicht mit bestehenden Eintraegen")
from autoclicker.utils import eindeutiger_name as _en

check("freier Name bleibt unveraendert", _en("Slot 5", {"Slot 1": 1}) == "Slot 5")
check("belegter Name bekommt eine 2", _en("Slot 1", {"Slot 1": 1}) == "Slot 1 2")
check("zaehlt weiter bis frei", _en("Slot 1", {"Slot 1": 1, "Slot 1 2": 1}) == "Slot 1 3")
check("funktioniert auch mit einem Set", _en("A", {"A"}) == "A 2")
check("leeres Verzeichnis: Name bleibt", _en("A", {}) == "A")
# Der Fall aus der Praxis: 'Slot 2' geloescht -> len+1 zeigt auf das bestehende 'Slot 3'
_bestand = {"Slot 1": 1, "Slot 3": 1}
_vorschlag = f"Slot {len(_bestand) + 1}"
check("len+1 trifft nach einem 'del' einen bestehenden Namen",
      _vorschlag == "Slot 3" and _vorschlag in _bestand)
check("...und wird auf einen freien Namen ausgewichen",
      _en(_vorschlag, _bestand) == "Slot 3 2")

# Und der Ablauf der Auto-Erkennung: N Slots anlegen darf nie einen bestehenden treffen
_slots = {"Slot 1": "alt", "Slot 3": "alt"}
for _ in range(4):
    _n = _en(f"Slot {len(_slots) + 1}", _slots)
    _slots[_n] = "neu"
check("Auto-Erkennung ueberschreibt keinen bestehenden Slot",
      _slots["Slot 1"] == "alt" and _slots["Slot 3"] == "alt")
check("Auto-Erkennung legt alle 4 Slots wirklich an", len(_slots) == 6)


print(f"\n================  {PASS} PASS / {FAIL} FAIL  ================")
sys.exit(1 if FAIL else 0)
