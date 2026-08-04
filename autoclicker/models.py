"""
Datenklassen für den Autoclicker.
Definiert alle Datenstrukturen wie ClickPoint, SequenceStep, Sequence, etc.
"""

import random
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import AppConfig

# Der DATEI-Default für min_confidence: was gilt, wenn das Feld in der JSON fehlt.
# Konstant, bewusst NICHT aus der Config abgeleitet — sonst würde ein Feld, das gerade
# zufällig dem Config-Wert entspricht, beim Speichern weggelassen und beim nächsten Start
# mit einem ANDEREN Wert zurückkommen, sobald man die Config anfasst.
#
# Davon zu unterscheiden: `AppConfig.scan_min_confidence` ist die Voreinstellung, die die
# Editoren beim Anlegen NEUER Profile vorschlagen. Zwei verschiedene Dinge — sie hier
# zusammenzulegen war die Ursache stillen Datenverlusts.
DEFAULT_MIN_CONFIDENCE: float = 0.8


# =============================================================================
# STRING-KONSTANTEN (zentral definiert, verhindert Tippfehler)
# =============================================================================
# Aktions-Typen (zentral, eine Quelle der Wahrheit).
# ElseConfig, BossProfile und IconScanConfig teilen sich dieselben Aktionswerte —
# die familienspezifischen Namen unten sind nur Aliase für Lesbarkeit/Kompat.
ACTION_CLICK = "click"              # Punkt klicken
ACTION_KEY = "key"                  # Taste drücken
ACTION_SKIP = "skip"                # Schritt überspringen
ACTION_SKIP_CYCLE = "skip_cycle"    # Zyklus überspringen
ACTION_RESTART = "restart"          # Sequenz neustarten
ACTION_ITEM_SCAN = "item_scan"      # Item-Scan ausführen (nur Boss)

# ElseConfig.action
ELSE_SKIP = ACTION_SKIP
ELSE_SKIP_CYCLE = ACTION_SKIP_CYCLE
ELSE_RESTART = ACTION_RESTART
ELSE_CLICK = ACTION_CLICK
ELSE_KEY = ACTION_KEY
VALID_ELSE_ACTIONS = {ELSE_SKIP, ELSE_SKIP_CYCLE, ELSE_RESTART, ELSE_CLICK, ELSE_KEY}

# pixel_timeout_action (Config)
TIMEOUT_SKIP_CYCLE = "skip_cycle"
TIMEOUT_RESTART = "restart"
TIMEOUT_STOP = "stop"

# consecutive_timeout_action (Config)
CONSEC_STOP = "stop"
CONSEC_QUIT = "quit"
CONSEC_EXIT = "exit"

# SequenceStep.item_scan_mode
SCAN_MODE_ALL = "all"         # Bestes pro Kategorie
SCAN_MODE_BEST = "best"       # Nur 1 bestes Item total
SCAN_MODE_EVERY = "every"     # Jedes gefundene Item
VALID_SCAN_MODES = {SCAN_MODE_ALL, SCAN_MODE_BEST, SCAN_MODE_EVERY}

# BossProfile.action
BOSS_ACTION_SCAN = ACTION_ITEM_SCAN
BOSS_ACTION_CLICK = ACTION_CLICK
BOSS_ACTION_KEY = ACTION_KEY
BOSS_ACTION_SKIP = ACTION_SKIP
BOSS_ACTION_SKIP_CYCLE = ACTION_SKIP_CYCLE
BOSS_ACTION_RESTART = ACTION_RESTART
VALID_BOSS_ACTIONS = {BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY,
                      BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART}

# IconScanConfig.action — Aktion wenn ein Icon (z.B. rotes "!") erkannt wird
ICON_ACTION_CLICK = ACTION_CLICK
ICON_ACTION_KEY = ACTION_KEY
ICON_ACTION_SKIP = ACTION_SKIP
ICON_ACTION_SKIP_CYCLE = ACTION_SKIP_CYCLE
ICON_ACTION_RESTART = ACTION_RESTART
VALID_ICON_ACTIONS = {ICON_ACTION_CLICK, ICON_ACTION_KEY, ICON_ACTION_SKIP,
                      ICON_ACTION_SKIP_CYCLE, ICON_ACTION_RESTART}


# =============================================================================
# DATENKLASSEN
# =============================================================================
@dataclass
class ClickPoint:
    """Ein Klickpunkt mit x,y Koordinaten und stabiler ID."""
    x: int
    y: int
    name: str = ""  # Optionaler Name für den Punkt
    id: int = 0     # Stabile ID für Referenzierung (bleibt bei Umsortierung erhalten)
    # Pixelfarbe an der Position zum Aufnahme-Zeitpunkt (r,g,b) oder None.
    # Wird beim Erstellen eines Schritts aus diesem Punkt als recorded_color
    # übernommen — zuverlässiger als ein Live-Abgriff im Editor, da das Spiel
    # bei der Aufnahme im richtigen Zustand war.
    color: Optional[tuple[int, int, int]] = None
    # Herkunfts-Kommentar, z.B. "Aufnahme 'Bossfarm'" — bleibt auch nach
    # Umbenennen des Punkts sichtbar, damit klar bleibt woher er stammt.
    source: str = ""

    def __str__(self) -> str:
        src = f"  [{self.source}]" if self.source else ""
        if self.name:
            return f"#{self.id} {self.name} ({self.x}, {self.y}){src}"
        return f"#{self.id} ({self.x}, {self.y}){src}"


