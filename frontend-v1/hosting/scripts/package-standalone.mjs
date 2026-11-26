/** Complete the owned Next standalone artifact; never copies credentials or legacy files. */
import { cp, mkdir, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const host = fileURLToPath(new URL("..", import.meta.url));
await stat(host + "/.next/standalone/hosting/server.js");
await mkdir(host + "/.next/standalone/hosting/.next", { recursive: true });
const assets = host + "/.next/standalone/hosting/.next/static";
await cp(host + "/.next/static", assets, { recursive: true, force: true });
const fontLicenses = {
  "IBM-Plex-Sans": "@fontsource-variable/ibm-plex-sans",
  "IBM-Plex-Sans-JP": "@fontsource/ibm-plex-sans-jp",
  "IBM-Plex-Mono": "@fontsource/ibm-plex-mono",
};
await mkdir(assets + "/licenses", { recursive: true });
await Promise.all(Object.entries(fontLicenses).map(([name, pkg]) =>
  cp(host + "/../node_modules/" + pkg + "/LICENSE", assets + "/licenses/" + name + ".txt")));
