# nyc-arthouse-digest

Local Python project that aggregates NYC art-house film listings and sends a weekly email digest.

## What it includes

- Plug-in scraper interface per venue.
- OpenAI agent extraction pipeline (`src/agents/`) with schema-constrained output.
- Agent-configured venues:
  - Metrograph
  - Film at Lincoln Center
  - IFC Center
  - Angelika New York
  - Village East by Angelika
  - Cinema123 by Angelika
  - Film Forum
- Angelika venues use an agent-fed API context (Reading backend now-playing JSON) because public pages are JS app shells.
- Manual fallback source (`data/manual_highlights.yaml`) so digest still works when a site scraper breaks.
- Deduping logic for duplicate records.
- Top-picks heuristics based on notes/title hints (`Q&A`, `35mm`, `70mm`, `one-night`, `premiere`, `restored`) plus earliest-date fill-in.
- HTML email + plain-text fallback.
- Caching of fetched HTML in `cache/` with a one-week TTL to avoid hammering sites.
- CLI dry run mode writing `digest_preview.html`.

## Project layout

- `src/main.py`
- `src/models.py`
- `src/render.py`
- `src/emailer.py`
- `src/config.py`
- `src/scrapers/base.py`
- `src/agents/openai_extractor.py`
- `src/agents/venue_agent.py`
- `src/scrapers/manual_yaml.py`
- `src/scrapers/metrograph.py`
- `src/templates/email.html.j2`
- `data/manual_highlights.yaml`
- `cache/`
- `tests/`

## Requirements

- Python 3.11+

## Setup

```bash
cd /Users/eliasisraelancona/Projects/nyc-arthouse-digest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Edit `config.yaml` and/or set environment variables.

Important: local `config.yaml` is not the source of truth for the weekly GitHub-scheduled email. The workflow in `.github/workflows/weekly-digest.yml` sets `DIGEST_RECIPIENTS` from GitHub Actions secrets, which overrides `config.yaml` during scheduled and manual Actions runs.

### OpenAI agent mode

Create `.env`:

```bash
OPENAI_API_KEY=your_key_here
# optional
OPENAI_MODEL=gpt-5-mini
OPENAI_TIMEOUT_SECONDS=45
```

### YAML config

```yaml
recipients:
  - "you@example.com"
  - "dad@example.com"

smtp:
  host: "smtp.gmail.com"
  port: 587
  username: "you@gmail.com"
  password: "APP_PASSWORD_HERE"
  sender: "you@gmail.com"
  use_starttls: true
```

### Environment variables (override YAML)

- `DIGEST_RECIPIENTS` (comma-separated)
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_SENDER`
- `SMTP_STARTTLS` (`true`/`false`)

## Run

### Dry run (no email, writes preview file)

```bash
python -m src.main --dry-run
```

Optional:

```bash
python -m src.main --dry-run --mode agent
python -m src.main --dry-run --mode hybrid
python -m src.main --dry-run --mode scraper --venues metrograph manual
python -m src.main --dry-run --preview-path digest_preview.html
```

### Send email

```bash
python -m src.main --send
```

Optional venue selection:

```bash
python -m src.main --send --mode agent
```

### Mode behavior

- `--mode scraper`: only deterministic scrapers.
- `--mode agent`: only OpenAI extraction for supported venues.
- `--mode hybrid`: OpenAI first, deterministic scraper fallback if agent fails/returns empty.

## Venue notes

Agent mode is configured for:

- Metrograph
- Film at Lincoln Center
- IFC Center
- Angelika New York
- Village East by Angelika
- Cinema123 by Angelika
- Film Forum

Additional placeholder stubs (not yet agent-configured): Angelika Film Center (generic key) and A24 Cherry Lane.

If a site becomes JS-rendered or markup changes, keep digest quality via `data/manual_highlights.yaml` and/or `--mode hybrid`.

## Manual YAML format

`data/manual_highlights.yaml`:

```yaml
items:
  - title: "Film Title"
    venue: "Venue Name"
    url: "https://..."
    start: "2026-02-27 19:00"   # optional
    notes: "Q&A / 35mm / etc"    # optional
```

## Scheduling weekly

### Cron (simple)

Edit crontab:

```bash
crontab -e
```

Example: run every Sunday at 9:00 AM and send digest:

```cron
0 9 * * 0 cd /Users/eliasisraelancona/Projects/nyc-arthouse-digest && /Users/eliasisraelancona/Projects/nyc-arthouse-digest/.venv/bin/python -m src.main --send >> cron.log 2>&1
```

### launchd (macOS-native)

Create `~/Library/LaunchAgents/com.local.nyc-arthouse-digest.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.local.nyc-arthouse-digest</string>

    <key>ProgramArguments</key>
    <array>
      <string>/Users/eliasisraelancona/Projects/nyc-arthouse-digest/.venv/bin/python</string>
      <string>-m</string>
      <string>src.main</string>
      <string>--send</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/eliasisraelancona/Projects/nyc-arthouse-digest</string>

    <key>StartCalendarInterval</key>
    <dict>
      <key>Weekday</key><integer>0</integer>
      <key>Hour</key><integer>9</integer>
      <key>Minute</key><integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/eliasisraelancona/Projects/nyc-arthouse-digest/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/eliasisraelancona/Projects/nyc-arthouse-digest/launchd.err.log</string>
  </dict>
</plist>
```

Load:

```bash
launchctl unload ~/Library/LaunchAgents/com.local.nyc-arthouse-digest.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.local.nyc-arthouse-digest.plist
```

## Gmail app password SMTP

1. Enable 2-Step Verification on your Google account.
2. Create an App Password for Mail.
3. Use that 16-character app password in `SMTP_PASSWORD` / `config.yaml`.
4. Use:
   - host: `smtp.gmail.com`
   - port: `587`
   - STARTTLS: `true`

## Tests

```bash
pytest -q
```

## GitHub Actions (Always-On Weekly Send)

Use this if you want sends even when your Mac is closed.

Workflow file included:
- `.github/workflows/weekly-digest.yml`

It runs hourly on Mondays and only sends at 9:00 AM America/New_York (DST-safe via timezone guard).

In your GitHub repo, add these **Repository Secrets**:
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (optional, e.g. `gpt-5-mini`)
- `DIGEST_RECIPIENTS` (comma-separated emails)
- `SMTP_HOST` (`smtp.mail.me.com`)
- `SMTP_PORT` (`587`)
- `SMTP_USERNAME`
- `SMTP_PASSWORD` (app-specific password)
- `SMTP_SENDER`

Recipient source of truth for GitHub sends:
- Scheduled weekly runs use `DIGEST_RECIPIENTS`.
- Manual Actions runs use `DIGEST_RECIPIENTS_TEST`.
- Local runs from your Mac use `config.yaml` unless you export `DIGEST_RECIPIENTS`.

Duplicate-send protection:
- The workflow skips sending if a successful digest run already completed earlier the same day in America/New_York.
- Manual reruns can bypass that safeguard only by setting the `force_resend` workflow input to `true`.

Then trigger a one-time test via **Actions > Weekly NYC Arthouse Digest > Run workflow**.

## Notes on reliability

- Scrapers are best-effort and intentionally isolated so one failure does not break the digest.
- HTML fetches are cached for one week in `cache/`.
- Manual YAML keeps output useful even when live scrape returns empty.
