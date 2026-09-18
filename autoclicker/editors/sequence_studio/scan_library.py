"""Öffnen, Pflegen und Speichern von Item-Scan-Konfigurationen."""

from typing import Optional

from ...models import ItemScanConfig
from ...utils import unique_name, sanitize_filename
from .scan_contract import ART_ITEM, ART_SCAN, ART_SLOT, referenzen_umbenennen


class ScanLibraryMixin:
    """Verwaltet die Scan-Bibliothek und ihre Beziehungen zu Slots und Items."""

    def scan_open(self, data: Optional[dict] = None) -> dict:
        """Wählt den Item-Scan, in dessen Zusammenhang gearbeitet wird.

        Der Scan ist hier das Übergeordnete: mit mehreren Spielen liegen sonst
        alle Slots und Items aller Spiele in einer Liste, und keine davon gehört
        sichtbar irgendwohin. Ist einer offen, zeigen die Listen standardmässig
        nur seine Mitglieder, und sein Bild kommt gleich mit.

        Ein leerer Name macht ihn wieder zu — dann sieht man den ganzen Bestand.
        """
        name = str((data or {}).get("name") or "")
        self._scan_load()
        if name and name not in self.scans:
            return self._scan_report(f"Scan '{name}' gibt es nicht.", "err")
        self.scan_offen = name
        self._scan_working_set(name)
        self._treffer = {}
        if name:
            self.scan_art, self.scan_name = ART_SCAN, name
            if not self._photo_load(name):
                # Ein älterer Scan bringt Slots mit, aber kein gemerktes Bild.
                # Dass seine Slots trotzdem dastehen, ist die halbe Antwort auf
                # „warum ist die Mitte leer" — die andere Hälfte ist der Knopf.
                source = self.scans[name].capture_window_title
                quelltext = (f" Fenster '{source}' ist momentan nicht offen."
                             if source and not self.scan_fenster_id else "")
                if self._canvas_area():
                    return self._scan_report(
                        f"'{name}' geöffnet — kein Bild gemerkt, die Slots stehen "
                        "trotzdem. „Screenshot aufnehmen“ legt das Spiel dahinter."
                        + quelltext,
                        "info")
                return self._scan_report(
                    f"'{name}' geöffnet — noch kein Bild dazu. Screenshot aufnehmen."
                    + quelltext,
                    "info")
            source = self.scans[name].capture_window_title
            if source and not self.scan_fenster_id:
                return self._scan_report(
                    f"'{name}' geöffnet, Bild von zuletzt. Fenster '{source}' ist "
                    "momentan nicht offen.", "warn")
            return self._scan_report(f"'{name}' geöffnet, Bild von zuletzt.")
        self._foto = None
        self._foto_bild = ""
        self._foto_info = None
        self.scan_bereich = None
        self.scan_fenster_id = 0
        return self._scan_report("Kein Scan offen — der ganze Bestand steht da.", "info")

    def scan_new(self, data: Optional[dict] = None) -> dict:
        """Eine neue Item-Scan-Konfiguration — leer, aber mit eindeutigem Namen.

        **Erst laden, dann anlegen.** `_scan_load()` ersetzt `self.scans`
        komplett durch das, was auf Platte steht — passiert es NACH dem Anlegen,
        ist der frische Scan wieder weg. In der Oberfläche fällt das nicht auf
        (der Reiter zeichnet beim Öffnen und lädt dabei), über die Brücke
        aufgerufen aber sehr wohl.
        """
        self._scan_load()
        name = unique_name(str((data or {}).get("name") or "Neuer Scan"), self.scans)
        self._remember("Scan angelegt")
        self.scans[name] = ItemScanConfig(name=name)
        self.scans[name].owner_sequence = self.board.name
        self.scan_art, self.scan_name = ART_SCAN, name
        # Ein frisch angelegter Scan ist der, an dem man arbeitet — sonst müsste
        # man ihn direkt danach noch einmal auswählen.
        self.scan_offen = name
        self._scan_working_set(name)
        # Eine Aufnahme ohne Scan hatte früher kein Speicherziel. Falls aus
        # einer bereits offenen Sitzung noch so ein verwaistes Bild da ist,
        # darf ein anschliessend angelegter Scan es nicht still übernehmen.
        self._foto = None
        self._foto_bild = ""
        self._foto_info = None
        self.scan_bereich = None
        self.scan_fenster_id = 0
        return self._scan_changed(f"Scan '{name}' angelegt und geöffnet.")

    def scan_set(self, data: dict) -> dict:
        """Ein Feld einer Scan-Konfiguration."""
        name = str((data or {}).get("name") or "")
        field = str((data or {}).get("field") or "")
        value = (data or {}).get("value")
        cfg = self.scans.get(name)
        if cfg is None:
            return self._scan_report(f"Scan '{name}' gibt es nicht.", "err")

        if field == "name":
            new = sanitize_filename(str(value or "").strip())
            if not new or new == cfg.name:
                return self.scan_data()
            if new in self.scans:
                return self._scan_report(f"'{new}' gibt es schon.", "warn")
            self._remember(f"Scan '{cfg.name}' umbenannt")
            old = cfg.name
            self.scans = {(new if k == old else k): v for k, v in self.scans.items()}
            cfg.name = new
            self.scan_name = new
            if self.scan_offen == old:
                self.scan_offen = new
            # Der Name IST die Referenz, und sie steht an ZWEI Stellen: im
            # Schritt und als Fallback-Scan eines Boss-Scans, den
            # `runtime/steps.py` bei „kein Boss erkannt" wirklich ausfuehrt.
            # Ohne die zweite lief der Fallback nach dem Umbenennen ins Leere.
            referenzen_umbenennen(self.board, "item", old, new)
            for boss_cfg in getattr(self, "boss_scans", {}).values():
                if boss_cfg.default_scan == old:
                    boss_cfg.default_scan = new
            # Das Erinnerungsbild gehört zum Scan, nicht zum Dateinamen.
            try:
                self._photo_path(old).replace(self._photo_path(new))
            except OSError:
                pass
            alt_pfad = self.filepath.parent / "item_scans" / f"{sanitize_filename(old)}.json"
            try:
                alt_pfad.unlink(missing_ok=True)
            except OSError:
                return self._scan_report(
                    f"'{old}' wurde umbenannt, die alte Datei blieb liegen.", "warn")
            return self._scan_changed(
                f"'{old}' heisst jetzt '{new}'.")
        if field == "tolerance":
            try:
                tolerance = int(value)
            except (TypeError, ValueError):
                return self._scan_report(
                    "Die Farb-Toleranz muss eine ganze Zahl sein.", "err")
            self._remember(f"'{name}': Farb-Toleranz")
            cfg.color_tolerance = max(0, tolerance)
            return self._scan_changed()
        if field == "lernen":
            self._remember(f"'{name}': Unbekanntes lernen")
            cfg.learn_unknown = bool(value)
            return self._scan_changed()
        if field == "use_catalog":
            self._remember(f"'{name}': Katalog")
            cfg.use_catalog = bool(value)
            return self._scan_changed(
                f"'{cfg.name}': Katalog {'an' if cfg.use_catalog else 'aus'}")
        if field == "reverse":
            self._remember(f"'{name}': Laufrichtung")
            cfg.reverse = bool(value)
            return self._scan_changed(
                f"'{cfg.name}': Slots laufen "
                f"{'rückwärts' if cfg.reverse else 'vorwärts'}")
        return self._scan_report(f"Unbekanntes Feld '{field}'.", "err")

    def scan_delete_all(self, data: dict) -> dict:
        """Löscht alle Slots bzw. alle Items dieses Scans auf einen Schlag.

        Einzeln durchzuklicken war bei fünfzig Stück der Grund, warum man diesen
        Knopf sucht.

        Der Bezug ist derselbe wie überall: der offene Scan, sonst der ganze
        Bestand (`_scan_slots()` / `_candidates()`) — dieselbe Regel wie bei
        „N Items prüfen & lernen".

        Kein Bestätigungsdialog, aus demselben Grund wie beim einzelnen
        Löschen: STRG+Z holt den ganzen Stand zurück, auch diesen.
        """
        kind = str((data or {}).get("kind") or "")
        if kind == ART_SLOT:
            names = [s.name for s in self._scan_slots()]
            if not names:
                return self._scan_report("Keine Slots zum Löschen.", "warn")
            self._auswahl = names
            return self.scan_slot_delete()
        if kind == ART_ITEM:
            names = [i.name for i in self._candidates()]
            if not names:
                return self._scan_report("Keine Items zum Löschen.", "warn")
            self._remember(f"{len(names)} Item(s) gelöscht" if len(names) > 1
                        else f"'{names[0]}' gelöscht")
            for name in names:
                del self.items[name]
            self._sync_objects()
            self.scan_name = ""
            was = f"'{names[0]}'" if len(names) == 1 else f"{len(names)} Items"
            return self._scan_changed(f"{was} gelöscht.", "warn")
        return self._scan_report(f"Unbekannte Art '{kind}'.", "err")

    def scan_toggle_all(self, data: dict) -> dict:
        """Schaltet alle Slots oder Items des offenen Scans gemeinsam ein/aus."""
        kind = str((data or {}).get("kind") or "")
        active = bool((data or {}).get("active"))
        if kind == ART_SLOT:
            entries = self._scan_slots()
            bezeichnung = "Slots"
        elif kind == ART_ITEM:
            entries = list(self.items.values())
            bezeichnung = "Items"
        else:
            return self._scan_report(f"Unbekannte Art '{kind}'.", "err")
        if not entries:
            return self._scan_report(f"Keine {bezeichnung} zum Schalten.", "warn")
        changed = [e for e in entries if e.enabled != active]
        if not changed:
            return self.scan_data()
        self._remember(f"{len(entries)} {bezeichnung}: {'ein' if active else 'aus'}")
        for entry in entries:
            entry.enabled = active
        return self._scan_changed(
            f"Alle {len(entries)} {bezeichnung} sind "
            f"{'eingeschaltet' if active else 'ausgeschaltet'}.")

    def scan_delete(self, data: Optional[dict] = None) -> dict:
        """Löscht die offene Scan-Konfiguration samt Datei."""
        # Die Scan-Maske kennt ihren Namen selbst und schickt ihn mit. Der
        # globale Auswahlzustand kann inzwischen schon wieder auf einem Slot
        # oder Item stehen; davon darf der Löschknopf seiner sichtbaren Maske
        # nicht abhängen. Ohne Namen bleibt der offene Scan der sinnvolle
        # Rückfall für ältere Aufrufer.
        name = str((data or {}).get("name") or self.scan_offen)
        if name not in self.scans:
            return self._scan_report("Kein Scan gewählt.", "warn")
        # STRG+Z holt die Konfiguration zurück, nicht die Dateien: die JSON
        # schreibt das nächste Speichern neu, der gemerkte Screenshot ist weg.
        self._remember(f"Scan '{name}' gelöscht (Bild bleibt weg)")
        del self.scans[name]
        self.scan_name = ""
        if self.scan_offen == name:
            self.scan_offen = ""
        try:
            self._photo_path(name).unlink(missing_ok=True)
        except OSError:
            pass
        path = self.filepath.parent / "item_scans" / f"{sanitize_filename(name)}.json"
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return self._scan_report(f"'{name}' entfernt, die Datei blieb liegen.", "warn")
        # Auch Löschen ist ein eigener Schreibvorgang: es dreht die
        # Änderungszeit des Ordners weiter.
        self._disk_track(self.filepath.parent / "item_scans")
        return self._scan_report(f"Scan '{name}' gelöscht.", "warn")

    # --------------------------------------------------------------- Sichern

    def scan_save(self, data: Optional[dict] = None) -> dict:
        """Schreibt Slots, Items und alle Scan-Konfigurationen.

        Ein Knopf für alle Dateiarten des Reiters, weil sie zusammen entstehen:
        wer einen Slot anlegt, lernt daraus ein Item und hängt beides in einen
        Scan; wer eine Boss-Region aufzieht, nimmt gleich die Vorlage auf.
        Getrennte Knöpfe hiessen, sich diese Reihenfolge merken zu müssen.

        **Die Punkte gehen mit.** Ein Klickpunkt einer Boss- oder Icon-Aktion
        ist ein Punkt in `sequence.json` — die Koordinate steht dort und sonst
        nirgends. Bliebe er ungeschrieben, zeigte die gespeicherte Aktion beim
        nächsten Start ins Leere.

        Danach erfährt der Hauptprozess davon (Briefkasten-Befehl `data`) —
        sonst arbeitete er bis zum nächsten `CTRL+ALT+L` mit dem alten Stand.
        """
        from ...persistence import save_item_scan

        # Scan-Aktionen können neue Sequenzpunkte anlegen, ohne einen Ablaufblock
        # zu verändern. Darum muss derselbe Knopf zuerst auch `sequence.json`
        # schreiben. Beim Umbenennen lädt `save()` den verschobenen Ordner
        # neu; die noch ungespeicherten Scan-Objekte halten wir über diesen
        # kurzen Schritt fest und schreiben sie danach in den neuen Ordner.
        arbeitsbestand = (
            self.slots, self.items, self.scans, self.boss_scans,
            self.icon_scans, self.global_bosses, self.scan_offen,
        )
        sequenz_antwort = self.save(data)
        if sequenz_antwort.get("question"):
            return self._scan_report(
                "Sequenz wurde ausserhalb geändert — zuerst im Sequenz-Reiter entscheiden.",
                "warn")
        sequenz_status = sequenz_antwort.get("status") or {}
        if sequenz_status.get("kind") == "err":
            return self._scan_report(
                sequenz_status.get("text") or "Sequenz konnte nicht gespeichert werden.",
                "err")
        (self.slots, self.items, self.scans, self.boss_scans,
         self.icon_scans, self.global_bosses, self.scan_offen) = arbeitsbestand

        fehler = []
        self._sync_objects()
        for cfg in self.scans.values():
            try:
                cfg.owner_sequence = self.board.name
                if not save_item_scan(cfg):
                    fehler.append(f"{cfg.name}.json")
            except (OSError, ValueError):
                fehler.append(f"{cfg.name}.json")
        fehler += self._detection_save()
        if fehler:
            return self._scan_report("Nicht geschrieben: " + ", ".join(fehler), "err")

        self._scan_dirty = False
        # Der eigene Schreibvorgang darf sich nicht selbst als Fremdaenderung
        # melden - sonst stuende der Hinweis nach jedem Speichern da.
        self._disk_track()
        from ...mailbox import send_command
        send_command("daten")
        return self._scan_report(
            f"{len(self.slots)} Slot(s), {len(self.items)} Item(s), "
            f"{len(self.scans)} Item-Scan(s), {len(self.boss_scans)} Boss-Scan(s), "
            f"{len(self.icon_scans)} Icon-Scan(s) gespeichert.")
