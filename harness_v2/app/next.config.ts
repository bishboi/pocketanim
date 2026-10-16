import { existsSync, readFileSync } from "fs";
import path from "path";
import type { NextConfig } from "next";

// v2 reads its own .env.local (Next loads it); what that does not set is taken from v1's harness/app/.env.local, so
// the keys and models set up for v1 work here as they are (lib/models.ts names the variables each model reads).
const v1 = path.join(process.cwd(), "..", "..", "harness", "app", ".env.local");
if (existsSync(v1)) {
  for (const line of readFileSync(v1, "utf8").split("\n")) {
    const m = /^\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*?)\s*$/.exec(line);
    if (!m || process.env[m[1]] !== undefined) continue;
    process.env[m[1]] = m[2].replace(/^(["'])(.*)\1$/, "$2");
  }
}

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.join(process.cwd()),
  // The offline PDF reader runs pdf.js on the server, as it is shipped.
  serverExternalPackages: ["pdfjs-dist", "sharp"],
};

export default nextConfig;
