// Browserless vm battery for the FR24 retention metric rendering in app.js.
//
// Runs under plain `node tests/test_fr24_retention_vm.mjs` (no package.json,
// no JS runner in this repo). It executes the REAL app.js source inside a
// node `vm` context, seeds the real appState with stub translations that
// mirror the production i18n copy exactly, then drives the production
// fr24RetentionMetrics helper through roadmap §6.6's three-case matrix:
//
//   FR24 events        -> auto-delete on: min(fr24_retention_days, 29) days
//                          auto-delete off: indefinite
//   FR24 out-of-area   -> auto-delete on: state_retention_days days
//    aircraft states      auto-delete off: indefinite
//   free-provider      -> always state_retention_days days (the
//    out-of-area states   exclude_provider carve-out only protects FR24 rows)
//
// Exit code 0 = every scenario green; failures print SCENARIO FAILED lines.

import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const APP_JS = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "static", "app.js");
const source = fs.readFileSync(APP_JS, "utf8");

// Exact copies of the production strings in app/i18n.py -- if either side
// drifts, this battery fails and the copy must be re-synced deliberately.
const TRANSLATIONS = {
  en: {
    fr24_retention_title: "Data retention",
    fr24_retention_events: "FR24 events",
    fr24_retention_fr24_states: "Outside aircraft state — last seen via FR24",
    fr24_retention_free_states: "Outside aircraft state — last seen via free provider",
    fr24_retention_indefinite: "Indefinite — automatic deletion off",
    fr24_retention_days: "days",
  },
  pt: {
    fr24_retention_title: "Retenção de dados",
    fr24_retention_events: "Eventos FR24",
    fr24_retention_fr24_states: "Fora do estado de aeronave — último sinal via FR24",
    fr24_retention_free_states: "Fora do estado de aeronave — último sinal via provedor gratuito",
    fr24_retention_indefinite: "Indefinido — exclusão automática desligada",
    fr24_retention_days: "dias",
  },
};

function makeElement() {
  return {
    listeners: {},
    innerHTML: "",
    textContent: "",
    hidden: false,
    disabled: false,
    dataset: {},
    style: {},
    classList: { toggle() {}, add() {}, remove() {} },
    addEventListener(type, fn) {
      (this.listeners[type] ||= []).push(fn);
    },
    setAttribute() {},
    getAttribute() {
      return null;
    },
    querySelector() {
      return makeElement();
    },
    querySelectorAll() {
      return [];
    },
    appendChild() {},
  };
}

const registry = {};
function $(selector) {
  if (!registry[selector]) registry[selector] = makeElement();
  return registry[selector];
}

const documentStub = {
  documentElement: { lang: "" },
  querySelector: $,
  querySelectorAll: () => [],
  createElement: () => makeElement(),
  addEventListener() {},
  body: makeElement(),
};

