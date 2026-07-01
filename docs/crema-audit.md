# Crema Template Audit

Audit date: 2026-07-01. **AUDIT ONLY: no template, model, service, route, CSS, or
migration fixes were made.** This document is the proposed findings and task list
for approval before implementation.

---

## 1. Territory map

### Crema template files

| File | Role |
|---|---|
| `app/templates/public/crema/base.html` | Layout shell, meta tags, tokens/CSS include, preview banner, nav include, content block, default footer include. |
| `app/templates/public/crema/tokens.html` | Inline design tokens and Google Fonts. Values are hardcoded CSS custom properties. |
| `app/templates/public/crema/_nav.html` | Sticky header, brand/logo, desktop nav links, Book CTA, burger button, duplicated mobile menu links. |
| `app/templates/public/crema/_footer.html` | Shared footer partial for non-home pages. Reads address/contact from the resolved `visit` view. |
| `app/templates/public/crema/home.html` | One-page home experience: hero carousel, menu section tiles, story/gallery/find-us sections, and an inline footer that bypasses `_footer.html`. |
| `app/templates/public/crema/menu.html` | Menu page: section panels, section thumbnails, inline item lists, columnar price tables, menu footer blocks. |
| `app/templates/public/crema/_menu_item.html` | Single text-first menu item row: name, tags, price, description, extras, variants. |
| `app/static/themes/crema/crema.css` | Crema CSS. Main breakpoints are 860px, 768px, 680px, and 520px. |

Public rendering is in `app/web/public.py`: the route resolves the tenant from the
request host, loads public site data, calls `resolve_site_view(...)`, and renders the
selected template with `{site, view, storage_url, render_mode, ...}`.

### Where per-venue config/settings live today

There are three relevant paths. The important finding is that the JSONB settings
pattern described in the project context is not currently wired into runtime reads.

**Path A: `Site` columns read directly as `site.<field>`**

`app/models/site.py` defines columns such as `restaurant_name`, `slug`, `template`,
`tagline`, `hero_heading`, `hero_subheading`, `booking_url`, `order_url`,
`meta_title`, `meta_description`, and `settings`. Crema currently reads
`site.restaurant_name`, `site.booking_url`, and `site.tagline` indirectly via the
resolver. `hero_heading` and `hero_subheading` exist but are not read by Crema or the
front-page admin UI.

**Path B: resolver-fed `view` object**

`app/content/resolver.py` returns a `SiteView` dict keyed by area: `home`,
`our_story`, `visit`, `gallery`, `menu`, `events`, and `seo`. Each area has
`status` plus `fields`; each field is a `FieldView(value, source)`, where `source` is
`real`, `sample`, `derived`, or `empty`.

This is the dominant public-template pattern. Crema reads values such as
`view.home.fields.logo.value`, `view.gallery.fields.photos.value`,
`view.menu.fields.menus.value`, and `view["visit"].fields.contact.value`.

For visit/contact specifically, the resolver reads the first `Location` by position.
`_resolve_visit(...)` uses `location.address_*`, `location.phone`, `location.email`,
and `location.regular_hours`; it does not use the older `Site.address_*`,
`Site.phone`, or `Site.email` columns for public rendering.

**Path C: `Site.settings` JSONB**

`Site.settings` exists as a JSONB column with default `{}`, and `site_service.create_site`
initialises it to `{}`. However, a runtime search found no `get_setting`, no
`SETTINGS_DEFAULTS`, and no active public-template read of `site.settings`. The
settings JSONB design is therefore aspirational in this repo right now. Any task that
uses `settings` also has to build the read/default pattern first.

### Components called out

**Footer:** `_footer.html` renders restaurant name, street/suburb, and phone from
`view["visit"]`. `home.html` suppresses the base footer and duplicates similar footer
markup inline at lines 317-327. Neither footer renders email, social links, copyright,
or year.

**Nav/header:** `_nav.html` renders brand/logo, Menu, conditional in-page anchors
for Our Story/Gallery/Find Us, and a conditional Book link from `site.booking_url`.
The mobile menu duplicates the desktop link list manually.

**Menu item:** `_menu_item.html` is text-first. It renders dietary tags inline after
the item name and never renders item images. Section-level photos exist in
`menu.html`, but item-level photos do not.

---

## 2. Social links

### Current state

There is no implemented social-link mechanism: no model field, resolver field, admin
input, or Crema footer markup. The design doc already lists `social_links` as a
location/contact field (`docs/restaurant_platform_design.md`).

