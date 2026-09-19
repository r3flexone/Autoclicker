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
MAX_FILES = 50

# Wie viele Zeilen eine Rangliste zeigt. Dieselbe Zahl wie in der Konsolen-
# Ausgabe des Werkzeugs, damit beide Wege dasselbe Bild geben.
RANK_ROWS = 10


class BridgeReportMixin:
    """Der Reiter „Bericht": Session-Logs lesen und bewerten."""

    def _report_init(self) -> None:
        # Welche Sitzung offen ist. "" heisst „alle zusammen" — der Normalfall,
        # denn die Frage nach dem hängenden Schritt stellt sich über die Nacht
        # und nicht über eine einzelne Datei.
        self._report_choice: str = ""

    # ------------------------------------------------------------ Momentaufnahme

    def report_data(self, data: Optional[dict] = None) -> dict:
        """Alles, was der Reiter zeichnet. Eigener Gegenstand, nicht die Sequenz.

        Geht deshalb über `ask()` und nicht über `call()`: eine Antwort von hier
        als Momentaufnahme zu behandeln zerschösse den Editor-Zustand.
        """
        if isinstance(data, dict) and "file" in data:
            self._report_choice = str(data.get("file") or "")

        folder = self._report_folder()
        all_of = self._report_files(folder)
        evaluate, error = self._report_tool()
        if evaluate is None:
            return self._report_empty(folder, error)

        total = evaluate(all_of)
        names = {s["file"] for s in total["sessions"]}
        # Eine Wahl, deren Datei es nicht mehr gibt, fällt auf „alle" zurück
        # statt einen leeren Bericht zu zeigen: der Ordner wird aufgeräumt,
        # das Fenster steht derweil offen.
        if self._report_choice and self._report_choice not in names:
            self._report_choice = ""

        if self._report_choice:
            one = [p for p in all_of if p.name == self._report_choice]
            report = evaluate(one)
        else:
            report = total

        return {
            "folder": str(folder.resolve()) if folder else "",
            "active": bool(self._report_config("session_log_enabled", False)),
            "available": True,
            "error": "",
            "selected": self._report_choice,
            # Neueste zuerst: danach sucht man. Die Auswertung selbst liest in
            # Dateireihenfolge, das ändert an den Summen nichts.
            "sessions": list(reversed(total["sessions"])),
            "skipped_files": max(0, len(self._report_all_files(folder)) - len(all_of)),
            "bericht": self._report_brief(report),
            "yield_value": self._yield(report),
        }

    # ------------------------------------------------------------ Dateien

    def _report_config(self, field: str, default_value):
        from ...config import CONFIG
        return getattr(CONFIG, field, default_value)

    def _report_folder(self) -> Optional[Path]:
        folder = Path(self._report_config("session_log_dir", "logs") or "logs")
        return folder if folder.is_dir() else None

    @staticmethod
    def _report_all_files(folder: Optional[Path]) -> list:
        if folder is None:
            return []
        return sorted(folder.glob("*.csv"))

    def _report_files(self, folder: Optional[Path]) -> list:
        return self._report_all_files(folder)[-MAX_FILES:]

    @staticmethod
    def _report_tool():
        """`evaluate` aus `tools/log_report.py`, oder der Grund, warum nicht.

        Der Import steht hier und nicht am Modulkopf: `tools/` gehört nicht zum
        Programm, sondern zum Repo. Fehlt es, soll der Reiter das sagen — nicht
        das Fenster beim Start damit umfallen.
        """
        wurzel = Path(__file__).resolve().parents[3]
        if str(wurzel) not in sys.path:
            sys.path.insert(0, str(wurzel))
        try:
            from tools.log_report import evaluate
        except ImportError as e:
            return None, f"tools/log_report.py nicht gefunden ({e})"
        return evaluate, ""

    def _report_empty(self, folder: Optional[Path], error: str) -> dict:
        return {
            "folder": str(folder.resolve()) if folder else "",
            "active": bool(self._report_config("session_log_enabled", False)),
            "available": False,
            "error": error,
            "selected": "",
            "sessions": [],
            "skipped_files": 0,
            "bericht": None,
            "yield_value": None,
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
            "sessions": len(raw["sessions"]),
            "duration": raw["duration"],
            "clicks": raw["events"].get("click", 0),
            "keys": raw["events"].get("key", 0),
            "scrolls": raw["events"].get("scroll", 0),
            "timeouts": raw["timeouts"][:RANK_ROWS],
            "timeouts_total": sum(n for _, n in raw["timeouts"]),
            "items": raw["items"][:RANK_ROWS],
            "items_total": sum(n for _, n in raw["items"]),
            "detected": raw["detected"][:RANK_ROWS],
            # Beide Seiten der Nachprüfung: „12x ohne Wirkung" allein sagt
            # nichts, solange nicht dabeisteht, wie oft es geklappt hat.
            "verify_ok_total": sum(verify_ok.values()),
            "verify_miss_total": sum(n for _, n in miss),
            "verify_miss": [[name, n, verify_ok.get(name, 0)]
                            for name, n in miss[:RANK_ROWS]],
            "disturbances": raw["disturbances"],
            "unbekannt": raw["unbekannt"],
            "unreadable": raw["unreadable"],
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
            return {"file": path, "readable": False, "rows": [],
                    "gold": 0.0, "per_hour": None, "without_value": []}

        lines, without, gold = [], [], 0.0
        for name, count in raw["items"]:
            value = values.get(name)
            if value is None:
                without.append([name, count])
                continue
            total_sum = value * count
            gold += total_sum
            lines.append([name, count, value, total_sum])
        lines.sort(key=lambda z: z[3], reverse=True)
        hours = raw["duration"] / 3600 if raw["duration"] > 0 else 0
        return {
            "file": path,
            "readable": True,
            "rows": lines,
            "gold": gold,
            "per_hour": (gold / hours) if hours else None,
            "without_value": without,
        }