# =============================================================================
# KOORDINATEN GEHÖREN IN points.json — NIRGENDWO SONST
# =============================================================================
# Jede Stelle, auf die eine Sequenz klickt oder schaut, ist ein Punkt aus dem
# Punkte-Pool. Die Sequenz speichert nur die `point_id`; x/y/Farbe stehen in
# `points.json` und werden beim Laden von dort geholt.
#
# Warum so streng: eine Koordinate an zwei Stellen ist eine Koordinate, die an
# einer der beiden Stellen falsch sein kann. Wer die Sequenzdatei liest, sieht
# dann etwas anderes als das, was die App klickt — und beim Nachrechnen (Monitor
# umgestellt, Import auf einen anderen Rechner) muss jede Kopie einzeln erwischt
# werden. Genau daran hing die Kalibrierung.
#
# Es gibt deshalb bewusst KEINEN Rückfallwert: hat ein Schritt eine tote
# `point_id`, wird er übersprungen und gemeldet. Ein Schritt, der "sicherheits-
# halber" auf eine veraltete Kopie klickt, ist schlimmer als einer, der stehen
# bleibt und sagt warum.
#
# `pixel`/`color` bzw. `x`/`y`/`name` unten bleiben trotzdem als Felder bestehen:
# sie sind die AUFGELÖSTEN ARBEITSWERTE, die `resolve_point_references()` beim
# Laden füllt — dasselbe Muster wie `ItemScanConfig.slots`/`items`. Worker und
# Editoren lesen sie unverändert; gespeichert werden sie nicht.

@dataclass
class ElseConfig:
    """Fallback-Aktion wenn eine Bedingung (Farbe/Scan) fehlschlägt."""
    action: str                          # "skip", "skip_cycle", "restart", "click", "key"
    # Referenz auf den Fallback-Punkt (nur bei action="click"). DAS ist der
    # gespeicherte Wert — x/y/name darunter werden daraus abgeleitet.
    point_id: Optional[int] = None
    x: int = 0                           # abgeleitet: X für Fallback-Klick
    y: int = 0                           # abgeleitet: Y für Fallback-Klick
    delay: float = 0                     # Delay vor Fallback
    key: Optional[str] = None            # Taste für Fallback
    name: str = ""                       # abgeleitet: Name des Fallback-Punkts


@dataclass
class WaitCondition:
    """Farb-Bedingung an einer Pixel-Position: warten oder einmal prüfen."""
    # Referenz auf den Punkt, dessen Position UND Farbe geprüft werden. DAS ist
    # der gespeicherte Wert — pixel/color darunter werden daraus abgeleitet.
    #
    # Dass die erwartete Farbe aus dem Punkt kommt, ist Absicht: sie war vorher
    # eine zweite Kopie von `ClickPoint.color`. Soll an derselben Stelle auf eine
    # ANDERE Farbe geprüft werden, ist das ein eigener Punkt — im Punkte-Menü
    # liest man dann auch, dass es zwei Prüfungen sind.
    point_id: Optional[int] = None
    pixel: tuple[int, int] = (0, 0)      # abgeleitet: (x, y) Position zum Prüfen
    color: tuple[int, int, int] = (0, 0, 0)  # abgeleitet: (r,g,b) die erscheinen soll
    until_gone: bool = False             # True = warte bis Farbe WEG ist
    # True = NICHT warten, sondern einmal prüfen. Passt die Farbe nicht, greift sofort
    # else_config (Standard: Schritt überspringen) statt bis zum Timeout zu blockieren.
    check_only: bool = False


