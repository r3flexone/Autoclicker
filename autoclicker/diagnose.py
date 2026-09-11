"""Selbstdiagnose: was ist kaputt, BEVOR die Sequenz läuft.

Die häufigste Frustration ist "ich starte, und es passiert das Falsche". Die meisten
Ursachen dafür sind statisch prüfbar — und die Prüfungen gab es auch schon, nur verstreut
über die Laufzeit und erst dann, wenn es zu spät war: eine Meldung in
`resolve_point_references()`, eine in `resolve_scan_references()`, eine Warnung im
Boss-Scan. Hier laufen sie an einer Stelle und auf Zuruf.

Zwei Aufrufer:
- `main.py` beim Start — nur die billigen Prüfungen (kein Datei-Scan), und **still, wenn
  nichts zu melden ist**. Dieselbe Regel wie beim Migrations-Durchgang: der Normalfall
  kostet kein Wort.
- Punkte-Menü (`CTRL+ALT+P` → `check`) — alles, inklusive der Sequenzdateien.

Der Unterschied ist bewusst: die Sequenzprüfung muss jede Sequenzdatei laden. Auf Zuruf
ist das in Ordnung, bei jedem Programmstart wäre es eine Bremse, die niemand bestellt hat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .models import AutoClickerState
from .persistence import sequence_templates_dir
from .utils import col, err, hint, info, ok, warn
from .winapi import get_virtual_desktop

# Ab wie vielen gleichartigen Befunden nur noch gezählt statt aufgezählt wird.
_MAX_EINZELN = 8

STUFE_FEHLER = "fehler"     # läuft so nicht (oder tut garantiert das Falsche)
STUFE_HINWEIS = "hinweis"   # läuft, ist aber vermutlich nicht gewollt


@dataclass
class Befund:
    """Ein Prüfergebnis: wo, was, und was man dagegen tut."""
    stufe: str
    bereich: str
    text: str
    tipp: str = ""


@dataclass
class Pruefbericht:
    befunde: list[Befund] = field(default_factory=list)
    geprueft: list[str] = field(default_factory=list)

    def melde(self, stufe: str, bereich: str, text: str, tipp: str = "") -> None:
        self.befunde.append(Befund(stufe, bereich, text, tipp))

    @property
    def fehler(self) -> list[Befund]:
        return [b for b in self.befunde if b.stufe == STUFE_FEHLER]

    @property
    def hinweise(self) -> list[Befund]:
        return [b for b in self.befunde if b.stufe == STUFE_HINWEIS]

    def __bool__(self) -> bool:
        """True = es gibt etwas zu melden."""
        return bool(self.befunde)


# ---------------------------------------------------------------------------
# Einzelprüfungen
# ---------------------------------------------------------------------------

def _pruefe_templates(state: AutoClickerState, bericht: Pruefbericht) -> None:
    """Jedes referenzierte Template-PNG muss auf Platte liegen.

    Fehlt es, meldet das Matching still `(False, 0.0, None)` — das Item wird nie erkannt,
    und die einzige Spur ist eine Logger-Zeile im Rauschen.
    """
    with state.lock:
        owner = state.active_sequence.name if state.active_sequence else ""
        quellen = [(f"Item '{i.name}' (Scan '{scan.name}')", tpl)
                   for scan in state.item_scans.values() for i in scan.items
                   for tpl in i.template_names()]
        for scan in state.boss_scans.values():
            quellen += [(f"Boss '{b.name}' (Scan '{scan.name}')", b.template)
                        for b in scan.bosses]
        quellen += [(f"Boss '{b.name}' (Bibliothek)", b.template)
                    for b in state.global_bosses]
        quellen += [(f"Icon-Scan '{c.name}'", c.template)
                    for c in state.icon_scans.values()]

    template_ordner = sequence_templates_dir(owner) if owner else Path("sequences")
    fehlend = [(wer, tpl) for wer, tpl in quellen
               if tpl and not (template_ordner / tpl).exists()]
    bericht.geprueft.append(f"{sum(1 for _, t in quellen if t)} Template-Verweise")
    for wer, tpl in fehlend:
        bericht.melde(STUFE_FEHLER, wer,
                      f"Template '{tpl}' fehlt in {template_ordner}/",
                      "Template neu aufnehmen oder den Verweis entfernen")


def _pruefe_erkennung(state: AutoClickerState, bericht: Pruefbericht) -> None:
    """Ein Profil ohne Template UND ohne Marker wird nie erkannt.

    `_check_profile_match` gibt in dem Fall immer False zurück — der Scan läuft, findet
    nichts, und nichts sagt warum. Der stillste Fehler im ganzen Programm.
    """
    with state.lock:
        kandidaten = []
        for scan in state.boss_scans.values():
            kandidaten += [(f"Boss '{b.name}' (Scan '{scan.name}')", b) for b in scan.bosses]
        kandidaten += [(f"Boss '{b.name}' (Bibliothek)", b) for b in state.global_bosses]
        kandidaten += [(f"Icon-Scan '{c.name}'", c) for c in state.icon_scans.values()]
        items = [(f"Item '{i.name}' (Scan '{scan.name}')", i)
                 for scan in state.item_scans.values() for i in scan.items]

    for wer, profil in kandidaten:
        if not profil.template and not profil.marker_colors:
            bericht.melde(STUFE_FEHLER, wer,
                          "weder Template noch Farb-Marker — wird nie erkannt",
                          "Template aufnehmen oder Marker-Farben setzen")
    for wer, item in items:
        if not item.template_names() and not item.marker_colors:
            bericht.melde(STUFE_HINWEIS, wer,
                          "weder Template noch Farb-Marker — wird in keinem Scan gefunden")
    bericht.geprueft.append(f"{len(kandidaten) + len(items)} Erkennungs-Profile")


def _pruefe_scan_referenzen(state: AutoClickerState, bericht: Pruefbericht) -> None:
    """Ein eigenständiger Scan braucht mindestens Slots und Erkennung."""
    with state.lock:
        scans = list(state.item_scans.values())

    for cfg in scans:
        if not cfg.slots:
            bericht.melde(STUFE_FEHLER, f"Item-Scan '{cfg.name}'",
                          "kein einziger Slot — der Scan kann nichts absuchen")
        elif not any(slot.enabled for slot in cfg.slots):
            bericht.melde(STUFE_FEHLER, f"Item-Scan '{cfg.name}'",
                          "kein Slot ist eingeschaltet — der Scan kann nichts absuchen")
        if not any(item.enabled for item in cfg.items) and not cfg.learn_unknown:
            bericht.melde(STUFE_HINWEIS, f"Item-Scan '{cfg.name}'",
                          "keine aktiven Items und kein Auto-Lernen — findet nie etwas")
    bericht.geprueft.append(f"{len(scans)} Item-Scan(s)")

    # **`default_scan` ist die fünfte Referenz auf einen Scan-Namen** — und die
    # einzige, die nicht in einem Schritt steht, sondern in einer Boss-Scan-Datei.
    # `_pruefe_sequenzen()` sieht deshalb nur die vier im Schritt; diese fiel
    # durch, obwohl `runtime/steps.py` sie bei „kein Boss erkannt" wirklich
    # ausführt: `execute_item_scan(state, config.default_scan)`. Zeigt sie ins
    # Leere, tut der Fallback nichts und sagt es nicht.
    with state.lock:
        boss_scans = list(state.boss_scans.values())
    vorhanden = {cfg.name for cfg in scans}
    for cfg in boss_scans:
        if cfg.default_scan and cfg.default_scan not in vorhanden:
            bericht.melde(STUFE_HINWEIS, f"Boss-Scan '{cfg.name}'",
                          f"Fallback-Scan '{cfg.default_scan}' gibt es nicht",
                          "im Scans-Reiter einen vorhandenen Item-Scan wählen")
    if boss_scans:
        bericht.geprueft.append(f"{len(boss_scans)} Fallback-Scan-Verweis(e)")


def _pruefe_llm_ocr(state: AutoClickerState, bericht: Pruefbericht) -> None:
    """Ein Scan mit use_llm/use_ocr nützt nichts, wenn es global aus ist."""
    with state.lock:
        scans = list(state.boss_scans.values())
        llm_an = state.config.llm_enabled
        ocr_an = state.config.ocr_enabled

    for cfg in scans:
        if cfg.use_llm and not llm_an:
            bericht.melde(STUFE_HINWEIS, f"Boss-Scan '{cfg.name}'",
                          "use_llm ist an, llm_enabled global aus — LLM wird ignoriert",
                          "llm_enabled in config.json setzen oder use_llm abschalten")
        if cfg.use_ocr and not ocr_an:
            bericht.melde(STUFE_HINWEIS, f"Boss-Scan '{cfg.name}'",
                          "use_ocr ist an, ocr_enabled global aus — OCR wird ignoriert",
                          "ocr_enabled in config.json setzen oder use_ocr abschalten")


def _pruefe_koordinaten(state: AutoClickerState, bericht: Pruefbericht) -> None:
    """Punkte ausserhalb aller Monitore klicken ins Nichts."""
    rect = get_virtual_desktop()
    if rect is None:
        return
    links, oben, rechts, unten = rect
    with state.lock:
        punkte = list(state.points)
    draussen = [p for p in punkte
                if not (links <= p.x < rechts and oben <= p.y < unten)]
    bericht.geprueft.append(f"{len(punkte)} Punkt(e)")
    for p in draussen:
        bericht.melde(STUFE_FEHLER, f"Punkt #{p.id} {p.name}".strip(),
                      f"({p.x}, {p.y}) liegt ausserhalb aller Monitore "
                      f"({links},{oben})-({rechts},{unten})",
                      "Bildschirm-Layout geaendert? Punkte-Menue -> 'fix' rechnet "
                      "alle Koordinaten aus einem neu gesetzten Punkt um")


def _pruefe_sequenzen(state: AutoClickerState, bericht: Pruefbericht) -> None:
    """Sequenzdateien: tote Punkt-Referenzen und Verweise auf nicht existierende Scans.

    Liest alle Sequenzdateien — deshalb nur auf Zuruf, nicht beim Start.
    """
    from .persistence import list_available_sequences, load_sequence_file

    dateien = list_available_sequences()
    bericht.geprueft.append(f"{len(dateien)} Sequenz(en)")

    for name, pfad in dateien:
        seq = load_sequence_file(pfad)
        if seq is None:
            bericht.melde(STUFE_FEHLER, f"Sequenz '{name}'",
                          f"{pfad.name} ist nicht ladbar", "Datei prüfen oder neu anlegen")
            continue

        from .persistence import (list_available_item_scans, list_available_boss_scans,
                                  list_available_icon_scans)
        punkt_ids = {p.id for p in seq.points}
        bekannt = {
            "item_scan": {n for n, _ in list_available_item_scans(seq.name)},
            "boss_scan": {n for n, _ in list_available_boss_scans(seq.name)},
            "boss_watcher": {n for n, _ in list_available_boss_scans(seq.name)},
            "icon_scan": {n for n, _ in list_available_icon_scans(seq.name)},
        }
        phasen = [("INIT", seq.init_steps)]
        phasen += [(lp.name, lp.steps) for lp in seq.loop_phases]
        phasen.append(("END", seq.end_steps))

        tote_refs, tote_scans = [], []
        for phase, steps in phasen:
            for i, step in enumerate(steps, 1):
                if step.point_id is not None and step.point_id not in punkt_ids:
                    tote_refs.append(f"{phase}[{i}] → Punkt #{step.point_id}")
                for feld, namen in bekannt.items():
                    verweis = getattr(step, feld, None)
                    if verweis and verweis not in namen:
                        tote_scans.append(f"{phase}[{i}] → {feld} '{verweis}'")

        for eintrag in _gekuerzt(tote_refs):
            bericht.melde(STUFE_HINWEIS, f"Sequenz '{seq.name}'",
                          f"{eintrag} gibt es nicht mehr",
                          "Punkt im Punkte-Editor dieser Sequenz neu setzen")
        for eintrag in _gekuerzt(tote_scans):
            bericht.melde(STUFE_FEHLER, f"Sequenz '{seq.name}'",
                          f"{eintrag} existiert nicht")

        if seq.total_steps() == 0:
            bericht.melde(STUFE_HINWEIS, f"Sequenz '{seq.name}'", "hat keine Schritte")
        for lp in seq.loop_phases:
            if not lp.steps:
                bericht.melde(STUFE_HINWEIS, f"Sequenz '{seq.name}'",
                              f"Loop-Phase '{lp.name}' ist leer")


def _gekuerzt(eintraege: list[str]) -> list[str]:
    """Lange Listen abschneiden — 40 gleichartige Zeilen liest niemand."""
    if len(eintraege) <= _MAX_EINZELN:
        return eintraege
    rest = len(eintraege) - _MAX_EINZELN
    return eintraege[:_MAX_EINZELN] + [f"... und {rest} weitere"]


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def pruefe_setup(state: AutoClickerState, mit_sequenzen: bool = True) -> Pruefbericht:
    """Prüft das geladene Setup. `mit_sequenzen=False` lässt den Datei-Scan weg."""
    bericht = Pruefbericht()
    _pruefe_templates(state, bericht)
    _pruefe_erkennung(state, bericht)
    _pruefe_scan_referenzen(state, bericht)
    _pruefe_llm_ocr(state, bericht)
    _pruefe_koordinaten(state, bericht)
    if mit_sequenzen:
        _pruefe_sequenzen(state, bericht)
    return bericht


def print_bericht(bericht: Pruefbericht, still_wenn_sauber: bool = False) -> None:
    """Gibt den Bericht aus. `still_wenn_sauber` unterdrückt die Erfolgsmeldung."""
    if not bericht:
        if not still_wenn_sauber:
            print(f"\n{ok('Setup-Prüfung: nichts zu beanstanden.')}")
            if bericht.geprueft:
                print(f"       {hint('Geprüft: ' + ', '.join(bericht.geprueft))}")
        return

    print(f"\n{col('=' * 60, 'cyan')}")
    print(col("  SETUP-PRÜFUNG", "bold"))
    print(col("=" * 60, "cyan"))

    for ueberschrift, liste, stil in (
        (f"{len(bericht.fehler)} Fehler — so läuft es nicht:", bericht.fehler, err),
        (f"{len(bericht.hinweise)} Hinweis(e) — läuft, ist aber evtl. nicht gewollt:",
         bericht.hinweise, warn),
    ):
        if not liste:
            continue
        print(f"\n{stil(ueberschrift)}")
        for b in liste:
            print(f"  {col(b.bereich, 'cyan')}: {b.text}")
            if b.tipp:
                print(f"    {hint('→ ' + b.tipp)}")

    if bericht.geprueft:
        print(f"\n{info('Geprüft: ' + ', '.join(bericht.geprueft))}")
    print(col("=" * 60, "cyan"))


def check_beim_start(state: AutoClickerState) -> Pruefbericht:
    """Start-Prüfung: ohne Sequenzdateien, und still wenn alles in Ordnung ist."""
    bericht = pruefe_setup(state, mit_sequenzen=False)
    if bericht:
        print_bericht(bericht)
        print(f"{hint('Vollständige Prüfung inkl. Sequenzen: CTRL+ALT+P → check')}")
    return bericht
