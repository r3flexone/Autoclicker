"""
Hilfsfunktionen für den Autoclicker.
JSON-Handling, Input-Funktionen, Zeit-Parser, etc.
"""

import ctypes
import json
import logging
import msvcrt
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AutoClickerState

# Logger
logger = logging.getLogger("autoclicker")


# =============================================================================
# ANSI-FARBAUSGABE
# =============================================================================

# Optimistisch starten - wird nach _detect_ansi_support()/_is_pycharm() korrekt gesetzt
_COLORS_ENABLED = True

# ANSI-Farbcodes
_C = {
    "reset":   "\033[0m",
    "bold":    "\033[1m",
    "dim":     "\033[2m",
    "green":   "\033[32m",
    "red":     "\033[31m",
    "yellow":  "\033[33m",
    "blue":    "\033[34m",
    "cyan":    "\033[36m",
    "magenta": "\033[35m",
    "gray":    "\033[90m",
    "white":   "\033[97m",
    "bg_green": "\033[42m",
    "bg_red":   "\033[41m",
}


def col(text: str, color: str) -> str:
    """Färbt Text mit ANSI-Escape-Codes.

    Farben: green, red, yellow, blue, cyan, magenta, gray, bold, dim
    """
    if not _COLORS_ENABLED:
        return text
    code = _C.get(color, "")
    if not code:
        return text
    return f"{code}{text}{_C['reset']}"


def ok(msg: str) -> str:
    """Formatiert eine Erfolgsmeldung: [OK] grün."""
    return f"{col('[OK]', 'green')} {msg}"


def err(msg: str) -> str:
    """Formatiert eine Fehlermeldung: [FEHLER] rot."""
    return f"{col('[FEHLER]', 'red')} {msg}"


def warn(msg: str) -> str:
    """Formatiert eine Warnung: [WARNUNG] gelb."""
    return f"{col('[WARNUNG]', 'yellow')} {msg}"


def info(msg: str) -> str:
    """Formatiert eine Info-Meldung: [INFO] cyan."""
    return f"{col('[INFO]', 'cyan')} {msg}"


def hint(msg: str) -> str:
    """Formatiert einen Hinweis in grau."""
    return col(msg, 'gray')


def dbg(msg: str) -> str:
    """Formatiert eine Debug-Meldung: [DEBUG] in grau."""
    return f"{col('[DEBUG]', 'gray')} {msg}"


def save_tag(msg: str) -> str:
    """Formatiert eine Speicher-Meldung: [SAVE] grün."""
    return f"{col('[SAVE]', 'green')} {msg}"


def load_tag(msg: str) -> str:
    """Formatiert eine Lade-Meldung: [LOAD] cyan."""
    return f"{col('[LOAD]', 'cyan')} {msg}"


def delete_tag(msg: str) -> str:
    """Formatiert eine Lösch-Meldung: [DELETE] gelb."""
    return f"{col('[DELETE]', 'yellow')} {msg}"


def header(title: str, width: int = 60) -> str:
    """Erzeugt eine farbige Überschrift."""
    line = "=" * width
    return f"\n{col(line, 'cyan')}\n  {col(title, 'bold')}\n{col(line, 'cyan')}"


def cmd_hint(cmd: str, desc: str) -> str:
    """Formatiert einen Befehl mit Beschreibung für Hilfe-Texte."""
    return f"  {col(cmd, 'yellow'):30s} {desc}"


def breadcrumb(*parts: str) -> str:
    """Formatiert eine Breadcrumb-Navigation (z.B. Hauptmenü > Item-Scan > Slots)."""
    colored = []
    for i, part in enumerate(parts):
        if i == len(parts) - 1:
            colored.append(col(part, 'bold'))
        else:
            colored.append(col(part, 'gray'))
    sep = col(" > ", 'gray')
    return sep.join(colored)


def suggest_command(cmd: str, known_commands: list[str]) -> str:
    """Gibt einen Vorschlag für einen ähnlichen Befehl zurück.

    Nutzt difflib.get_close_matches für Fuzzy-Matching.

    Returns:
        Formatierter Hinweis-String oder leerer String.
    """
    from difflib import get_close_matches
    # Nur das erste Wort matchen (z.B. "delet 3" → "del")
    first_word = cmd.split()[0] if cmd else ""
    if not first_word:
        return ""
    matches = get_close_matches(first_word, known_commands, n=1, cutoff=0.5)
    if matches:
        colored_match = col(matches[0], "yellow")
        return f" {hint(f'Meintest du {colored_match}?')}"
    return ""


