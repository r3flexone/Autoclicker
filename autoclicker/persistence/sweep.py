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

def _lade(pfad: Path):
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def _rt_sequence(pfad: Path):
    from .sequences import load_sequence_file
    seq = load_sequence_file(pfad)
    # stamp() wie in save_sequence_file - ohne Stempel gilt die Datei beim naechsten
    # Start wieder als Schema 0 und laeuft die ganze Kette erneut.
    return stamp(ser._sequence_to_dict(seq)) if seq else None


def _rt_item_scan(pfad: Path):
    from .item_scans import load_item_scan_file
    cfg = load_item_scan_file(pfad)
    return ser._item_scan_to_dict(cfg) if cfg else None


def _rt_boss_scan(pfad: Path):
    from .boss_scans import load_boss_scan_file
    cfg = load_boss_scan_file(pfad)
    return ser._boss_scan_to_dict(cfg) if cfg else None


def _rt_icon_scan(pfad: Path):
    from .icon_scans import load_icon_scan_file
    cfg = load_icon_scan_file(pfad)
    return ser._icon_scan_to_dict(cfg) if cfg else None


def _rt_items(pfad: Path):
    data, _ = migrate(_lade(pfad), KIND_ITEMS)
    if not isinstance(data, dict):
        return None
    return {name: ser._item_to_dict(ser._item_from_dict(i, name))
            for name, i in data.items()}


def _rt_slots(pfad: Path):
    data, _ = migrate(_lade(pfad), KIND_SLOTS)
    if not isinstance(data, dict):
        return None
    return {name: ser._slot_to_dict(ser._slot_from_dict(name, s))
            for name, s in data.items()}


def _rt_bosses(pfad: Path):
    data, _ = migrate(_lade(pfad), KIND_GLOBAL_BOSSES)
    if not isinstance(data, list):
        return None
    return [ser._boss_profile_to_dict(ser._boss_profile_from_dict(b)) for b in data]


def _rt_config(pfad: Path):
    """config.json: from_dict wirft unbekannte Keys weg, to_dict schreibt die aktuellen."""
    from ..config import AppConfig
    data = _lade(pfad)
    return AppConfig.from_dict(data).to_dict() if isinstance(data, dict) else None


KIND_CONFIG = "config"

RoundTrip = Callable[[Path], object]


def _sequences_dir() -> Path:
    from ..config import SEQUENCES_DIR
    return Path(SEQUENCES_DIR)


def sammle_dateien() -> list[tuple[Path, str, RoundTrip]]:
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
    dateien: list[tuple[Path, str, RoundTrip]] = []

    from ..config import CONFIG_FILE
    cfg = Path(CONFIG_FILE)
    if cfg.exists():
        dateien.append((cfg, KIND_CONFIG, _rt_config))

    # Die Punkte haben keine eigene Datei mehr - sie stehen im Feld `points` der
    # `sequence.json` und werden mit ihr round-getrippt.
    seq_dir = _sequences_dir()
    if seq_dir.is_dir():
        for ordner in sorted(e for e in seq_dir.iterdir() if e.is_dir()):
            haupt = ordner / "sequence.json"
            if haupt.exists():
                dateien.append((haupt, KIND_SEQUENCE, _rt_sequence))
            for unter, kind, rt in (
                ("item_scans", KIND_ITEM_SCAN, _rt_item_scan),
                ("boss_scans", KIND_BOSS_SCAN, _rt_boss_scan),
                ("icon_scans", KIND_ICON_SCAN, _rt_icon_scan),
            ):
                d = ordner / unter
                if not d.is_dir():
                    continue
                for datei in sorted(d.glob("*.json")):
                    # Die Boss-Bibliothek liegt als `bibliothek.json` zwischen den
                    # Scan-Konfigurationen (s. `_global_bosses_file`) und ist eine
                    # Liste, kein Scan - mit dem Scan-Loader gelesen waere sie
                    # unlesbar und wuerde als "uebersprungen" gemeldet.
                    if unter == "boss_scans" and datei.name == "bibliothek.json":
                        dateien.append((datei, KIND_GLOBAL_BOSSES, _rt_bosses))
                    else:
                        dateien.append((datei, kind, rt))

    # Presets sind programmweit und gehoeren keiner Sequenz.
    for ordner, kind, rt in (
        (ITEM_PRESETS_DIR, KIND_ITEMS, _rt_items),
        (SLOT_PRESETS_DIR, KIND_SLOTS, _rt_slots),
    ):
        d = Path(ordner)
        if d.is_dir():
            for datei in sorted(d.glob("*.json")):
                dateien.append((datei, kind, rt))

    return dateien


