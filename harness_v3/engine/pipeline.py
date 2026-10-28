"""A video from its narration, end to end.

    python pipeline.py narration.txt out_dir [--score given.score] [--quality m] [--model MODEL] [--critic]

1. voice: the narration spoken and every word timed (voice.py).
2. storyboard: one small-model call cuts it into shots (prompts.STORYBOARD).
3. score: one small-model call a shot, in order, each told what the shot before left up (prompts.SCORE + GRAMMAR).
   With `--score`, a score given by hand is used instead (and steps 2-3 are skipped).
4. render: the score played on one clock (render.py).
5. critic (`--critic`): frames at the words the score pins things to, judged by a vision model (prompts.CRITIC);
   its faults are written to out_dir/critic.txt (a shot to score again).

The model is any OpenRouter model (`--model`, else V3_MODEL, else a small one); the key is OPENROUTER_API_KEY.
Without a key, steps 2, 3 and 5 cannot run: give `--score`. Token use is written to out_dir/usage.json.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import env  # noqa: E402,F401 -- the keys from .env files, before anything reads them
import prompts  # noqa: E402

DEFAULT_MODEL = os.environ.get("V3_MODEL", "anthropic/claude-haiku-4.5")
SHOT_STEP = 18.0
USAGE: list[dict] = []


def chat(system: str, user: str, model: str, images: list[str] | None = None, max_tokens: int = 1800) -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set: give a score with --score, or set the key")
    content = [{"type": "text", "text": user}] + [{"type": "image_url", "image_url": {"url": i}} for i in images or []]
    body = {"model": model, "max_tokens": max_tokens, "temperature": 0.4,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content if images else user}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "User-Agent": "harness-v3/1.0", "HTTP-Referer": "https://github.com/bishboi/pocketanim",
                                          "X-Title": "harness v3"})
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.loads(r.read())
    USAGE.append({"model": model, **(out.get("usage") or {})})
    return out["choices"][0]["message"]["content"]


def storyboard(words: list[dict], model: str) -> list[dict]:
    system, user = prompts.storyboard_prompt(words)
    text = chat(system, user, model, max_tokens=900)
    shots = []
    for line in text.splitlines():
        m = re.search(r"SHOT\s+(\S+)\s*\|\s*words\s*w(\d+)\s*-\s*w(\d+)\s*\|(.*)", line, re.I)
        if m:
            shots.append({"name": re.sub(r"\W", "", m.group(1)) or f"s{len(shots)}", "a": int(m.group(2)),
                          "b": int(m.group(3)), "plan": m.group(4).strip()})
    if not shots:
        raise SystemExit(f"the storyboard had no SHOT lines:\n{text[:500]}")
    return shots


def score(shots: list[dict], words: list[dict], model: str) -> str:
    """Each shot written in its own call, in order: shots laid out in rows of three on the canvas."""
    out, before = ["look paper"], ""
    for k, s in enumerate(shots):
        at = ((k % 3) * SHOT_STEP, -(k // 3) * 11.0)
        mine = [w for w in words if s["a"] <= w["i"] <= s["b"]]
        system, user = prompts.score_prompt(s["plan"], mine, at, before)
        text = chat(system, user, model)
        text = re.sub(r"^```\w*|```$", "", text.strip(), flags=re.M).strip()
        if not re.search(r"^\s*shot\s", text, re.M):
            text = f"shot {s['name']} at {at[0]:g},{at[1]:g}\n" + text
        out.append(f"# ---- {s['name']}: {s['plan'][:90]}\n{text}")
        before = " ".join(re.findall(r"^\s*ent\s+(\S+)", text, re.M))
    return "\n\n".join(out) + "\n"


def critic(video: Path, score_text: str, words: list[dict], model: str, out: Path) -> str:
    """Frames at the score's anchors (a few a shot), judged by a vision model."""
    times = sorted({float(words[int(m)]["start"]) + 0.5 for m in re.findall(r"^w(\d+)", score_text, re.M)
                    if int(m) < len(words)})[::3][:12]
    images, said = [], []
    for t in times:
        f = out / f"critic-{t:.1f}.jpg"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=640:-1", str(f)], check=True)
        images.append("data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode())
        near = [w["w"] for w in words if abs(float(w["start"]) - t) < 1.5]
        said.append(f"t{t:.1f}: \"{' '.join(near)}\"")
    return chat(prompts.CRITIC, "FRAMES, in order:\n" + "\n".join(said), model, images=images, max_tokens=500)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("narration")
    ap.add_argument("out")
    ap.add_argument("--score")
    ap.add_argument("--quality", default="m")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--critic", action="store_true")
    ap.add_argument("--voice", default="en_US-ryan-high")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if not (out / "words.json").exists():
        subprocess.run([sys.executable, str(HERE / "voice.py"), a.narration, str(out), "--voice", a.voice,
                        "--speed", "1.22", "--pause", "0.85"], check=True)
    words = json.loads((out / "words.json").read_text())["words"]
    if a.score:
        text = Path(a.score).read_text()
    else:
        shots = storyboard(words, a.model)
        (out / "storyboard.json").write_text(json.dumps(shots, indent=1))
        text = score(shots, words, a.model)
    (out / "video.score").write_text(text)
    import render
    notes = render.render(text, out, out / "video.mp4", a.quality)
    for n in notes:
        print("note:", n)
    if a.critic:
        (out / "critic.txt").write_text(critic(out / "video.mp4", text, words, a.model, out))
    (out / "usage.json").write_text(json.dumps(USAGE, indent=1))
    print(f"wrote {out / 'video.mp4'}" + (f"; {sum(u.get('total_tokens', 0) for u in USAGE)} tokens" if USAGE else ""))


if __name__ == "__main__":
    main()
