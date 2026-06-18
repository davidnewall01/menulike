# Restaurant Site Platform — Codex Context

## What This Project Is

A multi-tenant SaaS that lets restaurants stand up a **beautiful, distinctive website**,
point their own domain at it, and manage their content — sold at ~$30/mo.

We are the **marketing / brand / website** product (the "Popmenu lane"): software-as-the-product,
real revenue from customer #1, **no payment liability, no ordering operations.** We are explicitly
**not** an ordering/payments engine (the "Foodhub lane") — ordering is a future *handoff* to the
restaurant's own Stripe/Foodhub, never something we build.

First customer: **Porto Azzurro** (currently a static Netlify site). Immediate goal: get Porto
Azzurro live on the platform via **concierge** (we load their content by hand) before any
self-serve UI exists.

- `docs/restaurant_platform_design.md` — architecture / design / schema reference
- `docs/restaurant_platform_dev_plan.md` — the phased build plan (Phase 0 → live)

Both are living docs — keep them updated as decisions change.

Greenfield repo. Reuses architectural *patterns* from prior work (Tradelike) but shares no code.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI · SQLAlchemy (async) · PostgreSQL · Alembic |
| Frontend | HTMX · Jinja2 · CSS (see note) |
| Infrastructure | Railway (hosting) · AWS S3 ap-southeast-2 (files) · Resend (email) |
| Billing | Stripe (deferred — not v1) |
| Custom domains | Custom-hostname provider — Approximated 🟡 (or Cloudflare for SaaS) |
| Images | Pillow derivatives now → on-the-fly image CDN later |

Chosen for one-person maintainability. **Do not add or layer on frameworks.**

🟡 **CSS decision (confirm):** the *admin app* can use Tailwind + DaisyUI (internal tooling,
speed). The *public templates* carry the product's whole differentiator — distinctive design —
and DaisyUI's generic components fight that. Lean **hand-written / bespoke CSS per template** for
the public site.

---

## Branching Strategy

- `main` — production, deployed to Railway. Only receives tested merges from `staging`.
- `staging` — active development, deployed to Railway staging.

Small changes → commit to `staging`. Features → short-lived branch off `staging` → merge back
when complete. Tested `staging` → merge to `main` → deploy.

---

## Architecture Pattern

```
routes → coordinators → services → DB
```

- **Routes** — HTTP concerns only. No business logic, no inline DB queries, no policy.
- **Coordinators** — own the transaction/commit boundary. Thin: call service(s), `await
  session.commit()`, return.
- **Services** — business logic, two flavours:
  - **Action services** (writes) — may `flush()`, **never `commit()`**. Own all auth + FK
    validation. Fail closed on invalid IDs.
  - **Query services** (reads) — take tenant scope and enforce it. No `flush()`/`commit()`.
- **Serializers** live in their own module — never imported across action/query layers.
- **Never** commit in a service. **Never** put business logic in a route.

### Multi-tenant safety (non-negotiable)

This is multi-tenant. A **cross-restaurant data leak is the worst bug we can ship.** There are
two scope-derivation paths, and neither may trust route params:

- **Public render:** tenant is resolved from the request `Host` header → site. Public and
  read-only, but still strictly scoped to that one site.
- **Admin app:** tenant = the authenticated owner's own site (from the session). The internal
  admin may act across tenants — explicit and audited only.

Rules:

1. **Scope derives from session/host, never from route params.** A `site_id`/`tenant_id` in a
   param is validated against the session, or (preferred) not accepted at all.
2. **Every write validates FKs against tenant scope before mutating.** A cross-tenant ID → 400.
3. **Every read is scoped.** A query without a tenant scope is a leak waiting to happen.
4. **Fail closed.** A failed lookup raises 400 — never a silent fallback to a default site.

The auth/capability layer can start minimal (internal-admin vs owner) and grow. The scope
discipline above is non-negotiable from day 1.

### Architectural violations CC must never make

- ❌ DB queries directly in route handlers — use a service
- ❌ `await session.commit()` in a service — flush only; coordinator commits
- ❌ Business logic in a coordinator — coordinators orchestrate, services decide
- ❌ Creating model instances in a route — service-layer work
- ❌ Trusting a tenant/site id from route params without validating against session/host
- ❌ Foreign-key trust in writes — validate against tenant scope first
- ❌ Silent fallback on a failed lookup — fail closed with 400
- ❌ Read services / queries without a tenant scope

**The test:** could a malicious request leak another restaurant's data by passing crafted
params? If yes, the service must validate, not trust.

---

## Content model & the content/design boundary (product-specific — read this)

The whole product rests on separating **content** (what the restaurant *is*) from **design
config** (how it *looks*):

- **Content** → relational tables (menu tree, photos, hours, location, details). The canonical pool.
- **Design config** → which template, theme/colours, section order & visibility → per-site
  `settings` JSONB with `SETTINGS_DEFAULTS`.

Principles (from the design doc):

- **Templates are *views* over the shared content model.** A new template rearranges/rethemes
  existing slots. A template that needs a new content *type* is a schema change, not a quick add.
- **Slots are defined by content shape, not presentation.** Model at the **most permissive shape**;
  lesser presentations degrade from it — single hero = `feature_images[0]`, single price = one
  `variant`, unnamed subsection = headingless passthrough.
