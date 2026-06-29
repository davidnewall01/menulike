# Menulike — Development Plan

> **Living document.** Companion to `restaurant_platform_design.md` (the architecture/schema
> reference). This is the *sequence* to build it. Update phases as they complete; add a
> Changelog line when the plan changes.
>
> Status markers: ✅ done · 🟡 in progress · ⬜ not started · ❓ open · 🔭 deferred

Last updated: 2026-06-26

---

## Where we are (reality, June 2026)

**Menulike is LIVE in production.** The original plan (get Porto Azzurro live via concierge) is
**done** — and more. Current reality:

- ✅ Live multi-tenant SaaS on Railway (prod Postgres, S3, all env config).
- ✅ Self-serve signup + the full build/configure/preview/publish flow — proven with **multiple
  real tenants** signing up from different machines.
- ✅ Porto Azzurro: account created, content loaded, **published**, live at
  `portoazzurro.menulike.com`; custom domain (`portoazzurro.com.au`) handed off to Eve & Carlos
  (DNS pointing in their hands).
- ✅ Custom-domain routing built + proven end-to-end through the Approximated proxy (the
  `apx-incoming-host` header gotcha solved; unique-constraint + active-only security model).
- ✅ Tailwind CDN → committed build artifact (no CDN, no build step in deploy).
- ✅ The Details dismantle (chunks 1–4) + single-location read-cutover.
- ✅ Approximated proven manually (cert issuance, routing, the `/api/vhosts` spec captured).

**So the question is no longer "get Porto live." It's "how does menulike become a business."**

---

## The organising principle

The roadmap is a **dependency graph + a revenue clock**, not a wishlist sorted by coolness.
Almost everything on the idea list is *valuable*; the question is always: **what does this
unlock, and what gets us to paying customers soonest?**

Two hard-won rules:
- **Features earn their place by being required for a milestone, not by being on a wishlist.**
- **Build the revenue engine first; let paying customers fund and direct the premium features**
  by what they'll actually pay for. (We have a "~70% of sites could use this" gut read from real
  feedback — turn it into *paying* customers with minimum core, then let them direct the rest.)

---

## Operating model (the established rhythm — unchanged)

- Each phase ≈ one or more focused CC sessions with an explicit hard stop.
- **Audit-first:** CC reads and reports (Phase 0 investigate + STOP) before implementing.
- **Browser verification is a hard gate** — tests don't catch wedge states or UX issues.
- Small logical commits; "do not commit until confirmed" gates.
- Prompts: a "Do NOT" scope section, a manual test plan, "re-read files before editing."
- Architecture invariants hold: skinny routes → coordinators (commit) → services (flush),
  IDOR check at top of every service, hand-written migrations, resolver owns presentation.
- Milestone code reviews: Codex + CC, report-only, reconcile, then fix.

---

## PHASE A — Finish Porto (concierge tail) 🟡

Almost done; no real build left.

- [x] Porto published + live on `portoazzurro.menulike.com`.
- [x] Gallery auto-hides when no real gallery photos; logo recolours dark on interior pages.
- [x] Custom domain configured + handed to Eve & Carlos.
- [ ] Eve & Carlos point DNS → cert issues → Porto live on `portoazzurro.com.au`. *(external —
      their action; watch the four Approximated checks go green)*
- [ ] Porto's photos trickle in (gallery gracefully hidden until then — not blocking).

**Exit:** Porto live on their own domain. *(Then Porto is the reference/sales asset.)*

---

## PHASE B — "Get to paid" (the revenue engine) ⬜  ← THE NEXT REAL PHASE

This is the cluster that turns menulike from "a product with pilots" into "a business that takes
money from strangers." Nothing here is optional for a business; everything *after* this phase is
premium/customer-directed.

**Two sub-stages:** (1) take money from the *first few* (domains still concierge'd by SQL — fine
at 3–5 customers); (2) *true self-serve* (domain automation) before opening to stranger volume.

Rough build order:

- [ ] **Billing — menulike's own subscription (Stripe).** The gate to all revenue. Plans, payment
      method, the publish→pay coupling. *Probably the true #1.*
