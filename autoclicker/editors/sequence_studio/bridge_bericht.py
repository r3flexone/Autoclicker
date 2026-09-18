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

    def _report_init(self) -> None:
        # Welche Sitzung offen ist. "" heisst „alle zusammen" — der Normalfall,
        # denn die Frage nach dem hängenden Schritt stellt sich über die Nacht
        # und nicht über eine einzelne Datei.
        self._bericht_wahl: str = ""

    # ------------------------------------------------------------ Momentaufnahme

    def report_data(self, data: Optional[dict] = None) -> dict:
        """Alles, was der Reiter zeichnet. Eigener Gegenstand, nicht die Sequenz.

        Geht deshalb über `frage()` und nicht über `ruf()`: eine Antwort von hier
        als Momentaufnahme zu behandeln zerschösse den Editor-Zustand.
        """
        if isinstance(data, dict) and "datei" in data:
            self._bericht_wahl = str(data.get("datei") or "")

        folder = self._report_folder()
        alle = self._report_files(folder)
        auswerten, fehler = self._report_tool()
        if auswerten is None:
            return self._report_empty(folder, fehler)

        total = auswerten(alle)
        names = {s["datei"] for s in total["sitzungen"]}
        # Eine Wahl, deren Datei es nicht mehr gibt, fällt auf „alle" zurück
        # statt einen leeren Bericht zu zeigen: der Ordner wird aufgeräumt,
        # das Fenster steht derweil offen.
        if self._bericht_wahl and self._bericht_wahl not in names:
            self._bericht_wahl = ""

        if self._bericht_wahl:
            eine = [p for p in alle if p.name == self._bericht_wahl]
            report = auswerten(eine)
        else:
            report = total

        return {
            "ordner": str(folder.resolve()) if folder else "",
            "aktiv": bool(self._report_config("session_log_enabled", False)),
            "verfuegbar": True,
            "fehler": "",
            "gewaehlt": self._bericht_wahl,
            # Neueste zuerst: danach sucht man. Die Auswertung selbst liest in
            # Dateireihenfolge, das ändert an den Summen nichts.
            "sitzungen": list(reversed(total["sitzungen"])),
            "ausgelassen": max(0, len(self._report_all_files(folder)) - len(alle)),
            "bericht": self._report_brief(report),
            "ertrag": self._yield(report),
        }

    # ------------------------------------------------------------ Dateien

    def _report_config(self, feld: str, vorgabe):
        from ...config import CONFIG
        return getattr(CONFIG, feld, vorgabe)

    def _report_folder(self) -> Optional[Path]:
        folder = Path(self._report_config("session_log_dir", "logs") or "logs")
        return folder if folder.is_dir() else None

    @staticmethod
    def _report_all_files(folder: Optional[Path]) -> list:
        if folder is None:
            return []
        return sorted(folder.glob("*.csv"))

    def _report_files(self, folder: Optional[Path]) -> list:
        return self._report_all_files(folder)[-MAX_DATEIEN:]

    @staticmethod
    def _report_tool():
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

    def _report_empty(self, folder: Optional[Path], fehler: str) -> dict:
        return {
            "ordner": str(folder.resolve()) if folder else "",
            "aktiv": bool(self._report_config("session_log_enabled", False)),
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
    def _report_brief(raw: dict) -> dict:
        """Die Auswertung auf das eingedampft, was der Reiter zeigt.

        Die vollständigen Ranglisten mitzuschicken wäre bei einer Nacht mit
        hundert Item-Namen ein Vielfaches der Anzeige — und angezeigt werden
        ohnehin nur die obersten Zeilen.
        """
        verify_ok = raw["verify_ok"]
        miss = raw["verify_miss"]
        return {
            "sitzungen": len(raw["sitzungen"]),
            "dauer": raw["dauer"],
            "klicks": raw["ereignisse"].get("click", 0),
            "tasten": raw["ereignisse"].get("key", 0),
            "scrolls": raw["ereignisse"].get("scroll", 0),
            "timeouts": raw["timeouts"][:RANG_ZEILEN],
            "timeouts_gesamt": sum(n for _, n in raw["timeouts"]),
            "items": raw["items"][:RANG_ZEILEN],
            "items_gesamt": sum(n for _, n in raw["items"]),
            "erkannt": raw["erkannt"][:RANG_ZEILEN],
            # Beide Seiten der Nachprüfung: „12x ohne Wirkung" allein sagt
            # nichts, solange nicht dabeisteht, wie oft es geklappt hat.
            "verify_ok_gesamt": sum(verify_ok.values()),
            "verify_miss_gesamt": sum(n for _, n in miss),
            "verify_miss": [[name, n, verify_ok.get(name, 0)]
                            for name, n in miss[:RANG_ZEILEN]],
            "stoerungen": raw["stoerungen"],
            "unbekannt": raw["unbekannt"],
            "nicht_lesbar": raw["nicht_lesbar"],
        }

    def _yield(self, raw: dict) -> Optional[dict]:
        """Stückzahlen mal Marktwert — der tatsächliche Ertrag eines Laufs.

        **Die Zahl ist eine Obergrenze, keine Abrechnung.** `item_found` heisst
        „erkannt", nicht „eingesammelt und verkauft": ein Klick kann ins Leere
        gehen, ein Item im Inventar bleiben, ein Verkauf scheitern. Der Reiter
        schreibt das dazu, statt eine Genauigkeit zu behaupten, die das Log
        nicht hergibt.

        Ohne eingetragene Marktwert-Datei gibt es Stückzahlen und sonst nichts.
        Das ist kein Fehlerfall, sondern der Normalfall ohne Marktanalyse.
        """
        path = str(self._report_config("scan_market_value_file", "") or "")
        if not path or not raw["items"]:
            return None
        from ...runtime.item_scan import load_market_values
        values = load_market_values(path)
        if not values:
            return {"datei": path, "lesbar": False, "zeilen": [],
                    "gold": 0.0, "pro_stunde": None, "ohne_wert": []}

        lines, ohne, gold = [], [], 0.0
        for name, count in raw["items"]:
            value = values.get(name)
            if value is None:
                ohne.append([name, count])
                continue
            summe = value * count
            gold += summe
            lines.append([name, count, value, summe])
        lines.sort(key=lambda z: z[3], reverse=True)
        stunden = raw["dauer"] / 3600 if raw["dauer"] > 0 else 0
        return {
            "datei": path,
            "lesbar": True,
            "zeilen": lines,
            "gold": gold,
            "pro_stunde": (gold / stunden) if stunden else None,
            "ohne_wert": ohne,
        }
