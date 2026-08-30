#!/usr/bin/env python3
"""Plattformübergreifender Autoclicker mit Sequenzen und Item-Erkennung."""

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
from autoclicker.config import CONFIG, SEQUENCES_DIR, CONFIG_FILE
from autoclicker.models import AutoClickerState
from autoclicker.winapi import (
    HOTKEY_RECORD, HOTKEY_UNDO, HOTKEY_CLEAR, HOTKEY_RESET,
    HOTKEY_EDITOR, HOTKEY_ITEM_SCAN, HOTKEY_LOAD, HOTKEY_SHOW,
    HOTKEY_TOGGLE, HOTKEY_PAUSE, HOTKEY_SKIP, HOTKEY_SWITCH,
    HOTKEY_SCHEDULE, HOTKEY_ANALYZE, HOTKEY_QUIT, HOTKEY_FINISH,
    HOTKEY_IMPORT_EXPORT, HOTKEY_RECORD_SEQ, HOTKEY_RECORD_PAUSE,
    HOTKEY_SEQUENCE_STUDIO, HOTKEY_SCAN_STUDIO, HOTKEY_HELP, HOTKEY_RECORD_COLOR,
    HOTKEY_RECORD_SCREENSHOT, HOTKEY_REC_PHASE, HOTKEY_REC_REGION, HOTKEY_REC_WATCH,
    register_hotkeys, unregister_hotkeys, flush_hotkey_messages,
    poll_hotkey, get_current_thread_id, platform_name, environment_warnings,
    PlatformError,
)
from autoclicker.persistence import (
    ensure_sequences_dir, init_directories,
    list_available_sequences, sweep_beim_start,
)
from autoclicker.diagnose import check_beim_start
from autoclicker.runtime import print_status
from autoclicker.utils import col, err, info, warn, hint, init_logging
from autoclicker.handlers import (
    handle_record, handle_undo, handle_clear, handle_reset,
    handle_editor, handle_item_scan_editor, handle_load, handle_show,
    handle_toggle, handle_pause, handle_skip, handle_switch,
    handle_schedule, handle_analyze, handle_quit, handle_finish,
    handle_import_export, handle_record_sequence, handle_record_pause,
    handle_record_color, handle_record_screenshot,
    handle_rec_phase, handle_rec_region, handle_rec_watch,
    handle_sequence_studio, handle_scan_studio, BEFEHLE
)
from autoclicker.befehl import hole as hole_befehl, verwerfe as verwirf_befehle


def print_banner() -> None:
    """Vier Zeilen fuer den Wiedereinstieg — die volle Hilfe liegt auf CTRL+ALT+O.

    Frueher stand hier bei JEDEM Start die komplette Hilfe samt drei Tutorials: rund 70
    Zeilen, die alles Wichtige (Config-Pfad, geladene Daten, LLM/OCR-Status) nach oben
    aus dem Fenster geschoben haben. Beim ersten Start ist die Anleitung Gold wert, beim
    fuenfzigsten ist sie Rauschen.
    """
    line = col("=" * 65, 'cyan')
    print(line)
    print(f"  {col(platform_name().upper() + ' AUTOCLICKER', 'bold')}")
    print(f"  {col('CTRL+ALT+A', 'yellow')} Punkt aufnehmen   "
          f"{col('CTRL+ALT+E', 'yellow')} Sequenz-Editor   "
          f"{col('CTRL+ALT+S', 'yellow')} Start/Stop")
    print(f"  {col('CTRL+ALT+O', 'yellow')} {hint('alle Hotkeys + Anleitung')}")
    print(line)


