"use strict";

/* ------------------------------------------------------------------ Werkzeug */

const $ = (id) => document.getElementById(id);

/** Kleiner DOM-Bauer: el("div", {class:"x", onclick:f}, kind, "text") */
function el(tag, attrs, ...kinder) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "style") n.setAttribute("style", v);
    else if (k === "text") n.textContent = v;
    else if (v === true) n.setAttribute(k, "");
    else n.setAttribute(k, v);
  }
  for (const kind of kinder.flat()) {
    if (kind === null || kind === undefined || kind === false) continue;
    n.appendChild(typeof kind === "object" ? kind : document.createTextNode(String(kind)));
  }
  return n;
}

/** Zahlenfeld, das seinen Wert erst beim Verlassen meldet.
 *
 * Bewusst `change` und nicht `input`: jede Meldung baut die Ansicht neu, und ein
 * Neuaufbau mitten in der Eingabe nimmt das Feld weg, in das gerade getippt wird.
 * Dieselbe Regel wie beim Dear-PyGui-Vorgänger — diskrete Bedienelemente (Klick,
 * fertig) dürfen sofort melden, Tipp-Felder erst am Ende. */
/* Welche Erklaerungen gerade aufgeklappt sind — als Schluessel, nicht als
 * DOM-Verweis. Der Inspektor wird bei JEDER Aenderung komplett neu gebaut
 * (`replaceChildren`), ein gemerktes Element waere danach ein Element, das
 * niemand mehr sieht. Aufgeklappt bleibt aufgeklappt, bis man es zuklappt —
 * auch ueber einen Block-Wechsel hinweg. */
const offeneHilfen = new Set();

/** Das kleine ⓘ hinter einer Beschriftung. Klick klappt den Text auf, Klick zu.
 *
 * Es war erst der native Tooltip (`title`) — eine Zeile Code, aber er verschwindet
 * bei jedem Tastendruck und nach ein paar Sekunden von selbst. Zum Nachlesen taugt
 * er damit nicht, und abfotografieren laesst er sich auch nicht.
 *
 * Der aufgeklappte Text landet HINTER dem Bedienelement, also genau dort, wo er
 * frueher dauerhaft stand. Deshalb braucht es keine Positionsrechnung und kein
 * Overlay: die Seite bleibt so klein, wie sie sein soll.
 *
 * `schluessel` ist die Identitaet ueber Neuaufbauten hinweg. Der Text taugt dafuer
 * nicht: die Beschriftung traegt die Punkt-Nummer, und der STELLE-Text haengt am
 * Block-Typ — beides wechselt, die Stelle in der Oberflaeche aber nicht. */
function info(text, schluessel) {
  if (!text) return null;
  const zeichen = el("span", {class: "info", "data-hilfe": schluessel || text}, "i");
  zeichen._text = text;
  zeichen.addEventListener("click", (e) => {
    // Das ⓘ steckt in einem <label>; ohne das hier wuerde der Klick das Feld
    // fokussieren bzw. den Schalter umlegen.
    e.preventDefault();
    e.stopPropagation();
    const key = zeichen.getAttribute("data-hilfe");
    if (offeneHilfen.has(key)) offeneHilfen.delete(key);
    else offeneHilfen.add(key);
    hilfeZeichnen(zeichen);
  });
  return zeichen;
}

/** Bringt EIN ⓘ auf den Stand von `offeneHilfen` — auf- oder zugeklappt. */
function hilfeZeichnen(zeichen) {
  const offen = offeneHilfen.has(zeichen.getAttribute("data-hilfe"));
  const wirt = zeichen.closest("label") || zeichen.parentNode;
  const nachbar = wirt.nextElementSibling;
  const da = nachbar && nachbar.classList.contains("hilfe-text") ? nachbar : null;
  zeichen.classList.toggle("an", offen);
  if (offen && !da) {
    wirt.parentNode.insertBefore(el("p", {class: "hinweis hilfe-text"}, zeichen._text),
                                 wirt.nextSibling);
  } else if (!offen && da) {
    da.remove();
  }
}

/** Nach dem Neuaufbau: alles wieder aufklappen, was aufgeklappt war. */
function hilfenAnwenden(wurzel) {
  for (const zeichen of wurzel.querySelectorAll(".info")) hilfeZeichnen(zeichen);
}

/** Beschriftung, ggf. mit ⓘ dahinter. */
function beschriftet(text, hilfe, schluessel) {
  return hilfe ? el("span", {class: "mitinfo"}, text, info(hilfe, schluessel)) : text;
}

function feld(beschriftung, wert, beim_setzen, extra, hilfe, schluessel) {
  const eingabe = el("input", Object.assign({value: wert === null || wert === undefined ? "" : wert,
                                             autocomplete: "off"}, extra || {}));
  eingabe.addEventListener("change", () => beim_setzen(eingabe.value));
  eingabe.addEventListener("keydown", (e) => { if (e.key === "Enter") eingabe.blur(); });
  return el("label", {class: "feld"}, beschriftet(beschriftung, hilfe, schluessel), eingabe);
}

/** Kategorie als echtes Kombinationsfeld: vorhandene Namen lassen sich aus der
 *  Browser-Liste anklicken, das Feld bleibt aber frei beschreibbar. Ein <select>
 *  waere hier zu streng, weil neue Kategorien ohne einen zweiten Bedienweg
 *  angelegt werden koennen sollen. */
function kategorienWerte(zusatz) {
  const werte = [];
  const gesehen = new Set();
  for (const roh of SC.kategorien.concat(zusatz || [])) {
    const wert = String(roh || "").trim();
    const schluessel = wert.toLocaleLowerCase("de");
    if (wert && !gesehen.has(schluessel)) {
      gesehen.add(schluessel);
      werte.push(wert);
    }
  }
  return werte;
}

/* ------------------------------------------------------------ Kategorie wählen
 *
 * **Vorhandene anklicken, neue tippen — und die neue ist beim naechsten Item
 * gleich anklickbar.** Ein freies Textfeld allein hat genau das Problem, das man
 * nicht sehen kann: „Helme", „helme" und „Helmr" sind drei Kategorien. Items
 * derselben Kategorie konkurrieren miteinander (das kleinere P gewinnt) — eine
 * vertippte trennt ein Item still von seiner Gruppe, und nichts wird rot.
 *
 * Ein <select> allein waere zu streng: neue Kategorien muessen ohne einen
 * zweiten Bedienweg entstehen koennen. Also beides in EINEM Bedienelement, mit
 * dem Auswaehlen als Normalfall — und getippt wird nur noch, wenn man es
 * ausdruecklich will. Vorher war Tippen der einzige Weg und die Vorschlagsliste
 * (`<datalist>`) ein Angebot, das man kennen musste. */
const KATEGORIE_NEU = "\u0000neu";   // als Kategoriename nicht eingebbar

/* Welche Kategorie-Felder gerade im Tippen stehen — als Schluessel, nicht als
 * DOM-Verweis.
 *
 * **Der Modus muss den Neuaufbau ueberleben.** Die Ansicht wird nach jeder
 * Bruecken-Antwort neu gebaut, und der Entwurf speichert 900 ms nach der
 * letzten Aenderung von selbst: wer „+ neue Kategorie" waehlt und anfaengt zu
 * tippen, saehe sein Feld mitten im Wort wieder zur Auswahlliste werden.
 * Dieselbe Mechanik wie bei `offeneHilfen` und `klappZu` — und derselbe Grund,
 * aus dem `fokusMerken()` existiert. */
const kategorieFrei = new Set();

/** Was in der Lern-Vorschau schon getippt, aber noch nicht uebernommen ist.
 *
 * Eine Kategorie, die in Zeile 1 entsteht, muss in Zeile 2 waehlbar sein —
 * sonst tippt man sie zwanzigmal und beim einundzwanzigsten Mal anders. */
function kategorieZusatz() {
  return [...document.querySelectorAll(".kategorie-wahl")]
    .map((n) => (n.wert ? n.wert() : "")).filter(Boolean);
}

/** Zieht die Auswahllisten aller Kategorie-Bedienelemente nach. */
function kategorieOptionenAktualisieren() {
  for (const n of document.querySelectorAll(".kategorie-wahl")) {
    if (n.optionenNeu) n.optionenNeu();
  }
}

function kategorieWahl(wert, beim_setzen, opts) {
  opts = opts || {};
  const huelle = el("span", {class: "kategorie-wahl"
    + (opts.klasse ? " " + opts.klasse : "")});
  // Woran der Tipp-Modus haengt. Ohne Schluessel gibt es ihn nicht — dann
  // entscheidet allein, ob es etwas zu waehlen gibt.
  const schluessel = opts.schluessel || "";
  let aktuell = String(wert || "");
  let gesperrt = false;

  const werte = () => kategorienWerte(kategorieZusatz().concat(aktuell));
  const melde = (v) => {
    aktuell = v;
    // Ein uebernommener Name steht beim naechsten Aufbau in der Liste — also
    // ist das Tippen hier zu Ende. Bleibt das Feld leer, bleibt es offen:
    // sonst waere ein Vertipper („Enter" auf nichts) ein Rueckwurf in die
    // Auswahl, und man faengt von vorn an.
    if (schluessel && v) kategorieFrei.delete(schluessel);
    beim_setzen(v);
  };

  const auswahlfeld = () => {
    const s = el("select", {title: opts.titel
      || "Vorhandene Kategorie wählen — oder unten eine neue anlegen"});
    s.optionen = () => {
      const alt = aktuell;
      s.replaceChildren(
        el("option", {value: ""}, opts.leer || "— ohne Kategorie —"),
        ...werte().map((k) => el("option", {value: k}, k)),
        el("option", {value: KATEGORIE_NEU}, "＋ neue Kategorie …"));
      s.value = alt;
    };
    s.optionen();
    s.addEventListener("change", () => {
      if (s.value === KATEGORIE_NEU) return tausche(true, "");
      melde(s.value);
    });
    return s;
  };

  const textfeld = (vorgabe) => {
    const e = el("input", {value: vorgabe, autocomplete: "off",
      placeholder: opts.platzhalter || "Neue Kategorie",
      title: "Neuen Namen tippen — beim nächsten Item steht er in der Liste"});
    e.addEventListener("change", () => melde(e.value.trim()));
    e.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") e.blur();
      // ESC fuehrt zurueck in die Liste, sonst waere das Tippen eine Falltuer:
      // hinein kommt man mit einem Klick, heraus nur ueber einen Umweg.
      if (ev.key === "Escape" && werte().length) { ev.stopPropagation(); tausche(false); }
    });
    return e;
  };

  function tausche(frei, vorgabe, merken) {
    if (schluessel && merken !== false) {
      if (frei) kategorieFrei.add(schluessel);
      else kategorieFrei.delete(schluessel);
    }
    const neu = frei ? textfeld(vorgabe === undefined ? aktuell : vorgabe)
                     : auswahlfeld();
    neu.disabled = gesperrt;
    huelle.replaceChildren(neu);
    huelle.wert = () => (frei ? neu.value.trim() : neu.value);
    huelle.optionenNeu = frei ? null : neu.optionen;
    if (frei && merken !== false) neu.focus();
  }

  // **Getippt wird nur, wenn es nichts zu waehlen gibt** — oder wenn der
  // aktuelle Wert (ein Vorschlag der Lern-Vorschau) noch in keiner Liste steht,
  // oder wenn hier vor dem Neuaufbau schon getippt wurde.
  const vorhandene = kategorienWerte(kategorieZusatz());
  tausche(!vorhandene.length
          || (schluessel && kategorieFrei.has(schluessel))
          || (!!aktuell && !vorhandene.some((k) => k === aktuell)),
          undefined, false);
  huelle.sperren = (an) => {
    gesperrt = an;
    for (const n of huelle.children) n.disabled = an;
  };
  huelle.gesperrt = () => gesperrt;
  // Von aussen setzen (Sammel-Aktion der Lern-Vorschau). Steht der Wert nicht
  // in der Liste, muss das Feld dafuer ins Tippen wechseln — sonst schluckt
  // ein <select> ihn stillschweigend.
  huelle.setzen = (v) => {
    aktuell = String(v || "");
    const da = kategorienWerte(kategorieZusatz());
    tausche(!!aktuell && !da.some((k) => k === aktuell), aktuell);
    if (huelle.optionenNeu) huelle.optionenNeu();
    beim_setzen(aktuell);
  };
  return huelle;
}

function itemsDerKategorie(kategorie) {
  return SC.items.filter((i) => (i.kategorie || "") === (kategorie || ""))
    .slice().sort((a, b) => a.prioritaet - b.prioritaet || a.name.localeCompare(b.name, "de"));
}

/** Sichtbare Rangfolge statt einer Zahl ohne Zusammenhang. Prioritaeten gelten
 *  innerhalb einer Kategorie; deshalb waere eine globale Liste irrefuehrend. */
function prioritaetsUebersicht(kategorie, aktuellerName) {
  if (!kategorie) {
    return el("p", {class: "hinweis prioritaets-hinweis"},
      "Ohne Kategorie konkurriert dieses Item mit keinem anderen Item.");
  }
  const items = itemsDerKategorie(kategorie);
  return el("div", {class: "prioritaets-uebersicht"},
    el("span", {class: "klein"}, "Rangfolge in „" + kategorie + "“"),
    el("div", {class: "prioritaets-chips"}, items.map((i) => el("span", {
      class: "prioritaets-chip" + (i.name === aktuellerName ? " aktuell" : ""),
      title: i.name + " · Priorität " + i.prioritaet,
    }, "P" + i.prioritaet + " · " + i.name))),
    el("small", {class: "eingabe-hilfe"},
      "Kleinere Zahl gewinnt; bei gleicher Zahl entscheidet die Scan-Reihenfolge."));
}

function allePrioritaeten() {
  if (!SC.kategorien.length) return null;
  return el("div", {class: "prioritaeten-alle"},
    el("span", {class: "klein"}, "Bereits gesetzte Prioritäten"),
    SC.kategorien.map((k) => el("div", {class: "prioritaeten-kategorie"},
      el("b", {}, k),
      el("span", {}, itemsDerKategorie(k).map((i) => "P" + i.prioritaet + " " + i.name).join(" · ")))));
}

/** Noch nicht uebernommene Kategorien gehoeren bereits zur aktuellen Eingabe.
 *  Die Vorschau darf nicht erst nach „Ausgewaehlte uebernehmen" von ihnen
 *  erfahren, sonst muss derselbe freie Text in jeder Zeile neu getippt werden. */
/** Eine in einer Zeile entstandene Kategorie in allen anderen waehlbar machen.
 *
 * Ohne das tippt man dieselbe Kategorie in zwanzig Zeilen — und beim
 * einundzwanzigsten Mal anders. Fuellte frueher eine `<datalist>`; seit die
 * Kategorie ein eigenes Bedienelement ist, zieht es dessen Auswahllisten nach. */
function scanReviewKategorienAktualisieren() {
  kategorieOptionenAktualisieren();
}

function scanReviewKategorieAufAuswahl(eingabe) {
  const wert = eingabe.wert();
  if (!wert) return;
  for (const zeile of document.querySelectorAll(".scan-review-zeile")) {
    const haken = zeile.querySelector(".scan-review-haken");
    const kategorie = zeile.querySelector(".scan-review-kategorie");
    if (haken && haken.checked && kategorie && !kategorie.gesperrt()) {
      kategorie.setzen(wert);
    }
  }
}

function prioritaetsfeld(wert, kategorie, beim_setzen) {
  const eingabe = el("input", {type: "number", value: wert, min: 0, step: 1});
  eingabe.addEventListener("change", () => {
    if (eingabe.value.trim() !== "") beim_setzen(Number(eingabe.value));
  });
  eingabe.addEventListener("keydown", (e) => { if (e.key === "Enter") eingabe.blur(); });
  const nachVorn = el("button", {
    class: "btn still", type: "button", disabled: !kategorie,
    title: kategorie
      ? "Ganz nach vorn; alle anderen Items in „" + kategorie + "“ rutschen um eins nach hinten"
      : "Dafür braucht das Item eine Kategorie",
    onclick: () => beim_setzen(0),
  }, "Ganz nach vorn");
  return el("div", {class: "prioritaets-feld"},
    el("label", {class: "feld"}, "Priorität", el("div", {class: "reihe"}, eingabe, nachVorn)),
    el("small", {class: "eingabe-hilfe"},
      "0 macht daraus P1 und verschiebt alle anderen dieser Kategorie um +1. " +
      "Eine konfigurierte Marktwert-Datei hat beim Lauf Vorrang."));
}

function zahlfeld(beschriftung, wert, beim_setzen, extra, hilfe, schluessel) {
  return feld(beschriftung, wert, (v) => beim_setzen(Number(v) || 0),
              Object.assign({type: "number"}, extra || {}), hilfe, schluessel);
}

/** Farbwähler mit Hex daneben. Ohne gemessene Farbe bleibt er leer statt eine
 *  zu behaupten — dieselbe Regel wie beim Quadrat in der Punkte-Palette. */
function farbfeld(beschriftung, hex, beim_setzen, hilfe, schluessel) {
  const wahl = el("input", {type: "color", value: hex || "#000000",
                            style: "width:44px;height:28px;padding:2px"});
  const text = el("span", {class: "klein mono"}, hex || "keine Farbe aufgenommen");
  wahl.addEventListener("change", () => beim_setzen(wahl.value.toUpperCase()));
  return el("label", {class: "feld"}, beschriftet(beschriftung, hilfe, schluessel),
    el("div", {class: "reihe"}, wahl, text));
}

function schalter(beschriftung, an, beim_setzen, unbestimmt) {
  const box = el("input", {type: "checkbox"});
  box.checked = !!an;
  // `indeterminate` geht nur ueber die Eigenschaft, nicht ueber ein Attribut.
  if (unbestimmt) box.indeterminate = true;
  // Aus dem Mischzustand heraus heisst ein Klick „alle" — das ist der Griff,
  // den man dort will. Ohne das entschiede der Browser (er setzt checked=true),
  // was zufaellig dasselbe waere; ausgeschrieben haengt es nicht am Zufall.
  box.addEventListener("change", () => beim_setzen(unbestimmt ? true : box.checked));
  return el("label", {class: "an"}, box, beschriftung);
}

function auswahl(beschriftung, werte, aktuell, beim_setzen, hilfe, schluessel) {
  const s = el("select");
  for (const w of werte) {
    const o = el("option", {value: String(w.wert)}, w.text);
    if (String(w.wert) === String(aktuell)) o.selected = true;
    s.appendChild(o);
  }
  s.addEventListener("change", () => beim_setzen(s.value));
  return beschriftung ? el("label", {class: "feld"}, beschriftet(beschriftung, hilfe, schluessel), s) : s;
}

/* ---------------------------------------------------- Fokus ueber den Neuaufbau
 *
 * **Jede Meldung baut die Ansicht neu — und nimmt dabei das Feld weg, in dem man
 * gerade steht.** Tipp-Felder melden beim Verlassen (`change`), also loest genau
 * der TAB-Sprung den Neuaufbau aus; bis die Bruecke geantwortet hat, liegt der
 * Fokus schon im naechsten Feld, und `replaceChildren()` wirft es weg. Sichtbar
 * wurde das beim Item: Namen tippen, TAB nach Kategorie — und der Cursor war weg.
 *
 * Gemerkt wird die POSITION unter den Eingabefeldern des naechsten Elements mit
 * `id`, nicht das Element selbst (das gibt es danach nicht mehr) und auch kein
 * eigener Schluessel an jedem Feld (den muesste jeder Bauer mitschleppen, und ein
 * vergessener faellt nicht auf). Der Aufbau des Inspektors haengt am Typ des
 * gewaehlten Dings, nicht an seinen Werten — die Position bleibt also stehen. */
function fokusMerken() {
  const a = document.activeElement;
  if (!a || !["INPUT", "SELECT", "TEXTAREA"].includes(a.tagName)) return null;
  const kasten = a.closest("[id]");
  if (!kasten) return null;
  const felder = [...kasten.querySelectorAll("input, select, textarea")];
  const i = felder.indexOf(a);
  if (i < 0) return null;
  // Zahl- und Farbfelder haben keine Auswahl - dann bleibt nur der Fokus.
  let start = null, ende = null;
  try { start = a.selectionStart; ende = a.selectionEnd; } catch (e) { /* egal */ }
  return {id: kasten.id, i: i, start: start, ende: ende};
}

function fokusHerstellen(merk) {
  if (!merk) return;
  const kasten = document.getElementById(merk.id);
  if (!kasten) return;
  const ziel = [...kasten.querySelectorAll("input, select, textarea")][merk.i];
  if (!ziel) return;
  ziel.focus();
  if (merk.start !== null) {
    try { ziel.setSelectionRange(merk.start, merk.ende); } catch (e) { /* egal */ }
  }
}

function segment(werte, aktuell, beim_setzen) {
  return el("div", {class: "segment"}, werte.map((w) =>
    el("button", {class: w.wert === aktuell ? "an" : "", onclick: () => beim_setzen(w.wert)},
       w.text)));
}

function ueberschrift(text, hilfe, schluessel) {
  return el("span", {class: "ueberschrift mitinfo"}, text, info(hilfe, schluessel));
}

/* -------------------------------------------------------------------- Brücke */

let S = null;             // letzte Momentaufnahme
let ziehen = null;        // was gerade gezogen wird
let aktiveAblage = null;  // hervorgehobene Einfügestelle
let offeneFrage = null;

function warteAufBruecke() {
  return new Promise((fertig) => {
    if (window.pywebview && window.pywebview.api) return fertig();
    window.addEventListener("pywebviewready", () => fertig(), {once: true});
  });
}

/** Ein Befehl an die Brücke. Antwort ist immer die neue Momentaufnahme. */
async function ruf(name, daten) {
  try {
    const antwort = await window.pywebview.api[name](daten === undefined ? null : daten);
    uebernimm(antwort);
  } catch (e) {
    setzeStatus({text: String(e && e.message ? e.message : e), art: "err"});
  }
}

/** Wie ruf(), aber die Antwort ersetzt NICHT die Momentaufnahme.
 *
 * Für alles, was gefragt und nicht befohlen wird: Sequenzliste, Laufstatus.
 * Über `ruf()` geholt würde ihre Antwort in `S` landen und den Editor-Zustand
 * zerschiessen — ein Blick in die Übersicht wäre dann ein Datenverlust. */
async function frage(name, daten) {
  try {
    return await window.pywebview.api[name](daten === undefined ? null : daten);
  } catch (e) {
    setzeStatus({text: String(e && e.message ? e.message : e), art: "err"});
    return null;
  }
}

function uebernimm(neu) {
  if (!neu) return;
  S = neu;
  zeichne();
  if (S.frage) zeigeFrage(S.frage);
}

/* ----------------------------------------------------------------- Ansichten */

let ansicht = "editor";

/** Schaltet zwischen Editor, Übersicht und Live-Run um.
 *
 * Reiner Oberflächenzustand: die Brücke erfährt davon nichts, und in der
 * Momentaufnahme steht er auch nicht — er ändert ja nichts an der Sequenz.
 * Der Editor bleibt dabei im Dokument stehen (nur `hidden`), damit
 * Scrollstand und ungespeicherte Eingaben den Ausflug überleben. */
function setzeAnsicht(neu) {
  ansicht = neu;
  for (const t of document.querySelectorAll(".tab"))
    t.classList.toggle("an", t.dataset.ansicht === neu);
  $("rumpf").hidden = neu !== "editor";
  $("sicht-sequenzen").hidden = neu !== "sequenzen";
  $("sicht-lauf").hidden = neu !== "lauf";
  $("sicht-config").hidden = neu !== "einstellungen";
  $("sicht-scans").hidden = neu !== "scans";
  // Die Sequenz-Bedienelemente im Kopf gehoeren nur zur Sequenz. Einstellungen
  // und Scans bearbeiten andere Dateien und haben ihren eigenen Speichern-Knopf.
  for (const n of document.querySelectorAll("[data-sequenz]"))
    n.hidden = neu === "einstellungen" || neu === "scans";
  if (neu === "scans") zeichneScans(!SC);
  if (neu === "sequenzen") zeichneSequenzenliste();
  // Bei jedem Oeffnen frisch von Platte: der Hauptprozess schreibt dieselbe
  // Datei (Debug-Stufen, Import, Factory Reset).
  if (neu === "einstellungen") zeichneEinstellungen(true);
  laufTaktSetzen(neu === "lauf");
}

/* ------------------------------------------------------------------ Zeichnen */

function zeichne() {
  if (!S) return;
  const merk = fokusMerken();
  $("fuss-datei").textContent = S.datei || "";
  $("fuss-punkte").textContent = S.punkte.length + " Punkte";
  $("punkt-offen").hidden = !S.dirty;
  $("fuss-lampe").classList.toggle("offen", !!S.dirty);
  $("fuss-lampe").title = S.dirty ? "ungespeicherte Änderungen" : "gespeichert";
  // Der Fenstertitel bleibt schlicht: in der Titelleiste steht sonst der
  // Sequenzname doppelt (er steht schon im Kopf der Seite), und das Fenster
  // findet sich in der Taskleiste besser über einen gleichbleibenden Namen.
  document.title = "Sequenz-Studio";
  setzeStatus(S.status);
  zeichneKopf();
  zeichneSequenz();
  zeichnePunkte();
  zeichnePhasen();
  zeichneInspektor();
  fokusHerstellen(merk);
}

function setzeStatus(status) {
  const n = $("status");
  n.textContent = (status && status.text) || "";
  // Mit Praefix: „info" allein ist die Klasse des ⓘ-Knopfes (13px, rund), und ein
  // Status mit dieser Art bekam dessen Gestalt — ein leerer Kreis neben dem
  // Start-Knopf, den niemand zuordnen konnte.
  n.className = "status art-" + ((status && status.art) || "info");
}

function zeichneKopf() {
  const s = $("seq-auswahl");
  s.replaceChildren();
  if (!S.sequenzen.length) s.appendChild(el("option", {value: ""}, "(keine gespeichert)"));
  // Eine frisch angelegte Sequenz steht noch in keiner Datei — ohne diesen Eintrag
  // zeigte die Liste einen fremden Namen an, während man an ihr arbeitet.
  if (S.name && !S.sequenzen.includes(S.name)) {
    const o = el("option", {value: S.name}, S.name + " (ungespeichert)");
    o.selected = true;
    s.appendChild(o);
  }
  for (const name of S.sequenzen) {
    const o = el("option", {value: name}, name);
    if (name === S.name) o.selected = true;
    s.appendChild(o);
  }
}

function zeichneSequenz() {
  if (document.activeElement !== $("seq-name")) $("seq-name").value = S.name;
  if (document.activeElement !== $("seq-zyklen")) $("seq-zyklen").value = S.zyklen;
  if (document.activeElement !== $("seq-info")) $("seq-info").value = S.beschreibung;
  $("seq-bloecke").textContent = S.phasen.reduce((n, p) => n + p.bloecke.length, 0);
}

function zeichnePunkte() {
  const filter = $("punkt-filter").value.trim().toLowerCase();
  const liste = S.punkte.filter((p) => !filter ||
      (p.name + " #" + p.id + " " + p.x + "," + p.y).toLowerCase().includes(filter));
  $("punkte-zahl").textContent = liste.length + "/" + S.punkte.length;
  const ziel = $("punkte");
  ziel.replaceChildren();
  if (!S.punkte.length) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Noch keine Punkte aufgenommen. Im Hauptprozess mit CTRL+ALT+A anlegen."));
    return;
  }
  for (const p of liste) {
    ziel.appendChild(el("div", {
      class: "punkt", draggable: "true", title: p.quelle || "",
      ondragstart: (e) => { ziehen = {art: "punkt", punkt: p.id};
                            e.dataTransfer.effectAllowed = "copy"; },
      ondragend: () => { ziehen = null; loescheAblage(); },
    },
      // Ohne aufgenommene Farbe bleibt das Feld LEER (nur Rahmen). Vorher stand
      // dort die Linienfarbe als Füllung — das behauptete eine Farbe, die nie
      // gemessen wurde, und der Farb-Trigger hängt an derselben Quelle.
      el("span", {class: "kugel" + (p.farbe ? "" : " ohne"),
                  title: p.farbe ? "" : "keine Farbe aufgenommen",
                  style: p.farbe ? "background:" + p.farbe : ""}),
      el("span", {class: "nr"}, "#" + p.id),
      el("span", {class: "name"}, p.name),
      el("span", {class: "xy"}, p.x + "," + p.y)));
  }
}

/* --------------------------------------------------------------------- Board */

function zeichnePhasen() {
  const ziel = $("phasen");
  ziel.replaceChildren();
  for (const phase of S.phasen) ziel.appendChild(zeichnePhase(phase));
  ziel.appendChild(el("div", {class: "phase"},
    el("button", {class: "leerzone", onclick: () => ruf("phase_anhaengen")},
       "+ Loop-Phase")));
}

function zeichnePhase(phase) {
  const kopf = el("div", {class: "phase-kopf " + phase.art});
  // INIT und END tragen keinen frei wählbaren Namen — sie bekommen deshalb auch
  // kein Eingabefeld, das nichts annimmt.
  const name = phase.art === "loop"
    ? el("input", {class: "phase-name wachse", value: phase.name})
    : el("span", {class: "phase-name wachse"}, phase.name);
  name.addEventListener("change", () => ruf("phase_setzen",
    {phase: phase.index, feld: "name", wert: name.value}));
  // Kein „×N" als Marke daneben: bei einer Loop-Phase stünde der Wert damit
  // zweimal im Kopf, einmal als Zahl zum Anfassen und einmal als Abzeichen, das
  // sich nicht ändern lässt. Die zugehörige Klasse `.zaehler` ist damit
  // ersatzlos weg — die Sequenzen-Übersicht benutzt ihre eigene (`.zahl`).
  kopf.appendChild(el("div", {class: "reihe"}, name,
    el("span", {class: "klein mono"}, phase.bloecke.length + " Schritte")));

  if (phase.art === "loop") {
    const wdh = el("input", {type: "number", min: "1", value: phase.wiederholungen,
                             style: "width:70px", title: "Wiederholungen"});
    wdh.addEventListener("change", () => ruf("phase_setzen",
      {phase: phase.index, feld: "wiederholungen", wert: Number(wdh.value) || 1}));
    const start = el("input", {value: phase.start, placeholder: "HH:MM",
                               style: "width:74px", title: "Start erst ab dieser Uhrzeit"});
    start.addEventListener("change", () => ruf("phase_setzen",
      {phase: phase.index, feld: "start", wert: start.value}));
    // Das „×" wandert vor das Feld: ohne die Marke daneben muss die Zahl selbst
    // sagen, was sie ist. Gedämpft, nicht in Akzentfarbe — es beschriftet nur.
    //
    // Und der Löschknopf ist deshalb KEIN „×" mehr: zwei gleiche Zeichen in einer
    // Zeile, eines als Beschriftung und eines als „Phase weg", ist die Sorte
    // Verwechslung, die man genau einmal macht.
    kopf.appendChild(el("div", {class: "phase-werkzeug"},
      el("span", {class: "klein mono"}, "×"), wdh, start,
      el("button", {class: "btn still gefahr", title: "Phase löschen",
                    onclick: () => ruf("phase_loeschen", {phase: phase.index})},
         papierkorb())));
  }

  const spalte = el("div", {class: "phase"}, kopf);
  phase.bloecke.forEach((block, i) => {
    spalte.appendChild(ablage(phase.index, i));
    spalte.appendChild(zeichneKarte(phase, block));
  });
  spalte.appendChild(ablage(phase.index, phase.bloecke.length));
  spalte.appendChild(el("button", {
    class: "leerzone",
    onclick: () => ruf("block_anhaengen", {phase: phase.index}),
    ondragover: (e) => { if (ziehen) { e.preventDefault(); markiere(e.currentTarget); } },
    ondragleave: () => loescheAblage(),
    ondrop: (e) => abwerfen(e, phase.index, phase.bloecke.length),
  }, phase.bloecke.length ? "+ Block" : "leer — Block anlegen oder Punkt herziehen"));
  return spalte;
}

/** Papierkorb-Zeichen als Inline-SVG — nichts wird von aussen geladen. */
function papierkorb() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("width", "13");
  svg.setAttribute("height", "13");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  const pfad = document.createElementNS(ns, "path");
  pfad.setAttribute("d", "M4 6h16M9 6V4h6v2M6 6l1 14h10l1-14M10 11v5M14 11v5");
  svg.appendChild(pfad);
  return svg;
}

/** Einfügestelle zwischen zwei Karten: nur ein Strich, der aufleuchtet. */
function ablage(phase, zeile) {
  return el("div", {
    class: "ablage",
    ondragover: (e) => { if (ziehen) { e.preventDefault(); markiere(e.currentTarget); } },
    ondragleave: () => loescheAblage(),
    ondrop: (e) => abwerfen(e, phase, zeile),
  });
}

function markiere(n) {
  if (aktiveAblage === n) return;
  loescheAblage();
  aktiveAblage = n;
  n.classList.add("aktiv");
}

