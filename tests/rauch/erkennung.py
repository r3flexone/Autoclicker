"""Rauchtest Scans-Reiter: die drei Scan-Arten durchschalten."""

from pathlib import Path

from ._bild import flaeche_mit_marke, stelle_bildschirm
from ._bruecke import Fenster, main, sandkasten


def aufbau():
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import Sequence

    sandkasten("rauch_erk_")
    image, region = flaeche_mit_marke()
    stelle_bildschirm(image)

    b = StudioBridge(Sequence(name="Rauch"),
                     Path("sequences/rauch/sequence.json"), "sequences")
    # **Erst der Scan, dann das Bild.** Die Aufnahme braucht ein eindeutiges
    # Speicherziel (`_scan_requirement`) — ohne offenen Scan der jeweiligen
    # Art gibt es kein Foto, und alles, was eines braucht (Marker messen,
    # testen), stuende offen.
    b.boss_scan_new({"name": "Bossfarm"})
    b.scan_screenshot({"kind": "boss"})
    b.boss_scan_set({"field": "region", "value": list(region)})
    b.boss_new({"name": "Ancient Dragon"})
    b.marker_measure({"kind": "boss"})
    b.boss_set({"field": "action", "value": "item_scan"})
    b.boss_new({"name": "Hydra", "global": True})
    b.icon_scan_new({"name": "Mission nicht machbar"})
    b.scan_screenshot({"kind": "icon"})
    b.icon_set({"field": "region", "value": list(region)})
    b.marker_measure({"kind": "icon"})
    b.icon_set({"field": "action", "value": "click"})
    return b


def lauf():
    b = aufbau()
    fehler = []

    def pruefe(bedingung, text):
        if not bedingung:
            fehler.append(text)

    with Fenster(b) as f:
        f.reiter("scans")
        for kind in ("item", "boss", "icon"):
            f.klick(f'#scan-art button[data-scan-kind="{kind}"]')
            pruefe(bool(f.text("#view-scans").strip()), f"{kind}: Ansicht leer")
            if kind in ("boss", "icon"):
                # Testen ist folgenlos - es zeigt nur, WAS passieren wuerde.
                marke = "Boss-Scan testen" if kind == "boss" else "Icon-Scan testen"
                f.klick_text("#view-scans button", marke)
                pruefe(bool(f.status().strip()), f"{kind}: Test meldete nichts")
            f.image(f"erkennung_{kind}")
        # Die Aufnahme-Karte wandert zwischen den Assistenten und muss zurueck.
        f.klick('#scan-art button[data-scan-kind="item"]')
        pruefe("Aufnahme" in f.text("#view-scans"),
               "die Aufnahme-Karte kam nicht zum Item-Assistenten zurueck")
        fehler.extend(f.fehler)
    return fehler


if __name__ == "__main__":
    main("Erkennung", lauf)
