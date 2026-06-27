"""Sample content for the fallback-not-stored model.

These constants provide placeholder content shown to owners in preview mode
when they haven't yet provided their own real content for a given area.
Sample content is NEVER written to tenant data — it exists only here.

Note: visit fields (address, hours, contact) are deliberately NOT sampled.
Fake-but-plausible factual data (hours, phone numbers) could mislead owners
into believing it's real. Those fields show empty-but-prompting in preview.
"""

# --- Home ---

TAGLINE = "Fresh Mediterranean flavours, harbourside"

# --- Our Story ---

OUR_STORY_HEADING = "Our Story"
OUR_STORY_BODY = (
    "Every dish we serve tells a story of sun-ripened produce, "
    "time-honoured recipes, and the Mediterranean coast.\n\n"
    "We opened our doors with a simple belief: that great food "
    "starts with great ingredients, prepared with care and shared "
    "with warmth."
)

# --- Sample image URLs (static assets under app/static/samples/) ---
# These are visibly-placeholder images (solid colour + "SAMPLE" text baked
# into the image itself), NOT stock photos. No additional overlay needed —
# the baked-in text is the watermark.

HERO_IMAGE_URL = "/static/samples/hero.jpg"
LOGO_IMAGE_URL = "/static/samples/logo.png"
GALLERY_IMAGE_URLS = [
    "/static/samples/gallery_1.jpg",
    "/static/samples/gallery_2.jpg",
    "/static/samples/gallery_3.jpg",
]

# --- Events ---

EVENT_UPCOMING_1_HEADING = "Chef's Table Friday"
EVENT_UPCOMING_1_BODY = (
    "An intimate five-course dinner with wine pairings, "
    "hosted by our head chef."
)
EVENT_UPCOMING_2_HEADING = "Live Jazz Saturday"
EVENT_UPCOMING_2_BODY = (
    "Enjoy live jazz from 7 pm while you dine. No cover charge."
)
EVENT_SPECIAL_1_HEADING = "Happy Hour"
EVENT_SPECIAL_1_BODY = "Half-price house wines and cocktails, every weekday 4\u20136 pm."
EVENT_SPECIAL_2_HEADING = "Sunday Long Lunch"
EVENT_SPECIAL_2_BODY = "Three courses for $55 pp — a lazy afternoon with family and friends."


def event_sample_date(days_ahead: int):
    """Return a sample date N days in the future (always upcoming in preview)."""
    from datetime import date, timedelta
    return date.today() + timedelta(days=max(days_ahead, 1))
