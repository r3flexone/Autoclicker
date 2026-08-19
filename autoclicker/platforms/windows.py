"""
Windows API Konstanten, Strukturen und Funktionen.
Kapselt alle ctypes-Definitionen für Maus, Tastatur und Hotkeys.
"""

import ctypes
import ctypes.wintypes as wintypes
import logging
import struct
import time
from typing import TYPE_CHECKING

from .common import (
    APP_ID, HOTKEY_ANALYZE, HOTKEY_CLEAR, HOTKEY_EDITOR, HOTKEY_FINISH,
    HOTKEY_HELP, HOTKEY_IMPORT_EXPORT, HOTKEY_ITEM_SCAN, HOTKEY_LOAD,
    HOTKEY_PAUSE, HOTKEY_QUIT, HOTKEY_RECORD, HOTKEY_RECORD_COLOR,
    HOTKEY_RECORD_PAUSE, HOTKEY_RECORD_SCREENSHOT, HOTKEY_RECORD_SEQ,
    HOTKEY_REC_PHASE, HOTKEY_REC_REGION, HOTKEY_REC_WATCH, HOTKEY_RESET,
    HOTKEY_SCAN_STUDIO, HOTKEY_SCHEDULE, HOTKEY_SEQUENCE_STUDIO,
    HOTKEY_SHOW, HOTKEY_SKIP, HOTKEY_SWITCH, HOTKEY_TOGGLE, HOTKEY_UNDO,
    PlatformError, WHEEL_STEP,
)

logger = logging.getLogger("autoclicker")

if TYPE_CHECKING:
    from ..models import AutoClickerState

from .. import symbol
from ..config import CONFIG
from ..utils import err, warn

# Win32-spezifische Modifier und Virtual-Key-Codes bleiben im Windows-Backend.
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
MOD_REC = MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_NOREPEAT

VK_A, VK_B, VK_C, VK_D, VK_E, VK_F = (0x41, 0x42, 0x43, 0x44, 0x45, 0x46)
VK_G, VK_H, VK_I, VK_J, VK_K, VK_L = (0x47, 0x48, 0x49, 0x4A, 0x4B, 0x4C)
VK_M, VK_N, VK_O, VK_P, VK_Q, VK_R = (0x4D, 0x4E, 0x4F, 0x50, 0x51, 0x52)
VK_S, VK_T, VK_U, VK_V, VK_W, VK_X = (0x53, 0x54, 0x55, 0x56, 0x57, 0x58)
VK_Y, VK_Z = 0x59, 0x5A

VK_CODES = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09,
    "space": 0x20, "leertaste": 0x20,
    "escape": 0x1B, "esc": 0x1B, "backspace": 0x08,
    "delete": 0x2E, "del": 0x2E,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
    **{str(i): 0x30 + i for i in range(10)},
    **{chr(97 + i): 0x41 + i for i in range(26)},
}

WHEEL_DELTA = WHEEL_STEP

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


# Window Messages
WM_HOTKEY = 0x0312
WM_SETICON = 0x0080
WM_LBUTTONDOWN = 0x0201
WM_MOUSEWHEEL = 0x020A
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104     # Taste mit gedruecktem ALT (z.B. ALT+F4)

# Mouse Input
INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800

# Keyboard Input
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

PM_REMOVE = 0x0001
SRCCOPY = 0x00CC0020
PW_RENDERFULLCONTENT = 0x00000002


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


