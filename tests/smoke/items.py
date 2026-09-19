"""Rauchtest Item-Masken: erkennen, Kategorie wählen und neu anlegen."""

from pathlib import Path

from ._image import inventory_image, mock_screen
from ._bridge import Window, main, sandbox


def setup():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import Sequence

    sandbox("rauch_items_")
    image, corners = inventory_image()
    mock_screen(image)

    b = StudioBridge(Sequence(name="Rauch"),
                     Path("sequences/smoke/sequence.json"), "sequences")
    b.scan_new({"name": "Inventar"})
    b.scan_screenshot()
    for sx, sy in corners:
        b.scan_mode_set({"mode": "slot"})
        b.scan_click({"x": sx, "y": sy})
        b.scan_click({"x": sx + 62, "y": sy + 60})
    b.scan_learn_preview({"scope": "all"})
    b.scan_learn_preview_apply({})
    b.scan_recognize()
    return b, len(corners)


def run():
    b, count = setup()
    error = []

    def expect(condition, text):
        if not condition:
            error.append(text)

    expect(len(b.items) == count, f"{count} Items erwartet, gelernt: {sorted(b.items)}")

    with Window(b) as f:
        f.tab("scans")
        name_field = f.page.locator("#scan-name")
        expect(name_field.is_visible(),
               "das Namensfeld des offenen Scans ist nicht sichtbar")
        expect(name_field.is_enabled(),
               "das Namensfeld des offenen Scans ist nicht bearbeitbar")
        expect(name_field.input_value() == "Inventar",
               "das Namensfeld zeigt nicht den Namen des offenen Scans")
        source_layout = f.page.eval_on_selector(".scan-source-state", """e => {
          const info = e.querySelector('.scan-source-info').getBoundingClientRect();
          const knopf = e.querySelector('#scan-fullscreen').getBoundingClientRect();
          const breite = e.getBoundingClientRect().width;
          return {info: info.width, knopf: knopf.width, breite};
        }""")
        expect(source_layout["info"] >= source_layout["breite"] - 1,
               f"der Quellenstand nutzt nicht die volle Breite: {source_layout}")
        expect(source_layout["knopf"] >= source_layout["breite"] - 1,
               f"der Vollbild-Knopf quetscht den Quellenstand ein: {source_layout}")

        # Die Suchregion darf mit der zweiten Ecke aus dem Bild heraus in die
        # mittlere Buehne gezogen werden. Gespeichert wird der Bildrand, denn
        # nur innerhalb davon gibt es Pixel fuer die Erkennung.
        f.click('[data-scan-step="2"]')
        f.click("#scan-slots-find")
        image_edge = f.page.locator("#scan-overlay").bounding_box()
        stage_edge = f.page.locator("#scan-stage").bounding_box()
        x_outside = image_edge["x"] + image_edge["width"] + 5
        expect(x_outside < stage_edge["x"] + stage_edge["width"],
               "der Rauchtest braucht freien Platz rechts neben dem Bild")
        f.page.mouse.click(image_edge["x"] + image_edge["width"] * .2,
                            image_edge["y"] + image_edge["height"] * .2)
        f.settle()
        f.page.mouse.click(x_outside,
                            image_edge["y"] + image_edge["height"] * .8)
        f.settle()
        right_image_edge = (b._photo_info["left"]
                            + round(b._photo_info["width"] / b._photo_info["scale"]))
        expect(b._search_area is not None
               and b._search_area[2] == right_image_edge,
               f"Ecke ausserhalb rastet nicht am Bildrand ein: {b._search_area}")
        f.page.keyboard.press("Escape")
        f.settle()
        expect(f.text("#scan-sequence").strip() == "Rauch",
               "Zielsequenz der Scan-Aufnahme ist nicht sichtbar")
        cards_list = f.count("#scan-insp .scan-card")
        expect(cards_list == count, f"{count} Item-Masken erwartet, da: {cards_list}")
        expect(f.count("#scan-insp .category-chooser") == count,
               "jede Maske braucht ein Kategorie-Bedienelement")
        f.image("items_masken")

        # Ohne vorhandene Kategorien ist es ein Textfeld - es gibt nichts zu waehlen.
        type_value = f.page.eval_on_selector("#scan-insp .category-chooser > *", "e => e.tagName")
        expect(type_value == "INPUT", f"ohne Kategorien erwartet INPUT, da: {type_value}")

        # Eine neue Kategorie anlegen ...
        f.page.fill("#scan-insp .category-chooser input", "Helme")
        f.page.eval_on_selector(
            "#scan-insp .category-chooser input",
            "e => e.dispatchEvent(new Event('change', {bubbles: true}))")
        f.settle()
        type_value = f.page.eval_on_selector("#scan-insp .category-chooser > *", "e => e.tagName")
        expect(type_value == "SELECT", f"nach dem Anlegen erwartet SELECT, da: {type_value}")

        # ... und sie muss beim NAECHSTEN Item waehlbar sein. Genau dafuer gibt es
        # `refreshCategoryOptions()`; ohne das tippt man sie zwanzigmal.
        options = f.page.eval_on_selector_all(
            "#scan-insp .category-chooser select option", "ns => ns.map(n => n.textContent)")
        expect("Helme" in options, f"'Helme' fehlt in der Auswahl: {options[:6]}")
        f.image("items_kategorie")

        # Der Tipp-Modus muss einen Neuaufbau ueberleben: der Entwurf speichert
        # 900 ms nach der letzten Aenderung, und das Feld wuerde sonst mitten im
        # Wort wieder zur Auswahlliste.
        f.page.eval_on_selector_all("#scan-insp .category-chooser select", """ns => {
          const s = ns[1];
          s.value = s.options[s.options.length - 1].value;
          s.dispatchEvent(new Event('change', {bubbles: true}));
        }""")
        f.settle()
        types = f.page.eval_on_selector_all(
            "#scan-insp .category-chooser", "ns => ns.map(n => n.firstElementChild.tagName)")
        expect(types[1] == "INPUT", f"'neue Kategorie' oeffnet kein Textfeld: {types[:3]}")
        # **Der Neuaufbau, den es zu ueberleben gilt, IST das Auto-Speichern** —
        # also wird auf den gewartet und nicht auf 1100 ms. Der Unterschied ist
        # hier nicht bloss Stabilitaet: laeuft die Wartezeit ab, bevor der
        # Neuaufbau kommt, vergleicht die Zusicherung darunter zweimal denselben
        # unberuehrten Zustand — und ist gruen, ohne etwas geprueft zu haben.
        # 200 ms Zugabe, weil `SC.dirty` schon vor dem `renderScans()` faellt.
        try:
            f.page.wait_for_function("() => !SC.dirty", timeout=15000)
        except Exception:
            pass                                # die Zusicherung meldet es genauer
        f.settle()
        types_after = f.page.eval_on_selector_all(
            "#scan-insp .category-chooser", "ns => ns.map(n => n.firstElementChild.tagName)")
        expect(types_after == types,
               f"der Tipp-Modus ueberlebt den Neuaufbau nicht: {types} -> {types_after}")

        # ------------------------------------------------------------------
        # **Kein Feld eines Items laesst die Zeile springen — und der Fokus
        # bleibt in seiner Maske.**
        #
        # Gemeldet wurde es beim TAB: man tippt einen Namen, springt weiter, und
        # die Zeile ist woanders. Zwei Ursachen lagen dahinter, beide nur im
        # Fenster messbar: die gemerkte Reihenfolge haengt am NAMEN (ein
        # umbenanntes Item galt als neu und rutschte ans Ende), und
        # `scanFetchPreviews()` baut die rechte Spalte an `renderScans()`
        # vorbei neu — beim Umbenennen fehlt die Vorschau unter dem neuen Namen,
        # sie wird nachgeholt, und dieser Aufbau rettete den Fokus nicht.
        f.click_text("#scan-insp .tabs .tab", "Items")
        f.settle()
        before = f.page.eval_on_selector_all(
            "#scan-insp .scan-card", "ns => ns.map(n => n.id)")
        expect(all(n.startswith("card:item:") for n in before),
               f"jede Item-Maske braucht ihre id: {before[:3]}")
        target_id = before[0] or "(ohne id)"

        # 1. Umbenennen: echtes Tippen, echtes TAB.
        #
        # **Dabei darf das Vorschaubild nicht verschwinden.** Der
        # Zwischenspeicher haengt am ITEM-Namen, das Bild an der Template-DATEI
        # — und die heisst nach dem Umbenennen genauso. Ohne
        # `scanPreviewRename()` galt die Vorschau als fehlend: die Maske
        # wurde einmal OHNE Bild gezeichnet, dieselben Bytes noch einmal aus
        # Python geholt und die Spalte ein zweites Mal aufgebaut. Sichtbar war
        # das als kurzes Flackern. Gemessen wird beides — die Zahl der
        # Neuaufbauten und ob das Bild durchgehend dasteht.
        name_field = f'[id="{target_id}"] .scan-card-fields > input'
        had_image = f.page.eval_on_selector(
            f'[id="{target_id}"]', "e => !!e.querySelector('img.mini')")
        expect(had_image, "das Item hat vor dem Umbenennen keine Vorschau")
        # Jeden Neuaufbau der rechten Spalte mitzaehlen.
        f.page.evaluate("""() => {
          window.__aufbauten = 0;
          const ziel = document.getElementById('scan-insp');
          window.__beob = new MutationObserver(() => { window.__aufbauten++; });
          window.__beob.observe(ziel, {childList: true});
        }""")
        f.page.click(name_field)
        f.page.fill(name_field, "Zeta")
        f.page.keyboard.press("Tab")
        f.page.wait_for_timeout(900)
        aufbauten = f.page.evaluate("() => { window.__beob.disconnect();"
                                     " return window.__aufbauten; }")
        expect(aufbauten <= 1,
               f"das Umbenennen baut die Spalte {aufbauten}x neu auf (Flackern)")
        expect(f.page.eval_on_selector(
                   '[id="card:item:Zeta"]',
                   "e => !!e.querySelector('img.mini')"),
               "die Vorschau ist nach dem Umbenennen weg")
        after = f.page.eval_on_selector_all(
            "#scan-insp .scan-card", "ns => ns.map(n => n.id)")
        expect(after[0] == "card:item:Zeta",
               f"das Umbenennen verschiebt die Zeile: {after}")
        expect(len(after) == len(before) and after[1:] == before[1:],
               f"die uebrigen Zeilen haben sich bewegt: {before} -> {after}")
        wo = f.page.evaluate("""() => {
          const a = document.activeElement;
          const m = a && a.closest ? a.closest('.scan-card') : null;
          return m ? m.id : (a ? a.tagName : "nichts");
        }""")
        expect(wo == "card:item:Zeta",
               f"der Fokus verlaesst die Maske: erwartet Zeta, da: {wo}")

        # 2. Kategorie: sie war der erste Sortierschluessel und damit das letzte
        #    Feld, das die Zeile noch wegspringen liess.
        f.page.eval_on_selector_all(".scan-card .category-chooser select", """(ns, id) => {
          const e = ns.find((n) => n.closest(".scan-card").id === id) || ns[0];
          e.focus();
          e.value = "Helme";
          e.dispatchEvent(new Event('change', {bubbles: true}));
        }""", "card:item:Zeta")
        f.page.wait_for_timeout(900)
        after_cat = f.page.eval_on_selector_all(
            "#scan-insp .scan-card", "ns => ns.map(n => n.id)")
        expect(after_cat == after,
               f"die Kategorie verschiebt die Zeile: {after} -> {after_cat}")
        # Sie steht dann unter der ALTEN Ueberschrift — das muss dastehen,
        # sonst liest sich die Liste falsch.
        stamp = f.page.eval_on_selector(
            '[id="card:item:Zeta"] .scan-card-state', "e => e.textContent")
        expect("→ Helme" in stamp,
               f"die gewechselte Kategorie wird nicht angesagt: {stamp!r}")

        # ------------------------------------------------------------------
        # **Beim Tippen springt nichts, auf Knopfdruck schon.** Sortierte sich
        # die Liste nach jeder Aenderung neu, rutscht genau die Zeile weg, an
        # der man gerade arbeitet — man tippt eine 2 und tippt danach im
        # naechsten Item weiter.
        f.click_text("#scan-insp .tabs .tab", "Items")
        before_prio = f.page.eval_on_selector_all(
            "#scan-insp .scan-card", "ns => ns.map(n => n.id)")
        # Das ERSTE Item auf einen hohen Rang setzen: sortiert die Liste
        # sofort, stuende es danach am Ende seiner Gruppe. Genau daran misst
        # sich, ob die Reihenfolge stehen bleibt.
        first = before_prio[0]
        f.page.eval_on_selector_all('.scan-card input[type="number"]', """(ns, id) => {
          const e = ns.find((n) => n.closest(".scan-card").id === id) || ns[0];
          e.focus();
          e.value = "9";
          e.dispatchEvent(new Event('change', {bubbles: true}));
        }""", first)
        f.settle()
        after_prio = f.page.eval_on_selector_all(
            "#scan-insp .scan-card", "ns => ns.map(n => n.id)")
        expect(after_prio == before_prio,
               f"die Liste sortiert beim Tippen um: {before_prio} -> {after_prio}")
        # Gegenprobe zur Gegenprobe: der Knopf muss sie sehr wohl umsortieren,
        # sonst misst der Test oben nur eine Liste, die sich ohnehin nicht regt.
        f.click_text("#scan-insp .scan-header button", "↕ Sortieren")
        sortiert = f.page.eval_on_selector_all(
            "#scan-insp .scan-card", "ns => ns.map(n => n.id)")
        expect(sortiert != before_prio,
               f"„Sortieren“ ordnet die Liste nicht um: {sortiert}")

        buttons = f.page.eval_on_selector_all(
            "#scan-insp .scan-header button", "ns => ns.map(n => n.textContent)")
        expect(any("Sortieren" in k for k in buttons),
               f"kein Sortier-Knopf im Kopf: {buttons}")
        # Und der Kopf bleibt beim Scrollen stehen — sonst ist die Reiterleiste
        # nach drei Umdrehungen weg.
        sticky = f.page.eval_on_selector(
            "#scan-insp .scan-header", "e => getComputedStyle(e).position")
        expect(sticky == "sticky", f"der Kopf klebt nicht: {sticky}")

        # ------------------------------------------------------------------
        # **Alle drei Listen stehen rechts und sind Masken.** Das ist die
        # Schicht, die die Vertragssuite nicht sehen kann: dass ein Reiter
        # ueberhaupt etwas zeichnet, faellt nur im Fenster auf.
        left_before = f.page.eval_on_selector(
            "#view-scans .page.left", "e => e.getBoundingClientRect().height")
        for tab, kind in (("Slots", "slot"), ("Scans", "scan"), ("Items", "item")):
            f.click_text("#scan-insp .tabs .tab", tab)
            cards_list = f.count("#scan-insp .scan-card")
            expect(cards_list > 0, f"Reiter „{tab}“ zeichnet keine Maske")
            own_ones = f.count(f'#scan-insp .scan-card[id^="card:{kind}:"]')
            expect(own_ones == cards_list,
                   f"„{tab}“: {cards_list} Masken, davon {own_ones} mit {kind}-id")
            expect(f.count("#ab-listen .scan-card") == 0,
                   f"„{tab}“: es steht noch eine Maske in der linken Spalte")
            left = f.page.eval_on_selector(
                "#view-scans .page.left", "e => e.getBoundingClientRect().height")
            expect(left == left_before,
                   f"die linke Spalte aendert bei „{tab}“ ihre Hoehe: "
                   f"{left_before} -> {left}")
            f.image("items_reiter_" + tab.lower())
            if kind == "slot":
                # Die Kachel zeigt die stabile ID, nicht die Stelle im Scan —
                # in dieser Sitzung fallen beide zusammen (Anlegen == Reihenfolge
                # im Scan), aber die ID darf sich nicht aendern, wenn ein Slot
                # ab- und wieder angeschaltet wird (siehe Vertragssuite dafuer).
                ids = f.page.eval_on_selector_all(
                    "#scan-insp .scan-badge .num",
                    "ns => ns.map(n => n.textContent)")
                expect(ids == ["#" + str(i + 1) for i in range(cards_list)],
                       f"Slot-IDs nicht wie erwartet: {ids}")
                # Nummer und Groesse stehen auf EINER Hoehe — die eine unten in
                # der ersten Spalte, die andere in der Zustandszeile der
                # dritten. Ohne `align-self:stretch` laegen sie auseinander.
                edges = f.page.evaluate("""() => {
                  const m = document.querySelector("#scan-insp .scan-card");
                  const n = m.querySelector(".scan-badge .num");
                  const g = m.querySelector(".scan-card-state .num");
                  return [Math.round(n.getBoundingClientRect().bottom),
                          Math.round(g.getBoundingClientRect().bottom)];
                }""")
                expect(abs(edges[0] - edges[1]) <= 1,
                       f"Nummer und Größe stehen nicht auf einer Höhe: {edges}")

        # **Ein Scan war nicht mehr zu loeschen**: der Klick auf ihn oeffnete
        # ihn, das Oeffnen schaltete auf die Item-Liste um, und der Knopf stand
        # in der Spalte, die man damit gerade verlassen hatte.
        f.click_text("#scan-insp .tabs .tab", "Scans")
        f.click('#scan-insp .scan-card[id="card:scan:Inventar"] input')
        f.settle()
        f.click('#scan-insp .scan-card[id="card:scan:Inventar"] .scan-card-state')
        tab_after = f.text("#scan-insp .tabs .tab.on")
        expect(tab_after.startswith("Scans"),
               f"nach dem Oeffnen steht der Reiter auf „{tab_after}“")
        buttons = f.page.eval_on_selector_all(
            "#scan-insp .scan-card-detail button", "ns => ns.map(n => n.textContent)")
        expect(any("löschen" in k for k in buttons),
               f"kein Loesch-Knopf im Detailteil des Scans: {buttons}")
        f.image("items_scan_detail")

        # **Der Bestaetigungsklick** war die einzige Item-Eigenschaft ohne
        # Bedienelement — im Modell und in den Konsolen-Editoren gibt es sie
        # seit jeher.
        f.click_text("#scan-insp .tabs .tab", "Items")
        f.click("#scan-insp .scan-card .scan-card-fields input")
        f.settle()
        captions = f.page.eval_on_selector_all(
            "#scan-insp .scan-card-detail .heading",
            "ns => ns.map(n => n.textContent)")
        expect(any("BESTÄTIGUNGSKLICK" in b for b in captions),
               f"kein Bestaetigungsklick in der Item-Maske: {captions}")

        # **Ein Buchstabe ist erst ohne Modifikator ein Werkzeug.** Geprueft
        # wurde nur der Buchstabe: STRG+F (Reflex „suchen") schaltete damit auf
        # „Hintergrundfarbe", STRG+B auf „Bereich". Sichtbar passiert nichts —
        # aber der naechste Klick im Bild misst dann eine Farbe, statt
        # auszuwaehlen.
        #
        # Der Fokus muss dafuer AUS dem Textfeld heraus: in einem Eingabefeld
        # kehrt `keyboard()` schon vorher um, und der Test waere gruen, ohne je
        # die Stelle erreicht zu haben, um die es geht.
        f.page.evaluate("document.activeElement && document.activeElement.blur()")
        for key, name in (("f", "STRG+F"), ("b", "STRG+B"), ("s", "STRG+S")):
            f.page.evaluate("callScan('scan_mode_set', {mode:'choice', kind:'item'})")
            f.settle()
            f.page.keyboard.press(f"Control+{key}")
            f.settle()
            mode = f.page.evaluate("SC.mode")
            expect(mode == "choice", f"{name} wechselt den Modus auf '{mode}'")
        # Ohne Modifikator muss der Buchstabe weiterhin greifen — sonst hat der
        # Riegel das Werkzeug gleich mit abgeschaltet. Erst aus dem Textfeld
        # heraus: in einem Eingabefeld ist „F“ ein Buchstabe und kein Werkzeug.
        f.page.evaluate("document.activeElement && document.activeElement.blur()")
        f.page.keyboard.press("f")
        f.settle()
        expect(f.page.evaluate("SC.mode") == "measure",
               "„F“ allein schaltet nicht mehr auf „Hintergrundfarbe“")
        f.page.evaluate("callScan('scan_mode_set', {mode:'choice', kind:'item'})")
        f.settle()

        # **Was getippt und noch nicht gemeldet ist, ueberlebt das
        # Auto-Speichern.** Es ist der einzige Neuaufbau, der an der Uhr haengt
        # statt am Nutzer (900 ms nach der letzten Aenderung) — er trifft also
        # als einziger ein Feld, in dem gerade getippt wird. Dass nichts
        # verlorengeht, liegt am Browser: ein fokussiertes, geaendertes `input`
        # feuert sein `change`, bevor es aus dem Dokument fliegt. Das steht hier
        # als Zusicherung, nicht als Beiwerk — faellt es weg, verschluckt das
        # Fenster Tastendruecke, und man sucht den Fehler in der Bruecke.
        f.click_text("#scan-insp .tabs .tab", "Items")
        f.settle()
        # Das Namensfeld traegt kein `type` (s. `cardName`) — ein Selektor auf
        # `[type=text]` findet es deshalb nicht.
        fields = "#scan-insp .scan-card .scan-card-fields > input:not([type])"
        names = f.page.locator(fields)
        if names.count() >= 2:
            names.nth(0).fill("Zuerst")
            names.nth(0).press("Tab")          # meldet und plant das Speichern
            f.page.wait_for_timeout(120)
            f.page.locator(fields).nth(1).click()
            f.page.locator(fields).nth(1).type("Getippt", delay=20)
            typed = f.page.locator(fields).nth(1).input_value()
            # **Gewartet wird auf den Zustand, nicht auf die Uhr.** Hier stand
            # eine feste Wartezeit von 1800 ms mit dem Kommentar „laenger als
            # die 900 ms" — nur liegen hier ZWEI Runden hintereinander: das
            # Auto-Speichern ist entprellt (`clearTimeout` in
            # `scanScheduleAutosave`), sein Neuaufbau stoesst das
            # fokussierte Feld an, und dessen `change` plant die naechsten
            # 900 ms. Die Rechnung ging also auf ~300 ms Luft aus, und die
            # frisst ein ausgelasteter CI-Laeufer zwischen Bruecke und
            # Neuzeichnen auf: gruen auf dem Entwicklungsrechner, rot in CI.
            #
            # Gefragt wird deshalb nach beiden Tatsachen zugleich (der Name ist
            # in den Daten UND nichts ist mehr offen) — kommt einer nicht,
            # sagen die Zusicherungen darunter weiterhin, welcher.
            try:
                f.page.wait_for_function(
                    "n => (SC.items || []).some(i => i.name === n) && !SC.dirty",
                    arg=typed, timeout=15000)
            except Exception:
                pass                            # die Zusicherung meldet es genauer
            expect(typed in (f.page.evaluate("SC.items.map(i => i.name)") or []),
                   f"das Getippte ({typed!r}) kam nicht in den Daten an: "
                   f"{f.page.evaluate('SC.items.map(i => i.name)')}")
            expect(not f.page.evaluate("SC.dirty"),
                   "der Entwurf wurde nicht von selbst gespeichert")
        else:
            error.append("keine zwei Item-Namensfelder fuer die Tipp-Probe")

        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Items", run)