def _zahlen_normalisieren(x):
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
        return {k: _zahlen_normalisieren(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_zahlen_normalisieren(v) for v in x]
    return x


def _gleich(a, b) -> bool:
    """Inhaltsgleich? Normalisierter JSON-Text, damit Schluesselreihenfolge,
    Einrueckung und der Python-Zahlentyp nicht als Aenderung durchgehen."""
    return (json.dumps(_zahlen_normalisieren(a), sort_keys=True, ensure_ascii=False)
            == json.dumps(_zahlen_normalisieren(b), sort_keys=True, ensure_ascii=False))


def sicherungspfad(pfad: Path) -> Path:
    """Wohin die .bak-Kopie von `pfad` gehoert: unter BACKUPS_DIR, Struktur gespiegelt.

    `sequences/all_dayli.json` -> `backups/sequences/all_dayli.json.bak`. Die
    Unterordner sind noetig, sonst ueberschrieben `item_scans/foo.json` und
    `boss_scans/foo.json` dieselbe Sicherung.

    Absolute Pfade werden relativ zum Arbeitsverzeichnis gelegt; liegt eine Datei
    ausserhalb, bleibt nur ihr Name uebrig.
    """
    p = Path(pfad)
    if p.is_absolute():
        try:
            p = p.relative_to(Path.cwd())
        except ValueError:
            p = Path(p.name)
    return Path(BACKUPS_DIR) / p.with_suffix(p.suffix + ".bak")


def _schreibe(pfad: Path, data) -> None:
    """Sicherung anlegen, dann schreiben - im selben Format wie die App selbst.

    compact_json + atomic_write, sonst wechselte die Formatierung bei jedem Save
    hin und her. Die Sicherung liegt unter `backups/` statt neben dem Original,
    damit ein `*.json`-Glob sie nicht erwischt; der Ordner entsteht erst hier.
    """
    backup = sicherungspfad(pfad)
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(pfad.read_text(encoding="utf-8"), encoding="utf-8")
    atomic_write(pfad, compact_json(data))


class SweepErgebnis:
    """Was der Durchgang gefunden hat. `geaendert` ist die Liste (Pfad, Meldungen)."""

    def __init__(self) -> None:
        self.geaendert: list[tuple[Path, list[str]]] = []
        self.aktuell: int = 0
        self.uebersprungen: list[Path] = []
        self.geschrieben: bool = False

    @property
    def anzahl_geaendert(self) -> int:
        return len(self.geaendert)

    def __bool__(self) -> bool:
        """True = es gab etwas zu tun."""
        return bool(self.geaendert or self.uebersprungen)


def sweep(write: bool = False) -> SweepErgebnis:
    """Alle Dateien pruefen und (bei write=True) sauber zurueckschreiben.

    Gibt ein SweepErgebnis zurueck und druckt selbst NICHTS - die Ausgabe entscheidet
    der Aufrufer (Start: knapp; Tool: ausfuehrlich).

    Einen Punkte-Kontext gibt es nicht mehr: eine Sequenz bringt ihre Punkte im
    eigenen Feld mit, `load_sequence_file()` loest sie daraus auf.
    """
    ergebnis = SweepErgebnis()
    ergebnis.geschrieben = write

    for pfad, kind, rt in sammle_dateien():
        roh = _lade(pfad)
        if roh is None:
            ergebnis.uebersprungen.append(pfad)
            continue

        # Auf einer Kopie, damit die Meldungen nicht vom Round-Trip verfaelscht werden.
        _, meldungen = migrate(json.loads(json.dumps(roh)), kind)

        # Die Loader melden ihre Migration selbst - hier stumm, sonst stehen dieselben
        # Zeilen doppelt im Protokoll.
        with contextlib.redirect_stdout(io.StringIO()):
            sauber = rt(pfad)

        if sauber is None:
            ergebnis.uebersprungen.append(pfad)
            continue

        if not meldungen and _gleich(roh, sauber):
            ergebnis.aktuell += 1
            continue

        if not meldungen:
            meldungen = ["Felder aufgeraeumt (Round-Trip durch Loader + Serializer)"]
        ergebnis.geaendert.append((pfad, meldungen))
        if write:
            _schreibe(pfad, sauber)

    return ergebnis


def sweep_beim_start() -> SweepErgebnis:
    """Start-Durchgang: schreibt, und meldet nur wenn es etwas zu melden gab.

    Bewusst nach `init_directories()` und VOR dem Laden aufrufen - dann liest der Rest
    des Starts schon die aufgeraeumten Dateien und die Loader haben nichts zu melden.
    """
    from ..utils import col, hint, warn

    ergebnis = sweep(write=True)
    if not ergebnis:
        return ergebnis  # Normalfall: alles aktuell, kein Wort darueber

    if ergebnis.geaendert:
        print(f"\n{col('[MIGRATION]', 'cyan')} "
              f"{ergebnis.anzahl_geaendert} Datei(en) aufs aktuelle Format gehoben:")
        for pfad, meldungen in ergebnis.geaendert:
            print(f"            {pfad.name}")
            for m in meldungen:
                print(f"              - {m}")
        print(f"            {hint(f'Sicherungen liegen unter {BACKUPS_DIR}/.')}")

    for pfad in ergebnis.uebersprungen:
        print(warn(f"[MIGRATION] {pfad.name} nicht lesbar - bleibt unveraendert."))

    if ergebnis.geaendert:
        print()
    return ergebnis
