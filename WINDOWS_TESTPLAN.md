# Windows-Testplan — Idle-Clans-Autoclicker

Stand: Branch `claude/magical-hawking-e0e84t`. Dieser Plan deckt die **ganze App** ab
(nicht nur die jüngsten Änderungen). 🆕 = in den letzten Sessions neu/geändert — dort
besonders genau prüfen.

## Voraussetzungen
- Windows, Python-Umgebung mit `pillow`, `opencv-python`, `numpy`, `dearpygui` (für GUI),
  optional Ollama/LM Studio (LLM) und ein OCR-Backend (easyocr/tesseract).
- Spiel „Idle Clans" offen, damit echte Klicks/Screenshots etwas treffen.

## 0. Automatisiert (schon grün auf Linux — auf Windows gegenprüfen)
- [ ] `python tools/test_logic.py` → erwartet `46 PASS / 0 FAIL`, Exit 0.
      Deckt ab: Scan-Serialisierung (Item/Boss/Icon) Round-Trip, `_point_to_dict`,
      `LOAD_EXCEPTIONS` (kaputte Dateien → None), defensives Slot-Laden,
      `compact_json`, `sanitize_filename`, `describe_color`, Koordinaten-Remapping,
      Config-Backward-Compat (entferntes Feld), `export_bundle`-ZIP-Format.
- [ ] `python tools/sync_json.py` läuft ohne Fehler über vorhandene JSON-Dateien.
- [ ] App startet: `python main.py` → Begrüßung + Hilfe erscheinen, keine Exception.

---

## 1. Hotkeys & Hilfe
- [ ] `CTRL+ALT+O` zeigt die Hilfe; alle gelisteten Hotkeys reagieren.
- [ ] Jeder Editor-Hotkey öffnet den richtigen Editor (siehe `print_help`).

## 2. Punkte (CTRL+ALT+A / +P / +U / +C)
- [ ] `CTRL+ALT+A` nimmt Mausposition als Punkt auf; Farbe wird als
      `█ Farbname (r,g,b)` angezeigt 🆕 (nicht als nackte RGB-Zahl).
- [ ] `CTRL+ALT+P` (Punkte-Editor):
  - [ ] `show <Nr>` 🆕 bewegt die Maus zum Punkt, zeigt Details (Position, Farbe, Herkunft), keine Umbenennen-Abfrage.
  - [ ] `<Nr>` testet (Maus hin) + fragt nach neuem Namen.
  - [ ] `<Nr> <Name>` benennt um; `del <Nr>` löscht; `list` zeigt Liste neu.
  - [ ] `done`/`d`/`ESC`/`q` 🆕 schließt mit Meldung „Editor geschlossen — Hotkeys wieder aktiv".
  - [ ] 🆕 Während laufender Aufnahme/laufendem Klicker lässt sich der Punkte-Editor **nicht** öffnen (Warnung).
- [ ] Punkt-Herkunft 🆕: Punkte aus einer Aufnahme zeigen `[Aufnahme '<Name>']` in der Liste.

## 3. Sequenz-Aufnahme (CTRL+ALT+J / +H)
- [ ] `CTRL+ALT+J` startet Aufnahme, jeder Linksklick wird mit `█`-Farbe geloggt 🆕.
- [ ] `CTRL+ALT+H` pausiert/setzt fort; erneut `J` stoppt.
- [ ] Nach Stopp: Name/Zyklen/Beschreibung-Abfrage, Sequenz wird geladen,
      neue Punkte landen global mit Herkunfts-Kommentar 🆕.

## 4. Sequenz-Editor (CTRL+ALT+E) + Loop-Phasen
- [ ] Neue Sequenz anlegen; INIT/LOOP/END-Phasen durchlaufen.
- [ ] Befehle: `<Nr> <Zeit>`, `wait`, `key`, `scan`, `boss`, `watcher`, `icon`,
      `del`, `edit`, `move`, `copy`, `color/colorgone`, `else …` — je 1× testen.
- [ ] `?` / `??` zeigen Kurz-/Vollhilfe.
- [ ] 🆕 **ESC im Schritt-Editor einer Loop-Phase** verwirft **nur diese Phase**,
      nicht die ganze Sequenz (zurück ins Loops-Menü, andere Phasen bleiben).
- [ ] Speichern → Datei in `sequences/` erscheint, lädt nach Neustart korrekt.

