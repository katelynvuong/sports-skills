"""Tests for the watch module — diff, storage, output, engine."""

import json
import os
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _diff tests
# ---------------------------------------------------------------------------

class TestCanonicalHash:
    def test_deterministic(self):
        from sports_skills.watch._diff import canonical_hash

        data = {"b": 2, "a": 1}
        assert canonical_hash(data) == canonical_hash({"a": 1, "b": 2})

    def test_different_data_different_hash(self):
        from sports_skills.watch._diff import canonical_hash

        h1 = canonical_hash({"score": 14})
        h2 = canonical_hash({"score": 21})
        assert h1 != h2

    def test_nested_sorting(self):
        from sports_skills.watch._diff import canonical_hash

        d1 = {"outer": {"z": 1, "a": 2}}
        d2 = {"outer": {"a": 2, "z": 1}}
        assert canonical_hash(d1) == canonical_hash(d2)


class TestQuickChanged:
    def test_none_old_hash_is_changed(self):
        from sports_skills.watch._diff import quick_changed

        assert quick_changed(None, "abc") is True

    def test_same_hash_not_changed(self):
        from sports_skills.watch._diff import quick_changed

        assert quick_changed("abc", "abc") is False

    def test_different_hash_is_changed(self):
        from sports_skills.watch._diff import quick_changed

        assert quick_changed("abc", "def") is True


