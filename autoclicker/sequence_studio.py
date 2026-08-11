"""
Einstiegspunkt für das Sequenz-Studio (läuft als eigener Subprocess).

Aufruf:
    python -m autoclicker.sequence_studio "<Sequenz-Name>"
    python -m autoclicker.sequence_studio            # zuletzt bearbeitete Sequenz

Wird vom Hotkey-Handler (handle_sequence_studio in handlers.py) per subprocess.Popen
gestartet, damit der Fenster-Event-Loop nicht mit der Windows-Hotkey-Message-Pump
des Hauptprozesses kollidiert. Liest/schreibt sequences/<name>.json direkt; nach dem
Speichern lädt man im Hauptprozess mit CTRL+ALT+L neu.

Die Oberfläche ist eine Webseite (`editors/sequence_studio/web/index.html`) in einem
pywebview-Fenster, die Verbindung dorthin ist `StudioBridge` — mehr gibt es nicht.
Auf Windows läuft das über WebView2, das bei Windows 10/11 in der Regel vorhanden
ist; sonst installiert man einmalig Microsofts „Evergreen Runtime".
"""

import sys
import time
from pathlib import Path

from .config import SEQUENCES_DIR
from .models import Sequence
from .persistence import (
    ensure_sequences_dir, list_available_sequences, load_sequence_file,
)
from .utils import sanitize_filename, col

WINDOW_TITLE = "Sequenz-Studio"
INDEX = Path(__file__).parent / "editors" / "sequence_studio" / "web" / "index.html"


def zuletzt_bearbeitet() -> "Path | None":
    """Die zuletzt geänderte Sequenzdatei, oder None wenn es keine gibt.

    Der Ersatz für ein „zuletzt geöffnet"-Gedächtnis, und zwar bewusst: dafür
    müsste jemand mitschreiben, und keiner der beiden Prozesse kann das gefahrlos.
    Die `config.json` gehört dem Hauptprozess — schriebe das Studio dort hinein,
    überschriebe der nächste `save_config()` im Hauptprozess den Eintrag mit
    seinem älteren Stand im Speicher. Eine eigene Merkdatei wäre eine Datei mehr
    für einen Wert, den das Dateisystem schon kennt.

    Der Unterschied zu „zuletzt geöffnet": eine Sequenz, die man nur angesehen
    und nicht gespeichert hat, zählt hier nicht. Wer nichts geändert hat, hat
    aber auch nichts, wo er weitermachen müsste.
    """
    neueste, zeit = None, -1.0
    for _, pfad in list_available_sequences():
        try:
            m = pfad.stat().st_mtime
        except OSError:
            continue
        if m > zeit:
            neueste, zeit = pfad, m
    return neueste


def _resolve_sequence(name: str) -> tuple[Sequence, Path]:
    """Lädt die Sequenz mit gegebenem Namen, sonst die zuletzt bearbeitete.

    Eine neue Sequenz landet **nie** auf einer vorhandenen Datei. Der Name IN der
    Datei muss nicht der Dateiname sein — `all_dayli.json` enthält „all dayli" —,
    und ohne diese Regel bekam `... sequence_studio all_dayli` eine leere Sequenz,
    die auf der vollen Datei lag: ein Druck auf „Speichern" und 50 Schritte waren
    weg. Deshalb erst über den Dateinamen nachfassen, und wenn auch das nichts
    lädt, auf einen freien Pfad ausweichen.

    Ohne Namen (Studio aus dem Hauptprozess ohne aktive Sequenz, oder direkt von
    der Kommandozeile) kommt die zuletzt bearbeitete Sequenz — ein leeres Fenster
    ist fast nie das, was man wollte. Erst wenn es gar keine gibt, wird eine neue
    angelegt.
    """
    ensure_sequences_dir()
    if name:
        for seq_name, path in list_available_sequences():
            if seq_name == name:
                seq = load_sequence_file(path)
                if seq:
                    return seq, path
    else:
        letzte = zuletzt_bearbeitet()
        if letzte is not None:
            seq = load_sequence_file(letzte)
            if seq:
                return seq, letzte

    base = name or f"Sequenz_{int(time.time())}"
    path = Path(SEQUENCES_DIR) / f"{sanitize_filename(base)}.json"
    if path.exists():
        seq = load_sequence_file(path)
        if seq:
            return seq, path
        # Datei da, aber nicht ladbar: kaputt ist nicht leer. Draufschreiben
        # hiesse, den einzigen Rest wegzuwerfen, den man noch reparieren kann.
        base = f"{base}_{int(time.time())}"
        path = Path(SEQUENCES_DIR) / f"{sanitize_filename(base)}.json"
    return Sequence(name=base), path


