"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { SceneIR } from "@/lib/pocketanim";
import { drawLayered, imagePlacement, type PlacedImage } from "@/lib/draw";
import { Button } from "@/components/ui/button";

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
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(autoPlay);
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