function loescheAblage() {
  if (aktiveAblage) aktiveAblage.classList.remove("aktiv");
  aktiveAblage = null;
}

function abwerfen(e, phase, zeile) {
  e.preventDefault();
  e.stopPropagation();
  loescheAblage();
  const was = ziehen;
  ziehen = null;
  if (!was) return;
  if (was.art === "punkt") ruf("punkt_einfuegen", {phase: phase, zeile: zeile, punkt: was.punkt});
  else ruf("ziehen", {von_phase: was.phase, von_zeile: was.zeile,
                      nach_phase: phase, nach_zeile: zeile});
}

function zeichneKarte(phase, block) {
  // Der Titel steht in der Kopfzeile, nicht im Leib: dort traegt er die Typfarbe
  // mit und steht NEBEN dem Typ statt darunter — eine Zeile weniger pro Karte,
  // und bei 50 Karten untereinander ist das der Unterschied.
  const leib = el("div", {class: "karte-leib"},
    block.zeilen.map((z) => el("div", {class: "karte-zeile"}, z)));

  if (block.farbfeld) {
    leib.appendChild(el("div", {class: "karte-farbe"},
      el("span", {class: "feldchen", style: "background:" + block.farbfeld}),
      block.farbtext));
  }
  if (block.else_text) {
    // Ein ELSE ohne Bedingung feuert nie — auf der Karte stuende es sonst als
    // Zusage da („sonst: Schritt überspringen"), die nichts einloest.
    leib.appendChild(el("div", {class: "karte-else" + (block.else_greift ? "" : " tot")},
      block.else_text + (block.else_greift ? "" : " · greift nie")));
  }

  return el("div", {
    class: "karte" + (block.gewaehlt ? " gewaehlt" : ""),
    draggable: "true",
    onclick: (e) => ruf("waehlen", {
      phase: phase.index, zeile: block.zeile,
      modus: e.ctrlKey || e.metaKey ? "dazu" : (e.shiftKey ? "bereich" : "einzeln")}),
    ondragstart: (e) => { ziehen = {art: "block", phase: phase.index, zeile: block.zeile};
                          e.dataTransfer.effectAllowed = "move"; },
    ondragend: () => { ziehen = null; loescheAblage(); },
    ondragover: (e) => {
      if (!ziehen) return;
      e.preventDefault();
      const r = e.currentTarget.getBoundingClientRect();
      const unten = e.clientY > r.top + r.height / 2;
      const strich = unten ? e.currentTarget.nextElementSibling
                           : e.currentTarget.previousElementSibling;
      if (strich && strich.classList.contains("ablage")) markiere(strich);
    },
    ondrop: (e) => {
      const r = e.currentTarget.getBoundingClientRect();
      abwerfen(e, phase.index, block.zeile + (e.clientY > r.top + r.height / 2 ? 1 : 0));
    },
  },
    el("div", {class: "karte-kopf", style: "background:" + block.farbe},
      el("span", {class: "karte-typ"}, block.label),
      block.titel ? el("span", {class: "karte-titel"}, block.titel) : null,
      block.prueft ? el("span", {class: "marke-klein", title: "prüft nach der Aktion nach"},
                        "prüft") : null,
      block.warnung ? el("span", {class: "marke-klein warn"}, block.warnung) : null,
      el("span", {class: "karte-nr"}, String(block.zeile + 1).padStart(2, "0"))),
    leib);
}

/* -------------------------------------------------------- Ansicht: Sequenzen */

/** Zeitstempel (Sekunden) als „TT.MM.JJJJ HH:MM“.
 *
 * Von Hand statt `toLocaleString()`: das Fenster erbt seine Locale von der
 * WebView, und die muss nicht die der Konsole sein. Ein Datum, das mal
 * deutsch und mal amerikanisch herum steht, liest man zweimal falsch. */
function zeitpunkt(sekunden) {
  if (!sekunden) return "—";
  const d = new Date(sekunden * 1000);
  const zz = (n) => String(n).padStart(2, "0");
  return zz(d.getDate()) + "." + zz(d.getMonth() + 1) + "." + d.getFullYear() +
         " " + zz(d.getHours()) + ":" + zz(d.getMinutes());
}

/** Eine Phasenfarbe aus dem Stylesheet (`--init` / `--loop` / `--end`).
 *
 * Der Balken setzt seine Segmente per Inline-Stil — die Breite ist gerechnet,
 * eine Klasse trägt er nicht. Die Farbe deshalb trotzdem aus `:root` zu holen
 * statt sie hier auszuschreiben, hält die Palette an einer Stelle: sonst wäre
 * die Übersicht die eine Ansicht, in der ein Phasenton nach dem nächsten
 * Umfärben nicht mehr stimmt. Gemerkt wird sie, weil `getComputedStyle` sonst
 * bei zwanzig Sequenzkarten sechzigmal liefe. */
const _phasenfarben = {};
function phasenFarbe(art) {
  if (!(art in _phasenfarben)) {
    _phasenfarben[art] = getComputedStyle(document.documentElement)
      .getPropertyValue("--" + art).trim() || "#64748B";
  }
  return _phasenfarben[art];
}

/** INIT / Loop-Phasen / END als Segmente, Breite nach Schrittzahl.
 *
 * Leere Phasen fallen raus statt als Strich stehenzubleiben: ein Segment der
 * Breite 0 sagt nichts, kostet aber eine Lücke.
 *
 * INIT und END standen hier auf demselben Grau: der Balken sagte damit zwar,
 * WIE VIEL am Anfang und am Ende liegt, aber nicht, dass es Anfang und Ende
 * sind — und es war die einzige Ansicht, die die Phasenfarben nicht sprach. */
function phasenBalken(s) {
  const teile = [{n: s.init, farbe: phasenFarbe("init"), was: "INIT: " + s.init}]
    .concat((s.phasen || []).map((p) => ({n: p.schritte, farbe: phasenFarbe("loop"),
      was: p.name + ": " + p.schritte + " Schritte ×" + p.wiederholungen +
           (p.start ? " ab " + p.start : "")})))
    .concat([{n: s.end, farbe: phasenFarbe("end"), was: "END: " + s.end}]);
  const summe = teile.reduce((a, t) => a + t.n, 0) || 1;
  return el("div", {class: "balken"}, teile.filter((t) => t.n).map((t) =>
    el("span", {style: "flex:" + t.n / summe + ";background:" + t.farbe, title: t.was})));
}

async function zeichneSequenzenliste() {
  const ziel = $("sicht-sequenzen");
  const liste = await frage("sequenz_liste");
  // Zwischen Frage und Antwort kann umgeschaltet worden sein — dann gehoert
  // die Antwort in eine Ansicht, die niemand mehr ansieht.
  if (ansicht !== "sequenzen") return;
  ziel.replaceChildren();
  if (!liste || !liste.length) {
    // grid-column: sonst stünde der Text in der ersten Spalte des Rasters und
    // wäre auf einem breiten Fenster in die linke Ecke gequetscht.
    ziel.appendChild(el("p", {class: "leer", style: "grid-column:1/-1"},
      "Noch keine Sequenz gespeichert. Im Editor eine anlegen (Neu) oder im " +
      "Hauptprozess mit CTRL+ALT+J eine aufnehmen."));
    return;
  }
  for (const s of liste) ziel.appendChild(seqKarte(s));
}

function seqKarte(s) {
  const karte = el("div", {class: "seq-karte" + (s.offen ? " offen" : "") +
                                  (s.defekt ? " defekt" : "")});
  karte.appendChild(el("div", {class: "seq-kopf"},
    el("span", {class: "seq-name"}, s.name),
    s.offen ? el("span", {class: "zahl", style: "color:var(--accent)"}, "offen") : null));

  if (s.defekt) {
    karte.appendChild(el("p", {class: "seq-warn"},
      "Nicht ladbar — die Datei ist beschädigt oder kein gültiges Sequenz-Format. " +
      "Sie bleibt unangetastet; nachsehen lohnt sich in " + s.datei + "."));
  } else {
    if (s.beschreibung) karte.appendChild(el("p", {class: "seq-notiz"}, s.beschreibung));
    karte.appendChild(phasenBalken(s));
    karte.appendChild(el("div", {class: "seq-zahlen"},
      el("span", {class: "zahl"}, s.schritte + " Schritte"),
      el("span", {class: "zahl"}, s.phasen.length + " Loop-Phasen"),
      el("span", {class: "zahl"}, s.zyklen ? s.zyklen + " Zyklen" : "endlos")));
    if (s.warnungen && s.warnungen.length) {
      karte.appendChild(el("p", {class: "seq-warn"},
        s.warnungen.length + "× Scan ohne Konfiguration — " + s.warnungen[0] +
        (s.warnungen.length > 1 ? " u. a." : "")));
    }
  }

  karte.appendChild(el("div", {class: "seq-fuss"},
    el("span", {class: "klein mono wachse"}, s.datei + " · " + zeitpunkt(s.geaendert)),
    // Öffnen geht über den vorhandenen Befehl, nicht über einen neuen: dann
    // greift auch die vorhandene Rückfrage bei ungespeicherten Änderungen.
    s.defekt ? null : el("button", {
      class: "btn" + (s.offen ? "" : " haupt"), disabled: s.offen,
      onclick: async () => { await ruf("laden", {name: s.name}); setzeAnsicht("editor"); },
    }, s.offen ? "geöffnet" : "Öffnen")));
  return karte;
}

/* --------------------------------------------------------- Ansicht: Live-Run */

let laufTakt = null;
let laufLief = false;

/** Der schnelle Takt läuft nur, solange der Reiter offen ist.
 *
 * Ein Fenster, das im Hintergrund alle 500 ms eine Datei liest, tut das die
 * ganze Nacht — und die Datei liegt auf derselben Platte, auf die der Worker
 * gerade schreibt. Daneben gibt es den langsamen Puls (s.u.), der nur die eine
 * Frage stellt: hat gerade ein Lauf angefangen? */
function laufTaktSetzen(an) {
  if (laufTakt) { clearInterval(laufTakt); laufTakt = null; }
  if (!an) return;
  zeichneLauf();
  laufTakt = setInterval(zeichneLauf, 500);
}

/** Springt beim Start eines Laufs von selbst in die Live-Ansicht.
 *
 * **Nur auf der Flanke** (nichts → läuft), nicht solange etwas läuft: sonst
 * käme man während eines Durchgangs nicht mehr in den Editor zurück, die
 * Ansicht würde jedes Mal zurückspringen. Wer den Reiter wechselt, während es
 * läuft, hat sich dafür entschieden.
 *
 * Der Puls ist bewusst der langsamste, der die Frage noch rechtzeitig
 * beantwortet: ein Start ist nichts, was man in einer halben Sekunde verpasst.
 */
function laufFlanke(aktiv) {
  if (aktiv && !laufLief && ansicht !== "lauf") setzeAnsicht("lauf");
  laufLief = aktiv;
  const knopf = $("btn-lauf");
  knopf.textContent = aktiv ? "■ Stoppen" : "▶ Starten";
  knopf.classList.toggle("gefahr", aktiv);
}

/** Einen Lauf-Befehl abschicken, nachfassen — und melden, wenn niemand zuhört. */
async function laufSchicken(befehl) {
  await ruf("lauf_befehl", {befehl: befehl});
  laufNachfassen();
  // Der Hauptprozess leert den Briefkasten beim Lesen. Liegt der Befehl nach
  // zwei Sekunden immer noch da, ist keiner da — dann darf hier nicht
  // „gestartet" stehen bleiben.
  setTimeout(async () => {
    if (await frage("befehl_offen")) {
      setzeStatus({art: "warn", text: "Kein Hauptprozess erreichbar — der Befehl " +
                                       "liegt noch und wird nicht nachgeholt."});
    }
  }, 2000);
}

/** Sofort nachsehen, statt auf den nächsten Puls zu warten.
 *
 * Der Hauptprozess holt seinen Briefkasten alle 250 ms; bis der Lauf steht und
 * die Statusdatei liegt, vergeht knapp eine Sekunde. Ohne dieses Nachfassen
 * bliebe die Ansicht nach einem Druck auf „Starten" bis zu zwei Sekunden
 * unbeeindruckt stehen — und genau in dieser Lücke drückt man ein zweites Mal.
 */
function laufNachfassen() {
  for (const ms of [400, 900, 1600]) {
    setTimeout(async () => laufFlanke(!!((await frage("lauf_status")) || {}).aktiv), ms);
  }
}

function flankenPuls() {
  setInterval(async () => {
    if (ansicht === "lauf") return;      // dort fragt schon der schnelle Takt
    const z = await frage("lauf_status");
    laufFlanke(!!(z && z.aktiv));
  }, 2000);
}

/** Sekunden als „2:05“ bzw. „1:23:45“. */
function dauer(sekunden) {
  const s = Math.max(0, Math.floor(sekunden));
  const zz = (n) => String(n).padStart(2, "0");
  const std = Math.floor(s / 3600);
  return (std ? std + ":" + zz(Math.floor(s / 60) % 60) : String(Math.floor(s / 60))) +
         ":" + zz(s % 60);
}

/** Restzeit knapp: unter zehn Sekunden mit Zehntel, darüber ganze Sekunden. */
function restzeit(sekunden) {
  const s = Math.max(0, sekunden);
  return (s < 10 ? s.toFixed(1) : String(Math.round(s))) + " s";
}

function hexfarbe(rgb) {
  return "#" + rgb.map((n) => Math.max(0, Math.min(255, Math.round(n)))
                              .toString(16).padStart(2, "0")).join("");
}

/** Ein Farbfeld mit Beschriftung — schraffiert, wenn nichts gemessen wurde. */
function farbstueck(text, rgb) {
  return el("div", {class: "stueck"},
    el("span", {class: "feldchen" + (rgb ? "" : " leer"),
                style: rgb ? "background:" + hexfarbe(rgb) : ""}),
    el("span", {class: "mono"}, text + (rgb ? " " + rgb.join(",") : " —")));
}

/** Worauf der laufende Block gerade wartet.
 *
 * Der Kasten ist die Antwort auf „seit 12 s" allein: bei einer Wartezeit von
 * 15 s sind zwölf Sekunden fast geschafft, bei einem Farb-Trigger mit 300 s
 * Timeout haben sie gerade erst angefangen — und ob überhaupt etwas Passendes
 * in Sicht ist, sagte die verstrichene Zeit gar nicht.
 *
 * Heruntergezählt wird **hier**, aus den absoluten Zeitstempeln der
 * Statusdatei. Mit Restwerten aus dem Worker ruckelte die Anzeige in dessen
 * Sekundentakt; beide Prozesse laufen auf derselben Maschine, also derselben Uhr.
 */
function warteKasten(w, jetzt) {
  if (!w) return null;
  const uebrig = w.bis ? Math.max(0, w.bis - jetzt) : null;
  // „Knapp" meint knapp vor dem TIMEOUT — eine Warnung. Eine ablaufende
  // Wartezeit ist keine: die soll ablaufen, und amber daneben hiesse Alarm, wo
  // alles nach Plan läuft.
  const knapp = w.art === "farbe" && uebrig !== null && uebrig <= 5;
  const kasten = el("div", {class: "warten art-" + (w.art === "farbe" ? "farbe" : "zeit") +
                                   (knapp ? " knapp" : "")});

  if (w.art === "farbe") {
    const treffer = w.distanz !== null && w.distanz !== undefined &&
                    w.distanz <= w.toleranz;
    // Das Ziel hängt an der Richtung: bei `bis_weg` ist ein Treffer genau das,
    // worauf NICHT gewartet wird — dieselbe Zahl, umgekehrte Bedeutung.
    const erfuellt = w.bis_weg ? !treffer : treffer;
    kasten.appendChild(el("div", {class: "kopf"},
      el("span", {class: "wachse"},
         (w.bis_weg ? "wartet, bis die Farbe weg ist" : "wartet auf die Farbe") +
         " bei (" + w.punkt.join(",") + ")"),
      el("span", {class: "klein mono"}, "seit " + dauer(jetzt - w.seit))));
    const angaben = el("div", {class: "wachse"},
      el("div", {class: "farbpaar"},
        farbstueck("soll", w.soll),
        farbstueck("jetzt", w.ist),
        w.distanz === null || w.distanz === undefined
          ? el("span", {class: "klein"}, "nicht messbar")
          : el("span", {class: "marke-treffer" + (erfuellt ? "" : " daneben")},
               "Δ " + w.distanz + " · " +
               (treffer ? "im Toleranzbereich" : "ausserhalb") + " (" + w.toleranz + ")")));
    // Das Bild steht links neben den Zahlen: es beantwortet die Anschlussfrage
    // („was ist da statt dessen zu sehen?"), nicht dieselbe.
    kasten.appendChild(w.bild
      ? el("div", {class: "pixel-kasten"},
          el("div", {class: "live-pixel"},
            el("div", {class: "rahmen"}, el("img", {src: w.bild, alt: ""})),
            el("span", {class: "schild"}, "LIVE-PIXEL")),
          angaben)
      : angaben);
  } else {
    kasten.appendChild(el("div", {class: "kopf"},
      el("span", {class: "wachse"}, w.text || "wartet"),
      el("span", {class: "rest"}, uebrig === null ? "" : "noch " + restzeit(uebrig))));
  }

  if (uebrig !== null) {
    kasten.appendChild(balken(jetzt - w.seit, w.bis - w.seit));
  }
  if (w.art === "farbe") {
    kasten.appendChild(el("span", {class: "klein"}, uebrig === null
      ? "ohne Timeout — wartet, bis die Farbe stimmt"
      : "Timeout in " + restzeit(uebrig) + " · danach " + (w.danach || "—")));
  } else if (uebrig !== null) {
    kasten.appendChild(el("span", {class: "klein"}, "von " + restzeit(w.gesamt || 0)));
  }
  return kasten;
}

function balken(ist, soll) {
  const anteil = soll > 0 ? Math.max(0, Math.min(1, ist / soll)) : 0;
  return el("div", {class: "fortschritt"}, el("span", {style: "width:" + anteil * 100 + "%"}));
}

/** Alle Phasen des Laufs nebeneinander, die laufende breit.
 *
 * Die Liste kommt aus dem Laufstatus, nicht aus der geöffneten Sequenz: laufen
 * kann eine ganz andere. Fehlt sie (Statusdatei einer älteren Fassung), bleibt
 * es bei der einen laufenden Phase — geraten wird nichts.
 *
 * „Abgeschlossen" gilt innerhalb des laufenden Zyklus: im nächsten Durchgang
 * sind dieselben Loop-Phasen wieder ausstehend. Anders wäre es gelogen, sobald
 * eine Sequenz mehr als einen Zyklus hat.
 */
function phasenLeiste(z, beendet) {
  const jetzige = z.phase_pos;
  const liste = Array.isArray(z.phasen) && z.phasen.length
    ? z.phasen
    : [{name: z.phase || "—", art: "loop", wiederholungen: z.wiederholungen || 1}];
  const pos = jetzige === undefined || jetzige === null || !Array.isArray(z.phasen)
    ? 0 : jetzige;

  return el("div", {class: "phasen-leiste"}, liste.map((p, i) => {
    // In der Zusammenfassung laeuft nichts mehr: die Stelle, an der Schluss
    // war, ist markiert, nicht "gerade dran". Sonst behauptete die Leiste einen
    // Lauf, den es nicht mehr gibt.
    const laeuft = i === pos && !beendet;
    const kachel = el("div", {
      class: "phasen-kachel" + (laeuft ? " laeuft" : (i < pos ? " fertig" : ""))
             + (beendet && i === pos ? " schluss" : ""),
      "data-art": p.art || "loop",
    }, el("div", {class: "p-name"}, p.name || "—"));

    if (laeuft) {
      kachel.appendChild(el("div", {class: "reihe"},
        el("span", {class: "klein mono wachse"},
           "Durchlauf " + (z.durchlauf || 1) + " / " + (z.wiederholungen || 1)),
        el("span", {class: "klein mono"},
           "Block " + (z.block || 0) + " / " + (z.bloecke || 0))));
      kachel.appendChild(balken(z.durchlauf || 0, z.wiederholungen || 1));
    } else if (beendet && i === pos) {
      // Die Phase, in der Schluss war. „ausstehend" waere hier falsch (sie lief
      // ja) und „abgeschlossen" auch (sie kam nicht durch) — ausser der Lauf
      // ist regulaer bis zum Ende gekommen.
      kachel.appendChild(el("div", {class: "p-lage"},
        (z.grund || "").startsWith("alle Zyklen") ? "abgeschlossen" : "hier war Schluss"));
    } else if (i < pos) {
      kachel.appendChild(el("div", {class: "p-lage"}, "abgeschlossen"));
    } else {
      // Eine zeitgesteuerte Phase wartet nicht auf ihren Vorgänger, sondern auf
      // die Uhr — das ist der Unterschied zwischen „gleich" und „um 07:00".
      kachel.appendChild(el("div", {class: "p-lage"},
        p.start ? "wartet auf " + p.start : "ausstehend"));
    }
    return kachel;
  }));
}

async function zeichneLauf() {
  const z = await frage("lauf_status");
  laufFlanke(!!(z && z.aktiv));   // auch hier mitfuehren, sonst kippt die Flanke
  if (ansicht !== "lauf") return;
  const ziel = $("sicht-lauf");
  ziel.replaceChildren();
  if (!z || !z.aktiv) {
    if (z && z.ende) return zeichneAbschluss(ziel, z);
    // Leerzustand ehrlich beschriften statt mit Nullen füllen: eine Tafel voller
    // Nullen sieht aus wie ein Lauf, der nichts tut.
    ziel.appendChild(el("div", {class: "lauf-kopf"},
      el("span", {class: "lampe"}),
      el("span", {class: "lauf-name"},
         z && z.verwaist ? "Nicht sauber beendet" : "Es läuft gerade keine Sequenz")));
    ziel.appendChild(el("p", {class: "hinweis"}, z && z.verwaist
      ? "Der letzte Lauf hat sich nicht sauber beendet — der Hauptprozess wurde " +
        "vermutlich hart abgeschossen. Ein neuer Start räumt das auf."
      : "Startet die zuletzt gespeicherte Fassung der geöffneten Sequenz — " +
        "danach zeigt diese Ansicht mit, wo sie gerade steht."));
    ziel.appendChild(steuerung(false));
    return;
  }

  const jetzt = Date.now() / 1000;
  ziel.appendChild(el("div", {class: "lauf-kopf"},
    el("span", {class: "lampe an"}),
    el("span", {class: "lauf-name"}, z.sequenz || "(ohne Namen)"),
    el("span", {class: "zahl"},
       "Zyklus " + (z.zyklus || 0) + " / " + (z.zyklen ? z.zyklen : "∞")),
    el("span", {class: "zahl"}, "läuft " + dauer(jetzt - (z.start || jetzt)))));

  ziel.appendChild(phasenLeiste(z));

  // Kopfzeile in der Typfarbe des laufenden Blocks — dieselbe Gestalt wie seine
  // Karte im Board, damit man ihn wiedererkennt statt ihn zu lesen. Ohne Typ
  // (alte Statusdatei) bleibt sie neutral statt eine Farbe zu erfinden.
  const zaehler = z.zaehler || {};
  ziel.appendChild(el("div", {class: "lauf-mitte"},
    el("div", {class: "tafel mit-kopf"},
      el("div", {class: "karte-kopf",
                 style: "background:" + (z.block_farbe || "#2A3245") +
                        (z.block_farbe ? "" : ";color:var(--text)")},
        el("span", {class: "karte-typ"}, z.block_marke || "AKTUELLER BLOCK"),
        el("span", {class: "karte-titel"}, z.block_titel || "(ohne Namen)"),
        el("span", {class: "karte-nr"},
           "Block " + (z.block || 0) + " / " + (z.bloecke || 0))),
      el("div", {class: "tafel-leib"},
        el("div", {class: "karte-zeile"}, z.block_label || ""),
        balken(z.block || 0, z.bloecke || 1),
        el("span", {class: "klein mono"},
           "seit " + dauer(jetzt - (z.block_seit || jetzt))),
        warteKasten(z.warten, jetzt))),
    el("div", {class: "kachel"},
      [["Klicks", "klicks"], ["Items", "items"], ["Tasten", "tasten"],
       ["Timeouts", "timeouts"], ["Übersprungen", "uebersprungen"],
       ["Neustarts", "neustarts"]].map(([text, schluessel]) =>
        el("div", {}, el("b", {}, String(zaehler[schluessel] || 0)),
                      el("small", {}, text.toUpperCase()))))));

  ziel.appendChild(steuerung(true));
}

/** Der letzte Lauf, nachdem er fertig ist.
 *
 * Vorher verschwand hier alles in dem Moment, in dem die Sequenz durch war:
 * die Datei wurde geloescht, die Ansicht zeigte „Es läuft gerade keine
 * Sequenz". Ausgerechnet dann sieht man aber hin — die Frage ist ja, was
 * herausgekommen ist. Jetzt bleibt der Stand stehen, bis der nächste Start ihn
 * überschreibt.
 *
 * Dieselben Kacheln wie im Lauf, damit man nicht umlernen muss; die Zeitangaben
 * sind fest statt mitlaufend, denn hier tickt nichts mehr.
 */
function zeichneAbschluss(ziel, z) {
  const zaehler = z.zaehler || {};
  // Warum es zu Ende ist, entscheidet die Farbe: durchgelaufen ist gruen,
  // von Hand gestoppt neutral, Notbremse rot. Eine Zusammenfassung, die bei
  // jedem Ausgang gleich aussieht, muss man lesen statt anzusehen.
  const grund = z.grund || "";
  const art = grund.startsWith("Notbremse") ? "err"
            : grund.startsWith("alle Zyklen") ? "ok" : "warn";
  ziel.appendChild(el("div", {class: "lauf-kopf"},
    el("span", {class: "lampe fertig"}),
    el("span", {class: "lauf-name"}, z.sequenz || "(ohne Namen)"),
    el("span", {class: "zahl abschluss-" + art}, "beendet"),
    el("span", {class: "zahl"}, zeitpunkt(z.ende)),
    el("span", {class: "zahl"}, "lief " + dauer(z.dauer || 0))));

  ziel.appendChild(el("p", {class: "hinweis abschluss-" + art},
    grund + " · " + (z.gelaufen || 0) + " von " +
    (z.zyklen ? z.zyklen : "∞") + " Zyklen"));

  if (z.phasen && z.phasen.length) ziel.appendChild(phasenLeiste(z, true));

  ziel.appendChild(el("div", {class: "kachel"},
    [["Klicks", "klicks"], ["Items", "items"], ["Tasten", "tasten"],
     ["Timeouts", "timeouts"], ["Übersprungen", "uebersprungen"],
     ["Neustarts", "neustarts"]].map(([text, schluessel]) =>
      el("div", {}, el("b", {}, String(zaehler[schluessel] || 0)),
                    el("small", {}, text.toUpperCase())))));

  ziel.appendChild(steuerung(false));
}

/** Start/Pause/Stopp.
 *
 * Die Knöpfe führen nichts aus — dieses Fenster hat keinen Zugriff auf
 * `state.stop_event`. Sie legen einen Befehl ab, den der Hauptprozess in
 * derselben Schleife abholt wie seine Hotkeys (`befehl.py`). Deshalb steht das
 * Hotkey-Kürzel weiterhin daneben: es ist derselbe Weg, nur ohne Fensterwechsel.
 */
function steuerung(laeuft) {
  const knopf = (text, befehl, klasse) => el("button", {
    class: "btn" + (klasse ? " " + klasse : ""),
    onclick: () => laufSchicken(befehl),
  }, text);
  return el("div", {class: "reihe", style: "gap:8px;flex-wrap:wrap"},
    laeuft ? null : knopf("▶ Starten", "start", "haupt"),
    laeuft ? knopf("⏸ Pause", "pause") : null,
    laeuft ? knopf("■ Stoppen", "stop", "gefahr") : null,
    el("span", {class: "klein"},
       laeuft ? "oder CTRL+ALT+S / CTRL+ALT+G im Hauptprozess"
              : "startet die gespeicherte Fassung — ungespeicherte Änderungen " +
                "werden vorher geschrieben"));
}

/* ----------------------------------------------------------------- Inspektor */

function punktListe(aktuell, mitLeer) {
  const werte = S.punkte.map((p) => ({wert: p.id, text: "#" + p.id + " " + p.name +
                                                        " (" + p.x + "," + p.y + ")"}));
  if (mitLeer || aktuell === null || aktuell === undefined) {
    werte.unshift({wert: "", text: "(kein Punkt)"});
  }
  return werte;
}

function zeichneInspektor() {
  const ziel = $("inspektor");
  ziel.replaceChildren();
  const b = S.block;
  const gewaehlt = S.auswahl.zeilen.length;

  $("btn-block-weg").disabled = gewaehlt === 0;
  $("btn-block-kopie").disabled = gewaehlt === 0;
  if (!b) {
    $("insp-punkt").style.background = "#2A3245";
    $("insp-titel").textContent = gewaehlt > 1 ? gewaehlt + " BLÖCKE GEWÄHLT" : "KEIN BLOCK";
    ziel.appendChild(el("div", {class: "leer"}, gewaehlt > 1
      ? el("span", {}, "Mehrfachauswahl: verschieben mit ALT+↑/↓, duplizieren mit " +
                       "STRG+D, löschen mit Entf.",
           el("br"), "Für die Einstellungen einen einzelnen Block wählen.")
      : el("span", {}, "Block anklicken, um ihn zu bearbeiten.", el("br"),
           "Ziehen sortiert um — auch über Phasengrenzen.")));
    return;
  }

  const phase = S.phasen[b.phase];
  $("insp-punkt").style.background = b.farbe;
  $("insp-titel").textContent = "BLOCK " + String(b.zeile + 1).padStart(2, "0") +
                                " · " + phase.name.toUpperCase();

  // --- Typ ---
  // Jede Kachel traegt ihre Farbe, nicht nur die gewaehlte: damit ist das Raster
  // zugleich die Legende zu den Farben im Board — vorher musste man sie sich aus
  // den Karten zusammensuchen —, und man sieht vor dem Klick, wie die Karte
  // danach aussieht.
  //
  // Die Farbe liegt ringsum statt als Streifen links (dieselbe Regel wie bei
  // Phasenkopf, Karte und laufender Phase), die GEWAEHLTE ist zusaetzlich
  // ausgefuellt. `border-color` steht im style-Attribut und damit nach dem
  // `border`-Kurzformat aus .typ-chip — andersherum raeumte die Kurzform die
  // Farbe wieder weg.
  ziel.appendChild(ueberschrift("BLOCK-TYP",
    "Die Farbe der Kachel wiederholt sich auf der Karte im Board — das Raster " +
    "ist zugleich die Legende dazu.", "blocktyp"));
  ziel.appendChild(el("div", {class: "gitter3"}, S.typen.map((t) =>
    el("button", {
      class: "typ-chip",
      style: "border-color:" + t.farbe +
             (t.key === b.typ
               ? ";background:" + t.farbe + ";color:#0C0F14;font-weight:600"
               : ""),
      onclick: () => ruf("block_typ", {typ: t.key}),
    }, t.label))));

  // Die drei Klick-/Warte-Typen unterscheiden sich in genau zwei Eigenschaften.
  // Als Schalter steht diese Tabelle auf dem Schirm, statt im Kopf zu sein.
  if (b.typ === "click" || b.typ === "wait_click" || b.typ === "wait") baueAktion(ziel, b);

  // --- Gemeinsames ---
  if (b.typ !== "screenshot") {
    // Der Name steht nur hier, wenn er dem SCHRITT gehört. Hat der Block einen
    // Punkt, gehört der Name dem Punkt — und dann steht er unten bei der Stelle,
    // zusammen mit Auswahl, Farbe und Koordinaten. Vorher stand oben „Name
    // (Punkt #1)" und weiter unten nochmal „Punkt": zweimal dieselbe Sache an
    // zwei Stellen, und man musste raten, welche die führende ist.
    if (b.point_id === null || b.point_id === undefined) {
      ziel.appendChild(feld("Name", b.name, (v) => ruf("block_setzen", {feld: "name", wert: v})));
    }
    ziel.appendChild(el("div", {class: "gitter2"},
      zahlfeld("Wartezeit (s)", b.delay_before,
               (v) => ruf("block_setzen", {feld: "delay_before", wert: v}),
               {step: "0.1", min: "0"}),
      zahlfeld("bis (0 = fest)", b.delay_max,
               (v) => ruf("block_setzen", {feld: "delay_max", wert: v}),
               {step: "0.1", min: "0"})));
  }

  // Ein Warte-Block ohne Trigger beobachtet nichts — dann gibt es auch keine
  // Stelle zu zeigen.
  if (b.typ === "click" || b.typ === "wait_click" ||
      (b.typ === "wait" && b.trigger !== "kein")) baueStelle(ziel, b);
  if (b.typ === "key") {
    ziel.appendChild(feld("Taste", b.key_press,
      (v) => ruf("block_setzen", {feld: "key_press", wert: v}), {placeholder: "enter, space, f1"}));
  }
  baueScan(ziel, b);
  if (b.typ === "screenshot") baueScreenshot(ziel, b);

  // Der Farb-Trigger fragt VOR dem Schritt. Sinn ergibt er nur, wo die Laufzeit
  // ihn auch auswertet: bei Klick, Warten und Taste — `runtime/steps.py` wartet
  // fuer diese drei an genau einer Stelle, und dass die Taste dazugehoert, war
  // einmal ein Fehler und ist ausdruecklich repariert. Scans und Screenshot
  // kehren vorher um; dort waere die Bedingung wirkungslos.
  //
  // Gezeigt wird der Abschnitt trotzdem, wenn schon eine Bedingung dranhaengt:
  // sonst waere sie unerreichbar, und ein Zustand, den man sieht (Farbfeld auf
  // der Karte) aber nicht mehr wegbekommt, ist genau die Falltuer, die der
  // geloeschte "nur warten"-Schalter war.
  const mitTrigger = b.typ === "click" || b.typ === "wait_click" ||
                     b.typ === "wait" || b.typ === "key";
  if (mitTrigger || b.trigger !== "kein") baueTrigger(ziel, b, mitTrigger);
  baueNachpruefung(ziel, b);
  baueElse(ziel, b);
  baueProbe(ziel, b);

  // Zuletzt, wenn alles im Dokument haengt: was aufgeklappt war, bleibt es. Der
  // Inspektor wird bei jeder Aenderung komplett neu gebaut — ohne diese Zeile
  // verschwindet eine gerade gelesene Erklaerung beim naechsten Klick irgendwo.
  hilfenAnwenden(ziel);
}

