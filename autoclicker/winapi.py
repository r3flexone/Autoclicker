"""
Windows API Konstanten, Strukturen und Funktionen.
Kapselt alle ctypes-Definitionen für Maus, Tastatur und Hotkeys.
"""

import ctypes
import ctypes.wintypes as wintypes
import logging
import time
from typing import TYPE_CHECKING

logger = logging.getLogger("autoclicker")

if TYPE_CHECKING:
    from .models import AutoClickerState

from .config import CONFIG
from .utils import err, warn

# =============================================================================
# DPI-AWARENESS (muss früh gesetzt werden)
# =============================================================================
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except (AttributeError, OSError):
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Fallback für ältere Windows
    except (AttributeError, OSError):
        pass  # DPI-Awareness nicht unterstützt


# =============================================================================
# WINDOWS API KONSTANTEN
# =============================================================================
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000

# Virtual Key Codes
VK_A = 0x41  # Add Point
VK_U = 0x55  # Undo
VK_C = 0x43  # Clear all points
VK_X = 0x58  # Reset all (points + sequences) - X statt R (R oft belegt)
VK_E = 0x45  # Editor
VK_N = 0x4E  # Item-Scan Editor (N für New/Scan)
VK_L = 0x4C  # Load
VK_P = 0x50  # Print/Show
VK_S = 0x53  # Start/Stop
VK_T = 0x54  # Test colors (Farb-Analysator)
VK_Q = 0x51  # Quit
VK_G = 0x47  # Pause/Resume (G statt R wegen Konflikten)
VK_K = 0x4B  # Skip current wait
VK_W = 0x57  # Quick-Switch (Wechseln)
VK_Z = 0x5A  # Schedule (Zeitplan)
VK_F = 0x46  # Finish (Zyklus abschließen)

# Hotkey IDs
HOTKEY_RECORD = 1
HOTKEY_UNDO = 2
HOTKEY_CLEAR = 3
HOTKEY_RESET = 4
HOTKEY_EDITOR = 5
HOTKEY_ITEM_SCAN = 6
HOTKEY_LOAD = 7
HOTKEY_SHOW = 8
HOTKEY_TOGGLE = 9
HOTKEY_ANALYZE = 10
HOTKEY_QUIT = 11
HOTKEY_PAUSE = 12
HOTKEY_SKIP = 13
HOTKEY_SWITCH = 14
HOTKEY_SCHEDULE = 15
HOTKEY_FINISH = 16

# Window Messages
WM_HOTKEY = 0x0312

# Mouse Input
INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

# Keyboard Input
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

# Häufige Virtual Key Codes für Tastatureingaben
VK_CODES = {
    "enter": 0x0D, "return": 0x0D,
    "tab": 0x09,
    "space": 0x20, "leertaste": 0x20,
    "escape": 0x1B, "esc": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E, "del": 0x2E,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
    "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
    "f11": 0x7A, "f12": 0x7B,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45,
    "f": 0x46, "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A,
    "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E, "o": 0x4F,
    "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59, "z": 0x5A,
}

PM_REMOVE = 0x0001


# =============================================================================
# WINDOWS API STRUKTUREN
# =============================================================================
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION),
    ]


# =============================================================================
# WINDOWS API FUNKTIONEN (user32, kernel32)
# =============================================================================
user32 = ctypes.windll.user32

user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL

user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL

user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL

user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL

user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL

user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

kernel32 = ctypes.windll.kernel32
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


# =============================================================================
# MAUS- UND TASTATUR-FUNKTIONEN
# =============================================================================
def get_cursor_pos() -> tuple[int, int]:
    """Liest die aktuelle Mausposition."""
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def set_cursor_pos(x: int, y: int) -> bool:
    """Setzt die Mausposition."""
    return bool(user32.SetCursorPos(x, y))


