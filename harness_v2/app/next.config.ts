import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.join(process.cwd()),
  // The offline PDF reader runs pdf.js on the server, as it is shipped.
  serverExternalPackages: ["pdfjs-dist"],
};

export default nextConfig;