/** „Sitzt der Punkt da, wo ich denke?" — die Maus fährt hin und sagt es.
 *
 * Nur bei Blöcken mit Stelle. Das Fenster bewegt die Maus nicht selbst (es sieht
 * den Bildschirm nicht); der Hauptprozess tut es und misst dabei, ob die Farbe
 * dort noch der gespeicherten entspricht. Diese Zeile steht in seiner Konsole —
 * hier kann sie nicht stehen, und das zu behaupten wäre schlimmer als der Weg
 * zum anderen Fenster.
 */
function baueProbe(ziel, b) {
  // Ein Block hat bis zu drei Stellen — Klick, Prüf-Pixel des Triggers und
  // ELSE-Klick —, und „sitzt das noch?" fragt man bei jeder. Angeboten wird
  // nur, was der Block wirklich hat.
  const stellen = [];
  if (b.point_id !== null && b.point_id !== undefined)
    stellen.push(["klick", "Stelle", b.point_id]);
  if (b.trigger !== "kein" && b.trigger_punkt !== null && b.trigger_punkt !== undefined)
    stellen.push(["trigger", "Prüf-Pixel", b.trigger_punkt]);
  if (b.verify !== "kein" && b.verify_punkt !== null && b.verify_punkt !== undefined)
    stellen.push(["verify", "Nachprüf-Pixel", b.verify_punkt]);
  if (b.else_aktion === "click" && b.else_punkt !== null && b.else_punkt !== undefined)
    stellen.push(["else", "ELSE-Klick", b.else_punkt]);
  if (!stellen.length) return;

  const fuss = el("div", {class: "insp-fuss"});
  for (const [welche, text, punkt] of stellen) {
    fuss.appendChild(el("button", {
      class: "btn breit",
      onclick: () => ruf("punkt_zeigen", {welche: welche}),
    }, "◎ " + text + " zeigen (#" + punkt + ")"));
  }
  fuss.appendChild(el("p", {class: "hinweis"},
    "Setzt die Maus im Hauptprozess auf die Stelle. Dort steht dann auch, ob " +
    "die gemessene Farbe noch zur gespeicherten passt."));
  ziel.appendChild(fuss);
}

function baueAktion(ziel, b) {
  const klickt = b.typ === "click" || b.typ === "wait_click";
  const farbe = b.trigger !== "kein";
  const ergibt = klickt ? (farbe ? "wait_click" : "click") : "wait";
  const typ = S.typen.find((t) => t.key === ergibt);

  // Der Schluessel bleibt "aktion" und haengt bewusst NICHT am Block-Typ: der
  // wechselt hier ja gerade, und eine Erklaerung, die man aufklappt und die beim
  // ersten Schalten verschwindet, ist keine.
  ziel.appendChild(ueberschrift("AKTION",
    "Diese beiden Schalter SIND der Block-Typ: klicken und/oder auf eine Farbe " +
    "warten. Die Kacheln oben setzen dieselben zwei Werte — was dabei " +
    "herauskommt, steht darunter.", "aktion"));
  ziel.appendChild(schalter("klickt an der Stelle", klickt, (an) =>
    ruf("block_typ", {typ: an ? (farbe ? "wait_click" : "click") : "wait"})));
  ziel.appendChild(schalter("wartet auf eine Farbe", farbe, (an) => {
    // Bei einem Warte-Block aendert die Farbe den Typ nicht — WARTEN heisst mit
    // und ohne Trigger WARTEN. Bei den Klick-Typen ist sie der Unterschied
    // zwischen KLICK und FARBE+KLICK, laeuft dort also ueber den Typ.
    if (!klickt) ruf("block_trigger", {wahl: an ? "da" : "kein"});
    else ruf("block_typ", {typ: an ? "wait_click" : "click"});
  }));
  ziel.appendChild(el("div", {class: "reihe", style: "padding-top:2px"},
    el("span", {class: "klein"}, "ergibt"),
    el("span", {class: "karte-typ", style: "background:" + typ.farbe}, typ.label)));
}

function baueStelle(ziel, b) {
  // Beides an der Ueberschrift: der Zusatz fuer WARTEN-Bloecke erklaert, warum
  // hier ueberhaupt eine Stelle steht, obwohl nicht geklickt wird.
  ziel.appendChild(ueberschrift(b.typ === "wait" ? "BEOBACHTETE STELLE" : "KLICK-POSITION",
    "X und Y verschieben den Punkt selbst. Jeder Block, der ihn benutzt, zeigt " +
    "danach auf die neue Stelle — die Sequenz speichert keine eigenen Koordinaten." +
    (b.typ === "wait" ? " Dieser Block klickt übrigens nicht: die Stelle wird nur " +
     "beobachtet. Zum Klicken oben den Typ KLICK oder FARBE+KLICK wählen." : ""),
    "stelle"));
  if (!S.punkte.length && b.point_id === null) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Keine Punkte vorhanden. Im Hauptprozess mit CTRL+ALT+A aufnehmen — " +
      "oder hier eine Stelle eintragen, dann entsteht ein Punkt dafür."));
  } else {
    ziel.appendChild(auswahl("Punkt", punktListe(b.point_id), b.point_id === null ? "" : b.point_id,
      (v) => v && ruf("block_punkt", {punkt: Number(v)})));
  }
  // Alles, was dem Punkt gehört, steht beieinander: welcher, wie er heisst,
  // welche Farbe er trägt, wo er liegt.
  if (b.point_id !== null && b.point_id !== undefined) {
    const p = S.punkte.find((q) => q.id === b.point_id);
    ziel.appendChild(feld("Name des Punkts", b.name,
      (v) => ruf("punkt_setzen", {punkt: b.point_id, feld: "name", wert: v}), null,
      "Der Name gehört dem Punkt, nicht diesem Block: er ändert sich überall, " +
      "wo derselbe Punkt benutzt wird.", "punktname"));
    ziel.appendChild(farbfeld("Farbe des Punkts", p && p.farbe,
      (hex) => ruf("punkt_setzen", {punkt: b.point_id, feld: "farbe", wert: hex}),
      "Beim Aufnehmen gemessen. Ein Farb-Trigger prüft GENAU diese Farbe — wer " +
      "sie hier ändert, ändert mit, worauf gewartet wird.", "punktfarbe"));
  }
  ziel.appendChild(el("div", {class: "gitter2"},
    zahlfeld("X", b.x, (v) => setzeStelle(b, v, b.y), {step: "1"}),
    zahlfeld("Y", b.y, (v) => setzeStelle(b, b.x, v), {step: "1"})));
  // Die Stelle anfahren statt sie zu tippen — derselbe Weg wie beim
  // Screenshot-Bereich. Die Zahlenfelder bleiben daneben stehen, für den Fall,
  // dass man eine Koordinate abschreibt.
  ziel.appendChild(el("button", {
    class: "btn breit",
    title: "Maus an die Stelle bewegen und ENTER drücken (ESC bricht ab)",
    onclick: () => ruf("punkt_aufnehmen"),
  }, "✛ Stelle mit der Maus setzen"));
  ziel.appendChild(el("p", {class: "hinweis"},
    "Danach: Maus im Spiel an die Stelle, ENTER. Die Farbe wird dabei " +
    "gleich mitgemessen — ESC bricht ab."));
  // Hier stand ein Schalter "nur warten (kein Klick)". Er setzte `wait_only` —
  // also genau das, was der Typ-Chip WARTEN oben schon setzt: ein Zustand, zwei
  // Bedienelemente. Das rächte sich, weil er sich bei "warten" selbst ausblendete
  // und damit eine Falltuer war. Die Chips koennen alles, was er konnte:
  // WARTEN hin, FARBE+KLICK verlustfrei zurueck (der Trigger bleibt), KLICK
  // zurueck ohne Trigger — und das ist keine Nebenwirkung, sondern die Bedeutung
  // von KLICK. Was seine Beschriftung erklaerte, steht am ⓘ der Ueberschrift.
  if (b.scroll) {
    ziel.appendChild(zahlfeld("Mausrad (Stufen, 0 = kein Rad)", b.scroll,
      (v) => ruf("block_setzen", {feld: "scroll", wert: v}), {step: "1"}));
  }
}

function setzeStelle(b, x, y) {
  if (b.point_id === null || b.point_id === undefined) {
    ruf("punkt_anlegen", {x: x, y: y});
  } else {
    // Zwei Felder, ein Punkt: nur die geänderte Achse schicken.
    if (x !== b.x) ruf("punkt_setzen", {punkt: b.point_id, feld: "x", wert: x});
    if (y !== b.y) ruf("punkt_setzen", {punkt: b.point_id, feld: "y", wert: y});
  }
}

function baueScan(ziel, b) {
  const scans = {item_scan: ["ITEM-SCAN", "item_scan"], icon_scan: ["ICON-SCAN", "icon_scan"],
                 boss_scan: ["BOSS-SCAN", "boss_scan"], boss_watcher: ["BOSS-WATCHER", "boss_watcher"]};
  const eintrag = scans[b.typ];
  if (!eintrag) return;
  const [titel, feldname] = eintrag;
  const vorhanden = (S.scan_namen && S.scan_namen[b.typ]) || [];
  const wert = b[feldname];
  ziel.appendChild(ueberschrift(titel));

  if (!vorhanden.length && !wert) {
    // Nichts zum Auswählen — dann ist ein leeres Feld die falsche Antwort. Es
    // gäbe nur einen Namen her, der auf keine Datei zeigt, und der Block liefe
    // still ins Leere. Also sagen, wo die Konfiguration herkommt.
    // CTRL+ALT+N fuer alle drei: Boss- und Icon-Scans sind Untermenues des
    // Item-Scan-Menues, eigene Hotkeys haben sie nicht.
    ziel.appendChild(el("p", {class: "hinweis"},
      "Keine Konfiguration vorhanden. Im Hauptprozess mit CTRL+ALT+N anlegen " +
      "(Boss- und Icon-Scans liegen in demselben Menü), dann steht sie hier " +
      "zur Auswahl."));
    return;
  }

  // Der gespeicherte Name bleibt wählbar, auch wenn seine Datei fehlt: sonst
  // würde ein Öffnen mit gelöschter Konfiguration den Namen stillschweigend auf
  // den ersten Eintrag der Liste ändern.
  const werte = [{wert: "", text: "(keine)"}].concat(vorhanden.map(
    (n) => ({wert: n, text: n})));
  if (wert && !vorhanden.includes(wert)) werte.push({wert: wert, text: wert + " — fehlt"});
  ziel.appendChild(auswahl("Konfiguration", werte, wert,
    (v) => ruf("block_setzen", {feld: feldname, wert: v}),
    "Im Item-/Boss-/Icon-Editor angelegt (Hauptprozess, CTRL+ALT+N). " +
    "Ohne Konfiguration wird nicht gespeichert.", "scan"));
  if (b.typ === "item_scan") {
    ziel.appendChild(auswahl("Modus", S.scan_modi.map((m) => ({wert: m, text: m})),
      b.item_scan_mode, (v) => ruf("block_setzen", {feld: "item_scan_mode", wert: v})));
  }
}

function baueScreenshot(ziel, b) {
  ziel.appendChild(ueberschrift("SCREENSHOT"));
  const hatBereich = !!b.screenshot_region;
  ziel.appendChild(schalter("Bereich statt Vollbild", hatBereich,
    (an) => ruf("block_bereich", {werte: an ? (b.screenshot_region || [0, 0, 100, 100]) : null})));
  if (!hatBereich) return;
  const r = b.screenshot_region.slice();
  const setze = (i) => (v) => { r[i] = v; ruf("block_bereich", {werte: r}); };

  // Der eigentliche Weg: die Ecke anfahren statt sie auszurechnen. Vier Zahlen
  // sagen niemandem, wo der Bereich liegt — sie bleiben trotzdem stehen, fuer
  // den Fall, dass man eine Koordinate abschreibt.
  ziel.appendChild(el("button", {class: "btn", onclick: (e) => {
    // blur() ist Pflicht, nicht Kosmetik: ein Knopf behaelt nach dem Klick den
    // Fokus, und das ENTER, mit dem die Ecke bestaetigt wird, wuerde ihn gleich
    // nochmal ausloesen — also mitten in der Aufnahme eine zweite starten.
    e.currentTarget.blur();
    // Sofortige Rueckmeldung, bevor die Bruecke blockiert: von dort kommt bis
    // zum zweiten Tastendruck nichts, und ein Fenster, das schweigt, sieht aus
    // wie eines, das den Klick verschluckt hat.
    setzeStatus({text: "Ecke 1 anfahren + ENTER, dann Ecke 2 + ENTER (ESC bricht ab)",
                 art: "warn"});
    ruf("bereich_aufnehmen");
  }}, "Bereich mit der Maus aufnehmen ⌖"));

  ziel.appendChild(el("div", {class: "gitter2"},
    zahlfeld("X1", r[0], setze(0)), zahlfeld("Y1", r[1], setze(1)),
    zahlfeld("X2", r[2], setze(2)), zahlfeld("Y2", r[3], setze(3))));
  ziel.appendChild(el("p", {class: "hinweis"},
    "Grösse: " + Math.abs(r[2] - r[0]) + " × " + Math.abs(r[3] - r[1]) + " Pixel"));
}

// Richtungen einer Farb-Bedingung. Das Aus steht nur dort mit im Segment, wo es
// kein eigenes Bedienelement dafuer gibt — bei den Klick-/Warte-Typen macht das
// der Schalter im Abschnitt AKTION, und zwei Wege zum selben Aus waeren einer zu viel.
const RICHTUNG_AUS = {wert: "kein", text: "kein"};
const RICHTUNGEN = [{wert: "da", text: "bis Farbe DA"}, {wert: "weg", text: "bis Farbe WEG"}];

function baueTrigger(ziel, b, mitTrigger) {
  // Bei TASTE gibt es keine Aktions-Schalter, dort bleibt das Aus im Segment.
  const ohneAus = b.typ === "click" || b.typ === "wait_click" || b.typ === "wait";
  // Ist der Trigger bei diesen Typen aus, hat der Abschnitt keinen Inhalt: das Ein
  // und Aus macht der Schalter in AKTION, Stelle und „nur prüfen" hängen an einer
  // Bedingung, die es nicht gibt. Eine Überschrift ohne alles darunter sieht aus
  // wie ein Stück Oberfläche, das nicht geladen hat — also gar nichts zeigen.
  // Ausnahme: fehlt dem Block der Punkt, bleibt der Hinweis unten stehen. Der
  // erklärt, warum sich der Trigger nicht einschalten lässt.
  if (ohneAus && b.trigger === "kein"
      && b.point_id !== null && b.point_id !== undefined) return;
  ziel.appendChild(ueberschrift("FARB-TRIGGER (VOR DEM SCHRITT)",
    mitTrigger
      ? "Wartet vor dem Schritt darauf, dass die Farbe des Punkts da ist (oder weg)."
      : "Dieser Block-Typ wertet keinen Farb-Trigger aus — die Laufzeit kehrt " +
        "vorher um. Die Bedingung steht nur hier, damit sie sich abschalten lässt.",
    "trigger-an"));
  if (!(ohneAus && b.trigger === "kein")) {
    ziel.appendChild(segment(ohneAus ? RICHTUNGEN : [RICHTUNG_AUS].concat(RICHTUNGEN),
      b.trigger, (w) => ruf("block_trigger", {wahl: w})));
  }
  if (b.trigger !== "kein") {
    ziel.appendChild(auswahl("Geprüfte Stelle", punktListe(b.trigger_punkt), b.trigger_punkt,
      (v) => v && ruf("block_trigger", {wahl: b.trigger, punkt: Number(v)}),
      "Farbe und Stelle kommen aus dem Punkt. Soll an derselben Stelle auf eine " +
      "andere Farbe geprüft werden, ist das ein eigener Punkt.", "trigger"));
    ziel.appendChild(schalter("nur prüfen, nicht warten", b.trigger_pruefen,
      (an) => ruf("block_trigger", {wahl: b.trigger, pruefen: an})));
  } else if (b.point_id === null || b.point_id === undefined) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Ohne Punkt gibt es nichts zu prüfen — erst eine Stelle wählen."));
  }
}

function baueNachpruefung(ziel, b) {
  // Bleibt bei JEDEM Typ: „hat die Aktion gewirkt?" ergibt auch bei einer Taste
  // und bei einem Scan Sinn — anders als der Trigger davor.
  const richtungen = [RICHTUNG_AUS].concat(RICHTUNGEN);
  ziel.appendChild(ueberschrift("NACHPRÜFUNG (NACH DEM SCHRITT)",
    "„Hat die Aktion gewirkt?“ Bleibt die Wirkung aus, wird die Aktion " +
    "wiederholt (verify_retries), danach greift ELSE.", "verify"));
  ziel.appendChild(segment(richtungen, b.verify,
    (w) => ruf("block_trigger", {welche: "verify", wahl: w})));
  if (b.verify !== "kein") {
    ziel.appendChild(auswahl("Geprüfte Stelle", punktListe(b.verify_punkt), b.verify_punkt,
      (v) => v && ruf("block_trigger", {welche: "verify", wahl: b.verify, punkt: Number(v)})));
  }
}

/** Was ohne ELSE passiert — aus der Config des Hauptprozesses, nicht geraten.
 *
 * Hier stand „die Sequenz macht weiter", und das war schlicht falsch: die
 * Voreinstellung `pixel_timeout_action: "skip_cycle"` bricht den ganzen Zyklus
 * ab. Der Unterschied entscheidet, ob man ELSE ueberhaupt braucht — also gehoert
 * die echte Einstellung hierher und nicht ein allgemeiner Satz.
 */
function ohneElseText() {
  const o = S.ohne_else || {};
  if (!o.folge) return "Ohne ELSE entscheidet nach dem Timeout die Einstellung " +
                       "pixel_timeout_action in der config.json.";
  const zeit = o.sekunden > 0 ? o.sekunden + " s" : "ohne Timeout";
  return "Ohne ELSE wartet der Schritt bis zum Timeout (" + zeit + "), danach: " +
         o.folge + " (config.json: pixel_timeout_action)." +
         (o.notbremse > 0 ? " Nach " + o.notbremse + " Timeouts in Folge greift " +
                            "die Notbremse." : "");
}

function baueElse(ziel, b) {
  // Kein Auslöser, kein Abschnitt: an einem reinen Klick (Taste, Warten,
  // Screenshot, Boss-Watcher) kann ELSE nie feuern, und ein Bedienelement steht
  // nur da, wo die Laufzeit es auswertet — dieselbe Regel wie beim Farb-Trigger,
  // den es bei Scans und Screenshot auch nicht gibt.
  //
  // Ausnahme: ist trotzdem eine Aktion gesetzt (Trigger nachträglich entfernt,
  // Typ umgestellt, Import), bleibt der Abschnitt stehen. Sonst stünde das ELSE
  // unsichtbar in der Datei und wäre nicht mehr loszuwerden — dieselbe Falltür
  // wie beim gelöschten Schalter „nur warten".
  if (!b.else_greift && !b.else_aktion) return;
  // Kein ELSE heisst: keine Kachel markiert. Eine Kachel „(keine)" stand vorher
  // im Raster und sah aus wie eine sechste Aktion, obwohl sie das Gegenteil ist
  // — die Abwesenheit von allen.
  //
  // Der Rückweg ist die markierte Kachel selbst: ein zweiter Klick darauf hebt
  // sie auf. Fehlen darf er nicht (sonst dieselbe Falltür wie beim gelöschten
  // Schalter „nur warten": gesetzt und nicht mehr loszuwerden), und weil man ein
  // Umschalten nicht sieht, steht es im Hinweis darunter und im Tooltip der
  // Kachel.
  ziel.appendChild(ueberschrift("ELSE — WENN DIE BEDINGUNG NICHT GREIFT",
    "ELSE ist ein „stattdessen“, kein „zusätzlich“: greift es, entfällt die " +
    "eigene Aktion des Schritts. Ein zweiter Klick auf die markierte Kachel " +
    "hebt sie wieder auf.", "else"));
  // Kacheln statt Klappmenü: die Auswahl ist fest und kurz (fünf Aktionen), und
  // im Inspektor ist der Platz da. Ein Klappmenü versteckt vier von fünf
  // Möglichkeiten hinter einem Klick — hier sieht man auf einen Blick, was es
  // überhaupt gibt. Dieselbe Form wie das Typ-Raster darüber, damit beide als
  // dasselbe Bedienelement zu erkennen sind.
  // Der Block kann gar nichts ausloesen: das gehoert VOR die Kacheln, sonst
  // stellt man erst eine Aktion ein und liest danach, dass sie nie drankommt.
  if (!b.else_greift) {
    ziel.appendChild(el("p", {class: "hinweis warnung"},
      "Dieser Block hat keine Bedingung — ELSE kommt hier nie zum Zug. " +
      "Ausgelöst wird es von einem Farb-Trigger (Timeout oder „nur prüfen“), " +
      "einer Nachprüfung ohne Wirkung oder einem Scan, der nichts findet."));
  }
  ziel.appendChild(el("div", {class: "gitter3"}, S.else_aktionen.map((a) =>
    el("button", {
      // Eigene Klasse trotz gleicher Form: eine Typ-Kachel schaltet den Block-Typ,
      // eine ELSE-Kachel die Ersatzaktion. Wer eine davon später anders gestalten
      // will, soll nicht beide erwischen.
      class: "typ-chip else-chip" + (a === b.else_aktion ? " an" : ""),
      title: a === b.else_aktion ? "nochmal klicken = kein ELSE" : "",
      // Dieselbe Kachel nochmal: das leere Kommando entfernt die Aktion. Eine
      // andere Kachel wechselt sie wie gewohnt.
      onclick: () => ruf("block_else", {aktion: a === b.else_aktion ? "" : a}),
    }, a))));
  // Der Satz zur gewählten Aktion — und dahinter, wie man sie wieder los wird.
  // Ein Umschalten sieht man einem Bedienelement nicht an; ungesagt fände es nur,
  // wer es zufällig probiert.
  ziel.appendChild(el("p", {class: "hinweis"}, ({
    "": ohneElseText(),
    skip: "Nur diesen Schritt überspringen.",
    skip_cycle: "Den laufenden Zyklus abbrechen und den nächsten beginnen.",
    restart: "Die Sequenz von vorn beginnen.",
    click: "Stattdessen einen anderen Punkt klicken.",
    key: "Stattdessen eine Taste drücken."}[b.else_aktion] || "") +
    (b.else_aktion ? " Nochmal auf die markierte Kachel klicken = kein ELSE." : "")));
  if (b.else_aktion === "click") {
    ziel.appendChild(auswahl("ELSE-Punkt", punktListe(b.else_punkt), b.else_punkt,
      (v) => v && ruf("block_else", {aktion: "click", punkt: Number(v)})));
  }
  if (b.else_aktion === "key") {
    ziel.appendChild(feld("ELSE-Taste", b.else_taste,
      (v) => ruf("block_else", {aktion: "key", taste: v})));
  }
}

/* -------------------------------------------------------------------- Dialog */

function zeigeFrage(frage) {
  // Titel, Text und Knopfbeschriftungen kommen aus der Brücke: die Fälle
  // unterscheiden sich zu sehr, um sie hier zusammenzusetzen (bei „ausserhalb
  // geändert" gibt es nichts zu verwerfen und nichts vorher zu speichern).
  offeneFrage = frage;
  $("dialog-titel").textContent = frage.titel || "Rückfrage";
  $("dialog-text").textContent = frage.text || "";
  $("dialog-weg").textContent = frage.weiter || "Weiter";
  $("dialog-speichern").hidden = !frage.speichern;
  $("schleier").hidden = false;
}

function schliesseFrage() {
  offeneFrage = null;
  $("schleier").hidden = true;
}

async function fortfahren(verwerfen) {
  const frage = offeneFrage;
  schliesseFrage();
  if (!frage) return;
  if (frage.art === "speichern") return ruf("speichern", {erzwingen: true});
  if (!verwerfen) await ruf("speichern");
  if (frage.art === "laden") await ruf("laden", {name: frage.ziel, verwerfen: true});
  else await ruf("neu", {verwerfen: true});
}

/* ------------------------------------------------------------ Ansicht: Scans */

/* Slots, Items und Item-Scans auf einem eingefrorenen Screenshot. Eigener
 * Zustand neben `S`, wie bei den Einstellungen: der Reiter bearbeitet andere
 * Dateien (slots.json, items.json, item_scans/), und eine Sequenz-Momentaufnahme
 * waere dafuer der falsche Gegenstand.
 *
 * Gezeichnet wird ein <img> mit einem <svg> darueber. Das SVG traegt ein
 * viewBox in BILD-Pixeln — damit ist jede Rechnung im Overlay unabhaengig vom
 * Zoom, und nur die Strichstaerken und Schriftgroessen muessen gegengerechnet
 * werden. */
let SC = null;
/* Welche Liste links offen ist — `null` heisst „noch nicht entschieden", dann
 * gilt `scanListeAktiv()`.
 *
 * **Mit offenem Scan sind die Items die Arbeit.** Vorher stand die Liste immer
 * auf „Scans": wer einen Scan lud, sah dessen Namen noch einmal und musste
 * erst unten links auf „Items" klicken, um an das zu kommen, weswegen er den
 * Scan geoeffnet hat. Der Scan ist die Klammer, nicht der Inhalt.
 *
 * Dieselbe Regel wie bei `klappZu`: die Vorgabe gilt, bis jemand einen Reiter
 * anfasst — ab dann steht dort seine Entscheidung. Ein Bedienelement, das
 * zurueckspringt, ist keine Hilfe. */
let scanListe = null;
let scanZoom = 1;
// Hat der Nutzer den Zoom selbst gesetzt (1:1 oder STRG+Rad)? Dann fasst ihn
// die Fenstergroesse nicht mehr an — sonst raeumte ein Verschieben des Fensters
// die gerade eingestellte Vergroesserung weg.
let scanZoomHand = false;
let scanFotoStand = 0;
let scanVorschauen = new Map();   // Item-Name -> data:-URL des Templates
let scanZeiger = null;            // letzte Mausposition im Bild (fuer die Vorschau)
let scanKategorie = "";           // Kategorie-Filter der Item-Liste
let scanGefuehrt = true;
let scanAutoSaveTimer = 0;
let scanAssistentSchritt = null;

/* Welche Abschnitte der linken Spalte zugeklappt sind. `null` heisst „noch
 * nichts entschieden" — dann gilt die abgeleitete Vorgabe aus `klappVorgabe()`.
 * Sobald jemand einen Kopf anfasst, steht dort true/false und die Vorgabe
 * schweigt: eine Automatik, die eine ausdrueckliche Entscheidung ueberstimmt,
 * ist keine Hilfe mehr, sondern ein Bedienelement, das zurueckspringt.
 *
 * Reiner Oberflaechenzustand, deshalb hier und nicht in der Bruecke: er aendert
 * nichts an den Daten. */
let klappZu = {modi: null};

/* Der zuletzt in die Sichtbarkeit geholte Slot. Ohne das scrollte die Buehne
 * bei JEDEM Neuzeichnen zum gewaehlten Slot zurueck — auch dann, wenn man
 * gerade woanders hinsieht. */
let scanGezeigt = "";

/* Ziehen eines gewaehlten Slots im Bild: Startpunkt und laufender Versatz.
 * Der Versatz wird nur GEZEICHNET; geschrieben wird einmal beim Loslassen. Ein
 * Aufruf je Mausbewegung waere ein Dutzend Brueckenaufrufe pro Sekunde und ein
 * Rueckgaengig-Stapel voll mit Ein-Pixel-Schritten. */
let scanZiehStart = null;
let scanZiehVersatz = null;
let scanZiehGemacht = false;
/* Wann zuletzt mit den Pfeiltasten verschoben wurde. Eine gehaltene Taste ist
 * EIN Verschieben, nicht dreissig — nur der erste Schritt kommt auf den
 * Rueckgaengig-Stapel (`zaehlt`). */
let scanSchubZeit = 0;

/* **Die Reihenfolge ist die Rangfolge**, und sie ist dieselbe wie in `MODI`
 * (ein Test haelt beide Zug um Zug gegeneinander, nicht nur als Menge).
 * „Slots finden" steht direkt hinter „Auswaehlen", weil es das ist, was man
 * ZUERST macht: das Automatische ist der Normalfall, und erst wenn es nicht
 * klappt, zieht man einen Slot von Hand auf. Als vorletzte Kachel stand es da,
 * wo man den Notnagel sucht — und wer der Liste folgte, hatte 45 Slots einzeln
 * aufgezogen, bevor er es fand. */
/* Die Zustandsfarben aus dem Stylesheet, damit SVG-Text und Listen dieselbe
 * Quelle benutzen wie Umriss und Fuellung. `fill` im SVG nimmt kein
 * `var(--x)` aus einer fremden Regel entgegen, also einmal auslesen. */
const SLOT_FARBE = (() => {
  const s = getComputedStyle(document.documentElement);
  return {treffer: s.getPropertyValue("--slot-ok").trim(),
          fremditem: s.getPropertyValue("--slot-fremd").trim(),
          leer: s.getPropertyValue("--slot-offen").trim()};
})();

const SCAN_MODI = [
  {key: "wahl", text: "Auswählen", taste: "V", haupt: true,
   hilfe: "Slot anklicken — daneben zieht ein Rechteck um mehrere"},
  {key: "finden", text: "Slots finden", taste: "G", haupt: true,
   hilfe: "Bereich aufziehen, dann leeren Slot-Hintergrund anklicken"},
  {key: "slot", text: "Neuer Slot", taste: "S", haupt: true,
   hilfe: "zwei Ecken anklicken — wenn Finden nicht greift"},
  {key: "messen", text: "Hintergrundfarbe", taste: "F", hilfe: "Stelle im Slot anklicken"},
  {key: "klick", text: "Klickpunkt", taste: "K", hilfe: "wohin geklickt wird"},
  {key: "bereich", text: "Bereich", taste: "B", hilfe: "zwei Ecken um den Teil, der zählt"},
];

async function zeichneScans(frisch) {
  if (frisch || !SC) {
    const antwort = await frage("scan_daten");
    if (!antwort || ansicht !== "scans") return;
    SC = antwort;
  }
  const merk = fokusMerken();
  await scanBildPflegen();
  scanWerkzeuge();
  // Erst die Art, dann alles Weitere: sie entscheidet, welche Bloecke der
  // linken Spalte ueberhaupt gelten und wo die Aufnahme-Karte gerade haengt.
  scanArtPflegen();
  scanCanvasWerkzeuge();
  scanErgebnisZeichnen();
  scanListeZeichnen();
  erkBibliothekZeichnen();
  scanOverlay();
  scanZeigeGewaehlten();
  scanInspektor();
  setzeStatus(SC.status);
  fokusHerstellen(merk);
}

