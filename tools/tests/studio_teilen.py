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
from autoclicker.editors.sequence_studio.bridge_teilen import TEILE as _TEILE
from autoclicker.models import (
    AutoClickerState as _ST, ClickPoint as _CP, LoopPhase as _PHASE,
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
_fehlend = [k for k, _ in _TEILE
            if f"include_{k}" not in _export_args or f"import_{k}" not in _import_args]
check("jeder anhakbare Teil hat sein Argument auf beiden Seiten", _fehlend == [])
if _fehlend:
    print("        ohne Argument: " + ", ".join(_fehlend))

check("die Seite hat einen Reiter dafuer", 'data-ansicht="teilen"' in _web)
check("und ruft die Bruecke ueber einen eigenen Kanal", "rufTeilen(" in _web)
_gerufen = sorted(set(re.findall(r'rufTeilen\("([a-z_]+)"', _web)))
_ohne = [n for n in _gerufen if not callable(getattr(_SB, n, None))]
check("jeden gerufenen Namen gibt es in der Bruecke", _ohne == [])

_sand = tempfile.mkdtemp(prefix="teilen_")
_cwd = _os.getcwd()
_os.chdir(_sand)
try:
    for _d in ("sequences", "item_scans", "boss_scans", "icon_scans", "slots"):
        Path(_d).mkdir()
    Path("items/templates").mkdir(parents=True)
    from autoclicker.persistence import save_data, save_points
    _st = _ST()
    _st.points = [_CP(id=1, x=100, y=100, name="A"), _CP(id=2, x=200, y=200, name="B")]
    save_points(_st)
    _seq = _SEQ(name="Farm", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1, delay_before=3.0), _STEP(point_id=2)])])
    _st.sequences["Farm"] = _seq
    _st.active_sequence = _seq
    save_data(_st)

    _b = _SB(_seq, Path("sequences/Farm.json"), "sequences")
    _z = _b.teilen_daten()
    # **Gezaehlt wird, was auf Platte liegt** — exportiert wird derselbe Stand.
    check("der Bestand kommt von Platte",
          _z["bestand"]["points"] == 2 and _z["bestand"]["sequences"] == 1)
    check("noch kein Buendel da", _z["exporte"] == [])
    check("und nichts gewaehlt", _z["import"] is None)

    _z = _b.export_starten({"teile": {k: True for k, _ in _TEILE}, "name": "probe"})
    check("das Buendel steht auf Platte", Path("exports/probe.zip").exists())
    check("und in der Liste", [e["name"] for e in _z["exporte"]] == ["probe.zip"])
    _z = _b.export_starten({"teile": {k: False for k, _ in _TEILE}})
    check("ohne Auswahl wird nichts geschrieben", _z["status"]["art"] == "warn")

    _z = _b.import_pruefen({"pfad": "gibtsnicht.zip"})
    check("eine fehlende Datei ist ein Fehler", _z["status"]["art"] == "err")
    check("und nichts bleibt gewaehlt", _z["import"] is None)

    _z = _b.import_pruefen({"pfad": "exports/probe.zip"})
    check("das Manifest sagt, was drin ist", _z["import"]["inhalt"]["points"] == 2)
    # Ohne beidseitig bekanntes Spielfenster gibt es nichts umzurechnen.
    check("ohne Fenster keine automatische Umrechnung", _z["import"]["auto"] is False)

    _z = _b.import_starten({"teile": {k: True for k, _ in _TEILE},
                            "modus": "identity", "merge": True})
    check("der Import laeuft durch", _z["status"]["art"] == "ok")
    check("und das Fenster liest danach neu", len(_b.points) >= 2)

    # **Der Import schreibt auf Platte, nicht nur in den Speicher.**
    _b2 = _SB(_seq, Path("sequences/Farm.json"), "sequences")
    check("ein frisches Studio sieht dasselbe",
          _b2.teilen_daten()["bestand"]["sequences"] >= 1)
finally:
    _os.chdir(_cwd)
