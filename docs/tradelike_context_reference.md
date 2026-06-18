# Tradelike — Claude Code Context

## What This Project Is

Tradelike is a multi-tenant workforce management SaaS platform for the Australian construction industry. It manages relationships between **work clients** (construction companies) and **work providers** (subcontractors, sole traders, trade companies).

The platform is in pilot with FDO Carpentry. A V2 UI rebuild is underway to replace the original /web/ surface module-by-module. A sandpit/demo instance is also maintained for onboarding.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy (async), PostgreSQL, Alembic |
| /web/ Frontend (legacy) | HTMX, Jinja2, Tailwind CSS, DaisyUI v4, IBM Plex Sans/Mono |
| /v2/ Frontend (current) | HTMX, Jinja2, hand-written CSS, Barlow + Barlow Condensed + JetBrains Mono |
| Mobile | Separate PWA template tree |
| Infrastructure | Railway (hosting), S3 (file storage), Resend (transactional email) |
| Maps | Leaflet |

This stack is deliberately chosen for one-person maintainability. Do not suggest replacing or layering on additional frameworks. **Tailwind/DaisyUI is being phased out** — V2 modules use hand-written CSS only.

---

## V2 vs /web/ — Read This First

The codebase has two parallel UI surfaces:

- **`/web/*`** — original UI, DaisyUI/Tailwind based, currently in production use by pilot client. **Legacy. Being phased out module-by-module as V2 modules ship.**
- **`/v2/*`** — current rebuild, hand-written CSS, modern interaction patterns. **All new module work happens here.**

**For any new feature: build in V2. Do not add features to /web/.**

For bug fixes: fix where the bug is. If a /web/ user-facing bug needs a quick fix, fix it in /web/. Don't try to backport V2 patterns into /web/.

When CC is working in /web/ vs /v2/, the conventions differ significantly — see the relevant section below.

---

## Branching Strategy

Two permanent branches:

- `main` — production. Deployed to Railway pilot (FDO Carpentry).
  Only receives merges from staging when tested and ready to deploy.

- `staging` — active development. Deployed to Railway staging.
  All new features and fixes are made here and tested before merging to main.

Workflow:
- Small changes → commit directly to `staging`
- Major features (V2 modules, multi-session work) → short-lived feature branch off `staging`, merge back to `staging` when complete
- Staging tested and ready → merge `staging` → `main` → deploy to pilot
- Production hotfix → branch off `main`, fix, merge to `main` AND `staging`

Feature branches for V2 modules are short-lived (days to weeks, not months). Each V2 module's branch merges to staging when the module is functionally complete and Codex-reviewed.

---

## Architecture Pattern

```
web routes → coordinators → services → DB
```

- **Routes** handle HTTP concerns only — no business logic, no DB queries inline, no policy enforcement
- **Coordinators** own the transaction/commit boundary. Thin wrappers — call service, commit, return. They orchestrate calls across services and call `await session.commit()`.
- **Services** contain business logic. Two flavours:
  - **Action services** (writes) — e.g. `app/services/asset_actions.py`. Can `flush()`, never `commit()`. Own all auth/capability checks for writes. Validate foreign keys against tenant scope. Fail closed on invalid IDs.
  - **Query services** (reads) — e.g. `app/services/asset_queries.py`. Take `auth_ctx` and enforce tenant scope. No `flush()` or `commit()`.
- **Serializers** (e.g. `_asset_to_dict`) live in their own module — never imported across action/query layer. Place in `app/services/{module}_serializers.py`.
- **Never** put commit logic in a service. **Never** put business logic in a route.

Related coordinator functions are grouped into single files (e.g. `app/coordinators/asset.py`).

### Multi-tenant safety rules (non-negotiable)

These are the rules. Codex flagged each of these as critical findings in the V2 Asset Register review — they were violations that caused real cross-tenant leak risks before backend hardening landed.

