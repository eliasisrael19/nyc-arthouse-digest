from __future__ import annotations

from datetime import date

from src.workflow_guard import find_prior_successful_send_run, jobs_include_successful_step, run_date_in_timezone


def test_run_date_in_timezone_prefers_available_timestamps() -> None:
    run = {
        "id": 1,
        "created_at": "2026-05-04T13:08:04Z",
    }

    assert run_date_in_timezone(run, "America/New_York") == date(2026, 5, 4)


def test_jobs_include_successful_step_counts_only_actual_send_step() -> None:
    jobs_payload = {
        "jobs": [
            {
                "name": "send-digest",
                "steps": [
                    {"name": "Skip if digest already sent today", "conclusion": "success"},
                    {"name": "Send digest", "conclusion": "success"},
                ],
            }
        ]
    }

    assert jobs_include_successful_step(jobs_payload) is True


def test_jobs_include_successful_step_ignores_skipped_send_step() -> None:
    jobs_payload = {
        "jobs": [
            {
                "name": "send-digest",
                "steps": [
                    {"name": "Guard for Monday at or after 9 AM ET", "conclusion": "success"},
                    {"name": "Send digest", "conclusion": "skipped"},
                ],
            }
        ]
    }

    assert jobs_include_successful_step(jobs_payload) is False


def test_find_prior_successful_send_run_ignores_skipped_runs() -> None:
    workflow_runs = [
        {
            "id": 25320796139,
            "event": "schedule",
            "created_at": "2026-05-04T13:08:04Z",
        },
        {
            "id": 25315979790,
            "event": "schedule",
            "created_at": "2026-05-04T11:17:42Z",
        },
    ]
    jobs_by_run_id = {
        "25315979790": {
            "jobs": [
                {
                    "name": "send-digest",
                    "steps": [
                        {"name": "Guard for Monday at or after 9 AM ET", "conclusion": "success"},
                        {"name": "Send digest", "conclusion": "skipped"},
                    ],
                }
            ]
        }
    }

    duplicate = find_prior_successful_send_run(
        workflow_runs,
        current_run_id="25320796139",
        target_date=date(2026, 5, 4),
        timezone_name="America/New_York",
        jobs_by_run_id=jobs_by_run_id,
    )

    assert duplicate is None


def test_find_prior_successful_send_run_returns_actual_sent_run() -> None:
    workflow_runs = [
        {
            "id": 25332446611,
            "event": "schedule",
            "created_at": "2026-05-04T17:11:24Z",
        },
        {
            "id": 25327499348,
            "event": "schedule",
            "created_at": "2026-05-04T15:21:53Z",
        },
    ]
    jobs_by_run_id = {
        "25327499348": {
            "jobs": [
                {
                    "name": "send-digest",
                    "steps": [
                        {"name": "Set recipients for this run", "conclusion": "success"},
                        {"name": "Send digest", "conclusion": "success"},
                    ],
                }
            ]
        }
    }

    duplicate = find_prior_successful_send_run(
        workflow_runs,
        current_run_id="25332446611",
        target_date=date(2026, 5, 4),
        timezone_name="America/New_York",
        jobs_by_run_id=jobs_by_run_id,
    )

    assert duplicate is workflow_runs[1]
