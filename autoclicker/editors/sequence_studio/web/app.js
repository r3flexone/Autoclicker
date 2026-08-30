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
 * `schluessel` ist die Identitaet ueber Neuaufbauten hinweg; der Text taugt
 * dafuer nicht, weil Beschriftungen die Punkt-Nummer bzw. den Block-Typ tragen. */
function info(text, schluessel) {
  if (!text) return null;
  // Kein Schriftzeichen und kein CSS-Kreis: WebView2 kann beides auf zwei
  // verschiedenen Pixelrastern rendern, wodurch zwei versetzte Konturen
  // entstehen. Kreis, Punkt und Strich kommen gemeinsam aus EINEM SVG.
  const bild = svgEl("svg", {class: "info-glyphe", viewBox: "0 0 16 16",
    "aria-hidden": "true"});
  bild.append(
    svgEl("circle", {cx: "8", cy: "8", r: "6.5", fill: "none",
      stroke: "currentColor", "stroke-width": "1"}),
    svgEl("circle", {cx: "8", cy: "5", r: ".8", fill: "currentColor"}),
    svgEl("path", {d: "M8 7.5v4", fill: "none", stroke: "currentColor",
      "stroke-width": "1.3", "stroke-linecap": "round"}));
  const zeichen = el("span", {class: "info", "data-hilfe": schluessel || text}, bild);
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

function prioritaetsBelegung(kategorie) {
  const items = itemsDerKategorie(kategorie);
  const belegt = new Map();
  for (const i of items) {
    if (!belegt.has(i.prioritaet)) belegt.set(i.prioritaet, []);
    belegt.get(i.prioritaet).push(i.name);
  }
  const hoechste = items.length ? Math.max(...items.map((i) => i.prioritaet)) : 0;
  if (hoechste + 1 > PRIO_MAX_ZEIGEN) {
    const raenge = [...belegt.keys()].sort((a, b) => a - b);
    // Der naechste freie gehoert dazu — sonst nennt die Uebersicht keinen,
    // und genau den sucht man.
    let frei = 1;
    while (belegt.has(frei)) frei += 1;
    if (!raenge.includes(frei)) raenge.push(frei);
    raenge.sort((a, b) => a - b);
    return raenge.map((p) => ({prio: p, namen: belegt.get(p) || []}));
  }
  const alle = [];
  for (let p = 1; p <= hoechste + 1; p += 1) alle.push({prio: p, namen: belegt.get(p) || []});
  return alle;
}

/** Die Prioritaet, die dieses Item bekaeme, wenn niemand etwas einstellt:
 *  der erste freie Rang seiner Kategorie. */
function naechsteFreiePrioritaet(kategorie, ausser) {
  const vergeben = new Set(itemsDerKategorie(kategorie)
    .filter((i) => i.name !== ausser).map((i) => i.prioritaet));
  let p = 1;
  while (vergeben.has(p)) p += 1;
  return p;
}

/** Teilt sich dieses Item seinen Rang mit einem anderen seiner Kategorie? */
function prioritaetDoppelt(item) {
  if (!item.kategorie) return [];
  return itemsDerKategorie(item.kategorie)
    .filter((i) => i.name !== item.name && i.prioritaet === item.prioritaet)
    .map((i) => i.name);
}

/** Sichtbare Rangfolge statt einer Zahl ohne Zusammenhang. Prioritaeten gelten
 *  innerhalb einer Kategorie; deshalb waere eine globale Liste irrefuehrend. */
function prioritaetsUebersicht(kategorie, aktuellerName) {
  if (!kategorie) {
    return el("p", {class: "hinweis prioritaets-hinweis"},
      "Ohne Kategorie konkurriert dieses Item mit keinem anderen Item.");
  }
  const belegung = prioritaetsBelegung(kategorie);
  return el("div", {class: "prioritaets-uebersicht"},
    el("span", {class: "klein"}, "Rangfolge in „" + kategorie + "“"),
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
 * einundzwanzigsten Mal anders. */
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

/** Ein Schalter — mit ⓘ statt eines Erklaerungsabsatzes darunter.
 *
 * **Erklaerungen gehoeren ins ⓘ, nicht neben das Bedienelement.** Fuenf
 * Absaetze untereinander sind eine Textwand, in der das Bedienelement
 * untergeht; wer die Regel schon kennt, liest sie trotzdem jedes Mal mit. Das
 * ⓘ zeigt sie auf Wunsch, und `offeneHilfen` merkt sich, welche offen sind. */
function schalter(beschriftung, an, beim_setzen, hilfe, schluessel) {
  const box = el("input", {type: "checkbox"});
  box.checked = !!an;
  box.addEventListener("change", () => beim_setzen(box.checked));
  return el("label", {class: "an"}, box, beschriftet(beschriftung, hilfe, schluessel));
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
  let start = null, ende = null;
  try { start = a.selectionStart; ende = a.selectionEnd; } catch (e) { /* egal */ }
  const neu = umbenannt && umbenannt.von === kasten.id ? umbenannt.nach : kasten.id;
  // Beide ids: lehnt die Bruecke den neuen Namen ab (schon vergeben), heisst
  // die Maske danach weiter wie vorher — und der Fokus soll trotzdem stehen.
  return {id: neu, alt: kasten.id, i: i, start: start, ende: ende};
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
    if (name === "laden" || name === "neu") {
      gewaehltePhase = null;
      offeneSonderphasen.clear();
    }
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
  $("sicht-teilen").hidden = neu !== "teilen";
  $("sicht-werkzeuge").hidden = neu !== "werkzeuge";
  // Die Sequenz-Bedienelemente im Kopf gehoeren nur zur Sequenz. Die anderen
  // Reiter bearbeiten andere Dateien und haben ihren eigenen Knopf.
  for (const n of document.querySelectorAll("[data-sequenz]"))
    n.hidden = ["einstellungen", "scans", "teilen", "werkzeuge"].includes(neu);
  if (neu === "scans") zeichneScans(!SC);
  if (neu === "sequenzen") zeichneSequenzenliste();
  if (neu === "teilen") zeichneTeilen();
  // Frisch beim Oeffnen: der Bericht der letzten Sitzung beschriebe einen Stand,
  // den es nach einem Speichern nicht mehr gibt.
  if (neu === "werkzeuge") zeichneWerkzeuge(true);
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
  if (!S.phasen.some((p) => p.index === gewaehltePhase && p.art === "loop")) {
    gewaehltePhase = null;
  }
  const sichtbar = S.phasen.filter((phase) => phase.art === "loop" ||
    phase.bloecke.length || offeneSonderphasen.has(phase.art));
  for (const phase of sichtbar) ziel.appendChild(zeichnePhase(phase));

  const verborgen = S.phasen.filter((phase) => phase.art !== "loop" &&
    !phase.bloecke.length && !offeneSonderphasen.has(phase.art));
  const werkzeuge = el("div", {class: "phase phasen-anlegen"},
    el("button", {class: "leerzone", onclick: () => ruf("phase_anhaengen")}, "+ Phase"));
  for (const phase of verborgen) {
    const titel = phase.art === "init" ? "+ Startphase (einmal davor)"
                                       : "+ Abschlussphase (einmal danach)";
    werkzeuge.appendChild(el("button", {class: "leerzone", onclick: () => {
      offeneSonderphasen.add(phase.art);
      zeichnePhasen();
    }}, titel));
  }
  ziel.appendChild(werkzeuge);
}

function zeichnePhase(phase) {
  const phaseGewaehlt = phase.art === "loop" && phase.index === gewaehltePhase;
  const kopf = el("div", {
    class: "phase-kopf " + phase.art + (phaseGewaehlt ? " gewaehlt" : ""),
    title: phase.art === "loop" ? "Phase auswählen — Entf löscht sie" : "",
    onclick: (e) => {
      if (phase.art !== "loop" || e.target.closest("input, button")) return;
      gewaehltePhase = phase.index;
      ruf("auswahl_leeren");
    }});
  // INIT und END tragen keinen frei wählbaren Namen — sie bekommen deshalb auch
  // kein Eingabefeld, das nichts annimmt.
  const sondername = phase.art === "init" ? "START · einmal davor"
                   : phase.art === "end" ? "ABSCHLUSS · einmal danach" : phase.name;
  const name = phase.art === "loop"
    ? el("input", {class: "phase-name wachse", value: phase.name})
    : el("span", {class: "phase-name wachse"}, sondername);
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
      el("button", {class: "btn still", title: "Alle Wartezeiten dieser Phase skalieren",
        onclick: () => {
          const faktor = window.prompt("Wartezeiten mit welchem Faktor multiplizieren?", "1.0");
          if (faktor !== null) ruf("phase_skalieren", {phase: phase.index, faktor: faktor});
        }}, "Wartezeiten ×")));
  }
  if (phase.bloecke.length) {
    const alle = S.auswahl.phase === phase.index &&
                 S.auswahl.zeilen.length === phase.bloecke.length;
    kopf.appendChild(el("button", {class: "btn still phase-alle",
      onclick: () => ruf("phase_auswahl", {phase: phase.index})},
      alle ? "Auswahl aufheben" : "Alle Blöcke wählen"));
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

  const auswahl = el("input", {
    type: "checkbox", class: "karte-auswahl", checked: block.gewaehlt,
    title: block.gewaehlt ? "Aus Auswahl entfernen" : "Zur Auswahl hinzufügen",
    onclick: (e) => {
      e.stopPropagation();
      gewaehltePhase = null;
      ruf("waehlen", {phase: phase.index, zeile: block.zeile, modus: "dazu"});
    },
    onmousedown: (e) => e.stopPropagation(),
  });

  return el("div", {
    class: "karte" + (block.gewaehlt ? " gewaehlt" : ""),
    draggable: "true",
    onclick: (e) => {
      gewaehltePhase = null;
      return ruf("waehlen", {
        phase: phase.index, zeile: block.zeile,
        modus: e.ctrlKey || e.metaKey ? "dazu" : (e.shiftKey ? "bereich" : "einzeln")});
    },
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
      auswahl,
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
 * Der Balken setzt seine Segmente per Inline-Stil (die Breite ist gerechnet).
 * Die Farbe trotzdem aus `:root` zu holen haelt die Palette an einer Stelle;
 * gemerkt, weil `getComputedStyle` sonst je Sequenzkarte dreimal liefe. */
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
 * Leere Phasen fallen raus: ein Segment der Breite 0 sagt nichts, kostet aber
 * eine Luecke. Die Phasenfarben sind dieselben wie ueberall sonst. */
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
      "Sie bleibt unangetastet; nachsehen lohnt sich in " + s.datei + "."));
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
    el("span", {class: "zahl"}, s.phasen.length + " Loop-Phasen"),
    el("span", {class: "zahl"}, s.zyklen ? s.zyklen + " Zyklen" : "endlos")]));

  karte.appendChild(el("div", {class: "seq-fuss"},
    el("span", {class: "klein mono wachse", title: s.datei},
       s.datei + " · " + zeitpunkt(s.geaendert)),
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
 * Nur auf der Flanke (nichts → laeuft), nicht solange etwas laeuft: sonst kaeme
 * man waehrend eines Durchgangs nicht mehr in den Editor zurueck. */
function laufFlanke(aktiv) {
  if (aktiv && !laufLief && ansicht !== "lauf") setzeAnsicht("lauf");
  laufLief = aktiv;
  const knopf = $("btn-lauf");
  knopf.textContent = aktiv ? "■ Stoppen" : "▶ Starten";
  knopf.classList.toggle("gefahr", aktiv);
}

/** Einen Lauf-Befehl abschicken, nachfassen — und melden, wenn niemand zuhört. */
async function laufSchicken(befehl, extra) {
  await ruf("lauf_befehl", Object.assign({befehl: befehl}, extra || {}));
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
 * „seit 12 s" allein beantwortet die Frage nicht: bei 15 s Wartezeit ist das
 * fast geschafft, bei 300 s Timeout gerade erst angefangen.
 *
 * Heruntergezaehlt wird hier, aus den absoluten Zeitstempeln der Statusdatei —
 * mit Restwerten aus dem Worker ruckelte die Anzeige in dessen Sekundentakt. */
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
 * Die Liste kommt aus dem Laufstatus, nicht aus der geoeffneten Sequenz: laufen
 * kann eine ganz andere. Fehlt sie, bleibt es bei der einen laufenden Phase.
 *
 * „Abgeschlossen" gilt innerhalb des laufenden Zyklus — im naechsten Durchgang
 * sind dieselben Loop-Phasen wieder ausstehend. */
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
    if (z && z.countdown) {
      const jetzt = Date.now() / 1000;
      ziel.appendChild(el("div", {class: "lauf-kopf"},
        el("span", {class: "lampe an"}),
        el("span", {class: "lauf-name"}, z.sequenz || "(ohne Namen)"),
        el("span", {class: "zahl"}, "startet in " +
          restzeit((z.zielzeit || jetzt) - jetzt))));
      ziel.appendChild(el("p", {class: "hinweis"},
        "Geplant für " + new Date((z.zielzeit || jetzt) * 1000).toLocaleString("de-CH") +
        ". Der Countdown kann hier oder mit dem Stop-Hotkey abgebrochen werden."));
      ziel.appendChild(steuerung(false, z));
      return;
    }
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
    ziel.appendChild(steuerung(false, z));
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

  if (z.manuell) ziel.appendChild(manuelleSteuerung(z.manuell));
  ziel.appendChild(steuerung(true, z));
}

/** Der letzte Lauf, nachdem er fertig ist.
 *
 * Der Stand bleibt stehen, bis der naechste Start ihn ueberschreibt — sonst
 * waere die Ansicht genau dann leer, wenn man hinsieht. Dieselben Kacheln wie
 * im Lauf, nur mit festen statt mitlaufenden Zeitangaben. */
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

  ziel.appendChild(steuerung(false, z));
}

/** Der Worker wartet wirklich auf diese vier Antworten; keine Konsolentaste. */
function manuelleSteuerung(m) {
  const knopf = (text, aktion, klasse) => el("button", {
    class: "btn" + (klasse ? " " + klasse : ""),
    onclick: () => laufSchicken("manuell_aktion", {aktion: aktion}),
  }, text);
  return el("section", {class: "tafel manuell-tafel"},
    el("span", {class: "ueberschrift"}, "MANUELLER SCHRITTMODUS"),
    el("b", {}, m.titel || "Aktueller Block"),
    el("p", {class: "hinweis"}, m.aktion || ""),
    el("div", {class: "reihe", style: "gap:8px;flex-wrap:wrap"},
      knopf("▶ Ausführen", "run", "haupt"),
      knopf("↷ Überspringen", "skip"),
      knopf("Normal weiter", "continue"),
      knopf("■ Stoppen", "stop", "gefahr")));
}

/** Start/Pause/Stopp.
 *
 * Die Knöpfe führen nichts aus — dieses Fenster hat keinen Zugriff auf
 * `state.stop_event`. Sie legen einen Befehl ab, den der Hauptprozess in
 * derselben Schleife abholt wie seine Hotkeys (`befehl.py`). Deshalb steht das
 * Hotkey-Kürzel weiterhin daneben: es ist derselbe Weg, nur ohne Fensterwechsel.
 */
function steuerung(laeuft, stand) {
  const knopf = (text, befehl, klasse) => el("button", {
    class: "btn" + (klasse ? " " + klasse : ""),
    onclick: () => laufSchicken(befehl),
  }, text);
  const zeile = el("div", {class: "reihe", style: "gap:8px;flex-wrap:wrap"},
    !laeuft && !(stand && stand.countdown) ? knopf("▶ Starten", "start", "haupt") : null,
    !laeuft && !(stand && stand.countdown) ? knopf("▶ Schrittweise", "start_manuell") : null,
    laeuft ? knopf("⏸ Pause", "pause") : null,
    laeuft ? knopf("↷ Warten überspringen", "skip") : null,
    laeuft ? knopf("⏭ Block überspringen", "skip_step") : null,
    laeuft ? knopf("✓ Zyklus abschliessen", "finish") : null,
    laeuft ? knopf("■ Stoppen", "stop", "gefahr") : null,
    !laeuft && stand && stand.countdown ? knopf("■ Zeitplan abbrechen", "stop", "gefahr") : null,
    el("span", {class: "klein"},
       laeuft ? "oder CTRL+ALT+S / CTRL+ALT+G im Hauptprozess"
               : "startet die gespeicherte Fassung — ungespeicherte Änderungen " +
                 "werden vorher geschrieben"));
  if (!laeuft && !(stand && stand.countdown)) {
    const zeit = el("input", {placeholder: "14:30 oder +30m", autocomplete: "off",
      style: "width:150px"});
    const plan = el("button", {class: "btn", onclick: () => {
      if (!zeit.value.trim()) {
        setzeStatus({art: "warn", text: "Bitte eine Startzeit eingeben."});
        return;
      }
      laufSchicken("zeitplan", {zeit: zeit.value.trim()});
    }}, "◷ Start planen");
    zeile.append(el("span", {class: "trenner"}), zeit, plan);
  }
  return zeile;
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
    ziel.appendChild(el("div", {class: gewaehlt > 1 ? "sammel-editor" : "leer"}, gewaehlt > 1
      ? zeichneSammelEditor(gewaehlt)
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
  if (b.trigger !== "kein" && b.trigger_punkt !== null && b.trigger_punkt !== undefined)
    stellen.push(["trigger", "Prüf-Pixel", b.trigger_punkt]);
  if (b.verify !== "kein" && b.verify_punkt !== null && b.verify_punkt !== undefined)
    stellen.push(["verify", "Nachprüf-Pixel", b.verify_punkt]);
  if (b.else_aktion === "click" && b.else_punkt !== null && b.else_punkt !== undefined)
    stellen.push(["else", "ELSE-Klick", b.else_punkt]);
  const fuss = el("div", {class: "insp-fuss"});
  fuss.appendChild(el("button", {
    class: "btn breit",
    title: "Führt diesen Block sofort aus — Wartezeit und Farb-Trigger werden übersprungen",
    onclick: () => ruf("block_testen"),
  }, "▶ Block einmal testen"));
  for (const [welche, text, punkt] of stellen) {
    fuss.appendChild(el("button", {
      class: "btn breit",
      onclick: () => ruf("punkt_zeigen", {welche: welche}),
    }, "◎ " + text + " zeigen (#" + punkt + ")"));
  }
  ziel.appendChild(fuss);
}

function zeichneSammelEditor(anzahl) {
  const zeitfeld = (beschriftung, feldname, wert, gemischt) => {
    const eingabe = el("input", {
      type: "number", min: "0", step: "0.1",
      value: gemischt ? "" : (wert === null || wert === undefined ? 0 : wert),
      placeholder: gemischt ? "verschieden" : "",
    });
    eingabe.addEventListener("change", () => {
      if (eingabe.value.trim() !== "") {
        ruf("auswahl_setzen", {feld: feldname, wert: Number(eingabe.value)});
      }
    });
    eingabe.addEventListener("keydown", (e) => { if (e.key === "Enter") eingabe.blur(); });
    return el("label", {class: "feld"}, beschriftung, eingabe);
  };
  return el("div", {},
    el("p", {class: "hinweis"},
      anzahl + " Blöcke gemeinsam bearbeiten. Verschieben: ALT+↑/↓, löschen: Entf."),
    el("span", {class: "ueberschrift"}, "WARTEZEIT FÜR AUSWAHL"),
    el("div", {class: "reihe sammel-schnell"}, [0, 0.5, 1].map((sekunden) =>
      el("button", {class: "btn still", onclick: () => ruf("auswahl_setzen",
        {feld: "delay_before", wert: sekunden})}, String(sekunden).replace(".", ",") + " s"))),
    el("div", {class: "gitter2"},
      zeitfeld("Wartezeit (s)", "delay_before", S.auswahl.delay_before,
               S.auswahl.delay_before_gemischt),
      zeitfeld("bis (0 = fest)", "delay_max", S.auswahl.delay_max,
               S.auswahl.delay_max_gemischt)),
    el("p", {class: "hinweis"},
      "Nur diese Wartefelder werden gemeinsam geändert; Typ, Ziel und Bedingungen bleiben erhalten."));
}

function baueAktion(ziel, b) {
  const klickt = b.typ === "click" || b.typ === "wait_click";
  const farbe = b.trigger !== "kein";

  // Der Schluessel bleibt "aktion" und haengt bewusst NICHT am Block-Typ: der
  // wechselt hier ja gerade, und eine Erklaerung, die man aufklappt und die beim
  // ersten Schalten verschwindet, ist keine.
  ziel.appendChild(ueberschrift("AKTION",
    "Diese beiden Schalter SIND der Block-Typ: klicken und/oder auf eine Farbe " +
    "warten. Die Kacheln oben zeigen das Ergebnis automatisch an.", "aktion"));
  ziel.appendChild(schalter("klickt an der Stelle", klickt, (an) =>
    ruf("block_typ", {typ: an ? (farbe ? "wait_click" : "click") : "wait"})));
  ziel.appendChild(schalter("wartet auf eine Farbe", farbe, (an) => {
    // Bei einem Warte-Block aendert die Farbe den Typ nicht — WARTEN heisst mit
    // und ohne Trigger WARTEN. Bei den Klick-Typen ist sie der Unterschied
    // zwischen KLICK und FARBE+KLICK, laeuft dort also ueber den Typ.
    if (!klickt) ruf("block_trigger", {wahl: an ? "da" : "kein"});
    else ruf("block_typ", {typ: an ? "wait_click" : "click"});
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
    onclick: () => mitWarten("ruf", "punkt_aufnehmen"),
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
    mitWarten("ruf", "bereich_aufnehmen");
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
  if (!b.else_greift && !b.else_aktion) return;
  // Kein ELSE heisst: keine Kachel markiert. Eine Kachel „(keine)" saehe aus wie
  // eine sechste Aktion, obwohl sie die Abwesenheit von allen ist.
  //
  // Der Rueckweg ist die markierte Kachel selbst — und weil man ein Umschalten
  // nicht sieht, steht es im Hinweis darunter und im Tooltip der Kachel.
  const auswirkung = b.else_aktion
    ? ELSE_BESCHREIBUNGEN[b.else_aktion]
    : ohneElseText();
  ziel.appendChild(ueberschrift("ELSE — WENN DIE BEDINGUNG NICHT GREIFT",
    "ELSE ist ein „stattdessen“, kein „zusätzlich“: greift es, entfällt die " +
    "eigene Aktion des Schritts. " + auswirkung +
    (b.else_aktion ? " Ein zweiter Klick auf die markierte Kachel hebt ELSE wieder auf." : ""),
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
  ziel.appendChild(el("div", {class: "gitter3"}, S.else_aktionen.map((a) =>
    el("button", {
      // Eigene Klasse trotz gleicher Form: eine Typ-Kachel schaltet den Block-Typ,
      // eine ELSE-Kachel die Ersatzaktion. Wer eine davon später anders gestalten
      // will, soll nicht beide erwischen.
      class: "typ-chip else-chip" + (a === b.else_aktion ? " an" : ""),
      title: ELSE_BESCHREIBUNGEN[a] +
             (a === b.else_aktion ? " Nochmal klicken = kein ELSE." : ""),
      // Dieselbe Kachel nochmal: das leere Kommando entfernt die Aktion. Eine
      // andere Kachel wechselt sie wie gewohnt.
      onclick: () => ruf("block_else", {aktion: a === b.else_aktion ? "" : a}),
    }, a))));
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
/* Wohin der Reiter nach dem naechsten `scan_oeffnen` springt. `null` heisst
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
 * Rueckgaengig-Stapel (`zaehlt`). */
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
  // Nach Laden oder Umbenennen einer Sequenz darf die Scan-Aufnahme der zuvor
  // offenen Sequenz nicht weiter im Reiter stehen. Der Name ist ein billiger,
  // eindeutiger Besitzerwechsel und erzwingt dann eine frische Aufnahme.
  if (SC && S && SC.sequenz !== S.name) frisch = true;
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
  if (name === "scan_neu_laden" || name === "scan_lernvorschau_uebernehmen")
    scanOrdnungVergessen();
  // **Einen Scan zu oeffnen ist ein Wechsel des Zusammenhangs.** Danach gilt
  // wieder die Vorgabe — und die sind bei offenem Scan seine Items, also das,
  // weswegen man ihn geoeffnet hat. Vorher landete man auf der Scan-Liste und
  // sah den Namen, den man gerade angeklickt hatte, ein zweites Mal.
  if (name === "scan_oeffnen") {
    scanListe = scanReiterNachOeffnen;
    scanReiterNachOeffnen = null;
    scanOrdnungVergessen();
  }
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
               aktion: scanArt === "item" ? "Bestätigungsklick setzen"
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
    el("span", {class: "wachse"})
  );
  if (e.unbekannt) ziel.appendChild(el("button", {class: "btn still",
    onclick: () => scanErgebnisNaechster("unbekannt_slots")}, "Nächsten unbekannten zeigen"));
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

/** Hat die aktuelle Art ein eindeutiges Ziel für Bild, Slots und Regionen? */
function scanKonfigurationOffen() {
  return !!(SC && SC.aufnahme_bereit && SC.aufnahme_bereit[scanArt]);
}

/** Holt das Bild nur, wenn es ein neues gibt — es ist der grosse Brocken. */
async function scanBildPflegen() {
  const bild = $("scan-bild");
  const leer = $("scan-leer");
  if (!SC.foto) {
    $("scan-flaeche").hidden = true;
    $("scan-ohne-bild").hidden = true;
    leer.hidden = false;
    leer.textContent = !scanKonfigurationOffen()
      ? "Zuerst oben einen Scan anlegen oder auswählen. Danach kann ein Screenshot aufgenommen werden."
      : SC.pillow
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
  $("scan-sequenz").textContent = SC.sequenz || "— keine Sequenz —";
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
      onclick: () => rufScan("scan_modus_setzen", {modus: m.key, art: scanArt}),
    },
      el("span", {}, m.text),
      el("span", {class: "taste"}, m.taste),
      el("span", {class: "klein"}, m.hilfe)));
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
  const fensterquelle = !!(SC.fenster_titel || SC.fenster_id);
  $("scan-foto").textContent = fensterquelle ? "Fenster aufnehmen"
    : (SC.bereich ? "Bereich aufnehmen" : "Screenshot aufnehmen");

  // Der Bereich gilt fuer JEDE weitere Aufnahme dieses Scans — er muss also
  // dastehen, nicht nur in der Statuszeile aufblitzen.
  const quelleninfo = $("scan-quelleninfo");
  const quellenname = $("scan-quellenname");
  const bz = $("scan-bereich");
  const groesse = SC.bereich
    ? (SC.bereich[2] - SC.bereich[0]) + "×" + (SC.bereich[3] - SC.bereich[1])
    : "";
  quellenname.textContent = fensterquelle
    ? "Fenster „" + (SC.fenster_titel || "gewählt") + "“"
    : (SC.bereich ? "Eigener Bildschirmausschnitt" : "Ganzer Bildschirm");
  const quellendetails = [];
  if (fensterquelle) quellendetails.push("Slots relativ");
  if (groesse) quellendetails.push(groesse);
  if (!fensterquelle && SC.bereich) {
    quellendetails.push("Position " + SC.bereich[0] + ", " + SC.bereich[1]);
  }
  if (!SC.fenster_verfuegbar && SC.fenster_titel) {
    quellendetails.push("Fenster nicht geöffnet");
  }
  bz.textContent = quellendetails.join(" · ");
  bz.hidden = !quellendetails.length;
  // Bei einem gewaehlten Fenster steht dabei, was das bedeutet: es wird direkt
  // abgebildet, also darf das Studio davor liegen.
  quelleninfo.title = fensterquelle
    ? "Editor und Live-Scan verwenden dieselbe Aufnahmequelle. Verschieben wird automatisch ausgeglichen; beim Desktop-Fallback muss das Fenster sichtbar sein."
    : (SC.bereich ? "Ausschnitt vom Bildschirm — hier darf nichts davor liegen." : "");
  quelleninfo.classList.toggle("an", !!SC.bereich || fensterquelle);
  $("scan-vollbild").disabled = !bereit || (!SC.bereich && !fensterquelle) || !SC.pillow;
  // Aufziehen geht nur auf einem Bild — vorher gibt es nichts anzuklicken.
  const auf = $("scan-aufziehen");
  auf.disabled = !bereit || !fotoDa();
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
function maskeId(art, name) { return "maske:" + art + ":" + name; }

/** Der Reiter folgt der Auswahl — aber nur, wenn sie sich geaendert hat.
 *
 * Ein Klick im Bild waehlt einen Slot. Steht gerade die Item-Liste offen,
 * geschieht rechts sonst nichts, und der Klick sieht wirkungslos aus. Beim
 * blossen Neuzeichnen darf dagegen nichts umschalten: sonst waere der Weg aus
 * der Slot-Liste heraus versperrt, solange ein Slot gewaehlt ist. */
function scanReiterFolgen() {
  if (!SC || scanArt !== "item") return;
  const jetzt = SC.wahl.art + ":" + SC.wahl.name;
  if (jetzt === scanWahlZuletzt) return;
  const erster = scanWahlZuletzt === null;
  scanWahlZuletzt = jetzt;
  // Der Scan hat seinen eigenen Weg (`scanReiterNachOeffnen`); und beim
  // allerersten Zeichnen gibt es keinen Wechsel, nur einen Anfangszustand.
  if (erster) return;
  const ziel = {slot: "slots", item: "items"}[SC.wahl.art];
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
    for (const [key, text, zahl] of [["bosse", "Bosse", erkBosse().length],
                                     ["bibliothek", "Bibliothek",
                                      SC.global_bosses.length]]) {
      an(tabs, el("button", {class: "tab" + (offen === key ? " an" : ""),
        onclick: () => { scanListe = key; zeichneScans(); }}, text + " " + zahl));
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
  for (const [key, text, sichtbar, gesamt] of gruppen) {
    an(tabs, el("button", {
      class: "tab" + (offen === key ? " an" : ""),
      title: sichtbar === gesamt ? "" : gesamt + " insgesamt",
      onclick: () => { scanListe = key;
                       scanOrdnungVergessen(); zeichneScans(); },
    }, text + " " + sichtbar + (sichtbar === gesamt ? "" : "/" + gesamt)));
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
    const art = offen === "slots" ? "slot" : "item";
    const gesamt = offen === "slots" ? SC.slots : SC.items;
    filter.appendChild(el("button", {class: "btn gefahr", disabled: !gesamt.length,
      title: gesamt.length
        ? "Löscht alle " + gesamt.length + " " + (art === "slot" ? "Slots" : "Items")
          + " aus „" + SC.offen + "“ — nicht nur aus der Mitgliedschaft. "
          + "STRG+Z nimmt es zurück."
        : "Nichts zu löschen.",
      onclick: () => rufScan("scan_alle_loeschen", {art: art})},
      gesamt.length + " " + (art === "slot" ? "Slots" : "Items") + " löschen"));
  }
  if (offen === "items" && SC.kategorien.length) {
    filter.appendChild(auswahl("", [{wert: "", text: "alle Kategorien"}].concat(
      SC.kategorien.map((k) => ({wert: k, text: k}))), scanKategorie,
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
function scanOrdnungGruppe(art) {
  const merk = scanOrdnung[art];
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
function scanOrdnungUmbenennen(art, alt, neu) {
  const merk = scanOrdnung[art];
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
function scanVorschauUmbenennen(art, alt, neu) {
  if (art !== "item" || !neu || alt === neu) return;
  const bild = scanVorschauen.get(alt);
  if (bild) scanVorschauen.set(neu, bild);
}

/** Die gemerkte Reihenfolge als Rang je Name; unbekannt = ans Ende. */
function scanOrdnungRang(art) {
  const merk = scanOrdnung[art];
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
function scanSichtbar(eintraege, mitKategorie, art) {
  let liste = eintraege;
  if (mitKategorie && scanKategorie)
    liste = liste.filter((e) => (e.kategorie || "") === scanKategorie);
  return liste;
}

/** Ein Namensfeld in einer Maske — mit dem Fokus-Anker fuer das Umbenennen. */
function maskeName(art, name, titel, setze) {
  const feld = el("input", {value: name, autocomplete: "off", title: titel});
  feld.addEventListener("change", () => {
    const neu = feld.value.trim();
    // DREI Dinge haengen am Namen: der Anker fuer den Fokus, der Rang in der
    // Liste und die gemerkte Vorschau. Wer umbenennt, sagt allen dreien vorher
    // Bescheid — wer eines vergisst, sieht es sofort: der Fokus springt weg,
    // die Zeile wandert, oder das Bild blinkt.
    fokusUmbenennung(maskeId(art, name), maskeId(art, neu));
    scanOrdnungUmbenennen(art, name, neu);
    scanVorschauUmbenennen(art, name, neu);
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
function maskeBauen(art, name, gewaehlt, teile, detail, beimWaehlen) {
  const maske = el("div", {class: "scan-maske" + (gewaehlt ? " an" : ""),
                           id: maskeId(art, name)});
  for (const teil of teile) maske.appendChild(teil);
  if (gewaehlt && detail) {
    const kasten = el("div", {class: "scan-maske-detail"});
    detail(kasten);
    maske.appendChild(kasten);
  }
  // Ein Klick auf die Maske waehlt sie; ein zweiter klappt ein offenes Item
  // wieder zu. Felder und Knoepfe sind davon ausgenommen, sonst wuerde schon
  // das Bearbeiten den Detailteil unter der Hand schliessen.
  maske.addEventListener("click", (e) => {
    if (e.target.closest("input, label, button, select, summary, details")) return;
    if (gewaehlt && art === "item") {
      rufScan("scan_waehlen", {art: "item", name: ""});
    } else if (!gewaehlt) {
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
  const setze = (feld, wert) => rufScan("scan_slot_setzen",
                                        {name: s.name, feld: feld, wert: wert});
  const gewaehlt = SC.auswahl.includes(s.name)
                || (SC.wahl.art === "slot" && SC.wahl.name === s.name);
  const name = maskeName("slot", s.name,
    "Name — zugleich die Referenz in jedem Scan", (v) => setze("name", v));
  // **Die ID ist eine reine Anzeige-Kachel, kein Knopf.** Sie bleibt gleich,
  // auch wenn der Slot im offenen Scan ab- und wieder angeschaltet wird — DAS
  // ändert nur seine STELLE (er wandert ans Ende der Mitgliederliste), nicht
  // seine Identität. Die Stelle steht deshalb nur noch im Tooltip, nicht mehr
  // in der Zahl selbst.
  const id = el("span", {class: "zahl",
    title: s.nummer
      ? "Slot-ID #" + s.id + " — bleibt gleich, auch beim Ab-/Wieder-Anschalten. "
        + "Läuft in „" + SC.offen + "“ als " + s.lauf + ". von " + s.gesamt + "."
        + (s.lauf !== s.nummer ? " (rückwärts)" : "")
      : "Slot-ID #" + s.id + " — bleibt gleich, auch beim Ab-/Wieder-Anschalten."},
    "#" + s.id);
  const box = el("input", {type: "checkbox",
    "aria-label": s.name + " ein- oder ausschalten"});
  box.checked = !!s.aktiv;
  box.addEventListener("change", () => setze("aktiv", box.checked));
  const anaus = el("label", {class: "an scan-slot-schalter",
    title: s.aktiv ? "Slot ist aktiv — ausschalten" : "Slot ist aus — einschalten"}, box);
  const felder = el("div", {class: "scan-maske-felder"}, name, scanSlotStand(s));
  const maske = maskeBauen("slot", s.name, gewaehlt,
    [el("div", {class: "scan-marke"}, anaus, id),
     el("span", {class: "kugel" + (s.farbe ? "" : " ohne"),
                  title: s.farbe ? "Hintergrund " + s.farbe : "Hintergrund nicht gemessen",
                  style: s.farbe ? "background:" + s.farbe : ""}),
     felder],
    (kasten) => scanSlotDetails(kasten, s),
    () => rufScan("scan_waehlen", {art: "slot", name: s.name}));
  maske.classList.toggle("aus", !s.aktiv);
  return maske;
}

/** Die Zustandszeile eines Slots: Groesse, Warnung, letzter Treffer. */
function scanSlotStand(s) {
  // Die Groesse ist ein gemessener WERT, kein Satz — also dieselbe Kachel wie
  // die Nummer daneben. Was daneben steht („Item 1", „unbekannt", „→ Helme"),
  // ist eine Aussage und bleibt Text.
  const teile = [el("span", {class: "zahl"}, s.breite + "×" + s.hoehe)];
  if (!s.aktiv) teile.push(el("span", {class: "klein slot-aus"}, "aus"));
  // Ein winziger Slot ist im Bild kaum zu treffen — in der Liste ist er so
  // gross wie jeder andere. Deshalb steht die Warnung HIER: das ist der Weg,
  // ihn auszuwaehlen und zu loeschen.
  if (s.winzig) {
    teile.push(el("span", {class: "klein", style: "color:var(--err)",
      title: "Zu klein zum Erkennen — hier auswählen und löschen"}, "⚠ zu klein"));
  } else if (s.treffer && s.treffer.name) {
    teile.push(el("span", {class: "klein",
      style: "color:var(" + (s.treffer.fremd ? "--slot-fremd" : "--slot-ok") + ")",
      title: s.treffer.fremd
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
    a.prioritaet - b.prioritaet || a.name.localeCompare(b.name, "de");
  const liste = scanSichtbar(SC.items, true, "item").slice().sort((a, b) =>
    rang ? (rang(a.name) - rang(b.name)) || frisch(a, b)
         : ((a.kategorie || "").localeCompare(b.kategorie || "", "de")
            || frisch(a, b)));
  if (!rang) {
    scanOrdnung.item = liste.map((i) => ({name: i.name, gruppe: i.kategorie || ""}));
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
    const kategorie = (gefroren === null ? (i.kategorie || "") : gefroren)
                      || "Ohne Kategorie";
    if (kategorie !== letzteKategorie) {
      ziel.appendChild(el("div", {class: "scan-kategorie-kopf"}, kategorie));
      letzteKategorie = kategorie;
    }
    ziel.appendChild(scanItemMaske(i, gefroren));
  }
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
  const setze = (feld, wert) => rufScan("scan_item_setzen",
                                        {name: i.name, feld: feld, wert: wert});
  const gewaehlt = SC.wahl.art === "item" && SC.wahl.name === i.name;
  const bild = scanVorschauen.get(i.name);

  const box = el("input", {type: "checkbox",
    "aria-label": i.name + " ein- oder ausschalten"});
  box.checked = !!i.aktiv;
  box.addEventListener("change", () => setze("aktiv", box.checked));
  const anaus = el("label", {class: "an scan-slot-schalter",
    title: i.aktiv ? "Item ist aktiv — ausschalten" : "Item ist aus — einschalten"}, box);

  const name = maskeName("item", i.name,
    "Name — zugleich die Referenz in jedem Scan", (v) => setze("name", v));

  // Vorhandene anklicken, neue tippen — dasselbe Bedienelement wie in der
  // Lern-Vorschau. Ein freies Textfeld allein macht aus „Helme" und „helme"
  // zwei Kategorien, und Items derselben Kategorie konkurrieren miteinander.
  const kat = kategorieWahl(i.kategorie || "", (v) => setze("kategorie", v),
    {titel: "Items derselben Kategorie konkurrieren; die kleinere Priorität gewinnt",
     leer: "— ohne —", schluessel: "item:" + i.name});

  // **Die Zahl allein sagt nicht, ob sie frei ist.** Teilt sich das Item seinen
  // Rang mit einem anderen derselben Kategorie, entscheidet die Scan-Reihenfolge
  // — also der Zufall. Das steht am Feld, nicht erst im aufgeklappten Detail:
  // getippt wird hier.
  const kollision = prioritaetDoppelt(i);
  const prio = el("input", {
    type: "number", value: i.prioritaet, min: 0, step: 1,
    class: kollision.length ? "doppelt" : "",
    title: kollision.length
      ? "P" + i.prioritaet + " hat auch: " + kollision.join(", ")
        + " — bei gleicher Zahl entscheidet der Zufall"
      : "Priorität — kleiner gewinnt" + (i.kategorie
          ? " (frei in „" + i.kategorie + "“: P"
            + naechsteFreiePrioritaet(i.kategorie, i.name) + ")"
          : ", zählt nur innerhalb einer Kategorie")});
  prio.addEventListener("change", () => {
    if (prio.value.trim() !== "") setze("prioritaet", Number(prio.value));
  });
  prio.addEventListener("keydown", (e) => { if (e.key === "Enter") prio.blur(); });

  const felder = el("div", {class: "scan-maske-felder"}, name,
    el("div", {class: "scan-maske-unten"}, kat, prio), scanItemStand(i, gefroren));

  const maske = maskeBauen("item", i.name, gewaehlt,
    [el("div", {class: "scan-marke"}, anaus),
     bild ? el("img", {class: "mini", src: bild, alt: ""})
          : el("span", {class: "kugel" + (i.marker.length ? "" : " ohne"),
                        style: i.marker.length ? "background:" + i.marker[0] : ""}),
     felder],
    // **Das Gewaehlte klappt seine Einstellungen hier auf**, statt sie in eine
    // andere Spalte zu legen: Vorlage, Marker, Konfidenz und Loeschen gehoeren
    // diesem Item, und man sieht beim Arbeiten daran nicht zwischen zwei Orten
    // hin und her. Nur beim gewaehlten — sechzig aufgeklappte Bloecke waeren
    // keine Liste mehr.
    (kasten) => scanItemDetails(kasten, i),
    () => rufScan("scan_waehlen", {art: "item", name: i.name}));
  maske.classList.add("scan-item-maske");
  maske.classList.toggle("aus", !i.aktiv);
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
      && (i.kategorie || "") !== gefroren) {
    teile.push(el("span", {style: "color:var(--accent)",
      title: "Beim nächsten „Sortieren“ rutscht das Item in diese Gruppe"},
      "→ " + (i.kategorie || "ohne Kategorie")));
  }
  if ((i.erkannt_in || []).length) {
    teile.push(el("span", {style: "color:var(--slot-ok)"},
      "erkannt in " + i.erkannt_in.slice(0, 2).join(", ")
      + (i.erkannt_in.length > 2 ? " +" + (i.erkannt_in.length - 2) : "")));
  }
  if (i.stumm) {
    teile.push(el("span", {style: "color:var(--err)",
      title: "Weder Template noch Marker — dieses Item wird nie erkannt"}, "stumm"));
  } else if (!(i.vorlagen || []).length) {
    teile.push(el("span", {class: "mono"}, i.marker.length + " Marker"));
  }
  if ((i.fehlende_scan_groessen || []).length) {
    teile.push(el("span", {style: "color:var(--accent)",
      title: "Für die Slot-Größen dieses Scans gibt es noch keine Vorlage"},
      "Vorlage fehlt"));
  }
  const kollision = prioritaetDoppelt(i);
  if (kollision.length) {
    teile.push(el("span", {style: "color:var(--accent)",
      title: "Gleiche Priorität wie " + kollision.join(", ")
             + " — welches zuerst geklickt wird, entscheidet der Zufall"},
      "P" + i.prioritaet + " doppelt"));
  }
  if (i.bestaetigung) {
    teile.push(el("span", {class: "mono", title: "Nach dem Klick wird bestätigt: "
      + i.bestaetigung.text}, "+ Bestätigung"));
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
  const stand = el("div", {class: "scan-maske-stand"},
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
     el("div", {class: "scan-maske-felder"}, name, stand)],
    (kasten) => scanScanDetails(kasten, c),
    // Waehlen und Oeffnen sind hier dasselbe: ein Scan, den man ansieht, ist
    // der, an dem man arbeitet. Der Reiter bleibt dabei stehen — sonst
    // verschwindet die Maske, die sich gerade aufgeklappt hat.
    () => { scanReiterNachOeffnen = "scans";
            rufScan("scan_oeffnen", {name: c.name}); });
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
  if (neu && ansicht === "scans") scanInspektor();
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
    const gewaehlt = SC.auswahl.includes(s.name)
      || (SC.wahl.art === "slot" && SC.wahl.name === s.name);
    // Gruen = hier liegt ein Item, das der Scan kennt. Amber = erkannt, aber
    // noch nicht Mitglied dieses Scans — anderer Zustand, andere Farbe, sonst
    // sucht man spaeter, warum der Scan das Gruene nicht findet.
    const zustand = (s.treffer
      ? (s.treffer.name ? (s.treffer.fremd ? " fremditem" : " treffer") : " leer")
      : "");
    const aus = s.aktiv ? "" : " aus";
    // Die Fuellung traegt denselben Zustand wie der Umriss: auf einem bunten
    // Spielbild ist die Flaeche das, was man sieht, der Strich schaerft nur.
    svg.appendChild(svgEl("rect", {x: x1, y: y1, width: x2 - x1, height: y2 - y1,
      class: "scan-fuellung" + zustand + aus + (gewaehlt ? " gewaehlt" : "")}));
    svg.appendChild(svgEl("rect", {x: x1, y: y1, width: x2 - x1, height: y2 - y1,
      class: "scan-slot" + zustand + aus + (gewaehlt ? " gewaehlt" : "")}));
    // Name ueber dem Rechteck, Erkennungsergebnis darunter — so ueberdeckt
    // keins von beiden das Bild im Slot.
    //
    // Nur, wenn er hineinpasst: die Schrift steht in SCHIRM-Pixeln (gegen den
    // Zoom gerechnet), der Slot in Bild-Pixeln, und bei 45 Slots waeren es 45
    // Namen uebereinander. Der gewaehlte behaelt seinen immer.
    const breit = (x2 - x1) * scanZoom;      // Breite auf dem Schirm
    if (breit >= 34 || gewaehlt) {
      svg.appendChild(svgEl("text", {x: x1, y: y1 - 3 * px, class: "scan-marke" + aus,
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
    svg.appendChild(svgEl("path", {class: "scan-kreuz" + aus,
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
 * Einen Slot in der Liste anzuklicken markiert ihn im Bild — bei 45 Slots auf
 * 1:1 liegt er dabei aber meist ausserhalb.
 *
 * Gescrollt wird NUR, wenn er wirklich draussen liegt, und nur beim Wechsel der
 * Auswahl: eine Buehne, die bei jedem Neuzeichnen springt, nimmt einem die
 * Stelle weg, die man gerade ansieht. */
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

function scanStelleAusEvent(e, amBildrand = false) {
  const rand = $("scan-overlay").getBoundingClientRect();
  if (!rand.width || !rand.height || !SC || !SC.foto) return null;
  let bx = (e.clientX - rand.left) / rand.width * SC.foto.breite;
  let by = (e.clientY - rand.top) / rand.height * SC.foto.hoehe;
  if (amBildrand) {
    bx = Math.max(0, Math.min(SC.foto.breite, bx));
    by = Math.max(0, Math.min(SC.foto.hoehe, by));
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
    el("div", {class: "knopfpaar"},
      scanArt === "item"
        // **Derselbe Befehl heisst ueberall gleich.** Er stand hier als „Items
        // erkennen" und im Assistenten als „Erkennung testen" — zwei Namen fuer
        // einen Knopf, und man probiert beide aus, weil man annimmt, sie taeten
        // Verschiedenes.
        ? el("button", {class: "btn", disabled: !fotoDa() || !SC.slots.length,
                        title: "Hält jeden Slot gegen die Item-Profile und schreibt "
                               + "das Ergebnis an Bild und Item-Liste",
                        onclick: () => rufScan("scan_erkennen")}, "Items erkennen")
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
                    onclick: () => rufScan("scan_rueckgaengig")}, "↶ Zurück")));
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
    const art = scanListe === "slots" ? "slot" : "item";
    const eintraege = scanListe === "slots" ? SC.slots : SC.items;
    const irgendAn = eintraege.some((e) => !!e.aktiv);
    filter.appendChild(el("button", {class: "btn still", disabled: !eintraege.length,
      title: "Schaltet alle " + (art === "slot" ? "Slots" : "Items")
             + (irgendAn ? " aus." : " ein."),
      onclick: () => rufScan("scan_alle_schalten",
                             {art: art, aktiv: !irgendAn})},
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
  if (scanMaskenRechts() && SC.auswahl.length > 1) {
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
    const status = el("span", {class: "klein mono scan-review-status"});
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
      zeile.classList.toggle("ueberspringen", !haken.checked);
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
    zeile = el("div", {class: "scan-review-zeile" +
        (z.variante ? " variante" : z.duplikat ? " duplikat fertig" : ""),
      "data-slot": z.slot, "data-vorhanden": vorhandenerName,
      "data-als-anderes": "false"}, haken, status,
      z.bild ? el("img", {class: "scan-review-bild", src: z.bild, alt: ""})
             : el("span", {class: "scan-review-bild leer"}),
      el("div", {class: "felder"},
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
  liste.appendChild(el("div", {class: "knopfpaar", style: "margin-top:8px"},
    el("button", {class: "btn", onclick: () => rufScan("scan_lernvorschau_abbrechen")}, "Abbrechen"),
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

/** Was zum gewaehlten Slot gehoert — im Detailteil seiner Maske.
 *
 * **Der Name steht in der Maske, nicht hier.** Dieselbe Regel wie beim Item und
 * beim Klick-Block im Sequenz-Editor: was dem Ding GEHOERT (seine Identitaet),
 * steht beim Ding; hier bleibt, was man daran EINSTELLT. */
function scanSlotDetails(ziel, s) {
  const setze = (feld, wert) => rufScan("scan_slot_setzen", {name: s.name, feld: feld, wert: wert});

  ziel.appendChild(el("div", {class: "knopfpaar"},
    el("button", {class: "btn still",
      title: "Wohin geklickt wird, wenn in diesem Slot ein gesuchtes Item liegt",
      onclick: () => rufScan("scan_modus_setzen", {modus: "klick"})},
      "Klickpunkt setzen"),
    el("button", {class: "btn still", disabled: !fotoDa(),
      title: "Die Farbe des leeren Slots — sie wird beim Item-Lernen abgezogen, "
             + "damit nicht der Rahmen als Merkmal gelernt wird",
      onclick: () => rufScan("scan_modus_setzen", {modus: "messen"})},
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
  erweitert.appendChild(farbfeld("Hintergrund", s.farbe, (v) => setze("farbe", v),
    "Die Farbe des leeren Slots. Sie wird beim Item-Lernen abgezogen, damit " +
    "nicht der Rahmen als Merkmal gelernt wird.", "hintergrund"));
  ziel.appendChild(erweitert);

  ziel.appendChild(el("div", {class: "knopfpaar"},
    el("button", {class: "btn", disabled: !fotoDa(),
                  onclick: () => rufScan("scan_item_lernen", {slot: s.name})},
       "Item lernen"),
    el("button", {class: "btn gefahr", onclick: () => rufScan("scan_slot_loeschen")},
       "löschen")));
  if (fotoDa()) {
    // „Alle" heisst: alle Slots des offenen Scans, nicht des ganzen Bestands
    // (`_scan_slots()` in scans.py). Das steht im Knopf, weil es vorher
    // stillschweigend anders war — und die Meldung danach ratlos machte.
    ziel.appendChild(el("button", {class: "btn still",
      title: SC.offen ? "Alle Slots aus „" + SC.offen + "“ — nicht der ganze Bestand"
                      : "Alle Slots im Bestand (kein Scan offen)",
      onclick: () => rufScan("scan_lernvorschau", {scope: "alle"})},
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
    "sich mit STRG+Z zurücknehmen.", "auswahl"));
  ziel.appendChild(el("p", {class: "hinweis"}, SC.auswahl.length + " Slots gewählt"));
  // Die Namen stehen da, nicht nur die Zahl: was man loescht, soll man vorher
  // lesen koennen. Bei dreissig wird die Liste lang - dafuer scrollt sie.
  ziel.appendChild(el("div", {class: "spalte", style: "gap:2px;max-height:160px;"
    + "overflow-y:auto;font-family:var(--mono);font-size:11px;color:var(--muted)"},
    ...SC.auswahl.map((n) => el("span", {}, n))));

  ziel.appendChild(ueberschrift("LAGE UND GRÖSSE",
    "Verschieben: im Bild ziehen oder Pfeiltasten (SHIFT = 10 px) — der " +
    "Klickpunkt geht mit. Angleichen zieht alle auf die MITTLERE Grösse, um " +
    "ihre Mitte herum: ein einzelner Verklicker soll nicht alle anderen " +
    "verbiegen.", "auswahl-lage"));
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

  ziel.appendChild(el("div", {class: "knopfpaar", style: "margin-top:14px"},
    el("button", {class: "btn", onclick: () => rufScan("scan_abbrechen")},
       "Auswahl aufheben"),
    el("button", {class: "btn gefahr", onclick: () => rufScan("scan_slot_loeschen")},
       SC.auswahl.length + " löschen")));
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
    erweitert.appendChild(el("div", {class: "spalte", style: "gap:5px"},
      (i.vorlagen || []).map((v) => el("div", {class: "reihe"},
        el("span", {class: "hinweis mono wachse"}, v),
        el("button", {class: "btn still", title: "Nur vom Item lösen; Datei bleibt erhalten",
          onclick: () => rufScan("scan_item_vorlage_entfernen", {name: i.name, datei: v})},
          "Vorlage entfernen")))));
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
  if (i.kategorie === "Auto" && (i.vorlagen || []).length) {
    ziel.appendChild(el("button", {class: "btn breit", style: "margin-top:10px",
      onclick: () => rufScan("scan_items_autoname", {namen: [i.name]})},
      "✦ Mit LLM benennen"));
  }
  ziel.appendChild(scanItemBestaetigung(i));
  if (i.stumm) {
    ziel.appendChild(el("p", {class: "hinweis", style: "color:var(--err)"},
      "Weder Template noch Marker — dieses Item wird nie erkannt."));
  }
  ziel.appendChild(el("button", {class: "btn gefahr", style: "margin-top:14px",
    onclick: () => rufScan("scan_item_loeschen")}, "Item löschen"));
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
  const setze = (feld, wert) => rufScan("scan_item_setzen",
                                        {name: i.name, feld: feld, wert: wert});
  const kasten = el("div", {class: "spalte", style: "gap:7px"});
  kasten.appendChild(ueberschrift("BESTÄTIGUNGSKLICK",
    "Manche Spiele fragen nach dem Klick nach („wirklich verkaufen?“). Ohne "
    + "die Bestätigung bleibt das Popup stehen, und der Scan kommt nicht mehr "
    + "zum nächsten Slot. Die Stelle steht als Punkt in sequence.json — dieselbe "
    + "Kalibrierung erfasst sie mit.", "bestaetigung"));
  const wahl = auswahl("Punkt", [{wert: "", text: "— keine Bestätigung —"}].concat(
    SC.punkte.map((p) => ({wert: p.id, text: "#" + p.id + " " + p.name}))),
    i.bestaetigung ? i.bestaetigung.punkt_id : "", (v) => setze("bestaetigung", v));
  kasten.appendChild(wahl);
  // Ein Punkt, den es nicht mehr gibt, wird GESAGT statt verschwiegen: der
  // Lauf klickt sonst nichts, und man sucht den Fehler bei der Erkennung.
  if (i.bestaetigung && i.bestaetigung.fehlt) {
    kasten.appendChild(el("p", {class: "hinweis", style: "color:var(--err)"},
      i.bestaetigung.text + " — die Bestätigung greift nicht."));
  }
  kasten.appendChild(el("button", {class: "btn still", disabled: !fotoDa(),
    title: "Die Stelle im Bild anklicken — dabei entsteht ein Punkt, oder ein "
           + "vorhandener an derselben Stelle wird wiederverwendet",
    onclick: () => rufScan("region_modus", {art: "item", modus: "aktion"})},
    "Stelle im Bild anklicken"));
  if (i.bestaetigung) {
    kasten.appendChild(zahlfeld("Wartezeit (s)", i.bestaetigung_verzoegerung,
      (v) => setze("bestaetigung_verzoegerung", v), {min: 0, step: "any"},
      "Zeit zwischen dem Item-Klick und der Bestätigung — das Popup braucht "
      + "einen Moment, bis es da ist.", "bestaetigungszeit"));
  }
  return kasten;
}

/** Was zum offenen Item-Scan gehoert — im Detailteil seiner Maske. */
function scanScanDetails(ziel, c) {
  const setze = (feld, wert) => rufScan("scan_setzen", {name: c.name, feld: feld, wert: wert});

  ziel.appendChild(ueberschrift("EINSTELLUNGEN",
    "Welche Slots nach welchen Items durchsucht werden, steht in den Reitern "
    + "daneben: der Haken vor jeder Maske heisst „gehört zu diesem Scan“. Hier "
      + "steht, WIE gesucht wird. Ein Block vom Typ ITEM-SCAN verweist per Name "
      + "auf diesen Scan.", "itemscan"));

  ziel.appendChild(zahlfeld("Farb-Toleranz", c.toleranz, (v) => setze("toleranz", v),
    {min: 0, step: 1},
    "Wie weit eine Marker-Farbe abweichen darf, damit sie noch als gefunden gilt.",
    "toleranz"));
  ziel.appendChild(schalter("Unbekanntes lernen", c.lernen, (v) => setze("lernen", v),
    "Neue Slot-Inhalte werden als Items in die globale Liste gelernt — nie in "
    + "diesen Scan, damit sie nicht ungeprüft geklickt werden.", "lernen"));
  ziel.appendChild(schalter("Slots rückwärts", c.reverse, (v) => setze("reverse", v),
    "Von hinten nach vorn (4, 3, 2, 1). Sinnvoll, wenn das Spiel den Bestand "
    + "nach vorn aufrückt: dann verschiebt ein Klick nicht die noch nicht "
    + "besuchten Slots. Die Richtung gehört zum Inventar, deshalb steht sie hier "
    + "und nicht in den Einstellungen.", "reverse"));

  if (c.fehlend.length) {
    ziel.appendChild(el("p", {class: "hinweis", style: "color:var(--err)"},
      "Zeigt ins Leere: " + c.fehlend.join(", ") + ". Der Scan läuft mit dem Rest " +
      "weiter — lieber ein Slot weniger als ein toter Scan."));
  }
  ziel.appendChild(el("button", {class: "btn gefahr",
    title: "Entfernt die Konfiguration und ihre Datei. STRG+Z holt die "
           + "Konfiguration zurück, den gemerkten Screenshot nicht.",
    onclick: () => rufScan("scan_loeschen", {name: c.name})}, "Diesen Scan löschen"));
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
 * einmal und sind messbar (`tools/tests/studio_erkennung.py`). */
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
  karte.appendChild(el("div", {class: "knopfpaar"},
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
  ziel.appendChild(el("div", {class: "knopfpaar"},
    el("button", {class: "btn still",
      onclick: () => rufScan("boss_waehlen", {name: ""})}, "‹ zurück zum Scan"),
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
  const antwort = await frage("teilen_daten");
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

function teilenHaken(ziel, auswahl, zahlen) {
  for (const t of T.teile) {
    const zeile = el("label", {class: "teilen-zeile an"});
    const box = el("input", {type: "checkbox"});
    box.checked = !!auswahl[t.key];
    box.addEventListener("change", () => { auswahl[t.key] = box.checked; zeichneTeilen(); });
    zeile.append(box, el("span", {}, t.text),
      el("span", {class: "zahl"}, String(zahlen[t.key] ?? 0)));
    ziel.appendChild(zeile);
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
  rumpf.appendChild(el("p", {class: "hinweis"}, T.fenster && T.fenster.gefunden
    ? "Spielfenster „" + T.fenster.titel + "“: " + T.fenster.breite + "×"
      + T.fenster.hoehe + " px. Der Empfänger rechnet damit automatisch um."
    : (T.fenster
        ? "Spielfenster „" + T.fenster.titel + "“ ist nicht offen — der Empfänger "
          + "setzt beim Import zwei Punkte von Hand."
        : "Kein Fenstertitel eingestellt (window_focus_title) — der Empfänger "
          + "setzt beim Import zwei Punkte von Hand.")));
  rumpf.appendChild(el("button", {class: "btn haupt",
    onclick: () => rufTeilen("export_starten",
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
        onclick: () => rufTeilen("import_pruefen", {pfad: "exports/" + e.name})},
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
    el("button", {class: "btn breit", onclick: () => rufTeilen("datei_waehlen")},
      "Datei wählen …"),
    feld("oder Pfad", i ? i.pfad : "",
      (v) => rufTeilen("import_pruefen", {pfad: v})));
  ziel.replaceChildren(kopf);

  const rumpf = el("div", {class: "abschnitt wachsend"});
  if (!i) {
    rumpf.appendChild(el("p", {class: "hinweis"},
      "Noch keine Datei gewählt. Ein Bündel ist ein ZIP mit manifest.json."));
    ziel.appendChild(rumpf);
    return;
  }
  rumpf.appendChild(el("div", {class: "feld-still"}, i.datei,
    el("span", {class: "mono"}, i.erstellt || "")));
  teilenHaken(rumpf, teilenImport, i.inhalt);

  rumpf.appendChild(ueberschrift("KOORDINATEN",
    "Wie die Stellen des Absenders auf deinen Bildschirm kommen.", "importkoord"));
  // Ohne beidseitig bekanntes Fenster gibt es nichts zu wählen — eine Kachel,
  // die nichts tut, ist schlechter als keine.
  const modi = (i.auto ? [{wert: "auto", text: "aus Fenstergrösse"}] : [])
    .concat([{wert: "identity", text: "1:1 übernehmen"}]);
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
    onclick: () => rufTeilen("import_starten",
      {teile: teilenImport, modus: teilenModus, merge: teilenMerge})},
    "Bündel einlesen"));
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
let wzAufnahmeLive = {aktiv: false, pausiert: false, anzahl: 0, ereignisse: []};
/* Der Live-Stand der Klick-Runde. Sie laeuft im HAUPTPROZESS (dort haengt der
 * Maus-Hook), also weiss dieses Fenster von sich aus nichts ueber sie — der
 * Stand kommt ueber `.nachklick.json`. Ohne ihn stand hier nur „gestartet",
 * waehrend die Konsole jeden Schritt einzeln meldete. */
let wzNachklickPoll = 0;
let wzNachklickLive = {aktiv: false, index: 0, gesamt: 0, verlauf: [], punkt: {}};
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
 * per `_stelle_abwarten()` bzw. `bereich_aufnehmen()` global auf ENTER — bis zu
 * `warte_timeout` Sekunden. Solange kommt keine Antwort zurueck; die Seite kann
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
  punkt_aufnehmen: ["Stelle aufnehmen", 1],
  bereich_aufnehmen: ["Screenshot-Bereich aufziehen", 2],
  maus_stelle: ["Parkposition setzen", 1],
  werkzeug_punkt_aufnehmen: ["Punkt aufnehmen", 1],
  werkzeug_farben: ["Farbe messen", 1],
  kalib_referenz: ["Referenzpunkt setzen", 1],
};

let warteZaehler = null;

/** Blendet ein, worauf gerade gewartet wird — mit Countdown bis zum Zeitablauf. */
function warteZeigen(name) {
  const [was, drucke] = WARTE_GRIFFE[name] || ["Stelle setzen", 1];
  const grenze = (S && S.warte_timeout) || (W && W.warte_timeout) || 60;
  let rest = Math.round(grenze);
  const zahl = el("span", {class: "warte-rest"}, rest + " s");
  const kasten = el("div", {class: "warte-kasten"},
    el("div", {class: "warte-titel"}, was),
    el("div", {class: "warte-text"},
      "Fahre mit der Maus an die Stelle im Spiel und drücke ",
      el("b", {}, "ENTER"),
      drucke > 1 ? " — " + drucke + "× nacheinander, eine Ecke je Druck." : "."),
    el("div", {class: "warte-fuss"},
      el("span", {}, "ESC bricht ab"), zahl));
  warteWeg();
  document.body.appendChild(
    el("div", {class: "warte-huelle", id: "warte-huelle"}, kasten));
  // Der Countdown ist die zweite Haelfte der Auskunft: DASS gewartet wird, sagt
  // der Kasten — wie lange noch, nur die Zahl. Laeuft sie ab, endet der Aufruf
  // von selbst, und die Bruecke meldet „Nichts gedrueckt".
  warteZaehler = setInterval(() => {
    rest -= 1;
    zahl.textContent = Math.max(0, rest) + " s";
    if (rest <= 0) clearInterval(warteZaehler);
  }, 1000);
}

function warteWeg() {
  clearInterval(warteZaehler);
  warteZaehler = null;
  const alt = $("warte-huelle");
  if (alt) alt.remove();
}

/** Ruft eine blockierende Methode und zeigt so lange, worauf gewartet wird.
 *
 * `art` waehlt den Kanal, den der Aufruf ohnehin haette: `ruf` ersetzt die
 * Momentaufnahme, `werkzeug` zeichnet den Reiter neu, `frage` fragt nur. Das
 * Overlay aendert daran nichts — es legt sich nur davor.
 */
async function mitWarten(art, name, daten) {
  warteZeigen(name);
  try {
    return art === "ruf" ? await ruf(name, daten)
         : art === "werkzeug" ? await rufWerkzeug(name, daten)
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
  {key: "punkte", name: "Punkte verwalten", befehl: "points", bezug: "sequenz",
   kurz: "Aufnehmen, nachmessen, umbenennen und sicher löschen"},
  {key: "farben", name: "Farben analysieren", befehl: "color", bezug: "bestand",
   kurz: "Pixel und häufigste Bildschirmfarben sichtbar machen"},
  {key: "kalibrieren", name: "Kalibrieren", befehl: "fix", bezug: "bestand",
   kurz: "Koordinaten an ein neues Bildschirm-Layout anpassen"},
  {key: "klicken", name: "Punkte nachklicken", befehl: "klick", bezug: "sequenz",
   kurz: "Alle Klickstellen geführt im Spiel kontrollieren"},
];

/** Kleine, lokale Linien-Icons. Keine Schriftzeichen und keine externe Datei:
 *  dadurch bleiben Strichstärke und Ausrichtung in jedem System identisch. */
function wzIcon(art) {
  const pfade = {
    aufnahme: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18", "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8"],
    pruefen: ["M9 11l2 2 4-5", "M12 3a9 9 0 1 0 9 9", "M16 4l5-1-1 5"],
    kalibrieren: ["M12 2v4M12 18v4M2 12h4M18 12h4", "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8"],
    klicken: ["M5 3l12 9-6 1 3 6-3 2-3-6-4 4z"],
    punkte: ["M12 2v5M12 17v5M2 12h5M17 12h5", "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8"],
    farben: ["M12 3c-4 4-7 7-7 11a7 7 0 0 0 14 0c0-4-3-7-7-11z", "M9 15h6"],
    info: ["M12 11v6M12 7h.01", "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20"],
    ok: ["M4 12l5 5L20 6"],
    fehler: ["M6 6l12 12M18 6L6 18"],
    hinweis: ["M12 3L2 21h20z", "M12 9v5M12 18h.01"],
    ordner: ["M3 6h7l2 2h9v11H3z"],
  };
  const svg = svgEl("svg", {class: "wz-symbol", viewBox: "0 0 24 24",
    fill: "none", stroke: "currentColor", "stroke-width": "1.8",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true"});
  for (const d of pfade[art] || pfade.info) svg.appendChild(svgEl("path", {d}));
  return svg;
}

function wzKopf(key, titel, text) {
  return el("section", {class: "wz-hero " + key},
    el("div", {class: "wz-hero-icon"}, wzIcon(key)),
    el("div", {class: "wz-hero-copy"},
      el("div", {class: "wz-kicker"}, "WERKZEUG"),
      el("h2", {}, titel),
      el("p", {}, text)));
}

function wzInfo(titel, text, art = "info") {
  // Erklaerungen bleiben aus dem Arbeitsfluss, bis jemand sie braucht. Das
  // Studio verwendet dafuer bereits ueberall dasselbe kleine i; ein eigener
  // Infokasten im Werkzeuge-Reiter war nicht nur unruhig, sondern drueckte bei
  // schmaler Mitte auch die eigentlichen Bedienelemente zusammen.
  const zeichen = info(text, "werkzeug-" + titel);
  zeichen.setAttribute("title", titel);
  zeichen.setAttribute("aria-label", titel);
  return el("div", {class: "wz-info-kompakt " + art}, zeichen);
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
      el("b", {}, W ? W.sequenz : "—"),
      el("span", {}, " bleibt unverändert"));
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
    el("b", {}, W ? W.sequenz : "—"),
    el("span", {class: "hint"}, W ? " (" + W.datei + ")" : ""));
  if (W && W.offen)
    kasten.append(el("span", {class: "art-warn"}, " — ungespeichert"));
  return kasten;
}

async function zeichneWerkzeuge(frisch) {
  const antwort = await frage("werkzeug_daten");
  if (!antwort || ansicht !== "werkzeuge") return;
  W = antwort;
  for (const u of W.umfang)
    if (wzUmfang[u.schluessel] === undefined) wzUmfang[u.schluessel] = u.vorgabe;
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
  if (antwort.meldung)
    setzeStatus({text: antwort.meldung, art: antwort.ok ? "ok" : "err"});
  await zeichneWerkzeuge();
  return antwort;
}

function wzLinksZeichnen() {
  const ziel = $("wz-links");
  // Die Kopfleiste blendet ihre Sequenz-Bedienelemente in diesem Reiter aus (er
  // bearbeitet andere Dateien). Damit war aber auch der NAME weg, und bei der
  // Nachklicken ist das genau die Frage, die man sich stellt.
  const kopf = el("div", {class: "abschnitt"},
    el("span", {class: "ueberschrift"}, "WERKZEUGE"),
    el("div", {class: "wz-offen"},
      el("span", {class: "hint"}, "offene Sequenz"),
      el("b", {}, W ? W.sequenz : "—"),
      W && W.offen ? el("span", {class: "punkt-offen", title: "ungespeicherte Änderungen"})
                   : null));
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
    : wzOffen === "punkte" ? wzPunkteBauen()
    : wzOffen === "farben" ? wzFarbenBauen()
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
  raus.push(el("div", {class: "wz-aktion"},
    el("button", {class: "btn haupt wz-hauptaktion", onclick: wzPruefen},
      wzIcon("pruefen"), el("span", {}, "Jetzt prüfen"))));

  if (!wzBericht) return raus;
  if (!wzBericht.ok) {
    raus.push(el("p", {class: "art-err"}, wzBericht.meldung || "Prüfung fehlgeschlagen."));
    return raus;
  }
  if (!wzBericht.befunde.length) {
    raus.push(el("div", {class: "wz-erfolg"}, wzIcon("ok"),
      el("div", {}, el("b", {}, "Alles in Ordnung"),
        el("span", {}, wzBericht.geprueft.length + " Bereiche ohne Befund geprüft."))));
    return raus;
  }
  raus.push(el("div", {class: "wz-kennzahlen"},
    wzKennzahl(String(wzBericht.fehler || 0), "Fehler", "fehler"),
    wzKennzahl(String(wzBericht.hinweise || 0), "Hinweise", "hinweis"),
    wzKennzahl(String(wzBericht.geprueft.length), "Bereiche", "neutral")));
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
  const raus = [wzKopf("punkte", "Punkte verwalten",
    "Klickstellen sind eigenständige Objekte — jede Änderung zieht alle verwendenden Blöcke mit.")];
  raus.push(wzBezug("punkte"));
  const punkte = (W && W.punkte) || [];
  if (!punkte.some(p => p.id === wzPunktId)) wzPunktId = punkte.length ? punkte[0].id : null;
  const punkt = punkte.find(p => p.id === wzPunktId);
  const neuName = el("input", {placeholder: "Name des neuen Punkts", value: "Neuer Punkt",
    autocomplete: "off"});
  raus.push(el("div", {class: "wz-aktion gitter2"}, neuName,
    el("button", {class: "btn haupt", onclick: async () => {
      setzeStatus({art: "info", text: "Ins Spiel wechseln, Maus platzieren und ENTER drücken …"});
      const a = await mitWarten("werkzeug", "werkzeug_punkt_aufnehmen",
                                {name: neuName.value});
      if (a && a.ok) wzPunktId = a.punkt_id;
    }}, "＋ Neuen Punkt aufnehmen")));
  if (!punkt) {
    raus.push(el("p", {class: "leer"}, "Noch keine Punkte in dieser Sequenz."));
    return raus;
  }
  raus.push(auswahl("Punkt", punkte.map(p => ({wert: p.id,
    text: "#" + p.id + " " + p.name + " (" + p.x + ", " + p.y + ")"})), punkt.id,
    (v) => { wzPunktId = Number(v); wzMitteZeichnen(); wzRechtsZeichnen(); }));
  const setze = (feld, wert) => rufWerkzeug("werkzeug_punkt_setzen",
    {punkt_id: punkt.id, feld: feld, wert: wert});
  raus.push(feld("Name", punkt.name, (v) => setze("name", v)));
  raus.push(el("div", {class: "gitter2"},
    zahlfeld("X", punkt.x, (v) => setze("x", v), {step: "1"}),
    zahlfeld("Y", punkt.y, (v) => setze("y", v), {step: "1"})));
  raus.push(farbfeld("Gespeicherte Farbe", punkt.farbe ? hexfarbe(punkt.farbe) : "",
    (v) => setze("farbe", v)));
  raus.push(el("div", {class: "reihe", style: "gap:8px;flex-wrap:wrap"},
    el("button", {class: "btn", onclick: () => rufWerkzeug("werkzeug_punkt_zeigen",
      {punkt_id: punkt.id})}, "◎ Zeigen & Farbe prüfen"),
    el("button", {class: "btn", onclick: () => mitWarten("werkzeug",
      "werkzeug_punkt_aufnehmen", {punkt_id: punkt.id})}, "✛ Neu messen"),
    el("button", {class: "btn gefahr", disabled: punkt.verwendungen.length,
      title: punkt.verwendungen.length ? "Erst die aufgeführten Verwendungen entfernen" : "",
      onclick: () => rufWerkzeug("werkzeug_punkt_loeschen", {punkt_id: punkt.id})},
      "Löschen")));
  if (punkt.verwendungen.length) raus.push(el("p", {class: "hinweis"},
    "Löschen ist gesperrt: Dieser Punkt wird noch " + punkt.verwendungen.length + "× verwendet."));
  return raus;
}

/* ------------------------------------------------------ Farben analysieren */

function wzFarbenBauen() {
  const raus = [wzKopf("farben", "Farben analysieren",
    "Liest einen Pixel oder gruppiert die häufigsten Farben eines Bildschirmbereichs.")];
  raus.push(wzInfo("Aufnahme ohne Studio im Bild",
    "Nach dem Klick ins Spiel wechseln. Punkt und Vollbild starten mit ENTER; bei einer Region " +
    "werden obere linke und untere rechte Ecke jeweils mit ENTER bestätigt."));
  const starten = async (art) => {
    setzeStatus({art: "info", text: "Ins Spiel wechseln und mit ENTER bestätigen …"});
    wzFarbAnalyse = await mitWarten("werkzeug", "werkzeug_farben", {art: art});
    wzMitteZeichnen(); wzRechtsZeichnen();
  };
  raus.push(el("div", {class: "gitter3 wz-aktion"},
    el("button", {class: "btn haupt", onclick: () => starten("punkt")}, "Pixel unter Maus"),
    el("button", {class: "btn", onclick: () => starten("region")}, "Bereich analysieren"),
    el("button", {class: "btn", onclick: () => starten("vollbild")}, "Vollbild analysieren")));
  if (wzFarbAnalyse && !wzFarbAnalyse.ok)
    raus.push(el("p", {class: "art-err"}, wzFarbAnalyse.meldung || "Analyse fehlgeschlagen."));
  if (wzFarbAnalyse && wzFarbAnalyse.ok) {
    const liste = el("div", {class: "wz-farbliste"});
    for (const f of wzFarbAnalyse.farben || []) liste.appendChild(el("div", {class: "wz-farbzeile"},
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
  const zyklen = el("input", {type: "number", min: "0", step: "1",
    value: String(wzAufnahmeZyklen), disabled: wzAufnahmeGestartet});
  zyklen.addEventListener("input", () => { wzAufnahmeZyklen = Math.max(0, Number(zyklen.value) || 0); });
  const notiz = el("textarea", {rows: "3", disabled: wzAufnahmeGestartet,
    placeholder: "optional — wofür ist diese Sequenz?"}, wzAufnahmeBeschreibung);
  notiz.addEventListener("input", () => { wzAufnahmeBeschreibung = notiz.value; });
  formular.append(
    el("label", {class: "feld"}, "Name", name),
    el("label", {class: "feld"}, "Zyklen · 0 = endlos", zyklen),
    el("label", {class: "feld wz-aufnahme-notiz"}, "Notiz", notiz));
  raus.push(formular);

  const stand = el("div", {class: "wz-aufnahme-stand" +
    (wzAufnahmeGestartet ? " laeuft" : "")},
    el("span", {class: "wz-rec-punkt"}),
    el("div", {}, el("b", {}, wzAufnahmeGestartet ? "Aufnahme läuft" : "Bereit zur Aufnahme"),
      el("span", {}, wzAufnahmeGestartet
        ? "Ins Spiel wechseln. Der Stopp-Knopf und CTRL+ALT+J bauen danach die Blöcke."
        : "Starten, ins Spiel wechseln und den gewünschten Ablauf einmal ausführen.")));
  const aktion = el("button", {
    class: "btn " + (wzAufnahmeGestartet ? "gefahr" : "haupt") + " wz-aufnahme-knopf",
    onclick: wzAufnahmeGestartet ? wzAufnahmeStoppen : wzAufnahmeStarten,
  }, wzAufnahmeGestartet ? "■ Aufnahme stoppen" : "● Aufnahme starten");
  stand.appendChild(aktion);
  raus.push(stand);

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
    setzeStatus({text: "Bitte zuerst einen Namen eingeben.", art: "err"});
    return;
  }
  const antwort = await frage("aufnahme_starten", {
    name: name, zyklen: wzAufnahmeZyklen, beschreibung: wzAufnahmeBeschreibung});
  if (!antwort) return;
  setzeStatus({text: antwort.meldung || "", art: antwort.ok ? "ok" : "err"});
  if (!antwort.ok) return;
  wzAufnahmeName = antwort.name || name;
  wzAufnahmeGestartet = true;
  wzAufnahmeLive = {aktiv: true, pausiert: false, anzahl: 0, ereignisse: []};
  wzAufnahmeBeobachten();
  wzMitteZeichnen();
  wzRechtsZeichnen();
  wzAufnahmeLiveStarten();
}

/** Drei feste Zeilen statt eines wachsenden Logs: neuestes Ereignis unten. */
function wzAufnahmeAusgabeFuellen(ziel) {
  if (!ziel) return;
  const daten = wzAufnahmeLive || {};
  const ereignisse = Array.isArray(daten.ereignisse) ? daten.ereignisse.slice(-3) : [];
  const kopftext = daten.pausiert ? "PAUSIERT" : wzAufnahmeGestartet ? "LIVE" : "LETZTE EREIGNISSE";
  ziel.replaceChildren(el("div", {class: "wz-ausgabe-kopf"},
    el("span", {}, kopftext),
    el("span", {class: "wz-ausgabe-zaehler"}, String(daten.anzahl || 0) + " Ereignisse")));
  const zeilen = el("div", {class: "wz-ausgabe-zeilen"});
  if (!ereignisse.length) {
    zeilen.appendChild(el("div", {class: "wz-ausgabe-leer"},
      wzAufnahmeGestartet ? "Warte auf das erste Ereignis …" : "Noch nichts aufgenommen."));
  } else {
    ereignisse.forEach((e, i) => {
      const farbe = e.farbe
        ? el("span", {class: "wz-ausgabe-farbe",
            style: "color:rgb(" + e.farbe.join(",") + ")"}, "█") : null;
      zeilen.appendChild(el("div", {class: "wz-ausgabe-zeile" +
          (i === ereignisse.length - 1 ? " neu" : "")},
        el("span", {class: "wz-ausgabe-nr"}, String(e.nummer || "")),
        el("span", {class: "wz-ausgabe-text"}, e.text || "—"),
        el("span", {class: "wz-ausgabe-zeit"}, e.zeit || ""),
        el("span", {class: "wz-ausgabe-farbtext"}, farbe, e.farbtext || "")));
    });
  }
  ziel.appendChild(zeilen);
}

function wzAufnahmeLiveStarten() {
  const nummer = ++wzAufnahmeLivePoll;
  const lesen = async () => {
    if (nummer !== wzAufnahmeLivePoll || !wzAufnahmeGestartet) return;
    const status = await frage("aufnahme_status");
    if (status) {
      wzAufnahmeLive = status;
      wzAufnahmeAusgabeFuellen($("wz-aufnahme-ausgabe"));
    }
    setTimeout(lesen, 300);
  };
  setTimeout(lesen, 150);
}

async function wzAufnahmeStoppen() {
  const antwort = await frage("aufnahme_stoppen");
  if (!antwort) return;
  setzeStatus({text: antwort.meldung || "", art: antwort.ok ? "ok" : "err"});
  if (antwort.ok) wzAufnahmeBeobachten(true);
}

/** Findet die vom Hauptprozess gespeicherte Datei und öffnet ihre fertigen Blöcke. */
function wzAufnahmeBeobachten(schnell = false) {
  const nummer = ++wzAufnahmePoll;
  let versuche = 0;
  const pruefen = async () => {
    if (nummer !== wzAufnahmePoll || !wzAufnahmeGestartet) return;
    const liste = (await frage("sequenz_liste")) || [];
    if (liste.some(s => s.name === wzAufnahmeName)) {
      wzAufnahmeGestartet = false;
      ++wzAufnahmeLivePoll;
      await ruf("laden", {name: wzAufnahmeName});
      setzeAnsicht("editor");
      setzeStatus({text: "Aufnahme gespeichert — die erzeugten Blöcke sind geöffnet.", art: "ok"});
      return;
    }
    versuche += 1;
    if (schnell && versuche >= 12) {
      wzAufnahmeGestartet = false;
      ++wzAufnahmeLivePoll;
      wzMitteZeichnen();
      setzeStatus({text: "Keine gespeicherte Aufnahme gefunden — wurde etwas aufgezeichnet?", art: "warn"});
      return;
    }
    setTimeout(pruefen, schnell ? 350 : 1000);
  };
  setTimeout(pruefen, schnell ? 350 : 1000);
}

function wzKennzahl(wert, label, art) {
  return el("div", {class: "wz-kennzahl " + art},
    el("strong", {}, wert), el("span", {}, label));
}

function wzBefund(b, stufe) {
  const kasten = el("div", {class: "wz-befund " + stufe});
  kasten.appendChild(el("div", {class: "wz-befund-icon"}, wzIcon(stufe)));
  const copy = el("div", {class: "wz-befund-copy"},
    el("div", {class: "wz-bereich"}, b.bereich), el("div", {}, b.text));
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
    for (const b of wzBericht.geprueft)
      liste.appendChild(el("div", {class: "wz-geprueft"}, wzIcon("ok"), el("span", {}, b)));
  }
  return [kopf, liste];
}

async function wzPruefen() {
  setzeStatus({text: "Prüfe…", art: "info"});
  wzBericht = await frage("werkzeug_pruefen");
  if (!wzBericht) return;
  const n = wzBericht.fehler || 0, h = wzBericht.hinweise || 0;
  setzeStatus({
    text: !wzBericht.ok ? (wzBericht.meldung || "Prüfung fehlgeschlagen.")
        : (n || h) ? n + " Fehler, " + h + " Hinweis(e)."
        : "Alles in Ordnung.",
    art: !wzBericht.ok || n ? "err" : h ? "warn" : "ok",
  });
  wzMitteZeichnen();
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

  if (!W || !W.punkte.length) {
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
    const werte = el("div", {class: "wz-kennzahlen"},
      wzKennzahl(wzVorz(v.x), "X-Versatz", "neutral"),
      wzKennzahl(wzVorz(v.y), "Y-Versatz", "neutral"));
    if (K.skalierung && (K.skalierung.x !== 1 || K.skalierung.y !== 1))
      werte.appendChild(wzKennzahl(K.skalierung.x + "×" + K.skalierung.y,
        "Skalierung X/Y", "hinweis"));
    raus.push(werte);
    raus.push(wzVersatzFelder(v));
    if (K.identitaet)
      raus.push(el("p", {class: "art-warn"},
        "Der Transform ändert nichts — der Punkt sitzt schon richtig."));
    raus.push(wzUmfangKasten());
    const leiste = el("div", {style: "display:flex;gap:8px;margin-top:14px"});
    leiste.appendChild(el("button", {
      class: "btn haupt", disabled: !!K.identitaet,
      onclick: () => rufWerkzeug("kalib_anwenden", {...wzUmfang}),
    }, "Umrechnen und speichern"));
    leiste.appendChild(el("button", {
      class: "btn", onclick: () => rufWerkzeug("kalib_abbrechen"),
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
  kasten.appendChild(el("div", {class: "art-warn"}, f.meldung));
  const reihe = el("div", {class: "wz-farbreihe"});
  reihe.append(el("span", {class: "hint"}, "gespeichert"), wzFarbe(f.erwartet),
               el("span", {class: "hint"}, "dort gemessen"), wzFarbe(f.gemessen),
               el("span", {class: "hint"},
                  "(" + f.stelle[0] + ", " + f.stelle[1] + ")"));
  kasten.appendChild(reihe);
  const leiste = el("div", {style: "display:flex;gap:8px"});
  leiste.appendChild(el("button", {
    class: "btn", onclick: async () => {
      const n = f.nummer, id = f.punkt_id;
      wzFarbfrage = null;
      // Auch „Trotzdem setzen" misst die Stelle NEU — kalib_referenz wartet
      // in jedem Fall auf ENTER. Ohne den Hinweis sieht der Knopf aus, als
      // habe er nichts getan.
      await mitWarten("werkzeug", "kalib_referenz",
                      {nummer: n, punkt_id: id, bestaetigt: true});
    },
  }, "Trotzdem setzen"));
  leiste.appendChild(el("button", {
    class: "btn haupt", onclick: () => {
      wzFarbfrage = null;
      setzeStatus({text: "Verworfen — nichts gesetzt.", art: "info"});
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
  let beste = W.punkte[0], weit = -1;
  for (const p of W.punkte) {
    if (ref1 && p.id === ref1.punkt_id) continue;
    const d = Math.hypot(p.x - (ref1 ? ref1.alt[0] : 0), p.y - (ref1 ? ref1.alt[1] : 0));
    if (d > weit) { weit = d; beste = p; }
  }
  return beste.id;
}

/** Eine Referenzpunkt-Zeile: welchen Punkt, und der Knopf zum Anfahren. */
function wzRefZeile(nummer, gesetzt) {
  const kasten = el("div", {class: "wz-ref"});
  kasten.appendChild(el("div", {class: "wz-bereich"},
    nummer === 1 ? "1. Referenzpunkt (Verschiebung)"
                 : "2. Referenzpunkt (Skalierung, optional)"));
  const wahl = el("select");
  for (const p of W.punkte)
    wahl.appendChild(el("option", {value: String(p.id)},
      "#" + p.id + " " + p.name + " (" + p.x + ", " + p.y + ")"));
  if (gesetzt) wahl.value = String(gesetzt.punkt_id);
  // Der zweite Punkt soll WEIT weg vom ersten liegen — genau das steht als
  // Hinweis darueber. Der erste Eintrag der Liste ist aber der erste Punkt
  // selbst, und den lehnt die Bruecke ab: ein Vorschlag, der garantiert eine
  // Fehlermeldung ergibt, ist schlimmer als gar keiner.
  else if (nummer === 2) wahl.value = String(wzWeitesterPunkt(W.kalibrierung.ref1));
  kasten.appendChild(wahl);
  kasten.appendChild(el("button", {
    class: "btn",
    onclick: async () => {
      setzeStatus({text: "Maus auf die Stelle, dann ENTER (ESC bricht ab)…", art: "info"});
      const antwort = await mitWarten("frage", "kalib_referenz",
        {nummer, punkt_id: Number(wahl.value)});
      // Die Farbe passt nicht: nachfragen statt setzen. Ein Referenzpunkt, der
      // danebenliegt, verschiebt nicht sich selbst, sondern ALLES.
      if (antwort && antwort.bestaetigen) { wzFarbfrage = {...antwort, nummer}; }
      else if (antwort && antwort.meldung)
        setzeStatus({text: antwort.meldung, art: antwort.ok ? "ok" : "err"});
      await zeichneWerkzeuge();
    },
  }, gesetzt ? "Neu anfahren" : "Stelle anfahren"));
  if (wzFarbfrage && wzFarbfrage.nummer === nummer)
    kasten.appendChild(wzFarbfrageBauen());
  if (gesetzt)
    kasten.appendChild(el("div", {class: "hint"},
      "(" + gesetzt.alt[0] + ", " + gesetzt.alt[1] + ") → ("
      + gesetzt.neu[0] + ", " + gesetzt.neu[1] + ")"));
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
    class: "btn", onclick: () => rufWerkzeug("kalib_versatz",
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
    const zeile = el("label", {class: "teilen-zeile an"});
    const box = el("input", {type: "checkbox"});
    box.checked = !!wzUmfang[u.schluessel];
    box.addEventListener("change", () => { wzUmfang[u.schluessel] = box.checked; });
    zeile.append(box, el("span", {}, u.text));
    kasten.appendChild(zeile);
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
 * Grund fuer `nachklick_verlauf`: beide aendern nichts, aber nur einer heisst
 * „ich habe hingesehen". */
const WZ_NK_ART = {
  passt: ["✓", "nk-passt", "bestätigt — bleibt, wo er ist"],
  gesetzt: ["→", "nk-gesetzt", "neu gesetzt"],
  uebersprungen: ["↷", "nk-skip", "übersprungen"],
  fehlt: ["✕", "nk-fehlt", "Punkt gibt es nicht mehr"],
};

/** Der Live-Stand der Runde: wo sie steht, was dran ist, was war. */
function wzNachklickAusgabeFuellen(ziel) {
  if (!ziel) return;
  const d = wzNachklickLive || {};
  const gesamt = d.gesamt || 0;
  const fertig = Math.min(d.index || 0, gesamt);
  const laeuft = !!d.aktiv && !d.verwaist;

  // Der Kopf beantwortet die erste Frage („laeuft das ueberhaupt noch?"), und
  // ein verwaister Stand sagt es, statt eine tote Runde als lebend zu zeigen.
  const kopftext = d.verwaist ? "KEIN HAUPTPROZESS"
    : d.pausiert ? "PAUSIERT" : laeuft ? "LÄUFT" : gesamt ? "BEENDET" : "NICHT GESTARTET";
  ziel.replaceChildren(el("div", {class: "wz-ausgabe-kopf"},
    el("span", {}, kopftext),
    el("span", {class: "wz-ausgabe-zaehler"},
      gesamt ? fertig + " von " + gesamt + " Punkt(en)" : "—")));

  if (!gesamt) {
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
               style: "width:" + Math.round(fertig / gesamt * 100) + "%"})));

  // Der aktuelle Punkt ist die Antwort auf „was macht das Programm gerade".
  const p = d.punkt || {};
  if (laeuft && p.id !== undefined) {
    ziel.appendChild(el("div", {class: "nk-jetzt"},
      el("span", {class: "nk-jetzt-marke"}, "jetzt"),
      el("span", {class: "zahl"}, "#" + p.id),
      el("span", {class: "nk-jetzt-name"}, p.name || ""),
      el("span", {class: "nk-jetzt-pos"}, "(" + p.x + ", " + p.y + ")"),
      p.farbe ? el("span", {class: "wz-ausgabe-farbe",
                            style: "color:rgb(" + p.farbe.join(",") + ")"}, "█") : null));
    ziel.appendChild(el("div", {class: "hint nk-hinweis"}, d.pausiert
      ? "Pausiert — Klicks setzen keinen Punkt. CTRL+ALT+H macht weiter."
      : "Der Zeiger steht schon dort. Stimmt die Stelle — klicken. Sonst "
        + "hinfahren und dort klicken."));
  } else if (!laeuft && gesamt) {
    ziel.appendChild(el("div", {class: "hint nk-hinweis"},
      (d.geaendert || 0) + " Stelle(n) geändert. Was davon geschrieben wurde, "
      + "hängt daran, ob übernommen oder verworfen wurde."));
  }

  // Der Verlauf laeuft rueckwaerts: das Letzte ist das, was man sucht.
  const verlauf = Array.isArray(d.verlauf) ? d.verlauf.slice(-6).reverse() : [];
  const zeilen = el("div", {class: "wz-ausgabe-zeilen"});
  if (!verlauf.length) {
    zeilen.appendChild(el("div", {class: "wz-ausgabe-leer"},
      "Noch kein Punkt erledigt."));
  } else {
    for (const v of verlauf) {
      const [zeichen, klasse, was] = WZ_NK_ART[v.art] || ["·", "", v.art];
      zeilen.appendChild(el("div", {class: "nk-zeile"},
        el("span", {class: "nk-art " + klasse, title: was}, zeichen),
        el("span", {class: "zahl"}, "#" + v.id),
        el("span", {class: "nk-name"}, v.name || ""),
        el("span", {class: "nk-wohin"}, v.alt && v.neu
          ? "(" + v.alt[0] + ", " + v.alt[1] + ") → (" + v.neu[0] + ", " + v.neu[1] + ")"
          : was)));
    }
  }
  ziel.appendChild(zeilen);
  if (d.sonstige)
    ziel.appendChild(el("div", {class: "hint nk-hinweis"},
      d.sonstige + " Stelle(n) erreicht die Runde nicht (beobachtete Pixel, "
      + "ELSE, Rad) — dafür bleibt walk im Punkte-Menü."));
}

/* Gepollt wird, solange der Reiter offen ist — nicht nur nach dem eigenen
 * Startknopf. Die Runde kann aus dem Punkte-Menue gestartet worden sein, und
 * dann ist dieses Fenster trotzdem der bequemere Platz, um ihr zuzusehen.
 * Nach dem Ende laeuft der Poll aus (`ruhig`), damit ein offener Reiter nicht
 * dauerhaft alle 400 ms eine Datei liest. */
function wzNachklickLiveStarten() {
  const nummer = ++wzNachklickPoll;
  let ruhig = 0;
  const lesen = async () => {
    if (nummer !== wzNachklickPoll || wzOffen !== "klicken") return;
    const stand = await frage("nachklick_status");
    if (nummer !== wzNachklickPoll || wzOffen !== "klicken") return;
    if (stand) {
      const lief = wzNachklickLive.aktiv;
      wzNachklickLive = stand;
      wzNachklickAusgabeFuellen($("wz-nachklick-ausgabe"));
      // Endet die Runde, sagt es die Statuszeile — sonst merkt man es nur,
      // wenn man gerade hinsieht.
      if (lief && !stand.aktiv)
        setzeStatus({text: "Klick-Runde beendet — " + (stand.geaendert || 0)
                     + " Stelle(n) geändert.", art: "ok"});
      ruhig = stand.aktiv ? 0 : ruhig + 1;
    } else {
      ruhig += 1;
    }
    if (ruhig > 12) return;
    setTimeout(lesen, wzNachklickLive.aktiv ? 400 : 1000);
  };
  setTimeout(lesen, 100);
}

function wzKlickenBauen() {
  const raus = [wzKopf("klicken", "Punkte nachklicken",
    "Eine geführte Kontrollrunde durch alle Klickstellen der geöffneten Sequenz.")];
  raus.push(wzBezug("klicken"));

  const schritte = el("div", {class: "wz-schritte"});
  WZ_SCHRITTE.forEach(([titel, text], i) => {
    schritte.append(el("div", {class: "wz-nummer"}, String(i + 1)),
      el("div", {class: "wz-schritt-text"}, el("b", {}, titel + ": "), text));
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
    class: "btn haupt", onclick: () => rufWerkzeug("nachklick_starten"),
    title: "Startet die Runde im Hauptprozess — geklickt wird danach im Spiel",
  }, "Runde starten"));
  // Zwei Ausgaenge, weil es zwei Absichten gibt. Ein einzelner „Beenden"-Knopf
  // muesste sich fuer eine entscheiden und laege in der Haelfte der Faelle
  // falsch. Ob gerade eine Runde laeuft, weiss dieses Fenster nicht (der Zustand
  // liegt drueben) - die Knoepfe stehen deshalb immer da, und der Hauptprozess
  // sagt, was er vorgefunden hat.
  leiste.appendChild(el("button", {
    class: "btn", onclick: () => rufWerkzeug("nachklick_beenden"),
    title: "Schreibt die gesetzten Stellen nach sequence.json (= CTRL+ALT+J)",
  }, "Übernehmen"));
  leiste.appendChild(el("button", {
    class: "btn", onclick: () => rufWerkzeug("nachklick_beenden", {verwerfen: true}),
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
  if (wzOffen === "punkte") {
    const punkt = W && W.punkte.find(p => p.id === wzPunktId);
    const kopf = el("div", {class: "abschnitt"},
      el("span", {class: "ueberschrift"}, "VERWENDUNGEN"),
      el("span", {class: "hint"}, punkt ? "Punkt #" + punkt.id : "kein Punkt gewählt"));
    const liste = el("div", {class: "abschnitt wachsend", style: "gap:5px"});
    if (!punkt || !punkt.verwendungen.length)
      liste.appendChild(el("p", {class: "hinweis"}, "Dieser Punkt wird nirgends verwendet und kann sicher gelöscht werden."));
    else for (const v of punkt.verwendungen)
      liste.appendChild(el("div", {class: "wz-geprueft"}, wzIcon("punkte"), el("span", {}, v)));
    return ziel.replaceChildren(kopf, liste);
  }
  if (wzOffen === "farben")
    return ziel.replaceChildren(el("div", {class: "abschnitt"},
      el("span", {class: "ueberschrift"}, "MESSUNG"),
      el("p", {class: "hinweis"}, wzFarbAnalyse && wzFarbAnalyse.ok
        ? (wzFarbAnalyse.meldung || "Analyse abgeschlossen.")
        : "Noch keine Analyse. Die Farbfelder erscheinen nach der Aufnahme in der Mitte.")));
  if (wzOffen === "klicken")
    return ziel.replaceChildren(el("div", {class: "abschnitt"},
      wzInfo("Was die Runde nicht erreicht",
        "Beobachtete Pixel, Nachprüfungen, ELSE-Klicks und Rad-Schritte kommen "
        + "in einem normalen Durchlauf gar nicht vor. Dafür bleibt walk im "
        + "Punkte-Menü. Welche das sind, sagt die Runde beim Start in der Konsole.")));
  if (!W || !W.kalibrierung.ref1)
    return ziel.replaceChildren(el("div", {class: "abschnitt"},
      el("span", {class: "ueberschrift"}, "VORSCHAU"),
      el("div", {class: "hint", style: "white-space:normal"},
        "Sobald der erste Referenzpunkt steht, steht hier, was sich ändern würde.")));

  const zeilen = W.kalibrierung.vorschau || [];
  const kopf = el("div", {class: "abschnitt"},
    el("span", {class: "ueberschrift"}, "VORSCHAU"),
    el("div", {class: "hint"}, zeilen.length + " Stelle(n), Auszug"));
  const liste = el("div", {class: "abschnitt wachsend", style: "gap:4px"});
  for (const z of zeilen) {
    liste.appendChild(el("div", {class: "wz-vorschau"},
      el("div", {}, z.was),
      el("div", {class: "hint"},
        "(" + z.vorher.join(", ") + ") → (" + z.nachher.join(", ") + ")")));
  }
  if (!zeilen.length)
    liste.appendChild(el("div", {class: "hint"}, "Nichts, was sich ändern würde."));
  ziel.replaceChildren(kopf, liste);
}

/* Der Reiter bearbeitet `config.json` — eine ANDERE Datei als der Editor, also
 * liegt sein Zustand neben `S`: `C` ist die Antwort von `config_lesen()`,
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
  const antwort = await mitWarten("frage", "maus_stelle");
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
  $("btn-aufnahme").addEventListener("click", () => wzOeffnen("aufnahme"));
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
  $("scan-name").addEventListener("change", (e) => {
    if (!SC || !SC.offen) return;
    rufScan("scan_setzen", {name: SC.offen, feld: "name", wert: e.target.value});
  });
  $("scan-name").addEventListener("keydown", (e) => {
    if (e.key === "Enter") e.target.blur();
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
    rufScan("scan_modus_setzen", {modus: "finden", art: scanArt}));
  $("scan-slot-neu").addEventListener("click", () =>
    rufScan("scan_modus_setzen", {modus: "slot", art: scanArt}));
  $("scan-test").addEventListener("click", () => rufScan("scan_erkennen"));
  $("scan-lernen").addEventListener("click", () =>
    rufScan("scan_lernvorschau", {scope: "alle"}));
  document.querySelectorAll("[data-scan-tool]").forEach((knopf) =>
    knopf.addEventListener("click", () =>
      rufScan("scan_modus_setzen", {modus: knopf.dataset.scanTool, art: scanArt})));
  $("scan-pin").addEventListener("click", () =>
    rufScan("scan_modus_setzen", {modus: SC.modus, art: scanArt,
                                   fixiert: !SC.werkzeug_fixiert}));
  $("scan-foto").addEventListener("click", () => rufScan("scan_foto", {art: scanArt}));
  $("scan-vollbild").addEventListener("click", () =>
    rufScan("scan_bereich_setzen", {art: scanArt}));
  $("scan-aufziehen").addEventListener("click",
    () => rufScan("scan_modus_setzen", {modus: "bereich", art: scanArt}));
  $("scan-fenster-neu").addEventListener("click", scanFensterPflegen);
  $("scan-fenster").addEventListener("change", (e) => {
    const wahl = scanFenster[Number(e.target.value)];
    // Waehlen nimmt NICHT auf — das tut der Knopf darueber. Vorher stand hier
    // beides in einem Griff, und dann sah es aus, als handele die Liste von
    // selbst und der Knopf gar nicht (er holte dasselbe Bild noch einmal).
    if (wahl) rufScan("scan_bereich_setzen",
      {art: scanArt, bereich: wahl.bereich, fenster: wahl.id});
    else rufScan("scan_bereich_setzen", {art: scanArt});
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
  const buehne = $("scan-buehne");
  flaeche.addEventListener("click", (e) => {
    // Ein Klick, der ein Ziehen beendet hat, ist kein Klick. Ohne das waehlte
    // das Loslassen den Slot gleich noch einmal neu aus.
    if (scanZiehGemacht) { scanZiehGemacht = false; return; }
    const stelle = scanStelleAusEvent(e);
    if (!stelle) return;
    // ALT misst den Hintergrund des Slots unter dem Zeiger — ohne den Umweg
    // ueber die Modus-Kachel. Der haeufigste Handgriff nach dem Finden.
    if (e.altKey) return rufScan("scan_direkt", {x: stelle[0], y: stelle[1],
                                                 was: "messen", art: scanArt});
    // STRG nimmt einen einzelnen Slot zur Auswahl dazu oder heraus — dieselbe
    // Geste wie im Sequenz-Editor.
    rufScan("scan_klick", {x: stelle[0], y: stelle[1], art: scanArt,
                           zusatz: e.ctrlKey || e.metaKey});
  });
  // Beim automatischen Finden darf eine Ecke auch im freien Teil der MITTLEREN
  // Buehne liegen. Der Helfer klemmt sie an den Bildrand; die Seitenleisten
  // liegen ausserhalb dieses Elements und koennen die Geste nie ausloesen.
  buehne.addEventListener("click", (e) => {
    const stelle = scanSuchStelleAusBuehne(e);
    if (stelle) rufScan("scan_klick", {x: stelle[0], y: stelle[1], art: scanArt});
  });
  flaeche.addEventListener("dblclick", (e) => {
    const stelle = scanStelleAusEvent(e);
    if (stelle) rufScan("scan_direkt",
      {x: stelle[0], y: stelle[1], was: "klick", art: scanArt});
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
  buehne.addEventListener("mousemove", (e) => {
    if (!SC || !SC.ecke || SC.modus !== "finden") return;
    const stelle = scanSuchStelleAusBuehne(e);
    if (!stelle) return;
    scanZeiger = stelle;
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
    if (gewaehltePhase !== null) {
      gewaehltePhase = null;
      return zeichnePhasen();
    }
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
      if (modus) { e.preventDefault(); return rufScan("scan_modus_setzen",
        {modus: modus.key, art: scanArt}); }
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
  if (e.key === "Delete" && gewaehltePhase !== null) {
    e.preventDefault();
    const phase = gewaehltePhase;
    gewaehltePhase = null;
    return ruf("phase_loeschen", {phase: phase});
  }
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
