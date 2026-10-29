/** C25 loopback UI QA; production never imports this entry. */
export default {
  poweredByHeader: false,
  experimental: { cpus: 2, externalDir: true },
  async rewrites() {
    return ["/v1/:path*", "/catalogue/:path*", "/research/:path*", "/_ocean/:path*"].map(source => ({ source, destination: `http://127.0.0.1:3101${source}` }));
  },
};
