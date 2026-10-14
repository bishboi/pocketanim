"""OpenAI models asked of OpenAI itself (providers.py, app/lib/providers.ts): with OPENAI_API_KEY set, a model named
openai/... goes to OpenAI's API in its form, priced from its tokens; every other model, and every model without the
key, stays on OpenRouter."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from forge.util import REPO

import llm  # noqa: E402
import providers  # noqa: E402

APP = REPO / "harness" / "app"


def _serve(name, got):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            got.append((name, self.path, self.headers.get("Authorization"), body))
            reply = {"choices": [{"message": {"content": json.dumps({"ok": name})}}],
                     "usage": {"prompt_tokens": 1000, "completion_tokens": 500}}
            if name == "openrouter":
                reply["usage"]["cost"] = 0.5
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def test_an_openai_model_is_asked_of_openai_in_its_form(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.delenv("PANIM_OPENAI_DIRECT", raising=False)
    body = {"model": "openai/gpt-5.1", "usage": {"include": True}, "provider": {"sort": "price"},
            "reasoning": {"effort": "medium"}, "temperature": 0, "max_tokens": 160, "stream": True,
            "messages": [{"role": "user", "content": "hi"}]}
    url, headers, sent = providers.chat(body)
    assert url == "https://api.openai.com/v1/chat/completions" and headers["Authorization"] == "Bearer sk-openai"
    # A reasoning model's small cap is raised: its thinking counts in it.
    assert sent == {"model": "gpt-5.1", "reasoning_effort": "medium", "max_completion_tokens": 4000, "stream": True,
                    "stream_options": {"include_usage": True}, "messages": [{"role": "user", "content": "hi"}]}
    # Not a reasoning model: its temperature stays, and no reasoning setting is sent.
    _, _, older = providers.chat({"model": "openai/gpt-4.1", "temperature": 0, "reasoning": {"effort": "low"},
                                  "messages": []})
    assert older == {"model": "gpt-4.1", "temperature": 0, "messages": []}
    # Every gpt from 5 on is a reasoning model (gpt-6-luna too): no temperature.
    _, _, newer = providers.chat({"model": "openai/gpt-6-luna", "temperature": 0, "max_tokens": 9000, "messages": []})
    assert newer == {"model": "gpt-6-luna", "max_completion_tokens": 9000, "messages": []}
    # Other models, and OpenAI's without the key or with it switched off, stay on OpenRouter as they were.
    for model, env in (("google/gemini-2.5-flash", {}), ("openai/gpt-5.1", {"PANIM_OPENAI_DIRECT": "off"})):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        url, headers, sent = providers.chat({**body, "model": model})
        assert "openrouter.ai" in url and headers["Authorization"] == "Bearer or-key" and sent["model"] == model
    monkeypatch.delenv("PANIM_OPENAI_DIRECT")
    monkeypatch.delenv("OPENAI_API_KEY")
    assert not providers.direct("openai/gpt-5.1")


def test_the_python_steps_reach_openai_and_price_its_tokens(monkeypatch):
    got: list = []
    openai, openai_url = _serve("openai", got)
    router, router_url = _serve("openrouter", got)
    try:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.setenv("OPENAI_BASE_URL", openai_url + "/v1")
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
        monkeypatch.setenv("OPENROUTER_URL", router_url + "/api/v1/chat/completions")
        monkeypatch.setenv("PANIM_OPENAI_PRICES", json.dumps({"gpt-5.1": [2.0, 10.0]}))
        reply, usd = llm.chat_json("openai/gpt-5.1", "system", "user")
        assert reply == {"ok": "openai"} and usd == pytest.approx((1000 * 2 + 500 * 10) / 1e6)
        reply, usd = llm.chat_json("google/gemini-2.5-flash", "system", "user")
        assert reply == {"ok": "openrouter"} and usd == 0.5
    finally:
        openai.shutdown()
        router.shutdown()
    assert got[0][1] == "/v1/chat/completions" and got[0][2] == "Bearer sk-openai"
    assert got[0][3]["model"] == "gpt-5.1" and "usage" not in got[0][3]
    assert got[1][2] == "Bearer or-key" and got[1][3]["model"] == "google/gemini-2.5-flash"


def test_the_web_app_routes_the_same_way(tmp_path):
    tsc = APP / "node_modules" / ".bin" / "tsc"
    if not tsc.exists() or not shutil.which("node"):
        pytest.skip("no TypeScript compiler")
    built = subprocess.run([str(tsc), "lib/providers.ts", "--outDir", str(tmp_path), "--module", "commonjs",
                            "--target", "es2022", "--skipLibCheck"], cwd=APP, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    script = f"""
process.env.OPENAI_API_KEY = "sk-openai"; process.env.OPENROUTER_URL = "";
process.env.PANIM_OPENAI_PRICES = '{{"gpt-5.1": [2, 10]}}';
const p = require({json.dumps(str(tmp_path / 'providers.js'))});
const a = p.chatRequest({{ model: "openai/gpt-5.1", usage: {{ include: true }}, reasoning: {{ effort: "low" }},
  max_tokens: 50, temperature: 0, stream: true, messages: [] }}, "or-key");
