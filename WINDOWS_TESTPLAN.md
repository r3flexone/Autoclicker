# Windows-Testplan — Idle-Clans-Autoclicker

Stand: 2026-08-02, Branch `claude/idle-clans-gold-farming-e16x20`. Dieser Plan deckt die
**ganze App** ab (nicht nur die jüngsten Änderungen). 🆕 = in den letzten Sessions
neu/geändert — dort besonders genau prüfen.

Was hier abgehakt ist, wurde auf echtem Windows geprüft — mit Datum dahinter. Ein Haken
ohne Datum ist ein Vorsatz, kein Nachweis.

## Voraussetzungen
- Windows, Python-Umgebung mit `pillow`, `opencv-python`, `numpy`, `dearpygui`
  (Scan-Studio), `pywebview` (Sequenz-Studio),
  optional Ollama/LM Studio (LLM) und ein OCR-Backend (easyocr/tesseract).
- Spiel „Idle Clans" offen, damit echte Klicks/Screenshots etwas treffen.

## 0. Automatisiert (schon grün auf Linux — auf Windows gegenprüfen)
- [x] `python tools/test_logic.py` → erwartet `475 PASS / 0 FAIL`, Exit 0.
      **2026-08-02 Windows: 475 PASS / 0 FAIL, Exit 0 ✓**
      Unter Windows mit `PYTHONIOENCODING=utf-8` starten — auf einer cp1252-Konsole
      bricht die Ausgabe sonst mit `UnicodeEncodeError` ab (Box-Zeichen).
      Bis 2026-08-02 waren hier 4 Checks dauerhaft rot: die Geometrie-Helfer
      (`get_virtual_desktop` & Co.) wurden nur gegen ihr gestubbtes Linux-Verhalten
      geprüft. Jetzt prüft der Test beide Plattformen.
      **2026-06-16 Windows: 83 PASS / 0 FAIL, Exit 0 ✓** (damaliger Stand)
      Deckt ab: Scan-Serialisierung (Item/Boss/Icon) Round-Trip, `_point_to_dict`,
      `LOAD_EXCEPTIONS` (kaputte Dateien → None), defensives Slot-Laden,
      `compact_json`, `sanitize_filename`, `describe_color`, Koordinaten-Remapping,
      Config-Backward-Compat (entferntes Feld), `export_bundle`-ZIP-Format,
      LLM-Vision-Logik (is_no_boss/clean_boss_name/match_boss_name/Reasoning-Strip/
      Antwort-Extraktion/Request-Builder — ohne Backend).
- [ ] Erster Start hebt vorhandene JSON-Dateien (`[MIGRATION]`-Meldung), zweiter Start ist still.
- [ ] `python tools/migrate.py` meldet danach „0 angepasst".
      **2026-06-16 Windows: durchgelaufen, alle Migrationen ohne Fehler ✓**
- [x] App startet: `python main.py` → Begrüssung + Hilfe erscheinen, keine Exception.
      **2026-06-16 Windows: Begrüssung + Hilfe ok, alle Loader + LLM verbunden, keine Exception ✓**

## 0b. Plattform-Schicht ohne laufendes Spiel (2026-08-02 Windows ✓)
Das lässt sich prüfen, ohne Idle Clans zu öffnen — reine API-Pfade gegen echtes Windows.
Alle Punkte unten sind an diesem Datum grün gewesen.

- [x] Voller Import aller Module (`winapi`, `imaging`, `handlers`, `runtime.worker`)
      — das ist der Teil, der in der Linux-Sandbox an `msvcrt`/`ctypes.windll` scheitert.
- [x] `take_screenshot` / `take_screenshot_bitblt`: Region, Vollbild, **und Monitore mit
      negativen Koordinaten** (links vom bzw. über dem primären), Regionen quer über
      Monitorgrenzen, ImageGrab-Fallback. BitBlt-Pixel deckt sich mit `get_pixel_color`.