1. **Services derive tenant scope from `auth_ctx.acting_party_id`.** Never accept tenant identifiers from route parameters and trust them. If a route accepts `client_id`, the service must validate it against `auth_ctx`, OR (preferred) the route doesn't accept it at all and the service uses `auth_ctx` directly.

2. **All write services validate foreign keys against tenant scope before mutating.** If a write service accepts a `job_id`, `worker_id`, `provider_person_id`, etc., it must verify that referenced entity belongs to the correct tenant graph. Invalid or cross-tenant IDs raise 400 with a clear error.

3. **Capability checks combine with ownership checks.** `require_capability(auth_ctx, "...")` is a coarse first-pass gate. The actual authorisation is the ownership/membership check that follows. Both are required.

4. **Read services take `auth_ctx` and enforce scope.** A query service without `auth_ctx` is a tenant leak waiting to happen. Always pass `auth_ctx` to read services and have them filter by scope.

5. **Fail closed, never silently fall back.** If a foreign-key lookup fails, raise 400. Do not fall back to `auth_ctx.acting_party_id` or default values silently.

### Capability gating exceptions

`checkout_asset()` and `checkin_asset()` use `asset:read` (not `asset:update`) as their first-pass capability gate. **This is intentional, not a bug.** Provider workers need to self-checkout assets via the mobile app, and provider workers only have `asset:read`. The actual authorisation happens in the ownership/link check that follows the capability check. Do not "fix" this without considering the mobile self-checkout path.

### Common architectural violations CC must never make

- ❌ DB queries directly in route handlers — use a service function
- ❌ `await db.commit()` in a service — flush only, coordinator commits
- ❌ Business logic in a coordinator — coordinators orchestrate, services decide
- ❌ `await db.commit()` in a route — route calls coordinator, coordinator commits
- ❌ Creating model instances in a route — that's service layer work
- ❌ Trusting tenant identifiers (e.g. `client_id`) from route parameters without validation — services derive scope from `auth_ctx`
- ❌ Foreign-key trust in writes — validate against tenant scope before mutating
- ❌ Silent fallback when lookup fails — fail closed with 400
- ❌ Action services importing private helpers from query services — extract to shared serializers module
- ❌ Read services without `auth_ctx` — every read takes `auth_ctx` and enforces scope

**The test:** Could this logic be unit tested without an HTTP request? If yes, it belongs in a service. Could a malicious client cause a leak by passing crafted parameters? If yes, the service must validate, not trust.

---

## Settings / Config Columns

`WorkProvider` and `ClientProviderLink` have a `settings` JSONB column for org/relationship config. Defaults are defined as `SETTINGS_DEFAULTS` on the model class; use `model.get_setting(key)` to read with fallback. Some older settings (e.g. `auto_accept_assignments`) predate this pattern and remain as dedicated columns — that's intentional, don't migrate them.

**When to use a dedicated column vs JSONB:** If a setting needs to be queried, filtered, indexed, or constrained at the DB level, it gets its own column. If it's just read-at-runtime config, it goes in `settings` JSONB.

### ClientProviderLink — current shape

**Dedicated columns:**
- `auto_accept_assignments` — assignment goes straight to ACCEPTED/FILLED on publish
- `share_tickets` — client can view worker tickets/licences ONLY (not worker visibility)
- `asset_visibility` — provider can see client asset register (NONE or ALL)
- `notify_client_on_unavailability` — client notified when worker records leave

**JSONB settings (use `get_setting(key)`):**
- `share_leave` — leave label: "On Leave" (True) vs "Busy" (False)
- `allow_provider_session_management` — provider can clock in/out for workers
- `allow_client_session_edit` — client can edit work sessions
- `direct_assignment` — client assigns named workers (True) or org only (False)
- `worker_visibility` — client sees named workers on schedule/workers page

**Dependencies:**
- `direct_assignment=False` → `worker_visibility` forced to False
- `worker_visibility=False` → `share_tickets` and `share_leave` have no visual effect (no named workers to show)

