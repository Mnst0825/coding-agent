import json
import time
import os

from llm import chat
from tools import TOOL_SCHEMAS, execute_tool
from history import trim, truncate_tool_result

SYSTEM_PROMPT = """你是一个编程智能体。
你只能通过工具读写文件和执行命令。
当前工作目录是：{workspace}

要求：
1. 先探索目录和文件，再修改。
2. 修改后尽量运行测试或命令验证。
3. 不要编造文件内容。
4. 任务完成后，用中文给出简短总结。
"""

def save_log(messages, task):
    os.makedirs("logs", exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    safe_task = "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in task[:30]
    )
    path = f"logs/{ts}_{safe_task}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    print(f"[日志] 已保存到 {path}")
    return path

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


class Agent:
    def __init__(self, workspace, max_steps=30):
        self.workspace = workspace
        self.max_steps = max_steps
        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(workspace=workspace),
            }
        ]

    def run(self, task):
        self.messages.append({"role": "user", "content": task})

        for step in range(1, self.max_steps + 1):
            self.messages = trim(self.messages)

            try:
                m = chat(self.messages, TOOL_SCHEMAS)
            except Exception as e:
                print(f"[API错误] {type(e).__name__}: {e}")
                time.sleep(2)
                continue

            self.messages.append(msg_to_dict(m))

            if not m.tool_calls:
                print(m.content or "(无输出)")
                save_log(self.messages, task)
                return m.content

            for tc in m.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result = execute_tool(name, args)
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
        save_log(self.messages, task)
        return None