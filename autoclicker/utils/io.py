"""
Input-Handling: Tastatur, interaktive Auswahl, Pause-Warten.

Drei Konsolen-Modi werden unterstützt:
  - echte Windows-Konsole (cmd/PowerShell): msvcrt + ANSI mit Cursor-Bewegung
  - PyCharm/IntelliJ: GetAsyncKeyState-Polling + ANSI ohne Cursor
  - sonstige IDE-Konsolen: Fallback auf Nummern-Eingabe

Konsolen-Detection lebt in console.py — wir importieren die _REAL_CONSOLE,
_ANSI_ENABLED, _PYCHARM-Flags von dort.
"""

import ctypes
import msvcrt
import sys
import time
from typing import TYPE_CHECKING

from .console import (
    _REAL_CONSOLE, _ANSI_ENABLED, _PYCHARM,
    col, clear_line,
)

if TYPE_CHECKING:
    from ..models import AutoClickerState


# =============================================================================
# ABBRUCH-ERKENNUNG
# =============================================================================

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


# =============================================================================
# ZEILEN-INPUT (safe_input mit ESC-Support)
# =============================================================================

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
            elif ch in ('\r', '\n'):  # Enter
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


# =============================================================================
# EINZEL-TASTEN-INPUT (für Pfeiltasten-Navigation)
# =============================================================================

# Virtual Key Codes für GetAsyncKeyState
_VK_MAP = {
    0x26: 'up',        # VK_UP
    0x28: 'down',      # VK_DOWN
    0x25: 'left',      # VK_LEFT
    0x27: 'right',     # VK_RIGHT
    0x0D: 'enter',     # VK_RETURN
    0x1B: 'escape',    # VK_ESCAPE
    0x08: 'backspace', # VK_BACK
}
# Zifferntasten 0-9: Hauptreihe + Numpad. VK_NUMPAD* kommt nur bei aktivem
# NumLock — dann erwartet der Nutzer Ziffern (Menü-Auswahl), keine Pfeile.
# Bei NumLock aus sendet der Numpad ohnehin VK_UP/DOWN/LEFT/RIGHT (oben gemappt).
for _i in range(10):
    _VK_MAP[0x30 + _i] = str(_i)
    _VK_MAP[0x60 + _i] = str(_i)


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


# =============================================================================
# INTERAKTIVE MENÜ-AUSWAHL
# =============================================================================

def interactive_select(options: list[str], title: str = "",
                       allow_cancel: bool = True, default: int = 0) -> int:
    """Interaktive Menü-Auswahl mit Pfeiltasten.

    Navigation:
        Hoch/Runter  - Auswahl bewegen
        Enter/Rechts - Bestätigen
        Escape/Links - Abbrechen (gibt -1 zurück)
        0-9          - Direkte Nummern-Eingabe

    default: Index der vorausgewählten Option (z.B. der aktuelle Wert beim
    Bearbeiten) — Enter bestätigt diesen direkt.

    Drei Modi je nach Konsolen-Umgebung:
        - cmd/PowerShell: Mehrzeiliges Menü mit Cursor-Bewegung
        - PyCharm/IDE:    Einzeilen-Navigation (\\r überschreibt)
        - Sonstige:       Klassische Nummern-Eingabe

    Returns:
        Index der gewählten Option (0-basiert), oder -1 bei Abbruch.
    """
    if not options:
        return -1
    default = max(0, min(default, len(options) - 1))

    if _ANSI_ENABLED:
        return _ansi_select(options, title, allow_cancel, default)
    elif _PYCHARM:
        return _single_line_select(options, title, allow_cancel, default)
    else:
        return _fallback_select(options, title, allow_cancel, default)