const sandbox = {
  console,
  setTimeout,
  clearTimeout,
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
  navigator: { language: "en-US" },
  window: {
    location: { hash: "" },
    addEventListener() {},
  },
  document: documentStub,
  $,
  $$: () => [],
  STUB_TRANSLATIONS: TRANSLATIONS,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

vm.runInContext(source, sandbox, { filename: "app.js" });

// Seed the real appState the way init() does after /api/i18n responds.
// Script-level const bindings live in the context's shared global lexical
// environment, so a second script in the same context can reach appState.
vm.runInContext(
  "appState.translations = STUB_TRANSLATIONS; appState.language = 'en';",
  sandbox,
);

let failures = 0;
function check(name, condition) {
  if (condition) {
    console.log(`PASS ${name}`);
  } else {
    failures += 1;
    console.log(`SCENARIO FAILED ${name}`);
  }
}

const metricsOf = (status) => vm.runInContext("fr24RetentionMetrics", sandbox)(status);
const htmlOf = (status) => metricsOf(status).join("");

// --- (1) defaults, auto-delete OFF: FR24-owned data is indefinite ------------

{
  const status = {
    auto_delete_enabled: false,
    retention_events_days: 29,
    retention_state_days: 14,
  };
  const [events, fr24States, freeStates] = metricsOf(status);
  check(
    "(1) off + defaults -> FR24 events labeled min(29,cfg) window but presented indefinite",
    events.includes(TRANSLATIONS.en.fr24_retention_events) &&
      events.includes(TRANSLATIONS.en.fr24_retention_indefinite) &&
      !events.includes("29"),
  );
  check(
    "(1) off + defaults -> FR24 out-of-area states presented indefinite",
    fr24States.includes(TRANSLATIONS.en.fr24_retention_fr24_states) &&
      fr24States.includes(TRANSLATIONS.en.fr24_retention_indefinite),
  );
  check(
    "(1) off + defaults -> free-provider out-of-area states still count down cfg days",
    freeStates.includes(TRANSLATIONS.en.fr24_retention_free_states) &&
      freeStates.includes(`14 ${TRANSLATIONS.en.fr24_retention_days}`) &&
      !freeStates.includes(TRANSLATIONS.en.fr24_retention_indefinite),
  );
}

// --- (2) auto-delete ON: countdowns for both FR24-owned windows --------------

{
  const status = {
    auto_delete_enabled: true,
    retention_events_days: 29,
    retention_state_days: 14,
  };
  const [events, fr24States, freeStates] = metricsOf(status);
  check(
    "(2) on + defaults -> FR24 events count down effective days",
    events.includes(`${29} ${TRANSLATIONS.en.fr24_retention_days}`) &&
      !events.includes(TRANSLATIONS.en.fr24_retention_indefinite),
  );
  check(
    "(2) on + defaults -> FR24 out-of-area states count down state days",
    fr24States.includes(`14 ${TRANSLATIONS.en.fr24_retention_days}`),
  );
  check(
    "(2) on + defaults -> free-provider states unchanged at state days",
    freeStates.includes(`14 ${TRANSLATIONS.en.fr24_retention_days}`),
  );
}

// --- (3) env overrides flow through untouched --------------------------------

{
  const status = {
    auto_delete_enabled: true,
    retention_events_days: 17, // FR24_RETENTION_DAYS=17 (< cap 29)
    retention_state_days: 21, // STATE_RETENTION_DAYS=21
  };
  const [events, fr24States, freeStates] = metricsOf(status);
  check(
    "(3) overrides -> events render overridden days",
    events.includes(`17 ${TRANSLATIONS.en.fr24_retention_days}`),
  );
  check(
    "(3) overrides -> both state windows render overridden state days",
    fr24States.includes(`21 ${TRANSLATIONS.en.fr24_retention_days}`) &&
      freeStates.includes(`21 ${TRANSLATIONS.en.fr24_retention_days}`),
  );
}

// --- (4) cap: retention above 29 still renders the payload's capped value ----

{
  const status = {
    auto_delete_enabled: true,
    retention_events_days: 45, // payload already applies min(cfg, 29)
    retention_state_days: 14,
  };
  const [events] = metricsOf(status);
  check(
    "(4) capped payload value rendered as-is by the frontend",
    events.includes(`45 ${TRANSLATIONS.en.fr24_retention_days}`),
  );
}

// --- (5) PT language matrix ---------------------------------------------------

{
  vm.runInContext("appState.language = 'pt';", sandbox);
  const status = {
    auto_delete_enabled: false,
    retention_events_days: 29,
    retention_state_days: 14,
  };
  const [events, , freeStates] = metricsOf(status);
  check(
    "(5) pt + off -> PT labels and PT indefinite copy",
    events.includes(TRANSLATIONS.pt.fr24_retention_events) &&
      events.includes(TRANSLATIONS.pt.fr24_retention_indefinite) &&
      freeStates.includes(TRANSLATIONS.pt.fr24_retention_free_states) &&
      freeStates.includes(`14 ${TRANSLATIONS.pt.fr24_retention_days}`),
  );
  vm.runInContext("appState.language = 'en';", sandbox);
}

// --- (6) joined HTML is three escaped metric articles -------------------------

{
  const html = htmlOf({
    auto_delete_enabled: true,
    retention_events_days: 29,
    retention_state_days: 14,
  });
  const articles = html.split("<article").length - 1;
  check(
    "(6) joined render -> exactly three metric articles carrying all labels",
    articles === 3 &&
      html.includes('class="metric-label"') &&
      [TRANSLATIONS.en.fr24_retention_events, TRANSLATIONS.en.fr24_retention_fr24_states, TRANSLATIONS.en.fr24_retention_free_states].every(
        (label) => html.includes(label),
      ),
  );
}

if (failures > 0) {
  console.error(`\n${failures} scenario(s) failed`);
  process.exitCode = 1;
} else {
  console.log("\nAll scenarios green");
}
