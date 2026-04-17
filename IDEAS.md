# Feature-Ideen (Backlog)

Sammlung von Features, die diskutiert aber nicht umgesetzt wurden. Kurzbeschreibung + Tradeoff, damit eine spätere Entscheidung ohne erneute Analyse möglich ist.

## Reliability

### Disconnect-Detection
Pixel-Trigger oder Template-Match auf Login-Screen / Verbindungsfehler-Popup, dann Auto-Reconnect oder sauberer Stop.

- **Nutzen:** Verhindert dass der Bot stundenlang ins Leere klickt, wenn das Spiel abstürzt oder die Verbindung weg ist.
- **Tradeoff:** Benötigt eine kalibrierte Pixel-Position/Template pro Benutzer. Auto-Reconnect ist riskant (Passwort-Eingabe o.ä.) – sicherer: nur Stop + Notify.
- **Ansatz:** Neuer SequenceStep-Typ oder Background-Watcher (ähnlich Boss-Watcher), der periodisch prüft.

## Safety

### Session-Zeitlimit + Break-Scheduler
Harte Obergrenze (z.B. max. 6h pro Tag), danach automatischer Stop. Plus geplante Pausen (z.B. alle 60min für 2-5min).

- **Nutzen:** Schutz vor Bans durch 24/7-Laufzeit. Kombiniert mit Humanization zusätzliche Tarnung.
- **Tradeoff:** Reduziert Throughput, muss konfigurierbar sein.
- **Ansatz:** Zwei neue Config-Werte (`max_session_hours`, `break_interval_min` + `break_duration_min`). Im Main-Loop zwischen Zyklen prüfen.

## Observability

### Discord/Telegram-Webhook-Notifications
Ping bei wichtigen Events: Boss erkannt (LLM), Inventory voll, unerwarteter Stop, Disconnect, Session-Ende.

- **Nutzen:** Kein ständiger Blick aufs Fenster nötig. Besonders stark in Kombination mit LLM-Boss-Detection.
- **Tradeoff:** Webhook-URL als Secret verwalten (nicht ins Repo). Netzwerk-Abhängigkeit.
- **Ansatz:** Neues Modul `autoclicker/notifications.py` mit `send_webhook(url, message, image=None)`. Hook-Points in execution.py.

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

- **Dry-Run / Simulation**: Zeigt was passieren würde ohne zu klicken (für Sequenz-Debugging).
- **Profile-Export/Import**: Komplette Config als Bundle teilen.
- **Multi-Monitor / DPI-Awareness**: Korrekte Koordinaten bei Scaling ≠ 100%.
- **XP-Tracker**: OCR oder Pixel-Tracking der XP-Anzeige für Skill-Progress-Schätzung.
- **Death-Screen-Detection**: Analog zu Disconnect, spezifisch für Ingame-Tod.
- **Auto-Login**: Automatisches Re-Login nach Session-Timeout (riskant – nur mit gespeicherten Credentials, potenzielles Sicherheitsrisiko).
