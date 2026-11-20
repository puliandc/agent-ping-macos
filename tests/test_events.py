import contextlib
import fcntl
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("agent_ping", str(ROOT / "bin/agent-ping"))
spec = importlib.util.spec_from_loader(loader.name, loader)
ping = importlib.util.module_from_spec(spec)
loader.exec_module(ping)


class EventTests(unittest.TestCase):
    def test_codex_turn_does_not_claim_whole_task_complete_or_copy_conversation(self):
        event = ping.codex_event(json.dumps({"type": "agent-turn-complete", "thread-id": "t", "turn-id": "u",
                                            "input-messages": ["private prompt"], "last-assistant-message": "private reply"}))
        self.assertEqual(event["kind"], "turn-complete")
        self.assertNotIn("private", json.dumps(event))
        self.assertEqual(event["id"], ping.codex_event(json.dumps({"type": "agent-turn-complete", "thread-id": "t", "turn-id": "u"}))["id"])

    def test_unsupported_codex_event_is_ignored(self):
        self.assertIsNone(ping.codex_event('{"type":"approval-requested"}'))

    def test_links_cannot_execute_commands_or_contain_credentials(self):
        for url in ["javascript:alert(1)", "file:///etc/passwd", "https://user:secret@example.com", "https://"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                ping.make_event("question", "test", "hello", url=url)

    def test_allowed_task_link_is_preserved(self):
        self.assertEqual(ping.make_event("question", "test", "hello", url="https://example.com/task")["url"], "https://example.com/task")

    def test_known_sources_select_their_installed_app_identifiers(self):
        for source, bundle in [("Codex", "com.openai.codex"), ("DSH", "com.deepseek.dsh"),
                               ("DeepSeek Harness", "com.deepseek.dsh"), ("飞书机器人", "com.electron.lark")]:
            with self.subTest(source=source):
                self.assertEqual(ping.make_event("question", source, "test")["appBundleId"], bundle)

    def test_explicit_app_overrides_source_default(self):
        self.assertEqual(ping.make_event("done", "DSH", "test", app_bundle_id="com.apple.Terminal")["appBundleId"], "com.apple.Terminal")
        with self.assertRaises(ValueError):
            ping.make_event("done", "DSH", "test", app_bundle_id="")

    def test_app_target_cannot_be_a_shell_command_or_file_path(self):
        for bundle in ["/Applications/App.app", "open -a Codex", "com.example;echo hello", ""]:
            with self.subTest(bundle=bundle), self.assertRaises(ValueError):
                ping.validate({**ping.make_event("done", "test", "test"), "appBundleId": bundle})

    def test_concurrent_retry_never_overwrites_pending_event_and_receipt_deduplicates(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "work") as folder:
            root = Path(folder)
            event = ping.make_event("done", "test", "first", event_id="same")
            self.assertTrue(ping.enqueue(event, root))
            self.assertFalse(ping.enqueue({**event, "message": "second"}, root))
            files = list((root / "inbox").iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text())["message"], "first")
            self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / "inbox").stat().st_mode & 0o777, 0o700)
            (root / "receipts" / files[0].name).touch()
            files[0].unlink()
            self.assertFalse(ping.enqueue(event, root))

    def test_dry_run_does_not_create_queue(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "work") as folder:
            root = Path(folder) / "nonexistent"
            old = os.environ.get("AGENTPING_DATA_DIR")
            os.environ["AGENTPING_DATA_DIR"] = str(root)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(ping.main(["demo", "--dry-run"]), 0)
                self.assertFalse(root.exists())
            finally:
                if old is None:
                    os.environ.pop("AGENTPING_DATA_DIR", None)
                else:
                    os.environ["AGENTPING_DATA_DIR"] = old

    def test_status_distinguishes_stale_file_from_running_instance(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "work") as folder:
            root = Path(folder)
            lock = root / "app.lock"
            lock.touch()
            self.assertFalse(ping.app_running(root))
            with lock.open("r+") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertTrue(ping.app_running(root))


if __name__ == "__main__":
    unittest.main()