---

## Project Structure

```
app/
  routes/           # FastAPI route handlers (web routes split between v1/v2 modules)
  coordinators/     # Transaction owners, orchestration logic
  services/         # Business logic — action and query services
    *_actions.py    # Write services (flush only)
    *_queries.py    # Read services (take auth_ctx)
    *_serializers.py # Shared dict serializers (no cross-import between actions/queries)

models.py           # All SQLAlchemy ORM models — single file in project root

templates/
  web/              # /web/ legacy templates (DaisyUI/Tailwind)
  web/partials/     # /web/ HTMX partial templates
  v2/               # V2 templates (hand-written CSS, Barlow fonts)
    base.html       # V2 base — shared dropdown/modal/expand JS
    _archetype_a.html # Directory layout (list + detail panel) — Asset Register, Workers, etc.
    _archetype_b.html # Canvas layout — TBD
    _archetype_c.html # Ledger layout — TBD
    {module}/       # Module-specific templates (assets/, workers/, etc.)
  mobile/           # PWA template tree (separate from web)

static/
  v2/css/           # V2 modular CSS files
    _tokens.css     # Design tokens (colors, spacing, typography)
    _reset.css      # Base reset
    chrome.css      # Header, sidebar, nav
    page.css        # Page-level layout
    buttons.css     # Button conventions
    archetype-a.css # Archetype A directory layout styles
    {module}.css    # Module-specific styles
    forms.css       # Form modal shell + form field styles
    modals.css      # Lightbox modal shell (image viewer)
    tables.css      # Table styles
```

---

## V2 Conventions

V2 modules follow strict conventions to keep the surface coherent. Workers V2 inherits these from Asset Register.

### Three Archetypes

V2 organises pages into three reusable layouts:

- **Archetype A — Directory** — list + detail panel. Used for resource registers (Asset Register, Workers, Customers, Providers).
- **Archetype B — Canvas** — full-bleed working area. TBD (likely Schedule, Job Kanban).
- **Archetype C — Ledger** — chronological feed with filters. TBD (likely Timesheets, Activity).

Each archetype has its own base template (`_archetype_a.html` etc.) and CSS file (`archetype-a.css` etc.).

### Mutation Conventions

| Action type | Pattern |
|---|---|
| Create / Edit record | Modal |
| Soft-delete (e.g. retire asset) — reversible | Inline amber confirmation strip |
| Soft-delete while in use (e.g. retire while on hire) — destructive | Inline red confirmation strip with required reason |
| Worker self-action (check out/in asset) | Inline form |
| Lightweight in-place edit (e.g. slot date) | Popover |

Two-tier severity: **amber** (considered/reversible) vs **red/danger** (destructive).

### Modal CSS Namespacing

V2 has two distinct modal types with separate CSS namespaces:

- **`.modal-*`** — form modals (create/edit asset, compliance modals, etc.). Translucent overlay, fixed 640px width. Defined in `forms.css`.
- **`.lightbox-*`** — image lightbox (photo viewer). Dark opaque overlay, fluid width. Defined in `modals.css`.

These are NOT consolidatable — the visual treatment is genuinely different (form modal vs immersive media viewer). Keep them namespaced separately. Module-specific modals (like compliance) should use `.modal-*` and only add module-specific extensions, not redefine the shell.

### V2 Typography Convention

Typography convention refined April 2026 after Workers V2 shipped — section headers and sub-tabs moved from uppercase to Title Case once visual chrome (yellow underline, dividers) was in place to carry hierarchy. Asset Register updated retrospectively for consistency.

The principle: where strong visual chrome (yellow underline, divider, container) carries hierarchy, Title Case reads better. Where the text IS the chrome (status pills, filter tabs, column headers), uppercase emphasises function.

