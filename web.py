import hmac
import json
import os
import secrets
import threading
import uuid
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

load_dotenv()

from agent import Agent
from history import trim

app = Flask(__name__)
# 未配置 SECRET_KEY 时用随机值，避免使用可被猜到的固定密钥伪造 session
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "")
if not WEB_PASSWORD:
    print("[警告] 未设置 WEB_PASSWORD，网页登录将被禁用")

# 同一会话同一时间只允许一个任务，防止并发写坏历史文件
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _session_lock(sid: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(sid, threading.Lock())

WORKSPACE_ROOT = Path("workspace").resolve()
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

MAX_HISTORY = 40


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def get_user_workspace():
    sid = session.get("sid")
    if not sid:
        sid = str(uuid.uuid4())
        session["sid"] = sid
    p = WORKSPACE_ROOT / sid
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def history_file(ws: str) -> Path:
    return Path(ws) / ".messages.json"


def load_history(ws: str):
    f = history_file(ws)
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return None
        return trim(data, max_messages=MAX_HISTORY)
    except Exception as e:
        print(f"[警告] 载入历史失败: {e}")
        return None


def save_history(ws: str, messages):
    f = history_file(ws)
    try:
        f.write_text(
            json.dumps(messages, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[警告] 保存历史失败: {e}")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if WEB_PASSWORD and hmac.compare_digest(
            password.encode("utf-8"), WEB_PASSWORD.encode("utf-8")
        ):
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "密码错误" if WEB_PASSWORD else "服务端未配置 WEB_PASSWORD"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    data = request.get_json() or {}
    task = (data.get("task") or "").strip()
    if not task:
        return jsonify({"error": "任务为空"}), 400

    ws = get_user_workspace()
    lock = _session_lock(session["sid"])
    if not lock.acquire(blocking=False):
        return jsonify({"error": "上一个任务还在执行，请稍候"}), 409

    try:
        history = load_history(ws)
        agent = Agent(workspace=ws, max_steps=30, history=history)
        try:
            result = agent.run(task)
        except Exception as e:
            result = f"执行出错：{type(e).__name__}: {e}"
        save_history(ws, agent.messages)
    finally:
        lock.release()

    return jsonify({
        "result": result or "(无输出)",
        "stats": getattr(agent, "stats", None),
    })


@app.route("/api/new_session", methods=["POST"])
@login_required
def new_session():
    ws = get_user_workspace()
    f = history_file(ws)
    if f.exists():
        try:
            f.unlink()
        except Exception as e:
            print(f"[警告] 删除历史失败: {e}")
    return jsonify({"ok": True})


@app.route("/api/sessions", methods=["GET"])
@login_required
def get_sessions():
    sessions = []
    for p in WORKSPACE_ROOT.iterdir():
        if p.is_dir():
            hist_file = p / ".messages.json"
            title = "空会话"
            mtime = p.stat().st_mtime  # 默认用文件夹修改时间

            if hist_file.exists():
                try:
                    mtime = hist_file.stat().st_mtime
                    data = json.loads(hist_file.read_text(encoding="utf-8"))

                    # 寻找第一条真正的用户指令作为标题
                    for msg in data:
                        if msg.get("role") == "user":
                            content = msg.get("content", "")
                            # 过滤掉系统追加的审查员提示
                            if content.startswith("代码审查员认为"):
                                continue
                            # 过滤掉 RAG 附带的上下文，只取第一行
                            clean_title = content.split("\n")[0].strip()
                            if clean_title:
                                title = clean_title[:25] + "..." if len(clean_title) > 25 else clean_title
                                break
                except Exception as e:
                    print(f"[读取历史失败] {p.name}: {e}")

            sessions.append({
                "id": p.name,
                "title": title,
                "time": mtime
            })

    # 按最后修改时间倒序，最新的在最上面
    sessions.sort(key=lambda x: x["time"], reverse=True)
    return jsonify({"sessions": sessions, "current": session.get("sid")})


@app.route("/api/switch_session", methods=["POST"])
@login_required
def switch_session():
    data = request.get_json() or {}
    new_sid = data.get("sid")
    if not new_sid:
        return jsonify({"error": "无效的 SID"}), 400

    # 验证该 SID 对应的文件夹确实存在
    p = WORKSPACE_ROOT / new_sid
    if not p.exists() or not p.is_dir():
        return jsonify({"error": "会话不存在"}), 404

    # 直接覆盖当前浏览器的 session
    session["sid"] = new_sid
    return jsonify({"ok": True})


@app.route("/api/history", methods=["GET"])
@login_required
def get_history():
    """获取当前会话的聊天记录，过滤掉 system 和 tool 消息"""
    ws = get_user_workspace()
    f = Path(ws) / ".messages.json"
    if not f.exists():
        return jsonify({"history": []})

    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        clean_history = []
        for m in data:
            # 只保留 user 和 assistant 的普通文本（不包含带工具调用的 assistant）
            if m.get("role") in ["user", "assistant"] and m.get("content"):
                # 避免把加载 RAG 的那一坨又渲染出来，只取最前面的任务描述
                if m["role"] == "user":
                    content = m["content"].split("\n\n---\n")[0]
                else:
                    content = m["content"]

                clean_history.append({
                    "role": m["role"],
                    "content": content
                })
        return jsonify({"history": clean_history})
    except Exception as e:
        print(f"[警告] 获取历史失败: {e}")
        return jsonify({"history": []})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)