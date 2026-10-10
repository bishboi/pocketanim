"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

/**
 * Clears what this browser keeps for the app (harness/scripts/clear_all.sh says to open it): the lecture page's
 * versions and traces (IndexedDB "pocketanim"), and the settings and SVG lab state in localStorage.
 */
export default function Reset() {
  const [state, setState] = useState("Clearing this browser's lecture history...");

  useEffect(() => {
    const clear = async () => {
      try {
        for (const key of Object.keys(localStorage)) {
          if (key.startsWith("panim.") || key.startsWith("svg-lab")) localStorage.removeItem(key);
        }
        sessionStorage.clear();
      } catch {
        // Storage blocked: there is nothing kept to clear.
      }
      await new Promise<void>((resolve) => {
        try {
          const request = indexedDB.deleteDatabase("pocketanim");
          request.onsuccess = request.onerror = request.onblocked = () => resolve();
        } catch {
          resolve();
        }
      });
      setState("Cleared: lecture versions, page state and settings in this browser.");
    };
    void clear();
  }, []);

  return (
    <main style={{ padding: 24, fontFamily: "sans-serif" }}>
      <p>{state}</p>
      <p><Link href="/">Back to the lecture page</Link></p>
    </main>
  );
}
