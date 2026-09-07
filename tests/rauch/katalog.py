"""Rauchtest Item-Katalog: der Schalter am Scan und das Einordnen auf Knopfdruck.

Was die Vertragssuite hier NICHT sehen kann: ob der Schalter und der Knopf
ueberhaupt gezeichnet werden. Beide haengen an Feldern der Momentaufnahme
(`use_catalog`, `katalog_an`) — steht dort ein Tippfehler, ist der Wert
schlicht `undefined`, die Seite laeuft weiter und der Knopf fehlt einfach.
Genau der Fehler, der im Fenster sofort auffaellt und in keinem Logik-Test.
"""

import json
from pathlib import Path

from ._bild import inventar, stelle_bildschirm
from ._bruecke import Fenster, main, sandkasten

# Namen aus dem echten Katalog. Zwei Helme (damit die Rangfolge etwas zu
# entscheiden hat) und ein Name, den der Katalog NICHT kennt.
BEKANNT = ["Citadel Helmet", "Centaurs Helmet"]
FREMD = "item_7"


def aufbau():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import ItemProfile, Sequence
    from autoclicker import config as cfgmod

    sandkasten("rauch_katalog_")
    bild, _ecken = inventar()
    stelle_bildschirm(bild)

    datei = Path("katalog.json").resolve()
    datei.write_text(json.dumps({"items": {
        "Citadel Helmet": {"kategorie": "Helm", "wert": 15000},
        "Centaurs Helmet": {"kategorie": "Helm", "wert": 20000},
    }}), encoding="utf-8")
    cfgmod.CONFIG.scan_catalog_file = str(datei)

    b = StudioBridge(Sequence(name="Rauch"),
                     Path("sequences/rauch/sequence.json"), "sequences")
    b.scan_neu({"name": "Inventar"})
    b.scan_oeffnen({"name": "Inventar"})
    for name in BEKANNT + [FREMD]:
        b.items[name] = ItemProfile(name=name)
        b._dazu("item", name)
    return b


def lauf():
    b = aufbau()
    fehler = []

    def pruefe(bedingung, text):
        if not bedingung:
            fehler.append(text)

    def knoepfe(f):
        """Wie oft der Katalog-Knopf gerade gezeichnet ist."""
        return len([k for k in f.seite.query_selector_all("#scan-insp button")
                    if "Aus Katalog einordnen" in (k.inner_text() or "")])

    with Fenster(b) as f:
        f.reiter("scans")

        # Solange der Scan den Katalog nicht benutzt, darf der Knopf nicht da
        # sein — er koennte nichts tun, und ein Knopf, der nichts tut, ist
        # schlechter als keiner.
        pruefe(knoepfe(f) == 0,
               "der Katalog-Knopf steht da, obwohl der Scan den Katalog nicht benutzt")

        # Der Schalter steht in den Einstellungen des Scans, also in der
        # aufgeklappten Scan-Maske — und wird hier ueber die SEITE bedient, nicht
        # ueber die Bruecke: dass ein Klick dort ankommt, ist genau das, was ein
        # Logik-Test nicht sehen kann.
        f.klick_text("#scan-insp .tabs button", "Scans")
        f.klick("#scan-insp .scan-maske")
        schalter = f.seite.locator("#scan-insp label", has_text="Item-Katalog benutzen")
        pruefe(schalter.count() == 1,
               "der Katalog-Schalter fehlt in den Scan-Einstellungen")
        f.bild("katalog_schalter")
        schalter.locator("input").click()
        f.seite.wait_for_timeout(700)
        pruefe(b.scans["Inventar"].use_catalog is True,
               "der Klick auf den Schalter kam nicht in der Bruecke an")

        pruefe(knoepfe(f) == 1,
               "der Katalog-Knopf fehlt, obwohl der Scan den Katalog benutzt")
        f.bild("katalog_knopf")

        f.klick_text("#scan-insp button", "Aus Katalog einordnen")

        pruefe(b.items["Citadel Helmet"].category == "Helm"
               and b.items["Centaurs Helmet"].category == "Helm",
               f"die Kategorie wurde nicht gesetzt: "
               f"{[(n, i.category) for n, i in b.items.items()]}")
        # Teurer zuerst: Centaurs (20000) vor Citadel (15000).
        pruefe(b.items["Centaurs Helmet"].priority == 1
               and b.items["Citadel Helmet"].priority == 2,
               f"die Rangfolge stimmt nicht: "
               f"{[(n, i.priority) for n, i in b.items.items()]}")
        # Ein Name, den der Katalog nicht kennt, wird nicht geraten.
        pruefe(b.items[FREMD].category is None,
               f"'{FREMD}' wurde eingeordnet, obwohl er nicht im Katalog steht")

        # Und es steht auch dran, dass etwas passiert ist.
        status = f.status()
        pruefe("eingeordnet" in status,
               f"die Statuszeile sagt nichts vom Einordnen: {status!r}")
        f.bild("katalog_eingeordnet")

    return fehler


if __name__ == "__main__":
    main("Katalog", lauf)