- [x] **The freemium boundary — DECIDED: free to build/preview, PAY TO PUBLISH.** The free tier
      delivers the full wow (build + preview the real site, instant-menu magic); going *public*
      (subdomain OR custom domain) is the pay event. Keeps something real behind the wall (being
      live at all); sidesteps free-subdomain cannibalization. The wildcard `*.menulike.com` free-
      subdomain idea is OFF the table. *(Still open: is custom-domain a higher tier than subdomain,
      or included? — a pricing-tier question, not the freemium line. See pricing in Open Qs.)*
- [ ] **Public signup + marketing site** — the funnel. Signup *exists*; needs the public front
      door + a landing page that **leads with the instant-menu wow** (empirically the hook). The
      pitch leads with the *diner's* pain (no more PDF menus on your phone), owner ease is the
      kicker. `menulike.com` apex currently parks; this fills it.
- [ ] **Template viewer** (sample images + cuisine picker) — so a prospect can *see* templates
      before committing. Part of the funnel.
- [ ] **Events page (display-only) — scoped as a Mama Dumplings SALES-CLOSER.** A thin content
      type: list of upcoming events (title, date, description, optional image), rendered on the
      page. Optional smart: auto-hide the block after the date passes. **Justification: it closes a
      paying guinea-pig (Mama Dumplings does ticketed nights), and closing first payers IS Phase
      B's job — NOT "build it for template design later" (template design works off sample data).**
      **OUT OF SCOPE (the scope guard — keeps it a few-hours feature, not a mini-project):**
      ticketing, RSVP, recurring events, capacity, past-event archives, calendar views. Any of
      those → it's become the commerce build → move to D.
- [ ] **Approximated API integration + custom-domain self-serve UX** — the customer adds their own
      domain through the dashboard (enters domain → DNS instructions → status → live), driven by
      `POST /api/vhosts` + status read/webhook flipping `custom_domain.status` to active when
      resolving. **This is core to the Phase B promise** (self-serve go-live = the PAID step; can't
      have a you-shaped bottleneck at the moment of payment). Concierge the *first few* by SQL;
      build this *before* stranger volume. `approximated_id` column reserved; recon done (API +
      webhooks buildable).
- [ ] **FAQ / instructions / "why is this happening" help** — so self-serve doesn't drown you in
      support. Lightweight but real.
- [ ] **Audit log (consequential actions only)** — build *with* billing. Audit account/plan/
      billing changes, publish, domain changes, deletions. **NOT** content edits (noise). Trigger:
      the moment money makes "what happened and when" a question.
- [ ] **🔒 Whole-app security audit — THE GATE before going properly public.** IDOR sweep across
      *every* surface, auth hardening, public attack surface, rate-limiting, input validation.
      Strangers + money must NOT go live without this pass. (Custom-domain + chunk-1-4 reviews
      done; this is the holistic one. Moved up from Phase E — "before public" = end of Phase B,
      not a scale-nicety.)

**Exit:** a stranger can find menulike, sign up, build, pay, and go live on their own domain
without you touching anything — and it's been security-audited before that door opened.

---

## PHASE C — The moat: templates × curated variation ⬜

The template *library* is the moat (§1 design doc). But the sharp insight from this session:
**curated variation may be a higher-leverage moat play than raw template count.**

- [ ] **Template infrastructure** (the "factory") — Olive/Slate page-complete; preview-honours-
      template (retire Linen-hardcode); the slot manifest (generalised from `FEATURE_IMAGE_MODE`);
      template-selection→dashboard. *Gates everything below.*
