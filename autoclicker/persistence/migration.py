"""Schema-Migration für die JSON-Dateien.

Der Code soll nur das AKTUELLE Schema lesen; alles Alte wird genau hier
hochgehoben, statt in jedem Loader eine weitere `get(alter_key, default)`-
Zeile anzuhängen.

Jede Datei trägt ein Feld `schema_version` (fehlt es: Version 0). Pro
Dateityp gibt es eine Kette von Schritten — Eintrag i hebt von i auf i+1.
Gespeichert wird immer im aktuellen Schema; `tools/migrate.py` erledigt den
Rest in einem Rutsch.

**Das Modul soll schrumpfen.** Sind alle Dateien aktuell, ist der Schritt
tot und wird ersatzlos gelöscht — samt dem Alt-Code, den er ersetzt hat.
`SCHEMA_VERSION` dabei nie zurückdrehen: die Nummern bleiben eindeutig, es
fällt nur der Weg dorthin weg.
"""

from __future__ import annotations

from typing import Callable, Optional

# Aktuelles Schema. Bei jeder Änderung, die alte Dateien unlesbar oder unsauber macht:
# hochzählen UND einen Schritt in die passende Kette eintragen.
SCHEMA_VERSION = 4

VERSION_KEY = "schema_version"

# Dateitypen. Versioniert (mit `schema_version` in der Datei) ist nur, was ein Dict als
# obersten Knoten hat - der Rest laeuft ueber _NORMALIZER, s.u.
KIND_SEQUENCE = "sequence"          # sequences/<name>.json     versioniert
KIND_POINTS = "points"              # sequences/points.json     Liste
KIND_ITEMS = "items"                # items/items.json, items/presets/*.json
KIND_ITEM_SCAN = "item_scan"        # item_scans/<name>.json
KIND_SLOTS = "slots"                # slots/slots.json, slots/presets/*.json
KIND_BOSS_SCAN = "boss_scan"        # boss_scans/<name>.json
KIND_ICON_SCAN = "icon_scan"        # icon_scans/<name>.json
KIND_GLOBAL_BOSSES = "global_bosses"  # boss_scans/global/bosses.json

# Jeder Dateityp MUSS in _CHAINS oder _NORMALIZER stehen, auch wenn es (noch) nichts zu
# tun gibt - dann als _norm_noop. Sonst muesste man sich beim naechsten Formatwechsel
# daran erinnern, den Haken im Loader ueberhaupt erst einzubauen. Ein Test prueft das.

# Ergebnis eines Migrationsschritts: (Daten, Meldungen)
MigrationStep = Callable[[dict, dict], list[str]]


def file_version(data) -> int:
    """Version einer geladenen Datei. Ohne Feld: 0 (vor der Versionierung).

    Nimmt bewusst auch Nicht-Dicts entgegen: points.json ist eine Liste, items.json und
    slots.json sind Name->Eintrag-Dicts. Die tragen kein Versions-Feld (s. _NORMALIZER)
    und zaehlen deshalb als 0.
    """
    if not isinstance(data, dict):
        return 0
    try:
        return int(data.get(VERSION_KEY, 0))
    except (TypeError, ValueError):
        return 0


# Sequenzen: die Kette ist LEER - und das ist der Zielzustand.
# Hier standen vier Schritte (Schema 0 bis 4); es gibt keinen Altbestand mehr,
# den sie heben koennten. Was sie erledigt haben, damit niemand es erneut baut:
#   0 -> 1  drei konkurrierende Phasen-Formate auf `loop_phases` vereinheitlicht
#   1 -> 2  `delay_after` -> `delay_before`
#   2 -> 3  Aufnahmen des alten Recorders mit ihrem Punkt verknuepft
#   3 -> 4  jede Koordinate aus der Sequenz nach points.json gezogen
# SCHEMA_VERSION bleibt auf 4: eine aeltere Datei wird auf 4 gestempelt und sonst
# gelesen, wie sie dasteht (fehlende Felder bekommen ihren Standardwert). Fuer eine
# sehr alte Sicherung ist der Weg `git show <commit>:.../migration.py` oder die
# Sequenz im Studio neu zu bauen.


# Dateitypen OHNE Versions-Feld: points.json ist eine Liste, items.json/slots.json
# und die Presets sind Name->Eintrag-Dicts - ein Key "schema_version" waere dort ein
# Fremdkoerper. Statt einer Kette bekommen sie einen NORMALISIERER: idempotent, also
# beliebig oft laufbar, und ebenso geloescht, sobald es keine Altbestaende mehr gibt.

# `_norm_items` ist ersatzlos entfallen. Es hob `confirm_point` von [x, y] auf
# {"x":.., "y":..} - ein Feld, das der Loader seit der Umstellung auf Punkt-Referenzen
# gar nicht mehr liest. Einen Normalisierer zu pflegen, der ein totes Feld in ein
# anderes totes Format bringt, ist genau das Anwachsen, das dieses Modul vermeiden
# soll. Ein altes confirm_point meldet jetzt der Loader (`_alt_gemeldet`), und der
# Bestaetigungs-Punkt wird einmal neu gesetzt.


