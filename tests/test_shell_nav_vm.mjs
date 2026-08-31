// Browserless vm battery for the global shell + primary navigation in app.js.
//
// Mirrors the pattern in tests/test_fr24_track_panel_vm.mjs: read the real
// `app/static/app.js` source, run it under a node `vm` context with a DOM
// stub built from the real `app/static/index.html` markup, then drive the
// primary-tab click handler and keydown wiring against the spec in
// GitHub issue #13.
//
// Exit code 0 = every scenario green; failures print SCENARIO FAILED lines.

import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const APP_JS = path.join(ROOT, "app", "static", "app.js");
const INDEX_HTML = path.join(ROOT, "app", "static", "index.html");
const I18N_PY = path.join(ROOT, "app", "i18n.py");

const source = fs.readFileSync(APP_JS, "utf8");
const indexHtml = fs.readFileSync(INDEX_HTML, "utf8");
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

// Lightweight i18n extractor — only the nav keys, no Python needed.
function extractNavLabels(sourceText) {
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

const tr = extractNavLabels(i18nSource);

// Parse primary tabs from the static HTML. Use \w+ so "fr24" matches (it has
// digits). The attribute order varies between buttons, so don't anchor on
// `class=…` first.
const tabRegex = /<button\b[^>]*\bdata-view="(\w+)"[^>]*\bdata-i18n="([\w]+)"[^>]*>/g;
const tabs = [];
for (const m of indexHtml.matchAll(tabRegex)) {
  tabs.push({ dataView: m[1], dataI18n: m[2] });
}

const expectedViews = ["dashboard", "events", "areas", "settings", "fr24", "logs"];
const expectedI18n = [
  "nav_dashboard",
  "nav_events",
  "nav_areas",
  "nav_settings",
  "nav_fr24",
  "nav_logs",
];

// ---- Scenario 1: markup invariants ----------------------------------------

console.log("\nScenario 1: markup invariants");
check(
  "(1a) exactly six primary tabs in target order",
  tabs.length === expectedViews.length &&
    tabs.every((tab, i) => tab.dataView === expectedViews[i]),
  `got ${JSON.stringify(tabs.map((t) => t.dataView))}`,
);
check(
  "(1b) tab data-i18n keys match expected set/order",
  tabs.every((tab, i) => tab.dataI18n === expectedI18n[i]),
  `got ${JSON.stringify(tabs.map((t) => t.dataI18n))}`,
);

const idRegex = /<button[^>]*\bid="(tab-[\w-]+)"[^>]*\bclass="tab\b/g;
const tabIds = [...indexHtml.matchAll(idRegex)].map((m) => m[1]);
check(
  "(1c) tab ids match expected set",
  tabIds.length === 6 &&
    tabIds.includes("tab-dashboard") &&
    tabIds.includes("tab-events") &&
    tabIds.includes("tab-areas") &&
    tabIds.includes("tab-settings") &&
    tabIds.includes("tab-fr24") &&
    tabIds.includes("tab-logs"),
  `got ${JSON.stringify(tabIds)}`,
);

// ---- Scenario 2: i18n coverage ---------------------------------------------

console.log("\nScenario 2: i18n coverage");
const expectedLabels = {
  pt: {
    nav_dashboard: "Monitoramento",
    nav_events: "Eventos",
    nav_areas: "Áreas",
    nav_settings: "Configurações",
  },
  en: {
    nav_dashboard: "Monitoring",
    nav_events: "Events",
    nav_areas: "Areas",
    nav_settings: "Settings",
  },
};
for (const lang of ["pt", "en"]) {
  for (const [key, want] of Object.entries(expectedLabels[lang])) {
    const got = tr[lang][key];
    check(
      `(2) i18n[${lang}][${key}] === ${JSON.stringify(want)}`,
      got === want,
      `got ${JSON.stringify(got)}`,
    );
  }
}

// ---- DOM stub --------------------------------------------------------------

const registry = new Map();

function makeElement() {
  const el = {
    tagName: "DIV",
    dataset: {},
    attributes: {},
    listeners: {},
    hidden: false,
    textContent: "",
    innerHTML: "",
    classList: {
      _set: new Set(),
      add(c) {
        this._set.add(c);
      },
      remove(c) {
        this._set.delete(c);
      },
      toggle(c, on) {
        if (on === undefined) {
          if (this._set.has(c)) this._set.delete(c);
          else this._set.add(c);
        } else if (on) this._set.add(c);
        else this._set.delete(c);
      },
      contains(c) {
        return this._set.has(c);
      },
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
      if (name === "data-view") this.dataset.view = String(value);
      else if (name === "data-i18n") this.dataset.i18n = String(value);
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
    focus() {
      documentStub.activeElement = this;
    },
    blur() {
      if (documentStub.activeElement === this) documentStub.activeElement = null;
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
  };
  return el;
}

function autoregister(selector) {
  if (registry.has(selector)) return registry.get(selector);
  const el = makeElement();
  if (selector.startsWith("#")) el.setAttribute("id", selector.slice(1));
  registry.set(selector, el);
  return el;
}
function matchSelector(el, selector) {
  if (!el) return false;
  const tmpl = selector.match(/^([a-z]+)\.tab\[data-view="([\w]+)"\]$/);
  if (tmpl) {
    const [, tag, view] = tmpl;
    if (el.tagName.toLowerCase() !== tag) return false;
    if (!el.classList.contains("tab")) return false;
    return el.dataset.view === view;
  }
  if (selector === ".tab") return el.classList.contains("tab");
  if (selector === ".tab.active")
    return el.classList.contains("tab") && el.classList.contains("active");
  if (selector === ".view") return el.classList.contains("view");
  if (selector === ".view.active")
    return el.classList.contains("view") && el.classList.contains("active");
  // Generic class selector: match the first token after the dot against any
  // class on the element. Sufficient for this harness (we only use .tab,
  // .view, .skip-link in assertions).
  const classMatch = selector.match(/^\.([a-z][\w-]*)$/);
  if (classMatch) return el.classList.contains(classMatch[1]);
  if (selector.startsWith("#")) return el.attributes.id === selector.slice(1);
  return false;
}

const skipLink = autoregister(".skip-link");
skipLink.classList.add("skip-link");

const tabEls = tabs.map((tab) => {
  const el = autoregister(`#tab-${tab.dataView}`);
  el.tagName = "BUTTON";
  el.setAttribute("id", `tab-${tab.dataView}`);
  el.setAttribute("data-view", tab.dataView);
  el.setAttribute("data-i18n", tab.dataI18n);
  el.setAttribute("aria-controls", `view-${tab.dataView}`);
  el.setAttribute("role", "tab");
  el.classList.add("tab");
  if (tab.dataView === "dashboard") {
    el.classList.add("active");
    el.setAttribute("aria-selected", "true");
  } else {
    el.setAttribute("aria-selected", "false");
  }
  return el;
});

const viewEls = tabs.map((tab) => {
  const el = autoregister(`#view-${tab.dataView}`);
  el.tagName = "SECTION";
  el.setAttribute("id", `view-${tab.dataView}`);
  el.setAttribute("role", "tabpanel");
  el.classList.add("view");
  if (tab.dataView === "dashboard") el.classList.add("active");
  return el;
});

const documentStub = {
  activeElement: null,
  addEventListener() {},
  removeEventListener() {},
  documentElement: { lang: "en", _lang: "en", set lang(v) { this._lang = v; }, get lang() { return this._lang; } },
  querySelector(selector) {
    if (selector.startsWith("#")) return autoregister(selector);
    for (const el of registry.values()) if (matchSelector(el, selector)) return el;
    return null;
  },
  querySelectorAll(selector) {
    if (selector.startsWith("#")) return [autoregister(selector)];
    return [...registry.values()].filter((el) => matchSelector(el, selector));
  },
  getElementById(id) {
    return autoregister(`#${id}`);
  },
};

const sandbox = {
  document: documentStub,
  window: {
    location: { hash: "" },
    addEventListener() {},
    removeEventListener() {},
  },
  fetch: async () => ({ ok: false, json: async () => ({}) }),
  console,
  Date,
  Math,
  Set,
  Map,
  Promise,
  JSON,
  Object,
  Array,
  Number,
  String,
  Error,
  URLSearchParams,
  URL,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
  Node: { TEXT_NODE: 3, ELEMENT_NODE: 1 },
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: "app.js" });

// Expose `t` and `appState` to the host. Script-level `const` declarations
// in the vm context don't appear on the sandbox object; pull them through a
// second snippet.
const exports6 = vm.runInContext(
  "({ t: t, appState: appState })",
  sandbox,
  { filename: "(exports)" },
);
const t = exports6.t;
const appState = exports6.appState;

const tick = () => new Promise((r) => setTimeout(r, 0));
const settle = async () => {
  for (let i = 0; i < 8; i += 1) await tick();
};

// ---- Scenario 3: skip-link on activation ----------------------------------

console.log("\nScenario 3: skip-link updates on tab activation");

for (const tab of tabEls) {
  tab.click();
  await settle();
  const got = skipLink.getAttribute("href");
  check(
    `(3) skip-link after click ${tab.dataset.view}`,
    got === `#view-${tab.dataset.view}`,
    `got ${JSON.stringify(got)}`,
  );
}

// ---- Scenario 4: skip-link initial state -----------------------------------

console.log("\nScenario 4: skip-link initial state from index.html");
check(
  "(4) skip-link href is #view-dashboard in static HTML",
  indexHtml.includes('class="skip-link" href="#view-dashboard"'),
);

// ---- Scenario 5: Home/End keys ---------------------------------------------

console.log("\nScenario 5: Home/End keys");

tabEls[0].focus();
tabEls[0].dispatch("keydown", { key: "End" });
await settle();
const lastFocused = documentStub.activeElement;
check(
  "(5a) End focuses last primary tab",
  lastFocused && lastFocused.dataset && lastFocused.dataset.view === "logs",
  `got ${lastFocused?.dataset?.view ?? "null"}`,
);

documentStub.activeElement = tabEls[tabEls.length - 1];
tabEls[tabEls.length - 1].dispatch("keydown", { key: "Home" });
await settle();
const firstFocused = documentStub.activeElement;
check(
  "(5b) Home focuses first primary tab",
  firstFocused && firstFocused.dataset && firstFocused.dataset.view === "dashboard",
  `got ${firstFocused?.dataset?.view ?? "null"}`,
);

// ---- Scenario 6: palette key resolution -----------------------------------

console.log("\nScenario 6: palette key resolution");

if (!t || !appState) {
  check("(6) sandbox exposes t() and appState", false, "missing");
} else {
  appState.translations = tr;
  const cases = [
    ["nav_dashboard", expectedLabels.pt.nav_dashboard, expectedLabels.en.nav_dashboard],
    ["nav_areas", expectedLabels.pt.nav_areas, expectedLabels.en.nav_areas],
    ["nav_events", expectedLabels.pt.nav_events, expectedLabels.en.nav_events],
    ["nav_settings", expectedLabels.pt.nav_settings, expectedLabels.en.nav_settings],
  ];
  for (const [key, want_pt, want_en] of cases) {
    appState.language = "pt";
    const ptVal = t(key);
    appState.language = "en";
    const enVal = t(key);
    check(
      `(6a) t("${key}", "pt") !== key string (no missing-key leak)`,
      ptVal !== key,
      `got ${JSON.stringify(ptVal)}`,
    );
    check(
      `(6b) t("${key}", "pt") === ${JSON.stringify(want_pt)}`,
      ptVal === want_pt,
      `got ${JSON.stringify(ptVal)}`,
    );
    check(
      `(6c) t("${key}", "en") === ${JSON.stringify(want_en)}`,
      enVal === want_en,
      `got ${JSON.stringify(enVal)}`,
    );
    check(
      `(6d) PT and EN values differ for ${key}`,
      ptVal !== enVal,
      `both ${JSON.stringify(ptVal)}`,
    );
  }
}

if (failures > 0) {
  console.error(`\nSCENARIO FAILED: ${failures} check(s)`);
  process.exit(1);
} else {
  console.log("\nAll scenarios green");
}
