"""Der Reiter „Bericht": was die vergangenen Läufe hinterlassen haben.

Der Live-Run zeigt das Jetzt, dieser Reiter das Gestern. Er beantwortet die eine
Frage, die man nach einer langen Nacht hat und bis hierher nur raten konnte:
**welcher Schritt läuft am häufigsten in den Timeout?**

Gerechnet wird nicht hier, sondern in `tools/log_report.py` — demselben Werkzeug,
das die Kommandozeile benutzt. Eine zweite Auswertung „fürs Fenster" wäre eine,
die andere Zahlen nennt als der Weg, den die README beschreibt. Die Richtung
stimmt dabei so, wie sie schon immer beschrieben war: **das Werkzeug importiert
nichts aus `autoclicker/`, die Brücke ruft das Werkzeug** — nie umgekehrt.
Deshalb steht der Import hier unten in der Methode und in einem `try`: fehlt
`tools/`, ist das ein Reiter, der sich erklärt, und kein Fenster, das nicht
aufgeht.

Der Ertrag ist derselbe Gedanke eine Stufe weiter: `item_found` aus dem Log mal
`marktwert.json` aus der Marktanalyse. Auch dort wird nichts importiert — die
Verbindung zwischen den beiden Subsystemen ist eine Datei und bleibt eine.
"""

import sys
from pathlib import Path
from typing import Optional

# Wie viele Log-Dateien höchstens gelesen werden, neueste zuerst. `logs/` wächst
# mit jedem Start, und der Reiter wird bei jedem Öffnen gezeichnet: ohne Deckel
# liest ein halbes Jahr Betrieb bei jedem Klick mit. Was wegfällt, wird gesagt —
# eine stillschweigend gekürzte Auswertung ist schlimmer als eine kurze.
MAX_DATEIEN = 50

# Wie viele Zeilen eine Rangliste zeigt. Dieselbe Zahl wie in der Konsolen-
# Ausgabe des Werkzeugs, damit beide Wege dasselbe Bild geben.
RANG_ZEILEN = 10