def _beim_schliessen(bridge) -> None:
    """Rettet ungespeicherte Änderungen, wenn das Fenster geschlossen wird.

    Das X schliesst sofort — gefragt wird hier nicht mehr, sondern **gesichert**.
    Der Rückfrage-Dialog in der Oberfläche schützt Laden und Neu; das Schliessen
    ging bisher daran vorbei und warf die Arbeit still weg, obwohl der Stern im
    Titel die ganze Zeit sagte, dass etwas offen ist.
    """
    ziel = bridge.rettung_schreiben()
    if ziel is not None:
        print(f"\nUngespeicherte Aenderungen gesichert: {ziel}")
        print("  Zum Weiterarbeiten in den sequences/-Ordner kopieren.")


def _haenge_schliesser_an(fenster, bridge) -> None:
    """Hängt `_beim_schliessen` ans Fenster — über beide pywebview-Schreibweisen.

    Bis pywebview 3.5 hiessen die Ereignisse `fenster.closing`, danach
    `fenster.events.closing`. Beides zu versuchen kostet drei Zeilen; ohne den
    Haken geht die Rettungskopie verloren, und zwar genau dann, wenn man sie
    braucht.
    """
    for besitzer in (getattr(fenster, "events", None), fenster):
        ereignis = getattr(besitzer, "closing", None) if besitzer is not None else None
        if ereignis is not None and hasattr(ereignis, "__iadd__"):
            ereignis += lambda: _beim_schliessen(bridge)
            return


def main(argv: list[str]) -> int:
    seq_name = argv[1] if len(argv) > 1 else ""

    try:
        import webview
    except ImportError:
        print("Das Sequenz-Studio braucht pywebview. Installieren mit:")
        print("    pip install pywebview")
        return 1

    if not INDEX.exists():
        print(f"Die Oberflaeche fehlt: {INDEX}")
        return 1

    seq, path = _resolve_sequence(seq_name)

    from .editors.sequence_studio.bridge import StudioBridge
    bridge = StudioBridge(seq, path, SEQUENCES_DIR)

    fenster = webview.create_window(
        f"{WINDOW_TITLE} – {seq.name}",
        url=INDEX.as_uri(),
        js_api=bridge,
        width=1600,
        height=1000,
        background_color="#0C0F14",
    )
    _haenge_schliesser_an(fenster, bridge)
    try:
        # gui=None: pywebview nimmt, was da ist (Windows: WebView2/EdgeChromium).
        webview.start()
    except KeyboardInterrupt:
        # Beendet man den Hauptprozess mit CTRL+C, bekommt dieser Subprozess das
        # Signal mit (gleiche Konsolengruppe). Ohne diesen Zweig landet ein
        # Traceback in der Konsole, der wie ein Absturz aussieht, obwohl nur
        # zugemacht wurde.
        print(f"\n{col('[SEQUENZ-STUDIO]', 'cyan')} Abgebrochen.")
        return 0

    _schlussmeldung(bridge)
    return 0


def _schlussmeldung(bridge) -> None:
    """Sagt beim Zumachen, was passiert ist — und was jetzt noch zu tun ist.

    Die Meldung landet in der Konsole des HAUPTPROZESSES (der Subprozess erbt sie),
    also genau dort, wo vorher „Sequenz-Studio geöffnet" stand. Ohne sie bleibt das
    Öffnen als letzte Zeile stehen und man weiss nicht, ob das Fenster noch lebt.

    Der Hinweis aufs Neuladen ist der eigentliche Zweck: der Hauptprozess hält
    seinen eigenen Stand im Speicher und merkt von der geschriebenen Datei nichts.
    Deshalb erscheint er nur, wenn wirklich gespeichert wurde — sonst wäre es eine
    Aufforderung, etwas nachzuladen, das sich gar nicht geändert hat.
    """
    tag = col("[SEQUENZ-STUDIO]", "cyan")
    if getattr(bridge, "_gespeichert", False):
        print(f"\n{tag} Geschlossen — '{bridge.board.name}' gespeichert.")
        print(f"     Im Hauptprozess mit {col('CTRL+ALT+L', 'yellow')} neu laden.")
    else:
        print(f"\n{tag} Geschlossen — nichts gespeichert.")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