def coord_context(x: int, y: int) -> str:
    """Beschreibt Koordinaten mit räumlichem Kontext.

    Nutzt die Bildschirmauflösung für relative Positionsangaben.
    Beispiel: (1920, 1080) = rechts unten (100%, 100%)
    """
    try:
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)
    except (AttributeError, OSError):
        return f"({x}, {y})"

    if screen_w <= 0 or screen_h <= 0:
        return f"({x}, {y})"

    # Horizontale Position
    if x < screen_w * 0.33:
        h_pos = "links"
    elif x < screen_w * 0.66:
        h_pos = "mitte"
    else:
        h_pos = "rechts"

    # Vertikale Position
    if y < screen_h * 0.33:
        v_pos = "oben"
    elif y < screen_h * 0.66:
        v_pos = "mitte"
    else:
        v_pos = "unten"

    # Kombination
    if v_pos == "mitte" and h_pos == "mitte":
        pos_str = "Mitte"
    elif v_pos == "mitte":
        pos_str = h_pos
    elif h_pos == "mitte":
        pos_str = v_pos
    else:
        pos_str = f"{v_pos} {h_pos}"

    pct_x = x * 100 // screen_w
    pct_y = y * 100 // screen_h

    return f"({x}, {y}) {hint(f'= {pos_str} ({pct_x}%, {pct_y}%)')}"


def sanitize_filename(name: str) -> str:
    """Bereinigt einen Namen für sichere Dateinamen.

    Entfernt/ersetzt unsichere Zeichen wie ../, \\, :, *, ?, ", <, >, |
    """
    # Entferne Path-Traversal-Versuche
    name = name.replace("..", "").replace("/", "_").replace("\\", "_")
    # Entferne Windows-unsichere Zeichen
    name = re.sub(r'[<>:"|?*]', '', name)
    # Leerzeichen zu Unterstrichen
    name = name.replace(' ', '_')
    # Nur alphanumerische Zeichen, Unterstriche und Bindestriche erlauben
    name = re.sub(r'[^\w\-]', '', name)
    # Leere Namen verhindern
    if not name:
        name = "unnamed"
    return name.lower()


def compact_json(data: dict, indent: int = 2) -> str:
    """Formatiert JSON mit kompakten Arrays (Koordinaten/Farben auf einer Zeile).

    Wandelt:
        [
            55,
            15,
            50
        ]
    zu:
        [55, 15, 50]
    """
    json_str = json.dumps(data, indent=indent, ensure_ascii=False)
    # Regex: Finde Arrays die nur Zahlen enthalten und über mehrere Zeilen gehen
    # 4er-Arrays (scan_region: x1, y1, x2, y2)
    pattern4 = r'\[\s*\n\s*(\d+),\s*\n\s*(\d+),\s*\n\s*(\d+),\s*\n\s*(\d+)\s*\n\s*\]'
    json_str = re.sub(pattern4, r'[\1, \2, \3, \4]', json_str)
    # 3er-Arrays (RGB-Farben)
    pattern3 = r'\[\s*\n\s*(\d+),\s*\n\s*(\d+),\s*\n\s*(\d+)\s*\n\s*\]'
    json_str = re.sub(pattern3, r'[\1, \2, \3]', json_str)
    # 2er-Arrays (x, y Koordinaten)
    pattern2 = r'\[\s*\n\s*(\d+),\s*\n\s*(\d+)\s*\n\s*\]'
    json_str = re.sub(pattern2, r'[\1, \2]', json_str)
    return json_str


def is_cancel(value: str) -> bool:
    """Prüft ob die Eingabe ein Abbruch-Befehl ist.

    Akzeptiert: ESC-Taste, cancel, abbruch, q, quit (case-insensitive).
    """
    if value == "\x1b":
        return True
    return value.strip().lower() in ("cancel", "abbruch", "q", "quit")


def cancel_hint() -> str:
    """Gibt den passenden Abbruch-Hinweis zurück je nach Umgebung.

    Echte Konsole: 'ESC' (funktioniert via msvcrt).
    PyCharm/IDE: 'q' (ESC springt ins Code-Fenster).
    """
    return "ESC" if _REAL_CONSOLE else "q"


