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
Reiter im Sequenz-Studio, aus `_CONFIG_SECTIONS` + `config_meta.py` generiert).

## Bedienung

### Sequenz-Studio: Screenshot-Vorschau in der Punkte-Palette
Die Punkte als Marker auf einem Bildschirmfoto, statt nur als Koordinatenpaare.

- **Nutzen:** „Punkt #3" sagt einem nichts; auf dem Bild sieht man sofort, welcher Knopf
  gemeint ist. Für das Sortieren einer aufgenommenen Sequenz ist das der Unterschied.
- **Tradeoff:** Der Subprozess müsste einen Screenshot aufnehmen (`imaging.take_screenshot`,
  braucht Pillow/Windows) und als Data-URL in die Seite reichen — und das Bild ist der
  Bildschirm von *jetzt*, nicht der vom Zeitpunkt der Aufnahme. Wenn das Spiel gerade
  nicht läuft, zeigt die Vorschau den Desktop.

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
