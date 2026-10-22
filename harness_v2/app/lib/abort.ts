/**
 * Stopping a long job from anywhere inside it: the job runs in an abort scope (withAbort), and what it starts below,
 * however deep, sees the scope's signal: model requests end (timeoutOrAbort), subprocesses are killed with their
 * children (killOnAbort). Nothing has to pass the signal along by hand.
 */
import { AsyncLocalStorage } from "node:async_hooks";
import type { ChildProcess } from "node:child_process";

const scope = new AsyncLocalStorage<AbortSignal>();

/** Run `fn` with `signal` as the stop signal of everything it starts. */
export function withAbort<T>(signal: AbortSignal, fn: () => Promise<T>): Promise<T> {
  return scope.run(signal, fn);
}

/** The stop signal of the job this code runs in, if any. */
export function currentSignal(): AbortSignal | undefined {
  return scope.getStore();
}

/** Whether the job this code runs in has been stopped. */
export function stopped(): boolean {
  return !!scope.getStore()?.aborted;
}

/** A fetch signal that ends after `ms`, or when the job is stopped. */
export function timeoutOrAbort(ms: number): AbortSignal {
  const s = scope.getStore();
  return s ? AbortSignal.any([AbortSignal.timeout(ms), s]) : AbortSignal.timeout(ms);
}

/** Whether a subprocess should be started in its own process group (so a stop can kill all it started). */
export function detachedForAbort(): boolean {
  return !!scope.getStore();
}

/** Kill `child` and everything it started (its process group when it has one). */
export function killTree(child: ChildProcess): void {
  try {
    if (child.pid && detachedForAbort()) process.kill(-child.pid, "SIGKILL");
    else child.kill("SIGKILL");
  } catch {
    child.kill("SIGKILL");
  }
}

/** Kill `child` and everything it started when the job is stopped; returns the function that stops watching. */
export function killOnAbort(child: ChildProcess, onKill?: () => void): () => void {
  const s = scope.getStore();
  if (!s) return () => {};
  const kill = () => {
    onKill?.();
    try {
      if (child.pid) process.kill(-child.pid, "SIGKILL");
    } catch {
      child.kill("SIGKILL");
    }
  };
  if (s.aborted) {
    kill();
    return () => {};
  }
  s.addEventListener("abort", kill, { once: true });
  return () => s.removeEventListener("abort", kill);
}
