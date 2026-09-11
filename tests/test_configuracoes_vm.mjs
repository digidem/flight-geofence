// Browserless vm battery for the Configurações reorganization surface (issue #19).
//
// Tests:
// - 6-section stepper structure and anchor sections (operacao, deteccao, notificacoes, fr24, sistema, registros)
// - Hidden state of FR24 and Registros stepper buttons until child issues land
// - Empty section containers for #fr24 and #registros
// - Atomic move of manual actions (#sync-now, #poll-now, #test-email) from Monitoramento to Operação
// - showSettingsStep(n) as single source of truth for stepper state
// - openSettingsSection(sectionId) cross-section jump helper
// - Stepper prev/next navigation flow (skipping hidden steps)
// - Environment-locked badge on settings with source='environment' && locked=true
// - i18n key coverage
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
    get id() { return this.attributes.id || ""; },
    set id(v) { this.attributes.id = String(v); },
    attributes: {},
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
    get className() { return [...this.classList._set].join(" "); },
    set className(v) {
      this.classList._set.clear();
      for (const c of String(v || "").split(/\s+/)) if (c) this.classList._set.add(c);
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
      if (name === "data-step") this.dataset.step = String(value);
      if (name === "data-next") this.dataset.next = String(value);
      if (name === "data-prev") this.dataset.prev = String(value);
      if (name === "data-view") this.dataset.view = String(value);
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
    appendChild(child) {
      (this._children ||= []).push(child);
      child.parentElement = this;
      return child;
    },
    scrollIntoView() { this._scrolled = true; },
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
      const found = findInTree(this, selector);
      if (found) return found;
      for (const [k, v] of registry.entries()) {
        if (matchSelector(v, selector)) return v;
      }
      return null;
    },
    querySelectorAll(selector) {
      const out = [];
      collectInTree(this, selector, out);
      if (out.length) return out;
      for (const [k, v] of registry.entries()) {
        if (matchSelector(v, selector)) out.push(v);
      }
      return out;
    },
  };
  return el;
}

function findInTree(root, selector) {
  for (const child of root._children || []) {
    if (matchSelector(child, selector)) return child;
    const res = findInTree(child, selector);
    if (res) return res;
  }
  return null;
}

function collectInTree(root, selector, out) {
  for (const child of root._children || []) {
    if (matchSelector(child, selector)) out.push(child);
    collectInTree(child, selector, out);
  }
}

