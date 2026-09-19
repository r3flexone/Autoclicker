"""Stabiles Protokoll zwischen Scan-Logik, Brücke und Weboberfläche."""

MODE_CHOICE = "choice"
MODE_SLOT = "slot"
MODE_MEASURE = "measure"
MODE_CLICK = "click"
MODE_AREA = "area"
MODE_FIND = "find"
MODES = (
    MODE_CHOICE,
    MODE_FIND,
    MODE_SLOT,
    MODE_MEASURE,
    MODE_CLICK,
    MODE_AREA,
)

# Die beiden Werkzeuge der Erkennungs-Scans (Boss, Icon). Sie stehen NEBEN
# `MODES` und nicht darin: `MODES` sind die Kacheln der Item-Ansicht, und ein Test
# hält die Kachelliste der Seite Zug um Zug dagegen. Eine Region aufzuziehen
# ergibt bei Slots keinen Sinn, ein Slot-Suchlauf bei einem Boss keinen — zwei
# Arten, zwei Werkzeugkästen.
MODE_REGION = "region"
MODE_ACTION = "action"
MODES_DETECTION = (
    MODE_CHOICE,
    MODE_REGION,
    MODE_ACTION,
)
# Was `scan_mode_set()` überhaupt annimmt. Reihenfolge egal, Menge zählt.
MODES_ALL = MODES + (MODE_REGION, MODE_ACTION)

KIND_SLOT = "slot"
KIND_ITEM = "item"
KIND_SCAN = "scan"
# Die Erkennungs-Scans. `KIND_BOSS_SCAN`/`KIND_ICON_SCAN` sind die Konfigurationen,
# `KIND_BOSS` ist ein einzelner Boss DARIN — dieselbe Trennung wie Scan/Slot bei
# den Items: der Scan ist der Zusammenhang, das andere das bearbeitete Ding.
KIND_BOSS_SCAN = "boss_scan"
KIND_BOSS = "boss"
KIND_ICON_SCAN = "icon_scan"
# Die globale Boss-Bibliothek ist keine Datei unter vielen, sondern EIN Eintrag
# am Ende der Liste. Sie gilt zusätzlich in jedem Boss-Scan.
KIND_LIBRARY = "bibliothek"

# Womit die Oberfläche zwischen den drei Scan-Arten umschaltet. Reiner
# Oberflächenzustand (`scanKind` in app.js) — die Brücke bekommt bei jedem Befehl
# gesagt, worauf er wirkt, statt sich eine vierte Wahrheit zu merken.
SCAN_KINDS = ("item", "boss", "icon")

MIN_SLOT = 8
HIT_MIN = 14
UNDO_DEPTH = 30
# Kleinste Kantenlänge einer Erkennungs-Region. Anders als beim Slot geht es
# hier nicht ums Treffen mit der Maus, sondern ums Erkennen: unter ein paar
# Pixeln hat ein Template keine Struktur mehr, an der es sich festhalten kann.
MIN_REGION = 6


# Welches Feld eines Schritts auf welche Scan-Art zeigt — und mit welchem
# Vorsatz der Konsolen-Editor daraus eine Beschriftung baut (`steps.py`).
# `boss` hat ZWEI Felder: ein Boss-Scan wird als einmaliger Scan und als
# Watcher benutzt, beide zeigen per Namen auf dieselbe Datei.
_REF_FIELDS = {
    "item": (("item_scan",), "Scan:"),
    "boss": (("boss_scan", "boss_watcher"), None),
    "icon": (("icon_scan",), "Icon:"),
}
# Die Boss-Felder tragen verschiedene Vorsaetze, deshalb einzeln.
_REF_PREFIX = {"item_scan": "Scan:", "boss_scan": "Boss:",
                "boss_watcher": "Watcher:", "icon_scan": "Icon:"}


def rename_references(board, kind: str, old: str, new: str) -> int:
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
    fields = _REF_FIELDS.get(kind, ((), None))[0]
    hit = 0
    for lane in getattr(board, "lanes", []):
        for step in lane.steps:
            for field in fields:
                if getattr(step, field, None) != old:
                    continue
                setattr(step, field, new)
                hit += 1
                prefix = _REF_PREFIX[field]
                if step.name == f"{prefix}{old}":
                    step.name = f"{prefix}{new}"
    return hit
