"""Zeit-Eingaben (`utils/parsing.parse_time_input`), Form für Form.

Geschrieben, BEVOR die Funktion (Komplexität 24) zerlegt wurde — sie stand nur
mit zwei Fällen in der Suite. Sie trägt den Zeitplan (CTRL+ALT+T) und den
Countdown aus dem Studio; eine falsch gelesene Zeit startet eine Sequenz zur
falschen Stunde.
"""
from datetime import datetime, timedelta

from ._harness import check, section

from autoclicker.utils.parsing import parse_time_input as _pti

section("Zeit-Eingaben: Dauer, Uhrzeit, Fehler")

for _text, _expected in (("30s", (30.0, "30s")), ("30m", (1800.0, "30m")),
                         ("30min", (1800.0, "30m")), ("2h", (7200.0, "2h")),
                         ("2std", (7200.0, "2h")), ("1.5h", (5400.0, "1.5h")),
                         ("0.5m", (30.0, "0.5m")), ("2.5s", (2.5, "2.5s")),
                         ("+30", (1800.0, "30m")), ("+30m", (1800.0, "30m")),
                         ("+2h", (7200.0, "2h")), ("+45s", (45.0, "45s")),
                         ("  30S ", (30.0, "30s")), ("0s", (0.0, "0s"))):
    _sec, _desc, _ts = _pti(_text)
    check(f"'{_text}' ist eine Dauer", (_sec, _desc, _ts) == (*_expected, None))

for _text, _message in (("", "Keine Zeit angegeben"),
                        ("30", "Einheit fehlt! Nutze z.B. '30s', '30m' oder '30h'"),
                        ("xs", "Ungültige Zahl: xs"),
                        ("-5s", "Zeit muss positiv sein"),
                        ("25:00", "Ungültige Uhrzeit: 25:00"),
                        ("12:60", "Ungültige Uhrzeit: 12:60"),
                        ("ab:cd", "Ungültiges Zeitformat: ab:cd"),
                        ("2460", "Ungültige Uhrzeit: 2460 (gültig: 0000-2359)"),
                        ("0099", "Ungültige Uhrzeit: 0099 (gültig: 0000-2359)")):
    check(f"'{_text}' wird abgelehnt", _pti(_text) == (-1, _message, None))


def _clock(text, hour, minute):
    before = datetime.now()
    seconds, desc, stamp = _pti(text)
    target = before.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= before:
        target += timedelta(days=1)
    day = "heute" if target.date() == before.date() else "morgen"
    return (desc == f"{day} um {hour:02d}:{minute:02d}"
            and stamp == target.timestamp()
            and abs(seconds - (target - before).total_seconds()) < 2)


_soon = datetime.now() + timedelta(minutes=5)
_past = datetime.now() - timedelta(minutes=5)
check("HH:MM in der Zukunft: heute", _clock(_soon.strftime("%H:%M"), _soon.hour, _soon.minute)
      or _soon.date() != datetime.now().date())
check("HH:MM vorbei: morgen", _clock(_past.strftime("%H:%M"), _past.hour, _past.minute))
check("H:M ohne führende Null", _clock(f"{_past.hour}:{_past.minute}", _past.hour, _past.minute))
check("'7:' ohne Minuten wird abgelehnt", _pti("7:") == (-1, "Ungültiges Zeitformat: 7:", None))
check("HHMM vierstellig", _clock(_past.strftime("%H%M"), _past.hour, _past.minute))
check("eine Uhrzeit mit + ist trotzdem eine Uhrzeit",
      _clock("+" + _past.strftime("%H:%M"), _past.hour, _past.minute))

# 'infs' ist für float() eine Zahl — die Beschreibung (int(value)) stürzte
# daran mit OverflowError ab, mitten im Zeitplan-Dialog.
try:
    _inf = _pti("infs")
except OverflowError:
    _inf = "Absturz"
check("'infs' wird abgelehnt, statt abzustürzen", _inf == (-1, "Ungültige Zahl: infs", None))
check("'nans' ebenso", _pti("nans") == (-1, "Ungültige Zahl: nans", None))
