"use client";

import { useSession } from "@/lib/session";

export function AuthControls() {
  const { status, user, error, signOut } = useSession();

  if (status === "loading") {
    return (
      <div className="flex items-center gap-2 border border-line bg-surface/80 px-3 py-1.5 backdrop-blur-sm">
        <span className="size-1.5 animate-pulse rounded-full bg-muted" aria-hidden />
        <span className="font-mono text-[11px] text-muted">Checking session</span>
      </div>
    );
  }

  if (status === "unconfigured") {
    return (
      <div
        className="flex items-center gap-2 border border-line bg-surface/80 px-3 py-1.5 backdrop-blur-sm"
        title="Auth0 is not configured in this environment"
      >
        <span className="size-1.5 rounded-full bg-amber-500" aria-hidden />
        <span className="font-mono text-[11px] text-muted">Auth: Not configured</span>
      </div>
    );
  }

  if (status === "unavailable") {
    return (
      <div
        className="flex items-center gap-2 border border-line bg-surface/80 px-3 py-1.5 backdrop-blur-sm"
        title={error ?? "Auth service unavailable"}
      >
        <span className="size-1.5 rounded-full bg-red-500" aria-hidden />
        <span className="font-mono text-[11px] text-muted">Auth: Unavailable</span>
      </div>
    );
  }

  if (status === "unauthenticated" || !user) {
    return (
      <a
        href="/auth/login"
        className="inline-flex items-center border border-line bg-surface px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-ink transition-colors hover:border-ink hover:bg-ink hover:text-white"
      >
        Sign in
      </a>
    );
  }

  const identity = user.name || user.email || "Authenticated user";

  return (
    <div className="flex items-center gap-3 border border-line bg-surface/90 px-3.5 py-1.5 backdrop-blur-sm">
      <span className="size-1.5 rounded-full bg-emerald-500" aria-hidden />
      <span className="max-w-[200px] truncate font-mono text-[11px] text-ink sm:max-w-[280px]">
        {identity}
      </span>
      <span className="text-line" aria-hidden>
        |
      </span>
      <button
        type="button"
        onClick={() => void signOut()}
        className="font-mono text-[11px] text-muted transition-colors hover:text-ink hover:underline"
      >
        Sign out
      </button>
    </div>
  );
}
