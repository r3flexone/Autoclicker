"""
Sequenz-Persistenz.

Jede Sequenz liegt vollständig unter ``sequences/<name>/``. Ihr Punkt-Pool
steht in ``sequence.json``; Punkt-IDs gelten nur innerhalb dieser Sequenz.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from ..config import SEQUENCES_DIR
from ..models import ClickPoint, ELSE_SKIP, LoopPhase, Sequence, AutoClickerState
from .migration import KIND_SEQUENCE, SCHEMA_VERSION, migrate, stamp
from ..utils import compact_json, sanitize_filename, save_tag, err, info, warn, hint, atomic_write, describe_color
from .serialization import _parse_steps, _sequence_to_dict

logger = logging.getLogger("autoclicker")


# =============================================================================
# VERZEICHNIS
# =============================================================================

def ensure_sequences_dir() -> Path:
    """Stellt sicher, dass der Sequenzen-Ordner existiert."""
    path = Path(SEQUENCES_DIR)
    path.mkdir(exist_ok=True)
    return path


def sequence_dir(name: str) -> Path:
    """Besitzordner einer Sequenz."""
    return ensure_sequences_dir() / sanitize_filename(name)


def sequence_file(name: str) -> Path:
    """Hauptdatei einer Sequenz in ihrem Besitzordner."""
    return sequence_dir(name) / "sequence.json"


def sequence_templates_dir(name: str) -> Path:
    """Template-Ordner einer Sequenz."""
    return sequence_dir(name) / "templates"


def active_sequence_dir(state: AutoClickerState) -> Path:
    """Besitzordner der aktiven Sequenz; ohne Auswahl ist das ein Fehler."""
    with state.lock:
        seq = state.active_sequence
    if seq is None:
        raise ValueError("Keine Sequenz ausgewählt.")
    return sequence_dir(seq.name)


def active_templates_dir(state: AutoClickerState) -> Path:
    """Template-Ordner der aktiven Sequenz."""
    return active_sequence_dir(state) / "templates"


# =============================================================================
# SEQUENZ-DATEI I/O
# =============================================================================

def save_sequence_file(seq: Sequence, filepath: Path) -> bool:
    """Speichert eine einzelne Sequenz direkt in die angegebene Datei."""
    filepath = Path(filepath)
    if filepath.name != "sequence.json":
        filepath = filepath.parent / sanitize_filename(seq.name) / "sequence.json"
    try:
        atomic_write(filepath, compact_json(stamp(_sequence_to_dict(seq))))
        return True
    except (IOError, OSError) as e:
        print(err(f"Sequenz konnte nicht gespeichert werden: {e}"))
        return False


def load_sequence_file(filepath: Path, points: Optional[list] = None) -> Optional[Sequence]:
    """Lädt eine einzelne Sequenz-Datei.

    `points` bleibt nur vorübergehend aufrufkompatibel; die Datenquelle ist
    ausschließlich das Feld `points` derselben Sequenzdatei.
    """
    filepath = Path(filepath)
    if filepath.is_dir():
        filepath = filepath / "sequence.json"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        data, meldungen = migrate(data, KIND_SEQUENCE)
        if meldungen:
            print(info(f"'{filepath.stem}' auf Schema {SCHEMA_VERSION} gehoben:"))
            for m in meldungen:
                print(f"         - {m}")
            print(f"         {hint('Beim nächsten Speichern wird das Format dauerhaft sauber.')}")

        loop_phases = [
            LoopPhase(
                name=lp.get("name", "Loop"),
                steps=_parse_steps(lp.get("steps", [])),
                repeat=lp.get("repeat", 1),
                scheduled_start=lp.get("scheduled_start"),
            )
            for lp in data.get("loop_phases", [])
        ]
        seq_points = _als_punkte(data.get("points", []))
        seq = Sequence(
            data["name"],
            _parse_steps(data.get("init_steps", [])),
            loop_phases,
            _parse_steps(data.get("end_steps", [])),
            data.get("total_cycles", 1),
            data.get("description", ""),
            seq_points,
        )

        # Arbeitswerte fuellen. `still=True`: dass ein Schritt seine Koordinate aus dem
        # Punkt bekommt, ist beim Laden kein Ereignis, sondern der einzige Weg. Gemeldet
        # werden nur tote Referenzen.
        for m in aufloesen({p.id: p for p in seq.points}, seq, still=True):
            print(warn(f"'{filepath.stem}': {m}"))
        return seq

    except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


# Sequenz-Liste mit mtime-Cache — die Editor-Auswahl ruft list_available_sequences
# mehrmals hintereinander auf, ohne Cache wäre das pro Aufruf ein voller Dir-Scan.
_seq_cache: list[tuple[str, Path]] = []
_seq_cache_key: tuple = ()


def _verzeichnis_kennung(seq_dir: Path) -> tuple:
    """Was der Cache vergleicht: die Eintraege selbst, nicht die Ordner-Uhr.

    Die mtime des Ordners ist auf grober Zeitaufloesung unsicher (NTFS) — zwei
    im selben Tick geschriebene Sequenzen liessen die zweite unsichtbar werden.
    Name, Groesse und mtime jedes Eintrags fangen das ab; teuer ist ohnehin
    erst das Parsen, und das spart der Cache weiterhin.
    """
    eintraege = []
    with os.scandir(seq_dir) as it:
        for e in it:
            if not e.is_dir():
                continue
            try:
                datei = Path(e.path) / "sequence.json"
                st = datei.stat()
            except OSError:
                continue
            eintraege.append((e.name, st.st_size, st.st_mtime_ns))
    return tuple(sorted(eintraege))


def list_available_sequences() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Sequenz-Dateien auf (mit Verzeichnis-Cache)."""
    global _seq_cache, _seq_cache_key
    seq_dir = Path(SEQUENCES_DIR)
    if not seq_dir.exists():
        return []

    try:
        current_key = _verzeichnis_kennung(seq_dir)
    except OSError:
        return []

    if _seq_cache and _seq_cache_key == current_key:
        return _seq_cache

    # sorted(): sonst haengt die Menue-Reihenfolge vom Dateisystem ab und der
    # dritte Eintrag ist mal seq02, mal seq13.
    sequences = []
    for ordner in sorted(p for p in seq_dir.iterdir() if p.is_dir()):
        f = ordner / "sequence.json"
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                name = data.get("name", ordner.name)
                sequences.append((name, f))
        except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError,
                ValueError, UnicodeDecodeError):
            pass
    _seq_cache = sequences
    _seq_cache_key = current_key
    return sequences