**UPPERCASE — High-level chrome, status, brief labels:**
- Filter tabs (ALL, AVAILABLE, IN USE, etc.)
- Status pills (AVAILABLE, IN USE, RETIRED, OVERDUE, ACTIVE, INACTIVE)
- Table column headers (WORKER, OUT, IN, DURATION)
- Sidebar nav group headers (WORKSPACE, JOBS, TEAM)
- Header chrome (top breadcrumbs, wordmark)
- Modal breadcrumb / super-label (ASSET REGISTER above modal title)

**Title Case — Section structure (with visual chrome doing the hierarchy work, e.g. yellow underline beneath section headers):**
- Detail panel section headers (Properties, Role & Employment, Contact, Compliance, Current Hire, Retirement, etc.)
- Detail panel sub-tabs (Details, Hire, Photos, Compliance)
- Modal section headers (Identity, Equipment Details, Purchase)
- Inline form section headers (Check Out, Check In, Retire This Asset)

**Title Case — Content (data, input labels, action buttons):**
- Field labels in property grids (Category, Serial Number, Make / Model)
- Field labels in modals and inline forms (Asset Number, Worker, Job (Optional))
- Modal titles ("Edit Asset", "Add Compliance Record")
- Action buttons ("Save Changes", "Check Out", "Add Record")
- Compliance type pills (Service, Registration, Inspection — these are data, not status)
- Optional indicators ("(Optional)" with capital O — part of the field label)

**Sentence case — Prose (instruction, guidance):**
- Helper text under labels ("Unique within org")
- Placeholder text in inputs ("Search workers...", "Condition, quirks...")
- Empty state messages
- Validation error messages
- Toast/banner messages