### Recommended data home

Add social links to `Location`, not to the Crema template and not to `Site.settings`.

Reasons:

- The footer and Find Us contact card already read visit/contact data from
  `Location` through `view["visit"]`.
- The existing owner-facing `/admin/visit` screen edits address, phone, email, and
  hours for each location; social links are the same kind of contact channel.
- `Site.settings` is not read anywhere today, so using it would require building the
  settings subsystem before the feature.
- Hardcoding links in Crema would break the tenant boundary and fail the stated
  requirement.

### Proposed shape

Use `Location.social_links` as JSONB, defaulting to an empty list:

```json
[
  {"platform": "instagram", "url": "https://instagram.com/example"},
  {"platform": "facebook", "url": "https://facebook.com/example"}
]
```

A list keeps platform order venue-controlled and leaves room for new platforms.
Known platforms for first-pass icon mapping: `instagram`, `facebook`, `tiktok`,
`youtube`, `tripadvisor`, `google`, `x`. Any blank URL should be normalised away or
skipped at render time; blank platforms render nothing.

### Consumers

- `app/content/resolver.py`: add a `social` field to the `visit` area with
  `never_sample=True`. Value should be `[]` when absent.
- `app/templates/public/crema/_footer.html`: render a social icon/link row if the
  resolved list is non-empty.
- `app/templates/public/crema/home.html`: once footer markup is consolidated, it
  should consume the same partial. Optionally also render socials in the Find Us
  contact card.
- `app/templates/admin/visit.html`, `app/web/admin.py`, `app/services/location_service.py`,
  and `app/coordinators/location_coordinator.py`: extend the existing Visit & Contact
  edit path to save social links per scoped location.

---

## 3. Dead-links inventory

Classification key:

- **(a) working internal nav/control**
- **(b) external embed/service/scheme/asset**
- **(c) dead or placeholder going nowhere**
- **(d) should be config-driven**
- **preview-only**: admin prompt shown only in authenticated preview mode

| Link/control text | File + line | Current target | Class | Recommended action |
|---|---:|---|---|---|
| Brand | `_nav.html:3` | `{{ nav_prefix or '/' }}` | (a) | OK. |
| Menu | `_nav.html:16` | `{{ nav_prefix }}/menu` | (a) | OK. |
| Our Story | `_nav.html:17` | `#our-story` | (a) | OK; gated on real content in public mode. |
| Gallery | `_nav.html:18` | `#gallery` | (a) | OK; gated on real content in public mode. |
| Find Us | `_nav.html:19` | `#find-us` | (a) | OK; gated on visit content in public mode. |
| Book | `_nav.html:21` | `{{ site.booking_url }}` | (d) | Correctly config-driven and conditional; owner-facing edit path is missing. |
| Burger | `_nav.html:24` | inline JS toggle | (a) | Works as control; tap target is too small, see mobile findings. |
| Mobile Menu | `_nav.html:28` | `{{ nav_prefix }}/menu` | (a) | OK; duplicated markup. |
| Mobile Our Story | `_nav.html:29` | `#our-story` | (a) | OK; same gating. |
| Mobile Gallery | `_nav.html:30` | `#gallery` | (a) | OK; same gating. |
| Mobile Find Us | `_nav.html:31` | `#find-us` | (a) | OK; same gating. |
| Mobile Book | `_nav.html:33` | `{{ site.booking_url }}` | (d) | Correctly config-driven and conditional; owner-facing edit path is missing. |
| Back to dashboard | `base.html:27` | `/admin/` | preview-only | OK. |
| Google Fonts preconnect | `tokens.html:1-2` | Google font origins | (b) | OK. |
| Google Fonts stylesheet | `tokens.html:3` | Google Fonts URL | (b) | OK. |
| Carousel prev | `home.html:37` | Alpine click handler | (a) | OK; only rendered when more than one photo. |
| Carousel next | `home.html:40` | Alpine click handler | (a) | OK; only rendered when more than one photo. |
| Add your photos | `home.html:52` | `/admin/front-page` | preview-only | OK. |
| Add your logo | `home.html:65` | `/admin/front-page` | preview-only | OK. |
| Add your tagline | `home.html:75` | `/admin/front-page` | preview-only | OK. |
| View Menu | `home.html:79` | `{{ nav_prefix }}/menu` | (a) | OK. |
| Book a Table | `home.html:81` | `{{ site.booking_url }}` | (d) | Correctly config-driven and conditional; owner-facing edit path is missing. |
| Section tile | `home.html:128` | `{{ nav_prefix }}/menu#section-{{ section.section_id }}` | (a) | OK; target IDs exist in `menu.html:39`. |
| Add menu sections | `home.html:155` | `/admin/menus` | preview-only | OK. |
| Add your story | `home.html:169` | `/admin/our-story` | preview-only | OK. |
| Add gallery photos | `home.html:204` | `/admin/gallery` | preview-only | OK. |
| Add your hours | `home.html:269` | `/admin/hours` | preview-only | OK. |
| Add your address | `home.html:284` | `/admin/visit` | preview-only | OK. |
| Phone | `home.html:295` | `tel:{{ cv.phone }}` | (b) | OK; only rendered when phone exists. |
| Email | `home.html:298` | `mailto:{{ cv.email }}` | (b) | OK; only rendered when email exists. |
| Book a Table | `home.html:301` | `{{ site.booking_url }}` | (d) | Correctly config-driven and conditional; owner-facing edit path is missing. |
| Add contact details | `home.html:306` | `/admin/visit` | preview-only | OK. |
| Add your menu | `menu.html:14` | `/admin/menus` | preview-only | OK. |