def _norm_item_scan(data, context: dict) -> list[str]:
    """Kein Altformat-Umbau: ein Scan enthält heute seine Slots und Items."""
    return []


# Felder, die ein Punkt haben darf. Alles andere ist Altbestand und fliegt raus -
# _point_to_dict schreibt ohnehin nur diese.
_POINT_KEYS = ("id", "x", "y", "name", "color", "source")


def _norm_points(data, context: dict) -> list[str]:
    """points.json - Liste von Punkten.

    Faengt zwei Altlasten ab: fehlende IDs (frueher zaehlte die Position) und Felder,
    die es nicht mehr gibt. Damit darf load_points die ID als gesetzt voraussetzen.
    """
    if not isinstance(data, list):
        return []
    meldungen = []
    ohne_id = [p for p in data if isinstance(p, dict) and p.get("id") is None]
    if ohne_id:
        vergeben = {p["id"] for p in data if isinstance(p, dict) and p.get("id") is not None}
        naechste = 1
        for p in ohne_id:
            while naechste in vergeben:
                naechste += 1
            p["id"] = naechste
            vergeben.add(naechste)
        meldungen.append(f"{len(ohne_id)} Punkt(e) ohne ID nachtraeglich nummeriert")

    entfernt = set()
    for p in data:
        if not isinstance(p, dict):
            continue
        for key in [k for k in p if k not in _POINT_KEYS]:
            del p[key]
            entfernt.add(key)
    if entfernt:
        meldungen.append(f"tote Punkt-Felder entfernt: {', '.join(sorted(entfernt))}")
    return meldungen


def _norm_noop(data, context: dict) -> list[str]:
    """Kein Altbestand - aber der Haken sitzt.

    Diese Typen haben heute nichts zu heben; der Eintrag steht trotzdem hier,
    damit eine spaetere Formataenderung genau eine Funktion kostet statt
    zusaetzlich der Frage, wo der Aufruf ueberhaupt hingehoert.
    """
    return []


_NORMALIZER: dict[str, MigrationStep] = {
    KIND_POINTS: _norm_points,
    KIND_ITEMS: _norm_noop,
    KIND_ITEM_SCAN: _norm_item_scan,
    KIND_SLOTS: _norm_noop,
    KIND_BOSS_SCAN: _norm_noop,
    KIND_ICON_SCAN: _norm_noop,
    KIND_GLOBAL_BOSSES: _norm_noop,
}

# Alle bekannten Dateitypen - fuer den Test, dass keiner ohne Schleuse dasteht.
ALL_KINDS = (KIND_SEQUENCE, KIND_POINTS, KIND_ITEMS, KIND_ITEM_SCAN,
             KIND_SLOTS, KIND_BOSS_SCAN, KIND_ICON_SCAN, KIND_GLOBAL_BOSSES)


# ---------------------------------------------------------------------------
# Migrations-Ketten je Dateityp
# ---------------------------------------------------------------------------

# Eintrag i hebt von Version i auf i+1. Die Sequenz-Kette ist leer, der Eintrag
# bleibt: der Schluessel sagt "dieser Dateityp ist versioniert", und daran haengt
# der Test, dass kein Dateityp ohne Schleuse dasteht.
_CHAINS: dict[str, list[MigrationStep]] = {
    KIND_SEQUENCE: [],
}


def migrate(data, kind: str, context: Optional[dict] = None) -> tuple:
    """Hebt geladene Daten auf den aktuellen Stand.

    Gibt (Daten, Meldungen) zurück; leere Meldungen = war schon aktuell. Die
    Daten werden in-place verändert und zusätzlich zurückgegeben.

    Versionierte Typen laufen ihre Kette ab und bekommen den Versions-Stempel,
    unversionierte (Liste/Name-Dict) laufen durch ihren Normalisierer.
    """
    context = context or {}

    if kind in _NORMALIZER:
        return data, _NORMALIZER[kind](data, context)

    if not isinstance(data, dict):
        return data, []

    kette = _CHAINS.get(kind, [])
    version = file_version(data)
    meldungen = []

    if version > SCHEMA_VERSION:
        # Datei aus einer neueren Version - nicht herunterrechnen, nur warnen.
        return data, [f"Datei hat Schema {version}, dieser Code kennt nur {SCHEMA_VERSION} "
                      "- unbekannte Felder bleiben unangetastet"]

    while version < SCHEMA_VERSION:
        if version >= len(kette):
            # Kein Schritt hinterlegt: Version anheben, nichts zu tun.
            version += 1
            continue
        meldungen.extend(kette[version](data, context))
        version += 1

    data[VERSION_KEY] = SCHEMA_VERSION
    return data, meldungen


def needs_migration(data: dict) -> bool:
    return file_version(data) < SCHEMA_VERSION


def stamp(data: dict) -> dict:
    """Setzt die aktuelle Schema-Version - beim Speichern aufrufen, damit frisch
    geschriebene Dateien nie erneut durch die Migration müssen."""
    data[VERSION_KEY] = SCHEMA_VERSION
    return data
