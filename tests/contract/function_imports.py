"""Jeder Import in einer Funktion zeigt auf etwas, das es gibt.

**Ein Import im Funktionsrumpf wird erst beim Aufruf ausgewertet** — und
genau dort sieht ihn weder flake8 (pyflakes löst keine Modul-Attribute auf)
noch der Test „Jedes Modul ist importierbar" (der importiert nur Module). Als
`diagnostics._virtueller_desktop` beim Eingrenzen der Windows-Abhängigkeiten
durch `winapi.get_virtual_desktop()` ersetzt wurde, blieb in
`import_export_editor._outside_all_monitors` der alte Name stehen: die
Konsolen-Kalibrierung (`fix`) und das Weitergeben des Versatzes nach `repair`
warfen seither `ImportError`, sobald sie die Vorschau zeigen wollten.

Geprüft werden nur Importe aus `autoclicker` selbst — ob ein Fremdpaket
(OpenCV, EasyOCR, Playwright) installiert ist, ist eine Frage der Umgebung,
nicht des Codes.
"""
import ast as _ast
import importlib as _importlib

from ._harness import REPO, check, section

section("Jeder Import in einer Funktion zeigt auf etwas, das es gibt")


def _module_name(path) -> str:
    rel = path.relative_to(REPO).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve(node: _ast.ImportFrom, module: str, is_package: bool) -> str:
    if not node.level:
        return node.module or ""
    base = module.split(".")
    if not is_package:
        base = base[:-1]
    base = base[:len(base) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


_missing = []
_checked = 0
_sources = (sorted((REPO / "autoclicker").rglob("*.py")) + sorted((REPO / "tools").glob("*.py"))
            + [REPO / "main.py"])
for _path in _sources:
    _module = _module_name(_path)
    _tree = _ast.parse(_path.read_text(encoding="utf-8"))
    for _func in _ast.walk(_tree):
        if not isinstance(_func, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            continue
        for _node in _ast.walk(_func):
            if not isinstance(_node, _ast.ImportFrom):
                continue
            _target = _resolve(_node, _module, _path.name == "__init__.py")
            if not _target.startswith("autoclicker"):
                continue
            try:
                _imported = _importlib.import_module(_target)
            except ImportError as _e:
                _missing.append(f"{_module}.{_func.name}: Modul {_target} ({_e})")
                continue
            for _alias in _node.names:
                _checked += 1
                if _alias.name == "*" or hasattr(_imported, _alias.name):
                    continue
                try:
                    _importlib.import_module(f"{_target}.{_alias.name}")
                except ImportError:
                    _missing.append(f"{_module}.{_func.name}: {_target}.{_alias.name}")

check("der Test findet überhaupt Importe in Funktionen", _checked > 50)
check("jeder davon zeigt auf einen Namen, den es gibt", _missing == [])
for _entry in _missing:
    print(f"        fehlt: {_entry}")

# Und die eine Stelle, an der es aufgefallen ist, rechnet wieder.
from autoclicker.editors import import_export_editor as _IEE

_old = _IEE.get_virtual_desktop
try:
    _IEE.get_virtual_desktop = lambda: (0, 0, 100, 100)
    check("ausserhalb aller Monitore wird gezählt",
          _IEE._outside_all_monitors([(5, 5), (150, 5), (5, -1), (99, 99)]) == 2)
    _IEE.get_virtual_desktop = lambda: None
    check("ohne bekannten Desktop zählt nichts als ausserhalb",
          _IEE._outside_all_monitors([(5000, 5000)]) == 0)
finally:
    _IEE.get_virtual_desktop = _old
