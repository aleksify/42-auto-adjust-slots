# 42-auto-adjust-slots

Open evaluation slots from home without worrying about a slot getting booked before you can make it to campus.

This script polls your open slots on the 42 intra and deletes any that start sooner than your commute time, so a student who books an eval always picks one you can actually reach.

## How it works

Every couple of minutes, the script:

1. Fetches your open slots in the next 24 hours via the 42 API.
2. Deletes any slot whose `begin_at` is within `BUFFER_MINUTES` of now.
3. Leaves the rest alone.

## Requirements

- Python 3.11+
- `pip install requests` (ideally in a venv)
- A 42 API app: https://profile.intra.42.fr/oauth/applications/new
  - Redirect URI: `http://localhost:8080/callback`
  - Scopes: `public`, `projects`

## Setup

Copy the template and fill in the credentials from your 42 API app:

```
cp .env.example .env
```

`.env` should look like:

```
UID=your_client_uid
SECRET=your_client_secret
```

## Usage

```
python3 script.py
```

First run opens your browser to authorize the app. The resulting tokens are cached in `.token.json` (mode `0600`) and refreshed automatically.

Stop with `Ctrl+C`.

## Configuration

Edit the constants at the top of `script.py`:

| Name | Default | Meaning |
|---|---|---|
| `BUFFER_MINUTES` | `60` | Delete slots starting sooner than this many minutes from now. Set to your commute time. |
| `CHECK_EVERY_MIN` | `2` | How often to poll. |
| `REQUEST_TIMEOUT` | `30` | Per-request timeout in seconds. |
| `MAX_RETRIES` | `5` | Retries on HTTP 429 (respects `Retry-After`). |

## Notes

- The 42 API rate-limits at ~2 req/sec / 1200 req/hour. The script honors `Retry-After` on 429.
- `.token.json` holds your refresh token — keep it private.
