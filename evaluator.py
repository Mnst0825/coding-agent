"""对智能体的最终回答做自动评估，不达标时给出修改意见，供智能体再生成。"""
import json
import os
import re

from llm import complete

EVAL_ENABLED = os.environ.get("EVAL_ENABLED", "1") != "0"
EVAL_MIN_SCORE = int(os.environ.get("EVAL_MIN_SCORE", 7))
EVAL_MAX_ROUNDS = int(os.environ.get("EVAL_MAX_ROUNDS", 1))
MAX_TRACE_CHARS = 6000

EVAL_PROMPT = """你是严格的代码任务评审员。根据用户任务、智能体的执行过程和最终回答，判断任务是否真正完成。

评分标准（1-10 分）：
- 是否完成了任务的全部要求，没有遗漏
- 是否真的运行验证过（看执行过程里的命令输出），而不是只声称完成
- 执行过程中的报错是否都已解决
- 最终总结是否如实反映了做了什么、结果如何

只输出一个 JSON 对象，不要输出其他内容：
{"score": 整数1-10, "issues": ["具体问题1", "具体问题2"], "suggestion": "下一步应该怎么改，一两句话"}
任务已完整完成时 issues 为空数组。"""


def build_trace(messages) -> str:
    """把本轮任务的工具调用和结果压缩成文本，过长时保留末尾。"""
    lines = []
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                fn = tc["function"]
                lines.append(f"[调用] {fn['name']}({(fn.get('arguments') or '')[:300]})")
        elif m.get("role") == "tool":
            lines.append(f"[结果] {(m.get('content') or '')[:500]}")
    trace = "\n".join(lines) or "(没有调用任何工具)"
    if len(trace) > MAX_TRACE_CHARS:
        trace = "...[前面已省略]\n" + trace[-MAX_TRACE_CHARS:]
    return trace


def parse_verdict(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        score = int(data["score"])
    except (ValueError, KeyError, TypeError):
        return None
    issues = data.get("issues") or []
    if not isinstance(issues, list):
        issues = [str(issues)]
    return {
        "score": max(1, min(10, score)),
        "issues": [str(i) for i in issues],
        "suggestion": str(data.get("suggestion") or ""),
    }


def evaluate(task: str, trace_messages, answer: str):
    """返回 (verdict, usage)。评估失败或解析不了时 verdict 为 None，调用方应直接放行。"""
    text, usage = complete([
        {"role": "system", "content": EVAL_PROMPT},
        {
            "role": "user",
            "content": f"## 用户任务\n{task}\n\n## 执行过程\n{build_trace(trace_messages)}"
                       f"\n\n## 最终回答\n{answer or '(空)'}",
        },
    ])
    return parse_verdict(text), usage


def feedback_message(verdict: dict) -> str:
    issues = "\n".join(f"- {i}" for i in verdict["issues"]) or "- (未列出具体问题)"
    return (
        f"【自动评估】本次结果得分 {verdict['score']}/10，未达到 {EVAL_MIN_SCORE} 分。\n"
        f"存在的问题：\n{issues}\n"
        f"修改建议：{verdict['suggestion'] or '无'}\n\n"
        "请针对以上问题继续修改并运行验证，完成后重新用中文总结。"
    )
