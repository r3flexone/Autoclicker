"""Rauchtest Werkzeuge-Reiter: prüfen, kalibrieren, Farbfrage, Klick-Runde."""

import re
from pathlib import Path

from ._bruecke import Fenster, main, sandkasten


def quelle_wz() -> str:
    """Der `WZ_WERKZEUGE`-Block aus `app.js` — die Liste, die die Seite zeichnet."""
    # Absolut, denn `sandkasten()` wechselt vorher das Arbeitsverzeichnis.
    datei = (Path(__file__).resolve().parents[2]
             / "autoclicker/editors/sequence_studio/web/app.js")
    quelle = datei.read_text(encoding="utf-8")
    ab = quelle.index("const WZ_WERKZEUGE = [")
    return quelle[ab:quelle.index("];", ab)]


def aufbau():
    """Ein kleiner Bestand plus die Brücke darauf — wie im Vertragstest."""
    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    from autoclicker.models import (
        AutoClickerState, ClickPoint, ItemProfile, ItemScanConfig,
        LoopPhase, Sequence, SequenceStep,
    )
    from autoclicker.persistence import (
        list_available_sequences, save_data, save_item_scan,
    )

    sandkasten("rauch_wz_")
    st = AutoClickerState()
    seq = Sequence(name="Farm", loop_phases=[LoopPhase(name="A", steps=[
        SequenceStep(point_id=1, delay_before=3.0), SequenceStep(point_id=2)])],
        points=[ClickPoint(id=1, x=100, y=100, name="Sammeln",
                           color=(10, 200, 30)),
                ClickPoint(id=2, x=900, y=600, name="Bestaetigen"),
                ClickPoint(id=3, x=400, y=300, name="Menue")])
    st.sequences["Farm"] = seq
    st.active_sequence = seq
    st.points = seq.points
    save_data(st)
    # Absichtlich unvollständig, damit die Prüfung etwas darstellt.
    save_item_scan(ItemScanConfig(
        name="Inventar", owner_sequence="Farm",
        items=[ItemProfile(name="Geist")],
    ))

    b = StudioBridge(seq, Path(dict(list_available_sequences())["Farm"]), "sequences")
    # Maus und Bildschirm gibt es hier nicht: beide werden gestellt, alles andere
    # laeuft wie im Fenster.
    b._stelle_abwarten = lambda: (555, 444, "")
    b._farbe_an = staticmethod(lambda x, y: (200, 10, 30))
    return b