class BITMAPINFOHEADER(ctypes.Structure):
    """Minimaler 32-Bit-DIB-Header für Desktop- und Fensteraufnahmen."""

    _fields_ = [
        ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
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
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

gdi32 = ctypes.windll.gdi32
gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.GetPixel.restype = wintypes.COLORREF

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.BitBlt.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL

user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.GetDesktopWindow.restype = wintypes.HWND
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

# Low-Level Mouse Hook
_LRESULT = ctypes.c_ssize_t
_HOOKPROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = _LRESULT

WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13


class _POINT_LL(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", _POINT_LL),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


_mouse_hook_handle = None
_mouse_hook_proc = None  # Referenz halten, damit GC den Callback nicht räumt
_keyboard_hook_handle = None
_keyboard_hook_proc = None


# Rueckwaerts-Tabelle VK-Code -> Tastenname, fuer die Aufnahme: der Hook liefert einen
# Code, `send_key()` will einen Namen. Bei Mehrfachnamen gewinnt der ERSTE aus VK_CODES
# ("enter" vor "return", "space" vor "leertaste") - dict behaelt die Reihenfolge, und die
# Erstnennung ist jeweils die gelaeufigere.
VK_NAMES = {}
for _name, _vk in VK_CODES.items():
    VK_NAMES.setdefault(_vk, _name)
del _name, _vk


def get_screen_pixel(x: int, y: int) -> tuple[int, int, int] | None:
    """Liest die Pixelfarbe an einer Bildschirmposition.

    Schneller GDI-Pfad (GetDC/GetPixel) zuerst — ideal in Aufnahme-Callbacks.
    GetDC(None) ist aber am primären Monitor verankert; auf Mehrmonitor-Setups
    mit Fenstern bei negativen/grossen Koordinaten liefert GetPixel dort
    CLR_INVALID. In dem Fall Fallback auf den Pillow-Pfad (all_screens=True),
    der den gesamten virtuellen Desktop abdeckt.
    """
    try:
        hdc = user32.GetDC(None)
        colorref = gdi32.GetPixel(hdc, x, y)
        user32.ReleaseDC(None, hdc)
        if colorref != 0xFFFFFFFF:  # nicht CLR_INVALID
            return (colorref & 0xFF, (colorref >> 8) & 0xFF, (colorref >> 16) & 0xFF)
    except (OSError, AttributeError):
        pass
    # Fallback: virtueller Desktop (zweiter Monitor, negative Koordinaten)
    try:
        from ..imaging import get_pixel_color
        return get_pixel_color(x, y)
    except Exception:
        return None


def install_mouse_hook(on_lbutton_down, on_wheel=None) -> bool:
    """Installiert einen systemweiten Low-Level-Maus-Hook für Linksklicks und Mausrad.

    on_lbutton_down(x, y, color) wird bei jedem Linksklick aufgerufen.
    color ist ein (r,g,b)-Tupel oder None.
    on_wheel(x, y, delta) wird bei jeder Mausrad-Bewegung aufgerufen; `delta` ist die
    ROHE Windows-Distanz (positiv = hoch), eine Rasterstufe = WHEEL_DELTA. Bewusst
    nicht hier schon in Stufen umgerechnet: hochaufloesende Raeder senden Bruchteile,
    und einzeln abgerundet ergaeben die null. Der Aufrufer summiert erst und teilt dann.
    None = Mausrad wird ignoriert.

    Rechtsklicks fehlen bewusst: der Autoclicker kann gar keine ausfuehren
    (`send_click` ist auf LEFTDOWN/LEFTUP festgelegt). Sie aufzuzeichnen hiesse,
    etwas mitzuschneiden, das beim Abspielen zum Linksklick wuerde.
    """
    global _mouse_hook_handle, _mouse_hook_proc

    if _mouse_hook_handle:
        return True  # bereits installiert

    def _hook_proc(nCode, wParam, lParam):
        if nCode >= 0 and wParam == WM_LBUTTONDOWN:
            info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            x, y = info.pt.x, info.pt.y
            color = get_screen_pixel(x, y)
            try:
                on_lbutton_down(x, y, color)
            except Exception:
                pass
        elif nCode >= 0 and wParam == WM_MOUSEWHEEL and on_wheel is not None:
            info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            # Die Rad-Distanz steht im HIGH word von mouseData und ist VORZEICHENBEHAFTET.
            # mouseData ist ein DWORD (unsigned), deshalb von Hand ins Zweierkomplement
            # zurueckrechnen - sonst wird jedes Runterscrollen zu einem riesigen Plus.
            delta = (info.mouseData >> 16) & 0xFFFF
            if delta >= 0x8000:
                delta -= 0x10000
            try:
                on_wheel(info.pt.x, info.pt.y, delta)
            except Exception:
                pass
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    _mouse_hook_proc = _HOOKPROC(_hook_proc)
    h_module = kernel32.GetModuleHandleW(None)
    handle = user32.SetWindowsHookExW(WH_MOUSE_LL, _mouse_hook_proc, h_module, 0)
    if handle:
        _mouse_hook_handle = handle
        return True
    _mouse_hook_proc = None
    return False


def remove_mouse_hook() -> None:
    """Entfernt den installierten Maus-Hook."""
    global _mouse_hook_handle, _mouse_hook_proc
    if _mouse_hook_handle:
        user32.UnhookWindowsHookEx(_mouse_hook_handle)
        _mouse_hook_handle = None
    _mouse_hook_proc = None


# Modifier-Tasten. Waehrend der Aufnahme wird bei gedruecktem CTRL oder ALT NICHTS
# mitgeschnitten - dort liegen die Hotkeys der App (alle CTRL+ALT+Buchstabe). Sonst
# stuende ein 'j' in der Sequenz, sobald man die Aufnahme mit CTRL+ALT+J stoppt.
_VK_CONTROL, _VK_MENU, _VK_SHIFT = 0x11, 0x12, 0x10


def install_keyboard_hook(on_key_down) -> bool:
    """Installiert einen systemweiten Low-Level-Tastatur-Hook für die Aufnahme.

    on_key_down(name) wird beim Herunterdruecken einer Taste aufgerufen; `name` ist
    ein Schluessel aus VK_CODES, also genau das, was `send_key()` wieder abspielen kann.

    Drei Dinge werden bewusst NICHT gemeldet:
    - Tasten mit gedruecktem CTRL oder ALT (das sind die Hotkeys der App)
    - Tasten, die `send_key()` gar nicht kennt (waeren beim Abspielen still weg)
    - die Wiederholungen einer festgehaltenen Taste (Windows feuert dann laufend
      WM_KEYDOWN nach; ohne Filter entstuenden daraus dutzende Schritte)
    """
    global _keyboard_hook_handle, _keyboard_hook_proc

    if _keyboard_hook_handle:
        return True

    gedrueckt = set()  # welche VK-Codes gerade unten sind -> Auto-Repeat erkennen

    def _hook_proc(nCode, wParam, lParam):
        if nCode >= 0:
            info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = info.vkCode
            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if vk not in gedrueckt:
                    gedrueckt.add(vk)
                    hoch = user32.GetAsyncKeyState
                    modifier = (hoch(_VK_CONTROL) & 0x8000) or (hoch(_VK_MENU) & 0x8000)
                    name = VK_NAMES.get(vk)
                    if name and not modifier:
                        try:
                            on_key_down(name)
                        except Exception:
                            pass
            else:
                gedrueckt.discard(vk)
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    _keyboard_hook_proc = _HOOKPROC(_hook_proc)
    h_module = kernel32.GetModuleHandleW(None)
    handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _keyboard_hook_proc, h_module, 0)
    if handle:
        _keyboard_hook_handle = handle
        return True
    _keyboard_hook_proc = None
    return False


def remove_keyboard_hook() -> None:
    """Entfernt den installierten Tastatur-Hook."""
    global _keyboard_hook_handle, _keyboard_hook_proc
    if _keyboard_hook_handle:
        user32.UnhookWindowsHookEx(_keyboard_hook_handle)
        _keyboard_hook_handle = None
    _keyboard_hook_proc = None


# =============================================================================
# BILDSCHIRM-GEOMETRIE
# =============================================================================
# Lag vorher fuenfmal im Baum verstreut (imaging, item_scan, diagnose, scan_studio,
# console), jedes Mal mit eigenen SM_*-Konstanten und eigenem try/except. Genau solche
# Kopien machen eine Portierung teuer: fuer Linux muesste man alle fuenf finden.

_SM_CXSCREEN, _SM_CYSCREEN = 0, 1
_SM_XVIRTUALSCREEN, _SM_YVIRTUALSCREEN = 76, 77
_SM_CXVIRTUALSCREEN, _SM_CYVIRTUALSCREEN = 78, 79


def get_screen_size() -> tuple[int, int] | None:
    """Groesse des Primaermonitors, oder None wenn nicht ermittelbar."""
    try:
        b, h = user32.GetSystemMetrics(_SM_CXSCREEN), user32.GetSystemMetrics(_SM_CYSCREEN)
    except (AttributeError, OSError):
        return None
    return (b, h) if b > 0 and h > 0 else None


def get_virtual_desktop() -> tuple[int, int, int, int] | None:
    """(links, oben, rechts, unten) ueber ALLE Monitore, oder None.

    Auf Nicht-Windows (oder bei gestubbtem ctypes) kommt 0 zurueck - dann lieber None
    liefern als eine Flaeche von 0x0 zu behaupten, gegen die jede Koordinate ausserhalb
    liegt.
    """
    try:
        x = user32.GetSystemMetrics(_SM_XVIRTUALSCREEN)
        y = user32.GetSystemMetrics(_SM_YVIRTUALSCREEN)
        b = user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN)
        h = user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN)
    except (AttributeError, OSError):
        return None
    if b <= 0 or h <= 0:
        return None
    return (x, y, x + b, y + h)


