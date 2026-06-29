# Restaurant Site Platform — Architecture, Design & Schema

> **Living document.** Decisions get added and edited here as the design evolves. Each
> entry is a decision we've actually made, not a wishlist. When something changes,
> update the section *and* add a line to the Changelog at the bottom so we can see how
> thinking moved over time.
>
> Status markers: ✅ decided · 🟡 leaning / provisional · ❓ open question · 🔭 roadmap (not v1)

Last updated: 2026-06-20

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

**PoC posture — switching shipped; theme/layout still fused per template.** Three templates now
exist — **Linen** (centred-light flagship), **Slate** (dark, vertical-nav), **Olive** (split +
carousel) — named by material aesthetic, never per-client. A **site-level `template` field + an
Appearance template-picker are built**: an owner switches template from the admin and the public
site re-renders, content intact. Within each template, theme + layout are still **fused** into one
self-contained bundle (§5); there is no separate theme- or layout-picker yet.

🔭 Still deferred: the per-page **layout selector** and the multi-theme **library / marketplace**.
(Template *switching itself* is no longer deferred — it shipped.) The seams (token/template split,
presentation-independent content) keep these cheap later.

---

## 3b. Template strategy — purpose-fit, not just pretty 🔭

> Sharpened during competitive research (June 2026, vs Sociavore/BentoBox). The moat isn't "a dozen
> pretty templates" — it's **a dozen templates each purpose-fit by TYPE, SHAPE, and CAPACITY**. That's
> three dimensions of fit generic builders (one-size templates) and font-freedom platforms (Sociavore)
> structurally don't have. A menulike template is a *look + a content-shape + a capacity*, all tuned
> to guarantee beauty.

**Three dimensions every template declares:**

1. **Best-fit descriptor (restaurant TYPE)** — each template advertises who it's for, surfaced in the
   template picker. *Linen = "classy restaurants, cafes, focused menus."* The picker guides owners to
   self-select the right template for their content, which both prevents bad outcomes (wrong-shape
   content in the wrong template) and reinforces the always-beautiful promise. Positions menulike as
   the platform that *understands restaurants*, not a template dump.

