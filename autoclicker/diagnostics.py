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
from typing import Optional

from .models import AutoClickerState
from .persistence import sequence_templates_dir
from .utils import col, err, hint, info, ok, warn
from .winapi import get_virtual_desktop

# Ab wie vielen gleichartigen Befunden nur noch gezählt statt aufgezählt wird.
_MAX_SINGLE = 8

LEVEL_ERROR = "error"      # läuft so nicht (oder tut garantiert das Falsche)
LEVEL_HINT = "hint"      # läuft, ist aber vermutlich nicht gewollt


@dataclass
class Finding:
    """Ein Prüfergebnis: wo, was, und was man dagegen tut.

    `target` ist die Sprungmarke fürs Studio: wohin man muss, um es zu
    reparieren — `{"view": "scans", "kind": …, "name": …}` für einen Scan,
    `{"view": "editor", "phase": i, "row": j}` für einen Block, `{"view":
    "editor", "point": id}` für einen Punkt. Die Konsole liest es nicht; ein
    Befund ohne Ziel bleibt erlaubt (eine unlesbare Datei hat keins).
    """
    level: str
    area: str
    text: str
    tip: str = ""
    target: Optional[dict] = None


@dataclass
class CheckReport:
    findings: list[Finding] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)

    def add_finding(self, level: str, area: str, text: str, tip: str = "",
                    target: Optional[dict] = None) -> None:
        self.findings.append(Finding(level, area, text, tip, target))

    @property
    def errors(self) -> list[Finding]:
        return [b for b in self.findings if b.level == LEVEL_ERROR]

    @property
    def hints(self) -> list[Finding]:
        return [b for b in self.findings if b.level == LEVEL_HINT]

    def __bool__(self) -> bool:
        """True = es gibt etwas zu melden."""
        return bool(self.findings)


# ---------------------------------------------------------------------------
# Einzelprüfungen
# ---------------------------------------------------------------------------


def _scan_target(kind: str, name: str) -> dict:
    """Sprungmarke auf einen Scan im Scans-Reiter (leerer Name = die Bibliothek)."""
    return {"view": "scans", "kind": kind, "name": name}


def _block_target(phase: int, row: int, sequence: str) -> dict:
    """Sprungmarke auf einen Block: Phase als Lane-Index (0 = INIT), Zeile ab 0."""
    return {"view": "editor", "sequence": sequence, "phase": phase, "row": row}


def _check_templates(state: AutoClickerState, report: CheckReport) -> None:
    """Jedes referenzierte Template-PNG muss auf Platte liegen.

    Fehlt es, meldet das Matching still `(False, 0.0, None)` — das Item wird nie erkannt,
    und die einzige Spur ist eine Logger-Zeile im Rauschen.
    """
    with state.lock:
        owner = state.active_sequence.name if state.active_sequence else ""
        sources = [(f"Item '{i.name}' (Scan '{scan.name}')", tpl, _scan_target("item", scan.name))
                   for scan in state.item_scans.values() for i in scan.items
                   for tpl in i.template_names()]
        for scan in state.boss_scans.values():
            sources += [(f"Boss '{b.name}' (Scan '{scan.name}')", b.template,
                         _scan_target("boss", scan.name))
                        for b in scan.bosses]
        sources += [(f"Boss '{b.name}' (Bibliothek)", b.template, _scan_target("boss", ""))
                    for b in state.global_bosses]
        sources += [(f"Icon-Scan '{c.name}'", c.template, _scan_target("icon", c.name))
                    for c in state.icon_scans.values()]

    template_folder = sequence_templates_dir(owner) if owner else Path("sequences")
    missing = [(who, tpl, target) for who, tpl, target in sources
               if tpl and not (template_folder / tpl).exists()]
    report.checked.append(f"{sum(1 for _, t, _ in sources if t)} Template-Verweise")
    for who, tpl, target in missing:
        report.add_finding(LEVEL_ERROR, who,
                      f"Template '{tpl}' fehlt in {template_folder}/",
                      "Template neu aufnehmen oder den Verweis entfernen", target)