- [x] `get_pixel_color` / `get_screen_pixel` / `color_distance` / `get_color_name`.
- [x] `match_template_in_image`: Selbst-Match eines synthetischen Templates → 100 %.
- [x] `get_foreground_window_title`, `is_target_window_active`,
      `get_client_rect_by_title` (unbekannter Titel → sauber `False`/`None`).
- [x] DPI-Awareness steht nach dem Import auf 2 (Per-Monitor).
- [x] `register_hotkeys()` / `unregister_hotkeys()` als Zyklus.
- [x] `send_click` / `send_key` / `set_cursor_pos` gegen ein neutrales Ziel (Notepad):
      Text kam nachweislich im Zielfenster an.
- [x] OCR end-to-end mit gerendertem Text: `read_text` erkennt, `detect_boss_name`
      matcht bekannte Bosse, lehnt Nicht-Bosse ab und schlägt neue Namen vor.
      ⚠ Der **erste** Aufruf lädt EasyOCR-Modelle aus dem Netz (Minuten, kann mit
      HTTP-Fehler scheitern) — danach ~300 ms.
- [x] `diagnose.pruefe_setup()` gegen echten Datenbestand → 0 Befunde.
- [x] `export_bundle` → ZIP mit `manifest.json` + Templates; `import_bundle` stellt
      denselben Stand wieder her. ⚠ Import **nur in einer CWD-Sandbox** testen, er
      schreibt sonst echte Daten inkl. `config.json` (s. CLAUDE.md).

Offen bleibt alles, was das laufende Spiel braucht — die Abschnitte unten.

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
  - [ ] `done`/`d`/`ESC`/`q` 🆕 schliesst mit Meldung „Editor geschlossen — Hotkeys wieder aktiv".
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

> Hinweis: Slot-/Item-/Item-Scan-/Boss-/Icon-Editor werden **alle** über das
> Hub-Menü `CTRL+ALT+N` (Item-Scan-Editor) erreicht und dort ausgewählt.

## 5. Item-Editor (CTRL+ALT+N → Items)
- [ ] `add`, `edit <Nr>`, `del <Nr>`, `rename <Nr>` (Template wird mit umbenannt).
- [ ] `learn <Nr>`, `learn <von>-<bis>`, `autoscan`, `autoscan nocolor`.
- [ ] 🆕 `autoname`: benennt `Auto …`-Items per LLM aus ihren Templates
      (nur bei `llm_enabled`); zeigt `+ 'Auto Slot 3' → 'Schwert'`, Fallback „bleibt".
- [ ] `save`/`load`/`preset del` Presets.
- [ ] Transaktional: `cancel`/`ESC` verwirft Änderungen seit Editor-Start.

## 6. Slot-Editor (CTRL+ALT+N → Slots) 🆕 transaktional
- [ ] `auto` (Slot-Auto-Erkennung), `add`, `edit <Nr>`, `del <Nr>`, `del all`.
- [ ] 🆕 **Transaktional**: Änderungen (auch `auto`/Preset-`load`) werden erst bei
      `done` gespeichert; `cancel`/`ESC` stellt den Startzustand wieder her
      (Datei `slots/slots.json` zurückgesetzt).
- [ ] 🆕 Duplikat-Check: neuer Slot mit existierendem Namen fragt „Überschreiben?".

## 7. Item-Scan-Editor (CTRL+ALT+N → Item-Scan)
- [ ] Neuen Scan: Slots wählen, Items wählen, Toleranz, **Schritt 4 Auto-Lernen** 🆕.
- [ ] 🆕 `learn_unknown`: im laufenden Scan werden unbekannte Slots als `Auto <Slot>`
      gelernt (Kategorie 'Auto', **kein** LLM live).
- [ ] 🆕 **Auto-Scan-Setup-Ende**: nach `autoscan` fragt es bei `llm_enabled`
      „Items jetzt per LLM benennen?" (Default ja) — benennt die neuen Items.
- [ ] 🆕 `done` mit 0 Slots zeigt Fehler + bleibt im Menü (kein Komplett-Abbruch).
- [ ] Defektes Scan-JSON 🆕: erscheint als `[WARNUNG] … fehlt im Menü!` statt still zu verschwinden.

