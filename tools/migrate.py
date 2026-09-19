#!/usr/bin/env python3
"""Hebt ALLE JSON-Dateien auf den aktuellen Stand und schreibt sie sauber zurueck.

Normalerweise nicht noetig: der Autoclicker macht denselben Durchgang bei jedem
Start (`migrate_on_start`, Default an).

    python tools/migrate.py            # zeigt nur an, was passieren wuerde
    python tools/migrate.py --write    # schreibt (mit Backup)

Die Logik steckt in `persistence/sweep.py`; hier ist nur die CLI drumherum.
Pro Datei laufen zwei Aufraeum-Arten: die MIGRATION hebt Altformate (wird im
Klartext gemeldet), der ROUND-TRIP schickt die Datei durch Loader + Serializer
und raeumt damit auch Dateitypen ohne Migrationsschritt auf.

Backups landen unter backups/<ordner>/<datei>.bak. Ein zweiter Lauf findet
nichts mehr zu tun — genau daran erkennt man, dass alles sauber ist.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

try:
    import msvcrt  # noqa: F401  (echtes Modul auf Windows)
except ImportError:
    sys.modules["msvcrt"] = types.ModuleType("msvcrt")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from autoclicker.persistence.migration import SCHEMA_VERSION  # noqa: E402
from autoclicker.persistence.paths import BACKUPS_DIR  # noqa: E402
from autoclicker.persistence.sweep import collect_files, sweep  # noqa: E402


def main() -> int:
    write_out = "--write" in sys.argv
    print(f"Ziel-Schema: {SCHEMA_VERSION}")
    print("Modus:", f"SCHREIBEN (Backups unter {BACKUPS_DIR}/)" if write_out
          else "nur anzeigen (--write zum Schreiben)")

    files = collect_files()
    if not files:
        print("\nKeine Dateien gefunden - nichts zu tun.")
        return 0
    print(f"Gefundene Dateien: {len(files)}\n")

    result = sweep(write=write_out)

    for path, messages in result.changed:
        try:
            name = path.relative_to(ROOT)
        except ValueError:
            name = path
        print(f"  {name}")
        for m in messages:
            print(f"      - {m}")
    for path in result.skipped:
        print(f"  [UEBERSPRUNGEN] {path.name}: nicht ladbar, bleibt unveraendert")

    print(f"\n{result.changed_count} angepasst, {result.current} bereits aktuell, "
          f"{len(result.skipped)} uebersprungen.")
    if result.changed and not write_out:
        print("Nichts geschrieben. Mit --write erneut ausfuehren.")
    elif result.changed:
        print("Geschrieben. Ein zweiter Lauf sollte nichts mehr finden.")
    return 1 if result.skipped else 0


if __name__ == "__main__":
    sys.exit(main())
