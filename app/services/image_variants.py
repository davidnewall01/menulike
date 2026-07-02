"""Image variant generation — resize + WebP encode via Pillow.

Pure image processing with no S3 or DB concerns.  Takes source bytes,
returns a dict of variant name → (webp_bytes, width, height).

Variant tiers:
  original_webp  — source re-encoded to WebP, long edge capped at 2560px
  large          — max width 1600px
  medium         — max width 800px
  thumb          — max width 400px

Rules:
  - Never upscale.  If the source is narrower than a tier's target width,
    that tier is generated at the source's own width (cap-to-source).
  - Aspect ratio always preserved (width-constrained resize).
  - EXIF/metadata stripped on output.
  - Non-RGB inputs (CMYK, palette, RGBA) converted to RGB before WebP save.
"""

import io
from dataclasses import dataclass

from PIL import Image

WEBP_QUALITY = 82

VARIANT_SPECS: list[tuple[str, int]] = [
    ("original_webp", 2560),
    ("large", 1600),
    ("medium", 800),
    ("thumb", 400),
]


@dataclass(frozen=True, slots=True)
class Variant:
    name: str
    data: bytes
    width: int
    height: int


def _to_rgb(img: Image.Image) -> Image.Image:
    """Convert any mode (CMYK, P, LA, RGBA, etc.) to RGB for WebP output."""
    if img.mode == "RGB":
        return img
    if img.mode in ("RGBA", "LA", "PA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        # Use alpha channel to composite onto white
        background.paste(img, mask=img.split()[-1])
        return background
    return img.convert("RGB")


def generate_variants(source_data: bytes) -> list[Variant]:
    """Generate all WebP variants from raw upload bytes.

    Returns a list of Variant objects (always 4 — one per tier).
    Raises on truly corrupt/unreadable images (let caller handle).
    """
    img = Image.open(io.BytesIO(source_data))
    # Honour EXIF orientation before any processing
    img = _apply_exif_orientation(img)
    img = _to_rgb(img)
    src_w, src_h = img.size

    # Step 1: produce original_webp (long-edge capped at 2560)
    orig_target_w = _cap_long_edge(src_w, src_h, 2560)
    orig_img = _resize(img, orig_target_w) if orig_target_w < src_w else img
    orig_data = _encode_webp(orig_img)
    variants: list[Variant] = [
        Variant("original_webp", orig_data, orig_img.size[0], orig_img.size[1])
    ]

    # Step 2: derive smaller tiers FROM orig_img (so nothing exceeds it)
    base_w = orig_img.size[0]
    for name, max_width in VARIANT_SPECS:
        if name == "original_webp":
            continue
        target_w = min(max_width, base_w)
        resized = _resize(orig_img, target_w) if target_w < base_w else orig_img
        data = _encode_webp(resized)
        variants.append(Variant(name, data, resized.size[0], resized.size[1]))

    return variants


def _cap_long_edge(w: int, h: int, max_edge: int) -> int:
    """Return the target width that keeps the long edge ≤ max_edge."""
    if max(w, h) <= max_edge:
        return w  # no resize needed, return original width
    if w >= h:
        # Width is the long edge
        return max_edge
    # Height is the long edge — scale width proportionally
    return int(w * max_edge / h)


def _resize(img: Image.Image, target_w: int) -> Image.Image:
    """Width-constrained resize preserving aspect ratio."""
    w, h = img.size
    ratio = target_w / w
    target_h = int(h * ratio)
    return img.resize((target_w, target_h), Image.LANCZOS)


def _encode_webp(img: Image.Image) -> bytes:
    """Encode to WebP with quality setting and no metadata."""
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=4)
    return buf.getvalue()


def _apply_exif_orientation(img: Image.Image) -> Image.Image:
    """Rotate/flip based on EXIF orientation tag, then strip EXIF."""
    try:
        from PIL import ExifTags
        exif = img.getexif()
        orientation_key = next(
            k for k, v in ExifTags.TAGS.items() if v == "Orientation"
        )
        orientation = exif.get(orientation_key)
        if orientation == 2:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        elif orientation == 3:
            img = img.transpose(Image.ROTATE_180)
        elif orientation == 4:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        elif orientation == 5:
            img = img.transpose(Image.ROTATE_270).transpose(Image.FLIP_LEFT_RIGHT)
        elif orientation == 6:
            img = img.transpose(Image.ROTATE_270)
        elif orientation == 7:
            img = img.transpose(Image.ROTATE_90).transpose(Image.FLIP_LEFT_RIGHT)
        elif orientation == 8:
            img = img.transpose(Image.ROTATE_90)
    except (StopIteration, AttributeError, KeyError):
        pass
    return img