2. **Content-SHAPE fit** — templates fit a menu *architecture*, not just an aesthetic. Two shapes
   identified so far:
   - **Discrete-small-menus (Linen):** a few separate menus (Food, Drinks), each modest. Tabs = *which
     menu*. Editorial, whitespace-heavy — the aesthetic *depends* on modest content volume.
   - **Big-sectioned-single-menu (🔭 future — Indian/Chinese/diner/large-pub):** ONE large menu, many
     sections (Starters, Chicken, Lamb, Seafood, Breads…). Nav = *jump to a section* within one long
     scrolling menu, with scroll-tracking section-nav (the pattern Gusto's real site used). A big menu
     *wants* this; forcing it into Linen's discrete-menu tab model is a mismatch.
   - The data model (menu→section→subsection→item) already holds any shape; templates differ in how
     they *render and navigate* it.

3. **Designed CAPACITY (max menus)** — a template declares how much it holds beautifully. *Linen ≈ 8
   menus* (and modest sections each). The capacity is a **feature, not a limitation** — same logic as
   "Linen uses these two fonts": the constraint *is* the quality guarantee. (Rhetorical check: what
   restaurant has 8 *menus* live at once? Almost none — so the cap rarely bites in practice, it just
   prevents the absurd case.) The cap lives in the template's manifest/config, read by the menu-list
   screen.
   - **Enforced at the THREE menu-creation entry points** (a cap is only real if every door is
     guarded): (a) create by hand, (b) create by extraction, (c) **section split/move** — promoting a
     section to its own menu is *also* menu-creation through a side door, and the easiest to forget.
     (This third door is exactly what created the Gusto 13-tab overflow — a section-split spree.)
   - Lean: **hard block** at the limit ("Linen supports max 8 menus — combine some or switch
     template") over soft warn, consistent with the constrain-to-guarantee-beauty philosophy. (Build-
     time call.)

**The unifying principle: CONSTRAIN → GUIDE → DEGRADE** (same philosophy as the font/theme
constraints, §3):
- **Constrain** — cap menus / curate fonts, so the beauty-breaking case can't happen.
- **Guide** — the picker's best-fit descriptors + config-screen alerts steer owners to the right
  template/structure before they hit a wall.
- **Degrade** — even so, render gracefully past the ideal (e.g. mobile menu-tabs scroll + centre-on-
  tap) so it never *breaks*, just isn't *optimised*. The graceful fallback is the backstop, NOT the
  primary solution — prevention (capacity) does the heavy lifting.

**Status:** Linen ships today as the discrete-small-menus template (its implicit capacity ~8). The
declared best-fit/shape/capacity *properties*, the picker descriptors, the config-screen alerts, and
the 3-entry-point cap enforcement are 🔭 **Phase C (template-infrastructure / "factory") work** —
captured here as the strategy; built when the factory exists. The big-sectioned-menu template is a
future addition once the factory is in place and a customer of that shape pulls for it.

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
- **Template code structure ✅ (as built — revised):** each template is a **self-contained
  bundle**, not a shared `themes/`·`layouts/`·`_partials/` split. `app/templates/public/{name}/`
  holds its own `base · home · _nav · _footer · tokens`, with `app/static/themes/{name}/{name}.css`
  alongside. Internal references are **direct within the bundle**; dynamic resolution happens
  **only at the route entry** (`resolve_template` → falls back to the flagship; `page_path`). A
  curated `AVAILABLE_TEMPLATES` allowlist (not a folder-scan) gates what owners can pick.
  *Why the change from the planned split:* templates diverge on **nav and base structure**
  (vertical vs split nav, full-bleed vs split layout), so a shared-partials split leaves the
  divergent parts shared and forces per-template retrofits. Self-contained bundles keep each
  template's `_nav`/`base` its own. The theme/layout seam (§3) still lives in `tokens.html` vs the
  layout templates *within* each bundle.
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
- 🟡 **One asset can't serve every context (the logo-colour lesson).** A single stored logo is a
  *fixed-colour* asset: Porto's white-on-transparent logo reads on a dark hero (Linen/Slate) but
  vanishes on a light nav bar (Olive). Per *keep-originals*, the fix is never to mutate the source —
  it's a **render-time treatment** (CSS filter / blend) or a **per-context variant asset**, chosen
  by the template. Interim: templates on light surfaces fall back to the **text wordmark** rather
  than force the image. A proper context-aware logo treatment is 🔭 deferred.
- **Derivatives strategy:**
  - 🟡 Start: a few fixed sizes via Pillow on upload.
  - Graduate to an **on-the-fly image CDN** (Cloudflare Images / imgix / Cloudinary) once the
    (template × size × crop) matrix hurts — which, with several templates, will be soon.
- **Focal point** solves cross-template cropping (same source → wide banner here, square tile
  there). Store an (x,y) focal point; render via CSS `object-position` or an image-CDN URL param.

> **Build status (2026-06-20):** photo library built and browser-verified — upload → S3 →
> per-site library (view / alt / delete), format-agnostic (JPEG/PNG/WebP/JFIF). **Image *roles*
> are now built** (`feature_images`, `logo`) with an Appearance editor; `feature_images` supports
> the full ordered **list** (multi-image carousel), proven live in the Olive template. Focal point,
> tags, and derivative sizing remain deferred.

---

## 8. Content model — slot inventory

The "content pool": the union of every slot any v1 template might ask for. *(shape, cardinality,
required/optional.)* Presentation config (template, theme, section order) is **not** here — it's
the Design surface.

**Identity** (site-level)
- `restaurant_name` — text, single, **required**
- `logo` — image, 0..1, optional (fallback: wordmark of name). *Fixed-colour asset — see the
  logo-colour lesson (§7): light-surface templates fall back to the text wordmark.*
- `tagline` — short text, single, optional

**Home / hero**
- `feature_images` — image list, 1..N, **required** (single-hero uses `[0]`; carousel uses all).
  ✅ **Built & proven:** ordered list with add / remove / reorder; templates declare
  single-vs-carousel via a `FEATURE_IMAGE_MODE` map and the Appearance editor adapts its control.
  The live proof of principles 3–4, and the first atom of the template **slot manifest** (§10).
- `hero_heading` — text, single, optional (defaults to `restaurant_name`)
- `hero_subheading` — short text, single, optional

**About / narrative pages** ✅ **content-block primitive built (2026-06-20)**
- `content_block` — the narrative primitive: an ordered list of blocks `{heading?, body?,
  image_photo_id?, position}` keyed by `page_key`. ONE flexible shape — the render adapts to which
  fields are present (heading+body+image → text beside an alternating-side image; body only → prose;
  image only → full-width; heading only → divider). Body is multi-paragraph plain text rendered as
  *escaped* paragraphs. v1 wires `page_key="our_story"`; 🔭 Events reuses it later (same table,
  same editor). 🔭 Deferred: rich-text body, per-block layout control, arbitrary custom pages.
  *(This generalises the old single `about_story`/`about_image` degenerate one-block case.)*

**Menu** — nested entity, see §9

**Photos** (the library; everything else references in)
- `photos` — image list; each: `s3_key`, `focal_point`, `tags` (food/interior/exterior),
  `alt_text`, `order`
- `gallery` — ordered selection from `photos`, 0..N, optional. ✅ **built (2026-06-20):** a third
  ordered image role (reuses the multi-image-role machinery), managed on its own `/admin/gallery`
  page (content, not Appearance/design). Rendered as a **varied-size masonry** driven by each
  photo's stored aspect ratio (`width`/`height`) — no uniform grid, no crop, no new data. 🔭
  Deferred escalation: explicit owner-set prominence ("make this one featured/large") is a
  content-driven add, only if a real need appears (same pattern as the price-columns decision).

**Hours** ✅ **built (2026-06-20)**
- `regular_hours` — per day-of-week, a list of open/close ranges (zero ranges = closed; multiple =
  lunch + dinner). Local wall-clock times, never UTC; overnight ranges allowed (close < open, e.g.
  18:00–01:00). Ordered by day, then `open_time`.
- `hours_exceptions` — date-anchored overrides: `{start_date, end_date, is_closed, special_hours?,
  label}`. Single date or range; closed or special-hours; local calendar dates. Covers public
  holidays, seasonal closures, one-offs, special-day hours. The Visit page renders active + upcoming
  exceptions (`end_date >= today`). 🔭 Deferred: auto-knowing public holidays, recurring annual
  exceptions, a live "open now" badge, schema.org markup.

**Location & contact**
- `address` — structured (street, suburb, state, postcode, country), **required**
- `geo` — lat/lng, optional (geocoded; drives map pin)
- `phone`, `email` — text, optional
- `social_links` — list of {platform, url}, optional

**Calls to action**
- `booking_url` — text, optional (OpenTable etc.)
- `order_url` — text, optional (their own Stripe/Foodhub — the "Order Now" handoff)
- ❓ `cta_links` — **ordered labeled-links collection** (label + url), 0..N. Surfaced by the Olive
  template's right-panel button stack (Make a Reservation / View Menu / special menus / Gift
  Voucher). Currently rendered as a **static placeholder**; the real content type is the same
  bounded-collection primitive (§3) and is 🔭 deferred until a template needs it for real.

