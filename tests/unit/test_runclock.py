"""Tests for the run-age clock."""

from teamsleech.services import runclock


def test_elapsed_and_remaining_are_sane():
    assert runclock.elapsed_minutes() >= 0
    remaining = runclock.remaining_minutes()
    assert 0 <= remaining <= runclock.RUN_LIMIT_MINUTES


def test_remaining_counts_down(monkeypatch):
    monkeypatch.setattr(
        runclock, "STARTED_AT", runclock.time.monotonic() - 600
    )
    assert 9.9 < runclock.elapsed_minutes() < 10.1
    assert 44.9 < runclock.remaining_minutes() < 45.1


def test_remaining_never_negative(monkeypatch):
    monkeypatch.setattr(
        runclock, "STARTED_AT", runclock.time.monotonic() - 99999
    )
    assert runclock.remaining_minutes() == 0.0
