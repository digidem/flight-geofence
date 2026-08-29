# Flight-Geofence — UX/UI Improvement Proposal

> **Status:** approved and moved to `docs/UX_REVIEW.md` (was `local/ux-ui-review-proposal.md` git-ignored draft). This is now the implementation source of truth.
> **Baseline:** `node --check` ✅ `pytest -q` 353 passed ✅ `TZ=America/Sao_Paulo node tests/test_fr24_*_vm.mjs` ✅ `docker compose config --quiet` ✅  
> **Screenshots:** `local/ux-review-baseline/ux-*.png` 26 captures (390/768/1280 via `google-chrome --headless --remote-debugging-port=9333` + `BU_CDP_URL`).  
> **Supporting audits:** `local/ux-review-baseline/01-heuristics.md` · `02-design-system.md` · `03-responsive-interaction.md` · `04-a11y.md` · `05-performance-quality.md`.  
> **Policy:** frontend stays dependency-free (`AGENTS.md`). New lib (map, axe, lighthouse) requires explicit approval. `SPEC.md` safety framing ("unverified signal") must be preserved — every event surface keeps the disclaimer.

---

## Executive Summary — Three Biggest Wins

1. **Make it usable on a phone without rewriting it.** Add 3 breakpoints (480/768/1024) and collapse `grid.two` to 1-col `<768`, stack `filters` `<600`, give every `table-wrap` a sticky header + scroll affordance (or card fallback `<640`). This alone fixes the "UI components are unresponsive" complaint (see `ux-dashboard-390.png` / `ux-areas-390.png` / `ux-logs-390.png` where tables clip and panels squeeze). Effort **M**, no new dep, unblocks demos in the field.

2. **Make every mutation honest about its state.** Add `aria-busy` + CSS spinner + `disabled` to every `api()` mutation (`runAction`, `saveSelection`, `saveForm`×5, FR24 toggle/policy/cluster/test, track panel, `loadLogs` pagination). Replace `window.confirm/alert` with an accessible modal, debounce `area-search` 300 ms, add `handleHashRoute` focus management, and fix `review-save` missing error surface. This fixes the interaction-unresponsiveness that isn't about layout (see `03-responsive-interaction.md` D-I1..D-I7).

3. **Fix the information architecture before polishing pixels.** Collapse the 6-tab bar into an overflow menu `<768` (keep Dashboard/Areas/Events always visible; move FR24+Logs to "⋯" overflow), group Settings 5 panels into a stepped workflow with section nav, and flatten the FR24 cluster form (15+ fields) into a 4-step wizard (Identity → Altitude/Categories → Bounds → Areas). Add a persistent SPEC disclaimer banner on every event surface. This reduces click counts (FR24 cluster 9-15 clicks → 4 steps) and prevents misreading signals as accusations.

---

## Prioritized Backlog (P0/P1/P2)

Columns: **ID** · **View/Component** · **Problem (1 line)** · **Evidence ref** · **Proposal (concrete)** · **Effort** · **Needs new dep?** · **SPEC/AGENTS risk** · **Verification**

### P0 — Must fix before field use (blocks task or safety)

