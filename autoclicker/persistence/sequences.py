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
from ..utils import compact_json, sanitize_filename, save_tag, load_tag, err, info, warn, atomic_write
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


# =============================================================================
# SEQUENZ-DATEI I/O
# =============================================================================

def save_sequence_file(seq: Sequence, filepath: Path) -> bool:
    """Speichert eine einzelne Sequenz direkt in die angegebene Datei."""
    try:
        atomic_write(filepath, compact_json(_sequence_to_dict(seq)))
        return True
    except (IOError, OSError) as e:
        print(err(f"Sequenz konnte nicht gespeichert werden: {e}"))
        return False


def load_sequence_file(filepath: Path) -> Optional[Sequence]:
    """Lädt eine einzelne Sequenz-Datei (mit Start + mehreren Loop-Phasen).

    Unterstützt drei Formate:
      - aktuell: loop_phases (Liste von LoopPhase-Dicts)
      - alt:     loop_steps + max_loops (eine Phase)
      - uralt:   steps (keine Phasen)
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        init_steps = _parse_steps(data.get("init_steps", []))
        end_steps = _parse_steps(data.get("end_steps", []))
        description = data.get("description", "")

        # Rückwärtskompatibilität: alte start_steps → erste LoopPhase mit repeat=1
        old_start_steps = _parse_steps(data.get("start_steps", []))

        # Neues Format mit loop_phases (mehrere Loop-Phasen)
        if "loop_phases" in data:
            loop_phases = []
            if old_start_steps:
                loop_phases.append(LoopPhase("Start", old_start_steps, 1))
            for lp_data in data["loop_phases"]:
                lp = LoopPhase(
                    name=lp_data.get("name", "Loop"),
                    steps=_parse_steps(lp_data.get("steps", [])),
                    repeat=lp_data.get("repeat", 1),
                    scheduled_start=lp_data.get("scheduled_start")
                )
                loop_phases.append(lp)
            total_cycles = data.get("total_cycles", 1)
            return Sequence(data["name"], init_steps, loop_phases, end_steps, total_cycles, description)

        # Altes Format mit loop_steps (eine Loop-Phase) - konvertieren
        if "loop_steps" in data:
            loop_steps = _parse_steps(data.get("loop_steps", []))
            max_loops = data.get("max_loops", 0)
            loop_phases = []
            if old_start_steps:
                loop_phases.append(LoopPhase("Start", old_start_steps, 1))
            if loop_steps:
                loop_phases.append(LoopPhase("Loop 1", loop_steps, max_loops if max_loops > 0 else 1))
            total_cycles = 0 if max_loops == 0 else 1
            return Sequence(data["name"], init_steps, loop_phases, end_steps, total_cycles, description)

        # Uraltes Format (nur steps) - konvertieren
        if "steps" in data:
            loop_steps = _parse_steps(data["steps"])
            loop_phases = [LoopPhase("Loop 1", loop_steps, 1)] if loop_steps else []
            return Sequence(data["name"], [], loop_phases, [], 0, description)

        return Sequence(data["name"], [], [], [], 1, description)

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

    sequences = []
    for f in seq_dir.glob("*.json"):
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
        points_data = [
            {"id": p.id, "x": p.x, "y": p.y, "name": p.name,
             **({"color": list(p.color)} if p.color else {})}
            for p in state.points
        ]
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
        points_data = [
            {"id": p.id, "x": p.x, "y": p.y, "name": p.name,
             **({"color": list(p.color)} if p.color else {})}
            for p in state.points
        ]
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
                # Lade Punkte mit ID (Fallback für alte Dateien ohne ID)
                state.points = []
                for i, p in enumerate(data):
                    point_id = p.get("id", i + 1)  # Fallback: Index + 1 für alte Dateien
                    color_raw = p.get("color")
                    color = tuple(int(v) for v in color_raw) if color_raw else None
                    state.points.append(ClickPoint(p["x"], p["y"], p.get("name", ""), point_id, color=color))
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
    """Findet einen Punkt anhand seiner ID (O(1) Dict-Lookup mit Fallback)."""
    points_by_id = {p.id: p for p in state.points}
    return points_by_id.get(point_id)


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
            print(f"  #{p.id:3d} {p.name:20s} ({p.x:4d}, {p.y:4d})")
        print("-" * 50)
