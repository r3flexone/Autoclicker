#!/usr/bin/env python3
"""
Windows Autoclicker mit Sequenz-Unterstützung und Item-Erkennung.
Neues modulares Hauptskript - ersetzt autoclicker.py
"""

import ctypes
import ctypes.wintypes as wintypes
import sys
import time

# stdout/stderr auf UTF-8 zwingen, damit Unicode (→, ü, █) auch in
# umgeleiteter Ausgabe oder bei Codepage <65001 nicht crasht.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

# Modulare Imports
from autoclicker.config import AppConfig, CONFIG, SEQUENCES_DIR, CONFIG_FILE
from autoclicker.models import AutoClickerState
from autoclicker.winapi import (
    user32, kernel32,
    WM_HOTKEY, PM_REMOVE,
    HOTKEY_RECORD, HOTKEY_UNDO, HOTKEY_CLEAR, HOTKEY_RESET,
    HOTKEY_EDITOR, HOTKEY_ITEM_SCAN, HOTKEY_LOAD, HOTKEY_SHOW,
    HOTKEY_TOGGLE, HOTKEY_PAUSE, HOTKEY_SKIP, HOTKEY_SWITCH,
    HOTKEY_SCHEDULE, HOTKEY_ANALYZE, HOTKEY_QUIT, HOTKEY_FINISH,
    HOTKEY_IMPORT_EXPORT, HOTKEY_RECORD_SEQ, HOTKEY_RECORD_PAUSE,
    HOTKEY_SEQUENCE_STUDIO, HOTKEY_SCAN_STUDIO, HOTKEY_HELP, HOTKEY_RECORD_COLOR,
    HOTKEY_RECORD_SCREENSHOT, HOTKEY_REC_PHASE, HOTKEY_REC_REGION, HOTKEY_REC_WATCH,
    register_hotkeys, unregister_hotkeys, flush_hotkey_messages
)
from autoclicker.persistence import (
    ensure_sequences_dir, ensure_item_scans_dir, init_directories, sweep_beim_start,
    list_available_sequences,
    load_points, load_global_slots, load_global_items, load_all_item_scans,
    load_all_boss_scans, load_all_icon_scans, load_global_bosses,
    resolve_klick_referenzen
)
from autoclicker.diagnose import check_beim_start
from autoclicker.runtime import print_status
from autoclicker.utils import col, info, warn, hint, init_logging
from autoclicker.handlers import (
    handle_record, handle_undo, handle_clear, handle_reset,
    handle_editor, handle_item_scan_editor, handle_load, handle_show,
    handle_toggle, handle_pause, handle_skip, handle_switch,
    handle_schedule, handle_analyze, handle_quit, handle_finish,
    handle_import_export, handle_record_sequence, handle_record_pause,
    handle_record_color, handle_record_screenshot,
    handle_rec_phase, handle_rec_region, handle_rec_watch,
    handle_sequence_studio, handle_scan_studio
)


def print_banner() -> None:
    """Vier Zeilen fuer den Wiedereinstieg — die volle Hilfe liegt auf CTRL+ALT+O.

    Frueher stand hier bei JEDEM Start die komplette Hilfe samt drei Tutorials: rund 70
    Zeilen, die alles Wichtige (Config-Pfad, geladene Daten, LLM/OCR-Status) nach oben
    aus dem Fenster geschoben haben. Beim ersten Start ist die Anleitung Gold wert, beim
    fuenfzigsten ist sie Rauschen.
    """
    line = col("=" * 65, 'cyan')
    print(line)
    print(f"  {col('WINDOWS AUTOCLICKER', 'bold')}")
    print(f"  {col('CTRL+ALT+A', 'yellow')} Punkt aufnehmen   "
          f"{col('CTRL+ALT+E', 'yellow')} Sequenz-Editor   "
          f"{col('CTRL+ALT+S', 'yellow')} Start/Stop")
    print(f"  {col('CTRL+ALT+O', 'yellow')} {hint('alle Hotkeys + Anleitung')}")
    print(line)


