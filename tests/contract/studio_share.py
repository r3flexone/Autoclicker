"""Der Reiter „Teilen": ein Bündel schreiben und eines einlesen.

Import/Export lagen nur in der Konsole. Die Logik (`import_export.py`) bleibt
dieselbe — geprüft wird, was die Brücke daraus macht: der Bestand kommt von
Platte, nicht aus dem Fenster.
"""
import os as _os
import tempfile
from pathlib import Path

from ._harness import check, section, studio_web_source
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.editors.sequence_studio.bridge_share import PARTS as _PARTS
from autoclicker.models import (
    AutoClickerState as _ST, ClickPoint as _CP, ItemProfile as _ITEM,
    ItemScanConfig as _ISC, ItemSlot as _SLOT, LoopPhase as _PHASE,
    Sequence as _SEQ, SequenceStep as _STEP,
)

_web = studio_web_source()

section("Teilen: Export und Import im Studio")

# Die Schluessel sind die Argumentnamen von export_bundle/import_bundle ohne
# Praefix — laufen sie auseinander, exportiert man etwas anderes als angehakt.
import inspect as _inspect
from autoclicker.import_export import export_bundle as _exp, import_bundle as _imp
_export_args = set(_inspect.signature(_exp).parameters)
_import_args = set(_inspect.signature(_imp).parameters)
_missing = [k for k, _ in _PARTS
            if f"include_{k}" not in _export_args or f"import_{k}" not in _import_args]
check("jeder anhakbare Teil hat sein Argument auf beiden Seiten", _missing == [])
if _missing:
    print("        ohne Argument: " + ", ".join(_missing))

check("die Seite hat einen Reiter dafuer", 'data-view="share"' in _web)
check("und ruft die Bruecke ueber einen eigenen Kanal", "callShare(" in _web)

_sandbox = tempfile.mkdtemp(prefix="teilen_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    Path("sequences").mkdir()
    from autoclicker.persistence import (
        list_available_sequences, save_sequence_file, sequence_file, save_item_scan,
    )
    _st = _ST()
    _seq = _SEQ(name="Farm", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1, delay_before=3.0), _STEP(point_id=2)])],
        points=[_CP(id=1, x=100, y=100, name="A"),
                _CP(id=2, x=200, y=200, name="B")])
    _st.active_sequence = _seq
    _st.points = _seq.points
    save_sequence_file(_seq, sequence_file(_seq.name))
    save_item_scan(_ISC(
        name="Inventar", owner_sequence="Farm",
        slots=[_SLOT(name="Slot 1", scan_region=(10, 10, 60, 60),
                     click_pos=(35, 35))],
        items=[_ITEM(name="Erz", marker_colors=[(10, 20, 30)])],
    ))

    _farm_path = dict(list_available_sequences())["Farm"]
    _b = _SB(_seq, _farm_path, "sequences")
    # Der Test misst ausdrücklich den Pfad ohne bekanntes Spielfenster; eine
    # zufällig laufende echte Instanz darf das Ergebnis nicht umdrehen.
    _b._window_layout = lambda: None
    _z = _b.share_data()
    # **Gezaehlt wird, was auf Platte liegt** — exportiert wird derselbe Stand.
    check("der Bestand kommt von Platte",
          _z["inventory"]["sequences"] == 1)
    check("noch kein Buendel da", _z["exports"] == [])
    check("und nichts gewaehlt", _z["import"] is None)

    _z = _b.export_start({"parts": {k: True for k, _ in _PARTS}, "name": "probe"})
    check("das Buendel steht auf Platte", Path("exports/probe.zip").exists())
    check("und in der Liste", [e["name"] for e in _z["exports"]] == ["probe.zip"])
    _z = _b.export_start({"parts": {k: False for k, _ in _PARTS}})
    check("ohne Auswahl wird nichts geschrieben", _z["status"]["kind"] == "warn")

    _z = _b.import_check({"path": "gibtsnicht.zip"})
    check("eine fehlende Datei ist ein Fehler", _z["status"]["kind"] == "err")
    check("und nichts bleibt gewaehlt", _z["import"] is None)

    _z = _b.import_check({"path": "exports/probe.zip"})
    check("das Manifest sagt, was drin ist", _z["import"]["content"]["sequences"] == 1)
    # Ohne beidseitig bekanntes Spielfenster gibt es nichts umzurechnen.
    check("ohne Fenster keine automatische Umrechnung", _z["import"]["auto"] is False)

    _z = _b.import_start({"parts": {k: True for k, _ in _PARTS},
                            "mode": "identity", "merge": True})
    check("der Import laeuft durch", _z["status"]["kind"] == "ok")
    check("und das Fenster liest danach neu", len(_b.points) >= 2)

    # **Der Import schreibt auf Platte, nicht nur in den Speicher.**
    _b2 = _SB(_seq, _farm_path, "sequences")
    check("ein frisches Studio sieht dasselbe",
          _b2.share_data()["inventory"]["sequences"] >= 1)
finally:
    _os.chdir(_cwd)


section("Teilen: einzelne Sequenzen, Teilen-Ordner, Datum")

import json as _json
import zipfile as _zip
from autoclicker.config import CONFIG as _CONFIG, AppConfig as _AC, apply_config as _apply

