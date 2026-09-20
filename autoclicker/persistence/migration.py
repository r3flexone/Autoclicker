"""Schema-Migration für die JSON-Dateien — heute nur noch die Mechanik.

Der Code soll nur das AKTUELLE Schema lesen; alles Alte wird genau hier
hochgehoben, statt in jedem Loader eine weitere `get(alter_key, default)`-
Zeile anzuhängen.

Jede versionierte Datei trägt ein Feld `schema_version` (fehlt es: Version 0).
Pro Dateityp gibt es eine Kette von Schritten — Eintrag i hebt von i auf i+1.
Gespeichert wird immer im aktuellen Schema; `tools/migrate.py` erledigt den
Rest in einem Rutsch.

**Das Modul ist geschrumpft, und das ist der Zielzustand.** Vier Schritte
hoben die Sequenzen auf Schema 4 und sind mit ihrem Altbestand gelöscht. Die
Normalisierer für Dateien ohne Versionsfeld (`points.json`, `items.json`,
`slots.json`) hoben Dateien, die es seit dem Umzug auf Besitzeinheiten gar
nicht mehr gibt — sie sind ersatzlos weg, samt `KIND_POINTS`. Was bleibt:
Versionserkennung, Stempel und die Schleuse im Loader, denn die kostet nichts
und ist die Stelle, an der eine künftige Umstellung landet. Neue
Formatänderungen brauchen KEINEN Schritt mehr (Default in der Dataclass,
`data.get(key, default)` im Loader); `SCHEMA_VERSION` nie zurückdrehen.
"""

from __future__ import annotations

from typing import Callable, Optional

# Aktuelles Schema. Bei jeder Änderung, die alte Dateien unlesbar macht:
# hochzählen UND einen Schritt in die passende Kette eintragen.
SCHEMA_VERSION = 4

VERSION_KEY = "schema_version"

# Dateitypen. Versioniert (mit `schema_version` in der Datei) ist nur, was ein
# Dict als obersten Knoten hat und eine Kette in `_CHAINS` besitzt — heute die
# Sequenz. Die uebrigen tragen kein Versionsfeld: `migrate()` laesst sie, wie
# sie sind. Die Konstanten bleiben, weil `sweep.py` und die Loader ihren Typ
# beim Aufruf nennen — so faellt ein neuer Dateityp auf, statt still durchzugehen.
KIND_SEQUENCE = "sequence"            # sequences/<name>/sequence.json   versioniert
KIND_ITEMS = "items"                  # presets/items/*.json
KIND_ITEM_SCAN = "item_scan"          # sequences/<name>/item_scans/*.json
KIND_SLOTS = "slots"                  # presets/slots/*.json
KIND_BOSS_SCAN = "boss_scan"          # sequences/<name>/boss_scans/*.json
KIND_ICON_SCAN = "icon_scan"          # sequences/<name>/icon_scans/*.json
KIND_GLOBAL_BOSSES = "global_bosses"  # sequences/<name>/boss_scans/bibliothek.json

# Ergebnis eines Migrationsschritts: (Daten, Meldungen)
MigrationStep = Callable[[dict, dict], list[str]]


def file_version(data) -> int:
    """Version einer geladenen Datei. Ohne Feld: 0 (vor der Versionierung).

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


# Alle Dateitypen — `sweep.py` und die Tests halten die Loader dagegen.
ALL_KINDS = (KIND_SEQUENCE, KIND_ITEMS, KIND_ITEM_SCAN,
             KIND_SLOTS, KIND_BOSS_SCAN, KIND_ICON_SCAN, KIND_GLOBAL_BOSSES)

# Versionierte Typen und ihre Ketten. Die Sequenz-Kette ist LEER: ihre vier
# Schritte sind gelaufen und geloescht. Der Eintrag bleibt, damit die Schleuse
# sitzt, wenn die naechste Umstellung kommt.
_CHAINS: dict[str, list[MigrationStep]] = {
    KIND_SEQUENCE: [],
}


def migrate(data, kind: str, context: Optional[dict] = None) -> tuple:
    """Hebt geladene Daten auf den aktuellen Stand.

    Gibt (Daten, Meldungen) zurück; leere Meldungen = war schon aktuell. Die
    Daten werden in-place verändert und zusätzlich zurückgegeben.

    Versionierte Typen laufen ihre Kette ab und bekommen den Versions-Stempel;
    alle anderen kommen unangetastet zurueck.
    """
    context = context or {}
    if kind not in _CHAINS or not isinstance(data, dict):
        return data, []

    chain = _CHAINS[kind]
    version = file_version(data)
    messages = []

    if version > SCHEMA_VERSION:
        # Datei aus einer neueren Version - nicht herunterrechnen, nur warnen.
        return data, [f"Datei hat Schema {version}, dieser Code kennt nur {SCHEMA_VERSION} "
                      "- unbekannte Felder bleiben unangetastet"]

    while version < SCHEMA_VERSION:
        if version >= len(chain):
            # Kein Schritt hinterlegt: Version anheben, nichts zu tun.
            version += 1
            continue
        messages.extend(chain[version](data, context))
        version += 1

    data[VERSION_KEY] = SCHEMA_VERSION
    return data, messages


def needs_migration(data: dict) -> bool:
    return file_version(data) < SCHEMA_VERSION


def stamp(data: dict) -> dict:
    """Setzt die aktuelle Schema-Version - beim Speichern aufrufen, damit frisch
    geschriebene Dateien nie erneut durch die Migration müssen."""
    data[VERSION_KEY] = SCHEMA_VERSION
    return data