/** Ein Befehl an den Scan-Teil der Brücke. Antwort ist die neue Scan-Aufnahme. */
async function rufScan(name, daten) {
  const antwort = await frage(name, daten);
  if (!antwort) return;
  SC = antwort;
  // **Einen Scan zu oeffnen ist ein Wechsel des Zusammenhangs.** Danach gilt
  // wieder die Vorgabe — und die sind bei offenem Scan seine Items, also das,
  // weswegen man ihn geoeffnet hat. Vorher landete man auf der Scan-Liste und
  // sah den Namen, den man gerade angeklickt hatte, ein zweites Mal.
  if (name === "scan_oeffnen") scanListe = null;
  if (name === "scan_foto")
    scanAssistentSchritt = SC.schritte[1].fertig ? 3 : 2;
  else if (name === "scan_lernvorschau" || name === "scan_erkennen")
    scanAssistentSchritt = 3;
  else if (name === "scan_modus_setzen" && daten &&
           (daten.modus === "finden" || daten.modus === "slot"))
    scanAssistentSchritt = 2;
  await zeichneScans();
  scanAutoSpeichernPlanen(name);
}

function scanAutoSpeichernPlanen(ursache) {
  clearTimeout(scanAutoSaveTimer);
  if (!SC || !SC.dirty || ursache === "scan_speichern") return;
  const stand = $("scan-speicherstand");
  if (stand) { stand.textContent = "Entwurf wird gespeichert …"; stand.classList.add("offen"); }
  scanAutoSaveTimer = setTimeout(async () => {
    const antwort = await frage("scan_speichern");
    if (!antwort) return;
    SC = antwort;
    await zeichneScans();
  }, 900);
}

function scanCanvasWerkzeuge() {
  const sicht = $("sicht-scans");
  sicht.classList.toggle("gefuehrt", scanGefuehrt);
  sicht.classList.toggle("hat-bild", fotoDa());
  $("scan-frei").textContent = scanGefuehrt ? "Alle Werkzeuge" : "Nur Assistent";
  document.querySelectorAll("[data-scan-tool]").forEach((knopf) => {
    knopf.classList.toggle("an", SC.modus === knopf.dataset.scanTool);
    knopf.disabled = !SC.pillow && knopf.dataset.scanTool !== "wahl";
  });
  const modus = SCAN_MODI.find((m) => m.key === SC.modus);
  const erk = {region: "Region aufziehen", aktion: "Klickpunkt setzen"}[SC.modus];
  $("scan-werkzeugstand").textContent = SC.modus === "wahl"
    ? (scanArt === "item" ? "Slot anklicken zum Bearbeiten"
                          : "Werkzeug wählen oder rechts ein Feld ändern")
    // Beim Aufziehen steht der STAND dabei, nicht nur der Name des Werkzeugs:
    // ohne ihn sieht man dem Bild nicht an, ob schon eine Ecke gesetzt ist.
    : "Aktiv: " + (erk || (modus ? modus.text : SC.modus))
      + (SC.ecke ? " — erste Ecke gesetzt, zweite Ecke anklicken · ESC bricht ab" : "");
  $("scan-werkzeugstand").classList.toggle("art-warn", !!SC.ecke);
  $("scan-pin").classList.toggle("an", !!SC.werkzeug_fixiert);
  $("scan-pin").hidden = SC.modus === "wahl";
  $("scan-pin").setAttribute("aria-pressed", String(!!SC.werkzeug_fixiert));
  $("scan-pin-lang").textContent = SC.werkzeug_fixiert ? "Angeheftet" : "Anheften";
  $("scan-pin-kurz").textContent = SC.werkzeug_fixiert ? "Pin ✓" : "Pin";
  const stand = $("scan-speicherstand");
  stand.textContent = SC.dirty ? "Wird gespeichert …" : "✓ Gespeichert";
  stand.classList.toggle("offen", !!SC.dirty);
}

function scanErgebnisZeichnen() {
  const ziel = $("scan-ergebnis");
  ziel.replaceChildren();
  // Boss und Icon haben ein anderes Ergebnis als ein Item-Scan: EIN Treffer
  // statt 45. Dieselbe Leiste, weil es dieselbe Frage ist — „was hat der Test
  // ergeben" —, aber ein anderer Inhalt.
  if (scanArt !== "item") {
    ziel.hidden = !erkTestleiste(ziel);
    return;
  }
  const e = SC.ergebnis;
  ziel.hidden = !e;
  if (!e) return;
  ziel.append(
    el("b", {}, "Testergebnis"),
    el("span", {class: "kennzahl", style: "color:var(--ok)"}, e.erkannt + " erkannt"),
    el("span", {class: "kennzahl", style: "color:var(--accent)"}, e.unbekannt + " unbekannt"),
    el("span", {class: "kennzahl", style: "color:var(--slot-fremd)"}, e.fremd + " noch nicht im Scan"),
    el("span", {class: "wachse"})
  );
  if (e.unbekannt) ziel.appendChild(el("button", {class: "btn still",
    onclick: () => scanErgebnisNaechster("unbekannt_slots")}, "Nächsten unbekannten zeigen"));
  if (e.fremd) ziel.appendChild(el("button", {class: "btn haupt",
    onclick: () => rufScan("scan_treffer_uebernehmen")}, "Sichere Treffer übernehmen"));
}

function scanErgebnisNaechster(feld) {
  const namen = (SC.ergebnis && SC.ergebnis[feld]) || [];
  if (!namen.length) return;
  const aktuell = namen.indexOf(SC.wahl.name);
  const name = namen[(aktuell + 1) % namen.length];
  rufScan("scan_waehlen", {art: "slot", name: name});
}

/** Gibt es ein echtes Bild — oder nur die aus den Slots gerechnete Flaeche? */
function fotoDa() { return !!(SC && SC.foto && SC.foto.bild); }

/** Holt das Bild nur, wenn es ein neues gibt — es ist der grosse Brocken. */
async function scanBildPflegen() {
  const bild = $("scan-bild");
  const leer = $("scan-leer");
  if (!SC.foto) {
    $("scan-flaeche").hidden = true;
    $("scan-ohne-bild").hidden = true;
    leer.hidden = false;
    leer.textContent = SC.pillow
      ? "Noch kein Bild. „Screenshot aufnehmen“ friert den Bildschirm ein — darauf werden die Slots aufgezogen."
      : "Ohne Pillow gibt es kein Bild (pip install pillow). Slots lassen sich dann nur über die Zahlenfelder rechts setzen.";
    return;
  }
  $("scan-flaeche").hidden = false;
  leer.hidden = true;
  // Ohne Bild bleibt die Flaeche leer, aber sie hat die Groesse und die Lage
  // der Slots — man sieht also, was der Scan hat, und kann es anfassen.
  $("scan-flaeche").classList.toggle("ohne-bild", !fotoDa());
  $("scan-ohne-bild").hidden = fotoDa();
  // Woran man merkt, dass eine ANDERE Flaeche dasteht: beim Bild der
  // Zeitstempel, sonst ihre Groesse. Ohne diese Marke passte entweder gar
  // nichts mehr ein (Zoom vom vorigen Scan) oder bei jedem Neuzeichnen wieder,
  // was jedes Hineinzoomen sofort zuruecksetzte.
  const marke = fotoDa() ? SC.foto.stand
                         : -(SC.foto.breite * 100000 + SC.foto.hoehe);
  if (marke !== scanFotoStand) {
    scanFotoStand = marke;
    if (fotoDa()) {
      const url = await frage("scan_bild");
      if (url) bild.src = url;
    } else {
      bild.removeAttribute("src");
    }
    scanEinpassen();
  }
  $("scan-groesse").textContent = fotoDa()
    ? SC.foto.breite + "×" + SC.foto.hoehe
    : "kein Bild";
}

function scanEinpassen() {
  if (!SC || !SC.foto) return;
  const platz = $("scan-buehne").clientWidth - 24;
  // Ein Bild wird nie vergroessert — jedes Pixel darueber waere erfunden, und
  // gemessen wird ohnehin im Original. Die aus den Slots gerechnete Flaeche hat
  // keine Pixel, die man faelschen koennte: sie darf die Buehne fuellen, sonst
  // haengt ein Inventar von 300 px verloren in einer Ecke.
  const grenze = fotoDa() ? 1 : 4;
  scanZoom = Math.max(0.05, Math.min(grenze, platz / SC.foto.breite));
  scanZoomHand = false;
  scanZoomAnwenden();
}

function scanZoomAnwenden() {
  if (!SC || !SC.foto) return;
  const f = $("scan-flaeche");
  f.style.width = Math.round(SC.foto.breite * scanZoom) + "px";
  // Die Hoehe kommt sonst vom Bild. Ohne eines waere sie 0, und die Flaeche
  // haette weder Platz fuer die Slots noch etwas zum Anklicken.
  f.style.height = fotoDa() ? "" : Math.round(SC.foto.hoehe * scanZoom) + "px";
  $("scan-zoom").textContent = Math.round(scanZoom * 100) + " %";
  scanOverlay();
}

/* ---- Umrechnung: Bildschirm <-> Bild. Die einzige Stelle, die das darf. ---- */

function scanZuBild(x, y) {
  const f = SC.foto;
  return [(x - f.links) * f.skala, (y - f.oben) * f.skala];
}

function scanZuSchirm(bx, by) {
  const f = SC.foto;
  return [Math.round(f.links + bx / f.skala), Math.round(f.oben + by / f.skala)];
}

function scanWerkzeuge() {
  const wahl = $("scan-offen");
  wahl.replaceChildren();
  wahl.appendChild(el("option", {value: ""}, SC.scans.length
    ? "— keiner (ganzer Bestand) —" : "— noch kein Item-Scan —"));
  for (const c of SC.scans) {
    const o = el("option", {value: c.name}, c.name);
    if (c.name === SC.offen) o.selected = true;
    wahl.appendChild(o);
  }
  const offen = SC.scans.find((c) => c.name === SC.offen);
  $("scan-umfang").textContent = offen
    ? offen.slots.length + " Slots · " + offen.items.length + " Items"
    : SC.slots.length + " Slots · " + SC.items.length + " Items";

  // Der Name gehoert zum offenen Scan - ohne einen gibt es nichts zu benennen,
  // dann ist das Feld weg statt leer und wirkungslos.
  $("scan-name-zeile").hidden = !offen;
  if (offen && $("scan-name") !== document.activeElement) $("scan-name").value = offen.name;

  const ziel = $("scan-modi");
  ziel.replaceChildren();
  for (const m of SCAN_MODI) {
    const an = SC.modus === m.key;
    ziel.appendChild(el("button", {
      class: "scan-modus" + (an ? " an" : ""),
      // Ein Umschalten sieht man einem Bedienelement nicht an — dieselbe Regel
      // wie bei der ELSE-Kachel im Inspektor. Es steht deshalb im Tooltip der
      // markierten Kachel UND im Hinweis unter dem Raster.
      title: an && m.key !== "wahl"
        ? "Nochmal klicken = zurück zum Auswählen" : "",
      onclick: () => rufScan("scan_modus_setzen", {modus: m.key}),
    },
      el("span", {}, m.text),
      el("span", {class: "taste"}, m.taste),
      el("span", {class: "klein"}, m.hilfe)));
  }
  $("scan-modi-zurueck").hidden = SC.modus === "wahl";
  const modus = SCAN_MODI.find((m) => m.key === SC.modus);
  $("scan-modus-kurz").textContent = modus ? modus.text : "";
  klappPflegen();
  scanSchritte();
  $("scan-foto").disabled = !SC.pillow;
  const fensterquelle = !!(SC.fenster_titel || SC.fenster_id);
  $("scan-foto").textContent = fensterquelle ? "Fenster aufnehmen"
    : (SC.bereich ? "Bereich aufnehmen" : "Screenshot aufnehmen");

  // Der Bereich gilt fuer JEDE weitere Aufnahme dieses Scans — er muss also
  // dastehen, nicht nur in der Statuszeile aufblitzen.
  const bz = $("scan-bereich");
  const groesse = SC.bereich
    ? (SC.bereich[2] - SC.bereich[0]) + "×" + (SC.bereich[3] - SC.bereich[1])
      + " ab (" + SC.bereich[0] + ", " + SC.bereich[1] + ")"
    : "";
  bz.textContent = fensterquelle
    ? "Fenster „" + (SC.fenster_titel || "gewählt") + "“ · relative Slots"
      + (groesse ? " · " + groesse : "")
      + (!SC.fenster_verfuegbar && SC.fenster_titel ? " · nicht geöffnet" : "")
    : (!SC.bereich ? "Vollbild" : "Bereich " + groesse);
  // Bei einem gewaehlten Fenster steht dabei, was das bedeutet: es wird direkt
  // abgebildet, also darf das Studio davor liegen.
  bz.title = fensterquelle
    ? "Editor und Live-Scan verwenden dieselbe Aufnahmequelle. Verschieben wird automatisch ausgeglichen; beim Desktop-Fallback muss das Fenster sichtbar sein."
    : (SC.bereich ? "Ausschnitt vom Bildschirm — hier darf nichts davor liegen." : "");
  bz.classList.toggle("an", !!SC.bereich || fensterquelle);
  $("scan-vollbild").disabled = (!SC.bereich && !fensterquelle) || !SC.pillow;
  // Aufziehen geht nur auf einem Bild — vorher gibt es nichts anzuklicken.
  const auf = $("scan-aufziehen");
  auf.disabled = !fotoDa();
  auf.classList.toggle("an", SC.modus === "bereich");
  scanFensterPflegen();
}

/** Nur die technischen Sonderwerkzeuge sind noch ein klassischer Klappbereich. */
function klappVorgabe(schluessel) { return false; }

function klappPflegen() {
  for (const [schluessel, id] of [["modi", "ab-modi"]]) {
    const zu = klappZu[schluessel] === null ? klappVorgabe(schluessel)
                                            : klappZu[schluessel];
    $(id).classList.toggle("zu", zu);
  }
}

/** Ein Assistent mit genau einer offenen Aufgabe und jederzeit erreichbaren Schritten. */
function scanSchritte() {
  if (!scanAssistentSchritt) {
    const offen = SC.schritte.find((s) => !s.fertig);
    scanAssistentSchritt = offen ? offen.nr : 3;
  }
  for (const s of SC.schritte) {
    const karte = $("scan-assistent-" + s.nr);
    const offen = scanAssistentSchritt === s.nr;
    karte.classList.toggle("offen", offen);
    karte.classList.toggle("fertig", s.fertig);
    $("scan-schritt-" + s.nr + "-nr").textContent = s.fertig ? "✓" : String(s.nr);
    $("scan-schritt-" + s.nr + "-inhalt").hidden = !offen;
  }
  const scan = SC.scans.find((c) => c.name === SC.offen);
  const slots = scan ? scan.slots.length : SC.slots.length;
  const items = scan ? scan.items.length : SC.items.length;
  $("scan-schritt-1-status").textContent = fotoDa()
    ? "Bild gespeichert · " + SC.foto.breite + "×" + SC.foto.hoehe : "Noch kein Bild";
  $("scan-schritt-2-status").textContent = slots
    ? slots + (slots === 1 ? " Slot" : " Slots") : "Noch keine Slots";
  $("scan-schritt-3-status").textContent = items
    ? items + (items === 1 ? " Item" : " Items") : "Noch keine Items";
  $("scan-slots-finden").disabled = !fotoDa() || !SC.pillow;
  $("scan-slot-neu").disabled = !fotoDa() || !SC.pillow;
  $("scan-test").disabled = !fotoDa() || !slots;
  $("scan-lernen").disabled = !fotoDa() || !slots;
}

let scanFenster = [];

/** Die offenen Fenster zur Auswahl — nur nachgeholt, wenn Pillow da ist. */
async function scanFensterPflegen() {
  const wahl = $("scan-fenster");
  if (!SC.pillow) { wahl.hidden = true; return; }
  scanFenster = (await frage("scan_fenster")) || [];
  wahl.hidden = false;
  wahl.replaceChildren();
  wahl.appendChild(el("option", {value: ""}, scanFenster.length
    ? "— kein Fenster (ganzer Bildschirm) —" : "— keine Fenster gefunden —"));
  scanFenster.forEach((f, i) => {
    // Die Lage steht dabei, weil sie das einzige Unterscheidungsmerkmal ist,
    // wenn dasselbe Programm mehrmals offen ist.
    const b = f.bereich;
    const o = el("option", {value: String(i)},
      f.titel + "  ·  " + (b[2] - b[0]) + "×" + (b[3] - b[1])
      + " ab (" + b[0] + ", " + b[1] + ")");
    // **Die Wahl bleibt stehen.** Seit die Auswahl nicht mehr selbst aufnimmt,
    // liegt zwischen "Fenster gewaehlt" und "Bild da" ein zweiter Klick — und
    // in dieser Zeit muss ablesbar sein, WAS aufgenommen wird.
    if (SC.fenster_id && f.id === SC.fenster_id) o.selected = true;
    wahl.appendChild(o);
  });
  if (SC.fenster_titel && !scanFenster.some((f) => f.id === SC.fenster_id)) {
    wahl.appendChild(el("option", {
      value: "__nicht_offen__", selected: true, disabled: true,
    }, "„" + SC.fenster_titel + "“ · momentan nicht geöffnet"));
  }
}

/** Stehen die Item-Masken in der rechten Spalte?
 *
 * **Die breitere Spalte war die leerere.** Links sind 290 px und darin fuenf
 * Bloecke uebereinander — die Liste, mit der man arbeitet, faengt ganz unten an;
 * rechts sind 370 px und standen seit dem Umbau fast leer, weil Name, Kategorie
 * und Prioritaet in die Maske gewandert sind. Also wandert die Liste dorthin,
 * wo sie hinpasst.
 *
 * Nur die Items: Scans und Slots bleiben links. Der Scan ist Navigation (man
 * waehlt ihn und arbeitet dann woanders), und die Slots zieht man im BILD auf —
 * ihre Liste ist der zweite Weg dorthin, nicht die Arbeitsflaeche. */
function scanItemsRechts() {
  return scanArt === "item" && scanListeAktiv() === "items";
}

/** Welche Liste gilt: die gewaehlte, sonst die zur Lage passende Vorgabe. */
function scanListeAktiv() {
  if (scanListe) return scanListe;
  if (scanArt === "boss") return "bosse";
  if (scanArt === "icon") return "icons";
  return SC && SC.offen ? "items" : "scans";
}

function scanListeZeichnen() {
  const tabs = $("scan-listen-tabs");
  const offen = scanListeAktiv();
  tabs.replaceChildren();
  if (scanArt !== "item") {
    $("scan-filterzeile").replaceChildren();
    const ziel = $("scan-liste");
    ziel.replaceChildren();
    if (scanArt === "icon") {
      tabs.appendChild(el("button", {class: "tab an"},
        "Icon-Scans " + SC.icon_scans.length));
      return erkListeIcons(ziel);
    }
    // Zwei Listen, weil es zwei Orte sind: die Bosse DIESES Scans und die,
    // die in jedem gelten. Sie zusammenzuwerfen hiesse, den Unterschied zu
    // verlieren, an dem alles haengt.
    for (const [key, text, zahl] of [["bosse", "Bosse", erkBosse().length],
                                     ["bibliothek", "Bibliothek",
                                      SC.global_bosses.length]]) {
      tabs.appendChild(el("button", {class: "tab" + (offen === key ? " an" : ""),
        onclick: () => { scanListe = key; zeichneScans(); }}, text + " " + zahl));
    }
    return offen === "bibliothek" ? erkListeBibliothek(ziel) : erkListeBosse(ziel);
  }
  // Die Zahl am Reiter ist die der SICHTBAREN Eintraege — sonst stuende dort 40,
  // waehrend zwei in der Liste stehen, und man sucht den Rest.
  // Reihenfolge = Rangfolge: der Scan ist das Uebergeordnete, Slots und Items
  // haengen an ihm.
  const gruppen = [["scans", "Scans", SC.scans.length, SC.scans.length],
                   ["slots", "Slots", scanSichtbar(SC.slots, false).length, SC.slots.length],
                   ["items", "Items", scanSichtbar(SC.items, true).length, SC.items.length]];
  for (const [key, text, sichtbar, gesamt] of gruppen) {
    tabs.appendChild(el("button", {
      class: "tab" + (offen === key ? " an" : ""),
      title: sichtbar === gesamt ? "" : gesamt + " insgesamt",
      onclick: () => { scanListe = key; zeichneScans(); },
    }, text + " " + sichtbar + (sichtbar === gesamt ? "" : "/" + gesamt)));
  }

  // Filter und Liste gehoeren zusammen — stehen die Masken rechts, ziehen beide
  // um, und der Abschnitt hier schrumpft auf die Reiter.
  const rechts = scanItemsRechts();
  $("ab-listen").classList.toggle("nur-reiter", rechts);
  const filter = $("scan-filterzeile");
  const ziel = $("scan-liste");
  filter.replaceChildren();
  ziel.replaceChildren();
  if (rechts) {
    // **Ein Reiter, der Inhalt woanders aufmacht, sagt das.** Sonst schrumpft
    // hier etwas zusammen und drueben erscheint etwas — und ob das
    // zusammengehoert, muss man raten.
    ziel.appendChild(el("p", {class: "hinweis"},
      "Die Item-Masken stehen rechts — dort ist Platz für Name, Kategorie und "
      + "Priorität nebeneinander."));
    return;
  }
  scanFilterzeile(filter, offen);
  if (offen === "slots") return scanListeSlots(ziel);
  if (offen === "items") return scanListeItems(ziel);
  return scanListeScans(ziel);
}

/** Was die Liste einschraenkt: Mitgliedschaft, „alle dazu/raus", Kategorie. */
function scanFilterzeile(filter, offen) {
  if (SC.offen && offen !== "scans") {
    const art = offen === "slots" ? "slot" : "item";
    const gesamt = offen === "slots" ? SC.slots : SC.items;
    const drin = gesamt.filter((e) => e.dabei).length;
    filter.appendChild(schalter("nur aus „" + SC.offen + "\u201c",
      SC.nur_dabei, (v) => rufScan("scan_filter", {wert: v})));
    // Ein Scan umfasst fast immer ALLES seines Spiels - 56 Haekchen einzeln
    // zu setzen war der Weg dorthin. Der Knopf SAGT, was er tut, statt zu
    // schalten: ein Schalter haette drei Staende (keins/manche/alle), und bei
    // "manche" waere er nicht zu beschriften.
    filter.appendChild(el("button", {class: "btn still",
      title: drin + " von " + gesamt.length + " sind dabei",
      onclick: () => rufScan("scan_alle", {art: art, wert: drin < gesamt.length})},
      drin < gesamt.length ? "alle dazu" : "alle raus"));
  }
  if (offen === "items" && SC.kategorien.length) {
    filter.appendChild(auswahl("", [{wert: "", text: "alle Kategorien"}].concat(
      SC.kategorien.map((k) => ({wert: k, text: k}))), scanKategorie,
      (v) => { scanKategorie = v; zeichneScans(); }));
  }
}

/** Was die Liste zeigt: gefiltert nach offenem Scan und Kategorie. */
function scanSichtbar(eintraege, mitKategorie) {
  let liste = eintraege;
  if (SC.offen && SC.nur_dabei) liste = liste.filter((e) => e.dabei);
  if (mitKategorie && scanKategorie)
    liste = liste.filter((e) => (e.kategorie || "") === scanKategorie);
  return liste;
}

function scanListeSlots(ziel) {
  const liste = scanSichtbar(SC.slots, false);
  if (!liste.length) {
    ziel.appendChild(el("p", {class: "hinweis"}, SC.slots.length
      ? "Kein Slot gehört zu diesem Scan. Den Filter ausschalten und Häkchen setzen."
      : "Noch keine Slots. Modus „Neuer Slot“, dann zwei Ecken im Bild anklicken."));
    return;
  }
  for (const s of liste) {
    ziel.appendChild(el("button", {
      class: "scan-zeile" + (SC.auswahl.includes(s.name)
        || (SC.wahl.art === "slot" && SC.wahl.name === s.name) ? " an" : ""),
      onclick: () => rufScan("scan_waehlen", {art: "slot", name: s.name}),
    },
      el("span", {class: "kugel" + (s.farbe ? "" : " ohne"),
                  style: s.farbe ? "background:" + s.farbe : ""}),
      el("span", {class: "name"}, s.name),
      // Ein winziger Slot ist im Bild kaum zu treffen — in der Liste ist er so
      // gross wie jeder andere. Deshalb steht die Warnung HIER: das ist der
      // Weg, ihn auszuwaehlen und zu loeschen.
      s.winzig
        ? el("span", {class: "klein", style: "color:var(--err)",
                      title: "Zu klein zum Erkennen — hier auswählen und löschen"},
             s.breite + "×" + s.hoehe + " ⚠")
        : (s.treffer && s.treffer.name
            ? el("span", {class: "klein",
                          style: "color:var(" + (s.treffer.fremd ? "--slot-fremd"
                                                                 : "--slot-ok") + ")",
                          title: s.treffer.fremd
                            ? "erkannt, gehört aber noch nicht zu diesem Scan" : ""},
                 s.treffer.name)
            // Nichts erkannt = hier ist noch zu lernen. Dieselbe Farbe wie sein
            // Rechteck im Bild, damit Liste und Bild zusammengehen.
            : el("span", {class: "klein mono",
                          style: s.treffer ? "color:var(--slot-offen)" : ""},
                 s.treffer ? "unbekannt" : s.breite + "×" + s.hoehe))));
  }
}

function scanListeItems(ziel) {
  const liste = scanSichtbar(SC.items, true).slice().sort((a, b) =>
    (a.kategorie || "").localeCompare(b.kategorie || "", "de") ||
    a.prioritaet - b.prioritaet || a.name.localeCompare(b.name, "de"));
  if (!liste.length) {
    ziel.appendChild(el("p", {class: "hinweis"}, SC.items.length
      ? "Kein Item passt zum Filter. Der Bestand hat " + SC.items.length + " Stück."
      : "Noch keine Items. Einen Slot wählen und rechts „Item lernen“ — oder alle "
        + "Slots auf einmal."));
    return;
  }
  scanVorschauenHolen(liste.map((i) => i.name));
  let letzteKategorie = null;
  for (const i of liste) {
    const kategorie = i.kategorie || "Ohne Kategorie";
    if (kategorie !== letzteKategorie) {
      ziel.appendChild(el("div", {class: "scan-kategorie-kopf"}, kategorie));
      letzteKategorie = kategorie;
    }
    ziel.appendChild(scanItemMaske(i));
  }
}

/** Ein Item als kleine Maske: Haken, Name, Kategorie, Priorität — direkt in der Liste.
 *
 * **Ein Ein-Aus-Knopf war zu wenig.** Die Liste konnte nur „gehört dazu / gehört
 * nicht dazu"; alles andere kostete einen Klick in die Liste, einen Blick nach
 * rechts und einen Weg zurueck — bei sechzig Items sechzig Mal. Die vier Dinge,
 * die man dabei wirklich aendert, sind immer dieselben, und sie passen
 * nebeneinander.
 *
 * Was NICHT hier steht: Vorlagen, Marker, Konfidenz, Loeschen. Das gehoert dem
 * Inspektor — er hat den Platz fuer das grosse Bild, und man braucht es selten.
 * Name, Kategorie und Prioritaet stehen dafuer NUR hier: dieselbe Sache an zwei
 * Stellen waere zwei Wahrheiten, und man muesste raten, welche fuehrt. */
function scanItemMaske(i) {
  const setze = (feld, wert) => rufScan("scan_item_setzen",
                                        {name: i.name, feld: feld, wert: wert});
  const gewaehlt = SC.wahl.art === "item" && SC.wahl.name === i.name;
  const bild = scanVorschauen.get(i.name);

  const name = el("input", {value: i.name, autocomplete: "off",
                            title: "Name — zugleich die Referenz in jedem Scan"});
  name.addEventListener("change", () => setze("name", name.value));
  name.addEventListener("keydown", (e) => { if (e.key === "Enter") name.blur(); });

  // Vorhandene anklicken, neue tippen — dasselbe Bedienelement wie in der
  // Lern-Vorschau. Ein freies Textfeld allein macht aus „Helme" und „helme"
  // zwei Kategorien, und Items derselben Kategorie konkurrieren miteinander.
  const kat = kategorieWahl(i.kategorie || "", (v) => setze("kategorie", v),
    {titel: "Items derselben Kategorie konkurrieren; die kleinere Priorität gewinnt",
     leer: "— ohne —", schluessel: "item:" + i.name});

  const prio = el("input", {type: "number", value: i.prioritaet, min: 0, step: 1,
                            title: "Priorität — kleiner gewinnt"});
  prio.addEventListener("change", () => {
    if (prio.value.trim() !== "") setze("prioritaet", Number(prio.value));
  });
  prio.addEventListener("keydown", (e) => { if (e.key === "Enter") prio.blur(); });

  const felder = el("div", {class: "scan-maske-felder"}, name,
    el("div", {class: "scan-maske-unten"}, kat, prio), scanItemStand(i));

  const maske = el("div", {class: "scan-maske" + (gewaehlt ? " an" : "")});
  if (SC.offen) {
    // Der Haken ist die vierte Angabe und steht deshalb IN der Maske statt in
    // einer eigenen Liste: „gehoert zu diesem Scan" ist eine Eigenschaft des
    // Items im Zusammenhang, keine getrennte Verwaltung.
    const kasten = el("input", {type: "checkbox",
      title: "gehört zum Scan „" + SC.offen + "“"});
    kasten.checked = !!i.dabei;
    kasten.addEventListener("change", () => rufScan("scan_mitglied",
      {scan: SC.offen, art: "item", name: i.name}));
    maske.appendChild(el("label", {class: "an"}, kasten));
  } else {
    maske.appendChild(el("span", {}));
  }
  maske.appendChild(bild
    ? el("img", {class: "mini", src: bild, alt: ""})
    : el("span", {class: "kugel" + (i.marker.length ? "" : " ohne"),
                  style: i.marker.length ? "background:" + i.marker[0] : ""}));
  maske.appendChild(felder);
  // **Das Gewaehlte klappt seine Einstellungen hier auf**, statt sie in eine
  // andere Spalte zu legen: Vorlage, Marker, Konfidenz und Loeschen gehoeren
  // diesem Item, und man sieht beim Arbeiten daran nicht zwischen zwei Orten
  // hin und her. Nur beim gewaehlten — sechzig aufgeklappte Bloecke waeren
  // keine Liste mehr.
  if (gewaehlt) {
    const detail = el("div", {class: "scan-maske-detail"});
    scanItemDetails(detail, i);
    maske.appendChild(detail);
  }
  // Ein Klick auf die Maske waehlt das Item — aber nicht, wenn er einem Feld
  // galt. Sonst nimmt der Neuaufbau das Feld weg, in das gerade geklickt wurde.
  maske.addEventListener("click", (e) => {
    if (e.target.closest("input, label, button, select, summary, details")) return;
    if (!gewaehlt) rufScan("scan_waehlen", {art: "item", name: i.name});
  });
  return maske;
}

/** Die Zustandszeile einer Item-Maske: erkannt, stumm, fehlende Vorlage.
 *
 * **„Items erkennen" war in dieser Liste unsichtbar.** Der Knopf faerbte die
 * Rechtecke im Bild und fuellte die Ergebnisleiste — wer aber in der Item-Liste
 * stand (und das ist die Liste, in der man arbeitet), sah nach dem Klick
 * nichts und hielt ihn fuer wirkungslos. Hier steht jetzt, WO das Item gerade
 * gefunden wurde. */
function scanItemStand(i) {
  const teile = [];
  if ((i.erkannt_in || []).length) {
    teile.push(el("span", {style: "color:var(--slot-" + (i.dabei ? "ok" : "fremd") + ")",
      title: i.dabei ? "" : "erkannt, gehört aber noch nicht zu diesem Scan"},
      "erkannt in " + i.erkannt_in.slice(0, 2).join(", ")
      + (i.erkannt_in.length > 2 ? " +" + (i.erkannt_in.length - 2) : "")));
  }
  if (i.stumm) {
    teile.push(el("span", {style: "color:var(--err)",
      title: "Weder Vorlage noch Marker — dieses Item wird nie erkannt"}, "stumm"));
  }
  if ((i.fehlende_scan_groessen || []).length) {
    teile.push(el("span", {style: "color:var(--accent)",
      title: "Für diese Slot-Größe noch keine Vorlage gelernt"},
      "⚠ " + i.fehlende_scan_groessen.map((g) => g[0] + "×" + g[1]).join(", ")));
  }
  if (!teile.length) teile.push(el("span", {class: "mono"}, "P" + i.prioritaet));
  return el("div", {class: "scan-maske-stand"}, teile);
}

function scanListeScans(ziel) {
  if (!SC.scans.length) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Noch kein Item-Scan. Er ist die Klammer um Slots und Items — bei mehreren "
      + "Spielen der einzige Weg, sie auseinanderzuhalten."));
  }
  for (const c of SC.scans) {
    // Ein Klick oeffnet ihn: waehlen und oeffnen sind hier dasselbe, denn ein
    // Scan, den man ansieht, ist der, an dem man arbeitet.
    ziel.appendChild(el("button", {
      class: "scan-zeile" + (SC.offen === c.name ? " an" : ""),
      onclick: () => rufScan("scan_oeffnen", {name: c.name}),
    },
      el("span", {class: "name"}, c.name),
      c.fehlend.length
        ? el("span", {class: "klein", style: "color:var(--err)"}, c.fehlend.length + "× fehlt")
        : el("span", {class: "klein mono"}, c.slots.length + "S/" + c.items.length + "I")));
  }
}

