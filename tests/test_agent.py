import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import agent


def fake_reply(content=None, tool_calls=None, usage=(100, 20)):
    msg = NS(content=content, tool_calls=tool_calls)
    u = None if usage is None else NS(
        prompt_tokens=usage[0], completion_tokens=usage[1],
        total_tokens=sum(usage), prompt_tokens_details=NS(cached_tokens=10),
    )
    return msg, u


class AgentStatsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def test_usage_accumulated_and_logged(self):
        call = NS(id="c1", function=NS(name="list_files", arguments="{}"))
        replies = [
            fake_reply(tool_calls=[call], usage=(100, 20)),
            fake_reply(content="完成", usage=(150, 30)),
        ]
        with mock.patch.object(agent, "chat", side_effect=replies):
            a = agent.Agent(workspace=self.tmp.name)
            self.assertEqual(a.run("列出文件"), "完成")

        s = a.stats
        self.assertEqual(s["status"], "done")
        self.assertEqual((s["steps"], s["llm_calls"]), (2, 2))
        self.assertEqual((s["prompt_tokens"], s["completion_tokens"], s["total_tokens"]), (250, 50, 300))
        self.assertEqual(s["cached_tokens"], 20)
        self.assertEqual(s["tool_calls"], {"list_files": 1})

        lines = Path("logs/usage.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertEqual(row["total_tokens"], 300)
        detail = json.loads(Path(row["log"]).read_text(encoding="utf-8"))
        self.assertEqual(detail["stats"]["total_tokens"], 300)

    def test_missing_usage_and_error_still_logged(self):
        replies = [fake_reply(content="ok", usage=None)]
        with mock.patch.object(agent, "chat", side_effect=replies):
            a = agent.Agent(workspace=self.tmp.name)
            a.run("x")
        self.assertEqual(a.stats["usage_missing"], 1)
        self.assertEqual(a.stats["total_tokens"], 0)

        with mock.patch.object(agent, "chat", side_effect=RuntimeError("boom")), \
                mock.patch.object(agent.time, "sleep"):
            a = agent.Agent(workspace=self.tmp.name)
            with self.assertRaises(RuntimeError):
                a.run("y")
        self.assertEqual(a.stats["status"], "error")
        self.assertEqual(a.stats["api_errors"], agent.MAX_API_ERRORS)
        rows = Path("logs/usage.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(rows[-1])["status"], "error")


if __name__ == "__main__":
    unittest.main()
