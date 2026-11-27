"""Tests for the review-queue triage service."""

from teamsleech.models.domain import Recording, SubjectConfig, UserSession
from teamsleech.services.triage import (
    FLAG_BROKEN,
    FLAG_DUPLICATE,
    FLAG_SPLIT,
    prepare_session,
    propose_name,
)


def _rec(
    name,
    subject="FT",
    created="2026-11-09",
    time="10:00",
    size_mb=250.0,
    duration_ms=4_500_000,
    is_video=True,
):
    return Recording(
        name=name,
        size_mb=size_mb,
        created=created,
        time=time,
        duration_ms=duration_ms,
        drive_id="d",
        item_id=name,
        team_name=f"{subject} team",
        subject_name=subject,
        is_video=is_video,
    )


def _subject(short="FT", kind="lecture", next_no=5, doctor="Azza Hegazy"):
    return SubjectConfig(
        name=f"{short} course",
        short=short,
        doctor=doctor,
        keywords=["x"],
        kind=kind,
        next_no=next_no,
    )


def test_propose_name_lecture():
    assert propose_name(_subject(), 5) == "FT - L05 - Dr. Azza Hegazy"


def test_propose_name_section():
    assert (
        propose_name(_subject(short="CN", kind="section", doctor="Fady Alaa"), 3)
        == "CN - Sec03 - Dr. Fady Alaa"
    )


def test_propose_name_no_doctor():
    assert propose_name(_subject(doctor=""), 7) == "FT - L07"


def test_broken_short_video_flagged_and_not_selected():
    session = UserSession(
        pending_recordings=[
            _rec("good.mp4"),
            _rec("oops.mp4", duration_ms=40_000),
        ]
    )
    prepare_session(session, [_subject()])
    assert session.triage_flags[1] == FLAG_BROKEN
    assert 0 in session.selected_indices
    assert 1 not in session.selected_indices


def test_tiny_video_without_duration_flagged():
    session = UserSession(pending_recordings=[_rec("tiny.mp4", size_mb=3.0, duration_ms=0)])
    prepare_session(session, [_subject()])
    assert session.triage_flags[0] == FLAG_BROKEN


def test_duplicates_flagged_keeping_largest():
    session = UserSession(
        pending_recordings=[
            _rec("a.mp4", size_mb=250.0),
            _rec("b.mp4", size_mb=255.0),
            _rec("c.mp4", size_mb=248.0),
        ]
    )
    prepare_session(session, [_subject()])
    assert session.triage_flags.get(0) == FLAG_DUPLICATE
    assert session.triage_flags.get(2) == FLAG_DUPLICATE
    assert 1 not in session.triage_flags  # largest kept clean
    assert session.selected_indices == {1}


def test_split_parts_flagged_when_sizes_differ():
    session = UserSession(
        pending_recordings=[
            _rec("part1.mp4", time="10:00", size_mb=250.0),
            _rec("part2.mp4", time="11:20", size_mb=120.0),
        ]
    )
    prepare_session(session, [_subject()])
    assert session.triage_flags[0] == FLAG_SPLIT
    assert session.triage_flags[1] == FLAG_SPLIT


def test_same_day_different_subjects_not_duplicates():
    session = UserSession(
        pending_recordings=[
            _rec("a.mp4", subject="FT", size_mb=250.0),
            _rec("b.mp4", subject="CN", size_mb=250.0),
        ]
    )
    prepare_session(session, [_subject("FT"), _subject("CN")])
    assert not session.triage_flags
    assert session.selected_indices == {0, 1}


def test_numbering_oldest_first_from_next_no():
    session = UserSession(
        pending_recordings=[
            _rec("new.mp4", created="2026-11-09"),
            _rec("old.mp4", created="2026-11-02"),
        ]
    )
    prepare_session(session, [_subject(next_no=5)])
    assert session.rename_overrides[1] == "FT - L05 - Dr. Azza Hegazy"
    assert session.rename_overrides[0] == "FT - L06 - Dr. Azza Hegazy"
    assert session.proposed_numbers[1] == 5
    assert session.proposed_numbers[0] == 6


def test_section_kind_uses_sec_prefix():
    session = UserSession(pending_recordings=[_rec("s.mp4")])
    prepare_session(session, [_subject(kind="section", next_no=3)])
    assert session.rename_overrides[0].startswith("FT - Sec03")


def test_documents_selected_but_not_renamed():
    session = UserSession(
        pending_recordings=[
            _rec("slides.pdf", is_video=False, duration_ms=0, size_mb=2.0),
        ]
    )
    prepare_session(session, [_subject()])
    assert 0 in session.selected_indices
    assert 0 not in session.rename_overrides


def test_offline_week_gap_does_not_shift_numbering():
    # Two lectures one week, then a gap, then one more: numbers just continue.
    subjects = [_subject(next_no=8)]
    session = UserSession(pending_recordings=[_rec("w1.mp4", created="2026-10-19")])
    prepare_session(session, subjects)
    assert session.proposed_numbers[0] == 8