| ID | View/Component | Problem | Evidence | Proposal | Effort | Dep? | Risk | Verification |
|----|----------------|---------|----------|----------|--------|------|------|--------------|
| P0-01 | All · `table-wrap` tables (Areas 6cols, Dashboard 7cols, Logs 7cols, Detail) | Tables overflow viewport on mobile with no affordance, header not sticky | `ux-areas-390.png`, `ux-dashboard-390.png`, `ux-logs-390.png` · `index.html:61,72,214` `app.js:667,716,909` · `02-design-system.md` table-wrap, `03-responsive` matrix | Add `@media(max-width:640px)` card fallback **or** sticky header + scroll affordance: `table-wrap {overflow:auto}` + `thead th {position:sticky;top:0;background:var(--surface)}` + `::after` fade shadow on overflow. Column priority: Dashboard hide Telemetry `<768`; Logs hide Latency `<640`. Keep `<table><caption>` + `scope="col"` from 04-A11y. | M | No | None | Resize to 390px → no clipped columns; scroll hint visible; `axe` passes table caption; manual scroll shows sticky header |
| P0-02 | All · mutations (`api()` everywhere) | No loading/disabled/`aria-busy` on mutations — double-click fires duplicate POSTs, no feedback for 0.5-40 s | `03-responsive-interaction.md` D-I1/D-I2 · `app.js:71-88 api()`, `939-959 saveForm`, `1057-1072 runAction`, `728-737 saveSelection`, `891-922 loadLogs` | Wrap every `api()` call site: `button.disabled=true; container.setAttribute('aria-busy','true'); show spinner` before fetch, `finally {disabled=false; remove aria-busy}`. `saveForm` disables its submit; `runAction` already disables but add `aria-busy` + spinner; `loadLogs` disables `#logs-filter`; `loadAreas/loadReviews/loadStatus` add `aria-busy` on `tbody`/`review-list`. Shared helper `withLoading(button, container, fn)`. | M | No (CSS spinner) | None — preserves `AGENTS.md` error surfacing rule | Trigger sync-now / save settings / filter logs at 390px → button disabled + spinner visible + `aria-busy="true"` in AX tree; double-click fires only one network request |
| P0-03 | All · SPEC safety framing | Disclaimer "unverified signal" missing as persistent banner on event surfaces — risk of misreading signals as proof of landing/wrongdoing | G5/E4 in `01-heuristics.md` · `SPEC.md v0.4` safety framing + `AGENTS.md` Detection invariants | Add i18n key `spec_disclaimer_banner` (PT: "Sinais não verificados — não constituem prova de pouso, desligamento deliberado, garimpo ilegal ou irregularidade." EN: "Unverified signals — not proof of landing, deliberate transponder shutdown, illegal mining, or wrongdoing.") Render as non-dismissible `role="note"` banner at top of Dashboard, Events, Event-detail, and email template. Keep `SPEC.md` wording neutral. | S | No | **Preserves** SPEC safety framing; never weaken copy | Visit Dashboard/Events/detail at any width → banner visible above content; `axe` no color-contrast fail; translation toggles PT/EN |
| P0-04 | FR24 · `#fr24-cluster-form` 15+ fields | Flat form with alt min/max, 6 categories, manual bounds 4 inputs, area picker, buffer — 9-15 clicks, error-prone | `ux-fr24-390.png` · `index.html:158-184` 15+ fields · `01-heuristics.md` F1 (sev 3) | Refactor into 4-step wizard (still one `form`, JS step nav, no dep): Step1 Identity (name, buffer, enabled), Step2 Altitude & Categories, Step3 Bounds (auto vs manual + validation hint N>S etc), Step4 Areas (picker + overlap warning). Progress `role="progressbar"` + `<fieldset>` per step + Prev/Next + Save on last. Validation before step advance. | L | No | FR24 doc sweep rule — if copy/tokens change, sweep `README+.env.example+FLIGHTRADAR_API.md+SPEC` together (flag in code comment) | Fill wizard on mobile 390px → each step shows ≤5 controls; Prev/Next work; final Save posts same `FR24ClusterPayload`; invalid N≤S shows inline `error` before advance |
| P0-05 | IA · `nav.tabs` 6 tabs | Tabs crowd/wrap on mobile, no overflow | `ux-dashboard-390.png` 2-row wrap · `index.html:26-33` · `01-heuristics.md` IA-1, `03` matrix | `<768px`: keep 4 primary tabs (Painel, Áreas, Eventos, Configurações) + overflow button "⋯ Mais" containing FR24, Logs. `role="tablist"` + `aria-selected` + `aria-controls` per tab (fix 04-A2/A3). No new dep. At `≥768` show all 6. | M | No | None | 390px → 4 tabs + overflow button visible, no wrap; 768px → 6 tabs row; keyboard Tab → overflow menu via Enter/Space |
| P0-06 | Event detail · `handleHashRoute` `app.js:640-652` | Hash route swap doesn't move focus — keyboard/screen-reader loses context | 04-A4 · `app.js:640-652` no `focus()` | After `detailView.classList.add('active')` + `loadEventDetail`, focus the `h3` or panel: `panel.setAttribute('tabindex','-1'); panel.focus();` Also add `role="tabpanel"` + skip. | S | No | None | Keyboard: click Events → open `#/events/<id>` → `document.activeElement` is inside detail panel; VoiceOver announces new view |

