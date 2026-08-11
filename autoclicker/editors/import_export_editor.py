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
from ..winapi import get_cursor_pos


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
        print(f"    Sequenzen:   {len(state.sequences)}")
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
    print(header("EXPORT"))

    # Auswahl was exportiert wird
    include = {
        "points": True, "sequences": True, "slots": True,
        "items": True, "item_scans": True, "boss_scans": True,
        "icon_scans": True,
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
            "icon_scans": "Icon-Scans",
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
            "icon_scans": len(state.icon_scans),
        }

    active = {k: v for k, v in include.items() if v and k != "config"}
    if not any(active.values()) and not include["config"]:
        print(f"  {err('Nichts zum Exportieren ausgewählt!')}")
        return

    print(f"  {col('Wird exportiert:', 'bold')}")
    for key, label in [("points", "Punkte"), ("sequences", "Sequenzen"),
                       ("slots", "Slots"), ("items", "Items"),
                       ("item_scans", "Item-Scans"), ("boss_scans", "Boss-Scans"),
                       ("icon_scans", "Icon-Scans")]:
        if include[key]:
            print(f"    {col('✓', 'green')} {label}: {counts.get(key, 0)}")
    if include["config"]:
        print(f"    {col('✓', 'green')} Config-Einstellungen")
    print()

    # Referenz: bevorzugt automatisch aus der Spielfenster-Grösse, sonst manuell
    from ..winapi import get_client_rect_by_title
    win_title = state.config.window_focus_title
    source_window = get_client_rect_by_title(win_title) if win_title else None

    if source_window:
        sl, st, sr, sb = source_window
        ref1, ref2 = (sl, st), (sr, sb)
        print(col("  === SPIELFENSTER ERKANNT ===", "bold"))
        print(f"  Fenster '{win_title}': {sr - sl}x{sb - st} px @ ({sl}, {st})")
        print(f"  {info('Beim Import wird die Skalierung automatisch aus der Fenstergrösse abgeleitet.')}")
        print()
    else:
        # Fallback: manuelle Referenzpunkte (Fenster nicht gefunden / kein Titel gesetzt)
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
        include_icon_scans=include["icon_scans"],
        include_config=include["config"],
        source_window=source_window,
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
        print("\n  Gefundene ZIP-Dateien:")
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
        print("\n  Keine ZIP-Dateien in ./exports/ oder ./ gefunden.")
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
        descriptions = manifest.get("sequence_descriptions", {})
        if isinstance(seqs, list) and descriptions:
            for sname in seqs:
                if descriptions.get(sname):
                    print(f"      - {col(sname, 'cyan')}: {descriptions[sname]}")
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
    if "icon_scans" in contents:
        iscans = contents["icon_scans"]
        print(f"    Icon-Scans:  {len(iscans) if isinstance(iscans, list) else iscans}")
    if "templates" in contents:
        print(f"    Templates:   {contents['templates']}")
    if "config" in contents:
        print("    Config:      ja")

    print("\n  Referenzpunkte des Exporters:")
    print(f"    Punkt 1: ({src_ref1[0]}, {src_ref1[1]})")
    print(f"    Punkt 2: ({src_ref2[0]}, {src_ref2[1]})")

    # Koordinaten-Anpassung: bevorzugt automatisch aus der Spielfenster-Grösse
    from ..import_export import compute_transform, transform_from_windows
    from ..winapi import get_client_rect_by_title

    src_window = manifest.get("source_window")
    dst_window = get_client_rect_by_title(state.config.window_focus_title) if src_window else None

    print(f"\n  {col('Koordinaten-Anpassung:', 'bold')}")
    if src_window and dst_window:
        sl, st, sr, sb = src_window
        dl, dt, dr, db = dst_window
        print(f"    Spielfenster beim Export: {sr - sl}x{sb - st} px, jetzt: {dr - dl}x{db - dt} px")
        print("    [1] Automatisch aus Fenstergrösse (empfohlen)")
        print("    [2] Manuell (2 Punkte klicken)")
        print("    [3] 1:1 übernehmen (gleicher Bildschirm)")
        c = safe_input("    Wahl (Enter = 1): ").strip()
        mode = "manual" if c == "2" else "identity" if c == "3" else "auto"
    else:
        if src_window and not dst_window:
            print(f"    {info(f'Spielfenster nicht gefunden — bitte 2 Punkte manuell setzen.')}")
        print("    [1] Remapping (andere Auflösung/Fensterposition)")
        print("    [2] 1:1 übernehmen (gleicher Bildschirm)")
        c = safe_input("    Wahl (Enter = 1): ").strip()
        mode = "identity" if c == "2" else "manual"

    transform = None
    if mode == "auto":
        transform = transform_from_windows(tuple(src_window), tuple(dst_window))
    elif mode == "manual":
        print(f"\n  {col('Deine Referenzpunkte setzen:', 'bold')}")
        print("  Klicke die GLEICHEN Stellen im Spielfenster wie der Exporter:")
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

        transform = compute_transform(src_ref1, src_ref2, dst_ref1, dst_ref2)

    if transform:
        scale_x = transform["scale_x"]
        scale_y = transform["scale_y"]
        print(f"\n  Skalierung: {scale_x:.2%} x {scale_y:.2%}")
        off_x = transform["offset_x"]
        off_y = transform["offset_y"]
        print(f"  Verschiebung: ({off_x:+.0f}, {off_y:+.0f}) Pixel")
        print()

    # Was importieren?
    import_flags = {}
    print(f"  {col('Was importieren?', 'bold')}")
    parts = [("points", "Punkte"), ("sequences", "Sequenzen"), ("slots", "Slots"),
             ("items", "Items"), ("item_scans", "Item-Scans"),
             ("boss_scans", "Boss-Scans"), ("icon_scans", "Icon-Scans"),
             ("config", "Config")]
    for key, label in parts:
        if key in contents:
            choice = safe_input(f"    {label}? (j/n, Enter = ja): ").strip().lower()
            import_flags[f"import_{key}"] = choice != "n"

    # Merge oder ersetzen?
    print("\n  Bestehende Daten:")
    print("    [1] Behalten + ergänzen (Merge)")
    print("    [2] Ersetzen (bestehende Daten werden überschrieben)")
    merge_choice = safe_input("    Wahl (Enter = 1): ").strip()
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

        # Plausibilität: liegen die Klick-Ziele im Spielfenster? (nur Warnung)
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
    else:
        print(f"\n  {err(f'Import fehlgeschlagen: {result}')}")


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

