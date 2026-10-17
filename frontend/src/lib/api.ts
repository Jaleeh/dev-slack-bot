export type ConnectionState = "connected" | "down" | "unknown";

export type HealthStatus = {
  backend: ConnectionState;
  database: ConnectionState;
  checkedAt: Date;
};

const HEALTH_URL = "/api/health";

/** Checks the backend and database. Never throws: failures map to "down" or "unknown". */
export async function fetchHealth(): Promise<HealthStatus> {
  const checkedAt = new Date();

  try {
    const response = await fetch(HEALTH_URL, { cache: "no-store" });
    return { ...statesFor(response.status), checkedAt };
  } catch {
    return { backend: "down", database: "unknown", checkedAt };
  }
}

function statesFor(
  httpStatus: number,
): Pick<HealthStatus, "backend" | "database"> {
  if (httpStatus === 200)
    return { backend: "connected", database: "connected" };
  if (httpStatus === 503) return { backend: "connected", database: "down" };

  // Any other answer means the backend itself is unhealthy, so the database is unknown.
  return { backend: "down", database: "unknown" };
}
