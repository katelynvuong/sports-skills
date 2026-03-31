---
name: watch
description: |
  Realtime data watcher — monitor any sports-skills endpoint for live changes. Polls at configurable intervals, detects JSON-level changes via structural diffing, and outputs change events via stdout (default), JSONL file, or webhook POST. Zero config, no API keys.

  Use when: user wants to monitor live scores, track standings changes over time, watch prediction market price movements, set up automated data pipelines, or detect real-time data changes across any sport.
  Don't use when: user wants a one-time data fetch — use the specific sport module directly (e.g., nfl-data, football-data, kalshi).
license: MIT
metadata:
  author: machina-sports
  version: "0.1.0"
---

# Watch — Realtime Data Watcher

Before writing queries, consult `references/api-reference.md` for parameters and output format.

## Setup

Before first use, check if the CLI is available:
```bash
which sports-skills || pip install sports-skills
```
If `pip install` fails (package not found or Python version error), install from GitHub:
```bash
pip install git+https://github.com/machina-sports/sports-skills.git
```
The package requires Python 3.10+. No API keys required.

## Quick Start

```bash
# Watch NFL scores every 30 seconds
sports-skills watch nfl get_scoreboard --interval=30

# Watch Premier League standings every 5 minutes, save to file
sports-skills watch football get_season_standings --season_id=premier-league-2025 --interval=300 --output=file --output_path=./epl.jsonl

# Watch Kalshi NBA markets with webhook
sports-skills watch kalshi get_markets --series_ticker=KXNBA --interval=60 --output=webhook --webhook_url=http://localhost:8080/hooks

# Multi-watcher from config file
sports-skills watch --config=watchers.json
```

Python SDK:
```python
from sports_skills.watch import start_watcher

# Blocks until Ctrl+C
start_watcher("nfl", "get_scoreboard", interval=30)
```

## How It Works

1. **First poll** captures a baseline snapshot — no event is emitted.
2. Each subsequent poll hashes the response and compares with the stored snapshot.
3. If the hash differs, a structural diff is computed showing exactly what changed.
4. The change event (with diff + full data) is emitted via the configured output.
5. The new snapshot replaces the old one in local SQLite storage (`~/.sports-skills/watch.db`).

Snapshots persist across restarts — if you stop and restart a watcher, it compares against the last known state.

## CRITICAL: Before Any Watch

- **Interval**: Minimum 5 seconds. Recommended intervals by use case:
  - Live scores (game day): 30s
  - Standings / schedules: 300s (5 min)
  - Prediction markets: 60s
  - News: 600s (10 min)
- **Cache awareness**: The underlying connectors cache responses (typically 120-300s TTL). If your interval is shorter than the cache TTL, the watcher effectively polls at the cache rate. This is expected.
- **Rate limiting**: Watchers go through the same rate limiters as direct calls. Multiple watchers share rate limit budgets.

## Output Modes

| Mode | Flag | Description |
|---|---|---|
| stdout | `--output=stdout` (default) | JSON lines to stdout — pipe to `jq`, log files, etc. |
| file | `--output=file --output_path=./data.jsonl` | Append JSONL to a file |
| webhook | `--output=webhook --webhook_url=http://...` | POST JSON to a URL |

Operational messages (startup, errors, shutdown) always go to stderr, keeping stdout machine-parseable.

## Config File (Multi-Watcher)

Create a `watchers.json`:
```json
{
    "watchers": [
        {
            "module": "nfl",
            "command": "get_scoreboard",
            "params": {},
            "interval": 30,
            "output": "stdout"
        },
        {
            "module": "football",
            "command": "get_season_standings",
            "params": {"season_id": "premier-league-2025"},
            "interval": 300,
            "output": "file",
            "output_path": "./epl-standings.jsonl"
        }
    ]
}
```

Then run:
```bash
sports-skills watch --config=watchers.json
```

## Change Event Format

Each change event emitted contains:
```json
{
    "timestamp": "2026-03-31T14:22:05+00:00",
    "watcher_id": "nfl:get_scoreboard:{}",
    "module": "nfl",
    "command": "get_scoreboard",
    "params": {},
    "poll_number": 42,
    "diff": {
        "changed": true,
        "summary": "3 modified, 1 added",
        "changes": [
            {"path": "events[0].score.home", "old": 14, "new": 21, "type": "modified"}
        ]
    },
    "data": { "..." : "full current response data" }
}
```

## Examples

### 1. Track Live NBA Scores on Game Night
**Action:** `sports-skills watch nba get_scoreboard --interval=30`
**Result:** Emits a change event every time a score updates, with diff showing exactly which games changed.

### 2. Monitor EPL Standings After Matchday
**Action:** `sports-skills watch football get_season_standings --season_id=premier-league-2025 --interval=300 --output=file --output_path=./epl.jsonl`
**Result:** Appends standings changes to a JSONL file every 5 minutes.

### 3. Kalshi Market Price Alerts via Webhook
**Action:** `sports-skills watch kalshi get_markets --series_ticker=KXNBA --interval=60 --output=webhook --webhook_url=http://localhost:8080/hooks`
**Result:** POSTs to your webhook whenever market prices change.

### 4. Multi-Sport Dashboard Data Feed
**Action:** Create a `watchers.json` monitoring NFL scores (30s), NBA scores (30s), and EPL standings (300s), then `sports-skills watch --config=watchers.json`
**Result:** All three watchers run concurrently in separate threads. Stdout receives interleaved change events.

## Error Handling

- Poll failures are logged to stderr and retried on the next interval.
- After 10 consecutive errors, the interval doubles (capped at 10x original) to reduce load.
- On recovery, the interval resets automatically.
- Webhook failures are logged but never crash the watcher.
- Press Ctrl+C for graceful shutdown — all threads stop cleanly.

## Commands That DO NOT Exist

- `watch` has no `list` or `status` command — it's a long-running process, not a CRUD API.
- There is no `unwatch` — stop the process with Ctrl+C.
- There is no `history` — use the JSONL file output if you need historical data.

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| "Minimum interval is 5s" | Interval too low | Use `--interval=5` or higher |
| "Unknown module" | Typo in module name | Check `sports-skills catalog` for valid modules |
| No events emitted | Data hasn't changed, or interval < cache TTL | Wait longer, or increase interval |
| Events on every poll | Data source returns volatile fields (timestamps) | Expected for some endpoints |
