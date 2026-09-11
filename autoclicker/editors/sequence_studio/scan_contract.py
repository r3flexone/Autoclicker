"""Stabiles Protokoll zwischen Scan-Logik, Brücke und Weboberfläche."""

MODUS_WAHL = "wahl"
MODUS_SLOT = "slot"
MODUS_MESSEN = "messen"
MODUS_KLICK = "klick"
MODUS_BEREICH = "bereich"
MODUS_FINDEN = "finden"
MODI = (
    MODUS_WAHL,
    MODUS_FINDEN,
    MODUS_SLOT,
    MODUS_MESSEN,
    MODUS_KLICK,
    MODUS_BEREICH,
)

# Die beiden Werkzeuge der Erkennungs-Scans (Boss, Icon). Sie stehen NEBEN
# `MODI` und nicht darin: `MODI` sind die Kacheln der Item-Ansicht, und ein Test
# hält die Kachelliste der Seite Zug um Zug dagegen. Eine Region aufzuziehen
# ergibt bei Slots keinen Sinn, ein Slot-Suchlauf bei einem Boss keinen — zwei
# Arten, zwei Werkzeugkästen.
MODUS_REGION = "region"
MODUS_AKTION = "aktion"
MODI_ERKENNUNG = (
    MODUS_WAHL,
    MODUS_REGION,
    MODUS_AKTION,
)
# Was `scan_modus_setzen()` überhaupt annimmt. Reihenfolge egal, Menge zählt.
MODI_ALLE = MODI + (MODUS_REGION, MODUS_AKTION)

ART_SLOT = "slot"
ART_ITEM = "item"
ART_SCAN = "scan"
# Die Erkennungs-Scans. `ART_BOSS_SCAN`/`ART_ICON_SCAN` sind die Konfigurationen,
# `ART_BOSS` ist ein einzelner Boss DARIN — dieselbe Trennung wie Scan/Slot bei
# den Items: der Scan ist der Zusammenhang, das andere das bearbeitete Ding.
ART_BOSS_SCAN = "boss_scan"
ART_BOSS = "boss"
ART_ICON_SCAN = "icon_scan"
# Die globale Boss-Bibliothek ist keine Datei unter vielen, sondern EIN Eintrag
# am Ende der Liste. Sie gilt zusätzlich in jedem Boss-Scan.
ART_BIBLIOTHEK = "bibliothek"

# Womit die Oberfläche zwischen den drei Scan-Arten umschaltet. Reiner
# Oberflächenzustand (`scanArt` in app.js) — die Brücke bekommt bei jedem Befehl
# gesagt, worauf er wirkt, statt sich eine vierte Wahrheit zu merken.
ARTEN = ("item", "boss", "icon")

MIN_SLOT = 8
TREFFER_MIN = 14
UNDO_TIEFE = 30
# Kleinste Kantenlänge einer Erkennungs-Region. Anders als beim Slot geht es
# hier nicht ums Treffen mit der Maus, sondern ums Erkennen: unter ein paar
# Pixeln hat ein Template keine Struktur mehr, an der es sich festhalten kann.
MIN_REGION = 6


# Welches Feld eines Schritts auf welche Scan-Art zeigt — und mit welchem
# Vorsatz der Konsolen-Editor daraus eine Beschriftung baut (`steps.py`).
# `boss` hat ZWEI Felder: ein Boss-Scan wird als einmaliger Scan und als
# Watcher benutzt, beide zeigen per Namen auf dieselbe Datei.
_REF_FELDER = {
    "item": (("item_scan",), "Scan:"),
    "boss": (("boss_scan", "boss_watcher"), None),
    "icon": (("icon_scan",), "Icon:"),
}
# Die Boss-Felder tragen verschiedene Vorsaetze, deshalb einzeln.
_REF_VORSATZ = {"item_scan": "Scan:", "boss_scan": "Boss:",
                "boss_watcher": "Watcher:", "icon_scan": "Icon:"}


def referenzen_umbenennen(board, art: str, alt: str, neu: str) -> int:
    """Zieht jede Sequenz-Referenz auf einen Scan nach. Gibt die Anzahl zurück.

    **Der Name IST die Referenz** — ein Scan wird per Namen aus dem Schritt
    heraus gerufen, nicht per ID. Wer ihn umbenennt, ohne die Schritte
    nachzuziehen, hinterlässt Blöcke, die auf einen Scan zeigen, den es nicht
    mehr gibt; gemessen an einem echten Umbenenn-Durchgang zog **eine von
    sechs** Referenzen nach.

    Zwei Dinge macht sie, und das zweite ist die Feinheit:

    * die **Felder** (`item_scan`, `boss_scan`, `boss_watcher`, `icon_scan`) —
      das ist die Wirkung, ohne sie läuft der Block ins Leere.
    * die **Beschriftung** (`step.name`), aber nur, wenn sie genau die
      abgeleitete Form hat (`Boss:<alt>`). Ein selbst getippter Blockname wird
      **nicht** angefasst: er gehört dem Nutzer, und ihn stillschweigend
      umzuschreiben wäre schlimmer als eine veraltete Beschriftung.
    """
    felder = _REF_FELDER.get(art, ((), None))[0]
    getroffen = 0
    for lane in getattr(board, "lanes", []):
        for step in lane.steps:
            for feld in felder:
                if getattr(step, feld, None) != alt:
                    continue
                setattr(step, feld, neu)
                getroffen += 1
                vorsatz = _REF_VORSATZ[feld]
                if step.name == f"{vorsatz}{alt}":
                    step.name = f"{vorsatz}{neu}"
    return getroffen
