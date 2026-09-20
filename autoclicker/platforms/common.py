"""Betriebssystemunabhängige Tasten- und Hotkey-Definitionen."""

APP_ID = "Autoclicker.SequenzStudio"


class PlatformError(RuntimeError):
    """Eine angeforderte Systemaktion konnte nicht ausgeführt werden."""

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
HOTKEY_SKIP_STEP = 28

KEY_NAMES = frozenset({
    "enter", "return", "tab", "space", "leertaste", "escape", "esc",
    "backspace", "delete", "del", "left", "up", "right", "down",
    *(f"f{i}" for i in range(1, 13)),
    *(str(i) for i in range(10)),
    *(chr(97 + i) for i in range(26)),
})

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
    # CTRL+ALT+SHIFT ist die Ebene, die nur waehrend eines laufenden Vorgangs
    # wirkt: die Aufnahme-Marker waehrend einer Aufnahme, das Ueberspringen
    # eines Blocks waehrend eines Laufs. mark_color() und mark_screenshot()
    # pruefen als Erstes _recording_running() und lagen trotzdem auf der
    # Basis-Ebene - eine halbe Ebene fuer eine ganze Sache. Damit werden dort
    # M und D frei; die Basis hatte nur noch R und Y. Der Buchstabe darf
    # derselbe bleiben wie in der Basis, solange die Bedeutung verwandt ist:
    # K ueberspringt die Wartezeit, SHIFT+K den ganzen Block.
    HOTKEY_RECORD_COLOR: "<ctrl>+<alt>+<shift>+m",
    HOTKEY_RECORD_SCREENSHOT: "<ctrl>+<alt>+<shift>+d",
    HOTKEY_REC_PHASE: "<ctrl>+<alt>+<shift>+p",
    HOTKEY_REC_REGION: "<ctrl>+<alt>+<shift>+r",
    HOTKEY_REC_WATCH: "<ctrl>+<alt>+<shift>+b",
    HOTKEY_SKIP_STEP: "<ctrl>+<alt>+<shift>+k",
}