## 5. Item-Editor (CTRL+ALT+I → Items)
- [ ] `add`, `edit <Nr>`, `del <Nr>`, `rename <Nr>` (Template wird mit umbenannt).
- [ ] `learn <Nr>`, `learn <von>-<bis>`, `autoscan`, `autoscan nocolor`.
- [ ] 🆕 `autoname`: benennt `Auto …`-Items per LLM aus ihren Templates
      (nur bei `llm_enabled`); zeigt `+ 'Auto Slot 3' → 'Schwert'`, Fallback „bleibt".
- [ ] `save`/`load`/`preset del` Presets.
- [ ] Transaktional: `cancel`/`ESC` verwirft Änderungen seit Editor-Start.

## 6. Slot-Editor (CTRL+ALT+I → Slots) 🆕 transaktional
- [ ] `auto` (Slot-Auto-Erkennung), `add`, `edit <Nr>`, `del <Nr>`, `del all`.
- [ ] 🆕 **Transaktional**: Änderungen (auch `auto`/Preset-`load`) werden erst bei
      `done` gespeichert; `cancel`/`ESC` stellt den Startzustand wieder her
      (Datei `slots/slots.json` zurückgesetzt).
- [ ] 🆕 Duplikat-Check: neuer Slot mit existierendem Namen fragt „Überschreiben?".

## 7. Item-Scan-Editor (CTRL+ALT+I)
- [ ] Neuen Scan: Slots wählen, Items wählen, Toleranz, **Schritt 4 Auto-Lernen** 🆕.
- [ ] 🆕 `learn_unknown`: im laufenden Scan werden unbekannte Slots als `Auto <Slot>`
      gelernt (Kategorie 'Auto', **kein** LLM live).
- [ ] 🆕 **Auto-Scan-Setup-Ende**: nach `autoscan` fragt es bei `llm_enabled`
      „Items jetzt per LLM benennen?" (Default ja) — benennt die neuen Items.
- [ ] 🆕 `done` mit 0 Slots zeigt Fehler + bleibt im Menü (kein Komplett-Abbruch).
- [ ] Defektes Scan-JSON 🆕: erscheint als `[WARNUNG] … fehlt im Menü!` statt still zu verschwinden.

## 8. Boss-Scan-Editor (CTRL+ALT+B)
- [ ] Region: 🆕 manuelle Koordinaten-Eingabe wiederholt bei Tippfehler (z. B. `4691.`),
      bricht **nicht** den Editor ab; `cancel` = zurück ins Region-Menü.
- [ ] Boss anlegen: Template **oder** Marker; Aktion (scan/click/key/skip/…).
- [ ] 🆕 Tasten-Eingabe bei „key"-Aktion wiederholt bei ungültiger Taste.
- [ ] 🆕 **Boss-Bibliothek verwalten** (Menüpunkt): globale Bosse anlegen → gelten
      in jedem Boss-Scan; ein Scan darf 0 lokale Bosse haben.
- [ ] 🆕 Menüpunkt „Auto-Lernen neuer Bosse → Bibliothek/Scan [umschalten]" toggelt
      `boss_learn_global` (in `config.json` gespeichert).
- [ ] 🆕 Beim Bearbeiten: Aktion/Default-Aktion/LLM-/OCR-Modus/„Region beibehalten"
      sind **vorausgewählt** (Enter überschreibt nichts).
- [ ] Menü kehrt nach jeder Aktion zurück (Loop), `ESC` beendet.

## 9. Icon-Scan-Editor (CTRL+ALT+N)
- [ ] Region (wie Boss) + Erkennung (Template/Marker) + Aktion.
- [ ] 🆕 Beim Bearbeiten ist „Bestehende Erkennung beibehalten" vorausgewählt.
- [ ] 🆕 Tasten-Eingabe wiederholt bei Fehleingabe.

## 10. Ausführung / Runtime (CTRL+ALT+S / +G / +K / +W / +F)
- [ ] Start/Stop (`S`), Pause/Weiter (`G`), Skip (`K`), Skip-Cycle (`W`), Finish (`F`).
- [ ] Echte Klicks landen an den Punktkoordinaten; Wartezeiten stimmen.
- [ ] Farb-Trigger (`pixel`/`color`/`colorgone`) lösen korrekt aus / Timeout-Verhalten.
- [ ] Item-Scan-Step klickt das beste Item je Kategorie (all/best/every).
- [ ] 🆕 Item-Auto-Lernen während des Scans bremst den Lauf **nicht** spürbar
      (keine LLM-Pause), neue Items heißen `Auto <Slot>`.