@dataclass
class SequenceStep:
    """Ein Schritt in einer Sequenz: Erst warten/prüfen, DANN klicken."""
    # x/y/name sind abgeleitet (siehe Block oben) und deshalb optional: Pflicht ist die
    # `point_id`, nicht die Koordinate. Frueher war es umgekehrt - da MUSSTE jeder
    # Aufrufer x und y angeben, und genau das hat die Kopien erzeugt.
    x: int = 0
    y: int = 0
    delay_before: float = 0.0   # Wartezeit in Sekunden VOR diesem Klick (0 = sofort)
    name: str = ""              # abgeleitet: Name des Punktes
    # Referenz auf den Punkt im Punkte-Pool. DAS ist der gespeicherte Wert; x/y/name
    # und recorded_color werden beim Laden daraus geholt.
    #
    # Ein Schritt, der irgendwohin zeigt, MUSS eine point_id haben — die Migration legt
    # notfalls einen Punkt an, damit das ausnahmslos gilt. `None` bleibt genau den
    # Schritten, die gar keine Stelle haben: Tastendruck, Wait-only, Scans, Screenshot
    # und der Blanko-Block des Node-Editors.
    point_id: Optional[int] = None
    # Optional: Warten auf Farbe statt Zeit (VOR dem Klick)
    wait_condition: Optional[WaitCondition] = None
    # Optional: Item-Scan ausführen statt direktem Klick
    item_scan: Optional[str] = None      # Name des Item-Scans
    item_scan_mode: str = "all"          # "all" = bestes pro Kategorie, "best" = nur 1 Item total
    # Optional: Nur warten, nicht klicken
    wait_only: bool = False              # True = nur warten, kein Klick
    # Optional: Zufällige Verzögerung (delay_before bis delay_max)
    delay_max: Optional[float] = None    # None = feste Zeit, sonst Bereich
    # Optional: Tastendruck statt Mausklick
    key_press: Optional[str] = None      # z.B. "enter", "space", "f1"
    # Optional: Mausrad drehen statt klicken. Positiv = hoch, negativ = runter,
    # Betrag = Rasterstufen. Gescrollt wird an (x, y), weil Windows das Rad-Event an
    # das Fenster UNTER dem Cursor liefert.
    scroll: Optional[int] = None
    # Optional: Fallback/Else-Aktion wenn Bedingung fehlschlägt
    else_config: Optional[ElseConfig] = None
    # Optional: Boss-Scan ausführen (erkennt Boss → bedingte Aktion)
    boss_scan: Optional[str] = None      # Name der BossScanConfig
    # Optional: Boss-Watcher (wartet bis Boss erkannt, dann Aktion)
    boss_watcher: Optional[str] = None   # Name der BossScanConfig für Watcher-Modus
    # Optional: Icon-Scan (erkennt Symbol/Icon in Region → Aktion)
    icon_scan: Optional[str] = None      # Name der IconScanConfig
    # Optional: Screenshot machen (kein Klick, kein Scan)
    screenshot_only: bool = False        # True = nur Screenshot, kein Klick
    screenshot_region: Optional[tuple[int, int, int, int]] = None  # (x1,y1,x2,y2) oder None = Vollbild
    # Abgeleitet aus `ClickPoint.color`: die bei der Aufnahme erfasste Pixelfarbe am
    # Klickpunkt (r,g,b). Reines Hilfs-/Referenzdatum für die Nachbearbeitung — erlaubt,
    # einen aufgenommenen Klick nachträglich in einen Farb-Trigger umzuwandeln, ohne die
    # Farbe erneut abgreifen zu müssen. Beeinflusst die Ausführung NICHT.
    recorded_color: Optional[tuple[int, int, int]] = None
    # Arbeitswert, wird nie gespeichert: True = die point_id zeigt ins Leere, der Punkt
    # wurde geloescht. `step_gate()` ueberspringt den Schritt dann und meldet es. Ohne
    # dieses Flag wuerde er auf (0, 0) klicken - es gibt ja keine Rueckfall-Koordinate
    # mehr, und das ist genau so gewollt.
    unresolved: bool = False

    def __str__(self) -> str:
        else_str = self._else_str()
        if self.boss_watcher:
            return f"BOSS-WATCHER '{self.boss_watcher}' (wartet auf Boss){else_str}"
        if self.screenshot_only:
            region = self.screenshot_region
            if region:
                return f"SCREENSHOT ({region[0]},{region[1]})→({region[2]},{region[3]})"
            return "SCREENSHOT (Vollbild)"
        if self.key_press:
            return (f"{self._trigger_str()} → drücke Taste '{self.key_press}'{else_str}")
        if self.scroll:
            richtung = "hoch" if self.scroll > 0 else "runter"
            ziel = f"{self.name} " if self.name else ""
            return (f"{self._trigger_str()} → scrolle {richtung} x{abs(self.scroll)} "
                    f"bei {ziel}({self.x}, {self.y}){else_str}")
        if self.boss_scan:
            return f"BOSS-SCAN '{self.boss_scan}'{else_str}"
        if self.icon_scan:
            # Fehlte hier komplett: ein Icon-Scan-Schritt fiel bis ans Ende durch und
            # wurde in der Schritt-Liste als "sofort → klicke (0, 0)" angezeigt.
            return f"ICON-SCAN '{self.icon_scan}'{else_str}"
        if self.item_scan:
            mode_strs = {SCAN_MODE_ALL: "bestes/Kategorie", SCAN_MODE_BEST: "1 bestes", SCAN_MODE_EVERY: "JEDES"}
            mode_str = mode_strs.get(self.item_scan_mode, self.item_scan_mode)
            return f"SCAN '{self.item_scan}' → klicke {mode_str}{else_str}"
        wc = self.wait_condition
        if self.wait_only:
            if wc:
                gone_str = "WEG ist" if wc.until_gone else "DA ist"
                if wc.check_only:
                    return (f"PRÜFE einmal ob Farbe {gone_str} bei "
                            f"({wc.pixel[0]},{wc.pixel[1]}) (kein Klick){else_str}")
                return f"WARTE bis Farbe {gone_str} bei ({wc.pixel[0]},{wc.pixel[1]}) (kein Klick){else_str}"
            return f"WARTE {self._delay_str()} (kein Klick)"
        ref = f" #{self.point_id}" if self.point_id is not None else ""
        pos_str = (f"{self.name}{ref} ({self.x}, {self.y})" if self.name
                   else f"{ref.strip()} ({self.x}, {self.y})".strip())
        if wc:
            if wc.check_only:
                zustand = "WEG" if wc.until_gone else "DA"
                vorlauf = f"warte {self._delay_str()}, dann " if self.delay_before > 0 else ""
                return (f"{vorlauf}prüfe einmal ob Farbe {zustand} bei "
                        f"({wc.pixel[0]},{wc.pixel[1]}) → klicke {pos_str}"
                        f"{else_str or ' | sonst: überspringen'}")
            gone_str = "bis Farbe WEG" if wc.until_gone else "auf Farbe"
            delay_str = self._delay_str()
            if self.delay_before > 0:
                return f"warte {delay_str}, dann {gone_str} bei ({wc.pixel[0]},{wc.pixel[1]}) → klicke {pos_str}{else_str}"
            return f"warte {gone_str} bei ({wc.pixel[0]},{wc.pixel[1]}) → klicke {pos_str}{else_str}"
        elif self.delay_before > 0:
            return f"warte {self._delay_str()} → klicke {pos_str}"
        else:
            return f"sofort → klicke {pos_str}"

    def _trigger_str(self) -> str:
        """Was VOR der Aktion passiert: Farb-Bedingung und/oder Wartezeit.

        Taste und Scroll zeigten hier früher nur die Wartezeit. Eine Farb-Bedingung
        an so einem Schritt war damit unsichtbar — man konnte sie im edit-Menü setzen
        und sah sie in der Schritt-Liste nirgends wieder.
        """
        wc = self.wait_condition
        if not wc:
            return self._delay_str()
        zustand = "WEG" if wc.until_gone else "DA"
        pixel = f"({wc.pixel[0]},{wc.pixel[1]})"
        if wc.check_only:
            art = f"prüfe einmal ob Farbe {zustand} bei {pixel}"
        else:
            art = f"warte bis Farbe {zustand} bei {pixel}"
        if self.delay_before > 0:
            # "warte 2s, dann warte bis..." doppelt sich — die Vorlaufzeit sagt das schon.
            return f"warte {self._delay_str()}, dann {art.removeprefix('warte ')}"
        return art

    def _else_str(self) -> str:
        """Hilfsfunktion für Else-Anzeige."""
        ec = self.else_config
        if not ec:
            return ""
        if ec.action == ELSE_SKIP:
            return " | ELSE: skip"
        elif ec.action == ELSE_SKIP_CYCLE:
            return " | ELSE: skip_cycle"
        elif ec.action == ELSE_RESTART:
            return " | ELSE: restart"
        elif ec.action == ELSE_CLICK:
            name = ec.name or f"({ec.x},{ec.y})"
            return f" | ELSE: klicke {name}"
        elif ec.action == ELSE_KEY:
            return f" | ELSE: Taste '{ec.key}'"
        return ""

    def _delay_str(self) -> str:
        """Hilfsfunktion für Delay-Anzeige (fest oder Bereich)."""
        if self.delay_max and self.delay_max > self.delay_before:
            return f"{self.delay_before:.0f}-{self.delay_max:.0f}s"
        return f"{self.delay_before:.0f}s"

    def get_actual_delay(self) -> float:
        """Gibt die tatsächliche Verzögerung zurück (bei Bereich: zufällig)."""
        if self.delay_max and self.delay_max > self.delay_before:
            return random.uniform(self.delay_before, self.delay_max)
        return self.delay_before


