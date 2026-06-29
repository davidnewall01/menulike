# NEW_TEMPLATE.md — How to Build a New Template

Seeded from the instrumented Crema build (June 2025). Update as more templates
are built and patterns stabilise.

---

## What You're Building

A template is a **view over the shared content model** — it rearranges/rethemes
existing content slots (hero, logo, tagline, menus, sections, photos, etc.).
It does NOT create new data models. If a template needs a new content *type*,
that's a schema change, not a template concern.

---

## Steps (ordered, with effort notes)

### 1. Investigate (10-15 min)

- Read **Linen home.html** — the correct reference for resolver wiring
  (`view.home.fields.*` pattern)
- Read **template_resolver.py** — `FEATURE_IMAGE_MODE` dict
- Read **resolver.py** — what fields each area exposes
- Read existing tokens.html files — CSS variable naming conventions
- Check if your template's signature feature needs data already in the view
  or requires new plumbing (see Section-Grid Finding below)

**Do NOT copy Olive's code patterns** — Olive bypasses the resolver (`role_images`
direct access) which is a known bug.

### 2. Register the Template (~5 min)

Three touch points:

1. **Migration**: New `NNN_templatename.py` — INSERT into `template_meta` +
   `tag_vocabulary` + `template_tag`. Set `is_available = false` until complete.
   - Watch for `tag_vocabulary.value` (not `name`) column
   - Watch for autoincrement sequence — if prior migrations used explicit IDs,
     add `SELECT setval(...)` before inserting new tags

2. **template_resolver.py**: Add entry to `FEATURE_IMAGE_MODE` dict
   (`"single"` or `"carousel"`)

3. **Template directory**: `app/templates/public/{name}/`

### 3. Build Base Template Files (~10 min, mostly copied from Linen)

These are ~80% copied from Linen with template-specific adjustments:

- **base.html** — HTML skeleton, tokens include, CSS link, nav/footer includes,
  preview banner. Change: template paths, CSS file reference.
- **tokens.html** — CSS custom properties + Google Fonts link. **100% new** —
  defines the template's entire colour palette and typography.
- **_nav.html** — Navigation bar. ~90% copied from Linen; adjust link labels
  and button style for the template's personality.
- **_footer.html** — Footer. ~95% copied from Linen.

### 4. Build the Front Page (~20 min)

The main creative work. Read data from the resolver (`view.home.fields.*`),
NOT from `role_images` directly. Key fields:

```
view.home.fields.hero.value     → hero image URL (or None)
view.home.fields.hero.source    → "real" | "sample" | "empty"
view.home.fields.logo.value     → logo image URL (or None)
view.home.fields.tagline.value  → tagline string (or None)
view["visit"].fields.address.value → {street, suburb, ...} or None
view["visit"].fields.contact.value → {phone, email} or None
view.menu.fields.menus.value    → [Menu, ...] (with .sections, .sections[].photo)
```

Handle preview mode: show `preview-prompt` links when `render_mode == "preview"`
and `field.source != "real"`. Show `sample-badge` when `source == "sample"`.

### 5. Build the CSS (~20 min)

Hand-written, bespoke CSS per template. No Tailwind for public templates.

Conventions:
- BEM-style class names: `.component__element--modifier`
- All colours via CSS custom properties from tokens.html
- `clamp()` for responsive typography
- Mobile breakpoints: typically 860px, 768px, 520px
- `object-fit: cover` for images
- Preview banner, sample badge, and preview prompt styles needed

### 6. Verify (~5 min)

Browser-verify hard gates:
1. Front page renders with real resolver data (split/hero/whatever archetype)
2. Any signature feature (e.g. section-grid) renders with real data
3. Missing data degrades gracefully (placeholder, not crash)
4. No `role_images` crash on any render path
5. Porto Azzurro (Linen) still works after any eager-load changes

---

## Key Finding: Section-Grid Plumbing

**Question**: Are menu sections + section images available on the home page view?

**Answer**: YES, via `view.menu.fields.menus.value[N].sections[M].photo`, BUT
it required one plumbing change: `Section.photo` was not eager-loaded in
`_PUBLIC_SITE_OPTIONS` (site_service.py). Added a `joinedload(Section.photo)`
branch. Without this, accessing `section.photo` in async context would fail
with a lazy-load error.

**Cost**: One line of code (joinedload), but it required:
1. Reading the entire eager-load chain to understand what was missing
2. Knowing the difference between selectinload and joinedload patterns
3. Testing that the change didn't break existing templates

**Verdict**: The section-grid was 95% free (data model already supports it),
but the eager-load gap made it not zero-cost. Future templates that access
deeper relationships should audit `_PUBLIC_SITE_OPTIONS` first.

---

## File Checklist

