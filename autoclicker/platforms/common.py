"""Betriebssystemunabhängige Tasten- und Hotkey-Definitionen."""

APP_ID = "Autoclicker.SequenzStudio"

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
HOTKEY_IMPORT_EXPORT = 17
HOTKEY_RECORD_SEQ = 18
HOTKEY_RECORD_PAUSE = 19
HOTKEY_SEQUENCE_STUDIO = 20
HOTKEY_SCAN_STUDIO = 21
HOTKEY_HELP = 22
HOTKEY_RECORD_COLOR = 23
HOTKEY_RECORD_SCREENSHOT = 24
HOTKEY_REC_PHASE = 25
HOTKEY_REC_REGION = 26
HOTKEY_REC_WATCH = 27

WHEEL_DELTA = 120

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

# Eine Quelle für die globalen Kombinationen beider Backends.
HOTKEY_BINDINGS = {
    HOTKEY_RECORD: "<ctrl>+<alt>+a",
    HOTKEY_UNDO: "<ctrl>+<alt>+u",
    HOTKEY_CLEAR: "<ctrl>+<alt>+c",
    HOTKEY_RESET: "<ctrl>+<alt>+x",
    HOTKEY_EDITOR: "<ctrl>+<alt>+e",
    HOTKEY_ITEM_SCAN: "<ctrl>+<alt>+n",
    HOTKEY_LOAD: "<ctrl>+<alt>+l",
    HOTKEY_SHOW: "<ctrl>+<alt>+p",
    HOTKEY_TOGGLE: "<ctrl>+<alt>+s",
    HOTKEY_ANALYZE: "<ctrl>+<alt>+t",
    HOTKEY_QUIT: "<ctrl>+<alt>+q",
    HOTKEY_PAUSE: "<ctrl>+<alt>+g",
    HOTKEY_SKIP: "<ctrl>+<alt>+k",
    HOTKEY_SWITCH: "<ctrl>+<alt>+w",
    HOTKEY_SCHEDULE: "<ctrl>+<alt>+z",
    HOTKEY_FINISH: "<ctrl>+<alt>+f",
    HOTKEY_IMPORT_EXPORT: "<ctrl>+<alt>+i",
    HOTKEY_RECORD_SEQ: "<ctrl>+<alt>+j",
    HOTKEY_RECORD_PAUSE: "<ctrl>+<alt>+h",
    HOTKEY_SEQUENCE_STUDIO: "<ctrl>+<alt>+b",
    HOTKEY_SCAN_STUDIO: "<ctrl>+<alt>+v",
    HOTKEY_HELP: "<ctrl>+<alt>+o",
    HOTKEY_RECORD_COLOR: "<ctrl>+<alt>+m",
    HOTKEY_RECORD_SCREENSHOT: "<ctrl>+<alt>+d",
    HOTKEY_REC_PHASE: "<ctrl>+<alt>+<shift>+p",
    HOTKEY_REC_REGION: "<ctrl>+<alt>+<shift>+d",
    HOTKEY_REC_WATCH: "<ctrl>+<alt>+<shift>+m",
}
