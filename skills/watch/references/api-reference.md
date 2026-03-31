# Watch API Reference

## CLI Usage

### Single Watcher

```
sports-skills watch <module> <command> [--endpoint-params...] [--watch-params...]
```

### Config File

```
sports-skills watch --config=<path>
```

## Watch Parameters

These parameters control the watcher behavior and are separated from endpoint parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `--interval` | float | `60` | Polling interval in seconds (minimum 5) |
| `--output` | string | `"stdout"` | Output mode: `stdout`, `file`, or `webhook` |
| `--output_path` | string | — | File path for `file` output mode (required if output=file) |
| `--webhook_url` | string | — | URL for `webhook` output mode (required if output=webhook) |
| `--db_path` | string | `~/.sports-skills/watch.db` | Override SQLite snapshot database path |
| `--config` | string | — | Path to JSON config file for multi-watcher mode |

All other `--key=value` flags are passed through as endpoint parameters.

## Python SDK

### `start_watcher(module_name, command, **kwargs)`

Start a single watcher. Blocks until Ctrl+C or `KeyboardInterrupt`.

```python
from sports_skills.watch import start_watcher

start_watcher(
    "nfl",
    "get_scoreboard",
    params={"date": "2026-01-15"},
    interval=30,
    output_mode="stdout",       # "stdout" | "file" | "webhook"
    output_path=None,           # required for "file"
    webhook_url=None,           # required for "webhook"
    db_path=None,               # override SQLite path
)
```

### `start_watchers_from_config(config_path, **kwargs)`

Start multiple watchers from a JSON config file. Blocks until Ctrl+C.

```python
from sports_skills.watch import start_watchers_from_config

start_watchers_from_config("watchers.json", db_path=None)
```

### `make_watcher_id(module_name, command, params)`

Generate the deterministic watcher ID for a given endpoint spec.

```python
from sports_skills.watch import make_watcher_id

wid = make_watcher_id("nfl", "get_scoreboard", {})
# Returns: "nfl:get_scoreboard:{}"
```

## Config File Schema

```json
{
    "watchers": [
        {
            "module": "string (required)",
            "command": "string (required)",
            "params": "object (default: {})",
            "interval": "number (default: 60, minimum: 5)",
            "output": "string (default: 'stdout'): stdout | file | webhook",
            "output_path": "string (required if output=file)",
            "webhook_url": "string (required if output=webhook)"
        }
    ],
    "db_path": "string | null (default: null, uses ~/.sports-skills/watch.db)"
}
```

## Change Event Schema

Every change event emitted (after the initial baseline poll) has this structure:

```json
{
    "timestamp": "ISO 8601 UTC timestamp",
    "watcher_id": "module:command:{sorted_params_json}",
    "module": "module name",
    "command": "command name",
    "params": {},
    "poll_number": 42,
    "diff": {
        "changed": true,
        "summary": "human-readable summary (e.g., '3 modified, 1 added')",
        "changes": [
            {
                "path": "dot.separated[0].path",
                "old": "previous value or null",
                "new": "new value or null",
                "type": "modified | added | removed"
            }
        ]
    },
    "data": "full current response data from the endpoint"
}
```

## Recommended Intervals by Data Source

| Use Case | Interval | Rationale |
|---|---|---|
| Live scores (game day) | 30s | ESPN cache TTL ~120s, but scores update frequently |
| Standings / schedules | 300s | Changes are infrequent |
| Prediction markets (Kalshi/Polymarket) | 60s | Market prices shift regularly during events |
| News feeds | 600s | New articles are published infrequently |
| F1 session data | 30s | Timing data updates rapidly during sessions |
| Transfer news / player values | 3600s | Changes are very infrequent |

## Snapshot Storage

Snapshots are stored in a SQLite database at `~/.sports-skills/watch.db`.

Table schema:
```sql
CREATE TABLE snapshots (
    watcher_id   TEXT PRIMARY KEY,
    json_text    TEXT NOT NULL,
    sha256_hash  TEXT NOT NULL,
    updated_at   REAL NOT NULL
);
```

Snapshots persist across process restarts. Old snapshots (>7 days) can be pruned programmatically via `SnapshotStore.prune()`.
