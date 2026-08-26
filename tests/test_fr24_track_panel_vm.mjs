// Browserless vm battery for the FR24 event-track panel wiring in app.js.
//
// Runs under plain `node tests/test_fr24_track_panel_vm.mjs` (no package.json,
// no JS runner in this repo). It executes the REAL app.js source inside a
// node `vm` context with a minimal DOM/fetch stub, then drives the delegated
// panel click handler and setupEventTrackPanel through the G-review-R2
// scenarios: blocked-disabled states, navigation-mid-flight race guard, and
// terminal outcomes re-derived from a fresh GET (single source of truth).
//
// Exit code 0 = every scenario green; failures print SCENARIO FAILED lines.

import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const APP_JS = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "static", "app.js");
const source = fs.readFileSync(APP_JS, "utf8");

const TRACK_URL = (id) => `/api/fr24/events/${id}/track`;

const TRANSLATIONS = {
  en: {
    fr24_track_button: "Fetch flight track",
    fr24_track_cost: "Estimated cost: {credits} credits",
    fr24_track_confirm: "Fetch this flight's track? Estimated cost: ~{credits} credits.",
    fr24_track_fetching: "Fetching track…",
    fr24_track_success: "Track stored: {records} points, {credits} credits.",
    fr24_track_error: "Track fetch failed: {detail}",
    fr24_track_blocked_missing: "This event has no Flightradar24 ID, so there is no track to fetch.",
    fr24_track_blocked_fetched: "The track for this event was already fetched.",
    fr24_track_blocked_paused: "FR24 budget exhausted with policy=pause_fr24 — manual fetch refused.",
    fr24_track_blocked_progress: "A fetch for this flight is already in progress.",
    fr24_track_loading: "Checking track availability…",
  },
  pt: {
    fr24_track_button: "Buscar rastreamento do voo",
    fr24_track_cost: "Custo estimado: {credits} créditos",
    fr24_track_confirm: "Buscar o rastreamento deste voo? Custo estimado: ~{credits} créditos.",
    fr24_track_fetching: "Buscando rastreamento…",
    fr24_track_success: "Rastreamento armazenado: {records} pontos, {credits} créditos.",
    fr24_track_error: "Falha ao buscar rastreamento: {detail}",
    fr24_track_blocked_missing: "Este evento não possui ID da Flightradar24; não há rastreamento para buscar.",
    fr24_track_blocked_fetched: "O rastreamento deste evento já foi buscado.",
    fr24_track_blocked_paused: "Orçamento FR24 esgotado com policy=pause_fr24 — busca manual recusada.",
    fr24_track_blocked_progress: "Uma busca para este voo já está em andamento.",
    fr24_track_loading: "Verificando disponibilidade de rastreamento…",
  },
};

function makeElement(tag = "div") {
  const listeners = {};
  return {
    tagName: tag.toUpperCase(),
    listeners,
    dataset: {},
    hidden: false,
    disabled: false,
    textContent: "",
    innerHTML: "",
    value: "",
    checked: false,
    placeholder: "",
    style: {},
    classList: { add() {}, remove() {}, toggle() {} },
    childNodes: [],
    children: [],
    addEventListener(type, fn) {
      (listeners[type] ||= []).push(fn);
    },
    removeEventListener() {},
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    querySelector() {
      return null;
    },
    getAttribute() {
      return null;
    },
    setAttribute() {},
    closest(selector) {
      return selector === "#event-track-fetch" ? registry["#event-track-fetch"] : null;
    },
    dispatch(type, event) {
      for (const fn of listeners[type] ?? []) fn(event);
    },
  };
}

const registry = {};
function $(selector) {
  if (!registry[selector]) registry[selector] = makeElement(selector.startsWith("#") ? "div" : "div");
  return registry[selector];
}

function $$(selector) {
  return [];
}

const documentStub = {
  documentElement: { lang: "" },
  querySelector: (selector) => $(selector),
  querySelectorAll: () => [],
  createElement: () => makeElement(),
  createTextNode: (text) => ({ nodeType: 3, textContent: text }),
};

// --- fetch routing -----------------------------------------------------------

let routeGetTrack = null; // (eventId) => response-like | {deferred}
let routePostTrack = null; // (eventId) => response-like
let postCalls = [];
let deferredGets = new Map(); // eventId -> {resolve, respond}

function jsonResponse(body, status = 200) {
  return {
    ok: status < 400,
    status,
    json: async () => body,
  };
}

