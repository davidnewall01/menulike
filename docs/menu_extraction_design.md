# menulike — Menu Extraction (Design)

*Status: design, pre-build. Scope: first slice, Porto-first. Last updated 2026-06-22.*

The onboarding wedge: turn a restaurant's existing menu (however it exists) into structured
menu data without retyping. This doc specs the **first slice only** — a single PDF → structured
draft → review → commit into the menu tree — built on the Porto Azzurro food menu as the pilot
shape. Everything else (image, paste-text, URL, multi-menu split, merge-into-existing) is named
and deferred at the end.

---

## 1. Scope

**In (this slice)**
- One **PDF** upload (Porto's `Food.pdf`).
- **Vision-based** extraction → structured menu JSON.
- A light **`extras`** slot on items so add-ons are captured, not dropped, plus section- and
  menu-level **note** capture.
- An **async extraction job** (the LLM call takes seconds; the upload request must not block).
- **Review → commit** into the menu tree, with unreviewed data kept off the public site until
  the owner confirms.

**Out (named, deferred — see §9)**
- Image / paste-text / URL sources.
- Multi-menu split within one source (Porto's food is a *single* menu, so this slice never
  triggers it — that's the point of starting here).
- Merge/replace into an already-populated menu.
- The structured, ordering-grade modifier engine (foodbooking's lane — likely permanent out).

**Why Porto first.** Its food PDF is one menu's worth of content, so it exercises the whole
extract → review → commit spine on the simplest target shape. We add the split, the other
sources, and merge semantics as the *next* slice, when a real multi-menu source forces them.

---

## 2. End-to-end flow

```
upload PDF ─▶ create extraction job (status=processing, file→S3)
            ─▶ [background] rasterize pages → vision model → structured JSON
            ─▶ store JSON on the job (status=ready)  |  (status=error on failure)
owner opens review ─▶ edit / fix / confirm target menu
            ─▶ commit ─▶ write Menu + Section/Subsection/Item/Variant tree
            ─▶ menu goes live when the owner publishes
```

The job record exists primarily to absorb the **latency** (a vision call over a 2-page PDF is
seconds-to-tens-of-seconds; you can't do it inside the upload request) and to give the draft a
home and a retry handle.

---

## 3. Extraction: vision-first

**Render each page to an image and send the page images to a vision-capable model** (reuse the
exact `pdftoppm`/pdf2image rasterise step already proven).

> This is deliberately **neither PDF text-layer extraction nor a separate OCR step (Tesseract)**.
> A vision model does character reading, layout understanding, and structuring in one pass, and
> works whether or not the PDF has a text layer — so scanned/image-only PDFs (and, next slice,
> photos) all flow through the same path. The PDF text layer, when present, is an *optional*
> grounding aid only (see below), never the mechanism.

Reasons:

- Menu meaning is *visual*. Porto's page has a **glossary sidebar** and **dot-leader rows** that
  jam name + tags + price onto one line; linear text extraction scrambles column order and can
  mistake glossary terms for items. Vision sees "this is a sidebar, not menu items" and reads the
  section structure as laid out.
- **PDF and image sources converge on one pipeline** — rasterise → vision. When we add the image
  source next slice, it's nearly free, because a photo of a menu *is* a page image.
- Send **all pages in one request** so the model keeps section continuity across the page break
  (Porto's `SECONDI` starts on page 2).

**Enhancement (optional):** when the PDF has a clean text layer, also pass the extracted text as
grounding alongside the image, so prices/spellings come from the exact characters rather than
OCR. Not required for the first build.

**Invocation.** Server-side call from FastAPI to a vision model (Claude Sonnet-class: strong
vision + structuring, low cost — a few cents per extraction, at onboarding time, not per view).
Run it in a **background task** so upload returns immediately with `status=processing`; the task
updates the job to `ready`/`error`. In-process background tasks are fine at this volume; a
process restart mid-task leaves a job stuck in `processing` — acceptable for v1, add a
timeout/retry later. API key in env.

---

## 4. Structured output contract

The model returns **JSON only** (no prose, no code fences), shaped to the menu tree:

```json
{
  "menu_name": "Food",
  "sections": [
    {
      "name": "PIZZAS",
      "note": "Gluten free base available at an additional cost of $6.00 per pizza",
      "subsections": [
        {
          "name": null,
          "items": [
            { "name": "MARGHERITA",
              "description": "Tomato, abundance of mozzarella, oregano, cracked pepper",
              "dietary_tags": ["V"],
              "variants": [{ "label": null, "price": "23.00" }],
              "extras": [] }
          ]
        }
      ]
    },
    {
      "name": "INSALATE",
      "note": null,
      "subsections": [
        { "name": null, "items": [
          { "name": "NOSTRA SALAD",
            "description": "Mesculin leaves, cherry tomatoes, cucumber, olives, onions tossed with balsamic glaze",
            "dietary_tags": ["V","VGN","GF"],
            "variants": [{ "label": null, "price": "14.00" }],
            "extras": [{ "label": "Chicken", "price": "6.00" }] }
        ]}
      ]
    }
  ],
  "menu_note": "All prices are GST inclusive. Cakeage $4.00 per person.",
  "ignored": ["glossary sidebar", "allergy disclaimer footer", "contact email"]
}
```

**Prompt rules the contract enforces:**

- **Single price → one variant with `label: null`.** Multiple prices → variants with labels
  (glass/bottle, 6pc/12pc). Porto is single-price throughout.
- **Add-ons → the right home.** Item-level extra ("Chicken extra 6.00" on a salad) →
  `item.extras`. Applies-to-the-whole-section ("GF base +$6 per pizza", "Basic extras 4.00 /
  Meats 6.00") → `section.note`. Whole-menu ("GST inclusive", "Cakeage $4") → `menu_note`.
- **Not every line is an item.** The glossary, allergy disclaimer, contact email, "NO HALF
  PIZZAS" are not menu items. Capture genuine notes where they belong ("NO HALF PIZZAS" → pizza
  section note); list everything deliberately skipped in **`ignored`** so the owner can see
  nothing was silently lost.
- **Preserve wording.** Don't paraphrase descriptions. Keep prices as **strings** as written
  ("16.90") — never floats, never rounded.
- **Don't guess.** Unreadable price or item → `null` + flag, never invented.
- **Dietary tags** map to the canonical set (V/VGN/GF/DF); an unrecognised tag is kept verbatim
  and flagged rather than coerced. Conditional tags ("VGN upon request") stay as text on the
  item, not forced into a clean tag.

Server **validates** the JSON against this schema before storing it; a malformed response →
`status=error` with a retry.

---

## 5. Schema touchpoints

> Exact current column/field names to be confirmed in the build's Phase-0 audit against the live
> models — this section describes the *target* shape, not asserted current state.

- **`Item.extras`** — new. A JSONB list of `{label, price?}`, display-only content (never queried
  individually), rendered as a text line under the item. Same "display-only structured content"
  posture as the content-block body. This is the one piece worth landing now so the extractor has
  somewhere to put add-ons; the ordering-grade modifier system stays out.
- **`Section.note`** — confirm/add. Nullable text for section-level notes ("GF base +$6"). Already
  rendered as a subnote in the print repro, so the render side expects it.
- **`Menu` footnote** — confirm/add. Menu has `description` + `availability_note`; menu-level
  footnotes (GST line, cakeage, allergy disclaimer) need a home — reuse an existing field or add
  `Menu.footnote` (nullable text).
- **`MenuExtraction`** (the job/draft) — new table:
  `id, site_id (FK, indexed), source_type, source_file_key (S3), status
  (processing|ready|error|committed|discarded), result_json (JSONB, nullable),
  target_menu_id (nullable, chosen at review), error (nullable), timestamps`.
  Scoped to site; **IDOR-gated** on `extraction_id` → 404 for a foreign job.

---

## 6. Review & commit — the pivotal decision

We want the owner to fix the inevitable slips (a misread price, a mis-grouped item) before
anything is public, **without** building a second editing surface that duplicates the menu editor.

**Recommended: import into a draft (not-yet-visible) menu, then reuse the existing menu editor.**
On commit, write the JSON into a fresh `Menu` flagged not-public; "review" is just the owner
opening that menu in the **editor they already have** (sections/items/variants CRUD all exist),
fixing what's wrong, and **publishing** to go live. Maximum reuse, the owner edits in the tool
they know, and unreviewed data never hits the public site because the menu isn't visible yet.

**The audit question this hinges on:** do menulike menus already have a per-menu **visibility /
published** flag (does `get_site_by_slug` filter unpublished menus out of the public render)? If
yes, or if it's a cheap add, this is the path. **Surface the `ignored` list and any low-confidence
flags at import time** (a one-screen summary before "open in editor"), since the editor itself
won't show them.

**Fallback, if a visibility flag is a real lift:** a standalone **review form** rendered from the
job JSON; nothing is written to the menu tree until the owner confirms, at which point the tree is
created. Safer (no unreviewed rows in the tree at all) but it duplicates much of the menu editor.

Lean: the reuse path, conditional on the visibility flag existing/being cheap. Settle this first
(§10) because it shapes the whole back half of the build.

**Commit target.** v1 imports into a **new** menu (name from `menu_name`, editable). Porto already
has Dinner/Lunch/Drinks menus — if any is an empty stub, the owner deletes it; **merging/replacing
into a populated menu is deferred** (dedupe + update is its own problem). Guard: warn if the chosen
target is non-empty.

---

## 7. Edge cases & failure modes

- **Multi-page** — all pages in one request; watch section continuity across the break.
- **Sidebars / disclaimers / contact lines** — not items; `ignored` makes the skip visible.
- **Uncertain extraction** — null + flag, surfaced for the owner to fill; never guessed.
- **Failed/empty extraction** — `status=error`, message, retry; re-running spawns a new job.
- **Double-commit** — guard so a job can't be committed twice (`status=committed` terminal).
- **Security/scope** — uploaded PDF → scoped S3 key; job IDOR-gated to site; the image sent to the
  API is the restaurant's own public menu (no sensitive data).
- **Price type** — match the existing variant price type (string/Decimal); preserve as written.

---

## 8. Architecture fit

Standard routes → coordinators → services, scoping off `auth_ctx.scoped_site_id`, IDOR on every
foreign id.

- **Service** `menu_extraction_service` (scoped, flush-only): `create_job`, `run_extraction` (the
  vision call + validate + store JSON; invoked from the background task), `get_draft`,
  `commit_draft` (build the Menu tree), `discard`.
- **Coordinator** `menu_extraction_coordinator` (commit boundaries): job creation; the big
  `commit_draft` transactional write of Menu + Section/Subsection/Item/Variant.
- **Routes** (admin, scoped): `POST upload` (create job + kick off background task);
  `GET status` (HTMX poll while `processing`); `GET review`; `POST commit`; `POST discard`.
- **Migration** — hand-written: `MenuExtraction` table + `Item.extras` (+ `Section.note` /
  `Menu.footnote` if not present).

---

## 9. Deferred (named, not forgotten)

- **Image source** — same vision pipeline; near-free once the PDF path works. Next slice.
- **Paste-text source** — cheapest of all (no OCR/parse): text → model → structure. Good universal
  escape hatch.
- **Web URL source** — messiest (HTML / embedded PDF / JS widget / iframe ordering embed); often
  loops back to a PDF or image anyway. Lowest priority.
- **Multi-menu split** within one source — extractor emits multiple detected blocks each with a
  proposed target; the review screen confirms/remaps. Not needed for Porto.
- **Merge/replace** into a populated menu — dedupe + update semantics.
- **Ordering-grade modifier engine** (grouped, shared, required-vs-optional, cart totals) — that's
  ordering, not a website; foodbooking's lane. Likely permanent out.
- **Confidence-flag UI** — beyond the basic null-flagging, a richer "check this" surface.

---

## 10. Open decisions to settle before the CC prompt

1. **Menu visibility flag** — does it exist / is it cheap? Determines review path (§6). *Most
   important — settle first.*
2. **Extras home** — `Item.extras` as JSONB list of `{label, price?}` — agreed shape? (vs a child
   table — not recommended for display-only content).
3. **Commit target** — new menu only for v1, with a non-empty-target warning — agreed?
4. **Model/provider** — which vision model, and where the API key/config lives.