| P0-07 | FR24 · delete uses `window.confirm/alert` + Reviews save has no error surface | Inconsistent confirmation; silent failure on review save | `app.js:401 confirm`, `406 alert`, `772-780` no catch | Replace both with shared accessible modal (`role="dialog" aria-modal="true"` + focus trap, `aria-live` for errors). Review save: add `try/catch` + inline `form-result` (reuse `saveForm` pattern). | M | No | None | Trigger FR24 delete → custom modal with PT/EN copy; Escape closes; Delete still calls `DELETE /api/fr24/clusters`; review save failure shows inline error, not silent |
| P0-08 | All views · empty/loading/error states inconsistent | Dashboard `no_events` muted row only (`app.js:669`), Areas `areas_no_data` muted, Review `review_no_events`, FR24 `fr24_no_clusters`, Logs `logs_no_rows` — all plain `<p class="muted">` with no illustration/CTA; loading only `Event detail Loading…` (`app.js:540`) text; errors inconsistent (`areaFeedback` vs `form-result` vs `alert`) | `02` defect 3 · `ux-detail-390.png` skeleton missing · `05-performance-quality.md` error surfacing matrix | Standardize per view: **Loading** → `aria-busy="true"` on container + CSS skeleton (3 gray bars `class="skeleton"` with `prefers-reduced-motion` kill) instead of plain text; **Empty** → illustration placeholder (inline SVG 120×80 warm `paper` tone) + muted copy + CTA link (e.g. Dashboard empty → "Nenhum sinal — [Selecionar áreas]"; Areas empty → "Nenhum resultado — [Limpar filtros]"; Review empty → "Nenhum evento para calibrar"); **Error/Failed poll** → replicate Logs pattern `#logs-error[role=alert]` for every view (Dashboard warnings `app.js:657-659` already `warning` divs — add `role="status"`; Areas `area-error` already `role=alert` planned). No new dep. | M | No | None — preserves `escapeHtml` + `Intl` | Empty Areas at 390px → illustration + CTA visible; loading dashboard shows skeleton, not blank; `axe` live regions pass; failed `loadAreas` shows `area-error` inline, not stale rows |

### P1 — High impact, polish & accessibility