# =============================================================================
# SAMMEL-SAVE (Punkte + alle Sequenzen)
# =============================================================================

def save_data(state: AutoClickerState) -> None:
    """Speichert alle Sequenzen einschließlich ihrer Punkte."""
    ensure_sequences_dir()

    # Snapshot unter Lock - damit Worker-Thread parallele Mutationen nicht stören
    with state.lock:
        sequences_snapshot = list(state.sequences.items())

    # Sequenzen speichern
    for name, seq in sequences_snapshot:
        save_sequence_file(seq, sequence_file(name))

    print(save_tag(f"Daten gespeichert in '{SEQUENCES_DIR}/'"))


# =============================================================================
# PUNKTE
# =============================================================================

def save_points(state: AutoClickerState) -> None:
    """Speichert die aktive Sequenz einschließlich ihres Punkt-Pools."""
    with state.lock:
        seq = state.active_sequence
        if seq is None:
            return
        seq.points = state.points
        name = seq.name
    save_sequence_file(seq, sequence_file(name))


def load_points(state: AutoClickerState) -> None:
    """Setzt die Arbeitsansicht auf die Punkte der aktiven Sequenz."""
    with state.lock:
        state.points = state.active_sequence.points if state.active_sequence else []


def _punkt_aus_dict(p: dict) -> ClickPoint:
    """Ein rohes Punkt-Dict (schon migriert) als ClickPoint."""
    farbe = p.get("color")
    return ClickPoint(p["x"], p["y"], p.get("name", ""), p["id"],
                      color=tuple(int(v) for v in farbe) if farbe else None,
                      source=p.get("source", ""))


