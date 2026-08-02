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
SCHEMA_VERSION = 3

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
    # Punkt ohne ID taugt nicht als Referenz - sonst landet `"point_id": null` im
    # Schritt und wird beim naechsten Lauf erneut als Treffer gemeldet. Punkte ohne ID
    # bekommen von _norm_points eine, danach greift die Verknuepfung.
    punkt_id = treffer[0].get("id")
    if punkt_id is None:
        return 0
    step["point_id"] = punkt_id
    return 1


def _drop_dead_keys(step: dict) -> set:
    entfernt = set()
    for key in _DEAD_STEP_KEYS:
        if key in step:
            del step[key]
            entfernt.add(key)
    return entfernt


# ---------------------------------------------------------------------------
# Sequenzen: Version 1 -> 2
# ---------------------------------------------------------------------------

def _seq_v1_to_v2(data: dict, context: dict) -> list[str]:
    """Raeumt `delay_after` weg - den Vorlaeufer von `delay_before`.

    Der Loader hat das Feld bisher selbst abgefangen ("Unterstuetze beide Formate").
    Genau diese Art Verzweigung soll hier landen und dort verschwinden: ein Schritt in
    der Kette, danach kennt der Loader nur noch `delay_before`.
    """
    umbenannt = 0
    for _phase, steps in _iter_step_lists(data):
        for step in steps:
            if "delay_after" in step:
                alt = step.pop("delay_after")
                # delay_before gewinnt, falls beide dastehen - es ist das aktuelle Feld.
                if step.get("delay_before") is None:
                    step["delay_before"] = alt if alt is not None else 0
                umbenannt += 1
    return [f"{umbenannt} Schritt(e): delay_after -> delay_before"] if umbenannt else []


def _seq_v2_to_v3(data: dict, context: dict) -> list[str]:
    """Verknüpft Klick-Schritte nachträglich mit ihrem Punkt (`point_id`).

    Warum ein eigener Schritt, obwohl v0→v1 schon verknüpft: der Recorder legte
    Schritte und Punkte unabhängig voneinander an, ohne Referenz dazwischen. Die
    Sequenz wurde dabei sofort auf die damals aktuelle Version gestempelt — also
    lief die Kette nie über sie, und die Verknüpfung passierte nie.

    Der Recorder baut die Referenz inzwischen selbst ein. Dieser Schritt ist
    ausschliesslich für den Bestand da, der davor entstanden ist: einmal beim Start
    durchgezogen, danach ist Ruhe.

    **Löschen, sobald keine Altbestände mehr existieren** — samt Hochzählen von
    SCHEMA_VERSION. Das Modul soll schrumpfen.
    """
    punkte = context.get("points") or []
    nach_pos: dict = {}
    for p in punkte:
        try:
            nach_pos.setdefault((int(p["x"]), int(p["y"])), []).append(p)
        except (KeyError, TypeError, ValueError):
            continue

    verknuepft = 0
    for _phase, steps in _iter_step_lists(data):
        for step in steps:
            verknuepft += _link_step_to_point(step, nach_pos)
    return [f"{verknuepft} Schritt(e) nachträglich mit ihrem Punkt verknüpft"] if verknuepft else []


# ---------------------------------------------------------------------------
# Dateitypen OHNE Versions-Feld
# ---------------------------------------------------------------------------
# points.json ist eine Liste, items.json/slots.json und die Presets sind
# Name->Eintrag-Dicts. Da laesst sich kein `schema_version` unterbringen, ohne die
# Struktur umzubauen - ein Key "schema_version" neben lauter Item-Namen waere ein
# Fremdkoerper im selben Namensraum.
#
# Statt einer Kette bekommen diese Typen einen NORMALISIERER: eine Funktion, die die
# Altform erkennt und in die aktuelle hebt, und die man beliebig oft laufen lassen kann
# (zweiter Lauf aendert nichts). Der Effekt ist derselbe - die Loader duerfen nur noch
# das aktuelle Format kennen - und geloescht wird der Normalisierer genauso, sobald
# keine Altbestaende mehr existieren.

def _fix_item(item: dict) -> bool:
    """Hebt ein einzelnes Item-Dict. True = es wurde etwas geaendert."""
    cp = item.get("confirm_point")
    # confirm_point war frueher [x, y], heute {"x": .., "y": ..}
    if isinstance(cp, (list, tuple)) and len(cp) == 2:
        item["confirm_point"] = {"x": cp[0], "y": cp[1]}
        return True
    return False


def _norm_items(data, context: dict) -> list[str]:
    """items.json, items/presets/*.json - Name -> Item-Dict."""
    if not isinstance(data, dict):
        return []
    fixed = sum(1 for v in data.values() if isinstance(v, dict) and _fix_item(v))
    return [f"{fixed} Item(s): confirm_point [x,y] -> {{x,y}}"] if fixed else []


def _norm_item_scan(data, context: dict) -> list[str]:
    """item_scans/*.json - Kopien von Slots/Items werden zu Namens-Referenzen.

    Vorher lag jeder Slot und jedes Item vollstaendig im Scan. Der Name war schon immer
    die Identitaet - also bleibt nur der Name, und aufgeloest wird gegen slots.json /
    items.json. Damit wirken Aenderungen am globalen Eintrag sofort in jedem Scan.

    Namen, die es global nicht gibt, meldet resolve_scan_references() beim Laden. Die
    vollen Daten stehen bis dahin noch in der .bak-Sicherung.
    """
    if not isinstance(data, dict):
        return []
    meldungen = []
    for feld, namensfeld, label in (("slots", "slot_names", "Slot"),
                                    ("items", "item_names", "Item")):
        eingebettet = data.pop(feld, None)
        if eingebettet is None:
            continue
        namen = [e["name"] for e in eingebettet
                 if isinstance(e, dict) and e.get("name")]
        # Schon vorhandene Namensliste gewinnt - sie ist das aktuelle Feld.
        if not data.get(namensfeld):
            data[namensfeld] = namen
        meldungen.append(f"{len(namen)} {label}(s) als Referenz statt Kopie "
                         f"({feld} -> {namensfeld})")
    return meldungen


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

    Diese Typen haben heute nichts zu heben. Der Eintrag steht trotzdem hier und der
    Loader ruft trotzdem migrate() auf: eine spaetere Formataenderung kostet dann genau
    eine Funktion an dieser Stelle, statt zusaetzlich die Frage "wo muss der Aufruf
    ueberhaupt hin". Genau daran scheitern Migrationen sonst - nicht am Umrechnen,
    sondern daran, dass die Schleuse an der Stelle fehlt.
    """
    return []


_NORMALIZER: dict[str, MigrationStep] = {
    KIND_POINTS: _norm_points,
    KIND_ITEMS: _norm_items,
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

# Eintrag i hebt von Version i auf i+1.
_CHAINS: dict[str, list[MigrationStep]] = {
    KIND_SEQUENCE: [_seq_v0_to_v1, _seq_v1_to_v2, _seq_v2_to_v3],
}


def migrate(data, kind: str, context: Optional[dict] = None) -> tuple:
    """Hebt geladene Daten auf den aktuellen Stand.

    Gibt (Daten, Meldungen) zurück. Leere Meldungen = war schon aktuell. Die Daten werden
    in-place verändert und zusätzlich zurückgegeben, damit sich beides aufrufen lässt.

    Zwei Wege, je nach Dateityp: versionierte Typen laufen ihre Kette ab und bekommen den
    Versions-Stempel, unversionierte (Liste/Name-Dict) laufen durch ihren Normalisierer.
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