| ID | View/Component | Problem | Evidence | Proposal | Effort | Dep? | Risk | Verification |
|----|----------------|---------|----------|----------|--------|------|------|--------------|
| P1-01 | Global · responsive breakpoints | No media queries — only `prefers-reduced-motion` | `styles.css:1` `02-design-system.md` "No tokens" · `ux-settings-390.png` narrow panels | Add 3 breakpoints: `480/768/1024` as CSS vars `--bp-sm/md/lg`. Rules: `grid.two {grid-template-columns:1fr}` `<768` → `1fr 1fr` `≥768`; `filters {flex-direction:column}` `<600` → row `≥600`; `metric-grid {grid-template-columns:repeat(2,1fr)}` `<480` → `repeat(4,1fr)` `≥768`. | M | No | None | 320px→1-col grid; 390px→filters stacked; 1280px→4 metrics row; no layout shift at breakpoints |
| P1-02 | Global · `styles.css` maintainability | Single 7.7KB minified line (27 rules + `::root` tokens) unmaintainable, no dark mode | `styles.css:1` · `02-design-system.md` defects 1-2 | Split into `tokens.css` + `components.css` + `layout.css` (still 3 `<link>` or one concatenated build step — no new dep). Keep URL `/static/styles.css` as concatenated entry or update `index.html:7` to 3 links. No framework. | S | No (split) | None — still dependency-free | `node --check`, `docker compose config` still pass; file count change flagged in PR; no visual regression at 390/768/1280 |
| P1-03 | Global · contrast | `--muted #746a70` + `.eyebrow 0.7rem opacity .7` → effective 2.9:1 fails AA | `02-design-system.md` contrast table · `styles.css:1` | Darken `--muted` to `#5f555b` (4.8:1 on paper), remove `.eyebrow opacity:.7` → `opacity:1`, bump `.eyebrow` to `0.75rem` + `700`. Fix `fr24-power` muted similarly. Unify `amber/warning/error/muted/signal` semantics via token table in 02. | S | No | None | WCAG contrast checker shows 4.8:1 on eyebrow; `axe` color-contrast passes; manual toggle PT/EN unchanged |
| P1-04 | Global · typography | `Inter` referenced but never loaded; table `14px` inline | `styles.css:1 font-family:Inter` · `app.js:583 style font-size:14px` | **Option A (proposed):** keep `system-ui` stack explicitly (`font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif`) — no extra load. **Option B:** if brand requires Inter, add `<link rel="preconnect" href="https://fonts.googleapis.com"><link href="Inter 400/600/800">` + `font-display:swap` + self-host note — requires approval as new dep (network). Move `14px` table to class `table--detail`. | S | Option B needs approval | None | With Option A, computed font is `system-ui`; no FOUT; with B, Inter loads with `display=swap` |
| P1-05 | A11y · tabs + panels | Missing `role="tablist/tab/tabpanel"`, `aria-selected`, `aria-controls`, `view` missing `tabpanel` | 04-A2/A3 · `index.html:26-33,36-239` | Add `nav.tabs role="tablist"`; each `button.tab role="tab" aria-selected aria-controls="view-xxx"`; each `section.view role="tabpanel" aria-labelledby="tab-xxx" tabindex="0"`. Toggle `aria-selected` in `app.js:1152` tab click handler + `handleHashRoute`. | S | No | None | `axe` tab-related violations clear; AX tree shows `tablist` with 6 tabs, `tab selected=true` on active |
| P1-06 | A11y · skip-link + live regions | No skip-link; `action-result`/`form-result`/`logs-error`/`area-error` not `aria-live`; tables missing `caption/scope` | 04-A1/A7/A13/A15 · `index.html:55,70,144,212` | Add `<a class="skip-link" href="#view-dashboard">` with `:focus{top:0}`. Add `role="status" aria-live="polite"` to `action-result`, `form-result`×5, `logs-summary`; `role="alert" aria-live="assertive"` to `area-error/logs-error`; `<caption class="sr-only">` + `th scope="col"` per table; `lang-toggle aria-label`. | S | No | None | Keyboard Tab from top lands on skip-link; screen-reader announces filter results; `axe` bypass/label violations clear |
| P1-07 | Areas · `area-search` no debounce, requires Filter click | Typing does nothing until "Filtrar" click; no Enter binding | `03` D-I5 · `index.html:68` `#area-search` + `app.js:1162-1165` only `click` on `#area-filter` | Add `input` listener: `debounce(300ms) → appState.areaFilter.search = value; loadAreas()` + `keydown Enter` also triggers. Keep Filter button as explicit trigger for category/selected changes. | S | No | None | Type "Tupi" → table updates after 300 ms without clicking Filtrar; Filter button still works; network shows debounced `GET /api/areas?search=` |
| P1-08 | Interaction · `fr24-enable-toggle` / `fr24-test` / pagination | Partial loading states (see P0-02) — specific to FR24 toggle, test, logs pagination | `app.js:1205-1287`, `891-922` | Extend P0-02: toggle shows `aria-busy` on `.fr24-power` during `POST /api/settings` or enable call; test button shows spinner; prev/next disable + `aria-label="Logs pagination"` wrapper. | S | No | None | Toggle click → track disabled + spinner; test click → result area `aria-live` announces; logs prev/next disabled correctly |
| P1-09 | Settings · 5 forms flat, locked state unclear | `grid.two` with Workflow/Secrets/Notifications/Noise/Display + Connectivity — flat scroll, no section nav; locked fields look editable | `01` S1/S2 · `ux-settings-390.png` · `app.js:961-972 setField` | Group into **3-step workflow with progress** (replaces 2-section idea): **Step 1 — Operação** (Workflow `operating_phase` + `poll_interval` + Display language/timezone — because `formatTime` depends on timezone), **Step 2 — Detecção & Áreas** (Noise thresholds + flight_providers), **Step 3 — Notificações & Segredos** (Email provider + recipients + Keys + Connectivity tests). Sticky stepper `<nav aria-label="Settings steps" role="tablist">` with `aria-selected` + Prev/Next + Save per step (keeps existing 5 `form` endpoints, just visual grouping via `<fieldset>` wrappers — no API change). Progress `role="progressbar" aria-valuenow`. Locked fields: add `🔒` icon + `aria-describedby="env-locked-note"` + `title` preserved; `disabled` stays via `setField` `app.js:970`. Cross-link from dashboard warnings to correct step. | M | No | Env precedence preserved (`setField` `locked` stays); no API migration | 390px → stepper stacked vertical; 768px → horizontal stepper; locked input shows padlock + tooltip; navigating via stepper updates `aria-selected`; `axe` label violations clear; `loadSettings` still sequential ✅ |
| P1-10 | Event detail · raw table layout | `<table style="width:100%">` label/value rows — dense, not a card | `app.js:583` · `ux-detail-390.png` | Replace with definition card: `<dl class="detail-grid"><dt>Horário</dt><dd>…</dd></dl>` with `dt` muted + `dd` strong, copy link affordances inline. Table card fallback keeps `<table>` at `≥768` but card `<dl>` is default on mobile. Move inline `style=` to class `detail-table`. | M | No | None | 390px → card `dl` single column; 768px → 2-col grid; no inline `style=` remaining |
| P1-11 | Global · inline styles & semantics | `fr24-area-picker max-height:220px` inline, `event-detail` width inline, warning/error/muted/signal colors unmapped | `02` defects 5-6 · `index.html:180` | Replace inline with classes: `.area-picker {max-height:220px;overflow:auto}`; `.detail-table {width:100%;border-collapse:collapse;font-size:14px}`; map `signal` variants to tokens `--signal-inside/failed/warning` + document in `tokens.css`. | S | No | None | No `style=` attr on event-detail table or picker in HTML/JS output |
| P1-12 | Global · tap targets | `input/select/button` <44px, checkbox hit-area small | `03` matrix last row · `styles.css:1` no min-height | Add `input,select,button {min-height:44px}`; `label.check {padding:6px 0}` expanding checkbox hit area; `button.tab {min-height:44px}`. Area checkbox: wrap `<label class="check area-label">` around input + hit area 44×44 via `::before`. | S | No | None | Touch audit at 390px: every interactive element ≥44px tall measured via CDP `DOM.getBoxModel` |
| P1-13 | Global · language/timezone dual path | Topbar `PT` toggle (`app.js:1137-1138` instant `POST /api/settings`) vs Settings → `language/timezone` + Save (`app.js:1203`) — two paths confuse operator, first-paint briefly shows `pt` before `loadSettings` resolves (`app.js:1075-1081`) | `01-heuristics.md` IA click-count 1-3 · `app.js:974-1055 applyTranslations/loadSettings` | Unify: keep both entry points but make them same mutation. Topbar toggle becomes `<select>` or keeps button but calls same `saveForm` helper + `loadSettings` + `loadStatus` + `applyTranslations`; Settings Language/Timezone selects sync via `applyTranslations` (`app.js:999-1007` already syncs `langSelect`/`tzSelect`). Add `localStorage` cache `flight-geofence:lang` / `timezone` written by `loadSettings`, read in `init` before first paint (`app.js:1075`) to prevent flash — still server-authoritative, cache only for initial render. Add `aria-label` on toggle (already in P1-06). | S | No | Preserves `await loadSettings()` gate; cache does not override server | EN browser: first paint eyebrow shows EN, not PT; toggling PT via topbar or Settings both persist and show same `PT` label; `Intl` timezone consistent |
| P1-14 | Login · throttled help & recovery | Login fails with `429/401` shows raw `body.detail` in `#login-error.error` `index.html:17` `app.js:1094-1110` without duration or recovery path; `_login_allowed` `app/main.py:192-196` allows 8/15 min but UI never surfaces 15-min window, retry time, or that password is `ADMIN_PASSWORD` env-configured | 01-heuristics.md L2 (sev 1) + Codex medium finding | Add i18n keys `login_throttled` / `login_retry_in` (PT: "Muitas tentativas — tente novamente em 15 minutos. Use a senha configurada como `ADMIN_PASSWORD` ou contate o operador." EN: "Too many attempts — try again in 15 minutes. Use the password from `ADMIN_PASSWORD` or contact the operator.") Map `429` / 8-failures response to that key instead of raw `detail`. `#login-error` gets `role="alert" aria-live="assertive"` (fix 04-A15) + countdown text. Keep constant-time compare + throttle backend unchanged. | S | No | Preserves security throttling; no auth weakening | Trigger 8 failed logins → 9th shows localized throttled message with 15-min hint + `ADMIN_PASSWORD` recovery line; screen-reader announces via `role=alert`; `axe` passes |
| P1-15 | Logs/FR24 · unexplained terminology | Logs `kind` (`call/observation/detection` `app/i18n.py` `logs_kind_*`) + `disposition` (`outside_pending_confirmation` etc `app.js:787-797`) + FR24 blockers `flag_disabled/missing_api_key/no_enabled_clusters/budget_exhausted_paused` `app.js:328-336` use insider jargon without definition; operator must infer meaning | 01-heuristics.md copy audit (Logs kinds, dispositions) + G-Logs2/R-Logs2 + Codex medium | Add contextual help: Logs header gets info `button aria-label` with tooltip (`title` + `aria-describedby`) — e.g. "Chamadas = requisições ao provedor; Observações = posições retornadas (inclui fora de áreas); Detecções = motivos de não-evento" + disposition short helper "fora — aguardando N confirmações". FR24 `#fr24-blockers.warning` `app.js:335` + `id=fr24-blockers` each code gets expanded localized sentence via existing `fr24_blocker_*` keys plus `title` explaining outcome ("FR24 pausado — orçamento esgotado até <date>"). Reuse existing i18n dictionary, no new dep. | S | No | Preserves SPEC copy; no detection change | Logs view: hover `?` shows kind/detection definitions; FR24 blockers show full sentence with date when paused; PT/EN toggle updates help text; `axe` tooltip accessible via `aria-describedby` |
| ID | Component | Problem | Proposal | Effort | Dep? | Verification |
|----|-----------|---------|----------|--------|------|--------------|
| P2-01 | Search · global command palette | No cross-view search; Areas/Logs filtered separately | Optional palette `Cmd+K` overlay: jump to view, search areas, search events by hex — fuzzy via `appState` — P2, keep as note. No dep if vanilla. | M | No | `Cmd+K` opens palette; type "Jacareacanga" → jumps to Areas filtered |
| P2-03 | FR24 · minimap | SVG sketch 280px cap, no legend | Set `fr24-minimap {max-width:100%}` `<768`; add legend `— território` / `- - limites FR24` below SVG; keep equirectangular sketch (real map only if dep approved). | S | Real map (MapLibre/Leaflet) needs approval | 390px → minimap full-width with legend |
| P2-04 | Perf · virtualization | Areas 500 rows / Review 200 cards could be 3k nodes | Paginate Areas (`offset` already exists) with 50/page or virtualize via `IntersectionObserver` — keep as P2, not blocking. | M | No | Scroll 500-row table without jank |
| P2-07 | Copy · timezone name | `formatTime` shows `Day dd/mm/yyyy at hh:mm` without zone name | Append `Intl` `timeZoneName:"short"` → `· BRT` etc via `formatTime`. | S | No | Timestamp shows `… 14:32 · BRT` at 390/768 |
| P2-08 | Tooling · axe/lighthouse CI | No CI axe/lighthouse; offline run missing | Add `npx axe-core` + `npx lighthouse` in `make check` (or separate `make a11y`). Store JSON under `local/ux-review-baseline/lighthouse-*.json`. | S | Dev dep (axe-core, lighthouse) — needs approval if net-new | CI shows `axe` 0 violations, Lighthouse perf ≥90 |
---

