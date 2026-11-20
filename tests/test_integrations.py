import importlib.machinery
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    result = importlib.util.module_from_spec(spec)
    loader.exec_module(result)
    return result


receiver = module("receiver", ROOT / "integrations/receive.py")
installer = module("installer", ROOT / "scripts/install-integrations")


class IntegrationTests(unittest.TestCase):
    def test_codex_completion_is_turn_scoped_and_does_not_copy_content(self):
        event = receiver.translate("codex", {"hook_event_name": "Stop", "session_id": "s", "turn_id": "t",
                                              "last_assistant_message": "private reply", "transcript_path": "private path"})
        self.assertEqual(event["kind"], "turn-complete")
        self.assertEqual(event["appBundleId"], "com.openai.codex")
        self.assertNotIn("private", json.dumps(event))
        self.assertEqual(event["id"], receiver.translate("codex", {"hook_event_name": "Stop", "session_id": "s", "turn_id": "t"})["id"])

    def test_approval_requests_do_not_collapse_different_approvals_in_one_turn(self):
        data = {"hook_event_name": "PermissionRequest", "session_id": "s", "turn_id": "t", "tool_name": "Bash"}
        first, second = receiver.translate("codex", data), receiver.translate("codex", data)
        self.assertEqual(first["kind"], "question")
        self.assertNotEqual(first["id"], second["id"])

    def test_question_tool_names_and_async_names_are_supported(self):
        for name in ["request_user_input", "functions.request_user_input_async", "mcp__app__request_user_input", "ask_user_question"]:
            with self.subTest(name=name):
                event = receiver.translate("codex", {"hook_event_name": "PreToolUse", "tool_name": name, "tool_use_id": "call1"})
                self.assertEqual(event["kind"], "question")

    def test_ordinary_tool_use_does_not_notify(self):
        self.assertIsNone(receiver.translate("codex", {"hook_event_name": "PreToolUse", "tool_name": "Bash"}))

    def test_dsh_end_question_approval_and_error(self):
        for trigger, kind in [("TurnCompleted", "turn-complete"), ("QuestionRequested", "question"),
                              ("ApprovalRequested", "question"), ("TurnFailed", "error")]:
            with self.subTest(trigger=trigger):
                event = receiver.translate("dsh", {"hook_event_name": trigger, "event_id": "event-1"})
                self.assertEqual(event["kind"], kind)
                self.assertEqual(event["appBundleId"], "com.deepseek.dsh")

    def test_feishu_is_not_a_supported_integration(self):
        with self.assertRaises(ValueError):
            receiver.translate("feishu", {"hook_event_name": "Stop"})

    def test_codex_install_preserves_other_handlers_and_is_idempotent(self):
        old = {"description": "existing", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "existing-notifier"}]}]}}
        once = installer.merge_codex(old)
        self.assertEqual(once, installer.merge_codex(once))
        self.assertEqual(once["hooks"]["Stop"][0]["hooks"][0]["command"], "existing-notifier")
        self.assertEqual(installer.merge_codex(once, False), old)

    def test_dsh_install_preserves_original_config_and_can_be_removed(self):
        old = "# existing settings\n- id: example\n  config:\n    enabled: true\n"
        once = installer.merge_dsh(old)
        self.assertEqual(once, installer.merge_dsh(once))
        self.assertEqual(installer.merge_dsh(once, False), old)

    def test_only_human_interaction_tools_are_matched(self):
        import re
        matcher = re.compile(installer.codex_groups()["PreToolUse"]["matcher"])
        self.assertIsNotNone(matcher.search("functions.request_user_input_async"))
        self.assertIsNone(matcher.search("functions.exec_command"))


if __name__ == "__main__":
    unittest.main()
