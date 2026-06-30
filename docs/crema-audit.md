# Crema Template Audit

Audit date: 2026-07-01. AUDIT ONLY — no changes made.

---

## 1. Territory Map

### File inventory

| File | Role |
|---|---|
| `templates/public/crema/base.html` | Layout shell: head, nav include, content block, footer include |
| `templates/public/crema/tokens.html` | CSS custom properties (inline `<style>`) + Google Fonts preconnect |
| `templates/public/crema/_nav.html` | Sticky nav + burger menu (mobile) |
| `templates/public/crema/_footer.html` | Shared footer (used by menu page, base.html default) |
| `templates/public/crema/home.html` | Home: hero carousel, section-grid tiles, Our Story, Gallery, Find Us, inline footer |
| `templates/public/crema/menu.html` | Full menu page: section panels, columnar tables, footer blocks |
| `templates/public/crema/_menu_item.html` | Single item partial (inline/stacked extras, variants, tags) |
| `static/themes/crema/crema.css` | All styles (~849 lines). Breakpoints at 860px, 768px, 680px, 520px |

### Per-venue config pattern

Venue-specific data flows through two paths:

1. **Site model columns** — `restaurant_name`, `tagline`, `booking_url`, `order_url`,
   `meta_title`, `meta_description`, `settings` (JSONB). Read directly in templates
   as `site.restaurant_name`, `site.booking_url` etc.

2. **Content resolver** (`app/content/resolver.py`) — `resolve_site_view()` builds a
   `SiteView` dict of `AreaView` objects, each with `fields` (keyed `FieldView` with
   `.value` and `.source`). Areas: `home`, `our_story`, `visit`, `gallery`, `menu`,
   `events`, `seo`. Templates access as `view.home.fields.hero.value` etc.

   Visit data (address, hours, contact) comes from the **Location** model (first
   location by position), resolved into `view["visit"].fields.*`.

3. **`settings` JSONB** — per-site design config with `SETTINGS_DEFAULTS` pattern.
   Currently used for other templates; Crema does not yet read any settings keys
   (the tokens.html hardcodes all colour/font values).

**Key observation:** `social_links` is spec'd in the design doc (§6b: `social_links —
list of {platform, url}, optional`) but **not yet implemented** — no column on
Location or Site, no resolver field, no admin form, no template rendering.

---

## 2. Social Links — Finding & Specification

### Current state
- **No mechanism exists.** No model column, no admin UI, no resolver field, no
  template rendering anywhere in the codebase.
- The design doc specs it as a Location-level field (`social_links — list of
  {platform, url}`), but it was never built.

### Recommended implementation

**Where the data lives:** Add a `social_links` JSONB column to the **Location** model
(matching the design doc). Shape: `[{"platform": "instagram", "url": "https://..."}, ...]`.
Supported platforms: `instagram`, `facebook`, `tiktok`, `twitter` (X), `youtube`,
`tripadvisor`, `google`. Blank/absent = not rendered.

**Why Location, not Site:** The design doc places it on Location, and it's logically
per-venue contact info (a multi-location venue may have different Instagram accounts).
The resolver already reads from the first Location for address/hours/contact — social
links extend the same pattern.

**Resolver:** Add a `social_links` field to the `visit` area in `_resolve_visit()`.
`never_sample=True` (same as address/contact — don't show fake social links).

**Admin:** Add to the existing Visit/Location admin form — a repeatable
platform+URL pair, or a simpler flat form with one input per platform.

**Template consumers:**
- `_footer.html` (shared) — renders social icon links for any non-blank platform
- `home.html` inline footer — same
- Optionally: Contact card in Find Us section

**Blank platforms render nothing** — no empty icon slots, no "follow us" heading
if all are blank.

---

## 3. Dead Links Inventory

| # | Link text | File:line | Target | Class | Action |
|---|---|---|---|---|---|
| 1 | `{restaurant_name}` (brand) | `_nav.html:3` | `{{ nav_prefix or '/' }}` | (a) working | OK |
| 2 | Menu | `_nav.html:16` | `{{ nav_prefix }}/menu` | (a) working | OK |
| 3 | Our Story | `_nav.html:17` | `#our-story` | (a) working | Conditional on source=real |
| 4 | Gallery | `_nav.html:18` | `#gallery` | (a) working | Conditional on source=real |
| 5 | Find Us | `_nav.html:19` | `#find-us` | (a) working | Conditional on source=real |
| 6 | Book | `_nav.html:21` | `{{ site.booking_url }}` | (d) config-driven | OK — conditional on booking_url |
| 7 | Menu (mobile) | `_nav.html:28` | `{{ nav_prefix }}/menu` | (a) working | OK |
| 8 | Our Story (mobile) | `_nav.html:29` | `#our-story` | (a) working | OK |
| 9 | Gallery (mobile) | `_nav.html:30` | `#gallery` | (a) working | OK |
| 10 | Find Us (mobile) | `_nav.html:31` | `#find-us` | (a) working | OK |
| 11 | Book (mobile) | `_nav.html:33` | `{{ site.booking_url }}` | (d) config-driven | OK |
| 12 | View Menu | `home.html:79` | `{{ nav_prefix }}/menu` | (a) working | OK |
| 13 | Book a Table | `home.html:81` | `{{ site.booking_url }}` | (d) config-driven | OK — conditional |
| 14 | Section grid tiles | `home.html:128` | `/menu#section-{uuid}` | (a) working | OK — deep-link anchors exist |
| 15 | Phone (contact) | `home.html:295` | `tel:{{ cv.phone }}` | (b) external | OK |
| 16 | Email (contact) | `home.html:298` | `mailto:{{ cv.email }}` | (b) external | OK |
| 17 | Book a Table (visit) | `home.html:301` | `{{ site.booking_url }}` | (d) config-driven | OK — conditional |
| 18 | Eyebrow "Neighbourhood Cafe" | `home.html:58` | n/a (not a link) | **(c) HARDCODED TEXT** | **Should be config-driven or removed** |