### Findings

- No Crema link is a true `(c)` dead/placeholder link. Existing public links either
  navigate internally, use a scheme like `tel:`/`mailto:`, or are conditional on data.
- `booking_url` is the main should-be-config-driven CTA and is already read from
  config/data, but no owner-facing form currently edits it. It is a `Site` column and
  appears in Crema and other public templates.
- `order_url` exists on `Site` but is not consumed by Crema. That is appropriate for
  v1: ordering is a future handoff, not a payment/ordering engine.
- Hardcoded venue-specific copy exists even though it is not a link:
  `home.html:58` renders `Neighbourhood Cafe`. This should be config-driven or
  omitted, because a non-cafe venue would inherit the wrong identity.
- `home.html:27` uses `{{ site.name }}` in hero image alt text, but the model field is
  `restaurant_name`. This likely renders blank/incorrect alt text.

---

## 4. Footer and mobile

### Footer completeness

Current footer content:

- restaurant name
- street/suburb
- phone

Missing:

- social links
- email, although `view["visit"].fields.contact.value.email` already exists
- copyright/year
- one shared footer implementation for all Crema pages

The home page currently overrides the base footer with an empty block and then
hand-rolls its own footer at `home.html:317-327`. This means footer improvements made
in `_footer.html` will not reach the home page unless duplicated. Consolidating this
should happen before social rendering.

### Responsive/mobile findings from code

| Issue | Evidence | Confidence | Recommended action |
|---|---|---:|---|
| Columnar price tables can overflow on narrow screens. | `.cm-col-table` has no mobile wrapper/overflow/stacking rule; price headers and cells use `white-space: nowrap`; item header takes 60%. | High | Add horizontal scroll wrapper or collapse columnar tables below a mobile breakpoint. |
| Burger tap target is too small. | `.burger` is `26px` by `20px` with no padding. | High | Increase button hit area to at least 44x44 while preserving icon size. |
| Nav and hero breakpoints are mismatched. | Nav switches at 768px; hero stacks at 860px. | Medium | Screenshot around 800px; likely align burger breakpoint to 860px if nav crowds. |
| Hero CTA buttons may wrap loosely on small phones. | `.btn` has `14px 30px` padding; two CTAs wrap in `.split__cta`. | Medium | Screenshot around 360px; tighten padding/gap only if needed. |
| Gallery remains two columns below 680px. | No 1-column gallery breakpoint. | Low | Screenshot very narrow widths; optional 1-column rule if cramped. |
| Carousel has fixed mobile height. | At <=860px `.carousel { height: 380px; }`. | Low/visual | Screenshot short landscape and small portrait. |

Footer itself has low overflow risk because it is centered text with modest padding.

---

## 5. Tags vs images

### Current menu item behaviour

`_menu_item.html` renders a text-first menu row:

- item name
- dietary tags inline after the name, joined by comma
- single unlabelled price at the right
- description if present
- extras either inline or stacked depending on `section.extras_display`
- labelled variants as a small text row

The columnar menu table in `menu.html` also renders tags beside the item name. There
is no per-item image slot and no menu item photo FK in the data model. Crema only uses
section photos, such as section panel thumbnails and home menu-section tiles.

### Assessment

The current text+tags presentation looks intentional in code. It does not read like a
broken fallback because no empty image frame is rendered. This is a good fit for
venues without strong dish photography.

