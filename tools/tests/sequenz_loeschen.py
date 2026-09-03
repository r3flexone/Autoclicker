"""Sequenzen-Reiter: löschen mit Rückfrage — und nach `backups/`, nicht ins Nichts.

Eine Sequenz ist eine **Besitzeinheit**: Punkte stehen in ihrer `sequence.json`,
Scans, Vorlagen und gemerkte Bildschirme liegen daneben im selben Ordner. Nur die
JSON zu entfernen liesse einen Ordner voller Vorlagen zurück, den nie wieder
jemand ansieht — deshalb geht der ganze Ordner, und deshalb sagt die Rückfrage,
was daran hängt.

Zwei Absagen gehören dazu und werden hier gemessen: die offene Sequenz (der
nächste Druck auf Speichern legte den Ordner wieder an) und ein laufender Lauf
(der Worker liest gerade aus diesen Ordnern).
"""
import os as _os
import re
import tempfile
from pathlib import Path

from ._harness import check, section, studio_web_source
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.models import (
    AutoClickerState as _ST, ClickPoint as _CP, ItemProfile as _ITEM,
    ItemScanConfig as _ISC, ItemSlot as _SLOT, LoopPhase as _PHASE,
    Sequence as _SEQ, SequenceStep as _STEP,
)

_web = studio_web_source()

section("Sequenzen-Reiter: loeschen mit Rueckfrage")

_sand = Path(tempfile.mkdtemp(prefix="seqloesch_"))
_cwd = _os.getcwd()
_os.chdir(_sand)
try:
    Path("sequences").mkdir(exist_ok=True)
    from autoclicker.persistence import (
        list_available_sequences, save_data, save_item_scan,
    )

    def _anlegen(name):
        st = _ST()
        seq = _SEQ(name=name, loop_phases=[_PHASE(name="A", steps=[_STEP(point_id=1)])],
                   points=[_CP(id=1, x=10, y=20)])
        st.sequences[name] = seq
        st.active_sequence = seq
        st.points = seq.points
        save_data(st)
        return seq

    _farm = _anlegen("Farm")
    _raid = _anlegen("Raid")
    # An „Raid" haengt mehr als die JSON — genau das soll die Rueckfrage nennen.
    save_item_scan(_ISC(name="Inventar", owner_sequence="Raid",
                        slots=[_SLOT(name="Slot 1", scan_region=(0, 0, 10, 10), click_pos=(5, 5))],
                        items=[_ITEM(name="Erz")]))
    (Path("sequences/Raid/templates")).mkdir(parents=True, exist_ok=True)
    (Path("sequences/Raid/templates/erz.png")).write_bytes(b"x")
    (Path("sequences/Raid/templates/holz.png")).write_bytes(b"x")

    _b = _SB(_farm, dict(list_available_sequences())["Farm"], "sequences")
    _b._laeuft = lambda: False          # kein echter Lauf in der Testumgebung

    _liste = {e["name"]: e for e in _b.sequenz_liste()}
    check("beide Sequenzen stehen in der Uebersicht", set(_liste) == {"Farm", "Raid"})
    _umfang = {u["art"]: u["anzahl"] for u in _liste["Raid"]["umfang"]}
    check("der Umfang nennt die Scans", _umfang.get("item_scans") == 1)
    check("und die Vorlagen", _umfang.get("templates") == 2)
    check("eine Sequenz ohne Beiwerk hat keinen Umfang", _liste["Farm"]["umfang"] == [])
    # **Die Mehrzahl steht fertig in den Daten.** Die Ansicht haengte erst ein
    # "n" an — das ergibt "Vorlagen" und "Item-Scann". Bei drei von fuenf
    # Woertern falsch, und aufgefallen ist es erst am gerenderten Dialog.
    _woerter = {u["art"]: u["wort"] for u in _liste["Raid"]["umfang"]}
    check("bei einem bleibt die Einzahl", _woerter.get("item_scans") == "Item-Scan")
    check("bei mehreren steht die richtige Mehrzahl",
          _woerter.get("templates") == "Vorlagen")
    from autoclicker.editors.sequence_studio.bridge_services import BridgeServicesMixin
    check("kein Wort entsteht durch ein angehaengtes n",
          all(viele != eins + "n" or eins.endswith("e")
              for _, eins, viele in BridgeServicesMixin._UMFANG))

    # --- Die offene Sequenz nicht ------------------------------------------
    _z = _b.sequenz_loeschen({"name": "Farm"})
    check("die offene Sequenz wird abgelehnt", _z["ok"] is False)
    check("und die Absage sagt, warum", "geöffnet" in _z["meldung"])
    check("der Ordner steht noch", Path("sequences/Farm").is_dir())

    # --- Waehrend eines Laufs nicht ----------------------------------------
    _b._laeuft = lambda: True
    _z = _b.sequenz_loeschen({"name": "Raid"})
    check("waehrend eines Laufs wird abgelehnt", _z["ok"] is False)
    check("der Ordner steht auch dann noch", Path("sequences/Raid").is_dir())
    _b._laeuft = lambda: False

    # --- Der Normalfall -----------------------------------------------------
    _z = _b.sequenz_loeschen({"name": "Raid"})
    check("eine fremde Sequenz laesst sich loeschen", _z["ok"] is True)
    check("der Ordner ist weg", not Path("sequences/Raid").exists())
    # **Verschoben, nicht entfernt.** Alles muss mit — die Vorlagen sind der
    # Teil, den man am wenigsten wiederherstellen kann.
    _bak = Path("backups/sequences/Raid")
    check("er liegt unter backups/", _bak.is_dir())
    check("samt sequence.json", (_bak / "sequence.json").exists())
    check("samt Item-Scan", (_bak / "item_scans").is_dir())
    check("und samt Vorlagen",
          sorted(p.name for p in (_bak / "templates").iterdir()) == ["erz.png", "holz.png"])
    check("die Uebersicht zeigt sie nicht mehr",
          [e["name"] for e in _b.sequenz_liste()] == ["Farm"])

    # --- Zweimal derselbe Name ueberschreibt die Sicherung nicht -----------
    _anlegen("Raid")
    _b.sequenz_loeschen({"name": "Raid"})
    _stände = sorted(p.name for p in Path("backups/sequences").iterdir())
    check("eine zweite Sicherung bekommt einen Zeitstempel", len(_stände) == 2)
    check("und die erste bleibt die erste", "Raid" in _stände)

    # --- Was es nicht gibt ---------------------------------------------------
    _z = _b.sequenz_loeschen({"name": "Gibtsnicht"})
    check("ein unbekannter Name ist eine Absage, kein Absturz", _z["ok"] is False)
    _z = _b.sequenz_loeschen({})
    check("ohne Namen passiert nichts", _z["ok"] is False)
