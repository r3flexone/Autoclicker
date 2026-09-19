"""Schreibt das Programm-Symbol als PNG und ICO — für Verknüpfungen unter Windows.

    python tools/symbol.py                 -> symbol/ mit PNGs und autoclicker.ico
    python tools/symbol.py --target C:\\Bilder
    python tools/symbol.py --sizes 256,512

Fenster und Taskleiste setzt die App selbst; diese Dateien sind für alles, was
Windows aus einer Datei nimmt (Verknüpfung, angehefteter Eintrag, Ordnerbild).

Gerastert wird aus derselben Geometrie wie die Weboberfläche
(`autoclicker/symbol.py`) — deshalb liegt hier keine Binärdatei im Repo, die
beim nächsten Logo-Entwurf veraltet. Ohne Pillow läuft es trotzdem: PNG und ICO
werden dann von Hand zusammengesetzt.
"""

import argparse
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoclicker.symbol import pixel_rows          # noqa: E402

# Was Windows tatsächlich anfragt: 16 (Titelleiste), 32 (ALT+TAB), 48 (grosse
# Kacheln, 150 % Skalierung), 256 (Verknüpfung, Explorer-Vorschau). Die Grössen
# dazwischen rechnet Windows sich selbst.
SIZES = (16, 32, 48, 64, 128, 256)


def png_bytes(edge: int) -> bytes:
    """Ein PNG mit Alphakanal, ohne Pillow zusammengesetzt."""
    raw = bytearray()
    for line in pixel_rows(edge):
        raw.append(0)                              # Filter 0 = keiner
        for r, g, b, a in line:
            raw += bytes((r, g, b, a))

    def piece(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + piece(b"IHDR", struct.pack(">IIBBBBB", edge, edge, 8, 6, 0, 0, 0))
            + piece(b"IDAT", zlib.compress(bytes(raw), 9))
            + piece(b"IEND", b""))


def ico_bytes(sizes=SIZES) -> bytes:
    """Eine ICO-Datei mit mehreren Grössen, jede als eingebettetes PNG.

    Windows nimmt PNG-Einträge seit Vista; das spart das BMP-Format mit seiner
    doppelten Höhe und der Maske. 256 steht im Verzeichnis als **0** — ein Byte
    fasst nur bis 255, und 0 heisst dort „256".
    """
    images = [png_bytes(k) for k in sizes]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = len(head) + 16 * len(images)
    directory = b""
    for edge, image in zip(sizes, images):
        directory += struct.pack("<BBBBHHII", edge % 256, edge % 256, 0, 0,
                                   1, 32, len(image), offset)
        offset += len(image)
    return head + directory + b"".join(images)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--target", default="symbol", help="Ordner für die Dateien")
    p.add_argument("--sizes", default=",".join(str(g) for g in SIZES),
                   help="Kantenlängen der PNGs, mit Komma getrennt")
    args = p.parse_args()

    try:
        sizes = tuple(sorted({int(g) for g in args.sizes.split(",") if g.strip()}))
    except ValueError:
        print("Die Grössen müssen Zahlen sein, z. B. --sizes 32,256")
        return 2
    if not sizes or min(sizes) < 8 or max(sizes) > 1024:
        print("Grössen zwischen 8 und 1024 angeben.")
        return 2

    target = Path(args.target)
    target.mkdir(parents=True, exist_ok=True)
    for edge in sizes:
        file = target / f"autoclicker-{edge}.png"
        file.write_bytes(png_bytes(edge))
        print(f"  {file}")
    ico = target / "autoclicker.ico"
    ico.write_bytes(ico_bytes(tuple(k for k in sizes if k <= 256)))
    print(f"  {ico}")
    print("\nVerknüpfung: Rechtsklick -> Eigenschaften -> Anderes Symbol -> "
          f"{ico.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
