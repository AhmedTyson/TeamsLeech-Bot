"""Edge-case tests for triage, numbering, captions and checklist views."""

import json

from teamsleech.core.config import settings
from teamsleech.models.domain import Recording, SubjectConfig, UserSession
from teamsleech.services.triage import (
    DUP_SIZE_TOLERANCE,
    FLAG_BROKEN,
    FLAG_DUPLICATE,
    FLAG_SPLIT,
    prepare_session,
    propose_name,
)
from teamsleech.tg_bot.views import build_checklist_text


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


def _subject(short="FT", kind="lecture", next_no=5, doctor="Azza Hegazy", topic_id=None):
    return SubjectConfig(
        name=f"{short} course",
        short=short,
        doctor=doctor,
        keywords=["x"],
        kind=kind,
        next_no=next_no,
        topic_id=topic_id,
    )


# --- duplicate tolerance boundaries -------------------------------------

def test_dup_tolerance_boundary_inclusive():
    # exactly at the tolerance still counts as same lecture
    big = 250.0
    small = big * (1 - DUP_SIZE_TOLERANCE)
    session = UserSession(pending_recordings=[_rec("a.mp4", size_mb=big), _rec("b.mp4", size_mb=small)])
    prepare_session(session, [_subject()])
    assert FLAG_DUPLICATE in session.triage_flags.values()


def test_just_outside_tolerance_is_split():
    big = 250.0
    small = big * (1 - DUP_SIZE_TOLERANCE - 0.01)
    session = UserSession(pending_recordings=[_rec("a.mp4", size_mb=big), _rec("b.mp4", size_mb=small)])
    prepare_session(session, [_subject()])
    assert session.triage_flags[0] == FLAG_SPLIT
    assert session.triage_flags[1] == FLAG_SPLIT


def test_zero_sizes_not_treated_as_duplicates():
    session = UserSession(
        pending_recordings=[
            _rec("a.mp4", size_mb=0.0, duration_ms=4_500_000),
            _rec("b.mp4", size_mb=0.0, duration_ms=4_000_000),
        ]
    )
    prepare_session(session, [_subject()])
    # no usable size info -> cannot prove duplicate, must be flagged as split
    assert session.triage_flags[0] == FLAG_SPLIT
    assert session.triage_flags[1] == FLAG_SPLIT


def test_equal_size_tie_keeps_one_clean():
    session = UserSession(
        pending_recordings=[_rec("a.mp4", size_mb=250.0), _rec("b.mp4", size_mb=250.0)]
    )
    prepare_session(session, [_subject()])
    assert len(session.selected_indices) == 1
    assert sum(1 for f in session.triage_flags.values() if f == FLAG_DUPLICATE) == 1


def test_broken_recording_excluded_from_dup_grouping():
    session = UserSession(
        pending_recordings=[
            _rec("good.mp4", size_mb=250.0),
            _rec("broken.mp4", size_mb=250.0, duration_ms=30_000),
        ]
    )
    prepare_session(session, [_subject()])
    assert session.triage_flags[1] == FLAG_BROKEN
    assert 0 not in session.triage_flags
    assert session.selected_indices == {0}


def test_same_lecture_different_days_not_flagged():
    session = UserSession(
        pending_recordings=[
            _rec("w1.mp4", created="2026-11-02"),
            _rec("w2.mp4", created="2026-11-09"),
        ]
    )
    prepare_session(session, [_subject()])
    assert not session.triage_flags
    assert session.selected_indices == {0, 1}


# --- audio (.m4a lectures are videos for numbering, audio for sending) ---

def test_m4a_audio_lecture_numbered_like_video():
    session = UserSession(pending_recordings=[_rec("lec.m4a")])
    prepare_session(session, [_subject(next_no=7)])
    assert session.rename_overrides[0] == "FT - L07 - Dr. Azza Hegazy"
    assert session.proposed_numbers[0] == 7


def test_short_audio_flagged_broken():
    session = UserSession(pending_recordings=[_rec("clip.m4a", duration_ms=20_000)])
    prepare_session(session, [_subject()])
    assert session.triage_flags[0] == FLAG_BROKEN
    assert not session.selected_indices


# --- numbering edge cases -------------------------------------------------