def print_help(mit_anleitung: bool = True) -> None:
    """Zeigt die Hilfe mit farbigen Kategorien an."""
    line = col("=" * 65, 'cyan')
    print(line)
    print(f"  {col('WINDOWS AUTOCLICKER MIT SEQUENZ-UNTERSTÜTZUNG', 'bold')}")
    print(line)
    print()

    # Aufnahme (grün)
    print(col("Aufnahme:", 'green'))
    print(f"  {col('CTRL+ALT+A', 'yellow')}  Mausposition als Punkt speichern")
    print(f"  {col('CTRL+ALT+U', 'yellow')}  Letzten Punkt entfernen {hint('(während einer Aufnahme: letztes Ereignis)')}")
    print(f"  {col('CTRL+ALT+C', 'yellow')}  Alle Punkte löschen")
    print(f"  {col('CTRL+ALT+J', 'yellow')}  Sequenz aufnehmen {hint('(Klick/Taste/Mausrad → Sequenz erstellen)')}")
    print(f"  {col('CTRL+ALT+M', 'yellow')}  Aufnahme: auf Farbe warten {hint('(Maus über die Stelle, sobald sie da ist)')}")
    print(f"  {col('CTRL+ALT+D', 'yellow')}  Aufnahme: Screenshot {hint('(Vollbild)')}")
    print(f"  {col('CTRL+ALT+SHIFT+D', 'yellow')}  Aufnahme: Screenshot-Bereich {hint('(2× drücken = zwei Ecken)')}")
    print(f"  {col('CTRL+ALT+SHIFT+M', 'yellow')}  Aufnahme: beobachten ohne Klick {hint('(Maus auf die Stelle)')}")
    print(f"  {col('CTRL+ALT+SHIFT+P', 'yellow')}  Aufnahme: Phasengrenze {hint('(1× = LOOP, 2× = END)')}")
    print(f"  {col('CTRL+ALT+H', 'yellow')}  Aufnahme pausieren/fortsetzen {hint('(während einer Aufnahme)')}")
    print()

    # Editoren (blau)
    print(col("Editoren:", 'blue'))
    print(f"  {col('CTRL+ALT+E', 'yellow')}  Sequenz-Editor {hint('(Punkte + Zeiten verknüpfen)')}")
    print(f"  {col('CTRL+ALT+B', 'yellow')}  Sequenz-Studio {hint('(Phasen + Schritte visuell – braucht pywebview)')}")
    print(f"  {col('CTRL+ALT+N', 'yellow')}  Item-Scan Editor {hint('(Items erkennen + vergleichen)')}")
    print(f"  {col('CTRL+ALT+V', 'yellow')}  Scan-Studio {hint('(Slots/Items/Scans + Boss/Icon visuell)')}")
    print(f"  {col('CTRL+ALT+L', 'yellow')}  Gespeicherte Sequenz laden")
    print(f"  {col('CTRL+ALT+P', 'yellow')}  Punkte testen/anzeigen/umbenennen "
          f"{hint('(dort auch: check = Setup prüfen, fix = kalibrieren, walk, manuell, log/detail)')}")
    print(f"  {col('CTRL+ALT+I', 'yellow')}  Import/Export {hint('(Setup teilen/importieren)')}")
    print(f"  {col('CTRL+ALT+T', 'yellow')}  Farb-Analysator {hint('(für Bilderkennung)')}")
    print()

    # Ausführung (magenta)
    print(col("Ausführung:", 'magenta'))
    print(f"  {col('CTRL+ALT+S', 'yellow')}  Start/Stop der aktiven Sequenz")
    print(f"  {col('CTRL+ALT+F', 'yellow')}  Sanft beenden {hint('(Zyklus abschliessen, dann END + Stop)')}")
    print(f"  {col('CTRL+ALT+G', 'yellow')}  Pause/Resume")
    print(f"  {col('CTRL+ALT+K', 'yellow')}  Skip {hint('(aktuelle Wartezeit überspringen)')}")
    print(f"  {col('CTRL+ALT+W', 'yellow')}  Quick-Switch {hint('(schnell Sequenz wechseln)')}")
    print(f"  {col('CTRL+ALT+Z', 'yellow')}  Zeitplan {hint('(Start zu bestimmter Zeit)')}")
    print()

    # System (rot)
    print(col("System:", 'red'))
    print(f"  {col('CTRL+ALT+O', 'yellow')}  Diese Hilfe erneut anzeigen")
    print(f"  {col('CTRL+ALT+X', 'yellow')}  Factory Reset {hint('(Punkte + Sequenzen)')}")
    print(f"  {col('CTRL+ALT+Q', 'yellow')}  Programm beenden")
    print()

    if mit_anleitung:
        print_anleitung()
    else:
        print(hint(f"  Daten: '{SEQUENCES_DIR}/' | Einstellungen: '{CONFIG_FILE}'"))
        print(line)
        print()


