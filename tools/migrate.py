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
from autoclicker.persistence.sweep import sammle_dateien, sweep  # noqa: E402


def main() -> int:
    schreiben = "--write" in sys.argv
    print(f"Ziel-Schema: {SCHEMA_VERSION}")
    print("Modus:", f"SCHREIBEN (Backups unter {BACKUPS_DIR}/)" if schreiben
          else "nur anzeigen (--write zum Schreiben)")

    dateien = sammle_dateien()
    if not dateien:
        print("\nKeine Dateien gefunden - nichts zu tun.")
        return 0
    print(f"Gefundene Dateien: {len(dateien)}\n")

    ergebnis = sweep(write=schreiben)

    for pfad, meldungen in ergebnis.geaendert:
        try:
            name = pfad.relative_to(ROOT)
        except ValueError:
            name = pfad
        print(f"  {name}")
        for m in meldungen:
            print(f"      - {m}")
    for pfad in ergebnis.uebersprungen:
        print(f"  [UEBERSPRUNGEN] {pfad.name}: nicht ladbar, bleibt unveraendert")

    print(f"\n{ergebnis.anzahl_geaendert} angepasst, {ergebnis.aktuell} bereits aktuell, "
          f"{len(ergebnis.uebersprungen)} uebersprungen.")
    if ergebnis.geaendert and not schreiben:
        print("Nichts geschrieben. Mit --write erneut ausfuehren.")
    elif ergebnis.geaendert:
        print("Geschrieben. Ein zweiter Lauf sollte nichts mehr finden.")
    return 1 if ergebnis.uebersprungen else 0


if __name__ == "__main__":
    sys.exit(main())