/** Template-Bilder nachholen, die wir noch nicht haben — in EINEM Aufruf. */
async function scanVorschauenHolen(namen) {
  const fehlend = namen.filter((n) => !scanVorschauen.has(n));
  if (!fehlend.length) return;
  // Vormerken, damit ein zweiter Aufbau nicht nochmal fragt.
  for (const n of fehlend) scanVorschauen.set(n, "");
  const antwort = await frage("scan_vorschau", {namen: fehlend});
  if (!antwort) return;
  let neu = false;
  for (const [name, url] of Object.entries(antwort)) {
    if (url) { scanVorschauen.set(name, url); neu = true; }
  }
  if (neu && ansicht === "scans") { scanListeZeichnen(); scanInspektor(); }
}

/* ------------------------------------------------------------------ Overlay */

function scanOverlay() {
  const svg = $("scan-overlay");
  if (!SC || !SC.foto) { svg.replaceChildren(); return; }
  const f = SC.foto;
  svg.setAttribute("viewBox", "0 0 " + f.breite + " " + f.hoehe);
  svg.replaceChildren();
  // Schrift und Punktgroessen werden gegen den Zoom gerechnet, damit sie in
  // jeder Vergroesserung gleich gross auf dem Schirm stehen. Striche erledigt
  // `vector-effect` im CSS.
  const px = 1 / Math.max(scanZoom, 0.001);
  // Bei offenem Item-Scan: seine Slots normal, alle anderen gestrichelt und
  // blass. Ohne das muss man Liste und Bild im Kopf zusammenbringen.
  const offen = SC.scans.find((c) => c.name === SC.offen) || null;

  // Was gerade gezogen wird, wird SCHON VERSCHOBEN gezeichnet — sonst zieht man
  // blind und sieht das Ergebnis erst beim Loslassen. Nur eine Zeichnung: die
  // Daten aendert erst der Aufruf beim Loslassen.
  const zieh = scanZiehVersatz || [0, 0];
  const gezogen = zieh[0] || zieh[1]
    ? new Set(scanGewaehlteSlots().map((s) => s.name)) : null;

  // Slots gehoeren dem Item-Scan. Auf einem Boss-Bild waeren 45 Rechtecke kein
  // Ueberblick, sondern ein Gitter ueber der einen Region, um die es geht.
  for (const s of (scanArt === "item" ? SC.slots : [])) {
    const fremd = offen && !s.dabei ? " fremd" : "";
    // Bei eingeschaltetem Filter bleiben fremde Slots ganz weg: sie gehoeren zu
    // einem anderen Spiel und liegen womoeglich an genau derselben Stelle.
    // Ausgeschaltet stehen sie gestrichelt da — dann sucht man ja gerade das,
    // was man noch dazunehmen koennte.
    if (fremd && SC.nur_dabei) continue;
    const v = gezogen && gezogen.has(s.name) ? zieh : [0, 0];
    const [x1, y1] = scanZuBild(s.region[0] + v[0], s.region[1] + v[1]);
    const [x2, y2] = scanZuBild(s.region[2] + v[0], s.region[3] + v[1]);
    // Gewaehlt ist, was in der Auswahl steht — bei einem Rechteck sind das
    // dreissig. `SC.wahl` bleibt der eine, den der Inspektor bearbeitet.
    const gewaehlt = SC.auswahl.includes(s.name)
      || (SC.wahl.art === "slot" && SC.wahl.name === s.name);
    // Gruen = hier liegt ein Item, das der Scan kennt. Amber = erkannt, aber
    // noch nicht Mitglied dieses Scans — anderer Zustand, andere Farbe, sonst
    // sucht man spaeter, warum der Scan das Gruene nicht findet.
    const zustand = (s.treffer
      ? (s.treffer.name ? (s.treffer.fremd ? " fremditem" : " treffer") : " leer")
      : "") + fremd;
    // Die Fuellung traegt denselben Zustand wie der Umriss: auf einem bunten
    // Spielbild ist die Flaeche das, was man sieht, der Strich schaerft nur.
    svg.appendChild(svgEl("rect", {x: x1, y: y1, width: x2 - x1, height: y2 - y1,
      class: "scan-fuellung" + zustand + (gewaehlt ? " gewaehlt" : "")}));
    svg.appendChild(svgEl("rect", {x: x1, y: y1, width: x2 - x1, height: y2 - y1,
      class: "scan-slot" + zustand + (gewaehlt ? " gewaehlt" : "")}));
    // Der Name steht ueber dem Rechteck, das Erkennungsergebnis darunter — so
    // ueberdeckt keins von beiden das Bild im Slot.
    //
    // Aber nur, wenn er auch hineinpasst: die Schrift steht in SCHIRM-Pixeln
    // (gegen den Zoom gerechnet), der Slot in Bild-Pixeln. Bei 45 Slots passt
    // das Bild nur klein ins Fenster, und dann war jede Marke breiter als ihr
    // Slot — 45 Namen uebereinander, aus denen keiner mehr lesbar war. Der
    // gewaehlte behaelt seinen Namen: welcher es ist, ist die eine Frage, die
    // auch bei 20 % beantwortet sein muss.
    const breit = (x2 - x1) * scanZoom;      // Breite auf dem Schirm
    if (breit >= 34 || gewaehlt) {
      svg.appendChild(svgEl("text", {x: x1, y: y1 - 3 * px, class: "scan-marke" + fremd,
        "font-size": 11 * px, "stroke-width": 3 * px}, s.name));
    }
    if (s.treffer && s.treffer.name && (breit >= 34 || gewaehlt)) {
      // Dieselbe Quelle wie der Umriss — sonst laeuft die Marke von ihrem
      // eigenen Rechteck farblich weg.
      svg.appendChild(svgEl("text", {x: x1, y: y2 + 12 * px, class: "scan-marke",
        "font-size": 10 * px, "stroke-width": 3 * px,
        fill: SLOT_FARBE[s.treffer.fremd ? "fremditem" : "treffer"]}, s.treffer.name));
    }
    const [kx, ky] = scanZuBild(s.klick[0] + v[0], s.klick[1] + v[1]);
    const arm = 4 * px;
    svg.appendChild(svgEl("path", {class: "scan-kreuz",
      d: `M${kx - arm} ${ky}H${kx + arm}M${kx} ${ky - arm}V${ky + arm}`}));
  }

  if (scanArt !== "item") erkOverlay(svg, px);

  // Der Suchbereich der Slot-Erkennung steht, bis die Farbe gezeigt ist. Ohne
  // ihn klickt man den Hintergrund an, ohne zu sehen, worin gesucht wird — und
  // ein zu eng gezogener Bereich saehe genauso aus wie ein zu weiter.
  if (SC.suchbereich) {
    const [ax, ay] = scanZuBild(SC.suchbereich[0], SC.suchbereich[1]);
    const [bx, by] = scanZuBild(SC.suchbereich[2], SC.suchbereich[3]);
    svg.appendChild(svgEl("rect", {class: "scan-suchbereich",
      x: ax, y: ay, width: bx - ax, height: by - ay}));
    svg.appendChild(svgEl("text", {x: ax, y: ay - 4 * px, class: "scan-marke",
      "font-size": 11 * px, "stroke-width": 3 * px, fill: "#7C9CF5"},
      "Suchbereich — jetzt leeren Slot-Hintergrund anklicken"));
  }

  // Die erste Ecke und das entstehende Rechteck: ohne die sieht man beim
  // Aufziehen nicht, was man gerade baut.
  if (SC.ecke) {
    const [ex, ey] = scanZuBild(SC.ecke[0], SC.ecke[1]);
    svg.appendChild(svgEl("circle", {cx: ex, cy: ey, r: 3 * px, class: "scan-eck"}));
    if (scanZeiger) {
      const [zx, zy] = scanZuBild(scanZeiger[0], scanZeiger[1]);
      svg.appendChild(svgEl("rect", {class: "scan-vorschau",
        x: Math.min(ex, zx), y: Math.min(ey, zy),
        width: Math.abs(zx - ex), height: Math.abs(zy - ey)}));
    }
  }
}

/** Wie el(), aber im SVG-Namensraum — sonst zeichnet der Browser nichts. */
function svgEl(tag, attrs, text) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined) continue;
    n.setAttribute(k, String(v));
  }
  if (text !== undefined) n.textContent = text;
  return n;
}

/** Die gewaehlten Slots — die Auswahl, sonst der eine im Inspektor.
 *
 * Dieselbe Frage wie `_auswahl_slots()` in der Bruecke, und sie muss dieselbe
 * Antwort geben: was man ziehen kann, ist genau das, worauf „loeschen" und
 * „Groesse angleichen" wirken. Die Seite beantwortet sie nur fuer die Geste
 * (was liegt unter dem Zeiger), gerechnet wird weiterhin drueben. */
function scanGewaehlteSlots() {
  if (!SC) return [];
  const namen = SC.auswahl.length ? SC.auswahl
    : (SC.wahl.art === "slot" && SC.wahl.name ? [SC.wahl.name] : []);
  return SC.slots.filter((s) => namen.includes(s.name));
}

function scanInSlot(slot, stelle) {
  return stelle[0] >= slot.region[0] && stelle[0] <= slot.region[2]
      && stelle[1] >= slot.region[1] && stelle[1] <= slot.region[3];
}

/** Holt den gewaehlten Slot in die Sichtbarkeit der Buehne.
 *
 * **Liste und Bild waren zwei getrennte Welten.** Einen Slot in der Liste
 * anzuklicken markierte ihn im Bild — nur sah man das nicht, wenn er gerade
 * ausserhalb lag. Bei 45 Slots auf 1:1 ist das der Normalfall, und man sucht
 * die weisse Markierung, statt zu arbeiten.
 *
 * Gescrollt wird NUR, wenn er wirklich draussen liegt, und nur beim Wechsel der
 * Auswahl (`scanGezeigt`): eine Buehne, die bei jedem Neuzeichnen springt,
 * nimmt einem die Stelle weg, die man gerade ansieht. */
function scanZeigeGewaehlten() {
  if (!SC || !SC.foto || SC.wahl.art !== "slot") { scanGezeigt = ""; return; }
  const name = SC.wahl.name;
  if (!name || name === scanGezeigt) return;
  scanGezeigt = name;
  const slot = SC.slots.find((s) => s.name === name);
  if (!slot) return;
  const buehne = $("scan-buehne");
  const [bx1, by1] = scanZuBild(slot.region[0], slot.region[1]);
  const [bx2, by2] = scanZuBild(slot.region[2], slot.region[3]);
  // Bild-Pixel -> Pixel auf der Buehne. Der Rand haelt den Slot von der Kante
  // weg: dicht am Rand sieht man ihn zwar, aber nicht, was um ihn herum liegt.
  const rand = 60;
  const l = bx1 * scanZoom, o = by1 * scanZoom;
  const r = bx2 * scanZoom, u = by2 * scanZoom;
  if (l < buehne.scrollLeft + rand || r > buehne.scrollLeft + buehne.clientWidth - rand)
    buehne.scrollLeft = Math.max(0, (l + r) / 2 - buehne.clientWidth / 2);
  if (o < buehne.scrollTop + rand || u > buehne.scrollTop + buehne.clientHeight - rand)
    buehne.scrollTop = Math.max(0, (o + u) / 2 - buehne.clientHeight / 2);
}

function scanStelleAusEvent(e) {
  const rand = $("scan-overlay").getBoundingClientRect();
  if (!rand.width || !rand.height || !SC || !SC.foto) return null;
  const bx = (e.clientX - rand.left) / rand.width * SC.foto.breite;
  const by = (e.clientY - rand.top) / rand.height * SC.foto.hoehe;
  return scanZuSchirm(bx, by);
}

/* --------------------------------------------------------------- Inspektor */

function scanInspektor() {
  const ziel = $("scan-insp");
  ziel.replaceChildren();
  if (SC.review) return scanReview(ziel);
  const kopf = el("div", {class: "abschnitt"},
    el("div", {class: "reihe"},
      el("span", {class: "ueberschrift wachse"},
         SC.dirty ? "NICHT GESPEICHERT"
                  : (scanItemsRechts() ? "ITEMS" : "SCANS · SLOTS · ITEMS")),
      SC.dirty ? el("span", {class: "punkt-offen"}) : null),
    // **Der Hauptprozess schreibt dieselben Dateien.** Ein Lauf mit
    // Auto-Lernen legt Items an und speichert sie; ohne diesen Hinweis sucht
    // man sie hier vergeblich und haelt es fuer einen Fehler beim Lernen.
    // Bei ungespeicherten Änderungen zwei Knöpfe statt einer Rückfrage: was
    // passiert, steht dann VOR dem Klick da und nicht danach.
    SC.fremd ? el("div", {class: "fremdhinweis"},
      el("span", {}, "Auf Platte hat sich etwas geändert — vermutlich hat ein "
        + "Lauf Items dazugelernt."),
      el("div", {class: "reihe"},
        SC.dirty ? el("button", {class: "btn haupt", onclick: async () => {
          await rufScan("scan_speichern");
          await rufScan("scan_neu_laden", {verwerfen: true});
        }}, "Speichern & neu laden") : null,
        el("button", {class: "btn", onclick: () => rufScan("scan_neu_laden",
                                                           {verwerfen: true})},
           SC.dirty ? "Änderungen verwerfen & neu laden" : "Neu laden"))) : null,
    el("button", {class: "btn haupt", onclick: () => rufScan("scan_speichern")},
       "Speichern"),
    el("div", {class: "reihe"},
      scanArt === "item"
        // **Derselbe Befehl heisst ueberall gleich.** Er stand hier als „Items
        // erkennen" und im Assistenten als „Erkennung testen" — zwei Namen fuer
        // einen Knopf, und man probiert beide aus, weil man annimmt, sie taeten
        // Verschiedenes.
        ? el("button", {class: "btn wachse", disabled: !fotoDa() || !SC.slots.length,
                        title: "Hält jeden Slot gegen die Item-Profile und schreibt "
                               + "das Ergebnis an Bild und Item-Liste",
                        onclick: () => rufScan("scan_erkennen")}, "Items erkennen")
        : el("button", {class: "btn wachse", disabled: !fotoDa() || !erkScan(),
                        title: "Erkennen, anzeigen — die Aktion wird NICHT ausgeführt",
                        onclick: () => erkTesten()},
             scanArt === "boss" ? "Boss-Scan testen" : "Icon-Scan testen"),
      // **Der Knopf NENNT, was er zurücknimmt.** Ein „Rückgängig" ohne Angabe
      // drückt man entweder gar nicht (weil man nicht weiss, was passiert) oder
      // einmal zu oft. Die Beschreibung kommt aus der Brücke — dort weiss man,
      // was der Schritt war.
      // **Der Knopf traegt den Namen des Schritts** — und der kann lang sein
      // („'Mission nicht machbar': Klickpunkt"). Ohne Kuerzung schiebt er den
      // Nachbarn aus der Zeile, und ein Knopf, den man nicht erreicht, ist
      // schlimmer als eine abgeschnittene Beschriftung.
      el("button", {class: "btn scan-undo", disabled: !SC.undo.tiefe,
                    title: SC.undo.tiefe
                      ? "STRG+Z — nimmt zurück: " + SC.undo.was
                        + " (" + SC.undo.tiefe + " Schritte gemerkt)"
                      : "Nichts zum Rückgängigmachen",
                    onclick: () => rufScan("scan_rueckgaengig")},
         SC.undo.tiefe ? "↶ " + SC.undo.was : "↶ Rückgängig")));
  ziel.appendChild(kopf);

  const rumpf = el("div", {class: "abschnitt wachsend"});
  // **Die Items sind hier die Arbeit, nicht ein einzelnes Ding.** Sechzig
  // Masken brauchen Breite, und die hat diese Spalte; der Inspektor hatte
  // seit dem Umbau ohnehin fast nichts mehr zu zeigen. Was zum GEWAEHLTEN
  // Item gehoert, steht in seiner Maske — nicht daneben.
  if (scanItemsRechts()) {
    const filter = el("div", {class: "reihe", style: "margin-bottom:8px"});
    scanFilterzeile(filter, "items");
    if (filter.childNodes.length) rumpf.appendChild(filter);
    const liste = el("div", {class: "spalte", style: "gap:3px"});
    scanListeItems(liste);
    rumpf.appendChild(liste);
  } else if (scanArt !== "item") erkInspektor(rumpf);
  else if (SC.wahl.art === "slot") scanInspSlot(rumpf);
  else if (SC.wahl.art === "item") scanInspItem(rumpf);
  else if (SC.wahl.art === "scan") scanInspScan(rumpf);
  if (!rumpf.childNodes.length) {
    rumpf.appendChild(el("p", {class: "hinweis"},
      "Nichts gewählt. Links eine Zeile anklicken — oder im Bild einen Slot."));
  }
  ziel.appendChild(rumpf);
}

function scanReview(ziel) {
  const itemsId = "review-items";
  const bekannteNamen = new Set((SC.review.itemnamen || []).map(String));
  const kopf = el("div", {class: "abschnitt"},
    el("span", {class: "ueberschrift"}, "ITEMS VOR DER ÜBERNAHME PRÜFEN"),
    el("p", {class: "hinweis"},
      "Erkannte Items sind direkt angehakt. Häkchen = gehört zum aktuellen Scan. " +
      "Nimmst du es bei einem bereits enthaltenen Item weg, wird nur diese Zuordnung " +
      "entfernt; das Item und seine Bilder bleiben gelernt."));
  const vorhanden = allePrioritaeten();
  if (vorhanden) kopf.appendChild(vorhanden);
  const sammelKategorie = kategorieWahl("", scanReviewKategorienAktualisieren, {
    leer: "— Kategorie für alle ausgewählten —",
    platzhalter: "Kategorie für alle ausgewählten Items",
    schluessel: "review-sammel",
  });
  kopf.appendChild(el("div", {class: "scan-review-sammel"}, sammelKategorie,
    el("button", {class: "btn still", type: "button",
      onclick: () => scanReviewKategorieAufAuswahl(sammelKategorie)},
    "Auf ausgewählte anwenden")));
  ziel.appendChild(kopf);
  const liste = el("div", {class: "abschnitt wachsend scan-review"});
  for (const z of SC.review.zeilen) {
    const haken = el("input", {type: "checkbox", class: "scan-review-haken"});
    const standardAuswahl = !!z.ausgewaehlt;
    const vorhandenerName = String(z.vorhanden || "");
    let alsAnderes = false;
    let vorherigeAuswahl = standardAuswahl;
    haken.checked = standardAuswahl;
    haken.title = "Angehakt: im aktuellen Scan verwenden · abgehakt: auslassen oder entfernen";
    const name = el("input", {class: "scan-review-name",
      value: z.name, list: itemsId, autocomplete: "off",
      placeholder: "Item-Name", title: "Vorhandenes Item auswählen oder neuen Namen eingeben"});
    // Dasselbe Bedienelement wie in der Item-Maske: waehlen ist der Normalfall,
    // tippen die Ausnahme. Gerade hier entstehen die Kategorien, und gerade
    // hier tippt man sie sonst zwanzigmal — beim einundzwanzigsten Mal anders.
    const kat = kategorieWahl(z.kategorie || "", scanReviewKategorienAktualisieren,
      {klasse: "scan-review-kategorie", schluessel: "review:" + z.slot});
    const prio = el("input", {
      class: "scan-review-prio",
      type: "number", value: z.prioritaet ?? 1, min: 0, step: 1,
      title: "Kleinere Zahl gewinnt; 0 setzt das Item in seiner Kategorie nach vorn",
    });
    const status = el("span", {class: "klein mono"});
    const wechsel = vorhandenerName ? el("button", {
      class: "btn still scan-review-aktion", type: "button",
      title: "Nur verwenden, wenn die automatische Erkennung falsch war",
    }, "Als anderes Item lernen") : null;
    let zeile;
    const synchronisiere = () => {
      const bestehend = bekannteNamen.has(name.value.trim());
      const normalerTreffer = !!vorhandenerName && !alsAnderes;
      name.disabled = normalerTreffer;
      // Kategorie und Priorität des erkannten Profils sind direkt änderbar.
      // Wird ein anderer vorhandener Name gewählt, schützen wir dagegen dessen
      // Werte vor den leeren Standards der Aktion „Als anderes Item lernen“.
      kat.sperren(bestehend && !normalerTreffer);
      prio.disabled = bestehend && !normalerTreffer;
      zeile.dataset.alsAnderes = alsAnderes ? "true" : "false";
      zeile.classList.toggle("entfernen", !haken.checked && normalerTreffer && !!z.im_scan);
      zeile.classList.toggle("ueberspringen", !haken.checked &&
        (!normalerTreffer || !z.im_scan));
      if (!haken.checked) {
        status.textContent = z.slot + (normalerTreffer && z.im_scan
          ? " · „" + vorhandenerName + "“ · wird aus diesem Scan entfernt"
          : " · wird nicht übernommen");
      } else if (alsAnderes) {
        status.textContent = z.slot + (bestehend
          ? " · vorhandenes „" + name.value.trim() + "“ gewählt · Vorlage ergänzen"
          : " · wird als neues Item gelernt");
      } else if (z.variante) {
        status.textContent = z.slot + " · „" + vorhandenerName +
          "“ erkannt · neue Vorlage für diese Slot-Größe · " +
          (z.im_scan ? "bleibt im Scan" : "wird zum Scan hinzugefügt");
      } else if (z.duplikat && z.im_scan) {
        status.textContent = z.slot + " · „" + vorhandenerName +
          "“ erkannt · bleibt im Scan";
      } else if (z.duplikat && z.kann_hinzufuegen) {
        status.textContent = z.slot + " · „" + vorhandenerName +
          "“ erkannt · wird zum Scan hinzugefügt";
      } else if (z.duplikat) {
        status.textContent = z.slot + " · „" + vorhandenerName + "“ · bereits gelernt";
      } else {
        status.textContent = z.slot + (bestehend
          ? " · neue Vorlage für „" + name.value.trim() + "“" : " · neues Item");
      }
    };
    name.addEventListener("input", synchronisiere);
    zeile = el("div", {class: "scan-review-zeile" +
        (z.variante ? " variante" : z.duplikat && z.kann_hinzufuegen
          ? " duplikat zuordnen" : z.duplikat ? " duplikat fertig" : ""),
      "data-slot": z.slot, "data-vorhanden": vorhandenerName,
      "data-als-anderes": "false"}, haken,
      z.bild ? el("img", {src: z.bild}) : el("span", {}),
      el("div", {class: "felder"},
        status,
        name, el("div", {class: "scan-review-sortierung"}, kat,
          el("label", {class: "scan-review-prio"}, el("span", {}, "Priorität"), prio)),
        wechsel));
    zeile._reviewSynchronisieren = synchronisiere;
    const gleicheAuswahlSetzen = () => {
      if (!vorhandenerName || alsAnderes) {
        synchronisiere();
        return;
      }
      // Dasselbe Item kann in mehreren Slots liegen. Ein Häkchen steht für die
      // Item-Zuordnung, deshalb bewegen sich alle Vorkommen gemeinsam.
      for (const andere of document.querySelectorAll(".scan-review-zeile")) {
        if (andere.dataset.vorhanden !== vorhandenerName ||
            andere.dataset.alsAnderes === "true") continue;
        const andererHaken = andere.querySelector('input[type="checkbox"]');
        if (andererHaken) andererHaken.checked = haken.checked;
        if (andere._reviewSynchronisieren) andere._reviewSynchronisieren();
      }
    };
    haken.addEventListener("change", gleicheAuswahlSetzen);
    if (wechsel) wechsel.addEventListener("click", () => {
      alsAnderes = !alsAnderes;
      if (alsAnderes) {
        vorherigeAuswahl = haken.checked;
        name.value = z.neu_name || "Item";
        kat.value = "";
        prio.value = 1;
        haken.checked = true;
        wechsel.textContent = "Treffer „" + vorhandenerName + "“ verwenden";
      } else {
        name.value = z.name;
        kat.value = z.kategorie || "";
        prio.value = z.prioritaet ?? 1;
        haken.checked = vorherigeAuswahl;
        wechsel.textContent = "Als anderes Item lernen";
      }
      zeile.classList.toggle("anderes", alsAnderes);
      synchronisiere();
      if (!alsAnderes) gleicheAuswahlSetzen();
      scanReviewKategorienAktualisieren();
    });
    synchronisiere();
    liste.appendChild(zeile);
  }
  liste.appendChild(el("datalist", {id: itemsId},
    [...bekannteNamen].map((name) => el("option", {value: name}))));
  liste.appendChild(el("div", {class: "reihe", style: "margin-top:8px"},
    el("button", {class: "btn", onclick: () => rufScan("scan_lernvorschau_abbrechen")}, "Abbrechen"),
    el("span", {class: "wachse"}),
    el("button", {class: "btn haupt", onclick: scanReviewUebernehmen}, "Auswahl anwenden")));
  ziel.appendChild(liste);
}

function scanReviewUebernehmen() {
  // **Gelesen wird ueber Klassen, nicht ueber Positionen.** Vorher wurden die
  // Felder einer Zeile durchnummeriert aus `querySelectorAll` gegriffen — wer
  // eines dazwischen einbaut (oder ein Textfeld durch eine Auswahlliste
  // ersetzt, wie es die Kategorie jetzt ist), verschiebt still alle folgenden.
  // Ein Import, der die Prioritaet als Kategorie liest, faellt niemandem auf.
  const zeilen = [...document.querySelectorAll(".scan-review-zeile")].map((n) => ({
    slot: n.dataset.slot,
    ausgewaehlt: n.querySelector(".scan-review-haken").checked,
    vorhanden: n.dataset.vorhanden || "",
    als_anders: n.dataset.alsAnderes === "true",
    name: n.querySelector(".scan-review-name").value.trim(),
    kategorie: n.querySelector(".scan-review-kategorie").wert(),
    prioritaet: Number(n.querySelector(".scan-review-prio").value),
  }));
  rufScan("scan_lernvorschau_uebernehmen", {zeilen: zeilen});
}

function scanSlotAktuell() {
  return SC.slots.find((s) => s.name === SC.wahl.name) || null;
}

function scanInspSlot(ziel) {
  // Mehrere Slots gewaehlt: dann gibt es keine Einzelfelder zu zeigen (welchen
  // Namen truege das Feld?), sondern nur, was auf alle wirkt. Dieselbe Haltung
  // wie im Sequenz-Editor bei einer Mehrfachauswahl.
  if (SC.auswahl.length > 1) return scanInspAuswahl(ziel);
  const s = scanSlotAktuell();
  if (!s) return;
  const setze = (feld, wert) => rufScan("scan_slot_setzen", {name: s.name, feld: feld, wert: wert});

  ziel.appendChild(ueberschrift("SLOT",
    "Ein Slot ist eine Fläche, die gescannt wird, plus die Stelle, auf die " +
    "geklickt wird, wenn dort etwas Passendes liegt.", "slot"));
  ziel.appendChild(feld("Name", s.name, (v) => setze("name", v)));
  ziel.appendChild(el("div", {class: "reihe", style: "margin-top:8px"},
    el("button", {class: "btn still",
      onclick: () => rufScan("scan_modus_setzen", {modus: "klick"})},
      "Klickpunkt im Bild setzen"),
    el("button", {class: "btn still", disabled: !fotoDa(),
      onclick: () => rufScan("scan_modus_setzen", {modus: "messen"})},
      "Hintergrund messen")));

  const erweitert = el("details", {class: "scan-erweitert"},
    el("summary", {}, "Erweiterte Einstellungen · Koordinaten und Hintergrund"));

  erweitert.appendChild(ueberschrift("FLÄCHE",
    "In Bildschirm-Koordinaten. Bequemer: Modus „Neuer Slot“ und zwei Ecken " +
    "im Bild anklicken.", "flaeche"));
  erweitert.appendChild(el("div", {class: "gitter2"},
    zahlfeld("Links", s.region[0], (v) => setze("x1", v)),
    zahlfeld("Oben", s.region[1], (v) => setze("y1", v)),
    zahlfeld("Rechts", s.region[2], (v) => setze("x2", v)),
    zahlfeld("Unten", s.region[3], (v) => setze("y2", v))));
  erweitert.appendChild(el("p", {class: "hinweis"}, s.breite + " × " + s.hoehe + " px"));

  erweitert.appendChild(ueberschrift("KLICKPUNKT",
    "Wohin geklickt wird, wenn in diesem Slot ein gesuchtes Item liegt.", "klickpunkt"));
  erweitert.appendChild(el("div", {class: "gitter2"},
    zahlfeld("X", s.klick[0], (v) => setze("kx", v)),
    zahlfeld("Y", s.klick[1], (v) => setze("ky", v))));

  erweitert.appendChild(ueberschrift("HINTERGRUND",
    "Die Farbe des leeren Slots. Sie wird beim Item-Lernen abgezogen, damit " +
    "nicht der Rahmen als Merkmal gelernt wird.", "hintergrund"));
  erweitert.appendChild(farbfeld("Farbe", s.farbe, (v) => setze("farbe", v)));
  ziel.appendChild(erweitert);

  ziel.appendChild(el("div", {class: "reihe", style: "margin-top:14px"},
    el("button", {class: "btn", disabled: !fotoDa(),
                  onclick: () => rufScan("scan_item_lernen", {slot: s.name})},
       "Item lernen"),
    el("button", {class: "btn", onclick: () => rufScan("scan_slot_doppeln")}, "daneben"),
    el("span", {class: "wachse"}),
    el("button", {class: "btn gefahr", onclick: () => rufScan("scan_slot_loeschen")},
       "löschen")));
  if (fotoDa()) {
    // „Alle" heisst: alle Slots des offenen Scans, nicht des ganzen Bestands
    // (`_scan_slots()` in scans.py). Das steht im Knopf, weil es vorher
    // stillschweigend anders war — und die Meldung danach ratlos machte.
    ziel.appendChild(el("button", {class: "btn still", style: "margin-top:6px",
      title: SC.offen ? "Alle Slots aus „" + SC.offen + "“ — nicht der ganze Bestand"
                      : "Alle Slots im Bestand (kein Scan offen)",
      onclick: () => rufScan("scan_lernvorschau", {scope: "alle"})},
      SC.offen ? "Items dieses Scans prüfen & lernen" : "alle Items prüfen & lernen"));
  }
  if (s.treffer) {
    ziel.appendChild(el("p", {class: "hinweis", style: "margin-top:10px"},
      s.treffer.name ? "Zuletzt erkannt: " + s.treffer.name
                     : "Zuletzt: " + (s.treffer.grund || "nichts erkannt")));
    // Der Treffer ist ein Vorschlag, keine Festlegung. Stimmt er nicht, lernt
    // man aus demselben Slot ein zweites Item („Item lernen" oben); gehoert er
    // nur noch nicht zum Scan, ist es ein Klick.
    if (s.treffer.fremd) {
      ziel.appendChild(el("button", {class: "btn still",
        onclick: () => rufScan("scan_mitglied", {art: "item", name: s.treffer.name})},
        "„" + s.treffer.name + "“ zu diesem Scan dazunehmen"));
    }
    if (s.treffer.name) {
      ziel.appendChild(el("p", {class: "hinweis"},
        "Stimmt nicht? „Item lernen“ legt aus diesem Slot ein weiteres Item an."));
    }
  }
}

// Welche Haken-Listen gerade ihren ganzen Bestand zeigen. Reiner
// Oberflaechenzustand: er aendert nichts am Scan, also gehoert er nicht in die
// Momentaufnahme.
let hakenAlleZeigen = {slot: false, item: false};

/** Eine Haken-Liste: standardmaessig nur, was zu diesem Scan gehoert.
 *
 * **Ein neuer Scan faengt leer an.** Vorher standen dort alle 56 Slots und alle
 * 24 Items des gesamten Bestands — die eines anderen Spiels also mit. Slots sind
 * Bildschirm-Koordinaten und damit ohnehin nur fuer ihr eigenes Spiel zu
 * gebrauchen; sie in einem fremden Scan anzubieten ist reines Rauschen.
 *
 * **Items sind der Sonderfall, und zwar der wichtige.** Dasselbe Item kann in
 * mehreren Spielen vorkommen, und es zweimal zu lernen ist genau das, was man
 * vermeiden will. Deshalb erscheint ein Item auch dann, wenn es GERADE IN EINEM
 * SLOT ERKANNT wird — dann steht es da, bevor man auf die Idee kommt, es neu zu
 * lernen. Ein Haken genuegt.
 *
 * Der Rest des Bestands ist einen Klick entfernt, nicht weg. */
