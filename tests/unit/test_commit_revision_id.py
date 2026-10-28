from __future__ import annotations

import tempfile
from pathlib import Path

from advertfloz.application.services.campaign_import import ImportResult
from advertfloz.application.services.campaign_revision import commit_import
from advertfloz.domain.enums import Platform
from advertfloz.domain.models import Campaign, Post
from advertfloz.infrastructure.persistence.local_sqlite import Repository


def test_commit_import_updates_post_revision_id_across_campaigns():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.sqlite"
        repo = Repository(str(db_path))

        # First campaign gets revision 1
        repo.upsert_campaign(
            Campaign(
                campaign_id="campaign-first",
                name="First Campaign",
                campaign_tag="first",
                default_timezone="Asia/Kolkata",
                start_date="2026-01-01",
                end_date="2026-01-30",
            )
        )
        r1 = repo.create_revision("campaign-first", "hash1")
        assert r1 == 1

        # Second campaign has posts assembled with default revision_id=1
        posts = [
            Post(
                post_id="P001",
                campaign_id="campaign-second",
                revision_id=1,
                image_id=1,
                scheduled_at="2026-01-01T10:00:00",
                timezone="Asia/Kolkata",
                platforms=(Platform.FACEBOOK,),
                caption="Testing revision synchronization",
            )
        ]
        result = ImportResult(
            campaign_id="campaign-second",
            campaign_name="Second Campaign",
            campaign_tag="second",
            default_timezone="Asia/Kolkata",
            start_date="2026-01-01",
            end_date="2026-01-30",
            posts=posts,
            assets={},
            issues=[],
            plan_hash="hash2",
        )

        # Commit should create revision 2, and update posts' revision_id to 2
        r2 = commit_import(repo, result)
        assert r2 == 2
        assert result.posts[0].revision_id == 2

        # list_posts with revision_id=2 should find the post
        found = repo.list_posts("campaign-second", 2)
        assert len(found) == 1
        assert found[0].revision_id == 2
        assert found[0].post_id == "P001"

        repo.close()

