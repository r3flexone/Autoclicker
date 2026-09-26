"""Blöcke ohne eigene Stelle haben keinen Punkt — und Namen sind keine Dateinamen.

Zwei Befunde aus derselben echten Sequenz, deshalb ein Modul.

Gemeldet an einem Item-Scan-Block, der ein Farbfeld vor seinem Scan-Namen
trug: er war aus einem duplizierten Klick-Block per Typwechsel entstanden, und
`set_block_type()` liess die `point_id` stehen. Derselbe Weg galt für jeden
Typ ohne Stelle (Boss-Scan, Boss-Watcher, Icon-Scan, Taste, Screenshot). Der
Rest wirkte: der Punkt galt als verwendet, die Live-Ansicht zeigte vor dem
Scan dessen Pixel, und fehlte er, übersprang der Lauf den ganzen Scan.

Dazu ein zweiter Fehler am selben Ort: die schon markierte Typ-Kachel noch
einmal anzuklicken löschte den Scan-Namen (bzw. setzte eine Taste auf „enter").
"""
import contextlib as _cl
import io as _io
import json as _json
import os as _os
import shutil as _sh
import tempfile as _tmp

from ._harness import check, section
from autoclicker.models import (
    BLOCK_BOSS_SCAN, BLOCK_BOSS_WATCHER, BLOCK_CLICK, BLOCK_ICON_SCAN,
    BLOCK_ITEM_SCAN, BLOCK_KEY, BLOCK_SCREENSHOT, BLOCK_WAIT, BLOCK_WAIT_CLICK,
    POSITIONLESS_BLOCKS,
    ClickPoint as _CP,
    ElseConfig as _EC,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
    WaitCondition as _WC,
    block_type as _type,
)
from autoclicker.persistence import (
    load_sequence_file, save_sequence_file, sequence_file,
)
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.editors.sequence_studio.model import set_block_type as _set_type

_ALL = (BLOCK_ITEM_SCAN, BLOCK_BOSS_SCAN, BLOCK_BOSS_WATCHER, BLOCK_ICON_SCAN,
        BLOCK_KEY, BLOCK_SCREENSHOT)


def _click():
    return _STEP(x=4458, y=221, name="Bestätigen Juwel", point_id=12,
                 recorded_color=(32, 135, 111),
                 verify_condition=_WC(point_id=3),
                 else_config=_EC(action="click", point_id=4))


# =============================================================================
section("Typwechsel: ein Block ohne Stelle verliert den Punkt, sonst nichts")
# =============================================================================
check("die Menge nennt genau die sechs Typen ohne Stelle",
      POSITIONLESS_BLOCKS == set(_ALL))
for _t in _ALL:
    _s = _click()
    _set_type(_s, _t)
    check(f"{_t}: point_id, x/y und Farbe weg — der Name bleibt",
          _type(_s) == _t and _s.point_id is None and (_s.x, _s.y) == (0, 0)
          and _s.recorded_color is None and _s.name == "Bestätigen Juwel")
    check(f"{_t}: Nachprüfung und ELSE-Klick sind eigene Referenzen und bleiben",
          _s.verify_condition.point_id == 3 and _s.else_config.point_id == 4)
for _t in (BLOCK_CLICK, BLOCK_WAIT, BLOCK_WAIT_CLICK):
    _s = _click()
    _set_type(_s, _t)
    check(f"{_t}: der Punkt bleibt — Klick/Warten sind zwei Schalter an einem Block",
          _type(_s) == _t and _s.point_id == 12 and (_s.x, _s.y) == (4458, 221))

# =============================================================================
section("Dieselbe Kachel noch einmal ändert nichts")
# =============================================================================
for _field, _value, _t in (("item_scan", "raid", BLOCK_ITEM_SCAN),
                           ("boss_scan", "drache", BLOCK_BOSS_SCAN),
                           ("boss_watcher", "wache", BLOCK_BOSS_WATCHER),
                           ("icon_scan", "truhe", BLOCK_ICON_SCAN),
                           ("key_press", "space", BLOCK_KEY)):
    _s = _STEP(**{_field: _value})
    _set_type(_s, _t)
    check(f"{_t}: '{_value}' übersteht den zweiten Klick auf die markierte Kachel",
          getattr(_s, _field) == _value)
