/** Separate loopback development app; no production export or fixture fallback. */
export default {
  poweredByHeader: false,
  experimental: { cpus: 2, externalDir: true },
  async rewrites() {
    return ["/v1/:path*", "/catalogue/:path*", "/research/:path*"].map(source => ({ source, destination: `http://127.0.0.1:3101${source}` }));
  },
};
