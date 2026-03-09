# Google Play Console MCP

A Python [Model Context Protocol](https://modelcontextprotocol.io/) server that
lets AI assistants (Claude, etc.) manage your Google Play Store production
releases directly.

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
   **Release Manager** (or higher) role.
4. Enable these APIs in your Google Cloud project:
   - [Google Play Android Developer API](https://console.cloud.google.com/apis/library/androidpublisher.googleapis.com)
   - [Google Play Developer Reporting API](https://console.cloud.google.com/apis/library/playdeveloperreporting.googleapis.com)

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
   - Find the service account and grant it **Release Manager** permissions.

---

## License

MIT
