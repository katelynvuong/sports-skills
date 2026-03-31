"""Output handlers for watch change events — stdout, file (JSONL), webhook."""

from __future__ import annotations

import json
import logging
import sys
import urllib.request

logger = logging.getLogger("sports_skills.watch")


class OutputHandler:
    """Base class for emitting change events."""

    def emit(self, event: dict) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class StdoutOutput(OutputHandler):
    """Print change events as JSON lines to stdout."""

    def emit(self, event: dict) -> None:
        line = json.dumps(event, default=str, ensure_ascii=False)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


class FileOutput(OutputHandler):
    """Append change events as JSONL to a file."""

    def __init__(self, path: str):
        self._path = path

    def emit(self, event: dict) -> None:
        line = json.dumps(event, default=str, ensure_ascii=False)
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            logger.error("Failed to write to %s: %s", self._path, e)


class WebhookOutput(OutputHandler):
    """POST change events as JSON to a webhook URL."""

    def __init__(self, url: str, *, timeout: int = 10):
        self._url = url
        self._timeout = timeout

    def emit(self, event: dict) -> None:
        body = json.dumps(event, default=str, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                if resp.status >= 400:
                    logger.warning("Webhook returned %d for %s", resp.status, self._url)
        except Exception as e:
            logger.warning("Webhook POST to %s failed: %s", self._url, e)


def create_output(mode: str, **kwargs) -> OutputHandler:
    """Factory: create the right OutputHandler from mode string.

    Args:
        mode: "stdout", "file", or "webhook"
        path: Required for "file" mode.
        url: Required for "webhook" mode.
        timeout: Optional for "webhook" mode (default 10).
    """
    if mode == "stdout":
        return StdoutOutput()
    elif mode == "file":
        path = kwargs.get("path")
        if not path:
            raise ValueError("--output-path is required when --output=file")
        return FileOutput(path)
    elif mode == "webhook":
        url = kwargs.get("url")
        if not url:
            raise ValueError("--webhook-url is required when --output=webhook")
        timeout = int(kwargs.get("timeout", 10))
        return WebhookOutput(url, timeout=timeout)
    else:
        raise ValueError(f"Unknown output mode '{mode}'. Use: stdout, file, webhook")