_s = _STEP(boss_scan="drache")
_set_type(_s, BLOCK_ITEM_SCAN)
check("ein ECHTER Wechsel nimmt keinen fremden Namen mit (Boss → Item-Scan leer)",
      _s.item_scan == "" and _s.boss_scan is None)

# =============================================================================
section("Brücke: gelöst wird gesagt, derselbe Typ legt keinen Abzug ab")
# =============================================================================
_sandbox = _tmp.mkdtemp(prefix="ohne_stelle_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    _seq = _SEQ("juwel", loop_phases=[_PHASE("Loop", steps=[
        _STEP(x=10, y=10, point_id=1),
        _STEP(x=20, y=20, point_id=2, wait_only=True)])],
        points=[_CP(10, 10, "Bestätigen", 1, color=(32, 135, 111)),
                _CP(20, 20, "Beobachten", 2, color=(1, 2, 3))])
    _path = sequence_file(_seq.name)
    _path.parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(_seq, _path)
    with _cl.redirect_stdout(_io.StringIO()):
        _b = _SB(load_sequence_file(_path), _path, "sequences")

    def _card(snap, row):
        return snap["phases"][1]["blocks"][row]

    _snap = _b.snapshot()
    check("ein Klick-Block trägt das Farbfeld an seiner STELLE",
          _card(_snap, 0)["point_color"] == "#20876F"
          and _card(_snap, 0)["rows"][0]["label"] == "STELLE")
    check("ein Warten-Block mit Punkt trägt es NICHT vor seiner Wartezeit",
          _card(_snap, 1)["point_color"] is None)

    _b.select({"phase": 1, "row": 0})
    _snap = _b.block_set_type({"type": BLOCK_ITEM_SCAN})
    _step = _b.board.lanes[1].steps[0]
    check("Klick → Item-Scan: der Punkt ist gelöst und die Meldung sagt es",
          _step.point_id is None and "Punkt #1 gelöst" in _snap["status"]["text"])
    check("…die Karte zeigt kein Farbfeld mehr vor dem Scan-Namen",
          _card(_snap, 0)["point_color"] is None and _card(_snap, 0)["points"] == [])
    check("…und der Punkt gilt nicht mehr als von diesem Block verwendet",
          _b._point_usages(1) == [])
    check("…der Titel bleibt als eigener Name des Blocks",
          _card(_snap, 0)["title"] == "Bestätigen")
    _snap = _b.block_point({"point": 1})
    check("auch über „Punkt wählen“ bekommt ein Scan keinen Punkt",
          _b.board.lanes[1].steps[0].point_id is None
          and _snap["status"]["kind"] == "warn")
    _before_create = len(_b.points)
    _b.point_create({"x": 99, "y": 99})
    check("…und über „Punkt anlegen“ weder einen Punkt noch einen Listeneintrag",
          _b.board.lanes[1].steps[0].point_id is None and len(_b.points) == _before_create)

    _before = len(_b._edit_undo)
    _b.block_set({"field": "item_scan", "value": "raid"})
    _depth = len(_b._edit_undo)
    _snap = _b.block_set_type({"type": BLOCK_ITEM_SCAN})
    check("die schon markierte Kachel: Scan-Name bleibt, kein neuer Abzug",
          _b.board.lanes[1].steps[0].item_scan == "raid"
          and len(_b._edit_undo) == _depth and _depth == _before + 1)

    _b.undo()
    _b.undo()
    check("STRG+Z holt den Punkt zurück", _b.board.lanes[1].steps[0].point_id == 1)
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)

