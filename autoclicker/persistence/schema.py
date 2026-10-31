"""Schema-Version der gespeicherten Dateien: der Stempel und die Erkennung einer neueren Fassung.

Eine Umrechnung alter Dateien gibt es nicht mehr. Hier standen eine Kette von
Schritten (Eintrag i hob von Version i auf i+1), ein Dateityp pro Loader und
`migrate()` als Schleuse in jedem von ihnen. Vier Schritte hoben die Sequenzen auf
Schema 4 und sind mit ihrem Altbestand gelöscht; die leere Schleuse blieb "für die
nächste Umstellung" stehen und ist zuletzt auch gegangen, denn neue Formatänderungen
brauchen ausdrücklich KEINEN Schritt: Default in der Dataclass, `data.get(key,
default)` im Loader. Eine ältere Datei wird gelesen wie jede andere; was der Loader
nicht kennt, schreibt der Serializer beim nächsten Speichern nicht zurück.

Was bleibt, ist das, was kein Loader ersetzen kann:

* `stamp()` — jede gespeicherte Sequenz trägt `schema_version`.
* `from_newer_version()` — eine Datei aus einer **neueren** Fassung des Programms
  (Schema über `SCHEMA_VERSION`). Sie wird gelesen, aber der Start-Durchgang
  (`sweep.py`) schreibt sie nicht zurück: der Round-Trip durch Loader und
  Serializer liesse alles fallen, was nur die neuere Fassung kennt, und stempelte
  ein niedrigeres Schema darüber.

`SCHEMA_VERSION` wird nur hochgezählt, wenn eine ältere Fassung die Datei nicht mehr
anfassen soll; zurückgedreht wird sie nie.
"""

from __future__ import annotations

SCHEMA_VERSION = 4

VERSION_KEY = "schema_version"


def file_version(data) -> int:
    """Version einer geladenen Datei. Ohne Feld: 0.

    Nimmt bewusst auch Nicht-Dicts entgegen: die Boss-Bibliothek ist eine Liste,
    Presets sind Name->Eintrag-Dicts. Die tragen kein Versions-Feld und
    zaehlen deshalb als 0.
    """
    if not isinstance(data, dict):
        return 0
    try:
        return int(data.get(VERSION_KEY, 0))
    except (TypeError, ValueError):
        return 0


def from_newer_version(data) -> bool:
    """Stammt die Datei aus einer neueren Fassung des Programms als dieser?"""
    return file_version(data) > SCHEMA_VERSION


def stamp(data: dict) -> dict:
    """Setzt die aktuelle Schema-Version - beim Speichern aufrufen."""
    data[VERSION_KEY] = SCHEMA_VERSION
    return data
