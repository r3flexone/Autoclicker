"""Rauchtest Item-Katalog: der Schalter am Scan und das Einordnen auf Knopfdruck.

Was die Vertragssuite hier NICHT sehen kann: ob der Schalter und der Knopf
ueberhaupt gezeichnet werden. Beide haengen an Feldern der Momentaufnahme
(`use_catalog`, `catalog_on`) — steht dort ein Tippfehler, ist der Wert
schlicht `undefined`, die Seite laeuft weiter und der Knopf fehlt einfach.
Genau der Fehler, der im Fenster sofort auffaellt und in keinem Logik-Test.
"""

import json
from pathlib import Path

from ._image import inventory_image, mock_screen
from ._bridge import Window, main, sandbox

# Namen aus dem echten Katalog. Zwei Helme (damit die Rangfolge etwas zu
# entscheiden hat) und ein Name, den der Katalog NICHT kennt.
BEKANNT = ["Citadel Helmet", "Centaurs Helmet"]
FREMD = "item_7"



def mini_png(target: Path) -> None:
    """Eine winzige, GUELTIGE Vorlage.

    Der Durchgang oeffnet die Datei wirklich — mit kaputten Bytes zaehlte jedes
    Item als "ohne Vorschlag", und der Test pruefte den Fehlerpfad statt den
    Abbruch. Erzeugt statt als Hex getippt: eine von Hand geschriebene
    PNG-Pruefsumme ist genau die Sorte Detail, die man einmal falsch abtippt
    und dann lange sucht.
    """
    from PIL import Image
    Image.new("RGB", (8, 8), (200, 60, 60)).save(target)


def setup():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import ItemProfile, Sequence
    from autoclicker import config as cfgmod

    sandbox("rauch_katalog_")
    image, _corners = inventory_image()
    mock_screen(image)

    file = Path("catalog.json").resolve()
    file.write_text(json.dumps({"items": {
        "Citadel Helmet": {"kategorie": "Helm", "wert": 15000},
        "Centaurs Helmet": {"kategorie": "Helm", "wert": 20000},
    }}), encoding="utf-8")
    cfgmod.CONFIG.scan_catalog_file = str(file)

    # **Beide LLM-Schalter, und keiner davon aus der echten config.json.** Der
    # Sammel-Knopf haengt am Modul-CONFIG (`llm_on` in der Momentaufnahme), der
    # Durchgang liest die DATEI (`load_config`). Haengte der Test an der Config
    # des Entwicklers, waere er hier gruen und auf einem frischen Checkout rot —
    # dort steht `llm_enabled` auf false.
    cfgmod.CONFIG.llm_enabled = True
    # Der Pfad steht auch in der DATEI: der Einstellungen-Reiter liest sie und
    # nicht `CONFIG`, und nur ein vom Standard abweichender Wert bringt den
    # „↺ Standard"-Knopf ueberhaupt hervor — den, dessen Beschriftung hier
    # geprueft wird.
    Path("config.json").write_text(
        json.dumps({"llm_enabled": True, "scan_catalog_file": str(file)}),
        encoding="utf-8")

    b = StudioBridge(Sequence(name="Rauch"),
                     Path("sequences/smoke/sequence.json"), "sequences")
    b.scan_new({"name": "Inventar"})
    b.scan_open({"name": "Inventar"})
    # Die Vorlagen stehen HIER und nicht spaeter im Lauf: `SC` wird beim
    # Reiterwechsel nicht neu von der Bruecke geholt (das ist Absicht — der
    # Scans-Reiter haelt seinen eigenen Zustand), also saehe die Seite eine
    # Aenderung, die erst danach passiert, ueberhaupt nicht.
    templates_list = Path("sequences/smoke/templates")
    templates_list.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(BEKANNT + [FREMD]):
        mini_png(templates_list / f"t{i}.png")
        b.items[name] = ItemProfile(name=name, template=f"t{i}.png")
        b._add_to_scan("item", name)
    return b


