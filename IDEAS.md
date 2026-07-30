# Feature-Ideen (Backlog)

Sammlung von Features, die diskutiert aber **nicht umgesetzt** wurden. Kurzbeschreibung +
Tradeoff, damit eine spätere Entscheidung ohne erneute Analyse möglich ist.

Ist ein Eintrag gebaut, fliegt er hier raus — ein Backlog, das Erledigtes mitführt, verliert
seinen Zweck. Zuletzt entfallen, weil umgesetzt: *Profile-Export/Import* (`import_export.py`,
inklusive Config und Koordinaten-Remapping), *Multi-Monitor / DPI-Awareness*
(`SetProcessDpiAwareness(2)` in `winapi.py`, virtueller Desktop in `imaging.py`),
*Dry-Run / Simulation* (manueller Modus + Debug-Stufe 2).

## Bedienung

### Einstellungs-Menü (Config im Programm statt im Texteditor)
`AppConfig` hat 66 Werte. Im Programm umschaltbar sind drei: `debug_log`, `debug_detail`,
`boss_learn_global`. Alles andere — Klick-Verzögerungen, Pixel-Toleranz, Timeout-Verhalten,
Humanization, Fokus-Check, LLM, OCR — geht nur, indem man `config.json` im Texteditor
aufmacht und weiß, wie das Feld heißt.

- **Nutzen:** Nimmt dem Programm die letzte Stelle, an der man eine Datei von Hand editieren muss. Wer die Toleranz eines Farb-Triggers nachziehen will, muss dafür nicht wissen, dass das Feld `pixel_wait_tolerance` heißt.
- **Tradeoff:** 66 Werte sind zu viele für ein flaches Menü — es braucht die Sektionen, sonst wird es unübersichtlicher als die JSON. Und jeder neue Config-Wert muss im Menü landen, sonst entsteht wieder eine Zwei-Klassen-Config.
- **Ansatz:** Das Gerüst liegt schon da: `_CONFIG_SECTIONS` in `config.py` gruppiert alle Felder nach Thema, die Kommentare an den Dataclass-Feldern sind brauchbare Erklärtexte. Das Menü daraus **generieren** statt handschreiben — dann kann kein Feld vergessen werden. Bool umschalten, Zahlen mit Bereichsangabe, feste Auswahl (`pixel_timeout_action`) als Liste; Validierung übernimmt `AppConfig.__post_init__`, gespeichert wird sofort über `save_config`.

## Reliability

### Disconnect-Detection
Pixel-Trigger oder Template-Match auf Login-Screen / Verbindungsfehler-Popup, dann Auto-Reconnect oder sauberer Stop.

- **Nutzen:** Verhindert dass der Bot stundenlang ins Leere klickt, wenn das Spiel abstürzt oder die Verbindung weg ist.
- **Tradeoff:** Benötigt eine kalibrierte Pixel-Position/Template pro Benutzer. Auto-Reconnect ist riskant (Passwort-Eingabe o.ä.) – sicherer: nur Stop + Notify.
- **Ansatz:** Neuer SequenceStep-Typ oder Background-Watcher (ähnlich Boss-Watcher), der periodisch prüft.

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

- **XP-Tracker**: OCR oder Pixel-Tracking der XP-Anzeige für Skill-Progress-Schätzung.
- **Death-Screen-Detection**: Analog zu Disconnect, spezifisch für Ingame-Tod.
- **Auto-Login**: Automatisches Re-Login nach Session-Timeout (riskant – nur mit gespeicherten Credentials, potenzielles Sicherheitsrisiko).
