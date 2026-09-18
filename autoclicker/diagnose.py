"""Selbstdiagnose: was ist kaputt, BEVOR die Sequenz läuft.

Die häufigste Frustration ist "ich starte, und es passiert das Falsche". Die meisten
Ursachen dafür sind statisch prüfbar — und die Prüfungen gab es auch schon, nur verstreut
über die Laufzeit und erst dann, wenn es zu spät war: eine Meldung in
`resolve_point_references()`, eine in `resolve_click_references()`, eine Warnung im
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
_MAX_SINGLE = 8

LEVEL_ERROR = "fehler"     # läuft so nicht (oder tut garantiert das Falsche)
LEVEL_HINT = "hinweis"   # läuft, ist aber vermutlich nicht gewollt


@dataclass
class Finding:
    """Ein Prüfergebnis: wo, was, und was man dagegen tut."""
    level: str
    area: str
    text: str
    tip: str = ""


@dataclass
class CheckReport:
    befunde: list[Finding] = field(default_factory=list)
    geprueft: list[str] = field(default_factory=list)

    def add_finding(self, level: str, area: str, text: str, tip: str = "") -> None:
        self.befunde.append(Finding(level, area, text, tip))

    @property
    def errors(self) -> list[Finding]:
        return [b for b in self.befunde if b.level == LEVEL_ERROR]

    @property
    def hints(self) -> list[Finding]:
        return [b for b in self.befunde if b.level == LEVEL_HINT]

    def __bool__(self) -> bool:
        """True = es gibt etwas zu melden."""
        return bool(self.befunde)


# ---------------------------------------------------------------------------
# Einzelprüfungen
# ---------------------------------------------------------------------------

def _check_templates(state: AutoClickerState, report: CheckReport) -> None:
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
    missing = [(wer, tpl) for wer, tpl in quellen
               if tpl and not (template_ordner / tpl).exists()]
    report.geprueft.append(f"{sum(1 for _, t in quellen if t)} Template-Verweise")
    for wer, tpl in missing:
        report.add_finding(LEVEL_ERROR, wer,
                      f"Template '{tpl}' fehlt in {template_ordner}/",
                      "Template neu aufnehmen oder den Verweis entfernen")


def _check_detection(state: AutoClickerState, report: CheckReport) -> None:
    """Ein Profil ohne Template UND ohne Marker wird nie erkannt.

    `_check_profile_match` gibt in dem Fall immer False zurück — der Scan läuft, findet
    nichts, und nichts sagt warum. Der stillste Fehler im ganzen Programm.
    """
    with state.lock:
        candidates = []
        for scan in state.boss_scans.values():
            candidates += [(f"Boss '{b.name}' (Scan '{scan.name}')", b) for b in scan.bosses]
        candidates += [(f"Boss '{b.name}' (Bibliothek)", b) for b in state.global_bosses]
        candidates += [(f"Icon-Scan '{c.name}'", c) for c in state.icon_scans.values()]
        items = [(f"Item '{i.name}' (Scan '{scan.name}')", i)
                 for scan in state.item_scans.values() for i in scan.items]

    for wer, profil in candidates:
        if not profil.template and not profil.marker_colors:
            report.add_finding(LEVEL_ERROR, wer,
                          "weder Template noch Farb-Marker — wird nie erkannt",
                          "Template aufnehmen oder Marker-Farben setzen")
    for wer, item in items:
        if not item.template_names() and not item.marker_colors:
            report.add_finding(LEVEL_HINT, wer,
                          "weder Template noch Farb-Marker — wird in keinem Scan gefunden")
    report.geprueft.append(f"{len(candidates) + len(items)} Erkennungs-Profile")


def _check_scan_references(state: AutoClickerState, report: CheckReport) -> None:
    """Ein eigenständiger Scan braucht mindestens Slots und Erkennung."""
    with state.lock:
        scans = list(state.item_scans.values())

    for cfg in scans:
        if not cfg.slots:
            report.add_finding(LEVEL_ERROR, f"Item-Scan '{cfg.name}'",
                          "kein einziger Slot — der Scan kann nichts absuchen")
        elif not any(slot.enabled for slot in cfg.slots):
            report.add_finding(LEVEL_ERROR, f"Item-Scan '{cfg.name}'",
                          "kein Slot ist eingeschaltet — der Scan kann nichts absuchen")
        if not any(item.enabled for item in cfg.items) and not cfg.learn_unknown:
            report.add_finding(LEVEL_HINT, f"Item-Scan '{cfg.name}'",
                          "keine aktiven Items und kein Auto-Lernen — findet nie etwas")
    report.geprueft.append(f"{len(scans)} Item-Scan(s)")

    # **`default_scan` ist die fünfte Referenz auf einen Scan-Namen** — und die
    # einzige, die nicht in einem Schritt steht, sondern in einer Boss-Scan-Datei.
    # `_check_sequences()` sieht deshalb nur die vier im Schritt; diese fiel
    # durch, obwohl `runtime/steps.py` sie bei „kein Boss erkannt" wirklich
    # ausführt: `execute_item_scan(state, config.default_scan)`. Zeigt sie ins
    # Leere, tut der Fallback nichts und sagt es nicht.
    with state.lock:
        boss_scans = list(state.boss_scans.values())
    existing = {cfg.name for cfg in scans}
    for cfg in boss_scans:
        if cfg.default_scan and cfg.default_scan not in existing:
            report.add_finding(LEVEL_HINT, f"Boss-Scan '{cfg.name}'",
                          f"Fallback-Scan '{cfg.default_scan}' gibt es nicht",
                          "im Scans-Reiter einen vorhandenen Item-Scan wählen")
    if boss_scans:
        report.geprueft.append(f"{len(boss_scans)} Fallback-Scan-Verweis(e)")


def _check_llm_ocr(state: AutoClickerState, report: CheckReport) -> None:
    """Ein Scan mit use_llm/use_ocr nützt nichts, wenn es global aus ist."""
    with state.lock:
        scans = list(state.boss_scans.values())
        llm_an = state.config.llm_enabled
        ocr_an = state.config.ocr_enabled

    for cfg in scans:
        if cfg.use_llm and not llm_an:
            report.add_finding(LEVEL_HINT, f"Boss-Scan '{cfg.name}'",
                          "use_llm ist an, llm_enabled global aus — LLM wird ignoriert",
                          "llm_enabled in config.json setzen oder use_llm abschalten")
        if cfg.use_ocr and not ocr_an:
            report.add_finding(LEVEL_HINT, f"Boss-Scan '{cfg.name}'",
                          "use_ocr ist an, ocr_enabled global aus — OCR wird ignoriert",
                          "ocr_enabled in config.json setzen oder use_ocr abschalten")


def _check_coordinates(state: AutoClickerState, report: CheckReport) -> None:
    """Punkte ausserhalb aller Monitore klicken ins Nichts."""
    rect = get_virtual_desktop()
    if rect is None:
        return
    left, top, right, bottom = rect
    with state.lock:
        points = list(state.points)
    draussen = [p for p in points
                if not (left <= p.x < right and top <= p.y < bottom)]
    report.geprueft.append(f"{len(points)} Punkt(e)")
    for p in draussen:
        report.add_finding(LEVEL_ERROR, f"Punkt #{p.id} {p.name}".strip(),
                      f"({p.x}, {p.y}) liegt ausserhalb aller Monitore "
                      f"({left},{top})-({right},{bottom})",
                      "Bildschirm-Layout geaendert? Punkte-Menue -> 'fix' rechnet "
                      "alle Koordinaten aus einem neu gesetzten Punkt um")


def _check_sequences(state: AutoClickerState, report: CheckReport) -> None:
    """Sequenzdateien: tote Punkt-Referenzen und Verweise auf nicht existierende Scans.

    Liest alle Sequenzdateien — deshalb nur auf Zuruf, nicht beim Start.
    """
    from .persistence import list_available_sequences, load_sequence_file

    dateien = list_available_sequences()
    report.geprueft.append(f"{len(dateien)} Sequenz(en)")

    for name, path in dateien:
        seq = load_sequence_file(path)
        if seq is None:
            report.add_finding(LEVEL_ERROR, f"Sequenz '{name}'",
                          f"{path.name} ist nicht ladbar", "Datei prüfen oder neu anlegen")
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
                for feld, names in bekannt.items():
                    verweis = getattr(step, feld, None)
                    if verweis and verweis not in names:
                        tote_scans.append(f"{phase}[{i}] → {feld} '{verweis}'")

        for entry in _truncated(tote_refs):
            report.add_finding(LEVEL_HINT, f"Sequenz '{seq.name}'",
                          f"{entry} gibt es nicht mehr",
                          "Punkt im Punkte-Editor dieser Sequenz neu setzen")
        for entry in _truncated(tote_scans):
            report.add_finding(LEVEL_ERROR, f"Sequenz '{seq.name}'",
                          f"{entry} existiert nicht")

        if seq.total_steps() == 0:
            report.add_finding(LEVEL_HINT, f"Sequenz '{seq.name}'", "hat keine Schritte")
        for lp in seq.loop_phases:
            if not lp.steps:
                report.add_finding(LEVEL_HINT, f"Sequenz '{seq.name}'",
                              f"Loop-Phase '{lp.name}' ist leer")


def _truncated(entries: list[str]) -> list[str]:
    """Lange Listen abschneiden — 40 gleichartige Zeilen liest niemand."""
    if len(entries) <= _MAX_SINGLE:
        return entries
    remainder = len(entries) - _MAX_SINGLE
    return entries[:_MAX_SINGLE] + [f"... und {remainder} weitere"]


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def check_setup(state: AutoClickerState, mit_sequenzen: bool = True) -> CheckReport:
    """Prüft das geladene Setup. `mit_sequenzen=False` lässt den Datei-Scan weg."""
    report = CheckReport()
    _check_templates(state, report)
    _check_detection(state, report)
    _check_scan_references(state, report)
    _check_llm_ocr(state, report)
    _check_coordinates(state, report)
    if mit_sequenzen:
        _check_sequences(state, report)
    return report


def print_report(report: CheckReport, still_wenn_sauber: bool = False) -> None:
    """Gibt den Bericht aus. `still_wenn_sauber` unterdrückt die Erfolgsmeldung."""
    if not report:
        if not still_wenn_sauber:
            print(f"\n{ok('Setup-Prüfung: nichts zu beanstanden.')}")
            if report.geprueft:
                print(f"       {hint('Geprüft: ' + ', '.join(report.geprueft))}")
        return

    print(f"\n{col('=' * 60, 'cyan')}")
    print(col("  SETUP-PRÜFUNG", "bold"))
    print(col("=" * 60, "cyan"))

    for ueberschrift, liste, stil in (
        (f"{len(report.errors)} Fehler — so läuft es nicht:", report.errors, err),
        (f"{len(report.hints)} Hinweis(e) — läuft, ist aber evtl. nicht gewollt:",
         report.hints, warn),
    ):
        if not liste:
            continue
        print(f"\n{stil(ueberschrift)}")
        for b in liste:
            print(f"  {col(b.area, 'cyan')}: {b.text}")
            if b.tip:
                print(f"    {hint('→ ' + b.tip)}")

    if report.geprueft:
        print(f"\n{info('Geprüft: ' + ', '.join(report.geprueft))}")
    print(col("=" * 60, "cyan"))


def check_on_start(state: AutoClickerState) -> CheckReport:
    """Start-Prüfung: ohne Sequenzdateien, und still wenn alles in Ordnung ist."""
    report = check_setup(state, mit_sequenzen=False)
    if report:
        print_report(report)
        print(f"{hint('Vollständige Prüfung inkl. Sequenzen: CTRL+ALT+P → check')}")
    return report
