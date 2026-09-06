"""Der Item-/Gegner-Katalog aus der offiziellen Idle-Clans-API.

Geschrieben wird die Datei von `tools/katalog.py`, gelesen hier. Wie bei
`marktwert.json` ist die Verbindung **eine Datei, kein Import**: das Werkzeug
weiss nichts vom Autoclicker, der Autoclicker nichts vom Werkzeug. Fehlt die
Datei, laeuft alles wie vorher — der Katalog ist Zusatz, nie Voraussetzung.

Er beantwortet zwei Fragen:

* **Wie heisst das Item wirklich?** `namen()` liefert die geschlossene Liste, aus
  der die LLM-Benennung waehlen darf. Frei geraten nennt ein Modell die Art
  ("Bogen"), aus einer Liste den Gegenstand ("Godlike Bow").
* **Womit konkurriert es?** `kategorie()` — im Autoclicker heisst eine Kategorie
  "diese Items konkurrieren, nimm nur das beste" (`_filter_scan_results`).

**Das haengt NICHT am LLM.** Die Kategorie folgt aus dem *Namen*; ob den ein
Mensch getippt oder ein Modell vorgeschlagen hat, ist gleichgueltig. `llm_enabled`
schaltet nur den einen der beiden Wege zum Namen frei.

Warum hier und nicht in `runtime/`: der Katalog wird vor allem beim Bearbeiten
gebraucht (Scan-Studio, Item-Editor), und `runtime/__init__` zieht den Worker
samt `imaging` und `winapi` nach. Dieselbe Ueberlegung wie bei `befehl.py`.
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


class Katalog:
    """Name -> Kategorie und Wert, plus die Gegnerliste.

    Nachgeschlagen wird ohne Ruecksicht auf Gross-/Kleinschreibung: ein Modell
    antwortet mal `Godlike Bow`, mal `godlike bow`, und beides meint dasselbe.
    Zurueck kommt immer die Schreibweise aus dem Katalog — sonst entstuenden
    ueber `_kategorie_normalisieren` zwei Kategorien mit demselben Wort.
    """

    def __init__(self, items: Optional[dict] = None,
                 gegner: Optional[list] = None) -> None:
        self.items: dict = items or {}
        self.gegner: list = list(gegner or [])
        self._index = {name.casefold(): name for name in self.items}

    def __bool__(self) -> bool:
        return bool(self.items or self.gegner)

    def __len__(self) -> int:
        return len(self.items)

    def treffer(self, name: str) -> Optional[str]:
        """Die Katalog-Schreibweise zu einem Namen, oder None."""
        return self._index.get(str(name or "").strip().casefold())

    def kategorie(self, name: str) -> Optional[str]:
        """Die Gruppe, in der dieses Item mit anderen konkurriert."""
        echt = self.treffer(name)
        if echt is None:
            return None
        return self.items[echt].get("kategorie") or None

    def wert(self, name: str) -> Optional[float]:
        """Grundwert in Gold. Rangfolge INNERHALB eines Scans, nicht global."""
        echt = self.treffer(name)
        if echt is None:
            return None
        try:
            return float(self.items[echt].get("wert") or 0)
        except (TypeError, ValueError):
            return None

    def namen(self) -> list:
        """Alle Item-Namen — die geschlossene Liste fuer die LLM-Auswahl."""
        return list(self.items)


LEER = Katalog()


def lade_katalog(pfad: str) -> Katalog:
    """Katalog aus `pfad`. Leerer Katalog, wenn aus oder nicht lesbar.

    Nicht lesbar ist kein Abbruchgrund: der Katalog verbessert das Benennen und
    Einordnen, er traegt keinen Lauf. Gemeldet wird es trotzdem — still zu
    scheitern hiesse, dass man die Wirkung sucht, die nie eintritt.
    """
    if not pfad:
        return LEER
    try:
        st = os.stat(pfad)
    except OSError:
        return LEER
    stand = (st.st_mtime, st.st_size)
    eintrag = _cache.get(pfad)
    if eintrag is not None and eintrag["stand"] == stand:
        return eintrag["katalog"]
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            roh = json.load(f)
    except (json.JSONDecodeError, IOError, OSError, UnicodeDecodeError) as e:
        logger.error(f"Katalog-Datei nicht lesbar ({pfad}): {e}")
        return LEER
    if not isinstance(roh, dict):
        logger.error(f"Katalog-Datei ist kein Objekt: {pfad}")
        return LEER

    items = {}
    for name, eintraege in (roh.get("items") or {}).items():
        if not isinstance(eintraege, dict):
            continue
        kategorie = eintraege.get("kategorie")
        try:
            wert = float(eintraege.get("wert") or 0)
        except (TypeError, ValueError):
            wert = 0.0
        items[str(name)] = {"kategorie": str(kategorie) if kategorie else None,
                            "wert": wert}
    gegner = [str(g) for g in (roh.get("gegner") or []) if g]

    katalog = Katalog(items, gegner)
    _cache[pfad] = {"stand": stand, "katalog": katalog}
    return katalog


def raenge(namen_und_werte: list) -> dict:
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
    for name, kategorie, wert in namen_und_werte:
        je_kategorie.setdefault(kategorie, []).append((name, wert))

    ergebnis: dict = {}
    for eintraege in je_kategorie.values():
        vergeben: dict = {}
        for name, _wert in sorted(eintraege, key=lambda nw: (-(nw[1] or 0), nw[0])):
            if name not in vergeben:
                vergeben[name] = len(vergeben) + 1
            ergebnis[name] = vergeben[name]
    return ergebnis
