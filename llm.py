import os
from functools import lru_cache

from openai import OpenAI


@lru_cache(maxsize=1)
def _client():
    return OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY", "dummy"),
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
        timeout=float(os.environ.get("LLM_TIMEOUT", 60)),
        max_retries=2,
    )


def chat(messages, tools, model=None):
    model = model or os.environ.get("MODEL")
    if not model:
        raise RuntimeError("请设置环境变量 MODEL")

    resp = _client().chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0,
    )
    return resp.choices[0].message
