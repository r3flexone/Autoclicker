"""
Import/Export-Editor für den Autoclicker.
Ermöglicht das Exportieren und Importieren von kompletten Setups als ZIP
mit optionalem Koordinaten-Remapping für andere Bildschirme.
"""

import os
import time
from datetime import datetime
from pathlib import Path

from ..models import AutoClickerState
from ..utils import safe_input, is_cancel, confirm, interactive_select, col, ok, err, info, hint, header, breadcrumb
from ..winapi import get_cursor_pos


def run_import_export_editor(state: AutoClickerState) -> None:
    """Hauptmenü für Import/Export."""
    print(header("IMPORT / EXPORT"))
    print(f"  {breadcrumb('Hauptmenü', 'Import/Export')}")
    print()
    print(f"  Setups als ZIP exportieren und auf anderen PCs importieren.")
    print(f"  Koordinaten werden automatisch an den neuen Bildschirm angepasst.")
    print()

    menu_options = [
        "Exportieren (alles)",
        "Exportieren (mit Auswahl)",
        "Importieren",
    ]

    choice = interactive_select(menu_options)
    if choice < 0:
        return

    if choice == 0:
        _run_export(state, select_parts=False)
    elif choice == 1:
        _run_export(state, select_parts=True)
    elif choice == 2:
        _run_import(state)


# =============================================================================
# EXPORT
# =============================================================================

def _run_export(state: AutoClickerState, select_parts: bool) -> None:
    print(header("EXPORT"))

    # Auswahl was exportiert wird
    include = {
        "points": True, "sequences": True, "slots": True,
        "items": True, "item_scans": True, "boss_scans": True,
        "config": True,
    }

    if select_parts:
        labels = {
            "points": "Punkte",
            "sequences": "Sequenzen",
            "slots": "Slots",
            "items": "Items + Templates",
            "item_scans": "Item-Scans",
            "boss_scans": "Boss-Scans",
            "config": "Config-Einstellungen",
        }
        print("\n  Was soll exportiert werden?")
        for key, label in labels.items():
            choice = safe_input(f"  {label}? (j/n, Enter = ja): ").strip().lower()
            include[key] = choice != "n"
        print()

    # Zusammenfassung
    with state.lock:
        counts = {
            "points": len(state.points),
            "sequences": len(state.sequences),
            "slots": len(state.global_slots),
            "items": len(state.global_items),
            "item_scans": len(state.item_scans),
            "boss_scans": len(state.boss_scans),
        }

    active = {k: v for k, v in include.items() if v and k != "config"}
    if not any(active.values()) and not include["config"]:
        print(f"  {err('Nichts zum Exportieren ausgewählt!')}")
        return

    print(f"  {col('Wird exportiert:', 'bold')}")
    for key, label in [("points", "Punkte"), ("sequences", "Sequenzen"),
                       ("slots", "Slots"), ("items", "Items"),
                       ("item_scans", "Item-Scans"), ("boss_scans", "Boss-Scans")]:
        if include[key]:
            print(f"    {col('✓', 'green')} {label}: {counts.get(key, 0)}")
    if include["config"]:
        print(f"    {col('✓', 'green')} Config-Einstellungen")
    print()

    # Referenzpunkte setzen
    print(col("  === REFERENZPUNKTE ===", "bold"))
    print()
    print(f"  Beim Import werden diese Punkte auf dem neuen Bildschirm angeklickt.")
    print(f"  Daraus berechnet das Programm die Koordinaten-Anpassung.")
    print()
    print(f"  {col('Tipp:', 'yellow')} Wähle zwei markante Ecken im Spielfenster,")
    print(f"         die auf jedem Bildschirm leicht wiederzufinden sind.")
    print(f"         z.B. linke obere Ecke + rechte untere Ecke des Spielfensters.")
    print()

    ref1 = _get_reference_point(1, "Oben-Links im Spielfenster")
    if ref1 is None:
        return
    ref2 = _get_reference_point(2, "Unten-Rechts im Spielfenster")
    if ref2 is None:
        return

    if ref1 == ref2:
        print(f"\n  {err('Die zwei Referenzpunkte sind identisch! Bitte verschiedene Punkte wählen.')}")
        return

    print(f"\n  Referenz 1: ({ref1[0]}, {ref1[1]})")
    print(f"  Referenz 2: ({ref2[0]}, {ref2[1]})")

    # Dateiname
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    default_name = f"autoclicker_export_{timestamp}.zip"
    print(f"\n  Dateiname (Enter = {default_name}):")
    name_input = safe_input("  > ").strip()
    if is_cancel(name_input):
        print(f"  {info('Abgebrochen')}")
        return
    filename = name_input if name_input else default_name
    if not filename.endswith(".zip"):
        filename += ".zip"

    # Export-Verzeichnis
    export_dir = Path("exports")
    export_dir.mkdir(exist_ok=True)
    filepath = export_dir / filename

    print(f"\n  Exportiere nach: {filepath}")

    from ..import_export import export_bundle
    success, result = export_bundle(
        state, str(filepath), ref1, ref2,
        include_points=include["points"],
        include_sequences=include["sequences"],
        include_slots=include["slots"],
        include_items=include["items"],
        include_item_scans=include["item_scans"],
        include_boss_scans=include["boss_scans"],
        include_config=include["config"],
    )

    if success:
        size = os.path.getsize(result) / 1024
        print(f"\n  {ok(f'Export erfolgreich!')}")
        print(f"  Datei: {col(result, 'cyan')} ({size:.1f} KB)")
        print()
        _print_sharing_guide(filepath, ref1, ref2)
    else:
        print(f"\n  {err(f'Export fehlgeschlagen: {result}')}")


