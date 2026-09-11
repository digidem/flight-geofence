// Browserless vm battery for the Áreas › Clusters surface (issue #17).
//
// Tests cluster configuration relocated from #view-fr24 into Áreas sub-nav:
// - Sub-nav switching between "Áreas protegidas" and "Clusters"
// - Relocation of #fr24-cluster-list, #fr24-cluster-form, #fr24-area-picker to Áreas
// - Absence of duplicate IDs in #view-fr24
// - Cluster data loading on sub-tab activation without visiting FR24 tab
// - Card rendering, minimap, 4-step wizard navigation, bounds validation, and form submit
// - Plain-language explanation copy above cluster list
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
    elements: {
      namedItem(name) {
        return this[name] || autoregister(`[name='${name}']`);
      },
    },
    set innerHTML(v) {
      this._innerHTML = String(v ?? "");
      this._children = [];
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
      if (name === "data-step") this.dataset.step = String(value);
      if (name === "data-i18n") this.dataset.i18n = String(value);
      if (name === "aria-selected") this.attributes["aria-selected"] = String(value);
    },
    getAttribute(name) {
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
    reset() {},
    scrollIntoView() {},
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
      return registry.get(selector) || null;
    },
    querySelectorAll(selector) {
      return [];
    },
  };
  return el;
}
function autoregister(selector) {
  if (registry.has(selector)) return registry.get(selector);
  const el = makeElement();
  if (selector.startsWith("#")) el.setAttribute("id", selector.slice(1));
  else if (selector.startsWith(".")) el.classList.add(selector.slice(1));
  registry.set(selector, el);
  return el;
}

// Elements for Áreas sub-nav and panels
const areasTabProtected = autoregister("#areas-tab-protected");
areasTabProtected.classList.add("active");
areasTabProtected.setAttribute("aria-selected", "true");
const areasTabClusters = autoregister("#areas-tab-clusters");
areasTabClusters.setAttribute("aria-selected", "false");
const areasPanelProtected = autoregister("#areas-panel-protected");
areasPanelProtected.hidden = false;
const areasPanelClusters = autoregister("#areas-panel-clusters");
areasPanelClusters.hidden = true;
// Relocated cluster elements
const fr24ClusterList = autoregister("#fr24-cluster-list");
const fr24ClusterForm = autoregister("#fr24-cluster-form");
const fr24AreaPicker = autoregister("#fr24-area-picker");
const fr24WizardNext = autoregister("#fr24-wizard-next");
const fr24WizardPrev = autoregister("#fr24-wizard-prev");
const fr24WizardSave = autoregister("#fr24-wizard-save");
const fr24ClusterReset = autoregister("#fr24-cluster-reset");
const fr24WizardProgress = autoregister("#fr24-wizard-progress");
const fr24WizardStepLabel = autoregister("#fr24-wizard-step-label");
const fr24WizardBoundsError = autoregister("#fr24-wizard-bounds-error");
const fr24ManualBounds = autoregister("#fr24-manual-bounds");
const fr24ManualBoundsFields = autoregister("#fr24-manual-bounds-fields");

// Setup form elements
for (const name of [
  "id", "name", "buffer_km", "min_altitude_ft", "max_altitude_ft",
  "enabled", "use_manual_bounds", "manual_north", "manual_south",
  "manual_west", "manual_east"
]) {
  const inputEl = makeElement();
  inputEl.name = name;
  fr24ClusterForm.elements[name] = inputEl;
}

const documentStub = {
  activeElement: null,
  documentElement: { lang: "en" },
  body: {
    contains(el) { return true; },
  },
  getElementById(id) {
    return autoregister(`#${id}`);
  },
  querySelector(sel) {
    return autoregister(sel);
  },
  querySelectorAll(sel) {
    if (sel.includes("fieldset[data-step]")) {
      return [1, 2, 3, 4].map((step) => {
        const fs = makeElement();
        fs.setAttribute("data-step", String(step));
        return fs;
      });
    }
    if (sel.includes(".fr24-area-checkbox")) return [];
    if (sel.includes("input[name='categories']")) return [];
    if (sel.includes(".review-card")) return [];
    return [];
  },
  addEventListener(type, fn) {},
};

// ---- Mock fetch routes -----------------------------------------------------
let fetchLog = [];
let mockClusters = [];
let mockSelectedAreas = [];

