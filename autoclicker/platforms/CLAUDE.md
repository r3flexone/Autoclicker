# Plattform-Schicht

Details zur `CLAUDE.md` im Wurzelordner — dort stehen Befehle, Architektur
und die Regeln, die überall gelten. Claude Code lädt diese Datei, sobald eine
Datei aus `autoclicker/platforms/` gelesen wird. Was hier steht, gilt genauso; neue
Begründungen zu diesem Bereich gehören hierher, nicht in die Wurzel.

## Plattform-Schicht (Windows und Linux/X11)

**Das Betriebssystem steht in einem Backend, nicht im Rest des Baums.**
`platforms/load_backend()` wählt es einmal anhand von `sys.platform`; alles andere
importiert weiterhin `autoclicker.winapi` und merkt nichts davon. Ein nicht
unterstütztes System (Wayland, macOS) fliegt dort mit `RuntimeError` auf, statt
sich später als stiller Fehlschlag zu zeigen.

| Modul | was |
|---|---|
| `winapi.py` | **stabile Fassade** — reicht den Vertrag an das Backend durch, dazu vier Helfer, die nur aus Systemaufrufen abgeleitet sind (`resolve_window`, `get_virtual_origin`, `get_screen_center`, `check_failsafe`). Kein Systemcode. |
| `platforms/base.py` | der Vertrag (`PlatformBackend`-Protocol): Eingabe, Fenster, Hotkeys, Bildschirm — nur Systemaufrufe |
| `platforms/common.py` | betriebssystemneutral: Tastennamen, `HOTKEY_*`-IDs, `PlatformError`, `APP_ID`, `desktop_origin()` |
| `platforms/windows.py` | WinAPI-Backend (ctypes: Maus, Tastatur, Hotkeys, GDI, Hooks, Fenster-Symbol) |
| `platforms/linux_x11.py` | X11-Backend (`python-xlib`, `pynput`, `mss`) |
| `utils/io.py` | Tastendruck-Erfassung (`msvcrt` / `GetAsyncKeyState`) |
| `utils/console.py` | Konsolen-Erkennung, Fenstertitel, ANSI-Freischaltung |

Windows-spezifischer Code darf nur noch in **drei** Dateien stehen —
`platforms/windows.py`, `utils/io.py`, `utils/console.py`. Ein Test in
`tests/test_logic.py` (`PLATFORM_MODULES`) hält das fest: greift ein anderes Modul auf
`ctypes.windll`, `ctypes.WinDLL`, `wintypes` oder `msvcrt` zu, schlägt er fehl und nennt
die Datei. Er prüft **beide** Richtungen — kein Windows-Aufruf ausserhalb der Liste, und
kein Eintrag auf der Liste, der gar nichts Plattformspezifisches mehr enthält, sonst
wächst sie zur Fiktion.

**Wer einen Systemaufruf braucht, erweitert den Vertrag, nicht die Fassade.** Neue
Funktion in `base.py` eintragen, in *beiden* Backends implementieren, über `winapi`
exportieren. Nur eine Hälfte zu bauen ist der Fehler, den die Matrix in
`.github/workflows/tests.yml` fängt: die Suite läuft auf Ubuntu **und** Windows gegen
denselben Testvertrag (`test_platforms.py`).

Das gilt auch für `imaging.py`: es ist seit dem Umbau plattformneutral und holt sich
den Screenshot über das Backend, statt selbst BitBlt zu rufen.

**Der Vertrag besteht aus Systemaufrufen — was sich nur aus ihnen ergibt, steht
einmal in der Fassade.** `resolve_window`, `get_virtual_origin`, `get_screen_center`
und `check_failsafe` lagen früher gleichlautend in beiden Backends. Sie rufen die
Primitiven des Backends (`list_windows`, `get_virtual_desktop`, `get_screen_size`,
`get_cursor_pos`) über `_backend`; ein Test, der sie mit anderen Daten füttern will,
patcht deshalb `winapi._backend`, nicht die Fassade. Wer eine fünfte solche Funktion
schreibt, prüft zuerst, ob sie ein Systemaufruf ist.

**Es gibt keine Nachricht, die der Hauptthread abholt.** `poll_hotkey()` fragt
`PeekMessage` nur nach `WM_HOTKEY`, und die Hauptschleife endet über
`state.quit_event`. Ein `post_quit()`, das ein `WM_QUIT` in die Queue des
Hauptthreads stellte, las niemand — es ist samt `get_current_thread_id()` gelöscht.
Wer einen Thread aufwecken will, nimmt ein Event.

**Bildschirm-Geometrie gehört in `winapi.py`, nicht in den Aufrufer.** `GetSystemMetrics`
lag vorher fünfmal im Baum (`imaging`, `runtime/item_scan`, `diagnostics`, `scan_studio`,
`utils/console`), jedes Mal mit eigenen `SM_*`-Konstanten und eigenem `try/except`. Wer
die Fenstergrösse oder den virtuellen Desktop braucht, nimmt:

- `get_virtual_desktop()` → `(l, t, r, b)` über alle Monitore, oder `None`
- `get_virtual_origin()` → linke/obere Kante, `(0, 0)` als Rückfall
- `get_screen_size()` → Primärmonitor, oder `None`
- `get_screen_center()` → Mitte, mit Rückfallkette bis `(960, 540)`

`None` statt `(0, 0, 0, 0)` ist Absicht: eine Fläche von 0×0 würde jede Koordinate als
„ausserhalb aller Monitore" melden — genau der Fehler, den `diagnostics.py` sonst produziert
hätte.