@dataclass
class LoopPhase:
    """Eine Loop-Phase mit eigenen Schritten und Wiederholungen."""
    name: str
    steps: list[SequenceStep] = field(default_factory=list)
    repeat: int = 1  # Wie oft diese Phase wiederholt wird
    scheduled_start: Optional[str] = None  # Startzeit z.B. "12:30" – wartet bis diese Uhrzeit

    def __str__(self) -> str:
        step_count = len(self.steps)
        pixel_triggers = sum(1 for s in self.steps if s.wait_condition)
        trigger_str = f" [Farb: {pixel_triggers}]" if pixel_triggers > 0 else ""
        time_str = f" [Start: {self.scheduled_start}]" if self.scheduled_start else ""
        return f"{self.name}: {step_count} Schritte x{self.repeat}{trigger_str}{time_str}"


@dataclass
class Sequence:
    """Eine Klick-Sequenz mit Init-, Loop- und End-Phase."""
    name: str
    init_steps: list[SequenceStep] = field(default_factory=list)   # Einmalig vor allen Zyklen
    loop_phases: list[LoopPhase] = field(default_factory=list)     # Mehrere Loop-Phasen
    end_steps: list[SequenceStep] = field(default_factory=list)    # Einmalig nach allen Zyklen
    total_cycles: int = 1  # 0 = unendlich, >0 = wie oft alle Loops durchlaufen werden
    # Freitext-Beschreibung (was macht die Sequenz?) — wird beim Laden/Listen und
    # beim Export angezeigt, damit man/Empfänger weiß worum es geht. Reines
    # Hilfsdatum, beeinflusst die Ausführung NICHT.
    description: str = ""

    def __str__(self) -> str:
        init_count = len(self.init_steps)
        end_count = len(self.end_steps)
        loop_info = f"{len(self.loop_phases)} Loop(s)"
        if self.total_cycles == 0:
            loop_info += " ∞"
        elif self.total_cycles == 1:
            loop_info += " (1x)"
        else:
            loop_info += f" (x{self.total_cycles})"
        all_steps = self.init_steps + [s for lp in self.loop_phases for s in lp.steps] + self.end_steps
        pixel_triggers = sum(1 for s in all_steps if s.wait_condition)
        trigger_str = f" [Farb-Trigger: {pixel_triggers}]" if pixel_triggers > 0 else ""
        init_str = f"Init: {init_count}, " if init_count > 0 else ""
        end_str = f", End: {end_count}" if end_count > 0 else ""
        return f"{self.name} ({init_str}{loop_info}{end_str}){trigger_str}"

    def total_steps(self) -> int:
        return len(self.init_steps) + sum(len(lp.steps) for lp in self.loop_phases) + len(self.end_steps)


