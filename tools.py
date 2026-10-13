import os
import re
import subprocess
from pathlib import Path

WORKSPACE = Path(os.environ.get("AGENT_WORKSPACE", "./workspace")).resolve()

MAX_TIMEOUT = 120


def set_workspace(path: str):
    global WORKSPACE
    WORKSPACE = Path(path).resolve()
    WORKSPACE.mkdir(parents=True, exist_ok=True)


def _safe(root: Path, path: str) -> Path:
    if Path(path).is_absolute():
        raise ValueError(f"不允许绝对路径: {path}")
    p = (root / path).resolve()
    if p != root and root not in p.parents:
        raise ValueError(f"路径越界，拒绝访问: {path}")
    return p


def read_file(root: Path, path: str, start: int = 1, end: int | None = None) -> str:
    p = _safe(root, path)
    if not p.is_file():
        raise FileNotFoundError(f"不是文件: {path}")
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines:
        return "(空文件)"
    start = max(1, start)
    end = len(lines) if end is None else min(end, len(lines))
    out = []
    for i in range(start, end + 1):
        out.append(f"{i:>4}: {lines[i - 1]}")
    return "\n".join(out)


def write_file(root: Path, path: str, content: str) -> str:
    p = _safe(root, path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"已写入 {p.relative_to(root)}，{len(content)} 字符"


def edit_file(root: Path, path: str, old: str, new: str) -> str:
    p = _safe(root, path)
    if not p.is_file():
        raise FileNotFoundError(f"不是文件: {path}")
    if not old:
        raise ValueError("old 不能为空")
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        raise ValueError("未找到 old 文本，请先 read_file 确认原文（注意缩进和空白）")
    if count > 1:
        raise ValueError(f"old 文本出现 {count} 次，请提供更多上下文使其唯一")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return f"已修改 {p.relative_to(root)}"


def list_files(root: Path, path: str = ".") -> str:
    p = _safe(root, path)
    if not p.exists():
        raise FileNotFoundError(f"路径不存在: {path}")
    results = []
    if p.is_file():
        results.append(str(p.relative_to(root)))
    else:
        for cur, dirs, files in os.walk(p):
            dirs[:] = [
                d for d in dirs
                if d not in {".git", "__pycache__", "node_modules", ".venv"}
            ]
            for f in files:
                fp = Path(cur) / f
                if fp.name == ".messages.json":
                    continue
                results.append(str(fp.relative_to(root)))
            if len(results) > 500:
                results.append("...[超过500个文件，已截断]")
                break
    return "\n".join(results) if results else "(空目录)"


DANGEROUS = [
    r"rm\s+-rf\s+/(?:\s|$)",
    r"shutdown",
    r"reboot",
    r"mkfs",
    r"format\s+[a-zA-Z]:",
    r":\(\)\s*\{",
]


def run_command(root: Path, command: str, timeout: int = 30) -> str:
    for pat in DANGEROUS:
        if re.search(pat, command):
            raise ValueError(f"危险命令已拒绝: {command}")

    timeout = max(1, min(int(timeout), MAX_TIMEOUT))
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"命令超时（>{timeout}s）: {command}"

    out = (proc.stdout or "")
    if proc.stdout and proc.stderr:
        out += "\n"
    out += (proc.stderr or "")
    out = out.strip()
    if len(out) > 8000:
        out = out[:8000] + "\n...[输出截断]"
    return f"exit={proc.returncode}\n{out}"


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取工作区内文件，返回带行号内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作区路径"},
                    "start": {"type": "integer", "description": "起始行，默认1"},
                    "end": {"type": "integer", "description": "结束行，默认文件末尾"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入或覆盖工作区内文件，适合新建文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "局部替换文件内容：把唯一出现的 old 文本替换为 new。old 必须与原文完全一致（含缩进）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old": {"type": "string", "description": "要被替换的原文，必须在文件中唯一"},
                    "new": {"type": "string", "description": "替换后的文本"},
                },
                "required": ["path", "old", "new"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出工作区内文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，默认 ."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": f"在工作区目录执行 shell 命令，返回退出码和输出。超时上限 {MAX_TIMEOUT} 秒。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "description": "秒，默认30"},
                },
                "required": ["command"],
            },
        },
    },
]

TOOLS = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_files": list_files,
    "run_command": run_command,
}

_ALLOWED_ARGS = {
    s["function"]["name"]: set(s["function"]["parameters"]["properties"])
    for s in TOOL_SCHEMAS
}


def execute_tool(name: str, args: dict, workspace: str | Path | None = None) -> str:
    if name not in TOOLS:
        raise ValueError(f"未知工具: {name}")
    if not isinstance(args, dict):
        raise ValueError("工具参数必须是 JSON 对象")
    unknown = set(args) - _ALLOWED_ARGS[name]
    if unknown:
        raise ValueError(f"未知参数: {', '.join(sorted(unknown))}")
    root = Path(workspace).resolve() if workspace else WORKSPACE
    return TOOLS[name](root, **args)
