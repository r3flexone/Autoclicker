"""Tastatur-Eingabe in der echten Konsole (`utils/io.py`), mit gestellter Tastatur.

Geschrieben, BEVOR `safe_input` (18) und `_read_key_msvcrt` (12) zerlegt
wurden. Der Weg über `msvcrt` (echte Windows-Konsole) stand in keinem Test —
die Suite läuft in einer Pipe und nimmt immer den `stdin`-Weg. Gestellt ist
`msvcrt` als Folge von Tastendrücken; gemessen wird, was bei Enter herauskommt.
"""
import contextlib as _cl
import io as _io
import sys as _sys

from ._harness import check, section

import autoclicker.utils.io as _IO


class _Keys:
    """Ein `msvcrt`, das vorgegebene Tasten liefert."""

    def __init__(self, wide="", raw=()):
        self.wide, self.raw = list(wide), list(raw)

    def getwch(self):
        # Ist die Folge zu Ende, drückt die Tastatur Enter: eine Eingabe, die
        # weiterliest, wo sie hätte aufhören sollen, endet so mit einem falschen
        # Ergebnis statt mit einem IndexError aus dem Test selbst.
        return self.wide.pop(0) if self.wide else "\r"

    def getch(self):
        return self.raw.pop(0)


@_cl.contextmanager
def _console(keys):
    saved = (_IO._REAL_CONSOLE, _IO.msvcrt, _IO.flush_input_buffer)
    _IO._REAL_CONSOLE, _IO.msvcrt, _IO.flush_input_buffer = True, keys, (lambda: None)
    try:
        with _cl.redirect_stdout(_io.StringIO()):
            yield
    finally:
        _IO._REAL_CONSOLE, _IO.msvcrt, _IO.flush_input_buffer = saved


def _typed(wide):
    with _console(_Keys(wide)):
        try:
            return _IO.safe_input("> ")
        except (KeyboardInterrupt, EOFError) as e:
            return type(e).__name__


section("Konsolen-Eingabe: Zeile aus einzelnen Tasten")
check("Zeichen bis Enter", _typed("ab\r") == "ab")
check("\\n gilt wie Enter", _typed("ab\n") == "ab")
check("Rücktaste löscht das letzte Zeichen", _typed("ax\x08b\r") == "ab")
check("Rücktaste auf leerer Zeile tut nichts", _typed("\x08\x7fa\r") == "a")
check("ESC bricht mit \\x1b ab", _typed("ab\x1b") == "\x1b")
check("STRG+C wirft KeyboardInterrupt", _typed("a\x03") == "KeyboardInterrupt")
check("STRG+D und STRG+Z werfen EOFError",
      _typed("\x04") == "EOFError" and _typed("\x1a") == "EOFError")
check("Pfeiltasten (Präfix + zweites Zeichen) werden verworfen",
      _typed("a\xe0Hb\x00Kc\r") == "abc")
check("Steuerzeichen unter Leerzeichen werden ignoriert", _typed("\x01a\x02\r") == "a")
check("Umlaute gehen durch", _typed("ä ö\r") == "ä ö")


def _piped(text):
    saved = (_IO._REAL_CONSOLE, _IO.flush_input_buffer, _sys.stdin)
    _IO._REAL_CONSOLE, _IO.flush_input_buffer, _sys.stdin = False, (lambda: None), _io.StringIO(text)
    try:
        with _cl.redirect_stdout(_io.StringIO()):
            return _IO.safe_input("> ")
    finally:
        _IO._REAL_CONSOLE, _IO.flush_input_buffer, _sys.stdin = saved


check("Pipe: eine Zeile ohne Zeilenende", _piped("hallo\r\n") == "hallo")
check("Pipe: EOF ist leer", _piped("") == "")

section("Konsolen-Eingabe: einzelne Taste")


def _key(*raw):
    with _console(_Keys(raw=raw)):
        return _IO._read_key_msvcrt()


for _raw, _name in (((b"\xe0", b"H"), "up"), ((b"\xe0", b"P"), "down"),
                    ((b"\x00", b"K"), "left"), ((b"\xe0", b"M"), "right"),
                    ((b"\xe0", b"X"), "unknown"), ((b"\r",), "enter"),
                    ((b"\x1b",), "escape"), ((b"\x08",), "backspace"),
                    ((b"a",), "a"), ((b"\xff",), "unknown")):
    check(f"{_raw} → {_name}", _key(*_raw) == _name)
_saved_msvcrt = _IO.msvcrt
_IO.msvcrt = None
check("ohne msvcrt: unknown", _IO._read_key_msvcrt() == "unknown")
_IO.msvcrt = _saved_msvcrt
