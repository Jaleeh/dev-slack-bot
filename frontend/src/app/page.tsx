import { StatusPanel } from "@/components/status/StatusPanel";

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-12 sm:px-8 sm:py-16">
      <header className="mb-10 border-b border-rule pb-6">
        <p className="mb-1.5 text-xs uppercase tracking-[0.08em] text-muted-foreground">
          dev-slack-bot · local
        </p>
        <h1 className="text-3xl font-semibold">System status</h1>
        <p className="mt-2 text-muted-foreground">
          Whether the backend and its database are reachable from this browser.
        </p>
      </header>
      <StatusPanel />
    </main>
  );
}
