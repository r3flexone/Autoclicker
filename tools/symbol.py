"""Schreibt das Programm-Symbol als PNG und ICO — für Verknüpfungen unter Windows.

    python tools/symbol.py                 -> symbol/ mit PNGs und autoclicker.ico
    python tools/symbol.py --ziel C:\\Bilder
    python tools/symbol.py --groessen 256,512

Das Symbol im Fenster und in der Taskleiste setzt die App selbst
(`winapi.setze_fenster_symbol`) — dafür braucht es diese Dateien **nicht**. Sie
sind für alles, was Windows aus einer Datei nimmt: eine Verknüpfung auf dem
Desktop, ein angehefteter Eintrag, ein Ordnerbild.

Gerastert wird direkt aus derselben SVG-Datei, die auch die Weboberfläche zeigt
(`autoclicker/symbol.py` übernimmt das ohne Zusatzbibliothek). Deshalb liegt
hier keine fertige Binärdatei im Repo: sie wäre eine Kopie, die beim nächsten
Logo-Entwurf wieder veralten könnte.

Ohne Pillow läuft es trotzdem — PNG und ICO werden dann von Hand
zusammengesetzt (beides sind einfache Formate, wenn man sich auf unkomprimiert
bzw. eingebettete PNGs beschränkt). Das ist kein Selbstzweck: wer sich ein
Symbol für eine Verknüpfung holt, soll dafür nichts installieren müssen.
"""

import argparse
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoclicker.symbol import punkte              # noqa: E402

# Was Windows tatsächlich anfragt: 16 (Titelleiste), 32 (ALT+TAB), 48 (grosse
# Kacheln, 150 % Skalierung), 256 (Verknüpfung, Explorer-Vorschau). Die Grössen
# dazwischen rechnet Windows sich selbst.
GROESSEN = (16, 32, 48, 64, 128, 256)


def png_bytes(kante: int) -> bytes:
    """Ein PNG mit Alphakanal, ohne Pillow zusammengesetzt."""
    roh = bytearray()
    for zeile in punkte(kante):
        roh.append(0)                              # Filter 0 = keiner
        for r, g, b, a in zeile:
            roh += bytes((r, g, b, a))

    def stueck(art: bytes, daten: bytes) -> bytes:
        return (struct.pack(">I", len(daten)) + art + daten
                + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + stueck(b"IHDR", struct.pack(">IIBBBBB", kante, kante, 8, 6, 0, 0, 0))
            + stueck(b"IDAT", zlib.compress(bytes(roh), 9))
            + stueck(b"IEND", b""))


def ico_bytes(groessen=GROESSEN) -> bytes:
    """Eine ICO-Datei mit mehreren Grössen, jede als eingebettetes PNG.

    Windows nimmt PNG-Einträge seit Vista; das spart das BMP-Format mit seiner
    doppelten Höhe und der Maske. 256 steht im Verzeichnis als **0** — ein Byte
    fasst nur bis 255, und 0 heisst dort „256".
    """
    bilder = [png_bytes(k) for k in groessen]
    kopf = struct.pack("<HHH", 0, 1, len(bilder))
    versatz = len(kopf) + 16 * len(bilder)
    verzeichnis = b""
    for kante, bild in zip(groessen, bilder):
        verzeichnis += struct.pack("<BBBBHHII", kante % 256, kante % 256, 0, 0,
                                   1, 32, len(bild), versatz)
        versatz += len(bild)
    return kopf + verzeichnis + b"".join(bilder)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ziel", default="symbol", help="Ordner für die Dateien")
    p.add_argument("--groessen", default=",".join(str(g) for g in GROESSEN),
                   help="Kantenlängen der PNGs, mit Komma getrennt")
    args = p.parse_args()

    try:
        groessen = tuple(sorted({int(g) for g in args.groessen.split(",") if g.strip()}))
    except ValueError:
        print("Die Grössen müssen Zahlen sein, z. B. --groessen 32,256")
        return 2
    if not groessen or min(groessen) < 8 or max(groessen) > 1024:
        print("Grössen zwischen 8 und 1024 angeben.")
        return 2

    ziel = Path(args.ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    for kante in groessen:
        datei = ziel / f"autoclicker-{kante}.png"
        datei.write_bytes(png_bytes(kante))
        print(f"  {datei}")
    ico = ziel / "autoclicker.ico"
    ico.write_bytes(ico_bytes(tuple(k for k in groessen if k <= 256)))
    print(f"  {ico}")
    print("\nVerknüpfung: Rechtsklick -> Eigenschaften -> Anderes Symbol -> "
          f"{ico.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