## 8. Boss-Scan-Editor (CTRL+ALT+N → Boss-Scan)
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

## 9. Icon-Scan-Editor (CTRL+ALT+N → Icon-Scan)
- [ ] Region (wie Boss) + Erkennung (Template/Marker) + Aktion.
- [ ] 🆕 Beim Bearbeiten ist „Bestehende Erkennung beibehalten" vorausgewählt.
- [ ] 🆕 Tasten-Eingabe wiederholt bei Fehleingabe.

## 10. Ausführung / Runtime (CTRL+ALT+S / +G / +K / +F / +W / +Z)
- [ ] Start/Stop (`S`), Pause/Weiter (`G`), Skip Wartezeit (`K`), Sanft beenden (`F`),
      Quick-Switch Sequenz (`W`), Zeitplan-Start (`Z`).
- [ ] Echte Klicks landen an den Punktkoordinaten; Wartezeiten stimmen.
- [ ] Farb-Trigger (`pixel`/`color`/`colorgone`) lösen korrekt aus / Timeout-Verhalten.
- [ ] Item-Scan-Step klickt das beste Item je Kategorie (all/best/every).
- [ ] 🆕 Item-Auto-Lernen während des Scans bremst den Lauf **nicht** spürbar
      (keine LLM-Pause), neue Items heissen `Auto <Slot>`.
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

## 12. Import/Export (CTRL+ALT+I)
- [ ] Export erzeugt ZIP unter `exports/` mit `manifest.json` + Daten + Templates.
- [ ] 🆕 Globale Boss-Bibliothek (`global_bosses.json`) ist im Bundle.
- [ ] Import auf **anderem Bildschirm/Auflösung**: Koordinaten-Remapping
      (automatisch aus Fenstergrösse, sonst 2-Punkt) verschiebt Klicks korrekt.
- [ ] Merge vs. Ersetzen verhält sich wie erwartet.

## 13. Scan-Studio GUI (CTRL+ALT+V) 🆕 geführter Slot-Ablauf
- [ ] Startet als eigenes Fenster (Screenshot sichtbar).
- [ ] 🆕 **Geführter Slot-Ablauf**: Rechteck ziehen → Werkzeug springt automatisch
      auf „Klickpunkt setzen" (Radio wechselt sichtbar) → Klick → springt auf
      „Farbe picken" → Klick → zurück auf „Slot zeichnen". Status führt durch jeden Schritt.
- [ ] 🆕 Unterbrechen: manueller Werkzeug-Wechsel (Radio) bricht den geführten
      Ablauf ab; „Slot zeichnen" überspringt Klickpunkt/Farbe und lässt das
      nächste Rechteck ziehen.
- [ ] Tabs „Scan bauen / Icon-Scan / Boss-Scan", „Autoscan"-Knopf, „Speichern".
- [ ] Gespeicherte Slots erscheinen identisch im Konsolen-Slot-Editor (gleiche Datei).

## 14. Sequenz-Studio (CTRL+ALT+B) 🆕 Weboberfläche statt Dear PyGui
- [ ] Fenster öffnet sich (braucht `pywebview`; auf Windows WebView2). Ohne das Paket
      erscheint stattdessen der Hinweis mit dem `pip install`-Befehl, kein Traceback.
- [ ] Schriften und Farben stehen, nichts lädt nach — das Fenster darf auch ohne
      Internet vollständig aussehen.
- [ ] Karten lassen sich anklicken (STRG = dazu, SHIFT = Bereich), ziehen sortiert um,
      die Einfüge-Marke zeigt vorher, wo der Block landet.
- [ ] Ziehen über eine Phasengrenze funktioniert; ein Punkt aus der Palette wird per
      Ziehen zum Klick-Block mit `#Nr` auf der Karte.
- [ ] Tastatur: `Entf` löscht die Auswahl, `ALT+↑/↓` verschiebt sie, `STRG+S` speichert
      (auch direkt nach einer Eingabe — der zuletzt getippte Wert muss mitgehen).
