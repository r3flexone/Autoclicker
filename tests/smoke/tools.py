"""Rauchtest Werkzeuge-Reiter: prüfen, kalibrieren, Farbfrage, Klick-Runde."""

import re
from pathlib import Path

from ._bridge import Window, main, sandbox


def source_wz() -> str:
    """Der `WZ_TOOLS`-Block aus `app.js` — die Liste, die die Seite zeichnet."""
    # Absolut, denn `sandbox()` wechselt vorher das Arbeitsverzeichnis.
    file = (Path(__file__).resolve().parents[2]
             / "autoclicker/editors/sequence_studio/web/app.js")
    source = file.read_text(encoding="utf-8")
    ab = source.index("const WZ_TOOLS = [")
    return source[ab:source.index("];", ab)]


def setup():
    """Ein kleiner Bestand plus die Brücke darauf — wie im Vertragstest."""
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import (
        AutoClickerState, ClickPoint, ItemProfile, ItemScanConfig,
        LoopPhase, Sequence, SequenceStep,
    )
    from autoclicker.persistence import (
        list_available_sequences, save_sequence_file, sequence_file, save_item_scan,
    )

    sandbox("rauch_wz_")
    st = AutoClickerState()
    seq = Sequence(name="Farm", loop_phases=[LoopPhase(name="A", steps=[
        SequenceStep(point_id=1, delay_before=3.0), SequenceStep(point_id=2)])],
        points=[ClickPoint(id=1, x=100, y=100, name="Sammeln",
                           color=(10, 200, 30)),
                ClickPoint(id=2, x=900, y=600, name="Bestaetigen"),
                ClickPoint(id=3, x=400, y=300, name="Menue")])
    st.active_sequence = seq
    st.points = seq.points
    save_sequence_file(seq, sequence_file(seq.name))
    # Absichtlich unvollständig, damit die Prüfung etwas darstellt.
    save_item_scan(ItemScanConfig(
        name="Inventar", owner_sequence="Farm",
        items=[ItemProfile(name="Geist")],
    ))

    b = StudioBridge(seq, Path(dict(list_available_sequences())["Farm"]), "sequences")
    # Maus und Bildschirm gibt es hier nicht: beide werden gestellt, alles andere
    # laeuft wie im Fenster.
    b._await_position = lambda: (555, 444, "")
    b._color_at = staticmethod(lambda x, y: (200, 10, 30))
    return b