**Navigation** ❓ *(discovery finding — not yet a slot)*
- Nav items are **hardcoded per template** today (Eat / Drink / Visit / Gallery). All three
  templates revealed this should be **content-driven** — a `nav_links` labeled-links collection
  (same primitive as `cta_links`), with the template owning only arrangement. Deferred, but flagged
  as the next obvious content-shape leak.

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
- **How menus appear** (tabs vs scroll vs pages, per-dish photos vs text rows, **stacked prices
  vs price-columns**) is the template's job — content carries only structure + order.
- ✅ **Variant display — stacked default; price-columns a deferred owner option (decided 2026-06-20).**
  Variants render *stacked under the item* by default (Linen ships this): mobile-correct and valid
  for any variant shape. A *price-column* grid (Small | Large, or wine Glass | Bottle | Carafe as
  section columns) is an alternative the owner should be able to choose — but it carries a hidden
  content prerequisite: **every item in the section must share the same variant labels in the same
  order** (a homogeneous section), and it collapses back to stacked on mobile regardless. So columns
  is a **per-section, eligibility-gated, *design-config* option** (stored Design-side, read by the
  template) — *not* a content/schema change. (Sections declaring fixed price-columns was considered
  and rejected: it trades the flexible per-item variant model for rigidity — the content-shape leak
  principle 2 warns against.) 🔭 Deferred; a natural future atom of the config form seeded by
  `FEATURE_IMAGE_MODE`.

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

