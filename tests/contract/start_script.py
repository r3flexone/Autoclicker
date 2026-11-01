"""`start.bat` und `requirements.txt` — der Doppelklick-Start für Windows.

Was hier schiefgeht, fällt erst beim Doppelklick auf, auf einem fremden PC, wo
niemand nachsieht: der eigene ist längst eingerichtet und startet nie mehr den
Einrichtungsweg. Zwei Fallen sieht man der Batch-Datei nicht an:

- **Zeilenenden.** cmd findet Sprungmarken (`goto`, `call :marke`) in einer
  Batch-Datei mit reinen LF-Zeilenenden nicht zuverlässig. Das Repo legt sonst
  überall LF ab; `.gitattributes` macht für `*.bat` die Ausnahme, und nur
  dieser Test merkt, wenn ein Editor sie wieder auf LF schreibt.
- **Zeichensatz.** cmd liest eine Batch-Datei in der OEM-Codepage, ein
  UTF-8-„ü“ käme als Zeichensalat an. Dasselbe gilt für `requirements.txt`,
  die pip in der Codepage des Systems liest.

Die Version, die `start.bat` installiert, hält `python_floor.py` fest.
"""
import re
from unittest.mock import patch

from ._harness import REPO, check, section

# =============================================================================
section("start.bat: Zeilenenden und Zeichensatz, die cmd versteht")
# =============================================================================
_bat = (REPO / "start.bat").read_bytes()
check("start.bat hat Zeilen", _bat.count(b"\n") > 20)
check("jede Zeile endet mit CRLF", _bat.count(b"\n") == _bat.count(b"\r\n"))
check("start.bat ist reines ASCII", _bat.isascii())
check("requirements.txt ist reines ASCII",
      (REPO / "requirements.txt").read_bytes().isascii())
check("start.bat installiert aus requirements.txt", b"-r requirements.txt" in _bat)

# =============================================================================
section("requirements.txt: die Linux-Pakete sind die, die der Start vermisst")
# =============================================================================
# Gefragt wird die Plattform-Schicht selbst, nicht eine abgeschriebene Liste:
# sie meldet beim Start jedes fehlende Paket mit `pip install <name>`. Fehlt
# eines davon in requirements.txt, richtet der Weg von Hand ein Linux ein, das
# beim ersten Start sagt, es fehle etwas.
from autoclicker.platforms import linux_x11                         # noqa: E402

with patch.object(linux_x11, "find_spec", return_value=None):
    _reported = {m.split("pip install ", 1)[1] for m in linux_x11.environment_warnings()
                 if "pip install " in m}


def _requirements():
    """Name -> Umgebungsmarke je Zeile, ohne Kommentare."""
    entries = {}
    for line in (REPO / "requirements.txt").read_text(encoding="ascii").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            name, _, marker = line.partition(";")
            entries[name.strip().lower()] = marker.strip()
    return entries


_entries = _requirements()
_linux_only = {name for name, marker in _entries.items()
               if re.fullmatch(r'sys_platform\s*==\s*"linux"', marker)}
check("die Plattform-Schicht meldet Pakete", len(_reported) >= 3)
check("jedes davon steht in requirements.txt, nur für Linux", _reported <= _linux_only)
check("und nichts steht dort nur für Linux, das sie nicht meldet", _linux_only <= _reported)
check("alles andere gilt auf jedem System",
      all(not marker for name, marker in _entries.items() if name not in _linux_only))
