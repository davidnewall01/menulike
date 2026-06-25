# Restaurant Site Platform — Architecture, Design & Schema

> **Living document.** Decisions get added and edited here as the design evolves. Each
> entry is a decision we've actually made, not a wishlist. When something changes,
> update the section *and* add a line to the Changelog at the bottom so we can see how
> thinking moved over time.
>
> Status markers: ✅ decided · 🟡 leaning / provisional · ❓ open question · 🔭 roadmap (not v1)

Last updated: 2026-06-24

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

**The core value thesis (the clearest articulation of why we win — 2026-06-24).** A custom agency
site costs a restaurant *thousands* and leaves them **unable to maintain it themselves**. menulike's
bet: **a dozen genuinely good templates means most restaurants find one that's 80–90% of what they
want, at a low monthly price, that they CAN self-maintain.** The owner's decision becomes: "pay
thousands for an agency to get the last 10% — and then be locked out of editing my own site — or
take 80–90% now, cheaply, and own it." For most restaurants that's an easy call. **The template
LIBRARY is therefore the product's moat, not any single template.** Strategic consequence: getting
from one content-complete template (Linen) to a *dozen* is the highest-leverage roadmap work — but
it's gated on **template infrastructure** first (Olive/Slate are home-only stubs; preview hardcodes
Linen; the slot-manifest isn't built — see §3). "A dozen templates" is not a dozen design jobs; it's
*first* the infrastructure (real multi-page templates + preview-honours-template + slot system),
*then* templates become a repeatable production line. Build the factory before the catalogue.

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
- Social cross-posting (specials/events → Instagram/Facebook) — **via aggregator, never
  Meta-direct.** Same handoff discipline as ordering: we don't own the platform integration,
  we hand off to middleware. Detail in §11.

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

**🟡 Template-config surface + template-owned samples (the next big template chunk, parked
2026-06-24).** Two related ideas surfaced and deferred together because they share one mechanism —
*a template declares its own stuff*:
1. **Template selection moves to the dashboard** (site-wide control, sits with publish), and the
   renamed **Front Page** surface (ex-Appearance) renders the **content slots the active template
   declares** — single-hero for Linen, carousel for Olive, etc. This is the **slot manifest** (§8,
   §10) made into a real config surface: "fill the slots this template needs." `FEATURE_IMAGE_MODE`
   is the first atom; this generalises it.
2. **Sample content becomes template-owned**, keyed **(template, role) → image**, instead of one
   global sample per role. Linen+hero = pizza, Slate+hero = a dark-aesthetic steak shot, etc., so
   each template *previews as itself* and sells its own look. The resolver's sample-fallback already
   exists; this only makes the sample *value* template-aware (`samples.for_template(tpl, role)`
   instead of a global constant). Assets live in the template bundle (fits §5 self-contained
   bundles). **Decision: this is (a) aesthetic-match — sample suits the template's vibe — built
   template-keyed now-ish; (b) cuisine-match — sample reflects what the restaurant serves — is the
   future cuisine-picker layered ABOVE as a third key (cuisine, template, role).** Do them together
   (both touch the sample path) — don't rebuild the resolver sample path twice.
   - **Cost reality:** code is small; the *asset production* (tasteful watermarked sample set per
     template per role) is the real, ongoing cost, and it multiplies with template count. This is
     the backlogged "sample assets ugly" item with a per-template multiplier. The cuisine-picker (b)
     multiplies it again (per-cuisine sets) — **massive hand-built-image cost, uncertain ROI,
     genuinely deferred** ("design for it, don't build it for a long while").
   - **Image-heavy templates** (e.g. a Chinese restaurant with a 50-dish image grid) are a future
     bridge — possibly a day or two of work per such template if deemed worth it; design the slot
     model so it doesn't preclude them, but don't build speculatively.

