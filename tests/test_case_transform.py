"""Tests for smart case transforms."""

from app.utils.case_transform import smart_title_case, smart_sentence_case, to_upper, to_lower


class TestSmartTitleCase:
    def test_basic(self):
        assert smart_title_case("ESPRESSO MARTINI") == "Espresso Martini"

    def test_preserves_known_abbreviations_in_all_caps(self):
        # GF is a known abbreviation — preserved even in all-caps text
        assert smart_title_case("PORK CHICKEN OR VEGAN GF") == "Pork Chicken or Vegan GF"

    def test_preserves_region_abbreviations(self):
        assert smart_title_case("HUNTER VALLEY NSW") == "Hunter Valley NSW"

    def test_preserves_abbreviations_in_mixed_case(self):
        # In mixed-case text, short ALL-CAPS words are preserved
        assert smart_title_case("Pale Ale IPA") == "Pale Ale IPA"

    def test_does_not_treat_regular_short_words_as_abbrev_in_all_caps(self):
        # "IN" and "OF" should NOT be preserved as abbreviations in all-caps text
        assert smart_title_case("SALT AND PEPPER IN A BOWL") == "Salt and Pepper in a Bowl"

    def test_joiners_lowercase(self):
        assert smart_title_case("PETAL & STEM SAUVIGNON BLANC") == "Petal & Stem Sauvignon Blanc"
        assert smart_title_case("SALT AND PEPPER SQUID") == "Salt and Pepper Squid"

    def test_first_word_always_capitalised(self):
        assert smart_title_case("THE CLASSIC BURGER") == "The Classic Burger"
        assert smart_title_case("A SIMPLE SALAD") == "A Simple Salad"

    def test_empty_and_none(self):
        assert smart_title_case("") == ""
        assert smart_title_case(None) is None

    def test_already_mixed_case(self):
        assert smart_title_case("Espresso Martini") == "Espresso Martini"

    def test_single_word(self):
        assert smart_title_case("COCKTAILS") == "Cocktails"

    def test_with_numbers(self):
        assert smart_title_case("TULLOCH VERDELHO 2025") == "Tulloch Verdelho 2025"

    def test_ampersand(self):
        assert smart_title_case("PRAWN & CHIVES") == "Prawn & Chives"

    def test_dietary_at_end(self):
        assert smart_title_case("CHICKEN SCHNITZEL GF DF") == "Chicken Schnitzel GF DF"


class TestSmartSentenceCase:
    def test_basic(self):
        assert smart_sentence_case("SLOW ROASTED PEKING DUCK") == "Slow roasted peking duck"

    def test_preserves_known_abbreviations(self):
        assert smart_sentence_case("POACHED IN RICE WINE GF") == "Poached in rice wine GF"

    def test_preserves_region_abbreviations(self):
        assert smart_sentence_case("HUNTER VALLEY NSW AUSTRALIA") == "Hunter valley NSW australia"

    def test_empty(self):
        assert smart_sentence_case("") == ""
        assert smart_sentence_case(None) is None

    def test_single_word(self):
        assert smart_sentence_case("DESCRIPTION") == "Description"


class TestSimpleTransforms:
    def test_upper(self):
        assert to_upper("hello world") == "HELLO WORLD"

    def test_lower(self):
        assert to_lower("HELLO WORLD") == "hello world"

    def test_empty(self):
        assert to_upper("") == ""
        assert to_lower("") == ""
        assert to_upper(None) is None
        assert to_lower(None) is None
