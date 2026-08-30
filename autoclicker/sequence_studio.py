"""Einstiegspunkt für das Sequenz-Studio (läuft als eigener Subprocess).

Aufruf:
    python -m autoclicker.sequence_studio "<Sequenz-Name>"
    python -m autoclicker.sequence_studio            # zuletzt geöffnete/gespeicherte
    python -m autoclicker.sequence_studio "" --scans # Reiter „Scans" vorgewählt

Eigener Prozess, damit der Fenster-Event-Loop nicht mit der Hotkey-Message-
Pump kollidiert. Liest/schreibt sequences/<name>/sequence.json direkt; danach im
Hauptprozess CTRL+ALT+L. Die Oberfläche ist eine Webseite
(`editors/sequence_studio/web/index.html`), die Verbindung `StudioBridge`.
"""

import json
import sys
import time
from pathlib import Path

from .config import SEQUENCES_DIR, STUDIO_LAST_SEQUENCE_FILE
from .models import Sequence
from .persistence import (
    ensure_sequences_dir, list_available_sequences, load_sequence_file,
    sequence_file,
)
from .utils import sanitize_filename, atomic_write, compact_json, col

WINDOW_TITLE = "Sequenz-Studio"
INDEX = Path(__file__).parent / "editors" / "sequence_studio" / "web" / "index.html"


def zuletzt_bearbeitet() -> "Path | None":
    """Die zuletzt geöffnete oder gespeicherte Sequenz, oder None.

    Der Studio-Merker trägt den Zeitpunkt des letzten Öffnens/Speicherns. Eine
    danach von einem anderen Programmteil gespeicherte sequence.json gewinnt
    trotzdem — entscheidend ist das jüngere der beiden Ereignisse.
    """
    verfuegbar = list_available_sequences()
    neueste, zeit = None, -1
    for _, pfad in verfuegbar:
        try:
            m = pfad.stat().st_mtime_ns
        except OSError:
            continue
        if m > zeit:
            neueste, zeit = pfad, m

    marker = Path(STUDIO_LAST_SEQUENCE_FILE)
    try:
        daten = json.loads(marker.read_text(encoding="utf-8"))
        ordner = str(daten.get("ordner") or "") if isinstance(daten, dict) else ""
        gemerkt = next((pfad for _, pfad in verfuegbar
                        if pfad.parent.name == ordner), None)
        if gemerkt is not None and marker.stat().st_mtime_ns >= zeit:
            return gemerkt
    except (OSError, ValueError, TypeError):
        pass
    return neueste


def merke_zuletzt_verwendet(pfad) -> bool:
    """Merkt eine vorhandene Sequenz als zuletzt geöffnet/gespeichert."""
    pfad = Path(pfad)
    if not pfad.is_file():
        return False
    try:
        atomic_write(Path(STUDIO_LAST_SEQUENCE_FILE), compact_json({
            "ordner": pfad.parent.name,
        }))
        return True
    except OSError:
        return False


def _resolve_sequence(name: str) -> tuple[Sequence, Path]:
    """Lädt die Sequenz mit gegebenem Namen, sonst die zuletzt verwendete.

    Eine neue Sequenz landet NIE auf einer vorhandenen Datei: der Name IN der
    Datei muss nicht der Dateiname sein, und ohne diese Regel lag eine leere
    Sequenz auf der vollen Datei. Ohne Namen kommt die zuletzt geöffnete oder
    gespeicherte — ein leeres Fenster ist fast nie das, was man wollte.
    """
    ensure_sequences_dir()
    if name:
        for seq_name, path in list_available_sequences():
            if seq_name == name or path.parent.name == sanitize_filename(name):
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
    path = sequence_file(base)
    if path.exists():
        seq = load_sequence_file(path)
        if seq:
            return seq, path
        # Datei da, aber nicht ladbar: kaputt ist nicht leer. Draufschreiben
        # hiesse, den einzigen Rest wegzuwerfen, den man noch reparieren kann.
        base = f"{base}_{int(time.time())}"
        path = sequence_file(base)
    return Sequence(name=base), path


def _scans_beim_schliessen_speichern(bridge) -> bool:
    """Speichert offene Scan-Änderungen synchron vor dem Fensterschliessen."""
    if not getattr(bridge, "_scan_dirty", False):
        return False

    antwort = bridge.scan_speichern()
    status = antwort.get("status", {}) if isinstance(antwort, dict) else {}
    if status.get("art") == "err":
        print(f"\nItem-Scans konnten nicht gespeichert werden: "
              f"{status.get('text', 'unbekannter Fehler')}")
        return False

    print("\nUngespeicherte Item-Scan-Aenderungen gespeichert.")
    return True


