"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { SceneIR } from "@/lib/pocketanim";
import { drawFrame } from "@/lib/draw";
import { Button } from "@/components/ui/button";

export function Player({ ir }: { ir: Extract<SceneIR, { mode: "2d" }> }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const total = ir.frames.length;

  const draw = useCallback(
    (index: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const { width, height } = canvas;
      drawFrame(ctx, ir.shapes, ir.frames[index] ?? [], width, height);
    },
    [ir],
  );

  useEffect(() => {
    draw(frame);
  }, [frame, draw]);

  // Play on a wall clock rather than per animation frame, so playback runs at
  // the program's own fps on any display.
  useEffect(() => {
    if (!playing) return;
    const started = performance.now();
    const from = frame;
    let raf = 0;
    const tick = (now: number) => {
      const elapsed = ((now - started) / 1000) * ir.fps;
      const next = from + Math.floor(elapsed);
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
        width={640}
        height={360}
        className="w-full rounded border border-neutral-800 bg-black"
      />
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
