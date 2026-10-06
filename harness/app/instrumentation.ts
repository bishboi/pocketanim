/**
 * Runs once as the server starts: the build caches are warmed in the background (instrumentation-node.ts,
 * lib/pocketanim.ts warmCaches), not on the first lecture's time.
 */
export async function register() {
  // Inside the check, so the edge bundle leaves the Node-only module out.
  if (process.env.NEXT_RUNTIME === "nodejs") await import("./instrumentation-node");
}
