// Browserless vm battery for the Áreas selection surface (issue #16).
//
// Mirrors tests/test_eventos_vm.mjs and tests/test_monitoramento_vm.mjs:
// executes real `app/static/app.js` under node `vm` with DOM stubbing
// built from `app/static/index.html`, driving `loadAreas()`, bulk controls,
// filter combinations, empty states, and layout invariants against Issue #16 spec.
//
// Exit code 0 = every scenario green; failures print SCENARIO FAILED lines.

import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const APP_JS = path.join(ROOT, "app", "static", "app.js");
const INDEX_HTML = path.join(ROOT, "app", "static", "index.html");
const COMPONENTS_CSS = path.join(ROOT, "app", "static", "components.css");
const I18N_PY = path.join(ROOT, "app", "i18n.py");

const source = fs.readFileSync(APP_JS, "utf8");
const indexHtml = fs.readFileSync(INDEX_HTML, "utf8");
const componentsCss = fs.readFileSync(COMPONENTS_CSS, "utf8");
const i18nSource = fs.readFileSync(I18N_PY, "utf8");

let failures = 0;
function check(name, condition, detail) {
  if (condition) {
    console.log(`  ok  ${name}`);
  } else {
    failures += 1;
    console.log(`  FAIL ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

// Lightweight i18n extractor — uses [a-z_0-9]+ so keys with digits match.
function extractTranslations(sourceText) {
  const result = { pt: {}, en: {} };
  const ptStart = sourceText.indexOf('"pt": {');
  const enStart = sourceText.indexOf('"en": {');
  if (ptStart === -1 || enStart === -1) {
    throw new Error("Could not locate pt/en blocks in app/i18n.py");
  }
  const kvRegex = /"([a-z_0-9]+)":\s*"([^"\\]*(?:\\.[^"\\]*)*)"(?:,|\s*\n)/g;
  for (const m of sourceText.slice(ptStart, enStart).matchAll(kvRegex)) {
    result.pt[m[1]] = m[2];
  }
  for (const m of sourceText.slice(enStart).matchAll(kvRegex)) {
    result.en[m[1]] = m[2];
  }
  return result;
}
const tr = extractTranslations(i18nSource);

// ---- DOM stub --------------------------------------------------------------
const registry = new Map();

function makeElement() {
  const el = {
    tagName: "DIV",
    dataset: {},
    attributes: {},
    listeners: {},
    hidden: false,
    value: "",
    disabled: false,
    checked: false,
    textContent: "",
    _innerHTML: "",
    _children: [],
    set innerHTML(v) {
      this._innerHTML = String(v ?? "");
      this._children = [];
      adoptInnerHTML(this, this._innerHTML);
    },
    get innerHTML() { return this._innerHTML || ""; },
    classList: {
      _set: new Set(),
      add(c) { this._set.add(c); },
      remove(c) { this._set.delete(c); },
      toggle(c, on) {
        if (on === undefined) {
          if (this._set.has(c)) this._set.delete(c);
          else this._set.add(c);
        } else if (on) this._set.add(c);
        else this._set.delete(c);
      },
      contains(c) { return this._set.has(c); },
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
      if (name === "data-id") this.dataset.id = String(value);
      if (name === "data-view") this.dataset.view = String(value);
      if (name === "data-i18n") this.dataset.i18n = String(value);
      if (name === "href") this.href = String(value);
    },
    getAttribute(name) {
      if (name === "href") return this.href ?? null;
      return Object.prototype.hasOwnProperty.call(this.attributes, name)
        ? this.attributes[name]
        : null;
    },
    addEventListener(type, fn) {
      (this.listeners[type] ||= []).push(fn);
    },
    removeEventListener(type, fn) {
      const arr = this.listeners[type] || [];
      const i = arr.indexOf(fn);
      if (i >= 0) arr.splice(i, 1);
    },
    focus() { documentStub.activeElement = this; },
    blur() { if (documentStub.activeElement === this) documentStub.activeElement = null; },
    append(child) {
      (this._children ||= []).push(child);
      child.parentElement = this;
    },
    click() {
      for (const fn of this.listeners.click || []) {
        try {
          const r = fn({ currentTarget: this, target: this, preventDefault() {}, stopPropagation() {} });
          if (r && typeof r.catch === "function") r.catch(() => {});
        } catch {}
      }
    },
    dispatch(type, init = {}) {
      for (const fn of this.listeners[type] || []) {
        try {
          const r = fn(Object.assign({ currentTarget: this, target: this, preventDefault() {}, stopPropagation() {} }, init));
          if (r && typeof r.catch === "function") r.catch(() => {});
        } catch {}
      }
    },
    querySelector(selector) {
      return findChild(this, selector);
    },
    querySelectorAll(selector) {
      const out = [];
      collectChildren(this, selector, out);
      return out;
    },
  };
  return el;
}

function adoptInnerHTML(parent, html) {
  // Parse rows and inputs from innerHTML
  const rowMatches = [...html.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/g)];
  for (const rowMatch of rowMatches) {
    const rowEl = makeElement();
    rowEl.tagName = "TR";
    rowEl.parentElement = parent;
    parent.append(rowEl);

    // Look for checkboxes inside the row
    const inputMatches = [...rowMatch[1].matchAll(/<input([^>]*?)>/g)];
    for (const inMatch of inputMatches) {
      const attrs = inMatch[1];
      const inputEl = makeElement();
      inputEl.tagName = "INPUT";
      inputEl.parentElement = rowEl;

      const typeMatch = attrs.match(/type=["']([^"']+)["']/);
      if (typeMatch) inputEl.setAttribute("type", typeMatch[1]);
      const classMatch = attrs.match(/class=["']([^"']+)["']/);
      if (classMatch) {
        for (const c of classMatch[1].split(/\s+/)) if (c) inputEl.classList.add(c);
      }
      const dataIdMatch = attrs.match(/data-id=["']([^"']+)["']/);
      if (dataIdMatch) inputEl.setAttribute("data-id", dataIdMatch[1]);
      if (/checked\b/.test(attrs)) inputEl.checked = true;

      rowEl.append(inputEl);
      // Register for $$(".area-checkbox") lookup
      const idKey = inputEl.dataset.id ? `checkbox-${inputEl.dataset.id}` : `cb-${Math.random()}`;
      registry.set(idKey, inputEl);
    }
  }
}

function findChild(parent, selector) {
  const all = [];
  collectChildren(parent, selector, all);
  return all[0] || null;
}

function collectChildren(parent, selector, out) {
  for (const child of parent._children || []) {
    if (matchChild(child, selector)) out.push(child);
    collectChildren(child, selector, out);
  }
}

function matchChild(el, selector) {
  if (!el) return false;
  if (selector.startsWith(".")) {
    return el.classList && el.classList.contains(selector.slice(1));
  }
  if (selector.startsWith("#")) {
    return el.attributes && el.attributes.id === selector.slice(1);
  }
  return false;
}

function autoregister(selector) {
  if (registry.has(selector)) return registry.get(selector);
  const el = makeElement();
  if (selector.startsWith("#")) el.setAttribute("id", selector.slice(1));
  else if (selector.startsWith(".")) el.classList.add(selector.slice(1));
  registry.set(selector, el);
  return el;
}

// ---- Register existing elements from index.html ----
const areaSearch = autoregister("#area-search");
const areaCategory = autoregister("#area-category");
const areaSelected = autoregister("#area-selected");
const areaFilter = autoregister("#area-filter");
const selectAllFiltered = autoregister("#select-all-filtered");
const deselectAllFiltered = autoregister("#deselect-all-filtered");
const areaSummary = autoregister("#area-summary");
const areaStatus = autoregister("#area-status");
const areaError = autoregister("#area-error");
const areasBody = autoregister("#areas-body");
const areasPrev = autoregister("#areas-prev");
const areasNext = autoregister("#areas-next");
const areasPaginationInfo = autoregister("#areas-pagination-info");

// Global document stub
const documentStub = {
  activeElement: null,
  documentElement: { lang: "en" },
  body: {
    contains(el) { return true; },
  },
  querySelector(sel) {
    if (registry.has(sel)) return registry.get(sel);
    return autoregister(sel);
  },
  querySelectorAll(sel) {
    if (sel === ".area-checkbox") {
      const out = [];
      for (const [k, el] of registry.entries()) {
        if (el && el.classList && el.classList.contains("area-checkbox")) out.push(el);
      }
      return out;
    }
    const match = registry.get(sel);
    return match ? [match] : [];
  },
  addEventListener(type, fn) {},
};

// ---- Mock API fetch routes -------------------------------------------------
let mockAreas = [];
let mockStatus = {
  areas: { total: 0, selected: 0 },
  query_regions: 0,
};
let lastSelectionPayload = null;
let apiCalls = [];

function resetApi() {
  apiCalls = [];
  lastSelectionPayload = null;
  mockAreas = [
    { id: "area-1", name: "TI Raposa Serra do Sol", category: "indigenous_territory", state: "RR", phase: "Homologada", selected: true, source: "FUNAI" },
    { id: "area-2", name: "TI Yanomami", category: "indigenous_territory", state: "RR/AM", phase: "Regularizada", selected: false, source: "FUNAI" },
    { id: "area-3", name: "PARNA Montanhas do Tumucumaque", category: "conservation_unit", state: "AP/PA", phase: "Criada", selected: true, source: "CNUC" },
  ];
  mockStatus = {
    areas: { total: 3, selected: 2 },
    query_regions: 4,
    warnings: [],
    phase: "review",
    version: "0.8.3",
    events: { total: 0, review: { useful: 0, unreviewed: 0, noise: 0, uncertain: 0 } },
  };
}

function jsonResponse(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
  };
}

function fakeFetch(url, options = {}) {
  const method = options.method || "GET";
  apiCalls.push({ endpoint: url, method, body: options.body });
  if (url.startsWith("/api/areas/selection")) {
    lastSelectionPayload = options.body ? JSON.parse(options.body) : null;
    return Promise.resolve(jsonResponse({ success: true }));
  }
  if (url.startsWith("/api/areas")) {
    const u = new URL("http://localhost" + url);
    const search = (u.searchParams.get("search") || "").toLowerCase();
    const cat = u.searchParams.get("category") || "";
    const sel = u.searchParams.get("selected") || "";
    const limit = parseInt(u.searchParams.get("limit") || "50", 10);
    const offset = parseInt(u.searchParams.get("offset") || "0", 10);

    let filtered = mockAreas.filter((a) => {
      if (search && !a.name.toLowerCase().includes(search) && !(a.state || "").toLowerCase().includes(search)) return false;
      if (cat && a.category !== cat) return false;
      if (sel === "true" && !a.selected) return false;
      if (sel === "false" && a.selected) return false;
      return true;
    });

    const paginated = filtered.slice(offset, offset + limit);
    return Promise.resolve(jsonResponse({
      total: filtered.length,
      items: paginated,
    }));
  }
  if (url === "/api/status") {
    return Promise.resolve(jsonResponse(mockStatus));
  }
  return Promise.resolve(jsonResponse({}));
}

const sandbox = {
  console,
  setTimeout,
  clearTimeout,
  URLSearchParams,
  document: documentStub,
  window: {
    location: { hash: "", pathname: "/", search: "" },
    addEventListener() {},
  },
  history: {
    length: 1,
    pushState() {},
    replaceState() {},
    back() {},
  },
  fetch: fakeFetch,
};
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: "app.js" });

const exportsObj = vm.runInContext(
  "({ loadAreas: typeof loadAreas !== 'undefined' ? loadAreas : null, bulkFiltered: typeof bulkFiltered !== 'undefined' ? bulkFiltered : null, loadStatus: typeof loadStatus !== 'undefined' ? loadStatus : null, appState: typeof appState !== 'undefined' ? appState : null, t: typeof t !== 'undefined' ? t : null })",
  sandbox,
  { filename: "(exports)" },
);
const { loadAreas, bulkFiltered, loadStatus, appState, t } = exportsObj;

if (appState) {
  appState.translations = tr;
  appState.language = "pt";
}
// ---- Test Scenarios --------------------------------------------------------

console.log("Scenario 1: Markup and layout invariants (#view-areas)");
check(
  "(1a) #view-areas section exists in index.html",
  /<section\s+id=["']view-areas["']/.test(indexHtml),
  "expected #view-areas section in index.html"
);
check(
  "(1b) .areas-shell wraps the view-areas content",
  /<section\s+id=["']view-areas["'][\s\S]*?<div\s+class=["']areas-shell["']>/.test(indexHtml),
  "expected <div class='areas-shell'> inside #view-areas"
);
check(
  "(1c) .areas-toolbar contains header, filters, bulk controls, and instructions",
  /<div\s+class=["']areas-toolbar["']>[\s\S]*?class=["']panel-header wrap["'][\s\S]*?class=["']bulk["'][\s\S]*?class=["']phase-grid areas-instructions["']/.test(indexHtml),
  "expected .areas-toolbar to group header, filters, bulk, instructions"
);
check(
  "(1d) .panel wraps table and pagination below .areas-toolbar",
  /<\/div>\s*<article\s+class=["']panel["']>\s*<div\s+class=["']table-wrap["']>/.test(indexHtml),
  "expected <article class='panel'> with table-wrap below .areas-toolbar"
);
const requiredIds = [
  "area-search", "area-category", "area-selected", "area-filter",
  "select-all-filtered", "deselect-all-filtered", "area-summary",
  "area-status", "area-error", "areas-body",
  "areas-prev", "areas-next", "areas-pagination-info"
];
for (const id of requiredIds) {
  check(
    `(1e) #${id} preserved in markup`,
    new RegExp(`id=["']${id}["']`).test(indexHtml),
    `missing #${id} in index.html`
  );
}
check(
  "(1f) No map element on Áreas page",
  !/<section\s+id=["']view-areas["'][\s\S]*?<div\s+id=["'](?:area-map|areas-map)["']/.test(indexHtml),
  "unexpected map element inside #view-areas"
);
check(
  "(1g) No 'Limpar filtros' button on Áreas page (per spec)",
  !/<section\s+id=["']view-areas["'][\s\S]*?(?:Limpar\s+filtros|clear-filter)/i.test(indexHtml),
  "unexpected 'Limpar filtros' button found in #view-areas"
);

console.log("\nScenario 2: CSS rules and sticky toolbar invariants");
check(
  "(2a) .areas-shell flex column layout",
  /\.areas-shell\s*\{[\s\S]*?display:\s*flex;[\s\S]*?flex-direction:\s*column;[\s\S]*?gap:\s*16px;/.test(componentsCss),
  "expected .areas-shell flex layout rules in components.css"
);
check(
  "(2b) .areas-toolbar has position: sticky below tabs/subnav",
  /\.areas-toolbar\s*\{[\s\S]*?position:\s*sticky;[\s\S]*?top:\s*(?:48|104)px;[\s\S]*?z-index:\s*4;/.test(componentsCss),
  "expected sticky top:48px or top:104px z-index:4 on .areas-toolbar"
);
check(
  "(2c) .areas-toolbar .bulk has padding: 0 to sit flush inside toolbar",
  /\.areas-toolbar\s+\.bulk\s*\{[\s\S]*?padding:\s*0;/.test(componentsCss),
  "expected padding:0 on .areas-toolbar .bulk"
);
check(
  "(2d) components.css brace balance is 0",
  (() => {
    let o = 0, c = 0;
    for (const ch of componentsCss) { if (ch === "{") o++; if (ch === "}") c++; }
    return o === c;
  })(),
  "unbalanced braces in components.css"
);

console.log("\nScenario 3: loadAreas() populates table and count summary");
resetApi();
await loadAreas();
check(
  "(3a) #area-summary displays matching count",
  areaSummary.textContent.includes("3") && areaSummary.textContent.includes(tr.pt.areas_matching || "áreas correspondentes"),
  `got "${areaSummary.textContent}"`
);
check(
  "(3b) 3 rows rendered in #areas-body",
  areasBody._children.filter((c) => c.tagName === "TR").length === 3,
  `got ${areasBody._children.length} rows`
);
check(
  "(3c) Primary label is area.name, not raw external_id",
  areasBody.innerHTML.includes("TI Raposa Serra do Sol") && !areasBody.innerHTML.includes("<td>area-1</td>"),
  "table should show area name, not raw id as primary cell"
);
check(
  "(3d) Checkboxes render with correct checked state",
  (() => {
    const cb1 = registry.get("checkbox-area-1");
    const cb2 = registry.get("checkbox-area-2");
    return cb1 && cb1.checked === true && cb2 && cb2.checked === false;
  })(),
  "checkboxes should reflect area.selected"
);
check(
  "(3e) Pagination info displays range",
  areasPaginationInfo.textContent === "1–3 / 3",
  `got "${areasPaginationInfo.textContent}"`
);

console.log("\nScenario 4: Filter combinations");
resetApi();
appState.areaFilter.search = "Raposa";
appState.areaFilter.category = "";
appState.areaFilter.selected = "";
await loadAreas();
check(
  "(4a) Search filter narrows result",
  areasBody._children.filter((c) => c.tagName === "TR").length === 1 &&
    areasBody.innerHTML.includes("TI Raposa Serra do Sol"),
  "expected 1 row for search 'Raposa'"
);

appState.areaFilter.search = "";
appState.areaFilter.category = "conservation_unit";
await loadAreas();
check(
  "(4b) Category filter narrows result to conservation units",
  areasBody._children.filter((c) => c.tagName === "TR").length === 1 &&
    areasBody.innerHTML.includes("Montanhas do Tumucumaque"),
  "expected 1 conservation unit row"
);

appState.areaFilter.category = "";
appState.areaFilter.selected = "false";
await loadAreas();
check(
  "(4c) Selected=false filter shows only unselected areas",
  areasBody._children.filter((c) => c.tagName === "TR").length === 1 &&
    areasBody.innerHTML.includes("TI Yanomami"),
  "expected 1 unselected area (TI Yanomami)"
);

console.log("\nScenario 5: Empty states (zero-data vs no filter match)");
// Case 5a: Areas exist in dataset, but filter matches zero
appState.areaFilter.search = "nonexistent-area-xyz";
await loadAreas();
check(
  "(5a) Filter returning zero results shows areas_no_match copy",
  areasBody.innerHTML.includes(tr.pt.areas_no_match || "Nenhuma área corresponde aos filtros"),
  `expected "${tr.pt.areas_no_match}", got: ${areasBody.innerHTML}`
);

// Case 5b: Zero areas in total dataset
mockAreas = [];
mockStatus = { areas: { total: 0, selected: 0 }, query_regions: 0 };
appState.areaFilter.search = "";
appState.areaFilter.category = "";
appState.areaFilter.selected = "";
await loadAreas();
check(
  "(5b) Zero-data in dataset shows areas_no_data copy ('Nenhuma área disponível')",
  areasBody.innerHTML.includes(tr.pt.areas_no_data || "Nenhuma área disponível"),
  `expected "${tr.pt.areas_no_data}", got: ${areasBody.innerHTML}`
);
check(
  "(5c) Zero-data copy does NOT mention any screen (durable across issues)",
  !areasBody.innerHTML.includes("sincronização") && !areasBody.innerHTML.includes("Monitoramento"),
  "zero-data copy must not name screens or manual sync actions"
);

console.log("\nScenario 6: Individual area selection toggling");
resetApi();
appState.areaFilter = { search: "", category: "", selected: "" };
await loadAreas();
const cbYanomami = registry.get("checkbox-area-2");
check("(6a) Checkbox found for area-2", !!cbYanomami);
if (cbYanomami) {
  cbYanomami.checked = true;
  cbYanomami.dispatch("change");
  // Wait microtask tick for async save
  await new Promise((r) => setTimeout(r, 20));
  check(
    "(6b) Toggling checkbox calls POST /api/areas/selection",
    lastSelectionPayload &&
      Array.isArray(lastSelectionPayload.ids) &&
      lastSelectionPayload.ids[0] === "area-2" &&
      lastSelectionPayload.selected === true,
    `payload=${JSON.stringify(lastSelectionPayload)}`
  );
}

console.log("\nScenario 7: Bulk selection controls");
resetApi();
await bulkFiltered(true);
check(
  "(7a) Select all filtered calls POST with selected=true",
  lastSelectionPayload && lastSelectionPayload.selected === true,
  `payload=${JSON.stringify(lastSelectionPayload)}`
);

await bulkFiltered(false);
check(
  "(7b) Deselect all filtered calls POST with selected=false",
  lastSelectionPayload && lastSelectionPayload.selected === false,
  `payload=${JSON.stringify(lastSelectionPayload)}`
);

console.log("\nScenario 8: Pagination controls");
resetApi();
appState.areasLimit = 1;
appState.areasOffset = 0;
await loadAreas();
check(
  "(8a) Next button enabled when more pages exist",
  areasNext.disabled === false,
  `disabled=${areasNext.disabled}`
);
check(
  "(8b) Prev button disabled on first page",
  areasPrev.disabled === true,
  `disabled=${areasPrev.disabled}`
);
console.log("\nScenario 9: i18n key parity and wording");
check(
  "(9a) areas_no_data in PT is 'Nenhuma área disponível'",
  tr.pt.areas_no_data === "Nenhuma área disponível",
  `got "${tr.pt.areas_no_data}"`
);
check(
  "(9b) areas_no_data in EN is 'No areas available'",
  tr.en.areas_no_data === "No areas available",
  `got "${tr.en.areas_no_data}"`
);
check(
  "(9c) areas_no_match in PT is 'Nenhuma área corresponde aos filtros'",
  tr.pt.areas_no_match === "Nenhuma área corresponde aos filtros",
  `got "${tr.pt.areas_no_match}"`
);
check(
  "(9d) areas_no_match in EN is 'No areas match the filters'",
  tr.en.areas_no_match === "No areas match the filters",
  `got "${tr.en.areas_no_match}"`
);

console.log("\nScenario 10: Keyboard behavior invariants");
check(
  "(10a) Table rows have no row-level click or Enter keydown bindings",
  !/\$\(["']#areas-body["']\)[^;]*?\.addEventListener\(["'](?:click|keydown)["']/.test(source) &&
    !/\.area-label[^;]*?\.addEventListener\(["'](?:click|keydown)["']/.test(source),
  "table body / row labels should not bind row-level click/Enter"
);
check(
  "(10b) Checkbox is native input with label.check",
  /<label class=["']check area-label["']><input class=["']area-checkbox["'] type=["']checkbox["']/.test(source),
  "checkboxes should use native input inside label.check"
);

if (failures > 0) {
  console.error(`\nSCENARIO FAILED: ${failures} check(s)`);
  process.exit(1);
} else {
  console.log("\nAll scenarios green");
}