def _punkte_aus_datei() -> list[ClickPoint]:
    """Entfallen: Punkte werden nicht außerhalb einer Sequenz geladen."""
    return []


def punkte_nachladen(state: AutoClickerState) -> list[ClickPoint]:
    """Lädt den Punkt-Pool der aktiven Sequenz frisch von Platte."""
    with state.lock:
        seq = state.active_sequence
    if seq is None:
        return []
    pfad = sequence_file(seq.name)
    geladen = load_sequence_file(pfad)
    if geladen is None:
        return list(seq.points)
    with state.lock:
        seq.points = geladen.points
        state.points = seq.points
        return list(seq.points)


# `_sichere_neue_punkte()` stand hier und ist mit der Migrationskette entfallen: es
# schrieb Punkte weg, die `_seq_v3_to_v4` gerade angelegt hatte. Ohne Kette legt die
# Migration keine Punkte mehr an, also gibt es auch nichts nachzuschreiben — und eine
# Funktion, die auf ein Ereignis wartet, das nicht mehr eintritt, ist genau die Sorte
# Altlast, die dieses Projekt nicht mitschleppt.


def _als_punkte(points) -> list[ClickPoint]:
    """Punkte-Liste vereinheitlichen: ClickPoints ODER rohe Dicts rein, ClickPoints raus.

    Noetig, weil die Aufrufer beides liefern — der Sweep rohe Dicts (er will den
    State nicht anfassen), die Editoren `list(state.points)`.
    """
    raus = []
    for p in points or []:
        if isinstance(p, dict):
            try:
                raus.append(_punkt_aus_dict(p))
            except (KeyError, TypeError, ValueError):
                continue
        else:
            raus.append(p)
    return raus


# `_als_dicts()` ist mit der Migrationskette entfallen. Es reichte die Punkte als rohe
# Dicts in die Migration - und zwar bewusst als DIESELBE Liste statt als Kopie, damit
# von `_seq_v3_to_v4` angelegte Punkte beim Aufrufer ankamen. Ohne Kette bekommt
# `migrate()` fuer Sequenzen gar keinen Punkte-Kontext mehr.


def get_next_point_id(state: AutoClickerState) -> int:
    """Gibt die nächste freie Punkt-ID zurück."""
    if not state.points:
        return 1
    return max(p.id for p in state.points) + 1


def punkt_an_stelle(punkte, x: int, y: int, color=None,
                    radius: Optional[int] = None,
                    farbtoleranz: Optional[int] = None):
    """Der vorhandene Punkt an dieser Stelle — oder None. Die eine Regel.

    Editor und Aufnahme stellen dieselbe Frage; mit exaktem Vergleich entstand
    pro Klick ein eigener Punkt. Zwei Bedingungen:

    1. Abstand ≤ `punkt_radius` (0 = nur exakt, das alte Verhalten)
    2. Die Farbe muss passen — an einer Farbgrenze klickt man zwei
       verschiedene Dinge, und zwei Spiele übereinander unterscheiden sich in
       nichts anderem.

    Fehlt einer Seite die Farbe, zählt nur die exakte Stelle: lieber ein Punkt
    zu viel als zwei zusammengelegt, die es nicht sind.
    """
    from ..config import CONFIG
    radius = CONFIG.punkt_radius if radius is None else radius
    ftol = CONFIG.punkt_farbtoleranz if farbtoleranz is None else farbtoleranz
    genau = None
    for p in punkte:
        if (p.x, p.y) == (x, y):
            genau = p
            break
    if genau is not None or radius <= 0 or not color:
        return genau
    beste, bester_abstand = None, None
    for p in punkte:
        if not p.color:
            continue
        if max(abs(a - b) for a, b in zip(p.color, color)) > ftol:
            continue
        abstand = ((p.x - x) ** 2 + (p.y - y) ** 2) ** 0.5
        if abstand <= radius and (bester_abstand is None or abstand < bester_abstand):
            beste, bester_abstand = p, abstand
    return beste


