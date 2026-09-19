"""Reiter „Werkzeuge": prüfen und kalibrieren, ohne die Konsole.

Diese beiden Dinge gab es bisher nur im Punkte-Menü (`CTRL+ALT+P` → `check`,
`fix`) — also ausgerechnet die Handgriffe, die man nach einem Bildschirm-Umbau
braucht, und die man dann in einem Fenster sucht, das schon offen ist.

**Warum das hier laufen KANN, obwohl es Maus und Bildschirm braucht.** Der
Studio-Prozess sieht `AutoClickerState` nicht, aber er sieht sehr wohl das
Betriebssystem: der Scans-Reiter nimmt Screenshots auf, und `point_capture()`
liest die Mausposition über eine globale Taste. Genau dieselben zwei Griffe
braucht eine Kalibrierung. Der Umweg über den Briefkasten ist deshalb nur da
nötig, wo wirklich der Hauptprozess gemeint ist — bei der Klick-Runde, die einen
Maus-Hook installiert.

**Gerechnet wird mit denselben Funktionen wie in der Konsole**
(`import_export.calibrate_inventory`, `diagnostics.check_setup`). Eine zweite
Rechnung „für das Fenster" wäre eine, die etwas anderes tut als der Weg, den die
README beschreibt.
"""

from __future__ import annotations

from typing import Optional

from .bridge_contract import WAIT_TIMEOUT


# Was die Kalibrierung anfasst. Steht als Tabelle da, weil die Ansicht dieselben
# Schalter zeigt und der Test beide Seiten gegeneinander hält.
CALIB_EXTENT = (
    ("with_scans", "Scan-Regionen und Klickpunkte", True),
    ("with_sequences", "Screenshot-Bereiche in den Sequenzen", True),
    ("with_slots", "Slots", False),
)