- [ ] Eigenschaften: Typwechsel, Wartezeit, Punkt, Farb-Trigger, Nachprüfung, ELSE,
      Scan-Name/-Modus, Screenshot-Bereich. Änderungen erscheinen sofort auf der Karte.
- [ ] X/Y im Feld „Stelle" verschieben den **Punkt**: alle Blöcke darauf ziehen mit.
- [ ] 🆕 **Duplizieren** (Knopf oder `STRG+D`): die Kopie steht direkt hinter dem
      Original, trägt dessen Einstellungen (Wartezeit, Trigger, Nachprüfung, ELSE)
      und ist danach ausgewählt. Gegenprobe: an der Kopie etwas ändern → das
      Original bleibt, wie es war. Mehrfachauswahl duplizieren → die Kopien liegen
      als Block hinter der Auswahl.
- [ ] 🆕 ELSE an einem reinen Klick-Block: der Abschnitt fehlt ganz. Gegenprobe:
      an einem Block mit Farb-Trigger ELSE setzen, dann den Typ auf KLICK stellen →
      ELSE wird automatisch entfernt, die Statuszeile sagt es, die Karte zeigt kein
      „sonst:" mehr. Zurück auf FARBE+KLICK → Abschnitt wieder da, nichts markiert.
- [ ] 🆕 ELSE: ohne Aktion nennt der Hinweis den echten Timeout und die echte
      Folge aus der `config.json` (Voreinstellung: 300 s → Zyklus abbrechen).
      Gegenprobe: `pixel_timeout_action` auf `stop` stellen, Studio neu öffnen →
      der Hinweis sagt „Sequenz stoppen".
- [ ] 🆕 ELSE: ohne gesetzte Aktion ist **keine** Kachel markiert und es gibt
      keine Kachel „(keine)". Eine Aktion setzen, dann **dieselbe Kachel nochmal**
      klicken → ELSE ist wieder weg. Eine andere Kachel wechselt normal.
- [ ] 🆕 **Stelle mit der Maus setzen**: Knopf im Inspektor, Maus ins Spiel an die
      Stelle, ENTER → X/Y und Farbe des Punkts stimmen. ESC ändert nichts.
- [ ] 🆕 **Fremde Änderung**: Studio offen lassen, im Hauptprozess dieselbe Sequenz
      speichern (oder eine Aufnahme machen → points.json), dann im Studio speichern
      → Rückfrage „Ausserhalb geändert". „Trotzdem speichern" überschreibt,
      Abbrechen lässt die Datei in Ruhe.
- [ ] 🆕 **Live-Ausschnitt**: bei einem Farb-Trigger zeigt der Live-Run ein Bild der
      geprüften Stelle mit Fadenkreuz, das sich etwa im Sekundentakt erneuert.
- [ ] 🆕 „Stelle zeigen" gibt es getrennt für Klick, Prüf-Pixel und ELSE-Klick —
      jeder Knopf fährt die richtige Position an.
- [ ] Laden/Neu mit ungespeicherten Änderungen fragt nach (Speichern / Verwerfen /
      Abbrechen).
- [ ] Fenster mit ungespeicherten Änderungen schliessen → Konsole meldet eine
      Rettungskopie unter `backups/<name>.ungespeichert.json`, und die Datei ist da.
- [ ] Gespeicherte Sequenz lädt im Konsolen-Editor und läuft im Worker.
- [ ] 🆕 Das Fenster trägt in Titelleiste und Taskleiste das Studio-Symbol
      (amber Kachel mit Zeiger), nicht das Python-Symbol. Schlägt das fehl, ist es
      kosmetisch — das Fenster muss trotzdem aufgehen.
- [ ] **Starten aus dem Studio** (🆕): Knopf im Kopf → Hauptprozess meldet
      „[STUDIO] '<Name>' geladen und gestartet", die Sequenz läuft, und die Ansicht
      springt von selbst in den Live-Run.
- [ ] Vor dem Start eine Änderung machen und NICHT speichern → sie ist trotzdem im
      Lauf (das Studio speichert vorher).
