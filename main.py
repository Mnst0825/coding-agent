import argparse

from dotenv import load_dotenv

load_dotenv()

from agent import Agent
from tools import set_workspace

#验证环境变量
import os
print("[DEBUG] MODEL =", os.environ.get("MODEL"))
print("[DEBUG] BASE_URL =", os.environ.get("OPENAI_BASE_URL"))

def main():
    parser = argparse.ArgumentParser(description="最小编程智能体")
    parser.add_argument("task", nargs="*", help="可选单次任务；不传则进入交互模式")
    parser.add_argument("--workspace", default="./workspace", help="工作目录")
    parser.add_argument("--max-steps", type=int, default=30)
    args = parser.parse_args()

    set_workspace(args.workspace)

    if args.task:
        Agent(workspace=args.workspace, max_steps=args.max_steps).run(" ".join(args.task))
        return

    print("进入交互模式。输入任务执行，输入 exit 退出。")
    while True:
        try:
            task = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not task:
            continue
        if task.lower() in {"exit", "quit"}:
            break
        Agent(workspace=args.workspace, max_steps=args.max_steps).run(task)


if __name__ == "__main__":
    main()