def send_click(x: int, y: int, move_delay: float = 0.01, post_delay: float = 0.05) -> None:
    """Führt einen Linksklick an der angegebenen Position aus."""
    set_cursor_pos(x, y)
    time.sleep(move_delay)

    inputs = (INPUT * 2)()
    inputs[0].type = INPUT_MOUSE
    inputs[0].union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
    inputs[1].type = INPUT_MOUSE
    inputs[1].union.mi.dwFlags = MOUSEEVENTF_LEFTUP

    sent = user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
    if sent != 2:
        logger.warning(f"SendInput Klick: nur {sent}/2 Events gesendet @ ({x}, {y})")

    # Warte nach dem Klick damit das Ziel-Programm den Klick verarbeiten kann
    if post_delay > 0:
        time.sleep(post_delay)


def send_key(key_name: str) -> bool:
    """Führt einen Tastendruck aus. Gibt True zurück wenn erfolgreich."""
    key_lower = key_name.lower()
    if key_lower not in VK_CODES:
        print(err(f"Unbekannte Taste: '{key_name}'"))
        print(f"         Verfügbar: {', '.join(sorted(VK_CODES.keys()))}")
        return False

    vk_code = VK_CODES[key_lower]

    inputs = (INPUT * 2)()
    # Key down
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].union.ki.wVk = vk_code
    inputs[0].union.ki.dwFlags = 0
    # Key up
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].union.ki.wVk = vk_code
    inputs[1].union.ki.dwFlags = KEYEVENTF_KEYUP

    sent = user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
    if sent != 2:
        logger.warning(f"SendInput Taste '{key_name}': nur {sent}/2 Events gesendet")
        return False
    return True


def check_failsafe(state: 'AutoClickerState' = None) -> bool:
    """Prüft, ob die Maus in der Fail-Safe-Ecke ist."""
    cfg = state.config if state else CONFIG
    if not cfg.failsafe_enabled:
        return False
    x, y = get_cursor_pos()
    return x <= cfg.failsafe_x and y <= cfg.failsafe_y


# =============================================================================
# HOTKEY-REGISTRIERUNG
# =============================================================================
def register_hotkeys() -> bool:
    """Registriert alle globalen Hotkeys."""
    success = True
    hotkeys = [
        (HOTKEY_RECORD, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_A, "CTRL+ALT+A (Punkt speichern)"),
        (HOTKEY_UNDO, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_U, "CTRL+ALT+U (Rückgängig)"),
        (HOTKEY_CLEAR, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_C, "CTRL+ALT+C (Alle löschen)"),
        (HOTKEY_RESET, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_X, "CTRL+ALT+X (Factory Reset)"),
        (HOTKEY_EDITOR, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_E, "CTRL+ALT+E (Editor)"),
        (HOTKEY_ITEM_SCAN, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_N, "CTRL+ALT+N (Item-Scan)"),
        (HOTKEY_LOAD, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_L, "CTRL+ALT+L (Laden)"),
        (HOTKEY_SHOW, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_P, "CTRL+ALT+P (Punkte anzeigen)"),
        (HOTKEY_TOGGLE, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_S, "CTRL+ALT+S (Start/Stop)"),
        (HOTKEY_ANALYZE, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_T, "CTRL+ALT+T (Farb-Analyse)"),
        (HOTKEY_QUIT, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_Q, "CTRL+ALT+Q (Beenden)"),
        (HOTKEY_PAUSE, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_G, "CTRL+ALT+G (Pause)"),
        (HOTKEY_SKIP, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_K, "CTRL+ALT+K (Skip)"),
        (HOTKEY_SWITCH, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_W, "CTRL+ALT+W (Wechseln)"),
        (HOTKEY_SCHEDULE, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_Z, "CTRL+ALT+Z (Zeitplan)"),
        (HOTKEY_FINISH, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_F, "CTRL+ALT+F (Sanft beenden)"),
    ]

    for hotkey_id, modifiers, vk, name in hotkeys:
        if not user32.RegisterHotKey(None, hotkey_id, modifiers, vk):
            print(warn(f"Konnte Hotkey nicht registrieren: {name}"))
            success = False

    return success


def unregister_hotkeys() -> None:
    """Deregistriert alle globalen Hotkeys."""
    for hotkey_id in range(1, HOTKEY_FINISH + 1):
        user32.UnregisterHotKey(None, hotkey_id)
