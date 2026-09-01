"""Linux-X11-Backend für Eingabe, Hotkeys, Fenster und Bildschirmzugriff.

Alle Fremdpakete werden verzögert importiert. Dadurch bleiben Konfiguration,
Migrationen und Tests auch auf einem Server ohne grafische Sitzung nutzbar.
Wayland wird bewusst nicht als X11 ausgegeben: globale Eingabe ist dort eine
Compositor-/Portal-Frage und darf nicht scheinbar funktionieren.
"""

from importlib.util import find_spec
import logging
import os
import queue
import threading
import time

from .common import (
    APP_ID, HOTKEY_BINDINGS, KEY_NAMES, PlatformError, WHEEL_STEP,
)
from ..config import CONFIG
from ..utils import err, warn

logger = logging.getLogger("autoclicker")

_hotkey_queue: queue.Queue[int] = queue.Queue()
_hotkey_listener = None
_mouse_listener = None
_keyboard_listener = None


def _session_type() -> str:
    session = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if session:
        return session
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def _x11_ready() -> bool:
    return _session_type() != "wayland" and bool(os.environ.get("DISPLAY"))


def platform_name() -> str:
    return "Linux/X11" if _x11_ready() else "Linux"


def environment_warnings() -> list[str]:
    meldungen = []
    if _session_type() == "wayland":
        meldungen.append(
            "Wayland erkannt: globale Hotkeys, Eingabesimulation und "
            "Fensteraufnahme benötigen eine X11-Sitzung.")
    elif not os.environ.get("DISPLAY"):
        meldungen.append("Keine X11-Sitzung gefunden: DISPLAY ist nicht gesetzt.")
    for modul, paket in (
            ("pynput", "pynput"), ("Xlib", "python-xlib"), ("mss", "mss")):
        if find_spec(modul) is None:
            meldungen.append(f"Linux-Abhängigkeit fehlt: pip install {paket}")
    return meldungen


def _pynput():
    if not _x11_ready():
        raise RuntimeError("Linux-Eingabe benötigt eine X11-Sitzung")
    from pynput import keyboard, mouse
    return keyboard, mouse


def _mss_desktop():
    if not _x11_ready():
        raise RuntimeError("Bildschirmaufnahme benötigt eine X11-Sitzung")
    from mss import mss
    from mss.exception import ScreenShotError
    try:
        return mss()
    except ScreenShotError as fehler:
        raise RuntimeError(f"X11-Bildschirmaufnahme nicht verfügbar: {fehler}") from fehler


def get_virtual_desktop() -> tuple[int, int, int, int] | None:
    try:
        with _mss_desktop() as bildschirm:
            monitor = bildschirm.monitors[0]
            return (
                int(monitor["left"]), int(monitor["top"]),
                int(monitor["left"] + monitor["width"]),
                int(monitor["top"] + monitor["height"]),
            )
    except (ImportError, OSError, RuntimeError):
        return None


def get_screen_size() -> tuple[int, int] | None:
    try:
        with _mss_desktop() as bildschirm:
            monitor = bildschirm.monitors[1]
            return int(monitor["width"]), int(monitor["height"])
    except (ImportError, OSError, RuntimeError, IndexError):
        return None


def get_virtual_origin() -> tuple[int, int]:
    rechteck = get_virtual_desktop()
    return (rechteck[0], rechteck[1]) if rechteck else (0, 0)