def get_virtual_origin() -> tuple[int, int]:
    """Linke/obere Kante des virtuellen Desktops. (0, 0), wenn nicht ermittelbar."""
    rect = get_virtual_desktop()
    return (rect[0], rect[1]) if rect else (0, 0)


def get_screen_center() -> tuple[int, int]:
    """Mitte des virtuellen Desktops, sonst des Primaermonitors, sonst 960x540."""
    rect = get_virtual_desktop()
    if rect:
        return (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    groesse = get_screen_size()
    if groesse:
        return groesse[0] // 2, groesse[1] // 2
    return 960, 540


# =============================================================================
# MAUS- UND TASTATUR-FUNKTIONEN
# =============================================================================
def get_cursor_pos() -> tuple[int, int]:
    """Liest die aktuelle Mausposition."""
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise PlatformError("Windows konnte die Mausposition nicht lesen")
    return point.x, point.y


def set_cursor_pos(x: int, y: int) -> bool:
    """Setzt die Mausposition."""
    return bool(user32.SetCursorPos(x, y))


def send_click(x: int, y: int, move_delay: float = 0.01,
               post_delay: float = 0.05) -> bool:
    """Führt einen Linksklick aus. True nur bei vollständig gesendeten Events."""
    if not set_cursor_pos(x, y):
        logger.error("Mausposition konnte nicht gesetzt werden: (%s, %s)", x, y)
        return False
    time.sleep(move_delay)

    inputs = (INPUT * 2)()
    inputs[0].type = INPUT_MOUSE
    inputs[0].union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
    inputs[1].type = INPUT_MOUSE
    inputs[1].union.mi.dwFlags = MOUSEEVENTF_LEFTUP

    sent = user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
    if sent != 2:
        logger.warning(f"SendInput Klick: nur {sent}/2 Events gesendet @ ({x}, {y})")
        return False

    # Warte nach dem Klick damit das Ziel-Programm den Klick verarbeiten kann
    if post_delay > 0:
        time.sleep(post_delay)
    return True


def send_scroll(clicks: int, x: int = None, y: int = None,
                move_delay: float = 0.01, post_delay: float = 0.05) -> bool:
    """Dreht das Mausrad um `clicks` Rasterstufen. Positiv = hoch, negativ = runter.

    Windows liefert das Scroll-Event an das Fenster UNTER dem Cursor, nicht an das
    fokussierte - deshalb muss der Zeiger vorher auf die Zielposition. Ohne x/y wird
    dort gescrollt, wo die Maus gerade steht.
    """
    if not clicks:
        return True
    if x is not None and y is not None:
        if not set_cursor_pos(x, y):
            logger.error("Mausposition fürs Scrollen nicht gesetzt: (%s, %s)", x, y)
            return False
        time.sleep(move_delay)

    inputs = (INPUT * 1)()
    inputs[0].type = INPUT_MOUSE
    inputs[0].union.mi.dwFlags = MOUSEEVENTF_WHEEL
    # mouseData ist ein DWORD (unsigned). Runterscrollen braucht einen negativen Delta,
    # der als Zweierkomplement in 32 Bit passen muss - explizit maskieren statt auf die
    # Breite von c_ulong zu vertrauen (auf Windows 32 Bit, anderswo 64).
    inputs[0].union.mi.mouseData = (clicks * WHEEL_DELTA) & 0xFFFFFFFF

    sent = user32.SendInput(1, inputs, ctypes.sizeof(INPUT))
    if sent != 1:
        logger.warning(f"SendInput Scroll: {sent}/1 Events gesendet ({clicks} Stufen)")
        return False

    if post_delay > 0:
        time.sleep(post_delay)
    return True


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


def get_foreground_window_title() -> str:
    """Gibt den Titel des aktuellen Vordergrund-Fensters zurück (leer bei Fehler)."""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value or ""
    except (OSError, AttributeError):
        return ""


def is_target_window_active(title_substring: str) -> bool:
    """Prüft ob der Titel des aktiven Fensters den gegebenen Substring enthält (case-insensitive).

    Leerer Substring → immer True (Check deaktiviert).
    """
    if not title_substring:
        return True
    current = get_foreground_window_title()
    return title_substring.lower() in current.lower()


# Fenster-Geometrie (für fenster-basiertes Koordinaten-Remapping bei Import/Export)
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL


def _find_window_by_title(title_substring: str):
    """Findet das HWND des ersten sichtbaren Fensters dessen Titel den Substring enthält."""
    if not title_substring:
        return None
    target = title_substring.lower()
    found = []

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if target in (buf.value or "").lower():
                found.append(hwnd)
                return False  # Enumeration abbrechen
        return True

    try:
        user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    except (OSError, AttributeError):
        return None
    return found[0] if found else None


def liste_fenster() -> list:
    """Alle sichtbaren Fenster als `(titel, (l, t, r, b), hwnd)`.

    Für den Fall, den `get_client_rect_by_title()` nicht lösen kann: **dasselbe
    Programm mehrmals offen.** Der Titel ist dann dreimal derselbe, und wer den
    Scan auf die Fassung oben links legen will, braucht die Fenster einzeln —
    unterscheidbar an ihrer Lage, nicht an ihrem Namen.

    Geliefert wird der **Client-Bereich** (Inhalt ohne Titelleiste und Rahmen),
    denn genau der ist das Spielfeld. Fenster ohne Titel, ohne Fläche oder
    ausserhalb aller Monitore fallen weg: sie sind Werkzeugfenster des Systems
    und in einer Auswahlliste nur Rauschen.

    Sortiert nach Lage (oben vor unten, links vor rechts) — dieselbe Reihenfolge,
    in der man sie auf dem Bildschirm sucht.
    """
    gefunden = []

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        laenge = user32.GetWindowTextLengthW(hwnd)
        if laenge <= 0:
            return True
        puffer = ctypes.create_unicode_buffer(laenge + 1)
        user32.GetWindowTextW(hwnd, puffer, laenge + 1)
        titel = (puffer.value or "").strip()
        if not titel:
            return True
        rect = wintypes.RECT()
        pt = wintypes.POINT(0, 0)
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return True
        if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return True
        breite, hoehe = rect.right - rect.left, rect.bottom - rect.top
        if breite < 80 or hoehe < 80:
            return True
        # Das Handle kommt mit: nur damit laesst sich das Fenster spaeter
        # DIREKT abbilden (`imaging.take_window_screenshot`), also auch dann,
        # wenn etwas davor liegt. Ueber den Titel ginge das nicht — bei
        # mehreren Fassungen desselben Spiels ist er dreimal derselbe.
        gefunden.append((titel, (pt.x, pt.y, pt.x + breite, pt.y + hoehe),
                         int(hwnd)))
        return True

    try:
        user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    except (OSError, AttributeError):
        return []
    schirm = get_virtual_desktop()
    if schirm:
        gefunden = [e for e in gefunden
                    if e[1][0] < schirm[2] and e[1][2] > schirm[0]
                    and e[1][1] < schirm[3] and e[1][3] > schirm[1]]
    return sorted(gefunden, key=lambda e: (e[1][1], e[1][0]))


def get_client_rect_by_handle(hwnd: int):
    """Client-Bereich eines HWND als absolute Bildschirm-Koordinaten."""
    if not hwnd:
        return None
    try:
        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return None
        pt = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return None
        return (pt.x, pt.y, pt.x + width, pt.y + height)
    except (OSError, AttributeError, TypeError, ValueError):
        return None


def resolve_window(title: str, instance: int = 0, reference_rect=None):
    """Findet eine gespeicherte Fensterquelle erneut.

    Ergebnis ist dasselbe Tupel wie ein Eintrag aus :func:`liste_fenster`.
    Exakte Titel gewinnen. Bei mehreren gleichnamigen Fenstern wählt die beim
    Speichern gemerkte, nach Bildschirmposition sortierte Instanz. Ist dieser
    Index nicht mehr vorhanden, gewinnt das geometrisch ähnlichste Fenster.
    """
    if not isinstance(title, str) or not title.strip():
        return None
    fenster = liste_fenster()
    ziel = title.strip().casefold()
    kandidaten = [e for e in fenster if e[0].strip().casefold() == ziel]
    if not kandidaten:
        kandidaten = [e for e in fenster if ziel in e[0].casefold()]
    if not kandidaten:
        return None
    try:
        index = int(instance)
    except (TypeError, ValueError):
        index = 0
    if 0 <= index < len(kandidaten):
        return kandidaten[index]
    if isinstance(reference_rect, (list, tuple)) and len(reference_rect) == 4:
        try:
            ref = tuple(int(v) for v in reference_rect)
            return min(kandidaten, key=lambda e: sum(
                abs(int(e[1][i]) - ref[i]) for i in range(4)))
        except (TypeError, ValueError):
            pass
    return kandidaten[0]


def get_client_rect_by_title(title_substring: str):
    """Liefert den Client-Bereich (Spielinhalt ohne Titelleiste/Rahmen) des Fensters
    mit passendem Titel als absolute Bildschirm-Koordinaten.

    Returns:
        (left, top, right, bottom) oder None wenn kein passendes/sinnvolles Fenster.
    """
    hwnd = _find_window_by_title(title_substring)
    if not hwnd:
        return None
    return get_client_rect_by_handle(hwnd)


def check_failsafe(state: 'AutoClickerState' = None) -> bool:
    """Prüft, ob die Maus in der Fail-Safe-Ecke ist."""
    cfg = state.config if state else CONFIG
    if not cfg.failsafe_enabled:
        return False
    try:
        x, y = get_cursor_pos()
    except PlatformError:
        return True
    return x <= cfg.failsafe_x and y <= cfg.failsafe_y


# =============================================================================
# HOTKEY-REGISTRIERUNG
# =============================================================================
# Zentrale Hotkey-Definition — register und unregister speisen sich beide hieraus,
# damit neue Hotkeys nicht versehentlich aus dem unregister-Pfad rausfallen.
_HOTKEY_DEFINITIONS = [
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
    (HOTKEY_IMPORT_EXPORT, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_I, "CTRL+ALT+I (Import/Export)"),
    (HOTKEY_RECORD_SEQ, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_J, "CTRL+ALT+J (Sequenz aufnehmen)"),
    (HOTKEY_RECORD_PAUSE, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_H, "CTRL+ALT+H (Aufnahme pausieren)"),
    (HOTKEY_SEQUENCE_STUDIO, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_B, "CTRL+ALT+B (Visueller Editor)"),
    (HOTKEY_SCAN_STUDIO, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_V, "CTRL+ALT+V (Scan-Studio)"),
    (HOTKEY_HELP, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_O, "CTRL+ALT+O (Hilfe anzeigen)"),
    (HOTKEY_RECORD_COLOR, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_M, "CTRL+ALT+M (Aufnahme: auf Farbe warten)"),
    (HOTKEY_RECORD_SCREENSHOT, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_D, "CTRL+ALT+D (Aufnahme: Screenshot-Marker)"),
    (HOTKEY_REC_PHASE, MOD_REC, VK_P, "CTRL+ALT+SHIFT+P (Aufnahme: Phasengrenze)"),
    (HOTKEY_REC_REGION, MOD_REC, VK_D, "CTRL+ALT+SHIFT+D (Aufnahme: Bereichs-Ecke)"),
    (HOTKEY_REC_WATCH, MOD_REC, VK_M, "CTRL+ALT+SHIFT+M (Aufnahme: beobachten ohne Klick)"),
]

# Windows-Fehlercode: Hotkey ist bereits registriert (von einem anderen Programm)
ERROR_HOTKEY_ALREADY_REGISTERED = 1409


def register_hotkeys() -> bool:
    """Registriert alle globalen Hotkeys."""
    success = True
    for hotkey_id, modifiers, vk, name in _HOTKEY_DEFINITIONS:
        if not user32.RegisterHotKey(None, hotkey_id, modifiers, vk):
            error_code = kernel32.GetLastError()
            print(warn(f"Konnte Hotkey nicht registrieren: {name} (Fehlercode {error_code})"))
            if error_code == ERROR_HOTKEY_ALREADY_REGISTERED:
                combo = name.split(" ", 1)[0]
                print(warn(f"  {combo}: Tastenkombination ist bereits von einem anderen Programm belegt."))
            success = False
    return success


def poll_hotkey() -> int | None:
    """Liefert den nächsten globalen Hotkey oder ``None``."""
    msg = wintypes.MSG()
    if user32.PeekMessageW(
            ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY, PM_REMOVE):
        return int(msg.wParam)
    return None


def get_current_thread_id() -> int:
    """Kennung des Threads mit der Windows-Nachrichtenqueue."""
    return int(kernel32.GetCurrentThreadId())


def post_quit(thread_id: int) -> None:
    """Weckt und beendet die Nachrichtenqueue des Hauptthreads."""
    user32.PostThreadMessageW(int(thread_id), 0x0012, 0, 0)  # WM_QUIT


def wait_for_key(names: tuple[str, ...], timeout: float | None = 60.0):
    """Wartet global auf eine benannte Taste und entprellt gehaltene Tasten."""
    codes = {code: name for name, code in VK_CODES.items() if name in names}
    if not codes:
        return None
    end = None if timeout is None else time.time() + max(0.0, timeout)
    while any(user32.GetAsyncKeyState(code) & 0x8000 for code in codes):
        if end is not None and time.time() >= end:
            return None
        time.sleep(0.02)
    previous = {code: bool(user32.GetAsyncKeyState(code) & 0x8000)
                for code in codes}
    while end is None or time.time() < end:
        for code, name in codes.items():
            state = user32.GetAsyncKeyState(code)
            was_down = previous[code]
            previous[code] = bool(state & 0x8000)
            if (previous[code] and not was_down) or bool(state & 0x0001):
                return name
        time.sleep(0.02)
    return None


def platform_name() -> str:
    return "Windows"


def environment_warnings() -> list[str]:
    return []


def _bitmap_to_image(mem_dc, bitmap, width: int, height: int):
    """Liest eine GDI-Bitmap als PIL-RGB-Bild aus."""
    try:
        from PIL import Image
    except ImportError:
        return None

    info = BITMAPINFOHEADER()
    info.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.biWidth = width
    info.biHeight = -height  # Negativ = Zeilen bereits von oben nach unten.
    info.biPlanes = 1
    info.biBitCount = 32
    info.biCompression = 0
    buffer = (ctypes.c_char * (width * height * 4))()
    copied = gdi32.GetDIBits(
        mem_dc, bitmap, 0, height, buffer, ctypes.byref(info), 0)
    if copied != height:
        return None
    return Image.frombytes("RGB", (width, height), bytes(buffer), "raw", "BGRX")


def _release_bitmap(hwnd, window_dc, mem_dc, bitmap, old_bitmap) -> None:
    """Gibt einen vollständigen GDI-Aufnahmekontext bestmöglich frei."""
    for cleanup in (
        lambda: gdi32.SelectObject(mem_dc, old_bitmap)
        if old_bitmap and mem_dc else None,
        lambda: gdi32.DeleteObject(bitmap) if bitmap else None,
        lambda: gdi32.DeleteDC(mem_dc) if mem_dc else None,
        lambda: user32.ReleaseDC(hwnd, window_dc) if window_dc else None,
    ):
        try:
            cleanup()
        except (OSError, AttributeError):
            pass


def _capture_screen_bitblt(region=None):
    """Schneller GDI-Pfad; ``None`` signalisiert den ImageGrab-Fallback."""
    if region is None:
        rect = get_virtual_desktop()
        if rect is None:
            return None
        left, top, right, bottom = rect
    else:
        try:
            left, top, right, bottom = (int(value) for value in region)
        except (TypeError, ValueError):
            return None
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return None

    hwnd = window_dc = mem_dc = bitmap = old_bitmap = None
    try:
        hwnd = user32.GetDesktopWindow()
        window_dc = user32.GetWindowDC(hwnd)
        if not window_dc:
            return None
        mem_dc = gdi32.CreateCompatibleDC(window_dc)
        bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
        if not mem_dc or not bitmap:
            return None
        old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
        if not gdi32.BitBlt(
                mem_dc, 0, 0, width, height, window_dc, left, top, SRCCOPY):
            logger.warning("BitBlt fehlgeschlagen; verwende ImageGrab-Fallback")
            return None
        image = _bitmap_to_image(mem_dc, bitmap, width, height)
        if image is None:
            logger.warning("GetDIBits fehlgeschlagen; verwende ImageGrab-Fallback")
        return image
    except (OSError, ValueError, AttributeError) as fehler:
        logger.warning("BitBlt-Screenshot fehlgeschlagen: %s", fehler)
        return None
    finally:
        _release_bitmap(hwnd, window_dc, mem_dc, bitmap, old_bitmap)


def capture_screen(region=None):
    """Screenshot des virtuellen Desktops mit GDI und Pillow-Fallback."""
    image = _capture_screen_bitblt(region)
    if image is not None:
        return image

    try:
        from PIL import ImageGrab
        full_image = ImageGrab.grab(all_screens=True)
        if region is None:
            return full_image
        left, top, right, bottom = (int(value) for value in region)
        origin_x, origin_y = get_virtual_origin()
        crop = (
            left - origin_x, top - origin_y,
            right - origin_x, bottom - origin_y,
        )
        if crop[2] <= crop[0] or crop[3] <= crop[1]:
            return None
        return full_image.crop(crop)
    except (ImportError, OSError, TypeError, ValueError) as fehler:
        logger.error("Windows-Screenshot fehlgeschlagen: %s", fehler)
        return None


def capture_window(hwnd: int):
    """Bildet den Client-Bereich eines Fensters unabhängig von Überdeckung ab."""
    if not hwnd:
        return None

    window_dc = mem_dc = bitmap = old_bitmap = None
    try:
        window_rect = wintypes.RECT()
        client_rect = wintypes.RECT()
        client_origin = wintypes.POINT(0, 0)
        if not user32.GetWindowRect(hwnd, ctypes.byref(window_rect)):
            return None
        if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
            return None
        if not user32.ClientToScreen(hwnd, ctypes.byref(client_origin)):
            return None

        width = window_rect.right - window_rect.left
        height = window_rect.bottom - window_rect.top
        client_width = client_rect.right - client_rect.left
        client_height = client_rect.bottom - client_rect.top
        if min(width, height, client_width, client_height) <= 0:
            return None

        window_dc = user32.GetWindowDC(hwnd)
        if not window_dc:
            return None
        mem_dc = gdi32.CreateCompatibleDC(window_dc)
        bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
        if not mem_dc or not bitmap:
            return None
        old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
        if not user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT):
            logger.warning("PrintWindow fehlgeschlagen")
            return None
        image = _bitmap_to_image(mem_dc, bitmap, width, height)
        if image is None:
            logger.warning("GetDIBits für Fensteraufnahme fehlgeschlagen")
            return None

        offset_x = client_origin.x - window_rect.left
        offset_y = client_origin.y - window_rect.top
        image = image.crop((
            offset_x, offset_y,
            offset_x + client_width, offset_y + client_height,
        ))
        screen_rect = (
            client_origin.x, client_origin.y,
            client_origin.x + client_width, client_origin.y + client_height,
        )
        return image, screen_rect
    except (OSError, TypeError, ValueError, AttributeError) as fehler:
        logger.error("Fenster-Screenshot fehlgeschlagen: %s", fehler)
        return None
    finally:
        _release_bitmap(hwnd, window_dc, mem_dc, bitmap, old_bitmap)


