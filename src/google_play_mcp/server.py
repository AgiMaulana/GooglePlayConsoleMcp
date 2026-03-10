"""Google Play Console MCP Server.

Exposes Google Play Console operations as MCP tools so AI assistants
(Claude, etc.) can manage the full app release lifecycle programmatically.
"""

import json
import os
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .client import PublisherClient, ReportingClient

load_dotenv()

mcp = FastMCP(
    "Google Play Console MCP",
    instructions=(
        "Tools for managing the full Google Play Store release lifecycle: "
        "uploading artifacts, creating and promoting releases across all tracks "
        "(internal, alpha/closed, beta/open, production), managing testers, "
        "adjusting rollout percentages, and fetching Android Vitals (crash and ANR rates)."
    ),
)

_CREDS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")


def _publisher() -> PublisherClient:
    return PublisherClient(_CREDS)


def _reporting() -> ReportingClient:
    return ReportingClient(_CREDS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_release(release: dict) -> dict:
    fraction = release.get("userFraction")
    rollout_pct = round(fraction * 100, 2) if fraction is not None else (
        100.0 if release.get("status") == "completed" else None
    )
    return {
        "name": release.get("name"),
        "versionCodes": release.get("versionCodes", []),
        "status": release.get("status"),
        "rolloutPercentage": rollout_pct,
        "releaseNotes": release.get("releaseNotes", []),
    }


def _format_track(track_data: dict) -> dict:
    return {
        "track": track_data.get("track"),
        "releases": [_format_release(r) for r in track_data.get("releases", [])],
        "countryAvailability": track_data.get("countryAvailability", {}),
    }


def _notes_from_dict(notes_dict: Optional[dict]) -> Optional[list]:
    """Convert {lang: text} dict to API release notes format."""
    if not notes_dict:
        return None
    return [{"language": lang, "text": text} for lang, text in notes_dict.items()]


def _parse_reporting_rows(rows: list) -> list:
    parsed = []
    for row in rows:
        dims = {
            d.get("dimension"): d.get("stringValue") or d.get("int64Value")
            for d in row.get("dimensions", [])
        }
        metrics: dict = {}
        for m in row.get("metrics", []):
            name = m.get("metric")
            val = m.get("decimalValue") or m.get("int64Value")
            if val is not None:
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    pass
            metrics[name] = val
        parsed.append({
            "date": row.get("startTime", {}),
            "versionCode": dims.get("versionCode"),
            **metrics,
        })
    return parsed


# ---------------------------------------------------------------------------
# Tool: list_tracks
# ---------------------------------------------------------------------------

@mcp.tool()
def list_tracks(package_name: str) -> str:
    """List all release tracks and their current releases.

    Returns all tracks (internal, alpha/closed, beta/open, production) with
    their releases, rollout percentages, statuses, and country availability.

    Args:
        package_name: App package name, e.g. com.example.myapp
    """
    try:
        data = _publisher().list_tracks(package_name)
        tracks = [_format_track(t) for t in data.get("tracks", [])]
        return json.dumps(
            {"packageName": package_name, "tracks": tracks},
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_track_info
# ---------------------------------------------------------------------------

@mcp.tool()
def get_track_info(
    package_name: str,
    track: str = "production",
) -> str:
    """Get detailed information for a specific release track.

    Returns releases with status, rollout percentage, version codes, release
    notes, and country availability for the track.

    Args:
        package_name: App package name, e.g. com.example.myapp
        track: Track name — "internal", "alpha", "beta", or "production".
            Defaults to "production".
    """
    try:
        track_data = _publisher().get_track(package_name, track)
        formatted = _format_track(track_data)
        releases = formatted["releases"]

        statuses = {r["status"] for r in releases if r["status"]}
        if "inProgress" in statuses:
            summary = "Staged rollout in progress."
        elif "draft" in statuses:
            summary = "Release is in draft / under Google Play review."
        elif "halted" in statuses:
            summary = "Rollout is halted."
        elif statuses == {"completed"}:
            summary = "Release fully rolled out (100%)."
        else:
            summary = f"Status: {', '.join(statuses)}" if statuses else "No active releases."

        return json.dumps(
            {
                "packageName": package_name,
                "summary": summary,
                **formatted,
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: create_release
# ---------------------------------------------------------------------------

@mcp.tool()
def create_release(
    package_name: str,
    track: str,
    version_codes: list[int],
    rollout_percentage: float = 10.0,
    status: str = "draft",
    release_name: str = "",
    release_notes: Optional[dict] = None,
    country_codes: Optional[list[str]] = None,
) -> str:
    """Create or replace a release on any track.

    Use this to publish a build to internal testing, closed testing (alpha),
    open testing (beta), or production. The release replaces any existing
    release on the track for the given version codes.

    Args:
        package_name: App package name, e.g. com.example.myapp
        track: Target track — "internal", "alpha", "beta", or "production".
        version_codes: List of version codes to include, e.g. [1234].
        rollout_percentage: Percentage of users to roll out to when status is
            "inProgress". Default 10%. Ignored for other statuses.
        status: Release status — "draft" (default, saves without releasing),
            "inProgress" (staged rollout using rollout_percentage),
            "halted", or "completed" (release to all users immediately).
        release_name: Optional human-readable release name.
        release_notes: Optional dict of release notes keyed by language code,
            e.g. {"en-US": "Bug fixes", "fr-FR": "Corrections de bugs"}.
        country_codes: Optional list of ISO 3166-1 alpha-2 country codes to
            restrict availability, e.g. ["US", "GB"]. Pass an empty list to
            remove country restrictions.

    NOTE: If Managed Publishing is enabled in Google Play Console, this edit
    will be committed but held pending approval — it will NOT go live
    automatically. Call publish_managed_release after approval to send it live.
    """
    try:
        notes = _notes_from_dict(release_notes)
        result = _publisher().create_release(
            package_name=package_name,
            track=track,
            version_codes=version_codes,
            rollout_percentage=rollout_percentage,
            release_name=release_name or None,
            release_notes=notes,
            status=status,
            country_codes=country_codes,
        )
        return json.dumps(
            {
                "success": True,
                "message": (
                    f"Release created on '{track}' track with status '{status}'."
                ),
                "track": _format_track(result["track"]),
                "editId": result.get("commit", {}).get("editId"),
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: update_release
# ---------------------------------------------------------------------------

@mcp.tool()
def update_release(
    package_name: str,
    track: str = "production",
    rollout_percentage: Optional[float] = None,
    status: Optional[str] = None,
    version_codes: Optional[list[int]] = None,
) -> str:
    """Update the rollout percentage and/or status of an existing release.

    Use this to:
    - Increase rollout: update_release(pkg, rollout_percentage=50)
    - Complete rollout: update_release(pkg, rollout_percentage=100)
    - Halt a rollout: update_release(pkg, status="halted")
    - Resume a halted rollout: update_release(pkg, status="inProgress")

    NOTE: If Managed Publishing is enabled in Google Play Console, this edit
    will be committed but held pending approval — it will NOT go live
    automatically. Call publish_managed_release after approval to send it live.

    Args:
        package_name: App package name, e.g. com.example.myapp
        track: Track to update. Defaults to "production".
        rollout_percentage: New rollout percentage (0 < value <= 100). Pass
            100 to complete the rollout for all users.
        status: New status — "inProgress", "halted", "completed", or "draft".
            If both rollout_percentage and status are provided, status takes
            precedence for the status field.
        version_codes: Optional filter — only updates a release containing
            these version codes. If omitted, updates the first release found.
    """
    try:
        result = _publisher().update_release(
            package_name=package_name,
            track=track,
            rollout_percentage=rollout_percentage,
            version_codes=version_codes,
            status=status,
        )
        return json.dumps(
            {
                "success": True,
                "message": "Release updated successfully.",
                "track": _format_track(result["track"]),
                "editId": result.get("commit", {}).get("editId"),
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: promote_release
# ---------------------------------------------------------------------------

@mcp.tool()
def promote_release(
    package_name: str,
    from_track: str,
    to_track: str,
    version_codes: list[int],
    rollout_percentage: float = 10.0,
    release_name: str = "",
    release_notes: Optional[dict] = None,
) -> str:
    """Promote a release from one track to another.

    Copies the specified version codes from the source track to the
    destination track. Release notes and name are inherited from the
    source release unless explicitly overridden.

    Common flows:
    - internal → alpha (closed testing)
    - alpha → beta (open testing)
    - beta → production (with staged rollout)
    - internal → production

    Args:
        package_name: App package name, e.g. com.example.myapp
        from_track: Source track — "internal", "alpha", or "beta".
        to_track: Destination track — "alpha", "beta", or "production".
        version_codes: Version codes to promote, e.g. [1234].
        rollout_percentage: Rollout percentage for the destination track.
            Default 10%. Use 100 for an immediate full release.
        release_name: Optional override for the release name.
        release_notes: Optional override for release notes as a dict keyed
            by language code, e.g. {"en-US": "New features"}.
    """
    try:
        notes = _notes_from_dict(release_notes)
        result = _publisher().promote_release(
            package_name=package_name,
            from_track=from_track,
            to_track=to_track,
            version_codes=version_codes,
            rollout_percentage=rollout_percentage,
            release_name=release_name or None,
            release_notes=notes,
        )
        return json.dumps(
            {
                "success": True,
                "message": (
                    f"Version codes {version_codes} promoted from '{from_track}' "
                    f"to '{to_track}' at {rollout_percentage}% rollout."
                ),
                "track": _format_track(result["track"]),
                "editId": result.get("commit", {}).get("editId"),
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: publish_managed_release
# ---------------------------------------------------------------------------

@mcp.tool()
def publish_managed_release(package_name: str) -> str:
    """Send approved changes live when Managed Publishing is enabled.

    If Managed Publishing is enabled in Google Play Console, edits committed
    via create_release, update_release, or promote_release are held pending
    approval and will NOT go live automatically. Call this tool after your
    changes have been reviewed and approved in Play Console to make them live.

    This is equivalent to clicking "Send changes live" in Google Play Console.
    Has no effect if Managed Publishing is not enabled.

    Args:
        package_name: App package name, e.g. com.example.myapp
    """
    try:
        _publisher().publish_managed_release(package_name)
        return json.dumps(
            {
                "success": True,
                "message": "Changes sent live successfully via Managed Publishing.",
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: list_artifacts
# ---------------------------------------------------------------------------

@mcp.tool()
def list_artifacts(package_name: str) -> str:
    """List all APKs and AABs uploaded to the app.

    Returns version codes, SHA hashes, and upload details for all artifacts.
    Useful for finding which version codes are available to assign to a track.

    Args:
        package_name: App package name, e.g. com.example.myapp
    """
    try:
        data = _publisher().list_artifacts(package_name)
        apks = [
            {
                "type": "apk",
                "versionCode": a.get("versionCode"),
                "sha1": a.get("binary", {}).get("sha1"),
                "sha256": a.get("binary", {}).get("sha256"),
            }
            for a in data.get("apks", [])
        ]
        bundles = [
            {
                "type": "bundle",
                "versionCode": b.get("versionCode"),
                "sha256": b.get("sha256"),
            }
            for b in data.get("bundles", [])
        ]
        all_artifacts = sorted(
            apks + bundles,
            key=lambda x: x.get("versionCode") or 0,
            reverse=True,
        )
        return json.dumps(
            {
                "packageName": package_name,
                "totalCount": len(all_artifacts),
                "artifacts": all_artifacts,
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: upload_artifact
# ---------------------------------------------------------------------------

@mcp.tool()
def upload_artifact(
    package_name: str,
    file_path: str,
    track: str = "internal",
    status: str = "draft",
    rollout_percentage: float = 10.0,
    release_name: str = "",
    release_notes: Optional[dict] = None,
) -> str:
    """Upload an APK or AAB and create a release on the given track.

    The file type is auto-detected from the extension (.apk or .aab).
    The upload and track assignment happen in a single atomic operation.

    Args:
        package_name: App package name, e.g. com.example.myapp
        file_path: Absolute local path to the APK or AAB file.
        track: Track to release on — "internal" (default), "alpha", "beta",
            or "production".
        status: Release status — "draft" (default), "inProgress", or
            "completed". For production with staged rollout use "inProgress"
            with rollout_percentage.
        rollout_percentage: Rollout percentage when status is "inProgress".
            Default 10%.
        release_name: Optional human-readable release name.
        release_notes: Optional dict of release notes keyed by language code,
            e.g. {"en-US": "Initial release"}.
    """
    try:
        notes = _notes_from_dict(release_notes)
        result = _publisher().upload_artifact(
            package_name=package_name,
            file_path=file_path,
            track=track,
            rollout_percentage=rollout_percentage if status == "inProgress" else None,
            release_name=release_name or None,
            release_notes=notes,
            status=status,
        )
        return json.dumps(
            {
                "success": True,
                "message": (
                    f"Uploaded {result['artifactType'].upper()} with version code "
                    f"{result['versionCode']} to '{track}' track."
                ),
                "versionCode": result["versionCode"],
                "artifactType": result["artifactType"],
                "track": _format_track(result["track"]),
                "editId": result.get("commit", {}).get("editId"),
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: upload_to_internal_sharing
# ---------------------------------------------------------------------------

@mcp.tool()
def upload_to_internal_sharing(
    package_name: str,
    file_path: str,
) -> str:
    """Upload an APK or AAB to Internal App Sharing and get a shareable link.

    Internal App Sharing lets you share a specific build directly with testers
    via a URL, without assigning it to any release track. Ideal for quick
    one-off testing. File type is auto-detected from the extension (.apk/.aab).

    Args:
        package_name: App package name, e.g. com.example.myapp
        file_path: Absolute local path to the APK or AAB file.
    """
    try:
        result = _publisher().upload_to_internal_sharing(
            package_name=package_name,
            file_path=file_path,
        )
        return json.dumps(
            {
                "success": True,
                "downloadUrl": result.get("downloadUrl"),
                "artifactType": result.get("artifactType"),
                "certificateFingerprint": result.get("certificateFingerprint"),
                "message": (
                    "Share the downloadUrl with testers. They must have Internal "
                    "App Sharing enabled in their Play Store settings."
                ),
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_testers
# ---------------------------------------------------------------------------

@mcp.tool()
def get_testers(
    package_name: str,
    track: str = "internal",
) -> str:
    """Get the list of testers for an internal or closed testing track.

    Returns tester email addresses and Google Groups configured for the track.
    Only applicable to "internal" and closed testing (alpha) tracks.

    Args:
        package_name: App package name, e.g. com.example.myapp
        track: Track to query — "internal" (default) or "alpha".
    """
    try:
        data = _publisher().get_testers(package_name, track)
        return json.dumps(
            {
                "packageName": package_name,
                "track": track,
                "testers": data.get("testers", []),
                "googleGroups": data.get("googleGroups", []),
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: update_testers
# ---------------------------------------------------------------------------

@mcp.tool()
def update_testers(
    package_name: str,
    track: str = "internal",
    emails: Optional[list[str]] = None,
    google_groups: Optional[list[str]] = None,
) -> str:
    """Replace the tester list for an internal or closed testing track.

    WARNING: This is a full replacement. Testers not included in the new
    list will lose access to the track. To add testers, first call
    get_testers to retrieve the current list and include them in the update.

    Only applicable to "internal" and closed testing (alpha) tracks.
    Open testing (beta) and production use rollout percentages instead.

    Args:
        package_name: App package name, e.g. com.example.myapp
        track: Track to update — "internal" (default) or "alpha".
        emails: List of tester email addresses. Pass an empty list to remove
            all individual testers.
        google_groups: List of Google Group email addresses for tester groups.
            Pass an empty list to remove all groups.
    """
    try:
        result = _publisher().update_testers(
            package_name=package_name,
            track=track,
            emails=emails,
            google_groups=google_groups,
        )
        testers = result.get("testers", {})
        return json.dumps(
            {
                "success": True,
                "message": f"Tester list updated for '{track}' track.",
                "track": track,
                "testers": testers.get("testers", []),
                "googleGroups": testers.get("googleGroups", []),
                "editId": result.get("commit", {}).get("editId"),
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_crash_rate
# ---------------------------------------------------------------------------

@mcp.tool()
def get_crash_rate(
    package_name: str,
    days: int = 7,
    version_code: str = "",
) -> str:
    """Fetch user-perceived crash rate for the app from Android Vitals.

    Uses the Google Play Developer Reporting API v1beta1.
    Returns daily crashRate, userPerceivedCrashRate, and distinctUsers
    broken down by version code for the requested period.

    Google's "bad behavior threshold" for user-perceived crash rate is ~1.09%.
    Apps exceeding this may be penalized in Play Store ranking.

    Args:
        package_name: App package name, e.g. com.example.myapp
        days: Number of past days to include (default 7, max 30).
        version_code: Optional single version code to filter results.
    """
    days = max(1, min(days, 30))
    try:
        raw = _reporting().query_crash_rate(
            package_name=package_name,
            days=days,
            version_code=version_code or None,
        )
        rows = _parse_reporting_rows(raw.get("rows", []))
        if not rows:
            return json.dumps(
                {
                    "packageName": package_name,
                    "message": (
                        "No crash data available. Data may lag up to 2 days "
                        "or the app has no crashes in this period."
                    ),
                    "rows": [],
                },
                indent=2,
            )
        return json.dumps(
            {
                "packageName": package_name,
                "periodDays": days,
                "badBehaviorThreshold": {"userPerceivedCrashRate": 0.0109},
                "totalRows": len(rows),
                "rows": rows,
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_anr_rate
# ---------------------------------------------------------------------------

@mcp.tool()
def get_anr_rate(
    package_name: str,
    days: int = 7,
    version_code: str = "",
) -> str:
    """Fetch ANR (Application Not Responding) rate from Android Vitals.

    Uses the Google Play Developer Reporting API v1beta1.
    Returns daily anrRate, userPerceivedAnrRate, and distinctUsers broken
    down by version code for the requested period.

    Google's "bad behavior threshold" for user-perceived ANR rate is ~0.47%.
    Apps exceeding this may be penalized in Play Store ranking.

    Args:
        package_name: App package name, e.g. com.example.myapp
        days: Number of past days to include (default 7, max 30).
        version_code: Optional single version code to filter results.
    """
    days = max(1, min(days, 30))
    try:
        raw = _reporting().query_anr_rate(
            package_name=package_name,
            days=days,
            version_code=version_code or None,
        )
        rows = _parse_reporting_rows(raw.get("rows", []))
        if not rows:
            return json.dumps(
                {
                    "packageName": package_name,
                    "message": (
                        "No ANR data available. Data may lag up to 2 days "
                        "or the app has no ANRs in this period."
                    ),
                    "rows": [],
                },
                indent=2,
            )
        return json.dumps(
            {
                "packageName": package_name,
                "periodDays": days,
                "badBehaviorThreshold": {"userPerceivedAnrRate": 0.0047},
                "totalRows": len(rows),
                "rows": rows,
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_vitals_summary
# ---------------------------------------------------------------------------

@mcp.tool()
def get_vitals_summary(
    package_name: str,
    days: int = 7,
) -> str:
    """Get a combined Android Vitals summary: crash rate and ANR rate.

    Fetches both crash and ANR metrics and returns a per-version-code
    summary with averages over the period. Highlights the latest version's
    rates against Google's bad behavior thresholds.

    Args:
        package_name: App package name, e.g. com.example.myapp
        days: Number of past days to include (default 7, max 30).
    """
    days = max(1, min(days, 30))
    try:
        crash_raw = _reporting().query_crash_rate(package_name, days)
        anr_raw = _reporting().query_anr_rate(package_name, days)

        crash_rows = _parse_reporting_rows(crash_raw.get("rows", []))
        anr_rows = _parse_reporting_rows(anr_raw.get("rows", []))

        # Aggregate by version code: average rates over the period
        def _aggregate(rows: list, rate_key: str, perceived_key: str) -> dict:
            by_version: dict = {}
            for row in rows:
                vc = row.get("versionCode") or "unknown"
                entry = by_version.setdefault(vc, {"values": [], "perceived": [], "users": []})
                if row.get(rate_key) is not None:
                    entry["values"].append(row[rate_key])
                if row.get(perceived_key) is not None:
                    entry["perceived"].append(row[perceived_key])
                if row.get("distinctUsers") is not None:
                    entry["users"].append(row["distinctUsers"])
            result = {}
            for vc, data in by_version.items():
                avg = lambda lst: round(sum(lst) / len(lst), 6) if lst else None
                result[vc] = {
                    f"avg_{rate_key}": avg(data["values"]),
                    f"avg_{perceived_key}": avg(data["perceived"]),
                    "avgDistinctUsers": avg(data["users"]),
                }
            return result

        crash_by_vc = _aggregate(crash_rows, "crashRate", "userPerceivedCrashRate")
        anr_by_vc = _aggregate(anr_rows, "anrRate", "userPerceivedAnrRate")

        all_vcs = sorted(
            set(crash_by_vc) | set(anr_by_vc),
            key=lambda x: int(x) if str(x).isdigit() else 0,
            reverse=True,
        )

        summary = []
        for vc in all_vcs:
            entry = {"versionCode": vc}
            entry.update(crash_by_vc.get(vc, {}))
            entry.update(anr_by_vc.get(vc, {}))
            # Flag if exceeding bad behavior thresholds
            crash_pct = entry.get("avg_userPerceivedCrashRate")
            anr_pct = entry.get("avg_userPerceivedAnrRate")
            entry["exceedsCrashThreshold"] = crash_pct is not None and crash_pct > 0.0109
            entry["exceedsAnrThreshold"] = anr_pct is not None and anr_pct > 0.0047
            summary.append(entry)

        latest = summary[0] if summary else None

        return json.dumps(
            {
                "packageName": package_name,
                "periodDays": days,
                "badBehaviorThresholds": {
                    "userPerceivedCrashRate": 0.0109,
                    "userPerceivedAnrRate": 0.0047,
                },
                "latestVersionSummary": latest,
                "allVersions": summary,
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Google Play Console MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for HTTP transport (default: 8080)",
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http", host="0.0.0.0", port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