# =============================================================================
section("Altbestand: der Loader nimmt den Rest-Punkt ab — gesagt, nicht still")
# =============================================================================
_sandbox = _tmp.mkdtemp(prefix="ohne_stelle_alt_")
_os.chdir(_sandbox)
try:
    _path = sequence_file("alt")
    _path.parent.mkdir(parents=True, exist_ok=True)
    # So stand es in einer echten Datei: der Serializer liess den Namen weg,
    # weil eine point_id danebenstand — er kam nur über den Punkt an die Karte.
    _path.write_text(_json.dumps({
        "name": "alt", "schema_version": 4,
        "points": [{"id": 12, "x": 4458, "y": 221, "name": "Bestätigen Juwel",
                    "color": [32, 135, 111]},
                   {"id": 5, "x": 1, "y": 2, "name": "Knopf"}],
        "loop_phases": [{"name": "Loop", "repeat": 1, "steps": [
            {"point_id": 5, "delay_before": 1.0},
            {"point_id": 12, "delay_before": 2.03, "item_scan": "raid"},
            {"point_id": 12, "delay_before": 0.0, "boss_scan": "drache"},
            {"point_id": 12, "delay_before": 0.0, "icon_scan": "truhe"},
            {"point_id": 12, "delay_before": 0.0, "key_press": "space",
             "name": "Eigener Name"},
        ]}],
    }), encoding="utf-8")
    _out = _io.StringIO()
    with _cl.redirect_stdout(_out):
        _loaded = load_sequence_file(_path)
    _steps = _loaded.loop_phases[0].steps
    check("der Klick behält seinen Punkt", _steps[0].point_id == 5)
    check("Item-, Boss-, Icon-Scan und Taste verlieren ihn",
          all(s.point_id is None for s in _steps[1:]))
    check("…ohne Koordinaten-Rest", all((s.x, s.y) == (0, 0) for s in _steps[1:]))
    check("der Name des Punkts wird der des Blocks, ein eigener gewinnt",
          [s.name for s in _steps[1:]] == ["Bestätigen Juwel"] * 3 + ["Eigener Name"])
    check("gemeldet wird jede Stelle einzeln",
          _out.getvalue().count("braucht als Block ohne eigene Stelle keinen Punkt") == 4)
    check("…und kein Schritt gilt deshalb als unaufgelöst",
          not any(s.unresolved for s in _steps))

    with _cl.redirect_stdout(_io.StringIO()):
        save_sequence_file(_loaded, _path)
    _written = _json.loads(_path.read_text(encoding="utf-8"))["loop_phases"][0]["steps"]
    check("gespeichert steht die point_id nur noch am Klick",
          [s.get("point_id") for s in _written] == [5, None, None, None, None])
    check("…und der Name steht jetzt im Block selbst",
          _written[1].get("name") == "Bestätigen Juwel" and "x" not in _written[1])
    _out = _io.StringIO()
    with _cl.redirect_stdout(_out):
        load_sequence_file(_path)
    check("beim zweiten Laden ist nichts mehr zu melden",
          "ohne eigene Stelle" not in _out.getvalue())
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)


# =============================================================================
section("Namen sind keine Dateinamen: Leerzeichen bleiben, die Datei ist bereinigt")
# =============================================================================
from autoclicker.editors.sequence_studio.scan_contract import (  # noqa: E402
    clean_scan_name as _clean, free_scan_name as _free, scan_name_taken as _taken,
)
check("Leerraum wird zusammengezogen, sonst nichts",
      _clean("  Raid   Scan ") == "Raid Scan" and _clean("Götter") == "Götter")
check("belegt ist, was in DIESELBE Datei schriebe",
      _taken("raid  scan", {"Raid Scan": 1}) == "Raid Scan"
      and _taken("Raid Scan", {"Raid Scan": 1}, old="Raid Scan") == ""
      and _taken("Beute", {"Raid Scan": 1}) == "")
