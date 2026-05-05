"""Tests for MCP server tool functions."""

from unittest.mock import patch

import pytest


@pytest.fixture
def publisher_mock():
    with patch("google_play_mcp.server._publisher") as mock:
        yield mock


@pytest.fixture
def reporting_mock():
    with patch("google_play_mcp.server._reporting") as mock:
        yield mock


class TestListTracks:
    def test_returns_dict(self, publisher_mock):
        from google_play_mcp.server import list_tracks

        publisher_mock.return_value.list_tracks.return_value = {
            "tracks": [
                {
                    "track": "production",
                    "releases": [
                        {
                            "name": "v1.0",
                            "versionCodes": ["1"],
                            "status": "completed",
                            "userFraction": 1.0,
                        }
                    ],
                }
            ]
        }

        result = list_tracks("com.example.app")

        assert isinstance(result, dict)
        assert "packageName" in result
        assert "tracks" in result

    def test_error_returns_dict(self, publisher_mock):
        from google_play_mcp.server import list_tracks

        publisher_mock.return_value.list_tracks.side_effect = Exception("API error")

        result = list_tracks("com.example.app")

        assert isinstance(result, dict)
        assert result["success"] is False
        assert "error" in result


class TestGetTrackInfo:
    def test_returns_dict(self, publisher_mock):
        from google_play_mcp.server import get_track_info

        publisher_mock.return_value.get_track.return_value = {
            "track": "production",
            "releases": [
                {
                    "name": "v1.0",
                    "versionCodes": ["1"],
                    "status": "completed",
                    "userFraction": 1.0,
                }
            ],
        }

        result = get_track_info("com.example.app", "production")

        assert isinstance(result, dict)
        assert "packageName" in result
        assert "summary" in result


class TestCreateRelease:
    def test_returns_dict(self, publisher_mock):
        from google_play_mcp.server import create_release

        publisher_mock.return_value.create_release.return_value = {
            "track": {"track": "production", "releases": []},
            "commit": {"editId": "edit123"},
        }

        result = create_release(
            package_name="com.example.app",
            track="production",
            version_codes=[1],
        )

        assert isinstance(result, dict)
        assert result["success"] is True
        assert "track" in result
        assert "editId" in result

    def test_error_returns_dict(self, publisher_mock):
        from google_play_mcp.server import create_release

        publisher_mock.return_value.create_release.side_effect = Exception("API error")

        result = create_release(
            package_name="com.example.app",
            track="production",
            version_codes=[1],
        )

        assert isinstance(result, dict)
        assert result["success"] is False


class TestUpdateRelease:
    def test_returns_dict(self, publisher_mock):
        from google_play_mcp.server import update_release

        publisher_mock.return_value.update_release.return_value = {
            "track": {"track": "production", "releases": []},
            "commit": {"editId": "edit123"},
        }

        result = update_release(
            package_name="com.example.app",
            track="production",
            rollout_percentage=50,
        )

        assert isinstance(result, dict)
        assert result["success"] is True


class TestUpdateReleaseFiltersCompletedReleases:
    """Test for GitHub issue #6: update_release should filter out completed releases."""

    def test_update_to_100_percent_filters_other_completed_releases(self, publisher_mock):
        """When completing a staged rollout, other completed releases are excluded from PUT body."""
        from google_play_mcp.client import PublisherClient
        from unittest.mock import MagicMock

        # Create a real PublisherClient but mock the internal methods
        with patch.object(PublisherClient, '_create_edit') as mock_create, \
             patch.object(PublisherClient, '_get_track') as mock_get, \
             patch.object(PublisherClient, '_update_track') as mock_update, \
             patch.object(PublisherClient, '_commit_edit') as mock_commit, \
             patch.object(PublisherClient, '_delete_edit'):
            
            mock_create.return_value = "edit123"
            mock_get.return_value = {
                "track": "production",
                "releases": [
                    {"name": "5.58.5", "versionCodes": ["50107"], "status": "inProgress", "userFraction": 0.5},
                    {"name": "5.57.2", "versionCodes": ["50106"], "status": "completed", "userFraction": 1.0},
                ],
            }
            mock_update.return_value = {"track": "production", "releases": []}
            mock_commit.return_value = {"editId": "edit123"}
            
            # Create client with mocked credentials
            with patch("google_play_mcp.client._get_credentials"):
                client = PublisherClient()
                
                # Update the inProgress release to 100%
                result = client.update_release(
                    package_name="com.example.app",
                    track="production",
                    rollout_percentage=100,
                    version_codes=[50107],
                )
                
                # Verify _update_track was called with filtered releases
                mock_update.assert_called_once()
                call_args = mock_update.call_args
                body = call_args[0][3]  # The body parameter
                
                # Should only have 1 release (the target), not both
                assert len(body["releases"]) == 1, \
                    f"Expected 1 release in PUT body, got {len(body['releases'])}"
                assert body["releases"][0]["versionCodes"] == ["50107"]
                assert body["releases"][0]["status"] == "completed"