### Findings

- **No dead links** — all links are either conditional on data presence or point to
  working internal routes.
- **One hardcoded text issue:** `home.html:58` hardcodes `"Neighbourhood Cafe"` as
  the eyebrow text. This is venue-specific copy — it should either come from a
  config/settings field (e.g. `settings.eyebrow_text`) or be removed. A seafood
  restaurant wouldn't call itself "Neighbourhood Cafe".
- **`site.name` bug:** `home.html:27` uses `site.name` for carousel alt text, but
  the Site model only has `site.restaurant_name`. This renders blank alt text.
  Should be `site.restaurant_name`.
- **Booking URL** renders correctly when present, hides cleanly when absent. No
  admin form exists for owners to set it — currently internal-admin/seed only.
- **`order_url`** exists on the Site model but is never referenced in any Crema
  template. This is correct per CLAUDE.md (ordering is deferred), but worth noting.

---

## 4. Footer + Mobile Audit

### Footer

The footer is minimal (both shared `_footer.html` and the home inline footer):
- Restaurant name (Fraunces)
- Address (street, suburb) if present
- Phone if present
- Dark background (`--ink`), cream text, centred

**Missing from footer:**
- Social links (not yet built — see section 2)
- Email (the contact resolver provides it, footer doesn't render it)
- Copyright/year line
- Any navigation links (some templates include footer nav — optional)

**home.html has TWO footers:** The home page overrides `{% block footer %}` to empty
(`_footer.html` is suppressed) and renders its own inline footer at line 317-327.
This creates a maintenance risk — changes to `_footer.html` don't propagate to the
home page. Should consolidate: either include the shared partial with a modifier
class, or extract the home footer into the same partial with a flag.

### Mobile / Responsive

**Breakpoints in crema.css:**

| Breakpoint | What changes |
|---|---|
| 860px | Split hero → single column; menu two-col → single-col; section-grid tiles → 2-wide |
| 768px | Desktop nav links hidden, burger shown, mobile menu enabled |
| 680px | Story blocks → single column; gallery → 2-col; visit cards → stacked; scroll-section padding reduced |
| 520px | Section-grid tiles → full-width single column |

**Issues identified from code:**

1. **Nav breakpoint mismatch (768px) vs content breakpoint (860px):** Between 768-860px
   the nav still shows desktop links but the hero is already single-column. The nav
   links may crowd on tablets at this width. **Suspect — needs screenshot to confirm.**

2. **`.btn` padding (14px 30px):** On narrow screens, two side-by-side CTA buttons
   ("View Menu" + "Book a Table") may overflow or wrap awkwardly. `flex-wrap: wrap` is
   set on `.split__cta` which helps, but the individual buttons are fairly wide.
   **Suspect — needs screenshot to confirm.**

3. **Columnar price table on mobile:** No mobile-specific styling for `.cm-col-table`.
   A table with 3+ variant columns will overflow horizontally or cramp on narrow
   screens. **Likely issue — needs screenshot of a columnar section on mobile.**

4. **Gallery grid:** Goes to 2-col at 680px but never to 1-col. On very narrow screens
   (<400px) the 2-col grid may feel cramped. Minor — the images have aspect-ratio
   constraints so they won't break, just get small.

5. **Visit cards (3-col → 1-col at 680px):** Clean collapse, no issues expected.

6. **Footer:** No responsive issues — it's just centred text, works at any width.

7. **Carousel height (380px on mobile):** Fixed pixel height. On very short
   landscape phones this may consume too much viewport. Minor.

8. **Burger tap target:** 26x20px is below the recommended 44x44px minimum for
   touch targets (WCAG). The clickable area should be larger.

---

## 5. Tags vs Images — Menu Item Audit

### Current implementation

The `_menu_item.html` partial renders **text-only items** — there is no per-item
image support:

```
ITEM NAME  V, GF                    $22.00
Description text here
extras line (inline or stacked)
variants (if multi/labelled)
```

- **Dietary tags** render inline after the item name in sage-green uppercase
  (`.cm-item__tags`). Always shown when present. Looks intentional and clean.
- **No item image** field or rendering exists. The menu data model (`MenuItem`)
  does not have a photo/image field — items are text-only by design.
- **Section-level photos** exist (thumbnail in panel header), but per-item photos
  are not part of the data model.

### Assessment

The text+tags presentation **already looks intentional** — it reads like a proper
typeset cafe menu. This is not a broken fallback; it's the design. The clean
two-column layout, balanced spacing, and consistent tag styling make it work.

### Recommendations

**Option A (recommended for v1): Stay text-only, tags always visible.**
No changes needed. The current approach suits the concierge-first model — most
venues being onboarded won't have per-dish photography. The text menu with tags
is the Crema identity: warm typography, scannable. Adding per-item images would
require a new data model field and would clutter the two-column balance layout.

**Option B (future): Optional per-item hero image for featured items.**
If/when `MenuItem` gains an optional `photo_id` FK, featured items with photos
could render as a wider "hero item" card (spanning both columns, image left,
text right). Non-photo items stay as text rows. This would require:
- Migration: add `photo_id` FK to `menu_items` table
- Model: add relationship
- Admin: photo picker on item edit
- Template: conditional image rendering with `break-inside: avoid` and
  `column-span: all` for the hero variant
- CSS: new `.cm-item--hero` class

**Option C (future): Image grid/tile mode per section.**
A section-level setting (`item_display: "list" | "tiles"`) where tiles show
item photo + name + price in a grid. Requires per-item photos (Option B
prerequisite) plus significant template/CSS work. Parked.

**Recommendation:** Ship v1 as-is (Option A). The text menu is the right call
for concierge-first. Revisit Options B/C when self-serve owners with good
photography become the primary user.

---

## 6. Ordered Task List

Dependencies mapped. Config/data work comes first since templates consume it.

### Phase 1: Data & config foundation

| # | Task | Touches | Depends on | Notes |
|---|---|---|---|---|
| 1 | **Add `social_links` JSONB to Location model** | migration, `location.py` | — | `[{platform, url}]`, nullable, default `[]` |
| 2 | **Resolve social_links in visit area** | `resolver.py` | 1 | New field in `_resolve_visit()`, `never_sample=True` |
| 3 | **Admin form for social links** | admin templates, `admin.py`, schemas | 1 | Add to Visit/Location edit form. One input per platform (instagram, facebook, tiktok, twitter, youtube, tripadvisor, google) |
| 4 | **Add eyebrow text to settings** | `settings` JSONB or new Site column | — | Default: `None` (template falls back to restaurant type or omits). Crema currently hardcodes "Neighbourhood Cafe" |
| 5 | **Admin form for eyebrow text** | admin templates | 4 | Simple text input on front-page or site-details form |

### Phase 2: Template fixes (independent of each other, depend on Phase 1)

| # | Task | Touches | Depends on | Notes |
|---|---|---|---|---|
| 6 | **Render social links in footer** | `_footer.html`, `home.html` (inline footer), `crema.css` | 2 | SVG icons per platform, conditional on non-blank URL |
| 7 | **Consolidate home footer with shared footer** | `home.html`, `_footer.html` | — | Eliminate duplicate footer. Either include shared partial with modifier, or extract to single source |
| 8 | **Fix `site.name` → `site.restaurant_name`** | `home.html:27` | — | Bug: blank alt text on carousel images |
| 9 | **Replace hardcoded eyebrow** | `home.html:58` | 4,5 | Read from settings/config, fall back gracefully |
| 10 | **Add email to footer** | `_footer.html`, `home.html` | — | Resolver already provides it; footer just doesn't render it |

### Phase 3: Mobile/responsive polish

| # | Task | Touches | Depends on | Notes |
|---|---|---|---|---|
| 11 | **Columnar table mobile overflow** | `crema.css` | — | Add `overflow-x: auto` wrapper or responsive table collapse for `.cm-col-table` |
| 12 | **Align nav breakpoint with content** | `crema.css` | — | Consider moving burger breakpoint from 768px to 860px to match hero collapse |
| 13 | **Increase burger tap target** | `crema.css` | — | Pad to >=44x44px clickable area |
| 14 | **Verify CTA button wrapping on mobile** | manual test | — | Screenshot needed at ~400px — `.split__cta` flex-wrap is set but buttons may still be too wide |

### Independent quick fixes (can be done anytime)

| # | Task | Touches | Depends on | Notes |
|---|---|---|---|---|
| 8 | Fix `site.name` bug | `home.html` | — | One-line fix |
| 10 | Add email to footer | `_footer.html` + `home.html` | — | Small template change |
| 13 | Burger tap target | `crema.css` | — | CSS-only |

### Execution order recommendation

1. **Task 8** (site.name bug — one-line, zero risk)
2. **Tasks 1-3** (social_links: migration → resolver → admin form)
3. **Tasks 4-5** (eyebrow config)
4. **Tasks 6-7** (footer consolidation + social rendering)
5. **Tasks 9-10** (eyebrow + email in footer)
6. **Tasks 11-14** (mobile polish — can be batched)

Tasks 8, 10, 11, 12, 13 are all independent and can be done in any order or
parallelised. The social links chain (1→2→3→6) is the longest dependency path
and should start first.
