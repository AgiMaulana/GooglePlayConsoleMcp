# Google Play Console MCP

A Python [Model Context Protocol](https://modelcontextprotocol.io/) server that
lets AI assistants (Claude, etc.) manage your Google Play Store production
releases directly.

<!-- mcp-name: io.github.agimaulana/google-play-mcp -->

## Quick start

**stdio (recommended):**
```bash
claude mcp add google-play-mcp \
  -e GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json \
  -- uvx google-play-mcp
```

**HTTP (local server):**
```bash
# 1. Start the server
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json \
  uvx google-play-mcp --transport http --port 8080

# 2. In another terminal
claude mcp add --transport http google-play-mcp http://localhost:8080
```

## Features

| Tool | Description |
|---|---|
| `promote_to_production` | Promote a build from internal track to production with a custom rollout % |
| `check_review_status` | Check production release status (draft / inProgress / halted / completed) |
| `update_rollout_percentage` | Increase or complete an existing staged rollout |
| `get_production_release_info` | Fetch current rollout %, version codes, and release notes |
| `get_crash_rate` | Fetch user-perceived crash rate via the Play Developer Reporting API |

---

## Prerequisites

1. **Python 3.10+**
2. A **Google Cloud service account** with the JSON key downloaded.
3. The service account must be added to your **Google Play Console** with the
   correct permissions (see table below).
4. Enable these APIs in your Google Cloud project:
   - [Google Play Android Developer API](https://console.cloud.google.com/apis/library/androidpublisher.googleapis.com)
   - [Google Play Developer Reporting API](https://console.cloud.google.com/apis/library/playdeveloperreporting.googleapis.com)

### Required Play Console permissions

| Tool | Minimum permission required |
|---|---|
| `promote_to_production` | **Release to production, exclude devices, and use app signing by Google Play** (under Releases) |
| `update_rollout_percentage` | **Release to production, exclude devices, and use app signing by Google Play** (under Releases) |
| `check_review_status` | **View app information and download bulk reports (read-only)** |
| `get_production_release_info` | **View app information and download bulk reports (read-only)** |
| `get_crash_rate` | **View app information and download bulk reports (read-only)** |

> **Tip:** Granting **Release Manager** covers the release tools but does **not** automatically
> include Reporting API access. You must also explicitly enable
> **View app information and download bulk reports (read-only)** for `get_crash_rate` to work.
> The easiest setup is to grant all of the above permissions to the service account.

---

## Installation

### Option A — install directly from GitHub (recommended)

```bash
pip install git+https://github.com/AgiMaulana/GooglePlayConsoleMcp.git
```

### Option B — clone and install locally

```bash
git clone https://github.com/AgiMaulana/GooglePlayConsoleMcp.git
cd GooglePlayConsoleMcp
pip install .
```

### Option C — using `uvx` (no permanent install)

```bash
uvx --from git+https://github.com/AgiMaulana/GooglePlayConsoleMcp.git google-play-mcp
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```dotenv
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
```

---

## Running the server

```bash
google-play-mcp
```

The server communicates over **stdio** (the standard MCP transport).

---

## Claude Desktop Integration

Add this block to your `claude_desktop_config.json`
(`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "google-play": {
      "command": "google-play-mcp",
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/absolute/path/to/service-account.json"
      }
    }
  }
}
```

If you prefer to run without installing (using `uvx`):

```json
{
  "mcpServers": {
    "google-play": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/AgiMaulana/GooglePlayConsoleMcp.git",
        "google-play-mcp"
      ],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/absolute/path/to/service-account.json"
      }
    }
  }
}
```

Restart Claude Desktop after editing the config.

---

## Tool reference

### `promote_to_production`

```
package_name       : str        — e.g. "com.example.myapp"
version_codes      : list[int]  — e.g. [1042]
rollout_percentage : float      — 1–100 (use 100 for immediate full release)
release_name       : str        — optional, e.g. "2.4.1"
release_notes_en   : str        — optional English release notes
```

### `check_review_status`

```
package_name : str
```

Returns each production release with its status and rollout percentage.

### `update_rollout_percentage`

```
package_name       : str
rollout_percentage : float      — new %, 0 < value <= 100
version_codes      : list[int]  — optional; targets the first inProgress release if omitted
```

### `get_production_release_info`

```
package_name : str
```

Returns the active release's rollout percentage, version codes, and release notes.

> **Note on install / update events:** Raw install and update event counts are
> not available through the public Google Play Developer API. Access them via
> **Play Console → Statistics**, [BigQuery data exports](https://support.google.com/googleplay/android-developer/answer/10668107),
> or Firebase Analytics.

### `get_crash_rate`

```
package_name : str
days         : int  — look-back window, 1–30 (default 7)
version_code : str  — optional single version code to filter
```

Returns daily `crashRate`, `userPerceivedCrashRate`, and `distinctUsers`
per version code.

---

## Service account setup guide

1. Go to [IAM & Admin → Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts) in your Google Cloud project.
2. Create a new service account (or use an existing one).
3. Download a JSON key and store it somewhere safe.
4. In [Google Play Console](https://play.google.com/console) → **Setup → API access**:
   - Link your Google Cloud project.
   - Find the service account and click **Manage Play Console permissions**.
   - Under **Account permissions**, enable:
     - **View app information and download bulk reports (read-only)**
   - Under **App permissions** for each app, enable:
     - **View app information and download bulk reports (read-only)**
     - **Release to production, exclude devices, and use app signing by Google Play** _(if you need write access)_
   - Click **Apply** and then **Invite user** to save.

> **Note:** Permissions are split between account-level and per-app level. Even if you grant account-level
> read access, you must also grant the same permissions at the app level for the Reporting API (crash rate)
> to work correctly.

---

## Troubleshooting

### `403 Forbidden` when calling `get_crash_rate`

```
403 Client Error: Forbidden for url: https://playdeveloperreporting.googleapis.com/...
```

This means the service account does not have access to the app in the Reporting API.
Retrying will not help — this is a permissions issue.

**Fix:**

1. Go to [Play Console](https://play.google.com/console) → **Setup → API access**.
2. Find the service account and click **Manage Play Console permissions**.
3. Under **App permissions**, select the app and enable:
   - **View app information and download bulk reports (read-only)**
4. Save and wait a few minutes for permissions to propagate.

> Account-level permissions alone are not enough — the permission must be granted
> at the **per-app** level for the Reporting API to return data.

---

## Marketplaces

This server is listed on:

- [Smithery](https://smithery.ai) — search `google-play-mcp`
- [Official MCP Registry](https://registry.modelcontextprotocol.io) — `io.github.agimaulana/google-play-mcp`

---

## License

MIT