- [ ] **Theme multiplier — CURATED variations, never free choice. START with LIGHT/DARK only.**
      First step (a cheap *test* of the whole curated-variation thesis): light/dark mode per
      template, **where appropriate** (some templates are designed dark — e.g. Linen's hero — so
      it's per-template "does a light/dark variant make sense", not universal). NO font changes
      yet. If owners value light/dark → validates investing in fuller curated palettes (3–5
      designer palettes + 2–3 font pairings per template). If they shrug → the multiplier isn't the
      moat, and you've learned it cheaply. **Free colour/font choice GUTS the "always beautiful"
      moat — curation extends it.** `template × curated-palette × curated-fonts` = huge apparent
      range from bounded design work. *(Possibly higher-leverage than 10 new templates.)*
- [ ] **New templates** toward "a dozen" — the catalogue, once the factory + multiplier exist.
      "A dozen good templates → 80–90% fit" is the thesis (§1). Build *after* the factory; sequence
      *after* the funnel (no point having 12 templates if no one can sign up).
- [ ] **Linen additions** (incremental): events block, social links, T&Cs page.

**Exit:** genuine variety (templates × curated themes) so most prospects find an 80–90% fit.

---

## PHASE D — Premium features (post-revenue, customer-directed) 🔭

Built *in response to* what paying customers ask for / will pay for. Roughly in likely-demand
order. Most are **upsells / plan differentiators**.

- [ ] **Events (display-only)** — *first low-hanging fruit; a few hours.* A content type showing
      upcoming events beautifully. Smarts: auto-remove the block after the date passes. **NO
      ticketing** (that's the commerce build — separate, later, via the connect model below).
- [ ] **Dietary / allergen filtering** — *strong differentiator, data already captured.* Let
      diners filter "show me gluten-free" — a structured-data superpower a PDF can never match.
- [ ] **QR-to-live-menu** — *cheap, real, on-thesis (Lawrence's "no PDF" win).* Table-tent QR →
      live menu. (NB: QR-to-**order** is the decade-old dream but it's full hospitality ordering /
      hardware integration — a *pivot*, not a feature. Keep the dream; build the cheap half.)
- [ ] **PDF menu generator** — *on-thesis: one source of truth, many outputs (web/print/QR).*
      ~10 standard print templates, pick one, populated with logo + menu + non-menu info. NOT
      Canva. A retention/lock-in play (menu lives in menulike → reprinting is one click).
- [ ] **Owner analytics** — "247 people viewed your menu this week." First-party preferred;
      bot-filtering is the real work. Sticky, pitch-able, "owns-the-audience" thesis.
- [ ] **Commerce via the CONNECT model** (tickets / vouchers / shop) — **the client connects
      their OWN account** (Stripe Connect pattern), menulike provides the linking form + the
      beautiful native *presentation*, money flows to *their* account. Security: never hold money
      or credentials; store tokens (encrypted), verify webhooks, minimal scope, money never flows
      through us → stays out of deep PCI scope. **menulike owns presentation, delegates the
      transaction.** Native browsing on your site + clean Stripe Checkout handoff (not a janky
      iframe). *Don't build a commerce platform.*
- [ ] **Reservations** — integrate/embed a specialist (connect model), don't build a booking
      engine.
- [ ] **Delivery links** (Uber Eats / Deliveroo) — the *link/button* is a 1-hour feature; the
      *deep* menu-sync integration is a trap. Do the link, never the sync.
- [ ] **Social cross-posting** — the aggregator (§11 design doc), never Meta-direct; bundled into
      plan tier.
- [ ] **Rewards, Functions & Catering, multi-site support** — plan differentiators / specific-
      segment features, demand-driven.

**TRAPS — resist hard:** online food ordering + **POS/kitchen hardware integration** (a different
company; every POS is bespoke; has eaten whole companies). Deep delivery-platform integration.
Building any commerce/payments *platform* ourselves. Free-form colour/font customization (guts the
moat).

---

## PHASE E — Scale & ops (demand-triggered) 🔭

Built as load demands — genuinely deferred. *(Note: custom-domain self-serve and the whole-app
security audit moved UP to Phase B — they're core to "self-serve go-live" and "before public",
not scale-niceties.)*

- [ ] **Admin / concierge screens** — manage tenants/support via UI instead of raw SQL.
      **Demand-triggered, likely B/C-ish** (SQL works at 3–10 customers; build when SQL surgery
      starts costing time or causing errors on *paying* customers' live accounts — you'll feel it).
- [ ] **Stale-pending domain auto-expiry** — unactivated domain claims (pending, never resolved)
      auto-free after N days, so squatters can't permanently block a domain. *(Self-serve-era refinement.)*
- [ ] **Image CDN** — Pillow fixed sizes fine until the crop matrix / traffic hurts. *(Genuinely
      far off — pure performance-at-scale.)*

---

## Key decisions (locked this session)

- **Concierge Porto, harvest self-serve learnings from a later lower-stakes customer.** ✅
- **Commerce = connect-their-own-account, never build payments.** menulike owns presentation,
  delegates transaction (Stripe Connect pattern). ✅
- **Theme multiplier = curated variation, never free choice.** Protects the "always beautiful"
  moat. ✅
- **Events = display-only first; ticketing is a separate later commerce build.** ✅
- **Audit log = consequential actions only, built with billing.** ✅
- **Custom-domain security = global unique constraint + active-only resolution** (no TXT
  verification — friction; A-record-pointing + resolution-check is implicit proof of control). ✅
- **The instant-menu is the marketing hook** — owner wow (upload→beautiful) AND diner wow (no PDF
  on your phone). Pitch leads with the diner's pain, owner ease is the kicker. ✅ *(Real feedback:
  Lawrence — a diner — independently flagged "so nice not to download a PDF.")*
- **Freemium line = free build/preview, PAY TO PUBLISH.** Going public (subdomain or custom domain)
  is the pay event. Free-live-subdomain idea off the table. ✅
- **Theme multiplier starts as LIGHT/DARK only (no fonts), per-template where appropriate** — a
  cheap test of the curated-variation thesis before fuller palettes. ✅
- **Positioning = website platform NOW, commerce additive LATER.** Clean architecture keeps commerce
  open; "website platform" defers, doesn't foreclose. ✅
- **Events → Phase B, scoped display-only, justified as a Mama Dumplings sales-closer** (ticketing/
  RSVP/recurrence OUT). ✅
- **Guinea-pigs pay a discounted "founding member" rate** — even token payment = real willingness-
  to-pay validation, and a better frame than "would you pay?" ✅
- **Whole-app security audit = the GATE at end of Phase B** (before public), not a Phase E nicety. ✅
- **Custom-domain self-serve (API + UX) belongs in Phase B** (it's the paid self-serve go-live step;
  concierge the first few by SQL, automate before stranger volume). ✅

---

## Open questions ❓

- [ ] **Pricing** — what's a restaurant pay per month, and what are the tiers? (Even one paying
      customer covers the Approximated $30/mo.) Sub-question now the freemium line is set: is
      *custom domain* a higher tier than *subdomain*, or included in the one paid plan?
- [ ] **The moat: more templates vs more curated variation?** Light/dark is the first cheap test.
      If curated variation lands, it may give more perceived choice for less work than 10 new
      templates *and* keep the beauty guarantee tighter. Let the light/dark test inform this before
      committing to "10 new templates."
- [ ] **Positioning depth** — settled as "website platform now"; the open part is *how far* commerce
      eventually goes (secondary surface vs core). Customer-directed; revisit when paying customers
      pull on it.
- [ ] **Is Porto a *paying* customer or a free reference/showcase?** Likely a discounted founding-
      member rate (the guinea-pig conversation hasn't happened yet). Determines whether their
      Approximated cost is revenue-covered or a sales-asset investment.

### Resolved this session
- ~~Freemium boundary~~ → **pay to publish** (free build/preview).
- ~~Custom-domain self-serve placement~~ → **Phase B** (core to self-serve go-live).
- ~~Security audit placement~~ → **end of Phase B** (before public).
- ~~Theme multiplier shape~~ → **curated only; light/dark first**.
- ~~Events placement~~ → **Phase B, display-only, sales-closer**.
- ~~Positioning (now)~~ → **website platform; commerce additive later**.

---

## Changelog

- **2026-06-26** — **Full rewrite.** The original (2026-06-18) plan — concierge Porto, defer
  everything — is DONE and was actively misleading. New reality: menulike live in prod,
  multi-tenant, self-serve flow proven, Porto published + custom domain handed off, Approximated
  + custom-domain routing built. Re-framed around "how menulike becomes a business": Phase A
  (finish Porto) → B (get to paid: billing, funnel, Approximated API, FAQ, audit log) → C (the
  moat: template infra + curated theme multiplier + new templates) → D (premium, post-revenue,
  customer-directed, via the connect model — resist the commerce/hardware traps) → E (self-serve
  scale & ops + whole-app security audit). Locked decisions on commerce (connect model), theme
  multiplier (curated only), events (display-only), audit log (consequential + with billing).
  Open: freemium boundary, moat shape, positioning, pricing, Porto-paying-or-showcase.
- **2026-06-18** — Initial plan (four phases to get Porto live via concierge). Superseded.
