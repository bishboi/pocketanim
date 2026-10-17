/**
 * The geometry a browser draws a pocketanim program from (v1's harness/app/lib/pocketanim.ts types, as written by
 * harness_v2/engine/tools/scene_ir.py): the shapes, the pieces on screen frame by frame, the pictures.
 */


/** A raster image and where it is: keys are [frame, alpha, ulx, uly, urx, ury, dlx, dly] in scene units. */
export type SceneImage = { asset: string; width: number; height: number; z: number; keys: number[][] };

export type SceneIR =
  | {
      mode: "2d";
      fps: number;
      /** The program's clear colour, "#RRGGBB". Absent means black. */
      background?: string;
      shapes: number[][];
      pieces: Instance[][];
      runs: [number, number[]][];
      frames: number;
      /** Each piece's z, for slotting images into the draw order. */
      pieceZ?: number[];
      /** Photos and figures the program cannot carry, drawn by the player (scene_ir.py). */
      images?: SceneImage[];
      /**
       * A long lecture: the geometry is in segments (sceneSegment), and shapes, pieces and runs here are empty.
       * Each segment is a 2D scene of its own frames, from `start`.
       */
      segments?: { start: number; frames: number }[];
      error?: undefined;
    }
  | { mode: "3d"; fps: number; frames: number; error?: undefined }
  | { mode: "frames"; fps: number; frames: number; error?: undefined }
  | { error: string };

/** [shapeIndex, a, b, c, d, e, f, fillRGBA, strokeRGBA, strokeWidth] */
export type Instance = [
  number, number, number, number, number, number, number,
  number[], number[], number,
];