class BridgeBerichtMixin:
    """Der Reiter „Bericht": Session-Logs lesen und bewerten."""

    def _bericht_init(self) -> None:
        # Welche Sitzung offen ist. "" heisst „alle zusammen" — der Normalfall,
        # denn die Frage nach dem hängenden Schritt stellt sich über die Nacht
        # und nicht über eine einzelne Datei.
        self._bericht_wahl: str = ""

    # ------------------------------------------------------------ Momentaufnahme

    def bericht_daten(self, daten: Optional[dict] = None) -> dict:
        """Alles, was der Reiter zeichnet. Eigener Gegenstand, nicht die Sequenz.

        Geht deshalb über `frage()` und nicht über `ruf()`: eine Antwort von hier
        als Momentaufnahme zu behandeln zerschösse den Editor-Zustand.
        """
        if isinstance(daten, dict) and "datei" in daten:
            self._bericht_wahl = str(daten.get("datei") or "")

        ordner = self._bericht_ordner()
        alle = self._bericht_dateien(ordner)
        auswerten, fehler = self._bericht_werkzeug()
        if auswerten is None:
            return self._bericht_leer(ordner, fehler)

        gesamt = auswerten(alle)
        namen = {s["datei"] for s in gesamt["sitzungen"]}
        # Eine Wahl, deren Datei es nicht mehr gibt, fällt auf „alle" zurück
        # statt einen leeren Bericht zu zeigen: der Ordner wird aufgeräumt,
        # das Fenster steht derweil offen.
        if self._bericht_wahl and self._bericht_wahl not in namen:
            self._bericht_wahl = ""

        if self._bericht_wahl:
            eine = [p for p in alle if p.name == self._bericht_wahl]
            bericht = auswerten(eine)
        else:
            bericht = gesamt

        return {
            "ordner": str(ordner.resolve()) if ordner else "",
            "aktiv": bool(self._bericht_config("session_log_enabled", False)),
            "verfuegbar": True,
            "fehler": "",
            "gewaehlt": self._bericht_wahl,
            # Neueste zuerst: danach sucht man. Die Auswertung selbst liest in
            # Dateireihenfolge, das ändert an den Summen nichts.
            "sitzungen": list(reversed(gesamt["sitzungen"])),
            "ausgelassen": max(0, len(self._bericht_alle_dateien(ordner)) - len(alle)),
            "bericht": self._bericht_kurz(bericht),
            "ertrag": self._ertrag(bericht),
        }

    # ------------------------------------------------------------ Dateien

    def _bericht_config(self, feld: str, vorgabe):
        from ...config import CONFIG
        return getattr(CONFIG, feld, vorgabe)

    def _bericht_ordner(self) -> Optional[Path]:
        ordner = Path(self._bericht_config("session_log_dir", "logs") or "logs")
        return ordner if ordner.is_dir() else None

    @staticmethod
    def _bericht_alle_dateien(ordner: Optional[Path]) -> list:
        if ordner is None:
            return []
        return sorted(ordner.glob("*.csv"))

    def _bericht_dateien(self, ordner: Optional[Path]) -> list:
        return self._bericht_alle_dateien(ordner)[-MAX_DATEIEN:]

    @staticmethod
    def _bericht_werkzeug():
        """`auswerten` aus `tools/log_report.py`, oder der Grund, warum nicht.

        Der Import steht hier und nicht am Modulkopf: `tools/` gehört nicht zum
        Programm, sondern zum Repo. Fehlt es, soll der Reiter das sagen — nicht
        das Fenster beim Start damit umfallen.
        """
        wurzel = Path(__file__).resolve().parents[3]
        if str(wurzel) not in sys.path:
            sys.path.insert(0, str(wurzel))
        try:
            from tools.log_report import auswerten
        except ImportError as e:
            return None, f"tools/log_report.py nicht gefunden ({e})"
        return auswerten, ""

    def _bericht_leer(self, ordner: Optional[Path], fehler: str) -> dict:
        return {
            "ordner": str(ordner.resolve()) if ordner else "",
            "aktiv": bool(self._bericht_config("session_log_enabled", False)),
            "verfuegbar": False,
            "fehler": fehler,
            "gewaehlt": "",
            "sitzungen": [],
            "ausgelassen": 0,
            "bericht": None,
            "ertrag": None,
        }

    # ------------------------------------------------------------ Auswertung

    @staticmethod
    def _bericht_kurz(roh: dict) -> dict:
        """Die Auswertung auf das eingedampft, was der Reiter zeigt.

        Die vollständigen Ranglisten mitzuschicken wäre bei einer Nacht mit
        hundert Item-Namen ein Vielfaches der Anzeige — und angezeigt werden
        ohnehin nur die obersten Zeilen.
        """
        verify_ok = roh["verify_ok"]
        miss = roh["verify_miss"]
        return {
            "sitzungen": len(roh["sitzungen"]),
            "dauer": roh["dauer"],
            "klicks": roh["ereignisse"].get("click", 0),
            "tasten": roh["ereignisse"].get("key", 0),
            "scrolls": roh["ereignisse"].get("scroll", 0),
            "timeouts": roh["timeouts"][:RANG_ZEILEN],
            "timeouts_gesamt": sum(n for _, n in roh["timeouts"]),
            "items": roh["items"][:RANG_ZEILEN],
            "items_gesamt": sum(n for _, n in roh["items"]),
            "erkannt": roh["erkannt"][:RANG_ZEILEN],
            # Beide Seiten der Nachprüfung: „12x ohne Wirkung" allein sagt
            # nichts, solange nicht dabeisteht, wie oft es geklappt hat.
            "verify_ok_gesamt": sum(verify_ok.values()),
            "verify_miss_gesamt": sum(n for _, n in miss),
            "verify_miss": [[name, n, verify_ok.get(name, 0)]
                            for name, n in miss[:RANG_ZEILEN]],
            "stoerungen": roh["stoerungen"],
            "unbekannt": roh["unbekannt"],
            "nicht_lesbar": roh["nicht_lesbar"],
        }

    def _ertrag(self, roh: dict) -> Optional[dict]:
        """Stückzahlen mal Marktwert — der tatsächliche Ertrag eines Laufs.

        **Die Zahl ist eine Obergrenze, keine Abrechnung.** `item_found` heisst
        „erkannt", nicht „eingesammelt und verkauft": ein Klick kann ins Leere
        gehen, ein Item im Inventar bleiben, ein Verkauf scheitern. Der Reiter
        schreibt das dazu, statt eine Genauigkeit zu behaupten, die das Log
        nicht hergibt.

        Ohne eingetragene Marktwert-Datei gibt es Stückzahlen und sonst nichts.
        Das ist kein Fehlerfall, sondern der Normalfall ohne Marktanalyse.
        """
        pfad = str(self._bericht_config("scan_market_value_file", "") or "")
        if not pfad or not roh["items"]:
            return None
        from ...runtime.item_scan import lade_marktwerte
        werte = lade_marktwerte(pfad)
        if not werte:
            return {"datei": pfad, "lesbar": False, "zeilen": [],
                    "gold": 0.0, "pro_stunde": None, "ohne_wert": []}

        zeilen, ohne, gold = [], [], 0.0
        for name, anzahl in roh["items"]:
            wert = werte.get(name)
            if wert is None:
                ohne.append([name, anzahl])
                continue
            summe = wert * anzahl
            gold += summe
            zeilen.append([name, anzahl, wert, summe])
        zeilen.sort(key=lambda z: z[3], reverse=True)
        stunden = roh["dauer"] / 3600 if roh["dauer"] > 0 else 0
        return {
            "datei": pfad,
            "lesbar": True,
            "zeilen": zeilen,
            "gold": gold,
            "pro_stunde": (gold / stunden) if stunden else None,
            "ohne_wert": ohne,
        }
