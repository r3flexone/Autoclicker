"""Reiter „Werkzeuge": prüfen und kalibrieren, ohne die Konsole.

Diese beiden Dinge gab es bisher nur im Punkte-Menü (`CTRL+ALT+P` → `check`,
`fix`) — also ausgerechnet die Handgriffe, die man nach einem Bildschirm-Umbau
braucht, und die man dann in einem Fenster sucht, das schon offen ist.

**Warum das hier laufen KANN, obwohl es Maus und Bildschirm braucht.** Der
Studio-Prozess sieht `AutoClickerState` nicht, aber er sieht sehr wohl das
Betriebssystem: der Scans-Reiter nimmt Screenshots auf, und `punkt_aufnehmen()`
liest die Mausposition über eine globale Taste. Genau dieselben zwei Griffe
braucht eine Kalibrierung. Der Umweg über den Briefkasten ist deshalb nur da
nötig, wo wirklich der Hauptprozess gemeint ist — bei der Klick-Runde, die einen
Maus-Hook installiert.

**Gerechnet wird mit denselben Funktionen wie in der Konsole**
(`import_export.kalibriere_bestand`, `diagnose.pruefe_setup`). Eine zweite
Rechnung „für das Fenster" wäre eine, die etwas anderes tut als der Weg, den die
README beschreibt.
"""

from __future__ import annotations

from typing import Optional


# Was die Kalibrierung anfasst. Steht als Tabelle da, weil die Ansicht dieselben
# Schalter zeigt und der Test beide Seiten gegeneinander hält.
KALIB_UMFANG = (
    ("mit_scans", "Scan-Regionen und Klickpunkte", True),
    ("mit_sequenzen", "Screenshot-Bereiche in den Sequenzen", True),
    ("mit_slots", "Slots", False),
)


