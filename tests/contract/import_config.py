"""Import: die Config aus einem Bündel läuft durch dieselbe Prüfung wie die Datei.

`_import_sequence_bundle` schrieb jeden erlaubten Schlüssel per `setattr` in
das laufende Config-Objekt — ohne `__post_init__`, ohne Typprüfung. Ein
Bündel mit `pixel_check_interval: 0` oder einem Tippfehler in
`pixel_timeout_action` landete damit ungeprüft im Lauf; `config.json` von
Platte hätte beides korrigiert. Jetzt geht es über `AppConfig.from_dict`
und `apply_config` — hineingeschrieben, nicht getauscht.
"""
import contextlib as _cl
import io as _io
import json as _json
import os as _os
import shutil as _sh
import tempfile as _tmp
import zipfile as _zip

from ._harness import check, section
from autoclicker.models import AutoClickerState as _ST
from autoclicker.import_export import import_bundle, EXPORT_VERSION, MANIFEST_FILE
from autoclicker.config import CONFIG as _CONFIG, AppConfig as _AC, apply_config as _apply

section("Import: Config-Werte werden geprueft, nicht durchgereicht")

_sandbox = _tmp.mkdtemp(prefix="import_cfg_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
_snapshot = _CONFIG.to_dict()       # das Modul-CONFIG teilen sich alle Tests
try:
    _bundle = "b.zip"
    with _zip.ZipFile(_bundle, "w") as zf:
        zf.writestr(MANIFEST_FILE, _json.dumps({
            "version": EXPORT_VERSION, "layout": "sequence-folders",
            "reference_points": {"point1": [0, 0], "point2": [1, 1]},
            "contents": {"config": True}}))
        zf.writestr("config.json", _json.dumps({
            "pixel_check_interval": 0,            # __post_init__ hebt auf 0.1
            "pixel_timeout_action": "explodieren",  # ungueltig -> skip_cycle
            "click_per_point": 3,                 # gueltig, kommt an
            "failsafe_x": 999,                    # sensibel, bleibt draussen
            "erfunden": 1,                        # unbekannt, faellt weg
        }))
    _st = _ST()
    _st.config = _CONFIG                          # wie in main.py: EIN Objekt
    _before_failsafe = _st.config.failsafe_x
    with _cl.redirect_stdout(_io.StringIO()):
        _ok, _msg = import_bundle(_st, _bundle, import_sequences=False, import_config=True)
    check("der Import meldet Erfolg", _ok is True)
    check("ein gueltiger Wert kommt an", _st.config.click_per_point == 3)
    check("ein ungueltiger Wert wird korrigiert statt uebernommen",
          _st.config.pixel_check_interval == 0.1
          and _st.config.pixel_timeout_action == "skip_cycle")
    check("sensible Felder bleiben, wie sie waren", _st.config.failsafe_x == _before_failsafe)
    check("unbekannte Schluessel landen nicht am Objekt", not hasattr(_st.config, "erfunden"))
    check("das Config-Objekt ist dasselbe geblieben (kein Tausch)", _st.config is _CONFIG)
    _saved = _json.loads(open("config.json", encoding="utf-8").read())
    check("und die Datei traegt den geprueften Stand",
          _saved["click_per_point"] == 3 and _saved["pixel_check_interval"] == 0.1)
finally:
    with _cl.redirect_stdout(_io.StringIO()):
        _apply(_CONFIG, _AC.from_dict(_snapshot))
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)
