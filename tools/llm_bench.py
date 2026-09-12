#!/usr/bin/env python3
"""Misst die LLM-Benennung gegen den eigenen Bestand — Variante gegen Variante.

    python tools/llm_bench.py                      # Standard: Vorlagen, einstufig
    python tools/llm_bench.py --modell qwen/qwen3.8-27b
    python tools/llm_bench.py --bild slot          # Ausschnitt statt Vorlage
    python tools/llm_bench.py --zweistufig         # erst die Art, dann der Name
    python tools/llm_bench.py --stimmen 3          # dreimal fragen, Mehrheit
    python tools/llm_bench.py --reasoning
    python tools/llm_bench.py --alle-modelle       # jedes geladene Modell nacheinander
    python tools/llm_bench.py --scan sequences/x/item_scans/y.json --limit 10

**Warum es das gibt.** Ob eine Aenderung am Prompt, am Bild oder am Modell
etwas bringt, laesst sich nicht ansehen — nur messen. Vier Befunde stehen
bereits fest und muessen nicht noch einmal geprueft werden:

* Die Lernmaske ist BESSER als ein neutraler Grund (9 von 10 beantworteten
  Vorlagen richtig gegen 6 von 14). Sie sieht falsch aus (83 % des Bildes sind
  durchsichtig) und ist es nicht.
* Ohne die geschlossene Namensliste kommt die ART statt des Gegenstands
  ("Bogen" statt "Godlike Bow") — 0 von 4.
* Das ganze Inventar-Raster in EINEM Aufruf laesst das Modell die
  Kandidatenliste abschreiben, statt das Bild zu lesen.
* Die ersten Aufrufe an einen kalten Server dauern ueber 120 s, die folgenden
  3,5. Deshalb waermt dieses Werkzeug vor dem Messen auf — sonst misst die
  erste Zahl das Laden des Modells und nicht die Frage.

**Was der Goldstandard ist — und was er nicht beweist.** Gemessen wird gegen
die Item-Namen, die im Katalog stehen: das sind echte Namen des Spiels, also
pruefbar. Ob sie am RICHTIGEN Item stehen, weiss dieses Werkzeug nicht — wer
seinen Bestand vom Modell benennen liess und nie nachgesehen hat, misst gegen
dessen eigene Fehler. Mit `--bild slot` ist der Bezug ein anderer und
belastbarer: dort ordnet die Template-Erkennung zu, also das, was der Nutzer
selbst gelernt hat.

Geschrieben wird nichts. Das Werkzeug liest den Scan, das gemerkte Bild und
den Katalog — und fragt das Modell.
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoclicker.config import load_config                          # noqa: E402
from autoclicker.katalog import lade_katalog                        # noqa: E402
from autoclicker.llm_vision import (                                # noqa: E402
    TIMEOUT, analyze_image, chat_endpoint, clean_boss_name,
    suggest_item_name_grund, test_endpoint_for,
)

BILDQUELLEN = ("vorlage", "grund", "slot")
NEUTRAL = (38, 42, 52)      # der Ton der Studio-Flaeche, nicht Schwarz: ein
                            # ausgeschnittenes Item auf Schwarz ist ein anderer
                            # Kontrast als eines in seinem Slot.


class NurConfig:
    """`state`-Stellvertreter fuer `_check_profile_match`.

    Die Erkennung braucht vom State nichts als die Config. Nachgebaut statt
    das private `_NurConfig` des Studios zu importieren: ein Werkzeug, das an
    internen Namen haengt, bricht beim naechsten Umbau — und drei Zeilen sind
    billiger als diese Kopplung.
    """

    def __init__(self, config):
        self.config = config


# ---------------------------------------------------------------- Bestand

def finde_scan(pfad: str = "") -> Path:
    """Die Scan-Datei — angegeben oder die zuletzt bearbeitete.

    Dieselbe Regel wie `zuletzt_bearbeitet()` im Studio: ein echtes „zuletzt
    geoeffnet" muesste jemand mitschreiben, und das Dateisystem weiss es schon.
    """
    if pfad:
        return Path(pfad)
    kandidaten = sorted(Path("sequences").glob("*/item_scans/*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    kandidaten = [p for p in kandidaten if p.name != "bibliothek.json"]
    if not kandidaten:
        raise SystemExit("Kein Item-Scan gefunden — --scan angeben.")
    return kandidaten[0]


def lade_scan(pfad: Path) -> dict:
    """Rohdaten des Scans plus die Pfade, die daran haengen."""
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    return {
        "name": daten.get("name") or pfad.stem,
        "items": daten.get("items") or {},
        "slots": daten.get("slots") or {},
        "toleranz": int(daten.get("color_tolerance") or 30),
        "vorlagen": pfad.parent.parent / "templates",
        # `sequences/<name>/bilder/<scan>.png` — neben `item_scans/`, nicht
        # darin (`_foto_pfad()` im Studio: `filepath.parent / "bilder"`).
        "bild": pfad.parent.parent / "bilder" / (pfad.stem + ".png"),
    }


def lade_foto(pfad: Path):
    """Das gemerkte Bild samt Ursprung — `(Bild, links, oben)` oder `None`.

    Der Ursprung des virtuellen Desktops steht IM PNG (Text-Chunk), nicht in
    einer Datei daneben. Ohne ihn waeren alle Slot-Regionen um einen Monitor
    verschoben.
    """
    from PIL import Image
    try:
        bild = Image.open(pfad)
        bild.load()
    except (OSError, ValueError):
        return None
    try:
        return bild, int(bild.info["links"]), int(bild.info["oben"])
    except (KeyError, TypeError, ValueError):
        return bild, 0, 0


# ---------------------------------------------------------------- Proben

def proben_aus_vorlagen(scan: dict, katalog, grund: bool, limit: int) -> list:
    """`(Wahrheit, Bild)` je Item mit Vorlage, dessen Name im Katalog steht."""
    from PIL import Image
    proben = []
    for name, eintrag in scan["items"].items():
        if len(proben) >= limit:
            break
        datei = eintrag.get("template")
        if not datei or not katalog.treffer(name):
            continue
        pfad = scan["vorlagen"] / datei
        try:
            with Image.open(pfad) as roh:
                bild = roh.copy()
        except (OSError, ValueError):
            continue
        proben.append((katalog.treffer(name), auf_grund(bild) if grund else bild))
    return proben


def auf_grund(bild, farbe=NEUTRAL):
    """Alpha auf einen neutralen Grund legen, statt es mitzuschicken."""
    from PIL import Image
    if bild.mode != "RGBA":
        return bild.convert("RGB")
    flaeche = Image.new("RGB", bild.size, farbe)
    flaeche.paste(bild, mask=bild.getchannel("A"))
    return flaeche


def proben_aus_slots(scan: dict, katalog, config, limit: int) -> list:
    """`(Wahrheit, Ausschnitt)` je Slot — die Wahrheit kommt aus dem Template.

    **Der belastbarere Bezug.** Bei den Vorlagen ist die Wahrheit der Name, der
    am Item steht; hat ihn das Modell selbst gesetzt und niemand nachgesehen,
    misst man gegen dessen eigene Fehler. Hier ordnet die Template-Erkennung zu
    — dieselbe Funktion, die im Lauf entscheidet — und das Bild ist der
    Ausschnitt, den das Spiel wirklich zeigt: mit echtem Hintergrund, nicht
    freigestellt.
    """
    from autoclicker.runtime.item_scan import _check_profile_match
    from autoclicker.persistence.serialization import _item_from_dict

    foto = lade_foto(scan["bild"])
    if foto is None:
        raise SystemExit(f"Kein gemerktes Bild ({scan['bild']}) — "
                         "im Scans-Reiter einmal aufnehmen, oder --bild vorlage.")
    bild, links, oben = foto
    profile = [_item_from_dict(e, n) for n, e in scan["items"].items()]
    stellvertreter = NurConfig(config)
    proben = []
    for slot in scan["slots"].values():
        if len(proben) >= limit:
            break
        region = slot.get("scan_region")
        if not region or len(region) != 4:
            continue
        kasten = (region[0] - links, region[1] - oben,
                  region[2] - links, region[3] - oben)
        if kasten[0] < 0 or kasten[1] < 0:
            continue
        if kasten[2] > bild.width or kasten[3] > bild.height:
            continue
        ausschnitt = bild.crop(kasten).convert("RGB")
        for item in profile:
            if not katalog.treffer(item.name):
                continue
            if _check_profile_match(item, ausschnitt, scan["toleranz"],
                                    stellvertreter, False,
                                    template_root=scan["vorlagen"]):
                proben.append((katalog.treffer(item.name), ausschnitt))
                break
    return proben


# ---------------------------------------------------------------- Fragen

def frage_einstufig(bild, kandidaten: list, config, modell: str) -> tuple:
    """Ein Aufruf mit der ganzen Namensliste — der Weg, den das Studio geht."""
    return suggest_item_name_grund(
        bild, provider=config.llm_provider, endpoint=config.llm_endpoint,
        model=modell, timeout=max(config.llm_timeout, 120),
        candidates=kandidaten)


def frage_zweistufig(bild, katalog, config, modell: str) -> tuple:
    """Erst die Art, dann der Name aus NUR dieser Art.

    Gegen den Fehler, der uebrig bleibt: die Art trifft das Modell zuverlaessig
    ("Scimitar"), die Stufe nicht ("Refined" statt "Viperstrike"). Der zweite
    Aufruf sieht statt tausend Namen nur noch die paar Dutzend seiner Art —
    und damit ist die Stufe die einzige Frage, die offenbleibt.
    """
    kategorien = sorted({katalog.kategorie(n) for n in katalog.namen()
                         if katalog.kategorie(n)})
    system = ("You identify items from the game Idle Clans by their inventory "
              "icon.\nAnswer with exactly one word copied verbatim from the "
              "CATEGORIES list below. No explanation.\n\nCATEGORIES:\n"
              + "\n".join(kategorien))
    ok, antwort, _ms = analyze_image(
        img=bild, provider=config.llm_provider, endpoint=config.llm_endpoint,
        model=modell, prompt="Which category is this item?",
        system_prompt=system, timeout=max(config.llm_timeout, 120),
        max_tokens=16)
    if not ok:
        return None, (TIMEOUT if str(antwort).startswith("Timeout") else str(antwort))
    art = clean_boss_name(antwort)
    passend = {k.casefold(): k for k in kategorien}.get(art.casefold())
    if passend is None:
        # Eine erfundene Art ist kein Ergebnis: die zweite Frage haette dann
        # gar keine Kandidaten. Lieber sagen, woran es lag.
        return None, f"unbekannte Art '{art}'"
    eng = [n for n in katalog.namen() if katalog.kategorie(n) == passend]
    return frage_einstufig(bild, eng, config, modell)


def mit_stimmen(frage, stimmen: int) -> tuple:
    """Mehrfach fragen und die Mehrheit nehmen.

    Bei `temperature 0` kommt zwar immer dasselbe heraus — die Bildkodierung
    und das Sampling der Server sind aber nicht bitgleich, und ein Modell, das
    schwankt, ist eine andere Auskunft als eines, das konsequent danebenliegt.
    Genau das misst dieser Schalter.
    """
    namen, gruende = [], []
    for _ in range(stimmen):
        name, grund = frage()
        if name:
            namen.append(name)
        else:
            gruende.append(grund)
    if not namen:
        return None, (gruende[0] if gruende else "")
    return Counter(namen).most_common(1)[0][0], ""


# ---------------------------------------------------------------- Lauf

def aufwaermen(bild, config, modell: str) -> float:
    """Ein Aufruf vor der Messung — er misst das Laden, nicht die Frage."""
    start = time.time()
    suggest_item_name_grund(bild, provider=config.llm_provider,
                            endpoint=config.llm_endpoint, model=modell,
                            timeout=300, candidates=["Godlike Bow"])
    return time.time() - start


def lauf(proben: list, katalog, config, args, modell: str) -> dict:
    """Eine Variante ueber alle Proben. Gibt Zahlen zurueck, druckt Zeilen."""
    kandidaten = katalog.namen()
    treffer, offen, zeiten, fehler = 0, 0, [], []
    for wahrheit, bild in proben:
        start = time.time()
        if args.zweistufig:
            def einmal():
                return frage_zweistufig(bild, katalog, config, modell)
        else:
            def einmal():
                return frage_einstufig(bild, kandidaten, config, modell)
        if args.stimmen > 1:
            name, grund = mit_stimmen(einmal, args.stimmen)
        else:
            name, grund = einmal()
        dauer = time.time() - start
        zeiten.append(dauer)
        richtig = bool(name) and name.casefold() == wahrheit.casefold()
        treffer += 1 if richtig else 0
        if not name:
            offen += 1
        if not richtig:
            fehler.append((wahrheit, name or f"— ({grund})"))
        marke = "OK " if richtig else "-- "
        print(f"    {marke} {wahrheit:<26} -> {str(name):<26} ({dauer:.1f}s)")
    return {
        "treffer": treffer, "gesamt": len(proben), "ohne": offen,
        "sekunden": sum(zeiten) / len(zeiten) if zeiten else 0.0,
        "fehler": fehler,
    }


def geladene_modelle(config) -> list:
    """Was der Server gerade anbietet — fuer `--alle-modelle`."""
    import json as _json
    import urllib.request
    ziel = config.llm_endpoint or test_endpoint_for(config.llm_provider)
    if config.llm_endpoint:
        ziel = chat_endpoint(config.llm_provider).replace(
            "/chat/completions", "/models")
    try:
        with urllib.request.urlopen(ziel, timeout=10) as antwort:
            roh = _json.loads(antwort.read().decode("utf-8"))
    except Exception as e:                       # noqa: BLE001 — Auskunft, kein Absturz
        print(f"[WARN] Modell-Liste nicht lesbar: {e}")
        return []
    if config.llm_provider == "ollama":
        return [m.get("name") for m in roh.get("models", []) if m.get("name")]
    return [m.get("id") for m in roh.get("data", []) if m.get("id")]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Misst die LLM-Benennung gegen den eigenen Bestand.")
    p.add_argument("--scan", default="", help="Scan-Datei (Standard: die zuletzt bearbeitete)")
    p.add_argument("--bild", choices=BILDQUELLEN, default="vorlage",
                   help="vorlage = gelerntes Template, grund = ohne Alpha, "
                        "slot = Ausschnitt aus dem gemerkten Bild")
    p.add_argument("--modell", default="", help="Modellname (Standard: aus config.json)")
    p.add_argument("--alle-modelle", action="store_true",
                   help="jedes Modell des Servers nacheinander")
    p.add_argument("--zweistufig", action="store_true",
                   help="erst die Art fragen, dann nur deren Namen anbieten")
    p.add_argument("--stimmen", type=int, default=1, help="mehrfach fragen, Mehrheit nehmen")
    p.add_argument("--reasoning", action="store_true", help="Denkschritte zulassen")
    p.add_argument("--limit", type=int, default=14, help="wie viele Proben (Standard: 14)")
    p.add_argument("--ohne-aufwaermen", action="store_true",
                   help="nicht vorheizen — dann misst die erste Zahl das Modell-Laden")
    args = p.parse_args(argv)

    config = load_config()
    if args.reasoning:
        config.llm_reasoning = True
    katalog = lade_katalog(config.scan_catalog_file)
    if not katalog:
        raise SystemExit("Kein Katalog — Einstellungen → 'Item-Katalog', "
                         "oder python tools/katalog.py")

    scan = lade_scan(finde_scan(args.scan))
    if args.bild == "slot":
        proben = proben_aus_slots(scan, katalog, config, args.limit)
    else:
        proben = proben_aus_vorlagen(scan, katalog, args.bild == "grund", args.limit)
    if not proben:
        raise SystemExit(
            "Keine Proben: kein Item dieses Scans traegt einen Namen aus dem "
            "Katalog. Erst benennen (Studio → Scans → „Alle … benennen“).")

    print(f"Scan '{scan['name']}' · {len(proben)} Proben · Bild: {args.bild}"
          + (" · zweistufig" if args.zweistufig else "")
          + (f" · {args.stimmen} Stimmen" if args.stimmen > 1 else "")
          + (" · Reasoning" if args.reasoning else ""))
    if args.bild != "slot":
        print("  \033[90mDer Goldstandard sind die gespeicherten Namen — sie "
              "beweisen nur, dass sie ECHTE Namen sind, nicht dass sie am "
              "richtigen Item stehen. --bild slot misst gegen die "
              "Template-Erkennung.\033[0m")

    modelle = geladene_modelle(config) if args.alle_modelle else [
        args.modell or config.llm_model]
    ergebnisse = {}
    for modell in modelle:
        print(f"\n=== {modell} ===")
        if not args.ohne_aufwaermen:
            print(f"  \033[90maufwaermen … {aufwaermen(proben[0][1], config, modell):.0f}s"
                  "\033[0m")
        ergebnisse[modell] = lauf(proben, katalog, config, args, modell)
        e = ergebnisse[modell]
        print(f"  {e['treffer']}/{e['gesamt']} richtig, "
              f"{e['sekunden']:.1f}s je Item"
              + (f", {e['ohne']} ohne Antwort" if e["ohne"] else ""))

    if len(ergebnisse) > 1:
        print("\nZUSAMMENFASSUNG")
        for modell, e in sorted(ergebnisse.items(),
                                key=lambda kv: -kv[1]["treffer"]):
            print(f"  {e['treffer']:>3}/{e['gesamt']}  {e['sekunden']:>6.1f}s  {modell}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
