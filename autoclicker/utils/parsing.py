"""
Parsing und Formatting: Zeit-Eingaben, Zahlen-Bereiche, Dauer-Formatierung,
Dateinamen-Bereinigung, kompaktes JSON.

Überwiegend reine String-/Daten-Funktionen; Ausnahme: atomic_write() schreibt
crash-sicher in eine Datei (Temp + os.replace) und wird von der Persistenz genutzt.
"""

import json
import os
import stat
import tempfile
import time
from pathlib import Path
import re
from datetime import datetime, timedelta


# =============================================================================
# ZEIT-EINGABEN PARSEN
# =============================================================================

def parse_time_input(time_str: str) -> tuple[float, str, float | None]:
    """Parst Zeit-Eingaben in verschiedenen Formaten.

        14:30 / 1430  → Sekunden bis 14:30 Uhr (heute oder morgen)
        30s / 30m / 2h → absolute Dauer (auch 30min, 2std)
        +30m / +2      → relativ (+ ohne Einheit = Minuten)

    Gibt `(sekunden, beschreibung, zielzeit_timestamp | None)` zurück; der
    Zeitstempel nur bei Uhrzeiten. Bei Fehler `(-1, fehlermeldung, None)`.
    """
    time_str = time_str.strip().lower()

    if not time_str:
        return (-1, "Keine Zeit angegeben", None)

    # Relative Zeit mit + Präfix: +30m, +2h, +2 (ohne Einheit = Minuten)
    has_plus_prefix = time_str.startswith("+")
    if has_plus_prefix:
        time_str = time_str[1:]

    def calculate_time_to_target(hour: int, minute: int) -> tuple[float, str, float]:
        """Berechnet Sekunden bis zur Zielzeit und gibt (seconds, description, timestamp) zurück."""
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if target <= now:
            target += timedelta(days=1)
            day_str = "morgen"
        else:
            day_str = "heute"

        seconds = (target - now).total_seconds()
        target_timestamp = target.timestamp()

        return (seconds, f"{day_str} um {hour:02d}:{minute:02d}", target_timestamp)

    # Format: HH:MM (Uhrzeit mit Doppelpunkt)
    if ":" in time_str:
        try:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0

            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return (-1, f"Ungültige Uhrzeit: {time_str}", None)

            return calculate_time_to_target(hour, minute)
        except ValueError:
            return (-1, f"Ungültiges Zeitformat: {time_str}", None)

    # Format: HHMM (4-stellige Uhrzeit ohne Doppelpunkt, 0000-2359)
    if time_str.isdigit() and len(time_str) == 4:
        try:
            hour = int(time_str[:2])
            minute = int(time_str[2:])

            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return (-1, f"Ungültige Uhrzeit: {time_str} (gültig: 0000-2359)", None)

            return calculate_time_to_target(hour, minute)
        except ValueError:
            return (-1, f"Ungültiges Zeitformat: {time_str}", None)

    # Format: Zahl mit Einheit (30s, 30m, 30min, 2h, 2std)
    try:
        unit = None
        value_str = time_str

        if time_str.endswith("std"):
            unit = "h"
            value_str = time_str[:-3]
        elif time_str.endswith("min"):
            unit = "m"
            value_str = time_str[:-3]
        elif time_str.endswith("h"):
            unit = "h"
            value_str = time_str[:-1]
        elif time_str.endswith("m"):
            unit = "m"
            value_str = time_str[:-1]
        elif time_str.endswith("s"):
            unit = "s"
            value_str = time_str[:-1]
        elif has_plus_prefix:
            unit = "m"  # + Präfix ohne Einheit = Minuten
        else:
            return (-1, f"Einheit fehlt! Nutze z.B. '{time_str}s', '{time_str}m' oder '{time_str}h'", None)

        value = float(value_str)

        if value < 0:
            return (-1, "Zeit muss positiv sein", None)

        if unit == "h":
            seconds = value * 3600
            desc = f"{value:.0f}h" if value == int(value) else f"{value}h"
        elif unit == "m":
            seconds = value * 60
            desc = f"{value:.0f}m" if value == int(value) else f"{value}m"
        else:
            seconds = value
            desc = f"{value:.0f}s" if value == int(value) else f"{value}s"

        return (seconds, desc, None)
    except ValueError:
        return (-1, f"Ungültige Zahl: {time_str}", None)


# =============================================================================
# ZAHLEN-EINGABEN PARSEN
# =============================================================================