function matchSelector(el, selector) {
  if (!el) return false;
  if (selector === '[role="tab"]') return el.getAttribute("role") === "tab";
  if (selector.startsWith("#")) return el.id === selector.slice(1);
  if (selector.startsWith(".env-badge")) {
    const isBadge = el.classList && el.classList.contains("env-badge");
    const keyMatch = selector.match(/\[data-key="([^"]+)"\]/);
    if (keyMatch) return isBadge && el.dataset.key === keyMatch[1];
    return isBadge;
  }
  if (selector.startsWith(".")) return el.classList && el.classList.contains(selector.slice(1));
  if (selector.startsWith("[name='") && selector.endsWith("']")) {
    const n = selector.slice(7, -2);
    return el.name === n;
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

// Stepper tabs (1-6)
const tab1 = autoregister("#settings-step-tab-1");
tab1.setAttribute("role", "tab"); tab1.setAttribute("data-step", "1"); tab1.classList.add("active"); tab1.setAttribute("aria-selected", "true");
const tab2 = autoregister("#settings-step-tab-2");
tab2.setAttribute("role", "tab"); tab2.setAttribute("data-step", "2"); tab2.setAttribute("aria-selected", "false");
const tab3 = autoregister("#settings-step-tab-3");
tab3.setAttribute("role", "tab"); tab3.setAttribute("data-step", "3"); tab3.setAttribute("aria-selected", "false");
const tab4 = autoregister("#settings-step-tab-4");
tab4.setAttribute("role", "tab"); tab4.setAttribute("data-step", "4"); tab4.setAttribute("aria-selected", "false"); tab4.hidden = true;
const tab5 = autoregister("#settings-step-tab-5");
tab5.setAttribute("role", "tab"); tab5.setAttribute("data-step", "5"); tab5.setAttribute("aria-selected", "false");
const tab6 = autoregister("#settings-step-tab-6");
tab6.setAttribute("role", "tab"); tab6.setAttribute("data-step", "6"); tab6.setAttribute("aria-selected", "false"); tab6.hidden = true;

// Stepper panels (1-6)
const panel1 = autoregister("#settings-step-1");
panel1.classList.add("settings-step"); panel1.classList.add("active"); panel1.hidden = false;
const panel2 = autoregister("#settings-step-2");
panel2.classList.add("settings-step"); panel2.hidden = true;
const panel3 = autoregister("#settings-step-3");
panel3.classList.add("settings-step"); panel3.hidden = true;
const panel4 = autoregister("#settings-step-4");
panel4.classList.add("settings-step"); panel4.hidden = true;
const panel5 = autoregister("#settings-step-5");
panel5.classList.add("settings-step"); panel5.hidden = true;
const panel6 = autoregister("#settings-step-6");
panel6.classList.add("settings-step"); panel6.hidden = true;

// Section anchors
const secOperacao = autoregister("#operacao");
const secDeteccao = autoregister("#deteccao");
const secNotificacoes = autoregister("#notificacoes");
const secFr24 = autoregister("#fr24");
const secSistema = autoregister("#sistema");
const secRegistros = autoregister("#registros");

// Forms
const formCore = autoregister("#settings-core");
const formDisplay = autoregister("#settings-display");
const formThresholds = autoregister("#settings-thresholds");
const formEmail = autoregister("#settings-email");
const formKeys = autoregister("#settings-keys");

// Primary settings tab
const settingsPrimaryTab = autoregister('.tab[data-view="settings"]');
settingsPrimaryTab.setAttribute("data-view", "settings");

// Manual actions
const syncNow = autoregister("#sync-now");
const pollNow = autoregister("#poll-now");
const testEmail = autoregister("#test-email");
const actionResult = autoregister("#action-result");

// Stepper buttons
const stepper = autoregister(".settings-stepper");

// Stepper nav buttons
const next1to2 = autoregister(".settings-next-1");
next1to2.classList.add("settings-next"); next1to2.setAttribute("data-next", "2");
const prev2to1 = autoregister(".settings-prev-2");
prev2to1.classList.add("settings-prev"); prev2to1.setAttribute("data-prev", "1");
const next2to3 = autoregister(".settings-next-2");
next2to3.classList.add("settings-next"); next2to3.setAttribute("data-next", "3");
const prev3to2 = autoregister(".settings-prev-3");
prev3to2.classList.add("settings-prev"); prev3to2.setAttribute("data-prev", "2");
const next3to5 = autoregister(".settings-next-3");
next3to5.classList.add("settings-next"); next3to5.setAttribute("data-next", "5");
const prev5to3 = autoregister(".settings-prev-5");
prev5to3.classList.add("settings-prev"); prev5to3.setAttribute("data-prev", "3");

const documentStub = {
  activeElement: null,
  documentElement: { lang: "en" },
  body: {
    contains(el) { return true; },
  },
  createElement(tag) {
    const el = makeElement();
    el.tagName = String(tag).toUpperCase();
    return el;
  },
  getElementById(id) {
    return autoregister(`#${id}`);
  },
  querySelector(sel) {
    if (sel === ".settings-stepper") return stepper;
    if (registry.has(sel)) return registry.get(sel);
    for (const [k, v] of registry.entries()) {
      if (matchSelector(v, sel)) return v;
    }
    return autoregister(sel);
  },
  querySelectorAll(sel) {
    if (sel === '[role="tab"]') {
      return [tab1, tab2, tab3, tab4, tab5, tab6];
    }
    if (sel === ".settings-step") {
      return [panel1, panel2, panel3, panel4, panel5, panel6];
    }
    if (sel === ".settings-next") {
      return [next1to2, next2to3, next3to5];
    }
    if (sel === ".settings-prev") {
      return [prev2to1, prev3to2, prev5to3];
    }
    const out = [];
    for (const [k, v] of registry.entries()) {
      if (matchSelector(v, sel)) out.push(v);
    }
    return out;
  },
  addEventListener(type, fn) {},
};

// ---- Mock API fetch routes -------------------------------------------------
let apiLog = [];

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
  apiLog.push({ url, method, body: options.body });
  if (url === "/api/boundaries/sync" && method === "POST") {
    return Promise.resolve(jsonResponse({ status: "started", detail: "Boundary sync started" }));
  }
  if (url === "/api/poll" && method === "POST") {
    return Promise.resolve(jsonResponse({ status: "started", detail: "Poll cycle started" }));
  }
  if (url === "/api/email/test" && method === "POST") {
    return Promise.resolve(jsonResponse({ status: "sent", detail: "Test email sent" }));
  }
  if (url === "/api/settings") {
    return Promise.resolve(jsonResponse({
      settings: {
        operating_phase: { value: "review", source: "interface", locked: false },
        poll_interval_seconds: { value: 60, source: "environment", locked: true },
        language: { value: "pt", source: "default", locked: false },
        timezone: { value: "America/Sao_Paulo", source: "environment", locked: true },
        flight_providers: { value: ["adsb_lol"], source: "interface", locked: false },
      },
      provider_options: {},
    }));
  }
  return Promise.resolve(jsonResponse({}));
}

const sandbox = {
  console,
  setTimeout,
  clearTimeout,
  URLSearchParams,
  RadioNodeList: class RadioNodeList {},
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
  "({ showSettingsStep: typeof showSettingsStep !== 'undefined' ? showSettingsStep : null, openSettingsSection: typeof openSettingsSection !== 'undefined' ? openSettingsSection : null, initSettingsStepper: typeof initSettingsStepper !== 'undefined' ? initSettingsStepper : null, setField: typeof setField !== 'undefined' ? setField : null, loadSettings: typeof loadSettings !== 'undefined' ? loadSettings : null, appState: typeof appState !== 'undefined' ? appState : null, t: typeof t !== 'undefined' ? t : null })",
  sandbox,
  { filename: "(exports)" },
);
const { showSettingsStep, openSettingsSection, initSettingsStepper, setField, loadSettings, appState, t } = exportsObj;

if (appState) {
  appState.translations = tr;
  appState.language = "pt";
}

// ---- Test Scenarios --------------------------------------------------------

console.log("Scenario 1: Stepper and section markup invariants");
check(
  "(1a) 6 stepper step buttons exist in index.html",
  (indexHtml.match(/id=["']settings-step-tab-[1-6]["']/g) || []).length === 6,
  "expected settings-step-tab-1 through settings-step-tab-6"
);
check(
  "(1b) FR24 step button (tab 4) is hidden in static markup",
  /id=["']settings-step-tab-4["'][^>]*\bhidden\b/.test(indexHtml),
  "expected hidden attribute on settings-step-tab-4"
);
check(
  "(1c) Registros step button (tab 6) is hidden in static markup",
  /id=["']settings-step-tab-6["'][^>]*\bhidden\b/.test(indexHtml),
  "expected hidden attribute on settings-step-tab-6"
);
check(
  "(1d) All six anchor sections exist in index.html",
  ["operacao", "deteccao", "notificacoes", "fr24", "sistema", "registros"].every((sec) =>
    new RegExp(`<section\\s+id=["']${sec}["']`).test(indexHtml)
  ),
  "expected sections #operacao, #deteccao, #notificacoes, #fr24, #sistema, #registros"
);
check(
  "(1e) Empty section #fr24 exists without GitHub issue reference",
  /<section\s+id=["']fr24["'][^>]*>\s*<\/section>/.test(indexHtml) && !/Issue\s*#\s*18/i.test(indexHtml.slice(indexHtml.indexOf('id="fr24"'), indexHtml.indexOf('id="fr24"') + 100)),
  "expected clean empty <section id='fr24'></section>"
);
check(
  "(1f) Empty section #registros exists without GitHub issue reference",
  /<section\s+id=["']registros["'][^>]*>\s*<\/section>/.test(indexHtml) && !/Issue\s*#\s*20/i.test(indexHtml.slice(indexHtml.indexOf('id="registros"'), indexHtml.indexOf('id="registros"') + 100)),
  "expected clean empty <section id='registros'></section>"
);
check(
  "(1g) #sync-now, #poll-now, #test-email are inside #operacao",
  (() => {
    const opMatch = indexHtml.match(/<section\s+id=["']operacao["'][\s\S]*?<\/section>/);
    const opHtml = opMatch ? opMatch[0] : "";
    return opHtml.includes('id="sync-now"') &&
      opHtml.includes('id="poll-now"') &&
      opHtml.includes('id="test-email"') &&
      opHtml.includes('id="action-result"');
  })(),
  "expected manual actions inside #operacao"
);
check(
  "(1h) #sync-now, #poll-now, #test-email are NOT in #view-dashboard (Monitoramento)",
  (() => {
    const dashMatch = indexHtml.match(/<section\s+id=["']view-dashboard["'][\s\S]*?<\/section>/);
    const dashHtml = dashMatch ? dashMatch[0] : "";
    return !dashHtml.includes('id="sync-now"') &&
      !dashHtml.includes('id="poll-now"') &&
      !dashHtml.includes('id="test-email"');
  })(),
  "manual actions must be removed from Monitoramento"
);
check(
  "(1i) All six anchor sections have tabindex='-1' so openSettingsSection can focus them",
  ["operacao", "deteccao", "notificacoes", "fr24", "sistema", "registros"].every((sec) =>
    new RegExp(`<section\\s+id=["']${sec}["'][^>]*\\btabindex=["']-1["']`).test(indexHtml)
  ),
  "expected tabindex='-1' on all six anchor sections"
);
console.log("\nScenario 2: showSettingsStep(n) single source of truth");
check("(2a) showSettingsStep function is defined", typeof showSettingsStep === "function");
showSettingsStep(2);
check(
  "(2b) showSettingsStep(2) activates step 2 panel and tab",
  panel2.hidden === false &&
    panel2.classList.contains("active") &&
    panel1.hidden === true &&
    tab2.classList.contains("active") &&
    tab2.getAttribute("aria-selected") === "true" &&
    tab1.getAttribute("aria-selected") === "false",
  "expected step 2 active and step 1 hidden"
);
showSettingsStep(5);
check(
  "(2c) showSettingsStep(5) activates step 5 panel (Sistema)",
  panel5.hidden === false &&
    panel5.classList.contains("active") &&
    panel2.hidden === true &&
    tab5.classList.contains("active"),
  "expected step 5 active"
);

console.log("\nScenario 3: openSettingsSection(sectionId) helper");
check("(3a) openSettingsSection function is defined", typeof openSettingsSection === "function");
openSettingsSection("notificacoes");
check(
  "(3b) openSettingsSection('notificacoes') activates step 3",
  panel3.hidden === false && panel3.classList.contains("active") && tab3.classList.contains("active"),
  "expected step 3 active for 'notificacoes'"
);
openSettingsSection("sistema");
check(
  "(3c) openSettingsSection('sistema') activates step 5",
  panel5.hidden === false && panel5.classList.contains("active") && tab5.classList.contains("active"),
  "expected step 5 active for 'sistema'"
);
openSettingsSection("fr24");
check(
  "(3d) openSettingsSection('fr24') activates step 4 (even while tab button is hidden)",
  panel4.hidden === false && panel4.classList.contains("active"),
  "expected step 4 active for 'fr24'"
);
check(
  "(3e) openSettingsSection and showSettingsStep are globally available on window",
  typeof sandbox.window.openSettingsSection === "function" &&
    typeof sandbox.window.showSettingsStep === "function",
  "expected window.openSettingsSection and window.showSettingsStep"
);

console.log("\nScenario 4: Stepper navigation");
initSettingsStepper();
// Click next on step 1 -> goes to step 2
showSettingsStep(1);
next1to2.click();
check(
  "(4a) Step 1 next button advances to step 2",
  panel2.hidden === false && panel1.hidden === true,
  "expected step 2 after clicking next1to2"
);

// Click next on step 3 -> skips hidden step 4, jumps to step 5
showSettingsStep(3);
next3to5.click();
check(
  "(4b) Step 3 next button jumps to step 5 (Sistema), skipping hidden step 4 (FR24)",
  panel5.hidden === false && panel3.hidden === true,
  "expected step 5 after clicking next3to5"
);

// Click prev on step 5 -> jumps back to step 3
prev5to3.click();
check(
  "(4c) Step 5 prev button jumps back to step 3, skipping hidden step 4",
  panel3.hidden === false && panel5.hidden === true,
  "expected step 3 after clicking prev5to3"
);

console.log("\nScenario 5: Environment-locked settings badge");
const testForm = makeElement();
const pollIntervalInput = makeElement();
pollIntervalInput.name = "poll_interval_seconds";
testForm.elements.poll_interval_seconds = pollIntervalInput;
const parentLabel = makeElement();
parentLabel.append(pollIntervalInput);
testForm.append(parentLabel);

// Setting with source="environment" and locked=true
setField(testForm, "poll_interval_seconds", { value: 60, source: "environment", locked: true });
check(
  "(5a) Environment-locked setting disables field",
  pollIntervalInput.disabled === true,
  `disabled=${pollIntervalInput.disabled}`
);
const envBadge = parentLabel.querySelector(".env-badge");
check(
  "(5b) Environment-locked setting displays .signal.env-badge",
  !!envBadge && envBadge.hidden === false,
  "expected visible .signal.env-badge"
);
check(
  "(5c) Badge contains translated 'Definido por variável de ambiente'",
  envBadge && envBadge.textContent === (tr.pt.settings_locked_env || "Definido por variável de ambiente"),
  `got "${envBadge ? envBadge.textContent : ""}"`
);

// Setting with source="interface" and locked=false
const nonLockedInput = makeElement();
nonLockedInput.name = "operating_phase";
testForm.elements.operating_phase = nonLockedInput;
const nonLockedLabel = makeElement();
nonLockedLabel.append(nonLockedInput);
testForm.append(nonLockedLabel);

setField(testForm, "operating_phase", { value: "shadow", source: "interface", locked: false });
const nonLockedBadge = nonLockedLabel.querySelector(".env-badge");
check(
  "(5d) Non-locked setting has no visible badge",
  !nonLockedBadge || nonLockedBadge.hidden === true,
  "non-locked setting should not have visible badge"
);

console.log("\nScenario 6: Manual actions wired in Operação");
apiLog = [];
syncNow.click();
await new Promise((r) => setTimeout(r, 20));
check(
  "(6a) #sync-now triggers POST /api/boundaries/sync",
  apiLog.some((c) => c.url === "/api/boundaries/sync" && c.method === "POST"),
  `apiLog=${JSON.stringify(apiLog)}`
);

apiLog = [];
pollNow.click();
await new Promise((r) => setTimeout(r, 20));
check(
  "(6b) #poll-now triggers POST /api/poll",
  apiLog.some((c) => c.url === "/api/poll" && c.method === "POST"),
  `apiLog=${JSON.stringify(apiLog)}`
);

apiLog = [];
testEmail.click();
await new Promise((r) => setTimeout(r, 20));
check(
  "(6c) #test-email triggers POST /api/email/test",
  apiLog.some((c) => c.url === "/api/email/test" && c.method === "POST"),
  `apiLog=${JSON.stringify(apiLog)}`
);

console.log("\nScenario 7: Secrets never redisplayed");
check(
  "(7a) SMTP password placeholder is 'Deixe em branco para manter existente'",
  /name=["']smtp_password["'][^>]*data-i18n-placeholder=["']settings_placeholder["']/.test(indexHtml),
  "expected placeholder for smtp_password"
);
check(
  "(7b) All three API key inputs use password type and placeholder",
  ["flightradar24_api_key", "adsbexchange_api_key", "resend_api_key"].every((k) =>
    new RegExp(`name=["']${k}["'][^>]*type=["']password["'][^>]*data-i18n-placeholder=["']settings_placeholder["']`).test(indexHtml)
  ),
  "expected password type and placeholder on all API keys"
);

console.log("\nScenario 8: i18n coverage for sections and locked badge");
const i18nKeys = [
  "settings_section_operation", "settings_section_detection", "settings_section_notifications",
  "settings_section_fr24", "settings_section_system", "settings_section_logs",
  "settings_locked_env", "settings_manual_actions", "settings_operations_title"
];
for (const k of i18nKeys) {
  check(
    `(8) ${k} exists in PT and EN`,
    Boolean(tr.pt[k] && tr.en[k]),
    `missing ${k} in pt/en: pt=${tr.pt[k]} en=${tr.en[k]}`
  );
}

if (failures > 0) {
  console.error(`\nSCENARIO FAILED: ${failures} check(s)`);
  process.exit(1);
} else {
  console.log("\nAll scenarios green");
}
