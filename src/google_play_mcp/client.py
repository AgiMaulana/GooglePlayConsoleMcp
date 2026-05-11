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

    def _commit_edit(
        self,
        package_name: str,
        edit_id: str,
        submit_for_review: bool = True,
    ) -> Dict[str, Any]:
        return self.service.edits().commit(
            packageName=package_name,
            editId=edit_id,
            changesNotSentForReview=not submit_for_review,
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
        submit_for_review: bool = True,
    ) -> Dict[str, Any]:
        """Create or replace a release on the given track.

        status: "draft" | "inProgress" | "halted" | "completed"
        rollout_percentage: used when status is "inProgress" (default 10%).
        country_codes: if provided, restricts the release to those countries.
        submit_for_review: if True, submits changes for Google Play review.
            Set to False to keep as draft (changesNotSentForReview=True).
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
            commit = self._commit_edit(package_name, edit_id, submit_for_review)
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
        submit_for_review: bool = True,
    ) -> Dict[str, Any]:
        """Update an existing release's rollout percentage and/or status.

        Targets the first matching release (by version_codes if provided,
        otherwise the first inProgress/halted/draft/completed release).

        When updating a release to completed/100%, filters out any other
        completed releases from the PUT body to avoid the API error:
        "Only one completed release is allowed."

        submit_for_review: if True, submits changes for Google Play review.
            Set to False to keep as draft (changesNotSentForReview=True).
        """
        if rollout_percentage is not None and not (0 < rollout_percentage <= 100):
            raise ValueError("rollout_percentage must be > 0 and <= 100.")

        edit_id = self._create_edit(package_name)
        try:
            track_data = self._get_track(package_name, edit_id, track)
            releases: List[Dict[str, Any]] = track_data.get("releases", [])

            # Normalize target version codes to strings for consistent comparison
            target_vcs = {str(vc) for vc in version_codes} if version_codes else None

            # Find the target release and clone it to avoid mutating the original
            target_release = None
            target_release_vcs: Optional[set] = None
            target_was_completed = False

            # When completing a rollout without version_codes, prefer inProgress release
            # to avoid targeting an already-completed release
            completing_without_vcs = (
                rollout_percentage is not None and rollout_percentage >= 100 and not version_codes
            )

            for release in releases:
                # Normalize version codes to strings for comparison
                release_vcs = {str(vc) for vc in release.get("versionCodes", [])}

                if target_vcs:
                    if not release_vcs.intersection(target_vcs):
                        continue

                # Skip completed releases when completing rollout without version_codes
                # This ensures we target inProgress releases instead
                if completing_without_vcs and release.get("status") == "completed":
                    continue

                # Found target release - clone it to avoid mutating original
                target_release = dict(release)
                target_release_vcs = release_vcs

                # Track if target is currently completed (before modification)
                target_was_completed = release.get("status") == "completed"
                break

            if not target_release:
                raise ValueError(
                    f"No matching release found in the '{track}' track."
                )

            # Apply updates to the cloned target release
            if status:
                target_release["status"] = status
            if rollout_percentage is not None:
                if rollout_percentage >= 100:
                    target_release["status"] = "completed"
                    target_release.pop("userFraction", None)
                else:
                    if not status:
                        target_release["status"] = "inProgress"
                    target_release["userFraction"] = round(rollout_percentage / 100.0, 4)

            # Determine if we need to filter completed releases
            target_is_becoming_completed = (
                status == "completed" or
                (rollout_percentage is not None and rollout_percentage >= 100)
            )
            should_filter = (
                target_is_becoming_completed or
                (target_was_completed and status and status != "completed")
            )

            # Rebuild the releases payload safely
            # This avoids mutating the original releases list and ensures proper filtering
            if should_filter:
                releases_for_put = []
                for r in releases:
                    # Normalize version codes for comparison
                    r_vcs = {str(vc) for vc in r.get("versionCodes", [])}

                    # Include the updated target release
                    if r_vcs == target_release_vcs:
                        releases_for_put.append(target_release)
                        continue

                    # Exclude other completed releases when:
                    # (1) target becomes completed, OR
                    # (2) target was completed and is being changed to non-completed
                    if should_filter and r.get("status") == "completed":
                        continue

                    releases_for_put.append(r)

                # Sanity check: ensure only one completed release in final payload
                completed_count = sum(
                    1 for r in releases_for_put if r.get("status") == "completed"
                )
                if completed_count > 1:
                    raise RuntimeError(
                        f"Internal error: {completed_count} completed releases in payload. "
                        "Expected at most 1 when target is completed."
                    )
            else:
                # When not filtering, still include the updated target release
                releases_for_put = []
                for r in releases:
                    r_vcs = {str(vc) for vc in r.get("versionCodes", [])}
                    if r_vcs == target_release_vcs:
                        releases_for_put.append(target_release)
                    else:
                        releases_for_put.append(r)

            updated_track = self._update_track(
                package_name, edit_id, track, {"track": track, "releases": releases_for_put}
            )
            commit = self._commit_edit(package_name, edit_id, submit_for_review)
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
        submit_for_review: bool = True,
    ) -> Dict[str, Any]:
        """Copy a release from one track to another.

        Release notes and name are inherited from the source release unless
        overridden. rollout_percentage applies when to_track is production.

        submit_for_review: if True, submits changes for Google Play review.
            Set to False to keep as draft (changesNotSentForReview=True).
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
            commit = self._commit_edit(package_name, edit_id, submit_for_review)
            return {"track": updated_track, "commit": commit}
        except Exception:
            self._delete_edit(package_name, edit_id)
            raise

    def commit_draft_release(
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
        """Commit changes without submitting for Google Play review.

        Equivalent to create_release with submit_for_review=False.
        Use this when you want to prepare changes but defer review submission.
        """
        return self.create_release(
            package_name=package_name,
            track=track,
            version_codes=version_codes,
            rollout_percentage=rollout_percentage,
            release_name=release_name,
            release_notes=release_notes,
            status=status,
            country_codes=country_codes,
            submit_for_review=False,
        )

    def submit_release_for_review(
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
        """Commit changes and submit immediately for Google Play review.

        Equivalent to create_release with submit_for_review=True.
        Use this when you want to submit changes for review in one step.
        """
        return self.create_release(
            package_name=package_name,
            track=track,
            version_codes=version_codes,
            rollout_percentage=rollout_percentage,
            release_name=release_name,
            release_notes=release_notes,
            status=status,
            country_codes=country_codes,
            submit_for_review=True,
        )

    def promote_draft_release(
        self,
        package_name: str,
        from_track: str,
        to_track: str,
        version_codes: List[int],
        rollout_percentage: float = 10.0,
        release_name: Optional[str] = None,
        release_notes: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Promote a release without submitting for Google Play review.

        Equivalent to promote_release with submit_for_review=False.
        Use this when you want to promote changes but defer review submission.
        """
        return self.promote_release(
            package_name=package_name,
            from_track=from_track,
            to_track=to_track,
            version_codes=version_codes,
            rollout_percentage=rollout_percentage,
            release_name=release_name,
            release_notes=release_notes,
            submit_for_review=False,
        )

    def promote_for_review(
        self,
        package_name: str,
        from_track: str,
        to_track: str,
        version_codes: List[int],
        rollout_percentage: float = 10.0,
        release_name: Optional[str] = None,
        release_notes: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Promote a release and submit immediately for Google Play review.

        Equivalent to promote_release with submit_for_review=True.
        """
        return self.promote_release(
            package_name=package_name,
            from_track=from_track,
            to_track=to_track,
            version_codes=version_codes,
            rollout_percentage=rollout_percentage,
            release_name=release_name,
            release_notes=release_notes,
            submit_for_review=True,
        )

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
        submit_for_review: bool = True,
    ) -> Dict[str, Any]:
        """Upload an APK or AAB and create a release on the given track.

        File type is inferred from the extension (.apk or .aab).
        Everything (upload + track assignment) happens in a single edit.

        submit_for_review: if True, submits changes for Google Play review.
            Set to False to keep as draft (changesNotSentForReview=True).
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
            commit = self._commit_edit(package_name, edit_id, submit_for_review)
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
        submit_for_review: bool = True,
    ) -> Dict[str, Any]:
        """Replace the tester list for an internal/closed testing track.

        This is a full replacement — existing testers not in the new list
        will lose access.

        submit_for_review: if True, submits changes for Google Play review.
            Set to False to keep as draft (changesNotSentForReview=True).
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
            commit = self._commit_edit(package_name, edit_id, submit_for_review)
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
            "vitals/crashrate",
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
            "vitals/anrrate",
            ["anrRate", "userPerceivedAnrRate", "distinctUsers"],
            days,
            version_code,
        )

    def query_wakelock_rate(
        self,
        package_name: str,
        days: int = 7,
        version_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._query_metric_set(
            package_name,
            "vitals/stuckbackgroundwakelockrate",
            ["stuckBackgroundWakelockRate", "distinctUsers"],
            days,
            version_code,
        )

    def query_wakeup_rate(
        self,
        package_name: str,
        days: int = 7,
        version_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._query_metric_set(
            package_name,
            "vitals/excessivewakeuprate",
            ["excessiveWakeupRate", "distinctUsers"],
            days,
            version_code,
        )

    def list_available_metrics(self, package_name: str) -> Dict[str, Any]:
        """List available metric sets for the app (for debugging)."""
        url = f"{REPORTING_BASE_URL}/apps/{package_name}/crashRateMetricSet"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()