class TestComputeDiff:
    def test_no_changes(self):
        from sports_skills.watch._diff import compute_diff

        assert compute_diff({"a": 1}, {"a": 1}) == []

    def test_modified_value(self):
        from sports_skills.watch._diff import compute_diff

        changes = compute_diff({"score": 14}, {"score": 21})
        assert len(changes) == 1
        assert changes[0]["type"] == "modified"
        assert changes[0]["path"] == "score"
        assert changes[0]["old"] == 14
        assert changes[0]["new"] == 21

    def test_added_key(self):
        from sports_skills.watch._diff import compute_diff

        changes = compute_diff({"a": 1}, {"a": 1, "b": 2})
        assert len(changes) == 1
        assert changes[0]["type"] == "added"
        assert changes[0]["path"] == "b"

    def test_removed_key(self):
        from sports_skills.watch._diff import compute_diff

        changes = compute_diff({"a": 1, "b": 2}, {"a": 1})
        assert len(changes) == 1
        assert changes[0]["type"] == "removed"
        assert changes[0]["path"] == "b"

    def test_nested_change(self):
        from sports_skills.watch._diff import compute_diff

        old = {"game": {"score": {"home": 14, "away": 7}}}
        new = {"game": {"score": {"home": 21, "away": 7}}}
        changes = compute_diff(old, new)
        assert len(changes) == 1
        assert changes[0]["path"] == "game.score.home"

    def test_list_modification(self):
        from sports_skills.watch._diff import compute_diff

        old = {"items": [1, 2, 3]}
        new = {"items": [1, 99, 3]}
        changes = compute_diff(old, new)
        assert len(changes) == 1
        assert changes[0]["path"] == "items[1]"

    def test_list_added_element(self):
        from sports_skills.watch._diff import compute_diff

        changes = compute_diff({"items": [1]}, {"items": [1, 2]})
        assert len(changes) == 1
        assert changes[0]["type"] == "added"
        assert changes[0]["path"] == "items[1]"

    def test_list_removed_element(self):
        from sports_skills.watch._diff import compute_diff

        changes = compute_diff({"items": [1, 2]}, {"items": [1]})
        assert len(changes) == 1
        assert changes[0]["type"] == "removed"

    def test_max_depth(self):
        from sports_skills.watch._diff import compute_diff

        old = {"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}
        new = {"a": {"b": {"c": {"d": {"e": {"f": 2}}}}}}
        changes = compute_diff(old, new, max_depth=3)
        assert len(changes) == 1
        # Should stop at depth 3 and report the subtree as modified
        assert changes[0]["type"] == "modified"


class TestBuildDiffSummary:
    def test_no_changes(self):
        from sports_skills.watch._diff import build_diff_summary

        result = build_diff_summary([])
        assert result["changed"] is False

    def test_with_changes(self):
        from sports_skills.watch._diff import build_diff_summary

        changes = [
            {"path": "a", "old": 1, "new": 2, "type": "modified"},
            {"path": "b", "old": None, "new": 3, "type": "added"},
        ]
        result = build_diff_summary(changes)
        assert result["changed"] is True
        assert "1 modified" in result["summary"]
        assert "1 added" in result["summary"]
        assert len(result["changes"]) == 2


# ---------------------------------------------------------------------------
# _storage tests
# ---------------------------------------------------------------------------

class TestSnapshotStore:
    def test_get_missing_returns_none(self):
        from sports_skills.watch._storage import SnapshotStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            try:
                text, h = store.get_snapshot("nonexistent")
                assert text is None
                assert h is None
            finally:
                store.close()

    def test_save_and_get(self):
        from sports_skills.watch._storage import SnapshotStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            try:
                store.save_snapshot("w1", '{"score":14}', "abc123")
                text, h = store.get_snapshot("w1")
                assert text == '{"score":14}'
                assert h == "abc123"
            finally:
                store.close()

    def test_upsert_overwrites(self):
        from sports_skills.watch._storage import SnapshotStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            try:
                store.save_snapshot("w1", '{"v":1}', "hash1")
                store.save_snapshot("w1", '{"v":2}', "hash2")
                text, h = store.get_snapshot("w1")
                assert text == '{"v":2}'
                assert h == "hash2"
            finally:
                store.close()

    def test_delete(self):
        from sports_skills.watch._storage import SnapshotStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            try:
                store.save_snapshot("w1", "{}", "h")
                store.delete_snapshot("w1")
                text, h = store.get_snapshot("w1")
                assert text is None
            finally:
                store.close()

    def test_list_watchers(self):
        from sports_skills.watch._storage import SnapshotStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            try:
                store.save_snapshot("w1", "{}", "h1")
                store.save_snapshot("w2", "{}", "h2")
                watchers = store.list_watchers()
                ids = [w["watcher_id"] for w in watchers]
                assert "w1" in ids
                assert "w2" in ids
            finally:
                store.close()

    def test_prune_old_entries(self):
        from sports_skills.watch._storage import SnapshotStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            try:
                store.save_snapshot("w1", "{}", "h1")
                # Manually backdate
                store._conn.execute(
                    "UPDATE snapshots SET updated_at = ? WHERE watcher_id = ?",
                    (time.time() - 999999, "w1"),
                )
                store._conn.commit()
                pruned = store.prune(max_age_seconds=1000)
                assert pruned == 1
                text, _ = store.get_snapshot("w1")
                assert text is None
            finally:
                store.close()


# ---------------------------------------------------------------------------
# _output tests
# ---------------------------------------------------------------------------

class TestOutputHandlers:
    def test_stdout_output(self, capsys):
        from sports_skills.watch._output import StdoutOutput

        handler = StdoutOutput()
        handler.emit({"test": True})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["test"] is True

    def test_file_output(self):
        from sports_skills.watch._output import FileOutput

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            handler = FileOutput(path)
            handler.emit({"event": 1})
            handler.emit({"event": 2})

            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
            assert len(lines) == 2
            assert json.loads(lines[0])["event"] == 1
            assert json.loads(lines[1])["event"] == 2
        finally:
            os.unlink(path)

    def test_create_output_stdout(self):
        from sports_skills.watch._output import StdoutOutput, create_output

        handler = create_output("stdout")
        assert isinstance(handler, StdoutOutput)

    def test_create_output_file(self):
        from sports_skills.watch._output import FileOutput, create_output

        handler = create_output("file", path="/tmp/test.jsonl")
        assert isinstance(handler, FileOutput)

    def test_create_output_file_missing_path(self):
        from sports_skills.watch._output import create_output

        with pytest.raises(ValueError, match="output-path"):
            create_output("file")

    def test_create_output_webhook_missing_url(self):
        from sports_skills.watch._output import create_output

        with pytest.raises(ValueError, match="webhook-url"):
            create_output("webhook")

    def test_create_output_unknown_mode(self):
        from sports_skills.watch._output import create_output

        with pytest.raises(ValueError, match="Unknown output mode"):
            create_output("kafka")


# ---------------------------------------------------------------------------
# _engine tests
# ---------------------------------------------------------------------------

class TestMakeWatcherId:
    def test_deterministic(self):
        from sports_skills.watch._engine import _make_watcher_id

        id1 = _make_watcher_id("nfl", "get_scoreboard", {"date": "2026-01-15"})
        id2 = _make_watcher_id("nfl", "get_scoreboard", {"date": "2026-01-15"})
        assert id1 == id2

    def test_different_params_different_id(self):
        from sports_skills.watch._engine import _make_watcher_id

        id1 = _make_watcher_id("nfl", "get_scoreboard", {"date": "2026-01-15"})
        id2 = _make_watcher_id("nfl", "get_scoreboard", {"date": "2026-01-16"})
        assert id1 != id2

    def test_none_params_excluded(self):
        from sports_skills.watch._engine import _make_watcher_id

        id1 = _make_watcher_id("nfl", "get_scoreboard", {"date": None})
        id2 = _make_watcher_id("nfl", "get_scoreboard", {})
        assert id1 == id2

    def test_param_order_irrelevant(self):
        from sports_skills.watch._engine import _make_watcher_id

        id1 = _make_watcher_id("nfl", "cmd", {"a": 1, "b": 2})
        id2 = _make_watcher_id("nfl", "cmd", {"b": 2, "a": 1})
        assert id1 == id2


class TestWatcherEngine:
    def test_add_watcher_invalid_module(self):
        from sports_skills.watch._engine import WatcherEngine
        from sports_skills.watch._storage import SnapshotStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            engine = WatcherEngine(store=store)
            try:
                with pytest.raises(ValueError, match="Unknown module"):
                    engine.add_watcher(module_name="fakesport", command="get_scores")
            finally:
                store.close()

    def test_add_watcher_invalid_command(self):
        from sports_skills.watch._engine import WatcherEngine
        from sports_skills.watch._storage import SnapshotStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            engine = WatcherEngine(store=store)
            try:
                with pytest.raises(ValueError, match="Unknown command"):
                    engine.add_watcher(module_name="nfl", command="fake_command")
            finally:
                store.close()

    def test_add_watcher_interval_too_low(self):
        from sports_skills.watch._engine import WatcherEngine
        from sports_skills.watch._storage import SnapshotStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            engine = WatcherEngine(store=store)
            try:
                with pytest.raises(ValueError, match="Minimum interval"):
                    engine.add_watcher(module_name="nfl", command="get_scoreboard", interval=2)
            finally:
                store.close()

    def test_add_watcher_returns_id(self):
        from sports_skills.watch._engine import WatcherEngine
        from sports_skills.watch._storage import SnapshotStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            engine = WatcherEngine(store=store)
            try:
                wid = engine.add_watcher(module_name="nfl", command="get_scoreboard", interval=10)
                assert "nfl:get_scoreboard" in wid
            finally:
                store.close()

    def test_run_no_watchers(self, capsys):
        from sports_skills.watch._engine import WatcherEngine
        from sports_skills.watch._storage import SnapshotStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            engine = WatcherEngine(store=store)
            engine.run()
            captured = capsys.readouterr()
            assert "No watchers" in captured.err


class TestWatcherPollOnce:
    """Test the Watcher._poll_once method with mocked modules."""

    def test_first_poll_saves_baseline(self):
        from sports_skills.watch._engine import Watcher
        from sports_skills.watch._output import StdoutOutput
        from sports_skills.watch._storage import SnapshotStore

        mock_module = MagicMock()
        mock_module.__name__ = "sports_skills.nfl"
        mock_module.get_scoreboard.return_value = {
            "status": True,
            "data": {"events": [{"score": 14}]},
            "message": "ok",
        }

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            output = StdoutOutput()
            shutdown = threading.Event()

            watcher = Watcher(
                watcher_id="nfl:get_scoreboard:{}",
                module=mock_module,
                command="get_scoreboard",
                params={},
                interval=60,
                output=output,
                store=store,
                shutdown_event=shutdown,
            )

            with patch.object(output, "emit") as mock_emit:
                watcher._poll_once()

                # Should NOT emit on first poll (baseline)
                mock_emit.assert_not_called()

                # Should save snapshot
                text, h = store.get_snapshot("nfl:get_scoreboard:{}")
                assert text is not None
                assert h is not None

            store.close()

    def test_second_poll_with_change_emits_event(self):
        from sports_skills.watch._engine import Watcher
        from sports_skills.watch._output import StdoutOutput
        from sports_skills.watch._storage import SnapshotStore

        mock_module = MagicMock()
        mock_module.__name__ = "sports_skills.nfl"

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            output = StdoutOutput()
            shutdown = threading.Event()

            watcher = Watcher(
                watcher_id="nfl:get_scoreboard:{}",
                module=mock_module,
                command="get_scoreboard",
                params={},
                interval=60,
                output=output,
                store=store,
                shutdown_event=shutdown,
            )

            # First poll — baseline
            mock_module.get_scoreboard.return_value = {
                "status": True,
                "data": {"score": 14},
                "message": "ok",
            }
            watcher._poll_once()

            # Second poll — data changed
            mock_module.get_scoreboard.return_value = {
                "status": True,
                "data": {"score": 21},
                "message": "ok",
            }

            with patch.object(output, "emit") as mock_emit:
                watcher._poll_once()
                mock_emit.assert_called_once()
                event = mock_emit.call_args[0][0]
                assert event["diff"]["changed"] is True
                assert event["data"]["score"] == 21
                assert event["poll_number"] == 2

            store.close()

    def test_no_change_does_not_emit(self):
        from sports_skills.watch._engine import Watcher
        from sports_skills.watch._output import StdoutOutput
        from sports_skills.watch._storage import SnapshotStore

        mock_module = MagicMock()
        mock_module.__name__ = "sports_skills.nfl"

        data = {"status": True, "data": {"score": 14}, "message": "ok"}
        mock_module.get_scoreboard.return_value = data

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            output = StdoutOutput()
            shutdown = threading.Event()

            watcher = Watcher(
                watcher_id="nfl:get_scoreboard:{}",
                module=mock_module,
                command="get_scoreboard",
                params={},
                interval=60,
                output=output,
                store=store,
                shutdown_event=shutdown,
            )

            watcher._poll_once()  # baseline

            with patch.object(output, "emit") as mock_emit:
                watcher._poll_once()  # same data
                mock_emit.assert_not_called()

            store.close()

    def test_error_response_does_not_emit(self):
        from sports_skills.watch._engine import Watcher
        from sports_skills.watch._output import StdoutOutput
        from sports_skills.watch._storage import SnapshotStore

        mock_module = MagicMock()
        mock_module.__name__ = "sports_skills.nfl"
        mock_module.get_scoreboard.return_value = {
            "status": False,
            "data": None,
            "message": "API error",
        }

        with tempfile.TemporaryDirectory() as tmp:
            store = SnapshotStore(db_path=os.path.join(tmp, "test.db"))
            output = StdoutOutput()
            shutdown = threading.Event()

            watcher = Watcher(
                watcher_id="nfl:get_scoreboard:{}",
                module=mock_module,
                command="get_scoreboard",
                params={},
                interval=60,
                output=output,
                store=store,
                shutdown_event=shutdown,
            )

            with patch.object(output, "emit") as mock_emit:
                watcher._poll_once()
                mock_emit.assert_not_called()

            store.close()


# ---------------------------------------------------------------------------
# Module import smoke test
# ---------------------------------------------------------------------------

class TestWatchImports:
    def test_watch_module_imports(self):
        import sports_skills.watch

        assert sports_skills.watch is not None

    def test_public_api_available(self):
        from sports_skills.watch import make_watcher_id, start_watcher, start_watchers_from_config

        assert callable(start_watcher)
        assert callable(start_watchers_from_config)
        assert callable(make_watcher_id)
