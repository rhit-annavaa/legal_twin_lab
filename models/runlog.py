import json
import os
from datetime import datetime, timezone

import config


def persist_run(run_id: str, record: dict) -> str:
    """Write a full run record (inputs + transcript + outcome) to runs/<run_id>.json so a
    simulated proceeding can be reopened, diffed against another run, or included in a batch
    variance report later. Returns the path written.

    Note on reproducibility: the Anthropic Messages API has no seed parameter, so run_id is a
    label for cross-referencing a run's transcript/outcome later, not a mechanism that makes the
    run reproducible. Two runs with identical inputs can still produce different transcripts and
    outcomes — that's expected model variance, not a bug. If you need to gauge that variance, use
    /api/session/batch to run the same configuration N times and see the spread rather than
    trusting any single run as "the" answer.
    """
    record = dict(record)
    record.setdefault("run_id", run_id)
    record.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
    path = os.path.join(config.RUNS_DIR, f"{run_id}.json")
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    return path