check("ein freier Name weicht auf den Zähler aus",
      _free("Neuer Scan", {"neuer scan": 1}) == "Neuer Scan 2")

_sandbox = _tmp.mkdtemp(prefix="namen_")
_os.chdir(_sandbox)
try:
    _seq = _SEQ("Abrechnung mit den Göttern", loop_phases=[_PHASE("Loop", steps=[
        _STEP(item_scan="item_scan_raid"), _STEP(boss_scan="drache_alt")])])
    _path = sequence_file(_seq.name)
    _path.parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(_seq, _path)
    with _cl.redirect_stdout(_io.StringIO()):
        _b = _SB(load_sequence_file(_path), _path, "sequences")
        _b.scan_new({"name": "item_scan_raid"})
        _b.scan_new({"name": "Beute"})
        _b.boss_scan_new({"name": "drache_alt"})
        _b.scan_save()
    _scans = _path.parent / "item_scans"
    check("Ordner der Sequenz bereinigt, ihr Name nicht",
          _path.parent.name == "abrechnung_mit_den_göttern"
          and _b.board.name == "Abrechnung mit den Göttern")

    # Nur die Schreibweise: dieselbe Datei — sie darf nicht gelöscht werden.
    with _cl.redirect_stdout(_io.StringIO()):
        _snap = _b.scan_set({"name": "item_scan_raid", "field": "name",
                             "value": "Item Scan Raid"})
    # VOR dem Speichern gemessen: danach schriebe es die Datei ohnehin neu, und
    # ein Absturz dazwischen hinterliesse gar keine.
    check("…und bei gleicher Datei bleibt die Datei stehen (vor dem Speichern)",
          (_scans / "item_scan_raid.json").exists())
    with _cl.redirect_stdout(_io.StringIO()):
        _b.scan_save()
    _names = sorted(_json.loads(p.read_text(encoding="utf-8"))["name"]
                    for p in _scans.glob("*.json"))
    check("Umbenennen behält die Leerzeichen",
          "Item Scan Raid" in _b.scans and _snap["status"]["kind"] == "ok")
    check("…gespeichert steht der neue Name in derselben Datei",
          (_scans / "item_scan_raid.json").exists()
          and _names == ["Beute", "Item Scan Raid"])
    check("…und die Referenz im Block zieht mit",
          _b.board.lanes[1].steps[0].item_scan == "Item Scan Raid")

    # Anderer Name: neue Datei, die alte ist weg.
    with _cl.redirect_stdout(_io.StringIO()):
        _b.scan_set({"name": "Item Scan Raid", "field": "name", "value": "Raid Scan"})
        _b.scan_save()
    check("ein neuer Name bekommt seine Datei, die alte verschwindet",
          (_scans / "raid_scan.json").exists()
          and not (_scans / "item_scan_raid.json").exists())

    with _cl.redirect_stdout(_io.StringIO()):
        _snap = _b.scan_set({"name": "Beute", "field": "name", "value": "raid  SCAN"})
    check("ein Name, der auf eine fremde Datei fiele, wird abgelehnt",
          "Beute" in _b.scans and _snap["status"]["kind"] == "warn"
          and "Raid Scan" in _snap["status"]["text"])

    with _cl.redirect_stdout(_io.StringIO()):
        _b.boss_scan_set({"name": "drache_alt", "field": "name",
                          "value": "Drache alt"})
        _b.scan_save()
    check("Boss-Scans behalten die Leerzeichen genauso, ihre Datei bleibt",
          "Drache alt" in _b.boss_scans
          and (_path.parent / "boss_scans" / "drache_alt.json").exists()
          and _b.board.lanes[1].steps[1].boss_scan == "Drache alt")

    with _cl.redirect_stdout(_io.StringIO()):
        _b.new({"discard": True})
    check("eine neue Sequenz heisst „Neue Sequenz“, nicht Sequenz_<Zeitstempel>",
          _b.board.name == "Neue Sequenz")
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)