def parse_non_negative_float(value: str, field_name: str = "Wert") -> tuple[float | None, str | None]:
    """Parst einen nicht-negativen Float-Wert aus einem String.

    Returns:
        (wert, None) bei Erfolg, (None, fehlermeldung) bei Fehler.
    """
    try:
        v = float(value)
    except ValueError:
        return None, f"'{value}' ist keine gültige Zahl"
    if v < 0:
        return None, f"{field_name} darf nicht negativ sein (Eingabe: {v:g})"
    return v, None


def parse_non_negative_range(value: str, field_name: str = "Bereich") -> tuple[tuple[float, float] | None, str | None]:
    """Parst einen nicht-negativen Min-Max-Bereich aus einem String (Format: 'min-max').

    Returns:
        ((min, max), None) bei Erfolg, (None, fehlermeldung) bei Fehler.
    """
    parts = value.split("-", 1)
    if len(parts) != 2:
        return None, f"{field_name}: Format <Min>-<Max> erwartet (z.B. 1-5)"
    min_val, min_err = parse_non_negative_float(parts[0], "Min")
    if min_err:
        return None, min_err
    max_val, max_err = parse_non_negative_float(parts[1], "Max")
    if max_err:
        return None, max_err
    if max_val < min_val:
        return None, f"Max ({max_val:g}) muss >= Min ({min_val:g}) sein"
    return (min_val, max_val), None


# =============================================================================
# FORMATTING + SANITIZING
# =============================================================================

