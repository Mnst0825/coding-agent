import os
from openai import OpenAI


def chat(messages, tools, model=None):
    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY", "dummy"),
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
    )
    model = model or os.environ.get("MODEL")
    if not model:
        raise RuntimeError("请设置环境变量 MODEL")

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0,
    )
    return resp.choices[0].message