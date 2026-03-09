"""Google Play Console MCP Server.

Exposes Google Play Console operations as MCP tools so AI assistants
(Claude, etc.) can manage production releases programmatically.
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
        "Tools for managing Google Play Store production releases: "
        "promoting builds, adjusting rollout percentages, checking review "
        "status, and fetching crash-rate vitals."
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
    """Return a clean summary dict for a single release."""
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
    }


# ---------------------------------------------------------------------------
# Tool: promote_to_production
# ---------------------------------------------------------------------------

@mcp.tool()
def promote_to_production(
    package_name: str,
    version_codes: list[int],
    rollout_percentage: float,
    release_name: str = "",
    release_notes_en: str = "",
) -> str:
    """Promote an app build from the internal track to production with a
    staged rollout.

    Args:
        package_name: App package name, e.g. com.example.myapp
        version_codes: List of version codes to promote (e.g. [1234]).
        rollout_percentage: Initial rollout percentage, 0 < value <= 100.
            Use 100 for an immediate full release.
        release_name: Optional human-readable release name.
        release_notes_en: Optional English release notes (plain text).
    """
    try:
        notes = (
            [{"language": "en-US", "text": release_notes_en}]
            if release_notes_en
            else None
        )
        result = _publisher().promote_to_production(
            package_name=package_name,
            version_codes=version_codes,
            rollout_percentage=rollout_percentage,
            release_name=release_name or None,
            release_notes=notes,
        )
        track_summary = _format_track(result["track"])
        commit = result.get("commit", {})
        return json.dumps(
            {
                "success": True,
                "message": (
                    f"Version codes {version_codes} promoted to production "
                    f"at {rollout_percentage}% rollout."
                ),
                "track": track_summary,
                "editId": commit.get("editId"),
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: check_review_status
# ---------------------------------------------------------------------------

@mcp.tool()
def check_review_status(package_name: str) -> str:
    """Check the current production release status for an app.

    Returns all production releases with their status (draft, inProgress,
    halted, completed) and rollout percentages. A release in 'inProgress'
    state indicates it is either under review or actively rolling out.

    Args:
        package_name: App package name, e.g. com.example.myapp
    """
    try:
        track_data = _publisher().get_track(package_name, "production")
        releases = track_data.get("releases", [])

        if not releases:
            return json.dumps(
                {
                    "packageName": package_name,
                    "message": "No releases found in the production track.",
                    "releases": [],
                },
                indent=2,
            )

        formatted = [_format_release(r) for r in releases]

        # Derive a human-readable overall status
        statuses = {r["status"] for r in formatted if r["status"]}
        if "inProgress" in statuses:
            summary = "Staged rollout in progress."
        elif "draft" in statuses:
            summary = "Release is in draft / under Google Play review."
        elif "halted" in statuses:
            summary = "Rollout is halted."
        elif statuses == {"completed"}:
            summary = "Release fully rolled out (100%)."
        else:
            summary = f"Status: {', '.join(statuses)}"

        return json.dumps(
            {
                "packageName": package_name,
                "summary": summary,
                "releases": formatted,
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: update_rollout_percentage
# ---------------------------------------------------------------------------

@mcp.tool()
def update_rollout_percentage(
    package_name: str,
    rollout_percentage: float,
    version_codes: list[int] | None = None,
) -> str:
    """Update the rollout percentage for the current production release.

    Args:
        package_name: App package name, e.g. com.example.myapp
        rollout_percentage: New rollout percentage, 0 < value <= 100.
            Pass 100 to complete the rollout for all users.
        version_codes: Optional list of version codes to target. If omitted,
            the most recent inProgress or halted release is updated.
    """
    try:
        result = _publisher().update_rollout_percentage(
            package_name=package_name,
            rollout_percentage=rollout_percentage,
            version_codes=version_codes,
        )
        track_summary = _format_track(result["track"])
        commit = result.get("commit", {})
        return json.dumps(
            {
                "success": True,
                "message": f"Rollout updated to {rollout_percentage}%.",
                "track": track_summary,
                "editId": commit.get("editId"),
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_production_release_info
# ---------------------------------------------------------------------------

@mcp.tool()
def get_production_release_info(package_name: str) -> str:
    """Fetch the current production release info: rollout percentage,
    version codes, status, and release notes.

    Note: Detailed install / update event analytics (raw install counts,
    update events) are not exposed by the public Google Play Developer API.
    They are available in Google Play Console UI, BigQuery data exports, or
    Firebase Analytics if integrated with your app.

    Args:
        package_name: App package name, e.g. com.example.myapp
    """
    try:
        track_data = _publisher().get_track(package_name, "production")
        releases = track_data.get("releases", [])

        formatted = [_format_release(r) for r in releases]

        # Find the active / latest release
        active = next(
            (r for r in formatted if r["status"] in ("inProgress", "completed")),
            formatted[0] if formatted else None,
        )

        return json.dumps(
            {
                "packageName": package_name,
                "activeRelease": active,
                "allReleases": formatted,
                "note": (
                    "Install & Update event counts are not available via the "
                    "public API. Use Play Console > Statistics or set up "
                    "BigQuery exports for detailed analytics."
                ),
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
    """Fetch user-perceived crash rate for the production release.

    Uses the Google Play Developer Reporting API v1beta1.
    Returns daily crashRate, userPerceivedCrashRate, and distinctUsers
    broken down by version code for the requested period.

    Args:
        package_name: App package name, e.g. com.example.myapp
        days: Number of past days to include (default 7, max 30).
        version_code: Optional single version code string to filter results.
    """
    days = max(1, min(days, 30))
    try:
        raw = _reporting().query_crash_rate(
            package_name=package_name,
            days=days,
            version_code=version_code or None,
        )

        rows = raw.get("rows", [])
        if not rows:
            return json.dumps(
                {
                    "packageName": package_name,
                    "message": (
                        "No crash data found. Data may not be available yet "
                        "or the app has no crashes in this period."
                    ),
                    "rows": [],
                },
                indent=2,
            )

        # Parse rows into a readable format
        parsed_rows = []
        for row in rows:
            dims = {d.get("dimension"): d.get("stringValue") or d.get("int64Value")
                    for d in row.get("dimensions", [])}
            metrics = {}
            for m in row.get("metrics", []):
                name = m.get("metric")
                val = m.get("decimalValue") or m.get("int64Value")
                if val is not None:
                    # decimalValue comes as a string like "0.0012"
                    try:
                        val = float(val)
                    except (TypeError, ValueError):
                        pass
                metrics[name] = val

            date_info = row.get("startTime", {})
            parsed_rows.append(
                {
                    "date": date_info,
                    "versionCode": dims.get("versionCode"),
                    "crashRate": metrics.get("crashRate"),
                    "userPerceivedCrashRate": metrics.get("userPerceivedCrashRate"),
                    "distinctUsers": metrics.get("distinctUsers"),
                }
            )

        return json.dumps(
            {
                "packageName": package_name,
                "periodDays": days,
                "totalRows": len(parsed_rows),
                "rows": parsed_rows,
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
