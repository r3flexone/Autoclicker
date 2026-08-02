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
from ..models import ClickPoint, ELSE_SKIP, LoopPhase, Sequence, AutoClickerState
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

    `points` sind die Punkte, aus denen die Koordinaten geholt werden. Ohne sie stünden
    im Ergebnis lauter Nullen — in der Datei stehen ja nur noch IDs. Deshalb lädt die
    Funktion sie selbst nach, wenn der Aufrufer keine übergibt: von den Aufrufern hat
    die Hälfte gar keinen Punkte-Pool zur Hand (Node-Editor, Canvas, Export), und die
    dürfen deswegen keine halbe Sequenz bekommen.
    """
    if points is None:
        points = _punkte_aus_datei()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Die Migration rechnet mit rohen Dicts und darf die Liste erweitern: legt sie
        # fuer einen unverknuepften Schritt einen Punkt an, landet er hier drin.
        punkt_dicts = _als_dicts(points)
        vorher = len(punkt_dicts)
        data, meldungen = migrate(data, KIND_SEQUENCE, {"points": punkt_dicts})
        if len(punkt_dicts) > vorher:
            _sichere_neue_punkte(punkt_dicts, len(punkt_dicts) - vorher, filepath.stem)
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
        seq = Sequence(
            data["name"],
            _parse_steps(data.get("init_steps", [])),
            loop_phases,
            _parse_steps(data.get("end_steps", [])),
            data.get("total_cycles", 1),
            data.get("description", ""),
        )

        # Arbeitswerte fuellen. `still=True`: dass ein Schritt seine Koordinate aus dem
        # Punkt bekommt, ist beim Laden kein Ereignis, sondern der einzige Weg. Gemeldet
        # werden nur tote Referenzen.
        for m in aufloesen({p.id: p for p in _als_punkte(punkt_dicts)}, seq, still=True):
            print(warn(f"'{filepath.stem}': {m}"))
        return seq

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


def _punkt_aus_dict(p: dict) -> ClickPoint:
    """Ein rohes Punkt-Dict (schon migriert) als ClickPoint."""
    farbe = p.get("color")
    return ClickPoint(p["x"], p["y"], p.get("name", ""), p["id"],
                      color=tuple(int(v) for v in farbe) if farbe else None,
                      source=p.get("source", ""))


def _punkte_aus_datei() -> list[ClickPoint]:
    """points.json direkt lesen, ohne den globalen State anzufassen.

    Fuer die Aufrufer von `load_sequence_file`, die keinen State haben (Node-Editor,
    Canvas, Export). Fehlt oder bricht die Datei, gibt es eben keine Punkte - dann
    meldet `aufloesen()` die Schritte als verwaist, statt still Nullen zu liefern.
    """
    pfad = Path(SEQUENCES_DIR) / "points.json"
    if not pfad.exists():
        return []
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            data, _ = migrate(json.load(f), KIND_POINTS)
        return [_punkt_aus_dict(p) for p in data]
    except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError,
            ValueError, UnicodeDecodeError):
        return []


def _sichere_neue_punkte(punkt_dicts: list, anzahl: int, seq_name: str) -> None:
    """Schreibt Punkte weg, die die Migration gerade angelegt hat.

    Der Normalweg fuer Altbestand ist der Start-Durchgang (`sweep`), und der schreibt
    points.json selbst. Diese Absicherung gilt allen anderen Aufrufern - Import,
    Node-Editor, ein Ordner, der nachtraeglich hineinkopiert wurde: dort entstuenden
    IDs, die nach dem naechsten Neustart auf nichts mehr zeigen. Lieber einmal zu viel
    geschrieben als eine Sequenz, die ins Leere klickt.
    """
    try:
        pfad = Path(SEQUENCES_DIR) / "points.json"
        pfad.parent.mkdir(exist_ok=True)
        atomic_write(pfad, compact_json([
            _point_to_dict(_punkt_aus_dict(p)) for p in punkt_dicts]))
    except (OSError, KeyError, TypeError, ValueError) as e:
        print(warn(f"'{seq_name}': {anzahl} neue Punkt(e) konnten nicht gespeichert "
                   f"werden ({e}) - die Sequenz zeigt bis dahin ins Leere."))
        return
    print(info(f"'{seq_name}': {anzahl} Koordinate(n) als Punkt uebernommen "
               f"(points.json ergaenzt)."))


def _als_punkte(points) -> list[ClickPoint]:
    """Punkte-Liste vereinheitlichen: ClickPoints ODER rohe Dicts rein, ClickPoints raus.

    Noetig, weil die Aufrufer beides liefern - der Sweep rohe Dicts (er will den State
    nicht anfassen), die Editoren `list(state.points)`. Vorher fiel das niemandem auf,
    weil die Migration Dict-Zugriffe in einem `except TypeError: continue` hatte: mit
    ClickPoints tat sie schlicht nichts.
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


