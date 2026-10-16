// The PDF viewer's worker is served from public/ (pdf.js runs it in a Web Worker).
import { copyFileSync, existsSync } from "node:fs";
const from = "node_modules/pdfjs-dist/build/pdf.worker.min.mjs";
if (existsSync(from)) copyFileSync(from, "public/pdf.worker.min.mjs");
