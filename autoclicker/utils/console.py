"""
Konsolen-Output: ANSI-Farben, Status-Tags, Konsolen-Erkennung.

Hier liegt auch die Detection-Logik für Windows-Console vs. PyCharm/IDE —
sie wird beim Import einmalig ausgeführt und setzt die Modul-Konstanten
_REAL_CONSOLE, _ANSI_ENABLED, _PYCHARM und _COLORS_ENABLED.
"""

import ctypes
import colorsys
import os

# =============================================================================
# ANSI-FARBCODES
# =============================================================================

# Optimistisch starten - wird nach _detect_ansi_support()/_is_pycharm() korrekt gesetzt
_COLORS_ENABLED = True

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


# =============================================================================
# STATUS-TAGS
# =============================================================================

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


def _color_name(r: int, g: int, b: int) -> str:
    """Heuristischer deutscher Farbname für einen RGB-Wert (Hue-basiert)."""
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 30:  # Grauachse: kaum Sättigung
        if mx < 50:
            return "Schwarz"
        if mx < 120:
            return "Dunkelgrau"
        if mx < 200:
            return "Grau"
        return "Weiß"
    hue = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[0] * 360
    dark = mx < 128
    if hue < 15 or hue >= 345:
        return "Dunkelrot" if dark else "Rot"
    if hue < 45:
        # Braun = dunkles Orange; Schwelle höher als die generelle Dark-Grenze,
        # damit klassische Brauntöne (z.B. 139,69,19) nicht als Orange landen.
        return "Braun" if mx < 170 else "Orange"
    if hue < 70:
        return "Oliv" if dark else "Gelb"
    if hue < 160:
        return "Dunkelgrün" if dark else "Grün"
    if hue < 200:
        return "Türkis"
    if hue < 255:
        return "Dunkelblau" if dark else "Blau"
    if hue < 290:
        return "Lila"
    return "Pink"


def describe_color(color) -> str:
    """Beschreibt eine RGB-Farbe menschenlesbar: farbiger Block + Name.

    Beispiel: '█ Rot (220,40,30)' — der Block ist via ANSI-Truecolor in der
    echten Farbe eingefärbt (Windows-Konsole mit VT-Processing und PyCharm
    können das). Ohne Farb-Support bleibt nur Name + Werte.
    """
    try:
        r, g, b = (int(v) for v in color)
    except (TypeError, ValueError):
        return str(color)
    name = _color_name(r, g, b)
    rgb = hint(f"({r},{g},{b})")
    if _COLORS_ENABLED:
        return f"\033[38;2;{r};{g};{b}m█{_C['reset']} {name} {rgb}"
    return f"{name} {rgb}"


def save_tag(msg: str) -> str:
    """Formatiert eine Speicher-Meldung: [SAVE] grün."""
    return f"{col('[SAVE]', 'green')} {msg}"


def load_tag(msg: str) -> str:
    """Formatiert eine Lade-Meldung: [LOAD] cyan."""
    return f"{col('[LOAD]', 'cyan')} {msg}"


def delete_tag(msg: str) -> str:
    """Formatiert eine Lösch-Meldung: [DELETE] gelb."""
    return f"{col('[DELETE]', 'yellow')} {msg}"


# =============================================================================
# LAYOUT-HELPER
# =============================================================================

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

    if x < screen_w * 0.33:
        h_pos = "links"
    elif x < screen_w * 0.66:
        h_pos = "mitte"
    else:
        h_pos = "rechts"

    if y < screen_h * 0.33:
        v_pos = "oben"
    elif y < screen_h * 0.66:
        v_pos = "mitte"
    else:
        v_pos = "unten"

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


def clear_line() -> None:
    """Löscht die aktuelle Konsolenzeile."""
    print("\r" + " " * 80 + "\r", end="", flush=True)


def set_console_title(text: str) -> None:
    """Setzt den Titel des Konsolenfensters (nur Windows, nur ASCII).

    Plattform-/Fehler-tolerant: windll wird NUR lazy im Funktionskörper
    angefasst (dieses Modul wird auch auf Linux importiert). Fehler werden
    stillschweigend verworfen — der Titel ist reines UX-Beiwerk.
    """
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(str(text))
    except (AttributeError, OSError):
        pass


# =============================================================================
# KONSOLEN-ERKENNUNG (beim Import einmalig ausgeführt)
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


# Beim Import einmalig prüfen
_REAL_CONSOLE = _is_real_console()
_ANSI_ENABLED = _detect_ansi_support()  # Voller ANSI (Farben + Cursor)
_PYCHARM = _is_pycharm()               # Nur ANSI-Farben, kein Cursor

# Farben final konfigurieren (nach _ANSI_ENABLED/_PYCHARM Check)
_COLORS_ENABLED = _ANSI_ENABLED or _PYCHARM

if not _REAL_CONSOLE:
    if _PYCHARM:
        print(info("PyCharm erkannt - Pfeiltasten-Navigation via GetAsyncKeyState aktiv"))
    else:
        print(info("IDE-Konsole erkannt - Fallback auf Nummern-Eingabe"))
