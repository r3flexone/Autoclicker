# Tests

Details zur `CLAUDE.md` im Wurzelordner — dort stehen Befehle, Architektur
und die Regeln, die überall gelten. Claude Code lädt diese Datei, sobald eine
Datei aus `tests/` gelesen wird. Was hier steht, gilt genauso; neue
Begründungen zu diesem Bereich gehören hierher, nicht in die Wurzel.

## Aufbau der Testschichten

**Alles Testbare liegt unter `tests/`, und `tools/` enthält nur noch Werkzeuge.**
Vorher lagen die drei Schichten an drei Orten: elf `test_*.py` im
Wurzelverzeichnis, die Vertragssuite in `tools/`, die Rauchtests daneben. Wer
„die Tests" suchte, musste alle drei kennen — und das Wurzelverzeichnis eines
Projekts ist der schlechteste Ort für elf Dateien, die man beim Arbeiten am
Programm nie aufmacht.

| liegt jetzt | war vorher |
|---|---|
| `tests/all_tests.py`, `tests/mutation_check.py`, `tests/root_tests.py` | `tools/` |
| `tests/test_logic.py` + `tests/contract/` | `tools/test_logic.py` + `tools/tests/` |
| `tests/root/` | die `test_*.py` im Wurzelverzeichnis |
| `tests/smoke/` | `tools/rauchtests/` |

Zwei Dinge, die dabei auffallen sollen:

- **`tools/test_llm.py` und `tools/test_ocr.py` sind mitgezogen — nicht.** Sie
  tragen den `test_`-Präfix, sind aber interaktive Werkzeuge: sie öffnen einen
  Region-Picker und reden mit einem LLM bzw. einer OCR-Engine. Ein Name, der
  etwas Falsches verspricht, ist hier sonst ein Fehler; diese beiden bleiben in
  `tools/`, weil sie **dort** hingehören, und der Baum in der README sagt es
  ausdrücklich dazu.
- **`tests/root/` ist ein flacher Ordner ohne `__init__.py`**, und das ist
  Absicht: `unittest.discover()` legt sein Startverzeichnis selbst in
  `sys.path`, also findet jedes Modul sein `test_support` weiterhin als
  schlichten Nachbarn. Das Repo-Wurzelverzeichnis legt `root_tests.py`
  zusätzlich dazu (`autoclicker`, `main`, `market_analysis`) — ohne das liefe
  nur der Aufruf über `-m`, nicht der ausgeschriebene.

**Hier standen einmal ZWEI Kommandos, und das hat einen roten CI-Lauf gekostet:**
`tests/test_logic.py` war grün, gemeldet wurde „alles grün", und die Wurzelmodule
liefen nie. Die Warnung dazu stand an dieser Stelle — eine Regel, an die man sich
erinnern muss, ist keine.

Der Grund für die Trennung ist weg: `test_itemscan_editor_ux` und
`test_scan_services` importierten `PIL` auf Modulebene und starben ohne Pillow
schon beim LADEN, womit `unittest` gar nicht erst sammelte. Beide überspringen
jetzt sauber (`@needs_pillow`), und damit läuft ein Aufruf überall — 106 Tests
mit Pillow, dieselben 106 mit 23 übersprungenen ohne.

