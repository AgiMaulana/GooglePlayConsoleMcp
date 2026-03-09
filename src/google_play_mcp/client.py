"""Google Play API clients for the Android Publisher API and Reporting API."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from googleapiclient.discovery import build

PUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
REPORTING_SCOPE = "https://www.googleapis.com/auth/playdeveloperreporting"
REPORTING_BASE_URL = "https://playdeveloperreporting.googleapis.com/v1beta1"


def _get_credentials(
    scopes: List[str], credentials_file: Optional[str] = None
):
    """Return Google credentials from a service account file or ADC."""
    creds_path = credentials_file or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        return service_account.Credentials.from_service_account_file(
            creds_path, scopes=scopes
        )
    creds, _ = google.auth.default(scopes=scopes)
    return creds


class PublisherClient:
    """Wraps the Google Play Android Publisher API v3 (edits + tracks)."""

    def __init__(self, credentials_file: Optional[str] = None) -> None:
        self.creds = _get_credentials([PUBLISHER_SCOPE], credentials_file)
        self.service = build("androidpublisher", "v3", credentials=self.creds)

    # ------------------------------------------------------------------
    # Low-level edit helpers
    # ------------------------------------------------------------------

    def _create_edit(self, package_name: str) -> str:
        result = self.service.edits().insert(
            packageName=package_name, body={}
        ).execute()
        return result["id"]

    def _commit_edit(self, package_name: str, edit_id: str) -> Dict[str, Any]:
        return self.service.edits().commit(
            packageName=package_name, editId=edit_id
        ).execute()

    def _delete_edit(self, package_name: str, edit_id: str) -> None:
        """Best-effort cleanup for read-only edits."""
        try:
            self.service.edits().delete(
                packageName=package_name, editId=edit_id
            ).execute()
        except Exception:
            pass

    def _get_track(
        self, package_name: str, edit_id: str, track: str
    ) -> Dict[str, Any]:
        return self.service.edits().tracks().get(
            packageName=package_name, editId=edit_id, track=track
        ).execute()

    def _update_track(
        self,
        package_name: str,
        edit_id: str,
        track: str,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.service.edits().tracks().update(
            packageName=package_name, editId=edit_id, track=track, body=body
        ).execute()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_track(self, package_name: str, track: str) -> Dict[str, Any]:
        """Read-only fetch of a track. Creates and deletes a temporary edit."""
        edit_id = self._create_edit(package_name)
        try:
            return self._get_track(package_name, edit_id, track)
        finally:
            self._delete_edit(package_name, edit_id)

    def promote_to_production(
        self,
        package_name: str,
        version_codes: List[int],
        rollout_percentage: float,
        release_name: Optional[str] = None,
        release_notes: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Promote the given version codes to the production track.

        rollout_percentage: 0 < value <= 100
        """
        if not (0 < rollout_percentage <= 100):
            raise ValueError(
                "rollout_percentage must be > 0 and <= 100."
            )

        release: Dict[str, Any] = {
            "versionCodes": [str(vc) for vc in version_codes],
            "status": "completed" if rollout_percentage == 100 else "inProgress",
        }
        if rollout_percentage < 100:
            release["userFraction"] = round(rollout_percentage / 100.0, 4)
        if release_name:
            release["name"] = release_name
        if release_notes:
            release["releaseNotes"] = release_notes

        edit_id = self._create_edit(package_name)
        try:
            track_body = {"track": "production", "releases": [release]}
            updated_track = self._update_track(
                package_name, edit_id, "production", track_body
            )
            commit = self._commit_edit(package_name, edit_id)
            return {"track": updated_track, "commit": commit}
        except Exception:
            self._delete_edit(package_name, edit_id)
            raise

    def update_rollout_percentage(
        self,
        package_name: str,
        rollout_percentage: float,
        version_codes: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Update the rollout percentage of an existing production release.

        Targets the first release whose status is inProgress or halted.
        If version_codes is provided, only a release containing those codes
        will be updated.
        """
        if not (0 < rollout_percentage <= 100):
            raise ValueError(
                "rollout_percentage must be > 0 and <= 100."
            )

        edit_id = self._create_edit(package_name)
        try:
            track_data = self._get_track(package_name, edit_id, "production")
            releases: List[Dict[str, Any]] = track_data.get("releases", [])

            target_vcs = (
                {str(vc) for vc in version_codes} if version_codes else None
            )

            updated = False
            for release in releases:
                if release.get("status") not in ("inProgress", "halted", "completed"):
                    continue
                if target_vcs:
                    existing_vcs = set(release.get("versionCodes", []))
                    if not existing_vcs.intersection(target_vcs):
                        continue

                if rollout_percentage >= 100:
                    release["status"] = "completed"
                    release.pop("userFraction", None)
                else:
                    release["status"] = "inProgress"
                    release["userFraction"] = round(rollout_percentage / 100.0, 4)
                updated = True
                break

            if not updated:
                raise ValueError(
                    "No matching inProgress/halted/completed release found "
                    "in the production track."
                )

            track_body = {"track": "production", "releases": releases}
            updated_track = self._update_track(
                package_name, edit_id, "production", track_body
            )
            commit = self._commit_edit(package_name, edit_id)
            return {"track": updated_track, "commit": commit}
        except Exception:
            self._delete_edit(package_name, edit_id)
            raise


class ReportingClient:
    """Wraps the Google Play Developer Reporting API v1beta1."""

    def __init__(self, credentials_file: Optional[str] = None) -> None:
        self.creds = _get_credentials([REPORTING_SCOPE], credentials_file)
        self.session = AuthorizedSession(self.creds)

    def _app_path(self, package_name: str) -> str:
        return f"apps/{package_name}"

    def query_crash_rate(
        self,
        package_name: str,
        days: int = 7,
        version_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query crash-rate metrics for the app.

        Returns crashRate, userPerceivedCrashRate, and distinctUsers
        aggregated daily, broken down by versionCode.
        """
        app = self._app_path(package_name)
        url = f"{REPORTING_BASE_URL}/{app}/crashRateMetricSet:query"

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        def _date(dt: datetime) -> Dict[str, int]:
            return {"year": dt.year, "month": dt.month, "day": dt.day}

        body: Dict[str, Any] = {
            "timelineSpec": {
                "aggregationPeriod": "DAILY",
                "startTime": _date(start),
                "endTime": _date(end),
            },
            "metrics": [
                "crashRate",
                "userPerceivedCrashRate",
                "distinctUsers",
            ],
            "dimensions": ["versionCode"],
            "pageSize": days * 10,
        }
        if version_code:
            body["filter"] = f'versionCode = "{version_code}"'

        resp = self.session.post(url, json=body)
        resp.raise_for_status()
        return resp.json()

    def list_available_metrics(self, package_name: str) -> Dict[str, Any]:
        """List all available metric sets for the app (for debugging)."""
        app = self._app_path(package_name)
        url = f"{REPORTING_BASE_URL}/{app}/crashRateMetricSet"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()
