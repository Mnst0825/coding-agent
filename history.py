MAX_TOOL_CHARS = 8000


def trim(messages, max_messages=40):
    if len(messages) <= max_messages:
        return messages
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    keep = max_messages - len(system)
    if keep <= 0:
        return system
    return system + rest[-keep:]


def truncate_tool_result(text: str) -> str:
    if len(text) > MAX_TOOL_CHARS:
        return text[:MAX_TOOL_CHARS] + "\n...[结果截断]"
    return text