def flush_input_buffer() -> None:
    """Leert den Tastatur-Input-Buffer (entfernt gepufferte Tastendrücke).

    Echte Windows-Konsole: msvcrt.kbhit/getch.
    PyCharm/IDE (Pipe-stdin): PeekNamedPipe + sys.stdin.read.
    """
    if _REAL_CONSOLE:
        try:
            while msvcrt.kbhit():
                msvcrt.getwch()  # getwch statt getch — gleicher Buffer-Typ wie safe_input
        except Exception:
            pass
    else:
        # Pipe-stdin (PyCharm): leftover Enter vom interactive_select leeren
        try:
            handle = ctypes.windll.kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
            bytes_avail = ctypes.c_ulong(0)
            ok_pipe = ctypes.windll.kernel32.PeekNamedPipe(
                handle, None, 0, None, ctypes.byref(bytes_avail), None)
            if ok_pipe and bytes_avail.value > 0:
                sys.stdin.read(bytes_avail.value)
        except Exception:
            pass


def safe_input(prompt: str = "") -> str:
    """Sicherer Input mit Abbruch-Support.

    In echter Windows-Konsole: Zeichenweise Eingabe via msvcrt mit ESC-Erkennung.
    In PyCharm/IDE: Normaler input() (ESC springt ins Code-Fenster, daher
    'q', 'cancel' oder 'abbruch' zum Abbrechen tippen).
    """
    flush_input_buffer()

    if _REAL_CONSOLE:
        if prompt:
            print(prompt, end="", flush=True)

        chars = []
        while True:
            try:
                ch = msvcrt.getwch()
            except (EOFError, KeyboardInterrupt):
                raise

            if ch == '\x1b':  # ESC
                print()
                return "\x1b"
            elif ch in ('\r', '\n'):  # Enter (auch \n falls CTRL noch gehalten)
                print()
                return ''.join(chars)
            elif ch in ('\x08', '\x7f'):  # Backspace
                if chars:
                    chars.pop()
                    print('\b \b', end='', flush=True)
            elif ch == '\x03':  # Ctrl+C
                print()
                raise KeyboardInterrupt
            elif ch == '\x04' or ch == '\x1a':  # Ctrl+D / Ctrl+Z (EOF)
                print()
                raise EOFError
            elif ch in ('\x00', '\xe0'):  # Spezial-Tasten Prefix (Pfeile etc.)
                msvcrt.getwch()  # Zweites Byte lesen und verwerfen
            elif ch >= ' ':  # Druckbare Zeichen
                chars.append(ch)
                print(ch, end='', flush=True)
    else:
        # Non-Windows/IDE: Prompt manuell ausgeben, dann stdin lesen
        # (vermeidet doppelte Ausgabe durch Windows Console API + Python stdout)
        try:
            if prompt:
                sys.stdout.write(prompt)
                sys.stdout.flush()
            line = sys.stdin.readline()
            if not line:  # EOF
                return ""
            return line.rstrip('\n\r')
        except (EOFError, KeyboardInterrupt):
            return ""


def confirm(message: str, default: bool = False) -> bool:
    """Fragt Benutzer nach Bestätigung (j/n)."""
    suffix = " (J/n): " if default else " (j/N): "
    response = safe_input(message + suffix).strip().lower()
    if not response:
        return default
    return response in ("j", "ja", "y", "yes")


def clear_line() -> None:
    """Löscht die aktuelle Konsolenzeile."""
    print("\r" + " " * 80 + "\r", end="", flush=True)


# =============================================================================
# KONSOLEN-ERKENNUNG, ANSI-SUPPORT UND PFEILTASTEN-NAVIGATION
# =============================================================================