# =============================================================================
# ITEM-SCAN DATENKLASSEN
# =============================================================================
@dataclass
class ItemProfile:
    """Ein Item-Typ mit Marker-Farben und/oder Template-Matching."""
    name: str
    marker_colors: list[tuple[int, int, int]] = field(default_factory=list)  # Liste von (r,g,b) Marker-Farben
    # Kategorie für Prioritäts-Vergleich (z.B. "Hosen", "Jacken", "Juwelen")
    category: Optional[str] = None  # Wenn None, ist jedes Item seine eigene Kategorie
    priority: int = 1  # 1 = beste, höher = schlechter (innerhalb der Kategorie)
    # Referenz auf den Punkt, der nach dem Klick bestätigt (Popup o.ä.). DAS ist der
    # gespeicherte Wert; `confirm_point` darunter ist der abgeleitete Arbeitswert und
    # wird von `resolve_scan_references()` gefüllt.
    #
    # Der Editor fragt ohnehin nach einer Punkt-ID — die wurde bisher nur weggeworfen
    # und durch eine Koordinaten-Kopie ersetzt. Folge: den Punkt zu verschieben ließ
    # den Bestätigungsklick stehen, und die Kalibrierung brauchte einen Sonderfall.
    confirm_point_id: Optional[int] = None
    confirm_point: Optional[ClickPoint] = None  # abgeleitet: Punkt für die Bestätigung
    confirm_delay: float = 0.5  # Wartezeit vor Bestätigungs-Klick
    # Template Matching (optional - überschreibt marker_colors wenn gesetzt)
    template: Optional[str] = None  # Dateiname des Template-Bildes (in items/templates/)
    min_confidence: float = DEFAULT_MIN_CONFIDENCE  # Mindest-Konfidenz für Template-Match

    def __str__(self) -> str:
        if self.template:
            template_str = f"Template: {self.template} (≥{self.min_confidence:.0%})"
        else:
            colors_str = ", ".join([f"RGB{c}" for c in self.marker_colors[:3]])
            if len(self.marker_colors) > 3:
                colors_str += f" (+{len(self.marker_colors)-3})"
            template_str = colors_str if colors_str else "keine Marker"
        confirm_str = f" → ({self.confirm_point.x},{self.confirm_point.y})" if self.confirm_point else ""
        category_str = f" [{self.category}]" if self.category else ""
        return f"[P{self.priority}]{category_str} {self.name}: {template_str}{confirm_str}"


@dataclass
class ItemSlot:
    """Ein Slot wo Items erscheinen können."""
    name: str
    scan_region: tuple[int, int, int, int]  # (x1, y1, x2, y2) Bereich zum Scannen
    click_pos: tuple[int, int]              # (x, y) Wo geklickt werden soll
    slot_color: Optional[tuple[int, int, int]] = None  # RGB-Farbe des leeren Slots

    def __str__(self) -> str:
        r = self.scan_region
        color_str = f", Hintergrund: RGB{self.slot_color}" if self.slot_color else ""
        return f"{self.name}: Scan ({r[0]},{r[1]})-({r[2]},{r[3]}){color_str}"


