"""Der Reiter „Teilen": ein Bündel schreiben und eines einlesen.

Import/Export lagen nur in der Konsole. Die Logik (`import_export.py`) bleibt
dieselbe — geprüft wird, was die Brücke daraus macht: der Bestand kommt von
Platte, nicht aus dem Fenster.
"""
import os as _os
import re
import tempfile
from pathlib import Path

from ._harness import check, section, studio_web_source
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.editors.sequence_studio.bridge_share import PARTS as _TEILE
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
_missing = [k for k, _ in _TEILE
            if f"include_{k}" not in _export_args or f"import_{k}" not in _import_args]
check("jeder anhakbare Teil hat sein Argument auf beiden Seiten", _missing == [])
if _missing:
    print("        ohne Argument: " + ", ".join(_missing))

check("die Seite hat einen Reiter dafuer", 'data-view="share"' in _web)
check("und ruft die Bruecke ueber einen eigenen Kanal", "callShare(" in _web)
_called = sorted(set(re.findall(r'callShare\("([a-z_]+)"', _web)))
_without = [n for n in _called if not callable(getattr(_SB, n, None))]
check("jeden gerufenen Namen gibt es in der Bruecke", _without == [])

_sandbox = tempfile.mkdtemp(prefix="teilen_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    Path("sequences").mkdir()
    from autoclicker.persistence import (
        list_available_sequences, save_data, save_item_scan,
    )
    _st = _ST()
    _seq = _SEQ(name="Farm", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1, delay_before=3.0), _STEP(point_id=2)])],
        points=[_CP(id=1, x=100, y=100, name="A"),
                _CP(id=2, x=200, y=200, name="B")])
    _st.sequences["Farm"] = _seq
    _st.active_sequence = _seq
    _st.points = _seq.points
    save_data(_st)
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

    _z = _b.export_start({"parts": {k: True for k, _ in _TEILE}, "name": "probe"})
    check("das Buendel steht auf Platte", Path("exports/probe.zip").exists())
    check("und in der Liste", [e["name"] for e in _z["exports"]] == ["probe.zip"])
    _z = _b.export_start({"parts": {k: False for k, _ in _TEILE}})
    check("ohne Auswahl wird nichts geschrieben", _z["status"]["kind"] == "warn")

    _z = _b.import_check({"path": "gibtsnicht.zip"})
    check("eine fehlende Datei ist ein Fehler", _z["status"]["kind"] == "err")
    check("und nichts bleibt gewaehlt", _z["import"] is None)

    _z = _b.import_check({"path": "exports/probe.zip"})
    check("das Manifest sagt, was drin ist", _z["import"]["content"]["sequences"] == 1)
    # Ohne beidseitig bekanntes Spielfenster gibt es nichts umzurechnen.
    check("ohne Fenster keine automatische Umrechnung", _z["import"]["auto"] is False)

    _z = _b.import_start({"parts": {k: True for k, _ in _TEILE},
                            "mode": "identity", "merge": True})
    check("der Import laeuft durch", _z["status"]["kind"] == "ok")
    check("und das Fenster liest danach neu", len(_b.points) >= 2)

    # **Der Import schreibt auf Platte, nicht nur in den Speicher.**
    _b2 = _SB(_seq, _farm_path, "sequences")
    check("ein frisches Studio sieht dasselbe",
          _b2.share_data()["inventory"]["sequences"] >= 1)
finally:
    _os.chdir(_cwd)