def _get_reference_point(num: int, description: str) -> tuple[int, int] | None:
    """Lässt den Benutzer einen Referenzpunkt setzen."""
    print(f"  Referenzpunkt {num} ({description}):")
    print(f"    Maus an die Stelle bewegen und Enter drücken (oder 'x' zum Abbrechen)")
    result = safe_input(f"    > ").strip()
    if is_cancel(result):
        print(f"  {info('Abgebrochen')}")
        return None
    x, y = get_cursor_pos()
    print(f"    -> ({x}, {y})")
    return (x, y)


def _print_sharing_guide(filepath: Path, ref1: tuple, ref2: tuple) -> None:
    """Zeigt eine Kurzanleitung zum Teilen der Datei."""
    print(col("  === ANLEITUNG FÜR DEN EMPFÄNGER ===", "bold"))
    print()
    print(f"  {col('1.', 'cyan')} Die Datei '{filepath.name}' an den Empfänger schicken")
    print(f"  {col('2.', 'cyan')} Der Empfänger legt die Datei in seinen Autoclicker-Ordner")
    print(f"     oder an einen beliebigen Ort")
    print(f"  {col('3.', 'cyan')} Im Autoclicker: {col('CTRL+ALT+I', 'yellow')} → Importieren")
    print(f"  {col('4.', 'cyan')} Beim Import wird nach 2 Referenzpunkten gefragt:")
    print(f"     - Punkt 1: {col('Oben-Links im Spielfenster', 'green')} (dein Punkt: {ref1[0]},{ref1[1]})")
    print(f"     - Punkt 2: {col('Unten-Rechts im Spielfenster', 'green')} (dein Punkt: {ref2[0]},{ref2[1]})")
    print(f"  {col('5.', 'cyan')} Das Programm passt alle Koordinaten automatisch an!")
    print()
    print(f"  {col('Hinweis:', 'yellow')} Der Empfänger muss die gleichen Stellen im")
    print(f"           Spielfenster anklicken, damit die Anpassung funktioniert.")
    print(f"           Ideal: Fensterecken oder andere feste UI-Elemente.")
    print()


# =============================================================================
# IMPORT
# =============================================================================

