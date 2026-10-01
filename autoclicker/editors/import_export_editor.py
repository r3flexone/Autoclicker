"""
Import/Export-Editor für den Autoclicker.
Ermöglicht das Exportieren und Importieren von kompletten Setups als ZIP
mit optionalem Koordinaten-Remapping für andere Bildschirme.
"""

import os
from datetime import datetime
from pathlib import Path

from ..models import AutoClickerState
from ..utils import safe_input, is_cancel, confirm, interactive_select, col, ok, err, info, warn, header, breadcrumb
from ..winapi import get_cursor_pos, get_virtual_desktop


def run_import_export_editor(state: AutoClickerState) -> None:
    """Hauptmenü für Import/Export."""
    print(header("IMPORT / EXPORT"))
    print(f"  {breadcrumb('Hauptmenü', 'Import/Export')}")
    print()
    print("  Setups als ZIP exportieren und auf anderen PCs importieren.")
    print("  Koordinaten werden automatisch an den neuen Bildschirm angepasst.")
    print()

    menu_options = [
        "Exportieren (alles)",
        "Exportieren (mit Auswahl)",
        "Importieren",
        "Übersicht: gespeicherte Daten & Presets",
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
    elif choice == 3:
        _show_data_overview(state)


# =============================================================================
# ÜBERSICHT (gespeicherte Daten + Presets)
# =============================================================================

def _show_data_overview(state: AutoClickerState) -> None:
    """Zeigt was aktuell im State liegt und welche Presets/Sequenzen verfügbar sind.

    Hilft, vor einem Export zu sehen was mitgenommen wird und welche Presets es
    überhaupt gibt (Slot-/Item-Presets liegen separat von den aktiven Daten).
    """
    from ..persistence import (
        list_slot_presets, list_item_presets, list_available_sequences,
        load_sequence_file,
    )

    print(header("ÜBERSICHT: GESPEICHERTE DATEN"))

    with state.lock:
        print(f"\n  {col('Aktiver State (wird beim Export mitgenommen):', 'bold')}")
        print(f"    Punkte:      {len(state.points)}")
        print(f"    Slots:       {len(state.global_slots)}")
        print(f"    Items:       {len(state.global_items)}")
        print(f"    Item-Scans:  {len(state.item_scans)}")
        print(f"    Boss-Scans:  {len(state.boss_scans)}")
        print(f"    Icon-Scans:  {len(state.icon_scans)}")

    # Gespeicherte Sequenzen (mit Beschreibung)
    sequences = list_available_sequences()
    print(f"\n  {col('Gespeicherte Sequenzen:', 'bold')} ({len(sequences)})")
    if sequences:
        for name, path in sequences:
            seq = load_sequence_file(path)
            desc = f" — {seq.description}" if seq and seq.description else ""
            print(f"    {col('•', 'cyan')} {name}{col(desc, 'gray') if desc else ''}")
    else:
        print(f"    {info('(keine)')}")

    # Slot-Presets
    slot_presets = list_slot_presets()
    print(f"\n  {col('Slot-Presets:', 'bold')} ({len(slot_presets)})")
    if slot_presets:
        for pname, _, count in slot_presets:
            print(f"    {col('•', 'cyan')} {pname} ({count} Slots)")
    else:
        print(f"    {info('(keine)')}")

    # Item-Presets
    item_presets = list_item_presets()
    print(f"\n  {col('Item-Presets:', 'bold')} ({len(item_presets)})")
    if item_presets:
        for pname, _, count in item_presets:
            print(f"    {col('•', 'cyan')} {pname} ({count} Items)")
    else:
        print(f"    {info('(keine)')}")
    print()


# =============================================================================
# EXPORT
# =============================================================================

def _run_export(state: AutoClickerState, select_parts: bool) -> None:
    """Export in Stufen: Umfang → Referenz (Fenster oder zwei Punkte) → Datei → schreiben."""
    print(header("EXPORT"))
    include = _ask_export_parts(select_parts)
    if not include["sequences"] and not include["config"]:
        print(f"  {err('Nichts zum Exportieren ausgewählt!')}")
        return
    _print_export_summary(include)

    references = _export_references(state)
    if references is None:
        return
    ref1, ref2, source_window = references
    filepath = _ask_export_path()
    if filepath is None:
        return

    print(f"\n  Exportiere nach: {filepath}")
    from ..import_export import export_bundle
    success, result = export_bundle(
        state, str(filepath), ref1, ref2,
        include_sequences=include["sequences"],
        include_config=include["config"],
        source_window=source_window,
    )
    if success:
        size = os.path.getsize(result) / 1024
        print(f"\n  {ok('Export erfolgreich!')}")
        print(f"  Datei: {col(result, 'cyan')} ({size:.1f} KB)")
        print()
        _print_sharing_guide(filepath, ref1, ref2)
    else:
        print(f"\n  {err(f'Export fehlgeschlagen: {result}')}")


def _ask_export_parts(select_parts: bool) -> dict:
    """Was ins Bündel kommt — ohne Auswahl alles."""
    include = {"sequences": True, "config": True}
    if not select_parts:
        return include
    labels = {
        "sequences": "Sequenzordner (inkl. Punkte, Scans und Vorlagen)",
        "config": "Config-Einstellungen",
    }
    print("\n  Was soll exportiert werden?")
    for key, label in labels.items():
        choice = safe_input(f"  {label}? (j/n, Enter = ja): ").strip().lower()
        include[key] = choice != "n"
    print()
    return include


def _print_export_summary(include: dict) -> None:
    from ..persistence import list_available_sequences
    print(f"  {col('Wird exportiert:', 'bold')}")
    if include["sequences"]:
        print(f"    {col('✓', 'green')} Sequenzordner: {len(list_available_sequences())}")
    if include["config"]:
        print(f"    {col('✓', 'green')} Config-Einstellungen")
    print()


def _export_references(state: AutoClickerState):
    """Die Referenz fürs Umrechnen beim Empfänger: `(ref1, ref2, Fenster)` oder None.

    Bevorzugt die Ecken des Spielfensters (dann rechnet der Import selbst um),
    sonst zwei Punkte von Hand. None = abgebrochen oder unbrauchbar (gesagt).
    """
    from ..winapi import get_client_rect_by_title
    win_title = state.config.window_focus_title
    source_window = get_client_rect_by_title(win_title) if win_title else None
    if source_window:
        sl, st, sr, sb = source_window
        print(col("  === SPIELFENSTER ERKANNT ===", "bold"))
        print(f"  Fenster '{win_title}': {sr - sl}x{sb - st} px @ ({sl}, {st})")
        print(f"  {info('Beim Import wird die Skalierung automatisch aus der Fenstergrösse abgeleitet.')}")
        print()
        return (sl, st), (sr, sb), source_window

    print(col("  === REFERENZPUNKTE ===", "bold"))
    print()
    if win_title:
        print(f"  {info(f'Spielfenster „{win_title}“ nicht gefunden — nutze manuelle Referenzpunkte.')}")
    print("  Beim Import werden diese Punkte auf dem neuen Bildschirm angeklickt.")
    print("  Daraus berechnet das Programm die Koordinaten-Anpassung.")
    print()
    print(f"  {col('Tipp:', 'yellow')} Wähle zwei markante Ecken im Spielfenster,")
    print("         z.B. linke obere Ecke + rechte untere Ecke des Spielfensters.")
    print()
    refs = _ask_two_references(
        "Die zwei Referenzpunkte sind identisch! Bitte verschiedene Punkte wählen.")
    if refs is None:
        return None
    print(f"\n  Referenz 1: ({refs[0][0]}, {refs[0][1]})")
    print(f"  Referenz 2: ({refs[1][0]}, {refs[1][1]})")
    return refs[0], refs[1], None


def _ask_two_references(same_message: str):
    """Zwei Punkte im Spielfenster (oben links, unten rechts) — oder None.

    Geteilt von Export und Import: beide brauchen dieselben zwei Stellen, und
    zwei gleiche Punkte geben keine Umrechnung her.
    """
    ref1 = _get_reference_point(1, "Oben-Links im Spielfenster")
    if ref1 is None:
        return None
    ref2 = _get_reference_point(2, "Unten-Rechts im Spielfenster")
    if ref2 is None:
        return None
    if ref1 == ref2:
        print(f"\n  {err(same_message)}")
        return None
    return ref1, ref2


def _ask_export_path():
    """Wohin das Bündel kommt (unter `exports/`, '.zip' wird ergänzt) — oder None."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    default_name = f"autoclicker_export_{timestamp}.zip"
    print(f"\n  Dateiname (Enter = {default_name}):")
    name_input = safe_input("  > ").strip()
    if is_cancel(name_input):
        print(f"  {info('Abgebrochen')}")
        return None
    filename = name_input or default_name
    if not filename.endswith(".zip"):
        filename += ".zip"
    export_dir = Path("exports")
    export_dir.mkdir(exist_ok=True)
    return export_dir / filename


def _get_reference_point(num: int, description: str) -> tuple[int, int] | None:
    """Lässt den Benutzer einen Referenzpunkt setzen."""
    print(f"  Referenzpunkt {num} ({description}):")
    print("    Maus an die Stelle bewegen und Enter drücken (oder 'x' zum Abbrechen)")
    result = safe_input("    > ").strip()
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
    print("     oder an einen beliebigen Ort")
    print(f"  {col('3.', 'cyan')} Im Autoclicker: {col('CTRL+ALT+I', 'yellow')} → Importieren")
    print(f"  {col('4.', 'cyan')} Beim Import wird nach 2 Referenzpunkten gefragt:")
    print(f"     - Punkt 1: {col('Oben-Links im Spielfenster', 'green')} (dein Punkt: {ref1[0]},{ref1[1]})")
    print(f"     - Punkt 2: {col('Unten-Rechts im Spielfenster', 'green')} (dein Punkt: {ref2[0]},{ref2[1]})")
    print(f"  {col('5.', 'cyan')} Das Programm passt alle Koordinaten automatisch an!")
    print()
    print(f"  {col('Hinweis:', 'yellow')} Der Empfänger muss die gleichen Stellen im")
    print("           Spielfenster anklicken, damit die Anpassung funktioniert.")
    print("           Ideal: Fensterecken oder andere feste UI-Elemente.")
    print()


# =============================================================================
# IMPORT
# =============================================================================

def _run_import(state: AutoClickerState) -> None:
    """Import in Stufen: Datei → Manifest zeigen → Umrechnung → Umfang → importieren."""
    print(header("IMPORT"))
    filepath = _choose_bundle()
    if filepath is None:
        return

    from ..import_export import read_manifest
    success, manifest = read_manifest(filepath)
    if not success:
        print(f"\n  {err(manifest)}")
        return
    contents = manifest.get("contents", {})
    _print_bundle_contents(manifest)

    transform = _import_transform(state, manifest)
    if transform is _CANCELLED:
        return
    if transform:
        print(f"\n  Skalierung: {transform['scale_x']:.2%} x {transform['scale_y']:.2%}")
        print(f"  Verschiebung: ({transform['offset_x']:+.0f}, {transform['offset_y']:+.0f}) Pixel")
        print()

    import_flags = _ask_import_parts(contents)
    print("\n  Bestehende Daten:")
    print("    [1] Behalten + ergänzen (Merge)")
    print("    [2] Ersetzen (bestehende Daten werden überschrieben)")
    merge = safe_input("    Wahl (Enter = 1): ").strip() != "2"

    print()
    if not confirm("  Importieren?"):
        print(f"  {info('Abgebrochen')}")
        return

    from ..import_export import import_bundle
    success, result = import_bundle(
        state, filepath, transform=transform, merge=merge, **import_flags
    )
    if success:
        _report_import(state, result, transform)
    else:
        print(f"\n  {err(f'Import fehlgeschlagen: {result}')}")


# Abbruch ist hier nicht None: „keine Umrechnung" (1:1) ist ein gültiges Ergebnis.
_CANCELLED = object()


def _choose_bundle():
    """Die ZIP-Datei: aus `exports/` und dem Arbeitsordner (neueste zuerst) oder ein Pfad."""
    candidates = []
    export_dir = Path("exports")
    if export_dir.exists():
        candidates.extend(sorted(export_dir.glob("*.zip"),
                                 key=lambda f: f.stat().st_mtime, reverse=True))
    candidates.extend(sorted(Path(".").glob("*.zip"),
                             key=lambda f: f.stat().st_mtime, reverse=True))
    by_path = {}
    for f in candidates:                     # eine Datei, die in beiden liegt, einmal
        by_path.setdefault(f.resolve(), f)
    unique_zips = list(by_path.values())

    if not unique_zips:
        print("\n  Keine ZIP-Dateien in ./exports/ oder ./ gefunden.")
        return _ask_filepath()

    print("\n  Gefundene ZIP-Dateien:")
    shown = unique_zips[:10]
    options = [f"{f.name} ({f.stat().st_size / 1024:.1f} KB)" for f in shown]
    options.append("Anderen Pfad eingeben...")
    choice = interactive_select(options)
    if choice < 0:
        return None
    if choice < len(shown):
        return str(shown[choice])
    return _ask_filepath()


# Diese Teile stehen im Manifest als Liste von Namen — gezeigt wird die Anzahl.
_LISTED = {"sequences", "item_scans", "boss_scans", "icon_scans"}


def _print_bundle_contents(manifest: dict) -> None:
    """Was im Bündel steht, samt Beschreibungen und Referenzpunkten des Exporters."""
    contents = manifest.get("contents", {})
    print(f"\n  {col('Inhalt der Export-Datei:', 'bold')}")
    for key, label in (("points", "Punkte:     "), ("sequences", "Sequenzen:  "),
                       ("slots", "Slots:      "), ("items", "Items:      "),
                       ("item_scans", "Item-Scans: "), ("boss_scans", "Boss-Scans: "),
                       ("icon_scans", "Icon-Scans: "), ("templates", "Templates:  ")):
        if key not in contents:
            continue
        value = contents[key]
        shown = len(value) if key in _LISTED and isinstance(value, list) else value
        print(f"    {label} {shown}")
        if key == "sequences":
            _print_sequence_descriptions(value, manifest.get("sequence_descriptions", {}))
    if "config" in contents:
        print("    Config:      ja")

    ref = manifest.get("reference_points", {})
    src_ref1 = tuple(ref.get("point1", [0, 0]))
    src_ref2 = tuple(ref.get("point2", [0, 0]))
    print("\n  Referenzpunkte des Exporters:")
    print(f"    Punkt 1: ({src_ref1[0]}, {src_ref1[1]})")
    print(f"    Punkt 2: ({src_ref2[0]}, {src_ref2[1]})")


def _print_sequence_descriptions(sequences, descriptions: dict) -> None:
    if isinstance(sequences, list) and descriptions:
        for sname in sequences:
            if descriptions.get(sname):
                print(f"      - {col(sname, 'cyan')}: {descriptions[sname]}")


def _import_transform(state: AutoClickerState, manifest: dict):
    """Wie die Koordinaten umgerechnet werden — Transform, None (1:1) oder `_CANCELLED`.

    Bevorzugt automatisch aus der Fenstergrösse: kennt das Manifest das
    Spielfenster des Exporters und ist es hier offen, reicht eine Taste.
    Sonst von Hand mit zwei Punkten, oder 1:1.
    """
    from ..import_export import compute_transform, transform_from_windows
    from ..winapi import get_client_rect_by_title

    src_window = manifest.get("source_window")
    dst_window = get_client_rect_by_title(state.config.window_focus_title) if src_window else None
    mode = _ask_transform_mode(src_window, dst_window)
    if mode == "identity":
        return None
    if mode == "auto":
        return transform_from_windows(tuple(src_window), tuple(dst_window))

    print(f"\n  {col('Deine Referenzpunkte setzen:', 'bold')}")
    print("  Klicke die GLEICHEN Stellen im Spielfenster wie der Exporter:")
    print()
    refs = _ask_two_references("Referenzpunkte sind identisch!")
    if refs is None:
        return _CANCELLED
    ref = manifest.get("reference_points", {})
    src_ref1 = tuple(ref.get("point1", [0, 0]))
    src_ref2 = tuple(ref.get("point2", [0, 0]))
    return compute_transform(src_ref1, src_ref2, refs[0], refs[1])


def _ask_transform_mode(src_window, dst_window) -> str:
    """'auto', 'manual' oder 'identity' — mit beiden Fenstern ist 'auto' die Vorgabe."""
    print(f"\n  {col('Koordinaten-Anpassung:', 'bold')}")
    if src_window and dst_window:
        sl, st, sr, sb = src_window
        dl, dt, dr, db = dst_window
        print(f"    Spielfenster beim Export: {sr - sl}x{sb - st} px, jetzt: {dr - dl}x{db - dt} px")
        print("    [1] Automatisch aus Fenstergrösse (empfohlen)")
        print("    [2] Manuell (2 Punkte klicken)")
        print("    [3] 1:1 übernehmen (gleicher Bildschirm)")
        choice = safe_input("    Wahl (Enter = 1): ").strip()
        return "manual" if choice == "2" else "identity" if choice == "3" else "auto"
    if src_window and not dst_window:
        print(f"    {info('Spielfenster nicht gefunden — bitte 2 Punkte manuell setzen.')}")
    print("    [1] Remapping (andere Auflösung/Fensterposition)")
    print("    [2] 1:1 übernehmen (gleicher Bildschirm)")
    choice = safe_input("    Wahl (Enter = 1): ").strip()
    return "identity" if choice == "2" else "manual"


def _ask_import_parts(contents: dict) -> dict:
    """Was übernommen wird — gefragt nur nach dem, was das Bündel enthält.

    Ein Bündel hat zwei Teile: Sequenzordner (mit Punkten, Scans und Vorlagen)
    und die Config. Hier standen acht Fragen für das Layout aus der Zeit des
    globalen Bestands — für ein Bündel, das `import_bundle()` ohnehin ablehnt.
    """
    import_flags = {}
    print(f"  {col('Was importieren?', 'bold')}")
    for key, label in (('sequences', 'Sequenzordner inkl. Punkte, Scans und Vorlagen'),
                       ('config', 'Config')):
        if key in contents:
            choice = safe_input(f"    {label}? (j/n, Enter = ja): ").strip().lower()
            import_flags[f"import_{key}"] = choice != "n"
    return import_flags


def _report_import(state: AutoClickerState, result, transform) -> None:
    """Erfolg melden, Klick-Ziele ausserhalb des Fensters zeigen, zum Prüfen raten."""
    print(f"\n  {ok('Import erfolgreich!')}")
    print(f"  Importiert: {result}")

    # Plausibilität: liegen die Klick-Ziele im Spielfenster? (nur Warnung)
    from ..winapi import get_client_rect_by_title
    check_win = get_client_rect_by_title(state.config.window_focus_title)
    if check_win:
        from ..import_export import clicks_outside_window
        outside = clicks_outside_window(state, check_win)
        if outside:
            print(f"\n  {warn(f'{len(outside)} Klick-Position(en) liegen AUSSERHALB des Spielfensters:')}")
            for label, x, y in outside[:8]:
                print(f"    - {label}: ({x}, {y})")
            if len(outside) > 8:
                print(f"    ... und {len(outside) - 8} weitere")
            print(f"  {info('Das kann gewollt sein, deutet aber meist auf falsche Skalierung/Position hin.')}")

    if transform and transform != {"scale_x": 1.0, "scale_y": 1.0, "offset_x": 0, "offset_y": 0}:
        print(f"\n  {col('Hinweis:', 'yellow')} Koordinaten wurden automatisch angepasst.")
        print("           Teste die Sequenz einmal im Debug-Modus (config.json → debug_detail: true)")
        print("           um zu prüfen ob alle Positionen stimmen.")


def _ask_filepath() -> str | None:
    """Fragt nach einem Dateipfad."""
    print("  Pfad zur ZIP-Datei eingeben:")
    path = safe_input("  > ").strip().strip('"').strip("'")
    if is_cancel(path):
        print(f"  {info('Abgebrochen')}")
        return None
    if not Path(path).exists():
        print(f"  {err(f'Datei nicht gefunden: {path}')}")
        return None
    return path


# =============================================================================
# KALIBRIERUNG (Bildschirm-Layout hat sich geändert)
# =============================================================================

def run_calibration(state: AutoClickerState) -> None:
    """Rechnet alle gespeicherten Koordinaten auf ein geändertes Bildschirm-Layout um.

    Der Nutzer setzt einen bekannten Punkt neu; die Differenz gilt für alles andere.
    Optional ein zweiter Punkt, dann wird zusätzlich skaliert (andere Auflösung).

    Stufen: Umrechnung bestimmen (`_ask_calibration_transform`) → Vorschau →
    Umfang (`_ask_calibration_extent`) → Zustimmung → sichern, umrechnen,
    berichten. Geschrieben wird erst nach der Zustimmung.
    """
    from ..import_export import is_identity, calibrate_inventory, backup_before_calibration
    print(header("KALIBRIERUNG"))
    print(f"  {breadcrumb('Punkte', 'Kalibrierung')}")
    print()
    print("  Wenn Windows die Bildschirme neu angeordnet hat, sind alle gespeicherten")
    print("  Koordinaten um denselben Betrag verschoben. Du setzt EINEN Punkt neu,")
    print("  der Rest wird daraus umgerechnet.")
    print()

    with state.lock:
        points = list(state.points)
    if not points:
        print(f"  {err('Keine Punkte vorhanden — es gibt nichts zu kalibrieren.')}")
        return

    transform = _ask_calibration_transform(state, points)
    if transform is None:
        print(f"  {info(_CALIBRATION_CANCELLED)}")
        return
    if is_identity(transform):
        print(f"\n  {info('Der Versatz ist null — nichts zu tun.')}")
        return
    _print_calibration_preview(state, transform)

    with state.lock:
        slot_count = len(state.global_slots)
    if slot_count:
        _warn_slots_are_approximate(slot_count)
    extent = _ask_calibration_extent()
    if extent is None:
        print(f"  {info(_CALIBRATION_CANCELLED)}")
        return
    print()
    print(f"  {warn('Das schreibt die gespeicherten Dateien um.')}")
    if not confirm("  Jetzt übernehmen?", default=False):
        print(f"  {info(_CALIBRATION_CANCELLED)}")
        return

    backup = backup_before_calibration(state)
    if backup:
        print(f"  {ok('Sicherung angelegt:')} {backup}")
    else:
        print(f"  {warn('Sicherung fehlgeschlagen — es wird trotzdem geschrieben.')}")
    number = calibrate_inventory(state, transform, **extent)
    _print_calibration_result(number, extent, slot_count)


_CALIBRATION_CANCELLED = "[ABBRUCH] Kalibrierung abgebrochen — nichts geändert."


def _ask_calibration_transform(state: AutoClickerState, points: list):
    """Die Umrechnung aus einem (oder zwei) neu gesetzten Punkten — None bei Abbruch."""
    from ..import_export import transform_from_offset
    ref1 = _calibration_reference(state, points, "Referenzpunkt")
    if ref1 is None:
        return None
    p_old, p_new = ref1
    transform = transform_from_offset(p_old, p_new)
    offset = f"{transform['offset_x']:+.0f} X, {transform['offset_y']:+.0f} Y"
    print()
    print(f"  Verschiebung: {col(offset, 'yellow')}")

    if len(points) > 1:
        transform = _maybe_add_scale(state, points, ref1, transform)
    # Mit der Maus trifft man den Pixel nicht genau. Weiss man, dass eine Achse
    # stimmt, ist eine erzwungene 0 genauer als jede Messung.
    if transform["scale_x"] == 1.0 and transform["scale_y"] == 1.0:
        return _adjust_offset(transform)
    return transform


def _maybe_add_scale(state: AutoClickerState, points: list, ref1: tuple, transform: dict) -> dict:
    """Ein optionaler zweiter Punkt, möglichst weit vom ersten — dann wird auch skaliert."""
    from ..import_export import compute_transform
    print()
    print("  Hat sich auch die AUFLÖSUNG geändert, reicht Verschieben nicht —")
    print("  dann braucht es einen zweiten Punkt, möglichst weit vom ersten weg.")
    if not confirm("  Zweiten Referenzpunkt setzen (Skalierung)?", default=False):
        return transform
    p_old, p_new = ref1
    ref2 = _calibration_reference(state, points, "Zweiter Referenzpunkt", except_step=p_old)
    if ref2 is None:
        print(f"  {info('Ohne zweiten Punkt — es wird nur verschoben.')}")
        return transform
    q_old, q_new = ref2
    transform = compute_transform(p_old, q_old, p_new, q_new)
    factor = f"{transform['scale_x']:.4f} X, {transform['scale_y']:.4f} Y"
    print()
    print(f"  Skalierung: {col(factor, 'yellow')}")
    return transform


def _print_calibration_preview(state: AutoClickerState, transform: dict) -> None:
    """Ein Auszug der Umrechnung — und eine Warnung, wenn Ziele vom Bildschirm fielen."""
    from ..import_export import calibration_preview
    preview = calibration_preview(state, transform)
    print()
    print(col("  VORSCHAU (Auszug):", 'bold'))
    for label, old, new in preview[:12]:
        print(f"    {label:<34} ({old[0]:>5}, {old[1]:>5})  ->  ({new[0]:>5}, {new[1]:>5})")
    if len(preview) > 12:
        print(f"    {info(f'... und {len(preview) - 12} weitere')}")

    outside = _outside_all_monitors([new for _, _, new in preview])
    if outside:
        print()
        print(f"  {warn(f'{outside} Klick-Ziel(e) lägen danach ausserhalb aller Monitore.')}")
        print(f"  {info('Meist heisst das: der Referenzpunkt lag auf einem anderen Bildschirm')}")
        print(f"  {info('als diese Ziele — dann stimmt die Verschiebung fuer sie nicht.')}")


def _warn_slots_are_approximate(slot_count: int) -> None:
    print()
    print(f"  {warn('Fuer Slots ist das nur eine Naeherung.')}")
    print("  Ein Klick-Ziel vertraegt ein paar Pixel Abweichung — eine Scan-Region")
    print("  nicht: die schneidet dann das Item-Icon an oder zieht Nachbarpixel")
    print("  rein, und das Template-Matching wird unzuverlaessig.")
    print(f"  {info('Genauer: Item-Scan -> Slots -> ' + col('repair', 'yellow'))}")
    print(f"  {info('Das misst die ' + str(slot_count) + ' Slots neu, statt sie zu verschieben.')}")


def _ask_calibration_extent():
    """Was mitgezogen wird, als Schalter für `calibrate_inventory` — None bei Abbruch."""
    print()
    print(col("  Was soll mitgezogen werden?", 'bold'))
    extent = interactive_select([
        "Alles ausser Slots (Punkte, Scan-Regionen, Sequenzen) — Slots per 'repair'",
        "Alles inkl. Slots (Naeherung, s.o.)",
        "Nur die Punkte",
    ], default=0)
    if extent < 0:
        return None
    return {"with_scans": extent in (0, 1), "with_sequences": extent in (0, 1),
            "with_slots": extent == 1}


_CALIBRATION_CAPTION = {
    "points": "Punkte", "slots": "Slots", "items": "Item-Bestätigungsklicks",
    "item_scans": "Item-Scan-Fensteranker",
    "boss_scans": "Boss-Scans", "icon_scans": "Icon-Scans",
    "bosses": "globale Bosse", "sequences": "Sequenzdateien",
}


def _print_calibration_result(number: dict, extent: dict, slot_count: int) -> None:
    print()
    print(f"  {ok('Kalibriert:')}")
    for key_name, count in number.items():
        if count:
            print(f"    {count:>4}  {_CALIBRATION_CAPTION[key_name]}")
    if extent["with_sequences"]:
        print()
        print(f"  {info('Sequenzdateien wurden umgeschrieben — mit CTRL+ALT+L neu laden.')}")
    if not slot_count:
        return
    print()
    if extent["with_slots"]:
        print(f"  {warn('Die Slots wurden nur VERSCHOBEN, nicht neu vermessen —')}")
        print("  fuer Scan-Regionen ist das eine Naeherung.")
    else:
        print(f"  {info('Die Slots blieben unberuehrt — sie brauchen die genaue Messung.')}")
    print(f"  Pixelgenau macht es {col('Item-Scan -> Slots -> repair', 'yellow')}.")


def _adjust_offset(transform: dict) -> dict | None:
    """Lässt den gemessenen Versatz je Achse von Hand korrigieren.

    Der Grund: mit der Maus trifft man den Zielpixel nicht exakt. Steht da
    „+2 X" und man weiss, dass die X-Achse gar nicht verrutscht ist, dann ist
    eine eingetippte 0 genauer als die Messung. Umgekehrt genauso — oft stimmt
    eine Achse und nur die andere hat sich verschoben.

    Gibt den (ggf. geänderten) Transform zurück, oder None bei Abbruch.
    """
    vx, vy = round(transform["offset_x"]), round(transform["offset_y"])
    print()
    print(col("  Versatz nachjustieren:", 'bold'))
    print(f"  {info('Enter = uebernehmen. Stimmt eine Achse schon, hier 0 eintragen —')}")
    print(f"  {info('das ist genauer als die Maus-Messung.')}")

    new = []
    for axis, value in (("X", vx), ("Y", vy)):
        while True:
            user_input = safe_input(f"    {axis}-Versatz (Enter = {value:+d}): ").strip()
            if is_cancel(user_input):
                return None
            if not user_input:
                new.append(value)
                break
            try:
                new.append(int(round(float(user_input.replace(",", ".")))))
                break
            except ValueError:
                # Wiederholen statt abbrechen — wie in den anderen Editoren
                print(f"    {err('Bitte eine ganze Zahl, z.B. 0 oder -25.')}")

    if (new[0], new[1]) != (vx, vy):
        print(f"  {ok(f'Versatz von Hand gesetzt: {new[0]:+d} X, {new[1]:+d} Y')}")
    return {"scale_x": 1.0, "scale_y": 1.0,
            "offset_x": new[0], "offset_y": new[1]}


def _calibration_reference(state: AutoClickerState, points: list, title: str,
                    except_step: tuple | None = None):
    """Lässt einen Punkt wählen und seine RICHTIGE Position aufnehmen.

    Gibt ((alt_x, alt_y), (new_x, new_y)) zurück oder None bei Abbruch.
    """
    from ..winapi import set_cursor_pos

    selection = [p for p in points if except_step is None or (p.x, p.y) != except_step]
    if not selection:
        return None

    print()
    print(col(f"  {title}:", 'bold'))
    caption = [f"#{p.id} {p.name or '(ohne Namen)'}  ({p.x}, {p.y})" for p in selection]
    idx = interactive_select(caption, default=0)
    if idx < 0:
        return None
    point = selection[idx]

    # Maus dorthin, wo der Punkt AKTUELL zeigt — dann sieht man die Abweichung
    set_cursor_pos(point.x, point.y)
    print(f"  Die Maus steht jetzt auf der GESPEICHERTEN Position ({point.x}, {point.y}).")
    print("  Bewege sie dorthin, wo dieser Punkt WIRKLICH hingehört, dann Enter.")
    print(f"  {info('(x = abbrechen)')}")
    if is_cancel(safe_input("    > ").strip()):
        return None
    new = get_cursor_pos()
    print(f"    -> ({new[0]}, {new[1]})")
    return (point.x, point.y), new


def _outside_all_monitors(targets: list[tuple[int, int]]) -> int:
    """Wie viele Ziele nach der Umrechnung auf keinem Bildschirm mehr lägen.

    Hier stand `from ..diagnostics import _virtueller_desktop` — eine Funktion,
    die es seit dem Eingrenzen der Windows-Abhängigkeiten nicht mehr gibt
    (Bildschirm-Geometrie kommt aus `winapi`). Der Import stand im Rumpf, also
    fiel er erst beim Aufruf um: Kalibrierung und `repair` warfen ImportError.
    """
    rect = get_virtual_desktop()
    if rect is None:
        return 0
    left, top, right, bottom = rect
    return sum(1 for x, y in targets
               if not (left <= x < right and top <= y < bottom))