def print_anleitung() -> None:
    """Schritt-fuer-Schritt-Anleitung — beim ersten Start und ueber CTRL+ALT+O."""
    line = col("=" * 65, 'cyan')
    print(col("Anleitung:", 'bold'))
    print()
    print(f"  {col('Einfache Klick-Sequenz:', 'cyan')}")
    print(f"    {col('1.', 'cyan')} Maus auf die gewünschte Stelle bewegen")
    print(f"    {col('2.', 'cyan')} {col('CTRL+ALT+A', 'yellow')} drücken → Punkt wird gespeichert")
    print(f"    {col('3.', 'cyan')} Schritte 1-2 für alle Klick-Positionen wiederholen")
    print(f"    {col('4.', 'cyan')} {col('CTRL+ALT+E', 'yellow')} → Sequenz-Editor öffnen")
    _hint_text = hint('Punkte mit Zeiten verknüpfen, z.B. "1 30" = Punkt 1 nach 30s klicken')
    print(f"       {_hint_text}")
    print(f"    {col('5.', 'cyan')} {col('CTRL+ALT+S', 'yellow')} → Sequenz starten")
    print()
    print(f"  {col('Mit Item-Erkennung:', 'cyan')} {hint('(für automatisches Erkennen + Klicken von Items)')}")
    print(f"    {col('1.', 'cyan')} Punkte aufnehmen wie oben")
    print(f"    {col('2.', 'cyan')} {col('CTRL+ALT+N', 'yellow')} → Item-Scan Editor")
    print(f"       {col('a)', 'gray')} {col('Slots', 'green')} erstellen   {hint('= Bereiche wo Items erscheinen')}")
    print(f"       {col('b)', 'gray')} {col('Items', 'green')} lernen      {hint('= welche Items erkannt werden sollen')}")
    print(f"       {col('c)', 'gray')} {col('Scan', 'green')} erstellen    {hint('= Slots + Items verknüpfen')}")
    print(f"    {col('3.', 'cyan')} {col('CTRL+ALT+E', 'yellow')} → Im Editor: {col('scan <Name>', 'yellow')} als Schritt einfügen")
    print(f"    {col('4.', 'cyan')} {col('CTRL+ALT+S', 'yellow')} → Sequenz starten")
    print()
    print(f"  {col('Farb-Trigger:', 'cyan')} {hint('(warte bis Farbe erscheint/verschwindet)')}")
    print(f"    Im Editor: {col('1 pixel', 'yellow')} {hint('= warte auf Farbe, dann Punkt 1 klicken')}")
    print(f"               {col('1 gone', 'yellow')}  {hint('= warte bis Farbe WEG ist, dann klicken')}")
    print()
    print(hint(f"  Daten: '{SEQUENCES_DIR}/' | Einstellungen: '{CONFIG_FILE}'"))
    print(line)
    print()


def _erster_start(state) -> bool:
    """Nichts aufgenommen, nichts gespeichert — dann ist die Anleitung das Wichtigste."""
    return not (state.points or state.global_slots or state.global_items
                or state.item_scans or list_available_sequences())


