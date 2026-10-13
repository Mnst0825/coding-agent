import os
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
from tools import set_workspace

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me")
WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "")

WORKSPACE_ROOT = Path("workspace").resolve()
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)


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


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == WEB_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "密码错误"
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
    set_workspace(ws)
    agent = Agent(workspace=ws, max_steps=30)
    try:
        result = agent.run(task)
    except Exception as e:
        result = f"执行出错：{type(e).__name__}: {e}"
    return jsonify({"result": result or "(无输出)"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)