class TestPromoteRelease:
    def test_returns_dict(self, publisher_mock):
        from google_play_mcp.server import promote_release

        publisher_mock.return_value.promote_release.return_value = {
            "track": {"track": "beta", "releases": []},
            "commit": {"editId": "edit123"},
        }

        result = promote_release(
            package_name="com.example.app",
            from_track="internal",
            to_track="beta",
            version_codes=[1],
        )

        assert isinstance(result, dict)
        assert result["success"] is True


class TestPublishManagedRelease:
    def test_returns_dict(self, publisher_mock):
        from google_play_mcp.server import publish_managed_release

        publisher_mock.return_value.publish_managed_release.return_value = {}

        result = publish_managed_release("com.example.app")

        assert isinstance(result, dict)
        assert result["success"] is True


class TestListArtifacts:
    def test_returns_dict(self, publisher_mock):
        from google_play_mcp.server import list_artifacts

        publisher_mock.return_value.list_artifacts.return_value = {
            "apks": [{"versionCode": "1", "binary": {"sha1": "abc", "sha256": "def"}}],
            "bundles": [],
        }

        result = list_artifacts("com.example.app")

        assert isinstance(result, dict)
        assert "packageName" in result
        assert "artifacts" in result


class TestUploadArtifact:
    def test_returns_dict(self, publisher_mock):
        from google_play_mcp.server import upload_artifact

        publisher_mock.return_value.upload_artifact.return_value = {
            "versionCode": 1,
            "artifactType": "apk",
            "track": {"track": "internal", "releases": []},
            "commit": {"editId": "edit123"},
        }

        result = upload_artifact(
            package_name="com.example.app",
            file_path="/tmp/app.apk",
        )

        assert isinstance(result, dict)
        assert result["success"] is True


class TestUploadToInternalSharing:
    def test_returns_dict(self, publisher_mock):
        from google_play_mcp.server import upload_to_internal_sharing

        publisher_mock.return_value.upload_to_internal_sharing.return_value = {
            "downloadUrl": "https://example.com",
            "artifactType": "apk",
            "certificateFingerprint": "abc",
        }

        result = upload_to_internal_sharing(
            package_name="com.example.app",
            file_path="/tmp/app.apk",
        )

        assert isinstance(result, dict)
        assert result["success"] is True


class TestGetTesters:
    def test_returns_dict(self, publisher_mock):
        from google_play_mcp.server import get_testers

        publisher_mock.return_value.get_testers.return_value = {
            "testers": ["test@example.com"],
            "googleGroups": [],
        }

        result = get_testers("com.example.app")

        assert isinstance(result, dict)
        assert "testers" in result


class TestUpdateTesters:
    def test_returns_dict(self, publisher_mock):
        from google_play_mcp.server import update_testers

        publisher_mock.return_value.update_testers.return_value = {
            "testers": {"testers": ["test@example.com"], "googleGroups": []},
            "commit": {"editId": "edit123"},
        }

        result = update_testers(
            package_name="com.example.app",
            emails=["test@example.com"],
        )

        assert isinstance(result, dict)
        assert result["success"] is True


