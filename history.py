MAX_TOOL_CHARS = 8000


def trim(messages, max_messages=40):
    if len(messages) <= max_messages:
        return messages
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    keep = max_messages - len(system)
    if keep <= 0:
        return system
    rest = rest[-keep:]
    # 截断后开头不能是孤立的 tool 消息（其对应的 assistant tool_calls 已被裁掉），
    # 否则 API 会报错。从第一条 user 消息开始保留。
    for i, m in enumerate(rest):
        if m.get("role") == "user":
            return system + rest[i:]
    return system


def truncate_tool_result(text: str) -> str:
    if len(text) > MAX_TOOL_CHARS:
        return text[:MAX_TOOL_CHARS] + "\n...[结果截断]"
    return text

#改进：按 token 裁剪 + 滚动摘要。
