import {
  PHASE_DEVELOPMENT_SERVER,
  PHASE_PRODUCTION_BUILD,
} from "next/constants";
import { describe, expect, it } from "vitest";

import nextConfig from "./next.config";

describe("next.config", () => {
  it("builds a static export with trailing-slash routes for FastAPI to serve", () => {
    const config = nextConfig(PHASE_PRODUCTION_BUILD);

    expect(config.output).toBe("export");
    expect(config.trailingSlash).toBe(true);
    expect(config.rewrites).toBeUndefined();
  });

  it("proxies /api to the local backend in next dev", async () => {
    const config = nextConfig(PHASE_DEVELOPMENT_SERVER);

    expect(config.output).toBeUndefined();
    expect(await config.rewrites?.()).toEqual([
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ]);
  });
});
