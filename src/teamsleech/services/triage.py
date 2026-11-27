"""Review-queue triage: propose names/numbers, flag messy recordings.

Nothing here publishes or uploads. It pre-fills the checklist session with
proposed names (still editable through the existing rename flow), selects
only the clean items, and tags the rest for the owner's decision:

- broken meetings (accidental sub-minute recordings)
- duplicates (same doctor/subject, same day, similar size, e.g. several
  teams holding the same lecture)
- possible splits (same day, several parts with different sizes)

Numbering comes from each subject's stored ``next_no`` counter, never from
week counts, so offline weeks and catch-up scans cannot shift it.
"""

import logging
from collections import defaultdict

from teamsleech.models.domain import Recording, SubjectConfig, UserSession
from teamsleech.services.scanner import subject_key

log = logging.getLogger("triage")

BROKEN_MAX_DURATION_MS = 90_000  # < 1.5 min video = broken meeting, not a lecture
SMALL_VIDEO_MB = 15.0  # tiny file with no duration metadata
DUP_SIZE_TOLERANCE = 0.15  # two recordings within 15% size = same lecture

FLAG_BROKEN = "broken meeting? (<1.5 min)"
FLAG_DUPLICATE = "duplicate? (same day, similar size)"
FLAG_SPLIT = "possible split (multiple parts, same day)"


def number_prefix(subject: SubjectConfig) -> str:
    return "Sec" if subject.kind == "section" else "L"


def propose_name(subject: SubjectConfig, number: int) -> str:
    short = subject.short or subject.name
    base = f"{short} - {number_prefix(subject)}{number:02d}"
    if subject.doctor:
        base += f" - Dr. {subject.doctor}"
    return base


def _similar_size(a: Recording, b: Recording) -> bool:
    if a.size_mb <= 0 or b.size_mb <= 0:
        return False
    return abs(a.size_mb - b.size_mb) / max(a.size_mb, b.size_mb) <= DUP_SIZE_TOLERANCE


def prepare_session(session: UserSession, subjects: list[SubjectConfig]) -> None:
    """Fill selection, name proposals and triage flags for pending recordings."""
    subj_map = {subject_key(s): s for s in subjects}
    session.selected_indices.clear()
    session.rename_overrides.clear()
    session.triage_flags.clear()
    session.proposed_numbers.clear()

    # --- flag broken/tiny recordings -------------------------------------
    for i, rec in enumerate(session.pending_recordings):
        if not rec.is_video:
            continue
        if rec.duration_ms and rec.duration_ms < BROKEN_MAX_DURATION_MS:
            session.triage_flags[i] = FLAG_BROKEN
        elif not rec.duration_ms and rec.size_mb < SMALL_VIDEO_MB:
            session.triage_flags[i] = FLAG_BROKEN

    # --- duplicates and possible splits, per subject+day ------------------
    by_day: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, rec in enumerate(session.pending_recordings):
        if rec.is_video and i not in session.triage_flags:
            by_day[(rec.subject_name, rec.created)].append(i)
    for indices in by_day.values():
        if len(indices) < 2:
            continue
        recs = [session.pending_recordings[i] for i in indices]
        if all(_similar_size(recs[0], r) for r in recs[1:]):
            keep = max(indices, key=lambda i: session.pending_recordings[i].size_mb)
            for i in indices:
                if i != keep:
                    session.triage_flags[i] = FLAG_DUPLICATE
        else:
            for i in indices:
                session.triage_flags[i] = FLAG_SPLIT

    # --- select clean items, number videos oldest-first -------------------
    clean = [i for i in range(len(session.pending_recordings)) if i not in session.triage_flags]
    clean.sort(
        key=lambda i: (
            session.pending_recordings[i].created,
            session.pending_recordings[i].time,
        )
    )
    counters: dict[str, int] = {}
    for i in clean:
        rec = session.pending_recordings[i]
        session.selected_indices.add(i)
        if not rec.is_video:
            continue  # documents keep their original name unless edited
        subj = subj_map.get(rec.subject_name)
        if not subj:
            continue
        n = counters.get(rec.subject_name, subj.next_no)
        session.rename_overrides[i] = propose_name(subj, n)
        session.proposed_numbers[i] = n
        counters[rec.subject_name] = n + 1
