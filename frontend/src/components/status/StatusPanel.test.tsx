import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { StatusPanel } from "./StatusPanel";

function stubFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })),
  );
}

describe("StatusPanel", () => {
  it("shows backend and database connected when health is ok", async () => {
    stubFetch(200, { status: "ok", database: "ok" });
    render(<StatusPanel />);

    expect(
      await screen.findByRole("row", { name: /backend.*connected/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("row", { name: /database.*connected/i }),
    ).toBeInTheDocument();
  });

  it("shows the database down when health returns 503", async () => {
    stubFetch(503, { status: "degraded", database: "down" });
    render(<StatusPanel />);

    expect(
      await screen.findByRole("row", { name: /database.*down/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("row", { name: /backend.*connected/i }),
    ).toBeInTheDocument();
  });

  it("shows the backend down when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    render(<StatusPanel />);

    expect(
      await screen.findByRole("row", { name: /backend.*down/i }),
    ).toBeInTheDocument();
  });

  it("shows the backend down when health returns an unexpected status", async () => {
    stubFetch(500, { detail: "boom" });
    render(<StatusPanel />);

    expect(
      await screen.findByRole("row", { name: /backend.*down/i }),
    ).toBeInTheDocument();
  });

  it("checks again when Recheck is pressed", async () => {
    stubFetch(503, { status: "degraded", database: "down" });
    render(<StatusPanel />);
    await screen.findByRole("row", { name: /database.*down/i });

    stubFetch(200, { status: "ok", database: "ok" });
    await userEvent.click(screen.getByRole("button", { name: /recheck/i }));

    expect(
      await screen.findByRole("row", { name: /database.*connected/i }),
    ).toBeInTheDocument();
  });
});