function hakenListe(ziel, titel, hilfe, schluessel, c, art, bestand, drin, leerText) {
  // `erkannt` kommt aus der Bruecke (`_erkannte_items()`), damit die Regel
  // „gehoert dazu ODER wird gerade gesehen" an EINER Stelle steht und messbar
  // ist. Slots tragen das Merkmal nicht — sie sind Bildschirm-Koordinaten und
  // gehoeren immer genau einem Spiel.
  const alles = hakenAlleZeigen[art];
  const sichtbar = alles ? bestand
    : bestand.filter((e) => drin.includes(e.name) || e.erkannt);
  ziel.appendChild(hakenKopf(titel, hilfe, schluessel, c.name, art,
                             bestand.length, drin.length));
  if (sichtbar.length) {
    ziel.appendChild(el("div", {class: "scan-haken"}, sichtbar.map((e) =>
      hakenZeile(e.name, drin.includes(e.name),
                 () => rufScan("scan_mitglied", {scan: c.name, art: art, name: e.name}),
                 art, !drin.includes(e.name) && !!e.erkannt))));
  } else if (!alles) {
    ziel.appendChild(el("p", {class: "hinweis"}, leerText));
  }
  const rest = bestand.length - sichtbar.length;
  if (rest > 0 || alles) {
    ziel.appendChild(el("button", {class: "btn still",
      onclick: () => { hakenAlleZeigen[art] = !alles; zeichneScans(); }},
      alles ? "nur die aus diesem Scan" : rest + " weitere im Bestand zeigen"));
  }
}

/** Eine Zeile der Haken-Liste: Schieber = gehoert dazu, Name = bearbeiten.
 *
 * **Zwei verschiedene Fragen brauchen zwei Bedienelemente.** Vorher war die
 * ganze Zeile ein Schalter, und um ein Item zu BEARBEITEN musste man es links in
 * der Liste suchen — die zeigt aber standardmaessig nur Scan-Mitglieder. Wer ein
 * gelerntes Item umbenennen wollte, das (richtigerweise) noch zu keinem Scan
 * gehoert, musste es also erst aufnehmen. Man musste etwas AENDERN, um es
 * ansehen zu koennen.
 *
 * Jetzt schaltet der Schieber die Zugehoerigkeit, und ein Klick auf den Namen
 * waehlt den Eintrag aus — der Inspektor zeigt danach ihn. */
function hakenZeile(name, an, umschalten, art, erkannt) {
  const s = schalter("", an, umschalten);
  s.classList.add("haken-nur-schalter");
  return el("div", {class: "haken-zeile"}, s,
    el("button", {class: "haken-name" + (erkannt ? " erkannt" : ""),
                  // Erkannt, aber noch nicht dabei: dieselbe Farbe wie im Bild
                  // (tuerkis), damit man die beiden Stellen zusammenbringt.
                  title: erkannt ? "wird gerade in einem Slot erkannt — Haken "
                                   + "setzen statt neu lernen" : "bearbeiten",
                  onclick: () => rufScan("scan_waehlen", {art: art, name: name})},
       name));
}

/** Ueberschrift einer Haken-Liste, mit Stand und einem „alle"-Schieber.
 *
 * **56 Schalter einzeln zu setzen ist keine Bedienung.** Ein Scan umfasst fast
 * immer ALLES seines Spiels; die Ausnahme klickt man danach einzeln weg — nicht
 * umgekehrt.
 *
 * Derselbe Schieber wie die Eintraege darunter, damit man ihn nicht als etwas
 * anderes lesen muss. Drei Stellungen statt zwei: bei 23 von 56 steht er in der
 * MITTE (`indeterminate`) — „aus" waere dort schlicht gelogen, und man wuesste
 * nicht, was ein Klick tut. Aus der Mitte heraus schaltet er ein; ganz an
 * schaltet er alles aus. */
function hakenKopf(titel, hilfe, schluessel, scan, art, gesamt, drin) {
  const gemischt = drin > 0 && drin < gesamt;
  const alle = schalter("alle", drin === gesamt && gesamt > 0,
    (v) => rufScan("scan_alle", {scan: scan, art: art, wert: v}), gemischt);
  alle.classList.add("haken-alle");
  // **Dasselbe Raster wie die Liste darunter.** Rechts angeklebt stand der
  // Schieber ueber nichts — die Eintraege stehen zweispaltig und linksbuendig,
  // er sass allein am rechten Rand. In derselben Spalte steht er genau ueber
  // dem ersten Eintrag, und die Zahl nimmt die zweite Spalte.
  return el("div", {class: "spalte", style: "gap:6px"},
    el("span", {class: "ueberschrift mitinfo"}, titel, info(hilfe, schluessel)),
    el("div", {class: "scan-haken haken-kopf"},
      alle,
      el("span", {class: "klein mono haken-stand"}, drin + "/" + gesamt)));
}

/** Mehrere Slots gewaehlt — nur, was auf alle wirkt.
 *
 * **Eine Mehrfachauswahl konnte bis hierher genau eines: geloescht werden.**
 * Damit war das Rechteck ein Werkzeug zum Wegraeumen und sonst nichts —
 * obwohl gerade die Handgriffe nach dem Finden fast immer viele Slots auf
 * einmal betreffen (die Reihe sitzt drei Pixel zu hoch, die Haelfte gehoert
 * nicht in diesen Scan, aus den fuenf orangen soll gelernt werden). */
function scanInspAuswahl(ziel) {
  ziel.appendChild(ueberschrift("AUSWAHL",
    "Mit einem Rechteck im Bild gewählt (im Modus „Auswählen“ neben einen Slot " +
    "klicken). STRG-Klick nimmt einzelne dazu oder heraus.", "auswahl"));
  ziel.appendChild(el("p", {class: "hinweis"}, SC.auswahl.length + " Slots gewählt"));
  // Die Namen stehen da, nicht nur die Zahl: was man loescht, soll man vorher
  // lesen koennen. Bei dreissig wird die Liste lang - dafuer scrollt sie.
  ziel.appendChild(el("div", {class: "spalte", style: "gap:2px;max-height:160px;"
    + "overflow-y:auto;font-family:var(--mono);font-size:11px;color:var(--muted)"},
    ...SC.auswahl.map((n) => el("span", {}, n))));

  ziel.appendChild(ueberschrift("LAGE UND GRÖSSE",
    "Wirkt auf alle Gewählten zugleich. Verschieben nimmt den Klickpunkt mit; " +
    "Angleichen zieht alle auf die mittlere Grösse, um ihre Mitte herum.",
    "auswahl-lage"));
  ziel.appendChild(el("p", {class: "hinweis"},
    "Verschieben: im Bild ziehen, oder Pfeiltasten (SHIFT = 10 px)."));
  ziel.appendChild(el("button", {class: "btn breit",
    onclick: () => rufScan("scan_groesse_angleichen")}, "Grösse angleichen"));

  ziel.appendChild(ueberschrift("HINTERGRUND UND ITEMS",
    "Gemessen wird jeder Slot an sich selbst — eine gemeinsame Farbe für alle " +
    "wäre an jedem einzelnen ein bisschen falsch.", "auswahl-lernen"));
  ziel.appendChild(el("button", {class: "btn breit", disabled: !fotoDa(),
    onclick: () => rufScan("scan_auswahl_farbe")}, "Hintergrund neu messen"));
  ziel.appendChild(el("button", {class: "btn breit", disabled: !fotoDa(),
    title: "Aus jedem gewählten Slot ein Item — Doppelte werden übersprungen",
    onclick: () => rufScan("scan_lernvorschau", {scope: "auswahl"})},
    SC.auswahl.length + " Items prüfen & lernen"));

  // Zwischen „einer" (Haekchen) und „alle" (Schieber im Kopf) lag nichts —
  // und genau dazwischen liegt der Alltag.
  if (SC.offen) {
    ziel.appendChild(ueberschrift("SCAN „" + SC.offen + "“",
      "Nimmt die gewählten Slots in den offenen Scan oder heraus.", "auswahl-scan"));
    ziel.appendChild(el("div", {class: "reihe"},
      el("button", {class: "btn wachse",
        onclick: () => rufScan("scan_auswahl_mitglied", {wert: true})}, "dazu"),
      el("button", {class: "btn wachse",
        onclick: () => rufScan("scan_auswahl_mitglied", {wert: false})}, "heraus")));
  }

  ziel.appendChild(el("div", {class: "reihe", style: "margin-top:14px"},
    el("button", {class: "btn", onclick: () => rufScan("scan_abbrechen")},
       "Auswahl aufheben"),
    el("span", {class: "wachse"}),
    el("button", {class: "btn gefahr", onclick: () => rufScan("scan_slot_loeschen")},
       SC.auswahl.length + " löschen")));
  // Loeschen ist hier die einzige Aktion, die etwas wegnimmt — und seit es ein
  // Rueckgaengig gibt, ist sie es nicht mehr endgueltig. Das gehoert dazu:
  // sonst traut man sich an die Sammel-Aktionen nicht heran.
  ziel.appendChild(el("p", {class: "hinweis"},
    "Alles hier lässt sich mit STRG+Z zurücknehmen."));
}

function scanInspItem(ziel) {
  const i = SC.items.find((x) => x.name === SC.wahl.name);
  if (!i) return;
  // Der Weg hierher bleibt fuer den Fall, dass ein Item gewaehlt ist, waehrend
  // eine andere Liste offen steht — dann gibt es keine Maske, in der die
  // Einstellungen stehen koennten.
  ziel.appendChild(ueberschrift("ITEM",
    "Ein Item wird über sein Template (Bildvergleich) und/oder seine " +
    "Marker-Farben erkannt. Ohne beides wird es nie gefunden.", "item"));
  ziel.appendChild(el("div", {class: "feld-still"}, i.name,
    el("span", {class: "mono"}, (i.kategorie || "ohne Kategorie") + " · P" + i.prioritaet)));
  ziel.appendChild(el("p", {class: "hinweis"},
    "Name, Kategorie und Priorität stehen im Reiter „Items“ an der Maske des "
    + "Items — dort lassen sie sich für sechzig Items der Reihe nach tippen."));
  scanItemDetails(ziel, i);
}

/** Was man an einem Item selten ändert: Vorlagen, Marker, Konfidenz, Löschen.
 *
 * **Steht IN der Maske des gewählten Items**, nicht daneben: sonst sieht man
 * beim Arbeiten an einem Ding zwischen zwei Orten hin und her, und die Maske
 * trägt seine Identität ohnehin schon. Dieselbe Regel wie „was dem Punkt
 * gehört, steht beim Punkt" im Sequenz-Editor. */
function scanItemDetails(ziel, i) {
  const setze = (feld, wert) => rufScan("scan_item_setzen", {name: i.name, feld: feld, wert: wert});
  const bild = scanVorschauen.get(i.name);
  if (bild) ziel.appendChild(el("img", {class: "scan-gross", src: bild}));
  if ((i.erkannt_in || []).length) {
    ziel.appendChild(el("p", {class: "hinweis", style: "color:var(--slot-ok)"},
      "Gerade erkannt in: " + i.erkannt_in.join(", ")));
  }
  ziel.appendChild(prioritaetsUebersicht(i.kategorie, i.name));
  const erweitert = el("details", {class: "scan-erweitert"},
    el("summary", {}, "Erweiterte Erkennungseinstellungen"));
  erweitert.appendChild(zahlfeld("Konfidenz", i.konfidenz, (v) => setze("konfidenz", v),
      {min: 0, max: 1, step: "any"},
      "Wie gut das Template passen muss (0–1).", "konf"));
  erweitert.appendChild(el("p", {class: "hinweis"},
    (i.vorlagengroessen || []).length
      ? "Gelernte Slot-Größen: " + i.vorlagengroessen.map((g) => g[0] + "×" + g[1]).join(", ")
      : "Keine Bildvorlage — nur Marker-Farben."));
  if ((i.vorlagen || []).length) {
    erweitert.appendChild(el("p", {class: "hinweis mono"},
      "Vorlagen: " + i.vorlagen.join(", ")));
  }
  if ((i.fehlende_scan_groessen || []).length) {
    erweitert.appendChild(el("p", {class: "hinweis", style: "color:var(--accent)"},
      "Für diesen Scan noch nicht gelernt: " +
      i.fehlende_scan_groessen.map((g) => g[0] + "×" + g[1]).join(", ") +
      ". Beim Lernen diesen Item-Namen auswählen, um die Vorlage zu ergänzen."));
  }
  if (i.marker.length) {
    erweitert.appendChild(ueberschrift("MARKER-FARBEN",
      "Die häufigsten Farben im gelernten Ausschnitt, ohne den Slot-Hintergrund.",
      "marker"));
    erweitert.appendChild(el("div", {class: "scan-marker"},
      i.marker.map((c) => el("span", {style: "background:" + c, title: c}))));
  }
  ziel.appendChild(erweitert);
  if (i.stumm) {
    ziel.appendChild(el("p", {class: "hinweis", style: "color:var(--err)"},
      "Weder Template noch Marker — dieses Item wird nie erkannt."));
  }
  ziel.appendChild(el("button", {class: "btn gefahr", style: "margin-top:14px",
    onclick: () => rufScan("scan_item_loeschen")}, "Item löschen"));
}

function scanInspScan(ziel) {
  const c = SC.scans.find((x) => x.name === SC.wahl.name);
  if (!c) return;
  const setze = (feld, wert) => rufScan("scan_setzen", {name: c.name, feld: feld, wert: wert});
  const um = (art, name) => rufScan("scan_mitglied", {scan: c.name, art: art, name: name});
  if (SC.offen !== c.name) {
    ziel.appendChild(el("button", {class: "btn haupt",
      onclick: () => rufScan("scan_oeffnen", {name: c.name})}, "Diesen Scan öffnen"));
  }

  // **Der Name steht links, wo der Scan gewaehlt wird — hier nur noch, was man
  // an ihm EINSTELLT.** Zwei Felder fuer denselben Wert waren dieselbe Sache an
  // zwei Stellen, und man musste raten, welche die fuehrende ist; genau das wurde
  // beim Klick-Block im Sequenz-Editor schon einmal aufgeloest. Die Ueberschrift
  // nennt den Scan trotzdem: sonst weiss man nicht, woran diese Regler haengen.
  ziel.appendChild(ueberschrift("SCAN „" + c.name + "“",
    "Welche Slots nach welchen Items durchsucht werden. Ein Block vom Typ " +
    "ITEM-SCAN verweist per Name hierauf. Umbenennen: oben links.", "itemscan"));
  const erweitert = el("details", {class: "scan-erweitert"},
    el("summary", {}, "Erweiterte Scan-Einstellungen"));
  erweitert.appendChild(zahlfeld("Farb-Toleranz", c.toleranz, (v) => setze("toleranz", v),
    {min: 0, step: 1},
    "Wie weit eine Marker-Farbe abweichen darf, damit sie noch als gefunden gilt.",
    "toleranz"));
  erweitert.appendChild(schalter("Unbekanntes lernen", c.lernen, (v) => setze("lernen", v)));
  erweitert.appendChild(el("p", {class: "hinweis"},
    "Neue Slot-Inhalte werden als Items in die globale Liste gelernt — nie in " +
    "diesen Scan, damit sie nicht ungeprüft geklickt werden."));

  erweitert.appendChild(schalter("Slots rückwärts", c.reverse, (v) => setze("reverse", v)));
  erweitert.appendChild(el("p", {class: "hinweis"},
    "Von hinten nach vorn (4, 3, 2, 1). Sinnvoll, wenn das Spiel den Bestand " +
    "nach vorn aufrückt: dann verschiebt ein Klick nicht die noch nicht " +
    "besuchten Slots. Die Richtung gehört zum Inventar, deshalb steht sie hier " +
    "und nicht in den Einstellungen."));
  ziel.appendChild(erweitert);

  hakenListe(ziel, "SLOTS", "Welche Flächen dieser Scan ansieht.", "scanslots",
    c, "slot", SC.slots, c.slots,
    "Noch keine Slots in diesem Scan. Im Bild aufziehen oder finden.");
  hakenListe(ziel, "ITEMS", "Wonach gesucht wird. Erkannte tauchen von selbst "
    + "auf — damit du sie nicht ein zweites Mal lernst.", "scanitems",
    c, "item", SC.items, c.items,
    "Noch keine Items in diesem Scan. Aus einem Slot lernen — was schon im "
    + "Bestand ist und erkannt wird, steht hier von selbst.");

  if (c.fehlend.length) {
    ziel.appendChild(el("p", {class: "hinweis", style: "color:var(--err);margin-top:10px"},
      "Zeigt ins Leere: " + c.fehlend.join(", ") + ". Der Scan läuft mit dem Rest " +
      "weiter — lieber ein Slot weniger als ein toter Scan."));
  }
  ziel.appendChild(el("button", {class: "btn gefahr", style: "margin-top:14px",
    onclick: () => rufScan("scan_loeschen")}, "Scan löschen"));
}

/* ------------------------------------------- Ansicht: Bosse und Icon-Scans */

/* **Dieselbe Buehne, eine andere Frage.** Ein Boss-Scan ist ein Rechteck auf
 * einem Bild und eine Aktion dahinter; ein Icon-Scan ist dasselbe, nur ohne
 * Bosse-Liste. Beide lagen bisher in Konsolen-Editoren, die man fuer JEDE
 * Aenderung von vorn durchklicken musste — auch fuer eine Konfidenz.
 *
 * Welche Art offen ist, ist reiner Oberflaechenzustand wie `ansicht` und
 * `scanListe`: er steht nicht in der Momentaufnahme und nicht in der Bruecke,
 * denn er aendert nichts an den Daten. Die Bruecke bekommt bei jedem Befehl
 * gesagt, worauf er wirkt (`{art: "boss"}`) — eine vierte Wahrheit ueber
 * "was ist gerade gemeint" waere eine zu viel. */
let scanArt = "item";
/* Welcher Assistent-Schritt der Erkennungs-Arten offen ist. Eigene Variable
 * neben `scanAssistentSchritt`: die Arten haben verschieden viele Schritte, und
 * ein gemeinsamer Zaehler stuende beim Umschalten auf einem, den es nicht gibt. */
let scanErkSchritt = null;

const SCAN_ARTEN = ["item", "boss", "icon"];

/* **Welche Bruecken-Methode zu welcher Art gehoert — als Tabelle.**
 *
 * Boss und Icon beantworten dieselben Fragen mit anderen Methoden ("oeffne den
 * Scan", "setze ein Feld", "teste"). Als Ternaeroperator an einem halben Dutzend
 * Aufrufstellen verteilt waeren die Namen sechsmal da — und der Test „jeder
 * Aufruf der Seite passt zur Bruecke" faende keinen davon: er sucht nach einem
 * Methodennamen direkt hinter der oeffnenden Klammer eines Aufrufs, und ein
 * Ternaeroperator steht genau dort. Hier stehen sie einmal und sind messbar
 * (`tools/tests/studio_erkennung.py` liest diese Tabelle). */
const ERK_BEFEHL = {
  boss: {oeffnen: "boss_scan_oeffnen", neu: "boss_scan_neu",
         scan_feld: "boss_scan_setzen", feld: "boss_setzen",
         loeschen: "boss_scan_loeschen", testen: "boss_testen"},
  icon: {oeffnen: "icon_scan_oeffnen", neu: "icon_scan_neu",
         scan_feld: "icon_setzen", feld: "icon_setzen",
         loeschen: "icon_scan_loeschen", testen: "icon_testen"},
};

/** Der Befehlsname fuer die offene Art. */
function erkBefehl(schluessel) {
  return (ERK_BEFEHL[scanArt] || ERK_BEFEHL.boss)[schluessel];
}

/** Der offene Boss- bzw. Icon-Scan — oder null. */
function erkScan() {
  if (!SC) return null;
  if (scanArt === "boss") return SC.boss_scans.find((c) => c.name === SC.boss.offen) || null;
  if (scanArt === "icon") return SC.icon_scans.find((c) => c.name === SC.icon.offen) || null;
  return null;
}

/** Die Bosse, die dieser Scan sieht: seine eigenen plus die Bibliothek.
 *
 * Genau diese Liste sieht auch der Lauf (`execute_boss_scan` merged lokal +
 * global, lokale gewinnen bei Namensgleichheit). Nur die lokalen zu zeigen
 * hiesse, die Haelfte der Erkennung zu verschweigen — und man sucht dann, warum
 * ein Boss erkannt wird, der gar nicht in der Liste steht. */
function erkBosse() {
  const c = erkScan();
  const lokal = c ? c.bosse : [];
  const namen = new Set(lokal.map((b) => b.name));
  return lokal.concat(SC.global_bosses.filter((b) => !namen.has(b.name)));
}

/** Der gewaehlte Boss — der eine, den die rechte Spalte bearbeitet. */
function erkBoss() {
  if (!SC || scanArt !== "boss" || !SC.boss.wahl) return null;
  const liste = SC.boss.wahl_global ? SC.global_bosses : ((erkScan() || {}).bosse || []);
  return liste.find((b) => b.name === SC.boss.wahl) || null;
}

/** Steht die Bibliothek statt eines Scans im Vordergrund? */
function erkBibliothek() { return scanArt === "boss" && scanListeAktiv() === "bibliothek"; }

function scanArtSetzen(art) {
  if (!SCAN_ARTEN.includes(art) || art === scanArt) return;
  scanArt = art;
  scanErkSchritt = null;
  // Eine andere Art ist ein anderer Zusammenhang: die Vorgabe gilt wieder.
  scanListe = null;
  // Ein Werkzeug der alten Art wuerde in der neuen etwas anderes tun.
  rufScan("scan_abbrechen");
}

/** Welche Bloecke der linken Spalte gelten — und wo die Aufnahme gerade haengt. */
function scanArtPflegen() {
  for (const k of document.querySelectorAll("[data-scan-art]"))
    k.classList.toggle("an", k.dataset.scanArt === scanArt);
  const item = scanArt === "item";
  $("ab-itemwahl").hidden = !item;
  $("ab-weg").hidden = !item;
  $("ab-modi").hidden = !item;
  $("ab-erk-wahl").hidden = item;
  $("ab-erk-weg").hidden = item;
  for (const knopf of document.querySelectorAll("[data-erk-tool]")) {
    knopf.hidden = item;
    knopf.disabled = !SC.pillow || !erkScan();
    knopf.classList.toggle("an", SC.modus === knopf.dataset.erkTool);
  }
  // **Die Aufnahme-Karte wandert, also muss sie auch zurueck.** Sie gehoert
  // allen drei Arten und existiert deshalb nur EINMAL im Dokument; blieb sie
  // beim Umschalten im versteckten Erkennungs-Block liegen, fehlte dem
  // Item-Assistenten sein erster Schritt — und mit ihm der einzige Weg zu
  // einem Screenshot.
  if (item) {
    const heim = $("scan-schritte");
    const karte = $("scan-assistent-1");
    if (karte.parentElement !== heim) heim.insertBefore(karte, heim.firstChild);
    return;
  }
  erkWahlZeichnen();
  erkSchritteZeichnen();
}

/* ----------------------------------------------------- Auswahl und Name */

/** Oben in der linken Spalte: welcher Scan, wie er heisst, ein neuer.
 *
 * **Der Name steht da, wo der Scan gewaehlt wird** — dieselbe Regel wie beim
 * Item-Scan und beim Klick-Block: was dem Ding gehoert, steht beim Ding; rechts
 * bleibt, was man daran einstellt. */
function erkWahlZeichnen() {
  const ziel = $("ab-erk-wahl");
  const boss = scanArt === "boss";
  const liste = boss ? SC.boss_scans : SC.icon_scans;
  const offen = erkScan();
  const kinder = [el("span", {class: "ueberschrift"}, boss ? "BOSS-SCAN" : "ICON-SCAN")];
  kinder.push(auswahl("", [{wert: "", text: liste.length
      ? "— keiner gewählt —" : (boss ? "— noch kein Boss-Scan —" : "— noch kein Icon-Scan —")}]
    .concat(liste.map((c) => ({wert: c.name, text: c.name}))),
    offen ? offen.name : "",
    (v) => rufScan(erkBefehl("oeffnen"), {name: v})));
  if (offen) {
    kinder.push(feld("Name", offen.name,
      (v) => rufScan(erkBefehl("scan_feld"),
                     {name: offen.name, feld: "name", wert: v})));
  }
  kinder.push(el("div", {class: "reihe"},
    el("button", {class: "btn still", onclick: () => {
      scanErkSchritt = 2;
      rufScan(erkBefehl("neu"));
    }}, boss ? "+ neuer Boss-Scan" : "+ neuer Icon-Scan"),
    el("span", {class: "wachse"}),
    el("span", {class: "klein mono"}, offen
      ? (boss ? erkBosse().length + " Bosse" : erkWieText(offen.erkennung))
      : liste.length + (liste.length === 1 ? " Scan" : " Scans"))));
  ziel.replaceChildren(...kinder);
}

/* ------------------------------------------------------------- Assistent */

/** Woran ein Scan erkennt — als Wort, nicht als Schluessel. */
function erkWieText(wie) {
  return {template: "per Vorlage", marker: "per Farben",
          keine: "ohne Erkennung"}[wie] || wie;
}

/** Eine Schrittkarte des Assistenten — dieselbe Gestalt wie beim Item-Scan. */
function erkKarte(nr, titel, stand, fertig, inhalt) {
  const offen = scanErkSchritt === nr;
  return el("div", {class: "scan-assistent-schritt" + (offen ? " offen" : "")
                           + (fertig ? " fertig" : "")},
    el("button", {class: "scan-assistent-kopf", onclick: () => {
      // Ein Schritt bleibt jederzeit wieder aufklappbar — er ist kein
      // Fortschrittsbalken, sondern ein Weg, den man auch rueckwaerts geht.
      scanErkSchritt = offen ? null : nr;
      zeichneScans();
    }},
      el("span", {class: "nr"}, fertig && !offen ? "✓" : String(nr)),
      el("span", {class: "wachse"}, el("b", {}, titel), el("small", {}, stand)),
      el("span", {class: "pfeil"}, "›")),
    el("div", {class: "scan-assistent-inhalt", hidden: !offen}, inhalt));
}

function erkSchritteZeichnen() {
  const ziel = $("ab-erk-weg");
  const boss = scanArt === "boss";
  const c = erkScan();
  // Erst alles bauen, dann umhaengen. **Die Aufnahme-Karte existiert genau
  // einmal im Dokument** — sie gehoert allen drei Arten, und sie zweimal zu
  // bauen waeren zwei Stellen, an denen eine Aenderung an der Aufnahme
  // vergessen werden kann. Genau deshalb darf sie erst wandern, wenn nichts
  // mehr schiefgehen kann: bricht der Aufbau vorher ab, haengt sie in einem
  // Baum, den niemand mehr sieht — und mit ihr der einzige Weg zu einem Bild.
  const weitere = [];
  if (c) {
    weitere.push(erkRegionSchritt(c));
    if (boss) {
      weitere.push(erkBosseSchritt(c), erkWegeSchritt(c), erkFallbackSchritt(c));
    } else {
      weitere.push(erkErkennungSchritt(c), erkAktionSchritt(c, "icon"));
    }
  }
  const schritte = el("div", {class: "scan-assistent"});
  const aufnahme = $("scan-assistent-1");
  aufnahme.classList.toggle("offen", scanErkSchritt === 1);
  aufnahme.classList.toggle("fertig", fotoDa());
  $("scan-schritt-1-nr").textContent = fotoDa() && scanErkSchritt !== 1 ? "✓" : "1";
  $("scan-schritt-1-inhalt").hidden = scanErkSchritt !== 1;
  schritte.append(aufnahme, ...weitere);

  if (!c) {
    ziel.replaceChildren(
      el("span", {class: "ueberschrift"}, boss ? "BOSS-SCAN EINRICHTEN" : "ICON-SCAN EINRICHTEN"),
      schritte,
      el("p", {class: "hinweis"}, "Oben einen Scan anlegen — danach stehen die "
        + "weiteren Schritte hier."));
    return;
  }
  const kinder = [el("span", {class: "ueberschrift"},
                     boss ? "BOSS-SCAN EINRICHTEN" : "ICON-SCAN EINRICHTEN")];
  // **Fehlende Voraussetzung blendet nichts aus, sondern erklaert sich.** Ohne
  // OpenCV ist die Template-Erkennung aus — Farb-Marker, OCR und LLM gehen
  // trotzdem. Amber, nicht rot: es ist ein Zustand, kein Defekt.
  if (!SC.opencv) {
    kinder.push(el("div", {class: "fremdhinweis"},
      el("span", {}, "OpenCV nicht installiert — Template-Erkennung ist aus. "
        + "Farb-Marker, OCR und LLM gehen trotzdem."),
      el("span", {class: "mono klein"}, "pip install opencv-python")));
  }
  kinder.push(schritte);
  ziel.replaceChildren(...kinder);
}

/** Schritt 2: die Region. Aufziehen ODER vier Zahlen — beides bleibt. */
function erkRegionSchritt(c) {
  const r = c.region;
  const gesetzt = (r[2] - r[0]) > 0 && (r[3] - r[1]) > 0
    && !(r[0] === 0 && r[1] === 0 && r[2] === 100 && r[3] === 100);
  const setze = (i, v) => {
    const neu = r.slice();
    neu[i] = Number(v) || 0;
    erkFeld("region", neu);
  };
  return erkKarte(2, "Region", gesetzt
    ? "(" + r[0] + "," + r[1] + ") → (" + r[2] + "," + r[3] + ")  ·  "
      + (r[2] - r[0]) + "×" + (r[3] - r[1])
    : "Noch nicht gesetzt", gesetzt, [
    el("p", {class: "hinweis"}, scanArt === "boss"
      ? "Der Bereich, in dem der Boss-Name bzw. sein Bild erscheint. Eng genug, "
        + "dass nichts Wechselndes mit hineinfällt."
      : "Eng um das Symbol herum. Was mit im Rechteck liegt, wird mitgelernt."),
    el("div", {class: "gitter2"},
      zahlfeld("Links", r[0], (v) => setze(0, v), {step: 1}),
      zahlfeld("Oben", r[1], (v) => setze(1, v), {step: 1}),
      zahlfeld("Rechts", r[2], (v) => setze(2, v), {step: 1}),
      zahlfeld("Unten", r[3], (v) => setze(3, v), {step: 1})),
    el("button", {class: "btn haupt scan-assistent-haupt", disabled: !fotoDa(),
      onclick: () => rufScan("region_modus", {art: scanArt, modus: "region"})},
      "Region im Bild aufziehen"),
  ]);
}

/** Schritt 3 (Boss): die Bosse dieses Scans. */
function erkBosseSchritt(c) {
  const lokal = c.bosse.length;
  const global = SC.global_bosses.length;
  return erkKarte(3, "Bosse", lokal || global
    ? lokal + " lokal · " + global + " global"
    : "Noch kein Boss · die Bibliothek ist leer", lokal > 0 || global > 0, [
    el("p", {class: "hinweis"}, "Jeder Boss hat eine eigene Erkennung und eine "
      + "eigene Aktion. Die Reihenfolge ist die Priorität: der erste Treffer gewinnt."),
    el("button", {class: "btn haupt scan-assistent-haupt",
      onclick: () => rufScan("boss_neu")}, "+ Boss anlegen"),
    el("button", {class: "btn still scan-assistent-haupt", disabled: !fotoDa()
        || !erkBosse().length,
      onclick: () => rufScan("boss_alle_testen")}, "Alle gegen dieses Bild halten"),
  ]);
}

/** Schritt 4 (Boss): OCR und LLM. */
function erkWegeSchritt(c) {
  const b = SC.bereit;
  const an = [c.use_ocr ? "OCR" : null, c.use_llm ? "LLM" : null].filter(Boolean);
  const lampe = !b.llm_stand ? "" : (b.llm_stand.erreichbar ? " an" : " aus");
  return erkKarte(4, "LLM & OCR", an.length ? an.join(" + ") + " aktiv" : "aus",
    an.length > 0, [
    el("span", {class: "ueberschrift"}, "OCR TEXTERKENNUNG"),
    schalter("OCR benutzen", c.use_ocr, (v) => erkFeld("use_ocr", v)),
    c.use_ocr ? segment([{wert: true, text: "als Fallback"}, {wert: false, text: "primär"}],
      c.ocr_fallback, (v) => erkFeld("ocr_fallback", v)) : null,
    // **Gefragt, nicht mitgeliefert.** `import easyocr` zieht Torch nach und
    // dauert Sekunden; in einer Momentaufnahme, die nach jedem Klick neu
    // entsteht, hat das nichts verloren. Dieselbe Lampe wie beim LLM.
    el("div", {class: "reihe"},
      el("span", {class: "scan-lampe" + (!b.ocr_stand ? ""
        : (b.ocr_stand.da ? " an" : " aus"))}),
      el("span", {class: "klein wachse"}, !b.ocr_stand
        ? "noch nicht geprüft"
        : (b.ocr_stand.da ? b.ocr_stand.backends.join(", ")
                          : "kein Backend installiert")),
      el("button", {class: "btn still", onclick: () => rufScan("ocr_pruefen")},
         "prüfen")),
    el("p", {class: "hinweis"}, !b.ocr_an
      ? "OCR ist in den Einstellungen aus (ocr_enabled) — dieser Schalter "
        + "greift erst danach."
      : (b.ocr_stand && !b.ocr_stand.da
          ? "pip install easyocr (oder pytesseract)"
          : b.ocr_backend + " · " + (b.ocr_sprachen.join(",") || "en")
            + " · min " + b.ocr_min.toFixed(2))),
    el("span", {class: "ueberschrift"}, "LLM VISION"),
    schalter("LLM benutzen", c.use_llm, (v) => erkFeld("use_llm", v)),
    c.use_llm ? segment([{wert: true, text: "als Fallback"}, {wert: false, text: "primär"}],
      c.llm_fallback, (v) => erkFeld("llm_fallback", v)) : null,
    el("div", {class: "reihe"},
      el("span", {class: "scan-lampe" + lampe}),
      // Ohne Probe steht hier „noch nicht geprueft", nicht der Endpunkt: ein
      // leeres Feld (die Voreinstellung ist leer) saehe aus wie ein Fehler.
      // Der Endpunkt gehoert in den Tooltip — dort sucht man ihn, wenn die
      // Lampe rot ist.
      el("span", {class: "klein wachse", title: b.llm_endpunkt || ""},
        !b.llm_stand ? "noch nicht geprüft"
          : (b.llm_stand.erreichbar ? "erreichbar (" + b.llm_stand.dauer + " ms)"
                                    : "nicht erreichbar")),
      el("button", {class: "btn still", onclick: () => rufScan("llm_pruefen")}, "testen")),
    el("p", {class: "hinweis"}, b.llm_an
      ? erkReihenfolge(c)
      : "LLM ist in den Einstellungen aus (llm_enabled) — dieser Schalter greift "
        + "erst danach."),
  ]);
}

