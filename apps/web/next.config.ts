import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Desktop build (ADR-0008): a self-contained server.js run by the bundled Node runtime.
  ...(process.env.TABFORGE_WEB_OUTPUT === "standalone" ? { output: "standalone" as const } : {}),
};

export default nextConfig;
