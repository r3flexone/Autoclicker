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

_sandbox = Path(tempfile.mkdtemp(prefix="seqloesch_"))
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    Path("sequences").mkdir(exist_ok=True)
    from autoclicker.persistence import (
        list_available_sequences, save_data, save_item_scan, sequence_dir,
        sequence_templates_dir,
    )

    def _create(name):
        st = _ST()
        seq = _SEQ(name=name, loop_phases=[_PHASE(name="A", steps=[_STEP(point_id=1)])],
                   points=[_CP(id=1, x=10, y=20)])
        st.sequences[name] = seq
        st.active_sequence = seq
        st.points = seq.points
        save_data(st)
        return seq

    _farm = _create("Farm")
    _raid = _create("Raid")
    # An „Raid" haengt mehr als die JSON — genau das soll die Rueckfrage nennen.
    save_item_scan(_ISC(name="Inventar", owner_sequence="Raid",
                        slots=[_SLOT(name="Slot 1", scan_region=(0, 0, 10, 10), click_pos=(5, 5))],
                        items=[_ITEM(name="Erz")]))
    # **Der Ordner heisst nicht wie die Sequenz.** `sanitize_filename()` macht
    # aus „Raid" das Verzeichnis `sequences/raid` — die Pfade kommen deshalb aus
    # der Persistenz und werden nicht aus dem Anzeigenamen zusammengehaengt.
    # Genau dieser Unterschied war der Fehler: `sequence_delete()` hing den
    # angezeigten Namen an `sequences/` und griff daneben.
    _folder_raid = sequence_dir("Raid")
    check("der Ordner traegt den bereinigten Namen, nicht den angezeigten",
          _folder_raid.name == "raid" and _folder_raid.is_dir())
    _templates = sequence_templates_dir("Raid")
    _templates.mkdir(parents=True, exist_ok=True)
    (_templates / "erz.png").write_bytes(b"x")
    (_templates / "holz.png").write_bytes(b"x")
    # Der Stolperstein selbst: ein Ordner, der so heisst wie die Sequenz — und
    # der gerade NICHT gemeint ist.
    #
    # **Ob es ihn ueberhaupt geben kann, entscheidet das Dateisystem.** Auf einem
    # case-insensitiven (Windows, macOS) IST `sequences/Raid` derselbe Ordner wie
    # `sequences/raid` — genau deshalb blieb der Fehler dort unsichtbar, waehrend
    # die Ubuntu-Jobs rot standen. Gefragt wird deshalb das Dateisystem und nicht
    # `sys.platform`: auch Windows kann case-sensitive Verzeichnisse haben.
    # Geprueft werden beide Seiten — auf der einen bleibt der Fremdordner stehen,
    # auf der anderen ist er der echte und muss mitgewandert sein.
    _falle = Path("sequences/Raid")
    _falle.mkdir(parents=True, exist_ok=True)
    (_falle / "nicht_gemeint.txt").write_bytes(b"x")
    _falle_eigen = not _os.path.samefile(_falle, _folder_raid)

    _b = _SB(_farm, dict(list_available_sequences())["Farm"], "sequences")
    _b._running = lambda: False          # kein echter Lauf in der Testumgebung

    _list = {e["name"]: e for e in _b.sequence_list()}
    check("beide Sequenzen stehen in der Uebersicht", set(_list) == {"Farm", "Raid"})
    _extent = {u["kind"]: u["count"] for u in _list["Raid"]["scope"]}
    check("der Umfang nennt die Scans", _extent.get("item_scans") == 1)
    check("und die Vorlagen", _extent.get("templates") == 2)
    check("eine Sequenz ohne Beiwerk hat keinen Umfang", _list["Farm"]["scope"] == [])
    # **Die Mehrzahl steht fertig in den Daten.** Die Ansicht haengte erst ein
    # "n" an — das ergibt "Vorlagen" und "Item-Scann". Bei drei von fuenf
    # Woertern falsch, und aufgefallen ist es erst am gerenderten Dialog.
    _words = {u["kind"]: u["word"] for u in _list["Raid"]["scope"]}
    check("bei einem bleibt die Einzahl", _words.get("item_scans") == "Item-Scan")
    check("bei mehreren steht die richtige Mehrzahl",
          _words.get("templates") == "Vorlagen")
    from autoclicker.editors.sequence_studio.bridge_services import BridgeServicesMixin
    check("kein Wort entsteht durch ein angehaengtes n",
          all(many != one_item + "n" or one_item.endswith("e")
              for _, one_item, many in BridgeServicesMixin._EXTENT))

    # --- Die offene Sequenz nicht ------------------------------------------
    _z = _b.sequence_delete({"name": "Farm"})
    check("die offene Sequenz wird abgelehnt", _z["ok"] is False)
    check("und die Absage sagt, warum", "geöffnet" in _z["message"])
    check("der Ordner steht noch", sequence_dir("Farm").is_dir())

    # --- Waehrend eines Laufs nicht ----------------------------------------
    _b._running = lambda: True
    _z = _b.sequence_delete({"name": "Raid"})
    check("waehrend eines Laufs wird abgelehnt", _z["ok"] is False)
    check("der Ordner steht auch dann noch", _folder_raid.is_dir())
    _b._running = lambda: False

    # --- Der Normalfall -----------------------------------------------------
    _z = _b.sequence_delete({"name": "Raid"})
    check("eine fremde Sequenz laesst sich loeschen", _z["ok"] is True)
    check("der Ordner ist weg", not _folder_raid.exists())
    # **Verschoben, nicht entfernt.** Alles muss mit — die Vorlagen sind der
    # Teil, den man am wenigsten wiederherstellen kann. Die Struktur ist
    # gespiegelt (wie bei `backup_path()`), also steht dort der ORDNERname.
    _bak = Path("backups/sequences") / _folder_raid.name
    check("er liegt unter backups/", _bak.is_dir())
    check("samt sequence.json", (_bak / "sequence.json").exists())
    check("samt Item-Scan", (_bak / "item_scans").is_dir())
    check("und samt Vorlagen",
          sorted(p.name for p in (_bak / "templates").iterdir()) == ["erz.png", "holz.png"])
    check("die Uebersicht zeigt sie nicht mehr",
          [e["name"] for e in _b.sequence_list()] == ["Farm"])
    if _falle_eigen:
        check("der gleichnamige Fremdordner bleibt unangetastet",
              (_falle / "nicht_gemeint.txt").exists())
    else:
        check("ohne Gross-/Kleinunterschied ist er der echte und wandert mit",
              (_bak / "nicht_gemeint.txt").exists() and not _falle.exists())

    # --- Zweimal derselbe Name ueberschreibt die Sicherung nicht -----------
    _create("Raid")
    _b.sequence_delete({"name": "Raid"})
    _stände = sorted(p.name for p in Path("backups/sequences").iterdir())
    check("eine zweite Sicherung bekommt einen Zeitstempel", len(_stände) == 2)
    check("und die erste bleibt die erste", _folder_raid.name in _stände)

    # --- Was es nicht gibt ---------------------------------------------------
    _z = _b.sequence_delete({"name": "Gibtsnicht"})
    check("ein unbekannter Name ist eine Absage, kein Absturz", _z["ok"] is False)
    _z = _b.sequence_delete({})
    check("ohne Namen passiert nichts", _z["ok"] is False)
    # `name` kommt aus dem Fenster. Zusammengehaengt fuehrte ein `..` aus
    # `sequences/` heraus; ueber die Eintragsliste gibt es den Pfad gar nicht.
    _z = _b.sequence_delete({"name": "../sequences"})
    check("ein Pfad im Namen greift ins Leere", _z["ok"] is False)
    check("und der Sequenzordner steht noch", Path("sequences").is_dir())
