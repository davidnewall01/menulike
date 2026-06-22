"""Menu extraction service — PDF → validated structured JSON via Claude vision.

Rasterises a PDF in-memory (PyMuPDF), sends page images to Claude, and
validates the response into ExtractedMenu. No DB, no S3, no side effects.
"""

import base64
import json

import fitz  # PyMuPDF
from anthropic import AsyncAnthropic

from app.core.config import settings
from app.schemas.extraction import ExtractedMenu


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ExtractionNotConfigured(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is not set."""


class ExtractionFailed(RuntimeError):
    """Raised when the model response cannot be parsed/validated.

    Carries the raw model text so the harness can display it for tuning.
    """

    def __init__(self, message: str, raw_text: str):
        super().__init__(message)
        self.raw_text = raw_text


class InvalidPDF(ValueError):
    """Raised for non-PDF, oversized, or too-many-page uploads."""


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

MAX_PDF_SIZE = 20 * 1024 * 1024  # 20 MB
MAX_PAGES = 15
RENDER_DPI = 150
MAX_LONG_EDGE = 1600


def _require_config() -> None:
    if not settings.ANTHROPIC_API_KEY:
        raise ExtractionNotConfigured(
            "Menu extraction is not configured. Set ANTHROPIC_API_KEY."
        )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """\
You are extracting a restaurant menu from page images into structured JSON. Output JSON ONLY — \
no prose, no code fences. Schema:
{ "menu_name": str, "sections": [ { "name": str, "note": str|null, "subsections": [ { "name": \
str|null, "items": [ { "name": str, "description": str|null, "dietary_tags": [str], \
"variants": [ { "label": str|null, "price": str|null } ], "extras": [ { "label": str, "price": \
str|null } ] } ] } ] } ], "menu_note": str|null, "ignored": [str] }

Rules:
- The images are sequential pages of one menu; a section may continue across a page break — \
treat them as one continuous document.
- A single price → one variant with label:null. Multiple prices (e.g. glass/bottle, 6pc/12pc) → \
one variant each, with the label.
- Prices are STRINGS exactly as printed ("16.90"); never invent, round, or convert. If a price \
is unreadable, use null.
- Item-level add-ons ("Chicken extra 6.00") → that item's "extras". Section-wide notes ("Gluten \
free base +$6 per pizza", "Basic extras 4.00 / Meats 6.00", "NO HALF PIZZAS") → that section's \
"note". Whole-menu notes ("All prices GST inclusive", "Cakeage $4") → "menu_note".
- Dietary tags → canonical codes only: V, VGN, GF, DF. An unrecognised or conditional tag (e.g. \
"VGN on request") stays as text in the item description, not in dietary_tags.
- Most subsections are unnamed → name:null (passthrough).
- NOT menu items: glossaries, allergy disclaimers, contact details, addresses. Do not invent \
items for them; list what you deliberately skipped in "ignored".
- Preserve item names and descriptions verbatim; do not paraphrase.
"""


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _rasterise_pdf(pdf_bytes: bytes) -> list[bytes]:
    """Render each page of a PDF to a PNG, capped at MAX_PAGES.

    Returns a list of PNG byte buffers at ~150 DPI, long edge ≤ 1600px.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if doc.page_count > MAX_PAGES:
        doc.close()
        raise InvalidPDF(
            f"PDF has {doc.page_count} pages (max {MAX_PAGES})."
        )

    pages: list[bytes] = []
    for page in doc:
        # Render at target DPI
        mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
        pix = page.get_pixmap(matrix=mat)

        # Scale down if long edge exceeds cap
        long_edge = max(pix.width, pix.height)
        if long_edge > MAX_LONG_EDGE:
            scale = MAX_LONG_EDGE / long_edge
            mat = fitz.Matrix(scale * RENDER_DPI / 72, scale * RENDER_DPI / 72)
            pix = page.get_pixmap(matrix=mat)

        pages.append(pix.tobytes("png"))
    doc.close()
    return pages


async def extract_from_pdf(pdf_bytes: bytes) -> ExtractedMenu:
    """Extract structured menu data from a PDF.

    Raises:
        ExtractionNotConfigured — ANTHROPIC_API_KEY missing.
        InvalidPDF — bad content type, too large, or too many pages.
        ExtractionFailed — model response didn't validate (carries raw text).
    """
    _require_config()

    if len(pdf_bytes) > MAX_PDF_SIZE:
        raise InvalidPDF(
            f"PDF is {len(pdf_bytes) / 1024 / 1024:.1f} MB (max {MAX_PDF_SIZE // 1024 // 1024} MB)."
        )

    # Rasterise
    page_pngs = _rasterise_pdf(pdf_bytes)

    # Build message content: one image block per page + the prompt
    content: list[dict] = []
    for png in page_pngs:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(png).decode(),
            },
        })
    content.append({"type": "text", "text": EXTRACTION_PROMPT})

    # Call Claude
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=settings.MENU_EXTRACTION_MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": content}],
    )

    raw_text = response.content[0].text

    # Strip code fences if present
    text = raw_text.strip()
    if text.startswith("```"):
        # Remove opening fence (possibly ```json)
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3].rstrip()

    # Parse and validate
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ExtractionFailed(
            f"Model returned invalid JSON: {e}", raw_text=raw_text
        )

    try:
        return ExtractedMenu.model_validate(data)
    except Exception as e:
        raise ExtractionFailed(
            f"JSON did not match extraction schema: {e}", raw_text=raw_text
        )