- **Cap depth; never recurse.** Fixed, named levels only.

### Menu (the deep entity)

Four fixed levels, no recursion: **Menu → Section → Subsection → Item → Variants.**

- Subsection `name` is optional (unnamed = headingless passthrough — handles flat sections).
- Variants are **display-only priced variants** (`label`, `price`) — **NOT** a modifiers/options
  engine. Modifiers are ordering-system territory, which we hand off, not build.
- Multiple menus per restaurant is core (food + drinks minimum).
- `availability_note` is plain text ("Lunch 12–3pm"), not structured scheduling.
- Storage: normalised tree, one table per level, FK'd to parent.
- **Ordering is an explicit `position` column on every level — never table/row order.** Relational
  tables have no inherent order; `ORDER BY position` within each parent. Also enables drag-reorder.
- How menus appear (tabs / scroll / pages, per-dish photos vs text rows) is the *template's* call,
  not content.

### Media

- Binaries in **S3** (`*_key` + metadata in DB). **Never** DB blobs, **never** base64 in HTML.
- **One photo library per site** is the source of truth; hero / gallery / about / item images are
  *roles referencing into it*, not separate uploads.
- Keep originals untouched; **strip EXIF/GPS on ingest**; normalise rotation.
- Generate derivatives (Pillow sizes now; image CDN later). A `focal_point` (x,y) drives
  cross-template cropping via `object-position` / CDN URL params.

---

## Hosting & custom domains

- **Subdomain-first:** every tenant at `{slug}.<platform>.app` (one wildcard DNS record + wildcard
  TLS), tenant resolved by `Host`. This subdomain is *permanent* (preview + fallback live site) —
  **`noindex` it.**
- **Custom domains:** via the custom-hostname provider — register the hostname by API; it issues +
  renews the cert and proxies to the Railway origin with `Host` intact (so tenant resolution still
  works). Go-live = *attach domain* (additive), not a deploy.

**Concierge DNS foot-guns (burn these in):**
- The customer adds **one** DNS record. Everything else is automatic.
- **Never touch their MX records** — that's their email. Only the web records (A/CNAME).
- **Don't let them cancel old hosting until the new site is confirmed live.**
- Never collect the customer's registrar password (use screen-share / delegated access).

---

## Settings / config (JSONB pattern)

Per-site design config lives in a `settings` JSONB column with `SETTINGS_DEFAULTS` on the model;
read via `get_setting(key)` with fallback.

**Dedicated column vs JSONB:** if a setting must be queried, filtered, indexed, or constrained at
the DB level, it gets its own column. Read-at-runtime config goes in `settings` JSONB. **Content
is always relational, never JSONB.**

---

## Migrations

- Write migrations **by hand**. Do **not** run `alembic revision --autogenerate`.
- **Naming:** `NNN_descriptive_name.py` (e.g. `001_site_and_menu_tree.py`). The `revision` string
  inside the file matches the prefix (`'001'`). `down_revision` references the previous number
  (`'001'` → `'002'` chains as `down_revision = '001'`).
- **Numbering freezes on push to staging.** While a migration is local-only, keep its number as
  the next increment. Once pushed to `staging`, that number is sealed — never renumber. If two
  developers collide, the later one renumbers before push.
- After creating/editing a migration, rebuild the DB from scratch (drop, recreate,
  `alembic upgrade head`).
- Consolidate a feature branch's migrations into one descriptive migration before merge.
- **Post-merge immutability:** a merged migration is sealed. Never edit/combine/remove it; new
  changes are always new migrations chained off the latest.

---

## CC Workflow Conventions

- **Read-and-report before any non-trivial change:** show the current code, confirm understanding,
  propose the specific approach, **wait for approval** before implementing. Skip only for genuine
  one-line tweaks.
- **Browser verification is a hard gate.** Tests don't catch wedge states or UX issues. A change
  isn't done until it's verified working in the browser.
- **Codex for milestone reviews:** Codex finds, CC validates each finding against codebase reality
  (≈85% accuracy — false positives happen), CC fixes, optional Codex verify pass. Always validate
  before implementing.
- **Commit hygiene:** one logical commit per session, descriptive message; verify with
  `git log --oneline -3`. Never force-push a shared branch. Honour explicit "don't commit until
  confirmed" gates.

---

## Scope discipline (don't let it creep back)

**v1 / concierge-first:** template site + custom domain · menu · photos · restaurant details —
loaded by us, for Porto Azzurro.

🔭 **Deferred — do NOT build yet:** self-serve owner app · onboarding wizard · Stripe billing ·
design/template switcher · templates 2 & 3 · events · reviews · marketing capture · ordering.

**Never build an ordering or payments engine.** Ordering is always a handoff — an "Order Now"
button to the restaurant's own Stripe/Foodhub.

---

## Environment

- Dev: Windows / PowerShell / PyCharm
- Virtual env: 🟡 name TBD (e.g. `restaurant_env`)

```bash
# Run dev server
uvicorn app.main:app --reload

# Tests
pytest

# Rebuild DB from scratch (drop + recreate manually, then)
alembic upgrade head
```
