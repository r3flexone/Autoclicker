#!/usr/bin/env python3
"""
Hebt ALLE JSON-Dateien auf den aktuellen Stand und schreibt sie sauber zurueck.

Der Unterschied zu sync_json.py: das hier ist kein Feld-fuer-Feld-Nachpflegen, sondern
die Schleuse aus autoclicker/persistence/migration.py. Danach enthaelt jede Datei genau
das aktuelle Format - keine Altformate, keine toten Felder.

    python tools/migrate.py            # zeigt nur an, was passieren wuerde
    python tools/migrate.py --write    # schreibt (mit Backup)

Zwei Arten von Aufraeumen laufen dabei:

1. MIGRATION  - Altformate werden ins aktuelle Format gehoben (Sequenz-Phasen,
                point_id, confirm_point, Punkt-IDs). Wird im Klartext gemeldet.
2. ROUND-TRIP - die Datei wird zusaetzlich durch Loader + Serializer geschickt.
                Der Loader kennt nur aktuelle Felder, der Serializer schreibt nur
                aktuelle Felder - alles, was dazwischen wegfaellt, war Altbestand.
                Das raeumt auch Dateitypen auf, die keinen Migrationsschritt haben.

Backups landen als <datei>.bak neben dem Original. Ein zweiter Lauf findet nichts mehr
zu tun - genau daran erkennt man, dass alles sauber ist.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import types
from pathlib import Path

try:
    import msvcrt  # noqa: F401  (echtes Modul auf Windows)
except ImportError:
    sys.modules["msvcrt"] = types.ModuleType("msvcrt")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from autoclicker.persistence.migration import (  # noqa: E402
    KIND_BOSS_SCAN, KIND_GLOBAL_BOSSES, KIND_ICON_SCAN, KIND_ITEMS, KIND_ITEM_SCAN,
    KIND_POINTS, KIND_SEQUENCE, KIND_SLOTS, SCHEMA_VERSION,
    file_version, migrate, stamp,
)
from autoclicker.persistence import serialization as ser  # noqa: E402
from autoclicker.persistence.item_scans import load_item_scan_file  # noqa: E402
from autoclicker.persistence.boss_scans import load_boss_scan_file  # noqa: E402
from autoclicker.persistence.icon_scans import load_icon_scan_file  # noqa: E402
from autoclicker.persistence.sequences import load_sequence_file  # noqa: E402

SEQUENCES_DIR = ROOT / "sequences"
POINTS_FILE = SEQUENCES_DIR / "points.json"


def _lade(pfad: Path):
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [FEHLER] {pfad.name}: {e}")
        return None


# ---------------------------------------------------------------------------
# Round-Trip: laden + zurueckschreiben. Was der Loader nicht kennt, verschwindet.
# ---------------------------------------------------------------------------

def _rt_sequence(pfad: Path, punkte: list):
    # stamp() wie in save_sequence_file - ohne Versions-Stempel wuerde die Datei beim
    # naechsten Lauf wieder als "Schema 0" gelten und alles noch einmal durchlaufen.
    seq = load_sequence_file(pfad, punkte)
    return stamp(ser._sequence_to_dict(seq)) if seq else None


def _rt_item_scan(pfad: Path, punkte: list):
    cfg = load_item_scan_file(pfad)
    return ser._item_scan_to_dict(cfg) if cfg else None


def _rt_boss_scan(pfad: Path, punkte: list):
    cfg = load_boss_scan_file(pfad)
    return ser._boss_scan_to_dict(cfg) if cfg else None


def _rt_icon_scan(pfad: Path, punkte: list):
    cfg = load_icon_scan_file(pfad)
    return ser._icon_scan_to_dict(cfg) if cfg else None


def _rt_points(pfad: Path, punkte: list):
    """Punkte round-trippen, ohne den globalen State anzufassen."""
    from autoclicker.models import ClickPoint
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
    from autoclicker.models import ItemSlot
    data = _lade(pfad)
    if not isinstance(data, dict):
        return None
    return {name: ser._slot_to_dict(ItemSlot(
        name=s["name"], scan_region=tuple(s["scan_region"]),
        click_pos=tuple(s["click_pos"]),
        slot_color=tuple(s["slot_color"]) if s.get("slot_color") else None))
        for name, s in data.items()}


def _rt_bosses(pfad: Path, punkte: list):
    data = _lade(pfad)
    if not isinstance(data, list):
        return None
    return [ser._boss_profile_to_dict(ser._boss_profile_from_dict(b)) for b in data]


def _rt_config(pfad: Path, punkte: list):
    """config.json: from_dict wirft unbekannte Keys weg, to_dict schreibt die aktuellen."""
    from autoclicker.config import AppConfig
    data = _lade(pfad)
    return AppConfig.from_dict(data).to_dict() if isinstance(data, dict) else None


def _sammle() -> list[tuple[Path, str, object]]:
    """Alle JSON-Dateien der App mit ihrem Typ und ihrer Round-Trip-Funktion."""
    dateien: list[tuple[Path, str, object]] = []

    cfg = ROOT / "config.json"
    if cfg.exists():
        dateien.append((cfg, "config", _rt_config))

    if POINTS_FILE.exists():
        dateien.append((POINTS_FILE, KIND_POINTS, _rt_points))
    if SEQUENCES_DIR.exists():
        for p in sorted(SEQUENCES_DIR.glob("*.json")):
            if p != POINTS_FILE:
                dateien.append((p, KIND_SEQUENCE, _rt_sequence))

    for ordner, kind, rt in (
        ("item_scans", KIND_ITEM_SCAN, _rt_item_scan),
        ("boss_scans", KIND_BOSS_SCAN, _rt_boss_scan),
        ("icon_scans", KIND_ICON_SCAN, _rt_icon_scan),
    ):
        d = ROOT / ordner
        if d.exists():
            for p in sorted(d.glob("*.json")):
                dateien.append((p, kind, rt))

    gb = ROOT / "boss_scans" / "global" / "bosses.json"
    if gb.exists():
        dateien.append((gb, KIND_GLOBAL_BOSSES, _rt_bosses))

    for datei, kind, rt in (
        (ROOT / "items" / "items.json", KIND_ITEMS, _rt_items),
        (ROOT / "slots" / "slots.json", KIND_SLOTS, _rt_slots),
    ):
        if datei.exists():
            dateien.append((datei, kind, rt))

    for ordner, kind, rt in (
        (ROOT / "items" / "presets", KIND_ITEMS, _rt_items),
        (ROOT / "slots" / "presets", KIND_SLOTS, _rt_slots),
    ):
        if ordner.exists():
            for p in sorted(ordner.glob("*.json")):
                dateien.append((p, kind, rt))

    return dateien


def _punkte() -> list:
    """Punkte fuer die Koordinaten-Zuordnung. Fehlen sie, laeuft die Migration ohne
    Verknuepfung durch - kein Grund abzubrechen."""
    data = _lade(POINTS_FILE) if POINTS_FILE.exists() else None
    # Erst normalisieren: Punkte ohne ID taugen nicht als Referenz, und ohne diesen
    # Schritt braeuchte es zwei Laeufe, bis die Schritte ihren Punkt finden.
    data, _ = migrate(data, KIND_POINTS)
    return data if isinstance(data, list) else []


def _schreibe(pfad: Path, data) -> None:
    backup = pfad.with_suffix(pfad.suffix + ".bak")
    if not backup.exists():
        backup.write_text(pfad.read_text(encoding="utf-8"), encoding="utf-8")
    pfad.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _gleich(a, b) -> bool:
    """Inhaltsgleich? Verglichen wird normalisierter JSON-Text, damit
    Schluesselreihenfolge und Einrueckung nicht als Aenderung durchgehen."""
    return (json.dumps(a, sort_keys=True, ensure_ascii=False)
            == json.dumps(b, sort_keys=True, ensure_ascii=False))


def main() -> int:
    schreiben = "--write" in sys.argv
    print(f"Ziel-Schema: {SCHEMA_VERSION}")
    print("Modus:", "SCHREIBEN (Backups als *.bak)" if schreiben
          else "nur anzeigen (--write zum Schreiben)")

    punkte = _punkte()
    print(f"Punkte fuer die Zuordnung: {len(punkte)}")

    dateien = _sammle()
    if not dateien:
        print("\nKeine Dateien gefunden - nichts zu tun.")
        return 0
    print(f"Gefundene Dateien: {len(dateien)}\n")

    geaendert = aktuell = fehler = 0
    for pfad, kind, rt in dateien:
        roh = _lade(pfad)
        if roh is None:
            fehler += 1
            continue

        vorher = file_version(roh)
        # Auf einer Kopie, damit die Meldungen nicht vom Round-Trip verfaelscht werden.
        _, meldungen = migrate(json.loads(json.dumps(roh)), kind, {"points": punkte})

        # Round-Trip ist die eigentliche Reinigung. Scheitert er, bleibt die Datei
        # unangetastet - lieber Altbestand behalten als Daten verlieren.
        # Die Loader melden ihre Migration selbst - hier stumm, sonst stehen dieselben
        # Zeilen doppelt und in der falschen Reihenfolge im Protokoll.
        with contextlib.redirect_stdout(io.StringIO()):
            sauber = rt(pfad, punkte)
        if sauber is None:
            print(f"  [UEBERSPRUNGEN] {pfad.name}: nicht ladbar, bleibt unveraendert")
            fehler += 1
            continue

        if not meldungen and _gleich(roh, sauber):
            aktuell += 1
            continue

        geaendert += 1
        version = f"  (Schema {vorher} -> {SCHEMA_VERSION})" if kind == KIND_SEQUENCE else ""
        print(f"  {pfad.relative_to(ROOT)}{version}")
        for m in meldungen:
            print(f"      - {m}")
        if not meldungen:
            print("      - Felder aufgeraeumt (Round-Trip durch Loader + Serializer)")
        if schreiben:
            _schreibe(pfad, sauber)

    print(f"\n{geaendert} angepasst, {aktuell} bereits aktuell, {fehler} uebersprungen.")
    if geaendert and not schreiben:
        print("Nichts geschrieben. Mit --write erneut ausfuehren.")
    elif geaendert:
        print("Geschrieben. Ein zweiter Lauf sollte nichts mehr finden.")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