finally:
    _os.chdir(_cwd)
    import shutil as _sh
    _sh.rmtree(_sand, ignore_errors=True)


# --- Die Verdrahtung in der Ansicht ---------------------------------------
# **Ein Loeschen ohne Rueckfrage waere der einzige Weg im Studio, auf dem ein
# Klick einen Ordner nimmt.** Der Knopf muss also ueber den Dialog gehen, und
# der Dialog muss den Fall kennen — fehlt einer der beiden Teile, passiert
# entweder nichts oder zu viel.
_karte = _web[_web.index("function seqKarte"):_web.index("function frageLoeschen")]
check("die Karte hat einen Loeschen-Knopf", '"Löschen"' in _karte)
check("und er geht ueber die Rueckfrage, nicht direkt an die Bruecke",
      "frageLoeschen(s)" in _karte and 'sequenz_loeschen' not in _karte)
check("die offene Sequenz laesst sich nicht loeschen — auch nicht im Knopf",
      re.search(r'class: "btn gefahr still", disabled: s\.offen', _karte) is not None)
# Gleiche Spalten: zwei verschieden breite Knoepfe nebeneinander lesen sich als
# zwei Rangstufen. Dieselbe Klasse wie ueberall sonst, kein drittes Muster.
check("beide Knoepfe teilen sich gleiche Spalten",
      'el("div", {class: "knopfpaar"}' in _karte)
check("und die Klasse ist auch gestaltet", ".seq-fuss .knopfpaar{" in _web)
_forts = _web[_web.index("async function fortfahren"):_web.index("Ansicht: Scans")]
check("der Dialog kennt den Loesch-Fall", 'offen.art === "seq_loeschen"' in _forts)
check("und ruft die Bruecke ueber den fragenden Kanal",
      'frage("sequenz_loeschen"' in _forts)
check("danach wird die Uebersicht neu gezeichnet",
      "zeichneSequenzenliste()" in _forts)
# Die lokale Variable hiess `frage` und verdeckte den gleichnamigen Helfer.
check("die lokale Variable verdeckt den Bruecken-Helfer nicht mehr",
      "const frage = offeneFrage" not in _web)
