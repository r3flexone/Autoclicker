"""Rauchtest Item-Masken: erkennen, Kategorie wählen und neu anlegen."""

from pathlib import Path

from ._bild import inventar, stelle_bildschirm
from ._bruecke import Fenster, main, sandkasten


def aufbau():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import Sequence

    sandkasten("rauch_items_")
    image, corners = inventar()
    stelle_bildschirm(image)

    b = StudioBridge(Sequence(name="Rauch"),
                     Path("sequences/rauch/sequence.json"), "sequences")
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
    b, count = aufbau()
    error = []

    def pruefe(condition, text):
        if not condition:
            error.append(text)

    pruefe(len(b.items) == count, f"{count} Items erwartet, gelernt: {sorted(b.items)}")

    with Fenster(b) as f:
        f.reiter("scans")
        namensfeld = f.seite.locator("#scan-name")
        pruefe(namensfeld.is_visible(),
               "das Namensfeld des offenen Scans ist nicht sichtbar")
        pruefe(namensfeld.is_enabled(),
               "das Namensfeld des offenen Scans ist nicht bearbeitbar")
        pruefe(namensfeld.input_value() == "Inventar",
               "das Namensfeld zeigt nicht den Namen des offenen Scans")
        quellenlayout = f.seite.eval_on_selector(".scan-source-state", """e => {
          const info = e.querySelector('.scan-source-info').getBoundingClientRect();
          const knopf = e.querySelector('#scan-fullscreen').getBoundingClientRect();
          const breite = e.getBoundingClientRect().width;
          return {info: info.width, knopf: knopf.width, breite};
        }""")
        pruefe(quellenlayout["info"] >= quellenlayout["breite"] - 1,
               f"der Quellenstand nutzt nicht die volle Breite: {quellenlayout}")
        pruefe(quellenlayout["knopf"] >= quellenlayout["breite"] - 1,
               f"der Vollbild-Knopf quetscht den Quellenstand ein: {quellenlayout}")

        # Die Suchregion darf mit der zweiten Ecke aus dem Bild heraus in die
        # mittlere Buehne gezogen werden. Gespeichert wird der Bildrand, denn
        # nur innerhalb davon gibt es Pixel fuer die Erkennung.
        f.click_value('[data-scan-schritt="2"]')
        f.click_value("#scan-slots-find")
        bildrand = f.seite.locator("#scan-overlay").bounding_box()
        buehnenrand = f.seite.locator("#scan-stage").bounding_box()
        x_draussen = bildrand["x"] + bildrand["width"] + 5
        pruefe(x_draussen < buehnenrand["x"] + buehnenrand["width"],
               "der Rauchtest braucht freien Platz rechts neben dem Bild")
        f.seite.mouse.click(bildrand["x"] + bildrand["width"] * .2,
                            bildrand["y"] + bildrand["height"] * .2)
        f.ruhe()
        f.seite.mouse.click(x_draussen,
                            bildrand["y"] + bildrand["height"] * .8)
        f.ruhe()
        rechter_bildrand = (b._photo_info["left"]
                            + round(b._photo_info["width"] / b._photo_info["scale"]))
        pruefe(b._search_area is not None
               and b._search_area[2] == rechter_bildrand,
               f"Ecke ausserhalb rastet nicht am Bildrand ein: {b._search_area}")
        f.seite.keyboard.press("Escape")
        f.ruhe()
        pruefe(f.text("#scan-sequence").strip() == "Rauch",
               "Zielsequenz der Scan-Aufnahme ist nicht sichtbar")
        masken = f.count("#scan-insp .scan-card")
        pruefe(masken == count, f"{count} Item-Masken erwartet, da: {masken}")
        pruefe(f.count("#scan-insp .category-chooser") == count,
               "jede Maske braucht ein Kategorie-Bedienelement")
        f.image("items_masken")

        # Ohne vorhandene Kategorien ist es ein Textfeld - es gibt nichts zu waehlen.
        type_value = f.seite.eval_on_selector("#scan-insp .category-chooser > *", "e => e.tagName")
        pruefe(type_value == "INPUT", f"ohne Kategorien erwartet INPUT, da: {type_value}")

        # Eine neue Kategorie anlegen ...
        f.seite.fill("#scan-insp .category-chooser input", "Helme")
        f.seite.eval_on_selector(
            "#scan-insp .category-chooser input",
            "e => e.dispatchEvent(new Event('change', {bubbles: true}))")
        f.ruhe()
        type_value = f.seite.eval_on_selector("#scan-insp .category-chooser > *", "e => e.tagName")
        pruefe(type_value == "SELECT", f"nach dem Anlegen erwartet SELECT, da: {type_value}")

        # ... und sie muss beim NAECHSTEN Item waehlbar sein. Genau dafuer gibt es
        # `refreshCategoryOptions()`; ohne das tippt man sie zwanzigmal.
        options = f.seite.eval_on_selector_all(
            "#scan-insp .category-chooser select option", "ns => ns.map(n => n.textContent)")
        pruefe("Helme" in options, f"'Helme' fehlt in der Auswahl: {options[:6]}")
        f.image("items_kategorie")

        # Der Tipp-Modus muss einen Neuaufbau ueberleben: der Entwurf speichert
        # 900 ms nach der letzten Aenderung, und das Feld wuerde sonst mitten im
        # Wort wieder zur Auswahlliste.
        f.seite.eval_on_selector_all("#scan-insp .category-chooser select", """ns => {
          const s = ns[1];
          s.value = s.options[s.options.length - 1].value;
          s.dispatchEvent(new Event('change', {bubbles: true}));
        }""")
        f.ruhe()
        types = f.seite.eval_on_selector_all(
            "#scan-insp .category-chooser", "ns => ns.map(n => n.firstElementChild.tagName)")
        pruefe(types[1] == "INPUT", f"'neue Kategorie' oeffnet kein Textfeld: {types[:3]}")
        # **Der Neuaufbau, den es zu ueberleben gilt, IST das Auto-Speichern** —
        # also wird auf den gewartet und nicht auf 1100 ms. Der Unterschied ist
        # hier nicht bloss Stabilitaet: laeuft die Wartezeit ab, bevor der
        # Neuaufbau kommt, vergleicht die Zusicherung darunter zweimal denselben
        # unberuehrten Zustand — und ist gruen, ohne etwas geprueft zu haben.
        # 200 ms Zugabe, weil `SC.dirty` schon vor dem `renderScans()` faellt.
        try:
            f.seite.wait_for_function("() => !SC.dirty", timeout=15000)
        except Exception:
            pass                                # die Zusicherung meldet es genauer
        f.ruhe()
        typen_danach = f.seite.eval_on_selector_all(
            "#scan-insp .category-chooser", "ns => ns.map(n => n.firstElementChild.tagName)")
        pruefe(typen_danach == types,
               f"der Tipp-Modus ueberlebt den Neuaufbau nicht: {types} -> {typen_danach}")

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
        f.klick_text("#scan-insp .tabs .tab", "Items")
        f.ruhe()
        before = f.seite.eval_on_selector_all(
            "#scan-insp .scan-card", "ns => ns.map(n => n.id)")
        pruefe(all(n.startswith("maske:item:") for n in before),
               f"jede Item-Maske braucht ihre id: {before[:3]}")
        ziel_id = before[0] or "(ohne id)"

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
        namensfeld = f'[id="{ziel_id}"] .scan-card-fields > input'
        hatte_bild = f.seite.eval_on_selector(
            f'[id="{ziel_id}"]', "e => !!e.querySelector('img.mini')")
        pruefe(hatte_bild, "das Item hat vor dem Umbenennen keine Vorschau")
        # Jeden Neuaufbau der rechten Spalte mitzaehlen.
        f.seite.evaluate("""() => {
          window.__aufbauten = 0;
          const ziel = document.getElementById('scan-insp');
          window.__beob = new MutationObserver(() => { window.__aufbauten++; });
          window.__beob.observe(ziel, {childList: true});
        }""")
        f.seite.click(namensfeld)
        f.seite.fill(namensfeld, "Zeta")
        f.seite.keyboard.press("Tab")
        f.seite.wait_for_timeout(900)
        aufbauten = f.seite.evaluate("() => { window.__beob.disconnect();"
                                     " return window.__aufbauten; }")
        pruefe(aufbauten <= 1,
               f"das Umbenennen baut die Spalte {aufbauten}x neu auf (Flackern)")
        pruefe(f.seite.eval_on_selector(
                   '[id="maske:item:Zeta"]',
                   "e => !!e.querySelector('img.mini')"),
               "die Vorschau ist nach dem Umbenennen weg")
        nach = f.seite.eval_on_selector_all(
            "#scan-insp .scan-card", "ns => ns.map(n => n.id)")
        pruefe(nach[0] == "maske:item:Zeta",
               f"das Umbenennen verschiebt die Zeile: {nach}")
        pruefe(len(nach) == len(before) and nach[1:] == before[1:],
               f"die uebrigen Zeilen haben sich bewegt: {before} -> {nach}")
        wo = f.seite.evaluate("""() => {
          const a = document.activeElement;
          const m = a && a.closest ? a.closest('.scan-card') : null;
          return m ? m.id : (a ? a.tagName : "nichts");
        }""")
        pruefe(wo == "maske:item:Zeta",
               f"der Fokus verlaesst die Maske: erwartet Zeta, da: {wo}")

        # 2. Kategorie: sie war der erste Sortierschluessel und damit das letzte
        #    Feld, das die Zeile noch wegspringen liess.
        f.seite.eval_on_selector_all(".scan-card .category-chooser select", """(ns, id) => {
          const e = ns.find((n) => n.closest(".scan-card").id === id) || ns[0];
          e.focus();
          e.value = "Helme";
          e.dispatchEvent(new Event('change', {bubbles: true}));
        }""", "maske:item:Zeta")
        f.seite.wait_for_timeout(900)
        nach_kat = f.seite.eval_on_selector_all(
            "#scan-insp .scan-card", "ns => ns.map(n => n.id)")
        pruefe(nach_kat == nach,
               f"die Kategorie verschiebt die Zeile: {nach} -> {nach_kat}")
        # Sie steht dann unter der ALTEN Ueberschrift — das muss dastehen,
        # sonst liest sich die Liste falsch.
        stamp = f.seite.eval_on_selector(
            '[id="maske:item:Zeta"] .scan-card-state', "e => e.textContent")
        pruefe("→ Helme" in stamp,
               f"die gewechselte Kategorie wird nicht angesagt: {stamp!r}")

        # ------------------------------------------------------------------
        # **Beim Tippen springt nichts, auf Knopfdruck schon.** Sortierte sich
        # die Liste nach jeder Aenderung neu, rutscht genau die Zeile weg, an
        # der man gerade arbeitet — man tippt eine 2 und tippt danach im
        # naechsten Item weiter.
        f.klick_text("#scan-insp .tabs .tab", "Items")
        vor_prio = f.seite.eval_on_selector_all(
            "#scan-insp .scan-card", "ns => ns.map(n => n.id)")
        # Das ERSTE Item auf einen hohen Rang setzen: sortiert die Liste
        # sofort, stuende es danach am Ende seiner Gruppe. Genau daran misst
        # sich, ob die Reihenfolge stehen bleibt.
        first = vor_prio[0]
        f.seite.eval_on_selector_all('.scan-card input[type="number"]', """(ns, id) => {
          const e = ns.find((n) => n.closest(".scan-card").id === id) || ns[0];
          e.focus();
          e.value = "9";
          e.dispatchEvent(new Event('change', {bubbles: true}));
        }""", first)
        f.ruhe()
        nach_prio = f.seite.eval_on_selector_all(
            "#scan-insp .scan-card", "ns => ns.map(n => n.id)")
        pruefe(nach_prio == vor_prio,
               f"die Liste sortiert beim Tippen um: {vor_prio} -> {nach_prio}")
        # Gegenprobe zur Gegenprobe: der Knopf muss sie sehr wohl umsortieren,
        # sonst misst der Test oben nur eine Liste, die sich ohnehin nicht regt.
        f.klick_text("#scan-insp .scan-header button", "↕ Sortieren")
        sortiert = f.seite.eval_on_selector_all(
            "#scan-insp .scan-card", "ns => ns.map(n => n.id)")
        pruefe(sortiert != vor_prio,
               f"„Sortieren“ ordnet die Liste nicht um: {sortiert}")

        knoepfe = f.seite.eval_on_selector_all(
            "#scan-insp .scan-header button", "ns => ns.map(n => n.textContent)")
        pruefe(any("Sortieren" in k for k in knoepfe),
               f"kein Sortier-Knopf im Kopf: {knoepfe}")
        # Und der Kopf bleibt beim Scrollen stehen — sonst ist die Reiterleiste
        # nach drei Umdrehungen weg.
        klebt = f.seite.eval_on_selector(
            "#scan-insp .scan-header", "e => getComputedStyle(e).position")
        pruefe(klebt == "sticky", f"der Kopf klebt nicht: {klebt}")

        # ------------------------------------------------------------------
        # **Alle drei Listen stehen rechts und sind Masken.** Das ist die
        # Schicht, die die Vertragssuite nicht sehen kann: dass ein Reiter
        # ueberhaupt etwas zeichnet, faellt nur im Fenster auf.
        links_vorher = f.seite.eval_on_selector(
            "#view-scans .page.left", "e => e.getBoundingClientRect().height")
        for reiter, kind in (("Slots", "slot"), ("Scans", "scan"), ("Items", "item")):
            f.klick_text("#scan-insp .tabs .tab", reiter)
            masken = f.count("#scan-insp .scan-card")
            pruefe(masken > 0, f"Reiter „{reiter}“ zeichnet keine Maske")
            eigene = f.count(f'#scan-insp .scan-card[id^="maske:{kind}:"]')
            pruefe(eigene == masken,
                   f"„{reiter}“: {masken} Masken, davon {eigene} mit {kind}-id")
            pruefe(f.count("#ab-listen .scan-card") == 0,
                   f"„{reiter}“: es steht noch eine Maske in der linken Spalte")
            left = f.seite.eval_on_selector(
                "#view-scans .page.left", "e => e.getBoundingClientRect().height")
            pruefe(left == links_vorher,
                   f"die linke Spalte aendert bei „{reiter}“ ihre Hoehe: "
                   f"{links_vorher} -> {left}")
            f.image("items_reiter_" + reiter.lower())
            if kind == "slot":
                # Die Kachel zeigt die stabile ID, nicht die Stelle im Scan —
                # in dieser Sitzung fallen beide zusammen (Anlegen == Reihenfolge
                # im Scan), aber die ID darf sich nicht aendern, wenn ein Slot
                # ab- und wieder angeschaltet wird (siehe Vertragssuite dafuer).
                ids = f.seite.eval_on_selector_all(
                    "#scan-insp .scan-badge .num",
                    "ns => ns.map(n => n.textContent)")
                pruefe(ids == ["#" + str(i + 1) for i in range(masken)],
                       f"Slot-IDs nicht wie erwartet: {ids}")
                # Nummer und Groesse stehen auf EINER Hoehe — die eine unten in
                # der ersten Spalte, die andere in der Zustandszeile der
                # dritten. Ohne `align-self:stretch` laegen sie auseinander.
                kanten = f.seite.evaluate("""() => {
                  const m = document.querySelector("#scan-insp .scan-card");
                  const n = m.querySelector(".scan-badge .num");
                  const g = m.querySelector(".scan-card-state .num");
                  return [Math.round(n.getBoundingClientRect().bottom),
                          Math.round(g.getBoundingClientRect().bottom)];
                }""")
                pruefe(abs(kanten[0] - kanten[1]) <= 1,
                       f"Nummer und Größe stehen nicht auf einer Höhe: {kanten}")

        # **Ein Scan war nicht mehr zu loeschen**: der Klick auf ihn oeffnete
        # ihn, das Oeffnen schaltete auf die Item-Liste um, und der Knopf stand
        # in der Spalte, die man damit gerade verlassen hatte.
        f.klick_text("#scan-insp .tabs .tab", "Scans")
        f.click_value('#scan-insp .scan-card[id="maske:scan:Inventar"] input')
        f.ruhe()
        f.click_value('#scan-insp .scan-card[id="maske:scan:Inventar"] .scan-card-state')
        reiter_danach = f.text("#scan-insp .tabs .tab.on")
        pruefe(reiter_danach.startswith("Scans"),
               f"nach dem Oeffnen steht der Reiter auf „{reiter_danach}“")
        knoepfe = f.seite.eval_on_selector_all(
            "#scan-insp .scan-card-detail button", "ns => ns.map(n => n.textContent)")
        pruefe(any("löschen" in k for k in knoepfe),
               f"kein Loesch-Knopf im Detailteil des Scans: {knoepfe}")
        f.image("items_scan_detail")

        # **Der Bestaetigungsklick** war die einzige Item-Eigenschaft ohne
        # Bedienelement — im Modell und in den Konsolen-Editoren gibt es sie
        # seit jeher.
        f.klick_text("#scan-insp .tabs .tab", "Items")
        f.click_value("#scan-insp .scan-card .scan-card-fields input")
        f.ruhe()
        beschriftungen = f.seite.eval_on_selector_all(
            "#scan-insp .scan-card-detail .heading",
            "ns => ns.map(n => n.textContent)")
        pruefe(any("BESTÄTIGUNGSKLICK" in b for b in beschriftungen),
               f"kein Bestaetigungsklick in der Item-Maske: {beschriftungen}")

        # **Ein Buchstabe ist erst ohne Modifikator ein Werkzeug.** Geprueft
        # wurde nur der Buchstabe: STRG+F (Reflex „suchen") schaltete damit auf
        # „Hintergrundfarbe", STRG+B auf „Bereich". Sichtbar passiert nichts —
        # aber der naechste Klick im Bild misst dann eine Farbe, statt
        # auszuwaehlen.
        #
        # Der Fokus muss dafuer AUS dem Textfeld heraus: in einem Eingabefeld
        # kehrt `keyboard()` schon vorher um, und der Test waere gruen, ohne je
        # die Stelle erreicht zu haben, um die es geht.
        f.seite.evaluate("document.activeElement && document.activeElement.blur()")
        for key, name in (("f", "STRG+F"), ("b", "STRG+B"), ("s", "STRG+S")):
            f.seite.evaluate("callScan('scan_mode_set', {mode:'choice', kind:'item'})")
            f.ruhe()
            f.seite.keyboard.press(f"Control+{key}")
            f.ruhe()
            mode = f.seite.evaluate("SC.mode")
            pruefe(mode == "choice", f"{name} wechselt den Modus auf '{mode}'")
        # Ohne Modifikator muss der Buchstabe weiterhin greifen — sonst hat der
        # Riegel das Werkzeug gleich mit abgeschaltet. Erst aus dem Textfeld
        # heraus: in einem Eingabefeld ist „F“ ein Buchstabe und kein Werkzeug.
        f.seite.evaluate("document.activeElement && document.activeElement.blur()")
        f.seite.keyboard.press("f")
        f.ruhe()
        pruefe(f.seite.evaluate("SC.mode") == "measure",
               "„F“ allein schaltet nicht mehr auf „Hintergrundfarbe“")
        f.seite.evaluate("callScan('scan_mode_set', {mode:'choice', kind:'item'})")
        f.ruhe()

        # **Was getippt und noch nicht gemeldet ist, ueberlebt das
        # Auto-Speichern.** Es ist der einzige Neuaufbau, der an der Uhr haengt
        # statt am Nutzer (900 ms nach der letzten Aenderung) — er trifft also
        # als einziger ein Feld, in dem gerade getippt wird. Dass nichts
        # verlorengeht, liegt am Browser: ein fokussiertes, geaendertes `input`
        # feuert sein `change`, bevor es aus dem Dokument fliegt. Das steht hier
        # als Zusicherung, nicht als Beiwerk — faellt es weg, verschluckt das
        # Fenster Tastendruecke, und man sucht den Fehler in der Bruecke.
        f.klick_text("#scan-insp .tabs .tab", "Items")
        f.ruhe()
        # Das Namensfeld traegt kein `type` (s. `cardName`) — ein Selektor auf
        # `[type=text]` findet es deshalb nicht.
        fields = "#scan-insp .scan-card .scan-card-fields > input:not([type])"
        names = f.seite.locator(fields)
        if names.count() >= 2:
            names.nth(0).fill("Zuerst")
            names.nth(0).press("Tab")          # meldet und plant das Speichern
            f.seite.wait_for_timeout(120)
            f.seite.locator(fields).nth(1).click()
            f.seite.locator(fields).nth(1).type("Getippt", delay=20)
            getippt = f.seite.locator(fields).nth(1).input_value()
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
                f.seite.wait_for_function(
                    "n => (SC.items || []).some(i => i.name === n) && !SC.dirty",
                    arg=getippt, timeout=15000)
            except Exception:
                pass                            # die Zusicherung meldet es genauer
            pruefe(getippt in (f.seite.evaluate("SC.items.map(i => i.name)") or []),
                   f"das Getippte ({getippt!r}) kam nicht in den Daten an: "
                   f"{f.seite.evaluate('SC.items.map(i => i.name)')}")
            pruefe(not f.seite.evaluate("SC.dirty"),
                   "der Entwurf wurde nicht von selbst gespeichert")
        else:
            error.append("keine zwei Item-Namensfelder fuer die Tipp-Probe")

        error.extend(f.error)
    return error


if __name__ == "__main__":
    main("Items", run)
