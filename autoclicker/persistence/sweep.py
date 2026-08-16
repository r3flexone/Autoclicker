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
   .bak-Kopie unter `backups/` (Struktur gespiegelt), und laesst sich eine Datei nicht
   laden, bleibt sie unangetastet.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Callable, Optional

from .migration import (
    KIND_BOSS_SCAN, KIND_GLOBAL_BOSSES, KIND_ICON_SCAN, KIND_ITEMS, KIND_ITEM_SCAN,
    KIND_POINTS, KIND_SEQUENCE, KIND_SLOTS, migrate, stamp,
)
from ..utils import atomic_write, compact_json
from . import serialization as ser
from .paths import (
    BACKUPS_DIR, BOSS_SCANS_DIR, ICON_SCANS_DIR, ITEMS_FILE, ITEM_PRESETS_DIR,
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
    return {name: ser._item_to_dict(ser._item_from_dict(i, name))
            for name, i in data.items()}


def _rt_slots(pfad: Path, punkte: list):
    data, _ = migrate(_lade(pfad), KIND_SLOTS)
    if not isinstance(data, dict):
        return None
    return {name: ser._slot_to_dict(ser._slot_from_dict(name, s))
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


def _punkte_schreibfertig(punkte: list) -> list:
    """Rohe Punkt-Dicts durch den Serializer, damit points.json einheitlich aussieht -
    egal ob ein Eintrag aus der Datei kam oder gerade von der Migration angelegt wurde."""
    from ..models import ClickPoint
    raus = []
    for p in punkte:
        farbe = tuple(int(v) for v in p["color"]) if p.get("color") else None
        raus.append(ser._point_to_dict(ClickPoint(
            p["x"], p["y"], p.get("name", ""), p["id"],
            color=farbe, source=p.get("source", ""))))
    return raus


def _punkte_kontext() -> list:
    """Punkte fuer die Koordinaten-Zuordnung, schon normalisiert.

    Ohne die Normalisierung hier haetten Punkte noch keine IDs und die Schritte koennten
    sie nicht referenzieren - es braeuchte einen zweiten Durchgang.
    """
    data, _ = migrate(_lade(_points_file()), KIND_POINTS)
    return data if isinstance(data, list) else []


def _zahlen_normalisieren(x):
    """int und float derselben Zahl angleichen - JSON kennt nur EINEN Zahlentyp.

    `600` und `600.0` sind dieselbe Zahl; dass Python daraus zwei Typen macht, ist ein
    Artefakt und kein Unterschied im Dateiformat. Ohne das galt eine von Hand auf `600`
    getippte Wartezeit als "aufzuraeumen", weil der Loader daraus `600.0` macht — der
    Durchgang schrieb die Datei um, legte ein .bak an und meldete eine Migration, die
    inhaltlich nichts tat.

    bool bleibt bool: `True` darf nicht als `1.0` durchgehen, sonst waere ein
    umgekipptes Flag unsichtbar.
    """
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, dict):
        return {k: _zahlen_normalisieren(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_zahlen_normalisieren(v) for v in x]
    return x


def _gleich(a, b) -> bool:
    """Inhaltsgleich? Normalisierter JSON-Text, damit Schluesselreihenfolge,
    Einrueckung und der Python-Zahlentyp nicht als Aenderung durchgehen."""
    return (json.dumps(_zahlen_normalisieren(a), sort_keys=True, ensure_ascii=False)
            == json.dumps(_zahlen_normalisieren(b), sort_keys=True, ensure_ascii=False))


def sicherungspfad(pfad: Path) -> Path:
    """Wohin die .bak-Kopie von `pfad` gehoert: unter BACKUPS_DIR, Struktur gespiegelt.

    `sequences/all_dayli.json` -> `backups/sequences/all_dayli.json.bak`

    Die Unterordner werden mitgenommen, weil sonst `item_scans/foo.json` und
    `boss_scans/foo.json` dieselbe Sicherung ueberschrieben - gleicher Dateiname, und
    die zweite Datei haette keine mehr.

    Absolute Pfade werden relativ zum Arbeitsverzeichnis gelegt (die Pfad-Konstanten sind
    CWD-relativ). Liegt eine Datei ausserhalb, bleibt nur ihr Name uebrig - ohne das
    entstuende unter backups/ eine Kopie des ganzen Laufwerkspfads.
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

    compact_json + atomic_write, damit die Datei nach dem Start-Durchgang genauso aussieht
    wie nach einem normalen Speichern. Sonst wechselte die Formatierung bei jedem Save
    hin und her.

    Die Sicherung liegt unter `backups/` statt neben dem Original: dort stoert sie den
    Blick auf die eigentlichen Daten nicht, und ein `*.json`-Glob ueber `sequences/`
    kann sie gar nicht erst erwischen. Angelegt wird der Ordner erst hier - gab es nie
    etwas zu sichern, entsteht er auch nicht.
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


def sweep(write: bool = False, punkte: Optional[list] = None) -> SweepErgebnis:
    """Alle Dateien pruefen und (bei write=True) sauber zurueckschreiben.

    Gibt ein SweepErgebnis zurueck und druckt selbst NICHTS - die Ausgabe entscheidet
    der Aufrufer (Start: knapp; Tool: ausfuehrlich).
    """
    ergebnis = SweepErgebnis()
    ergebnis.geschrieben = write
    punkte = _punkte_kontext() if punkte is None else punkte
    # Die Sequenz-Migration darf Punkte ANLEGEN (Koordinaten, die vorher nur im Schritt
    # standen). Sie landen in dieser Liste - gemerkt wird die Ausgangslaenge, damit am
    # Ende feststeht, ob points.json nachgeschrieben werden muss.
    punkte_vorher = len(punkte)

    for pfad, kind, rt in sammle_dateien():
        roh = _lade(pfad)
        if roh is None:
            ergebnis.uebersprungen.append(pfad)
            continue

        # Auf einer Kopie, damit die Meldungen nicht vom Round-Trip verfaelscht werden.
        # Auch die Punkte-Liste wird kopiert: dieser Lauf dient nur der Meldung, und die
        # Sequenz-Migration legt inzwischen Punkte an - sonst entstuenden sie zweimal
        # bzw. auch fuer eine Datei, die der Round-Trip danach gar nicht laden kann.
        _, meldungen = migrate(json.loads(json.dumps(roh)), kind,
                               {"points": json.loads(json.dumps(punkte))})

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

    # points.json zuletzt: erst jetzt steht fest, ob eine Sequenz-Migration Punkte
    # angelegt hat. Wuerde man das oben in der Schleife erledigen, waere die Datei
    # geschrieben, bevor die Sequenzen ueberhaupt gelesen sind - und die neuen Punkte
    # existierten beim naechsten Start nicht mehr.
    neu = len(punkte) - punkte_vorher
    if neu > 0:
        pfad = _points_file()
        ergebnis.geaendert.append(
            (pfad, [f"{neu} Punkt(e) aus Sequenz-Koordinaten uebernommen"]))
        if write:
            _schreibe(pfad, _punkte_schreibfertig(punkte))

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
