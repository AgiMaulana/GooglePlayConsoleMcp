"""Google Play API clients for the Android Publisher API and Reporting API."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

PUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
REPORTING_SCOPE = "https://www.googleapis.com/auth/playdeveloperreporting"
REPORTING_BASE_URL = "https://playdeveloperreporting.googleapis.com/v1beta1"

APK_MIME = "application/vnd.android.package-archive"
BUNDLE_MIME = "application/octet-stream"


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
    """Wraps the Google Play Android Publisher API v3 (edits + tracks + testers)."""

    def __init__(self, credentials_file: Optional[str] = None) -> None:
        self.creds = _get_credentials([PUBLISHER_SCOPE], credentials_file)
        self.service = build("androidpublisher", "v3", credentials=self.creds)

    # -----------------------------------------------------------------------
    # Edit lifecycle helpers
    # -----------------------------------------------------------------------

    def _create_edit(self, package_name: str) -> str:
        return self.service.edits().insert(
            packageName=package_name, body={}
        ).execute()["id"]

    def _commit_edit(self, package_name: str, edit_id: str) -> Dict[str, Any]:
        return self.service.edits().commit(
            packageName=package_name, editId=edit_id
        ).execute()

    def _delete_edit(self, package_name: str, edit_id: str) -> None:
        """Best-effort cleanup for read-only or failed edits."""
        try:
            self.service.edits().delete(
                packageName=package_name, editId=edit_id
            ).execute()
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Low-level helpers (used within an open edit)
    # -----------------------------------------------------------------------

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

    def _get_country_availability(
        self, package_name: str, edit_id: str, track: str
    ) -> Dict[str, Any]:
        try:
            return self.service.edits().countryavailability().get(
                packageName=package_name, editId=edit_id, track=track
            ).execute()
        except Exception:
            return {}

    # -----------------------------------------------------------------------
    # Public: Track & Release Management
    # -----------------------------------------------------------------------

    def list_tracks(self, package_name: str) -> Dict[str, Any]:
        """Return all tracks with their releases and country availability."""
        edit_id = self._create_edit(package_name)
        try:
            result = self.service.edits().tracks().list(
                packageName=package_name, editId=edit_id
            ).execute()
            tracks = result.get("tracks", [])
            for track_data in tracks:
                track_name = track_data.get("track", "")
                track_data["countryAvailability"] = self._get_country_availability(
                    package_name, edit_id, track_name
                )
            return {"tracks": tracks}
        finally:
            self._delete_edit(package_name, edit_id)

    def get_track(self, package_name: str, track: str) -> Dict[str, Any]:
        """Read-only fetch of a single track, including country availability."""
        edit_id = self._create_edit(package_name)
        try:
            track_data = self._get_track(package_name, edit_id, track)
            track_data["countryAvailability"] = self._get_country_availability(
                package_name, edit_id, track
            )
            return track_data
        finally:
            self._delete_edit(package_name, edit_id)

    def create_release(
        self,
        package_name: str,
        track: str,
        version_codes: List[int],
        rollout_percentage: float = 10.0,
        release_name: Optional[str] = None,
        release_notes: Optional[List[Dict[str, str]]] = None,
        status: str = "draft",
        country_codes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create or replace a release on the given track.

        status: "draft" | "inProgress" | "halted" | "completed"
        rollout_percentage: used when status is "inProgress" (default 10%).
        country_codes: if provided, restricts the release to those countries.
        """
        release: Dict[str, Any] = {
            "versionCodes": [str(vc) for vc in version_codes],
            "status": status,
        }
        if status == "inProgress":
            if rollout_percentage >= 100:
                release["status"] = "completed"
            else:
                release["userFraction"] = round(rollout_percentage / 100.0, 4)
        if release_name:
            release["name"] = release_name
        if release_notes:
            release["releaseNotes"] = release_notes

        edit_id = self._create_edit(package_name)
        try:
            updated_track = self._update_track(
                package_name, edit_id, track, {"track": track, "releases": [release]}
            )
            if country_codes is not None:
                self.service.edits().countryavailability().update(
                    packageName=package_name,
                    editId=edit_id,
                    track=track,
                    body={"countries": [{"countryCode": cc} for cc in country_codes]},
                ).execute()
            commit = self._commit_edit(package_name, edit_id)
            return {"track": updated_track, "commit": commit}
        except Exception:
            self._delete_edit(package_name, edit_id)
            raise

    def update_release(
        self,
        package_name: str,
        track: str,
        rollout_percentage: Optional[float] = None,
        version_codes: Optional[List[int]] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing release's rollout percentage and/or status.

        Targets the first matching release (by version_codes if provided,
        otherwise the first inProgress/halted/draft/completed release).
        """
        if rollout_percentage is not None and not (0 < rollout_percentage <= 100):
            raise ValueError("rollout_percentage must be > 0 and <= 100.")

        edit_id = self._create_edit(package_name)
        try:
            track_data = self._get_track(package_name, edit_id, track)
            releases: List[Dict[str, Any]] = track_data.get("releases", [])
            target_vcs = {str(vc) for vc in version_codes} if version_codes else None

            updated = False
            for release in releases:
                if target_vcs:
                    if not set(release.get("versionCodes", [])).intersection(target_vcs):
                        continue
                if status:
                    release["status"] = status
                if rollout_percentage is not None:
                    if rollout_percentage >= 100:
                        release["status"] = "completed"
                        release.pop("userFraction", None)
                    else:
                        if not status:
                            release["status"] = "inProgress"
                        release["userFraction"] = round(rollout_percentage / 100.0, 4)
                updated = True
                break

            if not updated:
                raise ValueError(
                    f"No matching release found in the '{track}' track."
                )

            updated_track = self._update_track(
                package_name, edit_id, track, {"track": track, "releases": releases}
            )
            commit = self._commit_edit(package_name, edit_id)
            return {"track": updated_track, "commit": commit}
        except Exception:
            self._delete_edit(package_name, edit_id)
            raise

    def promote_release(
        self,
        package_name: str,
        from_track: str,
        to_track: str,
        version_codes: List[int],
        rollout_percentage: float = 10.0,
        release_name: Optional[str] = None,
        release_notes: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Copy a release from one track to another.

        Release notes and name are inherited from the source release unless
        overridden. rollout_percentage applies when to_track is production.
        """
        if not (0 < rollout_percentage <= 100):
            raise ValueError("rollout_percentage must be > 0 and <= 100.")

        edit_id = self._create_edit(package_name)
        try:
            src_releases = self._get_track(
                package_name, edit_id, from_track
            ).get("releases", [])
            target_vcs = {str(vc) for vc in version_codes}
            src = next(
                (
                    r for r in src_releases
                    if set(r.get("versionCodes", [])).intersection(target_vcs)
                ),
                None,
            )
            notes = release_notes or (src.get("releaseNotes") if src else None)
            name = release_name or (src.get("name") if src else None)

            release: Dict[str, Any] = {
                "versionCodes": [str(vc) for vc in version_codes],
                "status": "completed" if rollout_percentage >= 100 else "inProgress",
            }
            if rollout_percentage < 100:
                release["userFraction"] = round(rollout_percentage / 100.0, 4)
            if name:
                release["name"] = name
            if notes:
                release["releaseNotes"] = notes

            updated_track = self._update_track(
                package_name, edit_id, to_track,
                {"track": to_track, "releases": [release]}
            )
            commit = self._commit_edit(package_name, edit_id)
            return {"track": updated_track, "commit": commit}
        except Exception:
            self._delete_edit(package_name, edit_id)
            raise

    # -----------------------------------------------------------------------
    # Public: Artifact Management
    # -----------------------------------------------------------------------

    def list_artifacts(self, package_name: str) -> Dict[str, Any]:
        """List all APKs and AABs currently known for the app."""
        edit_id = self._create_edit(package_name)
        try:
            apks = self.service.edits().apks().list(
                packageName=package_name, editId=edit_id
            ).execute().get("apks", [])
            bundles = self.service.edits().bundles().list(
                packageName=package_name, editId=edit_id
            ).execute().get("bundles", [])
            return {"apks": apks, "bundles": bundles}
        finally:
            self._delete_edit(package_name, edit_id)

    def upload_artifact(
        self,
        package_name: str,
        file_path: str,
        track: str,
        rollout_percentage: Optional[float] = None,
        release_name: Optional[str] = None,
        release_notes: Optional[List[Dict[str, str]]] = None,
        status: str = "draft",
    ) -> Dict[str, Any]:
        """Upload an APK or AAB and create a release on the given track.

        File type is inferred from the extension (.apk or .aab).
        Everything (upload + track assignment) happens in a single edit.
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".apk":
            mime = APK_MIME
            artifact_type = "apk"
        elif ext == ".aab":
            mime = BUNDLE_MIME
            artifact_type = "bundle"
        else:
            raise ValueError(f"Unrecognized file extension '{ext}'. Use .apk or .aab.")

        media = MediaFileUpload(file_path, mimetype=mime, resumable=True)
        edit_id = self._create_edit(package_name)
        try:
            if artifact_type == "apk":
                artifact = self.service.edits().apks().upload(
                    packageName=package_name, editId=edit_id, media_body=media
                ).execute()
            else:
                artifact = self.service.edits().bundles().upload(
                    packageName=package_name, editId=edit_id, media_body=media
                ).execute()

            version_code = artifact["versionCode"]
            release: Dict[str, Any] = {
                "versionCodes": [str(version_code)],
                "status": status,
            }
            if status == "inProgress" and rollout_percentage is not None:
                if rollout_percentage >= 100:
                    release["status"] = "completed"
                else:
                    release["userFraction"] = round(rollout_percentage / 100.0, 4)
            if release_name:
                release["name"] = release_name
            if release_notes:
                release["releaseNotes"] = release_notes

            updated_track = self._update_track(
                package_name, edit_id, track, {"track": track, "releases": [release]}
            )
            commit = self._commit_edit(package_name, edit_id)
            return {
                "versionCode": version_code,
                "artifactType": artifact_type,
                "artifact": artifact,
                "track": updated_track,
                "commit": commit,
            }
        except Exception:
            self._delete_edit(package_name, edit_id)
            raise

    def upload_to_internal_sharing(
        self,
        package_name: str,
        file_path: str,
    ) -> Dict[str, Any]:
        """Upload an APK or AAB to Internal App Sharing.

        Returns a shareable download URL. Does NOT assign the build to any
        track — use this for quick tester distribution without a Play track.
        File type is inferred from the extension (.apk or .aab).
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".apk":
            mime = APK_MIME
            artifact_type = "apk"
        elif ext == ".aab":
            mime = BUNDLE_MIME
            artifact_type = "bundle"
        else:
            raise ValueError(f"Unrecognized file extension '{ext}'. Use .apk or .aab.")

        media = MediaFileUpload(file_path, mimetype=mime, resumable=False)
        if artifact_type == "apk":
            result = self.service.internalappsharingartifacts().uploadapk(
                packageName=package_name, media_body=media
            ).execute()
        else:
            result = self.service.internalappsharingartifacts().uploadbundle(
                packageName=package_name, media_body=media
            ).execute()
        result["artifactType"] = artifact_type
        return result

    # -----------------------------------------------------------------------
    # Public: Tester Management
    # -----------------------------------------------------------------------

    def publish_managed_release(self, package_name: str) -> Dict[str, Any]:
        """Send approved changes live when Managed Publishing is enabled.

        With Managed Publishing on, committed edits are held pending manual
        approval and do NOT go live automatically. This calls the
        managedPublishing.publish endpoint — equivalent to clicking
        "Send changes live" in Google Play Console.

        Has no effect if Managed Publishing is not enabled.
        """
        return (
            self.service.managedPublishing()
            .publish(packageName=package_name, body={})
            .execute()
        )

    def get_testers(self, package_name: str, track: str) -> Dict[str, Any]:
        """Get tester emails and Google Groups for an internal/closed testing track."""
        edit_id = self._create_edit(package_name)
        try:
            return self.service.edits().testers().get(
                packageName=package_name, editId=edit_id, track=track
            ).execute()
        finally:
            self._delete_edit(package_name, edit_id)

    def update_testers(
        self,
        package_name: str,
        track: str,
        emails: Optional[List[str]] = None,
        google_groups: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Replace the tester list for an internal/closed testing track.

        This is a full replacement — existing testers not in the new list
        will lose access.
        """
        body: Dict[str, Any] = {}
        if emails is not None:
            body["testers"] = emails
        if google_groups is not None:
            body["googleGroups"] = google_groups

        edit_id = self._create_edit(package_name)
        try:
            result = self.service.edits().testers().update(
                packageName=package_name, editId=edit_id, track=track, body=body
            ).execute()
            commit = self._commit_edit(package_name, edit_id)
            return {"testers": result, "commit": commit}
        except Exception:
            self._delete_edit(package_name, edit_id)
            raise


class ReportingClient:
    """Wraps the Google Play Developer Reporting API v1beta1."""

    def __init__(self, credentials_file: Optional[str] = None) -> None:
        self.creds = _get_credentials([REPORTING_SCOPE], credentials_file)
        self.session = AuthorizedSession(self.creds)

    def _query_metric_set(
        self,
        package_name: str,
        metric_set: str,
        metrics: List[str],
        days: int,
        version_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        # API data lags by ~1 day; using today as endTime returns 400.
        end = datetime.now(timezone.utc) - timedelta(days=1)
        start = end - timedelta(days=days)

        def _date(dt: datetime) -> Dict[str, int]:
            return {"year": dt.year, "month": dt.month, "day": dt.day}

        body: Dict[str, Any] = {
            "timelineSpec": {
                "aggregationPeriod": "DAILY",
                "startTime": _date(start),
                "endTime": _date(end),
            },
            "metrics": metrics,
            "dimensions": ["versionCode"],
            "pageSize": days * 10,
        }
        if version_code:
            body["filter"] = f'versionCode = "{version_code}"'

        url = f"{REPORTING_BASE_URL}/apps/{package_name}/{metric_set}:query"
        resp = self.session.post(url, json=body)
        resp.raise_for_status()
        return resp.json()

    def query_crash_rate(
        self,
        package_name: str,
        days: int = 7,
        version_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._query_metric_set(
            package_name,
            "crashRateMetricSet",
            ["crashRate", "userPerceivedCrashRate", "distinctUsers"],
            days,
            version_code,
        )

    def query_anr_rate(
        self,
        package_name: str,
        days: int = 7,
        version_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._query_metric_set(
            package_name,
            "anrRateMetricSet",
            ["anrRate", "userPerceivedAnrRate", "distinctUsers"],
            days,
            version_code,
        )

    def list_available_metrics(self, package_name: str) -> Dict[str, Any]:
        """List available metric sets for the app (for debugging)."""
        url = f"{REPORTING_BASE_URL}/apps/{package_name}/crashRateMetricSet"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()
