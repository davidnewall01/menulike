# Restaurant Site Platform — Development Plan

> **Living document.** Companion to `restaurant_platform_design.md` (the architecture/schema
> reference). This is the *sequence* to build it. Update phases as they complete; add a
> Changelog line when the plan changes.
>
> Status markers: ✅ done · 🟡 in progress · ⬜ not started · ❓ open · 🔭 deferred

Last updated: 2026-06-18

---

## Goal & definition of done

**Get Porto Azzurro live on the SaaS platform**, replacing the static Netlify site — its real
content served from the platform database through a template, at its own domain, looking at
least as good as the current static site.

This target deliberately *shrinks* the MVP. To get one real customer live we need the vertical
spine plus a way for **us** to load their content. We do **not** need the self-serve app,
onboarding wizard, billing, template switcher, or the other templates — that's all deferred to
"customer #2+ readiness." We **concierge** Porto Azzurro.

---

## Operating model

How we build each phase (the established rhythm):

- Each phase ≈ one or more focused CC sessions with an explicit hard stop.
- **Audit-first:** CC reads and reports before implementing.
- **Browser verification is a hard gate** — tests don't catch wedge states or UX issues. Each
  phase exits only on a verified, working result in the browser.
- Small logical commits; "do not commit until confirmed" gates.
- Prompts include a "Do not" section, a manual test plan, and "re-read files before editing."

---

## Phase 0 — Walking skeleton (the spine) ⬜

Prove content flows DB → template → browser for a tenant, end to end.

- [ ] Project scaffold (FastAPI · SQLAlchemy async · Postgres · Alembic · HTMX · Jinja2 ·
      Tailwind + DaisyUI) / confirm repo & Railway env
- [ ] `tenants` / `sites` table (id, slug, restaurant_name, …)
- [ ] Tenant resolution from `Host` header (subdomain → tenant), cached lookup
- [ ] Wildcard subdomain serving on Railway (`*.<platform>.app`) + wildcard TLS
- [ ] Alembic migrations for the entities Porto Azzurro needs: site/identity, menu (5 tables),
      photos, hours, location, social/CTA
- [ ] Seed script: one tenant (Porto Azzurro) with placeholder content
- [ ] Trivial template renders seeded content from the DB

**Exit gate:** a seeded tenant renders real DB content at `{slug}.<platform>.app` over HTTPS.

---

## Phase 1 — The Porto Azzurro template (build 1 for real) ⬜

The polished public template reproducing the current site — our flagship and our sales asset.

- [ ] Site layout + nav (Eat / Drink / Visit / Gallery)
- [ ] Hero / `feature_images` (single hero from `[0]`)
- [ ] Menu rendering: menu → sections (as tabs) → subsections (headingless when unnamed) →
      items (name, description, dietary badges, price) → variants
- [ ] About section
- [ ] Gallery (from the photo library)
- [ ] Visit / contact (hours, address + map, phone, social)
- [ ] Theme tokens matching Porto Azzurro (serif display type, palette)
- [ ] Responsive / mobile

**Exit gate:** browser-verified quality parity with the static Netlify site.

---

## Phase 2 — Concierge content tooling ⬜

A thin internal surface for **us** to load one restaurant. (See decision D-1 below — building
real editors here, not throwaway scripts, because they become the self-serve editors later.)

- [ ] Internal admin auth (just us, for now)
- [ ] Details editor: name, tagline, logo, hours, location, contact, social, CTAs
- [ ] Photo library: upload to S3, set focal point, tag, assign roles (hero / gallery / about)
- [ ] Menu editor: the tree (menu / section / subsection / item / variant), drag-reorder via
      `position`, dietary tags
- [ ] Load Porto Azzurro's **actual** content

**Exit gate:** Porto Azzurro's real menu, photos, and details live in the DB and render correctly
through the Phase 1 template on the subdomain.

---

## Phase 3 — Custom domain + go live ⬜

- [ ] Integrate the custom-hostname provider (Approximated 🟡): register hostname via API
- [ ] Internal flow to attach a custom domain to a tenant → show the DNS record → verify
      "connected ✓"
- [ ] Attach Porto Azzurro's domain — concierge DNS checklist: **one record**, **never touch
      MX**, **keep old hosting until confirmed live**
- [ ] Confirm cert issued, site live, parity holds

**Exit gate:** Porto Azzurro live on the platform at its own domain, HTTPS, quality parity.
**🎯 DONE.**

---

## Deferred — customer #2+ readiness 🔭

Not needed to get Porto Azzurro live; tackled after.

- Self-serve owner admin app + onboarding wizard
- Stripe billing (subscription, payment method, invoices, customer portal)
- Design / template switcher + live preview
- Templates 2 & 3 (Photofull, Modern) + slot-discovery wireframes
- Internal-admin polish; self-serve DNS guidance (auto-detect provider, screenshot guides)
- Image CDN (Pillow fixed sizes are fine until the crop matrix hurts)

---

## Key decisions

- **D-1 (Phase 2 tooling): build thin-but-real content editors, not throwaway seed/import
  scripts.** 🟡 The menu/details editors we build to load Porto Azzurro by hand are the *same*
  ones we later expose to self-serve customers — product investment, not throwaway concierge
  work. (A one-off seed in Phase 0 to prove rendering is fine.) *Confirm before Phase 2.*
- **Concierge before self-serve.** ✅ Get the concierge path working end-to-end first; the
  self-serve app is built on top of it afterward.

---

## Open questions ❓

- [ ] Repo: own repo / stack instance for this product? (carry-over patterns assumed)
- [ ] Confirm D-1 (editors vs scripts) before starting Phase 2.
- [ ] Custom-hostname provider final pick (Approximated vs Cloudflare for SaaS) — re-pull pricing
      at Phase 3.
- [ ] Does Porto Azzurro have a domain ready to point, or do we register one with them?

---

## Changelog

- **2026-06-18** — Initial plan. Four phases to get Porto Azzurro live via concierge (walking
  skeleton → flagship template → concierge content tooling → custom domain). Self-serve,
  billing, and additional templates deferred to customer #2+ readiness.