def punkt_fuer_stelle(state: AutoClickerState, x: int, y: int,
                      color=None, name: str = "", source: str = "") -> int:
    """ID des Punktes an (x, y) - liegt dort keiner, wird einer angelegt.

    DER Weg, wie ein Editor an eine Stelle kommt; deshalb gibt es eine ID
    zurueck und keinen Punkt. Ein vorhandener an derselben Stelle wird
    wiederverwendet (`punkt_an_stelle()`), sonst wandert beim Nachjustieren nur
    eine von zwei Stellen mit.

    Ohne state.lock aufrufen bzw. den Aufrufer sperren lassen — schreibt state.points.
    """
    p = punkt_an_stelle(state.points, x, y, color)
    if p is not None:
        # Farbe nachtragen, falls der vorhandene Punkt noch keine hatte: ein
        # Farb-Trigger braucht sie, ein reiner Klickpunkt kam bisher ohne aus.
        if color and not p.color:
            p.color = tuple(color)
        return p.id

    punkt = ClickPoint(x, y, name or f"Punkt {get_next_point_id(state)}",
                       get_next_point_id(state),
                       color=tuple(color) if color else None, source=source)
    state.points.append(punkt)
    return punkt.id


def get_point_by_id(state: AutoClickerState, point_id: int) -> Optional[ClickPoint]:
    """Findet einen Punkt anhand seiner ID.

    Der Docstring versprach frueher O(1) - gebaut wurde aber bei JEDEM Aufruf das
    komplette Dict neu, also O(n) plus Allokation. Ein Durchlauf tut dasselbe billiger.
    """
    return next((p for p in state.points if p.id == point_id), None)


def _phasen(sequence):
    """(Phasenname, Schrittliste) fuer INIT, jede Loop-Phase und END."""
    raus = [("INIT", sequence.init_steps)]
    for lp in sequence.loop_phases:
        raus.append((lp.name, lp.steps))
    raus.append(("END", sequence.end_steps))
    return raus


