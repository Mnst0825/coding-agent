import tempfile
import unittest
from pathlib import Path

from history import trim
from tools import execute_tool


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, name, **args):
        return execute_tool(name, args, workspace=self.ws)

    def test_write_and_read(self):
        self.run_tool("write_file", path="a/b.txt", content="x\ny")
        self.assertEqual(self.run_tool("read_file", path="a/b.txt"), "   1: x\n   2: y")

    def test_read_empty_file(self):
        self.run_tool("write_file", path="e.txt", content="")
        self.assertEqual(self.run_tool("read_file", path="e.txt"), "(空文件)")

    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):
            self.run_tool("read_file", path="../x")
        with self.assertRaises(ValueError):
            self.run_tool("write_file", path=str(Path(self.ws).resolve() / "x"), content="")

    def test_edit_file(self):
        self.run_tool("write_file", path="f.py", content="a = 1\nb = 2\n")
        self.run_tool("edit_file", path="f.py", old="b = 2", new="b = 3")
        self.assertEqual((Path(self.ws) / "f.py").read_text(encoding="utf-8"), "a = 1\nb = 3\n")

    def test_edit_file_requires_unique_match(self):
        self.run_tool("write_file", path="f.py", content="x\nx\n")
        with self.assertRaises(ValueError):
            self.run_tool("edit_file", path="f.py", old="x", new="y")
        with self.assertRaises(ValueError):
            self.run_tool("edit_file", path="f.py", old="z", new="y")

    def test_unknown_tool_and_args(self):
        with self.assertRaises(ValueError):
            self.run_tool("nope")
        with self.assertRaises(ValueError):
            self.run_tool("list_files", bogus=1)

    def test_list_hides_history_file(self):
        self.run_tool("write_file", path=".messages.json", content="[]")
        self.run_tool("write_file", path="k.txt", content="")
        self.assertEqual(self.run_tool("list_files"), "k.txt")

    def test_run_command_uses_workspace(self):
        self.run_tool("write_file", path="marker.txt", content="")
        out = self.run_tool("run_command", command="python -c \"import os;print(os.listdir())\"")
        self.assertIn("marker.txt", out)
        self.assertTrue(out.startswith("exit=0"))

    def test_dangerous_command_rejected(self):
        with self.assertRaises(ValueError):
            self.run_tool("run_command", command="shutdown /s")


class TrimTest(unittest.TestCase):
    def test_no_trim_when_short(self):
        msgs = [{"role": "system"}, {"role": "user"}]
        self.assertIs(trim(msgs, max_messages=40), msgs)

    def test_trim_does_not_start_with_orphan_tool(self):
        msgs = [{"role": "system", "content": "s"}]
        for i in range(10):
            msgs += [
                {"role": "user", "content": str(i)},
                {"role": "assistant", "tool_calls": [{"id": str(i)}]},
                {"role": "tool", "tool_call_id": str(i)},
            ]
        out = trim(msgs, max_messages=6)
        self.assertEqual(out[0]["role"], "system")
        self.assertEqual(out[1]["role"], "user")
        self.assertLessEqual(len(out), 6)


if __name__ == "__main__":
    unittest.main()
