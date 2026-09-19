#!/usr/bin/env python3
"""Misst die LLM-Benennung gegen den eigenen Bestand — Variante gegen Variante.

    python tools/llm_bench.py                      # Standard: Vorlagen, einstufig
    python tools/llm_bench.py --model qwen/qwen3.8-27b
    python tools/llm_bench.py --image slot          # Ausschnitt statt Vorlage
    python tools/llm_bench.py --two-stage         # erst die Art, dann der Name
    python tools/llm_bench.py --votes 3          # dreimal fragen, Mehrheit
    python tools/llm_bench.py --reasoning
    python tools/llm_bench.py --all-models       # jedes geladene Modell nacheinander
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
dessen eigene Fehler. Mit `--image slot` ist der Bezug ein anderer und
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
from autoclicker.catalog import load_catalog                        # noqa: E402
from autoclicker.llm_vision import (                                # noqa: E402
    TIMEOUT, analyze_image, chat_endpoint, clean_boss_name,
    suggest_item_name_with_reason, test_endpoint_for,
)

IMAGE_SOURCES = ("template", "background", "slot")
NEUTRAL = (38, 42, 52)      # der Ton der Studio-Flaeche, nicht Schwarz: ein
                            # ausgeschnittenes Item auf Schwarz ist ein anderer
                            # Kontrast als eines in seinem Slot.


class ConfigOnly:
    """`state`-Stellvertreter fuer `_check_profile_match`.

    Die Erkennung braucht vom State nichts als die Config. Nachgebaut statt
    das private `_NurConfig` des Studios zu importieren: ein Werkzeug, das an
    internen Namen haengt, bricht beim naechsten Umbau — und drei Zeilen sind
    billiger als diese Kopplung.
    """

    def __init__(self, config):
        self.config = config


# ---------------------------------------------------------------- Bestand

def find_scan(path: str = "") -> Path:
    """Die Scan-Datei — angegeben oder die zuletzt bearbeitete.

    Dieselbe Regel wie `last_edited()` im Studio: ein echtes „zuletzt
    geoeffnet" muesste jemand mitschreiben, und das Dateisystem weiss es schon.
    """
    if path:
        return Path(path)
    candidates = sorted(Path("sequences").glob("*/item_scans/*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    candidates = [p for p in candidates if p.name != "bibliothek.json"]
    if not candidates:
        raise SystemExit("Kein Item-Scan gefunden — --scan angeben.")
    return candidates[0]


def load_scan(path: Path) -> dict:
    """Rohdaten des Scans plus die Pfade, die daran haengen."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "name": data.get("name") or path.stem,
        "items": data.get("items") or {},
        "slots": data.get("slots") or {},
        "tolerance": int(data.get("color_tolerance") or 30),
        "templates": path.parent.parent / "templates",
        # `sequences/<name>/bilder/<scan>.png` — neben `item_scans/`, nicht
        # darin (`_photo_path()` im Studio: `filepath.parent / "bilder"`).
        "image": path.parent.parent / "bilder" / (path.stem + ".png"),
    }


def load_photo(path: Path):
    """Das gemerkte Bild samt Ursprung — `(Bild, links, oben)` oder `None`.

    Der Ursprung des virtuellen Desktops steht IM PNG (Text-Chunk), nicht in
    einer Datei daneben. Ohne ihn waeren alle Slot-Regionen um einen Monitor
    verschoben.
    """
    from PIL import Image
    try:
        image = Image.open(path)
        image.load()
    except (OSError, ValueError):
        return None
    try:
        return image, int(image.info["left"]), int(image.info["top"])
    except (KeyError, TypeError, ValueError):
        return image, 0, 0


# ---------------------------------------------------------------- Proben

def samples_from_templates(scan: dict, catalog, background: bool, limit: int) -> list:
    """`(Wahrheit, Bild)` je Item mit Vorlage, dessen Name im Katalog steht."""
    from PIL import Image
    samples = []
    for name, entry in scan["items"].items():
        if len(samples) >= limit:
            break
        file = entry.get("template")
        if not file or not catalog.match(name):
            continue
        path = scan["templates"] / file
        try:
            with Image.open(path) as raw:
                image = raw.copy()
        except (OSError, ValueError):
            continue
        samples.append((catalog.match(name), on_background(image) if background else image))
    return samples


def on_background(image, color=NEUTRAL):
    """Alpha auf einen neutralen Grund legen, statt es mitzuschicken."""
    from PIL import Image
    if image.mode != "RGBA":
        return image.convert("RGB")
    surface = Image.new("RGB", image.size, color)
    surface.paste(image, mask=image.getchannel("A"))
    return surface