def run_kalibrierung(state: AutoClickerState) -> None:
    """Rechnet alle gespeicherten Koordinaten auf ein geändertes Bildschirm-Layout um.

    Der Nutzer setzt einen bekannten Punkt neu; die Differenz gilt für alles andere.
    Optional ein zweiter Punkt, dann wird zusätzlich skaliert (andere Auflösung).
    """
    from ..import_export import (
        compute_transform, transform_aus_verschiebung, ist_identitaet,
        kalibrier_vorschau, kalibriere_bestand,
    )
    print(header("KALIBRIERUNG"))
    print(f"  {breadcrumb('Punkte', 'Kalibrierung')}")
    print()
    print("  Wenn Windows die Bildschirme neu angeordnet hat, sind alle gespeicherten")
    print("  Koordinaten um denselben Betrag verschoben. Du setzt EINEN Punkt neu,")
    print("  der Rest wird daraus umgerechnet.")
    print()

    with state.lock:
        punkte = list(state.points)
    if not punkte:
        print(f"  {err('Keine Punkte vorhanden — es gibt nichts zu kalibrieren.')}")
        return

    # --- Referenzpunkt 1: Verschiebung ------------------------------------------
    ref1 = _kalib_referenz(state, punkte, "Referenzpunkt")
    if ref1 is None:
        print(f"  {info('[ABBRUCH] Kalibrierung abgebrochen — nichts geändert.')}")
        return
    p_alt, p_neu = ref1
    transform = transform_aus_verschiebung(p_alt, p_neu)

    versatz = f"{transform['offset_x']:+.0f} X, {transform['offset_y']:+.0f} Y"
    print()
    print(f"  Verschiebung: {col(versatz, 'yellow')}")

    # --- Referenzpunkt 2 (optional): Skalierung ---------------------------------
    if len(punkte) > 1:
        print()
        print("  Hat sich auch die AUFLÖSUNG geändert, reicht Verschieben nicht —")
        print("  dann braucht es einen zweiten Punkt, möglichst weit vom ersten weg.")
        if confirm("  Zweiten Referenzpunkt setzen (Skalierung)?", default=False):
            ref2 = _kalib_referenz(state, punkte, "Zweiter Referenzpunkt",
                                   ausser=p_alt)
            if ref2 is None:
                print(f"  {info('Ohne zweiten Punkt — es wird nur verschoben.')}")
            else:
                q_alt, q_neu = ref2
                transform = compute_transform(p_alt, q_alt, p_neu, q_neu)
                faktor = f"{transform['scale_x']:.4f} X, {transform['scale_y']:.4f} Y"
                print()
                print(f"  Skalierung: {col(faktor, 'yellow')}")

    # --- Versatz von Hand nachziehen --------------------------------------------
    # Mit der Maus trifft man den Pixel nicht genau. Weiss man, dass eine Achse
    # stimmt, ist eine erzwungene 0 genauer als jede Messung.
    if transform["scale_x"] == 1.0 and transform["scale_y"] == 1.0:
        transform = _versatz_anpassen(transform)
        if transform is None:
            print(f"  {info('[ABBRUCH] Kalibrierung abgebrochen — nichts geändert.')}")
            return

    if ist_identitaet(transform):
        print(f"\n  {info('Der Versatz ist null — nichts zu tun.')}")
        return

    # --- Vorschau ----------------------------------------------------------------
    vorschau = kalibrier_vorschau(state, transform)
    print()
    print(col("  VORSCHAU (Auszug):", 'bold'))
    for label, alt, neu in vorschau[:12]:
        print(f"    {label:<34} ({alt[0]:>5}, {alt[1]:>5})  ->  ({neu[0]:>5}, {neu[1]:>5})")
    if len(vorschau) > 12:
        print(f"    {info(f'... und {len(vorschau) - 12} weitere')}")

    draussen = _ausserhalb_der_monitore([neu for _, _, neu in vorschau])
    if draussen:
        print()
        print(f"  {warn(f'{draussen} Klick-Ziel(e) lägen danach ausserhalb aller Monitore.')}")
        print(f"  {info('Meist heisst das: der Referenzpunkt lag auf einem anderen Bildschirm')}")
        print(f"  {info('als diese Ziele — dann stimmt die Verschiebung fuer sie nicht.')}")

    # --- Umfang -------------------------------------------------------------------
    with state.lock:
        anzahl_slots = len(state.global_slots)

    if anzahl_slots:
        print()
        print(f"  {warn('Fuer Slots ist das nur eine Naeherung.')}")
        print("  Ein Klick-Ziel vertraegt ein paar Pixel Abweichung — eine Scan-Region")
        print("  nicht: die schneidet dann das Item-Icon an oder zieht Nachbarpixel")
        print("  rein, und das Template-Matching wird unzuverlaessig.")
        print(f"  {info('Genauer: Item-Scan -> Slots -> ' + col('repair', 'yellow'))}")
        print(f"  {info('Das misst die ' + str(anzahl_slots) + ' Slots neu, statt sie zu verschieben.')}")

    print()
    print(col("  Was soll mitgezogen werden?", 'bold'))
    umfang = interactive_select([
        "Alles ausser Slots (Punkte, Scan-Regionen, Sequenzen) — Slots per 'repair'",
        "Alles inkl. Slots (Naeherung, s.o.)",
        "Nur die Punkte",
    ], default=0)
    if umfang < 0:
        print(f"  {info('[ABBRUCH] Kalibrierung abgebrochen — nichts geändert.')}")
        return
    mit_slots = umfang == 1
    mit_scans = umfang in (0, 1)
    mit_sequenzen = umfang in (0, 1)

    print()
    print(f"  {warn('Das schreibt die gespeicherten Dateien um.')}")
    if not confirm("  Jetzt übernehmen?", default=False):
        print(f"  {info('[ABBRUCH] Kalibrierung abgebrochen — nichts geändert.')}")
        return

    from ..import_export import sichere_vor_kalibrierung
    sicherung = sichere_vor_kalibrierung(state)
    if sicherung:
        print(f"  {ok('Sicherung angelegt:')} {sicherung}")
    else:
        print(f"  {warn('Sicherung fehlgeschlagen — es wird trotzdem geschrieben.')}")

    zahl = kalibriere_bestand(state, transform, mit_scans=mit_scans,
                              mit_sequenzen=mit_sequenzen, mit_slots=mit_slots)

    print()
    print(f"  {ok('Kalibriert:')}")
    beschriftung = {"punkte": "Punkte", "slots": "Slots", "items": "Item-Bestätigungsklicks",
                    "boss_scans": "Boss-Scans", "icon_scans": "Icon-Scans",
                    "bosse": "globale Bosse", "sequenzen": "Sequenzdateien"}
    for schluessel, anzahl in zahl.items():
        if anzahl:
            print(f"    {anzahl:>4}  {beschriftung[schluessel]}")
    if mit_sequenzen:
        print()
        print(f"  {info('Sequenzdateien wurden umgeschrieben — mit CTRL+ALT+L neu laden.')}")

    if anzahl_slots:
        print()
        if mit_slots:
            print(f"  {warn('Die Slots wurden nur VERSCHOBEN, nicht neu vermessen —')}")
            print("  fuer Scan-Regionen ist das eine Naeherung.")
        else:
            print(f"  {info('Die Slots blieben unberuehrt — sie brauchen die genaue Messung.')}")
        print(f"  Pixelgenau macht es {col('Item-Scan -> Slots -> repair', 'yellow')}.")