async function fakeFetch(url, options = {}) {
  const method = options.method || "GET";
  if (url === "/api/i18n") return jsonResponse(TRANSLATIONS);
  if (url === "/api/auth/status") return jsonResponse({ authenticated: true, csrf_token: "csrf-test" });
  if (url.startsWith("/api/fr24/events/") && url.endsWith("/track")) {
    const eventId = decodeURIComponent(url.split("/")[4]);
    if (method === "POST") {
      postCalls.push(eventId);
      return routePostTrack ? routePostTrack(eventId) : jsonResponse({ fetched: true });
    }
    if (routeGetTrack) {
      const result = routeGetTrack(eventId);
      if (result && result.deferred) {
        return new Promise((resolve) => {
          deferredGets.set(eventId, { resolve, respond: result.respond });
        });
      }
      return result;
    }
    return jsonResponse({});
  }
  if (url.startsWith("/api/events")) {
    return jsonResponse({
      events: [
        {
          id: "ev-a",
          event_type: "PROBABLE_STOP",
          occurred_at: "2026-08-25T12:00:00+00:00",
          aircraft_hex: "abc123",
          area_names: ["Area A"],
          reason: "battery",
          provider: "flightradar24",
          review_status: "unreviewed",
          phase: "shadow",
          details: { episode_id: "ep-a" },
        },
        {
          id: "ev-b",
          event_type: "PROBABLE_STOP",
          occurred_at: "2026-08-25T13:00:00+00:00",
          aircraft_hex: "def456",
          area_names: ["Area B"],
          reason: "battery",
          provider: "flightradar24",
          review_status: "unreviewed",
          phase: "shadow",
          details: { episode_id: "ep-b" },
        },
      ],
    });
  }
  return jsonResponse({});
}

// --- sandbox -----------------------------------------------------------------

