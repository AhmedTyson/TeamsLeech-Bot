"""Tests for unpublished-in-order selection."""

from teamsleech.models.domain import Recording
from teamsleech.services.missing import unpublished_in_order


def rec(name, created):
    return Recording(
        name=name, size_mb=1.0, created=created,
        drive_id="d", item_id=name, team_name="t", subject_name="s",
    )


def test_skips_published_prefix_oldest_first():
    recs = [
        rec("c.mp4", "2026-03-03"),
        rec("a.mp4", "2026-01-01"),
        rec("b.mp4", "2026-02-02"),
        rec("d.mp4", "2026-04-04"),
    ]
    kept = unpublished_in_order(recs, next_no=3)
    assert [r.name for r in kept] == ["c.mp4", "d.mp4"]


def test_next_no_one_keeps_everything_in_order():
    recs = [rec("b.mp4", "2026-02-02"), rec("a.mp4", "2026-01-01")]
    kept = unpublished_in_order(recs, next_no=1)
    assert [r.name for r in kept] == ["a.mp4", "b.mp4"]


def test_next_no_beyond_count_empties():
    recs = [rec("a.mp4", "2026-01-01")]
    assert unpublished_in_order(recs, next_no=5) == []


def test_none_next_no_defaults_to_one():
    recs = [rec("a.mp4", "2026-01-01")]
    assert [r.name for r in unpublished_in_order(recs, None)] == ["a.mp4"]


def test_empty_input():
    assert unpublished_in_order([], 3) == []


def test_ties_break_by_name():
    recs = [rec("b.mp4", "2026-01-01"), rec("a.mp4", "2026-01-01")]
    kept = unpublished_in_order(recs, next_no=1)
    assert [r.name for r in kept] == ["a.mp4", "b.mp4"]