def _als_dicts(points) -> list[dict]:
    """Gegenrichtung zu `_als_punkte` - die Migration rechnet mit rohen Dicts.

    Sind schon alle Eintraege Dicts, kommt DIESELBE Liste zurueck, keine Kopie: die
    Migration haengt neu angelegte Punkte an, und der Aufrufer (sweep) schreibt sie
    danach weg. Mit einer Kopie fielen genau diese Punkte still unter den Tisch -
    die Sequenz zeigte dann auf IDs, die es nirgends gab.
    """
    if points is None:
        return []
    if all(isinstance(p, dict) for p in points):
        return points
    return [p if isinstance(p, dict) else _point_to_dict(p) for p in points]


def get_next_point_id(state: AutoClickerState) -> int:
    """Gibt die nächste freie Punkt-ID zurück."""
    if not state.points:
        return 1
    return max(p.id for p in state.points) + 1


def punkt_fuer_stelle(state: AutoClickerState, x: int, y: int,
                      color=None, name: str = "", source: str = "") -> int:
    """ID des Punktes an (x, y) - liegt dort keiner, wird einer angelegt.

    DER Weg, wie ein Editor an eine Stelle kommt. Wer stattdessen Koordinaten in den
    Schritt schreibt, baut die Kopie wieder ein, die diese ganze Umstellung beseitigt
    hat - deshalb gibt es hier eine ID zurueck und keinen Punkt.

    Ein vorhandener Punkt an derselben Stelle wird wiederverwendet: klickt eine Sequenz
    zweimal denselben Knopf, soll das EIN Punkt sein. Sonst wandert beim Nachjustieren
    nur eine der beiden Stellen mit, und die Sequenz laeuft halb korrigiert weiter.

    Ohne state.lock aufrufen bzw. den Aufrufer sperren lassen - schreibt state.points.
    """
    for p in state.points:
        if (p.x, p.y) == (x, y):
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

    Drei Referenzen pro Schritt, alle nach demselben Muster:

    | Referenz                | fuellt                          |
    |-------------------------|---------------------------------|
    | `step.point_id`         | x, y, name, recorded_color      |
    | `wait_condition.point_id` | pixel, color                  |
    | `else_config.point_id`  | x, y, name                      |

    Die Arbeitswerte sind das, was Worker und Editoren lesen; gespeichert wird nur die
    ID. Deshalb laeuft das hier direkt beim Laden - sonst saehe jeder Aufrufer, der die
    Datei ohne Punkte oeffnet, lauter Nullen.

    `still=True` unterdrueckt die "folgt Punkt"-Meldungen (beim Laden ist das keine
    Nachricht, sondern der Normalfall). Verwaiste Referenzen werden IMMER gemeldet.
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
    """`aufloesen()` gegen den State-Punktpool - der Weg fuer Worker und Editoren.

    Der Punkt ist die Wahrheit: verschiebt man ihn, ziehen alle Schritte mit, die auf ihn
    zeigen. Genau das war vorher das Problem - eine verrutschte Aufnahme musste in jedem
    Schritt einzeln nachgezogen werden, und man musste den falschen Schritt erst finden.

    Ohne state.lock aufrufen bzw. den Aufrufer sperren lassen: die Funktion liest
    state.points und schreibt in die Sequenz-Schritte.
    """
    return aufloesen({p.id: p for p in state.points}, sequence)


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