- [ ] Boss-Scan-Step / Boss-Watcher: Erkennung → hinterlegte Aktion;
      🆕 globale Bibliotheks-Bosse gelten zusätzlich; unbekannte Bosse landen je
      nach `boss_learn_global` in Scan oder Bibliothek.
- [ ] Icon-Scan-Step löst Aktion bei sichtbarem Icon aus.
- [ ] Failsafe (Maus in Ecke) stoppt; Window-Fokus-Check pausiert/stoppt bei
      falschem Fenster; Humanize-Mikro-Delays/Breaks aktiv.
- [ ] Session-Log (falls aktiviert): CSV unter `logs/` wird geschrieben.

## 11. LLM & OCR (optional, Backend nötig)
- [ ] `python tools/test_llm.py` und `… screenshot` — Verbindung + Antwort.
- [ ] Boss-Erkennung per LLM (primär & Fallback), per OCR (primär & Fallback) —
      kein Doppel-Aufruf, plausible Treffer.
- [ ] 🆕 `autoname` / Setup-Ende-Benennung: LLM liefert kurze Item-Namen,
      Timeout/„kein Name" → sauberer Fallback, App hängt nicht.

## 12. Import/Export (CTRL+ALT+ … Import/Export-Editor)
- [ ] Export erzeugt ZIP unter `exports/` mit `manifest.json` + Daten + Templates.
- [ ] 🆕 Globale Boss-Bibliothek (`global_bosses.json`) ist im Bundle.
- [ ] Import auf **anderem Bildschirm/Auflösung**: Koordinaten-Remapping
      (automatisch aus Fenstergröße, sonst 2-Punkt) verschiebt Klicks korrekt.
- [ ] Merge vs. Ersetzen verhält sich wie erwartet.

## 13. Scan-Studio GUI (CTRL+ALT+ … ) 🆕 geführter Slot-Ablauf
- [ ] Startet als eigenes Fenster (Screenshot sichtbar).
- [ ] 🆕 **Geführter Slot-Ablauf**: Rechteck ziehen → Werkzeug springt automatisch
      auf „Klickpunkt setzen" (Radio wechselt sichtbar) → Klick → springt auf
      „Farbe picken" → Klick → zurück auf „Slot zeichnen". Status führt durch jeden Schritt.
- [ ] 🆕 Unterbrechen: manueller Werkzeug-Wechsel (Radio) bricht den geführten
      Ablauf ab; „Slot zeichnen" überspringt Klickpunkt/Farbe und lässt das
      nächste Rechteck ziehen.
- [ ] Tabs „Scan bauen / Icon-Scan / Boss-Scan", „Autoscan"-Knopf, „Speichern".
- [ ] Gespeicherte Slots erscheinen identisch im Konsolen-Slot-Editor (gleiche Datei).

## 14. Node-/Sequenz-Editor GUI (CTRL+ALT+V)
- [ ] Startet; Blöcke/Lanes anlegen, Punkte-Palette, Sequenz speichern.
- [ ] Gespeicherte Sequenz lädt im Konsolen-Editor und läuft im Worker.

## 15. Robustheit / Backward-Compat
- [ ] Alte `config.json` (mit `scan_learn_llm_names`) lädt ohne Fehler 🆕
      (Feld wird ignoriert).
- [ ] Manuell beschädigte Scan-/Slot-/Sequenz-Datei → App startet, meldet Warnung,
      überspringt nur die kaputte Datei.
- [ ] DPI-Skalierung ≠ 100 %: Klick-/Screenshot-Koordinaten stimmen.

---

### Bekannte Nicht-Abdeckung (bewusst offen)
- Scan-Studio-GUI-Autoscan nutzt (noch) **keine** LLM-Benennung am Ende — dort
  heißen Items generisch „Item N". (Konsolen-Autoscan tut es 🆕.)
- GUI/DPG, echte Maus/Tastatur, LLM/OCR-Backends lassen sich nur auf Windows
  mit Hardware/Backends real prüfen — daher dieser manuelle Plan.
