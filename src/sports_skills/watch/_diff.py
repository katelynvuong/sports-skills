"""Change detection for the watch engine — hashing and structural JSON diffing."""

from __future__ import annotations

import hashlib
import json


def canonical_hash(data) -> str:
    """SHA-256 of canonical JSON (sorted keys, no whitespace)."""
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def quick_changed(old_hash: str | None, new_hash: str) -> bool:
    """Fast check: did the data change? True if old_hash is None (first poll)."""
    if old_hash is None:
        return True
    return old_hash != new_hash


def compute_diff(old, new, *, _path: str = "", _depth: int = 0, max_depth: int = 5) -> list[dict]:
    """Compute structural diff between two JSON-serializable values.

    Returns a list of change entries:
        [{"path": "events[0].score", "old": 14, "new": 21, "type": "modified"}, ...]

    Types: "added", "removed", "modified".
    """
    if _depth >= max_depth:
        if old != new:
            return [{"path": _path or "(root)", "old": old, "new": new, "type": "modified"}]
        return []

    changes: list[dict] = []

    if isinstance(old, dict) and isinstance(new, dict):
        all_keys = set(old) | set(new)
        for key in sorted(all_keys):
            child_path = f"{_path}.{key}" if _path else key
            if key not in old:
                changes.append({"path": child_path, "old": None, "new": new[key], "type": "added"})
            elif key not in new:
                changes.append({"path": child_path, "old": old[key], "new": None, "type": "removed"})
            else:
                changes.extend(
                    compute_diff(old[key], new[key], _path=child_path, _depth=_depth + 1, max_depth=max_depth)
                )

    elif isinstance(old, list) and isinstance(new, list):
        min_len = min(len(old), len(new))
        for i in range(min_len):
            child_path = f"{_path}[{i}]"
            changes.extend(
                compute_diff(old[i], new[i], _path=child_path, _depth=_depth + 1, max_depth=max_depth)
            )
        for i in range(min_len, len(new)):
            changes.append({"path": f"{_path}[{i}]", "old": None, "new": new[i], "type": "added"})
        for i in range(min_len, len(old)):
            changes.append({"path": f"{_path}[{i}]", "old": old[i], "new": None, "type": "removed"})

    elif old != new:
        changes.append({"path": _path or "(root)", "old": old, "new": new, "type": "modified"})

    return changes


def build_diff_summary(changes: list[dict]) -> dict:
    """Build a diff result with summary from a list of changes.

    Returns:
        {"changed": bool, "summary": str, "changes": [...]}
    """
    if not changes:
        return {"changed": False, "summary": "no changes", "changes": []}

    added = sum(1 for c in changes if c["type"] == "added")
    removed = sum(1 for c in changes if c["type"] == "removed")
    modified = sum(1 for c in changes if c["type"] == "modified")

    parts = []
    if modified:
        parts.append(f"{modified} modified")
    if added:
        parts.append(f"{added} added")
    if removed:
        parts.append(f"{removed} removed")

    return {
        "changed": True,
        "summary": ", ".join(parts),
        "changes": changes,
    }
