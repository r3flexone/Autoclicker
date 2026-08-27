"""Rauchtest Scans-Reiter: die drei Scan-Arten durchschalten."""

from pathlib import Path

from ._bild import flaeche_mit_marke, stelle_bildschirm
from ._bruecke import Fenster, main, sandkasten


def aufbau():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import Sequence

    sandkasten("rauch_erk_")
    bild, region = flaeche_mit_marke()
    stelle_bildschirm(bild)

    b = StudioBridge(Sequence(name="Rauch"),
                     Path("sequences/rauch/sequence.json"), "sequences")
    # **Erst der Scan, dann das Bild.** Die Aufnahme braucht ein eindeutiges
    # Speicherziel (`_scan_voraussetzung`) — ohne offenen Scan der jeweiligen
    # Art gibt es kein Foto, und alles, was eines braucht (Marker messen,
    # testen), stuende offen.
    b.boss_scan_neu({"name": "Bossfarm"})
    b.scan_foto({"art": "boss"})
    b.boss_scan_setzen({"feld": "region", "wert": list(region)})
    b.boss_neu({"name": "Ancient Dragon"})
    b.marker_messen({"art": "boss"})
    b.boss_setzen({"feld": "aktion", "wert": "item_scan"})
    b.boss_neu({"name": "Hydra", "global": True})
    b.icon_scan_neu({"name": "Mission nicht machbar"})
    b.scan_foto({"art": "icon"})
    b.icon_setzen({"feld": "region", "wert": list(region)})
    b.marker_messen({"art": "icon"})
    b.icon_setzen({"feld": "aktion", "wert": "click"})
    return b


def lauf():
    b = aufbau()
    fehler = []

    def pruefe(bedingung, text):
        if not bedingung:
            fehler.append(text)

    with Fenster(b) as f:
        f.reiter("scans")
        for art in ("item", "boss", "icon"):
            f.klick(f'#scan-art button[data-scan-art="{art}"]', warten=600)
            pruefe(bool(f.text("#sicht-scans").strip()), f"{art}: Ansicht leer")
            if art in ("boss", "icon"):
                # Testen ist folgenlos - es zeigt nur, WAS passieren wuerde.
                marke = "Boss-Scan testen" if art == "boss" else "Icon-Scan testen"
                f.klick_text("#sicht-scans button", marke, warten=900)
                pruefe(bool(f.status().strip()), f"{art}: Test meldete nichts")
            f.bild(f"erkennung_{art}")
        # Die Aufnahme-Karte wandert zwischen den Assistenten und muss zurueck.
        f.klick('#scan-art button[data-scan-art="item"]', warten=600)
        pruefe("Aufnahme" in f.text("#sicht-scans"),
               "die Aufnahme-Karte kam nicht zum Item-Assistenten zurueck")
        fehler.extend(f.fehler)
    return fehler


if __name__ == "__main__":
    main("Erkennung", lauf)