> **Build status (2026-06-20):** menu *admin tooling* functionally complete — CRUD at every level,
> reparent (move-item), drag-reorder within a parent, expand/collapse. The **public menu render now
> ships in the Linen bundle** — template-aware `/menu`, tabbed multi-menu (Eat/Drink), stacked
> variants, headingless-subsection passthrough, dietary tags, descriptions — replacing the old
> pre-template path. This is the reusable bounded-collection primitive the block model (§3)
> generalises from.

---

## 9b. Scalability — the public-read-path story 🔭

> **Status: nothing to build now (one live site). This is the reference for *when* it gets
> slow — the levers, and why the architecture makes them all *additive* (no rearchitect).**

**The load profile is lopsided — that's the key insight.** Two traffic types, wildly different:
- **Admin/editing** — a few hundred owners occasionally editing. Low, infrequent, write-ish.
  **Never the bottleneck.** Even thousands of owners editing occasionally is trivial. Do NOT
  optimise the admin app.
- **Public site serving** — thousands of public sites served to anonymous diners (someone Googles
  "<restaurant> menu" → lands on the page). Read-heavy, public, scales with success. **This is the
  only path that matters for scale.**

So the whole scale question = *how cheaply do we serve a public restaurant page to a diner?*
Everything else is noise.

**The levers (all ADDITIVE later — the architecture already puts the seams in the right places):**

1. **Cache the resolved public view.** Every public page-load currently runs the tenant-resolve +
   the eager-loaded site/menu/photos/hours/blocks bundle. But a restaurant's content is
   **read-mostly** (menu changes ~monthly). So the resolved view is highly cacheable. *Because the
   **resolver** centralises "produce the view," we cache **its output** without touching routes or
   templates.* The #1 scale lever; the architecture is already cache-ready for it.
2. **Cache tenant resolution.** Host → site_id is a DB lookup per request (esp. the custom-domain
   table query). host→site_id rarely changes → a tiny, high-hit-rate cache. Single chokepoint
   (resolve_tenant) = easy to cache.
3. **Image CDN in front of S3** (already §7/§5 backlog). Photos are the heavy payload; serving from
   S3 ap-southeast-2 means a London diner hits Sydney per image. CloudFront/Cloudflare → edge-cached
   globally. **The most *user-perceived* scale fix** (slow images = slow-feeling site), so likely
   *higher* priority than its Phase-E placement once real diner traffic exists. Already on S3 (not
   app-served) → CDN drops in cleanly.
4. **Postgres / Railway tier** = a *dial*, not a redesign. Single shared Postgres handles serious
   load for a long time; scale the instance (and read-replicas if/when reads dominate — they will)
   when metrics say so. **Don't pre-optimise infrastructure.**

**Shared-DB multi-tenancy scales fine for thousands of tenants** — row-level `site_id` scoping is
the standard SaaS pattern. Per-tenant databases are NOT needed at this scale (probably ever). Set
that worry down.

**The ONE thing worth checking proactively (cheap, today): N+1 in the menu tree.** The 4-level tree
(menu→section→subsection→item→variant) must not fire a query *per section/item*. Eager-loading
(`selectinload`) should make it a handful of queries regardless of menu size — but *verify* by
rendering a big menu (100+ items) with SQL logging and counting queries. If query count scales with
item count, that's an N+1 to fix. Verifiable now; a real foot-gun if present.

**Principle:** architect so these fixes stay *additive* (keep the resolver the single place public
rendering happens → it stays cacheable; keep tenant-resolution a single chokepoint; keep images on
S3 not app-served). Then add caching + CDN **when traffic metrics demand it** — not before.
Premature scale-optimisation against unobserved load is the trap.

