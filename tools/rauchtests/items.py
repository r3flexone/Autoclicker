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

        fehler.extend(f.fehler)
    return fehler


if __name__ == "__main__":
    main("Items", lauf)