## Wire Descriptions (Top 4 P0 — covers severities 3 and critical IA)

### Wire P0-01 — Tables responsive (390px card fallback)

```
┌─────────────────────────────────────┐ 390px viewport
│ Areas — Tabela como cartões         │
├─────────────────────────────────────┤
│ ┌─ Card 1 ──────────────────────┐   │
│ │ ☑ Monitorar                    │   │
│ │ TI Jacareacanga · PA            │ │
│ │ Tipo: Território indígena       │ │
│ │ Fase: homologada · Fonte: FUNAI│ │
│ └───────────────────────────────┘   │
│ ┌─ Card 2 ──────────────────────┐   │
│ │ ☐ UC Jamanxim · PA              │ │
│ │ Tipo: Unidade de conservação   │ │
│ └───────────────────────────────┘   │
│ [Anterior] [Próxima] (if paginated) │
└─────────────────────────────────────┘

Desktop ≥640px: revert to <table> with sticky thead + fade shadow on overflow-y scroll.
Button `.bulk` sticky below filters. `scope="col"` + `<caption class="sr-only">`.
```

*Annotated screenshot:* `ux-areas-390.png` shows current 6-col clipped table → overlay note "Replace with cards <640; keep table ≥640 with sticky header". Same pattern for Dashboard 7cols, Logs 7cols.