---


- [ ] Validate the 4-level menu model against the **Drinks** menu (wine → Red/White/Sparkling).
- [~] Detail the remaining content entities to the menu's depth: **hours done** (regular +
  exceptions, §8); **location** done (structured address); **about** still open (the narrative
  block primitive).
- [ ] Decide `variants` storage: child table vs JSONB.
- [ ] **Price-columns as a per-section design-config option** — stacked is the shipped default;
  offer columns where a section's variants are homogeneous, owner-chosen, Design-side (§9).
- [x] ~~Pick the custom-hostname provider~~ → **Approximated** (decided 2026-06-18; see §6).
- [ ] Pick the image CDN (and when to switch from Pillow).
- [x] ~~Front-end approach for the public templates~~ → **SSR Jinja + hand-authored CSS design
  tokens + Alpine.js; no JS framework, no DaisyUI on public; `themes/`·`layouts/`·`_partials/`
  structure** (decided 2026-06-19; see §3, §5).
- [x] ~~**Name the flagship template.**~~ → **Linen** (flagship); siblings **Slate**, **Olive**.
  Named by material aesthetic, never per-client (decided 2026-06-20).
- [x] ~~**Flagship built (home + menu + visit + gallery + our story).**~~ → **Linen is
  content-complete.** Home (hero + logo roles), menu (§9), Visit (hours model), Gallery (masonry),
  and **Our Story** (content-block primitive, §8) all shipped. The site is content-complete; work now
  shifts to the **platform layer** (custom domains via Approximated, Stripe billing, onboarding,
  internal admin) — deferrable behind concierge onboarding until there's a customer to charge.
- [x] ~~Wireframe the 2 non-flagship templates for slot discovery.~~ → **Slate** (dark/vertical-nav)
  and **Olive** (split/carousel) built as full homes — the discovery pass. Divergence axes landed as
  centred-light / dark-vertical / split-carousel rather than the planned minimal/photo-heavy/
  content-rich (2026-06-20).
- [ ] **`nav_links` as content** — make navigation a labeled-links collection (§8); currently
  hardcoded per template.
- [ ] **`cta_links` collection** — the Olive button stack as real content, not a placeholder (§8).
- [ ] **Context-aware logo treatment** — render-time filter or per-context variant so one logo
  serves dark hero + light nav (§7).
- [ ] **Generalise the config form from `FEATURE_IMAGE_MODE`** — the single-vs-carousel mode map is
  the first atom of a template **slot manifest**; the manifest-driven config form grows from it once
  2–3 more slots need template-aware editing.
- [x] ~~**Design the content-block primitive**~~ → **built** as `content_block` (one flexible
  `{heading?, body?, image?}` shape, render adapts, keyed by `page_key`); Our Story shipped on it,
  Events reuses it later (§8). (2026-06-20)
- [x] ~~Confirm whether this lives in its own repo / stack instance~~ → **own standalone repo** (decided).

---

## Changelog

- **2026-06-26** — **Added §3b Template strategy (purpose-fit).** Sharpened during competitive
  research (vs Sociavore/BentoBox). The moat reframed: not "a dozen pretty templates" but a dozen each
  purpose-fit by THREE dimensions — best-fit TYPE (picker descriptor: Linen = classy/cafes/focused
  menus), content-SHAPE (discrete-small-menus like Linen vs a future big-sectioned-single-menu for
  Indian/Chinese/diners), and designed CAPACITY (Linen ≈ 8 menus, a feature not a limit, enforced at
  the 3 menu-creation doors: hand / extraction / section-split — the third caused the Gusto 13-tab
  overflow). Unifying principle CONSTRAIN → GUIDE → DEGRADE (cap to guarantee beauty; picker/alerts
  guide; graceful render as backstop, e.g. mobile menu-tab scroll+centre-on-tap). All Phase C
  (template-factory) work; captured as strategy now.

