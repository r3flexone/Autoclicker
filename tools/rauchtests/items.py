"""Rauchtest Item-Masken: erkennen, Kategorie wählen und neu anlegen."""

from pathlib import Path

from ._bild import inventar, stelle_bildschirm
from ._bruecke import Fenster, main, sandkasten


def aufbau():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import Sequence

    sandkasten("rauch_items_")
    bild, ecken = inventar()
    stelle_bildschirm(bild)

    b = StudioBridge(Sequence(name="Rauch"),
                     Path("sequences/rauch/sequence.json"), "sequences")
    b.scan_neu({"name": "Inventar"})
    b.scan_foto()
    for sx, sy in ecken:
        b.scan_modus_setzen({"modus": "slot"})
        b.scan_klick({"x": sx, "y": sy})
        b.scan_klick({"x": sx + 62, "y": sy + 60})
    b.scan_lernvorschau({"scope": "alle"})
    b.scan_lernvorschau_uebernehmen({})
    b.scan_erkennen()
    return b, len(ecken)


def lauf():
    b, anzahl = aufbau()
    fehler = []

    def pruefe(bedingung, text):
        if not bedingung:
            fehler.append(text)

    pruefe(len(b.items) == anzahl, f"{anzahl} Items erwartet, gelernt: {sorted(b.items)}")

    with Fenster(b) as f:
        f.reiter("scans")
        namensfeld = f.seite.locator("#scan-name")
        pruefe(namensfeld.is_visible(),
               "das Namensfeld des offenen Scans ist nicht sichtbar")
        pruefe(namensfeld.is_enabled(),
               "das Namensfeld des offenen Scans ist nicht bearbeitbar")
        pruefe(namensfeld.input_value() == "Inventar",
               "das Namensfeld zeigt nicht den Namen des offenen Scans")
        quellenlayout = f.seite.eval_on_selector(".scan-quellenstand", """e => {
          const info = e.querySelector('.scan-quelleninfo').getBoundingClientRect();
          const knopf = e.querySelector('#scan-vollbild').getBoundingClientRect();
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
        f.klick('[data-scan-schritt="2"]')
        f.klick("#scan-slots-finden")
        bildrand = f.seite.locator("#scan-overlay").bounding_box()
        buehnenrand = f.seite.locator("#scan-buehne").bounding_box()
        x_draussen = bildrand["x"] + bildrand["width"] + 5
        pruefe(x_draussen < buehnenrand["x"] + buehnenrand["width"],
               "der Rauchtest braucht freien Platz rechts neben dem Bild")
        f.seite.mouse.click(bildrand["x"] + bildrand["width"] * .2,
                            bildrand["y"] + bildrand["height"] * .2)
        f.seite.wait_for_timeout(400)
        f.seite.mouse.click(x_draussen,
                            bildrand["y"] + bildrand["height"] * .8)
        f.seite.wait_for_timeout(700)
        rechter_bildrand = (b._foto_info["links"]
                            + round(b._foto_info["breite"] / b._foto_info["skala"]))
        pruefe(b._suchbereich is not None
               and b._suchbereich[2] == rechter_bildrand,
               f"Ecke ausserhalb rastet nicht am Bildrand ein: {b._suchbereich}")
        f.seite.keyboard.press("Escape")
        f.seite.wait_for_timeout(400)
        pruefe(f.text("#scan-sequenz").strip() == "Rauch",
               "Zielsequenz der Scan-Aufnahme ist nicht sichtbar")
        masken = f.anzahl("#scan-insp .scan-maske")
        pruefe(masken == anzahl, f"{anzahl} Item-Masken erwartet, da: {masken}")
        pruefe(f.anzahl("#scan-insp .kategorie-wahl") == anzahl,
               "jede Maske braucht ein Kategorie-Bedienelement")
        f.bild("items_masken")

        # Ohne vorhandene Kategorien ist es ein Textfeld - es gibt nichts zu waehlen.
        typ = f.seite.eval_on_selector("#scan-insp .kategorie-wahl > *", "e => e.tagName")
        pruefe(typ == "INPUT", f"ohne Kategorien erwartet INPUT, da: {typ}")

        # Eine neue Kategorie anlegen ...
        f.seite.fill("#scan-insp .kategorie-wahl input", "Helme")
        f.seite.eval_on_selector(
            "#scan-insp .kategorie-wahl input",
            "e => e.dispatchEvent(new Event('change', {bubbles: true}))")
        f.seite.wait_for_timeout(700)
        typ = f.seite.eval_on_selector("#scan-insp .kategorie-wahl > *", "e => e.tagName")
        pruefe(typ == "SELECT", f"nach dem Anlegen erwartet SELECT, da: {typ}")

        # ... und sie muss beim NAECHSTEN Item waehlbar sein. Genau dafuer gibt es
        # `kategorieOptionenAktualisieren()`; ohne das tippt man sie zwanzigmal.
        optionen = f.seite.eval_on_selector_all(
            "#scan-insp .kategorie-wahl select option", "ns => ns.map(n => n.textContent)")
        pruefe("Helme" in optionen, f"'Helme' fehlt in der Auswahl: {optionen[:6]}")
        f.bild("items_kategorie")

        # Der Tipp-Modus muss einen Neuaufbau ueberleben: der Entwurf speichert
        # 900 ms nach der letzten Aenderung, und das Feld wuerde sonst mitten im
        # Wort wieder zur Auswahlliste.
        f.seite.eval_on_selector_all("#scan-insp .kategorie-wahl select", """ns => {
          const s = ns[1];
          s.value = s.options[s.options.length - 1].value;
          s.dispatchEvent(new Event('change', {bubbles: true}));
        }""")
        f.seite.wait_for_timeout(400)
        typen = f.seite.eval_on_selector_all(
            "#scan-insp .kategorie-wahl", "ns => ns.map(n => n.firstElementChild.tagName)")
        pruefe(typen[1] == "INPUT", f"'neue Kategorie' oeffnet kein Textfeld: {typen[:3]}")
        f.seite.wait_for_timeout(1100)          # Autospeichern abwarten
        typen_danach = f.seite.eval_on_selector_all(
            "#scan-insp .kategorie-wahl", "ns => ns.map(n => n.firstElementChild.tagName)")
        pruefe(typen_danach == typen,
               f"der Tipp-Modus ueberlebt den Neuaufbau nicht: {typen} -> {typen_danach}")

        # ------------------------------------------------------------------
        # **Kein Feld eines Items laesst die Zeile springen — und der Fokus
        # bleibt in seiner Maske.**
        #
        # Gemeldet wurde es beim TAB: man tippt einen Namen, springt weiter, und
        # die Zeile ist woanders. Zwei Ursachen lagen dahinter, beide nur im
        # Fenster messbar: die gemerkte Reihenfolge haengt am NAMEN (ein
        # umbenanntes Item galt als neu und rutschte ans Ende), und
        # `scanVorschauenHolen()` baut die rechte Spalte an `zeichneScans()`
        # vorbei neu — beim Umbenennen fehlt die Vorschau unter dem neuen Namen,
        # sie wird nachgeholt, und dieser Aufbau rettete den Fokus nicht.
        f.klick_text("#scan-insp .tabs .tab", "Items")
        f.seite.wait_for_timeout(300)
        vorher = f.seite.eval_on_selector_all(
            "#scan-insp .scan-maske", "ns => ns.map(n => n.id)")
        pruefe(all(n.startswith("maske:item:") for n in vorher),
               f"jede Item-Maske braucht ihre id: {vorher[:3]}")
        ziel_id = vorher[0] or "(ohne id)"

        # 1. Umbenennen: echtes Tippen, echtes TAB.
        #
        # **Dabei darf das Vorschaubild nicht verschwinden.** Der
        # Zwischenspeicher haengt am ITEM-Namen, das Bild an der Template-DATEI
        # — und die heisst nach dem Umbenennen genauso. Ohne
        # `scanVorschauUmbenennen()` galt die Vorschau als fehlend: die Maske
        # wurde einmal OHNE Bild gezeichnet, dieselben Bytes noch einmal aus
        # Python geholt und die Spalte ein zweites Mal aufgebaut. Sichtbar war
        # das als kurzes Flackern. Gemessen wird beides — die Zahl der
        # Neuaufbauten und ob das Bild durchgehend dasteht.
        namensfeld = f'[id="{ziel_id}"] .scan-maske-felder > input'
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
            "#scan-insp .scan-maske", "ns => ns.map(n => n.id)")
        pruefe(nach[0] == "maske:item:Zeta",
               f"das Umbenennen verschiebt die Zeile: {nach}")
        pruefe(len(nach) == len(vorher) and nach[1:] == vorher[1:],
               f"die uebrigen Zeilen haben sich bewegt: {vorher} -> {nach}")
        wo = f.seite.evaluate("""() => {
          const a = document.activeElement;
          const m = a && a.closest ? a.closest('.scan-maske') : null;
          return m ? m.id : (a ? a.tagName : "nichts");
        }""")
        pruefe(wo == "maske:item:Zeta",
               f"der Fokus verlaesst die Maske: erwartet Zeta, da: {wo}")

        # 2. Kategorie: sie war der erste Sortierschluessel und damit das letzte
        #    Feld, das die Zeile noch wegspringen liess.
        f.seite.eval_on_selector_all(".scan-maske .kategorie-wahl select", """(ns, id) => {
          const e = ns.find((n) => n.closest(".scan-maske").id === id) || ns[0];
          e.focus();
          e.value = "Helme";
          e.dispatchEvent(new Event('change', {bubbles: true}));
        }""", "maske:item:Zeta")
        f.seite.wait_for_timeout(900)
        nach_kat = f.seite.eval_on_selector_all(
            "#scan-insp .scan-maske", "ns => ns.map(n => n.id)")
        pruefe(nach_kat == nach,
               f"die Kategorie verschiebt die Zeile: {nach} -> {nach_kat}")
        # Sie steht dann unter der ALTEN Ueberschrift — das muss dastehen,
        # sonst liest sich die Liste falsch.
        stand = f.seite.eval_on_selector(
            '[id="maske:item:Zeta"] .scan-maske-stand', "e => e.textContent")
        pruefe("→ Helme" in stand,
               f"die gewechselte Kategorie wird nicht angesagt: {stand!r}")

        # ------------------------------------------------------------------
        # **Beim Tippen springt nichts, auf Knopfdruck schon.** Sortierte sich
        # die Liste nach jeder Aenderung neu, rutscht genau die Zeile weg, an
        # der man gerade arbeitet — man tippt eine 2 und tippt danach im
        # naechsten Item weiter.
        f.klick_text("#scan-insp .tabs .tab", "Items")
        vor_prio = f.seite.eval_on_selector_all(
            "#scan-insp .scan-maske", "ns => ns.map(n => n.id)")
        # Das ERSTE Item auf einen hohen Rang setzen: sortiert die Liste
        # sofort, stuende es danach am Ende seiner Gruppe. Genau daran misst
        # sich, ob die Reihenfolge stehen bleibt.
        erste = vor_prio[0]
        f.seite.eval_on_selector_all('.scan-maske input[type="number"]', """(ns, id) => {
          const e = ns.find((n) => n.closest(".scan-maske").id === id) || ns[0];
          e.focus();
          e.value = "9";
          e.dispatchEvent(new Event('change', {bubbles: true}));
        }""", erste)
        f.seite.wait_for_timeout(700)
        nach_prio = f.seite.eval_on_selector_all(
            "#scan-insp .scan-maske", "ns => ns.map(n => n.id)")
        pruefe(nach_prio == vor_prio,
               f"die Liste sortiert beim Tippen um: {vor_prio} -> {nach_prio}")
        # Gegenprobe zur Gegenprobe: der Knopf muss sie sehr wohl umsortieren,
        # sonst misst der Test oben nur eine Liste, die sich ohnehin nicht regt.
        f.klick_text("#scan-insp .scan-kopf button", "↕ Sortieren")
        sortiert = f.seite.eval_on_selector_all(
            "#scan-insp .scan-maske", "ns => ns.map(n => n.id)")
        pruefe(sortiert != vor_prio,
               f"„Sortieren“ ordnet die Liste nicht um: {sortiert}")

        knoepfe = f.seite.eval_on_selector_all(
            "#scan-insp .scan-kopf button", "ns => ns.map(n => n.textContent)")
        pruefe(any("Sortieren" in k for k in knoepfe),
               f"kein Sortier-Knopf im Kopf: {knoepfe}")
        # Und der Kopf bleibt beim Scrollen stehen — sonst ist die Reiterleiste
        # nach drei Umdrehungen weg.
        klebt = f.seite.eval_on_selector(
            "#scan-insp .scan-kopf", "e => getComputedStyle(e).position")
        pruefe(klebt == "sticky", f"der Kopf klebt nicht: {klebt}")

        # ------------------------------------------------------------------
        # **Alle drei Listen stehen rechts und sind Masken.** Das ist die
        # Schicht, die die Vertragssuite nicht sehen kann: dass ein Reiter
        # ueberhaupt etwas zeichnet, faellt nur im Fenster auf.
        links_vorher = f.seite.eval_on_selector(
            "#sicht-scans .seite.links", "e => e.getBoundingClientRect().height")
        for reiter, art in (("Slots", "slot"), ("Scans", "scan"), ("Items", "item")):
            f.klick_text("#scan-insp .tabs .tab", reiter)
            masken = f.anzahl("#scan-insp .scan-maske")
            pruefe(masken > 0, f"Reiter „{reiter}“ zeichnet keine Maske")
            eigene = f.anzahl(f'#scan-insp .scan-maske[id^="maske:{art}:"]')
            pruefe(eigene == masken,
                   f"„{reiter}“: {masken} Masken, davon {eigene} mit {art}-id")
            pruefe(f.anzahl("#ab-listen .scan-maske") == 0,
                   f"„{reiter}“: es steht noch eine Maske in der linken Spalte")
            links = f.seite.eval_on_selector(
                "#sicht-scans .seite.links", "e => e.getBoundingClientRect().height")
            pruefe(links == links_vorher,
                   f"die linke Spalte aendert bei „{reiter}“ ihre Hoehe: "
                   f"{links_vorher} -> {links}")
            f.bild("items_reiter_" + reiter.lower())
            if art == "slot":
                # Die Kachel zeigt die stabile ID, nicht die Stelle im Scan —
                # in dieser Sitzung fallen beide zusammen (Anlegen == Reihenfolge
                # im Scan), aber die ID darf sich nicht aendern, wenn ein Slot
                # ab- und wieder angeschaltet wird (siehe Vertragssuite dafuer).
                ids = f.seite.eval_on_selector_all(
                    "#scan-insp .scan-marke .zahl",
                    "ns => ns.map(n => n.textContent)")
                pruefe(ids == ["#" + str(i + 1) for i in range(masken)],
                       f"Slot-IDs nicht wie erwartet: {ids}")
                # Nummer und Groesse stehen auf EINER Hoehe — die eine unten in
                # der ersten Spalte, die andere in der Zustandszeile der
                # dritten. Ohne `align-self:stretch` laegen sie auseinander.
                kanten = f.seite.evaluate("""() => {
                  const m = document.querySelector("#scan-insp .scan-maske");
                  const n = m.querySelector(".scan-marke .zahl");
                  const g = m.querySelector(".scan-maske-stand .zahl");
                  return [Math.round(n.getBoundingClientRect().bottom),
                          Math.round(g.getBoundingClientRect().bottom)];
                }""")
                pruefe(abs(kanten[0] - kanten[1]) <= 1,
                       f"Nummer und Größe stehen nicht auf einer Höhe: {kanten}")

        # **Ein Scan war nicht mehr zu loeschen**: der Klick auf ihn oeffnete
        # ihn, das Oeffnen schaltete auf die Item-Liste um, und der Knopf stand
        # in der Spalte, die man damit gerade verlassen hatte.
        f.klick_text("#scan-insp .tabs .tab", "Scans")
        f.klick('#scan-insp .scan-maske[id="maske:scan:Inventar"] input')
        f.seite.wait_for_timeout(300)
        f.klick('#scan-insp .scan-maske[id="maske:scan:Inventar"] .scan-maske-stand')
        reiter_danach = f.text("#scan-insp .tabs .tab.an")
        pruefe(reiter_danach.startswith("Scans"),
               f"nach dem Oeffnen steht der Reiter auf „{reiter_danach}“")
        knoepfe = f.seite.eval_on_selector_all(
            "#scan-insp .scan-maske-detail button", "ns => ns.map(n => n.textContent)")
        pruefe(any("löschen" in k for k in knoepfe),
               f"kein Loesch-Knopf im Detailteil des Scans: {knoepfe}")
        f.bild("items_scan_detail")

        # **Der Bestaetigungsklick** war die einzige Item-Eigenschaft ohne
        # Bedienelement — im Modell und in den Konsolen-Editoren gibt es sie
        # seit jeher.
        f.klick_text("#scan-insp .tabs .tab", "Items")
        f.klick("#scan-insp .scan-maske .scan-maske-felder input")
        f.seite.wait_for_timeout(300)
        beschriftungen = f.seite.eval_on_selector_all(
            "#scan-insp .scan-maske-detail .ueberschrift",
            "ns => ns.map(n => n.textContent)")
        pruefe(any("BESTÄTIGUNGSKLICK" in b for b in beschriftungen),
               f"kein Bestaetigungsklick in der Item-Maske: {beschriftungen}")

        fehler.extend(f.fehler)
    return fehler


if __name__ == "__main__":
    main("Items", lauf)
