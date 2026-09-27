"""Model workers' transport: stateless calls that must return JSON.

A worker sends a cached prefix (system prompt: template, style vocabulary, op
schemas) and a short task, may call the read-only lookup tools, and must end
with one JSON object. The orchestrator validates it against a schema; a reply
that does not parse is retried once with the parser's message.

OpenRouter when OPENROUTER_API_KEY is set; otherwise `available()` is False and
the offline workers in workers.py run instead.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request

from forge import tools

URL = "https://openrouter.ai/api/v1/chat/completions"


def available() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def model_name() -> str:
    return os.environ.get("FORGE_MODEL") or os.environ.get("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.5"


def _wire_name(name: str) -> str:
    return name.replace(".", "_")


def _tool_specs() -> list[dict]:
    specs = []
    for t in tools.read_only_tools():
        props = {k: {"type": "array" if v == "array" else "string"} for k, v in t.params.items()}
        specs.append({"type": "function", "function": {
            "name": _wire_name(t.name), "description": t.doc,
            "parameters": {"type": "object", "properties": props, "additionalProperties": True}}})
    return specs


def _post(body: dict) -> dict:
    request = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode())


def parse_json(text: str):
    """The JSON object in a reply, fenced or bare."""
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text or "")
    body = fence.group(1) if fence else text or ""
    start = min([i for i in (body.find("{"), body.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("the reply holds no JSON")
    return json.loads(body[start:body.rfind("}" if body[start] == "{" else "]") + 1])


def ask(job, system: str, task: str, max_turns: int = 8, check=None) -> dict:
    """One worker call. `check(obj)` returns a list of problems; empty accepts."""
    by_wire = {_wire_name(t.name): t.name for t in tools.read_only_tools()}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    repaired = False
    for _turn in range(max_turns):
        body = _post({"model": model_name(), "messages": messages, "tools": _tool_specs(),
                      "tool_choice": "auto", "usage": {"include": True}})
        usage = body.get("usage") or {}
        job.spend(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), float(usage.get("cost") or 0))
        message = (body.get("choices") or [{}])[0].get("message") or {}
        calls = message.get("tool_calls") or []
        if calls:
            messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
            for call in calls:
                name = by_wire.get(call["function"]["name"])
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                    result = tools.call(name, job=job, **args) if name else {"error": "unknown tool"}
                except Exception as error:  # noqa: BLE001 -- the model reads the error
                    result = {"error": f"{type(error).__name__}: {error}"}
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": json.dumps(result, ensure_ascii=False, default=str)[:12000]})
            continue
        text = message.get("content") or ""
        try:
            obj = parse_json(text)
            problems = check(obj) if check else []
        except (ValueError, json.JSONDecodeError) as error:
            obj, problems = None, [f"not valid JSON: {error}"]
        if not problems:
            return obj
        if repaired:
            raise ValueError("; ".join(problems[:6]))
        repaired = True
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": "Fix these and reply with the JSON only:\n- " + "\n- ".join(problems[:12])})
    raise ValueError("the worker kept calling tools without answering")
