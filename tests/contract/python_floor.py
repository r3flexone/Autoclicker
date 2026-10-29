"""Die untere Python-Grenze steht an drei Stellen — und muss dort gleich sein.

Die CI prüfte auf 3.10, benutzt wurde 3.14. Ein f-String, dessen `{…}` über
zwei Zeilen lief (erst ab 3.12 erlaubt), hielt die CI deshalb vier Läufe lang
rot, während jeder lokale Lauf grün war. Die Grenze ist seither die Version,
die wirklich benutzt wird; README und `tests.yml` nennen sie beide, und dieser
Test hält sie zusammen — sonst liefe die eine bei der nächsten Anhebung der
anderen davon.

Die dritte Stelle ist `start.bat`: es sucht und installiert genau diese
Version. Liefe es davon, bekäme ein neuer PC ein Python, gegen das nie
getestet wurde — und niemand sähe es, weil der eigene PC längst eingerichtet ist.
"""
import re
import sys

from ._harness import REPO, check, section

# =============================================================================
section("Python-Untergrenze: README, CI und start.bat nennen dieselbe Version")
# =============================================================================
_readme = (REPO / "README.md").read_text(encoding="utf-8")
_workflow = (REPO / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
_floor = re.search(r"^- Python (\d+\.\d+)\+$", _readme, re.MULTILINE)
_ci = re.findall(r'python-version:\s*"(\d+\.\d+)"', _workflow)
check("die README nennt eine Untergrenze", _floor is not None)
check("jeder CI-Job prüft genau auf dieser Untergrenze",
      bool(_ci) and _floor is not None and set(_ci) == {_floor.group(1)})
_bat = (REPO / "start.bat").read_text(encoding="utf-8", errors="replace")
_bat_version = re.findall(r'^set "PY_VERSION=(\d+\.\d+)"$', _bat, re.MULTILINE)
check("start.bat sucht und installiert genau diese Version",
      _floor is not None and _bat_version == [_floor.group(1)])
if _floor is not None:
    _need = tuple(int(n) for n in _floor.group(1).split("."))
    check(f"und dieser Lauf erfüllt sie (Python {sys.version.split()[0]})",
          sys.version_info[:2] >= _need)
