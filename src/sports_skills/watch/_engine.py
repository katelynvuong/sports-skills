"""Core watcher engine — polling loop, threading, signal handling."""

from __future__ import annotations

import json
import logging
import signal
import sys
import threading
from datetime import datetime, timezone

from sports_skills.watch._diff import build_diff_summary, canonical_hash, compute_diff, quick_changed
from sports_skills.watch._output import OutputHandler, create_output
from sports_skills.watch._storage import SnapshotStore

logger = logging.getLogger("sports_skills.watch")

_MIN_INTERVAL = 5
_MAX_CONSECUTIVE_ERRORS = 10
_MAX_BACKOFF_MULTIPLIER = 10


def _make_watcher_id(module_name: str, command: str, params: dict) -> str:
    """Generate a deterministic watcher ID from endpoint spec."""
    clean = {k: v for k, v in sorted(params.items()) if v is not None}
    return f"{module_name}:{command}:{json.dumps(clean, sort_keys=True)}"


class Watcher:
    """A single polling watcher for one endpoint.

    Runs in its own thread, polling at a fixed interval with interruptible sleep.
    """

    def __init__(
        self,
        *,
        watcher_id: str,
        module,
        command: str,
        params: dict,
        interval: float,
        output: OutputHandler,
        store: SnapshotStore,
        shutdown_event: threading.Event,
    ):
        self._watcher_id = watcher_id
        self._module = module
        self._command = command
        self._params = params
        self._interval = interval
        self._base_interval = interval
        self._output = output
        self._store = store
        self._shutdown = shutdown_event
        self._poll_count = 0
        self._consecutive_errors = 0

    @property
    def watcher_id(self) -> str:
        return self._watcher_id

    def run(self) -> None:
        """Main poll loop. Runs until shutdown_event is set."""
        while not self._shutdown.is_set():
            self._poll_once()
            self._shutdown.wait(self._interval)

    def _poll_once(self) -> None:
        """Execute one poll cycle: fetch → hash → diff → emit → store."""
        self._poll_count += 1
        func = getattr(self._module, self._command, None)
        if not func:
            logger.error("[%s] Function '%s' not found — stopping", self._watcher_id, self._command)
            self._shutdown.set()
            return

        try:
            result = func(**self._params)
        except Exception as e:
            self._handle_error(f"call failed: {e}")
            return

        if not isinstance(result, dict) or not result.get("status"):
            msg = result.get("message", "unknown error") if isinstance(result, dict) else str(result)
            self._handle_error(f"returned error: {msg}")
            return

        # Success — reset error backoff
        if self._consecutive_errors > 0:
            self._consecutive_errors = 0
            self._interval = self._base_interval
            logger.info("[%s] Recovered — interval reset to %.0fs", self._watcher_id, self._interval)

        data = result.get("data")
        new_hash = canonical_hash(data)

        try:
            old_json, old_hash = self._store.get_snapshot(self._watcher_id)
        except Exception as e:
            logger.warning("[%s] Storage read failed: %s — treating as first poll", self._watcher_id, e)
            old_json, old_hash = None, None

        is_first_poll = old_hash is None

        if not quick_changed(old_hash, new_hash):
            return

        # Compute diff (skip on first poll — no baseline to compare against)
        if is_first_poll:
            diff_result = {"changed": False, "summary": "initial baseline", "changes": []}
            _log(self._watcher_id, f"baseline captured (poll #{self._poll_count})")
        else:
            old_data = json.loads(old_json) if old_json else {}
            changes = compute_diff(old_data, data)
            diff_result = build_diff_summary(changes)
            _log(self._watcher_id, f"change detected — {diff_result['summary']} (poll #{self._poll_count})")

        # Save new snapshot
        data_json = json.dumps(data, sort_keys=True, default=str)
        try:
            self._store.save_snapshot(self._watcher_id, data_json, new_hash)
        except Exception as e:
            logger.warning("[%s] Storage write failed: %s", self._watcher_id, e)

        # Emit change event (skip first poll — baseline only)
        if not is_first_poll:
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "watcher_id": self._watcher_id,
                "module": self._module.__name__.split(".")[-1],
                "command": self._command,
                "params": self._params,
                "poll_number": self._poll_count,
                "diff": diff_result,
                "data": data,
            }
            try:
                self._output.emit(event)
            except Exception as e:
                logger.warning("[%s] Output emit failed: %s", self._watcher_id, e)

    def _handle_error(self, msg: str) -> None:
        """Handle a poll error: log, track consecutive errors, apply backoff."""
        self._consecutive_errors += 1
        logger.warning("[%s] Poll #%d %s (error %d/%d)",
                        self._watcher_id, self._poll_count, msg,
                        self._consecutive_errors, _MAX_CONSECUTIVE_ERRORS)

        if self._consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
            new_interval = min(self._base_interval * _MAX_BACKOFF_MULTIPLIER, self._interval * 2)
            if new_interval != self._interval:
                self._interval = new_interval
                logger.warning("[%s] Backing off — interval now %.0fs", self._watcher_id, self._interval)