const b = p.chatRequest({{ model: "anthropic/claude-sonnet-4.5", usage: {{ include: true }}, messages: [] }}, "or-key");
console.log(JSON.stringify({{ a, b, cost: p.replyCost("openai/gpt-5.1", {{ prompt_tokens: 1000, completion_tokens: 500 }}),
  kept: p.replyCost("openai/gpt-5.1", {{ cost: 0.3 }}) }}));
"""
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert out["a"]["url"] == "https://api.openai.com/v1/chat/completions"
    assert out["a"]["headers"]["Authorization"] == "Bearer sk-openai"
    assert out["a"]["body"] == {"model": "gpt-5.1", "reasoning_effort": "low", "max_completion_tokens": 4000,
                                "stream": True, "stream_options": {"include_usage": True}, "messages": []}
    assert "openrouter.ai" in out["b"]["url"] and out["b"]["headers"]["Authorization"] == "Bearer or-key"
    assert out["b"]["body"]["model"] == "anthropic/claude-sonnet-4.5"
    assert out["cost"] == pytest.approx(0.007) and out["kept"] == 0.3


def test_a_request_with_tools_goes_to_openais_responses_api(tmp_path):
    # OpenAI refuses function tools with a reasoning setting on chat completions: such a request is sent to
    # /v1/responses in that API's form, and its stream read back as chat deltas (a tool call's name and arguments).
    tsc = APP / "node_modules" / ".bin" / "tsc"
    if not tsc.exists() or not shutil.which("node"):
        pytest.skip("no TypeScript compiler")
    built = subprocess.run([str(tsc), "lib/providers.ts", "--outDir", str(tmp_path), "--module", "commonjs",
                            "--target", "es2022", "--skipLibCheck"], cwd=APP, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    script = f"""
process.env.OPENAI_API_KEY = "sk-openai";
const p = require({json.dumps(str(tmp_path / 'providers.js'))});
const tool = {{ type: "function", function: {{ name: "write_section", description: "d", parameters: {{ type: "object" }} }} }};
const r = p.modelRequest({{ model: "openai/gpt-6-luna", stream: true, tool_choice: "required", usage: {{ include: true }},
  reasoning: {{ effort: "medium" }}, tools: [tool], messages: [
    {{ role: "system", content: "sys" }},
    {{ role: "user", content: [{{ type: "text", text: "look" }}, {{ type: "image_url", image_url: {{ url: "data:x" }} }}] }},
    {{ role: "assistant", content: null, tool_calls: [{{ id: "c1", type: "function", function: {{ name: "write_section", arguments: "{{}}" }} }}] }},
    {{ role: "tool", tool_call_id: "c1", content: "saved" }} ] }}, "or-key");
