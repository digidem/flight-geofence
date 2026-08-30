// Browserless vm battery for the availability-aware aircraft hex link
// ordering in app.js (aircraftHexLinks).
//
// Runs under plain `node tests/test_hex_links_vm.mjs` (no package.json,
// no JS runner in this repo). It executes the REAL app.js source inside a
// node `vm` context and drives the production aircraftHexLinks helper:
//
//   fresh events (0 < age <= 24h)   -> FlightAware first, then the
//                                      observing provider's globe order
//   older / future / invalid times  -> provider globe first, FlightAware last
//   flightradar24 events            -> ADS-B Exchange globe preferred
//                                      (FR24 has no public hex globe)
//   unknown provider                -> ADSB.lol globe preferred
//   timezone-less timestamps        -> interpreted as UTC, mirroring the
//                                      Python builder (regardless of the
//                                      host timezone)
//
// The Python mirror lives in app/links.py::aircraft_hex_links; if either
// side drifts, this battery (or tests/test_links.py) must fail.
//
// Exit code 0 = every scenario green; failures print SCENARIO FAILED lines.

import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const APP_JS = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "static", "app.js");
const source = fs.readFileSync(APP_JS, "utf8");

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
    addEventListener() {},
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
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

vm.runInContext(source, sandbox, { filename: "app.js" });

const linksOf = (hex, provider, occurredAt, registration) =>
  vm.runInContext("aircraftHexLinks", sandbox)(hex, provider, occurredAt, registration);
let failures = 0;
function check(name, condition) {
  if (condition) {
    console.log(`PASS ${name}`);
  } else {
    failures += 1;
    console.log(`SCENARIO FAILED ${name}`);
  }
}

const labels = (links) => links.map((l) => l.label);
const FA = "FlightAware";
const LOL = "ADSB.lol";
const ADSBX = "ADS-B Exchange";
const APLANES = "Airplanes.live";

const now = Date.now();
const hoursAgo = (h) => new Date(now - h * 3600 * 1000).toISOString();
const hoursFromNow = (h) => new Date(now + h * 3600 * 1000).toISOString();
// --- registration known: FlightAware aircraft page leads unconditionally ---
// The /live/modes/{hex}/redirect rots within hours of landing; the
// registration page always resolves, so it wins whenever known.
check(
  "stale with registration: FlightAware aircraft page first",
  JSON.stringify(labels(linksOf("e494d5", "adsb_lol", hoursAgo(25), "PT-JLL"))) ===
    JSON.stringify([FA, LOL, ADSBX, APLANES]),
);
check(
  "fresh with registration: FlightAware aircraft page first (no modes redirect)",
  JSON.stringify(labels(linksOf("e494d5", "adsb_lol", hoursAgo(1), "PT-JLL"))) ===
    JSON.stringify([FA, LOL, ADSBX, APLANES]),
);
check(
  "registration URL keeps original format",
  linksOf("e494d5", "adsb_lol", hoursAgo(25), "PT-JLL")[0].url ===
    "https://www.flightaware.com/live/flight/PT-JLL",
);
check(
  "registration is trimmed and uppercased",
  linksOf("e494d5", "adsb_lol", hoursAgo(25), "  pt-jll  ")[0].url ===
    "https://www.flightaware.com/live/flight/PT-JLL",
);
check(
  "invalid registration falls back to freshness ordering",
  labels(linksOf("e49abc", "adsb_lol", hoursAgo(25), "1"))[0] === LOL,
);
check(
  "empty registration falls back to freshness ordering",
  labels(linksOf("e49abc", "adsb_lol", hoursAgo(25), ""))[0] === LOL,
);
check(
  "dehyphenated-invalid registration falls back (parity with Python)",
  labels(linksOf("e49abc", "adsb_lol", hoursAgo(25), "-A"))[0] === LOL,
);


// --- fresh events lead with FlightAware -----------------------------------
check(
  "fresh adsb_lol: FlightAware first, provider globe second",
  JSON.stringify(labels(linksOf("e49abc", "adsb_lol", hoursAgo(1)))) ===
    JSON.stringify([FA, LOL, ADSBX, APLANES]),
);
check(
  "fresh flightradar24: FlightAware first, ADS-B Exchange second",
  JSON.stringify(labels(linksOf("e49abc", "flightradar24", hoursAgo(1)))) ===
    JSON.stringify([FA, ADSBX, LOL, APLANES]),
);
check(
  "fresh adsbexchange: FlightAware first, own globe second",
  JSON.stringify(labels(linksOf("e49abc", "adsbexchange", hoursAgo(1)))) ===
    JSON.stringify([FA, ADSBX, LOL, APLANES]),
);

