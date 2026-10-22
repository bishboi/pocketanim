"""Speak the chapter (Microsoft's Hindi neural voice, edge-tts) and lay it on one track with every word's time.

    <venv with edge-tts>/bin/python voice.py        # writes lines.json, chapter.wav, timing.json here

The transcript's lines are numbered inline (28..64); years are spoken as a Hindi narrator says them
("अठारह सौ उनहत्तर"), shown on screen as digits.
"""
import asyncio, json, re, subprocess, wave
from pathlib import Path

import edge_tts

HERE = Path(__file__).resolve().parent
VOICE, RATE = "hi-IN-MadhurNeural", "+4%"
LEAD, GAP = 0.6, 0.38

SPOKEN = {
    "145 से 90": "एक सौ पैंतालीस से नब्बे",
    "1869": "अठारह सौ उनहत्तर",
    "1839 से 1931": "अठारह सौ उनतालीस से उन्नीस सौ इकतीस",
    "1254 से 1324": "बारह सौ चौवन से तेरह सौ चौबीस",
    "1274 से 1290": "बारह सौ चौहत्तर से बारह सौ नब्बे",
    "1552 से 1610": "पंद्रह सौ बावन से सोलह सौ दस",
    "1532 से 1597": "पंद्रह सौ बत्तीस से पंद्रह सौ सत्तानवे",
    "1980s": "उन्नीस सौ अस्सी के दशक",
    "1866 से 1934": "अठारह सौ छियासठ से उन्नीस सौ चौंतीस",
    "1907": "उन्नीस सौ सात",
    "1914": "उन्नीस सौ चौदह",
    "960 से 1279": "नौ सौ साठ से बारह सौ उन्यासी",
}


def split(text: str) -> list[str]:
    lines, pos = [], 0
    for n in range(28, 65):
        m = re.compile(rf"(?<=[।?!;]) {n}").search(text, pos)
        assert m, n
        lines.append(text[pos:m.start()].strip())
        pos = m.end()
    lines.append(text[pos:].strip())
    return lines


def spoken(line: str) -> str:
    for k, v in sorted(SPOKEN.items(), key=lambda kv: -len(kv[0])):
        line = line.replace(k, v)
    return line


async def say(text: str, out: Path) -> list[dict]:
    words = []
    c = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    with open(out, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"w": ch["text"], "start": ch["offset"] / 1e7, "end": (ch["offset"] + ch["duration"]) / 1e7})
    return words


def main():
    lines = split((HERE / "transcript.txt").read_text(encoding="utf-8").strip())
    (HERE / "lines.json").write_text(json.dumps({"lines": lines}, ensure_ascii=False, indent=1), encoding="utf-8")
    parts = HERE / ".voice"
    parts.mkdir(exist_ok=True)
    rows, clock, pcm = [], LEAD, [b"\0\0\0\0" * int(LEAD * 44100)]
    for n, line in enumerate(lines):
        mp3, wav = parts / f"{n:02d}.mp3", parts / f"{n:02d}.wav"
        words = asyncio.run(say(spoken(line), mp3))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ar", "44100", "-ac", "2", "-sample_fmt", "s16", str(wav)], check=True)
        with wave.open(str(wav)) as w:
            data = w.readframes(w.getnframes())
            seconds = w.getnframes() / 44100
        # The voice's own trailing silence trimmed to the words' end + a little, then the gap.
        speech_end = (words[-1]["end"] if words else seconds) + 0.12
        keep = min(seconds, speech_end)
        data = data[: int(keep * 44100) * 4]
        rows.append({"n": n, "text": line, "spoken": spoken(line), "start": round(clock + (words[0]["start"] if words else 0), 3),
                     "end": round(clock + keep, 3), "words": [{"w": w["w"], "start": round(clock + w["start"], 3), "end": round(clock + w["end"], 3)} for w in words]})
        pcm.append(data)
        clock += keep
        pause = GAP + (0.25 if line.endswith("?") or n in (0, 1, 7, 14, 26) else 0)
        pcm.append(b"\0\0\0\0" * int(pause * 44100))
        clock += int(pause * 44100) / 44100
        print(n, round(keep, 2), line[:40])
    pcm.append(b"\0\0\0\0" * int(1.2 * 44100))
    clock += 1.2
    with wave.open(str(HERE / "chapter.wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"".join(pcm))
    (HERE / "timing.json").write_text(json.dumps({"ok": True, "seconds": round(clock, 3), "track": "chapter.wav", "source": "voice",
                                                  "voice": {"engine": "edge-tts", "voice": VOICE}, "lines": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("seconds", round(clock, 2))


if __name__ == "__main__":
    main()
