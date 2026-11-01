#!/usr/bin/env python3
"""Schickt ALLE JSON-Dateien durch Loader und Serializer und schreibt sie sauber zurueck.

Normalerweise nicht noetig: der Autoclicker macht denselben Durchgang bei jedem
Start (`migrate_on_start`, Default an) — dieses Werkzeug ist sein Trockenlauf.

    python tools/migrate.py            # zeigt nur an, was passieren wuerde
    python tools/migrate.py --write    # schreibt (mit Backup)

Die Logik steckt in `persistence/sweep.py`; hier ist nur die CLI drumherum.
Umgerechnet wird nichts: was der Loader nicht kennt, schreibt der Serializer nicht
zurueck, und genau das raeumt auf. Eine Datei aus einer NEUEREN Fassung des
Programms (hoeheres Schema) bleibt, wie sie ist, und wird gemeldet.

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

from autoclicker.persistence.schema import SCHEMA_VERSION  # noqa: E402
from autoclicker.persistence.paths import BACKUPS_DIR  # noqa: E402
from autoclicker.persistence.sweep import collect_files, sweep  # noqa: E402


def main() -> int:
    write_out = "--write" in sys.argv
    print(f"Schema dieses Stands: {SCHEMA_VERSION}")
    print("Modus:", f"SCHREIBEN (Backups unter {BACKUPS_DIR}/)" if write_out
          else "nur anzeigen (--write zum Schreiben)")

    files = collect_files()
    if not files:
        print("\nKeine Dateien gefunden - nichts zu tun.")
        return 0
    print(f"Gefundene Dateien: {len(files)}\n")

    result = sweep(write=write_out)

    for path in result.changed:
        try:
            name = path.relative_to(ROOT)
        except ValueError:
            name = path
        print(f"  {name}  (Felder aufgeraeumt)")
    for path, version in result.newer:
        print(f"  [NEUERE FASSUNG] {path.name}: Schema {version}, bleibt unveraendert")
    for path in result.skipped:
        print(f"  [UEBERSPRUNGEN] {path.name}: nicht ladbar, bleibt unveraendert")

    print(f"\n{result.changed_count} angepasst, {result.current} bereits aktuell, "
          f"{len(result.newer)} aus einer neueren Fassung, "
          f"{len(result.skipped)} uebersprungen.")
    if result.changed and not write_out:
        print("Nichts geschrieben. Mit --write erneut ausfuehren.")
    elif result.changed:
        print("Geschrieben. Ein zweiter Lauf sollte nichts mehr finden.")
    return 1 if result.skipped else 0


if __name__ == "__main__":
    sys.exit(main())
