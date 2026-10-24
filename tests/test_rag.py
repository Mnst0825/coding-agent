import tempfile
import unittest
from pathlib import Path

import rag


class RagTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        Path(self.tmp.name, "a.md").write_text(
            "# 标题\n\n## 运行测试\n用 unittest 运行单元测试。\n\n"
            "## 前端页面\n写 HTML 页面时内联 CSS。\n",
            encoding="utf-8",
        )
        self.index = rag.Index(rag.load_docs(Path(self.tmp.name)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_tokenize_mixed(self):
        self.assertEqual(rag.tokenize("运行pytest测试"), ["运行", "pytest", "测试"])
        self.assertEqual(rag.tokenize("单元测试"), ["单元", "元测", "测试"])

    def test_load_splits_by_heading(self):
        self.assertEqual([d.title for d in self.index.docs], ["运行测试", "前端页面"])

    def test_search_ranks_relevant_first(self):
        hits = self.index.search("帮我跑一下单元测试", top_k=2, min_score=0)
        self.assertEqual(hits[0][1].title, "运行测试")

    def test_irrelevant_query_returns_nothing(self):
        self.assertEqual(self.index.search("今天天气怎么样", min_score=0.5), [])


if __name__ == "__main__":
    unittest.main()