def _is_real_console() -> bool:
    """Prüft ob stdin ein echtes Windows-Console-Handle hat.

    In PyCharm/IDE-Konsolen gibt es kein echtes Console-Handle,
    daher funktionieren msvcrt.getch()/kbhit() dort nicht.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        STD_INPUT_HANDLE = -10
        handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        mode = ctypes.c_ulong()
        result = kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        return result != 0
    except (AttributeError, OSError):
        return False


def _detect_ansi_support() -> bool:
    """Prüft ob ANSI-Escape-Codes unterstützt werden.

    Unterscheidet zwischen:
    - Voller ANSI-Support (Farben + Cursor-Bewegung): Nur echte Windows-Konsole
    - Teilweiser ANSI-Support (nur Farben): PyCharm/IntelliJ
    """
    # Echte Windows-Konsole: Voller ANSI-Support (Farben + Cursor)
    if _REAL_CONSOLE:
        try:
            kernel32 = ctypes.windll.kernel32
            STD_OUTPUT_HANDLE = -11
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
            return True
        except (AttributeError, OSError):
            return False

    return False


def _is_pycharm() -> bool:
    """Prüft ob PyCharm/IntelliJ die Host-Umgebung ist.

    PyCharm unterstützt ANSI-Farben (\\033[7m) aber KEINE Cursor-Bewegung (\\033[A).
    """
    return bool(os.environ.get("PYCHARM_HOSTED"))


# Virtual Key Codes für GetAsyncKeyState
_VK_MAP = {
    0x26: 'up',        # VK_UP
    0x28: 'down',      # VK_DOWN
    0x25: 'left',      # VK_LEFT
    0x27: 'right',     # VK_RIGHT
    0x0D: 'enter',     # VK_RETURN
    0x1B: 'escape',    # VK_ESCAPE
    0x08: 'backspace', # VK_BACK
    # Numpad-Pfeiltasten
    0x68: 'up',        # VK_NUMPAD8
    0x62: 'down',      # VK_NUMPAD2
    0x64: 'left',      # VK_NUMPAD4
    0x66: 'right',     # VK_NUMPAD6
}
# Zifferntasten 0-9
for _i in range(10):
    _VK_MAP[0x30 + _i] = str(_i)


# Beim Import einmalig prüfen
_REAL_CONSOLE = _is_real_console()
_ANSI_ENABLED = _detect_ansi_support()  # Voller ANSI (Farben + Cursor)
_PYCHARM = _is_pycharm()               # Nur ANSI-Farben, kein Cursor

# Farben erst jetzt final konfigurieren (nach _ANSI_ENABLED/_PYCHARM Check)
_COLORS_ENABLED = _ANSI_ENABLED or _PYCHARM

if not _REAL_CONSOLE:
    if _PYCHARM:
        print(info("PyCharm erkannt - Pfeiltasten-Navigation via GetAsyncKeyState aktiv"))
    else:
        print(info("IDE-Konsole erkannt - Fallback auf Nummern-Eingabe"))


def _read_key_msvcrt() -> str:
    """Liest Tastendruck via msvcrt.getch() (echte Windows-Konsole)."""
    byte = msvcrt.getch()

    # Pfeiltasten und andere erweiterte Tasten (0xE0 oder 0x00 Prefix)
    if byte in (b'\xe0', b'\x00'):
        next_byte = msvcrt.getch()
        if next_byte == b'H':
            return 'up'
        elif next_byte == b'P':
            return 'down'
        elif next_byte == b'K':
            return 'left'
        elif next_byte == b'M':
            return 'right'
        return 'unknown'

    if byte == b'\r':
        return 'enter'
    if byte == b'\x1b':
        return 'escape'
    if byte == b'\x08':
        return 'backspace'

    try:
        return byte.decode('utf-8')
    except UnicodeDecodeError:
        return 'unknown'


def _read_key_polling() -> str:
    """Liest Tastendruck via GetAsyncKeyState (funktioniert in PyCharm/IDE).

    Nutzt die gleiche Windows API wie die Hotkeys - funktioniert überall,
    auch ohne echtes Console-Handle.
    """
    user32 = ctypes.windll.user32

    # Vorherige Zustände initialisieren (Flanken-Erkennung)
    prev_states = {}
    for vk in _VK_MAP:
        prev_states[vk] = bool(user32.GetAsyncKeyState(vk) & 0x8000)

    while True:
        for vk, name in _VK_MAP.items():
            is_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
            was_down = prev_states[vk]
            prev_states[vk] = is_down

            # Steigende Flanke = Taste gerade gedrückt
            if is_down and not was_down:
                return name

        time.sleep(0.02)  # 50Hz Polling - reaktionsschnell, CPU-schonend


def read_key() -> str:
    """Liest einen einzelnen Tastendruck (blockierend).

    Nutzt msvcrt.getch() in echten Windows-Konsolen,
    oder GetAsyncKeyState-Polling in PyCharm/IDE-Konsolen.

    Returns:
        'up', 'down', 'left', 'right', 'enter', 'escape',
        'backspace', oder das gedrückte Zeichen als String.
    """
    if _REAL_CONSOLE:
        return _read_key_msvcrt()
    return _read_key_polling()


def interactive_select(options: list[str], title: str = "",
                       allow_cancel: bool = True) -> int:
    """Interaktive Menü-Auswahl mit Pfeiltasten.

    Navigation:
        Hoch/Runter  - Auswahl bewegen
        Enter/Rechts - Bestätigen
        Escape/Links - Abbrechen (gibt -1 zurück)
        0-9          - Direkte Nummern-Eingabe

    Drei Modi je nach Konsolen-Umgebung:
        - cmd/PowerShell: Mehrzeiliges Menü mit Cursor-Bewegung
        - PyCharm/IDE:    Einzeilen-Navigation (\\r überschreibt)
        - Sonstige:       Klassische Nummern-Eingabe

    Args:
        options: Liste der Optionen (werden als Text angezeigt)
        title: Optionaler Titel über dem Menü
        allow_cancel: Ob Escape/Links erlaubt ist

    Returns:
        Index der gewählten Option (0-basiert), oder -1 bei Abbruch.
    """
    if not options:
        return -1

    if _ANSI_ENABLED:
        # Voller ANSI: Mehrzeiliges Menü mit Cursor-Bewegung (cmd/PowerShell)
        return _ansi_select(options, title, allow_cancel)
    elif _PYCHARM:
        # PyCharm: Einzeilen-Navigation mit \r (ANSI-Farben ja, Cursor nein)
        return _single_line_select(options, title, allow_cancel)
    else:
        # Fallback: Klassische Nummern-Eingabe
        return _fallback_select(options, title, allow_cancel)


def _ansi_select(options: list[str], title: str,
                 allow_cancel: bool) -> int:
    """Mehrzeiliges Menü mit ANSI-Cursor-Bewegung (echte Windows-Konsole)."""
    selected = 0
    num_options = len(options)

    flush_input_buffer()

    if title:
        print(title)

    cancel_str = ", Esc=Abbruch" if allow_cancel else ""
    print(f"  (Pfeiltasten: navigieren, Enter: wählen{cancel_str})")

    _draw_menu(options, selected)

    while True:
        key = read_key()

        if key == 'up':
            selected = (selected - 1) % num_options
        elif key == 'down':
            selected = (selected + 1) % num_options
        elif key in ('enter', 'right'):
            _clear_menu_lines(num_options)
            print(f"  > {options[selected]}")
            return selected
        elif key in ('escape', 'left') and allow_cancel:
            _clear_menu_lines(num_options)
            print("  (Abgebrochen)")
            return -1
        elif key.isdigit():
            num = int(key)
            if 1 <= num <= num_options:
                _clear_menu_lines(num_options)
                print(f"  > {options[num - 1]}")
                return num - 1
            elif num == 0 and allow_cancel:
                _clear_menu_lines(num_options)
                print("  (Abgebrochen)")
                return -1
            continue
        else:
            continue

        _clear_menu_lines(num_options)
        _draw_menu(options, selected)


def _single_line_select(options: list[str], title: str,
                        allow_cancel: bool) -> int:
    """Einzeilen-Navigation für PyCharm/IDE (kein Cursor-Movement nötig).

    Zeigt die aktuelle Auswahl auf EINER Zeile und überschreibt mit \\r.
    PyCharm unterstützt ANSI-Farben aber keine Cursor-Bewegung.
    """
    selected = 0
    num_options = len(options)

    if title:
        print(title)

    cancel_str = ", Esc=Abbruch" if allow_cancel else ""
    print(f"  (Pfeiltasten: navigieren, Enter: wählen{cancel_str})")

    # Alle Optionen einmal auflisten (statisch)
    for i, opt in enumerate(options):
        print(f"   {i+1}. {opt}")

    # Aktuelle Auswahl auf einer Zeile anzeigen (überschreibbar)
    _print_single_selection(options, selected, num_options)

    while True:
        key = read_key()

        if key == 'up':
            selected = (selected - 1) % num_options
        elif key == 'down':
            selected = (selected + 1) % num_options
        elif key in ('enter', 'right'):
            text = f"  > {options[selected]}"
            print(f"\r{text}{' ' * (60 - len(text))}")
            return selected
        elif key in ('escape', 'left') and allow_cancel:
            print(f"\r  (Abgebrochen){' ' * 40}")
            return -1
        elif key.isdigit():
            num = int(key)
            if 1 <= num <= num_options:
                text = f"  > {options[num - 1]}"
                print(f"\r{text}{' ' * (60 - len(text))}")
                return num - 1
            elif num == 0 and allow_cancel:
                print(f"\r  (Abgebrochen){' ' * 40}")
                return -1
            continue
        else:
            continue

        _print_single_selection(options, selected, num_options)


def _print_single_selection(options: list[str], selected: int,
                            total: int) -> None:
    """Zeigt aktuelle Auswahl auf einer Zeile mit \\r (PyCharm-kompatibel)."""
    text = f"  \033[7m >> [{selected+1}/{total}] {options[selected]} \033[0m"
    # \r springt an Zeilenanfang, Leerzeichen löschen Rest der alten Zeile
    print(f"\r{text}{' ' * 20}", end="", flush=True)


def _draw_menu(options: list[str], selected: int) -> None:
    """Zeichnet das Menü mit Auswahl-Markierung (nur echte Konsole)."""
    for i, opt in enumerate(options):
        if i == selected:
            print(f"  \033[7m {i+1}. {opt} \033[0m")  # Invertiert (highlighted)
        else:
            print(f"   {i+1}. {opt}")


def _clear_menu_lines(num_lines: int) -> None:
    """Bewegt den Cursor num_lines nach oben und löscht jede Zeile (nur echte Konsole)."""
    for _ in range(num_lines):
        print(f"\033[A\033[2K", end="", flush=True)


def _fallback_select(options: list[str], title: str,
                     allow_cancel: bool) -> int:
    """Fallback-Auswahl ohne ANSI (klassische Nummern-Eingabe)."""
    if title:
        print(title)
    for i, opt in enumerate(options):
        print(f"  [{i+1}] {opt}")
    if allow_cancel:
        print("  [0] Abbrechen")

    while True:
        try:
            choice = safe_input("> ").strip()
            if is_cancel(choice):
                return -1
            num = int(choice)
            if 1 <= num <= len(options):
                return num - 1
            if num == 0 and allow_cancel:
                return -1
            print(f"  -> Ungültig! (1-{len(options)})")
        except ValueError:
            print("  -> Bitte eine Nummer eingeben")


def wait_while_paused(state: 'AutoClickerState', message: str) -> bool:
    """
    Wartet solange pausiert ist. Gibt False zurück wenn gestoppt wurde.

    Args:
        state: AutoClickerState
        message: Nachricht die während der Pause angezeigt wird

    Returns:
        True wenn fortgesetzt, False wenn gestoppt
    """
    pause_interval = state.config.pause_check_interval
    while state.pause_event.is_set() and not state.stop_event.is_set():
        clear_line()
        print(f"{col('[PAUSE]', 'yellow')} {message} | Fortsetzen: {col('CTRL+ALT+G', 'yellow')}", end="", flush=True)
        time.sleep(pause_interval)
    return not state.stop_event.is_set()


def parse_time_input(time_str: str) -> tuple[float, str, float | None]:
    """Parst Zeit-Eingaben in verschiedenen Formaten.

    Unterstützte Formate:
        14:30       → Sekunden bis 14:30 Uhr (heute oder morgen)
        1430        → Sekunden bis 14:30 Uhr (4-stellig, 0000-2359)
        30s         → 30 Sekunden
        30m, 30min  → 30 Minuten
        2h, 2std    → 2 Stunden
        +30m        → In 30 Minuten (relativ)
        +2          → In 2 Minuten (+ ohne Einheit = Minuten)

    Returns:
        (sekunden: float, beschreibung: str, zielzeit_timestamp: float | None)
        - zielzeit_timestamp: Absolute Zielzeit bei Uhrzeiten (HH:MM, HHMM), sonst None
        Bei Fehler: (-1, fehlermeldung, None)
    """
    time_str = time_str.strip().lower()

    # Leere Eingabe
    if not time_str:
        return (-1, "Keine Zeit angegeben", None)

    # Relative Zeit mit + Präfix: +30m, +2h, +2 (ohne Einheit = Minuten)
    has_plus_prefix = time_str.startswith("+")
    if has_plus_prefix:
        time_str = time_str[1:]

    # Hilfsfunktion für Uhrzeiten (vermeidet Code-Duplizierung)
    def calculate_time_to_target(hour: int, minute: int) -> tuple[float, str, float]:
        """Berechnet Sekunden bis zur Zielzeit und gibt (seconds, description, timestamp) zurück."""
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # Wenn Zielzeit bereits vorbei ist, nimm morgen
        if target <= now:
            target += timedelta(days=1)
            day_str = "morgen"
        else:
            day_str = "heute"

        seconds = (target - now).total_seconds()
        target_timestamp = target.timestamp()

        return (seconds, f"{day_str} um {hour:02d}:{minute:02d}", target_timestamp)

    # Format: HH:MM (Uhrzeit mit Doppelpunkt)
    if ":" in time_str:
        try:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0

            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return (-1, f"Ungültige Uhrzeit: {time_str}", None)

            return calculate_time_to_target(hour, minute)
        except ValueError:
            return (-1, f"Ungültiges Zeitformat: {time_str}", None)

    # Format: HHMM (4-stellige Uhrzeit ohne Doppelpunkt, 0000-2359)
    if time_str.isdigit() and len(time_str) == 4:
        try:
            hour = int(time_str[:2])
            minute = int(time_str[2:])

            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return (-1, f"Ungültige Uhrzeit: {time_str} (gültig: 0000-2359)", None)

            return calculate_time_to_target(hour, minute)
        except ValueError:
            return (-1, f"Ungültiges Zeitformat: {time_str}", None)

    # Format: Zahl mit Einheit (30s, 30m, 30min, 2h, 2std)
    # Bei + Präfix ohne Einheit: Default = Minuten
    try:
        unit = None
        value_str = time_str

        if time_str.endswith("std"):
            unit = "h"
            value_str = time_str[:-3]
        elif time_str.endswith("min"):
            unit = "m"
            value_str = time_str[:-3]
        elif time_str.endswith("h"):
            unit = "h"
            value_str = time_str[:-1]
        elif time_str.endswith("m"):
            unit = "m"
            value_str = time_str[:-1]
        elif time_str.endswith("s"):
            unit = "s"
            value_str = time_str[:-1]
        elif has_plus_prefix:
            # + Präfix ohne Einheit = Minuten
            unit = "m"
        else:
            # Keine Einheit und kein + Präfix = Fehler
            return (-1, f"Einheit fehlt! Nutze z.B. '{time_str}s', '{time_str}m' oder '{time_str}h'", None)

        value = float(value_str)

        if value < 0:
            return (-1, "Zeit muss positiv sein", None)

        if unit == "h":
            seconds = value * 3600
            desc = f"{value:.0f}h" if value == int(value) else f"{value}h"
        elif unit == "m":
            seconds = value * 60
            desc = f"{value:.0f}m" if value == int(value) else f"{value}m"
        else:
            seconds = value
            desc = f"{value:.0f}s" if value == int(value) else f"{value}s"

        # Relative Zeiten haben keine absolute Zielzeit
        return (seconds, desc, None)
    except ValueError:
        return (-1, f"Ungültige Zahl: {time_str}", None)


def parse_non_negative_float(value: str, field_name: str = "Wert") -> tuple[float | None, str | None]:
    """Parst einen nicht-negativen Float-Wert aus einem String.

    Returns:
        (wert, None) bei Erfolg, (None, fehlermeldung) bei Fehler.
    """
    try:
        v = float(value)
    except ValueError:
        return None, f"'{value}' ist keine gültige Zahl"
    if v < 0:
        return None, f"{field_name} darf nicht negativ sein (Eingabe: {v:g})"
    return v, None


def parse_non_negative_range(value: str, field_name: str = "Bereich") -> tuple[tuple[float, float] | None, str | None]:
    """Parst einen nicht-negativen Min-Max-Bereich aus einem String (Format: 'min-max').

    Returns:
        ((min, max), None) bei Erfolg, (None, fehlermeldung) bei Fehler.
    """
    parts = value.split("-", 1)
    if len(parts) != 2:
        return None, f"{field_name}: Format <Min>-<Max> erwartet (z.B. 1-5)"
    min_val, min_err = parse_non_negative_float(parts[0], "Min")
    if min_err:
        return None, min_err
    max_val, max_err = parse_non_negative_float(parts[1], "Max")
    if max_err:
        return None, max_err
    if max_val < min_val:
        return None, f"Max ({max_val:g}) muss >= Min ({min_val:g}) sein"
    return (min_val, max_val), None


def format_duration(seconds: float) -> str:
    """Formatiert Sekunden als hh:mm:ss oder mm:ss."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
