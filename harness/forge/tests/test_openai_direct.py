"""OpenAI models asked of OpenAI itself (providers.py, app/lib/providers.ts): with OPENAI_API_KEY set, a model named
openai/... goes to OpenAI's API in its form, priced from its tokens; every other model, and every model without the
key, stays on OpenRouter."""

from __future__ import annotations

import json
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
