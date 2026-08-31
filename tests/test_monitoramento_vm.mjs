// Browserless vm battery for the Monitoramento surface (issue #14).
//
// Mirrors tests/test_shell_nav_vm.mjs: read the real `app/static/app.js`,
// run under node `vm` with a DOM stub built from `app/static/index.html`,
// then drive `loadMonitoramento()`, `openEvents(filter)`, and the tab/refresh
// handlers against the spec.
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

// Lightweight i18n extractor — uses [a-z_0-9]+ so keys with digits (fr24) match.
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
    textContent: "",
    innerHTML: "",
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
    focus() { documentStub.activeElement = this; },
    blur() { if (documentStub.activeElement === this) documentStub.activeElement = null; },
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
  const classMatch = selector.match(/^\.([a-z][\w-]*)$/);
  if (classMatch) return el.classList.contains(classMatch[1]);
  if (selector.startsWith("#")) return el.attributes.id === selector.slice(1);
  return false;
}

const tabIds = ["dashboard", "events", "areas", "settings", "fr24", "logs"];
const tabs = tabIds.map((v) => {
  const el = autoregister(`#tab-${v}`);
  el.tagName = "BUTTON";
  el.setAttribute("id", `tab-${v}`);
  el.setAttribute("data-view", v);
  el.setAttribute("role", "tab");
  el.classList.add("tab");
  if (v === "dashboard") {
    el.classList.add("active");
    el.setAttribute("aria-selected", "true");
  } else {
    el.setAttribute("aria-selected", "false");
  }
  return el;
});

for (const v of tabIds) {
  const vEl = autoregister(`#view-${v}`);
  vEl.tagName = "SECTION";
  vEl.setAttribute("id", `view-${v}`);
  vEl.setAttribute("role", "tabpanel");
  vEl.classList.add("view");
  if (v === "dashboard") vEl.classList.add("active");
}

autoregister("#dashboard-events");
const map = autoregister("#monitoramento-map");
map.setAttribute("role", "img");
const mapEmpty = autoregister("#monitoramento-map-empty");
const recent = autoregister("#monitoramento-recent-events");
const attentionBtn = autoregister("#monitoramento-attention-btn");
const attentionCount = autoregister("#monitoramento-attention-count");
const fr24Tiles = autoregister("#monitoramento-fr24-tiles");
const fr24Blockers = autoregister("#monitoramento-fr24-blockers");
const fr24Details = autoregister("#monitoramento-fr24-details");
fr24Details.setAttribute("href", "#tab-fr24");
const viewAllBtn = autoregister("#monitoramento-view-all-events");
const reviewFilter = autoregister("#review-filter");
reviewFilter.tagName = "SELECT";
const refresh = autoregister("#refresh");
const syncNow = autoregister("#sync-now");
const pollNow = autoregister("#poll-now");
const testEmail = autoregister("#test-email");
const langToggle = autoregister("#lang-toggle");
const loginForm = autoregister("#login-form");
const loginError = autoregister("#login-error");
const phaseBadge = autoregister("#phase-badge");
const versionBadge = autoregister("#version-badge");
const warnings = autoregister("#warnings");
const metrics = autoregister("#metrics");
const actionResult = autoregister("#action-result");
const settingsLanguage = autoregister("#settings-language");

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

const fetchCalls = new Map();
function fakeFetch(url, options = {}) {
  const key = `${options.method || "GET"} ${url}`;
  fetchCalls.set(key, (fetchCalls.get(key) || 0) + 1);
  if (fakeFetch.route) {
    const route = fakeFetch.route(url, options);
    if (route) return Promise.resolve(route);
  }
  return Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({}),
    text: async () => "",
  });
}