/** In welcher Reihenfolge erkannt wird — als ein Satz.
 *
 * Bei gleicher Einstellung laeuft OCR VOR LLM: OCR ist lokal und schnell, das
 * LLM kostet bis `llm_timeout`. Dieselbe Reihenfolge steht in
 * `runtime/boss_detection.py`; hier wird sie nur vorgelesen. */
function erkReihenfolge(c) {
  const vorn = [], hinten = [];
  for (const [name, an, fallback] of [["OCR", c.use_ocr, c.ocr_fallback],
                                      ["LLM", c.use_llm, c.llm_fallback]])
    if (an) (fallback ? hinten : vorn).push(name);
  return "Reihenfolge: " + vorn.concat(["Template/Marker"], hinten).join(" → ");
}

/** Schritt 5 (Boss): was passiert, wenn KEIN Boss erkannt wird. */
function erkFallbackSchritt(c) {
  const text = (SC.aktionen.boss.find((a) => a.wert === c.default_action) || {}).text
    || c.default_action;
  return erkKarte(5, "Fallback", "wenn kein Boss erkannt: " + text, true, [
    el("p", {class: "hinweis"}, "Greift, wenn keiner der Bosse passt — und auch "
      + "dann, wenn OCR und LLM nichts finden."),
    erkAktionsKacheln(SC.aktionen.boss, c.default_action,
                      (v) => erkFeld("default_action", v)),
    c.default_action === "item_scan"
      ? auswahl("Item-Scan", [{wert: "", text: "— keiner —"}].concat(
          SC.item_scan_namen.map((n) => ({wert: n, text: n}))), c.default_scan || "",
          (v) => erkFeld("default_scan", v))
      : null,
  ]);
}

/** Schritt 3 (Icon): Template oder Farb-Marker. */
function erkErkennungSchritt(c) {
  return erkKarte(3, "Erkennung", c.erkennung === "template"
    ? "Vorlage · min " + c.konfidenz.toFixed(2)
    : (c.erkennung === "marker" ? c.marker.length + " Marker · Toleranz " + c.toleranz
                                : "Noch nichts gesetzt"),
    c.erkennung !== "keine", erkErkennungsFelder(c, "icon"));
}

/** Die Erkennungs-Felder — dieselben fuer Boss und Icon.
 *
 * Beide erkennen ueber Template ODER Farb-Marker; das sind dieselben Felder und
 * dieselben Knoepfe. Zwei Fassungen davon waeren zwei Stellen, an denen ein
 * Griff fehlt — und „Vorlage neu aufnehmen" ist genau der Griff, der heute den
 * ganzen Konsolen-Ablauf kostet. */
function erkErkennungsFelder(objekt, art, name) {
  const ueber = ERK_BEFEHL[art].feld;
  const setze = (feld, wert) => rufScan(ueber, Object.assign(
    {feld: feld, wert: wert}, name ? {name: name} : {}));
  const template = objekt.erkennung !== "marker";
  return [
    segment([{wert: "template", text: "Template"}, {wert: "marker", text: "Farb-Marker"}],
      objekt.erkennung === "marker" ? "marker" : "template",
      // Umschalten heisst hier: das andere loswerden. Beides stehen zu lassen
      // waere `_check_profile_match`s UND — dann muessen BEIDE stimmen, und
      // niemand rechnet damit.
      (v) => setze(v === "marker" ? "template" : "marker", v === "marker" ? "" : [])),
    template ? el("div", {class: "reihe", style: "align-items:flex-start"},
      objekt.vorschau
        ? el("img", {class: "scan-vorlage", src: objekt.vorschau, alt: ""})
        : el("div", {class: "scan-vorlage leer"}, "keine Vorlage"),
      el("div", {class: "spalte wachse"},
        el("span", {class: "klein mono"}, objekt.template || "—"),
        zahlfeld("Min. Konfidenz", objekt.konfidenz, (v) => setze("konfidenz", v),
          {min: 0.05, max: 1, step: 0.01},
          "Ab welcher Übereinstimmung ein Treffer zählt. Zu hoch heisst "
          + "„findet nie“, zu tief „findet alles“.", "konfidenz"))) : null,
    template ? el("button", {class: "btn scan-assistent-haupt",
      disabled: !fotoDa() || !SC.opencv,
      title: SC.opencv ? "Lernt die Region aus dem eingefrorenen Bild"
                       : "Ohne OpenCV gibt es kein Template-Matching",
      onclick: () => rufScan("vorlage_aufnehmen", Object.assign(
        {art: art}, name ? {name: name} : {}))}, "Vorlage neu aufnehmen") : null,
    !template ? el("div", {class: "scan-marker"},
      objekt.marker.map((h) => el("span", {class: "scan-farbfeld", style: "background:" + h,
                                           title: h})),
      el("span", {class: "scan-farbfeld leer", title: "noch Platz"})) : null,
    !template ? el("div", {class: "gitter2"},
      zahlfeld("Toleranz", objekt.toleranz === undefined ? 30 : objekt.toleranz,
        (v) => setze("toleranz", v), {min: 0, step: 1},
        "Wie weit eine Marker-Farbe abweichen darf.", "erktoleranz"),
      el("div", {class: "feld-still"}, "gemessen",
        el("span", {class: "mono"}, objekt.marker.length + " Farben"))) : null,
    !template ? el("button", {class: "btn scan-assistent-haupt", disabled: !fotoDa(),
      onclick: () => rufScan("marker_messen", Object.assign(
        {art: art}, name ? {name: name} : {}))}, "Marker im Bild neu messen") : null,
    !template ? el("p", {class: "hinweis"}, "min. Pixel über 1 halten — sonst löst "
      + "ein einzelner Rausch-Pixel den Scan aus (Einstellung "
      + "scan_marker_min_pixels, gerade " + SC.bereit.marker_min_pixel + ").") : null,
  ];
}

/** Aktions-Kacheln: feste kurze Auswahl, also Kacheln statt Klappliste.
 *
 * Die Werte kommen aus `models.py` (ueber die Momentaufnahme) — die Ansicht
 * erfindet keine Aktionsnamen. Ein getipptes "skipcycle" waere ein Wert, den
 * `__post_init__` beim Speichern still auf den Standard hebt: der Klick saehe
 * aus, als haette er gewirkt. */
function erkAktionsKacheln(werte, aktuell, beim_setzen) {
  // Dasselbe Raster wie beim Block-Typ im Sequenz-Editor — die Kacheln sollen
  // sich gleich anfuehlen. Auf der Kachel steht das Schlagwort, im Tooltip der
  // Satz: „Zyklus abbrechen" ist auf 9,5 px zweizeilig und unlesbar.
  return el("div", {class: "gitter3"}, werte.map((a) =>
    el("button", {class: "typ-chip" + (a.wert === aktuell ? " an" : ""),
      title: a.text, onclick: () => beim_setzen(a.wert)}, a.kurz)));
}

/** Die Felder hinter einer Aktion — Punkt, Taste, Verzoegerung, Item-Scan. */
function erkAktionsFelder(objekt, art, name) {
  const ueber = ERK_BEFEHL[art].feld;
  const setze = (feld, wert) => rufScan(ueber, Object.assign(
    {feld: feld, wert: wert}, name ? {name: name} : {}));
  const felder = [];
  if (objekt.aktion === "item_scan") {
    felder.push(auswahl("Item-Scan", [{wert: "", text: "— keiner —"}].concat(
      SC.item_scan_namen.map((n) => ({wert: n, text: n}))), objekt.scan || "",
      (v) => setze("scan", v)));
    felder.push(auswahl("Modus", SC.aktionen.scan_modi.map(
      (m) => ({wert: m.wert, text: m.text})), objekt.scan_modus,
      (v) => setze("scan_modus", v)));
  }
  if (objekt.aktion === "click") {
    felder.push(auswahl("Punkt", [{wert: "", text: "— keiner —"}].concat(
      SC.punkte.map((p) => ({wert: p.id, text: "#" + p.id + " " + p.name}))),
      objekt.punkt_id === null || objekt.punkt_id === undefined ? "" : objekt.punkt_id,
      (v) => setze("punkt", v === "" ? null : Number(v))));
    felder.push(el("button", {class: "btn still", disabled: !fotoDa(),
      onclick: () => rufScan("region_modus", {art: art, modus: "aktion"})},
      "Stelle im Bild anklicken"));
  }
  if (objekt.aktion === "key")
    felder.push(feld("Taste", objekt.taste || "", (v) => setze("taste", v)));
  felder.push(zahlfeld("Verzögerung vor Aktion (s)", objekt.verzoegerung,
    (v) => setze("verzoegerung", v), {min: 0, step: 0.1}));
  return felder;
}

/** Schritt 4 (Icon): die Aktion bei Fund. */
function erkAktionSchritt(c, art) {
  const text = (SC.aktionen.icon.find((a) => a.wert === c.aktion) || {}).text || c.aktion;
  return erkKarte(4, "Aktion", text + (c.verzoegerung ? " · " + c.verzoegerung + " s" : ""),
    true, [
    erkAktionsKacheln(SC.aktionen.icon, c.aktion, (v) => erkFeld("aktion", v)),
    // Ausgebreitet, nicht als Liste in der Liste: `el()` flacht genau EINE
    // Ebene ab, und ein Array als Kind landet als solches in `appendChild` —
    // was den ganzen Aufbau abbricht.
    ...erkAktionsFelder(c, art),
  ]);
}

/** Ein Feld des OFFENEN Scans setzen — Boss-Scan oder Icon-Scan. */
function erkFeld(feld, wert) {
  const c = erkScan();
  if (!c) return;
  rufScan(erkBefehl("scan_feld"), {name: c.name, feld: feld, wert: wert});
}

/* -------------------------------------------------------------- Testleiste */

/** Was der letzte Test ergeben hat — und was die Aktion WAERE.
 *
 * **Der Test fuehrt die Aktion nicht aus.** Er erkennt, zeigt und benennt; das
 * steht auch als Nachsatz in der Leiste. Ein Testknopf, der im Editor eines
 * Autoclickers wirklich klickt, ist die schlechteste denkbare Ueberraschung. */
function erkTestleiste(ziel) {
  const t = scanArt === "boss" ? SC.boss.test : SC.icon.test;
  if (!t) return false;
  const farbe = t.ok ? "var(--ok)" : "var(--err)";
  ziel.append(
    el("b", {style: "color:" + farbe},
      t.ok ? "Test: " + t.name + " erkannt" : "Test: " + t.name + " nicht erkannt"));
  if (t.methode && t.konfidenz !== null && t.methode === "Template")
    ziel.appendChild(el("span", {class: "kennzahl"}, "Template · " + t.konfidenz.toFixed(2)));
  if (t.marker_gesamt)
    ziel.appendChild(el("span", {class: "kennzahl"},
      t.marker_gefunden + " von " + t.marker_gesamt + " Markern · nötig " + t.marker_noetig));
  if (t.toleranz) ziel.appendChild(el("span", {class: "kennzahl"}, "Toleranz " + t.toleranz));
  if (t.dauer) ziel.appendChild(el("span", {class: "kennzahl"}, t.dauer + " ms"));
  ziel.appendChild(el("span", {class: "wachse"}));
  ziel.appendChild(el("span", {class: "klein"},
    t.ok ? "Aktion wäre: " + t.aktion + " (wird nicht ausgeführt)" : t.grund));
  // **Der Vorschlag ist der Kern.** Ein Test, der nur „fehlgeschlagen" sagt,
  // laesst einen genau dort stehen, wo man vorher war.
  if (t.vorschlag)
    ziel.appendChild(el("button", {class: "btn an",
      onclick: () => erkFeld(t.vorschlag.feld, t.vorschlag.wert)}, t.vorschlag.text));
  ziel.appendChild(el("button", {class: "btn still", onclick: () => erkTesten()},
    "nochmal testen"));
  return true;
}

function erkTesten() { return rufScan(erkBefehl("testen")); }

/* ------------------------------------------------------------------ Listen */

function erkListeBosse(ziel) {
  const c = erkScan();
  if (!c) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Noch kein Boss-Scan. Oben einen anlegen — er ist die Klammer um Region, "
      + "Bosse und Fallback."));
    return;
  }
  const lokal = c.bosse;
  if (!lokal.length && !SC.global_bosses.length) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Noch kein Boss. Ein Boss ist eine Vorlage (oder ein paar Farben) und eine "
      + "Aktion dahinter."));
  }
  for (const b of lokal) ziel.appendChild(erkBossZeile(b, false));
  if (SC.global_bosses.length) {
    ziel.appendChild(el("div", {class: "scan-kategorie-kopf"},
      "AUS DER BIBLIOTHEK · GILT ZUSÄTZLICH"));
    const namen = new Set(lokal.map((x) => x.name));
    for (const b of SC.global_bosses) {
      // Ein lokaler Boss gleichen Namens hat Vorrang — dann steht der globale
      // hier blass, statt so zu tun, als wuerde er benutzt.
      ziel.appendChild(erkBossZeile(b, true, namen.has(b.name)));
    }
  }
  ziel.appendChild(el("button", {class: "leerzone",
    onclick: () => { scanListe = "bibliothek"; zeichneScans(); }},
    "Boss-Bibliothek (global) · " + SC.global_bosses.length));
}

function erkBossZeile(b, global, verdeckt) {
  const test = SC.boss.tests[b.name];
  const gewaehlt = SC.boss.wahl === b.name && SC.boss.wahl_global === !!global;
  return el("button", {
    class: "scan-zeile" + (gewaehlt ? " an" : ""),
    style: verdeckt ? "opacity:.5" : null,
    title: verdeckt ? "Ein lokaler Boss gleichen Namens hat Vorrang" : "",
    onclick: () => rufScan("boss_waehlen", {name: b.name, global: !!global}),
  },
    b.vorschau ? el("img", {class: "mini", src: b.vorschau})
               : el("span", {class: "kugel" + (b.marker.length ? "" : " ohne"),
                             style: b.marker.length ? "background:" + b.marker[0] : ""}),
    el("span", {class: "name"}, b.name),
    b.erkennung === "keine"
      ? el("span", {class: "klein", style: "color:var(--accent)",
                    title: "Weder Vorlage noch Marker — nur OCR/LLM können ihn finden"},
           "⚠ keine Vorlage")
      : (test
          ? el("span", {class: "klein", style: "color:var(" + (test.ok ? "--slot-ok" : "--err") + ")"},
               test.ok ? "erkannt" : "nein")
          : el("span", {class: "klein mono"},
               (SC.aktionen.boss.find((a) => a.wert === b.aktion) || {}).text || b.aktion)));
}

function erkListeIcons(ziel) {
  if (!SC.icon_scans.length) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Noch kein Icon-Scan. Er erkennt EIN Symbol in einer Region und tut dann "
      + "etwas — keine Slots, keine Kategorien, kein LLM."));
  }
  for (const c of SC.icon_scans) {
    const test = SC.icon.test && SC.icon.test.name === c.name ? SC.icon.test : null;
    ziel.appendChild(el("button", {
      class: "scan-zeile" + (SC.icon.offen === c.name ? " an" : ""),
      onclick: () => rufScan("icon_scan_oeffnen", {name: c.name}),
    },
      c.vorschau ? el("img", {class: "mini", src: c.vorschau})
                 : el("span", {class: "kugel" + (c.marker.length ? "" : " ohne"),
                               style: c.marker.length ? "background:" + c.marker[0] : ""}),
      el("span", {class: "name"}, c.name),
      c.erkennung === "keine"
        ? el("span", {class: "klein", style: "color:var(--accent)"}, "⚠ ohne Erkennung")
        : (test ? el("span", {class: "klein",
                              style: "color:var(" + (test.ok ? "--slot-ok" : "--err") + ")"},
                     test.ok ? "erkannt" : "nein")
                : el("span", {class: "klein mono"},
                     (c.region[2] - c.region[0]) + "×" + (c.region[3] - c.region[1])))));
  }
}

/** Die Bibliothek in der Liste: dieselben Bosse, die in der Mitte als Karten
 *  stehen. Die Knoepfe („+ Boss", „zurueck") stehen NICHT hier, sondern rechts
 *  — sonst gaebe es sie zweimal, und man raet, welcher der fuehrende ist. */
function erkListeBibliothek(ziel) {
  ziel.appendChild(el("p", {class: "hinweis"},
    "Diese Bosse gelten zusätzlich in JEDEM Boss-Scan. Ein lokaler Boss mit "
    + "gleichem Namen hat Vorrang."));
  if (!SC.global_bosses.length) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Noch leer. Rechts einen anlegen — oder einen Boss aus einem Scan "
      + "hierher verschieben."));
    return;
  }
  for (const b of SC.global_bosses) ziel.appendChild(erkBossZeile(b, true));
}

/* ---------------------------------------------- Bibliothek als Kartenraster */

function erkBibliothekZeichnen() {
  const ziel = $("scan-bibliothek");
  const zeigen = erkBibliothek();
  ziel.hidden = !zeigen;
  $("scan-flaeche").hidden = zeigen || !SC.foto;
  $("scan-leer").hidden = zeigen || !!SC.foto;
  $("scan-ohne-bild").hidden = zeigen || fotoDa();
  if (!zeigen) return;
  ziel.replaceChildren();
  if (!SC.global_bosses.length) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Die Bibliothek ist leer. Wer denselben Boss in mehreren Scans braucht, "
      + "pflegt ihn sonst mehrfach — und ändert beim nächsten Mal nur die Hälfte."));
    return;
  }
  for (const b of SC.global_bosses) ziel.appendChild(erkBibliothekKarte(b));
}

function erkBibliothekKarte(b) {
  // Ein vom LLM entdeckter Boss wird als `skip` angelegt: er ist erkannt, aber
  // es ist noch nicht entschieden, was mit ihm passieren soll. Das ist keine
  // Warnung, sondern eine offene Aufgabe — deshalb Amber und ein Hauptknopf.
  const offen = b.aktion === "skip" && b.erkennung === "keine";
  const karte = el("div", {class: "seq-karte" + (offen ? " neu-vom-llm" : "")},
    el("div", {class: "scan-karte-kopf"},
      b.vorschau ? el("img", {class: "mini", src: b.vorschau})
                 : el("span", {class: "kugel" + (b.marker.length ? "" : " ohne"),
                               style: b.marker.length ? "background:" + b.marker[0] : ""}),
      el("b", {class: "wachse"}, b.name),
      el("span", {class: "zahl"}, offen ? "neu vom LLM" : b.erkennung)));
  if (b.marker.length) {
    karte.appendChild(el("div", {class: "scan-marker"},
      b.marker.map((h) => el("span", {class: "scan-farbfeld", style: "background:" + h}))));
  }
  if (offen) {
    karte.appendChild(el("p", {class: "hinweis"},
      "Seine Aktion ist noch „Schritt überspringen“ — er wird erkannt, aber es "
      + "passiert nichts."));
  } else {
    karte.appendChild(el("div", {class: "scan-karte-zahlen"},
      el("span", {class: "zahl"}, "konf " + b.konfidenz.toFixed(2)),
      el("span", {class: "zahl"}, (SC.aktionen.boss.find((a) => a.wert === b.aktion)
        || {}).text || b.aktion),
      b.scan ? el("span", {class: "zahl"}, "scan → " + b.scan) : null,
      b.verzoegerung ? el("span", {class: "zahl"}, "delay " + b.verzoegerung + " s") : null));
  }
  karte.appendChild(el("div", {class: "reihe"},
    el("button", {class: offen ? "btn haupt" : "btn still",
      onclick: () => { scanListe = "bosse";
                       rufScan("boss_waehlen", {name: b.name, global: true}); }},
      offen ? "Aktion zuweisen" : "bearbeiten"),
    el("button", {class: "btn still",
      onclick: () => rufScan("boss_loeschen", {name: b.name, global: true})}, "löschen")));
  return karte;
}

/* ------------------------------------------------------- Rechte Spalte */

function erkInspektor(ziel) {
  if (erkBibliothek()) return erkInspBibliothek(ziel);
  const c = erkScan();
  if (!c) {
    ziel.appendChild(el("p", {class: "hinweis"}, scanArt === "boss"
      ? "Kein Boss-Scan gewählt. Links einen anlegen."
      : "Kein Icon-Scan gewählt. Links einen anlegen."));
    return;
  }
  if (scanArt === "icon") return erkInspIcon(ziel, c);
  const b = erkBoss();
  return b ? erkInspBoss(ziel, c, b) : erkInspBossScan(ziel, c);
}

/** Ohne gewaehlten Boss gehoert die Spalte dem Scan: Region, Toleranz, Fallback. */
function erkInspBossScan(ziel, c) {
  ziel.appendChild(ueberschrift("BOSS-SCAN „" + c.name + "“",
    "Ein Block vom Typ BOSS-SCAN oder BOSS-WATCHER verweist per Name hierauf. "
    + "Umbenennen: oben links.", "bossscan"));
  ziel.appendChild(zahlfeld("Farb-Toleranz", c.toleranz,
    (v) => erkFeld("toleranz", v), {min: 0, step: 1},
    "Gilt für die Marker-Farben aller Bosse dieses Scans.", "bosstoleranz"));
  ziel.appendChild(ueberschrift("WENN KEIN BOSS ERKANNT",
    "Greift auch dann, wenn OCR und LLM nichts finden.", "bossfallback"));
  ziel.appendChild(erkAktionsKacheln(SC.aktionen.boss, c.default_action,
    (v) => erkFeld("default_action", v)));
  if (c.default_action === "item_scan") {
    ziel.appendChild(auswahl("Item-Scan", [{wert: "", text: "— keiner —"}].concat(
      SC.item_scan_namen.map((n) => ({wert: n, text: n}))), c.default_scan || "",
      (v) => erkFeld("default_scan", v)));
  }
  if (Object.keys(SC.boss.tests).length) {
    ziel.appendChild(ueberschrift("ALLE BOSSE GEGEN DIESES BILD",
      "Was jeder einzelne ergeben hat — und woran es lag.", "bosstests"));
    for (const [name, t] of Object.entries(SC.boss.tests)) {
      ziel.appendChild(el("div", {class: "scan-erg-zeile" + (t.ok ? " ok" : "")},
        el("span", {}, name),
        el("span", {class: "mono klein",
                    style: "color:var(" + (t.ok ? "--ok" : "--dim") + ")"},
           t.ok ? "erkannt" : "nein"),
        el("span", {class: "grund"}, t.grund)));
    }
  }
  ziel.appendChild(el("p", {class: "hinweis"}, "Im Sequenz-Editor: ein Block "
    + "BOSS-SCAN prüft einmal, BOSS-WATCHER wartet, bis ein Boss auftaucht."));
  ziel.appendChild(el("button", {class: "btn gefahr", style: "margin-top:14px",
    onclick: () => rufScan(erkBefehl("loeschen"))}, "Boss-Scan löschen"));
}

/** Der wichtigste Fall: einen bestehenden Boss aendern, ohne den Assistenten
 *  noch einmal zu durchlaufen. Jedes Feld steht hier und ist einzeln setzbar. */
function erkInspBoss(ziel, c, b) {
  ziel.appendChild(el("div", {class: "reihe"},
    el("button", {class: "btn still",
      onclick: () => rufScan("boss_waehlen", {name: ""})}, "‹ zurück zum Scan"),
    el("span", {class: "wachse"}),
    el("button", {class: "btn still",
      onclick: () => rufScan("boss_loeschen")}, "löschen")));
  ziel.appendChild(el("button", {class: "btn haupt", disabled: !fotoDa(),
    onclick: () => rufScan("boss_testen")}, "Diesen Boss testen"));
  ziel.appendChild(ueberschrift("BOSS", "Der Name ist zugleich das, was OCR und "
    + "LLM im Bild suchen — er sollte also der Name im Spiel sein.", "bossname"));
  ziel.appendChild(feld("Name", b.name, (v) => rufScan("boss_setzen",
    {name: b.name, global: b.global, feld: "name", wert: v})));
  if (b.global) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Aus der Bibliothek — Änderungen gelten in jedem Boss-Scan."));
  }
  ziel.appendChild(ueberschrift("ERKENNUNG", "Template ODER Farb-Marker. Beides "
    + "gesetzt heisst: beides muss stimmen.", "bosserkennung"));
  for (const teil of erkErkennungsFelder(b, "boss", b.name))
    if (teil) ziel.appendChild(teil);
  ziel.appendChild(ueberschrift("AKTION BEI TREFFER",
    "Was passiert, wenn genau dieser Boss erkannt wird.", "bossaktion"));
  ziel.appendChild(erkAktionsKacheln(SC.aktionen.boss, b.aktion,
    (v) => rufScan("boss_setzen", {name: b.name, global: b.global,
                                   feld: "aktion", wert: v})));
  for (const teil of erkAktionsFelder(b, "boss", b.name))
    if (teil) ziel.appendChild(teil);
  ziel.appendChild(el("button", {class: "btn still", style: "margin-top:14px",
    title: "Bosse der Bibliothek gelten in jedem Boss-Scan",
    onclick: () => rufScan("boss_global_verschieben", {name: b.name, global: b.global})},
    b.global ? "In diesen Scan holen" : "In die Bibliothek verschieben"));
}

function erkInspIcon(ziel, c) {
  ziel.appendChild(el("button", {class: "btn haupt", disabled: !fotoDa(),
    onclick: () => rufScan("icon_testen")}, "Icon-Scan testen"));
  ziel.appendChild(ueberschrift("ICON-SCAN „" + c.name + "“",
    "Erkennt EIN Symbol in einer Region und tut dann etwas. Ein Block vom Typ "
    + "ICON-SCAN verweist per Name hierauf.", "iconscan"));
  // **Der Ausschnitt zeigt, was der Scan sieht.** Vier Zahlen sagen nicht, ob
  // die Region sitzt; ein Bild von 104 px sagt es in einer Sekunde.
  ziel.appendChild(c.ausschnitt
    ? el("img", {class: "scan-vorlage quadrat", src: c.ausschnitt, alt: ""})
    : el("div", {class: "scan-vorlage quadrat leer"}, "kein Bild"));
  ziel.appendChild(el("p", {class: "hinweis"},
    "Der Ausschnitt zeigt, was der Scan sieht — "
    + (c.region[2] - c.region[0]) + "×" + (c.region[3] - c.region[1])
    + " ab (" + c.region[0] + ", " + c.region[1] + ")."));
  ziel.appendChild(el("button", {class: "btn", disabled: !fotoDa(),
    onclick: () => rufScan("region_modus", {art: "icon", modus: "region"})},
    "Region neu aufziehen"));
  ziel.appendChild(ueberschrift("AKTION BEI FUND",
    "Was passiert, wenn das Symbol da ist.", "iconaktion"));
  ziel.appendChild(erkAktionsKacheln(SC.aktionen.icon, c.aktion,
    (v) => erkFeld("aktion", v)));
  for (const teil of erkAktionsFelder(c, "icon"))
    if (teil) ziel.appendChild(teil);
  // **Das ELSE gehoert dem Block, nicht dem Scan.** `IconScanConfig` hat kein
  // else-Feld, und eins hier einzufuehren hiesse, dieselbe Sache an zwei
  // Stellen zu haben: der Sequenz-Editor setzt sie am Block, wo sie auch fuer
  // Item- und Boss-Scans steht.
  ziel.appendChild(ueberschrift("WENN NICHTS ERKANNT",
    "Die Ersatzaktion gehört dem Block in der Sequenz, nicht dem Scan — dort "
    + "steht sie für alle drei Scan-Arten an derselben Stelle.", "iconelse"));
  ziel.appendChild(el("p", {class: "hinweis"},
    "Im Sequenz-Editor am Block einstellen. Als Befehl im Konsolen-Editor: "
    + "icon " + c.name + " else skip"));
  ziel.appendChild(el("button", {class: "btn gefahr", style: "margin-top:14px",
    onclick: () => rufScan(erkBefehl("loeschen"))}, "Icon-Scan löschen"));
}

function erkInspBibliothek(ziel) {
  ziel.appendChild(ueberschrift("BOSS-BIBLIOTHEK",
    "Gilt zusätzlich in jedem Boss-Scan. Ein lokaler Boss mit gleichem Namen "
    + "hat Vorrang.", "bossbib"));
  ziel.appendChild(el("p", {class: "hinweis"},
    SC.global_bosses.length + " Boss(e). Neu entdeckte Bosse landen hier, wenn "
    + "boss_learn_global eingeschaltet ist (Reiter Einstellungen) — sonst im "
    + "Scan, der sie gefunden hat."));
  ziel.appendChild(el("button", {class: "btn haupt",
    onclick: () => rufScan("boss_neu", {global: true})}, "+ Boss anlegen"));
  ziel.appendChild(el("button", {class: "btn still",
    onclick: () => { scanListe = "bosse"; zeichneScans(); }}, "zurück zum Scan"));
}

/* ------------------------------------------------------------------ Overlay */

/** Die Region des offenen Erkennungs-Scans und ihr Klickpunkt.
 *
 * Gezeichnet wird nur die des OFFENEN Scans, nicht jede vorhandene: zwanzig
 * Rechtecke auf einem Bild sind kein Ueberblick, sondern ein Gitter. */
function erkOverlay(svg, px) {
  const c = erkScan();
  if (!c) return;
  const t = scanArt === "boss" ? SC.boss.test : SC.icon.test;
  const zustand = !t ? "" : (t.ok ? " ok" : " fehl");
  const [x1, y1] = scanZuBild(c.region[0], c.region[1]);
  const [x2, y2] = scanZuBild(c.region[2], c.region[3]);
  svg.appendChild(svgEl("rect", {x: x1, y: y1, width: x2 - x1, height: y2 - y1,
    class: "scan-region-f" + zustand}));
  svg.appendChild(svgEl("rect", {x: x1, y: y1, width: x2 - x1, height: y2 - y1,
    class: "scan-region" + zustand}));
  const marke = (t && t.ok && t.konfidenz !== null && t.methode === "Template")
    ? t.name + " · " + t.konfidenz.toFixed(2)
    : (t ? (t.ok ? t.name + " erkannt" : "nicht erkannt")
         : "Region · " + (c.region[2] - c.region[0]) + "×" + (c.region[3] - c.region[1]));
  svg.appendChild(svgEl("text", {x: x1, y: y2 + 13 * px, class: "scan-marke",
    "font-size": 11 * px, "stroke-width": 3 * px,
    fill: !t ? null : (t.ok ? SLOT_FARBE.treffer : "#EF4444")}, marke));

  // Der Klickpunkt der Aktion: gestrichelt und in Amber — er ist ein
  // Handlungsort, keine Erkennung.
  const objekt = scanArt === "boss" ? erkBoss() : c;
  const punkt = objekt && objekt.punkt_id !== null && objekt.punkt_id !== undefined
    ? SC.punkte.find((p) => p.id === objekt.punkt_id) : null;
  if (!punkt || objekt.aktion !== "click") return;
  const [ax, ay] = scanZuBild(punkt.x, punkt.y);
  const arm = 9 * px;
  svg.appendChild(svgEl("rect", {class: "scan-aktion", x: ax - arm, y: ay - arm,
    width: arm * 2, height: arm * 2}));
  svg.appendChild(svgEl("text", {x: ax - arm, y: ay - arm - 4 * px, class: "scan-marke",
    "font-size": 10 * px, "stroke-width": 3 * px, fill: "#F59E0B"},
    "Klickpunkt Aktion"));
}

/* ----------------------------------------------------- Ansicht: Einstellungen */

