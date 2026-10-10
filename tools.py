import json
import os
import re
import subprocess
from pathlib import Path

WORKSPACE = Path(os.environ.get("AGENT_WORKSPACE", "./workspace")).resolve()


def set_workspace(path: str):
    global WORKSPACE
    WORKSPACE = Path(path).resolve()
    WORKSPACE.mkdir(parents=True, exist_ok=True)


def _safe(path: str) -> Path:
    if Path(path).is_absolute():
        raise ValueError(f"不允许绝对路径: {path}")
    p = (WORKSPACE / path).resolve()
    if p != WORKSPACE and WORKSPACE not in p.parents:
        raise ValueError(f"路径越界，拒绝访问: {path}")
    return p


def read_file(path: str, start: int = 1, end: int | None = None) -> str:
    p = _safe(path)
    if not p.is_file():
        raise FileNotFoundError(f"不是文件: {path}")
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    start = max(1, start)
    end = len(lines) if end is None else min(end, len(lines))
    out = []
    for i in range(start, end + 1):
        out.append(f"{i:>4}: {lines[i - 1]}")
    return "\n".join(out)


def write_file(path: str, content: str) -> str:
    p = _safe(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"已写入 {p.relative_to(WORKSPACE)}，{len(content)} 字符"


def list_files(path: str = ".") -> str:
    p = _safe(path)
    if not p.exists():
        raise FileNotFoundError(f"路径不存在: {path}")
    results = []
    if p.is_file():
        results.append(str(p.relative_to(WORKSPACE)))
    else:
        for root, dirs, files in os.walk(p):
            dirs[:] = [
                d for d in dirs
                if d not in {".git", "__pycache__", "node_modules", ".venv"}
            ]
            for f in files:
                fp = Path(root) / f
                results.append(str(fp.relative_to(WORKSPACE)))
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


def run_command(command: str, timeout: int = 30) -> str:
    for pat in DANGEROUS:
        if re.search(pat, command):
            raise ValueError(f"危险命令已拒绝: {command}")

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
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
            "description": "写入或覆盖工作区内文件。",
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
            "description": "在工作区目录执行 shell 命令，返回退出码和输出。",
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


def execute_tool(name: str, args: dict) -> str:
    if name == "read_file":
        return read_file(**args)
    if name == "write_file":
        return write_file(**args)
    if name == "list_files":
        return list_files(**args)
    if name == "run_command":
        return run_command(**args)
    raise ValueError(f"未知工具: {name}")