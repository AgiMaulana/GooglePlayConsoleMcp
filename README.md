# Google Play Console MCP

A Python [Model Context Protocol](https://modelcontextprotocol.io/) server that
lets AI assistants (Claude, etc.) manage your Google Play Store production
releases directly.

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

| Tool | Description |
|---|---|
| `promote_to_production` | Promote a build from internal track to production with a custom rollout % |
| `check_review_status` | Check production release status (draft / inProgress / halted / completed) |
| `update_rollout_percentage` | Increase or complete an existing staged rollout |
| `get_production_release_info` | Fetch current rollout %, version codes, and release notes |
| `get_crash_rate` | Fetch user-perceived crash rate via the Play Developer Reporting API |

---

## Prerequisites

1. **`uv`** — [install guide](https://docs.astral.sh/uv/getting-started/installation/)
2. A **Google Cloud service account** with the JSON key downloaded.
3. The service account added to **Google Play Console** with the correct permissions (see below).
4. These APIs enabled in your Google Cloud project:
   - [Google Play Android Developer API](https://console.cloud.google.com/apis/library/androidpublisher.googleapis.com)
   - [Google Play Developer Reporting API](https://console.cloud.google.com/apis/library/playdeveloperreporting.googleapis.com)

### Required Play Console permissions

| Tool | Minimum permission required |
|---|---|
| `promote_to_production` | **Release to production, exclude devices, and use app signing by Google Play** |
| `update_rollout_percentage` | **Release to production, exclude devices, and use app signing by Google Play** |
| `check_review_status` | **View app information and download bulk reports (read-only)** |
| `get_production_release_info` | **View app information and download bulk reports (read-only)** |
| `get_crash_rate` | **View app information and download bulk reports (read-only)** |

> **Important:** Release Manager does **not** grant Reporting API access. You must also enable
> **View app information and download bulk reports (read-only)** — both at account level and
> per-app level — for `get_crash_rate` to work.

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

> **Note:** Raw install/update event counts are not available via the public API.
> Use **Play Console → Statistics**, [BigQuery exports](https://support.google.com/googleplay/android-developer/answer/10668107), or Firebase Analytics.

### `get_crash_rate`

```
package_name : str
days         : int  — look-back window, 1–30 (default 7)
version_code : str  — optional single version code to filter
```

Returns daily `crashRate`, `userPerceivedCrashRate`, and `distinctUsers` per version code.

---

## Troubleshooting

### `403 Forbidden` on `get_crash_rate`

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