- [ ] Pause und Stoppen aus der Live-Ansicht wirken; CTRL+ALT+S/G tun weiterhin
      dasselbe.
- [ ] Während eines Laufs in den Editor wechseln → die Ansicht bleibt dort stehen.
- [ ] 🆕 Der Live-Run zeigt **alle** Phasen: die laufende breit, davorliegende als
      „abgeschlossen", spätere als „ausstehend" bzw. „wartet auf <Uhrzeit>" bei
      einer zeitgesteuerten Phase. Beim Phasenwechsel wandert die Markierung mit.
- [ ] 🆕 Sequenz mit vielen Loop-Phasen (≥ 6) laufen lassen → die Phasen-Leiste
      bricht in mehrere Zeilen um, keine Kachel wird unlesbar schmal. Fenster
      schmal ziehen → auch die Kopfleiste bricht um, nichts läuft seitlich raus.
- [ ] 🆕 Der laufende Block im Live-Run trägt seine Typfarbe und Marke (grün
      FARBE+KLICK, rot BOSS-SCAN, …) — dieselbe wie seine Karte im Editor.
- [ ] 🆕 Ein Block mit **Wartezeit** läuft: im Live-Run steht „noch X s von Y s",
      der Balken füllt sich, und nach Ablauf verschwindet der Kasten sofort —
      nicht erst beim nächsten Block.
- [ ] 🆕 Ein Block mit **Farb-Trigger** wartet: der Kasten nennt die Stelle, stellt
      Soll gegen Ist, zeigt „Δ N · im Toleranzbereich/ausserhalb" und zählt den
      Timeout herunter; darunter steht, was danach passiert (ELSE bzw. die globale
      Timeout-Aktion). Gegenprobe: `pixel_wait_timeout: 0` → „ohne Timeout", kein
      Countdown.
- [ ] 🆕 „Stelle zeigen" unter einem Klick-Block: die Maus springt auf den Punkt,
      und in der Konsole steht die gespeicherte neben der aktuellen Farbe (mit
      „passt" bzw. „weicht ab"). Während eines Laufs passiert nichts — dort gehört
      die Maus dem Worker.
- [ ] Im Studio „Starten" drücken, während der Hauptprozess **nicht** läuft; danach
      den Hauptprozess starten → es darf **nichts** losklicken. Im Studio erscheint
      nach ~2 s „Kein Hauptprozess erreichbar".
- [ ] CTRL+ALT+B **während** ein Lauf läuft → das Fenster geht auf (die Sperre ist
      absichtlich weg) und zeigt den Live-Run.

## 15. Robustheit / Backward-Compat
- [ ] Alte `config.json` (mit `scan_learn_llm_names`) lädt ohne Fehler 🆕
      (Feld wird ignoriert).
- [ ] Manuell beschädigte Scan-/Slot-/Sequenz-Datei → App startet, meldet Warnung,
      überspringt nur die kaputte Datei.
- [ ] DPI-Skalierung ≠ 100 %: Klick-/Screenshot-Koordinaten stimmen.
      Teilweise erledigt: **Multi-Monitor mit negativen Koordinaten** ist geprüft
      (2026-08-02, s. 0b). Offen bleibt der eigentliche Fall — **unterschiedliche DPIs
      pro Monitor**; dafür muss die Skalierung eines Monitors abweichend gesetzt werden.

---

### Bekannte Nicht-Abdeckung (bewusst offen)
- Scan-Studio-GUI-Autoscan nutzt (noch) **keine** LLM-Benennung am Ende — dort
  heissen Items generisch „Item N". (Konsolen-Autoscan tut es 🆕.)
- GUI (Dear PyGui / WebView2), echte Maus/Tastatur, LLM/OCR-Backends lassen sich nur
  auf Windows mit Hardware/Backends real prüfen — daher dieser manuelle Plan. Die
  Weboberfläche des Sequenz-Studios ist immerhin in Chromium durchgeklickt worden;
  ungeprüft bleibt das Fenster selbst (WebView2, Schliessen-Ereignis, DPI).