def get_screen_center() -> tuple[int, int]:
    rechteck = get_virtual_desktop()
    if rechteck:
        return ((rechteck[0] + rechteck[2]) // 2,
                (rechteck[1] + rechteck[3]) // 2)
    groesse = get_screen_size()
    return (groesse[0] // 2, groesse[1] // 2) if groesse else (960, 540)


def capture_screen(region=None):
    """Screenshot über MSS; Ergebnis ist ein PIL-RGB-Bild."""
    try:
        from PIL import Image
        with _mss_desktop() as bildschirm:
            if region:
                links, oben, rechts, unten = (int(v) for v in region)
                if rechts <= links or unten <= oben:
                    return None
                monitor = {
                    "left": links, "top": oben,
                    "width": rechts - links, "height": unten - oben,
                }
            else:
                monitor = bildschirm.monitors[0]
            roh = bildschirm.grab(monitor)
            return Image.frombytes("RGB", roh.size, roh.rgb)
    except (ImportError, OSError, RuntimeError, ValueError) as fehler:
        logger.error("Linux-Screenshot fehlgeschlagen: %s", fehler)
        return None


def capture_window(_handle: int):
    """Direkte Fensteraufnahme ist im X11-Backend noch nicht verfügbar."""
    return None


def get_screen_pixel(x: int, y: int) -> tuple[int, int, int] | None:
    bild = capture_screen((int(x), int(y), int(x) + 1, int(y) + 1))
    return tuple(bild.getpixel((0, 0))[:3]) if bild is not None else None


def get_cursor_pos() -> tuple[int, int]:
    try:
        _, mouse = _pynput()
        x, y = mouse.Controller().position
        return int(x), int(y)
    except (ImportError, OSError, RuntimeError) as fehler:
        raise PlatformError(f"Linux konnte die Mausposition nicht lesen: {fehler}") from fehler


def set_cursor_pos(x: int, y: int) -> bool:
    try:
        _, mouse = _pynput()
        mouse.Controller().position = (int(x), int(y))
        return True
    except (ImportError, OSError, RuntimeError):
        return False


def send_click(x: int, y: int, move_delay: float = 0.01,
               post_delay: float = 0.05) -> bool:
    try:
        _, mouse = _pynput()
        controller = mouse.Controller()
        controller.position = (int(x), int(y))
        time.sleep(max(0.0, move_delay))
        controller.click(mouse.Button.left)
        time.sleep(max(0.0, post_delay))
        return True
    except (ImportError, OSError, RuntimeError) as fehler:
        logger.error("Linux-Klick fehlgeschlagen: %s", fehler)
        return False


def send_scroll(clicks: int, x: int = None, y: int = None,
                move_delay: float = 0.01, post_delay: float = 0.05) -> bool:
    if not clicks:
        return True
    try:
        _, mouse = _pynput()
        controller = mouse.Controller()
        if x is not None and y is not None:
            controller.position = (int(x), int(y))
            time.sleep(max(0.0, move_delay))
        controller.scroll(0, int(clicks))
        time.sleep(max(0.0, post_delay))
        return True
    except (ImportError, OSError, RuntimeError) as fehler:
        logger.error("Linux-Scrollen fehlgeschlagen: %s", fehler)
        return False


def _keyboard_key(keyboard, name: str):
    sondertasten = {
        "enter": keyboard.Key.enter, "return": keyboard.Key.enter,
        "tab": keyboard.Key.tab, "space": keyboard.Key.space,
        "leertaste": keyboard.Key.space, "escape": keyboard.Key.esc,
        "esc": keyboard.Key.esc, "backspace": keyboard.Key.backspace,
        "delete": keyboard.Key.delete, "del": keyboard.Key.delete,
        "left": keyboard.Key.left, "right": keyboard.Key.right,
        "up": keyboard.Key.up, "down": keyboard.Key.down,
    }
    for nummer in range(1, 13):
        sondertasten[f"f{nummer}"] = getattr(keyboard.Key, f"f{nummer}")
    return sondertasten.get(name, name if len(name) == 1 else None)


def send_key(key_name: str) -> bool:
    name = str(key_name).strip().lower()
    try:
        keyboard, _ = _pynput()
        taste = _keyboard_key(keyboard, name)
        if taste is None:
            print(err(f"Unbekannte Taste: '{key_name}'"))
            return False
        controller = keyboard.Controller()
        controller.press(taste)
        controller.release(taste)
        return True
    except (ImportError, OSError, RuntimeError) as fehler:
        logger.error("Linux-Tastendruck fehlgeschlagen: %s", fehler)
        return False


def install_mouse_hook(on_lbutton_down, on_wheel=None) -> bool:
    global _mouse_listener
    if _mouse_listener is not None:
        return True
    try:
        _, mouse = _pynput()

        def on_click(x, y, button, pressed):
            if pressed and button == mouse.Button.left:
                on_lbutton_down(int(x), int(y), get_screen_pixel(int(x), int(y)))

        def on_scroll(x, y, _dx, dy):
            if on_wheel is not None:
                on_wheel(int(x), int(y), int(dy) * WHEEL_STEP)

        _mouse_listener = mouse.Listener(on_click=on_click, on_scroll=on_scroll)
        _mouse_listener.start()
        return True
    except (ImportError, OSError, RuntimeError) as fehler:
        logger.error("Linux-Maushook fehlgeschlagen: %s", fehler)
        _mouse_listener = None
        return False


def remove_mouse_hook() -> None:
    global _mouse_listener
    if _mouse_listener is not None:
        _mouse_listener.stop()
        _mouse_listener = None


def _key_name(keyboard, taste) -> str | None:
    char = getattr(taste, "char", None)
    if isinstance(char, str) and len(char) == 1:
        return char.lower()
    mapping = {
        keyboard.Key.enter: "enter", keyboard.Key.tab: "tab",
        keyboard.Key.space: "space", keyboard.Key.esc: "escape",
        keyboard.Key.backspace: "backspace", keyboard.Key.delete: "delete",
        keyboard.Key.left: "left", keyboard.Key.right: "right",
        keyboard.Key.up: "up", keyboard.Key.down: "down",
    }
    for nummer in range(1, 13):
        mapping[getattr(keyboard.Key, f"f{nummer}")] = f"f{nummer}"
    return mapping.get(taste)


def install_keyboard_hook(on_key_down) -> bool:
    global _keyboard_listener
    if _keyboard_listener is not None:
        return True
    try:
        keyboard, _ = _pynput()
        modifier = set()
        steuerung = {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
        alt = {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
               keyboard.Key.alt_gr}

        def on_press(taste):
            if taste in steuerung or taste in alt:
                modifier.add(taste)
                return
            name = _key_name(keyboard, taste)
            if name in KEY_NAMES and not modifier:
                on_key_down(name)

        def on_release(taste):
            modifier.discard(taste)

        _keyboard_listener = keyboard.Listener(
            on_press=on_press, on_release=on_release)
        _keyboard_listener.start()
        return True
    except (ImportError, OSError, RuntimeError) as fehler:
        logger.error("Linux-Tastaturhook fehlgeschlagen: %s", fehler)
        _keyboard_listener = None
        return False


def remove_keyboard_hook() -> None:
    global _keyboard_listener
    if _keyboard_listener is not None:
        _keyboard_listener.stop()
        _keyboard_listener = None


def _x_display():
    if not _x11_ready():
        raise RuntimeError("Fensterzugriff benötigt X11")
    from Xlib import display
    return display.Display()


def _window_title(display, window) -> str:
    from Xlib import error as xerror
    try:
        atom = display.intern_atom("_NET_WM_NAME")
        prop = window.get_full_property(atom, display.intern_atom("UTF8_STRING"))
        if prop and prop.value:
            value = prop.value
            return (value.decode("utf-8", "replace")
                    if isinstance(value, bytes) else str(value)).strip()
    except (AttributeError, UnicodeError, xerror.XError):
        pass
    try:
        return str(window.get_wm_name() or "").strip()
    except (AttributeError, TypeError, xerror.XError):
        return ""


def _window_rect(window, root) -> tuple[int, int, int, int] | None:
    from Xlib import error as xerror
    try:
        geom = window.get_geometry()
        pos = window.translate_coords(root, 0, 0)
        x = int(getattr(pos, "dst_x", getattr(pos, "x", 0)))
        y = int(getattr(pos, "dst_y", getattr(pos, "y", 0)))
        width, height = int(geom.width), int(geom.height)
        return (x, y, x + width, y + height) if width > 0 and height > 0 else None
    except (AttributeError, TypeError, ValueError, xerror.XError):
        return None


def _client_ids(display, root) -> list[int]:
    from Xlib import X
    for name in ("_NET_CLIENT_LIST_STACKING", "_NET_CLIENT_LIST"):
        prop = root.get_full_property(
            display.intern_atom(name), X.AnyPropertyType)
        if prop is not None and prop.value is not None:
            return [int(value) for value in prop.value]
    return []


def liste_fenster() -> list:
    try:
        from Xlib import X, error as xerror
    except ImportError:
        return []
    display = None
    try:
        display = _x_display()
        root = display.screen().root
        gefunden = []
        for xid in _client_ids(display, root):
            try:
                window = display.create_resource_object("window", xid)
                if window.get_attributes().map_state != X.IsViewable:
                    continue
                titel = _window_title(display, window)
                rect = _window_rect(window, root)
                if titel and rect and rect[2] - rect[0] >= 80 and rect[3] - rect[1] >= 80:
                    gefunden.append((titel, rect, xid))
            except (AttributeError, TypeError, xerror.XError):
                continue
        return sorted(gefunden, key=lambda eintrag: (eintrag[1][1], eintrag[1][0]))
    except (OSError, RuntimeError, xerror.DisplayError, xerror.XError):
        return []
    finally:
        if display is not None:
            display.close()


def get_client_rect_by_handle(handle: int):
    try:
        from Xlib import error as xerror
    except ImportError:
        return None
    display = None
    try:
        display = _x_display()
        root = display.screen().root
        window = display.create_resource_object("window", int(handle))
        rect = _window_rect(window, root)
        return rect
    except (OSError, RuntimeError, TypeError, ValueError,
            xerror.DisplayError, xerror.XError):
        return None
    finally:
        if display is not None:
            display.close()


def resolve_window(title: str, instance: int = 0, reference_rect=None):
    if not isinstance(title, str) or not title.strip():
        return None
    ziel = title.strip().casefold()
    fenster = liste_fenster()
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
                abs(e[1][i] - ref[i]) for i in range(4)))
        except (TypeError, ValueError):
            pass
    return kandidaten[0]


def get_client_rect_by_title(title_substring: str):
    ziel = str(title_substring or "").casefold()
    eintrag = next((e for e in liste_fenster() if ziel in e[0].casefold()), None)
    return eintrag[1] if eintrag else None


def get_foreground_window_title() -> str:
    try:
        from Xlib import X, error as xerror
    except ImportError:
        return ""
    display = None
    try:
        display = _x_display()
        root = display.screen().root
        prop = root.get_full_property(
            display.intern_atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
        if not prop or not len(prop.value):
            return ""
        window = display.create_resource_object("window", int(prop.value[0]))
        return _window_title(display, window)
    except (OSError, RuntimeError, TypeError,
            xerror.DisplayError, xerror.XError):
        return ""
    finally:
        if display is not None:
            display.close()


def is_target_window_active(title_substring: str) -> bool:
    if not title_substring:
        return True
    return str(title_substring).casefold() in get_foreground_window_title().casefold()


def get_window_title_at(x: int, y: int) -> str:
    """Titel des Fensters UNTER dieser Stelle — "" wenn keins.

    Der geometrische Gegenpart zum Vordergrund-Titel: ein Klick, der ein
    Fenster erst aktiviert, wird sonst gegen das VORIGE Fenster geprüft (siehe
    die ausführliche Begründung im Windows-Backend).

    `liste_fenster()` liefert die sichtbaren Fenster mit ihrem Client-Rechteck,
    sortiert nach Lage. Eine Stapelreihenfolge kennt X11 hier nicht — bei
    Überlappung gewinnt deshalb das KLEINSTE treffende Fenster: ein Dialog über
    einem grossen Spielfenster ist fast immer der obenliegende.
    """
    treffer = []
    for eintrag in liste_fenster():
        try:
            titel, rect = eintrag[0], eintrag[1]
            links, oben, rechts, unten = rect
        except (TypeError, ValueError, IndexError):
            continue
        if links <= x < rechts and oben <= y < unten:
            treffer.append(((rechts - links) * (unten - oben), titel))
    if not treffer:
        return ""
    return min(treffer)[1]


def check_failsafe(state=None) -> bool:
    cfg = state.config if state else CONFIG
    if not cfg.failsafe_enabled:
        return False
    try:
        x, y = get_cursor_pos()
    except PlatformError:
        # Ohne bekannte Mausposition ist Weiterklicken nicht sicher.
        return True
    return x <= cfg.failsafe_x and y <= cfg.failsafe_y


def register_hotkeys() -> bool:
    global _hotkey_listener
    if _hotkey_listener is not None:
        return True
    if not _x11_ready():
        return False
    try:
        keyboard, _ = _pynput()
        callbacks = {
            kombination: (lambda hotkey_id=hotkey_id:
                          _hotkey_queue.put(hotkey_id))
            for hotkey_id, kombination in HOTKEY_BINDINGS.items()
        }
        _hotkey_listener = keyboard.GlobalHotKeys(callbacks)
        _hotkey_listener.start()
        return True
    except (ImportError, OSError, RuntimeError) as fehler:
        print(warn(f"Linux-Hotkeys konnten nicht registriert werden: {fehler}"))
        _hotkey_listener = None
        return False


def poll_hotkey() -> int | None:
    try:
        return _hotkey_queue.get_nowait()
    except queue.Empty:
        return None


def flush_hotkey_messages() -> None:
    while poll_hotkey() is not None:
        pass


def unregister_hotkeys() -> None:
    global _hotkey_listener
    if _hotkey_listener is not None:
        _hotkey_listener.stop()
        _hotkey_listener = None
    flush_hotkey_messages()


def get_current_thread_id() -> int:
    return threading.get_ident()


def post_quit(_thread_id: int) -> None:
    """Linux hat keine Windows-Nachrichtenqueue; das Event beendet die Schleife."""


def wait_for_key(names: tuple[str, ...], timeout: float | None = 60.0):
    """Wartet über einen kurzlebigen X11-Listener auf eine erlaubte Taste."""
    try:
        keyboard, _ = _pynput()
    except (ImportError, OSError, RuntimeError):
        return None
    result = {"name": None}
    finished = threading.Event()

    def on_press(key):
        name = _key_name(keyboard, key)
        if name in names:
            result["name"] = name
            finished.set()
            return False
        return None

    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    finished.wait(timeout=None if timeout is None else max(0.0, timeout))
    listener.stop()
    return result["name"]


def setze_app_id(_app_id: str = APP_ID) -> bool:
    return False


def setze_fenster_symbol(_titel_substring: str, warten: float = 0.0) -> bool:
    if warten > 0:
        time.sleep(min(float(warten), 0.05))
    return False
