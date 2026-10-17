import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

const DEV_BACKEND_URL = "http://localhost:8000";

const baseConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

// FastAPI serves the built files, so builds are a static export. Rewrites do not
// work with a static export, so `next dev` drops it and proxies /api instead.
export default function nextConfig(phase: string): NextConfig {
  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      ...baseConfig,
      rewrites: async () => [
        { source: "/api/:path*", destination: `${DEV_BACKEND_URL}/api/:path*` },
      ],
    };
  }

  return {
    ...baseConfig,
    output: "export",
    // Emits /route/index.html, which FastAPI StaticFiles resolves; /route.html it would not.
    trailingSlash: true,
  };
}