def samples_from_slots(scan: dict, catalog, config, limit: int) -> list:
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

    photo = load_photo(scan["image"])
    if photo is None:
        raise SystemExit(f"Kein gemerktes Bild ({scan['image']}) — "
                         "im Scans-Reiter einmal aufnehmen, oder --image template.")
    image, left, top = photo
    profile = [_item_from_dict(e, n) for n, e in scan["items"].items()]
    stand_in = ConfigOnly(config)
    samples = []
    for slot in scan["slots"].values():
        if len(samples) >= limit:
            break
        region = slot.get("scan_region")
        if not region or len(region) != 4:
            continue
        box = (region[0] - left, region[1] - top,
                  region[2] - left, region[3] - top)
        if box[0] < 0 or box[1] < 0:
            continue
        if box[2] > image.width or box[3] > image.height:
            continue
        crop = image.crop(box).convert("RGB")
        for item in profile:
            if not catalog.match(item.name):
                continue
            if _check_profile_match(item, crop, scan["tolerance"],
                                    stand_in, False,
                                    template_root=scan["templates"]):
                samples.append((catalog.match(item.name), crop))
                break
    return samples


# ---------------------------------------------------------------- Fragen

def ask_single_stage(image, candidates: list, config, model: str) -> tuple:
    """Ein Aufruf mit der ganzen Namensliste — der Weg, den das Studio geht."""
    return suggest_item_name_with_reason(
        image, provider=config.llm_provider, endpoint=config.llm_endpoint,
        model=model, timeout=max(config.llm_timeout, 120),
        candidates=candidates)


def ask_two_stage(image, catalog, config, model: str) -> tuple:
    """Erst die Art, dann der Name aus NUR dieser Art.

    Gegen den Fehler, der uebrig bleibt: die Art trifft das Modell zuverlaessig
    ("Scimitar"), die Stufe nicht ("Refined" statt "Viperstrike"). Der zweite
    Aufruf sieht statt tausend Namen nur noch die paar Dutzend seiner Art —
    und damit ist die Stufe die einzige Frage, die offenbleibt.
    """
    categories = sorted({catalog.category(n) for n in catalog.names()
                         if catalog.category(n)})
    system = ("You identify items from the game Idle Clans by their inventory "
              "icon.\nAnswer with exactly one word copied verbatim from the "
              "CATEGORIES list below. No explanation.\n\nCATEGORIES:\n"
              + "\n".join(categories))
    ok, answer, _ms = analyze_image(
        img=image, provider=config.llm_provider, endpoint=config.llm_endpoint,
        model=model, prompt="Which category is this item?",
        system_prompt=system, timeout=max(config.llm_timeout, 120),
        max_tokens=16)
    if not ok:
        return None, (TIMEOUT if str(answer).startswith("Timeout") else str(answer))
    kind = clean_boss_name(answer)
    matching = {k.casefold(): k for k in categories}.get(kind.casefold())
    if matching is None:
        # Eine erfundene Art ist kein Ergebnis: die zweite Frage haette dann
        # gar keine Kandidaten. Lieber sagen, woran es lag.
        return None, f"unbekannte Art '{kind}'"
    narrow = [n for n in catalog.names() if catalog.category(n) == matching]
    return ask_single_stage(image, narrow, config, model)


def with_votes(ask_fn, votes: int) -> tuple:
    """Mehrfach fragen und die Mehrheit nehmen.

    Bei `temperature 0` kommt zwar immer dasselbe heraus — die Bildkodierung
    und das Sampling der Server sind aber nicht bitgleich, und ein Modell, das
    schwankt, ist eine andere Auskunft als eines, das konsequent danebenliegt.
    Genau das misst dieser Schalter.
    """
    names, reasons = [], []
    for _ in range(votes):
        name, reason = ask_fn()
        if name:
            names.append(name)
        else:
            reasons.append(reason)
    if not names:
        return None, (reasons[0] if reasons else "")
    return Counter(names).most_common(1)[0][0], ""


# ---------------------------------------------------------------- Lauf

def warm_up(image, config, model: str) -> float:
    """Ein Aufruf vor der Messung — er misst das Laden, nicht die Frage."""
    start = time.time()
    suggest_item_name_with_reason(image, provider=config.llm_provider,
                            endpoint=config.llm_endpoint, model=model,
                            timeout=300, candidates=["Godlike Bow"])
    return time.time() - start


