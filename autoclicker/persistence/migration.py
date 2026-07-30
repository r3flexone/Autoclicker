"""Schema-Migration für die JSON-Dateien.

Zweck: der Code soll das AKTUELLE Schema lesen dürfen - und nur das. Alles Alte wird
genau hier abgefangen und hochgehoben, statt in jedem Loader eine weitere
`data.get(alter_key, default)`-Zeile anzuhängen. Sonst wird jede Umstellung teurer als
die vorige, bis niemand mehr etwas anfassen will.

So funktioniert es
------------------
Jede Datei trägt ein Feld `schema_version`. Fehlt es, gilt Version 0 ("alles, was vor
der Versionierung entstanden ist"). Pro Dateityp gibt es eine Kette von Schritten:
Eintrag i hebt von Version i auf i+1. `migrate()` läuft die Kette ab und protokolliert
jede Änderung im Klartext.

Gespeichert wird IMMER im aktuellen Schema. Eine Sequenz, die du einmal bearbeitest und
speicherst, ist damit automatisch sauber; `tools/migrate.py` erledigt den Rest in einem
Rutsch.

Das Ziel ist, dass dieses Modul schrumpft
-----------------------------------------
Sind alle Dateien auf der aktuellen Version, ist der zugehörige Migrationsschritt tot
und kann ersatzlos gelöscht werden - zusammen mit dem Alt-Code, den er ersetzt hat.
Genau dafür ist es da: nicht als wachsende Sammlung von Sonderfällen, sondern als
Schleuse, durch die Altlasten einmal durchgehen und danach verschwunden sind.

Beim Löschen eines Schritts SCHEMA_VERSION nicht zurückdrehen - die Nummern bleiben
eindeutig, es fällt nur der Weg dorthin weg.
"""

from __future__ import annotations

from typing import Callable, Optional

# Aktuelles Schema. Bei jeder Änderung, die alte Dateien unlesbar oder unsauber macht:
# hochzählen UND einen Schritt in die passende Kette eintragen.
SCHEMA_VERSION = 1

VERSION_KEY = "schema_version"

# Dateitypen
KIND_SEQUENCE = "sequence"
KIND_POINTS = "points"

# Ergebnis eines Migrationsschritts: (Daten, Meldungen)
MigrationStep = Callable[[dict, dict], list[str]]


def file_version(data: dict) -> int:
    """Version einer geladenen Datei. Ohne Feld: 0 (vor der Versionierung)."""
    try:
        return int(data.get(VERSION_KEY, 0))
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Sequenzen: Version 0 -> 1
# ---------------------------------------------------------------------------

def _seq_v0_to_v1(data: dict, context: dict) -> list[str]:
    """Hebt eine Sequenz auf Schema 1.

    Erledigt drei Altlasten auf einmal:

    1. Drei konkurrierende Phasen-Formate werden zu `loop_phases` vereinheitlicht.
       Vorher musste der Loader alle drei kennen.
    2. Schritte bekommen `point_id`, wo sich der Punkt eindeutig über die Koordinaten
       zuordnen lässt - damit folgen sie ab sofort dem Punkte-Pool statt eine tote
       Kopie zu sein. Mehrdeutige Fälle bleiben bewusst unverknüpft.
    3. Tote Felder fliegen raus (siehe _DEAD_STEP_KEYS).

    `context` liefert optional die Punkte: {"points": [{"id","x","y","name"}, ...]}
    """
    meldungen = []

    # --- 1. Phasen vereinheitlichen -------------------------------------------------
    if "loop_phases" not in data:
        if "loop_steps" in data:
            data["loop_phases"] = [{
                "name": "Loop",
                "repeat": data.pop("max_loops", 1) or 1,
                "steps": data.pop("loop_steps"),
            }]
            meldungen.append("loop_steps + max_loops -> loop_phases")
        elif "steps" in data:
            data["loop_phases"] = [{
                "name": "Loop", "repeat": 1, "steps": data.pop("steps"),
            }]
            meldungen.append("steps (uraltes Format) -> loop_phases")
        else:
            data["loop_phases"] = []

    # start_steps war eine eigene Phase vor den Loops
    alt_start = data.pop("start_steps", None)
    if alt_start:
        data["loop_phases"].insert(0, {"name": "Start", "repeat": 1, "steps": alt_start})
        meldungen.append("start_steps -> eigene Loop-Phase 'Start'")

    data.setdefault("init_steps", [])
    data.setdefault("end_steps", [])

    # max_loops kann auch neben loop_phases herumliegen - dann ist es bedeutungslos
    if data.pop("max_loops", None) is not None:
        meldungen.append("max_loops entfernt (wird von loop_phases[].repeat abgelöst)")

    # --- 2./3. Schritte durchgehen ---------------------------------------------------
    punkte = context.get("points") or []
    nach_pos = {}
    for p in punkte:
        try:
            nach_pos.setdefault((int(p["x"]), int(p["y"])), []).append(p)
        except (KeyError, TypeError, ValueError):
            continue

    verknuepft = 0
    entfernt = set()
    for phase_name, steps in _iter_step_lists(data):
        for step in steps:
            verknuepft += _link_step_to_point(step, nach_pos)
            entfernt |= _drop_dead_keys(step)

    if verknuepft:
        meldungen.append(f"{verknuepft} Schritt(e) mit ihrem Punkt verknüpft (point_id)")
    if entfernt:
        meldungen.append(f"tote Felder entfernt: {', '.join(sorted(entfernt))}")

    return meldungen


