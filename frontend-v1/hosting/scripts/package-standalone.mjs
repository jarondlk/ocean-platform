/** Complete the owned Next standalone artifact; never copies credentials or legacy files. */
import { cp, mkdir, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const host = fileURLToPath(new URL("..", import.meta.url));
await stat(host + "/.next/standalone/hosting/server.js");
await mkdir(host + "/.next/standalone/hosting/.next", { recursive: true });
await cp(host + "/.next/static", host + "/.next/standalone/hosting/.next/static", { recursive: true, force: true });