def print_help(mit_anleitung: bool = True) -> None:
    """Zeigt die Hilfe mit farbigen Kategorien an."""
    line = col("=" * 65, 'cyan')
    print(line)
    print(f"  {col(platform_name().upper() + ' AUTOCLICKER MIT SEQUENZ-UNTERSTÜTZUNG', 'bold')}")
    print(line)
    print()

    # Aufnahme (grün)
    print(col("Aufnahme:", 'green'))
    print(f"  {col('CTRL+ALT+A', 'yellow')}  Mausposition als Punkt speichern")
    print(f"  {col('CTRL+ALT+U', 'yellow')}  Letzten Punkt entfernen {hint('(während einer Aufnahme: letztes Ereignis)')}")
    print(f"  {col('CTRL+ALT+C', 'yellow')}  Alle Punkte löschen")
    print(f"  {col('CTRL+ALT+J', 'yellow')}  Sequenz aufnehmen {hint('(Klick/Taste/Mausrad → Sequenz erstellen)')}")
    print(f"  {col('CTRL+ALT+SHIFT+M', 'yellow')}  Aufnahme: auf Farbe warten {hint('(Maus über die Stelle, sobald sie da ist)')}")
    print(f"  {col('CTRL+ALT+SHIFT+D', 'yellow')}  Aufnahme: Screenshot {hint('(Vollbild)')}")
    print(f"  {col('CTRL+ALT+SHIFT+R', 'yellow')}  Aufnahme: Screenshot-Bereich {hint('(2× drücken = zwei Ecken)')}")
    print(f"  {col('CTRL+ALT+SHIFT+B', 'yellow')}  Aufnahme: beobachten ohne Klick {hint('(Maus auf die Stelle)')}")
    print(f"  {col('CTRL+ALT+SHIFT+P', 'yellow')}  Aufnahme: neue Phase {hint('(beliebig oft — jede Grenze eine Loop-Phase)')}")
    print(f"  {col('CTRL+ALT+H', 'yellow')}  Aufnahme pausieren/fortsetzen {hint('(während einer Aufnahme)')}")
    print()

    # Editoren (blau)
    print(col("Editoren:", 'blue'))
    print(f"  {col('CTRL+ALT+E', 'yellow')}  Sequenz-Editor {hint('(Punkte + Zeiten verknüpfen)')}")
    print(f"  {col('CTRL+ALT+B', 'yellow')}  Sequenz-Studio {hint('(Phasen + Schritte visuell – braucht pywebview)')}")
    print(f"  {' ' * 12}{hint('dort auch: Reiter Werkzeuge = prüfen, kalibrieren, nachklicken')}")
    print(f"  {col('CTRL+ALT+N', 'yellow')}  Item-Scan Editor {hint('(Items erkennen + vergleichen)')}")
    print(f"  {col('CTRL+ALT+V', 'yellow')}  Studio: Reiter Scans {hint('(Item-, Boss- und Icon-Scans auf einem Screenshot)')}")
    print(f"  {col('CTRL+ALT+L', 'yellow')}  Gespeicherte Sequenz laden")
    print(f"  {col('CTRL+ALT+P', 'yellow')}  Punkte testen/anzeigen/umbenennen "
          f"{hint('(dort auch: check = Setup prüfen, fix = kalibrieren, walk, klick = nachklicken, manuell, log/detail)')}")
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
    return not list_available_sequences()


# Wie oft im Leerlauf nach einem Befehl aus dem Studio gesehen wird. Die Schleife
# dreht alle 10 ms; jedes Mal eine Datei zu öffnen wäre hundertmal pro Sekunde für
# etwas, das man von Hand auslöst.
_BEFEHL_TAKT = 0.25
_befehl_zuletzt = 0.0


def _pruefe_befehle(state) -> None:
    """Holt einen Befehl aus dem Briefkasten und führt ihn aus.

    Läuft im **Main-Thread**, im Leerlauf derselben Schleife, die auch die
    Hotkeys abholt. Damit ist ein Befehl aus dem Studio exakt dasselbe wie ein
    Hotkey-Druck: dieselbe Reihenfolge, dieselben Sperren, kein zweiter
    nebenläufiger Pfad im Programm. Ein Watcher-Thread hätte genau das gebracht,
    und zwar nur, weil er eine Datei liest, die niemand eilig braucht.
    """
    global _befehl_zuletzt
    jetzt = time.monotonic()
    if jetzt - _befehl_zuletzt < _BEFEHL_TAKT:
        return
    _befehl_zuletzt = jetzt

    auftrag = hole_befehl()
    if auftrag is None:
        return
    name = auftrag["befehl"]
    fn = BEFEHLE.get(name)
    if fn is None:
        print(f"\n{info(f'Unbekannter Befehl aus dem Studio: {name}')}")
        return
    # Kein flush_hotkey_messages() danach: das verwirft aufgestaute Hotkeys und ist
    # für Handler gedacht, die minutenlang auf Konsolen-Eingaben warten. Ein Befehl
    # blockiert nicht — er lädt höchstens eine Datei und startet einen Thread.
    # Würde hier geflusht, verschluckte ein zufällig gleichzeitiger Tastendruck.
    try:
        fn(state, auftrag["argumente"])
    except PlatformError as fehler:
        print(err(f"Systemaktion fehlgeschlagen: {fehler}"))


def _studio_beim_start_oeffnen(state) -> bool:
    """Öffnet auf Wunsch das Studio, nachdem der Hauptprozess empfangsbereit ist."""
    if not state.config.studio_open_on_start:
        return False
    return handle_sequence_studio(state, beenden_mit_fenster=True)


def _tui_ist_startoberflaeche(state) -> bool:
    """Die Option wählt eine Startoberfläche, nicht einen zweiten Fachkern.

    Im Studio-Modus bleibt derselbe Hauptprozess für Hotkeys und Laufzeit aktiv;
    Banner, Anleitung und Bereitschaftsmenü sind aber keine zweite Oberfläche im
    Hintergrund. Konsolenwerkzeuge bleiben als ausdrücklicher Rückfallweg nutzbar.
    """
    return not state.config.studio_open_on_start


