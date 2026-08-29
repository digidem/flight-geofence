# Orchestrator Prompt — Implement `docs/UX_REVIEW.md` in Phases (worktree + PR)

> **Paste this entire prompt to the next agent.** It is self-contained. The next agent MUST act as orchestrator under the contract below, work in a **separate worktree**, and deliver a **PR**. No code has been changed yet — this prompt is the handoff from review to implementation.

---

You are the **orchestrator** for `flight-geofence` UX/UI implementation. Source of truth is `docs/UX_REVIEW.md` (moved from `local/ux-ui-review-proposal.md` at `45fc07a`, baseline `local/ux-review-baseline/` is gitignored — read it via `read` tool, do not commit it). Follow the **orchestration contract** verbatim:

**Contract:**
- Decompose, dispatch, verify, iterate. Substantial or parallelizable work: `task` subagents. Trivial self-contained edits: `edit`/`write` inline.
- NEVER yield before closure. Phase completion is not a yield point. Stop only when every item is green or genuinely `[blocked]`.
- Before dispatch, enumerate the full surface. Expand `docs/UX_REVIEW.md` backlog `P0 8 / P1 15 / P2 5`, audits `01-05`, file list, and `Implementation Phasing 0→1→2→3` into flat `todo` items. Re-read `docs/UX_REVIEW.md`, `app/static/styles.css:raw`, `app/static/index.html`, `app/static/app.js`, `app/i18n.py`, `AGENTS.md`, `docs/SPEC.md`. NEVER work from memory.
- Parallelize maximally. Disjoint-scope edits MUST be parallel `task` in one message. Serialize only when a produced contract (types, CSS tokens, shared modal helper) is consumed next — state the dependency.
- Every `task` self-contained: ≤3–5 explicit target paths (no globs), exact change APIs/patterns, edge cases, observable acceptance criteria. Each `task` MUST say "skip gates/formatters; edit only".
- Verify each phase before next: `node --check app/static/app.js`, `env -u DATABASE_PATH -u DOWNLOAD_DIR -u FLIGHTRADAR24_API_KEY -u FR24_RETENTION_DAYS uv run python -m pytest -q` (353 passed), `TZ=America/Sao_Paulo node tests/test_fr24_retention_vm.mjs && node tests/test_fr24_track_panel_vm.mjs`, `uv run ruff check app tests` (compare worktree vs base via `git worktree`), `lsp diagnostics` on changed files, and for UI phases `BU_CDP_URL=http://127.0.0.1:9333` screenshot at 390/768/1280 + `axe-core` 0 violations. Dispatch fix-up subagents on red, re-verify.
- Commit only on green phase: `git commit -m "feat(ux): phase N — <name>"` (focused). NEVER commit red trees.
- No scope creep/shrink, no "follow-up" relabeling, no `local/` commits.

**Setup — create worktree first:**

```bash
git fetch origin
git worktree add ../flight-geofence-ux-impl -b feat/ux-review-impl
cd ../flight-geofence-ux-impl
# verify baseline before edits
node --check app/static/app.js
env -u DATABASE_PATH -u DOWNLOAD_DIR uv run python -m pytest -q
```

**Phasing — implement exactly as `docs/UX_REVIEW.md` § Implementation Phasing (plus P1-14/15):**

- **Phase 0 — Foundations (1 day, blocks everything):** `P1-01` breakpoints `480/768/1024` as `--bp-*` vars + missing 480 card logic, `P1-02` split `styles.css` → `tokens.css`+`components.css`+`layout.css` (keep `/static/styles.css` as concatenated entry or 3 `<link>` in `index.html:7`, still dependency-free), `P1-03` contrast `--muted #746a70→#5f555b` + `.eyebrow 0.7rem opacity .7→0.75rem opacity:1 700`. Verify `node --check`, `docker compose config --quiet`, 390/768/1280 no regression, `axe` color-contrast 0. Commit `feat(ux): phase 0 — foundations`.

- **Phase 1 — P0 safety + responsiveness (1 week):** `P0-01` tables card fallback `<640` + sticky `thead` + scroll affordance, `P0-02` `withLoading(button,container,fn)` for every `api()` site (`app.js:71-88`, `939-959`, `1057-1072`, `728-737`, `891-922`, `1205-1287`, `1293-1349`) with `aria-busy`+spinner+`disabled`, `P0-03` SPEC banner `role=note` i18n `spec_disclaimer_banner`, `P0-08` per-view skeleton/`aria-busy` + inline SVG 120×80 empty + CTA + `role=alert` replication, `P0-05` nav overflow `⋯ Mais` `<768` + `role=tablist`, `P0-06` `handleHashRoute app.js:640-652` `panel.focus()`, `P0-07` modal `role=dialog` + `review-save` `try/catch`, `P0-04` FR24 4-step wizard (single `form`, 4 `fieldset[data-step]`, `progress role=progressbar`, N>S via `fr24ClusterNumericBounds app.js:134-145`). Four-doc sweep if copy changes (`README`+`SPEC`+`.env.example`+`FLIGHTRADAR_API.md`). Verify per `Verification` column + `pytest` 353. Commit `feat(ux): phase 1 — p0 safety`.

