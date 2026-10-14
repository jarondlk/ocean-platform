/** P00 is a static, synthetic preview. It has no API or authentication routes. */
const nextConfig = {
  output: "export",
  poweredByHeader: false,
  images: { unoptimized: true },
  experimental: { cpus: 2 },
};
export default nextConfig;