def main() -> int:
    """Hauptfunktion."""
    print_banner()

    # State initialisieren
    state = AutoClickerState()
    state.config = AppConfig.from_dict(CONFIG.to_dict())
    # Logger-Meldungen sichtbar und im Stil des Programms. DEBUG nur, wenn eine der
    # Ausgabe-Stufen an ist - sonst blieben Diagnosen wie "Template passt nicht zur
    # Slot-Groesse" unsichtbar, obwohl genau danach gesucht wird.
    init_logging(state.config.debug_log or state.config.debug_detail)
    main_thread_id = kernel32.GetCurrentThreadId()

    # Ordner erstellen
    ensure_sequences_dir()
    ensure_item_scans_dir()
    init_directories()

    # Alle JSON-Dateien aufs aktuelle Format heben - VOR dem Laden, damit der Rest des
    # Starts schon die aufgeraeumten Dateien liest. Meldet nur, wenn es etwas zu tun gab.
    if state.config.migrate_on_start:
        sweep_beim_start()

    # Gespeicherte Daten laden
    load_points(state)
    load_global_slots(state)
    load_global_items(state)
    load_all_item_scans(state)
    load_all_boss_scans(state)
    load_global_bosses(state)
    load_all_icon_scans(state)

    # Klick-Ziele aufloesen, NACHDEM alles geladen ist. `load_all_item_scans` loest zwar
    # schon auf, sieht die Boss- und Icon-Scans an dieser Stelle aber noch gar nicht -
    # deren Klick-Punkte staenden bis zum ersten Sequenzlauf auf (0, 0).
    for meldung in resolve_klick_referenzen(state):
        print(warn(meldung))

    # Beim allerersten Start die volle Anleitung zeigen - da ist sie das Wichtigste
    # im Fenster. Danach reicht der Banner oben, alles Weitere liegt auf CTRL+ALT+O.
    if _erster_start(state):
        print()
        print_help()

    # Setup pruefen - meldet nur, wenn etwas nicht stimmt (Sequenzdateien bleiben
    # aussen vor, das waere beim Start eine Bremse; die volle Pruefung liegt auf
    # CTRL+ALT+P -> check).
    check_beim_start(state)

    # Hotkeys registrieren
    if not register_hotkeys():
        print(warn("Nicht alle Hotkeys konnten registriert werden."))
        print()

    # LLM-Verbindung prüfen wenn aktiviert
    if state.config.llm_enabled:
        try:
            from autoclicker.llm_vision import test_connection
            provider = state.config.llm_provider
            ok, msg = test_connection(provider)
            if ok:
                print(col(f"[LLM] {provider} verbunden: {msg}", 'green'))
            else:
                provider_name = "LM Studio" if provider == "lmstudio" else "Ollama"
                print(warn(f"[LLM] {provider_name} nicht erreichbar! {msg}"))
                print(warn(f"       Bitte {provider_name} starten für Boss-Erkennung."))
        except Exception:
            pass
        print()

    # OCR-Status prüfen wenn aktiviert
    if state.config.ocr_enabled:
        try:
            from autoclicker.ocr import is_available, get_status
            if is_available():
                print(col(f"[OCR] {get_status()}", 'green'))
            else:
                print(warn(f"[OCR] {get_status()}"))
        except Exception:
            pass
        print()

    print(col("Bereit!", 'green') + f" Starte mit {col('CTRL+ALT+A', 'yellow')} um Punkte aufzunehmen.")
    print(f"        oder mit {col('CTRL+ALT+S', 'yellow')} eine Sequenz starten.")
    print_status(state)
    print()

    # Message-Struktur für Windows-Nachrichten
    msg = wintypes.MSG()

    # Hotkey-Handler Zuordnung
    hotkey_handlers = {
        HOTKEY_RECORD: handle_record,
        HOTKEY_UNDO: handle_undo,
        HOTKEY_CLEAR: handle_clear,
        HOTKEY_RESET: handle_reset,
        HOTKEY_EDITOR: handle_editor,
        HOTKEY_ITEM_SCAN: handle_item_scan_editor,
        HOTKEY_LOAD: handle_load,
        HOTKEY_SHOW: handle_show,
        HOTKEY_TOGGLE: handle_toggle,
        HOTKEY_PAUSE: handle_pause,
        HOTKEY_SKIP: handle_skip,
        HOTKEY_SWITCH: handle_switch,
        HOTKEY_SCHEDULE: handle_schedule,
        HOTKEY_ANALYZE: handle_analyze,
        HOTKEY_FINISH: handle_finish,
        HOTKEY_IMPORT_EXPORT: handle_import_export,
        HOTKEY_RECORD_SEQ: handle_record_sequence,
        HOTKEY_RECORD_PAUSE: handle_record_pause,
        HOTKEY_RECORD_COLOR: handle_record_color,
        HOTKEY_RECORD_SCREENSHOT: handle_record_screenshot,
        HOTKEY_REC_PHASE: handle_rec_phase,
        HOTKEY_REC_REGION: handle_rec_region,
        HOTKEY_REC_WATCH: handle_rec_watch,
        HOTKEY_SEQUENCE_STUDIO: handle_sequence_studio,
        HOTKEY_SCAN_STUDIO: handle_scan_studio,
        HOTKEY_HELP: lambda _state: print_help(),
    }

    try:
        # Haupt-Event-Loop
        while not state.quit_event.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY:
                    hk_id = msg.wParam

                    if hk_id == HOTKEY_QUIT:
                        handle_quit(state, main_thread_id)
                        break
                    elif hk_id in hotkey_handlers:
                        hotkey_handlers[hk_id](state)
                        # Während ein blockierender Handler lief, aufgestaute
                        # WM_HOTKEY-Messages verwerfen (sonst feuern sie als Burst).
                        flush_hotkey_messages()
            else:
                time.sleep(0.01)

    except KeyboardInterrupt:
        print(f"\n{col('[ABBRUCH]', 'red')} Programm wird beendet...")
        state.stop_event.set()
        state.quit_event.set()

    finally:
        unregister_hotkeys()
        print(f"\n{info('Hotkeys deregistriert.')}")
        time.sleep(0.2)
        print(info("Programm beendet."))

    return 0


if __name__ == "__main__":
    sys.exit(main())