### Recommendation

**Recommended v1: keep item images out of Crema item rows.** Treat item images as a
future enhancement, keep tags always available, and make the text menu the intentional
default. Section-level photos already provide visual interest without requiring a
photo for every dish.

Future options:

| Option | Behaviour | Required changes |
|---|---|---|
| A. Text-only items, tags always | Current model; tags render whenever present; no item image slots. | No item-image work. Optional polish only. |
| B. Optional hero image for featured items | Items with photos render as larger feature rows; normal items stay text-only. | Add `photo_id`/relationship to menu item, migration, admin photo picker, `_menu_item.html` conditional layout, CSS for feature row. |
| C. Section tile/grid mode | A section can render photo-led dish tiles. | Depends on item photos plus a real per-template/settings display-mode mechanism. Larger template and admin change. |

Do not add an always-on image placeholder to every item. That would make photo-light
venues look unfinished.

---

## 6. Ordered task list for approval

### Must come first

The data/config work underpins both social links and CTA cleanup, but there are two
separate foundations:

- Social links belong on `Location` and flow through the existing Visit resolver/admin
  path.
- Booking URL already has a `Site` column, but needs an owner-facing edit path.
- The hardcoded Crema eyebrow should not use `Site.settings` until the settings
  reader/default pattern exists. Use an existing `Site` column or add an explicit
  field through the established site/front-page path.

### Phase 0: audit-confirmed quick fixes

| Order | Task | Touches | Dependency |
|---:|---|---|---|
| 1 | Fix hero alt text from `site.name` to `site.restaurant_name`. | `app/templates/public/crema/home.html` | None. |
| 2 | Consolidate home footer and shared footer into one Crema footer partial. | `home.html`, `_footer.html`, maybe `crema.css` modifier class | None; should precede social footer rendering. |
| 3 | Add email to the consolidated footer. | `_footer.html` | Task 2. |
| 4 | Fix burger tap target. | `crema.css` | None. |
| 5 | Protect columnar menu tables on mobile. | `menu.html`, `crema.css` | None. |

### Phase 1: data/config foundation

| Order | Task | Touches | Dependency |
|---:|---|---|---|
| 6 | Add `Location.social_links` JSONB with default empty list; hand-write migration. | `app/models/location.py`, Alembic migration | None. |
| 7 | Extend location update/create services and coordinator kwargs to accept scoped social links. | `location_service.py`, `location_coordinator.py`, tests | Task 6. |
| 8 | Extend `/admin/visit` form and POST handler to edit social links per location. | `admin/visit.html`, `app/web/admin.py` | Tasks 6-7. |
| 9 | Add `visit.social` to the resolver with no sample data. | `app/content/resolver.py`, resolver tests | Task 6. |
| 10 | Add owner-facing booking URL editing. | Likely front-page/details admin form, `SiteDetailsForm` or dedicated form, site service/coordinator | None; uses existing `Site.booking_url`. |
| 11 | Decide and wire the Crema hero eyebrow source. | Likely `Site.hero_subheading` or a new explicit front-page field | Approval needed before implementation. |

### Phase 2: Crema rendering

| Order | Task | Touches | Dependency |
|---:|---|---|---|
| 12 | Render footer social links, skipping blank/unknown URLs gracefully. | `_footer.html`, `crema.css`, tests if practical | Tasks 2 and 9. |
| 13 | Optionally render social links in the Find Us contact card. | `home.html`, `crema.css` | Task 9. |
| 14 | Replace hardcoded `Neighbourhood Cafe` eyebrow with the approved config field or omit when blank. | `home.html` | Task 11. |

### Phase 3: screenshot-gated responsive polish

| Order | Task | Touches | Dependency |
|---:|---|---|---|
| 15 | Screenshot around 800px and align nav breakpoint if crowded. | `crema.css` | Browser verification. |
| 16 | Screenshot around 360px and adjust hero CTA spacing only if awkward. | `crema.css` | Browser verification. |
| 17 | Screenshot narrow gallery and short landscape carousel; adjust only if visibly poor. | `crema.css` | Browser verification. |

### Independent work

- Tasks 1, 4, and 5 can be done immediately and independently.
- Task 2 should happen before Task 12.
- Tasks 6-9 form the social-link chain.
- Task 10 is independent of social links but needed to make existing booking CTAs truly owner-configurable.
- Task 11/14 is independent of social links and booking, but should be approved because it decides the source of venue-specific hero copy.