def run(samples: list, catalog, config, args, model: str) -> dict:
    """Eine Variante ueber alle Proben. Gibt Zahlen zurueck, druckt Zeilen."""
    candidates = catalog.names()
    match, remaining, times, error = 0, 0, [], []
    for truth, image in samples:
        start = time.time()
        if args.two_stage:
            def once():
                return ask_two_stage(image, catalog, config, model)
        else:
            def once():
                return ask_single_stage(image, candidates, config, model)
        if args.votes > 1:
            name, reason = with_votes(once, args.votes)
        else:
            name, reason = once()
        duration = time.time() - start
        times.append(duration)
        correct = bool(name) and name.casefold() == truth.casefold()
        match += 1 if correct else 0
        if not name:
            remaining += 1
        if not correct:
            error.append((truth, name or f"— ({reason})"))
        badge = "OK " if correct else "-- "
        print(f"    {badge} {truth:<26} -> {str(name):<26} ({duration:.1f}s)")
    return {
        "match": match, "total": len(samples), "without": remaining,
        "seconds": sum(times) / len(times) if times else 0.0,
        "error": error,
    }


def loaded_models(config) -> list:
    """Was der Server gerade anbietet — fuer `--all-models`."""
    import json as _json
    import urllib.request
    target = config.llm_endpoint or test_endpoint_for(config.llm_provider)
    if config.llm_endpoint:
        target = chat_endpoint(config.llm_provider).replace(
            "/chat/completions", "/models")
    try:
        with urllib.request.urlopen(target, timeout=10) as answer:
            raw = _json.loads(answer.read().decode("utf-8"))
    except Exception as e:                       # noqa: BLE001 — Auskunft, kein Absturz
        print(f"[WARN] Modell-Liste nicht lesbar: {e}")
        return []
    if config.llm_provider == "ollama":
        return [m.get("name") for m in raw.get("models", []) if m.get("name")]
    return [m.get("id") for m in raw.get("data", []) if m.get("id")]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Misst die LLM-Benennung gegen den eigenen Bestand.")
    p.add_argument("--scan", default="", help="Scan-Datei (Standard: die zuletzt bearbeitete)")
    p.add_argument("--image", choices=IMAGE_SOURCES, default="template",
                   help="template = gelerntes Template, background = ohne Alpha, "
                        "slot = Ausschnitt aus dem gemerkten Bild")
    p.add_argument("--model", default="", help="Modellname (Standard: aus config.json)")
    p.add_argument("--all-models", action="store_true",
                   help="jedes Modell des Servers nacheinander")
    p.add_argument("--two-stage", action="store_true",
                   help="erst die Art fragen, dann nur deren Namen anbieten")
    p.add_argument("--votes", type=int, default=1, help="mehrfach fragen, Mehrheit nehmen")
    p.add_argument("--reasoning", action="store_true", help="Denkschritte zulassen")
    p.add_argument("--limit", type=int, default=14, help="wie viele Proben (Standard: 14)")
    p.add_argument("--no-warmup", action="store_true",
                   help="nicht vorheizen — dann misst die erste Zahl das Modell-Laden")
    args = p.parse_args(argv)

    config = load_config()
    if args.reasoning:
        config.llm_reasoning = True
    catalog = load_catalog(config.scan_catalog_file)
    if not catalog:
        raise SystemExit("Kein Katalog — Einstellungen → 'Item-Katalog', "
                         "oder python tools/catalog.py")

    scan = load_scan(find_scan(args.scan))
    if args.image == "slot":
        samples = samples_from_slots(scan, catalog, config, args.limit)
    else:
        samples = samples_from_templates(scan, catalog, args.image == "background", args.limit)
    if not samples:
        raise SystemExit(
            "Keine Proben: kein Item dieses Scans traegt einen Namen aus dem "
            "Katalog. Erst benennen (Studio → Scans → „Alle … benennen“).")

    print(f"Scan '{scan['name']}' · {len(samples)} Proben · Bild: {args.image}"
          + (" · zweistufig" if args.two_stage else "")
          + (f" · {args.votes} Stimmen" if args.votes > 1 else "")
          + (" · Reasoning" if args.reasoning else ""))
    if args.image != "slot":
        print("  \033[90mDer Goldstandard sind die gespeicherten Namen — sie "
              "beweisen nur, dass sie ECHTE Namen sind, nicht dass sie am "
              "richtigen Item stehen. --image slot misst gegen die "
              "Template-Erkennung.\033[0m")

    models = loaded_models(config) if args.all_models else [
        args.model or config.llm_model]
    results = {}
    for model in models:
        print(f"\n=== {model} ===")
        if not args.no_warmup:
            print(f"  \033[90maufwaermen … {warm_up(samples[0][1], config, model):.0f}s"
                  "\033[0m")
        results[model] = run(samples, catalog, config, args, model)
        e = results[model]
        print(f"  {e['match']}/{e['total']} richtig, "
              f"{e['seconds']:.1f}s je Item"
              + (f", {e['without']} ohne Antwort" if e["without"] else ""))

    if len(results) > 1:
        print("\nZUSAMMENFASSUNG")
        for model, e in sorted(results.items(),
                                key=lambda kv: -kv[1]["match"]):
            print(f"  {e['match']:>3}/{e['total']}  {e['seconds']:>6.1f}s  {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
