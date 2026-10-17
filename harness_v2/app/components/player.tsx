"use client";

/**
 * v1's web player (harness/app/components/player.tsx), as v2 uses it: a scene is not a video but the program the phone
 * plays, drawn in the browser from its geometry (scene_ir.json) on a canvas, frame by frame, at the program's fps.
 * v2 adds a range (one beat of a chapter: played from its first frame to its last, and again), plain buttons, a
 * still of one frame (FrameStill), and the loading of a scene's geometry from its URL (IRPlayer).
 */

import { useEffect, useRef, useState, useCallback } from "react";
import type { SceneIR } from "@/lib/ir";
import { drawLayered, imagePlacement, type PlacedImage } from "@/lib/draw";

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

type Scene2D = Extract<SceneIR, { mode: "2d" }>;

/** The pieces on screen at `index` of a scene (or of one segment of one), each with its z. */
function layersAt(scene: Pick<Scene2D, "runs" | "pieces" | "pieceZ">, index: number) {
  let cursor = index;
  for (const [count, indexes] of scene.runs) {
    if (cursor < count) {
      return indexes.map((piece) => ({ z: scene.pieceZ?.[piece] ?? 0, instances: scene.pieces[piece] }));
    }
    cursor -= count;
  }
  return [];
}

export function Player({
  ir,
  autoPlay = false,
  audioSrc = null,
  imageUrl,
  segmentUrl,
  range,
  compact = false,
}: {
  ir: Scene2D;
  /** Only these frames [first, last]: a beat in its chapter. */
  range?: [number, number];
  compact?: boolean;
  autoPlay?: boolean;
  audioSrc?: string | null;
  /** Where the build's photos and figures are served: the asset name goes on the end. */
  imageUrl?: (asset: string) => string;
  /** Where a long lecture's geometry segments are served (ir.segments): the segment's number goes on the end. */
  segmentUrl?: (index: number) => string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const first = Math.max(0, range?.[0] ?? 0);
  const [frame, setFrame] = useState(first);
  const [playing, setPlaying] = useState(autoPlay);
  const [speed, setSpeed] = useState(1);
  const [full, setFull] = useState(false);
  useEffect(() => {
    const onChange = () => setFull(document.fullscreenElement === boxRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  // The last frame played, plus one (a range ends at its own last frame).
  const total = range ? Math.min(ir.frames, range[1] + 1) : ir.frames;
  // The voice stops with its player: a lecture switched away from kept talking over the next one.
  useEffect(() => {
    const audio = audioRef.current;
    return () => {
      audio?.pause();
    };
  }, []);

  // A long lecture comes in segments of about two minutes: the one playing and the next are loaded, the rest
  // are fetched when reached and dropped when left behind, so an hour of geometry is never in the tab at once.
  const segments = ir.segments;
  const loadedSegments = useRef<Map<number, Scene2D & { start: number }>>(new Map());
  const pendingSegments = useRef<Set<number>>(new Set());
  const [segmentsReady, setSegmentsReady] = useState(0);
  const [waiting, setWaiting] = useState(false);
  const segmentOf = useCallback(
    (index: number) => {
      if (!segments?.length) return -1;
      let k = 0;
      while (k + 1 < segments.length && segments[k + 1].start <= index) k++;
      return k;
    },
    [segments],
  );
  const ensure = useCallback(
    (k: number) => {
      if (!segments || !segmentUrl || k < 0 || k >= segments.length) return;
      if (loadedSegments.current.has(k) || pendingSegments.current.has(k)) return;
      pendingSegments.current.add(k);
      fetch(segmentUrl(k))
        .then((response) => (response.ok ? response.json() : Promise.reject(new Error(`${response.status}`))))
        .then((data) => {
          loadedSegments.current.set(k, { ...data, start: segments[k].start });
          // Keep the segment just loaded and its neighbours; a tab holding every segment is the problem solved.
          for (const held of [...loadedSegments.current.keys()]) {
            if (Math.abs(held - k) > 2) loadedSegments.current.delete(held);
          }
          setSegmentsReady((n) => n + 1);
        })
        .catch(() => {})
        .finally(() => pendingSegments.current.delete(k));
    },
    [segments, segmentUrl],
  );
  /** Whether the geometry for `index` is here (fetching it, and the segment after, when not). */
  const ready = useCallback(
    (index: number) => {
      if (!segments?.length) return true;
      const k = segmentOf(index);
      ensure(k);
      const seg = loadedSegments.current.get(k);
      if (seg && index - seg.start > seg.frames / 2) ensure(k + 1);
      return !!seg;
    },
    [segments, segmentOf, ensure],
  );
  useEffect(() => {
    ensure(0);
    ensure(1);
  }, [ensure]);

  /** The atlas and the layers for a frame, or null while its segment is still on its way. */
  const pictureAt = useCallback(
    (index: number): { shapes: number[][]; layers: ReturnType<typeof layersAt> } | null => {
      if (!segments?.length) return { shapes: ir.shapes, layers: layersAt(ir, index) };
      if (!ready(index)) return null;
      const seg = loadedSegments.current.get(segmentOf(index))!;
      return { shapes: seg.shapes, layers: layersAt(seg, index - seg.start) };
    },
    // segmentsReady: a segment that arrives changes what this returns.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ir, segments, ready, segmentOf, segmentsReady],
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

      const picture = pictureAt(index);
      if (!picture) return;                 // its segment is loading: the last frame stays up meanwhile
      const { width, height } = canvas;
      drawLayered(ctx, picture.shapes, picture.layers, imagesAt(index), width, height, ir.background);
    },
    [ir.background, pictureAt, imagesAt],
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
      const audio = audioRef.current;
      const at = frame / ir.fps;
      // Before its metadata is in, a media element ignores a seek: make it once it can.
      if (audio.readyState >= 1) audio.currentTime = at;
      else audio.addEventListener("loadedmetadata", () => { audio.currentTime = at; }, { once: true });
      audio.playbackRate = speed;
      void audio.play().catch(() => {});
    }
    let started = performance.now();
    let from = frame;
    let held: number | null = null;          // the frame playback waits at while its segment loads
    let lastResync = 0;
    let raf = 0;
    const tick = (now: number) => {
      // The narration is the master clock once it is actually playing, as on
      // the phone: a wall clock started before the audio had buffered let the
      // picture run ahead of a long lecture's voice.
      const audio = audioRef.current;
      if (held !== null) {
        if (!ready(held)) {
          raf = requestAnimationFrame(tick);
          return;
        }
        // The segment is here: carry on from where the picture stopped, voice and all.
        from = held;
        started = now;
        if (audio) {
          audio.currentTime = held / ir.fps;
          void audio.play().catch(() => {});
        }
        held = null;
        setWaiting(false);
      }
      // The voice leads only while it is where playback should be. A seek the audio could not make (a file
      // still loading, a server without byte ranges) left it at 0, and following it sent the picture back to
      // the start: then the wall clock leads, and the voice is asked again to move to it.
      const wall = from + Math.floor(((now - started) / 1000) * ir.fps * speed);
      let next = wall;
      if (audio && !audio.paused && audio.readyState >= 2) {
        const heard = Math.floor(audio.currentTime * ir.fps);
        if (Math.abs(heard - wall) <= ir.fps * 2) {
          next = heard;
        } else if (now - lastResync > 1000) {
          lastResync = now;
          audio.currentTime = wall / ir.fps;
        }
      }
      if (!ready(Math.min(next, total - 1))) {
        held = Math.min(next, total - 1);
        audio?.pause();
        setWaiting(true);
        raf = requestAnimationFrame(tick);
        return;
      }
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
  }, [playing, ir.fps, total, speed, ready]);

  const clock = (n: number) => {
    const s = Math.max(0, Math.floor(n / ir.fps));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  };

  // Seeking while playing: playback restarts from the new frame (the effect above captures its start point).
  const seek = (to: number) => {
    const next = Math.min(Math.max(first, Math.round(to)), Math.max(first, total - 1));
    const wasPlaying = playing;
    setPlaying(false);
    setFrame(next);
    if (audioRef.current) audioRef.current.currentTime = next / ir.fps;
    if (wasPlaying) setTimeout(() => setPlaying(true), 0);
  };
  const toggle = () => {
    if (frame >= total - 1) setFrame(first);
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
      className={`flex flex-col ${compact ? "gap-1" : "gap-3"} outline-none ${full ? "h-full w-full justify-center bg-black p-3" : ""}`}
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
        min={first}
        max={Math.max(first, total - 1)}
        value={frame}
        onChange={(e) => seek(Number(e.target.value))}
        className="w-full cursor-pointer accent-amber-400"
      />
      <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-300">
        <button className="rounded bg-amber-500 px-2.5 py-0.5 font-semibold text-black" onClick={toggle} data-testid="player-play">
          {playing ? "Pause" : "Play"}
        </button>
        {!compact && <button className="rounded border border-neutral-700 px-2 py-0.5 hover:bg-neutral-800" onClick={() => seek(frame - 10 * ir.fps)}>−10s</button>}
        {!compact && <button className="rounded border border-neutral-700 px-2 py-0.5 hover:bg-neutral-800" onClick={() => seek(frame + 10 * ir.fps)}>+10s</button>}
        <span className="font-mono tabular-nums">{clock(frame - first)} / {clock(total - 1 - first)}</span>
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
        <button className="rounded border border-neutral-700 px-2 py-0.5 hover:bg-neutral-800" onClick={fullscreen}>{full ? "Exit full screen" : "Full screen"}</button>
      </div>
      {waiting && <p className="text-xs text-amber-400">Loading the next part of the lecture…</p>}
      {!compact && <p className="text-xs text-neutral-500">
        Drawn in the browser from the program&apos;s own geometry — no video, and
        no server round-trip per frame.
      </p>}
    </div>
  );
}


// ---------------- v2: loading a scene's geometry, a still, the player from a URL ----------------

const IR_CACHE = new Map<string, Promise<SceneIR>>();

/** A scene's geometry from its URL (kept: a chapter's frames and its player share one). */
export function useIR(src?: string): { ir?: SceneIR; error?: string } {
  const [state, setState] = useState<{ ir?: SceneIR; error?: string }>({});
  useEffect(() => {
    if (!src) return;
    let live = true;
    if (!IR_CACHE.has(src)) IR_CACHE.set(src, fetch(src).then(async (r) => (r.ok ? r.json() : { error: (await r.json().catch(() => ({}))).error ?? `${r.status}` })));
    IR_CACHE.get(src)!.then((ir) => live && setState(ir.error ? { error: ir.error } : { ir })).catch((e) => live && setState({ error: String(e) }));
    return () => { live = false; };
  }, [src]);
  return state;
}

/** v1's player on a scene's geometry at `src` (its pictures under `assets`), all of it or a range of frames. */
export function IRPlayer({ src, assets, range, compact, autoPlay, audio }: { src: string; assets: string; range?: [number, number]; compact?: boolean; autoPlay?: boolean;
  /** The narration track, played as the clock (a scene spoken with a voice). */
  audio?: string }) {
  const { ir, error } = useIR(src);
  const imageUrl = useCallback((asset: string) => `${assets}${encodeURIComponent(asset)}`, [assets]);
  const segmentUrl = useCallback((k: number) => `${src}&segment=${k}`, [src]);
  if (error) return <p className="text-xs text-red-300">The player could not load it: {error}</p>;
  if (!ir) return <div className="flex aspect-video w-full items-center justify-center rounded border border-neutral-800 bg-black text-xs text-neutral-500">loading the scene…</div>;
  if (!("mode" in ir) || ir.mode !== "2d") return <p className="text-xs text-amber-300">This scene has no 2D geometry for the browser player ({"mode" in ir ? ir.mode : "none"}).</p>;
  return <Player key={`${src}|${range?.join("-")}|${audio ?? ""}`} ir={ir} imageUrl={imageUrl} segmentUrl={segmentUrl} range={range} compact={compact} autoPlay={autoPlay}
    audioSrc={audio ?? null} />;
}

/** One frame of a scene, drawn from its geometry (a beat's last frame in a chapter's strip). */
export function FrameStill({ src, assets, frame, className }: { src: string; assets: string; frame: number; className?: string }) {
  const { ir } = useIR(src);
  const ref = useRef<HTMLCanvasElement>(null);
  const [tick, setTick] = useState(0);
  const images = useRef<Map<string, HTMLImageElement>>(new Map());
  useEffect(() => {
    if (!ir || !("mode" in ir) || ir.mode !== "2d") return;
    for (const image of ir.images ?? []) {
      if (images.current.has(image.asset)) continue;
      const el = new Image();
      el.onload = () => setTick((n) => n + 1);
      el.src = `${assets}${encodeURIComponent(image.asset)}`;
      images.current.set(image.asset, el);
    }
  }, [ir, assets]);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !ir || !("mode" in ir) || ir.mode !== "2d" || ir.segments?.length) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const at = Math.min(Math.max(0, frame), ir.frames - 1);
    const placed: PlacedImage[] = [];
    for (const image of ir.images ?? []) {
      const el = images.current.get(image.asset);
      const place = imagePlacement(image.keys, at);
      if (el?.complete && el.naturalWidth && place) placed.push({ z: image.z, image: el, width: el.naturalWidth, height: el.naturalHeight, ...place });
    }
    drawLayered(ctx, ir.shapes, layersAt(ir, at), placed, canvas.width, canvas.height, ir.background);
  }, [ir, frame, tick]);
  return <canvas ref={ref} width={640} height={360} className={className ?? "aspect-video w-full rounded bg-black"} />;
}
