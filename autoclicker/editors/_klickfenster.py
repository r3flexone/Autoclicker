"""Welches Fenster hat einen Klick bekommen? — geteilt von Aufnahme und Klick-Runde.

Beide laufen aus dem Maus-Hook und müssen dieselbe Frage beantworten: gehört
dieser Klick zum Spiel oder zu einem anderen Fenster? Die Antwort stand zweimal
im Baum, und die beiden Fassungen waren **verschieden** — die Klick-Runde
fragte das Fenster unter dem Zeiger, die Aufnahme den Vordergrund. Genau daran
fehlte in jeder Studio-Aufnahme der erste Klick (s. `geklicktes_fenster`).
"""

from ..winapi import get_foreground_window_title, get_window_title_at


def geklicktes_fenster(x: int, y: int) -> str:
    """Der Titel des Fensters, in das GEKLICKT wurde — "" wenn unbekannt.

    **Nicht der Vordergrund.** Windows liefert den Button-Down an das Fenster
    unter dem Zeiger; war das nicht das aktive, wird es durch genau diesen
    Klick erst aktiv. Im Hook steht im Vordergrund also noch das VORIGE
    Fenster, und die Frage „in welchem Fenster bin ich?" wird für den Klick
    davor beantwortet.

    Zweimal ist das an echten Daten aufgefallen, in beiden Richtungen:

    * **Klick-Runde**: ein Klick, der das Studio erst nach vorn holte, zählte
      als Klick ins Spiel — ein Punkt wanderte auf eine Stelle im
      Studio-Fenster (Farbe `#1C2333`, dessen Panel-Grau).
    * **Aufnahme**: sie wird mit einem Knopf im Studio gestartet, also ist das
      Studio vorn — und der **erste Klick ins Spiel** wurde als Studio-Klick
      verworfen. Am Ende dasselbe umgekehrt: der Klick auf „Aufnahme stoppen"
      kam bei vorn stehendem Spiel als Spielklick in die Sequenz (letzter
      Schritt einer echten Aufnahme: `(1347, 709)`, Farbe `#1C2333`).

    Der Rückfall auf den Vordergrund ist Absicht: liefert die geometrische
    Frage nichts (kein Fenster, fremder Desktop), ist die alte Antwort immer
    noch besser als gar keine.
    """
    try:
        titel = (get_window_title_at(x, y) or "").strip()
    except Exception:
        titel = ""
    if titel:
        return titel
    try:
        return (get_foreground_window_title() or "").strip()
    except Exception:
        return ""