def _tui_bereit_anzeigen(state) -> None:
    """Der Abschluss des sichtbaren TUI-Starts, auch als Studio-Rückfall."""
    print(col("Bereit!", 'green') +
          f" Starte mit {col('CTRL+ALT+A', 'yellow')} um Punkte aufzunehmen.")
    print(f"        oder mit {col('CTRL+ALT+S', 'yellow')} eine Sequenz starten.")
    print_status(state)
    print()


def _plattform_bereit() -> bool:
    """Meldet fehlende Systemvoraussetzungen, bevor Daten verändert werden."""
    meldungen = environment_warnings()
    for meldung in meldungen:
        print(warn(meldung))
    if meldungen:
        print(err("Plattform nicht einsatzbereit; Start abgebrochen."))
        print()
        return False
    return True


def main() -> int:
    """Hauptfunktion."""
    # State initialisieren
    state = AutoClickerState()
    # Dasselbe Objekt, keine Kopie: `from .config import CONFIG` steht in
    # imaging und in mehreren Item-Editoren, und mit einer Kopie lasen die
    # dauerhaft den Stand vom Programmstart. Wer die Werte aendert, schreibt
    # deshalb HINEIN (config.uebernehmen) statt state.config auszutauschen.
    state.config = CONFIG
    # Logger-Meldungen sichtbar und im Stil des Programms. DEBUG nur, wenn eine der
    # Ausgabe-Stufen an ist - sonst blieben Diagnosen wie "Template passt nicht zur
    # Slot-Groesse" unsichtbar, obwohl genau danach gesucht wird.
    init_logging(state.config.debug_log or state.config.debug_detail)
    tui_start = _tui_ist_startoberflaeche(state)
    if tui_start:
        print_banner()
    if not _plattform_bereit():
        return 2
    main_thread_id = get_current_thread_id()

    # Ordner erstellen
    ensure_sequences_dir()
    init_directories()

    # Start-Durchgang: alle JSON-Dateien aufs aktuelle Format heben, BEVOR etwas
    # geladen wird - dann liest der Rest des Starts schon die aufgeraeumten Dateien.
    # Meldet nur, wenn es etwas zu melden gab (persistence/sweep.py).
    if state.config.migrate_on_start:
        sweep_beim_start()

    # Sequenz, Punkte und Scans werden gemeinsam geladen, sobald der Nutzer eine
    # Sequenz auswählt. Ohne Besitzer gibt es bewusst keinen globalen Scan-Bestand.

    # Beim allerersten Start die volle Anleitung zeigen - da ist sie das Wichtigste
    # im Fenster. Danach reicht der Banner oben, alles Weitere liegt auf CTRL+ALT+O.
    erster_start = _erster_start(state)
    if tui_start and erster_start:
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

    if tui_start:
        _tui_bereit_anzeigen(state)

    # Briefkasten leeren, bevor die Schleife anfängt zu lesen. Wer im Studio auf
    # „Starten" drückt, während gar kein Hauptprozess läuft, bekommt keine
    # Wirkung — und darf sie auch nicht bekommen, sobald einer startet. Die
    # Altersregel in befehl.py fängt das meiste ab, aber nicht die letzten
    # Sekunden davor.
    verwirf_befehle()

    # Erst NACH dem Leeren des Briefkastens: der automatisch geoeffnete Editor
    # kann sehr schnell „Starten" senden. Stuende dieser Aufruf weiter oben,
    # wuerde `verwirf_befehle()` genau diesen ersten Auftrag wegwerfen.
    studio_offen = _studio_beim_start_oeffnen(state)
    if not tui_start and not studio_offen:
        # Ein fehlgeschlagenes GUI darf keinen unsichtbaren, scheinbar toten
        # Hauptprozess hinterlassen. In diesem Sonderfall wird die TUI sichtbar
        # zur Startoberflaeche und nennt auch beim ersten Start die Anleitung.
        print(warn("Studio konnte nicht geöffnet werden — starte in der Konsole."))
        print_banner()
        if erster_start:
            print()
            print_help()
        _tui_bereit_anzeigen(state)

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
            hk_id = poll_hotkey()
            if hk_id is not None:
                if hk_id == HOTKEY_QUIT:
                    handle_quit(state, main_thread_id)
                    break
                if hk_id in hotkey_handlers:
                    try:
                        hotkey_handlers[hk_id](state)
                    except PlatformError as fehler:
                        print(err(f"Systemaktion fehlgeschlagen: {fehler}"))
                    # Während ein blockierender Handler lief, aufgestaute
                    # Hotkeys verwerfen (sonst feuern sie als Burst).
                    flush_hotkey_messages()
            else:
                _pruefe_befehle(state)
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