const plain = p.modelRequest({{ model: "openai/gpt-6-luna", messages: [] }}, "or-key");
const other = p.modelRequest({{ model: "google/gemini-2.5-flash", tools: [tool], messages: [] }}, "or-key");
const s = new p.ResponsesStream();
const deltas = [
  {{ type: "response.output_item.added", item: {{ type: "reasoning", id: "r1" }} }},
  {{ type: "response.output_text.delta", delta: "Here " }},
  {{ type: "response.output_item.added", item: {{ type: "function_call", id: "fc1", call_id: "call_9", name: "write_section", arguments: "" }} }},
  {{ type: "response.function_call_arguments.delta", item_id: "fc1", delta: "{{\\"n\\":" }},
  {{ type: "response.function_call_arguments.delta", item_id: "fc1", delta: "1}}" }},
  {{ type: "response.completed", response: {{ usage: {{ input_tokens: 100, output_tokens: 40 }} }} }},
].map((e) => s.handle(e).delta).filter(Boolean);
const failed = new p.ResponsesStream().handle({{ type: "response.failed", response: {{ error: {{ message: "nope" }} }} }});
console.log(JSON.stringify({{ r, plain: plain.url, other: other.url, deltas, usage: s.usage, finish: s.finishReason, failed }}));
"""
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    r = out["r"]
    assert r["responses"] and r["url"] == "https://api.openai.com/v1/responses"
    assert r["body"]["model"] == "gpt-6-luna" and r["body"]["reasoning"] == {"effort": "medium"}
    assert r["body"]["tools"] == [{"type": "function", "name": "write_section", "description": "d",
                                   "parameters": {"type": "object"}}]
    assert r["body"]["tool_choice"] == "required" and r["body"]["stream"] and r["body"]["store"] is False
    assert "usage" not in r["body"] and "messages" not in r["body"]
    assert r["body"]["input"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": [{"type": "input_text", "text": "look"}, {"type": "input_image", "image_url": "data:x"}]},
        {"type": "function_call", "call_id": "c1", "name": "write_section", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c1", "output": "saved"}]
    assert out["plain"].endswith("/chat/completions") and "openrouter.ai" in out["other"]
    assert out["deltas"][0] == {"content": "Here "}
    assert out["deltas"][1]["tool_calls"][0] == {"index": 0, "id": "call_9",
                                                 "function": {"name": "write_section", "arguments": ""}}
    assert "".join(d["tool_calls"][0]["function"]["arguments"] for d in out["deltas"][2:]) == '{"n":1}'
    assert out["usage"] == {"prompt_tokens": 100, "completion_tokens": 40, "prompt_tokens_details": {"cached_tokens": 0}}
    assert out["finish"] == "tool_calls"
    assert out["failed"] == {"error": "nope"}


def test_forge_sends_no_reasoning_setting_with_tools(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    _, _, sent = providers.chat({"model": "openai/gpt-6-luna", "reasoning": {"effort": "low"},
                                 "tools": [{"type": "function", "function": {"name": "x"}}], "messages": []})
    assert "reasoning_effort" not in sent and sent["tools"]


LIST = {"data": [
    {"id": "openai/gpt-6-luna", "pricing": {"prompt": "0.000002", "completion": "0.000016", "input_cache_read": "0.0000002"}},
    {"id": "openai/gpt-image-2", "pricing": {"prompt": "0.000005", "completion": "0.00004"}},
    {"id": "google/gemini-2.5-flash", "pricing": {"prompt": "0.0000003", "completion": "0.0000025"}}]}


def _serve_list():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    hits = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):  # noqa: N802
            hits.append(self.path)
            data = json.dumps(LIST).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/api/v1/models", hits, server


def test_an_openai_reply_is_priced_from_the_model_list(tmp_path, monkeypatch):
    url, hits, server = _serve_list()
    monkeypatch.setenv("PANIM_PRICE_LIST_URL", url)
    monkeypatch.setenv("PANIM_PRICE_CACHE", str(tmp_path / "prices.json"))
    monkeypatch.delenv("PANIM_OPENAI_PRICES", raising=False)
    monkeypatch.setattr(providers, "_listed", None)
    try:
        usage = {"prompt_tokens": 10_000, "completion_tokens": 2_000, "prompt_tokens_details": {"cached_tokens": 4_000}}
        # 6,000 fresh input at $2/M, 4,000 cached at $0.20/M, 2,000 output at $16/M.
        assert providers.cost("openai/gpt-6-luna", usage) == pytest.approx(0.012 + 0.0008 + 0.032)
        assert providers.cost("openai/gpt-6-luna-2026-09-01", {"prompt_tokens": 1_000_000}) == pytest.approx(2.0)
        assert providers.cost("openai/unknown-model", usage) == 0.0
        assert providers.cost("openai/gpt-6-luna", {"cost": 0.25}) == 0.25          # OpenRouter's own figure kept
        assert len(hits) == 1 and json.loads((tmp_path / "prices.json").read_text())["models"]["gpt-6-luna"]["in"] == 2.0
        monkeypatch.setattr(providers, "_listed", None)                             # a new process: from the cache
        assert providers.cost("openai/gpt-6-luna", {"completion_tokens": 1_000_000}) == pytest.approx(16.0)
        assert len(hits) == 1
        monkeypatch.setenv("PANIM_OPENAI_PRICES", json.dumps({"gpt-6-luna": [1, 2, 0.5]}))   # one's own wins
        assert providers.cost("openai/gpt-6-luna", usage) == pytest.approx((6000 * 1 + 4000 * 0.5 + 2000 * 2) / 1e6)
    finally:
        server.shutdown()


def test_the_web_app_prices_openai_replies_from_the_model_list(tmp_path):
    tsc = APP / "node_modules" / ".bin" / "tsc"
    if not tsc.exists() or not shutil.which("node"):
        pytest.skip("no TypeScript compiler")
    built = subprocess.run([str(tsc), "lib/providers.ts", "--outDir", str(tmp_path), "--module", "commonjs",
                            "--target", "es2022", "--skipLibCheck"], cwd=APP, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    url, hits, server = _serve_list()
    script = f"""
const p = require({json.dumps(str(tmp_path / 'providers.js'))});
(async () => {{
  await p.ensurePrices();
  const usage = {{ prompt_tokens: 10000, completion_tokens: 2000, prompt_tokens_details: {{ cached_tokens: 4000 }} }};
  console.log(JSON.stringify({{ cost: p.replyCost("openai/gpt-6-luna", usage),
    none: p.replyCost("openai/unknown-model", usage) }}));
}})();
"""
    env = {**os.environ, "PANIM_PRICE_LIST_URL": url, "PANIM_PRICE_CACHE": str(tmp_path / "prices.json")}
    env.pop("PANIM_OPENAI_PRICES", None)
    try:
        done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60, env=env)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert out["cost"] == pytest.approx(0.0448) and out["none"] == 0
    assert hits and (tmp_path / "prices.json").exists()
