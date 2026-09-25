import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A stray lockfile in harness/ otherwise becomes the traced workspace root.
  outputFileTracingRoot: path.join(process.cwd()),
};

export default nextConfig;
