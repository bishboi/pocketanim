// The PDF viewer's worker is served from public/ (pdf.js runs it in a Web Worker). public/ holds nothing else, and
// git keeps no empty folder, so it is made here.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
const from = "node_modules/pdfjs-dist/build/pdf.worker.min.mjs";
mkdirSync("public", { recursive: true });
if (existsSync(from)) copyFileSync(from, "public/pdf.worker.min.mjs");
else console.warn(`${from} not found: the PDF viewer will not load until npm install has run`);
