"""Unit tests for the opening-hours summariser (pure function, no DB)."""

from datetime import time
from types import SimpleNamespace

from app.content.hours_summary import summarise_hours


def _r(day, open_hm, close_hm, label=None):
    return SimpleNamespace(
        day_of_week=day,
        open_time=time(*open_hm),
        close_time=time(*close_hm),
        label=label,
    )


class TestByService:
    def test_lunch_and_dinner_group_by_period(self):
        # Lunch Thu–Fri 12–2; Dinner Tue–Sat 5–10
        rows = [
            _r(1, (17, 0), (22, 0), "dinner"), _r(2, (17, 0), (22, 0), "dinner"),
            _r(3, (12, 0), (14, 0), "lunch"), _r(3, (17, 0), (22, 0), "dinner"),
            _r(4, (12, 0), (14, 0), "lunch"), _r(4, (17, 0), (22, 0), "dinner"),
            _r(5, (17, 0), (22, 0), "dinner"),
        ]
        assert summarise_hours(rows) == [
            {"heading": "Lunch", "days": "Thu–Fri", "times": ["12:00pm – 2:00pm"]},
            {"heading": "Dinner", "days": "Tue–Sat", "times": ["5:00pm – 10:00pm"]},
        ]

    def test_service_order_is_breakfast_lunch_dinner(self):
        rows = [
            _r(0, (17, 0), (21, 0), "dinner"),
            _r(0, (8, 0), (11, 0), "breakfast"),
            _r(0, (12, 0), (14, 0), "lunch"),
        ]
        assert [row["heading"] for row in summarise_hours(rows)] == ["Breakfast", "Lunch", "Dinner"]

    def test_non_consecutive_days_do_not_collapse(self):
        rows = [
            _r(0, (12, 0), (14, 0), "lunch"),
            _r(2, (12, 0), (14, 0), "lunch"),
            _r(3, (12, 0), (14, 0), "lunch"),
        ]
        assert [row["days"] for row in summarise_hours(rows)] == ["Mon", "Wed–Thu"]

    def test_unlabelled_leftover_renders_last_with_no_heading(self):
        rows = [
            _r(0, (9, 0), (11, 0), "breakfast"),
            _r(5, (10, 0), (15, 0)),
        ]
        result = summarise_hours(rows)
        assert result[0]["heading"] == "Breakfast"
        assert result[-1] == {"heading": None, "days": "Sat", "times": ["10:00am – 3:00pm"]}


class TestByDay:
    def test_collapse_identical_consecutive_days(self):
        rows = [_r(d, (9, 0), (17, 0)) for d in range(6)] + [_r(6, (9, 0), (12, 0))]
        assert summarise_hours(rows) == [
            {"heading": None, "days": "Mon–Sat", "times": ["9:00am – 5:00pm"]},
            {"heading": None, "days": "Sun", "times": ["9:00am – 12:00pm"]},
        ]

    def test_split_shift_keeps_both_ranges(self):
        rows = []
        for d in range(5):
            rows += [_r(d, (12, 0), (14, 0)), _r(d, (17, 0), (22, 0))]
        assert summarise_hours(rows) == [
            {"heading": None, "days": "Mon–Fri",
             "times": ["12:00pm – 2:00pm", "5:00pm – 10:00pm"]},
        ]

    def test_closed_days_are_omitted(self):
        rows = [_r(0, (9, 0), (17, 0)), _r(2, (9, 0), (17, 0))]
        days = [row["days"] for row in summarise_hours(rows)]
        assert days == ["Mon", "Wed"]  # Tue (closed) not present


def test_empty_returns_empty():
    assert summarise_hours([]) == []