def _check_detection(state: AutoClickerState, report: CheckReport) -> None:
    """Ein Profil ohne Template UND ohne Marker wird nie erkannt.

    `_check_profile_match` gibt in dem Fall immer False zurück — der Scan läuft, findet
    nichts, und nichts sagt warum. Der stillste Fehler im ganzen Programm.
    """
    with state.lock:
        candidates = []
        for scan in state.boss_scans.values():
            candidates += [(f"Boss '{b.name}' (Scan '{scan.name}')", b,
                            _scan_target("boss", scan.name)) for b in scan.bosses]
        candidates += [(f"Boss '{b.name}' (Bibliothek)", b, _scan_target("boss", ""))
                       for b in state.global_bosses]
        candidates += [(f"Icon-Scan '{c.name}'", c, _scan_target("icon", c.name))
                       for c in state.icon_scans.values()]
        items = [(f"Item '{i.name}' (Scan '{scan.name}')", i, _scan_target("item", scan.name))
                 for scan in state.item_scans.values() for i in scan.items]

    for who, profile, target in candidates:
        if not profile.template and not profile.marker_colors:
            report.add_finding(LEVEL_ERROR, who,
                          "weder Template noch Farb-Marker — wird nie erkannt",
                          "Template aufnehmen oder Marker-Farben setzen", target)
    for who, item, target in items:
        if not item.template_names() and not item.marker_colors:
            report.add_finding(LEVEL_HINT, who,
                          "weder Template noch Farb-Marker — wird in keinem Scan gefunden",
                          target=target)
    report.checked.append(f"{len(candidates) + len(items)} Erkennungs-Profile")


def _check_scan_references(state: AutoClickerState, report: CheckReport) -> None:
    """Ein eigenständiger Scan braucht mindestens Slots und Erkennung."""
    with state.lock:
        scans = list(state.item_scans.values())

    for cfg in scans:
        target = _scan_target("item", cfg.name)
        if not cfg.slots:
            report.add_finding(LEVEL_ERROR, f"Item-Scan '{cfg.name}'",
                          "kein einziger Slot — der Scan kann nichts absuchen", target=target)
        elif not any(slot.enabled for slot in cfg.slots):
            report.add_finding(LEVEL_ERROR, f"Item-Scan '{cfg.name}'",
                          "kein Slot ist eingeschaltet — der Scan kann nichts absuchen",
                          target=target)
        if not any(item.enabled for item in cfg.items) and not cfg.learn_unknown:
            report.add_finding(LEVEL_HINT, f"Item-Scan '{cfg.name}'",
                          "keine aktiven Items und kein Auto-Lernen — findet nie etwas",
                          target=target)
    report.checked.append(f"{len(scans)} Item-Scan(s)")

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
                          "im Scans-Reiter einen vorhandenen Item-Scan wählen",
                          _scan_target("boss", cfg.name))
    if boss_scans:
        report.checked.append(f"{len(boss_scans)} Fallback-Scan-Verweis(e)")


def _check_llm_ocr(state: AutoClickerState, report: CheckReport) -> None:
    """Ein Scan mit use_llm/use_ocr nützt nichts, wenn es global aus ist."""
    with state.lock:
        scans = list(state.boss_scans.values())
        llm_on = state.config.llm_enabled
        ocr_on = state.config.ocr_enabled

    for cfg in scans:
        if cfg.use_llm and not llm_on:
            report.add_finding(LEVEL_HINT, f"Boss-Scan '{cfg.name}'",
                          "use_llm ist an, llm_enabled global aus — LLM wird ignoriert",
                          "llm_enabled in config.json setzen oder use_llm abschalten")
        if cfg.use_ocr and not ocr_on:
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
    outside = [p for p in points
                if not (left <= p.x < right and top <= p.y < bottom)]
    report.checked.append(f"{len(points)} Punkt(e)")
    for p in outside:
        report.add_finding(LEVEL_ERROR, f"Punkt #{p.id} {p.name}".strip(),
                      f"({p.x}, {p.y}) liegt ausserhalb aller Monitore "
                      f"({left},{top})-({right},{bottom})",
                      "Bildschirm-Layout geaendert? Punkte-Menue -> 'fix' rechnet "
                      "alle Koordinaten aus einem neu gesetzten Punkt um",
                      {"view": "editor", "point": p.id})