@dataclass
class ItemScanConfig:
    """Konfiguration für Item-Erkennung und -Vergleich.

    WAS IN DER DATEI STEHT sind nur die Namen (`slot_names`, `item_names`). Slots und
    Items selbst leben in slots/slots.json bzw. items/items.json - der Scan verweist
    darauf, statt sie zu kopieren.

    Vorher lag jedes Item zweimal auf Platte: global und vollständig eingebettet in jedem
    Scan, der es benutzt. Änderte man die Marker-Farben des globalen Items, passierte im
    Scan nichts. Dass das wehtat, sieht man daran, dass es `update_item_in_scans()` gab -
    eine Funktion, die nach einem Umbenennen alle Scan-Dateien nachzieht. Genau dieselbe
    Falle wie bei den Punkten in Sequenzen.

    `slots` und `items` sind die AUFGELÖSTEN Arbeitslisten, gefüllt von
    `resolve_scan_references()`. Der Worker liest sie, die Editoren schreiben sie - beides
    unverändert. Nur gespeichert werden sie nicht mehr.
    """
    name: str
    slots: list[ItemSlot] = field(default_factory=list)      # aufgelöst, nicht gespeichert
    items: list[ItemProfile] = field(default_factory=list)   # aufgelöst, nicht gespeichert
    slot_names: list[str] = field(default_factory=list)      # das steht in der Datei
    item_names: list[str] = field(default_factory=list)      # das steht in der Datei
    color_tolerance: int = 40  # Farbtoleranz für Erkennung
    # Opt-in: unbekannte Slot-Inhalte beim Scannen automatisch als neue globale
    # Items lernen (Kategorie 'Auto', wird NICHT geklickt).
    learn_unknown: bool = False

    def __post_init__(self) -> None:
        self.sync_names()

    def sync_names(self) -> None:
        """Leitet fehlende Namenslisten aus den Objekten ab.

        DER GRUND: Namen und Objekte sind zwei Darstellungen derselben Sache, und wer nur
        eine davon setzt, hinterlässt eine halbe Config. Genau das ist passiert - Editoren
        und Scan-Studio bauen die Config aus Objekten, der Loader aus Namen, und niemand
        füllte die jeweils andere Seite:

        * Beim Öffnen waren `slots`/`items` leer, also zeigte das Menü "0 Slots, 0 Items"
          und beim Bearbeiten war nichts vorausgewählt.
        * Beim Speichern waren `slot_names`/`item_names` leer - und
          `resolve_scan_references()` (läuft vor JEDEM Sequenzstart) leerte daraufhin die
          Objekte. Ein gerade bearbeiteter Scan lief bis zum Neustart ins Leere.

        Die Namen sind die Wahrheit (sie stehen in der Datei), die Objekte werden
        aufgelöst. Diese Methode stellt sicher, dass die Wahrheit nie fehlt - egal von
        welcher Seite die Config gebaut wurde.
        """
        if not self.slot_names and self.slots:
            self.slot_names = [s.name for s in self.slots]
        if not self.item_names and self.items:
            self.item_names = [i.name for i in self.items]

    def __str__(self) -> str:
        learn_str = " [Auto-Lernen]" if self.learn_unknown else ""
        # Über die Namen zählen: frisch geladen sind die Objekte noch nicht aufgelöst,
        # und "0 Slots" wäre dann schlicht falsch.
        return (f"{self.name} ({len(self.slot_names)} Slots, "
                f"{len(self.item_names)} Items){learn_str}")


# =============================================================================
# BOSS-SCAN DATENKLASSEN
# =============================================================================
@dataclass
class BossProfile:
    """Ein Boss-Typ mit Erkennungsmethode und zugeordneter Aktion."""
    name: str
    marker_colors: list[tuple[int, int, int]] = field(default_factory=list)  # Farb-Marker
    template: Optional[str] = None              # Template-Bild (in items/templates/)
    min_confidence: float = DEFAULT_MIN_CONFIDENCE  # Für Template-Matching
    # Aktion wenn dieser Boss erkannt wird:
    action: str = BOSS_ACTION_SCAN              # "item_scan", "click", "key", "skip", "skip_cycle", "restart"
    action_scan: Optional[str] = None           # Name des Item-Scans (wenn action="item_scan")
    action_scan_mode: str = SCAN_MODE_ALL       # Scan-Modus ("all", "best", "every")
    # Referenz auf den Klick-Punkt (wenn action="click"). Gespeichert wird die ID,
    # action_x/y sind abgeleitet — siehe Block bei ElseConfig.
    action_point_id: Optional[int] = None
    action_x: int = 0                           # abgeleitet: Klick-X
    action_y: int = 0                           # abgeleitet: Klick-Y
    action_key: Optional[str] = None            # Taste (wenn action="key")
    action_delay: float = 0                     # Verzögerung vor Aktion

    def __str__(self) -> str:
        detect_parts = []
        if self.template:
            detect_parts.append(f"Template: {self.template} (≥{self.min_confidence:.0%})")
        if self.marker_colors:
            colors_str = ", ".join([f"RGB{c}" for c in self.marker_colors[:2]])
            if len(self.marker_colors) > 2:
                colors_str += f" (+{len(self.marker_colors)-2})"
            detect_parts.append(colors_str)
        detect_str = " + ".join(detect_parts) if detect_parts else "keine Erkennung"

        if self.action == BOSS_ACTION_SCAN:
            mode_strs = {SCAN_MODE_ALL: "alle", SCAN_MODE_BEST: "bestes", SCAN_MODE_EVERY: "jedes"}
            action_str = f"→ Scan '{self.action_scan}' ({mode_strs.get(self.action_scan_mode, self.action_scan_mode)})"
        elif self.action == BOSS_ACTION_CLICK:
            action_str = f"→ Klick ({self.action_x},{self.action_y})"
        elif self.action == BOSS_ACTION_KEY:
            action_str = f"→ Taste '{self.action_key}'"
        elif self.action == BOSS_ACTION_SKIP:
            action_str = "→ überspringen"
        elif self.action == BOSS_ACTION_SKIP_CYCLE:
            action_str = "→ Zyklus überspringen"
        elif self.action == BOSS_ACTION_RESTART:
            action_str = "→ Neustart"
        else:
            action_str = f"→ {self.action}"
        return f"{self.name}: {detect_str} {action_str}"


