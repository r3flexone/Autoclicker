"""Alle JSON-Dateien in einem Durchgang aufs aktuelle Format heben.

Unterschied zu `migration.py`: das dort ist reine Datenlogik (dict rein, dict
raus), hier kommt das Dateisystem dazu. Zwei Aufrufer: `main.py` beim Start
(schreibt, meldet nur bei Aenderungen) und `tools/migrate.py` von Hand (zeigt
per Default nur an).

Beim START und nicht beim Speichern, weil Speichern ohnehin das aktuelle
Format schreibt — das Problem sind Dateien, die man NICHT anfasst. Danach
sind alle Dateien aktuell und der Migrationsschritt darf geloescht werden.

Zwei Regeln: **still, wenn nichts zu tun ist**, und **nie Daten verlieren**
(.bak unter `backups/` vor der ersten Aenderung, unladbare Dateien bleiben
unangetastet).
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Callable

from .migration import (
    KIND_BOSS_SCAN, KIND_GLOBAL_BOSSES, KIND_ICON_SCAN, KIND_ITEMS, KIND_ITEM_SCAN,
    KIND_SEQUENCE, KIND_SLOTS, migrate, stamp,
)
from ..utils import atomic_write, compact_json
from . import serialization as ser
from .paths import BACKUPS_DIR, ITEM_PRESETS_DIR, SLOT_PRESETS_DIR


# ---------------------------------------------------------------------------
# Round-Trip pro Dateityp: laden + zurueckschreiben.
# ---------------------------------------------------------------------------
# Das ist die eigentliche Reinigung. Der Loader kennt nur aktuelle Felder, der
# Serializer schreibt nur aktuelle Felder - was dazwischen wegfaellt, war Altbestand.
# Deshalb werden auch Dateitypen sauber, die gar keinen Migrationsschritt haben.

def _load(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def _rt_sequence(path: Path):
    from .sequences import load_sequence_file
    seq = load_sequence_file(path)
    # stamp() wie in save_sequence_file - ohne Stempel gilt die Datei beim naechsten
    # Start wieder als Schema 0 und laeuft die ganze Kette erneut.
    return stamp(ser._sequence_to_dict(seq)) if seq else None


def _rt_item_scan(path: Path):
    from .item_scans import load_item_scan_file
    cfg = load_item_scan_file(path)
    return ser._item_scan_to_dict(cfg) if cfg else None


def _rt_boss_scan(path: Path):
    from .boss_scans import load_boss_scan_file
    cfg = load_boss_scan_file(path)
    return ser._boss_scan_to_dict(cfg) if cfg else None


def _rt_icon_scan(path: Path):
    from .icon_scans import load_icon_scan_file
    cfg = load_icon_scan_file(path)
    return ser._icon_scan_to_dict(cfg) if cfg else None


def _rt_items(path: Path):
    data, _ = migrate(_load(path), KIND_ITEMS)
    if not isinstance(data, dict):
        return None
    return {name: ser._item_to_dict(ser._item_from_dict(i, name))
            for name, i in data.items()}


def _rt_slots(path: Path):
    data, _ = migrate(_load(path), KIND_SLOTS)
    if not isinstance(data, dict):
        return None
    return {name: ser._slot_to_dict(ser._slot_from_dict(name, s))
            for name, s in data.items()}


def _rt_bosses(path: Path):
    data, _ = migrate(_load(path), KIND_GLOBAL_BOSSES)
    if not isinstance(data, list):
        return None
    return [ser._boss_profile_to_dict(ser._boss_profile_from_dict(b)) for b in data]


def _rt_config(path: Path):
    """config.json: from_dict wirft unbekannte Keys weg, to_dict schreibt die aktuellen."""
    from ..config import AppConfig
    data = _load(path)
    return AppConfig.from_dict(data).to_dict() if isinstance(data, dict) else None


KIND_CONFIG = "config"

RoundTrip = Callable[[Path], object]


def _sequences_dir() -> Path:
    from ..config import SEQUENCES_DIR
    return Path(SEQUENCES_DIR)


def collect_files() -> list[tuple[Path, str, RoundTrip]]:
    """Alle JSON-Dateien der App mit Typ und Round-Trip-Funktion.

    Alle Pfade sind relativ zum Arbeitsverzeichnis - genau wie im laufenden Programm.
    Ein anderes Verzeichnis testet man deshalb mit os.chdir(), nicht durch Umbiegen der
    Konstanten.

    **Gelaufen wird ueber die Besitzeinheiten, nicht ueber Dateitypen.** Eine Sequenz
    ist samt Punkten, Scans und Bibliothek EIN Ordner (`sequences/<name>/`). Hier stand
    einmal die flache Struktur von frueher - ein `glob("sequences/*.json")` plus Ordner
    `item_scans/`, `boss_scans/`, `slots/`, `items/` im Wurzelverzeichnis. Nach dem
    Umzug fand der Glob nichts mehr und die Wurzelordner gab es nicht: der Durchgang
    erfasste von dreizehn Datendateien noch die `config.json`, und zwar still. Wer
    hier etwas ergaenzt, geht deshalb vom Sequenzordner aus.
    """
    files: list[tuple[Path, str, RoundTrip]] = []

    from ..config import CONFIG_FILE
    cfg = Path(CONFIG_FILE)
    if cfg.exists():
        files.append((cfg, KIND_CONFIG, _rt_config))

    # Die Punkte haben keine eigene Datei mehr - sie stehen im Feld `points` der
    # `sequence.json` und werden mit ihr round-getrippt.
    seq_dir = _sequences_dir()
    if seq_dir.is_dir():
        for folder in sorted(e for e in seq_dir.iterdir() if e.is_dir()):
            main_part = folder / "sequence.json"
            if main_part.exists():
                files.append((main_part, KIND_SEQUENCE, _rt_sequence))
            for below, kind, rt in (
                ("item_scans", KIND_ITEM_SCAN, _rt_item_scan),
                ("boss_scans", KIND_BOSS_SCAN, _rt_boss_scan),
                ("icon_scans", KIND_ICON_SCAN, _rt_icon_scan),
            ):
                d = folder / below
                if not d.is_dir():
                    continue
                for file in sorted(d.glob("*.json")):
                    # Die Boss-Bibliothek liegt als `bibliothek.json` zwischen den
                    # Scan-Konfigurationen (s. `_global_bosses_file`) und ist eine
                    # Liste, kein Scan - mit dem Scan-Loader gelesen waere sie
                    # unlesbar und wuerde als "uebersprungen" gemeldet.
                    if below == "boss_scans" and file.name == "bibliothek.json":
                        files.append((file, KIND_GLOBAL_BOSSES, _rt_bosses))
                    else:
                        files.append((file, kind, rt))

    # Presets sind programmweit und gehoeren keiner Sequenz.
    for folder, kind, rt in (
        (ITEM_PRESETS_DIR, KIND_ITEMS, _rt_items),
        (SLOT_PRESETS_DIR, KIND_SLOTS, _rt_slots),
    ):
        d = Path(folder)
        if d.is_dir():
            for file in sorted(d.glob("*.json")):
                files.append((file, kind, rt))

    return files


def _normalize_numbers(x):
    """int und float derselben Zahl angleichen - JSON kennt nur EINEN Zahlentyp.

    Ohne das galt eine von Hand auf `600` getippte Wartezeit als aufzuraeumen
    (der Loader macht `600.0` daraus) und der Durchgang meldete eine Migration,
    die inhaltlich nichts tat. bool bleibt bool — sonst waere ein umgekipptes
    Flag unsichtbar.

    **Ein Tupel ist dabei eine Liste.** JSON kennt nur das Array; der Loader gibt
    Farben als Tupel zurueck, in der Datei stehen sie als Liste. Stieg die
    Normalisierung nicht in das Tupel hinein, blieben dessen Zahlen `int`,
    waehrend die der Liste `float` wurden - und zwei inhaltsgleiche Dateien
    galten als verschieden. Genau derselbe Fehler wie bei `600` gegen `600.0`,
    nur eine Klammer weiter: jeder Start haette dieselben Item-Scans neu
    geschrieben, ein .bak angelegt und eine Migration gemeldet, die nichts tut.
    """
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, dict):
        return {k: _normalize_numbers(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_normalize_numbers(v) for v in x]
    return x


def _equal(a, b) -> bool:
    """Inhaltsgleich? Normalisierter JSON-Text, damit Schluesselreihenfolge,
    Einrueckung und der Python-Zahlentyp nicht als Aenderung durchgehen."""
    return (json.dumps(_normalize_numbers(a), sort_keys=True, ensure_ascii=False)
            == json.dumps(_normalize_numbers(b), sort_keys=True, ensure_ascii=False))


def backup_path(path: Path) -> Path:
    """Wohin die .bak-Kopie von `path` gehoert: unter BACKUPS_DIR, Struktur gespiegelt.

    `sequences/all_dayli.json` -> `backups/sequences/all_dayli.json.bak`. Die
    Unterordner sind noetig, sonst ueberschrieben `item_scans/foo.json` und
    `boss_scans/foo.json` dieselbe Sicherung.

    Absolute Pfade werden relativ zum Arbeitsverzeichnis gelegt; liegt eine Datei
    ausserhalb, bleibt nur ihr Name uebrig.
    """
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.relative_to(Path.cwd())
        except ValueError:
            p = Path(p.name)
    return Path(BACKUPS_DIR) / p.with_suffix(p.suffix + ".bak")


def _write(path: Path, data) -> None:
    """Sicherung anlegen, dann schreiben - im selben Format wie die App selbst.

    compact_json + atomic_write, sonst wechselte die Formatierung bei jedem Save
    hin und her. Die Sicherung liegt unter `backups/` statt neben dem Original,
    damit ein `*.json`-Glob sie nicht erwischt; der Ordner entsteht erst hier.
    """
    backup = backup_path(path)
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    atomic_write(path, compact_json(data))


class SweepResult:
    """Was der Durchgang gefunden hat. `changed` ist die Liste (Pfad, Meldungen)."""

    def __init__(self) -> None:
        self.changed: list[tuple[Path, list[str]]] = []
        self.current: int = 0
        self.skipped: list[Path] = []
        self.written: bool = False

    @property
    def changed_count(self) -> int:
        return len(self.changed)

    def __bool__(self) -> bool:
        """True = es gab etwas zu tun."""
        return bool(self.changed or self.skipped)


def sweep(write: bool = False) -> SweepResult:
    """Alle Dateien pruefen und (bei write=True) sauber zurueckschreiben.

    Gibt ein SweepErgebnis zurueck und druckt selbst NICHTS - die Ausgabe entscheidet
    der Aufrufer (Start: knapp; Tool: ausfuehrlich).

    Einen Punkte-Kontext gibt es nicht mehr: eine Sequenz bringt ihre Punkte im
    eigenen Feld mit, `load_sequence_file()` loest sie daraus auf.
    """
    result = SweepResult()
    result.written = write

    for path, kind, rt in collect_files():
        raw = _load(path)
        if raw is None:
            result.skipped.append(path)
            continue

        # Auf einer Kopie, damit die Meldungen nicht vom Round-Trip verfaelscht werden.
        _, messages = migrate(json.loads(json.dumps(raw)), kind)

        # Die Loader melden ihre Migration selbst - hier stumm, sonst stehen dieselben
        # Zeilen doppelt im Protokoll.
        with contextlib.redirect_stdout(io.StringIO()):
            clean = rt(path)

        if clean is None:
            result.skipped.append(path)
            continue

        if not messages and _equal(raw, clean):
            result.current += 1
            continue

        if not messages:
            messages = ["Felder aufgeraeumt (Round-Trip durch Loader + Serializer)"]
        result.changed.append((path, messages))
        if write:
            _write(path, clean)

    return result


def sweep_on_start() -> SweepResult:
    """Start-Durchgang: schreibt, und meldet nur wenn es etwas zu melden gab.

    Bewusst nach `init_directories()` und VOR dem Laden aufrufen - dann liest der Rest
    des Starts schon die aufgeraeumten Dateien und die Loader haben nichts zu melden.
    """
    from ..utils import col, hint, warn

    result = sweep(write=True)
    if not result:
        return result  # Normalfall: alles aktuell, kein Wort darueber

    if result.changed:
        print(f"\n{col('[MIGRATION]', 'cyan')} "
              f"{result.changed_count} Datei(en) aufs aktuelle Format gehoben:")
        for path, messages in result.changed:
            print(f"            {path.name}")
            for m in messages:
                print(f"              - {m}")
        print(f"            {hint(f'Sicherungen liegen unter {BACKUPS_DIR}/.')}")

    for path in result.skipped:
        print(warn(f"[MIGRATION] {path.name} nicht lesbar - bleibt unveraendert."))

    if result.changed:
        print()
    return result