**🐛 Known issue — preview hardcodes Linen (found 2026-06-24, deferred).** All five `/admin/preview`
routes hardcode `public/linen/...` and never call `resolve_template(site.template)` — so the
preview always renders Linen regardless of the saved template. The *public* routes correctly use
`resolve_template`; preview was written before template switching and never wired up. **This is NOT
a standalone fix:** Olive and Slate are **home-only stubs** (only `home.html` exists — they were
built as discovery-pass homes, §below). Wiring `resolve_template` into preview *without* completing
Olive/Slate's other pages would turn a quiet limitation (always shows Linen) into a loud crash (500
on every non-home nav link in Olive/Slate preview). So the preview fix is **gated on Olive/Slate
being page-complete** — the same "see your site in every template" dependency that recurs. Both
belong in the template-config chunk. Until then: **Linen is the only previewable template;** the
"Look:" chip reflects the saved template, but preview renders Linen.

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

## 6b. Tenancy & multi-venue 🟡 (Feature A buildable; Feature B/C laid out, additive, deferred)

The landscape for "one owner, more than one place." Split by **what's shared**, which is the right
axis. Three independent concerns — do not conflate them:

**Feature A — multiple LOCATIONS under ONE site (shared menu, per-location address+hours).**
The common, contained case: a brand with one menu but several physical venues differing only in
*where* and *when* (e.g. shared menu, Gordon hours vs Manly hours). Model: **address + hours become
a repeatable `location` entity under the Site**, not single columns. Visit Us lists each location
as its own entity. One tenant, one menu, N locations.
- ✅ **Decided: build this into Chunk 4** (the Visit & Contact editor) — promote address+hours from
  single-on-Site to a `locations` list.
- 🔑 **THE BRIGHT LINE:** a location carries **address + hours ONLY** — never menu, never any other
  content. The moment a venue needs a *different menu*, that is Feature B (a separate Site), NOT
  another location. This rule keeps Feature A and Feature B from tangling. Enforce it in Chunk 4.
- On Linen, multiple venues surface **only on Visit Us** (the rest of the site is shared). There is
  no front-end venue-switcher in Feature A — there's one site, one menu, just several locations
  listed on Visit.

**Chunk 4 build status (2026-06-24): single-location complete end-to-end; multi-location built but
GATED.**
- ✅ **Phase 1** (committed): `Location` entity + migration 013 — one default location backfilled
  per site from `Site.address_*`/phone/email; hours (`regular_hours`, `hours_exceptions`)
  re-parented to `location_id`. Verified on real data (one location/site, no null hours). lat/lng
  columns carried empty.
- ✅ **Phase 2** (committed): migration 014 sets `location_id` NOT NULL (verify-no-nulls first);
  `location_service`/`coordinator` (IDOR-scoped); hours services cut over to `location_id` with the
  new foreign-`location_id` IDOR hole closed; `site_id` kept on hours tables (expand-contract).
  Backward-compat path: callers without `location_id` resolve the site's default location.
- ✅ **Phase 3** (committed): `/admin/visit` editor (absorbs `/admin/hours`, old URL redirects).
  **Single-location degrades to a plain address+contact+hours form** (no label field, no Remove, no
  list chrome); becomes a list only at ≥2 locations. **Google Places Autocomplete** on the address
  field (public client-side key from `.env` — MUST be referrer+API-restricted in the Google console
  before public launch; ops concern). Selecting a suggestion populates address + **stores lat/lng**
  (captured for future schema.org SEO, §12 — no map shown). Manual entry always works (graceful
  degradation; coords null). **Gate:** `MULTI_LOCATION_ENABLED=False` hides the "+ add another
  location" affordance AND guards the add-location route — so owners can't reach the unfinished
  multi-location public render. Multi-location code (entity/services/editor list-mode) all stays;
  only the entrance is gated.
