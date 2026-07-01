"""Derive a grouped/summarised view of opening hours from per-day rows.

Pure presentation logic — no DB, no I/O. Given a location's ``regular_hours``
rows (each with ``day_of_week`` 0=Mon..6=Sun, ``open_time``, ``close_time`` and
an optional service ``label``), produce an ordered list of summary rows that
collapse consecutive days and, when service-period labels are used, group by
service:

    Lunch  — Thu–Fri  12:00pm – 2:00pm
    Dinner — Tue–Sat  5:00pm – 10:00pm

This is a *lesser presentation that degrades from* the structured per-day hours
(design doc: "model at the most permissive shape; lesser presentations degrade
from it"). It never becomes a source of truth — closed days are simply omitted,
nothing is invented.

Each returned row is a dict: ``{"heading": str | None, "days": str,
"times": list[str]}``.
"""

from __future__ import annotations

from datetime import time
from typing import Any

_SHORT_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# Service-period display order (unknown/None labels sort last).
_LABEL_ORDER = ["breakfast", "lunch", "dinner"]


def _fmt_time(t: time) -> str:
    """3:30pm / 9:00am — matches the detailed hours formatting."""
    return t.strftime("%I:%M%p").lower().lstrip("0")


def _fmt_range(open_t: time, close_t: time) -> str:
    return f"{_fmt_time(open_t)} – {_fmt_time(close_t)}"


def _day_label(start: int, end: int) -> str:
    return _SHORT_DAYS[start] if start == end else f"{_SHORT_DAYS[start]}–{_SHORT_DAYS[end]}"


def _day_runs(days: list[int]) -> list[tuple[int, int]]:
    """Split day indices into (start, end) runs of *consecutive* days."""
    runs: list[tuple[int, int]] = []
    days = sorted(set(days))
    i = 0
    while i < len(days):
        start = end = days[i]
        while i + 1 < len(days) and days[i + 1] == end + 1:
            i += 1
            end = days[i]
        runs.append((start, end))
        i += 1
    return runs


def summarise_hours(rows: Any) -> list[dict]:
    """Ordered summary rows collapsing consecutive days.

    Groups by service period when any row is labelled, otherwise by day.
    """
    rows = list(rows)
    if not rows:
        return []
    if any(getattr(r, "label", None) for r in rows):
        return _summarise_by_service(rows)
    return _summarise_by_day(rows)


def _summarise_by_service(rows: list) -> list[dict]:
    """One group per service label (ordered breakfast→lunch→dinner), then any
    unlabelled ranges last with no heading. Within a group, identical times
    collapse across consecutive days."""
    buckets: dict[str, list] = {}
    for r in rows:
        buckets.setdefault(r.label or "", []).append(r)

    ordered = [k for k in _LABEL_ORDER if k in buckets]
    ordered += [k for k in buckets if k and k not in _LABEL_ORDER]
    if "" in buckets:
        ordered.append("")

    out: list[dict] = []
    for key in ordered:
        heading = key.capitalize() if key else None
        by_time: dict[tuple[time, time], list[int]] = {}
        for r in buckets[key]:
            by_time.setdefault((r.open_time, r.close_time), []).append(r.day_of_week)
        for (open_t, close_t) in sorted(by_time):
            for start, end in _day_runs(by_time[(open_t, close_t)]):
                out.append({
                    "heading": heading,
                    "days": _day_label(start, end),
                    "times": [_fmt_range(open_t, close_t)],
                })
    return out


def _summarise_by_day(rows: list) -> list[dict]:
    """Collapse consecutive days that share an identical set of time ranges."""
    by_day: dict[int, list[tuple[time, time]]] = {}
    for r in rows:
        by_day.setdefault(r.day_of_week, []).append((r.open_time, r.close_time))
    # signature = sorted tuple of ranges for that day
    seq = [(d, tuple(sorted(by_day[d]))) for d in sorted(by_day)]

    out: list[dict] = []
    i = 0
    while i < len(seq):
        start_day, sig = seq[i]
        end_day = start_day
        while i + 1 < len(seq) and seq[i + 1][0] == end_day + 1 and seq[i + 1][1] == sig:
            i += 1
            end_day = seq[i][0]
        out.append({
            "heading": None,
            "days": _day_label(start_day, end_day),
            "times": [_fmt_range(o, c) for (o, c) in sig],
        })
        i += 1
    return out