class WatcherEngine:
    """Manages multiple Watcher instances across threads.

    Handles signal registration, graceful shutdown, and thread lifecycle.
    """

    def __init__(self, store: SnapshotStore | None = None):
        self._store = store or SnapshotStore()
        self._shutdown = threading.Event()
        self._threads: list[threading.Thread] = []
        self._watchers: list[Watcher] = []

    def add_watcher(
        self,
        *,
        module_name: str,
        command: str,
        params: dict | None = None,
        interval: float = 60.0,
        output_mode: str = "stdout",
        output_path: str | None = None,
        webhook_url: str | None = None,
    ) -> str:
        """Create and register a Watcher. Returns the watcher_id.

        Raises ValueError if module/command is invalid or interval < 5s.
        """
        from sports_skills.cli import _REGISTRY, _load_module

        if interval < _MIN_INTERVAL:
            raise ValueError(f"Minimum interval is {_MIN_INTERVAL}s, got {interval}s")

        if module_name not in _REGISTRY:
            raise ValueError(f"Unknown module '{module_name}'. Available: {', '.join(_REGISTRY.keys())}")
        if command not in _REGISTRY[module_name]:
            raise ValueError(
                f"Unknown command '{command}' for module '{module_name}'. "
                f"Available: {', '.join(_REGISTRY[module_name].keys())}"
            )

        module = _load_module(module_name)
        params = params or {}
        watcher_id = _make_watcher_id(module_name, command, params)

        output = create_output(
            output_mode,
            path=output_path,
            url=webhook_url,
        )

        watcher = Watcher(
            watcher_id=watcher_id,
            module=module,
            command=command,
            params=params,
            interval=interval,
            output=output,
            store=self._store,
            shutdown_event=self._shutdown,
        )
        self._watchers.append(watcher)
        return watcher_id

    def run(self) -> None:
        """Start all watchers and block until shutdown (Ctrl+C or SIGTERM)."""
        if not self._watchers:
            _log("engine", "No watchers configured — nothing to do.")
            return

        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        # Print startup summary to stderr
        _log("engine", f"Starting {len(self._watchers)} watcher(s)...")
        for w in self._watchers:
            _log("engine", f"  {w.watcher_id} — every {w._base_interval:.0f}s")

        # Start threads
        for watcher in self._watchers:
            t = threading.Thread(target=watcher.run, name=f"watcher-{watcher.watcher_id}", daemon=True)
            self._threads.append(t)
            t.start()

        _log("engine", "Press Ctrl+C to stop.")

        # Block until shutdown
        try:
            while not self._shutdown.is_set():
                self._shutdown.wait(1.0)
        except KeyboardInterrupt:
            pass

        self._cleanup()

    def shutdown(self) -> None:
        """Programmatic shutdown (for SDK usage)."""
        self._shutdown.set()

    def _handle_signal(self, signum, frame) -> None:
        _log("engine", "Shutting down...")
        self._shutdown.set()

    def _cleanup(self) -> None:
        """Join threads and close resources."""
        for t in self._threads:
            t.join(timeout=5.0)

        for w in self._watchers:
            try:
                w._output.close()
            except Exception:
                pass

        try:
            self._store.close()
        except Exception:
            pass

        _log("engine", "Stopped.")


def _log(tag: str, msg: str) -> None:
    """Print operational message to stderr (keeps stdout clean for data)."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    sys.stderr.write(f"[watch {ts}] {tag}: {msg}\n")
    sys.stderr.flush()
