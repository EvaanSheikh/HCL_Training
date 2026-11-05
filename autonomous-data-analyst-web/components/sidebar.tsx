"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiStatus } from "./api-status";

const WORKSPACE = ["Analysis", "Datasets", "Sessions", "Reports"] as const;
const SYSTEM = ["Trace", "Evaluation"] as const;

const ROUTE_MAP: Record<string, string> = {
  Analysis: "/",
  Datasets: "/datasets",
  Sessions: "/sessions",
  Reports: "/reports",
  Trace: "/trace",
  Evaluation: "/evaluation",
};

function NavGroup({ label, items, active }: { label: string; items: readonly string[]; active?: string }) {
  return (
    <div>
      <p className="mono-label !text-white/40">{label}</p>
      <ul className="mt-3 space-y-px">
        {items.map((item) => {
          const href = ROUTE_MAP[item] ?? "/";
          const isCurrent = item === active;
          return (
            <li key={item}>
              <Link
                href={href}
                aria-current={isCurrent ? "page" : undefined}
                className={`block border-l py-1.5 pl-3 text-[15px] transition-colors ${
                  isCurrent
                    ? "border-white font-medium text-white"
                    : "border-transparent text-white/50 hover:border-white/40 hover:text-white"
                }`}
              >
                {item}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function Sidebar({ active = "Analysis" }: { active?: string }) {
  return (
    <aside className="sticky top-0 hidden h-dvh flex-col justify-between bg-ink px-7 py-8 text-white lg:flex">
      <div className="space-y-12">
        <div>
          <Link href="/" className="inline-block text-[28px] font-semibold leading-none tracking-[0.04em] text-white">
            NOHA
          </Link>
          <p className="mono-label mt-3 !text-white/50">Autonomous Data Analyst</p>
        </div>
        <nav aria-label="Primary" className="space-y-9">
          <NavGroup label="Workspace" items={WORKSPACE} active={active} />
          <NavGroup label="System" items={SYSTEM} active={active} />
        </nav>
      </div>
      <ApiStatus />
    </aside>
  );
}

export function MobileBar({ active = "Analysis" }: { active?: string }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <header className="flex items-center justify-between bg-ink px-5 py-4 text-white lg:hidden">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setOpen(!open)}
            aria-label="Toggle navigation menu"
            className="flex h-8 w-8 items-center justify-center rounded border border-white/20 text-white/80 hover:text-white"
          >
            <span className="text-sm">☰</span>
          </button>
          <Link href="/" className="text-lg font-semibold tracking-[0.04em] text-white">
            NOHA
          </Link>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] uppercase tracking-wider text-white/60">{active}</span>
          <ApiStatus />
        </div>
      </header>
      {open && (
        <div className="border-b border-white/10 bg-ink px-6 py-4 text-white lg:hidden">
          <nav aria-label="Mobile Primary" className="space-y-6">
            <NavGroup label="Workspace" items={WORKSPACE} active={active} />
            <NavGroup label="System" items={SYSTEM} active={active} />
          </nav>
        </div>
      )}
    </>
  );
}