```
app/templates/public/{name}/
  base.html          # HTML skeleton
  tokens.html        # CSS custom properties + fonts
  home.html          # Front page
  _nav.html          # Navigation
  _footer.html       # Footer
  menu.html          # (later chunk)
  ...                # Other inner pages

app/static/themes/{name}/
  {name}.css         # Bespoke CSS

alembic/versions/
  NNN_{name}_template.py  # Registration migration

app/web/template_resolver.py  # FEATURE_IMAGE_MODE entry
```

---

## What Was New vs Copied-from-Linen (Crema build)

| File | New vs Copied | Notes |
|------|--------------|-------|
| tokens.html | 100% new | Palette, fonts, spacing — defines the template |
| base.html | 80% Linen | Changed includes paths, CSS link |
| _nav.html | 90% Linen | Changed link labels ("Menu" not "Eat/Drink") |
| _footer.html | 95% Linen | Identical structure |
| home.html | 70% new | Split archetype is new layout; resolver wiring copied from Linen |
| crema.css | 100% new | All component styles, responsive breakpoints |
| Migration | Pattern from 023/024 | Tag seeding needed sequence fix |
| template_resolver | 1 line | Added FEATURE_IMAGE_MODE entry |
| site_service | 1 line | Added Section.photo eager-load |

---

## Surprises / Gotchas

1. **tag_vocabulary column is `value`, not `name`** — the model and migration
   use different naming than you'd expect. Check the schema before writing SQL.

2. **Autoincrement sequence not synced** — migration 023 used bulk_insert with
   explicit tag_ids, leaving the sequence at 1. New INSERTs via ON CONFLICT
   collide. Fix: `SELECT setval(...)` before inserting new tags.

3. **Menus need `is_published = true`** to appear in public render — the
   `_PUBLIC_SITE_OPTIONS` filter on `Menu.is_published.is_(True)` means
   unpublished menus won't show in the section-grid. This is correct behaviour
   but can confuse testing.

4. **`page_path_safe` fallback** — incomplete templates (missing menu.html etc.)
   automatically fall back to Linen's version of that page. This is by design
   and means you can ship a front-page-only template without breaking navigation.

5. **Olive is NOT a code reference** — it bypasses the resolver and has known
   bugs. Only use it as a visual archetype reference.

6. **`feature_image_mode` is a real design decision** — register "carousel" vs
   "single" deliberately at template creation time. Crema was initially registered
   as "single" (wrong — café = photo-forward, needs carousel). This controls which
   admin upload component renders AND requires the resolver to expose a `hero_images`
   list field (added to `_resolve_home`). A carousel template reading only `hero`
   (single URL) gets one image; it needs `hero_images` (URL list) for multi-image.
   Think about this at registration, not as an afterthought.

7. **Section-grid "verified but not rendering" discrepancy** — the chunk-1 report
   claimed "15 tiles verified" but the grid didn't render in preview. Root cause:
   `_resolve_menu()` returns `sample_value=None` for menus (sample menu tree is
   deferred). The template gated on `{% if menus_field.value %}`, which is `None`
   in preview → grid skipped entirely. The chunk-1 test passed only because real
   menus were temporarily published. Fix: add an `{% elif render_mode == "preview" %}`
   branch that shows placeholder tiles with a "Add your menu sections" prompt. This
   is template-level preview scaffolding — the resolver doesn't need to provide
   sample menu data for the grid to show its shape.

8. **Eager-load on ALL site-loading queries** — `Section.photo` needed eager-loading
   in BOTH `_PUBLIC_SITE_OPTIONS` (public render) AND `get_owner_site_preview` (admin
   preview). Missing either causes `MissingGreenlet` in async context. When adding a
   new relationship access to a template, audit every query that loads the site for
   rendering (public + preview at minimum).

---

## Restyle Cost (design-language lock-in)

The front page is the **design-language laboratory**. The Crema build proved:

- **Initial build** (working-but-plain front page): ~70 min
- **Restyle to final design language** (Option B): ~20 min
  - tokens.html: new fonts (Fraunces + DM Sans) + palette (9 named colours)
  - crema.css: full rewrite (hero → contained carousel in loose side-by-side layout,
    all components restyled to new tokens)
  - home.html: +1 structural element (eyebrow)

**Key insight:** establish tokens BEFORE building inner pages. The tokens set in the
restyle propagate to all inner pages — menu, gallery, visit, etc. Building inner pages
before locking the design language means restyling everything twice.

**Recommended order:** (1) build front page with placeholder tokens → (2) lock design
language via restyle → (3) design-language polish pass (propagating decisions only) →
(4) build inner pages using locked tokens.

**Design-language polish** (~10 min): after the restyle, a short pass fixes propagating
decisions — hero proportion, header treatment, shared eyebrow component, page container
alignment, type scale. The "local vs propagating" test: if a fix would affect inner pages,
do it now; if it's one-off local polish, defer to the whole-template pass. Crema's polish
pass fixed: nav border removal, eyebrow → shared `.eyebrow` class (13px/500/uppercase/
.22em/terracotta), unified 40px horizontal padding across nav/hero/section-grid for
vertical-column alignment.

