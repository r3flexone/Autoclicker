"""Zustand, Darstellung und Undo-Verlauf des Scan-Editors."""

import base64
import copy
import re as _re
from typing import Optional

from ...models import ItemProfile, ItemScanConfig, ItemSlot
from .model import hex_color
from .scan_contract import (
    SCAN_KINDS,
    KIND_SCAN,
    KIND_SLOT,
    MIN_SLOT,
    MODE_FIND,
    MODE_CHOICE,
    UNDO_DEPTH,
)
from .scan_model import existing_categories


def _natural_key(name: str) -> list:
    """Sortierschlüssel, der Zahlen als Zahlen liest: "Slot 2" vor "Slot 10"."""
    return [int(teil) if teil.isdigit() else teil.casefold()
            for teil in _re.split(r"(\d+)", name or "")]


class ScanStateMixin:
    """Verwaltet Scan-Zustand und erzeugt JSON-fähige Momentaufnahmen."""

    def _scan_init(self) -> None:
        """Wird aus `StudioBridge.__init__` gerufen."""
        self.slots: dict = {}
        self.items: dict = {}
        self.scans: dict = {}
        self._scan_state_snapshot: dict = {}            # Scan-Name -> mtime seiner Datei
        self._scan_loaded = False
        self._photo = None                      # PIL-Bild in Originalgrösse
        self._photo_image: str = ""              # data:-URL, verkleinert
        self._photo_info: Optional[dict] = None
        self._corner: Optional[tuple] = None     # erste Ecke beim Aufziehen
        # Worin die Slot-Erkennung sucht. Nur für den einen Durchgang, deshalb
        # nicht neben `scan_area`: der schränkt das BILD ein und gilt für
        # jede weitere Aufnahme, dieser hier schränkt eine SUCHE ein und ist
        # danach wieder weg.
        self._search_area: Optional[tuple] = None
        # Welcher Teil des Bildschirms aufgenommen wird. None = alles. Nicht in
        # der Scan-Datei, sondern IM gemerkten Bild: dessen Ursprung und Grösse
        # SIND der Bereich, und zwei Stellen für dieselbe Angabe liefen
        # auseinander.
        self.scan_area: Optional[tuple] = None
        # Das gewaehlte Fenster. Damit wird es DIREKT abgebildet, also auch
        # dann, wenn etwas davor liegt — allen voran dieses Studio. Nur fuer
        # die Sitzung: ein Fenster-Handle ueberlebt keinen Neustart, und ein
        # gespeichertes zeigte beim naechsten Mal irgendwohin.
        self.scan_window_id: int = 0
        self.scan_mode: str = MODE_CHOICE
        # Werkzeuge sind standardmaessig einmalig. Fuer Serien kann die Ansicht
        # sie anheften; dann bleibt der Modus nach einer erfolgreichen Aktion an.
        self.scan_tool_pinned: bool = False
        self.scan_kind: str = KIND_SLOT
        self.scan_name: str = ""
        # Die Slot-Auswahl. `scan_name` bleibt der EINE, an dem der Inspektor
        # arbeitet (Farbe messen, Klickpunkt, lernen); `_selection` ist die Menge,
        # auf der Sammel-Aktionen laufen. Dieselbe Trennung wie im
        # Sequenz-Editor, wo `sel_rows` neben dem angezeigten Block steht.
        self._selection: list = []
        # Der offene Item-Scan ist der ZUSAMMENHANG, nicht die Auswahl: wer
        # einen Slot anklickt, um ihn zu bearbeiten, arbeitet weiter an
        # demselben Scan. Vorher hing beides an `scan_kind`/`scan_name`, und ein
        # Klick auf einen Slot verlor den Zusammenhang.
        self.open_scan: str = ""
        # Welche der drei Ansichten den gemeinsamen Aufnahmebereich gerade
        # benutzt. Die Weboberfläche schickt die Art bei jedem Handgriff mit;
        # der Wert ist der Rückhalt für den anschliessenden Klick ins Bild.
        self.scan_capture_kind: str = "item"
        self._matches: dict = {}               # Slot-Name -> Erkennungsergebnis
        # Mehrfach-Lernen wird erst als Vorschau aufgebaut und danach bestaetigt.
        # PIL-Crops bleiben im Python-Prozess; die Seite erhaelt nur data:-Bilder.
        self._learn_review: list = []
        # Der Rückgängig-Stapel: `(Beschreibung, Abzug)` je Schritt, jüngster
        # zuletzt. Siehe `_remember()` — hier gab es bis dahin gar nichts, und ein
        # Rechteck über dreissig Slots plus Entf war endgültig.
        self._undo: list = []
        self._scan_dirty = False
        self._scan_status = ("", "info")
        self._preview: dict = {}              # Template-Datei -> (mtime, data-URL)
        # Wie die Dateien aussahen, als wir sie gelesen haben. Der Hauptprozess
        # schreibt dieselben — daran erkennt der Reiter, dass er veraltet ist.
        self._disk: dict = {}
        # Boss- und Icon-Scans liegen im selben Reiter, auf derselben Aufnahme
        # und mit demselben Rückgängig-Stapel. Ihr Zustand lebt in
        # `scan_detect.py`; von hier aus wird er nur mitgeführt.
        self._detection_init()

    def _scan_load(self) -> None:
        """Slots, Items und Scan-Konfigurationen von Platte — einmal je Sitzung.

        Nicht im Konstruktor: wer das Studio für eine Sequenz aufmacht, soll nicht
        auf Dateien warten, die er vielleicht nie ansieht. `_disk_state()` merkt
        sich dabei, wie sie aussahen — der Hauptprozess schreibt dieselben.
        """
        if self._scan_loaded:
            return
        self._scan_loaded = True
        self.scans = self._scans_load()
        self._detection_load()
        # Der zuletzt bearbeitete Scan ist offen — dieselbe Regel wie bei den
        # Sequenzen (`last_edited()` in `sequence_studio.py`) und aus
        # demselben Grund: ein echtes „zuletzt geöffnet" müsste jemand
        # mitschreiben, und das Dateisystem weiss es schon.
        #
        # Vorher öffnete sich nur bei GENAU EINEM Scan etwas. Wer einen zweiten
        # anlegte, sah beim nächsten Öffnen eine leere Mitte und musste erst
        # merken, dass oben links eine Auswahl steht.
        if self._scan_state_snapshot:
            neuster = max(self._scan_state_snapshot, key=lambda n: self._scan_state_snapshot[n])
            self.open_scan = neuster
            self._scan_working_set(neuster)
            self._photo_load(neuster)
        self._disk = self._disk_state()

    def _scan_has_config(self, kind: str) -> bool:
        """Ist für die gewünschte Aufnahmeart wirklich ein Scan geöffnet?"""
        if kind == "boss":
            return self.boss_open in self.boss_scans
        if kind == "icon":
            return self.icon_open in self.icon_scans
        return self.open_scan in self.scans

    def _scan_requirement(self, data: Optional[dict] = None) -> Optional[dict]:
        """Sperrt Aufnahme und Bildwerkzeuge ohne eindeutiges Speicherziel.

        Ein Bild oder Slot ohne Scan lebte vorher nur im Arbeitsspeicher. Beim
        Speichern gab es keine Konfiguration, der man ihn hätte zuordnen können;
        nach dem Schliessen war er weg. Darum gilt die Reihenfolge zentral in der
        Brücke und nicht nur als deaktivierter Knopf in der Seite.
        """
        self._scan_load()
        kind = str((data or {}).get("kind") or self.scan_capture_kind or "item")
        if kind not in SCAN_KINDS:
            kind = "item"
        self.scan_capture_kind = kind
        if self._scan_has_config(kind):
            return None
        name = {"item": "Item-Scan", "boss": "Boss-Scan", "icon": "Icon-Scan"}[kind]
        return self._scan_report(
            f"Zuerst einen {name} anlegen oder öffnen — erst danach können Bild "
            "und Bereiche dazu erfasst werden.", "warn")

    def _disk_state(self) -> dict:
        """Pfad -> Änderungszeit für alles, was der Reiter von Platte liest.

        Der Ordner der Scans kommt als Ganzes mit: eine gelöschte oder neu
        dazugekommene Datei ändert seinen eigenen Zeitstempel, und genau das
        soll auffallen.
        """
        stamp = {}
        scan_ordner = self.filepath.parent / "item_scans"
        paths = [scan_ordner]
        paths += sorted(scan_ordner.glob("*.json")) if scan_ordner.is_dir() else []
        # Boss- und Icon-Scans gehören dazu, seit der Reiter sie bearbeitet:
        # der Konsolen-Editor bleibt als zweiter Weg bestehen, und ein per LLM
        # entdeckter Boss landet im Lauf in der Bibliothek. Ohne diese Pfade
        # meldete „auf Platte hat sich etwas geändert" ausgerechnet das nicht,
        # woran man gerade arbeitet.
        paths += self._detection_paths()
        for p in paths:
            try:
                stamp[str(p)] = p.stat().st_mtime
            except OSError:
                stamp[str(p)] = 0.0
        return stamp

    def _disk_track(self, *paths) -> None:
        """Der eigene Schreibvorgang zählt nicht als Fremdänderung.

        Das gemerkte Bild liegt unter `item_scans/bilder/`, und das Anlegen des
        Unterordners dreht die Änderungszeit des Elternordners weiter — sonst meldete
        der Reiter direkt nach der eigenen Aufnahme eine Fremdänderung.

        Ohne Argumente der ganze Stand (nach dem Speichern), mit Argumenten nur die
        genannten Pfade — sonst verschluckt es eine fremde Änderung anderswo.
        """
        stamp = self._disk_state()
        if not paths:
            self._disk = stamp
            return
        for path in paths:
            if str(path) in stamp:
                self._disk[str(path)] = stamp[str(path)]

    def _disk_changed_externally(self) -> bool:
        """Hat jemand anders die Dateien angefasst, seit wir sie gelesen haben?

        „Jemand anders" ist im Alltag der eigene Hauptprozess: Auto-Lernen im
        Lauf schreibt `items.json`, der Konsolen-Editor schreibt Scans. Eigene
        Speicherungen zählen nicht mit — `scan_save()` zieht den Stand nach.
        """
        return bool(self._scan_loaded) and self._disk_state() != self._disk

    def scan_reload(self, data: Optional[dict] = None) -> dict:
        """Liest Slots, Items und Scans neu von Platte.

        **Ungespeichertes wird nicht kommentarlos verworfen.** Der erste Druck
        meldet nur, der zweite (mit `discard`) lädt — dieselbe Zwei-Schritt-
        Regel wie überall, wo hier etwas verloren gehen kann.
        """
        if self._scan_dirty and not (data or {}).get("discard"):
            return self._scan_report(
                "Es gibt ungespeicherte Änderungen. Nochmal „Neu laden“ verwirft sie "
                "— „Speichern“ behält sie.", "warn")
        remaining = self.open_scan
        self._scan_loaded = False
        self._corner = self._search_area = None
        self._selection, self._matches = [], {}
        self.scan_name, self.open_scan = "", ""
        self._preview = {}
        # Der Stapel beschreibt Stände, die es nach dem Neulesen nicht mehr
        # gibt. Ein Rückgängig darüber hinweg holte den Speicherstand von vorhin
        # zurück und überschriebe damit genau das, was gerade von Platte kam.
        self._undo = []
        self._scan_dirty = False
        self._boss_test_result = self._icon_test_result = None
        self._boss_test_results = {}
        self._region_target = None
        self._scan_load()
        # Der vorher offene Scan bleibt offen, wenn es ihn noch gibt — sonst
        # steht man nach dem Nachladen woanders als vorher.
        if remaining and remaining in self.scans:
            self.open_scan = remaining
            self.scan_kind, self.scan_name = KIND_SCAN, remaining
            self._photo_load(remaining)
        return self._scan_report(
            f"Neu geladen: {len(self.slots)} Slot(s), {len(self.items)} Item(s), "
            f"{len(self.scans)} Scan(s).")

    def _next_slot_id(self) -> int:
        """Die nächste freie Slot-ID — dieselbe Rechnung wie bei Punkten."""
        return max((s.id for s in self.slots.values()), default=0) + 1

    def _slot_ids_assign(self) -> None:
        """Backfill für Altbestand ohne Slot-ID.

        Neue Slots bekommen ihre ID bei der Entstehung (`scan_interaction.py`);
        ältere Dateien kennen das Feld noch nicht und laden mit `id=0`. Vergeben
        wird in stabiler Reihenfolge, sonst hinge die Zuteilung von der
        zufälligen Dict-Reihenfolge ab. Das ist ein Schreibzugriff wert — die ID
        soll ab jetzt feststehen, nicht bei jedem Start neu gewürfelt werden.

        **Stabil heisst hier natürlich sortiert, nicht Zeichen für Zeichen.**
        Ein reiner String-Vergleich stellt "Slot 10" zwischen "Slot 1" und
        "Slot 2"; bei sechzig durchnummerierten Slots bekam "Slot 2" damit die
        ID 12 und "Slot 3" die 23. Die IDs waren stabil und trotzdem
        unbrauchbar, weil sie in Sprüngen dastanden.
        """
        without = sorted((s for s in self.slots.values() if not s.id),
                      key=lambda s: _natural_key(s.name))
        if not without:
            return
        next_one = self._next_slot_id()
        for slot in without:
            slot.id = next_one
            next_one += 1
        self._scan_dirty = True

    def _scans_load(self) -> dict:
        """Alle Item-Scan-Konfigurationen als Name -> Config.

        Nebenbei wird der Änderungszeitpunkt jeder Datei gemerkt: daran hängt,
        welcher Scan beim Öffnen vorne steht.
        """
        from ...persistence import load_item_scan_file
        found = {}
        self._scan_state_snapshot = {}
        folder = self.filepath.parent / "item_scans"
        for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            cfg = load_item_scan_file(path, self.board.name)
            if cfg is None:
                continue
            key_name = cfg.name or path.stem
            found[key_name] = cfg
            try:
                self._scan_state_snapshot[key_name] = path.stat().st_mtime
            except OSError:
                self._scan_state_snapshot[key_name] = 0.0
        return found

    def _scan_working_set(self, name: str) -> None:
        """Bindet Listen und Werkzeuge an den Besitz des geöffneten Scans."""
        cfg = self.scans.get(name)
        self.slots = {slot.name: slot for slot in cfg.slots} if cfg else {}
        self.items = {item.name: item for item in cfg.items} if cfg else {}
        self._slot_ids_assign()

    def _sync_objects(self) -> None:
        """Schreibt den Arbeitsbestand in den geöffneten Scan zurück."""
        cfg = self.scans.get(self.open_scan)
        if cfg is not None:
            cfg.slots = list(self.slots.values())
            cfg.items = list(self.items.values())

    def _add_to_scan(self, kind: str, name: str) -> bool:
        """Nimmt einen frisch angelegten Slot bzw. ein Item in den offenen Scan.

        Wer in einem offenen Scan etwas anlegt, legt es für ihn an — sonst wäre es
        sofort wieder weg (die Listen zeigen nur die Mitglieder). Ohne offenen Scan
        passiert nichts. Gibt zurück, ob es eine Änderung war.
        """
        cfg = self.scans.get(self.open_scan)
        if cfg is None:
            return False
        inventory = self.slots if kind == KIND_SLOT else self.items
        if name not in inventory:
            return False
        self._sync_objects()
        return True

    def _scan_report(self, text: str, kind: str = "ok") -> dict:
        self._scan_status = (text, kind)
        return self.scan_data()

    def _scan_changed(self, text: str = "", kind: str = "ok") -> dict:
        self._scan_dirty = True
        return self._scan_report(text, kind) if text else self.scan_data()

    def _tool_done(self) -> None:
        """Einmal-Werkzeuge fallen nach erfolgreicher Aktion ins Auswaehlen zurueck."""
        if not self.scan_tool_pinned:
            self.scan_mode = MODE_CHOICE
            self._corner = None
            self._search_area = None
            # Das Ziel gehoerte zu genau diesem Durchgang. Bliebe es stehen,
            # wirkte der naechste Buchstabendruck auf einen Scan, den man
            # inzwischen gar nicht mehr offen hat.
            self._region_target = None

    # ----------------------------------------------------------- Rückgängig

    def _state(self) -> dict:
        """Ein vollständiger Abzug dessen, was dieser Reiter bearbeitet."""
        return {
            "slots": copy.deepcopy(self.slots),
            "items": copy.deepcopy(self.items),
            "scans": copy.deepcopy(self.scans),
            "kind": self.scan_kind,
            "name": self.scan_name,
            "selection": list(self._selection),
            "open": self.open_scan,
            "dirty": self._scan_dirty,
            "area": copy.deepcopy(self.scan_area),
            "window_id": self.scan_window_id,
            # Der Abzug ist vollständig oder er ist keiner: ein Rückgängig, das
            # die Slots zurückdreht und den Boss-Scan stehen lässt, wäre ein
            # halbes Zurück — und das ist schlimmer als gar keins.
            "detection": self._detection_state(),
        }

    def _remember(self, what: str) -> None:
        """Legt den Stand VOR einer Änderung auf den Rückgängig-Stapel.

        Ein vollständiger Abzug statt einzelner Rückwärts-Schritte: eine Aktion rührt
        hier fast immer an mehrere Stellen (ein gelöschter Slot verschwindet aus
        jedem Scan), und ein vergessener Rückwärts-Schritt drehte die Daten halb
        zurück. Aufgerufen von der Methode, die ändert — nicht von der Oberfläche.
        """
        self._undo.append((what, self._state()))
        del self._undo[:-UNDO_DEPTH]

    def scan_undo(self, data: Optional[dict] = None) -> dict:
        """Nimmt den letzten Schritt zurück (STRG+Z).

        Was auf Platte passiert ist, holt das nicht zurück: ein gelöschter Scan kommt
        als Konfiguration wieder, sein gemerkter Screenshot ist weg. Das steht in der
        Meldung, statt ein vollständiges Zurück zu versprechen.
        """
        if not self._undo:
            return self._scan_report("Nichts zum Rückgängigmachen.", "info")
        what, stamp = self._undo.pop()
        self.slots = stamp["slots"]
        self.items = stamp["items"]
        self.scans = stamp["scans"]
        self.scan_kind, self.scan_name = stamp["kind"], stamp["name"]
        self._selection = [n for n in stamp["selection"] if n in self.slots]
        self.open_scan = stamp["open"]
        self._scan_dirty = stamp["dirty"]
        self.scan_area = stamp.get("area")
        self.scan_window_id = stamp.get("window_id", 0)
        self._detection_undo(stamp.get("detection") or {})
        # Die Scan-Konfigurationen tragen abgeleitete Objektlisten; nach dem
        # Abzug zeigen sie auf Kopien statt auf die Slots in `self.slots`.
        self._sync_objects()
        # Ein Treffer gehört zu dem Slot-Stand, in dem er gemessen wurde. Was es
        # nicht mehr gibt, fliegt raus — der Rest bleibt gültig, denn das Bild
        # hat sich nicht geändert.
        self._matches = {n: t for n, t in self._matches.items() if n in self.slots}
        return self._scan_report(
            f"Rückgängig: {what}. ({len(self._undo)} weitere Schritte)"
            if self._undo else f"Rückgängig: {what}.", "warn")

    def _steps(self) -> list:
        """Die drei Schritte zu einem neuen Scan, mit ihrem Stand.

        Zwischen Schritt 2 und 3 liegt das Spiel: Slots nimmt man oft am leeren
        Inventar auf, „Items lernen" auf dem alten Bild lernt leere Slots.

        Der Stand wird abgeleitet, nicht mitgeschrieben — erledigt heisst: es ist da.
        """
        cfg = self.scans.get(self.open_scan)
        hat_slots = (any(s.enabled for s in cfg.slots) if cfg
                     else any(s.enabled for s in self.slots.values()))
        hat_items = (any(i.enabled for i in cfg.items) if cfg
                     else any(i.enabled for i in self.items.values()))
        raw = [
            (1, "Bild", "Aufnehmen — Vollbild, oder vorher rechts ein Fenster "
                "wählen.", self._photo is not None,
             "scan_screenshot", "Screenshot aufnehmen"),
            (2, "Slots", "Bereich um das Inventar aufziehen, dann auf einen "
                "LEEREN Slot-Hintergrund klicken.", hat_slots,
             "modus:" + MODE_FIND, "Slots finden"),
            (3, "Items", "Inventar im Spiel füllen, NEU aufnehmen, dann lernen.",
             hat_items, "scan_learn_preview", "Items prüfen & lernen"),
        ]
        remaining = [nr for nr, _, _, done, _, _ in raw if not done]
        current = remaining[0] if remaining else 0
        return [{"nr": nr, "title": title, "what": what, "done": done,
                 "current": nr == current, "command": command, "button": knopf}
                for nr, title, what, done, command, knopf in raw]

    def _canvas_area(self) -> Optional[dict]:
        """Die Arbeitsfläche: das Bild, sonst das Rechteck um die Slots.

        Ein älterer Scan bringt Slots mit, aber kein gemerktes Bild; ohne die
        Ersatzfläche stünde die Mitte leer, obwohl die Slots da sind. Alle
        Umrechnungen laufen über `left`/`top`/`scale` und stimmen genauso.
        `image` sagt, was von beidem dasteht.
        """
        if self._photo_info:
            return dict(self._photo_info, image=True)
        regionen = [s.scan_region for s in self._scan_slots() if s.scan_region]
        if not regionen:
            return None
        margin = 40
        left = min(r[0] for r in regionen) - margin
        top = min(r[1] for r in regionen) - margin
        right = max(r[2] for r in regionen) + margin
        bottom = max(r[3] for r in regionen) + margin
        return {"left": left, "top": top, "image": False, "scale": 1.0,
                "width": max(1, right - left), "height": max(1, bottom - top),
                "stamp": 0.0}

    def _scan_slots(self) -> list:
        """Die Slots des offenen Scans.

        `self.slots` ist bereits die gebundene Arbeitsansicht genau dieses
        Scans. Eine zweite Mitgliedsliste würde denselben Besitz nochmals und
        potenziell widersprüchlich ausdrücken.
        """
        return list(self.slots.values())

    # -------------------------------------------------------- Momentaufnahme

    def scan_data(self, data: Optional[dict] = None) -> dict:
        """Alles, was der Reiter zum Zeichnen braucht — ohne das Bild selbst."""
        # Lokal wie in `_catalog_check()`: `scan_state` soll `config` nicht
        # schon beim Import nachziehen. `CONFIG` und nicht `load_config()` —
        # es gibt EIN Config-Objekt pro Prozess, und der Einstellungen-Reiter
        # haelt es aktuell.
        from ...config import CONFIG
        self._scan_load()
        text, kind = self._scan_status
        cfg = self.scans.get(self.open_scan)
        dabei_slots = set(cfg.slot_names) if cfg else set()
        dabei_items = set(cfg.item_names) if cfg else set()
        # Einmal gerechnet: die Arbeitsfläche steht in der Aufnahme UND
        # entscheidet, welche fremden Slots gerade zu sehen sind.
        surface = self._canvas_area()
        # **Die Nummer eines Slots ist seine Stelle im Scan**, nicht eine
        # erfundene ID: `ItemSlot` hat keine, der Name IST der Schlüssel — und
        # genau diese Reihenfolge läuft `execute_item_scan()` ab. „#7" heisst
        # also „wird als siebter angesehen", und das ist die Frage, die man an
        # eine Nummer hat.
        aktive_slots = [s for s in cfg.slots if s.enabled] if cfg else []
        nummern = {s.name: i + 1 for i, s in enumerate(aktive_slots)}
        detected = self._detected_items()
        return {
            # Scan, Slots, Items und Vorlagen liegen im Ordner dieser Sequenz.
            # Der Bezug muss in der Ansicht vor der Aufnahme sichtbar sein;
            # nur aus dem aktuell offenen Editor darauf zu schliessen ist bei
            # mehreren Sequenzen zu fehleranfaellig.
            "sequence": self.board.name,
            "recording_ready": {
                kind: self._scan_has_config(kind) for kind in SCAN_KINDS
            },
            "mode": self.scan_mode,
            "tool_pinned": self.scan_tool_pinned,
            "corner": list(self._corner) if self._corner else None,
            # Der Suchbereich muss zu SEHEN sein, solange man noch die Farbe
            # zeigen soll — sonst klickt man den Hintergrund an und weiss nicht,
            # worin gesucht wird.
            "search_area": list(self._search_area) if self._search_area else None,
            "photo": surface,
            "slots": [self._slot_json(s, s.name in dabei_slots,
                                      nummern.get(s.name), len(aktive_slots),
                                      bool(cfg.reverse) if cfg else False)
                      for s in self.slots.values()],
            "items": [self._item_json(i, i.name in dabei_items, detected.get(i.name))
                      for i in self.items.values()],
            "scans": [self._scan_json(c) for c in self.scans.values()],
            "categories": existing_categories(self.items),
            # Ob der OFFENE Scan den Katalog benutzt UND eine Datei da ist. Die
            # Ansicht rechnet das nicht selbst nach: sie sieht `config.json`
            # nicht, und zwei Antworten auf dieselbe Frage liefen auseinander.
            "catalog_on": bool(self._catalog()),
            # Ob die Sammel-Benennung ueberhaupt etwas tun kann. Die Ansicht
            # sieht `config.json` nicht — ein Knopf, der jedes Mal nur „ist
            # nicht aktiviert" meldet, ist schlechter als keiner.
            "llm_on": bool(CONFIG.llm_enabled),
            # Laeuft gerade ein Benenn-Durchgang, und wie weit ist er?
            "autoname": self._autoname_state(),
            "area": list(self.scan_area) if self.scan_area else None,
            "window_id": self.scan_window_id,
            # Der Titel ist die dauerhafte Quelle, das HWND nur ihr aktueller
            # Sitzungswert. So bleibt in der Oberfläche auch bei geschlossenem
            # Spiel sichtbar, welches Fenster dieser Scan erwartet.
            "window_title": cfg.capture_window_title if cfg else None,
            "window_available": bool(self.scan_window_id),
            "window_reference": (list(cfg.capture_window_rect)
                                  if cfg and cfg.capture_window_rect else None),
            "steps": self._steps(),
            "open": self.open_scan,
            "choice": {"kind": self.scan_kind, "name": self.scan_name},
            # Die Menge, auf der Sammel-Aktionen laufen. `choice` bleibt der EINE,
            # den der Inspektor bearbeitet — zwei Dinge, zwei Felder.
            "selection": [n for n in self._selection if n in self.slots],
            # Was STRG+Z zurücknehmen würde. Der Knopf nennt es beim Namen: ein
            # „Rückgängig" ohne Angabe, WAS es rückgängig macht, drückt man
            # entweder gar nicht oder einmal zu oft.
            "undo": {"depth": len(self._undo),
                     "what": self._undo[-1][0] if self._undo else ""},
            "dirty": self._scan_dirty,
            # Hat der Hauptprozess die Dateien angefasst? Ein Lauf mit
            # Auto-Lernen tut das, und ohne diesen Hinweis sucht man die
            # gelernten Items im Reiter vergeblich.
            "foreign": self._disk_changed_externally(),
            "status": {"text": text, "kind": kind},
            "result": self._result_json(),
            "review": self._review_json(),
            # Beide sind optional und der Reiter sagt es, statt Knöpfe
            # anzubieten, die nichts tun: ohne Pillow gibt es kein Bild, ohne
            # OpenCV kein Template-Matching (also keine Erkennung und kein
            # Erkennen von Doppelten beim Lernen).
            "opencv": self._has_opencv(),
            "pillow": self._has_pillow(),
            # Boss- und Icon-Scans liegen in derselben Momentaufnahme: sie
            # teilen sich Bühne, Zoom, Rückgängig und Speichern-Knopf. Zwei
            # Aufnahmen hiessen zwei Wahrheiten über dasselbe Bild.
            **self._detection_json(),
        }

    def _result_json(self) -> Optional[dict]:
        """Kompakte Auswertung des letzten Testscans fuer die Ergebnisleiste."""
        if not self._matches:
            return None
        slots = self._scan_slots()
        slot_namen = {s.name for s in slots}
        match = {n: t for n, t in self._matches.items() if n in slot_namen}
        detected = [n for n, t in match.items() if t.get("name") and not t.get("foreign")]
        foreign = [n for n, t in match.items() if t.get("name") and t.get("foreign")]
        unbekannt = [n for n, t in match.items() if not t.get("name")]
        return {
            "total": len(slots), "detected": len(detected), "foreign": len(foreign),
            "unbekannt": len(unbekannt), "detected_slots": detected,
            "foreign_slots": foreign, "unknown_slots": unbekannt,
        }

    def _review_json(self) -> Optional[dict]:
        if not self._learn_review:
            return None
        return {
            "rows": [
                {k: v for k, v in line.items() if k != "crop"}
                for line in self._learn_review
            ],
            # Name ist zugleich die Item-Identitaet. Die Vorschlaege machen es
            # moeglich, eine weitere Slot-Groesse an ein bestehendes Item zu
            # haengen, statt aus Versehen ein zweites Item anzulegen.
            "item_names": sorted(self.items, key=str.casefold),
        }

    @staticmethod
    def _has_opencv() -> bool:
        try:
            from ...imaging import OPENCV_AVAILABLE
            return bool(OPENCV_AVAILABLE)
        except ImportError:
            return False

    @staticmethod
    def _has_pillow() -> bool:
        try:
            from ...imaging import PILLOW_AVAILABLE
            return bool(PILLOW_AVAILABLE)
        except ImportError:
            return False

    def _slot_json(self, slot: ItemSlot, included: bool = False,
                   number: Optional[int] = None, total: int = 0,
                   rueckwaerts: bool = False) -> dict:
        match = self._matches.get(slot.name)
        width = slot.scan_region[2] - slot.scan_region[0]
        height = slot.scan_region[3] - slot.scan_region[1]
        return {
            "included": included,
            "active": bool(slot.enabled),
            "name": slot.name,
            "region": list(slot.scan_region),
            "click_pos": list(slot.click_pos),
            "color": hex_color(slot.slot_color),
            "width": width,
            "height": height,
            # Zu klein, um je etwas zu erkennen — und im Bild kaum zu treffen.
            # Neu entstehen kann so einer nicht mehr; wer noch einen hat, soll
            # ihn in der LISTE finden, denn dort ist er so gross wie jeder
            # andere. Das ist der zweite Weg zum Löschen.
            "tiny": width < MIN_SLOT or height < MIN_SLOT,
            "match": match,
            # **Stabile Identität.** Bleibt beim Aus- und Wiedereinschalten
            # gleich; die laufende Nummer gehört dagegen nur aktiven Slots.
            "id": slot.id,
            # Die Stelle im offenen Scan (1-basiert) und die Stelle im LAUF —
            # die beiden gehen auseinander, sobald „Slots rückwärts" an ist.
            # Nur für den Tooltip und die Vorsortierung; angezeigt wird die ID.
            "number": number,
            "run_index": (total - number + 1) if (number and rueckwaerts) else number,
            "total": total,
        }

    def _detected_items(self) -> dict:
        """Item-Name -> die Slots, in denen es gerade erkannt wird.

        Ein erkanntes Item steht deshalb im Scan-Inspektor, bevor jemand es ein
        zweites Mal lernt. Der Slot-Name kommt mit: „erkannt" ohne Beleg ist eine
        Behauptung, und in der Item-Liste sah man vom Erkennen sonst gar nichts.
        """
        found: dict = {}
        for slot, entry in self._matches.items():
            name = entry.get("name")
            if name:
                found.setdefault(name, []).append(slot)
        return found

    def _item_json(self, item: ItemProfile, included: bool = False,
                   detected_in=None) -> dict:
        from ...imaging import template_size
        vorlagen = item.template_names()
        sizes = []
        for name in vorlagen:
            size = template_size(name, self.filepath.parent / "templates")
            if size and list(size) not in sizes:
                sizes.append(list(size))
        scan_groessen = []
        cfg = self.scans.get(self.open_scan)
        if cfg is not None:
            for slot_name in cfg.slot_names:
                slot = self.slots.get(slot_name)
                if slot is None:
                    continue
                region = slot.scan_region
                size = [region[2] - region[0], region[3] - region[1]]
                if size not in scan_groessen:
                    scan_groessen.append(size)
        fehlende_groessen = ([g for g in scan_groessen if g not in sizes]
                             if vorlagen else [])
        return {
            "included": included,
            "active": bool(item.enabled),
            # Gehört (noch) nicht dazu, wird aber gerade gesehen. Die Ansicht
            # zeigt genau diese beiden Sorten, alles Weitere auf Knopfdruck: ein
            # neuer Scan soll leer anfangen und nicht mit dem Bestand eines
            # fremden Spiels.
            "detected": bool(detected_in),
            # In WELCHEN Slots — sonst ist „erkannt" eine Behauptung ohne Beleg,
            # und bei einem Fehlgriff (zwei Items sehen sich ähnlich) fehlt
            # genau die Angabe, an der man ihn bemerkt.
            "detected_in": list(detected_in or []),
            "name": item.name,
            "category": item.category,
            "priority": item.priority,
            "confidence": item.min_confidence,
            "template": vorlagen[0] if vorlagen else None,
            "templates": vorlagen,
            "template_sizes": sizes,
            "missing_scan_sizes": fehlende_groessen,
            "marker": [hex_color(c) for c in item.marker_colors],
            # **Der Klick danach.** Manche Spiele fragen nach („wirklich
            # verkaufen?"), und ohne die Bestätigung bleibt das Popup stehen —
            # der nächste Slot wird dann gar nicht mehr erreicht. Das Feld gab
            # es im Modell und in den Konsolen-Editoren seit jeher; im Studio
            # war es die einzige Item-Eigenschaft ohne Bedienelement.
            "confirmation": self._confirmation_json(item),
            "confirmation_delay": item.confirm_delay,
            # Ein Profil ohne Template UND ohne Marker wird nie erkannt — das
            # sagt die Selbstdiagnose auch, nur eben erst beim Start.
            "silent": not vorlagen and not item.marker_colors,
        }

    def _confirmation_json(self, item: ItemProfile) -> Optional[dict]:
        """Der Bestätigungsklick eines Items — als Punkt, nie als Zahlenpaar.

        Die Koordinate steht in der Punktliste der `sequence.json`, sonst nirgends; `confirm_point`
        ist der abgeleitete Arbeitswert. Zeigt die Referenz ins Leere, wird das
        gesagt statt verschwiegen — ein Klick auf (0, 0) wäre schlimmer.
        """
        if item.confirm_point_id is None:
            return None
        point = next((p for p in self.points if p.id == item.confirm_point_id), None)
        if point is None:
            return {"point_id": item.confirm_point_id, "missing": True,
                    "text": f"Punkt #{item.confirm_point_id} fehlt"}
        return {"point_id": point.id, "missing": False,
                "text": (point.name or f"Punkt {point.id}")
                        + f" ({point.x}, {point.y})"}

    def _scan_json(self, cfg: ItemScanConfig) -> dict:
        return {
            "name": cfg.name,
            "slots": list(cfg.slot_names),
            "items": list(cfg.item_names),
            "tolerance": cfg.color_tolerance,
            "learn": bool(cfg.learn_unknown),
            "reverse": bool(cfg.reverse),
            "use_catalog": bool(cfg.use_catalog),
            "window": ({
                "title": cfg.capture_window_title,
                "instance": cfg.capture_window_index,
                "reference": (list(cfg.capture_window_rect)
                              if cfg.capture_window_rect else None),
            } if cfg.capture_window_title else None),
            # Namen, die es global nicht mehr gibt: der Scan läuft mit dem Rest
            # weiter, aber man soll es sehen, bevor er es meldet.
            "missing_items": ([n for n in cfg.slot_names if n not in self.slots] +
                        [n for n in cfg.item_names if n not in self.items]),
        }

    def scan_preview(self, data: Optional[dict] = None) -> dict:
        """Template-Bilder als data:-URLs — nur die angefragten Namen.

        Getrennt von `scan_data()` aus demselben Grund wie der Screenshot: bei
        fünfzig Items wären das 200 KB, die sonst bei jedem Klick mitliefen. Die
        Seite merkt sie sich und fragt nur nach, was sie noch nicht hat.
        """
        self._scan_load()
        names = (data or {}).get("names") or []
        result = {}
        for name in names:
            item = self.items.get(name)
            if item is None or not item.template_names():
                continue
            url = self._template_url(item.template_names()[0])
            if url:
                result[name] = url
        return result

    def _template_url(self, file_name: str) -> str:
        """Ein Template als data:-URL, gemerkt an mtime + Name."""
        path = self.filepath.parent / "templates" / file_name
        try:
            stamp = path.stat().st_mtime
        except OSError:
            return ""
        gemerkt = self._preview.get(file_name)
        if gemerkt and gemerkt[0] == stamp:
            return gemerkt[1]
        try:
            raw = path.read_bytes()
        except OSError:
            return ""
        url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        self._preview[file_name] = (stamp, url)
        return url

    # ------------------------------------------------------ Auswahl und Modus