class BridgeToolsMixin:
    """Prüfen, kalibrieren, Klick-Runde starten."""

    def _tools_init(self) -> None:
        # Eine angefangene Kalibrierung: Referenzpunkte und der daraus
        # gerechnete Transform. Reiner Sitzungszustand - gespeichert wird erst
        # beim Anwenden, und ein halb gesetzter Referenzpunkt darf nichts ändern.
        self._calib: dict = {}
        # Ob DIESES Fenster eine Klick-Runde gestartet hat. Nur dafür da, sie
        # beim Schliessen zu verwerfen: die Runde gehört dem Fenster, und wer es
        # zumacht, hat nicht übernommen.
        self._reclick_started = False

    # ------------------------------------------------------------ Momentaufnahme

    def tool_data(self, data: Optional[dict] = None) -> dict:
        """Alles, was der Reiter zeichnet. Eigener Gegenstand, nicht die Sequenz.

        Geht deshalb über `ask()` und nicht über `call()`: eine Antwort von hier
        als Momentaufnahme zu behandeln zerschösse den Editor-Zustand.
        """
        from ..sequence_recorder import RECORDING_HOTKEYS
        self._scan_load()
        return {
            "points": [{"id": p.id, "name": p.name or f"Punkt #{p.id}",
                        "x": p.x, "y": p.y,
                        "color": list(p.color) if p.color else None,
                        "usages": self._point_usages(p.id)}
                       for p in self.points],
            "calibration": self._calib_json(),
            # Dieselbe Zahl wie in der Momentaufnahme: mehrere Werkzeuge
            # hier warten mit der Maus auf ENTER und blockieren dabei die
            # Bruecke. Der Reiter braucht sie, ohne den Editor zu fragen.
            "wait_timeout": WAIT_TIMEOUT,
            "scope": [{"key": k, "text": t, "default_value": v}
                       for k, t, v in CALIB_EXTENT],
            "recording_keys": [list(line) for line in RECORDING_HOTKEYS],
            # Welche Sequenz offen ist, gehoert hierher: die Kopfleiste blendet
            # ihre Bedienelemente in diesem Reiter aus (er bearbeitet andere
            # Dateien), und ohne diese Angabe weiss man bei der Klick-Runde
            # nicht, welche Sequenz man gleich nachklickt.
            "sequence": self.board.name,
            # Jede Datei heisst nun `sequence.json`; unterscheidbar ist der
            # bereinigte Besitzer-Ordner.
            "file": self.filepath.parent.name,
            "open": bool(self._dirty),
            "running": self._running(),
        }

    def _point_usages(self, point_id: int, except_step=None) -> list[str]:
        """Alle Referenzen auf einen Punkt, lesbar für Löschschutz und UI.

        `except_step` nimmt einen Schritt heraus — der Inspektor fragt damit „wer
        benutzt diesen Punkt SONST noch", denn dass der gewählte Block ihn
        benutzt, weiss man dort schon.
        """
        out = []
        for lane in self.board.lanes:
            for nr, step in enumerate(lane.steps, 1):
                if step is except_step:
                    continue
                base_name = f"{lane.name} · Block {nr}"
                if step.point_id == point_id:
                    out.append(base_name + " · Stelle")
                if step.wait_condition and step.wait_condition.point_id == point_id:
                    out.append(base_name + " · Prüf-Pixel")
                if step.verify_condition and step.verify_condition.point_id == point_id:
                    out.append(base_name + " · Nachprüfung")
                if step.else_config and step.else_config.point_id == point_id:
                    out.append(base_name + " · ELSE")
        for item in self.items.values():
            if item.confirm_point_id == point_id:
                out.append(f"Item '{item.name}' · Bestätigung")
        for name, cfg in self.boss_scans.items():
            for boss in cfg.bosses:
                if boss.action_point_id == point_id:
                    out.append(f"Boss '{boss.name}' in '{name}' · Aktion")
        for boss in self.global_bosses:
            if boss.action_point_id == point_id:
                out.append(f"Boss '{boss.name}' aus Bibliothek · Aktion")
        for name, cfg in self.icon_scans.items():
            if cfg.action_point_id == point_id:
                out.append(f"Icon-Scan '{name}' · Aktion")
        return out

    # --------------------------------------------------------- Punkte verwalten

    def tool_point_capture(self, data: Optional[dict] = None) -> dict:
        """Legt einen freien Punkt an oder misst einen vorhandenen neu."""
        if self._running():
            return {"ok": False, "message": "Eine Sequenz läuft — die Maus gehört dem Worker."}
        data = data or {}
        point = self._point_with_id(data.get("point_id"))
        x, y, message = self._await_position()
        if x is None:
            return {"ok": False, "message": message + " — nichts geändert."}
        color = self._color_at(x, y)
        if point is None:
            from .model import PalettePoint
            point = PalettePoint(
                id=max((p.id for p in self.points), default=0) + 1,
                x=x, y=y,
                name=str(data.get("name") or "Neuer Punkt").strip() or "Neuer Punkt",
                color=tuple(color) if color else None,
                source="Sequenz-Studio",
            )
            self.points.append(point)
            action = "angelegt"
        else:
            point.x, point.y = x, y
            if color:
                point.color = tuple(color)
            action = "neu gemessen"
        self._points_apply()
        self._dirty = True
        return {"ok": True, "point_id": point.id,
                "message": f"Punkt #{point.id} {action}: ({x}, {y})."}

    def tool_point_set(self, data: Optional[dict] = None) -> dict:
        """Ändert Name, Koordinate oder Farbe eines Punktes aus der Werkzeugliste."""
        data = data or {}
        point = self._point_with_id(data.get("point_id"))
        if point is None:
            return {"ok": False, "message": "Punkt nicht gefunden."}
        field, value = str(data.get("field") or ""), data.get("value")
        try:
            if field in ("x", "y"):
                setattr(point, field, int(value))
            elif field == "name":
                point.name = str(value or "").strip()
            elif field == "color":
                from .model import rgb_value
                point.color = rgb_value(value)
            else:
                return {"ok": False, "message": f"Unbekanntes Feld '{field}'."}
        except (TypeError, ValueError):
            return {"ok": False, "message": f"'{value}' ist kein gültiger Wert."}
        self._points_apply()
        self._dirty = True
        return {"ok": True, "message": f"Punkt #{point.id} geändert."}

    def tool_point_show(self, data: Optional[dict] = None) -> dict:
        """Fährt einen Punkt an und liefert gespeicherte sowie aktuelle Farbe."""
        if self._running():
            return {"ok": False, "message": "Eine Sequenz läuft — die Maus gehört dem Worker."}
        point = self._point_with_id((data or {}).get("point_id"))
        if point is None:
            return {"ok": False, "message": "Punkt nicht gefunden."}
        from ...winapi import set_cursor_pos
        set_cursor_pos(point.x, point.y)
        current = self._color_at(point.x, point.y)
        return {"ok": True, "point_id": point.id,
                "saved": list(point.color) if point.color else None,
                "current": list(current) if current else None,
                "message": f"Maus steht auf Punkt #{point.id} ({point.x}, {point.y})."}

    def tool_point_delete(self, data: Optional[dict] = None) -> dict:
        """Löscht nur unbenutzte Punkte; Referenzen werden nie still gebrochen."""
        point = self._point_with_id((data or {}).get("point_id"))
        if point is None:
            return {"ok": False, "message": "Punkt nicht gefunden."}
        used = self._point_usages(point.id)
        if used:
            return {"ok": False, "usages": used,
                    "message": f"Punkt #{point.id} wird noch {len(used)}× verwendet."}
        self.points.remove(point)
        self._dirty = True
        return {"ok": True, "message": f"Punkt #{point.id} gelöscht."}

    # ---------------------------------------------------------- Farbanalysator

    def tool_colors(self, data: Optional[dict] = None) -> dict:
        """Farbe unter der Maus oder häufigste Farben einer Region/Vollbild."""
        if self._running():
            return {"ok": False, "message": "Eine Sequenz läuft — Analyse ist gesperrt."}
        kind = str((data or {}).get("kind") or "point")
        if kind == "point":
            x, y, message = self._await_position()
            if x is None:
                return {"ok": False, "message": message + " — nichts analysiert."}
            color = self._color_at(x, y)
            if not color:
                return {"ok": False, "message": "Farbe konnte nicht gelesen werden."}
            from ...imaging import get_color_name
            return {"ok": True, "kind": "point", "position": [x, y],
                    "colors": [self._color_json(tuple(color), 1, 1, get_color_name)],
                    "message": f"Farbe bei ({x}, {y}) gelesen."}

        region = None
        if kind == "region":
            x1, y1, message = self._await_position()
            if x1 is None:
                return {"ok": False, "message": message + " — keine erste Ecke."}
            x2, y2, message = self._await_position()
            if x2 is None:
                return {"ok": False, "message": message + " — keine zweite Ecke."}
            region = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            if region[2] - region[0] < 2 or region[3] - region[1] < 2:
                return {"ok": False, "message": "Der gewählte Bereich ist zu klein."}
        elif kind == "fullscreen":
            # ENTER ist die Übergabe: Das Studio kann in den Hintergrund, bevor
            # der Screenshot entsteht.
            _, _, message = self._await_position()
            if message:
                return {"ok": False, "message": message + " — nichts analysiert."}
        else:
            return {"ok": False, "message": "Unbekannte Analyseart."}

        from ...imaging import analyze_screen_colors, get_color_name
        counters = analyze_screen_colors(region)
        if not counters:
            return {"ok": False, "message": "Keine Farben gefunden (Pillow installiert?)."}
        total = sum(counters.values())
        top = sorted(counters.items(), key=lambda e: e[1], reverse=True)[:20]
        return {"ok": True, "kind": kind, "region": list(region) if region else None,
                "colors": [self._color_json(f, n, total, get_color_name) for f, n in top],
                "message": f"{total} Stichproben analysiert."}

    @staticmethod
    def _color_json(color, count: int, total: int, name_function) -> dict:
        r, g, b = (int(v) for v in color[:3])
        return {"rgb": [r, g, b], "hex": f"#{r:02X}{g:02X}{b:02X}",
                "name": name_function((r, g, b)), "count": int(count),
                "share_pct": round(100.0 * count / max(1, total), 1)}

    def _running(self) -> bool:
        """Läuft gerade eine Sequenz? Aus der Statusdatei, wie im Live-Run."""
        try:
            stamp = self.run_status()
        except Exception:                                        # noqa: BLE001
            return False
        return bool(isinstance(stamp, dict) and stamp.get("active"))

    def _calib_json(self) -> dict:
        """Der Stand der laufenden Kalibrierung — leer, solange keine läuft."""
        if not self._calib:
            return {}
        transform = self._calib.get("transform") or {}
        return {
            "ref1": self._calib.get("ref1"),
            "ref2": self._calib.get("ref2"),
            "offset": {"x": round(transform.get("offset_x", 0.0), 1),
                        "y": round(transform.get("offset_y", 0.0), 1)},
            "scaling": {"x": round(transform.get("scale_x", 1.0), 4),
                           "y": round(transform.get("scale_y", 1.0), 4)},
            "identity": self._is_identity(transform),
            "preview": self._calib.get("preview", []),
        }

    @staticmethod
    def _is_identity(transform: dict) -> bool:
        if not transform:
            return True
        from ...import_export import is_identity
        return bool(is_identity(transform))

    # ------------------------------------------------------------------ Prüfen

    def tool_check(self, data: Optional[dict] = None) -> dict:
        """`check` aus dem Punkte-Menü: fehlende Templates, tote Verweise, Koordinaten.

        Gerechnet wird auf einem frischen State von Platte, nicht auf dem, was
        die Reiter gerade offen haben — sonst prüfte der Bericht einen Ausschnitt
        und meldete „sauber", weil er die halben Daten gar nicht kennt.
        """
        from ...diagnostics import LEVEL_ERROR, check_setup
        try:
            report = check_setup(self._inventory())
        except Exception as e:                                   # noqa: BLE001
            return {"ok": False, "message": f"Prüfung fehlgeschlagen: {e}",
                    "findings": [], "checked": []}
        return {
            "ok": True,
            "findings": [{"level": b.level, "area": b.area, "text": b.text,
                         "tip": b.tip} for b in report.befunde],
            "checked": list(report.checked),
            "errors": sum(1 for b in report.befunde if b.level == LEVEL_ERROR),
            "hints": sum(1 for b in report.befunde if b.level != LEVEL_ERROR),
        }

    # ------------------------------------------------------------- Kalibrieren

    def calib_reference(self, data: dict) -> dict:
        """Einen Referenzpunkt neu setzen: Maus auf die Stelle, ENTER.

        `number` ist 1 oder 2. Der erste Punkt gibt die Verschiebung, der zweite
        zusätzlich die Skalierung — den braucht man nur, wenn sich auch die
        Auflösung geändert hat.

        Der gewählte Punkt liefert die ALTE Stelle aus `sequence.json`, die Maus
        die neue. Beides zusammen ist der Transform, mehr steckt nicht dahinter.

        **Die Farbe wird gegengeprüft, und zwar bevor etwas gilt.** Ein
        Referenzpunkt, der danebenliegt, verschiebt nicht sich selbst, sondern
        ALLES — das ist der eine Handgriff, bei dem ein Vergreifen den ganzen
        Bestand kostet. Weicht die Farbe an der neuen Stelle von der
        gespeicherten ab, kommt deshalb `confirm` zurück statt eines
        gesetzten Punktes. Mit `bestaetigt: true` gilt er trotzdem: manchmal hat
        sich das Spiel geändert, und dann ist die abweichende Farbe richtig.
        Verboten wird nichts, es geht nur nicht mehr aus Versehen.
        """
        data = data or {}
        number = 2 if int(data.get("number") or 1) == 2 else 1
        point = self._point_with_id(data.get("point_id"))
        if point is None:
            return {"ok": False, "message": "Punkt nicht gefunden."}
        if number == 2 and not self._calib.get("ref1"):
            return {"ok": False, "message": "Erst den ersten Referenzpunkt setzen."}
        if number == 2 and self._calib["ref1"]["point_id"] == point.id:
            return {"ok": False,
                    "message": "Der zweite Punkt muss ein anderer sein — "
                               "am besten weit weg vom ersten."}

        x, y, message = self._await_position()
        if x is None:
            return {"ok": False, "message": message + " — nichts geändert."}

        check_result = self._color_check(point, x, y)
        if check_result is not None and not data.get("confirmed"):
            return check_result

        self._calib[f"ref{number}"] = {
            "point_id": point.id, "name": point.name or f"Punkt #{point.id}",
            "alt": [point.x, point.y], "neu": [x, y],
        }
        if number == 1:
            # Ein neuer erster Punkt macht den zweiten bedeutungslos: er wurde
            # gegen eine andere Verschiebung gemessen.
            self._calib.pop("ref2", None)
        self._calib_compute()
        measured = self._color_at(x, y)
        extra = ""
        if check_result is not None:
            extra = " — Farbe weicht ab, trotzdem übernommen"
        elif measured and point.color:
            extra = " — Farbe passt"
        return {"ok": True, "message": f"{point.name or point.id}: "
                                       f"({point.x}, {point.y}) → ({x}, {y}){extra}"}

    @staticmethod
    def _color_at(x: int, y: int):
        """Die Bildschirmfarbe an einer Stelle — oder None, wenn nicht lesbar."""
        try:
            from ...imaging import get_pixel_color
            return get_pixel_color(x, y)
        except Exception:                                        # noqa: BLE001
            return None

    def _color_check(self, point, x: int, y: int) -> Optional[dict]:
        """`None`, wenn die Farbe passt — sonst die Rückfrage.

        Verglichen wird mit `punkt_farbtoleranz`, derselben Schwelle, an der auch
        `point_at_position()` entscheidet, ob zwei Stellen dieselbe sind. Zwei
        Toleranzen für dieselbe Frage wären zwei Antworten.

        Fehlt eine der beiden Farben, wird NICHT gefragt: ein Punkt ohne
        gespeicherte Farbe (von Hand angelegt) hat nichts, womit man vergleichen
        könnte, und eine Rückfrage ohne Grundlage gewöhnt man sich ab wegzuklicken.
        """
        from ...config import CONFIG
        if not point.color:
            return None
        measured = self._color_at(x, y)
        if not measured:
            return None
        distance = max(abs(a - b) for a, b in zip(point.color, measured))
        if distance <= CONFIG.punkt_farbtoleranz:
            return None
        return {
            "ok": False,
            "confirm": True,
            "point_id": point.id,
            "expected": list(point.color),
            "measured": list(measured),
            "gap": distance,
            "tolerance": CONFIG.punkt_farbtoleranz,
            "position": [x, y],
            "message": (f"Andere Farbe als gespeichert (Abstand {distance}, erlaubt "
                        f"{CONFIG.punkt_farbtoleranz}). Triffst du wirklich "
                        f"'{point.name or point.id}'?"),
        }

    def calib_offset(self, data: dict) -> dict:
        """Den gemessenen Versatz von Hand nachziehen.

        Mit der Maus trifft man den Pixel nicht genau. Weiss man, dass eine Achse
        stimmt, ist eine erzwungene 0 genauer als jede Messung — dasselbe
        Zugeständnis macht der Konsolen-Weg mit `_adjust_offset()`.
        """
        if not self._calib.get("transform"):
            return {"ok": False, "message": "Es läuft keine Kalibrierung."}
        transform = dict(self._calib["transform"])
        for axis in ("x", "y"):
            value = (data or {}).get(axis)
            if value is None or value == "":
                continue
            try:
                transform[f"offset_{axis}"] = float(value)
            except (TypeError, ValueError):
                return {"ok": False, "message": f"'{value}' ist keine Zahl."}
        self._calib["transform"] = transform
        self._calib_preview()
        return {"ok": True, "message": "Versatz übernommen."}

    def calib_cancel(self, data: Optional[dict] = None) -> dict:
        """Alles vergessen. Geschrieben wurde bis hierher nichts."""
        self._calib = {}
        return {"ok": True, "message": "Kalibrierung verworfen — nichts geändert."}

    def calib_apply(self, data: Optional[dict] = None) -> dict:
        """Sichern, umrechnen, den Hauptprozess neu laden lassen.

        Vor dem Umrechnen entsteht ein vollständiges Export-ZIP
        (`backup_before_calibration`): die Kalibrierung schreibt Punkte, Slots,
        Scans und Sequenzdateien in einem Rutsch um, und ohne Rückweg wäre ein
        danebenliegender Referenzpunkt teuer.

        `with_slots` steht getrennt und ist standardmässig AUS: eine aus einer
        Mausposition abgeleitete Verschiebung ist für ein Klickziel gut genug,
        für eine Scan-Region aber nur eine Näherung — dafür gibt es `repair`,
        das die Slots misst. Nach einer Reparatur dürfen sie kein zweites Mal
        wandern.
        """
        from ...import_export import calibrate_inventory, backup_before_calibration
        transform = self._calib.get("transform")
        if not transform:
            return {"ok": False, "message": "Es läuft keine Kalibrierung."}
        if self._is_identity(transform):
            return {"ok": False,
                    "message": "Der Transform ändert nichts — nichts zu tun."}
        if self._running():
            return {"ok": False,
                    "message": "Eine Sequenz läuft. Erst stoppen — sonst klickt "
                               "sie mitten im Umrechnen auf halb verschobene Stellen."}

        extent = {k: bool((data or {}).get(k, v)) for k, _, v in CALIB_EXTENT}
        state = self._inventory()
        backup = backup_before_calibration(state)
        try:
            tally = calibrate_inventory(state, transform, **extent)
        except Exception as e:                                   # noqa: BLE001
            return {"ok": False, "message": f"Kalibrierung fehlgeschlagen: {e}"}

        self._calib = {}
        self._after_calibration()
        parts = ", ".join(f"{n} {name}" for name, n in sorted(tally.items()) if n)
        message = f"Kalibriert: {parts or 'nichts geändert'}."
        if backup:
            message += f" Sicherung: {backup}"
        return {"ok": True, "message": message, "backup": backup or ""}

    def _after_calibration(self) -> None:
        """Beide Seiten auf den neuen Stand: der Reiter und der Hauptprozess."""
        from .model import load_palette_points
        from ...mailbox import send_command
        self.points = load_palette_points(self.filepath)
        # Der Hauptprozess hält seinen eigenen Stand im Speicher und merkt von
        # geschriebenen Dateien nichts. Ohne das klickt er bis zum nächsten
        # Neustart auf die alten Stellen.
        send_command("data_reload")

    def _point_with_id(self, point_id):
        try:
            wanted = int(point_id)
        except (TypeError, ValueError):
            return None
        return next((p for p in self.points if p.id == wanted), None)

    def _calib_compute(self) -> None:
        """Aus den gesetzten Referenzpunkten einen Transform bauen."""
        from ...import_export import compute_transform, transform_from_offset
        ref1 = self._calib.get("ref1")
        if not ref1:
            self._calib.pop("transform", None)
            return
        ref2 = self._calib.get("ref2")
        if ref2:
            self._calib["transform"] = compute_transform(
                tuple(ref1["alt"]), tuple(ref2["alt"]),
                tuple(ref1["neu"]), tuple(ref2["neu"]))
        else:
            self._calib["transform"] = transform_from_offset(
                tuple(ref1["alt"]), tuple(ref1["neu"]))
        self._calib_preview()

    def _calib_preview(self) -> None:
        """Was sich ändern WÜRDE — ohne etwas anzufassen.

        Der Grund, warum die Kalibrierung im Fenster besser ist als in der
        Konsole: dort scrollt die Liste weg, hier steht sie neben dem Knopf.
        """
        from ...import_export import calibration_preview
        transform = self._calib.get("transform")
        if not transform:
            self._calib["preview"] = []
            return
        try:
            lines = calibration_preview(self._inventory(), transform)
        except Exception:                                        # noqa: BLE001
            self._calib["preview"] = []
            return
        self._calib["preview"] = [
            {"what": str(what), "before": list(before), "after": list(after)}
            for what, before, after in lines[:40]
        ]

    # -------------------------------------------------------------- Klick-Runde

    def reclick_start(self, data: Optional[dict] = None) -> dict:
        """Die Klick-Runde im HAUPTPROZESS starten (`click_value` im Punkte-Menü).

        Das eine Werkzeug, das hier nicht laufen kann: es braucht einen
        systemweiten Maus-Hook, und der gehört dem Prozess, der auch die Hotkeys
        pumpt — sonst gingen `CTRL+ALT+K`/`U`/`H`/`J` ins Leere. Deshalb der
        Briefkasten; bedient wird danach im Spiel, nicht im Fenster.
        """
        from ...mailbox import send_command
        if self._running():
            return {"ok": False,
                    "message": "Eine Sequenz läuft — Nachklicken braucht die "
                               "Maus für sich."}
        if self._dirty:
            return {"ok": False,
                    "message": "Erst speichern: die Runde klickt die Sequenz von "
                               "Platte nach, nicht die im Fenster."}
        # Die Datei MIT: der Hauptprozess hat womoeglich eine ganz andere Sequenz
        # geladen als die hier offene. Ohne sie klickt man eine Runde lang die
        # Punkte einer fremden Sequenz nach - dieselbe Falle, die `command_start`
        # laengst vermeidet.
        if not send_command("reclick", file=str(self.filepath)):
            return {"ok": False, "message": "Befehl konnte nicht abgelegt werden."}
        self._reclick_started = True
        return {"ok": True,
                "message": f"Nachklicken für '{self.board.name}' gestartet — der "
                           "Zeiger steht auf dem ersten Punkt, geklickt wird im Spiel."}

    def reclick_end(self, data: Optional[dict] = None) -> dict:
        """Die Runde beenden — übernehmen oder verwerfen (`verwerfen: true`).

        Ein Knopf, der etwas anfängt, muss es auch beenden können. Ohne das bleibt
        man mit einem scharfen Maus-Hook sitzen und der Frage, wie man ihn wieder
        los wird — die Antwort stand nur im Konsolenfenster.

        **Zwei Ausgänge, weil es zwei Absichten gibt.** Übernehmen ist der
        einzige Weg, auf dem die Runde je etwas schreibt; verwerfen lässt
        den Punkt-Pool in `sequence.json` unberührt. Ein einzelner „Beenden"-Knopf müsste sich für
        eine der beiden entscheiden und läge in der Hälfte der Fälle falsch.

        Ob überhaupt eine Runde läuft, weiss dieser Prozess nicht (der Zustand
        liegt im `AutoClickerState` drüben). Deshalb wird der Befehl immer
        abgelegt, und der Hauptprozess sagt, was er vorgefunden hat — das ist
        ehrlicher, als hier zu raten und den Knopf womöglich zu sperren, während
        sehr wohl eine Runde läuft.
        """
        from ...mailbox import send_command
        discard = bool((data or {}).get("discard"))
        # Warum verworfen wurde, weiss nur der Aufrufer — der Hauptprozess kann
        # den Knopf nicht vom geschlossenen Fenster unterscheiden.
        reason = str((data or {}).get("reason") or "button")
        if not send_command("reclick_stop", discard="1" if discard else "0",
                     reason=reason):
            return {"ok": False, "message": "Befehl konnte nicht abgelegt werden."}
        self._reclick_started = False
        return {"ok": True,
                "message": ("Verworfen — sequence.json bleibt, wie sie war."
                            if discard else
                            "Übernommen — was gesetzt wurde, steht im "
                            "Konsolenfenster.")}

    # Aelter als das gilt ein Stand als verwaist — dieselbe Rechnung wie beim
    # Laufstatus. Die Runde schreibt bei jeder Bewegung; bleibt sie laenger
    # stumm, ist der Hauptprozess weg und nicht etwa besonders langsam.
    RECLICK_MAX_AGE = 5.0

    def reclick_status(self, data: Optional[dict] = None) -> dict:
        """Was die Runde GERADE macht — gelesen aus `.reclick.json`.

        Der Zustand liegt im Hauptprozess (dort haengt der Maus-Hook), und ohne
        diesen Rueckkanal stand im Fenster nur „gestartet": welcher Punkt dran
        ist, wie weit die Runde ist und was mit den vorherigen passierte, meldete
        allein die Konsole. Genau das braucht man aber waehrend des Klickens, und
        zwar dort, wo die Knoepfe sind.

        Reine Auskunft, also `ask()`-Kanal: eine Momentaufnahme kommt hier nicht
        zurueck, und ueber `call()` geholt zerschoesse die Antwort den Editor.
        """
        import json
        import time
        from ...config import RECLICK_STATUS_FILE
        empty = {"active": False, "index": 0, "total": 0, "history": [],
                "point": {}, "orphaned": False}
        try:
            with open(RECLICK_STATUS_FILE, "r", encoding="utf-8") as f:
                stamp = json.load(f)
        except (OSError, ValueError):
            return empty
        if not isinstance(stamp, dict):
            return empty
        # Ein abgestuerzter Hauptprozess hinterlaesst ein „aktiv" ohne jemanden
        # dahinter. Am Alter erkennbar, und nur solange es aktiv behauptet: eine
        # abgeschlossene Runde ist Vergangenheit und darf alt sein.
        old = time.time() - float(stamp.get("stamp") or 0)
        stamp["orphaned"] = bool(stamp.get("active") and old > self.RECLICK_MAX_AGE)
        return stamp

    def reclick_on_close(self) -> None:
        """Beim Zumachen des Fensters: eine offene Runde verwerfen.

        Sie gehört diesem Fenster — es hat sie gestartet, und seine Anleitung ist
        der einzige Ort, an dem steht, wie man sie bedient. Ohne das bliebe ein
        scharfer Maus-Hook im Hauptprozess zurück, der jeden Klick des Nutzers
        gegen eine Punktliste rechnet, die er nirgends mehr sehen kann.
        """
        if not self._reclick_started:
            return
        self.reclick_end({"discard": True, "reason": "window"})