@dataclass
class BossScanConfig:
    """Konfiguration für Boss-Erkennung mit bedingten Aktionen."""
    name: str
    scan_region: tuple[int, int, int, int] = (0, 0, 100, 100)  # Feste Region wo der Boss erscheint
    bosses: list[BossProfile] = field(default_factory=list)      # Erkennbare Bosse (Reihenfolge = Priorität)
    color_tolerance: int = 30                                     # Farbtoleranz für Marker
    default_action: str = BOSS_ACTION_SKIP                        # Fallback wenn kein Boss erkannt
    default_scan: Optional[str] = None                            # Fallback Item-Scan
    # LLM Vision Erkennung (optional, zusätzlich zu Template/Marker)
    use_llm: bool = False                                         # LLM für Erkennung verwenden
    llm_fallback: bool = True                                     # LLM nur als Fallback (wenn Template/Marker nichts finden)
    # OCR-Texterkennung (optional, schnelle Alternative zu LLM)
    use_ocr: bool = False                                         # OCR für Boss-Name-Erkennung
    ocr_fallback: bool = True                                     # OCR nur als Fallback

    def __str__(self) -> str:
        r = self.scan_region
        tags = []
        if self.use_llm:
            tags.append("LLM")
        if self.use_ocr:
            tags.append("OCR")
        tag_str = f" [{'+'.join(tags)}]" if tags else ""
        return f"{self.name} ({len(self.bosses)} Bosse, Region ({r[0]},{r[1]})-({r[2]},{r[3]})){tag_str}"


@dataclass
class IconScanConfig:
    """Konfiguration für Icon-Erkennung in einer Region → Aktion.

    Erkennt ein einzelnes Symbol/Icon (z.B. ein rotes "!" das eine nicht
    machbare Mission markiert) per Template-Matching ODER Farb-Marker und führt
    bei Fund eine Aktion aus (Klick / Taste / Zyklus überspringen / ...).
    Kein Item-Sammeln, kein LLM — bewusst schlank gehalten.
    """
    name: str
    scan_region: tuple[int, int, int, int] = (0, 0, 100, 100)  # Region in der gesucht wird
    template: Optional[str] = None                              # Template-Bild (in items/templates/)
    min_confidence: float = DEFAULT_MIN_CONFIDENCE              # Mindest-Konfidenz für Template-Match
    marker_colors: list[tuple[int, int, int]] = field(default_factory=list)  # Alternativ: Farb-Marker
    color_tolerance: int = 30                                   # Farbtoleranz für Marker
    action: str = ICON_ACTION_CLICK                            # Aktion bei Fund (Standard: klicken)
    # Referenz auf den Klick-Punkt (wenn action="click"); action_x/y sind abgeleitet.
    action_point_id: Optional[int] = None
    action_x: int = 0                                          # abgeleitet: Klick-X
    action_y: int = 0                                          # abgeleitet: Klick-Y
    action_key: Optional[str] = None                           # Taste (wenn action="key")
    action_delay: float = 0                                    # Verzögerung vor der Aktion

    def __str__(self) -> str:
        r = self.scan_region
        if self.template:
            detect = f"Template: {self.template} (≥{self.min_confidence:.0%})"
        elif self.marker_colors:
            detect = f"{len(self.marker_colors)} Marker"
        else:
            detect = "keine Erkennung"
        if self.action == ICON_ACTION_CLICK:
            act = f"→ Klick ({self.action_x},{self.action_y})"
        elif self.action == ICON_ACTION_KEY:
            act = f"→ Taste '{self.action_key}'"
        else:
            act = f"→ {self.action}"
        return f"{self.name} ({detect}, Region ({r[0]},{r[1]})-({r[2]},{r[3]})) {act}"


# =============================================================================
# SEQUENZ-AUFNAHME
# =============================================================================
# Ereignisarten der Aufnahme. Frueher war jedes Ereignis ein Linksklick und lag als
# nacktes (t, x, y, color)-Tupel in der Liste; seit auch Tastendruck, Mausrad und
# Farb-Warten mitgeschnitten werden, muss die Art mitgefuehrt werden.
REC_CLICK = "click"         # Linksklick an (x, y)
REC_KEY = "key"             # Tastendruck (key)
REC_SCROLL = "scroll"       # Mausrad an (x, y), scroll = Rasterstufen (+ = hoch)
# Warte-Marker: "ab hier warte ich". Hat BEWUSST keine eigene Stelle — beim Drücken
# parkt die Maus irgendwo, und diese Stelle waere Zufall. Er haengt sich an den
# naechsten Klick und laesst DEN auf seine eigene Farbe warten.
REC_WAIT_COLOR = "wait"


@dataclass
class RecordEvent:
    """Ein aufgezeichnetes Ereignis der Sequenz-Aufnahme.

    Rein transient: lebt nur in `AutoClickerState.recording_events` und wird nie
    gespeichert — `stop_recording()` baut daraus SequenceSteps und wirft die Liste weg.
    Deshalb steht das hier auch ohne Serialisierer und ohne Default-Tabelle.
    """
    kind: str
    t: float                                    # time.monotonic() beim Auslösen
    x: int = 0
    y: int = 0
    color: Optional[tuple[int, int, int]] = None
    key: Optional[str] = None                   # nur REC_KEY
    scroll: int = 0                             # nur REC_SCROLL, Rasterstufen

    def __str__(self) -> str:
        if self.kind == REC_KEY:
            return f"Taste '{self.key}'"
        if self.kind == REC_SCROLL:
            richtung = "hoch" if self.scroll > 0 else "runter"
            return f"Scroll {richtung} x{abs(self.scroll)} bei ({self.x}, {self.y})"
        if self.kind == REC_WAIT_COLOR:
            return "Warte-Marker (nächster Klick wartet auf seine Farbe)"
        return f"Klick ({self.x}, {self.y})"


