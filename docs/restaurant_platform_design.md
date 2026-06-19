# Restaurant Site Platform — Architecture, Design & Schema

> **Living document.** Decisions get added and edited here as the design evolves. Each
> entry is a decision we've actually made, not a wishlist. When something changes,
> update the section *and* add a line to the Changelog at the bottom so we can see how
> thinking moved over time.
>
> Status markers: ✅ decided · 🟡 leaning / provisional · ❓ open question · 🔭 roadmap (not v1)

Last updated: 2026-06-19

---

## 1. Product context & scope

A productised SaaS that lets restaurants stand up a **beautiful, distinctive website**
themselves, point their own domain at it, and manage their own content — sold at a low
monthly price (~$30/mo working assumption).

**Positioning (the lane we're in):**
- We're the *marketing / brand / website* product (the "Popmenu lane"): software-as-the-product,
  real money from customer #1, **no payment liability, no 24/7 ordering ops.**
- We are explicitly **not** the ordering/payments operations business (the "Foodhub lane"):
  that model only works at huge scale, monetises on transactions + hardware, and drags you
  into chargebacks, PCI, and a 24/7 support desk.
- Differentiator: genuinely well-designed, distinctive templates — *not* generic off-the-shelf
  themes (which are the "very average" sites we're beating). Distinctive **but templatable**,
  never bespoke-per-client.

**v1 scope ✅**
- Template-based site + custom domain
- Menu (the deep entity)
- Photos / media
- Restaurant details (identity, hours, location, contact)
- Self-serve multi-tenant platform, with **concierge onboarding** for the first cohort

**Roadmap 🔭 (model-aware, do not build yet)**
- Events
- Reviews / testimonials
- Customer capture / marketing campaigns
- Online ordering — and even then it's an **"Order Now" handoff** to the restaurant's own
  Stripe / Foodhub, never an ordering engine we build

---

## 2. Architecture principles (the durable rules)

These are the load-bearing ideas every other decision hangs off.

1. **Content vs presentation split.** The *content model* (what the restaurant **is** —
   menu, photos, hours, story) is stored once and is completely separate from *design config*
   (which template, theme/colours, section order & visibility — how it **looks**). This split
   is what makes everything else work.

2. **Templates are views over a shared content model.** A template renders the same content
   pool in its own arrangement + theme. New templates are cheap *to the exact extent* they
   only rearrange / retheme / re-lay-out content that already exists. A template that needs a
   new *kind* of content (e.g. a hero video) is a schema change — the "content shape leak."

3. **Slots are defined by content shape, not presentation.** "Single hero background" vs
   "square carousel" are two presentations of one slot (`feature_images`), not two slots.

4. **Model every slot at the most permissive shape; lesser presentations degrade from it.**
   The recurring trick across the whole schema:
   - `feature_images` is a list → single hero = `[0]`, carousel = all
   - `variants` is a list → single price = one entry
   - menu `subsection` is always present → "no sub-grouping" = one unnamed, headingless subsection
   - A list can always render as "just the first"; a single value can't expand into a list.

5. **Cap depth; never go recursive.** Fixed, named levels (e.g. Menu → Section → Subsection →
   Item) beat arbitrary nesting. If something wants one level deeper than the schema allows,
   that's a signal to question the design, not to deepen the schema.

6. **Document the public pages first.** The content model falls *backward* out of "what does
   this page need to display." Design the output, and the schema + editors are largely implied.

7. **Build 1 template for real, wireframe 2 more for slot discovery.** Schema = the union of
   slots across ~3 deliberately-different templates (minimal / photo-heavy / content-rich).
   Don't design the template *engine* from a single example; let it emerge from a few concrete
   templates. (Templates four-plus should be cheap rearrangements of the same slots.)

---

## 3. Templating architecture — theme · layout · content · blocks ✅

Principle 1 (content vs presentation) splits the *presentation* side one level deeper. What we
loosely call a "template" is really **four layers**, and keeping them separate is what lets
templates stay coherent *and* flexible at once.

1. **Theme** — *site-level, one choice.* The design language: type, palette, spacing scale,
   component styling, overall feel. The **coherence guarantee** — pick it once and everything
   inherits it. Implemented as design tokens (§5).
2. **Layout** — *per-page, selectable.* Within a theme, how a given page-type arranges its
   content (menu as text-columns vs photo-grid; home as full-bleed vs split hero; an events
   page). Layouts render *in the theme*, so mixing them can't break the look — coherent by
   construction.
3. **Content** — the slot / role pool (§8). **Presentation-independent**, so it survives
   theme/layout switches: change template, content persists; the new layout consumes what it
   needs, gaps prompt, surplus lies dormant. (The non-destructive-switch payoff of the
   content/presentation split.)
4. **Blocks** — for *narrative* pages (Our Story; 🔭 Events): an ordered collection of
   `{heading?, body, image_ref?}` units the owner composes. The **same bounded-collection
   primitive as the menu** (explicit `position`, CRUD + reorder), generalised.

**The "template per page" question, resolved.** *Can a client pick a different template for each
page* (classic home, photofull menu, fun events page)? Yes — but the per-page thing they pick is
a **layout**, under **one site theme**. One theme = coherence; per-page layouts = the genuine
variation. That delivers the flexibility (photofull menu, events page) *without* the
Frankenstein-site risk that "a full template per page" would invite. It's how Squarespace-class
builders work — proven, not novel risk.

**Structured vs narrative pages.**
- **Structured pages** (home, menu, gallery, visit) — known data shapes; purpose-built layouts
  fed by roles / menus.
- **Narrative pages** (Our Story; 🔭 Events) — freeform owner content; the block primitive.
- 🟡 **Scoping line:** *don't unify everything into blocks yet.* "Everything is a block — even a
  menu-block, a hero-block" is a real, elegant end-state, but it's a page-builder engine, and
  building that before customer #2 is over-rotation. Two mechanisms for now: fixed layouts for
  structured pages, blocks for narrative ones.

**PoC posture — fused now, separable in code.** Right now theme + layout are **fused** into one
per-customer template (the flagship). No theme-picker, no layout-picker. The separation lives in
the **code structure** (tokens vs templates, §5), so surfacing the split later is *config, not
rewrite*.

🔭 Deferred: the per-page **layout selector**, the multi-theme **library / marketplace**, and
template **switching** UI. The seams (token/template split, presentation-independent content) go
in now so these stay cheap later.

---

## 4. Surfaces

Three distinct surfaces by audience — easy to conflate, important to separate.

1. **Public site** — the rendered restaurant pages diners see (home/hero, menu, about,
   gallery, contact). This is the *output*; document it first because it drives the schema.
2. **Owner admin app** — where the restaurant manages its site:
   - **Onboarding** = a wizard *skin over the editors* + domain connect. Build editors once;
     onboarding just sequences them. (sign up → name + pick template → run editors → preview →
     connect domain / stay on free subdomain)
   - **Content** editors — Details, Menu, Photo library
   - **Design / Appearance** — template picker + live preview, theme, section order & visibility
     (kept *separate* from Content — mirrors the content/presentation split)
   - **Account & Billing** — login/profile, subscription + payment method + invoices
     (Stripe customer portal does most of this), domain status
3. **Internal / platform admin** — needed from day 1 *because* we concierge: tenant list,
   open/manage any restaurant, run hand-onboarding.

---

## 5. Tech stack

Carried over from existing patterns; this product reuses the architectural style but is its own
thing. The front-end approach for the public templates is now decided (✅, was 🟡).

- **Backend:** FastAPI · SQLAlchemy (async) · PostgreSQL · Alembic (hand-written migrations)
- **Admin frontend:** HTMX · Jinja2 · Tailwind + DaisyUI — the CRUD UI, where DaisyUI's
  components earn their keep.
- **Public site rendering ✅:** server-rendered **Jinja2 — no JS framework.** Restaurant sites
  are content-heavy, SEO-critical, interactivity-light; SSR gives fast first paint, works
  without JS, and reads Postgres **directly, with no API boundary.** A second stack (Astro/Next)
  would double the toolchain and force an API layer — the wrong tax for a solo team, solving
  problems we don't have.
- **Public styling ✅:** **hand-authored CSS driven by design tokens** (CSS custom properties).
  Per-tenant theming is *runtime* — each site sets its own token values, so tokens drive
  everything: swap the token set and the whole site re-themes. Maximum craft (design quality *is*
  the product), native theming, no build pipeline. **DaisyUI is *not* used on the public side** —
  it reads generic; public is bespoke.
- **Public interactivity ✅:** **Alpine.js** for the few declarative bits (mobile menu,
  scroll-spy, lightbox). No framework.
- **Template code structure ✅:** `themes/` (token sets — the *theme* layer) · `layouts/`
  (per-page Jinja, referencing tokens only, never hardcoded colour — the *layout* layer) ·
  `_partials/` (shared: nav, footer, dish, block, gallery). Public render route: resolve site by
  `Host` → load theme tokens + content → render the page's layout. Physically separate folders =
  the theme/layout seam (§3) is real in code even while fused in the product.
- **Hosting:** Railway (staging + production)
- **Media:** AWS S3 (ap-southeast-2)
- **Email:** Resend
- **New for this product:** Stripe (billing), a custom-hostname provider (see §6), an image
  CDN when needed (see §7)

Architectural non-negotiables inherited: routes HTTP-only → coordinators own the commit
boundary → services flush only; IDOR checks at top of every service; UTC storage everywhere;
capability-based auth; settings JSONB with `SETTINGS_DEFAULTS`.

---

## 6. Hosting & custom domains ✅

**The model:** the app resolves the tenant from the request `Host` header → looks up the
domain → loads that tenant's content + template config → renders. App logic is trivial; the
infra (HTTPS for customer-owned domains) is the only real work.

**Phasing:**
- **Subdomains first (day 1):** every tenant gets `{slug}.<platform>.app` behind one wildcard
  DNS record + one wildcard TLS cert. Instant, zero per-customer setup. This subdomain is a
  *permanent* address (doubles as preview before launch and as the live site for anyone who
  never connects their own domain). **`noindex` it** so the preview doesn't pollute search.
- **Custom domains (the upgrade):** front the Railway app with a **custom-hostname provider**.
  Register the hostname via API, they issue + auto-renew the cert and proxy to the Railway
  origin with the `Host` header intact.
  - ✅ **Provider: Approximated.** ~$20/mo for <100 domains, ~$0.20/domain after. Dedicated IP,
    **apex domains work for everyone** (the deciding factor), human support. The ~$20/mo over the
    near-free alternative is noise at our scale; what it buys is clean apex + support exactly at
    the DNS step where non-technical owners struggle.
  - Considered and rejected: **Cloudflare for SaaS** — free for the first 100 custom hostnames,
    then $0.10/mo each. Cheapest, but clean **apex** support needs Enterprise, which is friction
    precisely where low-tech owners struggle.

**Go-live is "attach domain," not a deploy.** The site is already live on the subdomain; a
custom domain just points a second name at the same running site.

**Concierge DNS checklist (foot-guns):**
- ❌ Never collect the customer's registrar username/password — liability. Use screen-share,
  delegated access (GoDaddy etc.), or "you read the record, they type it."
- ❌ Never touch their **MX records** — that's their email; only edit the web records (A/CNAME).
- ❌ Don't let them cancel old hosting until the new site is confirmed live (fallback safety).
- The customer's whole job = add **one DNS record** at their registrar. Everything else (cert,
  routing, rendering) is automatic.

🔭 Self-serve DNS guidance later: auto-detect their provider → written step-by-step with
screenshots + copy-paste values → live "connected ✓" verification. Videos last, if ever.

---

## 7. Media / photos ✅

- **Stored, not embedded.** Binaries → S3 (existing bucket pattern, `*_key` reference in DB
  with metadata). Never DB blobs. Never base64 in HTML.
- **One photo library per site is the source of truth.** Hero / gallery / about / item images
  are *roles referencing into it*, not separate uploads. Upload once, assign roles.
- **Keep originals untouched;** generate derivatives from them. **Strip EXIF/GPS on ingest;**
  normalise rotation.
- **Derivatives strategy:**
  - 🟡 Start: a few fixed sizes via Pillow on upload.
  - Graduate to an **on-the-fly image CDN** (Cloudflare Images / imgix / Cloudinary) once the
    (template × size × crop) matrix hurts — which, with several templates, will be soon.
- **Focal point** solves cross-template cropping (same source → wide banner here, square tile
  there). Store an (x,y) focal point; render via CSS `object-position` or an image-CDN URL param.

> **Build status (2026-06-19):** the photo-library foundation is built and browser-verified —
> upload → S3 → per-site library (view / alt / delete), format-agnostic (JPEG/PNG/WebP). Roles,
> focal point, tags, and derivative sizing are *not yet* built (deferred per above).

---

## 8. Content model — slot inventory

The "content pool": the union of every slot any v1 template might ask for. *(shape, cardinality,
required/optional.)* Presentation config (template, theme, section order) is **not** here — it's
the Design surface.

**Identity** (site-level)
- `restaurant_name` — text, single, **required**
- `logo` — image, 0..1, optional (fallback: wordmark of name)
- `tagline` — short text, single, optional

**Home / hero**
- `feature_images` — image list, 1..N, **required** (single-hero uses `[0]`; carousel uses all)
- `hero_heading` — text, single, optional (defaults to `restaurant_name`)
- `hero_subheading` — short text, single, optional

**About**
- `about_story` — rich text, single, optional
- `about_image` — image ref, 0..1, optional

**Menu** — nested entity, see §9

**Photos** (the library; everything else references in)
- `photos` — image list; each: `s3_key`, `focal_point`, `tags` (food/interior/exterior),
  `alt_text`, `order`
- `gallery` — ordered selection from `photos`, 0..N, optional

**Hours**
- `opening_hours` — per-day open/close ranges; closed days; multiple ranges/day (lunch + dinner)

**Location & contact**
- `address` — structured (street, suburb, state, postcode, country), **required**
- `geo` — lat/lng, optional (geocoded; drives map pin)
- `phone`, `email` — text, optional
- `social_links` — list of {platform, url}, optional

**Calls to action**
- `booking_url` — text, optional (OpenTable etc.)
- `order_url` — text, optional (their own Stripe/Foodhub — the "Order Now" handoff)

**SEO / meta** (site-level, mostly derivable)
- `meta_title`, `meta_description`, `og_image`, `favicon` — optional, sensible defaults

**Modelling notes**
- Photo library is the source; image slots are *roles* referencing into it.
- "Featured / signature dishes" = a `featured` flag on `menu_item`, **not** a parallel content set.
- Required set is tiny (name, ≥1 feature image, menu, address); everything else degrades
  gracefully — which is what makes templates swappable.
- **Narrative content is block-composed (§3).** About/Our Story and 🔭 Events are an ordered list
  of content blocks (`{heading?, body, image_ref?}`) — the same primitive as the menu. The single
  `about_story` + `about_image` above is the **degenerate one-block case**; the block model
  generalises it for richer stories and for Events later.

🔭 Deferred slots: `events`, `reviews`/testimonials, marketing capture, ordering.

---

## 9. Menu schema ✅ (the deep entity)

**Hierarchy: four fixed levels, no recursion.**

```
Menu        → Dinner, Drinks, ...
  Section   → the "tabs": To Start, Pizza, Mains, Dolci   (presentation: tabs/anchors/pages = template's call)
    Subsection → Bread, Antipasti, Insalate                (name OPTIONAL → unnamed = headingless passthrough)
      Item    → the dish (+ dietary tags, optional image, featured flag)
        Variants → label + price                           (single price = one entry)
```

- **Multiple menus per restaurant is v1 core**, not later (almost every restaurant has food +
  drinks at minimum). *(Confirmed against Porto's demo: Eat and Drink are simply two menus.)*
- **Subsection is uniform but optionally unnamed** — a flat section (e.g. "Pizza") is one
  nameless subsection rendered without a heading. Avoids the "items have two possible parents"
  problem; the renderer always walks the same tree.
- **Variants = display-level priced variants only** (Small $14 / Large $20, Glass / Bottle).
  **Not** a modifiers/options/add-ons engine — that's ordering-system territory we explicitly
  hand off.
- **Availability** ("Lunch 12–3pm") = a plain `availability_note` text field on the menu, not
  structured time-based switching.
- **How menus appear** (tabs vs scroll vs pages, per-dish photos vs text rows) is the template's
  job — content carries only structure + order.

**Storage — normalised tree, one table per level (NOT a flat denormalised table).**
A flat "one row per item with group columns" table breaks down: group renames duplicate across
rows, group-level data has nowhere to live, empty sections can't exist, and variants don't fit.

```
menus(id, restaurant_id, name, description?, availability_note?, position)
sections(id, menu_id, name, description?, position)
subsections(id, section_id, name?, position)
menu_items(id, subsection_id, name, description?, dietary_tags?, image_id?, featured, position)
menu_item_variants(id, item_id, label?, price, position)
```

- **Ordering is explicit, never row order.** Relational tables have no inherent order — a
  `SELECT` without `ORDER BY` is undefined. Every level has a `position` column; `ORDER BY
  position` within each parent. Integer positions with gaps (10, 20, 30); renumber occasionally.
  This is also what enables drag-to-reorder in the editor.
- 🟡 `variants` could be a child table (above) or a JSONB column on `menu_items` — small bounded
  list owned with the item. Child table if we'll query/constrain variants; JSONB if we just
  render them. Either is defensible.
- The **editor** can present the whole tree as one indented, drag-reorderable list — normalised
  underneath, table-like on top. Wrapper levels (unnamed subsection) auto-created and hidden
  until a named group is wanted.

> **Build status (2026-06-19):** menu tooling is functionally complete — CRUD at every level,
> reparent (move-item), drag-reorder within a parent, expand/collapse. This is the reusable
> bounded-collection primitive the block model (§3) generalises from.

---

## 10. Open questions / next ❓

- [ ] Validate the 4-level menu model against the **Drinks** menu (wine → Red/White/Sparkling).
- [ ] Detail the remaining content entities (hours, location, about) to the same depth as the menu.
- [ ] Decide `variants` storage: child table vs JSONB.
- [x] ~~Pick the custom-hostname provider~~ → **Approximated** (decided 2026-06-18; see §6).
- [ ] Pick the image CDN (and when to switch from Pillow).
- [x] ~~Front-end approach for the public templates~~ → **SSR Jinja + hand-authored CSS design
  tokens + Alpine.js; no JS framework, no DaisyUI on public; `themes/`·`layouts/`·`_partials/`
  structure** (decided 2026-06-19; see §3, §5).
- [ ] **Name the flagship template.** *(in progress 2026-06-19)*
- [ ] **Design the content-block primitive** — narrative pages (Our Story now, Events later); §3.
- [ ] **Build the flagship template** (the "build 1 for real" of principle 7), co-designed with
  the site-level slots it needs: hero (`feature_images`), `gallery`, `opening_hours`, plus the
  Our Story narrative page.
- [ ] Wireframe the 2 non-flagship templates for slot discovery (Photofull, Modern).
- [x] ~~Confirm whether this lives in its own repo / stack instance~~ → **own standalone repo** (decided).

---

## Changelog

- **2026-06-19** — **Templating architecture added (§3).** The "template" splits into four
  layers — **theme** (site-level, one), **layout** (per-page, selectable, renders *in* the theme),
  **content** (presentation-independent roles/slots), **blocks** (narrative pages). Resolves
  "template per page" as *per-page layout under one site theme* — flexibility without Frankenstein
  sites. Structured vs narrative pages distinguished; "everything is a block" deferred as
  over-build. Theme + layout **fused for the PoC**, kept separable in code.
- **2026-06-19** — **Front-end approach decided (§5, was 🟡).** Public sites render **SSR Jinja +
  hand-authored CSS design tokens + Alpine.js** — no JS framework, no DaisyUI on public. Code
  structure `themes/` · `layouts/` · `_partials/` makes the theme/layout seam real in code. Admin
  keeps HTMX · Jinja · Tailwind + DaisyUI. (Astro/Next considered and rejected: doubles the stack
  and forces an API boundary for a solo team.)
- **2026-06-19** — Content model: **narrative content recorded as block-composed (§8);**
  `about_story`/`about_image` noted as the degenerate single-block case. Build-status notes added
  to §7 (photo library) and §9 (menu tooling) reflecting what's now shipped.
- **2026-06-18** — Custom-domain provider **decided: Approximated** (✅, was 🟡). Clean apex for
  every customer + human support outweighs the ~$20/mo over Cloudflare for SaaS. §6 updated;
  Cloudflare recorded as considered-and-rejected.
- **2026-06-18** — Initial document. Captured: positioning & v1 scope; architecture principles;
  three surfaces; hosting & custom-domain approach (subdomain-first → custom-hostname provider);
  media/photo architecture; full content-model slot inventory; menu schema (4 fixed levels,
  normalised tables, explicit `position` ordering, display-only variants).
