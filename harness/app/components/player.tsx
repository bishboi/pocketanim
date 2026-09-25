"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { SceneIR } from "@/lib/pocketanim";
import { drawFrame } from "@/lib/draw";
import { Button } from "@/components/ui/button";

export function Player({
  ir,
  autoPlay = false,
  audioSrc = null,
}: {
  ir: Extract<SceneIR, { mode: "2d" }>;
  autoPlay?: boolean;
  audioSrc?: string | null;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(autoPlay);
  const total = ir.frames;

  const pictureAt = useCallback(
    (index: number) => {
      let cursor = index;
      for (const [count, indexes] of ir.runs) {
        if (cursor < count) {
          const picture = [];
          for (const piece of indexes) picture.push(...ir.pieces[piece]);
          return picture;
        }
        cursor -= count;
      }
      return [];
    },
    [ir.runs, ir.pieces],
  );

  const draw = useCallback(
    (index: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const { width, height } = canvas;
      drawFrame(ctx, ir.shapes, pictureAt(index), width, height, ir.background);
    },
    [ir.shapes, ir.background, pictureAt],
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
          : from + Math.floor(((now - started) / 1000) * ir.fps);
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
  }, [playing, ir.fps, total]);

  const seconds = (n: number) => (n / ir.fps).toFixed(1);

  return (
    <div className="flex flex-col gap-3">
      <canvas
        ref={canvasRef}
        width={1280}
        height={720}
        className="aspect-video h-auto w-full rounded border border-neutral-800 bg-black"
      />
      {audioSrc && <audio ref={audioRef} src={audioSrc} preload="auto" />}
      <div className="flex items-center gap-3">
        <Button
          size="sm"
          onClick={() => {
            if (frame >= total - 1) setFrame(0);
            setPlaying((p) => !p);
          }}
        >
          {playing ? "Pause" : "Play"}
        </Button>
        <input
          type="range"
          min={0}
          max={Math.max(0, total - 1)}
          value={frame}
          onChange={(e) => {
            setPlaying(false);
            setFrame(Number(e.target.value));
          }}
          className="w-full"
        />
        <span className="w-24 shrink-0 text-right text-xs tabular-nums text-neutral-500">
          {seconds(frame)}s / {seconds(total - 1)}s
        </span>
      </div>
      <p className="text-xs text-neutral-500">
        Drawn in the browser from the program&apos;s own geometry — no video, and
        no server round-trip per frame.
      </p>
    </div>
  );
}