const sandbox = {
  console,
  setTimeout,
  clearTimeout,
  encodeURIComponent,
  decodeURIComponent,
  JSON,
  Math,
  Date,
  Promise,
  Object,
  Array,
  String,
  Number,
  Boolean,
  isNaN,
  parseInt,
  parseFloat,
  Node: { TEXT_NODE: 3 },
  navigator: { language: "en-US" },
  window: {
    confirm: () => true,
    location: { hash: "" },
    addEventListener() {},
  },
  document: documentStub,
  $,
  $$: () => [],
  fetch: fakeFetch,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

vm.runInContext(source, sandbox, { filename: "app.js" });

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
const settle = async () => {
  for (let i = 0; i < 8; i += 1) await tick();
};

const panel = $("#event-track-panel");
const button = $("#event-track-fetch");
const costLine = $("#event-track-cost");
const resultBox = $("#event-track-result");
const detailContent = $("#event-detail-content");

async function renderEvent(id) {
  await sandbox.loadEventDetail(id);
  await settle();
}

function clickFetch() {
  const handler = panel.listeners.click[panel.listeners.click.length - 1];
  if (!handler) throw new Error("no delegated click handler registered");
  return handler({ target: { closest: () => button }, currentTarget: panel });
}

let failures = 0;
function check(name, condition) {
  if (condition) {
    console.log(`PASS ${name}`);
  } else {
    failures += 1;
    console.log(`SCENARIO FAILED ${name}`);
  }
}

function resetPanelState() {
  panel.dataset = {};
  button.disabled = false;
  button.hidden = false;
  costLine.textContent = "";
  resultBox.textContent = "";
  detailContent.innerHTML = "";
}

// --- (a) already_fetched ends disabled ---------------------------------------

resetPanelState();
routeGetTrack = (id) =>
  jsonResponse({
    available: false,
    event_id: id,
    fr24_id: "fr24-x",
    already_fetched: true,
    estimated_credits: 40,
    blocked_reason: "already_fetched",
  });
await renderEvent("ev-a");
check(
  "(a) already_fetched -> button visible but disabled with blocker line",
  button.disabled === true && button.hidden === false && costLine.textContent === TRANSLATIONS.en.fr24_track_blocked_fetched,
);

// --- (b) paused ends disabled --------------------------------------------------

resetPanelState();
routeGetTrack = (id) =>
  jsonResponse({
    available: false,
    event_id: id,
    fr24_id: "fr24-x",
    already_fetched: false,
    estimated_credits: 40,
    blocked_reason: "budget_exhausted_pause_fr24",
  });
await renderEvent("ev-b");
check(
  "(b) paused -> button visible but disabled with pause line",
  button.disabled === true && button.hidden === false && costLine.textContent === TRANSLATIONS.en.fr24_track_blocked_paused,
);

// --- (f) confirm cancel sends nothing -----------------------------------------

resetPanelState();
postCalls = [];
routeGetTrack = (id) =>
  jsonResponse({ available: true, event_id: id, fr24_id: "fr24-x", already_fetched: false, estimated_credits: 40, blocked_reason: null });
sandbox.window.confirm = () => false;
await renderEvent("ev-a");
await clickFetch();
await settle();
check("(f) confirm cancel -> zero POSTs, button stays enabled", postCalls.length === 0 && button.disabled === false);
sandbox.window.confirm = () => true;

// --- (e) success: flash consumed, state re-derived to disabled -----------------

resetPanelState();
let stage = "first";
routeGetTrack = (id) => {
  if (stage === "first") {
    stage = "after";
    return jsonResponse({ available: true, event_id: id, fr24_id: "fr24-x", already_fetched: false, estimated_credits: 40, blocked_reason: null });
  }
  return jsonResponse({ available: false, event_id: id, fr24_id: "fr24-x", already_fetched: true, estimated_credits: 40, blocked_reason: "already_fetched" });
};
routePostTrack = () => jsonResponse({ fetched: true, records_returned: 2, estimated_credits: 80 });
await renderEvent("ev-a");
await clickFetch();
await settle();
check(
  "(e) success -> flash consumed AND button re-derived disabled",
  button.disabled === true &&
    resultBox.textContent ===
      TRANSLATIONS.en.fr24_track_success.replace("{records}", "2").replace("{credits}", "80"),
);

// --- (d) provider failure: no manual re-enable, fresh GET decides ---------------

resetPanelState();
stage = "first";
routeGetTrack = (id) => {
  if (stage === "first") {
    stage = "after";
    return jsonResponse({ available: true, event_id: id, fr24_id: "fr24-x", already_fetched: false, estimated_credits: 40, blocked_reason: null });
  }
  // Budget ran out server-side while the failed POST was in flight.
  return jsonResponse({ available: false, event_id: id, fr24_id: "fr24-x", already_fetched: false, estimated_credits: 40, blocked_reason: "budget_exhausted_pause_fr24" });
};
routePostTrack = () => jsonResponse({ detail: "FR24 request failed for https://fr24api.flightradar24.com/api/flight-tracks: 503" }, 502);
await renderEvent("ev-a");
await clickFetch();
await settle();
check(
  "(d) provider failure -> state re-derived from fresh GET (disabled), not hand-enabled",
  button.disabled === true && costLine.textContent === TRANSLATIONS.en.fr24_track_blocked_paused,
);

// --- (c) navigation mid-flight abandons stale continuation ----------------------

resetPanelState();
postCalls = [];
// Event A: GET says available; its POST will hang until released.
routeGetTrack = (id) => {
  if (id === "ev-a" && !deferredGets.has("ev-a-post")) {
    // First GET for A is immediate-available so the button arms.
    if (!routeGetTrack.armedA) {
      routeGetTrack.armedA = true;
      return jsonResponse({ available: true, event_id: id, fr24_id: "fr24-a", already_fetched: false, estimated_credits: 40, blocked_reason: null });
    }
  }
  if (id === "ev-b") {
    return jsonResponse({ available: true, event_id: id, fr24_id: "fr24-b", already_fetched: false, estimated_credits: 40, blocked_reason: null });
  }
  return jsonResponse({ available: false, event_id: id, fr24_id: "fr24-a", already_fetched: true, estimated_credits: 40, blocked_reason: "already_fetched" });
};
routeGetTrack.armedA = false;
let releasePost;
routePostTrack = (id) =>
  new Promise((resolve) => {
    releasePost = () => resolve(jsonResponse({ fetched: true, records_returned: 2, estimated_credits: 80 }));
  });
await renderEvent("ev-a"); // arms the button for A
panel.dataset.eventId = "ev-a";
const clickPromise = clickFetch(); // POST for A hangs
await settle();

// Operator navigates to event B while A's POST is in flight.
await renderEvent("ev-b");
const bCostBefore = costLine.textContent;
const bEnabledBefore = button.disabled === false;

releasePost(); // A's POST completes server-side (logged + audited)
await clickPromise.catch(() => {});
await settle();

check(
  "(c) navigation mid-flight -> new event untouched (dataset stays ev-b, cost intact, button enabled)",
  panel.dataset.eventId === "ev-b" &&
    costLine.textContent === bCostBefore &&
    bEnabledBefore &&
    button.disabled === false &&
    resultBox.textContent !== TRANSLATIONS.en.fr24_track_success.replace("{records}", "2").replace("{credits}", "80"),
);

// --- R3 (g) success terminal refresh hangs; nav to B must not be clobbered ----

resetPanelState();
postCalls = [];
let gStage = "arm";
let releaseGRefresh;
routeGetTrack = (id) => {
  if (id === "ev-b") {
    return jsonResponse({ available: true, event_id: id, fr24_id: "fr24-b", already_fetched: false, estimated_credits: 40, blocked_reason: null });
  }
  if (gStage === "arm") {
    gStage = "refresh";
    return jsonResponse({ available: true, event_id: id, fr24_id: "fr24-a", already_fetched: false, estimated_credits: 40, blocked_reason: null });
  }
  if (gStage === "refresh") {
    gStage = "done";
    return {
      deferred: true,
      respond: () => jsonResponse({ available: false, event_id: id, fr24_id: "fr24-a", already_fetched: true, estimated_credits: 40, blocked_reason: "already_fetched" }),
    };
  }
  return jsonResponse({ available: false, event_id: id, fr24_id: "fr24-a", already_fetched: true, estimated_credits: 40, blocked_reason: "already_fetched" });
};
routePostTrack = (id) => jsonResponse({ fetched: true, records_returned: 2, estimated_credits: 80 });
await renderEvent("ev-a"); // arms A (stage arm -> refresh consumed by setup GET)
const gClick = clickFetch(); // POST ok -> handler calls loadEventDetail(A) -> refresh GET hangs
await settle(); // let POST resolve + deferred refresh GET register
await renderEvent("ev-b"); // operator navigates to B during the hung refresh
const gCost = costLine.textContent;
const gDataset = panel.dataset.eventId;
deferredGets.get("ev-a").resolve(deferredGets.get("ev-a").respond());
deferredGets.delete("ev-a");
await gClick.catch(() => {});
await settle();
check(
  "(g) success-refresh hang + nav -> B survives A's late refresh",
  panel.dataset.eventId === "ev-b" &&
    costLine.textContent === gCost &&
    gDataset === "ev-b" &&
    button.disabled === false &&
    resultBox.textContent !== TRANSLATIONS.en.fr24_track_success.replace("{records}", "2").replace("{credits}", "80"),
);

// --- R3 (h) error terminal refresh hang + nav -> B untouched -------------------

resetPanelState();
postCalls = [];
let hStage = "arm";
routeGetTrack = (id) => {
  if (id === "ev-b") {
    return jsonResponse({ available: true, event_id: id, fr24_id: "fr24-b", already_fetched: false, estimated_credits: 40, blocked_reason: null });
  }
  if (hStage === "arm") {
    hStage = "refresh";
    return jsonResponse({ available: true, event_id: id, fr24_id: "fr24-a", already_fetched: false, estimated_credits: 40, blocked_reason: null });
  }
  if (hStage === "refresh") {
    hStage = "done";
    return {
      deferred: true,
      respond: () => jsonResponse({ available: true, event_id: id, fr24_id: "fr24-a", already_fetched: false, estimated_credits: 40, blocked_reason: null }),
    };
  }
  return jsonResponse({ available: true, event_id: id, fr24_id: "fr24-a", already_fetched: false, estimated_credits: 40, blocked_reason: null });
};
routePostTrack = (id) => jsonResponse({ detail: "FR24 request failed for https://fr24api.flightradar24.com/api/flight-tracks: 503" }, 502);
await renderEvent("ev-a");
const hClick = clickFetch();
await settle();
await renderEvent("ev-b");
const hCost = costLine.textContent;
const hResult = resultBox.textContent;
deferredGets.get("ev-a").resolve(deferredGets.get("ev-a").respond());
deferredGets.delete("ev-a");
await hClick.catch(() => {});
await settle();
check(
  "(h) error-refresh hang + nav -> B untouched, no stale error written",
  panel.dataset.eventId === "ev-b" && costLine.textContent === hCost && button.disabled === false && resultBox.textContent === hResult,
);

// --- R3 (i) stay-on-A error text persists through the refresh ------------------

resetPanelState();
postCalls = [];
let iStage = "arm";
routeGetTrack = (id) => {
  if (iStage === "arm") {
    iStage = "refresh";
    return jsonResponse({ available: true, event_id: id, fr24_id: "fr24-i", already_fetched: false, estimated_credits: 40, blocked_reason: null });
  }
  return jsonResponse({ available: false, event_id: id, fr24_id: "fr24-i", already_fetched: false, estimated_credits: 40, blocked_reason: "budget_exhausted_pause_fr24" });
};
routePostTrack = (id) => jsonResponse({ detail: "FR24 request failed for https://fr24api.flightradar24.com/api/flight-tracks: 503" }, 502);
await renderEvent("ev-a");
await clickFetch();
await settle();
check(
  "(i) stay-on-A error -> localized error persists after refresh, button re-derived disabled",
  resultBox.textContent ===
    TRANSLATIONS.en.fr24_track_error.replace(
      "{detail}",
      "FR24 request failed for https://fr24api.flightradar24.com/api/flight-tracks: 503",
    ) &&
    button.disabled === true,
);

if (failures > 0) {
  console.log(`\n${failures} scenario(s) FAILED`);
  process.exitCode = 1;
} else {
  console.log("\nAll scenarios green");
}
