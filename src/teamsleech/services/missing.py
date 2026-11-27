"""Unpublished-recordings selection for the scan-missing run.

A Bot API bot cannot read the group's history, so the record of what is
already published lives in each subject's `next_no` (seeded/corrected with
/setno). Heuristic: order a subject's recordings oldest-first and treat the
first (next_no - 1) as already posted; everything after that is queued for
review, oldest first. The owner sanity-checks the first queued item per
subject in the normal review step before anything is published.
"""

from teamsleech.models.domain import Recording


def unpublished_in_order(
    recs: list[Recording], next_no: int | None
) -> list[Recording]:
    """Recordings after the already-published prefix, oldest first."""
    ordered = sorted(recs, key=lambda r: (r.created or "", r.name))
    skip = max(0, (next_no or 1) - 1)
    return ordered[skip:]
