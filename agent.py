import json
import os
import platform
import time

from llm import chat
from tools import TOOL_SCHEMAS, execute_tool
from history import trim, truncate_tool_result
from rag import build_context

MAX_API_ERRORS = 3

if platform.system() == "Windows":
    SHELL_HINT = "运行环境是 Windows，shell 命令请使用 Windows 兼容写法（如 dir 而不是 ls）。"
else:
    SHELL_HINT = f"运行环境是 {platform.system()}，shell 命令请使用 POSIX 写法。"

SYSTEM_PROMPT = """你是一个编程智能体。
你只能通过工具读写文件和执行命令。
当前工作目录是：{workspace}
{shell_hint}

工作流程：
1. 先用 list_files 探索目录。
2. 用 read_file 查看关键文件，不要凭猜测改代码。
3. 修改已有文件时优先用 edit_file 局部替换，避免整文件重写；新建文件用 write_file。
4. 写完代码后运行测试或命令验证。
5. 如果报错，读错误信息，自己修，再运行，最多重试 3 次。
6. 任务完成时，用中文总结改了哪些文件、运行了什么、结果如何。
"""

def save_log(messages, task, stats=None):
    os.makedirs("logs", exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    safe_task = "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in task[:30]
    )
    path = f"logs/{ts}_{safe_task}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"task": task, "stats": stats, "messages": messages},
            f, ensure_ascii=False, indent=2,
        )
    if stats is not None:
        # 每个任务一行，方便汇总统计 token 消耗
        with open("logs/usage.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"time": ts, "task": task[:100], "log": path, **stats},
                ensure_ascii=False,
            ) + "\n")
    print(f"[日志] 已保存到 {path}")
    return path


def new_stats():
    return {
        "status": "running",
        "steps": 0,
        "llm_calls": 0,
        "api_errors": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "usage_missing": 0,
        "tool_calls": {},
        "rag_hits": [],
        "llm_seconds": 0.0,
        "seconds": 0.0,
        "reflections": 0,
    }


def add_usage(stats, usage):
    if usage is None:
        stats["usage_missing"] += 1
        return
    p = usage.prompt_tokens or 0
    c = usage.completion_tokens or 0
    stats["prompt_tokens"] += p
    stats["completion_tokens"] += c
    stats["total_tokens"] += usage.total_tokens or (p + c)
    details = getattr(usage, "prompt_tokens_details", None)
    stats["cached_tokens"] += getattr(details, "cached_tokens", None) or 0


def format_stats(s):
    text = (
        f"{s['steps']} 步 · {s['llm_calls']} 次调用 · "
        f"tokens {s['total_tokens']}（输入 {s['prompt_tokens']} / 输出 {s['completion_tokens']}）"
        f" · 耗时 {s['seconds']:.1f}s"
    )
    if s.get("reflections"): # 新增
        text += f" · 反思 {s['reflections']} 次"
    if s["usage_missing"]:
        text += f" · {s['usage_missing']} 次调用未返回用量"
    return text


def msg_to_dict(m):
    d = {"role": "assistant", "content": m.content or ""}
    if m.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in m.tool_calls
        ]
    return d


from llm import chat, complete


def evaluate_task(messages):
    """用无工具的独立模型审查任务。返回 (score, reason)"""
    # 将历史对话压缩成文本供审查员阅读
    history_text = "\n".join([f"{m['role']}: {m.get('content', '')}" for m in messages if m.get('content')])

    prompt = f"""你是一个严格的代码审查员。请阅读以下智能体的工作记录，评估任务是否真正完成。
评分标准：
1. 目标是否完全达成。
2. 是否运行了验证（如测试或命令）。
3. 总结是否清晰。

对话记录：
{history_text}

请严格按以下格式输出（不要输出多余废话）：
Score: <1-10的整数>
Reason: <简短说明>
"""
    try:
        text, _ = complete([{"role": "user", "content": prompt}])
        import re
        score_match = re.search(r"Score:\s*(\d+)", text)
        score = int(score_match.group(1)) if score_match else 10
        return score, text
    except Exception as e:
        print(f"[评估失败] {e}")
        return 10, "评估出错默认通过"

