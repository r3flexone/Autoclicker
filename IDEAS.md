# Feature-Ideen (Backlog)

Sammlung von Features, die diskutiert aber **nicht umgesetzt** wurden. Kurzbeschreibung +
Tradeoff, damit eine spätere Entscheidung ohne erneute Analyse möglich ist.

Ist ein Eintrag gebaut, fliegt er hier raus — ein Backlog, das Erledigtes mitführt, verliert
seinen Zweck. Zuletzt entfallen, weil umgesetzt: *Profile-Export/Import* (`import_export.py`,
inklusive Config und Koordinaten-Remapping), *Multi-Monitor / DPI-Awareness*
(`SetProcessDpiAwareness(2)` in `winapi.py`, virtueller Desktop in `imaging.py`),
*Dry-Run / Simulation* (manueller Modus + Debug-Stufe 2), *Sequenzen-Übersicht*
und *Live-Run* im Sequenz-Studio (zwei eigene Ansichten; der Live-Run liest
`.lauf.json` und steuert über `befehl.py` zurück), *Einstellungs-Menü* (vierter
Reiter im Sequenz-Studio, aus `_CONFIG_SECTIONS` + `config_meta.py` generiert),
*Bericht-Reiter* samt *Ertrag eines Laufs* (achter Reiter; `bridge_bericht.py`
über `auswerten()` aus `tools/log_report.py`, Stückzahlen mal
`scan_market_value_file`).

**Was Oberfläche anfasst, wird symmetrisch gebaut.** Für die Einträge unten ist das keine
Geschmacksfrage, sondern eine Abnahmebedingung: gleiche Spalten statt Textbreite
(`knopfpaar` bzw. `btn breit` — kein drittes Muster daneben), untereinander stehende Zeilen
auf **derselben** `auto-fit`-Regel (min. 118 px, damit nichts abgeschnitten wird), Zustand
ringsum markiert statt an einer Kante, und die Vorschau-Quadrate mit fester Kantenlänge.
Ein neuer Reiter reiht sich in die vorhandene `.tabs`-Leiste ein, statt sich eine zweite
danebenzustellen.

## Bedienung

### Sequenz-Studio: Screenshot-Vorschau in der Punkte-Palette
Die Punkte als Marker auf einem Bildschirmfoto, statt nur als Koordinatenpaare.

- **Nutzen:** „Punkt #3" sagt einem nichts; auf dem Bild sieht man sofort, welcher Knopf
  gemeint ist. Für das Sortieren einer aufgenommenen Sequenz ist das der Unterschied.
- **Tradeoff:** Der Subprozess müsste einen Screenshot aufnehmen (`imaging.take_screenshot`,
  braucht Pillow/Windows) und als Data-URL in die Seite reichen — und das Bild ist der
  Bildschirm von *jetzt*, nicht der vom Zeitpunkt der Aufnahme. Wenn das Spiel gerade
  nicht läuft, zeigt die Vorschau den Desktop.

### Bausteine: eine Sequenz aus einer Sequenz aufrufen
Der Weg zur Bank steht in jeder Sequenz, die ihn braucht — als Kopie.

- **Nutzen:** Ein Schritt-Typ „Sequenz X ausführen". Ändert sich der Weg, ändert man ihn
  einmal. Dasselbe Argument wie „Referenzen statt Kopien", nur eine Ebene höher.
- **Tradeoff:** Punkte sind sequenzlokal, der Baustein bringt seine eigenen mit — das passt.
  Was nicht passt: Live-Run, Phasenleiste und `.lauf.json` beschreiben **eine** Sequenz mit
  Phasen; ein Aufruf macht daraus einen Stapel, und „Phase 2 von 4" stimmt dann nicht mehr.
  Dazu die Rekursion (A ruft B ruft A) und die Frage, was `restart` in einem Baustein
  bedeutet. Deutlich billiger und fast so gut: eine reine Editor-Funktion „Schritte aus
  Sequenz X hier einfügen" — eine Kopie, aber eine bewusste und einmalige.

## Performance

### Ein Screenshot pro Scan statt einer pro Slot
`execute_item_scan()` macht für jeden Slot eine eigene Bildschirmaufnahme (BitBlt +
GetDIBits). Bei 5 Slots sind das 5 Aufnahmen, wo eine über das umschliessende Rechteck
plus Zuschneiden reichen würde.

- **Nutzen:** Weniger GDI-Aufrufe pro Scan-Schritt. Nebeneffekt: alle Slots stammen aus
  demselben Frame, der Vergleich zwischen ihnen wird also konsistenter.
- **Tradeoff:** Genau dieser Nebeneffekt ist die Frage. Heute liegt zwischen den Slots
  `scan_slot_delay` (Default 0.1 s) und jeder Slot sieht einen etwas späteren Spielstand —
  bei einem statischen Inventar egal, bei animierten Inhalten nicht. Zweitens hilft die
  Bündelung nur, wenn die Slots nah beieinander liegen: sind sie über den Bildschirm
  verteilt, nimmt das umschliessende Rechteck fast das ganze Bild auf und die Aufnahme wird
  teurer statt billiger. Es bräuchte also eine Schranke (Rechteckfläche vs. Summe der
  Slot-Flächen), und damit eine Heuristik, die man auf einem echten Windows-Setup messen
  muss — auf Linux ist das nicht prüfbar.
