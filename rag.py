"""轻量 RAG：从 knowledge/*.md 中检索与任务相关的经验，拼进提示词。

每个 Markdown 文件按 "## 标题" 切分成条目，用 BM25 做关键词检索，
中文按相邻两字切词，英文按单词切词，不依赖向量模型和额外库。
"""
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

KNOWLEDGE_DIR = Path(os.environ.get("RAG_DIR", Path(__file__).parent / "knowledge"))
TOP_K = int(os.environ.get("RAG_TOP_K", 3))
MIN_SCORE = float(os.environ.get("RAG_MIN_SCORE", 1.0))

_WORD = re.compile(r"[a-z0-9_.+#-]+|[一-鿿]+")


@dataclass
class Doc:
    source: str
    title: str
    text: str


def tokenize(text: str) -> list[str]:
    tokens = []
    for w in _WORD.findall(text.lower()):
        if "一" <= w[0] <= "鿿":
            tokens += [w] if len(w) == 1 else [w[i:i + 2] for i in range(len(w) - 1)]
        else:
            tokens.append(w.strip(".-"))
    return [t for t in tokens if t]


def load_docs(root: Path = KNOWLEDGE_DIR) -> list[Doc]:
    docs = []
    for f in sorted(Path(root).glob("**/*.md")):
        text = f.read_text(encoding="utf-8")
        for part in re.split(r"^## ", text, flags=re.M)[1:]:
            title, _, body = part.partition("\n")
            if body.strip():
                docs.append(Doc(f.name, title.strip(), body.strip()))
    return docs


class Index:
    def __init__(self, docs: list[Doc], k1=1.5, b=0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.tfs = [Counter(tokenize(d.title + " " + d.text)) for d in docs]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avg_len = sum(self.lens) / len(docs) if docs else 0
        df = Counter(t for tf in self.tfs for t in tf)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def search(self, query: str, top_k=TOP_K, min_score=MIN_SCORE):
        q = set(tokenize(query))
        scored = []
        for doc, tf, dl in zip(self.docs, self.tfs, self.lens):
            score = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    score += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * dl / self.avg_len)
                    )
            if score >= min_score:
                scored.append((score, doc))
        scored.sort(key=lambda x: -x[0])
        return scored[:top_k]


_cache: tuple[float, Index] | None = None


def get_index() -> Index:
    """知识库文件有改动时自动重建索引，改完 md 不用重启服务。"""
    global _cache
    files = list(KNOWLEDGE_DIR.glob("**/*.md"))
    mtime = max((f.stat().st_mtime for f in files), default=0) + len(files)
    if _cache is None or _cache[0] != mtime:
        _cache = (mtime, Index(load_docs()))
    return _cache[1]


def build_context(task: str) -> tuple[str, list[str]]:
    """返回 (要拼进提示词的参考知识, 命中的条目名列表)。没命中时返回空串。"""
    hits = get_index().search(task)
    if not hits:
        return "", []
    blocks = [f"### {d.title}\n{d.text}" for _, d in hits]
    names = [f"{d.source}#{d.title} ({s:.2f})" for s, d in hits]
    context = (
        "以下是知识库中可能相关的经验，仅供参考，与任务无关时请忽略：\n\n"
        + "\n\n".join(blocks)
    )
    return context, names
