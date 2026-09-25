"""Bedienbarkeit des Studios: Rueckgaengig, Sprungmarken, Uebersicht, Punkte, Einstieg.

Fuenf Umbauten, die alle dieselbe Sorte Luecke schliessen: die Daten wussten
etwas (wer einen Punkt benutzt, welcher Scan gemeint ist, wann zuletzt
gelaufen), und die Ansicht sagte es nicht — oder es gab keinen Weg zurueck.
"""
import csv
import os as _os
import re
import tempfile
from pathlib import Path

from ._harness import check, section, studio_web_source
from autoclicker.models import (
    AutoClickerState as _ST,
    ClickPoint as _CP,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB

_web = studio_web_source()

# ----------------------------------------------------------------------
section("Rueckgaengig im Editor: ein Abzug je Aenderung")

_sandbox = Path(tempfile.mkdtemp(prefix="bedien_"))
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    Path("sequences").mkdir(exist_ok=True)
    from autoclicker.persistence import list_available_sequences, save_sequence_file, sequence_file

    def _saved(name, steps, points):
        st = _ST()
        seq = _SEQ(name=name, loop_phases=[_PHASE(name="A", steps=steps)], points=points)
        st.active_sequence = seq
        st.points = seq.points
        save_sequence_file(seq, sequence_file(seq.name))
        return _SB(seq, dict(list_available_sequences())[name], "sequences")

    _b = _saved("Farm", [
        _STEP(x=1, y=1, point_id=1, delay_before=0),
        _STEP(x=1, y=1, point_id=1, delay_before=0),           # teilt Punkt 1
        _STEP(key_press="e", delay_before=0),
    ], [_CP(1, 1, "eins", 1), _CP(2, 2, "zwei", 2)])

    _u0 = _b.snapshot()["undo"]
    check("frisch geladen gibt es nichts zurueckzunehmen",
          _u0["can"] is False and _u0["redo"] is False and _u0["offer"] is False)

    _b.select({"phase": 1, "row": 0, "mode": "single"})
    _b.select({"phase": 1, "row": 1, "mode": "add"})
    _z = _b.selection_delete()
    check("Loeschen legt einen Abzug ab und bietet den Rueckweg an",
          _z["undo"]["can"] is True and _z["undo"]["offer"] is True
          and "gel" in _z["undo"]["what"] and len(_z["phases"][1]["blocks"]) == 1)
    _z = _b.undo()
    check("STRG+Z bringt beide Bloecke zurueck",
          len(_z["phases"][1]["blocks"]) == 3 and _z["undo"]["redo"] is True
          and _z["status"]["text"].startswith("Rückgängig"))
    check("und die Auswahl von davor gleich mit",
          _b.sel_rows == {0, 1} and _b.sel_lane is _b.board.lanes[1])
    check("der Rueckweg an der Meldung ist danach weg", _z["undo"]["offer"] is False)
    _z = _b.redo()
    check("STRG+Y loescht sie wieder",
          len(_z["phases"][1]["blocks"]) == 1 and _z["undo"]["can"] is True)
    _b.undo()

    # Der Abzug nimmt die Punkte mit: ein Block, der zurueckkommt, darf nicht
    # ins Leere zeigen.
    _b.select({"phase": 1, "row": 0, "mode": "single"})
    _b.point_detach()
    _fresh = [p.id for p in _b.points]
    _b.undo()
    check("ein Zurueck ueber point_detach nimmt den neuen Punkt wieder mit",
          [p.id for p in _b.points] == [1, 2] and len(_fresh) == 3)
    check("und die Bloecke zeigen wieder auf ihre alten Punkte",
          _b.board.lanes[1].steps[0].point_id == 1)

    # Eine gehaltene Pfeiltaste ist EIN Verschieben.
    _b.select({"phase": 1, "row": 0, "mode": "single"})
    _before = len(_b._edit_undo)
    _b.selection_move({"delta": 1})
    _b.selection_move({"delta": 1})
    check("zwei schnelle Schritte derselben Serie sind ein Abzug",
          len(_b._edit_undo) == _before + 1)
    _b.undo()
    check("und das Zurueck holt den Block an seinen Ausgangsplatz",
          _b.board.lanes[1].steps[0].point_id == 1)

    # Nur bei echter Aenderung: eine abgelehnte Eingabe legt nichts ab.
    _before = len(_b._edit_undo)
    _b.block_set({"field": "gibt_es_nicht", "value": 1})
    check("ein abgelehntes Feld legt keinen Abzug ab", len(_b._edit_undo) == _before)

    # Speichern leert den Stapel.
    _b.save()
    _u = _b.snapshot()["undo"]
    check("nach dem Speichern ist der Stapel leer", _u["can"] is False and _u["redo"] is False)
    check("Zurueck ohne Stapel ist eine Meldung, kein Fehler",
          _b.undo()["status"]["kind"] == "info")

    # Die Ansicht: Knoepfe, Tasten, Meldung.
    check("Zurueck und Wieder stehen im Kopf",
          'id="btn-undo"' in _web and 'id="btn-redo"' in _web
          and 'call("undo")' in _web and 'call("redo")' in _web)
    check("STRG+Z und STRG+Y sind im Editor belegt",
          'e.key.toLowerCase() === "y"' in _web
          and 'call(e.shiftKey ? "redo" : "undo")' in _web)
    check("und die Meldung traegt den Rueckweg", 'id="status-action"' in _web
          and '$("status-action").hidden = !(u.can && u.offer)' in _web)

    # ------------------------------------------------------------------
    section("Sprungmarken: jeder Befund traegt sein Ziel")

    from autoclicker.diagnostics import CheckReport as _CR, Finding as _F, check_setup as _cs
    check("ein Befund hat ein Ziel-Feld, und es darf leer bleiben",
          _F("error", "x", "y").target is None)
    _r = _CR()
    _r.add_finding("error", "a", "b", target={"view": "scans"})
    check("add_finding reicht das Ziel durch", _r.findings[0].target == {"view": "scans"})

    from autoclicker.models import ItemScanConfig as _ISC
    _st = _ST()
    _seq = _SEQ(name="Farm", loop_phases=[_PHASE(name="A", steps=[
        _STEP(x=1, y=1, point_id=99, delay_before=0),            # toter Punkt
        _STEP(item_scan="fehlt", delay_before=0),                # toter Scan
    ])], points=[_CP(1, 1, "p", 1)])
    _st.active_sequence = _seq
    _st.points = _seq.points
    save_sequence_file(_seq, sequence_file(_seq.name))
    _st.item_scans["Inventar"] = _ISC(name="Inventar")           # ohne Slots
    _rep = _cs(_st)
    _by_text = {b.text: b for b in _rep.findings}
    _scan = next((b for b in _rep.findings if b.area == "Item-Scan 'Inventar'"), None)
    check("ein Scan ohne Slot zeigt in den Scans-Reiter",
          _scan is not None
          and _scan.target == {"view": "scans", "kind": "item", "name": "Inventar"})
    _dead_point = next((b for b in _rep.findings if "Punkt #99" in b.text), None)
    check("ein toter Punkt-Verweis zeigt auf seinen Block (Lane 1, Zeile 0)",
          _dead_point is not None
          and _dead_point.target == {"view": "editor", "sequence": "Farm",
                                     "phase": 1, "row": 0})
    _dead_scan = next((b for b in _rep.findings if "item_scan 'fehlt'" in b.text), None)
    check("ein toter Scan-Verweis zeigt auf seinen Block (Zeile 1)",
          _dead_scan is not None and _dead_scan.target["row"] == 1)

    _bt = _SB(_seq, dict(list_available_sequences())["Farm"], "sequences")
    _tc = _bt.tool_check()
    check("der Werkzeuge-Reiter reicht das Ziel durch",
          _tc["ok"] and any(b.get("target") for b in _tc["findings"]))
    check("und die Seite baut daraus einen Sprungknopf",
          "jumpButton(t, where)" in _web and "async function goTo(t)" in _web)

    # Bericht: der Timeout-Name wird gegen die offene Sequenz aufgeloest.
    _bt.board.lanes[1].steps[0].name = "Bank oeffnen"
    _targets = _bt._report_targets({"timeouts": [("Bank oeffnen", 2), ("A[2]", 1),
                                                 ("Unbekannt", 1)]})
    check("ein Timeout-Name findet seinen Block ueber den Namen",
          _targets.get("Bank oeffnen") == {"view": "editor", "sequence": "Farm",
                                           "phase": 1, "row": 0})
    check("und ohne Namen ueber Phase[n]", _targets.get("A[2]", {}).get("row") == 1)
    check("was es nicht gibt, bekommt kein erfundenes Ziel", "Unbekannt" not in _targets)
    check("die Rangzeile oeffnet den Block", 'jumpButton(target, "Block öffnen")' in _web
          and "(B.targets || {})[name]" in _web)
    check("die Warnmarke auf der Karte ist eine Sprungmarke",
          'class: "badge-small warn jump"' in _web and "focus: 'select[data-key=\"scan\"]'" in _web
          and "if (key) s.dataset.key = key;" in _web)

    # ------------------------------------------------------------------
    section("Uebersicht: letzter Lauf, Duplizieren, Plural")

    from autoclicker.config import CONFIG
    _old_dir = CONFIG.session_log_dir
    CONFIG.session_log_dir = "logs"
    Path("logs").mkdir(exist_ok=True)
    _cols = ["timestamp", "elapsed_sec", "event", "detail", "x", "y", "extra"]
    with open(Path("logs") / "2026-01-02_000000_farm.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(_cols)
        w.writerows([("2026-01-02 00:00:00", 0, "session_start", "Farm", "", "", ""),
                     ("2026-01-02 00:00:01", 1, "click", "Bank", 10, 20, ""),
                     ("2026-01-02 00:00:03", 3, "timeout", "Bank oeffnen", "", "", ""),
                     ("2026-01-02 00:30:00", 1800, "session_end", "Farm", "", "", "")])
    try:
        _lst = _bt.sequence_list()
        _farm = next(s for s in _lst if s["name"] == "Farm")
        check("die Karte kennt den letzten Lauf",
              _farm["last_run"] is not None and _farm["last_run"]["duration"] == 1800.0
              and _farm["last_run"]["clicks"] == 1 and _farm["last_run"]["timeouts"] == 1)
        check("und seinen Beginn als Zeitstempel",
              isinstance(_farm["last_run"]["begin"], float) and _farm["last_run"]["begin"] > 0)
        _dup = _bt.sequence_duplicate({"name": "Farm"})
        check("Duplizieren kopiert den Ordner unter einem freien Namen",
              _dup["ok"] and _dup["name"] == "Farm 2"
              and (Path("sequences") / "farm_2" / "sequence.json").exists())
        _names = {s["name"] for s in _bt.sequence_list()}
        check("und die Kopie traegt den neuen Namen in der Datei", "Farm 2" in _names)
        check("eine Sequenz ohne Log hat keinen letzten Lauf",
              next(s for s in _bt.sequence_list() if s["name"] == "Farm 2")["last_run"] is None)
        check("was es nicht gibt, laesst sich nicht kopieren",
              _bt.sequence_duplicate({"name": "Nix"})["ok"] is False)

        # **Die Uebersicht parst nur, was sich geaendert hat.** Sie wird bei
        # jedem Oeffnen des Reiters neu gezeichnet und lud dafuer jede Sequenz
        # vollstaendig — samt Migration, Punkt-Aufloesung und Konsolen-Warnzeilen.
        import autoclicker.editors.sequence_studio.bridge_services as _bsv
        import time as _time_u
        _loads = []
        _orig_lsf = _bsv.load_sequence_file
        _bsv.load_sequence_file = lambda path: _loads.append(str(path)) or _orig_lsf(path)
        try:
            _bt._sequence_facts_cache.clear()          # kalt anfangen, wie beim Oeffnen
            _bt.sequence_list()
            _first = len(_loads)
            _bt.sequence_list()
            check("ein zweites Zeichnen liest keine Sequenzdatei erneut",
                  _first >= 2 and len(_loads) == _first)
            _farm_file = Path("sequences") / "farm" / "sequence.json"
            _time_u.sleep(0.02)
            _farm_file.write_text(
                _farm_file.read_text(encoding="utf-8").replace('"name": "Farm"',
                                                               '"name": "Farm neu"'),
                encoding="utf-8")
            _names_after = {s["name"] for s in _bt.sequence_list()}
            check("eine geaenderte Datei wird neu gelesen — und nur die",
                  "Farm neu" in _names_after and len(_loads) == _first + 1)
        finally:
            _bsv.load_sequence_file = _orig_lsf
    finally:
        CONFIG.session_log_dir = _old_dir
    check("'1 Zyklen' gibt es nicht mehr",
          '" Zyklus" : " Zyklen"' in _web and 's.cycles + " Zyklen"' not in _web)
    check("Filter und Ordnung stehen ueber der Liste",
          'class: "seq-toolbar"' in _web and "function seqSorted" in _web)
    check("das Datum steht als Spanne mit dem Stempel im Tooltip",
          "function sinceText" in _web and "title: timestamp(s.changed)" in _web)

    # ------------------------------------------------------------------
    section("Punkte-Liste: Verwendung, ungenutzt, Sprung")

    _pb = _saved("Punkte", [
        _STEP(x=1, y=1, point_id=1, delay_before=0),
        _STEP(x=1, y=1, point_id=1, delay_before=0),
    ], [_CP(1, 1, "oft", 1), _CP(9, 9, "nie", 2)])
    _pts = {p["id"]: p for p in _pb.snapshot()["points"]}
    check("jeder Punkt kennt seine Verwendungen", _pts[1]["usages"] == 2 and _pts[2]["usages"] == 0)
    check("jeder Block kennt seine Punkte",
          _pb.snapshot()["phases"][1]["blocks"][0]["points"] == [1])
    _pr = _pb.tool_points_prune()
    check("ungenutzte Punkte gehen in einem Griff",
          _pr["ok"] and _pr["count"] == 1 and [p.id for p in _pb.points] == [1])
    check("nochmal gibt es nichts zu tun", "nichts zu tun" in _pb.tool_points_prune()["message"])
    _pb.undo()
    check("benutzte bleiben, und STRG+Z holt die anderen zurueck",
          [p.id for p in _pb.points] == [1, 2])
    check("die Zeile zeigt den Zaehler, die Geste steht dran",
          'class: "uses"' in _web and 'class: "points-hint"' in _web
          and 'id="points-unused"' in _web)
    check("ein Klick markiert die Bloecke des Punkts",
          "pointHighlight" in _web and '" uses-point"' in _web
          and "function selectedPoints" in _web)
    check("'ungenutzt' ist ein Filterwort", 'filter === "ungenutzt"' in _web)
    check("und das Werkzeug hat den Sammelknopf", 'callTool("tool_points_prune")' in _web)

    # ------------------------------------------------------------------
    section("Einstieg und Tastenkuerzel")

    check("ein leeres Board zeigt die Einstiegskarte",
          "function startCard" in _web
          and "if (!S.phases.some((phase) => phase.blocks.length)) target.appendChild(startCard());"
          in _web)
    check("sie nennt beide Wege und den Import",
          'wzOpen("recording")' in _web and '"Ersten Block anlegen"' in _web
          and 'setView("share")' in _web)
    check("die Tafel gibt es, mit Taste und Knopf",
          'id="shortcuts"' in _web and 'e.key === "?"' in _web and 'id="btn-help"' in _web)
    # Eine Quelle: die Buchstaben der Scan-Modi kommen aus SCAN_MODES, nicht
    # abgetippt — und jedes Kuerzel, das keyboard() liest, steht in der Tafel.
    check("die Scan-Modi nehmen ihre Buchstaben aus SCAN_MODES",
          'SCAN_MODES.map((m) => m.shortcut)' in _web)
    _table = _web[_web.index("function shortcutTable"):_web.index("function toggleShortcuts")]
    _keyboard = _web[_web.index("function keyboard(e)"):]
    _used = set(re.findall(r'e\.key(?:\.toLowerCase\(\))? === "(\w+)"', _keyboard))
    _named = {"s": "STRG S", "z": "STRG Z", "y": "STRG Y", "d": "STRG D", "t": "T",
              "Delete": "ENTF", "Escape": "ESC", "ArrowUp": "ALT ↑", "ArrowDown": "ALT ↓"}
    _missing = [k for k in _used if k in _named and _named[k] not in _table]
    check(f"jedes Kuerzel aus keyboard() steht in der Tafel ({_missing or 'alle'})",
          not _missing)
    check("ESC schliesst die Tafel zuerst",
          'if (!$("shortcuts").hidden) return toggleShortcuts(false);' in _web)
finally:
    _os.chdir(_cwd)
    import shutil as _sh
    _sh.rmtree(_sandbox, ignore_errors=True)