def test_independent_counters_per_subject():
    session = UserSession(
        pending_recordings=[
            _rec("f1.mp4", subject="FT", created="2026-11-02"),
            _rec("c1.mp4", subject="CN", created="2026-11-02"),
            _rec("f2.mp4", subject="FT", created="2026-11-09"),
            _rec("c2.mp4", subject="CN", created="2026-11-09"),
        ]
    )
    prepare_session(session, [_subject("FT", next_no=5), _subject("CN", kind="section", next_no=2)])
    names = session.rename_overrides
    assert names[0] == "FT - L05 - Dr. Azza Hegazy"
    assert names[1] == "CN - Sec02 - Dr. Azza Hegazy"
    assert names[2] == "FT - L06 - Dr. Azza Hegazy"
    assert names[3] == "CN - Sec03 - Dr. Azza Hegazy"


def test_recording_for_unconfigured_subject_selected_but_unnamed():
    session = UserSession(pending_recordings=[_rec("mystery.mp4", subject="ZZ")])
    prepare_session(session, [_subject("FT")])
    assert 0 in session.selected_indices
    assert 0 not in session.rename_overrides
    assert 0 not in session.proposed_numbers


def test_number_three_digits_not_truncated():
    assert propose_name(_subject(), 104).startswith("FT - L104")


def test_subject_without_short_uses_full_name():
    s = _subject()
    s.short = ""
    assert propose_name(s, 3).startswith("FT course - L03")


def test_same_day_pair_never_numbers_both_silently():
    # Similar sizes: the largest copy is kept, the duplicate is flagged.
    session = UserSession(
        pending_recordings=[
            _rec("early.mp4", time="09:00", size_mb=250.0),
            _rec("later.mp4", time="14:00", size_mb=250.0),
        ]
    )
    prepare_session(session, [_subject(next_no=1)])
    assert list(session.triage_flags.values()) == [FLAG_DUPLICATE]
    assert len(session.selected_indices) == 1

    # Different sizes: a possible split, both held back for the owner.
    session = UserSession(
        pending_recordings=[
            _rec("part1.mp4", time="09:00", size_mb=250.0),
            _rec("part2.mp4", time="14:00", size_mb=100.0),
        ]
    )
    prepare_session(session, [_subject(next_no=1)])
    assert len(session.triage_flags) == 2
    assert not session.selected_indices


def test_prepare_session_is_idempotent():
    session = UserSession(pending_recordings=[_rec("a.mp4"), _rec("b.mp4", duration_ms=10_000)])
    prepare_session(session, [_subject()])
    first = (dict(session.triage_flags), set(session.selected_indices), dict(session.rename_overrides))
    prepare_session(session, [_subject()])
    second = (dict(session.triage_flags), set(session.selected_indices), dict(session.rename_overrides))
    assert first == second


# --- SubjectConfig persistence shape ---------------------------------------

def test_subject_config_roundtrip_keeps_group_fields():
    s = _subject(kind="section", next_no=12, topic_id=-1001234567890)
    data = json.loads(json.dumps({"subjects": [s.model_dump()]}))
    s2 = SubjectConfig(**data["subjects"][0])
    assert s2.topic_id == -1001234567890
    assert s2.kind == "section"
    assert s2.next_no == 12


def test_subject_config_ignores_unknown_legacy_fields():
    s = SubjectConfig(name="X", short="X", keywords=[], mystery_field="old")
    assert s.kind == "lecture"
    assert s.next_no == 1
    assert s.topic_id is None


# --- target group parsing ----------------------------------------------------

def test_target_chat_id_parsing(monkeypatch):
    monkeypatch.setattr(settings, "telegram_target_chat_id", "")
    assert settings.target_chat_id() is None
    monkeypatch.setattr(settings, "telegram_target_chat_id", " -1009876543210 ")
    assert settings.target_chat_id() == -1009876543210
    monkeypatch.setattr(settings, "telegram_target_chat_id", "not-a-number")
    assert settings.target_chat_id() is None


# --- checklist view with flags ------------------------------------------------

def test_checklist_shows_flags_and_note():
    session = UserSession(pending_recordings=[_rec("a.mp4"), _rec("b.mp4", duration_ms=10_000)])
    prepare_session(session, [_subject()])
    text = build_checklist_text(
        session.grouped_recordings, session.scan_label, session.rename_overrides,
        flags=session.triage_flags,
    )
    assert "broken meeting?" in text
    assert "1 item(s) flagged" in text
    assert "Tap their number to include them anyway" in text


def test_checklist_without_flags_has_no_warning():
    session = UserSession(pending_recordings=[_rec("a.mp4")])
    prepare_session(session, [_subject()])
    text = build_checklist_text(
        session.grouped_recordings, session.scan_label, session.rename_overrides,
        flags=session.triage_flags,
    )
    assert "flagged" not in text