- 🔭 **Phase 4 (BACKLOG — the multi-location PUBLIC render).** Deferred because the next 2–3 pilot
  prospects are single-venue and the single-location public Visit page is sound today. Two-location
  testing revealed its full scope:
  - **Visit page**: wrap WHERE / HOURS / RESERVE in `{% for location in locations %}` — each
    location renders its own address, its own hours (fixes the **doubled-hours bug** seen when the
    old single-location template met multi-location data), its own phone/email. Labelled locations
    get a section heading; a single unlabelled location renders heading-free (identical to today).
  - **Per-location "Get directions" link**: anchor to
    `https://www.google.com/maps/dir/?api=1&destination={url-encoded address}` (text address, no
    coords, no map — Linen stays clean).
  - **Global slots** (home hero contact bar + footer): one location → full address (as today);
    multiple → **suburb list** ("Fingal Bay · Anna Bay"). No "primary location".
  - **Resolver**: `_resolve_visit` reads `site.locations` (list); presence checks aggregate across
    locations; "visit yours" = ≥1 location with address AND hours AND contact.
  - **Details strip** (the dismantle's remaining structural step): remove address/phone/email from
    `_DETAIL_FIELDS` + `SiteDetailsForm` + `_details_form.html`; Details then holds ONLY
    restaurant_name.
  - **Final step: flip `MULTI_LOCATION_ENABLED=True`** to unhide the add-location affordance once
    the render supports it.
- 🔭 **Deferred contraction migration** (after Phase 4 committed + proven): drop
  `Site.address_*`/phone/email + the old `site_id` FK on the hours tables. NOT before — expand-
  contract keeps the old columns through the cutover.

**Feature B — multiple SITES under one BRAND, with a front-end switcher (different menus).**
The bigger case: genuinely independent venues (Melbourne vs Sydney, *different menus*), operating
under one URL, where the **diner must choose which venue** up front. (Real example: Nomad
Melbourne/Sydney ran different menus.) Different menu ⇒ different Site. Needs:
- A **Brand** entity *above* Site — owns the group, the apex domain, shared branding, the venue
  list / switcher config. Sites gain a **nullable `brand_id`**. Single-site restaurants have
  `brand_id = NULL` and are unaffected — **this is purely additive, no re-pour.**
- **Routing change (the real work, not the switcher):** tenant resolution moves from "hostname →
  Site" to "hostname → Brand → (path → Site)". Path-based is the likely model
  (`brand.com/sydney`, `brand.com/melbourne`, apex = switcher) — one domain, one cert, cleanest for
  the owner. **Chunk 4 must not deepen the "one site per hostname" assumption** so this stays
  reachable (Chunk 4 doesn't touch routing, so it's safe).
- **Per-content brand-vs-site decision** (defer): menu = site (given); logo/branding = brand
  (likely); story/events = TBD. Decide per content type when Feature B is built.
- The **switcher itself is the easy part** — a chooser rendered on the brand's apex landing once
  Brand→Sites + routing exist. The architecture is routing + the Brand entity; the switcher is the
  visible tip.
- 🔭 **Deferred.** Demand-validate first (how many prospects actually run different-menu chains?).
  But it's additive, so nothing now blocks it.

**Feature C — multiple MANAGERS (per-venue access control).** ORTHOGONAL to A and B. Letting the
Gordon manager edit only Gordon's content while the brand owner sits above — this is **roles &
permissions**, not data structure. An account can own N sites with a *single* manager (no C needed)
OR delegate per-venue (needs C). 🔭 Furthest out; only if delegation is demanded.

**Why this is safe to defer without painting ourselves into a corner:** the two structural pieces
(Brand parent, brand-then-venue routing) are both **additive** — a nullable `brand_id` and a
resolution layer — neither undoes Chunk 4 or anything shipped. The single real risk is *conceptual
bleed* between "location" (A: where+when, shared menu) and "site/venue" (B: own menu); the
bright-line rule (locations never carry content) eliminates it. NOTE: "Template" (Linen/Slate/Olive)
is the **visual** layer and has nothing to do with tenancy — a venue-switcher is a brand/routing
concept, never a template.

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
  > **Build status (2026-06-24) — specced, not rendered.** The Linen hero overlay renders
  > **`tagline` only**; `hero_heading` and `hero_subheading` are stored columns + Details-form
  > fields that no current template reads. The dashboard "Front page" badge correctly tracks
  > `{hero_image, tagline}` — matching what Linen actually shows. These two columns are being
  > **removed from the Details form** (they let owners type into fields that do nothing). Before
  > any column-drop migration, confirm Olive/Slate don't read them either; if all three templates
  > ignore them, they're dead columns. Kept in the slot inventory as a *future* slot a richer
  > hero layout might consume — but not wired today.

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

## 10. Open questions / next ❓

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

**Sequencing & near-term work (added 2026-06-24 — Porto can now self-serve end-to-end; chunks 1–4
of the Details dismantle shipped, single-location complete).** Recommended order:
1. [ ] **Codex milestone review across the Details dismantle (chunks 1–4)** — four chunks of
   structural surgery on the same area (resolver, dismantle, locations migration); review at this
   clean seam before building further. Do FIRST.
2. [ ] 🚨 **Tailwind CDN → build-step (HARD pre-public gate).** Public pages currently load
   `cdn.tailwindcss.com`, which (a) Tailwind explicitly warns against in production, (b) compiles
   CSS in-browser on every load (slow), and (c) causes the **flash-of-unstyled-content** that makes
   the dashboard look briefly wrong on cold load (it looks right once warm/cached — same root cause).
   Fix = compile Tailwind via PostCSS/CLI to a static stylesheet. **Must precede ANY public launch
   (app or marketing site).**
3. [ ] **menulike marketing/landing site** — the public site that *sells* menulike to restaurant
   owners (distinct from the app). Needed to send prospects beyond Porto. Gated on #2.
4. [ ] **Dashboard polish pass** (one unit): the dashboard is *functional* but wants "zip." Items:
   the wide side whitespace (content sits in a centred max-width column — fine for reading, but a
   dashboard may want more width or to use the side space); mobile-friendliness; trim the top items;
   general visual lift. The mobile cold-load render issue resolves with #2 (Tailwind).
5. [ ] **Finish the Details dismantle**: Phase 4 (multi-location public render + Details strip +
   `MULTI_LOCATION_ENABLED` flag-on, §6b), then chunk 5 (Details → "Restaurant info"), then the
   deferred column-drop migration. Single-venue pilots don't need Phase 4 urgently, but the dismantle
   should close to avoid a lingering half-state.
6. [ ] **Template-infrastructure campaign** (the unlock for the "dozen templates" thesis, §1): make
   Olive/Slate page-complete + preview-honours-template + the slot manifest (generalised from
   `FEATURE_IMAGE_MODE`) + template-selection→dashboard. This is the factory that makes a template
   *library* a production line rather than a series of one-offs.
- [ ] **After pilot (do NOT build before pilot validates willingness-to-pay):** admin/concierge
  screens; Stripe billing (with the photo-quota and social-tier levers, §7/§11, as plan
  differentiators).

---

## 11. Social cross-posting 🔭 (roadmap — aggregator, never Meta-direct)

**The thesis fit.** "Publish once, push everywhere" is the menu-hub promise extended to
marketing: a special/event composed in the platform posts to the site *and* to the
restaurant's Instagram/Facebook, and because it originated here, the resulting traffic is
**attributable** — feeding the owns-your-audience loop. Strategically aligned. But it's a
**distribution feature, not a foundation feature** — it rides on top of a posting/specials
data model we'd build for the site anyway, and it must never be built Meta-direct.

**Why never direct (the platform-dependency trap).** Posting to Instagram via Meta's Graph API
(the only sanctioned path) imposes, on *us* as builder:
- A Meta developer app + **business verification** + per-permission **app review** (a screencast
  per permission; 2–6 weeks; first-submission rejections common for content-publish).
- **Permanent maintenance tax:** Meta ships a new API version each quarter, breaking changes
  occur *within* versions, long-lived tokens expire every 60 days (re-auth plumbing per connected
  restaurant). Industry rule-of-thumb: **5–10% of engineering capacity, indefinitely**, just to
  keep it alive. For a solo founder this is disqualifying. Same risk class as GloriaFood
  (platform-owned, can be sunset under us).

**Why aggregator (Postproxy / Zernio / Phyllo).** Their USP is precisely that they **eat the
builder-side tax** — one Meta integration maintained across thousands of apps, so app review +
OAuth + token refresh + quarterly breakage are *theirs*. They post via Meta's official Graph API
under the hood, so it stays platform-sanctioned. Our build shrinks from quarters-plus-forever to
weeks. Tradeoff: a dependency-on-a-dependency (if the aggregator dies we re-platform) + per-post
or per-seat cost — both acceptable, and deferrable until a customer pays for the feature. This is
the **exact same handoff discipline as ordering** (§1): we don't own the engine, we hand off.

**The residual friction the aggregator *cannot* remove (owner-side, unavoidable).** Meta enforces
these on the posting account itself, so no middleware abstracts them away:
- The owner needs an Instagram **Professional** (Business/Creator) account — personal accounts are
  excluded from the publish API entirely.
- It must be **linked to a Facebook Page.**
- Then an OAuth "connect" consent.

The aggregator makes step 3 a smooth button, but steps 1–2 are Meta's wall. **Mitigant:** any
restaurant already running IG for marketing has almost certainly cleared 1–2 already (Meta nags
businesses into Professional accounts relentlessly). The friction self-selects — owners who'd want
cross-posting have mostly done the painful part; owners who haven't wouldn't use it.

**Sequencing.**
1. **Now (Phase 0):** build nothing for social — but when the specials/events surface is built,
   structure a "post" as a first-class object (`title`, `body`, `image_ref`, `publish_targets`)
   that publishes to the **site** first. Valuable standalone; it's the substrate social plugs into.
2. **Phase 1 (on first paying pull):** integrate an **aggregator**, not Meta-direct. Build a
   "connect your Instagram" flow that hands off to the aggregator's OAuth and detect-and-guides if
   the account isn't Professional yet. Validate demand before owning anything.
3. **Phase 2 (only if it becomes core revenue):** consider direct integration if aggregator margin
   starts hurting — a champagne problem, years out.

❓ Open: which aggregator (compare Postproxy / Zernio / Phyllo on price, platform coverage, and
their own longevity risk) — defer until Phase 1 is actually triggered.

> **Pricing-strategy lean (2026-06-24):** the aggregator economics favour **bundling social into
> a higher menulike plan tier** ("Pro includes cross-posting") over a metered "+$5/mo" add-on.
> Reasons: (a) per-restaurant cost only drops to its floor at high tier-fill, so a metered fee is
> underwater early; (b) the IG-Professional + Facebook-Page wall means attach rate is partial, and
> a bundled feature dodges the attach-rate problem; (c) restaurants resist nickel-and-dime line
> items but will upgrade for value. The win is **retention + upgrade leverage**, not the marginal
> fee. Re-check live aggregator pricing at Phase 1 (tiers reprice; the aggregator is itself a
> dependency).

> **Carried-over security check (2026-06-24):** when `booking_url` and `order_url` return as the
> ordering/booking config tiles, **re-introduce URL-scheme validation.** The `javascript:`-scheme
> blocking validator (`url_scheme_check` + allowlist, in `schemas/site.py`) was removed with those
> fields in the Details dead-field strip (chunk 1). It was a real XSS guard, not decoration — any
> future surface that accepts an owner-supplied URL for rendering as a link must validate the
> scheme against an allowlist (http/https/mailto/tel only).

---

## 12. SEO — the structured-data moat 🟡 (foundation shipped, moat deferred)

**The strategic point (write this for owners, not engineers).** Restaurant SEO is an industry
people build whole consultancies on — but most of that value, for a restaurant, comes from things
menulike can do **automatically and for free**, because we already hold the data in structured
form. The owner should never see most of it; it just works in the background and we *tell them*
it's working. That "we handle being found on Google for you" story is a genuine differentiator and
a real reason to choose (and stay on) menulike — but only if we actually ship the moat, not just
the meta tags.

**SEO is a stack, ranked by what actually moves the needle for a restaurant:**

1. **Structured data / schema.org markup — THE MOAT (highest leverage, deferred 🔭→ promote).**
   Because we hold structured **menu + hours + address + price** data, we can emit
   `Restaurant` / `Menu` / `LocalBusiness` **JSON-LD** into every page. This is what powers
   Google's **rich results** — the search cards showing hours, price range, "open now," and menu
   links inline. A generic Wix/Squarespace restaurant site usually *can't* do this well; we can do
   it **perfectly, with zero owner effort**, precisely because our content model is structured
   (the whole §2 thesis paying off in SEO). This is the defensible advantage. It is invisible
   markup the owner never edits.
2. **Local SEO signals.** Consistent NAP (Name/Address/Phone) across the site + `LocalBusiness`
   markup + geo-coordinates. Restaurants are found via *local* queries ("italian near me"); our
   structured address feeds this directly.
3. **Per-page meta.** Today meta is **site-level** (one title/description for the whole site —
   shipped, §below). Real SEO wants per-page meta (menu page, visit page each with their own).
   A future expansion of the §-below surface.
4. **Performance / mobile / crawlability.** Our SSR-Jinja, no-framework, fast-first-paint stack
   (§5) already wins here almost by accident. Keep it.
5. **Meta tags (title + description) — the SMALLEST lever, shipped first.** Deliberately tiny
   (~60 / ~155 chars; Google truncates beyond). Important to *have*, not where SEO is won. This is
   what the "Search listing" tile shows.

**Shipped (2026-06-24): site-level meta tags, derive-with-override.** The "Search listing" tile +
`/admin/seo` surface present a **Google-result preview** and two fields (title, description) using
the **derive-with-override** pattern (same shape as sample-fallback, §below): a computed default
the owner can override, **derived values never stored** — only explicit overrides are written, so
the meta **self-heals** when name/suburb/tagline change. Derivation degrades gracefully (cuisine
field doesn't exist): title = `{name} — {suburb}` → `{name}`; description = 4-rung ladder
(tagline+suburb → tagline → name+suburb → omit-when-too-thin). All four public base templates now
read the **resolved** value, so public `<title>`/`<meta>` match the preview — and this **closed a
live gap**: previously `<meta description>` was simply omitted when null, so untouched sites
shipped with no description at all. Tile status is **"Auto-generated" (green ✓, not a nag) vs
"Customised"** — an auto-generated listing is *complete and shippable*, never a warning state.

**🔭 Next-big-SEO chunk — schema.org structured data (promote from backlog).** Emit JSON-LD from
existing structured data: `Restaurant`/`LocalBusiness` (name, address, geo, phone, hours, price
range, URL) on all pages; `Menu` (sections → items → prices) on the menu page. Zero owner input.
Once shipped, the "Search listing" tile grows a second line — e.g. **"✓ Rich results enabled"** —
making the invisible work **visible as a selling point**. This is the surface where the structured-
data thesis becomes a customer-facing SEO advantage. ❓ Open: geo-coordinates (we have address but
not lat/lng — geocode on save? which provider?); per-page meta as the follow-on.

**🔭 Geocoding — own-your-coords, NOT Google (decided 2026-06-24, deferred as its own feature).**
The Location entity (§6b) carries `latitude`/`longitude` columns. Plan: **geocode on address save**
(once per address change, not per page-load — so volume is tiny, deep inside any free tier), store
the coords, and use them for (a) a **map on the Visit page** and (b) **schema.org `geo` markup**
feeding local SEO (the moat above).
- **⚠️ Provider decision — do NOT use Google Geocoding for stored coords.** Google's license forbids
  storing geocoding results permanently *unless they're displayed on a Google map* (cache ≤30 days
  otherwise). Since we want to **store coords permanently** (for schema.org markup + our own map),
  Google's terms are a trap. **Use a permissive-storage geocoder** (Geocodio / OpenCage /
  Geocode.earth all allow permanent storage). Cost is negligible at our volume regardless.