### Ground/surface two-tone (the cosy-cafe warmth trick)

The cosy-cafe warmth came from PROMOTING a deeper warm tone (`--ground: #d8ccbd`) to be
the PAGE GROUND, with lighter warm-paper (`--surface: #fbf6ee`) as RAISED SURFACES (tiles,
carousel, nav, page column). The warm tone was already in the palette; it just needed to
be the ground, not a secondary accent. Lesson: for a warm/cosy template, the GROUND tone
carries most of the mood — decide ground-vs-surface deliberately, and define both as
tokens (`--ground`, `--surface`) so every page inherits the warmth without scattered hex.

### Count-robust grid layout (section-grid)

Signature features rendering VARIABLE-COUNT content need count-robust layout. Crema's
section-grid uses a **count-to-columns mapping** (constrain / guide / degrade):

- Counts 1-5: N columns (single row)
- 6→3, 7→4, 8→4, 9→3, 10→5, 11→4, 12→3: clean rectangles or near-clean
- 13+: fallback to 4 columns, last row left-aligned acceptable
- Short last rows (7, 11): centred via `justify-content: center` on a flex container
- Responsive: tablet→2 cols, mobile→1 col (overrides count logic)

Implementation: Jinja computes `cols` from `all_sections|length`, sets `--grid-cols` CSS
custom property on the container; flex layout with `calc()` tile widths + `justify-content:
center` handles both exact-fit rows and centred partial rows.

**5-across verdict** (pending visual review): at max-width 1200px with 40px padding, 5-col
tiles are ~208px wide / ~156px tall (4:3). Borderline — workable for short section names
with photos, tight for long names or placeholder-heavy grids. Decision: ship 5-across,
review live, cap to 4 if too thin in practice (5→3+2 centred).

### Single-page scroll architecture

Single-page scroll (Crema) REUSES the content model, resolver fields, and guided-blank-
preview prompts — it's a PRESENTATION change, not a data change. Scroll sections read the
same fields that multi-page templates (Linen) read as separate routes:
- Our Story → `view.our_story.fields.blocks` (same as Linen's `/our-story` page)
- Gallery → `view.gallery.fields.photos` (same as Linen's `/gallery` page)
- Find Us → `view.visit.fields.{address,hours,contact}` (same as Linen's `/visit` page)

**New scroll-specific concerns (not needed in multi-page):**

1. **Per-section VISIBILITY logic** — the declared property of scroll templates:
   - Preview: ALWAYS render (empty sections show "Add your X" prompts = onboarding worklist)
   - Public: render ONLY if real content exists (hide empty sections = no blank gaps)
   - Multi-page doesn't need this (pages are destinations; scroll sections are inline)

2. **Anchor nav with empty-section-aware link hiding** — nav links become `#anchors`;
   in public mode, if a section is hidden, its nav link is also omitted. MENU stays a
   page link (separate route).

3. **Hours plumbing** — `hours_by_day`, `day_names`, `hours_exceptions` were route-level
   context vars computed only in the `/visit` route. Scroll templates need them on the
   home route too. Extracted into `_build_hours_context()` helper, called from both
   `home()` and `visit()` routes (+ admin `preview_home()`). ~5 lines of plumbing.

**Effort breakdown:**
- Plumbing (hours helper + route wiring): ~10 min, known pattern
- Scroll sections (Our Story + Gallery + Find Us): ~80% reused from Linen's field-reading
  patterns, ~20% new (layout as stacked sections, visibility conditionals, anchor offset)
- CSS for 3 sections: ~15 min (story blocks, gallery grid, visit cards — all in Crema tokens)
- Nav anchor conversion: ~5 min

### Shared page container (the "local vs propagating" rule)

Inconsistent section widths LOOK like local polish but the cause (no shared container) is
propagating — fix as ONE shared page container all sections reference, not per-section
padding. Crema uses `.page-col` (max-width + surface bg) as the outer column, with 40px
horizontal padding on every section inside it. Scroll sections initially had an inner
`max-width: 800px` that broke alignment — removed so they inherit the full page-col width.
Story text gets its own `max-width: 640px` to stay readable without constraining the whole
section. Recurrence of the earlier hero/grid alignment fix — establish the canonical page
container ONCE and have everything use it.

### Hero arrangement variants (future feature — NOT built)

The restyle chose "Option B" (loose side-by-side, contained carousel). Other archetypes
exist: centred hero, full-bleed banner, stacked. This is a LOGGED FUTURE FEATURE —
a constrained hero-choice option ("constrain-to-beauty") where templates offer 2-3
pre-designed hero arrangements, not freeform layout. Crema ships with side-by-side only.
