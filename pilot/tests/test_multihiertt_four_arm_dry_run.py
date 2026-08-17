import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PILOT_DIR = os.path.join(ROOT, "pilot")
MULTIBENCH_DIR = os.path.join(PILOT_DIR, "multibench")
for path in (PILOT_DIR, MULTIBENCH_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import llm  # noqa: E402
import multihiertt_four_arm_dry_run as dry_run  # noqa: E402


class _FakeResponse:
    status_code = 200
    text = '{"ok": true}'

    def json(self):
        return {
            "model": "deepseek-v4-flash",
            "system_fingerprint": "fp-test",
            "choices": [{"message": {"content": '{"answer": 42}'}, "finish_reason": "stop"}],
        }


class MultiHierttFourArmDryRunTest(unittest.TestCase):
    def test_parse_answer_accepts_json_answer(self):
        parsed, err = dry_run.parse_answer('{"answer": ["A", "B"]}')
        self.assertIsNone(err)
        self.assertEqual(parsed, ["A", "B"])

    def test_parse_answer_handles_fenced_json(self):
        parsed, err = dry_run.parse_answer('```json\n{"answer": "$46.4 million"}\n```')
        self.assertIsNone(err)
        self.assertEqual(parsed, "$46.4 million")

    def test_parse_answer_conservatively_extracts_invalid_json_answer_value(self):
        parsed, err = dry_run.parse_answer('{"answer": 45.86%}')
        self.assertIsNone(err)
        self.assertEqual(parsed, "45.86%")

        parsed, err = dry_run.parse_answer('{"answer": 807 * (807 / 1061) = 613.6"}')
        self.assertIsNone(err)
        self.assertEqual(parsed, "807 * (807 / 1061) = 613.6")

    def test_deepseek_payload_disables_thinking_and_can_request_json_mode(self):
        captured = {}

        def fake_post(url, headers, json, timeout):
            captured["url"] = url
            captured["payload"] = json
            return _FakeResponse()

        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "test-key",
                "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
                "DEEPSEEK_MODEL": "deepseek-v4-flash",
            },
            clear=False,
        ), patch("llm.httpx.post", side_effect=fake_post):
            out = llm.call_once_with_metadata(
                [{"role": "user", "content": "Return JSON."}],
                max_tokens=10,
                temperature=0,
                response_format={"type": "json_object"},
            )

        self.assertEqual(out["text"], '{"answer": 42}')
        self.assertEqual(captured["payload"]["thinking"], {"type": "disabled"})
        self.assertEqual(captured["payload"]["response_format"], {"type": "json_object"})

    def test_cache_rejects_runtime_drift(self):
        good_runtime = dict(dry_run.EXPECTED_RUNTIME)
        good_runtime.update({
            "system_fingerprint": "fp-a",
            "model_version": "fp-a",
            "effective_model": "deepseek-v4-flash",
            "endpoint": "https://api.deepseek.com/chat/completions",
        })
        bad_runtime = dict(good_runtime)
        bad_runtime["system_fingerprint"] = "fp-b"
        bad_runtime["model_version"] = "fp-b"

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cache.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "key": "a",
                    "uid": "u1",
                    "arm": "none",
                    "raw_response": '{"answer": 1}',
                    "answer": 1,
                    "parse_error": None,
                    "runtime": good_runtime,
                }) + "\n")
                f.write(json.dumps({
                    "key": "b",
                    "uid": "u2",
                    "arm": "case",
                    "raw_response": '{"answer": 2}',
                    "answer": 2,
                    "parse_error": None,
                    "runtime": bad_runtime,
                }) + "\n")

            with self.assertRaisesRegex(RuntimeError, "Invalid execution cache record"):
                dry_run.ExecCache(path)


if __name__ == "__main__":
    unittest.main()
