"use client";

import { useEffect, useState } from "react";

type Status = {
  version?: { version: string; commit: string | null; branch: string | null; dirty: boolean; date: string | null };
  resources?: { id: string; label: string; ready: boolean; detail: string; install?: string }[];
};

/** The harness version on every page, and what is not installed yet (with a button to get it). */
export function VersionBar() {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

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
    setNote(data.ok ? `${what} installed` : `${what} failed: ${data.output ?? data.error ?? response.status}`);
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
      {missing.map((r) => (
        <span key={r.id} title={r.detail} data-testid={`resource-${r.id}`}
          className={r.detail.startsWith("NONE") ? "font-semibold text-red-400" : "text-amber-300/90"}>
          {r.label}: {r.detail}
          {r.install && (
            <button type="button" disabled={!!busy} onClick={() => install(r.install!)}
              className="ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-neutral-100 hover:bg-neutral-700">
              {busy === r.install ? "downloading…" : "download"}
            </button>
          )}
        </span>
      ))}
      {note && <span className="text-neutral-300">{note}</span>}
    </div>
  );
}