### Wire P0-02 — Global loading state (button + container)

```
Before fetch:           During fetch:                     After (success):
┌──────────────────┐   ┌──────────────────────────┐    ┌──────────────────┐
│ [Sincronizar ◷ ] │ → │ [⟳ Sincronizando... ] (disabled, aria-busy) │ → │ ✓ Atualizado · 12:03 BRT (role=status) │
│  limites oficiais│   │  spinner CSS (12px) + "Sincronizando" │    │  panel aria-busy removed, button re-enabled │
└──────────────────┘   └──────────────────────────┘    └──────────────────┘

Failure:
┌──────────────────────────────────────────┐
│ ⚠ Falha ao sincronizar: timeout · [Tentar novamente]  (role=alert, aria-live=assertive) │
└──────────────────────────────────────────┘
```

*Helpers:* `withLoading(button, statusContainer, async () => api(...))` sets `button.disabled`, `container.setAttribute('aria-busy','true')`, injects `<span class="spinner" aria-hidden="true">` before text, restores in `finally`. Applies to `runAction`, `saveSelection`, `saveForm`, `fr24-*`, `logs`.

### Wire P0-04 — FR24 cluster 4-step wizard (390px)

```
390px — Step 2 of 4: Altitude & Categorias
┌─────────────────────────────────────────┐
│ FR24 · Novo cluster  (2/4) ○○●○  [— progress 50%] │
├─────────────────────────────────────────┤
│ ┌─ Passo 2 · Altitude & Categorias ─┐   │
│ │ Altitude mínima (ft)  [-2000____] │   │
│ │ Altitude máxima (ft)  [10000____] │   │
│ │ Categorias FR24  [fieldsets]      │   │
│ │  ☑ T geral  ☑ H helicóp.  ☑ N n/c │   │
│ │  ☐ P passageiro (custo)            │   │
│ │  ☐ C carga   ☐ J jato exec.       │   │
│ └────────────────────────────────────┘  │
│ [< Anterior]            [Próxima >]       │  ← Prev/Next, Save only on step 4
│ Step 1: Nome+Buffer+Ativo  Step 3: Limites (auto vs 4 inputs)  Step 4: Áreas (picker + overlap warning) │
│ Validation: N>S check shows inline `error` before Próxima enabled. No API change — one POST `FR24ClusterPayload` on final Save. │
└─────────────────────────────────────────┘
Desktop ≥768: wizard same but steps shown as horizontal stepper; area picker `max-height:220px` replaced by `class .area-picker`.
```