# Felder, die früher geschrieben, aber nie (mehr) gelesen werden. Beim Entfernen eines
# Feldes aus dem Code gehört sein Name hierher - dann räumt die Migration ihn weg,
# statt ihn ewig in jeder Datei mitzuschleppen.
_DEAD_STEP_KEYS = (
    "clicks",           # Vorläufer von click_per_point (Config)
    "point_index",      # Positions-Index vor der stabilen point_id
    "use_pixel_wait",   # implizit durch wait_pixel/wait_color
)


def _iter_step_lists(data: dict):
    """Alle Schritt-Listen einer Sequenz mit Phasennamen."""
    yield "INIT", data.get("init_steps") or []
    for lp in data.get("loop_phases") or []:
        yield lp.get("name", "LOOP"), lp.get("steps") or []
    yield "END", data.get("end_steps") or []


def _link_step_to_point(step: dict, nach_pos: dict) -> int:
    """Setzt point_id, wenn genau ein Punkt auf denselben Koordinaten liegt.

    Mehrdeutige Stellen (zwei Punkte übereinander) bleiben unverknüpft - lieber keine
    Referenz als stillschweigend die falsche.
    """
    if step.get("point_id") is not None:
        return 0
    # Schritte ohne echte Position haben keinen Punkt
    if (step.get("key_press") or step.get("item_scan") or step.get("boss_scan")
            or step.get("boss_watcher") or step.get("icon_scan")
            or step.get("screenshot_only") or step.get("wait_only")):
        return 0
    try:
        pos = (int(step.get("x")), int(step.get("y")))
    except (TypeError, ValueError):
        return 0
    treffer = nach_pos.get(pos, [])
    if len(treffer) != 1:
        return 0
    step["point_id"] = treffer[0].get("id")
    return 1


def _drop_dead_keys(step: dict) -> set:
    entfernt = set()
    for key in _DEAD_STEP_KEYS:
        if key in step:
            del step[key]
            entfernt.add(key)
    return entfernt


# ---------------------------------------------------------------------------
# Migrations-Ketten je Dateityp
# ---------------------------------------------------------------------------

# Eintrag i hebt von Version i auf i+1.
_CHAINS: dict[str, list[MigrationStep]] = {
    KIND_SEQUENCE: [_seq_v0_to_v1],
    KIND_POINTS: [],          # points.json ist bereits sauber - Kette bleibt leer
}


def migrate(data: dict, kind: str, context: Optional[dict] = None) -> tuple[dict, list[str]]:
    """Hebt ein geladenes dict auf SCHEMA_VERSION.

    Gibt (Daten, Meldungen) zurück. Leere Meldungen = war schon aktuell. Das dict wird
    in-place verändert und zusätzlich zurückgegeben, damit sich beides aufrufen lässt.
    """
    if not isinstance(data, dict):
        return data, []

    context = context or {}
    kette = _CHAINS.get(kind, [])
    version = file_version(data)
    meldungen = []

    if version > SCHEMA_VERSION:
        # Datei aus einer neueren Version - nicht herunterrechnen, nur warnen.
        return data, [f"Datei hat Schema {version}, dieser Code kennt nur {SCHEMA_VERSION} "
                      f"- unbekannte Felder bleiben unangetastet"]

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
