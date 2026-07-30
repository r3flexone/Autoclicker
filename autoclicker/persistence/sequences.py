"""
Sequenz- und Punkt-Persistenz.

Sequenzen liegen als einzelne JSON-Dateien unter sequences/<name>.json.
Punkte (ClickPoints) liegen gemeinsam in sequences/points.json mit
stabilen IDs für Referenzierung aus Sequenz-Schritten.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..config import SEQUENCES_DIR
from ..models import ClickPoint, LoopPhase, Sequence, AutoClickerState
from .migration import KIND_POINTS, KIND_SEQUENCE, SCHEMA_VERSION, migrate, stamp
from ..utils import compact_json, sanitize_filename, save_tag, load_tag, err, info, warn, hint, atomic_write, describe_color
from .serialization import _parse_steps, _sequence_to_dict, _point_to_dict

logger = logging.getLogger("autoclicker")


# =============================================================================
# VERZEICHNIS
# =============================================================================

def ensure_sequences_dir() -> Path:
    """Stellt sicher, dass der Sequenzen-Ordner existiert."""
    path = Path(SEQUENCES_DIR)
    path.mkdir(exist_ok=True)
    return path


# =============================================================================
# SEQUENZ-DATEI I/O
# =============================================================================

def save_sequence_file(seq: Sequence, filepath: Path) -> bool:
    """Speichert eine einzelne Sequenz direkt in die angegebene Datei."""
    try:
        atomic_write(filepath, compact_json(stamp(_sequence_to_dict(seq))))
        return True
    except (IOError, OSError) as e:
        print(err(f"Sequenz konnte nicht gespeichert werden: {e}"))
        return False


def load_sequence_file(filepath: Path, points: Optional[list] = None) -> Optional[Sequence]:
    """Lädt eine einzelne Sequenz-Datei.

    Die Altformate (start_steps / loop_steps+max_loops / steps) kennt dieser Loader
    NICHT mehr - darum kümmert sich migration.migrate(), bevor hier gelesen wird. So
    steht hier nur noch das aktuelle Schema, und neue Umstellungen kosten einen
    Migrationsschritt statt einer weiteren Sonderfall-Verzweigung.

    `points` (optional) erlaubt der Migration, Schritte über ihre Koordinaten mit
    Punkten zu verknüpfen.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        data, meldungen = migrate(data, KIND_SEQUENCE, {"points": points or []})
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
        return Sequence(
            data["name"],
            _parse_steps(data.get("init_steps", [])),
            loop_phases,
            _parse_steps(data.get("end_steps", [])),
            data.get("total_cycles", 1),
            data.get("description", ""),
        )

    except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


# Sequenz-Liste mit mtime-Cache — die Editor-Auswahl ruft list_available_sequences
# mehrmals hintereinander auf, ohne Cache wäre das pro Aufruf ein voller Dir-Scan.
_seq_cache: list[tuple[str, Path]] = []
_seq_cache_mtime: float = 0