/* Der Reiter bearbeitet `config.json` — eine ANDERE Datei als der Editor. Sein
 * Zustand liegt deshalb neben `S` und nicht darin: `C` ist die Antwort von
 * `config_lesen()` (Werte, Standardwerte, Abschnitte, Beschreibungen), und
 * `cfgGeaendert` sammelt, was noch nicht geschrieben ist.
 *
 * Gespeichert wird auf Knopfdruck, nicht bei jedem Tastendruck: die Werte
 * greifen in einen laufenden Lauf, und eine halb getippte Zahl darf nicht
 * schon gelten. */
let C = null;
let cfgGeaendert = {};
let cfgAbschnitt = 0;
let cfgSuche = "";
let cfgKorrekturen = [];

async function zeichneEinstellungen(frisch) {
  if (frisch || !C) {
    const antwort = await frage("config_lesen");
    // Zwischen Frage und Antwort kann umgeschaltet worden sein.
    if (!antwort || ansicht !== "einstellungen") return;
    C = antwort;
    // Was inzwischen von aussen genauso gesetzt wurde, ist keine Aenderung mehr.
    for (const k of Object.keys(cfgGeaendert))
      if (cfgGleich(cfgGeaendert[k], C.werte[k])) delete cfgGeaendert[k];
  }
  const merk = fokusMerken();
  zeichneCfgListe();
  zeichneCfgFelder();
  zeichneCfgRechts();
  fokusHerstellen(merk);
}

/** Gleicher Wert? Arrays über ihre Darstellung, alles andere strikt. */
function cfgGleich(a, b) {
  if (Array.isArray(a) || Array.isArray(b)) return JSON.stringify(a) === JSON.stringify(b);
  return a === b;
}

function cfgWert(key) {
  return Object.prototype.hasOwnProperty.call(cfgGeaendert, key)
    ? cfgGeaendert[key] : C.werte[key];
}

function cfgSetzen(key, wert) {
  if (cfgGleich(wert, C.werte[key])) delete cfgGeaendert[key];
  else cfgGeaendert[key] = wert;
  // Eine neue Eingabe macht die Korrekturmeldung von vorhin gegenstandslos.
  cfgKorrekturen = [];
  zeichneEinstellungen();
}

/** Wirkt das Feld überhaupt — oder hängt es an einem Schalter, der aus ist? */
function cfgAktiv(key) {
  const m = C.meta[key] || {};
  if (m.dep && !cfgWert(m.dep)) return false;
  if (m.dep_nicht && cfgWert(m.dep_nicht)) return false;
  if (m.dep_min && !(Number(cfgWert(m.dep_min)) > 0)) return false;
  return true;
}

function cfgWarum(m) {
  const anderes = m.dep || m.dep_nicht || m.dep_min;
  const name = (C.meta[anderes] && C.meta[anderes].label) || anderes;
  if (m.dep) return "Wirkt nur, wenn „" + name + "“ an ist.";
  if (m.dep_nicht) return "Wirkt nur, wenn „" + name + "“ aus ist.";
  return "Wirkt nur, wenn „" + name + "“ grösser als 0 ist.";
}

function cfgTrifft(key) {
  if (!cfgSuche) return true;
  const m = C.meta[key] || {};
  return (key + " " + (m.label || "") + " " + (m.hilfe || ""))
    .toLowerCase().includes(cfgSuche);
}

/** Ein Wert als Text — für „Standard: …" und die Änderungskarten. */
function cfgText(wert, m) {
  m = m || {};
  if (wert === null || wert === undefined || wert === "")
    return m.leer || (wert === "" ? "(leer)" : "keiner");
  if (wert === true) return "an";
  if (wert === false) return m.art === "xy" ? "aus" : "aus";
  if (Array.isArray(wert)) return "(" + wert.join(", ") + ")";
  if (m.optionen) {
    const t = m.optionen.find((o) => cfgGleich(o.wert, wert));
    if (t) return t.text;
  }
  if (wert === 0 && m.leer) return "0 — " + m.leer;
  return String(wert) + (m.einheit ? " " + m.einheit : "");
}

function zeichneCfgListe() {
  const ziel = $("cfg-liste");
  ziel.replaceChildren();
  C.abschnitte.forEach((a, i) => {
    const offen = a.keys.filter((k) => k in cfgGeaendert).length;
    const treffer = cfgSuche ? a.keys.filter(cfgTrifft).length : 0;
    ziel.appendChild(el("button", {
      class: "cfg-nav" + (!cfgSuche && i === cfgAbschnitt ? " an" : ""),
      onclick: () => { cfgSuche = ""; $("cfg-suche").value = ""; cfgAbschnitt = i;
                       zeichneEinstellungen(); },
    },
      el("span", {class: "wachse"}, a.titel),
      cfgSuche ? el("span", {class: "klein mono"}, treffer ? treffer + "×" : "") : null,
      offen ? el("span", {class: "zahl"}, offen) : null));
  });
}

function zeichneCfgFelder() {
  const ziel = $("cfg-felder");
  ziel.replaceChildren();
  if (C.fehler) {
    ziel.appendChild(el("p", {class: "leer", style: "color:var(--err)"}, C.fehler));
    return;
  }
  // Bei einer Suche werden ALLE Abschnitte mit Treffern gezeigt, nicht nur der
  // gewaehlte: wer sucht, weiss ja gerade nicht, wo der Wert steht.
  const gruppen = cfgSuche
    ? C.abschnitte.filter((a) => a.keys.some(cfgTrifft))
    : [C.abschnitte[cfgAbschnitt]].filter(Boolean);
  if (!gruppen.length) {
    ziel.appendChild(el("p", {class: "leer"}, "Kein Feld passt zu „" + cfgSuche + "“."));
    return;
  }
  for (const a of gruppen) {
    ziel.appendChild(el("div", {class: "cfg-gruppe"}, a.titel));
    for (const key of a.keys) if (cfgTrifft(key)) ziel.appendChild(cfgZeile(key));
  }
}

function cfgZeile(key) {
  const m = C.meta[key] || {label: key, art: "text"};
  const aktiv = cfgAktiv(key);
  const links = el("div", {},
    el("div", {class: "cfg-name"}, m.label),
    el("div", {class: "cfg-key"}, key),
    m.hilfe ? el("p", {class: "hinweis", style: "margin-top:5px"}, m.hilfe) : null,
    aktiv ? null : el("p", {class: "hinweis", style: "margin-top:5px;color:var(--accent)"},
                      cfgWarum(m)));
  const rechts = el("div", {class: "cfg-rechte"},
    cfgBedienelement(key, m), cfgLeer(key, m), cfgStandard(key, m));
  return el("div", {class: "cfg-zeile" + (key in cfgGeaendert ? " geaendert" : "") +
                           (aktiv ? "" : " blass")}, links, rechts);
}

function cfgBedienelement(key, m) {
  const wert = cfgWert(key);
  const setze = (v) => cfgSetzen(key, v);
  if (m.art === "bool") return schalter(wert ? "an" : "aus", wert, setze);
  if (m.art === "enum") return cfgKacheln(key, m, wert);
  if (m.art === "xy") return cfgStelle(key, m, wert);
  if (m.art === "area") {
    const feld = el("textarea", {});
    feld.value = wert === null || wert === undefined ? "" : String(wert);
    feld.addEventListener("change", () => setze(feld.value.trim() || null));
    return feld;
  }
  if (m.art === "text") {
    const feld = el("input", {autocomplete: "off",
                              value: wert === null || wert === undefined ? "" : String(wert)});
    feld.addEventListener("change", () => {
      const roh = feld.value.trim();
      setze(roh === "" && (C.optional || []).includes(key) ? null : roh);
    });
    feld.addEventListener("keydown", (e) => { if (e.key === "Enter") feld.blur(); });
    return feld;
  }
  return cfgZahl(key, m, wert);
}

function cfgZahl(key, m, wert) {
  const optional = (C.optional || []).includes(key);
  const feld = el("input", {type: "number", step: m.art === "int" ? "1" : "any",
                            value: wert === null || wert === undefined ? "" : wert});
  if (m.art === "ratio") { feld.setAttribute("min", "0"); feld.setAttribute("max", "1"); }
  feld.addEventListener("change", () => {
    const roh = feld.value.trim();
    // Leer heisst `null`, wo die Dataclass das erlaubt, und sonst 0. Der
    // Unterschied ist nicht kosmetisch: click_max_total = 0 waere „nach null
    // Klicks stoppen", null dagegen „unbegrenzt".
    if (roh === "") return cfgSetzen(key, optional ? null : 0);
    let z = Number(roh);
    // Fehleingabe wiederholen statt uebernehmen — dieselbe Regel wie in den
    // Konsolen-Editoren. Der Neuaufbau stellt den alten Wert wieder her.
    if (!isFinite(z)) return zeichneEinstellungen();
    if (m.art === "int") z = Math.round(z);
    if (m.art === "ratio") z = Math.max(0, Math.min(1, z));
    cfgSetzen(key, z);
  });
  feld.addEventListener("keydown", (e) => { if (e.key === "Enter") feld.blur(); });
  // Ein Prozentwert liest sich als Prozent, nicht als 0.8 — die Datei traegt
  // trotzdem die Zahl, mit der der Vergleich rechnet.
  const zusatz = m.art === "ratio" ? "= " + Math.round((Number(wert) || 0) * 100) + " %"
                                   : (m.einheit || "");
  if (!zusatz) return feld;
  return el("div", {class: "cfg-einheit"}, feld, el("span", {class: "einheit"}, zusatz));
}

/** Feste kurze Auswahl als Kacheln — dieselbe Regel wie beim Block-Typ. */
function cfgKacheln(key, m, wert) {
  return el("div", {class: "cfg-chips"}, (m.optionen || []).map((o) =>
    el("button", {class: "typ-chip" + (cfgGleich(o.wert, wert) ? " an" : ""),
                  onclick: () => cfgSetzen(key, o.wert)}, o.text)));
}

/** `scan_park_mouse`: aus (`false`) oder eine Stelle (`[x, y]`). */
function cfgStelle(key, m, wert) {
  const an = Array.isArray(wert);
  const xy = an ? wert : [0, 0];
  const setzeXY = (i, v) => {
    const neu = [Number(xy[0]) || 0, Number(xy[1]) || 0];
    neu[i] = Math.round(Number(v) || 0);
    cfgSetzen(key, neu);
  };
  const zahl = (i) => {
    const f = el("input", {type: "number", step: "1", value: xy[i], disabled: !an});
    f.addEventListener("change", () => setzeXY(i, f.value));
    return f;
  };
  return el("div", {class: "spalte", style: "gap:6px"},
    schalter(an ? "parken" : "aus", an, (v) => cfgSetzen(key, v ? [xy[0], xy[1]] : false)),
    an ? el("div", {class: "gitter2"}, zahl(0), zahl(1)) : null,
    // Eine Stelle faehrt man an, statt sie zu tippen — derselbe Weg wie beim
    // Klick-Block. Messen kann das nur ein Prozess auf demselben Rechner, und
    // das ist dieser hier.
    an ? el("button", {class: "btn still", onclick: () => cfgStelleAufnehmen(key)},
            "✛ mit der Maus setzen") : null,
    an ? el("p", {class: "hinweis"}, "Maus im Spiel an die Stelle, dann ENTER.") : null);
}

async function cfgStelleAufnehmen(key) {
  setzeStatus({text: "Maus an die Stelle bewegen und ENTER drücken (ESC bricht ab).",
               art: "warn"});
  const antwort = await frage("maus_stelle");
  if (!antwort) return;
  if (!antwort.ok) return setzeStatus({text: antwort.meldung || "Abgebrochen.", art: "warn"});
  cfgSetzen(key, [antwort.x, antwort.y]);
  setzeStatus({text: "Parkposition: (" + antwort.x + ", " + antwort.y + ")", art: "ok"});
}

/** Was ein leeres Feld bzw. eine 0 hier bedeutet — nur dann, wenn es so steht.
 *
 * Ohne diese Zeile liest sich eine 0 wie „aus", und bei `click_max_total` heisst
 * sie das Gegenteil. Sie steht deshalb am Wert und nicht in der Erklaerung: dort
 * las man sie erst, wenn man schon zweifelte. */
function cfgLeer(key, m) {
  const wert = cfgWert(key);
  const leer = wert === null || wert === undefined || wert === "" || wert === 0;
  if (!m.leer || !leer) return null;
  return el("span", {class: "cfg-standard"}, "= " + m.leer);
}

function cfgStandard(key, m) {
  const std = C.standard[key];
  if (cfgGleich(cfgWert(key), std))
    return el("span", {class: "cfg-standard"}, "Standard");
  return el("button", {class: "btn still cfg-standard",
                       title: "auf den Standardwert zurücksetzen",
                       onclick: () => cfgSetzen(key, std)},
            "↺ Standard: " + cfgText(std, m));
}

function zeichneCfgRechts() {
  const ziel = $("cfg-rechts");
  const keys = Object.keys(cfgGeaendert);
  ziel.replaceChildren();

  const kopf = el("div", {class: "abschnitt"},
    el("div", {class: "reihe"},
      el("span", {class: "ueberschrift wachse"}, "ÄNDERUNGEN"),
      keys.length ? el("span", {class: "zahl"}, keys.length) : null),
    el("button", {class: "btn haupt", disabled: !keys.length, onclick: cfgSpeichern},
       "In config.json schreiben"),
    keys.length ? el("button", {class: "btn", onclick: () => {
      cfgGeaendert = {}; cfgKorrekturen = []; zeichneEinstellungen();
    }}, "Änderungen verwerfen") : null);
  ziel.appendChild(kopf);

  const liste = el("div", {class: "abschnitt wachsend"});
  if (!keys.length && !cfgKorrekturen.length) {
    liste.appendChild(el("p", {class: "hinweis"},
      "Nichts geändert. Ein Wert gilt erst, wenn er geschrieben ist."));
  }
  for (const key of keys) {
    const m = C.meta[key] || {};
    liste.appendChild(el("div", {class: "cfg-karte"},
      el("div", {class: "reihe"},
        el("span", {class: "wachse", style: "font-size:12px"}, m.label || key),
        el("button", {class: "btn still", title: "diese Änderung zurücknehmen",
                      onclick: () => cfgSetzen(key, C.werte[key])}, "zurück")),
      el("div", {class: "cfg-key"}, key),
      el("div", {class: "reihe klein"},
        el("span", {class: "cfg-alt"}, cfgText(C.werte[key], m)), "→",
        el("span", {class: "cfg-neu"}, cfgText(cfgGeaendert[key], m)))));
  }
  // Korrekturen stehen, bis der naechste Wert angefasst wird: die Datei enthaelt
  // dann etwas anderes als eingegeben, und das darf nicht stillschweigend
  // passieren.
  for (const k of cfgKorrekturen) {
    const m = C.meta[k.key] || {};
    liste.appendChild(el("div", {class: "cfg-karte warn"},
      el("div", {style: "font-size:12px;color:var(--accent)"}, "korrigiert beim Speichern"),
      el("div", {class: "cfg-key"}, k.key),
      el("div", {class: "reihe klein"},
        el("span", {class: "cfg-alt"}, cfgText(k.gesendet, m)), "→",
        el("span", {class: "cfg-neu"}, cfgText(k.wurde, m)))));
  }
  ziel.appendChild(liste);

  ziel.appendChild(el("div", {class: "abschnitt"},
    el("p", {class: "hinweis"},
      "Ein laufender Lauf zieht sofort mit — der Hauptprozess lädt die Datei " +
      "neu, sobald hier geschrieben wurde."),
    el("p", {class: "cfg-key", style: "word-break:break-all"}, C.pfad || "")));
}

async function cfgSpeichern() {
  // Ein Feld, in dem gerade getippt wird, meldet erst beim Verlassen.
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  const werte = Object.assign({}, cfgGeaendert);
  const anzahl = Object.keys(werte).length;
  if (!anzahl) return;
  const antwort = await frage("config_schreiben", {werte: werte});
  if (!antwort) return;
  if (!antwort.ok)
    return setzeStatus({text: antwort.meldung || "Nicht gespeichert.", art: "err"});
  C.werte = antwort.werte;
  cfgGeaendert = {};
  cfgKorrekturen = antwort.korrekturen || [];
  setzeStatus({
    text: anzahl + (anzahl === 1 ? " Einstellung" : " Einstellungen") + " gespeichert." +
          (cfgKorrekturen.length ? "  " + cfgKorrekturen.length + " davon korrigiert." : ""),
    art: cfgKorrekturen.length ? "warn" : "ok"});
  zeichneEinstellungen();
}

/* --------------------------------------------------------------- Verdrahtung */

function verdrahte() {
  for (const t of document.querySelectorAll(".tab"))
    t.addEventListener("click", () => setzeAnsicht(t.dataset.ansicht));

  $("btn-laden").addEventListener("click",
    () => ruf("laden", {name: $("seq-auswahl").value}));
  $("seq-auswahl").addEventListener("dblclick",
    () => ruf("laden", {name: $("seq-auswahl").value}));
  $("btn-neu").addEventListener("click", () => ruf("neu"));
  $("btn-speichern").addEventListener("click", speichere);
  // Ein Knopf, zwei Bedeutungen — er trägt die aktuelle als Beschriftung, damit
  // niemand raten muss, was ein Druck jetzt tut.
  $("btn-lauf").addEventListener("click", () => laufSchicken(laufLief ? "stop" : "start"));
  $("btn-block-weg").addEventListener("click", () => ruf("auswahl_loeschen"));
  $("btn-block-kopie").addEventListener("click", () => ruf("auswahl_duplizieren"));

  $("seq-name").addEventListener("change", (e) =>
    ruf("sequenz_setzen", {feld: "name", wert: e.target.value}));
  $("seq-zyklen").addEventListener("change", (e) =>
    ruf("sequenz_setzen", {feld: "zyklen", wert: Number(e.target.value) || 0}));
  $("seq-info").addEventListener("change", (e) =>
    ruf("sequenz_setzen", {feld: "beschreibung", wert: e.target.value}));
  $("punkt-filter").addEventListener("input", zeichnePunkte);
  // Das Feld selbst wird beim Neuaufbau nicht ersetzt (es steht fest im
  // Dokument), deshalb darf es bei jedem Tastendruck melden.
  $("cfg-suche").addEventListener("input", (e) => {
    cfgSuche = e.target.value.trim().toLowerCase();
    zeichneEinstellungen();
  });

  for (const knopf of document.querySelectorAll("[data-scan-art]"))
    knopf.addEventListener("click", () => scanArtSetzen(knopf.dataset.scanArt));
  for (const knopf of document.querySelectorAll("[data-erk-tool]"))
    knopf.addEventListener("click", () => rufScan("region_modus",
      {art: scanArt, modus: knopf.dataset.erkTool}));

  $("scan-offen").addEventListener("change", (e) => {
    scanAssistentSchritt = null;
    rufScan("scan_oeffnen", {name: e.target.value});
  });
  $("scan-neu").addEventListener("click", () => {
    scanAssistentSchritt = 1;
    rufScan("scan_neu");
  });
  $("scan-frei").addEventListener("click", () => {
    scanGefuehrt = !scanGefuehrt;
    zeichneScans();
  });
  document.querySelectorAll("[data-scan-schritt]").forEach((knopf) =>
    knopf.addEventListener("click", () => {
      scanAssistentSchritt = Number(knopf.dataset.scanSchritt);
      scanSchritte();
    }));
  $("scan-slots-finden").addEventListener("click", () =>
    rufScan("scan_modus_setzen", {modus: "finden"}));
  $("scan-slot-neu").addEventListener("click", () =>
    rufScan("scan_modus_setzen", {modus: "slot"}));
  $("scan-test").addEventListener("click", () => rufScan("scan_erkennen"));
  $("scan-lernen").addEventListener("click", () =>
    rufScan("scan_lernvorschau", {scope: "alle"}));
  document.querySelectorAll("[data-scan-tool]").forEach((knopf) =>
    knopf.addEventListener("click", () =>
      rufScan("scan_modus_setzen", {modus: knopf.dataset.scanTool})));
  $("scan-pin").addEventListener("click", () =>
    rufScan("scan_modus_setzen", {modus: SC.modus, fixiert: !SC.werkzeug_fixiert}));
  // Wie jedes Tipp-Feld: melden beim VERLASSEN, nicht bei jedem Tastendruck -
  // sonst baut die Antwort die Ansicht neu, waehrend man noch tippt.
  $("scan-name").addEventListener("change", (e) => {
    if (SC && SC.offen) rufScan("scan_setzen",
                                {name: SC.offen, feld: "name", wert: e.target.value});
  });
  $("scan-name").addEventListener("keydown",
    (e) => { if (e.key === "Enter") e.target.blur(); });
  $("scan-foto").addEventListener("click", () => rufScan("scan_foto"));
  $("scan-vollbild").addEventListener("click", () => rufScan("scan_bereich_setzen"));
  $("scan-aufziehen").addEventListener("click",
    () => rufScan("scan_modus_setzen", {modus: "bereich"}));
  $("scan-fenster").addEventListener("change", (e) => {
    const wahl = scanFenster[Number(e.target.value)];
    // Waehlen nimmt NICHT auf — das tut der Knopf darueber. Vorher stand hier
    // beides in einem Griff, und dann sah es aus, als handele die Liste von
    // selbst und der Knopf gar nicht (er holte dasselbe Bild noch einmal).
    if (wahl) rufScan("scan_bereich_setzen", {bereich: wahl.bereich, fenster: wahl.id});
    else rufScan("scan_bereich_setzen");
  });
  $("scan-fit").addEventListener("click", scanEinpassen);
  $("scan-1zu1").addEventListener("click", () => {
    // 1:1 heisst: ein Bildschirm-Pixel ist ein Bildschirm-Pixel. Das Bild ist
    // fuer die Uebertragung verkleinert, also muss der Zoom das ausgleichen.
    scanZoom = SC && SC.foto ? 1 / SC.foto.skala : 1;
    scanZoomHand = true;
    scanZoomAnwenden();
  });
  for (const kopf of document.querySelectorAll(".klapp-kopf")) {
    kopf.addEventListener("click", () => {
      const s = kopf.dataset.klapp;
      // Beim ersten Griff die Vorgabe uebernehmen und umdrehen — sonst taete der
      // erste Klick auf einen automatisch zugeklappten Abschnitt nichts.
      klappZu[s] = !(klappZu[s] === null ? klappVorgabe(s) : klappZu[s]);
      klappPflegen();
    });
  }

  const flaeche = $("scan-overlay");
  flaeche.addEventListener("click", (e) => {
    // Ein Klick, der ein Ziehen beendet hat, ist kein Klick. Ohne das waehlte
    // das Loslassen den Slot gleich noch einmal neu aus.
    if (scanZiehGemacht) { scanZiehGemacht = false; return; }
    const stelle = scanStelleAusEvent(e);
    if (!stelle) return;
    // ALT misst den Hintergrund des Slots unter dem Zeiger — ohne den Umweg
    // ueber die Modus-Kachel. Der haeufigste Handgriff nach dem Finden.
    if (e.altKey) return rufScan("scan_direkt", {x: stelle[0], y: stelle[1],
                                                 was: "messen"});
    // STRG nimmt einen einzelnen Slot zur Auswahl dazu oder heraus — dieselbe
    // Geste wie im Sequenz-Editor.
    rufScan("scan_klick", {x: stelle[0], y: stelle[1],
                           zusatz: e.ctrlKey || e.metaKey});
  });
  flaeche.addEventListener("dblclick", (e) => {
    const stelle = scanStelleAusEvent(e);
    if (stelle) rufScan("scan_direkt", {x: stelle[0], y: stelle[1], was: "klick"});
  });

  // **Einen gewaehlten Slot zieht man, statt vier Zahlen zu tippen.** Gepackt
  // wird nur, was schon gewaehlt IST — damit braucht die Seite keine eigene
  // Trefferregel (die liegt in `_slot_unter()` in Python und soll dort bleiben),
  // und die Geste liest sich wie ueberall sonst: erst auswaehlen, dann ziehen.
  flaeche.addEventListener("mousedown", (e) => {
    if (e.button !== 0 || !SC || SC.modus !== "wahl" || SC.ecke) return;
    const stelle = scanStelleAusEvent(e);
    if (!stelle || !scanGewaehlteSlots().some((s) => scanInSlot(s, stelle))) return;
    scanZiehStart = stelle;
    scanZiehVersatz = [0, 0];
  });
  flaeche.addEventListener("mousemove", (e) => {
    if (scanZiehStart) {
      const stelle = scanStelleAusEvent(e);
      if (!stelle) return;
      const dx = stelle[0] - scanZiehStart[0], dy = stelle[1] - scanZiehStart[1];
      // **Ein wackliger Klick ist kein Ziehen.** Unter der Schwelle bleibt es
      // ein Klick (also eine Auswahl); ohne sie verschöbe jedes Anklicken eines
      // gewählten Slots ihn um ein, zwei Pixel — und weil das aussieht wie
      // nichts, fiele es erst beim Erkennen auf.
      if (!scanZiehVersatz && Math.abs(dx) < 2 && Math.abs(dy) < 2) return;
      scanZiehVersatz = [dx, dy];
      // Nur zeichnen: geschrieben wird einmal beim Loslassen.
      scanOverlay();
      return;
    }
    // Nur waehrend des Aufziehens gebraucht — sonst waere es ein Neuaufbau des
    // Overlays bei jeder Mausbewegung.
    if (!SC || !SC.ecke) return;
    scanZeiger = scanStelleAusEvent(e);
    scanOverlay();
  });
  // Am Fenster, nicht an der Flaeche: wer ueber den Bildrand hinauszieht,
  // liesse sonst einen Slot am Zeiger kleben.
  window.addEventListener("mouseup", () => {
    if (!scanZiehStart) return;
    const [dx, dy] = scanZiehVersatz || [0, 0];
    scanZiehStart = scanZiehVersatz = null;
    if (!dx && !dy) return;
    scanZiehGemacht = true;
    rufScan("scan_verschieben", {dx: dx, dy: dy});
  });
  // Mit STRG zoomen, wie in jedem Bildbetrachter; ohne STRG scrollt die Buehne.
  $("scan-buehne").addEventListener("wheel", (e) => {
    if (!e.ctrlKey || !SC || !SC.foto) return;
    e.preventDefault();
    scanZoom = Math.max(0.05, Math.min(4, scanZoom * (e.deltaY < 0 ? 1.15 : 0.87)));
    scanZoomHand = true;
    scanZoomAnwenden();
  }, {passive: false});

  // **Die Buehne aendert ihre Groesse mit dem Fenster, das Bild tat es nicht.**
  // Wer klein aufnimmt und dann gross zieht, sah sein Bild in einer Ecke kleben;
  // wer gross aufnimmt und klein zieht, musste scrollen. Beides ist derselbe
  // fehlende Handgriff. Ein von Hand gesetzter Zoom bleibt stehen — der ist eine
  // Ansage, die Fenstergroesse nicht.
  let scanRahmen = 0;
  window.addEventListener("resize", () => {
    if (ansicht !== "scans" || !SC || !SC.foto || scanZoomHand) return;
    // Gebuendelt: waehrend des Ziehens am Fensterrand feuert das im Dutzend,
    // und jeder Aufruf baut das Overlay neu.
    clearTimeout(scanRahmen);
    scanRahmen = setTimeout(scanEinpassen, 120);
  });

  $("dialog-ab").addEventListener("click", schliesseFrage);
  $("dialog-weg").addEventListener("click", () => fortfahren(true));
  $("dialog-speichern").addEventListener("click", () => fortfahren(false));

  // Ziehen über dem Board darf nicht als "Datei öffnen" enden.
  document.addEventListener("dragover", (e) => { if (ziehen) e.preventDefault(); });
  document.addEventListener("drop", (e) => e.preventDefault());
  document.addEventListener("keydown", tastatur);
}

async function speichere() {
  // Ein Feld, in dem gerade getippt wird, meldet seinen Wert erst beim Verlassen.
  // Ohne das Blur ginge die letzte Eingabe beim Speichern verloren.
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  await ruf("speichern");
  // Nur hier nachziehen, nicht in `zeichne()`: die Liste liest jede Sequenzdatei
  // einmal, und `zeichne()` läuft nach JEDEM Befehl. Ändern kann sich die Liste
  // ohnehin nur durch ein Speichern (Umbenennen legt eine neue Datei an).
  if (ansicht === "sequenzen") zeichneSequenzenliste();
}

function imTextfeld() {
  const a = document.activeElement;
  return a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.tagName === "SELECT");
}

function tastatur(e) {
  if (e.key === "Escape") {
    if (offeneFrage) return schliesseFrage();
    if (imTextfeld()) return document.activeElement.blur();
    if (ansicht === "scans") return rufScan("scan_abbrechen");
    if (ansicht === "einstellungen") return;
    return ruf("auswahl_leeren");
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    // Derselbe Griff, drei Dateien: welche gemeint ist, sagt der offene Reiter.
    if (ansicht === "einstellungen") return cfgSpeichern();
    if (ansicht === "scans") return rufScan("scan_speichern");
    return speichere();
  }
  if (imTextfeld() || offeneFrage) return;
  if (ansicht === "scans") {
    // STRG+Z steht NACH der Textfeld-Abfrage: in einem Eingabefeld gehoert das
    // Rueckgaengig dem Feld, nicht dem Reiter.
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      return rufScan("scan_rueckgaengig");
    }
    // **Pfeiltasten schieben die Auswahl.** Ein Slot, der drei Pixel daneben
    // liegt, war vorher nur ueber vier Zahlenfelder zu retten — und dreissig
    // gar nicht.
    const schub = {ArrowLeft: [-1, 0], ArrowRight: [1, 0],
                   ArrowUp: [0, -1], ArrowDown: [0, 1]}[e.key];
    if (schub && SC && (SC.auswahl.length || SC.wahl.art === "slot")) {
      e.preventDefault();
      const weit = e.shiftKey ? 10 : 1;
      // Eine GEHALTENE Taste ist ein Verschieben, nicht dreissig: nur der erste
      // Schritt einer Serie kommt auf den Rueckgaengig-Stapel.
      const jetzt = Date.now();
      const serie = jetzt - scanSchubZeit < 900;
      scanSchubZeit = jetzt;
      return rufScan("scan_verschieben",
                     {dx: schub[0] * weit, dy: schub[1] * weit, zaehlt: !serie});
    }
    // **Die Modus-Buchstaben gehoeren der Item-Art.** Ein „S" in der Boss-Ansicht
    // legte sonst einen Slot an — ein Werkzeug fuer etwas, das dort gar nicht
    // vorkommt, und der naechste Klick im Bild haette eine andere Wirkung als
    // die Leiste behauptet.
    if (scanArt === "item") {
      const modus = SCAN_MODI.find((m) => m.taste.toLowerCase() === e.key.toLowerCase());
      if (modus) { e.preventDefault(); return rufScan("scan_modus_setzen", {modus: modus.key}); }
      if (e.key === "Delete" && SC && SC.wahl.art === "slot") {
        e.preventDefault();
        return rufScan("scan_slot_loeschen");
      }
      return;
    }
    // Dieselbe Idee eine Ebene weiter: R und K sind die beiden Werkzeuge der
    // Erkennungs-Scans, T testet. Testen liegt auf einer Taste, weil man beim
    // Einstellen einer Toleranz zehnmal hintereinander testet.
    const werkzeug = {r: "region", k: "aktion"}[e.key.toLowerCase()];
    if (werkzeug) {
      e.preventDefault();
      return rufScan("region_modus", {art: scanArt, modus: werkzeug});
    }
    if (e.key.toLowerCase() === "t" && SC && erkScan()) {
      e.preventDefault();
      return erkTesten();
    }
    if (e.key === "Delete" && scanArt === "boss" && SC && SC.boss.wahl) {
      e.preventDefault();
      return rufScan("boss_loeschen");
    }
    return;
  }
  // Alles Weitere arbeitet auf der Block-Auswahl, die es hier nicht gibt.
  if (ansicht === "einstellungen") return;
  if (e.key === "Delete") { e.preventDefault(); return ruf("auswahl_loeschen"); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d") {
    e.preventDefault();          // sonst legt der Browser ein Lesezeichen an
    return ruf("auswahl_duplizieren");
  }
  if (e.altKey && e.key === "ArrowUp") { e.preventDefault(); return ruf("auswahl_verschieben", {delta: -1}); }
  if (e.altKey && e.key === "ArrowDown") { e.preventDefault(); return ruf("auswahl_verschieben", {delta: 1}); }
}

warteAufBruecke().then(async () => {
  verdrahte();
  flankenPuls();
  await ruf("snapshot");
  // CTRL+ALT+V startet denselben Prozess wie CTRL+ALT+B, nur mit vorgewaehltem
  // Reiter. Erst NACH der ersten Momentaufnahme, weil sie den Wunsch mitbringt.
  if (S && S.start_ansicht && S.start_ansicht !== "editor") setzeAnsicht(S.start_ansicht);
});
