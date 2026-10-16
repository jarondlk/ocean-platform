import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import { dirname, extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { loopbackHost, modeEnvelope, previewMode } from "./preview-mode.mjs";

const mode = previewMode(process.argv.slice(2));
const directory = resolve(dirname(fileURLToPath(import.meta.url)), "../out");
await stat(resolve(directory, "index.html"));
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2" };
const server = http.createServer(async (request, response) => {
  try {
    if (!loopbackHost(request.headers.host)) { response.writeHead(403).end(); return; }
    const url = new URL(request.url, "http://127.0.0.1:3100");
    if (url.pathname === "/_ocean/runtime-mode") {
      response.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
      response.end(JSON.stringify(modeEnvelope(mode))); return;
    }
    const path = resolve(directory, `.${decodeURIComponent(url.pathname === "/" ? "/index.html" : url.pathname)}`);
    if (!path.startsWith(`${directory}${sep}`)) { response.writeHead(403).end(); return; }
    let content; let extension = extname(path);
    try { content = await readFile(path); } catch (error) { if (extension) throw error; content = await readFile(`${path}.html`); extension = ".html"; }
    response.writeHead(200, { "Content-Type": types[extension] ?? "application/octet-stream", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer" });
    response.end(content);
  } catch { response.writeHead(404, { "Content-Type": "text/plain" }).end("Not found"); }
});
server.listen(3100, "127.0.0.1", () => console.log(`OCEAN v1 local ${mode}: http://127.0.0.1:3100`));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.close(() => process.exit(0)));