class Agent:
    def __init__(self, workspace, max_steps=30, history=None):
        self.workspace = workspace
        self.max_steps = max_steps
        # 新增：最大反思次数
        self.max_reflections = 2
        self.reflections_done = 0
        if history:
            self.messages = history
        else:
            self.messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(
                        workspace=workspace, shell_hint=SHELL_HINT
                    ),
                }
            ]

    def run(self, task):
        self.stats = new_stats()
        start = time.time()
        try:
            return self._run(task)
        except Exception:
            self.stats["status"] = "error"
            raise
        finally:
            self.stats["seconds"] = round(time.time() - start, 2)
            self.stats["llm_seconds"] = round(self.stats["llm_seconds"], 2)
            print(f"[统计] {self.stats['status']} · {format_stats(self.stats)}")
            save_log(self.messages, task, self.stats)

    def _run(self, task):
        stats = self.stats
        try:
            context, hits = build_context(task)
        except Exception as e:
            print(f"[RAG] 检索失败，跳过: {type(e).__name__}: {e}")
            context, hits = "", []
        stats["rag_hits"] = hits
        if hits:
            print(f"[RAG] 命中: {'; '.join(hits)}")
        content = f"{task}\n\n---\n{context}" if context else task
        self.messages.append({"role": "user", "content": content})
        api_errors = 0

        for step in range(1, self.max_steps + 1):
            stats["steps"] = step
            self.messages = trim(self.messages)

            t0 = time.time()
            try:
                m, usage = chat(self.messages, TOOL_SCHEMAS)
                api_errors = 0
            except Exception as e:
                api_errors += 1
                stats["api_errors"] += 1
                print(f"[API错误 {api_errors}/{MAX_API_ERRORS}] {type(e).__name__}: {e}")
                if api_errors >= MAX_API_ERRORS:
                    raise
                time.sleep(2 ** api_errors)
                continue
            finally:
                stats["llm_seconds"] += time.time() - t0

            stats["llm_calls"] += 1
            add_usage(stats, usage)
            if usage is not None:
                print(
                    f"[LLM] 第{step}步 输入 {usage.prompt_tokens} / 输出 {usage.completion_tokens} tokens，"
                    f"耗时 {time.time() - t0:.1f}s，累计 {stats['total_tokens']}"
                )

            self.messages.append(msg_to_dict(m))

            if not m.tool_calls:
                content = m.content or ""
                print(content)

                # --- 新增：独立评估与重试逻辑 ---
                if self.reflections_done < self.max_reflections:
                    # 把当前回复临时加入，让审查员看到全貌
                    temp_messages = self.messages + [{"role": "assistant", "content": content}]

                    print("\n[审查员] 正在审查任务完成情况...")
                    score, reason = evaluate_task(temp_messages)
                    print(f"[审查员] 打分: {score} / 10\n原因:\n{reason}")

                    if score < 8:  # 门槛设为 8 分
                        self.reflections_done += 1
                        stats["reflections"] = self.reflections_done
                        print(f"[审查员] 分数低于 8 分，打回重做（第 {self.reflections_done} 次反思）...")

                        self.messages.append({"role": "assistant", "content": content})
                        self.messages.append({
                            "role": "system",
                            "content": f"代码审查员认为任务未达标（评分 {score}/10）。\n原因：\n{reason}\n\n请继续使用工具修改代码并验证。"
                        })
                        continue  # 跳过 return，进入下一轮 for 循环

                # 如果不是反思，或者分数达标，或者次数用完，则正常退出
                stats["status"] = "done"
                return content

            for tc in m.tool_calls:
                name = tc.function.name
                stats["tool_calls"][name] = stats["tool_calls"].get(name, 0) + 1
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result = execute_tool(name, args, workspace=self.workspace)
                except Exception as e:
                    result = f"工具执行错误: {type(e).__name__}: {e}"

                result = truncate_tool_result(str(result))
                print(f"[工具] {name} -> {result[:200]}")
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    }
                )

        print("达到最大步数，停止。")
        stats["status"] = "max_steps"
        return f"达到最大步数（{self.max_steps}），任务未完成。可以继续发送指令让我接着做。"
