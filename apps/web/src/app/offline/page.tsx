import type { Metadata } from "next";

export const metadata: Metadata = { title: "Offline" };

export default function OfflinePage() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 px-6 text-center">
      <span className="brand-gradient grid size-14 place-items-center rounded-2xl text-white">
        <svg viewBox="0 0 24 24" className="size-7" fill="none" aria-hidden>
          <path
            d="M5 18V6l14 12V6"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <h1 className="text-2xl font-semibold tracking-tight">You&apos;re offline</h1>
      <p className="text-muted-foreground max-w-sm">
        Nexora needs a connection to reach your assistant. Your conversations are safe. Reconnect and refresh.
      </p>
    </main>
  );
}
