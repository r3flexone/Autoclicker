"""Auswahl des Backends ohne Betriebssystem-Code im Rest der Anwendung."""

from importlib import import_module
import sys


def load_backend():
    if sys.platform == "win32":
        return import_module(".windows", __name__)
    if sys.platform.startswith("linux"):
        return import_module(".linux_x11", __name__)
    raise RuntimeError(f"Nicht unterstütztes Betriebssystem: {sys.platform}")
