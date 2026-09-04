# Issue #15 — Implementation Plan

Repo: `digidem/flight-geofence`
Branch: `ux/15-eventos` (forked from `4821519 main`, post-#13 and #14)
Worktree: `worktrees/issue-15`
Scope: rebuild `#view-events` as a review queue + right-hand investigation drawer; repoint `#/events/{id}` to Eventos + drawer; implement three-opener browser-history semantics; extract `renderEventDetailCard()`; add `loadEventReviewCounts()`. No backend changes, no new statuses, no new endpoints.
## Round-1 BLOCKER fixes (Sonnet)

Four BLOCKERs from Sonnet round 1; all addressed below.

### BL1 - opener focus restoration survives the tab activation rewrite

The plan's `setEventOpener(id, button, "events")` captured a button that is destroyed when `tab.click()` runs `loadReviews()` (which rewrites `#review-list.innerHTML`). **Fix:** the capture moves to AFTER `loadReviews()` completes, using a stable selector (`[data-event-id="{id}"]`) written into the new card on the next render. Concretely: in `loadReviews()`, after rendering, find the card with `data-id` matching `pendingOpenerEventId` and set its open button as `eventOpener.focusEl`; clear `pendingOpenerEventId`. The "Abrir evento" click handler in `loadReviews()` sets `pendingOpenerEventId = id` and calls `location.hash = "#/events/{id}"`.

### BL2 - FR24 track panel belongs in `#view-events`, not `#view-event-detail`

The `#event-track-panel` markup is moved out of `<section id="view-event-detail">` (which becomes a standalone fallback #22 may remove) into `<section id="view-events">` (the new home for the drawer). `setupEventTrackPanel()` continues to wire the same DOM element; only its parent section changes. Both the drawer and the standalone detail view call `setupEventTrackPanel(event)`.

### BL3 - keep `#review-refresh` (or guard the binding)

Decision 9's markup includes `<button id="review-refresh" class="button ghost dark" type="button" data-i18n="monitoramento_refresh">Atualizar</button>` (reusing the existing key) inside `.eventos-toolbar`. The handler at `app.js:1890` continues to work; the wire is preserved.

### BL4 - `eventOpener.view` is actually consulted

The close path consults `eventOpener.view`:
- If `view === "events"` and `#view-events.active`, restore focus to the captured button.
- If `view === "events"` and the tab is no longer active, drop focus (the captured element is destroyed).
- If `view === "dashboard"` and `#view-dashboard.active`, restore focus to the dot.
- Otherwise drop focus.

Implementation: `if (eventOpener && eventOpener.focusEl && document.body.contains(eventOpener.focusEl) && viewIsActive(eventOpener.view)) { ... }` where `viewIsActive(view)` checks the appropriate primary view's `.active` class.

## Final key strategy

The plan adds 6 new i18n keys: `eventos_title`, `eventos_drawer_aria`, `eventos_needs_review`, `eventos_classification_actions`, `eventos_empty_state`, `eventos_open_action`. All distinct EN/PT pairs. Existing review translation keys (`review_unreviewed`, `review_useful`, `review_noise`, `review_uncertain`, `review_save`, `review_notes`, `col_review`) and the four `email_*` keys are reused unchanged.

## Verified pre-implementation facts

- View section `#view-events` in `app/static/index.html:89-95` contains `#review-filter`, `#review-list`, prev/next pagination, and the existing select. The new layout fits inside the same view element.
- `app/static/app.js:1271` `reviewCard()` is a one-shot template literal returning an `<article class="review-card" data-id="…">`. The card already has `data-id`; we add an "Abrir evento" button as an additional child.
- `app/static/app.js:1288` `loadReviews()` fetches `/api/events?limit=N&offset=M&review_status=…` and renders via `events.map(reviewCard).join("")`. The pagination state and global reload paths are unchanged.
- `app/static/app.js:837` `loadEventDetail()` builds detail markup inline. Extraction: pull everything from line 854 (`const hexLinks = …`) through line 882 (`container.innerHTML = …`) into a new `renderEventDetailCard(event)` returning the inner HTML (no container write). The track-panel wiring stays in `loadEventDetail` so the existing "always wired" behavior is preserved.
- `app/static/app.js:940` `handleHashRoute()` only matches `#/events/{id}`. The drawer opens via the same hash. The current branch activates `#view-event-detail`; we change it to activate `#view-events` + open the drawer.
- `/api/status` returns `events.review.{unreviewed, useful, noise, uncertain}` (already used by `loadStatus()` metrics tile). `loadEventReviewCounts()` reads the same payload.
- `positionLinks(lat, lng)` is the existing helper (`app/static/app.js:772`); no alias introduced.
- Browser-history semantics: `location.hash = "..."` fires `hashchange`; `history.pushState()` does NOT. Escape uses `history.back()` if there is an in-app opener (i.e. a previous hash entry in history) and `history.replaceState(...)` on direct-loaded draws.

## Decisions

### Decision 1 — Drawer as an in-view panel (not a modal overlay)

The drawer is a `<aside id="eventos-drawer" class="eventos-drawer" hidden>` inside `#view-events`. At ≥1024px it docks to the right (`grid-template-columns: minmax(0, 1fr) 380px`). At <1024px it positions absolutely over the list and becomes full-screen below 600px. This satisfies the responsive wireframe without introducing a new view.

### Decision 2 — `loadEventReviewCounts()` (new, small, owns the chips)

```js
async function loadEventReviewCounts() {
  const status = await api("/api/status");
  const counts = status?.events?.review || {};
  const order = ["unreviewed", "useful", "noise", "uncertain"];
  const chips = order.map((k) => {
    const labelKey = `review_${k}`;
    const count = counts[k] ?? 0;
    return `<button class="eventos-status-chip" data-status="${k}" data-count="${count}" type="button">${escapeHtml(t(labelKey))} <strong>${count}</strong></button>`;
  }).join("");
  const container = $("#eventos-status-chips");
  if (container) container.innerHTML = chips;
}
```

Chips are buttons with `data-status` for the existing four statuses. Clicking a chip sets `#review-filter.value` to the status and calls `loadReviews()` (and `loadEventReviewCounts()` to refresh). The existing `#review-filter` select stays (keyboard parity) and stays in sync with the chip selection. The chip count comes from `/api/status`, not from the events list — that's the issue's explicit "uses /api/status events.review.*".

### Decision 3 — Three-opener model via `setEventOpener()` + `handleHashRoute()`

```js
let eventOpener = null; // { id, focusEl: HTMLElement|null, view: "dashboard" | "events" }
function setEventOpener(id, focusEl, view) { eventOpener = { id, focusEl, view }; }
function clearEventOpener() { eventOpener = null; }
```

- **Opener A (Eventos queue list)**: clicking "Abrir evento" in a card calls `setEventOpener(event.id, button, "events")` then sets `location.hash = "#/events/{id}"`. The hashchange fires `handleHashRoute()`.
- **Opener B (Monitoramento map dot)**: same as A but `view = "dashboard"`. (Monitoramento already sets `location.hash = "#/events/{id}"` on dot click per #14.)
- **Opener C (direct load)**: no opener set. `handleHashRoute()` activates Eventos + drawer, Escape uses `history.replaceState(...)`.

`handleHashRoute()`:
1. Activate `#view-events` (no `aria-selected` round-trip; the tab handler does that).
2. Capture the matcher; if the URL matches `#/events/{id}`:
   - Trigger `loadEventReviewCounts()` and `loadReviews()` (idempotent; existing `Promise.all` style).
   - Resolve the event client-side from the existing `/api/events` payload (`limit=500`, same as today).
   - If found, render the drawer via `openEventDrawer(eventId)`.
   - If not found in the cache, fetch fresh and resolve.

### Decision 4 — `openEventDrawer(eventId)` (replaces `loadEventDetail` for the Eventos path)

```js
async function openEventDrawer(eventId) {
  const drawer = $("#eventos-drawer");
  if (!drawer) return;
  // fetch / resolve from /api/events (limit=500)
  const result = await api("/api/events?limit=500");
  const event = result.events.find((e) => e.id === eventId);
  if (!event) {
    drawer.innerHTML = `<p class="muted">${escapeHtml(t("eventos_empty_state"))}</p>`;
    drawer.hidden = false;
    return;
  }
  drawer.innerHTML = renderEventDetailCard(event);
  drawer.hidden = false;
  // wire the review form (delegated handler is module-level, see Decision 5)
  wireDrawerForm(event);
  // track panel — always wired
  await setupEventTrackPanel(event);
}
```

### Decision 5 — Form handling (review-save in the drawer)

The existing `reviewCard` click handler is module-level (per #13's pattern: "register EXACTLY ONCE here (delegated) instead of per event-detail render"). For #15 we add a single delegated handler on `#eventos-drawer` that wires the review form when the drawer renders. Saving calls `loadReviews()` (refreshes the list) and `loadEventReviewCounts()` (refreshes the chips). Existing `loadStatus()` is also called if any global state (e.g. `#phase-badge`) needs to refresh.

### Decision 6 — `renderEventDetailCard(event)` extracted helper

The inline detail markup from `loadEventDetail` is extracted into a function that returns the inner HTML (no `container.innerHTML = …` write). The function uses the existing `positionLinks()`, `aircraftHexLinks()`, `registrationLinks()`, `callsignLinks()`, `providerLinks()`, `translateClassification()`, `eventLabel()`, `formatTime()`, `escapeHtml()`, and the existing translation keys. `loadEventDetail()` (the standalone detail view for `#view-event-detail` that #22 may remove) keeps its `container.innerHTML` write and calls `renderEventDetailCard(event)` instead of building the markup.

### Decision 7 — `handleHashRoute()` rewrite

```js
function handleHashRoute() {
  const hash = window.location.hash || "";
  const match = hash.match(/^#\/events\/([a-f0-9-]+)$/i);
  if (match) {
    const tab = $("#tab-events");
    if (tab) tab.click();
    openEventDrawer(match[1]).catch(() => {});
    return;
  }
  // hash isn't an event-detail pattern → close drawer
  const drawer = $("#eventos-drawer");
  if (drawer && !drawer.hidden) {
    drawer.hidden = true;
    drawer.innerHTML = "";
    if (eventOpener && eventOpener.focusEl && document.body.contains(eventOpener.focusEl)) {
      try { eventOpener.focusEl.focus(); } catch {}
    }
    clearEventOpener();
  }
}
```

The Events tab's click handler already routes to `loadReviews()` for `view === "events"`, so activating it kicks the queue load. The `setEventOpener()` is called from the "Abrir evento" click handler (case A) and from the Monitoramento map-dot click (case B). Case C (direct load) leaves `eventOpener` null.

### Decision 8 — Escape and Back semantics

- **Escape with in-app opener (A or B)**: if `history.length > 1`, call `history.back()`. The browser pops the `location.hash` to the previous URL (no event-detail pattern) and the `hashchange` handler closes the drawer.
- **Escape with no opener (C, direct load)**: call `history.replaceState(null, "", window.location.pathname + window.location.search)` to clear the hash without a new history entry, then close the drawer.
- **Browser Back**: same as Escape for A/B; the URL falls off the event-detail pattern.

Bound to `document.addEventListener("keydown", …)` once (module init) and only when the drawer is open.

### Decision 9 — Rebuild `#view-events` body

```html
<section id="view-events" class="view" role="tabpanel" aria-labelledby="tab-events" tabindex="0">
  <div class="eventos-shell">
    <div class="eventos-toolbar">
      <h2 data-i18n="eventos_title">Eventos</h2>
      <label><span data-i18n="col_review">Filtro</span><select id="review-filter">
        <option value="" data-i18n="review_all">Todas as revisões</option>
        <option value="unreviewed" data-i18n="review_unreviewed">Aguardando revisão</option>
        <option value="useful" data-i18n="review_useful">Útil</option>
        <option value="noise" data-i18n="review_noise">Ruído</option>
        <option value="uncertain" data-i18n="review_uncertain">Incerto</option>
      </select></label>
      <div id="eventos-status-chips" class="eventos-status-chips"></div>
    </div>
    <div class="eventos-body">
      <div class="eventos-list">
        <div id="review-list"></div>
        <div class="actions"><button id="review-prev">Anterior</button><button id="review-next">Próxima</button><span id="review-pagination-info"></span></div>
      </div>
      <aside id="eventos-drawer" class="eventos-drawer" role="region" aria-label="…" hidden>
      </aside>
    </div>
  </div>
</section>
```

### Decision 10 — CSS additions (only existing tokens)

```css
.eventos-shell { display: flex; flex-direction: column; gap: 16px; }
.eventos-toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.eventos-status-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.eventos-status-chip { /* inherits .button ghost */ padding: 6px 12px; border-radius: 999px; }
.eventos-status-chip[data-count="0"] { opacity: 0.5; }
.eventos-status-chip.active { background: var(--burgundy); color: var(--paper); }
.eventos-body { display: grid; gap: 16px; grid-template-columns: 1fr; }
@media (min-width: 1024px) {
  .eventos-body { grid-template-columns: minmax(0, 1fr) 380px; align-items: start; }
}
.eventos-list { display: flex; flex-direction: column; gap: 12px; }
.eventos-drawer { padding: 16px; background: var(--paper); border: 1px solid var(--line); border-radius: 8px; }
@media (max-width: 1023px) {
  .eventos-drawer { position: fixed; bottom: 0; left: 0; right: 0; max-height: 50vh; z-index: 10; box-shadow: 0 -8px 16px var(--shadow); }
}
@media (max-width: 599px) {
  .eventos-drawer { max-height: 100vh; }
}
```

### Decision 11 — `reviewCard()` minimal extension

```js
const openBtn = `<button class="button ghost dark review-open" type="button" data-i18n="eventos_open_action">Abrir evento</button>`;
return `<article class="review-card" data-id="${escapeHtml(event.id)}">
  <div><strong>${eventLabel(event.event_type)} · ${hexDisplay}</strong> · ${regDisplay}<p>${escapeHtml(event.reason)}</p><p class="muted">${event.area_names.map(escapeHtml).join(", ")} · ${escapeHtml(formatTime(event.occurred_at))}</p></div>
  ${openBtn}
  <label>...</label>
  <label>...</label>
  <button class="button secondary review-save">${t("review_save")}</button>
</article>`;
```

A single delegated click handler on `#review-list` (added in the same `$$(".review-card")` loop in `loadReviews()`) wires the open button: `setEventOpener(id, button, "events"); window.location.hash = "#/events/" + id;`.

### Decision 12 — `#/events/{id}` mapping via Monitoramento (case B)

The Monitoramento map dot already calls `window.location.hash = "#/events/{id}"` per #14. The `setEventOpener` for case B must be set BEFORE the hash assignment so the drawer's escape-handler knows the opener. I'll add a tiny wrapper at the Monitoramento map dot click site: `setEventOpener(id, dotAnchor, "dashboard"); window.location.hash = "#/events/" + id;`.

### Decision 13 — Test plan

`tests/test_eventos_vm.mjs` covers:

- **Case A** (Eventos queue list): render the list, click "Abrir evento" on a card → drawer opens with that event. Click "Abrir evento" on a different card → drawer updates without remounting the list (`#review-list` DOM identity preserved).
- **Case B** (Monitoramento map dot): synthetic click on a map dot sets `location.hash = "#/events/{id}"` and `setEventOpener(id, dot, "dashboard")`. The hashchange triggers `handleHashRoute` which activates Eventos and opens the drawer.
- **Case C** (direct load): set `location.hash = "#/events/{id}"` with no prior opener → drawer opens. Press Escape: drawer closes and `history.replaceState` is called (no new history entry). `eventOpener` stays null.
- **Back navigation**: pressing browser Back with an opener uses `history.back()`; the URL falls off the event-detail pattern and the drawer closes.
- **Status chips**: `loadEventReviewCounts()` populates the chips with the four status counts from `/api/status`.
- **Chip click**: clicking a chip sets `#review-filter.value` to that status and calls `loadReviews()` + `loadEventReviewCounts()`.
- **Empty queue copy**: when no events match the filter, the list area shows `t("eventos_empty_state")`.
- **Review save from drawer**: after save, `loadReviews()` and `loadEventReviewCounts()` are called; the chip counts and list reflect the change.

## File-by-file plan

### `app/i18n.py`

Add 6 new keys under PT/EN (parallel to Monitoramento). All distinct.

### `app/static/index.html`

Replace `#view-events` body (lines 89-95). Keep all existing `id`s (`#review-filter`, `#review-list`, `#review-prev`, `#review-next`, `#review-pagination-info`) plus the new `#eventos-status-chips` and `#eventos-drawer`.

### `app/static/app.js`

Refactor:
- `loadEventDetail()` — extract the inline markup to `renderEventDetailCard(event)`. The function still does its own `container.innerHTML = …` for the standalone detail view (which #22 may remove).
- `handleHashRoute()` — repoint to activate Eventos + drawer.
- `reviewCard()` — add the "Abrir evento" button. Wire the click handler inside `loadReviews()`.
- `loadReviews()` — add chip count refresh + tab click handler delegation for the open button.
- Add `loadEventReviewCounts()` (new, small, idempotent).
- Add `openEventDrawer(eventId)` (new, idempotent, can be called repeatedly).
- Add `setEventOpener(id, focusEl, view)` and `clearEventOpener()`.
- Add `eventOpener` module-level state.
- Add Escape-key handler at module init.
- Update Monitoramento's map dot click (line ~1067) to call `setEventOpener` first.

### `app/static/components.css`

Add `.eventos-*` hooks per Decision 10.

### `tests/test_eventos_vm.mjs` (new)

Mirrors `tests/test_monitoramento_vm.mjs`. Stub all relevant elements. Drive the three opener paths + review-save flow.

## Verification matrix (run before Sonnet review)

1. `uv run ruff check app tests` — zero net-new.
2. `make check` — full pytest suite passes.
3. `node --check app/static/app.js` — parses.
4. `node tests/test_eventos_vm.mjs` — new VM harness green.
5. `node tests/test_monitoramento_vm.mjs` — regression guard.
6. `node tests/test_shell_nav_vm.mjs` — regression guard.
7. `node tests/test_fr24_track_panel_vm.mjs` — regression guard.
8. `node tests/test_hex_links_vm.mjs`, `node tests/test_fr24_retention_vm.mjs` — regression guard.
9. `docker compose config --quiet` — compose unchanged.

## Out of scope (do not address in this lane)

- Removing `#view-event-detail` (deferred to #22 per the issue).
- New `GET /api/events/{id}` endpoint (issue explicitly says client-side resolution only).
- New event statuses (only the four existing).
- `fr24_event_tracks_enabled` gate (always wired per #14).
- Arrow-key queue navigation.
- A new hash route other than `#/events/{id}`.
- A general hash router.