def flush_hotkey_messages() -> None:
    """Verwirft alle aufgestauten WM_HOTKEY-Messages.

    Während ein blockierender Editor läuft, sammeln sich WM_HOTKEY-Messages in
    der Queue des Main-Threads an und feuern danach als Burst. Nach Rückkehr
    aus einem Handler aufrufen, um diese veralteten Hotkey-Events zu verwerfen.
    """
    msg = wintypes.MSG()
    while user32.PeekMessageW(ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY, PM_REMOVE):
        pass


def unregister_hotkeys() -> None:
    """Deregistriert alle globalen Hotkeys."""
    for hotkey_id, _, _, _ in _HOTKEY_DEFINITIONS:
        user32.UnregisterHotKey(None, hotkey_id)


# Wie das Symbol AUSSIEHT, steht in der SVG-Datei der Weboberfläche —
# `symbol.py` rastert sie hier nur in die Form, die Windows haben will. Auch
# `tools/symbol.py` macht daraus PNG-/ICO-Dateien für eine Verknüpfung; es gibt
# deshalb keine zweite Beschreibung des Motivs, die auseinanderlaufen könnte.
def setze_app_id(app_id: str = APP_ID) -> bool:
    """Gibt dem Prozess eine eigene Kennung für die Taskleiste. True = gesetzt.

    Die Taskleiste nimmt **nicht** das Symbol aus `WM_SETICON`, solange sie das
    Fenster unter der ausführenden Datei einsortiert — und die heisst hier
    `python.exe`. Titelleiste und ALT+TAB zeigten das eigene Symbol deshalb
    längst, die Taskleiste weiter die Schlange. Erst eine eigene AppUserModelID
    löst das Fenster aus dieser Gruppe, und dann gilt dort das Fenstersymbol.

    **Muss laufen, bevor das erste Fenster entsteht.** Danach hat Windows die
    Zuordnung schon getroffen; ein späterer Aufruf ändert sie für dieses Fenster
    nicht mehr.
    """
    try:
        return ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            ctypes.c_wchar_p(app_id)) == 0
    except (AttributeError, OSError):
        return False


