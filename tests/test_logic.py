"""Logik-/Daten-Schicht-Tests — laufen ohne GUI/LLM, plattformunabhängig.

Aufruf:  python tests/test_logic.py   (Exit 0 = alle grün)

Prüft Serialisierung/Persistenz, Backward-Compat, Farb-/Parsing-Helfer und
das Export-Format. Auf Linux/Mac wird msvcrt gestubbt (auf Windows nicht —
da ist es echt vorhanden), damit der Import der utils nicht scheitert.
"""
import sys, types, json, tempfile
from pathlib import Path

# Der dokumentierte Direktaufruf muss auch unter Windows-Codepages wie cp1252
# funktionieren: die Tests geben bewusst Unicode-Symbole aus.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

# MUSS vor dem msvcrt-Stub geladen werden: `subprocess` erkennt Windows daran,
# dass sich msvcrt importieren laesst, und zieht dann `_winapi` nach - das es
# auf Linux nicht gibt. Wer danach etwas importiert, das subprocess braucht
# (z.B. PIL.ImageGrab), bekommt einen ModuleNotFoundError und haelt Pillow
# faelschlich fuer nicht installiert. Genau daran lief der Bild-Teil der
# Scan-Tests ins Leere.
import subprocess  # noqa: F401

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

# **Zaehler und Ausgabe leben im Harness, nicht hier.** Sonst zaehlte jedes
# ausgelagerte Modul fuer sich, und die Schlusszeile saehe nur den letzten Stand.
# Die Stubs oben stehen trotzdem in dieser Datei: sie muessen VOR dem ersten
# autoclicker-Import sitzen, und der kommt gleich.
import tests.contract._harness as _H     # noqa: E402
from tests.contract._harness import check, section     # noqa: E402

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

slot = ItemSlot(name="Slot 1", scan_region=(10, 20, 110, 120), click_pos=(60, 70),
                slot_color=(30, 40, 50), enabled=False)
item = ItemProfile(name="Schwert", marker_colors=[(200, 30, 30)], category="Waffe", priority=2,
                   confirm_point=ClickPoint(5, 6), confirm_delay=0.7, template="schwert.png", min_confidence=0.85)
isc = ItemScanConfig(name="MyScan", slots=[slot], items=[item], color_tolerance=42, learn_unknown=True)
r = roundtrip(_item_scan_to_dict, load_item_scan_file, isc)
check("ItemScan name/tol/learn_unknown", r.name == "MyScan" and r.color_tolerance == 42 and r.learn_unknown is True)
# Ein Item-Scan ist eigenständig: gleichnamige Einträge anderer Scans sind
# andere Objekte und dürfen ihn nicht verändern.
check("ItemScan speichert vollständige Slots", r.slot_names == ["Slot 1"]
      and r.slots[0].scan_region == (10, 20, 110, 120))
check("ein ausgeschalteter Slot überlebt den Datei-Zyklus",
      r.slots[0].enabled is False)
check("aktiv ist der alte Standard und wird nicht extra geschrieben",
      "enabled" not in _item_scan_to_dict(ItemScanConfig(
          name="Standard", slots=[ItemSlot("S", (0, 0, 10, 10), (5, 5))]))["slots"]["S"])
check("ItemScan speichert vollständige Items", r.item_names == ["Schwert"]
      and r.items[0].template == "schwert.png")
check("ItemScan lädt eigene Objekte", r.slots and r.items)

# --- Die Scan-Richtung gehoert zum Scan, nicht zum Programm ---
# Sie stand als `config.scan_reverse` in der Config und galt damit fuer ALLE
# Scans - die Richtung haengt aber am Inventar: wer ein Spiel von hinten leert
# und ein zweites von vorn, hatte die Wahl zwischen zwei falschen Laeufen.
check("aus ist der Normalfall", isc.reverse is False)
check("aus wird nicht geschrieben",
      "reverse" not in _item_scan_to_dict(ItemScanConfig(name="X")))
check("an ueberlebt den Roundtrip",
      roundtrip(_item_scan_to_dict, load_item_scan_file,
                ItemScanConfig(name="X", reverse=True)).reverse is True)

# Und die globale Einstellung ist WEG, nicht bloss unbenutzt. Ein Feld, das
# niemand mehr liest, aber weiter in der config.json steht, ist genau die
# Altlast, die dieses Projekt nicht mitschleppt.
from autoclicker.config import AppConfig as _ACrev
check("scan_reverse gibt es in der Config nicht mehr",
      not hasattr(_ACrev(), "scan_reverse"))
_rev_tree = [p for p in (Path(__file__).resolve().parent.parent
                         / "autoclicker").rglob("*.py")]
_rev_hits = [f"{p.name}:{i+1}" for p in _rev_tree
                for i, z in enumerate(p.read_text(encoding="utf-8").splitlines())
                if "scan_reverse" in z and not z.strip().startswith("#")]
check(f"und kommt im Code nicht mehr vor ({_rev_hits or 'nirgends'})",
      not _rev_hits)

# `edit_item_scan` BAUT die Config neu auf, statt die vorhandene zu aendern -
# ein vergessenes Feld ist beim Bearbeiten eines bestehenden Scans still weg.
# Genau das waere `reverse` beinahe passiert. Abgeleitete Felder gehoeren nicht
# in die Liste: `slot_names`/`item_names` sind Properties ueber den Objekten.
import ast as _ast_rev, dataclasses as _dc_rev
_src_rev = _ast_rev.parse((Path(__file__).resolve().parent.parent / "autoclicker"
                           / "editors" / "item_scan_editor.py").read_text(encoding="utf-8"))
_fn_rev = next(n for n in _ast_rev.walk(_src_rev)
               if isinstance(n, _ast_rev.FunctionDef) and n.name == "edit_item_scan")
_build_rev = [n for n in _ast_rev.walk(_fn_rev) if isinstance(n, _ast_rev.Call)
            and getattr(n.func, "id", "") == "ItemScanConfig"]
check("edit_item_scan baut genau eine Config", len(_build_rev) == 1)
_handed_over = {k.arg for k in _build_rev[0].keywords}
_expected = {f.name for f in _dc_rev.fields(ItemScanConfig)} - {"slot_names", "item_names"}
check(f"und uebergibt jedes Feld der Dataclass (fehlt: "
      f"{sorted(_expected - _handed_over) or 'nichts'})", _handed_over == _expected)

boss = BossProfile(name="Drache", marker_colors=[(10, 20, 30)], template="drache.png", min_confidence=0.9,
                   action="click", action_point_id=4, action_delay=1.5)
bsc = BossScanConfig(name="BScan", scan_region=(1, 2, 3, 4), bosses=[boss], color_tolerance=33,
                     default_action="skip", use_llm=True, llm_fallback=False, use_ocr=True, ocr_fallback=False)
r = roundtrip(_boss_scan_to_dict, load_boss_scan_file, bsc)
check("BossScan flags (llm/ocr)", r.use_llm and not r.llm_fallback and r.use_ocr and not r.ocr_fallback)
check("BossScan region/tol/default", r.scan_region == (1, 2, 3, 4) and r.color_tolerance == 33 and r.default_action == "skip")
# Das Klick-Ziel ist eine Punkt-ID; action_x/y sind abgeleitet und stehen nicht in der
# Datei - gefuellt werden sie von resolve_click_references(), s. eigener Abschnitt.
check("BossScan boss action", r.bosses[0].name == "Drache" and r.bosses[0].action == "click" and r.bosses[0].action_point_id == 4)
check("BossScan speichert keine Klick-Koordinate",
      "action_x" not in _boss_scan_to_dict(bsc)["bosses"][0])

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
section("item_scans: altes Listenformat wird sicher abgelehnt")
mixed = {"name": "S", "slots": [
    {"name": "ok", "scan_region": [0, 0, 5, 5], "click_pos": [2, 2]},
    {"name": "kaputt"}],  # unvollstaendig - der Name genuegt jetzt trotzdem
    "items": [{"name": "Schwert", "marker_colors": []}]}
pm = tmp / "mixed.json"; pm.write_text(json.dumps(mixed), encoding="utf-8")
rm = load_item_scan_file(pm)
check("Altformat-Scan crasht nicht", rm is None)

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
         (245, 245, 245): "Weiss", (255, 165, 0): "Orange", (139, 69, 19): "Braun"}
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
section("export_bundle: Sequenzordner bleibt als Besitzeinheit zusammen")
import zipfile
from autoclicker.models import AutoClickerState
st = AutoClickerState()
from autoclicker.import_export import export_bundle, read_manifest
import os as _os_bundle
_bundle_old = Path.cwd()
_bundle_root = tmp / "new_layout"
(_bundle_root / "sequences" / "Test" / "item_scans").mkdir(parents=True)
_seq_json = {"name": "Test", "points": [_point_to_dict(
    ClickPoint(1, 2, "P1", 1, color=(3, 4, 5), source="Aufnahme 'A'"))],
    "init_steps": [], "loop_phases": [], "end_steps": []}
(_bundle_root / "sequences" / "Test" / "sequence.json").write_text(
    compact_json(_seq_json), encoding="utf-8")
(_bundle_root / "sequences" / "Test" / "item_scans" / "MyScan.json").write_text(
    compact_json(_item_scan_to_dict(isc)), encoding="utf-8")
zpath = str(tmp / "bundle.zip")
_os_bundle.chdir(_bundle_root)
try:
    ok_exp, msg = export_bundle(st, zpath, (0, 0), (100, 100),
                                include_config=False)
finally:
    _os_bundle.chdir(_bundle_old)
check("export_bundle Erfolg", ok_exp is True)
with zipfile.ZipFile(zpath) as zf:
    names = zf.namelist()
    iname = "sequences/Test/item_scans/MyScan.json"
    check("Punkte liegen in sequence.json", "sequences/Test/sequence.json" in names)
    check("Item-Scan liegt unter seiner Sequenz", iname in names)
    iscan_json = json.loads(zf.read(iname))
    check("Export-Item-Scan == save-Format", iscan_json == json.loads(compact_json(_item_scan_to_dict(isc))))
    seq_export = json.loads(zf.read("sequences/Test/sequence.json"))
    check("Export-Punkt bleibt in seiner Sequenz", seq_export["points"][0] == _seq_json["points"][0])
ok_man, man = read_manifest(zpath)
check("read_manifest OK", ok_man and man.get("layout") == "sequence-folders")

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

# ------------------------------------------------- Einmal-Farbpruefung
section("Farbpruefung ohne Warten")
from autoclicker.models import SequenceStep, WaitCondition
from autoclicker.persistence.serialization import _step_to_dict, _parse_steps

_check = SequenceStep(x=30, y=40, delay_before=0, name="farbcheck",
                      wait_condition=WaitCondition(pixel=(5, 6), color=(1, 2, 3),
                                                   check_only=True, until_gone=True))
_back = _parse_steps([_step_to_dict(_check)])
check("check_only ueberlebt Round-Trip", _back[0].wait_condition.check_only is True)
check("until_gone ueberlebt Round-Trip", _back[0].wait_condition.until_gone is True)

_old = _parse_steps([{"x": 1, "y": 2, "delay_before": 1, "name": "alt"}])
check("alte Schritte ohne neue Keys: keine WaitCondition", _old[0].wait_condition is None)
# Das Mausrad ist ersatzlos gestrichen. Ein `"scroll"` in einer alten Datei ist ein
# unbekannter Schluessel wie jeder andere: der Loader ignoriert ihn, der Schritt
# wird zum Klick auf seinen Punkt — und ein Modell-Feld dafuer gibt es nicht mehr.
_old_scroll = _parse_steps([{"point_id": 3, "delay_before": 0, "scroll": -3}])
check("ein altes 'scroll'-Feld faellt still weg", not hasattr(_old_scroll[0], "scroll")
      and _old_scroll[0].point_id == 3 and "scroll" not in _step_to_dict(_old_scroll[0]))
_old_color = _parse_steps([{"x": 1, "y": 2, "delay_before": 0, "wait_pixel": [3, 4],
                            "wait_color": [5, 6, 7]}])
check("alter Farb-Trigger bleibt Warten (check_only=False)",
      _old_color[0].wait_condition.check_only is False)

_check_text = str(SequenceStep(
    x=1, y=2, delay_before=0,
    wait_condition=WaitCondition(pixel=(1, 2), color=(3, 4, 5), check_only=True)))
check("Einmal-Pruefung wird als 'prüfe einmal' angezeigt", "prüfe einmal" in _check_text)
check("Einmal-Pruefung nennt den Standard-Fallback", "überspringen" in _check_text)

# ------------------------------------------------------------- Debug-Modi
section("Debug-Modi: getrennte Flags, alte Keys fallen weg")
from autoclicker.config import AppConfig

# `_FIELD_MIGRATION` (clicks_per_point -> click_per_point, debug_mode -> debug_detail
# usw.) ist geloescht: der Start-Durchgang schreibt config.json laengst im aktuellen
# Format, die Tabelle war nach dem ersten Start wirkungslos. Ein alter Schluessel ist
# heute ein unbekannter — er faellt weg, das Feld bekommt seinen Default.
_c = AppConfig.from_dict({"debug_detection": True, "debug_mode": True, "debug_step": True})
check("alte Debug-Schluessel werden nicht mehr uebersetzt, sondern ignoriert",
      _c.debug_log is False and _c.debug_detail is False)
check("und es gibt keine Uebersetzungstabelle mehr", not hasattr(AppConfig, "_FIELD_MIGRATION"))

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
_detail_independent = True
_rows_ok = True
for _l, _d in ((True, False), (False, True), (True, True), (False, False)):
    _st.config.debug_log, _st.config.debug_detail, _st.step_mode = _l, _d, False
    if _dbg.is_detail_debug(_st) is not _d or _dbg.skip_waits(_st) is not False:
        _detail_independent = False
    if _dbg.is_log_debug(_st) is not (_l or _d):
        _rows_ok = False
check("Detail-Stufe haengt nur an ihrem eigenen Flag", _detail_independent)
check("Detail-Stufe erzwingt echte Zeilen statt Ueberschreiben", _rows_ok)

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
_orig_read_key = _dbg.read_command
_results = {}
for _key in ("w", "enter", "s", "q", "c"):
    _st.step_mode = True
    _st.stop_event.clear()
    # `read_command` nimmt seit dem Haltepunkt eine Zeitgrenze entgegen — der
    # Stub muss sie schlucken, sonst misst der Test die Signatur statt das Gate.
    _dbg.read_command = (lambda *a, _t=_key, **k: _t)
    _results[_key] = _dbg.step_gate(_st, _step, "LOOP", 1, 3)
_dbg.read_command = _orig_read_key
check("Gate: 'w' fuehrt aus", _results["w"] == _dbg.GATE_RUN)
check("Gate: Enter fuehrt aus", _results["enter"] == _dbg.GATE_RUN)
check("Gate: 's' ueberspringt", _results["s"] == _dbg.GATE_SKIP)
check("Gate: 'q' bricht ab", _results["q"] == _dbg.GATE_STOP)
check("Gate: 'c' laeuft weiter UND schaltet den Modus aus",
      _results["c"] == _dbg.GATE_RUN and _st.step_mode is False)

# Studio-Entscheidung: der Worker liest dann ausdrücklich NICHT aus stdin.
import threading as _threading_step
import time as _time_step
import autoclicker.runtime.status as _status_step
_st.step_mode = True
_st.step_via_studio = True
_st.stop_event.clear()
_studio_result = {}
_studio_thread = _threading_step.Thread(
    target=lambda: _studio_result.setdefault(
        "value", _dbg.step_gate(_st, _step, "LOOP", 2, 3)))
_studio_thread.start()
_deadline = _time_step.time() + 1.0
while not (_status_step._state.get("manual")) and _time_step.time() < _deadline:
    _time_step.sleep(0.01)
with _st.lock:
    _st.step_command = "skip"
    _st.step_command_event.set()
_studio_thread.join(1.0)
check("Studio-Gate wartet auf den sichtbaren Befehl",
      _studio_result.get("value") == _dbg.GATE_SKIP)
check("und räumt die sichtbare Rückfrage danach weg",
      _status_step._state.get("manual") is None)
_st.step_via_studio = False
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


def _detail_rows(step):
    buf = _io.StringIO()
    with _ctx.redirect_stdout(buf):
        _dbg.print_step_detail(_st, step, "LOOP", 15, 67)
    return [z for z in buf.getvalue().splitlines() if z.strip()]


_lines = _detail_rows(SequenceStep(x=10, y=20, delay_before=0, name="Klick 15"))
check("Detail: Klick-Schritt belegt genau eine Zeile", len(_lines) == 1)
check("Detail: Zeile nennt Schritt, Name und Ziel",
      "15/67" in _lines[0] and "Klick 15" in _lines[0] and "(10, 20)" in _lines[0])

# Nur wo es wirklich mehr zu sagen gibt, kommen Zusatzzeilen dazu
_rows_color = _detail_rows(SequenceStep(
    x=10, y=20, delay_before=0, name="Farbschritt",
    wait_condition=_WC(pixel=(77, 88), color=(10, 20, 30))))
check("Detail: Farb-Bedingung ergaenzt Zeilen", len(_rows_color) > 1)
check("Detail: Farb-Bedingung nennt den Pruef-Pixel",
      any("77" in z and "88" in z for z in _rows_color))
_st.config.debug_detail = False

# ---------------------------------------- Punkt-Referenzen (verrutschtes Fenster)
section("Punkt-Referenzen: Schritte folgen dem Punkte-Pool")
from autoclicker.models import Sequence as _Seq, LoopPhase as _LP, ClickPoint as _CP
from autoclicker.persistence.sequences import resolve_point_references as _resolve
from autoclicker.runtime.debug import step_label as _label

_st2 = AutoClickerState()
_st2.points = [_CP(x=100, y=200, name="Marktbutton", id=3, color=(1, 2, 3)),
               _CP(x=300, y=400, name="Verkaufen", id=7),
               _CP(x=500, y=600, name="Bestaetigen", id=9),
               _CP(x=999, y=999, name="Ladebalken", id=11, color=(4, 5, 6))]
_seq = _Seq(name="Verkauf", loop_phases=[_LP(name="LOOP", steps=[
    # Klick + Pruef-Pixel AN DERSELBEN Stelle: eine ID, zwei Verwendungen
    SequenceStep(delay_before=0, point_id=3, wait_condition=_WC(point_id=3)),
    # Klick hier, geprueft wird woanders: zwei verschiedene Punkte
    SequenceStep(delay_before=0, point_id=7, wait_condition=_WC(point_id=11)),
    SequenceStep(delay_before=0, key_press="enter"),         # ohne Stelle
    SequenceStep(delay_before=0, point_id=42),               # verwaist
])], points=_st2.points)
_st2.active_sequence = _seq

# Fenster war beim Aufnehmen um (+8,+5) verschoben -> Punkte korrigiert
for _p in _st2.points:
    _p.x += 8
    _p.y += 5
_messages = _resolve(_st2, _seq)
_s = _seq.loop_phases[0].steps

check("verknuepfter Schritt folgt dem Punkt", (_s[0].x, _s[0].y) == (108, 205))
check("Name kommt aus dem Punkt", _s[0].name == "Marktbutton")
check("recorded_color kommt aus dem Punkt", _s[0].recorded_color == (1, 2, 3))
# Der Pruef-Pixel ist eine eigene Referenz - er zieht nicht mit dem Klick mit, sondern
# mit SEINEM Punkt. Zeigen beide auf denselben, ist das Ergebnis dasselbe wie frueher;
# der Unterschied ist, dass es jetzt in der Datei steht statt geraten zu werden.
check("Pruef-Pixel am selben Punkt landet auf derselben Stelle",
      tuple(_s[0].wait_condition.pixel) == (108, 205))
check("Pruef-Pixel holt seine Farbe aus seinem Punkt",
      tuple(_s[0].wait_condition.color) == (1, 2, 3))
check("Pruef-Pixel an eigenem Punkt folgt DIESEM Punkt",
      tuple(_s[1].wait_condition.pixel) == (1007, 1004))
check("Schritt ohne Stelle bleibt bei (0, 0)", (_s[2].x, _s[2].y) == (0, 0))
check("verwaiste Referenz wird gemeldet",
      any("#42" in m and "nicht mehr gibt" in m for m in _messages))

# Der Kern der Umstellung: eine tote Referenz hat KEINE Rueckfall-Koordinate mehr.
# Frueher blieb der Schritt auf seinem alten x/y stehen und klickte dorthin - also auf
# eine Stelle, deren Punkt jemand bewusst geloescht hatte.
check("verwaiste Referenz klickt nicht ersatzweise irgendwohin",
      (_s[3].x, _s[3].y) == (0, 0))
check("verwaiste Referenz ist als unresolved markiert", _s[3].unresolved is True)
check("aufgeloester Schritt ist NICHT unresolved", _s[0].unresolved is False)

# Zweiter Lauf: keine Verschiebungen mehr, aber die verwaiste Referenz nervt weiter
_second = _resolve(_st2, _seq)
check("zweiter Lauf meldet keine Verschiebung mehr",
      not any("->" in m for m in _second))
check("verwaiste Referenz wird dauerhaft gemeldet", len(_second) == 1)

# Der verwaiste Schritt darf die Sequenz weder abbrechen noch irgendwohin klicken.
# Gegenprobe zum Fix: ohne die unresolved-Abfrage in step_gate liefert das GATE_RUN,
# und _s[3] klickt mit seinen aufgeloesten (0, 0) in die Bildschirmecke.
from autoclicker.runtime.debug import (step_gate as _gate, GATE_SKIP as _G_SKIP,
                                       GATE_RUN as _G_RUN, target_of as _target)
_st2.step_mode = False
check("verwaister Schritt wird zur Laufzeit uebersprungen",
      _gate(_st2, _s[3], "LOOP", 4, 4) == _G_SKIP)
check("ein aufgeloester Schritt laeuft normal", _gate(_st2, _s[0], "LOOP", 1, 4) == _G_RUN)
check("verwaister Schritt hat kein Ziel fuer den Zeiger", _target(_s[3]) is None)

check("Label nennt die Punkt-ID", "#3" in _label(_s[0]))
check("Label sagt klar, wenn es gar keine Stelle gibt", "ohne Stelle" in _label(_s[2]))
check("Label nennt einen fehlenden Punkt beim Namen", "FEHLT" in _label(_s[3]))

# Serialisierung der Referenz
_rt = _parse_steps([_step_to_dict(_s[0])])
check("point_id ueberlebt Round-Trip", _rt[0].point_id == 3)
check("wait_point_id ueberlebt Round-Trip", _rt[0].wait_condition.point_id == 3)
check("alte Schritte ohne point_id -> None",
      _parse_steps([{"x": 1, "y": 2, "delay_before": 0}])[0].point_id is None)

# DIE Invariante der Umstellung: in einer gespeicherten Sequenz steht keine Koordinate.
# Sie hier gegen den Serializer zu pruefen ist der Zweck der ganzen Uebung - faellt sie,
# ist eine Kopie zurueck, und die naechste Kalibrierung erwischt sie nicht.
_KOORD_KEYS = ("x", "y", "wait_pixel", "wait_color", "else_x", "else_y",
               "recorded_color", "name", "else_name")
_saved = [_step_to_dict(st) for st in _s]
check("kein Schritt MIT Punkt speichert noch eine Koordinate",
      all(not any(k in d for k in _KOORD_KEYS)
          for d, st in zip(_saved, _s) if st.point_id is not None))
check("die ID wird stattdessen gespeichert",
      all("point_id" in d for d, st in zip(_saved, _s) if st.point_id is not None))
check("auch der Pruef-Pixel speichert nur seine ID",
      _saved[1].get("wait_point_id") == 11
      and "wait_pixel" not in _saved[1])

# --------------------------------- Klick-Ziele ausserhalb der Sequenzen
section("Punkt-Referenzen: auch Bestaetigung, Boss- und Icon-Aktion")

# Dieselbe Regel wie bei den Schritten, nur an drei anderen Stellen. Der Item-Editor
# fragt ohnehin nach einer Punkt-ID - frueher wurde sie weggeworfen und durch eine
# Koordinaten-Kopie ersetzt, sodass ein verschobener Punkt den Bestaetigungsklick
# stehenliess. Boss- und Icon-Klick hingen an gar keinem Punkt.
from autoclicker.models import (ItemProfile as _IP, BossScanConfig as _BSC2,
                                IconScanConfig as _ISC2)
from autoclicker.persistence import resolve_click_references as _rkr
from autoclicker.persistence.serialization import _item_to_dict

_st5 = AutoClickerState()
_st5.points = [_CP(x=10, y=20, name="Popup-OK", id=1),
               _CP(x=30, y=40, name="Boss-Angriff", id=2),
               _CP(x=50, y=60, name="Icon-Weg", id=3)]
_seq5 = _Seq(name="Scanfolge", points=_st5.points)
_st5.active_sequence = _seq5
_items5 = {"Kohle": _IP(name="Kohle", confirm_point_id=1),
           "Erz": _IP(name="Erz"),
           "Tot": _IP(name="Tot", confirm_point_id=99)}
_st5.global_items = _items5
_st5.item_scans = {"Inventar": ItemScanConfig(
    name="Inventar", items=list(_items5.values()), owner_sequence="Scanfolge")}
_st5.global_bosses = [BossProfile(name="Drache", action="click", action_point_id=2)]
_ic5 = _ISC2(name="I", action="click", action_point_id=3)
_st5.icon_scans = {"I": _ic5}
_report5 = _rkr(_st5)

check("Bestaetigungsklick kommt aus dem Punkt",
      (_st5.global_items["Kohle"].confirm_point.x,
       _st5.global_items["Kohle"].confirm_point.y) == (10, 20))
check("Item ohne Referenz hat keinen Bestaetigungsklick",
      _st5.global_items["Erz"].confirm_point is None)
check("Boss-Klick kommt aus dem Punkt",
      (_st5.global_bosses[0].action_x, _st5.global_bosses[0].action_y) == (30, 40))
check("Icon-Klick kommt aus dem Punkt", (_ic5.action_x, _ic5.action_y) == (50, 60))

# Punkt verschieben -> alle drei ziehen mit. Das ist der ganze Zweck.
for _p in _st5.points:
    _p.x += 7
    _p.y += 9
_rkr(_st5)
check("verschobener Punkt zieht den Bestaetigungsklick mit",
      (_st5.global_items["Kohle"].confirm_point.x,
       _st5.global_items["Kohle"].confirm_point.y) == (17, 29))
check("verschobener Punkt zieht den Boss-Klick mit",
      (_st5.global_bosses[0].action_x, _st5.global_bosses[0].action_y) == (37, 49))
check("verschobener Punkt zieht den Icon-Klick mit",
      (_ic5.action_x, _ic5.action_y) == (57, 69))

check("tote Referenz wird gemeldet",
      any("#99" in m and "nicht mehr gibt" in m for m in _report5))
check("tote Referenz laesst den Klick weg statt auf (0,0) zu zielen",
      _st5.global_items["Tot"].confirm_point is None)

# Boss-Profile INNERHALB eines Scans zaehlen mit, nicht nur die globalen
_bp6 = BossProfile(name="Lokal", action="click", action_point_id=1)
_st5.boss_scans = {"B": _BSC2(name="B", bosses=[_bp6])}
_rkr(_st5)
check("auch Bosse in einem Scan werden aufgeloest", (_bp6.action_x, _bp6.action_y) == (17, 29))

# Und die Datei traegt nur die ID
check("gespeichert wird nur die Referenz",
      "confirm_point" not in _item_to_dict(_st5.global_items["Kohle"])
      and _item_to_dict(_st5.global_items["Kohle"]).get("confirm_point_id") == 1)
check("Icon-Scan speichert keine Klick-Koordinate",
      "action_x" not in _icon_scan_to_dict(_ic5)
      and _icon_scan_to_dict(_ic5).get("action_point_id") == 3)


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

# --- Die Sequenz-Kette ist LEER, und das ist der Zielzustand ---
# Hier standen vier Schritte (Schema 0 bis 4) und die Tests dazu. Sie sind mit den
# Schritten geloescht: es gibt keinen Altbestand mehr, den sie heben koennten. Was
# bleibt, ist die MECHANIK - Versionserkennung, Stempel, die Schleuse im Loader -,
# denn die kostet nichts und ist die Stelle, an der eine kuenftige Umstellung landet.
from autoclicker.persistence.migration import _CHAINS as _KETTEN
check("die Sequenz-Kette ist leer", _KETTEN[KIND_SEQUENCE] == [])
check("der Eintrag bleibt trotzdem stehen (die Schleuse sitzt)",
      KIND_SEQUENCE in _KETTEN)

# **Eine Altdatei wird gestempelt, nicht umgerechnet.** Das ist die bewusst
# akzeptierte Folge: ohne Schritte kann niemand `steps` in `loop_phases` heben. Der
# Loader stuerzt deswegen NICHT ab - er liest mit `data.get(key, default)` und
# bekommt eine leere Sequenz. Dieser Test haelt genau das fest, statt zu schweigen:
# wer eine sehr alte Sicherung einspielt, soll das Ergebnis hier nachlesen koennen.
_ancient = {"name": "U", "steps": [
    {"x": 100, "y": 200, "name": "Markt", "delay_before": 1}]}
_d, _m = migrate(_ancient, KIND_SEQUENCE)
check("eine Altdatei bekommt den Versions-Stempel", _d["schema_version"] == SCHEMA_VERSION)
check("und sie wird nicht mehr umgerechnet", _m == [] and "loop_phases" not in _d)

# Idempotenz: zweiter Lauf aendert nichts mehr
import copy as _copy
_before = _copy.deepcopy(_d)
_d3, _m3 = migrate(_d, KIND_SEQUENCE)
check("zweiter Migrationslauf meldet nichts", _m3 == [])
check("zweiter Migrationslauf aendert nichts", _d3 == _before)

# Neuere Schema-Version wird nicht heruntergerechnet
_newer = {"name": "Z", "schema_version": SCHEMA_VERSION + 5, "loop_phases": []}
_d4, _m4 = migrate(_newer, KIND_SEQUENCE, {})
check("neuere Version wird nicht angefasst", _d4["schema_version"] == SCHEMA_VERSION + 5)
check("neuere Version wird gemeldet", any("kennt nur" in m for m in _m4))

# Der Loader ueberlebt eine Altdatei - er liefert eine leere Sequenz statt zu werfen.
# Eine Datei, die den Loader wirft, waere ein Fehler; eine, die auf Standardwerten
# landet, ist es nicht (siehe die Persistenz-Regeln in CLAUDE.md).
_mp = tmp / "altformat.json"
_mp.write_text(json.dumps({"name": "Alt", "steps": [
    {"x": 100, "y": 200, "name": "Markt", "delay_before": 0}]}), encoding="utf-8")
_seq_old = _load_seq(_mp)
check("der Loader wirft bei einer Altdatei nicht", _seq_old is not None)
check("sie kommt leer an, statt halb geraten", _seq_old is not None
      and _seq_old.loop_phases == [] and _seq_old.init_steps == [])

# Gegenprobe: eine AKTUELLE Datei laedt vollstaendig - der Loader ist in Ordnung,
# es fehlt der Altdatei nur der Weg hierher.
_mp4 = tmp / "aktuell.json"
_mp4.write_text(json.dumps({
    "name": "Aktuell", "schema_version": SCHEMA_VERSION, "total_cycles": 1,
    "points": [{"id": 3, "x": 100, "y": 200, "name": "Markt"}],
    "init_steps": [], "end_steps": [],
    "loop_phases": [{"name": "Loop", "repeat": 1,
                     "steps": [{"point_id": 3, "delay_before": 0}]}]}), encoding="utf-8")
_seq_new = _load_seq(_mp4)
check("eine aktuelle Datei laedt vollstaendig",
      _seq_new is not None and len(_seq_new.loop_phases[0].steps) == 1)
check("und ihre Koordinate kommt aus ihrer Punktliste",
      _seq_new is not None
      and (_seq_new.loop_phases[0].steps[0].x, _seq_new.loop_phases[0].steps[0].y)
      == (100, 200))


# ------------------------------------------------ Migration: alle Dateitypen
section("Migration: Dateitypen ohne Versions-Feld bleiben unangetastet")
from autoclicker.persistence.migration import (
    KIND_ITEMS as _K_ITEMS, KIND_ITEM_SCAN as _K_ISCAN,
    file_version as _fv, migrate as _mig,
)

# file_version muss auch Listen und Muell vertragen - die Boss-Bibliothek IST eine
# Liste. Vorher knallte hier AttributeError und tools/migrate.py starb an der ersten Datei.
check("file_version(Liste) = 0", _fv([{"x": 1}]) == 0)
check("file_version(None) = 0", _fv(None) == 0)
check("file_version(dict ohne Feld) = 0", _fv({"name": "x"}) == 0)

# Die Normalisierer sind Geschichte: `_norm_points` hob eine `points.json`, die es seit
# den sequenzlokalen Punkten nicht mehr gibt, die uebrigen waren No-ops. Ein Modul
# voller Haken fuer Dateien, die niemand mehr schreibt, ist genau das Anwachsen, das
# hier vermieden werden soll. Was bleibt, ist die Regel: unversionierte Typen kommen
# unveraendert zurueck — auch ein totes `confirm_point`-Feld wird nicht angefasst.
import autoclicker.persistence.migration as _mg_check
check("KIND_POINTS und die Normalisierer gibt es nicht mehr",
      not hasattr(_mg_check, "KIND_POINTS") and not hasattr(_mg_check, "_NORMALIZER"))
_items = {"Kohle": {"name": "Kohle", "confirm_point": [55, 66]}}
_items_before = json.loads(json.dumps(_items))
_items, _m = _mig(_items, _K_ITEMS)
check("Items: kein Normalisierer mehr, nichts wird angefasst",
      _items == _items_before and _m == [])

# Item-Scans werden nicht mehr auf einen globalen Namensbestand migriert.
_scan = {"name": "inv", "slots": {"S1": {"scan_region": [0, 0, 1, 1],
                                                   "click_pos": [0, 0]}},
         "items": {"Kohle": {"confirm_point_id": 7}}}
_scan_before = json.loads(json.dumps(_scan))
_scan, _m = _mig(_scan, _K_ISCAN)
check("Item-Scan: eigenstaendiger Bestand bleibt unangetastet",
      _scan == _scan_before)
check("Item-Scan: kein Altlast-Umbau", _m == [])
check("Item-Scan: zweiter Lauf meldet nichts", _mig(_scan, _K_ISCAN)[1] == [])

# Der Loader kennt die alte Liste NICHT mehr - dafuer ist die Migration da
from autoclicker.persistence.serialization import _item_from_dict as _ifd
check("Loader ignoriert das alte confirm_point-Format",
      _ifd({"confirm_point": [1, 2]}, "X").confirm_point is None)
# Auch das juengere {x,y}-Format ist tot - der Bestaetigungsklick ist heute ein Punkt.
check("Loader ignoriert auch die {x,y}-Form",
      _ifd({"confirm_point": {"x": 1, "y": 2}}, "X").confirm_point is None)
check("Loader liest die Punkt-Referenz",
      _ifd({"confirm_point_id": 9}, "X").confirm_point_id == 9)
# Der Name kommt aus dem Schluessel, nicht mehr aus dem Eintrag
check("Name kommt aus dem Schluessel", _ifd({}, "Kohle").name == "Kohle")

# Hier stand der Test, dass ein Schritt an einem Punkt OHNE ID einen neuen Punkt
# bekommt - Verhalten von `_seq_v3_to_v4`, mit der Kette entfallen; `_norm_points`
# (IDs nachnummerieren) ist ihm gefolgt. `_point_from_dict` verlangt die ID.

# scheduled_start war nur da, um den Debug-Enter-Prompt zu ueberspringen - beides weg
check("kein scheduled_start-Flag mehr am State",
      not any(f.name == "scheduled_start"
              for f in __import__("dataclasses").fields(AutoClickerState)))


# ------------------------------------------------ Debug-Stufen zur Laufzeit
section("Debug-Stufen im Punkte-Menue umschaltbar (ohne config.json editieren)")
import autoclicker.config as _cfgmod
import autoclicker.handlers as _hnd

_saved = []
_orig_save = _cfgmod.save_config
_cfgmod.save_config = lambda c: _saved.append((c.debug_log, c.debug_detail))

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
check("jede Umschaltung wird persistiert", len(_saved) == 3)
_cfgmod.save_config = _orig_save


# ------------------------------------- Zusage: jeder Dateityp hat eine Schleuse
section("Migration greift bei JEDEM Dateityp (Formatwechsel ohne Neuaufnahme)")
from autoclicker.persistence import migration as _mg

# 1. Versioniert ist genau, was eine Kette hat — und das ist die Sequenz. Alle
#    anderen Typen stehen in ALL_KINDS und kommen aus migrate() unveraendert zurueck.
check("nur die Sequenz hat eine Kette", set(_mg._CHAINS) == {_mg.KIND_SEQUENCE})
check("jeder Typ mit Kette steht in ALL_KINDS",
      all(k in _mg.ALL_KINDS for k in _mg._CHAINS))

# 2. JEDER Loader ruft migrate() auf - gesucht statt aufgezaehlt.
#
# Vorher stand hier eine handgepflegte Liste von sechs Dateien. Die deckte genau die
# ab, an die jemand gedacht hatte; drei weitere Module lesen dieselben Dateien direkt
# (die GUI-Subprozesse) und fielen durch. Eine Liste, die nur das prueft, woran man
# ohnehin denkt, ist keine Pruefung - dasselbe Argument wie bei PLATTFORM_MODULE.
_repo = Path(__file__).resolve().parent.parent

# Bewusste Ausnahmen, mit Grund. Wer eine neue eintraegt, muss sie begruenden koennen.
_MIGRATE_EXCEPTIONS = {
    # Die Config hat kein schema_version und laeuft ueber AppConfig.from_dict(),
    # das unbekannte Keys wegfiltert - der Normalisierer waere hier wirkungslos.
    "autoclicker/config.py":
        "AppConfig.from_dict filtert unbekannte Keys selbst",
    # Die GUI-Subprozesse lesen dieselben Dateien mit eigenen schlanken Ladern
    # (kein AutoClickerState) und werden AUS dem Hauptprozess gestartet, der beim
    # Start alles gehoben hat. Mit `migrate_on_start: false` gilt das nicht mehr -
    # folgenlos, solange die Sequenz-Kette leer ist.
    "autoclicker/editors/sequence_studio/model.py":
        "Subprozess - Hauptprozess hat beim Start gesweept (sofern migrate_on_start an ist)",
    # list_scan_files() liest EIN Feld ("name") fuer die Auswahlliste und baut keine
    # Dataclass. Es gibt nichts zu heben - solange `name` das Feld bleibt, an dem ein
    # Scan haengt. Wuerde es je umbenannt, gehoert diese Zeile hier weg.
    "autoclicker/persistence/_scan_store.py":
        "liest nur das Feld 'name', baut keine Dataclass",
    # Die Marktwert-Datei kommt von aussen (market_analysis) und ist kein Datenformat
    # dieses Programms: Name -> Zahl, kein schema_version, nichts zu heben. Sie wird
    # gelesen wie eine Fremddatei - fehlerhafte Eintraege fliegen einzeln raus.
    "autoclicker/runtime/item_scan.py":
        "liest die externe Marktwert-JSON (Fremdformat ohne Schema)",
    # Derselbe Fall wie die Marktwert-Datei: der Katalog kommt aus der Spiel-API
    # (geschrieben von tools/catalog.py), ist Name -> {kategorie, wert} und traegt
    # kein schema_version. Es gibt nichts zu heben; kaputte Eintraege fliegen
    # einzeln raus, statt den Katalog unbrauchbar zu machen.
    "autoclicker/catalog.py":
        "liest die externe Katalog-JSON (Fremdformat ohne Schema)",
    # Die Bruecke laedt aus zwei transienten Zustandsdateien (.run.json aus
    # runtime/status.py, .recording.json aus dem Recorder): kein Bestand, also
    # nichts zu heben. Sequenzen laedt sie ueber load_sequence_file(), und das
    # migriert.
    "autoclicker/editors/sequence_studio/bridge_services.py":
        "liest nur transiente Zustandsdateien; Sequenzen ueber load_sequence_file()",
    # Dasselbe im Werkzeuge-Reiter: .reclick.json ist der Live-Stand der
    # Klick-Runde aus dem Hauptprozess. Er wird bei jeder Bewegung ueberschrieben
    # und beschreibt den Moment, nicht einen Bestand.
    "autoclicker/editors/sequence_studio/bridge_tools.py":
        "liest nur den transienten Stand der Klick-Runde",
}
_leser, _without_call = [], []
for _pf in sorted((_repo / "autoclicker").rglob("*.py")):
    _txt = _pf.read_text(encoding="utf-8")
    if "json.load(" not in _txt:
        continue
    _rel = _pf.relative_to(_repo).as_posix()
    _leser.append(_rel)
    if "migrate(" not in _txt and _rel not in _MIGRATE_EXCEPTIONS:
        _without_call.append(_rel)
check("jeder Loader ruft migrate() auf (oder steht begruendet auf der Ausnahmeliste)",
      _without_call == [])
if _without_call:
    print("        " + ", ".join(_without_call))
# Gegenrichtung: eine Ausnahme, die gar nicht mehr laedt, ist eine Fiktion
_dead_exceptions = [a for a in _MIGRATE_EXCEPTIONS if a not in _leser]
check("keine Ausnahme fuer eine Datei, die gar nichts mehr laedt", _dead_exceptions == [])
check("der Test findet ueberhaupt Loader", len(_leser) >= 6)

# 3. Unbekannter Typ ist ein Programmierfehler, kein stiller No-Op-Pfad:
#    migrate() laesst die Daten unangetastet, aber ALL_KINDS deckt alles ab (s. 1.)
check("ALL_KINDS deckt alle KIND_-Konstanten ab",
      set(_mg.ALL_KINDS) == {v for n, v in vars(_mg).items()
                             if n.startswith("KIND_") and isinstance(v, str)})

# 4. "Schon neu" heisst: nichts wird angefasst. Fuer JEDEN Typ.
_current = {
    _mg.KIND_SEQUENCE: {"schema_version": _mg.SCHEMA_VERSION, "name": "s",
                        "init_steps": [], "loop_phases": [], "end_steps": []},
    _mg.KIND_ITEMS: {"I": {"name": "I", "confirm_point": {"x": 1, "y": 2}}},
    _mg.KIND_ITEM_SCAN: {"name": "sc", "slot_names": ["S"], "item_names": ["I"]},
    _mg.KIND_SLOTS: {"S": {"name": "S", "scan_region": [0, 0, 1, 1], "click_pos": [0, 0]}},
    _mg.KIND_BOSS_SCAN: {"name": "b", "bosses": []},
    _mg.KIND_ICON_SCAN: {"name": "i", "scan_region": [0, 0, 1, 1]},
    _mg.KIND_GLOBAL_BOSSES: [{"name": "Drache"}],
}
check("Testdaten decken alle Dateitypen ab", set(_current) == set(_mg.ALL_KINDS))
_untouched = True
for _kind, _data in _current.items():
    _before = json.dumps(_data, sort_keys=True)
    _out, _report = _mg.migrate(_data, _kind)
    # Der Versions-Stempel darf gesetzt werden, der Inhalt nicht wandern.
    _after = json.dumps(_out, sort_keys=True)
    if _report or (_kind != _mg.KIND_SEQUENCE and _before != _after):
        _untouched = False
        print(f"        -> {_kind} wurde angefasst: {_report}")
check("aktuelle Daten werden bei keinem Typ veraendert", _untouched)


# ------------------------------------------- Start-Durchgang (persistence/sweep)
section("Start-Durchgang: alle Dateien beim Programmstart aufs aktuelle Format")
import os as _os
from autoclicker.persistence.sweep import sweep as _sweep, collect_files as _sammle

# Gestellt wird die ECHTE Struktur: eine Sequenz ist eine Besitzeinheit
# (`sequences/<name>/`) mit ihrer sequence.json, ihren Scan-Ordnern und ihrer
# Boss-Bibliothek. Hier stand einmal die flache Struktur von frueher
# (`sequences/points.json`, `items/items.json`, `item_scans/` im Wurzelordner) —
# der Test blieb gruen, waehrend `collect_files()` produktiv nur noch die
# config.json fand. Ein Test, der eine Welt stellt, die es nicht mehr gibt,
# misst nichts.
_sw = Path(tempfile.mkdtemp())
for _d in ("sequences/alt/item_scans", "sequences/alt/boss_scans",
           "presets/items", "presets/slots"):
    (_sw / _d).mkdir(parents=True, exist_ok=True)

# Auf aktuellem Schema, aber mit einem toten Feld im Schritt: genau der Fall, den der
# Durchgang OHNE Migrationsschritt loest - was der Loader nicht kennt, schreibt der
# Serializer nicht zurueck. Die Punkte stehen IM selben Dokument - eine eigene
# points.json gibt es nicht mehr.
(_sw / "sequences/alt/sequence.json").write_text(json.dumps(
    {"name": "alt", "schema_version": 4, "total_cycles": 1,
     "points": [{"id": 2, "x": 300, "y": 400, "name": "B", "legacy_flag": True}],
     "init_steps": [], "end_steps": [],
     "loop_phases": [{"name": "L", "repeat": 1, "steps": [
         {"point_id": 2, "delay_before": 1, "clicks": 2, "point_index": 0}]}]}),
    encoding="utf-8")
# Ein gueltiger Item-Scan mit Farben als Liste. Der Loader gibt sie als Tupel
# zurueck - beides ist in JSON dasselbe Array, also darf es KEINE Aenderung sein.
(_sw / "sequences/alt/item_scans/scan.json").write_text(json.dumps(
    {"name": "scan",
     "slots": {"S1": {"scan_region": [0, 0, 10, 10], "click_pos": [5, 5],
                      "slot_color": [20, 95, 80], "id": 1}},
     "items": {"K": {"marker_colors": [[20, 95, 80], [210, 15, 150]], "uralt": 1}}}),
    encoding="utf-8")
(_sw / "sequences/alt/item_scans/kaputt.json").write_text("{ kein json", encoding="utf-8")

_cwd = _os.getcwd()
try:
    _os.chdir(_sw)
    check("Sweep findet alle Dateien der Besitzeinheit", len(_sammle()) == 3)
    # Die Bibliothek liegt zwischen den Boss-Scans und ist eine Liste, kein Scan.
    # Mit dem Scan-Loader gelesen waere sie unlesbar und wuerde als "uebersprungen"
    # gemeldet - dabei ist sie die Datei, die im Betrieb am haeufigsten dazukommt
    # (ein Lauf legt per LLM entdeckte Bosse dort ab).
    (_sw / "sequences/alt/boss_scans/bibliothek.json").write_text(
        json.dumps([{"name": "Drache", "action": "skip", "tot": 1}]), encoding="utf-8")
    _kinds = {p.name: k for p, k, _ in _sammle()}
    check("die Boss-Bibliothek wird als Bibliothek erkannt, nicht als Scan",
          _kinds.get("bibliothek.json") == _mg.KIND_GLOBAL_BOSSES)

    _e1 = _sweep(write=True)
    check("Sweep hebt die Altbestaende", _e1.changed_count == 3)
    check("Sweep meldet 'es gab was zu tun'", bool(_e1) is True)
    check("kaputte Datei wird uebersprungen, nicht geschrieben",
          len(_e1.skipped) == 1 and _e1.skipped[0].name == "kaputt.json")
    check("kaputte Datei bleibt unveraendert",
          (_sw / "sequences/alt/item_scans/kaputt.json").read_text(
              encoding="utf-8") == "{ kein json")
    # Sicherungen gehoeren unter backups/, nicht neben das Original: dort verstellen sie
    # den Blick auf die Daten und ein *.json-Glob koennte sie erwischen.
    check("Sicherung liegt unter backups/ mit gespiegeltem Ordner",
          (_sw / "backups/sequences/alt/sequence.json.bak").exists())
    check("und NICHT mehr neben dem Original",
          not (_sw / "sequences/alt/sequence.json.bak").exists())
    check("Sicherung hat den Stand VOR dem Aufraeumen",
          "point_index" in (_sw / "backups/sequences/alt/sequence.json.bak").read_text(
              encoding="utf-8"))

    # Zweiter Durchgang: nur noch die kaputte Datei bleibt uebrig, sonst still
    _e2 = _sweep(write=True)
    check("zweiter Durchgang aendert nichts mehr", _e2.changed_count == 0)
    check("zweiter Durchgang zaehlt alles als aktuell", _e2.current == 3)

    # Ergebnis pruefen: Inhalt gehoben, Sequenz funktionsfaehig
    _sq = json.loads((_sw / "sequences/alt/sequence.json").read_text(encoding="utf-8"))
    check("Start-Durchgang stempelt die Sequenz-Version",
          _sq.get("schema_version") == _mg.SCHEMA_VERSION)
    check("die Punkt-Referenz bleibt unangetastet",
          _sq["loop_phases"][0]["steps"][0]["point_id"] == 2)
    check("der Punkt selbst steht in derselben Datei",
          [_p["id"] for _p in _sq["points"]] == [2])
    check("und sein totes Feld ist weg", "legacy_flag" not in _sq["points"][0])
    # **Das ist der Beleg, dass es ohne Migrationsschritt geht.** `clicks` und
    # `point_index` stehen in keiner Dataclass, der Loader liest sie nicht, der
    # Serializer schreibt sie nicht zurueck - der Round-Trip allein raeumt sie weg.
    check("Start-Durchgang entfernt tote Schritt-Felder ohne Migrationsschritt",
          "clicks" not in _sq["loop_phases"][0]["steps"][0]
          and "point_index" not in _sq["loop_phases"][0]["steps"][0])
    _sc = json.loads(
        (_sw / "sequences/alt/item_scans/scan.json").read_text(encoding="utf-8"))
    check("Start-Durchgang entfernt totes Item-Feld", "uralt" not in _sc["items"]["K"])
    check("die Marker-Farben ueberleben unveraendert",
          _sc["items"]["K"]["marker_colors"] == [[20, 95, 80], [210, 15, 150]])
    _bb = json.loads(
        (_sw / "sequences/alt/boss_scans/bibliothek.json").read_text(encoding="utf-8"))
    check("und die Bibliothek wurde geraeumt statt uebersprungen",
          isinstance(_bb, list) and "tot" not in _bb[0])

    # **Ein Tupel ist eine Liste.** Der Loader gibt Farben als Tupel zurueck, in der
    # Datei stehen sie als Array - in JSON dasselbe. Stieg `_normalize_numbers`
    # nicht in das Tupel hinein, blieben dessen Zahlen int, waehrend die der Liste
    # float wurden: zwei inhaltsgleiche Dateien galten als verschieden, und JEDER
    # Start schrieb dieselben Item-Scans neu, legte ein .bak an und meldete eine
    # Migration, die nichts tut. Genau der Fehler, den `600` gegen `600.0` unten
    # fuer Zahlen abfaengt - nur eine Klammer weiter.
    (_sw / "backups/sequences/alt/item_scans/scan.json.bak").unlink(missing_ok=True)
    _e_t = _sweep(write=True)
    check("ein Item-Scan mit Farben wird nicht bei jedem Start neu geschrieben",
          _e_t.changed_count == 0
          and not (_sw / "backups/sequences/alt/item_scans/scan.json.bak").exists())

    # Von Hand getippte Wartezeit: `600` statt `600.0`. In JSON ist das dieselbe Zahl,
    # also gibt es nichts aufzuraeumen. Vorher schrieb der Durchgang die Datei deswegen
    # um, legte ein .bak an und meldete eine Migration, die inhaltlich nichts tat —
    # bei JEDEM Start, an dem jemand eine runde Zahl in die JSON getippt hatte.
    _manual_dir = _sw / "sequences/hand"
    _manual_dir.mkdir(parents=True, exist_ok=True)
    _manual = _manual_dir / "sequence.json"
    _manual.write_text(json.dumps(
        {"name": "hand", "schema_version": _mg.SCHEMA_VERSION,
         "points": [{"id": 1, "x": 10, "y": 20, "name": "H"}],
         "init_steps": [], "end_steps": [],
         "loop_phases": [{"name": "L", "repeat": 1,
                          "steps": [{"point_id": 1, "delay_before": 1.5}]}]}),
        encoding="utf-8")
    _sweep(write=True)                    # einmal in die Normalform bringen
    (_sw / "backups/sequences/hand/sequence.json.bak").unlink(missing_ok=True)
    # ... und jetzt genau EINE Zahl auf int zurueckdrehen, sonst nichts
    _norm = json.loads(_manual.read_text(encoding="utf-8"))
    _norm["loop_phases"][0]["steps"][0]["delay_before"] = 600
    _manual.write_text(json.dumps(_norm, indent=2), encoding="utf-8")
    _before = _manual.read_text(encoding="utf-8")

    _e3 = _sweep(write=True)
    check("von Hand getippte 600 gilt nicht als Aenderung", _e3.changed_count == 0)
    check("die Datei bleibt dabei unangetastet",
          _manual.read_text(encoding="utf-8") == _before)
    check("und es entsteht kein .bak fuer nichts",
          not (_sw / "backups/sequences/hand/sequence.json.bak").exists())
finally:
    _os.chdir(_cwd)

# Die Struktur unter backups/ wird gespiegelt. Ohne das ueberschriebe die Sicherung von
# item_scans/foo.json die von boss_scans/foo.json - gleicher Name, anderer Ordner, und
# eine der beiden haette keine Sicherung mehr.
from autoclicker.persistence.sweep import backup_path as _sp
check("Sicherung landet unter backups/ mit gespiegeltem Ordner",
      _sp(Path("sequences/all_dayli.json")) == Path("backups/sequences/all_dayli.json.bak"))
check("gleiche Dateinamen in verschiedenen Ordnern kollidieren nicht",
      _sp(Path("item_scans/foo.json")) != _sp(Path("boss_scans/foo.json")))
check("Datei im Wurzelverzeichnis behaelt ihren Platz",
      _sp(Path("config.json")) == Path("backups/config.json.bak"))
# Ein absoluter Pfad darf unter backups/ nicht den halben Laufwerkspfad nachbauen
check("absoluter Pfad wird relativ zum Arbeitsverzeichnis gelegt",
      _sp(Path.cwd() / "sequences" / "x.json") == Path("backups/sequences/x.json.bak"))
check("Pfad ausserhalb des Arbeitsverzeichnisses behaelt nur den Namen",
      _sp(Path(tempfile.gettempdir()) / "fremd.json") == Path("backups/fremd.json.bak"))

# _equal muss die Zahlentypen angleichen, ohne echte Unterschiede zu verschlucken.
# Beide Richtungen, sonst waere auch ein "alles ist gleich" gruen.
from autoclicker.persistence.sweep import _equal as _gl
check("_equal: 600 und 600.0 sind dieselbe Zahl", _gl({"d": 600}, {"d": 600.0}))
check("_equal: auch verschachtelt", _gl({"s": [{"d": 1}]}, {"s": [{"d": 1.0}]}))
check("_equal: echte Wertaenderung faellt weiterhin auf", not _gl({"d": 600}, {"d": 700}))
# bool ist in Python ein int - ohne Sonderfall waere ein umgekipptes Flag unsichtbar
check("_equal: True geht nicht als 1.0 durch", not _gl({"b": True}, {"b": 1.0}))
check("_equal: fehlender Schluessel faellt weiterhin auf", not _gl({"d": 1}, {"d": 1, "x": 2}))
check("_equal: Zeichenkette bleibt Zeichenkette", not _gl({"d": "600"}, {"d": 600}))

# Abschaltbar, falls man Altbestand einfrieren will
check("migrate_on_start ist ein Config-Feld mit Default an",
      AppConfig().migrate_on_start is True)


# --------------------------------- Schlanke Schritte (nur benutzte Felder)
section("Sequenz-Schritte: nur gesetzte Felder werden geschrieben")
from autoclicker.models import SequenceStep as _SS, WaitCondition as _WCx, ElseConfig as _ECx
from autoclicker.persistence.serialization import (
    _step_to_dict as _s2d, _parse_steps as _p2s, _STEP_DEFAULTS as _SD)

_click = _s2d(_SS(x=100, y=200, delay_before=1, name="Klick 15", point_id=7))
# Seit Schema 4 bleiben genau zwei Felder: worauf gezeigt wird und wie lange vorher
# gewartet wird. x/y/name kommen aus dem Punkt und werden nicht mitgeschrieben.
check("einfacher Klick braucht nur 2 Felder", len(_click) == 2)
check("die Stelle steht als ID drin, nicht als Koordinate",
      _click.get("point_id") == 7 and "x" not in _click and "y" not in _click)
check("delay_before bleibt immer sichtbar", "delay_before" in _click)
# Ein Schritt OHNE Punkt hat auch keine Koordinate zu speichern (Taste, Scan, ...)
check("Schritt ohne Stelle speichert erst recht keine Koordinate",
      "x" not in _s2d(_SS(delay_before=0, key_press="enter")))
check("kein leeres wait_pixel mehr", "wait_pixel" not in _click)
check("kein leeres else_action mehr", "else_action" not in _click)
check("kein item_scan_mode ohne item_scan", "item_scan_mode" not in _click)

# Gesetzte Felder muessen selbstverstaendlich drinbleiben
_color = _s2d(_SS(x=1, y=2, delay_before=0, name="F",
                 wait_condition=_WCx(pixel=(5, 6), color=(7, 8, 9), until_gone=True),
                 else_config=_ECx(action="click", x=10, y=11)))
check("gesetzte Farb-Bedingung wird geschrieben",
      _color.get("wait_pixel") == (5, 6) and _color.get("wait_until_gone") is True)
check("gesetzte Else-Aktion wird geschrieben",
      _color.get("else_action") == "click" and _color.get("else_x") == 10)

# 0 ist nicht False: else_delay=0 ist ein echter Wert, screenshot_only=0 nicht.
# Ein Bool-Default darf keine 0 verschlucken und eine Zahl keinen Bool.
check("eine 0 in einem Bool-Feld wird nicht als Default verschluckt",
      _s2d(_SS(x=0, y=0, delay_before=0, screenshot_only=0)).get("screenshot_only") == 0)

# Round-Trip ohne Referenzen: diese Schritte tragen nichts Abgeleitetes, sie muessen
# unveraendert zurueckkommen.
_cases = [
    _SS(delay_before=0.5, name="Taste", key_press="enter"),
    _SS(delay_before=0, name="Scan", item_scan="inv", item_scan_mode="best"),
    _SS(delay_before=0, name="Shot", screenshot_only=True,
        screenshot_region=(1, 2, 3, 4)),
    _SS(delay_before=2, name="Zufall", delay_max=4.0, wait_only=True),
]
_deviations = [st for st in _cases if _p2s([_s2d(st)])[0] != st]
check("Round-Trip aendert keinen Schritt ohne Referenz", _deviations == [])

# Round-Trip MIT Referenzen: die abgeleiteten Werte fehlen nach dem Parsen (sie stehen
# ja nicht in der Datei) und kommen erst durch das Aufloesen zurueck. Genau diese zwei
# Haelften zusammen muessen den Ausgangszustand ergeben - sonst geht beim Speichern
# etwas verloren, das niemand wiederherstellen kann.
from autoclicker.persistence.sequences import resolve as _aufl
_pool = {7: _CP(x=100, y=200, name="Klick", id=7),
         8: _CP(x=5, y=6, name="Pruef", id=8, color=(7, 8, 9)),
         9: _CP(x=10, y=11, name="Ausweich", id=9)}
_with_ref = [
    _SS(x=100, y=200, delay_before=1, name="Klick", point_id=7),
    _SS(x=100, y=200, delay_before=0, name="Klick", point_id=7,
        wait_condition=_WCx(point_id=8, pixel=(5, 6), color=(7, 8, 9), check_only=True),
        else_config=_ECx(action="click", point_id=9, x=10, y=11, name="Ausweich")),
    _SS(x=100, y=200, delay_before=0, name="Klick", point_id=7, key_press="enter"),
]
_returned = _p2s([_s2d(st) for st in _with_ref])
_aufl(_pool, _Seq(name="rt", loop_phases=[_LP(name="L", steps=_returned)]), quiet=True)
check("Round-Trip + Aufloesen stellt den Schritt vollstaendig wieder her",
      [st for a, st in zip(_returned, _with_ref) if a != st] == [])

# Die Default-Tabelle darf nicht von der Dataclass abdriften
_dc_defaults = {f.name: f.default for f in __import__("dataclasses").fields(_SS)}
_drifted = [k for k, v in _SD.items()
                if k in _dc_defaults and _dc_defaults[k] is not v
                and _dc_defaults[k] != v]
check("Default-Tabelle passt zur Dataclass", _drifted == [])

# `delay_after` war die Altlast, die `_seq_v1_to_v2` in `delay_before` umbenannt hat.
# Der Schritt ist mit der Kette entfallen; was BLEIBT, ist die Zusicherung, dass der
# Loader das alte Feld nicht kennt - denn das ist der Grund, warum es die Migration
# ueberhaupt gab. Ein Schritt mit `delay_after` bekommt heute schlicht den Default.
check("Loader kennt delay_after nicht mehr",
      _p2s([{"x": 1, "y": 2, "delay_after": 9}])[0].delay_before == 0)


# ------------------------------- Items/Slots gehören genau einem Scan
section("Item-Scans besitzen ihre Slots/Items")
from autoclicker.persistence.item_scans import resolve_click_references as _resolve_scans
from autoclicker.models import ItemScanConfig as _ISC

_st4 = AutoClickerState()
_slot4 = ItemSlot(name="S1", scan_region=(0, 0, 10, 10), click_pos=(5, 5))
_item4 = ItemProfile(name="Kohle", marker_colors=[(1, 2, 3)], category="Erz", priority=1)
_st4.item_scans = {"inv": _ISC(name="inv", slots=[_slot4], items=[_item4])}

_report = _resolve_scans(_st4)
_cfg = _st4.item_scans["inv"]
check("Scan behält seinen eigenen Slot", _cfg.slots == [_slot4])
check("Scan behält sein eigenes Item", _cfg.items == [_item4])
check("nichts zu meckern wenn alles da ist", _report == [])

from autoclicker.persistence.serialization import _item_scan_to_dict as _isc2d
_from_editor = _ISC(name="neu", slots=[_slot4], items=[_item4])
_saved = _isc2d(_from_editor)
check("vollständiger Slot wird eingebettet", "S1" in _saved["slots"])
check("vollständiges Item wird eingebettet", "Kohle" in _saved["items"])

# Zwei gleichnamige Items in zwei Scans bleiben getrennt.
_second_one = ItemProfile(name="Kohle", marker_colors=[(9, 9, 9)])
_st4.item_scans["zweites"] = _ISC(name="zweites", items=[_second_one])
_item4.marker_colors = [(4, 4, 4)]
check("gleichnamige Items anderer Scans bleiben unabhängig",
      _second_one.marker_colors == [(9, 9, 9)])


# ----------------------- Default-Tabellen duerfen nicht von den Dataclasses abdriften
section("Default-Tabellen passen zu den Dataclasses")
import dataclasses as _dc
from autoclicker.persistence import serialization as _ser
from autoclicker.models import (ItemProfile as _IP, ItemSlot as _IS2,
                                BossProfile as _BP, BossScanConfig as _BSC,
                                IconScanConfig as _ISC2, SequenceStep as _SS2,
                                ItemScanConfig as _ISCFG)

def _dataclass_defaults(cls):
    out = {}
    for f in _dc.fields(cls):
        if f.default is not _dc.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not _dc.MISSING:      # type: ignore[misc]
            out[f.name] = f.default_factory()          # type: ignore[misc]
    return out

# Steht in der Tabelle ein anderer Wert als in der Dataclass, wuerde das Feld beim
# Speichern weggelassen und beim Laden mit einem ANDEREN Wert wieder auftauchen -
# stiller Datenverlust. Deshalb hart pruefen.
_tables = [
    ("Item", _ser._ITEM_DEFAULTS, _IP),
    ("Slot", _ser._SLOT_DEFAULTS, _IS2),
    ("Boss", _ser._BOSS_DEFAULTS, _BP),
    ("Boss-Scan", _ser._BOSS_SCAN_DEFAULTS, _BSC),
    ("Icon-Scan", _ser._ICON_SCAN_DEFAULTS, _ISC2),
    ("Item-Scan", _ser._ITEM_SCAN_DEFAULTS, _ISCFG),
    ("Schritt", _ser._STEP_DEFAULTS, _SS2),
]
for _tab_name, _table, _cls in _tables:
    _dcd = _dataclass_defaults(_cls)
    _drift = [k for k, v in _table.items()
              if not (_tab_name == "Item-Scan" and k in ("slots", "items"))
              and k in _dcd and not (_dcd[k] == v and type(_dcd[k]) is type(v))]
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
section("Import: ein Weg, und Altbuendel werden abgelehnt statt halb eingelesen")
import os as _os, zipfile as _zip
from autoclicker.import_export import (import_bundle as _import_bundle,
                                       export_bundle as _export_bundle)
from autoclicker.models import AutoClickerState as _ACS
from autoclicker.persistence import list_available_sequences as _las

# **Hier stand die Pruefung eines zweiten, vollstaendigen Import-Wegs.** Buendel
# aus der Zeit des globalen Bestands brachten `points.json`, `slots.json` und
# `items.json` mit, und weil die Punkt-IDs damals programmweit galten, konnte
# eine importierte ID mit einer lokalen kollidieren — daran haing die halbe
# Sektion. Beides gibt es nicht mehr: eine Sequenz bringt ihre Punkte im eigenen
# Dokument mit, IDs gelten nur darin, und `_remap_point_ids`/
# `_referenzierte_punkte` sind ersatzlos entfallen.
#
# Der Altweg war zudem nicht bloss Altlast, sondern **kaputt**: Vorlagen landeten
# in `items/templates/`, wo seit dem Umzug keine Sequenz mehr nachsieht.
# Gemessen wird deshalb, dass er sauber ABSAGT statt so zu tun, als haette es
# geklappt.

_old_cwd = _os.getcwd()
_imp_dir = tempfile.mkdtemp()
try:
    _os.chdir(_imp_dir)

    # --- Ein Buendel im Altformat: erkennbar am fehlenden `layout` ---
    _old_bundle = Path(_imp_dir) / "alt.zip"
    with _zip.ZipFile(_old_bundle, "w") as _zf:
        _zf.writestr("manifest.json", json.dumps(
            {"version": 1, "reference_points": {"point1": [0, 0], "point2": [10, 10]},
             "contents": {}}))
        _zf.writestr("sequences/farm.json", json.dumps(
            {"name": "farm", "schema_version": 2, "init_steps": [], "end_steps": [],
             "loop_phases": []}))

    _st_old = _ACS()
    _ok_old, _msg_old = _import_bundle(_st_old, str(_old_bundle), import_config=False)
    check("ein Altbuendel wird abgelehnt", _ok_old is False)
    check("und die Absage sagt, warum und was stattdessen geht",
          "aelteren Fassung" in _msg_old and "Studio" in _msg_old)
    # Das ist der eigentliche Gewinn gegenueber dem alten Zweig: er meldete
    # Erfolg und hinterliess nichts Brauchbares.
    check("abgelehnt heisst: nichts angelegt", not Path("sequences").exists())

    # --- Der heutige Weg: exportieren, einlesen, alles wieder da ---
    from autoclicker.persistence import (ensure_sequences_dir as _esd_i,
                                         save_sequence_file as _ssf_i)
    from autoclicker.models import (Sequence as _SEQ_i, LoopPhase as _LP_i,
                                    SequenceStep as _SS_i, ClickPoint as _CP_i)
    _source = _SEQ_i("farm", [], [_LP_i(name="Loop", steps=[
        _SS_i(delay_before=0, point_id=7)], repeat=1)], [], 1, "",
        [_CP_i(500, 500, "Ofen", 7)])
    _esd_i()
    _ssf_i(_source, Path("sequences") / "farm" / "sequence.json")

    _st_exp = _ACS()
    _new_bundle = Path(_imp_dir) / "neu.zip"
    _ok_exp, _ = _export_bundle(_st_exp, str(_new_bundle), (0, 0), (10, 10))
    check("ein heutiges Buendel laesst sich schreiben", _ok_exp is True)

    _st_imp = _ACS()
    _ok_imp, _msg_imp = _import_bundle(_st_imp, str(_new_bundle), import_config=False,
                                       merge=False)
    check("und wieder einlesen", _ok_imp is True)
    # Gezaehlt wird, was auf der Platte liegt — einen Sequenz-Cache im State
    # gibt es nicht mehr, der Import schreibt Ordner.
    from autoclicker.persistence import load_sequence_file as _lsf_i
    _on_disk = dict(_las())
    _seq_i = _lsf_i(_on_disk["farm"]) if "farm" in _on_disk else None
    check("die Sequenz kommt an", _seq_i is not None)
    # Die Punkte reisen IM Dokument mit - ohne sie zeigte der Schritt ins Leere.
    check("ihr Punkt reist mit", _seq_i is not None
          and [(_p.id, _p.x, _p.y) for _p in _seq_i.points] == [(7, 500, 500)])
    _step_i = _seq_i.loop_phases[0].steps[0] if _seq_i else None
    check("und der Schritt zeigt weiterhin auf ihn",
          _step_i is not None and _step_i.point_id == 7)
    check("aufgeloest steht er auf der richtigen Stelle",
          _step_i is not None and (_step_i.x, _step_i.y) == (500, 500))

    # --- Punkt-IDs sind sequenzlokal, also kann nichts mehr kollidieren ---
    # Genau deshalb gibt es keine ID-Zuordnung mehr: eine zweite Sequenz mit
    # demselben Punkt #7 ist kein Konflikt, sondern ein anderer Punkt.
    _st_two = _ACS()
    _other = _SEQ_i("andere", [], [_LP_i(
        name="L", steps=[_SS_i(delay_before=0, point_id=7)], repeat=1)], [], 1, "",
        [_CP_i(9, 9, "Woanders", 7)])
    _ssf_i(_other, Path("sequences") / "andere" / "sequence.json")
    _before_two = {n for n, _ in _las()}
    _import_bundle(_st_two, str(_new_bundle), import_config=False, merge=True)
    # `merge` weicht einem vorhandenen Ordner aus (farm -> farm_2), der Name
    # steht also nicht vorher fest; gesucht wird die dazugekommene Sequenz.
    _after_two = dict(_las())
    _add_to_scan = [n for n in _after_two if n not in _before_two]
    check("die Sequenz kommt neben der vorhandenen an", len(_add_to_scan) == 1)
    _a = _lsf_i(_after_two["andere"]).points[0]
    _b = _lsf_i(_after_two[_add_to_scan[0]]).points[0] if _add_to_scan else _a
    check("zwei Sequenzen duerfen denselben Punkt #7 haben",
          _a.id == _b.id == 7 and (_a.x, _a.y) != (_b.x, _b.y))
finally:
    _os.chdir(_old_cwd)


# ------------------------------------------------- Laden veraendert nichts
section("Sequenz laden meldet nur, schreibt nicht")
from autoclicker.editors.sequence_editor.loader import _report_point_mismatches
from autoclicker.models import (Sequence as _Seq3, LoopPhase as _LP3,
                                SequenceStep as _SS3, ClickPoint as _CP3)

# Aufgenommene Punkte heissen per Default P<id> - eine Sequenz von einem anderen Rechner
# bringt also "P3" mit, und der lokale P3 liegt woanders. Frueher wurde der Schritt still
# dorthin verschoben UND die Datei ueberschrieben.
_st3 = _ACS()
_st3.points = [_CP3(50, 50, "P3", 3)]
_foreign = _SS3(x=900, y=900, delay_before=0, name="P3")
_seq3 = _Seq3("foreign", [], [_LP3("Loop", [_foreign])], [])
_report_point_mismatches(_st3, _seq3)
check("Schritt-Koordinaten bleiben unangetastet", (_foreign.x, _foreign.y) == (900, 900))
check("keine Referenz wird stillschweigend gesetzt", _foreign.point_id is None)

# Mit Referenz ist die Aufloesung zustaendig - dort wird der Schritt auch gemeldet
_linked = _SS3(x=900, y=900, delay_before=0, name="P3", point_id=3)
_seq4 = _Seq3("mit_ref", [], [_LP3("Loop", [_linked])], [], points=_st3.points)
_report_point_mismatches(_st3, _seq4)
check("Schritt mit point_id bleibt dem Loader egal", (_linked.x, _linked.y) == (900, 900))
from autoclicker.persistence import resolve_point_references as _rpr2
_report = _rpr2(_st3, _seq4)
check("erst die Aufloesung zieht ihn nach", (_linked.x, _linked.y) == (50, 50))
check("und meldet das im Klartext", len(_report) == 1 and "P3" in _report[0])


# -------------------------------------------- Item-Scan: Namen sind die Wahrheit
section("Item-Scan: Namen und Objekte bleiben synchron")
from autoclicker.models import ItemScanConfig as _ISC3, ItemSlot as _IS3, ItemProfile as _IP3
from autoclicker.persistence import resolve_click_references as _rsr

_slot_a, _slot_b = _IS3("S1", (0, 0, 10, 10), (5, 5)), _IS3("S2", (0, 0, 10, 10), (5, 5))
_item_a = _IP3("Kohle")

# So baut der EDITOR (und das Scan-Studio) eine Config: nur Objekte.
_cfg_editor = _ISC3(name="inv", slots=[_slot_a, _slot_b], items=[_item_a])
check("Editor-Config bekommt die Namen automatisch",
      _cfg_editor.slot_names == ["S1", "S2"] and _cfg_editor.item_names == ["Kohle"])

# Der Loader baut dieselben vollständigen Objekte. __str__ zeigt ihre Anzahl.
_cfg_file = _ISC3(name="inv", slots=[_slot_a, _slot_b], items=[_item_a])
check("frisch geladen zeigt das Menue die richtige Anzahl",
      "2 Slots" in str(_cfg_file) and "1 Items" in str(_cfg_file))

# Vor einem Lauf werden nur Punkt-IDs aufgelöst; der eigene Bestand bleibt.
_st5 = _ACS()
_st5.item_scans["inv"] = _cfg_editor
_rsr(_st5)
check("frisch bearbeiteter Scan ueberlebt den Sequenzstart",
      len(_cfg_editor.slots) == 2 and len(_cfg_editor.items) == 1)
check("Namen werden zu Objekten aufgeloest",
      [s.name for s in _cfg_file.slots] == ["S1", "S2"])

# Nachtraegliche Zuweisung an .slots (der Weg, der urspruenglich schiefging)
_cfg_late = _ISC3(name="spaet")
_cfg_late.slots = [_slot_a]
check("nachtraeglich gesetzte Objekte tragen ihre Namen nach",
      _cfg_late.slot_names == ["S1"])

# Gespeichert werden vollständige, scanlokale Objekte.
_saved = _item_scan_to_dict(_cfg_editor)
check("Datei enthaelt den vollständigen Scan-Bestand",
      set(_saved.get("slots", {})) == {"S1", "S2"}
      and set(_saved.get("items", {})) == {"Kohle"})


# ------------------------------------------------------- Setup-Pruefung
section("Setup-Pruefung findet die stillen Fehler")
from autoclicker.diagnostics import check_setup, LEVEL_ERROR, LEVEL_HINT
from autoclicker.models import (BossProfile as _BP2, BossScanConfig as _BSC2,
                                IconScanConfig as _ISC4)

_st6 = _ACS()
_diag_items = {
    "MitTemplate": _IP3("MitTemplate", template="gibtsnicht.png"),
    "OhneAlles": _IP3("OhneAlles"),
}
_st6.item_scans = {
    "inv": _ISC3(name="inv", slots=[_IS3("S1", (0, 0, 10, 10), (5, 5))],
                  items=list(_diag_items.values())),
    "empty": _ISC3(name="empty"),
    "aus": _ISC3(name="aus", slots=[
        _IS3("S aus", (0, 0, 10, 10), (5, 5), enabled=False)
    ]),
}
_st6.boss_scans = {"b": _BSC2(name="b", bosses=[_BP2("Hydra")], use_llm=True,
                                 default_scan="gibtsnicht")}
_st6.icon_scans = {"ico": _ISC4(name="ico")}

_rep = check_setup(_st6, with_sequences=False)
_texts = [f"{b.area}: {b.text}" for b in _rep.findings]


def _has(part):
    return any(part in t for t in _texts)


check("fehlendes Template wird gefunden", _has("gibtsnicht.png"))
check("Boss ohne Template UND ohne Marker wird gefunden",
      _has("Hydra") and _has("wird nie erkannt"))
check("Icon-Scan ohne Erkennung wird gefunden", _has("Icon-Scan 'ico'"))
check("Scan ganz ohne Slot wird gefunden", _has("kein einziger Slot"))
check("Scan nur mit ausgeschaltetem Slot wird gefunden",
      _has("kein Slot ist eingeschaltet"))
check("use_llm ohne llm_enabled wird gemeldet", _has("llm_enabled global aus"))
check("Fehler und Hinweise sind getrennt",
      len(_rep.errors) >= 3 and len(_rep.hints) >= 2
      and all(b.level in (LEVEL_ERROR, LEVEL_HINT) for b in _rep.findings))

# **Der Fallback-Scan ist die fuenfte Referenz auf einen Scan-Namen** - und die
# einzige, die nicht in einem Schritt steht, sondern in einer Boss-Scan-Datei.
# `_check_sequences()` sieht nur die vier im Schritt (`item_scan`, `boss_scan`,
# `boss_watcher`, `icon_scan`); diese fiel durch, obwohl `runtime/steps.py` sie
# bei „kein Boss erkannt" wirklich ausfuehrt.
check("ein Fallback-Scan, den es nicht gibt, wird gemeldet",
      _has("Fallback-Scan"))

_st_fb = _ACS()
_st_fb.item_scans = {"inv": _ISC3(
    name="inv", slots=[_IS3("S1", (0, 0, 10, 10), (5, 5))],
    items=[_IP3("Kohle", marker_colors=[(1, 2, 3)])])}
_st_fb.boss_scans = {"b": _BSC2(name="b", bosses=[_BP2("Hydra", template="t.png")],
                                default_scan="inv")}
_fb = check_setup(_st_fb, with_sequences=False)
check("ein Fallback-Scan, den es GIBT, wird nicht gemeldet",
      not any("Fallback-Scan" in f"{b.area}: {b.text}" for b in _fb.findings))

# Ein sauberes Setup darf NICHTS melden - sonst gewoehnt man sich das Ignorieren an
_st7 = _ACS()
_st7.item_scans = {"inv": _ISC3(
    name="inv", slots=[_IS3("S1", (0, 0, 10, 10), (5, 5))],
    items=[_IP3("Kohle", marker_colors=[(1, 2, 3)])])}
_clean = check_setup(_st7, with_sequences=False)
check("sauberes Setup meldet nichts", not _clean and _clean.findings == [])
check("trotzdem steht da, was geprueft wurde", len(_clean.checked) >= 3)


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
    _s1 = _img._template_at_size(_tpl, _c, 16, 16)
    _s2 = _img._template_at_size(_tpl, _c, 16, 16)
    check("skalierte Variante kommt aus dem Cache", _s1 is _s2 and _s1.shape[:2] == (16, 16))
    check("passende Groesse wird nicht skaliert",
          _img._template_at_size(_tpl, _c, 8, 8) is _c)

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

_clicks, _keys = [], []
_orig_click, _orig_key = _RS.safe_click, _RS.safe_key
_orig_shot, _orig_pillow = _RS.take_screenshot, _RS.PILLOW_AVAILABLE
_orig_failsafe = _RS.check_failsafe
_RS.safe_click = _RA.safe_click = lambda st, x, y, label="": (_clicks.append((x, y, label)), True)[1]
_RS.safe_key = _RA.safe_key = lambda st, key, label="": (_keys.append(key), True)[1]
_RS.check_failsafe = lambda st: False
_RS.PILLOW_AVAILABLE = True

def _color_step(hits, else_cfg, check_only=True):
    """Fuehrt einen Farb-Schritt aus. Returns (rueckgabe, klicks, tasten)."""
    _clicks.clear(); _keys.clear()
    _RS.take_screenshot = lambda region=None: _Pixel((10, 10, 10) if hits else (200, 200, 200))
    st = AutoClickerState(); st.config = _AC2()
    st.config.pixel_wait_timeout = 0.05
    st.config.pixel_check_interval = 0.01
    st.config.pixel_max_consecutive_timeouts = 0
    step = _SS(x=1, y=2, delay_before=0, name="Ziel",
                  wait_condition=_WCx(pixel=(5, 5), color=(10, 10, 10), check_only=check_only),
                  else_config=else_cfg)
    r = _RS.execute_step(st, step, 1, 3, "T")
    return r, [k for k in _clicks if k[2] == "Ziel"], list(_keys)

try:
    # Referenz: Bedingung erfuellt -> der Schritt klickt ganz normal
    _r, _own, _ = _color_step(True, None)
    check("checkcolor erfuellt -> eigener Klick laeuft", _r is True and len(_own) == 1)

    # Nicht erfuellt, kein else -> nur diesen Schritt ueberspringen (True!), kein Klick
    _r, _own, _ = _color_step(False, None)
    check("checkcolor nicht erfuellt -> Schritt uebersprungen, Phase laeuft weiter",
          _r is True and _own == [])

    # else skip -> kein eigener Klick
    _r, _own, _ = _color_step(False, _EC2(action="skip"))
    check("checkcolor + 'else skip' -> kein eigener Klick", _r is True and _own == [])

    # else <Punkt> -> NUR der Else-Punkt, nicht auch das eigene Ziel
    _r, _own, _ = _color_step(False, _EC2(action="click", x=999, y=999, name="E"))
    check("checkcolor + 'else <Punkt>' -> nur der Else-Punkt",
          _r is True and _own == [] and (999, 999, "else:E") in _clicks)

    # else key -> Taste statt Klick
    _r, _own, _t = _color_step(False, _EC2(action="key", key="enter"))
    check("checkcolor + 'else key' -> Taste statt eigenem Klick",
          _r is True and _own == [] and _t == ["enter"])

    # else restart/skip_cycle muessen weiterhin abbrechen
    _r, _own, _ = _color_step(False, _EC2(action="restart"))
    check("checkcolor + 'else restart' bricht ab", _r is False and _own == [])

    # Dasselbe auf dem Warte-Pfad: Timeout -> else, danach KEIN eigener Klick
    _r, _own, _ = _color_step(False, _EC2(action="skip"), check_only=False)
    check("Warten + Timeout + 'else skip' -> kein eigener Klick", _own == [])
    _r, _own, _ = _color_step(False, _EC2(action="click", x=999, y=999, name="E"),
                                 check_only=False)
    check("Warten + Timeout + 'else <Punkt>' -> nur der Else-Punkt",
          _own == [] and (999, 999, "else:E") in _clicks)
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
_clicked = []
_IS.take_screenshot = lambda region=None: object()
_IS._park_mouse_for_scan = lambda p: None
_IS.safe_click = lambda st, x, y, label="": (_clicked.append(label), True)[1]

def _immediate_run(items, slots, match):
    """treffer: dict slot_name -> item_name (was in diesem Slot erkannt wird)."""
    _clicked.clear()
    st = AutoClickerState(); st.config = _AC2()
    st.config.scan_click_immediate = True
    # reverse=False (Default): feste Slot-Reihenfolge, sonst haengt das Ergebnis
    # an der Prioritaet des zuerst gesehenen Items
    cfg = _ISC(name="inv", slots=slots, items=items, reverse=False)
    st.item_scans = {"inv": cfg}
    # Erkennung: Slot X erkennt Item Y. _check_profile_match sieht nur das Item,
    # daher ueber den gerade gescannten Slot mitgefuehrt.
    state_value = {"slot": None}
    _orig_exec = _IS.execute_item_scan
    def _prof(profile, img, tol, state, debug, label="gefunden",
              return_score=False):
        fits = match.get(state_value["slot"]) == profile.name
        return (fits, 1.0 if fits else 0.0) if return_score else fits
    _IS._check_profile_match = _prof
    def _exec(state, name, mode="all", slots_override=None, **kw):
        state_value["slot"] = slots_override[0].name if slots_override else None
        return _orig_exec(state, name, mode, slots_override, **kw)
    _IS.execute_item_scan = _exec
    _RS.execute_item_scan = _exec
    try:
        step = _SS(x=0, y=0, delay_before=0, name="S", item_scan="inv")
        _RS.execute_step(st, step, 1, 1, "T")
    finally:
        _IS.execute_item_scan = _orig_exec
        _RS.execute_item_scan = _orig_exec
    return list(_clicked)

try:
    _slots = [ItemSlot(name=f"S{i}", scan_region=(0, 0, 8, 8), click_pos=(i, i))
              for i in (1, 2, 3)]
    # Zwei Slots zeigen dieselbe Kategorie 'Erz' -> nur der erste darf geklickt werden
    _items = [ItemProfile(name="Kohle", marker_colors=[(1, 2, 3)], category="Erz", priority=1),
              ItemProfile(name="Eisen", marker_colors=[(4, 5, 6)], category="Erz", priority=5),
              ItemProfile(name="Fisch", marker_colors=[(7, 8, 9)], category="Nahrung", priority=1)]
    # S1 = Kohle (Erz, P1), S2 = Eisen (Erz, P5): das schlechtere Eisen faellt raus
    _r = _immediate_run(_items, _slots, {"S1": "Kohle", "S2": "Eisen", "S3": "Fisch"})
    check("Immediate: schlechteres Item derselben Kategorie faellt raus",
          _r == ["item:Kohle", "item:Fisch"])

    # Umgekehrt: erst Eisen (P5), dann Kohle (P1) — das BESSERE darf noch klicken
    _r = _immediate_run(_items, _slots, {"S1": "Eisen", "S2": "Kohle"})
    check("Immediate: besseres Item derselben Kategorie klickt nach",
          _r == ["item:Eisen", "item:Kohle"])

    # Andere Kategorien bleiben unabhaengig voneinander
    _r = _immediate_run(_items, _slots, {"S1": "Fisch", "S2": "Kohle"})
    check("Immediate: verschiedene Kategorien werden beide geklickt",
          _r == ["item:Fisch", "item:Kohle"])

    _slots[1].enabled = False
    _r = _immediate_run(_items, _slots, {"S2": "Fisch"})
    check("Immediate: ein ausgeschalteter Slot wird nicht besucht", _r == [])
    _slots[1].enabled = True

    # Reiner Lern-Scan (keine Items, learn_unknown=True) darf nicht vorzeitig aussteigen
    _st_learn = AutoClickerState(); _st_learn.config = _AC2()
    _st_learn.config.scan_click_immediate = True
    _st_learn.item_scans = {"lern": _ISC(name="lern", slots=_slots, items=[],
                                        learn_unknown=True, reverse=False)}
    _besucht = []
    _IS._check_profile_match = lambda *a, **k: (False, 0.0)
    _orig_learn = _IS._learn_unknown_slot_item
    _IS._learn_unknown_slot_item = lambda st, slot, img, dbg, cfg=None: _besucht.append(slot.name)
    try:
        _RS.execute_step(_st_learn, _SS(x=0, y=0, delay_before=0, name="L",
                                       item_scan="lern"), 1, 1, "T")
    finally:
        _IS._learn_unknown_slot_item = _orig_learn
    check("Immediate: reiner Lern-Scan besucht alle Slots",
          _besucht == ["S1", "S2", "S3"])

    # Tippfehler im Scan-Namen muss in BEIDEN Modi gemeldet werden, nicht nur im einen
    import contextlib as _cl   # _io steht schon oben
    def _silent_run(immediate):
        _st_t = AutoClickerState(); _st_t.config = _AC2()
        _st_t.config.scan_click_immediate = immediate
        _st_t.item_scans = {}
        _b = _io.StringIO()
        with _cl.redirect_stdout(_b):
            _RS.execute_step(_st_t, _SS(x=0, y=0, delay_before=0, name="S",
                                        item_scan="gibtsnicht"), 1, 1, "T")
        return "nicht gefunden" in _b.getvalue()
    check("fehlender Scan wird im Normal-Modus gemeldet", _silent_run(False))
    check("fehlender Scan wird auch im Immediate-Modus gemeldet", _silent_run(True))
finally:
    _IS._check_profile_match = _orig_prof
    _IS.take_screenshot = _orig_shot2
    _IS._park_mouse_for_scan = _orig_park
    _IS.safe_click = _orig_click2
    _RS.check_failsafe = _orig_failsafe2


# ------------------------------- Farb-Bedingung gilt fuer JEDE Aktion
section("Farb-Bedingung an der Taste (nicht nur am Klick)")
# Die Taste wurde vor der Farb-Bedingung abgefertigt: ein Trigger an so einem
# Schritt wurde ignoriert, die Aktion feuerte sofort. Jetzt wartet execute_step zentral
# fuer alle Aktions-Schritte an einer Stelle.
_orig_c3, _orig_k3 = _RS.safe_click, _RS.safe_key
_orig_shot3 = _RS.take_screenshot
_orig_p3, _orig_f3 = _RS.PILLOW_AVAILABLE, _RS.check_failsafe
_akt = {"klick": [], "action_key": []}
_shots = []

class _Pix2:
    def __init__(self, rgb): self._rgb = rgb
    def getpixel(self, _xy): return self._rgb

_RS.safe_click = _RA.safe_click = lambda st, x, y, label="": (_akt["klick"].append((x, y)), True)[1]
_RS.safe_key = _RA.safe_key = lambda st, k, label="": (_akt["action_key"].append(k), True)[1]
_RS.PILLOW_AVAILABLE = True
_RS.check_failsafe = lambda st: False

def _with_trigger(step, hits):
    for v in _akt.values():
        v.clear()
    _shots.clear()
    def _shot(region=None):
        _shots.append(region)
        return _Pix2((10, 10, 10) if hits else (200, 200, 200))
    _RS.take_screenshot = _shot
    st = AutoClickerState(); st.config = _AC2()
    st.config.pixel_wait_timeout = 0.05
    st.config.pixel_check_interval = 0.01
    st.config.pixel_max_consecutive_timeouts = 0
    _RS.execute_step(st, step, 1, 2, "T")
    return len(_shots) > 0, {k: list(v) for k, v in _akt.items()}

try:
    _wc3 = lambda **kw: _WCx(pixel=(5, 5), color=(10, 10, 10), **kw)

    # Trifft NICHT zu -> keine Aktion, egal welcher Schritt-Typ
    for _name, _step_local, _field in [
        ("Klick", _SS(x=1, y=2, delay_before=0, name="K", wait_condition=_wc3()), "klick"),
        ("Taste", _SS(x=0, y=0, delay_before=0, name="T", key_press="enter",
                      wait_condition=_wc3()), "action_key"),
    ]:
        _checked, _was = _with_trigger(_step_local, hits=False)
        check(f"{_name}-Schritt: Farb-Bedingung wird geprueft", _checked)
        check(f"{_name}-Schritt: Aktion feuert NICHT bei Nichttreffer", _was[_field] == [])

    # Trifft zu -> Aktion laeuft
    _, _was = _with_trigger(_SS(x=0, y=0, delay_before=0, name="T", key_press="enter",
                               wait_condition=_wc3()), hits=True)
    check("Taste-Schritt: Aktion laeuft bei Treffer", _was["action_key"] == ["enter"])

    # else greift jetzt auch hier — und ersetzt die Aktion
    _, _was = _with_trigger(_SS(x=0, y=0, delay_before=0, name="T", key_press="enter",
                               wait_condition=_wc3(check_only=True),
                               else_config=_EC2(action="click", x=99, y=99, name="E")),
                           hits=False)
    check("Taste-Schritt: else greift und ersetzt die Taste",
          _was["action_key"] == [] and _was["klick"] == [(99, 99)])

    # Ein Scan-Block, dessen Konfiguration noch fehlt ("" statt None), darf NICHT
    # bis zum Klick durchfallen. Genau das tat er: alle Scan-Zweige des Dispatchers
    # fragen per Truthiness ab, und die Koordinate eines Scan-Blocks ist (0, 0) —
    # ein Klick in die Bildschirmecke. Der Block ist erlaubt (man legt ihn an, um
    # die Stelle im Ablauf festzuhalten), also muss ihn die Laufzeit tragen.
    for _art_kind, _kw in [("Item-Scan", dict(item_scan="")),
                      ("Boss-Scan", dict(boss_scan="")),
                      ("Icon-Scan", dict(icon_scan="")),
                      ("Boss-Watcher", dict(boss_watcher=""))]:
        _, _was = _with_trigger(_SS(x=0, y=0, delay_before=0, **_kw), hits=True)
        check(f"{_art_kind} ohne Konfiguration klickt NICHT in die Ecke",
              _was["klick"] == [])

    # Ohne Farb-Bedingung bleibt es beim reinen Warten (keine Screenshots)
    _checked, _was = _with_trigger(_SS(x=0, y=0, delay_before=0, name="T",
                                       key_press="enter"), hits=True)
    check("Taste ohne Bedingung: kein Screenshot, Taste laeuft",
          not _checked and _was["action_key"] == ["enter"])

    # Anzeige muss die Bedingung zeigen, sonst ist sie im Editor unsichtbar
    check("Anzeige: Taste-Schritt zeigt die Farb-Bedingung",
          "Farbe DA bei (5,5)" in str(_SS(x=0, y=0, delay_before=0, key_press="enter",
                                          wait_condition=_wc3())))
    check("Anzeige: 'bis Farbe WEG' steht am Klick-Schritt",
          "Farbe WEG bei (5,5)" in str(_SS(x=1, y=1, delay_before=0,
                                           wait_condition=_wc3(until_gone=True))))
    check("Anzeige: ohne Bedingung weiterhin nur die Wartezeit",
          "Farbe" not in str(_SS(x=0, y=0, delay_before=3, key_press="enter")))
    # Jeder Schritt-Typ muss sich in der Liste als das zeigen, was er ist. Der
    # Icon-Scan hatte gar keinen Zweig und erschien als "sofort -> klicke (0, 0)".
    for _type, _kw, _expected in [
        ("Icon-Scan", dict(icon_scan="Mission"), "ICON-SCAN 'Mission'"),
        ("Boss-Scan", dict(boss_scan="B"), "BOSS-SCAN 'B'"),
        ("Watcher", dict(boss_watcher="W"), "BOSS-WATCHER 'W'"),
        ("Item-Scan", dict(item_scan="I"), "SCAN 'I'"),
        ("Screenshot", dict(screenshot_only=True), "SCREENSHOT"),
    ]:
        check(f"Anzeige: {_type} wird als solcher angezeigt",
              _expected in str(_SS(x=0, y=0, delay_before=0, **_kw)))
finally:
    _RS.safe_click = _RA.safe_click = _orig_c3
    _RS.safe_key = _RA.safe_key = _orig_k3
    _RS.take_screenshot = _orig_shot3
    _RS.PILLOW_AVAILABLE = _orig_p3
    _RS.check_failsafe = _orig_f3


# ------------------------------- Editor-Regel vs. Runtime-Verhalten fuer 'else'
section("'else' im Editor erlauben genau dort, wo die Runtime es auswertet")
# Der Editor verwarf 'boss X else skip' mit einer Warnung, obwohl der Boss-Scan die
# else-Aktion ausfuehrt. Dieser Test misst BEIDE Seiten und vergleicht sie, statt die
# Liste nur abzuschreiben: erlaubt der Editor else, muss die Aktion auch feuern.
from autoclicker.editors.sequence_editor.helpers import (
    apply_else_to_step as _apply_else, _can_else)
import io as _io2, contextlib as _cl2

_orig_c4, _orig_shot4 = _RS.safe_click, _RS.take_screenshot
_orig_f4, _orig_p4 = _RS.check_failsafe, _RS.PILLOW_AVAILABLE
_orig_bscan, _orig_iscan = _RS.execute_boss_scan, _RS.execute_icon_scan
_orig_iscan2 = _RS.execute_item_scan
_else_clicks = []
_RS.safe_click = _RA.safe_click = lambda st, x, y, label="": (_else_clicks.append((x, y)), True)[1]
_RS.check_failsafe = lambda st: False
_RS.PILLOW_AVAILABLE = True
# Alles schlaegt fehl -> falls else ausgewertet wird, muss es feuern
_RS.execute_boss_scan = lambda st, n: (False, None)
_RS.execute_icon_scan = lambda st, n: False
_RS.execute_item_scan = lambda st, n, m=None, slots_override=None: []
_RS.take_screenshot = lambda region=None: _Pix2((200, 200, 200))

def _else_fires(**kw):
    """Baut einen Schritt, haengt 'else <99,99>' an und prueft, ob es klickt."""
    _else_clicks.clear()
    step = _SS(x=1, y=2, delay_before=0, name="s", **kw)
    step.else_config = _EC2(action="click", x=99, y=99, name="E")
    st = AutoClickerState(); st.config = _AC2()
    st.config.pixel_wait_timeout = 0.05
    st.config.pixel_check_interval = 0.01
    st.config.pixel_max_consecutive_timeouts = 0
    st.config.llm_watcher_max_scans = 1
    st.boss_scans = {"X": _BSC(name="X")} if (kw.get("boss_scan") or kw.get("boss_watcher")) else {}
    with _cl2.redirect_stdout(_io2.StringIO()):
        _RS.execute_step(st, step, 1, 2, "T")
    return (99, 99) in _else_clicks

try:
    from autoclicker.models import BossScanConfig as _BSC
    _cases = {
        "Farb-Trigger": dict(wait_condition=_WCx(pixel=(5, 5), color=(10, 10, 10))),
        "Item-Scan":    dict(item_scan="X"),
        "Boss-Scan":    dict(boss_scan="X"),
        "Icon-Scan":    dict(icon_scan="X"),
        "Boss-Watcher": dict(boss_watcher="X"),
        "reiner Klick": dict(),
    }
    for _name, _kw in _cases.items():
        _step_local = _SS(x=1, y=2, delay_before=0, name="s", **_kw)
        _editor_allowed = _can_else(_step_local)
        _runtime_evaluates = _else_fires(**_kw)
        check(f"{_name}: Editor-Regel deckt sich mit der Runtime",
              _editor_allowed == _runtime_evaluates)

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
    # `init_steps` gehoert dazu, seit _run_loop_phases die Phasen-Position in den
    # Laufstatus schreibt: die haengt am Versatz "gibt es eine INIT-Phase?".
    def __init__(self, phases):
        self.loop_phases = phases
        self.init_steps = []


class _OneTick:
    """stop_event-Ersatz, der genau EINEN Schleifendurchlauf zulaesst.

    Der Watcher prueft `while not stop_event.is_set()` VOR dem Rumpf und wartet
    danach mit `stop_event.wait(10)`. Ein vorab gesetztes Event wuerde den Rumpf
    also nie ausfuehren, ein echtes Event 10 Sekunden kosten.
    """
    def __init__(self): self._done = False
    def is_set(self): return self._done
    def wait(self, timeout=None): self._done = True; return True   # -> break


def _watcher_tick(phases, h, m, pending=None, last=None):
    """Laesst den echten _schedule_watcher einen Tick zur Uhrzeit h:m laufen."""
    pending = {} if pending is None else pending
    last = {} if last is None else last

    class _FixedTime(_dt_mod.datetime):
        @classmethod
        def now(cls, tz=None): return cls(2026, 7, 31, h, m, 0)

    orig_dt = _WK.datetime
    _WK.datetime = _FixedTime
    try:
        with _cl2.redirect_stdout(_io2.StringIO()):
            _sw(phases, pending, last, _OneTick(), _th.Lock(), _th.Event())
    finally:
        _WK.datetime = orig_dt
    return pending


def _timer_run(phases, h, m):
    """Ein Watcher-Tick zur Uhrzeit h:m, danach ein echter Phasen-Durchlauf.

    Beide Seiten sind die Original-Funktionen; nur execute_step ist gestubbt und
    protokolliert, welche Phase wirklich drankam.
    """
    pending = _watcher_tick(phases, h, m)
    ran = []
    orig_step = _WK.execute_step
    _WK.execute_step = lambda s, step, i, n, ph: (ran.append(step), True)[1]
    try:
        with _cl2.redirect_stdout(_io2.StringIO()):
            _rlp(AutoClickerState(), _FakeSeq(phases), pending, _th.Lock(), "Zyklus 1", False)
    finally:
        _WK.execute_step = orig_step
    return ran


import datetime as _dt_mod
import autoclicker.runtime.worker as _WK

# A) eindeutige Namen — muss unveraendert funktionieren
_a = [_FakeLP("Morgen", "08:00"), _FakeLP("Abend", "20:00")]
check("eindeutige Namen: um 08:00 laeuft nur die Morgen-Phase",
      _timer_run(_a, 8, 0) == ["Morgen@08:00"])
_a = [_FakeLP("Morgen", "08:00"), _FakeLP("Abend", "20:00")]
check("eindeutige Namen: um 20:00 laeuft nur die Abend-Phase",
      _timer_run(_a, 20, 0) == ["Abend@20:00"])
_a = [_FakeLP("Morgen", "08:00"), _FakeLP("Abend", "20:00")]
check("eindeutige Namen: um 12:00 laeuft keine der beiden",
      _timer_run(_a, 12, 0) == [])

# B) gleicher Name (entsteht durch 'del' + 'add', Vorschlag ist 'Loop <len+1>')
_b = [_FakeLP("Loop 3", "08:00"), _FakeLP("Loop 3", "20:00")]
check("gleicher Name: um 20:00 laeuft die 20-Uhr-Phase (nicht die von 08:00)",
      _timer_run(_b, 20, 0) == ["Loop 3@20:00"])
_b = [_FakeLP("Loop 3", "08:00"), _FakeLP("Loop 3", "20:00")]
check("gleicher Name: um 08:00 laeuft die 08-Uhr-Phase",
      _timer_run(_b, 8, 0) == ["Loop 3@08:00"])
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
      _timer_run(_c, 9, 30) == ["Loop 2@09:30", "Loop 2@09:30"])

# D) ungeplante Phasen bleiben von alldem unberuehrt
_d = [_FakeLP("Immer", None), _FakeLP("Immer", None)]
check("Phasen ohne Startzeit laufen weiterhin jedes Mal",
      _timer_run(_d, 3, 45) == ["Immer@None", "Immer@None"])


# ------------------------------------------------------- Eindeutige Namen
section("Namensvergabe kollidiert nicht mit bestehenden Eintraegen")
from autoclicker.utils import unique_name as _en

check("freier Name bleibt unveraendert", _en("Slot 5", {"Slot 1": 1}) == "Slot 5")
check("belegter Name bekommt eine 2", _en("Slot 1", {"Slot 1": 1}) == "Slot 1 2")
check("zaehlt weiter bis frei", _en("Slot 1", {"Slot 1": 1, "Slot 1 2": 1}) == "Slot 1 3")
check("funktioniert auch mit einem Set", _en("A", {"A"}) == "A 2")
check("leeres Verzeichnis: Name bleibt", _en("A", {}) == "A")
# Der Fall aus der Praxis: 'Slot 2' geloescht -> len+1 zeigt auf das bestehende 'Slot 3'
_inventory = {"Slot 1": 1, "Slot 3": 1}
_proposal = f"Slot {len(_inventory) + 1}"
check("len+1 trifft nach einem 'del' einen bestehenden Namen",
      _proposal == "Slot 3" and _proposal in _inventory)
check("...und wird auf einen freien Namen ausgewichen",
      _en(_proposal, _inventory) == "Slot 3 2")

# Durchnummerierte Serien nehmen die erste FREIE Nummer statt einen Zaehler
# anzuhaengen — 'Slot 3 2' waere ein Name, den niemand lesen will.
from autoclicker.utils import next_free_name as _nf

check("Serie: leeres Verzeichnis beginnt bei 1", _nf("Slot", {}) == "Slot 1")
check("Serie: Luecke wird aufgefuellt", _nf("Slot", {"Slot 1": 1, "Slot 3": 1}) == "Slot 2")
check("Serie: lueckenlos zaehlt weiter",
      _nf("Slot", {"Slot 1": 1, "Slot 2": 1, "Slot 3": 1}) == "Slot 4")

# Der Ablauf der Auto-Erkennung: N Slots anlegen darf nie einen bestehenden treffen
_slots = {"Slot 1": "alt", "Slot 3": "alt"}
_assigned = []
for _ in range(4):
    _n = _nf("Slot", _slots)
    _slots[_n] = "neu"
    _assigned.append(_n)
check("Auto-Erkennung ueberschreibt keinen bestehenden Slot",
      _slots["Slot 1"] == "alt" and _slots["Slot 3"] == "alt")
check("Auto-Erkennung legt alle 4 Slots wirklich an", len(_slots) == 6)
check("Auto-Erkennung vergibt lesbare Namen",
      _assigned == ["Slot 2", "Slot 4", "Slot 5", "Slot 6"])

# Beide Helfer haben ihren Platz: fuer einen VORGEGEBENEN Namen gibt es keine Serie
check("unique_name bleibt fuer vorgegebene Namen zustaendig",
      _en("Beutel oben", {"Beutel oben": 1}) == "Beutel oben 2")

# --- Und niemand rechnet den Namen wieder selbst aus ---
# Die Regel stand nur in CLAUDE.md, und drei Editoren hielten sich nicht daran:
# `len(state.global_items) + 1` als Vorschlag schlug nach dem ersten Loeschen einen
# Namen vor, den es schon gab - worauf der Editor nach dem Ueberschreiben fragte,
# obwohl man nur "der naechste, bitte" gemeint hatte. Gesucht statt aufgezaehlt: eine
# Liste von drei Stellen prueft nur das, woran ohnehin jemand gedacht hat.
import re as _re_nf
_repo_nf = Path(__file__).resolve().parent.parent
_selbstgerechnet = []
for _pf_nf in sorted((_repo_nf / "autoclicker").rglob("*.py")):
    for _i_nf, _z_nf in enumerate(_pf_nf.read_text(encoding="utf-8").splitlines(), 1):
        # Ein Zaehler, der aus der GROESSE eines Namens-Verzeichnisses kommt. Genau das
        # ist der Fehler; `len(...) + 1` fuer eine Position oder Prioritaet nicht.
        if _re_nf.search(r"len\(\s*[\w.]*(global_items|global_slots|self\.items|"
                         r"self\.slots|loop_phases)\s*\)\s*\+\s*1", _z_nf):
            _selbstgerechnet.append(f"{_pf_nf.relative_to(_repo_nf).as_posix()}:{_i_nf}")
check("kein Editor rechnet einen Namensvorschlag aus der Bestandsgroesse",
      _selbstgerechnet == [])
if _selbstgerechnet:
    print("        " + ", ".join(_selbstgerechnet))


# ------------------------------------------------------------- Kalibrierung
section("Kalibrierung rechnet den Bestand auf ein neues Bildschirm-Layout um")

# Nach einem Windows-Neuaufbau sitzen die Monitore anders im virtuellen Desktop:
# alle gespeicherten Koordinaten sind um denselben Betrag verschoben. Ein neu
# gesetzter Referenzpunkt liefert die Differenz, der Rest wird daraus umgerechnet.
from autoclicker import import_export as _IE
from autoclicker.models import (ItemSlot as _KIS, ItemProfile as _KIP,
    BossScanConfig as _KBSC, BossProfile as _KBP, IconScanConfig as _KISC,
    Sequence as _KSEQ, SequenceStep as _KSS, LoopPhase as _KLP,
    WaitCondition as _KWC, ElseConfig as _KEC, ClickPoint as _KCP)

_t = _IE.transform_from_offset((100, 200), (140, 175))       # +40 / -25
check("ein Punkt ergibt eine reine Verschiebung",
      (_t["offset_x"], _t["offset_y"], _t["scale_x"], _t["scale_y"]) == (40, -25, 1.0, 1.0))
check("gleicher Punkt = Identitaet (nichts zu tun)",
      _IE.is_identity(_IE.transform_from_offset((5, 5), (5, 5))))
check("verschobener Punkt ist keine Identitaet", not _IE.is_identity(_t))
# Zwei Punkte koennen zusaetzlich skalieren — fuer den Fall geaenderter Aufloesung
check("zwei Punkte skalieren zusaetzlich",
      _IE.remap_point(400, 600, _IE.compute_transform((0,0), (1000,1000),
                                                      (0,0), (500,500))) == (200, 300))


def _calib_state():
    """Ein Bestand mit je einem Vertreter jeder Koordinaten-Art."""
    s = AutoClickerState()
    _points = [_KCP(x=100, y=200, name="Bank", id=1),
               _KCP(x=500, y=800, name="Ofen", id=2)]
    _slots = {"Slot 1": _KIS(name="Slot 1", scan_region=(10, 20, 60, 70),
                              click_pos=(35, 45))}
    _items = {"Erz": _KIP(name="Erz", confirm_point=_KCP(x=300, y=400, name=""))}
    _scan = _ISC(name="Inventar", slots=list(_slots.values()),
                 items=list(_items.values()),
                 owner_sequence="Seq")
    s.item_scans = {"Inventar": _scan}
    s.global_slots = _slots
    s.global_items = _items
    s.boss_scans = {"B": _KBSC(name="B", scan_region=(0, 0, 100, 100),
                               bosses=[_KBP(name="Drache", action="click",
                                            action_x=700, action_y=750)],
                               owner_sequence="Seq")}
    _icon = _KISC(name="I", scan_region=(5, 5, 55, 55), owner_sequence="Seq")
    _icon.action_x, _icon.action_y = 60, 65
    s.icon_scans = {"I": _icon}
    s.global_bosses = [_KBP(name="Global", action="click", action_x=11, action_y=22)]
    _step_local = _KSS(x=100, y=200, delay_before=0, name="klick", point_id=1)
    _trig = _KSS(x=0, y=0, delay_before=0, name="trigger",
                 wait_condition=_KWC(pixel=(640, 480), color=(1, 2, 3)),
                 else_config=_KEC(action="click", x=900, y=950))
    _shot = _KSS(x=0, y=0, delay_before=0, name="shot", screenshot_only=True,
                 screenshot_region=(1, 2, 3, 4))
    _seq = _KSEQ(name="Seq", init_steps=[_step_local],
                 loop_phases=[_KLP("L", [_trig, _shot], 1)], end_steps=[],
                 points=_points)
    s.active_sequence = _seq
    s.points = _seq.points
    return s, _step_local, _trig, _shot


# Die Vorschau darf nichts anfassen — sonst waere ein 'nein' beim Nachfragen wirkungslos
_vs, _, _, _ = _calib_state()
_preview = _IE.calibration_preview(_vs, _t)
check("Vorschau laesst den Bestand unveraendert",
      (_vs.points[0].x, _vs.points[0].y) == (100, 200))
check("Vorschau meldet vorher und nachher",
      ("Punkt #1 Bank", (100, 200), (140, 175)) in _preview)

# In einem temporaeren Verzeichnis arbeiten: calibrate_inventory SCHREIBT
_calib_tmp = tempfile.mkdtemp()
_calib_cwd = _os.getcwd()
_os.chdir(_calib_tmp)
try:
    _st, _step_local, _trig, _shot = _calib_state()
    with _cl2.redirect_stdout(_io2.StringIO()):
        _number = _IE.calibrate_inventory(_st, _t, with_scans=True, with_sequences=True)

    for _was, _actual, _expected_value in [
        ("Punkt (der Referenzpunkt selbst)", (_st.points[0].x, _st.points[0].y), (140, 175)),
        ("Punkt (ein anderer)", (_st.points[1].x, _st.points[1].y), (540, 775)),
        ("Slot-Scanregion", _st.global_slots["Slot 1"].scan_region, (50, -5, 100, 45)),
        ("Slot-Klickposition", _st.global_slots["Slot 1"].click_pos, (75, 20)),
        ("Item-Bestaetigungsklick", (_st.global_items["Erz"].confirm_point.x,
                                     _st.global_items["Erz"].confirm_point.y), (340, 375)),
        ("Boss-Scanregion", _st.boss_scans["B"].scan_region, (40, -25, 140, 75)),
        ("Boss-Klickaktion", (_st.boss_scans["B"].bosses[0].action_x,
                              _st.boss_scans["B"].bosses[0].action_y), (740, 725)),
        ("globaler Boss", (_st.global_bosses[0].action_x,
                           _st.global_bosses[0].action_y), (51, -3)),
        ("Icon-Scanregion", _st.icon_scans["I"].scan_region, (45, -20, 95, 30)),
        ("Icon-Klickaktion", (_st.icon_scans["I"].action_x,
                              _st.icon_scans["I"].action_y), (100, 40)),
        ("Trigger-Pixel ohne Punkt", _trig.wait_condition.pixel, (680, 455)),
        ("else-Klick ohne Punkt", (_trig.else_config.x, _trig.else_config.y), (940, 925)),
        ("Screenshot-Region", _shot.screenshot_region, (41, -23, 43, -21)),
    ]:
        check(f"kalibriert: {_was}", _actual == _expected_value)

    # Ein Schritt MIT point_id wird von der Kalibrierung selbst NICHT angefasst - sonst
    # wanderte er zweimal: einmal als Punkt und einmal als Schritt. Er landet trotzdem
    # richtig, weil er seine Stelle vom (bereits umgerechneten) Punkt holt.
    check("kalibriert: Schritt mit point_id wird nicht selbst verschoben",
          (_step_local.x, _step_local.y) == (100, 200))
    _IE_resolve = __import__("autoclicker.persistence", fromlist=["x"]).resolve_point_references
    _IE_resolve(_st, _st.active_sequence)
    check("kalibriert: Schritt mit point_id folgt dem Punkt (einfach, nicht doppelt)",
          (_step_local.x, _step_local.y) == (140, 175))

    # Umfang muss sich begrenzen lassen
    _st2, _step2, _, _ = _calib_state()
    with _cl2.redirect_stdout(_io2.StringIO()):
        _IE.calibrate_inventory(_st2, _t, with_scans=False, with_sequences=False)
    check("nur Punkte: Punkt wandert",
          (_st2.points[0].x, _st2.points[0].y) == (140, 175))
    check("nur Punkte: Slot bleibt unberuehrt",
          _st2.global_slots["Slot 1"].scan_region == (10, 20, 60, 70))
    check("nur Punkte: Sequenz-Schritt bleibt unberuehrt",
          (_step2.x, _step2.y) == (100, 200))

    # Slots getrennt ausklammerbar: eine aus der Maus abgeleitete Verschiebung ist
    # fuer eine Scan-Region nur eine Naeherung — dafuer gibt es slot_repair().
    # Nach einer Reparatur duerfen die Slots kein zweites Mal wandern.
    _st4, _step4, _, _ = _calib_state()
    with _cl2.redirect_stdout(_io2.StringIO()):
        _z4 = _IE.calibrate_inventory(_st4, _t, with_scans=True, with_sequences=True,
                                     with_slots=False)
    check("ohne Slots: Slot-Region bleibt exakt stehen",
          _st4.global_slots["Slot 1"].scan_region == (10, 20, 60, 70))
    check("ohne Slots: Slot-Klickposition bleibt stehen",
          _st4.global_slots["Slot 1"].click_pos == (35, 45))
    check("ohne Slots: die Zaehlung meldet keine Slots", _z4["slots"] == 0)
    check("ohne Slots: Boss-Scan wandert trotzdem",
          _st4.boss_scans["B"].scan_region == (40, -25, 140, 75))
    check("ohne Slots: Item-Bestaetigungsklick wandert trotzdem",
          (_st4.global_items["Erz"].confirm_point.x,
           _st4.global_items["Erz"].confirm_point.y) == (340, 375))
    # Der Schritt haengt am Punkt, und der ist umgerechnet - er landet also richtig,
    # ohne dass die Kalibrierung ihn selbst anfassen musste.
    _IE_resolve(_st4, _st4.active_sequence)
    check("ohne Slots: Sequenz-Schritt landet trotzdem richtig",
          (_step4.x, _step4.y) == (140, 175))

    # Sequenz-DATEIEN erfassen, nicht nur die geladenen Sequenzen
    from autoclicker.persistence import ensure_sequences_dir as _esd
    from autoclicker.config import SEQUENCES_DIR as _SQD
    _esd()
    _sq = Path(_SQD) / "nicht_geladen" / "sequence.json"
    _sq.parent.mkdir(parents=True, exist_ok=True)
    _sq.write_text(json.dumps({
        "name": "nicht_geladen", "schema_version": 2, "total_cycles": 1,
        "init_steps": [{"x": 100, "y": 200, "delay_before": 0, "name": "a"}],
        "loop_phases": [{"name": "L", "repeat": 1, "steps": [
            {"x": 10, "y": 20, "delay_before": 0, "name": "b",
             "wait_pixel": [640, 480], "wait_color": [1, 2, 3],
             "else_action": "click", "else_x": 900, "else_y": 950}]}],
        "end_steps": []}), encoding="utf-8")
    _st3 = AutoClickerState()
    with _cl2.redirect_stdout(_io2.StringIO()):
        _IE.calibrate_inventory(_st3, _t, with_scans=False, with_sequences=True)
    _d = json.loads(_sq.read_text(encoding="utf-8"))
    _s0, _s1 = _d["init_steps"][0], _d["loop_phases"][0]["steps"][0]
    check("nicht geladene Sequenzdatei wird mitgerechnet",
          (_s0["x"], _s0["y"]) == (140, 175))
    check("Trigger-Pixel in der Datei", _s1["wait_pixel"] == [680, 455])
    check("else-Klick in der Datei", (_s1["else_x"], _s1["else_y"]) == (940, 925))
    check("Farben bleiben unangetastet", _s1["wait_color"] == [1, 2, 3])

    # Hier stand die Gegenprobe zu `_seq_v3_to_v4` + `_als_dicts`: eine Sequenz auf
    # Schema 2 ohne points.json, deren Koordinaten die Migration in neu angelegte
    # Punkte zog. Beides ist geloescht - ohne Kette legt keine Migration mehr Punkte
    # an, also gibt es auch nichts mehr auf Platte zu schreiben.

    # Versatz von Hand nachziehen: mit der Maus trifft man den Pixel nicht genau.
    # Weiss man, dass eine Achse stimmt, ist eine eingetippte 0 genauer.
    from autoclicker.editors.import_export_editor import _adjust_offset as _va
    import autoclicker.editors.import_export_editor as _IEE

    def _adjust_with(inputs):
        consequence = list(inputs)
        _o = _IEE.safe_input
        _IEE.safe_input = lambda _p="": consequence.pop(0)
        try:
            with _cl2.redirect_stdout(_io2.StringIO()):
                return _va({"scale_x": 1.0, "scale_y": 1.0,
                            "offset_x": 2, "offset_y": -25})
        finally:
            _IEE.safe_input = _o

    _r = _adjust_with(["", ""])
    check("Versatz anpassen: Enter behaelt beide Achsen",
          (_r["offset_x"], _r["offset_y"]) == (2, -25))
    _r = _adjust_with(["0", ""])
    check("Versatz anpassen: X auf 0, Y bleibt gemessen",
          (_r["offset_x"], _r["offset_y"]) == (0, -25))
    _r = _adjust_with(["0", "0"])
    check("Versatz anpassen: beide auf 0 -> Identitaet",
          _IE.is_identity(_r))
    _r = _adjust_with(["", "-24"])
    check("Versatz anpassen: Y von Hand korrigiert",
          (_r["offset_x"], _r["offset_y"]) == (2, -24))
    _r = _adjust_with(["-3,5", ""])
    check("Versatz anpassen: Komma-Zahl wird gerundet", _r["offset_x"] == -4)
    _r = _adjust_with(["quatsch", "5", ""])
    check("Versatz anpassen: Fehleingabe fragt erneut statt abzubrechen",
          _r is not None and _r["offset_x"] == 5)
    check("Versatz anpassen: Ergebnis bleibt eine reine Verschiebung",
          _r["scale_x"] == 1.0 and _r["scale_y"] == 1.0)

    # Gegen-Verschiebung muss exakt zum Ausgangswert zurueckfuehren
    with _cl2.redirect_stdout(_io2.StringIO()):
        _IE.calibrate_inventory(_st3, _IE.transform_from_offset((140, 175), (100, 200)),
                               with_scans=False, with_sequences=True)
    _d2 = json.loads(_sq.read_text(encoding="utf-8"))
    check("Rueckrechnung trifft den Ausgangswert genau",
          (_d2["init_steps"][0]["x"], _d2["init_steps"][0]["y"]) == (100, 200))
finally:
    _os.chdir(_calib_cwd)


# Hier stand die Sektion "Start-Durchgang: zwei Altdateien teilen sich ihre Punkte".
# Sie mass, dass die Punkte-Liste durch die Sequenz-Migration DURCHGEREICHT und nicht
# kopiert wurde - sonst haetten zwei Altdateien dieselben IDs erneut vergeben. Mit
# `_seq_v3_to_v4` und `_als_dicts` ist der gemessene Mechanismus geloescht: keine
# Migration legt mehr Punkte an, also kann es auch keine doppelten IDs von dort geben.


# -------------------------------------------------------- Slot-Reparatur
section("Slot-Reparatur uebernimmt nur eine eindeutige Zuordnung")

# Eine Maus-Position trifft den Pixel nie genau; bei einer Scan-Region zaehlt das.
# Die Reparatur misst die Slots deshalb neu — darf die neuen Koordinaten aber nur
# uebernehmen, wenn die Zuordnung alt->neu zweifelsfrei ist.
from autoclicker.editors.slot_editor import _check_assignment as _zp

_INSET = 2
_BASIS = [(100, 100, 150, 150), (160, 100, 210, 150),
          (220, 100, 270, 150), (100, 160, 150, 210)]


def _rep_slots(regions):
    return [_KIS(name=f"Slot {i+1}", scan_region=r,
                 click_pos=((r[0]+r[2])//2, (r[1]+r[3])//2))
            for i, r in enumerate(regions)]


def _rep_rects(regions, dx=0, dy=0):
    """Macht aus gespeicherten Regionen wieder rohe Erkennungs-Rechtecke (x,y,w,h)."""
    return [(x1 - _INSET + dx, y1 - _INSET + dy,
             (x2 - x1) + 2 * _INSET, (y2 - y1) + 2 * _INSET)
            for (x1, y1, x2, y2) in regions]


_p, _v, _ = _zp(_rep_slots(_BASIS), _rep_rects(_BASIS), _INSET, (0, 0))
check("unveraendert: Zuordnung gilt, Versatz ist null", bool(_p) and _v == (0, 0))

_p, _v, _ = _zp(_rep_slots(_BASIS), _rep_rects(_BASIS, 37, -14), _INSET, (0, 0))
check("durchgaengige Verschiebung wird uebernommen", bool(_p) and _v == (37, -14))
check("jeder Slot bekommt seine eigene gemessene Region",
      _p[0][1] == (137, 86, 187, 136) and _p[1][1] == (197, 86, 247, 136))
check("Namen bleiben an ihren Slots", [s.name for s, _ in _p] ==
      ["Slot 1", "Slot 2", "Slot 3", "Slot 4"])

# Ablehnen, wo die Zuordnung geraten waere
_p, _, _m = _zp(_rep_slots(_BASIS), _rep_rects(_BASIS[:3], 37, -14), _INSET, (0, 0))
check("ein Slot weniger erkannt -> abgelehnt", not _p and _m)
_p, _, _ = _zp(_rep_slots(_BASIS), _rep_rects(_BASIS + [(280, 100, 330, 150)]),
               _INSET, (0, 0))
check("ein Slot zu viel erkannt -> abgelehnt", not _p)

_verdreht = _rep_rects([_BASIS[1], _BASIS[0], _BASIS[2], _BASIS[3]], 37, -14)
_p, _, _ = _zp(_rep_slots(_BASIS), _verdreht, _INSET, (0, 0))
check("vertauschte Reihenfolge -> abgelehnt (Versaetze streuen)", not _p)

_larger = [(x, y, int(w * 1.4), int(h * 1.4)) for (x, y, w, h) in _rep_rects(_BASIS, 10, 10)]
_p, _, _m = _zp(_rep_slots(_BASIS), _larger, _INSET, (0, 0))
check("andere Slot-Groesse -> abgelehnt (Aufloesung, nicht Verschiebung)",
      not _p and any("Aufloesung" in m for m in _m))

# Toleranzgrenze: Erkennungs-Rauschen ja, Ausreisser nein
_leicht = _rep_rects(_BASIS, 37, -14)
_leicht[2] = (_leicht[2][0] + 3, _leicht[2][1], _leicht[2][2], _leicht[2][3])
_p, _, _ = _zp(_rep_slots(_BASIS), _leicht, _INSET, (0, 0))
check("3 px Rauschen bleiben in der Toleranz", bool(_p))

_grob = _rep_rects(_BASIS, 37, -14)
_grob[2] = (_grob[2][0] + 9, _grob[2][1], _grob[2][2], _grob[2][3])
_p, _, _ = _zp(_rep_slots(_BASIS), _grob, _INSET, (0, 0))
check("9 px Ausreisser -> abgelehnt", not _p)

# Der Offset der markierten Region muss herausgerechnet werden, sonst haengt das
# Ergebnis davon ab, wie der Nutzer den Bereich gezogen hat
_p, _v, _ = _zp(_rep_slots(_BASIS), _rep_rects(_BASIS, -50, -50), _INSET, (50, 50))
check("Offset der markierten Region wird eingerechnet", _v == (0, 0))


# ------------------------------------------------- Tasten in IDE-Konsolen
section("Menue-Tasten wirken auch in IDE-Konsolen (kein msvcrt)")

# _read_key_polling erkennt nur, was in _VK_MAP steht: Pfeile, Enter, Escape,
# Ziffern — KEINE Buchstaben. Ein getipptes 'a' fiel durch, das Enter danach kam
# als 'enter' an, und jede Taste landete auf demselben Zweig: im Punkte-Durchgang
# lief 'a' (zurueck) vorwaerts, im manuellen Modus waren 's'/'c'/'q' unerreichbar.
import autoclicker.utils.io as _IO

check("_VK_MAP enthaelt weiterhin keine Buchstaben (nur fuer interactive_select)",
      not any(0x41 <= _vk <= 0x5A for _vk in _IO._VK_MAP))
check("read_command kennt alle 26 Buchstaben", len(_IO._VK_LETTERS) == 26)
check("die Befehlstasten w/a/s/c/d/q sind dabei",
      all(_b in _IO._VK_LETTERS.values() for _b in "wascdq"))

# In der IDE-Konsole liest read_command per Polling MIT den Buchstaben — ohne Enter.
_orig_real = _IO._REAL_CONSOLE
_orig_poll = _IO._read_key_polling
_seen = {}
try:
    _IO._REAL_CONSOLE = False          # IDE-Konsole erzwingen
    _IO._read_key_polling = (lambda extra=None, timeout=None:
                             _seen.update(extra=extra, timeout=timeout) or "a")
    check("IDE-Konsole: read_command liefert den Buchstaben direkt",
          _IO.read_command() == "a")
    check("IDE-Konsole: die Buchstaben werden ans Polling durchgereicht",
          _seen["extra"] is _IO._VK_LETTERS)
    # Die Zeitgrenze des Gates kommt ebenfalls dort an — ohne sie blockierte
    # das Gate in der Konsole, und CTRL+ALT+G kaeme nie zum Zug.
    _IO.read_command(timeout=0.2)
    check("IDE-Konsole: die Zeitgrenze wird ans Polling durchgereicht",
          _seen["timeout"] == 0.2)
finally:
    _IO._REAL_CONSOLE = _orig_real
    _IO._read_key_polling = _orig_poll

# Der eigentliche Beweis: der Navigationspfad durch walk_points
import autoclicker.runtime.debug as _DBG
from autoclicker.models import ClickPoint as _WCP


def _walk_path(keys_list):
    """Gibt die Reihenfolge der besuchten Punkt-Indizes zurueck."""
    st = AutoClickerState()
    st.points = [_WCP(x=i * 10, y=i * 10, name=f"P{i}", id=i) for i in range(1, 6)]
    besucht = []
    consequence = list(keys_list)
    _o_read, _o_cursor = _DBG.read_command, _DBG.set_cursor_pos
    _DBG.read_command = lambda *a, **k: consequence.pop(0) if consequence else "q"
    _DBG.set_cursor_pos = lambda x, y: besucht.append(x // 10)
    try:
        with _cl2.redirect_stdout(_io2.StringIO()):
            _DBG.walk_points(st)
    finally:
        _DBG.read_command, _DBG.set_cursor_pos = _o_read, _o_cursor
    return besucht


check("walk: 'w' blaettert vorwaerts",
      _walk_path(["w", "w", "w", "q"]) == [1, 2, 3, 4])
check("walk: 'a' blaettert ZURUECK (lief vorher vorwaerts)",
      _walk_path(["w", "w", "a", "q"]) == [1, 2, 3, 2])
check("walk: 'a' am Anfang bleibt beim ersten Punkt",
      _walk_path(["a", "a", "q"]) == [1, 1, 1])
check("walk: Enter blaettert vorwaerts", _walk_path(["enter", "enter", "q"]) == [1, 2, 3])
check("walk: 'q' beendet sofort", _walk_path(["q"]) == [1])
check("walk: hin und zurueck landet wieder am Ausgangspunkt",
      _walk_path(["w", "a", "q"]) == [1, 2, 1])
# Pfeiltasten gleichwertig — die kommen in IDE-Konsolen ohnehin an
check("walk: Pfeil rechts blaettert vorwaerts",
      _walk_path(["right", "right", "q"]) == [1, 2, 3])
check("walk: Pfeil links blaettert zurueck",
      _walk_path(["right", "right", "left", "q"]) == [1, 2, 3, 2])
check("walk: Pfeil runter/hoch wirken wie rechts/links",
      _walk_path(["down", "down", "up", "q"]) == [1, 2, 3, 2])
check("walk: 'd' blaettert vorwaerts (WASD)",
      _walk_path(["d", "d", "q"]) == [1, 2, 3])
check("walk: ESC beendet wie 'q'", _walk_path(["escape"]) == [1])
# Fehlgriff darf nicht weiterblaettern — sonst sucht man die Stelle neu
check("walk: unbekannte Taste bleibt stehen",
      _walk_path(["x", "x", "w", "q"]) == [1, 1, 1, 2])


# 'n' setzt den Punkt auf die aktuelle Mausposition — damit repariert man eine Sequenz,
# ohne Wartezeiten/else/Scans anzufassen: Schritte mit point_id ziehen automatisch nach.
def _walk_set(keys_list, mouse, color=(9, 9, 9)):
    """Gibt die Punkte nach dem Durchgang zurueck."""
    st = AutoClickerState()
    st.points = [_WCP(x=10, y=10, name="P1", id=1, color=(1, 2, 3)),
                 _WCP(x=20, y=20, name="P2", id=2)]
    consequence = list(keys_list)
    _o_read, _o_cursor = _DBG.read_command, _DBG.set_cursor_pos
    _o_get = _DBG.get_cursor_pos
    import autoclicker.imaging as _IMG
    import autoclicker.persistence as _PERS
    _o_pix, _o_save = _IMG.get_pixel_color, _PERS.save_points
    _DBG.read_command = lambda *a, **k: consequence.pop(0) if consequence else "q"
    _DBG.set_cursor_pos = lambda x, y: None
    _DBG.get_cursor_pos = lambda: mouse
    _IMG.get_pixel_color = lambda x, y: color
    _PERS.save_points = lambda s: None
    try:
        with _cl2.redirect_stdout(_io2.StringIO()):
            _DBG.walk_points(st)
    finally:
        _DBG.read_command, _DBG.set_cursor_pos = _o_read, _o_cursor
        _DBG.get_cursor_pos = _o_get
        _IMG.get_pixel_color, _PERS.save_points = _o_pix, _o_save
    return st.points


_pk = _walk_set(["n", "q"], mouse=(77, 88))
check("walk 'n': Punkt uebernimmt die Mausposition",
      (_pk[0].x, _pk[0].y) == (77, 88))
check("walk 'n': Farbe wird mitgezogen (sie gehoert zur Position)",
      _pk[0].color == (9, 9, 9))
check("walk 'n': andere Punkte bleiben unberuehrt",
      (_pk[1].x, _pk[1].y) == (20, 20))
check("walk 'n': Name und ID bleiben (Schritte zeigen per ID darauf)",
      _pk[0].id == 1 and _pk[0].name == "P1")

# Punkt ohne Farbe bekommt auch keine — sonst schleicht sich ein Trigger ein,
# den niemand gesetzt hat
_pk = _walk_set(["w", "n", "q"], mouse=(55, 66))
check("walk 'n': Punkt ohne Farbe bekommt keine", _pk[1].color is None)
check("walk 'n': Position trotzdem gesetzt", (_pk[1].x, _pk[1].y) == (55, 66))

# Maus steht noch auf der alten Stelle -> nichts tun, nicht weiterblaettern
_pk = _walk_set(["n", "q"], mouse=(10, 10))
check("walk 'n' ohne Mausbewegung aendert nichts",
      (_pk[0].x, _pk[0].y) == (10, 10))

# 'f' liest nur die Farbe neu, die Position bleibt
_pk = _walk_set(["f", "q"], mouse=(77, 88), color=(4, 5, 6))
check("walk 'f': nur die Farbe wird neu gelesen",
      _pk[0].color == (4, 5, 6) and (_pk[0].x, _pk[0].y) == (10, 10))

# Manueller Modus: s/c/q waren unerreichbar, jede Taste fuehrte den Schritt aus
from autoclicker.runtime.debug import (GATE_RUN as _GR, GATE_SKIP as _GS,
                                       GATE_STOP as _GT)


def _step_gate_with(key):
    st = AutoClickerState()
    st.step_mode = True
    step = _SS(x=5, y=5, delay_before=0, name="s")
    _o_read, _o_cursor = _DBG.read_command, _DBG.set_cursor_pos
    _DBG.read_command = lambda *a, **k: key
    _DBG.set_cursor_pos = lambda x, y: None
    try:
        with _cl2.redirect_stdout(_io2.StringIO()):
            return _DBG.step_gate(st, step, "L", 1, 1), st
    finally:
        _DBG.read_command, _DBG.set_cursor_pos = _o_read, _o_cursor


_g, _ = _step_gate_with("w")
check("manuell: 'w' fuehrt den Schritt aus", _g == _GR)
_g, _ = _step_gate_with("enter")
check("manuell: Enter fuehrt den Schritt aus", _g == _GR)
_g, _ = _step_gate_with("s")
check("manuell: 's' ueberspringt (war unerreichbar)", _g == _GS)
_g, _st_c = _step_gate_with("c")
check("manuell: 'c' laeuft normal weiter (war unerreichbar)",
      _g == _GR and _st_c.step_mode is False)
_g, _st_q = _step_gate_with("q")
check("manuell: 'q' bricht ab (war unerreichbar)",
      _g == _GT and _st_q.stop_event.is_set())
_g, _ = _step_gate_with("right")
check("manuell: Pfeil rechts fuehrt aus", _g == _GR)
_g, _ = _step_gate_with("down")
check("manuell: Pfeil runter ueberspringt", _g == _GS)
_g, _st_e = _step_gate_with("escape")
check("manuell: ESC bricht ab", _g == _GT and _st_e.stop_event.is_set())


# --------------------------------------------------- Plattform-Grenze
section("Betriebssystem-Abhaengigkeiten liegen nur in der Plattform-Schicht")

# Wer spaeter auf Linux portiert, muss genau diese Dateien anfassen — und sonst keine.
# Ohne diesen Test wandert der naechste GetSystemMetrics-Aufruf wieder irgendwohin:
# vorher lag dieselbe Abfrage fuenfmal im Baum (imaging, item_scan, diagnose,
# scan_studio, console), jedes Mal mit eigenen SM_*-Konstanten.
import re as _re_p

PLATTFORM_MODULE = {
    "autoclicker/platforms/windows.py",  # WinAPI-Backend
    "autoclicker/utils/io.py",      # Tastendruck-Erfassung (msvcrt / GetAsyncKeyState)
    "autoclicker/utils/console.py", # Konsolen-Erkennung, Fenstertitel, ANSI-Freischaltung
}
_WIN_PATTERN = _re_p.compile(r"ctypes\.(windll|WinDLL|WINFUNCTYPE)|\bwintypes\b|\bmsvcrt\b")

_package = Path(__file__).resolve().parent.parent / "autoclicker"
_outlier = []
for _path in sorted(_package.rglob("*.py")):
    _rel = _path.relative_to(_package.parent).as_posix()
    if _rel in PLATTFORM_MODULE:
        continue
    _matches = _WIN_PATTERN.findall(_path.read_text(encoding="utf-8"))
    if _matches:
        _outlier.append(f"{_rel} ({len(_matches)}x)")

check("kein Windows-Aufruf ausserhalb der Plattform-Schicht",
      _outlier == [])
if _outlier:
    print("        " + "; ".join(_outlier))

# Die Gegenrichtung: steht ein Modul auf der Liste, das gar nichts Windows-Spezifisches
# mehr enthaelt, gehoert es runter — sonst waechst die Liste zur Fiktion.
_superfluous = [m for m in sorted(PLATTFORM_MODULE)
                  if not _WIN_PATTERN.search((_package.parent / m).read_text(encoding="utf-8"))]
check("jedes gelistete Plattform-Modul ist auch wirklich eines", _superfluous == [])
if _superfluous:
    print("        unnoetig gelistet: " + ", ".join(_superfluous))

# Die Geometrie-Helfer muessen ohne Windows sauber None/Fallback liefern, sonst kann der
# Rest des Baums sie nicht gefahrlos aufrufen.
#
# Auf echtem Windows liefern sie dagegen echte Werte - dort ist "None" kein Erfolg,
# sondern ein Fehler. Frueher stand hier nur der Stub-Fall; damit war die Suite auf der
# Zielplattform dauerhaft rot (4x FAIL), und wer unter Windows entwickelt, konnte echte
# Regressionen nicht mehr von diesem Rauschen unterscheiden. Beide Seiten pruefen.
from autoclicker.winapi import (get_virtual_desktop, get_virtual_origin,
                                get_screen_center, get_screen_size)
_rect = get_virtual_desktop()
if sys.platform == "win32":
    check("get_virtual_desktop liefert ein Rechteck mit Flaeche",
          _rect is not None and _rect[2] > _rect[0] and _rect[3] > _rect[1])
    _size = get_screen_size()
    check("get_screen_size liefert eine positive Groesse",
          _size is not None and _size[0] > 0 and _size[1] > 0)
    # Der Ursprung darf negativ sein - ein Monitor links vom bzw. ueber dem primaeren
    # ist der Normalfall, nicht die Ausnahme.
    check("get_virtual_origin ist die linke obere Ecke des Rechtecks",
          get_virtual_origin() == (_rect[0], _rect[1]))
    _middle = get_screen_center()
    check("get_screen_center liegt im virtuellen Desktop",
          _rect[0] <= _middle[0] <= _rect[2] and _rect[1] <= _middle[1] <= _rect[3])
else:
    check("get_virtual_desktop meldet None statt einer 0x0-Flaeche", _rect is None)
    check("get_screen_size meldet None statt 0x0", get_screen_size() is None)
    check("get_virtual_origin faellt auf (0, 0) zurueck", get_virtual_origin() == (0, 0))
    check("get_screen_center faellt auf eine brauchbare Mitte zurueck",
          get_screen_center() == (960, 540))


# ------------------------------------------- Klick-Schritte referenzieren Punkte
section("Jeder Klick-Schritt zeigt per point_id auf seinen Punkt")

# Der Punkt ist die Wahrheit, der Schritt verweist nur. Haelt ein Schritt seine
# Koordinaten selbst, zieht ein verschobener Punkt ihn NICHT mit — und genau dafuer
# gibt es point_id. Der Recorder legte frueher beides unabhaengig an: Schritte ohne
# Referenz, Punkte hinterher. Die Migration verknuepft nur ALTE Dateien, eine frische
# Aufnahme ist schon gestempelt und blieb deshalb dauerhaft unverknuepft.
from autoclicker.editors.sequence_recorder import points_for_events as _pfe
from autoclicker.editors.sequence_recorder import recording_file as _aufnahme_datei
from autoclicker.models import (RecordEvent as _RE, REC_CLICK as _R_CLICK,
                                REC_KEY as _R_KEY, REC_WAIT_COLOR as _R_WAIT)

_st_rec = AutoClickerState()
_events = [_RE(_R_CLICK, 0.0, 100, 200, (1, 2, 3)),
           _RE(_R_CLICK, 1.0, 300, 400, None),
           _RE(_R_CLICK, 2.0, 100, 200, (1, 2, 3))]
_map, _new = _pfe(_events)
check("Recorder legt fuer jede Position einen Punkt an", len(_new) == 2)
check("gleiche Position zweimal geklickt -> nur ein Punkt", len(_new) == 2)
check("jedes Ereignis mit Stelle hat eine ID", set(_map) == {0, 1, 2})
check("beide Klicks auf dieselbe Stelle teilen sich die ID",
      _map[0] == _map[2] == _new[0].id)

# Der Punkt-Pool einer anderen aktiven Sequenz darf nicht in die neue Aufnahme
# geraten. Gleiche IDs sind erlaubt, weil IDs nur innerhalb einer Sequenz gelten.
# **Gemessen wird das an der SIGNATUR, nicht an einem Ergebnis**: die Funktion
# nahm einen `state` entgegen und benutzte ihn nie - ein Test, der einen
# uebergebenen Pool "ignoriert" sieht, prueft dann nichts. Ohne den Parameter
# gibt es den Weg gar nicht mehr, und das ist die staerkere Zusicherung
# (dieselbe Bauart wie beim geloeschten `scan_reverse`).
import inspect as _insp_rec
_sig_pfe = list(_insp_rec.signature(_pfe).parameters)
check("points_for_events nimmt Ereignisse und optional einen Punkte-Bestand",
      _sig_pfe == ["events", "existing"])
check("kein state in der Signatur - der Pool kann nur EXPLIZIT mitgegeben werden",
      "state" not in _sig_pfe)
_map2, _points2 = _pfe(_events)
check("Recorder baut ohne Bestand einen eigenen Punkt-Pool", len(_points2) == 2)

# Bei einer Einfuege-Aufnahme ("Ab hier aufnehmen") ist ein mitgegebener
# Bestand dagegen gewollt: ein Klick auf einen schon vorhandenen Punkt DER
# ZIELSEQUENZ soll ihn wiederverwenden statt einen zweiten mit derselben
# Stelle anzulegen - und die naechste ID darf nicht mit einer vorhandenen
# kollidieren.
_existing_pts_rec = [ClickPoint(100, 200, "P5", 5, color=(1, 2, 3))]
_map3, _new3 = _pfe(_events, existing=_existing_pts_rec)
check("ein Klick auf einen vorhandenen Punkt bekommt dessen ID",
      _map3[0] == 5 and _map3[2] == 5)
check("nur der wirklich neue Klick liefert einen neuen Punkt", len(_new3) == 1)
check("die neue ID liegt hinter der hoechsten vorhandenen", _new3[0].id == 6)
check("der uebergebene Bestand bleibt unveraendert", len(_existing_pts_rec) == 1)

# --- Ein Punkt heisst P<ID>, nicht nach seiner Sequenz --------------------
# Er trug den Sequenznamen als Vorsatz ("aufnahme_214638 3"). Seit die Punkte
# IN ihrer sequence.json stehen, sagt der nichts mehr - und beim Umbenennen der
# Sequenz wird er falsch, wobei jeder Punkt einzeln nachzuziehen waere.
check("die Namen sind kurz und tragen ihre ID",
      [pt.name for pt in _points2] == ["P1", "P2"])
check("und die Nummer im Namen IST die ID (nicht der Ereignis-Index)",
      all(pt.name == f"P{pt.id}" for pt in _points2))
check("die Herkunft nennt keine Sequenz mehr",
      {pt.source for pt in _points2} == {"Aufnahme"})

# Die Nummer folgt der ID, nicht der Stelle im Ereignisstrom: eine Aufnahme mit
# Tastendruecken dazwischen haette sonst P1, P4, P7 - und die Liste schreibt
# #1, #2, #3 daneben.
_ev_gappy = [_RE(_R_KEY, 0.0, key="a"),
               _RE(_R_CLICK, 1.0, 10, 20, (1, 2, 3)),
               _RE(_R_KEY, 2.0, key="b"),
               _RE(_R_CLICK, 3.0, 900, 900, (4, 5, 6))]
_map4, _points4 = _pfe(_ev_gappy)
check("Tastendruecke dazwischen verschieben die Nummern nicht",
      [pt.name for pt in _points4] == ["P1", "P2"])

# **Wer einen Punktnamen ERFINDET, nimmt dasselbe Schema.** Drei Wege legen
# Punkte an, ohne dass jemand einen Namen tippt - die Aufnahme, CTRL+ALT+A und
# der Rueckfall in `point_for_position()`. Sie standen auf `<Sequenz> <i>`, `P<id>`
# und `Punkt <id>`: dieselbe Frage, drei Antworten, und in EINER Liste
# untereinander. Gefragt werden deshalb beide erreichbaren Wege und verglichen -
# nicht die Implementierung abgeschrieben.
from autoclicker.persistence.sequences import point_for_position as _pfs
_st_names = AutoClickerState()
_seq_names = _KSEQ(name="N", init_steps=[], end_steps=[], loop_phases=[], points=[])
_st_names.active_sequence = _seq_names
_st_names.points = _seq_names.points
_id_a = _pfs(_st_names, 10, 20, (1, 2, 3))
_id_b = _pfs(_st_names, 900, 900, (4, 5, 6))
_names_pfs = [pt.name for pt in _st_names.points]
check("der Rueckfall in point_for_position nimmt P<ID>",
      _names_pfs == [f"P{_id_a}", f"P{_id_b}"])
check("und damit dasselbe Schema wie die Aufnahme",
      [n[0] for n in _names_pfs] == [n[0] for n in ("P1", "P2")])
# Ein uebergebener Name gewinnt weiterhin - der Rueckfall ist ein Rueckfall.
_id_c = _pfs(_st_names, 500, 500, None, name="Bankschalter")
check("ein getippter Name wird nicht ueberschrieben",
      next(pt.name for pt in _st_names.points if pt.id == _id_c) == "Bankschalter")
_capture_target = _aufnahme_datei("Neue Aufnahme")
check("Recorder speichert im Besitzordner der Sequenz",
      _capture_target.parts[-3:] == ("sequences", "neue_aufnahme", "sequence.json"))
check("Recorder legt keine direkte JSON-Datei mehr unter sequences/ an",
      _capture_target.parent.name != "sequences")

# --- Fast dieselbe Stelle ist dieselbe Stelle - aber nur bei gleicher Farbe ---
# Denselben Knopf trifft man beim Aufnehmen nie zweimal pixelgenau. Mit exaktem
# Koordinatenvergleich entstand pro Klick ein eigener Punkt: in einer echten
# Aufnahme lagen vier Punkte auf EINEM gruenen Knopf (#2/#13/#24/#40, 1.4-6.7 px
# auseinander, Farbe identisch).
from autoclicker.persistence.sequences import point_at_position as _pas
import autoclicker.config as _cfg_pas
_cfg_pas.CONFIG.punkt_radius = 8
_cfg_pas.CONFIG.punkt_farbtoleranz = 10

_st_rec3 = AutoClickerState()
_ev_nah = [_RE(_R_CLICK, 0.0, 100, 200, (32, 135, 111)),
           _RE(_R_CLICK, 1.0, 103, 202, (32, 135, 111)),   # 3.6 px daneben
           _RE(_R_CLICK, 2.0, 104, 205, (32, 135, 111))]   # 6.4 px daneben
_map3, _new3 = _pfe(_ev_nah)
check("drei Klicks auf denselben Knopf ergeben EINEN Punkt", len(_new3) == 1)
check("und alle drei Schritte zeigen darauf",
      _map3[0] == _map3[1] == _map3[2])

# Deine Bedingung: sobald die Farbe abweicht, MUSS ein eigener Punkt entstehen -
# auch einen Pixel daneben. An einer Farbgrenze klickt man zwei verschiedene
# Dinge, und zwei Spiele uebereinander unterscheiden sich in nichts anderem.
_st_rec4 = AutoClickerState()
_ev_color = [_RE(_R_CLICK, 0.0, 100, 200, (32, 135, 111)),
             _RE(_R_CLICK, 1.0, 101, 200, (179, 57, 57))]
_map4, _new4 = _pfe(_ev_color)
check("abweichende Farbe erzwingt einen eigenen Punkt",
      len(_new4) == 2 and _map4[0] != _map4[1])

# Ohne gemessene Farbe laesst sich die Regel nicht pruefen - dann zaehlt nur die
# exakte Stelle. Lieber ein Punkt zu viel als zwei falsch zusammengelegte.
_without_color = [_WCP(x=100, y=200, name="ohne Farbe", id=1)]
check("ohne Farbe wird nur exakt getroffen",
      _pas(_without_color, 103, 202, (1, 2, 3)) is None
      and _pas(_without_color, 100, 200, (1, 2, 3)) is not None)

# Radius 0 ist das alte Verhalten und muss erreichbar bleiben.
_with_color = [_WCP(x=100, y=200, name="p", id=1, color=(32, 135, 111))]
check("Radius 0 vergleicht wieder exakt",
      _pas(_with_color, 103, 202, (32, 135, 111), radius=0) is None)
check("und der naechste gewinnt, wenn mehrere passen",
      _pas([_WCP(x=100, y=200, name="fern", id=1, color=(32, 135, 111)),
            _WCP(x=104, y=204, name="nah", id=2, color=(32, 135, 111))],
           105, 205, (32, 135, 111)).id == 2)

# Die eigentliche Wirkung: Punkt verschieben -> Schritt zieht nach
_st_rec2 = AutoClickerState()
_seq_rec = _KSEQ(name="R", init_steps=[], end_steps=[], loop_phases=[_KLP("L", [
    _SS(x=100, y=200, delay_before=0, name="Klick 1", point_id=_map2[0])], 1)],
    points=_points2)
_st_rec2.active_sequence = _seq_rec
_st_rec2.points = _seq_rec.points
_st_rec2.points[0].x, _st_rec2.points[0].y = 777, 888
from autoclicker.persistence import resolve_point_references as _rpr
with _cl2.redirect_stdout(_io2.StringIO()):
    _rpr(_st_rec2, _seq_rec)
_step_rec = _seq_rec.loop_phases[0].steps[0]
check("verschobener Punkt zieht den aufgenommenen Schritt mit",
      (_step_rec.x, _step_rec.y) == (777, 888))

# Sequenz-Studio: ein Block AUS einem Punkt muss ihn auch referenzieren
from autoclicker.editors.sequence_studio.model import (step_from_point as _sfp,
                                                   PalettePoint as _PP)
_block = _sfp(_PP(id=7, x=11, y=22, name="Bank", color=(1, 2, 3)))
check("Sequenz-Studio: Block aus Punkt behaelt die Referenz", _block.point_id == 7)
check("Sequenz-Studio: Koordinaten und Farbe kommen mit",
      (_block.x, _block.y) == (11, 22) and _block.recorded_color == (1, 2, 3))

# Und die Gegenrichtung: kein Erzeuger von Klick-Schritten darf point_id vergessen.
# Ein Blanko-Block (0,0) ist ausgenommen — der hat noch gar keine Position.
import ast as _ast_p
_NO_CLICK = {"wait_only", "item_scan", "boss_scan", "boss_watcher", "icon_scan",
               "screenshot_only", "key_press"}
_without_ref = []
for _pf in sorted((Path(__file__).resolve().parent.parent / "autoclicker").rglob("*.py")):
    try: _b = _ast_p.parse(_pf.read_text(encoding="utf-8"))
    except SyntaxError: continue
    for _n in _ast_p.walk(_b):
        if not (isinstance(_n, _ast_p.Call)
                and getattr(_n.func, "id", None) == "SequenceStep"):
            continue
        _kw = {k.arg: k.value for k in _n.keywords}
        if _NO_CLICK & set(_kw) or "point_id" in _kw:
            continue
        # Blanko: x=0, y=0 als Literale -> noch keine echte Position
        def _null(a):
            v = _kw.get(a)
            return isinstance(v, _ast_p.Constant) and v.value == 0
        if _null("x") and _null("y"):
            continue
        _without_ref.append(f"{_pf.name}:{_n.lineno}")
check("kein Klick-Schritt wird ohne point_id gebaut", _without_ref == [])
if _without_ref:
    print("        " + ", ".join(_without_ref))


# --------------------------- Aufnahme: Taste, Warte-Marker
section("Aufnahme schneidet mehr mit als nur Linksklicks")

from autoclicker.editors.sequence_recorder import (
    steps_from_events as _sae, _append_event as _anh,
    discard_last as _verwirf, check_markers as _mpr)

# Eine Aufnahme, die alle Arten enthaelt. Der Marker wird 2s nach dem ersten
# Klick gedrueckt (bis dahin lief normal etwas ab — das bleibt Wartezeit), und erst
# 3.4s SPAETER kommt der Klick: das ist das Warten auf die Farbe. Das Mausrad war
# einmal die vierte Art und ist ersatzlos gestrichen (s. sequence_recorder).
_ev_all = [_RE(_R_CLICK, 0.0, 10, 20, (1, 2, 3)),
            _RE(_R_WAIT, 2.0),
            _RE(_R_CLICK, 5.4, 50, 60, (7, 7, 7)),
            _RE(_R_KEY, 6.0, key="enter"),
            _RE(_R_CLICK, 6.5, 50, 60, (7, 7, 7))]
_st_all = AutoClickerState()
_map_all, _new_all = _pfe(_ev_all)
_steps_all = _sae(_ev_all, _map_all)

check("Tastendruck bekommt keinen Punkt", 3 not in _map_all)
# DAS war der Fehler aus der echten Aufnahme: der Marker legte einen Punkt an der
# zufaelligen Mausposition an — Muell in points.json, mit einer Farbe von irgendwo.
check("Warte-Marker bekommt KEINEN eigenen Punkt", 1 not in _map_all)
check("nur Klicks bekommen einen", set(_map_all) == {0, 2, 4})
check("ein zweiter Klick auf dieselbe Stelle teilt sich den Punkt", _map_all[2] == _map_all[4])
check("kein Punkt ohne echte Stelle", len(_new_all) == 2)

check("Tastendruck wird ein key_press-Schritt",
      _steps_all[2].key_press == "enter" and _steps_all[2].point_id is None)
check("die Aufnahme kennt kein Mausrad mehr",
      not hasattr(_steps_all[3], "scroll") and _steps_all[3].point_id == _map_all[4])

# Der Kern: der Marker ist KEIN eigener Schritt, sondern eine Bedingung am naechsten
check("Marker wird kein eigener Schritt", len(_steps_all) == 4)
_ws = _steps_all[1]
check("der Klick danach traegt die Bedingung", _ws.wait_condition is not None)
check("und prueft SEINE EIGENE Stelle (ein Punkt, zweimal referenziert)",
      _ws.wait_condition.point_id == _ws.point_id == _map_all[2])
check("er klickt weiterhin", _ws.wait_only is False)
# Die Zeit bis zum Marker (2.0 - 0.0) bleibt; die 3.4s danach sind das Warten.
check("die Uhr wird beim Marker angehalten", _ws.delay_before == 2.0)
check("spaetere Schritte messen wieder normal",
      _steps_all[2].delay_before == 0.6 and _steps_all[3].delay_before == 0.5)

# Die Wartefarbe ist die des Klicks — richtig, weil man erst klickt, wenn es da ist
_pt_click = [p for p in _new_all if p.id == _map_all[2]][0]
check("gewartet wird auf die Farbe, die der Klick vorfand", _pt_click.color == (7, 7, 7))

# In der Datei stehen nur zwei Referenzen auf denselben Punkt, keine Koordinate
_d_extra = _s2d(_ws)
check("in der Datei stehen nur die zwei Referenzen",
      _d_extra.get("point_id") == _d_extra.get("wait_point_id") == _ws.point_id
      and not {"x", "y", "pixel", "color"} & set(_d_extra))

# Der Marker haengt an dem Klick, der ihm folgt — auch wenn dazwischen Zeit vergeht
_ev_real = [_RE(_R_CLICK, 0.0, 4464, 1357, (32, 135, 111)),
            _RE(_R_WAIT, 1.0),
            _RE(_R_CLICK, 435.34, 4764, 29, (179, 57, 57))]
_st_real = AutoClickerState()
_map_real, _points_real = _pfe(_ev_real)
_steps_real = _sae(_ev_real, _map_real)
check("echte Aufnahme: 434s Warten werden zur Bedingung, nicht zur Schlafzeit",
      _steps_real[1].delay_before == 1.0)
check("echte Aufnahme: geprueft wird die Klick-Stelle",
      _steps_real[1].wait_condition.point_id == _steps_real[1].point_id)
check("echte Aufnahme: kein Punkt an einer Zufallsstelle", len(_points_real) == 2)

# Frisch gebaute Schritte tragen NUR Referenzen — Pruef-Pixel und Farbe sind leer, bis
# aufgeloest wird. Der Worker macht das vor jedem Lauf; wer direkt nach der Aufnahme in
# den Editor geht, saehe sonst "(0,0)" statt der Stelle, auf die gewartet wird.
from autoclicker.models import Sequence as _SEQ3, LoopPhase as _LP3
from autoclicker.persistence import resolve_point_references as _rpr3
check("vor dem Aufloesen ist der Pruef-Pixel noch leer",
      _steps_real[1].wait_condition.pixel == (0, 0))
_seq_fresh = _SEQ3(name="F", loop_phases=[_LP3(name="L", steps=_steps_real, repeat=1)],
                    points=_points_real)
_st_real.active_sequence = _seq_fresh
_st_real.points = _seq_fresh.points
_rpr3(_st_real, _seq_fresh)
_sf = _seq_fresh.loop_phases[0].steps[1]
check("nach dem Aufloesen zeigt die Bedingung auf die Klick-Stelle",
      _sf.wait_condition.pixel == (_sf.x, _sf.y) == (4764, 29))
check("und traegt die beim Klick erfasste Farbe",
      _sf.wait_condition.color == (179, 57, 57))

# Ein Marker ohne folgenden Klick kann nichts: er wird verworfen statt zu verschwinden
_g1, _v1 = _mpr([_RE(_R_CLICK, 0.0, 1, 2), _RE(_R_WAIT, 1.0)])
check("Marker am Ende wird verworfen", _v1 == 1 and len(_g1) == 1)
_g2, _v2 = _mpr([_RE(_R_WAIT, 0.0), _RE(_R_KEY, 1.0, key="a")])
check("Marker vor einem Tastendruck wird verworfen", _v2 == 1 and len(_g2) == 1)
_g3, _v3 = _mpr([_RE(_R_WAIT, 0.0), _RE(_R_CLICK, 1.0, 5, 5)])
check("Marker vor einem Klick bleibt", _v3 == 0 and len(_g3) == 2)
_g4, _v4 = _mpr([_RE(_R_WAIT, 0.0), _RE(_R_WAIT, 0.5), _RE(_R_CLICK, 1.0, 5, 5)])
check("zweimal M ist derselbe Wunsch -> ein Marker", _v4 == 1 and len(_g4) == 2)

# Screenshot-Marker (CTRL+ALT+D): anders als der Warte-Marker wird er SEIN EIGENER
# Schritt — er hat keine Folge-Aktion, an die er sich haengen koennte. Eine Stelle hat
# er trotzdem nicht: beim Druecken parkt die Maus irgendwo, ein Punkt darauf waere
# derselbe Muell, den der Warte-Marker frueher in points.json geschrieben hat.
from autoclicker.models import REC_SCREENSHOT as _R_SHOT
from autoclicker.editors.sequence_recorder import mark_screenshot as _mshot

_ev_shot = [_RE(_R_CLICK, 0.0, 10, 20, (1, 2, 3)),
            _RE(_R_SHOT, 1.5),
            _RE(_R_CLICK, 2.0, 30, 40, (4, 5, 6))]
_st_shot = AutoClickerState()
_map_shot, _new_shot = _pfe(_ev_shot)
_steps_shot = _sae(_ev_shot, _map_shot)

check("Screenshot-Marker bekommt KEINEN eigenen Punkt", 1 not in _map_shot)
check("und legt damit auch keinen an", len(_new_shot) == 2)
check("er wird aber SEIN EIGENER Schritt (anders als der Warte-Marker)",
      len(_steps_shot) == 3 and _steps_shot[1].screenshot_only is True)
check("als Vollbild — der Bereich kommt spaeter im Editor",
      _steps_shot[1].screenshot_region is None)
check("ohne Klickziel und ohne Punkt-Referenz",
      _steps_shot[1].point_id is None and _steps_shot[1].wait_only is False)
check("die Wartezeit bis dahin bleibt echte Wartezeit",
      _steps_shot[1].delay_before == 1.5)
check("und der Klick danach misst ab dem Marker weiter",
      _steps_shot[2].delay_before == 0.5)

# Er darf NICHT wie der Warte-Marker verworfen werden, wenn nichts folgt: er braucht
# keine Folge-Aktion. Ein Marker am Ende ist ein Screenshot am Ende — voellig gueltig.
_g6, _v6 = _mpr([_RE(_R_CLICK, 0.0, 1, 2), _RE(_R_SHOT, 1.0)])
check("Screenshot-Marker am Ende bleibt (er braucht keinen Klick nach sich)",
      _v6 == 0 and len(_g6) == 2)
_steps_end = _sae(_g6, _pfe(_g6)[0])
check("und wird dort zum letzten Schritt", _steps_end[-1].screenshot_only is True)

# Ein Warte-Marker VOR einem Screenshot-Marker hat nichts zum Anhaengen: der
# Screenshot hat keine Stelle und keine Farbe, auf die man warten koennte.
_g7, _v7 = _mpr([_RE(_R_WAIT, 0.0), _RE(_R_SHOT, 1.0)])
check("Warte-Marker vor einem Screenshot-Marker wird verworfen", _v7 == 1)

# Der Hotkey haengt am Aufnahme-Zustand: ohne laufende Aufnahme passiert nichts
_st_disabled = AutoClickerState()
with _cl2.redirect_stdout(_io2.StringIO()):
    _mshot(_st_disabled)
check("ohne laufende Aufnahme zeichnet CTRL+ALT+D nichts auf",
      _st_disabled.recording_events == [])
_st_pau = AutoClickerState()
_st_pau.recording_active = True
_st_pau.recording_paused = True
with _cl2.redirect_stdout(_io2.StringIO()):
    _mshot(_st_pau)
check("und pausiert ebenso wenig", _st_pau.recording_events == [])
_st_on = AutoClickerState()
_st_on.recording_active = True
with _cl2.redirect_stdout(_io2.StringIO()):
    _mshot(_st_on)
check("waehrend der Aufnahme landet genau ein Screenshot-Ereignis in der Liste",
      len(_st_on.recording_events) == 1
      and _st_on.recording_events[0].kind == _R_SHOT)

# Der Schritt muss die Datei ueberleben — sonst ist der Marker beim naechsten Start weg
_d_shot = _s2d(_steps_shot[1])
check("screenshot_only steht in der Datei", _d_shot.get("screenshot_only") is True)
check("und ohne Klick-Koordinaten", not {"x", "y", "point_id"} & set(_d_shot))


# --------------------------- Aufnahme: Bereich, Beobachten, Phasengrenze
section("Aufnahme kann Bereich, Beobachten und Phasengrenze")

from autoclicker.models import (REC_REGION as _R_REG, REC_WATCH as _R_WATCH,
                                REC_PHASE as _R_PHASE)
from autoclicker.editors.sequence_recorder import (
    merge_regions as _bz, phase_boundaries as _pg,
    build_phases as _pb, mark_region as _mber, mark_phase as _mph)

# --- Bereich: zwei Ecken werden EIN Screenshot mit Rechteck ---
_ev_report = [_RE(_R_CLICK, 0.0, 1, 1),
           _RE(_R_REG, 1.0, 300, 400),      # Ecke 1
           _RE(_R_REG, 3.0, 100, 200),      # Ecke 2 (verkehrt herum angefahren)
           _RE(_R_CLICK, 4.0, 2, 2)]
_g_report, _half = _bz(_ev_report)
check("zwei Ecken werden EIN Ereignis", len(_g_report) == 3 and _half == 0)
check("und zwar ein Screenshot mit Rechteck",
      _g_report[1].kind == _R_SHOT and _g_report[1].region == (100, 200, 300, 400))
# Normalisiert: egal in welcher Reihenfolge die Ecken angefahren wurden
check("das Rechteck wird normalisiert (links/oben zuerst)",
      _g_report[1].region[0] < _g_report[1].region[2]
      and _g_report[1].region[1] < _g_report[1].region[3])
# Der Zeitstempel ist der der ERSTEN Ecke — die 2s Mausweg sind Bedienzeit
check("der Zeitstempel ist der der ersten Ecke", _g_report[1].t == 1.0)
_steps_report = _sae(_g_report, _pfe(_g_report)[0])
check("der Screenshot sitzt dort, wo die erste Ecke gesetzt wurde",
      _steps_report[1].delay_before == 1.0)
# Die Aufnahme erfindet keine Zeit und wirft keine weg: die Summe der Wartezeiten
# muss die verstrichene Zeit ergeben. Die 2s Mausweg zwischen den Ecken bleiben
# deshalb in der Wartezeit des NAECHSTEN Schritts stehen — Bedienzeit von Spielzeit
# zu trennen kann die Aufnahme nicht (Nachdenken sieht genauso aus).
check("keine Zeit geht durch das Falten verloren",
      sum(s.delay_before for s in _steps_report) == _ev_report[-1].t - _ev_report[0].t)
check("und der Schritt traegt den Bereich statt Vollbild",
      _steps_report[1].screenshot_region == (100, 200, 300, 400))

# Eine halbe Ecke ist kein Bereich — verwerfen, nicht still zu Vollbild degradieren
_g_half, _n_half = _bz([_RE(_R_CLICK, 0.0, 1, 1), _RE(_R_REG, 1.0, 5, 5)])
check("eine einzelne Ecke wird verworfen und gemeldet",
      _n_half == 1 and len(_g_half) == 1)
check("und wird KEIN Vollbild-Screenshot",
      not any(e.kind == _R_SHOT for e in _g_half))
# Vier Ecken = zwei Bereiche (die Paarbildung darf nicht durcheinanderkommen)
_g_vier, _ = _bz([_RE(_R_REG, 0.0, 0, 0), _RE(_R_REG, 1.0, 10, 10),
                  _RE(_R_REG, 2.0, 20, 20), _RE(_R_REG, 3.0, 30, 30)])
check("vier Ecken ergeben zwei Bereiche",
      len(_g_vier) == 2 and _g_vier[0].region == (0, 0, 10, 10)
      and _g_vier[1].region == (20, 20, 30, 30))

# --- Beobachten: wait_only-Schritt mit Punkt auf der beobachteten Stelle ---
_ev_watch = [_RE(_R_CLICK, 0.0, 10, 10, (1, 1, 1)),
             _RE(_R_WATCH, 2.0, 500, 600, (9, 9, 9)),
             _RE(_R_CLICK, 3.0, 20, 20, (2, 2, 2))]
_st_watch = AutoClickerState()
_map_watch, _points_watch = _pfe(_ev_watch)
_steps_watch = _sae(_ev_watch, _map_watch)
# Anders als der Warte-Marker: die Stelle ist BEWUSST gewaehlt, also bekommt sie
# einen Punkt — points.json ist die einzige Quelle fuer Koordinaten.
check("der Beobachtungs-Marker bekommt einen eigenen Punkt", 1 in _map_watch)
check("und der liegt auf der beobachteten Stelle",
      any((p.x, p.y) == (500, 600) for p in _points_watch))
_ws2 = _steps_watch[1]
check("er wird ein Schritt, der NICHT klickt", _ws2.wait_only is True)
check("ohne Klickziel, aber mit Pruef-Pixel-Referenz",
      _ws2.point_id is None and _ws2.wait_condition.point_id == _map_watch[1])
check("die Wartezeit davor bleibt echte Wartezeit", _ws2.delay_before == 2.0)
# In der Datei steht nur die Referenz, keine Koordinate
_d_watch = _s2d(_ws2)
check("in der Datei steht nur die Pruef-Referenz",
      _d_watch.get("wait_point_id") == _map_watch[1]
      and not {"x", "y", "pixel", "color", "point_id"} & set(_d_watch))
# Aufloesen fuellt Stelle und Farbe nach
_seq_w = _SEQ3(name="W", loop_phases=[_LP3(name="L", steps=_steps_watch, repeat=1)],
               points=_points_watch)
_st_watch.active_sequence = _seq_w
_st_watch.points = _seq_w.points
_rpr3(_st_watch, _seq_w)
_wa = _seq_w.loop_phases[0].steps[1]
check("nach dem Aufloesen zeigt er auf die beobachtete Stelle",
      _wa.wait_condition.pixel == (500, 600)
      and _wa.wait_condition.color == (9, 9, 9))

# --- Phasengrenze: schneidet die Schrittliste in INIT | LOOP | END ---
# Die Grenze wird ENTFERNT, nicht uebersprungen: sonst wuerde die Wartezeit des
# naechsten Schritts ab dem Tastendruck statt ab der letzten echten Aktion gemessen.
_ev_ph = [_RE(_R_CLICK, 0.0, 1, 1),      # INIT
          _RE(_R_PHASE, 5.0),            # Grenze — 5s nach dem Klick gedrueckt
          _RE(_R_CLICK, 6.0, 2, 2),      # LOOP, echte Wartezeit = 6s
          _RE(_R_CLICK, 7.0, 3, 3),
          _RE(_R_PHASE, 7.5),
          _RE(_R_CLICK, 8.0, 4, 4)]      # END
_without, _gr = _pg(_ev_ph)
check("die Grenzen verschwinden aus dem Ereignisstrom",
      not any(e.kind == _R_PHASE for e in _without) and len(_without) == 4)
check("und werden als Schritt-Indizes gemerkt", _gr == [1, 3])
_steps_ph = _sae(_without, _pfe(_without)[0])
check("die Grenze frisst keine Wartezeit weg", _steps_ph[1].delay_before == 6.0)
_ph = _pb(_steps_ph, _gr)
check("zwei Grenzen ergeben drei Phasen", len(_ph) == 3)
check("die erste bekommt die Schritte davor", len(_ph[0].steps) == 1)
check("die zweite die dazwischen", len(_ph[1].steps) == 2)
check("die dritte die danach", len(_ph[2].steps) == 1)
check("und keiner geht verloren",
      sum(len(x.steps) for x in _ph) == len(_steps_ph))
# Die Namen sind dieselben, die der Nutzer beim Stoppen angezeigt bekommt.
check("die Phasen heissen Loop, Loop 2, Loop 3",
      [x.name for x in _ph] == ["Loop", "Loop 2", "Loop 3"])
check("und jede laeuft einmal pro Zyklus", all(x.repeat == 1 for x in _ph))

# Ohne Grenze bleibt alles in EINER Phase — das bisherige Verhalten
_ph0 = _pb(_steps_ph, [])
check("ohne Grenze bleibt alles in einer Phase",
      len(_ph0) == 1 and len(_ph0[0].steps) == len(_steps_ph))
check("und die heisst schlicht Loop", _ph0[0].name == "Loop")

# Leere Abschnitte fallen weg: Grenze ganz am Anfang, zwei hintereinander
check("Grenze als erstes gedrueckt macht keine leere Phase",
      len(_pb(_steps_ph, [0])) == 1)
check("zwei Grenzen an derselben Stelle auch nicht",
      len(_pb(_steps_ph, [2, 2])) == 2)
# Ohne einen einzigen Schritt bleibt trotzdem eine Phase stehen — sonst haette
# die Sequenz keine Stelle, an der man danach etwas einfuegen koennte.
check("ganz ohne Schritte kommt eine leere Phase zurueck",
      len(_pb([], [])) == 1 and _pb([], [])[0].steps == [])

# Warte-Marker erzeugen keinen eigenen Schritt und duerfen den Schnitt nicht verschieben
_ev_mix = [_RE(_R_CLICK, 0.0, 1, 1), _RE(_R_WAIT, 1.0), _RE(_R_CLICK, 2.0, 2, 2),
           _RE(_R_PHASE, 3.0), _RE(_R_CLICK, 4.0, 3, 3)]
_without_mix, _gr_mix = _pg(_ev_mix)
check("ein Warte-Marker verschiebt den Schnitt nicht", _gr_mix == [2])
_steps_mix = _sae(*(lambda ev: (ev, _pfe(ev)[0]))(_without_mix))
_ph_mix = _pb(_steps_mix, _gr_mix)
check("und der Schnitt trifft die richtige Stelle",
      len(_ph_mix[0].steps) == 2 and len(_ph_mix[1].steps) == 1)

# Die Obergrenze von zwei Grenzen ist WEG: wer vier Abschnitte spielt, bekommt
# vier Phasen. Vorher stand beim dritten Druck "mehr Phasen kann die Aufnahme
# nicht", und man zog sie hinterher im Studio von Hand auseinander.
_st_ph = AutoClickerState()
_st_ph.recording_active = True
with _cl2.redirect_stdout(_io2.StringIO()):
    for _ in range(4):
        _mph(_st_ph)
check("die vierte Phasengrenze wird angenommen",
      sum(1 for x in _st_ph.recording_events if x.kind == _R_PHASE) == 4)
import inspect as _insp_ph
from autoclicker.editors import sequence_recorder as _recmod_ph
_rec_source_ph = _insp_ph.getsource(_recmod_ph.stop_recording)

# Die Aufnahme befuellt INIT und END nicht mehr: sie kann nicht sehen, welcher
# Abschnitt nur einmal laufen soll. Das steht im Studio an der Phase.
check("und die Aufnahme legt weder INIT noch END an",
      "init_steps" not in _rec_source_ph and "end_steps" not in _rec_source_ph)

# Alle Marker haengen am Aufnahme-Zustand
_st_off = AutoClickerState()
with _cl2.redirect_stdout(_io2.StringIO()):
    _mber(_st_off)
    _mph(_st_off)
check("ohne laufende Aufnahme zeichnen die neuen Marker nichts auf",
      _st_off.recording_events == [])


# --------------------------- OCR und LLM muessen denselben Boss meinen
section("OCR und LLM bilden denselben Text auf denselben Boss ab")

# Beide Erkenner bekommen laut Vertrag dieselbe (gemergte) Boss-Liste und ersetzen
# einander je nach *_fallback-Einstellung. Bilden sie denselben Text auf VERSCHIEDENE
# Bosse ab, laeuft dieselbe Sequenz unterschiedlich — jedes BossProfile hat seine
# eigene Aktion. Der Test misst beide Seiten, statt eine abzuschreiben.
from autoclicker.ocr import _match_text_to_boss as _ocr_match
from autoclicker.llm_vision import match_boss_name as _llm_match

_CASES = [
    # (Boss-Liste, erkannter Text)
    (["Ork", "Orkhaeuptling"], "Der Orkhaeuptling erscheint"),   # <- war der Bug
    (["Orkhaeuptling", "Ork"], "Der Orkhaeuptling erscheint"),   # Reihenfolge egal
    (["Drache", "Feuerdrache"], "Ein Feuerdrache!"),
    (["Feuerdrache", "Drache"], "Ein Feuerdrache!"),
    (["Ork", "Orkhaeuptling"], "Orkhaeuptling"),                 # exakt
    (["Goblin", "Goblinkoenig"], "Goblinkoenig greift an"),
]
_disagree = []
for _bosses, _text in _CASES:
    _o = _ocr_match(_text, _bosses)
    _l = _llm_match(_text, _bosses)[0]
    if _o != _l:
        _disagree.append(f"{_text!r} bei {_bosses}: OCR={_o!r} LLM={_l!r}")
check("beide Erkenner sind sich bei jedem Fall einig", _disagree == [])
if _disagree:
    for _z in _disagree:
        print("        " + _z)

# Die Regel selbst, damit der Test auch dann etwas sagt, wenn beide zusammen falsch waeren
check("der laengste enthaltene Name gewinnt (nicht der erste in der Liste)",
      _ocr_match("Der Orkhaeuptling erscheint", ["Ork", "Orkhaeuptling"]) == "Orkhaeuptling")
check("das gilt unabhaengig von der Listenreihenfolge",
      _ocr_match("Der Orkhaeuptling erscheint", ["Orkhaeuptling", "Ork"]) == "Orkhaeuptling")
# Umgekehrte Richtung: steckt der Text in mehreren Namen, gewinnt der kuerzeste —
# er behauptet am wenigsten ueber das hinaus, was gelesen wurde.
check("steckt der Text in mehreren Namen, gewinnt der kuerzeste",
      _ocr_match("Ork", ["Orkhaeuptling", "Orkschamane"]) is None
      or _ocr_match("Orkh", ["Orkhaeuptling", "Orkhaeuptling der Grosse"]) == "Orkhaeuptling")
check("ein zu kurzes Kuerzel matcht gar nichts",
      _ocr_match("or", ["Orkhaeuptling"]) is None)
check("leerer Text matcht nichts", _ocr_match("   ", ["Ork"]) is None)

# Das Mausrad ist ersatzlos gestrichen — samt Config-Schalter, Hook-Zweig und
# Schritt-Typ. Ein `record_scroll` in einer alten config.json ist ein unbekannter
# Schluessel und faellt beim Laden weg; der Hook nimmt keinen Rad-Callback mehr.
import inspect as _insp2
from autoclicker.winapi import install_mouse_hook as _imh
check("der Maus-Hook kennt kein Rad mehr",
      "on_wheel" not in _insp2.signature(_imh).parameters)
check("record_scroll ist aus der Config verschwunden",
      not hasattr(AppConfig.from_dict({"record_scroll": False}), "record_scroll"))

# Pausiert wird nichts aufgezeichnet — das galt fuer Klicks und muss fuer alles gelten
_st_pause = AutoClickerState()
_st_pause.recording_active = True
_st_pause.recording_paused = True
with _cl2.redirect_stdout(_io2.StringIO()):
    _accepted = _anh(_st_pause, _RE(_R_KEY, 0.0, key="a"))
check("pausierte Aufnahme nimmt auch Tasten nicht an",
      _accepted is False and _st_pause.recording_events == [])

# Zuruecknehmen
_st_undo = AutoClickerState()
_st_undo.recording_active = True
_st_undo.recording_events = [_RE(_R_CLICK, 0.0, 1, 2), _RE(_R_KEY, 1.0, key="x")]
with _cl2.redirect_stdout(_io2.StringIO()):
    _verwirf(_st_undo)
check("Zuruecknehmen entfernt genau das letzte Ereignis",
      len(_st_undo.recording_events) == 1
      and _st_undo.recording_events[0].kind == _R_CLICK)
with _cl2.redirect_stdout(_io2.StringIO()):
    _verwirf(_st_undo)
    _verwirf(_st_undo)          # eins zu viel darf nicht knallen
check("Zuruecknehmen auf leerer Aufnahme bleibt still stehen",
      _st_undo.recording_events == [])


# --------------------------- Status-Zeile: EIN Schreibvorgang, volle Loeschbreite
section("Die Status-Zeile ueberschreibt sich in einem Stueck")

# Die Status-Zeile wird ohne \n geschrieben, damit sie sich selbst ueberschreibt.
# Vorher waren das ZWEI einzeln geflushte Schreibvorgaenge (clear_line(), dann
# print(...)). Ein echtes Terminal fasst die zusammen; eine IDE-Konsole verarbeitet
# jeden Flush als eigenen Block und kann die Zeile dazwischen festschreiben — dann
# blieb eine alte Status-Zeile im Ablauf stehen, statt ueberschrieben zu werden.
from autoclicker.utils import status_line as _sl
import autoclicker.utils.console as _CONS


class _Capture:
    """Faengt die einzelnen write()-Aufrufe ab (print() ruft pro Teil einmal)."""

    def __init__(self):
        self.writes = []

    def write(self, s):
        if s:
            self.writes.append(s)
        return len(s)

    def flush(self):
        pass


_CONS._last_status_length = 0
_with = _Capture()
_real_out = sys.stdout
try:
    sys.stdout = _with
    _sl("short")
    _sl("[Loop] Schritt 2/50 | " + "X" * 90)     # laenger als die alten 80 Spalten
    _sl("danach wieder kurz")
finally:
    sys.stdout = _real_out

check("jede Status-Zeile geht als EIN write() raus", len(_with.writes) == 3)
check("und traegt ihr eigenes \\r bei sich",
      all(w.startswith("\r") for w in _with.writes))
check("keine Status-Zeile schliesst sich mit \\n ab",
      not any("\n" in w for w in _with.writes))

# Volle Loeschbreite: die 112 sichtbaren Zeichen der zweiten Zeile muessen weg sein,
# bevor die dritte (18 Zeichen) sie ersetzt. Mit fixen 80 blieb der Rest stehen.
_dritte = _with.writes[2]
_width = _dritte.count(" ", 0, _dritte.rfind("\r"))
check("die Loeschbreite folgt der vorherigen Zeile statt fixer 80",
      _width >= len("[Loop] Schritt 2/50 | ") + 90)

# ANSI-Sequenzen belegen keine Spalte — mitgezaehlt waere die Breite absurd gross
_CONS._last_status_length = 0
_with2 = _Capture()
try:
    sys.stdout = _with2
    _sl(_CONS.col("abc", "red"))
finally:
    sys.stdout = _real_out
check("ANSI-Codes zaehlen nicht zur Zeilenbreite",
      _CONS._visible_length(_CONS.col("abc", "red")) == 3)

# Eine Meldung, die die Status-Zeile bewusst abschliesst (\n mittendrin), darf die
# Breite nicht aus dem Teil DAVOR nehmen — dort steht nichts mehr zu ueberschreiben.
_CONS._last_status_length = 0
_with3 = _Capture()
try:
    sys.stdout = _with3
    _sl("A" * 50 + "\nkurz")
finally:
    sys.stdout = _real_out
check("nach einem \\n zaehlt nur der Teil dahinter",
      _CONS._last_status_length == 4)
_CONS._last_status_length = 0

# CTRL+ALT+U trifft waehrend der Aufnahme die Aufnahme, sonst die Punkte
from autoclicker.handlers import handle_undo as _hu
_st_ctx = AutoClickerState()
_st_ctx.points = [_WCP(x=1, y=2, name="P1", id=1)]
_st_ctx.recording_active = True
_st_ctx.recording_events = [_RE(_R_CLICK, 0.0, 5, 6)]
with _cl2.redirect_stdout(_io2.StringIO()):
    _hu(_st_ctx)
check("waehrend der Aufnahme nimmt CTRL+ALT+U das Ereignis zurueck",
      _st_ctx.recording_events == [] and len(_st_ctx.points) == 1)

# Die Umkehrung im Editor: 'colorgone' dreht einen aufgenommenen Trigger um, statt
# eine LIVE-Farbe abzugreifen (die Maus steht beim Editieren ja woanders).
from autoclicker.editors.sequence_editor.steps import _PhaseEditor as _SE_cls
_marker = _SS(x=50, y=60, point_id=_map_all[2],
              wait_condition=_WC(point_id=_map_all[2]))
_turn = _SE_cls.__dict__["_apply_trigger"]
check("colorgone dreht die Richtung des Triggers um",
      _turn(None, _marker, "gone") is True
      and _marker.wait_condition.until_gone is True)
check("und laesst den aufgenommenen Punkt in Ruhe",
      _marker.wait_condition.point_id == _map_all[2])


# Hier standen die Tests zu `_seq_v2_to_v3` und `_seq_v3_to_v4`; beide Schritte
# sind geloescht, weil es keinen Altbestand mehr gibt.
#
# Was bleibt, ist die Garantie darunter: die Kette laeuft, solange es etwas zu
# heben gibt, danach nie wieder. Gemessen mit einem GESTELLTEN Schritt - an einen
# echten gehaengt waere der Test beim naechsten Loeschen wieder faellig.
import autoclicker.persistence.migration as _MG
from autoclicker.persistence.sweep import sweep_on_start as _sweep_start
from autoclicker.persistence import (ensure_sequences_dir as _esd2,
                                     load_sequence_file as _lsf2)
from autoclicker.config import SEQUENCES_DIR as _SQD2

_once_tmp = tempfile.mkdtemp()
_once_cwd = _os.getcwd()
_os.chdir(_once_tmp)
_counters = {"n": 0}
_orig_chain = list(_MG._CHAINS[_MG.KIND_SEQUENCE])
try:
    def _counted(data, context):
        _counters["n"] += 1
        data["von_der_migration"] = True
        return ["gestellter Schritt gelaufen"]
    # Auf Position 0: hebt von Version 0 auf 1. Die restlichen Stufen bis
    # SCHEMA_VERSION haben keinen Eintrag und heben die Nummer nur an.
    _MG._CHAINS[_MG.KIND_SEQUENCE] = [_counted]

    _esd2()
    # Die Sequenz ist eine Besitzeinheit: sequence.json in ihrem eigenen Ordner,
    # Punkte im Feld `points` derselben Datei.
    _rfolder = Path(_SQD2) / "recording"
    _rfolder.mkdir(parents=True, exist_ok=True)
    _rfile = _rfolder / "sequence.json"
    _rfile.write_text(json.dumps({
        "name": "recording", "total_cycles": 1,
        "points": [{"id": 5, "x": 100, "y": 200, "name": "Bank"}],
        "init_steps": [], "end_steps": [],
        "loop_phases": [{"name": "Loop", "repeat": 1, "steps": [
            {"point_id": 5, "delay_before": 0}]}]}), encoding="utf-8")

    with _cl2.redirect_stdout(_io2.StringIO()):
        _sweep_start()
    _after_first = _counters["n"]
    _dat = json.loads(_rfile.read_text(encoding="utf-8"))
    check("erster Start hebt die Datei auf die aktuelle Version",
          _dat["schema_version"] == _MG.SCHEMA_VERSION)
    check("erster Start ruft die Kette ueberhaupt auf", _after_first > 0)

    _content_before = _rfile.read_text(encoding="utf-8")
    with _cl2.redirect_stdout(_io2.StringIO()):
        _sweep_start()
        _sweep_start()
    check("weitere Starts rufen keinen Migrationsschritt mehr auf",
          _counters["n"] == _after_first)
    check("weitere Starts lassen die Datei unveraendert",
          _rfile.read_text(encoding="utf-8") == _content_before)

    with _cl2.redirect_stdout(_io2.StringIO()):
        for _ in range(20):
            _lsf2(_rfile)
    check("Sequenz laden ruft keinen Migrationsschritt mehr auf",
          _counters["n"] == _after_first)
finally:
    _MG._CHAINS[_MG.KIND_SEQUENCE] = _orig_chain
    _os.chdir(_once_cwd)


# ------------------------------------------------ Item-Scan-Assistent
section("Mehrfachauswahl im Item-Scan-Assistenten")

# Schritt 1 (Slots) und Schritt 2 (Items) hatten dieselbe Schleife zweimal
# ausgeschrieben. Jetzt eine — und die ist testbar, weil sie nur safe_input braucht.
import autoclicker.editors.item_scan_editor as _ISE
from autoclicker.editors.item_scan_editor import parse_range as _bp

check("Bereich '1-5' wird gelesen", _bp("1-5", 10) == (1, 5))
check("Bereich rueckwaerts wird normalisiert", _bp("5-1", 10) == (1, 5))
check("Bereich ausserhalb der Liste -> None", _bp("1-11", 10) is None)
check("Bereich mit 0 -> None", _bp("0-3", 10) is None)
check("kein Bereich -> None", _bp("7", 10) is None)
check("Unsinn mit Strich -> None", _bp("a-b", 10) is None)
check("zu viele Teile -> None", _bp("1-2-3", 10) is None)


def _selection(inputs, entries=None, preselected=(), **kw):
    """Fuettert multi_select mit einer Tastenfolge."""
    entries = list(entries if entries is not None else ["A", "B", "C", "D"])
    consequence = list(inputs)
    _o = _ISE.safe_input
    _ISE.safe_input = lambda _p="": consequence.pop(0) if consequence else "cancel"
    try:
        with _cl2.redirect_stdout(_io2.StringIO()):
            return _ISE.multi_select(
                "> ", entries, list(preselected),
                lambda i, n, an: f"{i} {n} {an}", **kw)
    finally:
        _ISE.safe_input = _o


check("Einzelauswahl per Nummer", _selection(["2", "done"]) == ["B"])
check("nochmal dieselbe Nummer waehlt ab", _selection(["2", "2", "done"]) == [])
check("Bereich waehlt mehrere", _selection(["2-4", "done"]) == ["B", "C", "D"])
check("'all' waehlt alles", _selection(["all", "done"]) == ["A", "B", "C", "D"])
check("'clear' leert die Auswahl", _selection(["all", "clear", "done"]) == [])
check("Vorauswahl bleibt erhalten",
      _selection(["done"], preselected=["C"]) == ["C"])
check("'cancel' gibt None zurueck", _selection(["2", "cancel"]) is None)
check("Bereich fuegt nichts doppelt hinzu",
      _selection(["1-3", "2-4", "done"]) == ["A", "B", "C", "D"])
check("ungueltige Nummer aendert nichts", _selection(["9", "1", "done"]) == ["A"])
check("unbekannter Befehl aendert nichts", _selection(["quatsch", "1", "done"]) == ["A"])
check("'show' aendert die Auswahl nicht", _selection(["1", "show", "done"]) == ["A"])

# empty_error erzwingt mindestens einen Eintrag — 'done' darf dann nicht durchgehen
check("empty_error: 'done' ohne Auswahl wird abgelehnt",
      _selection(["done", "1", "done"], empty_error="Mindestens 1!") == ["A"])
check("ohne empty_error ist eine leere Auswahl erlaubt", _selection(["done"]) == [])

# Der 'new'-Befehl haengt einen Eintrag an UND waehlt ihn aus
_new_list = ["A", "B"]
_result = _selection(["new 1", "done"], entries=_new_list,
                     extra_prefix="new", extra_fn=lambda raw: "Frisch")
check("'new' waehlt den neuen Eintrag gleich mit", _result == ["Frisch"])
check("'new' bekommt die Roh-Eingabe (Slot-Nummer bleibt lesbar)",
      _selection(["new 3", "done"], extra_prefix="new",
               extra_fn=lambda raw: raw) == ["new 3"])
check("'new' ohne Ergebnis aendert nichts",
      _selection(["new 1", "done"], extra_prefix="new",
               extra_fn=lambda raw: None) == [])

# Regression: '1-5' darf nicht als unbekannter Befehl durchfallen, und 'new' nicht
# als Bereich gelesen werden (beides stand vorher in derselben elif-Kette)
check("'new' wird nicht als Bereich missverstanden",
      _selection(["new-quatsch", "1", "done"], extra_prefix="new",
               extra_fn=lambda raw: None) == ["A"])




# --------------------------- Nachpruefung: "hat die Aktion gewirkt?"
section("Nachpruefung wiederholt die Aktion, statt blind weiterzulaufen")

# Ein Klick war bis hierher ein Schuss ins Dunkle: geht er ins Leere (Lag, Fenster
# nicht vorn, Popup davor), lief die Sequenz weiter und alles Folgende traf daneben.
# `verify_condition` prueft NACH der Aktion und wiederholt sie notfalls.
from autoclicker.models import WaitCondition as _WC4, ElseConfig as _EC4, ELSE_SKIP as _ESK4
import autoclicker.runtime.steps as _RS
import autoclicker.runtime.actions as _RA

# --- Datei: nur die Referenz, keine Koordinate (die vierte Stelle) ---
_st_v = _SS(x=10, y=20, delay_before=0.0, name="Bank", point_id=1,
            verify_condition=_WC4(point_id=7, pixel=(50, 60), color=(0, 255, 0)))
_d_v = _s2d(_st_v)
check("die Nachpruefung steht als Referenz in der Datei",
      _d_v.get("verify_point_id") == 7)
check("und OHNE eigene Koordinate oder Farbe",
      "verify_pixel" not in _d_v and "verify_color" not in _d_v)
_back_v = _p2s([_d_v])[0]
check("sie ueberlebt den Datei-Zyklus",
      _back_v.verify_condition is not None
      and _back_v.verify_condition.point_id == 7)
check("ein Schritt ohne Nachpruefung schreibt das Feld gar nicht",
      "verify_point_id" not in _s2d(_SS(x=1, y=2, delay_before=0, point_id=1)))
# until_gone muss mit - sonst kippt die Richtung beim Laden
_d_vg = _s2d(_SS(x=1, y=2, delay_before=0, point_id=1,
                 verify_condition=_WC4(point_id=7, until_gone=True)))
check("die Richtung (WEG statt DA) ueberlebt ebenfalls",
      _p2s([_d_vg])[0].verify_condition.until_gone is True)

# `_REF_KEYS` (die vier Referenzfelder eines Schritts) stand hier fuer den Import.
# Seit Punkt-IDs sequenzlokal sind, rechnet der Import keine IDs mehr um — die
# Liste hatte nur noch diesen Test als Leser und ist geloescht.

# --- Aufloesen: Punkt fuellt pixel/color; fehlt er, entfaellt NUR die Pruefung ---
_st_res = AutoClickerState()
_st_res.points = [_WCP(x=111, y=222, name="Wirkung", id=7, color=(0, 255, 0))]
_seq_v = _SEQ3(name="V", loop_phases=[_LP3(name="L", steps=[
    _SS(x=1, y=2, delay_before=0, point_id=None,
        verify_condition=_WC4(point_id=7))], repeat=1)], points=_st_res.points)
_st_res.active_sequence = _seq_v
with _cl2.redirect_stdout(_io2.StringIO()):
    _rpr3(_st_res, _seq_v)
_sv = _seq_v.loop_phases[0].steps[0]
check("der Punkt fuellt Stelle und Farbe der Nachpruefung",
      _sv.verify_condition.pixel == (111, 222)
      and _sv.verify_condition.color == (0, 255, 0))

# Fehlender Punkt: Vorbedingung wuerde den Schritt ueberspringen — die NACHpruefung
# ist Zusatzsicherung, der Schritt laeuft weiter. Aber gemeldet wird es.
_st_gone = AutoClickerState()
_seq_gone = _SEQ3(name="W", loop_phases=[_LP3(name="L", steps=[
    _SS(x=1, y=2, delay_before=0, point_id=None,
        verify_condition=_WC4(point_id=999))], repeat=1)])
_report = _rpr3(_st_gone, _seq_gone)
_sw = _seq_gone.loop_phases[0].steps[0]
# Entfallen heisst: nicht geprueft — nicht: geloescht. Hier stand
# `verify_condition is None`, und genau das war der stille Datenverlust: das
# naechste Speichern schrieb die Sequenz ohne Nachpruefung (s. contract/points.py).
check("verwaiste Nachpruefung entfaellt, statt den Schritt zu reissen",
      _sw.verify_condition is not None and _sw.verify_condition.unresolved is True
      and _sw.unresolved is False)
check("und wird gemeldet", any("Nachpruefung" in m for m in _report))

# --- Laufzeit: wiederholen bis es wirkt, dann aufgeben ---
class _FakeImg:
    def __init__(self, color): self.color = color
    def getpixel(self, _): return self.color

def _run(effective_from_click, retries, else_cfg=None):
    """Fuehrt einen Schritt mit Nachpruefung aus. Gibt (ergebnis, klicks, shots) zurueck.

    Die Attrappe haengt am KLICK-Zaehler, nicht am Screenshot-Zaehler: eine Pruefung
    pollt mehrfach innerhalb ihres Zeitfensters, ein Screenshot-Zaehler wuerde also
    schon beim ersten Versuch gruen werden und nie eine Wiederholung ausloesen.
    """
    st = AutoClickerState()
    st.config = AppConfig()
    st.config.click_move_delay = st.config.click_post_delay = 0.0
    st.config.verify_timeout, st.config.verify_interval = 0.06, 0.02
    st.config.verify_retries = retries
    counters = {"shots": 0}
    def _shot(region=None):
        counters["shots"] += 1
        return _FakeImg((0, 255, 0) if st.total_clicks >= effective_from_click else (255, 0, 0))
    old_shot, old_click, old_fs = _RS.take_screenshot, _RA.send_click, _RS.check_failsafe
    _RS.take_screenshot, _RA.send_click, _RS.check_failsafe = _shot, (lambda *a, **k: True), (lambda s: False)
    try:
        step = _SS(x=1, y=2, delay_before=0.0, name="T", point_id=1,
                   verify_condition=_WC4(point_id=2, pixel=(5, 6), color=(0, 255, 0)),
                   else_config=else_cfg)
        with _cl2.redirect_stdout(_io2.StringIO()):
            res = _RS.execute_step(st, step, 1, 1, "Loop")
        return res, st.total_clicks, counters["shots"]
    finally:
        _RS.take_screenshot, _RA.send_click, _RS.check_failsafe = old_shot, old_click, old_fs

_res, _clicks, _shots = _run(effective_from_click=1, retries=2)
check("wirkt die Aktion sofort, wird sie NICHT wiederholt",
      _res is True and _clicks == 1)
_res, _clicks, _shots = _run(effective_from_click=2, retries=2)
check("wirkt sie erst nach einer Wiederholung, wird sie wiederholt", _clicks == 2)
check("und der Schritt gilt als erledigt", _res is True)
_res, _clicks, _shots = _run(effective_from_click=9999, retries=2)
check("bleibt die Wirkung aus, wird genau (retries+1)x versucht", _clicks == 3)
check("danach reisst die Sequenz NICHT ab (Hinweis, kein Abbruch)", _res is True)
_erg0, _clicks0, _ = _run(effective_from_click=9999, retries=0)
check("verify_retries=0 heisst: ein Versuch, keine Wiederholung", _clicks0 == 1)
# Mit else greift dieselbe Mechanik wie bei einer nicht erfuellten Vorbedingung
_erg_e, _, _ = _run(effective_from_click=9999, retries=1, else_cfg=_EC4(action=_ESK4))
check("mit else_config greift else nach dem letzten Versuch", _erg_e is True)

# Der Normalfall darf nichts kosten: ohne Bedingung kein einziger Screenshot
def _run_without():
    st = AutoClickerState(); st.config = AppConfig()
    st.config.click_move_delay = st.config.click_post_delay = 0.0
    counters = {"shots": 0}
    def _shot(region=None):
        counters["shots"] += 1
        return _FakeImg((0, 255, 0))
    old_shot, old_click, old_fs = _RS.take_screenshot, _RA.send_click, _RS.check_failsafe
    _RS.take_screenshot, _RA.send_click, _RS.check_failsafe = _shot, (lambda *a, **k: True), (lambda s: False)
    try:
        with _cl2.redirect_stdout(_io2.StringIO()):
            _RS.execute_step(st, _SS(x=1, y=2, delay_before=0.0, point_id=1), 1, 1, "Loop")
        return counters["shots"]
    finally:
        _RS.take_screenshot, _RA.send_click, _RS.check_failsafe = old_shot, old_click, old_fs
check("ohne Nachpruefung kostet der Schritt keinen Screenshot", _run_without() == 0)




# --------------------------- Scan-Configs: Schreib- und Leseseite gegeneinander
section("Scan-Configs: jedes Feld ueberlebt den Datei-Zyklus")

# Fuer Items, Slots, Punkte, Bosse und Schritte liegen Schreib- UND Leseseite in
# serialization.py. Bei den drei Scan-Typen steht dort nur der Writer; der Reader ist
# in persistence/<typ>.py ausgeschrieben. Zwei handgepflegte Feldlisten, die driften
# koennen - ein Feld, das nur der Writer kennt, faellt sonst niemandem auf.
#
# Der Test setzt jedes Feld auf einen Nicht-Default-Wert, schreibt eine echte Datei
# und liest sie zurueck. Was nicht ankommt, ist ein Loch.
import dataclasses as _dc5
import tempfile as _tf5, os as _os5
from autoclicker.models import (ItemScanConfig as _ISC5, BossScanConfig as _BSC5,
                                IconScanConfig as _ICS5)

# Abgeleitete Felder - stehen bewusst nicht in der Datei (siehe CLAUDE.md)
_SCAN_FLUECHTIG = {
    "ItemScanConfig": {"slots", "items", "owner_sequence"},
    "BossScanConfig": {"bosses"},                # eigene Liste, eigener Serialisierer
    "IconScanConfig": {"action_x", "action_y"},  # aus action_point_id
}
# Besitzer wird aus dem Ordner abgeleitet und steht bewusst in keiner Scan-Datei.
_SCAN_FLUECHTIG["BossScanConfig"].add("owner_sequence")
_SCAN_FLUECHTIG["IconScanConfig"].add("owner_sequence")


def _probe_value(field):
    """Ein Wert, der garantiert vom Default abweicht (None = Feld nicht pruefbar)."""
    t = str(field.type)
    d = field.default if field.default is not _dc5.MISSING else None
    if "bool" in t:
        return not bool(d)
    if "float" in t:
        return (d or 0.0) + 3.5
    if "int" in t and "tuple" not in t and "list" not in t:
        return (d or 0) + 7
    if "str" in t and "list" not in t and "dict" not in t:
        return "PROBE"
    return None


_old_cwd5 = _os5.getcwd()
_sandbox5 = _tf5.mkdtemp(prefix="scanfelder_")
_scan_holes = []
try:
    _os5.chdir(_sandbox5)
    from autoclicker.persistence import init_directories as _init5
    from autoclicker.utils import sanitize_filename as _san5
    from autoclicker.persistence.item_scans import (save_item_scan as _svi5,
                                                    load_item_scan_file as _ldi5)
    from autoclicker.persistence.boss_scans import (save_boss_scan as _svb5,
                                                    load_boss_scan_file as _ldb5)
    from autoclicker.persistence.icon_scans import (save_icon_scan as _svc5,
                                                    load_icon_scan_file as _ldc5)
    from autoclicker.persistence.sequences import sequence_dir as _seqdir5
    _owner5 = "ProbeSeq"
    with _cl2.redirect_stdout(_io2.StringIO()):
        _init5()
        for _label5, _kls5, _save5, _load5, _dir5 in (
                ("ItemScanConfig", _ISC5, _svi5, _ldi5, "item_scans"),
                ("BossScanConfig", _BSC5, _svb5, _ldb5, "boss_scans"),
                ("IconScanConfig", _ICS5, _svc5, _ldc5, "icon_scans")):
            _fl5 = _SCAN_FLUECHTIG.get(_label5, set())
            for _f5 in _dc5.fields(_kls5):
                if _f5.name in _fl5 or _f5.name == "name":
                    continue
                _w5 = _probe_value(_f5)
                if _w5 is None:
                    continue
                _cfg5 = _kls5(name="Probe", owner_sequence=_owner5)
                setattr(_cfg5, _f5.name, _w5)
                _save5(_cfg5)
                # Der Dateiname folgt dem SANITISIERTEN Namen ("probe.json"), nicht
                # dem eingetippten. Auf Windows faellt das nicht auf - dort ist das
                # Dateisystem gross/klein-blind -, auf Linux war jede Pruefung hier
                # "Datei nicht ladbar" und der Abschnitt dauerhaft rot.
                _to5 = _load5(_seqdir5(_owner5) / _dir5
                               / f"{_san5('Probe')}.json", _owner5)
                if _to5 is None:
                    _scan_holes.append(f"{_label5}.{_f5.name}: Datei nicht ladbar")
                elif getattr(_to5, _f5.name, "<fehlt>") != _w5:
                    _scan_holes.append(
                        f"{_label5}.{_f5.name}: geschrieben={_w5!r} -> "
                        f"gelesen={getattr(_to5, _f5.name, '<fehlt>')!r}")
finally:
    _os5.chdir(_old_cwd5)
    import shutil as _sh5
    _sh5.rmtree(_sandbox5, ignore_errors=True)

check("jedes Scan-Feld kommt so zurueck, wie es geschrieben wurde", _scan_holes == [])
if _scan_holes:
    for _z5 in _scan_holes:
        print("        " + _z5)


# ------------------------------------------------ Punkte aus dem zweiten Prozess
section("Was das Sequenz-Studio schreibt, findet der Hauptprozess wieder")

# Der Fall aus dem Alltag: das Studio legt einen Punkt an und speichert die
# Sequenz. Punkt und Schritt müssen aus derselben `sequence.json` kommen; eine
# zweite Datei oder ein Speicher-Merge würde wieder zwei Zeitstände mischen.
import shutil as _sh11
from autoclicker.models import AutoClickerState as _ST11

_old_cwd11 = _os.getcwd()
_sandbox11 = tempfile.mkdtemp(prefix="punkte_nach_")
try:
    _os.chdir(_sandbox11)
    from autoclicker.persistence import (ensure_sequences_dir as _esd11,
                                         load_sequence_file as _lsf11,
                                         sequence_file as _sf11)
    with _cl2.redirect_stdout(_io2.StringIO()):
        _esd11()

    _st11 = _ST11()
    _studio11 = _sf11("studio")
    _studio11.parent.mkdir(parents=True, exist_ok=True)
    _studio11.write_text(json.dumps({
        "name": "studio", "schema_version": _MG.SCHEMA_VERSION, "total_cycles": 1,
        "points": [
            {"id": 1, "x": 11, "y": 21, "name": "Bank", "color": [1, 2, 3]},
            {"id": 51, "x": 300, "y": 400, "name": "Studio", "color": [9, 9, 9]},
        ],
        "init_steps": [{"point_id": 51, "delay_before": 0}],
        "loop_phases": [], "end_steps": []}), encoding="utf-8")

    with _cl2.redirect_stdout(_io2.StringIO()):
        _seq11 = _lsf11(_studio11)

    _step11 = _seq11.init_steps[0]
    check("der im Studio angelegte Punkt loest sich auf",
          not getattr(_step11, "unresolved", False)
          and (_step11.x, _step11.y) == (300, 400))
    check("der Punkt-Pool kommt vollständig aus derselben Datei",
          {p.id for p in _seq11.points} == {1, 51})

    # IDs gelten nur innerhalb einer Sequenz: dieselbe #51 darf woanders auf
    # eine andere Stelle zeigen, ohne beim Laden zusammengemischt zu werden.
    _other11 = _sf11("andere")
    _other11.parent.mkdir(parents=True, exist_ok=True)
    _other11.write_text(json.dumps({
        "name": "andere", "schema_version": _MG.SCHEMA_VERSION,
        "points": [{"id": 51, "x": 7, "y": 8, "name": "Eigen"}],
        "init_steps": [{"point_id": 51, "delay_before": 0}],
        "loop_phases": [], "end_steps": []}), encoding="utf-8")
    with _cl2.redirect_stdout(_io2.StringIO()):
        _seq_other11 = _lsf11(_other11)
    check("gleiche Punkt-ID in anderer Sequenz bleibt unabhängig",
          (_seq_other11.init_steps[0].x, _seq_other11.init_steps[0].y) == (7, 8)
          and (_step11.x, _step11.y) == (300, 400))

    _other11.write_text("{kein json", encoding="utf-8")
    with _cl2.redirect_stdout(_io2.StringIO()):
        _broken11 = _lsf11(_other11)
    check("eine unlesbare sequence.json wird sicher abgelehnt", _broken11 is None)
finally:
    _os.chdir(_old_cwd11)
    _sh11.rmtree(_sandbox11, ignore_errors=True)

# Der Weg, den der Nutzer wirklich geht: CTRL+ALT+L bzw. der Studio-Startbefehl.
# Beide müssen die vollständige Sequenzdatei laden; ein separates Nachladen von
# Punkten wäre gerade wieder der alte, verteilte Vertrag.
import ast as _ast11

_wrong_reload11 = []
for _path11, _function11 in (
        ("autoclicker/handlers.py", "command_start"),
        ("autoclicker/handlers.py", "handle_switch"),
        ("autoclicker/editors/sequence_editor/loader.py", "run_sequence_loader")):
    _tree11 = _ast11.parse(Path(_path11).read_text(encoding="utf-8"))
    for _k11 in _ast11.walk(_tree11):
        if isinstance(_k11, _ast11.FunctionDef) and _k11.name == _function11:
            _names11 = {_n11.func.id for _n11 in _ast11.walk(_k11)
                        if isinstance(_n11, _ast11.Call)
                        and isinstance(_n11.func, _ast11.Name)}
            if "load_sequence_file" in _names11 and "reload_points" in _names11:
                _wrong_reload11.append(f"{_path11}:{_function11}")
check("kein Ladeweg mischt einen separaten Punkte-Pool hinein",
      _wrong_reload11 == [])
if _wrong_reload11:
    for _z11 in _wrong_reload11:
        print("        " + _z11)


# ------------------------------------------------ Fenster-Symbol
section("Das Fenster-Symbol wartet auf sein Fenster")

# `webview.start(func)` ruft func auf, BEVOR das Fenster steht - nachgemessen:
# zum Zeitpunkt des Aufrufs findet EnumWindows nichts, zwei Sekunden spaeter
# schon. Ohne Frist fiel set_window_icon() still auf False, und das Studio
# behielt das Symbol von python.exe.
import time as _t12
from autoclicker.platforms.windows import (
    set_window_icon as _sfs12, _icon_bits as _sb12,
)
import autoclicker.symbol as _sym12

_t0_12 = _t12.monotonic()
_erg12 = _sfs12("Fenster mit diesem Titel gibt es garantiert nicht", waiting=0.5)
_duration12 = _t12.monotonic() - _t0_12
check("ohne passendes Fenster wird die Frist ausgeschoepft und dann aufgegeben",
      _erg12 is False and _duration12 >= 0.45)

_t0_12 = _t12.monotonic()
_sfs12("Fenster mit diesem Titel gibt es garantiert nicht")
check("ohne Frist wird wie bisher genau einmal geschaut",
      _t12.monotonic() - _t0_12 < 0.4)

# Die Bilddaten sind reine Rechnung und deshalb auch ohne Windows pruefbar. Sie
# waren der zweite Teil des Fehlers: mit geraeteabhaengigen 24-Bit-Bits kam am
# Fenster ein schwarzes Quadrat an.
import struct as _struct12


def _symbolpixel12(bits, edge, x, y):
    """(B, G, R, A) an (x, y) mit Ursprung OBEN links - die Datei steht kopf."""
    offset = 40 + ((edge - 1 - y) * edge + x) * 4
    return tuple(bits[offset:offset + 4])


_symbol_holes12 = []
for _edge12 in (16, 32):
    _bits12 = _sb12(_edge12)
    _fields12 = _struct12.unpack("<IiiHHIIiiII", _bits12[:40])
    if not (_fields12[0] == 40 and _fields12[1] == _edge12
            and _fields12[3] == 1 and _fields12[4] == 32):
        _symbol_holes12.append(f"{_edge12}: Kopf beschreibt etwas anderes")
    # Die Hoehe im Kopf zaehlt doppelt: Farb- und Maskenbild untereinander.
    if _fields12[2] != _edge12 * 2:
        _symbol_holes12.append(f"{_edge12}: Hoehe im Kopf zaehlt nicht doppelt")
    # Maskenzeilen sind auf 4 Byte aufgefuellt - bei 16 px sind das 4, nicht 2.
    if len(_bits12) != 40 + _edge12 * _edge12 * 4 + 4 * _edge12:
        _symbol_holes12.append(f"{_edge12}: Laenge passt nicht zum Kopf")
    _corners12 = [_symbolpixel12(_bits12, _edge12, x, y)[3]
                for x in (0, _edge12 - 1) for y in (0, _edge12 - 1)]
    # Der gelieferte Radius ist bei 16 px nur gut einen Pixel gross. Der
    # Eckpixel ist deshalb kantengeglaettet, nicht zwingend komplett leer.
    if any(a >= 255 for a in _corners12):
        _symbol_holes12.append(f"{_edge12}: Ecken nicht abgerundet ({_corners12})")
    _innen12 = [_symbolpixel12(_bits12, _edge12, x, y)[3]
                for y in range(2, _edge12 - 2) for x in range(2, _edge12 - 2)]
    # Das neue Motiv hat absichtlich auch in der Mitte transparente Aussparungen.
    # Gesucht werden deshalb beide Zustaende statt eines alten festen Mittelpixels.
    if not any(a == 255 for a in _innen12) or not any(a == 0 for a in _innen12):
        _symbol_holes12.append(f"{_edge12}: Grund/Aussparung im Innern fehlt")

# Die durchsichtigen Ecken sind dabei der Beleg fuer die Rundung: ein randvolles
# Quadrat sieht aus wie ein Farbmuster, nicht wie ein Symbol.
check("beide Groessen stimmen in Kopf, Laenge, Rundung und Deckung",
      _symbol_holes12 == [])
if _symbol_holes12:
    for _z12 in _symbol_holes12:
        print("        " + _z12)

# DIB-Zeilen stehen von unten nach oben. Statt eine Stelle des alten Motivs als
# Orientierungshilfe festzuschreiben, wird jedes Pixel mit der kanonischen
# SVG-Rasterung verglichen. Das deckt Umdrehen, Kanalreihenfolge und Alpha ab.
_bits12 = _sb12(32)
_expected12 = list(_sym12.pixel_rows(32))
check("die Zeilen stehen von unten nach oben in der Datei",
      all(_symbolpixel12(_bits12, 32, x, y)
          == (_expected12[y][x][2], _expected12[y][x][1], _expected12[y][x][0], _expected12[y][x][3])
          for y in range(32) for x in range(32)))

# --- Ein gewaehltes Fenster wird DIREKT abgebildet ---
# Ein Ausschnitt vom Desktop zeigt, was auf dem Schirm zu sehen ist - also auch
# das Studio, das davor liegt. PrintWindow fragt das Fenster selbst.
import autoclicker.imaging as _img12
import autoclicker.platforms.windows as _win12

check("es gibt einen Weg, ein Fenster direkt abzubilden",
      callable(getattr(_img12, "take_window_screenshot", None)))
# PW_RENDERFULLCONTENT ist der Teil, auf den es ankommt: ohne dieses Flag
# liefern Fenster mit GPU-beschleunigtem Inhalt ein leeres Rechteck.
check("und zwar mit PW_RENDERFULLCONTENT",
      getattr(_win12, "PW_RENDERFULLCONTENT", 0) == 0x2)
check("ohne Fenster-Kennung passiert nichts",
      _img12.take_window_screenshot(0) is None)

# Der Pruefstein dahinter: manche Fenster geben trotz des Flags Schwarz zurueck.
# Das sieht aus wie ein Ergebnis und ist keines - alles Weitere arbeitete dann
# auf Nichts, ohne dass es jemand merkt.
try:
    from PIL import Image as _PIL12
    _pillow_present2 = True
except ImportError:
    _pillow_present2 = False
if _pillow_present2:
    check("eine einfarbige Flaeche gilt als leer",
          _img12.is_blank(_PIL12.new("RGB", (8, 8), (0, 0, 0))) is True)
    _bunt12 = _PIL12.new("RGB", (8, 8), (0, 0, 0))
    _bunt12.putpixel((4, 4), (255, 0, 0))
    check("ein Bild mit Inhalt nicht", _img12.is_blank(_bunt12) is False)
check("und None erst recht", _img12.is_blank(None) is True)

# Die Fensterliste liefert die Kennung mit - ohne sie liesse sich das Fenster
# spaeter nicht ansprechen, und ueber den Titel geht es nicht: bei mehreren
# Fassungen desselben Spiels ist er dreimal derselbe.
_source_wf12 = Path("autoclicker/platforms/windows.py").read_text(encoding="utf-8")
_lf12 = next(_k12 for _k12 in _ast11.walk(_ast11.parse(_source_wf12))
             if isinstance(_k12, _ast11.FunctionDef) and _k12.name == "list_windows")
_attachments12 = [_n12 for _n12 in _ast11.walk(_lf12)
               if isinstance(_n12, _ast11.Call)
               and isinstance(_n12.func, _ast11.Attribute)
               and _n12.func.attr == "append"]
check("die Fensterliste haengt drei Angaben an (Titel, Lage, Kennung)",
      len(_attachments12) == 1
      and isinstance(_attachments12[0].args[0], _ast11.Tuple)
      and len(_attachments12[0].args[0].elts) == 3)

# --- Das Studio laedt die Config nicht zweimal ---
# Der Subprozess teilt seine Ausgabe mit dem Hauptprozess. Beim Oeffnen stand
# dort zweimal "[CONFIG] Geladen": einmal vom Import des Pakets, einmal von
# _without_else(). Ein Leser darf weder die Datei schreiben noch die Konsole.
_source_br12 = Path(
    "autoclicker/editors/sequence_studio/bridge_services.py").read_text(
    encoding="utf-8")
_tree_br12 = _ast11.parse(_source_br12)
_lader12 = [_k12.lineno for _k12 in _ast11.walk(_tree_br12)
            if isinstance(_k12, _ast11.Call) and isinstance(_k12.func, _ast11.Name)
            and _k12.func.id == "load_config"]
check("die Bruecke ruft load_config() nirgends auf", _lader12 == [])
if _lader12:
    print("        Zeilen: " + ", ".join(str(z) for z in _lader12))
check("sie liest die Datei stattdessen selbst",
      "_config_file" in _source_br12)

# --- EINE SVG-Datei, alle Verwendungen ---
# Der Kopf und das Favicon laden die Datei direkt; symbol.py rastert genau diese
# Datei fuer Windows und tools/symbol.py. Damit ist das neue Logo nicht nur im
# grossen Fenster neu, waehrend ALT+TAB noch das alte Motiv zeigt.
_head12 = _H.studio_web_source()
_logo12 = _sym12.LOGO_PATH.read_text(encoding="utf-8")
check("die kanonische Logo-Datei liegt direkt bei der Weboberflaeche",
      _sym12.LOGO_PATH.name == "sequenz-studio-logo.svg" and _sym12.LOGO_PATH.exists())
check("Kopf und Favicon benutzen beide diese Datei",
      _head12.count('sequenz-studio-logo.svg') == 2)
# **Geprueft wird die Eigenschaft, nicht die Zeichnung.** Hier stand einmal
# 'rotate(180 128 128)' — ein Detail genau dieses Motivs, das beim naechsten
# neu gezeichneten Logo umfaellt, ohne dass etwas kaputt waere. Tragend sind
# zwei Dinge: die Maske (sonst gibt es keine echte Transparenz) und die
# Befehlsmenge, die `_path_polygons` ueberhaupt lesen kann — ein 'A' aus einem
# CAD-Export wuerde es mit ValueError ablehnen, und zwar erst beim Rastern.
check("das Logo traegt eine Maske statt einer Ersatzfarbe",
      'mask="url(#cutout)"' in _logo12)
# **Die flache Farbflaeche muss die ERSTE im Dokument bleiben.** symbol.py nimmt
# `next(rect mit mask=...)` und will dort sechs Hex-Ziffern; ein `url(#gold)`
# faellt mit ValueError um. Genau darauf beruht die Plakette: Verlauf, Rand und
# Innenschatten liegen DARUEBER und werden beim Rastern nicht gesehen, das
# 16-px-Symbol bleibt eine lesbare flache Flaeche.
import re as _re12c
_rects12 = _re12c.findall(r'<rect[^>]*mask="url\(#cutout\)"[^>]*>', _logo12)
check("der Rasterer findet zuerst eine flache Hex-Farbe",
      bool(_rects12) and _re12c.search(r'fill="#[0-9A-Fa-f]{6}"', _rects12[0]))
import re as _re12b
_commands12 = set(_re12b.findall(r'[A-Za-z]', " ".join(
    _re12b.findall(r'\sd="([^"]+)"', _logo12))))
check("und benutzt nur die SVG-Befehle, die symbol.py lesen kann",
      _commands12 <= {"M", "L", "C", "Z"})
if not _commands12 <= {"M", "L", "C", "Z"}:
    print("        unlesbar: " + ", ".join(sorted(_commands12 - {"M", "L", "C", "Z"})))
check("die alte, doppelte Inline-Zeichnung ist entfernt", '<svg width="20"' not in _head12)

# Auch die kleinste Windows-Fassung muss ein echtes Bild mit transparenten
# Ecken UND transparenten Aussparungen im Innern ergeben. Zwischenwerte im
# Alpha-Kanal beweisen, dass die Kanten geglaettet statt hart gerastert werden.
_pixel12 = list(_sym12.pixel_rows(16))
_flach12 = [p for z in _pixel12 for p in z]
check("die Rasterung liefert genau 16 x 16 Pixel",
      len(_pixel12) == 16 and all(len(z) == 16 for z in _pixel12))
check("sie verwendet exakt die Farbe des gelieferten SVGs",
      all(p[:3] == (0xD9, 0xA4, 0x20) for p in _flach12))
check("Grund, transparente Aussparungen und Kantenglaettung bleiben erhalten",
      any(p[3] == 255 for p in _flach12)
      and any(p[3] == 0 for p in _flach12)
      and any(0 < p[3] < 255 for p in _flach12))
check("Transparenz liegt auch mitten im Motiv, nicht nur an den Aussenecken",
      any(_pixel12[y][x][3] == 0 for y in range(2, 14) for x in range(2, 14)))

# --- Die Dateien fuer eine Verknuepfung ---
# Das Fenstersymbol setzt die App selbst; eine Verknuepfung, ein angehefteter
# Eintrag oder ein Ordnerbild nehmen es dagegen aus einer DATEI. PNG und ICO
# werden deshalb geschrieben statt im Repo zu liegen - eine Binaerdatei waere
# eine Kopie, die niemand mitzieht.
import importlib.util as _ilu12
_spec12 = _ilu12.spec_from_file_location(
    "_werkzeug_symbol", Path("tools/symbol.py"))
_werk12 = _ilu12.module_from_spec(_spec12)
_spec12.loader.exec_module(_werk12)

_png12 = _werk12.png_bytes(32)
check("das PNG traegt die Signatur", _png12.startswith(b"\x89PNG\r\n\x1a\n"))
check("und im Kopf die richtige Groesse und RGBA",
      _struct12.unpack(">IIBBBBB", _png12[16:29]) == (32, 32, 8, 6, 0, 0, 0))
check("die Stuecke stehen in der Reihenfolge, die das Format verlangt",
      _png12.index(b"IHDR") < _png12.index(b"IDAT") < _png12.index(b"IEND"))

_ico12 = _werk12.ico_bytes((16, 32, 256))
_type12, _art12, _cnt12 = _struct12.unpack("<HHH", _ico12[:6])
check("das ICO hat einen Verzeichniskopf", (_type12, _art12, _cnt12) == (0, 1, 3))
_entries12 = [_struct12.unpack("<BBBBHHII", _ico12[6 + i * 16:22 + i * 16])
                for i in range(_cnt12)]
# 256 steht als 0 im Verzeichnis: ein Byte fasst nur bis 255.
check("256 steht als 0 im Verzeichnis, wie das Format es will",
      [e[0] for e in _entries12] == [16, 32, 0])
check("jeder Eintrag zeigt auf ein eingebettetes PNG",
      all(_ico12[e[7]:e[7] + 8] == b"\x89PNG\r\n\x1a\n" for e in _entries12))
check("und die Laengen decken die Datei genau ab",
      _entries12[-1][7] + _entries12[-1][6] == len(_ico12))

# Titelleiste und Taskleiste sind zwei Mechanismen. Das Fenstersymbol reichte
# fuer die eine; die andere sortierte das Fenster weiter unter python.exe ein und
# zeigte dessen Symbol. Erst eine eigene AppUserModelID loest es aus der Gruppe.
from autoclicker.platforms.windows import set_app_id as _said12, APP_ID as _AID12

check("die Kennung fuer die Taskleiste laesst sich setzen", _said12() is True)
if sys.platform == "win32":
    _buffer12 = ctypes.c_wchar_p()
    _hr12 = ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID(
        ctypes.byref(_buffer12))
    check("und Windows gibt danach genau sie zurueck",
          _hr12 == 0 and _buffer12.value == _AID12)
else:
    # Ohne Windows bleibt nur die Form pruefbar - die Schnittstelle verlangt eine
    # punktgetrennte Kennung ohne Leerzeichen.
    check("die Kennung hat die Form, die die Schnittstelle verlangt",
          "." in _AID12 and " " not in _AID12 and len(_AID12) <= 128)

# Die eigentliche Regel ist die Reihenfolge: nach dem ersten Fenster hat Windows
# die Zuordnung schon getroffen, ein spaeterer Aufruf aendert nichts mehr.
_source12 = Path("autoclicker/sequence_studio.py").read_text(encoding="utf-8")
_main12 = next(_k12 for _k12 in _ast11.walk(_ast11.parse(_source12))
               if isinstance(_k12, _ast11.FunctionDef) and _k12.name == "main")
_row_id12 = [_n12.lineno for _n12 in _ast11.walk(_main12)
               if isinstance(_n12, _ast11.Call) and isinstance(_n12.func, _ast11.Name)
               and _n12.func.id == "set_app_id"]
_row_window12 = [_n12.lineno for _n12 in _ast11.walk(_main12)
                    if isinstance(_n12, _ast11.Call)
                    and isinstance(_n12.func, _ast11.Attribute)
                    and _n12.func.attr == "create_window"]
check("die Kennung wird gesetzt, BEVOR das erste Fenster entsteht",
      len(_row_id12) == 1 and len(_row_window12) == 1
      and _row_id12[0] < _row_window12[0])




# --------------------------- Marktwert-Bruecke (market_analysis -> Item-Scan)
section("Item-Klicks koennen nach Marktwert statt nach Handpriorität sortieren")

# Die einzige Verbindung zwischen den zwei Teilprojekten, und zwar in EINE Richtung:
# market_analysis schreibt eine Name->Gold-JSON in seinen eigenen output/-Ordner, der
# Autoclicker liest sie, falls in seiner config.json ein Pfad steht. Kein Import in
# irgendeine Richtung - ein Test prueft genau das.
import json as _js6, tempfile as _tf6, os as _os6
from autoclicker.runtime.item_scan import (load_market_values as _lmw,
                                           _effective_priority as _eprio,
                                           _marktwert_cache as _mwc)
from autoclicker.models import ItemProfile as _IP6

# Die Trennung ist die halbe Idee - sie muss gemessen werden, nicht behauptet
# Gemessen wird der IMPORT-Baum, nicht die Erwaehnung: in Kommentaren darf (und soll)
# stehen, woher die Datei kommt - eine Abhaengigkeit ist erst ein import.
import ast as _ast6

def _imported_modules(folder: Path, pattern: str) -> list[str]:
    match = []
    for _p in sorted(folder.rglob("*.py")):
        try:
            tree = _ast6.parse(_p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for _n in _ast6.walk(tree):
            names = []
            if isinstance(_n, _ast6.Import):
                names = [a.name for a in _n.names]
            elif isinstance(_n, _ast6.ImportFrom) and _n.module:
                names = [_n.module]
            if any(nm == pattern or nm.startswith(pattern + ".") for nm in names):
                match.append(f"{_p.name}:{_n.lineno}")
    return match

_root6 = Path(__file__).resolve().parent.parent
_ma_dir = _root6 / "market_analysis"
check("der Autoclicker importiert nichts aus market_analysis",
      _imported_modules(_root6 / "autoclicker", "market_analysis") == [])
check("und market_analysis importiert nichts aus dem Autoclicker",
      _imported_modules(_ma_dir, "autoclicker") == [])

# Leerer Pfad = aus. Das ist der Standard und muss ohne Datei funktionieren.
check("ohne konfigurierten Pfad bleibt alles wie bisher", _lmw("") == {})
check("ein Pfad ins Leere kippt nicht um", _lmw("gibt/es/nicht.json") == {})

_fd6, _path6 = _tf6.mkstemp(suffix=".json")
_os6.close(_fd6)
try:
    Path(_path6).write_text(_js6.dumps({"Kohle": 12.5, "Gold": 900, "Murks": "keine Zahl"}),
                            encoding="utf-8")
    _w6 = _lmw(_path6)
    check("Werte werden gelesen", _w6.get("Kohle") == 12.5 and _w6.get("Gold") == 900.0)
    check("unbrauchbare Eintraege fliegen einzeln raus, nicht die ganze Datei",
          "Murks" not in _w6 and len(_w6) == 2)

    # Sortierung: kleiner gewinnt. Wertvoller muss also kleiner werden.
    _kohle = _IP6(name="Kohle", priority=5)
    _gold = _IP6(name="Gold", priority=9)
    _egal = _IP6(name="Ohne Wert", priority=1)
    check("der wertvollere gewinnt, obwohl seine Handpriorität schlechter ist",
          _eprio(_gold, 9, _w6) < _eprio(_kohle, 5, _w6))
    check("ein Item ohne Marktwert behaelt seine gesetzte Prioritaet",
          _eprio(_egal, 1, _w6) == 1.0)
    # Die Folge, die man kennen muss - deshalb steht sie auch im Docstring
    check("jedes Item MIT Wert gewinnt gegen jedes ohne",
          _eprio(_kohle, 5, _w6) < _eprio(_egal, 1, _w6))
    check("ohne Wertetabelle entscheidet weiter die Handpriorität",
          _eprio(_kohle, 5, {}) == 5.0 and _eprio(_egal, 1, {}) == 1.0)

    # Neu gerechnete Analyse muss ohne Neustart greifen (Cache am mtime)
    _mwc.clear()
    _lmw(_path6)
    Path(_path6).write_text(_js6.dumps({"Kohle": 999.0}), encoding="utf-8")
    _os6.utime(_path6, (0, 0))            # mtime sicher veraendern
    check("eine neu geschriebene Wertetabelle greift ohne Neustart",
          _lmw(_path6).get("Kohle") == 999.0)
finally:
    _os6.unlink(_path6)

# Die Schreibseite: market_analysis baut die Datei aus seinem DataFrame
try:
    import pandas as _pd6
except ImportError:
    _pd6 = None
if _pd6 is not None:
    import importlib.util as _ilu6
    _spec6 = _ilu6.spec_from_file_location("_ma_analyse", _ma_dir / "analysis.py")
    # Der direkte Skriptmodus lädt seine Nachbarmodule ohne Paketpräfix; dafür
    # muss der Ordner wie beim echten Aufruf im Suchpfad stehen.
    sys.path.insert(0, str(_ma_dir))
    try:
        _ma6 = _ilu6.module_from_spec(_spec6)
        _spec6.loader.exec_module(_ma6)
        _df6 = _pd6.DataFrame([
            {"Item": "Kohle", "Gold pro Stück": 12.5},
            {"Item": "Kohle", "Gold pro Stück": 30.0},   # zweites Rezept, besserer Wert
            {"Item": "Murks", "Gold pro Stück": float("nan")},
        ])
        _fd7, _path7 = _tf6.mkstemp(suffix=".json")
        _os6.close(_fd7)
        try:
            _n6 = _ma6.export_market_values(_df6, _path7)
            _out6 = _js6.loads(Path(_path7).read_text(encoding="utf-8"))
            check("die Analyse schreibt Name -> Wert", _n6 == 1 and "Kohle" in _out6)
            check("bei mehreren Rezepten gewinnt der beste Wert", _out6["Kohle"] == 30.0)
            check("NaN landet nicht in der Datei", "Murks" not in _out6)
            check("und der Autoclicker liest genau das wieder",
                  _lmw(_path7).get("Kohle") == 30.0)
        finally:
            _os6.unlink(_path7)
    except Exception as _e6:               # pandas/openpyxl fehlt o.ae. - kein Testfehler
        print(f"  {'-':>4}  Schreibseite uebersprungen ({type(_e6).__name__})")
    finally:
        sys.path.remove(str(_ma_dir))
else:
    print("  ----  Schreibseite uebersprungen (pandas nicht installiert)")






# --------------------------- Sequenz-Studio: Umsortieren und Phasenwechsel
section("Sequenz-Studio sortiert per Ziehen um - auch ueber Phasengrenzen")

# Welcher Index nach dem Ziehen wo landet, ist genau die Art Logik, die still
# falsch wird. Sie lag frueher in der Ansicht und war nur pruefbar, indem der Test
# die halbe GUI stilllegte; seit sie in der Bruecke liegt, laeuft dieser Abschnitt
# ohne jede GUI und auf jeder Plattform.
from autoclicker.editors.sequence_studio.bridge import (
    StudioBridge as _SB8, TRIGGER_PRESENT as _TDA8, TRIGGER_NONE as _TKEIN8,
    TRIGGER_GONE as _TWEG8, trigger_name as _tn8)
from autoclicker.editors.sequence_studio.model import PalettePoint as _PP8
from autoclicker.models import Sequence as _SEQ8, LoopPhase as _LP8


def _bridge8():
    """Studio mit INIT[A] / Loop[1..5] / END[Z] - ohne Fenster, ohne Datei."""
    seq = _SEQ8(
        name="T",
        init_steps=[_SS(x=1, y=1, delay_before=0, name="A", point_id=1)],
        loop_phases=[_LP8(name="Loop", repeat=1, steps=[
            _SS(x=i, y=i, delay_before=0, name=str(i), point_id=i)
            for i in range(1, 6)])],
        end_steps=[_SS(x=9, y=9, delay_before=0, name="Z", point_id=9)])
    return _SB8(seq, Path("sequences/T.json"), "sequences")


def _names8(b, phase):
    return [s.name for s in b.board.lanes[phase].steps]


def _choose8(b, phase, *lines):
    for i, line in enumerate(lines):
        b.select({"phase": phase, "row": line, "mode": "single" if i == 0 else "add"})


def _drag8(b, from_phase, from_row, to_phase, to_row):
    b.drag({"from_phase": from_phase, "from_row": from_row,
              "to_phase": to_phase, "to_row": to_row})


INIT8, LOOP8, END8 = 0, 1, 2

# --- Ziehen innerhalb einer Phase ---
_b8 = _bridge8()
_choose8(_b8, LOOP8, 0)
_drag8(_b8, LOOP8, 0, LOOP8, 3)              # "1" vor Position 3
check("Ziehen nach hinten setzt an die richtige Stelle",
      _names8(_b8, LOOP8) == ["2", "3", "1", "4", "5"])
_b8 = _bridge8()
_choose8(_b8, LOOP8, 4)
_drag8(_b8, LOOP8, 4, LOOP8, 0)              # "5" ganz nach vorne
check("Ziehen nach vorne ebenso", _names8(_b8, LOOP8) == ["5", "1", "2", "3", "4"])
# Auf sich selbst gezogen darf nichts passieren
_b8 = _bridge8()
_choose8(_b8, LOOP8, 2)
_drag8(_b8, LOOP8, 2, LOOP8, 2)
check("auf die eigene Position gezogen aendert nichts",
      _names8(_b8, LOOP8) == ["1", "2", "3", "4", "5"])

# --- Mehrere auf einmal: die Auswahl wandert als Block ---
_b8 = _bridge8()
_choose8(_b8, LOOP8, 0, 1)
_drag8(_b8, LOOP8, 0, LOOP8, 4)
check("eine mehrfache Auswahl wandert zusammenhaengend",
      _names8(_b8, LOOP8) == ["3", "4", "1", "2", "5"])
check("und bleibt danach ausgewaehlt", sorted(_b8.sel_rows) == [2, 3])
# Ein Schritt AUSSERHALB der Auswahl zieht nur sich selbst
_b8 = _bridge8()
_choose8(_b8, LOOP8, 0, 1)
_drag8(_b8, LOOP8, 4, LOOP8, 0)
check("ein Schritt ausserhalb der Auswahl zieht nur sich selbst",
      _names8(_b8, LOOP8) == ["5", "1", "2", "3", "4"])

# --- Ueber die Phasengrenze: das kann der Konsolen-Editor bis heute nicht ---
_b8 = _bridge8()
_choose8(_b8, LOOP8, 0, 1)
_drag8(_b8, LOOP8, 0, INIT8, 1)
check("Schritte lassen sich in eine andere Phase ziehen",
      _names8(_b8, INIT8) == ["A", "1", "2"] and _names8(_b8, LOOP8) == ["3", "4", "5"])
check("die Auswahl folgt in die Zielphase",
      _b8.sel_lane is _b8.board.lanes[INIT8] and sorted(_b8.sel_rows) == [1, 2])
# Ans Ende einer Phase (die Ablage unter der Liste liefert at == len)
_b8 = _bridge8()
_choose8(_b8, LOOP8, 2)
_drag8(_b8, LOOP8, 2, END8, len(_b8.board.lanes[END8].steps))
check("Ziehen ans Ende einer Phase haengt an", _names8(_b8, END8) == ["Z", "3"])

# --- Sammel-Verschieben mit den Pfeilen ---
_b8 = _bridge8()
_choose8(_b8, LOOP8, 1, 2)
_b8.selection_move({"delta": 1})
check("Pfeil runter schiebt die ganze Auswahl",
      _names8(_b8, LOOP8) == ["1", "4", "2", "3", "5"] and sorted(_b8.sel_rows) == [2, 3])
_b8.selection_move({"delta": -1})
check("Pfeil hoch bringt sie zurueck",
      _names8(_b8, LOOP8) == ["1", "2", "3", "4", "5"] and sorted(_b8.sel_rows) == [1, 2])
# An den Raendern passiert nichts (und es wird nichts verschluckt)
_b8 = _bridge8()
_choose8(_b8, LOOP8, 0, 1)
_b8.selection_move({"delta": -1})
check("am oberen Rand bleibt die Reihenfolge stehen",
      _names8(_b8, LOOP8) == ["1", "2", "3", "4", "5"])
_choose8(_b8, LOOP8, 3, 4)
_b8.selection_move({"delta": 1})
check("am unteren Rand ebenso", _names8(_b8, LOOP8) == ["1", "2", "3", "4", "5"])

# --- Sammel-Loeschen ---
_b8 = _bridge8()
_choose8(_b8, LOOP8, 0, 2, 4)
_b8.selection_delete()
check("Sammel-Loeschen trifft genau die ausgewaehlten Schritte",
      _names8(_b8, LOOP8) == ["2", "4"])
check("und leert die Auswahl", _b8.sel_lane is None and _b8.sel_rows == set())

# --- Duplizieren ---
# Ein Block, der einem vorhandenen fast gleicht, ist beim Bauen der Normalfall.
_b8 = _bridge8()
_choose8(_b8, LOOP8, 1)
_b8.selection_duplicate()
check("die Kopie liegt direkt hinter dem Original",
      _names8(_b8, LOOP8) == ["1", "2", "2", "3", "4", "5"])
check("und ist die neue Auswahl", sorted(_b8.sel_rows) == [2])
# Die Kopie zeigt auf DENSELBEN Punkt: ein Duplikat ist erst mal derselbe Klick,
# und ein zweiter Punkt an derselben Stelle waere genau die Doppelung, die
# point_for_position() ueberall sonst vermeidet.
check("sie zeigt auf denselben Punkt",
      _b8.board.lanes[LOOP8].steps[2].point_id
      == _b8.board.lanes[LOOP8].steps[1].point_id)

# Tief kopiert: sonst aendert ein Griff an der Kopie zugleich das Original -
# der teuerste Fehler, den ein Duplizieren machen kann, weil er unsichtbar ist.
_b8 = _bridge8()
_b8.board.lanes[LOOP8].steps[0].else_config = _ECx(action="skip")
_choose8(_b8, LOOP8, 0)
_b8.selection_duplicate()
_b8.board.lanes[LOOP8].steps[1].else_config.action = "restart"
check("die Kopie haengt nicht am Original",
      _b8.board.lanes[LOOP8].steps[0].else_config.action == "skip")

# Mehrfachauswahl: alle Kopien hinter den LETZTEN Gewaehlten, in der Reihenfolge
# der Vorlagen. Jede einzeln hinter ihr Original zu setzen zerrisse die Auswahl
# in abwechselnd Original/Kopie.
_b8 = _bridge8()
_choose8(_b8, LOOP8, 0, 2)
_b8.selection_duplicate()
check("eine Mehrfachauswahl bleibt als Block beisammen",
      _names8(_b8, LOOP8) == ["1", "2", "3", "1", "3", "4", "5"])
check("und die Kopien sind zusammenhaengend gewaehlt", sorted(_b8.sel_rows) == [3, 4])

_b8 = _bridge8()
_z8 = _b8.selection_duplicate()
check("ohne Auswahl passiert nichts - mit Ansage",
      _names8(_b8, LOOP8) == ["1", "2", "3", "4", "5"]
      and _z8["status"]["kind"] == "warn")

# --- Kein Schritt geht je verloren ---
_b8 = _bridge8()
_before8 = sorted(_names8(_b8, INIT8) + _names8(_b8, LOOP8) + _names8(_b8, END8))
_choose8(_b8, LOOP8, 1, 3)
_drag8(_b8, LOOP8, 1, END8, 0)
_drag8(_b8, END8, 0, INIT8, 0)
check("ueber mehrere Phasenwechsel bleibt der Bestand vollstaendig",
      sorted(_names8(_b8, INIT8) + _names8(_b8, LOOP8) + _names8(_b8, END8)) == _before8)

# --- Die Auswahl lebt in genau EINER Phase ---
# Sonst haette "eine Position hoch" keine Bedeutung und die Sammelaktionen waeren
# nicht mehr eindeutig - deshalb faengt ein Klick in einer anderen Spalte neu an.
_b8 = _bridge8()
_choose8(_b8, LOOP8, 0, 1)
_b8.select({"phase": INIT8, "row": 0, "mode": "add"})
check("ein Klick in einer anderen Phase faengt die Auswahl neu an",
      _b8.sel_lane is _b8.board.lanes[INIT8] and _b8.sel_rows == {0})

# --- Auswahl muss sich ebenso leicht wieder abwählen lassen ---
_b8 = _bridge8()
_b8.select({"phase": LOOP8, "row": 1, "mode": "single"})
_b8.select({"phase": LOOP8, "row": 3, "mode": "area"})
check("Umschalt-Klick waehlt den Bereich ab dem festen Anker",
      _b8.sel_rows == {1, 2, 3})
_b8.select({"phase": LOOP8, "row": 3, "mode": "area"})
check("derselbe Umschalt-Klick waehlt den Bereich wieder ab",
      _b8.sel_lane is None and _b8.sel_rows == set())

_b8 = _bridge8()
_b8.phase_selection({"phase": LOOP8})
check("Alle-Blöcke wählt die ganze Phase", _b8.sel_rows == set(range(5)))
_b8.phase_selection({"phase": LOOP8})
check("derselbe Phasenknopf hebt die Auswahl wieder auf", _b8.sel_lane is None)

_b8 = _bridge8()
_choose8(_b8, LOOP8, 0, 2, 4)
_b8.selection_set({"field": "delay_before", "value": "0.5"})
check("eine Wartezeit lässt sich für die Auswahl gemeinsam setzen",
      [s.delay_before for s in _b8.board.lanes[LOOP8].steps]
      == [0.5, 0, 0.5, 0, 0.5])
check("der Snapshot liefert den gemeinsamen Wert für den Sammel-Inspektor",
      _b8.snapshot()["selection"]["delay_before"] == 0.5
      and not _b8.snapshot()["selection"]["delay_before_mixed"])




# --------------------------- Der Inspektor schreibt in Punkte, nicht in Koordinaten
section("Sequenz-Studio: was der Inspektor setzt, ueberlebt das Speichern")

# Der Dear-PyGui-Vorgaenger liess `else_x`, `else_y` und den Pruef-Pixel von Hand
# eintippen. Beides sind abgeleitete Arbeitswerte: `_step_to_dict` schreibt sie
# gar nicht, solange eine Referenz danebensteht - die Eingabe war beim naechsten
# Oeffnen weg. Die Weboberflaeche bietet deshalb ueberall Punkte an, und dieser
# Abschnitt misst, dass wirklich Referenzen entstehen.
from autoclicker.persistence.serialization import _step_to_dict as _s2d9


def _bridge9():
    """Ein Klick-Block mit Punkt #1, dazu drei Punkte in der Palette."""
    seq = _SEQ8(name="I", loop_phases=[_LP8(name="Loop", repeat=1, steps=[
        _SS(x=10, y=20, delay_before=0.5, name="Bank", point_id=1,
            recorded_color=(1, 2, 3))])])
    b = _SB8(seq, Path("sequences/I.json"), "sequences")
    b.points = [_PP8(id=1, x=10, y=20, name="Bank", color=(1, 2, 3)),
                _PP8(id=2, x=30, y=40, name="Tresen", color=(9, 9, 9)),
                _PP8(id=3, x=50, y=60, name="Ausgang")]
    b.select({"phase": 1, "row": 0})
    return b, b.board.lanes[1].steps[0]


# --- Farb-Trigger setzen und wieder wegnehmen ---
_b9, _s9 = _bridge9()
check("ohne Bedingung meldet die Auswahl 'kein Trigger'", _tn8(_s9.wait_condition) == _TKEIN8)
_b9.block_trigger({"choice": _TDA8})
check("'warte bis Farbe DA' legt die Bedingung an", _s9.wait_condition is not None)
check("und nimmt Stelle UND Farbe aus dem Punkt des Schritts",
      _s9.wait_condition.point_id == 1
      and _s9.wait_condition.pixel == (10, 20)
      and _s9.wait_condition.color == (1, 2, 3))
check("die Momentaufnahme zeigt denselben Zustand an",
      _b9.snapshot()["block"]["trigger"] == _TDA8)
_b9.block_trigger({"choice": _TWEG8})
check("Umschalten auf WEG dreht nur die Richtung",
      _s9.wait_condition.until_gone is True and _s9.wait_condition.point_id == 1)
_b9.block_trigger({"choice": _TWEG8, "check_only": True})
check("'nur pruefen' ist eine eigene Eigenschaft, kein vierter Zustand",
      _s9.wait_condition.check_only is True and _s9.wait_condition.until_gone is True)
_b9.block_trigger({"choice": _TKEIN8})
check("'kein Trigger' entfernt die Bedingung wieder", _s9.wait_condition is None)

# --- Ohne Punkt gibt es nichts zu pruefen ---
# Sonst entstuende eine Bedingung auf (0,0) - genau die Sorte stiller Unsinn,
# gegen die es auch keinen Rueckfallwert bei point_id gibt.
_b9, _s9 = _bridge9()
_s9.point_id = None
_state9 = _b9.block_trigger({"choice": _TDA8})
check("ohne Punkt entsteht KEINE Bedingung auf (0,0)", _s9.wait_condition is None)
check("und die Ablehnung wird begruendet",
      "Punkt" in _state9["status"]["text"] and _state9["status"]["kind"] == "warn")

# --- Die Nachpruefung ist dieselbe Bedingung, nur danach ---
_b9, _s9 = _bridge9()
_b9.block_trigger({"which": "verify", "choice": _TDA8})
check("die Nachpruefung laesst sich genauso setzen",
      _s9.verify_condition is not None and _s9.verify_condition.point_id == 1)
check("und laesst den Vor-Trigger in Ruhe", _s9.wait_condition is None)

# --- ELSE-Klick: eine Referenz, keine Koordinaten ---
_b9, _s9 = _bridge9()
_b9.block_else({"action": "click", "point": 2})
check("der ELSE-Klick zeigt auf einen Punkt", _s9.else_config.point_id == 2)
_d9 = _s2d9(_s9)
check("gespeichert wird die Referenz", _d9.get("else_point_id") == 2)
check("und NICHT die Koordinate daneben",
      _d9.get("else_x", 0) == 0 and _d9.get("else_y", 0) == 0)
_b9.block_else({"action": ""})
check("leere Aktion nimmt das ELSE wieder weg", _s9.else_config is None)

# --- Ein verschobener Punkt zieht JEDEN Schritt mit, der auf ihn zeigt ---
# Der DPG-Vorgaenger aktualisierte nur den gerade bearbeiteten Schritt; die
# uebrigen zeigten bis zum naechsten Oeffnen die alte Stelle an, obwohl
# gespeichert laengst die neue galt.
_b9, _s9 = _bridge9()
_b9.board.add_step(_b9.board.lanes[1], _SS(x=10, y=20, delay_before=0, name="Bank",
                                           point_id=1))
_b9.point_set({"point": 1, "field": "x", "value": 777})
check("beide Schritte auf demselben Punkt wandern mit",
      all((s.x, s.y) == (777, 20) for s in _b9.board.lanes[1].steps))

# --- Eine neue Stelle wird zum Punkt, nicht zu einer Koordinate im Schritt ---
_b9, _s9 = _bridge9()
_s9.point_id = None
_b9.point_create({"x": 111, "y": 222})
check("ein Blanko-Block bekommt einen echten Punkt",
      _s9.point_id == 4 and len(_b9.points) == 4)
check("und der Punkt traegt seine Herkunft",
      _b9.points[-1].source == "Sequenz-Studio")
_b9.point_create({"x": 111, "y": 222})
check("dieselbe Stelle ergibt KEINEN zweiten Punkt", len(_b9.points) == 4)

# --- Jeder Block-Typ laesst sich anzeigen und umschalten ---
# Die Karte und die Eigenschaften zeigen je nach Typ anderes (Taste statt Punkt,
# kein Trigger beim Screenshot). Ein Typ, der dabei knallt, macht den Block
# unanklickbar - frueher fiel das erst im laufenden Fenster auf.
_seq10 = _SEQ8(name="T", loop_phases=[_LP8(name="Loop", repeat=1, steps=[
    _SS(x=1, y=2, delay_before=0.5, name="K", point_id=1),      # Klick
    _SS(delay_before=1.0, key_press="enter"),                   # Taste
    _SS(delay_before=0, screenshot_only=True, name="S"),        # Screenshot
    _SS(delay_before=0, wait_only=True, name="W"),              # nur warten
    _SS(delay_before=0, item_scan="inv"),                       # Item-Scan
    _SS(delay_before=0, boss_scan="b"),                         # Boss-Scan
    _SS(delay_before=0, icon_scan="i"),                         # Icon-Scan
    _SS(delay_before=0, boss_watcher="w"),                      # Boss-Watcher
])])
_b10 = _SB8(_seq10, Path("sequences/T.json"), "sequences")
_error10, _types10 = [], []
for _r10 in range(len(_seq10.loop_phases[0].steps)):
    try:
        _types10.append(_b10.select({"phase": 1, "row": _r10})["block"]["type"])
    except Exception as _e10:                                    # noqa: BLE001
        _error10.append(f"Zeile {_r10}: {type(_e10).__name__} {_e10}")
check("jeder Block-Typ laesst sich anzeigen", _error10 == [])
if _error10:
    for _z10 in _error10:
        print("        " + _z10)
check("und wird als das erkannt, was er ist",
      _types10 == ["click", "key", "screenshot", "wait", "item_scan", "boss_scan",
                   "icon_scan", "boss_watcher"])
# Umschalten in jeden Typ und zurueck - set_block_type raeumt die Diskriminatoren
_b10.select({"phase": 1, "row": 0})
_error10b = []
for _t10 in [t["key"] for t in _b10.snapshot()["types"]]:
    _z10 = _b10.block_set_type({"type": _t10})
    if _z10["block"]["type"] != _t10:
        _error10b.append(_t10)
check("jeder Typ laesst sich auch einstellen", _error10b == [])

# --- FARBE+KLICK haengt am Punkt, nicht an einer Koordinaten-Kopie ---
# `set_block_type()` legt die Bedingung notfalls auf step.x/y an - das landete als
# wait_pixel/wait_color in der Datei, also als zweite Kopie einer Stelle, die es
# ausserhalb von points.json nicht geben soll. Der Typwechsel bindet sie deshalb an
# den Punkt des Schritts, und ohne Punkt wird er abgelehnt - dieselbe Regel, die
# block_trigger schon hatte.
_b10.select({"phase": 1, "row": 0})
_b10.block_set_type({"type": "click"})
_b10.block_set_type({"type": "wait_click"})
_wc10 = _seq10.loop_phases[0].steps[0].wait_condition
check("der Typwechsel auf FARBE+KLICK bindet die Bedingung an den Punkt",
      _wc10 is not None and _wc10.point_id == 1)
_d10b = _s2d9(_seq10.loop_phases[0].steps[0])
check("gespeichert wird auch hier die Referenz, keine Farb-Kopie",
      _d10b.get("wait_point_id") == 1 and _d10b.get("wait_pixel") is None
      and _d10b.get("wait_color") is None)
_b10.select({"phase": 1, "row": 1})            # Taste, ohne Punkt
_b10.block_set_type({"type": "click"})
_state10 = _b10.block_set_type({"type": "wait_click"})
check("ohne Punkt wird FARBE+KLICK abgelehnt",
      _seq10.loop_phases[0].steps[1].wait_condition is None
      and _state10["block"]["type"] == "click")
check("und auch das wird begruendet",
      _state10["status"]["kind"] == "warn" and "Punkt" in _state10["status"]["text"])

# Und zwar in `set_block_type()` SELBST, nicht als Reparatur danach. Die Funktion
# legte die Bedingung auf die rohen step.x/y an, und die Bruecke bog sie hinterher
# auf den Punkt um - wer sie direkt aufruft (oder die Reparatur vergisst), bekam
# wieder eine Koordinaten-Kopie ausserhalb von points.json.
from autoclicker.editors.sequence_studio.model import set_block_type as _sbt10
from autoclicker.models import SequenceStep as _SS10
_with_point10 = _SS10(x=100, y=200, point_id=7, recorded_color=(1, 2, 3))
_sbt10(_with_point10, "wait_click")
check("set_block_type haengt die Bedingung selbst an den Punkt",
      _with_point10.wait_condition is not None
      and _with_point10.wait_condition.point_id == 7)
# pixel/color sind ABGELEITET und stehen auf ihrem Default, bis `resolve()`
# sie aus dem Punkt fuellt - vorher standen hier step.x/y und recorded_color,
# also eine zweite Kopie der Stelle.
check("und legt keine Koordinaten-Kopie an",
      _with_point10.wait_condition.pixel == (0, 0)
      and _with_point10.wait_condition.color == (0, 0, 0))
_without_point10 = _SS10(x=100, y=200, recorded_color=(1, 2, 3))
_sbt10(_without_point10, "wait_click")
check("und ohne Punkt entsteht gar keine Bedingung",
      _without_point10.wait_condition is None)



# --------------------------- Befehle aus dem Studio an den Hauptprozess
section("Der Briefkasten zwischen Studio und Hauptprozess")

# Die Gegenrichtung zu .run.json: dort schreibt der Hauptprozess, was laeuft,
# hier legt das Studio ab, was passieren soll. Die Regeln, an denen alles haengt:
# genau einmal ausfuehren, und niemals einen Befehl von frueher nachfeuern - ein
# vergessenes "starte" wuerde sonst irgendwann spaeter unerwartet klicken.
import autoclicker.mailbox as _bf13

_sandbox13 = _tf5.mkdtemp(prefix="befehl_")
_cwd13 = _os.getcwd()
_os.chdir(_sandbox13)
try:
    _bf13.COMMAND_PATH = Path(_bf13.COMMAND_PATH.name)   # relativ zum Sandkasten

    check("ohne Briefkasten kommt nichts zurueck", _bf13.fetch_command() is None)

    _bf13.send_command("start", file="sequences/x.json", sequence="X")
    _job13 = _bf13.fetch_command()
    check("ein gesendeter Befehl kommt an",
          _job13 is not None and _job13["command"] == "start")
    check("mit seinen Argumenten",
          _job13["arguments"] == {"file": "sequences/x.json", "sequence": "X"})
    check("und der Briefkasten ist danach leer",
          not _bf13.COMMAND_PATH.exists() and _bf13.fetch_command() is None)

    # Ein Befehl von frueher darf NICHT nachfeuern. Das ist die gefaehrlichste
    # Stelle des ganzen Kanals: er loest Klicks aus.
    _bf13.send_command("start", file="sequences/x.json")
    _old13 = json.loads(_bf13.COMMAND_PATH.read_text(encoding="utf-8"))
    _old13["sent_at"] = _old13["sent_at"] - (_bf13.MAX_AGE + 5)
    _bf13.COMMAND_PATH.write_text(json.dumps(_old13), encoding="utf-8")
    check("ein zu alter Befehl wird verworfen", _bf13.fetch_command() is None)
    check("und liegt danach auch nicht mehr da", not _bf13.COMMAND_PATH.exists())

    # Unlesbares fliegt genauso raus - sonst wird es bei JEDEM Schleifendurchlauf
    # erneut gelesen und gemeldet.
    _bf13.COMMAND_PATH.write_text("{kein json", encoding="utf-8")
    check("eine kaputte Datei ergibt keinen Befehl", _bf13.fetch_command() is None)
    check("und wird trotzdem weggeraeumt", not _bf13.COMMAND_PATH.exists())

    _bf13.COMMAND_PATH.write_text(json.dumps({"stamp": __import__("time").time()}), encoding="utf-8")
    check("ein Eintrag ohne Befehl zaehlt nicht", _bf13.fetch_command() is None)

    # Zweimal senden staut nichts an: wer zweimal stoppt, meint einmal stoppen.
    _bf13.send_command("stop")
    _bf13.send_command("stop")
    check("der zweite Befehl ueberschreibt den ersten", _bf13.fetch_command()["command"] == "stop")
    check("und danach ist Ruhe", _bf13.fetch_command() is None)
finally:
    _os.chdir(_cwd13)

# --- Beide Seiten kennen dieselben Befehle ---
# Der Test, um den es hier eigentlich geht: die Bruecke darf nur senden, was der
# Hauptprozess auch ausfuehrt. Laufen die Listen auseinander, tut ein Knopf im
# Studio einfach nichts - keine Meldung, kein Fehler, nur Stille.
from autoclicker.handlers import COMMANDS as _BEF13

check("jeder Befehl der Bruecke hat einen Handler",
      sorted(_SB8.ALL_COMMANDS) == sorted(_BEF13))

# --- Die Bruecke speichert vor dem Start ---
# Der Hauptprozess laedt die DATEI. Was nur im Speicher steht, liefe nicht mit -
# ein Start-Knopf, der eine aeltere Fassung startet als die angezeigte, waere
# schlimmer als keiner.
_sandbox14 = _tf5.mkdtemp(prefix="studiostart_")
_cwd14 = _os.getcwd()
_os.chdir(_sandbox14)
try:
    Path("sequences").mkdir()
    _bf13.COMMAND_PATH = Path(_bf13.COMMAND_PATH.name)
    _seq14 = _SEQ8(name="Lauf", loop_phases=[_LP8(name="Loop", repeat=1, steps=[
        _SS(x=1, y=2, delay_before=0, name="K", point_id=1)])])
    _b14 = _SB8(_seq14, Path("sequences/lauf/sequence.json"), "sequences")
    _b14.board.total_cycles = 7          # ungespeicherte Aenderung
    _b14._dirty = True
    _state14 = _b14.run_command({"command": "start"})
    check("der Start speichert die offene Sequenz zuerst",
          _b14._dirty is False and Path("sequences/lauf/sequence.json").exists())
    _job14 = _bf13.fetch_command()
    check("und schickt genau diese Datei mit",
          _job14 is not None
          and Path(_job14["arguments"]["file"]) == Path("sequences/lauf/sequence.json"))
    check("die Aenderung steht in der Datei, nicht nur im Speicher",
          json.loads(Path("sequences/lauf/sequence.json").read_text(encoding="utf-8"))
          .get("total_cycles") == 7)
    check("gemeldet wird der Start auch", "gestartet" in _state14["status"]["text"])

    # Scheitert das Speichern, wird NICHT gestartet: sonst liefe die alte Fassung.
    _b14.board.name = ""
    _b14._dirty = True
    _state14b = _b14.run_command({"command": "start"})
    check("ohne Sequenz-Namen faellt der Start aus",
          _state14b["status"]["kind"] == "err" and _bf13.fetch_command() is None)

    # Stopp und Pause gehen ohne Speichern durch - sie betreffen den Lauf, nicht
    # die Datei.
    _b14.board.name = "Lauf"
    _b14.run_command({"command": "stop"})
    check("Stopp braucht kein Speichern", _bf13.fetch_command()["command"] == "stop")
    # --- Die Probe: Maus auf die Stelle des gewaehlten Blocks ---
    _b14.points = [_PP8(id=1, x=10, y=20, name="Bank", color=(1, 2, 3))]
    _b14.select({"phase": 1, "row": 0})
    _b14.point_show()
    _zeig14 = _bf13.fetch_command()
    check("die Probe schickt Stelle, Punkt und Farbe mit",
          _zeig14 is not None and _zeig14["command"] == "show"
          and _zeig14["arguments"]["x"] == 10 and _zeig14["arguments"]["y"] == 20
          and _zeig14["arguments"]["point"] == 1
          and _zeig14["arguments"]["color"] == [1, 2, 3])
    # Ein Block ohne Stelle hat nichts zu zeigen - und schickt deshalb nichts.
    _b14.board.add_step(_b14.board.lanes[1], _SS(delay_before=0, key_press="a"))
    _b14.select({"phase": 1, "row": 1})
    _state14d = _b14.point_show()
    check("ohne Stelle wird nichts geschickt",
          _bf13.fetch_command() is None and _state14d["status"]["kind"] == "warn")
    _b14.select({"phase": 1, "row": 0})

    _state14c = _b14.run_command({"command": "tanzen"})
    check("ein erfundener Befehl wird abgelehnt",
          _state14c["status"]["kind"] == "err" and _bf13.fetch_command() is None)

    # Die einzige Rueckmeldung, die das Fenster ueber den Hauptprozess bekommt: er
    # leert den Kasten. Liegt der Befehl noch, hoert niemand zu - dann darf im
    # Studio nicht "gestartet" stehen bleiben.
    check("ein geleerter Briefkasten heisst: angekommen", _b14.command_pending() is False)
    _b14.run_command({"command": "pause"})
    check("ein liegengebliebener Befehl ist erkennbar", _b14.command_pending() is True)
    _bf13.fetch_command()
    check("und nach dem Abholen wieder nicht", _b14.command_pending() is False)
finally:
    _os.chdir(_cwd14)

# --- Die Bloecke SIND die originalen SequenceStep-Objekte ---
# Das Studio gruppiert um, es konvertiert nicht. Sonst verloere jede Runde durchs
# Studio genau die Felder, die nur der Konsolen-Editor oder die Aufnahme setzen
# (gemessen wurde das einmal am Mausrad, das es inzwischen nicht mehr gibt —
# die Zusicherung gilt fuer jedes Feld, das die Oberflaeche nicht anfasst).
_step11 = _SS(x=5, y=6, delay_before=0, name="Klick", point_id=1, recorded_color=(9, 8, 7))
_seq11 = _SEQ8(name="R", loop_phases=[_LP8(name="Loop", repeat=1, steps=[_step11])])
_b11 = _SB8(_seq11, Path("sequences/R.json"), "sequences")
_b11.select({"phase": 1, "row": 0})
_b11.block_set({"field": "delay_before", "value": 2.0})
from autoclicker.editors.sequence_studio.model import board_to_sequence as _b2s11
_out11 = _b2s11(_b11.board).loop_phases[0].steps[0]
check("der bearbeitete Block ist dasselbe Objekt wie vorher",
      _out11 is _step11 and _out11.delay_before == 2.0)

# --- Unbekannte Felder werden abgelehnt, nicht stillschweigend gesetzt ---
_state11 = _b11.block_set({"field": "gibtsnicht", "value": 1})
check("ein unbekanntes Feld meldet sich als Fehler",
      _state11["status"]["kind"] == "err")
check("und legt nichts am Schritt an", not hasattr(_step11, "gibtsnicht"))

# --- Der Typ-Chip ist das EINE Bedienelement fuer 'nur warten' ---
# In der Ansicht stand darunter ein zweiter Schalter "nur warten (kein Klick)",
# der `wait_only` setzte - also genau das, was der Chip WARTEN setzt. Ein Zustand
# mit zwei Bedienelementen, und das rächte sich: der Schalter blendete sich bei
# genau dem Typ aus, den sein eigenes Einschalten erzeugte. Einmal geklickt, war
# er weg. Was die Chips koennen, steht hier - denn daran haengt, dass der zweite
# Weg entbehrlich ist.
_b13, _s13 = _bridge9()
_b13.block_trigger({"choice": _TDA8})
check("Ausgangslage: Farbe+Klick mit Trigger",
      _b13.snapshot()["block"]["type"] == "wait_click")

_b13.block_set_type({"type": "wait"})
check("der Chip WARTEN macht daraus einen Warte-Block",
      _b13.snapshot()["block"]["type"] == "wait"
      and _b13.snapshot()["block"]["wait_only"] is True)
check("und laesst den Farb-Trigger stehen", _s13.wait_condition is not None)

_b13.block_set_type({"type": "wait_click"})
check("der Chip FARBE+KLICK ist der verlustfreie Weg zurueck",
      _b13.snapshot()["block"]["type"] == "wait_click"
      and _s13.wait_condition is not None and _s13.wait_condition.point_id == 1)

# KLICK verliert den Trigger - das ist keine Nebenwirkung, sondern die Bedeutung
# von KLICK. Nur deshalb braucht es FARBE+KLICK als zweiten Rueckweg.
_b13.block_set_type({"type": "wait"})
_b13.block_set_type({"type": "click"})
check("der Chip KLICK laesst den Trigger bewusst fallen", _s13.wait_condition is None)

# Die Bruecke konnte das alles schon vorher - der Fehler sass in der ANSICHT, und
# darum faengt ihn keiner der Tests darueber. Pruefbar ist von aussen das, was ihn
# ausmachte: ein zweites Bedienelement fuer denselben Zustand.
import re as _re13b

_page13 = _H.studio_web_source()
_toggles13 = _re13b.findall(r'toggle\(\s*"([^"]*)"', _page13)
check("die Ansicht hat ueberhaupt Schalter", len(_toggles13) >= 2)
check("aber keinen zweiten fuer 'nur warten' neben dem Typ-Chip",
      not any("nur warten" in s for s in _toggles13))
check("und keinen anderen, der wait_only setzt",
      'field: "wait_only"' not in _page13)
_action13 = _page13[_page13.index("function buildAction"):
                     _page13.index("function buildPosition")]
check("die automatisch wechselnde Typ-Kachel wird nicht nochmals als 'ergibt' gezeigt",
      '"ergibt"' not in _action13 and "card-type" not in _action13)

# --- Tastendruck-Erkennung fuer Fenster-Prozesse ---
# Das Sequenz-Studio hat keine Konsole, in die man tippen koennte. Auf ENTER zu
# warten heisst dort: GetAsyncKeyState pollen. Der erste Entwurf fragte nur
# 0x8000 ("haelt gerade") ab und sah kurze Druecke nie - die Ecken-Aufnahme kam
# nie zurueck. Geprueft wird die Regel, nicht die API: ein Test, der echte
# Tastendruecke ins System schickt, tippt in das Fenster, das gerade vorn ist.
import time as _t15
from autoclicker.utils.io import key_newly_pressed as _tng15, wait_for_global_key as _wat15

check("gehalten + vorher oben = neuer Druck", _tng15(0x8000, False) is True)
check("gehalten + vorher schon unten = kein neuer Druck", _tng15(0x8000, True) is False)
check("kurzer Druck (nur Bit 0) zaehlt trotzdem", _tng15(0x0001, False) is True)
check("kurzer Druck zaehlt auch bei gehaltener Vortaste", _tng15(0x0001, True) is True)
check("nichts gedrueckt = nichts", _tng15(0x0000, False) is False)
check("losgelassen nach Halten meldet nichts", _tng15(0x0000, True) is False)

# Die Regel oben ist nur dann die Regel, wenn der Windows-Weg sie auch RUFT. Sie
# stand einmal ein zweites Mal ausgeschrieben in `wait_for_key()` — und dieser
# Block prüfte fünfmal eine Funktion, die niemand benutzte.
import inspect as _insp15
from autoclicker.platforms import windows as _pw15
check("wait_for_key entscheidet ueber key_newly_pressed, nicht selbst",
      "key_newly_pressed(" in _insp15.getsource(_pw15.wait_for_key)
      and "& 0x0001" not in _insp15.getsource(_pw15.wait_for_key))

# Die Zeitgrenze gilt auf beiden Plattformen: gestubbt liefert GetAsyncKeyState 0,
# auf Windows drueckt waehrend des Tests niemand.
_t0_15 = _t15.time()
check("ohne Tastendruck kommt None zurueck", _wat15(("enter",), timeout=0.3) is None)
check("und die Zeitgrenze wird eingehalten", _t15.time() - _t0_15 < 3.0)
check("eine Taste, die es nicht gibt, wartet gar nicht erst",
      _wat15(("gibtsnicht",), timeout=30.0) is None)

# --- Screenshot-Bereich: Ecke fuer Ecke mit der Maus ---
# Vier Zahlenfelder sind kein Weg, einen Bildschirmbereich zu bestimmen. Die
# Ecken kommen jetzt von der Maus - eine pro Aufruf, damit die Oberflaeche
# dazwischen sagen kann, welche schon steht. Der Windows-Teil (auf ENTER warten,
# Cursor lesen) wird hier ersetzt; gemessen wird, was die Bruecke daraus macht.
import autoclicker.utils.io as _io15
import autoclicker.winapi as _wa15

_b15 = _SB8(_SEQ8(name="S", loop_phases=[_LP8(name="L", repeat=1, steps=[
    _SS(delay_before=0, screenshot_only=True, screenshot_region=(0, 0, 100, 100))])]),
    Path("sequences/S.json"), "sequences")
_b15.select({"phase": 1, "row": 0})

_real15 = (_io15.wait_for_global_key, _wa15.get_cursor_pos)
try:
    # Beide Ecken in EINEM Aufruf: zwischendurch zum Fenster zurueckzufahren ist
    # genau der Weg, den die Maus-Aufnahme ersparen soll. Hier kommt Ecke 1 unten
    # rechts und Ecke 2 oben links - verkehrt herum, die Bruecke muss sortieren.
    _corners15 = iter([(900, 700), (300, 200)])
    _io15.wait_for_global_key = lambda *a, **k: "enter"
    _wa15.get_cursor_pos = lambda: next(_corners15)
    _z15 = _b15.area_capture()
    check("zwei ENTER ergeben einen Bereich",
          _z15["block"]["screenshot_region"] == [300, 200, 900, 700])
    check("und die Meldung nennt die Groesse", "600×500" in _z15["status"]["text"])

    # Ein Bereich, der keiner ist, wird gemeldet statt still gespeichert.
    _before15 = _z15["block"]["screenshot_region"]
    _corners15 = iter([(300, 200), (301, 201)])
    _z15 = _b15.area_capture()
    check("ein zu kleiner Bereich meldet sich und aendert nichts",
          _z15["status"]["kind"] == "warn"
          and _z15["block"]["screenshot_region"] == _before15)

    # ESC bei der ZWEITEN Ecke: auch die erste darf dann nicht stehenbleiben.
    _corners15 = iter([(10, 10), (20, 20)])
    _keys15 = iter(["enter", "escape"])
    _io15.wait_for_global_key = lambda *a, **k: next(_keys15)
    _z15 = _b15.area_capture()
    check("ESC nach der ersten Ecke laesst den alten Bereich ganz stehen",
          _z15["status"]["kind"] == "warn"
          and _z15["block"]["screenshot_region"] == _before15)

    # Keine Taste innerhalb der Zeitgrenze: dasselbe, nur mit anderem Grund.
    _io15.wait_for_global_key = lambda *a, **k: None
    _z15 = _b15.area_capture()
    check("ohne Tastendruck passiert ebenfalls nichts",
          _z15["status"]["kind"] == "warn"
          and _z15["block"]["screenshot_region"] == _before15)
finally:
    _io15.wait_for_global_key, _wa15.get_cursor_pos = _real15


# --- Die Scan-Konfigurationen kommen zur Auswahl, statt getippt zu werden ---
# Der Name IST die Referenz auf eine Datei in item_scans/ bzw. boss_scans/ bzw.
# icon_scans/. Getippt werden musste er trotzdem, und ein Tippfehler ergab einen
# Block, den der Executor stillschweigend nicht ausfuehrt - dieselbe Klasse
# Fehler wie eine point_id, die ins Leere zeigt.
_sc_tmp = tempfile.mkdtemp()
_sc_cwd = _os.getcwd()
_os.chdir(_sc_tmp)
try:
    _besitz14 = Path("sequences") / "s"
    for _folder14, _files14 in (("item_scans", ["beutel", "amboss"]),
                                  ("boss_scans", ["hoehle"]),
                                  ("icon_scans", [])):
        (_besitz14 / _folder14).mkdir(parents=True, exist_ok=True)
        for _d14 in _files14:
            (_besitz14 / _folder14 / f"{_d14}.json").write_text(
                "{}", encoding="utf-8")

    _b14 = _SB8(_SEQ8(name="S", loop_phases=[_LP8(name="L", repeat=1, steps=[
        _SS(delay_before=0, item_scan="")])]),
        Path("sequences/s/sequence.json"), "sequences")
    _names14 = _b14.snapshot()["scan_names"]
    check("die Momentaufnahme nennt die vorhandenen Item-Scans",
          _names14["item_scan"] == ["amboss", "beutel"])
    check("ein leerer Ordner ergibt eine leere Liste, keinen Fehler",
          _names14["icon_scan"] == [])
    check("der Boss-Watcher bekommt dieselben Konfigurationen wie der Boss-Scan",
          _names14["boss_watcher"] == _names14["boss_scan"] == ["hoehle"])

    # Neu angelegte Konfigurationen tauchen ohne Neustart auf: gelesen wird bei
    # jeder Momentaufnahme. Zwischen Haupt- und Studio-Prozess ist die Datei der
    # einzige gemeinsame Nenner - ein einmal gefuellter Cache waere hier falsch.
    (_besitz14 / "icon_scans" / "lupe.json").write_text("{}", encoding="utf-8")
    check("eine neu angelegte Konfiguration erscheint sofort",
          _b14.snapshot()["scan_names"]["icon_scan"] == ["lupe"])
finally:
    _os.chdir(_sc_cwd)

# --- Ein Scan ohne Konfiguration darf gespeichert werden ---
# Frueher hielt er das Speichern auf, weil er beim Executor durch den
# Truthiness-Dispatch bis zum Klick durchfaellt und zu einem Klick auf (0,0)
# degradiert. Die Begruendung stimmte, die Stelle nicht: wer einen Block anlegt,
# um seine Position im Ablauf festzuhalten, und die Konfiguration erst danach
# baut (anderer Prozess, CTRL+ALT+N), muss das speichern koennen. Repariert wird
# es dort, wo es kaputt ist - siehe den Executor-Abschnitt weiter unten.
_sb12 = tempfile.mkdtemp()
_cwd12 = _os.getcwd()
_os.chdir(_sb12)
try:
    Path("sequences").mkdir()
    _seq12 = _SEQ8(name="S", loop_phases=[_LP8(name="Loop", repeat=1, steps=[
        _SS(delay_before=0, item_scan="")])])
    _b12 = _SB8(_seq12, Path("sequences/S.json"), "sequences")
    _state12 = _b12.save()
    # Gegen den TATSAECHLICHEN Pfad pruefen, nicht gegen "S.json": die Datei folgt
    # dem sanitisierten Namen (hier "s.json"). Auf Windows faellt der Unterschied
    # nicht auf - dort ist das Dateisystem gross/klein-blind -, auf Linux riss der
    # Vergleich die Suite mit einem FileNotFoundError ab und alles darunter lief
    # gar nicht mehr.
    check("ein Scan ohne Konfiguration verhindert das Speichern NICHT",
          _b12.filepath.exists())
    check("Speichern merkt die zuletzt verwendete Sequenz",
          json.loads(Path(".studio-sequence.json").read_text(encoding="utf-8"))["folder"]
          == _b12.filepath.parent.name)
    check("gemeldet wird er trotzdem", _state12["status"]["kind"] == "warn")
    check("und die Meldung nennt die Scan-Art",
          "ITEM-SCAN" in _state12["status"]["text"])
    check("die Karte warnt weiterhin",
          _state12["phases"][1]["blocks"][0]["warning"] == "Name fehlt")

    # Der leere Name muss die Datei ueberleben - sonst waere der Block beim
    # naechsten Oeffnen ein Klick-Block und die Stelle im Ablauf falsch.
    _raw12 = json.loads(_b12.filepath.read_text(encoding="utf-8"))
    check("der leere Scan-Name steht in der Datei",
          _raw12["loop_phases"][0]["steps"][0].get("item_scan") == "")

    # Der Sequenz-Name ist etwas anderes: er IST der Dateiname.
    _b12.board.name = ""
    _z12b = _b12.save()
    check("ohne Sequenz-Namen wird weiterhin nicht gespeichert",
          _z12b["status"]["kind"] == "err")
    check("und die Meldung sagt die Folge zuerst",
          _z12b["status"]["text"].startswith("Nicht gespeichert"))
finally:
    _os.chdir(_cwd12)

# --- ...und zur Laufzeit uebersprungen statt in die Ecke geklickt ---
from autoclicker.runtime.steps import _scan_without_name as _son12

check("ein leerer Item-Scan wird als unfertig erkannt",
      _son12(_SS(delay_before=0, item_scan="")) == "ITEM-SCAN")
check("Leerzeichen zaehlen auch als leer",
      _son12(_SS(delay_before=0, boss_scan="   ")) == "BOSS-SCAN")
check("ein Icon-Scan MIT Namen ist fertig",
      _son12(_SS(delay_before=0, icon_scan="lupe")) is None)
check("ein gewoehnlicher Klick-Schritt ist nicht betroffen",
      _son12(_SS(x=5, y=6, delay_before=0, point_id=1)) is None)
check("und ein Boss-Watcher ohne Namen ebenfalls erkannt",
      _son12(_SS(delay_before=0, boss_watcher="")) == "BOSS-WATCHER")

# Jede Scan-Art, die der Dispatcher kennt, muss auch hier stehen - sonst faellt
# genau die eine wieder bis zum Klick durch.
from autoclicker.runtime.steps import _SCAN_FIELDS as _sf12
from autoclicker.editors.sequence_studio.bridge import SCAN_FIELD as _sfeld12
check("Executor und Studio kennen dieselben Scan-Felder",
      sorted(f for f, _ in _sf12) == sorted(_sfeld12.values()))


# --------------------------- Sequenz-Studio: Seite und Bruecke passen zusammen
section("Sequenz-Studio: jeder Aufruf der Seite passt zur Bruecke")

# Dieselbe Klasse Fehler wie bei den dpg-Signaturen weiter oben, nur eine Ebene
# tiefer: die Seite ruft die Bruecke ueber EINEN Helfer (`call()`), und der reicht
# immer genau ein Argument durch - `null`, wenn es nichts zu uebergeben gibt.
# `snapshot()` nahm keins an, also scheiterte ausgerechnet der Aufruf, der die
# Ansicht ueberhaupt erst fuellt: das Fenster ging auf und blieb leer, mit
# "takes 1 positional argument but 2 were given" in der Statuszeile. Kein Test
# sah das, weil jeder Test die Methoden direkt aufruft - so, wie die Seite es
# gerade NICHT tut.
import inspect as _inspect13, re as _re13

_html13 = _H.studio_web_source()
# JEDER Kanal: `call()` befiehlt, `ask()` fragt nur, `callScan()`, `callShare()`
# und `callTool()` bedienen ihre Reiter. Fehlt einer im Muster, ist der Fehler
# nicht "falsche Logik", sondern "Name existiert gar nicht" - eine leere Ansicht
# mit einer Zeile in der Statusleiste, und aufgefallen waere es erst beim Klicken.
#
# Das Muster endet deshalb auf `\(` und listet die Helfer einzeln: ein blosses
# `\bruf\w*\(` faenge auch `rufMichNicht()`, und ein blosses `\bruf\(` liess
# `callTool("calib_reference")` durchrutschen - also ausgerechnet den neuesten
# Reiter, der am ehesten einen Tippfehler enthaelt.
# `switchSequence` reicht seinen ersten Parameter an `call()` weiter — beim
# Umbenennen der Bruecken-Methode `neu` -> `new` war genau dieser Aufruf
# (`switchSequence("neu")`) der eine, den kein Muster sah: der Knopf „Neu"
# rief eine Methode, die es nicht mehr gab.
_HELPERS13 = ("call", "callScan", "callShare", "callTool", "ask", "switchSequence")
_called13 = set(_re13.findall(
    r'\b(?:' + "|".join(_HELPERS13) + r')\("([a-z_]+)"', _html13))
# `withWait()` ist der sechste Kanal und der einzige, bei dem der Methodenname
# NICHT das erste Argument ist: davor steht, welcher Helfer darunter laeuft
# ("call" / "ask" / "tool"). Ohne diese Zeile faellt jede blockierende
# Methode aus der Pruefung — also ausgerechnet die, die eine Minute lang
# wartet und bei einem Tippfehler gar nichts tut.
_called13 |= set(_re13.findall(
    r'\bwithWait\("(?:call|ask|tool)",\s*"([a-z_]+)"', _html13))
# `withWork()` ist der siebte Kanal — und der Gegenfall zu `withWait`: dort
# wartet die Bruecke auf einen ENTER-Druck, hier RECHNET sie (sechsundfuenfzig
# Modell-Aufrufe hintereinander). Wie dort waehlt das erste Argument den
# Kanal darunter, der Methodenname steht also an zweiter Stelle.
_called13 |= set(_re13.findall(
    r'\bwithWork\("(?:scan|ask)",\s*"([a-z_]+)"', _html13))
_called13 = sorted(_called13)
check("die Seite ruft ueberhaupt Bruecken-Methoden auf", len(_called13) >= 20)
check("und beide Kanaele sind erfasst - auch der fragende",
      "sequence_list" in _called13 and "run_status" in _called13)
check("und der Scans-Reiter ist mit erfasst (callScan)",
      "scan_data" in _called13 and "scan_click" in _called13)
check("und der Werkzeuge-Reiter (callTool)",
      "tool_check" in _called13 and "calib_reference" in _called13)
# Jeder Helfer, den die Seite benutzt, muss im Muster stehen. Sonst waechst ein
# vierter Kanal heran, den dieser Test nicht ansieht - genau so war es bei
# `callTool`, und der Reiter haette ungeprueft ausgeliefert werden koennen.
_KNOWN13 = _HELPERS13 + ("withWait", "withWork")
# Gefunden wird JEDE async-Funktion, die einen Bruecken-Namen weiterreicht —
# nicht nur die mit `call` im Namen. `withWait` heisst nicht so und waere unter
# dem alten Muster still durchgerutscht.
_helper_present13 = sorted(set(_re13.findall(
    r'\basync function (\w+)\(', _html13)))
_helper_present13 = [h for h in _helper_present13
               if h.startswith("call") or h in ("withWait", "withWork", "switchSequence")]
if not all(h in _KNOWN13 for h in _helper_present13):
    print(f"    ungeprueft: {[h for h in _helper_present13 if h not in _KNOWN13]}")
check("und kein Aufruf-Helfer bleibt ungeprueft",
      all(h in _KNOWN13 for h in _helper_present13))

_missing13 = [n for n in _called13 if not callable(getattr(_SB8, n, None))]
check("jede gerufene Methode gibt es in der Bruecke", _missing13 == [])
if _missing13:
    print("        fehlt in bridge.py: " + ", ".join(_missing13))

# `call()` uebergibt IMMER ein Argument - auch bei `call("snapshot")`, dann `null`.
_unpassend13 = []
for _name13 in _called13:
    _f13 = getattr(_SB8, _name13, None)
    if _f13 is None:
        continue
    try:
        _inspect13.signature(_f13).bind(None, None)   # self + das eine Argument
    except TypeError:
        _unpassend13.append(_name13)
check("und jede nimmt das eine Argument an, das die Seite schickt",
      _unpassend13 == [])
if _unpassend13:
    print("        nimmt kein Argument an: " + ", ".join(_unpassend13))

# Gegenprobe von der anderen Seite: die Momentaufnahme muss mit `null` gehen.
# Der try-Zweig ist nicht Zierde - ohne ihn reisst genau dieser Aufruf die ganze
# Suite mit einem TypeError ab, statt eine Zeile FAIL zu melden.
try:
    _same13 = _b12.snapshot(None)["name"] == _b12.snapshot()["name"]
except TypeError:
    _same13 = False
check("snapshot(None) liefert denselben Zustand wie snapshot()", _same13)

# --- Und derselbe Vertrag eine Etage tiefer: der Warte-Kasten ---
# Die Seite liest `w.<feld>` aus einem Dict, das die Laufzeit schreibt. Ein Feld
# umbenannt und niemand merkt es: JavaScript wirft bei `undefined` nicht, es
# zeigt einfach nichts an - "wartet auf die Farbe bei (undefined)" statt eines
# Fehlers. Deshalb werden hier die Namen gegeneinander gehalten.
from autoclicker.runtime.steps import _color_wait_status as _fws13

class _CfgW13:
    pixel_wait_tolerance = 30
    pixel_timeout_action = "stop"

class _StW13:
    config = _CfgW13()

_wc13 = _WCx(pixel=(4, 5), color=(1, 2, 3))
_color_fields13 = set(_fws13(_StW13(), _SS(delay_before=0), _wc13, (9, 9, 9), 4.0, 100.0, 30.0))
# Der Zeit-Zweig hat keine eigene Funktion - er steht als Dict-Literal in der
# Schleife, also wird er dort gelesen.
import autoclicker.runtime.actions as _act13
_time_source13 = _inspect13.getsource(_act13._wait_loop)
_time_fields13 = set(_re13.findall(r'"(\w+)":', _time_source13))
# Der Live-Pixel beim Zeitwarten kommt aus `_live_point` — mit DENSELBEN
# Namen wie beim Farb-Warten, denn die Seite zeichnet beide mit einer Funktion.
_live_fields13 = set(_re13.findall(r'"(\w+)":', _inspect13.getsource(_act13._live_point)))
check("der Live-Pixel beim Zeitwarten benutzt die Namen des Farb-Wartens",
      len(_live_fields13) >= 5 and _live_fields13 <= _color_fields13)
_time_fields13 |= _live_fields13


def _js_function13(name):
    """Quelltext einer Funktion aus app.js — bis zur nächsten."""
    part = _html13[_html13.index("function " + name + "("):]
    return part[:part.index("\nfunction ", 1)]


# `livePixelBox` gehört dazu: sie liest dasselbe `w`, nur eine Funktion tiefer.
_box13 = _js_function13("waitBox") + _js_function13("livePixelBox")
_read13 = set(_re13.findall(r"\bw\.([a-z_]+)", _box13))
check("der Warte-Kasten liest ueberhaupt Felder", len(_read13) >= 6)
_unknown13 = sorted(_read13 - _color_fields13 - _time_fields13)
check("und jedes davon schreibt die Laufzeit auch", _unknown13 == [])
if _unknown13:
    print("        liest, was niemand schreibt: " + ", ".join(_unknown13))

# --- Eine neue Sequenz landet nie auf einer vorhandenen Datei ---
# Der Name IN der Datei ist nicht der Dateiname: 'all dayli' liegt in
# all_dayli.json. Wer den Dateinamen uebergibt, traf keine Sequenz und bekam eine
# LEERE mit genau diesem Dateipfad - ein Druck auf 'Speichern' und die 50
# Schritte waren weg. Das ist der teuerste Fehler, den ein Editor machen kann.
_st_tmp = tempfile.mkdtemp()
_st_cwd = _os.getcwd()
_os.chdir(_st_tmp)
try:
    from autoclicker.sequence_studio import _resolve_sequence as _rs14
    Path("sequences").mkdir()
    _all14 = Path("sequences") / "all_dayli" / "sequence.json"
    _all14.parent.mkdir(parents=True)
    _all14.write_text(json.dumps({
        "name": "all dayli", "schema_version": 4, "total_cycles": 1,
        "init_steps": [], "end_steps": [],
        "loop_phases": [{"name": "L", "repeat": 1, "steps": [
            {"x": 1, "y": 2, "delay_before": 0, "name": "wichtig"}]}]}),
        encoding="utf-8")

    def _steps14(seq):
        """Schritte der ersten Loop-Phase - 0, wenn es gar keine gibt.

        Ohne diesen Umweg reisst eine leer zurueckgegebene Sequenz die Suite mit
        einem IndexError ab, statt eine Zeile FAIL zu melden.
        """
        return len(seq.loop_phases[0].steps) if seq.loop_phases else 0

    _seq14, _path14 = _rs14("all dayli")            # ueber den Namen
    check("der Name in der Datei findet die Sequenz", _steps14(_seq14) == 1)

    _seq14b, _path14b = _rs14("all_dayli")          # ueber den Dateinamen
    check("der Dateiname findet sie auch",
          _steps14(_seq14b) == 1 and _path14b == _path14)

    # --- Ohne Namen: die zuletzt bearbeitete Sequenz, kein leeres Fenster ---
    # Das Studio startet ohne Namen, wenn im Hauptprozess keine Sequenz aktiv ist
    # oder wenn man es direkt aufruft. Ein leeres Fenster ist da fast nie gemeint.
    from autoclicker.sequence_studio import (
        remember_last_used as _mz14,
        last_edited as _zb14,
    )
    _old14 = Path("sequences") / "aelter" / "sequence.json"
    _old14.parent.mkdir(parents=True)
    _old14.write_text(json.dumps({
        "name": "aelter", "schema_version": 4, "total_cycles": 1,
        "init_steps": [], "end_steps": [], "loop_phases": []}), encoding="utf-8")
    # Zeitstempel von Hand setzen - sonst haengt der Test an der Aufloesung der Uhr.
    # Moderne Werte statt Sekunden kurz nach 1970: NTFS und POSIX-Dateisysteme
    # behandeln sehr alte Zeitstempel nicht identisch. Der grosse Abstand hält
    # den Test weiterhin unabhängig von der Zeitauflösung des Dateisystems.
    _time14 = 1_700_000_000
    _os.utime(_old14, (_time14, _time14))
    _os.utime(_all14, (_time14 + 100, _time14 + 100))
    check("die zuletzt geaenderte Datei wird gefunden",
          _zb14() == _all14)

    _seq14d, _path14d = _rs14("")
    check("ohne Namen kommt genau die",
          _path14d == _all14
          and _steps14(_seq14d) == 1)

    check("eine geöffnete Sequenz wird gemerkt", _mz14(_old14))
    _seq14open, _path14open = _rs14("")
    check("zuletzt geöffnet schlägt die ältere Dateizeit",
          _path14open == _old14)

    # Speichert danach ein anderer Programmteil eine Sequenz, ist dieses Ereignis
    # neuer als das Öffnen und muss wieder gewinnen.
    _marker14 = Path(".studio-sequence.json")
    _after_marker14 = _marker14.stat().st_mtime_ns + 1_000_000_000
    _os.utime(_all14, ns=(_after_marker14, _after_marker14))
    _seq14e, _path14e = _rs14("")
    check("eine danach gespeicherte Sequenz gewinnt wieder",
          _path14e == _all14)

    # Kaputte Datei: nicht ladbar heisst nicht ueberschreibbar.
    _broken14 = Path("sequences") / "kaputt" / "sequence.json"
    _broken14.parent.mkdir(parents=True)
    _broken14.write_text("{kein json", encoding="utf-8")
    _os.utime(_broken14, (_time14 - 100, _time14 - 100))
    _seq14c, _path14c = _rs14("kaputt")
    check("eine unlesbare Datei wird nicht als Ziel uebernommen",
          _path14c != _broken14 and _seq14c.loop_phases == [])
finally:
    _os.chdir(_st_cwd)


# --------------------- Sequenz-Studio: Uebersicht und Live-Run (die zwei Fragen)
section("Sequenz-Studio: Uebersicht und Laufstatus")

# Beide Methoden sind der zweite Kanal: sie geben KEINE Momentaufnahme zurueck,
# sondern einen eigenen Gegenstand. Die Seite holt sie deshalb ueber `ask()` -
# ueber `call()` landete die Antwort in `S`, und ein Blick in die Uebersicht waere
# ein Datenverlust im Editor.
import threading as _thr16, time as _time16
from autoclicker.editors.sequence_studio.bridge import scan_warnings as _sw16
from autoclicker.editors.sequence_studio.model import sequence_to_board as _s2b16

_st16 = tempfile.mkdtemp()
_cwd16 = _os.getcwd()
_os.chdir(_st16)
try:
    Path("sequences").mkdir()

    def _write16(file, data):
        target = Path("sequences") / Path(file).stem / "sequence.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data), encoding="utf-8")

    _write16("gross.json", {
        "name": "gross", "schema_version": 4, "total_cycles": 3,
        "description": "zwei Phasen", "init_steps": [{"x": 1, "y": 1, "delay_before": 0}],
        "end_steps": [], "loop_phases": [
            {"name": "A", "repeat": 5, "steps": [{"x": 1, "y": 1, "delay_before": 0},
                                                 {"x": 2, "y": 2, "delay_before": 0}]},
            {"name": "B", "repeat": 1, "scheduled_start": "08:30",
             "steps": [{"item_scan": "", "delay_before": 0}]}]})
    _write16("klein.json", {
        "name": "klein", "schema_version": 4, "total_cycles": 0,
        "init_steps": [], "end_steps": [], "loop_phases": []})
    _broken16 = Path("sequences") / "kaputt" / "sequence.json"
    _broken16.parent.mkdir(parents=True)
    _broken16.write_text("{kein json", encoding="utf-8")

    _b16 = _SB8(_SEQ8(name="gross"),
                Path("sequences") / "gross" / "sequence.json", "sequences")
    _list16 = _b16.sequence_list()
    _after16 = {e["name"]: e for e in _list16}

    check("die Uebersicht findet jede Datei", len(_list16) == 3)
    check("auch die kaputte - als kaputt, nicht als fehlend",
          any(e.get("broken") for e in _list16))
    check("die Kennzahlen stimmen mit der Datei ueberein",
          _after16["gross"]["steps"] == 4 and _after16["gross"]["init"] == 1
          and len(_after16["gross"]["phases"]) == 2)
    check("Wiederholungen und Startzeit stehen an der Phase",
          _after16["gross"]["phases"][0]["repeat"] == 5
          and _after16["gross"]["phases"][1]["start"] == "08:30")
    check("die offene Sequenz ist als offen markiert",
          _after16["gross"]["open"] is True and _after16["klein"]["open"] is False)
    # Der Scan ohne Konfiguration ist die eine Warnung, die man in der Uebersicht
    # sehen will - sonst sucht man den Block hinterher in vier Phasen.
    check("ein Scan ohne Konfiguration wird gemeldet",
          len(_after16["gross"]["warnings"]) == 1
          and "ITEM-SCAN" in _after16["gross"]["warnings"][0])
    check("und eine saubere Sequenz meldet nichts", _after16["klein"]["warnings"] == [])
    check("eine kaputte Datei bringt die Uebersicht nicht um",
          Path(_after16["kaputt"]["file"]) == _broken16)

    # Gegenprobe zur Wiederverwendung: Speichern und Uebersicht duerfen nicht zwei
    # getrennte Regeln haben. Beide fragen scan_warnings() - der Test misst das,
    # indem er beide Seiten befragt und vergleicht.
    _b16b = _SB8(_SEQ8(name="gross"),
                 Path("sequences") / "gross" / "sequence.json", "sequences")
    _b16b.load({"name": "gross"})
    check("Laden merkt die zuletzt verwendete Sequenz",
          json.loads(Path(".studio-sequence.json").read_text(encoding="utf-8"))["folder"]
          == "gross")
    check("Speichern und Uebersicht benutzen dieselbe Regel",
          _b16b._scan_without_name() == _after16["gross"]["warnings"][0])
    check("und ohne leeren Scan sagen beide nichts",
          _sw16(_s2b16(_SEQ8(name="x"))) == [] and _b16._scan_without_name() is None)

    # --- Laufstatus: nichts laeuft ist der Normalfall, kein Fehler ---
    from autoclicker.config import RUN_STATUS_FILE as _rsf16
    check("ohne Statusdatei laeuft nichts", _b16.run_status() == {"active": False})

    Path(_rsf16).write_text("{kaputt", encoding="utf-8")
    check("eine unlesbare Statusdatei ist auch nur 'nichts laeuft'",
          _b16.run_status() == {"active": False})

    Path(_rsf16).write_text(json.dumps(
        {"active": True, "sequence": "S", "stamp": _time16.time()}), encoding="utf-8")
    check("ein frischer Stand kommt durch", _b16.run_status()["sequence"] == "S")

    # Aelter als 5 s heisst: der Schreiber lebt nicht mehr. Ein hart abgeschossener
    # Hauptprozess soll nicht ewig als "laeuft" in der Oberflaeche stehen.
    Path(_rsf16).write_text(json.dumps(
        {"active": True, "sequence": "S", "stamp": _time16.time() - 60}), encoding="utf-8")
    _orphaned16 = _b16.run_status()
    check("ein alter Stand gilt als verwaist",
          _orphaned16 == {"active": False, "orphaned": True})

    # --- Die Phasen-Uebersicht: alle Phasen, nicht nur die laufende ---
    # Die Liste steht im Laufstatus, weil die Ansicht sie sonst aus der GEOEFFNETEN
    # Sequenz holen muesste - laufen kann eine ganz andere.
    from autoclicker.runtime.worker import (_phase_overview as _pu16,
                                            _phase_pos as _pp16)
    _seq16 = _SEQ8(name="P",
                   init_steps=[_SS(x=1, y=1, delay_before=0)],
                   loop_phases=[_LP8(name="Farmen", repeat=25, steps=[
                                    _SS(x=1, y=1, delay_before=0)]),
                                _LP8(name="Verkaufen", repeat=1, scheduled_start="07:00",
                                     steps=[_SS(x=2, y=2, delay_before=0)])],
                   end_steps=[_SS(x=9, y=9, delay_before=0)])
    _list16 = _pu16(_seq16)
    check("die Uebersicht nennt jede Phase",
          [p["name"] for p in _list16] == ["INIT", "Farmen", "Verkaufen", "END"])
    check("und ihre Art", [p["kind"] for p in _list16]
          == ["init", "loop", "loop", "end"])
    check("eine zeitgesteuerte Phase bringt ihre Uhrzeit mit",
          _list16[2]["start"] == "07:00" and _list16[1]["start"] == "")

    # Die Positionsrechnung MUSS zur Liste passen: ein fehlender Versatz markiert
    # die falsche Kachel als laufend, und das faellt in der Ansicht niemandem auf.
    check("die Position der INIT-Phase zeigt auf INIT",
          _list16[_pp16(_seq16, "init")]["name"] == "INIT")
    check("die Positionen der Loop-Phasen zeigen auf sie selbst",
          all(_list16[_pp16(_seq16, "loop", i)]["name"] == lp.name
              for i, lp in enumerate(_seq16.loop_phases)))
    check("die Position der END-Phase zeigt auf END",
          _list16[_pp16(_seq16, "end")]["name"] == "END")

    # Ohne INIT verschiebt sich alles um eins - genau der Versatz, den die
    # Rechnung traegt.
    _without16 = _SEQ8(name="O", loop_phases=[_LP8(name="L", repeat=1, steps=[
        _SS(x=1, y=1, delay_before=0)])], end_steps=[_SS(x=2, y=2, delay_before=0)])
    _list_o16 = _pu16(_without16)
    check("ohne INIT faengt die Loop-Phase bei 0 an",
          _list_o16[_pp16(_without16, "loop", 0)]["name"] == "L"
          and _list_o16[_pp16(_without16, "end")]["name"] == "END")

    # --- "Stelle zeigen" gibt es fuer jede Stelle des Blocks ---
    # Klick, Pruef-Pixel und ELSE-Klick sind drei verschiedene Orte; die Frage
    # "sitzt das noch?" stellt sich bei allen.
    from autoclicker import mailbox as _bf19
    _b20 = _SB8(_SEQ8(name="Z", loop_phases=[_LP8(name="L", repeat=1, steps=[
        _SS(x=1, y=1, delay_before=0, point_id=1,
            wait_condition=_WCx(point_id=2, pixel=(2, 2), color=(1, 2, 3)),
            else_config=_ECx(action="click", point_id=3))])]),
        Path("sequences") / "z.json", "sequences")
    _b20.points = [_PP8(id=1, x=11, y=11, name="A", color=None),
                   _PP8(id=2, x=22, y=22, name="B", color=None),
                   _PP8(id=3, x=33, y=33, name="C", color=None)]
    _lane20 = next(i for i, ln in enumerate(_b20.board.lanes) if ln.steps)
    _b20.select({"phase": _lane20, "row": 0})
    for _which20, _expected20 in (("click", 11), ("trigger", 22), ("else", 33)):
        _bf19.discard_command()
        _b20.point_show({"which": _which20})
        _job20 = _bf19.fetch_command()
        check(f"'{_which20}' zeigt auf die richtige Stelle",
              (_job20 or {}).get("arguments", {}).get("x") == _expected20)
    _bf19.discard_command()

    # --- Stelle mit der Maus setzen ---
    # Die Windows-Teile (wait_for_global_key, get_cursor_pos, get_screen_pixel) sind
    # hier gestubbt; geprueft wird, was die Bruecke daraus macht.
    import autoclicker.utils.io as _io18
    import autoclicker.winapi as _wa18
    _b19 = _SB8(_SEQ8(name="M", loop_phases=[_LP8(name="L", repeat=1, steps=[
        _SS(x=0, y=0, delay_before=0)])]), Path("sequences") / "m.json", "sequences")
    _lane19 = next(i for i, ln in enumerate(_b19.board.lanes) if ln.steps)
    _b19.select({"phase": _lane19, "row": 0})
    _step19 = _b19.board.lanes[_lane19].steps[0]
    _old19 = (_io18.wait_for_global_key, _wa18.get_cursor_pos, _wa18.get_screen_pixel)
    try:
        _io18.wait_for_global_key = lambda keys_list, timeout=0: "enter"
        _wa18.get_cursor_pos = lambda: (640, 480)
        _wa18.get_screen_pixel = lambda x, y: (10, 20, 30)
        _z19 = _b19.point_capture()
        check("ohne Punkt entsteht einer an der Mausposition",
              _step19.point_id is not None and (_step19.x, _step19.y) == (640, 480))
        check("die Farbe wird dabei gemessen",
              _b19._point(_step19.point_id).color == (10, 20, 30))
        check("und die Meldung nennt beides",
              "640" in _z19["status"]["text"] and "10" in _z19["status"]["text"])

        # Ein zweiter Aufruf VERSCHIEBT den vorhandenen Punkt, statt einen
        # zweiten anzulegen - dieselbe Regel wie beim Tippen der Zahlen.
        _wa18.get_cursor_pos = lambda: (700, 500)
        _before19 = len(_b19.points)
        _b19.point_capture()
        check("ein zweiter Aufruf verschiebt statt anzulegen",
              len(_b19.points) == _before19 and (_step19.x, _step19.y) == (700, 500))

        # ESC laesst alles, wie es war.
        _io18.wait_for_global_key = lambda keys_list, timeout=0: "escape"
        _z19 = _b19.point_capture()
        check("ESC aendert nichts", (_step19.x, _step19.y) == (700, 500)
              and _z19["status"]["kind"] == "warn")
    finally:
        _io18.wait_for_global_key, _wa18.get_cursor_pos, _wa18.get_screen_pixel = _old19

    # --- Zwei Prozesse, eine Datei: der Zweite darf nicht kommentarlos gewinnen ---
    # Studio und Hauptprozess teilen sich den Ordner. Eine Aufnahme legt Punkte
    # an, `save_data()` schreibt die Sequenz - ohne diese Frage ist die Arbeit
    # des Ersten weg, ohne ein Wort.
    _b18 = _SB8(_SEQ8(name="W", loop_phases=[_LP8(name="L", repeat=1, steps=[
        _SS(x=1, y=2, delay_before=0, point_id=1)])]),
        Path("sequences") / "w" / "sequence.json", "sequences")
    _b18.points = [_PP8(id=1, x=1, y=2, name="P", color=None)]
    _z18 = _b18.save()
    check("das erste Speichern geht ohne Rueckfrage",
          _z18["question"] is None and Path("sequences/w/sequence.json").exists())

    # Jetzt schreibt "der Hauptprozess" dazwischen.
    _time16.sleep(0.01)
    Path("sequences/w/sequence.json").write_text(
        '{"name": "fremd"}', encoding="utf-8")
    _z18 = _b18.save()
    check("eine fremde Aenderung fuehrt zur Rueckfrage",
          (_z18["question"] or {}).get("kind") == "save")
    check("und die Datei ist unangetastet",
          "fremd" in Path("sequences/w/sequence.json").read_text(encoding="utf-8"))
    check("die Frage nennt die Datei",
          "sequence.json" in (_z18["question"] or {}).get("text", ""))

    _z18 = _b18.save({"force": True})
    check("mit Erzwingen wird geschrieben",
          _z18["question"] is None and "foreign" not in
          Path("sequences/w/sequence.json").read_text(encoding="utf-8"))
    _z18 = _b18.save()
    check("danach ist der Stand wieder aktuell - keine zweite Rueckfrage",
          _z18["question"] is None)

    # **Und ein Start bei offener Rueckfrage startet NICHT.** `run_command`
    # speicherte vor dem Start und prueft danach `kind == "err"` — die
    # Rueckfrage ist aber kein Fehler: der Start lief los, mit der Datei von
    # der Platte (der fremden Fassung), die eigenen Aenderungen blieben
    # ungespeichert, und weil `snapshot()` die Frage verbraucht hatte, sah die
    # Seite den Dialog nie. „'W' gestartet." stand ueber einem Lauf, der etwas
    # anderes tat als das Angezeigte.
    from autoclicker.mailbox import COMMAND_PATH as _CP18
    _b18.sequence_set({"field": "description", "value": "im Studio"})
    _time16.sleep(0.01)
    Path("sequences/w/sequence.json").write_text(
        '{"name": "W", "description": "fremd"}', encoding="utf-8")
    try:
        _CP18.unlink()
    except OSError:
        pass
    _z18 = _b18.run_command({"command": "start"})
    check("bei einer fremden Aenderung faellt der Start aus und die Frage kommt an",
          (_z18["question"] or {}).get("kind") == "save"
          and not _CP18.exists() and _b18._dirty)
    check("die Datei traegt weiter die fremde Fassung",
          "fremd" in Path("sequences/w/sequence.json").read_text(encoding="utf-8"))
    _b18.save({"force": True})
    _z18 = _b18.run_command({"command": "start"})
    check("nach dem Erzwingen startet er — mit der gespeicherten Fassung",
          _CP18.exists() and not _b18._dirty
          and "im Studio" in Path("sequences/w/sequence.json").read_text(encoding="utf-8"))
    try:
        _CP18.unlink()
    except OSError:
        pass

    check("es gibt keine zweite Punkt-Datei mit eigenem Konfliktstand",
          not Path("sequences/points.json").exists())

    # --- Der laufende Block traegt dieselbe Farbe wie seine Karte im Board ---
    # Die Farbe IST die Legende: waere sie in der Live-Ansicht eine andere,
    # muesste man beim Blick dorthin raten, welcher der neun Typen laeuft. Die
    # Laufzeit schreibt nur den Schluessel (sie darf die Ansicht nicht kennen),
    # uebersetzt wird in der Bruecke - dieser Test haelt beide Seiten gegeneinander.
    Path(_rsf16).write_text(json.dumps(
        {"active": True, "sequence": "S", "stamp": _time16.time(),
         "block_set_type": "boss_scan"}), encoding="utf-8")
    _running16 = _b16.run_status()
    _b16c = _SB8(_SEQ8(name="F", loop_phases=[_LP8(name="L", repeat=1, steps=[
        _SS(delay_before=0, boss_scan="drache")])]), Path("sequences/F.json"), "sequences")
    _card16 = [b for p in _b16c.snapshot()["phases"] for b in p["blocks"]][0]
    check("die Live-Ansicht faerbt wie das Board",
          _running16.get("block_color") == _card16["color"] is not None)
    check("und traegt dieselbe Marke",
          _running16.get("block_badge") == _card16["label"] == "BOSS-SCAN")

    # Ohne Typ wird keine Farbe erfunden - eine Statusdatei aus einer aelteren
    # Fassung hat das Feld nicht.
    Path(_rsf16).write_text(json.dumps(
        {"active": True, "sequence": "S", "stamp": _time16.time()}), encoding="utf-8")
    check("ohne Typ bleibt die Kopfzeile neutral",
          "block_color" not in _b16.run_status())

    # Und die Klassifikation ist EINE: die Laufzeit schreibt genau den Schluessel,
    # den das Studio faerbt. Zwei Kopien der Regel waeren zwei Stellen, an denen
    # ein neuer Block-Typ vergessen werden kann.
    from autoclicker.models import block_type as _bt16
    from autoclicker.editors.sequence_studio.model import BLOCK_COLORS as _bc16
    check("jeder Typ, den block_type liefert, hat eine Farbe",
          all(_bt16(s) in _bc16 for s in [
              _SS(delay_before=0, boss_scan="x"), _SS(delay_before=0, boss_watcher="x"),
              _SS(delay_before=0, icon_scan="x"), _SS(delay_before=0, item_scan="x"),
              _SS(delay_before=0, key_press="a"), _SS(delay_before=0, wait_only=True),
              _SS(delay_before=0, screenshot_only=True), _SS(x=1, y=2, delay_before=0),
              _SS(x=1, y=2, delay_before=0, wait_condition=_WCx(pixel=(1, 2), color=(3, 4, 5)))]))

    # --- Die Statusdatei darf NIE als Sequenz durchgehen ---
    # `Path.glob("*.json")` erfasst auch Dateien mit fuehrendem Punkt. Laege der
    # Laufstatus in sequences/, stuende er im Studio-Menue, im Konsolen-Menue und
    # in der Start-Migration - und weil er sich sekuendlich aendert, gewaenne er
    # jedes Mal last_edited(). Dieselbe Falle wie bei den .bak-Sicherungen.
    from autoclicker.persistence import list_available_sequences as _las16
    check("der Laufstatus liegt nicht im Sequenz-Ordner",
          Path(_rsf16).parent != Path("sequences"))
    (Path("sequences") / ".probe.json").write_text("{}", encoding="utf-8")
    check("einzelne JSON-Dateien im Wurzelordner werden nicht als Sequenz gelistet",
          not any(p.name == ".probe.json" for _, p in _las16()))
    (Path("sequences") / ".probe.json").unlink()

    # --- Der Schreiber: zwei Quellen, ein Zustand ---
    # Der Worker weiss die Phase, execute_step weiss den Block. Keiner kennt das
    # Ganze - deshalb fuehrt write_status() seinen Teil ein, statt ihn zu ersetzen.
    from autoclicker.runtime import status as _stat16

    class _FakeState16:
        lock = _thr16.Lock()
        total_clicks, items_found, key_presses = 7, 2, 1
        timeouts, skipped_cycles, restarts = 0, 0, 0

    _fs16 = _FakeState16()
    _stat16.finish_run()
    _stat16.write_status(_fs16, {"active": True, "sequence": "S", "phase": "A"}, immediately=True)
    _stat16.write_status(_fs16, {"block": 3, "blocks": 9}, immediately=True)
    # .get() statt [] ueberall hier unten: faellt der Merge weg, fehlt der
    # Schluessel ganz - und ein KeyError risse die restliche Suite mit, statt
    # eine Zeile FAIL zu melden. Genau der Fall, den dieser Test faengt.
    def _run16() -> dict:
        return json.loads(Path(_rsf16).read_text(encoding="utf-8"))

    _read16 = _run16()
    check("der zweite Schreiber loescht den ersten nicht",
          _read16.get("phase") == "A" and _read16.get("block") == 3)
    check("die Zaehler kommen aus dem State",
          _read16.get("counters", {}).get("clicks") == 7)

    # Die Drossel wirft den SCHREIBVORGANG weg, nicht die Information: sonst zeigte
    # der naechste Schreibvorgang einen Block, der laengst durch ist.
    _stat16.write_status(_fs16, {"block": 4})
    check("ein gedrosselter Aufruf schreibt nicht", _run16().get("block") == 3)
    _stat16.write_status(_fs16, {}, immediately=True)
    check("aber seine Information ist nicht verloren", _run16().get("block") == 4)

    # Ein wartender Lauf ist kein toter Lauf: das Lebenszeichen haelt `stamp`
    # frisch, ohne etwas zu aendern. Ohne das saehe ein Schritt, der auf eine Farbe
    # wartet, nach 5 s verwaist aus - der Fall, fuer den man die Ansicht aufmacht.
    _old16 = _run16().get("stamp", 0)
    _time16.sleep(0.25)
    _stat16.heartbeat(_fs16)
    _new16 = _run16()
    check("ein Lebenszeichen schiebt den Zeitstempel vor",
          _new16.get("stamp", 0) > _old16)
    check("und aendert sonst nichts", _new16.get("block") == 4)

    # Gegenprobe zum Lebenszeichen: der Aufruf muss auch DORT stehen, wo der
    # Worker lange haengt. Ein Lebenszeichen, das nur in status.py existiert und
    # von keiner Schleife gerufen wird, laesst genau den wartenden Lauf nach 5 s
    # als verwaist erscheinen - und wartende Laeufe sind der Grund fuer die
    # Ansicht. Geprueft wird der Quelltext der Funktionen, nicht ihr Ablauf:
    # ausfuehren liesse sich keine von ihnen ohne echtes Windows.
    import inspect as _insp16
    import autoclicker.runtime.actions as _act16
    import autoclicker.runtime.steps as _stp16

    # Die Rueckgratliste sind die SCHLEIFENRUEMPFE, nicht ihre Huellen: zwei der
    # drei liegen seit dem Warte-Kasten in einer eigenen Funktion, damit das
    # Abmelden in ein `finally` passt. Gegen die Huelle geprueft waere der Test
    # gruen geblieben, obwohl die Schleife selbst stumm ist.
    _loops16 = [
        ("_wait_loop", _act16._wait_loop),
        ("_color_loop", _stp16._color_loop),
        ("_execute_boss_watcher_step", _stp16._execute_boss_watcher_step),
    ]
    # Auf den AUFRUF pruefen, nicht auf das Wort: der Kommentar ueber jeder
    # Fundstelle nennt `status.heartbeat()` ebenfalls, und gegen das Wort
    # geprueft blieb der Test gruen, nachdem der Aufruf darunter entfernt war.
    # `waiting_for()` zaehlt mit: es schreibt ueber dieselbe Funktion und schiebt
    # `stamp` genauso vor - wer es ruft, braucht daneben kein Lebenszeichen.
    _silent16 = [n for n, f in _loops16
                if "status.heartbeat(state)" not in _insp16.getsource(f)
                and "status.waiting_for(state, " not in _insp16.getsource(f)]
    check("jede lange Warteschleife gibt ein Lebenszeichen", _silent16 == [])
    if _silent16:
        print("        ohne Lebenszeichen: " + ", ".join(_silent16))

    # --- Der Warte-Kasten: worauf der Block gerade wartet ---
    # "seit 12 s" allein beantwortet die Frage nicht: bei 15 s Wartezeit sind
    # zwoelf Sekunden fast geschafft, bei 300 s Timeout gerade erst angefangen.
    _stat16.write_status(_fs16, {"block": 5}, immediately=True)
    _time16.sleep(0.25)     # Setzen ist gedrosselt wie jeder andere Schreibvorgang
    _stat16.waiting_for(_fs16, {"kind": "time", "text": "Vor Klick", "since": 1.0,
                           "until": 7.0, "total": 6.0})
    check("der Warte-Teil kommt in die Datei",
          _run16().get("waiting", {}).get("kind") == "time")
    check("und laesst den Rest des Zustands stehen", _run16().get("block") == 5)
    # Das Abmelden umgeht die Drossel: zwischen "Farbe erkannt" und dem naechsten
    # Block liegt noch die eigene Aktion des Schritts - solange stuende in der
    # Ansicht "wartet auf Farbe", obwohl laengst geklickt wurde.
    _stat16.waiting_for(_fs16, None)
    check("das Abmelden wird nicht gedrosselt", _run16().get("waiting") is None)

    # Jede Warteschleife meldet sich selbst wieder ab - auf JEDEM Ausgang, sonst
    # laeuft die Restzeit in der Ansicht ins Negative. Deshalb `finally`.
    _without_signoff16 = [n for n, f in [("wait_with_pause_skip", _act16.wait_with_pause_skip),
                                        ("_execute_wait_for_color", _stp16._execute_wait_for_color)]
                         if "finally:" not in _insp16.getsource(f)
                         or "status.waiting_for(state, None)" not in _insp16.getsource(f)]
    check("jede Warteschleife meldet sich wieder ab", _without_signoff16 == [])
    # Und der Blockwechsel raeumt zusaetzlich ab: der neue Block wartet noch auf
    # nichts, der Kasten des vorherigen darf nicht darueber stehenbleiben.
    # `execute_step` ist seit dem Block-Skip-Fix nur noch die Huelle; der
    # Rumpf mit dem Laufstatus-Schreiber heisst `_dispatch_step`.
    check("der Blockwechsel raeumt den Warte-Kasten ab",
          '"waiting": None' in _insp16.getsource(_stp16._dispatch_step))

    # Was nach dem Timeout kommt, gehoert neben den Countdown: dass in 8 s
    # Schluss ist, hilft nur mit der Antwort, ob dann uebersprungen oder
    # gestoppt wird. Dieselbe Kette wie _handle_color_wait_timeout.
    from autoclicker.models import ElseConfig as _EC16, ACTION_TEXT as _AT16
    from autoclicker.models import TIMEOUT_TEXT as _TT16
    from autoclicker.models import VALID_ELSE_ACTIONS as _VEA16

    class _CfgFake16:
        pixel_timeout_action = "stop"

    class _StFake16:
        config = _CfgFake16()

    _st16 = _StFake16()
    _step16 = SequenceStep(x=1, y=2)
    check("ohne else nennt der Status die globale Timeout-Aktion",
          _stp16._timeout_consequence(_st16, _step16) == "Sequenz stoppen")
    _st16.config.pixel_timeout_action = "skip_cycle"
    check("...und folgt ihr, wenn sie sich aendert",
          _stp16._timeout_consequence(_st16, _step16) == "Zyklus abbrechen, nächster Zyklus")
    _step16.else_config = _EC16(action="skip")
    check("mit else gewinnt else", _stp16._timeout_consequence(_st16, _step16)
          == "ELSE: Schritt überspringen")
    # Die Texttabelle liegt in models.py, weil zwei Anzeigen sie brauchen, die
    # sich nicht kennen duerfen. Ein neuer Aktionstyp ohne Text stuende in beiden
    # als rohes "skip_cycle" da.
    check("jede else-Aktion hat einen Text", all(a in _AT16 for a in _VEA16))

    # --- Und dasselbe im Editor: was passiert OHNE else? ---
    # Der Hinweis im Inspektor behauptete "die Sequenz macht weiter". Die
    # Voreinstellung bricht aber den ganzen Zyklus ab - der Unterschied
    # entscheidet, ob man ELSE ueberhaupt braucht. Das Studio liest die Antwort
    # deshalb aus der Config statt sie zu behaupten.
    from autoclicker.config import load_config as _lc16
    _cfg16 = _lc16()
    _oe16 = _b16._without_else()
    check("das Studio nennt den Timeout aus der Config",
          _oe16.get("seconds") == _cfg16.pixel_wait_timeout)

    class _StCfg16:
        config = _cfg16

    # Der eigentliche Vertrag: Editor und Laufzeit muessen dieselbe Folge nennen.
    # Zwei Uebersetzungen desselben Config-Werts waeren zwei Stellen, an denen
    # eine neue Timeout-Aktion vergessen werden kann - und die eine davon sagte
    # dem Nutzer dann etwas anderes, als die Sequenz spaeter tut.
    check("Editor und Laufzeit nennen dieselbe Folge",
          _oe16.get("consequence") == _stp16._timeout_consequence(_StCfg16(), SequenceStep(x=1, y=2)))
    check("jede Timeout-Aktion hat einen Text",
          all(a in _TT16 for a in ("skip_cycle", "restart", "stop")))

    # --- Wo ELSE ueberhaupt feuern kann ---
    # ELSE ist die Antwort auf eine NICHT ERFUELLTE Bedingung. Ein reiner Klick
    # hat keine: er klickt, und danach geht es weiter. Ein ELSE daran ist eine
    # Zusage, die nichts einloest - deshalb sagt es die Oberflaeche.
    from autoclicker.editors.sequence_studio.bridge import else_applies as _eg16
    _cases16 = {
        "Klick": (SequenceStep(x=1, y=2, delay_before=0), False),
        "Taste": (SequenceStep(delay_before=0, key_press="a"), False),
        "Warten": (SequenceStep(delay_before=5, wait_only=True), False),
        "Screenshot": (SequenceStep(delay_before=0, screenshot_only=True), False),
        # Der Watcher laeuft in seine eigenen Grenzen (max. Scans, Timeout) und
        # macht danach weiter, ohne ELSE zu fragen - siehe _execute_boss_watcher_step.
        "Boss-Watcher": (SequenceStep(delay_before=0, boss_watcher="w"), False),
        "Farb-Trigger": (SequenceStep(x=1, y=2, delay_before=0,
                                      wait_condition=_WCx(pixel=(1, 2), color=(3, 4, 5))), True),
        "Nachpruefung": (SequenceStep(x=1, y=2, delay_before=0,
                                      verify_condition=_WCx(pixel=(1, 2), color=(3, 4, 5))), True),
        "Item-Scan": (SequenceStep(delay_before=0, item_scan="s"), True),
        "Boss-Scan": (SequenceStep(delay_before=0, boss_scan="s"), True),
        "Icon-Scan": (SequenceStep(delay_before=0, icon_scan="s"), True),
    }
    # Die Ausloeser-Liste und die Scan-Felder des Editors sind zwei Listen ueber
    # dieselben Felder - laufen sie auseinander, warnt der Editor am falschen Block.
    from autoclicker.editors.sequence_studio.bridge import _ELSE_SCANS as _es16
    check("die ELSE-Ausloeser sind Scan-Felder, die der Editor kennt",
          set(_es16) < set(_sfeld12.values()))
    check("...und der Boss-Watcher ist bewusst NICHT dabei",
          "boss_watcher" in _sfeld12.values() and "boss_watcher" not in _es16)

    _wrong16 = [n for n, (s, target) in _cases16.items() if _eg16(s) is not target]
    check("die Oberflaeche weiss, wo ELSE feuern kann", _wrong16 == [])
    if _wrong16:
        print("        falsch beurteilt: " + ", ".join(_wrong16))

    # Gegenprobe an der Laufzeit: JEDE Stelle, die else ausloest, muss zu einem
    # Schritt gehoeren, den else_applies() als ausloesefaehig kennt. Geprueft am
    # Quelltext - die Handler selbst laufen nur mit echtem Windows.
    _source16 = _insp16.getsource(_stp16)
    _trigger16 = _source16.count("execute_else_action(state, step") + \
        _source16.count("_gate_after_else(state, step")
    check("der Test kennt alle Ausloeser-Stellen der Laufzeit", _trigger16 >= 8)

    # --- Faellt der Ausloeser weg, faellt das ELSE mit ---
    # Wer den Trigger wegnimmt, hat den einzigen Ausloeser entfernt. Das ELSE
    # stehenzulassen hiesse, es unsichtbar in der Datei zu behalten - der
    # Abschnitt faellt in der Oberflaeche ja mit dem Ausloeser weg.
    _b17 = _SB8(_SEQ8(name="E", loop_phases=[_LP8(name="L", repeat=1, steps=[
        SequenceStep(x=1, y=2, delay_before=0, point_id=1,
                     wait_condition=_WCx(point_id=1, pixel=(1, 2), color=(3, 4, 5)),
                     else_config=_EC16(action="skip"))])]),
        Path("sequences/E.json"), "sequences")
    _b17.points = [_PP8(id=1, x=1, y=2, name="P", color=(3, 4, 5))]
    # Die Lane mit dem Schritt suchen: sequence_to_board legt INIT und END mit an.
    _lane17 = next(i for i, ln in enumerate(_b17.board.lanes) if ln.steps)
    _b17.select({"phase": _lane17, "row": 0})
    _step17 = _b17.board.lanes[_lane17].steps[0]
    _z17 = _b17.block_set_type({"type": "click"})
    check("Typwechsel ohne Ausloeser raeumt das ELSE weg",
          _step17.else_config is None)
    check("und sagt es", "ELSE entfernt" in _z17["status"]["text"])
    # Zurueck: der Abschnitt ist wieder da, aber leer - frisch auswaehlbar.
    _b17.block_set_type({"type": "wait_click"})
    check("zurueckgestellt ist der Ausloeser wieder da",
          _step17.wait_condition is not None)
    check("...aber ohne ELSE", _b17._block_detail()["else_action"] == "")

    # Dasselbe ueber den Trigger-Schalter statt ueber den Typ.
    _b17.block_else({"action": "skip"})
    _b17.block_trigger({"choice": _TKEIN8})
    check("Trigger entfernen raeumt das ELSE ebenfalls weg",
          _step17.else_config is None)

    # Ein ELSE, das weiterhin ausgeloest werden kann, bleibt unangetastet -
    # sonst raeumte der Aufraeumer genau das weg, wofuer er da ist.
    _b17.block_trigger({"choice": _TDA8})
    _b17.block_else({"action": "restart"})
    _b17.block_set({"field": "name", "value": "neu"})
    check("ein wirksames ELSE bleibt", _step17.else_config is not None)

    # --- Am Ende bleibt die Zusammenfassung stehen ---
    # Hier wurde die Datei frueher geloescht, und die Live-Ansicht war genau in
    # dem Moment leer, in dem man sie ansieht: direkt nachdem etwas fertig
    # geworden ist.
    _stat16.write_status(_fs16, {"active": True, "sequence": "S", "phase": "A",
                             "phase_pos": 1, "block": 5, "waiting": {"kind": "time"}},
                     immediately=True)
    _stat16.finish_run(_fs16, "alle Zyklen durchgelaufen", 12, 90.5)
    _end16 = _run16()
    check("am Ende steht die Zusammenfassung da", Path(_rsf16).exists())
    check("sie ist nicht mehr aktiv", _end16.get("active") is False)
    check("nennt den Grund", _end16.get("reason") == "alle Zyklen durchgelaufen")
    check("die gelaufenen Zyklen und die Dauer",
          _end16.get("elapsed_cycles") == 12 and _end16.get("duration") == 90.5)
    check("die Zaehler", _end16.get("counters", {}).get("clicks") == 7)
    check("und die Sequenz", _end16.get("sequence") == "S")
    # Wo Schluss war, bleibt drin; was einen MOMENT beschreibt, nicht: ein
    # "wartet auf Farbe" in einer Zusammenfassung waere eine Behauptung ueber
    # etwas, das laengst vorbei ist.
    check("die Stelle bleibt erhalten", _end16.get("phase_pos") == 1)
    check("der laufende Block nicht", "block" not in _end16)
    check("und das Warten auch nicht", "waiting" not in _end16)

    # Der Leser darf sie NICHT als verwaist verwerfen - sie ist Vergangenheit,
    # sie DARF alt sein. Nur ein Lauf, der sich fuer aktiv haelt, hat ein Alter.
    _end16["stamp"] = _time16.time() - 600
    Path(_rsf16).write_text(json.dumps(_end16), encoding="utf-8")
    _read16 = _b16.run_status()
    check("eine alte Zusammenfassung bleibt lesbar",
          _read16.get("end") and _read16.get("reason"))
    Path(_rsf16).write_text(json.dumps({"active": True, "sequence": "S",
                                        "stamp": _time16.time() - 600}), encoding="utf-8")
    check("ein alter AKTIVER Lauf gilt weiter als verwaist",
          _b16.run_status().get("orphaned") is True)

    # Vergessen gehoert trotzdem dazu: der naechste Lauf ist eine andere Sequenz,
    # und ein stehengebliebener Block stuende sonst in seiner ersten Momentaufnahme.
    _stat16.write_status(_fs16, {"active": True}, immediately=True)
    check("und der naechste Lauf faengt bei null an", "block" not in _run16())

    # Ohne State (der Lauf lief gar nicht erst an) gibt es nichts zusammenzufassen.
    _stat16.finish_run()
    check("ein Lauf ohne Zahlen laesst nichts liegen", not Path(_rsf16).exists())
finally:
    _os.chdir(_cwd16)


# Die Scans-Sektionen des Studios stehen in `tests/contract/studio_scans.py` —
# ueber 1.200 Zeilen und in sich geschlossen, also das erste eigene Modul.


# --------------------------- Template-Maske: der Hintergrund zaehlt nicht mit
section("Template-Vergleich blendet den Hintergrund aus")

# Gemessen an einem echten Bestand: von 62x60 Pixeln eines Slots sind 10-40 % das
# Item, der Rest ist die immer gleiche Slot-Flaeche. Ein Vergleich ueber das ganze
# Rechteck stimmt damit hauptsaechlich darueber ab, dass beide denselben
# Hintergrund haben.
try:
    from PIL import Image as _PILm
    import autoclicker.imaging as _imgm
    _has_mask = _imgm.OPENCV_AVAILABLE and _imgm.NUMPY_AVAILABLE
except ImportError:
    _has_mask = False

if not _has_mask:
    print("  ----  uebersprungen (Pillow/OpenCV/NumPy fehlt)")
else:
    _HG_M = (30, 128, 108)

    def _slot_image(background, seed):
        """Ein Slot: Hintergrund + ein Symbol in der Mitte."""
        import random
        b = _PILm.new("RGB", (40, 40), background)
        r = random.Random(seed)
        for x in range(14, 26):
            for y in range(14, 26):
                b.putpixel((x, y), (r.randrange(120, 256), r.randrange(120, 256),
                                    r.randrange(120, 256)))
        return b

    _m = _imgm.with_background_mask(_slot_image(_HG_M, 1), _HG_M)
    check("die Maske steckt im Bild, nicht daneben", _m.mode == "RGBA")
    _alpha = list(_m.getchannel("A").getdata())
    _deckend = sum(1 for a in _alpha if a > 127)
    check(f"nur das Symbol ist deckend ({_deckend} von 1600 Pixeln)",
          _deckend == 144)
    check("und der Hintergrund durchsichtig",
          _alpha[0] == 0 and _alpha[-1] == 0)

    # **Die Kernfrage: dasselbe Item vor einem ANDEREN Hintergrund.**
    # Die Maske merkt sich Stellen, nicht Farben - also darf das Menue dahinter
    # eine voellig andere Farbe haben.
    import tempfile as _tfm, os as _osm
    _dirm = _tfm.mkdtemp(prefix="maske_")
    _oldm = _imgm.TEMPLATES_DIR
    _imgm.TEMPLATES_DIR = _dirm
    _imgm._template_cache.clear()
    try:
        _m.save(_osm.path.join(_dirm, "gelernt.png"))
        _equal = _imgm.match_template_in_image(_slot_image(_HG_M, 1), "gelernt.png", 0.8)
        check("im eigenen Slot wird es erkannt", _equal[0] and _equal[1] > 0.99)

        _other_menu = _slot_image((90, 40, 120), 1)      # violetter Hintergrund
        _foreign = _imgm.match_template_in_image(_other_menu, "gelernt.png", 0.8)
        check("und vor einem anders gefaerbten Menue genauso",
              _foreign[0] and _foreign[1] > 0.99)

        # Gegenprobe: ein ANDERES Symbol darf nicht passen, auch nicht auf
        # demselben Hintergrund - sonst haette die Maske nur alles durchgelassen.
        _other = _imgm.match_template_in_image(_slot_image(_HG_M, 2), "gelernt.png", 0.8)
        check("ein anderes Symbol passt nicht", not _other[0])

        # Ohne Maske (Template ohne Alpha) bleibt es beim alten Verhalten - und
        # genau dann zieht der Hintergrund die Uebereinstimmung hoch.
        # --- Marker sehen dieselbe Flaeche wie das Template ---
        # Der Hintergrund steckte als Marker in JEDEM Item: gemessen 19 von 19.
        # Ursache war nicht das Verfahren, sondern die Schwelle - der dunklere
        # Rand des Slots lag 44 entfernt, `scan_slot_color_distance` auf 25.
        from autoclicker.editors.item_editor.markers import (
            _collect_markers_silent as _cms_m)
        _with_margin = _PILm.new("RGB", (40, 40), _HG_M)
        for _x in range(40):                      # dunklerer Rand des Slots
            for _y in range(40):
                if _x < 2 or _y < 2 or _x > 37 or _y > 37:
                    _with_margin.putpixel((_x, _y), (20, 95, 80))
        for _x in range(16, 24):
            for _y in range(16, 24):
                _with_margin.putpixel((_x, _y), (210, 15, 150))
        # Die Schwelle explizit setzen: sonst misst der Test die config.json des
        # Benutzers statt der Regel - und beim naechsten Wechsel des Wertes faellt
        # er aus einem Grund um, der nichts mit dem Code zu tun hat.
        import autoclicker.config as _cfgm
        _old_limit = _cfgm.CONFIG.scan_slot_color_distance
        _cfgm.CONFIG.scan_slot_color_distance = _ACrev().scan_slot_color_distance
        _raw_markers = _cms_m(_with_margin, _HG_M)
        _mask_marker = _cms_m(_imgm.with_background_mask(_with_margin, _HG_M), _HG_M)
        check("der Slot-Rand ist keine Marker-Farbe mehr",
              (20, 95, 80) not in _mask_marker)
        check("die Item-Farbe schon", (210, 15, 150) in _mask_marker)
        check("und ueber die Maske kommt dasselbe heraus wie ueber die Farbregel",
              set(_mask_marker) == set(_raw_markers))
        _cfgm.CONFIG.scan_slot_color_distance = _old_limit

        _slot_image(_HG_M, 1).save(_osm.path.join(_dirm, "ohne.png"))
        _imgm._template_cache.clear()
        _without = _imgm.match_template_in_image(_slot_image((90, 40, 120), 1), "ohne.png", 0.8)
        check("ohne Maske stoert der fremde Hintergrund sehr wohl",
              _without[1] < _foreign[1])

        # --- Der Groessen-Konflikt wird EINMAL gemeldet, nicht pro Item ---
        # Wer zwei Inventare im Bestand hat, hat zwei Slot-Groessen; die
        # Erkennung prueft die Items des einen auch gegen die Slots des anderen
        # (genau dafuer ist "erkannt, aber nicht in diesem Scan" da). Pro Item
        # gewarnt sind das zwei Dutzend gleichlautende Zeilen - und damit ist die
        # Sperre so gut wie keine.
        import logging as _logm
        _seen_m = []

        class _Catchm(_logm.Handler):
            def emit(self, rate):
                _seen_m.append(rate.getMessage())

        _catchm = _Catchm()
        _imgm.logger.addHandler(_catchm)
        _imgm._reported_sizes.clear()
        try:
            _otherm = _PILm.new("RGB", (40, 37), _HG_M)      # 3 px flacher
            for _i_m in range(3):
                _slot_image(_HG_M, 10 + _i_m).save(
                    _osm.path.join(_dirm, f"fremd{_i_m}.png"))
            _imgm._template_cache.clear()
            for _i_m in range(3):
                _imgm.match_template_in_image(_otherm, f"fremd{_i_m}.png", 0.8)
        finally:
            _imgm.logger.removeHandler(_catchm)
        _konflikt_m = [t for t in _seen_m if "gelernt, geprüft wurde gegen" in t]
        check(f"drei Templates derselben Groesse ergeben EINE Meldung "
              f"({len(_konflikt_m)})", len(_konflikt_m) == 1)
        _text_m = _konflikt_m[0] if _konflikt_m else ""

        # **Die Meldung darf nicht wie ein Defekt klingen, denn meistens ist sie
        # keiner.** Sie hiess "passt nicht zur Scan-Region" und empfahl "Template
        # neu aufnehmen" - im haeufigen Fall genau das Falsche. Wer sie las,
        # suchte einen Fehler, den er nicht gemacht hat.
        check("sie nennt den haeufigen Fall zuerst und beim Namen",
              "normal" in _text_m and "Slot-Höhen" in _text_m)
        # Zwei Ursachen nebeneinander helfen niemandem - es braucht die FRAGE,
        # die sie unterscheidet. Beantworten kann sie nur der Nutzer.
        check("sie stellt die Frage, die beide Faelle trennt",
              "übrigen Items" in _text_m and "gar nichts mehr" in _text_m)
        check("und nennt die Reparatur nur fuer den zweiten Fall",
              "verschoben" in _text_m and "neu vermessen" in _text_m)
        # Die Sperre gehoert weiterhin dazu, sonst stehen zwei Dutzend gleiche
        # Zeilen da und die Meldung ist so gut wie keine.
        check("und sagt, dass sie sich abschaltet", "nicht mehr gemeldet" in _text_m)

        # --- Kein negativer Prozentwert ---
        # TM_CCOEFF_NORMED laeuft von -1 bis +1; unter 0 heisst "die beiden Bilder
        # haben nichts gemeinsam". Als "-51 % Übereinstimmung" gelesen wirkte das
        # wie eine kaputte Zahl, und der Leser sucht den Fehler in der Rechnung.
        from autoclicker.imaging import _size_hint as _gh_m
        check("ein Wert unter 0 wird als 'keine Ähnlichkeit' ausgegeben",
              "keine Ähnlichkeit" in _gh_m("x.png", 62, 57, 62, 60, -0.51)
              and "-51" not in _gh_m("x.png", 62, 57, 62, 60, -0.51))
        check("ein Wert darueber steht als Prozent da",
              "12 %" in _gh_m("x.png", 62, 57, 62, 60, 0.12).replace("\u202f", " ")
              or "12%" in _gh_m("x.png", 62, 57, 62, 60, 0.12))
        # Beide Groessen stehen drin - sonst weiss man nicht, welche Flaeche gemeint
        # ist. Die Zahlen kommen aus dem gestellten Bild (Template 40x40 gegen einen
        # 3 px flacheren Slot), nicht aus einem echten Bestand.
        check("beide Groessen stehen in der Meldung",
              "40x40" in _text_m and "40x37" in _text_m)
        _imgm._reported_sizes.clear()
    finally:
        _imgm.TEMPLATES_DIR = _oldm
        _imgm._template_cache.clear()
        import shutil as _shm
        _shm.rmtree(_dirm, ignore_errors=True)


# --- Jeder Slot-Zustand hat Umriss UND Fuellung in derselben Farbfamilie ---
# Die Rechtecke liegen auf einem SPIELBILD, nicht auf dem dunklen Panel: ein
# duenner Strich in var(--dim) verschwindet zwischen bunten Item-Symbolen. Die
# Flaeche traegt die Aussage - fehlt zu einem Zustand die Fuellungs-Regel, sieht
# er aus wie der Normalfall und niemand merkt es.
# Die Seite selbst - frueher hing dieser Block an einer Variablen aus den
# Scans-Sektionen, die jetzt in `tests/contract/studio_scans.py` stehen. Was eine
# Datei liest, liest sie besser selbst, als sie ueber tausend Zeilen zu erben.
_html18 = _H.studio_web_source()
# Zwei Zustaende, nicht drei: „erkannt, aber nicht in diesem Scan" ist mit
# dem globalen Bestand verschwunden - der Scan besitzt seine Items.
_states18 = ("match", "empty")
_missing18 = [f"{k}.{z}" for z in _states18
              for k in ("scan-slot", "scan-fill")
              if f".{k}.{z}{{" not in _html18.replace(" ", "")]
check(f"jeder Slot-Zustand hat Umriss und Fuellung ({_missing18 or 'vollstaendig'})",
      not _missing18)
# Und jede benutzte Farbvariable ist auch definiert - ein Tippfehler in einem
# var(--slot-...) faellt sonst nur auf, wenn man genau hinsieht.
_used18 = set(_re13.findall(r"var\((--slot-[\w-]+)\)", _html18))
_definiert18 = set(_re13.findall(r"(--slot-[\w-]+)\s*:", _html18))
check(f"jede --slot-Farbe ist definiert ({sorted(_used18 - _definiert18) or 'alle'})",
      _used18 and not (_used18 - _definiert18))
# Die JS-Seite liest dieselben Variablen aus, statt Hexwerte zu wiederholen.
check("und SLOT_COLOR deckt genau die Zustaende ab",
      sorted(_re13.findall(r"\"?([\w-]+)\"?:\s*s\.getPropertyValue", _html18))
      == sorted(_states18))

# --- Jeder Neuaufbau rettet den Fokus hinueber ---
# Tipp-Felder melden beim VERLASSEN (`change`), also loest genau der TAB-Sprung
# den Neuaufbau aus - und `replaceChildren()` wirft dabei das Feld weg, in dem
# man inzwischen steht. Gemeldet wurde es am Item (Name tippen, TAB nach
# Kategorie, Cursor weg); dieselbe Falle steckt in jedem Neuaufbau mit Feldern.
def _js_body18(name: str) -> str:
    """Der Text einer JS-Funktion bis zur naechsten auf Spaltenebene 0."""
    start = _html18.index(f"function {name}(")
    remainder = _html18[start + 10:]
    end = _re13.search(r"\n(?:async )?function ", remainder)
    return remainder[:end.start()] if end else remainder

_rebuild18 = ("render", "renderScans", "renderSettings")
_without_focus18 = [n for n in _rebuild18
                 if "rememberFocus()" not in _js_body18(n)
                 or "restoreFocus(" not in _js_body18(n)]
check(f"jeder Neuaufbau merkt sich den Fokus ({_without_focus18 or 'alle'})",
      not _without_focus18)

# --- Der Scan-Name steht an EINER Stelle, und zwar dort, wo man den Scan waehlt ---
# Er lag im Inspektor rechts, waehrend die Auswahl links steht: man waehlte den
# Scan in der einen Spalte und benannte ihn in der anderen. Dieselbe Doppelung
# gab es beim Klick-Block schon einmal ("Name (Punkt #1)" oben, "Punkt" unten) -
# zwei Felder fuer denselben Wert, und man muss raten, welches fuehrt.
check("der Detailteil des Scans baut kein eigenes Namensfeld mehr",
      'field("Name"' not in _js_body18("scanScanDetails")
      and "cardName(" not in _js_body18("scanScanDetails"))
# Der gefuehrte Arbeitsweg zeigt die Scan-Maske rechts nicht. Deshalb muss die
# Bearbeitungsflaeche direkt bei der Auswahl links stehen. Die Maske zeigt den
# Namen weiterhin, baut aber kein zweites Eingabefeld fuer denselben Wert.
check("die Scan-Maske zeigt den Namen nur als Beschriftung",
      'class: "scan-card-name"' in _js_body18("scanScanCard")
      and 'cardName("scan"' not in _js_body18("scanScanCard"))
check("und die linke Spalte traegt das bearbeitbare Namensfeld",
      'id="scan-name"' in _html18
      and 'field: "name", value: e.target.value' in _html18)
check("die Klappliste zum Waehlen bleibt",
      'id="scan-open"' in _html18)
# Die Ueberschrift im Detailteil nennt den Scan NICHT noch einmal: sein Name
# steht in derselben Maske eine Zeile darueber.
check("und der Detailteil wiederholt ihn nicht",
      'heading("SCAN' not in _js_body18("scanScanDetails"))

# --- In einer scrollenden Spalte darf kein Abschnitt nochmal scrollen ---
# `.seite` scrollt als Ganzes. Setzt ein Abschnitt darin zusaetzlich
# `overflow-y:auto` mit `flex:1`, rechnen beide ihre Hoehe gegeneinander aus:
# `flex:1` loest gegen die SICHTBARE Hoehe auf, und sobald die Abschnitte
# darueber zusammen hoeher sind als das Fenster, bleibt fuer den letzten nichts
# uebrig. Im Scans-Reiter war das die Liste (Scans/Slots/Items) - auf wenige
# Pixel gequetscht und unerreichbar, obwohl die Spalte scrollte.
def _css_rule18(choice: str) -> str:
    position = _html18.index("\n" + choice + "{")
    return _html18[position + len(choice) + 2:_html18.index("}", position)]

# --- Der „alle"-Schieber hat drei Stellungen, nicht zwei ---
# Ueber 56 Schaltern stand er meistens weder auf ein noch auf aus - deshalb gab
# es einmal einen Mischzustand (`indeterminate`). Der Weg ist heute ein anderer:
# EIN Knopf, der SAGT, was er tut („alle dazu" / „alle raus"). Damit ist der
# dritte Stand ersatzlos weg, samt seinem CSS - ein Schalter, der bei „23 von
# 56" nicht zu beschriften ist, war das Problem und nicht die Loesung.
check("es gibt keine globale Mitgliedschaft mehr zu schalten",
      '"alle dazu" : "alle raus"' not in _html18
      and "scan-mitglied" not in _html18)
check("und der Mischzustand ist ersatzlos weg",
      "indeterminate" not in _html18 and "unbestimmt" not in _html18)

check("die Spalte scrollt selbst", "overflow-y:auto" in _css_rule18(".page"))
check("und der wachsende Abschnitt darin nicht nochmal",
      "overflow" not in _css_rule18(".section.growing"))
# `1 0 auto` und nicht `1`: waechst in den freien Platz, schrumpft aber nie
# unter seinen Inhalt - genau das war der Fehler.
check("er darf auch nicht unter seinen Inhalt schrumpfen",
      "flex:1 0 auto" in _css_rule18(".section.growing"))

# --- Das Dear-PyGui-Fenster ist wirklich weg ---
# Geprueft wird der CODE, nicht der Text: dass in zwei Modul-Docstrings steht,
# was frueher unter `scan_canvas/` lag, ist die Begruendung fuer den heutigen
# Aufbau und soll stehen bleiben (CLAUDE.md: "Eine Begruendung ist keine
# Altlast"). Ein IMPORT auf ein Fremdpaket, das niemand mehr installiert,
# waere dagegen ein Modul, das gar nicht erst startet.
import ast as _ast10
_repo17 = Path(__file__).resolve().parent.parent
_rest18 = []
for _pf18 in sorted((_repo17 / "autoclicker").rglob("*.py")):
    if "__pycache__" in _pf18.parts:
        continue
    for _k18 in _ast10.walk(_ast10.parse(_pf18.read_text(encoding="utf-8"))):
        _names18 = []
        if isinstance(_k18, _ast10.Import):
            _names18 = [a.name for a in _k18.names]
        elif isinstance(_k18, _ast10.ImportFrom):
            _names18 = [_k18.module or ""]
        for _n18 in _names18:
            if "dearpygui" in _n18 or "scan_canvas" in _n18:
                _rest18.append(f"{_pf18.name}:{_k18.lineno} {_n18}")
check("kein Modul importiert mehr Dear PyGui", _rest18 == [])
if _rest18:
    print("        " + ", ".join(_rest18))
check("und das alte Scan-Studio-Modul ist geloescht",
      not (_repo17 / "autoclicker/scan_studio.py").exists())
check("der Ordner scan_canvas ebenso",
      not (_repo17 / "autoclicker/editors/scan_canvas").exists())


# --------------------------- Einstellungen im Studio: Schema, Bruecke, Datei
section("Einstellungen: jedes Feld beschrieben, jeder Wert schreibbar")

from dataclasses import fields as _felder17
from autoclicker.config import (
    AppConfig as _AC17, config_sections as _abs17, optional_fields as _opt17,
    save_config as _sc17, apply_config as _ueb17,
)
from autoclicker.config_meta import CONTROLS as _ARTEN17, META as _META17

_names17 = [f.name for f in _felder17(_AC17)]

# --- Das Schema deckt die Dataclass ab, in beide Richtungen ---
# Ohne diesen Test ist die Tabelle in drei Wochen unvollstaendig: ein neues Feld
# in AppConfig faellt nirgends auf, es waere im Fenster einfach nicht da - und
# damit nur in der Datei einstellbar, also genau dort, wo es nicht mehr sein soll.
check("jedes Config-Feld hat eine Beschreibung",
      sorted(_META17) == sorted(_names17))
_too_many17 = sorted(set(_META17) - set(_names17))
if _too_many17:
    print("        beschrieben, aber nicht vorhanden: " + ", ".join(_too_many17))
_missing17 = sorted(set(_names17) - set(_META17))
if _missing17:
    print("        vorhanden, aber unbeschrieben: " + ", ".join(_missing17))

# --- Ein Knopf am Feld zeigt auf eine Methode, die es gibt ---
# Sonst ist er ein Bedienelement, das nichts tut — und das gibt es hier nicht
# (dieselbe Regel wie bei den Kacheln des Teilen-Reiters). Geprueft wird auch,
# dass die Ansicht ihn ueberhaupt zeichnet: eine Meta-Angabe, die niemand liest,
# ist ein Knopf, den niemand sieht.
_actions17 = {k: m.action for k, m in _META17.items() if m.action}
_dead17 = [f"{k} -> {a[0]}" for k, a in _actions17.items()
           if not callable(getattr(_SB8, a[0], None))]
check("jeder Feld-Knopf zeigt auf eine Bruecken-Methode", _dead17 == [])
if _dead17:
    print("        fehlt in der Bruecke: " + ", ".join(_dead17))
check("und die Ansicht zeichnet ihn", "cfgAction(" in _H.studio_web_source())
# Der Katalog ist der Fall, fuer den es das gibt: bis dahin konnte ihn nur
# `python tools/catalog.py` anlegen — ausgerechnet die Datei, ohne die das LLM
# frei raet und die Kategorie leer bleibt.
check("und der Katalog laesst sich im Fenster holen",
      _actions17.get("scan_catalog_file", ("",))[0] == "catalog_fetch")

check("jede Art gibt es auch als Bedienelement",
      all(m.kind in _ARTEN17 for m in _META17.values()))
check("Kacheln nur bei enum - und enum nie ohne Kacheln",
      all(bool(m.options) == (m.kind == "enum") for m in _META17.values()))

# --- Abhaengigkeiten zeigen auf Felder, die es gibt ---
# Ein `dep` ins Leere macht das Feld dauerhaft blass: es waere sichtbar,
# unbedienbar und ohne Erklaerung, warum.
_bools17 = {f.name for f in _felder17(_AC17) if isinstance(f.default, bool)}
_broken17 = []
for _k17, _m17 in _META17.items():
    for _field17, _expected17 in ((_m17.dep, _bools17), (_m17.dep_not, _bools17),
                                 (_m17.dep_min, set(_names17) - _bools17)):
        if _field17 and _field17 not in _expected17:
            _broken17.append(f"{_k17} -> {_field17}")
check("jede Abhaengigkeit zeigt auf ein passendes Feld", _broken17 == [])
if _broken17:
    print("        " + ", ".join(_broken17))

# --- Jede angebotene Auswahl ueberlebt die Validierung ---
# Der eigentliche Test des Schemas: `__post_init__` wirft unbekannte Werte auf
# den Standard zurueck. Stuende in den Kacheln ein Wert, den die Validierung
# nicht kennt, koennte man ihn anklicken, speichern - und die Datei traege etwas
# anderes. Beide Seiten messen, nicht eine abschreiben.
_unfit17 = []
for _k17, _m17 in _META17.items():
    for _value17, _text17 in _m17.options:
        if getattr(_AC17(**{_k17: _value17}), _k17) != _value17:
            _unfit17.append(f"{_k17}={_value17!r}")
check("jede angebotene Auswahl ueberlebt __post_init__", _unfit17 == [])
if _unfit17:
    print("        wird beim Speichern verworfen: " + ", ".join(_unfit17))

# --- Die Abschnitte decken alles ab ---
# `config_sections()` haengt Nichtzugeordnetes hinten an (damit nichts
# unsichtbar wird). Genau das darf aber nie noetig sein - sonst steht ein Feld
# in der Datei woanders als in seiner Gruppe.
_groups17 = _abs17()
check("die Abschnitte decken jedes Feld ab",
      sorted(k for _, keys in _groups17 for k in keys) == sorted(_names17))
check("kein Feld faellt in den Nachzuegler-Abschnitt",
      "SONSTIGE" not in [t for t, _ in _groups17])
check("und keines steht doppelt",
      len([k for _, keys in _groups17 for k in keys]) == len(_names17))

# --- Optional heisst: leeres Feld ist `null`, nicht 0 ---
_defaults17 = {f.name: f.default for f in _felder17(_AC17)}
check("optionale Felder sind genau die mit Standard None",
      sorted(_opt17()) == sorted(k for k, v in _defaults17.items() if v is None))

# --- Der Wertvergleich der Bruecke ---
from autoclicker.editors.sequence_studio.bridge import _same_value as _gw17

check("600 und 600.0 sind derselbe Wert", _gw17(600, 600.0))
check("True ist nicht 1", not _gw17(True, 1))
check("False ist nicht 0", not _gw17(False, 0))
check("Listen werden elementweise verglichen", _gw17([960, 540], [960.0, 540.0]))
check("und Ungleiches bleibt ungleich", not _gw17([960, 540], [960, 541]))
check("None ist nicht 0", not _gw17(None, 0))

# --- Bruecke gegen Datei ---
_sandbox17 = tempfile.mkdtemp(prefix="studiocfg_")
_cwd17 = _os.getcwd()
_os.chdir(_sandbox17)
try:
    Path("sequences").mkdir()
    _b17 = _SB8(_SEQ8(name="S"), Path("sequences/S.json"), "sequences")

    # Ohne Datei: Standardwerte, kein Fehler, und der Pfad ist absolut.
    _read17 = _b17.config_read()
    check("ohne config.json kommen die Standardwerte",
          _read17["values"]["click_per_point"] == 1 and not _read17["error"])
    check("der Pfad steht absolut dabei", _os.path.isabs(_read17["path"]))
    check("die Beschreibungen kommen mit",
          _read17["meta"]["click_per_point"]["label"] == "Klicks pro Punkt")

    # Eine Datei mit einem von Hand gesetzten Wert - der muss ein Speichern
    # ueberleben, das ihn gar nicht anfasst. Das ist der Grund, warum nur die
    # geaenderten Schluessel geschickt werden: der Hauptprozess schreibt
    # dieselbe Datei, und ein Fenster, das seit einer Stunde offensteht, darf
    # dessen Aenderungen nicht mit seinem alten Stand ueberbuegeln.
    _sc17(_AC17(window_focus_title="Idle Clans X", scan_marker_count=9))
    _answer17 = _b17.config_write({"values": {"click_post_delay": 0.25}})
    check("das Speichern meldet Erfolg", _answer17["ok"])
    _file17 = json.loads(Path("config.json").read_text(encoding="utf-8"))
    check("der geaenderte Wert steht in der Datei", _file17["click_post_delay"] == 0.25)
    check("und der fremde Wert ist unangetastet",
          _file17["window_focus_title"] == "Idle Clans X"
          and _file17["scan_marker_count"] == 9)
    check("nichts wurde korrigiert", _answer17["corrections"] == [])
    check("die Reihenfolge in der Datei folgt den Abschnitten",
          list(_file17) == [k for _, keys in _groups17 for k in keys])

    # Der Hauptprozess erfaehrt davon - sonst gaelte die Einstellung erst nach
    # einem Neustart, obwohl die Datei schon neu ist.
    import autoclicker.mailbox as _bf17
    _job17 = _bf17.fetch_command()
    check("der Hauptprozess bekommt Bescheid",
          _job17 is not None and _job17["command"] == "config")

    # Eine Korrektur wird gemeldet statt still hingenommen.
    _answer17 = _b17.config_write({"values": {"scan_min_confidence": 1.5}})
    check("eine Korrektur wird zurueckgemeldet",
          [k["key"] for k in _answer17["corrections"]] == ["scan_min_confidence"]
          and _answer17["corrections"][0]["became"] == 0.8)
    check("und die Datei traegt den korrigierten Wert",
          json.loads(Path("config.json").read_text(encoding="utf-8"))["scan_min_confidence"] == 0.8)

    # Ein `600` von Hand darf nicht als Korrektur gelten, nur weil der Loader
    # eine 600.0 daraus macht.
    _answer17 = _b17.config_write({"values": {"pixel_show_delay": 1}})
    check("eine ganze Zahl in einem Kommafeld ist keine Korrektur",
          _answer17["corrections"] == [])

    # Nichts zu tun ist kein Fehler, aber auch kein Schreibvorgang.
    check("ohne Werte wird nicht geschrieben", _b17.config_write({"values": {}})["ok"] is False)

    # Kaputt ist nicht leer: draufschreiben wuerde den einzigen Rest wegwerfen,
    # den man noch von Hand reparieren kann.
    Path("config.json").write_text("{kein json", encoding="utf-8")
    _answer17 = _b17.config_write({"values": {"click_per_point": 3}})
    check("eine unlesbare config.json wird nicht ueberschrieben",
          not _answer17["ok"] and Path("config.json").read_text(encoding="utf-8") == "{kein json")
    check("und der Leser meldet sie statt Standardwerte zu behaupten",
          bool(_b17.config_read()["error"]))

    # **Ein gescheitertes Schreiben ist kein Erfolg.** `save_config()` gab
    # `None` zurueck, und die Bruecke meldete `ok: True` ueber einer Datei, die
    # nicht geschrieben wurde — dazu wanderte der Wert in den eigenen Prozess
    # und der Briefkasten-Befehl ging raus, waehrend der Hauptprozess die alte
    # DATEI las: zwei Prozesse, zwei Staende. Genau der Fall aus CLAUDE.md
    # („Ein Saver sagt, ob er gespeichert hat").
    _sc17(_AC17(click_per_point=1))
    _bf17.discard_command()
    import autoclicker.config as _cfgmod17
    _old_write17 = _cfgmod17.atomic_write

    def _broken17(*a, **k):
        raise OSError("Platte voll")
    _cfgmod17.atomic_write = _broken17
    try:
        with _ctx.redirect_stdout(_io.StringIO()):
            _answer17 = _b17.config_write({"values": {"click_per_point": 5}})
    finally:
        _cfgmod17.atomic_write = _old_write17
    check("ein Schreibfehler meldet ok: False",
          _answer17["ok"] is False and "nicht geschrieben" in _answer17["message"])
    check("die Datei ist unveraendert",
          json.loads(Path("config.json").read_text(encoding="utf-8"))["click_per_point"] == 1)
    check("der eigene Prozess uebernimmt den Wert nicht",
          _cfgmod17.CONFIG.click_per_point != 5)
    check("und der Hauptprozess bekommt keinen Befehl", _bf17.fetch_command() is None)
finally:
    _os.chdir(_cwd17)

# --- Ein Config-Objekt pro Prozess ---
# `state.config` IST das Modul-CONFIG. Wer es austauscht, laesst jeden zurueck,
# der `from .config import CONFIG` geschrieben hat (imaging, die Item-Editoren) -
# die saehen ab da dauerhaft die Werte vom Programmstart. Deshalb wird
# hineingeschrieben, und deshalb prueft der Test die QUELLE: eine Zuweisung an
# `.config` ist ausserhalb von main.py ein Fehler.
_target17, _source17 = _AC17(), _AC17(click_per_point=7, llm_model="x")
_ueb17(_target17, _source17)
check("apply_config() traegt alle Werte ueber",
      _target17.click_per_point == 7 and _target17.llm_model == "x")
check("und laesst das Objekt in Ruhe", _target17 is not _source17)

_assignments17 = []
for _pf17 in sorted((_repo17 / "autoclicker").rglob("*.py")) + [_repo17 / "main.py"]:
    if "__pycache__" in _pf17.parts:
        continue
    for _nr17, _row17 in enumerate(_pf17.read_text(encoding="utf-8").splitlines(), 1):
        # Nur der State: ein `self.config = ...` in einem Stellvertreter-Objekt
        # (scans._ConfigOnly) ist kein Austausch der Programm-Config.
        if _re13.search(r"^\s*(?:\w+\.)?state\.config\s*=\s*", _row17):
            _assignments17.append(f"{_pf17.name}:{_nr17}: {_row17.strip()}")
# Ohne Zeilennummer: die waere bei jeder Einfuegung in main.py falsch, und der
# Test soll die Regel pinnen, nicht die Zeile.
_allowed17 = ["main.py: state.config = CONFIG"]
_found17 = [f"{z.split(':')[0]}: {z.split(': ', 1)[1]}" for z in _assignments17]
check("nur main.py setzt state.config - und zwar auf CONFIG selbst",
      _found17 == _allowed17)
if _found17 != _allowed17:
    for _z17 in _assignments17:
        print("        " + _z17)


# --------------------------- Doku gegen Code: Hotkeys und Config-Felder
section("Was der Code kann, steht auch in der Doku")

# Beide Seiten messen, nicht eine abschreiben: die Hilfe im Programm und die
# README-Tabelle sind das, wonach jemand sucht, der einen Hotkey NICHT kennt.
# Fehlt er dort, existiert er praktisch nicht - genau so waren fuenf
# Aufnahme-Hotkeys und sechs Config-Felder monatelang unauffindbar.
import re as _re15

_root15 = Path(__file__).resolve().parent.parent
_winapi15 = (_root15 / "autoclicker/platforms/windows.py").read_text(encoding="utf-8")
_table15 = _re15.search(r"_HOTKEY_DEFINITIONS = \[(.*?)\n\]", _winapi15, _re15.S).group(1)
_hotkeys15 = set(_re15.findall(r'"(CTRL\+ALT\+(?:SHIFT\+)?\w)\s', _table15))
_help15 = set(_re15.findall(r"col\('(CTRL\+ALT\+(?:SHIFT\+)?\w)'",
                             (_root15 / "main.py").read_text(encoding="utf-8")))
_readme15 = (_root15 / "README.md").read_text(encoding="utf-8")
_tab15 = set(_re15.findall(r"\| `(CTRL\+ALT\+(?:SHIFT\+)?\w)` \|", _readme15))

check("der Test findet ueberhaupt Hotkeys", len(_hotkeys15) > 20)
check("jeder registrierte Hotkey steht in print_help()",
      sorted(_hotkeys15 - _help15) == [])
if _hotkeys15 - _help15:
    print("        fehlt in der Hilfe: " + ", ".join(sorted(_hotkeys15 - _help15)))
check("und in der Hotkey-Tabelle der README",
      sorted(_hotkeys15 - _tab15) == [])
if _hotkeys15 - _tab15:
    print("        fehlt in der README: " + ", ".join(sorted(_hotkeys15 - _tab15)))
check("und die Hilfe erfindet keine, die es nicht gibt",
      sorted(_help15 - _hotkeys15) == [])

# Config: jedes Feld der Dataclass muss in der README vorkommen. Ein Wert, den man
# nur durch Lesen von config.py findet, ist kein eingestellter, sondern ein
# versteckter - und die Datei ist die einzige Stelle, an der man ihn aendern kann.
# Die Felder kommen aus der Dataclass selbst, nicht aus einem Regex ueber den
# Quelltext: der fing auch `try:` in den Methoden darunter ein.
from autoclicker.config import AppConfig as _AC15
_fields15 = {f.name for f in _dc5.fields(_AC15)}
check("der Test findet ueberhaupt Config-Felder", len(_fields15) > 50)
_undok15 = sorted(f for f in _fields15 if f"`{f}`" not in _readme15)
check("jedes Config-Feld ist in der README beschrieben", _undok15 == [])
if _undok15:
    print("        undokumentiert: " + ", ".join(_undok15))




# --------------------------- Die Doku nennt nur Dateien, die es gibt
section("CLAUDE.md zeigt auf Dateien, die es wirklich gibt")

# **Eine Doku, die in die Irre fuehrt, ist schlimmer als keine** — und genau das
# ist passiert: `tools/llm_bench.py` suchte das gemerkte Bild zuerst unter
# `item_scans/bilder/`, weil CLAUDE.md es an zwei Stellen so schrieb. Der Code
# legt es daneben ab (`sequences/<name>/bilder/`). Pfade mit Platzhaltern kann
# kein Test pruefen, Dateinamen sehr wohl.
_claude16 = (_root15 / "CLAUDE.md").read_text(encoding="utf-8")
_named16 = sorted(set(_re15.findall(r"`([\w/\.]+\.py)`", _claude16)))
check("der Test findet ueberhaupt Dateinamen", len(_named16) > 50)

# Drei Dateien werden mit Absicht genannt, obwohl es sie nicht mehr gibt: die
# Begruendung, WARUM etwas nicht mehr so gebaut ist, ist laut CLAUDE.md selbst
# keine Altlast — sie verhindert, dass jemand den alten Weg noch einmal
# einschlaegt.
_DELETED16 = {
    "autoclicker/scan_studio.py",    # das zweite Fenster in Dear PyGui
    "execution.py",                  # Weiterleitung ohne Inhalt
    "tools/sync_json.py",            # pflegte Felder nach, die heute fehlen sollen
}
_missing16 = [d for d in _named16
            if d not in _DELETED16
            and not list(_root15.rglob(d.split("/")[-1]))]
check("jede genannte .py-Datei existiert", _missing16 == [])
if _missing16:
    print("        gibt es nicht: " + ", ".join(_missing16))

# Und die Ausnahmeliste bleibt ehrlich: taucht eine der drei wieder auf, gehoert
# sie da nicht mehr hin. Dieselbe Regel wie bei `PLATTFORM_MODULE` — eine Liste,
# die niemand prueft, waechst zur Fiktion.
_wieder16 = sorted(d for d in _DELETED16
                   if list(_root15.rglob(d.split("/")[-1])))
check("und keine der drei Ausnahmen ist heimlich zurueck", _wieder16 == [])
if _wieder16:
    print("        wieder da: " + ", ".join(_wieder16))


# --------------------------- Jedes Modul laesst sich ueberhaupt importieren
section("Jedes Modul ist importierbar (kein Import zeigt ins Leere)")

# Eine Massen-Umbenennung hat einmal einen Modulnamen auf eine Datei zeigen
# lassen, die es nie gab: pyflakes loest keine Fremdmodule auf, und aufgefallen
# waere es erst beim Druecken des Hotkeys. Der Test importiert deshalb JEDES Modul
# einmal - der billigste Beweis, dass die Importe aufgehen.
import importlib as _il10

_root10 = Path(__file__).resolve().parent.parent

_broken10, _checked10 = [], 0
for _pf10 in sorted((_root10 / "autoclicker").rglob("*.py")):
    if "__pycache__" in _pf10.parts:
        continue
    _rel10 = _pf10.relative_to(_root10).with_suffix("")
    _mod10 = ".".join(_rel10.parts)
    if _mod10.endswith(".__init__"):
        _mod10 = _mod10[: -len(".__init__")]
    try:
        with _cl2.redirect_stdout(_io2.StringIO()):
            _il10.import_module(_mod10)
        _checked10 += 1
    except Exception as _e10:
        _broken10.append(f"{_mod10}: {type(_e10).__name__} {_e10}")

check("jedes Modul laesst sich importieren", _broken10 == [])
if _broken10:
    for _z10 in _broken10:
        print("        " + _z10)
check("und der Test hat wirklich etwas geprueft", _checked10 >= 50)

# Das allein reicht NICHT: genau der Fehler von oben sass in einem Import INNERHALB
# einer Funktion (scan_studio.main importiert den Canvas erst beim Start, damit Dear
# PyGui nicht am Modul haengt). Einen Modulrumpf zu importieren fuehrt solche Zeilen
# nie aus - der Test war gruen, die App kaputt.
#
# Deshalb zusaetzlich statisch: jede relative Import-Zeile, egal wo sie steht, muss
# auf eine Datei zeigen, die es gibt.
import ast as _ast10

_dead10 = []
for _pf10 in sorted((_root10 / "autoclicker").rglob("*.py")):
    if "__pycache__" in _pf10.parts:
        continue
    try:
        _tree10 = _ast10.parse(_pf10.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    for _k10 in _ast10.walk(_tree10):
        if not (isinstance(_k10, _ast10.ImportFrom) and _k10.level and _k10.module):
            continue
        # level=1 -> eigenes Paket, level=2 -> eins darueber, ...
        _base10 = _pf10.parent
        for _ in range(_k10.level - 1):
            _base10 = _base10.parent
        _target10 = _base10.joinpath(*_k10.module.split("."))
        if not (_target10.with_suffix(".py").exists() or (_target10 / "__init__.py").exists()):
            _dead10.append(f"{_pf10.name}:{_k10.lineno} from {'.' * _k10.level}{_k10.module}")
check("auch Importe INNERHALB von Funktionen zeigen auf existierende Module",
      _dead10 == [])
if _dead10:
    for _z10 in _dead10:
        print("        " + _z10)


# ============================================================================
# Crash-sicheres Schreiben, Zeit-Eingaben, Presets, Session-Log
# ============================================================================
# Diese vier standen in KEINEM Test - und `atomic_write()` ist ausgerechnet die
# Funktion, die einen Absturz mitten im Speichern ueberleben soll. Was das Projekt
# an Daten haelt, haengt an ihr: jeder Saver geht durch sie.

# Die ausgelagerten Themen-Module
# Der Einstiegspunkt bleibt genau einer, aber nicht alles muss in dieser Datei
# stehen (sie war mit ueber 7.000 Zeilen die groesste des Repos). Neue Sektionen
# kommen als eigenes Modul unter `tests/contract/`, holen ihr Geruest aus
# `_harness.py` und werden hier importiert - Import = ausfuehren.
import tests.contract.studio_scans          # noqa: F401,E402
import tests.contract.studio_detection     # noqa: F401,E402
import tests.contract.studio_tools     # noqa: F401,E402
import tests.contract.console_editors     # noqa: F401,E402
import tests.contract.persistence_base      # noqa: F401,E402
import tests.contract.reclick            # noqa: F401,E402
import tests.contract.studio_share        # noqa: F401,E402
import tests.contract.report              # noqa: F401,E402
import tests.contract.points               # noqa: F401,E402
import tests.contract.sequence_delete     # noqa: F401,E402
import tests.contract.catalog               # noqa: F401,E402
import tests.contract.breakpoint            # noqa: F401,E402
import tests.contract.usability             # noqa: F401,E402
import tests.contract.scheduled_phases      # noqa: F401,E402
import tests.contract.sequence_context      # noqa: F401,E402
import tests.contract.pause_and_skip        # noqa: F401,E402
import tests.contract.pixel_fallback        # noqa: F401,E402
import tests.contract.import_config         # noqa: F401,E402
import tests.contract.start_from            # noqa: F401,E402
import tests.contract.record_from           # noqa: F401,E402
import tests.contract.session_limit         # noqa: F401,E402
import tests.contract.block_import          # noqa: F401,E402
import tests.contract.sequence_names        # noqa: F401,E402
import tests.contract.run_lifecycle         # noqa: F401,E402
import tests.contract.point_surface         # noqa: F401,E402
import tests.contract.live_wait             # noqa: F401,E402
import tests.contract.cross_phase_selection  # noqa: F401,E402


import shutil as _shD
from autoclicker.imaging import (PILLOW_AVAILABLE, OPENCV_AVAILABLE)

# ---------------------------------- Vorlagenordner: Dedup ohne ihn ist blind
section("Vorlagen werden IM Sequenzordner gesucht, nicht im globalen von frueher")

# **Die Vorlage liegt bei ihrer Sequenz.** Wer `template_root` weglaesst, faellt
# auf `items/templates/` zurueck - den globalen Ordner aus der Zeit vor den
# Besitzeinheiten, den es nicht mehr gibt. `template_size()` liefert dann fuer
# JEDE Vorlage None, und alles, was Groessen vergleicht, sagt "kenne ich nicht".
#
# Das ist kein Schoenheitsfehler: daran haengt die Dedup-Pruefung von
# `learn_unknown`. Findet sie nie einen Treffer, legt der Worker denselben Slot
# in JEDEM Zyklus erneut als neues Item an.
if PILLOW_AVAILABLE and OPENCV_AVAILABLE:
    from PIL import Image as _ImgD
    from autoclicker.imaging import template_size as _tsD
    from autoclicker.editors.item_editor.markers import (
        _item_has_compatible_template as _ihctD,
        _find_matching_existing_item as _fmeiD)
    from autoclicker.models import ItemProfile as _IPD

    _sandboxD = Path(tempfile.mkdtemp(prefix="vorlagen_"))
    _folderD = _sandboxD / "sequences" / "farm" / "templates"
    _folderD.mkdir(parents=True)
    _ImgD.new("RGB", (62, 60), (10, 120, 90)).save(_folderD / "bogen_62x60.png")
    _itemD = _IPD("Bogen", template="bogen_62x60.png")
    _imageD = _ImgD.new("RGB", (62, 60), (10, 120, 90))

    check("mit Ordner wird die Vorlage gemessen",
          _tsD("bogen_62x60.png", _folderD) == (62, 60))
    check("ohne Ordner findet sie niemand", _tsD("bogen_62x60.png") is None)

    # Das ist die Zusicherung, an der der Fehler haing: die Dedup-Pruefung.
    check("mit Ordner gilt das Item als schon versorgt",
          _ihctD(_itemD, _imageD, _folderD) is True)
    check("ohne Ordner haelt sie es faelschlich fuer neu",
          _ihctD(_itemD, _imageD) is False)

    if OPENCV_AVAILABLE:
        check("und die Duplikat-Suche findet es nur mit Ordner",
              _fmeiD(_imageD, [("Bogen", _itemD)], 0.8, _folderD) == "Bogen")

    # Die Weitergabe an beide Helfer prüft test_runtime_hardening durch
    # einen ausgeführten Lernschritt, unabhängig von Zeilenumbrüchen im Code.
    _shD.rmtree(_sandboxD, ignore_errors=True)
else:
    print("  ÜBERSPRUNGEN: Vorlagengrössen brauchen Pillow und OpenCV")


PASS, FAIL = _H.PASS, _H.FAIL

print(f"\n================  {PASS} PASS / {FAIL} FAIL  ================")
sys.exit(1 if FAIL else 0)