def _check_sequences(state: AutoClickerState, report: CheckReport) -> None:
    """Sequenzdateien: tote Punkt-Referenzen und Verweise auf nicht existierende Scans.

    Liest alle Sequenzdateien — deshalb nur auf Zuruf, nicht beim Start.
    """
    from .persistence import list_available_sequences, load_sequence_file

    files = list_available_sequences()
    report.checked.append(f"{len(files)} Sequenz(en)")

    for name, path in files:
        seq = load_sequence_file(path)
        if seq is None:
            report.add_finding(LEVEL_ERROR, f"Sequenz '{name}'",
                          f"{path.name} ist nicht ladbar", "Datei prüfen oder neu anlegen")
            continue

        from .persistence import (list_available_item_scans, list_available_boss_scans,
                                  list_available_icon_scans)
        point_ids = {p.id for p in seq.points}
        known = {
            "item_scan": {n for n, _ in list_available_item_scans(seq.name)},
            "boss_scan": {n for n, _ in list_available_boss_scans(seq.name)},
            "boss_watcher": {n for n, _ in list_available_boss_scans(seq.name)},
            "icon_scan": {n for n, _ in list_available_icon_scans(seq.name)},
        }
        phases = [("INIT", seq.init_steps)]
        phases += [(lp.name, lp.steps) for lp in seq.loop_phases]
        phases.append(("END", seq.end_steps))

        # Die Sprungmarke zeigt auf den Block: Lane-Index wie im Studio-Board
        # (0 = INIT, dann die Loop-Phasen, zuletzt END), Zeile ab 0.
        dead_refs, dead_scans = [], []
        for lane, (phase, steps) in enumerate(phases):
            for i, step in enumerate(steps, 1):
                target = _block_target(lane, i - 1, seq.name)
                if step.point_id is not None and step.point_id not in point_ids:
                    dead_refs.append((f"{phase}[{i}] → Punkt #{step.point_id}", target))
                for attr, names in known.items():
                    ref = getattr(step, attr, None)
                    if ref and ref not in names:
                        dead_scans.append((f"{phase}[{i}] → {attr} '{ref}'", target))

        for entry, target in _truncated(dead_refs):
            report.add_finding(LEVEL_HINT, f"Sequenz '{seq.name}'",
                          f"{entry} gibt es nicht mehr",
                          "Punkt im Punkte-Editor dieser Sequenz neu setzen", target)
        for entry, target in _truncated(dead_scans):
            report.add_finding(LEVEL_ERROR, f"Sequenz '{seq.name}'",
                          f"{entry} existiert nicht", target=target)

        if seq.total_steps() == 0:
            report.add_finding(LEVEL_HINT, f"Sequenz '{seq.name}'", "hat keine Schritte")
        for lane, lp in enumerate(seq.loop_phases, 1):
            if not lp.steps:
                report.add_finding(LEVEL_HINT, f"Sequenz '{seq.name}'",
                              f"Loop-Phase '{lp.name}' ist leer",
                              target=_block_target(lane, 0, seq.name))


def _truncated(entries: list) -> list:
    """Lange Listen abschneiden — 40 gleichartige Zeilen liest niemand.

    Einträge sind `(Text, Ziel)`; die Sammelzeile am Ende hat kein Ziel.
    """
    if len(entries) <= _MAX_SINGLE:
        return entries
    remainder = len(entries) - _MAX_SINGLE
    return entries[:_MAX_SINGLE] + [(f"... und {remainder} weitere", None)]


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def check_setup(state: AutoClickerState, with_sequences: bool = True) -> CheckReport:
    """Prüft das geladene Setup. `with_sequences=False` lässt den Datei-Scan weg."""
    report = CheckReport()
    _check_templates(state, report)
    _check_detection(state, report)
    _check_scan_references(state, report)
    _check_llm_ocr(state, report)
    _check_coordinates(state, report)
    if with_sequences:
        _check_sequences(state, report)
    return report


def print_report(report: CheckReport, quiet_when_clean: bool = False) -> None:
    """Gibt den Bericht aus. `quiet_when_clean` unterdrückt die Erfolgsmeldung."""
    if not report:
        if not quiet_when_clean:
            print(f"\n{ok('Setup-Prüfung: nichts zu beanstanden.')}")
            if report.checked:
                print(f"       {hint('Geprüft: ' + ', '.join(report.checked))}")
        return

    print(f"\n{col('=' * 60, 'cyan')}")
    print(col("  SETUP-PRÜFUNG", "bold"))
    print(col("=" * 60, "cyan"))

    for heading, listing, style in (
        (f"{len(report.errors)} Fehler — so läuft es nicht:", report.errors, err),
        (f"{len(report.hints)} Hinweis(e) — läuft, ist aber evtl. nicht gewollt:",
         report.hints, warn),
    ):
        if not listing:
            continue
        print(f"\n{style(heading)}")
        for b in listing:
            print(f"  {col(b.area, 'cyan')}: {b.text}")
            if b.tip:
                print(f"    {hint('→ ' + b.tip)}")

    if report.checked:
        print(f"\n{info('Geprüft: ' + ', '.join(report.checked))}")
    print(col("=" * 60, "cyan"))


def check_on_start(state: AutoClickerState) -> CheckReport:
    """Start-Prüfung: ohne Sequenzdateien, und still wenn alles in Ordnung ist."""
    report = check_setup(state, with_sequences=False)
    if report:
        print_report(report)
        print(f"{hint('Vollständige Prüfung inkl. Sequenzen: CTRL+ALT+P → check')}")
    return report
