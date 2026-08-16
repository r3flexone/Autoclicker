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


# ---------------------------------------------------------------------------
# Sequenzen: die Kette ist LEER - und das ist der Zielzustand
# ---------------------------------------------------------------------------
# Hier standen vier Schritte (Schema 0 bis 4). Sie sind ersatzlos gelöscht, weil
# es keinen Altbestand mehr gibt, den sie heben könnten: alle Sequenzdateien
# stehen auf `schema_version: 4`. Genau das ist der Lebenslauf, für den dieses
# Modul gebaut wurde — Altlasten gehen einmal durch die Schleuse und danach
# verschwindet die Schleuse.
#
# Was sie erledigt haben, damit niemand es erneut baut:
#
#   0 -> 1  drei konkurrierende Phasen-Formate (`steps`, `loop_steps` + `max_loops`,
#           `start_steps`) auf `loop_phases` vereinheitlicht; tote Schritt-Felder
#           (`clicks`, `point_index`, `use_pixel_wait`) entfernt
#   1 -> 2  `delay_after` -> `delay_before`
#   2 -> 3  Aufnahmen des alten Recorders nachträglich mit ihrem Punkt verknüpft
#   3 -> 4  jede Koordinate aus der Sequenz nach points.json gezogen, notfalls als
#           neu angelegter Punkt — seither gilt ausnahmslos: eine Koordinate steht
#           in points.json, sonst nirgends
#
# **SCHEMA_VERSION bleibt auf 4.** Die Nummern sind eindeutig; es fällt nur der Weg
# dorthin weg. Eine Datei mit einer älteren Nummer wird jetzt kommentarlos auf 4
# gestempelt und ansonsten so gelesen, wie sie dasteht — der Loader arbeitet mit
# `data.get(key, default)`, ein fehlendes Feld bekommt also seinen Standardwert.
# Für den Fall, dass doch einmal eine sehr alte Datei auftaucht (eine Sicherung von
# vor Dezember 2025), ist der Weg nicht die Wiederbelebung dieser Schritte, sondern
# `git show <commit>:autoclicker/persistence/migration.py` — oder die Sequenz im
# Studio neu zu bauen, was inzwischen billiger ist.


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

# `_norm_items` ist ersatzlos entfallen. Es hob `confirm_point` von [x, y] auf
# {"x":.., "y":..} - ein Feld, das der Loader seit der Umstellung auf Punkt-Referenzen
# gar nicht mehr liest. Einen Normalisierer zu pflegen, der ein totes Feld in ein
# anderes totes Format bringt, ist genau das Anwachsen, das dieses Modul vermeiden
# soll. Ein altes confirm_point meldet jetzt der Loader (`_alt_gemeldet`), und der
# Bestaetigungs-Punkt wird einmal neu gesetzt.


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

# Eintrag i hebt von Version i auf i+1.
#
# **Die Sequenz-Kette ist leer, der Eintrag bleibt.** Der Schlüssel sagt „dieser
# Dateityp ist versioniert und läuft über eine Kette" — und daran hängt der Test,
# dass kein Dateityp ohne Schleuse dasteht. Ohne den Eintrag müsste man sich beim
# nächsten Formatwechsel erst wieder erinnern, wo der Haken überhaupt hingehört;
# genau daran scheitern Migrationen, nicht am Umrechnen. Eine leere Liste kostet
# nichts: `migrate()` hebt die Version dann nur an und lässt die Daten in Ruhe.
_CHAINS: dict[str, list[MigrationStep]] = {
    KIND_SEQUENCE: [],
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