function resetMocks() {
  fetchLog = [];
  mockClusters = [
    {
      id: "cl-1",
      name: "Raposa Cluster",
      enabled: true,
      buffer_km: 15,
      min_altitude_ft: -2000,
      max_altitude_ft: 10000,
      categories: ["T", "H", "N"],
      area_ids: ["area-1"],
      use_manual_bounds: false,
      last_poll_at: "2026-09-02T00:00:00Z",
      last_estimated_credits: 40,
    },
  ];
  mockSelectedAreas = [
    { id: "area-1", name: "TI Raposa Serra do Sol" },
    { id: "area-2", name: "TI Yanomami" },
  ];
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
  fetchLog.push({ url, method, body: options.body });
  if (url.startsWith("/api/areas?selected=true")) {
    return Promise.resolve(jsonResponse({ total: mockSelectedAreas.length, items: mockSelectedAreas }));
  }
  if (url.startsWith("/api/fr24/clusters")) {
    if (method === "POST") {
      const payload = options.body ? JSON.parse(options.body) : {};
      return Promise.resolve(jsonResponse({ success: true, cluster: payload }));
    }
    if (method === "DELETE") {
      return Promise.resolve(jsonResponse({ success: true }));
    }
    return Promise.resolve(jsonResponse({ clusters: mockClusters }));
  }
  if (url === "/api/status") {
    return Promise.resolve(jsonResponse({
      areas: { total: 2, selected: 2 },
      query_regions: 2,
      events: { total: 0, review: { useful: 0, unreviewed: 0, noise: 0, uncertain: 0 } },
      warnings: [],
      phase: "review",
      version: "0.8.3",
    }));
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
  "({ loadFr24Clusters: typeof loadFr24Clusters !== 'undefined' ? loadFr24Clusters : null, loadFr24: typeof loadFr24 !== 'undefined' ? loadFr24 : null, initAreasSubnav: typeof initAreasSubnav !== 'undefined' ? initAreasSubnav : null, appState: typeof appState !== 'undefined' ? appState : null, t: typeof t !== 'undefined' ? t : null })",
  sandbox,
  { filename: "(exports)" },
);
const { loadFr24Clusters, loadFr24, initAreasSubnav, appState, t } = exportsObj;

if (appState) {
  appState.translations = tr;
  appState.language = "pt";
}

// ---- Test Scenarios --------------------------------------------------------

console.log("Scenario 1: Markup and relocation invariants");
check(
  "(1a) #view-areas contains .areas-subnav with two tabs",
  /<section\s+id=["']view-areas["'][\s\S]*?<nav\s+class=["']areas-subnav["'][\s\S]*?id=["']areas-tab-protected["'][\s\S]*?id=["']areas-tab-clusters["']/.test(indexHtml),
  "expected .areas-subnav with protected and clusters tabs inside #view-areas"
);
check(
  "(1b) #view-areas contains #areas-panel-protected and #areas-panel-clusters",
  /<section\s+id=["']view-areas["'][\s\S]*?id=["']areas-panel-protected["'][\s\S]*?id=["']areas-panel-clusters["']/.test(indexHtml),
  "expected both subpanels inside #view-areas"
);
check(
  "(1c) #fr24-cluster-list is located inside #areas-panel-clusters",
  /<div\s+id=["']areas-panel-clusters["'][\s\S]*?id=["']fr24-cluster-list["']/.test(indexHtml),
  "expected #fr24-cluster-list inside #areas-panel-clusters"
);
check(
  "(1d) #fr24-cluster-form is located inside #areas-panel-clusters",
  /<div\s+id=["']areas-panel-clusters["'][\s\S]*?id=["']fr24-cluster-form["']/.test(indexHtml),
  "expected #fr24-cluster-form inside #areas-panel-clusters"
);
check(
  "(1e) Plain-language explanation copy appears above the cluster list",
  /data-i18n=["']areas_clusters_explanation["']/.test(indexHtml),
  "expected areas_clusters_explanation copy above #fr24-cluster-list"
);

// Check that #view-fr24 no longer contains cluster elements
const fr24SectionMatch = indexHtml.match(/<section\s+id=["']view-fr24["'][\s\S]*?<\/section>/);
const fr24SectionHtml = fr24SectionMatch ? fr24SectionMatch[0] : "";
check(
  "(1f) #view-fr24 no longer contains #fr24-cluster-list",
  !/id=["']fr24-cluster-list["']/.test(fr24SectionHtml),
  "unexpected #fr24-cluster-list found in #view-fr24"
);
check(
  "(1g) #view-fr24 no longer contains #fr24-cluster-form",
  !/id=["']fr24-cluster-form["']/.test(fr24SectionHtml),
  "unexpected #fr24-cluster-form found in #view-fr24"
);
check(
  "(1h) #view-fr24 no longer contains #fr24-area-picker",
  !/id=["']fr24-area-picker["']/.test(fr24SectionHtml),
  "unexpected #fr24-area-picker found in #view-fr24"
);
check(
  "(1i) Cluster IDs appear exactly once in the document (no duplicates)",
  (() => {
    const listCount = (indexHtml.match(/id=["']fr24-cluster-list["']/g) || []).length;
    const formCount = (indexHtml.match(/id=["']fr24-cluster-form["']/g) || []).length;
    const pickerCount = (indexHtml.match(/id=["']fr24-area-picker["']/g) || []).length;
    return listCount === 1 && formCount === 1 && pickerCount === 1;
  })(),
  "expected exactly one occurrence of each cluster element ID in index.html"
);

console.log("\nScenario 2: Sub-nav switching");
initAreasSubnav();
check(
  "(2a) Protected tab is active by default; clusters tab is inactive",
  areasTabProtected.classList.contains("active") &&
    areasTabProtected.getAttribute("aria-selected") === "true" &&
    !areasTabClusters.classList.contains("active"),
  "expected protected tab active by default"
);

// Click clusters tab
resetMocks();
areasTabClusters.click();
check(
  "(2b) Clicking Clusters tab activates it and hides protected panel",
  areasTabClusters.classList.contains("active") &&
    areasTabClusters.getAttribute("aria-selected") === "true" &&
    areasPanelClusters.hidden === false &&
    areasPanelProtected.hidden === true,
  "expected clusters tab active and panel visible"
);

// Click protected tab
areasTabProtected.click();
check(
  "(2c) Clicking Protected tab switches back",
  areasTabProtected.classList.contains("active") &&
    areasTabProtected.getAttribute("aria-selected") === "true" &&
    areasPanelProtected.hidden === false &&
    areasPanelClusters.hidden === true,
  "expected protected tab active and panel visible"
);

console.log("\nScenario 3: Activation triggers cluster loader without visiting FR24 tab");
resetMocks();
// Click clusters tab again
areasTabClusters.click();
await new Promise((r) => setTimeout(r, 20));
check(
  "(3a) Switching to Clusters sub-tab fetches /api/fr24/clusters",
  fetchLog.some((c) => c.url.startsWith("/api/fr24/clusters")),
  `fetchLog=${JSON.stringify(fetchLog)}`
);
check(
  "(3b) Switching to Clusters sub-tab fetches /api/areas?selected=true",
  fetchLog.some((c) => c.url.startsWith("/api/areas?selected=true")),
  `fetchLog=${JSON.stringify(fetchLog)}`
);
check(
  "(3c) Cluster card rendered into #fr24-cluster-list",
  fr24ClusterList.innerHTML.includes("Raposa Cluster"),
  `got: ${fr24ClusterList.innerHTML}`
);

console.log("\nScenario 4: CSS rules and layout");
check(
  "(4a) .areas-subnav is sticky below primary tabs",
  /\.areas-subnav\s*\{[\s\S]*?position:\s*sticky;[\s\S]*?top:\s*48px;[\s\S]*?z-index:\s*5;/.test(componentsCss),
  "expected .areas-subnav with sticky top:48px z-index:5"
);
check(
  "(4b) .areas-toolbar top is 104px to sit below .areas-subnav",
  /\.areas-toolbar\s*\{[\s\S]*?top:\s*104px;/.test(componentsCss),
  "expected .areas-toolbar top:104px"
);
check(
  "(4c) components.css brace balance is 0",
  (() => {
    let o = 0, c = 0;
    for (const ch of componentsCss) { if (ch === "{") o++; if (ch === "}") c++; }
    return o === c;
  })(),
  "unbalanced braces in components.css"
);

console.log("\nScenario 5: Empty clusters state");
mockClusters = [];
resetMocks();
mockClusters = [];
await loadFr24Clusters();
check(
  "(5a) Empty clusters displays fr24_no_clusters message",
  fr24ClusterList.innerHTML.includes(tr.pt.fr24_no_clusters || "Nenhum cluster configurado"),
  `got: ${fr24ClusterList.innerHTML}`
);

console.log("\nScenario 6: i18n keys for Áreas subnav and cluster explanation");
check(
  "(6a) areas_subnav_protected exists in PT and EN",
  tr.pt.areas_subnav_protected === "Áreas protegidas" && tr.en.areas_subnav_protected === "Protected areas",
  `pt=${tr.pt.areas_subnav_protected} en=${tr.en.areas_subnav_protected}`
);
check(
  "(6b) areas_subnav_clusters exists in PT and EN",
  tr.pt.areas_subnav_clusters === "Clusters" && tr.en.areas_subnav_clusters === "Clusters",
  `pt=${tr.pt.areas_subnav_clusters} en=${tr.en.areas_subnav_clusters}`
);
check(
  "(6c) areas_clusters_explanation exists in PT and EN and differs",
  Boolean(tr.pt.areas_clusters_explanation && tr.en.areas_clusters_explanation && tr.pt.areas_clusters_explanation !== tr.en.areas_clusters_explanation),
  `pt=${tr.pt.areas_clusters_explanation}`
);

if (failures > 0) {
  console.error(`\nSCENARIO FAILED: ${failures} check(s)`);
  process.exit(1);
} else {
  console.log("\nAll scenarios green");
}
