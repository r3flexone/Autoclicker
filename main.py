#!/usr/bin/env python3
"""
Windows Autoclicker mit Sequenz-Unterstützung und Item-Erkennung.
Neues modulares Hauptskript - ersetzt autoclicker.py
"""

import ctypes
import ctypes.wintypes as wintypes
import sys
import time

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
    register_hotkeys, unregister_hotkeys
)
from autoclicker.persistence import (
    ensure_sequences_dir, ensure_item_scans_dir, init_directories,
    load_points, load_global_slots, load_global_items, load_all_item_scans,
    load_all_boss_scans
)
from autoclicker.execution import print_status
from autoclicker.utils import col, info, warn, hint
from autoclicker.handlers import (
    handle_record, handle_undo, handle_clear, handle_reset,
    handle_editor, handle_item_scan_editor, handle_load, handle_show,
    handle_toggle, handle_pause, handle_skip, handle_switch,
    handle_schedule, handle_analyze, handle_quit, handle_finish
)


def print_help() -> None:
    """Zeigt die Hilfe mit farbigen Kategorien an."""
    line = col("=" * 65, 'cyan')
    print(line)
    print(f"  {col('WINDOWS AUTOCLICKER MIT SEQUENZ-UNTERSTÜTZUNG', 'bold')}")
    print(line)
    print()

    # Aufnahme (grün)
    print(col("Aufnahme:", 'green'))
    print(f"  {col('CTRL+ALT+A', 'yellow')}  Mausposition als Punkt speichern")
    print(f"  {col('CTRL+ALT+U', 'yellow')}  Letzten Punkt entfernen")
    print(f"  {col('CTRL+ALT+C', 'yellow')}  Alle Punkte löschen")
    print()

    # Editoren (blau)
    print(col("Editoren:", 'blue'))
    print(f"  {col('CTRL+ALT+E', 'yellow')}  Sequenz-Editor {hint('(Punkte + Zeiten verknüpfen)')}")
    print(f"  {col('CTRL+ALT+N', 'yellow')}  Item-Scan Editor {hint('(Items erkennen + vergleichen)')}")
    print(f"  {col('CTRL+ALT+L', 'yellow')}  Gespeicherte Sequenz laden")
    print(f"  {col('CTRL+ALT+P', 'yellow')}  Punkte testen/anzeigen/umbenennen")
    print(f"  {col('CTRL+ALT+T', 'yellow')}  Farb-Analysator {hint('(für Bilderkennung)')}")
    print()

    # Ausführung (magenta)
    print(col("Ausführung:", 'magenta'))
    print(f"  {col('CTRL+ALT+S', 'yellow')}  Start/Stop der aktiven Sequenz")
    print(f"  {col('CTRL+ALT+F', 'yellow')}  Sanft beenden {hint('(Zyklus abschließen, dann END + Stop)')}")
    print(f"  {col('CTRL+ALT+G', 'yellow')}  Pause/Resume")
    print(f"  {col('CTRL+ALT+K', 'yellow')}  Skip {hint('(aktuelle Wartezeit überspringen)')}")
    print(f"  {col('CTRL+ALT+W', 'yellow')}  Quick-Switch {hint('(schnell Sequenz wechseln)')}")
    print(f"  {col('CTRL+ALT+Z', 'yellow')}  Zeitplan {hint('(Start zu bestimmter Zeit)')}")
    print()

    # System (rot)
    print(col("System:", 'red'))
    print(f"  {col('CTRL+ALT+X', 'yellow')}  Factory Reset {hint('(Punkte + Sequenzen)')}")
    print(f"  {col('CTRL+ALT+Q', 'yellow')}  Programm beenden")
    print()

    # Schritt-für-Schritt-Anleitung
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


def main() -> int:
    """Hauptfunktion."""
    print_help()

    # State initialisieren
    state = AutoClickerState()
    state.config = AppConfig.from_dict(CONFIG.to_dict())
    main_thread_id = kernel32.GetCurrentThreadId()

    # Ordner erstellen
    ensure_sequences_dir()
    ensure_item_scans_dir()
    init_directories()

    # Gespeicherte Daten laden
    load_points(state)
    load_global_slots(state)
    load_global_items(state)
    load_all_item_scans(state)
    load_all_boss_scans(state)

    # Hotkeys registrieren
    if not register_hotkeys():
        print(warn("Nicht alle Hotkeys konnten registriert werden."))
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