class BridgeWerkzeugeMixin:
    """Prüfen, kalibrieren, Klick-Runde starten."""

    def _werkzeuge_init(self) -> None:
        # Eine angefangene Kalibrierung: Referenzpunkte und der daraus
        # gerechnete Transform. Reiner Sitzungszustand - gespeichert wird erst
        # beim Anwenden, und ein halb gesetzter Referenzpunkt darf nichts ändern.
        self._kalib: dict = {}

    # ------------------------------------------------------------ Momentaufnahme

    def werkzeug_daten(self, daten: Optional[dict] = None) -> dict:
        """Alles, was der Reiter zeichnet. Eigener Gegenstand, nicht die Sequenz.

        Geht deshalb über `frage()` und nicht über `ruf()`: eine Antwort von hier
        als Momentaufnahme zu behandeln zerschösse den Editor-Zustand.
        """
        return {
            "punkte": [{"id": p.id, "name": p.name or f"Punkt #{p.id}",
                        "x": p.x, "y": p.y}
                       for p in self.points],
            "kalibrierung": self._kalib_json(),
            "umfang": [{"schluessel": k, "text": t, "vorgabe": v}
                       for k, t, v in KALIB_UMFANG],
            "sequenz": self.board.name,
            "laeuft": self._laeuft(),
        }

    def _laeuft(self) -> bool:
        """Läuft gerade eine Sequenz? Aus der Statusdatei, wie im Live-Run."""
        try:
            stand = self.lauf_status()
        except Exception:                                        # noqa: BLE001
            return False
        return bool(isinstance(stand, dict) and stand.get("aktiv"))

    def _kalib_json(self) -> dict:
        """Der Stand der laufenden Kalibrierung — leer, solange keine läuft."""
        if not self._kalib:
            return {}
        transform = self._kalib.get("transform") or {}
        return {
            "ref1": self._kalib.get("ref1"),
            "ref2": self._kalib.get("ref2"),
            "versatz": {"x": round(transform.get("offset_x", 0.0), 1),
                        "y": round(transform.get("offset_y", 0.0), 1)},
            "skalierung": {"x": round(transform.get("scale_x", 1.0), 4),
                           "y": round(transform.get("scale_y", 1.0), 4)},
            "identitaet": self._ist_identitaet(transform),
            "vorschau": self._kalib.get("vorschau", []),
        }

    @staticmethod
    def _ist_identitaet(transform: dict) -> bool:
        if not transform:
            return True
        from ...import_export import ist_identitaet
        return bool(ist_identitaet(transform))

    # ------------------------------------------------------------------ Prüfen

    def werkzeug_pruefen(self, daten: Optional[dict] = None) -> dict:
        """`check` aus dem Punkte-Menü: fehlende Templates, tote Verweise, Koordinaten.

        Gerechnet wird auf einem frischen State von Platte, nicht auf dem, was
        die Reiter gerade offen haben — sonst prüfte der Bericht einen Ausschnitt
        und meldete „sauber", weil er die halben Daten gar nicht kennt.
        """
        from ...diagnose import STUFE_FEHLER, pruefe_setup
        try:
            bericht = pruefe_setup(self._bestand())
        except Exception as e:                                   # noqa: BLE001
            return {"ok": False, "meldung": f"Prüfung fehlgeschlagen: {e}",
                    "befunde": [], "geprueft": []}
        return {
            "ok": True,
            "befunde": [{"stufe": b.stufe, "bereich": b.bereich, "text": b.text,
                         "tipp": b.tipp} for b in bericht.befunde],
            "geprueft": list(bericht.geprueft),
            "fehler": sum(1 for b in bericht.befunde if b.stufe == STUFE_FEHLER),
            "hinweise": sum(1 for b in bericht.befunde if b.stufe != STUFE_FEHLER),
        }

    # ------------------------------------------------------------- Kalibrieren

    def kalib_referenz(self, daten: dict) -> dict:
        """Einen Referenzpunkt neu setzen: Maus auf die Stelle, ENTER.

        `nummer` ist 1 oder 2. Der erste Punkt gibt die Verschiebung, der zweite
        zusätzlich die Skalierung — den braucht man nur, wenn sich auch die
        Auflösung geändert hat.

        Der gewählte Punkt liefert die ALTE Stelle aus `points.json`, die Maus
        die neue. Beides zusammen ist der Transform, mehr steckt nicht dahinter.
        """
        daten = daten or {}
        nummer = 2 if int(daten.get("nummer") or 1) == 2 else 1
        punkt = self._punkt_mit_id(daten.get("punkt_id"))
        if punkt is None:
            return {"ok": False, "meldung": "Punkt nicht gefunden."}
        if nummer == 2 and not self._kalib.get("ref1"):
            return {"ok": False, "meldung": "Erst den ersten Referenzpunkt setzen."}
        if nummer == 2 and self._kalib["ref1"]["punkt_id"] == punkt.id:
            return {"ok": False,
                    "meldung": "Der zweite Punkt muss ein anderer sein — "
                               "am besten weit weg vom ersten."}

        x, y, meldung = self._stelle_abwarten()
        if x is None:
            return {"ok": False, "meldung": meldung + " — nichts geändert."}

        self._kalib[f"ref{nummer}"] = {
            "punkt_id": punkt.id, "name": punkt.name or f"Punkt #{punkt.id}",
            "alt": [punkt.x, punkt.y], "neu": [x, y],
        }
        if nummer == 1:
            # Ein neuer erster Punkt macht den zweiten bedeutungslos: er wurde
            # gegen eine andere Verschiebung gemessen.
            self._kalib.pop("ref2", None)
        self._kalib_rechnen()
        return {"ok": True, "meldung": f"{punkt.name or punkt.id}: "
                                       f"({punkt.x}, {punkt.y}) → ({x}, {y})"}

    def kalib_versatz(self, daten: dict) -> dict:
        """Den gemessenen Versatz von Hand nachziehen.

        Mit der Maus trifft man den Pixel nicht genau. Weiss man, dass eine Achse
        stimmt, ist eine erzwungene 0 genauer als jede Messung — dasselbe
        Zugeständnis macht der Konsolen-Weg mit `_versatz_anpassen()`.
        """
        if not self._kalib.get("transform"):
            return {"ok": False, "meldung": "Es läuft keine Kalibrierung."}
        transform = dict(self._kalib["transform"])
        for achse in ("x", "y"):
            wert = (daten or {}).get(achse)
            if wert is None or wert == "":
                continue
            try:
                transform[f"offset_{achse}"] = float(wert)
            except (TypeError, ValueError):
                return {"ok": False, "meldung": f"'{wert}' ist keine Zahl."}
        self._kalib["transform"] = transform
        self._kalib_vorschau()
        return {"ok": True, "meldung": "Versatz übernommen."}

    def kalib_abbrechen(self, daten: Optional[dict] = None) -> dict:
        """Alles vergessen. Geschrieben wurde bis hierher nichts."""
        self._kalib = {}
        return {"ok": True, "meldung": "Kalibrierung verworfen — nichts geändert."}

    def kalib_anwenden(self, daten: Optional[dict] = None) -> dict:
        """Sichern, umrechnen, den Hauptprozess neu laden lassen.

        Vor dem Umrechnen entsteht ein vollständiges Export-ZIP
        (`sichere_vor_kalibrierung`): die Kalibrierung schreibt Punkte, Slots,
        Scans und Sequenzdateien in einem Rutsch um, und ohne Rückweg wäre ein
        danebenliegender Referenzpunkt teuer.

        `mit_slots` steht getrennt und ist standardmässig AUS: eine aus einer
        Mausposition abgeleitete Verschiebung ist für ein Klickziel gut genug,
        für eine Scan-Region aber nur eine Näherung — dafür gibt es `repair`,
        das die Slots misst. Nach einer Reparatur dürfen sie kein zweites Mal
        wandern.
        """
        from ...import_export import kalibriere_bestand, sichere_vor_kalibrierung
        transform = self._kalib.get("transform")
        if not transform:
            return {"ok": False, "meldung": "Es läuft keine Kalibrierung."}
        if self._ist_identitaet(transform):
            return {"ok": False,
                    "meldung": "Der Transform ändert nichts — nichts zu tun."}
        if self._laeuft():
            return {"ok": False,
                    "meldung": "Eine Sequenz läuft. Erst stoppen — sonst klickt "
                               "sie mitten im Umrechnen auf halb verschobene Stellen."}

        umfang = {k: bool((daten or {}).get(k, v)) for k, _, v in KALIB_UMFANG}
        state = self._bestand()
        sicherung = sichere_vor_kalibrierung(state)
        try:
            zaehlung = kalibriere_bestand(state, transform, **umfang)
        except Exception as e:                                   # noqa: BLE001
            return {"ok": False, "meldung": f"Kalibrierung fehlgeschlagen: {e}"}

        self._kalib = {}
        self._nach_kalibrierung()
        teile = ", ".join(f"{n} {name}" for name, n in sorted(zaehlung.items()) if n)
        meldung = f"Kalibriert: {teile or 'nichts geändert'}."
        if sicherung:
            meldung += f" Sicherung: {sicherung}"
        return {"ok": True, "meldung": meldung, "sicherung": sicherung or ""}

    def _nach_kalibrierung(self) -> None:
        """Beide Seiten auf den neuen Stand: der Reiter und der Hauptprozess."""
        from .model import load_palette_points
        from ...befehl import sende
        self.points = load_palette_points(self.sequences_dir)
        self._stand_punkte = self._punkte_stand()
        # Der Hauptprozess hält seinen eigenen Stand im Speicher und merkt von
        # geschriebenen Dateien nichts. Ohne das klickt er bis zum nächsten
        # Neustart auf die alten Stellen.
        sende("daten")

    def _punkte_stand(self):
        from .bridge_contract import _mtime, _punkte_pfad
        return _mtime(_punkte_pfad(self.sequences_dir))

    def _punkt_mit_id(self, punkt_id):
        try:
            gesucht = int(punkt_id)
        except (TypeError, ValueError):
            return None
        return next((p for p in self.points if p.id == gesucht), None)

    def _kalib_rechnen(self) -> None:
        """Aus den gesetzten Referenzpunkten einen Transform bauen."""
        from ...import_export import compute_transform, transform_aus_verschiebung
        ref1 = self._kalib.get("ref1")
        if not ref1:
            self._kalib.pop("transform", None)
            return
        ref2 = self._kalib.get("ref2")
        if ref2:
            self._kalib["transform"] = compute_transform(
                tuple(ref1["alt"]), tuple(ref2["alt"]),
                tuple(ref1["neu"]), tuple(ref2["neu"]))
        else:
            self._kalib["transform"] = transform_aus_verschiebung(
                tuple(ref1["alt"]), tuple(ref1["neu"]))
        self._kalib_vorschau()

    def _kalib_vorschau(self) -> None:
        """Was sich ändern WÜRDE — ohne etwas anzufassen.

        Der Grund, warum die Kalibrierung im Fenster besser ist als in der
        Konsole: dort scrollt die Liste weg, hier steht sie neben dem Knopf.
        """
        from ...import_export import kalibrier_vorschau
        transform = self._kalib.get("transform")
        if not transform:
            self._kalib["vorschau"] = []
            return
        try:
            zeilen = kalibrier_vorschau(self._bestand(), transform)
        except Exception:                                        # noqa: BLE001
            self._kalib["vorschau"] = []
            return
        self._kalib["vorschau"] = [
            {"was": str(was), "vorher": list(vorher), "nachher": list(nachher)}
            for was, vorher, nachher in zeilen[:40]
        ]

    # -------------------------------------------------------------- Klick-Runde

    def nachklick_starten(self, daten: Optional[dict] = None) -> dict:
        """Die Klick-Runde im HAUPTPROZESS starten (`klick` im Punkte-Menü).

        Das eine Werkzeug, das hier nicht laufen kann: es braucht einen
        systemweiten Maus-Hook, und der gehört dem Prozess, der auch die Hotkeys
        pumpt — sonst gingen `CTRL+ALT+K`/`U`/`H`/`J` ins Leere. Deshalb der
        Briefkasten; bedient wird danach im Spiel, nicht im Fenster.
        """
        from ...befehl import sende
        if self._laeuft():
            return {"ok": False,
                    "meldung": "Eine Sequenz läuft — die Klick-Runde braucht die "
                               "Maus für sich."}
        if self._dirty:
            return {"ok": False,
                    "meldung": "Erst speichern: die Runde klickt die Sequenz von "
                               "Platte nach, nicht die im Fenster."}
        if not sende("nachklick"):
            return {"ok": False, "meldung": "Befehl konnte nicht abgelegt werden."}
        return {"ok": True,
                "meldung": "Klick-Runde gestartet — die Anleitung steht im "
                           "Konsolenfenster, geklickt wird im Spiel."}
