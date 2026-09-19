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
const PRESENCE_ONLY = new Set(["disabled", "checked", "hidden", "readonly",
                            "required", "selected", "multiple", "open"]);

function el(tag, attrs, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (PRESENCE_ONLY.has(k) && !v) continue;
    if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "style") n.setAttribute("style", v);
    else if (k === "text") n.textContent = v;
    else if (v === true) n.setAttribute(k, "");
    else n.setAttribute(k, v);
  }
  for (const kind of children.flat()) {
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
const openHelps = new Set();

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
  const image = svgEl("svg", {class: "info-glyph", viewBox: "0 0 16 16",
    "aria-hidden": "true"});
  image.append(
    svgEl("circle", {cx: "8", cy: "8", r: "6.5", fill: "none",
      stroke: "currentColor", "stroke-width": "1"}),
    svgEl("circle", {cx: "8", cy: "5", r: ".8", fill: "currentColor"}),
    svgEl("path", {d: "M8 7.5v4", fill: "none", stroke: "currentColor",
      "stroke-width": "1.3", "stroke-linecap": "round"}));
  const glyph = el("span", {class: "info", "data-hilfe": key || text}, image);
  glyph._text = text;
  glyph.addEventListener("click", (e) => {
    // Das ⓘ steckt in einem <label>; ohne das hier wuerde der Klick das Feld
    // fokussieren bzw. den Schalter umlegen.
    e.preventDefault();
    e.stopPropagation();
    const helpId = glyph.getAttribute("data-hilfe");
    if (openHelps.has(helpId)) openHelps.delete(helpId);
    else openHelps.add(helpId);
    renderHelp(glyph);
  });
  return glyph;
}

/** Bringt EIN ⓘ auf den Stand von `openHelps` — auf- oder zugeklappt. */
function renderHelp(glyph) {
  const open = openHelps.has(glyph.getAttribute("data-hilfe"));
  const host = glyph.closest("label") || glyph.parentNode;
  const sibling = host.nextElementSibling;
  const present = sibling && sibling.classList.contains("help-text") ? sibling : null;
  glyph.classList.toggle("on", open);
  if (open && !present) {
    host.parentNode.insertBefore(el("p", {class: "hint help-text"}, glyph._text),
                                 host.nextSibling);
  } else if (!open && present) {
    present.remove();
  }
}

/** Nach dem Neuaufbau: alles wieder aufklappen, was aufgeklappt war. */
function applyHelps(root) {
  for (const glyph of root.querySelectorAll(".info")) renderHelp(glyph);
}

/** Beschriftung, ggf. mit ⓘ dahinter. */
function labeled(text, help, key) {
  return help ? el("span", {class: "with-info"}, text, info(help, key)) : text;
}

function field(caption, value, onSet, extra, help, key) {
  const inputEl = el("input", Object.assign({value: value === null || value === undefined ? "" : value,
                                             autocomplete: "off"}, extra || {}));
  inputEl.addEventListener("change", () => onSet(inputEl.value));
  inputEl.addEventListener("keydown", (e) => { if (e.key === "Enter") inputEl.blur(); });
  return el("label", {class: "field"}, labeled(caption, help, key), inputEl);
}

/** Kategorie als echtes Kombinationsfeld: vorhandene Namen lassen sich aus der
 *  Browser-Liste anklicken, das Feld bleibt aber frei beschreibbar. Ein <select>
 *  waere hier zu streng, weil neue Kategorien ohne einen zweiten Bedienweg
 *  angelegt werden koennen sollen. */
function categoryValues(zusatz) {
  const values = [];
  const seen = new Set();
  for (const raw of SC.categories.concat(zusatz || [])) {
    const value = String(raw || "").trim();
    const key = value.toLocaleLowerCase("de");
    if (value && !seen.has(key)) {
      seen.add(key);
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
const CATEGORY_NEW = "\u0000neu";   // als Kategoriename nicht eingebbar

/* Welche Kategorie-Felder gerade im Tippen stehen — als Schluessel, nicht als
 * DOM-Verweis. Der Modus muss den Neuaufbau ueberleben: der Entwurf speichert
 * 900 ms nach der letzten Aenderung, und das Feld wuerde sonst mitten im Wort
 * wieder zur Auswahlliste. Dieselbe Mechanik wie `openHelps` und `collapsed`. */
const categoryFree = new Set();

/** Was in der Lern-Vorschau schon getippt, aber noch nicht uebernommen ist.
 *
 * Eine Kategorie, die in Zeile 1 entsteht, muss in Zeile 2 waehlbar sein —
 * sonst tippt man sie zwanzigmal und beim einundzwanzigsten Mal anders. */
function categoryNote() {
  return [...document.querySelectorAll(".category-chooser")]
    .map((n) => (n.value ? n.value() : "")).filter(Boolean);
}

/** Zieht die Auswahllisten aller Kategorie-Bedienelemente nach. */
function refreshCategoryOptions() {
  for (const n of document.querySelectorAll(".category-chooser")) {
    if (n.optionenNeu) n.optionenNeu();
  }
}

function categoryChooser(value, onSet, opts) {
  opts = opts || {};
  const wrapper = el("span", {class: "category-chooser"
    + (opts.cls ? " " + opts.cls : "")});
  // Woran der Tipp-Modus haengt. Ohne Schluessel gibt es ihn nicht — dann
  // entscheidet allein, ob es etwas zu waehlen gibt.
  const key = opts.key || "";
  let current = String(value || "");
  let locked = false;

  const values = () => categoryValues(categoryNote().concat(current));
  const add_finding = (v) => {
    current = v;
    // Ein uebernommener Name steht beim naechsten Aufbau in der Liste — also
    // ist das Tippen hier zu Ende. Bleibt das Feld leer, bleibt es offen:
    // sonst waere ein Vertipper („Enter" auf nichts) ein Rueckwurf in die
    // Auswahl, und man faengt von vorn an.
    if (key && v) categoryFree.delete(key);
    onSet(v);
  };

  const selectEl = () => {
    const s = el("select", {title: opts.title
      || "Vorhandene Kategorie wählen — oder unten eine neue anlegen"});
    s.rebuildOptions = () => {
      const alt = current;
      s.replaceChildren(
        el("option", {value: ""}, opts.empty || "— ohne Kategorie —"),
        ...values().map((k) => el("option", {value: k}, k)),
        el("option", {value: CATEGORY_NEW}, "＋ neue Kategorie …"));
      s.value = alt;
    };
    s.rebuildOptions();
    s.addEventListener("change", () => {
      if (s.value === CATEGORY_NEW) return swap(true, "");
      add_finding(s.value);
    });
    return s;
  };

  const textEl = (default_value) => {
    const e = el("input", {value: default_value, autocomplete: "off",
      placeholder: opts.placeholder || "Neue Kategorie",
      title: "Neuen Namen tippen — beim nächsten Item steht er in der Liste"});
    e.addEventListener("change", () => add_finding(e.value.trim()));
    e.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") e.blur();
      // ESC fuehrt zurueck in die Liste, sonst waere das Tippen eine Falltuer:
      // hinein kommt man mit einem Klick, heraus nur ueber einen Umweg.
      if (ev.key === "Escape" && values().length) { ev.stopPropagation(); swap(false); }
    });
    return e;
  };

  function swap(free, default_value, remember) {
    if (key && remember !== false) {
      if (free) categoryFree.add(key);
      else categoryFree.delete(key);
    }
    const neu = free ? textEl(default_value === undefined ? current : default_value)
                     : selectEl();
    neu.disabled = locked;
    wrapper.replaceChildren(neu);
    wrapper.value = () => (free ? neu.value.trim() : neu.value);
    wrapper.optionenNeu = free ? null : neu.rebuildOptions;
    if (free && remember !== false) neu.focus();
  }

  // **Getippt wird nur, wenn es nichts zu waehlen gibt** — oder wenn der
  // aktuelle Wert (ein Vorschlag der Lern-Vorschau) noch in keiner Liste steht,
  // oder wenn hier vor dem Neuaufbau schon getippt wurde.
  const presentNames = categoryValues(categoryNote());
  swap(!presentNames.length
          || (key && categoryFree.has(key))
          || (!!current && !presentNames.some((k) => k === current)),
          undefined, false);
  wrapper.lock = (on) => {
    locked = on;
    for (const n of wrapper.children) n.disabled = on;
  };
  wrapper.locked = () => locked;
  // Von aussen setzen (Sammel-Aktion der Lern-Vorschau). Steht der Wert nicht
  // in der Liste, muss das Feld dafuer ins Tippen wechseln — sonst schluckt
  // ein <select> ihn stillschweigend.
  wrapper.set_value = (v) => {
    current = String(v || "");
    const present = categoryValues(categoryNote());
    swap(!!current && !present.some((k) => k === current), current);
    if (wrapper.optionenNeu) wrapper.optionenNeu();
    onSet(current);
  };
  return wrapper;
}

function itemsOfCategory(category) {
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
 * auf hundert Kacheln auf: ueber `PRIO_MAX_SHOW` bleiben nur die belegten. */
const PRIO_MAX_SHOW = 24;

function priorityAllocation(category) {
  const items = itemsOfCategory(category);
  const taken = new Map();
  for (const i of items) {
    if (!taken.has(i.priority)) taken.set(i.priority, []);
    taken.get(i.priority).push(i.name);
  }
  const highestRank = items.length ? Math.max(...items.map((i) => i.priority)) : 0;
  if (highestRank + 1 > PRIO_MAX_SHOW) {
    const ranks = [...taken.keys()].sort((a, b) => a - b);
    // Der naechste freie gehoert dazu — sonst nennt die Uebersicht keinen,
    // und genau den sucht man.
    let free = 1;
    while (taken.has(free)) free += 1;
    if (!ranks.includes(free)) ranks.push(free);
    ranks.sort((a, b) => a - b);
    return ranks.map((p) => ({rank: p, names: taken.get(p) || []}));
  }
  const alle = [];
  for (let p = 1; p <= highestRank + 1; p += 1) alle.push({rank: p, names: taken.get(p) || []});
  return alle;
}

/** Die Prioritaet, die dieses Item bekaeme, wenn niemand etwas einstellt:
 *  der erste freie Rang seiner Kategorie. */
function nextFreePriority(category, exceptName) {
  const assigned = new Set(itemsOfCategory(category)
    .filter((i) => i.name !== exceptName).map((i) => i.priority));
  let p = 1;
  while (assigned.has(p)) p += 1;
  return p;
}

/** Teilt sich dieses Item seinen Rang mit einem anderen seiner Kategorie? */
function priorityDuplicate(item) {
  if (!item.category) return [];
  return itemsOfCategory(item.category)
    .filter((i) => i.name !== item.name && i.priority === item.priority)
    .map((i) => i.name);
}

/** Sichtbare Rangfolge statt einer Zahl ohne Zusammenhang. Prioritaeten gelten
 *  innerhalb einer Kategorie; deshalb waere eine globale Liste irrefuehrend. */
function priorityOverview(category, currentName) {
  if (!category) {
    return el("p", {class: "hint priority-hint"},
      "Ohne Kategorie konkurriert dieses Item mit keinem anderen Item.");
  }
  const allocation = priorityAllocation(category);
  return el("div", {class: "priority-overview"},
    el("span", {class: "small"}, "Rangfolge in „" + category + "“"),
    el("div", {class: "priority-chips"}, allocation.map((r) => {
      const thisOne = r.names.includes(currentName);
      const free = !r.names.length;
      return el("span", {
        // Ein freier Rang ist kein Eintrag, sondern eine Luecke — gestrichelt
        // und ohne Namen. Sonst zaehlt man die vergebenen ab, um ihn zu finden.
        class: "priority-chip" + (thisOne ? " current" : "")
               + (free ? " free" : "") + (r.names.length > 1 ? " duplicate" : ""),
        title: free ? "Priorität " + r.rank + " ist frei"
                    : r.names.join(", ") + " · Priorität " + r.rank
                      + (r.names.length > 1 ? " — doppelt vergeben" : ""),
      }, "P" + r.rank + " · " + (free ? "frei" : r.names.join(", ")));
    })),
    el("small", {class: "input-help"},
      "Kleinere Zahl gewinnt. Zwei Items mit derselben Zahl entscheidet die "
      + "Scan-Reihenfolge — also der Zufall."));
}

function allPriorities() {
  if (!SC.categories.length) return null;
  return el("div", {class: "priorities-all"},
    el("span", {class: "small"}, "Bereits gesetzte Prioritäten"),
    SC.categories.map((k) => el("div", {class: "priorities-category"},
      el("b", {}, k),
      el("span", {}, itemsOfCategory(k).map((i) => "P" + i.priority + " " + i.name).join(" · ")))));
}

/** Noch nicht uebernommene Kategorien gehoeren bereits zur aktuellen Eingabe.
 *  Die Vorschau darf nicht erst nach „Ausgewaehlte uebernehmen" von ihnen
 *  erfahren, sonst muss derselbe freie Text in jeder Zeile neu getippt werden. */
/** Eine in einer Zeile entstandene Kategorie in allen anderen waehlbar machen.
 *
 * Ohne das tippt man dieselbe Kategorie in zwanzig Zeilen — und beim
 * einundzwanzigsten Mal anders. */
function scanReviewRefreshCategories() {
  refreshCategoryOptions();
}

function scanReviewCategoryToSelection(inputEl) {
  const value = inputEl.value();
  if (!value) return;
  for (const row of document.querySelectorAll(".scan-review-row")) {
    const checkbox = row.querySelector(".scan-review-check");
    const category = row.querySelector(".scan-review-category");
    if (checkbox && checkbox.checked && category && !category.locked()) {
      category.set_value(value);
    }
  }
}

function numberField(caption, value, onSet, extra, help, key) {
  return field(caption, value, (v) => onSet(Number(v) || 0),
              Object.assign({type: "number"}, extra || {}), help, key);
}

/** Farbwähler mit Hex daneben. Ohne gemessene Farbe bleibt er leer statt eine
 *  zu behaupten — dieselbe Regel wie beim Quadrat in der Punkte-Palette. */
function color_swatch(caption, hex, onSet, help, key) {
  const choice = el("input", {type: "color", value: hex || "#000000",
                            style: "width:44px;height:28px;padding:2px"});
  const text = el("span", {class: "small mono"}, hex || "keine Farbe aufgenommen");
  choice.addEventListener("change", () => onSet(choice.value.toUpperCase()));
  return el("label", {class: "field"}, labeled(caption, help, key),
    el("div", {class: "row"}, choice, text));
}

/** Ein Schalter — mit ⓘ statt eines Erklaerungsabsatzes darunter.
 *
 * **Erklaerungen gehoeren ins ⓘ, nicht neben das Bedienelement.** Fuenf
 * Absaetze untereinander sind eine Textwand, in der das Bedienelement
 * untergeht; wer die Regel schon kennt, liest sie trotzdem jedes Mal mit. Das
 * ⓘ zeigt sie auf Wunsch, und `openHelps` merkt sich, welche offen sind. */
function toggle(caption, on, onSet, help, key) {
  const box = el("input", {type: "checkbox"});
  box.checked = !!on;
  box.addEventListener("change", () => onSet(box.checked));
  return el("label", {class: "on"}, box, labeled(caption, help, key));
}

function selection(caption, values, current, onSet, help, key) {
  const s = el("select");
  for (const w of values) {
    const o = el("option", {value: String(w.value)}, w.text);
    if (String(w.value) === String(current)) o.selected = true;
    s.appendChild(o);
  }
  s.addEventListener("change", () => onSet(s.value));
  return caption ? el("label", {class: "field"}, labeled(caption, help, key), s) : s;
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
function rememberFocus() {
  // Ein Umbenennen aendert die Identitaet und damit die id. Wer umbenennt, sagt
  // es vorher; hier wird es einmal eingeloest und danach vergessen.
  const renamed = focusRenamed;
  focusRenamed = null;
  const a = document.activeElement;
  if (!a || !["INPUT", "SELECT", "TEXTAREA"].includes(a.tagName)) return null;
  const boxEl = a.closest("[id]");
  if (!boxEl) return null;
  const fields = [...boxEl.querySelectorAll("input, select, textarea")];
  const i = fields.indexOf(a);
  if (i < 0) return null;
  // Zahl- und Farbfelder haben keine Auswahl - dann bleibt nur der Fokus.
  let start = null, end = null;
  try { start = a.selectionStart; end = a.selectionEnd; } catch (e) { /* egal */ }
  const neu = renamed && renamed.fromName === boxEl.id ? renamed.toName : boxEl.id;
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
  return {id: neu, alt: boxEl.id, i: i, start: start, end: end};
}

/** Vor einem Umbenennen: unter welcher id die Maske danach steht. */
function focusRename(fromName, toName) {
  focusRenamed = fromName && toName && fromName !== toName ? {fromName: fromName, toName: toName} : null;
}
let focusRenamed = null;

function restoreFocus(memo) {
  if (!memo) return;
  const boxEl = document.getElementById(memo.id)
              || document.getElementById(memo.alt);
  if (!boxEl) return;
  const target = [...boxEl.querySelectorAll("input, select, textarea")][memo.i];
  if (!target) return;
  target.focus();
  if (memo.start !== null) {
    try { target.setSelectionRange(memo.start, memo.end); } catch (e) { /* egal */ }
  }
}

function segment(values, current, onSet) {
  return el("div", {class: "segment"}, values.map((w) =>
    el("button", {class: w.value === current ? "on" : "", onclick: () => onSet(w.value)},
       w.text)));
}

function heading(text, help, key) {
  return el("span", {class: "heading with-info"}, text, info(help, key));
}

/* -------------------------------------------------------------------- Brücke */

let S = null;             // letzte Momentaufnahme
let drag = null;        // was gerade gezogen wird
let activeDropZone = null;  // hervorgehobene Einfügestelle
let openQuestion = null;
let selectedPhase = null; // Loop-Phase; Entf löscht sie wie eine Block-Auswahl
const openSpecialPhases = new Set(); // leere Start-/Abschlussphasen auf Wunsch

function waitForBridge() {
  return new Promise((done) => {
    if (window.pywebview && window.pywebview.api) return done();
    window.addEventListener("pywebviewready", () => done(), {once: true});
  });
}

/** Ein Befehl an die Brücke. Antwort ist immer die neue Momentaufnahme. */
async function call(name, data_reload) {
  try {
    const answer = await window.pywebview.api[name](data_reload === undefined ? null : data_reload);
    const switched = name === "load" || name === "new";
    if (switched) {
      selectedPhase = null;
      openSpecialPhases.clear();
    }
    adopt(answer);
    // **Der offene Reiter muss dem Wechsel folgen.** Scans, Teilen und
    // Werkzeuge lesen alle aus `sequences/<name>/` — ihre Ansicht haengt aber
    // an eigenem Zustand (`SC`, `T`, `W`), den `render()` nicht anfasst. Seit
    // die Auswahl in JEDEM Reiter steht, kann der Wechsel auch von dort
    // kommen, und dann stuenden dort die Slots, Zahlen und Punkte der VORIGEN
    // Sequenz — mit dem Namen der neuen im Kopf. Genau die Sorte stiller
    // Fehlanzeige, bei der man den Fehler in den Daten sucht.
    //
    // Nur bei einem WIRKLICHEN Wechsel: hat die Bruecke stattdessen nach
    // ungespeicherten Aenderungen gefragt, ist noch gar nichts geladen —
    // `proceed()` kommt danach ohnehin hier vorbei.
    if (switched && S && !S.question && view !== "editor") setView(view);
  } catch (e) {
    setStatus({text: String(e && e.message ? e.message : e), kind: "err"});
  }
}

/** Wie call(), aber die Antwort ersetzt NICHT die Momentaufnahme.
 *
 * Für alles, was gefragt und nicht befohlen wird: Sequenzliste, Laufstatus.
 * Über `call()` geholt würde ihre Antwort in `S` landen und den Editor-Zustand
 * zerschiessen — ein Blick in die Übersicht wäre dann ein Datenverlust. */
async function ask(name, data_reload) {
  try {
    return await window.pywebview.api[name](data_reload === undefined ? null : data_reload);
  } catch (e) {
    setStatus({text: String(e && e.message ? e.message : e), kind: "err"});
    return null;
  }
}

function adopt(neu) {
  if (!neu) return;
  S = neu;
  render();
  if (S.question) showQuestion(S.question);
}

/* ----------------------------------------------------------------- Ansichten */

let view = "editor";

/** Schaltet zwischen Editor, Übersicht und Live-Run um.
 *
 * Reiner Oberflächenzustand: die Brücke erfährt davon nichts, und in der
 * Momentaufnahme steht er auch nicht — er ändert ja nichts an der Sequenz.
 * Der Editor bleibt dabei im Dokument stehen (nur `hidden`), damit
 * Scrollstand und ungespeicherte Eingaben den Ausflug überleben. */
function setView(neu) {
  view = neu;
  for (const t of document.querySelectorAll(".tab"))
    t.classList.toggle("on", t.dataset.view === neu);
  $("editor-body").hidden = neu !== "editor";
  $("view-sequences").hidden = neu !== "sequences";
  $("view-run").hidden = neu !== "lauf";
  $("view-settings").hidden = neu !== "einstellungen";
  $("view-scans").hidden = neu !== "scans";
  $("view-share").hidden = neu !== "teilen";
  $("view-tools").hidden = neu !== "werkzeuge";
  $("view-report").hidden = neu !== "bericht";
  // Die Sequenz-Bedienelemente im Kopf gehoeren nur zur Sequenz. Die anderen
  // Reiter bearbeiten andere Dateien und haben ihren eigenen Knopf.
  for (const n of document.querySelectorAll("[data-sequenz]"))
    n.hidden = ["einstellungen", "scans", "teilen", "werkzeuge",
                "bericht"].includes(neu);
  if (neu === "scans") renderScans(!SC);
  if (neu === "sequences") renderSequenceList();
  if (neu === "teilen") renderShare();
  // Frisch beim Oeffnen: der Bericht der letzten Sitzung beschriebe einen Stand,
  // den es nach einem Speichern nicht mehr gibt.
  if (neu === "werkzeuge") renderTools(true);
  // Bei jedem Oeffnen frisch: waehrend das Fenster offensteht, schreibt ein
  // Lauf im Hauptprozess weiter in dieselbe CSV.
  if (neu === "bericht") renderReport();
  // Bei jedem Oeffnen frisch von Platte: der Hauptprozess schreibt dieselbe
  // Datei (Debug-Stufen, Import, Factory Reset).
  if (neu === "einstellungen") renderSettings(true);
  setRunPolling(neu === "lauf");
}

/* ------------------------------------------------------------------ Zeichnen */

function render() {
  if (!S) return;
  const memo = rememberFocus();
  $("footer-file").textContent = S.file || "";
  $("footer-points").textContent = S.points.length + " Punkte";
  $("dirty-dot").hidden = !S.dirty;
  $("footer-lamp").classList.toggle("open", !!S.dirty);
  $("footer-lamp").title = S.dirty ? "ungespeicherte Änderungen" : "saved";
  // Der Fenstertitel bleibt schlicht: in der Titelleiste steht sonst der
  // Sequenzname doppelt (er steht schon im Kopf der Seite), und das Fenster
  // findet sich in der Taskleiste besser über einen gleichbleibenden Namen.
  document.title = "Sequenz-Studio";
  setStatus(S.status);
  renderHeader();
  renderSequence();
  renderPoints();
  renderPhases();
  renderInspector();
  restoreFocus(memo);
}

/* Wie oft der Status seit Programmstart geschrieben wurde. Ein verzoegerter
 * Schreiber (s. `mailboxFollowUp`) merkt sich den Stand und schweigt,
 * wenn inzwischen jemand anders etwas gemeldet hat — eine zwei Sekunden alte
 * Warnung darf keine frische Meldung begraben. */
let statusStamp = 0;

function setStatus(status) {
  statusStamp += 1;
  const n = $("status");
  n.textContent = (status && status.text) || "";
  // Mit Praefix: „info" allein ist die Klasse des ⓘ-Knopfes (13px, rund), und ein
  // Status mit dieser Art bekam dessen Gestalt — ein leerer Kreis neben dem
  // Start-Knopf, den niemand zuordnen konnte.
  n.className = "status kind-" + ((status && status.kind) || "info");
}

function renderHeader() {
  const s = $("seq-select");
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

function renderSequence() {
  if (document.activeElement !== $("seq-name")) $("seq-name").value = S.name;
  if (document.activeElement !== $("seq-cycles")) $("seq-cycles").value = S.cycles;
  if (document.activeElement !== $("seq-info")) $("seq-info").value = S.description;
  $("seq-blocks").textContent = S.phases.reduce((n, p) => n + p.blocks.length, 0);
}

function renderPoints() {
  const filter = $("point-filter").value.trim().toLowerCase();
  const listEl = S.points.filter((p) => !filter ||
      (p.name + " #" + p.id + " " + p.x + "," + p.y).toLowerCase().includes(filter));
  $("points-count").textContent = listEl.length + "/" + S.points.length;
  const target = $("points");
  target.replaceChildren();
  if (!S.points.length) {
    target.appendChild(el("p", {class: "hint"},
      "Noch keine Punkte aufgenommen. Im Hauptprozess mit CTRL+ALT+A anlegen."));
    return;
  }
  for (const p of listEl) {
    target.appendChild(el("div", {
      class: "point", draggable: "true", title: p.source || "",
      ondragstart: (e) => { drag = {kind: "point", point: p.id};
                            e.dataTransfer.effectAllowed = "copy"; },
      ondragend: () => { drag = null; clearDropZone(); },
    },
      // Ohne aufgenommene Farbe bleibt das Feld LEER (nur Rahmen). Vorher stand
      // dort die Linienfarbe als Füllung — das behauptete eine Farbe, die nie
      // gemessen wurde, und der Farb-Trigger hängt an derselben Quelle.
      el("span", {class: "dot" + (p.color ? "" : " without"),
                  title: p.color ? "" : "keine Farbe aufgenommen",
                  style: p.color ? "background:" + p.color : ""}),
      el("span", {class: "nr"}, "#" + p.id),
      el("span", {class: "name"}, p.name),
      el("span", {class: "xy"}, p.x + "," + p.y)));
  }
}

/* --------------------------------------------------------------------- Board */

function renderPhases() {
  const target = $("phases");
  target.replaceChildren();
  if (!S.phases.some((p) => p.index === selectedPhase && p.kind === "loop")) {
    selectedPhase = null;
  }
  const visible = S.phases.filter((phase) => phase.kind === "loop" ||
    phase.blocks.length || openSpecialPhases.has(phase.kind));
  for (const phase of visible) target.appendChild(renderPhase(phase));

  const hiddenOne = S.phases.filter((phase) => phase.kind !== "loop" &&
    !phase.blocks.length && !openSpecialPhases.has(phase.kind));
  const werkzeuge = el("div", {class: "phase phases-create"},
    el("button", {class: "empty-zone", onclick: () => call("phase_append")}, "+ Phase"));
  for (const phase of hiddenOne) {
    const title = phase.kind === "init" ? "+ Startphase (einmal davor)"
                                       : "+ Abschlussphase (einmal danach)";
    werkzeuge.appendChild(el("button", {class: "empty-zone", onclick: () => {
      openSpecialPhases.add(phase.kind);
      renderPhases();
    }}, title));
  }
  target.appendChild(werkzeuge);
}

function renderPhase(phase) {
  const phaseSelected = phase.kind === "loop" && phase.index === selectedPhase;
  const head = el("div", {
    class: "phase-header " + phase.kind + (phaseSelected ? " selected" : ""),
    title: phase.kind === "loop" ? "Phase auswählen — Entf löscht sie" : "",
    onclick: (e) => {
      if (phase.kind !== "loop" || e.target.closest("input, button")) return;
      selectedPhase = phase.index;
      call("selection_clear");
    }});
  // INIT und END tragen keinen frei wählbaren Namen — sie bekommen deshalb auch
  // kein Eingabefeld, das nichts annimmt.
  const specialName = phase.kind === "init" ? "START · einmal davor"
                   : phase.kind === "end" ? "ABSCHLUSS · einmal danach" : phase.name;
  const name = phase.kind === "loop"
    ? el("input", {class: "phase-name grow", value: phase.name})
    : el("span", {class: "phase-name grow"}, specialName);
  name.addEventListener("change", () => call("phase_set",
    {phase: phase.index, field: "name", value: name.value}));
  // Kein „×N" als Marke daneben: bei einer Loop-Phase stünde der Wert damit
  // zweimal im Kopf, einmal als Zahl zum Anfassen und einmal als Abzeichen, das
  // sich nicht ändern lässt. Die zugehörige Klasse `.zaehler` ist damit
  // ersatzlos weg — die Sequenzen-Übersicht benutzt ihre eigene (`.zahl`).
  head.appendChild(el("div", {class: "row"}, name,
    el("span", {class: "small mono"}, phase.blocks.length + " Schritte")));

  if (phase.kind === "loop") {
    const reps = el("input", {type: "number", min: "1", value: phase.repeat,
                             title: "Wie oft diese Phase je Zyklus läuft — 1 = einmal"});
    reps.addEventListener("change", () => call("phase_set",
      {phase: phase.index, field: "repeat", value: Number(reps.value) || 1}));
    const start = el("input", {value: phase.start, placeholder: "HH:MM",
                               title: "Start erst ab dieser Uhrzeit"});
    start.addEventListener("change", () => call("phase_set",
      {phase: phase.index, field: "start", value: start.value}));
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
    head.appendChild(el("div", {class: "phase-tool"},
      el("label", {class: "field"}, "Läufe je Zyklus", reps),
      el("label", {class: "field"}, "Start ab Uhrzeit", start)));
  }
  // **Was auf ALLE Blöcke der Phase wirkt, steht beieinander** — und nur, wenn
  // es welche gibt. Das Skalieren stand vorher zwischen Wiederholungen und
  // Startzeit, also zwischen zwei Feldern, die die Phase BESCHREIBEN, während
  // es selbst jeden Block darin ändert. Ohne Blöcke hatte es ausserdem nichts
  // zu tun und stand trotzdem da.
  if (phase.blocks.length) {
    const alle = S.selection.phase === phase.index &&
                 S.selection.rows.length === phase.blocks.length;
    // `knopfpaar`, nicht `series` mit `wachse`: für „mehrere Knöpfe teilen sich
    // eine Zeile" gibt es genau eine Antwort im Haus, und sie bricht um, statt
    // die Beschriftung abzuschneiden, sobald eine Spalte unter 118 px fiele.
    const bulk = el("div", {class: "button-pair phase-all"},
      el("button", {class: "btn quiet",
        onclick: () => call("phase_selection", {phase: phase.index})},
        alle ? "Auswahl aufheben" : "Alle Blöcke wählen"));
    if (phase.kind === "loop") {
      bulk.appendChild(el("button", {
        class: "btn quiet",
        title: "Alle Wartezeiten dieser Phase mit einem Faktor multiplizieren",
        onclick: () => {
          const factor = window.prompt("Wartezeiten mit welchem Faktor multiplizieren?", "1.0");
          if (factor !== null) call("phase_scale", {phase: phase.index, factor: factor});
        }}, "Zeiten skalieren …"));
    }
    head.appendChild(bulk);
  }

  const column = el("div", {class: "phase"}, head);
  phase.blocks.forEach((block, i) => {
    column.appendChild(dropZone(phase.index, i));
    column.appendChild(renderCard(phase, block));
  });
  column.appendChild(dropZone(phase.index, phase.blocks.length));
  column.appendChild(el("button", {
    class: "empty-zone",
    onclick: () => call("block_append", {phase: phase.index}),
    ondragover: (e) => { if (drag) { e.preventDefault(); highlight(e.currentTarget); } },
    ondragleave: () => clearDropZone(),
    ondrop: (e) => drop(e, phase.index, phase.blocks.length),
  }, phase.blocks.length ? "+ Block" : "leer — Block anlegen oder Punkt herziehen"));
  return column;
}

/** Einfügestelle zwischen zwei Karten: nur ein Strich, der aufleuchtet. */
function dropZone(phase, row) {
  return el("div", {
    class: "dropzone",
    ondragover: (e) => { if (drag) { e.preventDefault(); highlight(e.currentTarget); } },
    ondragleave: () => clearDropZone(),
    ondrop: (e) => drop(e, phase, row),
  });
}

function highlight(n) {
  if (activeDropZone === n) return;
  clearDropZone();
  activeDropZone = n;
  n.classList.add("active");
}

function clearDropZone() {
  if (activeDropZone) activeDropZone.classList.remove("active");
  activeDropZone = null;
}

function drop(e, phase, row) {
  e.preventDefault();
  e.stopPropagation();
  clearDropZone();
  const what = drag;
  drag = null;
  if (!what) return;
  if (what.kind === "point") call("point_insert", {phase: phase, row: row, point: what.point});
  else call("drag", {von_phase: what.phase, from_row: what.row,
                      nach_phase: phase, to_row: row});
}

function renderCard(phase, block) {
  // Der Titel steht in der Kopfzeile, nicht im Leib: dort traegt er die Typfarbe
  // mit und steht NEBEN dem Typ statt darunter — eine Zeile weniger pro Karte,
  // und bei 50 Karten untereinander ist das der Unterschied.
  // Die Farbe des Punkts steht an seiner Stelle (erste Zeile) — bei JEDEM
  // Block, der einen Punkt hat, nicht nur an der Farb-Bedingung. Beim
  // Überfliegen unterscheidet man Karten an der Farbe des Knopfs, nicht an
  // vierstelligen Koordinaten.
  const body = el("div", {class: "card-body"},
    block.rows.map((z, i) => (i === 0 && block.point_color)
      ? el("div", {class: "card-row with-color"},
          el("span", {class: "swatch", style: "background:" + block.point_color,
                      title: "Farbe des Punkts " + block.point_color}),
          z)
      : el("div", {class: "card-row"}, z)));

  if (block.color_swatch) {
    body.appendChild(el("div", {class: "card-color"},
      el("span", {class: "swatch", style: "background:" + block.color_swatch}),
      block.color_text));
  }
  if (block.else_text) {
    // Ein ELSE ohne Bedingung feuert nie — auf der Karte stuende es sonst als
    // Zusage da („sonst: Schritt überspringen"), die nichts einloest.
    body.appendChild(el("div", {class: "card-else" + (block.else_applies ? "" : " dead")},
      block.else_text + (block.else_applies ? "" : " · greift nie")));
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
    class: "card" + (block.selected ? " selected" : ""),
    title: "Klick wählt · STRG+Klick nimmt dazu oder heraus · "
           + "SHIFT+Klick wählt bis hierher · Ziehen sortiert um",
    draggable: "true",
    onclick: (e) => {
      selectedPhase = null;
      return call("select", {
        phase: phase.index, row: block.row,
        mode: e.ctrlKey || e.metaKey ? "dazu" : (e.shiftKey ? "area" : "einzeln")});
    },
    ondragstart: (e) => { drag = {kind: "block", phase: phase.index, row: block.row};
                          e.dataTransfer.effectAllowed = "move"; },
    ondragend: () => { drag = null; clearDropZone(); },
    ondragover: (e) => {
      if (!drag) return;
      e.preventDefault();
      const r = e.currentTarget.getBoundingClientRect();
      const bottom = e.clientY > r.top + r.height / 2;
      const line = bottom ? e.currentTarget.nextElementSibling
                           : e.currentTarget.previousElementSibling;
      if (line && line.classList.contains("dropzone")) highlight(line);
    },
    ondrop: (e) => {
      const r = e.currentTarget.getBoundingClientRect();
      drop(e, phase.index, block.row + (e.clientY > r.top + r.height / 2 ? 1 : 0));
    },
  },
    el("div", {class: "card-header", style: "background:" + block.color},
      el("span", {class: "card-type"}, block.label),
      block.title ? el("span", {class: "card-title"}, block.title) : null,
      block.checks ? el("span", {class: "badge-small", title: "prüft nach der Aktion nach"},
                        "prüft") : null,
      // Der Haltepunkt steht auf der Karte, nicht nur im Inspektor: „wo hält
      // es an" ist die Frage, die man beim Überfliegen von fünfzig Karten hat.
      block.breakpoint ? el("span", {class: "badge-small breakpoint",
                                     title: "Haltepunkt — der Lauf hält vor diesem Block an"},
                            "⏸ halt") : null,
      block.warning ? el("span", {class: "badge-small warn"}, block.warning) : null,
      el("span", {class: "card-nr"}, String(block.row + 1).padStart(2, "0"))),
    body);
}

/* -------------------------------------------------------- Ansicht: Sequenzen */

/** Zeitstempel (Sekunden) als „TT.MM.JJJJ HH:MM“.
 *
 * Von Hand statt `toLocaleString()`: das Fenster erbt seine Locale von der
 * WebView, und die muss nicht die der Konsole sein. Ein Datum, das mal
 * deutsch und mal amerikanisch herum steht, liest man zweimal falsch. */
function timestamp(seconds) {
  if (!seconds) return "—";
  const d = new Date(seconds * 1000);
  const zz = (n) => String(n).padStart(2, "0");
  return zz(d.getDate()) + "." + zz(d.getMonth() + 1) + "." + d.getFullYear() +
         " " + zz(d.getHours()) + ":" + zz(d.getMinutes());
}

/** Eine Phasenfarbe aus dem Stylesheet (`--init` / `--loop` / `--end`).
 *
 * Der Balken setzt seine Segmente per Inline-Stil (die Breite ist gerechnet).
 * Die Farbe trotzdem aus `:root` zu holen haelt die Palette an einer Stelle;
 * gemerkt, weil `getComputedStyle` sonst je Sequenzkarte dreimal liefe. */
const _phaseColors = {};
function phaseColor(kind) {
  if (!(kind in _phaseColors)) {
    _phaseColors[kind] = getComputedStyle(document.documentElement)
      .getPropertyValue("--" + kind).trim() || "#64748B";
  }
  return _phaseColors[kind];
}

/** INIT / Loop-Phasen / END als Segmente, Breite nach Schrittzahl.
 *
 * Leere Phasen fallen raus: ein Segment der Breite 0 sagt nichts, kostet aber
 * eine Luecke. Die Phasenfarben sind dieselben wie ueberall sonst. */
function phaseBar(s) {
  const parts = [{n: s.init, color: phaseColor("init"), what: "INIT: " + s.init}]
    .concat((s.phases || []).map((p) => ({n: p.steps, color: phaseColor("loop"),
      what: p.name + ": " + p.steps + " Schritte ×" + p.repeat +
           (p.start ? " ab " + p.start : "")})))
    .concat([{n: s.end, color: phaseColor("end"), what: "END: " + s.end}]);
  const totalSum = parts.reduce((a, t) => a + t.n, 0) || 1;
  return el("div", {class: "bar"}, parts.filter((t) => t.n).map((t) =>
    el("span", {style: "flex:" + t.n / totalSum + ";background:" + t.color, title: t.what})));
}

async function renderSequenceList() {
  const target = $("view-sequences");
  const listEl = await ask("sequence_list");
  // Zwischen Frage und Antwort kann umgeschaltet worden sein — dann gehoert
  // die Antwort in eine Ansicht, die niemand mehr ansieht.
  if (view !== "sequences") return;
  target.replaceChildren();
  if (!listEl || !listEl.length) {
    // grid-column: sonst stünde der Text in der ersten Spalte des Rasters und
    // wäre auf einem breiten Fenster in die linke Ecke gequetscht.
    target.appendChild(el("p", {class: "empty", style: "grid-column:1/-1"},
      "Noch keine Sequenz gespeichert. Im Editor eine anlegen (Neu) oder im " +
      "Hauptprozess mit CTRL+ALT+J eine aufnehmen."));
    return;
  }
  for (const s of listEl) target.appendChild(seqCard(s));
}

/** Eine Sequenz als Karte — mit FESTEN Zeilen, damit die Karten sich einmessen.
 *
 * **Jede Karte legt dieselben fünf Zeilen an, auch leere.** Vorher liess eine
 * fehlende Notiz alles darunter hochrutschen: bei drei Karten nebeneinander lag
 * dann der Phasenbalken der einen auf Höhe der Kennzahlen der anderen, und die
 * Übersicht war keine mehr. Mit `subgrid` teilen sich alle Karten einer Reihe
 * die Zeilenhöhen (siehe `.seq-card` im Stylesheet) — dafür muss jede Zeile
 * aber DA sein, sonst rutscht der Rest wieder eine Stelle nach oben. */
function seqCard(s) {
  const cardEl = el("div", {class: "seq-card" + (s.open ? " open" : "") +
                                  (s.broken ? " broken" : "")});
  cardEl.appendChild(el("div", {class: "seq-header"},
    el("span", {class: "seq-name"}, s.name),
    s.open ? el("span", {class: "num", style: "color:var(--accent)"}, "open") : null));

  // Zeile 2: Notiz bzw. Warnung. Eine defekte Datei hat weder Balken noch
  // Kennzahlen — die Zeilen bleiben trotzdem stehen, damit die Nachbarkarten
  // nicht verrutschen.
  const text = el("div", {class: "seq-text"});
  if (s.broken) {
    text.appendChild(el("p", {class: "seq-warn"},
      "Nicht ladbar — die Datei ist beschädigt oder kein gültiges Sequenz-Format. " +
      "Sie bleibt unangetastet; nachsehen lohnt sich in " + s.file + "."));
  } else {
    if (s.description) text.appendChild(el("p", {class: "seq-note"}, s.description));
    if (s.warnings && s.warnings.length) {
      text.appendChild(el("p", {class: "seq-warn"},
        s.warnings.length + "× Scan ohne Konfiguration — " + s.warnings[0] +
        (s.warnings.length > 1 ? " u. a." : "")));
    }
  }
  cardEl.appendChild(text);
  cardEl.appendChild(el("div", {class: "seq-bar"},
    s.broken ? null : phaseBar(s)));
  cardEl.appendChild(el("div", {class: "seq-numbers"}, s.broken ? null : [
    el("span", {class: "num"}, s.steps + " Schritte"),
    el("span", {class: "num"}, s.phases.length + " Loop-Phasen"),
    el("span", {class: "num"}, s.cycles ? s.cycles + " Zyklen" : "endlos")]));

  // Zwei Knöpfe teilen sich gleiche Spalten (`knopfpaar`): „Öffnen" und
  // „Löschen" sind verschieden lang, und zwei verschieden breite Knöpfe
  // nebeneinander lesen sich als zwei Rangstufen. Bei einer defekten Datei
  // bleibt die erste Spalte leer statt zu verschwinden — sonst säße das
  // Löschen dort, wo bei den Nachbarkarten das Öffnen steht.
  cardEl.appendChild(el("div", {class: "seq-footer"},
    el("span", {class: "small mono grow", title: s.file},
       s.file + " · " + timestamp(s.changed)),
    el("div", {class: "button-pair"},
      // Öffnen geht über den vorhandenen Befehl, nicht über einen neuen: dann
      // greift auch die vorhandene Rückfrage bei ungespeicherten Änderungen.
      s.broken ? el("span", {}) : el("button", {
        class: "btn" + (s.open ? "" : " primary"), disabled: s.open,
        onclick: async () => { await call("load", {name: s.name}); setView("editor"); },
      }, s.open ? "geöffnet" : "Öffnen"),
      el("button", {
        class: "btn danger quiet", disabled: s.open,
        title: s.open
          ? "Erst eine andere Sequenz laden — sonst legt der nächste Druck auf "
            + "Speichern den Ordner wieder an."
          : "Räumt den ganzen Sequenzordner nach backups/ weg",
        onclick: () => askDelete(s),
      }, "Löschen"))));
  return cardEl;
}

/** Die Rückfrage vor dem Löschen — mit dem, was wirklich weggeht.
 *
 * Eine Sequenz ist eine Besitzeinheit: Scans, Vorlagen und gemerkte Bildschirme
 * liegen in ihrem Ordner. „Sequenz löschen?" allein verschwiege den halben
 * Umfang, und der ist genau das, was man hinterher vermisst. */
function askDelete(s) {
  // Das Wort kommt fertig gebeugt aus der Bruecke. Ein angehaengtes "n" ergab
  // "2× Item-Scann" — deutsche Mehrzahl ist keine Regel fuer eine Zeile hier.
  const parts = (s.scope || []).map((u) => u.count + "× " + u.word);
  showQuestion({
    kind: "seq_loeschen",
    target: s.name,
    title: "„" + s.name + "“ löschen?",
    text: "Der ganze Ordner geht weg"
      + (parts.length ? " — samt " + parts.join(", ") + "." : ".")
      + " Er wird nach backups/sequences/ verschoben, nicht gelöscht:"
      + " zurückholen geht von Hand.",
    proceed_label: "Löschen",
  });
}

/* --------------------------------------------------------- Ansicht: Live-Run */

let runPolling = null;
let runWasRunning = false;

/** Der schnelle Takt läuft nur, solange der Reiter offen ist.
 *
 * Ein Fenster, das im Hintergrund alle 500 ms eine Datei liest, tut das die
 * ganze Nacht — und die Datei liegt auf derselben Platte, auf die der Worker
 * gerade schreibt. Daneben gibt es den langsamen Puls (s.u.), der nur die eine
 * Frage stellt: hat gerade ein Lauf angefangen? */
function setRunPolling(on) {
  if (runPolling) { clearInterval(runPolling); runPolling = null; }
  if (!on) return;
  renderRun();
  runPolling = setInterval(renderRun, 500);
}

/** Springt beim Start eines Laufs von selbst in die Live-Ansicht.
 *
 * Nur auf der Flanke (nichts → laeuft), nicht solange etwas laeuft: sonst kaeme
 * man waehrend eines Durchgangs nicht mehr in den Editor zurueck. */
function runEdge(active) {
  if (active && !runWasRunning && view !== "lauf") setView("lauf");
  runWasRunning = active;
  const button = $("btn-run");
  button.textContent = active ? "■ Stoppen" : "▶ Starten";
  button.classList.toggle("danger", active);
}

/** Einen Lauf-Befehl abschicken, nachfassen — und melden, wenn niemand zuhört. */
async function sendRun(command, extra) {
  await call("run_command", Object.assign({command: command}, extra || {}));
  runFollowUp();
  mailboxFollowUp();
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
function mailboxFollowUp() {
  const stamp = statusStamp;
  setTimeout(async () => {
    if (!(await ask("command_pending"))) return;
    // Hat inzwischen jemand anders etwas gemeldet, ist diese Warnung zwei
    // Sekunden alt und wuerde die frischere Meldung ueberschreiben.
    if (statusStamp !== stamp) return;
    setStatus({kind: "warn", text: "Kein Hauptprozess erreichbar — der Befehl " +
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
function runFollowUp() {
  for (const ms of [400, 900, 1600]) {
    setTimeout(async () => runEdge(!!((await ask("run_status")) || {}).active), ms);
  }
}

function edgePulse() {
  setInterval(async () => {
    if (view === "lauf") return;      // dort fragt schon der schnelle Takt
    const z = await ask("run_status");
    runEdge(!!(z && z.active));
  }, 2000);
}

/** Sekunden als „2:05“ bzw. „1:23:45“. */
function duration(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const zz = (n) => String(n).padStart(2, "0");
  const std = Math.floor(s / 3600);
  return (std ? std + ":" + zz(Math.floor(s / 60) % 60) : String(Math.floor(s / 60))) +
         ":" + zz(s % 60);
}

/** Restzeit knapp: unter zehn Sekunden mit Zehntel, darüber ganze Sekunden. */
function remainingTime(seconds) {
  const s = Math.max(0, seconds);
  return (s < 10 ? s.toFixed(1) : String(Math.round(s))) + " s";
}

function hexColor(rgb) {
  return "#" + rgb.map((n) => Math.max(0, Math.min(255, Math.round(n)))
                              .toString(16).padStart(2, "0")).join("");
}

/** Ein Farbfeld mit Beschriftung — schraffiert, wenn nichts gemessen wurde. */
function colorChip(text, rgb) {
  return el("div", {class: "piece"},
    el("span", {class: "swatch" + (rgb ? "" : " empty"),
                style: rgb ? "background:" + hexColor(rgb) : ""}),
    el("span", {class: "mono"}, text + (rgb ? " " + rgb.join(",") : " —")));
}

/** Worauf der laufende Block gerade wartet.
 *
 * „seit 12 s" allein beantwortet die Frage nicht: bei 15 s Wartezeit ist das
 * fast geschafft, bei 300 s Timeout gerade erst angefangen.
 *
 * Heruntergezaehlt wird hier, aus den absoluten Zeitstempeln der Statusdatei —
 * mit Restwerten aus dem Worker ruckelte die Anzeige in dessen Sekundentakt. */
function waitBox(w, now) {
  if (!w) return null;
  const remaining = w.until ? Math.max(0, w.until - now) : null;
  // „Knapp" meint knapp vor dem TIMEOUT — eine Warnung. Eine ablaufende
  // Wartezeit ist keine: die soll ablaufen, und amber daneben hiesse Alarm, wo
  // alles nach Plan läuft.
  const tight = w.kind === "color" && remaining !== null && remaining <= 5;
  const boxEl = el("div", {class: "waiting kind-" + (w.kind === "color" ? "color" : "time") +
                                   (tight ? " tight" : "")});

  if (w.kind === "color") {
    const match = w.distance !== null && w.distance !== undefined &&
                    w.distance <= w.tolerance;
    // Das Ziel hängt an der Richtung: bei `until_gone` ist ein Treffer genau das,
    // worauf NICHT gewartet wird — dieselbe Zahl, umgekehrte Bedeutung.
    const fulfilled = w.until_gone ? !match : match;
    boxEl.appendChild(el("div", {class: "header"},
      el("span", {class: "grow"},
         (w.until_gone ? "wartet, bis die Farbe weg ist" : "wartet auf die Farbe") +
         " bei (" + w.point.join(",") + ")"),
      el("span", {class: "small mono"}, "seit " + duration(now - w.since))));
    const details = el("div", {class: "grow"},
      el("div", {class: "color-pair"},
        colorChip("target", w.target),
        colorChip("jetzt", w.actual),
        w.distance === null || w.distance === undefined
          ? el("span", {class: "small"}, "nicht messbar")
          : el("span", {class: "badge-match" + (fulfilled ? "" : " beside")},
               "Δ " + w.distance + " · " +
               (match ? "im Toleranzbereich" : "ausserhalb") + " (" + w.tolerance + ")")));
    // Das Bild steht links neben den Zahlen: es beantwortet die Anschlussfrage
    // („was ist da statt dessen zu sehen?"), nicht dieselbe.
    boxEl.appendChild(w.image
      ? el("div", {class: "pixel-box"},
          el("div", {class: "live-pixel"},
            el("div", {class: "frame"}, el("img", {src: w.image, alt: ""})),
            el("span", {class: "sign"}, "LIVE-PIXEL")),
          details)
      : details);
  } else {
    boxEl.appendChild(el("div", {class: "header"},
      el("span", {class: "grow"}, w.text || "wartet"),
      el("span", {class: "remainder"}, remaining === null ? "" : "noch " + remainingTime(remaining))));
  }

  if (remaining !== null) {
    boxEl.appendChild(bar(now - w.since, w.until - w.since));
  }
  if (w.kind === "color") {
    boxEl.appendChild(el("span", {class: "small"}, remaining === null
      ? "ohne Timeout — wartet, bis die Farbe stimmt"
      : "Timeout in " + remainingTime(remaining) + " · danach " + (w.after_value || "—")));
  } else if (remaining !== null) {
    boxEl.appendChild(el("span", {class: "small"}, "von " + remainingTime(w.total || 0)));
  }
  return boxEl;
}

function bar(actual, target) {
  const share_pct = target > 0 ? Math.max(0, Math.min(1, actual / target)) : 0;
  return el("div", {class: "progress"}, el("span", {style: "width:" + share_pct * 100 + "%"}));
}

/** Alle Phasen des Laufs nebeneinander, die laufende breit.
 *
 * Die Liste kommt aus dem Laufstatus, nicht aus der geoeffneten Sequenz: laufen
 * kann eine ganz andere. Fehlt sie, bleibt es bei der einen laufenden Phase.
 *
 * „Abgeschlossen" gilt innerhalb des laufenden Zyklus — im naechsten Durchgang
 * sind dieselben Loop-Phasen wieder ausstehend. */
function phaseStrip(z, finished) {
  const currentOne = z.phase_pos;
  const listEl = Array.isArray(z.phases) && z.phases.length
    ? z.phases
    : [{name: z.phase || "—", kind: "loop", repeat: z.repeat || 1}];
  const pos = currentOne === undefined || currentOne === null || !Array.isArray(z.phases)
    ? 0 : currentOne;

  return el("div", {class: "phase-strip"}, listEl.map((p, i) => {
    // In der Zusammenfassung laeuft nichts mehr: die Stelle, an der Schluss
    // war, ist markiert, nicht "gerade dran". Sonst behauptete die Leiste einen
    // Lauf, den es nicht mehr gibt.
    const running = i === pos && !finished;
    const tile = el("div", {
      class: "phase-tile" + (running ? " running" : (i < pos ? " done" : ""))
             + (finished && i === pos ? " end-mark" : ""),
      "data-kind": p.kind || "loop",
    }, el("div", {class: "p-name"}, p.name || "—"));

    if (running) {
      tile.appendChild(el("div", {class: "row"},
        el("span", {class: "small mono grow"},
           "Durchlauf " + (z.pass_index || 1) + " / " + (z.repeat || 1)),
        el("span", {class: "small mono"},
           "Block " + (z.block || 0) + " / " + (z.blocks || 0))));
      tile.appendChild(bar(z.pass_index || 0, z.repeat || 1));
    } else if (finished && i === pos) {
      // Die Phase, in der Schluss war. „ausstehend" waere hier falsch (sie lief
      // ja) und „abgeschlossen" auch (sie kam nicht durch) — ausser der Lauf
      // ist regulaer bis zum Ende gekommen.
      tile.appendChild(el("div", {class: "p-position"},
        (z.reason || "").startsWith("alle Zyklen") ? "abgeschlossen" : "hier war Schluss"));
    } else if (i < pos) {
      tile.appendChild(el("div", {class: "p-position"}, "abgeschlossen"));
    } else {
      // Eine zeitgesteuerte Phase wartet nicht auf ihren Vorgänger, sondern auf
      // die Uhr — das ist der Unterschied zwischen „gleich" und „um 07:00".
      tile.appendChild(el("div", {class: "p-position"},
        p.start ? "wartet auf " + p.start : "ausstehend"));
    }
    return tile;
  }));
}

async function renderRun() {
  const z = await ask("run_status");
  runEdge(!!(z && z.active));   // auch hier mitfuehren, sonst kippt die Flanke
  if (view !== "lauf") return;
  const target = $("view-run");
  target.replaceChildren();
  if (!z || !z.active) {
    if (z && z.countdown) {
      const now = Date.now() / 1000;
      target.appendChild(el("div", {class: "run-header"},
        el("span", {class: "lamp on"}),
        el("span", {class: "run-name"}, z.sequence || "(ohne Namen)"),
        el("span", {class: "num"}, "startet in " +
          remainingTime((z.target_time || now) - now))));
      target.appendChild(el("p", {class: "hint"},
        "Geplant für " + new Date((z.target_time || now) * 1000).toLocaleString("de-CH") +
        ". Der Countdown kann hier oder mit dem Stop-Hotkey abgebrochen werden."));
      target.appendChild(controls(false, z));
      return;
    }
    if (z && z.end) return renderSummary(target, z);
    // Leerzustand ehrlich beschriften statt mit Nullen füllen: eine Tafel voller
    // Nullen sieht aus wie ein Lauf, der nichts tut.
    target.appendChild(el("div", {class: "run-header"},
      el("span", {class: "lamp"}),
      el("span", {class: "run-name"},
         z && z.orphaned ? "Nicht sauber beendet" : "Es läuft gerade keine Sequenz")));
    target.appendChild(el("p", {class: "hint"}, z && z.orphaned
      ? "Der letzte Lauf hat sich nicht sauber beendet — der Hauptprozess wurde " +
        "vermutlich hart abgeschossen. Ein neuer Start räumt das auf."
      : "Startet die zuletzt gespeicherte Fassung der geöffneten Sequenz — " +
        "danach zeigt diese Ansicht mit, wo sie gerade steht."));
    target.appendChild(controls(false, z));
    return;
  }

  const now = Date.now() / 1000;
  target.appendChild(el("div", {class: "run-header"},
    el("span", {class: "lamp on"}),
    el("span", {class: "run-name"}, z.sequence || "(ohne Namen)"),
    el("span", {class: "num"},
       "Zyklus " + (z.cycle || 0) + " / " + (z.cycles ? z.cycles : "∞")),
    el("span", {class: "num"}, "läuft " + duration(now - (z.start || now)))));

  target.appendChild(phaseStrip(z));

  // Kopfzeile in der Typfarbe des laufenden Blocks — dieselbe Gestalt wie seine
  // Karte im Board, damit man ihn wiedererkennt statt ihn zu lesen. Ohne Typ
  // (alte Statusdatei) bleibt sie neutral statt eine Farbe zu erfinden.
  const counters = z.counters || {};
  target.appendChild(el("div", {class: "run-middle"},
    el("div", {class: "panel with-header"},
      el("div", {class: "card-header",
                 style: "background:" + (z.block_color || "#2A3245") +
                        (z.block_color ? "" : ";color:var(--text)")},
        el("span", {class: "card-type"}, z.block_badge || "AKTUELLER BLOCK"),
        el("span", {class: "card-title"}, z.block_title || "(ohne Namen)"),
        el("span", {class: "card-nr"},
           "Block " + (z.block || 0) + " / " + (z.blocks || 0))),
      el("div", {class: "panel-body"},
        el("div", {class: "card-row"}, z.block_label || ""),
        bar(z.block || 0, z.blocks || 1),
        el("span", {class: "small mono"},
           "seit " + duration(now - (z.block_since || now))),
        waitBox(z.waiting, now))),
    el("div", {class: "tile"},
      [["Klicks", "clicks"], ["Items", "items"], ["Tasten", "keys"],
       ["Timeouts", "timeouts"], ["Übersprungen", "skipped"],
       ["Neustarts", "restarts"]].map(([text, key]) =>
        el("div", {}, el("b", {}, String(counters[key] || 0)),
                      el("small", {}, text.toUpperCase()))))));

  if (z.manual) target.appendChild(manualControls(z.manual));
  target.appendChild(controls(true, z));
}

/** Der letzte Lauf, nachdem er fertig ist.
 *
 * Der Stand bleibt stehen, bis der naechste Start ihn ueberschreibt — sonst
 * waere die Ansicht genau dann leer, wenn man hinsieht. Dieselben Kacheln wie
 * im Lauf, nur mit festen statt mitlaufenden Zeitangaben. */
function renderSummary(target, z) {
  const counters = z.counters || {};
  // Warum es zu Ende ist, entscheidet die Farbe: durchgelaufen ist gruen,
  // von Hand gestoppt neutral, Notbremse rot. Eine Zusammenfassung, die bei
  // jedem Ausgang gleich aussieht, muss man lesen statt anzusehen.
  const reason = z.reason || "";
  const kind = reason.startsWith("Notbremse") ? "err"
            : reason.startsWith("alle Zyklen") ? "ok" : "warn";
  target.appendChild(el("div", {class: "run-header"},
    el("span", {class: "lamp done"}),
    el("span", {class: "run-name"}, z.sequence || "(ohne Namen)"),
    el("span", {class: "num summary-" + kind}, "beendet"),
    el("span", {class: "num"}, timestamp(z.end)),
    el("span", {class: "num"}, "lief " + duration(z.duration || 0))));

  target.appendChild(el("p", {class: "hint summary-" + kind},
    reason + " · " + (z.elapsed_cycles || 0) + " von " +
    (z.cycles ? z.cycles : "∞") + " Zyklen"));

  if (z.phases && z.phases.length) target.appendChild(phaseStrip(z, true));

  target.appendChild(el("div", {class: "tile"},
    [["Klicks", "clicks"], ["Items", "items"], ["Tasten", "keys"],
     ["Timeouts", "timeouts"], ["Übersprungen", "skipped"],
     ["Neustarts", "restarts"]].map(([text, key]) =>
      el("div", {}, el("b", {}, String(counters[key] || 0)),
                    el("small", {}, text.toUpperCase())))));

  target.appendChild(controls(false, z));
}

/** Der Worker wartet wirklich auf diese Antworten; keine Konsolentaste.
 *
 * Dieselbe Tafel für zwei Anlässe: den manuellen Modus (hält vor JEDEM Block)
 * und einen Haltepunkt (hält vor DIESEM). Der Unterschied ist die dritte
 * Kachel — im Schrittmodus schaltet sie ihn aus („Normal weiter"), am
 * Haltepunkt schaltet sie ihn ein („Ab hier schrittweise"). Das Weiterlaufen
 * heisst am Haltepunkt „Weiter", denn es fragt danach nicht wieder. */
function manualControls(m) {
  const button = (text, action, cls) => el("button", {
    class: "btn" + (cls ? " " + cls : ""),
    onclick: () => sendRun("manual_action", {action: action}),
  }, text);
  const halt = !!m.breakpoint;
  return el("section", {class: "panel manual-panel"},
    el("span", {class: "heading"}, halt ? "⏸ HALTEPUNKT" : "MANUELLER SCHRITTMODUS"),
    el("b", {}, m.title || "Aktueller Block"),
    el("p", {class: "hint"}, m.action || ""),
    el("div", {class: "row", style: "gap:8px;flex-wrap:wrap"},
      button(halt ? "▶ Weiter" : "▶ Ausführen", "run", "primary"),
      button("↷ Überspringen", "skip"),
      halt ? button("Ab hier schrittweise", "step") : button("Normal weiter", "continue"),
      button("■ Stoppen", "stop", "danger")));
}

/** Start/Pause/Stopp.
 *
 * Die Knöpfe führen nichts aus — dieses Fenster hat keinen Zugriff auf
 * `state.stop_event`. Sie legen einen Befehl ab, den der Hauptprozess in
 * derselben Schleife abholt wie seine Hotkeys (`command.py`). Deshalb steht das
 * Hotkey-Kürzel weiterhin daneben: es ist derselbe Weg, nur ohne Fensterwechsel.
 */
function controls(running, stamp) {
  const button = (text, command, cls) => el("button", {
    class: "btn" + (cls ? " " + cls : ""),
    onclick: () => sendRun(command),
  }, text);
  const row = el("div", {class: "row", style: "gap:8px;flex-wrap:wrap"},
    !running && !(stamp && stamp.countdown) ? button("▶ Starten", "start", "primary") : null,
    !running && !(stamp && stamp.countdown) ? button("▶ Schrittweise", "start_manual") : null,
    running ? button("⏸ Pause", "pause") : null,
    running ? button("↷ Warten überspringen", "skip") : null,
    running ? button("⏭ Block überspringen", "skip_step") : null,
    running ? button("✓ Zyklus abschliessen", "finish") : null,
    running ? button("■ Stoppen", "stop", "danger") : null,
    !running && stamp && stamp.countdown ? button("■ Zeitplan abbrechen", "stop", "danger") : null,
    el("span", {class: "small"},
       running ? "oder CTRL+ALT+S / CTRL+ALT+G im Hauptprozess"
               : "startet die gespeicherte Fassung — ungespeicherte Änderungen " +
                 "werden vorher geschrieben"));
  if (!running && !(stamp && stamp.countdown)) {
    const time = el("input", {placeholder: "14:30 oder +30m", autocomplete: "off",
      style: "width:150px"});
    const plan = el("button", {class: "btn", onclick: () => {
      if (!time.value.trim()) {
        setStatus({kind: "warn", text: "Bitte eine Startzeit eingeben."});
        return;
      }
      sendRun("schedule", {time: time.value.trim()});
    }}, "◷ Start planen");
    row.append(el("span", {class: "divider"}), time, plan);
  }
  return row;
}

/* ----------------------------------------------------------------- Inspektor */

function pointList(current, withEmpty) {
  const values = S.points.map((p) => ({value: p.id, text: "#" + p.id + " " + p.name +
                                                        " (" + p.x + "," + p.y + ")"}));
  if (withEmpty || current === null || current === undefined) {
    values.unshift({value: "", text: "(kein Punkt)"});
  }
  return values;
}

function renderInspector() {
  const target = $("inspector");
  target.replaceChildren();
  const b = S.block;
  const selected = S.selection.rows.length;

  $("btn-block-delete").disabled = selected === 0;
  $("btn-block-copy").disabled = selected === 0;
  if (!b) {
    $("insp-point").style.background = "#2A3245";
    $("insp-title").textContent = selected > 1 ? selected + " BLÖCKE GEWÄHLT" : "KEIN BLOCK";
    target.appendChild(el("div", {class: selected > 1 ? "bulk-editor" : "empty"}, selected > 1
      ? renderBulkEditor(selected)
      : el("span", {}, "Block anklicken, um ihn zu bearbeiten.", el("br"),
           "Ziehen sortiert um — auch über Phasengrenzen.")));
    return;
  }

  const phase = S.phases[b.phase];
  $("insp-point").style.background = b.color;
  $("insp-title").textContent = "BLOCK " + String(b.row + 1).padStart(2, "0") +
                                " · " + phase.name.toUpperCase();

  // --- Typ ---
  // Jede Kachel traegt ihre Farbe, nicht nur die gewaehlte: damit ist das Raster
  // zugleich die Legende zu den Farben im Board. Ringsum statt als Streifen
  // links, die gewaehlte zusaetzlich ausgefuellt. `border-color` steht im
  // style-Attribut und damit NACH dem `border`-Kurzformat aus .type-chip —
  // andersherum raeumte die Kurzform die Farbe wieder weg.
  target.appendChild(heading("BLOCK-TYP",
    "Die Farbe der Kachel wiederholt sich auf der Karte im Board — das Raster " +
    "ist zugleich die Legende dazu.", "blocktyp"));
  target.appendChild(el("div", {class: "gitter3"}, S.types.map((t) =>
    el("button", {
      class: "type-chip",
      style: "border-color:" + t.color +
             (t.key === b.type
               ? ";background:" + t.color + ";color:#0C0F14;font-weight:600"
               : ""),
      onclick: () => call("block_set_type", {type: t.key}),
    }, t.label))));

  // Die drei Klick-/Warte-Typen unterscheiden sich in genau zwei Eigenschaften.
  // Als Schalter steht diese Tabelle auf dem Schirm, statt im Kopf zu sein.
  if (b.type === "click" || b.type === "wait_click" || b.type === "wait") buildAction(target, b);

  // --- Gemeinsames ---
  if (b.type !== "screenshot") {
    // Der Name steht nur hier, wenn er dem SCHRITT gehört. Hat der Block einen
    // Punkt, gehört der Name dem Punkt — und dann steht er unten bei der Stelle,
    // zusammen mit Auswahl, Farbe und Koordinaten. Vorher stand oben „Name
    // (Punkt #1)" und weiter unten nochmal „Punkt": zweimal dieselbe Sache an
    // zwei Stellen, und man musste raten, welche die führende ist.
    if (b.point_id === null || b.point_id === undefined) {
      target.appendChild(field("Name", b.name, (v) => call("block_set", {field: "name", value: v})));
    }
    target.appendChild(el("div", {class: "gitter2"},
      numberField("Wartezeit (s)", b.delay_before,
               (v) => call("block_set", {field: "delay_before", value: v}),
               {step: "0.1", min: "0"}),
      numberField("bis (0 = fest)", b.delay_max,
               (v) => call("block_set", {field: "delay_max", value: v}),
               {step: "0.1", min: "0"})));
  }

  // Der Haltepunkt gilt für JEDEN Typ — auch ein Screenshot kann die Stelle
  // sein, an der man einmal hinsehen will, bevor es weitergeht.
  target.appendChild(toggle("Haltepunkt — vor diesem Block anhalten", b.breakpoint,
    (on) => call("block_set", {field: "breakpoint", value: on}),
    "Der Lauf hält hier an und fragt — im Live-Run als Tafel (weiter, überspringen, "
    + "ab hier schrittweise, stoppen), in der Konsole per Taste. CTRL+ALT+G heisst "
    + "„weiter“. In einer Loop-Phase hält er in jedem Zyklus; ausschalten, wenn er "
    + "seinen Dienst getan hat.", "breakpoint"));

  // Ein Warte-Block ohne Trigger beobachtet nichts — dann gibt es auch keine
  // Stelle zu zeigen.
  if (b.type === "click" || b.type === "wait_click" ||
      (b.type === "wait" && b.trigger !== "kein")) buildPosition(target, b);
  if (b.type === "key") {
    target.appendChild(field("Taste", b.key_press,
      (v) => call("block_set", {field: "key_press", value: v}), {placeholder: "enter, space, f1"}));
  }
  buildScan(target, b);
  if (b.type === "screenshot") buildScreenshot(target, b);

  // Der Farb-Trigger fragt VOR dem Schritt und steht nur da, wo die Laufzeit ihn
  // auswertet: Klick, Warten und Taste. Scans und Screenshot kehren vorher um.
  //
  // Haengt trotzdem schon eine Bedingung dran, bleibt der Abschnitt sichtbar —
  // sonst waere sie unerreichbar.
  const withTrigger = b.type === "click" || b.type === "wait_click" ||
                     b.type === "wait" || b.type === "key";
  if (withTrigger || b.trigger !== "kein") buildTrigger(target, b, withTrigger);
  buildVerification(target, b);
  buildElse(target, b);
  buildProbe(target, b);

  // Zuletzt, wenn alles im Dokument haengt: was aufgeklappt war, bleibt es. Der
  // Inspektor wird bei jeder Aenderung komplett neu gebaut — ohne diese Zeile
  // verschwindet eine gerade gelesene Erklaerung beim naechsten Klick irgendwo.
  applyHelps(target);
}

/** „Sitzt der Punkt da, wo ich denke?" — die Maus faehrt hin und sagt es.
 *
 * Nur bei Bloecken mit Stelle. Das Fenster sieht den Bildschirm nicht; der
 * Hauptprozess bewegt die Maus, misst die Farbe und schreibt das Ergebnis in
 * seine eigene Konsole. */
function buildProbe(target, b) {
  // Ein Block hat bis zu drei Stellen — Klick, Prüf-Pixel des Triggers und
  // ELSE-Klick —, und „sitzt das noch?" fragt man bei jeder. Angeboten wird
  // nur, was der Block wirklich hat.
  const positions = [];
  if (b.point_id !== null && b.point_id !== undefined)
    positions.push(["click", "Stelle", b.point_id]);
  if (b.trigger !== "kein" && b.trigger_point !== null && b.trigger_point !== undefined)
    positions.push(["trigger", "Prüf-Pixel", b.trigger_point]);
  if (b.verify !== "kein" && b.verify_point !== null && b.verify_point !== undefined)
    positions.push(["verify", "Nachprüf-Pixel", b.verify_point]);
  if (b.else_action === "click" && b.else_point !== null && b.else_point !== undefined)
    positions.push(["else", "ELSE-Klick", b.else_point]);
  const footer = el("div", {class: "insp-footer"});
  footer.appendChild(el("button", {
    class: "btn wide",
    title: "Führt diesen Block sofort aus — Wartezeit und Farb-Trigger werden übersprungen",
    onclick: () => call("block_test"),
  }, "▶ Block einmal testen"));
  for (const [which, text, point] of positions) {
    footer.appendChild(el("button", {
      class: "btn wide",
      onclick: () => call("point_show", {which: which}),
    }, "◎ " + text + " zeigen (#" + point + ")"));
  }
  target.appendChild(footer);
}

function renderBulkEditor(count) {
  const timeField = (caption, fieldName, value, mixed) => {
    const inputEl = el("input", {
      type: "number", min: "0", step: "0.1",
      value: mixed ? "" : (value === null || value === undefined ? 0 : value),
      placeholder: mixed ? "verschieden" : "",
    });
    inputEl.addEventListener("change", () => {
      if (inputEl.value.trim() !== "") {
        call("selection_set", {field: fieldName, value: Number(inputEl.value)});
      }
    });
    inputEl.addEventListener("keydown", (e) => { if (e.key === "Enter") inputEl.blur(); });
    return el("label", {class: "field"}, caption, inputEl);
  };
  return el("div", {},
    el("p", {class: "hint"},
      count + " Blöcke gemeinsam bearbeiten. Verschieben: ALT+↑/↓, löschen: Entf."),
    el("span", {class: "heading"}, "WARTEZEIT FÜR AUSWAHL"),
    el("div", {class: "row bulk-quick"}, [0, 0.5, 1].map((seconds) =>
      el("button", {class: "btn quiet", onclick: () => call("selection_set",
        {field: "delay_before", value: seconds})}, String(seconds).replace(".", ",") + " s"))),
    el("div", {class: "gitter2"},
      timeField("Wartezeit (s)", "delay_before", S.selection.delay_before,
               S.selection.delay_before_mixed),
      timeField("bis (0 = fest)", "delay_max", S.selection.delay_max,
               S.selection.delay_max_mixed)),
    el("p", {class: "hint"},
      "Nur diese Wartefelder werden gemeinsam geändert; Typ, Ziel und Bedingungen bleiben erhalten."));
}

function buildAction(target, b) {
  const clicks = b.type === "click" || b.type === "wait_click";
  const color = b.trigger !== "kein";

  // Der Schluessel bleibt "aktion" und haengt bewusst NICHT am Block-Typ: der
  // wechselt hier ja gerade, und eine Erklaerung, die man aufklappt und die beim
  // ersten Schalten verschwindet, ist keine.
  target.appendChild(heading("AKTION",
    "Diese beiden Schalter SIND der Block-Typ: klicken und/oder auf eine Farbe " +
    "warten. Die Kacheln oben zeigen das Ergebnis automatisch an.", "action"));
  target.appendChild(toggle("klickt an der Stelle", clicks, (on) =>
    call("block_set_type", {type: on ? (color ? "wait_click" : "click") : "wait"})));
  target.appendChild(toggle("wartet auf eine Farbe", color, (on) => {
    // Bei einem Warte-Block aendert die Farbe den Typ nicht — WARTEN heisst mit
    // und ohne Trigger WARTEN. Bei den Klick-Typen ist sie der Unterschied
    // zwischen KLICK und FARBE+KLICK, laeuft dort also ueber den Typ.
    if (!clicks) call("block_trigger", {choice: on ? "present" : "kein"});
    else call("block_set_type", {type: on ? "wait_click" : "click"});
  }));
}

function buildPosition(target, b) {
  // Beides an der Ueberschrift: der Zusatz fuer WARTEN-Bloecke erklaert, warum
  // hier ueberhaupt eine Stelle steht, obwohl nicht geklickt wird.
  target.appendChild(heading(b.type === "wait" ? "BEOBACHTETE STELLE" : "KLICK-POSITION",
    "X und Y verschieben den Punkt selbst. Jeder Block, der ihn benutzt, zeigt " +
    "danach auf die neue Stelle — die Sequenz speichert keine eigenen Koordinaten. " +
    "Mit ‚Stelle mit der Maus setzen‘ wechselst du danach ins Spiel, bewegst die " +
    "Maus an die Stelle und drückst ENTER. Die Farbe wird mitgemessen; ESC bricht ab." +
    (b.type === "wait" ? " Dieser Block klickt übrigens nicht: die Stelle wird nur " +
     "beobachtet. Zum Klicken oben den Typ KLICK oder FARBE+KLICK wählen." : ""),
    "position"));
  if (!S.points.length && b.point_id === null) {
    target.appendChild(el("p", {class: "hint"},
      "Keine Punkte vorhanden. Im Hauptprozess mit CTRL+ALT+A aufnehmen — " +
      "oder hier eine Stelle eintragen, dann entsteht ein Punkt dafür."));
  } else {
    target.appendChild(selection("Punkt", pointList(b.point_id), b.point_id === null ? "" : b.point_id,
      (v) => v && call("block_point", {point: Number(v)})));
  }
  // Alles, was dem Punkt gehört, steht beieinander: welcher, wie er heisst,
  // welche Farbe er trägt, wo er liegt.
  if (b.point_id !== null && b.point_id !== undefined) {
    const p = S.points.find((q) => q.id === b.point_id);
    target.appendChild(field("Name des Punkts", b.name,
      (v) => call("point_set", {point: b.point_id, field: "name", value: v}), null,
      "Der Name gehört dem Punkt, nicht diesem Block: er ändert sich überall, " +
      "wo derselbe Punkt benutzt wird.", "punktname"));
    target.appendChild(color_swatch("Farbe des Punkts", p && p.color,
      (hex) => call("point_set", {point: b.point_id, field: "color", value: hex}),
      "Beim Aufnehmen gemessen. Ein Farb-Trigger prüft GENAU diese Farbe — wer " +
      "sie hier ändert, ändert mit, worauf gewartet wird.", "punktfarbe"));
    // Zustand, kein ⓘ: WER den Punkt sonst noch benutzt, sieht man sonst erst,
    // wenn ein anderer Block woanders hinklickt. Und der Rueckweg steht dabei:
    // ein eigener Punkt fuer diesen Block, die anderen bleiben, wo sie sind.
    if (b.point_others && b.point_others.length) {
      target.appendChild(el("p", {class: "hint"},
        "Punkt #" + b.point_id + " wird auch benutzt von: " + b.point_others.join(", ")));
      target.appendChild(el("button", {
        class: "btn wide",
        title: "Dieser Block bekommt eine Kopie des Punkts; die anderen Blöcke behalten #"
               + b.point_id + ". Danach lässt sich seine Stelle ändern, ohne die anderen zu verstellen.",
        onclick: () => call("point_detach"),
      }, "⧉ Eigenen Punkt für diesen Block"));
    }
  }
  target.appendChild(el("div", {class: "gitter2"},
    numberField("X", b.x, (v) => setPosition(b, v, b.y), {step: "1"}),
    numberField("Y", b.y, (v) => setPosition(b, b.x, v), {step: "1"})));
  // Die Stelle anfahren statt sie zu tippen — derselbe Weg wie beim
  // Screenshot-Bereich. Die Zahlenfelder bleiben daneben stehen, für den Fall,
  // dass man eine Koordinate abschreibt.
  target.appendChild(el("button", {
    class: "btn wide",
    title: "Maus an die Stelle bewegen und ENTER drücken (ESC bricht ab)",
    onclick: () => withWait("call", "point_capture"),
  }, "✛ Stelle mit der Maus setzen"));
  // Hier stand ein Schalter "nur warten (kein Klick)". Er setzte `wait_only` —
  // also genau das, was der Typ-Chip WARTEN oben schon setzt: ein Zustand, zwei
  // Bedienelemente. Das rächte sich, weil er sich bei "warten" selbst ausblendete
  // und damit eine Falltuer war. Die Chips koennen alles, was er konnte:
  // WARTEN hin, FARBE+KLICK verlustfrei zurueck (der Trigger bleibt), KLICK
  // zurueck ohne Trigger — und das ist keine Nebenwirkung, sondern die Bedeutung
  // von KLICK. Was seine Beschriftung erklaerte, steht am ⓘ der Ueberschrift.
  if (b.scroll) {
    target.appendChild(numberField("Mausrad (Stufen, 0 = kein Rad)", b.scroll,
      (v) => call("block_set", {field: "scroll", value: v}), {step: "1"}));
  }
}

function setPosition(b, x, y) {
  if (b.point_id === null || b.point_id === undefined) {
    call("point_create", {x: x, y: y});
  } else {
    // Zwei Felder, ein Punkt: nur die geänderte Achse schicken.
    if (x !== b.x) call("point_set", {point: b.point_id, field: "x", value: x});
    if (y !== b.y) call("point_set", {point: b.point_id, field: "y", value: y});
  }
}

function buildScan(target, b) {
  const scans = {item_scan: ["ITEM-SCAN", "item_scan"], icon_scan: ["ICON-SCAN", "icon_scan"],
                 boss_scan: ["BOSS-SCAN", "boss_scan"], boss_watcher: ["BOSS-WATCHER", "boss_watcher"]};
  const entry = scans[b.type];
  if (!entry) return;
  const [title, fieldName] = entry;
  const existing = (S.scan_names && S.scan_names[b.type]) || [];
  const value = b[fieldName];
  target.appendChild(heading(title));

  if (!existing.length && !value) {
    // Nichts zum Auswählen — dann ist ein leeres Feld die falsche Antwort. Es
    // gäbe nur einen Namen her, der auf keine Datei zeigt, und der Block liefe
    // still ins Leere. Also sagen, wo die Konfiguration herkommt.
    // CTRL+ALT+N fuer alle drei: Boss- und Icon-Scans sind Untermenues des
    // Item-Scan-Menues, eigene Hotkeys haben sie nicht.
    target.appendChild(el("p", {class: "hint"},
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
  target.appendChild(selection("Konfiguration", values, value,
    (v) => call("block_set", {field: fieldName, value: v}),
    "Im Item-/Boss-/Icon-Editor angelegt (Hauptprozess, CTRL+ALT+N). " +
    "Ohne Konfiguration wird nicht gespeichert.", "scan"));
  if (b.type === "item_scan") {
    target.appendChild(selection("Modus", S.scan_modes.map((m) => ({value: m, text: m})),
      b.item_scan_mode, (v) => call("block_set", {field: "item_scan_mode", value: v})));
  }
}

function buildScreenshot(target, b) {
  target.appendChild(heading("SCREENSHOT"));
  const hasArea = !!b.screenshot_region;
  target.appendChild(toggle("Bereich statt Vollbild", hasArea,
    (on) => call("block_area", {values: on ? (b.screenshot_region || [0, 0, 100, 100]) : null})));
  if (!hasArea) return;
  const r = b.screenshot_region.slice();
  const setter = (i) => (v) => { r[i] = v; call("block_area", {values: r}); };

  // Der eigentliche Weg: die Ecke anfahren statt sie auszurechnen. Vier Zahlen
  // sagen niemandem, wo der Bereich liegt — sie bleiben trotzdem stehen, fuer
  // den Fall, dass man eine Koordinate abschreibt.
  target.appendChild(el("button", {class: "btn", onclick: (e) => {
    // blur() ist Pflicht, nicht Kosmetik: ein Knopf behaelt nach dem Klick den
    // Fokus, und das ENTER, mit dem die Ecke bestaetigt wird, wuerde ihn gleich
    // nochmal ausloesen — also mitten in der Aufnahme eine zweite starten.
    e.currentTarget.blur();
    // Sofortige Rueckmeldung, bevor die Bruecke blockiert: von dort kommt bis
    // zum zweiten Tastendruck nichts, und ein Fenster, das schweigt, sieht aus
    // wie eines, das den Klick verschluckt hat.
    setStatus({text: "Ecke 1 anfahren + ENTER, dann Ecke 2 + ENTER (ESC bricht ab)",
                 kind: "warn"});
    withWait("call", "area_capture");
  }}, "Bereich mit der Maus aufnehmen ⌖"));

  target.appendChild(el("div", {class: "gitter2"},
    numberField("X1", r[0], setter(0)), numberField("Y1", r[1], setter(1)),
    numberField("X2", r[2], setter(2)), numberField("Y2", r[3], setter(3))));
  target.appendChild(el("p", {class: "hint"},
    "Grösse: " + Math.abs(r[2] - r[0]) + " × " + Math.abs(r[3] - r[1]) + " Pixel"));
}

// Richtungen einer Farb-Bedingung. Das Aus steht nur dort mit im Segment, wo es
// kein eigenes Bedienelement dafuer gibt — bei den Klick-/Warte-Typen macht das
// der Schalter im Abschnitt AKTION, und zwei Wege zum selben Aus waeren einer zu viel.
const DIRECTION_OFF = {value: "kein", text: "kein"};
const DIRECTIONS = [{value: "present", text: "bis Farbe DA"}, {value: "weg", text: "bis Farbe WEG"}];

function buildTrigger(target, b, withTrigger) {
  // Bei TASTE gibt es keine Aktions-Schalter, dort bleibt das Aus im Segment.
  const withoutOff = b.type === "click" || b.type === "wait_click" || b.type === "wait";
  // Ist der Trigger bei diesen Typen aus, hat der Abschnitt keinen Inhalt: das Ein
  // und Aus macht der Schalter in AKTION, Stelle und „nur prüfen" hängen an einer
  // Bedingung, die es nicht gibt. Eine Überschrift ohne alles darunter sieht aus
  // wie ein Stück Oberfläche, das nicht geladen hat — also gar nichts zeigen.
  // Ausnahme: fehlt dem Block der Punkt, bleibt der Hinweis unten stehen. Der
  // erklärt, warum sich der Trigger nicht einschalten lässt.
  if (withoutOff && b.trigger === "kein"
      && b.point_id !== null && b.point_id !== undefined) return;
  target.appendChild(heading("FARB-TRIGGER (VOR DEM SCHRITT)",
    withTrigger
      ? "Wartet vor dem Schritt darauf, dass die Farbe des Punkts da ist (oder weg)."
      : "Dieser Block-Typ wertet keinen Farb-Trigger aus — die Laufzeit kehrt " +
        "vorher um. Die Bedingung steht nur hier, damit sie sich abschalten lässt.",
    "trigger-an"));
  if (!(withoutOff && b.trigger === "kein")) {
    target.appendChild(segment(withoutOff ? DIRECTIONS : [DIRECTION_OFF].concat(DIRECTIONS),
      b.trigger, (w) => call("block_trigger", {choice: w})));
  }
  if (b.trigger !== "kein") {
    target.appendChild(selection("Geprüfte Stelle", pointList(b.trigger_point), b.trigger_point,
      (v) => v && call("block_trigger", {choice: b.trigger, point: Number(v)}),
      "Farbe und Stelle kommen aus dem Punkt. Soll an derselben Stelle auf eine " +
      "andere Farbe geprüft werden, ist das ein eigener Punkt.", "trigger"));
    target.appendChild(toggle("nur prüfen, nicht warten", b.trigger_check,
      (on) => call("block_trigger", {choice: b.trigger, check_only: on})));
  } else if (b.point_id === null || b.point_id === undefined) {
    target.appendChild(el("p", {class: "hint"},
      "Ohne Punkt gibt es nichts zu prüfen — erst eine Stelle wählen."));
  }
}

function buildVerification(target, b) {
  // Bleibt bei JEDEM Typ: „hat die Aktion gewirkt?" ergibt auch bei einer Taste
  // und bei einem Scan Sinn — anders als der Trigger davor.
  const directions = [DIRECTION_OFF].concat(DIRECTIONS);
  target.appendChild(heading("NACHPRÜFUNG (NACH DEM SCHRITT)",
    "„Hat die Aktion gewirkt?“ Bleibt die Wirkung aus, wird die Aktion " +
    "wiederholt (verify_retries), danach greift ELSE.", "verify"));
  target.appendChild(segment(directions, b.verify,
    (w) => call("block_trigger", {which: "verify", choice: w})));
  if (b.verify !== "kein") {
    target.appendChild(selection("Geprüfte Stelle", pointList(b.verify_point), b.verify_point,
      (v) => v && call("block_trigger", {which: "verify", choice: b.verify, point: Number(v)})));
  }
}

/** Was ohne ELSE passiert — aus der Config des Hauptprozesses, nicht geraten.
 *
 * Hier stand „die Sequenz macht weiter", und das war schlicht falsch: die
 * Voreinstellung `pixel_timeout_action: "skip_cycle"` bricht den ganzen Zyklus
 * ab. Der Unterschied entscheidet, ob man ELSE ueberhaupt braucht — also gehoert
 * die echte Einstellung hierher und nicht ein allgemeiner Satz.
 */
function withoutElseText() {
  const o = S.without_else || {};
  if (!o.consequence) return "Ohne ELSE entscheidet nach dem Timeout die Einstellung " +
                       "pixel_timeout_action in der config.json.";
  const time = o.seconds > 0 ? o.seconds + " s" : "ohne Timeout";
  return "Ohne ELSE wartet der Schritt bis zum Timeout (" + time + "), danach: " +
         o.consequence + " (config.json: pixel_timeout_action)." +
         (o.emergency_stop > 0 ? " Nach " + o.emergency_stop + " Timeouts in Folge greift " +
                            "die Notbremse." : "");
}

const ELSE_DESCRIPTIONS = {
  skip: "Nur diesen Schritt überspringen.",
  skip_cycle: "Den laufenden Zyklus abbrechen und den nächsten beginnen.",
  restart: "Die Sequenz von vorn beginnen.",
  click: "Stattdessen einen anderen Punkt klicken.",
  key: "Stattdessen eine Taste drücken.",
};

function buildElse(target, b) {
  // Kein Ausloeser, kein Abschnitt: an einem reinen Klick (Taste, Warten,
  // Screenshot, Boss-Watcher) kann ELSE nie feuern.
  //
  // Ist trotzdem eine Aktion gesetzt (Trigger entfernt, Typ umgestellt, Import),
  // bleibt der Abschnitt stehen — sonst stuende das ELSE unsichtbar in der Datei
  // und waere nicht mehr loszuwerden.
  if (!b.else_applies && !b.else_action) return;
  // Kein ELSE heisst: keine Kachel markiert. Eine Kachel „(keine)" saehe aus wie
  // eine sechste Aktion, obwohl sie die Abwesenheit von allen ist.
  //
  // Der Rueckweg ist die markierte Kachel selbst — und weil man ein Umschalten
  // nicht sieht, steht es im Hinweis darunter und im Tooltip der Kachel.
  const effect = b.else_action
    ? ELSE_DESCRIPTIONS[b.else_action]
    : withoutElseText();
  target.appendChild(heading("ELSE — WENN DIE BEDINGUNG NICHT GREIFT",
    "ELSE ist ein „stattdessen“, kein „zusätzlich“: greift es, entfällt die " +
    "eigene Aktion des Schritts. " + effect +
    (b.else_action ? " Ein zweiter Klick auf die markierte Kachel hebt ELSE wieder auf." : ""),
    "else"));
  // Kacheln statt Klappmenü: die Auswahl ist fest und kurz (fünf Aktionen), und
  // im Inspektor ist der Platz da. Ein Klappmenü versteckt vier von fünf
  // Möglichkeiten hinter einem Klick — hier sieht man auf einen Blick, was es
  // überhaupt gibt. Dieselbe Form wie das Typ-Raster darüber, damit beide als
  // dasselbe Bedienelement zu erkennen sind.
  // Der Block kann gar nichts ausloesen: das gehoert VOR die Kacheln, sonst
  // stellt man erst eine Aktion ein und liest danach, dass sie nie drankommt.
  if (!b.else_applies) {
    target.appendChild(el("p", {class: "hint warning"},
      "Dieser Block hat keine Bedingung — ELSE kommt hier nie zum Zug. " +
      "Ausgelöst wird es von einem Farb-Trigger (Timeout oder „nur prüfen“), " +
      "einer Nachprüfung ohne Wirkung oder einem Scan, der nichts findet."));
  }
  target.appendChild(el("div", {class: "gitter3"}, S.else_actions.map((a) =>
    el("button", {
      // Eigene Klasse trotz gleicher Form: eine Typ-Kachel schaltet den Block-Typ,
      // eine ELSE-Kachel die Ersatzaktion. Wer eine davon später anders gestalten
      // will, soll nicht beide erwischen.
      class: "type-chip else-chip" + (a === b.else_action ? " on" : ""),
      title: ELSE_DESCRIPTIONS[a] +
             (a === b.else_action ? " Nochmal klicken = kein ELSE." : ""),
      // Dieselbe Kachel nochmal: das leere Kommando entfernt die Aktion. Eine
      // andere Kachel wechselt sie wie gewohnt.
      onclick: () => call("block_else", {action: a === b.else_action ? "" : a}),
    }, a))));
  if (b.else_action === "click") {
    target.appendChild(selection("ELSE-Punkt", pointList(b.else_point), b.else_point,
      (v) => v && call("block_else", {action: "click", point: Number(v)})));
  }
  if (b.else_action === "key") {
    target.appendChild(field("ELSE-Taste", b.else_key,
      (v) => call("block_else", {action: "key", action_key: v})));
  }
}

/* -------------------------------------------------------------------- Dialog */

function showQuestion(ask) {
  // Titel, Text und Knopfbeschriftungen kommen aus der Brücke: die Fälle
  // unterscheiden sich zu sehr, um sie hier zusammenzusetzen (bei „ausserhalb
  // geändert" gibt es nichts zu verwerfen und nichts vorher zu speichern).
  openQuestion = ask;
  $("dialog-title").textContent = ask.title || "Rückfrage";
  $("dialog-text").textContent = ask.text || "";
  $("dialog-discard").textContent = ask.proceed_label || "Weiter";
  $("dialog-save").hidden = !ask.save;
  $("veil").hidden = false;
}

function closeQuestion() {
  openQuestion = null;
  $("veil").hidden = true;
}

/* Die lokale Variable hiess `ask` und verdeckte damit den gleichnamigen
 * Bruecken-Helfer — solange hier nur `call()` vorkam, fiel das nicht auf. Sie
 * heisst jetzt `open`, damit der fragende Kanal von hier aus erreichbar ist. */
async function proceed(discard) {
  const open = openQuestion;
  closeQuestion();
  if (!open) return;
  // Löschen geht über den fragenden Kanal: es ändert Dateien, nicht die offene
  // Sequenz — eine Momentaufnahme als Antwort zerschösse den Editor-Zustand.
  // Steht vorn, weil es weder speichern noch laden will.
  if (open.kind === "seq_loeschen") {
    const answer = await ask("sequence_delete", {name: open.target});
    if (answer) setStatus({text: answer.message, kind: answer.ok ? "ok" : "warn"});
    return renderSequenceList();
  }
  if (open.kind === "save") return call("save", {force: true});
  if (!discard) await call("save");
  if (open.kind === "load") await call("load", {name: open.target, discard: true});
  else await call("new", {discard: true});
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
 * gilt `scanActiveList()`.
 *
 * Mit offenem Scan sind die Items die Arbeit: der Scan ist die Klammer, nicht
 * der Inhalt. Dieselbe Regel wie bei `collapsed` — die Vorgabe gilt, bis jemand
 * einen Reiter anfasst. */
let scanList = null;
/* Wohin der Reiter nach dem naechsten `scan_open` springt. `null` heisst
 * „zurueck auf die Vorgabe" — bei offenem Scan sind das seine Items, also das,
 * weswegen man ihn geoeffnet hat. Wer ihn aus der Scan-Liste heraus oeffnet,
 * bleibt dort stehen: sonst verschwindet die Maske, die sich gerade
 * aufgeklappt hat, samt ihren Einstellungen. */
let scanTabAfterOpen = null;
/* Was zuletzt gewaehlt war (Art + Name). Ein Klick INS BILD waehlt einen Slot,
 * und der steht in der Slot-Liste — ohne das Nachziehen passiert nach dem
 * Klick sichtbar nichts, weil gerade die Item-Liste offen ist. Nur beim
 * WECHSEL, sonst kaeme man aus der Liste nicht mehr heraus. */
let scanLastChoice = null;
let scanZoom = 1;
// Hat der Nutzer den Zoom selbst gesetzt (1:1 oder STRG+Rad)? Dann fasst ihn
// die Fenstergroesse nicht mehr an — sonst raeumte ein Verschieben des Fensters
// die gerade eingestellte Vergroesserung weg.
let scanZoomManual = false;
let scanPhotoStamp = 0;
let scanPreviews = new Map();   // Item-Name -> data:-URL des Templates
let scanPointer = null;            // letzte Mausposition im Bild (fuer die Vorschau)
let scanCategory = "";           // Kategorie-Filter der Item-Liste
let scanGuided = true;
let scanAutoSaveTimer = 0;
let scanWizardStep = null;

/* Welche Abschnitte der linken Spalte zugeklappt sind. `null` heisst „noch
 * nichts entschieden" — dann gilt `collapseDefault()`; sobald jemand einen Kopf
 * anfasst, steht dort seine Entscheidung und die Automatik schweigt.
 *
 * Reiner Oberflaechenzustand, deshalb hier und nicht in der Bruecke. */
let collapsed = {modes: null};

/* Der zuletzt in die Sichtbarkeit geholte Slot. Ohne das scrollte die Buehne
 * bei JEDEM Neuzeichnen zum gewaehlten Slot zurueck — auch dann, wenn man
 * gerade woanders hinsieht. */
let scanShown = "";

/* Ziehen eines gewaehlten Slots im Bild: Startpunkt und laufender Versatz.
 * Der Versatz wird nur GEZEICHNET; geschrieben wird einmal beim Loslassen. Ein
 * Aufruf je Mausbewegung waere ein Dutzend Brueckenaufrufe pro Sekunde und ein
 * Rueckgaengig-Stapel voll mit Ein-Pixel-Schritten. */
let scanDragStart = null;
let scanDragOffset = null;
let scanDragDone = false;
/* Wann zuletzt mit den Pfeiltasten verschoben wurde. Eine gehaltene Taste ist
 * EIN Verschieben, nicht dreissig — nur der erste Schritt kommt auf den
 * Rueckgaengig-Stapel (`counts`). */
let scanNudgeTime = 0;

/* Die Reihenfolge ist die Rangfolge und dieselbe wie in `MODI` (ein Test haelt
 * beide Zug um Zug gegeneinander). „Slots finden" steht direkt hinter
 * „Auswaehlen", weil das Automatische der Normalfall ist und das Aufziehen von
 * Hand der Ausweichweg. */
/* Die Zustandsfarben aus dem Stylesheet, damit SVG-Text und Listen dieselbe
 * Quelle benutzen wie Umriss und Fuellung. `fill` im SVG nimmt kein
 * `var(--x)` aus einer fremden Regel entgegen, also einmal auslesen. */
const SLOT_COLOR = (() => {
  const s = getComputedStyle(document.documentElement);
  return {match: s.getPropertyValue("--slot-ok").trim(),
          "foreign-item": s.getPropertyValue("--slot-fremd").trim(),
          empty: s.getPropertyValue("--slot-offen").trim()};
})();

const SCAN_MODES = [
  {key: "choice", text: "Auswählen", shortcut: "V", primary: true,
   help: "Slot anklicken — daneben zieht ein Rechteck um mehrere"},
  {key: "find", text: "Slots finden", shortcut: "G", primary: true,
   help: "Bereich aufziehen, dann leeren Slot-Hintergrund anklicken"},
  {key: "slot", text: "Neuer Slot", shortcut: "S", primary: true,
   help: "zwei Ecken anklicken — wenn Finden nicht greift"},
  {key: "measure", text: "Hintergrundfarbe", shortcut: "F", help: "Stelle im Slot anklicken"},
  {key: "click", text: "Klickpunkt", shortcut: "K", help: "wohin geklickt wird"},
  {key: "area", text: "Bereich", shortcut: "B", help: "zwei Ecken um den Teil, der zählt"},
];

async function renderScans(fresh) {
  // Nach Laden oder Umbenennen einer Sequenz darf die Scan-Aufnahme der zuvor
  // offenen Sequenz nicht weiter im Reiter stehen. Der Name ist ein billiger,
  // eindeutiger Besitzerwechsel und erzwingt dann eine frische Aufnahme.
  if (SC && S && SC.sequence !== S.name) fresh = true;
  if (fresh || !SC) {
    const answer = await ask("scan_data");
    if (!answer || view !== "scans") return;
    SC = answer;
  }
  const memo = rememberFocus();
  await scanMaintainImage();
  scanTools();
  // Erst die Art, dann alles Weitere: sie entscheidet, welche Bloecke der
  // linken Spalte ueberhaupt gelten und wo die Aufnahme-Karte gerade haengt.
  scanMaintainKind();
  scanCanvasTools();
  scanRenderResult();
  scanFollowTab();
  detRenderLibrary();
  scanOverlay();
  scanShowSelected();
  scanInspector();
  setStatus(SC.status);
  restoreFocus(memo);
}

/** Ein Befehl an den Scan-Teil der Brücke. Antwort ist die neue Scan-Aufnahme. */
async function callScan(name, data_reload) {
  const answer = await ask(name, data_reload);
  if (!answer) return;
  SC = answer;
  // Frisch von Platte heisst frisch sortiert — dort gibt es keine Zeile, in
  // der jemand gerade tippt.
  if (name === "scan_reload" || name === "scan_learn_preview_apply")
    scanOrderForget();
  // **Einen Scan zu oeffnen ist ein Wechsel des Zusammenhangs.** Danach gilt
  // wieder die Vorgabe — und die sind bei offenem Scan seine Items, also das,
  // weswegen man ihn geoeffnet hat. Vorher landete man auf der Scan-Liste und
  // sah den Namen, den man gerade angeklickt hatte, ein zweites Mal.
  if (name === "scan_open") {
    scanList = scanTabAfterOpen;
    scanTabAfterOpen = null;
    scanOrderForget();
  }
  if (name === "scan_screenshot")
    scanWizardStep = SC.steps[1].done ? 3 : 2;
  else if (name === "scan_learn_preview" || name === "scan_recognize")
    scanWizardStep = 3;
  else if (name === "scan_mode_set" && data_reload &&
           (data_reload.mode === "find" || data_reload.mode === "slot"))
    scanWizardStep = 2;
  await renderScans();
  scanScheduleAutosave(name);
}

function scanScheduleAutosave(cause) {
  clearTimeout(scanAutoSaveTimer);
  if (!SC || !SC.dirty || cause === "scan_save") return;
  const stamp = $("scan-save-state");
  if (stamp) { stamp.textContent = "Entwurf wird gespeichert …"; stamp.classList.add("open"); }
  scanAutoSaveTimer = setTimeout(async () => {
    const answer = await ask("scan_save");
    if (!answer) return;
    SC = answer;
    await renderScans();
  }, 900);
}

function scanCanvasTools() {
  const ready = scanConfigOpen();
  const viewName = $("view-scans");
  viewName.classList.toggle("guided", scanGuided);
  viewName.classList.toggle("has-image", photoPresent());
  $("scan-free").textContent = scanGuided ? "Alle Werkzeuge" : "Nur Assistent";
  document.querySelectorAll("[data-scan-tool]").forEach((button) => {
    button.classList.toggle("on", SC.mode === button.dataset.scanTool);
    button.disabled = (!ready || !SC.pillow) && button.dataset.scanTool !== "choice";
  });
  const mode = SCAN_MODES.find((m) => m.key === SC.mode);
  const det = {region: "Region aufziehen",
               action: scanKind === "item" ? "Bestätigungsklick setzen"
                                          : "Klickpunkt setzen"}[SC.mode];
  $("scan-tool-state").textContent = !ready
    ? "Zuerst einen Scan anlegen oder auswählen"
    : SC.mode === "choice"
    ? (scanKind === "item" ? "Slot anklicken zum Bearbeiten"
                          : "Werkzeug wählen oder rechts ein Feld ändern")
    // Beim Aufziehen steht der STAND dabei, nicht nur der Name des Werkzeugs:
    // ohne ihn sieht man dem Bild nicht an, ob schon eine Ecke gesetzt ist.
    : "Aktiv: " + (det || (mode ? mode.text : SC.mode))
      + (SC.corner ? " — erste Ecke gesetzt, zweite Ecke anklicken · ESC bricht ab" : "");
  $("scan-tool-state").classList.toggle("kind-warn", !!SC.corner);
  $("scan-pin").classList.toggle("on", !!SC.tool_pinned);
  $("scan-pin").hidden = SC.mode === "choice";
  $("scan-pin").setAttribute("aria-pressed", String(!!SC.tool_pinned));
  $("scan-pin-lang").textContent = SC.tool_pinned ? "Angeheftet" : "Anheften";
  $("scan-pin-kurz").textContent = SC.tool_pinned ? "Pin ✓" : "Pin";
  const stamp = $("scan-save-state");
  stamp.textContent = SC.dirty ? "Wird gespeichert …" : "✓ Gespeichert";
  stamp.classList.toggle("open", !!SC.dirty);
}

function scanRenderResult() {
  const target = $("scan-result");
  target.replaceChildren();
  // Boss und Icon haben ein anderes Ergebnis als ein Item-Scan: EIN Treffer
  // statt 45. Dieselbe Leiste, weil es dieselbe Frage ist — „was hat der Test
  // ergeben" —, aber ein anderer Inhalt.
  if (scanKind !== "item") {
    target.hidden = !detTestBar(target);
    return;
  }
  const e = SC.result;
  target.hidden = !e;
  if (!e) return;
  target.append(
    el("b", {}, "Testergebnis"),
    el("span", {class: "metric", style: "color:var(--ok)"}, e.detected + " erkannt"),
    el("span", {class: "metric", style: "color:var(--accent)"}, e.unbekannt + " unbekannt"),
    el("span", {class: "grow"})
  );
  if (e.unbekannt) target.appendChild(el("button", {class: "btn quiet",
    onclick: () => scanResultNext("unknown_slots")}, "Nächsten unbekannten zeigen"));
}

function scanResultNext(field) {
  const names = (SC.result && SC.result[field]) || [];
  if (!names.length) return;
  const current = names.indexOf(SC.choice.name);
  const name = names[(current + 1) % names.length];
  callScan("scan_select", {kind: "slot", name: name});
}

/** Gibt es ein echtes Bild — oder nur die aus den Slots gerechnete Flaeche? */
function photoPresent() { return !!(SC && SC.photo && SC.photo.image); }

/** Hat die aktuelle Art ein eindeutiges Ziel für Bild, Slots und Regionen? */
function scanConfigOpen() {
  return !!(SC && SC.recording_ready && SC.recording_ready[scanKind]);
}

/** Holt das Bild nur, wenn es ein neues gibt — es ist der grosse Brocken. */
async function scanMaintainImage() {
  const image = $("scan-image");
  const empty = $("scan-empty");
  if (!SC.photo) {
    $("scan-surface").hidden = true;
    $("scan-no-image").hidden = true;
    empty.hidden = false;
    empty.textContent = !scanConfigOpen()
      ? "Zuerst oben einen Scan anlegen oder auswählen. Danach kann ein Screenshot aufgenommen werden."
      : SC.pillow
      ? "Noch kein Bild. „Screenshot aufnehmen“ friert den Bildschirm ein — darauf werden die Slots aufgezogen."
      : "Ohne Pillow gibt es kein Bild (pip install pillow). Slots lassen sich dann nur über die Zahlenfelder rechts setzen.";
    return;
  }
  $("scan-surface").hidden = false;
  empty.hidden = true;
  // Ohne Bild bleibt die Flaeche leer, aber sie hat die Groesse und die Lage
  // der Slots — man sieht also, was der Scan hat, und kann es anfassen.
  $("scan-surface").classList.toggle("no-image", !photoPresent());
  $("scan-no-image").hidden = photoPresent();
  // Woran man merkt, dass eine ANDERE Flaeche dasteht: beim Bild der
  // Zeitstempel, sonst ihre Groesse. Ohne diese Marke passte entweder gar
  // nichts mehr ein (Zoom vom vorigen Scan) oder bei jedem Neuzeichnen wieder,
  // was jedes Hineinzoomen sofort zuruecksetzte.
  const badge = photoPresent() ? SC.photo.stamp
                         : -(SC.photo.width * 100000 + SC.photo.height);
  if (badge !== scanPhotoStamp) {
    scanPhotoStamp = badge;
    if (photoPresent()) {
      const url = await ask("scan_image");
      if (url) image.src = url;
    } else {
      image.removeAttribute("src");
    }
    scanFit();
  }
  $("scan-size").textContent = photoPresent()
    ? SC.photo.width + "×" + SC.photo.height
    : "kein Bild";
}

function scanFit() {
  if (!SC || !SC.photo) return;
  const slotNr = $("scan-stage").clientWidth - 24;
  // Ein Bild wird nie vergroessert — jedes Pixel darueber waere erfunden, und
  // gemessen wird ohnehin im Original. Die aus den Slots gerechnete Flaeche hat
  // keine Pixel, die man faelschen koennte: sie darf die Buehne fuellen, sonst
  // haengt ein Inventar von 300 px verloren in einer Ecke.
  const limit = photoPresent() ? 1 : 4;
  scanZoom = Math.max(0.05, Math.min(limit, slotNr / SC.photo.width));
  scanZoomManual = false;
  scanApplyZoom();
}

function scanApplyZoom() {
  if (!SC || !SC.photo) return;
  const f = $("scan-surface");
  f.style.width = Math.round(SC.photo.width * scanZoom) + "px";
  // Die Hoehe kommt sonst vom Bild. Ohne eines waere sie 0, und die Flaeche
  // haette weder Platz fuer die Slots noch etwas zum Anklicken.
  f.style.height = photoPresent() ? "" : Math.round(SC.photo.height * scanZoom) + "px";
  $("scan-zoom").textContent = Math.round(scanZoom * 100) + " %";
  scanOverlay();
}

/* ---- Umrechnung: Bildschirm <-> Bild. Die einzige Stelle, die das darf. ---- */

function scanToImage(x, y) {
  const f = SC.photo;
  return [(x - f.left) * f.scale, (y - f.top) * f.scale];
}

function scanToScreen(bx, by) {
  const f = SC.photo;
  return [Math.round(f.left + bx / f.scale), Math.round(f.top + by / f.scale)];
}

function scanTools() {
  $("scan-sequence").textContent = SC.sequence || "— keine Sequenz —";
  const choice = $("scan-open");
  choice.replaceChildren();
  choice.appendChild(el("option", {value: ""}, SC.scans.length
    ? "— keiner (ganzer Bestand) —" : "— noch kein Item-Scan —"));
  for (const c of SC.scans) {
    const o = el("option", {value: c.name}, c.name);
    if (c.name === SC.open) o.selected = true;
    choice.appendChild(o);
  }
  const open = SC.scans.find((c) => c.name === SC.open);
  const ready = scanConfigOpen();
  $("scan-stage").classList.toggle("search-active", SC.mode === "find");
  const nameField = $("scan-name");
  nameField.value = open ? open.name : "";
  nameField.disabled = !open;
  $("scan-scope").textContent = open
    ? open.slots.length + " Slots · " + open.items.length + " Items"
    : SC.slots.length + " Slots · " + SC.items.length + " Items";

  const target = $("scan-modes");
  target.replaceChildren();
  for (const m of SCAN_MODES) {
    const on = SC.mode === m.key;
    target.appendChild(el("button", {
      class: "scan-mode" + (on ? " on" : ""),
      disabled: !ready,
      // Ein Umschalten sieht man einem Bedienelement nicht an — dieselbe Regel
      // wie bei der ELSE-Kachel im Inspektor. Es steht deshalb im Tooltip der
      // markierten Kachel UND im Hinweis unter dem Raster.
      title: on && m.key !== "choice"
        ? "Nochmal klicken = zurück zum Auswählen" : "",
      onclick: () => callScan("scan_mode_set", {mode: m.key, kind: scanKind}),
    },
      el("span", {}, m.text),
      el("span", {class: "key"}, m.shortcut),
      el("span", {class: "small"}, m.help)));
  }
  $("scan-modes-back").hidden = SC.mode === "choice";
  // **Was man ZWISCHENDURCH tut, braucht keinen Modus** — und die Erklaerung
  // dazu keinen eigenen Absatz. Sie stand als vier Zeilen Text unter den
  // Kacheln; das ⓘ zeigt sie auf Wunsch und merkt sich, ob es offen war.
  $("scan-photo-info").replaceChildren("Woher das Bild kommt", info(
    "Items werden aus diesem eingefrorenen Bild gelernt. Beim Lauf wird "
    + "dasselbe Fenster mit derselben Aufnahmemethode neu aufgenommen; die "
    + "Slots folgen seiner Position automatisch.", "recording"));
  $("scan-modes-direct").replaceChildren("Ohne Moduswechsel", info(
    "ALT+Klick misst den Hintergrund eines Slots, Doppelklick setzt seinen "
    + "Klickpunkt — beides wählt ihn gleich mit aus. Ein gewählter Slot lässt "
    + "sich mit der Maus ziehen oder mit den Pfeiltasten verschieben "
    + "(SHIFT = 10 px).", "direkt"));
  const mode = SCAN_MODES.find((m) => m.key === SC.mode);
  $("scan-mode-short").textContent = mode ? mode.text : "";
  maintainCollapse();
  scanSteps();
  $("scan-photo").disabled = !SC.pillow || !ready;
  const windowSource = !!(SC.window_title || SC.window_id);
  $("scan-photo").textContent = windowSource ? "Fenster aufnehmen"
    : (SC.area ? "Bereich aufnehmen" : "Screenshot aufnehmen");

  // Der Bereich gilt fuer JEDE weitere Aufnahme dieses Scans — er muss also
  // dastehen, nicht nur in der Statuszeile aufblitzen.
  const sourceInfo = $("scan-source-info");
  const sourceName = $("scan-source-name");
  const bz = $("scan-area");
  const size = SC.area
    ? (SC.area[2] - SC.area[0]) + "×" + (SC.area[3] - SC.area[1])
    : "";
  sourceName.textContent = windowSource
    ? "Fenster „" + (SC.window_title || "gewählt") + "“"
    : (SC.area ? "Eigener Bildschirmausschnitt" : "Ganzer Bildschirm");
  const sourceDetails = [];
  if (windowSource) sourceDetails.push("Slots relativ");
  if (size) sourceDetails.push(size);
  if (!windowSource && SC.area) {
    sourceDetails.push("Position " + SC.area[0] + ", " + SC.area[1]);
  }
  if (!SC.window_available && SC.window_title) {
    sourceDetails.push("Fenster nicht geöffnet");
  }
  bz.textContent = sourceDetails.join(" · ");
  bz.hidden = !sourceDetails.length;
  // Bei einem gewaehlten Fenster steht dabei, was das bedeutet: es wird direkt
  // abgebildet, also darf das Studio davor liegen.
  sourceInfo.title = windowSource
    ? "Editor und Live-Scan verwenden dieselbe Aufnahmequelle. Verschieben wird automatisch ausgeglichen; beim Desktop-Fallback muss das Fenster sichtbar sein."
    : (SC.area ? "Ausschnitt vom Bildschirm — hier darf nichts davor liegen." : "");
  sourceInfo.classList.toggle("on", !!SC.area || windowSource);
  $("scan-fullscreen").disabled = !ready || (!SC.area && !windowSource) || !SC.pillow;
  // Aufziehen geht nur auf einem Bild — vorher gibt es nichts anzuklicken.
  const up = $("scan-draw-area");
  up.disabled = !ready || !photoPresent();
  up.classList.toggle("on", SC.mode === "area");
  scanMaintainWindows();
}

/** Nur die technischen Sonderwerkzeuge sind noch ein klassischer Klappbereich. */
function collapseDefault(key) { return false; }

function maintainCollapse() {
  for (const [key, id] of [["modes", "sec-modes"]]) {
    const closed = collapsed[key] === null ? collapseDefault(key)
                                            : collapsed[key];
    $(id).classList.toggle("closed", closed);
  }
}

/** Ein Assistent mit genau einer offenen Aufgabe und jederzeit erreichbaren Schritten. */
function scanSteps() {
  if (!scanWizardStep) {
    const open = SC.steps.find((s) => !s.done);
    scanWizardStep = open ? open.nr : 3;
  }
  for (const s of SC.steps) {
    const cardEl = $("scan-wizard-" + s.nr);
    const open = scanWizardStep === s.nr;
    cardEl.classList.toggle("open", open);
    cardEl.classList.toggle("done", s.done);
    $("scan-step-" + s.nr + "-nr").textContent = s.done ? "✓" : String(s.nr);
    $("scan-step-" + s.nr + "-body").hidden = !open;
  }
  const scan = SC.scans.find((c) => c.name === SC.open);
  const slots = scan ? scan.slots.length : SC.slots.length;
  const items = scan ? scan.items.length : SC.items.length;
  $("scan-step-1-status").textContent = photoPresent()
    ? "Bild gespeichert · " + SC.photo.width + "×" + SC.photo.height : "Noch kein Bild";
  $("scan-step-2-status").textContent = slots
    ? slots + (slots === 1 ? " Slot" : " Slots") : "Noch keine Slots";
  $("scan-step-3-status").textContent = items
    ? items + (items === 1 ? " Item" : " Items") : "Noch keine Items";
  const ready = !!(SC.recording_ready && SC.recording_ready.item);
  $("scan-slots-find").disabled = !ready || !photoPresent() || !SC.pillow;
  $("scan-slot-new").disabled = !ready || !photoPresent() || !SC.pillow;
  $("scan-test").disabled = !ready || !photoPresent() || !slots;
  $("scan-learn").disabled = !ready || !photoPresent() || !slots;
}

let scanWindows = [];

/** Die offenen Fenster zur Auswahl — nur nachgeholt, wenn Pillow da ist. */
async function scanMaintainWindows() {
  const choice = $("scan-window");
  const neu = $("scan-window-capture");
  const ready = scanConfigOpen();
  neu.disabled = !SC.pillow || !ready;
  if (!SC.pillow) { choice.hidden = true; return; }
  choice.disabled = !ready;
  scanWindows = (await ask("scan_windows")) || [];
  choice.hidden = false;
  choice.replaceChildren();
  choice.appendChild(el("option", {value: ""}, scanWindows.length
    ? "— kein Fenster (ganzer Bildschirm) —" : "— keine Fenster gefunden —"));
  scanWindows.forEach((f, i) => {
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
    choice.appendChild(o);
  });
  if (SC.window_title && !scanWindows.some((f) => f.id === SC.window_id)) {
    choice.appendChild(el("option", {
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
function scanCardsRight() {
  return scanKind === "item";
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
 * Ein Ort, ein Bauplan (`scanListBlock`).
 *
 * Als Masken kommen nur die Item-Listen (`scanCardsRight()`): dort stehen
 * Dutzende gleichartiger Dinge nebeneinander. Ein Boss- oder Icon-Scan ist
 * EINES — Region, Erkennung, Aktion —, das traegt keine Maske, und seine Liste
 * ist drei Zeilen lang. */

/** Welche Liste gilt: die gewaehlte, sonst die zur Lage passende Vorgabe. */
function scanActiveList() {
  if (scanList) return scanList;
  if (scanKind === "boss") return "bosses";
  if (scanKind === "icon") return "icons";
  return SC && SC.open ? "items" : "scans";
}

/** Namen so vergleichen, wie man sie liest: „Slot 2" vor „Slot 10".
 *
 * Ein reiner Zeichenvergleich sortiert „Slot 10" zwischen „Slot 1" und
 * „Slot 2" — bei fünfundvierzig durchnummerierten Slots ist die Liste damit
 * unbrauchbar, obwohl sie sortiert ist. */
function byName(a, b) {
  return String(a).localeCompare(String(b), "de", {numeric: true});
}

/** Der Anker, an dem der Fokus einen Neuaufbau ueberlebt — eine id je Maske.
 *
 * Ohne sie zaehlt `rememberFocus()` die Position ueber die ganze Spalte, und die
 * drei Felder, die man dort tippt, sortieren die Liste gerade um. */
function cardId(kind, name) { return "maske:" + kind + ":" + name; }

/** Der Reiter folgt der Auswahl — aber nur, wenn sie sich geaendert hat.
 *
 * Ein Klick im Bild waehlt einen Slot. Steht gerade die Item-Liste offen,
 * geschieht rechts sonst nichts, und der Klick sieht wirkungslos aus. Beim
 * blossen Neuzeichnen darf dagegen nichts umschalten: sonst waere der Weg aus
 * der Slot-Liste heraus versperrt, solange ein Slot gewaehlt ist. */
function scanFollowTab() {
  if (!SC || scanKind !== "item") return;
  const now = SC.choice.kind + ":" + SC.choice.name;
  if (now === scanLastChoice) return;
  const first = scanLastChoice === null;
  scanLastChoice = now;
  // Der Scan hat seinen eigenen Weg (`scanTabAfterOpen`); und beim
  // allerersten Zeichnen gibt es keinen Wechsel, nur einen Anfangszustand.
  if (first) return;
  const target = {slot: "slots", item: "items"}[SC.choice.kind];
  if (target && scanActiveList() !== target) scanList = target;
}

/** Reiter, Filter und Liste — ein Bauplan, ein Ort. */
function scanListBlock(tabs, filter, target) {
  const open = scanActiveList();
  // Kopf und Liste werden getrennt gebaut (der Kopf klebt oben, die Liste
  // scrollt) — gerufen wird dieselbe Funktion zweimal, damit die Zuordnung
  // Reiter -> Inhalt an EINER Stelle steht und nicht an zweien auseinanderlaeuft.
  const on = (whereTo, kind) => { if (whereTo) whereTo.appendChild(kind); };
  if (scanKind !== "item") {
    if (scanKind === "icon") {
      on(tabs, el("button", {class: "tab on"},
        "Icon-Scans " + SC.icon_scans.length));
      return target ? detListIcons(target) : undefined;
    }
    // Zwei Listen, weil es zwei Orte sind: die Bosse DIESES Scans und die,
    // die in jedem gelten. Sie zusammenzuwerfen hiesse, den Unterschied zu
    // verlieren, an dem alles haengt.
    for (const [key, text, number] of [["bosses", "Bosse", detBosses().length],
                                     ["bibliothek", "Bibliothek",
                                      SC.global_bosses.length]]) {
      on(tabs, el("button", {class: "tab" + (open === key ? " on" : ""),
        onclick: () => { scanList = key; renderScans(); }}, text + " " + number));
    }
    if (!target) return undefined;
    return open === "bibliothek" ? detListLibrary(target) : detListBosses(target);
  }
  // Die Zahl am Reiter ist die der SICHTBAREN Eintraege — sonst stuende dort 40,
  // waehrend zwei in der Liste stehen, und man sucht den Rest.
  // Reihenfolge = Rangfolge: der Scan ist das Uebergeordnete, Slots und Items
  // haengen an ihm.
  const groups = [["scans", "Scans", SC.scans.length, SC.scans.length],
                   ["slots", "Slots", scanVisible(SC.slots, false, "slot").length, SC.slots.length],
                   ["items", "Items", scanVisible(SC.items, true, "item").length, SC.items.length]];
  for (const [key, text, visible, total] of groups) {
    on(tabs, el("button", {
      class: "tab" + (open === key ? " on" : ""),
      title: visible === total ? "" : total + " insgesamt",
      onclick: () => { scanList = key;
                       scanOrderForget(); renderScans(); },
    }, text + " " + visible + (visible === total ? "" : "/" + total)));
  }
  if (filter) scanFilterRow(filter, open);
  if (!target) return undefined;
  if (open === "slots") return scanListSlots(target);
  if (open === "items") return scanListItems(target);
  return scanListScans(target);
}

/** Was die Liste einschraenkt: Kategorie; Bestand gehoert immer zum Scan. */
function scanFilterRow(filter, open) {
  if (SC.open && open !== "scans") {
    const kind = open === "slots" ? "slot" : "item";
    const total = open === "slots" ? SC.slots : SC.items;
    filter.appendChild(el("button", {class: "btn danger", disabled: !total.length,
      title: total.length
        ? "Löscht alle " + total.length + " " + (kind === "slot" ? "Slots" : "Items")
          + " aus „" + SC.open + "“ — nicht nur aus der Mitgliedschaft. "
          + "STRG+Z nimmt es zurück."
        : "Nichts zu löschen.",
      onclick: () => callScan("scan_delete_all", {kind: kind})},
      total.length + " " + (kind === "slot" ? "Slots" : "Items") + " löschen"));
  }
  if (open === "items" && SC.categories.length) {
    filter.appendChild(selection("", [{value: "", text: "alle Kategorien"}].concat(
      SC.categories.map((k) => ({value: k, text: k}))), scanCategory,
      (v) => { scanCategory = v; renderScans(); }));
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
let scanOrder = {item: null, slot: null};

function scanOrderForget() {
  scanOrder = {item: null, slot: null};
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
function scanOrderGroup(kind) {
  const memo = scanOrder[kind];
  if (!memo) return null;
  const groups = new Map();
  for (const e of memo) groups.set(e.name, e.group);
  return (name) => (groups.has(name) ? groups.get(name) : null);
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
function scanOrderRename(kind, alt, neu) {
  const memo = scanOrder[kind];
  if (!memo || !neu || alt === neu) return;
  const i = memo.findIndex((e) => e.name === alt);
  if (i >= 0) memo.splice(i, 1, {name: neu, group: memo[i].group}, memo[i]);
}

/** Die gemerkte Vorschau auf den neuen Namen mitnehmen.
 *
 * Der Zwischenspeicher haengt am ITEM-Namen, das Bild aber an der
 * Template-DATEI — und die heisst nach dem Umbenennen genauso wie vorher. Ohne
 * das Mitnehmen galt die Vorschau als fehlend: die Maske wurde einmal ohne Bild
 * gezeichnet, `scanFetchPreviews()` holte dieselben Bytes noch einmal aus
 * Python und baute die Spalte danach ein zweites Mal auf. Sichtbar war das als
 * kurzes Flackern beim Umbenennen — dasselbe Bild, zwei Neuaufbauten.
 *
 * Der alte Eintrag bleibt stehen, aus demselben Grund wie bei
 * `scanOrderRename()`: lehnt die Bruecke den neuen Namen ab (Dublette,
 * leer), zeigt die Maske weiter unter dem alten Namen — und braucht dort ihr
 * Bild.
 */
function scanPreviewRename(kind, alt, neu) {
  if (kind !== "item" || !neu || alt === neu) return;
  const image = scanPreviews.get(alt);
  if (image) scanPreviews.set(neu, image);
}

/** Die gemerkte Reihenfolge als Rang je Name; unbekannt = ans Ende. */
function scanOrderRank(kind) {
  const memo = scanOrder[kind];
  if (!memo) return null;
  const rankNr = new Map();
  memo.forEach((e, i) => rankNr.set(e.name, i));
  return (name) => (rankNr.has(name) ? rankNr.get(name) : Number.MAX_SAFE_INTEGER);
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
function scanVisible(entries, withCategory, kind) {
  let listEl = entries;
  if (withCategory && scanCategory)
    listEl = listEl.filter((e) => (e.category || "") === scanCategory);
  return listEl;
}

/** Ein Namensfeld in einer Maske — mit dem Fokus-Anker fuer das Umbenennen. */
function cardName(kind, name, title, setter) {
  const field = el("input", {value: name, autocomplete: "off", title: title});
  field.addEventListener("change", () => {
    const neu = field.value.trim();
    // DREI Dinge haengen am Namen: der Anker fuer den Fokus, der Rang in der
    // Liste und die gemerkte Vorschau. Wer umbenennt, sagt allen dreien vorher
    // Bescheid — wer eines vergisst, sieht es sofort: der Fokus springt weg,
    // die Zeile wandert, oder das Bild blinkt.
    focusRename(cardId(kind, name), cardId(kind, neu));
    scanOrderRename(kind, name, neu);
    scanPreviewRename(kind, name, neu);
    setter(field.value);
  });
  field.addEventListener("keydown", (e) => { if (e.key === "Enter") field.blur(); });
  return field;
}

/** Das Gehaeuse einer Maske: id, Auswahl-Ring, Klick zum Waehlen, Detailteil.
 *
 * **Eine Bauform fuer Scans, Slots und Items.** Sie unterscheiden sich in dem,
 * was drinsteht — nicht darin, wie man sie anfasst. Vorher waren es drei
 * Formen an zwei Orten, und ein Slot liess sich nur ueber vier Zahlenfelder
 * bearbeiten, waehrend ein Item eine Maske hatte. */
function buildCard(kind, name, selected, parts, detail, onChoose) {
  const card = el("div", {class: "scan-card" + (selected ? " on" : ""),
                           id: cardId(kind, name)});
  for (const part of parts) card.appendChild(part);
  if (selected && detail) {
    const boxEl = el("div", {class: "scan-card-detail"});
    detail(boxEl);
    card.appendChild(boxEl);
  }
  // Ein Klick auf die Maske waehlt sie; ein zweiter klappt ein offenes Item
  // wieder zu. Felder und Knoepfe sind davon ausgenommen, sonst wuerde schon
  // das Bearbeiten den Detailteil unter der Hand schliessen.
  card.addEventListener("click", (e) => {
    if (e.target.closest("input, label, button, select, summary, details")) return;
    if (selected && kind === "item") {
      callScan("scan_select", {kind: "item", name: ""});
    } else if (!selected) {
      onChoose();
    }
  });
  return card;
}

function scanListSlots(target) {
  // **Die stabile ID ist die Reihenfolge.** Scan-Position, Name und Reihenfolge
  // in der Datei koennen sich aendern; die ID bezeichnet den Slot dauerhaft.
  // Deshalb gilt sie auch ueber die Grenze „gehoert zum offenen Scan" hinweg.
  // Alte oder ungueltige IDs landen am Ende und werden dort nach Namen stabil
  // geordnet — die Ansicht erfindet keine Reparatur fuer Bestandsdaten.
  const rankNr = scanOrderRank("slot");
  const listEl = scanVisible(SC.slots, false, "slot").slice().sort((a, b) =>
    rankNr ? (rankNr(a.name) - rankNr(b.name))
         : (((Number(a.id) > 0 ? Number(a.id) : Number.MAX_SAFE_INTEGER)
              - (Number(b.id) > 0 ? Number(b.id) : Number.MAX_SAFE_INTEGER))
             || byName(a.name, b.name)));
  if (!rankNr) scanOrder.slot = listEl.map((s) => ({name: s.name, group: ""}));
  if (!listEl.length) {
    target.appendChild(el("p", {class: "hint"}, SC.slots.length
      ? "Kein Slot gehört zu diesem Scan. Den Filter ausschalten und Häkchen setzen."
      : "Noch keine Slots. Modus „Slots finden“ — oder „Neuer Slot“ und zwei "
        + "Ecken im Bild anklicken."));
    return;
  }
  for (const s of listEl) target.appendChild(scanSlotCard(s));
}

/** Ein Slot als Maske — dieselbe Bauform wie beim Item.
 *
 * **Was man an einem Slot tippt, ist sein Name; alles andere zieht man im
 * Bild.** Deshalb traegt die zweite Zeile keinen Regler, sondern den Stand:
 * Groesse, Klickpunkt und was zuletzt darin erkannt wurde. Die Zahlen dazu
 * klappen im Detailteil auf, wie beim Item die Konfidenz. */
function scanSlotCard(s) {
  const setter = (field, value) => callScan("scan_slot_set",
                                        {name: s.name, field: field, value: value});
  const selected = SC.selection.includes(s.name)
                || (SC.choice.kind === "slot" && SC.choice.name === s.name);
  const name = cardName("slot", s.name,
    "Name — zugleich die Referenz in jedem Scan", (v) => setter("name", v));
  // **Die ID ist eine reine Anzeige-Kachel, kein Knopf.** Sie bleibt gleich,
  // auch wenn der Slot im offenen Scan ab- und wieder angeschaltet wird — DAS
  // ändert nur seine STELLE (er wandert ans Ende der Mitgliederliste), nicht
  // seine Identität. Die Stelle steht deshalb nur noch im Tooltip, nicht mehr
  // in der Zahl selbst.
  const id = el("span", {class: "num",
    title: s.number
      ? "Slot-ID #" + s.id + " — bleibt gleich, auch beim Ab-/Wieder-Anschalten. "
        + "Läuft in „" + SC.open + "“ als " + s.run_index + ". von " + s.total + "."
        + (s.run_index !== s.number ? " (rückwärts)" : "")
      : "Slot-ID #" + s.id + " — bleibt gleich, auch beim Ab-/Wieder-Anschalten."},
    "#" + s.id);
  const box = el("input", {type: "checkbox",
    "aria-label": s.name + " ein- oder ausschalten"});
  box.checked = !!s.active;
  box.addEventListener("change", () => setter("active", box.checked));
  const onOff = el("label", {class: "on scan-slot-toggle",
    title: s.active ? "Slot ist aktiv — ausschalten" : "Slot ist aus — einschalten"}, box);
  const fields = el("div", {class: "scan-card-fields"}, name, scanSlotState(s));
  const card = buildCard("slot", s.name, selected,
    [el("div", {class: "scan-badge"}, onOff, id),
     el("span", {class: "dot" + (s.color ? "" : " without"),
                  title: s.color ? "Hintergrund " + s.color : "Hintergrund nicht gemessen",
                  style: s.color ? "background:" + s.color : ""}),
     fields],
    (boxEl) => scanSlotDetails(boxEl, s),
    () => callScan("scan_select", {kind: "slot", name: s.name}));
  card.classList.toggle("off", !s.active);
  return card;
}

/** Die Zustandszeile eines Slots: Groesse, Warnung, letzter Treffer. */
function scanSlotState(s) {
  // Die Groesse ist ein gemessener WERT, kein Satz — also dieselbe Kachel wie
  // die Nummer daneben. Was daneben steht („Item 1", „unbekannt", „→ Helme"),
  // ist eine Aussage und bleibt Text.
  const parts = [el("span", {class: "num"}, s.width + "×" + s.height)];
  if (!s.active) parts.push(el("span", {class: "small slot-off"}, "aus"));
  // Ein winziger Slot ist im Bild kaum zu treffen — in der Liste ist er so
  // gross wie jeder andere. Deshalb steht die Warnung HIER: das ist der Weg,
  // ihn auszuwaehlen und zu loeschen.
  if (s.tiny) {
    parts.push(el("span", {class: "small", style: "color:var(--err)",
      title: "Zu klein zum Erkennen — hier auswählen und löschen"}, "⚠ zu klein"));
  } else if (s.match && s.match.name) {
    parts.push(el("span", {class: "small",
      style: "color:var(" + (s.match.foreign ? "--slot-fremd" : "--slot-ok") + ")",
      title: s.match.foreign
        ? "erkannt, gehört aber noch nicht zu diesem Scan" : ""}, s.match.name));
  } else if (s.match) {
    // Nichts erkannt = hier ist noch zu lernen. Dieselbe Farbe wie sein
    // Rechteck im Bild, damit Liste und Bild zusammengehen.
    parts.push(el("span", {class: "small", style: "color:var(--slot-offen)"},
                  "unbekannt"));
  }
  return el("div", {class: "scan-card-state"}, parts);
}

function scanListItems(target) {
  // **Gesortiert wird nur auf Ansage.** Steht eine gemerkte Reihenfolge, gilt
  // ausschliesslich sie — auch fuer die Gruppen, denn die Kategorie war als
  // erster Schluessel das letzte Feld, das die Zeile noch wegspringen liess.
  // Ohne Merkposten (erster Aufbau, „Sortieren", Neu laden) wird frisch geordnet.
  const rankNr = scanOrderRank("item");
  const group = scanOrderGroup("item");
  const fresh = (a, b) =>
    (SC.open ? Number(!!b.included) - Number(!!a.included) : 0) ||
    a.priority - b.priority || a.name.localeCompare(b.name, "de");
  const listEl = scanVisible(SC.items, true, "item").slice().sort((a, b) =>
    rankNr ? (rankNr(a.name) - rankNr(b.name)) || fresh(a, b)
         : ((a.category || "").localeCompare(b.category || "", "de")
            || fresh(a, b)));
  if (!rankNr) {
    scanOrder.item = listEl.map((i) => ({name: i.name, group: i.category || ""}));
  }
  if (!listEl.length) {
    target.appendChild(el("p", {class: "hint"}, SC.items.length
      ? "Kein Item passt zum Filter. Der Bestand hat " + SC.items.length + " Stück."
      : "Noch keine Items. Einen Slot wählen und „Item lernen“ — oder alle "
        + "Slots auf einmal."));
    return;
  }
  scanFetchPreviews(listEl.map((i) => i.name));
  let lastCategory = null;
  for (const i of listEl) {
    // Die Ueberschrift kommt aus der EINGEFRORENEN Gruppe, nicht aus dem
    // aktuellen Wert: sonst reisst ein gerade geaendertes Item eine zweite
    // Ueberschrift mitten in die Liste. Wo es hinwandert, sagt seine Maske.
    const frozen = group ? group(i.name) : null;
    const category = (frozen === null ? (i.category || "") : frozen)
                      || "Ohne Kategorie";
    if (category !== lastCategory) {
      target.appendChild(scanCategoryHeader(category, listEl));
      lastCategory = category;
    }
    target.appendChild(scanItemCard(i, frozen));
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
function scanCategoryHeader(category, listEl) {
  const empty = category === "Ohne Kategorie";
  const value = empty ? "" : category;
  const count = listEl.filter((i) => (i.category || "") === value).length;
  const field = el("input", {class: "scan-category-field", value: value,
    placeholder: "ohne Kategorie",
    title: "Umbenennen zieht alle Items dieser Gruppe mit. Leer = Kategorie "
           + "entfernen. Gleicher Name wie eine andere Gruppe = zusammenlegen."});
  field.addEventListener("change", () => {
    if (field.value.trim() === value) return;
    callScan("scan_category_rename", {alt: value, neu: field.value.trim()});
  });
  field.addEventListener("keydown", (e) => { if (e.key === "Enter") field.blur(); });
  return el("div", {class: "scan-category-header"}, field,
            el("span", {class: "num"}, String(count)));
}

/** Ein Item als kleine Maske: Haken, Name, Kategorie, Prioritaet — in der Liste.
 *
 * Ein Ein-Aus-Knopf war zu wenig: alles andere kostete einen Klick in die Liste,
 * einen Blick nach rechts und einen Weg zurueck, bei sechzig Items sechzig Mal.
 *
 * Was selten gebraucht wird (Vorlagen, Marker, Konfidenz, Loeschen), klappt
 * darunter auf. Name, Kategorie und Prioritaet stehen NUR hier — dieselbe Sache
 * an zwei Stellen waeren zwei Wahrheiten. */
function scanItemCard(i, frozen) {
  const setter = (field, value) => callScan("scan_item_set",
                                        {name: i.name, field: field, value: value});
  const selected = SC.choice.kind === "item" && SC.choice.name === i.name;
  const image = scanPreviews.get(i.name);

  const box = el("input", {type: "checkbox",
    "aria-label": i.name + " ein- oder ausschalten"});
  box.checked = !!i.active;
  box.addEventListener("change", () => setter("active", box.checked));
  const onOff = el("label", {class: "on scan-slot-toggle",
    title: i.active ? "Item ist aktiv — ausschalten" : "Item ist aus — einschalten"}, box);

  const name = cardName("item", i.name,
    "Name — zugleich die Referenz in jedem Scan", (v) => setter("name", v));

  // Vorhandene anklicken, neue tippen — dasselbe Bedienelement wie in der
  // Lern-Vorschau. Ein freies Textfeld allein macht aus „Helme" und „helme"
  // zwei Kategorien, und Items derselben Kategorie konkurrieren miteinander.
  const cat = categoryChooser(i.category || "", (v) => setter("category", v),
    {title: "Items derselben Kategorie konkurrieren; die kleinere Priorität gewinnt",
     empty: "— ohne —", key: "item:" + i.name});

  // **Die Zahl allein sagt nicht, ob sie frei ist.** Teilt sich das Item seinen
  // Rang mit einem anderen derselben Kategorie, entscheidet die Scan-Reihenfolge
  // — also der Zufall. Das steht am Feld, nicht erst im aufgeklappten Detail:
  // getippt wird hier.
  const collision = priorityDuplicate(i);
  const rank = el("input", {
    type: "number", value: i.priority, min: 0, step: 1,
    class: collision.length ? "duplicate" : "",
    title: collision.length
      ? "P" + i.priority + " hat auch: " + collision.join(", ")
        + " — bei gleicher Zahl entscheidet der Zufall"
      : "Priorität — kleiner gewinnt" + (i.category
          ? " (frei in „" + i.category + "“: P"
            + nextFreePriority(i.category, i.name) + ")"
            + "; 0 = ganz nach vorn, die anderen rücken um eins"
          : ", zählt nur innerhalb einer Kategorie")});
  rank.addEventListener("change", () => {
    if (rank.value.trim() !== "") setter("priority", Number(rank.value));
  });
  rank.addEventListener("keydown", (e) => { if (e.key === "Enter") rank.blur(); });

  const fields = el("div", {class: "scan-card-fields"}, name,
    el("div", {class: "scan-card-bottom"}, cat, rank), scanItemState(i, frozen));

  const card = buildCard("item", i.name, selected,
    [el("div", {class: "scan-badge"}, onOff),
     image ? el("img", {class: "mini", src: image, alt: ""})
          : el("span", {class: "dot" + (i.marker.length ? "" : " without"),
                        style: i.marker.length ? "background:" + i.marker[0] : ""}),
     fields],
    // **Das Gewaehlte klappt seine Einstellungen hier auf**, statt sie in eine
    // andere Spalte zu legen: Vorlage, Marker, Konfidenz und Loeschen gehoeren
    // diesem Item, und man sieht beim Arbeiten daran nicht zwischen zwei Orten
    // hin und her. Nur beim gewaehlten — sechzig aufgeklappte Bloecke waeren
    // keine Liste mehr.
    (boxEl) => scanItemDetails(boxEl, i),
    () => callScan("scan_select", {kind: "item", name: i.name}));
  card.classList.add("scan-item-card");
  card.classList.toggle("off", !i.active);
  return card;
}

/** Die Zustandszeile einer Item-Maske: erkannt, stumm, fehlende Vorlage.
 *
 * **„Items erkennen" war in dieser Liste unsichtbar.** Der Knopf faerbte die
 * Rechtecke im Bild und fuellte die Ergebnisleiste — wer aber in der Item-Liste
 * stand (und das ist die Liste, in der man arbeitet), sah nach dem Klick
 * nichts und hielt ihn fuer wirkungslos. Hier steht jetzt, WO das Item gerade
 * gefunden wurde. */
function scanItemState(i, frozen) {
  const parts = [];
  // Die Kategorie ist gewechselt, die Zeile steht aber noch unter der alten
  // Ueberschrift — das muss dastehen, sonst liest sich die Liste falsch.
  if (frozen !== null && frozen !== undefined
      && (i.category || "") !== frozen) {
    parts.push(el("span", {style: "color:var(--accent)",
      title: "Beim nächsten „Sortieren“ rutscht das Item in diese Gruppe"},
      "→ " + (i.category || "ohne Kategorie")));
  }
  if ((i.detected_in || []).length) {
    parts.push(el("span", {style: "color:var(--slot-ok)"},
      "erkannt in " + i.detected_in.slice(0, 2).join(", ")
      + (i.detected_in.length > 2 ? " +" + (i.detected_in.length - 2) : "")));
  }
  if (i.silent) {
    parts.push(el("span", {style: "color:var(--err)",
      title: "Weder Template noch Marker — dieses Item wird nie erkannt"}, "silent"));
  } else if (!(i.templates || []).length) {
    parts.push(el("span", {class: "mono"}, i.marker.length + " Marker"));
  }
  if ((i.missing_scan_sizes || []).length) {
    parts.push(el("span", {style: "color:var(--accent)",
      title: "Für die Slot-Größen dieses Scans gibt es noch keine Vorlage"},
      "Vorlage fehlt"));
  }
  const collision = priorityDuplicate(i);
  if (collision.length) {
    parts.push(el("span", {style: "color:var(--accent)",
      title: "Gleiche Priorität wie " + collision.join(", ")
             + " — welches zuerst geklickt wird, entscheidet der Zufall"},
      "P" + i.priority + " doppelt"));
  }
  if (i.confirmation) {
    parts.push(el("span", {class: "mono", title: "Nach dem Klick wird bestätigt: "
      + i.confirmation.text}, "+ Bestätigung"));
  }
  return el("div", {class: "scan-card-state"}, parts);
}

function scanListScans(target) {
  if (!SC.scans.length) {
    target.appendChild(el("p", {class: "hint"},
      "Noch kein Item-Scan. Er ist die Klammer um Slots und Items — bei mehreren "
      + "Spielen der einzige Weg, sie auseinanderzuhalten."));
  }
  for (const c of SC.scans) target.appendChild(scanScanCard(c));
}

/** Ein Item-Scan als Maske: Name, Umfang — und seine Einstellungen darunter.
 *
 * **Hier lag die Luecke, durch die ein Scan gar nicht mehr zu loeschen war.**
 * Ein Klick auf die Zeile oeffnete ihn, das Oeffnen schaltete auf die
 * Item-Liste um, und die Scan-Einstellungen standen in einer Spalte, die man
 * damit gerade verlassen hatte. Jetzt bleibt der Reiter stehen, und alles, was
 * dem Scan gehoert, klappt in seiner Maske auf. */
function scanScanCard(c) {
  const open = SC.open === c.name;
  const name = el("span", {class: "scan-card-name",
    title: "Ein Block vom Typ ITEM-SCAN verweist per Name hierauf"}, c.name);
  const stamp = el("div", {class: "scan-card-state"},
    el("span", {class: "small mono"},
       c.slots.length + " Slots · " + c.items.length + " Items"),
    open ? el("span", {class: "small", style: "color:var(--slot-ok)"}, "open") : null,
    c.missing_items.length
      ? el("span", {class: "small", style: "color:var(--err)",
                    title: "Zeigt ins Leere: " + c.missing_items.join(", ")},
           c.missing_items.length + "× fehlt")
      : null);
  return buildCard("scan", c.name, open,
    [el("span", {}),
     el("span", {class: "dot" + (open ? "" : " without"),
                 style: open ? "background:var(--slot-ok)" : ""}),
     el("div", {class: "scan-card-fields"}, name, stamp)],
    (boxEl) => scanScanDetails(boxEl, c),
    // Waehlen und Oeffnen sind hier dasselbe: ein Scan, den man ansieht, ist
    // der, an dem man arbeitet. Der Reiter bleibt dabei stehen — sonst
    // verschwindet die Maske, die sich gerade aufgeklappt hat.
    () => { scanTabAfterOpen = "scans";
            callScan("scan_open", {name: c.name}); });
}

/** Template-Bilder nachholen, die wir noch nicht haben — in EINEM Aufruf. */
async function scanFetchPreviews(names) {
  const missing_items = names.filter((n) => !scanPreviews.has(n));
  if (!missing_items.length) return;
  // Vormerken, damit ein zweiter Aufbau nicht nochmal fragt.
  for (const n of missing_items) scanPreviews.set(n, "");
  const answer = await ask("scan_preview", {names: missing_items});
  if (!answer) return;
  let neu = false;
  for (const [name, url] of Object.entries(answer)) {
    if (url) { scanPreviews.set(name, url); neu = true; }
  }
  if (neu && view === "scans") scanInspector();
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
  const dragState = scanDragOffset || [0, 0];
  const dragged = dragState[0] || dragState[1]
    ? new Set(scanSelectedSlots().map((s) => s.name)) : null;

  // Slots gehoeren dem Item-Scan. Auf einem Boss-Bild waeren 45 Rechtecke kein
  // Ueberblick, sondern ein Gitter ueber der einen Region, um die es geht.
  for (const s of (scanKind === "item" ? SC.slots : [])) {
    const v = dragged && dragged.has(s.name) ? dragState : [0, 0];
    const [x1, y1] = scanToImage(s.region[0] + v[0], s.region[1] + v[1]);
    const [x2, y2] = scanToImage(s.region[2] + v[0], s.region[3] + v[1]);
    // Gewaehlt ist, was in der Auswahl steht — bei einem Rechteck sind das
    // dreissig. `SC.wahl` bleibt der eine, den der Inspektor bearbeitet.
    const selected = SC.selection.includes(s.name)
      || (SC.choice.kind === "slot" && SC.choice.name === s.name);
    // Gruen = hier liegt ein Item, das der Scan kennt. Amber = erkannt, aber
    // noch nicht Mitglied dieses Scans — anderer Zustand, andere Farbe, sonst
    // sucht man spaeter, warum der Scan das Gruene nicht findet.
    const state = (s.match
      ? (s.match.name ? (s.match.foreign ? " foreign-item" : " match") : " empty")
      : "");
    const off = s.active ? "" : " off";
    // Die Fuellung traegt denselben Zustand wie der Umriss: auf einem bunten
    // Spielbild ist die Flaeche das, was man sieht, der Strich schaerft nur.
    svg.appendChild(svgEl("rect", {x: x1, y: y1, width: x2 - x1, height: y2 - y1,
      class: "scan-fill" + state + off + (selected ? " selected" : "")}));
    svg.appendChild(svgEl("rect", {x: x1, y: y1, width: x2 - x1, height: y2 - y1,
      class: "scan-slot" + state + off + (selected ? " selected" : "")}));
    // Name ueber dem Rechteck, Erkennungsergebnis darunter — so ueberdeckt
    // keins von beiden das Bild im Slot.
    //
    // Nur, wenn er hineinpasst: die Schrift steht in SCHIRM-Pixeln (gegen den
    // Zoom gerechnet), der Slot in Bild-Pixeln, und bei 45 Slots waeren es 45
    // Namen uebereinander. Der gewaehlte behaelt seinen immer.
    const wideMode = (x2 - x1) * scanZoom;      // Breite auf dem Schirm
    if (wideMode >= 34 || selected) {
      svg.appendChild(svgEl("text", {x: x1, y: y1 - 3 * px, class: "scan-badge" + off,
        "font-size": 11 * px, "stroke-width": 3 * px}, s.name));
    }
    if (s.match && s.match.name && (wideMode >= 34 || selected)) {
      // Dieselbe Quelle wie der Umriss — sonst laeuft die Marke von ihrem
      // eigenen Rechteck farblich weg.
      svg.appendChild(svgEl("text", {x: x1, y: y2 + 12 * px, class: "scan-badge",
        "font-size": 10 * px, "stroke-width": 3 * px,
        fill: SLOT_COLOR[s.match.foreign ? "foreign-item" : "match"]}, s.match.name));
    }
    const [kx, ky] = scanToImage(s.click_pos[0] + v[0], s.click_pos[1] + v[1]);
    const arm = 4 * px;
    svg.appendChild(svgEl("path", {class: "scan-cross" + off,
      d: `M${kx - arm} ${ky}H${kx + arm}M${kx} ${ky - arm}V${ky + arm}`}));
  }

  if (scanKind !== "item") detOverlay(svg, px);

  // Der Suchbereich der Slot-Erkennung steht, bis die Farbe gezeigt ist. Ohne
  // ihn klickt man den Hintergrund an, ohne zu sehen, worin gesucht wird — und
  // ein zu eng gezogener Bereich saehe genauso aus wie ein zu weiter.
  if (SC.search_area) {
    const [ax, ay] = scanToImage(SC.search_area[0], SC.search_area[1]);
    const [bx, by] = scanToImage(SC.search_area[2], SC.search_area[3]);
    svg.appendChild(svgEl("rect", {class: "scan-search-area",
      x: ax, y: ay, width: bx - ax, height: by - ay}));
    svg.appendChild(svgEl("text", {x: ax, y: ay - 4 * px, class: "scan-badge",
      "font-size": 11 * px, "stroke-width": 3 * px, fill: "#7C9CF5"},
      "Suchbereich — jetzt leeren Slot-Hintergrund anklicken"));
  }

  // Die erste Ecke und das entstehende Rechteck: ohne die sieht man beim
  // Aufziehen nicht, was man gerade baut.
  if (SC.corner) {
    const [ex, ey] = scanToImage(SC.corner[0], SC.corner[1]);
    svg.appendChild(svgEl("circle", {cx: ex, cy: ey, r: 3 * px, class: "scan-corner"}));
    if (scanPointer) {
      const [zx, zy] = scanToImage(scanPointer[0], scanPointer[1]);
      svg.appendChild(svgEl("rect", {class: "scan-preview",
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
function scanSelectedSlots() {
  if (!SC) return [];
  const names = SC.selection.length ? SC.selection
    : (SC.choice.kind === "slot" && SC.choice.name ? [SC.choice.name] : []);
  return SC.slots.filter((s) => names.includes(s.name));
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
function scanShowSelected() {
  if (!SC || !SC.photo || SC.choice.kind !== "slot") { scanShown = ""; return; }
  const name = SC.choice.name;
  if (!name || name === scanShown) return;
  scanShown = name;
  const slot = SC.slots.find((s) => s.name === name);
  if (!slot) return;
  const stage = $("scan-stage");
  const [bx1, by1] = scanToImage(slot.region[0], slot.region[1]);
  const [bx2, by2] = scanToImage(slot.region[2], slot.region[3]);
  // Bild-Pixel -> Pixel auf der Buehne. Der Rand haelt den Slot von der Kante
  // weg: dicht am Rand sieht man ihn zwar, aber nicht, was um ihn herum liegt.
  const margin = 60;
  const l = bx1 * scanZoom, o = by1 * scanZoom;
  const r = bx2 * scanZoom, u = by2 * scanZoom;
  if (l < stage.scrollLeft + margin || r > stage.scrollLeft + stage.clientWidth - margin)
    stage.scrollLeft = Math.max(0, (l + r) / 2 - stage.clientWidth / 2);
  if (o < stage.scrollTop + margin || u > stage.scrollTop + stage.clientHeight - margin)
    stage.scrollTop = Math.max(0, (o + u) / 2 - stage.clientHeight / 2);
}

function scanPositionFromEvent(e, atImageEdge = false) {
  const margin = $("scan-overlay").getBoundingClientRect();
  if (!margin.width || !margin.height || !SC || !SC.photo) return null;
  let bx = (e.clientX - margin.left) / margin.width * SC.photo.width;
  let by = (e.clientY - margin.top) / margin.height * SC.photo.height;
  if (atImageEdge) {
    bx = Math.max(0, Math.min(SC.photo.width, bx));
    by = Math.max(0, Math.min(SC.photo.height, by));
  }
  return scanToScreen(bx, by);
}

/** Eine Ecke ausserhalb des Screenshots gehoert beim automatischen Finden
 * trotzdem zur mittleren Arbeitsflaeche. Sie wird auf den naechsten Bildrand
 * geklemmt: dort enden die Pixel, in denen OpenCV suchen kann. Seitenleisten,
 * Werkzeugleiste und Ergebnisboxen sind keine Zeichenflaeche. */
function scanSearchPositionFromStage(e) {
  const surface = $("scan-surface");
  if (!SC || SC.mode !== "find" || surface.contains(e.target)) return null;
  if (e.target.closest("#scan-canvas-bar, #scan-result, #scan-library")) return null;
  return scanPositionFromEvent(e, true);
}

/* --------------------------------------------------------------- Inspektor */

/** Die rechte Spalte neu bauen — und dabei den Fokus selbst hinüberretten.
 *
 * **Der Schutz sitzt HIER, nicht bei den Aufrufern.** `renderScans()` hatte
 * ihn, aber es gibt einen zweiten Weg: `scanFetchPreviews()` baut die Spalte
 * direkt neu, sobald ein nachgeladenes Template ankommt. Genau das passiert beim
 * UMBENENNEN — unter dem neuen Namen gibt es noch keine Vorschau —, und dort
 * ging der Fokus verloren, während er beim Tippen einer Priorität stehen blieb.
 * Ein Schutz, an den jeder Aufrufer denken muss, ist einer, den einer vergisst. */
function scanInspector() {
  const memo = rememberFocus();
  scanBuildInspector();
  restoreFocus(memo);
}

function scanBuildInspector() {
  const target = $("scan-insp");
  target.replaceChildren();
  if (SC.review) return scanReview(target);
  const head = el("div", {class: "section scan-header"},
    el("div", {class: "row"},
      el("span", {class: "heading grow"},
         SC.dirty ? "NICHT GESPEICHERT" : scanColumnTitle()),
      SC.dirty ? el("span", {class: "dirty-dot"}) : null),
    // **Der Hauptprozess schreibt dieselben Dateien.** Ein Lauf mit
    // Auto-Lernen legt Items an und speichert sie; ohne diesen Hinweis sucht
    // man sie hier vergeblich und haelt es fuer einen Fehler beim Lernen.
    // Bei ungespeicherten Änderungen zwei Knöpfe statt einer Rückfrage: was
    // passiert, steht dann VOR dem Klick da und nicht danach.
    SC.foreign ? el("div", {class: "foreign-hint"},
      el("span", {}, "Auf Platte hat sich etwas geändert — vermutlich hat ein "
        + "Lauf Items dazugelernt."),
      el("div", {class: "row"},
        SC.dirty ? el("button", {class: "btn primary", onclick: async () => {
          await callScan("scan_save");
          await callScan("scan_reload", {discard: true});
        }}, "Speichern & neu laden") : null,
        el("button", {class: "btn", onclick: () => callScan("scan_reload",
                                                           {discard: true})},
           SC.dirty ? "Änderungen verwerfen & neu laden" : "Neu laden"))) : null,
    el("button", {class: "btn primary", onclick: () => callScan("scan_save")},
       "Speichern"),
    el("div", {class: "button-pair"},
      scanKind === "item"
        // **Derselbe Befehl heisst ueberall gleich.** Er stand hier als „Items
        // erkennen" und im Assistenten als „Erkennung testen" — zwei Namen fuer
        // einen Knopf, und man probiert beide aus, weil man annimmt, sie taeten
        // Verschiedenes.
        ? el("button", {class: "btn", disabled: !photoPresent() || !SC.slots.length,
                        title: "Hält jeden Slot gegen die Item-Profile und schreibt "
                               + "das Ergebnis an Bild und Item-Liste",
                        onclick: () => callScan("scan_recognize")}, "Items erkennen")
        : el("button", {class: "btn", disabled: !photoPresent() || !detScan(),
                        title: "Erkennen, anzeigen — die Aktion wird NICHT ausgeführt",
                        onclick: () => detTest()},
             scanKind === "boss" ? "Boss-Scan testen" : "Icon-Scan testen"),
      // **Der Knopf heisst „Zurück", die Beschreibung steht im Tooltip.** Er
      // trug den letzten Schritt im Namen („↶ 'Bogen Zeus': Priorität") — das
      // ist die genauere Auskunft und die schlechtere Beschriftung: sie wurde
      // zweizeilig, wechselte bei jeder Änderung ihre Länge, und was der Knopf
      // TUT, musste man aus ihr heraussuchen. Was zurückgenommen wird, liest,
      // wer nachfragt; dass es überhaupt etwas gibt, sagt der aktive Zustand.
      el("button", {class: "btn scan-undo", disabled: !SC.undo.depth,
                    title: SC.undo.depth
                      ? "STRG+Z — nimmt zurück: " + SC.undo.what
                        + " (" + SC.undo.depth + " Schritte gemerkt)"
                      : "Nichts zum Rückgängigmachen",
                    onclick: () => callScan("scan_undo")}, "↶ Zurück")));
  // **Der Katalog-Knopf braucht KEIN eingeschaltetes LLM.** Die Kategorie haengt
  // am Namen: heisst ein Item „Citadel Helmet", steht im Katalog „Helm" — ob den
  // Namen ein Mensch getippt oder ein Modell vorgeschlagen hat, ist gleichgueltig.
  // Er steht deshalb neben „Items erkennen" und nicht bei den LLM-Sachen.
  if (scanKind === "item" && SC.catalog_on) {
    head.appendChild(el("button", {class: "btn wide",
      title: "Setzt Kategorie und Priorität für jedes Item dieses Scans, dessen "
             + "Name im Katalog steht. Namen, die er nicht kennt, bleiben "
             + "unangetastet. Die Priorität wird innerhalb dieses Scans dicht "
             + "vergeben (teuerstes Item einer Kategorie bekommt P1).",
      onclick: () => callScan("scan_catalog_apply")},
      "⊞ Aus Katalog einordnen"));
  }
  // **Sechsundfuenfzig Masken aufzuklappen ist kein Bedienweg.** Den Knopf gab
  // es nur AM einzelnen Item — richtig fuer die Korrektur eines Namens, falsch
  // fuer den Normalfall: nach dem Lernen heissen sie alle „Item 1“ … „Item 56“,
  // und genau dann will man einmal ueber alle. Er steht deshalb hier oben,
  // neben dem Katalog-Knopf, mit derselben Bezugsregel (der offene Scan).
  if (scanKind === "item" && SC.llm_on) {
    const withTemplate = (SC.items || []).filter((i) => (i.templates || []).length).length;
    if (withTemplate) {
      head.appendChild(el("button", {class: "btn wide",
        title: withTemplate + " Item(s) mit Vorlage gehen nacheinander an das Modell. "
               + (SC.catalog_on
                  ? "Jeder Name wird aus dem Katalog gewählt, danach werden "
                    + "Kategorie und Priorität gesetzt."
                  : "Ohne Katalog rät das Modell frei — die Namen sind dann "
                    + "Vorschläge, keine echten Item-Namen.")
               + " Das dauert; STRG+Z nimmt den ganzen Durchgang zurück.",
        onclick: () => scanAutonameRun({all_items: true})},
        SC.catalog_on ? "✦ Alle aus Katalog benennen" : "✦ Alle mit LLM benennen"));
    }
  }
  // **Reiter und Filter gehoeren zum Kopf, nicht zur Liste.** Der Kopf bleibt
  // beim Scrollen stehen (`.scan-header` ist `sticky`) — bei sechzig Masken war
  // die Reiterleiste sonst nach drei Umdrehungen weg, und mit ihr der Weg
  // zurueck in eine andere Liste.
  const tabs = el("div", {class: "tabs small wide"});
  const filter = el("div", {class: "scan-filter"});
  scanListBlock(tabs, filter, null);
  head.appendChild(tabs);
  if (scanCardsRight()) {
    // **Sortieren ist ein Knopf, kein Nebeneffekt des Tippens.** Sortierte sich
    // die Liste nach jeder Aenderung neu, springt genau die Zeile weg, an der
    // man gerade arbeitet.
    filter.appendChild(el("button", {class: "btn quiet",
      title: "Ordnet die Liste neu nach Kategorie, Priorität und Name. Sonst "
             + "bleibt die Reihenfolge stehen, damit beim Tippen nichts springt.",
      onclick: () => { scanOrderForget(); renderScans(); }}, "↕ Sortieren"));
    const kind = scanList === "slots" ? "slot" : "item";
    const entries = scanList === "slots" ? SC.slots : SC.items;
    const anyOn = entries.some((e) => !!e.active);
    filter.appendChild(el("button", {class: "btn quiet", disabled: !entries.length,
      title: "Schaltet alle " + (kind === "slot" ? "Slots" : "Items")
             + (anyOn ? " aus." : " ein."),
      onclick: () => callScan("scan_toggle_all",
                             {kind: kind, active: !anyOn})},
      anyOn ? "Alle aus" : "Alle ein"));
  }
  if (filter.childNodes.length) head.appendChild(filter);
  target.appendChild(head);

  const bodyEl = el("div", {class: "section growing"});
  // **Hier steht die ganze Liste, nicht ein einzelnes Ding.** Was zum
  // GEWAEHLTEN gehoert, klappt in seiner Maske auf statt daneben zu stehen.
  // Eine Mehrfachauswahl meint etwas anderes als eine Maske: sie hat keinen
  // Namen und keine Einzelfelder, nur das, was auf alle wirkt. Deshalb steht
  // sie ueber der Liste und nicht in ihr.
  if (scanCardsRight() && SC.selection.length > 1) {
    const bulk = el("div", {class: "scan-bulk"});
    scanInspSelection(bulk);
    bodyEl.appendChild(bulk);
  }
  const listEl = el("div", {class: "column", style: "gap:3px"});
  scanListBlock(null, null, listEl);
  bodyEl.appendChild(listEl);
  // Boss und Icon tragen keine Masken — was zum Gewaehlten gehoert, steht
  // deshalb UNTER der Liste statt in ihr. Abgesetzt, damit man sieht, wo die
  // Liste aufhoert und das eine Ding anfaengt.
  if (!scanCardsRight()) {
    const insp = el("div", {class: "column det-insp"});
    detInspector(insp);
    if (insp.childNodes.length) bodyEl.appendChild(insp);
  }
  if (!bodyEl.childNodes.length) {
    bodyEl.appendChild(el("p", {class: "hint"},
      "Nichts gewählt. Links eine Zeile anklicken — oder im Bild einen Slot."));
  }
  target.appendChild(bodyEl);
}

/** Was in der Kopfzeile der rechten Spalte steht: die offene Liste.
 *
 * Sie stand als feste Aufzaehlung da („SCANS · SLOTS · ITEMS"), auch wenn nur
 * eine davon zu sehen war. Eine Ueberschrift, die drei Dinge nennt und eines
 * zeigt, beschreibt das Fenster statt den Inhalt. */
function scanColumnTitle() {
  if (scanKind === "icon") return "ICON-SCANS";
  if (scanKind === "boss") return detLibrary() ? "BOSS-BIBLIOTHEK" : "BOSS-SCANS";
  return {scans: "ITEM-SCANS", slots: "SLOTS", items: "ITEMS"}[scanActiveList()]
         || "SCANS";
}

function scanReview(target) {
  const itemsId = "review-items";
  const knownNames = new Set((SC.review.item_names || []).map(String));
  const head = el("div", {class: "section"},
    el("span", {class: "heading"}, "ITEMS VOR DER ÜBERNAHME PRÜFEN"),
    el("p", {class: "hint"},
      "Erkannte Items sind direkt angehakt. Häkchen = gehört zum aktuellen Scan. " +
      "Nimmst du es bei einem bereits enthaltenen Item weg, wird nur diese Zuordnung " +
      "entfernt; das Item und seine Bilder bleiben gelernt."));
  const existing = allPriorities();
  if (existing) head.appendChild(existing);
  const bulkCategory = categoryChooser("", scanReviewRefreshCategories, {
    empty: "— Kategorie für alle ausgewählten —",
    placeholder: "Kategorie für alle ausgewählten Items",
    key: "review-sammel",
  });
  head.appendChild(el("div", {class: "scan-review-bulk"}, bulkCategory,
    el("button", {class: "btn quiet", type: "button",
      onclick: () => scanReviewCategoryToSelection(bulkCategory)},
    "Auf ausgewählte anwenden")));
  target.appendChild(head);
  const listEl = el("div", {class: "section growing scan-review"});
  for (const z of SC.review.rows) {
    const checkbox = el("input", {type: "checkbox", class: "scan-review-check"});
    const defaultChoice = !!z.ticked;
    const existingName = String(z.existing || "");
    let alsAnderes = false;
    let previousChoice = defaultChoice;
    checkbox.checked = defaultChoice;
    checkbox.title = "Angehakt: im aktuellen Scan verwenden · abgehakt: auslassen oder entfernen";
    const name = el("input", {class: "scan-review-name",
      value: z.name, list: itemsId, autocomplete: "off",
      placeholder: "Item-Name", title: "Vorhandenes Item auswählen oder neuen Namen eingeben"});
    // Dasselbe Bedienelement wie in der Item-Maske: waehlen ist der Normalfall,
    // tippen die Ausnahme. Gerade hier entstehen die Kategorien, und gerade
    // hier tippt man sie sonst zwanzigmal — beim einundzwanzigsten Mal anders.
    const cat = categoryChooser(z.category || "", scanReviewRefreshCategories,
      {cls: "scan-review-category", key: "review:" + z.slot});
    const rank = el("input", {
      class: "scan-review-prio",
      type: "number", value: z.priority ?? 1, min: 0, step: 1,
      title: "Kleinere Zahl gewinnt; 0 setzt das Item in seiner Kategorie nach vorn",
    });
    const status = el("span", {class: "small mono scan-review-status"});
    const switched = existingName ? el("button", {
      class: "btn quiet scan-review-action", type: "button",
      title: "Nur verwenden, wenn die automatische Erkennung falsch war",
    }, "Als anderes Item lernen") : null;
    let row;
    const sync = () => {
      const existingOne = knownNames.has(name.value.trim());
      const normalMatch = !!existingName && !alsAnderes;
      name.disabled = normalMatch;
      // Kategorie und Priorität des erkannten Profils sind direkt änderbar.
      // Wird ein anderer vorhandener Name gewählt, schützen wir dagegen dessen
      // Werte vor den leeren Standards der Aktion „Als anderes Item lernen“.
      cat.lock(existingOne && !normalMatch);
      rank.disabled = existingOne && !normalMatch;
      row.dataset.alsAnderes = alsAnderes ? "true" : "false";
      row.classList.toggle("skip", !checkbox.checked);
      if (!checkbox.checked) {
        status.textContent = z.slot + " · wird nicht gelernt oder geändert";
      } else if (alsAnderes) {
        status.textContent = z.slot + (existingOne
          ? " · vorhandenes „" + name.value.trim() + "“ gewählt · Vorlage ergänzen"
          : " · wird als neues Item gelernt");
      } else if (z.variant) {
        status.textContent = z.slot + " · „" + existingName +
          "“ erkannt · neue Vorlage für diese Slot-Größe";
      } else if (z.duplicate) {
        status.textContent = z.slot + " · „" + existingName +
          "“ erkannt · bereits in diesem Scan eingerichtet";
      } else {
        status.textContent = z.slot + (existingOne
          ? " · neue Vorlage für „" + name.value.trim() + "“" : " · neues Item");
      }
    };
    name.addEventListener("input", sync);
    row = el("div", {class: "scan-review-row" +
        (z.variant ? " variant" : z.duplicate ? " duplicate done" : ""),
      "data-slot": z.slot, "data-existing": existingName,
      "data-als-anderes": "false"}, checkbox, status,
      z.image ? el("img", {class: "scan-review-image", src: z.image, alt: ""})
             : el("span", {class: "scan-review-image empty"}),
      el("div", {class: "fields"},
        name, el("div", {class: "scan-review-order"}, cat,
          el("label", {class: "scan-review-prio"}, el("span", {}, "Priorität"), rank)),
        switched));
    row._reviewSynchronisieren = sync;
    const setSameChoice = () => {
      if (!existingName || alsAnderes) {
        sync();
        return;
      }
      // Dasselbe Item kann in mehreren Slots liegen. Ein Häkchen steht für die
      // Item-Zuordnung, deshalb bewegen sich alle Vorkommen gemeinsam.
      for (const other of document.querySelectorAll(".scan-review-row")) {
        if (other.dataset.existing !== existingName ||
            other.dataset.alsAnderes === "true") continue;
        const otherCheckbox = other.querySelector('input[type="checkbox"]');
        if (otherCheckbox) otherCheckbox.checked = checkbox.checked;
        if (other._reviewSynchronisieren) other._reviewSynchronisieren();
      }
    };
    checkbox.addEventListener("change", setSameChoice);
    if (switched) switched.addEventListener("click", () => {
      alsAnderes = !alsAnderes;
      if (alsAnderes) {
        previousChoice = checkbox.checked;
        name.value = z.new_name || "Item";
        cat.value = "";
        rank.value = 1;
        checkbox.checked = true;
        switched.textContent = "Treffer „" + existingName + "“ verwenden";
      } else {
        name.value = z.name;
        cat.value = z.category || "";
        rank.value = z.priority ?? 1;
        checkbox.checked = previousChoice;
        switched.textContent = "Als anderes Item lernen";
      }
      row.classList.toggle("other", alsAnderes);
      sync();
      if (!alsAnderes) setSameChoice();
      scanReviewRefreshCategories();
    });
    sync();
    listEl.appendChild(row);
  }
  listEl.appendChild(el("datalist", {id: itemsId},
    [...knownNames].map((name) => el("option", {value: name}))));
  listEl.appendChild(el("div", {class: "button-pair", style: "margin-top:8px"},
    el("button", {class: "btn", onclick: () => callScan("scan_learn_preview_cancel")}, "Abbrechen"),
    el("button", {class: "btn primary", onclick: scanReviewApply}, "Auswahl anwenden")));
  target.appendChild(listEl);
}

function scanReviewApply() {
  // **Gelesen wird ueber Klassen, nicht ueber Positionen.** Vorher wurden die
  // Felder einer Zeile durchnummeriert aus `querySelectorAll` gegriffen — wer
  // eines dazwischen einbaut (oder ein Textfeld durch eine Auswahlliste
  // ersetzt, wie es die Kategorie jetzt ist), verschiebt still alle folgenden.
  // Ein Import, der die Prioritaet als Kategorie liest, faellt niemandem auf.
  const rows = [...document.querySelectorAll(".scan-review-row")].map((n) => ({
    slot: n.dataset.slot,
    ticked: n.querySelector(".scan-review-check").checked,
    existing: n.dataset.existing || "",
    as_other: n.dataset.alsAnderes === "true",
    name: n.querySelector(".scan-review-name").value.trim(),
    category: n.querySelector(".scan-review-category").value(),
    priority: Number(n.querySelector(".scan-review-prio").value),
  }));
  callScan("scan_learn_preview_apply", {rows: rows});
}

/** Was zum gewaehlten Slot gehoert — im Detailteil seiner Maske.
 *
 * **Der Name steht in der Maske, nicht hier.** Dieselbe Regel wie beim Item und
 * beim Klick-Block im Sequenz-Editor: was dem Ding GEHOERT (seine Identitaet),
 * steht beim Ding; hier bleibt, was man daran EINSTELLT. */
function scanSlotDetails(target, s) {
  const setter = (field, value) => callScan("scan_slot_set", {name: s.name, field: field, value: value});

  target.appendChild(el("div", {class: "button-pair"},
    el("button", {class: "btn quiet",
      title: "Wohin geklickt wird, wenn in diesem Slot ein gesuchtes Item liegt",
      onclick: () => callScan("scan_mode_set", {mode: "click"})},
      "Klickpunkt setzen"),
    el("button", {class: "btn quiet", disabled: !photoPresent(),
      title: "Die Farbe des leeren Slots — sie wird beim Item-Lernen abgezogen, "
             + "damit nicht der Rahmen als Merkmal gelernt wird",
      onclick: () => callScan("scan_mode_set", {mode: "measure"})},
      "Hintergrund messen")));

  const advanced = el("details", {class: "scan-advanced"},
    el("summary", {}, "Koordinaten und Hintergrund"));
  advanced.appendChild(heading("FLÄCHE",
    "In Bildschirm-Koordinaten. Bequemer: Modus „Neuer Slot“ und zwei Ecken " +
    "im Bild anklicken — oder den Slot im Bild ziehen.", "flaeche"));
  advanced.appendChild(el("div", {class: "gitter2"},
    numberField("Links", s.region[0], (v) => setter("x1", v)),
    numberField("Oben", s.region[1], (v) => setter("y1", v)),
    numberField("Rechts", s.region[2], (v) => setter("x2", v)),
    numberField("Unten", s.region[3], (v) => setter("y2", v))));
  advanced.appendChild(heading("KLICKPUNKT",
    "Wohin geklickt wird, wenn in diesem Slot ein gesuchtes Item liegt.", "klickpunkt"));
  advanced.appendChild(el("div", {class: "gitter2"},
    numberField("X", s.click_pos[0], (v) => setter("kx", v)),
    numberField("Y", s.click_pos[1], (v) => setter("ky", v))));
  advanced.appendChild(color_swatch("Hintergrund", s.color, (v) => setter("color", v),
    "Die Farbe des leeren Slots. Sie wird beim Item-Lernen abgezogen, damit " +
    "nicht der Rahmen als Merkmal gelernt wird.", "hintergrund"));
  target.appendChild(advanced);

  target.appendChild(el("div", {class: "button-pair"},
    el("button", {class: "btn", disabled: !photoPresent(),
                  onclick: () => callScan("scan_item_learn", {slot: s.name})},
       "Item lernen"),
    el("button", {class: "btn danger", onclick: () => callScan("scan_slot_delete")},
       "löschen")));
  if (photoPresent()) {
    // „Alle" heisst: alle Slots des offenen Scans, nicht des ganzen Bestands
    // (`_scan_slots()` in scans.py). Das steht im Knopf, weil es vorher
    // stillschweigend anders war — und die Meldung danach ratlos machte.
    target.appendChild(el("button", {class: "btn quiet",
      title: SC.open ? "Alle Slots aus „" + SC.open + "“ — nicht der ganze Bestand"
                      : "Alle Slots im Bestand (kein Scan offen)",
      onclick: () => callScan("scan_learn_preview", {scope: "all"})},
      SC.open ? "Items dieses Scans prüfen & lernen" : "alle Items prüfen & lernen"));
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
function scanInspSelection(target) {
  target.appendChild(heading("AUSWAHL",
    "Mit einem Rechteck im Bild gewählt (im Modus „Auswählen“ neben einen Slot " +
    "klicken). STRG-Klick nimmt einzelne dazu oder heraus. Alles hier lässt " +
    "sich mit STRG+Z zurücknehmen.", "selection"));
  target.appendChild(el("p", {class: "hint"}, SC.selection.length + " Slots gewählt"));
  // Die Namen stehen da, nicht nur die Zahl: was man loescht, soll man vorher
  // lesen koennen. Bei dreissig wird die Liste lang - dafuer scrollt sie.
  target.appendChild(el("div", {class: "column", style: "gap:2px;max-height:160px;"
    + "overflow-y:auto;font-family:var(--mono);font-size:11px;color:var(--muted)"},
    ...SC.selection.map((n) => el("span", {}, n))));

  target.appendChild(heading("LAGE UND GRÖSSE",
    "Verschieben: im Bild ziehen oder Pfeiltasten (SHIFT = 10 px) — der " +
    "Klickpunkt geht mit. Angleichen zieht alle auf die MITTLERE Grösse, um " +
    "ihre Mitte herum: ein einzelner Verklicker soll nicht alle anderen " +
    "verbiegen.", "auswahl-lage"));
  target.appendChild(el("button", {class: "btn wide",
    onclick: () => callScan("scan_align_size")}, "Grösse angleichen"));

  target.appendChild(heading("HINTERGRUND UND ITEMS",
    "Gemessen wird jeder Slot an sich selbst — eine gemeinsame Farbe für alle " +
    "wäre an jedem einzelnen ein bisschen falsch.", "auswahl-lernen"));
  target.appendChild(el("button", {class: "btn wide", disabled: !photoPresent(),
    onclick: () => callScan("scan_selection_color")}, "Hintergrund neu messen"));
  target.appendChild(el("button", {class: "btn wide", disabled: !photoPresent(),
    title: "Aus jedem gewählten Slot ein Item — Doppelte werden übersprungen",
    onclick: () => callScan("scan_learn_preview", {scope: "selection"})},
    SC.selection.length + " Items prüfen & lernen"));

  target.appendChild(el("div", {class: "button-pair", style: "margin-top:14px"},
    el("button", {class: "btn", onclick: () => callScan("scan_cancel")},
       "Auswahl aufheben"),
    el("button", {class: "btn danger", onclick: () => callScan("scan_slot_delete")},
       SC.selection.length + " löschen")));
}

/** Was man an einem Item selten ändert: Vorlagen, Marker, Konfidenz, Löschen.
 *
 * **Steht IN der Maske des gewählten Items**, nicht daneben: sonst sieht man
 * beim Arbeiten an einem Ding zwischen zwei Orten hin und her, und die Maske
 * trägt seine Identität ohnehin schon. Dieselbe Regel wie „was dem Punkt
 * gehört, steht beim Punkt" im Sequenz-Editor. */
function scanItemDetails(target, i) {
  const setter = (field, value) => callScan("scan_item_set", {name: i.name, field: field, value: value});
  const image = scanPreviews.get(i.name);
  if (image) target.appendChild(el("img", {class: "scan-large", src: image}));
  if ((i.detected_in || []).length) {
    target.appendChild(el("p", {class: "hint", style: "color:var(--slot-ok)"},
      "Gerade erkannt in: " + i.detected_in.join(", ")));
  }
  target.appendChild(priorityOverview(i.category, i.name));
  const advanced = el("details", {class: "scan-advanced"},
    el("summary", {}, "Erweiterte Erkennungseinstellungen"));
  advanced.appendChild(numberField("Konfidenz", i.confidence, (v) => setter("confidence", v),
      {min: 0, max: 1, step: "any"},
      "Wie gut das Template passen muss (0–1).", "konf"));
  advanced.appendChild(el("p", {class: "hint"},
    (i.template_sizes || []).length
      ? "Gelernte Slot-Größen: " + i.template_sizes.map((g) => g[0] + "×" + g[1]).join(", ")
      : "Keine Bildvorlage — nur Marker-Farben."));
  if ((i.templates || []).length) {
    advanced.appendChild(el("div", {class: "column", style: "gap:5px"},
      (i.templates || []).map((v) => el("div", {class: "row"},
        el("span", {class: "hint mono grow"}, v),
        el("button", {class: "btn quiet", title: "Nur vom Item lösen; Datei bleibt erhalten",
          onclick: () => callScan("scan_item_remove_template", {name: i.name, file: v})},
          "Vorlage entfernen")))));
  }
  if ((i.missing_scan_sizes || []).length) {
    advanced.appendChild(el("p", {class: "hint", style: "color:var(--accent)"},
      "Für diesen Scan noch nicht gelernt: " +
      i.missing_scan_sizes.map((g) => g[0] + "×" + g[1]).join(", ") +
      ". Beim Lernen diesen Item-Namen auswählen, um die Vorlage zu ergänzen."));
  }
  if (i.marker.length) {
    advanced.appendChild(heading("MARKER-FARBEN",
      "Die häufigsten Farben im gelernten Ausschnitt, ohne den Slot-Hintergrund.",
      "marker"));
    advanced.appendChild(el("div", {class: "scan-marker"},
      i.marker.map((c) => el("span", {style: "background:" + c, title: c}))));
  }
  target.appendChild(advanced);
  // Der Knopf hing einmal an `kategorie === "Auto"` — also genau an den Items,
  // die schon einen Namen vom Auto-Lernen haben. Wer 56 Vorlagen von Hand als
  // „item_1“ … angelegt hat, fand ihn deshalb nie, obwohl das der Fall ist, für
  // den man ihn sucht. Gebraucht wird eine Vorlage, sonst gibt es nichts zu sehen.
  if ((i.templates || []).length) {
    target.appendChild(el("button", {class: "btn wide", style: "margin-top:10px",
      title: SC.catalog_on
        ? "Wählt einen der echten Item-Namen aus dem Katalog und ordnet danach ein."
        : "Fragt das LLM nach einem freien Namensvorschlag. Mit eingeschaltetem "
          + "Item-Katalog wählt es stattdessen aus den echten Namen des Spiels.",
      onclick: () => scanAutonameRun({names: [i.name]})},
      SC.catalog_on ? "✦ Aus Katalog benennen" : "✦ Mit LLM benennen"));
  }
  target.appendChild(scanItemConfirmation(i));
  if (i.silent) {
    target.appendChild(el("p", {class: "hint", style: "color:var(--err)"},
      "Weder Template noch Marker — dieses Item wird nie erkannt."));
  }
  target.appendChild(el("button", {class: "btn danger", style: "margin-top:14px",
    onclick: () => callScan("scan_item_delete")}, "Item löschen"));
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
function scanItemConfirmation(i) {
  const setter = (field, value) => callScan("scan_item_set",
                                        {name: i.name, field: field, value: value});
  const boxEl = el("div", {class: "column", style: "gap:7px"});
  boxEl.appendChild(heading("BESTÄTIGUNGSKLICK",
    "Manche Spiele fragen nach dem Klick nach („wirklich verkaufen?“). Ohne "
    + "die Bestätigung bleibt das Popup stehen, und der Scan kommt nicht mehr "
    + "zum nächsten Slot. Die Stelle steht als Punkt in sequence.json — dieselbe "
    + "Kalibrierung erfasst sie mit.", "confirmation"));
  const choice = selection("Punkt", [{value: "", text: "— keine Bestätigung —"}].concat(
    SC.points.map((p) => ({value: p.id, text: "#" + p.id + " " + p.name}))),
    i.confirmation ? i.confirmation.point_id : "", (v) => setter("confirmation", v));
  boxEl.appendChild(choice);
  // Ein Punkt, den es nicht mehr gibt, wird GESAGT statt verschwiegen: der
  // Lauf klickt sonst nichts, und man sucht den Fehler bei der Erkennung.
  if (i.confirmation && i.confirmation.missing) {
    boxEl.appendChild(el("p", {class: "hint", style: "color:var(--err)"},
      i.confirmation.text + " — die Bestätigung greift nicht."));
  }
  boxEl.appendChild(el("button", {class: "btn quiet", disabled: !photoPresent(),
    title: "Die Stelle im Bild anklicken — dabei entsteht ein Punkt, oder ein "
           + "vorhandener an derselben Stelle wird wiederverwendet",
    onclick: () => callScan("region_mode", {kind: "item", mode: "action"})},
    "Stelle im Bild anklicken"));
  if (i.confirmation) {
    boxEl.appendChild(numberField("Wartezeit (s)", i.confirmation_delay,
      (v) => setter("confirmation_delay", v), {min: 0, step: "any"},
      "Zeit zwischen dem Item-Klick und der Bestätigung — das Popup braucht "
      + "einen Moment, bis es da ist.", "bestaetigungszeit"));
  }
  return boxEl;
}

/** Was zum offenen Item-Scan gehoert — im Detailteil seiner Maske. */
function scanScanDetails(target, c) {
  const setter = (field, value) => callScan("scan_set", {name: c.name, field: field, value: value});

  target.appendChild(heading("EINSTELLUNGEN",
    "Welche Slots nach welchen Items durchsucht werden, steht in den Reitern "
    + "daneben: der Haken vor jeder Maske heisst „gehört zu diesem Scan“. Hier "
      + "steht, WIE gesucht wird. Ein Block vom Typ ITEM-SCAN verweist per Name "
      + "auf diesen Scan.", "itemscan"));

  target.appendChild(numberField("Farb-Toleranz", c.tolerance, (v) => setter("tolerance", v),
    {min: 0, step: 1},
    "Wie weit eine Marker-Farbe abweichen darf, damit sie noch als gefunden gilt.",
    "tolerance"));
  target.appendChild(toggle("Unbekanntes lernen", c.learn, (v) => setter("learn", v),
    "Neue Slot-Inhalte werden als Items in die globale Liste gelernt — nie in "
    + "diesen Scan, damit sie nicht ungeprüft geklickt werden.", "learn"));
  target.appendChild(toggle("Slots rückwärts", c.reverse, (v) => setter("reverse", v),
    "Von hinten nach vorn (4, 3, 2, 1). Sinnvoll, wenn das Spiel den Bestand "
    + "nach vorn aufrückt: dann verschiebt ein Klick nicht die noch nicht "
    + "besuchten Slots. Die Richtung gehört zum Inventar, deshalb steht sie hier "
    + "und nicht in den Einstellungen.", "reverse"));
  target.appendChild(toggle("Item-Katalog benutzen", c.use_catalog,
    (v) => setter("use_catalog", v),
    "Mit Katalog kennt der Editor die echten Item-Namen des Spiels: „Aus Katalog "
    + "einordnen“ setzt Kategorie und Priorität, und die LLM-Benennung wählt aus "
    + "den echten Namen statt frei zu raten. Die Kategorie hängt am NAMEN, nicht "
    + "am LLM — sie funktioniert auch, wenn du den Namen selbst tippst. Der "
    + "Schalter steht hier und nicht in den Einstellungen, weil ein Katalog "
    + "immer nur für EIN Spiel gilt; wo die Datei liegt, sagt "
    + "„Item-Katalog“ in den Einstellungen.", "katalog"));

  if (c.missing_items.length) {
    target.appendChild(el("p", {class: "hint", style: "color:var(--err)"},
      "Zeigt ins Leere: " + c.missing_items.join(", ") + ". Der Scan läuft mit dem Rest " +
      "weiter — lieber ein Slot weniger als ein toter Scan."));
  }
  target.appendChild(el("button", {class: "btn danger",
    title: "Entfernt die Konfiguration und ihre Datei. STRG+Z holt die "
           + "Konfiguration zurück, den gemerkten Screenshot nicht.",
    onclick: () => callScan("scan_delete", {name: c.name})}, "Diesen Scan löschen"));
}

/* ------------------------------------------- Ansicht: Bosse und Icon-Scans */

/* Dieselbe Buehne, eine andere Frage: ein Boss-Scan ist ein Rechteck auf einem
 * Bild und eine Aktion dahinter, ein Icon-Scan dasselbe ohne Bosse-Liste.
 *
 * Welche Art offen ist, ist reiner Oberflaechenzustand wie `view` und
 * `scanList` — die Bruecke bekommt bei jedem Befehl gesagt, worauf er wirkt
 * (`{art: "boss"}`). */
let scanKind = "item";
/* Welcher Assistent-Schritt der Erkennungs-Arten offen ist. Eigene Variable
 * neben `scanWizardStep`: die Arten haben verschieden viele Schritte, und
 * ein gemeinsamer Zaehler stuende beim Umschalten auf einem, den es nicht gibt. */
let scanDetStep = null;

const SCAN_KINDS = ["item", "boss", "icon"];

/* Welche Bruecken-Methode zu welcher Art gehoert — als Tabelle.
 *
 * Als Ternaeroperator an jeder Aufrufstelle waeren die Namen sechsmal da, und
 * der Test „jeder Aufruf der Seite passt zur Bruecke" faende keinen davon: er
 * sucht den Methodennamen direkt hinter der oeffnenden Klammer. Hier stehen sie
 * einmal und sind messbar (`tests/vertrag/studio_erkennung.py`). */
const DET_COMMAND = {
  boss: {open: "boss_scan_open", new: "boss_scan_new",
         scan_field: "boss_scan_set", field: "boss_set",
         delete: "boss_scan_delete", test: "boss_test"},
  icon: {open: "icon_scan_open", new: "icon_scan_new",
         scan_field: "icon_set", field: "icon_set",
         delete: "icon_scan_delete", test: "icon_test"},
};

/** Der Befehlsname fuer die offene Art. */
function detCommand(key) {
  return (DET_COMMAND[scanKind] || DET_COMMAND.boss)[key];
}

/** Der offene Boss- bzw. Icon-Scan — oder null. */
function detScan() {
  if (!SC) return null;
  if (scanKind === "boss") return SC.boss_scans.find((c) => c.name === SC.boss.open) || null;
  if (scanKind === "icon") return SC.icon_scans.find((c) => c.name === SC.icon.open) || null;
  return null;
}

/** Die Bosse, die dieser Scan sieht: seine eigenen plus die Bibliothek.
 *
 * Genau diese Liste sieht auch der Lauf (`execute_boss_scan` merged lokal +
 * global, lokale gewinnen bei Namensgleichheit). Nur die lokalen zu zeigen
 * hiesse, die Haelfte der Erkennung zu verschweigen — und man sucht dann, warum
 * ein Boss erkannt wird, der gar nicht in der Liste steht. */
function detBosses() {
  const c = detScan();
  const local = c ? c.bosses : [];
  const names = new Set(local.map((b) => b.name));
  return local.concat(SC.global_bosses.filter((b) => !names.has(b.name)));
}

/** Der gewaehlte Boss — der eine, den die rechte Spalte bearbeitet. */
function detBoss() {
  if (!SC || scanKind !== "boss" || !SC.boss.choice) return null;
  const listEl = SC.boss.choice_global ? SC.global_bosses : ((detScan() || {}).bosses || []);
  return listEl.find((b) => b.name === SC.boss.choice) || null;
}

/** Steht die Bibliothek statt eines Scans im Vordergrund? */
function detLibrary() { return scanKind === "boss" && scanActiveList() === "bibliothek"; }

function scanSetKind(kind) {
  if (!SCAN_KINDS.includes(kind) || kind === scanKind) return;
  scanKind = kind;
  scanDetStep = null;
  // Eine andere Art ist ein anderer Zusammenhang: die Vorgabe gilt wieder.
  scanList = null;
  // Ein Werkzeug der alten Art wuerde in der neuen etwas anderes tun.
  callScan("scan_cancel");
}

/** Welche Bloecke der linken Spalte gelten — und wo die Aufnahme gerade haengt. */
function scanMaintainKind() {
  for (const k of document.querySelectorAll("[data-scan-kind]"))
    k.classList.toggle("on", k.dataset.scanKind === scanKind);
  const item = scanKind === "item";
  $("sec-item-choice").hidden = !item;
  $("sec-steps").hidden = !item;
  $("sec-modes").hidden = !item;
  $("sec-det-choice").hidden = item;
  $("sec-det-steps").hidden = item;
  for (const button of document.querySelectorAll("[data-erk-tool]")) {
    button.hidden = item;
    button.disabled = !SC.pillow || !detScan();
    button.classList.toggle("on", SC.mode === button.dataset.erkTool);
  }
  // **Die Aufnahme-Karte wandert, also muss sie auch zurueck.** Sie gehoert
  // allen drei Arten und existiert deshalb nur EINMAL im Dokument; blieb sie
  // beim Umschalten im versteckten Erkennungs-Block liegen, fehlte dem
  // Item-Assistenten sein erster Schritt — und mit ihm der einzige Weg zu
  // einem Screenshot.
  if (item) {
    const home = $("scan-steps");
    const cardEl = $("scan-wizard-1");
    if (cardEl.parentElement !== home) home.insertBefore(cardEl, home.firstChild);
    return;
  }
  detRenderChoice();
  detRenderSteps();
}

/* ----------------------------------------------------- Auswahl und Name */

/** Oben in der linken Spalte: welcher Scan, wie er heisst, ein neuer.
 *
 * **Der Name steht da, wo der Scan gewaehlt wird** — dieselbe Regel wie beim
 * Item-Scan und beim Klick-Block: was dem Ding gehoert, steht beim Ding; rechts
 * bleibt, was man daran einstellt. */
function detRenderChoice() {
  const target = $("sec-det-choice");
  const boss = scanKind === "boss";
  const listEl = boss ? SC.boss_scans : SC.icon_scans;
  const open = detScan();
  const children = [el("span", {class: "heading"}, boss ? "BOSS-SCAN" : "ICON-SCAN")];
  children.push(selection("", [{value: "", text: listEl.length
      ? "— keiner gewählt —" : (boss ? "— noch kein Boss-Scan —" : "— noch kein Icon-Scan —")}]
    .concat(listEl.map((c) => ({value: c.name, text: c.name}))),
    open ? open.name : "",
    (v) => callScan(detCommand("open"), {name: v})));
  if (open) {
    children.push(field("Name", open.name,
      (v) => callScan(detCommand("scan_field"),
                     {name: open.name, field: "name", value: v})));
  }
  children.push(el("div", {class: "row"},
    el("button", {class: "btn quiet", onclick: () => {
      scanDetStep = 2;
      callScan(detCommand("new"));
    }}, boss ? "+ neuer Boss-Scan" : "+ neuer Icon-Scan"),
    el("span", {class: "grow"}),
    el("span", {class: "small mono"}, open
      ? (boss ? detBosses().length + " Bosse" : detHowText(open.detection))
      : listEl.length + (listEl.length === 1 ? " Scan" : " Scans"))));
  target.replaceChildren(...children);
}

/* ------------------------------------------------------------- Assistent */

/** Woran ein Scan erkennt — als Wort, nicht als Schluessel. */
function detHowText(how) {
  return {template: "per Vorlage", marker: "per Farben",
          keine: "ohne Erkennung"}[how] || how;
}

/** Eine Schrittkarte des Assistenten — dieselbe Gestalt wie beim Item-Scan. */
function detCard(nr, title, stamp, done, content) {
  const open = scanDetStep === nr;
  return el("div", {class: "scan-wizard-step" + (open ? " open" : "")
                           + (done ? " done" : "")},
    el("button", {class: "scan-wizard-header", onclick: () => {
      // Ein Schritt bleibt jederzeit wieder aufklappbar — er ist kein
      // Fortschrittsbalken, sondern ein Weg, den man auch rueckwaerts geht.
      scanDetStep = open ? null : nr;
      renderScans();
    }},
      el("span", {class: "nr"}, done && !open ? "✓" : String(nr)),
      el("span", {class: "grow"}, el("b", {}, title), el("small", {}, stamp)),
      el("span", {class: "arrow"}, "›")),
    el("div", {class: "scan-wizard-body", hidden: !open}, content));
}

function detRenderSteps() {
  const target = $("sec-det-steps");
  const boss = scanKind === "boss";
  const c = detScan();
  // Erst alles bauen, dann umhaengen. **Die Aufnahme-Karte existiert genau
  // einmal im Dokument** — sie gehoert allen drei Arten, und sie zweimal zu
  // bauen waeren zwei Stellen, an denen eine Aenderung an der Aufnahme
  // vergessen werden kann. Genau deshalb darf sie erst wandern, wenn nichts
  // mehr schiefgehen kann: bricht der Aufbau vorher ab, haengt sie in einem
  // Baum, den niemand mehr sieht — und mit ihr der einzige Weg zu einem Bild.
  const more = [];
  if (c) {
    more.push(detRegionStep(c));
    if (boss) {
      more.push(detBossesStep(c), detWaysStep(c), detFallbackStep(c));
    } else {
      more.push(detDetectionStep(c), detActionStep(c, "icon"));
    }
  }
  const steps = el("div", {class: "scan-wizard"});
  const recording = $("scan-wizard-1");
  recording.classList.toggle("open", scanDetStep === 1);
  recording.classList.toggle("done", photoPresent());
  $("scan-step-1-nr").textContent = photoPresent() && scanDetStep !== 1 ? "✓" : "1";
  $("scan-step-1-body").hidden = scanDetStep !== 1;
  steps.append(recording, ...more);

  if (!c) {
    target.replaceChildren(
      el("span", {class: "heading"}, boss ? "BOSS-SCAN EINRICHTEN" : "ICON-SCAN EINRICHTEN"),
      steps,
      el("p", {class: "hint"}, "Oben einen Scan anlegen — danach stehen die "
        + "weiteren Schritte hier."));
    return;
  }
  const children = [el("span", {class: "heading"},
                     boss ? "BOSS-SCAN EINRICHTEN" : "ICON-SCAN EINRICHTEN")];
  // **Fehlende Voraussetzung blendet nichts aus, sondern erklaert sich.** Ohne
  // OpenCV ist die Template-Erkennung aus — Farb-Marker, OCR und LLM gehen
  // trotzdem. Amber, nicht rot: es ist ein Zustand, kein Defekt.
  if (!SC.opencv) {
    children.push(el("div", {class: "foreign-hint"},
      el("span", {}, "OpenCV nicht installiert — Template-Erkennung ist aus. "
        + "Farb-Marker, OCR und LLM gehen trotzdem."),
      el("span", {class: "mono small"}, "pip install opencv-python")));
  }
  children.push(steps);
  target.replaceChildren(...children);
}

/** Schritt 2: die Region. Aufziehen ODER vier Zahlen — beides bleibt. */
function detRegionStep(c) {
  const r = c.region;
  const placed = (r[2] - r[0]) > 0 && (r[3] - r[1]) > 0
    && !(r[0] === 0 && r[1] === 0 && r[2] === 100 && r[3] === 100);
  const setter = (i, v) => {
    const neu = r.slice();
    neu[i] = Number(v) || 0;
    detField("region", neu);
  };
  return detCard(2, "Region", placed
    ? "(" + r[0] + "," + r[1] + ") → (" + r[2] + "," + r[3] + ")  ·  "
      + (r[2] - r[0]) + "×" + (r[3] - r[1])
    : "Noch nicht gesetzt", placed, [
    el("p", {class: "hint"}, scanKind === "boss"
      ? "Der Bereich, in dem der Boss-Name bzw. sein Bild erscheint. Eng genug, "
        + "dass nichts Wechselndes mit hineinfällt."
      : "Eng um das Symbol herum. Was mit im Rechteck liegt, wird mitgelernt."),
    el("div", {class: "gitter2"},
      numberField("Links", r[0], (v) => setter(0, v), {step: 1}),
      numberField("Oben", r[1], (v) => setter(1, v), {step: 1}),
      numberField("Rechts", r[2], (v) => setter(2, v), {step: 1}),
      numberField("Unten", r[3], (v) => setter(3, v), {step: 1})),
    el("button", {class: "btn primary scan-wizard-main", disabled: !photoPresent(),
      onclick: () => callScan("region_mode", {kind: scanKind, mode: "region"})},
      "Region im Bild aufziehen"),
  ]);
}

/** Schritt 3 (Boss): die Bosse dieses Scans. */
function detBossesStep(c) {
  const local = c.bosses.length;
  const global = SC.global_bosses.length;
  return detCard(3, "Bosse", local || global
    ? local + " lokal · " + global + " global"
    : "Noch kein Boss · die Bibliothek ist leer", local > 0 || global > 0, [
    el("p", {class: "hint"}, "Jeder Boss hat eine eigene Erkennung und eine "
      + "eigene Aktion. Die Reihenfolge ist die Priorität: der erste Treffer gewinnt."),
    el("button", {class: "btn primary scan-wizard-main",
      onclick: () => callScan("boss_new")}, "+ Boss anlegen"),
    el("button", {class: "btn quiet scan-wizard-main", disabled: !photoPresent()
        || !detBosses().length,
      onclick: () => callScan("boss_test_all")}, "Alle gegen dieses Bild halten"),
  ]);
}

/** Schritt 4 (Boss): OCR und LLM. */
function detWaysStep(c) {
  const b = SC.ready;
  const on = [c.use_ocr ? "OCR" : null, c.use_llm ? "LLM" : null].filter(Boolean);
  const lamp = !b.llm_state ? "" : (b.llm_state.reachable ? " on" : " off");
  return detCard(4, "LLM & OCR", on.length ? on.join(" + ") + " aktiv" : "aus",
    on.length > 0, [
    el("span", {class: "heading"}, "OCR TEXTERKENNUNG"),
    toggle("OCR benutzen", c.use_ocr, (v) => detField("use_ocr", v)),
    c.use_ocr ? segment([{value: true, text: "als Fallback"}, {value: false, text: "primär"}],
      c.ocr_fallback, (v) => detField("ocr_fallback", v)) : null,
    // **Gefragt, nicht mitgeliefert.** `import easyocr` zieht Torch nach und
    // dauert Sekunden; in einer Momentaufnahme, die nach jedem Klick neu
    // entsteht, hat das nichts verloren. Dieselbe Lampe wie beim LLM.
    el("div", {class: "row"},
      el("span", {class: "scan-lamp" + (!b.ocr_state ? ""
        : (b.ocr_state.present ? " on" : " off"))}),
      el("span", {class: "small grow"}, !b.ocr_state
        ? "noch nicht geprüft"
        : (b.ocr_state.present ? b.ocr_state.backends.join(", ")
                          : "kein Backend installiert")),
      el("button", {class: "btn quiet", onclick: () => callScan("ocr_check")},
         "prüfen")),
    el("p", {class: "hint"}, !b.ocr_on
      ? "OCR ist in den Einstellungen aus (ocr_enabled) — dieser Schalter "
        + "greift erst danach."
      : (b.ocr_state && !b.ocr_state.present
          ? "pip install easyocr (oder pytesseract)"
          : b.ocr_backend + " · " + (b.ocr_languages.join(",") || "en")
            + " · min " + b.ocr_min.toFixed(2))),
    el("span", {class: "heading"}, "LLM VISION"),
    toggle("LLM benutzen", c.use_llm, (v) => detField("use_llm", v)),
    c.use_llm ? segment([{value: true, text: "als Fallback"}, {value: false, text: "primär"}],
      c.llm_fallback, (v) => detField("llm_fallback", v)) : null,
    el("div", {class: "row"},
      el("span", {class: "scan-lamp" + lamp}),
      // Ohne Probe steht hier „noch nicht geprueft", nicht der Endpunkt: ein
      // leeres Feld (die Voreinstellung ist leer) saehe aus wie ein Fehler.
      // Der Endpunkt gehoert in den Tooltip — dort sucht man ihn, wenn die
      // Lampe rot ist.
      el("span", {class: "small grow", title: b.llm_endpoint || ""},
        !b.llm_state ? "noch nicht geprüft"
          : (b.llm_state.reachable ? "erreichbar (" + b.llm_state.duration + " ms)"
                                    : "nicht erreichbar")),
      el("button", {class: "btn quiet", onclick: () => callScan("llm_check")}, "testen")),
    el("p", {class: "hint"}, b.llm_on
      ? detOrder(c)
      : "LLM ist in den Einstellungen aus (llm_enabled) — dieser Schalter greift "
        + "erst danach."),
  ]);
}

/** In welcher Reihenfolge erkannt wird — als ein Satz.
 *
 * Bei gleicher Einstellung laeuft OCR VOR LLM: OCR ist lokal und schnell, das
 * LLM kostet bis `llm_timeout`. Dieselbe Reihenfolge steht in
 * `runtime/boss_detection.py`; hier wird sie nur vorgelesen. */
function detOrder(c) {
  const front = [], back = [];
  for (const [name, on, fallback] of [["OCR", c.use_ocr, c.ocr_fallback],
                                      ["LLM", c.use_llm, c.llm_fallback]])
    if (on) (fallback ? back : front).push(name);
  return "Reihenfolge: " + front.concat(["Template/Marker"], back).join(" → ");
}

/** Schritt 5 (Boss): was passiert, wenn KEIN Boss erkannt wird. */
function detFallbackStep(c) {
  const text = (SC.actions.boss.find((a) => a.value === c.default_action) || {}).text
    || c.default_action;
  return detCard(5, "Fallback", "wenn kein Boss erkannt: " + text, true, [
    el("p", {class: "hint"}, "Greift, wenn keiner der Bosse passt — und auch "
      + "dann, wenn OCR und LLM nichts finden."),
    detActionTiles(SC.actions.boss, c.default_action,
                      (v) => detField("default_action", v)),
    c.default_action === "item_scan"
      ? selection("Item-Scan", [{value: "", text: "— keiner —"}].concat(
          SC.item_scan_names.map((n) => ({value: n, text: n}))), c.default_scan || "",
          (v) => detField("default_scan", v))
      : null,
  ]);
}

/** Schritt 3 (Icon): Template oder Farb-Marker. */
function detDetectionStep(c) {
  return detCard(3, "Erkennung", c.detection === "template"
    ? "Vorlage · min " + c.confidence.toFixed(2)
    : (c.detection === "marker" ? c.marker.length + " Marker · Toleranz " + c.tolerance
                                : "Noch nichts gesetzt"),
    c.detection !== "none", detDetectionFields(c, "icon"));
}

/** Die Erkennungs-Felder — dieselben fuer Boss und Icon.
 *
 * Beide erkennen ueber Template ODER Farb-Marker; das sind dieselben Felder und
 * dieselben Knoepfe. Zwei Fassungen davon waeren zwei Stellen, an denen ein
 * Griff fehlt — und „Vorlage neu aufnehmen" ist genau der Griff, der heute den
 * ganzen Konsolen-Ablauf kostet. */
function detDetectionFields(obj, kind, name) {
  const over = DET_COMMAND[kind].field;
  const setter = (field, value) => callScan(over, Object.assign(
    {field: field, value: value}, name ? {name: name} : {}));
  const template = obj.detection !== "marker";
  return [
    segment([{value: "template", text: "Template"}, {value: "marker", text: "Farb-Marker"}],
      obj.detection === "marker" ? "marker" : "template",
      // Umschalten heisst hier: das andere loswerden. Beides stehen zu lassen
      // waere `_check_profile_match`s UND — dann muessen BEIDE stimmen, und
      // niemand rechnet damit.
      (v) => setter(v === "marker" ? "template" : "marker", v === "marker" ? "" : [])),
    template ? el("div", {class: "row", style: "align-items:flex-start"},
      obj.preview
        ? el("img", {class: "scan-template", src: obj.preview, alt: ""})
        : el("div", {class: "scan-template empty"}, "keine Vorlage"),
      el("div", {class: "column grow"},
        el("span", {class: "small mono"}, obj.template || "—"),
        numberField("Min. Konfidenz", obj.confidence, (v) => setter("confidence", v),
          {min: 0.05, max: 1, step: 0.01},
          "Ab welcher Übereinstimmung ein Treffer zählt. Zu hoch heisst "
          + "„findet nie“, zu tief „findet alles“.", "confidence"))) : null,
    template ? el("button", {class: "btn scan-wizard-main",
      disabled: !photoPresent() || !SC.opencv,
      title: SC.opencv ? "Lernt die Region aus dem eingefrorenen Bild"
                       : "Ohne OpenCV gibt es kein Template-Matching",
      onclick: () => callScan("template_capture", Object.assign(
        {kind: kind}, name ? {name: name} : {}))}, "Vorlage neu aufnehmen") : null,
    !template ? el("div", {class: "scan-marker"},
      obj.marker.map((h) => el("span", {class: "scan-color-swatch", style: "background:" + h,
                                           title: h})),
      el("span", {class: "scan-color-swatch empty", title: "noch Platz"})) : null,
    !template ? el("div", {class: "gitter2"},
      numberField("Toleranz", obj.tolerance === undefined ? 30 : obj.tolerance,
        (v) => setter("tolerance", v), {min: 0, step: 1},
        "Wie weit eine Marker-Farbe abweichen darf.", "erktoleranz"),
      el("div", {class: "field-quiet"}, "measured",
        el("span", {class: "mono"}, obj.marker.length + " Farben"))) : null,
    !template ? el("button", {class: "btn scan-wizard-main", disabled: !photoPresent(),
      onclick: () => callScan("marker_measure", Object.assign(
        {kind: kind}, name ? {name: name} : {}))}, "Marker im Bild neu messen") : null,
    !template ? el("p", {class: "hint"}, "min. Pixel über 1 halten — sonst löst "
      + "ein einzelner Rausch-Pixel den Scan aus (Einstellung "
      + "scan_marker_min_pixels, gerade " + SC.ready.marker_min_pixel + ").") : null,
  ];
}

/** Aktions-Kacheln: feste kurze Auswahl, also Kacheln statt Klappliste.
 *
 * Die Werte kommen aus `models.py` (ueber die Momentaufnahme) — die Ansicht
 * erfindet keine Aktionsnamen. Ein getipptes "skipcycle" waere ein Wert, den
 * `__post_init__` beim Speichern still auf den Standard hebt: der Klick saehe
 * aus, als haette er gewirkt. */
function detActionTiles(values, current, onSet) {
  // Dasselbe Raster wie beim Block-Typ im Sequenz-Editor — die Kacheln sollen
  // sich gleich anfuehlen. Auf der Kachel steht das Schlagwort, im Tooltip der
  // Satz: „Zyklus abbrechen" ist auf 9,5 px zweizeilig und unlesbar.
  return el("div", {class: "gitter3"}, values.map((a) =>
    el("button", {class: "type-chip" + (a.value === current ? " on" : ""),
      title: a.text, onclick: () => onSet(a.value)}, a.short)));
}

/** Die Felder hinter einer Aktion — Punkt, Taste, Verzoegerung, Item-Scan. */
function detActionFields(obj, kind, name) {
  const over = DET_COMMAND[kind].field;
  const setter = (field, value) => callScan(over, Object.assign(
    {field: field, value: value}, name ? {name: name} : {}));
  const fields = [];
  if (obj.action === "item_scan") {
    fields.push(selection("Item-Scan", [{value: "", text: "— keiner —"}].concat(
      SC.item_scan_names.map((n) => ({value: n, text: n}))), obj.scan || "",
      (v) => setter("scan", v)));
    fields.push(selection("Modus", SC.actions.scan_modes.map(
      (m) => ({value: m.value, text: m.text})), obj.scan_mode,
      (v) => setter("scan_mode", v)));
  }
  if (obj.action === "click") {
    fields.push(selection("Punkt", [{value: "", text: "— keiner —"}].concat(
      SC.points.map((p) => ({value: p.id, text: "#" + p.id + " " + p.name}))),
      obj.point_id === null || obj.point_id === undefined ? "" : obj.point_id,
      (v) => setter("point", v === "" ? null : Number(v))));
    fields.push(el("button", {class: "btn quiet", disabled: !photoPresent(),
      onclick: () => callScan("region_mode", {kind: kind, mode: "action"})},
      "Stelle im Bild anklicken"));
  }
  if (obj.action === "key")
    fields.push(field("Taste", obj.action_key || "", (v) => setter("action_key", v)));
  fields.push(numberField("Verzögerung vor Aktion (s)", obj.delay,
    (v) => setter("delay", v), {min: 0, step: 0.1}));
  return fields;
}

/** Schritt 4 (Icon): die Aktion bei Fund. */
function detActionStep(c, kind) {
  const text = (SC.actions.icon.find((a) => a.value === c.action) || {}).text || c.action;
  return detCard(4, "Aktion", text + (c.delay ? " · " + c.delay + " s" : ""),
    true, [
    detActionTiles(SC.actions.icon, c.action, (v) => detField("action", v)),
    // Ausgebreitet, nicht als Liste in der Liste: `el()` flacht genau EINE
    // Ebene ab, und ein Array als Kind landet als solches in `appendChild` —
    // was den ganzen Aufbau abbricht.
    ...detActionFields(c, kind),
  ]);
}

/** Ein Feld des OFFENEN Scans setzen — Boss-Scan oder Icon-Scan. */
function detField(field, value) {
  const c = detScan();
  if (!c) return;
  callScan(detCommand("scan_field"), {name: c.name, field: field, value: value});
}

/* -------------------------------------------------------------- Testleiste */

/** Was der letzte Test ergeben hat — und was die Aktion WAERE.
 *
 * **Der Test fuehrt die Aktion nicht aus.** Er erkennt, zeigt und benennt; das
 * steht auch als Nachsatz in der Leiste. Ein Testknopf, der im Editor eines
 * Autoclickers wirklich klickt, ist die schlechteste denkbare Ueberraschung. */
function detTestBar(target) {
  const t = scanKind === "boss" ? SC.boss.test : SC.icon.test;
  if (!t) return false;
  const color = t.ok ? "var(--ok)" : "var(--err)";
  target.append(
    el("b", {style: "color:" + color},
      t.ok ? "Test: " + t.name + " erkannt" : "Test: " + t.name + " nicht erkannt"));
  if (t.method && t.confidence !== null && t.method === "Template")
    target.appendChild(el("span", {class: "metric"}, "Template · " + t.confidence.toFixed(2)));
  if (t.marker_total)
    target.appendChild(el("span", {class: "metric"},
      t.marker_found + " von " + t.marker_total + " Markern · nötig " + t.marker_required));
  if (t.tolerance) target.appendChild(el("span", {class: "metric"}, "Toleranz " + t.tolerance));
  if (t.duration) target.appendChild(el("span", {class: "metric"}, t.duration + " ms"));
  target.appendChild(el("span", {class: "grow"}));
  target.appendChild(el("span", {class: "small"},
    t.ok ? "Aktion wäre: " + t.action + " (wird nicht ausgeführt)" : t.reason));
  // **Der Vorschlag ist der Kern.** Ein Test, der nur „fehlgeschlagen" sagt,
  // laesst einen genau dort stehen, wo man vorher war.
  if (t.proposal)
    target.appendChild(el("button", {class: "btn on",
      onclick: () => detField(t.proposal.field, t.proposal.value)}, t.proposal.text));
  target.appendChild(el("button", {class: "btn quiet", onclick: () => detTest()},
    "nochmal testen"));
  return true;
}

function detTest() { return callScan(detCommand("test")); }

/* ------------------------------------------------------------------ Listen */

function detListBosses(target) {
  const c = detScan();
  if (!c) {
    target.appendChild(el("p", {class: "hint"},
      "Noch kein Boss-Scan. Oben einen anlegen — er ist die Klammer um Region, "
      + "Bosse und Fallback."));
    return;
  }
  const local = c.bosses;
  if (!local.length && !SC.global_bosses.length) {
    target.appendChild(el("p", {class: "hint"},
      "Noch kein Boss. Ein Boss ist eine Vorlage (oder ein paar Farben) und eine "
      + "Aktion dahinter."));
  }
  for (const b of local) target.appendChild(detBossRow(b, false));
  if (SC.global_bosses.length) {
    target.appendChild(el("div", {class: "scan-category-header"},
      "AUS DER BIBLIOTHEK · GILT ZUSÄTZLICH"));
    const names = new Set(local.map((x) => x.name));
    for (const b of SC.global_bosses) {
      // Ein lokaler Boss gleichen Namens hat Vorrang — dann steht der globale
      // hier blass, statt so zu tun, als wuerde er benutzt.
      target.appendChild(detBossRow(b, true, names.has(b.name)));
    }
  }
  target.appendChild(el("button", {class: "empty-zone",
    onclick: () => { scanList = "bibliothek"; renderScans(); }},
    "Boss-Bibliothek (global) · " + SC.global_bosses.length));
}

function detBossRow(b, global, covered) {
  const test = SC.boss.tests[b.name];
  const selected = SC.boss.choice === b.name && SC.boss.choice_global === !!global;
  return el("button", {
    class: "scan-row" + (selected ? " on" : ""),
    style: covered ? "opacity:.5" : null,
    title: covered ? "Ein lokaler Boss gleichen Namens hat Vorrang" : "",
    onclick: () => callScan("boss_select", {name: b.name, global: !!global}),
  },
    b.preview ? el("img", {class: "mini", src: b.preview})
               : el("span", {class: "dot" + (b.marker.length ? "" : " without"),
                             style: b.marker.length ? "background:" + b.marker[0] : ""}),
    el("span", {class: "name"}, b.name),
    b.detection === "none"
      ? el("span", {class: "small", style: "color:var(--accent)",
                    title: "Weder Vorlage noch Marker — nur OCR/LLM können ihn finden"},
           "⚠ keine Vorlage")
      : (test
          ? el("span", {class: "small", style: "color:var(" + (test.ok ? "--slot-ok" : "--err") + ")"},
               test.ok ? "detected" : "nein")
          : el("span", {class: "small mono"},
               (SC.actions.boss.find((a) => a.value === b.action) || {}).text || b.action)));
}

function detListIcons(target) {
  if (!SC.icon_scans.length) {
    target.appendChild(el("p", {class: "hint"},
      "Noch kein Icon-Scan. Er erkennt EIN Symbol in einer Region und tut dann "
      + "etwas — keine Slots, keine Kategorien, kein LLM."));
  }
  for (const c of SC.icon_scans) {
    const test = SC.icon.test && SC.icon.test.name === c.name ? SC.icon.test : null;
    target.appendChild(el("button", {
      class: "scan-row" + (SC.icon.open === c.name ? " on" : ""),
      onclick: () => callScan("icon_scan_open", {name: c.name}),
    },
      c.preview ? el("img", {class: "mini", src: c.preview})
                 : el("span", {class: "dot" + (c.marker.length ? "" : " without"),
                               style: c.marker.length ? "background:" + c.marker[0] : ""}),
      el("span", {class: "name"}, c.name),
      c.detection === "none"
        ? el("span", {class: "small", style: "color:var(--accent)"}, "⚠ ohne Erkennung")
        : (test ? el("span", {class: "small",
                              style: "color:var(" + (test.ok ? "--slot-ok" : "--err") + ")"},
                     test.ok ? "detected" : "nein")
                : el("span", {class: "small mono"},
                     (c.region[2] - c.region[0]) + "×" + (c.region[3] - c.region[1])))));
  }
}

/** Die Bibliothek in der Liste: dieselben Bosse, die in der Mitte als Karten
 *  stehen. Die Knoepfe („+ Boss", „zurueck") stehen NICHT hier, sondern rechts
 *  — sonst gaebe es sie zweimal, und man raet, welcher der fuehrende ist. */
function detListLibrary(target) {
  target.appendChild(el("p", {class: "hint"},
    "Diese Bosse gelten zusätzlich in JEDEM Boss-Scan. Ein lokaler Boss mit "
    + "gleichem Namen hat Vorrang."));
  if (!SC.global_bosses.length) {
    target.appendChild(el("p", {class: "hint"},
      "Noch leer. Rechts einen anlegen — oder einen Boss aus einem Scan "
      + "hierher verschieben."));
    return;
  }
  for (const b of SC.global_bosses) target.appendChild(detBossRow(b, true));
}

/* ---------------------------------------------- Bibliothek als Kartenraster */

function detRenderLibrary() {
  const target = $("scan-library");
  const show = detLibrary();
  target.hidden = !show;
  $("scan-surface").hidden = show || !SC.photo;
  $("scan-empty").hidden = show || !!SC.photo;
  $("scan-no-image").hidden = show || photoPresent();
  if (!show) return;
  target.replaceChildren();
  if (!SC.global_bosses.length) {
    target.appendChild(el("p", {class: "hint"},
      "Die Bibliothek ist leer. Wer denselben Boss in mehreren Scans braucht, "
      + "pflegt ihn sonst mehrfach — und ändert beim nächsten Mal nur die Hälfte."));
    return;
  }
  for (const b of SC.global_bosses) target.appendChild(detLibraryCard(b));
}

function detLibraryCard(b) {
  // Ein vom LLM entdeckter Boss wird als `skip` angelegt: er ist erkannt, aber
  // es ist noch nicht entschieden, was mit ihm passieren soll. Das ist keine
  // Warnung, sondern eine offene Aufgabe — deshalb Amber und ein Hauptknopf.
  const open = b.action === "skip" && b.detection === "none";
  const cardEl = el("div", {class: "seq-card" + (open ? " new-from-llm" : "")},
    el("div", {class: "scan-card-header"},
      b.preview ? el("img", {class: "mini", src: b.preview})
                 : el("span", {class: "dot" + (b.marker.length ? "" : " without"),
                               style: b.marker.length ? "background:" + b.marker[0] : ""}),
      el("b", {class: "grow"}, b.name),
      el("span", {class: "num"}, open ? "neu vom LLM" : b.detection)));
  if (b.marker.length) {
    cardEl.appendChild(el("div", {class: "scan-marker"},
      b.marker.map((h) => el("span", {class: "scan-color-swatch", style: "background:" + h}))));
  }
  if (open) {
    cardEl.appendChild(el("p", {class: "hint"},
      "Seine Aktion ist noch „Schritt überspringen“ — er wird erkannt, aber es "
      + "passiert nichts."));
  } else {
    cardEl.appendChild(el("div", {class: "scan-card-numbers"},
      el("span", {class: "num"}, "konf " + b.confidence.toFixed(2)),
      el("span", {class: "num"}, (SC.actions.boss.find((a) => a.value === b.action)
        || {}).text || b.action),
      b.scan ? el("span", {class: "num"}, "scan → " + b.scan) : null,
      b.delay ? el("span", {class: "num"}, "delay " + b.delay + " s") : null));
  }
  cardEl.appendChild(el("div", {class: "button-pair"},
    el("button", {class: open ? "btn primary" : "btn quiet",
      onclick: () => { scanList = "bosses";
                       callScan("boss_select", {name: b.name, global: true}); }},
      open ? "Aktion zuweisen" : "bearbeiten"),
    el("button", {class: "btn quiet",
      onclick: () => callScan("boss_delete", {name: b.name, global: true})}, "löschen")));
  return cardEl;
}

/* ------------------------------------------------------- Rechte Spalte */

function detInspector(target) {
  if (detLibrary()) return detInspLibrary(target);
  const c = detScan();
  if (!c) {
    target.appendChild(el("p", {class: "hint"}, scanKind === "boss"
      ? "Kein Boss-Scan gewählt. Links einen anlegen."
      : "Kein Icon-Scan gewählt. Links einen anlegen."));
    return;
  }
  if (scanKind === "icon") return detInspIcon(target, c);
  const b = detBoss();
  return b ? detInspBoss(target, c, b) : detInspBossScan(target, c);
}

/** Ohne gewaehlten Boss gehoert die Spalte dem Scan: Region, Toleranz, Fallback. */
function detInspBossScan(target, c) {
  target.appendChild(heading("BOSS-SCAN „" + c.name + "“",
    "Ein Block vom Typ BOSS-SCAN oder BOSS-WATCHER verweist per Name hierauf. "
    + "Umbenennen: oben links.", "bossscan"));
  target.appendChild(numberField("Farb-Toleranz", c.tolerance,
    (v) => detField("tolerance", v), {min: 0, step: 1},
    "Gilt für die Marker-Farben aller Bosse dieses Scans.", "bosstoleranz"));
  target.appendChild(heading("WENN KEIN BOSS ERKANNT",
    "Greift auch dann, wenn OCR und LLM nichts finden.", "bossfallback"));
  target.appendChild(detActionTiles(SC.actions.boss, c.default_action,
    (v) => detField("default_action", v)));
  if (c.default_action === "item_scan") {
    target.appendChild(selection("Item-Scan", [{value: "", text: "— keiner —"}].concat(
      SC.item_scan_names.map((n) => ({value: n, text: n}))), c.default_scan || "",
      (v) => detField("default_scan", v)));
  }
  if (Object.keys(SC.boss.tests).length) {
    target.appendChild(heading("ALLE BOSSE GEGEN DIESES BILD",
      "Was jeder einzelne ergeben hat — und woran es lag.", "bosstests"));
    for (const [name, t] of Object.entries(SC.boss.tests)) {
      target.appendChild(el("div", {class: "scan-result-row" + (t.ok ? " ok" : "")},
        el("span", {}, name),
        el("span", {class: "mono small",
                    style: "color:var(" + (t.ok ? "--ok" : "--dim") + ")"},
           t.ok ? "detected" : "nein"),
        el("span", {class: "reason"}, t.reason)));
    }
  }
  target.appendChild(el("p", {class: "hint"}, "Im Sequenz-Editor: ein Block "
    + "BOSS-SCAN prüft einmal, BOSS-WATCHER wartet, bis ein Boss auftaucht."));
  target.appendChild(el("button", {class: "btn danger", style: "margin-top:14px",
    onclick: () => callScan(detCommand("delete"))}, "Boss-Scan löschen"));
}

/** Der wichtigste Fall: einen bestehenden Boss aendern, ohne den Assistenten
 *  noch einmal zu durchlaufen. Jedes Feld steht hier und ist einzeln setzbar. */
function detInspBoss(target, c, b) {
  target.appendChild(el("div", {class: "button-pair"},
    el("button", {class: "btn quiet",
      onclick: () => callScan("boss_select", {name: ""})}, "‹ zurück zum Scan"),
    el("button", {class: "btn quiet",
      onclick: () => callScan("boss_delete")}, "löschen")));
  target.appendChild(el("button", {class: "btn primary", disabled: !photoPresent(),
    onclick: () => callScan("boss_test")}, "Diesen Boss testen"));
  target.appendChild(heading("BOSS", "Der Name ist zugleich das, was OCR und "
    + "LLM im Bild suchen — er sollte also der Name im Spiel sein.", "bossname"));
  target.appendChild(field("Name", b.name, (v) => callScan("boss_set",
    {name: b.name, global: b.global, field: "name", value: v})));
  if (b.global) {
    target.appendChild(el("p", {class: "hint"},
      "Aus der Bibliothek — Änderungen gelten in jedem Boss-Scan."));
  }
  target.appendChild(heading("ERKENNUNG", "Template ODER Farb-Marker. Beides "
    + "gesetzt heisst: beides muss stimmen.", "bosserkennung"));
  for (const part of detDetectionFields(b, "boss", b.name))
    if (part) target.appendChild(part);
  target.appendChild(heading("AKTION BEI TREFFER",
    "Was passiert, wenn genau dieser Boss erkannt wird.", "bossaktion"));
  target.appendChild(detActionTiles(SC.actions.boss, b.action,
    (v) => callScan("boss_set", {name: b.name, global: b.global,
                                   field: "action", value: v})));
  for (const part of detActionFields(b, "boss", b.name))
    if (part) target.appendChild(part);
  target.appendChild(el("button", {class: "btn quiet", style: "margin-top:14px",
    title: "Bosse der Bibliothek gelten in jedem Boss-Scan",
    onclick: () => callScan("boss_move_global", {name: b.name, global: b.global})},
    b.global ? "In diesen Scan holen" : "In die Bibliothek verschieben"));
}

function detInspIcon(target, c) {
  target.appendChild(el("button", {class: "btn primary", disabled: !photoPresent(),
    onclick: () => callScan("icon_test")}, "Icon-Scan testen"));
  target.appendChild(heading("ICON-SCAN „" + c.name + "“",
    "Erkennt EIN Symbol in einer Region und tut dann etwas. Ein Block vom Typ "
    + "ICON-SCAN verweist per Name hierauf.", "iconscan"));
  // **Der Ausschnitt zeigt, was der Scan sieht.** Vier Zahlen sagen nicht, ob
  // die Region sitzt; ein Bild von 104 px sagt es in einer Sekunde.
  target.appendChild(c.crop_image
    ? el("img", {class: "scan-template square", src: c.crop_image, alt: ""})
    : el("div", {class: "scan-template square empty"}, "kein Bild"));
  target.appendChild(el("p", {class: "hint"},
    "Der Ausschnitt zeigt, was der Scan sieht — "
    + (c.region[2] - c.region[0]) + "×" + (c.region[3] - c.region[1])
    + " ab (" + c.region[0] + ", " + c.region[1] + ")."));
  target.appendChild(el("button", {class: "btn", disabled: !photoPresent(),
    onclick: () => callScan("region_mode", {kind: "icon", mode: "region"})},
    "Region neu aufziehen"));
  target.appendChild(heading("AKTION BEI FUND",
    "Was passiert, wenn das Symbol da ist.", "iconaktion"));
  target.appendChild(detActionTiles(SC.actions.icon, c.action,
    (v) => detField("action", v)));
  for (const part of detActionFields(c, "icon"))
    if (part) target.appendChild(part);
  // **Das ELSE gehoert dem Block, nicht dem Scan.** `IconScanConfig` hat kein
  // else-Feld, und eins hier einzufuehren hiesse, dieselbe Sache an zwei
  // Stellen zu haben: der Sequenz-Editor setzt sie am Block, wo sie auch fuer
  // Item- und Boss-Scans steht.
  target.appendChild(heading("WENN NICHTS ERKANNT",
    "Die Ersatzaktion gehört dem Block in der Sequenz, nicht dem Scan — dort "
    + "steht sie für alle drei Scan-Arten an derselben Stelle.", "iconelse"));
  target.appendChild(el("p", {class: "hint"},
    "Im Sequenz-Editor am Block einstellen. Als Befehl im Konsolen-Editor: "
    + "icon " + c.name + " else skip"));
  target.appendChild(el("button", {class: "btn danger", style: "margin-top:14px",
    onclick: () => callScan(detCommand("delete"))}, "Icon-Scan löschen"));
}

function detInspLibrary(target) {
  target.appendChild(heading("BOSS-BIBLIOTHEK",
    "Gilt zusätzlich in jedem Boss-Scan. Ein lokaler Boss mit gleichem Namen "
    + "hat Vorrang.", "bossbib"));
  target.appendChild(el("p", {class: "hint"},
    SC.global_bosses.length + " Boss(e). Neu entdeckte Bosse landen hier, wenn "
    + "boss_learn_global eingeschaltet ist (Reiter Einstellungen) — sonst im "
    + "Scan, der sie gefunden hat."));
  target.appendChild(el("button", {class: "btn primary",
    onclick: () => callScan("boss_new", {global: true})}, "+ Boss anlegen"));
  target.appendChild(el("button", {class: "btn quiet",
    onclick: () => { scanList = "bosses"; renderScans(); }}, "zurück zum Scan"));
}

/* ------------------------------------------------------------------ Overlay */

/** Die Region des offenen Erkennungs-Scans und ihr Klickpunkt.
 *
 * Gezeichnet wird nur die des OFFENEN Scans, nicht jede vorhandene: zwanzig
 * Rechtecke auf einem Bild sind kein Ueberblick, sondern ein Gitter. */
function detOverlay(svg, px) {
  const c = detScan();
  if (!c) return;
  const t = scanKind === "boss" ? SC.boss.test : SC.icon.test;
  const state = !t ? "" : (t.ok ? " ok" : " miss");
  const [x1, y1] = scanToImage(c.region[0], c.region[1]);
  const [x2, y2] = scanToImage(c.region[2], c.region[3]);
  svg.appendChild(svgEl("rect", {x: x1, y: y1, width: x2 - x1, height: y2 - y1,
    class: "scan-region-f" + state}));
  svg.appendChild(svgEl("rect", {x: x1, y: y1, width: x2 - x1, height: y2 - y1,
    class: "scan-region" + state}));
  const badge = (t && t.ok && t.confidence !== null && t.method === "Template")
    ? t.name + " · " + t.confidence.toFixed(2)
    : (t ? (t.ok ? t.name + " erkannt" : "nicht erkannt")
         : "Region · " + (c.region[2] - c.region[0]) + "×" + (c.region[3] - c.region[1]));
  svg.appendChild(svgEl("text", {x: x1, y: y2 + 13 * px, class: "scan-badge",
    "font-size": 11 * px, "stroke-width": 3 * px,
    fill: !t ? null : (t.ok ? SLOT_COLOR.match : "#EF4444")}, badge));

  // Der Klickpunkt der Aktion: gestrichelt und in Amber — er ist ein
  // Handlungsort, keine Erkennung.
  const obj = scanKind === "boss" ? detBoss() : c;
  const point = obj && obj.point_id !== null && obj.point_id !== undefined
    ? SC.points.find((p) => p.id === obj.point_id) : null;
  if (!point || obj.action !== "click") return;
  const [ax, ay] = scanToImage(point.x, point.y);
  const arm = 9 * px;
  svg.appendChild(svgEl("rect", {class: "scan-action", x: ax - arm, y: ay - arm,
    width: arm * 2, height: arm * 2}));
  svg.appendChild(svgEl("text", {x: ax - arm, y: ay - arm - 4 * px, class: "scan-badge",
    "font-size": 10 * px, "stroke-width": 3 * px, fill: "#F59E0B"},
    "Klickpunkt Aktion"));
}

/* ------------------------------------------------------------ Ansicht: Teilen
 *
 * Ein Bündel schreiben und eines einlesen. Beide Seiten arbeiten auf dem
 * GESPEICHERTEN Stand — was im Fenster offen ist, liegt nicht auf Platte. */
let T = null;
let shareExport = {};    // welche Teile ins Bündel kommen
let shareImport = {};    // welche Teile eingelesen werden
let shareMode = "auto";
let shareMerge = true;

async function renderShare(fresh) {
  const answer = await ask("share_data");
  if (!answer || view !== "teilen") return;
  T = answer;
  for (const t of T.parts) {
    if (shareExport[t.key] === undefined) shareExport[t.key] = true;
    if (shareImport[t.key] === undefined) shareImport[t.key] = true;
  }
  const memo = rememberFocus();
  shareRenderExport();
  shareRenderMiddle();
  shareRenderImport();
  setStatus(T.status);
  restoreFocus(memo);
}

/** Ein Befehl an den Teilen-Teil. Antwort ist die neue Teilen-Aufnahme. */
async function callShare(name, data_reload) {
  const answer = await ask(name, data_reload);
  if (!answer) return;
  T = answer;
  await renderShare();
}

function shareCheckbox(target, selection, numbers) {
  for (const t of T.parts) {
    const row = el("label", {class: "share-row on"});
    const box = el("input", {type: "checkbox"});
    box.checked = !!selection[t.key];
    box.addEventListener("change", () => { selection[t.key] = box.checked; renderShare(); });
    row.append(box, el("span", {}, t.text),
      el("span", {class: "num"}, String(numbers[t.key] ?? 0)));
    target.appendChild(row);
  }
}

function shareRenderExport() {
  const target = $("share-export");
  const head = el("div", {class: "section"},
    heading("EXPORTIEREN",
      "Schreibt ein ZIP nach exports/. Enthält nur, was gespeichert ist.", "export"));
  if (T.open) {
    head.appendChild(el("div", {class: "foreign-hint"},
      "Im Fenster gibt es ungespeicherte Änderungen — die kommen nicht mit. "
      + "Erst speichern, dann exportieren."));
  }
  target.replaceChildren(head);

  const bodyEl = el("div", {class: "section growing"});
  shareCheckbox(bodyEl, shareExport, T.inventory);
  bodyEl.appendChild(field("Dateiname (leer = mit Zeitstempel)", "",
    () => {}, {id: "share-name"}));
  // **Die Referenzpunkte kommen aus dem Spielfenster.** Ist es offen, rechnet
  // der Empfänger die Koordinaten selbst um; sonst setzt er zwei Punkte von Hand.
  bodyEl.appendChild(el("p", {class: "hint"}, T.window && T.window.found
    ? "Spielfenster „" + T.window.title + "“: " + T.window.width + "×"
      + T.window.height + " px. Der Empfänger rechnet damit automatisch um."
    : (T.window
        ? "Spielfenster „" + T.window.title + "“ ist nicht offen — der Empfänger "
          + "setzt beim Import zwei Punkte von Hand."
        : "Kein Fenstertitel eingestellt (window_focus_title) — der Empfänger "
          + "setzt beim Import zwei Punkte von Hand.")));
  bodyEl.appendChild(el("button", {class: "btn primary",
    onclick: () => callShare("export_start",
      {parts: shareExport, name: ($("share-name") || {}).value || ""})},
    "Bündel schreiben"));
  target.appendChild(bodyEl);
}

function shareRenderMiddle() {
  const target = $("share-middle");
  target.replaceChildren();
  const cardEl = el("div", {class: "share-card"}, el("h3", {}, "Vorhandene Bündel"));
  if (!T.exports.length) {
    cardEl.appendChild(el("p", {class: "hint"},
      "Noch keins. „Bündel schreiben“ legt eines unter exports/ an."));
  }
  const listEl = el("div", {class: "share-list"});
  for (const e of T.exports) {
    listEl.appendChild(el("div", {class: "share-row"},
      el("span", {class: "mono"}, e.name),
      el("span", {class: "num mono"}, e.kb + " KB"),
      el("button", {class: "btn quiet",
        onclick: () => callShare("import_check", {path: "exports/" + e.name})},
        "einlesen")));
  }
  cardEl.appendChild(listEl);
  target.appendChild(cardEl);

  target.appendChild(el("div", {class: "share-card"},
    el("h3", {}, "Weitergeben"),
    el("p", {class: "hint"},
      "Die ZIP-Datei verschicken. Der Empfänger legt sie in seinen "
      + "Autoclicker-Ordner und liest sie hier oder mit CTRL+ALT+I ein. "
      + "Koordinaten werden dabei auf sein Fenster umgerechnet.")));
}

function shareRenderImport() {
  const target = $("share-import");
  const i = T.import;
  const head = el("div", {class: "section"},
    heading("IMPORTIEREN",
      "Liest ein Bündel ein und rechnet die Koordinaten um.", "import"),
    // EIN Knopf ueber die volle Breite heisst `btn breit` — `wachse` in einer
    // `series` war dasselbe mit einer zweiten Schreibweise.
    el("button", {class: "btn wide", onclick: () => callShare("file_choose")},
      "Datei wählen …"),
    field("oder Pfad", i ? i.path : "",
      (v) => callShare("import_check", {path: v})));
  target.replaceChildren(head);

  const bodyEl = el("div", {class: "section growing"});
  if (!i) {
    bodyEl.appendChild(el("p", {class: "hint"},
      "Noch keine Datei gewählt. Ein Bündel ist ein ZIP mit manifest.json."));
    target.appendChild(bodyEl);
    return;
  }
  bodyEl.appendChild(el("div", {class: "field-quiet"}, i.file,
    el("span", {class: "mono"}, i.created || "")));
  shareCheckbox(bodyEl, shareImport, i.content);

  bodyEl.appendChild(heading("KOORDINATEN",
    "Wie die Stellen des Absenders auf deinen Bildschirm kommen.", "importkoord"));
  // Ohne beidseitig bekanntes Fenster gibt es nichts zu wählen — eine Kachel,
  // die nichts tut, ist schlechter als keine.
  const modesList = (i.auto ? [{value: "auto", text: "aus Fenstergrösse"}] : [])
    .concat([{value: "identity", text: "1:1 übernehmen"}]);
  bodyEl.appendChild(segment(modesList, i.auto ? shareMode : "identity",
    (v) => { shareMode = v; renderShare(); }));
  bodyEl.appendChild(el("p", {class: "hint"}, i.auto
    ? "Beide Seiten kennen ihr Spielfenster — die Umrechnung geht automatisch."
    : "Ohne beidseitig bekanntes Spielfenster geht nur 1:1. Für ein echtes "
      + "Umrechnen zwei Punkte setzen: CTRL+ALT+I im Hauptprozess."));

  bodyEl.appendChild(toggle("Vorhandenes behalten und ergänzen", shareMerge,
    (v) => { shareMerge = v; renderShare(); }));
  bodyEl.appendChild(el("p", {class: "hint"}, shareMerge
    ? "Gleiche Namen werden übersprungen."
    : "Achtung: gleiche Namen werden überschrieben."));
  bodyEl.appendChild(el("button", {class: "btn primary",
    onclick: () => callShare("import_start",
      {parts: shareImport, mode: shareMode, merge: shareMerge})},
    "Bündel einlesen"));
  target.appendChild(bodyEl);
}

/* ------------------------------------------------------------ Ansicht: Bericht
 *
 * Der Live-Run zeigt das Jetzt, dieser Reiter das Gestern. Eigener Zustand
 * neben `S`, wie bei Teilen und Werkzeugen: er liest `logs/`, nicht die
 * geoeffnete Sequenz.
 *
 * Gezeichnet wird mit denselben Bausteinen wie der Werkzeuge-Reiter
 * (`wz-metrics`, `wz-subheader`, `abschnitt`) statt mit eigenen. Ein
 * achter Reiter, der sich seine eigene Gestalt gibt, kostet mehr als er
 * einbringt — und die Kennzahlen-Kacheln koennen genau das schon: gleiche
 * Spalten ueber `auto-fit`, gleiche Hoehe, gleiche Schrift. */

let B = null;

async function renderReport(data_reload) {
  const answer = await ask("report_data", data_reload === undefined ? null : data_reload);
  if (!answer || view !== "bericht") return;
  B = answer;
  const memo = rememberFocus();
  reportRenderLeft();
  reportRenderMiddle();
  reportRenderRight();
  restoreFocus(memo);
}

/** Sekunden als h:mm:ss — dieselbe Form wie in `tools/log_report.py`. */
function repDuration(sec) {
  const whole = Math.max(0, Math.round(sec || 0));
  const h = Math.floor(whole / 3600), m = Math.floor((whole % 3600) / 60), s = whole % 60;
  const two = (n) => String(n).padStart(2, "0");
  return h ? h + ":" + two(m) + ":" + two(s) : m + ":" + two(s);
}

/** Grosse Zahlen mit Tausenderpunkten. Gold geht in die Millionen, und
 *  „143920771" liest niemand. */
function repNumber(n, positions) {
  return (n || 0).toLocaleString("de-DE", {maximumFractionDigits: positions || 0});
}

/* Eine Rangzeile: Name links, Anzahl rechts, darunter ein Balken im Verhaeltnis
 * zum groessten Wert der Liste. VIER Listen benutzen sie (Timeouts, Items,
 * Erkanntes, Nachpruefung) — eine Bauform fuer alle, sonst hat dieselbe Sache
 * vier Gestalten. */
function repRank(name, value, share_pct, zusatz, kind) {
  const row = el("div", {class: "rep-rank" + (kind ? " " + kind : "")},
    el("span", {class: "rep-rank-name", title: name}, name),
    el("span", {class: "rep-rank-value mono"}, value),
    el("div", {class: "rep-bar"},
      el("div", {class: "rep-bar-fill",
        style: "width:" + Math.max(2, Math.round(share_pct * 100)) + "%"})));
  if (zusatz) row.appendChild(el("span", {class: "rep-rank-extra"}, zusatz));
  return row;
}

function repList(title, help, key, entries) {
  const boxEl = el("div", {class: "share-card"},
    heading(title, help, key));
  const highest = entries.reduce((m, e) => Math.max(m, e.value), 0) || 1;
  for (const e of entries)
    boxEl.appendChild(repRank(e.name, repNumber(e.value), e.value / highest,
      e.extra, e.kind));
  return boxEl;
}

/* ------------------------------------------------------------------- links */

function reportRenderLeft() {
  const target = $("rep-left");
  const head = el("div", {class: "section sticky"},
    heading("SITZUNGEN",
      "Eine Zeile je Lauf, neueste oben. „Alle zusammen“ ist der Normalfall: "
      + "die Frage nach dem haengenden Schritt stellt sich ueber die Nacht, "
      + "nicht ueber eine einzelne Datei.", "ber-sitzungen"));
  if (!B.active) {
    head.appendChild(el("p", {class: "hint warning"},
      "session_log_enabled ist aus — neue Laeufe schreiben nichts mit."));
  }
  target.replaceChildren(head);

  const bodyEl = el("div", {class: "section growing"});
  if (!B.available) {
    bodyEl.appendChild(el("p", {class: "hint"}, B.error));
    target.appendChild(bodyEl);
    return;
  }
  if (!B.sessions.length) {
    bodyEl.appendChild(el("p", {class: "hint"}, B.folder
      ? "Keine Logs in " + B.folder + "."
      : "Noch kein Log-Ordner. Er entsteht beim ersten Lauf mit "
        + "session_log_enabled."));
    target.appendChild(bodyEl);
    return;
  }

  bodyEl.appendChild(repSession({
    file: "", title: "Alle zusammen",
    bottom: B.sessions.length + " Sitzung(en)",
  }));
  for (const s of B.sessions) {
    bodyEl.appendChild(repSession({
      file: s.file,
      title: s.begin || s.file,
      bottom: repDuration(s.duration) + " · " + repNumber(s.clicks) + " Klicks",
      warning: s.timeouts ? s.timeouts + "× Timeout" : "",
    }));
  }
  if (B.skipped_files) {
    bodyEl.appendChild(el("p", {class: "hint"},
      B.skipped_files + " aeltere Datei(en) nicht gelesen — der Reiter liest die "
      + "neuesten 50."));
  }
  target.appendChild(bodyEl);
}

function repSession(s) {
  const on = (B.selected || "") === s.file;
  const row = el("button", {
    class: "rep-session" + (on ? " on" : ""),
    onclick: () => renderReport({file: s.file}),
  },
    el("span", {class: "rep-session-title"}, s.title),
    el("span", {class: "rep-session-bottom"}, s.bottom));
  if (s.warning)
    row.appendChild(el("span", {class: "rep-session-warn"}, s.warning));
  return row;
}

/* ------------------------------------------------------------------- Mitte */

function reportRenderMiddle() {
  const target = $("rep-middle");
  target.replaceChildren();
  const b = B.bericht;
  if (!b || !b.sessions) {
    target.appendChild(el("p", {class: "hint"},
      "Nichts auszuwerten. Der Bericht liest die CSV-Dateien, die ein Lauf mit "
      + "eingeschaltetem Session-Log hinterlaesst."));
    return;
  }

  target.appendChild(el("div", {class: "wz-metrics"},
    wzMetric(repDuration(b.duration), "Laufzeit", "neutral"),
    wzMetric(repNumber(b.clicks), "Klicks", "neutral"),
    wzMetric(repNumber(b.items_total), "Items", "neutral"),
    wzMetric(repNumber(b.timeouts_total), "Timeouts",
      b.timeouts_total ? "hint" : "neutral"),
    wzMetric(repNumber(b.verify_miss_total), "ohne Wirkung",
      b.verify_miss_total ? "error" : "neutral")));

  // DIE Frage, fuer die es den Reiter gibt — deshalb steht sie oben und nicht
  // zwischen den Item-Zahlen.
  if (b.timeouts.length) {
    target.appendChild(repList("TIMEOUTS — WO DIE SEQUENZ HAENGT",
      "Der oberste Eintrag ist der Schritt, den es zu reparieren lohnt: dort "
      + "ist eine Farb-Bedingung am haeufigsten nicht aufgegangen.", "ber-timeout",
      b.timeouts.map(([name, n]) => ({name: name, value: n, kind: "warn"}))));
  } else {
    target.appendChild(el("div", {class: "wz-success"}, wzIcon("ok"),
      el("div", {}, el("b", {}, "Keine Timeouts"),
        el("span", {}, "Jede Farb-Bedingung ist aufgegangen."))));
  }

  if (b.verify_miss.length) {
    target.appendChild(repList("NACHPRUEFUNG — KLICKS OHNE WIRKUNG",
      "Haeufige Fehlschlaege heissen: das Klickziel sitzt falsch, oder das "
      + "Spiel braucht laenger als verify_timeout.", "ber-verify",
      b.verify_miss.map(([name, n, good]) => ({
        name: name, value: n, kind: "error",
        extra: "bestätigt " + good + "/" + (good + n),
      }))));
  }

  if (b.items.length) {
    target.appendChild(repList("GEFUNDENE ITEMS", "", "ber-items",
      b.items.map(([name, n]) => ({name: name, value: n}))));
  }
  if (b.detected.length) {
    target.appendChild(repList("ERKANNT (BOSS/ICON)", "", "ber-erkannt",
      b.detected.map(([name, n]) => ({name: name, value: n}))));
  }
  if (b.disturbances.length) {
    target.appendChild(repList("UNTERBRECHUNGEN",
      "Fokusverluste und Humanize-Pausen. Eine Haeufung heisst, dass das "
      + "Spielfenster oft nicht vorn war.", "ber-stoer",
      b.disturbances.map(([name, n]) => ({name: name, value: n}))));
  }

  for (const [file, error] of b.unreadable) {
    target.appendChild(el("p", {class: "hint warning"},
      file + ": nicht lesbar (" + error + ")"));
  }
  if (b.unbekannt.length) {
    // Dieselbe Meldung wie in der Konsole: eine neue Ereignisart soll auffallen,
    // nicht stillschweigend fehlen.
    target.appendChild(el("p", {class: "hint"},
      "Nicht ausgewertete Ereignisarten: " + b.unbekannt.join(", ")));
  }
}

/* ------------------------------------------------------------------- rechts */

function reportRenderRight() {
  const target = $("rep-right");
  const head = el("div", {class: "section sticky"},
    heading("ERTRAG",
      "Stueckzahlen aus dem Log mal Marktwert aus der Analyse. Die Verbindung "
      + "zwischen beiden ist eine Datei (scan_market_value_file) — die "
      + "Marktanalyse selbst laeuft getrennt.", "ber-ertrag"));
  target.replaceChildren(head);

  const bodyEl = el("div", {class: "section growing"});
  const e = B.yield_value;
  if (!e) {
    bodyEl.appendChild(el("p", {class: "hint"},
      "Keine Bewertung: scan_market_value_file ist leer oder es wurden keine "
      + "Items gefunden. Mit eingetragener marktwert.json steht hier, was der "
      + "Lauf eingebracht hat."));
    target.appendChild(bodyEl);
    return;
  }
  if (!e.readable) {
    bodyEl.appendChild(el("p", {class: "hint warning"},
      "Marktwert-Datei nicht lesbar: " + e.file));
    target.appendChild(bodyEl);
    return;
  }

  bodyEl.appendChild(el("div", {class: "wz-metrics"},
    wzMetric(repNumber(e.gold), "Gold gesamt", "neutral"),
    wzMetric(e.per_hour === null ? "—" : repNumber(e.per_hour), "Gold/h",
      "neutral")));
  // **Obergrenze, keine Abrechnung.** `item_found` heisst „erkannt", nicht
  // „eingesammelt und verkauft". Das steht hier und nicht im ⓘ: wer die Zahl
  // liest, muss es lesen, ohne danach zu fragen.
  bodyEl.appendChild(el("p", {class: "hint warning"},
    "Obergrenze: gezaehlt wird, was der Scan ERKANNT hat — nicht, was "
    + "eingesammelt und verkauft wurde."));

  const highest = e.rows.reduce((m, z) => Math.max(m, z[3]), 0) || 1;
  const listEl = el("div", {class: "share-card"});
  for (const [name, count, value, totalSum] of e.rows) {
    listEl.appendChild(repRank(name, repNumber(totalSum), totalSum / highest,
      count + "× à " + repNumber(value)));
  }
  bodyEl.appendChild(listEl);

  if (e.without_value.length) {
    bodyEl.appendChild(el("p", {class: "hint"},
      e.without_value.length + " Item(s) ohne Marktwert: "
      + e.without_value.map(([name, n]) => name + " (" + n + "×)").join(", ")));
  }
  target.appendChild(bodyEl);
}

/* ----------------------------------------------------- Ansicht: Einstellungen */

/* --------------------------------------------------------------- Werkzeuge
 *
 * Was bisher nur im Punkte-Menue der Konsole ging: pruefen (`check`),
 * kalibrieren (`fix`) und Nachklicken (`klick`). Eigener Zustand neben `S`,
 * wie bei Einstellungen und Teilen — der Reiter arbeitet auf `sequence.json` und
 * dem ganzen Bestand, nicht auf der geoeffneten Sequenz.
 *
 * `wzOpenTool` ist reiner Oberflaechenzustand (welches Werkzeug in der Mitte
 * steht), `W` die Antwort der Bruecke, `wzReport` das Ergebnis der letzten
 * Pruefung. Die Pruefung steht bewusst NICHT in `W`: sie kostet einen Durchlauf
 * ueber den ganzen Bestand, und den will man auf Knopfdruck, nicht bei jedem
 * Neuzeichnen. */
let W = null;
let wzOpenTool = "check";
let wzReport = null;
let wzScopeState = {};
// Der Hauptprozess besitzt die Aufnahme. Dieser Merker sagt nicht mehr als das,
// was das Studio sicher weiss: der Startauftrag wurde erfolgreich abgelegt.
let wzRecordingStarted = false;
let wzRecordingName = "";
let wzRecordingCycles = 0;
let wzRecordingDescription = "";
let wzRecordingPoll = 0;
let wzRecordingLivePoll = 0;
let wzRecordingLive = {active: false, paused: false, count: 0, events: []};
/* Der Live-Stand der Klick-Runde. Sie laeuft im HAUPTPROZESS (dort haengt der
 * Maus-Hook), also weiss dieses Fenster von sich aus nichts ueber sie — der
 * Stand kommt ueber `.nachklick.json`. Ohne ihn stand hier nur „gestartet",
 * waehrend die Konsole jeden Schritt einzeln meldete. */
let wzReclickPoll = 0;
let wzReclickLive = {active: false, index: 0, total: 0, history: [], point: {}};
/* Eine offene Farb-Rueckfrage: die Stelle ist angefahren, aber die Farbe dort
 * weicht von der gespeicherten ab. Bis das jemand bestaetigt, ist NICHTS gesetzt
 * - der Zustand lebt nur hier, nicht in der Bruecke. */
let wzColorQuestion = null;
let wzPointId = null;
let wzColorAnalysis = null;

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
const WAIT_ACTIONS = {
  point_capture: ["Stelle aufnehmen", 1],
  area_capture: ["Screenshot-Bereich aufziehen", 2],
  mouse_position: ["Parkposition setzen", 1],
  tool_point_capture: ["Punkt aufnehmen", 1],
  tool_colors: ["Farbe messen", 1],
  calib_reference: ["Referenzpunkt setzen", 1],
};

let waitCounter = null;
let workClock = null;
let workLine = null;
let workEsc = null;

/** Blendet ein, worauf gerade gewartet wird — mit Countdown bis zum Zeitablauf. */
function showWait(name) {
  const [what, press] = WAIT_ACTIONS[name] || ["Stelle setzen", 1];
  const limit = (S && S.wait_timeout) || (W && W.wait_timeout) || 60;
  let remainder = Math.round(limit);
  const number = el("span", {class: "wait-remaining"}, remainder + " s");
  const boxEl = el("div", {class: "wait-box"},
    el("div", {class: "wait-title"}, what),
    el("div", {class: "wait-text"},
      "Fahre mit der Maus an die Stelle im Spiel und drücke ",
      el("b", {}, "ENTER"),
      press > 1 ? " — " + press + "× nacheinander, eine Ecke je Druck." : "."),
    el("div", {class: "wait-footer"},
      el("span", {}, "ESC bricht ab"), number));
  hideWait();
  document.body.appendChild(
    el("div", {class: "wait-shell", id: "wait-shell"}, boxEl));
  // Der Countdown ist die zweite Haelfte der Auskunft: DASS gewartet wird, sagt
  // der Kasten — wie lange noch, nur die Zahl. Laeuft sie ab, endet der Aufruf
  // von selbst, und die Bruecke meldet „Nichts gedrueckt".
  waitCounter = setInterval(() => {
    remainder -= 1;
    number.textContent = Math.max(0, remainder) + " s";
    if (remainder <= 0) clearInterval(waitCounter);
  }, 1000);
}

function hideWait() {
  clearInterval(waitCounter);
  waitCounter = null;
  clearInterval(workClock);
  workClock = null;
  workLine = null;
  if (workEsc) document.removeEventListener("keydown", workEsc);
  workEsc = null;
  const alt = $("wait-shell");
  if (alt) alt.remove();
}

/** Zeigt, dass ein langer Aufruf LAEUFT — mit hochzaehlender Uhr.
 *
 * Der Unterschied zu `showWait()` ist die Frage dahinter: dort wartet die
 * Bruecke auf einen ENTER-Druck und hat eine feste Grenze, hier arbeitet sie
 * und niemand weiss, wie lange. Ein Countdown waere hier eine erfundene Zahl —
 * die hochzaehlende Uhr sagt nur, dass es weitergeht, und genau das ist die
 * Frage bei sechsundfuenfzig Modell-Aufrufen hintereinander.
 */
function showWork(title, text, cancel) {
  const number = el("span", {class: "wait-remaining"}, "0 s");
  const row = el("div", {class: "wait-text"}, text);
  let sec = 0;
  const boxEl = el("div", {class: "wait-box"},
    el("div", {class: "wait-title"}, title), row,
    // **Ein Abbruch nur da, wo es einen gibt.** Ein Knopf, der einen
    // einzelnen HTTP-Aufruf nicht stoppen kann, waere ein Bedienelement, das
    // nichts tut — dieselbe Regel wie bei den Kacheln im Teilen-Reiter.
    cancel ? el("button", {class: "btn quiet wide", style: "margin-top:10px",
                            id: "work-cancel",
                            onclick: () => cancelWork(cancel)}, "Abbrechen") : null,
    el("div", {class: "wait-footer"},
      el("span", {}, cancel ? "ESC bricht ab" : "läuft …"), number));
  hideWait();
  document.body.appendChild(
    el("div", {class: "wait-shell", id: "wait-shell"}, boxEl));
  workLine = row;
  workClock = setInterval(() => { sec += 1; number.textContent = sec + " s"; }, 1000);
  if (cancel) {
    workEsc = (e) => { if (e.key === "Escape") cancelWork(cancel); };
    document.addEventListener("keydown", workEsc);
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
function cancelWork(cancel) {
  cancel();
  const button = $("work-cancel");
  if (button) {
    button.disabled = true;
    button.textContent = "Bricht ab …";
  }
  sayWork("Wartet noch auf die laufende Vorlage — die Antwort ist schon "
              + "unterwegs und laesst sich nicht zurueckholen.");
}

/** Die Zeile im Arbeits-Kasten austauschen, ohne ihn neu aufzubauen.
 *
 * Neu gebaut ginge auch und faenge die Uhr jedes Mal wieder bei 0 an — bei
 * sechsundfuenfzig Schritten also eine Uhr, die nie ueber drei Sekunden kommt
 * und damit nichts mehr sagt. */
function sayWork(text) {
  if (workLine) workLine.textContent = text;
}

let autonameCancel = false;

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
async function scanAutonameRun(data_reload) {
  autonameCancel = false;
  await callScan("scan_autoname_start", data_reload);
  // Kein Durchgang in der Momentaufnahme heisst: abgelehnt (LLM aus, nichts
  // mit Vorlage). Die Statuszeile sagt bereits, warum.
  if (!SC.autoname) return;
  showWork("Items benennen", "", () => { autonameCancel = true; });
  try {
    while (SC.autoname && SC.autoname.open > 0 && !autonameCancel) {
      const a = SC.autoname;
      sayWork("Vorlage " + (a.done + 1) + " von " + a.total
                  + " — " + a.renamed + " benannt");
      await callScan("scan_autoname_step", null);
    }
  } finally {
    hideWait();
    await callScan("scan_autoname_end", {cancelled: autonameCancel});
  }
}

/** Wie `withWait`, nur fuer Aufrufe, die selbst RECHNEN statt auf ENTER zu warten.
 *
 * `kind` waehlt denselben Kanal, den der Aufruf ohnehin haette: `scan` ersetzt
 * die Scan-Momentaufnahme, `ask` fragt nur. Der Einstellungen-Reiter braucht
 * den zweiten — seine Antwort ist keine Momentaufnahme, und ueber `callScan`
 * geholt zerschoesse sie den Scans-Reiter.
 */
async function withWork(kind, name, data_reload, title, text) {
  showWork(title, text);
  try {
    return kind === "scan" ? await callScan(name, data_reload) : await ask(name, data_reload);
  } finally {
    hideWait();
  }
}

/** Ruft eine blockierende Methode und zeigt so lange, worauf gewartet wird.
 *
 * `kind` waehlt den Kanal, den der Aufruf ohnehin haette: `call` ersetzt die
 * Momentaufnahme, `tool` zeichnet den Reiter neu, `ask` fragt nur. Das
 * Overlay aendert daran nichts — es legt sich nur davor.
 */
async function withWait(kind, name, data_reload) {
  showWait(name);
  try {
    return kind === "call" ? await call(name, data_reload)
         : kind === "tool" ? await callTool(name, data_reload)
         : await ask(name, data_reload);
  } finally {
    hideWait();
  }
}

const WZ_TOOLS = [
  {key: "recording", name: "Sequenz aufnehmen", command: "rec", scopeKind: "neu",
   short: "Echtes Spielen als neue Sequenz aufzeichnen"},
  {key: "check", name: "Bestand prüfen", command: "check", scopeKind: "inventory",
   short: "Fehler und unvollständige Verknüpfungen finden"},
  {key: "points", name: "Punkte verwalten", command: "points", scopeKind: "sequence",
   short: "Aufnehmen, nachmessen, umbenennen und sicher löschen"},
  // `nichts` ist kein fehlender Wert, sondern eine eigene Aussage: dieses
  // Werkzeug MISST nur den Bildschirm und schreibt nirgends hin. Es stand hier
  // auf „bestand" und war damit schlicht falsch — und die Zeile wurde als
  // einzige gar nicht erst gezeichnet, womit die Unwahrheit nicht auffiel.
  {key: "colors", name: "Farben analysieren", command: "color", scopeKind: "nichts",
   short: "Pixel und häufigste Bildschirmfarben sichtbar machen"},
  {key: "calibrate", name: "Kalibrieren", command: "fix", scopeKind: "inventory",
   short: "Koordinaten an ein neues Bildschirm-Layout anpassen"},
  {key: "reclick", name: "Punkte nachklicken", command: "klick", scopeKind: "sequence",
   short: "Alle Klickstellen geführt im Spiel kontrollieren"},
];

/** Kleine, lokale Linien-Icons. Keine Schriftzeichen und keine externe Datei:
 *  dadurch bleiben Strichstärke und Ausrichtung in jedem System identisch. */
function wzIcon(kind) {
  const paths = {
    recording: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18", "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8"],
    check: ["M9 11l2 2 4-5", "M12 3a9 9 0 1 0 9 9", "M16 4l5-1-1 5"],
    calibrate: ["M12 2v4M12 18v4M2 12h4M18 12h4", "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8"],
    reclick: ["M5 3l12 9-6 1 3 6-3 2-3-6-4 4z"],
    points: ["M12 2v5M12 17v5M2 12h5M17 12h5", "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8"],
    colors: ["M12 3c-4 4-7 7-7 11a7 7 0 0 0 14 0c0-4-3-7-7-11z", "M9 15h6"],
    info: ["M12 11v6M12 7h.01", "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20"],
    ok: ["M4 12l5 5L20 6"],
    error: ["M6 6l12 12M18 6L6 18"],
    hint: ["M12 3L2 21h20z", "M12 9v5M12 18h.01"],
    folder: ["M3 6h7l2 2h9v11H3z"],
  };
  const svg = svgEl("svg", {class: "wz-symbol", viewBox: "0 0 24 24",
    fill: "none", stroke: "currentColor", "stroke-width": "1.8",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true"});
  for (const d of paths[kind] || paths.info) svg.appendChild(svgEl("path", {d}));
  return svg;
}

function wzHeader(key, title, text) {
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
  // einer BESCHRIFTUNG (`labeled()`), und die ist es, die sagt, worueber
  // es sich lohnt nachzufragen. Eine Zeile kleiner Schrift kostet die Breite
  // nicht, um die es dem Kompakt-Umbau ging — ein Kasten waere das gewesen.
  // **Der Kasten hiess `wz-info-compact info`** — und `.info` ist der runde
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
  return el("div", {class: "wz-info-compact"},
    el("span", {class: "with-info"}, title, info(text, "werkzeug-" + title)));
}

/** Die Zeile „worauf wirkt das hier" — als eigener Baustein, damit sie an jedem
 *  Werkzeug gleich aussieht und keines sie vergessen kann. */
function wzScope(key) {
  const w = WZ_TOOLS.find(x => x.key === key);
  const boxEl = el("div", {class: "wz-scope"});
  if (w && w.scopeKind === "neu") {
    boxEl.classList.add("single");
    boxEl.append(el("span", {class: "wz-scope-badge"}, "Bezug"),
      el("span", {}, "eine neue Sequenz — die offene Sequenz "),
      el("b", {}, W ? W.sequence : "—"),
      el("span", {}, " bleibt unverändert"));
    return boxEl;
  }
  if (w && w.scopeKind === "nichts") {
    boxEl.classList.add("single");
    boxEl.append(el("span", {class: "wz-scope-badge"}, "Bezug"),
      el("span", {}, "nichts — es misst nur den Bildschirm und ändert keine Datei"));
    return boxEl;
  }
  if (!w || w.scopeKind === "inventory") {
    boxEl.append(el("span", {class: "wz-scope-badge"}, "Bezug"),
      el("span", {}, "der gesamte gespeicherte Bestand — alle Sequenzen, Punkte, "
        + "Slots und Scans, nicht nur die offene Sequenz"));
    return boxEl;
  }
  boxEl.classList.add("single");
  boxEl.append(el("span", {class: "wz-scope-badge"}, "Bezug"),
    el("span", {}, "die offene Sequenz "),
    el("b", {}, W ? W.sequence : "—"),
    el("span", {class: "hint"}, W ? " (" + W.file + ")" : ""));
  if (W && W.open)
    boxEl.append(el("span", {class: "kind-warn"}, " — ungespeichert"));
  return boxEl;
}

async function renderTools(fresh) {
  const answer = await ask("tool_data");
  if (!answer || view !== "werkzeuge") return;
  W = answer;
  for (const u of W.scope)
    if (wzScopeState[u.key] === undefined) wzScopeState[u.key] = u.default_value;
  if (fresh) { wzReport = null; wzColorQuestion = null; }
  const memo = rememberFocus();
  wzRenderLeft();
  wzRenderMiddle();
  wzRenderRight();
  restoreFocus(memo);
}

/** Ein Werkzeug-Befehl. Antwort ist ein Ergebnis, KEINE Momentaufnahme —
 *  deshalb `ask()` und danach neu zeichnen, statt `S` zu ersetzen. */
async function callTool(name, data_reload) {
  const answer = await ask(name, data_reload);
  if (!answer) return null;
  if (answer.message)
    setStatus({text: answer.message, kind: answer.ok ? "ok" : "err"});
  await renderTools();
  return answer;
}

function wzRenderLeft() {
  const target = $("wz-left");
  // Hier stand „offene Sequenz <Name>". Der Block hatte einen Grund: die
  // Kopfleiste blendete ihre Sequenz-Bedienelemente in diesem Reiter aus, und
  // damit war auch der Name weg — bei der Klick-Runde genau die Frage, die man
  // sich stellt. Seit die AUSWAHL in jedem Reiter steht, ist der Grund weg und
  // der Name stand dreimal gleichzeitig auf dem Schirm: oben in der Auswahl,
  // hier, und in der Bezugszeile des Werkzeugs. Von den dreien ist die
  // Bezugszeile die genaueste — sie sagt nicht nur WELCHE Sequenz offen ist,
  // sondern ob das Werkzeug sie überhaupt meint.
  const head = el("div", {class: "section"},
    el("span", {class: "heading"}, "WERKZEUGE"));
  const listEl = el("div", {class: "section growing", style: "gap:6px"});
  for (const w of WZ_TOOLS) {
    const button = el("button", {
      class: "wz-nav " + w.key + (wzOpenTool === w.key ? " on" : ""),
      onclick: () => wzOpen(w.key),
      // Der Konsolen-Befehl steht mit — dieselbe Regel wie bei den Config-
      // Schluesseln: wer das Werkzeug hier kennenlernt, erkennt es im
      // Punkte-Menue wieder, und wer es von dort kennt, findet es hier.
    }, el("span", {class: "wz-nav-icon"}, wzIcon(w.key)),
       el("span", {class: "wz-nav-copy"},
         el("span", {class: "wz-nav-title"}, w.name,
           el("span", {class: "wz-command"}, w.command)),
         el("span", {class: "wz-nav-short"}, w.short)),
       el("span", {class: "wz-nav-arrow"}, "›"));
    listEl.appendChild(button);
  }
  listEl.appendChild(wzInfo("Slots exakt reparieren",
    "CTRL+ALT+N → Slots → repair misst die Flächen pixelgenau neu."));
  target.replaceChildren(head, listEl);
  applyHelps(target);
}

/** Ein Werkzeug öffnen — auch als Sprungziel aus dem Editor heraus. */
function wzOpen(key) {
  if (!WZ_TOOLS.some(w => w.key === key)) return;
  wzOpenTool = key;
  if (view !== "werkzeuge") {
    setView("werkzeuge");
    return;
  }
  wzRenderMiddle();
  wzRenderRight();
  wzRenderLeft();
}

function wzRenderMiddle() {
  const target = $("wz-middle");
  const content = wzOpenTool === "recording" ? wzBuildRecording()
    : wzOpenTool === "check" ? wzBuildCheck()
    : wzOpenTool === "points" ? wzBuildPoints()
    : wzOpenTool === "colors" ? wzBuildColors()
    : wzOpenTool === "calibrate" ? wzBuildCalib() : wzBuildReclick();
  target.replaceChildren(...content);
  // Offene i-Texte ueberleben den Neuaufbau nach einer Werkzeug-Aktion.
  applyHelps(target);
}

/* ------------------------------------------------------------------ Prüfen */

function wzBuildCheck() {
  const out = [wzHeader("check", "Setup prüfen",
    "Ein vollständiger Gesundheitscheck für die gespeicherten Sequenzen und Scans.")];
  out.push(wzScope("check"));
  out.push(wzInfo("Was wird geprüft?",
    "Templates, Erkennungsmethoden, Punkt- und Scan-Verweise sowie Stellen "
    + "ausserhalb der angeschlossenen Monitore. Es zählt der zuletzt gespeicherte Stand."));
  out.push(el("div", {class: "wz-action row"},
    el("button", {class: "btn primary wz-main-action", onclick: wzCheck},
      wzIcon("check"), el("span", {}, "Jetzt prüfen"))));

  if (!wzReport) return out;
  if (!wzReport.ok) {
    out.push(el("p", {class: "kind-err"}, wzReport.message || "Prüfung fehlgeschlagen."));
    return out;
  }
  if (!wzReport.findings.length) {
    out.push(el("div", {class: "wz-success"}, wzIcon("ok"),
      el("div", {}, el("b", {}, "Alles in Ordnung"),
        el("span", {}, wzReport.checked.length + " Bereiche ohne Befund geprüft."))));
    return out;
  }
  out.push(el("div", {class: "wz-metrics"},
    wzMetric(String(wzReport.errors || 0), "Fehler", "error"),
    wzMetric(String(wzReport.hints || 0), "Hinweise", "hint"),
    wzMetric(String(wzReport.checked.length), "Bereiche", "neutral")));
  // Fehler zuerst: „laeuft so nicht" schlaegt „ist vermutlich nicht gewollt".
  for (const level of ["error", "hint"]) {
    const match = wzReport.findings.filter(b => b.level === level);
    if (!match.length) continue;
    out.push(el("h3", {style: "margin-top:16px"},
      level === "error" ? "Fehler (" + match.length + ")"
                         : "Hinweise (" + match.length + ")"));
    for (const b of match) out.push(wzFinding(b, level));
  }
  return out;
}

/* ------------------------------------------------------ Punkte verwalten */

function wzBuildPoints() {
  const out = [wzHeader("points", "Punkte verwalten",
    "Klickstellen sind eigenständige Objekte — jede Änderung zieht alle verwendenden Blöcke mit.")];
  out.push(wzScope("points"));
  const points = (W && W.points) || [];
  if (!points.some(p => p.id === wzPointId)) wzPointId = points.length ? points[0].id : null;
  const point = points.find(p => p.id === wzPointId);
  const newName = el("input", {placeholder: "Name des neuen Punkts", value: "Neuer Punkt",
    autocomplete: "off"});
  out.push(el("div", {class: "wz-action gitter2"}, newName,
    el("button", {class: "btn primary", onclick: async () => {
      setStatus({kind: "info", text: "Ins Spiel wechseln, Maus platzieren und ENTER drücken …"});
      const a = await withWait("tool", "tool_point_capture",
                                {name: newName.value});
      if (a && a.ok) wzPointId = a.point_id;
    }}, "＋ Neuen Punkt aufnehmen")));
  if (!point) {
    out.push(el("p", {class: "empty"}, "Noch keine Punkte in dieser Sequenz."));
    return out;
  }
  out.push(selection("Punkt", points.map(p => ({value: p.id,
    text: "#" + p.id + " " + p.name + " (" + p.x + ", " + p.y + ")"})), point.id,
    (v) => { wzPointId = Number(v); wzRenderMiddle(); wzRenderRight(); }));
  const setter = (field, value) => callTool("tool_point_set",
    {point_id: point.id, field: field, value: value});
  out.push(field("Name", point.name, (v) => setter("name", v)));
  out.push(el("div", {class: "gitter2"},
    numberField("X", point.x, (v) => setter("x", v), {step: "1"}),
    numberField("Y", point.y, (v) => setter("y", v), {step: "1"})));
  out.push(color_swatch("Gespeicherte Farbe", point.color ? hexColor(point.color) : "",
    (v) => setter("color", v)));
  out.push(el("div", {class: "row", style: "gap:8px;flex-wrap:wrap"},
    el("button", {class: "btn", onclick: () => callTool("tool_point_show",
      {point_id: point.id})}, "◎ Zeigen & Farbe prüfen"),
    el("button", {class: "btn", onclick: () => withWait("tool",
      "tool_point_capture", {point_id: point.id})}, "✛ Neu messen"),
    // Ausdruecklich ein Boolean, nicht die Anzahl: die Absicht ist „gesperrt,
    // SOLANGE er benutzt wird" — als Zahl gelesen hiess sie das Gegenteil.
    el("button", {class: "btn danger", disabled: point.usages.length > 0,
      title: point.usages.length ? "Erst die aufgeführten Verwendungen entfernen" : "",
      onclick: () => callTool("tool_point_delete", {point_id: point.id})},
      "Löschen")));
  if (point.usages.length) out.push(el("p", {class: "hint"},
    "Löschen ist gesperrt: Dieser Punkt wird noch " + point.usages.length + "× verwendet."));
  return out;
}

/* ------------------------------------------------------ Farben analysieren */

function wzBuildColors() {
  const out = [wzHeader("colors", "Farben analysieren",
    "Liest einen Pixel oder gruppiert die häufigsten Farben eines Bildschirmbereichs.")];
  // Fuenf Werkzeuge trugen ihre Bezugszeile, dieses nicht — obwohl „jedes
  // Werkzeug sagt, WORAUF es wirkt" die Regel des Reiters ist. Gerade hier ist
  // die Antwort die beruhigende: es fasst nichts an.
  out.push(wzScope("colors"));
  out.push(wzInfo("Aufnahme ohne Studio im Bild",
    "Nach dem Klick ins Spiel wechseln. Punkt und Vollbild starten mit ENTER; bei einer Region " +
    "werden obere linke und untere rechte Ecke jeweils mit ENTER bestätigt."));
  const startBtn = async (kind) => {
    setStatus({kind: "info", text: "Ins Spiel wechseln und mit ENTER bestätigen …"});
    wzColorAnalysis = await withWait("tool", "tool_colors", {kind: kind});
    wzRenderMiddle(); wzRenderRight();
  };
  out.push(el("div", {class: "gitter3 wz-action"},
    el("button", {class: "btn primary", onclick: () => startBtn("point")}, "Pixel unter Maus"),
    el("button", {class: "btn", onclick: () => startBtn("region")}, "Bereich analysieren"),
    el("button", {class: "btn", onclick: () => startBtn("fullscreen")}, "Vollbild analysieren")));
  if (wzColorAnalysis && !wzColorAnalysis.ok)
    out.push(el("p", {class: "kind-err"}, wzColorAnalysis.message || "Analyse fehlgeschlagen."));
  if (wzColorAnalysis && wzColorAnalysis.ok) {
    const listEl = el("div", {class: "wz-color-list"});
    for (const f of wzColorAnalysis.colors || []) listEl.appendChild(el("div", {class: "wz-color-row"},
      el("span", {class: "wz-color-sample", style: "background:" + f.hex}),
      el("b", {class: "mono"}, f.hex),
      el("span", {}, "RGB " + f.rgb.join(", ")),
      el("span", {class: "grow hint"}, f.name || ""),
      el("span", {class: "mono"}, f.share_pct + "%")));
    out.push(listEl);
  }
  return out;
}

/* --------------------------------------------------------------- Aufnehmen */

function wzNewRecordingName() {
  const d = new Date(), z = (n) => String(n).padStart(2, "0");
  return "aufnahme_" + z(d.getHours()) + z(d.getMinutes()) + z(d.getSeconds());
}

function wzBuildRecording() {
  if (!wzRecordingName) wzRecordingName = wzNewRecordingName();
  const out = [wzHeader("recording", "Sequenz aufnehmen",
    "Spiele den Ablauf einmal vor — jeder Klick, Tastendruck und Marker wird direkt zu Blöcken.")];
  out.push(wzScope("recording"));

  const form = el("div", {class: "wz-recording-form"});
  const name = el("input", {value: wzRecordingName, autocomplete: "off",
    disabled: wzRecordingStarted});
  name.addEventListener("input", () => { wzRecordingName = name.value; });
  const cycles = el("input", {type: "number", min: "0", step: "1",
    value: String(wzRecordingCycles), disabled: wzRecordingStarted});
  cycles.addEventListener("input", () => { wzRecordingCycles = Math.max(0, Number(cycles.value) || 0); });
  const note = el("textarea", {rows: "3", disabled: wzRecordingStarted,
    placeholder: "optional — wofür ist diese Sequenz?"}, wzRecordingDescription);
  note.addEventListener("input", () => { wzRecordingDescription = note.value; });
  form.append(
    el("label", {class: "field"}, "Name", name),
    el("label", {class: "field"}, "Zyklen · 0 = endlos", cycles),
    el("label", {class: "field wz-recording-note"}, "Notiz", note));
  out.push(form);

  const stamp = el("div", {class: "wz-recording-state" +
    (wzRecordingStarted ? " running" : "")},
    el("span", {class: "wz-rec-point"}),
    el("div", {}, el("b", {}, wzRecordingStarted ? "Aufnahme läuft" : "Bereit zur Aufnahme"),
      el("span", {}, wzRecordingStarted
        ? "Ins Spiel wechseln. Der Stopp-Knopf und CTRL+ALT+J bauen danach die Blöcke."
        : "Starten, ins Spiel wechseln und den gewünschten Ablauf einmal ausführen.")));
  const action = el("button", {
    class: "btn " + (wzRecordingStarted ? "danger" : "primary") + " wz-recording-button",
    onclick: wzRecordingStarted ? wzStopRecording : wzStartRecording,
  }, wzRecordingStarted ? "■ Aufnahme stoppen" : "● Aufnahme starten");
  stamp.appendChild(action);
  out.push(stamp);

  const output = el("div", {class: "wz-recording-output", id: "wz-recording-output"});
  out.push(output);
  wzFillRecordingOutput(output);

  out.push(el("div", {class: "wz-subheader"}, "HOTKEYS WÄHREND DER AUFNAHME"));
  out.push(wzKeyTable((W && W.recording_keys) || []));
  out.push(wzInfo("TUI bleibt verfügbar",
    "CTRL+ALT+J kann die Aufnahme weiterhin ganz ohne Studio starten. Dann werden "
    + "Name, Zyklen und Notiz wie bisher beim Beenden in der Konsole abgefragt."));
  return out;
}

async function wzStartRecording() {
  const name = wzRecordingName.trim();
  if (!name) {
    setStatus({text: "Bitte zuerst einen Namen eingeben.", kind: "err"});
    return;
  }
  const answer = await ask("recording_start", {
    name: name, cycles: wzRecordingCycles, description: wzRecordingDescription});
  if (!answer) return;
  setStatus({text: answer.message || "", kind: answer.ok ? "ok" : "err"});
  if (!answer.ok) return;
  wzRecordingName = answer.name || name;
  wzRecordingStarted = true;
  wzRecordingLive = {active: true, paused: false, count: 0, events: []};
  wzWatchRecording();
  wzRenderMiddle();
  wzRenderRight();
  wzStartRecordingLive();
}

/** Drei feste Zeilen statt eines wachsenden Logs: neuestes Ereignis unten. */
function wzFillRecordingOutput(target) {
  if (!target) return;
  const data_reload = wzRecordingLive || {};
  const events = Array.isArray(data_reload.events) ? data_reload.events.slice(-3) : [];
  const headText = data_reload.paused ? "PAUSIERT" : wzRecordingStarted ? "LIVE" : "LETZTE EREIGNISSE";
  target.replaceChildren(el("div", {class: "wz-output-header"},
    el("span", {}, headText),
    el("span", {class: "wz-output-counter"}, String(data_reload.count || 0) + " Ereignisse")));
  const rows = el("div", {class: "wz-output-rows"});
  if (!events.length) {
    rows.appendChild(el("div", {class: "wz-output-empty"},
      wzRecordingStarted ? "Warte auf das erste Ereignis …" : "Noch nichts aufgenommen."));
  } else {
    events.forEach((e, i) => {
      const color = e.color
        ? el("span", {class: "wz-output-color",
            style: "color:rgb(" + e.color.join(",") + ")"}, "█") : null;
      rows.appendChild(el("div", {class: "wz-output-row" +
          (i === events.length - 1 ? " new" : "")},
        el("span", {class: "wz-output-nr"}, String(e.number || "")),
        el("span", {class: "wz-output-text"}, e.text || "—"),
        el("span", {class: "wz-output-time"}, e.time || ""),
        el("span", {class: "wz-output-color-text"}, color, e.color_text || "")));
    });
  }
  target.appendChild(rows);
}

function wzStartRecordingLive() {
  const number = ++wzRecordingLivePoll;
  const read = async () => {
    if (number !== wzRecordingLivePoll || !wzRecordingStarted) return;
    const status = await ask("recording_status");
    if (status) {
      wzRecordingLive = status;
      wzFillRecordingOutput($("wz-recording-output"));
    }
    setTimeout(read, 300);
  };
  setTimeout(read, 150);
}

async function wzStopRecording() {
  const answer = await ask("recording_stop");
  if (!answer) return;
  setStatus({text: answer.message || "", kind: answer.ok ? "ok" : "err"});
  if (answer.ok) wzWatchRecording(true);
}

/** Findet die vom Hauptprozess gespeicherte Datei und öffnet ihre fertigen Blöcke.
 *
 * **Gefragt wird erst, wenn es etwas zu finden gibt.** `sequence_list()` laedt
 * JEDE Sequenzdatei einzeln (Migration und Punkt-Aufloesung inklusive) — genau
 * deshalb zieht `render()` sie nicht nach. Der langsame Zweig rief sie
 * trotzdem im Sekundentakt, unbegrenzt, ab dem Druck auf „Aufnahme starten":
 * also waehrend der ganzen Aufnahme, und die dauert per Definition lange, weil
 * der Nutzer so lange im Spiel ist. Solange die Aufnahme laeuft, kann die Datei
 * aber gar nicht da sein — `stop_recording()` schreibt sie. Der billige
 * Live-Stand (eine kleine JSON-Datei) sagt, wann das so weit ist.
 *
 * Die Wartezeit selbst bleibt unbegrenzt: eine Stunde aufzunehmen ist erlaubt.
 * Begrenzt wird nur der Fall, in dem die Aufnahme NIE anlaeuft — dann hoert
 * niemand zu, und das ist eine Meldung wert statt eines stillen Dauerlaufs. */
function wzWatchRecording(quick = false) {
  const number = ++wzRecordingPoll;
  let attempts = 0;
  const pruefen = async () => {
    if (number !== wzRecordingPoll || !wzRecordingStarted) return;
    if (!quick) {
      // Laeuft sie noch, gibt es nichts zu holen: billig warten statt fragen.
      if (wzRecordingLive && wzRecordingLive.active) {
        attempts = 0;
        return void setTimeout(pruefen, 1000);
      }
      // Der Zaehler steht nur still, solange die Aufnahme laeuft (oben auf 0
      // gesetzt). Eine Minute Suchen ohne laufende Aufnahme heisst also
      // entweder „nie angelaufen" oder „gestoppt, aber nichts geschrieben" —
      // beides gehoert gesagt statt still weitergedreht.
      if (attempts >= 60) {
        wzRecordingStarted = false;
        ++wzRecordingLivePoll;
        wzRenderMiddle();
        setStatus({text: "Keine laufende Aufnahme — hört der Hauptprozess zu?",
                     kind: "warn"});
        return;
      }
    }
    const listEl = (await ask("sequence_list")) || [];
    if (listEl.some(s => s.name === wzRecordingName)) {
      wzRecordingStarted = false;
      ++wzRecordingLivePoll;
      await call("load", {name: wzRecordingName});
      setView("editor");
      setStatus({text: "Aufnahme gespeichert — die erzeugten Blöcke sind geöffnet.", kind: "ok"});
      return;
    }
    attempts += 1;
    if (quick && attempts >= 12) {
      wzRecordingStarted = false;
      ++wzRecordingLivePoll;
      wzRenderMiddle();
      setStatus({text: "Keine gespeicherte Aufnahme gefunden — wurde etwas aufgezeichnet?", kind: "warn"});
      return;
    }
    setTimeout(pruefen, quick ? 350 : 1000);
  };
  setTimeout(pruefen, quick ? 350 : 1000);
}

function wzMetric(value, label, kind) {
  return el("div", {class: "wz-metric " + kind},
    el("strong", {}, value), el("span", {}, label));
}

function wzFinding(b, level) {
  const boxEl = el("div", {class: "wz-finding " + level});
  boxEl.appendChild(el("div", {class: "wz-finding-icon"}, wzIcon(level)));
  const copy = el("div", {class: "wz-finding-copy"},
    el("div", {class: "wz-area"}, b.area), el("div", {}, b.text));
  if (b.tip) copy.appendChild(el("div", {class: "hint", style: "white-space:normal"}, b.tip));
  boxEl.appendChild(copy);
  return boxEl;
}

function wzBuildChecked() {
  const head = el("div", {class: "section"},
    el("span", {class: "heading"}, "GEPRÜFT"));
  const listEl = el("div", {class: "section growing", style: "gap:4px"});
  if (!wzReport || !wzReport.ok) {
    listEl.appendChild(el("div", {class: "hint", style: "white-space:normal"},
      "Noch nichts geprüft."));
  } else {
    for (const b of wzReport.checked)
      listEl.appendChild(el("div", {class: "wz-checked"}, wzIcon("ok"), el("span", {}, b)));
  }
  return [head, listEl];
}

async function wzCheck() {
  setStatus({text: "Prüfe…", kind: "info"});
  wzReport = await ask("tool_check");
  if (!wzReport) return;
  const n = wzReport.errors || 0, h = wzReport.hints || 0;
  setStatus({
    text: !wzReport.ok ? (wzReport.message || "Prüfung fehlgeschlagen.")
        : (n || h) ? n + " Fehler, " + h + " Hinweis(e)."
        : "Alles in Ordnung.",
    kind: !wzReport.ok || n ? "err" : h ? "warn" : "ok",
  });
  wzRenderMiddle();
  // **Auch rechts.** Hier stand nur `wzRenderMiddle()`, und damit blieb in der
  // rechten Spalte „Noch nichts geprüft." stehen, während in der Mitte längst
  // der Bericht lag. Ausgerechnet dort: die Spalte listet, WAS geprüft wurde,
  // und ohne sie ist „Alles in Ordnung" eine Behauptung — genau die Begründung,
  // mit der sie gebaut wurde. Jeder andere Werkzeug-Befehl zeichnet beides
  // (`callTool` über `renderTools`); dieser eine ging seinen eigenen
  // Weg, weil er `ask()` direkt ruft.
  wzRenderRight();
}

/* ------------------------------------------------------------- Kalibrieren */

function wzBuildCalib() {
  const K = (W && W.calibration) || {};
  const out = [wzHeader("calibrate", "Koordinaten kalibrieren",
    "Einen bekannten Punkt neu messen und alle gespeicherten Stellen präzise mitziehen.")];
  out.push(wzScope("calibrate"));
  out.push(wzInfo("Wann brauche ich das?",
    "Wenn Windows Monitore verschoben oder die Auflösung geändert hat. Der erste "
    + "Referenzpunkt bestimmt die Verschiebung, ein zweiter optional die Skalierung."));

  if (!W || !W.points.length) {
    out.push(el("p", {class: "kind-err"}, "Keine Punkte vorhanden — es gibt nichts zu kalibrieren."));
    return out;
  }

  out.push(wzRefRow(1, K.ref1));
  // Der zweite Punkt erst anbieten, wenn der erste steht: ohne Verschiebung
  // gibt es keine Skalierung, und zwei leere Felder nebeneinander sehen aus,
  // als muesste man beide ausfuellen.
  if (K.ref1) {
    out.push(wzInfo("Zweiter Referenzpunkt",
      "Nur wenn sich auch die Auflösung geändert hat: Dann einen zweiten Punkt "
      + "möglichst weit vom ersten entfernt anfahren."));
    out.push(wzRefRow(2, K.ref2));
  }

  if (K.ref1) {
    out.push(el("div", {class: "wz-subheader"}, "BERECHNETER TRANSFORM"));
    const v = K.offset || {x: 0, y: 0};
    const values = el("div", {class: "wz-metrics"},
      wzMetric(wzSign(v.x), "X-Versatz", "neutral"),
      wzMetric(wzSign(v.y), "Y-Versatz", "neutral"));
    if (K.scaling && (K.scaling.x !== 1 || K.scaling.y !== 1))
      values.appendChild(wzMetric(K.scaling.x + "×" + K.scaling.y,
        "Skalierung X/Y", "hint"));
    out.push(values);
    out.push(wzOffsetFields(v));
    if (K.identity)
      out.push(el("p", {class: "kind-warn"},
        "Der Transform ändert nichts — der Punkt sitzt schon richtig."));
    out.push(wzScopeBox());
    const strip = el("div", {style: "display:flex;gap:8px;margin-top:14px"});
    strip.appendChild(el("button", {
      class: "btn primary", disabled: !!K.identity,
      onclick: () => callTool("calib_apply", {...wzScopeState}),
    }, "Umrechnen und speichern"));
    strip.appendChild(el("button", {
      class: "btn", onclick: () => callTool("calib_cancel"),
    }, "Verwerfen"));
    out.push(strip);
    out.push(wzInfo("Sicherung und laufende Sequenz",
      "Vorher entsteht ein vollständiges Export-ZIP als Sicherung. Läuft eine "
      + "Sequenz, wird nicht umgerechnet — sie klickt sonst mitten im Umbau."));
  }
  return out;
}

function wzSign(n) { return (n > 0 ? "+" : "") + n; }

function wzColor(rgb) {
  return el("span", {class: "wz-color",
                     style: "background:rgb(" + rgb.join(",") + ")"});
}

/** Die Rueckfrage bei abweichender Farbe: beide Farben nebeneinander, dann
 *  entscheiden. Gesperrt wird nichts — manchmal hat sich das Spiel geaendert und
 *  die neue Farbe ist die richtige. Es soll nur nicht aus Versehen gehen. */
function wzBuildColorQuestion() {
  const f = wzColorQuestion;
  const boxEl = el("div", {class: "wz-color-question"});
  boxEl.appendChild(el("div", {class: "kind-warn"}, f.message));
  const series = el("div", {class: "wz-color-series"});
  series.append(el("span", {class: "hint"}, "saved"), wzColor(f.expected),
               el("span", {class: "hint"}, "dort gemessen"), wzColor(f.measured),
               el("span", {class: "hint"},
                  "(" + f.position[0] + ", " + f.position[1] + ")"));
  boxEl.appendChild(series);
  const strip = el("div", {style: "display:flex;gap:8px"});
  strip.appendChild(el("button", {
    class: "btn", onclick: async () => {
      const n = f.number, id = f.point_id;
      wzColorQuestion = null;
      // Auch „Trotzdem setzen" misst die Stelle NEU — calib_reference wartet
      // in jedem Fall auf ENTER. Ohne den Hinweis sieht der Knopf aus, als
      // habe er nichts getan.
      await withWait("tool", "calib_reference",
                      {number: n, point_id: id, confirmed: true});
    },
  }, "Trotzdem setzen"));
  strip.appendChild(el("button", {
    class: "btn primary", onclick: () => {
      wzColorQuestion = null;
      setStatus({text: "Verworfen — nichts gesetzt.", kind: "info"});
      renderTools();
    },
  }, "Nochmal anfahren"));
  boxEl.appendChild(strip);
  boxEl.appendChild(el("div", {class: "hint", style: "white-space:normal"},
    "\u201eTrotzdem setzen\u201c ist richtig, wenn sich das Spiel geändert hat. Sonst "
    + "erst nachsehen: ein danebenliegender Referenzpunkt verschiebt nicht sich "
    + "selbst, sondern jede gespeicherte Stelle."));
  return boxEl;
}

/** Der Punkt mit dem groessten Abstand zum ersten Referenzpunkt.
 *
 * Zwei nah beieinander liegende Punkte machen die Skalierung unbrauchbar: der
 * Messfehler der Maus (ein paar Pixel) verteilt sich dann auf eine kurze
 * Strecke und wird zum Faktor hochgerechnet. */
function wzFarthestPoint(ref1) {
  let best = W.points[0], wide = -1;
  for (const p of W.points) {
    if (ref1 && p.id === ref1.point_id) continue;
    const d = Math.hypot(p.x - (ref1 ? ref1.alt[0] : 0), p.y - (ref1 ? ref1.alt[1] : 0));
    if (d > wide) { wide = d; best = p; }
  }
  return best.id;
}

/** Eine Referenzpunkt-Zeile: welchen Punkt, und der Knopf zum Anfahren. */
function wzRefRow(number, placed) {
  const boxEl = el("div", {class: "wz-ref"});
  boxEl.appendChild(el("div", {class: "wz-area"},
    number === 1 ? "1. Referenzpunkt (Verschiebung)"
                 : "2. Referenzpunkt (Skalierung, optional)"));
  const choice = el("select");
  for (const p of W.points)
    choice.appendChild(el("option", {value: String(p.id)},
      "#" + p.id + " " + p.name + " (" + p.x + ", " + p.y + ")"));
  if (placed) choice.value = String(placed.point_id);
  // Der zweite Punkt soll WEIT weg vom ersten liegen — genau das steht als
  // Hinweis darueber. Der erste Eintrag der Liste ist aber der erste Punkt
  // selbst, und den lehnt die Bruecke ab: ein Vorschlag, der garantiert eine
  // Fehlermeldung ergibt, ist schlimmer als gar keiner.
  else if (number === 2) choice.value = String(wzFarthestPoint(W.calibration.ref1));
  boxEl.appendChild(choice);
  boxEl.appendChild(el("button", {
    class: "btn",
    onclick: async () => {
      setStatus({text: "Maus auf die Stelle, dann ENTER (ESC bricht ab)…", kind: "info"});
      const answer = await withWait("ask", "calib_reference",
        {number, point_id: Number(choice.value)});
      // Die Farbe passt nicht: nachfragen statt setzen. Ein Referenzpunkt, der
      // danebenliegt, verschiebt nicht sich selbst, sondern ALLES.
      if (answer && answer.confirm) { wzColorQuestion = {...answer, number}; }
      else if (answer && answer.message)
        setStatus({text: answer.message, kind: answer.ok ? "ok" : "err"});
      await renderTools();
    },
  }, placed ? "Neu anfahren" : "Stelle anfahren"));
  if (wzColorQuestion && wzColorQuestion.number === number)
    boxEl.appendChild(wzBuildColorQuestion());
  if (placed)
    boxEl.appendChild(el("div", {class: "hint"},
      "(" + placed.alt[0] + ", " + placed.alt[1] + ") → ("
      + placed.neu[0] + ", " + placed.neu[1] + ")"));
  return boxEl;
}

/** Versatz von Hand nachziehen — mit der Maus trifft man den Pixel nicht genau. */
function wzOffsetFields(v) {
  const boxEl = el("div", {class: "wz-ref"});
  boxEl.appendChild(el("div", {class: "wz-area"}, "Versatz von Hand"));
  const fields = {};
  for (const axis of ["x", "y"]) {
    const field = el("input", {type: "number", step: "1", value: String(v[axis]),
                              style: "width:90px"});
    fields[axis] = field;
    boxEl.append(el("span", {}, axis.toUpperCase()), field);
  }
  boxEl.appendChild(el("button", {
    class: "btn", onclick: () => callTool("calib_offset",
      {x: fields.x.value, y: fields.y.value}),
  }, "Übernehmen"));
  boxEl.appendChild(wzInfo("Versatz von Hand",
    "Weisst du, dass eine Achse stimmt, ist eine getippte 0 genauer als jede Messung."));
  return boxEl;
}

function wzScopeBox() {
  const boxEl = el("div", {class: "wz-ref", style: "flex-direction:column;align-items:stretch"});
  boxEl.appendChild(el("div", {class: "wz-area"}, "Was mitgerechnet wird"));
  boxEl.appendChild(wzInfo("Punkte",
    "Punkte werden immer mitgerechnet — daran hängt alles andere."));
  for (const u of W.scope) {
    const row = el("label", {class: "share-row on"});
    const box = el("input", {type: "checkbox"});
    box.checked = !!wzScopeState[u.key];
    box.addEventListener("change", () => { wzScopeState[u.key] = box.checked; });
    row.append(box, el("span", {}, u.text));
    boxEl.appendChild(row);
  }
  boxEl.appendChild(wzInfo("Warum Slots standardmässig aus sind",
    "Slots stehen getrennt und sind aus: nach einem repair dürfen sie kein "
    + "zweites Mal wandern."));
  return boxEl;
}

/* --------------------------------------------------------- Punkte nachklicken */

/* Die vier Griffe während der Runde — dieselbe Liste wie `TASTEN` in
 * `editors/nachklick.py`. Sie steht hier als Tabelle und nicht als Absatz, weil
 * man sie MITTEN im Klicken nachschlägt: Fliesstext zwingt zum Lesen von vorn,
 * und dann liest ihn niemand. */
const WZ_KEYS = [
  ["CTRL+ALT+K", "überspringen", "Punkt bleibt, wo er ist"],
  ["CTRL+ALT+U", "zurück", "einen Punkt zurück, noch mal"],
  ["CTRL+ALT+H", "pausieren", "navigieren, ohne einen Punkt zu verbrauchen"],
  ["CTRL+ALT+J", "übernehmen", "fertig — JETZT werden die Punkte geschrieben"],
];

/* Was die Runde tut, in der Reihenfolge, in der es passiert. Drei Schritte statt
 * dreier Absätze: der Ablauf IST die Erklärung. */
const WZ_STEPS = [
  ["Starten", "Der Zeiger springt auf den ersten Punkt der Sequenz."],
  ["Klicken", "Stimmt die Stelle noch? Dann einfach klicken. Sonst hinfahren und "
            + "dort klicken — der Klick geht ans Spiel, die Oberfläche öffnet "
            + "sich wie im Lauf, und der nächste Punkt liegt vor dir."],
  ["Übernehmen", "Erst damit werden die Punkte geschrieben. Vorher ändert sich "
               + "nichts — an keiner Datei und in keinem Speicher."],
];

function wzKeyTable(keys = WZ_KEYS) {
  const bodyEl = el("tbody");
  for (const [combo, what, why] of keys)
    bodyEl.appendChild(el("tr", {},
      el("td", {}, el("span", {class: "wz-key"}, combo)),
      el("td", {class: "wz-what"}, what),
      el("td", {class: "wz-why"}, why)));
  return el("table", {class: "wz-keys"}, bodyEl);
}

/* Was ein erledigter Punkt geworden ist. Vier Ausgaenge, weil die Runde vier
 * kennt — und „bestaetigt" von „uebersprungen" zu unterscheiden ist der ganze
 * Grund fuer `reclick_history`: beide aendern nichts, aber nur einer heisst
 * „ich habe hingesehen". */
const WZ_RECLICK_KIND = {
  fits: ["✓", "rc-fits", "bestätigt — bleibt, wo er ist"],
  placed: ["→", "rc-set", "neu gesetzt"],
  skipped: ["↷", "rc-skip", "übersprungen"],
  missing: ["✕", "rc-missing", "Punkt gibt es nicht mehr"],
};

/** Der Live-Stand der Runde: wo sie steht, was dran ist, was war. */
function wzFillReclickOutput(target) {
  if (!target) return;
  const d = wzReclickLive || {};
  const total = d.total || 0;
  const done = Math.min(d.index || 0, total);
  const running = !!d.active && !d.orphaned;

  // Der Kopf beantwortet die erste Frage („laeuft das ueberhaupt noch?"), und
  // ein verwaister Stand sagt es, statt eine tote Runde als lebend zu zeigen.
  const headText = d.orphaned ? "KEIN HAUPTPROZESS"
    : d.paused ? "PAUSIERT" : running ? "LÄUFT" : total ? "BEENDET" : "NICHT GESTARTET";
  target.replaceChildren(el("div", {class: "wz-output-header"},
    el("span", {}, headText),
    el("span", {class: "wz-output-counter"},
      total ? done + " von " + total + " Punkt(en)" : "—")));

  if (!total) {
    target.appendChild(el("div", {class: "wz-output-rows"},
      el("div", {class: "wz-output-empty"},
        "Noch keine Runde gelaufen. „Runde starten“ setzt den Zeiger auf den "
        + "ersten Punkt.")));
    return;
  }

  // Ein Balken statt einer zweiten Zahl: wie weit die Runde ist, sieht man
  // beim Klicken aus dem Augenwinkel — eine Zahl muss man lesen.
  target.appendChild(el("div", {class: "rc-bar"},
    el("div", {class: "rc-bar-fill",
               style: "width:" + Math.round(done / total * 100) + "%"})));

  // Der aktuelle Punkt ist die Antwort auf „was macht das Programm gerade".
  const p = d.point || {};
  if (running && p.id !== undefined) {
    target.appendChild(el("div", {class: "rc-now"},
      el("span", {class: "rc-now-badge"}, "jetzt"),
      el("span", {class: "num"}, "#" + p.id),
      el("span", {class: "rc-now-name"}, p.name || ""),
      el("span", {class: "rc-now-pos"}, "(" + p.x + ", " + p.y + ")"),
      p.color ? el("span", {class: "wz-output-color",
                            style: "color:rgb(" + p.color.join(",") + ")"}, "█") : null));
    target.appendChild(el("div", {class: "hint rc-hint"}, d.paused
      ? "Pausiert — Klicks setzen keinen Punkt. CTRL+ALT+H macht weiter."
      : "Der Zeiger steht schon dort. Stimmt die Stelle — klicken. Sonst "
        + "hinfahren und dort klicken."));
  } else if (!running && total) {
    target.appendChild(el("div", {class: "hint rc-hint"},
      (d.changed || 0) + " Stelle(n) geändert. Was davon geschrieben wurde, "
      + "hängt daran, ob übernommen oder verworfen wurde."));
  }

  // Der Verlauf laeuft rueckwaerts: das Letzte ist das, was man sucht.
  const history = Array.isArray(d.history) ? d.history.slice(-6).reverse() : [];
  const rows = el("div", {class: "wz-output-rows"});
  if (!history.length) {
    rows.appendChild(el("div", {class: "wz-output-empty"},
      "Noch kein Punkt erledigt."));
  } else {
    for (const v of history) {
      const [glyph, cls, what] = WZ_RECLICK_KIND[v.kind] || ["·", "", v.kind];
      rows.appendChild(el("div", {class: "rc-row"},
        el("span", {class: "rc-kind " + cls, title: what}, glyph),
        el("span", {class: "num"}, "#" + v.id),
        el("span", {class: "rc-name"}, v.name || ""),
        el("span", {class: "rc-target"}, v.alt && v.neu
          ? "(" + v.alt[0] + ", " + v.alt[1] + ") → (" + v.neu[0] + ", " + v.neu[1] + ")"
          : what)));
    }
  }
  target.appendChild(rows);
  if (d.others)
    target.appendChild(el("div", {class: "hint rc-hint"},
      d.others + " Stelle(n) erreicht die Runde nicht (beobachtete Pixel, "
      + "ELSE, Rad) — dafür bleibt walk im Punkte-Menü."));
}

/* Gepollt wird, solange der Reiter offen ist — nicht nur nach dem eigenen
 * Startknopf. Die Runde kann aus dem Punkte-Menue gestartet worden sein, und
 * dann ist dieses Fenster trotzdem der bequemere Platz, um ihr zuzusehen.
 * Nach dem Ende laeuft der Poll aus (`quiet`), damit ein offener Reiter nicht
 * dauerhaft alle 400 ms eine Datei liest. */
function wzStartReclickLive() {
  const number = ++wzReclickPoll;
  let quiet = 0;
  const read = async () => {
    if (number !== wzReclickPoll || wzOpenTool !== "reclick") return;
    const stamp = await ask("reclick_status");
    if (number !== wzReclickPoll || wzOpenTool !== "reclick") return;
    if (stamp) {
      const wasRunning = wzReclickLive.active;
      wzReclickLive = stamp;
      wzFillReclickOutput($("wz-reclick-output"));
      // Endet die Runde, sagt es die Statuszeile — sonst merkt man es nur,
      // wenn man gerade hinsieht.
      if (wasRunning && !stamp.active)
        setStatus({text: "Klick-Runde beendet — " + (stamp.changed || 0)
                     + " Stelle(n) geändert.", kind: "ok"});
      quiet = stamp.active ? 0 : quiet + 1;
    } else {
      quiet += 1;
    }
    if (quiet > 12) return;
    setTimeout(read, wzReclickLive.active ? 400 : 1000);
  };
  setTimeout(read, 100);
}

function wzBuildReclick() {
  const out = [wzHeader("reclick", "Punkte nachklicken",
    "Eine geführte Kontrollrunde durch alle Klickstellen der geöffneten Sequenz.")];
  out.push(wzScope("reclick"));

  const steps = el("div", {class: "wz-steps"});
  WZ_STEPS.forEach(([title, text], i) => {
    steps.append(el("div", {class: "wz-number"}, String(i + 1)),
      el("div", {class: "wz-step-text"}, el("b", {}, title + ": "), text));
  });
  out.push(steps);

  // Die eine Regel, an der alles haengt — als Kasten, nicht als Satz im Absatz.
  out.push(el("div", {class: "wz-rule"},
    el("span", {}, "⚠"),
    el("span", {}, el("b", {}, "Nichts wird geschrieben, bis du übernimmst. "),
      "Fenster zu, Programm aus oder „Verwerfen“ = die Runde ist weg und "
      + "sequence.json bleibt, wie sie war. Geändert wird ohnehin nur die "
      + "Stelle: Wartezeiten, Bedingungen, ELSE und Scans bleiben unangetastet.")));

  const strip = el("div", {style: "display:flex;gap:8px;margin-top:4px"});
  strip.appendChild(el("button", {
    class: "btn primary",
    // Wie beim Start einer Sequenz: der Befehl geht in den Briefkasten, und ob
    // ihn jemand abholt, sieht man erst daran, dass er verschwindet.
    onclick: async () => { await callTool("reclick_start");
                           mailboxFollowUp(); },
    title: "Startet die Runde im Hauptprozess — geklickt wird danach im Spiel",
  }, "Runde starten"));
  // Zwei Ausgaenge, weil es zwei Absichten gibt. Ein einzelner „Beenden"-Knopf
  // muesste sich fuer eine entscheiden und laege in der Haelfte der Faelle
  // falsch. Ob gerade eine Runde laeuft, weiss dieses Fenster nicht (der Zustand
  // liegt drueben) - die Knoepfe stehen deshalb immer da, und der Hauptprozess
  // sagt, was er vorgefunden hat.
  strip.appendChild(el("button", {
    class: "btn", onclick: () => callTool("reclick_end"),
    title: "Schreibt die gesetzten Stellen nach sequence.json (= CTRL+ALT+J)",
  }, "Übernehmen"));
  strip.appendChild(el("button", {
    class: "btn", onclick: () => callTool("reclick_end", {discard: true}),
    title: "Beendet die Runde, ohne etwas zu schreiben",
  }, "Verwerfen"));
  out.push(strip);

  // Der Live-Stand steht ZWISCHEN Knoepfen und Tastentabelle: was das
  // Programm gerade macht, sucht man dort, wo man es gerade gestartet hat.
  const output = el("div", {class: "wz-output", id: "wz-reclick-output"});
  out.push(output);
  wzFillReclickOutput(output);

  wzStartReclickLive();
  out.push(wzKeyTable());
  out.push(wzInfo("Bedienung im Spiel",
    "Die Runde läuft wegen des systemweiten Maus-Hooks im Hauptprozess. Die "
    + "Tasten wirken überall — auch mit dem Spiel im Vordergrund. Gezählt "
    + "wird nur, was im Spielfenster geklickt wird (window_focus_title); ein "
    + "Klick woanders verbraucht keinen Punkt."));
  return out;
}

/* ------------------------------------------------------------------- rechts */

function wzRenderRight() {
  const target = $("wz-right");
  // Beim Pruefen steht hier, WAS geprueft wurde. „Alles in Ordnung" ist ohne
  // diese Liste eine Behauptung: man weiss nicht, ob der Bereich sauber war
  // oder gar nicht angesehen wurde.
  if (wzOpenTool === "check") return target.replaceChildren(...wzBuildChecked());
  if (wzOpenTool === "recording")
    return target.replaceChildren(el("div", {class: "section"},
      el("span", {class: "heading"}, "SO ENTSTEHEN DIE BLÖCKE"),
      el("div", {class: "wz-recording-flow"},
        el("b", {}, "1 · Starten"), el("span", {}, "Das Studio schickt Name und Einstellungen mit."),
        el("b", {}, "2 · Spielen"), el("span", {}, "Klicks, Tasten, Rad und Marker werden gesammelt."),
        el("b", {}, "3 · Stoppen"), el("span", {}, "Die Sequenz wird gespeichert und automatisch im Editor geöffnet."))));
  if (wzOpenTool === "points") {
    const point = W && W.points.find(p => p.id === wzPointId);
    const head = el("div", {class: "section"},
      el("span", {class: "heading"}, "VERWENDUNGEN"),
      el("span", {class: "hint"}, point ? "Punkt #" + point.id : "kein Punkt gewählt"));
    const listEl = el("div", {class: "section growing", style: "gap:5px"});
    if (!point || !point.usages.length)
      listEl.appendChild(el("p", {class: "hint"}, "Dieser Punkt wird nirgends verwendet und kann sicher gelöscht werden."));
    else for (const v of point.usages)
      listEl.appendChild(el("div", {class: "wz-checked"}, wzIcon("points"), el("span", {}, v)));
    return target.replaceChildren(head, listEl);
  }
  if (wzOpenTool === "colors")
    return target.replaceChildren(el("div", {class: "section"},
      el("span", {class: "heading"}, "MESSUNG"),
      el("p", {class: "hint"}, wzColorAnalysis && wzColorAnalysis.ok
        ? (wzColorAnalysis.message || "Analyse abgeschlossen.")
        : "Noch keine Analyse. Die Farbfelder erscheinen nach der Aufnahme in der Mitte.")));
  if (wzOpenTool === "reclick")
    // Als einziges Werkzeug stand hier keine Ueberschrift — die anderen fuenf
    // haben GEPRUEFT, SO ENTSTEHEN DIE BLOECKE, VERWENDUNGEN, MESSUNG und
    // VORSCHAU. Uebrig blieb ein Hinweis ohne Dach in einer sonst leeren
    // Spalte, und der sah aus, als sei die Spalte kaputt.
    return target.replaceChildren(el("div", {class: "section"},
      el("span", {class: "heading"}, "GRENZEN DER RUNDE"),
      wzInfo("Was die Runde nicht erreicht",
        "Beobachtete Pixel, Nachprüfungen, ELSE-Klicks und Rad-Schritte kommen "
        + "in einem normalen Durchlauf gar nicht vor. Dafür bleibt walk im "
        + "Punkte-Menü. Welche das sind, sagt die Runde beim Start in der Konsole.")));
  if (!W || !W.calibration.ref1)
    return target.replaceChildren(el("div", {class: "section"},
      el("span", {class: "heading"}, "VORSCHAU"),
      el("div", {class: "hint", style: "white-space:normal"},
        "Sobald der erste Referenzpunkt steht, steht hier, was sich ändern würde.")));

  const rows = W.calibration.preview || [];
  const head = el("div", {class: "section"},
    el("span", {class: "heading"}, "VORSCHAU"),
    el("div", {class: "hint"}, rows.length + " Stelle(n), Auszug"));
  const listEl = el("div", {class: "section growing", style: "gap:4px"});
  for (const z of rows) {
    listEl.appendChild(el("div", {class: "wz-preview"},
      el("div", {}, z.what),
      el("div", {class: "hint"},
        "(" + z.before.join(", ") + ") → (" + z.after.join(", ") + ")")));
  }
  if (!rows.length)
    listEl.appendChild(el("div", {class: "hint"}, "Nichts, was sich ändern würde."));
  target.replaceChildren(head, listEl);
}

/* Der Reiter bearbeitet `config.json` — eine ANDERE Datei als der Editor, also
 * liegt sein Zustand neben `S`: `C` ist die Antwort von `config_read()`,
 * `cfgChanged` sammelt, was noch nicht geschrieben ist.
 *
 * Gespeichert wird auf Knopfdruck: die Werte greifen in einen laufenden Lauf,
 * und eine halb getippte Zahl darf nicht schon gelten. */
let C = null;
let cfgChanged = {};
let cfgSection = 0;
let cfgSearch = "";
let cfgCorrections = [];

async function renderSettings(fresh) {
  if (fresh || !C) {
    const answer = await ask("config_read");
    // Zwischen Frage und Antwort kann umgeschaltet worden sein.
    if (!answer || view !== "einstellungen") return;
    C = answer;
    // Was inzwischen von aussen genauso gesetzt wurde, ist keine Aenderung mehr.
    for (const k of Object.keys(cfgChanged))
      if (cfgEqual(cfgChanged[k], C.values[k])) delete cfgChanged[k];
  }
  const memo = rememberFocus();
  renderCfgList();
  renderCfgFields();
  renderCfgRight();
  restoreFocus(memo);
}

/** Gleicher Wert? Arrays über ihre Darstellung, alles andere strikt. */
function cfgEqual(a, b) {
  if (Array.isArray(a) || Array.isArray(b)) return JSON.stringify(a) === JSON.stringify(b);
  return a === b;
}

function cfgValue(key) {
  return Object.prototype.hasOwnProperty.call(cfgChanged, key)
    ? cfgChanged[key] : C.values[key];
}

function cfgSet(key, value) {
  if (cfgEqual(value, C.values[key])) delete cfgChanged[key];
  else cfgChanged[key] = value;
  // Eine neue Eingabe macht die Korrekturmeldung von vorhin gegenstandslos.
  cfgCorrections = [];
  renderSettings();
}

/** Wirkt das Feld überhaupt — oder hängt es an einem Schalter, der aus ist? */
function cfgActive(key) {
  const m = C.meta[key] || {};
  if (m.dep && !cfgValue(m.dep)) return false;
  if (m.dep_not && cfgValue(m.dep_not)) return false;
  if (m.dep_min && !(Number(cfgValue(m.dep_min)) > 0)) return false;
  return true;
}

function cfgWhy(m) {
  const otherKind = m.dep || m.dep_not || m.dep_min;
  const name = (C.meta[otherKind] && C.meta[otherKind].label) || otherKind;
  if (m.dep) return "Wirkt nur, wenn „" + name + "“ an ist.";
  if (m.dep_not) return "Wirkt nur, wenn „" + name + "“ aus ist.";
  return "Wirkt nur, wenn „" + name + "“ grösser als 0 ist.";
}

function cfgMatches(key) {
  if (!cfgSearch) return true;
  const m = C.meta[key] || {};
  return (key + " " + (m.label || "") + " " + (m.help || ""))
    .toLowerCase().includes(cfgSearch);
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
    const t = m.options.find((o) => cfgEqual(o.value, value));
    if (t) return t.text;
  }
  if (value === 0 && m.empty) return "0 — " + m.empty;
  return String(value) + (m.unit ? " " + m.unit : "");
}

function renderCfgList() {
  const target = $("cfg-list");
  target.replaceChildren();
  C.sections.forEach((a, i) => {
    const open = a.keys.filter((k) => k in cfgChanged).length;
    const match = cfgSearch ? a.keys.filter(cfgMatches).length : 0;
    target.appendChild(el("button", {
      class: "cfg-nav" + (!cfgSearch && i === cfgSection ? " on" : ""),
      onclick: () => { cfgSearch = ""; $("cfg-search").value = ""; cfgSection = i;
                       renderSettings(); },
    },
      el("span", {class: "grow"}, a.title),
      cfgSearch ? el("span", {class: "small mono"}, match ? match + "×" : "") : null,
      open ? el("span", {class: "num"}, open) : null));
  });
}

function renderCfgFields() {
  const target = $("cfg-fields");
  target.replaceChildren();
  if (C.error) {
    target.appendChild(el("p", {class: "empty", style: "color:var(--err)"}, C.error));
    return;
  }
  // Bei einer Suche werden ALLE Abschnitte mit Treffern gezeigt, nicht nur der
  // gewaehlte: wer sucht, weiss ja gerade nicht, wo der Wert steht.
  const groups = cfgSearch
    ? C.sections.filter((a) => a.keys.some(cfgMatches))
    : [C.sections[cfgSection]].filter(Boolean);
  if (!groups.length) {
    target.appendChild(el("p", {class: "empty"}, "Kein Feld passt zu „" + cfgSearch + "“."));
    return;
  }
  for (const a of groups) {
    target.appendChild(el("div", {class: "cfg-group"}, a.title));
    for (const key of a.keys) if (cfgMatches(key)) target.appendChild(cfgRow(key));
  }
}

function cfgRow(key) {
  const m = C.meta[key] || {label: key, kind: "text"};
  const active = cfgActive(key);
  const left = el("div", {},
    el("div", {class: "cfg-name"}, m.label),
    el("div", {class: "cfg-key"}, key),
    m.help ? el("p", {class: "hint", style: "margin-top:5px"}, m.help) : null,
    active ? null : el("p", {class: "hint", style: "margin-top:5px;color:var(--accent)"},
                      cfgWhy(m)));
  const right = el("div", {class: "cfg-rights"},
    cfgControl(key, m), cfgEmpty(key, m), cfgDefault(key, m),
    cfgAction(key, m));
  return el("div", {class: "cfg-row" + (key in cfgChanged ? " changed" : "") +
                           (active ? "" : " blass")}, left, right);
}

/** Der Knopf UNTER einem Feld, wenn die Meta-Tabelle einen anmeldet.
 *
 * **Es gibt genau einen, und der Grund steht in `config_meta.py`:** den
 * Katalog konnte bis hierhin nur `python tools/katalog.py` anlegen — also
 * ausgerechnet die Datei, ohne die das LLM frei raet und die Kategorie leer
 * bleibt, liess sich im Fenster nicht beschaffen. Generisch statt als
 * Sonderfall, damit der naechste Fall keinen zweiten Bedienweg erfindet.
 */
function cfgAction(key, m) {
  const stamp = (C.states || {})[key];
  if (!m.action && !stamp) return null;
  return el("div", {class: "column", style: "gap:4px;margin-top:6px"},
    m.action ? el("button", {class: "btn quiet wide",
      onclick: () => cfgCallAction(key, m)}, m.action.text) : null,
    // **Der Pfad sagt nicht, ob die Datei da ist und wie alt sie ist.** Bei
    // einer Liste, die man holt, ist genau das die Frage — und ohne Antwort
    // holt man sie entweder nie wieder oder jedes Mal.
    stamp ? el("p", {class: "hint", style: "margin:0"}, stamp) : null);
}

async function cfgCallAction(key, m) {
  // Ein Netzabruf dauert, und der Reiter zeichnet sich danach neu: ohne den
  // Kasten saehe das Fenster in der Zwischenzeit tot aus.
  const answer = await withWork("ask", m.action.command, null,
    m.action.text, "Das kann ein paar Sekunden dauern.");
  if (!answer) return;
  // Geklappt, aber mit Vorbehalt (ein Konstrukt in der Antwort, das das
  // Werkzeug nicht kannte): dann sagt die Bruecke die Art selbst.
  setStatus({text: answer.message || "Fertig.",
               kind: answer.kind || (answer.ok ? "ok" : "err")});
  // Der Wert im Feld kann sich dabei geaendert haben (der Pfad wird
  // eingetragen) — frisch lesen statt den alten Stand stehen zu lassen.
  if (answer.ok) renderSettings(true);
}

function cfgControl(key, m) {
  const value = cfgValue(key);
  const setter = (v) => cfgSet(key, v);
  if (m.kind === "bool") return toggle(value ? "an" : "aus", value, setter);
  if (m.kind === "enum") return cfgTiles(key, m, value);
  if (m.kind === "xy") return cfgPosition(key, m, value);
  if (m.kind === "area") {
    const field = el("textarea", {});
    field.value = value === null || value === undefined ? "" : String(value);
    field.addEventListener("change", () => setter(field.value.trim() || null));
    return field;
  }
  if (m.kind === "text") {
    const field = el("input", {autocomplete: "off",
                              value: value === null || value === undefined ? "" : String(value)});
    field.addEventListener("change", () => {
      const raw = field.value.trim();
      setter(raw === "" && (C.optional || []).includes(key) ? null : raw);
    });
    field.addEventListener("keydown", (e) => { if (e.key === "Enter") field.blur(); });
    return field;
  }
  return cfgNumber(key, m, value);
}

function cfgNumber(key, m, value) {
  const optional = (C.optional || []).includes(key);
  const field = el("input", {type: "number", step: m.kind === "int" ? "1" : "any",
                            value: value === null || value === undefined ? "" : value});
  if (m.kind === "ratio") { field.setAttribute("min", "0"); field.setAttribute("max", "1"); }
  field.addEventListener("change", () => {
    const raw = field.value.trim();
    // Leer heisst `null`, wo die Dataclass das erlaubt, und sonst 0. Der
    // Unterschied ist nicht kosmetisch: click_max_total = 0 waere „nach null
    // Klicks stoppen", null dagegen „unbegrenzt".
    if (raw === "") return cfgSet(key, optional ? null : 0);
    let z = Number(raw);
    // Fehleingabe wiederholen statt uebernehmen — dieselbe Regel wie in den
    // Konsolen-Editoren. Der Neuaufbau stellt den alten Wert wieder her.
    if (!isFinite(z)) return renderSettings();
    if (m.kind === "int") z = Math.round(z);
    if (m.kind === "ratio") z = Math.max(0, Math.min(1, z));
    cfgSet(key, z);
  });
  field.addEventListener("keydown", (e) => { if (e.key === "Enter") field.blur(); });
  // Ein Prozentwert liest sich als Prozent, nicht als 0.8 — die Datei traegt
  // trotzdem die Zahl, mit der der Vergleich rechnet.
  const zusatz = m.kind === "ratio" ? "= " + Math.round((Number(value) || 0) * 100) + " %"
                                   : (m.unit || "");
  if (!zusatz) return field;
  return el("div", {class: "cfg-unit"}, field, el("span", {class: "unit"}, zusatz));
}

/** Feste kurze Auswahl als Kacheln — dieselbe Regel wie beim Block-Typ. */
function cfgTiles(key, m, value) {
  return el("div", {class: "cfg-chips"}, (m.options || []).map((o) =>
    el("button", {class: "type-chip" + (cfgEqual(o.value, value) ? " on" : ""),
                  onclick: () => cfgSet(key, o.value)}, o.text)));
}

/** `scan_park_mouse`: aus (`false`) oder eine Stelle (`[x, y]`). */
function cfgPosition(key, m, value) {
  const on = Array.isArray(value);
  const xy = on ? value : [0, 0];
  const setXY = (i, v) => {
    const neu = [Number(xy[0]) || 0, Number(xy[1]) || 0];
    neu[i] = Math.round(Number(v) || 0);
    cfgSet(key, neu);
  };
  const number = (i) => {
    const f = el("input", {type: "number", step: "1", value: xy[i], disabled: !on});
    f.addEventListener("change", () => setXY(i, f.value));
    return f;
  };
  return el("div", {class: "column", style: "gap:6px"},
    toggle(on ? "parken" : "aus", on, (v) => cfgSet(key, v ? [xy[0], xy[1]] : false)),
    on ? el("div", {class: "gitter2"}, number(0), number(1)) : null,
    // Eine Stelle faehrt man an, statt sie zu tippen — derselbe Weg wie beim
    // Klick-Block. Messen kann das nur ein Prozess auf demselben Rechner, und
    // das ist dieser hier.
    on ? el("button", {class: "btn quiet", onclick: () => cfgCapturePosition(key)},
            "✛ mit der Maus setzen") : null,
    on ? el("p", {class: "hint"}, "Maus im Spiel an die Stelle, dann ENTER.") : null);
}

async function cfgCapturePosition(key) {
  setStatus({text: "Maus an die Stelle bewegen und ENTER drücken (ESC bricht ab).",
               kind: "warn"});
  const answer = await withWait("ask", "mouse_position");
  if (!answer) return;
  if (!answer.ok) return setStatus({text: answer.message || "Abgebrochen.", kind: "warn"});
  cfgSet(key, [answer.x, answer.y]);
  setStatus({text: "Parkposition: (" + answer.x + ", " + answer.y + ")", kind: "ok"});
}

/** Was ein leeres Feld bzw. eine 0 hier bedeutet — nur dann, wenn es so steht.
 *
 * Ohne diese Zeile liest sich eine 0 wie „aus", und bei `click_max_total` heisst
 * sie das Gegenteil. Sie steht deshalb am Wert und nicht in der Erklaerung: dort
 * las man sie erst, wenn man schon zweifelte. */
function cfgEmpty(key, m) {
  const value = cfgValue(key);
  const empty = value === null || value === undefined || value === "" || value === 0;
  if (!m.empty || !empty) return null;
  return el("span", {class: "cfg-default"}, "= " + m.empty);
}

/** Wie lang der Standardwert IM KNOPF stehen darf, bevor er in den Tooltip
 *  wandert. Eine Zahl, „an", ein Enum-Text passen; ein Satz nicht. */
const STD_MAX = 24;

function cfgDefault(key, m) {
  const std = C.defaults[key];
  if (cfgEqual(cfgValue(key), std))
    return el("span", {class: "cfg-default"}, "Standard");
  // **Ein Knopf sagt, was er TUT** — dieselbe Regel wie beim Rückgängig im
  // Scans-Reiter. `cfgText()` gibt bei einem leeren Standardwert den
  // `empty`-Satz zurück ("Kategorie und Namen bleiben Handarbeit"), und der
  // stand hier als Beschriftung: der Knopf war breiter als seine Spalte und
  // lief rechts aus dem Fenster. Der Satz steht ohnehin schon eine Zeile
  // höher an `cfgEmpty()` — hier gehört hin, worauf zurückgesetzt wird.
  const raw = (std === null || std === undefined || std === "")
    ? "(leer)" : cfgText(std, m);
  const short = raw.length > STD_MAX;
  return el("button", {class: "btn quiet cfg-default",
                       title: "auf den Standardwert zurücksetzen"
                              + (short ? ": " + raw : ""),
                       onclick: () => cfgSet(key, std)},
            "↺ Standard" + (short ? "" : ": " + raw));
}

function renderCfgRight() {
  const target = $("cfg-right");
  const keys = Object.keys(cfgChanged);
  target.replaceChildren();

  const head = el("div", {class: "section"},
    el("div", {class: "row"},
      el("span", {class: "heading grow"}, "ÄNDERUNGEN"),
      keys.length ? el("span", {class: "num"}, keys.length) : null),
    el("button", {class: "btn primary", disabled: !keys.length, onclick: cfgSave},
       "In config.json schreiben"),
    keys.length ? el("button", {class: "btn", onclick: () => {
      cfgChanged = {}; cfgCorrections = []; renderSettings();
    }}, "Änderungen verwerfen") : null);
  target.appendChild(head);

  const listEl = el("div", {class: "section growing"});
  if (!keys.length && !cfgCorrections.length) {
    listEl.appendChild(el("p", {class: "hint"},
      "Nichts geändert. Ein Wert gilt erst, wenn er geschrieben ist."));
  }
  for (const key of keys) {
    const m = C.meta[key] || {};
    listEl.appendChild(el("div", {class: "cfg-card"},
      el("div", {class: "row"},
        el("span", {class: "grow", style: "font-size:12px"}, m.label || key),
        el("button", {class: "btn quiet", title: "diese Änderung zurücknehmen",
                      onclick: () => cfgSet(key, C.values[key])}, "zurück")),
      el("div", {class: "cfg-key"}, key),
      el("div", {class: "row small"},
        el("span", {class: "cfg-old"}, cfgText(C.values[key], m)), "→",
        el("span", {class: "cfg-new"}, cfgText(cfgChanged[key], m)))));
  }
  // Korrekturen stehen, bis der naechste Wert angefasst wird: die Datei enthaelt
  // dann etwas anderes als eingegeben, und das darf nicht stillschweigend
  // passieren.
  for (const k of cfgCorrections) {
    const m = C.meta[k.key] || {};
    listEl.appendChild(el("div", {class: "cfg-card warn"},
      el("div", {style: "font-size:12px;color:var(--accent)"}, "korrigiert beim Speichern"),
      el("div", {class: "cfg-key"}, k.key),
      el("div", {class: "row small"},
        el("span", {class: "cfg-old"}, cfgText(k.sent, m)), "→",
        el("span", {class: "cfg-new"}, cfgText(k.became, m)))));
  }
  target.appendChild(listEl);

  target.appendChild(el("div", {class: "section"},
    el("p", {class: "hint"},
      "Ein laufender Lauf zieht sofort mit — der Hauptprozess lädt die Datei " +
      "neu, sobald hier geschrieben wurde."),
    el("p", {class: "cfg-key", style: "word-break:break-all"}, C.path || "")));
}

async function cfgSave() {
  // Ein Feld, in dem gerade getippt wird, meldet erst beim Verlassen.
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  const values = Object.assign({}, cfgChanged);
  const count = Object.keys(values).length;
  if (!count) return;
  const answer = await ask("config_write", {values: values});
  if (!answer) return;
  if (!answer.ok)
    return setStatus({text: answer.message || "Nicht gespeichert.", kind: "err"});
  C.values = answer.values;
  cfgChanged = {};
  cfgCorrections = answer.corrections || [];
  setStatus({
    text: count + (count === 1 ? " Einstellung" : " Einstellungen") + " gespeichert." +
          (cfgCorrections.length ? "  " + cfgCorrections.length + " davon korrigiert." : ""),
    kind: cfgCorrections.length ? "warn" : "ok"});
  renderSettings();
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
async function switchSequence(command, data_reload) {
  if (SC && SC.dirty) {
    const answer = await ask("scan_save");
    if (answer) {
      SC = answer;
      if (SC.dirty) {                       // nicht geschrieben — Grund steht drin
        await renderScans();
        return;
      }
    }
  }
  return call(command, data_reload);
}

/* --------------------------------------------------------------- Verdrahtung */

function wire() {
  for (const t of document.querySelectorAll(".tab"))
    t.addEventListener("click", () => setView(t.dataset.view));

  $("btn-load").addEventListener("click",
    () => switchSequence("load", {name: $("seq-select").value}));
  $("seq-select").addEventListener("dblclick",
    () => switchSequence("load", {name: $("seq-select").value}));
  $("btn-new").addEventListener("click", () => switchSequence("new"));
  $("btn-save").addEventListener("click", saveSequence);
  $("btn-recording").addEventListener("click", () => wzOpen("recording"));
  // Ein Knopf, zwei Bedeutungen — er trägt die aktuelle als Beschriftung, damit
  // niemand raten muss, was ein Druck jetzt tut.
  $("btn-run").addEventListener("click", () => sendRun(runWasRunning ? "stop" : "start"));
  $("btn-block-delete").addEventListener("click", () => call("selection_delete"));
  $("btn-block-copy").addEventListener("click", () => call("selection_duplicate"));

  $("seq-name").addEventListener("change", (e) =>
    call("sequence_set", {field: "name", value: e.target.value}));
  $("seq-cycles").addEventListener("change", (e) =>
    call("sequence_set", {field: "cycles", value: Number(e.target.value) || 0}));
  $("seq-info").addEventListener("change", (e) =>
    call("sequence_set", {field: "description", value: e.target.value}));
  $("point-filter").addEventListener("input", renderPoints);
  // Das Feld selbst wird beim Neuaufbau nicht ersetzt (es steht fest im
  // Dokument), deshalb darf es bei jedem Tastendruck melden.
  $("cfg-search").addEventListener("input", (e) => {
    cfgSearch = e.target.value.trim().toLowerCase();
    renderSettings();
  });

  for (const button of document.querySelectorAll("[data-scan-kind]"))
    button.addEventListener("click", () => scanSetKind(button.dataset.scanKind));
  for (const button of document.querySelectorAll("[data-erk-tool]"))
    button.addEventListener("click", () => callScan("region_mode",
      {kind: scanKind, mode: button.dataset.erkTool}));

  $("scan-open").addEventListener("change", (e) => {
    scanWizardStep = null;
    callScan("scan_open", {name: e.target.value});
  });
  $("scan-name").addEventListener("change", (e) => {
    if (!SC || !SC.open) return;
    callScan("scan_set", {name: SC.open, field: "name", value: e.target.value});
  });
  $("scan-name").addEventListener("keydown", (e) => {
    if (e.key === "Enter") e.target.blur();
  });
  $("scan-new").addEventListener("click", () => {
    scanWizardStep = 1;
    callScan("scan_new");
  });
  $("scan-free").addEventListener("click", () => {
    scanGuided = !scanGuided;
    renderScans();
  });
  document.querySelectorAll("[data-scan-schritt]").forEach((button) =>
    button.addEventListener("click", () => {
      scanWizardStep = Number(button.dataset.scanSchritt);
      scanSteps();
    }));
  $("scan-slots-find").addEventListener("click", () =>
    callScan("scan_mode_set", {mode: "find", kind: scanKind}));
  $("scan-slot-new").addEventListener("click", () =>
    callScan("scan_mode_set", {mode: "slot", kind: scanKind}));
  $("scan-test").addEventListener("click", () => callScan("scan_recognize"));
  $("scan-learn").addEventListener("click", () =>
    callScan("scan_learn_preview", {scope: "all"}));
  document.querySelectorAll("[data-scan-tool]").forEach((button) =>
    button.addEventListener("click", () =>
      callScan("scan_mode_set", {mode: button.dataset.scanTool, kind: scanKind})));
  $("scan-pin").addEventListener("click", () =>
    callScan("scan_mode_set", {mode: SC.mode, kind: scanKind,
                                   pinned: !SC.tool_pinned}));
  $("scan-photo").addEventListener("click", () => callScan("scan_screenshot", {kind: scanKind}));
  $("scan-fullscreen").addEventListener("click", () =>
    callScan("scan_area_set", {kind: scanKind}));
  $("scan-draw-area").addEventListener("click",
    () => callScan("scan_mode_set", {mode: "area", kind: scanKind}));
  $("scan-window-capture").addEventListener("click", scanMaintainWindows);
  $("scan-window").addEventListener("change", (e) => {
    const choice = scanWindows[Number(e.target.value)];
    // Waehlen nimmt NICHT auf — das tut der Knopf darueber. Vorher stand hier
    // beides in einem Griff, und dann sah es aus, als handele die Liste von
    // selbst und der Knopf gar nicht (er holte dasselbe Bild noch einmal).
    if (choice) callScan("scan_area_set",
      {kind: scanKind, area: choice.area, window: choice.id});
    else callScan("scan_area_set", {kind: scanKind});
  });
  $("scan-fit").addEventListener("click", scanFit);
  $("scan-actual-size").addEventListener("click", () => {
    // 1:1 heisst: ein Bildschirm-Pixel ist ein Bildschirm-Pixel. Das Bild ist
    // fuer die Uebertragung verkleinert, also muss der Zoom das ausgleichen.
    scanZoom = SC && SC.photo ? 1 / SC.photo.scale : 1;
    scanZoomManual = true;
    scanApplyZoom();
  });
  for (const head of document.querySelectorAll(".collapse-header")) {
    head.addEventListener("click", () => {
      const s = head.dataset.klapp;
      // Beim ersten Griff die Vorgabe uebernehmen und umdrehen — sonst taete der
      // erste Klick auf einen automatisch zugeklappten Abschnitt nichts.
      collapsed[s] = !(collapsed[s] === null ? collapseDefault(s) : collapsed[s]);
      maintainCollapse();
    });
  }

  const surface = $("scan-overlay");
  const stage = $("scan-stage");
  surface.addEventListener("click", (e) => {
    // Ein Klick, der ein Ziehen beendet hat, ist kein Klick. Ohne das waehlte
    // das Loslassen den Slot gleich noch einmal neu aus.
    if (scanDragDone) { scanDragDone = false; return; }
    const position = scanPositionFromEvent(e);
    if (!position) return;
    // ALT misst den Hintergrund des Slots unter dem Zeiger — ohne den Umweg
    // ueber die Modus-Kachel. Der haeufigste Handgriff nach dem Finden.
    if (e.altKey) return callScan("scan_direct", {x: position[0], y: position[1],
                                                 what: "measure", kind: scanKind});
    // STRG nimmt einen einzelnen Slot zur Auswahl dazu oder heraus — dieselbe
    // Geste wie im Sequenz-Editor.
    callScan("scan_click", {x: position[0], y: position[1], kind: scanKind,
                           additive: e.ctrlKey || e.metaKey});
  });
  // Beim automatischen Finden darf eine Ecke auch im freien Teil der MITTLEREN
  // Buehne liegen. Der Helfer klemmt sie an den Bildrand; die Seitenleisten
  // liegen ausserhalb dieses Elements und koennen die Geste nie ausloesen.
  stage.addEventListener("click", (e) => {
    const position = scanSearchPositionFromStage(e);
    if (position) callScan("scan_click", {x: position[0], y: position[1], kind: scanKind});
  });
  surface.addEventListener("dblclick", (e) => {
    const position = scanPositionFromEvent(e);
    if (position) callScan("scan_direct",
      {x: position[0], y: position[1], what: "click", kind: scanKind});
  });

  // **Einen gewaehlten Slot zieht man, statt vier Zahlen zu tippen.** Gepackt
  // wird nur, was schon gewaehlt IST — damit braucht die Seite keine eigene
  // Trefferregel (die liegt in `_slot_under()` in Python und soll dort bleiben),
  // und die Geste liest sich wie ueberall sonst: erst auswaehlen, dann ziehen.
  surface.addEventListener("mousedown", (e) => {
    if (e.button !== 0 || !SC || SC.mode !== "choice" || SC.corner) return;
    const position = scanPositionFromEvent(e);
    if (!position || !scanSelectedSlots().some((s) => scanInSlot(s, position))) return;
    scanDragStart = position;
    scanDragOffset = [0, 0];
  });
  surface.addEventListener("mousemove", (e) => {
    if (scanDragStart) {
      const position = scanPositionFromEvent(e);
      if (!position) return;
      const dx = position[0] - scanDragStart[0], dy = position[1] - scanDragStart[1];
      // **Ein wackliger Klick ist kein Ziehen.** Unter der Schwelle bleibt es
      // ein Klick (also eine Auswahl); ohne sie verschöbe jedes Anklicken eines
      // gewählten Slots ihn um ein, zwei Pixel — und weil das aussieht wie
      // nichts, fiele es erst beim Erkennen auf.
      if (!scanDragOffset && Math.abs(dx) < 2 && Math.abs(dy) < 2) return;
      scanDragOffset = [dx, dy];
      // Nur zeichnen: geschrieben wird einmal beim Loslassen.
      scanOverlay();
      return;
    }
    // Nur waehrend des Aufziehens gebraucht — sonst waere es ein Neuaufbau des
    // Overlays bei jeder Mausbewegung.
    if (!SC || !SC.corner) return;
    scanPointer = scanPositionFromEvent(e);
    scanOverlay();
  });
  stage.addEventListener("mousemove", (e) => {
    if (!SC || !SC.corner || SC.mode !== "find") return;
    const position = scanSearchPositionFromStage(e);
    if (!position) return;
    scanPointer = position;
    scanOverlay();
  });
  // Am Fenster, nicht an der Flaeche: wer ueber den Bildrand hinauszieht,
  // liesse sonst einen Slot am Zeiger kleben.
  window.addEventListener("mouseup", () => {
    if (!scanDragStart) return;
    const [dx, dy] = scanDragOffset || [0, 0];
    scanDragStart = scanDragOffset = null;
    if (!dx && !dy) return;
    scanDragDone = true;
    callScan("scan_move", {dx: dx, dy: dy});
  });
  // Mit STRG zoomen, wie in jedem Bildbetrachter; ohne STRG scrollt die Buehne.
  $("scan-stage").addEventListener("wheel", (e) => {
    if (!e.ctrlKey || !SC || !SC.photo) return;
    e.preventDefault();
    scanZoom = Math.max(0.05, Math.min(4, scanZoom * (e.deltaY < 0 ? 1.15 : 0.87)));
    scanZoomManual = true;
    scanApplyZoom();
  }, {passive: false});

  // **Die Buehne aendert ihre Groesse mit dem Fenster, das Bild tat es nicht.**
  // Wer klein aufnimmt und dann gross zieht, sah sein Bild in einer Ecke kleben;
  // wer gross aufnimmt und klein zieht, musste scrollen. Beides ist derselbe
  // fehlende Handgriff. Ein von Hand gesetzter Zoom bleibt stehen — der ist eine
  // Ansage, die Fenstergroesse nicht.
  let scanFrame = 0;
  window.addEventListener("resize", () => {
    if (view !== "scans" || !SC || !SC.photo || scanZoomManual) return;
    // Gebuendelt: waehrend des Ziehens am Fensterrand feuert das im Dutzend,
    // und jeder Aufruf baut das Overlay neu.
    clearTimeout(scanFrame);
    scanFrame = setTimeout(scanFit, 120);
  });

  $("dialog-cancel").addEventListener("click", closeQuestion);
  $("dialog-discard").addEventListener("click", () => proceed(true));
  $("dialog-save").addEventListener("click", () => proceed(false));

  // Ziehen über dem Board darf nicht als "Datei öffnen" enden.
  document.addEventListener("dragover", (e) => { if (drag) e.preventDefault(); });
  document.addEventListener("drop", (e) => e.preventDefault());
  document.addEventListener("keydown", keyboard);
}

async function saveSequence() {
  // Ein Feld, in dem gerade getippt wird, meldet seinen Wert erst beim Verlassen.
  // Ohne das Blur ginge die letzte Eingabe beim Speichern verloren.
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  await call("save");
  // Nur hier nachziehen, nicht in `render()`: die Liste liest jede Sequenzdatei
  // einmal, und `render()` läuft nach JEDEM Befehl. Ändern kann sich die Liste
  // ohnehin nur durch ein Speichern (Umbenennen legt eine neue Datei an).
  if (view === "sequences") renderSequenceList();
}

function inTextField() {
  const a = document.activeElement;
  return a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.tagName === "SELECT");
}

function keyboard(e) {
  if (e.key === "Escape") {
    if (openQuestion) return closeQuestion();
    if (inTextField()) return document.activeElement.blur();
    if (view === "scans") return callScan("scan_cancel");
    if (view === "einstellungen") return;
    if (selectedPhase !== null) {
      selectedPhase = null;
      return renderPhases();
    }
    return call("selection_clear");
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    // Derselbe Griff, drei Dateien: welche gemeint ist, sagt der offene Reiter.
    if (view === "einstellungen") return cfgSave();
    if (view === "scans") return callScan("scan_save");
    return saveSequence();
  }
  if (inTextField() || openQuestion) return;
  if (view === "scans") {
    // STRG+Z steht NACH der Textfeld-Abfrage: in einem Eingabefeld gehoert das
    // Rueckgaengig dem Feld, nicht dem Reiter.
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      return callScan("scan_undo");
    }
    // **Pfeiltasten schieben die Auswahl.** Ein Slot, der drei Pixel daneben
    // liegt, war vorher nur ueber vier Zahlenfelder zu retten — und dreissig
    // gar nicht.
    const nudge = {ArrowLeft: [-1, 0], ArrowRight: [1, 0],
                   ArrowUp: [0, -1], ArrowDown: [0, 1]}[e.key];
    if (nudge && SC && (SC.selection.length || SC.choice.kind === "slot")) {
      e.preventDefault();
      const wide = e.shiftKey ? 10 : 1;
      // Eine GEHALTENE Taste ist ein Verschieben, nicht dreissig: nur der erste
      // Schritt einer Serie kommt auf den Rueckgaengig-Stapel.
      const now = Date.now();
      const serie = now - scanNudgeTime < 900;
      scanNudgeTime = now;
      return callScan("scan_move",
                     {dx: nudge[0] * wide, dy: nudge[1] * wide, counts: !serie});
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
    if (scanKind === "item") {
      const mode = SCAN_MODES.find((m) => m.shortcut.toLowerCase() === e.key.toLowerCase());
      if (mode) { e.preventDefault(); return callScan("scan_mode_set",
        {mode: mode.key, kind: scanKind}); }
      if (e.key === "Delete" && SC && SC.choice.kind === "slot") {
        e.preventDefault();
        return callScan("scan_slot_delete");
      }
      return;
    }
    // Dieselbe Idee eine Ebene weiter: R und K sind die beiden Werkzeuge der
    // Erkennungs-Scans, T testet. Testen liegt auf einer Taste, weil man beim
    // Einstellen einer Toleranz zehnmal hintereinander testet.
    const tool = {r: "region", k: "action"}[e.key.toLowerCase()];
    if (tool) {
      e.preventDefault();
      return callScan("region_mode", {kind: scanKind, mode: tool});
    }
    if (e.key.toLowerCase() === "t" && SC && detScan()) {
      e.preventDefault();
      return detTest();
    }
    if (e.key === "Delete" && scanKind === "boss" && SC && SC.boss.choice) {
      e.preventDefault();
      return callScan("boss_delete");
    }
    return;
  }
  // Alles Weitere arbeitet auf der Block-Auswahl, die es hier nicht gibt.
  if (view === "einstellungen") return;
  if (e.key === "Delete" && selectedPhase !== null) {
    e.preventDefault();
    const phase = selectedPhase;
    selectedPhase = null;
    return call("phase_delete", {phase: phase});
  }
  if (e.key === "Delete") { e.preventDefault(); return call("selection_delete"); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d") {
    e.preventDefault();          // sonst legt der Browser ein Lesezeichen an
    return call("selection_duplicate");
  }
  if (e.altKey && e.key === "ArrowUp") { e.preventDefault(); return call("selection_move", {delta: -1}); }
  if (e.altKey && e.key === "ArrowDown") { e.preventDefault(); return call("selection_move", {delta: 1}); }
}

waitForBridge().then(async () => {
  wire();
  edgePulse();
  await call("snapshot");
  // CTRL+ALT+V startet denselben Prozess wie CTRL+ALT+B, nur mit vorgewaehltem
  // Reiter. Erst NACH der ersten Momentaufnahme, weil sie den Wunsch mitbringt.
  if (S && S.start_view && S.start_view !== "editor") setView(S.start_view);
});
