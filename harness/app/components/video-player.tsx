"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

function clock(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${rest}` : `${m}:${rest}`;
}

/**
 * The finished MP4, as Manim rendered it (the same file the download gives): play from anywhere on the bar, at
 * 0.5x to 2x, 10 seconds back or on, and full screen. Keys: space or k plays and pauses, the arrows jump 5 s
 * (j and l 10 s), f is full screen, < and > change the speed.
 */
export function VideoPlayer({ src, autoPlay = false }: { src: string; autoPlay?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [buffered, setBuffered] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [full, setFull] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = useCallback(() => {
    const v = video.current;
    if (!v) return;
    if (v.paused) void v.play().catch(() => {});
    else v.pause();
  }, []);

  const jump = useCallback((by: number) => {
    const v = video.current;
    if (!v) return;
    v.currentTime = Math.min(Math.max(0, v.currentTime + by), v.duration || v.currentTime + by);
  }, []);

  const changeSpeed = useCallback((value: number) => {
    const v = video.current;
    if (v) v.playbackRate = value;
    setSpeed(value);
  }, []);

  const fullscreen = useCallback(() => {
    const el = box.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen?.().catch(() => {});
  }, []);

  // The video may have read its length before React attached the handlers below (the element arrives with the
  // page): read it now too, or the bar had no length and could not seek.
  useEffect(() => {
    const v = video.current;
    if (v && v.readyState >= 1) {
      setDuration(v.duration);
      setTime(v.currentTime);
    }
  }, [src]);

  useEffect(() => {
    const onChange = () => setFull(document.fullscreenElement === box.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  function onKey(event: React.KeyboardEvent) {
    const key = event.key;
    const step = SPEEDS.indexOf(speed);
    const handled: Record<string, () => void> = {
      " ": toggle, k: toggle, f: fullscreen,
      ArrowLeft: () => jump(-5), ArrowRight: () => jump(5), j: () => jump(-10), l: () => jump(10),
      "<": () => changeSpeed(SPEEDS[Math.max(0, step - 1)]),
      ">": () => changeSpeed(SPEEDS[Math.min(SPEEDS.length - 1, step + 1)]),
    };
    if (handled[key]) {
      event.preventDefault();
      handled[key]();
    }
  }

  return (
    <div
      ref={box}
      tabIndex={0}
      onKeyDown={onKey}
      data-testid="video-player"
      className={`flex flex-col gap-2 rounded outline-none ${full ? "h-full w-full justify-center bg-black p-3" : ""}`}
    >
      <video
        ref={video}
        src={src}
        autoPlay={autoPlay}
        preload="metadata"
        playsInline
        onClick={toggle}
        onDoubleClick={fullscreen}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => {
          setDuration(e.currentTarget.duration);
          e.currentTarget.playbackRate = speed;
        }}
        onProgress={(e) => {
          const b = e.currentTarget.buffered;
          setBuffered(b.length ? b.end(b.length - 1) : 0);
        }}
        onError={() => setError("The video could not be played.")}
        className={`w-full rounded border border-neutral-800 bg-black ${full ? "max-h-[calc(100vh-5rem)] object-contain" : ""}`}
      />
      <div className="relative h-4">
        <div
          className="pointer-events-none absolute top-1.5 h-1 rounded bg-neutral-700"
          style={{ width: `${duration ? (100 * buffered) / duration : 0}%` }}
        />
        <input
          type="range"
          aria-label="Position"
          data-testid="video-seek"
          min={0}
          max={duration || 0}
          step={0.1}
          value={Math.min(time, duration || 0)}
          onChange={(e) => {
            const v = video.current;
            if (v) v.currentTime = Number(e.target.value);
            setTime(Number(e.target.value));
          }}
          className="absolute inset-0 w-full cursor-pointer accent-amber-400"
        />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-300">
        <Button size="sm" onClick={toggle} data-testid="video-play">
          {playing ? "Pause" : "Play"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => jump(-10)} aria-label="Back 10 seconds">
          −10s
        </Button>
        <Button size="sm" variant="outline" onClick={() => jump(10)} aria-label="Forward 10 seconds">
          +10s
        </Button>
        <span className="font-mono tabular-nums">
          {clock(time)} / {clock(duration)}
        </span>
        <label className="ml-auto flex items-center gap-1">
          <span className="text-neutral-500">Speed</span>
          <select
            aria-label="Playback speed"
            data-testid="video-speed"
            value={speed}
            onChange={(e) => changeSpeed(Number(e.target.value))}
            className="rounded border border-neutral-700 bg-neutral-900 px-1 py-0.5 text-neutral-200"
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s === 1 ? "Normal" : `${s}×`}
              </option>
            ))}
          </select>
        </label>
        <Button size="sm" variant="outline" onClick={fullscreen} data-testid="video-fullscreen">
          {full ? "Exit full screen" : "Full screen"}
        </Button>
      </div>
      {error && <p className="text-xs text-rose-300">{error}</p>}
      {!full && (
        <p className="text-xs text-neutral-500">
          Click the bar to play from anywhere. Keys: space plays and pauses, ← → jump 5 s, f full screen, &lt; &gt; speed.
        </p>
      )}
    </div>
  );
}
