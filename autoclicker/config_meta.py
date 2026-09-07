"""
Beschreibung der Config-Felder für die Oberfläche — was `AppConfig` nicht sagt.

`AppConfig` kennt Name, Typ und Standardwert; `_CONFIG_SECTIONS` kennt Gruppen
und Reihenfolge. Was fehlt, ist alles, was ein Mensch braucht, um den Wert
einzustellen: eine Beschriftung in Klartext, ein Satz Erklärung, die Art des
Bedienelements und die Abhängigkeit vom Schalter darüber.

**Warum das hier liegt und nicht im HTML.** Die Oberfläche ist der ungetestete
Teil des Studios (s. `editors/sequence_studio/bridge.py`) — stünde die Tabelle
dort, fiele ein neu hinzugekommenes Config-Feld erst auf, wenn jemand es sucht.
Hier hält ein Test sie gegen die Dataclass: **jedes** Feld hat einen Eintrag,
und jeder Eintrag gehört zu einem Feld. Ein Feld, das nur in der Datei existiert,
gibt es damit nicht mehr.

Die Erklärungen sind bewusst das, was die Kommentare in `config.py` nicht sein
können: dort steht, was der Wert technisch tut, hier steht, wann man ihn anfasst.
"""

from dataclasses import dataclass

# Die Arten des Bedienelements. Mehr gibt es nicht — wer eine sechste braucht,
# trägt sie hier UND in der Oberfläche ein (`cfgFeld()` in web/index.html); ein
# Test hält beide Listen gegeneinander.
ART_BOOL = "bool"        # Kippschalter
ART_INT = "int"          # ganze Zahl
ART_FLOAT = "float"      # Kommazahl
ART_RATIO = "ratio"      # Kommazahl 0–1 (wird als Prozent angezeigt)
ART_TEXT = "text"        # einzeilig
ART_AREA = "area"        # mehrzeilig
ART_ENUM = "enum"        # feste Auswahl, `optionen`
ART_XY = "xy"            # Schalter + Koordinatenpaar (nur `scan_park_mouse`)

ARTEN = (ART_BOOL, ART_INT, ART_FLOAT, ART_RATIO, ART_TEXT, ART_AREA,
         ART_ENUM, ART_XY)


@dataclass(frozen=True)
class M:
    """Ein Feld, wie die Oberfläche es zeigt.

    `dep`/`dep_nicht`/`dep_min` machen ein Feld **grau, nicht unsichtbar**: dass
    es unter `llm_enabled` dreizehn weitere Felder gibt, ist die halbe
    Information. Ausgeblendete Felder sucht man in der Datei.
    """
    label: str
    art: str
    hilfe: str = ""
    einheit: str = ""
    # Für ART_ENUM: (Wert, Beschriftung). Der Wert ist der, der in der Datei
    # steht — auch `None` (ocr_backend: automatisch).
    optionen: tuple = ()
    # Was ein leeres Feld bzw. eine 0 bedeutet ("unendlich", "Standard-Port").
    # Ohne diesen Text liest sich eine 0 wie "aus", und bei click_max_total
    # heisst sie das Gegenteil.
    leer: str = ""
    # Ein Knopf UNTER dem Feld: `(Bruecken-Methode, Beschriftung)`. Dafuer gibt
    # es genau einen Fall und einen guten Grund — den Katalog konnte bis hierhin
    # nur `python tools/katalog.py` anlegen, also ausgerechnet die Datei, ohne
    # die das LLM frei raet, liess sich im Fenster nicht beschaffen. Wer die
    # Datei im Feld sieht, soll sie dort auch holen koennen.
    aktion: tuple = ()
    dep: str = ""            # wirkt nur, wenn dieses bool-Feld AN ist
    dep_nicht: str = ""      # wirkt nur, wenn dieses bool-Feld AUS ist
    dep_min: str = ""        # wirkt nur, wenn dieses Zahlfeld > 0 ist

    def as_dict(self) -> dict:
        """Als JSON-Werte für die Brücke — leere Felder fallen weg."""
        daten = {"label": self.label, "art": self.art}
        if self.hilfe:
            daten["hilfe"] = self.hilfe
        if self.einheit:
            daten["einheit"] = self.einheit
        if self.optionen:
            daten["optionen"] = [{"wert": w, "text": t} for w, t in self.optionen]
        if self.leer:
            daten["leer"] = self.leer
        if self.aktion:
            daten["aktion"] = {"befehl": self.aktion[0], "text": self.aktion[1]}
        for name in ("dep", "dep_nicht", "dep_min"):
            wert = getattr(self, name)
            if wert:
                daten[name] = wert
        return daten