def _beim_schliessen(bridge, beenden_mit_fenster: bool = False) -> None:
    """Sichert ungespeicherte Sequenz- und Scan-Änderungen beim Schliessen."""
    # Zuerst die Klick-Runde: sie haengt im Hauptprozess an einem systemweiten
    # Maus-Hook, und ihre Bedienung steht nur in diesem Fenster. Bleibt sie
    # scharf, rechnet drueben jeder Klick des Nutzers gegen eine Punktliste, die
    # er nirgends mehr sieht. Verworfen, nicht uebernommen: wer zumacht, hat
    # nicht uebernommen.
    try:
        bridge.nachklick_beim_schliessen()
    except Exception:
        pass
    _scans_beim_schliessen_speichern(bridge)

    ziel = bridge.rettung_schreiben()
    if ziel is not None:
        print(f"\nUngespeicherte Aenderungen gesichert: {ziel}")
        print("  Zum Weiterarbeiten in den sequences/-Ordner kopieren.")
    if beenden_mit_fenster and not getattr(bridge, "_beenden_gesendet", False):
        # Nur das automatisch gestartete Hauptfenster besitzt den Hauptprozess.
        # Ein per Hotkey zusätzlich geöffnetes Studio darf ihn beim Schliessen
        # nicht überraschend mitnehmen.
        from .befehl import sende
        bridge._beenden_gesendet = True
        sende("programm_beenden")


def _haenge_schliesser_an(fenster, bridge,
                          beenden_mit_fenster: bool = False) -> None:
    """Hängt `_beim_schliessen` ans Fenster — über beide pywebview-Schreibweisen.

    Bis pywebview 3.5 hiess das Ereignis `fenster.closing`, danach
    `fenster.events.closing`. Ohne den Haken geht die Rettungskopie verloren.
    """
    for besitzer in (getattr(fenster, "events", None), fenster):
        ereignis = getattr(besitzer, "closing", None) if besitzer is not None else None
        if ereignis is not None and hasattr(ereignis, "__iadd__"):
            ereignis += lambda: _beim_schliessen(bridge, beenden_mit_fenster)
            return


def main(argv: list[str]) -> int:
    # `--scans` waehlt nur den Reiter vor; ein leeres erstes Argument ist erlaubt.
    scans = "--scans" in argv[1:]
    beenden_mit_fenster = "--beenden-mit-fenster" in argv[1:]
    stellen = [a for a in argv[1:] if not a.startswith("--")]
    seq_name = stellen[0] if stellen else ""

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
    merke_zuletzt_verwendet(path)

    from .editors.sequence_studio.bridge import StudioBridge
    bridge = StudioBridge(seq, path, SEQUENCES_DIR)
    if scans:
        bridge.start_ansicht = "scans"

    # VOR dem ersten Fenster: sonst sortiert die Taskleiste es unter python.exe
    # ein. Die Titelleiste bekommt ihr Symbol weiter unten - zwei Mechanismen.
    try:
        from .winapi import setze_app_id
        setze_app_id()
    except Exception:          # noqa: BLE001 - eine Kennung ist kein Startgrund
        pass

    # Titel ohne Sequenznamen: der Name steht im Kopf der Oberflaeche, und
    # `setze_fenster_symbol()` findet das Fenster ueber den festen Titel.
    fenster = webview.create_window(
        WINDOW_TITLE,
        url=INDEX.as_uri(),
        js_api=bridge,
        width=1600,
        height=1000,
        background_color="#0C0F14",
    )
    _haenge_schliesser_an(fenster, bridge, beenden_mit_fenster)

    def _nach_dem_start() -> None:
        """Läuft, sobald die GUI-Schleife steht — das Fenster aber noch nicht.

        Deshalb die Frist: zum Zeitpunkt dieses Aufrufs existiert das Fenster nicht,
        und `setze_fenster_symbol()` fiele still auf `False` zurück.
        """
        try:
            from .winapi import setze_fenster_symbol
            setze_fenster_symbol(WINDOW_TITLE, warten=15.0)
        except Exception:      # noqa: BLE001 - ein Symbol ist kein Startgrund
            pass

    try:
        # gui=None: pywebview nimmt, was da ist (Windows: WebView2/EdgeChromium).
        webview.start(_nach_dem_start)
    except KeyboardInterrupt:
        # CTRL+C im Hauptprozess trifft diesen Subprozess mit (gleiche
        # Konsolengruppe); ohne den Zweig saehe das Zumachen wie ein Absturz aus.
        print(f"\n{col('[SEQUENZ-STUDIO]', 'cyan')} Abgebrochen.")
        return 0

    _schlussmeldung(bridge)
    return 0


def _schlussmeldung(bridge) -> None:
    """Sagt beim Zumachen, was passiert ist — und was jetzt noch zu tun ist.

    Landet in der Konsole des Hauptprozesses. Der Hinweis aufs Neuladen ist der
    Zweck und erscheint nur, wenn wirklich gespeichert wurde.
    """
    tag = col("[SEQUENZ-STUDIO]", "cyan")
    if getattr(bridge, "_gespeichert", False):
        print(f"\n{tag} Geschlossen — '{bridge.board.name}' gespeichert.")
        print(f"     Im Hauptprozess mit {col('CTRL+ALT+L', 'yellow')} neu laden.")
    else:
        print(f"\n{tag} Geschlossen — nichts gespeichert.")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