def run():
    b = setup()
    error = []

    def expect(condition, text):
        if not condition:
            error.append(text)

    def buttons(f):
        """Wie oft der Katalog-Knopf gerade gezeichnet ist."""
        return len([k for k in f.page.query_selector_all("#scan-insp button")
                    if "Aus Katalog einordnen" in (k.inner_text() or "")])

    with Window(b) as f:
        f.tab("scans")

        # Solange der Scan den Katalog nicht benutzt, darf der Knopf nicht da
        # sein — er koennte nichts tun, und ein Knopf, der nichts tut, ist
        # schlechter als keiner.
        expect(buttons(f) == 0,
               "der Katalog-Knopf steht da, obwohl der Scan den Katalog nicht benutzt")

        # Der Schalter steht in den Einstellungen des Scans, also in der
        # aufgeklappten Scan-Maske — und wird hier ueber die SEITE bedient, nicht
        # ueber die Bruecke: dass ein Klick dort ankommt, ist genau das, was ein
        # Logik-Test nicht sehen kann.
        f.click_text("#scan-insp .tabs button", "Scans")
        f.click("#scan-insp .scan-card")
        toggle = f.page.locator("#scan-insp label", has_text="Item-Katalog benutzen")
        expect(toggle.count() == 1,
               "der Katalog-Schalter fehlt in den Scan-Einstellungen")
        f.image("katalog_schalter")
        toggle.locator("input").click()
        f.settle()
        expect(b.scans["Inventar"].use_catalog is True,
               "der Klick auf den Schalter kam nicht in der Bruecke an")

        expect(buttons(f) == 1,
               "der Katalog-Knopf fehlt, obwohl der Scan den Katalog benutzt")
        f.image("katalog_knopf")

        f.click_text("#scan-insp button", "Aus Katalog einordnen")

        expect(b.items["Citadel Helmet"].category == "Helm"
               and b.items["Centaurs Helmet"].category == "Helm",
               f"die Kategorie wurde nicht gesetzt: "
               f"{[(n, i.category) for n, i in b.items.items()]}")
        # Teurer zuerst: Centaurs (20000) vor Citadel (15000).
        expect(b.items["Centaurs Helmet"].priority == 1
               and b.items["Citadel Helmet"].priority == 2,
               f"die Rangfolge stimmt nicht: "
               f"{[(n, i.priority) for n, i in b.items.items()]}")
        # Ein Name, den der Katalog nicht kennt, wird nicht geraten.
        expect(b.items[FREMD].category is None,
               f"'{FREMD}' wurde eingeordnet, obwohl er nicht im Katalog steht")

        # Und es steht auch dran, dass etwas passiert ist.
        status = f.status()
        expect("eingeordnet" in status,
               f"die Statuszeile sagt nichts vom Einordnen: {status!r}")
        f.image("katalog_eingeordnet")

        # --- Die Ueberschrift benennt die Kategorie um ----------------------
        # Ein Eingabefeld IN einer Ueberschrift ist die Stelle, an der ein
        # Tippfehler unsichtbar bleibt: die Vertragssuite sieht nur, dass die
        # Bruecken-Methode existiert.
        f.click_text("#scan-insp .tabs button", "Items")
        # Gezielt die Gruppe „Helm" — `.first` traf die Gruppe „Ohne
        # Kategorie", die in der Liste zuerst steht.
        field = f.page.locator('.scan-category-header input[value="Helm"]')
        expect(field.count() == 1,
               f"die Ueberschrift 'Helm' ist kein Feld ({field.count()} Treffer)")
        field.fill("Kopfschutz")
        field.press("Enter")
        f.settle()
        expect(b.items["Citadel Helmet"].category == "Kopfschutz"
               and b.items["Centaurs Helmet"].category == "Kopfschutz",
               "das Umbenennen kam nicht in der Bruecke an: "
               + str([(n, i.category) for n, i in b.items.items()]))
        f.image("kategorie_umbenannt")

        # --- Und der Katalog laesst sich HIER holen ------------------------
        # Der Knopf haengt an `meta.aktion` aus `config_meta.py`. Wuerde
        # `M.as_dict()` das Feld nicht mitliefern, waere der Wert schlicht
        # `undefined`, die Seite liefe weiter und der Knopf fehlte — genau der
        # Fehler, den die Vertragssuite nicht sehen kann: dort steht
        # `cfgAction(` im Quelltext und ist trotzdem wirkungslos.
        f.tab("settings")
        f.page.fill("#cfg-search", "Item-Katalog")
        f.settle()
        button = f.page.locator("#cfg-fields button",
                                has_text="Katalog aus der Spiel-API holen")
        expect(button.count() == 1,
               "der Knopf zum Holen fehlt am Katalog-Feld")
        f.image("katalog_einstellungen")

        # Ein Rauchtest geht nicht ins Netz: die Spieldaten kommen gestellt,
        # der Weg von der Seite bis in die Datei ist trotzdem der echte.
        import tools.catalog as tk
        real = tk.fetch_game_data
        tk.fetch_game_data = lambda *a, **kw: {"Items": {"Items": [
            {"Name": "godlike_bow", "EquipmentSlot": 7, "BaseValue": 900}]}}
        try:
            button.click()
            f.settle()
        finally:
            tk.fetch_game_data = real
        status = f.status()
        expect("1 Items" in status,
               f"der Klick auf 'Katalog holen' kam nicht an: {status!r}")
        # Und danach steht am Feld, was drinliegt und von wann es ist — sonst
        # holt man die Liste entweder nie wieder oder bei jedem Zweifel neu.
        f.settle()
        stamp_value = f.page.locator("#cfg-fields .cfg-rights p.hint")
        expect(stamp_value.count() >= 1 and "1 Items" in (stamp_value.first.inner_text() or ""),
               "der Stand des Katalogs fehlt am Feld: "
               + (stamp_value.first.inner_text() if stamp_value.count() else "(nichts)"))
        f.image("katalog_geholt")

        # --- Und nichts laeuft aus der Spalte -----------------------------
        # **Der Standard-Knopf trug den Standard-WERT im Namen**, und bei
        # diesem Feld ist das ein ganzer Satz ("Kategorie und Namen bleiben
        # Handarbeit"): der Knopf wurde breiter als seine Spalte und lief
        # rechts aus dem Fenster. Gemessen wird an der ZELLE gegen ihre
        # Spalte, nicht am Zeilen-Container — der ist immer so breit wie die
        # Zeile, und ein Test darauf bleibt gruen, waehrend der Inhalt auf
        # halber Strecke weiterlaeuft.
        # **In einem SCHMALEN Fenster**, sonst tritt der Fall gar nicht ein:
        # bei 1500 px passt auch ein Knopf mit einem ganzen Satz darin, und
        # der Test bliebe gruen, waehrend er bei 950 px aus dem Bild laeuft.
        # Gemessen wird gegen die Mitte (`#cfg-fields`), denn das ist die
        # Kante, hinter der es aus dem Fenster geht.
        f.page.set_viewport_size({"width": 950, "height": 700})
        f.page.fill("#cfg-search", "scan_")
        f.settle()
        out = f.page.evaluate("""() => {
            const mitte = document.getElementById('cfg-fields');
            const limit = mitte.getBoundingClientRect().right;
            const out = [];
            mitte.querySelectorAll('.cfg-rights > *').forEach((k) => {
              const r = k.getBoundingClientRect();
              if (r.width && r.right > limit + 1)
                out.push((k.textContent || '').slice(0, 40));
            });
            return out;
        }""")
        expect(not out, f"ragt aus der Spalte: {out}")

        # **Ein Knopf sagt, was er TUT.** Der Standard-Knopf trug den
        # Standard-WERT im Namen, und bei diesem Feld ist das ein ganzer Satz
        # ("Kategorie und Namen bleiben Handarbeit") — die Beschriftung war
        # damit laenger als die Spalte und wurde abgeschnitten. Der Satz steht
        # ohnehin schon eine Zeile hoeher am Wert; was zurueckgesetzt wird,
        # liest im Tooltip, wer nachfragt.
        long_text = f.page.evaluate("""() => [...document.querySelectorAll(
            '#cfg-fields .cfg-default')].map((k) => (k.textContent || '').trim())
            .filter((t) => t.length > 40)""")
        expect(not long_text, f"die Standard-Beschriftung ist ein Satz: {long_text}")
        f.image("cfg_spaltenbreite")

        # --- Der Benenn-Durchgang laesst sich abbrechen --------------------
        # **Die Schleife steht in der Ansicht**, damit es ein Abbrechen gibt —
        # und damit ist sie genau das, was die Vertragssuite nicht sehen kann:
        # dort werden Start, Schritt und Ende von Hand nacheinander gerufen.
        # Ob die Seite das auch tut, ob der Kasten kommt und ob der Knopf
        # wirklich stoppt, faellt nur hier auf.
        import autoclicker.llm_vision as lv
        import time as _t

        asked = []

        def slow(*a, **kw):
            asked.append(1)
            # Lang genug, um dazwischen zu klicken — und der Screenshot davor
            # kostet selbst schon eine halbe Sekunde. Mit 0,6 s war der
            # Durchgang durch, bevor der Klick kam, und Playwright wartete
            # danach auf einen Kasten, den es nicht mehr gab.
            _t.sleep(1.5)
            return ("Citadel Helmet", "") if len(asked) == 1 else (None, "")

        real_name = lv.suggest_item_name_with_reason
        lv.suggest_item_name_with_reason = slow
        try:
            f.tab("scans")
            f.click_text("#scan-insp .tabs button", "Items")
            f.settle()
            # **Nicht nach „Alle" suchen**: in derselben Leiste steht „alle
            # dazu" aus der Filterzeile, und `click_text` nimmt den ersten
            # Treffer — geklickt wurde dann der Filter, und der Kasten kam nie.
            button = f.page.locator(".scan-header button", has_text="benennen")
            expect(button.count() == 1,
                   f"der Sammel-Knopf fehlt im Kopf ({button.count()} Treffer)")

            # **Der Abbruch-Klick wird im BROWSER gestellt, bevor es losgeht.**
            # Waehrend eines Schritts haelt der Modell-Aufruf den Python-Thread
            # des Pruefstands fest — ein `page.click()` von hier waere erst
            # zustellbar, wenn der ganze Durchgang durch ist. Der Timer laeuft
            # dagegen im Browser weiter, also genau dort, wo auch der Nutzer
            # klickt. (Dieselbe Grenze ist der Grund, warum der Durchgang von
            # der Seite getrieben wird statt von einem Abbruch-Flag.)
            f.page.evaluate("""
                window.__abb = setInterval(() => {
                  const b = document.querySelector('.wait-box button');
                  if (b) { b.click(); clearInterval(window.__abb); }
                }, 100);
            """)
            button.click()
            f.page.wait_for_selector(".wait-box", state="detached", timeout=15000)
        finally:
            lv.suggest_item_name_with_reason = real_name

        expect(len(asked) < 3,
               f"der Abbruch hat nichts gestoppt: {len(asked)} von 3 gefragt")

        # **Ein ECHTER Mausklick, kein `el.click()` aus JavaScript.** Der oben
        # kommt aus einem Browser-Timer und geht am Zeiger vorbei — er wuerde
        # auch dann feuern, wenn ein Overlay davor laege oder der Knopf
        # `pointer-events:none` haette. Hier klickt Playwright wie ein Nutzer,
        # ohne laufenden Durchgang (der blockiert sonst den Pruefstand).
        f.page.evaluate("window.__traf = false;"
                         "showWork('T', 'x', () => { window.__traf = true; });")
        f.settle()
        f.page.click(".wait-box button")
        f.settle()
        expect(f.page.evaluate("window.__traf") is True,
               "ein echter Mausklick erreicht den Abbrechen-Knopf nicht")
        # **Und er quittiert sofort.** Der Abbruch wirkt erst, wenn die laufende
        # Vorlage zurueck ist — bis zu `llm_timeout`. Ohne Quittung sieht der
        # Knopf in dieser Zeit unberuehrt aus, und man haelt ihn fuer kaputt.
        receipt = f.page.evaluate(
            "() => { const b = document.getElementById('work-cancel');"
            "return b ? [b.disabled, b.textContent] : null; }")
        expect(receipt and receipt[0] is True and "Bricht ab" in receipt[1],
               f"der Abbrechen-Knopf quittiert den Klick nicht: {receipt}")
        f.page.evaluate("hideWait()")
        status = f.status()
        expect("abgebrochen" in status,
               f"die Statuszeile sagt nichts vom Abbruch: {status!r}")
        # Was bis dahin benannt wurde, bleibt stehen.
        expect("Citadel Helmet" in b.items,
               "der Abbruch hat das schon Benannte weggeworfen")
        f.image("autoname_abgebrochen")

    return error


if __name__ == "__main__":
    main("Katalog", run)