META: dict = {
    # === PROGRAMMSTART ===
    "studio_open_on_start": M(
        "Studio beim Start öffnen", ART_BOOL,
        "An: Das Studio ist die Startoberfläche; die Konsole bleibt nur Log und "
        "Rückfallweg für Konsolenwerkzeuge. Aus: Das Programm startet mit der TUI; "
        "das Studio lässt sich weiterhin per Hotkey öffnen."),

    # === KLICK ===
    "click_per_point": M(
        "Klicks pro Punkt", ART_INT,
        "Wie oft ein Klick-Block an derselben Stelle klickt. Für Spiele, die "
        "einen Doppelklick brauchen."),
    "click_max_total": M(
        "Klicks gesamt maximal", ART_INT,
        "Notaus über die Menge: nach so vielen Klicks stoppt der Lauf.",
        leer="unbegrenzt"),
    "click_move_delay": M(
        "Pause vor dem Klick", ART_FLOAT,
        "Zeit zwischen Mausbewegung und Klick. Zu kurz, und das Spiel klickt "
        "noch dort, wo die Maus vorher stand.", einheit="s"),
    "click_post_delay": M(
        "Pause nach dem Klick", ART_FLOAT,
        "Zeit, bevor die Maus weiterziehen darf. Der häufigste Grund für einen "
        "Klick, der im Spiel nicht ankommt.", einheit="s"),

    # === SICHERHEIT ===
    "failsafe_enabled": M(
        "Fail-Safe", ART_BOOL,
        "Maus in die obere linke Ecke reissen stoppt alles. Der Notausstieg, "
        "wenn eine Sequenz etwas anderes tut als gedacht."),
    "failsafe_x": M(
        "Fail-Safe X", ART_INT, "Löst aus, sobald die Maus-X-Koordinate "
        "kleiner oder gleich diesem Wert ist.", einheit="px", dep="failsafe_enabled"),
    "failsafe_y": M(
        "Fail-Safe Y", ART_INT, "Löst aus, sobald die Maus-Y-Koordinate "
        "kleiner oder gleich diesem Wert ist.", einheit="px", dep="failsafe_enabled"),

    # === PIXEL-ERKENNUNG ===
    "punkt_radius": M(
        "Punkte zusammenfassen ab", ART_INT,
        "Bis zu diesem Abstand gilt eine Stelle als derselbe Punkt und wird "
        "wiederverwendet, statt einen zweiten anzulegen. Man trifft denselben "
        "Knopf beim Aufnehmen nie zweimal pixelgenau — so entstanden vier Punkte "
        "auf einem Knopf. 0 = nur exakt gleiche Koordinate.", einheit="px"),
    "punkt_farbtoleranz": M(
        "...aber nur bei gleicher Farbe", ART_INT,
        "Weicht die Farbe stärker ab, entsteht IMMER ein eigener Punkt — auch einen Pixel daneben. An einer Farbgrenze klickt man zwei verschiedene Dinge, und zwei Spiele übereinander unterscheiden sich in nichts anderem.",
        dep_min="punkt_radius"),
    "pixel_wait_tolerance": M(
        "Farb-Toleranz", ART_INT,
        "Wie weit die gemessene Farbe von der gespeicherten abweichen darf "
        "(RGB-Abstand). Zu klein, und ein Farbverlauf im Spiel wird nie erkannt; "
        "zu gross, und jede Fläche passt."),
    "pixel_wait_timeout": M(
        "Timeout Farb-Trigger", ART_INT,
        "Wie lange ein Farb-Trigger auf seine Farbe wartet, bevor die Aktion "
        "unten greift.", einheit="s", leer="unbegrenzt warten"),
    "pixel_timeout_action": M(
        "Nach dem Timeout", ART_ENUM,
        "Was passiert, wenn die Farbe nicht kommt und der Block kein ELSE hat. "
        "Die Voreinstellung bricht den ganzen Zyklus ab, nicht nur den Schritt.",
        optionen=(("skip_cycle", "Zyklus abbrechen"),
                  ("restart", "Sequenz neu starten"),
                  ("stop", "Sequenz stoppen"))),
    "pixel_check_interval": M(
        "Prüf-Intervall", ART_FLOAT,
        "Wie oft die Farbe während des Wartens gemessen wird. Jede Messung ist "
        "ein Screenshot — kürzer heisst schneller reagieren und mehr Last.",
        einheit="s"),
    "pixel_max_consecutive_timeouts": M(
        "Notbremse nach X Timeouts", ART_INT,
        "Laufen so viele Farb-Trigger hintereinander in ihren Timeout, stimmt "
        "etwas Grundsätzliches nicht (Fenster zu, Spiel abgestürzt).",
        leer="keine Notbremse"),
    "pixel_consecutive_action": M(
        "Notbremse tut", ART_ENUM, "Was beim Auslösen der Notbremse passiert.",
        optionen=(("stop", "Sequenz stoppen"),
                  ("quit", "Programm beenden"),
                  ("exit", "Programm beenden (sofort)")),
        dep_min="pixel_max_consecutive_timeouts"),
    "pixel_show_delay": M(
        "Zeiger-Dauer", ART_FLOAT,
        "Wie lange die Maus beim Farbwarten auf dem Prüf-Pixel stehen bleibt.",
        einheit="s", dep="debug_show_pixel_position"),

    # === NACHPRUEFUNG ===
    "verify_timeout": M(
        "Wirkung abwarten", ART_FLOAT,
        "Wie lange die Nachprüfung auf die erwartete Wirkung wartet, bevor sie "
        "die Aktion wiederholt.", einheit="s"),
    "verify_retries": M(
        "Wiederholungen", ART_INT,
        "Wie oft die Aktion neu ausgeführt wird, wenn nichts passiert ist. "
        "Der eigentliche Gewinn der Nachprüfung — der häufigste Grund für einen "
        "wirkungslosen Klick ist vorübergehend.", leer="nicht wiederholen"),
    "verify_interval": M(
        "Prüf-Intervall", ART_FLOAT,
        "Wie oft während der Nachprüfung gemessen wird.", einheit="s"),

    # === SCAN ===
    "scan_click_immediate": M(
        "Sofort klicken", ART_BOOL,
        "Jeden Slot direkt nach seiner Erkennung klicken, statt erst alle zu "
        "scannen und dann zu klicken."),
    "scan_park_mouse": M(
        "Maus vor dem Scan parken", ART_XY,
        "Die Maus an eine Stelle fahren, bevor der Screenshot entsteht — sonst "
        "verdeckt der Cursor (oder ein Tooltip darunter) genau das Item, das "
        "erkannt werden soll."),
    "scan_slot_delay": M(
        "Pause zwischen Slots", ART_FLOAT, "Zeit zwischen zwei Slot-Scans.",
        einheit="s"),
    "scan_item_click_delay": M(
        "Pause nach Item-Klick", ART_FLOAT,
        "Zeit nach einem Klick auf ein gefundenes Item.", einheit="s"),
    "scan_marker_count": M(
        "Marker-Farben", ART_INT,
        "Wie viele häufigste Farben beim Lernen eines Items gemerkt werden. "
        "Mehr Marker heisst genauer und empfindlicher."),
    "scan_require_all_markers": M(
        "Alle Marker verlangen", ART_BOOL,
        "Ein Item gilt nur als erkannt, wenn jede gelernte Marker-Farbe im Slot "
        "vorkommt. Aus: es reicht die Mindestzahl darunter."),
    "scan_min_markers_required": M(
        "Marker mindestens", ART_INT,
        "Wie viele der gelernten Farben vorkommen müssen.",
        dep_nicht="scan_require_all_markers"),
    "scan_marker_min_pixels": M(
        "Pixel je Marker", ART_INT,
        "Wie viele abgetastete Pixel eine Marker-Farbe treffen müssen. Über 1 "
        "macht die Erkennung unempfindlich gegen einzelne Rausch-Pixel.",
        einheit="px"),
    "scan_market_value_file": M(
        "Marktwert-Tabelle", ART_TEXT,
        "Pfad zu einer Item→Gold-JSON aus market_analysis. Ist sie gesetzt, "
        "sortiert der Item-Scan seine Klicks nach Wert statt nach der von Hand "
        "getippten Priorität — und jedes Item MIT Wert gewinnt gegen jedes ohne.",
        leer="nach getippter Priorität"),
    "scan_catalog_file": M(
        "Item-Katalog", ART_TEXT,
        "Pfad zur katalog.json mit den echten Item-Namen des Spiels. Der Knopf "
        "darunter holt sie aus der offiziellen Spiel-API und trägt den Pfad "
        "gleich hier ein. Ist sie gesetzt, setzt „Aus Katalog einordnen“ "
        "Kategorie und Priorität, und die LLM-Benennung wählt aus den echten "
        "Namen statt frei zu raten. Die Kategorie hängt am Namen, nicht am "
        "LLM — sie funktioniert auch, wenn du den Namen selbst tippst.",
        leer="Kategorie und Namen bleiben Handarbeit",
        aktion=("katalog_holen", "Katalog aus der Spiel-API holen")),
    "scan_slot_hsv_tolerance": M(
        "Slot-Toleranz (HSV)", ART_INT,
        "Wie stark ein Slot-Hintergrund vom gelernten Farbton abweichen darf, "
        "damit die automatische Slot-Erkennung ihn noch findet."),
    "scan_slot_inset": M(
        "Slot-Einzug", ART_INT,
        "Wie viele Pixel vom Slot-Rand ignoriert werden. Der Rahmen des Slots "
        "gehört nicht zum Item und verfälscht sonst jeden Vergleich.",
        einheit="px"),
    "scan_slot_color_distance": M(
        "Hintergrund-Abstand", ART_INT,
        "Farbabstand, ab dem eine Farbe als Slot-Hintergrund gilt und beim "
        "Item-Lernen ausgeschlossen wird."),
    "scan_min_confidence": M(
        "Konfidenz für neue Profile", ART_RATIO,
        "Voreinstellung für neu angelegte Items — wie gut ein Template passen "
        "muss. Gespeicherte Items behalten ihren eigenen Wert."),
    "scan_confirm_delay": M(
        "Wartezeit vor Bestätigung", ART_FLOAT,
        "Voreinstellung für neue Items: Pause vor dem Bestätigungs-Klick.",
        einheit="s"),

    # === LLM VISION ===
    "llm_enabled": M(
        "LLM-Erkennung", ART_BOOL,
        "Boss-Namen von einem Bildmodell lesen lassen (Ollama oder LM Studio). "
        "Ohne diesen Schalter bleiben die Felder darunter wirkungslos, auch "
        "wenn ein einzelner Boss-Scan sie anfordert."),
    "llm_provider": M(
        "Anbieter", ART_ENUM, "Welche lokale Server-Software antwortet.",
        optionen=(("ollama", "Ollama"), ("lmstudio", "LM Studio")),
        dep="llm_enabled"),
    "llm_endpoint": M(
        "API-Adresse", ART_TEXT,
        "Volle URL, wenn der Server woanders läuft als auf dem Standard-Port.",
        leer="Standard-Port des Anbieters", dep="llm_enabled"),
    "llm_model": M(
        "Modell", ART_TEXT, "Name des Modells, wie der Server ihn kennt.",
        dep="llm_enabled"),
    "llm_timeout": M(
        "Timeout", ART_INT,
        "So lange steht der Worker still, wenn das Modell nicht antwortet. "
        "Deshalb läuft die LLM-Benennung neuer Items bewusst NICHT im Scan.",
        einheit="s", dep="llm_enabled"),
    "llm_retry_count": M(
        "Wiederholungen", ART_INT,
        "Wie oft bei „kein Boss erkannt“ neu gefragt wird.",
        leer="nicht wiederholen", dep="llm_enabled"),
    "llm_async": M(
        "Im Hintergrund", ART_BOOL,
        "Boss-Scan und Watcher in einem eigenen Thread — die Sequenz läuft "
        "weiter, während das Modell nachdenkt.", dep="llm_enabled"),
    "llm_boss_prompt": M(
        "Eigener Prompt", ART_AREA,
        "Ersetzt den eingebauten Text an das Modell.",
        leer="eingebauter Prompt", dep="llm_enabled"),
    "llm_reasoning": M(
        "Reasoning zulassen", ART_BOOL,
        "Denkschritte erlauben, wenn das Modell sie kann. Genauer und deutlich "
        "langsamer.", dep="llm_enabled"),
    "llm_max_tokens": M(
        "Antwort-Länge", ART_INT,
        "Obergrenze für die Antwort des Modells.",
        leer="automatisch (128 / 2048 mit Reasoning)", dep="llm_enabled"),
    "llm_debug": M(
        "Antworten mitschreiben", ART_BOOL,
        "Schreibt zu jeder Anfrage Modell, Prompt, die rohe JSON-Antwort und "
        "den daraus gelesenen Text in die Konsole — auch das Denk-Feld, das "
        "sonst verworfen wird. Der Weg, um eine leere Antwort einzuordnen: "
        "ein Modell ohne Bild-Fähigkeit, ein falscher Modellname und ein "
        "Reasoning-Modell ohne Token-Reserve sehen von aussen gleich aus.",
        dep="llm_enabled"),
    "llm_watcher_interval": M(
        "Watcher-Intervall", ART_FLOAT,
        "Wie oft der Boss-Watcher nachsieht.", einheit="s", dep="llm_enabled"),
    "llm_watcher_max_scans": M(
        "Watcher: max. Scans", ART_INT,
        "Danach gibt der Watcher auf und die Sequenz läuft weiter.",
        leer="unbegrenzt", dep="llm_enabled"),
    "llm_watcher_timeout": M(
        "Watcher: Timeout", ART_FLOAT,
        "Zeitgrenze für den Watcher.", einheit="s", leer="unbegrenzt",
        dep="llm_enabled"),
    "boss_learn_global": M(
        "Neue Bosse global lernen", ART_BOOL,
        "Ein von OCR oder LLM entdeckter unbekannter Boss landet in der "
        "globalen Bibliothek statt nur in diesem einen Scan. Gilt für beide "
        "Erkenner."),

    # === OCR ===
    "ocr_enabled": M(
        "OCR-Texterkennung", ART_BOOL,
        "Boss-Namen lokal aus dem Bild lesen. Schneller und billiger als das "
        "LLM, deshalb läuft OCR bei gleicher Einstellung zuerst. Achtung: der "
        "allererste Aufruf von EasyOCR lädt Modelle aus dem Netz."),
    "ocr_backend": M(
        "Erkenner", ART_ENUM, "Welche Bibliothek liest den Text.",
        optionen=((None, "automatisch"), ("easyocr", "EasyOCR"),
                  ("tesseract", "Tesseract")),
        dep="ocr_enabled"),
    "ocr_languages": M(
        "Sprachen", ART_TEXT,
        "Sprach-Codes mit Komma getrennt, z. B. „en,de“.", dep="ocr_enabled"),
    "ocr_min_confidence": M(
        "Mindest-Konfidenz", ART_RATIO,
        "Schlechter erkannter Text wird verworfen.", dep="ocr_enabled"),
    "ocr_retry_count": M(
        "Wiederholungen", ART_INT,
        "Wie oft bei zu niedriger Konfidenz neu gelesen wird.",
        leer="nicht wiederholen", dep="ocr_enabled"),

    # === WINDOW-FOKUS ===
    "window_focus_check": M(
        "Fenster-Fokus prüfen", ART_BOOL,
        "Vor jedem Klick und jeder Taste nachsehen, ob das Spielfenster vorn "
        "ist. Verhindert, dass eine Sequenz in ein anderes Programm tippt."),
    "window_focus_title": M(
        "Fenstertitel enthält", ART_TEXT,
        "Textstück aus dem Titel des Spielfensters, Gross-/Kleinschreibung egal.",
        dep="window_focus_check"),
    "window_focus_action": M(
        "Wenn nicht vorn", ART_ENUM,
        "Was passiert, solange ein anderes Fenster den Fokus hat.",
        optionen=(("pause", "warten, bis es vorn ist"),
                  ("stop", "Sequenz stoppen")),
        dep="window_focus_check"),

    # === HUMANIZATION ===
    "humanize_enabled": M(
        "Vermenschlichen", ART_BOOL,
        "Streuung in Klickpunkt und Zeiten, dazu Pausen. Ohne diesen Schalter "
        "sind die Felder darunter wirkungslos."),
    "humanize_click_jitter": M(
        "Klick-Streuung", ART_INT,
        "Maximale Abweichung vom Punkt je Klick. Sinnvoll sind 2–5; zu viel "
        "trifft den Knopf nicht mehr.", einheit="px", leer="exakt auf den Punkt",
        dep="humanize_enabled"),
    "humanize_micro_delay_min": M(
        "Extra-Pause min", ART_FLOAT,
        "Zusätzliche Zufallspause vor Klicks und Tasten, untere Grenze.",
        einheit="s", dep="humanize_enabled"),
    "humanize_micro_delay_max": M(
        "Extra-Pause max", ART_FLOAT,
        "Obere Grenze. Kleiner als das Minimum wird beim Speichern auf das "
        "Minimum gehoben.", einheit="s", dep="humanize_enabled"),
    "humanize_break_interval_min": M(
        "Pause alle", ART_FLOAT,
        "Nach so vielen Minuten Laufzeit eine längere Pause einlegen.",
        einheit="min", leer="keine Pausen", dep="humanize_enabled"),
    "humanize_break_duration_min": M(
        "Pausendauer min", ART_FLOAT, "Untere Grenze der Pausendauer.",
        einheit="min", dep="humanize_enabled"),
    "humanize_break_duration_max": M(
        "Pausendauer max", ART_FLOAT, "Obere Grenze der Pausendauer.",
        einheit="min", dep="humanize_enabled"),

    # === AUFNAHME ===
    "record_scroll": M(
        "Mausrad aufzeichnen", ART_BOOL,
        "Aus für Spiele, in denen das Rad nur die Ansicht dreht — solche "
        "Drehungen blähen die Aufnahme auf, ohne etwas zu bewirken."),

    # === SESSION-LOG ===
    "session_log_enabled": M(
        "Session-Log", ART_BOOL,
        "Schreibt jede Aktion und jede Erkennung als CSV mit. Auswerten mit "
        "tools/log_report.py — dort steht, welcher Schritt hängt."),
    "session_log_dir": M(
        "Log-Ordner", ART_TEXT, "Wohin die CSV-Dateien geschrieben werden.",
        dep="session_log_enabled"),

    # === TIMING ===
    "timing_pause_interval": M(
        "Puls während der Pause", ART_FLOAT,
        "Wie oft eine pausierte Sequenz nachsieht, ob es weitergeht.",
        einheit="s"),

    # === DATEIEN ===
    "migrate_on_start": M(
        "Beim Start aufräumen", ART_BOOL,
        "Hebt alle JSON-Dateien aufs aktuelle Format und legt vorher eine "
        "Sicherung unter backups/ an. Nur ausschalten, wenn Altbestand "
        "absichtlich eingefroren bleiben soll."),

    # === DEBUG ===
    "debug_log": M(
        "Stufe 1: alles ausgeben", ART_BOOL,
        "Jeder Schritt als eigene Zeile, statt einer Statuszeile, die sich "
        "selbst überschreibt."),
    "debug_detail": M(
        "Stufe 2: Detail + Zeiger", ART_BOOL,
        "Zusätzlich die Maus auf das Ziel setzen und ausschreiben, was kommt. "
        "Zieht Stufe 1 zwangsläufig mit — mehrzeilige Ausgabe verträgt sich "
        "nicht mit einer überschreibbaren Statuszeile."),
    "debug_show_pixel_position": M(
        "Prüf-Pixel zeigen", ART_BOOL,
        "Beim Warten auf eine Farbe kurz die Maus auf den gemessenen Pixel "
        "setzen — so sieht man, ob überhaupt die richtige Stelle geprüft wird."),
    "debug_save_templates": M(
        "Scan-Bilder sichern", ART_BOOL,
        "Legt Slot-Ausschnitt und Template bei jedem Vergleich in items/debug/ "
        "ab. Zum Nachsehen, warum ein Item nicht erkannt wird — füllt den "
        "Ordner schnell."),
}

