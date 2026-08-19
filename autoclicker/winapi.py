"""Kompatible Fassade für die plattformspezifischen Systemfunktionen.

Der historische Modulname bleibt bestehen, damit Fachlogik und Editoren keine
Betriebssystemauswahl enthalten. Neue Systemaufrufe gehören in ein Backend.
"""

from .platforms import load_backend
from .platforms.base import BACKEND_FUNCTIONS
from .platforms.common import KEY_NAMES
from .platforms.common import *  # noqa: F401,F403 - öffentliche Konstanten

_backend = load_backend()

# Übergangsname für ältere Erweiterungen. Unter Windows bleiben die bisherigen
# numerischen Werte erhalten; plattformneutrale Fachlogik verwendet KEY_NAMES.
VK_CODES = getattr(_backend, "VK_CODES", {name: name for name in KEY_NAMES})

_fehlend = [name for name in BACKEND_FUNCTIONS if not hasattr(_backend, name)]
if _fehlend:
    raise ImportError(
        f"Plattform-Backend {_backend.__name__} ist unvollständig: "
        + ", ".join(_fehlend))

globals().update({name: getattr(_backend, name) for name in BACKEND_FUNCTIONS})
