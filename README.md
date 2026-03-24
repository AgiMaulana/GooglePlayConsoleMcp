# Google Play Console MCP

[![Google Play Console MCP server](https://glama.ai/mcp/servers/AgiMaulana/GooglePlayConsoleMcp/badges/card.svg)](https://glama.ai/mcp/servers/AgiMaulana/GooglePlayConsoleMcp)
[![GooglePlayConsoleMcp MCP server](https://glama.ai/mcp/servers/AgiMaulana/GooglePlayConsoleMcp/badges/score.svg)](https://glama.ai/mcp/servers/AgiMaulana/GooglePlayConsoleMcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Python [Model Context Protocol](https://modelcontextprotocol.io/) server that
lets AI assistants (Claude, etc.) manage the full Google Play Store release
lifecycle directly — from uploading artifacts to managing testers, rollouts,
and Android Vitals.

<!-- mcp-name: io.github.AgiMaulana/google-play-mcp -->

---

## Quick start

### Option A — `uvx` (recommended, no install needed)

Run this once. Claude automatically starts and stops the server for every session — you never have to touch it again.

```bash
claude mcp add google-play-mcp \
  -e GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json \
  -- uvx google-play-mcp
```

> Requires `uv` — install with `brew install uv` or `curl -Lsf https://astral.sh/uv/install.sh | sh`

### Option B — `pip install`

If you prefer a permanent install:

```bash
pip install google-play-mcp

claude mcp add google-play-mcp \
  -e GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json \
  -- google-play-mcp
```

### Option C — HTTP (local server)

Only needed if you want to connect via HTTP transport instead of stdio:

```bash
# Terminal 1 — start the server
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json \
  uvx google-play-mcp --transport http --port 8080

# Terminal 2 — register with Claude
claude mcp add --transport http google-play-mcp http://localhost:8080
```

> **How stdio works:** With Options A and B, there is no server to start manually.
> Claude launches the process in the background when a session opens and shuts it
> down when the session ends. Zero maintenance.

---

## Features

### Tracks & Releases

| Tool | Description |
|---|---|
| `list_tracks` | List all tracks (internal, alpha, beta, production) with releases and country availability |
| `get_track_info` | Get detailed status, rollout %, and release notes for a specific track |
| `create_release` | Create or replace a release on any track with rollout %, release notes, and country targeting |
| `update_release` | Update rollout %, halt, resume, or complete an existing release |
| `promote_release` | Promote a release between tracks (e.g. internal → alpha → beta → production) |

### Artifact Management

| Tool | Description |
|---|---|
| `list_artifacts` | List all APKs and AABs with their version codes and SHA hashes |
| `upload_artifact` | Upload an APK or AAB and create a release on a track in one step |
| `upload_to_internal_sharing` | Upload a build to Internal App Sharing and get a shareable download URL |

### Tester Management

| Tool | Description |
|---|---|
| `get_testers` | Get tester email addresses and Google Groups for internal/closed testing |
| `update_testers` | Replace the tester list for an internal or closed testing track |

### Android Vitals

| Tool | Description |
|---|---|
| `get_crash_rate` | Daily crash rate and user-perceived crash rate by version code |
| `get_anr_rate` | Daily ANR rate and user-perceived ANR rate by version code |
| `get_vitals_summary` | Combined crash + ANR overview with bad behavior threshold indicators |
| `get_wakelock_rate` | Daily stuck background wake lock rate by version code (battery health) |
| `get_wakeup_rate` | Daily excessive wakeup rate by version code (battery health) |

---

## Prerequisites

1. **`uv`** — [install guide](https://docs.astral.sh/uv/getting-started/installation/)
2. A **Google Cloud service account** with the JSON key downloaded.
3. The service account added to **Google Play Console** with the correct permissions (see below).
4. These APIs enabled in your Google Cloud project:
   - [Google Play Android Developer API](https://console.cloud.google.com/apis/library/androidpublisher.googleapis.com)
   - [Google Play Developer Reporting API](https://console.cloud.google.com/apis/library/playdeveloperreporting.googleapis.com)

### Required Play Console permissions

| Tools | Minimum permission required |
|---|---|
| `upload_artifact`, `create_release`, `update_release`, `promote_release`, `update_testers` | **Release to production, exclude devices, and use app signing by Google Play** |
| `upload_to_internal_sharing` | **Release to testing tracks** |
| `list_tracks`, `get_track_info`, `list_artifacts`, `get_testers` | **View app information and download bulk reports (read-only)** |
| `get_crash_rate`, `get_anr_rate`, `get_vitals_summary`, `get_wakelock_rate`, `get_wakeup_rate` | **View app information and download bulk reports (read-only)** + Reporting API enabled |

> **Important:** Release Manager does **not** grant Reporting API access. You must also enable
> **View app information and download bulk reports (read-only)** — both at account level and
> per-app level — for the Vitals tools to work.

---

## Claude Desktop integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "google-play": {
      "command": "uvx",
      "args": ["google-play-mcp"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/absolute/path/to/service-account.json"
      }
    }
  }
}
```

Restart Claude Desktop after saving.

---

## Service account setup

1. Go to [IAM & Admin → Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts) in your GCP project.
2. Create a service account (or use an existing one) and download a JSON key.
3. In [Google Play Console](https://play.google.com/console) → **Setup → API access**:
   - Link your Google Cloud project.
   - Find the service account → **Manage Play Console permissions**.
   - Under **Account permissions**, enable **View app information and download bulk reports (read-only)**.
   - Under **App permissions** for each app, enable:
     - **View app information and download bulk reports (read-only)**
     - **Release to production…** _(if you need write access)_
   - Click **Apply** → **Invite user**.

> Permissions must be granted at **both** account level and per-app level.
> Account-level alone is not sufficient for the Reporting API.

---

## Tool reference

### `list_tracks`

```
package_name : str  — e.g. "com.example.myapp"
```

Returns all tracks with their releases, rollout percentages, statuses, and country availability.

---

### `get_track_info`

```
package_name : str
track        : str  — "internal" | "alpha" | "beta" | "production" (default: "production")
```

Returns a human-readable summary plus releases with status, rollout %, version codes, and release notes.

---

### `create_release`

```
package_name       : str
track              : str        — "internal" | "alpha" | "beta" | "production"
version_codes      : list[int]  — e.g. [1042]
rollout_percentage : float      — default 10.0 (used when status is "inProgress")
status             : str        — "draft" (default) | "inProgress" | "halted" | "completed"
release_name       : str        — optional
release_notes      : dict       — optional, e.g. {"en-US": "Bug fixes", "fr-FR": "Corrections"}
country_codes      : list[str]  — optional ISO 3166-1 alpha-2 codes, e.g. ["US", "GB"]
```

Creates or replaces a release on the given track. Use `status="inProgress"` with a
`rollout_percentage` for a staged production rollout, or `status="completed"` to release
to all users immediately.

---

### `update_release`

```
package_name       : str
track              : str    — default "production"
rollout_percentage : float  — optional; pass 100 to complete the rollout
status             : str    — optional; "inProgress" | "halted" | "completed" | "draft"
version_codes      : list[int]  — optional filter; targets first matching release if omitted
```

Update an existing release. Common use cases:
- **Increase rollout:** `update_release(pkg, rollout_percentage=50)`
- **Complete rollout:** `update_release(pkg, rollout_percentage=100)`
- **Halt rollout:** `update_release(pkg, status="halted")`
- **Resume rollout:** `update_release(pkg, status="inProgress")`

---

### `promote_release`

```
package_name       : str
from_track         : str        — "internal" | "alpha" | "beta"
to_track           : str        — "alpha" | "beta" | "production"
version_codes      : list[int]
rollout_percentage : float      — default 10.0
release_name       : str        — optional override
release_notes      : dict       — optional override; inherits from source if omitted
```

Copies a release from one track to another. Release notes and name are inherited from the
source release unless explicitly overridden.

---

### `list_artifacts`

```
package_name : str
```

Returns all APKs and AABs sorted by version code (newest first) with SHA hashes.

---

### `upload_artifact`

```
package_name       : str
file_path          : str    — absolute local path to .apk or .aab
track              : str    — default "internal"
status             : str    — "draft" (default) | "inProgress" | "completed"
rollout_percentage : float  — default 10.0 (used when status is "inProgress")
release_name       : str    — optional
release_notes      : dict   — optional
```

Uploads an APK or AAB (auto-detected from extension) and creates a release on the given
track in a single atomic operation. Returns the assigned version code.

---

### `upload_to_internal_sharing`

```
package_name : str
file_path    : str  — absolute local path to .apk or .aab
```

Uploads a build to Internal App Sharing (bypasses track assignment) and returns a
shareable `downloadUrl`. Testers must have Internal App Sharing enabled in their Play
Store settings. Ideal for quick one-off testing without affecting any release track.

---

### `get_testers`

```
package_name : str
track        : str  — "internal" (default) | "alpha"
```

Returns the list of tester email addresses and Google Groups for the track.

---

### `update_testers`

```
package_name  : str
track         : str         — "internal" (default) | "alpha"
emails        : list[str]   — optional; full replacement list of tester emails
google_groups : list[str]   — optional; full replacement list of Google Group emails
```

> **Warning:** This is a full replacement. Testers not in the new list will lose access.
> Call `get_testers` first to retrieve the current list if you only want to add/remove individuals.

---

### `get_crash_rate`

```
package_name : str
days         : int  — look-back window, 1–30 (default 7)
version_code : str  — optional single version code to filter
```

Returns daily `crashRate`, `userPerceivedCrashRate`, and `distinctUsers` per version code.
Google's bad behavior threshold for user-perceived crash rate is **~1.09%**.

---

### `get_anr_rate`

```
package_name : str
days         : int  — look-back window, 1–30 (default 7)
version_code : str  — optional single version code to filter
```

Returns daily `anrRate`, `userPerceivedAnrRate`, and `distinctUsers` per version code.
Google's bad behavior threshold for user-perceived ANR rate is **~0.47%**.

---

### `get_vitals_summary`

```
package_name : str
days         : int  — look-back window, 1–30 (default 7)
```

Returns a combined crash + ANR summary aggregated per version code, with averages over
the period and `exceedsCrashThreshold` / `exceedsAnrThreshold` flags. The latest version
is highlighted as `latestVersionSummary`.

### `get_wakelock_rate`

```
package_name : str
days         : int  — look-back window, 1–30 (default 7)
version_code : str  — optional single version code to filter
```

Returns daily `stuckBackgroundWakelockRate` and `distinctUsers` per version code.
Relevant for 2026 Google Play battery health enforcement — apps with an excessive
proportion of sessions holding a partial wake lock for more than 1 hour in the background
may be penalized.

---

### `get_wakeup_rate`

```
package_name : str
days         : int  — look-back window, 1–30 (default 7)
version_code : str  — optional single version code to filter
```

Returns daily `excessiveWakeupRate` and `distinctUsers` per version code.
Relevant for 2026 Google Play battery health enforcement — apps that wake the CPU too
frequently (above platform thresholds) may be penalized.

---

## Troubleshooting

### `403 Forbidden` on Vitals tools

```
403 Client Error: Forbidden for url: https://playdeveloperreporting.googleapis.com/...
```

This error has two common causes — check both:

**1. Google Play Developer Reporting API not enabled**

Enable it in your Google Cloud project:
[console.cloud.google.com/apis/library/playdeveloperreporting.googleapis.com](https://console.cloud.google.com/apis/library/playdeveloperreporting.googleapis.com)

**2. Service account lacks per-app Reporting API access**

1. Play Console → **Setup → API access** → find the service account → **Manage Play Console permissions**.
2. Under **App permissions**, select the app and enable **View app information and download bulk reports (read-only)**.
3. Save and wait a few minutes for the change to propagate.

### `404 Package not found`

The service account must be linked to the same Google Play Console account that owns the app.
Go to Play Console → **Setup → API access** and verify the service account is listed and has been invited.

---

## Marketplaces

| Registry | Link |
|---|---|
| [PyPI](https://pypi.org/project/google-play-mcp/) | `pip install google-play-mcp` |
| [Smithery](https://smithery.ai/server/@agimaulana/google-play-mcp) | search `google-play-mcp` |
| [Official MCP Registry](https://registry.modelcontextprotocol.io/servers/io.github.AgiMaulana/google-play-mcp) | `io.github.AgiMaulana/google-play-mcp` |

---

## License

MIT
