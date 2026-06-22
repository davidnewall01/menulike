"""Unit tests for parse_extras normalisation (getlist -> zip -> strip-blank-label)."""

from app.schemas.menu import parse_extras


class TestParseExtras:
    def test_basic_pair(self):
        result = parse_extras(["Side salad"], ["5.00"])
        assert result == [{"label": "Side salad", "price": "5.00"}]

    def test_multiple_pairs(self):
        result = parse_extras(
            ["Side salad", "Extra cheese"],
            ["5.00", "2.50"],
        )
        assert result == [
            {"label": "Side salad", "price": "5.00"},
            {"label": "Extra cheese", "price": "2.50"},
        ]

    def test_blank_label_dropped(self):
        """Rows with blank labels are dropped entirely."""
        result = parse_extras(["", "Extra cheese", "  "], ["5.00", "2.50", "1.00"])
        assert result == [{"label": "Extra cheese", "price": "2.50"}]

    def test_blank_price_kept(self):
        """Label-only extras (price blank) are kept — e.g. 'Seasonal'."""
        result = parse_extras(["Seasonal", "GF available"], ["", ""])
        assert result == [
            {"label": "Seasonal", "price": None},
            {"label": "GF available", "price": None},
        ]

    def test_whitespace_stripped(self):
        result = parse_extras(["  Side salad  "], ["  5.00  "])
        assert result == [{"label": "Side salad", "price": "5.00"}]

    def test_empty_lists(self):
        result = parse_extras([], [])
        assert result == []

    def test_mixed_blank_and_valid(self):
        result = parse_extras(
            ["", "Bread basket", "  ", "Seasonal"],
            ["0.00", "3.50", "1.00", ""],
        )
        assert result == [
            {"label": "Bread basket", "price": "3.50"},
            {"label": "Seasonal", "price": None},
        ]
