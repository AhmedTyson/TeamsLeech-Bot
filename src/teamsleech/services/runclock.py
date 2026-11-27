"""Run-age clock for the current GitHub Actions run.

bot-runner.yml kills the job at timeout-minutes (55). This clock lets the
bot report how much time is left and start its own continuation run before
the cap hits, so the owner never sees a silent cutoff.
"""

import time

STARTED_AT = time.monotonic()
RUN_LIMIT_MINUTES = 55
CONTINUATION_LEAD_MINUTES = 5


def elapsed_minutes() -> float:
    return (time.monotonic() - STARTED_AT) / 60.0


def remaining_minutes() -> float:
    return max(0.0, RUN_LIMIT_MINUTES - elapsed_minutes())