const sandbox = {
  document: documentStub,
  window: {
    location: { hash: "" },
    addEventListener() {},
    removeEventListener() {},
  },
  fetch: fakeFetch,
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

const exports6 = vm.runInContext(
  "({ loadStatus: loadStatus, loadMonitoramento: loadMonitoramento, openEvents: openEvents, appState: appState })",
  sandbox,
  { filename: "(exports)" },
);
const { loadStatus, loadMonitoramento, openEvents, appState } = exports6;

const tick = () => new Promise((r) => setTimeout(r, 0));
const settle = async () => { for (let i = 0; i < 8; i += 1) await tick(); };

// ---- Fixtures ---------------------------------------------------------------
function makeStatusPayload(unreviewed = 3) {
  return {
    phase: "review",
    version: "0.8.3",
    areas: { selected: 12, total: 47 },
    query_regions: 8,
    estimated_requests_per_day: 350,
    latest_sync: { completed_at: "2026-08-30T15:00:00Z", success: true },
    latest_poll: { completed_at: "2026-08-30T15:30:00Z", success: true },
    active_states: 18,
    events: {
      total: 42,
      review: { unreviewed, useful: 5, noise: 2, uncertain: 1 },
    },
    providers: [],
    warnings: ["Limites oficiais ainda não sincronizados."],
  };
}

function makeEventsPayload(count = 3) {
  const out = [];
  for (let i = 0; i < count; i += 1) {
    out.push({
      id: `evt-${i}`,
      occurred_at: new Date(Date.now() - i * 3600_000).toISOString(),
      event_type: "PROBABLE_STOP",
      aircraft_hex: `AABB${i.toString(16).padStart(2, "0").toUpperCase()}`,
      callsign: `TST${i}`,
      registration: `PT-TST${i}`,
      aircraft_type: "C172",
      area_names: ["Area X"],
      altitude_ft: 3500,
      ground_speed_kt: 95,
      phase: "review",
      review_status: ["unreviewed", "useful", "noise", "uncertain"][i % 4],
      latitude: -15 + i,
      longitude: -55 + i,
    });
  }
  return out;
}

// /api/fr24/status payload matches the real endpoint at app/main.py:924.
// Field names: credits_used_this_cycle, operating_budget, budget_state,
// projected_end_of_cycle_credits, billing_cycle_id, blockers, enabled.
function makeFr24StatusPayload(overrides = {}) {
  return {
    enabled: true,
    credits_used_this_cycle: 23,
    operating_budget: 200,
    billing_cycle_id: "2026-08",
    budget_state: "active",
    projected_end_of_cycle_credits: 80,
    all_empty_baseline: 12,
    active_clusters: 1,
    max_active_clusters: 2,
    latest_poll: { success: true, completed_at: "2026-08-30T15:30:00Z" },
    api_key_configured: true,
    api_key_source: "env",
    blockers: [],
    ...overrides,
  };
}

// /api/fr24/clusters payload: each cluster has use_manual_bounds +
// manual_* / calc_* fields (NOT a top-level `bounds`), plus
// coverage_geojson. fr24ClusterNumericBounds() reads use_manual_bounds.
function makeFr24ClustersPayload() {
  return {
    clusters: [
      {
        name: "Cluster A",
        use_manual_bounds: false,
        manual_north: null,
        manual_south: null,
        manual_west: null,
        manual_east: null,
        calc_north: -14,
        calc_south: -16,
        calc_west: -56,
        calc_east: -54,
        coverage_geojson: {
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              properties: { role: "area", name: "TI X" },
              geometry: {
                type: "Polygon",
                coordinates: [[[-55.5, -15.5], [-55.0, -15.5], [-55.0, -15.0], [-55.5, -15.0], [-55.5, -15.5]]],
              },
            },
          ],
        },
      },
    ],
  };
}

function configureDefaultRoutes() {
  fetchCalls.clear();
  fakeFetch.route = (url, options) => {
    const method = options.method || "GET";
    if (method === "GET" && url === "/api/status") {
      return { ok: true, json: async () => makeStatusPayload() };
    }
    if (method === "GET" && url.startsWith("/api/events")) {
      return { ok: true, json: async () => ({ events: makeEventsPayload() }) };
    }
    if (method === "GET" && url === "/api/fr24/status") {
      return { ok: true, json: async () => makeFr24StatusPayload() };
    }
    if (method === "GET" && url === "/api/fr24/clusters") {
      return { ok: true, json: async () => makeFr24ClustersPayload() };
    }
    return null;
  };
}

// ---- Scenario 1: markup invariants -----------------------------------------

console.log("\nScenario 1: markup invariants");
check("(1a) #view-dashboard present", indexHtml.includes('id="view-dashboard"'));
check("(1b) #monitoramento-map present", indexHtml.includes('id="monitoramento-map"'));
check("(1c) #monitoramento-attention-btn present", indexHtml.includes('id="monitoramento-attention-btn"'));
check("(1d) #monitoramento-recent-events present", indexHtml.includes('id="monitoramento-recent-events"'));
check("(1e) #monitoramento-fr24-tiles present", indexHtml.includes('id="monitoramento-fr24-tiles"'));
check(
  "(1f) manual sync / poll / test-email / refresh still present",
  indexHtml.includes('id="sync-now"') &&
    indexHtml.includes('id="poll-now"') &&
    indexHtml.includes('id="test-email"') &&
    indexHtml.includes('id="refresh"'),
);
check("(1g) old #dashboard-events tbody is gone from the body", !/<tbody[^>]*\bid="dashboard-events"/.test(indexHtml));