- **Ansatz:** In `execute_item_scan()` einmal das umschliessende Rechteck aller Slots
  aufnehmen und pro Slot `img.crop()` statt `take_screenshot(slot.scan_region)`. Die
  Slot-Schleife mit ihren Stop-/Pause-/Skip-Prüfungen bleibt unverändert. Vorher auf
  Windows messen, ob sich der Aufwand überhaupt lohnt.

## Reliability

### Disconnect-Detection
Pixel-Trigger oder Template-Match auf Login-Screen / Verbindungsfehler-Popup, dann Auto-Reconnect oder sauberer Stop.

Ein Teil davon ist inzwischen gebaut: die **Nachprüfung** (`verify <Nr> <Punkt-Nr>` im
Sequenz-Editor) merkt, dass ein Klick nicht gewirkt hat, wiederholt ihn und meldet es
im Log. Ein Disconnect fällt damit als Häufung von `verify_miss` auf
(`tools/log_report.py`), statt stundenlang unbemerkt zu bleiben. Offen bleibt das
gezielte Erkennen *des Login-Screens* und die Reaktion darauf.

- **Nutzen:** Verhindert dass der Bot stundenlang ins Leere klickt, wenn das Spiel abstürzt oder die Verbindung weg ist.
- **Tradeoff:** Benötigt eine kalibrierte Pixel-Position/Template pro Benutzer. Auto-Reconnect ist riskant (Passwort-Eingabe o.ä.) – sicherer: nur Stop + Notify.
- **Ansatz:** Ein Background-Watcher (ähnlich Boss-Watcher). Die Schwelle könnte aus
  dem Log kommen: N `verify_miss` oder `timeout` in Folge = vermutlich Disconnect.

### Fenster-Anker: den Versatz beim Start selbst ausgleichen
Ein Klick-Punkt steht in Bildschirm-Koordinaten. Zieht das Spielfenster um, stimmt keiner
mehr — und dafür gibt es heute drei Werkzeuge (`repair`, `fix`, Klick-Runde), die alle erst
**hinterher** reparieren.

- **Nutzen:** Die Sequenz merkt sich beim Speichern den Client-Bereich ihres Spielfensters
  (`get_client_rect_by_title`, wie das Export-Manifest es schon tut). Beim Start wird der
  aktuelle geholt und die Differenz einmal auf alle aufgelösten Punkte gerechnet — im
  Speicher, nicht in der Datei. Ein verschobenes Fenster kostet dann gar nichts mehr, und
  eine zweite Instanz desselben Spiels läuft mit derselben Sequenz.
- **Tradeoff:** Trägt nur, solange sich das Fenster **verschiebt**. Ändert es die Grösse,
  müsste skaliert werden, und eine skalierte Klickstelle ist eine geratene — genau deshalb
  rechnet der Import nur mit zwei bestätigten Referenzpunkten. Zweitens müssten Scan-Regionen
  und Slots mitwandern, sonst klickt es richtig und erkennt falsch. Und ein Anker, dessen
  Fenster gerade nicht da ist, darf den Lauf nicht blockieren: dann gilt der gespeicherte
  Stand, einmal gemeldet.
- **Ansatz:** Feld `fenster_anker` an `Sequence` (Titel + Client-Rechteck), gefüllt beim
  Speichern im Studio, aufgelöst in `resolve_point_references()`. Eine Grössenänderung wird
  gemeldet und **nicht** gerechnet. Reine Vorschaltung — die bestehenden Reparaturwege
  bleiben, wie sie sind.

## Safety

### Session-Zeitlimit
Harte Obergrenze (z.B. max. 6h pro Tag), danach automatischer Stop.

Der **Break-Scheduler dieses Eintrags ist gebaut**: `humanize_break_interval_min` +
`humanize_break_duration_min/max` legen periodische Pausen ein (`_humanize_check_break`
in `runtime/actions.py`). Offen ist nur die harte Obergrenze.

- **Nutzen:** Schutz vor Bans durch 24/7-Laufzeit.
- **Tradeoff:** Reduziert Throughput, muss konfigurierbar sein. Ein Stop mitten im Zyklus kann Items liegen lassen — sauberer wäre `finish_event` (Zyklus zu Ende, dann END-Phase).
- **Ansatz:** Ein Config-Wert `max_session_hours`. In `_run_main_loop` am Zyklus-Rand gegen `state.start_time` prüfen und `finish_event` setzen.

## Observability

### Discord/Telegram-Webhook-Notifications
Ping bei wichtigen Events: Boss erkannt (LLM), Inventory voll, unerwarteter Stop, Disconnect, Session-Ende.

- **Nutzen:** Kein ständiger Blick aufs Fenster nötig. Besonders stark in Kombination mit LLM-Boss-Detection.
- **Tradeoff:** Webhook-URL als Secret verwalten (nicht ins Repo). Netzwerk-Abhängigkeit.
- **Ansatz:** Neues Modul `autoclicker/notifications.py` mit `send_webhook(url, message, image=None)`. Hook-Points in `runtime/actions.py`.