- **Phase 2 — P1 polish & a11y (1 week):** `P1-05` `tablist/tab/tabpanel` + `aria-selected`/`aria-controls`, `P1-06` skip-link + `role=status/alert` `aria-live` + `caption scope=col`, `P1-07` debounced `area-search` 300ms, `P1-09` Settings 3-step workflow `Operação/Detecção/Notificações` stepper `role=tablist` (keep 5 `form` endpoints, visual `fieldset` grouping), `P1-10` `dl.detail-grid` card, `P1-11` inline `style=` → `.area-picker`/`.detail-table` + `--signal-*` tokens, `P1-12` `min-height:44px`, `P1-13` lang `localStorage` cache + unify topbar/Settings, `P1-14` login throttled `429` → `login_throttled` + `role=alert`, `P1-15` Logs/FR24 tooltips `aria-describedby`, `P1-04` `system-ui` stack + `table--detail`, `P1-08` FR24 toggle/test `aria-busy`. Verify `axe-core` 0 per view, keyboard Tab, touch 44px via CDP. Commit `feat(ux): phase 2 — a11y`.

- **Phase 3 — P2 debt (optional, if requested):** `P2-01` `Cmd+K` palette, `P2-03` minimap `max-width:100%` + legend, `P2-04` pagination `50/page`, `P2-07` `timeZoneName:short` → `· BRT`, `P2-08` `axe/lighthouse` CI. Commit `feat(ux): phase 3 — debt`.

**Parallelization guidance per phase:**
- Phase 0: split `tokens.css` vs `components.css` vs `layout.css` + `index.html` links — 3 parallel `task`.
- Phase 1: `P0-01` tables vs `P0-02` withLoading vs `P0-03` banner vs `P0-05` nav vs `P0-06` focus vs `P0-07` modal vs `P0-04` wizard — fan out 7 `task` after `withLoading` helper contract is produced.
- Phase 2: `P1-05/06` a11y vs `P1-07` debounced vs `P1-09` stepper vs `P1-10/11` detail/inline vs `P1-12/13/14/15` — fan out after `Phase 0` tokens.

**Verification gates (run after each phase, before commit):**
```bash
node --check app/static/app.js
env -u DATABASE_PATH -u DOWNLOAD_DIR -u FLIGHTRADAR24_API_KEY -u FR24_RETENTION_DAYS uv run python -m pytest -q
TZ=America/Sao_Paulo node tests/test_fr24_retention_vm.mjs
node tests/test_fr24_track_panel_vm.mjs
uv run ruff check app tests  # zero net-new vs base worktree
# plus lsp diagnostics on changed files via `lsp` tool
# plus for UI phases: start dev server DATABASE_PATH=data/runtime/flight_alerts.db DOWNLOAD_DIR=data/downloads + chrome headless 9333 + BU_CDP_URL screenshots 390/768/1280 + axe-core 0
```

**PR creation (after last green phase):**
```bash
git push -u origin feat/ux-review-impl
gh pr create --title "feat(ux): implement UX review phases 0-2 (P0+P1)" --body "Implements docs/UX_REVIEW.md phases 0-2 (P0 8 + P1 15). Baseline local/ux-review-baseline/ ignored. Verification: node --check, pytest 353, TZ VM tests, ruff 0 net-new, axe 0. Phases committed separately. Closes UX review." --base main
```

**Constraints to preserve (never weaken):**
- `escapeHtml` every `innerHTML` (`app.js:34-40`), `Intl.DateTimeFormat` with `appState.timezone` (never `getTimezoneOffset`), `await loadSettings()` before `loadStatus` (`app.js:1087`), mutation rollback (`checkbox.checked = !checked` `app.js:732`), `ADMIN_PASSWORD` throttle `app/main.py:192-196`, provider failure never counts as disappearance, `local/` + screenshots stay gitignored, `SPEC` safety framing, frontend dependency-free (new dep needs approval), four-doc sweep for FR24-visible copy.

Return terse status when PR is up, not recap.
