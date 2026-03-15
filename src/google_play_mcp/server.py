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
                # decimalValue is a Decimal message serialized as {"value": "0.001234"}
                if isinstance(val, dict):
                    val = val.get("value")
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    val = None
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
    """List all release tracks with their current releases.

    Returns tracks (internal, alpha, beta, production) with rollout
    percentages, statuses, and country availability.

    Args:
        package_name: Package name, e.g. com.example.myapp
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
    """Get detailed info for a specific release track.

    Returns releases with status, rollout %, version codes, release notes,
    and country availability.

    Args:
        package_name: Package name, e.g. com.example.myapp
        track: "internal", "alpha", "beta", or "production". Default "production".
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
    """Create or replace a release on a track.

    NOTE: With Managed Publishing enabled, the edit is held pending approval.
    Call publish_managed_release to send live.

    Args:
        package_name: Package name, e.g. com.example.myapp
        track: "internal", "alpha", "beta", or "production".
        version_codes: Version codes to include, e.g. [1234].
        rollout_percentage: Rollout % when status is "inProgress". Default 10%.
        status: "draft" (default), "inProgress" (staged), "halted", or "completed".
        release_name: Optional human-readable name.
        release_notes: Optional {lang: text} dict, e.g. {"en-US": "Bug fixes"}.
        country_codes: Optional ISO 3166-1 alpha-2 codes. Empty list removes restrictions.
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
    """Update rollout percentage and/or status of an existing release.

    Examples: increase rollout (rollout_percentage=50), complete (=100),
    halt (status="halted"), resume (status="inProgress").

    NOTE: With Managed Publishing enabled, changes are held pending approval.
    Call publish_managed_release to send live.

    Args:
        package_name: Package name, e.g. com.example.myapp
        track: Track to update. Default "production".
        rollout_percentage: New rollout % (0–100). Pass 100 to complete.
        status: "inProgress", "halted", "completed", or "draft".
        version_codes: Filter to release containing these codes. Default: first release found.
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

    Copies version codes from source to destination. Common: internal→alpha→beta→production.
    Release notes/name are inherited unless overridden.

    Args:
        package_name: Package name, e.g. com.example.myapp
        from_track: Source — "internal", "alpha", or "beta".
        to_track: Destination — "alpha", "beta", or "production".
        version_codes: Version codes to promote, e.g. [1234].
        rollout_percentage: Rollout % at destination. Default 10%. Use 100 for full release.
        release_name: Optional name override.
        release_notes: Optional {lang: text} override, e.g. {"en-US": "New features"}.
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

    Call after changes committed via create_release/update_release/promote_release
    have been reviewed in Play Console. No-op if Managed Publishing is off.

    Args:
        package_name: Package name, e.g. com.example.myapp
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

    Returns version codes and SHA hashes. Useful for finding version codes
    available to assign to a track.

    Args:
        package_name: Package name, e.g. com.example.myapp
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

    File type auto-detected from extension (.apk/.aab). Upload and track
    assignment are atomic.

    Args:
        package_name: Package name, e.g. com.example.myapp
        file_path: Absolute local path to the APK or AAB.
        track: "internal" (default), "alpha", "beta", or "production".
        status: "draft" (default), "inProgress", or "completed".
        rollout_percentage: Rollout % when status is "inProgress". Default 10%.
        release_name: Optional human-readable name.
        release_notes: Optional {lang: text} dict, e.g. {"en-US": "Initial release"}.
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
    """Upload APK or AAB to Internal App Sharing and get a shareable link.

    Shares a build via URL without assigning it to a track. Ideal for quick
    one-off testing. File type auto-detected from extension (.apk/.aab).

    Args:
        package_name: Package name, e.g. com.example.myapp
        file_path: Absolute local path to the APK or AAB.
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
    """Get tester emails and Google Groups for an internal or alpha track.

    Args:
        package_name: Package name, e.g. com.example.myapp
        track: "internal" (default) or "alpha".
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
    """Replace the tester list for an internal or alpha track.

    WARNING: Full replacement — omitted testers lose access.
    Call get_testers first to preserve existing testers.

    Args:
        package_name: Package name, e.g. com.example.myapp
        track: "internal" (default) or "alpha".
        emails: Tester email addresses. Empty list removes all individuals.
        google_groups: Google Group addresses. Empty list removes all groups.
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
    """Fetch user-perceived crash rate from Android Vitals.

    Returns daily crashRate, userPerceivedCrashRate, and distinctUsers by
    version code. Bad behavior threshold: userPerceivedCrashRate > 1.09%
    may cause Play Store ranking penalties.

    Args:
        package_name: Package name, e.g. com.example.myapp
        days: Past days to include (default 7, max 30).
        version_code: Optional version code filter.
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

    Returns daily anrRate, userPerceivedAnrRate, and distinctUsers by version
    code. Bad behavior threshold: userPerceivedAnrRate > 0.47% may cause
    Play Store ranking penalties.

    Args:
        package_name: Package name, e.g. com.example.myapp
        days: Past days to include (default 7, max 30).
        version_code: Optional version code filter.
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
# Tool: get_wakelock_rate
# ---------------------------------------------------------------------------

@mcp.tool()
def get_wakelock_rate(
    package_name: str,
    days: int = 7,
    version_code: str = "",
) -> str:
    """Fetch stuck background wake lock rate from Android Vitals.

    Returns daily stuckBackgroundWakelockRate and distinctUsers by version
    code. Excessive wakelock holding (>1 hour in background) may be penalized.

    Args:
        package_name: Package name, e.g. com.example.myapp
        days: Past days to include (default 7, max 30).
        version_code: Optional version code filter.
    """
    days = max(1, min(days, 30))
    try:
        raw = _reporting().query_wakelock_rate(
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
                        "No stuck wakelock data available. Data may lag up to 2 days "
                        "or the app has no wakelock violations in this period."
                    ),
                    "rows": [],
                },
                indent=2,
            )
        return json.dumps(
            {
                "packageName": package_name,
                "periodDays": days,
                "totalRows": len(rows),
                "rows": rows,
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_wakeup_rate
# ---------------------------------------------------------------------------

@mcp.tool()
def get_wakeup_rate(
    package_name: str,
    days: int = 7,
    version_code: str = "",
) -> str:
    """Fetch excessive CPU wakeup rate from Android Vitals.

    Returns daily excessiveWakeupRate and distinctUsers by version code.
    Frequent CPU wakeups above platform thresholds may be penalized.

    Args:
        package_name: Package name, e.g. com.example.myapp
        days: Past days to include (default 7, max 30).
        version_code: Optional version code filter.
    """
    days = max(1, min(days, 30))
    try:
        raw = _reporting().query_wakeup_rate(
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
                        "No excessive wakeup data available. Data may lag up to 2 days "
                        "or the app has no wakeup violations in this period."
                    ),
                    "rows": [],
                },
                indent=2,
            )
        return json.dumps(
            {
                "packageName": package_name,
                "periodDays": days,
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
    """Get combined Android Vitals: crash rate and ANR rate per version code.

    Returns averages over the period with threshold flags.
    Thresholds: userPerceivedCrashRate > 1.09%, userPerceivedAnrRate > 0.47%.

    Args:
        package_name: Package name, e.g. com.example.myapp
        days: Past days to include (default 7, max 30).
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
                if isinstance(row.get(rate_key), (int, float)):
                    entry["values"].append(row[rate_key])
                if isinstance(row.get(perceived_key), (int, float)):
                    entry["perceived"].append(row[perceived_key])
                if isinstance(row.get("distinctUsers"), (int, float)):
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
