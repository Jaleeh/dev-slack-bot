"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  type ConnectionState,
  fetchHealth,
  type HealthStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const STATE_LABEL: Record<ConnectionState, string> = {
  connected: "Connected",
  down: "Down",
  unknown: "Unknown",
};

const STATE_STYLE: Record<ConnectionState, string> = {
  connected: "bg-ok-soft text-ok",
  down: "bg-warn-soft text-warn",
  unknown: "bg-code text-muted-foreground",
};

export function StatusPanel() {
  const [health, setHealth] = useState<HealthStatus | undefined>();
  const [isChecking, setIsChecking] = useState(true);

  function showResult(result: HealthStatus) {
    setHealth(result);
    setIsChecking(false);
  }

  useEffect(() => {
    // Ignores a response that arrives after unmount (or after StrictMode's test unmount).
    let isActive = true;
    fetchHealth().then((result) => {
      if (isActive) showResult(result);
    });
    return () => {
      isActive = false;
    };
  }, []);

  function recheck() {
    setIsChecking(true);
    fetchHealth().then(showResult);
  }

  return (
    <section aria-labelledby="status-heading" className="space-y-6">
      <table className="w-full border-collapse text-sm">
        <caption id="status-heading" className="sr-only">
          Service status
        </caption>
        <tbody>
          <StatusRow
            name="Backend"
            detail="FastAPI · /api/health"
            state={health?.backend}
          />
          <StatusRow
            name="Database"
            detail="Postgres 18 · pgvector"
            state={health?.database}
          />
        </tbody>
      </table>

      <footer className="flex items-center justify-between gap-4 text-sm text-muted-foreground">
        <p aria-live="polite">
          {health
            ? `Last checked ${health.checkedAt.toLocaleTimeString()}`
            : "Checking…"}
        </p>
        <Button variant="outline" onClick={recheck} disabled={isChecking}>
          Recheck
        </Button>
      </footer>
    </section>
  );
}

function StatusRow(props: {
  name: string;
  detail: string;
  state: ConnectionState | undefined;
}) {
  return (
    <tr className="border-b border-rule last:border-b-0">
      <th scope="row" className="py-4 pr-4 text-left font-medium">
        {props.name}
      </th>
      <td className="py-4 pr-4 font-mono text-xs text-muted-foreground">
        {props.detail}
      </td>
      <td className="py-4 text-right">
        {props.state ? (
          <span
            className={cn(
              "inline-block rounded-sm px-2 py-0.5 text-[0.72rem] font-bold uppercase tracking-[0.08em]",
              STATE_STYLE[props.state],
            )}
          >
            {STATE_LABEL[props.state]}
          </span>
        ) : (
          <span className="text-muted-foreground">…</span>
        )}
      </td>
    </tr>
  );
}
