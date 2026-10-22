import type { NextConfig } from "next";

// Same-origin proxy so a remote browser only needs the frontend URL: /api-proxy/* is forwarded to the backend over the
// Docker network. Override the target for non-Docker development with BACKEND_INTERNAL_URL (read at build/start time).
const backend = (process.env.BACKEND_INTERNAL_URL ?? "http://backend:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  agentRules: false,
  output: "standalone",
  async rewrites() {
    return [{ source: "/api-proxy/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
