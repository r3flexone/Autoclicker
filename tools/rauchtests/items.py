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

    b = StudioBridge(Sequence(name="Rauch"), Path("sequences/Rauch.json"), "sequences")
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
        # **Der Fokus bleibt beim Bearbeiten in DERSELBEN Maske.**
        #
        # Genau die drei Angaben, die man hier tippt, sortieren die Liste um
        # (Kategorie, Prioritaet, Name). `fokusMerken()` klettert bis zum
        # naechsten Element mit `id` und zaehlt dort die Position unter den
        # Eingabefeldern — ohne id an der Maske ist das die ganze Spalte, also
        # rund zweihundert Felder bei sechzig Items. Nach dem Umsortieren steht
        # an derselben Position das Feld eines FREMDEN Items: der Cursor
        # springt weg, und wer weitertippt, aendert das falsche.
        #
        # Nur im Fenster messbar: die Vertragssuite sieht keinen Fokus.
        f.klick_text("#scan-insp .tabs .tab", "Items")
        vorher = f.seite.eval_on_selector_all(
            "#scan-insp .scan-maske", "ns => ns.map(n => n.id)")
        pruefe(all(n.startswith("maske:item:") for n in vorher),
               f"jede Item-Maske braucht ihre id: {vorher[:3]}")
        # Die ERSTE Maske ohne Kategorie: sie wandert nach „Helme" und damit ans
        # Ende, also ist die Position, an der sie stand, danach eine andere.
        # (Die letzte liegt schon in „Helme" — dort waere nichts umzusortieren,
        # und der Test maesse nichts.)
        ziel_id = vorher[0]
        if not ziel_id:
            # Ohne id gibt es nichts zu messen — die Meldung darueber ist die
            # eigentliche Auskunft, ein Absturz waere nur Rauschen davor.
            ziel_id = "(ohne id)"
        else:
            f.seite.eval_on_selector(
                f'[id="{ziel_id}"] .scan-maske-felder input', "e => e.focus()")
        f.seite.eval_on_selector_all(".scan-maske .kategorie-wahl select", """(ns, id) => {
          const e = ns.find((n) => n.closest(".scan-maske").id === id) || ns[0];
          e.focus();
          e.value = "Helme";
          e.dispatchEvent(new Event('change', {bubbles: true}));
        }""", ziel_id)
        f.seite.wait_for_timeout(700)
        wo = f.seite.evaluate("""() => {
          const a = document.activeElement;
          const m = a && a.closest ? a.closest('.scan-maske') : null;
          return m ? m.id : (a ? a.tagName : "nichts");
        }""")
        pruefe(wo == ziel_id,
               f"der Fokus verlaesst die Maske: erwartet {ziel_id}, da: {wo}")
        nachher = f.seite.eval_on_selector_all(
            "#scan-insp .scan-maske", "ns => ns.map(n => n.id)")
        # Gegenprobe zur Gegenprobe: waere die Liste GAR NICHT umsortiert
        # worden, pruefte der Test oben nichts.
        pruefe(nachher != vorher,
               "die Kategorie hat die Liste nicht umsortiert — der Test misst nichts")

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
