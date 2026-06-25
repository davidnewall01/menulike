"""Smart text case transforms for menu content.

Designed for restaurant menu text where abbreviations (GF, NV, NSW, IPA)
and joining words (and, or, with) need special handling.
"""

import re

# Words that stay lowercase in title case (unless first word)
_TITLE_JOINERS = frozenset({
    "a", "an", "and", "as", "at", "but", "by", "for", "in", "of",
    "on", "or", "the", "to", "with", "via", "vs",
})

# Known abbreviations — always preserved regardless of context
_KNOWN_ABBREVS = frozenset({
    "gf", "df", "vg", "vn", "nf", "v",  # dietary
    "nv", "nz", "nsw", "wa", "sa", "qld", "vic", "tas", "nt", "act",  # regions
    "ipa", "ibu", "abv",  # beer
    "fr", "it", "us", "uk",  # countries
})

# Short all-caps words: only preserve when text is NOT all-caps
_MIN_ABBREV_LEN = 2
_MAX_ABBREV_LEN = 3


def _is_all_upper(text: str) -> bool:
    """Check if the entire text is uppercase (ignoring non-alpha chars)."""
    alpha = re.sub(r"[^A-Za-z]", "", text)
    return bool(alpha) and alpha.isupper()


def _is_likely_abbreviation(word: str, text_is_all_upper: bool) -> bool:
    """Determine if a word should be preserved as an abbreviation.

    If the whole text is ALL CAPS, we can't distinguish abbreviations from
    regular words by case alone — only known abbreviations are preserved.
    If the text is mixed case, short ALL-CAPS words are also preserved.
    """
    stripped = re.sub(r"[^A-Za-z]", "", word)
    if not stripped:
        return False

    lower = stripped.lower()

    # Known abbreviations: always preserve
    if lower in _KNOWN_ABBREVS:
        return True

    # In all-caps text, we can't infer from case — only known abbrevs
    if text_is_all_upper:
        return False

    # In mixed-case text, short ALL-CAPS words are likely abbreviations
    return (
        _MIN_ABBREV_LEN <= len(stripped) <= _MAX_ABBREV_LEN
        and stripped.isupper()
        and stripped.isalpha()
    )


def _capitalise_word(word: str) -> str:
    """Capitalise first alpha char, lowercase the rest."""
    j = 0
    while j < len(word) and not word[j].isalpha():
        j += 1
    if j < len(word):
        return word[:j] + word[j].upper() + word[j + 1:].lower()
    return word


def smart_title_case(text: str) -> str:
    """Title Case with smart handling of abbreviations and joiners."""
    if not text:
        return text

    all_upper = _is_all_upper(text)
    words = text.split()
    result = []

    for i, word in enumerate(words):
        if _is_likely_abbreviation(word, all_upper):
            result.append(word.upper())
        elif i > 0 and word.lower() in _TITLE_JOINERS:
            result.append(word.lower())
        else:
            result.append(_capitalise_word(word))

    return " ".join(result)


def smart_sentence_case(text: str) -> str:
    """Sentence case with abbreviation preservation."""
    if not text:
        return text

    all_upper = _is_all_upper(text)
    words = text.split()
    result = []

    for i, word in enumerate(words):
        if _is_likely_abbreviation(word, all_upper):
            result.append(word.upper())
        elif i == 0:
            result.append(_capitalise_word(word))
        else:
            result.append(word.lower())

    return " ".join(result)


def to_upper(text: str) -> str:
    """Simple uppercase."""
    return text.upper() if text else text


def to_lower(text: str) -> str:
    """Simple lowercase."""
    return text.lower() if text else text


# Map of mode names to transform functions
TRANSFORMS = {
    "none": lambda t: t,
    "title": smart_title_case,
    "sentence": smart_sentence_case,
    "upper": to_upper,
    "lower": to_lower,
}

# Display labels for the UI
TRANSFORM_LABELS = {
    "none": "No change",
    "title": "Title Case",
    "sentence": "Sentence case",
    "upper": "UPPER CASE",
    "lower": "lower case",
}