## Erkennung

### Warten auf Text oder Zahl (OCR-Bedingung)
`WaitCondition` kennt heute nur Farbe. `ocr.py` kann Text, wird aber ausschliesslich für
Boss-Namen benutzt.

- **Nutzen:** „warte, bis in dieser Region *Fertig* steht" oder „bis die Menge ≥ 100 ist".
  Damit fallen Inventory-voll, Cooldowns und Fortschrittsbalken in **eine** Bedingung,
  statt für jeden Fall eine eigene Farbstelle zu suchen. Ein Farbpixel sagt nicht, wie
  viel; eine Zahl schon.
- **Tradeoff:** Der erste EasyOCR-Aufruf lädt Modelle aus dem Netz (Sekunden bis Minuten)
  und hielte den Worker mitten im Lauf an — dieselbe Falle, wegen der die LLM-Benennung
  nicht im Scan läuft. Danach kostet jede Prüfung ~300 ms, taugt also nicht für eine enge
  Schleife. Und kleine Spielschriften erkennt OCR unzuverlässig: ohne Toleranz („enthält"
  statt „ist gleich") ist es unbrauchbar.
- **Symmetrie:** im Inspektor steht die Text-Bedingung **neben** der Farb-Bedingung im
  selben Abschnitt und in derselben Form (Überschrift, ⓘ, Zahlenfeld) — nicht als zweiter
  Abschnitt darunter. Es ist dieselbe Frage („ist der Schritt dran?"), nur eine andere
  Messung.
- **Ansatz:** `WaitCondition` um `ocr_region` + `ocr_text`/`ocr_min` erweitern, ausgewertet
  an derselben Stelle wie die Farbe (`_farb_schleife`). Vorwärmen beim Programmstart, nicht
  im Worker. Fehlt OCR, wird gemeldet und übersprungen — wie heute ohne Pillow.

## Idle-Clans-spezifisch

### Inventory-Full-Detection
Template-Match oder Pixel-Trigger auf "Inventory full"-Popup, dann entweder Auto-Bank-Trip-Sequenz triggern oder sauber stoppen.

- **Nutzen:** Verhindert dass der Bot nach 2 Stunden ohne Ertrag weiterläuft.
- **Tradeoff:** Bank-Trip-Sequenz ist hoch individuell (Spielposition abhängig). Einfache Variante: nur Stop + Notify.
- **Ansatz:** Neuer Step-Typ `check_inventory` mit Template, der bei Fund eine andere Sequenz triggert.

### HP/Food-Trigger
Bei niedrigem HP automatisch Food klicken (Pixel-Farbtest auf HP-Bar).

- **Nutzen:** Ermöglicht Combat-AFK auch bei Gegnern die Schaden machen.
- **Tradeoff:** HP-Bar-Position muss kalibriert sein. Farberkennung bei verschiedenen HP-Stufen (grün → gelb → rot) komplex.
- **Ansatz:** Background-Watcher mit `wait_pixel`-ähnlicher Logik, aber parallel zur Sequenz. Bei Trigger wird ein definierter Punkt/Taste ausgelöst.

## Weitere Ideen (Kurzform)

- **XP-Tracker**: OCR oder Pixel-Tracking der XP-Anzeige für Skill-Progress-Schätzung.
- **Death-Screen-Detection**: Analog zu Disconnect, spezifisch für Ingame-Tod.
- **Auto-Login**: Automatisches Re-Login nach Session-Timeout (riskant – nur mit gespeicherten Credentials, potenzielles Sicherheitsrisiko).
- **Punkt-Gesundheit vor dem Start**: alle Punkte einer Sequenz in einem Rutsch gegen ihre
  gespeicherte Farbe halten, bevor der Lauf beginnt. Fängt ein umgebautes Spiel-UI in zwei
  Sekunden statt nach einer Stunde Fehlklicks. Haken: die meisten Punkte liegen in
  Untermenüs, die gerade nicht offen sind — ohne eine Regel dafür meldet der Test fast alles
  als „weicht ab" und ist damit wertlos. Tragfähig wohl nur für die Punkte der INIT-Phase.
- **Klick-Runde auch für Scan-Regionen**: heute setzt sie nur Punkte, Slots bleiben `repair`
  vorbehalten. Eine Runde, die auch eine Region neu aufziehen lässt, spart den Wechsel
  zwischen zwei Werkzeugen — misst aber schlechter, als `repair` es kann.
- **Warteschlange mehrerer Sequenzen**: nachts A, morgens B. Der Worker führt genau eine
  Sequenz aus (`state.active_sequence`), das gehört also eine Ebene darüber und nicht in ihn
  hinein.
- **Overlay während des Laufs**: ein durchklickbares Fenster, das die nächste Klickstelle
  markiert. Beim Suchen eines hängenden Schritts unschlagbar, kostet aber ein zweites
  GUI-Fenster samt plattformspezifischer Klick-Durchlässigkeit.
