"""Tests for the PublisherClient update_release filtering logic (GitHub issue #6).

These tests mock the underlying API calls to verify that the fix correctly
filters out completed releases when updating a release to 100%.
"""

from unittest.mock import MagicMock, patch

import pytest

from google_play_mcp.client import PublisherClient


@pytest.fixture
def publisher_client():
    """Create a PublisherClient with mocked internal methods."""
    with patch("google_play_mcp.client._get_credentials") as mock_creds:
        mock_creds.return_value = MagicMock()
        client = PublisherClient()
        client.service = MagicMock()
        yield client


class TestUpdateReleaseFiltersCompletedReleases:
    """Test that update_release filters out other completed releases (issue #6)."""

    def _setup_track_response(self, releases):
        """Helper to set up mock responses for track operations."""
        return {
            "track": "production",
            "releases": releases,
        }

    def test_complete_staged_rollout_excludes_other_completed_releases(
        self, publisher_client
    ):
        """When completing a staged rollout, other completed releases are excluded.

        Scenario:
        - Track has: inProgress release (v5.58.5 at 50%) + completed release (v5.57.2 at 100%)
        - Action: Update v5.58.5 to 100%
        - Expected: PUT body only contains v5.58.5 (completed), v5.57.2 is excluded
        """
        publisher_client._create_edit = MagicMock(return_value="edit123")
        publisher_client._get_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "inProgress",
                        "userFraction": 0.5,
                    },
                    {
                        "name": "5.57.2",
                        "versionCodes": ["50106"],
                        "status": "completed",
                        "userFraction": 1.0,
                    },
                ],
            }
        )
        publisher_client._update_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "completed",
                    }
                ],
            }
        )
        publisher_client._commit_edit = MagicMock(return_value={"editId": "edit123"})

        result = publisher_client.update_release(
            package_name="com.example.app",
            track="production",
            rollout_percentage=100,
            version_codes=[50107],
        )

        # Verify the PUT body only contains the target release
        publisher_client._update_track.assert_called_once()
        call_args = publisher_client._update_track.call_args
        body = call_args[0][3]  # The body parameter

        assert len(body["releases"]) == 1
        assert body["releases"][0]["versionCodes"] == ["50107"]
        assert body["releases"][0]["status"] == "completed"
        assert "userFraction" not in body["releases"][0]

        # Verify result structure
        assert "track" in result
        assert "commit" in result

    def test_partial_rollout_keeps_all_releases(self, publisher_client):
        """When updating to a partial rollout (<100%), other completed releases are kept.

        Scenario:
        - Track has: inProgress release (v5.58.5 at 50%) + completed release (v5.57.2 at 100%)
        - Action: Update v5.58.5 to 75%
        - Expected: PUT body contains both releases
        """
        publisher_client._create_edit = MagicMock(return_value="edit123")
        publisher_client._get_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "inProgress",
                        "userFraction": 0.5,
                    },
                    {
                        "name": "5.57.2",
                        "versionCodes": ["50106"],
                        "status": "completed",
                        "userFraction": 1.0,
                    },
                ],
            }
        )
        publisher_client._update_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "inProgress",
                        "userFraction": 0.75,
                    },
                    {
                        "name": "5.57.2",
                        "versionCodes": ["50106"],
                        "status": "completed",
                        "userFraction": 1.0,
                    },
                ],
            }
        )
        publisher_client._commit_edit = MagicMock(return_value={"editId": "edit123"})

        result = publisher_client.update_release(
            package_name="com.example.app",
            track="production",
            rollout_percentage=75,
            version_codes=[50107],
        )

        publisher_client._update_track.assert_called_once()
        call_args = publisher_client._update_track.call_args
        body = call_args[0][3]

        # Both releases should be included
        assert len(body["releases"]) == 2
        version_codes_in_body = {
            tuple(r["versionCodes"]) for r in body["releases"]
        }
        assert ("50107",) in version_codes_in_body
        assert ("50106",) in version_codes_in_body

    def test_halt_rollout_keeps_completed_releases(self, publisher_client):
        """When halting a rollout, completed releases are kept.

        Scenario:
        - Track has: inProgress release (v5.58.5 at 50%) + completed release (v5.57.2 at 100%)
        - Action: Halt v5.58.5
        - Expected: PUT body contains both releases
        """
        publisher_client._create_edit = MagicMock(return_value="edit123")
        publisher_client._get_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "inProgress",
                        "userFraction": 0.5,
                    },
                    {
                        "name": "5.57.2",
                        "versionCodes": ["50106"],
                        "status": "completed",
                        "userFraction": 1.0,
                    },
                ],
            }
        )
        publisher_client._update_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "halted",
                        "userFraction": 0.5,
                    },
                    {
                        "name": "5.57.2",
                        "versionCodes": ["50106"],
                        "status": "completed",
                        "userFraction": 1.0,
                    },
                ],
            }
        )
        publisher_client._commit_edit = MagicMock(return_value={"editId": "edit123"})

        publisher_client.update_release(
            package_name="com.example.app",
            track="production",
            status="halted",
            version_codes=[50107],
        )

        publisher_client._update_track.assert_called_once()
        call_args = publisher_client._update_track.call_args
        body = call_args[0][3]

        # Both releases should be included
        assert len(body["releases"]) == 2

    def test_update_completed_release_keeps_it(self, publisher_client):
        """When the target release is already completed, it should be kept.

        Scenario:
        - Track has: completed release (v5.58.5 at 100%) + completed release (v5.57.2 at 100%)
        - Action: Update v5.58.5 (already completed) - e.g., to resume or halt
        - Expected: PUT body only contains v5.58.5, v5.57.2 is excluded
        """
        publisher_client._create_edit = MagicMock(return_value="edit123")
        publisher_client._get_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "completed",
                        "userFraction": 1.0,
                    },
                    {
                        "name": "5.57.2",
                        "versionCodes": ["50106"],
                        "status": "completed",
                        "userFraction": 1.0,
                    },
                ],
            }
        )
        publisher_client._update_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "inProgress",
                        "userFraction": 1.0,
                    }
                ],
            }
        )
        publisher_client._commit_edit = MagicMock(return_value={"editId": "edit123"})

        publisher_client.update_release(
            package_name="com.example.app",
            track="production",
            status="inProgress",
            version_codes=[50107],
        )

        publisher_client._update_track.assert_called_once()
        call_args = publisher_client._update_track.call_args
        body = call_args[0][3]

        # Only the target release should be included
        assert len(body["releases"]) == 1
        assert body["releases"][0]["versionCodes"] == ["50107"]

    def test_update_without_version_codes_filters_completed(self, publisher_client):
        """When no version_codes specified, updates first matching release and filters others.

        Scenario:
        - Track has: inProgress release (first) + completed release
        - Action: Update to 100% without specifying version_codes
        - Expected: Updates the inProgress release, excludes the completed one
        """
        publisher_client._create_edit = MagicMock(return_value="edit123")
        publisher_client._get_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "inProgress",
                        "userFraction": 0.5,
                    },
                    {
                        "name": "5.57.2",
                        "versionCodes": ["50106"],
                        "status": "completed",
                        "userFraction": 1.0,
                    },
                ],
            }
        )
        publisher_client._update_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "completed",
                    }
                ],
            }
        )
        publisher_client._commit_edit = MagicMock(return_value={"editId": "edit123"})

        publisher_client.update_release(
            package_name="com.example.app",
            track="production",
            rollout_percentage=100,
        )

        publisher_client._update_track.assert_called_once()
        call_args = publisher_client._update_track.call_args
        body = call_args[0][3]

        # Only the target release should be included
        assert len(body["releases"]) == 1
        assert body["releases"][0]["versionCodes"] == ["50107"]

    def test_only_completed_release_on_track(self, publisher_client):
        """When there's only one completed release, it should be kept.

        Scenario:
        - Track has: single completed release
        - Action: Update to 100% (no-op, but shouldn't break)
        - Expected: PUT body contains the release
        """
        publisher_client._create_edit = MagicMock(return_value="edit123")
        publisher_client._get_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "completed",
                        "userFraction": 1.0,
                    }
                ],
            }
        )
        publisher_client._update_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "completed",
                    }
                ],
            }
        )
        publisher_client._commit_edit = MagicMock(return_value={"editId": "edit123"})

        publisher_client.update_release(
            package_name="com.example.app",
            track="production",
            rollout_percentage=100,
            version_codes=[50107],
        )

        publisher_client._update_track.assert_called_once()
        call_args = publisher_client._update_track.call_args
        body = call_args[0][3]

        # The release should still be included
        assert len(body["releases"]) == 1
        assert body["releases"][0]["versionCodes"] == ["50107"]

    def test_multiple_inprogress_releases_complete_one(self, publisher_client):
        """When completing one inProgress release, keep other inProgress releases.

        Scenario:
        - Track has: inProgress (v5.58.5 at 50%) + inProgress (v5.58.0 at 30%) + completed (v5.57.2)
        - Action: Update v5.58.5 to 100%
        - Expected: PUT body contains v5.58.5 (completed) and v5.58.0 (inProgress), excludes v5.57.2
        """
        publisher_client._create_edit = MagicMock(return_value="edit123")
        publisher_client._get_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "inProgress",
                        "userFraction": 0.5,
                    },
                    {
                        "name": "5.58.0",
                        "versionCodes": ["50105"],
                        "status": "inProgress",
                        "userFraction": 0.3,
                    },
                    {
                        "name": "5.57.2",
                        "versionCodes": ["50106"],
                        "status": "completed",
                        "userFraction": 1.0,
                    },
                ],
            }
        )
        publisher_client._update_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "completed",
                    },
                    {
                        "name": "5.58.0",
                        "versionCodes": ["50105"],
                        "status": "inProgress",
                        "userFraction": 0.3,
                    },
                ],
            }
        )
        publisher_client._commit_edit = MagicMock(return_value={"editId": "edit123"})

        publisher_client.update_release(
            package_name="com.example.app",
            track="production",
            rollout_percentage=100,
            version_codes=[50107],
        )

        publisher_client._update_track.assert_called_once()
        call_args = publisher_client._update_track.call_args
        body = call_args[0][3]

        # Should have 2 releases: the completed one and the other inProgress one
        assert len(body["releases"]) == 2
        version_codes_in_body = {
            tuple(r["versionCodes"]) for r in body["releases"]
        }
        assert ("50107",) in version_codes_in_body  # Target (now completed)
        assert ("50105",) in version_codes_in_body  # Other inProgress
        assert ("50106",) not in version_codes_in_body  # Old completed (excluded)

    def test_draft_releases_not_filtered(self, publisher_client):
        """Draft releases should never be filtered out.

        Scenario:
        - Track has: inProgress (v5.58.5 at 50%) + draft (v5.59.0) + completed (v5.57.2)
        - Action: Update v5.58.5 to 100%
        - Expected: PUT body contains v5.58.5 (completed) and v5.59.0 (draft), excludes v5.57.2
        """
        publisher_client._create_edit = MagicMock(return_value="edit123")
        publisher_client._get_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "inProgress",
                        "userFraction": 0.5,
                    },
                    {
                        "name": "5.59.0",
                        "versionCodes": ["50108"],
                        "status": "draft",
                    },
                    {
                        "name": "5.57.2",
                        "versionCodes": ["50106"],
                        "status": "completed",
                        "userFraction": 1.0,
                    },
                ],
            }
        )
        publisher_client._update_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "completed",
                    },
                    {
                        "name": "5.59.0",
                        "versionCodes": ["50108"],
                        "status": "draft",
                    },
                ],
            }
        )
        publisher_client._commit_edit = MagicMock(return_value={"editId": "edit123"})

        publisher_client.update_release(
            package_name="com.example.app",
            track="production",
            rollout_percentage=100,
            version_codes=[50107],
        )

        publisher_client._update_track.assert_called_once()
        call_args = publisher_client._update_track.call_args
        body = call_args[0][3]

        # Should have 2 releases: the completed one and the draft one
        assert len(body["releases"]) == 2
        version_codes_in_body = {
            tuple(r["versionCodes"]) for r in body["releases"]
        }
        assert ("50107",) in version_codes_in_body  # Target (now completed)
        assert ("50108",) in version_codes_in_body  # Draft (kept)
        assert ("50106",) not in version_codes_in_body  # Old completed (excluded)

    def test_halted_release_not_filtered_when_completing_other(
        self, publisher_client
    ):
        """Halted releases should not be filtered when completing another release.

        Scenario:
        - Track has: inProgress (v5.58.5 at 50%) + halted (v5.58.0 at 30%) + completed (v5.57.2)
        - Action: Update v5.58.5 to 100%
        - Expected: PUT body contains v5.58.5 (completed) and v5.58.0 (halted), excludes v5.57.2
        """
        publisher_client._create_edit = MagicMock(return_value="edit123")
        publisher_client._get_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "inProgress",
                        "userFraction": 0.5,
                    },
                    {
                        "name": "5.58.0",
                        "versionCodes": ["50105"],
                        "status": "halted",
                        "userFraction": 0.3,
                    },
                    {
                        "name": "5.57.2",
                        "versionCodes": ["50106"],
                        "status": "completed",
                        "userFraction": 1.0,
                    },
                ],
            }
        )
        publisher_client._update_track = MagicMock(
            return_value={
                "track": "production",
                "releases": [
                    {
                        "name": "5.58.5",
                        "versionCodes": ["50107"],
                        "status": "completed",
                    },
                    {
                        "name": "5.58.0",
                        "versionCodes": ["50105"],
                        "status": "halted",
                        "userFraction": 0.3,
                    },
                ],
            }
        )
        publisher_client._commit_edit = MagicMock(return_value={"editId": "edit123"})

        publisher_client.update_release(
            package_name="com.example.app",
            track="production",
            rollout_percentage=100,
            version_codes=[50107],
        )

        publisher_client._update_track.assert_called_once()
        call_args = publisher_client._update_track.call_args
        body = call_args[0][3]

        # Should have 2 releases: the completed one and the halted one
        assert len(body["releases"]) == 2
        version_codes_in_body = {
            tuple(r["versionCodes"]) for r in body["releases"]
        }
        assert ("50107",) in version_codes_in_body  # Target (now completed)
        assert ("50105",) in version_codes_in_body  # Halted (kept)
        assert ("50106",) not in version_codes_in_body  # Old completed (excluded)

    def test_no_error_cleanup_on_exception(self, publisher_client):
        """When an exception occurs, the edit should be deleted for cleanup."""
        publisher_client._create_edit = MagicMock(return_value="edit123")
        publisher_client._get_track = MagicMock(
            side_effect=Exception("API error")
        )
        publisher_client._delete_edit = MagicMock()

        with pytest.raises(Exception, match="API error"):
            publisher_client.update_release(
                package_name="com.example.app",
                track="production",
                rollout_percentage=100,
                version_codes=[50107],
            )

        # Verify cleanup was called
        publisher_client._delete_edit.assert_called_once_with(
            "com.example.app", "edit123"
        )