# =============================================================================
# AUTOCLICKER STATE
# =============================================================================
@dataclass
class AutoClickerState:
    """Zustand des Autoclickers."""
    # Punkte-Pool (wiederverwendbar)
    points: list[ClickPoint] = field(default_factory=list)

    # Manueller Modus: Sequenz Schritt für Schritt auf Bestätigung, Wartezeiten
    # übersprungen. Bewusst Laufzeit-Zustand statt Config - im Punkte-Menü
    # (CTRL+ALT+P -> 'manuell') umschaltbar. Mutation unter state.lock.
    step_mode: bool = False

    # Gespeicherte Sequenzen
    sequences: dict[str, Sequence] = field(default_factory=dict)

    # Globale Slots und Items (wiederverwendbar)
    global_slots: dict[str, ItemSlot] = field(default_factory=dict)
    global_items: dict[str, ItemProfile] = field(default_factory=dict)

    # Item-Scan Konfigurationen (verknüpft Slots + Items)
    item_scans: dict[str, ItemScanConfig] = field(default_factory=dict)

    # Boss-Scan Konfigurationen (Boss erkennen → bedingte Aktion)
    boss_scans: dict[str, BossScanConfig] = field(default_factory=dict)

    # Globale Boss-Bibliothek: gilt zusätzlich in JEDEM Boss-Scan.
    # Lokale Bosse eines Scans haben bei Namensgleichheit Vorrang.
    global_bosses: list[BossProfile] = field(default_factory=list)

    # Icon-Scan Konfigurationen (Symbol/Icon erkennen → Aktion)
    icon_scans: dict[str, IconScanConfig] = field(default_factory=dict)

    # Aktive Sequenz
    active_sequence: Optional[Sequence] = None

    # Laufzeit-Status
    is_running: bool = False
    total_clicks: int = 0

    # Statistiken
    items_found: int = 0
    key_presses: int = 0
    skipped_cycles: int = 0
    restarts: int = 0
    timeouts: int = 0
    consecutive_timeouts: int = 0
    start_time: Optional[float] = None

    # Bereits geklickte Kategorien im aktuellen Zyklus mit bester Priorität
    # Dict: {kategorie: beste_priorität} - verhindert schlechtere Items derselben Kategorie
    clicked_categories: dict[str, int] = field(default_factory=dict)

    # Thread-sichere Events
    stop_event: threading.Event = field(default_factory=threading.Event)
    quit_event: threading.Event = field(default_factory=threading.Event)
    pause_event: threading.Event = field(default_factory=threading.Event)
    skip_event: threading.Event = field(default_factory=threading.Event)
    restart_event: threading.Event = field(default_factory=threading.Event)
    skip_cycle_event: threading.Event = field(default_factory=threading.Event)
    finish_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    # Eigener Lock NUR für Maus/Tastatur-Eingaben (SetCursorPos + SendInput).
    # Garantiert echte Mutual-Exclusion zwischen Sequenz-Worker und dem
    # asynchronen LLM-Boss-Thread — verhindert interleaved Klicks an falscher
    # Position. WICHTIG: input_lock niemals nehmen während state.lock gehalten
    # wird (Deadlock-Gefahr — strikte Lock-Reihenfolge).
    input_lock: threading.Lock = field(default_factory=threading.Lock)

    # Flag für aktiven Countdown (verhindert Sequenz-Start durch CTRL+ALT+S)
    countdown_active: bool = False

    # Screenshot-Ordner für die aktuelle Sequenz-Session (z.B. "slots/Screenshots/2025-01-15_14-30-00")
    session_screenshots_dir: Optional[Path] = None

    # Session-Log (CSV) für die aktuelle Sequenz (None wenn deaktiviert)
    session_log: Optional[object] = None

    # Neu entdeckte Boss-Namen in dieser Session (zur Bestätigung am Ende)
    # Liste von (config_name, boss_name, quelle) Tupeln — quelle z.B. "LLM" oder "OCR"
    pending_new_bosses: list = field(default_factory=list)

    # Zeitpunkt der letzten Humanize-Break (Monotone Zeit)
    humanize_last_break: float = 0.0

    # LLM Async-Thread (Boss-Scan/Watcher läuft im Hintergrund)
    llm_thread: Optional[threading.Thread] = None
    llm_action_event: threading.Event = field(default_factory=threading.Event)

    # Set für einmalige Konfigurations-Warnungen pro Worker-Lauf (z.B. "use_llm aber !llm_enabled").
    # Wird beim Sequenz-Start in sequence_worker geleert. Zugriff unter state.lock.
    warned_inconsistencies: set = field(default_factory=set)

    # Konfiguration (thread-safe über lock)
    config: AppConfig = field(default_factory=AppConfig)

    # Sequenz-Aufnahme (Maus-Hook + Tastatur-Hook)
    recording_active: bool = False
    # Pausiert die laufende Aufnahme: Ereignisse werden ignoriert, ohne die Aufnahme
    # zu beenden (z.B. um im Spiel zu navigieren). Toggle via CTRL+ALT+H.
    recording_paused: bool = False
    # Liste von RecordEvent. Zugriff unter state.lock - der Maus- und der
    # Tastatur-Hook schreiben aus der Message-Pump, die Hotkey-Handler lesen.
    recording_events: list = field(default_factory=list)