- **2026-06-26** — **Added §9b Scalability (public-read-path story).** Reference-only (nothing to
  build at one live site). Load profile is lopsided — admin editing is never the bottleneck; the
  public read path (thousands of cacheable, read-mostly sites served to anonymous diners) is the
  only thing that scales. Levers — all *additive* because the architecture centralises the seams:
  (1) cache the resolved public view (resolver output), (2) cache tenant resolution (host→site_id),
  (3) image CDN in front of S3, (4) Postgres/Railway tier as a dial. Shared-DB multi-tenancy scales
  fine for thousands of tenants. One cheap proactive check: verify no N+1 in the menu tree (render a
  big menu with SQL logging). Add caching/CDN when traffic metrics demand it — not before.

- **2026-06-20** — **Our Story shipped + content-block primitive built → site content-complete.**
  `content_block` is the narrative primitive: one flexible `{heading?, body?, image?}` shape (not a
  typed-block system), ordered, keyed by `page_key`, render adapts to which fields are present, image
  sides auto-alternate, body renders as escaped paragraphs. Image is a library ref with `ON DELETE
  SET NULL`; `lazy="raise"` forces eager-loading. v1 wires `page_key="our_story"`; Events reuses the
  same table + editor later. **This was the last content page** — Linen now has home, menu, visit,
  gallery, and our story, so Porto's site is content-complete and the roadmap shifts to the platform
  layer (domains, billing, onboarding).

- **2026-06-20** — **Gallery shipped (§8).** A third ordered image role (`gallery`) reusing the
  multi-image-role machinery wholesale — managed on its own `/admin/gallery` page (kept as *content*,
  separate from Appearance/design). The public Linen page renders a **varied-size masonry** driven by
  each photo's stored aspect ratio (no uniform grid, no crop, no new data field). Explicit owner-set
  photo prominence deferred as a content-driven escalation. The picker was generalised
  (`add_url`/`add_target` per route) so gallery adds can't leak into the carousel. With Gallery in,
  only the Our Story narrative page remains before the site is content-complete.

- **2026-06-20** — **Hours model + Visit page shipped (§8).** Filled the discovery-pass hours gap.
  `regular_hours` — per day-of-week list of open/close ranges (multi-range lunch + dinner, closed =
  no ranges, overnight allowed, local wall-clock not UTC). `hours_exceptions` — date-anchored
  overrides (single date or range, closed or special-hours, label) for holidays/seasonal closures/
  one-offs; rendered active + upcoming on Visit. Both have an admin editor (the previously-stubbed
  Hours page). The **Linen Visit page** ships off the reference (Hours / Where / Reserve cards),
  consuming hours + the existing address/phone/email. Deferred: auto public-holidays, recurring
  exceptions, live "open now", schema.org markup.

- **2026-06-20** — **Linen menu render shipped + variant display decided (§9).** The public menu
  page now renders in the Linen bundle (template-aware `/menu`, tabbed Eat/Drink, headingless-
  subsection passthrough, dietary tags), retiring the old pre-template path. Variant display
  decided: **stacked under the item by default** (shipped), with **price-columns** (Small | Large,
  wine Glass | Bottle | Carafe) deferred as a **per-section, homogeneity-gated, design-config option**
  afforded to the owner — *not* a schema change (section-declared columns considered and rejected as
  a content-shape leak). Stacked is mobile-correct and renders any variant shape; columns is a
  desktop enhancement valid only for uniform sections.

- **2026-06-20** — **Template switching shipped + discovery pass complete.** Three templates now
  exist — **Linen** (flagship), **Slate**, **Olive** — named by material aesthetic; a site-level
  `template` field + an Appearance **picker** let owners switch with content intact. Template code
  structure **revised to self-contained per-template bundles** (`public/{name}/` + `themes/{name}/`),
  replacing the planned shared `themes/`·`layouts/`·`_partials/` split, because templates diverge on
  nav/base structure (§5). **`feature_images` list/carousel built and proven** — add/remove/reorder,
  with a `FEATURE_IMAGE_MODE` map driving a template-aware single-vs-carousel editor: the live
  validation of principles 3–4 and the **first atom of the slot-manifest / config form** (the "config
  for dissimilar sites" mechanism). Discovery findings recorded: nav + hero CTAs want to become
  **labeled-links collections** (§8); the **logo-colour-vs-context** lesson (§7).

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
