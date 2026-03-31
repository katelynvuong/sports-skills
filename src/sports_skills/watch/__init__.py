"""Realtime data watcher — poll any sports-skills endpoint and detect changes.

Monitors endpoints at configurable intervals, detects JSON-level changes,
and outputs notifications via stdout, file (JSONL), or webhook POST.

Usage (CLI):
    sports-skills watch nfl get_scoreboard --interval=30
    sports-skills watch --config=watchers.json

Usage (SDK):
    from sports_skills.watch import start_watcher
    start_watcher("nfl", "get_scoreboard", interval=30)
"""

from __future__ import annotations

import json

from sports_skills.watch._engine import WatcherEngine, _make_watcher_id
from sports_skills.watch._storage import SnapshotStore


def make_watcher_id(module_name: str, command: str, params: dict | None = None) -> str:
    """Generate a deterministic watcher ID from endpoint spec."""
    return _make_watcher_id(module_name, command, params or {})


def start_watcher(
    module_name: str,
    command: str,
    *,
    params: dict | None = None,
    interval: float = 60.0,
    output_mode: str = "stdout",
    output_path: str | None = None,
    webhook_url: str | None = None,
    db_path: str | None = None,
) -> None:
    """Start a single watcher (blocks until Ctrl+C).

    Args:
        module_name: Sport module (e.g., "nfl", "football", "kalshi").
        command: Function name (e.g., "get_scoreboard").
        params: Endpoint parameters as dict.
        interval: Polling interval in seconds (minimum 5).
        output_mode: "stdout", "file", or "webhook".
        output_path: File path for "file" mode.
        webhook_url: URL for "webhook" mode.
        db_path: Override SQLite DB path (default ~/.sports-skills/watch.db).
    """
    store = SnapshotStore(db_path=db_path) if db_path else None
    engine = WatcherEngine(store=store)
    engine.add_watcher(
        module_name=module_name,
        command=command,
        params=params,
        interval=interval,
        output_mode=output_mode,
        output_path=output_path,
        webhook_url=webhook_url,
    )
    engine.run()


def start_watchers_from_config(config_path: str, *, db_path: str | None = None) -> None:
    """Start multiple watchers from a JSON config file (blocks until Ctrl+C).

    Config format:
        {
            "watchers": [
                {"module": "nfl", "command": "get_scoreboard", "params": {}, "interval": 30},
                ...
            ],
            "db_path": null
        }
    """
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    watchers = config.get("watchers", [])
    if not watchers:
        raise ValueError(f"No watchers defined in {config_path}")

    effective_db_path = db_path or config.get("db_path")
    store = SnapshotStore(db_path=effective_db_path) if effective_db_path else None
    engine = WatcherEngine(store=store)

    errors = []
    for i, w in enumerate(watchers):
        if "module" not in w or "command" not in w:
            errors.append(f"Watcher #{i + 1}: 'module' and 'command' are required")
            continue
        try:
            engine.add_watcher(
                module_name=w["module"],
                command=w["command"],
                params=w.get("params", {}),
                interval=float(w.get("interval", 60)),
                output_mode=w.get("output", "stdout"),
                output_path=w.get("output_path"),
                webhook_url=w.get("webhook_url"),
            )
        except (ValueError, TypeError) as e:
            errors.append(f"Watcher #{i + 1} ({w['module']}.{w['command']}): {e}")

    if errors:
        raise ValueError("Config validation failed:\n  " + "\n  ".join(errors))

    engine.run()
