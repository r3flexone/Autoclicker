"""
Fernstart über Discord — mehrere PCs starten dieselbe Sequenz gleichzeitig.

Wer in einem gemeinsamen Discord-Kanal `!start raid` schreibt, startet auf
jedem PC, dessen Besitzer das Wort `raid` und den Absender freigegeben hat,
die Sequenz, die **dort** hinter dem Wort steht — 20 Sekunden nach dem
Zeitstempel der Nachricht, auf allen Rechnern derselbe Augenblick.

Drei Module, und die Grenze zwischen ihnen ist die Sicherheitsgrenze:

| Modul | darf | darf nicht |
|---|---|---|
| `settings.py` | `remote.json` lesen **und** schreiben | — (das Studio schreibt hier) |
| `discord.py` | mit discord.com reden | irgendetwas im Programm anfassen |
| `bot.py` | Discord lesen, antworten, Aufträge in eine Warteschlange legen | Dateien des Programms schreiben, Befehle des Briefkastens senden |

Aus einer Nachricht wird nie ein Pfad, eine Koordinate oder eine Einstellung:
Discord **wählt** nur aus dem, was der Besitzer im Studio freigegeben hat. Was
ein Auftrag auslöst, entscheidet der Hauptprozess (`REMOTE_COMMANDS` in
`handlers.py`), und er prüft die Freigabe dort ein zweites Mal selbst.
Begründungen: `autoclicker/CLAUDE.md`, Abschnitt „Fernstart über Discord“.
"""