def run():
    b = setup()
    error = []

    def expect(condition, text):
        if not condition:
            error.append(text)

    with Window(b) as f:
        f.tab("tools")
        # **Gegen die Tabelle in der Seite gemessen, nicht gegen eine getippte
        # Zahl.** Hier stand `== 4`, als es vier Werkzeuge gab; mit dem fuenften
        # und sechsten war der Pin schlicht falsch, ohne dass jemand etwas
        # kaputtgemacht haette. Gezaehlt wird jetzt, was `WZ_TOOLS` fuehrt.
        target = len(re.findall(r'\{key: "', source_wz()))
        expect(f.count("#wz-left button") == target,
               f"{target} Werkzeuge erwartet (je eines aus WZ_TOOLS), "
               f"da: {f.count('#wz-left button')}")
        # **Der Sequenzname steht EINMAL.** Links stand „offene Sequenz Farm" —
        # eingebaut, als die Kopfleiste ihre Sequenz-Bedienelemente in diesem
        # Reiter noch ausblendete. Seit die Auswahl in jedem Reiter steht, stand
        # er dreimal gleichzeitig auf dem Schirm: Auswahl, links, Bezugszeile.
        expect("Farm" not in f.text("#wz-left"),
               f"der Sequenzname steht wieder doppelt links: {f.text('#wz-left')[:80]!r}")

        # **Jedes Werkzeug sagt, WORAUF es wirkt** — das ist die Regel des
        # Reiters, und „Farben analysieren" hielt sie als einziges nicht ein.
        # In der Tabelle stand dort `bezug: "bestand"`, was fuer ein Werkzeug,
        # das nur misst, schlicht falsch gewesen waere; gezeichnet wurde die
        # Zeile gar nicht, also fiel die Unwahrheit nicht auf.
        for w in re.findall(r'\{key: "([a-z]+)"', source_wz()):
            f.click(f".wz-nav.{w}")
            expect(f.count("#wz-middle .wz-scope") == 1,
                   f"Werkzeug '{w}' hat keine Bezugszeile")
            expect(f.count("#wz-right .heading") >= 1,
                   f"Werkzeug '{w}' hat keine Ueberschrift in der rechten Spalte")

        # **Ein ⓘ haengt an einer BESCHRIFTUNG.** `wzInfo()` warf den Titel in
        # den Tooltip; uebrig blieb ein nackter Kreis in der Flaeche. Und der
        # Kasten trug die Klasse `info` — also die des runden ⓘ-Knopfes (13 px,
        # `flex:none`, zentriert): er erbte dessen Gestalt und sein Inhalt stand
        # mittig darueber hinaus, nach links aus dem Fenster heraus. Dieselbe
        # Falle wie einmal beim Status („Zustandsklassen bekommen ein Praefix").
        f.click(".wz-nav.check")
        compact = f.page.eval_on_selector_all(".wz-info-compact", """ns => ns.map(n => ({
          cls: n.className,
          text: (n.textContent || "").trim(),
          width: Math.round(n.getBoundingClientRect().width),
          links: Math.round(n.getBoundingClientRect().left)}))""")
        expect(compact, "kein einziger Hinweis mit ⓘ im Werkzeuge-Reiter")
        for k in compact:
            expect("info" not in k["cls"].split(),
                   f"der Hinweiskasten traegt die ⓘ-Knopfklasse: {k}")
            expect(len(k["text"]) > 3, f"Hinweis ohne sichtbaren Titel: {k}")
            expect(k["links"] >= 0, f"Hinweis laeuft links aus dem Fenster: {k}")

        # --- Aufnahme: der normale Weg ist vollständig im Studio sichtbar ---
        f.click_text("#wz-left button", "Sequenz aufnehmen")
        expect(f.count(".wz-recording-form input") == 2,
               "Name und Zyklen der Aufnahme fehlen")
        expect(f.count(".wz-recording-form textarea") == 1,
               "Notiz der Aufnahme fehlt")
        expect(f.count(".wz-recording-output") == 1,
               "rollende Live-Ausgabe der Aufnahme fehlt")
        keys_list = [z.inner_text() for z in
                  f.page.query_selector_all("#wz-middle .wz-keys .wz-key")]
        expect(len(keys_list) == 8, f"acht Aufnahme-Hotkeys erwartet, da: {keys_list}")
        expect("Aufnahme starten" in f.text("#wz-middle"), "sichtbarer Start fehlt")
        f.image("wz_aufnahme")

        # --- Pruefen ---
        f.click_text("#wz-left button", "Bestand prüfen")
        f.click_text("#wz-middle button", "Jetzt prüfen")
        expect(f.count(".wz-finding") == 2, "zwei Befunde erwartet")
        expect("Fehler" in f.status(), f"Status nach Pruefen: {f.status()!r}")
        # **Rechts muss der BERICHT stehen, nicht irgendein Text.** Hier stand
        # `bool(text.strip())` — und „Noch nichts geprüft." ist nicht leer. Der
        # Pin war damit erfüllt, während die Spalte nie nachgezogen wurde:
        # `wzCheck()` rief nur `wzRenderMiddle()`. Ausgerechnet diese Spalte
        # listet, WAS geprüft wurde, und ohne sie ist „Alles in Ordnung" eine
        # Behauptung — genau die Begründung, mit der sie gebaut wurde.
        expect("Noch nichts geprüft" not in f.text("#wz-right"),
               "rechts steht nach dem Pruefen weiter „Noch nichts geprueft.“")
        expect(f.count("#wz-right .wz-checked") >= 1,
               f"rechts fehlt die Liste der geprueften Bereiche: "
               f"{f.text('#wz-right')[:80]!r}")
        f.image("wz_pruefen")

        # --- Punkte verwalten: „sicher loeschen" muss auch loeschen koennen ---
        # `disabled: punkt.verwendungen.length` — und `el()` setzt jedes nicht
        # falsy Attribut, also auch `disabled="0"`. Ein vorhandenes
        # `disabled`-Attribut sperrt unabhaengig von seinem Wert: der Knopf war
        # bei 0 Verwendungen genauso tot wie bei 3, also immer. In einem
        # Werkzeug, das „Aufnehmen, nachmessen, umbenennen und sicher loeschen"
        # verspricht.
        f.click_text("#wz-left button", "Punkte verwalten")
        # Nicht der Sammelknopf „N ungenutzte loeschen" (der ist nie gesperrt,
        # er loescht nur, was 0x verwendet wird), sondern der des Punkts.
        locked = f.page.eval_on_selector(
            "#wz-middle button.danger:not(#wz-points-prune)", "e => e.disabled")
        expect(locked is True,
               "Punkt #1 wird verwendet — der Loeschen-Knopf muesste gesperrt sein")
        # #3 „Menue" haengt an keinem Block.
        f.page.select_option("#wz-middle select", index=2)
        f.settle()
        free = f.page.eval_on_selector("#wz-middle button.danger", "e => e.disabled")
        expect(free is False,
               "Punkt #3 wird nirgends verwendet — der Loeschen-Knopf ist trotzdem gesperrt")
        expect("nirgends verwendet" in f.text("#wz-right"),
               f"rechts fehlt die Freigabe: {f.text('#wz-right')[:80]!r}")

        # --- Farbfrage: die Stelle hat eine andere Farbe als der Punkt ---
        f.click_text("#wz-left button", "Kalibrieren")
        expect("gesamte gespeicherte Bestand" in f.text("#wz-middle"),
               "der Bezug fehlt beim Kalibrieren")
        f.click("#wz-middle .wz-ref button")
        expect(f.count(".wz-color-question") == 1, "keine Farb-Rueckfrage")
        expect(f.count(".wz-color") == 2, "beide Farben sollten dastehen")
        expect("Verschiebung" not in f.text("#wz-middle"),
               "trotz Rueckfrage schon gesetzt")
        f.image("wz_farbfrage")

        f.click_text(".wz-color-question button", "Trotzdem setzen")
        # Der Versatz steht als zwei Kennzahlen unter „BERECHNETER TRANSFORM",
        # nicht mehr als ein Satz „Verschiebung: …". Gemessen wird deshalb der
        # Kennzahlen-Block — der Satz war eine Formulierung, die Zahlen sind
        # die Aussage.
        metrics = f.text("#wz-middle .wz-metrics")
        expect("+455" in metrics and "+344" in metrics,
               f"Versatz falsch: {metrics!r}")
        expect(f.count("#wz-middle input[type=checkbox]") == 3, "drei Umfang-Haken")
        expect("Stelle(n)" in f.text("#wz-right"), "keine Vorschau rechts")
        f.image("wz_kalib")

        f.click_text("#wz-middle button", "Umrechnen und speichern")
        expect("Kalibriert" in f.status(), f"Anwenden: {f.status()!r}")
        expect([p.x for p in b.points] == [555, 1355, 855],
               f"Punkte nicht gewandert: {[(p.id, p.x) for p in b.points]}")

        # --- Nachklicken: starten UND beenden ---
        f.click_text("#wz-left button", "Punkte nachklicken")
        expect("die offene Sequenz" in f.text("#wz-middle"), "Bezug fehlt")
        expect("Farm" in f.text("#wz-middle"), "Sequenzname fehlt")
        buttons = [k.inner_text() for k in
                   f.page.query_selector_all("#wz-middle button")]
        expect(len(buttons) == 3,
               f"starten + uebernehmen + verwerfen erwartet, da: {buttons}")
        # Die vier Griffe stehen als TABELLE da, nicht als Absatz - man schlaegt
        # sie mitten im Klicken nach.
        keys_list = [z.inner_text() for z in
                  f.page.query_selector_all("#wz-middle .wz-keys .wz-key")]
        expect(len(keys_list) == 4, f"vier Hotkeys erwartet, da: {keys_list}")
        expect("CTRL+ALT+J" in keys_list, f"Uebernehmen-Taste fehlt: {keys_list}")
        expect("übernimmst" in f.text("#wz-middle .wz-rule"),
               "die Regel 'nichts wird geschrieben' fehlt")
        f.click_text("#wz-middle button", "Runde starten")
        expect("Farm" in f.status(), f"Start nennt die Sequenz nicht: {f.status()!r}")
        # Verwerfen ist der Ausgang, der NICHTS schreibt - und er muss es sagen.
        f.click_text("#wz-middle button", "Verwerfen")
        expect("sequence.json" in f.status(), f"Verwerfen: {f.status()!r}")
        f.click_text("#wz-middle button", "Übernehmen")
        expect("bernommen" in f.status(), f"Uebernehmen: {f.status()!r}")
        f.image("wz_klick")

        # --- Der Aufnahme-Waechter fragt erst, wenn es etwas zu finden gibt ---
        # `sequence_list()` laedt JEDE Sequenzdatei einzeln — genau deshalb
        # zieht `render()` sie nicht nach. Der langsame Zweig rief sie
        # trotzdem im Sekundentakt ab dem Druck auf „Aufnahme starten", also
        # waehrend der ganzen Aufnahme; und die dauert lange, weil der Nutzer
        # so lange im Spiel ist. Solange sie laeuft, kann die Datei aber gar
        # nicht da sein.
        counted = f.page.evaluate("""() => {
          window.__liste = 0;
          const alt = window.ask;
          window.ask = async function (name, daten) {
            if (name === "sequence_list") window.__liste++;
            return alt(name, daten);
          };
          // Aufnahme laeuft: der Waechter darf nur warten.
          wzRecordingStarted = true;
          wzRecordingName = "Gibt-Es-Nicht";
          wzRecordingLive = {active: true, pausiert: false, count: 0, events: []};
          wzWatchRecording();
          return true;
        }""")
        expect(counted, "der Waechter liess sich nicht anwerfen")
        f.page.wait_for_timeout(3400)
        during = f.page.evaluate("window.__liste")
        expect(during == 0,
               f"der Waechter fragt waehrend der laufenden Aufnahme: {during}x")
        # Endet sie, muss er sofort nachsehen — sonst faende er sie nie.
        f.page.evaluate("wzRecordingLive = {active: false, pausiert: false, "
                         "count: 0, events: []}")
        f.page.wait_for_timeout(2400)
        after_that = f.page.evaluate("window.__liste")
        expect(after_that > 0, "nach dem Ende der Aufnahme fragt der Waechter gar nicht")
        f.page.evaluate("wzRecordingStarted = false; ++wzRecordingPoll; "
                         "++wzRecordingLivePoll;")

        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Werkzeuge", run)
