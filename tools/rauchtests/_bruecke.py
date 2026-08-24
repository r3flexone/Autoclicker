"""Gerüst für die Rauchtests: eine echte Brücke hinter einem echten Browser.

**Warum es diese Schicht ueberhaupt gibt.** Die Vertragssuite prueft die Bruecke,
und das ist der grosse Teil — aber sie ruft deren Methoden DIREKT auf, also
genau so, wie die Seite es nicht tut. Was dazwischen liegt (ein Tippfehler in
einem Methodennamen, ein `appendChild` mit einer Liste, ein Zustand, der einen
Neuaufbau nicht ueberlebt), faellt dort nicht auf und im Fenster sofort.

Deshalb hier ein Chromium mit der echten `index.html` davor und der echten
`StudioBridge` dahinter: `window.pywebview.api` ist ein Proxy, der jeden Aufruf
an Python weiterreicht. Kein Nachbau, keine Attrappe — dieselben zwei Seiten wie
im Fenster, nur ohne pywebview dazwischen.

Playwright ist optional, wie OpenCV und Pillow: fehlt es, wird uebersprungen und
gesagt, was zu installieren waere. Ein Rauchtest, der ohne Browser rot ist,
meldet die Testumgebung statt eines Fehlers.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
WEB = WURZEL / "autoclicker" / "editors" / "sequence_studio" / "web"

# Der Proxy: jeder `window.pywebview.api.<name>(daten)`-Aufruf der Seite landet
# als ein Python-Aufruf auf der Bruecke. Genau ein Argument, wie im Fenster.
STUB = """
window.pywebview = {api: new Proxy({}, {get: (t, name) => (d) =>
  window.__bruecke(String(name), d === undefined ? null : d)})};