def _run_import(state: AutoClickerState) -> None:
    print(header("IMPORT"))

    # Datei suchen
    export_dir = Path("exports")
    zip_files = []

    # Erst im exports/ Ordner suchen
    if export_dir.exists():
        zip_files.extend(sorted(export_dir.glob("*.zip"), key=lambda f: f.stat().st_mtime, reverse=True))

    # Auch im aktuellen Verzeichnis
    zip_files.extend(sorted(Path(".").glob("*.zip"), key=lambda f: f.stat().st_mtime, reverse=True))

    # Deduplizieren
    seen = set()
    unique_zips = []
    for f in zip_files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_zips.append(f)

    if unique_zips:
        print(f"\n  Gefundene ZIP-Dateien:")
        options = [f"{f.name} ({f.stat().st_size / 1024:.1f} KB)" for f in unique_zips[:10]]
        options.append("Anderen Pfad eingeben...")
        choice = interactive_select(options)
        if choice < 0:
            return
        if choice < len(unique_zips[:10]):
            filepath = str(unique_zips[choice])
        else:
            filepath = _ask_filepath()
            if filepath is None:
                return
    else:
        print(f"\n  Keine ZIP-Dateien in ./exports/ oder ./ gefunden.")
        filepath = _ask_filepath()
        if filepath is None:
            return

    # Manifest lesen
    from ..import_export import read_manifest
    success, manifest = read_manifest(filepath)
    if not success:
        print(f"\n  {err(manifest)}")
        return

    # Inhalt anzeigen
    contents = manifest.get("contents", {})
    ref = manifest.get("reference_points", {})
    src_ref1 = tuple(ref.get("point1", [0, 0]))
    src_ref2 = tuple(ref.get("point2", [0, 0]))

    print(f"\n  {col('Inhalt der Export-Datei:', 'bold')}")
    if "points" in contents:
        print(f"    Punkte:      {contents['points']}")
    if "sequences" in contents:
        seqs = contents["sequences"]
        print(f"    Sequenzen:   {len(seqs) if isinstance(seqs, list) else seqs}")
    if "slots" in contents:
        print(f"    Slots:       {contents['slots']}")
    if "items" in contents:
        print(f"    Items:       {contents['items']}")
    if "item_scans" in contents:
        scans = contents["item_scans"]
        print(f"    Item-Scans:  {len(scans) if isinstance(scans, list) else scans}")
    if "boss_scans" in contents:
        bscans = contents["boss_scans"]
        print(f"    Boss-Scans:  {len(bscans) if isinstance(bscans, list) else bscans}")
    if "templates" in contents:
        print(f"    Templates:   {contents['templates']}")
    if "config" in contents:
        print(f"    Config:      ja")

    print(f"\n  Referenzpunkte des Exporters:")
    print(f"    Punkt 1: ({src_ref1[0]}, {src_ref1[1]})")
    print(f"    Punkt 2: ({src_ref2[0]}, {src_ref2[1]})")

    # Remapping oder 1:1?
    print(f"\n  {col('Koordinaten-Anpassung:', 'bold')}")
    print(f"    [1] Remapping (andere Auflösung/Fensterposition)")
    print(f"    [2] 1:1 übernehmen (gleicher Bildschirm)")
    remap_choice = safe_input(f"    Wahl (Enter = 1): ").strip()

    transform = None
    if remap_choice != "2":
        print(f"\n  {col('Deine Referenzpunkte setzen:', 'bold')}")
        print(f"  Klicke die GLEICHEN Stellen im Spielfenster wie der Exporter:")
        print()

        dst_ref1 = _get_reference_point(1, "Oben-Links im Spielfenster")
        if dst_ref1 is None:
            return
        dst_ref2 = _get_reference_point(2, "Unten-Rechts im Spielfenster")
        if dst_ref2 is None:
            return

        if dst_ref1 == dst_ref2:
            print(f"\n  {err('Referenzpunkte sind identisch!')}")
            return

        from ..import_export import compute_transform
        transform = compute_transform(src_ref1, src_ref2, dst_ref1, dst_ref2)

        scale_x = transform["scale_x"]
        scale_y = transform["scale_y"]
        print(f"\n  Skalierung: {scale_x:.2%} x {scale_y:.2%}")
        if abs(scale_x - 1.0) < 0.01 and abs(scale_y - 1.0) < 0.01:
            off_x = transform["offset_x"]
            off_y = transform["offset_y"]
            print(f"  Verschiebung: ({off_x:+.0f}, {off_y:+.0f}) Pixel")
        print()

    # Was importieren?
    import_flags = {}
    print(f"  {col('Was importieren?', 'bold')}")
    parts = [("points", "Punkte"), ("sequences", "Sequenzen"), ("slots", "Slots"),
             ("items", "Items"), ("item_scans", "Item-Scans"),
             ("boss_scans", "Boss-Scans"), ("config", "Config")]
    for key, label in parts:
        if key in contents:
            choice = safe_input(f"    {label}? (j/n, Enter = ja): ").strip().lower()
            import_flags[f"import_{key}"] = choice != "n"

    # Merge oder ersetzen?
    print(f"\n  Bestehende Daten:")
    print(f"    [1] Behalten + ergänzen (Merge)")
    print(f"    [2] Ersetzen (bestehende Daten werden überschrieben)")
    merge_choice = safe_input(f"    Wahl (Enter = 1): ").strip()
    merge = merge_choice != "2"

    # Bestätigung
    print()
    if not confirm("  Importieren?"):
        print(f"  {info('Abgebrochen')}")
        return

    from ..import_export import import_bundle
    success, result = import_bundle(
        state, filepath, transform=transform, merge=merge, **import_flags
    )

    if success:
        print(f"\n  {ok('Import erfolgreich!')}")
        print(f"  Importiert: {result}")
        if transform and transform != {"scale_x": 1.0, "scale_y": 1.0, "offset_x": 0, "offset_y": 0}:
            print(f"\n  {col('Hinweis:', 'yellow')} Koordinaten wurden automatisch angepasst.")
            print(f"           Teste die Sequenz einmal im Debug-Modus (config.json → debug_mode: true)")
            print(f"           um zu prüfen ob alle Positionen stimmen.")
    else:
        print(f"\n  {err(f'Import fehlgeschlagen: {result}')}")


def _ask_filepath() -> str | None:
    """Fragt nach einem Dateipfad."""
    print(f"  Pfad zur ZIP-Datei eingeben:")
    path = safe_input("  > ").strip().strip('"').strip("'")
    if is_cancel(path):
        print(f"  {info('Abgebrochen')}")
        return None
    if not Path(path).exists():
        print(f"  {err(f'Datei nicht gefunden: {path}')}")
        return None
    return path
