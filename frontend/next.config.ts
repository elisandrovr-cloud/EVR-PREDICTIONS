import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    // In local dev (no nginx) proxy API calls straight to the backend.
    const backend = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";
    return process.env.NODE_ENV === "development"
      ? [{ source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` }]
      : [];
  },
};

export default nextConfig;