def aufloesen(punkte: dict, sequence, still: bool = False) -> list[str]:
    """Fuellt die abgeleiteten Arbeitswerte aus dem Punkte-Pool. `punkte` ist id -> ClickPoint.

    Vier Referenzen pro Schritt:

    | Referenz                    | fuellt                      | fehlt der Punkt      |
    |-----------------------------|-----------------------------|----------------------|
    | `step.point_id`             | x, y, name, recorded_color  | Schritt uebersprungen|
    | `wait_condition.point_id`   | pixel, color                | Schritt uebersprungen|
    | `verify_condition.point_id` | pixel, color                | Pruefung entfaellt   |
    | `else_config.point_id`      | x, y, name                  | else wird 'skip'     |

    Klick und Vorbedingung sind der Schritt selbst, Nachpruefung und else nur
    Zusatz. Gemeldet wird beides.

    `still=True` unterdrueckt die "folgt Punkt"-Meldungen (beim Laden der
    Normalfall); verwaiste Referenzen werden IMMER gemeldet.
    """
    meldungen = []

    for phase_name, steps in _phasen(sequence):
        for i, step in enumerate(steps, 1):
            ort = f"{phase_name}[{i}]"

            if step.point_id is not None:
                punkt = punkte.get(step.point_id)
                if punkt is None:
                    # Kein Rueckfall auf alte Koordinaten - die gibt es nicht mehr.
                    # Der Schritt wird zur Laufzeit uebersprungen (siehe step_gate).
                    step.unresolved = True
                    meldungen.append(
                        f"{ort} '{step.name or 'Klick'}' zeigt auf Punkt "
                        f"#{step.point_id}, den es nicht mehr gibt - wird uebersprungen")
                else:
                    step.unresolved = False
                    alt = (step.x, step.y)
                    step.x, step.y, step.name = punkt.x, punkt.y, punkt.name
                    step.recorded_color = punkt.color
                    if alt != (0, 0) and alt != (punkt.x, punkt.y) and not still:
                        meldungen.append(
                            f"{ort} '{step.name}' folgt Punkt #{punkt.id}: "
                            f"{alt} -> ({punkt.x}, {punkt.y})")

            wc = step.wait_condition
            if wc is not None and wc.point_id is not None:
                punkt = punkte.get(wc.point_id)
                if punkt is None:
                    step.unresolved = True
                    meldungen.append(
                        f"{ort} Pruef-Pixel zeigt auf Punkt #{wc.point_id}, "
                        f"den es nicht mehr gibt - wird uebersprungen")
                else:
                    alt = tuple(wc.pixel)
                    wc.pixel = (punkt.x, punkt.y)
                    # Ohne Farbe am Punkt gaebe es nichts zu vergleichen; der Editor
                    # laesst das nicht zu, eine von Hand gebaute Datei schon.
                    wc.color = punkt.color if punkt.color else wc.color
                    if alt != (0, 0) and alt != wc.pixel and not still:
                        meldungen.append(
                            f"{ort} Pruef-Pixel folgt Punkt #{punkt.id}: "
                            f"{alt} -> {wc.pixel}")

            vc = step.verify_condition
            if vc is not None and vc.point_id is not None:
                punkt = punkte.get(vc.point_id)
                if punkt is None:
                    # Anders als beim Pruef-Pixel wird der Schritt NICHT uebersprungen:
                    # die Nachpruefung ist eine Zusatzsicherung, keine Vorbedingung.
                    # Sie faellt weg, der Schritt laeuft - und es wird gesagt.
                    meldungen.append(
                        f"{ort} Nachpruefung zeigt auf Punkt #{vc.point_id}, "
                        f"den es nicht mehr gibt - wird nicht mehr geprueft")
                    step.verify_condition = None
                else:
                    alt = tuple(vc.pixel)
                    vc.pixel = (punkt.x, punkt.y)
                    vc.color = punkt.color if punkt.color else vc.color
                    if alt != (0, 0) and alt != vc.pixel and not still:
                        meldungen.append(
                            f"{ort} Nachpruefung folgt Punkt #{punkt.id}: "
                            f"{alt} -> {vc.pixel}")

            ec = step.else_config
            if ec is not None and ec.point_id is not None:
                punkt = punkte.get(ec.point_id)
                if punkt is None:
                    # Die else-Aktion faellt auf "skip" zurueck statt auf (0,0) zu klicken.
                    meldungen.append(
                        f"{ort} Else-Klick zeigt auf Punkt #{ec.point_id}, "
                        f"den es nicht mehr gibt - else wird zu 'skip'")
                    ec.action = ELSE_SKIP
                    ec.point_id = None
                else:
                    alt = (ec.x, ec.y)
                    ec.x, ec.y, ec.name = punkt.x, punkt.y, punkt.name
                    if alt != (0, 0) and alt != (punkt.x, punkt.y) and not still:
                        meldungen.append(
                            f"{ort} Else-Klick folgt Punkt #{punkt.id}: "
                            f"{alt} -> ({punkt.x}, {punkt.y})")
    return meldungen


def resolve_point_references(state: AutoClickerState, sequence) -> list[str]:
    """Löst Schritt-Referenzen gegen den Punkt-Pool ihrer Sequenz auf."""
    return aufloesen({p.id: p for p in sequence.points}, sequence)


def print_points(state: AutoClickerState) -> None:
    """Zeigt alle gespeicherten Punkte an."""
    with state.lock:
        if not state.points:
            print(f"\n{info('Keine Punkte vorhanden.')}")
            print("       Punkte mit CTRL+ALT+A aufnehmen.")
            return

        print(f"\nGespeicherte Punkte ({len(state.points)}):")
        print("-" * 50)
        for p in state.points:
            color_str = f"  {describe_color(p.color)}" if p.color else ""
            src = f"  [{p.source}]" if p.source else ""
            print(f"  #{p.id:3d} {p.name:20s} ({p.x:4d}, {p.y:4d}){color_str}{src}")
        print("-" * 50)
