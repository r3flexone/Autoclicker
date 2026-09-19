"""Der Item-/Gegner-Katalog aus der offiziellen Idle-Clans-API.

Geschrieben wird die Datei von `tools/catalog.py`, gelesen hier. Wie bei
`marktwert.json` ist die Verbindung **eine Datei, kein Import**: das Werkzeug
weiss nichts vom Autoclicker, der Autoclicker nichts vom Werkzeug. Fehlt die
Datei, laeuft alles wie vorher — der Katalog ist Zusatz, nie Voraussetzung.

Er beantwortet zwei Fragen:

* **Wie heisst das Item wirklich?** `names()` liefert die geschlossene Liste, aus
  der die LLM-Benennung waehlen darf. Frei geraten nennt ein Modell die Art
  ("Bogen"), aus einer Liste den Gegenstand ("Godlike Bow").
* **Womit konkurriert es?** `category()` — im Autoclicker heisst eine Kategorie
  "diese Items konkurrieren, nimm nur das beste" (`_filter_scan_results`).

**Das haengt NICHT am LLM.** Die Kategorie folgt aus dem *Namen*; ob den ein
Mensch getippt oder ein Modell vorgeschlagen hat, ist gleichgueltig. `llm_enabled`
schaltet nur den einen der beiden Wege zum Namen frei.

Warum hier und nicht in `runtime/`: der Katalog wird vor allem beim Bearbeiten
gebraucht (Scan-Studio, Item-Editor), und `runtime/__init__` zieht den Worker
samt `imaging` und `winapi` nach. Dieselbe Ueberlegung wie bei `command.py`.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger("autoclicker")

# Pfad -> {"stand": (mtime, groesse), "katalog": Katalog}. Wie beim Marktwert
# ohne Lock: Dict-Zugriffe sind unter dem GIL atomar, und die Datei wird nur
# gelesen. Der Schluessel haengt am Dateistand, ein neu geschriebener Katalog
# greift also ohne Neustart.
_cache: dict = {}


class Catalog:
    """Name -> Kategorie und Wert, plus die Gegnerliste.

    Nachgeschlagen wird ohne Ruecksicht auf Gross-/Kleinschreibung: ein Modell
    antwortet mal `Godlike Bow`, mal `godlike bow`, und beides meint dasselbe.
    Zurueck kommt immer die Schreibweise aus dem Katalog — sonst entstuenden
    ueber `_category_normalize` zwei Kategorien mit demselben Wort.
    """

    def __init__(self, items: Optional[dict] = None,
                 enemy: Optional[list] = None) -> None:
        self.items: dict = items or {}
        self.enemy: list = list(enemy or [])
        self._index = {name.casefold(): name for name in self.items}

    def __bool__(self) -> bool:
        return bool(self.items or self.enemy)

    def __len__(self) -> int:
        return len(self.items)

    def match(self, name: str) -> Optional[str]:
        """Die Katalog-Schreibweise zu einem Namen, oder None."""
        return self._index.get(str(name or "").strip().casefold())

    def category(self, name: str) -> Optional[str]:
        """Die Gruppe, in der dieses Item mit anderen konkurriert."""
        real = self.match(name)
        if real is None:
            return None
        return self.items[real].get("kategorie") or None

    def value(self, name: str) -> Optional[float]:
        """Grundwert in Gold. Rangfolge INNERHALB eines Scans, nicht global."""
        real = self.match(name)
        if real is None:
            return None
        try:
            return float(self.items[real].get("wert") or 0)
        except (TypeError, ValueError):
            return None

    def names(self) -> list:
        """Alle Item-Namen — die geschlossene Liste fuer die LLM-Auswahl."""
        return list(self.items)


EMPTY = Catalog()


def load_catalog(path: str) -> Catalog:
    """Katalog aus `path`. Leerer Katalog, wenn aus oder nicht lesbar.

    Nicht lesbar ist kein Abbruchgrund: der Katalog verbessert das Benennen und
    Einordnen, er traegt keinen Lauf. Gemeldet wird es trotzdem — still zu
    scheitern hiesse, dass man die Wirkung sucht, die nie eintritt.
    """
    if not path:
        return EMPTY
    try:
        st = os.stat(path)
    except OSError:
        return EMPTY
    stand = (st.st_mtime, st.st_size)
    entry = _cache.get(path)
    if entry is not None and entry["stand"] == stand:
        return entry["catalog"]
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, IOError, OSError, UnicodeDecodeError) as e:
        logger.error(f"Katalog-Datei nicht lesbar ({path}): {e}")
        return EMPTY
    if not isinstance(raw, dict):
        logger.error(f"Katalog-Datei ist kein Objekt: {path}")
        return EMPTY

    items = {}
    for name, entries in (raw.get("items") or {}).items():
        if not isinstance(entries, dict):
            continue
        category = entries.get("kategorie")
        try:
            value = float(entries.get("wert") or 0)
        except (TypeError, ValueError):
            value = 0.0
        items[str(name)] = {"kategorie": str(category) if category else None,
                            "wert": value}
    enemy = [str(g) for g in (raw.get("gegner") or []) if g]

    catalog = Catalog(items, enemy)
    _cache[path] = {"stand": stand, "catalog": catalog}
    return catalog


def ranks(namen_und_werte: list) -> dict:
    """Dichte Prioritaeten je Kategorie: teuerstes Item bekommt P1.

    `namen_und_werte` ist eine Liste `(name, kategorie, wert)`. Zurueck kommt
    `name -> prioritaet`.

    **Gerechnet wird innerhalb der uebergebenen Menge**, also innerhalb EINES
    Scans, und dicht (1, 2, 3 …). Ein globaler Rang aus dem Katalog waere
    unbrauchbar: der beste Bogen eines Bestands bekaeme P49, weil 48 teurere im
    Katalog stehen, die man gar nicht besitzt.

    Gleicher Name heisst gleicher Rang — zwei Vorlagen desselben Items sind
    dasselbe Item, und zwei verschiedene Zahlen dafuer waeren eine Rangfolge,
    die per Zufall entscheidet.
    """
    je_kategorie: dict = {}
    for name, category, value in namen_und_werte:
        je_kategorie.setdefault(category, []).append((name, value))

    result: dict = {}
    for entries in je_kategorie.values():
        assigned: dict = {}
        for name, _value in sorted(entries, key=lambda nw: (-(nw[1] or 0), nw[0])):
            if name not in assigned:
                assigned[name] = len(assigned) + 1
            result[name] = assigned[name]
    return result
