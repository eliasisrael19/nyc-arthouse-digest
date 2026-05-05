from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo


TRACKED_EVENTS = {"schedule", "workflow_dispatch"}
SEND_JOB_NAME = "send-digest"
SEND_STEP_NAME = "Send digest"
RUN_TIMESTAMP_FIELDS = ("run_started_at", "created_at", "updated_at")


def _parse_github_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def run_date_in_timezone(run: Mapping[str, Any], timezone_name: str) -> date | None:
    zone = ZoneInfo(timezone_name)
    for field in RUN_TIMESTAMP_FIELDS:
        parsed = _parse_github_timestamp(run.get(field))
        if parsed:
            return parsed.astimezone(zone).date()
    return None


def jobs_include_successful_step(
    jobs_payload: Mapping[str, Any],
    *,
    job_name: str = SEND_JOB_NAME,
    step_name: str = SEND_STEP_NAME,
) -> bool:
    for job in jobs_payload.get("jobs", []):
        if job.get("name") != job_name:
            continue
        for step in job.get("steps", []):
            if step.get("name") == step_name and step.get("conclusion") == "success":
                return True
    return False


def find_prior_successful_send_run(
    workflow_runs: Iterable[Mapping[str, Any]],
    *,
    current_run_id: str,
    target_date: date,
    timezone_name: str,
    jobs_by_run_id: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    for run in workflow_runs:
        run_id = str(run.get("id"))
        if run_id == current_run_id:
            continue
        if run.get("event") not in TRACKED_EVENTS:
            continue
        if run_date_in_timezone(run, timezone_name) != target_date:
            continue
        jobs_payload = jobs_by_run_id.get(run_id)
        if not jobs_payload:
            continue
        if jobs_include_successful_step(jobs_payload):
            return run
    return None
