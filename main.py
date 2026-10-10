import argparse

from agent import Agent
from tools import set_workspace


def main():
    parser = argparse.ArgumentParser(description="最小编程智能体")
    parser.add_argument("task", help="交给 agent 的编程任务")
    parser.add_argument("--workspace", default="./workspace", help="工作目录")
    parser.add_argument("--max-steps", type=int, default=30)
    args = parser.parse_args()

    set_workspace(args.workspace)
    agent = Agent(workspace=args.workspace, max_steps=args.max_steps)
    agent.run(args.task)


if __name__ == "__main__":
    main()