**Alle drei Schichten laufen in einem eigenen Ordner, nie im Repo.** Die
Pfade der App sind CWD-relativ, und jeder Test ohne eigene Sandbox schrieb in
die echten Daten: bei jedem Lauf `.run.json`, `.recording.json` und
`.reclick.json` (ein offenes Studio zeigte danach eine Klick-Runde „Grund",
die es nie gab), früher ganze Sequenzordner („Studio", „Fokus", „Ruhig" …).
Gelesen wurde dabei die echte `config.json`, lokal galten also andere Werte
als in der CI. Gesetzt wird der Ordner an genau drei Stellen —
`tests/contract/_harness.py` (vor dem ersten `autoclicker`-Import),
`root_tests.main()` und `smoke()` in `all_tests.py` —, nicht in jedem
Testfall: ein Schutz, an den jeder Testfall denken muss, ist einer, den einer
vergisst. Wer Repo-Dateien liest, nimmt deshalb `REPO`/`ROOT`, nie einen
relativen Pfad. Die Vertragssuite prüft am Ende, dass sie im Repo nichts
angelegt hat.

**Was fehlt, wird übersprungen und gesagt, nicht als Fehler gemeldet.** Ein roter
Lauf, der nur die Testumgebung beschreibt, verdeckt echte Fehler im Rauschen —
dieselbe Regel wie bei OpenCV und Pillow im Produktivcode.

**Die Rauchtests sind die Schicht, die die Vertragssuite nicht sehen KANN.** Sie
ruft die Brücken-Methoden direkt auf, also genau so, wie die Seite es *nicht* tut:
ein Tippfehler in einem Methodennamen, ein `appendChild` mit einer Liste, ein
Zustand, der einen Neuaufbau nicht überlebt — nichts davon fällt dort auf, und im
Fenster sofort (der Reiter bleibt leer). Deshalb steht dort ein Chromium mit der
echten `index.html` davor und der echten `StudioBridge` dahinter; `window.pywebview.api`
ist ein Proxy, der jeden Aufruf nach Python weiterreicht. Kein Nachbau — dieselben
zwei Seiten wie im Fenster, nur ohne pywebview dazwischen (`tests/smoke/_bridge.py`).

Ein neuer Reiter bekommt dort eine Datei; das Gerüst (`Window`, `sandbox`,
`mock_screen`) nimmt einem den Aufbau ab. Sie laufen in CI in einem eigenen
Job, weil dort erst ein Browser installiert werden muss.

**Gewartet wird auf den Zustand der Seite, nicht auf die Uhr** (`Window.settle()`).
Nach jedem Klick und Reiterwechsel stand ein `wait_for_timeout(700)` — ein blinder
Schlaf, egal ob die Seite nach 20 ms fertig war. Gemessen über alle acht Tests:
**86 s Laufzeit, davon 70 s Schlaf** in 117 Aufrufen und 6,5 s echte Arbeit. Der
Prüfstand hat den Brücken-Proxy in der Hand, also zählt er dort, wie viele
Aufrufe unterwegs sind (`window.__pending`); `settle()` wartet, bis das zwei Frames
lang null ist — der Neuaufbau nach einer Antwort läuft in Microtasks, also vor
dem nächsten Frame, und eine Kette (Antwort → Neuaufbau → Vorschau nachladen)
fängt ihr nächstes Glied noch im selben Frame an. `tab()`, `click()` und
`click_text()` rufen es selbst; ein Test schreibt nach einer eigenen Aktion
`f.settle()`. Ergebnis: 86 s → 27 s, und die Wartezeit wächst nicht mehr mit der
Zahl der Klicks, sondern mit dem, was die Seite tut. Ohne den Zähler werden
alle acht Tests rot — die Bedingung trägt, sie ist kein Schmuck.

Fünf feste Wartezeiten bleiben, und jede hängt an einer **Uhr**, die die Seite
selbst stellt: das Auto-Speichern nach 900 ms und der Aufnahme-Wächter. Wer
eine neue braucht, schreibt dazu, auf welchen Timer sie wartet — sonst ist sie
in einem Jahr wieder ein „700, das reicht wohl".

**`tests/test_logic.py`** prüft Serialisierung,
Migration, Runtime-Gates, Kalibrierung, Tastenbelegung und die Plattform-Grenze — ohne
GUI, ohne Windows, ohne Netz. `msvcrt` und `ctypes.windll` werden am Dateianfang gestubbt;
deshalb läuft die komplette Logik-Schicht auch hier.

**Und seit `.github/workflows/tests.yml` läuft sie auch, wenn niemand daran denkt.**
Push und Pull Request auf jedem Branch, als Matrix auf Ubuntu und Windows. Dazu
zwei eigene Jobs: die Rauchtests (Browser, nur Linux — es geht um die Seite, nicht
um die Plattform) und `flake8 --select=F` (tote Importe, Tippfehler in Namen).
Jeder Job muss grün sein; ein roter Lauf ist ein Fehler, kein Hinweis.
Geprüft wird auf **Python 3.14**, der unteren Grenze — und die ist die Version,
die wirklich benutzt wird. Hier stand 3.10, ohne dass jemand 3.10 benutzte: ein
f-String, dessen `{…}` über zwei Zeilen lief (erst ab 3.12 erlaubt), hielt die
CI vier Läufe lang rot, während jeder lokale Lauf grün war. Eine Grenze, die
niemand benutzt, prüft nur, ob man sie einhält — nicht, ob das Programm läuft.
README (`Python 3.14+`) und alle `python-version` in `tests.yml` nennen dieselbe
Zahl; ein Test hält sie zusammen.

**Der Test-Job läuft dreimal: `ohne`, `pillow` und `mit` Bildpaketen.** OpenCV und Pillow sind
optional, und der Code degradiert sauber ohne sie — nur überspringt die Suite dann
**über hundert Tests** (Template-Vergleich, Masken, Slot-Erkennung, die
Grössen-Meldung): 1.154 statt 1.273. Ein Lauf nur ohne Fremdpakete ist also grün,
während der halbe Bilderkennungs-Teil ungeprüft bleibt — und genau dort ist schon
einmal eine kaputte Meldung durchgerutscht, weil die Zusicherung dazu lokal gar
nicht lief. Dieselbe Regel wie bei den Plattform-Stubs: **was das Echte anders macht
als der Ersatz, wird auf beiden Seiten geprüft.** Wer an `imaging.py` arbeitet,
installiert sie deshalb auch lokal (`pip install opencv-python-headless pillow numpy`)
— sonst sagt ein grüner Lauf hier nichts über die Stellen, um die es gerade geht.

**Die dritte Achse (`pillow`) ist eine echte Installation, keine Vollständigkeit
um der Vollständigkeit willen.** Pillow ohne OpenCV ist der Zustand, in dem
Screenshots und Farbmessung gehen, Template-Vergleich aber nicht — und wer nur
`ohne` und `mit` prüft, sieht genau die Zweige nie, die das eine haben und das
andere nicht.

**Ein grüner Exitcode ist kein grüner Lauf.** `contract()` verlangt zusätzlich die
Schlusszeile im Muster `N PASS / 0 FAIL` mit N > 0: eine Suite, die vor ihrem
Abschluss stirbt, meldete sonst Erfolg, weil niemand mehr etwas gedruckt hat.
Dasselbe Muster in der Gegenrichtung ist `--smoke-required` — lokal darf ein
fehlender Browser überspringen, im Browser-Job ist genau das ein Fehler.

**`--mutations` prüft die Tests, nicht den Code** (`tests/mutation_check.py`).
Jeder Fall entfernt in einem frischen Prozess **eine** Sicherung im Arbeits\-
speicher und erwartet, dass ein bestimmter Test darüber rot wird. Das ist die
Gegenprobe, die CLAUDE.md an anderer Stelle von Hand verlangt („Fix entschärfen,
Test muss rot werden") — nur automatisiert und für die Stellen, an denen es
schon einmal schiefging. Nur ein Assertion-Fehler zählt als erkannt: ein
Importfehler, ein übersprungener Test oder ein Timeout beweist nichts.

**Das ist eine gezielte Regressionsprüfung, keine vollständige Mutationsanalyse** —
die Fälle stehen als Liste in `CASES` und wachsen mit den Fehlern, die auffallen,
nicht mit dem Code.

`tests/root_tests.py` gibt es, weil `unittest discover` die Vertragssuite über
ihren Wrapper ein zweites Mal mitzog: im Gesamtlauf lief sie damit doppelt (und
die Zähler standen zweimal da). `--without-contract` lässt genau diesen Wrapper weg;
einzeln aufgerufen bleibt er drin, sonst fehlte er dort ganz.

**Ein Einstiegspunkt, mehrere Dateien.** `tests/test_logic.py` war mit über 7.000
Zeilen die grösste Datei des Repos — mehr als jedes Produktivmodul —, und die
durchnummerierten Variablennamen (`_b18`, `_sand18`) waren das Symptom: so
benennt man, wenn der Namensraum voll ist. Neue Sektionen kommen deshalb als
eigenes Modul unter **`tests/contract/`**, holen Stubs, Zähler und `check`/`section`
aus `tests/contract/_harness.py` und werden am Ende von `test_logic.py` importiert
(Import = ausführen, wie im Rest der Datei auch).

Zwei Dinge hängen daran: **die Zähler leben im Harness**, nicht im Aufrufer —
sonst zählte jedes Modul für sich und die Schlusszeile sähe nur den letzten
Stand. Und **die Stubs müssen vor dem ersten `autoclicker`-Import stehen**;
`_harness` setzt sie beim Import, also ist `from ._harness import check` die
erste Zeile eines neuen Moduls, nicht die dritte.

## Was ausserhalb der Suite bleibt

**Es gibt nur noch EINEN ungetesteten Rest, und der ist klein.** Bis zum Umbau lag
hier ein Absatz über einen Test, der jeden `dpg.<name>(..., kwarg=...)` gegen die
installierte Dear-PyGui-Version hielt — nötig, weil das Scan-Studio ein Fenster
brauchte und in keinem Test lief (es starb einmal an `add_static_texture(...,
format=...)`, das es in DPG 2.x nur noch bei `add_raw_texture` gibt). Dieses Fenster
gibt es nicht mehr, der Test ist ersatzlos gelöscht, und `dearpygui` steht in keiner
Anforderungsdatei mehr. Die Geschichte steht hier, damit niemand denselben Weg noch
einmal einschlägt: **eine Ansicht, die man nur über die Signaturen ihres Fremdpakets
prüfen kann, ist die falsche Ansicht.**

**Beim Studio stellt sich die Frage deshalb gar nicht.** Seine Oberfläche ist eine
Webseite. `bridge.py` und `scans.py` bleiben stabile Fassaden; die Logik liegt
nach Verantwortung in `bridge_view.py`, `bridge_services.py`,
`bridge_editing.py` sowie den `scan_*.py`-Modulen — ohne Fenster, ohne
Fremdpaket, also im Test. Ungeprüft bleibt nur, was wirklich Anzeige ist
(HTML/CSS/JS). Das ist die Richtung, in die GUI-Code hier gehört: **nicht die
Ansicht testbar machen, sondern die Logik aus ihr heraus.**

Automatisiert geprüft werden beide Plattformverträge. Manuell bleiben die echten
Desktop-Grenzen: globale Hotkeys, Eingabesimulation, Fensterfokus und Screenshots
in einer Windows- bzw. X11-Sitzung.

**`tests/all_tests.py` stellt seinen eigenen stdout auf UTF-8** (`reconfigure`,
`errors="replace"`) und braucht deshalb kein `PYTHONIOENCODING` mehr. Vorher riss
ein einziges Kaestchen aus einem Fortschrittsbalken den ganzen Lauf mit
`UnicodeEncodeError` ab — und zwar *nachdem* die Vertragssuite grün durch war:
die Unterprozesse liefen längst auf UTF-8, nur die Konsole des Runners nicht.
Hinter einer Pipe blieb davon ein Traceback und ein Exitcode, den niemand mehr
las. Ein unbekanntes Zeichen ist ein Darstellungsproblem, kein Testergebnis.
