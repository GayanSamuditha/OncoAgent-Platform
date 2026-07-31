import type { NextConfig } from "next";

const backendApiOrigin = (
  process.env.BACKEND_API_ORIGIN ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/backend/ready",
        destination: `${backendApiOrigin}/ready`,
      },
      {
        source: "/backend/metrics",
        destination: `${backendApiOrigin}/metrics`,
      },
    ];
  },
};

export default nextConfig;