"""


def playwright_da() -> tuple[bool, str]:
    """(verfuegbar, Grund). Chromium liegt im Image, Playwright nicht immer."""
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False, "playwright fehlt — nachinstallieren: pip install playwright"
    if not _chromium():
        return False, "kein Chromium gefunden (PLAYWRIGHT_BROWSERS_PATH?)"
    return True, ""


def _chromium() -> str:
    """Der Pfad zum vorinstallierten Chromium — oder "" fuer Playwrights eigenen."""
    basis = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))
    if not basis.is_dir():
        return ""
    for kandidat in sorted(basis.glob("chromium*/chrome-linux/chrome")):
        return str(kandidat)
    direkt = basis / "chromium"
    return str(direkt) if direkt.exists() else ""


def sandkasten(praefix: str) -> str:
    """Ein leeres Datenverzeichnis, in das gewechselt wird.

    Die Pfad-Konstanten sind CWD-relativ (s. CLAUDE.md), also reicht ein
    `chdir` — kein Test schreibt damit je in den echten Datenbestand.
    """
    sand = tempfile.mkdtemp(prefix=praefix)
    os.chdir(sand)
    Path("sequences").mkdir()
    return sand


class Fenster:
    """Die Seite im Browser, mit der echten Bruecke dahinter.

    Als Kontextmanager: `with Fenster(bruecke) as f: f.reiter("werkzeuge")`.
    Sammelt nebenbei jeden Seitenfehler ein — ein `pageerror` ist im Fenster ein
    Reiter, der leer bleibt, und genau danach wird hier gesucht.
    """

    def __init__(self, bruecke, breite: int = 1500, hoehe: int = 900):
        self.bruecke = bruecke
        self.fehler: list[str] = []
        self._groesse = (breite, hoehe)
        self._pw = None
        self._browser = None
        self.seite = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        pfad = _chromium()
        self._browser = self._pw.chromium.launch(
            **({"executable_path": pfad} if pfad else {}))
        self.seite = self._browser.new_page(
            viewport={"width": self._groesse[0], "height": self._groesse[1]})
        self.seite.on("pageerror", lambda e: self.fehler.append(f"pageerror: {e}"))
        self.seite.on("console", lambda m: self.fehler.append(
            f"console.error: {m.text}") if m.type == "error" else None)
        self.seite.expose_function("__bruecke", self._ruf)
        self.seite.add_init_script(STUB)
        self.seite.goto((WEB / "index.html").as_uri())
        self.seite.wait_for_timeout(600)
        return self

    def __exit__(self, *_):
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()
        return False

    def _ruf(self, name: str, daten):
        """Ein Aufruf der Seite an die Bruecke. Unbekannte Namen sind ein Fehler.

        Die Seite bekaeme sonst `null` und zeichnete eine leere Ansicht - also
        genau das Bild, das dieser Test aufdecken soll.
        """
        fn = getattr(self.bruecke, name, None)
        if fn is None or not callable(fn):
            self.fehler.append(f"Bruecke kennt '{name}' nicht")
            return None
        return fn(daten)

    # ---------------------------------------------------------------- Bedienen

    def reiter(self, name: str, warten: int = 700):
        self.seite.click(f'.tab[data-ansicht="{name}"]')
        self.seite.wait_for_timeout(warten)
        return self

    def klick(self, wahl: str, warten: int = 700):
        self.seite.click(wahl)
        self.seite.wait_for_timeout(warten)
        return self

    def klick_text(self, wahl: str, text: str, warten: int = 700):
        """Den Knopf mit diesem Text anklicken — robuster als eine Position.

        Ueber `nth-of-type` zu gehen bricht, sobald jemand einen Knopf davor
        einbaut, und der Test meldet dann etwas ueber die falsche Stelle.
        """
        # **Suchen und Klicken in einem Anlauf, notfalls nochmal.** Ein
        # festgehaltener Element-Zeiger loest sich auf, sobald zwischen Suche
        # und Klick ein Neuaufbau dazwischenkommt („Element is not attached to
        # the DOM") — und das passiert hier staendig, weil jede Bruecken-Antwort
        # neu zeichnet. Ueber den Text einen Selektor zu bauen geht nicht: die
        # Beschriftungen enthalten Zeilenumbrueche und Anfuehrungszeichen.
        letzter = None
        for _ in range(3):
            treffer = [k for k in self.seite.query_selector_all(wahl)
                       if text in (k.inner_text() or "")]
            if not treffer:
                self.seite.wait_for_timeout(150)
                continue
            try:
                treffer[0].click()
            except Exception as fehler:      # noqa: BLE001 - erneut versuchen
                letzter = fehler
                self.seite.wait_for_timeout(150)
                continue
            self.seite.wait_for_timeout(warten)
            return self
        raise AssertionError(f"kein '{text}' in {wahl}" + (f" ({letzter})" if letzter else ""))

    # ---------------------------------------------------------------- Ablesen

    def text(self, wahl: str) -> str:
        return self.seite.inner_text(wahl)

    def status(self) -> str:
        return self.seite.inner_text("#status")

    def anzahl(self, wahl: str) -> int:
        return len(self.seite.query_selector_all(wahl))

    def bild(self, name: str):
        ziel = Path(tempfile.gettempdir()) / f"rauchtest_{name}.png"
        self.seite.screenshot(path=str(ziel))
        return ziel


def haupt(name: str, lauf) -> int:
    """Ein Rauchtest als Programm: Ergebnis auf stdout, Rueckgabe als Exit-Code."""
    da, grund = playwright_da()
    if not da:
        print(f"UEBERSPRUNGEN  {name}: {grund}")
        return 0
    cwd = os.getcwd()
    try:
        fehler = lauf()
    finally:
        os.chdir(cwd)
    if fehler:
        print(f"FAIL  {name}")
        for f in fehler:
            print(f"        {f}")
        return 1
    print(f"OK    {name}")
    return 0


def main(name: str, lauf) -> None:
    sys.exit(haupt(name, lauf))
