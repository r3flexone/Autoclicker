#!/usr/bin/env python3
"""
Hebt alle JSON-Dateien auf das aktuelle Schema und schreibt sie sauber zurueck.

Der Unterschied zu sync_json.py: das hier ist kein Feld-fuer-Feld-Nachpflegen, sondern
die versionierte Migration aus autoclicker/persistence/migration.py. Danach enthaelt
jede Datei genau das aktuelle Schema - keine Altformate, keine toten Felder.

    python tools/migrate.py            # zeigt nur an, was passieren wuerde
    python tools/migrate.py --write    # schreibt (mit Backup)

Backups landen als <datei>.bak neben dem Original. Ein zweiter Lauf findet nichts mehr
zu tun - genau daran erkennt man, dass alles sauber ist.
"""

from __future__ import annotations

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
    KIND_POINTS, KIND_SEQUENCE, SCHEMA_VERSION, file_version, migrate,
)

SEQUENCES_DIR = ROOT / "sequences"
POINTS_FILE = SEQUENCES_DIR / "points.json"


def _lade(pfad: Path):
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [FEHLER] {pfad.name}: {e}")
        return None


def _punkte() -> list:
    """Punkte fuer die Koordinaten-Zuordnung. Fehlen sie, laeuft die Migration ohne
    Verknuepfung durch - kein Grund abzubrechen."""
    data = _lade(POINTS_FILE) if POINTS_FILE.exists() else None
    if isinstance(data, dict):
        return data.get("points") or []
    if isinstance(data, list):
        return data
    return []


def _schreibe(pfad: Path, data: dict) -> None:
    backup = pfad.with_suffix(pfad.suffix + ".bak")
    if not backup.exists():
        backup.write_text(pfad.read_text(encoding="utf-8"), encoding="utf-8")
    pfad.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    schreiben = "--write" in sys.argv
    print(f"Ziel-Schema: {SCHEMA_VERSION}")
    print("Modus:", "SCHREIBEN (Backups als *.bak)" if schreiben else "nur anzeigen (--write zum Schreiben)")

    punkte = _punkte()
    print(f"Punkte fuer die Zuordnung: {len(punkte)}\n")

    dateien = []
    if POINTS_FILE.exists():
        dateien.append((POINTS_FILE, KIND_POINTS))
    if SEQUENCES_DIR.exists():
        for p in sorted(SEQUENCES_DIR.glob("*.json")):
            if p != POINTS_FILE:
                dateien.append((p, KIND_SEQUENCE))

    if not dateien:
        print("Keine Dateien gefunden - nichts zu tun.")
        return 0

    geaendert = aktuell = fehler = 0
    for pfad, kind in dateien:
        data = _lade(pfad)
        if data is None:
            fehler += 1
            continue

        vorher = file_version(data)
        data, meldungen = migrate(data, kind, {"points": punkte})

        if not meldungen and vorher == SCHEMA_VERSION:
            aktuell += 1
            continue

        geaendert += 1
        print(f"  {pfad.name}  (Schema {vorher} -> {SCHEMA_VERSION})")
        for m in meldungen:
            print(f"      - {m}")
        if not meldungen:
            print("      - nur Versions-Stempel ergaenzt")
        if schreiben:
            _schreibe(pfad, data)

    print(f"\n{geaendert} angepasst, {aktuell} bereits aktuell, {fehler} Fehler.")
    if geaendert and not schreiben:
        print("Nichts geschrieben. Mit --write erneut ausfuehren.")
    elif geaendert:
        print("Geschrieben. Ein zweiter Lauf sollte nichts mehr finden.")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