// --- stale events lead with the provider globe ----------------------------
check(
  "stale adsb_lol: own globe first, FlightAware last",
  JSON.stringify(labels(linksOf("e49abc", "adsb_lol", hoursAgo(25)))) ===
    JSON.stringify([LOL, ADSBX, APLANES, FA]),
);
check(
  "stale flightradar24: ADS-B Exchange first (no FR24 globe)",
  JSON.stringify(labels(linksOf("e49abc", "flightradar24", hoursAgo(25)))) ===
    JSON.stringify([ADSBX, LOL, APLANES, FA]),
);
check(
  "stale airplanes_live: own globe first",
  JSON.stringify(labels(linksOf("e49abc", "airplanes_live", hoursAgo(25)))) ===
    JSON.stringify([APLANES, LOL, ADSBX, FA]),
);
check(
  "unknown provider defaults to ADSB.lol globe",
  JSON.stringify(labels(linksOf("e49abc", "mystery_provider", hoursAgo(25)))) ===
    JSON.stringify([LOL, ADSBX, APLANES, FA]),
);
check(
  "missing provider defaults to ADSB.lol globe",
  JSON.stringify(labels(linksOf("e49abc", undefined, hoursAgo(25)))) ===
    JSON.stringify([LOL, ADSBX, APLANES, FA]),
);

// --- exact freshness boundary (inclusive 24h) ------------------------------
check("boundary: 1s inside the 24h window is fresh (FlightAware first)",
  labels(linksOf("e49abc", "adsb_lol", new Date(now - (24 * 3600 - 1) * 1000).toISOString()))[0] === FA);
check("boundary: 1s past the 24h window is stale (globe first)",
  labels(linksOf("e49abc", "adsb_lol", new Date(now - (24 * 3600 + 1) * 1000).toISOString()))[0] === LOL);
check("boundary: just created is fresh",
  labels(linksOf("e49abc", "adsb_lol", new Date(now).toISOString()))[0] === FA);

// --- future / invalid / missing timestamps are stale -----------------------
check("future timestamp is stale", labels(linksOf("e49abc", "adsb_lol", hoursFromNow(2)))[0] === LOL);
check("unparseable timestamp is stale", labels(linksOf("e49abc", "adsb_lol", "garbage"))[0] === LOL);
check("empty timestamp is stale", labels(linksOf("e49abc", "adsb_lol", ""))[0] === LOL);
check("missing timestamp is stale", labels(linksOf("e49abc", "adsb_lol", undefined))[0] === LOL);

// --- timezone-less timestamps must read as UTC (Python parity) -------------
// A naive UTC timestamp one hour old would read as *local* time without the
// parity fix; under a UTC host this is equivalent, under any other host the
// pre-fix code misaged the event. Run this battery under
// `TZ=America/Sao_Paulo node tests/test_hex_links_vm.mjs` to pin it.
const naiveUtc = new Date(now - 3600 * 1000).toISOString().replace(/Z$/, "");
check("timezone-less timestamp treated as UTC (fresh)",
  labels(linksOf("e49abc", "adsb_lol", naiveUtc))[0] === FA);

// --- ordering keeps non-preferred globes stable ----------------------------
check(
  "non-preferred globes keep relative order (airplanes_live event)",
  JSON.stringify(labels(linksOf("e49abc", "airplanes_live", hoursAgo(25))).slice(1, 3)) ===
    JSON.stringify([LOL, ADSBX]),
);

// --- URL construction and validation unchanged -----------------------------
check("fresh URL is FlightAware modes redirect",
  linksOf("E49ABC", "adsb_lol", hoursAgo(1))[0].url === "https://www.flightaware.com/live/modes/e49abc/redirect");
check("stale first URL is adsb.lol globe",
  linksOf("E49ABC", "adsb_lol", hoursAgo(25))[0].url === "https://globe.adsb.lol/?icao=e49abc");
check("tilde-prefixed hex yields no links", linksOf("~29d348", "adsb_lol", hoursAgo(1)).length === 0);
check("invalid hex yields no links", linksOf("abc12", "adsb_lol", hoursAgo(1)).length === 0);
check("missing hex yields no links", linksOf("", "adsb_lol", hoursAgo(1)).length === 0);
check("exactly four links for a valid hex", linksOf("e49abc", "adsb_lol", hoursAgo(1)).length === 4);

if (failures > 0) {
  console.log(`\n${failures} scenario(s) FAILED`);
  process.exit(1);
}
console.log("\nAll hex-link ordering scenarios passed.");