_sandbox = tempfile.mkdtemp(prefix="teilen_ordner_")
_os.chdir(_sandbox)
_snapshot = _CONFIG.to_dict()        # config_write schreibt ins Modul-CONFIG
try:
    Path("sequences").mkdir()
    from autoclicker.persistence import (
        list_available_sequences, save_sequence_file, sequence_file,
    )
    for _name in ("Farm", "Raid"):
        save_sequence_file(_SEQ(name=_name, points=[_CP(id=1, x=1, y=1)]),
                           sequence_file(_name))
    _seq = _SEQ(name="Farm", points=[_CP(id=1, x=1, y=1)])
    _b = _SB(_seq, dict(list_available_sequences())["Farm"], "sequences")
    _b._window_layout = lambda: None
    _all = {k: True for k, _ in _PARTS}

    _z = _b.share_data()
    check("die Seite bekommt jede Sequenz zum Anhaken, die offene markiert",
          sorted((s["name"], s["open"]) for s in _z["sequences"])
          == [("Farm", True), ("Raid", False)])
    check("ohne Teilen-Ordner zeigt sie exports/ als Ziel",
          _z["folder"]["set"] is False and _z["folder"]["found"] is True)

    _z = _b.export_start({"parts": _all, "sequences": []})
    check("keine Sequenz angehakt: nichts geschrieben, und es wird gesagt",
          _z["status"]["kind"] == "warn" and not Path("exports").exists())

    _z = _b.export_start({"parts": _all, "sequences": ["Raid", "geloescht"]})
    check("eine einzelne Sequenz heisst wie sie, ohne Zeitstempel",
          Path("exports/raid.zip").exists() and "geschrieben" in _z["status"]["text"])
    with _zip.ZipFile("exports/raid.zip") as _zf:
        _manifest = _json.loads(_zf.read("manifest.json"))
    check("drin ist nur die angehakte — ein inzwischen gelöschter Name fällt weg",
          _manifest["contents"]["sequences"] == ["Raid"])
    _z = _b.export_start({"parts": _all, "sequences": ["Raid"]})
    check("ein zweiter Export ersetzt das Bündel und sagt es",
          "ersetzt" in _z["status"]["text"]
          and [e["name"] for e in _z["exports"]] == ["raid.zip"])

    # `sanitize_filename("")` ist „unbenannt“ — geprüft wurde einmal das
    # Ergebnis statt der Eingabe, und jeder Export ohne Namen hiess so.
    _z = _b.export_start({"parts": _all, "sequences": ["Farm", "Raid"]})
    _stamped = [p.name for p in Path("exports").glob("autoclicker_export_*.zip")]
    check("ohne Namen und mit mehreren Sequenzen kommt der Zeitstempel, nicht „unbenannt“",
          len(_stamped) == 1 and not Path("exports/unbenannt.zip").exists())
    for _p in Path("exports").glob("autoclicker_export_*.zip"):
        _p.unlink()

    _raid = [e["path"] for e in _b.share_data()["exports"] if e["name"] == "raid.zip"]
    _z = _b.import_check({"path": _raid[0] if _raid else ""})
    check("die Liste trägt den Pfad, mit dem die Seite einliest",
          _z["import"] is not None and _z["status"]["kind"] == "ok")
    check("das Datum aus dem Manifest steht lesbar da",
          _z["import"]["created"].startswith("erstellt ")
          and _z["import"]["created"][9:11].isdigit())
    check("ein Bündel ohne Datum bleibt ohne, statt eines zu erfinden",
          _b._created_text(None) == "" and _b._created_text("kaputt") == "")

    _z = _b.share_folder_set({"path": "gibtsnicht"})
    check("ein Ordner, den es nicht gibt, wird abgelehnt und nicht angelegt",
          _z["status"]["kind"] == "err" and not Path("gibtsnicht").exists()
          and _CONFIG.share_folder == "")

    Path("onedrive").mkdir()
    _z = _b.share_folder_set({"path": "onedrive"})
    _saved = _json.loads(Path("config.json").read_text(encoding="utf-8"))
    check("ein vorhandener Ordner landet in config.json und im laufenden CONFIG",
          _z["status"]["kind"] == "ok" and _saved.get("share_folder") == "onedrive"
          and _CONFIG.share_folder == "onedrive")
    check("und die Seite zeigt ihn als Ziel",
          _z["folder"] == {"set": True, "path": "onedrive", "found": True})
    _z = _b.export_start({"parts": _all, "sequences": ["Farm"]})
    check("der Export geht in den Teilen-Ordner",
          Path("onedrive/farm.zip").exists() and "im Teilen-Ordner" in _z["status"]["text"]
          and not Path("exports/farm.zip").exists())
    check("die Liste zeigt beide Ordner und sagt, woher",
          sorted((e["name"], e["shared"]) for e in _z["exports"])
          == [("farm.zip", True), ("raid.zip", False)])

    Path("onedrive/farm.zip").unlink()
    Path("onedrive").rmdir()
    _z = _b.share_data()
    check("ist der Ordner weg, sagt die Seite es vorher",
          _z["folder"]["set"] is True and _z["folder"]["found"] is False)
    _z = _b.export_start({"parts": _all, "sequences": ["Farm"]})
    check("und der Export wird abgelehnt statt nach exports/ auszuweichen",
          _z["status"]["kind"] == "err" and not Path("exports/farm.zip").exists())

    _z = _b.share_folder_set({"path": ""})
    check("leer heisst: zurück auf exports/",
          _z["folder"]["set"] is False and _CONFIG.share_folder == "")

    check("die Seite ruft beide Ordner-Befehle",
          'callShare("share_folder_choose")' in _web
          and 'callShare("share_folder_set"' in _web)
    check("und liest über den Pfad aus der Liste ein, nicht über exports/ + Name",
          'path: e.path' in _web and '"exports/" + e.name' not in _web)
finally:
    _apply(_CONFIG, _AC.from_dict(_snapshot))
    _os.chdir(_cwd)