def lauf():
    b = aufbau()
    fehler = []

    def pruefe(bedingung, text):
        if not bedingung:
            fehler.append(text)

    with Fenster(b) as f:
        f.reiter("werkzeuge")
        # **Gegen die Tabelle in der Seite gemessen, nicht gegen eine getippte
        # Zahl.** Hier stand `== 4`, als es vier Werkzeuge gab; mit dem fuenften
        # und sechsten war der Pin schlicht falsch, ohne dass jemand etwas
        # kaputtgemacht haette. Gezaehlt wird jetzt, was `WZ_WERKZEUGE` fuehrt.
        soll = len(re.findall(r'\{key: "', quelle_wz()))
        pruefe(f.anzahl("#wz-links button") == soll,
               f"{soll} Werkzeuge erwartet (je eines aus WZ_WERKZEUGE), "
               f"da: {f.anzahl('#wz-links button')}")
        pruefe("Farm" in f.text("#wz-links"), "die offene Sequenz fehlt links")

        # --- Aufnahme: der normale Weg ist vollständig im Studio sichtbar ---
        f.klick_text("#wz-links button", "Sequenz aufnehmen", warten=300)
        pruefe(f.anzahl(".wz-aufnahme-form input") == 2,
               "Name und Zyklen der Aufnahme fehlen")
        pruefe(f.anzahl(".wz-aufnahme-form textarea") == 1,
               "Notiz der Aufnahme fehlt")
        pruefe(f.anzahl(".wz-aufnahme-ausgabe") == 1,
               "rollende Live-Ausgabe der Aufnahme fehlt")
        tasten = [z.inner_text() for z in
                  f.seite.query_selector_all("#wz-mitte .wz-tasten .wz-taste")]
        pruefe(len(tasten) == 8, f"acht Aufnahme-Hotkeys erwartet, da: {tasten}")
        pruefe("Aufnahme starten" in f.text("#wz-mitte"), "sichtbarer Start fehlt")
        f.bild("wz_aufnahme")

        # --- Pruefen ---
        f.klick_text("#wz-links button", "Bestand prüfen", warten=300)
        f.klick_text("#wz-mitte button", "Jetzt prüfen", warten=900)
        pruefe(f.anzahl(".wz-befund") == 2, "zwei Befunde erwartet")
        pruefe("Fehler" in f.status(), f"Status nach Pruefen: {f.status()!r}")
        pruefe(bool(f.text("#wz-rechts").strip()), "rechts steht nicht, was geprueft wurde")
        f.bild("wz_pruefen")

        # --- Farbfrage: die Stelle hat eine andere Farbe als der Punkt ---
        f.klick_text("#wz-links button", "Kalibrieren", warten=500)
        pruefe("gesamte gespeicherte Bestand" in f.text("#wz-mitte"),
               "der Bezug fehlt beim Kalibrieren")
        f.klick("#wz-mitte .wz-ref button", warten=900)
        pruefe(f.anzahl(".wz-farbfrage") == 1, "keine Farb-Rueckfrage")
        pruefe(f.anzahl(".wz-farbe") == 2, "beide Farben sollten dastehen")
        pruefe("Verschiebung" not in f.text("#wz-mitte"),
               "trotz Rueckfrage schon gesetzt")
        f.bild("wz_farbfrage")

        f.klick_text(".wz-farbfrage button", "Trotzdem setzen", warten=900)
        # Der Versatz steht als zwei Kennzahlen unter „BERECHNETER TRANSFORM",
        # nicht mehr als ein Satz „Verschiebung: …". Gemessen wird deshalb der
        # Kennzahlen-Block — der Satz war eine Formulierung, die Zahlen sind
        # die Aussage.
        kennzahlen = f.text("#wz-mitte .wz-kennzahlen")
        pruefe("+455" in kennzahlen and "+344" in kennzahlen,
               f"Versatz falsch: {kennzahlen!r}")
        pruefe(f.anzahl("#wz-mitte input[type=checkbox]") == 3, "drei Umfang-Haken")
        pruefe("Stelle(n)" in f.text("#wz-rechts"), "keine Vorschau rechts")
        f.bild("wz_kalib")

        f.klick_text("#wz-mitte button", "Umrechnen und speichern", warten=1000)
        pruefe("Kalibriert" in f.status(), f"Anwenden: {f.status()!r}")
        pruefe([p.x for p in b.points] == [555, 1355, 855],
               f"Punkte nicht gewandert: {[(p.id, p.x) for p in b.points]}")

        # --- Nachklicken: starten UND beenden ---
        f.klick_text("#wz-links button", "Punkte nachklicken", warten=500)
        pruefe("die offene Sequenz" in f.text("#wz-mitte"), "Bezug fehlt")
        pruefe("Farm" in f.text("#wz-mitte"), "Sequenzname fehlt")
        knoepfe = [k.inner_text() for k in
                   f.seite.query_selector_all("#wz-mitte button")]
        pruefe(len(knoepfe) == 3,
               f"starten + uebernehmen + verwerfen erwartet, da: {knoepfe}")
        # Die vier Griffe stehen als TABELLE da, nicht als Absatz - man schlaegt
        # sie mitten im Klicken nach.
        tasten = [z.inner_text() for z in
                  f.seite.query_selector_all("#wz-mitte .wz-tasten .wz-taste")]
        pruefe(len(tasten) == 4, f"vier Hotkeys erwartet, da: {tasten}")
        pruefe("CTRL+ALT+J" in tasten, f"Uebernehmen-Taste fehlt: {tasten}")
        pruefe("übernimmst" in f.text("#wz-mitte .wz-regel"),
               "die Regel 'nichts wird geschrieben' fehlt")
        f.klick_text("#wz-mitte button", "Runde starten", warten=700)
        pruefe("Farm" in f.status(), f"Start nennt die Sequenz nicht: {f.status()!r}")
        # Verwerfen ist der Ausgang, der NICHTS schreibt - und er muss es sagen.
        f.klick_text("#wz-mitte button", "Verwerfen", warten=700)
        pruefe("sequence.json" in f.status(), f"Verwerfen: {f.status()!r}")
        f.klick_text("#wz-mitte button", "Übernehmen", warten=700)
        pruefe("bernommen" in f.status(), f"Uebernehmen: {f.status()!r}")
        f.bild("wz_klick")

        # --- Der Aufnahme-Waechter fragt erst, wenn es etwas zu finden gibt ---
        # `sequenz_liste()` laedt JEDE Sequenzdatei einzeln — genau deshalb
        # zieht `zeichne()` sie nicht nach. Der langsame Zweig rief sie
        # trotzdem im Sekundentakt ab dem Druck auf „Aufnahme starten", also
        # waehrend der ganzen Aufnahme; und die dauert lange, weil der Nutzer
        # so lange im Spiel ist. Solange sie laeuft, kann die Datei aber gar
        # nicht da sein.
        gezaehlt = f.seite.evaluate("""() => {
          window.__liste = 0;
          const alt = window.frage;
          window.frage = async function (name, daten) {
            if (name === "sequenz_liste") window.__liste++;
            return alt(name, daten);
          };
          // Aufnahme laeuft: der Waechter darf nur warten.
          wzAufnahmeGestartet = true;
          wzAufnahmeName = "Gibt-Es-Nicht";
          wzAufnahmeLive = {aktiv: true, pausiert: false, anzahl: 0, ereignisse: []};
          wzAufnahmeBeobachten();
          return true;
        }""")
        pruefe(gezaehlt, "der Waechter liess sich nicht anwerfen")
        f.seite.wait_for_timeout(3400)
        waehrend = f.seite.evaluate("window.__liste")
        pruefe(waehrend == 0,
               f"der Waechter fragt waehrend der laufenden Aufnahme: {waehrend}x")
        # Endet sie, muss er sofort nachsehen — sonst faende er sie nie.
        f.seite.evaluate("wzAufnahmeLive = {aktiv: false, pausiert: false, "
                         "anzahl: 0, ereignisse: []}")
        f.seite.wait_for_timeout(2400)
        danach = f.seite.evaluate("window.__liste")
        pruefe(danach > 0, "nach dem Ende der Aufnahme fragt der Waechter gar nicht")
        f.seite.evaluate("wzAufnahmeGestartet = false; ++wzAufnahmePoll; "
                         "++wzAufnahmeLivePoll;")

        fehler.extend(f.fehler)
    return fehler


if __name__ == "__main__":
    main("Werkzeuge", lauf)