**As-is (don't transform):**
- User-entered data (asset names, worker names, notes content)
- Identifiers (asset numbers like "DW-001", IDs)
- Code-like content (in JetBrains Mono font)

### V2 Date Format

All user-facing dates render as `dd Mmm yyyy` (e.g. `26 Apr 2026`) via the `format_iso_date` Jinja filter. No ad-hoc `[:10]` ISO slicing or inline `strftime` calls in templates.

### V2 Color & Spacing Tokens

All colors and spacing values use CSS custom properties from `_tokens.css`. Never hardcode colour values or spacing in module CSS — extend tokens if needed.

Selection state: 4px amber left border + subtle background tint (`--selection-bg`).

### V2 Directory Filter Row Pattern

Archetype A (directory) modules use a consistent filter row order above the list:

```
[text search]  [primary scope pills]  [secondary refinement]
```

Examples:
- Asset Register: `[Filter by name]` `[ALL/AVAILABLE/IN USE/...]`
- Workers: `[Search workers]` `[MY TEAM/ALL WORKERS]` `[ALL ROLES ▼]`

Text search comes first because finding-by-name is the most common action. Scope pills come second as a primary scope toggle. Secondary refinement controls (dropdowns, multi-select) come last.

Page-level summaries (e.g. "8 workers · 2 your team · 6 cross-org") live in the page header above the filter row, not duplicated within the filter row itself.

### V2 Sub-Tab Sizing

Detail panel sub-tabs use compact sizing (13px font, 10px/14px padding) to accommodate count badges next to tab labels without crowding. Established by Asset Register, adopted by Workers V2 and future modules.

Sub-tabs render as a sibling `.detail-tabs` div immediately below the navy detail header (dark background, light text, yellow `::after` underline on active tab, amber bottom border as baseline). CSS uses `.detail-tabs` / `.detail-tab` / `.count` classes defined in `archetype-a.css` (single source of truth for all directory modules). The header needs `margin-bottom: -1px` to prevent a sub-pixel white gap between the two navy elements.

### V2 Responsive Breakpoint

Single breakpoint: `@media (max-width: 1280px)` triggers narrow mode. Design floor is iPad 10th gen landscape (1080 × 810). Layout tokens in `_tokens.css` (`--sidebar-width`, `--sidebar-width-narrow`, `--list-min`, `--list-max`, `--list-min-narrow`, `--list-max-narrow`).

**Narrow mode (≤1280px):**
- Sidebar collapses to 64px icon rail — labels hidden, tooltips on hover
- Directory list column narrows from `minmax(540px, 620px)` to `minmax(440px, 480px)`
- Detail panel field grids stay 2-column at all widths (detail pane is ~546px at narrow — wider than comfortable mode)
- Modals unchanged — they overlay full viewport and have adequate gutters

**Media queries live co-located** with their component CSS (not in a separate file). Each CSS module has its own `@media (max-width: 1280px)` block at the bottom.

### V2 HTMX Patterns

- **Lazy-loaded tabs** — tabs in detail panels load content on first click via HTMX
- **OOB swaps** — used for refreshing counts, hero photos, alert dots, status counts when other regions update
- **Idempotent JS init** — any JS in a swappable partial uses a flag to prevent re-registration of global listeners (e.g. `window.__hirePickerInit`). Better: hoist shared JS to `base.html` with a one-time-init guard.
- **Error responses** — return 200 with the original container plus inline error message. HTMX 1.9.10 silently discards 4xx responses by default. (See backlog for response-targets extension investigation.)

### V2 Filter / Detail Coherence

When filter or search updates the list in a directory archetype, the response must include an OOB swap to update the detail pane (clear to empty state if selected item is filtered out) and an OOB swap to refresh status filter counts. Otherwise the detail pane shows stale data and counts disappear.

### Capability Wedge State Prevention

Any operation that changes `MembershipRole` must enforce two guards in the service layer:

1. **Self-demotion blocked** — a user cannot demote themselves out of Admin. Check `auth_ctx.person_party_id` against the membership being edited.
2. **Last-admin blocked** — cannot demote the only remaining Admin in an org. Count remaining Admins excluding the current membership; reject if zero.

Code paths that change MembershipRole:
- Worker deactivation (`coordinate_remove_member` — guards already exist)
- Worker edit (`update_worker` — guards added April 2026)
- Future: bulk role changes, automated downgrades, etc.

Why this matters: without these guards a user can lock themselves out (self-demote) or lock the entire org out of admin functions (last-admin demote). Both are recovery-only states requiring direct DB intervention.

### Capability Scope on Routes

Routes should require the minimum capability for the entity they expose. If a query needs to access entities beyond the primary resource for visibility computation (e.g. checking assignment data to determine cross-org worker visibility), do so without requiring the user to have capabilities on those secondary entities. The user is reading workers, not jobs.

---

## Domain Terminology

Use these terms precisely — wrong terminology creates confusion with the client and in the codebase.

| Correct | Never use |
|---|---|
| **tickets and licences** (V2 tab label: **Tickets**) | "competencies" — that's mining vertical language used by competitor LineupBoard |
| **compliance records** | tickets/licences as displayed in V2 (different word, same concept) |
| **work clients** | "clients" alone is ambiguous |
| **work providers** | "subcontractors" in code |
| **slots** | individual schedule entries |
| **assignments** | worker-to-slot relationships |
| **assets** | tools, equipment, vehicles in the asset register |
| **compliance records** | tickets/licences as displayed in V2 (different word, same concept) |
| **hire** | the act of checking out an asset to a worker for a period |

---

## Key Domain Rules

**Assignment status — `SUPERSEDED` vs `WITHDRAWN`**
This distinction is load-bearing and affects provider visibility rules, job status recalculation, history display, and cancel button guards.
- `WITHDRAWN` = clean retraction, no work was done
- `SUPERSEDED` = reassignment after work had already begun or was in progress

Never conflate these two statuses.

**Asset retirement — model-level, not assignment-level**
Asset retirement is an event on the Asset itself (`retired_at`, `retired_by`, `retire_reason`, `retire_notes` columns), not a closure on the active assignment. When retiring an asset that's currently on hire, the assignment closes via `AssetAssignmentStatus.RETIRED` AND the asset's retirement fields are set. Retire reason is required when retiring while on hire.

**`auto_accept_assignments` on `ClientProviderLink`**
Controls whether draft schedule publish transitions assignments to `ACCEPTED`/`FILLED` (auto) or `REQUESTED`/`OFFERED` (manual approval flow).

**Draft schedule workflow**
Copy-week creates `DRAFT` slots/assignments. Publish transitions them to live statuses based on the above flag.

**Compliance records vs status**
A compliance record is a tagged piece of compliance work (Service, Registration, Inspection, Calibration, Warranty, Insurance, Other). It has a `due_date` and optional `completed_date`. The status (OVERDUE, DUE_SOON, CURRENT, COMPLETED) is computed from these dates — not stored. Don't add a status column.

**Worker tickets vs asset compliance — different models, similar UI**
Worker tickets (`WorkerTicket` model) and asset compliance records (`AssetTag` model) look similar in the UI but have different data shapes. Worker tickets have `issued_date`/`expiry_date`, `licence_number`, `issuing_authority`, and free-text `ticket_type`. Asset tags have `due_date`/`completed_date`, an enum `tag_type`, and `label`. Alert thresholds are entity-appropriate: 30 days for asset compliance (DUE_SOON), 60 days for worker tickets (EXPIRING) — different domains, different renewal cycles.

**Sandpit/demo features**
Gated behind `SANDPIT_MODE=true` env flag. Never delete sandpit-only code — use the env flag.

**Beta navigation toggle**
Gated behind `BETA_NAV_ENABLED=true` env flag AND admin role. A header dropdown that lets admin users jump between /web/ and /v2/ versions of pages. On /web/ it shows V2 status for each module (available or "Coming Soon"); on /v2/ it links back to all /web/ pages.

This is a temporary dev/testing affordance — not a permanent product feature. Remove when V2 fully replaces /web/. Module list is a single source of truth in `app/services/beta_nav.py`; update there when V2 modules become available.

Uses role-string check (`"ADMIN" in roles`) rather than capability check (`auth_ctx.can("user:manage")`) for pragmatism — avoids per-route wiring for a temporary affordance. If a user with admin-equivalent permissions but not literal ADMIN role can't see the toggle, they can navigate manually.

---

## Slot Creation Modal (legacy /web/)

`slot_create_modal.html` is the canonical slot creation surface in /web/. It uses AJAX worker loading with leave/busy date badges, pre-checking, time pickers, trade type, and live preview. It posts to the existing `POST /web/jobs/{job_id}/add-slot` route.

**Rewire status:**
- `job_detail.html` — rewired (uses `hx-get` to `/web/jobs/{job_id}/slot-modal`)
- `job_create_modal.html` — pending (no `job_id` at creation time, needs flow redesign)
- `new_slot_popover.html` — intentionally separate (schedule grid fast-add, worker pre-selected from row click)

This will be superseded by V2 schedule work eventually. Don't extend /web/ slot-create patterns into V2.

---

## /web/ Frontend Conventions (Legacy)

For bug fixes in /web/ only. New work is /v2/.

**HTMX + scoped styles**
`<style>` tags injected via HTMX `innerHTML` are silently ignored by browsers. Do not put scoped styles inside partials — they have no effect. Use Tailwind utility classes instead.

**HTMX swap targets**
HTMX-refreshed UI elements must live inside the swapped partial, not outside the swap target. Anything outside the target won't update on navigation.

**Timezone handling**
`tz_offset` must be passed into Jinja2 contexts. On mobile, use direct `getTimezoneOffset()` calls — not hidden inputs.

**Back-navigation pattern**
Schedule grid back-navigation uses `/web/projects?open={id}` — not `/web/projects/{id}`.

---

## Coding Principles

1. **Patch files surgically** — never rebuild a file from memory. Always read the current file before making changes. Ask for the file if you don't have it.
2. **Read-and-report before non-trivial changes** — for any change touching multiple files, security-sensitive paths, or unfamiliar code, first show the relevant current code and confirm understanding before implementing. Especially required for multi-tenant safety, auth/capability work, FK validation, and shared pattern changes.
3. **Partials over duplication** — extract to a partial rather than duplicating template logic.
4. **Single source of truth** — one place for each piece of logic.
5. **Correct architectural layer** — fixes belong in the right layer (service vs coordinator vs route vs template). Don't push logic up or down the stack for convenience.
6. **Design before coding** — for any non-trivial feature, outline the approach and affected files before writing code.
7. **No unnecessary dependencies** — this is a one-person-maintainable codebase. Don't introduce new packages without good reason.
8. **One commit per logical change** — small, focused commits with descriptive messages. Don't bundle unrelated changes.

---

## Database Migrations

**Migration files use sequential numeric prefixes (`001_`, `002_`, …) with descriptive suffixes (e.g. `009_asset_closure_reasons`).**

- `001_initial.py` is **frozen** — do not edit it. It represents the schema at pilot go-live.
- Do NOT run `alembic revision --autogenerate`. Write migrations by hand.
- After creating or editing a migration, rebuild the database from scratch: drop, recreate, then run `alembic upgrade head`.
- **During feature branch development**: each CC session may create new migrations as needed. Chain them off the latest.
- **Pre-merge consolidation**: before merging a feature branch to main (or staging if it's a long-lived V2 module branch), consolidate related migrations created during the branch into a single migration with a descriptive name. Reset the dev DB and verify the consolidated migration produces the correct schema from scratch.
- **Post-merge immutability**: once a migration has been merged to main, it is sealed. Never edit, combine, or remove a merged migration. New schema changes always become new migrations chained off the latest.

---

## Test Suite

815+ tests passing. Run tests after any non-trivial change. Do not break passing tests.

```bash
pytest

# Faster runs during development — skip flaky/slow tests:
pytest tests/ -x -q --ignore=tests/test_bulk_accept.py --ignore=tests/test_org_assignment.py --ignore=tests/test_job_week_schedule.py
```

Asset Register has comprehensive multi-tenant safety test coverage (89 asset tests). Workers V2 should match this density for cross-tenant scenarios.

---

## CC Workflow Conventions

These are the patterns established through V2 work that produce reliable results.

### Read-and-Report Discipline

For any non-trivial change, before implementation:
1. Show the current code at the relevant locations
2. Confirm understanding of what's being changed and why
3. Propose the specific approach
4. Wait for approval before implementing

Skip this only for genuine quick tweaks (one-line fixes, single-CSS-property changes). Default to read-and-report when in doubt.

### Codex Code Review Pattern

For module-completion milestones (e.g. Asset Register, Workers V2), an external Codex review pass is run. Workflow:
1. CC builds the module
2. Codex reviews the codebase (architectural, quality, pattern, tests, multi-tenant safety lenses)
3. CC reads Codex findings, validates each against codebase reality, classifies as confirmed/false-positive/partial
4. Adjusted plan reviewed
5. CC implements fixes
6. Optional: Codex verification pass

**Codex finds, CC fixes, optional Codex verifies** — this is the established loop. Codex review accuracy is roughly 85% — false positives happen (e.g. "this looks like wrong capability" when it's actually intentional for mobile workers). Always validate findings before implementing.

### Read-and-Report Catches Codex False Positives

The C2 finding from the Asset Register review (`checkout_asset()` should require `asset:update`) was a false positive — provider workers self-checkout via mobile and only have `asset:read`. CC's read-and-report pass caught this before implementing. Without that step, a fix to a "security finding" would have broken the mobile self-checkout flow. Always confirm before implementing.

### Commit Hygiene

- Single logical commit per session, with a descriptive message
- Verify after commit: `git log --oneline -3` to confirm the commit landed
- Test count should go up after sessions that add functionality
- Never `git push --force` to shared branches

---

## Environment

- Dev environment: Windows
- Virtual environment: `workforce_env`
- Activate: `workforce_env\Scripts\activate` (PowerShell) or via PyCharm

### Browser Testing — Custom Device Entries

Add these custom devices in Chrome DevTools (Settings > Devices) for V2 responsive testing:

| Device | Width × Height | DPR | Notes |
|---|---|---|---|
| iPad 10th gen Landscape | 1080 × 810 | 2 | **Design floor** — V2 must be comfortable here |
| iPad Air Landscape | 1180 × 820 | 2 | Narrow mode triggers (≤1280px) |
| iPad Pro 11" Landscape | 1194 × 834 | 2 | Narrow mode triggers |
| iPad Pro 12.9" Landscape | 1366 × 1024 | 2 | Comfortable mode (>1280px) |

---

## Common Commands

```bash
# Run dev server
uvicorn app.main:app --reload

# Run tests
pytest

# Run specific test file
pytest tests/path/to/test_file.py

# Faster test runs during dev
pytest tests/ -x -q --ignore=tests/test_bulk_accept.py --ignore=tests/test_org_assignment.py --ignore=tests/test_job_week_schedule.py

# Rebuild database from scratch (drop, recreate, migrate)
# Drop and recreate the DB manually, then:
alembic upgrade head
```

---

## Current State (April 2026)

**In production (pilot — FDO Carpentry):**
- /web/ surface — sign-off UI, schedule, jobs, timesheets, projects, workers, providers, customers, asset register (basic)

**Recently completed on V2:**
- Asset Register V2 — full module (read, CRUD, retire with model migration, hire flow, photos, compliance records). Codex-reviewed. Backend hardened (multi-tenant safety + architectural cleanup). Frontend hardened (modal CSS namespacing, HTMX handler scoping, filter/detail coherence). Bucket 3 cleanup landed (date format, label case, photo position compaction). Forms and modals typography sweep landed.

**Active:**
- Asset Register V2 — about to merge to main
- Migration consolidation pending before merge

**Next:**
- Workers V2 — start fresh on a new branch off updated main, inheriting V2 patterns from Asset Register

**Deferred (backlog):**
- User-toggleable sidebar collapse at comfortable viewports (persist in localStorage or settings JSONB)
- Phone number E.164 normalisation (mobile stored as free-text VARCHAR(20) in local AU format; normalise to +61... at storage time for international `tel:` link compatibility)
- Web multi-photo upload
- Mobile compliance entry (Callum-blocked — pilot user can't add compliance via mobile currently)
- Project planning module (currently messy on staging — recode vs merge decision deferred)
- User-defined enums
- Multi-client sandbox tooling
- Service-level date formatting cleanup (waits for /web/ retirement)
- HTMX response-targets extension investigation
- Dropdown menu Tab cycling and focus trap (deferred from frontend hardening)
- S3 key guessability watch item

---

## Things That Have Failed In The Past — Don't Repeat

- **DB queries directly in routes** — caused multi-tenant leak in Asset Register V2 picker routes (Codex C1). Always go through services.
- **Foreign-key trust without validation** — caused cross-tenant assignment risk in `checkout_asset()` (Codex C3). Always validate FK against tenant scope.
- **Silent fallbacks on lookup failure** — masked bugs and allowed cross-tenant data attachments. Fail closed.
- **Read services without `auth_ctx`** — `get_asset_hire_history()` originally had no auth check. Always pass `auth_ctx` to reads.
- **Modal CSS consolidation attempt** — tried to unify form modal and lightbox shells, then realised they're genuinely different. Kept them namespaced separately. Don't re-attempt.
- **Tightening `asset:read` to `asset:update` for hire mutations** — would break mobile self-checkout for provider workers. Capability is intentional. Don't "fix" it.
- **Silent HTMX 4xx responses** — HTMX 1.9.10 discards them by default. Return 200 with inline error in the original container.
- **Duplicate listener registration on tab swap** — global listeners registered inside swappable partials accumulate on every reload. Use idempotent guards or hoist to base.html.