def _symbol_bits(kante: int = 32) -> bytes:
    """Das Symbol als ICO-Bilddaten: BITMAPINFOHEADER + BGRA + AND-Maske.

    Warum der Umweg über ein DIB und nicht `CreateIcon()` mit rohen Farbbits:
    das erzeugt eine **geräteabhängige** Bitmap, und die 24-Bit-Bytes werden auf
    einem 32-Bit-Bildschirm anders gelesen, als sie gemeint sind. Das Symbol kam
    dann zwar am Fenster an (beide `WM_GETICON` lieferten dasselbe Handle), war
    aber ein schwarzes Quadrat — schlimmer als das Python-Symbol, denn es sieht
    aus wie ein Fehler statt wie ein fremdes Programm. Ein DIB legt Breite,
    Höhe, Bittiefe und Byte-Reihenfolge selbst fest und hängt an keinem Gerät.

    Gerastert wird in `symbol.py`; hier wird nur umgepackt. Zwei Eigenheiten
    des Formats: die Höhe im Kopf zählt **doppelt** (Farb- und Maskenbild
    untereinander), und DIB-Zeilen stehen **von unten nach oben**.
    """
    kopf = struct.pack("<IiiHHIIiiII", 40, kante, kante * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    farben = bytearray()
    # DIB-Zeilen stehen von UNTEN nach oben, `punkte()` liefert von oben —
    # deshalb umgedreht. Ohne das steht auch das neue Logo auf dem Kopf.
    for zeile in reversed(list(symbol.punkte(kante))):
        for r, g, b, a in zeile:
            farben += bytes((b, g, r, a))       # BGRA, nicht RGBA
    # Die AND-Maske wertet Windows bei 32 Bit nicht mehr aus (das tut der
    # Alpha-Kanal), sie muss aber dastehen: 1 Bit je Pixel, Zeilen auf 4 Byte
    # aufgefüllt.
    return kopf + bytes(farben) + bytes(((kante + 31) // 32 * 4) * kante)


def setze_fenster_symbol(titel_substring: str, warten: float = 0.0) -> bool:
    """Gibt dem Fenster mit passendem Titel das Studio-Symbol. True = gesetzt.

    Ohne das trägt das Fenster das Symbol von `python.exe` — pywebview kann es
    auf Windows nicht selbst setzen (der `icon`-Parameter gilt dort nicht, weil
    das Symbol sonst aus der ausführenden Datei kommt). Ein Fenster in der
    Taskleiste, das aussieht wie ein Python-Prozess, findet man zwischen anderen
    Python-Prozessen nicht wieder.

    **`warten` ist der Grund, warum das Symbol bisher nie ankam.**
    `webview.start(func)` ruft `func` auf, sobald die Schleife läuft — das
    Fenster steht da noch nicht. Gemessen: zum Zeitpunkt des Aufrufs findet
    `EnumWindows` gar kein passendes Fenster, zwei Sekunden später schon, und
    dann greift das Setzen auch. Vorher fiel der Aufruf still auf `False`, und
    das Fenster behielt das Symbol von `python.exe`. Wer aus einem
    GUI-Startcallback aufruft, gibt deshalb eine Frist mit; ohne Angabe wird
    einmal geschaut wie bisher.

    Fehler werden geschluckt: ein fehlendes Symbol ist kein Grund, ein Fenster
    nicht zu öffnen.
    """
    frist = time.monotonic() + max(0.0, warten)
    hwnd = _find_window_by_title(titel_substring)
    while not hwnd and time.monotonic() < frist:
        time.sleep(0.1)
        hwnd = _find_window_by_title(titel_substring)
    if not hwnd:
        return False
    try:
        # Signaturen setzen, sonst behandelt ctypes das zurueckgegebene HICON als
        # int und schneidet es auf 32 Bit ab — auf einem 64-Bit-Windows kommt
        # dann ein kaputtes Handle bei SendMessage an, und das Symbol bleibt das
        # von python.exe. Genau daran ist der erste Versuch gescheitert.
        user32.CreateIconFromResourceEx.restype = ctypes.c_void_p
        user32.CreateIconFromResourceEx.argtypes = [
            ctypes.c_char_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32,
            ctypes.c_int, ctypes.c_int, ctypes.c_uint32]
        user32.SendMessageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                        ctypes.c_void_p, ctypes.c_void_p]
        # Jede Grösse wird in ihrer Grösse gezeichnet, nicht eine hochgerechnet:
        # 0 = klein (Titelleiste, 16 px), 1 = gross (ALT+TAB und Taskleiste, die
        # daraus ihre 24 px skaliert). Ein gedehntes 16er sah dort matschig aus.
        for art, kante in ((0, 16), (1, 32)):
            bits = _symbol_bits(kante)
            # 0x00030000 = Version 3 des Symbol-Formats, die einzige, die es gibt.
            symbol = user32.CreateIconFromResourceEx(bits, len(bits), 1, 0x00030000,
                                                     kante, kante, 0)
            if not symbol:
                return False
            user32.SendMessageW(hwnd, WM_SETICON, art, symbol)
        return True
    except (OSError, ValueError, AttributeError):
        return False