*Implementation:* keep single `<form id="fr24-cluster-form">`; wrap fields in 4 `<fieldset data-step>` toggled via `fieldset.hidden`; `progress role="progressbar" aria-valuenow` + `aria-selected` on stepper. Validation via `fr24ClusterNumericBounds` `app.js:134-145` N>S before step advance. Sweep note: if copy changes, update `README`+`SPEC`+`.env.example`+`FLIGHTRADAR_API.md` in one commit.

### Wire P0-05 — Nav overflow (<768)

```
390px:
┌─────────────────────────────────────────────┐
│ Topbar: Flight Geofence Alerts  [PT] [○ Sombra] [Sair] │
├─────────────────────────────────────────────┤
│ Tabs (role=tablist):                        │
│ [Painel] [Áreas] [Eventos] [⋯ Mais ▾]      │  ← 4 primary + overflow
│  overflow menu (when open, role=menu):      │
│  ┌───────────────────┐                      │
│  │ FR24              │                      │
│  │ Logs              │                      │
│  └───────────────────┘                      │
└─────────────────────────────────────────────┘

768px+ : [Painel][Áreas][Eventos][Configurações][FR24][Logs] single row, no overflow.
Keyboard: Tab→tab, ArrowLeft/Right roving, Enter→activate, overflow Enter→open menu, Tab inside menu.
```

*Implementation:* JS `matchMedia('(max-width:767px)')` toggles overflow; `aria-selected` sync on click + hash route. No new dep.

---

## Implementation Phasing (order matters — each phase verified before next)

**Phase 0 — Foundations (1 day, blocks everything):** P1-01 breakpoints + P1-02 split `styles.css` + P1-03 contrast tokens. Verify: `node --check`, `docker compose config --quiet`, 390/768/1280 screenshots no regression, `axe` color-contrast 0.

**Phase 1 — P0 safety + responsiveness (1 week):** P0-01 tables · P0-02 loading/disabled/aria-busy (shared `withLoading`) · P0-03 SPEC banner · P0-08 empty/loading/error skeletons · P0-05 nav overflow · P0-06 hash focus · P0-07 modal + review-save catch · P0-04 FR24 wizard. Verify per backlog Verification column; then `env -u DATABASE_PATH uv run pytest -q` still 353 passed, `ruff` no new errors.

**Phase 2 — P1 polish & a11y (1 week):** P1-05 tab roles · P1-06 skip-link/live regions · P1-07 debounced search · P1-09 stepped Settings · P1-10 detail card · P1-11 inline→class · P1-12 tap targets · P1-13 lang sync · P1-14 login throttled help · P1-15 Logs/FR24 terminology tooltips · P1-04 typography · P1-08 FR24 toggle/test loading. Verify: `axe-core` 0 violations per view, keyboard Tab walk, touch 44px audit via CDP, throttled login shows 15-min localized message.

---

## Non-Goals (explicit)

- No new framework (React/Vue/Tailwind) without explicit approval — violates `AGENTS.md` dependency-free rule. Proposal splits `styles.css` into 3 files still dependency-free.
- No public map of live aircraft positions — SPEC safety framing forbids exposing real-time positions publicly; minimap stays equirectangular sketch unless operator approves MapLibre/Leaflet private deployment.
- No alert copy change weakening "unverified signal" disclaimer — every change preserves/spec-strengthens disclaimer (P0-03).
- No weakening of `escapeHtml`, `Intl.DateTimeFormat` + `timezone`, `await loadSettings()` before render, or mutation error-rollback invariants — all preserved in `05-performance-quality.md` hygiene audit.

---

## Effort Legend

- **S** <1 day, single file, no migration.
- **M** 1-2 days, 2-4 files, minor state change.
- **L** 2-5 days, new workflow or major form refactor.