- **Map display:** prefer a **free OSM / Leaflet** map (no billing account, no API-key gating, no
  platform lock-in) over a Google embed — consistent with own-your-data / avoid-hostile-platform.
- This is **its own later feature** (a geocode-on-save hook + map render + schema.org markup),
  pairs naturally with the structured-data chunk above. Chunk 4 carries the lat/lng columns
  **empty** — does NOT populate them. "Verified by Google Business Profile" (claiming the real Maps
  listing, reviews) is a separate heavy OAuth integration — deferred entirely, same friction class
  as social (§11).
- **✅ Distinct & trivial — "Get directions" link (build with Chunk 4 Visit render).** The common
  near-term need ("a link that opens directions") needs **NONE** of the above — no API, no
  geocoding, no stored coords, no licensing concern. Google Maps accepts a plain text-address URL:
  `https://www.google.com/maps/dir/?api=1&destination={url-encoded address}`. Each location's Visit
  card renders a "Get directions" anchor built from its address fields; Google geocodes on its end,
  the user's device supplies the origin. Per-location (directions to *that* venue) — strengthens the
  multi-location story. Do NOT conflate with the deferred map-embed/SEO geocoding above: directions
  = a link; embedded map + schema.org `geo` = stored coords (deferred).

---

## Changelog

