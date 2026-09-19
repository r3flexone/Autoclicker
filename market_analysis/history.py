"""Laufhistorie in SQLite - was die Excel-Datei beim Ueberschreiben verliert.

Excel und Chart werden weiter bei jedem Lauf ueberschrieben: sie beantworten
"was farme ich JETZT", und dafuer ist ein Stand genug. Die zweite Frage - "war das
gestern auch schon so?" - konnten sie nie beantworten, und ein Preissturz sieht in
einer Momentaufnahme genauso aus wie ein dauerhaft schlechtes Item.

Datierte Excel-Kopien waeren der naheliegende und der falsche Weg: hundert .xlsx im
Ordner beantworten keine einzige Frage, ohne dass man sie alle oeffnet. Eine
Datenbank daneben kann man abfragen, und sie kostet nichts ausser sqlite3 aus der
Standardbibliothek.

Drei Regeln tragen das Modul:

- **Nur erfolgreiche Laeufe.** Geschrieben wird am Ende in EINER Transaktion. Bricht
  der Lauf vorher ab, steht nichts in der Datenbank - ein halber Lauf sieht sonst
  wie ein Markteinbruch aus.
- **Jeder Lauf traegt Zeitpunkt, Codeversion und Config-Hash.** Ohne die beiden
  letzten vergleicht man Zahlen, die unter verschiedenen Annahmen entstanden sind,
  und haelt eine geaenderte Ersparnis fuer eine Marktbewegung.
- **Alte Details werden zu Tageswerten und verschwinden.** Die Detailzeilen sind
  das Grosse (ein paar hundert je Lauf), die Tageswerte das Kleine. Ohne das waechst
  die Datei ewig, und niemand raeumt sie je auf.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import datetime, timedelta

try:
    from . import config as cfg
except ImportError:  # direkter Skriptstart
    import config as cfg  # type: ignore


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    tag           TEXT NOT NULL,
    code_version  TEXT NOT NULL,
    config_hash   TEXT NOT NULL,
    items         INTEGER NOT NULL DEFAULT 0,
    notiz         TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS items (
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    item        TEXT NOT NULL,
    item_id     INTEGER,
    skill       TEXT,
    bid         REAL, ask REAL, avg REAL,
    bid_vol     REAL, ask_vol REAL,
    npc_preis   REAL,
    kosten_h    REAL,
    gold_h      REAL,
    gold_h_real REAL,
    verkaufsweg TEXT,
    rang        INTEGER,
    warnungen   TEXT
);

CREATE TABLE IF NOT EXISTS orderbook (
    run_id  INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL,
    item_id INTEGER NOT NULL,
    item    TEXT,
    seite   TEXT NOT NULL,
    stufe   INTEGER NOT NULL,
    preis   REAL NOT NULL,
    menge   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS daily (
    tag       TEXT NOT NULL,
    item      TEXT NOT NULL,
    item_id   INTEGER,
    laeufe    INTEGER NOT NULL,
    bid       REAL, ask REAL,
    npc_preis REAL,
    kosten_h  REAL,
    gold_h    REAL,
    gold_h_real REAL,
    PRIMARY KEY (tag, item)
);

CREATE INDEX IF NOT EXISTS idx_items_item ON items(item);
CREATE INDEX IF NOT EXISTS idx_items_tag  ON items(tag);
CREATE INDEX IF NOT EXISTS idx_ob_item    ON orderbook(item_id);
CREATE INDEX IF NOT EXISTS idx_daily_item ON daily(item);
"""

ITEM_COLUMNS = ("item", "item_id", "skill", "bid", "ask", "avg", "bid_vol", "ask_vol",
                "npc_preis", "kosten_h", "gold_h", "gold_h_real", "verkaufsweg",
                "rang", "warnungen")


# ---------------------------------------------------------------
# Identitaet eines Laufs
# ---------------------------------------------------------------

def code_version() -> str:
    """Kurzer Git-Hash, sonst ein Hash ueber die Modulzeiten.

    Ohne Git (ZIP-Download, kopierter Ordner) waere `unknown` die ehrliche, aber
    nutzlose Antwort - dann taugt der Fingerabdruck der Dateien genauso: er aendert
    sich, wenn jemand am Code dreht, und genau darum geht es.
    """
    folder = os.path.dirname(os.path.abspath(__file__))
    try:
        out = subprocess.run(["git", "-C", folder, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    parts = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".py"):
            path = os.path.join(folder, name)
            try:
                parts.append(f"{name}:{os.path.getmtime(path):.0f}")
            except OSError:
                continue
    return "dat-" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:8]


