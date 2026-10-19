"""End-to-end: prompt -> import -> approve -> activate -> dispatch -> report.

Exercises the whole local pipeline with clearly-labelled demo fixtures. No live provider is
contacted: the demo mode uses the mock provider.
"""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from pathlib import Path

from advertfloz.application.services import reporting
from advertfloz.application.services.activation import activate_window
from advertfloz.application.services.campaign_import import assemble_import
from advertfloz.application.services.campaign_revision import commit_import
from advertfloz.application.services.prompt_builder import BriefInputs, build_master_prompt, validate_brief
from advertfloz.config import Settings
from advertfloz.domain.enums import JobStatus, Platform, ProductionState, SyncState
from advertfloz.infrastructure.persistence.local_sqlite import Repository
from advertfloz.infrastructure.scheduler import run_once
from tests.builders import seed_connection
from tests.support import make_image_zip, plan_row, write_plan


def test_full_local_pipeline(tmp_path: Path):
    # 1. Prompt Builder produces a downloadable prompt.
    brief = BriefInputs(product_name="MusikFlo", product_url="https://musikflo.example",
                        target_markets="India", campaign_start_date="2027-01-01", campaign_tag="musikflo_2027")
    assert validate_brief(brief).ok
    assert "campaign_plan.csv" in build_master_prompt(brief)

    # 2. Build a 16-day plan and matching image ZIP (P001..P016 -> 1.jpg..16.jpg).
    rows = []
    start = date(2027, 1, 1)
    for index in range(16):
        day = start + timedelta(days=index)
        rows.append(plan_row(f"P{index + 1:03d}", scheduled_at=f"{day.isoformat()}T09:00:00", platforms="facebook",
                             campaign_tag="musikflo_2027"))
    plan_path = write_plan(tmp_path / "campaign_plan.csv", rows)
    zip_path = make_image_zip(tmp_path / "advertfloz_images_001_016.zip", list(range(1, 17)))

    # 3. Validate and commit the import.
    result = assemble_import(campaign_id="c1", campaign_name="c1", revision_id=1,
                             plan_path=plan_path, zip_paths=[zip_path])
    assert result.ok, result.blocking
    assert result.mapping_complete()

    repo = Repository(tmp_path / "e2e.sqlite")
    revision = commit_import(repo, result)
    assert revision == 1
    # Import never activates.
    assert all(j.status is JobStatus.DRAFT for j in repo.list_jobs())

    # 4. Human approves and the app syncs each asset.
    for asset in repo.list_assets():
        repo.update_production_state(asset.image_id, ProductionState.APPROVED, approved=True)
        repo.update_sync_state(asset.image_id, SyncState.SYNCED, remote_object_key=f"{asset.image_id}.jpg")

    seed_connection(repo, Platform.FACEBOOK)

    # 5. Activate a 16-day window (>= 14-day gate).
    readiness = activate_window(repo, campaign_id="c1", revision_id=1, platform=Platform.FACEBOOK,
                                window_start="2027-01-01", window_days=16, confirmed_target_id="page-1",
                                connection_test_passed=True)
    assert readiness.can_activate
    assert all(j.status is JobStatus.QUEUED for j in repo.list_jobs())

    # 6. Dispatch through the demo scheduler (mock provider).
    settings = Settings(mode="demo", db_path=tmp_path / "e2e.sqlite", media_base_url="", _secrets={})
    # Bring all jobs due now.
    for job in repo.list_jobs():
        repo.transition_job(job.job_id, JobStatus.QUEUED, clear_lease=True)
    repo.conn.execute("UPDATE platform_jobs SET due_at_utc = ?", ("2000-01-01T00:00:00+00:00",))

    run = run_once(repo, settings, limit=20)
    assert run.tick.published == 16, run.tick
    assert repo.get_flag("scheduler_heartbeat_at")

    # 7. Report reflects what actually happened.
    text = reporting.what_actually_posted_csv(repo)
    parsed = list(csv.DictReader(io.StringIO(text)))
    published = [r for r in parsed if r["status"] == "PUBLISHED"]
    assert len(published) == 16
    assert all(r["remote_post_id"] for r in published)
    repo.close()