Total now: P0 8 (3 S + 4 M + 1 L) + P1 15 (10 S + 5 M) + P2 5 (3 S + 2 M) ≈ 10 S + 9 M + 1 L ≈ 3-4 weeks solo, phased P0 (1 week) → P1 → P2 as above.


---

## Four-Doc Sweep Flag

Future FR24-visible changes (budget policy, manual Tracks flow, enrichment retries, retention windows, CAS) must sweep `README.md` + `docs/SPEC.md` + `.env.example` + `FLIGHTRADAR_API.md` together in one commit (`AGENTS.md`). Proposal flags `P0-04` + `P1-09` as potentially FR24-visible if copy changes — sweep required at impl time.

---

## Verification Matrix (how reviewer confirms each fix)

| Category | Check |
|----------|-------|
| IA tabs | 390px → 4 tabs + overflow; 768px → 6 tabs; axe tablist passes; keyboard roving works |
| Responsive tables | 390px → cards, 768px → table sticky header + scroll hint; axe caption/scope passes |
| Interaction loading | Every `api()` site: disable + spinner + `aria-busy` + single request on double-click; failure shows `role=alert` + retry |
| Design tokens | Eyebrow contrast ≥4.8:1; no `style=` attrs; `tokens.css` values documented; Inter option flagged for approval |
| A11y | Skip-link focus; tablist/tab/tabpanel; table caption/scope; live regions; `axe-core` 0 violations; hash-route focus moves |
| Event detail | 390px → `dl` card; no inline `style=`; back link to filtered Events |
| Empty states | Each empty view shows illustration + CTA; not just `muted` paragraph |
| Perf/hygiene | `node --check` + `pytest` + `ruff` no new errors; `escapeHtml`/`Intl` invariants untouched |

---

## Appendix — Raw Evidence Index

| Artifact | Path | Note |
|----------|------|------|
| Screenshots 390/768/1280 | `local/ux-review-baseline/ux-login2-390/768/1280.png` (login), `ux-dashboard-*/.png`, `ux-areas-*/.png`, `ux-events-*/.png`, `ux-settings-*/.png`, `ux-fr24-*/.png`, `ux-logs-*/.png`, `ux-detail-390/768.png` | 26 PNGs via `BU_CDP_URL=http://127.0.0.1:9333` headless 148 + dev server `:8081` `DATABASE_PATH=data/runtime/flight_alerts.db` |
| `node --check` | inline | `node --check app/static/app.js` exit 0 |
| `pytest` | inline | `env -u DATABASE_PATH -u DOWNLOAD_DIR -u FLIGHTRADAR24_API_KEY -u FR24_RETENTION_DAYS uv run python -m pytest -q` 353 passed |
| VM tests | inline | `TZ=America/Sao_Paulo node tests/test_fr24_retention_vm.mjs` + `node tests/test_fr24_track_panel_vm.mjs` all green |
| `docker compose config` | inline | `docker compose config --quiet` exit 0 |
| Axe/Lighthouse | — | Offline run attempted; CDN not reachable. Manual WCAG checklists in `04-a11y.md` / manual per-view Lighthouse reasoning in `05-performance-quality.md`. Recommend online run: `npx lighthouse http://127.0.0.1:8081 --chrome-flags="--headless --remote-debugging-port=9333"` + `axe-core` inject; store JSON under `local/ux-review-baseline/lighthouse-*.json` + `axe-*.json` |
| Route inventory | `app/static/index.html:21-240` (sole SPA shell, 8 views), `app/main.py:390-397` (`/` + `/events/{id}` 302), `app/static/app.js:19-30 appState` keys, `app/i18n.py:7-824 TRANSLATIONS`, `app/static/styles.css:1` tokens |
| Heuristic audit | `local/ux-review-baseline/01-heuristics.md` | 26 heuristic rows + IA map + click counts |
| Design system audit | `local/ux-review-baseline/02-design-system.md` | Token table + contrast ratios + component inventory (14 components) |
| Responsive/interaction audit | `local/ux-review-baseline/03-responsive-interaction.md` | Breakpoint matrix 16 rows + async audit 8 handlers + CDP repro script |
| A11y audit | `local/ux-review-baseline/04-a11y.md` | 23 findings + WCAG checklist + fix literals |
| Perf/quality audit | `local/ux-review-baseline/05-performance-quality.md` | Bundle + `escapeHtml`/`Intl`/`loadSettings` audit |

---
> **Artifact location:** moved from `local/ux-ui-review-proposal.md` (git-ignored) to `docs/UX_REVIEW.md` per user approval `2026-08-28 45fc07a`. Baseline screenshots and audits remain in `local/ux-review-baseline/` (gitignored) for local verification only — do not commit.