def list_available_sequences() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Sequenz-Dateien auf (mit mtime-Cache)."""
    global _seq_cache, _seq_cache_mtime
    seq_dir = Path(SEQUENCES_DIR)
    if not seq_dir.exists():
        return []

    try:
        current_mtime = seq_dir.stat().st_mtime
    except OSError:
        return []

    if _seq_cache and _seq_cache_mtime == current_mtime:
        return _seq_cache

    # sorted(): sonst haengt die Menue-Reihenfolge vom Dateisystem ab und der
    # dritte Eintrag ist mal seq02, mal seq13.
    sequences = []
    for f in sorted(seq_dir.glob("*.json")):
        if f.name != "points.json":
            try:
                with open(f, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    name = data.get("name", f.stem)
                    sequences.append((name, f))
            except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError):
                pass  # Ungültige/korrupte Datei überspringen
    _seq_cache = sequences
    _seq_cache_mtime = current_mtime
    return sequences


# =============================================================================
# SAMMEL-SAVE (Punkte + alle Sequenzen)
# =============================================================================

def save_data(state: AutoClickerState) -> None:
    """Speichert Punkte und Sequenzen in JSON-Dateien."""
    ensure_sequences_dir()

    # Snapshot unter Lock - damit Worker-Thread parallele Mutationen nicht stören
    with state.lock:
        points_data = [_point_to_dict(p) for p in state.points]
        sequences_snapshot = list(state.sequences.items())

    # Punkte speichern (mit stabiler ID)
    try:
        atomic_write(Path(SEQUENCES_DIR) / "points.json", compact_json(points_data))
    except (IOError, OSError) as e:
        print(err(f"Punkte konnten nicht gespeichert werden: {e}"))

    # Sequenzen speichern
    for name, seq in sequences_snapshot:
        filename = f"{sanitize_filename(name)}.json"
        save_sequence_file(seq, Path(SEQUENCES_DIR) / filename)

    print(save_tag(f"Daten gespeichert in '{SEQUENCES_DIR}/'"))


# =============================================================================
# PUNKTE
# =============================================================================

def save_points(state: AutoClickerState) -> None:
    """Speichert nur die globalen Punkte (points.json), crash-sicher."""
    ensure_sequences_dir()
    with state.lock:
        points_data = [_point_to_dict(p) for p in state.points]
    try:
        atomic_write(Path(SEQUENCES_DIR) / "points.json", compact_json(points_data))
    except (IOError, OSError) as e:
        print(err(f"Punkte konnten nicht gespeichert werden: {e}"))


def load_points(state: AutoClickerState) -> None:
    """Lädt gespeicherte Punkte."""
    points_file = Path(SEQUENCES_DIR) / "points.json"
    if points_file.exists():
        try:
            with open(points_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Altlasten (fehlende IDs, tote Felder) raeumt die Migration weg - hier wird
            # nur noch das aktuelle Format gelesen.
            data, meldungen = migrate(data, KIND_POINTS)
            if meldungen:
                print(info("points.json aufgeraeumt:"))
                for m in meldungen:
                    print(f"         - {m}")
                print(hint("         Beim nächsten Speichern wird das dauerhaft."))
            state.points = []
            for p in data:
                color_raw = p.get("color")
                color = tuple(int(v) for v in color_raw) if color_raw else None
                state.points.append(ClickPoint(p["x"], p["y"], p.get("name", ""), p["id"],
                                               color=color, source=p.get("source", "")))
            print(load_tag(f"{len(state.points)} Punkt(e) geladen"))
        except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as e:
            print(warn(f"points.json konnte nicht geladen werden: {e}"))
            print(info("Starte mit leerer Punktliste."))
            state.points = []
    else:
        print(info("Keine gespeicherten Punkte gefunden."))


def get_next_point_id(state: AutoClickerState) -> int:
    """Gibt die nächste freie Punkt-ID zurück."""
    if not state.points:
        return 1
    return max(p.id for p in state.points) + 1


def get_point_by_id(state: AutoClickerState, point_id: int) -> Optional[ClickPoint]:
    """Findet einen Punkt anhand seiner ID.

    Der Docstring versprach frueher O(1) - gebaut wurde aber bei JEDEM Aufruf das
    komplette Dict neu, also O(n) plus Allokation. Ein Durchlauf tut dasselbe billiger.
    """
    return next((p for p in state.points if p.id == point_id), None)


def resolve_point_references(state: AutoClickerState, sequence) -> list[str]:
    """Zieht bei Schritten mit point_id die Koordinaten aus dem Punkte-Pool nach.

    Der Punkt ist die Wahrheit: verschiebt man ihn, ziehen alle Schritte mit, die auf ihn
    zeigen. Genau das war vorher das Problem - eine verrutschte Aufnahme musste in jedem
    Schritt einzeln nachgezogen werden, und man musste den falschen Schritt erst finden.

    Gibt Klartext-Meldungen zurueck (nachgezogene Schritte, verwaiste Referenzen).
    Schritte ohne point_id bleiben unberuehrt - Aufnahmen, Tastendruecke und Scans
    funktionieren unveraendert wie bisher.

    Ohne state.lock aufrufen bzw. den Aufrufer sperren lassen: die Funktion liest
    state.points und schreibt in die Sequenz-Schritte.
    """
    meldungen = []
    punkte = {p.id: p for p in state.points}

    phasen = [("INIT", sequence.init_steps)]
    for lp in sequence.loop_phases:
        phasen.append((lp.name, lp.steps))
    phasen.append(("END", sequence.end_steps))

    for phase_name, steps in phasen:
        for i, step in enumerate(steps, 1):
            if step.point_id is None:
                continue
            punkt = punkte.get(step.point_id)
            if punkt is None:
                meldungen.append(
                    f"{phase_name}[{i}] '{step.name}' zeigt auf Punkt #{step.point_id}, "
                    f"den es nicht mehr gibt - Schritt bleibt bei ({step.x}, {step.y})")
                continue
            if (punkt.x, punkt.y) == (step.x, step.y):
                continue

            alt = (step.x, step.y)
            step.x, step.y = punkt.x, punkt.y
            # Prüf-Pixel NUR mitziehen, wenn er genau auf dem alten Klickpunkt lag.
            # Ein bewusst anderswo gesetzter Pixel (z.B. per 'wait pixel') bleibt, wo er
            # ist - sonst würde das Nachziehen fremde Prüfstellen verschieben.
            wc = step.wait_condition
            pixel_info = ""
            if wc is not None and tuple(wc.pixel) == alt:
                wc.pixel = (punkt.x, punkt.y)
                pixel_info = " (Prüf-Pixel mitgezogen)"
            meldungen.append(
                f"{phase_name}[{i}] '{step.name}' folgt Punkt #{punkt.id}: "
                f"{alt} -> ({punkt.x}, {punkt.y}){pixel_info}")
    return meldungen


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