def format_duration(seconds: float) -> str:
    """Formatiert Sekunden als hh:mm:ss oder mm:ss."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


# Was in einem Item-NAMEN stehen darf, ausser Buchstaben und Ziffern. Eine
# Whitelist und keine Verbotsliste: so faellt ein Pfadtrenner heraus, ohne dass
# ihn jemand aufzaehlen muss.
_NAME_EXTRA = " -'()&.,+"


def ohne_zaehler(name: str) -> str:
    """Der Name ohne angehaengten Eindeutigkeits-Zaehler.

    Die Umkehrung zu `eindeutiger_name()`: aus "Godlike Bow 2" wird
    "Godlike Bow". Gebraucht wird sie beim Katalog — der Name IST dort der
    Schluessel, und ein angehaengter Zaehler macht ihn unbekannt: das Item
    stand danach ohne Kategorie da, obwohl sein Gegenstand im Katalog steht.

    Zahlen, die zum Namen gehoeren, bleiben: "Slot 1" ohne Zaehler waere
    "Slot", und das ist ein anderer Name. Der Aufrufer probiert deshalb ERST
    den vollen Namen und erst danach diesen hier — was im Katalog steht,
    gewinnt.
    """
    roh = str(name or "").rstrip()
    teile = roh.rsplit(" ", 1)
    if len(teile) == 2 and teile[0].strip() and teile[1].isdigit():
        return teile[0].strip()
    return roh


def bereinige_itemname(name: str) -> str:
    """Ein vorgeschlagener Item-Name — als NAME, nicht als Dateiname.

    **Hier stand `sanitize_filename()`, und das war die falsche Funktion.** Sie
    macht Kleinbuchstaben und ersetzt Leerzeichen durch Unterstriche: aus
    "Godlike Bow" wurde `godlike_bow`. Der Name ist aber der Schluessel, unter
    dem der Katalog nachgeschlagen wird, und `Katalog.treffer()` vergleicht
    `casefold()` — nicht Unterstriche. Kategorie und Prioritaet blieben deshalb
    IMMER aus, ausgerechnet bei einem Namen, der woertlich aus dem Katalog
    kommt und nur noch zugeordnet werden musste.

    Dateinamenssicher muss das Ergebnis nicht sein: wo aus dem Namen wirklich
    eine Datei wird (`_apply_item_rename`), laeuft `sanitize_filename()` eine
    Ebene tiefer noch einmal darueber.
    """
    roh = " ".join(str(name or "").split())
    sauber = "".join(c for c in roh if c.isalnum() or c in _NAME_EXTRA)
    return " ".join(sauber.split()).strip(" .,")


def sanitize_filename(name: str) -> str:
    """Bereinigt einen Namen für sichere Dateinamen.

    Entfernt/ersetzt unsichere Zeichen wie ../, \\, :, *, ?, ", <, >, |
    """
    # Entferne Path-Traversal-Versuche
    name = name.replace("..", "").replace("/", "_").replace("\\", "_")
    # Entferne Windows-unsichere Zeichen
    name = re.sub(r'[<>:"|?*]', '', name)
    # Leerzeichen zu Unterstrichen
    name = name.replace(' ', '_')
    # Nur alphanumerische Zeichen, Unterstriche und Bindestriche erlauben
    name = re.sub(r'[^\w\-]', '', name)
    name = name.lower()
    # Leeres Ergebnis abfangen (z.B. Name bestand nur aus Sonderzeichen)
    if not name:
        return "unbenannt"
    # Windows-reservierte Gerätenamen dürfen nicht als Dateiname (auch mit
    # Endung) verwendet werden — sonst schlägt das Erstellen/Öffnen fehl.
    reserved = {"con", "prn", "aux", "nul"}
    reserved |= {f"com{i}" for i in range(1, 10)}
    reserved |= {f"lpt{i}" for i in range(1, 10)}
    if name in reserved:
        name = name + "_"
    return name


def naechster_freier_name(praefix: str, vergeben) -> str:
    """Erste freie Nummer einer Serie: 'Slot 1', 'Slot 2', ...

    Fuer durchnummerierte Serien die bessere Wahl als `eindeutiger_name`: sie
    fuellt Luecken auf, waehrend ein angehaengter Zaehler 'Slot 3 2' ergaebe.
    """
    n = 1
    while f"{praefix} {n}" in vergeben:
        n += 1
    return f"{praefix} {n}"


def eindeutiger_name(basis: str, vergeben) -> str:
    """Hängt eine Zahl an, bis der Name in `vergeben` frei ist.

    Items, Slots und Presets liegen in Name→Eintrag-Dicts: ein doppelter Name
    überschreibt den alten still, und weil Scans per Name referenzieren, läuft
    der Scan danach weiter und tut etwas anderes. 'Slot <len+1>' trägt das nicht,
    sobald einmal gelöscht oder umbenannt wurde.

    `vergeben` ist alles, was `in` beantwortet (Dict, Set, Liste).
    """
    if basis not in vergeben:
        return basis
    n = 2
    while f"{basis} {n}" in vergeben:
        n += 1
    return f"{basis} {n}"


# Kurze Zahlen-Arrays wieder auf eine Zeile ziehen: 2er (x,y), 3er (RGB), 4er (Region).
# Das Vorzeichen MUSS mit: auf einem Monitor links vom Hauptbildschirm sind x/y negativ,
# und ohne `-?` blieben genau diese Koordinaten mehrzeilig stehen - ausgerechnet die,
# die man am ehesten nachschlagen will.
_ZAHL = r'(-?\d+)'
_KOMPAKT = [
    (re.compile(r'\[\s*\n\s*' + r',\s*\n\s*'.join([_ZAHL] * n) + r'\s*\n\s*\]'),
     '[' + ', '.join(f'\\{i + 1}' for i in range(n)) + ']')
    for n in (4, 3, 2)
]


def compact_json(data, indent: int = 2) -> str:
    """Formatiert JSON mit kompakten Arrays (Koordinaten/Farben auf einer Zeile).

    `data` ist dict ODER Liste — points.json und die Boss-Bibliothek sind Listen.
    """
    json_str = json.dumps(data, indent=indent, ensure_ascii=False)
    for muster, ersatz in _KOMPAKT:
        json_str = muster.sub(ersatz, json_str)
    return json_str


def atomic_write(path, text: str, encoding: str = "utf-8") -> None:
    """Schreibt `text` crash-sicher in `path`.

    Erst in eine temporäre Datei im selben Verzeichnis, flush + fsync, dann per
    os.replace() atomar umbenennen: bei einem Absturz mitten im Schreiben bleibt
    die alte Datei intakt statt halb geschrieben. os.replace ist atomar, solange
    beide Dateien auf demselben Dateisystem liegen.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        # os.replace kann auf Windows mit PermissionError (WinError 5) fehlschlagen:
        #  - persistent: die Ziel-Datei trägt das Read-only-Attribut → Flag entfernen
        #  - transient: Virenscanner/Indexer/Editor sperrt Temp-/Zieldatei kurz → Retry
        last_err = None
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                last_err = None
                break
            except PermissionError as e:
                last_err = e
                # Read-only-Flag des Ziels entfernen (häufigste persistente Ursache).
                try:
                    if path.exists():
                        os.chmod(path, stat.S_IWRITE)
                except OSError:
                    pass
                time.sleep(0.1 * (attempt + 1))
        if last_err is not None:
            raise last_err
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
