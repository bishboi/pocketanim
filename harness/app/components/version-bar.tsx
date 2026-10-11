"use client";

import { useEffect, useState } from "react";

type Status = {
  version?: { version: string; commit: string | null; branch: string | null; dirty: boolean; date: string | null };
  resources?: { id: string; label: string; ready: boolean; detail: string; install?: string }[];
};

/** What /api/image-check found: a real call to the image model. */
type ImageCheck = { ok: boolean; model: string; error?: string; seconds?: number; usd?: number; png?: string;
  svg?: string | null; paths?: number; note?: string | null };

/** The harness version on every page, and what is not installed yet (with a button to get it). */
export function VersionBar() {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [check, setCheck] = useState<ImageCheck | null>(null);
  const [checking, setChecking] = useState(false);

  /** Ask the image model for one picture now, to tell a failing model apart from a lecture that drew SVGs. */
  async function testImages() {
    setChecking(true);
    setCheck(null);
    const response = await fetch("/api/image-check", { method: "POST" }).catch(() => null);
    const data = (await response?.json().catch(() => null)) as ImageCheck | null;
    setCheck(data ?? { ok: false, model: "?", error: `the check did not answer (${response?.status ?? "offline"})` });
    setChecking(false);
  }
  const testButton = (
    <button type="button" disabled={checking} onClick={testImages} data-testid="image-check"
      className="ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-neutral-100 hover:bg-neutral-700">
      {checking ? "asking the image model…" : "test"}
    </button>
  );

  const load = () => fetch("/api/status").then((r) => r.json()).then(setStatus).catch(() => setStatus(null));
  useEffect(() => {
    load();
  }, []);

  async function install(what: string) {
    setBusy(what);
    setNote(null);
    const response = await fetch("/api/setup", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ what }) });
    const data = await response.json().catch(() => ({}));
    // The script's last line says what it found ("LaTeX is ready.", or what is still missing).
    const last = String(data.output ?? "").trim().split("\n").pop();
    setNote(data.ok ? `${what} installed${last ? `: ${last}` : ""}` : `${what} failed: ${data.output ?? data.error ?? response.status}`);
    setBusy(null);
    load();
  }

  const v = status?.version;
  const missing = (status?.resources ?? []).filter((r) => !r.ready);
  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 rounded border border-neutral-800 bg-neutral-950 px-3 py-1.5 text-xs text-neutral-400"
      data-testid="version-bar">
      <span className="font-mono text-neutral-200" data-testid="version">
        {v ? `v${v.version}` : "v?"}
        {v?.commit ? ` · ${v.commit}${v.dirty ? "+" : ""}` : ""}
        {v?.branch ? ` · ${v.branch}` : ""}
        {v?.date ? ` · ${v.date}` : ""}
      </span>
      {(status?.resources ?? []).filter((r) => r.ready).map((r) => (
        // What is ready, as a small tick: hovering says what it is (LaTeX says where it was found).
        <span key={r.id} title={r.detail} data-testid={`ready-${r.id}`} className="text-emerald-400/80">
          {r.label} ✓
          {r.id === "pictures" && testButton}
          {r.install && (
            <button type="button" disabled={!!busy} onClick={() => install(r.install!)}
              className="ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-neutral-100 hover:bg-neutral-700">
              {busy === r.install ? "downloading…" : "complete"}
            </button>
          )}
        </span>
      ))}
      {missing.map((r) => (
        <span key={r.id} title={r.detail} data-testid={`resource-${r.id}`}
          className={r.detail.startsWith("NONE") ? "font-semibold text-red-400" : "text-amber-300/90"}>
          {r.label}: {r.detail}
          {r.id === "pictures" && testButton}
          {r.install && (
            <button type="button" disabled={!!busy} onClick={() => install(r.install!)}
              className="ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-neutral-100 hover:bg-neutral-700">
              {busy === r.install ? "downloading…" : "download"}
            </button>
          )}
        </span>
      ))}
      {note && <span className="text-neutral-300">{note}</span>}
      {check && (
        <div className="mt-1 flex w-full flex-wrap items-start gap-3 border-t border-neutral-800 pt-1.5" data-testid="image-check-result">
          {check.ok ? (
            <>
              <span className="text-emerald-400">
                Image model works: {check.model} made a picture in {check.seconds}s
                {check.usd ? ` for $${check.usd.toFixed(4)}` : ""}.
                {check.svg ? ` The phone draws it traced into ${check.paths} vector shape${check.paths === 1 ? "" : "s"} (right).` : ` ${check.note ?? ""}`}
                {" "}If a lecture still shows only SVG drawings, its log says how many pictures the script asked for.
              </span>
              {check.png && (
                <figure className="text-center">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={check.png} alt="as the model made it" className="h-28 rounded bg-neutral-200 object-contain p-1" />
                  <figcaption>as the model made it</figcaption>
                </figure>
              )}
              {check.svg && (
                <figure className="text-center">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(check.svg)}`} alt="as the phone draws it"
                    className="h-28 rounded bg-neutral-200 object-contain p-1" />
                  <figcaption>as the phone draws it</figcaption>
                </figure>
              )}
            </>
          ) : (
            <span className="font-semibold text-red-400">Image model FAILED ({check.model}): {check.error}</span>
          )}
          <button type="button" onClick={() => setCheck(null)} className="ml-auto text-neutral-500 hover:text-neutral-300">close</button>
        </div>
      )}
    </div>
  );
}
