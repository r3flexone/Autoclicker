"use strict";

/* ------------------------------------------------------------------ Werkzeug */

const $ = (id) => document.getElementById(id);

/** Kleiner DOM-Bauer: el("div", {class:"x", onclick:f}, kind, "text") */
/* HTML-Attribute, die allein durch ihr DASEIN wirken: `disabled="0"` sperrt
 * genauso wie `disabled="1"`. Ein falsy Wert muss sie deshalb weglassen, sonst
 * bewirkt eine Zahl das Gegenteil dessen, was dasteht.
 *
 * Genau das ist passiert: `disabled: punkt.verwendungen.length` im Werkzeug
 * „Punkte verwalten". Bei 0 Verwendungen (also genau dann, wenn man loeschen
 * DARF) wurde `setAttribute("disabled", 0)` gesetzt — und bei 3 ebenso. Der
 * Loeschen-Knopf war dauerhaft tot, in einem Werkzeug, das „sicher loeschen"
 * verspricht. */
const NUR_DASEIN = new Set(["disabled", "checked", "hidden", "readonly",
                            "required", "selected", "multiple", "open"]);

function el(tag, attrs, ...kinder) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (NUR_DASEIN.has(k) && !v) continue;
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
 * `change` und nicht `input`: jede Meldung baut die Ansicht neu, und ein Neuaufbau
 * mitten in der Eingabe nimmt das Feld weg, in das gerade getippt wird. */
/* Welche Erklaerungen aufgeklappt sind — als Schluessel, nicht als DOM-Verweis:
 * der Inspektor wird bei jeder Aenderung neu gebaut. */
const offeneHilfen = new Set();

/** Das kleine ⓘ hinter einer Beschriftung. Klick klappt den Text auf, Klick zu.
 *
 * Kein nativer Tooltip: der verschwindet nach Sekunden und taugt zum Nachlesen
 * nicht. Der Text landet HINTER dem Bedienelement — keine Positionsrechnung,
 * kein Overlay.
 *
 * `key` ist die Identitaet ueber Neuaufbauten hinweg; der Text taugt
 * dafuer nicht, weil Beschriftungen die Punkt-Nummer bzw. den Block-Typ tragen. */
function info(text, key) {
  if (!text) return null;
  // Kein Schriftzeichen und kein CSS-Kreis: WebView2 kann beides auf zwei
  // verschiedenen Pixelrastern rendern, wodurch zwei versetzte Konturen
  // entstehen. Kreis, Punkt und Strich kommen gemeinsam aus EINEM SVG.
  const image = svgEl("svg", {class: "info-glyphe", viewBox: "0 0 16 16",
    "aria-hidden": "true"});
  image.append(
    svgEl("circle", {cx: "8", cy: "8", r: "6.5", fill: "none",
      stroke: "currentColor", "stroke-width": "1"}),
    svgEl("circle", {cx: "8", cy: "5", r: ".8", fill: "currentColor"}),
    svgEl("path", {d: "M8 7.5v4", fill: "none", stroke: "currentColor",
      "stroke-width": "1.3", "stroke-linecap": "round"}));
  const zeichen = el("span", {class: "info", "data-hilfe": key || text}, image);
  zeichen._text = text;
  zeichen.addEventListener("click", (e) => {
    // Das ⓘ steckt in einem <label>; ohne das hier wuerde der Klick das Feld
    // fokussieren bzw. den Schalter umlegen.
    e.preventDefault();
    e.stopPropagation();
    const hilfeId = zeichen.getAttribute("data-hilfe");
    if (offeneHilfen.has(hilfeId)) offeneHilfen.delete(hilfeId);
    else offeneHilfen.add(hilfeId);
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
function beschriftet(text, help, key) {
  return help ? el("span", {class: "mitinfo"}, text, info(help, key)) : text;
}

function feld(beschriftung, value, beim_setzen, extra, help, key) {
  const eingabe = el("input", Object.assign({value: value === null || value === undefined ? "" : value,
                                             autocomplete: "off"}, extra || {}));
  eingabe.addEventListener("change", () => beim_setzen(eingabe.value));
  eingabe.addEventListener("keydown", (e) => { if (e.key === "Enter") eingabe.blur(); });
  return el("label", {class: "feld"}, beschriftet(beschriftung, help, key), eingabe);
}

/** Kategorie als echtes Kombinationsfeld: vorhandene Namen lassen sich aus der
 *  Browser-Liste anklicken, das Feld bleibt aber frei beschreibbar. Ein <select>
 *  waere hier zu streng, weil neue Kategorien ohne einen zweiten Bedienweg
 *  angelegt werden koennen sollen. */
function kategorienWerte(zusatz) {
  const values = [];
  const gesehen = new Set();
  for (const roh of SC.categories.concat(zusatz || [])) {
    const value = String(roh || "").trim();
    const key = value.toLocaleLowerCase("de");
    if (value && !gesehen.has(key)) {
      gesehen.add(key);
      values.push(value);
    }
  }
  return values;
}

/* ------------------------------------------------------------ Kategorie wählen
 *
 * Vorhandene anklicken, neue tippen — und die neue ist beim naechsten Item gleich
 * anklickbar. Ein freies Textfeld allein macht aus „Helme", „helme" und „Helmr"
 * drei Kategorien, und Items derselben Kategorie konkurrieren miteinander: eine
 * vertippte trennt ein Item still von seiner Gruppe. Ein <select> allein waere zu
 * streng — neue Kategorien muessen ohne zweiten Bedienweg entstehen koennen. */
const KATEGORIE_NEU = "\u0000neu";   // als Kategoriename nicht eingebbar

/* Welche Kategorie-Felder gerade im Tippen stehen — als Schluessel, nicht als
 * DOM-Verweis. Der Modus muss den Neuaufbau ueberleben: der Entwurf speichert
 * 900 ms nach der letzten Aenderung, und das Feld wuerde sonst mitten im Wort
 * wieder zur Auswahlliste. Dieselbe Mechanik wie `offeneHilfen` und `klappZu`. */
const kategorieFrei = new Set();

/** Was in der Lern-Vorschau schon getippt, aber noch nicht uebernommen ist.
 *
 * Eine Kategorie, die in Zeile 1 entsteht, muss in Zeile 2 waehlbar sein —
 * sonst tippt man sie zwanzigmal und beim einundzwanzigsten Mal anders. */
function kategorieZusatz() {
  return [...document.querySelectorAll(".kategorie-wahl")]
    .map((n) => (n.value ? n.value() : "")).filter(Boolean);
}

/** Zieht die Auswahllisten aller Kategorie-Bedienelemente nach. */
function kategorieOptionenAktualisieren() {
  for (const n of document.querySelectorAll(".kategorie-wahl")) {
    if (n.optionenNeu) n.optionenNeu();
  }
}

function kategorieWahl(value, beim_setzen, opts) {
  opts = opts || {};
  const huelle = el("span", {class: "kategorie-wahl"
    + (opts.klasse ? " " + opts.klasse : "")});
  // Woran der Tipp-Modus haengt. Ohne Schluessel gibt es ihn nicht — dann
  // entscheidet allein, ob es etwas zu waehlen gibt.
  const key = opts.key || "";
  let current = String(value || "");
  let gesperrt = false;

  const values = () => kategorienWerte(kategorieZusatz().concat(current));
  const add_finding = (v) => {
    current = v;
    // Ein uebernommener Name steht beim naechsten Aufbau in der Liste — also
    // ist das Tippen hier zu Ende. Bleibt das Feld leer, bleibt es offen:
    // sonst waere ein Vertipper („Enter" auf nichts) ein Rueckwurf in die
    // Auswahl, und man faengt von vorn an.
    if (key && v) kategorieFrei.delete(key);
    beim_setzen(v);
  };

  const auswahlfeld = () => {
    const s = el("select", {title: opts.title
      || "Vorhandene Kategorie wählen — oder unten eine neue anlegen"});
    s.rebuildOptions = () => {
      const alt = current;
      s.replaceChildren(
        el("option", {value: ""}, opts.empty || "— ohne Kategorie —"),
        ...values().map((k) => el("option", {value: k}, k)),
        el("option", {value: KATEGORIE_NEU}, "＋ neue Kategorie …"));
      s.value = alt;
    };
    s.rebuildOptions();
    s.addEventListener("change", () => {
      if (s.value === KATEGORIE_NEU) return tausche(true, "");
      add_finding(s.value);
    });
    return s;
  };

  const textfeld = (vorgabe) => {
    const e = el("input", {value: vorgabe, autocomplete: "off",
      placeholder: opts.platzhalter || "Neue Kategorie",
      title: "Neuen Namen tippen — beim nächsten Item steht er in der Liste"});
    e.addEventListener("change", () => add_finding(e.value.trim()));
    e.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") e.blur();
      // ESC fuehrt zurueck in die Liste, sonst waere das Tippen eine Falltuer:
      // hinein kommt man mit einem Klick, heraus nur ueber einen Umweg.
      if (ev.key === "Escape" && values().length) { ev.stopPropagation(); tausche(false); }
    });
    return e;
  };

  function tausche(frei, vorgabe, merken) {
    if (key && merken !== false) {
      if (frei) kategorieFrei.add(key);
      else kategorieFrei.delete(key);
    }
    const neu = frei ? textfeld(vorgabe === undefined ? current : vorgabe)
                     : auswahlfeld();
    neu.disabled = gesperrt;
    huelle.replaceChildren(neu);
    huelle.value = () => (frei ? neu.value.trim() : neu.value);
    huelle.optionenNeu = frei ? null : neu.rebuildOptions;
    if (frei && merken !== false) neu.focus();
  }

  // **Getippt wird nur, wenn es nichts zu waehlen gibt** — oder wenn der
  // aktuelle Wert (ein Vorschlag der Lern-Vorschau) noch in keiner Liste steht,
  // oder wenn hier vor dem Neuaufbau schon getippt wurde.
  const vorhandene = kategorienWerte(kategorieZusatz());
  tausche(!vorhandene.length
          || (key && kategorieFrei.has(key))
          || (!!current && !vorhandene.some((k) => k === current)),
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
    current = String(v || "");
    const da = kategorienWerte(kategorieZusatz());
    tausche(!!current && !da.some((k) => k === current), current);
    if (huelle.optionenNeu) huelle.optionenNeu();
    beim_setzen(current);
  };
  return huelle;
}

function itemsDerKategorie(category) {
  return SC.items.filter((i) => (i.category || "") === (category || ""))
    .slice().sort((a, b) => a.priority - b.priority || a.name.localeCompare(b.name, "de"));
}

/** Wer belegt welchen Rang — Luecken eingeschlossen.
 *
 * **„Welche Prioritaet ist noch frei" war aus einer Zahl im Feld nicht zu
 * beantworten.** Die Uebersicht zeigte nur die vergebenen; ob P2 belegt ist
 * oder fehlt, sah man erst, wenn man P1, P3, P4 las und selbst nachzaehlte.
 *
 * Liefert `[{prio, namen}]` von 1 bis zum hoechsten belegten Rang plus eins —
 * der naechste freie steht also immer da. Eine getippte P99 spannt das nicht
 * auf hundert Kacheln auf: ueber `PRIO_MAX_ZEIGEN` bleiben nur die belegten. */
const PRIO_MAX_ZEIGEN = 24;

function prioritaetsBelegung(category) {
  const items = itemsDerKategorie(category);
  const belegt = new Map();
  for (const i of items) {
    if (!belegt.has(i.priority)) belegt.set(i.priority, []);
    belegt.get(i.priority).push(i.name);
  }
  const hoechste = items.length ? Math.max(...items.map((i) => i.priority)) : 0;
  if (hoechste + 1 > PRIO_MAX_ZEIGEN) {
    const ranks = [...belegt.keys()].sort((a, b) => a - b);
    // Der naechste freie gehoert dazu — sonst nennt die Uebersicht keinen,
    // und genau den sucht man.
    let frei = 1;
    while (belegt.has(frei)) frei += 1;
    if (!ranks.includes(frei)) ranks.push(frei);
    ranks.sort((a, b) => a - b);
    return ranks.map((p) => ({prio: p, namen: belegt.get(p) || []}));
  }
  const alle = [];
  for (let p = 1; p <= hoechste + 1; p += 1) alle.push({prio: p, namen: belegt.get(p) || []});
  return alle;
}

/** Die Prioritaet, die dieses Item bekaeme, wenn niemand etwas einstellt:
 *  der erste freie Rang seiner Kategorie. */
function naechsteFreiePrioritaet(category, ausser) {
  const vergeben = new Set(itemsDerKategorie(category)
    .filter((i) => i.name !== ausser).map((i) => i.priority));
  let p = 1;
  while (vergeben.has(p)) p += 1;
  return p;
}

/** Teilt sich dieses Item seinen Rang mit einem anderen seiner Kategorie? */
function prioritaetDoppelt(item) {
  if (!item.category) return [];
  return itemsDerKategorie(item.category)
    .filter((i) => i.name !== item.name && i.priority === item.priority)
    .map((i) => i.name);
}

/** Sichtbare Rangfolge statt einer Zahl ohne Zusammenhang. Prioritaeten gelten
 *  innerhalb einer Kategorie; deshalb waere eine globale Liste irrefuehrend. */
function prioritaetsUebersicht(category, aktuellerName) {
  if (!category) {
    return el("p", {class: "hinweis prioritaets-hinweis"},
      "Ohne Kategorie konkurriert dieses Item mit keinem anderen Item.");
  }
  const belegung = prioritaetsBelegung(category);
  return el("div", {class: "prioritaets-uebersicht"},
    el("span", {class: "klein"}, "Rangfolge in „" + category + "“"),
    el("div", {class: "prioritaets-chips"}, belegung.map((r) => {
      const dieses = r.namen.includes(aktuellerName);
      const frei = !r.namen.length;
      return el("span", {
        // Ein freier Rang ist kein Eintrag, sondern eine Luecke — gestrichelt
        // und ohne Namen. Sonst zaehlt man die vergebenen ab, um ihn zu finden.
        class: "prioritaets-chip" + (dieses ? " aktuell" : "")
               + (frei ? " frei" : "") + (r.namen.length > 1 ? " doppelt" : ""),
        title: frei ? "Priorität " + r.prio + " ist frei"
                    : r.namen.join(", ") + " · Priorität " + r.prio
                      + (r.namen.length > 1 ? " — doppelt vergeben" : ""),
      }, "P" + r.prio + " · " + (frei ? "frei" : r.namen.join(", ")));
    })),
    el("small", {class: "eingabe-hilfe"},
      "Kleinere Zahl gewinnt. Zwei Items mit derselben Zahl entscheidet die "
      + "Scan-Reihenfolge — also der Zufall."));
}

function allePrioritaeten() {
  if (!SC.categories.length) return null;
  return el("div", {class: "prioritaeten-alle"},
    el("span", {class: "klein"}, "Bereits gesetzte Prioritäten"),
    SC.categories.map((k) => el("div", {class: "prioritaeten-kategorie"},
      el("b", {}, k),
      el("span", {}, itemsDerKategorie(k).map((i) => "P" + i.priority + " " + i.name).join(" · ")))));
}

/** Noch nicht uebernommene Kategorien gehoeren bereits zur aktuellen Eingabe.
 *  Die Vorschau darf nicht erst nach „Ausgewaehlte uebernehmen" von ihnen
 *  erfahren, sonst muss derselbe freie Text in jeder Zeile neu getippt werden. */
/** Eine in einer Zeile entstandene Kategorie in allen anderen waehlbar machen.
 *
 * Ohne das tippt man dieselbe Kategorie in zwanzig Zeilen — und beim
 * einundzwanzigsten Mal anders. */
function scanReviewKategorienAktualisieren() {
  kategorieOptionenAktualisieren();
}

function scanReviewKategorieAufAuswahl(eingabe) {
  const value = eingabe.value();
  if (!value) return;
  for (const row of document.querySelectorAll(".scan-review-zeile")) {
    const haken = row.querySelector(".scan-review-haken");
    const category = row.querySelector(".scan-review-kategorie");
    if (haken && haken.checked && category && !category.gesperrt()) {
      category.setzen(value);
    }
  }
}

function zahlfeld(beschriftung, value, beim_setzen, extra, help, key) {
  return feld(beschriftung, value, (v) => beim_setzen(Number(v) || 0),
              Object.assign({type: "number"}, extra || {}), help, key);
}

/** Farbwähler mit Hex daneben. Ohne gemessene Farbe bleibt er leer statt eine
 *  zu behaupten — dieselbe Regel wie beim Quadrat in der Punkte-Palette. */
function color_swatch(beschriftung, hex, beim_setzen, help, key) {
  const wahl = el("input", {type: "color", value: hex || "#000000",
                            style: "width:44px;height:28px;padding:2px"});
  const text = el("span", {class: "klein mono"}, hex || "keine Farbe aufgenommen");
  wahl.addEventListener("change", () => beim_setzen(wahl.value.toUpperCase()));
  return el("label", {class: "feld"}, beschriftet(beschriftung, help, key),
    el("div", {class: "reihe"}, wahl, text));
}

/** Ein Schalter — mit ⓘ statt eines Erklaerungsabsatzes darunter.
 *
 * **Erklaerungen gehoeren ins ⓘ, nicht neben das Bedienelement.** Fuenf
 * Absaetze untereinander sind eine Textwand, in der das Bedienelement
 * untergeht; wer die Regel schon kennt, liest sie trotzdem jedes Mal mit. Das
 * ⓘ zeigt sie auf Wunsch, und `offeneHilfen` merkt sich, welche offen sind. */
function schalter(beschriftung, an, beim_setzen, help, key) {
  const box = el("input", {type: "checkbox"});
  box.checked = !!an;
  box.addEventListener("change", () => beim_setzen(box.checked));
  return el("label", {class: "an"}, box, beschriftet(beschriftung, help, key));
}

function selection(beschriftung, values, current, beim_setzen, help, key) {
  const s = el("select");
  for (const w of values) {
    const o = el("option", {value: String(w.value)}, w.text);
    if (String(w.value) === String(current)) o.selected = true;
    s.appendChild(o);
  }
  s.addEventListener("change", () => beim_setzen(s.value));
  return beschriftung ? el("label", {class: "feld"}, beschriftet(beschriftung, help, key), s) : s;
}

/* ---------------------------------------------------- Fokus ueber den Neuaufbau
 *
 * Tipp-Felder melden beim Verlassen, also loest genau der TAB-Sprung den
 * Neuaufbau aus — bis die Bruecke antwortet, steht der Fokus im naechsten Feld,
 * und `replaceChildren()` wirft es weg.
 *
 * Gemerkt wird die POSITION unter den Eingabefeldern des naechsten Elements mit
 * `id`: das Element selbst gibt es danach nicht mehr, und einen eigenen
 * Schluessel je Feld muesste jeder Bauer mitschleppen.
 *
 * **Deshalb traegt jede Maske eine eigene `id`.** Ohne die klettert `closest`
 * bis zur ganzen Spalte, und die Position zaehlt dann ueber ALLE Masken
 * hinweg — bei sechzig Items rund zweihundert Felder. Genau die drei Angaben,
 * die man dort tippt, sortieren die Liste aber um (Kategorie, Prioritaet,
 * Name): nach dem Neuaufbau steht an derselben Position das Feld eines
 * FREMDEN Items, und wer weitertippt, aendert das falsche. Mit der Maske als
 * Anker zaehlt die Position nur noch in ihr, und dort verschiebt sich
 * nichts. */
function fokusMerken() {
  // Ein Umbenennen aendert die Identitaet und damit die id. Wer umbenennt, sagt
  // es vorher; hier wird es einmal eingeloest und danach vergessen.
  const umbenannt = fokusUmbenannt;
  fokusUmbenannt = null;
  const a = document.activeElement;
  if (!a || !["INPUT", "SELECT", "TEXTAREA"].includes(a.tagName)) return null;
  const kasten = a.closest("[id]");
  if (!kasten) return null;
  const felder = [...kasten.querySelectorAll("input, select, textarea")];
  const i = felder.indexOf(a);
  if (i < 0) return null;
  // Zahl- und Farbfelder haben keine Auswahl - dann bleibt nur der Fokus.
  let start = null, end = null;
  try { start = a.selectionStart; end = a.selectionEnd; } catch (e) { /* egal */ }
  const neu = umbenannt && umbenannt.von === kasten.id ? umbenannt.nach : kasten.id;
  // Beide ids: lehnt die Bruecke den neuen Namen ab (schon vergeben), heisst
  // die Maske danach weiter wie vorher — und der Fokus soll trotzdem stehen.
  //
  // Den noch nicht gemeldeten WERT braucht es hier NICHT, und das ist einen
  // Satz wert, weil es nach einer Luecke aussieht: Tipp-Felder melden erst
  // beim Verlassen, ein Neuaufbau mitten in der Eingabe muesste das Getippte
  // also verlieren. Tut er nicht — wird ein fokussiertes, geaendertes `input`
  // aus dem Dokument entfernt, feuert der Browser vorher sein `change`, und
  // der Wert ist gemeldet, bevor der Knoten verschwindet. Ihn hier zusaetzlich
  // zu retten waere nicht nur ueberfluessig, sondern falsch: bei einem
  // abgelehnten Namen (schon vergeben) stuende danach der abgelehnte Text im
  // Feld, waehrend die Daten den alten tragen.
  return {id: neu, alt: kasten.id, i: i, start: start, end: end};
}

/** Vor einem Umbenennen: unter welcher id die Maske danach steht. */
function fokusUmbenennung(von, nach) {
  fokusUmbenannt = von && nach && von !== nach ? {von: von, nach: nach} : null;
}
let fokusUmbenannt = null;

function fokusHerstellen(merk) {
  if (!merk) return;
  const kasten = document.getElementById(merk.id)
              || document.getElementById(merk.alt);
  if (!kasten) return;
  const ziel = [...kasten.querySelectorAll("input, select, textarea")][merk.i];
  if (!ziel) return;
  ziel.focus();
  if (merk.start !== null) {
    try { ziel.setSelectionRange(merk.start, merk.end); } catch (e) { /* egal */ }
  }
}

function segment(values, current, beim_setzen) {
  return el("div", {class: "segment"}, values.map((w) =>
    el("button", {class: w.value === current ? "an" : "", onclick: () => beim_setzen(w.value)},
       w.text)));
}

function ueberschrift(text, help, key) {
  return el("span", {class: "ueberschrift mitinfo"}, text, info(help, key));
}

/* -------------------------------------------------------------------- Brücke */

let S = null;             // letzte Momentaufnahme
let drag = null;        // was gerade gezogen wird
let aktiveAblage = null;  // hervorgehobene Einfügestelle
let offeneFrage = null;
let gewaehltePhase = null; // Loop-Phase; Entf löscht sie wie eine Block-Auswahl
const offeneSonderphasen = new Set(); // leere Start-/Abschlussphasen auf Wunsch

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
    const wechsel = name === "load" || name === "neu";
    if (wechsel) {
      gewaehltePhase = null;
      offeneSonderphasen.clear();
    }
    uebernimm(antwort);
    // **Der offene Reiter muss dem Wechsel folgen.** Scans, Teilen und
    // Werkzeuge lesen alle aus `sequences/<name>/` — ihre Ansicht haengt aber
    // an eigenem Zustand (`SC`, `T`, `W`), den `zeichne()` nicht anfasst. Seit
    // die Auswahl in JEDEM Reiter steht, kann der Wechsel auch von dort
    // kommen, und dann stuenden dort die Slots, Zahlen und Punkte der VORIGEN
    // Sequenz — mit dem Namen der neuen im Kopf. Genau die Sorte stiller
    // Fehlanzeige, bei der man den Fehler in den Daten sucht.
    //
    // Nur bei einem WIRKLICHEN Wechsel: hat die Bruecke stattdessen nach
    // ungespeicherten Aenderungen gefragt, ist noch gar nichts geladen —
    // `fortfahren()` kommt danach ohnehin hier vorbei.
    if (wechsel && S && !S.frage && ansicht !== "editor") setzeAnsicht(ansicht);
  } catch (e) {
    setzeStatus({text: String(e && e.message ? e.message : e), kind: "err"});
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
    setzeStatus({text: String(e && e.message ? e.message : e), kind: "err"});
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
  $("sicht-sequenzen").hidden = neu !== "sequences";
  $("sicht-lauf").hidden = neu !== "lauf";
  $("sicht-config").hidden = neu !== "einstellungen";
  $("sicht-scans").hidden = neu !== "scans";
  $("sicht-teilen").hidden = neu !== "teilen";
  $("sicht-werkzeuge").hidden = neu !== "werkzeuge";
  $("sicht-bericht").hidden = neu !== "bericht";
  // Die Sequenz-Bedienelemente im Kopf gehoeren nur zur Sequenz. Die anderen
  // Reiter bearbeiten andere Dateien und haben ihren eigenen Knopf.
  for (const n of document.querySelectorAll("[data-sequenz]"))
    n.hidden = ["einstellungen", "scans", "teilen", "werkzeuge",
                "bericht"].includes(neu);
  if (neu === "scans") zeichneScans(!SC);
  if (neu === "sequences") zeichneSequenzenliste();
  if (neu === "teilen") zeichneTeilen();
  // Frisch beim Oeffnen: der Bericht der letzten Sitzung beschriebe einen Stand,
  // den es nach einem Speichern nicht mehr gibt.
  if (neu === "werkzeuge") zeichneWerkzeuge(true);
  // Bei jedem Oeffnen frisch: waehrend das Fenster offensteht, schreibt ein
  // Lauf im Hauptprozess weiter in dieselbe CSV.
  if (neu === "bericht") zeichneBericht();
  // Bei jedem Oeffnen frisch von Platte: der Hauptprozess schreibt dieselbe
  // Datei (Debug-Stufen, Import, Factory Reset).
  if (neu === "einstellungen") zeichneEinstellungen(true);
  laufTaktSetzen(neu === "lauf");
}

/* ------------------------------------------------------------------ Zeichnen */

function zeichne() {
  if (!S) return;
  const merk = fokusMerken();
  $("fuss-datei").textContent = S.file || "";
  $("fuss-punkte").textContent = S.points.length + " Punkte";
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

/* Wie oft der Status seit Programmstart geschrieben wurde. Ein verzoegerter
 * Schreiber (s. `briefkastenNachfassen`) merkt sich den Stand und schweigt,
 * wenn inzwischen jemand anders etwas gemeldet hat — eine zwei Sekunden alte
 * Warnung darf keine frische Meldung begraben. */
let statusStand = 0;

function setzeStatus(status) {
  statusStand += 1;
  const n = $("status");
  n.textContent = (status && status.text) || "";
  // Mit Praefix: „info" allein ist die Klasse des ⓘ-Knopfes (13px, rund), und ein
  // Status mit dieser Art bekam dessen Gestalt — ein leerer Kreis neben dem
  // Start-Knopf, den niemand zuordnen konnte.
  n.className = "status art-" + ((status && status.kind) || "info");
}

function zeichneKopf() {
  const s = $("seq-auswahl");
  s.replaceChildren();
  if (!S.sequences.length) s.appendChild(el("option", {value: ""}, "(keine gespeichert)"));
  // Eine frisch angelegte Sequenz steht noch in keiner Datei — ohne diesen Eintrag
  // zeigte die Liste einen fremden Namen an, während man an ihr arbeitet.
  if (S.name && !S.sequences.includes(S.name)) {
    const o = el("option", {value: S.name}, S.name + " (ungespeichert)");
    o.selected = true;
    s.appendChild(o);
  }
  for (const name of S.sequences) {
    const o = el("option", {value: name}, name);
    if (name === S.name) o.selected = true;
    s.appendChild(o);
  }
}

function zeichneSequenz() {
  if (document.activeElement !== $("seq-name")) $("seq-name").value = S.name;
  if (document.activeElement !== $("seq-zyklen")) $("seq-zyklen").value = S.cycles;
  if (document.activeElement !== $("seq-info")) $("seq-info").value = S.beschreibung;
  $("seq-bloecke").textContent = S.phases.reduce((n, p) => n + p.blocks.length, 0);
}

function zeichnePunkte() {
  const filter = $("punkt-filter").value.trim().toLowerCase();
  const liste = S.points.filter((p) => !filter ||
      (p.name + " #" + p.id + " " + p.x + "," + p.y).toLowerCase().includes(filter));
  $("punkte-zahl").textContent = liste.length + "/" + S.points.length;
  const ziel = $("points");
  ziel.replaceChildren();
  if (!S.points.length) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Noch keine Punkte aufgenommen. Im Hauptprozess mit CTRL+ALT+A anlegen."));
    return;
  }
  for (const p of liste) {
    ziel.appendChild(el("div", {
      class: "point", draggable: "true", title: p.source || "",
      ondragstart: (e) => { drag = {kind: "point", point: p.id};
                            e.dataTransfer.effectAllowed = "copy"; },
      ondragend: () => { drag = null; loescheAblage(); },
    },
      // Ohne aufgenommene Farbe bleibt das Feld LEER (nur Rahmen). Vorher stand
      // dort die Linienfarbe als Füllung — das behauptete eine Farbe, die nie
      // gemessen wurde, und der Farb-Trigger hängt an derselben Quelle.
      el("span", {class: "kugel" + (p.color ? "" : " ohne"),
                  title: p.color ? "" : "keine Farbe aufgenommen",
                  style: p.color ? "background:" + p.color : ""}),
      el("span", {class: "nr"}, "#" + p.id),
      el("span", {class: "name"}, p.name),
      el("span", {class: "xy"}, p.x + "," + p.y)));
  }
}

/* --------------------------------------------------------------------- Board */

function zeichnePhasen() {
  const ziel = $("phases");
  ziel.replaceChildren();
  if (!S.phases.some((p) => p.index === gewaehltePhase && p.kind === "loop")) {
    gewaehltePhase = null;
  }
  const sichtbar = S.phases.filter((phase) => phase.kind === "loop" ||
    phase.blocks.length || offeneSonderphasen.has(phase.kind));
  for (const phase of sichtbar) ziel.appendChild(zeichnePhase(phase));

  const verborgen = S.phases.filter((phase) => phase.kind !== "loop" &&
    !phase.blocks.length && !offeneSonderphasen.has(phase.kind));
  const werkzeuge = el("div", {class: "phase phasen-anlegen"},
    el("button", {class: "leerzone", onclick: () => ruf("phase_append")}, "+ Phase"));
  for (const phase of verborgen) {
    const title = phase.kind === "init" ? "+ Startphase (einmal davor)"
                                       : "+ Abschlussphase (einmal danach)";
    werkzeuge.appendChild(el("button", {class: "leerzone", onclick: () => {
      offeneSonderphasen.add(phase.kind);
      zeichnePhasen();
    }}, title));
  }
  ziel.appendChild(werkzeuge);
}

function zeichnePhase(phase) {
  const phaseGewaehlt = phase.kind === "loop" && phase.index === gewaehltePhase;
  const kopf = el("div", {
    class: "phase-kopf " + phase.kind + (phaseGewaehlt ? " gewaehlt" : ""),
    title: phase.kind === "loop" ? "Phase auswählen — Entf löscht sie" : "",
    onclick: (e) => {
      if (phase.kind !== "loop" || e.target.closest("input, button")) return;
      gewaehltePhase = phase.index;
      ruf("selection_clear");
    }});
  // INIT und END tragen keinen frei wählbaren Namen — sie bekommen deshalb auch
  // kein Eingabefeld, das nichts annimmt.
  const sondername = phase.kind === "init" ? "START · einmal davor"
                   : phase.kind === "end" ? "ABSCHLUSS · einmal danach" : phase.name;
  const name = phase.kind === "loop"
    ? el("input", {class: "phase-name wachse", value: phase.name})
    : el("span", {class: "phase-name wachse"}, sondername);
  name.addEventListener("change", () => ruf("phase_set",
    {phase: phase.index, feld: "name", value: name.value}));
  // Kein „×N" als Marke daneben: bei einer Loop-Phase stünde der Wert damit
  // zweimal im Kopf, einmal als Zahl zum Anfassen und einmal als Abzeichen, das
  // sich nicht ändern lässt. Die zugehörige Klasse `.zaehler` ist damit
  // ersatzlos weg — die Sequenzen-Übersicht benutzt ihre eigene (`.zahl`).
  kopf.appendChild(el("div", {class: "reihe"}, name,
    el("span", {class: "klein mono"}, phase.blocks.length + " Schritte")));

  if (phase.kind === "loop") {
    const wdh = el("input", {type: "number", min: "1", value: phase.wiederholungen,
                             title: "Wie oft diese Phase je Zyklus läuft — 1 = einmal"});
    wdh.addEventListener("change", () => ruf("phase_set",
      {phase: phase.index, feld: "wiederholungen", value: Number(wdh.value) || 1}));
    const start = el("input", {value: phase.start, placeholder: "HH:MM",
                               title: "Start erst ab dieser Uhrzeit"});
    start.addEventListener("change", () => ruf("phase_set",
      {phase: phase.index, feld: "start", value: start.value}));
    // Das „×" wandert vor das Feld: ohne die Marke daneben muss die Zahl selbst
    // sagen, was sie ist. Gedämpft, nicht in Akzentfarbe — es beschriftet nur.
    //
    // Und es ist das EINZIGE „×" in dieser Zeile. Der Löschknopf trug einmal
    // eines, was hier schon als Verwechslung notiert war — der Skalieren-Knopf
    // hiess danach aber „Wartezeiten ×" und brachte es an derselben Stelle
    // wieder zurück: ein „×" am ENDE einer Beschriftung liest sich als
    // „wegmachen", nicht als „mal". Er steht jetzt unten bei den Sammel-Aktionen
    // und sagt, was er tut (s. u.); hier bleiben nur die beiden Eigenschaften
    // der Phase.
    //
    // **Beide Zeilen liegen auf DEMSELBEN Raster** (`auto-fit`, min. 118 px —
    // dieselbe Regel wie `knopfpaar` darunter). Vorher war das hier ein
    // `flex` mit fest getippten 70 und 74 px: die Zeile hörte bei rund 60 % auf,
    // während die Knopfzeile darunter über die volle Breite ging. Zwei Zeilen
    // mit verschiedenen Kanten übereinander lesen sich als Versehen, und die
    // beiden Felder waren ausserdem *fast* gleich breit — nah genug, dass es
    // wie ein Rundungsfehler aussieht, statt wie eine Absicht.
    //
    // Damit die halbe Breite auch etwas trägt, bekommen sie ihre Beschriftung:
    // „× 1" und ein leeres „HH:MM" sagten bis dahin nur im Tooltip, was sie
    // sind — und ein Tooltip ist keine Beschriftung.
    kopf.appendChild(el("div", {class: "phase-werkzeug"},
      el("label", {class: "feld"}, "Läufe je Zyklus", wdh),
      el("label", {class: "feld"}, "Start ab Uhrzeit", start)));
  }
  // **Was auf ALLE Blöcke der Phase wirkt, steht beieinander** — und nur, wenn
  // es welche gibt. Das Skalieren stand vorher zwischen Wiederholungen und
  // Startzeit, also zwischen zwei Feldern, die die Phase BESCHREIBEN, während
  // es selbst jeden Block darin ändert. Ohne Blöcke hatte es ausserdem nichts
  // zu tun und stand trotzdem da.
  if (phase.blocks.length) {
    const alle = S.selection.phase === phase.index &&
                 S.selection.rows.length === phase.blocks.length;
    // `knopfpaar`, nicht `reihe` mit `wachse`: für „mehrere Knöpfe teilen sich
    // eine Zeile" gibt es genau eine Antwort im Haus, und sie bricht um, statt
    // die Beschriftung abzuschneiden, sobald eine Spalte unter 118 px fiele.
    const sammel = el("div", {class: "knopfpaar phase-alle"},
      el("button", {class: "btn still",
        onclick: () => ruf("phase_selection", {phase: phase.index})},
        alle ? "Auswahl aufheben" : "Alle Blöcke wählen"));
    if (phase.kind === "loop") {
      sammel.appendChild(el("button", {
        class: "btn still",
        title: "Alle Wartezeiten dieser Phase mit einem Faktor multiplizieren",
        onclick: () => {
          const faktor = window.prompt("Wartezeiten mit welchem Faktor multiplizieren?", "1.0");
          if (faktor !== null) ruf("phase_scale", {phase: phase.index, faktor: faktor});
        }}, "Zeiten skalieren …"));
    }
    kopf.appendChild(sammel);
  }

  const spalte = el("div", {class: "phase"}, kopf);
  phase.blocks.forEach((block, i) => {
    spalte.appendChild(ablage(phase.index, i));
    spalte.appendChild(zeichneKarte(phase, block));
  });
  spalte.appendChild(ablage(phase.index, phase.blocks.length));
  spalte.appendChild(el("button", {
    class: "leerzone",
    onclick: () => ruf("block_append", {phase: phase.index}),
    ondragover: (e) => { if (drag) { e.preventDefault(); markiere(e.currentTarget); } },
    ondragleave: () => loescheAblage(),
    ondrop: (e) => abwerfen(e, phase.index, phase.blocks.length),
  }, phase.blocks.length ? "+ Block" : "leer — Block anlegen oder Punkt herziehen"));
  return spalte;
}

/** Einfügestelle zwischen zwei Karten: nur ein Strich, der aufleuchtet. */
function ablage(phase, row) {
  return el("div", {
    class: "ablage",
    ondragover: (e) => { if (drag) { e.preventDefault(); markiere(e.currentTarget); } },
    ondragleave: () => loescheAblage(),
    ondrop: (e) => abwerfen(e, phase, row),
  });
}

function markiere(n) {
  if (aktiveAblage === n) return;
  loescheAblage();
  aktiveAblage = n;
  n.classList.add("active");
}

function loescheAblage() {
  if (aktiveAblage) aktiveAblage.classList.remove("active");
  aktiveAblage = null;
}

function abwerfen(e, phase, row) {
  e.preventDefault();
  e.stopPropagation();
  loescheAblage();
  const was = drag;
  drag = null;
  if (!was) return;
  if (was.kind === "point") ruf("point_insert", {phase: phase, row: row, point: was.point});
  else ruf("drag", {von_phase: was.phase, from_row: was.row,
                      nach_phase: phase, to_row: row});
}

function zeichneKarte(phase, block) {
  // Der Titel steht in der Kopfzeile, nicht im Leib: dort traegt er die Typfarbe
  // mit und steht NEBEN dem Typ statt darunter — eine Zeile weniger pro Karte,
  // und bei 50 Karten untereinander ist das der Unterschied.
  // Die Farbe des Punkts steht an seiner Stelle (erste Zeile) — bei JEDEM
  // Block, der einen Punkt hat, nicht nur an der Farb-Bedingung. Beim
  // Überfliegen unterscheidet man Karten an der Farbe des Knopfs, nicht an
  // vierstelligen Koordinaten.
  const leib = el("div", {class: "karte-leib"},
    block.rows.map((z, i) => (i === 0 && block.point_color)
      ? el("div", {class: "karte-zeile mit-farbe"},
          el("span", {class: "feldchen", style: "background:" + block.point_color,
                      title: "Farbe des Punkts " + block.point_color}),
          z)
      : el("div", {class: "karte-zeile"}, z)));

  if (block.color_swatch) {
    leib.appendChild(el("div", {class: "karte-farbe"},
      el("span", {class: "feldchen", style: "background:" + block.color_swatch}),
      block.color_text));
  }
  if (block.else_text) {
    // Ein ELSE ohne Bedingung feuert nie — auf der Karte stuende es sonst als
    // Zusage da („sonst: Schritt überspringen"), die nichts einloest.
    leib.appendChild(el("div", {class: "karte-else" + (block.else_greift ? "" : " tot")},
      block.else_text + (block.else_greift ? "" : " · greift nie")));
  }

  // **Kein Auswahl-Häkchen mehr.** Es sagte dasselbe wie der Amber-Ring um die
  // Karte, nur kleiner — und es konnte nichts, was STRG+Klick nicht auch kann
  // („dazu" ist derselbe Befehl). Dazu kam eine Zweideutigkeit über den ganzen
  // Baum: im Scans-Reiter heisst ein Kästchen „gehört dazu" bzw. „ist an", hier
  // hiess es „ist gerade gewählt". Zwei Bedeutungen für dasselbe Bedienelement,
  // und die Karte trug beide Zeichen gleichzeitig. Was die Gesten sind, steht
  // jetzt am Titel der Karte statt in einem Kästchen, das man erst anfassen
  // muss, um es zu verstehen.
  return el("div", {
    class: "karte" + (block.selected ? " gewaehlt" : ""),
    title: "Klick wählt · STRG+Klick nimmt dazu oder heraus · "
           + "SHIFT+Klick wählt bis hierher · Ziehen sortiert um",
    draggable: "true",
    onclick: (e) => {
      gewaehltePhase = null;
      return ruf("select", {
        phase: phase.index, row: block.row,
        modus: e.ctrlKey || e.metaKey ? "dazu" : (e.shiftKey ? "area" : "einzeln")});
    },
    ondragstart: (e) => { drag = {kind: "block", phase: phase.index, row: block.row};
                          e.dataTransfer.effectAllowed = "move"; },
    ondragend: () => { drag = null; loescheAblage(); },
    ondragover: (e) => {
      if (!drag) return;
      e.preventDefault();
      const r = e.currentTarget.getBoundingClientRect();
      const unten = e.clientY > r.top + r.height / 2;
      const strich = unten ? e.currentTarget.nextElementSibling
                           : e.currentTarget.previousElementSibling;
      if (strich && strich.classList.contains("ablage")) markiere(strich);
    },
    ondrop: (e) => {
      const r = e.currentTarget.getBoundingClientRect();
      abwerfen(e, phase.index, block.row + (e.clientY > r.top + r.height / 2 ? 1 : 0));
    },
  },
    el("div", {class: "karte-kopf", style: "background:" + block.color},
      el("span", {class: "karte-typ"}, block.label),
      block.title ? el("span", {class: "karte-titel"}, block.title) : null,
      block.checks ? el("span", {class: "marke-klein", title: "prüft nach der Aktion nach"},
                        "prüft") : null,
      // Der Haltepunkt steht auf der Karte, nicht nur im Inspektor: „wo hält
      // es an" ist die Frage, die man beim Überfliegen von fünfzig Karten hat.
      block.breakpoint ? el("span", {class: "marke-klein halt",
                                     title: "Haltepunkt — der Lauf hält vor diesem Block an"},
                            "⏸ halt") : null,
      block.warnung ? el("span", {class: "marke-klein warn"}, block.warnung) : null,
      el("span", {class: "karte-nr"}, String(block.row + 1).padStart(2, "0"))),
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
 * Der Balken setzt seine Segmente per Inline-Stil (die Breite ist gerechnet).
 * Die Farbe trotzdem aus `:root` zu holen haelt die Palette an einer Stelle;
 * gemerkt, weil `getComputedStyle` sonst je Sequenzkarte dreimal liefe. */
const _phasenfarben = {};
function phasenFarbe(kind) {
  if (!(kind in _phasenfarben)) {
    _phasenfarben[kind] = getComputedStyle(document.documentElement)
      .getPropertyValue("--" + kind).trim() || "#64748B";
  }
  return _phasenfarben[kind];
}

/** INIT / Loop-Phasen / END als Segmente, Breite nach Schrittzahl.
 *
 * Leere Phasen fallen raus: ein Segment der Breite 0 sagt nichts, kostet aber
 * eine Luecke. Die Phasenfarben sind dieselben wie ueberall sonst. */
function phasenBalken(s) {
  const teile = [{n: s.init, color: phasenFarbe("init"), was: "INIT: " + s.init}]
    .concat((s.phases || []).map((p) => ({n: p.schritte, color: phasenFarbe("loop"),
      was: p.name + ": " + p.schritte + " Schritte ×" + p.wiederholungen +
           (p.start ? " ab " + p.start : "")})))
    .concat([{n: s.end, color: phasenFarbe("end"), was: "END: " + s.end}]);
  const summe = teile.reduce((a, t) => a + t.n, 0) || 1;
  return el("div", {class: "balken"}, teile.filter((t) => t.n).map((t) =>
    el("span", {style: "flex:" + t.n / summe + ";background:" + t.color, title: t.was})));
}

async function zeichneSequenzenliste() {
  const ziel = $("sicht-sequenzen");
  const liste = await frage("sequence_list");
  // Zwischen Frage und Antwort kann umgeschaltet worden sein — dann gehoert
  // die Antwort in eine Ansicht, die niemand mehr ansieht.
  if (ansicht !== "sequences") return;
  ziel.replaceChildren();
  if (!liste || !liste.length) {
    // grid-column: sonst stünde der Text in der ersten Spalte des Rasters und
    // wäre auf einem breiten Fenster in die linke Ecke gequetscht.
    ziel.appendChild(el("p", {class: "empty", style: "grid-column:1/-1"},
      "Noch keine Sequenz gespeichert. Im Editor eine anlegen (Neu) oder im " +
      "Hauptprozess mit CTRL+ALT+J eine aufnehmen."));
    return;
  }
  for (const s of liste) ziel.appendChild(seqKarte(s));
}

/** Eine Sequenz als Karte — mit FESTEN Zeilen, damit die Karten sich einmessen.
 *
 * **Jede Karte legt dieselben fünf Zeilen an, auch leere.** Vorher liess eine
 * fehlende Notiz alles darunter hochrutschen: bei drei Karten nebeneinander lag
 * dann der Phasenbalken der einen auf Höhe der Kennzahlen der anderen, und die
 * Übersicht war keine mehr. Mit `subgrid` teilen sich alle Karten einer Reihe
 * die Zeilenhöhen (siehe `.seq-karte` im Stylesheet) — dafür muss jede Zeile
 * aber DA sein, sonst rutscht der Rest wieder eine Stelle nach oben. */
function seqKarte(s) {
  const karte = el("div", {class: "seq-karte" + (s.offen ? " offen" : "") +
                                  (s.defekt ? " defekt" : "")});
  karte.appendChild(el("div", {class: "seq-kopf"},
    el("span", {class: "seq-name"}, s.name),
    s.offen ? el("span", {class: "zahl", style: "color:var(--accent)"}, "offen") : null));

  // Zeile 2: Notiz bzw. Warnung. Eine defekte Datei hat weder Balken noch
  // Kennzahlen — die Zeilen bleiben trotzdem stehen, damit die Nachbarkarten
  // nicht verrutschen.
  const text = el("div", {class: "seq-text"});
  if (s.defekt) {
    text.appendChild(el("p", {class: "seq-warn"},
      "Nicht ladbar — die Datei ist beschädigt oder kein gültiges Sequenz-Format. " +
      "Sie bleibt unangetastet; nachsehen lohnt sich in " + s.file + "."));
  } else {
    if (s.beschreibung) text.appendChild(el("p", {class: "seq-notiz"}, s.beschreibung));
    if (s.warnungen && s.warnungen.length) {
      text.appendChild(el("p", {class: "seq-warn"},
        s.warnungen.length + "× Scan ohne Konfiguration — " + s.warnungen[0] +
        (s.warnungen.length > 1 ? " u. a." : "")));
    }
  }
  karte.appendChild(text);
  karte.appendChild(el("div", {class: "seq-balken"},
    s.defekt ? null : phasenBalken(s)));
  karte.appendChild(el("div", {class: "seq-zahlen"}, s.defekt ? null : [
    el("span", {class: "zahl"}, s.schritte + " Schritte"),
    el("span", {class: "zahl"}, s.phases.length + " Loop-Phasen"),
    el("span", {class: "zahl"}, s.cycles ? s.cycles + " Zyklen" : "endlos")]));

  // Zwei Knöpfe teilen sich gleiche Spalten (`knopfpaar`): „Öffnen" und
  // „Löschen" sind verschieden lang, und zwei verschieden breite Knöpfe
  // nebeneinander lesen sich als zwei Rangstufen. Bei einer defekten Datei
  // bleibt die erste Spalte leer statt zu verschwinden — sonst säße das
  // Löschen dort, wo bei den Nachbarkarten das Öffnen steht.
  karte.appendChild(el("div", {class: "seq-fuss"},
    el("span", {class: "klein mono wachse", title: s.file},
       s.file + " · " + zeitpunkt(s.changed)),
    el("div", {class: "knopfpaar"},
      // Öffnen geht über den vorhandenen Befehl, nicht über einen neuen: dann
      // greift auch die vorhandene Rückfrage bei ungespeicherten Änderungen.
      s.defekt ? el("span", {}) : el("button", {
        class: "btn" + (s.offen ? "" : " haupt"), disabled: s.offen,
        onclick: async () => { await ruf("load", {name: s.name}); setzeAnsicht("editor"); },
      }, s.offen ? "geöffnet" : "Öffnen"),
      el("button", {
        class: "btn gefahr still", disabled: s.offen,
        title: s.offen
          ? "Erst eine andere Sequenz laden — sonst legt der nächste Druck auf "
            + "Speichern den Ordner wieder an."
          : "Räumt den ganzen Sequenzordner nach backups/ weg",
        onclick: () => frageLoeschen(s),
      }, "Löschen"))));
  return karte;
}

/** Die Rückfrage vor dem Löschen — mit dem, was wirklich weggeht.
 *
 * Eine Sequenz ist eine Besitzeinheit: Scans, Vorlagen und gemerkte Bildschirme
 * liegen in ihrem Ordner. „Sequenz löschen?" allein verschwiege den halben
 * Umfang, und der ist genau das, was man hinterher vermisst. */
function frageLoeschen(s) {
  // Das Wort kommt fertig gebeugt aus der Bruecke. Ein angehaengtes "n" ergab
  // "2× Item-Scann" — deutsche Mehrzahl ist keine Regel fuer eine Zeile hier.
  const teile = (s.umfang || []).map((u) => u.count + "× " + u.wort);
  zeigeFrage({
    kind: "seq_loeschen",
    ziel: s.name,
    title: "„" + s.name + "“ löschen?",
    text: "Der ganze Ordner geht weg"
      + (teile.length ? " — samt " + teile.join(", ") + "." : ".")
      + " Er wird nach backups/sequences/ verschoben, nicht gelöscht:"
      + " zurückholen geht von Hand.",
    weiter: "Löschen",
  });
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
 * Nur auf der Flanke (nichts → laeuft), nicht solange etwas laeuft: sonst kaeme
 * man waehrend eines Durchgangs nicht mehr in den Editor zurueck. */
function laufFlanke(active) {
  if (active && !laufLief && ansicht !== "lauf") setzeAnsicht("lauf");
  laufLief = active;
  const knopf = $("btn-lauf");
  knopf.textContent = active ? "■ Stoppen" : "▶ Starten";
  knopf.classList.toggle("gefahr", active);
}

/** Einen Lauf-Befehl abschicken, nachfassen — und melden, wenn niemand zuhört. */
async function laufSchicken(befehl, extra) {
  await ruf("run_command", Object.assign({befehl: befehl}, extra || {}));
  laufNachfassen();
  briefkastenNachfassen();
}

/** Hört überhaupt jemand zu?
 *
 * Der Hauptprozess leert den Briefkasten beim Lesen. Liegt der Befehl nach zwei
 * Sekunden immer noch da, ist keiner da — dann darf im Fenster nicht
 * „gestartet" stehen bleiben.
 *
 * Steht als eigener Baustein da, weil es **jeden** Briefkasten-Befehl betrifft
 * und nicht nur die Laufsteuerung. Bei der Klick-Runde fehlte er, und dort ist
 * die Folge die unangenehmste: die Statuszeile meldete „gestartet", die Ansicht
 * blieb auf „NICHT GESTARTET" — und man steht im Spiel und klickt eine Runde
 * lang gegen niemanden. */
function briefkastenNachfassen() {
  const stamp = statusStand;
  setTimeout(async () => {
    if (!(await frage("command_pending"))) return;
    // Hat inzwischen jemand anders etwas gemeldet, ist diese Warnung zwei
    // Sekunden alt und wuerde die frischere Meldung ueberschreiben.
    if (statusStand !== stamp) return;
    setzeStatus({kind: "warn", text: "Kein Hauptprozess erreichbar — der Befehl " +
                                     "liegt noch und wird nicht nachgeholt."});
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
    setTimeout(async () => laufFlanke(!!((await frage("run_status")) || {}).active), ms);
  }
}

function flankenPuls() {
  setInterval(async () => {
    if (ansicht === "lauf") return;      // dort fragt schon der schnelle Takt
    const z = await frage("run_status");
    laufFlanke(!!(z && z.active));
  }, 2000);
}

/** Sekunden als „2:05“ bzw. „1:23:45“. */
function duration(sekunden) {
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
    el("span", {class: "feldchen" + (rgb ? "" : " empty"),
                style: rgb ? "background:" + hexfarbe(rgb) : ""}),
    el("span", {class: "mono"}, text + (rgb ? " " + rgb.join(",") : " —")));
}

/** Worauf der laufende Block gerade wartet.
 *
 * „seit 12 s" allein beantwortet die Frage nicht: bei 15 s Wartezeit ist das
 * fast geschafft, bei 300 s Timeout gerade erst angefangen.
 *
 * Heruntergezaehlt wird hier, aus den absoluten Zeitstempeln der Statusdatei —
 * mit Restwerten aus dem Worker ruckelte die Anzeige in dessen Sekundentakt. */
function warteKasten(w, jetzt) {
  if (!w) return null;
  const uebrig = w.until ? Math.max(0, w.until - jetzt) : null;
  // „Knapp" meint knapp vor dem TIMEOUT — eine Warnung. Eine ablaufende
  // Wartezeit ist keine: die soll ablaufen, und amber daneben hiesse Alarm, wo
  // alles nach Plan läuft.
  const knapp = w.kind === "color" && uebrig !== null && uebrig <= 5;
  const kasten = el("div", {class: "warten art-" + (w.kind === "color" ? "color" : "zeit") +
                                   (knapp ? " knapp" : "")});

  if (w.kind === "color") {
    const treffer = w.distanz !== null && w.distanz !== undefined &&
                    w.distanz <= w.tolerance;
    // Das Ziel hängt an der Richtung: bei `bis_weg` ist ein Treffer genau das,
    // worauf NICHT gewartet wird — dieselbe Zahl, umgekehrte Bedeutung.
    const erfuellt = w.bis_weg ? !treffer : treffer;
    kasten.appendChild(el("div", {class: "kopf"},
      el("span", {class: "wachse"},
         (w.bis_weg ? "wartet, bis die Farbe weg ist" : "wartet auf die Farbe") +
         " bei (" + w.point.join(",") + ")"),
      el("span", {class: "klein mono"}, "seit " + duration(jetzt - w.since))));
    const angaben = el("div", {class: "wachse"},
      el("div", {class: "farbpaar"},
        farbstueck("target", w.target),
        farbstueck("jetzt", w.actual),
        w.distanz === null || w.distanz === undefined
          ? el("span", {class: "klein"}, "nicht messbar")
          : el("span", {class: "marke-treffer" + (erfuellt ? "" : " daneben")},
               "Δ " + w.distanz + " · " +
               (treffer ? "im Toleranzbereich" : "ausserhalb") + " (" + w.tolerance + ")")));
    // Das Bild steht links neben den Zahlen: es beantwortet die Anschlussfrage
    // („was ist da statt dessen zu sehen?"), nicht dieselbe.
    kasten.appendChild(w.image
      ? el("div", {class: "pixel-kasten"},
          el("div", {class: "live-pixel"},
            el("div", {class: "rahmen"}, el("img", {src: w.image, alt: ""})),
            el("span", {class: "schild"}, "LIVE-PIXEL")),
          angaben)
      : angaben);
  } else {
    kasten.appendChild(el("div", {class: "kopf"},
      el("span", {class: "wachse"}, w.text || "wartet"),
      el("span", {class: "rest"}, uebrig === null ? "" : "noch " + restzeit(uebrig))));
  }

  if (uebrig !== null) {
    kasten.appendChild(balken(jetzt - w.since, w.until - w.since));
  }
  if (w.kind === "color") {
    kasten.appendChild(el("span", {class: "klein"}, uebrig === null
      ? "ohne Timeout — wartet, bis die Farbe stimmt"
      : "Timeout in " + restzeit(uebrig) + " · danach " + (w.danach || "—")));
  } else if (uebrig !== null) {
    kasten.appendChild(el("span", {class: "klein"}, "von " + restzeit(w.total || 0)));
  }
  return kasten;
}

function balken(actual, target) {
  const anteil = target > 0 ? Math.max(0, Math.min(1, actual / target)) : 0;
  return el("div", {class: "fortschritt"}, el("span", {style: "width:" + anteil * 100 + "%"}));
}

/** Alle Phasen des Laufs nebeneinander, die laufende breit.
 *
 * Die Liste kommt aus dem Laufstatus, nicht aus der geoeffneten Sequenz: laufen
 * kann eine ganz andere. Fehlt sie, bleibt es bei der einen laufenden Phase.
 *
 * „Abgeschlossen" gilt innerhalb des laufenden Zyklus — im naechsten Durchgang
 * sind dieselben Loop-Phasen wieder ausstehend. */
function phasenLeiste(z, beendet) {
  const jetzige = z.phase_pos;
  const liste = Array.isArray(z.phases) && z.phases.length
    ? z.phases
    : [{name: z.phase || "—", kind: "loop", wiederholungen: z.wiederholungen || 1}];
  const pos = jetzige === undefined || jetzige === null || !Array.isArray(z.phases)
    ? 0 : jetzige;

  return el("div", {class: "phasen-leiste"}, liste.map((p, i) => {
    // In der Zusammenfassung laeuft nichts mehr: die Stelle, an der Schluss
    // war, ist markiert, nicht "gerade dran". Sonst behauptete die Leiste einen
    // Lauf, den es nicht mehr gibt.
    const running = i === pos && !beendet;
    const kachel = el("div", {
      class: "phasen-kachel" + (running ? " laeuft" : (i < pos ? " fertig" : ""))
             + (beendet && i === pos ? " schluss" : ""),
      "data-art": p.kind || "loop",
    }, el("div", {class: "p-name"}, p.name || "—"));

    if (running) {
      kachel.appendChild(el("div", {class: "reihe"},
        el("span", {class: "klein mono wachse"},
           "Durchlauf " + (z.durchlauf || 1) + " / " + (z.wiederholungen || 1)),
        el("span", {class: "klein mono"},
           "Block " + (z.block || 0) + " / " + (z.blocks || 0))));
      kachel.appendChild(balken(z.durchlauf || 0, z.wiederholungen || 1));
    } else if (beendet && i === pos) {
      // Die Phase, in der Schluss war. „ausstehend" waere hier falsch (sie lief
      // ja) und „abgeschlossen" auch (sie kam nicht durch) — ausser der Lauf
      // ist regulaer bis zum Ende gekommen.
      kachel.appendChild(el("div", {class: "p-lage"},
        (z.reason || "").startsWith("alle Zyklen") ? "abgeschlossen" : "hier war Schluss"));
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
  const z = await frage("run_status");
  laufFlanke(!!(z && z.active));   // auch hier mitfuehren, sonst kippt die Flanke
  if (ansicht !== "lauf") return;
  const ziel = $("sicht-lauf");
  ziel.replaceChildren();
  if (!z || !z.active) {
    if (z && z.countdown) {
      const jetzt = Date.now() / 1000;
      ziel.appendChild(el("div", {class: "lauf-kopf"},
        el("span", {class: "lampe an"}),
        el("span", {class: "lauf-name"}, z.sequence || "(ohne Namen)"),
        el("span", {class: "zahl"}, "startet in " +
          restzeit((z.zielzeit || jetzt) - jetzt))));
      ziel.appendChild(el("p", {class: "hinweis"},
        "Geplant für " + new Date((z.zielzeit || jetzt) * 1000).toLocaleString("de-CH") +
        ". Der Countdown kann hier oder mit dem Stop-Hotkey abgebrochen werden."));
      ziel.appendChild(steuerung(false, z));
      return;
    }
    if (z && z.end) return zeichneAbschluss(ziel, z);
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
    ziel.appendChild(steuerung(false, z));
    return;
  }

  const jetzt = Date.now() / 1000;
  ziel.appendChild(el("div", {class: "lauf-kopf"},
    el("span", {class: "lampe an"}),
    el("span", {class: "lauf-name"}, z.sequence || "(ohne Namen)"),
    el("span", {class: "zahl"},
       "Zyklus " + (z.cycle || 0) + " / " + (z.cycles ? z.cycles : "∞")),
    el("span", {class: "zahl"}, "läuft " + duration(jetzt - (z.start || jetzt)))));

  ziel.appendChild(phasenLeiste(z));

  // Kopfzeile in der Typfarbe des laufenden Blocks — dieselbe Gestalt wie seine
  // Karte im Board, damit man ihn wiedererkennt statt ihn zu lesen. Ohne Typ
  // (alte Statusdatei) bleibt sie neutral statt eine Farbe zu erfinden.
  const counters = z.counters || {};
  ziel.appendChild(el("div", {class: "lauf-mitte"},
    el("div", {class: "tafel mit-kopf"},
      el("div", {class: "karte-kopf",
                 style: "background:" + (z.block_farbe || "#2A3245") +
                        (z.block_farbe ? "" : ";color:var(--text)")},
        el("span", {class: "karte-typ"}, z.block_marke || "AKTUELLER BLOCK"),
        el("span", {class: "karte-titel"}, z.block_title || "(ohne Namen)"),
        el("span", {class: "karte-nr"},
           "Block " + (z.block || 0) + " / " + (z.blocks || 0))),
      el("div", {class: "tafel-leib"},
        el("div", {class: "karte-zeile"}, z.block_label || ""),
        balken(z.block || 0, z.blocks || 1),
        el("span", {class: "klein mono"},
           "seit " + duration(jetzt - (z.block_seit || jetzt))),
        warteKasten(z.waiting, jetzt))),
    el("div", {class: "kachel"},
      [["Klicks", "klicks"], ["Items", "items"], ["Tasten", "tasten"],
       ["Timeouts", "timeouts"], ["Übersprungen", "skipped"],
       ["Neustarts", "neustarts"]].map(([text, key]) =>
        el("div", {}, el("b", {}, String(counters[key] || 0)),
                      el("small", {}, text.toUpperCase()))))));

  if (z.manual) ziel.appendChild(manuelleSteuerung(z.manual));
  ziel.appendChild(steuerung(true, z));
}

/** Der letzte Lauf, nachdem er fertig ist.
 *
 * Der Stand bleibt stehen, bis der naechste Start ihn ueberschreibt — sonst
 * waere die Ansicht genau dann leer, wenn man hinsieht. Dieselben Kacheln wie
 * im Lauf, nur mit festen statt mitlaufenden Zeitangaben. */
function zeichneAbschluss(ziel, z) {
  const counters = z.counters || {};
  // Warum es zu Ende ist, entscheidet die Farbe: durchgelaufen ist gruen,
  // von Hand gestoppt neutral, Notbremse rot. Eine Zusammenfassung, die bei
  // jedem Ausgang gleich aussieht, muss man lesen statt anzusehen.
  const reason = z.reason || "";
  const kind = reason.startsWith("Notbremse") ? "err"
            : reason.startsWith("alle Zyklen") ? "ok" : "warn";
  ziel.appendChild(el("div", {class: "lauf-kopf"},
    el("span", {class: "lampe fertig"}),
    el("span", {class: "lauf-name"}, z.sequence || "(ohne Namen)"),
    el("span", {class: "zahl abschluss-" + kind}, "beendet"),
    el("span", {class: "zahl"}, zeitpunkt(z.end)),
    el("span", {class: "zahl"}, "lief " + duration(z.duration || 0))));

  ziel.appendChild(el("p", {class: "hinweis abschluss-" + kind},
    reason + " · " + (z.gelaufen || 0) + " von " +
    (z.cycles ? z.cycles : "∞") + " Zyklen"));

  if (z.phases && z.phases.length) ziel.appendChild(phasenLeiste(z, true));

  ziel.appendChild(el("div", {class: "kachel"},
    [["Klicks", "klicks"], ["Items", "items"], ["Tasten", "tasten"],
     ["Timeouts", "timeouts"], ["Übersprungen", "skipped"],
     ["Neustarts", "neustarts"]].map(([text, key]) =>
      el("div", {}, el("b", {}, String(counters[key] || 0)),
                    el("small", {}, text.toUpperCase())))));

  ziel.appendChild(steuerung(false, z));
}

/** Der Worker wartet wirklich auf diese Antworten; keine Konsolentaste.
 *
 * Dieselbe Tafel für zwei Anlässe: den manuellen Modus (hält vor JEDEM Block)
 * und einen Haltepunkt (hält vor DIESEM). Der Unterschied ist die dritte
 * Kachel — im Schrittmodus schaltet sie ihn aus („Normal weiter"), am
 * Haltepunkt schaltet sie ihn ein („Ab hier schrittweise"). Das Weiterlaufen
 * heisst am Haltepunkt „Weiter", denn es fragt danach nicht wieder. */
function manuelleSteuerung(m) {
  const knopf = (text, action, klasse) => el("button", {
    class: "btn" + (klasse ? " " + klasse : ""),
    onclick: () => laufSchicken("manuell_aktion", {action: action}),
  }, text);
  const halt = !!m.breakpoint;
  return el("section", {class: "tafel manuell-tafel"},
    el("span", {class: "ueberschrift"}, halt ? "⏸ HALTEPUNKT" : "MANUELLER SCHRITTMODUS"),
    el("b", {}, m.title || "Aktueller Block"),
    el("p", {class: "hinweis"}, m.action || ""),
    el("div", {class: "reihe", style: "gap:8px;flex-wrap:wrap"},
      knopf(halt ? "▶ Weiter" : "▶ Ausführen", "run", "haupt"),
      knopf("↷ Überspringen", "skip"),
      halt ? knopf("Ab hier schrittweise", "step") : knopf("Normal weiter", "continue"),
      knopf("■ Stoppen", "stop", "gefahr")));
}

/** Start/Pause/Stopp.
 *
 * Die Knöpfe führen nichts aus — dieses Fenster hat keinen Zugriff auf
 * `state.stop_event`. Sie legen einen Befehl ab, den der Hauptprozess in
 * derselben Schleife abholt wie seine Hotkeys (`befehl.py`). Deshalb steht das
 * Hotkey-Kürzel weiterhin daneben: es ist derselbe Weg, nur ohne Fensterwechsel.
 */
function steuerung(running, stamp) {
  const knopf = (text, befehl, klasse) => el("button", {
    class: "btn" + (klasse ? " " + klasse : ""),
    onclick: () => laufSchicken(befehl),
  }, text);
  const row = el("div", {class: "reihe", style: "gap:8px;flex-wrap:wrap"},
    !running && !(stamp && stamp.countdown) ? knopf("▶ Starten", "start", "haupt") : null,
    !running && !(stamp && stamp.countdown) ? knopf("▶ Schrittweise", "start_manuell") : null,
    running ? knopf("⏸ Pause", "pause") : null,
    running ? knopf("↷ Warten überspringen", "skip") : null,
    running ? knopf("⏭ Block überspringen", "skip_step") : null,
    running ? knopf("✓ Zyklus abschliessen", "finish") : null,
    running ? knopf("■ Stoppen", "stop", "gefahr") : null,
    !running && stamp && stamp.countdown ? knopf("■ Zeitplan abbrechen", "stop", "gefahr") : null,
    el("span", {class: "klein"},
       running ? "oder CTRL+ALT+S / CTRL+ALT+G im Hauptprozess"
               : "startet die gespeicherte Fassung — ungespeicherte Änderungen " +
                 "werden vorher geschrieben"));
  if (!running && !(stamp && stamp.countdown)) {
    const zeit = el("input", {placeholder: "14:30 oder +30m", autocomplete: "off",
      style: "width:150px"});
    const plan = el("button", {class: "btn", onclick: () => {
      if (!zeit.value.trim()) {
        setzeStatus({kind: "warn", text: "Bitte eine Startzeit eingeben."});
        return;
      }
      laufSchicken("zeitplan", {zeit: zeit.value.trim()});
    }}, "◷ Start planen");
    row.append(el("span", {class: "trenner"}), zeit, plan);
  }
  return row;
}

/* ----------------------------------------------------------------- Inspektor */

function punktListe(current, mitLeer) {
  const values = S.points.map((p) => ({value: p.id, text: "#" + p.id + " " + p.name +
                                                        " (" + p.x + "," + p.y + ")"}));
  if (mitLeer || current === null || current === undefined) {
    values.unshift({value: "", text: "(kein Punkt)"});
  }
  return values;
}

function zeichneInspektor() {
  const ziel = $("inspektor");
  ziel.replaceChildren();
  const b = S.block;
  const selected = S.selection.rows.length;

  $("btn-block-weg").disabled = selected === 0;
  $("btn-block-kopie").disabled = selected === 0;
  if (!b) {
    $("insp-punkt").style.background = "#2A3245";
    $("insp-titel").textContent = selected > 1 ? selected + " BLÖCKE GEWÄHLT" : "KEIN BLOCK";
    ziel.appendChild(el("div", {class: selected > 1 ? "sammel-editor" : "empty"}, selected > 1
      ? zeichneSammelEditor(selected)
      : el("span", {}, "Block anklicken, um ihn zu bearbeiten.", el("br"),
           "Ziehen sortiert um — auch über Phasengrenzen.")));
    return;
  }

  const phase = S.phases[b.phase];
  $("insp-punkt").style.background = b.color;
  $("insp-titel").textContent = "BLOCK " + String(b.row + 1).padStart(2, "0") +
                                " · " + phase.name.toUpperCase();

  // --- Typ ---
  // Jede Kachel traegt ihre Farbe, nicht nur die gewaehlte: damit ist das Raster
  // zugleich die Legende zu den Farben im Board. Ringsum statt als Streifen
  // links, die gewaehlte zusaetzlich ausgefuellt. `border-color` steht im
  // style-Attribut und damit NACH dem `border`-Kurzformat aus .typ-chip —
  // andersherum raeumte die Kurzform die Farbe wieder weg.
  ziel.appendChild(ueberschrift("BLOCK-TYP",
    "Die Farbe der Kachel wiederholt sich auf der Karte im Board — das Raster " +
    "ist zugleich die Legende dazu.", "blocktyp"));
  ziel.appendChild(el("div", {class: "gitter3"}, S.typen.map((t) =>
    el("button", {
      class: "typ-chip",
      style: "border-color:" + t.color +
             (t.key === b.typ
               ? ";background:" + t.color + ";color:#0C0F14;font-weight:600"
               : ""),
      onclick: () => ruf("block_set_type", {typ: t.key}),
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
      ziel.appendChild(feld("Name", b.name, (v) => ruf("block_set", {feld: "name", value: v})));
    }
    ziel.appendChild(el("div", {class: "gitter2"},
      zahlfeld("Wartezeit (s)", b.delay_before,
               (v) => ruf("block_set", {feld: "delay_before", value: v}),
               {step: "0.1", min: "0"}),
      zahlfeld("bis (0 = fest)", b.delay_max,
               (v) => ruf("block_set", {feld: "delay_max", value: v}),
               {step: "0.1", min: "0"})));
  }

  // Der Haltepunkt gilt für JEDEN Typ — auch ein Screenshot kann die Stelle
  // sein, an der man einmal hinsehen will, bevor es weitergeht.
  ziel.appendChild(schalter("Haltepunkt — vor diesem Block anhalten", b.breakpoint,
    (an) => ruf("block_set", {feld: "breakpoint", value: an}),
    "Der Lauf hält hier an und fragt — im Live-Run als Tafel (weiter, überspringen, "
    + "ab hier schrittweise, stoppen), in der Konsole per Taste. CTRL+ALT+G heisst "
    + "„weiter“. In einer Loop-Phase hält er in jedem Zyklus; ausschalten, wenn er "
    + "seinen Dienst getan hat.", "breakpoint"));

  // Ein Warte-Block ohne Trigger beobachtet nichts — dann gibt es auch keine
  // Stelle zu zeigen.
  if (b.typ === "click" || b.typ === "wait_click" ||
      (b.typ === "wait" && b.trigger !== "kein")) baueStelle(ziel, b);
  if (b.typ === "key") {
    ziel.appendChild(feld("Taste", b.key_press,
      (v) => ruf("block_set", {feld: "key_press", value: v}), {placeholder: "enter, space, f1"}));
  }
  baueScan(ziel, b);
  if (b.typ === "screenshot") baueScreenshot(ziel, b);

  // Der Farb-Trigger fragt VOR dem Schritt und steht nur da, wo die Laufzeit ihn
  // auswertet: Klick, Warten und Taste. Scans und Screenshot kehren vorher um.
  //
  // Haengt trotzdem schon eine Bedingung dran, bleibt der Abschnitt sichtbar —
  // sonst waere sie unerreichbar.
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

/** „Sitzt der Punkt da, wo ich denke?" — die Maus faehrt hin und sagt es.
 *
 * Nur bei Bloecken mit Stelle. Das Fenster sieht den Bildschirm nicht; der
 * Hauptprozess bewegt die Maus, misst die Farbe und schreibt das Ergebnis in
 * seine eigene Konsole. */
function baueProbe(ziel, b) {
  // Ein Block hat bis zu drei Stellen — Klick, Prüf-Pixel des Triggers und
  // ELSE-Klick —, und „sitzt das noch?" fragt man bei jeder. Angeboten wird
  // nur, was der Block wirklich hat.
  const stellen = [];
  if (b.point_id !== null && b.point_id !== undefined)
    stellen.push(["klick", "Stelle", b.point_id]);
  if (b.trigger !== "kein" && b.trigger_point !== null && b.trigger_point !== undefined)
    stellen.push(["trigger", "Prüf-Pixel", b.trigger_point]);
  if (b.verify !== "kein" && b.verify_point !== null && b.verify_point !== undefined)
    stellen.push(["verify", "Nachprüf-Pixel", b.verify_point]);
  if (b.else_action === "click" && b.else_point !== null && b.else_point !== undefined)
    stellen.push(["else", "ELSE-Klick", b.else_point]);
  const fuss = el("div", {class: "insp-fuss"});
  fuss.appendChild(el("button", {
    class: "btn breit",
    title: "Führt diesen Block sofort aus — Wartezeit und Farb-Trigger werden übersprungen",
    onclick: () => ruf("block_test"),
  }, "▶ Block einmal testen"));
  for (const [welche, text, point] of stellen) {
    fuss.appendChild(el("button", {
      class: "btn breit",
      onclick: () => ruf("point_show", {welche: welche}),
    }, "◎ " + text + " zeigen (#" + point + ")"));
  }
  ziel.appendChild(fuss);
}

function zeichneSammelEditor(count) {
  const zeitfeld = (beschriftung, feldname, value, gemischt) => {
    const eingabe = el("input", {
      type: "number", min: "0", step: "0.1",
      value: gemischt ? "" : (value === null || value === undefined ? 0 : value),
      placeholder: gemischt ? "verschieden" : "",
    });
    eingabe.addEventListener("change", () => {
      if (eingabe.value.trim() !== "") {
        ruf("selection_set", {feld: feldname, value: Number(eingabe.value)});
      }
    });
    eingabe.addEventListener("keydown", (e) => { if (e.key === "Enter") eingabe.blur(); });
    return el("label", {class: "feld"}, beschriftung, eingabe);
  };
  return el("div", {},
    el("p", {class: "hinweis"},
      count + " Blöcke gemeinsam bearbeiten. Verschieben: ALT+↑/↓, löschen: Entf."),
    el("span", {class: "ueberschrift"}, "WARTEZEIT FÜR AUSWAHL"),
    el("div", {class: "reihe sammel-schnell"}, [0, 0.5, 1].map((sekunden) =>
      el("button", {class: "btn still", onclick: () => ruf("selection_set",
        {feld: "delay_before", value: sekunden})}, String(sekunden).replace(".", ",") + " s"))),
    el("div", {class: "gitter2"},
      zeitfeld("Wartezeit (s)", "delay_before", S.selection.delay_before,
               S.selection.delay_before_gemischt),
      zeitfeld("bis (0 = fest)", "delay_max", S.selection.delay_max,
               S.selection.delay_max_gemischt)),
    el("p", {class: "hinweis"},
      "Nur diese Wartefelder werden gemeinsam geändert; Typ, Ziel und Bedingungen bleiben erhalten."));
}

function baueAktion(ziel, b) {
  const klickt = b.typ === "click" || b.typ === "wait_click";
  const color = b.trigger !== "kein";

  // Der Schluessel bleibt "aktion" und haengt bewusst NICHT am Block-Typ: der
  // wechselt hier ja gerade, und eine Erklaerung, die man aufklappt und die beim
  // ersten Schalten verschwindet, ist keine.
  ziel.appendChild(ueberschrift("AKTION",
    "Diese beiden Schalter SIND der Block-Typ: klicken und/oder auf eine Farbe " +
    "warten. Die Kacheln oben zeigen das Ergebnis automatisch an.", "action"));
  ziel.appendChild(schalter("klickt an der Stelle", klickt, (an) =>
    ruf("block_set_type", {typ: an ? (color ? "wait_click" : "click") : "wait"})));
  ziel.appendChild(schalter("wartet auf eine Farbe", color, (an) => {
    // Bei einem Warte-Block aendert die Farbe den Typ nicht — WARTEN heisst mit
    // und ohne Trigger WARTEN. Bei den Klick-Typen ist sie der Unterschied
    // zwischen KLICK und FARBE+KLICK, laeuft dort also ueber den Typ.
    if (!klickt) ruf("block_trigger", {wahl: an ? "da" : "kein"});
    else ruf("block_set_type", {typ: an ? "wait_click" : "click"});
  }));
}

function baueStelle(ziel, b) {
  // Beides an der Ueberschrift: der Zusatz fuer WARTEN-Bloecke erklaert, warum
  // hier ueberhaupt eine Stelle steht, obwohl nicht geklickt wird.
  ziel.appendChild(ueberschrift(b.typ === "wait" ? "BEOBACHTETE STELLE" : "KLICK-POSITION",
    "X und Y verschieben den Punkt selbst. Jeder Block, der ihn benutzt, zeigt " +
    "danach auf die neue Stelle — die Sequenz speichert keine eigenen Koordinaten. " +
    "Mit ‚Stelle mit der Maus setzen‘ wechselst du danach ins Spiel, bewegst die " +
    "Maus an die Stelle und drückst ENTER. Die Farbe wird mitgemessen; ESC bricht ab." +
    (b.typ === "wait" ? " Dieser Block klickt übrigens nicht: die Stelle wird nur " +
     "beobachtet. Zum Klicken oben den Typ KLICK oder FARBE+KLICK wählen." : ""),
    "position"));
  if (!S.points.length && b.point_id === null) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Keine Punkte vorhanden. Im Hauptprozess mit CTRL+ALT+A aufnehmen — " +
      "oder hier eine Stelle eintragen, dann entsteht ein Punkt dafür."));
  } else {
    ziel.appendChild(selection("Punkt", punktListe(b.point_id), b.point_id === null ? "" : b.point_id,
      (v) => v && ruf("block_point", {point: Number(v)})));
  }
  // Alles, was dem Punkt gehört, steht beieinander: welcher, wie er heisst,
  // welche Farbe er trägt, wo er liegt.
  if (b.point_id !== null && b.point_id !== undefined) {
    const p = S.points.find((q) => q.id === b.point_id);
    ziel.appendChild(feld("Name des Punkts", b.name,
      (v) => ruf("point_set", {point: b.point_id, feld: "name", value: v}), null,
      "Der Name gehört dem Punkt, nicht diesem Block: er ändert sich überall, " +
      "wo derselbe Punkt benutzt wird.", "punktname"));
    ziel.appendChild(color_swatch("Farbe des Punkts", p && p.color,
      (hex) => ruf("point_set", {point: b.point_id, feld: "color", value: hex}),
      "Beim Aufnehmen gemessen. Ein Farb-Trigger prüft GENAU diese Farbe — wer " +
      "sie hier ändert, ändert mit, worauf gewartet wird.", "punktfarbe"));
    // Zustand, kein ⓘ: WER den Punkt sonst noch benutzt, sieht man sonst erst,
    // wenn ein anderer Block woanders hinklickt. Und der Rueckweg steht dabei:
    // ein eigener Punkt fuer diesen Block, die anderen bleiben, wo sie sind.
    if (b.point_others && b.point_others.length) {
      ziel.appendChild(el("p", {class: "hinweis"},
        "Punkt #" + b.point_id + " wird auch benutzt von: " + b.point_others.join(", ")));
      ziel.appendChild(el("button", {
        class: "btn breit",
        title: "Dieser Block bekommt eine Kopie des Punkts; die anderen Blöcke behalten #"
               + b.point_id + ". Danach lässt sich seine Stelle ändern, ohne die anderen zu verstellen.",
        onclick: () => ruf("point_detach"),
      }, "⧉ Eigenen Punkt für diesen Block"));
    }
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
    onclick: () => mitWarten("ruf", "point_capture"),
  }, "✛ Stelle mit der Maus setzen"));
  // Hier stand ein Schalter "nur warten (kein Klick)". Er setzte `wait_only` —
  // also genau das, was der Typ-Chip WARTEN oben schon setzt: ein Zustand, zwei
  // Bedienelemente. Das rächte sich, weil er sich bei "warten" selbst ausblendete
  // und damit eine Falltuer war. Die Chips koennen alles, was er konnte:
  // WARTEN hin, FARBE+KLICK verlustfrei zurueck (der Trigger bleibt), KLICK
  // zurueck ohne Trigger — und das ist keine Nebenwirkung, sondern die Bedeutung
  // von KLICK. Was seine Beschriftung erklaerte, steht am ⓘ der Ueberschrift.
  if (b.scroll) {
    ziel.appendChild(zahlfeld("Mausrad (Stufen, 0 = kein Rad)", b.scroll,
      (v) => ruf("block_set", {feld: "scroll", value: v}), {step: "1"}));
  }
}

function setzeStelle(b, x, y) {
  if (b.point_id === null || b.point_id === undefined) {
    ruf("point_create", {x: x, y: y});
  } else {
    // Zwei Felder, ein Punkt: nur die geänderte Achse schicken.
    if (x !== b.x) ruf("point_set", {point: b.point_id, feld: "x", value: x});
    if (y !== b.y) ruf("point_set", {point: b.point_id, feld: "y", value: y});
  }
}

function baueScan(ziel, b) {
  const scans = {item_scan: ["ITEM-SCAN", "item_scan"], icon_scan: ["ICON-SCAN", "icon_scan"],
                 boss_scan: ["BOSS-SCAN", "boss_scan"], boss_watcher: ["BOSS-WATCHER", "boss_watcher"]};
  const eintrag = scans[b.typ];
  if (!eintrag) return;
  const [title, feldname] = eintrag;
  const existing = (S.scan_namen && S.scan_namen[b.typ]) || [];
  const value = b[feldname];
  ziel.appendChild(ueberschrift(title));

  if (!existing.length && !value) {
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
  const values = [{value: "", text: "(keine)"}].concat(existing.map(
    (n) => ({value: n, text: n})));
  if (value && !existing.includes(value)) values.push({value: value, text: value + " — fehlt"});
  ziel.appendChild(selection("Konfiguration", values, value,
    (v) => ruf("block_set", {feld: feldname, value: v}),
    "Im Item-/Boss-/Icon-Editor angelegt (Hauptprozess, CTRL+ALT+N). " +
    "Ohne Konfiguration wird nicht gespeichert.", "scan"));
  if (b.typ === "item_scan") {
    ziel.appendChild(selection("Modus", S.scan_modi.map((m) => ({value: m, text: m})),
      b.item_scan_mode, (v) => ruf("block_set", {feld: "item_scan_mode", value: v})));
  }
}

function baueScreenshot(ziel, b) {
  ziel.appendChild(ueberschrift("SCREENSHOT"));
  const hatBereich = !!b.screenshot_region;
  ziel.appendChild(schalter("Bereich statt Vollbild", hatBereich,
    (an) => ruf("block_area", {values: an ? (b.screenshot_region || [0, 0, 100, 100]) : null})));
  if (!hatBereich) return;
  const r = b.screenshot_region.slice();
  const setze = (i) => (v) => { r[i] = v; ruf("block_area", {values: r}); };

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
                 kind: "warn"});
    mitWarten("ruf", "area_capture");
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
const RICHTUNG_AUS = {value: "kein", text: "kein"};
const RICHTUNGEN = [{value: "da", text: "bis Farbe DA"}, {value: "weg", text: "bis Farbe WEG"}];

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
    ziel.appendChild(selection("Geprüfte Stelle", punktListe(b.trigger_point), b.trigger_point,
      (v) => v && ruf("block_trigger", {wahl: b.trigger, point: Number(v)}),
      "Farbe und Stelle kommen aus dem Punkt. Soll an derselben Stelle auf eine " +
      "andere Farbe geprüft werden, ist das ein eigener Punkt.", "trigger"));
    ziel.appendChild(schalter("nur prüfen, nicht warten", b.trigger_check,
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
    ziel.appendChild(selection("Geprüfte Stelle", punktListe(b.verify_point), b.verify_point,
      (v) => v && ruf("block_trigger", {welche: "verify", wahl: b.verify, point: Number(v)})));
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

const ELSE_BESCHREIBUNGEN = {
  skip: "Nur diesen Schritt überspringen.",
  skip_cycle: "Den laufenden Zyklus abbrechen und den nächsten beginnen.",
  restart: "Die Sequenz von vorn beginnen.",
  click: "Stattdessen einen anderen Punkt klicken.",
  key: "Stattdessen eine Taste drücken.",
};

function baueElse(ziel, b) {
  // Kein Ausloeser, kein Abschnitt: an einem reinen Klick (Taste, Warten,
  // Screenshot, Boss-Watcher) kann ELSE nie feuern.
  //
  // Ist trotzdem eine Aktion gesetzt (Trigger entfernt, Typ umgestellt, Import),
  // bleibt der Abschnitt stehen — sonst stuende das ELSE unsichtbar in der Datei
  // und waere nicht mehr loszuwerden.
  if (!b.else_greift && !b.else_action) return;
  // Kein ELSE heisst: keine Kachel markiert. Eine Kachel „(keine)" saehe aus wie
  // eine sechste Aktion, obwohl sie die Abwesenheit von allen ist.
  //
  // Der Rueckweg ist die markierte Kachel selbst — und weil man ein Umschalten
  // nicht sieht, steht es im Hinweis darunter und im Tooltip der Kachel.
  const auswirkung = b.else_action
    ? ELSE_BESCHREIBUNGEN[b.else_action]
    : ohneElseText();
  ziel.appendChild(ueberschrift("ELSE — WENN DIE BEDINGUNG NICHT GREIFT",
    "ELSE ist ein „stattdessen“, kein „zusätzlich“: greift es, entfällt die " +
    "eigene Aktion des Schritts. " + auswirkung +
    (b.else_action ? " Ein zweiter Klick auf die markierte Kachel hebt ELSE wieder auf." : ""),
    "else"));
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
  ziel.appendChild(el("div", {class: "gitter3"}, S.else_actions.map((a) =>
    el("button", {
      // Eigene Klasse trotz gleicher Form: eine Typ-Kachel schaltet den Block-Typ,
      // eine ELSE-Kachel die Ersatzaktion. Wer eine davon später anders gestalten
      // will, soll nicht beide erwischen.
      class: "typ-chip else-chip" + (a === b.else_action ? " an" : ""),
      title: ELSE_BESCHREIBUNGEN[a] +
             (a === b.else_action ? " Nochmal klicken = kein ELSE." : ""),
      // Dieselbe Kachel nochmal: das leere Kommando entfernt die Aktion. Eine
      // andere Kachel wechselt sie wie gewohnt.
      onclick: () => ruf("block_else", {action: a === b.else_action ? "" : a}),
    }, a))));
  if (b.else_action === "click") {
    ziel.appendChild(selection("ELSE-Punkt", punktListe(b.else_point), b.else_point,
      (v) => v && ruf("block_else", {action: "click", point: Number(v)})));
  }
  if (b.else_action === "key") {
    ziel.appendChild(feld("ELSE-Taste", b.else_taste,
      (v) => ruf("block_else", {action: "key", taste: v})));
  }
}

/* -------------------------------------------------------------------- Dialog */

function zeigeFrage(frage) {
  // Titel, Text und Knopfbeschriftungen kommen aus der Brücke: die Fälle
  // unterscheiden sich zu sehr, um sie hier zusammenzusetzen (bei „ausserhalb
  // geändert" gibt es nichts zu verwerfen und nichts vorher zu speichern).
  offeneFrage = frage;
  $("dialog-titel").textContent = frage.title || "Rückfrage";
  $("dialog-text").textContent = frage.text || "";
  $("dialog-weg").textContent = frage.weiter || "Weiter";
  $("dialog-save").hidden = !frage.save;
  $("schleier").hidden = false;
}

function schliesseFrage() {
  offeneFrage = null;
  $("schleier").hidden = true;
}

/* Die lokale Variable hiess `frage` und verdeckte damit den gleichnamigen
 * Bruecken-Helfer — solange hier nur `ruf()` vorkam, fiel das nicht auf. Sie
 * heisst jetzt `offen`, damit der fragende Kanal von hier aus erreichbar ist. */
async function fortfahren(verwerfen) {
  const offen = offeneFrage;
  schliesseFrage();
  if (!offen) return;
  // Löschen geht über den fragenden Kanal: es ändert Dateien, nicht die offene
  // Sequenz — eine Momentaufnahme als Antwort zerschösse den Editor-Zustand.
  // Steht vorn, weil es weder speichern noch laden will.
  if (offen.kind === "seq_loeschen") {
    const antwort = await frage("sequence_delete", {name: offen.ziel});
    if (antwort) setzeStatus({text: antwort.message, kind: antwort.ok ? "ok" : "warn"});
    return zeichneSequenzenliste();
  }
  if (offen.kind === "save") return ruf("save", {erzwingen: true});
  if (!verwerfen) await ruf("save");
  if (offen.kind === "load") await ruf("load", {name: offen.ziel, verwerfen: true});
  else await ruf("new", {verwerfen: true});
}

/* ------------------------------------------------------------ Ansicht: Scans */

/* Slots, Items und Item-Scans auf einem eingefrorenen Screenshot. Eigener
 * Zustand neben `S`: der Reiter bearbeitet andere Dateien (slots.json,
 * items.json, item_scans/).
 *
 * Gezeichnet wird ein <img> mit einem <svg> darueber; dessen viewBox steht in
 * BILD-Pixeln, also muessen nur Strichstaerken und Schriftgroessen gegen den
 * Zoom gerechnet werden. */
let SC = null;
/* Welche Liste links offen ist — `null` heisst „noch nicht entschieden", dann
 * gilt `scanListeAktiv()`.
 *
 * Mit offenem Scan sind die Items die Arbeit: der Scan ist die Klammer, nicht
 * der Inhalt. Dieselbe Regel wie bei `klappZu` — die Vorgabe gilt, bis jemand
 * einen Reiter anfasst. */
let scanListe = null;
/* Wohin der Reiter nach dem naechsten `scan_open` springt. `null` heisst
 * „zurueck auf die Vorgabe" — bei offenem Scan sind das seine Items, also das,
 * weswegen man ihn geoeffnet hat. Wer ihn aus der Scan-Liste heraus oeffnet,
 * bleibt dort stehen: sonst verschwindet die Maske, die sich gerade
 * aufgeklappt hat, samt ihren Einstellungen. */
let scanReiterNachOeffnen = null;
/* Was zuletzt gewaehlt war (Art + Name). Ein Klick INS BILD waehlt einen Slot,
 * und der steht in der Slot-Liste — ohne das Nachziehen passiert nach dem
 * Klick sichtbar nichts, weil gerade die Item-Liste offen ist. Nur beim
 * WECHSEL, sonst kaeme man aus der Liste nicht mehr heraus. */
let scanWahlZuletzt = null;
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
 * nichts entschieden" — dann gilt `klappVorgabe()`; sobald jemand einen Kopf
 * anfasst, steht dort seine Entscheidung und die Automatik schweigt.
 *
 * Reiner Oberflaechenzustand, deshalb hier und nicht in der Bruecke. */
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
 * Rueckgaengig-Stapel (`counts`). */
let scanSchubZeit = 0;

/* Die Reihenfolge ist die Rangfolge und dieselbe wie in `MODI` (ein Test haelt
 * beide Zug um Zug gegeneinander). „Slots finden" steht direkt hinter
 * „Auswaehlen", weil das Automatische der Normalfall ist und das Aufziehen von
 * Hand der Ausweichweg. */
/* Die Zustandsfarben aus dem Stylesheet, damit SVG-Text und Listen dieselbe
 * Quelle benutzen wie Umriss und Fuellung. `fill` im SVG nimmt kein
 * `var(--x)` aus einer fremden Regel entgegen, also einmal auslesen. */
const SLOT_FARBE = (() => {
  const s = getComputedStyle(document.documentElement);
  return {treffer: s.getPropertyValue("--slot-ok").trim(),
          fremditem: s.getPropertyValue("--slot-fremd").trim(),
          empty: s.getPropertyValue("--slot-offen").trim()};
})();

const SCAN_MODI = [
  {key: "wahl", text: "Auswählen", taste: "V", haupt: true,
   help: "Slot anklicken — daneben zieht ein Rechteck um mehrere"},
  {key: "finden", text: "Slots finden", taste: "G", haupt: true,
   help: "Bereich aufziehen, dann leeren Slot-Hintergrund anklicken"},
  {key: "slot", text: "Neuer Slot", taste: "S", haupt: true,
   help: "zwei Ecken anklicken — wenn Finden nicht greift"},
  {key: "messen", text: "Hintergrundfarbe", taste: "F", help: "Stelle im Slot anklicken"},
  {key: "klick", text: "Klickpunkt", taste: "K", help: "wohin geklickt wird"},
  {key: "area", text: "Bereich", taste: "B", help: "zwei Ecken um den Teil, der zählt"},
];

async function zeichneScans(frisch) {
  // Nach Laden oder Umbenennen einer Sequenz darf die Scan-Aufnahme der zuvor
  // offenen Sequenz nicht weiter im Reiter stehen. Der Name ist ein billiger,
  // eindeutiger Besitzerwechsel und erzwingt dann eine frische Aufnahme.
  if (SC && S && SC.sequence !== S.name) frisch = true;
  if (frisch || !SC) {
    const antwort = await frage("scan_data");
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
  scanReiterFolgen();
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
  // Frisch von Platte heisst frisch sortiert — dort gibt es keine Zeile, in
  // der jemand gerade tippt.
  if (name === "scan_reload" || name === "scan_learn_preview_apply")
    scanOrdnungVergessen();
  // **Einen Scan zu oeffnen ist ein Wechsel des Zusammenhangs.** Danach gilt
  // wieder die Vorgabe — und die sind bei offenem Scan seine Items, also das,
  // weswegen man ihn geoeffnet hat. Vorher landete man auf der Scan-Liste und
  // sah den Namen, den man gerade angeklickt hatte, ein zweites Mal.
  if (name === "scan_open") {
    scanListe = scanReiterNachOeffnen;
    scanReiterNachOeffnen = null;
    scanOrdnungVergessen();
  }
  if (name === "scan_screenshot")
    scanAssistentSchritt = SC.schritte[1].fertig ? 3 : 2;
  else if (name === "scan_learn_preview" || name === "scan_recognize")
    scanAssistentSchritt = 3;
  else if (name === "scan_mode_set" && daten &&
           (daten.modus === "finden" || daten.modus === "slot"))
    scanAssistentSchritt = 2;
  await zeichneScans();
  scanAutoSpeichernPlanen(name);
}

function scanAutoSpeichernPlanen(ursache) {
  clearTimeout(scanAutoSaveTimer);
  if (!SC || !SC.dirty || ursache === "scan_save") return;
  const stamp = $("scan-speicherstand");
  if (stamp) { stamp.textContent = "Entwurf wird gespeichert …"; stamp.classList.add("offen"); }
  scanAutoSaveTimer = setTimeout(async () => {
    const antwort = await frage("scan_save");
    if (!antwort) return;
    SC = antwort;
    await zeichneScans();
  }, 900);
}

function scanCanvasWerkzeuge() {
  const bereit = scanKonfigurationOffen();
  const sicht = $("sicht-scans");
  sicht.classList.toggle("gefuehrt", scanGefuehrt);
  sicht.classList.toggle("hat-bild", fotoDa());
  $("scan-frei").textContent = scanGefuehrt ? "Alle Werkzeuge" : "Nur Assistent";
  document.querySelectorAll("[data-scan-tool]").forEach((knopf) => {
    knopf.classList.toggle("an", SC.modus === knopf.dataset.scanTool);
    knopf.disabled = (!bereit || !SC.pillow) && knopf.dataset.scanTool !== "wahl";
  });
  const modus = SCAN_MODI.find((m) => m.key === SC.modus);
  const erk = {region: "Region aufziehen",
               action: scanArt === "item" ? "Bestätigungsklick setzen"
                                          : "Klickpunkt setzen"}[SC.modus];
  $("scan-werkzeugstand").textContent = !bereit
    ? "Zuerst einen Scan anlegen oder auswählen"
    : SC.modus === "wahl"
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
  const stamp = $("scan-speicherstand");
  stamp.textContent = SC.dirty ? "Wird gespeichert …" : "✓ Gespeichert";
  stamp.classList.toggle("offen", !!SC.dirty);
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
    el("span", {class: "kennzahl", style: "color:var(--ok)"}, e.detected + " erkannt"),
    el("span", {class: "kennzahl", style: "color:var(--accent)"}, e.unbekannt + " unbekannt"),
    el("span", {class: "wachse"})
  );
  if (e.unbekannt) ziel.appendChild(el("button", {class: "btn still",
    onclick: () => scanErgebnisNaechster("unbekannt_slots")}, "Nächsten unbekannten zeigen"));
}

function scanErgebnisNaechster(feld) {
  const namen = (SC.ergebnis && SC.ergebnis[feld]) || [];
  if (!namen.length) return;
  const current = namen.indexOf(SC.wahl.name);
  const name = namen[(current + 1) % namen.length];
  rufScan("scan_select", {kind: "slot", name: name});
}

/** Gibt es ein echtes Bild — oder nur die aus den Slots gerechnete Flaeche? */
function fotoDa() { return !!(SC && SC.photo && SC.photo.image); }

/** Hat die aktuelle Art ein eindeutiges Ziel für Bild, Slots und Regionen? */
function scanKonfigurationOffen() {
  return !!(SC && SC.aufnahme_bereit && SC.aufnahme_bereit[scanArt]);
}

/** Holt das Bild nur, wenn es ein neues gibt — es ist der grosse Brocken. */
async function scanBildPflegen() {
  const image = $("scan-bild");
  const empty = $("scan-leer");
  if (!SC.photo) {
    $("scan-flaeche").hidden = true;
    $("scan-ohne-bild").hidden = true;
    empty.hidden = false;
    empty.textContent = !scanKonfigurationOffen()
      ? "Zuerst oben einen Scan anlegen oder auswählen. Danach kann ein Screenshot aufgenommen werden."
      : SC.pillow
      ? "Noch kein Bild. „Screenshot aufnehmen“ friert den Bildschirm ein — darauf werden die Slots aufgezogen."
      : "Ohne Pillow gibt es kein Bild (pip install pillow). Slots lassen sich dann nur über die Zahlenfelder rechts setzen.";
    return;
  }
  $("scan-flaeche").hidden = false;
  empty.hidden = true;
  // Ohne Bild bleibt die Flaeche leer, aber sie hat die Groesse und die Lage
  // der Slots — man sieht also, was der Scan hat, und kann es anfassen.
  $("scan-flaeche").classList.toggle("ohne-bild", !fotoDa());
  $("scan-ohne-bild").hidden = fotoDa();
  // Woran man merkt, dass eine ANDERE Flaeche dasteht: beim Bild der
  // Zeitstempel, sonst ihre Groesse. Ohne diese Marke passte entweder gar
  // nichts mehr ein (Zoom vom vorigen Scan) oder bei jedem Neuzeichnen wieder,
  // was jedes Hineinzoomen sofort zuruecksetzte.
  const marke = fotoDa() ? SC.photo.stamp
                         : -(SC.photo.width * 100000 + SC.photo.height);
  if (marke !== scanFotoStand) {
    scanFotoStand = marke;
    if (fotoDa()) {
      const url = await frage("scan_image");
      if (url) image.src = url;
    } else {
      image.removeAttribute("src");
    }
    scanEinpassen();
  }
  $("scan-groesse").textContent = fotoDa()
    ? SC.photo.width + "×" + SC.photo.height
    : "kein Bild";
}

function scanEinpassen() {
  if (!SC || !SC.photo) return;
  const platz = $("scan-buehne").clientWidth - 24;
  // Ein Bild wird nie vergroessert — jedes Pixel darueber waere erfunden, und
  // gemessen wird ohnehin im Original. Die aus den Slots gerechnete Flaeche hat
  // keine Pixel, die man faelschen koennte: sie darf die Buehne fuellen, sonst
  // haengt ein Inventar von 300 px verloren in einer Ecke.
  const grenze = fotoDa() ? 1 : 4;
  scanZoom = Math.max(0.05, Math.min(grenze, platz / SC.photo.width));
  scanZoomHand = false;
  scanZoomAnwenden();
}

function scanZoomAnwenden() {
  if (!SC || !SC.photo) return;
  const f = $("scan-flaeche");
  f.style.width = Math.round(SC.photo.width * scanZoom) + "px";
  // Die Hoehe kommt sonst vom Bild. Ohne eines waere sie 0, und die Flaeche
  // haette weder Platz fuer die Slots noch etwas zum Anklicken.
  f.style.height = fotoDa() ? "" : Math.round(SC.photo.height * scanZoom) + "px";
  $("scan-zoom").textContent = Math.round(scanZoom * 100) + " %";
  scanOverlay();
}

/* ---- Umrechnung: Bildschirm <-> Bild. Die einzige Stelle, die das darf. ---- */

function scanZuBild(x, y) {
  const f = SC.photo;
  return [(x - f.left) * f.scale, (y - f.top) * f.scale];
}

function scanZuSchirm(bx, by) {
  const f = SC.photo;
  return [Math.round(f.left + bx / f.scale), Math.round(f.top + by / f.scale)];
}

function scanWerkzeuge() {
  $("scan-sequenz").textContent = SC.sequence || "— keine Sequenz —";
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
  const bereit = scanKonfigurationOffen();
  $("scan-buehne").classList.toggle("such-aktiv", SC.modus === "finden");
  const namensfeld = $("scan-name");
  namensfeld.value = offen ? offen.name : "";
  namensfeld.disabled = !offen;
  $("scan-umfang").textContent = offen
    ? offen.slots.length + " Slots · " + offen.items.length + " Items"
    : SC.slots.length + " Slots · " + SC.items.length + " Items";

  const ziel = $("scan-modi");
  ziel.replaceChildren();
  for (const m of SCAN_MODI) {
    const an = SC.modus === m.key;
    ziel.appendChild(el("button", {
      class: "scan-modus" + (an ? " an" : ""),
      disabled: !bereit,
      // Ein Umschalten sieht man einem Bedienelement nicht an — dieselbe Regel
      // wie bei der ELSE-Kachel im Inspektor. Es steht deshalb im Tooltip der
      // markierten Kachel UND im Hinweis unter dem Raster.
      title: an && m.key !== "wahl"
        ? "Nochmal klicken = zurück zum Auswählen" : "",
      onclick: () => rufScan("scan_mode_set", {modus: m.key, kind: scanArt}),
    },
      el("span", {}, m.text),
      el("span", {class: "taste"}, m.taste),
      el("span", {class: "klein"}, m.help)));
  }
  $("scan-modi-zurueck").hidden = SC.modus === "wahl";
  // **Was man ZWISCHENDURCH tut, braucht keinen Modus** — und die Erklaerung
  // dazu keinen eigenen Absatz. Sie stand als vier Zeilen Text unter den
  // Kacheln; das ⓘ zeigt sie auf Wunsch und merkt sich, ob es offen war.
  $("scan-foto-info").replaceChildren("Woher das Bild kommt", info(
    "Items werden aus diesem eingefrorenen Bild gelernt. Beim Lauf wird "
    + "dasselbe Fenster mit derselben Aufnahmemethode neu aufgenommen; die "
    + "Slots folgen seiner Position automatisch.", "aufnahme"));
  $("scan-modi-direkt").replaceChildren("Ohne Moduswechsel", info(
    "ALT+Klick misst den Hintergrund eines Slots, Doppelklick setzt seinen "
    + "Klickpunkt — beides wählt ihn gleich mit aus. Ein gewählter Slot lässt "
    + "sich mit der Maus ziehen oder mit den Pfeiltasten verschieben "
    + "(SHIFT = 10 px).", "direkt"));
  const modus = SCAN_MODI.find((m) => m.key === SC.modus);
  $("scan-modus-kurz").textContent = modus ? modus.text : "";
  klappPflegen();
  scanSchritte();
  $("scan-foto").disabled = !SC.pillow || !bereit;
  const fensterquelle = !!(SC.window_title || SC.window_id);
  $("scan-foto").textContent = fensterquelle ? "Fenster aufnehmen"
    : (SC.area ? "Bereich aufnehmen" : "Screenshot aufnehmen");

  // Der Bereich gilt fuer JEDE weitere Aufnahme dieses Scans — er muss also
  // dastehen, nicht nur in der Statuszeile aufblitzen.
  const quelleninfo = $("scan-quelleninfo");
  const quellenname = $("scan-quellenname");
  const bz = $("scan-bereich");
  const groesse = SC.area
    ? (SC.area[2] - SC.area[0]) + "×" + (SC.area[3] - SC.area[1])
    : "";
  quellenname.textContent = fensterquelle
    ? "Fenster „" + (SC.window_title || "gewählt") + "“"
    : (SC.area ? "Eigener Bildschirmausschnitt" : "Ganzer Bildschirm");
  const quellendetails = [];
  if (fensterquelle) quellendetails.push("Slots relativ");
  if (groesse) quellendetails.push(groesse);
  if (!fensterquelle && SC.area) {
    quellendetails.push("Position " + SC.area[0] + ", " + SC.area[1]);
  }
  if (!SC.window_available && SC.window_title) {
    quellendetails.push("Fenster nicht geöffnet");
  }
  bz.textContent = quellendetails.join(" · ");
  bz.hidden = !quellendetails.length;
  // Bei einem gewaehlten Fenster steht dabei, was das bedeutet: es wird direkt
  // abgebildet, also darf das Studio davor liegen.
  quelleninfo.title = fensterquelle
    ? "Editor und Live-Scan verwenden dieselbe Aufnahmequelle. Verschieben wird automatisch ausgeglichen; beim Desktop-Fallback muss das Fenster sichtbar sein."
    : (SC.area ? "Ausschnitt vom Bildschirm — hier darf nichts davor liegen." : "");
  quelleninfo.classList.toggle("an", !!SC.area || fensterquelle);
  $("scan-vollbild").disabled = !bereit || (!SC.area && !fensterquelle) || !SC.pillow;
  // Aufziehen geht nur auf einem Bild — vorher gibt es nichts anzuklicken.
  const auf = $("scan-aufziehen");
  auf.disabled = !bereit || !fotoDa();
  auf.classList.toggle("an", SC.modus === "area");
  scanFensterPflegen();
}

/** Nur die technischen Sonderwerkzeuge sind noch ein klassischer Klappbereich. */
function klappVorgabe(key) { return false; }

function klappPflegen() {
  for (const [key, id] of [["modi", "ab-modi"]]) {
    const zu = klappZu[key] === null ? klappVorgabe(key)
                                            : klappZu[key];
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
    ? "Bild gespeichert · " + SC.photo.width + "×" + SC.photo.height : "Noch kein Bild";
  $("scan-schritt-2-status").textContent = slots
    ? slots + (slots === 1 ? " Slot" : " Slots") : "Noch keine Slots";
  $("scan-schritt-3-status").textContent = items
    ? items + (items === 1 ? " Item" : " Items") : "Noch keine Items";
  const bereit = !!(SC.aufnahme_bereit && SC.aufnahme_bereit.item);
  $("scan-slots-finden").disabled = !bereit || !fotoDa() || !SC.pillow;
  $("scan-slot-neu").disabled = !bereit || !fotoDa() || !SC.pillow;
  $("scan-test").disabled = !bereit || !fotoDa() || !slots;
  $("scan-lernen").disabled = !bereit || !fotoDa() || !slots;
}

let scanFenster = [];

/** Die offenen Fenster zur Auswahl — nur nachgeholt, wenn Pillow da ist. */
async function scanFensterPflegen() {
  const wahl = $("scan-fenster");
  const neu = $("scan-fenster-neu");
  const bereit = scanKonfigurationOffen();
  neu.disabled = !SC.pillow || !bereit;
  if (!SC.pillow) { wahl.hidden = true; return; }
  wahl.disabled = !bereit;
  scanFenster = (await frage("scan_windows")) || [];
  wahl.hidden = false;
  wahl.replaceChildren();
  wahl.appendChild(el("option", {value: ""}, scanFenster.length
    ? "— kein Fenster (ganzer Bildschirm) —" : "— keine Fenster gefunden —"));
  scanFenster.forEach((f, i) => {
    // Die Lage steht dabei, weil sie das einzige Unterscheidungsmerkmal ist,
    // wenn dasselbe Programm mehrmals offen ist.
    const b = f.area;
    const o = el("option", {value: String(i)},
      f.title + "  ·  " + (b[2] - b[0]) + "×" + (b[3] - b[1])
      + " ab (" + b[0] + ", " + b[1] + ")");
    // **Die Wahl bleibt stehen.** Seit die Auswahl nicht mehr selbst aufnimmt,
    // liegt zwischen "Fenster gewaehlt" und "Bild da" ein zweiter Klick — und
    // in dieser Zeit muss ablesbar sein, WAS aufgenommen wird.
    if (SC.window_id && f.id === SC.window_id) o.selected = true;
    wahl.appendChild(o);
  });
  if (SC.window_title && !scanFenster.some((f) => f.id === SC.window_id)) {
    wahl.appendChild(el("option", {
      value: "__nicht_offen__", selected: true, disabled: true,
    }, "„" + SC.window_title + "“ · momentan nicht geöffnet"));
  }
}

/** Stehen die Masken in der rechten Spalte?
 *
 * **Der ganze Listen-Block wandert, nicht nur die Eintraege.** Reiter, Filter
 * und Liste gehoeren zusammen; als der Reiter links stand und die Masken
 * rechts erschienen, aenderte die linke Spalte bei jedem Umschalten ihre
 * Hoehe, und ein Hinweis musste erklaeren, wohin der Inhalt verschwunden ist.
 *
 * Die Aufteilung ist damit nach VERANTWORTUNG geschnitten: links, wie der Scan
 * entsteht (Auswahl, Assistent, Modus-Kacheln), rechts, was drin ist.
 *
 * Boss- und Icon-Scans bleiben davon unberuehrt. Dort sind es nicht Dutzende
 * gleichartiger Dinge, sondern EIN Scan mit Region, Erkennung und Aktion — eine
 * Maske traegt das nicht, und die Liste ist drei Zeilen lang. */
function scanMaskenRechts() {
  return scanArt === "item";
}

/* **Die Liste steht rechts — die ganze, samt Reitern und Filter.**
 *
 * Der Schnitt geht nach VERANTWORTUNG, nicht nach Scan-Art: links, wie der
 * Scan entsteht (Auswahl, Assistent, Werkzeuge), rechts, was drin ist.
 *
 * Hier stand bis zum Umbau ein zweiter Listen-Block in der LINKEN Spalte, und
 * eine Funktion entschied je Reiter, welcher der beiden ihn fuellt. Das war
 * die Naht, an der die linke Spalte bei jedem Umschalten ihre Groesse aenderte
 * — und ein Hinweistext musste erklaeren, wohin der Inhalt verschwunden ist.
 * Ein Ort, ein Bauplan (`scanListenBlock`).
 *
 * Als Masken kommen nur die Item-Listen (`scanMaskenRechts()`): dort stehen
 * Dutzende gleichartiger Dinge nebeneinander. Ein Boss- oder Icon-Scan ist
 * EINES — Region, Erkennung, Aktion —, das traegt keine Maske, und seine Liste
 * ist drei Zeilen lang. */

/** Welche Liste gilt: die gewaehlte, sonst die zur Lage passende Vorgabe. */
function scanListeAktiv() {
  if (scanListe) return scanListe;
  if (scanArt === "boss") return "bosse";
  if (scanArt === "icon") return "icons";
  return SC && SC.offen ? "items" : "scans";
}

/** Namen so vergleichen, wie man sie liest: „Slot 2" vor „Slot 10".
 *
 * Ein reiner Zeichenvergleich sortiert „Slot 10" zwischen „Slot 1" und
 * „Slot 2" — bei fünfundvierzig durchnummerierten Slots ist die Liste damit
 * unbrauchbar, obwohl sie sortiert ist. */
function nachNamen(a, b) {
  return String(a).localeCompare(String(b), "de", {numeric: true});
}

/** Der Anker, an dem der Fokus einen Neuaufbau ueberlebt — eine id je Maske.
 *
 * Ohne sie zaehlt `fokusMerken()` die Position ueber die ganze Spalte, und die
 * drei Felder, die man dort tippt, sortieren die Liste gerade um. */
function maskeId(kind, name) { return "maske:" + kind + ":" + name; }

/** Der Reiter folgt der Auswahl — aber nur, wenn sie sich geaendert hat.
 *
 * Ein Klick im Bild waehlt einen Slot. Steht gerade die Item-Liste offen,
 * geschieht rechts sonst nichts, und der Klick sieht wirkungslos aus. Beim
 * blossen Neuzeichnen darf dagegen nichts umschalten: sonst waere der Weg aus
 * der Slot-Liste heraus versperrt, solange ein Slot gewaehlt ist. */
function scanReiterFolgen() {
  if (!SC || scanArt !== "item") return;
  const jetzt = SC.wahl.kind + ":" + SC.wahl.name;
  if (jetzt === scanWahlZuletzt) return;
  const erster = scanWahlZuletzt === null;
  scanWahlZuletzt = jetzt;
  // Der Scan hat seinen eigenen Weg (`scanReiterNachOeffnen`); und beim
  // allerersten Zeichnen gibt es keinen Wechsel, nur einen Anfangszustand.
  if (erster) return;
  const ziel = {slot: "slots", item: "items"}[SC.wahl.kind];
  if (ziel && scanListeAktiv() !== ziel) scanListe = ziel;
}

/** Reiter, Filter und Liste — ein Bauplan, ein Ort. */
function scanListenBlock(tabs, filter, ziel) {
  const offen = scanListeAktiv();
  // Kopf und Liste werden getrennt gebaut (der Kopf klebt oben, die Liste
  // scrollt) — gerufen wird dieselbe Funktion zweimal, damit die Zuordnung
  // Reiter -> Inhalt an EINER Stelle steht und nicht an zweien auseinanderlaeuft.
  const an = (wohin, kind) => { if (wohin) wohin.appendChild(kind); };
  if (scanArt !== "item") {
    if (scanArt === "icon") {
      an(tabs, el("button", {class: "tab an"},
        "Icon-Scans " + SC.icon_scans.length));
      return ziel ? erkListeIcons(ziel) : undefined;
    }
    // Zwei Listen, weil es zwei Orte sind: die Bosse DIESES Scans und die,
    // die in jedem gelten. Sie zusammenzuwerfen hiesse, den Unterschied zu
    // verlieren, an dem alles haengt.
    for (const [key, text, number] of [["bosse", "Bosse", erkBosse().length],
                                     ["bibliothek", "Bibliothek",
                                      SC.global_bosses.length]]) {
      an(tabs, el("button", {class: "tab" + (offen === key ? " an" : ""),
        onclick: () => { scanListe = key; zeichneScans(); }}, text + " " + number));
    }
    if (!ziel) return undefined;
    return offen === "bibliothek" ? erkListeBibliothek(ziel) : erkListeBosse(ziel);
  }
  // Die Zahl am Reiter ist die der SICHTBAREN Eintraege — sonst stuende dort 40,
  // waehrend zwei in der Liste stehen, und man sucht den Rest.
  // Reihenfolge = Rangfolge: der Scan ist das Uebergeordnete, Slots und Items
  // haengen an ihm.
  const gruppen = [["scans", "Scans", SC.scans.length, SC.scans.length],
                   ["slots", "Slots", scanSichtbar(SC.slots, false, "slot").length, SC.slots.length],
                   ["items", "Items", scanSichtbar(SC.items, true, "item").length, SC.items.length]];
  for (const [key, text, sichtbar, total] of gruppen) {
    an(tabs, el("button", {
      class: "tab" + (offen === key ? " an" : ""),
      title: sichtbar === total ? "" : total + " insgesamt",
      onclick: () => { scanListe = key;
                       scanOrdnungVergessen(); zeichneScans(); },
    }, text + " " + sichtbar + (sichtbar === total ? "" : "/" + total)));
  }
  if (filter) scanFilterzeile(filter, offen);
  if (!ziel) return undefined;
  if (offen === "slots") return scanListeSlots(ziel);
  if (offen === "items") return scanListeItems(ziel);
  return scanListeScans(ziel);
}

/** Was die Liste einschraenkt: Kategorie; Bestand gehoert immer zum Scan. */
function scanFilterzeile(filter, offen) {
  if (SC.offen && offen !== "scans") {
    const kind = offen === "slots" ? "slot" : "item";
    const total = offen === "slots" ? SC.slots : SC.items;
    filter.appendChild(el("button", {class: "btn gefahr", disabled: !total.length,
      title: total.length
        ? "Löscht alle " + total.length + " " + (kind === "slot" ? "Slots" : "Items")
          + " aus „" + SC.offen + "“ — nicht nur aus der Mitgliedschaft. "
          + "STRG+Z nimmt es zurück."
        : "Nichts zu löschen.",
      onclick: () => rufScan("scan_delete_all", {kind: kind})},
      total.length + " " + (kind === "slot" ? "Slots" : "Items") + " löschen"));
  }
  if (offen === "items" && SC.categories.length) {
    filter.appendChild(selection("", [{value: "", text: "alle Kategorien"}].concat(
      SC.categories.map((k) => ({value: k, text: k}))), scanKategorie,
      (v) => { scanKategorie = v; zeichneScans(); }));
  }
}

/* **Sortiert wird beim Laden und auf Knopfdruck — nicht bei jedem Tastendruck.**
 *
 * Die Liste ordnet nach Kategorie, Prioritaet und Name. Sortierte sie sich nach
 * JEDER Aenderung neu, springt genau das Item weg, an dem man gerade tippt: man
 * tippt eine 2, die Zeile rutscht drei Plaetze hoch, das naechste Feld ist ein
 * anderes. Gemerkt wird deshalb die Reihenfolge, in der zuletzt sortiert wurde;
 * neu Dazugekommenes und alles, was seine Kategorie gewechselt hat, haengt sich
 * ans Ende seiner Gruppe.
 *
 * Aufgefrischt wird sie beim Laden, beim Wechsel des Zusammenhangs (anderer
 * Scan, anderer Reiter) und durch „Sortieren". Reiner Oberflaechenzustand — die
 * Datei kennt keine Reihenfolge. */
let scanOrdnung = {item: null, slot: null};

function scanOrdnungVergessen() {
  scanOrdnung = {item: null, slot: null};
}

/** Die eingefrorene Gruppe eines Namens — oder `null`, wenn er neu ist.
 *
 * **Die Kategorie war der erste Sortierschluessel und damit das letzte Feld,
 * das die Zeile noch wegspringen liess.** Sie beim Tippen auszuwerten heisst:
 * ein Item, das gerade „Helme" bekommt, wandert im selben Moment in eine andere
 * Gruppe — mitten in der Bearbeitung, und der naechste TAB landet woanders.
 *
 * Eingefroren wird sie deshalb zusammen mit dem Rang. Die Ueberschriften kommen
 * aus dieser Momentaufnahme, nicht aus dem aktuellen Wert; damit bleibt die
 * Gliederung genau die, die zuletzt sortiert wurde. Was die Kategorie
 * inzwischen gewechselt hat, sagt seine Maske (`i.kategorie` steht im
 * Bedienelement) und die Zustandszeile. */
function scanOrdnungGruppe(kind) {
  const merk = scanOrdnung[kind];
  if (!merk) return null;
  const gruppen = new Map();
  for (const e of merk) gruppen.set(e.name, e.gruppe);
  return (name) => (gruppen.has(name) ? gruppen.get(name) : null);
}

/** Umbenennen aendert den Namen, nicht den Rang.
 *
 * Die gemerkte Reihenfolge haengt am Namen — ohne das Nachziehen ist ein gerade
 * umbenanntes Item „unbekannt" und rutscht ans Ende seiner Gruppe. Genau beim
 * Namen tippt man aber, und beim TAB aus dem Feld sprang die Zeile weg: dieselbe
 * Beschwerde wie beim Sortieren nach jedem Tastendruck, nur an einem Feld.
 *
 * Eingetragen werden BEIDE Namen (neu vor alt). Lehnt die Bruecke den neuen ab
 * — schon vergeben —, heisst das Item weiter wie vorher und behaelt trotzdem
 * seinen Platz; die Raenge verschieben sich dabei gleichmaessig, verglichen
 * werden sie ohnehin nur gegeneinander. */
function scanOrdnungUmbenennen(kind, alt, neu) {
  const merk = scanOrdnung[kind];
  if (!merk || !neu || alt === neu) return;
  const i = merk.findIndex((e) => e.name === alt);
  if (i >= 0) merk.splice(i, 1, {name: neu, gruppe: merk[i].gruppe}, merk[i]);
}

/** Die gemerkte Vorschau auf den neuen Namen mitnehmen.
 *
 * Der Zwischenspeicher haengt am ITEM-Namen, das Bild aber an der
 * Template-DATEI — und die heisst nach dem Umbenennen genauso wie vorher. Ohne
 * das Mitnehmen galt die Vorschau als fehlend: die Maske wurde einmal ohne Bild
 * gezeichnet, `scanVorschauenHolen()` holte dieselben Bytes noch einmal aus
 * Python und baute die Spalte danach ein zweites Mal auf. Sichtbar war das als
 * kurzes Flackern beim Umbenennen — dasselbe Bild, zwei Neuaufbauten.
 *
 * Der alte Eintrag bleibt stehen, aus demselben Grund wie bei
 * `scanOrdnungUmbenennen()`: lehnt die Bruecke den neuen Namen ab (Dublette,
 * leer), zeigt die Maske weiter unter dem alten Namen — und braucht dort ihr
 * Bild.
 */
function scanVorschauUmbenennen(kind, alt, neu) {
  if (kind !== "item" || !neu || alt === neu) return;
  const image = scanVorschauen.get(alt);
  if (image) scanVorschauen.set(neu, image);
}

/** Die gemerkte Reihenfolge als Rang je Name; unbekannt = ans Ende. */
function scanOrdnungRang(kind) {
  const merk = scanOrdnung[kind];
  if (!merk) return null;
  const rang = new Map();
  merk.forEach((e, i) => rang.set(e.name, i));
  return (name) => (rang.has(name) ? rang.get(name) : Number.MAX_SAFE_INTEGER);
}

/** Was die Liste zeigt: gefiltert nach offenem Scan und Kategorie.
 *
 * **„Gehoert dazu ODER wird gerade gesehen"** — die zweite Haelfte ist die
 * nuetzlichere: ein Item, das ein anderes Spiel schon kennt, steht da, bevor
 * jemand auf die Idee kommt, es neu zu lernen. Slots tragen das Merkmal nicht,
 * sie sind Bildschirm-Koordinaten und gehoeren immer genau einem Spiel.
 *
 * Dazu, was gerade abgewaehlt wurde (s. o.) — sonst nimmt der Filter einem den
 * Rueckweg. */
function scanSichtbar(eintraege, mitKategorie, kind) {
  let liste = eintraege;
  if (mitKategorie && scanKategorie)
    liste = liste.filter((e) => (e.category || "") === scanKategorie);
  return liste;
}

/** Ein Namensfeld in einer Maske — mit dem Fokus-Anker fuer das Umbenennen. */
function maskeName(kind, name, title, setze) {
  const feld = el("input", {value: name, autocomplete: "off", title: title});
  feld.addEventListener("change", () => {
    const neu = feld.value.trim();
    // DREI Dinge haengen am Namen: der Anker fuer den Fokus, der Rang in der
    // Liste und die gemerkte Vorschau. Wer umbenennt, sagt allen dreien vorher
    // Bescheid — wer eines vergisst, sieht es sofort: der Fokus springt weg,
    // die Zeile wandert, oder das Bild blinkt.
    fokusUmbenennung(maskeId(kind, name), maskeId(kind, neu));
    scanOrdnungUmbenennen(kind, name, neu);
    scanVorschauUmbenennen(kind, name, neu);
    setze(feld.value);
  });
  feld.addEventListener("keydown", (e) => { if (e.key === "Enter") feld.blur(); });
  return feld;
}

/** Das Gehaeuse einer Maske: id, Auswahl-Ring, Klick zum Waehlen, Detailteil.
 *
 * **Eine Bauform fuer Scans, Slots und Items.** Sie unterscheiden sich in dem,
 * was drinsteht — nicht darin, wie man sie anfasst. Vorher waren es drei
 * Formen an zwei Orten, und ein Slot liess sich nur ueber vier Zahlenfelder
 * bearbeiten, waehrend ein Item eine Maske hatte. */
function maskeBauen(kind, name, selected, teile, detail, beimWaehlen) {
  const maske = el("div", {class: "scan-maske" + (selected ? " an" : ""),
                           id: maskeId(kind, name)});
  for (const teil of teile) maske.appendChild(teil);
  if (selected && detail) {
    const kasten = el("div", {class: "scan-maske-detail"});
    detail(kasten);
    maske.appendChild(kasten);
  }
  // Ein Klick auf die Maske waehlt sie; ein zweiter klappt ein offenes Item
  // wieder zu. Felder und Knoepfe sind davon ausgenommen, sonst wuerde schon
  // das Bearbeiten den Detailteil unter der Hand schliessen.
  maske.addEventListener("click", (e) => {
    if (e.target.closest("input, label, button, select, summary, details")) return;
    if (selected && kind === "item") {
      rufScan("scan_select", {kind: "item", name: ""});
    } else if (!selected) {
      beimWaehlen();
    }
  });
  return maske;
}

function scanListeSlots(ziel) {
  // **Die stabile ID ist die Reihenfolge.** Scan-Position, Name und Reihenfolge
  // in der Datei koennen sich aendern; die ID bezeichnet den Slot dauerhaft.
  // Deshalb gilt sie auch ueber die Grenze „gehoert zum offenen Scan" hinweg.
  // Alte oder ungueltige IDs landen am Ende und werden dort nach Namen stabil
  // geordnet — die Ansicht erfindet keine Reparatur fuer Bestandsdaten.
  const rang = scanOrdnungRang("slot");
  const liste = scanSichtbar(SC.slots, false, "slot").slice().sort((a, b) =>
    rang ? (rang(a.name) - rang(b.name))
         : (((Number(a.id) > 0 ? Number(a.id) : Number.MAX_SAFE_INTEGER)
              - (Number(b.id) > 0 ? Number(b.id) : Number.MAX_SAFE_INTEGER))
             || nachNamen(a.name, b.name)));
  if (!rang) scanOrdnung.slot = liste.map((s) => ({name: s.name, gruppe: ""}));
  if (!liste.length) {
    ziel.appendChild(el("p", {class: "hinweis"}, SC.slots.length
      ? "Kein Slot gehört zu diesem Scan. Den Filter ausschalten und Häkchen setzen."
      : "Noch keine Slots. Modus „Slots finden“ — oder „Neuer Slot“ und zwei "
        + "Ecken im Bild anklicken."));
    return;
  }
  for (const s of liste) ziel.appendChild(scanSlotMaske(s));
}

/** Ein Slot als Maske — dieselbe Bauform wie beim Item.
 *
 * **Was man an einem Slot tippt, ist sein Name; alles andere zieht man im
 * Bild.** Deshalb traegt die zweite Zeile keinen Regler, sondern den Stand:
 * Groesse, Klickpunkt und was zuletzt darin erkannt wurde. Die Zahlen dazu
 * klappen im Detailteil auf, wie beim Item die Konfidenz. */
function scanSlotMaske(s) {
  const setze = (feld, value) => rufScan("scan_slot_set",
                                        {name: s.name, feld: feld, value: value});
  const selected = SC.selection.includes(s.name)
                || (SC.wahl.kind === "slot" && SC.wahl.name === s.name);
  const name = maskeName("slot", s.name,
    "Name — zugleich die Referenz in jedem Scan", (v) => setze("name", v));
  // **Die ID ist eine reine Anzeige-Kachel, kein Knopf.** Sie bleibt gleich,
  // auch wenn der Slot im offenen Scan ab- und wieder angeschaltet wird — DAS
  // ändert nur seine STELLE (er wandert ans Ende der Mitgliederliste), nicht
  // seine Identität. Die Stelle steht deshalb nur noch im Tooltip, nicht mehr
  // in der Zahl selbst.
  const id = el("span", {class: "zahl",
    title: s.number
      ? "Slot-ID #" + s.id + " — bleibt gleich, auch beim Ab-/Wieder-Anschalten. "
        + "Läuft in „" + SC.offen + "“ als " + s.lauf + ". von " + s.total + "."
        + (s.lauf !== s.number ? " (rückwärts)" : "")
      : "Slot-ID #" + s.id + " — bleibt gleich, auch beim Ab-/Wieder-Anschalten."},
    "#" + s.id);
  const box = el("input", {type: "checkbox",
    "aria-label": s.name + " ein- oder ausschalten"});
  box.checked = !!s.active;
  box.addEventListener("change", () => setze("active", box.checked));
  const anaus = el("label", {class: "an scan-slot-schalter",
    title: s.active ? "Slot ist aktiv — ausschalten" : "Slot ist aus — einschalten"}, box);
  const felder = el("div", {class: "scan-maske-felder"}, name, scanSlotStand(s));
  const maske = maskeBauen("slot", s.name, selected,
    [el("div", {class: "scan-marke"}, anaus, id),
     el("span", {class: "kugel" + (s.color ? "" : " ohne"),
                  title: s.color ? "Hintergrund " + s.color : "Hintergrund nicht gemessen",
                  style: s.color ? "background:" + s.color : ""}),
     felder],
    (kasten) => scanSlotDetails(kasten, s),
    () => rufScan("scan_select", {kind: "slot", name: s.name}));
  maske.classList.toggle("aus", !s.active);
  return maske;
}

/** Die Zustandszeile eines Slots: Groesse, Warnung, letzter Treffer. */
function scanSlotStand(s) {
  // Die Groesse ist ein gemessener WERT, kein Satz — also dieselbe Kachel wie
  // die Nummer daneben. Was daneben steht („Item 1", „unbekannt", „→ Helme"),
  // ist eine Aussage und bleibt Text.
  const teile = [el("span", {class: "zahl"}, s.width + "×" + s.height)];
  if (!s.active) teile.push(el("span", {class: "klein slot-aus"}, "aus"));
  // Ein winziger Slot ist im Bild kaum zu treffen — in der Liste ist er so
  // gross wie jeder andere. Deshalb steht die Warnung HIER: das ist der Weg,
  // ihn auszuwaehlen und zu loeschen.
  if (s.tiny) {
    teile.push(el("span", {class: "klein", style: "color:var(--err)",
      title: "Zu klein zum Erkennen — hier auswählen und löschen"}, "⚠ zu klein"));
  } else if (s.treffer && s.treffer.name) {
    teile.push(el("span", {class: "klein",
      style: "color:var(" + (s.treffer.foreign ? "--slot-fremd" : "--slot-ok") + ")",
      title: s.treffer.foreign
        ? "erkannt, gehört aber noch nicht zu diesem Scan" : ""}, s.treffer.name));
  } else if (s.treffer) {
    // Nichts erkannt = hier ist noch zu lernen. Dieselbe Farbe wie sein
    // Rechteck im Bild, damit Liste und Bild zusammengehen.
    teile.push(el("span", {class: "klein", style: "color:var(--slot-offen)"},
                  "unbekannt"));
  }
  return el("div", {class: "scan-maske-stand"}, teile);
}

function scanListeItems(ziel) {
  // **Gesortiert wird nur auf Ansage.** Steht eine gemerkte Reihenfolge, gilt
  // ausschliesslich sie — auch fuer die Gruppen, denn die Kategorie war als
  // erster Schluessel das letzte Feld, das die Zeile noch wegspringen liess.
  // Ohne Merkposten (erster Aufbau, „Sortieren", Neu laden) wird frisch geordnet.
  const rang = scanOrdnungRang("item");
  const gruppe = scanOrdnungGruppe("item");
  const frisch = (a, b) =>
    (SC.offen ? Number(!!b.dabei) - Number(!!a.dabei) : 0) ||
    a.priority - b.priority || a.name.localeCompare(b.name, "de");
  const liste = scanSichtbar(SC.items, true, "item").slice().sort((a, b) =>
    rang ? (rang(a.name) - rang(b.name)) || frisch(a, b)
         : ((a.category || "").localeCompare(b.category || "", "de")
            || frisch(a, b)));
  if (!rang) {
    scanOrdnung.item = liste.map((i) => ({name: i.name, gruppe: i.category || ""}));
  }
  if (!liste.length) {
    ziel.appendChild(el("p", {class: "hinweis"}, SC.items.length
      ? "Kein Item passt zum Filter. Der Bestand hat " + SC.items.length + " Stück."
      : "Noch keine Items. Einen Slot wählen und „Item lernen“ — oder alle "
        + "Slots auf einmal."));
    return;
  }
  scanVorschauenHolen(liste.map((i) => i.name));
  let letzteKategorie = null;
  for (const i of liste) {
    // Die Ueberschrift kommt aus der EINGEFRORENEN Gruppe, nicht aus dem
    // aktuellen Wert: sonst reisst ein gerade geaendertes Item eine zweite
    // Ueberschrift mitten in die Liste. Wo es hinwandert, sagt seine Maske.
    const gefroren = gruppe ? gruppe(i.name) : null;
    const category = (gefroren === null ? (i.category || "") : gefroren)
                      || "Ohne Kategorie";
    if (category !== letzteKategorie) {
      ziel.appendChild(scanKategorieKopf(category, liste));
      letzteKategorie = category;
    }
    ziel.appendChild(scanItemMaske(i, gefroren));
  }
}

/** Die Gruppenueberschrift — und zugleich der Weg, die Kategorie umzubenennen.
 *
 * **Die Kategorie ist kein eigenes Objekt**, sondern ein Feld an jedem Item;
 * zwei Gruppen zusammenzulegen hiess deshalb, jede Maske einzeln anzufassen.
 * Der Katalog ordnet bewusst ENG ein (dreizehn Kategorien mit je einem Item bei
 * einem echten Bestand), Zusammenlegen ist also der Normalfall und kein
 * Sonderfall.
 *
 * Getippt wird in der Ueberschrift selbst: sie traegt den Namen ohnehin, und
 * ein zweites Feld daneben waere dieselbe Sache an zwei Stellen. Gemeldet wird
 * bei `change`, nicht bei jedem Tastendruck — sonst zoege jedes Zeichen alle
 * Items mit.
 */
function scanKategorieKopf(category, liste) {
  const empty = category === "Ohne Kategorie";
  const value = empty ? "" : category;
  const count = liste.filter((i) => (i.category || "") === value).length;
  const feld = el("input", {class: "scan-kategorie-feld", value: value,
    placeholder: "ohne Kategorie",
    title: "Umbenennen zieht alle Items dieser Gruppe mit. Leer = Kategorie "
           + "entfernen. Gleicher Name wie eine andere Gruppe = zusammenlegen."});
  feld.addEventListener("change", () => {
    if (feld.value.trim() === value) return;
    rufScan("scan_category_rename", {alt: value, neu: feld.value.trim()});
  });
  feld.addEventListener("keydown", (e) => { if (e.key === "Enter") feld.blur(); });
  return el("div", {class: "scan-kategorie-kopf"}, feld,
            el("span", {class: "zahl"}, String(count)));
}

/** Ein Item als kleine Maske: Haken, Name, Kategorie, Prioritaet — in der Liste.
 *
 * Ein Ein-Aus-Knopf war zu wenig: alles andere kostete einen Klick in die Liste,
 * einen Blick nach rechts und einen Weg zurueck, bei sechzig Items sechzig Mal.
 *
 * Was selten gebraucht wird (Vorlagen, Marker, Konfidenz, Loeschen), klappt
 * darunter auf. Name, Kategorie und Prioritaet stehen NUR hier — dieselbe Sache
 * an zwei Stellen waeren zwei Wahrheiten. */
function scanItemMaske(i, gefroren) {
  const setze = (feld, value) => rufScan("scan_item_set",
                                        {name: i.name, feld: feld, value: value});
  const selected = SC.wahl.kind === "item" && SC.wahl.name === i.name;
  const image = scanVorschauen.get(i.name);

  const box = el("input", {type: "checkbox",
    "aria-label": i.name + " ein- oder ausschalten"});
  box.checked = !!i.active;
  box.addEventListener("change", () => setze("active", box.checked));
  const anaus = el("label", {class: "an scan-slot-schalter",
    title: i.active ? "Item ist aktiv — ausschalten" : "Item ist aus — einschalten"}, box);

  const name = maskeName("item", i.name,
    "Name — zugleich die Referenz in jedem Scan", (v) => setze("name", v));

  // Vorhandene anklicken, neue tippen — dasselbe Bedienelement wie in der
  // Lern-Vorschau. Ein freies Textfeld allein macht aus „Helme" und „helme"
  // zwei Kategorien, und Items derselben Kategorie konkurrieren miteinander.
  const kat = kategorieWahl(i.category || "", (v) => setze("category", v),
    {title: "Items derselben Kategorie konkurrieren; die kleinere Priorität gewinnt",
     empty: "— ohne —", key: "item:" + i.name});

  // **Die Zahl allein sagt nicht, ob sie frei ist.** Teilt sich das Item seinen
  // Rang mit einem anderen derselben Kategorie, entscheidet die Scan-Reihenfolge
  // — also der Zufall. Das steht am Feld, nicht erst im aufgeklappten Detail:
  // getippt wird hier.
  const kollision = prioritaetDoppelt(i);
  const prio = el("input", {
    type: "number", value: i.priority, min: 0, step: 1,
    class: kollision.length ? "doppelt" : "",
    title: kollision.length
      ? "P" + i.priority + " hat auch: " + kollision.join(", ")
        + " — bei gleicher Zahl entscheidet der Zufall"
      : "Priorität — kleiner gewinnt" + (i.category
          ? " (frei in „" + i.category + "“: P"
            + naechsteFreiePrioritaet(i.category, i.name) + ")"
            + "; 0 = ganz nach vorn, die anderen rücken um eins"
          : ", zählt nur innerhalb einer Kategorie")});
  prio.addEventListener("change", () => {
    if (prio.value.trim() !== "") setze("priority", Number(prio.value));
  });
  prio.addEventListener("keydown", (e) => { if (e.key === "Enter") prio.blur(); });

  const felder = el("div", {class: "scan-maske-felder"}, name,
    el("div", {class: "scan-maske-unten"}, kat, prio), scanItemStand(i, gefroren));

  const maske = maskeBauen("item", i.name, selected,
    [el("div", {class: "scan-marke"}, anaus),
     image ? el("img", {class: "mini", src: image, alt: ""})
          : el("span", {class: "kugel" + (i.marker.length ? "" : " ohne"),
                        style: i.marker.length ? "background:" + i.marker[0] : ""}),
     felder],
    // **Das Gewaehlte klappt seine Einstellungen hier auf**, statt sie in eine
    // andere Spalte zu legen: Vorlage, Marker, Konfidenz und Loeschen gehoeren
    // diesem Item, und man sieht beim Arbeiten daran nicht zwischen zwei Orten
    // hin und her. Nur beim gewaehlten — sechzig aufgeklappte Bloecke waeren
    // keine Liste mehr.
    (kasten) => scanItemDetails(kasten, i),
    () => rufScan("scan_select", {kind: "item", name: i.name}));
  maske.classList.add("scan-item-maske");
  maske.classList.toggle("aus", !i.active);
  return maske;
}

/** Die Zustandszeile einer Item-Maske: erkannt, stumm, fehlende Vorlage.
 *
 * **„Items erkennen" war in dieser Liste unsichtbar.** Der Knopf faerbte die
 * Rechtecke im Bild und fuellte die Ergebnisleiste — wer aber in der Item-Liste
 * stand (und das ist die Liste, in der man arbeitet), sah nach dem Klick
 * nichts und hielt ihn fuer wirkungslos. Hier steht jetzt, WO das Item gerade
 * gefunden wurde. */
function scanItemStand(i, gefroren) {
  const teile = [];
  // Die Kategorie ist gewechselt, die Zeile steht aber noch unter der alten
  // Ueberschrift — das muss dastehen, sonst liest sich die Liste falsch.
  if (gefroren !== null && gefroren !== undefined
      && (i.category || "") !== gefroren) {
    teile.push(el("span", {style: "color:var(--accent)",
      title: "Beim nächsten „Sortieren“ rutscht das Item in diese Gruppe"},
      "→ " + (i.category || "ohne Kategorie")));
  }
  if ((i.detected_in || []).length) {
    teile.push(el("span", {style: "color:var(--slot-ok)"},
      "erkannt in " + i.detected_in.slice(0, 2).join(", ")
      + (i.detected_in.length > 2 ? " +" + (i.detected_in.length - 2) : "")));
  }
  if (i.stumm) {
    teile.push(el("span", {style: "color:var(--err)",
      title: "Weder Template noch Marker — dieses Item wird nie erkannt"}, "stumm"));
  } else if (!(i.vorlagen || []).length) {
    teile.push(el("span", {class: "mono"}, i.marker.length + " Marker"));
  }
  if ((i.missing_scan_sizes || []).length) {
    teile.push(el("span", {style: "color:var(--accent)",
      title: "Für die Slot-Größen dieses Scans gibt es noch keine Vorlage"},
      "Vorlage fehlt"));
  }
  const kollision = prioritaetDoppelt(i);
  if (kollision.length) {
    teile.push(el("span", {style: "color:var(--accent)",
      title: "Gleiche Priorität wie " + kollision.join(", ")
             + " — welches zuerst geklickt wird, entscheidet der Zufall"},
      "P" + i.priority + " doppelt"));
  }
  if (i.confirmation) {
    teile.push(el("span", {class: "mono", title: "Nach dem Klick wird bestätigt: "
      + i.confirmation.text}, "+ Bestätigung"));
  }
  return el("div", {class: "scan-maske-stand"}, teile);
}

function scanListeScans(ziel) {
  if (!SC.scans.length) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Noch kein Item-Scan. Er ist die Klammer um Slots und Items — bei mehreren "
      + "Spielen der einzige Weg, sie auseinanderzuhalten."));
  }
  for (const c of SC.scans) ziel.appendChild(scanScanMaske(c));
}

/** Ein Item-Scan als Maske: Name, Umfang — und seine Einstellungen darunter.
 *
 * **Hier lag die Luecke, durch die ein Scan gar nicht mehr zu loeschen war.**
 * Ein Klick auf die Zeile oeffnete ihn, das Oeffnen schaltete auf die
 * Item-Liste um, und die Scan-Einstellungen standen in einer Spalte, die man
 * damit gerade verlassen hatte. Jetzt bleibt der Reiter stehen, und alles, was
 * dem Scan gehoert, klappt in seiner Maske auf. */
function scanScanMaske(c) {
  const offen = SC.offen === c.name;
  const name = el("span", {class: "scan-maske-name",
    title: "Ein Block vom Typ ITEM-SCAN verweist per Name hierauf"}, c.name);
  const stamp = el("div", {class: "scan-maske-stand"},
    el("span", {class: "klein mono"},
       c.slots.length + " Slots · " + c.items.length + " Items"),
    offen ? el("span", {class: "klein", style: "color:var(--slot-ok)"}, "offen") : null,
    c.fehlend.length
      ? el("span", {class: "klein", style: "color:var(--err)",
                    title: "Zeigt ins Leere: " + c.fehlend.join(", ")},
           c.fehlend.length + "× fehlt")
      : null);
  return maskeBauen("scan", c.name, offen,
    [el("span", {}),
     el("span", {class: "kugel" + (offen ? "" : " ohne"),
                 style: offen ? "background:var(--slot-ok)" : ""}),
     el("div", {class: "scan-maske-felder"}, name, stamp)],
    (kasten) => scanScanDetails(kasten, c),
    // Waehlen und Oeffnen sind hier dasselbe: ein Scan, den man ansieht, ist
    // der, an dem man arbeitet. Der Reiter bleibt dabei stehen — sonst
    // verschwindet die Maske, die sich gerade aufgeklappt hat.
    () => { scanReiterNachOeffnen = "scans";
            rufScan("scan_open", {name: c.name}); });
}

/** Template-Bilder nachholen, die wir noch nicht haben — in EINEM Aufruf. */
async function scanVorschauenHolen(namen) {
  const fehlend = namen.filter((n) => !scanVorschauen.has(n));
  if (!fehlend.length) return;
  // Vormerken, damit ein zweiter Aufbau nicht nochmal fragt.
  for (const n of fehlend) scanVorschauen.set(n, "");
  const antwort = await frage("scan_preview", {namen: fehlend});
  if (!antwort) return;
  let neu = false;
  for (const [name, url] of Object.entries(antwort)) {
    if (url) { scanVorschauen.set(name, url); neu = true; }
  }
  if (neu && ansicht === "scans") scanInspektor();
}

/* ------------------------------------------------------------------ Overlay */

function scanOverlay() {
  const svg = $("scan-overlay");
  if (!SC || !SC.photo) { svg.replaceChildren(); return; }
  const f = SC.photo;
  svg.setAttribute("viewBox", "0 0 " + f.width + " " + f.height);
  svg.replaceChildren();
  // Schrift und Punktgroessen werden gegen den Zoom gerechnet, damit sie in
  // jeder Vergroesserung gleich gross auf dem Schirm stehen. Striche erledigt
  // `vector-effect` im CSS.
  const px = 1 / Math.max(scanZoom, 0.001);
  // Bei offenem Item-Scan: seine Slots normal, alle anderen gestrichelt und
  // blass. Ohne das muss man Liste und Bild im Kopf zusammenbringen.
  // Was gerade gezogen wird, wird SCHON VERSCHOBEN gezeichnet — sonst zieht man
  // blind und sieht das Ergebnis erst beim Loslassen. Nur eine Zeichnung: die
  // Daten aendert erst der Aufruf beim Loslassen.
  const zieh = scanZiehVersatz || [0, 0];
  const gezogen = zieh[0] || zieh[1]
    ? new Set(scanGewaehlteSlots().map((s) => s.name)) : null;

  // Slots gehoeren dem Item-Scan. Auf einem Boss-Bild waeren 45 Rechtecke kein
  // Ueberblick, sondern ein Gitter ueber der einen Region, um die es geht.
  for (const s of (scanArt === "item" ? SC.slots : [])) {
    const v = gezogen && gezogen.has(s.name) ? zieh : [0, 0];
    const [x1, y1] = scanZuBild(s.region[0] + v[0], s.region[1] + v[1]);
    const [x2, y2] = scanZuBild(s.region[2] + v[0], s.region[3] + v[1]);
    // Gewaehlt ist, was in der Auswahl steht — bei einem Rechteck sind das
    // dreissig. `SC.wahl` bleibt der eine, den der Inspektor bearbeitet.
    const selected = SC.selection.includes(s.name)
      || (SC.wahl.kind === "slot" && SC.wahl.name === s.name);
    // Gruen = hier liegt ein Item, das der Scan kennt. Amber = erkannt, aber
    // noch nicht Mitglied dieses Scans — anderer Zustand, andere Farbe, sonst
    // sucht man spaeter, warum der Scan das Gruene nicht findet.
    const zustand = (s.treffer
      ? (s.treffer.name ? (s.treffer.foreign ? " fremditem" : " treffer") : " empty")
      : "");
    const aus = s.active ? "" : " aus";
    // Die Fuellung traegt denselben Zustand wie der Umriss: auf einem bunten
    // Spielbild ist die Flaeche das, was man sieht, der Strich schaerft nur.
    svg.appendChild(svgEl("rect", {x: x1, y: y1, width: x2 - x1, height: y2 - y1,
      class: "scan-fuellung" + zustand + aus + (selected ? " gewaehlt" : "")}));
    svg.appendChild(svgEl("rect", {x: x1, y: y1, width: x2 - x1, height: y2 - y1,
      class: "scan-slot" + zustand + aus + (selected ? " gewaehlt" : "")}));
    // Name ueber dem Rechteck, Erkennungsergebnis darunter — so ueberdeckt
    // keins von beiden das Bild im Slot.
    //
    // Nur, wenn er hineinpasst: die Schrift steht in SCHIRM-Pixeln (gegen den
    // Zoom gerechnet), der Slot in Bild-Pixeln, und bei 45 Slots waeren es 45
    // Namen uebereinander. Der gewaehlte behaelt seinen immer.
    const breit = (x2 - x1) * scanZoom;      // Breite auf dem Schirm
    if (breit >= 34 || selected) {
      svg.appendChild(svgEl("text", {x: x1, y: y1 - 3 * px, class: "scan-marke" + aus,
        "font-size": 11 * px, "stroke-width": 3 * px}, s.name));
    }
    if (s.treffer && s.treffer.name && (breit >= 34 || selected)) {
      // Dieselbe Quelle wie der Umriss — sonst laeuft die Marke von ihrem
      // eigenen Rechteck farblich weg.
      svg.appendChild(svgEl("text", {x: x1, y: y2 + 12 * px, class: "scan-marke",
        "font-size": 10 * px, "stroke-width": 3 * px,
        fill: SLOT_FARBE[s.treffer.foreign ? "fremditem" : "treffer"]}, s.treffer.name));
    }
    const [kx, ky] = scanZuBild(s.klick[0] + v[0], s.klick[1] + v[1]);
    const arm = 4 * px;
    svg.appendChild(svgEl("path", {class: "scan-kreuz" + aus,
      d: `M${kx - arm} ${ky}H${kx + arm}M${kx} ${ky - arm}V${ky + arm}`}));
  }

  if (scanArt !== "item") erkOverlay(svg, px);

  // Der Suchbereich der Slot-Erkennung steht, bis die Farbe gezeigt ist. Ohne
  // ihn klickt man den Hintergrund an, ohne zu sehen, worin gesucht wird — und
  // ein zu eng gezogener Bereich saehe genauso aus wie ein zu weiter.
  if (SC.search_area) {
    const [ax, ay] = scanZuBild(SC.search_area[0], SC.search_area[1]);
    const [bx, by] = scanZuBild(SC.search_area[2], SC.search_area[3]);
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
 * Dieselbe Frage wie `_selection_slots()` in der Bruecke, und sie muss dieselbe
 * Antwort geben: was man ziehen kann, ist genau das, worauf „loeschen" und
 * „Groesse angleichen" wirken. Die Seite beantwortet sie nur fuer die Geste
 * (was liegt unter dem Zeiger), gerechnet wird weiterhin drueben. */
function scanGewaehlteSlots() {
  if (!SC) return [];
  const namen = SC.selection.length ? SC.selection
    : (SC.wahl.kind === "slot" && SC.wahl.name ? [SC.wahl.name] : []);
  return SC.slots.filter((s) => namen.includes(s.name));
}

function scanInSlot(slot, position) {
  return position[0] >= slot.region[0] && position[0] <= slot.region[2]
      && position[1] >= slot.region[1] && position[1] <= slot.region[3];
}

/** Holt den gewaehlten Slot in die Sichtbarkeit der Buehne.
 *
 * Einen Slot in der Liste anzuklicken markiert ihn im Bild — bei 45 Slots auf
 * 1:1 liegt er dabei aber meist ausserhalb.
 *
 * Gescrollt wird NUR, wenn er wirklich draussen liegt, und nur beim Wechsel der
 * Auswahl: eine Buehne, die bei jedem Neuzeichnen springt, nimmt einem die
 * Stelle weg, die man gerade ansieht. */
function scanZeigeGewaehlten() {
  if (!SC || !SC.photo || SC.wahl.kind !== "slot") { scanGezeigt = ""; return; }
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

function scanStelleAusEvent(e, amBildrand = false) {
  const rand = $("scan-overlay").getBoundingClientRect();
  if (!rand.width || !rand.height || !SC || !SC.photo) return null;
  let bx = (e.clientX - rand.left) / rand.width * SC.photo.width;
  let by = (e.clientY - rand.top) / rand.height * SC.photo.height;
  if (amBildrand) {
    bx = Math.max(0, Math.min(SC.photo.width, bx));
    by = Math.max(0, Math.min(SC.photo.height, by));
  }
  return scanZuSchirm(bx, by);
}

/** Eine Ecke ausserhalb des Screenshots gehoert beim automatischen Finden
 * trotzdem zur mittleren Arbeitsflaeche. Sie wird auf den naechsten Bildrand
 * geklemmt: dort enden die Pixel, in denen OpenCV suchen kann. Seitenleisten,
 * Werkzeugleiste und Ergebnisboxen sind keine Zeichenflaeche. */
function scanSuchStelleAusBuehne(e) {
  const flaeche = $("scan-flaeche");
  if (!SC || SC.modus !== "finden" || flaeche.contains(e.target)) return null;
  if (e.target.closest("#scan-canvas-bar, #scan-ergebnis, #scan-bibliothek")) return null;
  return scanStelleAusEvent(e, true);
}

/* --------------------------------------------------------------- Inspektor */

/** Die rechte Spalte neu bauen — und dabei den Fokus selbst hinüberretten.
 *
 * **Der Schutz sitzt HIER, nicht bei den Aufrufern.** `zeichneScans()` hatte
 * ihn, aber es gibt einen zweiten Weg: `scanVorschauenHolen()` baut die Spalte
 * direkt neu, sobald ein nachgeladenes Template ankommt. Genau das passiert beim
 * UMBENENNEN — unter dem neuen Namen gibt es noch keine Vorschau —, und dort
 * ging der Fokus verloren, während er beim Tippen einer Priorität stehen blieb.
 * Ein Schutz, an den jeder Aufrufer denken muss, ist einer, den einer vergisst. */
function scanInspektor() {
  const merk = fokusMerken();
  scanInspektorBauen();
  fokusHerstellen(merk);
}

function scanInspektorBauen() {
  const ziel = $("scan-insp");
  ziel.replaceChildren();
  if (SC.review) return scanReview(ziel);
  const kopf = el("div", {class: "abschnitt scan-kopf"},
    el("div", {class: "reihe"},
      el("span", {class: "ueberschrift wachse"},
         SC.dirty ? "NICHT GESPEICHERT" : scanSpaltenTitel()),
      SC.dirty ? el("span", {class: "punkt-offen"}) : null),
    // **Der Hauptprozess schreibt dieselben Dateien.** Ein Lauf mit
    // Auto-Lernen legt Items an und speichert sie; ohne diesen Hinweis sucht
    // man sie hier vergeblich und haelt es fuer einen Fehler beim Lernen.
    // Bei ungespeicherten Änderungen zwei Knöpfe statt einer Rückfrage: was
    // passiert, steht dann VOR dem Klick da und nicht danach.
    SC.foreign ? el("div", {class: "fremdhinweis"},
      el("span", {}, "Auf Platte hat sich etwas geändert — vermutlich hat ein "
        + "Lauf Items dazugelernt."),
      el("div", {class: "reihe"},
        SC.dirty ? el("button", {class: "btn haupt", onclick: async () => {
          await rufScan("scan_save");
          await rufScan("scan_reload", {verwerfen: true});
        }}, "Speichern & neu laden") : null,
        el("button", {class: "btn", onclick: () => rufScan("scan_reload",
                                                           {verwerfen: true})},
           SC.dirty ? "Änderungen verwerfen & neu laden" : "Neu laden"))) : null,
    el("button", {class: "btn haupt", onclick: () => rufScan("scan_save")},
       "Speichern"),
    el("div", {class: "knopfpaar"},
      scanArt === "item"
        // **Derselbe Befehl heisst ueberall gleich.** Er stand hier als „Items
        // erkennen" und im Assistenten als „Erkennung testen" — zwei Namen fuer
        // einen Knopf, und man probiert beide aus, weil man annimmt, sie taeten
        // Verschiedenes.
        ? el("button", {class: "btn", disabled: !fotoDa() || !SC.slots.length,
                        title: "Hält jeden Slot gegen die Item-Profile und schreibt "
                               + "das Ergebnis an Bild und Item-Liste",
                        onclick: () => rufScan("scan_recognize")}, "Items erkennen")
        : el("button", {class: "btn", disabled: !fotoDa() || !erkScan(),
                        title: "Erkennen, anzeigen — die Aktion wird NICHT ausgeführt",
                        onclick: () => erkTesten()},
             scanArt === "boss" ? "Boss-Scan testen" : "Icon-Scan testen"),
      // **Der Knopf heisst „Zurück", die Beschreibung steht im Tooltip.** Er
      // trug den letzten Schritt im Namen („↶ 'Bogen Zeus': Priorität") — das
      // ist die genauere Auskunft und die schlechtere Beschriftung: sie wurde
      // zweizeilig, wechselte bei jeder Änderung ihre Länge, und was der Knopf
      // TUT, musste man aus ihr heraussuchen. Was zurückgenommen wird, liest,
      // wer nachfragt; dass es überhaupt etwas gibt, sagt der aktive Zustand.
      el("button", {class: "btn scan-undo", disabled: !SC.undo.tiefe,
                    title: SC.undo.tiefe
                      ? "STRG+Z — nimmt zurück: " + SC.undo.was
                        + " (" + SC.undo.tiefe + " Schritte gemerkt)"
                      : "Nichts zum Rückgängigmachen",
                    onclick: () => rufScan("scan_undo")}, "↶ Zurück")));
  // **Der Katalog-Knopf braucht KEIN eingeschaltetes LLM.** Die Kategorie haengt
  // am Namen: heisst ein Item „Citadel Helmet", steht im Katalog „Helm" — ob den
  // Namen ein Mensch getippt oder ein Modell vorgeschlagen hat, ist gleichgueltig.
  // Er steht deshalb neben „Items erkennen" und nicht bei den LLM-Sachen.
  if (scanArt === "item" && SC.katalog_an) {
    kopf.appendChild(el("button", {class: "btn breit",
      title: "Setzt Kategorie und Priorität für jedes Item dieses Scans, dessen "
             + "Name im Katalog steht. Namen, die er nicht kennt, bleiben "
             + "unangetastet. Die Priorität wird innerhalb dieses Scans dicht "
             + "vergeben (teuerstes Item einer Kategorie bekommt P1).",
      onclick: () => rufScan("scan_catalog_apply")},
      "⊞ Aus Katalog einordnen"));
  }
  // **Sechsundfuenfzig Masken aufzuklappen ist kein Bedienweg.** Den Knopf gab
  // es nur AM einzelnen Item — richtig fuer die Korrektur eines Namens, falsch
  // fuer den Normalfall: nach dem Lernen heissen sie alle „Item 1“ … „Item 56“,
  // und genau dann will man einmal ueber alle. Er steht deshalb hier oben,
  // neben dem Katalog-Knopf, mit derselben Bezugsregel (der offene Scan).
  if (scanArt === "item" && SC.llm_an) {
    const mitVorlage = (SC.items || []).filter((i) => (i.vorlagen || []).length).length;
    if (mitVorlage) {
      kopf.appendChild(el("button", {class: "btn breit",
        title: mitVorlage + " Item(s) mit Vorlage gehen nacheinander an das Modell. "
               + (SC.katalog_an
                  ? "Jeder Name wird aus dem Katalog gewählt, danach werden "
                    + "Kategorie und Priorität gesetzt."
                  : "Ohne Katalog rät das Modell frei — die Namen sind dann "
                    + "Vorschläge, keine echten Item-Namen.")
               + " Das dauert; STRG+Z nimmt den ganzen Durchgang zurück.",
        onclick: () => scanAutonameLauf({alle: true})},
        SC.katalog_an ? "✦ Alle aus Katalog benennen" : "✦ Alle mit LLM benennen"));
    }
  }
  // **Reiter und Filter gehoeren zum Kopf, nicht zur Liste.** Der Kopf bleibt
  // beim Scrollen stehen (`.scan-kopf` ist `sticky`) — bei sechzig Masken war
  // die Reiterleiste sonst nach drei Umdrehungen weg, und mit ihr der Weg
  // zurueck in eine andere Liste.
  const tabs = el("div", {class: "tabs klein breit"});
  const filter = el("div", {class: "scan-filter"});
  scanListenBlock(tabs, filter, null);
  kopf.appendChild(tabs);
  if (scanMaskenRechts()) {
    // **Sortieren ist ein Knopf, kein Nebeneffekt des Tippens.** Sortierte sich
    // die Liste nach jeder Aenderung neu, springt genau die Zeile weg, an der
    // man gerade arbeitet.
    filter.appendChild(el("button", {class: "btn still",
      title: "Ordnet die Liste neu nach Kategorie, Priorität und Name. Sonst "
             + "bleibt die Reihenfolge stehen, damit beim Tippen nichts springt.",
      onclick: () => { scanOrdnungVergessen(); zeichneScans(); }}, "↕ Sortieren"));
    const kind = scanListe === "slots" ? "slot" : "item";
    const eintraege = scanListe === "slots" ? SC.slots : SC.items;
    const irgendAn = eintraege.some((e) => !!e.active);
    filter.appendChild(el("button", {class: "btn still", disabled: !eintraege.length,
      title: "Schaltet alle " + (kind === "slot" ? "Slots" : "Items")
             + (irgendAn ? " aus." : " ein."),
      onclick: () => rufScan("scan_toggle_all",
                             {kind: kind, active: !irgendAn})},
      irgendAn ? "Alle aus" : "Alle ein"));
  }
  if (filter.childNodes.length) kopf.appendChild(filter);
  ziel.appendChild(kopf);

  const rumpf = el("div", {class: "abschnitt wachsend"});
  // **Hier steht die ganze Liste, nicht ein einzelnes Ding.** Was zum
  // GEWAEHLTEN gehoert, klappt in seiner Maske auf statt daneben zu stehen.
  // Eine Mehrfachauswahl meint etwas anderes als eine Maske: sie hat keinen
  // Namen und keine Einzelfelder, nur das, was auf alle wirkt. Deshalb steht
  // sie ueber der Liste und nicht in ihr.
  if (scanMaskenRechts() && SC.selection.length > 1) {
    const sammel = el("div", {class: "scan-sammel"});
    scanInspAuswahl(sammel);
    rumpf.appendChild(sammel);
  }
  const liste = el("div", {class: "spalte", style: "gap:3px"});
  scanListenBlock(null, null, liste);
  rumpf.appendChild(liste);
  // Boss und Icon tragen keine Masken — was zum Gewaehlten gehoert, steht
  // deshalb UNTER der Liste statt in ihr. Abgesetzt, damit man sieht, wo die
  // Liste aufhoert und das eine Ding anfaengt.
  if (!scanMaskenRechts()) {
    const insp = el("div", {class: "spalte erk-insp"});
    erkInspektor(insp);
    if (insp.childNodes.length) rumpf.appendChild(insp);
  }
  if (!rumpf.childNodes.length) {
    rumpf.appendChild(el("p", {class: "hinweis"},
      "Nichts gewählt. Links eine Zeile anklicken — oder im Bild einen Slot."));
  }
  ziel.appendChild(rumpf);
}

/** Was in der Kopfzeile der rechten Spalte steht: die offene Liste.
 *
 * Sie stand als feste Aufzaehlung da („SCANS · SLOTS · ITEMS"), auch wenn nur
 * eine davon zu sehen war. Eine Ueberschrift, die drei Dinge nennt und eines
 * zeigt, beschreibt das Fenster statt den Inhalt. */
function scanSpaltenTitel() {
  if (scanArt === "icon") return "ICON-SCANS";
  if (scanArt === "boss") return erkBibliothek() ? "BOSS-BIBLIOTHEK" : "BOSS-SCANS";
  return {scans: "ITEM-SCANS", slots: "SLOTS", items: "ITEMS"}[scanListeAktiv()]
         || "SCANS";
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
  const existing = allePrioritaeten();
  if (existing) kopf.appendChild(existing);
  const sammelKategorie = kategorieWahl("", scanReviewKategorienAktualisieren, {
    empty: "— Kategorie für alle ausgewählten —",
    platzhalter: "Kategorie für alle ausgewählten Items",
    key: "review-sammel",
  });
  kopf.appendChild(el("div", {class: "scan-review-sammel"}, sammelKategorie,
    el("button", {class: "btn still", type: "button",
      onclick: () => scanReviewKategorieAufAuswahl(sammelKategorie)},
    "Auf ausgewählte anwenden")));
  ziel.appendChild(kopf);
  const liste = el("div", {class: "abschnitt wachsend scan-review"});
  for (const z of SC.review.rows) {
    const haken = el("input", {type: "checkbox", class: "scan-review-haken"});
    const standardAuswahl = !!z.ticked;
    const vorhandenerName = String(z.existing || "");
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
    const kat = kategorieWahl(z.category || "", scanReviewKategorienAktualisieren,
      {klasse: "scan-review-kategorie", key: "review:" + z.slot});
    const prio = el("input", {
      class: "scan-review-prio",
      type: "number", value: z.priority ?? 1, min: 0, step: 1,
      title: "Kleinere Zahl gewinnt; 0 setzt das Item in seiner Kategorie nach vorn",
    });
    const status = el("span", {class: "klein mono scan-review-status"});
    const wechsel = vorhandenerName ? el("button", {
      class: "btn still scan-review-aktion", type: "button",
      title: "Nur verwenden, wenn die automatische Erkennung falsch war",
    }, "Als anderes Item lernen") : null;
    let row;
    const synchronisiere = () => {
      const bestehend = bekannteNamen.has(name.value.trim());
      const normalerTreffer = !!vorhandenerName && !alsAnderes;
      name.disabled = normalerTreffer;
      // Kategorie und Priorität des erkannten Profils sind direkt änderbar.
      // Wird ein anderer vorhandener Name gewählt, schützen wir dagegen dessen
      // Werte vor den leeren Standards der Aktion „Als anderes Item lernen“.
      kat.sperren(bestehend && !normalerTreffer);
      prio.disabled = bestehend && !normalerTreffer;
      row.dataset.alsAnderes = alsAnderes ? "true" : "false";
      row.classList.toggle("ueberspringen", !haken.checked);
      if (!haken.checked) {
        status.textContent = z.slot + " · wird nicht gelernt oder geändert";
      } else if (alsAnderes) {
        status.textContent = z.slot + (bestehend
          ? " · vorhandenes „" + name.value.trim() + "“ gewählt · Vorlage ergänzen"
          : " · wird als neues Item gelernt");
      } else if (z.variante) {
        status.textContent = z.slot + " · „" + vorhandenerName +
          "“ erkannt · neue Vorlage für diese Slot-Größe";
      } else if (z.duplikat) {
        status.textContent = z.slot + " · „" + vorhandenerName +
          "“ erkannt · bereits in diesem Scan eingerichtet";
      } else {
        status.textContent = z.slot + (bestehend
          ? " · neue Vorlage für „" + name.value.trim() + "“" : " · neues Item");
      }
    };
    name.addEventListener("input", synchronisiere);
    row = el("div", {class: "scan-review-zeile" +
        (z.variante ? " variante" : z.duplikat ? " duplikat fertig" : ""),
      "data-slot": z.slot, "data-existing": vorhandenerName,
      "data-als-anderes": "false"}, haken, status,
      z.image ? el("img", {class: "scan-review-bild", src: z.image, alt: ""})
             : el("span", {class: "scan-review-bild leer"}),
      el("div", {class: "felder"},
        name, el("div", {class: "scan-review-sortierung"}, kat,
          el("label", {class: "scan-review-prio"}, el("span", {}, "Priorität"), prio)),
        wechsel));
    row._reviewSynchronisieren = synchronisiere;
    const gleicheAuswahlSetzen = () => {
      if (!vorhandenerName || alsAnderes) {
        synchronisiere();
        return;
      }
      // Dasselbe Item kann in mehreren Slots liegen. Ein Häkchen steht für die
      // Item-Zuordnung, deshalb bewegen sich alle Vorkommen gemeinsam.
      for (const andere of document.querySelectorAll(".scan-review-zeile")) {
        if (andere.dataset.existing !== vorhandenerName ||
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
        kat.value = z.category || "";
        prio.value = z.priority ?? 1;
        haken.checked = vorherigeAuswahl;
        wechsel.textContent = "Als anderes Item lernen";
      }
      row.classList.toggle("anderes", alsAnderes);
      synchronisiere();
      if (!alsAnderes) gleicheAuswahlSetzen();
      scanReviewKategorienAktualisieren();
    });
    synchronisiere();
    liste.appendChild(row);
  }
  liste.appendChild(el("datalist", {id: itemsId},
    [...bekannteNamen].map((name) => el("option", {value: name}))));
  liste.appendChild(el("div", {class: "knopfpaar", style: "margin-top:8px"},
    el("button", {class: "btn", onclick: () => rufScan("scan_learn_preview_cancel")}, "Abbrechen"),
    el("button", {class: "btn haupt", onclick: scanReviewUebernehmen}, "Auswahl anwenden")));
  ziel.appendChild(liste);
}

function scanReviewUebernehmen() {
  // **Gelesen wird ueber Klassen, nicht ueber Positionen.** Vorher wurden die
  // Felder einer Zeile durchnummeriert aus `querySelectorAll` gegriffen — wer
  // eines dazwischen einbaut (oder ein Textfeld durch eine Auswahlliste
  // ersetzt, wie es die Kategorie jetzt ist), verschiebt still alle folgenden.
  // Ein Import, der die Prioritaet als Kategorie liest, faellt niemandem auf.
  const rows = [...document.querySelectorAll(".scan-review-zeile")].map((n) => ({
    slot: n.dataset.slot,
    ticked: n.querySelector(".scan-review-haken").checked,
    existing: n.dataset.existing || "",
    als_anders: n.dataset.alsAnderes === "true",
    name: n.querySelector(".scan-review-name").value.trim(),
    category: n.querySelector(".scan-review-kategorie").value(),
    priority: Number(n.querySelector(".scan-review-prio").value),
  }));
  rufScan("scan_learn_preview_apply", {rows: rows});
}

/** Was zum gewaehlten Slot gehoert — im Detailteil seiner Maske.
 *
 * **Der Name steht in der Maske, nicht hier.** Dieselbe Regel wie beim Item und
 * beim Klick-Block im Sequenz-Editor: was dem Ding GEHOERT (seine Identitaet),
 * steht beim Ding; hier bleibt, was man daran EINSTELLT. */
function scanSlotDetails(ziel, s) {
  const setze = (feld, value) => rufScan("scan_slot_set", {name: s.name, feld: feld, value: value});

  ziel.appendChild(el("div", {class: "knopfpaar"},
    el("button", {class: "btn still",
      title: "Wohin geklickt wird, wenn in diesem Slot ein gesuchtes Item liegt",
      onclick: () => rufScan("scan_mode_set", {modus: "klick"})},
      "Klickpunkt setzen"),
    el("button", {class: "btn still", disabled: !fotoDa(),
      title: "Die Farbe des leeren Slots — sie wird beim Item-Lernen abgezogen, "
             + "damit nicht der Rahmen als Merkmal gelernt wird",
      onclick: () => rufScan("scan_mode_set", {modus: "messen"})},
      "Hintergrund messen")));

  const erweitert = el("details", {class: "scan-erweitert"},
    el("summary", {}, "Koordinaten und Hintergrund"));
  erweitert.appendChild(ueberschrift("FLÄCHE",
    "In Bildschirm-Koordinaten. Bequemer: Modus „Neuer Slot“ und zwei Ecken " +
    "im Bild anklicken — oder den Slot im Bild ziehen.", "flaeche"));
  erweitert.appendChild(el("div", {class: "gitter2"},
    zahlfeld("Links", s.region[0], (v) => setze("x1", v)),
    zahlfeld("Oben", s.region[1], (v) => setze("y1", v)),
    zahlfeld("Rechts", s.region[2], (v) => setze("x2", v)),
    zahlfeld("Unten", s.region[3], (v) => setze("y2", v))));
  erweitert.appendChild(ueberschrift("KLICKPUNKT",
    "Wohin geklickt wird, wenn in diesem Slot ein gesuchtes Item liegt.", "klickpunkt"));
  erweitert.appendChild(el("div", {class: "gitter2"},
    zahlfeld("X", s.klick[0], (v) => setze("kx", v)),
    zahlfeld("Y", s.klick[1], (v) => setze("ky", v))));
  erweitert.appendChild(color_swatch("Hintergrund", s.color, (v) => setze("color", v),
    "Die Farbe des leeren Slots. Sie wird beim Item-Lernen abgezogen, damit " +
    "nicht der Rahmen als Merkmal gelernt wird.", "hintergrund"));
  ziel.appendChild(erweitert);

  ziel.appendChild(el("div", {class: "knopfpaar"},
    el("button", {class: "btn", disabled: !fotoDa(),
                  onclick: () => rufScan("scan_item_learn", {slot: s.name})},
       "Item lernen"),
    el("button", {class: "btn gefahr", onclick: () => rufScan("scan_slot_delete")},
       "löschen")));
  if (fotoDa()) {
    // „Alle" heisst: alle Slots des offenen Scans, nicht des ganzen Bestands
    // (`_scan_slots()` in scans.py). Das steht im Knopf, weil es vorher
    // stillschweigend anders war — und die Meldung danach ratlos machte.
    ziel.appendChild(el("button", {class: "btn still",
      title: SC.offen ? "Alle Slots aus „" + SC.offen + "“ — nicht der ganze Bestand"
                      : "Alle Slots im Bestand (kein Scan offen)",
      onclick: () => rufScan("scan_learn_preview", {scope: "alle"})},
      SC.offen ? "Items dieses Scans prüfen & lernen" : "alle Items prüfen & lernen"));
  }
  // Der Treffer ist ein Vorschlag, keine Festlegung. Stimmt er nicht, lernt
  // man aus demselben Slot ein zweites Item („Item lernen" oben); gehoert er
  // nur noch nicht zum Scan, ist es ein Klick.
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
    "klicken). STRG-Klick nimmt einzelne dazu oder heraus. Alles hier lässt " +
    "sich mit STRG+Z zurücknehmen.", "selection"));
  ziel.appendChild(el("p", {class: "hinweis"}, SC.selection.length + " Slots gewählt"));
  // Die Namen stehen da, nicht nur die Zahl: was man loescht, soll man vorher
  // lesen koennen. Bei dreissig wird die Liste lang - dafuer scrollt sie.
  ziel.appendChild(el("div", {class: "spalte", style: "gap:2px;max-height:160px;"
    + "overflow-y:auto;font-family:var(--mono);font-size:11px;color:var(--muted)"},
    ...SC.selection.map((n) => el("span", {}, n))));

  ziel.appendChild(ueberschrift("LAGE UND GRÖSSE",
    "Verschieben: im Bild ziehen oder Pfeiltasten (SHIFT = 10 px) — der " +
    "Klickpunkt geht mit. Angleichen zieht alle auf die MITTLERE Grösse, um " +
    "ihre Mitte herum: ein einzelner Verklicker soll nicht alle anderen " +
    "verbiegen.", "auswahl-lage"));
  ziel.appendChild(el("button", {class: "btn breit",
    onclick: () => rufScan("scan_align_size")}, "Grösse angleichen"));

  ziel.appendChild(ueberschrift("HINTERGRUND UND ITEMS",
    "Gemessen wird jeder Slot an sich selbst — eine gemeinsame Farbe für alle " +
    "wäre an jedem einzelnen ein bisschen falsch.", "auswahl-lernen"));
  ziel.appendChild(el("button", {class: "btn breit", disabled: !fotoDa(),
    onclick: () => rufScan("scan_selection_color")}, "Hintergrund neu messen"));
  ziel.appendChild(el("button", {class: "btn breit", disabled: !fotoDa(),
    title: "Aus jedem gewählten Slot ein Item — Doppelte werden übersprungen",
    onclick: () => rufScan("scan_learn_preview", {scope: "selection"})},
    SC.selection.length + " Items prüfen & lernen"));

  ziel.appendChild(el("div", {class: "knopfpaar", style: "margin-top:14px"},
    el("button", {class: "btn", onclick: () => rufScan("scan_cancel")},
       "Auswahl aufheben"),
    el("button", {class: "btn gefahr", onclick: () => rufScan("scan_slot_delete")},
       SC.selection.length + " löschen")));
}

/** Was man an einem Item selten ändert: Vorlagen, Marker, Konfidenz, Löschen.
 *
 * **Steht IN der Maske des gewählten Items**, nicht daneben: sonst sieht man
 * beim Arbeiten an einem Ding zwischen zwei Orten hin und her, und die Maske
 * trägt seine Identität ohnehin schon. Dieselbe Regel wie „was dem Punkt
 * gehört, steht beim Punkt" im Sequenz-Editor. */
function scanItemDetails(ziel, i) {
  const setze = (feld, value) => rufScan("scan_item_set", {name: i.name, feld: feld, value: value});
  const image = scanVorschauen.get(i.name);
  if (image) ziel.appendChild(el("img", {class: "scan-gross", src: image}));
  if ((i.detected_in || []).length) {
    ziel.appendChild(el("p", {class: "hinweis", style: "color:var(--slot-ok)"},
      "Gerade erkannt in: " + i.detected_in.join(", ")));
  }
  ziel.appendChild(prioritaetsUebersicht(i.category, i.name));
  const erweitert = el("details", {class: "scan-erweitert"},
    el("summary", {}, "Erweiterte Erkennungseinstellungen"));
  erweitert.appendChild(zahlfeld("Konfidenz", i.konfidenz, (v) => setze("konfidenz", v),
      {min: 0, max: 1, step: "any"},
      "Wie gut das Template passen muss (0–1).", "konf"));
  erweitert.appendChild(el("p", {class: "hinweis"},
    (i.template_sizes || []).length
      ? "Gelernte Slot-Größen: " + i.template_sizes.map((g) => g[0] + "×" + g[1]).join(", ")
      : "Keine Bildvorlage — nur Marker-Farben."));
  if ((i.vorlagen || []).length) {
    erweitert.appendChild(el("div", {class: "spalte", style: "gap:5px"},
      (i.vorlagen || []).map((v) => el("div", {class: "reihe"},
        el("span", {class: "hinweis mono wachse"}, v),
        el("button", {class: "btn still", title: "Nur vom Item lösen; Datei bleibt erhalten",
          onclick: () => rufScan("scan_item_remove_template", {name: i.name, file: v})},
          "Vorlage entfernen")))));
  }
  if ((i.missing_scan_sizes || []).length) {
    erweitert.appendChild(el("p", {class: "hinweis", style: "color:var(--accent)"},
      "Für diesen Scan noch nicht gelernt: " +
      i.missing_scan_sizes.map((g) => g[0] + "×" + g[1]).join(", ") +
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
  // Der Knopf hing einmal an `kategorie === "Auto"` — also genau an den Items,
  // die schon einen Namen vom Auto-Lernen haben. Wer 56 Vorlagen von Hand als
  // „item_1“ … angelegt hat, fand ihn deshalb nie, obwohl das der Fall ist, für
  // den man ihn sucht. Gebraucht wird eine Vorlage, sonst gibt es nichts zu sehen.
  if ((i.vorlagen || []).length) {
    ziel.appendChild(el("button", {class: "btn breit", style: "margin-top:10px",
      title: SC.katalog_an
        ? "Wählt einen der echten Item-Namen aus dem Katalog und ordnet danach ein."
        : "Fragt das LLM nach einem freien Namensvorschlag. Mit eingeschaltetem "
          + "Item-Katalog wählt es stattdessen aus den echten Namen des Spiels.",
      onclick: () => scanAutonameLauf({namen: [i.name]})},
      SC.katalog_an ? "✦ Aus Katalog benennen" : "✦ Mit LLM benennen"));
  }
  ziel.appendChild(scanItemBestaetigung(i));
  if (i.stumm) {
    ziel.appendChild(el("p", {class: "hinweis", style: "color:var(--err)"},
      "Weder Template noch Marker — dieses Item wird nie erkannt."));
  }
  ziel.appendChild(el("button", {class: "btn gefahr", style: "margin-top:14px",
    onclick: () => rufScan("scan_item_delete")}, "Item löschen"));
}

/** Der Klick NACH dem Klick: „wirklich verkaufen?" wegdrücken.
 *
 * **Das Feld gab es im Modell und in den Konsolen-Editoren seit jeher** — im
 * Studio war es die einzige Item-Eigenschaft ohne Bedienelement, und wer es
 * suchte, fand nichts. Ohne die Bestätigung bleibt das Popup stehen, und der
 * Scan erreicht den nächsten Slot gar nicht mehr.
 *
 * Gesetzt wird über einen PUNKT, nie über zwei Zahlen: die Koordinate steht in
 * der Punktliste in `sequence.json` und sonst nirgends. Zwei Wege dorthin, beide vorhanden — einen
 * bekannten Punkt wählen, oder die Stelle im Bild anklicken (dasselbe Werkzeug,
 * das Boss und Icon schon benutzen). */
function scanItemBestaetigung(i) {
  const setze = (feld, value) => rufScan("scan_item_set",
                                        {name: i.name, feld: feld, value: value});
  const kasten = el("div", {class: "spalte", style: "gap:7px"});
  kasten.appendChild(ueberschrift("BESTÄTIGUNGSKLICK",
    "Manche Spiele fragen nach dem Klick nach („wirklich verkaufen?“). Ohne "
    + "die Bestätigung bleibt das Popup stehen, und der Scan kommt nicht mehr "
    + "zum nächsten Slot. Die Stelle steht als Punkt in sequence.json — dieselbe "
    + "Kalibrierung erfasst sie mit.", "confirmation"));
  const wahl = selection("Punkt", [{value: "", text: "— keine Bestätigung —"}].concat(
    SC.points.map((p) => ({value: p.id, text: "#" + p.id + " " + p.name}))),
    i.confirmation ? i.confirmation.point_id : "", (v) => setze("confirmation", v));
  kasten.appendChild(wahl);
  // Ein Punkt, den es nicht mehr gibt, wird GESAGT statt verschwiegen: der
  // Lauf klickt sonst nichts, und man sucht den Fehler bei der Erkennung.
  if (i.confirmation && i.confirmation.fehlt) {
    kasten.appendChild(el("p", {class: "hinweis", style: "color:var(--err)"},
      i.confirmation.text + " — die Bestätigung greift nicht."));
  }
  kasten.appendChild(el("button", {class: "btn still", disabled: !fotoDa(),
    title: "Die Stelle im Bild anklicken — dabei entsteht ein Punkt, oder ein "
           + "vorhandener an derselben Stelle wird wiederverwendet",
    onclick: () => rufScan("region_mode", {kind: "item", modus: "action"})},
    "Stelle im Bild anklicken"));
  if (i.confirmation) {
    kasten.appendChild(zahlfeld("Wartezeit (s)", i.confirmation_delay,
      (v) => setze("confirmation_delay", v), {min: 0, step: "any"},
      "Zeit zwischen dem Item-Klick und der Bestätigung — das Popup braucht "
      + "einen Moment, bis es da ist.", "bestaetigungszeit"));
  }
  return kasten;
}

/** Was zum offenen Item-Scan gehoert — im Detailteil seiner Maske. */
function scanScanDetails(ziel, c) {
  const setze = (feld, value) => rufScan("scan_set", {name: c.name, feld: feld, value: value});

  ziel.appendChild(ueberschrift("EINSTELLUNGEN",
    "Welche Slots nach welchen Items durchsucht werden, steht in den Reitern "
    + "daneben: der Haken vor jeder Maske heisst „gehört zu diesem Scan“. Hier "
      + "steht, WIE gesucht wird. Ein Block vom Typ ITEM-SCAN verweist per Name "
      + "auf diesen Scan.", "itemscan"));

  ziel.appendChild(zahlfeld("Farb-Toleranz", c.tolerance, (v) => setze("tolerance", v),
    {min: 0, step: 1},
    "Wie weit eine Marker-Farbe abweichen darf, damit sie noch als gefunden gilt.",
    "tolerance"));
  ziel.appendChild(schalter("Unbekanntes lernen", c.lernen, (v) => setze("lernen", v),
    "Neue Slot-Inhalte werden als Items in die globale Liste gelernt — nie in "
    + "diesen Scan, damit sie nicht ungeprüft geklickt werden.", "lernen"));
  ziel.appendChild(schalter("Slots rückwärts", c.reverse, (v) => setze("reverse", v),
    "Von hinten nach vorn (4, 3, 2, 1). Sinnvoll, wenn das Spiel den Bestand "
    + "nach vorn aufrückt: dann verschiebt ein Klick nicht die noch nicht "
    + "besuchten Slots. Die Richtung gehört zum Inventar, deshalb steht sie hier "
    + "und nicht in den Einstellungen.", "reverse"));
  ziel.appendChild(schalter("Item-Katalog benutzen", c.use_catalog,
    (v) => setze("use_catalog", v),
    "Mit Katalog kennt der Editor die echten Item-Namen des Spiels: „Aus Katalog "
    + "einordnen“ setzt Kategorie und Priorität, und die LLM-Benennung wählt aus "
    + "den echten Namen statt frei zu raten. Die Kategorie hängt am NAMEN, nicht "
    + "am LLM — sie funktioniert auch, wenn du den Namen selbst tippst. Der "
    + "Schalter steht hier und nicht in den Einstellungen, weil ein Katalog "
    + "immer nur für EIN Spiel gilt; wo die Datei liegt, sagt "
    + "„Item-Katalog“ in den Einstellungen.", "katalog"));

  if (c.fehlend.length) {
    ziel.appendChild(el("p", {class: "hinweis", style: "color:var(--err)"},
      "Zeigt ins Leere: " + c.fehlend.join(", ") + ". Der Scan läuft mit dem Rest " +
      "weiter — lieber ein Slot weniger als ein toter Scan."));
  }
  ziel.appendChild(el("button", {class: "btn gefahr",
    title: "Entfernt die Konfiguration und ihre Datei. STRG+Z holt die "
           + "Konfiguration zurück, den gemerkten Screenshot nicht.",
    onclick: () => rufScan("scan_delete", {name: c.name})}, "Diesen Scan löschen"));
}

/* ------------------------------------------- Ansicht: Bosse und Icon-Scans */

/* Dieselbe Buehne, eine andere Frage: ein Boss-Scan ist ein Rechteck auf einem
 * Bild und eine Aktion dahinter, ein Icon-Scan dasselbe ohne Bosse-Liste.
 *
 * Welche Art offen ist, ist reiner Oberflaechenzustand wie `ansicht` und
 * `scanListe` — die Bruecke bekommt bei jedem Befehl gesagt, worauf er wirkt
 * (`{art: "boss"}`). */
let scanArt = "item";
/* Welcher Assistent-Schritt der Erkennungs-Arten offen ist. Eigene Variable
 * neben `scanAssistentSchritt`: die Arten haben verschieden viele Schritte, und
 * ein gemeinsamer Zaehler stuende beim Umschalten auf einem, den es nicht gibt. */
let scanErkSchritt = null;

const SCAN_ARTEN = ["item", "boss", "icon"];

/* Welche Bruecken-Methode zu welcher Art gehoert — als Tabelle.
 *
 * Als Ternaeroperator an jeder Aufrufstelle waeren die Namen sechsmal da, und
 * der Test „jeder Aufruf der Seite passt zur Bruecke" faende keinen davon: er
 * sucht den Methodennamen direkt hinter der oeffnenden Klammer. Hier stehen sie
 * einmal und sind messbar (`tests/vertrag/studio_erkennung.py`). */
const ERK_BEFEHL = {
  boss: {oeffnen: "boss_scan_open", neu: "boss_scan_new",
         scan_feld: "boss_scan_set", feld: "boss_set",
         loeschen: "boss_scan_delete", testen: "boss_test"},
  icon: {oeffnen: "icon_scan_open", neu: "icon_scan_new",
         scan_feld: "icon_set", feld: "icon_set",
         loeschen: "icon_scan_delete", testen: "icon_test"},
};

/** Der Befehlsname fuer die offene Art. */
function erkBefehl(key) {
  return (ERK_BEFEHL[scanArt] || ERK_BEFEHL.boss)[key];
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

function scanArtSetzen(kind) {
  if (!SCAN_ARTEN.includes(kind) || kind === scanArt) return;
  scanArt = kind;
  scanErkSchritt = null;
  // Eine andere Art ist ein anderer Zusammenhang: die Vorgabe gilt wieder.
  scanListe = null;
  // Ein Werkzeug der alten Art wuerde in der neuen etwas anderes tun.
  rufScan("scan_cancel");
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
  kinder.push(selection("", [{value: "", text: liste.length
      ? "— keiner gewählt —" : (boss ? "— noch kein Boss-Scan —" : "— noch kein Icon-Scan —")}]
    .concat(liste.map((c) => ({value: c.name, text: c.name}))),
    offen ? offen.name : "",
    (v) => rufScan(erkBefehl("oeffnen"), {name: v})));
  if (offen) {
    kinder.push(feld("Name", offen.name,
      (v) => rufScan(erkBefehl("scan_feld"),
                     {name: offen.name, feld: "name", value: v})));
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
function erkKarte(nr, title, stamp, fertig, inhalt) {
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
      el("span", {class: "wachse"}, el("b", {}, title), el("small", {}, stamp)),
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
  const placed = (r[2] - r[0]) > 0 && (r[3] - r[1]) > 0
    && !(r[0] === 0 && r[1] === 0 && r[2] === 100 && r[3] === 100);
  const setze = (i, v) => {
    const neu = r.slice();
    neu[i] = Number(v) || 0;
    erkFeld("region", neu);
  };
  return erkKarte(2, "Region", placed
    ? "(" + r[0] + "," + r[1] + ") → (" + r[2] + "," + r[3] + ")  ·  "
      + (r[2] - r[0]) + "×" + (r[3] - r[1])
    : "Noch nicht gesetzt", placed, [
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
      onclick: () => rufScan("region_mode", {kind: scanArt, modus: "region"})},
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
      onclick: () => rufScan("boss_new")}, "+ Boss anlegen"),
    el("button", {class: "btn still scan-assistent-haupt", disabled: !fotoDa()
        || !erkBosse().length,
      onclick: () => rufScan("boss_test_all")}, "Alle gegen dieses Bild halten"),
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
    c.use_ocr ? segment([{value: true, text: "als Fallback"}, {value: false, text: "primär"}],
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
      el("button", {class: "btn still", onclick: () => rufScan("ocr_check")},
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
    c.use_llm ? segment([{value: true, text: "als Fallback"}, {value: false, text: "primär"}],
      c.llm_fallback, (v) => erkFeld("llm_fallback", v)) : null,
    el("div", {class: "reihe"},
      el("span", {class: "scan-lampe" + lampe}),
      // Ohne Probe steht hier „noch nicht geprueft", nicht der Endpunkt: ein
      // leeres Feld (die Voreinstellung ist leer) saehe aus wie ein Fehler.
      // Der Endpunkt gehoert in den Tooltip — dort sucht man ihn, wenn die
      // Lampe rot ist.
      el("span", {class: "klein wachse", title: b.llm_endpoint || ""},
        !b.llm_stand ? "noch nicht geprüft"
          : (b.llm_stand.erreichbar ? "erreichbar (" + b.llm_stand.duration + " ms)"
                                    : "nicht erreichbar")),
      el("button", {class: "btn still", onclick: () => rufScan("llm_check")}, "testen")),
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
  const text = (SC.actions.boss.find((a) => a.value === c.default_action) || {}).text
    || c.default_action;
  return erkKarte(5, "Fallback", "wenn kein Boss erkannt: " + text, true, [
    el("p", {class: "hinweis"}, "Greift, wenn keiner der Bosse passt — und auch "
      + "dann, wenn OCR und LLM nichts finden."),
    erkAktionsKacheln(SC.actions.boss, c.default_action,
                      (v) => erkFeld("default_action", v)),
    c.default_action === "item_scan"
      ? selection("Item-Scan", [{value: "", text: "— keiner —"}].concat(
          SC.item_scan_namen.map((n) => ({value: n, text: n}))), c.default_scan || "",
          (v) => erkFeld("default_scan", v))
      : null,
  ]);
}

/** Schritt 3 (Icon): Template oder Farb-Marker. */
function erkErkennungSchritt(c) {
  return erkKarte(3, "Erkennung", c.erkennung === "template"
    ? "Vorlage · min " + c.konfidenz.toFixed(2)
    : (c.erkennung === "marker" ? c.marker.length + " Marker · Toleranz " + c.tolerance
                                : "Noch nichts gesetzt"),
    c.erkennung !== "keine", erkErkennungsFelder(c, "icon"));
}

/** Die Erkennungs-Felder — dieselben fuer Boss und Icon.
 *
 * Beide erkennen ueber Template ODER Farb-Marker; das sind dieselben Felder und
 * dieselben Knoepfe. Zwei Fassungen davon waeren zwei Stellen, an denen ein
 * Griff fehlt — und „Vorlage neu aufnehmen" ist genau der Griff, der heute den
 * ganzen Konsolen-Ablauf kostet. */
function erkErkennungsFelder(objekt, kind, name) {
  const ueber = ERK_BEFEHL[kind].feld;
  const setze = (feld, value) => rufScan(ueber, Object.assign(
    {feld: feld, value: value}, name ? {name: name} : {}));
  const template = objekt.erkennung !== "marker";
  return [
    segment([{value: "template", text: "Template"}, {value: "marker", text: "Farb-Marker"}],
      objekt.erkennung === "marker" ? "marker" : "template",
      // Umschalten heisst hier: das andere loswerden. Beides stehen zu lassen
      // waere `_check_profile_match`s UND — dann muessen BEIDE stimmen, und
      // niemand rechnet damit.
      (v) => setze(v === "marker" ? "template" : "marker", v === "marker" ? "" : [])),
    template ? el("div", {class: "reihe", style: "align-items:flex-start"},
      objekt.preview
        ? el("img", {class: "scan-vorlage", src: objekt.preview, alt: ""})
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
      onclick: () => rufScan("template_capture", Object.assign(
        {kind: kind}, name ? {name: name} : {}))}, "Vorlage neu aufnehmen") : null,
    !template ? el("div", {class: "scan-marker"},
      objekt.marker.map((h) => el("span", {class: "scan-farbfeld", style: "background:" + h,
                                           title: h})),
      el("span", {class: "scan-farbfeld leer", title: "noch Platz"})) : null,
    !template ? el("div", {class: "gitter2"},
      zahlfeld("Toleranz", objekt.tolerance === undefined ? 30 : objekt.tolerance,
        (v) => setze("tolerance", v), {min: 0, step: 1},
        "Wie weit eine Marker-Farbe abweichen darf.", "erktoleranz"),
      el("div", {class: "feld-still"}, "gemessen",
        el("span", {class: "mono"}, objekt.marker.length + " Farben"))) : null,
    !template ? el("button", {class: "btn scan-assistent-haupt", disabled: !fotoDa(),
      onclick: () => rufScan("marker_measure", Object.assign(
        {kind: kind}, name ? {name: name} : {}))}, "Marker im Bild neu messen") : null,
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
function erkAktionsKacheln(values, current, beim_setzen) {
  // Dasselbe Raster wie beim Block-Typ im Sequenz-Editor — die Kacheln sollen
  // sich gleich anfuehlen. Auf der Kachel steht das Schlagwort, im Tooltip der
  // Satz: „Zyklus abbrechen" ist auf 9,5 px zweizeilig und unlesbar.
  return el("div", {class: "gitter3"}, values.map((a) =>
    el("button", {class: "typ-chip" + (a.value === current ? " an" : ""),
      title: a.text, onclick: () => beim_setzen(a.value)}, a.kurz)));
}

/** Die Felder hinter einer Aktion — Punkt, Taste, Verzoegerung, Item-Scan. */
function erkAktionsFelder(objekt, kind, name) {
  const ueber = ERK_BEFEHL[kind].feld;
  const setze = (feld, value) => rufScan(ueber, Object.assign(
    {feld: feld, value: value}, name ? {name: name} : {}));
  const felder = [];
  if (objekt.action === "item_scan") {
    felder.push(selection("Item-Scan", [{value: "", text: "— keiner —"}].concat(
      SC.item_scan_namen.map((n) => ({value: n, text: n}))), objekt.scan || "",
      (v) => setze("scan", v)));
    felder.push(selection("Modus", SC.actions.scan_modi.map(
      (m) => ({value: m.value, text: m.text})), objekt.scan_modus,
      (v) => setze("scan_modus", v)));
  }
  if (objekt.action === "click") {
    felder.push(selection("Punkt", [{value: "", text: "— keiner —"}].concat(
      SC.points.map((p) => ({value: p.id, text: "#" + p.id + " " + p.name}))),
      objekt.point_id === null || objekt.point_id === undefined ? "" : objekt.point_id,
      (v) => setze("point", v === "" ? null : Number(v))));
    felder.push(el("button", {class: "btn still", disabled: !fotoDa(),
      onclick: () => rufScan("region_mode", {kind: kind, modus: "action"})},
      "Stelle im Bild anklicken"));
  }
  if (objekt.action === "key")
    felder.push(feld("Taste", objekt.taste || "", (v) => setze("taste", v)));
  felder.push(zahlfeld("Verzögerung vor Aktion (s)", objekt.delay,
    (v) => setze("delay", v), {min: 0, step: 0.1}));
  return felder;
}

/** Schritt 4 (Icon): die Aktion bei Fund. */
function erkAktionSchritt(c, kind) {
  const text = (SC.actions.icon.find((a) => a.value === c.action) || {}).text || c.action;
  return erkKarte(4, "Aktion", text + (c.delay ? " · " + c.delay + " s" : ""),
    true, [
    erkAktionsKacheln(SC.actions.icon, c.action, (v) => erkFeld("action", v)),
    // Ausgebreitet, nicht als Liste in der Liste: `el()` flacht genau EINE
    // Ebene ab, und ein Array als Kind landet als solches in `appendChild` —
    // was den ganzen Aufbau abbricht.
    ...erkAktionsFelder(c, kind),
  ]);
}

/** Ein Feld des OFFENEN Scans setzen — Boss-Scan oder Icon-Scan. */
function erkFeld(feld, value) {
  const c = erkScan();
  if (!c) return;
  rufScan(erkBefehl("scan_feld"), {name: c.name, feld: feld, value: value});
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
  const color = t.ok ? "var(--ok)" : "var(--err)";
  ziel.append(
    el("b", {style: "color:" + color},
      t.ok ? "Test: " + t.name + " erkannt" : "Test: " + t.name + " nicht erkannt"));
  if (t.methode && t.konfidenz !== null && t.methode === "Template")
    ziel.appendChild(el("span", {class: "kennzahl"}, "Template · " + t.konfidenz.toFixed(2)));
  if (t.marker_total)
    ziel.appendChild(el("span", {class: "kennzahl"},
      t.marker_gefunden + " von " + t.marker_total + " Markern · nötig " + t.marker_required));
  if (t.tolerance) ziel.appendChild(el("span", {class: "kennzahl"}, "Toleranz " + t.tolerance));
  if (t.duration) ziel.appendChild(el("span", {class: "kennzahl"}, t.duration + " ms"));
  ziel.appendChild(el("span", {class: "wachse"}));
  ziel.appendChild(el("span", {class: "klein"},
    t.ok ? "Aktion wäre: " + t.action + " (wird nicht ausgeführt)" : t.reason));
  // **Der Vorschlag ist der Kern.** Ein Test, der nur „fehlgeschlagen" sagt,
  // laesst einen genau dort stehen, wo man vorher war.
  if (t.vorschlag)
    ziel.appendChild(el("button", {class: "btn an",
      onclick: () => erkFeld(t.vorschlag.feld, t.vorschlag.value)}, t.vorschlag.text));
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
  const selected = SC.boss.wahl === b.name && SC.boss.wahl_global === !!global;
  return el("button", {
    class: "scan-zeile" + (selected ? " an" : ""),
    style: verdeckt ? "opacity:.5" : null,
    title: verdeckt ? "Ein lokaler Boss gleichen Namens hat Vorrang" : "",
    onclick: () => rufScan("boss_select", {name: b.name, global: !!global}),
  },
    b.preview ? el("img", {class: "mini", src: b.preview})
               : el("span", {class: "kugel" + (b.marker.length ? "" : " ohne"),
                             style: b.marker.length ? "background:" + b.marker[0] : ""}),
    el("span", {class: "name"}, b.name),
    b.erkennung === "keine"
      ? el("span", {class: "klein", style: "color:var(--accent)",
                    title: "Weder Vorlage noch Marker — nur OCR/LLM können ihn finden"},
           "⚠ keine Vorlage")
      : (test
          ? el("span", {class: "klein", style: "color:var(" + (test.ok ? "--slot-ok" : "--err") + ")"},
               test.ok ? "detected" : "nein")
          : el("span", {class: "klein mono"},
               (SC.actions.boss.find((a) => a.value === b.action) || {}).text || b.action)));
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
      onclick: () => rufScan("icon_scan_open", {name: c.name}),
    },
      c.preview ? el("img", {class: "mini", src: c.preview})
                 : el("span", {class: "kugel" + (c.marker.length ? "" : " ohne"),
                               style: c.marker.length ? "background:" + c.marker[0] : ""}),
      el("span", {class: "name"}, c.name),
      c.erkennung === "keine"
        ? el("span", {class: "klein", style: "color:var(--accent)"}, "⚠ ohne Erkennung")
        : (test ? el("span", {class: "klein",
                              style: "color:var(" + (test.ok ? "--slot-ok" : "--err") + ")"},
                     test.ok ? "detected" : "nein")
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
  $("scan-flaeche").hidden = zeigen || !SC.photo;
  $("scan-leer").hidden = zeigen || !!SC.photo;
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
  const offen = b.action === "skip" && b.erkennung === "keine";
  const karte = el("div", {class: "seq-karte" + (offen ? " neu-vom-llm" : "")},
    el("div", {class: "scan-karte-kopf"},
      b.preview ? el("img", {class: "mini", src: b.preview})
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
      el("span", {class: "zahl"}, (SC.actions.boss.find((a) => a.value === b.action)
        || {}).text || b.action),
      b.scan ? el("span", {class: "zahl"}, "scan → " + b.scan) : null,
      b.delay ? el("span", {class: "zahl"}, "delay " + b.delay + " s") : null));
  }
  karte.appendChild(el("div", {class: "knopfpaar"},
    el("button", {class: offen ? "btn haupt" : "btn still",
      onclick: () => { scanListe = "bosse";
                       rufScan("boss_select", {name: b.name, global: true}); }},
      offen ? "Aktion zuweisen" : "bearbeiten"),
    el("button", {class: "btn still",
      onclick: () => rufScan("boss_delete", {name: b.name, global: true})}, "löschen")));
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
  ziel.appendChild(zahlfeld("Farb-Toleranz", c.tolerance,
    (v) => erkFeld("tolerance", v), {min: 0, step: 1},
    "Gilt für die Marker-Farben aller Bosse dieses Scans.", "bosstoleranz"));
  ziel.appendChild(ueberschrift("WENN KEIN BOSS ERKANNT",
    "Greift auch dann, wenn OCR und LLM nichts finden.", "bossfallback"));
  ziel.appendChild(erkAktionsKacheln(SC.actions.boss, c.default_action,
    (v) => erkFeld("default_action", v)));
  if (c.default_action === "item_scan") {
    ziel.appendChild(selection("Item-Scan", [{value: "", text: "— keiner —"}].concat(
      SC.item_scan_namen.map((n) => ({value: n, text: n}))), c.default_scan || "",
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
           t.ok ? "detected" : "nein"),
        el("span", {class: "reason"}, t.reason)));
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
  ziel.appendChild(el("div", {class: "knopfpaar"},
    el("button", {class: "btn still",
      onclick: () => rufScan("boss_select", {name: ""})}, "‹ zurück zum Scan"),
    el("button", {class: "btn still",
      onclick: () => rufScan("boss_delete")}, "löschen")));
  ziel.appendChild(el("button", {class: "btn haupt", disabled: !fotoDa(),
    onclick: () => rufScan("boss_test")}, "Diesen Boss testen"));
  ziel.appendChild(ueberschrift("BOSS", "Der Name ist zugleich das, was OCR und "
    + "LLM im Bild suchen — er sollte also der Name im Spiel sein.", "bossname"));
  ziel.appendChild(feld("Name", b.name, (v) => rufScan("boss_set",
    {name: b.name, global: b.global, feld: "name", value: v})));
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
  ziel.appendChild(erkAktionsKacheln(SC.actions.boss, b.action,
    (v) => rufScan("boss_set", {name: b.name, global: b.global,
                                   feld: "action", value: v})));
  for (const teil of erkAktionsFelder(b, "boss", b.name))
    if (teil) ziel.appendChild(teil);
  ziel.appendChild(el("button", {class: "btn still", style: "margin-top:14px",
    title: "Bosse der Bibliothek gelten in jedem Boss-Scan",
    onclick: () => rufScan("boss_move_global", {name: b.name, global: b.global})},
    b.global ? "In diesen Scan holen" : "In die Bibliothek verschieben"));
}

function erkInspIcon(ziel, c) {
  ziel.appendChild(el("button", {class: "btn haupt", disabled: !fotoDa(),
    onclick: () => rufScan("icon_test")}, "Icon-Scan testen"));
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
    onclick: () => rufScan("region_mode", {kind: "icon", modus: "region"})},
    "Region neu aufziehen"));
  ziel.appendChild(ueberschrift("AKTION BEI FUND",
    "Was passiert, wenn das Symbol da ist.", "iconaktion"));
  ziel.appendChild(erkAktionsKacheln(SC.actions.icon, c.action,
    (v) => erkFeld("action", v)));
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
    onclick: () => rufScan("boss_new", {global: true})}, "+ Boss anlegen"));
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
  const point = objekt && objekt.point_id !== null && objekt.point_id !== undefined
    ? SC.points.find((p) => p.id === objekt.point_id) : null;
  if (!point || objekt.action !== "click") return;
  const [ax, ay] = scanZuBild(point.x, point.y);
  const arm = 9 * px;
  svg.appendChild(svgEl("rect", {class: "scan-aktion", x: ax - arm, y: ay - arm,
    width: arm * 2, height: arm * 2}));
  svg.appendChild(svgEl("text", {x: ax - arm, y: ay - arm - 4 * px, class: "scan-marke",
    "font-size": 10 * px, "stroke-width": 3 * px, fill: "#F59E0B"},
    "Klickpunkt Aktion"));
}

/* ------------------------------------------------------------ Ansicht: Teilen
 *
 * Ein Bündel schreiben und eines einlesen. Beide Seiten arbeiten auf dem
 * GESPEICHERTEN Stand — was im Fenster offen ist, liegt nicht auf Platte. */
let T = null;
let teilenExport = {};    // welche Teile ins Bündel kommen
let teilenImport = {};    // welche Teile eingelesen werden
let teilenModus = "auto";
let teilenMerge = true;

async function zeichneTeilen(frisch) {
  const antwort = await frage("share_data");
  if (!antwort || ansicht !== "teilen") return;
  T = antwort;
  for (const t of T.teile) {
    if (teilenExport[t.key] === undefined) teilenExport[t.key] = true;
    if (teilenImport[t.key] === undefined) teilenImport[t.key] = true;
  }
  const merk = fokusMerken();
  teilenExportZeichnen();
  teilenMitteZeichnen();
  teilenImportZeichnen();
  setzeStatus(T.status);
  fokusHerstellen(merk);
}

/** Ein Befehl an den Teilen-Teil. Antwort ist die neue Teilen-Aufnahme. */
async function rufTeilen(name, daten) {
  const antwort = await frage(name, daten);
  if (!antwort) return;
  T = antwort;
  await zeichneTeilen();
}

function teilenHaken(ziel, selection, zahlen) {
  for (const t of T.teile) {
    const row = el("label", {class: "teilen-zeile an"});
    const box = el("input", {type: "checkbox"});
    box.checked = !!selection[t.key];
    box.addEventListener("change", () => { selection[t.key] = box.checked; zeichneTeilen(); });
    row.append(box, el("span", {}, t.text),
      el("span", {class: "zahl"}, String(zahlen[t.key] ?? 0)));
    ziel.appendChild(row);
  }
}

function teilenExportZeichnen() {
  const ziel = $("teilen-export");
  const kopf = el("div", {class: "abschnitt"},
    ueberschrift("EXPORTIEREN",
      "Schreibt ein ZIP nach exports/. Enthält nur, was gespeichert ist.", "export"));
  if (T.offen) {
    kopf.appendChild(el("div", {class: "fremdhinweis"},
      "Im Fenster gibt es ungespeicherte Änderungen — die kommen nicht mit. "
      + "Erst speichern, dann exportieren."));
  }
  ziel.replaceChildren(kopf);

  const rumpf = el("div", {class: "abschnitt wachsend"});
  teilenHaken(rumpf, teilenExport, T.bestand);
  rumpf.appendChild(feld("Dateiname (leer = mit Zeitstempel)", "",
    () => {}, {id: "teilen-name"}));
  // **Die Referenzpunkte kommen aus dem Spielfenster.** Ist es offen, rechnet
  // der Empfänger die Koordinaten selbst um; sonst setzt er zwei Punkte von Hand.
  rumpf.appendChild(el("p", {class: "hinweis"}, T.window && T.window.gefunden
    ? "Spielfenster „" + T.window.title + "“: " + T.window.width + "×"
      + T.window.height + " px. Der Empfänger rechnet damit automatisch um."
    : (T.window
        ? "Spielfenster „" + T.window.title + "“ ist nicht offen — der Empfänger "
          + "setzt beim Import zwei Punkte von Hand."
        : "Kein Fenstertitel eingestellt (window_focus_title) — der Empfänger "
          + "setzt beim Import zwei Punkte von Hand.")));
  rumpf.appendChild(el("button", {class: "btn haupt",
    onclick: () => rufTeilen("export_start",
      {teile: teilenExport, name: ($("teilen-name") || {}).value || ""})},
    "Bündel schreiben"));
  ziel.appendChild(rumpf);
}

function teilenMitteZeichnen() {
  const ziel = $("teilen-mitte");
  ziel.replaceChildren();
  const karte = el("div", {class: "teilen-karte"}, el("h3", {}, "Vorhandene Bündel"));
  if (!T.exporte.length) {
    karte.appendChild(el("p", {class: "hinweis"},
      "Noch keins. „Bündel schreiben“ legt eines unter exports/ an."));
  }
  const liste = el("div", {class: "teilen-liste"});
  for (const e of T.exporte) {
    liste.appendChild(el("div", {class: "teilen-zeile"},
      el("span", {class: "mono"}, e.name),
      el("span", {class: "zahl mono"}, e.kb + " KB"),
      el("button", {class: "btn still",
        onclick: () => rufTeilen("import_check", {pfad: "exports/" + e.name})},
        "einlesen")));
  }
  karte.appendChild(liste);
  ziel.appendChild(karte);

  ziel.appendChild(el("div", {class: "teilen-karte"},
    el("h3", {}, "Weitergeben"),
    el("p", {class: "hinweis"},
      "Die ZIP-Datei verschicken. Der Empfänger legt sie in seinen "
      + "Autoclicker-Ordner und liest sie hier oder mit CTRL+ALT+I ein. "
      + "Koordinaten werden dabei auf sein Fenster umgerechnet.")));
}

function teilenImportZeichnen() {
  const ziel = $("teilen-import");
  const i = T.import;
  const kopf = el("div", {class: "abschnitt"},
    ueberschrift("IMPORTIEREN",
      "Liest ein Bündel ein und rechnet die Koordinaten um.", "import"),
    // EIN Knopf ueber die volle Breite heisst `btn breit` — `wachse` in einer
    // `reihe` war dasselbe mit einer zweiten Schreibweise.
    el("button", {class: "btn breit", onclick: () => rufTeilen("file_choose")},
      "Datei wählen …"),
    feld("oder Pfad", i ? i.pfad : "",
      (v) => rufTeilen("import_check", {pfad: v})));
  ziel.replaceChildren(kopf);

  const rumpf = el("div", {class: "abschnitt wachsend"});
  if (!i) {
    rumpf.appendChild(el("p", {class: "hinweis"},
      "Noch keine Datei gewählt. Ein Bündel ist ein ZIP mit manifest.json."));
    ziel.appendChild(rumpf);
    return;
  }
  rumpf.appendChild(el("div", {class: "feld-still"}, i.file,
    el("span", {class: "mono"}, i.erstellt || "")));
  teilenHaken(rumpf, teilenImport, i.inhalt);

  rumpf.appendChild(ueberschrift("KOORDINATEN",
    "Wie die Stellen des Absenders auf deinen Bildschirm kommen.", "importkoord"));
  // Ohne beidseitig bekanntes Fenster gibt es nichts zu wählen — eine Kachel,
  // die nichts tut, ist schlechter als keine.
  const modi = (i.auto ? [{value: "auto", text: "aus Fenstergrösse"}] : [])
    .concat([{value: "identity", text: "1:1 übernehmen"}]);
  rumpf.appendChild(segment(modi, i.auto ? teilenModus : "identity",
    (v) => { teilenModus = v; zeichneTeilen(); }));
  rumpf.appendChild(el("p", {class: "hinweis"}, i.auto
    ? "Beide Seiten kennen ihr Spielfenster — die Umrechnung geht automatisch."
    : "Ohne beidseitig bekanntes Spielfenster geht nur 1:1. Für ein echtes "
      + "Umrechnen zwei Punkte setzen: CTRL+ALT+I im Hauptprozess."));

  rumpf.appendChild(schalter("Vorhandenes behalten und ergänzen", teilenMerge,
    (v) => { teilenMerge = v; zeichneTeilen(); }));
  rumpf.appendChild(el("p", {class: "hinweis"}, teilenMerge
    ? "Gleiche Namen werden übersprungen."
    : "Achtung: gleiche Namen werden überschrieben."));
  rumpf.appendChild(el("button", {class: "btn haupt",
    onclick: () => rufTeilen("import_start",
      {teile: teilenImport, modus: teilenModus, merge: teilenMerge})},
    "Bündel einlesen"));
  ziel.appendChild(rumpf);
}

/* ------------------------------------------------------------ Ansicht: Bericht
 *
 * Der Live-Run zeigt das Jetzt, dieser Reiter das Gestern. Eigener Zustand
 * neben `S`, wie bei Teilen und Werkzeugen: er liest `logs/`, nicht die
 * geoeffnete Sequenz.
 *
 * Gezeichnet wird mit denselben Bausteinen wie der Werkzeuge-Reiter
 * (`wz-kennzahlen`, `wz-zwischenkopf`, `abschnitt`) statt mit eigenen. Ein
 * achter Reiter, der sich seine eigene Gestalt gibt, kostet mehr als er
 * einbringt — und die Kennzahlen-Kacheln koennen genau das schon: gleiche
 * Spalten ueber `auto-fit`, gleiche Hoehe, gleiche Schrift. */

let B = null;

async function zeichneBericht(daten) {
  const antwort = await frage("report_data", daten === undefined ? null : daten);
  if (!antwort || ansicht !== "bericht") return;
  B = antwort;
  const merk = fokusMerken();
  berichtLinksZeichnen();
  berichtMitteZeichnen();
  berichtRechtsZeichnen();
  fokusHerstellen(merk);
}

/** Sekunden als h:mm:ss — dieselbe Form wie in `tools/log_report.py`. */
function berDauer(sek) {
  const ganz = Math.max(0, Math.round(sek || 0));
  const h = Math.floor(ganz / 3600), m = Math.floor((ganz % 3600) / 60), s = ganz % 60;
  const zwei = (n) => String(n).padStart(2, "0");
  return h ? h + ":" + zwei(m) + ":" + zwei(s) : m + ":" + zwei(s);
}

/** Grosse Zahlen mit Tausenderpunkten. Gold geht in die Millionen, und
 *  „143920771" liest niemand. */
function berZahl(n, stellen) {
  return (n || 0).toLocaleString("de-DE", {maximumFractionDigits: stellen || 0});
}

/* Eine Rangzeile: Name links, Anzahl rechts, darunter ein Balken im Verhaeltnis
 * zum groessten Wert der Liste. VIER Listen benutzen sie (Timeouts, Items,
 * Erkanntes, Nachpruefung) — eine Bauform fuer alle, sonst hat dieselbe Sache
 * vier Gestalten. */
function berRang(name, value, anteil, zusatz, kind) {
  const row = el("div", {class: "ber-rang" + (kind ? " " + kind : "")},
    el("span", {class: "ber-rang-name", title: name}, name),
    el("span", {class: "ber-rang-wert mono"}, value),
    el("div", {class: "ber-balken"},
      el("div", {class: "ber-balken-fuell",
        style: "width:" + Math.max(2, Math.round(anteil * 100)) + "%"})));
  if (zusatz) row.appendChild(el("span", {class: "ber-rang-zusatz"}, zusatz));
  return row;
}

function berListe(title, help, key, eintraege) {
  const kasten = el("div", {class: "teilen-karte"},
    ueberschrift(title, help, key));
  const hoechst = eintraege.reduce((m, e) => Math.max(m, e.value), 0) || 1;
  for (const e of eintraege)
    kasten.appendChild(berRang(e.name, berZahl(e.value), e.value / hoechst,
      e.zusatz, e.kind));
  return kasten;
}

/* ------------------------------------------------------------------- links */

function berichtLinksZeichnen() {
  const ziel = $("ber-links");
  const kopf = el("div", {class: "abschnitt klebt"},
    ueberschrift("SITZUNGEN",
      "Eine Zeile je Lauf, neueste oben. „Alle zusammen“ ist der Normalfall: "
      + "die Frage nach dem haengenden Schritt stellt sich ueber die Nacht, "
      + "nicht ueber eine einzelne Datei.", "ber-sitzungen"));
  if (!B.active) {
    kopf.appendChild(el("p", {class: "hinweis warnung"},
      "session_log_enabled ist aus — neue Laeufe schreiben nichts mit."));
  }
  ziel.replaceChildren(kopf);

  const rumpf = el("div", {class: "abschnitt wachsend"});
  if (!B.available) {
    rumpf.appendChild(el("p", {class: "hinweis"}, B.fehler));
    ziel.appendChild(rumpf);
    return;
  }
  if (!B.sitzungen.length) {
    rumpf.appendChild(el("p", {class: "hinweis"}, B.ordner
      ? "Keine Logs in " + B.ordner + "."
      : "Noch kein Log-Ordner. Er entsteht beim ersten Lauf mit "
        + "session_log_enabled."));
    ziel.appendChild(rumpf);
    return;
  }

  rumpf.appendChild(berSitzung({
    file: "", title: "Alle zusammen",
    unten: B.sitzungen.length + " Sitzung(en)",
  }));
  for (const s of B.sitzungen) {
    rumpf.appendChild(berSitzung({
      file: s.file,
      title: s.beginn || s.file,
      unten: berDauer(s.duration) + " · " + berZahl(s.klicks) + " Klicks",
      warnung: s.timeouts ? s.timeouts + "× Timeout" : "",
    }));
  }
  if (B.ausgelassen) {
    rumpf.appendChild(el("p", {class: "hinweis"},
      B.ausgelassen + " aeltere Datei(en) nicht gelesen — der Reiter liest die "
      + "neuesten 50."));
  }
  ziel.appendChild(rumpf);
}

function berSitzung(s) {
  const an = (B.selected || "") === s.file;
  const row = el("button", {
    class: "ber-sitzung" + (an ? " an" : ""),
    onclick: () => zeichneBericht({file: s.file}),
  },
    el("span", {class: "ber-sitzung-titel"}, s.title),
    el("span", {class: "ber-sitzung-unten"}, s.unten));
  if (s.warnung)
    row.appendChild(el("span", {class: "ber-sitzung-warn"}, s.warnung));
  return row;
}

/* ------------------------------------------------------------------- Mitte */

function berichtMitteZeichnen() {
  const ziel = $("ber-mitte");
  ziel.replaceChildren();
  const b = B.bericht;
  if (!b || !b.sitzungen) {
    ziel.appendChild(el("p", {class: "hinweis"},
      "Nichts auszuwerten. Der Bericht liest die CSV-Dateien, die ein Lauf mit "
      + "eingeschaltetem Session-Log hinterlaesst."));
    return;
  }

  ziel.appendChild(el("div", {class: "wz-kennzahlen"},
    wzKennzahl(berDauer(b.duration), "Laufzeit", "neutral"),
    wzKennzahl(berZahl(b.klicks), "Klicks", "neutral"),
    wzKennzahl(berZahl(b.items_total), "Items", "neutral"),
    wzKennzahl(berZahl(b.timeouts_total), "Timeouts",
      b.timeouts_total ? "hinweis" : "neutral"),
    wzKennzahl(berZahl(b.verify_miss_total), "ohne Wirkung",
      b.verify_miss_total ? "fehler" : "neutral")));

  // DIE Frage, fuer die es den Reiter gibt — deshalb steht sie oben und nicht
  // zwischen den Item-Zahlen.
  if (b.timeouts.length) {
    ziel.appendChild(berListe("TIMEOUTS — WO DIE SEQUENZ HAENGT",
      "Der oberste Eintrag ist der Schritt, den es zu reparieren lohnt: dort "
      + "ist eine Farb-Bedingung am haeufigsten nicht aufgegangen.", "ber-timeout",
      b.timeouts.map(([name, n]) => ({name: name, value: n, kind: "warn"}))));
  } else {
    ziel.appendChild(el("div", {class: "wz-erfolg"}, wzIcon("ok"),
      el("div", {}, el("b", {}, "Keine Timeouts"),
        el("span", {}, "Jede Farb-Bedingung ist aufgegangen."))));
  }

  if (b.verify_miss.length) {
    ziel.appendChild(berListe("NACHPRUEFUNG — KLICKS OHNE WIRKUNG",
      "Haeufige Fehlschlaege heissen: das Klickziel sitzt falsch, oder das "
      + "Spiel braucht laenger als verify_timeout.", "ber-verify",
      b.verify_miss.map(([name, n, gut]) => ({
        name: name, value: n, kind: "fehler",
        zusatz: "bestätigt " + gut + "/" + (gut + n),
      }))));
  }

  if (b.items.length) {
    ziel.appendChild(berListe("GEFUNDENE ITEMS", "", "ber-items",
      b.items.map(([name, n]) => ({name: name, value: n}))));
  }
  if (b.detected.length) {
    ziel.appendChild(berListe("ERKANNT (BOSS/ICON)", "", "ber-erkannt",
      b.detected.map(([name, n]) => ({name: name, value: n}))));
  }
  if (b.disturbances.length) {
    ziel.appendChild(berListe("UNTERBRECHUNGEN",
      "Fokusverluste und Humanize-Pausen. Eine Haeufung heisst, dass das "
      + "Spielfenster oft nicht vorn war.", "ber-stoer",
      b.disturbances.map(([name, n]) => ({name: name, value: n}))));
  }

  for (const [file, fehler] of b.nicht_lesbar) {
    ziel.appendChild(el("p", {class: "hinweis warnung"},
      file + ": nicht lesbar (" + fehler + ")"));
  }
  if (b.unbekannt.length) {
    // Dieselbe Meldung wie in der Konsole: eine neue Ereignisart soll auffallen,
    // nicht stillschweigend fehlen.
    ziel.appendChild(el("p", {class: "hinweis"},
      "Nicht ausgewertete Ereignisarten: " + b.unbekannt.join(", ")));
  }
}

/* ------------------------------------------------------------------- rechts */

function berichtRechtsZeichnen() {
  const ziel = $("ber-rechts");
  const kopf = el("div", {class: "abschnitt klebt"},
    ueberschrift("ERTRAG",
      "Stueckzahlen aus dem Log mal Marktwert aus der Analyse. Die Verbindung "
      + "zwischen beiden ist eine Datei (scan_market_value_file) — die "
      + "Marktanalyse selbst laeuft getrennt.", "ber-ertrag"));
  ziel.replaceChildren(kopf);

  const rumpf = el("div", {class: "abschnitt wachsend"});
  const e = B.ertrag;
  if (!e) {
    rumpf.appendChild(el("p", {class: "hinweis"},
      "Keine Bewertung: scan_market_value_file ist leer oder es wurden keine "
      + "Items gefunden. Mit eingetragener marktwert.json steht hier, was der "
      + "Lauf eingebracht hat."));
    ziel.appendChild(rumpf);
    return;
  }
  if (!e.lesbar) {
    rumpf.appendChild(el("p", {class: "hinweis warnung"},
      "Marktwert-Datei nicht lesbar: " + e.file));
    ziel.appendChild(rumpf);
    return;
  }

  rumpf.appendChild(el("div", {class: "wz-kennzahlen"},
    wzKennzahl(berZahl(e.gold), "Gold gesamt", "neutral"),
    wzKennzahl(e.pro_stunde === null ? "—" : berZahl(e.pro_stunde), "Gold/h",
      "neutral")));
  // **Obergrenze, keine Abrechnung.** `item_found` heisst „erkannt", nicht
  // „eingesammelt und verkauft". Das steht hier und nicht im ⓘ: wer die Zahl
  // liest, muss es lesen, ohne danach zu fragen.
  rumpf.appendChild(el("p", {class: "hinweis warnung"},
    "Obergrenze: gezaehlt wird, was der Scan ERKANNT hat — nicht, was "
    + "eingesammelt und verkauft wurde."));

  const hoechst = e.rows.reduce((m, z) => Math.max(m, z[3]), 0) || 1;
  const liste = el("div", {class: "teilen-karte"});
  for (const [name, count, value, summe] of e.rows) {
    liste.appendChild(berRang(name, berZahl(summe), summe / hoechst,
      count + "× à " + berZahl(value)));
  }
  rumpf.appendChild(liste);

  if (e.without_value.length) {
    rumpf.appendChild(el("p", {class: "hinweis"},
      e.without_value.length + " Item(s) ohne Marktwert: "
      + e.without_value.map(([name, n]) => name + " (" + n + "×)").join(", ")));
  }
  ziel.appendChild(rumpf);
}

/* ----------------------------------------------------- Ansicht: Einstellungen */

/* --------------------------------------------------------------- Werkzeuge
 *
 * Was bisher nur im Punkte-Menue der Konsole ging: pruefen (`check`),
 * kalibrieren (`fix`) und Nachklicken (`klick`). Eigener Zustand neben `S`,
 * wie bei Einstellungen und Teilen — der Reiter arbeitet auf `sequence.json` und
 * dem ganzen Bestand, nicht auf der geoeffneten Sequenz.
 *
 * `wzOffen` ist reiner Oberflaechenzustand (welches Werkzeug in der Mitte
 * steht), `W` die Antwort der Bruecke, `wzBericht` das Ergebnis der letzten
 * Pruefung. Die Pruefung steht bewusst NICHT in `W`: sie kostet einen Durchlauf
 * ueber den ganzen Bestand, und den will man auf Knopfdruck, nicht bei jedem
 * Neuzeichnen. */
let W = null;
let wzOffen = "pruefen";
let wzBericht = null;
let wzUmfang = {};
// Der Hauptprozess besitzt die Aufnahme. Dieser Merker sagt nicht mehr als das,
// was das Studio sicher weiss: der Startauftrag wurde erfolgreich abgelegt.
let wzAufnahmeGestartet = false;
let wzAufnahmeName = "";
let wzAufnahmeZyklen = 0;
let wzAufnahmeBeschreibung = "";
let wzAufnahmePoll = 0;
let wzAufnahmeLivePoll = 0;
let wzAufnahmeLive = {active: false, pausiert: false, count: 0, events: []};
/* Der Live-Stand der Klick-Runde. Sie laeuft im HAUPTPROZESS (dort haengt der
 * Maus-Hook), also weiss dieses Fenster von sich aus nichts ueber sie — der
 * Stand kommt ueber `.nachklick.json`. Ohne ihn stand hier nur „gestartet",
 * waehrend die Konsole jeden Schritt einzeln meldete. */
let wzNachklickPoll = 0;
let wzNachklickLive = {active: false, index: 0, total: 0, history: [], point: {}};
/* Eine offene Farb-Rueckfrage: die Stelle ist angefahren, aber die Farbe dort
 * weicht von der gespeicherten ab. Bis das jemand bestaetigt, ist NICHTS gesetzt
 * - der Zustand lebt nur hier, nicht in der Bruecke. */
let wzFarbfrage = null;
let wzPunktId = null;
let wzFarbAnalyse = null;

/* Jedes Werkzeug sagt, WORAUF es wirkt. Ein einzelner Sequenzname oben im Reiter
 * waere fuer zwei davon schlicht falsch: Pruefen und Kalibrieren gehen ueber
 * den GANZEN Bestand (alle Sequenzen, Slots, Scans, Punkte), nur das Nachklicken
 * meint genau eine Sequenz — die hier offene. Die Aufnahme erzeugt dagegen wie
 * im TUI eine NEUE Sequenz. */
/* ------------------------------------------------- Griffe mit der Maus warten */

/* **Jeder Aufruf, der die Bruecke blockiert, steht hier.** Diese Methoden warten
 * per `_await_position()` bzw. `area_capture()` global auf ENTER — bis zu
 * `wait_timeout` Sekunden. Solange kommt keine Antwort zurueck; die Seite kann
 * also nichts anzeigen, was aus der Bruecke kaeme, und muss VOR dem Aufruf
 * sagen, worauf gewartet wird. Ohne das sah es aus, als tue das Fenster nichts —
 * und zwar eine Minute lang.
 *
 * Der zweite Wert ist die Zahl der Tastendruecke. Ihn mitzuzaehlen geht NICHT:
 * beide Ecken sind EIN Aufruf (die Hand soll zwischendurch nicht zum Fenster
 * zurueck), und die Seite erfaehrt vom ersten ENTER nichts. Sie sagt deshalb
 * vorher, wie viele kommen, statt einen Fortschritt zu erfinden.
 *
 * Ein Test haelt die Tabelle gegen die Bruecke: eine wartende Methode, die hier
 * fehlt, ist genau die, bei der das Fenster wieder stumm ist. */
const WARTE_GRIFFE = {
  point_capture: ["Stelle aufnehmen", 1],
  area_capture: ["Screenshot-Bereich aufziehen", 2],
  mouse_position: ["Parkposition setzen", 1],
  tool_point_capture: ["Punkt aufnehmen", 1],
  tool_colors: ["Farbe messen", 1],
  calib_reference: ["Referenzpunkt setzen", 1],
};

let warteZaehler = null;
let arbeitUhr = null;
let arbeitZeile = null;
let arbeitEsc = null;

/** Blendet ein, worauf gerade gewartet wird — mit Countdown bis zum Zeitablauf. */
function warteZeigen(name) {
  const [was, drucke] = WARTE_GRIFFE[name] || ["Stelle setzen", 1];
  const grenze = (S && S.wait_timeout) || (W && W.wait_timeout) || 60;
  let rest = Math.round(grenze);
  const number = el("span", {class: "warte-rest"}, rest + " s");
  const kasten = el("div", {class: "warte-kasten"},
    el("div", {class: "warte-titel"}, was),
    el("div", {class: "warte-text"},
      "Fahre mit der Maus an die Stelle im Spiel und drücke ",
      el("b", {}, "ENTER"),
      drucke > 1 ? " — " + drucke + "× nacheinander, eine Ecke je Druck." : "."),
    el("div", {class: "warte-fuss"},
      el("span", {}, "ESC bricht ab"), number));
  warteWeg();
  document.body.appendChild(
    el("div", {class: "warte-huelle", id: "warte-huelle"}, kasten));
  // Der Countdown ist die zweite Haelfte der Auskunft: DASS gewartet wird, sagt
  // der Kasten — wie lange noch, nur die Zahl. Laeuft sie ab, endet der Aufruf
  // von selbst, und die Bruecke meldet „Nichts gedrueckt".
  warteZaehler = setInterval(() => {
    rest -= 1;
    number.textContent = Math.max(0, rest) + " s";
    if (rest <= 0) clearInterval(warteZaehler);
  }, 1000);
}

function warteWeg() {
  clearInterval(warteZaehler);
  warteZaehler = null;
  clearInterval(arbeitUhr);
  arbeitUhr = null;
  arbeitZeile = null;
  if (arbeitEsc) document.removeEventListener("keydown", arbeitEsc);
  arbeitEsc = null;
  const alt = $("warte-huelle");
  if (alt) alt.remove();
}

/** Zeigt, dass ein langer Aufruf LAEUFT — mit hochzaehlender Uhr.
 *
 * Der Unterschied zu `warteZeigen()` ist die Frage dahinter: dort wartet die
 * Bruecke auf einen ENTER-Druck und hat eine feste Grenze, hier arbeitet sie
 * und niemand weiss, wie lange. Ein Countdown waere hier eine erfundene Zahl —
 * die hochzaehlende Uhr sagt nur, dass es weitergeht, und genau das ist die
 * Frage bei sechsundfuenfzig Modell-Aufrufen hintereinander.
 */
function arbeitZeigen(title, text, abbruch) {
  const number = el("span", {class: "warte-rest"}, "0 s");
  const row = el("div", {class: "warte-text"}, text);
  let sek = 0;
  const kasten = el("div", {class: "warte-kasten"},
    el("div", {class: "warte-titel"}, title), row,
    // **Ein Abbruch nur da, wo es einen gibt.** Ein Knopf, der einen
    // einzelnen HTTP-Aufruf nicht stoppen kann, waere ein Bedienelement, das
    // nichts tut — dieselbe Regel wie bei den Kacheln im Teilen-Reiter.
    abbruch ? el("button", {class: "btn still breit", style: "margin-top:10px",
                            id: "arbeit-abbruch",
                            onclick: () => arbeitAbbrechen(abbruch)}, "Abbrechen") : null,
    el("div", {class: "warte-fuss"},
      el("span", {}, abbruch ? "ESC bricht ab" : "läuft …"), number));
  warteWeg();
  document.body.appendChild(
    el("div", {class: "warte-huelle", id: "warte-huelle"}, kasten));
  arbeitZeile = row;
  arbeitUhr = setInterval(() => { sek += 1; number.textContent = sek + " s"; }, 1000);
  if (abbruch) {
    arbeitEsc = (e) => { if (e.key === "Escape") arbeitAbbrechen(abbruch); };
    document.addEventListener("keydown", arbeitEsc);
  }
}

/** Der Abbruch-Klick, und zwar SICHTBAR.
 *
 * **Hier war das „geht nicht".** Der Abbruch wirkt erst, wenn die laufende
 * Vorlage zurueck ist — und das dauert bis zu `llm_timeout` (Standard 60 s).
 * Bis dahin stand im Kasten unveraendert „Vorlage 3 von 56", der Knopf sah
 * unberuehrt aus, und man klickte ihn noch dreimal. Die Wartezeit laesst sich
 * nicht abkuerzen (die Antwort ist schon unterwegs), die Auskunft darueber
 * sehr wohl.
 */
function arbeitAbbrechen(abbruch) {
  abbruch();
  const knopf = $("arbeit-abbruch");
  if (knopf) {
    knopf.disabled = true;
    knopf.textContent = "Bricht ab …";
  }
  arbeitSagen("Wartet noch auf die laufende Vorlage — die Antwort ist schon "
              + "unterwegs und laesst sich nicht zurueckholen.");
}

/** Die Zeile im Arbeits-Kasten austauschen, ohne ihn neu aufzubauen.
 *
 * Neu gebaut ginge auch und faenge die Uhr jedes Mal wieder bei 0 an — bei
 * sechsundfuenfzig Schritten also eine Uhr, die nie ueber drei Sekunden kommt
 * und damit nichts mehr sagt. */
function arbeitSagen(text) {
  if (arbeitZeile) arbeitZeile.textContent = text;
}

let autonameAbbruch = false;

/** Treibt einen Benenn-Durchgang: einmal starten, dann Schritt fuer Schritt.
 *
 * **Die Schleife steht hier und nicht in der Bruecke, damit es ein Abbrechen
 * gibt.** Als EIN Aufruf blockierte der Durchgang bei sechsundfuenfzig Items
 * knapp drei Minuten, und von aussen laesst sich das nicht stoppen: ein
 * Abbruch-Flag brauchte einen zweiten Aufruf NEBEN dem laufenden.
 *
 * Entschieden wird trotzdem drueben — die Seite fragt nur nach dem naechsten
 * Schritt und zeigt an, was zurueckkommt. Der Zustand (was ist offen, was ist
 * benannt) liegt vollstaendig in der Bruecke.
 */
async function scanAutonameLauf(daten) {
  autonameAbbruch = false;
  await rufScan("scan_autoname_start", daten);
  // Kein Durchgang in der Momentaufnahme heisst: abgelehnt (LLM aus, nichts
  // mit Vorlage). Die Statuszeile sagt bereits, warum.
  if (!SC.autoname) return;
  arbeitZeigen("Items benennen", "", () => { autonameAbbruch = true; });
  try {
    while (SC.autoname && SC.autoname.offen > 0 && !autonameAbbruch) {
      const a = SC.autoname;
      arbeitSagen("Vorlage " + (a.fertig + 1) + " von " + a.total
                  + " — " + a.umbenannt + " benannt");
      await rufScan("scan_autoname_step", null);
    }
  } finally {
    warteWeg();
    await rufScan("scan_autoname_end", {abgebrochen: autonameAbbruch});
  }
}

/** Wie `mitWarten`, nur fuer Aufrufe, die selbst RECHNEN statt auf ENTER zu warten.
 *
 * `kind` waehlt denselben Kanal, den der Aufruf ohnehin haette: `scan` ersetzt
 * die Scan-Momentaufnahme, `frage` fragt nur. Der Einstellungen-Reiter braucht
 * den zweiten — seine Antwort ist keine Momentaufnahme, und ueber `rufScan`
 * geholt zerschoesse sie den Scans-Reiter.
 */
async function mitArbeit(kind, name, daten, title, text) {
  arbeitZeigen(title, text);
  try {
    return kind === "scan" ? await rufScan(name, daten) : await frage(name, daten);
  } finally {
    warteWeg();
  }
}

/** Ruft eine blockierende Methode und zeigt so lange, worauf gewartet wird.
 *
 * `kind` waehlt den Kanal, den der Aufruf ohnehin haette: `ruf` ersetzt die
 * Momentaufnahme, `werkzeug` zeichnet den Reiter neu, `frage` fragt nur. Das
 * Overlay aendert daran nichts — es legt sich nur davor.
 */
async function mitWarten(kind, name, daten) {
  warteZeigen(name);
  try {
    return kind === "ruf" ? await ruf(name, daten)
         : kind === "werkzeug" ? await rufWerkzeug(name, daten)
         : await frage(name, daten);
  } finally {
    warteWeg();
  }
}

const WZ_WERKZEUGE = [
  {key: "aufnahme", name: "Sequenz aufnehmen", befehl: "rec", bezug: "neu",
   kurz: "Echtes Spielen als neue Sequenz aufzeichnen"},
  {key: "pruefen", name: "Bestand prüfen", befehl: "check", bezug: "bestand",
   kurz: "Fehler und unvollständige Verknüpfungen finden"},
  {key: "points", name: "Punkte verwalten", befehl: "points", bezug: "sequence",
   kurz: "Aufnehmen, nachmessen, umbenennen und sicher löschen"},
  // `nichts` ist kein fehlender Wert, sondern eine eigene Aussage: dieses
  // Werkzeug MISST nur den Bildschirm und schreibt nirgends hin. Es stand hier
  // auf „bestand" und war damit schlicht falsch — und die Zeile wurde als
  // einzige gar nicht erst gezeichnet, womit die Unwahrheit nicht auffiel.
  {key: "colors", name: "Farben analysieren", befehl: "color", bezug: "nichts",
   kurz: "Pixel und häufigste Bildschirmfarben sichtbar machen"},
  {key: "kalibrieren", name: "Kalibrieren", befehl: "fix", bezug: "bestand",
   kurz: "Koordinaten an ein neues Bildschirm-Layout anpassen"},
  {key: "klicken", name: "Punkte nachklicken", befehl: "klick", bezug: "sequence",
   kurz: "Alle Klickstellen geführt im Spiel kontrollieren"},
];

/** Kleine, lokale Linien-Icons. Keine Schriftzeichen und keine externe Datei:
 *  dadurch bleiben Strichstärke und Ausrichtung in jedem System identisch. */
function wzIcon(kind) {
  const pfade = {
    aufnahme: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18", "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8"],
    pruefen: ["M9 11l2 2 4-5", "M12 3a9 9 0 1 0 9 9", "M16 4l5-1-1 5"],
    kalibrieren: ["M12 2v4M12 18v4M2 12h4M18 12h4", "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8"],
    klicken: ["M5 3l12 9-6 1 3 6-3 2-3-6-4 4z"],
    points: ["M12 2v5M12 17v5M2 12h5M17 12h5", "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8"],
    colors: ["M12 3c-4 4-7 7-7 11a7 7 0 0 0 14 0c0-4-3-7-7-11z", "M9 15h6"],
    info: ["M12 11v6M12 7h.01", "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20"],
    ok: ["M4 12l5 5L20 6"],
    fehler: ["M6 6l12 12M18 6L6 18"],
    hinweis: ["M12 3L2 21h20z", "M12 9v5M12 18h.01"],
    ordner: ["M3 6h7l2 2h9v11H3z"],
  };
  const svg = svgEl("svg", {class: "wz-symbol", viewBox: "0 0 24 24",
    fill: "none", stroke: "currentColor", "stroke-width": "1.8",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true"});
  for (const d of pfade[kind] || pfade.info) svg.appendChild(svgEl("path", {d}));
  return svg;
}

function wzKopf(key, title, text) {
  return el("section", {class: "wz-hero " + key},
    el("div", {class: "wz-hero-icon"}, wzIcon(key)),
    el("div", {class: "wz-hero-copy"},
      el("div", {class: "wz-kicker"}, "WERKZEUG"),
      el("h2", {}, title),
      el("p", {}, text)));
}

function wzInfo(title, text) {
  // Erklaerungen bleiben aus dem Arbeitsfluss, bis jemand sie braucht. Das
  // Studio verwendet dafuer bereits ueberall dasselbe kleine i; ein eigener
  // Infokasten im Werkzeuge-Reiter war nicht nur unruhig, sondern drueckte bei
  // schmaler Mitte auch die eigentlichen Bedienelemente zusammen.
  //
  // **Der Titel steht daneben, nicht im Tooltip.** Bis hierher wurde er zum
  // `title`-Attribut gemacht, und uebrig blieb ein nackter Kreis in der
  // Flaeche — an zwoelf Stellen, in „pruefen" und „kalibrieren" mitten im
  // Leeren, wo er wie ein Rest aussah. Ueberall sonst im Studio haengt ein ⓘ an
  // einer BESCHRIFTUNG (`beschriftet()`), und die ist es, die sagt, worueber
  // es sich lohnt nachzufragen. Eine Zeile kleiner Schrift kostet die Breite
  // nicht, um die es dem Kompakt-Umbau ging — ein Kasten waere das gewesen.
  // **Der Kasten hiess `wz-info-kompakt info`** — und `.info` ist der runde
  // ⓘ-Knopf: 13 px breit, `flex:none`, zentriert. Der Kasten erbte dessen
  // Gestalt, war 13 px breit statt so breit wie die Spalte, und sein Inhalt
  // stand mittig darüber hinaus — nach links aus dem Fenster heraus. Dieselbe
  // Falle wie einmal beim Status („Zustandsklassen bekommen ein Präfix"), nur
  // hier unsichtbar, solange der Kasten NUR das ⓘ enthielt: 13 px sahen dann
  // richtig aus.
  //
  // Das `kind`-Argument ist ersatzlos weg statt auf `art-…` umgeschrieben: es
  // hatte in zwölf Aufrufen keinen einzigen Nutzer und in der CSS-Datei keine
  // einzige Variante. Ein Präfix hätte einen toten Zweig gepflegt.
  return el("div", {class: "wz-info-kompakt"},
    el("span", {class: "mitinfo"}, title, info(text, "werkzeug-" + title)));
}

/** Die Zeile „worauf wirkt das hier" — als eigener Baustein, damit sie an jedem
 *  Werkzeug gleich aussieht und keines sie vergessen kann. */
function wzBezug(key) {
  const w = WZ_WERKZEUGE.find(x => x.key === key);
  const kasten = el("div", {class: "wz-bezug"});
  if (w && w.bezug === "neu") {
    kasten.classList.add("eine");
    kasten.append(el("span", {class: "wz-bezug-marke"}, "Bezug"),
      el("span", {}, "eine neue Sequenz — die offene Sequenz "),
      el("b", {}, W ? W.sequence : "—"),
      el("span", {}, " bleibt unverändert"));
    return kasten;
  }
  if (w && w.bezug === "nichts") {
    kasten.classList.add("eine");
    kasten.append(el("span", {class: "wz-bezug-marke"}, "Bezug"),
      el("span", {}, "nichts — es misst nur den Bildschirm und ändert keine Datei"));
    return kasten;
  }
  if (!w || w.bezug === "bestand") {
    kasten.append(el("span", {class: "wz-bezug-marke"}, "Bezug"),
      el("span", {}, "der gesamte gespeicherte Bestand — alle Sequenzen, Punkte, "
        + "Slots und Scans, nicht nur die offene Sequenz"));
    return kasten;
  }
  kasten.classList.add("eine");
  kasten.append(el("span", {class: "wz-bezug-marke"}, "Bezug"),
    el("span", {}, "die offene Sequenz "),
    el("b", {}, W ? W.sequence : "—"),
    el("span", {class: "hint"}, W ? " (" + W.file + ")" : ""));
  if (W && W.offen)
    kasten.append(el("span", {class: "art-warn"}, " — ungespeichert"));
  return kasten;
}

async function zeichneWerkzeuge(frisch) {
  const antwort = await frage("tool_data");
  if (!antwort || ansicht !== "werkzeuge") return;
  W = antwort;
  for (const u of W.umfang)
    if (wzUmfang[u.key] === undefined) wzUmfang[u.key] = u.vorgabe;
  if (frisch) { wzBericht = null; wzFarbfrage = null; }
  const merk = fokusMerken();
  wzLinksZeichnen();
  wzMitteZeichnen();
  wzRechtsZeichnen();
  fokusHerstellen(merk);
}

/** Ein Werkzeug-Befehl. Antwort ist ein Ergebnis, KEINE Momentaufnahme —
 *  deshalb `frage()` und danach neu zeichnen, statt `S` zu ersetzen. */
async function rufWerkzeug(name, daten) {
  const antwort = await frage(name, daten);
  if (!antwort) return null;
  if (antwort.message)
    setzeStatus({text: antwort.message, kind: antwort.ok ? "ok" : "err"});
  await zeichneWerkzeuge();
  return antwort;
}

function wzLinksZeichnen() {
  const ziel = $("wz-links");
  // Hier stand „offene Sequenz <Name>". Der Block hatte einen Grund: die
  // Kopfleiste blendete ihre Sequenz-Bedienelemente in diesem Reiter aus, und
  // damit war auch der Name weg — bei der Klick-Runde genau die Frage, die man
  // sich stellt. Seit die AUSWAHL in jedem Reiter steht, ist der Grund weg und
  // der Name stand dreimal gleichzeitig auf dem Schirm: oben in der Auswahl,
  // hier, und in der Bezugszeile des Werkzeugs. Von den dreien ist die
  // Bezugszeile die genaueste — sie sagt nicht nur WELCHE Sequenz offen ist,
  // sondern ob das Werkzeug sie überhaupt meint.
  const kopf = el("div", {class: "abschnitt"},
    el("span", {class: "ueberschrift"}, "WERKZEUGE"));
  const liste = el("div", {class: "abschnitt wachsend", style: "gap:6px"});
  for (const w of WZ_WERKZEUGE) {
    const knopf = el("button", {
      class: "wz-nav " + w.key + (wzOffen === w.key ? " an" : ""),
      onclick: () => wzOeffnen(w.key),
      // Der Konsolen-Befehl steht mit — dieselbe Regel wie bei den Config-
      // Schluesseln: wer das Werkzeug hier kennenlernt, erkennt es im
      // Punkte-Menue wieder, und wer es von dort kennt, findet es hier.
    }, el("span", {class: "wz-nav-icon"}, wzIcon(w.key)),
       el("span", {class: "wz-nav-copy"},
         el("span", {class: "wz-nav-titel"}, w.name,
           el("span", {class: "wz-befehl"}, w.befehl)),
         el("span", {class: "wz-nav-kurz"}, w.kurz)),
       el("span", {class: "wz-nav-pfeil"}, "›"));
    liste.appendChild(knopf);
  }
  liste.appendChild(wzInfo("Slots exakt reparieren",
    "CTRL+ALT+N → Slots → repair misst die Flächen pixelgenau neu."));
  ziel.replaceChildren(kopf, liste);
  hilfenAnwenden(ziel);
}

/** Ein Werkzeug öffnen — auch als Sprungziel aus dem Editor heraus. */
function wzOeffnen(key) {
  if (!WZ_WERKZEUGE.some(w => w.key === key)) return;
  wzOffen = key;
  if (ansicht !== "werkzeuge") {
    setzeAnsicht("werkzeuge");
    return;
  }
  wzMitteZeichnen();
  wzRechtsZeichnen();
  wzLinksZeichnen();
}

function wzMitteZeichnen() {
  const ziel = $("wz-mitte");
  const inhalt = wzOffen === "aufnahme" ? wzAufnahmeBauen()
    : wzOffen === "pruefen" ? wzPruefenBauen()
    : wzOffen === "points" ? wzPunkteBauen()
    : wzOffen === "colors" ? wzFarbenBauen()
    : wzOffen === "kalibrieren" ? wzKalibBauen() : wzKlickenBauen();
  ziel.replaceChildren(...inhalt);
  // Offene i-Texte ueberleben den Neuaufbau nach einer Werkzeug-Aktion.
  hilfenAnwenden(ziel);
}

/* ------------------------------------------------------------------ Prüfen */

function wzPruefenBauen() {
  const raus = [wzKopf("pruefen", "Setup prüfen",
    "Ein vollständiger Gesundheitscheck für die gespeicherten Sequenzen und Scans.")];
  raus.push(wzBezug("pruefen"));
  raus.push(wzInfo("Was wird geprüft?",
    "Templates, Erkennungsmethoden, Punkt- und Scan-Verweise sowie Stellen "
    + "ausserhalb der angeschlossenen Monitore. Es zählt der zuletzt gespeicherte Stand."));
  raus.push(el("div", {class: "wz-aktion reihe"},
    el("button", {class: "btn haupt wz-hauptaktion", onclick: wzPruefen},
      wzIcon("pruefen"), el("span", {}, "Jetzt prüfen"))));

  if (!wzBericht) return raus;
  if (!wzBericht.ok) {
    raus.push(el("p", {class: "art-err"}, wzBericht.message || "Prüfung fehlgeschlagen."));
    return raus;
  }
  if (!wzBericht.befunde.length) {
    raus.push(el("div", {class: "wz-erfolg"}, wzIcon("ok"),
      el("div", {}, el("b", {}, "Alles in Ordnung"),
        el("span", {}, wzBericht.checked.length + " Bereiche ohne Befund geprüft."))));
    return raus;
  }
  raus.push(el("div", {class: "wz-kennzahlen"},
    wzKennzahl(String(wzBericht.fehler || 0), "Fehler", "fehler"),
    wzKennzahl(String(wzBericht.hints || 0), "Hinweise", "hinweis"),
    wzKennzahl(String(wzBericht.checked.length), "Bereiche", "neutral")));
  // Fehler zuerst: „laeuft so nicht" schlaegt „ist vermutlich nicht gewollt".
  for (const stufe of ["fehler", "hinweis"]) {
    const treffer = wzBericht.befunde.filter(b => b.stufe === stufe);
    if (!treffer.length) continue;
    raus.push(el("h3", {style: "margin-top:16px"},
      stufe === "fehler" ? "Fehler (" + treffer.length + ")"
                         : "Hinweise (" + treffer.length + ")"));
    for (const b of treffer) raus.push(wzBefund(b, stufe));
  }
  return raus;
}

/* ------------------------------------------------------ Punkte verwalten */

function wzPunkteBauen() {
  const raus = [wzKopf("points", "Punkte verwalten",
    "Klickstellen sind eigenständige Objekte — jede Änderung zieht alle verwendenden Blöcke mit.")];
  raus.push(wzBezug("points"));
  const points = (W && W.points) || [];
  if (!points.some(p => p.id === wzPunktId)) wzPunktId = points.length ? points[0].id : null;
  const point = points.find(p => p.id === wzPunktId);
  const neuName = el("input", {placeholder: "Name des neuen Punkts", value: "Neuer Punkt",
    autocomplete: "off"});
  raus.push(el("div", {class: "wz-aktion gitter2"}, neuName,
    el("button", {class: "btn haupt", onclick: async () => {
      setzeStatus({kind: "info", text: "Ins Spiel wechseln, Maus platzieren und ENTER drücken …"});
      const a = await mitWarten("werkzeug", "tool_point_capture",
                                {name: neuName.value});
      if (a && a.ok) wzPunktId = a.point_id;
    }}, "＋ Neuen Punkt aufnehmen")));
  if (!point) {
    raus.push(el("p", {class: "empty"}, "Noch keine Punkte in dieser Sequenz."));
    return raus;
  }
  raus.push(selection("Punkt", points.map(p => ({value: p.id,
    text: "#" + p.id + " " + p.name + " (" + p.x + ", " + p.y + ")"})), point.id,
    (v) => { wzPunktId = Number(v); wzMitteZeichnen(); wzRechtsZeichnen(); }));
  const setze = (feld, value) => rufWerkzeug("tool_point_set",
    {point_id: point.id, feld: feld, value: value});
  raus.push(feld("Name", point.name, (v) => setze("name", v)));
  raus.push(el("div", {class: "gitter2"},
    zahlfeld("X", point.x, (v) => setze("x", v), {step: "1"}),
    zahlfeld("Y", point.y, (v) => setze("y", v), {step: "1"})));
  raus.push(color_swatch("Gespeicherte Farbe", point.color ? hexfarbe(point.color) : "",
    (v) => setze("color", v)));
  raus.push(el("div", {class: "reihe", style: "gap:8px;flex-wrap:wrap"},
    el("button", {class: "btn", onclick: () => rufWerkzeug("tool_point_show",
      {point_id: point.id})}, "◎ Zeigen & Farbe prüfen"),
    el("button", {class: "btn", onclick: () => mitWarten("werkzeug",
      "tool_point_capture", {point_id: point.id})}, "✛ Neu messen"),
    // Ausdruecklich ein Boolean, nicht die Anzahl: die Absicht ist „gesperrt,
    // SOLANGE er benutzt wird" — als Zahl gelesen hiess sie das Gegenteil.
    el("button", {class: "btn gefahr", disabled: point.usages.length > 0,
      title: point.usages.length ? "Erst die aufgeführten Verwendungen entfernen" : "",
      onclick: () => rufWerkzeug("tool_point_delete", {point_id: point.id})},
      "Löschen")));
  if (point.usages.length) raus.push(el("p", {class: "hinweis"},
    "Löschen ist gesperrt: Dieser Punkt wird noch " + point.usages.length + "× verwendet."));
  return raus;
}

/* ------------------------------------------------------ Farben analysieren */

function wzFarbenBauen() {
  const raus = [wzKopf("colors", "Farben analysieren",
    "Liest einen Pixel oder gruppiert die häufigsten Farben eines Bildschirmbereichs.")];
  // Fuenf Werkzeuge trugen ihre Bezugszeile, dieses nicht — obwohl „jedes
  // Werkzeug sagt, WORAUF es wirkt" die Regel des Reiters ist. Gerade hier ist
  // die Antwort die beruhigende: es fasst nichts an.
  raus.push(wzBezug("colors"));
  raus.push(wzInfo("Aufnahme ohne Studio im Bild",
    "Nach dem Klick ins Spiel wechseln. Punkt und Vollbild starten mit ENTER; bei einer Region " +
    "werden obere linke und untere rechte Ecke jeweils mit ENTER bestätigt."));
  const starten = async (kind) => {
    setzeStatus({kind: "info", text: "Ins Spiel wechseln und mit ENTER bestätigen …"});
    wzFarbAnalyse = await mitWarten("werkzeug", "tool_colors", {kind: kind});
    wzMitteZeichnen(); wzRechtsZeichnen();
  };
  raus.push(el("div", {class: "gitter3 wz-aktion"},
    el("button", {class: "btn haupt", onclick: () => starten("point")}, "Pixel unter Maus"),
    el("button", {class: "btn", onclick: () => starten("region")}, "Bereich analysieren"),
    el("button", {class: "btn", onclick: () => starten("fullscreen")}, "Vollbild analysieren")));
  if (wzFarbAnalyse && !wzFarbAnalyse.ok)
    raus.push(el("p", {class: "art-err"}, wzFarbAnalyse.message || "Analyse fehlgeschlagen."));
  if (wzFarbAnalyse && wzFarbAnalyse.ok) {
    const liste = el("div", {class: "wz-farbliste"});
    for (const f of wzFarbAnalyse.colors || []) liste.appendChild(el("div", {class: "wz-farbzeile"},
      el("span", {class: "wz-farbprobe", style: "background:" + f.hex}),
      el("b", {class: "mono"}, f.hex),
      el("span", {}, "RGB " + f.rgb.join(", ")),
      el("span", {class: "wachse hint"}, f.name || ""),
      el("span", {class: "mono"}, f.anteil + "%")));
    raus.push(liste);
  }
  return raus;
}

/* --------------------------------------------------------------- Aufnehmen */

function wzNeuerAufnahmeName() {
  const d = new Date(), z = (n) => String(n).padStart(2, "0");
  return "aufnahme_" + z(d.getHours()) + z(d.getMinutes()) + z(d.getSeconds());
}

function wzAufnahmeBauen() {
  if (!wzAufnahmeName) wzAufnahmeName = wzNeuerAufnahmeName();
  const raus = [wzKopf("aufnahme", "Sequenz aufnehmen",
    "Spiele den Ablauf einmal vor — jeder Klick, Tastendruck und Marker wird direkt zu Blöcken.")];
  raus.push(wzBezug("aufnahme"));

  const formular = el("div", {class: "wz-aufnahme-form"});
  const name = el("input", {value: wzAufnahmeName, autocomplete: "off",
    disabled: wzAufnahmeGestartet});
  name.addEventListener("input", () => { wzAufnahmeName = name.value; });
  const cycles = el("input", {type: "number", min: "0", step: "1",
    value: String(wzAufnahmeZyklen), disabled: wzAufnahmeGestartet});
  cycles.addEventListener("input", () => { wzAufnahmeZyklen = Math.max(0, Number(cycles.value) || 0); });
  const notiz = el("textarea", {rows: "3", disabled: wzAufnahmeGestartet,
    placeholder: "optional — wofür ist diese Sequenz?"}, wzAufnahmeBeschreibung);
  notiz.addEventListener("input", () => { wzAufnahmeBeschreibung = notiz.value; });
  formular.append(
    el("label", {class: "feld"}, "Name", name),
    el("label", {class: "feld"}, "Zyklen · 0 = endlos", cycles),
    el("label", {class: "feld wz-aufnahme-notiz"}, "Notiz", notiz));
  raus.push(formular);

  const stamp = el("div", {class: "wz-aufnahme-stand" +
    (wzAufnahmeGestartet ? " laeuft" : "")},
    el("span", {class: "wz-rec-punkt"}),
    el("div", {}, el("b", {}, wzAufnahmeGestartet ? "Aufnahme läuft" : "Bereit zur Aufnahme"),
      el("span", {}, wzAufnahmeGestartet
        ? "Ins Spiel wechseln. Der Stopp-Knopf und CTRL+ALT+J bauen danach die Blöcke."
        : "Starten, ins Spiel wechseln und den gewünschten Ablauf einmal ausführen.")));
  const action = el("button", {
    class: "btn " + (wzAufnahmeGestartet ? "gefahr" : "haupt") + " wz-aufnahme-knopf",
    onclick: wzAufnahmeGestartet ? wzAufnahmeStoppen : wzAufnahmeStarten,
  }, wzAufnahmeGestartet ? "■ Aufnahme stoppen" : "● Aufnahme starten");
  stamp.appendChild(action);
  raus.push(stamp);

  const ausgabe = el("div", {class: "wz-aufnahme-ausgabe", id: "wz-aufnahme-ausgabe"});
  raus.push(ausgabe);
  wzAufnahmeAusgabeFuellen(ausgabe);

  raus.push(el("div", {class: "wz-zwischenkopf"}, "HOTKEYS WÄHREND DER AUFNAHME"));
  raus.push(wzTastenTabelle((W && W.aufnahme_tasten) || []));
  raus.push(wzInfo("TUI bleibt verfügbar",
    "CTRL+ALT+J kann die Aufnahme weiterhin ganz ohne Studio starten. Dann werden "
    + "Name, Zyklen und Notiz wie bisher beim Beenden in der Konsole abgefragt."));
  return raus;
}

async function wzAufnahmeStarten() {
  const name = wzAufnahmeName.trim();
  if (!name) {
    setzeStatus({text: "Bitte zuerst einen Namen eingeben.", kind: "err"});
    return;
  }
  const antwort = await frage("recording_start", {
    name: name, cycles: wzAufnahmeZyklen, beschreibung: wzAufnahmeBeschreibung});
  if (!antwort) return;
  setzeStatus({text: antwort.message || "", kind: antwort.ok ? "ok" : "err"});
  if (!antwort.ok) return;
  wzAufnahmeName = antwort.name || name;
  wzAufnahmeGestartet = true;
  wzAufnahmeLive = {active: true, pausiert: false, count: 0, events: []};
  wzAufnahmeBeobachten();
  wzMitteZeichnen();
  wzRechtsZeichnen();
  wzAufnahmeLiveStarten();
}

/** Drei feste Zeilen statt eines wachsenden Logs: neuestes Ereignis unten. */
function wzAufnahmeAusgabeFuellen(ziel) {
  if (!ziel) return;
  const daten = wzAufnahmeLive || {};
  const events = Array.isArray(daten.events) ? daten.events.slice(-3) : [];
  const kopftext = daten.pausiert ? "PAUSIERT" : wzAufnahmeGestartet ? "LIVE" : "LETZTE EREIGNISSE";
  ziel.replaceChildren(el("div", {class: "wz-ausgabe-kopf"},
    el("span", {}, kopftext),
    el("span", {class: "wz-ausgabe-zaehler"}, String(daten.count || 0) + " Ereignisse")));
  const rows = el("div", {class: "wz-ausgabe-zeilen"});
  if (!events.length) {
    rows.appendChild(el("div", {class: "wz-ausgabe-leer"},
      wzAufnahmeGestartet ? "Warte auf das erste Ereignis …" : "Noch nichts aufgenommen."));
  } else {
    events.forEach((e, i) => {
      const color = e.color
        ? el("span", {class: "wz-ausgabe-farbe",
            style: "color:rgb(" + e.color.join(",") + ")"}, "█") : null;
      rows.appendChild(el("div", {class: "wz-ausgabe-zeile" +
          (i === events.length - 1 ? " neu" : "")},
        el("span", {class: "wz-ausgabe-nr"}, String(e.number || "")),
        el("span", {class: "wz-ausgabe-text"}, e.text || "—"),
        el("span", {class: "wz-ausgabe-zeit"}, e.zeit || ""),
        el("span", {class: "wz-ausgabe-farbtext"}, color, e.color_text || "")));
    });
  }
  ziel.appendChild(rows);
}

function wzAufnahmeLiveStarten() {
  const number = ++wzAufnahmeLivePoll;
  const lesen = async () => {
    if (number !== wzAufnahmeLivePoll || !wzAufnahmeGestartet) return;
    const status = await frage("recording_status");
    if (status) {
      wzAufnahmeLive = status;
      wzAufnahmeAusgabeFuellen($("wz-aufnahme-ausgabe"));
    }
    setTimeout(lesen, 300);
  };
  setTimeout(lesen, 150);
}

async function wzAufnahmeStoppen() {
  const antwort = await frage("recording_stop");
  if (!antwort) return;
  setzeStatus({text: antwort.message || "", kind: antwort.ok ? "ok" : "err"});
  if (antwort.ok) wzAufnahmeBeobachten(true);
}

/** Findet die vom Hauptprozess gespeicherte Datei und öffnet ihre fertigen Blöcke.
 *
 * **Gefragt wird erst, wenn es etwas zu finden gibt.** `sequence_list()` laedt
 * JEDE Sequenzdatei einzeln (Migration und Punkt-Aufloesung inklusive) — genau
 * deshalb zieht `zeichne()` sie nicht nach. Der langsame Zweig rief sie
 * trotzdem im Sekundentakt, unbegrenzt, ab dem Druck auf „Aufnahme starten":
 * also waehrend der ganzen Aufnahme, und die dauert per Definition lange, weil
 * der Nutzer so lange im Spiel ist. Solange die Aufnahme laeuft, kann die Datei
 * aber gar nicht da sein — `stop_recording()` schreibt sie. Der billige
 * Live-Stand (eine kleine JSON-Datei) sagt, wann das so weit ist.
 *
 * Die Wartezeit selbst bleibt unbegrenzt: eine Stunde aufzunehmen ist erlaubt.
 * Begrenzt wird nur der Fall, in dem die Aufnahme NIE anlaeuft — dann hoert
 * niemand zu, und das ist eine Meldung wert statt eines stillen Dauerlaufs. */
function wzAufnahmeBeobachten(schnell = false) {
  const number = ++wzAufnahmePoll;
  let versuche = 0;
  const pruefen = async () => {
    if (number !== wzAufnahmePoll || !wzAufnahmeGestartet) return;
    if (!schnell) {
      // Laeuft sie noch, gibt es nichts zu holen: billig warten statt fragen.
      if (wzAufnahmeLive && wzAufnahmeLive.active) {
        versuche = 0;
        return void setTimeout(pruefen, 1000);
      }
      // Der Zaehler steht nur still, solange die Aufnahme laeuft (oben auf 0
      // gesetzt). Eine Minute Suchen ohne laufende Aufnahme heisst also
      // entweder „nie angelaufen" oder „gestoppt, aber nichts geschrieben" —
      // beides gehoert gesagt statt still weitergedreht.
      if (versuche >= 60) {
        wzAufnahmeGestartet = false;
        ++wzAufnahmeLivePoll;
        wzMitteZeichnen();
        setzeStatus({text: "Keine laufende Aufnahme — hört der Hauptprozess zu?",
                     kind: "warn"});
        return;
      }
    }
    const liste = (await frage("sequence_list")) || [];
    if (liste.some(s => s.name === wzAufnahmeName)) {
      wzAufnahmeGestartet = false;
      ++wzAufnahmeLivePoll;
      await ruf("load", {name: wzAufnahmeName});
      setzeAnsicht("editor");
      setzeStatus({text: "Aufnahme gespeichert — die erzeugten Blöcke sind geöffnet.", kind: "ok"});
      return;
    }
    versuche += 1;
    if (schnell && versuche >= 12) {
      wzAufnahmeGestartet = false;
      ++wzAufnahmeLivePoll;
      wzMitteZeichnen();
      setzeStatus({text: "Keine gespeicherte Aufnahme gefunden — wurde etwas aufgezeichnet?", kind: "warn"});
      return;
    }
    setTimeout(pruefen, schnell ? 350 : 1000);
  };
  setTimeout(pruefen, schnell ? 350 : 1000);
}

function wzKennzahl(value, label, kind) {
  return el("div", {class: "wz-kennzahl " + kind},
    el("strong", {}, value), el("span", {}, label));
}

function wzBefund(b, stufe) {
  const kasten = el("div", {class: "wz-befund " + stufe});
  kasten.appendChild(el("div", {class: "wz-befund-icon"}, wzIcon(stufe)));
  const copy = el("div", {class: "wz-befund-copy"},
    el("div", {class: "wz-bereich"}, b.area), el("div", {}, b.text));
  if (b.tipp) copy.appendChild(el("div", {class: "hint", style: "white-space:normal"}, b.tipp));
  kasten.appendChild(copy);
  return kasten;
}

function wzGeprueftBauen() {
  const kopf = el("div", {class: "abschnitt"},
    el("span", {class: "ueberschrift"}, "GEPRÜFT"));
  const liste = el("div", {class: "abschnitt wachsend", style: "gap:4px"});
  if (!wzBericht || !wzBericht.ok) {
    liste.appendChild(el("div", {class: "hint", style: "white-space:normal"},
      "Noch nichts geprüft."));
  } else {
    for (const b of wzBericht.checked)
      liste.appendChild(el("div", {class: "wz-geprueft"}, wzIcon("ok"), el("span", {}, b)));
  }
  return [kopf, liste];
}

async function wzPruefen() {
  setzeStatus({text: "Prüfe…", kind: "info"});
  wzBericht = await frage("tool_check");
  if (!wzBericht) return;
  const n = wzBericht.fehler || 0, h = wzBericht.hints || 0;
  setzeStatus({
    text: !wzBericht.ok ? (wzBericht.message || "Prüfung fehlgeschlagen.")
        : (n || h) ? n + " Fehler, " + h + " Hinweis(e)."
        : "Alles in Ordnung.",
    kind: !wzBericht.ok || n ? "err" : h ? "warn" : "ok",
  });
  wzMitteZeichnen();
  // **Auch rechts.** Hier stand nur `wzMitteZeichnen()`, und damit blieb in der
  // rechten Spalte „Noch nichts geprüft." stehen, während in der Mitte längst
  // der Bericht lag. Ausgerechnet dort: die Spalte listet, WAS geprüft wurde,
  // und ohne sie ist „Alles in Ordnung" eine Behauptung — genau die Begründung,
  // mit der sie gebaut wurde. Jeder andere Werkzeug-Befehl zeichnet beides
  // (`rufWerkzeug` über `zeichneWerkzeuge`); dieser eine ging seinen eigenen
  // Weg, weil er `frage()` direkt ruft.
  wzRechtsZeichnen();
}

/* ------------------------------------------------------------- Kalibrieren */

function wzKalibBauen() {
  const K = (W && W.kalibrierung) || {};
  const raus = [wzKopf("kalibrieren", "Koordinaten kalibrieren",
    "Einen bekannten Punkt neu messen und alle gespeicherten Stellen präzise mitziehen.")];
  raus.push(wzBezug("kalibrieren"));
  raus.push(wzInfo("Wann brauche ich das?",
    "Wenn Windows Monitore verschoben oder die Auflösung geändert hat. Der erste "
    + "Referenzpunkt bestimmt die Verschiebung, ein zweiter optional die Skalierung."));

  if (!W || !W.points.length) {
    raus.push(el("p", {class: "art-err"}, "Keine Punkte vorhanden — es gibt nichts zu kalibrieren."));
    return raus;
  }

  raus.push(wzRefZeile(1, K.ref1));
  // Der zweite Punkt erst anbieten, wenn der erste steht: ohne Verschiebung
  // gibt es keine Skalierung, und zwei leere Felder nebeneinander sehen aus,
  // als muesste man beide ausfuellen.
  if (K.ref1) {
    raus.push(wzInfo("Zweiter Referenzpunkt",
      "Nur wenn sich auch die Auflösung geändert hat: Dann einen zweiten Punkt "
      + "möglichst weit vom ersten entfernt anfahren."));
    raus.push(wzRefZeile(2, K.ref2));
  }

  if (K.ref1) {
    raus.push(el("div", {class: "wz-zwischenkopf"}, "BERECHNETER TRANSFORM"));
    const v = K.versatz || {x: 0, y: 0};
    const values = el("div", {class: "wz-kennzahlen"},
      wzKennzahl(wzVorz(v.x), "X-Versatz", "neutral"),
      wzKennzahl(wzVorz(v.y), "Y-Versatz", "neutral"));
    if (K.skalierung && (K.skalierung.x !== 1 || K.skalierung.y !== 1))
      values.appendChild(wzKennzahl(K.skalierung.x + "×" + K.skalierung.y,
        "Skalierung X/Y", "hinweis"));
    raus.push(values);
    raus.push(wzVersatzFelder(v));
    if (K.identity)
      raus.push(el("p", {class: "art-warn"},
        "Der Transform ändert nichts — der Punkt sitzt schon richtig."));
    raus.push(wzUmfangKasten());
    const leiste = el("div", {style: "display:flex;gap:8px;margin-top:14px"});
    leiste.appendChild(el("button", {
      class: "btn haupt", disabled: !!K.identity,
      onclick: () => rufWerkzeug("calib_apply", {...wzUmfang}),
    }, "Umrechnen und speichern"));
    leiste.appendChild(el("button", {
      class: "btn", onclick: () => rufWerkzeug("calib_cancel"),
    }, "Verwerfen"));
    raus.push(leiste);
    raus.push(wzInfo("Sicherung und laufende Sequenz",
      "Vorher entsteht ein vollständiges Export-ZIP als Sicherung. Läuft eine "
      + "Sequenz, wird nicht umgerechnet — sie klickt sonst mitten im Umbau."));
  }
  return raus;
}

function wzVorz(n) { return (n > 0 ? "+" : "") + n; }

function wzFarbe(rgb) {
  return el("span", {class: "wz-farbe",
                     style: "background:rgb(" + rgb.join(",") + ")"});
}

/** Die Rueckfrage bei abweichender Farbe: beide Farben nebeneinander, dann
 *  entscheiden. Gesperrt wird nichts — manchmal hat sich das Spiel geaendert und
 *  die neue Farbe ist die richtige. Es soll nur nicht aus Versehen gehen. */
function wzFarbfrageBauen() {
  const f = wzFarbfrage;
  const kasten = el("div", {class: "wz-farbfrage"});
  kasten.appendChild(el("div", {class: "art-warn"}, f.message));
  const reihe = el("div", {class: "wz-farbreihe"});
  reihe.append(el("span", {class: "hint"}, "gespeichert"), wzFarbe(f.expected),
               el("span", {class: "hint"}, "dort gemessen"), wzFarbe(f.gemessen),
               el("span", {class: "hint"},
                  "(" + f.position[0] + ", " + f.position[1] + ")"));
  kasten.appendChild(reihe);
  const leiste = el("div", {style: "display:flex;gap:8px"});
  leiste.appendChild(el("button", {
    class: "btn", onclick: async () => {
      const n = f.number, id = f.point_id;
      wzFarbfrage = null;
      // Auch „Trotzdem setzen" misst die Stelle NEU — calib_reference wartet
      // in jedem Fall auf ENTER. Ohne den Hinweis sieht der Knopf aus, als
      // habe er nichts getan.
      await mitWarten("werkzeug", "calib_reference",
                      {number: n, point_id: id, confirmed: true});
    },
  }, "Trotzdem setzen"));
  leiste.appendChild(el("button", {
    class: "btn haupt", onclick: () => {
      wzFarbfrage = null;
      setzeStatus({text: "Verworfen — nichts gesetzt.", kind: "info"});
      zeichneWerkzeuge();
    },
  }, "Nochmal anfahren"));
  kasten.appendChild(leiste);
  kasten.appendChild(el("div", {class: "hint", style: "white-space:normal"},
    "\u201eTrotzdem setzen\u201c ist richtig, wenn sich das Spiel geändert hat. Sonst "
    + "erst nachsehen: ein danebenliegender Referenzpunkt verschiebt nicht sich "
    + "selbst, sondern jede gespeicherte Stelle."));
  return kasten;
}

/** Der Punkt mit dem groessten Abstand zum ersten Referenzpunkt.
 *
 * Zwei nah beieinander liegende Punkte machen die Skalierung unbrauchbar: der
 * Messfehler der Maus (ein paar Pixel) verteilt sich dann auf eine kurze
 * Strecke und wird zum Faktor hochgerechnet. */
function wzWeitesterPunkt(ref1) {
  let beste = W.points[0], weit = -1;
  for (const p of W.points) {
    if (ref1 && p.id === ref1.point_id) continue;
    const d = Math.hypot(p.x - (ref1 ? ref1.alt[0] : 0), p.y - (ref1 ? ref1.alt[1] : 0));
    if (d > weit) { weit = d; beste = p; }
  }
  return beste.id;
}

/** Eine Referenzpunkt-Zeile: welchen Punkt, und der Knopf zum Anfahren. */
function wzRefZeile(number, placed) {
  const kasten = el("div", {class: "wz-ref"});
  kasten.appendChild(el("div", {class: "wz-bereich"},
    number === 1 ? "1. Referenzpunkt (Verschiebung)"
                 : "2. Referenzpunkt (Skalierung, optional)"));
  const wahl = el("select");
  for (const p of W.points)
    wahl.appendChild(el("option", {value: String(p.id)},
      "#" + p.id + " " + p.name + " (" + p.x + ", " + p.y + ")"));
  if (placed) wahl.value = String(placed.point_id);
  // Der zweite Punkt soll WEIT weg vom ersten liegen — genau das steht als
  // Hinweis darueber. Der erste Eintrag der Liste ist aber der erste Punkt
  // selbst, und den lehnt die Bruecke ab: ein Vorschlag, der garantiert eine
  // Fehlermeldung ergibt, ist schlimmer als gar keiner.
  else if (number === 2) wahl.value = String(wzWeitesterPunkt(W.kalibrierung.ref1));
  kasten.appendChild(wahl);
  kasten.appendChild(el("button", {
    class: "btn",
    onclick: async () => {
      setzeStatus({text: "Maus auf die Stelle, dann ENTER (ESC bricht ab)…", kind: "info"});
      const antwort = await mitWarten("frage", "calib_reference",
        {number, point_id: Number(wahl.value)});
      // Die Farbe passt nicht: nachfragen statt setzen. Ein Referenzpunkt, der
      // danebenliegt, verschiebt nicht sich selbst, sondern ALLES.
      if (antwort && antwort.confirm) { wzFarbfrage = {...antwort, number}; }
      else if (antwort && antwort.message)
        setzeStatus({text: antwort.message, kind: antwort.ok ? "ok" : "err"});
      await zeichneWerkzeuge();
    },
  }, placed ? "Neu anfahren" : "Stelle anfahren"));
  if (wzFarbfrage && wzFarbfrage.number === number)
    kasten.appendChild(wzFarbfrageBauen());
  if (placed)
    kasten.appendChild(el("div", {class: "hint"},
      "(" + placed.alt[0] + ", " + placed.alt[1] + ") → ("
      + placed.neu[0] + ", " + placed.neu[1] + ")"));
  return kasten;
}

/** Versatz von Hand nachziehen — mit der Maus trifft man den Pixel nicht genau. */
function wzVersatzFelder(v) {
  const kasten = el("div", {class: "wz-ref"});
  kasten.appendChild(el("div", {class: "wz-bereich"}, "Versatz von Hand"));
  const felder = {};
  for (const achse of ["x", "y"]) {
    const feld = el("input", {type: "number", step: "1", value: String(v[achse]),
                              style: "width:90px"});
    felder[achse] = feld;
    kasten.append(el("span", {}, achse.toUpperCase()), feld);
  }
  kasten.appendChild(el("button", {
    class: "btn", onclick: () => rufWerkzeug("calib_offset",
      {x: felder.x.value, y: felder.y.value}),
  }, "Übernehmen"));
  kasten.appendChild(wzInfo("Versatz von Hand",
    "Weisst du, dass eine Achse stimmt, ist eine getippte 0 genauer als jede Messung."));
  return kasten;
}

function wzUmfangKasten() {
  const kasten = el("div", {class: "wz-ref", style: "flex-direction:column;align-items:stretch"});
  kasten.appendChild(el("div", {class: "wz-bereich"}, "Was mitgerechnet wird"));
  kasten.appendChild(wzInfo("Punkte",
    "Punkte werden immer mitgerechnet — daran hängt alles andere."));
  for (const u of W.umfang) {
    const row = el("label", {class: "teilen-zeile an"});
    const box = el("input", {type: "checkbox"});
    box.checked = !!wzUmfang[u.key];
    box.addEventListener("change", () => { wzUmfang[u.key] = box.checked; });
    row.append(box, el("span", {}, u.text));
    kasten.appendChild(row);
  }
  kasten.appendChild(wzInfo("Warum Slots standardmässig aus sind",
    "Slots stehen getrennt und sind aus: nach einem repair dürfen sie kein "
    + "zweites Mal wandern."));
  return kasten;
}

/* --------------------------------------------------------- Punkte nachklicken */

/* Die vier Griffe während der Runde — dieselbe Liste wie `TASTEN` in
 * `editors/nachklick.py`. Sie steht hier als Tabelle und nicht als Absatz, weil
 * man sie MITTEN im Klicken nachschlägt: Fliesstext zwingt zum Lesen von vorn,
 * und dann liest ihn niemand. */
const WZ_TASTEN = [
  ["CTRL+ALT+K", "überspringen", "Punkt bleibt, wo er ist"],
  ["CTRL+ALT+U", "zurück", "einen Punkt zurück, noch mal"],
  ["CTRL+ALT+H", "pausieren", "navigieren, ohne einen Punkt zu verbrauchen"],
  ["CTRL+ALT+J", "übernehmen", "fertig — JETZT werden die Punkte geschrieben"],
];

/* Was die Runde tut, in der Reihenfolge, in der es passiert. Drei Schritte statt
 * dreier Absätze: der Ablauf IST die Erklärung. */
const WZ_SCHRITTE = [
  ["Starten", "Der Zeiger springt auf den ersten Punkt der Sequenz."],
  ["Klicken", "Stimmt die Stelle noch? Dann einfach klicken. Sonst hinfahren und "
            + "dort klicken — der Klick geht ans Spiel, die Oberfläche öffnet "
            + "sich wie im Lauf, und der nächste Punkt liegt vor dir."],
  ["Übernehmen", "Erst damit werden die Punkte geschrieben. Vorher ändert sich "
               + "nichts — an keiner Datei und in keinem Speicher."],
];

function wzTastenTabelle(tasten = WZ_TASTEN) {
  const rumpf = el("tbody");
  for (const [taste, was, warum] of tasten)
    rumpf.appendChild(el("tr", {},
      el("td", {}, el("span", {class: "wz-taste"}, taste)),
      el("td", {class: "wz-was"}, was),
      el("td", {class: "wz-warum"}, warum)));
  return el("table", {class: "wz-tasten"}, rumpf);
}

/* Was ein erledigter Punkt geworden ist. Vier Ausgaenge, weil die Runde vier
 * kennt — und „bestaetigt" von „uebersprungen" zu unterscheiden ist der ganze
 * Grund fuer `reclick_history`: beide aendern nichts, aber nur einer heisst
 * „ich habe hingesehen". */
const WZ_NK_ART = {
  passt: ["✓", "nk-passt", "bestätigt — bleibt, wo er ist"],
  placed: ["→", "nk-gesetzt", "neu gesetzt"],
  skipped: ["↷", "nk-skip", "übersprungen"],
  fehlt: ["✕", "nk-fehlt", "Punkt gibt es nicht mehr"],
};

/** Der Live-Stand der Runde: wo sie steht, was dran ist, was war. */
function wzNachklickAusgabeFuellen(ziel) {
  if (!ziel) return;
  const d = wzNachklickLive || {};
  const total = d.total || 0;
  const fertig = Math.min(d.index || 0, total);
  const running = !!d.active && !d.verwaist;

  // Der Kopf beantwortet die erste Frage („laeuft das ueberhaupt noch?"), und
  // ein verwaister Stand sagt es, statt eine tote Runde als lebend zu zeigen.
  const kopftext = d.verwaist ? "KEIN HAUPTPROZESS"
    : d.pausiert ? "PAUSIERT" : running ? "LÄUFT" : total ? "BEENDET" : "NICHT GESTARTET";
  ziel.replaceChildren(el("div", {class: "wz-ausgabe-kopf"},
    el("span", {}, kopftext),
    el("span", {class: "wz-ausgabe-zaehler"},
      total ? fertig + " von " + total + " Punkt(en)" : "—")));

  if (!total) {
    ziel.appendChild(el("div", {class: "wz-ausgabe-zeilen"},
      el("div", {class: "wz-ausgabe-leer"},
        "Noch keine Runde gelaufen. „Runde starten“ setzt den Zeiger auf den "
        + "ersten Punkt.")));
    return;
  }

  // Ein Balken statt einer zweiten Zahl: wie weit die Runde ist, sieht man
  // beim Klicken aus dem Augenwinkel — eine Zahl muss man lesen.
  ziel.appendChild(el("div", {class: "nk-balken"},
    el("div", {class: "nk-balken-fuell",
               style: "width:" + Math.round(fertig / total * 100) + "%"})));

  // Der aktuelle Punkt ist die Antwort auf „was macht das Programm gerade".
  const p = d.point || {};
  if (running && p.id !== undefined) {
    ziel.appendChild(el("div", {class: "nk-jetzt"},
      el("span", {class: "nk-jetzt-marke"}, "jetzt"),
      el("span", {class: "zahl"}, "#" + p.id),
      el("span", {class: "nk-jetzt-name"}, p.name || ""),
      el("span", {class: "nk-jetzt-pos"}, "(" + p.x + ", " + p.y + ")"),
      p.color ? el("span", {class: "wz-ausgabe-farbe",
                            style: "color:rgb(" + p.color.join(",") + ")"}, "█") : null));
    ziel.appendChild(el("div", {class: "hint nk-hinweis"}, d.pausiert
      ? "Pausiert — Klicks setzen keinen Punkt. CTRL+ALT+H macht weiter."
      : "Der Zeiger steht schon dort. Stimmt die Stelle — klicken. Sonst "
        + "hinfahren und dort klicken."));
  } else if (!running && total) {
    ziel.appendChild(el("div", {class: "hint nk-hinweis"},
      (d.changed || 0) + " Stelle(n) geändert. Was davon geschrieben wurde, "
      + "hängt daran, ob übernommen oder verworfen wurde."));
  }

  // Der Verlauf laeuft rueckwaerts: das Letzte ist das, was man sucht.
  const history = Array.isArray(d.history) ? d.history.slice(-6).reverse() : [];
  const rows = el("div", {class: "wz-ausgabe-zeilen"});
  if (!history.length) {
    rows.appendChild(el("div", {class: "wz-ausgabe-leer"},
      "Noch kein Punkt erledigt."));
  } else {
    for (const v of history) {
      const [zeichen, klasse, was] = WZ_NK_ART[v.kind] || ["·", "", v.kind];
      rows.appendChild(el("div", {class: "nk-zeile"},
        el("span", {class: "nk-art " + klasse, title: was}, zeichen),
        el("span", {class: "zahl"}, "#" + v.id),
        el("span", {class: "nk-name"}, v.name || ""),
        el("span", {class: "nk-wohin"}, v.alt && v.neu
          ? "(" + v.alt[0] + ", " + v.alt[1] + ") → (" + v.neu[0] + ", " + v.neu[1] + ")"
          : was)));
    }
  }
  ziel.appendChild(rows);
  if (d.others)
    ziel.appendChild(el("div", {class: "hint nk-hinweis"},
      d.others + " Stelle(n) erreicht die Runde nicht (beobachtete Pixel, "
      + "ELSE, Rad) — dafür bleibt walk im Punkte-Menü."));
}

/* Gepollt wird, solange der Reiter offen ist — nicht nur nach dem eigenen
 * Startknopf. Die Runde kann aus dem Punkte-Menue gestartet worden sein, und
 * dann ist dieses Fenster trotzdem der bequemere Platz, um ihr zuzusehen.
 * Nach dem Ende laeuft der Poll aus (`ruhig`), damit ein offener Reiter nicht
 * dauerhaft alle 400 ms eine Datei liest. */
function wzNachklickLiveStarten() {
  const number = ++wzNachklickPoll;
  let ruhig = 0;
  const lesen = async () => {
    if (number !== wzNachklickPoll || wzOffen !== "klicken") return;
    const stamp = await frage("reclick_status");
    if (number !== wzNachklickPoll || wzOffen !== "klicken") return;
    if (stamp) {
      const lief = wzNachklickLive.active;
      wzNachklickLive = stamp;
      wzNachklickAusgabeFuellen($("wz-nachklick-ausgabe"));
      // Endet die Runde, sagt es die Statuszeile — sonst merkt man es nur,
      // wenn man gerade hinsieht.
      if (lief && !stamp.active)
        setzeStatus({text: "Klick-Runde beendet — " + (stamp.changed || 0)
                     + " Stelle(n) geändert.", kind: "ok"});
      ruhig = stamp.active ? 0 : ruhig + 1;
    } else {
      ruhig += 1;
    }
    if (ruhig > 12) return;
    setTimeout(lesen, wzNachklickLive.active ? 400 : 1000);
  };
  setTimeout(lesen, 100);
}

function wzKlickenBauen() {
  const raus = [wzKopf("klicken", "Punkte nachklicken",
    "Eine geführte Kontrollrunde durch alle Klickstellen der geöffneten Sequenz.")];
  raus.push(wzBezug("klicken"));

  const schritte = el("div", {class: "wz-schritte"});
  WZ_SCHRITTE.forEach(([title, text], i) => {
    schritte.append(el("div", {class: "wz-nummer"}, String(i + 1)),
      el("div", {class: "wz-schritt-text"}, el("b", {}, title + ": "), text));
  });
  raus.push(schritte);

  // Die eine Regel, an der alles haengt — als Kasten, nicht als Satz im Absatz.
  raus.push(el("div", {class: "wz-regel"},
    el("span", {}, "⚠"),
    el("span", {}, el("b", {}, "Nichts wird geschrieben, bis du übernimmst. "),
      "Fenster zu, Programm aus oder „Verwerfen“ = die Runde ist weg und "
      + "sequence.json bleibt, wie sie war. Geändert wird ohnehin nur die "
      + "Stelle: Wartezeiten, Bedingungen, ELSE und Scans bleiben unangetastet.")));

  const leiste = el("div", {style: "display:flex;gap:8px;margin-top:4px"});
  leiste.appendChild(el("button", {
    class: "btn haupt",
    // Wie beim Start einer Sequenz: der Befehl geht in den Briefkasten, und ob
    // ihn jemand abholt, sieht man erst daran, dass er verschwindet.
    onclick: async () => { await rufWerkzeug("reclick_start");
                           briefkastenNachfassen(); },
    title: "Startet die Runde im Hauptprozess — geklickt wird danach im Spiel",
  }, "Runde starten"));
  // Zwei Ausgaenge, weil es zwei Absichten gibt. Ein einzelner „Beenden"-Knopf
  // muesste sich fuer eine entscheiden und laege in der Haelfte der Faelle
  // falsch. Ob gerade eine Runde laeuft, weiss dieses Fenster nicht (der Zustand
  // liegt drueben) - die Knoepfe stehen deshalb immer da, und der Hauptprozess
  // sagt, was er vorgefunden hat.
  leiste.appendChild(el("button", {
    class: "btn", onclick: () => rufWerkzeug("reclick_end"),
    title: "Schreibt die gesetzten Stellen nach sequence.json (= CTRL+ALT+J)",
  }, "Übernehmen"));
  leiste.appendChild(el("button", {
    class: "btn", onclick: () => rufWerkzeug("reclick_end", {verwerfen: true}),
    title: "Beendet die Runde, ohne etwas zu schreiben",
  }, "Verwerfen"));
  raus.push(leiste);

  // Der Live-Stand steht ZWISCHEN Knoepfen und Tastentabelle: was das
  // Programm gerade macht, sucht man dort, wo man es gerade gestartet hat.
  const ausgabe = el("div", {class: "wz-ausgabe", id: "wz-nachklick-ausgabe"});
  raus.push(ausgabe);
  wzNachklickAusgabeFuellen(ausgabe);

  wzNachklickLiveStarten();
  raus.push(wzTastenTabelle());
  raus.push(wzInfo("Bedienung im Spiel",
    "Die Runde läuft wegen des systemweiten Maus-Hooks im Hauptprozess. Die "
    + "Tasten wirken überall — auch mit dem Spiel im Vordergrund. Gezählt "
    + "wird nur, was im Spielfenster geklickt wird (window_focus_title); ein "
    + "Klick woanders verbraucht keinen Punkt."));
  return raus;
}

/* ------------------------------------------------------------------- rechts */

function wzRechtsZeichnen() {
  const ziel = $("wz-rechts");
  // Beim Pruefen steht hier, WAS geprueft wurde. „Alles in Ordnung" ist ohne
  // diese Liste eine Behauptung: man weiss nicht, ob der Bereich sauber war
  // oder gar nicht angesehen wurde.
  if (wzOffen === "pruefen") return ziel.replaceChildren(...wzGeprueftBauen());
  if (wzOffen === "aufnahme")
    return ziel.replaceChildren(el("div", {class: "abschnitt"},
      el("span", {class: "ueberschrift"}, "SO ENTSTEHEN DIE BLÖCKE"),
      el("div", {class: "wz-aufnahme-ablauf"},
        el("b", {}, "1 · Starten"), el("span", {}, "Das Studio schickt Name und Einstellungen mit."),
        el("b", {}, "2 · Spielen"), el("span", {}, "Klicks, Tasten, Rad und Marker werden gesammelt."),
        el("b", {}, "3 · Stoppen"), el("span", {}, "Die Sequenz wird gespeichert und automatisch im Editor geöffnet."))));
  if (wzOffen === "points") {
    const point = W && W.points.find(p => p.id === wzPunktId);
    const kopf = el("div", {class: "abschnitt"},
      el("span", {class: "ueberschrift"}, "VERWENDUNGEN"),
      el("span", {class: "hint"}, point ? "Punkt #" + point.id : "kein Punkt gewählt"));
    const liste = el("div", {class: "abschnitt wachsend", style: "gap:5px"});
    if (!point || !point.usages.length)
      liste.appendChild(el("p", {class: "hinweis"}, "Dieser Punkt wird nirgends verwendet und kann sicher gelöscht werden."));
    else for (const v of point.usages)
      liste.appendChild(el("div", {class: "wz-geprueft"}, wzIcon("points"), el("span", {}, v)));
    return ziel.replaceChildren(kopf, liste);
  }
  if (wzOffen === "colors")
    return ziel.replaceChildren(el("div", {class: "abschnitt"},
      el("span", {class: "ueberschrift"}, "MESSUNG"),
      el("p", {class: "hinweis"}, wzFarbAnalyse && wzFarbAnalyse.ok
        ? (wzFarbAnalyse.message || "Analyse abgeschlossen.")
        : "Noch keine Analyse. Die Farbfelder erscheinen nach der Aufnahme in der Mitte.")));
  if (wzOffen === "klicken")
    // Als einziges Werkzeug stand hier keine Ueberschrift — die anderen fuenf
    // haben GEPRUEFT, SO ENTSTEHEN DIE BLOECKE, VERWENDUNGEN, MESSUNG und
    // VORSCHAU. Uebrig blieb ein Hinweis ohne Dach in einer sonst leeren
    // Spalte, und der sah aus, als sei die Spalte kaputt.
    return ziel.replaceChildren(el("div", {class: "abschnitt"},
      el("span", {class: "ueberschrift"}, "GRENZEN DER RUNDE"),
      wzInfo("Was die Runde nicht erreicht",
        "Beobachtete Pixel, Nachprüfungen, ELSE-Klicks und Rad-Schritte kommen "
        + "in einem normalen Durchlauf gar nicht vor. Dafür bleibt walk im "
        + "Punkte-Menü. Welche das sind, sagt die Runde beim Start in der Konsole.")));
  if (!W || !W.kalibrierung.ref1)
    return ziel.replaceChildren(el("div", {class: "abschnitt"},
      el("span", {class: "ueberschrift"}, "VORSCHAU"),
      el("div", {class: "hint", style: "white-space:normal"},
        "Sobald der erste Referenzpunkt steht, steht hier, was sich ändern würde.")));

  const rows = W.kalibrierung.preview || [];
  const kopf = el("div", {class: "abschnitt"},
    el("span", {class: "ueberschrift"}, "VORSCHAU"),
    el("div", {class: "hint"}, rows.length + " Stelle(n), Auszug"));
  const liste = el("div", {class: "abschnitt wachsend", style: "gap:4px"});
  for (const z of rows) {
    liste.appendChild(el("div", {class: "wz-vorschau"},
      el("div", {}, z.was),
      el("div", {class: "hint"},
        "(" + z.vorher.join(", ") + ") → (" + z.nachher.join(", ") + ")")));
  }
  if (!rows.length)
    liste.appendChild(el("div", {class: "hint"}, "Nichts, was sich ändern würde."));
  ziel.replaceChildren(kopf, liste);
}

/* Der Reiter bearbeitet `config.json` — eine ANDERE Datei als der Editor, also
 * liegt sein Zustand neben `S`: `C` ist die Antwort von `config_read()`,
 * `cfgGeaendert` sammelt, was noch nicht geschrieben ist.
 *
 * Gespeichert wird auf Knopfdruck: die Werte greifen in einen laufenden Lauf,
 * und eine halb getippte Zahl darf nicht schon gelten. */
let C = null;
let cfgGeaendert = {};
let cfgAbschnitt = 0;
let cfgSuche = "";
let cfgKorrekturen = [];

async function zeichneEinstellungen(frisch) {
  if (frisch || !C) {
    const antwort = await frage("config_read");
    // Zwischen Frage und Antwort kann umgeschaltet worden sein.
    if (!antwort || ansicht !== "einstellungen") return;
    C = antwort;
    // Was inzwischen von aussen genauso gesetzt wurde, ist keine Aenderung mehr.
    for (const k of Object.keys(cfgGeaendert))
      if (cfgGleich(cfgGeaendert[k], C.values[k])) delete cfgGeaendert[k];
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
    ? cfgGeaendert[key] : C.values[key];
}

function cfgSetzen(key, value) {
  if (cfgGleich(value, C.values[key])) delete cfgGeaendert[key];
  else cfgGeaendert[key] = value;
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
  return (key + " " + (m.label || "") + " " + (m.help || ""))
    .toLowerCase().includes(cfgSuche);
}

/** Ein Wert als Text — für „Standard: …" und die Änderungskarten. */
function cfgText(value, m) {
  m = m || {};
  if (value === null || value === undefined || value === "")
    return m.empty || (value === "" ? "(leer)" : "keiner");
  if (value === true) return "an";
  if (value === false) return m.kind === "xy" ? "aus" : "aus";
  if (Array.isArray(value)) return "(" + value.join(", ") + ")";
  if (m.options) {
    const t = m.options.find((o) => cfgGleich(o.value, value));
    if (t) return t.text;
  }
  if (value === 0 && m.empty) return "0 — " + m.empty;
  return String(value) + (m.unit ? " " + m.unit : "");
}

function zeichneCfgListe() {
  const ziel = $("cfg-liste");
  ziel.replaceChildren();
  C.sections.forEach((a, i) => {
    const offen = a.keys.filter((k) => k in cfgGeaendert).length;
    const treffer = cfgSuche ? a.keys.filter(cfgTrifft).length : 0;
    ziel.appendChild(el("button", {
      class: "cfg-nav" + (!cfgSuche && i === cfgAbschnitt ? " an" : ""),
      onclick: () => { cfgSuche = ""; $("cfg-suche").value = ""; cfgAbschnitt = i;
                       zeichneEinstellungen(); },
    },
      el("span", {class: "wachse"}, a.title),
      cfgSuche ? el("span", {class: "klein mono"}, treffer ? treffer + "×" : "") : null,
      offen ? el("span", {class: "zahl"}, offen) : null));
  });
}

function zeichneCfgFelder() {
  const ziel = $("cfg-felder");
  ziel.replaceChildren();
  if (C.fehler) {
    ziel.appendChild(el("p", {class: "empty", style: "color:var(--err)"}, C.fehler));
    return;
  }
  // Bei einer Suche werden ALLE Abschnitte mit Treffern gezeigt, nicht nur der
  // gewaehlte: wer sucht, weiss ja gerade nicht, wo der Wert steht.
  const gruppen = cfgSuche
    ? C.sections.filter((a) => a.keys.some(cfgTrifft))
    : [C.sections[cfgAbschnitt]].filter(Boolean);
  if (!gruppen.length) {
    ziel.appendChild(el("p", {class: "empty"}, "Kein Feld passt zu „" + cfgSuche + "“."));
    return;
  }
  for (const a of gruppen) {
    ziel.appendChild(el("div", {class: "cfg-gruppe"}, a.title));
    for (const key of a.keys) if (cfgTrifft(key)) ziel.appendChild(cfgZeile(key));
  }
}

function cfgZeile(key) {
  const m = C.meta[key] || {label: key, kind: "text"};
  const active = cfgAktiv(key);
  const left = el("div", {},
    el("div", {class: "cfg-name"}, m.label),
    el("div", {class: "cfg-key"}, key),
    m.help ? el("p", {class: "hinweis", style: "margin-top:5px"}, m.help) : null,
    active ? null : el("p", {class: "hinweis", style: "margin-top:5px;color:var(--accent)"},
                      cfgWarum(m)));
  const rechts = el("div", {class: "cfg-rechte"},
    cfgBedienelement(key, m), cfgLeer(key, m), cfgStandard(key, m),
    cfgAktion(key, m));
  return el("div", {class: "cfg-zeile" + (key in cfgGeaendert ? " geaendert" : "") +
                           (active ? "" : " blass")}, left, rechts);
}

/** Der Knopf UNTER einem Feld, wenn die Meta-Tabelle einen anmeldet.
 *
 * **Es gibt genau einen, und der Grund steht in `config_meta.py`:** den
 * Katalog konnte bis hierhin nur `python tools/katalog.py` anlegen — also
 * ausgerechnet die Datei, ohne die das LLM frei raet und die Kategorie leer
 * bleibt, liess sich im Fenster nicht beschaffen. Generisch statt als
 * Sonderfall, damit der naechste Fall keinen zweiten Bedienweg erfindet.
 */
function cfgAktion(key, m) {
  const stamp = (C.states || {})[key];
  if (!m.action && !stamp) return null;
  return el("div", {class: "spalte", style: "gap:4px;margin-top:6px"},
    m.action ? el("button", {class: "btn still breit",
      onclick: () => cfgAktionRufen(key, m)}, m.action.text) : null,
    // **Der Pfad sagt nicht, ob die Datei da ist und wie alt sie ist.** Bei
    // einer Liste, die man holt, ist genau das die Frage — und ohne Antwort
    // holt man sie entweder nie wieder oder jedes Mal.
    stamp ? el("p", {class: "hinweis", style: "margin:0"}, stamp) : null);
}

async function cfgAktionRufen(key, m) {
  // Ein Netzabruf dauert, und der Reiter zeichnet sich danach neu: ohne den
  // Kasten saehe das Fenster in der Zwischenzeit tot aus.
  const antwort = await mitArbeit("frage", m.action.befehl, null,
    m.action.text, "Das kann ein paar Sekunden dauern.");
  if (!antwort) return;
  // Geklappt, aber mit Vorbehalt (ein Konstrukt in der Antwort, das das
  // Werkzeug nicht kannte): dann sagt die Bruecke die Art selbst.
  setzeStatus({text: antwort.message || "Fertig.",
               kind: antwort.kind || (antwort.ok ? "ok" : "err")});
  // Der Wert im Feld kann sich dabei geaendert haben (der Pfad wird
  // eingetragen) — frisch lesen statt den alten Stand stehen zu lassen.
  if (antwort.ok) zeichneEinstellungen(true);
}

function cfgBedienelement(key, m) {
  const value = cfgWert(key);
  const setze = (v) => cfgSetzen(key, v);
  if (m.kind === "bool") return schalter(value ? "an" : "aus", value, setze);
  if (m.kind === "enum") return cfgKacheln(key, m, value);
  if (m.kind === "xy") return cfgStelle(key, m, value);
  if (m.kind === "area") {
    const feld = el("textarea", {});
    feld.value = value === null || value === undefined ? "" : String(value);
    feld.addEventListener("change", () => setze(feld.value.trim() || null));
    return feld;
  }
  if (m.kind === "text") {
    const feld = el("input", {autocomplete: "off",
                              value: value === null || value === undefined ? "" : String(value)});
    feld.addEventListener("change", () => {
      const roh = feld.value.trim();
      setze(roh === "" && (C.optional || []).includes(key) ? null : roh);
    });
    feld.addEventListener("keydown", (e) => { if (e.key === "Enter") feld.blur(); });
    return feld;
  }
  return cfgZahl(key, m, value);
}

function cfgZahl(key, m, value) {
  const optional = (C.optional || []).includes(key);
  const feld = el("input", {type: "number", step: m.kind === "int" ? "1" : "any",
                            value: value === null || value === undefined ? "" : value});
  if (m.kind === "ratio") { feld.setAttribute("min", "0"); feld.setAttribute("max", "1"); }
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
    if (m.kind === "int") z = Math.round(z);
    if (m.kind === "ratio") z = Math.max(0, Math.min(1, z));
    cfgSetzen(key, z);
  });
  feld.addEventListener("keydown", (e) => { if (e.key === "Enter") feld.blur(); });
  // Ein Prozentwert liest sich als Prozent, nicht als 0.8 — die Datei traegt
  // trotzdem die Zahl, mit der der Vergleich rechnet.
  const zusatz = m.kind === "ratio" ? "= " + Math.round((Number(value) || 0) * 100) + " %"
                                   : (m.unit || "");
  if (!zusatz) return feld;
  return el("div", {class: "cfg-einheit"}, feld, el("span", {class: "unit"}, zusatz));
}

/** Feste kurze Auswahl als Kacheln — dieselbe Regel wie beim Block-Typ. */
function cfgKacheln(key, m, value) {
  return el("div", {class: "cfg-chips"}, (m.options || []).map((o) =>
    el("button", {class: "typ-chip" + (cfgGleich(o.value, value) ? " an" : ""),
                  onclick: () => cfgSetzen(key, o.value)}, o.text)));
}

/** `scan_park_mouse`: aus (`false`) oder eine Stelle (`[x, y]`). */
function cfgStelle(key, m, value) {
  const an = Array.isArray(value);
  const xy = an ? value : [0, 0];
  const setzeXY = (i, v) => {
    const neu = [Number(xy[0]) || 0, Number(xy[1]) || 0];
    neu[i] = Math.round(Number(v) || 0);
    cfgSetzen(key, neu);
  };
  const number = (i) => {
    const f = el("input", {type: "number", step: "1", value: xy[i], disabled: !an});
    f.addEventListener("change", () => setzeXY(i, f.value));
    return f;
  };
  return el("div", {class: "spalte", style: "gap:6px"},
    schalter(an ? "parken" : "aus", an, (v) => cfgSetzen(key, v ? [xy[0], xy[1]] : false)),
    an ? el("div", {class: "gitter2"}, number(0), number(1)) : null,
    // Eine Stelle faehrt man an, statt sie zu tippen — derselbe Weg wie beim
    // Klick-Block. Messen kann das nur ein Prozess auf demselben Rechner, und
    // das ist dieser hier.
    an ? el("button", {class: "btn still", onclick: () => cfgStelleAufnehmen(key)},
            "✛ mit der Maus setzen") : null,
    an ? el("p", {class: "hinweis"}, "Maus im Spiel an die Stelle, dann ENTER.") : null);
}

async function cfgStelleAufnehmen(key) {
  setzeStatus({text: "Maus an die Stelle bewegen und ENTER drücken (ESC bricht ab).",
               kind: "warn"});
  const antwort = await mitWarten("frage", "mouse_position");
  if (!antwort) return;
  if (!antwort.ok) return setzeStatus({text: antwort.message || "Abgebrochen.", kind: "warn"});
  cfgSetzen(key, [antwort.x, antwort.y]);
  setzeStatus({text: "Parkposition: (" + antwort.x + ", " + antwort.y + ")", kind: "ok"});
}

/** Was ein leeres Feld bzw. eine 0 hier bedeutet — nur dann, wenn es so steht.
 *
 * Ohne diese Zeile liest sich eine 0 wie „aus", und bei `click_max_total` heisst
 * sie das Gegenteil. Sie steht deshalb am Wert und nicht in der Erklaerung: dort
 * las man sie erst, wenn man schon zweifelte. */
function cfgLeer(key, m) {
  const value = cfgWert(key);
  const empty = value === null || value === undefined || value === "" || value === 0;
  if (!m.empty || !empty) return null;
  return el("span", {class: "cfg-standard"}, "= " + m.empty);
}

/** Wie lang der Standardwert IM KNOPF stehen darf, bevor er in den Tooltip
 *  wandert. Eine Zahl, „an", ein Enum-Text passen; ein Satz nicht. */
const STD_MAX = 24;

function cfgStandard(key, m) {
  const std = C.standard[key];
  if (cfgGleich(cfgWert(key), std))
    return el("span", {class: "cfg-standard"}, "Standard");
  // **Ein Knopf sagt, was er TUT** — dieselbe Regel wie beim Rückgängig im
  // Scans-Reiter. `cfgText()` gibt bei einem leeren Standardwert den
  // `empty`-Satz zurück ("Kategorie und Namen bleiben Handarbeit"), und der
  // stand hier als Beschriftung: der Knopf war breiter als seine Spalte und
  // lief rechts aus dem Fenster. Der Satz steht ohnehin schon eine Zeile
  // höher an `cfgLeer()` — hier gehört hin, worauf zurückgesetzt wird.
  const roh = (std === null || std === undefined || std === "")
    ? "(leer)" : cfgText(std, m);
  const kurz = roh.length > STD_MAX;
  return el("button", {class: "btn still cfg-standard",
                       title: "auf den Standardwert zurücksetzen"
                              + (kurz ? ": " + roh : ""),
                       onclick: () => cfgSetzen(key, std)},
            "↺ Standard" + (kurz ? "" : ": " + roh));
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
                      onclick: () => cfgSetzen(key, C.values[key])}, "zurück")),
      el("div", {class: "cfg-key"}, key),
      el("div", {class: "reihe klein"},
        el("span", {class: "cfg-alt"}, cfgText(C.values[key], m)), "→",
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
        el("span", {class: "cfg-alt"}, cfgText(k.sent, m)), "→",
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
  const values = Object.assign({}, cfgGeaendert);
  const count = Object.keys(values).length;
  if (!count) return;
  const antwort = await frage("config_write", {values: values});
  if (!antwort) return;
  if (!antwort.ok)
    return setzeStatus({text: antwort.message || "Nicht gespeichert.", kind: "err"});
  C.values = antwort.values;
  cfgGeaendert = {};
  cfgKorrekturen = antwort.korrekturen || [];
  setzeStatus({
    text: count + (count === 1 ? " Einstellung" : " Einstellungen") + " gespeichert." +
          (cfgKorrekturen.length ? "  " + cfgKorrekturen.length + " davon korrigiert." : ""),
    kind: cfgKorrekturen.length ? "warn" : "ok"});
  zeichneEinstellungen();
}

/** Die Sequenz wechseln — erst offene Scan-Änderungen wegschreiben.
 *
 * Die Rückfrage nach ungespeicherten Änderungen kennt nur die SEQUENZ
 * (`_dirty`); die Scans haben ihren eigenen Merker (`_scan_dirty`), und
 * `load` wirft sie über `_scan_init()` wortlos weg. Erreichbar war das kaum,
 * solange die Auswahl nur im Editor stand — jetzt steht sie im Scans-Reiter
 * selbst, also direkt neben der Arbeit, die verlorenginge.
 *
 * Gefragt wird trotzdem nicht: der Reiter speichert ohnehin von selbst (900 ms
 * nach der letzten Änderung), ein Verwerfen-Modell gibt es dort gar nicht. Das
 * hier ist derselbe Griff, nur sofort statt nach der Wartezeit. Scheitert er —
 * etwa weil die Sequenzdatei ausserhalb geändert wurde —, bleibt es beim
 * bisherigen Stand, statt die Arbeit im Vorbeigehen mitzunehmen.
 */
async function sequenzWechseln(befehl, daten) {
  if (SC && SC.dirty) {
    const antwort = await frage("scan_save");
    if (antwort) {
      SC = antwort;
      if (SC.dirty) {                       // nicht geschrieben — Grund steht drin
        await zeichneScans();
        return;
      }
    }
  }
  return ruf(befehl, daten);
}

/* --------------------------------------------------------------- Verdrahtung */

function verdrahte() {
  for (const t of document.querySelectorAll(".tab"))
    t.addEventListener("click", () => setzeAnsicht(t.dataset.ansicht));

  $("btn-load").addEventListener("click",
    () => sequenzWechseln("load", {name: $("seq-auswahl").value}));
  $("seq-auswahl").addEventListener("dblclick",
    () => sequenzWechseln("load", {name: $("seq-auswahl").value}));
  $("btn-neu").addEventListener("click", () => sequenzWechseln("neu"));
  $("btn-save").addEventListener("click", speichere);
  $("btn-aufnahme").addEventListener("click", () => wzOeffnen("aufnahme"));
  // Ein Knopf, zwei Bedeutungen — er trägt die aktuelle als Beschriftung, damit
  // niemand raten muss, was ein Druck jetzt tut.
  $("btn-lauf").addEventListener("click", () => laufSchicken(laufLief ? "stop" : "start"));
  $("btn-block-weg").addEventListener("click", () => ruf("selection_delete"));
  $("btn-block-kopie").addEventListener("click", () => ruf("selection_duplicate"));

  $("seq-name").addEventListener("change", (e) =>
    ruf("sequence_set", {feld: "name", value: e.target.value}));
  $("seq-zyklen").addEventListener("change", (e) =>
    ruf("sequence_set", {feld: "cycles", value: Number(e.target.value) || 0}));
  $("seq-info").addEventListener("change", (e) =>
    ruf("sequence_set", {feld: "beschreibung", value: e.target.value}));
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
    knopf.addEventListener("click", () => rufScan("region_mode",
      {kind: scanArt, modus: knopf.dataset.erkTool}));

  $("scan-offen").addEventListener("change", (e) => {
    scanAssistentSchritt = null;
    rufScan("scan_open", {name: e.target.value});
  });
  $("scan-name").addEventListener("change", (e) => {
    if (!SC || !SC.offen) return;
    rufScan("scan_set", {name: SC.offen, feld: "name", value: e.target.value});
  });
  $("scan-name").addEventListener("keydown", (e) => {
    if (e.key === "Enter") e.target.blur();
  });
  $("scan-neu").addEventListener("click", () => {
    scanAssistentSchritt = 1;
    rufScan("scan_new");
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
    rufScan("scan_mode_set", {modus: "finden", kind: scanArt}));
  $("scan-slot-neu").addEventListener("click", () =>
    rufScan("scan_mode_set", {modus: "slot", kind: scanArt}));
  $("scan-test").addEventListener("click", () => rufScan("scan_recognize"));
  $("scan-lernen").addEventListener("click", () =>
    rufScan("scan_learn_preview", {scope: "alle"}));
  document.querySelectorAll("[data-scan-tool]").forEach((knopf) =>
    knopf.addEventListener("click", () =>
      rufScan("scan_mode_set", {modus: knopf.dataset.scanTool, kind: scanArt})));
  $("scan-pin").addEventListener("click", () =>
    rufScan("scan_mode_set", {modus: SC.modus, kind: scanArt,
                                   fixiert: !SC.werkzeug_fixiert}));
  $("scan-foto").addEventListener("click", () => rufScan("scan_screenshot", {kind: scanArt}));
  $("scan-vollbild").addEventListener("click", () =>
    rufScan("scan_area_set", {kind: scanArt}));
  $("scan-aufziehen").addEventListener("click",
    () => rufScan("scan_mode_set", {modus: "area", kind: scanArt}));
  $("scan-fenster-neu").addEventListener("click", scanFensterPflegen);
  $("scan-fenster").addEventListener("change", (e) => {
    const wahl = scanFenster[Number(e.target.value)];
    // Waehlen nimmt NICHT auf — das tut der Knopf darueber. Vorher stand hier
    // beides in einem Griff, und dann sah es aus, als handele die Liste von
    // selbst und der Knopf gar nicht (er holte dasselbe Bild noch einmal).
    if (wahl) rufScan("scan_area_set",
      {kind: scanArt, area: wahl.area, window: wahl.id});
    else rufScan("scan_area_set", {kind: scanArt});
  });
  $("scan-fit").addEventListener("click", scanEinpassen);
  $("scan-1zu1").addEventListener("click", () => {
    // 1:1 heisst: ein Bildschirm-Pixel ist ein Bildschirm-Pixel. Das Bild ist
    // fuer die Uebertragung verkleinert, also muss der Zoom das ausgleichen.
    scanZoom = SC && SC.photo ? 1 / SC.photo.scale : 1;
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
  const buehne = $("scan-buehne");
  flaeche.addEventListener("click", (e) => {
    // Ein Klick, der ein Ziehen beendet hat, ist kein Klick. Ohne das waehlte
    // das Loslassen den Slot gleich noch einmal neu aus.
    if (scanZiehGemacht) { scanZiehGemacht = false; return; }
    const position = scanStelleAusEvent(e);
    if (!position) return;
    // ALT misst den Hintergrund des Slots unter dem Zeiger — ohne den Umweg
    // ueber die Modus-Kachel. Der haeufigste Handgriff nach dem Finden.
    if (e.altKey) return rufScan("scan_direct", {x: position[0], y: position[1],
                                                 was: "messen", kind: scanArt});
    // STRG nimmt einen einzelnen Slot zur Auswahl dazu oder heraus — dieselbe
    // Geste wie im Sequenz-Editor.
    rufScan("scan_click", {x: position[0], y: position[1], kind: scanArt,
                           zusatz: e.ctrlKey || e.metaKey});
  });
  // Beim automatischen Finden darf eine Ecke auch im freien Teil der MITTLEREN
  // Buehne liegen. Der Helfer klemmt sie an den Bildrand; die Seitenleisten
  // liegen ausserhalb dieses Elements und koennen die Geste nie ausloesen.
  buehne.addEventListener("click", (e) => {
    const position = scanSuchStelleAusBuehne(e);
    if (position) rufScan("scan_click", {x: position[0], y: position[1], kind: scanArt});
  });
  flaeche.addEventListener("dblclick", (e) => {
    const position = scanStelleAusEvent(e);
    if (position) rufScan("scan_direct",
      {x: position[0], y: position[1], was: "klick", kind: scanArt});
  });

  // **Einen gewaehlten Slot zieht man, statt vier Zahlen zu tippen.** Gepackt
  // wird nur, was schon gewaehlt IST — damit braucht die Seite keine eigene
  // Trefferregel (die liegt in `_slot_under()` in Python und soll dort bleiben),
  // und die Geste liest sich wie ueberall sonst: erst auswaehlen, dann ziehen.
  flaeche.addEventListener("mousedown", (e) => {
    if (e.button !== 0 || !SC || SC.modus !== "wahl" || SC.ecke) return;
    const position = scanStelleAusEvent(e);
    if (!position || !scanGewaehlteSlots().some((s) => scanInSlot(s, position))) return;
    scanZiehStart = position;
    scanZiehVersatz = [0, 0];
  });
  flaeche.addEventListener("mousemove", (e) => {
    if (scanZiehStart) {
      const position = scanStelleAusEvent(e);
      if (!position) return;
      const dx = position[0] - scanZiehStart[0], dy = position[1] - scanZiehStart[1];
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
  buehne.addEventListener("mousemove", (e) => {
    if (!SC || !SC.ecke || SC.modus !== "finden") return;
    const position = scanSuchStelleAusBuehne(e);
    if (!position) return;
    scanZeiger = position;
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
    rufScan("scan_move", {dx: dx, dy: dy});
  });
  // Mit STRG zoomen, wie in jedem Bildbetrachter; ohne STRG scrollt die Buehne.
  $("scan-buehne").addEventListener("wheel", (e) => {
    if (!e.ctrlKey || !SC || !SC.photo) return;
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
    if (ansicht !== "scans" || !SC || !SC.photo || scanZoomHand) return;
    // Gebuendelt: waehrend des Ziehens am Fensterrand feuert das im Dutzend,
    // und jeder Aufruf baut das Overlay neu.
    clearTimeout(scanRahmen);
    scanRahmen = setTimeout(scanEinpassen, 120);
  });

  $("dialog-ab").addEventListener("click", schliesseFrage);
  $("dialog-weg").addEventListener("click", () => fortfahren(true));
  $("dialog-save").addEventListener("click", () => fortfahren(false));

  // Ziehen über dem Board darf nicht als "Datei öffnen" enden.
  document.addEventListener("dragover", (e) => { if (drag) e.preventDefault(); });
  document.addEventListener("drop", (e) => e.preventDefault());
  document.addEventListener("keydown", tastatur);
}

async function speichere() {
  // Ein Feld, in dem gerade getippt wird, meldet seinen Wert erst beim Verlassen.
  // Ohne das Blur ginge die letzte Eingabe beim Speichern verloren.
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  await ruf("save");
  // Nur hier nachziehen, nicht in `zeichne()`: die Liste liest jede Sequenzdatei
  // einmal, und `zeichne()` läuft nach JEDEM Befehl. Ändern kann sich die Liste
  // ohnehin nur durch ein Speichern (Umbenennen legt eine neue Datei an).
  if (ansicht === "sequences") zeichneSequenzenliste();
}

function imTextfeld() {
  const a = document.activeElement;
  return a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.tagName === "SELECT");
}

function tastatur(e) {
  if (e.key === "Escape") {
    if (offeneFrage) return schliesseFrage();
    if (imTextfeld()) return document.activeElement.blur();
    if (ansicht === "scans") return rufScan("scan_cancel");
    if (ansicht === "einstellungen") return;
    if (gewaehltePhase !== null) {
      gewaehltePhase = null;
      return zeichnePhasen();
    }
    return ruf("selection_clear");
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    // Derselbe Griff, drei Dateien: welche gemeint ist, sagt der offene Reiter.
    if (ansicht === "einstellungen") return cfgSpeichern();
    if (ansicht === "scans") return rufScan("scan_save");
    return speichere();
  }
  if (imTextfeld() || offeneFrage) return;
  if (ansicht === "scans") {
    // STRG+Z steht NACH der Textfeld-Abfrage: in einem Eingabefeld gehoert das
    // Rueckgaengig dem Feld, nicht dem Reiter.
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      return rufScan("scan_undo");
    }
    // **Pfeiltasten schieben die Auswahl.** Ein Slot, der drei Pixel daneben
    // liegt, war vorher nur ueber vier Zahlenfelder zu retten — und dreissig
    // gar nicht.
    const schub = {ArrowLeft: [-1, 0], ArrowRight: [1, 0],
                   ArrowUp: [0, -1], ArrowDown: [0, 1]}[e.key];
    if (schub && SC && (SC.selection.length || SC.wahl.kind === "slot")) {
      e.preventDefault();
      const weit = e.shiftKey ? 10 : 1;
      // Eine GEHALTENE Taste ist ein Verschieben, nicht dreissig: nur der erste
      // Schritt einer Serie kommt auf den Rueckgaengig-Stapel.
      const jetzt = Date.now();
      const serie = jetzt - scanSchubZeit < 900;
      scanSchubZeit = jetzt;
      return rufScan("scan_move",
                     {dx: schub[0] * weit, dy: schub[1] * weit, counts: !serie});
    }
    // **Ein Buchstabe ist erst ohne Modifikator ein Werkzeug.** Die Kacheln
    // liegen auf V/G/S/F/K/B, die Erkennungs-Werkzeuge auf R/K/T — und geprueft
    // wurde nur der Buchstabe. Damit schaltete STRG+F (Reflex „suchen") auf
    // „Hintergrundfarbe", STRG+B auf „Bereich" und STRG+R auf „Region": nichts
    // sichtbar passiert, aber der NAECHSTE Klick im Bild tut etwas anderes als
    // erwartet. Genau die Sorte Falle, die ein Modus haben darf und ein
    // Tastendruck nicht. STRG+S und STRG+Z sind vorher schon abgefangen.
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    // **Die Modus-Buchstaben gehoeren der Item-Art.** Ein „S" in der Boss-Ansicht
    // legte sonst einen Slot an — ein Werkzeug fuer etwas, das dort gar nicht
    // vorkommt, und der naechste Klick im Bild haette eine andere Wirkung als
    // die Leiste behauptet.
    if (scanArt === "item") {
      const modus = SCAN_MODI.find((m) => m.taste.toLowerCase() === e.key.toLowerCase());
      if (modus) { e.preventDefault(); return rufScan("scan_mode_set",
        {modus: modus.key, kind: scanArt}); }
      if (e.key === "Delete" && SC && SC.wahl.kind === "slot") {
        e.preventDefault();
        return rufScan("scan_slot_delete");
      }
      return;
    }
    // Dieselbe Idee eine Ebene weiter: R und K sind die beiden Werkzeuge der
    // Erkennungs-Scans, T testet. Testen liegt auf einer Taste, weil man beim
    // Einstellen einer Toleranz zehnmal hintereinander testet.
    const werkzeug = {r: "region", k: "action"}[e.key.toLowerCase()];
    if (werkzeug) {
      e.preventDefault();
      return rufScan("region_mode", {kind: scanArt, modus: werkzeug});
    }
    if (e.key.toLowerCase() === "t" && SC && erkScan()) {
      e.preventDefault();
      return erkTesten();
    }
    if (e.key === "Delete" && scanArt === "boss" && SC && SC.boss.wahl) {
      e.preventDefault();
      return rufScan("boss_delete");
    }
    return;
  }
  // Alles Weitere arbeitet auf der Block-Auswahl, die es hier nicht gibt.
  if (ansicht === "einstellungen") return;
  if (e.key === "Delete" && gewaehltePhase !== null) {
    e.preventDefault();
    const phase = gewaehltePhase;
    gewaehltePhase = null;
    return ruf("phase_delete", {phase: phase});
  }
  if (e.key === "Delete") { e.preventDefault(); return ruf("selection_delete"); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d") {
    e.preventDefault();          // sonst legt der Browser ein Lesezeichen an
    return ruf("selection_duplicate");
  }
  if (e.altKey && e.key === "ArrowUp") { e.preventDefault(); return ruf("selection_move", {delta: -1}); }
  if (e.altKey && e.key === "ArrowDown") { e.preventDefault(); return ruf("selection_move", {delta: 1}); }
}

warteAufBruecke().then(async () => {
  verdrahte();
  flankenPuls();
  await ruf("snapshot");
  // CTRL+ALT+V startet denselben Prozess wie CTRL+ALT+B, nur mit vorgewaehltem
  // Reiter. Erst NACH der ersten Momentaufnahme, weil sie den Wunsch mitbringt.
  if (S && S.start_view && S.start_view !== "editor") setzeAnsicht(S.start_view);
});