def config_hash(module_name=cfg) -> str:
    """Fingerabdruck der rechenrelevanten Config (CONFIG_HASH_KEYS).

    Bewusst nicht ueber die ganze Datei: Pfade, Farben und Schwellen fuer Warnungen
    aendern keine einzige Zahl. Was drin steht, entscheidet der Anwender ueber
    CONFIG_HASH_KEYS - so bleibt sichtbar, WAS als vergleichbar gilt.
    """
    values = {name: _hashable(getattr(module_name, name, None)) for name in cfg.CONFIG_HASH_KEYS}
    raw = json.dumps(values, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _hashable(value):
    """Floats runden, damit 0.6749999 und 0.675 nicht zwei Konfigurationen sind."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, (list, tuple)):
        return [_hashable(w) for w in value]
    return value


# ---------------------------------------------------------------
# Verbindung
# ---------------------------------------------------------------

def open_db(path: str | None = None) -> sqlite3.Connection:
    """Datenbank oeffnen und Schema sicherstellen. `:memory:` ist erlaubt (Tests)."""
    path = path or cfg.HISTORY_PATH
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


@contextmanager
def run_ctx(conn: sqlite3.Connection, note: str = "", timestamp: datetime | None = None):
    """Ein Lauf als Transaktion: committet erst, wenn der Block sauber durchlaeuft.

    Genau das ist "nur erfolgreiche Laeufe uebernehmen" - keine Statusspalte, die
    jemand auswerten muesste, sondern gar kein Eintrag. Eine Ausnahme im Block rollt
    auch die schon geschriebenen Item-Zeilen zurueck.
    """
    now = timestamp or datetime.now()
    cur = conn.execute(
        "INSERT INTO runs (ts, tag, code_version, config_hash, notiz) VALUES (?,?,?,?,?)",
        (now.isoformat(timespec="seconds"), now.strftime("%Y-%m-%d"),
         code_version(), config_hash(), note),
    )
    run_id = cur.lastrowid
    try:
        yield run_id
    except Exception:
        conn.rollback()
        raise
    conn.execute("UPDATE runs SET items = (SELECT COUNT(*) FROM items WHERE run_id = ?) "
                 "WHERE id = ?", (run_id, run_id))
    conn.commit()


# ---------------------------------------------------------------
# Schreiben
# ---------------------------------------------------------------

def write_items(conn: sqlite3.Connection, run_id: int, lines: list) -> int:
    """Eine Zeile je Item: Preise, Volumen, NPC-Preis, Kosten, Gold/h, Weg, Rang, Warnungen."""
    if not lines:
        return 0
    tag = _day_of_run(conn, run_id)
    data = [
        (run_id, tag) + tuple(_number(z.get(s)) if s not in ("item", "skill", "verkaufsweg", "warnungen")
                              else _text_value(z.get(s)) for s in ITEM_COLUMNS)
        for z in lines
    ]
    placeholder = ",".join("?" * (len(ITEM_COLUMNS) + 2))
    conn.executemany(
        f"INSERT INTO items (run_id, tag, {','.join(ITEM_COLUMNS)}) VALUES ({placeholder})",
        data,
    )
    return len(data)


def write_orderbook(conn: sqlite3.Connection, run_id: int, books: list,
                       top_n: int | None = None) -> int:
    """Gebots-/Angebotsstufen - nur fuer die wichtigsten Kandidaten.

    `books` ist `[{item, item_id, kauf: [(preis, menge)], verkauf: [...]}]`, bereits
    in Rangfolge. Gespeichert werden die ersten `top_n`: eine Stufe je Item und Lauf
    ist die groesste Tabelle von allen, und fuer Platz 400 der Rangliste sieht sie nie
    jemand an. Abgerufen wurden diese Buecher ohnehin schon (Sheet "Begruendung") -
    es entsteht also kein einziger zusaetzlicher Request.
    """
    limit = cfg.HISTORY_ORDERBOOK_TOP_N if top_n is None else top_n
    tag = _day_of_run(conn, run_id)
    data = []
    for book in books[:max(0, limit)]:
        for side in ("kauf", "verkauf"):
            for level, (price_value, amount_value) in enumerate(book.get(side) or [], 1):
                data.append((run_id, tag, int(book["item_id"]), _text_value(book.get("item")),
                              side, level, float(price_value), float(amount_value)))
    if data:
        conn.executemany(
            "INSERT INTO orderbook (run_id, tag, item_id, item, seite, stufe, preis, menge) "
            "VALUES (?,?,?,?,?,?,?,?)", data)
    return len(data)


# ---------------------------------------------------------------
# Aufraeumen: zusammenfassen, dann loeschen
# ---------------------------------------------------------------

def tidy_up(conn: sqlite3.Connection, today: datetime | None = None) -> dict:
    """Details verdichten und Alt-Bestand loeschen. Gibt eine Zaehlung zurueck.

    Reihenfolge ist keine Geschmacksfrage: erst zusammenfassen, dann loeschen. In der
    anderen Reihenfolge waeren die Tageswerte fuer genau die Tage leer, die man
    aufhebt - und aufgefallen waere es erst nach 90 Tagen.
    """
    today = today or datetime.now()
    limit_detail = (today - timedelta(days=cfg.HISTORY_DETAIL_DAYS)).strftime("%Y-%m-%d")
    limit_ob = (today - timedelta(days=cfg.HISTORY_ORDERBOOK_DAYS)).strftime("%Y-%m-%d")
    limit_daily = (today - timedelta(days=cfg.HISTORY_DAILY_DAYS)).strftime("%Y-%m-%d")

    condensed = condense_until(conn, limit_detail)
    gone_items = conn.execute("DELETE FROM items WHERE tag < ?", (limit_detail,)).rowcount
    gone_ob = conn.execute("DELETE FROM orderbook WHERE tag < ?", (limit_ob,)).rowcount
    gone_daily = conn.execute("DELETE FROM daily WHERE tag < ?", (limit_daily,)).rowcount
    gone_runs = _limit_runs(conn, cfg.HISTORY_RUN_LIMIT)
    conn.commit()
    return {"condensed": condensed, "items": gone_items, "orderbook": gone_ob,
            "daily": gone_daily, "runs": gone_runs}


def condense_until(conn: sqlite3.Connection, limit_day: str) -> int:
    """Alles vor `limit_day` zu einem Eintrag je Tag und Item zusammenfassen.

    Gemittelt wird ueber die Laeufe eines Tages; bei einem Lauf pro Tag ist das der
    Wert selbst. `INSERT OR REPLACE` macht den Durchgang wiederholbar - ein zweiter
    Aufruf schreibt dieselben Zahlen noch einmal, statt sie zu verdoppeln.
    """
    cur = conn.execute("""
        INSERT OR REPLACE INTO daily
            (tag, item, item_id, laeufe, bid, ask, npc_preis, kosten_h, gold_h, gold_h_real)
        SELECT tag, item, MAX(item_id), COUNT(*),
               AVG(bid), AVG(ask), AVG(npc_preis), AVG(kosten_h),
               AVG(gold_h), AVG(gold_h_real)
        FROM items WHERE tag < ? GROUP BY tag, item
    """, (limit_day,))
    return cur.rowcount


def _limit_runs(conn: sqlite3.Connection, limit: int) -> int:
    """Nur die juengsten `limit` Laufprotokolle behalten; Details haengen per CASCADE dran."""
    cur = conn.execute(
        "DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY id DESC LIMIT ?)",
        (max(1, limit),))
    return cur.rowcount


# ---------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------

def trend_rows(conn: sqlite3.Connection, item: str, days_count: int = 30) -> list:
    """Gold/h und Preise eines Items ueber die Zeit - Details und Tageswerte zusammen."""
    lines = conn.execute("""
        SELECT tag, bid, ask, npc_preis, kosten_h, gold_h, gold_h_real, 'detail' AS quelle
        FROM items WHERE item = ?
        UNION ALL
        SELECT tag, bid, ask, npc_preis, kosten_h, gold_h, gold_h_real, 'tag' AS quelle
        FROM daily WHERE item = ?
        ORDER BY tag DESC LIMIT ?
    """, (item, item, max(1, days_count))).fetchall()
    return [dict(z) for z in lines]


def last_runs(conn: sqlite3.Connection, count: int = 5) -> list:
    lines = conn.execute(
        "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (max(1, count),)).fetchall()
    return [dict(z) for z in lines]


def _day_of_run(conn: sqlite3.Connection, run_id: int) -> str:
    line = conn.execute("SELECT tag FROM runs WHERE id = ?", (run_id,)).fetchone()
    return line["tag"] if line else datetime.now().strftime("%Y-%m-%d")


def _number(value):
    """None bleibt None - eine 0 waere hier eine Behauptung."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number      # NaN faellt raus


def _text_value(value) -> str:
    return "" if value is None else str(value)
