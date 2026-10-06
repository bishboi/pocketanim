import { warmCaches } from "./lib/pocketanim";

// The server's start, on Node only (instrumentation.ts): warmed in the background, never awaited.
void warmCaches();