- **2026-06-24** — **🎉 MILESTONE: Porto can self-serve end-to-end (signup → build → publish).**
  After the dashboard IA re-cut + the full Details dismantle (chunks 1–4), an owner can create and
  configure every part of their site from the dashboard: menu, photos, front page (hero/logo/
  tagline), Our Story, Visit & hours (multi-location-capable, single-location-clean), Gallery, and
  an auto-generated Search listing. Verified on Porto Azzurro. Captured three strategic items:
  (1) **the core value thesis** (§1) — a dozen good templates → 80–90% fit, self-maintainable, vs
  thousands for an agency's last 10% with no self-maintenance; the template *library* is the moat,
  gated on template *infrastructure* first. (2) **Tailwind CDN → build-step is a hard pre-public
  gate** (§10) — also the cause of the dashboard cold-load render flash. (3) **Sequenced next-up**
  (§10): Codex review → Tailwind fix → marketing site → dashboard polish → finish dismantle →
  template-infrastructure campaign → (post-pilot) concierge + billing.

- **2026-06-24** — **Chunk 4 Phases 1–3 shipped: address+hours → multi-location entity (Feature A,
  §6b), single-location complete, multi-location gated.** Phase 1: `Location` entity + migration
  (one default location backfilled per site; hours re-parented to `location_id`; verified on real
  data). Phase 2: `location_id` NOT NULL + `location_service`/`coordinator` + hours cutover with the
  foreign-`location_id` IDOR hole closed (expand-contract keeps `site_id`). Phase 3: `/admin/visit`
  editor (absorbs `/admin/hours`) that **degrades to a plain form for one location** and becomes a
  list at ≥2; **Google Places Autocomplete** populating address + **storing lat/lng** for future SEO
  (manual entry always works); `MULTI_LOCATION_ENABLED=False` **gates** the add-location entrance so
  owners can't reach the unfinished public render. **Phase 4 (multi-location public render +
  directions link + suburb-list footer + Details strip + flag-on) → BACKLOG** — deferred because
  near-term pilots are single-venue and single-location renders soundly today; full scope captured
  in §6b. Geocoding-for-a-map and "Get directions" link separated (§12): directions = trivial text
  link; stored coords (now being captured via Places) feed deferred schema.org SEO, NOT a map (Linen
  stays mapless).

