import { pdfjs } from "react-pdf";

let configured = false;

/** Configure PDF.js worker once (must match pdfjs-dist version). */
export function ensurePdfWorker(): void {
  if (typeof window === "undefined" || configured) return;
  pdfjs.GlobalWorkerOptions.workerSrc = `/pdf.worker.${pdfjs.version}.min.mjs`;
  configured = true;
}
