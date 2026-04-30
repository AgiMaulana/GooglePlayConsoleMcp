"""Pytest fixtures for Google Play MCP server tests."""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest


@pytest.fixture
def mock_publisher_client():
    """Mock PublisherClient with typical test data."""
    with patch("google_play_mcp.server.PublisherClient") as mock:
        client = MagicMock()
        mock.return_value = client

        client.list_tracks.return_value = {
            "tracks": [
                {
                    "track": "internal",
                    "releases": [
                        {
                            "name": "v1.0.0",
                            "versionCodes": ["1"],
                            "status": "completed",
                            "userFraction": 1.0,
                        }
                    ],
                },
                {
                    "track": "production",
                    "releases": [
                        {
                            "name": "v1.0.0",
                            "versionCodes": ["1"],
                            "status": "completed",
                            "userFraction": 1.0,
                        }
                    ],
                },
            ]
        }

        client.get_track.return_value = {
            "track": "production",
            "releases": [
                {
                    "name": "v1.0.0",
                    "versionCodes": ["1"],
                    "status": "completed",
                    "userFraction": 1.0,
                }
            ],
        }

        client.create_release.return_value = {
            "track": {
                "track": "production",
                "releases": [
                    {
                        "name": "v1.0.0",
                        "versionCodes": ["1"],
                        "status": "draft",
                    }
                ],
            },
            "commit": {"editId": "edit123"},
        }

        client.update_release.return_value = {
            "track": {
                "track": "production",
                "releases": [
                    {
                        "versionCodes": ["1"],
                        "status": "inProgress",
                        "userFraction": 0.1,
                    }
                ],
            },
            "commit": {"editId": "edit123"},
        }

        client.promote_release.return_value = {
            "track": {
                "track": "beta",
                "releases": [
                    {
                        "versionCodes": ["1"],
                        "status": "inProgress",
                        "userFraction": 0.1,
                    }
                ],
            },
            "commit": {"editId": "edit123"},
        }

        client.publish_managed_release.return_value = {}

        client.list_artifacts.return_value = {
            "apks": [
                {
                    "versionCode": "1",
                    "binary": {"sha1": "abc", "sha256": "def"},
                }
            ],
            "bundles": [],
        }

        client.upload_artifact.return_value = {
            "versionCode": 1,
            "artifactType": "apk",
            "track": {
                "track": "internal",
                "releases": [
                    {
                        "versionCodes": ["1"],
                        "status": "draft",
                    }
                ],
            },
            "commit": {"editId": "edit123"},
        }

        client.upload_to_internal_sharing.return_value = {
            "downloadUrl": "https://play.google.com/apps/testing/abc",
            "artifactType": "apk",
            "certificateFingerprint": "finger",
        }

        client.get_testers.return_value = {
            "testers": ["test@example.com"],
            "googleGroups": [],
        }

        client.update_testers.return_value = {
            "testers": {"testers": ["test@example.com"], "googleGroups": []},
            "commit": {"editId": "edit123"},
        }

        yield client


@pytest.fixture
def mock_reporting_client():
    """Mock ReportingClient with typical test data."""
    with patch("google_play_mcp.server.ReportingClient") as mock:
        client = MagicMock()
        mock.return_value = client

        client.query_crash_rate.return_value = {
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

        client.query_anr_rate.return_value = {
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

        client.query_wakelock_rate.return_value = {
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

        client.query_wakeup_rate.return_value = {
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

        yield client


@pytest.fixture
def mock_creds(monkeypatch):
    """Disable actual Google credentials loading."""
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