def _versatz_anpassen(transform: dict) -> dict | None:
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

    neu = []
    for achse, wert in (("X", vx), ("Y", vy)):
        while True:
            eingabe = safe_input(f"    {achse}-Versatz (Enter = {wert:+d}): ").strip()
            if is_cancel(eingabe):
                return None
            if not eingabe:
                neu.append(wert)
                break
            try:
                neu.append(int(round(float(eingabe.replace(",", ".")))))
                break
            except ValueError:
                # Wiederholen statt abbrechen — wie in den anderen Editoren
                print(f"    {err('Bitte eine ganze Zahl, z.B. 0 oder -25.')}")

    if (neu[0], neu[1]) != (vx, vy):
        print(f"  {ok(f'Versatz von Hand gesetzt: {neu[0]:+d} X, {neu[1]:+d} Y')}")
    return {"scale_x": 1.0, "scale_y": 1.0,
            "offset_x": neu[0], "offset_y": neu[1]}


def _kalib_referenz(state: AutoClickerState, punkte: list, titel: str,
                    ausser: tuple | None = None):
    """Lässt einen Punkt wählen und seine RICHTIGE Position aufnehmen.

    Gibt ((alt_x, alt_y), (neu_x, neu_y)) zurück oder None bei Abbruch.
    """
    from ..winapi import set_cursor_pos

    auswahl = [p for p in punkte if ausser is None or (p.x, p.y) != ausser]
    if not auswahl:
        return None

    print()
    print(col(f"  {titel}:", 'bold'))
    beschriftung = [f"#{p.id} {p.name or '(ohne Namen)'}  ({p.x}, {p.y})" for p in auswahl]
    idx = interactive_select(beschriftung, default=0)
    if idx < 0:
        return None
    punkt = auswahl[idx]

    # Maus dorthin, wo der Punkt AKTUELL zeigt — dann sieht man die Abweichung
    set_cursor_pos(punkt.x, punkt.y)
    print(f"  Die Maus steht jetzt auf der GESPEICHERTEN Position ({punkt.x}, {punkt.y}).")
    print("  Bewege sie dorthin, wo dieser Punkt WIRKLICH hingehört, dann Enter.")
    print(f"  {info('(x = abbrechen)')}")
    if is_cancel(safe_input("    > ").strip()):
        return None
    neu = get_cursor_pos()
    print(f"    -> ({neu[0]}, {neu[1]})")
    return (punkt.x, punkt.y), neu


def _ausserhalb_der_monitore(ziele: list[tuple[int, int]]) -> int:
    """Wie viele Ziele nach der Umrechnung auf keinem Bildschirm mehr lägen."""
    from ..diagnose import _virtueller_desktop
    rect = _virtueller_desktop()
    if rect is None:
        return 0
    links, oben, rechts, unten = rect
    return sum(1 for x, y in ziele
               if not (links <= x < rechts and oben <= y < unten))