class TestGetCrashRate:
    def test_returns_dict(self, reporting_mock):
        from google_play_mcp.server import get_crash_rate

        reporting_mock.return_value.query_crash_rate.return_value = {
            "rows": [
                {
                    "startTime": {"year": 2024, "month": 1, "day": 1},
                    "dimensions": [{"dimension": "versionCode", "stringValue": "1"}],
                    "metrics": [
                        {"metric": "crashRate", "decimalValue": {"value": "0.01"}},
                        {
                            "metric": "userPerceivedCrashRate",
                            "decimalValue": {"value": "0.005"},
                        },
                        {"metric": "distinctUsers", "int64Value": "100"},
                    ],
                }
            ]
        }

        result = get_crash_rate("com.example.app")

        assert isinstance(result, dict)
        assert "packageName" in result
        assert "rows" in result


class TestGetAnrRate:
    def test_returns_dict(self, reporting_mock):
        from google_play_mcp.server import get_anr_rate

        reporting_mock.return_value.query_anr_rate.return_value = {
            "rows": [
                {
                    "startTime": {"year": 2024, "month": 1, "day": 1},
                    "dimensions": [{"dimension": "versionCode", "stringValue": "1"}],
                    "metrics": [
                        {"metric": "anrRate", "decimalValue": {"value": "0.001"}},
                        {
                            "metric": "userPerceivedAnrRate",
                            "decimalValue": {"value": "0.0005"},
                        },
                        {"metric": "distinctUsers", "int64Value": "100"},
                    ],
                }
            ]
        }

        result = get_anr_rate("com.example.app")

        assert isinstance(result, dict)
        assert "packageName" in result


class TestGetWakelockRate:
    def test_returns_dict(self, reporting_mock):
        from google_play_mcp.server import get_wakelock_rate

        reporting_mock.return_value.query_wakelock_rate.return_value = {
            "rows": [
                {
                    "startTime": {"year": 2024, "month": 1, "day": 1},
                    "dimensions": [{"dimension": "versionCode", "stringValue": "1"}],
                    "metrics": [
                        {
                            "metric": "stuckBackgroundWakelockRate",
                            "decimalValue": {"value": "0.001"},
                        },
                        {"metric": "distinctUsers", "int64Value": "100"},
                    ],
                }
            ]
        }

        result = get_wakelock_rate("com.example.app")

        assert isinstance(result, dict)
        assert "packageName" in result


class TestGetWakeupRate:
    def test_returns_dict(self, reporting_mock):
        from google_play_mcp.server import get_wakeup_rate

        reporting_mock.return_value.query_wakeup_rate.return_value = {
            "rows": [
                {
                    "startTime": {"year": 2024, "month": 1, "day": 1},
                    "dimensions": [{"dimension": "versionCode", "stringValue": "1"}],
                    "metrics": [
                        {
                            "metric": "excessiveWakeupRate",
                            "decimalValue": {"value": "0.01"},
                        },
                        {"metric": "distinctUsers", "int64Value": "100"},
                    ],
                }
            ]
        }

        result = get_wakeup_rate("com.example.app")

        assert isinstance(result, dict)
        assert "packageName" in result


class TestGetVitalsSummary:
    def test_returns_dict(self, reporting_mock):
        from google_play_mcp.server import get_vitals_summary

        reporting_mock.return_value.query_crash_rate.return_value = {
            "rows": [
                {
                    "startTime": {"year": 2024, "month": 1, "day": 1},
                    "dimensions": [{"dimension": "versionCode", "stringValue": "1"}],
                    "metrics": [
                        {"metric": "crashRate", "decimalValue": {"value": "0.01"}},
                        {
                            "metric": "userPerceivedCrashRate",
                            "decimalValue": {"value": "0.005"},
                        },
                        {"metric": "distinctUsers", "int64Value": "100"},
                    ],
                }
            ]
        }
        reporting_mock.return_value.query_anr_rate.return_value = {
            "rows": [
                {
                    "startTime": {"year": 2024, "month": 1, "day": 1},
                    "dimensions": [{"dimension": "versionCode", "stringValue": "1"}],
                    "metrics": [
                        {"metric": "anrRate", "decimalValue": {"value": "0.001"}},
                        {
                            "metric": "userPerceivedAnrRate",
                            "decimalValue": {"value": "0.0005"},
                        },
                        {"metric": "distinctUsers", "int64Value": "100"},
                    ],
                }
            ]
        }

        result = get_vitals_summary("com.example.app")

        assert isinstance(result, dict)
        assert "packageName" in result
        assert "allVersions" in result