finally:
    _os.chdir(_cwd)
    import shutil as _sh
    _sh.rmtree(_sandbox, ignore_errors=True)


# --- Die Verdrahtung in der Ansicht ---------------------------------------
# **Ein Loeschen ohne Rueckfrage waere der einzige Weg im Studio, auf dem ein
# Klick einen Ordner nimmt.** Der Knopf muss also ueber den Dialog gehen, und
# der Dialog muss den Fall kennen — fehlt einer der beiden Teile, passiert
# entweder nichts oder zu viel.
_karte = _web[_web.index("function seqCard"):_web.index("function askDelete")]
check("die Karte hat einen Loeschen-Knopf", '"Löschen"' in _karte)
check("und er geht ueber die Rueckfrage, nicht direkt an die Bruecke",
      "askDelete(s)" in _karte and 'sequence_delete' not in _karte)
check("die offene Sequenz laesst sich nicht loeschen — auch nicht im Knopf",
      re.search(r'class: "btn danger quiet", disabled: s\.open', _karte) is not None)
# Gleiche Spalten: zwei verschieden breite Knoepfe nebeneinander lesen sich als
# zwei Rangstufen. Dieselbe Klasse wie ueberall sonst, kein drittes Muster.
check("beide Knoepfe teilen sich gleiche Spalten",
      'el("div", {class: "button-pair"}' in _karte)
check("und die Klasse ist auch gestaltet", ".seq-footer .button-pair{" in _web)
_forts = _web[_web.index("async function proceed"):_web.index("Ansicht: Scans")]
check("der Dialog kennt den Loesch-Fall", 'open.kind === "seq_delete"' in _forts)
check("und ruft die Bruecke ueber den fragenden Kanal",
      'ask("sequence_delete"' in _forts)
check("danach wird die Uebersicht neu gezeichnet",
      "renderSequenceList()" in _forts)
# Die lokale Variable hiess `ask` und verdeckte den gleichnamigen Helfer.
check("die lokale Variable verdeckt den Bruecken-Helfer nicht mehr",
      "const ask = openQuestion" not in _web)
