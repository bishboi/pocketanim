"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { SceneIR } from "@/lib/pocketanim";
import { drawLayered, imagePlacement, type PlacedImage } from "@/lib/draw";
import { Button } from "@/components/ui/button";

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

export function Player({
  ir,
  autoPlay = false,
  audioSrc = null,
  imageUrl,
}: {
  ir: Extract<SceneIR, { mode: "2d" }>;
  autoPlay?: boolean;
  audioSrc?: string | null;
  /** Where the build's photos and figures are served: the asset name goes on the end. */
  imageUrl?: (asset: string) => string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(autoPlay);
  const [speed, setSpeed] = useState(1);
  const [full, setFull] = useState(false);
  useEffect(() => {
    const onChange = () => setFull(document.fullscreenElement === boxRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  const total = ir.frames;

  const pictureAt = useCallback(
    (index: number) => {
      let cursor = index;
      for (const [count, indexes] of ir.runs) {
        if (cursor < count) {
          return indexes.map((piece) => ({ z: ir.pieceZ?.[piece] ?? 0, instances: ir.pieces[piece] }));
        }
        cursor -= count;
      }
      return [];
    },
    [ir.runs, ir.pieces, ir.pieceZ],
  );

  // Photos and figures: loaded once, drawn at their recorded places. A redraw
  // follows each load, so a picture appears as soon as it arrives.
  const loaded = useRef<Map<string, HTMLImageElement>>(new Map());
  const [imagesReady, setImagesReady] = useState(0);
  useEffect(() => {
    if (!imageUrl || !ir.images?.length) return;
    let cancelled = false;
    for (const image of ir.images) {
      if (loaded.current.has(image.asset)) continue;
      const element = new Image();
      element.onload = () => {
        if (!cancelled) setImagesReady((n) => n + 1);
      };
      element.src = imageUrl(image.asset);
      loaded.current.set(image.asset, element);
    }
    return () => {
      cancelled = true;
    };
  }, [ir.images, imageUrl]);

  const imagesAt = useCallback(
    (index: number): PlacedImage[] => {
      const out: PlacedImage[] = [];
      for (const image of ir.images ?? []) {
        const element = loaded.current.get(image.asset);
        if (!element || !element.complete || !element.naturalWidth) continue;
        const place = imagePlacement(image.keys, index);
        if (place) out.push({ z: image.z, image: element, width: element.naturalWidth, height: element.naturalHeight, ...place });
      }
      return out;
    },
    // imagesReady: a newly loaded picture changes what this returns.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ir.images, imagesReady],
  );

  const draw = useCallback(
    (index: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const { width, height } = canvas;
      drawLayered(ctx, ir.shapes, pictureAt(index), imagesAt(index), width, height, ir.background);
    },
    [ir.shapes, ir.background, pictureAt, imagesAt],
  );

  useEffect(() => {
    draw(frame);
  }, [frame, draw]);

  // Play on a wall clock rather than per animation frame, so playback runs at
  // the program's own fps on any display.
  useEffect(() => {
    if (!playing) {
      audioRef.current?.pause();
      return;
    }
    if (audioRef.current) {
      audioRef.current.currentTime = frame / ir.fps;
      audioRef.current.playbackRate = speed;
      void audioRef.current.play().catch(() => {});
    }
    const started = performance.now();
    const from = frame;
    let raf = 0;
    const tick = (now: number) => {
      // The narration is the master clock once it is actually playing, as on
      // the phone: a wall clock started before the audio had buffered let the
      // picture run ahead of a long lecture's voice.
      const audio = audioRef.current;
      const next =
        audio && !audio.paused && audio.readyState >= 2 && audio.currentTime > 0
          ? Math.floor(audio.currentTime * ir.fps)
          : from + Math.floor(((now - started) / 1000) * ir.fps * speed);
      if (next >= total - 1) {
        setFrame(total - 1);
        setPlaying(false);
        return;
      }
      setFrame(next);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // `frame` is the start point, captured once when playback begins.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, ir.fps, total, speed]);

  const clock = (n: number) => {
    const s = Math.max(0, Math.floor(n / ir.fps));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  };

  // Seeking while playing: playback restarts from the new frame (the effect above captures its start point).
  const seek = (to: number) => {
    const next = Math.min(Math.max(0, Math.round(to)), Math.max(0, total - 1));
    const wasPlaying = playing;
    setPlaying(false);
    setFrame(next);
    if (audioRef.current) audioRef.current.currentTime = next / ir.fps;
    if (wasPlaying) setTimeout(() => setPlaying(true), 0);
  };
  const toggle = () => {
    if (frame >= total - 1) setFrame(0);
    setPlaying((p) => !p);
  };
  const changeSpeed = (value: number) => {
    setSpeed(value);
    if (audioRef.current) audioRef.current.playbackRate = value;
    if (playing) {
      setPlaying(false);
      setTimeout(() => setPlaying(true), 0);
    }
  };
  const fullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void boxRef.current?.requestFullscreen?.().catch(() => {});
  };
  function onKey(event: React.KeyboardEvent) {
    const step = SPEEDS.indexOf(speed);
    const keys: Record<string, () => void> = {
      " ": toggle, k: toggle, f: fullscreen,
      ArrowLeft: () => seek(frame - 5 * ir.fps), ArrowRight: () => seek(frame + 5 * ir.fps),
      j: () => seek(frame - 10 * ir.fps), l: () => seek(frame + 10 * ir.fps),
      "<": () => changeSpeed(SPEEDS[Math.max(0, step - 1)]),
      ">": () => changeSpeed(SPEEDS[Math.min(SPEEDS.length - 1, step + 1)]),
    };
    if (keys[event.key]) {
      event.preventDefault();
      keys[event.key]();
    }
  }

  return (
    <div
      ref={boxRef}
      tabIndex={0}
      onKeyDown={onKey}
      className={`flex flex-col gap-3 outline-none ${full ? "h-full w-full justify-center bg-black p-3" : ""}`}
    >
      <canvas
        ref={canvasRef}
        width={1280}
        height={720}
        onClick={toggle}
        onDoubleClick={fullscreen}
        className={`aspect-video h-auto w-full rounded border border-neutral-800 bg-black ${full ? "max-h-[calc(100vh-5rem)] object-contain" : ""}`}
      />
      {audioSrc && <audio ref={audioRef} src={audioSrc} preload="auto" />}
      <input
        type="range"
        aria-label="Position"
        min={0}
        max={Math.max(0, total - 1)}
        value={frame}
        onChange={(e) => seek(Number(e.target.value))}
        className="w-full cursor-pointer accent-amber-400"
      />
      <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-300">
        <Button size="sm" onClick={toggle}>
          {playing ? "Pause" : "Play"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => seek(frame - 10 * ir.fps)}>−10s</Button>
        <Button size="sm" variant="outline" onClick={() => seek(frame + 10 * ir.fps)}>+10s</Button>
        <span className="font-mono tabular-nums">{clock(frame)} / {clock(total - 1)}</span>
        <label className="ml-auto flex items-center gap-1">
          <span className="text-neutral-500">Speed</span>
          <select
            aria-label="Playback speed"
            value={speed}
            onChange={(e) => changeSpeed(Number(e.target.value))}
            className="rounded border border-neutral-700 bg-neutral-900 px-1 py-0.5 text-neutral-200"
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>{s === 1 ? "Normal" : `${s}×`}</option>
            ))}
          </select>
        </label>
        <Button size="sm" variant="outline" onClick={fullscreen}>{full ? "Exit full screen" : "Full screen"}</Button>
      </div>
      <p className="text-xs text-neutral-500">
        Drawn in the browser from the program&apos;s own geometry — no video, and
        no server round-trip per frame.
      </p>
    </div>
  );
}