def _navigate_select(num_options: int, allow_cancel: bool, default: int, redraw) -> int:
    """Gemeinsame Tasten-Navigationsschleife der Pfeiltasten-Menüs.

    Behandelt hoch/runter/enter/escape/Ziffern einheitlich; `redraw(selected)`
    wird nach jeder Bewegung aufgerufen, damit jeder Modus selbst weiß, wie er
    neu zeichnet (mehrzeilig vs. \\r-Einzeiler). Gibt den gewählten Index
    zurück oder -1 bei Abbruch.
    """
    selected = default
    while True:
        key = read_key()
        if key == 'up':
            selected = (selected - 1) % num_options
        elif key == 'down':
            selected = (selected + 1) % num_options
        elif key in ('enter', 'right'):
            return selected
        elif key in ('escape', 'left') and allow_cancel:
            return -1
        elif key.isdigit():
            num = int(key)
            if 1 <= num <= num_options:
                return num - 1
            if num == 0 and allow_cancel:
                return -1
            continue
        else:
            continue
        redraw(selected)


def _ansi_select(options: list[str], title: str,
                 allow_cancel: bool, default: int = 0) -> int:
    """Mehrzeiliges Menü mit ANSI-Cursor-Bewegung (echte Windows-Konsole)."""
    num_options = len(options)
    flush_input_buffer()

    if title:
        print(title)
    cancel_str = ", Esc=Abbruch" if allow_cancel else ""
    print(f"  (Pfeiltasten: navigieren, Enter: wählen{cancel_str})")
    _draw_menu(options, default)

    def _redraw(selected: int) -> None:
        _clear_menu_lines(num_options)
        _draw_menu(options, selected)

    choice = _navigate_select(num_options, allow_cancel, default, _redraw)
    _clear_menu_lines(num_options)
    print("  (Abgebrochen)" if choice == -1 else f"  > {options[choice]}")
    return choice


def _single_line_select(options: list[str], title: str,
                        allow_cancel: bool, default: int = 0) -> int:
    """Einzeilen-Navigation für PyCharm/IDE (kein Cursor-Movement nötig).

    Zeigt die aktuelle Auswahl auf EINER Zeile und überschreibt mit \\r.
    PyCharm unterstützt ANSI-Farben aber keine Cursor-Bewegung.
    """
    num_options = len(options)

    if title:
        print(title)
    cancel_str = ", Esc=Abbruch" if allow_cancel else ""
    print(f"  (Pfeiltasten: navigieren, Enter: wählen{cancel_str})")
    # Alle Optionen einmal auflisten (statisch), dann die Auswahl-Zeile
    for i, opt in enumerate(options):
        print(f"   {i+1}. {opt}")
    _print_single_selection(options, default, num_options)

    def _redraw(selected: int) -> None:
        _print_single_selection(options, selected, num_options)

    choice = _navigate_select(num_options, allow_cancel, default, _redraw)
    if choice == -1:
        print(f"\r  (Abgebrochen){' ' * 40}")
    else:
        text = f"  > {options[choice]}"
        print(f"\r{text}{' ' * (60 - len(text))}")
    return choice


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
        print("\033[A\033[2K", end="", flush=True)


def _fallback_select(options: list[str], title: str,
                     allow_cancel: bool, default: int = 0) -> int:
    """Fallback-Auswahl ohne ANSI (klassische Nummern-Eingabe)."""
    if title:
        print(title)
    for i, opt in enumerate(options):
        marker = " *" if i == default else ""
        print(f"  [{i+1}] {opt}{marker}")
    if allow_cancel:
        print("  [0] Abbrechen")

    while True:
        try:
            choice = safe_input("> ").strip()
            if is_cancel(choice):
                return -1
            if not choice:  # Enter = markierte Default-Option
                return default
            num = int(choice)
            if 1 <= num <= len(options):
                return num - 1
            if num == 0 and allow_cancel:
                return -1
            print(f"  -> Ungültig! (1-{len(options)})")
        except ValueError:
            print("  -> Bitte eine Nummer eingeben")


# =============================================================================
# PAUSE-HANDLING
# =============================================================================

def wait_while_paused(state: 'AutoClickerState', message: str) -> bool:
    """Wartet solange pausiert ist. Gibt False zurück wenn gestoppt wurde."""
    pause_interval = state.config.timing_pause_interval
    while state.pause_event.is_set() and not state.stop_event.is_set():
        clear_line()
        print(f"{col('[PAUSE]', 'yellow')} {message} | Fortsetzen: {col('CTRL+ALT+G', 'yellow')}", end="", flush=True)
        time.sleep(pause_interval)
    return not state.stop_event.is_set()
