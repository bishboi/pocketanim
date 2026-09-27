"""A stand-in for OpenRouter's chat completions that behaves like a careful model.

Exercises: a tool call before answering, template patterns, one reply that fails
its check (retried), and one beat with an unsupported number (repaired).
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG = []
STATE = {"facts_tries": 0}


def reply(content=None, tool_calls=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg}], "usage": {"prompt_tokens": 1200, "completion_tokens": 300, "cost": 0.002}}


def call(name, args):
    return [{"id": f"call_{len(LOG)}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text) if s.strip()]


def plan(system, task, used_tool):
    if not used_tool:
        return reply(tool_calls=call("sources_search", {"query": "battle guns noon"}))
    template = json.loads(system.split("TEMPLATE\n", 1)[1].split("\n\n", 1)[0])
    arc = [s["id"] for s in template["arc"]]
    passages = [p["id"] for p in task["passages"]]
    chapters = [{"slot": arc[0], "title": "Prologue", "passages": passages[:1]}]
    body = [s for s in arc[1:]]
    rest = passages[1:]
    per = max(1, len(rest) // len(body))
    for i, slot in enumerate(body):
        chunk = rest[i * per:(i + 1) * per] if i < len(body) - 1 else rest[i * per:]
        if chunk:
            chapters.append({"slot": slot, "title": slot.replace("_", " ").title(), "passages": chunk,
                             "facts_needed": ["numbers"]})
    return reply(json.dumps({"chapters": chapters, "open_questions": [],
                             "lexicon": {"Siraj ud-Daulah": "Siraj ood Dowla"}}))


def facts(task):
    STATE["facts_tries"] += 1
    p = task["passages"][0]
    if STATE["facts_tries"] == 1:   # wrong on purpose: the value is not in the passage
        return reply(json.dumps({"facts": [{"claim": "Bengal had 12345 ports.", "values": ["12345"], "source": p["id"]}]}))
    return reply(json.dumps({"facts": []}))


def write(task, used_tool):
    chapter = task["chapter"]
    if not used_tool:
        return reply(tool_calls=call("facts_query", {"chapter": chapter["id"]}))
    lines = [s for p in task["passages"] for s in sentences(p["text"])]
    beats = []
    if chapter["slot"] == "battle":
        units = task["region"]["units"]
        beats.append({"say": lines[0], "do": [{"op": "panel", "title": chapter["title"]}]
                      + [{"op": "unit", "id": u} for u in units]})
        beats.append({"pattern": "opening_fire", "slots": {"attacker": "french", "target": "company", "time": "08:00"},
                      "lines": {"line": "The French guns opened the battle, firing on the grove at eight."}})
        beats.append({"pattern": "decisive_charge",
                      "slots": {"attacker": "mir_madan", "target": "company", "outcome": "repulsed"},
                      "lines": {"setup": "Mir Madan led the Nawab's cavalry forward against the grove.",
                                "charge": "He charged, trusting that the rain had silenced the English guns.",
                                "result": "The English guns fired, and Mir Madan was killed."}})
        beats.append({"say": "At 2 p.m. the Nawab's army began to retreat to its camp.",
                      "do": [{"op": "clock", "time": "14:00"}, {"op": "rout", "unit": "nawab"},
                             {"op": "move", "unit": "company", "to": "small_tank"}]})
        return reply(json.dumps({"beats": beats}))
    for i, line in enumerate(lines):
        do = [{"op": "panel", "title": chapter["title"]}] if i == 0 else []
        do.append({"op": "fact", "text": line[:80]})
        beats.append({"say": line, "do": do})
    if chapter["slot"] == "forces":
        beats.append({"say": "Some say the Nawab brought about 99,999 men to the field that day.", "do": []})
    return reply(json.dumps({"beats": beats}))


def repair(task):
    return reply(json.dumps({"say": "The Nawab's army was many times larger than Clive's.", "do": []}))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = body["messages"]
        system, task_text = msgs[0]["content"], msgs[1]["content"]
        used_tool = any(m["role"] == "tool" for m in msgs)
        retry = any(m["role"] == "user" and m["content"].startswith("Fix these") for m in msgs[2:])
        task = json.loads(task_text)
        if "planner of Lecture Forge" in system:
            kind, out = "plan", plan(system, task, used_tool)
        elif "extract facts" in system:
            kind, out = "facts", facts(task)
        elif "script writer" in system:
            kind, out = "write", write(task, used_tool)
        elif "repair one beat" in system:
            kind, out = "repair", repair(task)
        else:
            kind, out = "unknown", reply("{}")
        LOG.append(kind + (" (retry)" if retry else "") + (" +tool" if used_tool else ""))

        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