- **2026-06-24** — **Chunk 3 Phase 1 shipped (partials parameterised) + template-config/sample
  direction parked (§3).** Phase 1 of the Front Page consolidation: the hero/logo/carousel picker
  partials (`_appearance_slot`, `_appearance_picker`, `_appearance_carousel`) no longer hardcode
  `/admin/appearance/` URLs — they take assign/clear/picker/carousel URLs as context (one
  `_IMAGE_ROLE_URLS` constant spread into context), so the same machinery works from any surface.
  Pure refactor, zero visible change, verified incl. second-interaction round-trips. **Parked for a
  later dedicated chunk:** (1) **template selection → dashboard**, Front Page becomes
  **slot-manifest-driven** (renders the slots the active template declares); (2) **template-owned
  samples** keyed (template, role) so each template previews as itself — aesthetic-match built
  template-keyed, cuisine-match (per-cuisine sample sets) layered above later as the deferred
  cuisine-picker. Both ride together (shared sample/slot path). Asset production is the real cost
  and it multiplies per template (and again per cuisine) — genuinely deferred.

- **2026-06-24** — **Details dismantle chunk 2 shipped: SEO → "Search listing" tile (§12).**
  Moved meta_title/meta_description off the Details form to their own dashboard tile + `/admin/seo`
  surface, upgraded to **derive-with-override** (computed default, override-only stored, self-heals
  on name/suburb/tagline change). Google-result preview on tile + surface. All four public base
  templates repointed to read the **resolved** meta — closing a live gap (untouched sites
  previously shipped with no `<meta description>` at all). Tile status "Auto-generated" (green ✓)
  vs "Customised" — never a nag. Resolver gained a `"derived"` source + `seo` area (not status-
  bearing, not publish-gated). Also captured the **SEO strategy (§12):** meta tags are the smallest
  lever; the real moat is **automated schema.org structured data** (Restaurant/Menu/LocalBusiness
  JSON-LD from our already-structured data → Google rich results, zero owner effort) — promoted to
  the next-big-SEO chunk, with the customer-facing story being "we handle being found on Google for
  you." Details now holds 7 fields: name, tagline, address ×4, phone, email.

