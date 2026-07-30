"""Alle JSON-Dateien in einem Durchgang aufs aktuelle Format heben.

Der Unterschied zu `migration.py`: das dort ist reine Datenlogik (dict rein, dict raus),
hier kommt das Dateisystem dazu - welche Datei welchen Typ hat, laden, zurueckschreiben.

Zwei Aufrufer, eine Logik:
- `main.py` beim Programmstart (schreibt, meldet nur wenn etwas passiert ist)
- `tools/migrate.py` von Hand (zeigt per Default nur an)

Warum beim START und nicht beim Speichern
-----------------------------------------
Speichern schreibt sowieso schon das aktuelle Format - jeder Saver geht durch die
Serializer. Das Problem sind Dateien, die man NICHT anfasst: eine alte Sequenz, die man
nur laufen laesst, bliebe auf Platte ewig im Altformat, und der Migrationsschritt
dafuer koennte nie geloescht werden.

Ein Durchgang beim Start loest das: nach dem ersten Start mit einer neuen Version sind
alle Dateien aktuell, der Schritt ist tot und darf raus. Genau so soll das Modul
schrumpfen.

Zwei Regeln fuer den Start-Durchgang:
1. **Still, wenn nichts zu tun ist.** Der Normalfall ist "alles aktuell" - dann kein Wort.
2. **Nie Daten verlieren.** Vor der ersten Aenderung an einer Datei entsteht eine
   .bak-Kopie, und laesst sich eine Datei nicht laden, bleibt sie unangetastet.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Callable, Optional

from .migration import (
    KIND_BOSS_SCAN, KIND_GLOBAL_BOSSES, KIND_ICON_SCAN, KIND_ITEMS, KIND_ITEM_SCAN,
    KIND_POINTS, KIND_SEQUENCE, KIND_SLOTS, file_version, migrate, stamp,
)
from . import serialization as ser
from .paths import (
    BOSS_SCANS_DIR, ICON_SCANS_DIR, ITEMS_FILE, ITEM_PRESETS_DIR,
    ITEM_SCANS_DIR, SLOTS_FILE, SLOT_PRESETS_DIR,
)


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


def _rt_sequence(pfad: Path, punkte: list):
    from .sequences import load_sequence_file
    seq = load_sequence_file(pfad, punkte)
    # stamp() wie in save_sequence_file - ohne Stempel gilt die Datei beim naechsten
    # Start wieder als Schema 0 und laeuft die ganze Kette erneut.
    return stamp(ser._sequence_to_dict(seq)) if seq else None


def _rt_item_scan(pfad: Path, punkte: list):
    from .item_scans import load_item_scan_file
    cfg = load_item_scan_file(pfad)
    return ser._item_scan_to_dict(cfg) if cfg else None


def _rt_boss_scan(pfad: Path, punkte: list):
    from .boss_scans import load_boss_scan_file
    cfg = load_boss_scan_file(pfad)
    return ser._boss_scan_to_dict(cfg) if cfg else None


def _rt_icon_scan(pfad: Path, punkte: list):
    from .icon_scans import load_icon_scan_file
    cfg = load_icon_scan_file(pfad)
    return ser._icon_scan_to_dict(cfg) if cfg else None


def _rt_points(pfad: Path, punkte: list):
    """Punkte round-trippen, ohne den globalen State anzufassen."""
    from ..models import ClickPoint
    data, _ = migrate(_lade(pfad), KIND_POINTS)
    if not isinstance(data, list):
        return None
    raus = []
    for p in data:
        farbe = tuple(int(v) for v in p["color"]) if p.get("color") else None
        raus.append(ser._point_to_dict(ClickPoint(
            p["x"], p["y"], p.get("name", ""), p["id"],
            color=farbe, source=p.get("source", ""))))
    return raus


def _rt_items(pfad: Path, punkte: list):
    data, _ = migrate(_lade(pfad), KIND_ITEMS)
    if not isinstance(data, dict):
        return None
    return {name: ser._item_to_dict(ser._item_from_dict(i)) for name, i in data.items()}


def _rt_slots(pfad: Path, punkte: list):
    from ..models import ItemSlot
    data, _ = migrate(_lade(pfad), KIND_SLOTS)
    if not isinstance(data, dict):
        return None
    return {name: ser._slot_to_dict(ItemSlot(
        name=s["name"], scan_region=tuple(s["scan_region"]),
        click_pos=tuple(s["click_pos"]),
        slot_color=tuple(s["slot_color"]) if s.get("slot_color") else None))
        for name, s in data.items()}


def _rt_bosses(pfad: Path, punkte: list):
    data, _ = migrate(_lade(pfad), KIND_GLOBAL_BOSSES)
    if not isinstance(data, list):
        return None
    return [ser._boss_profile_to_dict(ser._boss_profile_from_dict(b)) for b in data]


def _rt_config(pfad: Path, punkte: list):
    """config.json: from_dict wirft unbekannte Keys weg, to_dict schreibt die aktuellen."""
    from ..config import AppConfig
    data = _lade(pfad)
    return AppConfig.from_dict(data).to_dict() if isinstance(data, dict) else None


KIND_CONFIG = "config"

RoundTrip = Callable[[Path, list], object]


def _sequences_dir() -> Path:
    from ..config import SEQUENCES_DIR
    return Path(SEQUENCES_DIR)


def _points_file() -> Path:
    return _sequences_dir() / "points.json"


def sammle_dateien() -> list[tuple[Path, str, RoundTrip]]:
    """Alle JSON-Dateien der App mit Typ und Round-Trip-Funktion.

    Alle Pfade sind relativ zum Arbeitsverzeichnis - genau wie im laufenden Programm.
    Ein anderes Verzeichnis testet man deshalb mit os.chdir(), nicht durch Umbiegen der
    Konstanten.
    """
    dateien: list[tuple[Path, str, RoundTrip]] = []
    seq_dir = _sequences_dir()
    punkte_datei = _points_file()

    from ..config import CONFIG_FILE
    cfg = Path(CONFIG_FILE)
    if cfg.exists():
        dateien.append((cfg, KIND_CONFIG, _rt_config))

    if punkte_datei.exists():
        dateien.append((punkte_datei, KIND_POINTS, _rt_points))
    if seq_dir.exists():
        for p in sorted(seq_dir.glob("*.json")):
            if p != punkte_datei:
                dateien.append((p, KIND_SEQUENCE, _rt_sequence))

    for ordner, kind, rt in (
        (ITEM_SCANS_DIR, KIND_ITEM_SCAN, _rt_item_scan),
        (BOSS_SCANS_DIR, KIND_BOSS_SCAN, _rt_boss_scan),
        (ICON_SCANS_DIR, KIND_ICON_SCAN, _rt_icon_scan),
    ):
        d = Path(ordner)
        if d.exists():
            for p in sorted(d.glob("*.json")):
                dateien.append((p, kind, rt))

    gb = Path(BOSS_SCANS_DIR) / "global" / "bosses.json"
    if gb.exists():
        dateien.append((gb, KIND_GLOBAL_BOSSES, _rt_bosses))

    for datei, kind, rt in (
        (Path(ITEMS_FILE), KIND_ITEMS, _rt_items),
        (Path(SLOTS_FILE), KIND_SLOTS, _rt_slots),
    ):
        if datei.exists():
            dateien.append((datei, kind, rt))

    for ordner, kind, rt in (
        (ITEM_PRESETS_DIR, KIND_ITEMS, _rt_items),
        (SLOT_PRESETS_DIR, KIND_SLOTS, _rt_slots),
    ):
        d = Path(ordner)
        if d.exists():
            for p in sorted(d.glob("*.json")):
                dateien.append((p, kind, rt))

    return dateien


def _punkte_kontext() -> list:
    """Punkte fuer die Koordinaten-Zuordnung, schon normalisiert.

    Ohne die Normalisierung hier haetten Punkte noch keine IDs und die Schritte koennten
    sie nicht referenzieren - es braeuchte einen zweiten Durchgang.
    """
    data, _ = migrate(_lade(_points_file()), KIND_POINTS)
    return data if isinstance(data, list) else []


def _gleich(a, b) -> bool:
    """Inhaltsgleich? Normalisierter JSON-Text, damit Schluesselreihenfolge und
    Einrueckung nicht als Aenderung durchgehen."""
    return (json.dumps(a, sort_keys=True, ensure_ascii=False)
            == json.dumps(b, sort_keys=True, ensure_ascii=False))


def _schreibe(pfad: Path, data) -> None:
    backup = pfad.with_suffix(pfad.suffix + ".bak")
    if not backup.exists():
        backup.write_text(pfad.read_text(encoding="utf-8"), encoding="utf-8")
    pfad.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


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


def sweep(write: bool = False, punkte: Optional[list] = None) -> SweepErgebnis:
    """Alle Dateien pruefen und (bei write=True) sauber zurueckschreiben.

    Gibt ein SweepErgebnis zurueck und druckt selbst NICHTS - die Ausgabe entscheidet
    der Aufrufer (Start: knapp; Tool: ausfuehrlich).
    """
    ergebnis = SweepErgebnis()
    ergebnis.geschrieben = write
    punkte = _punkte_kontext() if punkte is None else punkte

    for pfad, kind, rt in sammle_dateien():
        roh = _lade(pfad)
        if roh is None:
            ergebnis.uebersprungen.append(pfad)
            continue

        # Auf einer Kopie, damit die Meldungen nicht vom Round-Trip verfaelscht werden.
        _, meldungen = migrate(json.loads(json.dumps(roh)), kind, {"points": punkte})

        # Die Loader melden ihre Migration selbst - hier stumm, sonst stehen dieselben
        # Zeilen doppelt im Protokoll.
        with contextlib.redirect_stdout(io.StringIO()):
            sauber = rt(pfad, punkte)

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
    from ..utils import col, hint, info, warn

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
        print(f"            {hint('Sicherungen liegen als *.bak daneben.')}")

    for pfad in ergebnis.uebersprungen:
        print(warn(f"[MIGRATION] {pfad.name} nicht lesbar - bleibt unveraendert."))

    if ergebnis.geaendert:
        print()
    return ergebnis