// ---- Scenario 2: loader composition ----------------------------------------

console.log("\nScenario 2: loadMonitoramento() composes the four endpoints");
configureDefaultRoutes();
(async () => {
  await loadMonitoramento();
  await settle();
  check(
    "(2a) exactly one /api/status request",
    fetchCalls.get("GET /api/status") === 1,
    `got ${fetchCalls.get("GET /api/status") || 0}`,
  );
  check(
    "(2b) exactly one /api/events?limit=100 request",
    fetchCalls.get("GET /api/events?limit=100") === 1,
    `got ${fetchCalls.get("GET /api/events?limit=100") || 0}`,
  );
  check(
    "(2c) exactly one /api/fr24/status request",
    fetchCalls.get("GET /api/fr24/status") === 1,
    `got ${fetchCalls.get("GET /api/fr24/status") || 0}`,
  );
  check(
    "(2d) exactly one /api/fr24/clusters request",
    fetchCalls.get("GET /api/fr24/clusters") === 1,
    `got ${fetchCalls.get("GET /api/fr24/clusters") || 0}`,
  );
})().then(async () => {
  await settle();

  // ---- Scenario 3: loadStatus() refactor ----------------------------------
  console.log("\nScenario 3: loadStatus() no longer fetches /api/events");
  configureDefaultRoutes();
  await loadStatus();
  await settle();
  check(
    "(3a) loadStatus alone does NOT call /api/events",
    !fetchCalls.has("GET /api/events?limit=100"),
    `unexpected fetch calls: ${[...fetchCalls.keys()].join(", ")}`,
  );
  check("(3b) loadStatus alone calls /api/status exactly once", fetchCalls.get("GET /api/status") === 1);

  // ---- Scenario 4: attention card ------------------------------------------
  console.log("\nScenario 4: attention card reads unreviewed count");
  configureDefaultRoutes();
  await loadMonitoramento();
  await settle();
  check(
    "(4a) attention-count reflects status.events.review.unreviewed",
    attentionCount.textContent === "3",
    `got ${JSON.stringify(attentionCount.textContent)}`,
  );

  // ---- Scenario 5: recent activity ----------------------------------------
  console.log("\nScenario 5: recent activity renders rows from eventRow()");
  check(
    "(5a) recent tbody renders callsigns TST0/TST1/TST2 from the same payload",
    recent.innerHTML.includes("TST0") && recent.innerHTML.includes("TST1") && recent.innerHTML.includes("TST2"),
    `got ${recent.innerHTML.length} bytes; first 200: ${recent.innerHTML.slice(0, 200)}`,
  );

  // ---- Scenario 6: map dots ------------------------------------------------
  console.log("\nScenario 6: map dots resolve from events with coords");
  check("(6a) map contains <svg>", map.innerHTML.includes("<svg"));
  check("(6b) map contains event-dot-* classes", /class="event-dot event-dot-/.test(map.innerHTML));
  check("(6c) map dots have aria-label", /aria-label="[^"]+"/.test(map.innerHTML), "no aria-label on dots");
  check("(6d) map dots have <title>", /<title>[^<]+<\/title>/.test(map.innerHTML));

  // ---- Scenario 6b: map dot lat/lng projection ----------------------------
  // Regression guard for the bug where cy was computed with px() instead of
  // py(). With the fixture, events at lat=-15, -14, -13 should produce cy
  // values spread across the map height (not collapsed to a single row).
  console.log("\nScenario 6b: map dot cy axis uses latitude (py), not longitude (px)");
  configureDefaultRoutes();
  await loadMonitoramento();
  await settle();
  const circles = [...map.innerHTML.matchAll(/<circle[^>]+cx="([\d.]+)"[^>]+cy="([\d.]+)"[^>]*>/g)];
  check(
    "(6b-i) three <circle> elements for three fixture events",
    circles.length === 3,
    `got ${circles.length}`,
  );
  if (circles.length === 3) {
    const cys = circles.map((m) => parseFloat(m[2])).sort((a, b) => a - b);
    const span = cys[2] - cys[0];
    check(
      "(6b-ii) cy values span the map height (lat-based projection)",
      span > 50,
      `cy span ${span.toFixed(2)} too small; latitude-based projection should spread dots across most of the map height`,
    );
  }

  // ---- Scenario 7: openEvents() race --------------------------------------
  console.log("\nScenario 7: openEvents(filter) sets filter before .click()");
  configureDefaultRoutes();
  reviewFilter.value = "";
  await openEvents("unreviewed");
  await settle();
  check(
    "(7a) review-filter.value === \"unreviewed\" after openEvents",
    reviewFilter.value === "unreviewed",
    `got ${JSON.stringify(reviewFilter.value)}`,
  );
  check("(7b) #tab-events is active after openEvents", tabs[1].classList.contains("active"));

  // ---- Scenario 7c: "Ver todos em Eventos" button wires to openEvents("") --
  console.log("\nScenario 7c: 'Ver todos em Eventos' button calls openEvents(\"\")");
  configureDefaultRoutes();
  reviewFilter.value = "unreviewed";
  viewAllBtn.click();
  await settle();
  check(
    "(7c) review-filter.value === \"\" after Ver todos em Eventos click",
    reviewFilter.value === "",
    `got ${JSON.stringify(reviewFilter.value)}`,
  );
  check("(7d) #tab-events is active after Ver todos em Eventos", tabs[1].classList.contains("active"));

  // ---- Scenario 8: refresh button uses loadMonitoramento -----------------
  console.log("\nScenario 8: #refresh calls loadMonitoramento, not loadStatus");
  configureDefaultRoutes();
  refresh.click();
  await settle();
  check(
    "(8a) #refresh triggers /api/events request (loadMonitoramento signature)",
    fetchCalls.has("GET /api/events?limit=100"),
    `got fetchCalls: ${[...fetchCalls.keys()].join(", ")}`,
  );

  // ---- Scenario 9: manual actions preserved ------------------------------
  console.log("\nScenario 9: manual sync/poll/test-email wired");
  let syncCalls = 0;
  fakeFetch.route = (url, options) => {
    if (url === "/api/boundaries/sync" && (options.method || "GET") === "POST") {
      syncCalls += 1;
      return { ok: true, json: async () => ({ status: "started" }) };
    }
    return null;
  };
  syncNow.click();
  await settle();
  check("(9a) #sync-now still wired to /api/boundaries/sync POST", syncCalls === 1, `got ${syncCalls}`);

  // ---- Scenario 10: map empty-state ---------------------------------------
  console.log("\nScenario 10: map empty-state when no clusters + no coords");
  configureDefaultRoutes();
  fakeFetch.route = (url, options) => {
    const method = options.method || "GET";
    if (method === "GET" && url === "/api/status") return { ok: true, json: async () => makeStatusPayload() };
    if (method === "GET" && url.startsWith("/api/events")) return { ok: true, json: async () => ({ events: [] }) };
    if (method === "GET" && url === "/api/fr24/status") return { ok: true, json: async () => makeFr24StatusPayload() };
    if (method === "GET" && url === "/api/fr24/clusters") return { ok: true, json: async () => ({ clusters: [] }) };
    return null;
  };
  await loadMonitoramento();
  await settle();
  check("(10a) #monitoramento-map-empty is shown when no clusters and no events", !mapEmpty.hidden, `hidden=${mapEmpty.hidden}`);
  check("(10b) map does not contain <svg>", !map.innerHTML.includes("<svg"));

  // ---- Scenario 11: FR24 details link -------------------------------------
  console.log("\nScenario 11: FR24 details link activates the FR24 tab");
  tabs[4].classList.remove("active");
  fr24Details.click();
  await settle();
  check("(11a) #tab-fr24 is active after clicking the FR24 details link", tabs[4].classList.contains("active"));

  // ---- Scenario 11b: FR24 summary reads the real /api/fr24/status fields -
  // regression guard for the BLOCKER where the renderer read credits_used /
  // budget / state, which the endpoint never returns (it returns
  // credits_used_this_cycle / operating_budget / budget_state).
  console.log("\nScenario 11b: FR24 summary reads real /api/fr24/status field names");
  configureDefaultRoutes();
  // Force blockers = ["budget_exhausted_paused"] so the assertion can verify
  // the renderer surfaces them through translateFr24Blocker.
  fakeFetch.route = (url, options) => {
    const method = options.method || "GET";
    if (method === "GET" && url === "/api/status") return { ok: true, json: async () => makeStatusPayload() };
    if (method === "GET" && url.startsWith("/api/events")) return { ok: true, json: async () => ({ events: makeEventsPayload() }) };
    if (method === "GET" && url === "/api/fr24/status") {
      return { ok: true, json: async () => makeFr24StatusPayload({
        credits_used_this_cycle: 187,
        operating_budget: 200,
        budget_state: "exhausted",
        billing_cycle_id: "2026-08",
        projected_end_of_cycle_credits: 240,
        blockers: ["budget_exhausted_paused"],
      }) };
    }
    if (method === "GET" && url === "/api/fr24/clusters") return { ok: true, json: async () => makeFr24ClustersPayload() };
    return null;
  };
  await loadMonitoramento();
  await settle();
  // The credits tile must reflect the real payload's credits_used_this_cycle
  // (not a permanent zero from the wrong field name).
  check(
    "(11b-i) FR24 credits tile shows 187 (credits_used_this_cycle, not 0)",
    fr24Tiles.innerHTML.includes("187"),
    `got ${fr24Tiles.innerHTML.slice(0, 300)}`,
  );
  check(
    "(11b-ii) FR24 percent rendered (187/200 → 94%)",
    fr24Tiles.innerHTML.includes("94%"),
    `got ${fr24Tiles.innerHTML.slice(0, 300)}`,
  );
  // The state tile should reflect the real budget_state (exhausted).
  check(
    "(11b-iii) FR24 state tile shows the i18n key for budget_state=exhausted",
    fr24Tiles.innerHTML.includes("Exhausted") || fr24Tiles.innerHTML.includes("exhausted"),
    `got ${fr24Tiles.innerHTML.slice(0, 300)}`,
  );
  // The blockers list renders through translateFr24Blocker.
  check(
    "(11b-iv) FR24 blockers list renders the translated blocker",
    fr24Blockers.innerHTML.includes("budget"),
    `got ${fr24Blockers.innerHTML.slice(0, 200)}`,
  );

  // ---- Scenario 7e: attention button click calls openEvents("unreviewed") -
  // regression guard for the round-1 dead-button class of bugs. The wire
  // is .onclick (not addEventListener), so the test invokes the click via
  // a synthetic event that triggers the same handler.
  console.log("\nScenario 7e: attention button click triggers openEvents(\"unreviewed\")");
  configureDefaultRoutes();
  // Move the dashboard tab to NOT active and ensure the events tab is not active.
  tabs[0].classList.remove("active");
  tabs[1].classList.remove("active");
  reviewFilter.value = "";
  // Invoke the renderer-assigned onclick directly (the only reliable way
  // without simulating addEventListener in the stub).
  if (typeof attentionBtn.onclick === "function") attentionBtn.onclick();
  await settle();
  check(
    "(7e-i) attention onclick activates #tab-events",
    tabs[1].classList.contains("active"),
    `events tab active=${tabs[1].classList.contains("active")}`,
  );
  check(
    "(7e-ii) attention onclick sets review-filter to 'unreviewed'",
    reviewFilter.value === "unreviewed",
    `got ${JSON.stringify(reviewFilter.value)}`,
  );

  console.log("\nScenario 12: i18n keys for Monitoramento exist in PT and EN");
  const newKeys = [
    "monitoramento_title",
    "monitoramento_attention",
    "monitoramento_attention_detail",
    "monitoramento_view_all_events",
    "monitoramento_recent_activity",
    "monitoramento_recent_empty",
    "monitoramento_fr24_details_link",
    "monitoramento_fr24_credits",
    "monitoramento_fr24_of_budget",
    "monitoramento_fr24_state",
    "monitoramento_fr24_state_active",
    "monitoramento_fr24_state_disabled",
    "monitoramento_fr24_state_paused",
    "monitoramento_empty",
    "monitoramento_map_aria",
    "monitoramento_event_unreviewed",
    "monitoramento_event_useful",
    "monitoramento_event_uncertain",
    "monitoramento_event_noise",
    "monitoramento_refresh",
    "monitoramento_actions",
    "monitoramento_sync_failed",
    "monitoramento_poll_failed",
  ];
  let i18nOK = true;
  for (const key of newKeys) {
    if (!tr.pt[key] || !tr.en[key] || tr.pt[key] === tr.en[key]) {
      i18nOK = false;
      check(
        `(12) i18n ${key} differs EN/PT`,
        false,
        `pt=${JSON.stringify(tr.pt[key])} en=${JSON.stringify(tr.en[key])}`,
      );
    }
  }
  if (i18nOK) {
    check("(12) all 23 new Monitoramento i18n keys exist and differ EN/PT", true);
  }

  if (failures > 0) {
    console.error(`\nSCENARIO FAILED: ${failures} check(s)`);
    process.exit(1);
  } else {
    console.log("\nAll scenarios green");
  }
}).catch((err) => {
  console.error("ERROR:", err.stack || err.message);
  process.exit(1);
});