- **2026-06-24** — **Details dismantle chunk 1 shipped: dead-field strip.** Removed SIX
  provably-dead fields (hero_heading, hero_subheading, about_story, address_country, booking_url,
  order_url) from the /admin/details form, schema (`SiteDetailsForm`), and service write-list —
  fields that wrote columns no template reads on any path. The now-empty Hero and About section
  headings went with them. **Columns and model attributes kept** (column-drop is a separate later
  migration gated on an `about_story` non-null scan + Olive/Slate read-check). The `javascript:`
  URL-scheme validator was removed with booking/order_url — flagged in §11 to return with those
  future config tiles. Browser-verified: survivors round-trip on save, public hero renders unchanged
  (tagline only, confirming §8 ghost-field flag). Details now holds 9 fields: name, tagline,
  address ×4, phone, email, meta_title, meta_description. Endgame remains: rehome the survivors to
  tiles, then DELETE the Details page entirely.

- **2026-06-24** — **Social cross-posting added to roadmap (§11, §1).** Strategically on-thesis
  (publish-once → attribution loop) but a **distribution feature, not foundation**, and a
  platform-dependency trap if built Meta-direct (business verification + per-permission app review +
  a permanent 5–10% maintenance tax owned by a hostile platform). Decision: **aggregator, never
  direct** — same handoff discipline as ordering. Sequence: site-first posting object now →
  aggregator on first paying pull → direct only if it becomes core revenue. Owner-side friction
  (IG Professional + Facebook Page link) is Meta's wall, unremovable by any middleware, but
  self-selects (marketing-active restaurants have mostly cleared it). Also flagged: **`hero_heading`
  / `hero_subheading` are specced-but-unrendered** in Linen (badge correctly tracks `tagline` only);
  being removed from the Details form, column-drop pending an Olive/Slate read check (§8).
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
