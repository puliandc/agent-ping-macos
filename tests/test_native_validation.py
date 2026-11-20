import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "dist/AgentPing.app/Contents/MacOS/AgentPing"


@unittest.skipUnless(BINARY.is_file(), "先运行 scripts/build，再验证原生事件读取")
class NativeValidationTests(unittest.TestCase):
    def validate(self, data):
        with tempfile.NamedTemporaryFile(dir=ROOT / "work", suffix=".json") as event:
            event.write(data)
            event.flush()
            return subprocess.run([str(BINARY), "--validate", event.name], capture_output=True, text=True, timeout=15)

    def event(self, **changes):
        value = {"id": "native-test", "kind": "question", "source": "测试来源", "title": "需要你处理",
                 "message": "正文", "url": None, "createdAt": "2026-11-17T00:00:00Z"}
        value.update(changes)
        return json.dumps(value, ensure_ascii=False).encode()

    def test_native_reader_accepts_unicode_events(self):
        result = self.validate(self.event())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("question", result.stdout)

    def test_native_reader_rejects_malformed_json(self):
        self.assertNotEqual(self.validate(b"{broken").returncode, 0)

    def test_native_reader_rejects_oversized_payload(self):
        self.assertNotEqual(self.validate(b" " * 65537).returncode, 0)

    def test_native_reader_rejects_unknown_kind(self):
        self.assertNotEqual(self.validate(self.event(kind="approve-and-run")).returncode, 0)

    def test_native_reader_accepts_app_target(self):
        self.assertEqual(self.validate(self.event(appBundleId="com.deepseek.dsh")).returncode, 0)

    def test_native_reader_rejects_app_paths_and_commands(self):
        for bundle in ["/Applications/App.app", "open -a Codex", "com.example;echo hello", ""]:
            with self.subTest(bundle=bundle):
                self.assertNotEqual(self.validate(self.event(appBundleId=bundle)).returncode, 0)

    def test_native_reader_rejects_executable_urls_and_missing_hosts(self):
        for url in ["javascript:alert(1)", "https://user:secret@example.com", "https://"]:
            with self.subTest(url=url):
                self.assertNotEqual(self.validate(self.event(url=url)).returncode, 0)
