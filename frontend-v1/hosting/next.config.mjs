import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** Independent Node host. The accepted static export remains unchanged. */
export default {
  poweredByHeader: false,
  output: "standalone",
  outputFileTracingRoot: resolve(dirname(fileURLToPath(import.meta.url)), ".."),
  experimental: { cpus: 2, externalDir: true },
  async headers() {
    return [{ source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "same-origin" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
      { key: "Content-Security-Policy", value: "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; frame-src 'none'; form-action 'self' https://accounts.google.com; base-uri 'self'; frame-ancestors 'none'" },
    ] }];
  },
};
