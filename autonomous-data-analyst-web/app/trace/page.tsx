"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Sidebar, MobileBar } from "@/components/sidebar";
import { useSession } from "@/lib/session";
import { listTraces } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { TraceItem, ToolCall, EvidenceRecord, PlanStep } from "@/lib/types";

function TraceContent() {
  const session = useSession();
  const searchParams = useSearchParams();
  const preselectedSessionId = searchParams.get("session_id");

  const [traces, setTraces] = useState<TraceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [filterFailureOnly, setFilterFailureOnly] = useState(false);

  // Selected Trace for deep inspection
  const [selectedTrace, setSelectedTrace] = useState<TraceItem | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listTraces();
      setTraces(data);
      if (preselectedSessionId) {
        const match = data.find((t) => t.session_id === preselectedSessionId);
        if (match) setSelectedTrace(match);
      } else if (data.length > 0) {
        setSelectedTrace((prev) => (prev ? prev : data[0]));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load execution traces.");
    } finally {
      setLoading(false);
    }
  }, [preselectedSessionId]);

  useEffect(() => {
    if (session.status === "authenticated") {
      void loadData();
    } else if (session.status !== "loading") {
      setLoading(false);
    }
  }, [session.status, loadData]);

  const filteredTraces = traces.filter((t) => {
    const term = search.toLowerCase();
    const matchesSearch =
      t.user_query.toLowerCase().includes(term) ||
      t.dataset_name.toLowerCase().includes(term) ||
      t.session_id.toLowerCase().includes(term) ||
      t.tool_calls.some((tc) => tc.action.toLowerCase().includes(term));
    const matchesFailure = !filterFailureOnly || t.has_failures || t.status === "failed";
    return matchesSearch && matchesFailure;
  });

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar active="Trace" />
      <MobileBar active="Trace" />

      <main className="min-w-0 bg-[var(--paper)]">
        <div className="mx-auto w-full max-w-[1180px] px-5 py-10 sm:px-10 lg:px-14 lg:py-14">
          {/* Header */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between border-b border-line pb-8">
            <div>
              <p className="mono-label !text-accent">Workspace / Observability</p>
              <h1 className="mt-2 text-3xl font-medium tracking-tight sm:text-4xl text-ink">
                Execution Trace
              </h1>
              <p className="mt-2 text-sm text-muted">
                Step-by-step audit of agent reasoning plans, dispatched tools, gathered evidence, and runtime anomalies.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => void loadData()}
                disabled={loading}
                className="border border-line bg-surface px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-muted transition-colors hover:border-ink hover:text-ink disabled:opacity-50"
              >
                {loading ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>

          {/* Auth Guard Banner */}
          {session.status === "unauthenticated" && (
            <div className="mt-8 border border-line bg-surface p-6">
              <p className="mono-label text-ink">Authentication Required</p>
              <p className="mt-1 text-sm text-muted">
                Sign in to view execution traces and runtime step audits.
              </p>
              <a
                href="/auth/login"
                className="mt-4 inline-block bg-ink px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-white hover:bg-accent"
              >
                Sign in →
              </a>
            </div>
          )}

          {/* Controls: Search and Filters */}
          <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1">
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search traces by query, dataset, tool name, or session ID..."
                className="w-full border border-line bg-surface px-3 py-2 font-mono text-[13px] text-ink placeholder:text-muted/60 focus:border-ink focus:outline-none"
              />
            </div>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer font-mono text-[12px] text-muted select-none">
                <input
                  type="checkbox"
                  checked={filterFailureOnly}
                  onChange={(e) => setFilterFailureOnly(e.target.checked)}
                  className="rounded-none border-line accent-ink"
                />
                Show Failures Only
              </label>
              <div className="font-mono text-[12px] text-muted">
                {filteredTraces.length} trace(s)
              </div>
            </div>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mt-6 border border-bad/30 bg-bad/5 p-4 text-[14px] text-bad">
              {error}
            </div>
          )}

          {/* Main Layout: Master-Detail Timeline Split */}
          <div className="mt-6">
            {loading ? (
              <div className="border border-line bg-surface p-12 text-center font-mono text-[13px] text-muted">
                Loading execution traces...
              </div>
            ) : filteredTraces.length === 0 ? (
              <div className="border border-line bg-surface p-12 text-center">
                <p className="font-serif text-lg font-light text-muted">
                  {traces.length === 0
                    ? "No execution traces recorded yet."
                    : "No traces match your filter criteria."}
                </p>
                <p className="mt-1 text-[13px] text-muted">
                  {traces.length === 0
                    ? "Execute a query in the Analysis workspace to record an execution trace."
                    : "Try clearing your search terms or toggling the failure filter."}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                {/* Left Column: Trace List (4 cols) */}
                <div className="lg:col-span-4 border border-line bg-surface">
                  <div className="border-b border-line bg-[#fbfaf8] px-4 py-3 font-mono text-[11px] uppercase tracking-wider text-muted">
                    Execution Traces ({filteredTraces.length})
                  </div>
                  <div className="max-h-[700px] overflow-y-auto divide-y divide-line">
                    {filteredTraces.map((t) => {
                      const isSelected = selectedTrace?.session_id === t.session_id;
                      return (
                        <button
                          key={t.session_id}
                          type="button"
                          onClick={() => setSelectedTrace(t)}
                          className={`w-full text-left p-4 transition-colors ${
                            isSelected
                              ? "bg-page border-l-2 border-l-ink"
                              : "hover:bg-[#f6f5f0]/60"
                          }`}
                        >
                          <div className="flex items-center justify-between font-mono text-[11px]">
                            <span
                              className={`border px-1.5 py-0.2 text-[9.5px] uppercase tracking-wider font-semibold ${
                                t.status === "analyzed"
                                  ? "border-ok/30 bg-ok/10 text-ok"
                                  : "border-bad/30 bg-bad/10 text-bad"
                              }`}
                            >
                              {t.status}
                            </span>
                            <span className="text-muted">{formatDate(t.created_at)}</span>
                          </div>
                          <div className="mt-1.5 font-serif text-[14px] text-ink line-clamp-2 leading-snug">
                            {t.user_query || "(No query text)"}
                          </div>
                          <div className="mt-2 flex items-center gap-3 font-mono text-[11px] text-muted">
                            <span className="truncate max-w-[120px]">{t.dataset_name}</span>
                            <span>·</span>
                            <span>{t.tool_calls.length} tools</span>
                            <span>·</span>
                            <span>{t.evidence.length} evidence</span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Right Column: Deep Trace Timeline (8 cols) */}
                <div className="lg:col-span-8 border border-line bg-surface">
                  {selectedTrace ? (
                    <div>
                      {/* Trace Header */}
                      <div className="border-b border-line p-5">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                          <div className="mono-label text-muted">Trace Inspector</div>
                          <div className="flex items-center gap-3 font-mono text-[11px]">
                            <Link
                              href={`/sessions?session_id=${encodeURIComponent(selectedTrace.session_id)}`}
                              className="text-ink hover:underline"
                            >
                              View Session →
                            </Link>
                            <span className="text-line">|</span>
                            <Link
                              href={`/reports?session_id=${encodeURIComponent(selectedTrace.session_id)}`}
                              className="text-ink hover:underline"
                            >
                              View Report →
                            </Link>
                          </div>
                        </div>
                        <h2 className="mt-2 font-serif text-xl font-light text-ink">
                          {selectedTrace.user_query}
                        </h2>
                        <div className="mt-2 flex flex-wrap items-center gap-4 font-mono text-[11.5px] text-muted">
                          <span>Session: {selectedTrace.session_id}</span>
                          <span>·</span>
                          <span>Dataset: {selectedTrace.dataset_name}</span>
                          <span>·</span>
                          <span>Timestamp: {formatDate(selectedTrace.created_at)}</span>
                        </div>
                      </div>

                      {/* Timeline Sections */}
                      <div className="p-6 space-y-8 max-h-[640px] overflow-y-auto">
                        {/* Errors (if any) */}
                        {selectedTrace.errors && selectedTrace.errors.length > 0 && (
                          <div className="border border-bad/30 bg-bad/5 p-4">
                            <div className="mono-label !text-bad mb-2">Errors Encountered</div>
                            <div className="space-y-1 font-mono text-[12px] text-bad">
                              {selectedTrace.errors.map((err, idx) => (
                                <div key={idx} className="leading-relaxed">
                                  • {typeof err === "string" ? err : JSON.stringify(err)}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* 1. Planning Stage */}
                        <div>
                          <div className="flex items-center justify-between border-b border-line pb-2 mb-4">
                            <div className="mono-label text-ink">
                              Stage 1: Analytical Execution Plan ({selectedTrace.plan_steps?.length || 0} steps)
                            </div>
                            <span className="font-mono text-[11px] text-muted">Planning</span>
                          </div>

                          {!selectedTrace.plan_steps || selectedTrace.plan_steps.length === 0 ? (
                            <p className="font-mono text-[12px] text-muted italic">
                              No explicit plan steps recorded in this session.
                            </p>
                          ) : (
                            <div className="space-y-2">
                              {selectedTrace.plan_steps.map((step: PlanStep, idx: number) => (
                                <div
                                  key={idx}
                                  className="flex items-start gap-3 border border-line bg-page p-3 font-mono text-[12px]"
                                >
                                  <span className="mono-label text-muted">
                                    {String(step.step ?? idx + 1).padStart(2, "0")}
                                  </span>
                                  <div className="flex-1">
                                    <div className="font-medium text-ink">
                                      {step.action}
                                    </div>
                                    {step.parameters && Object.keys(step.parameters).length > 0 && (
                                      <div className="mt-1 text-[11px] text-muted truncate">
                                        Params: {JSON.stringify(step.parameters)}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* 2. Tool Execution Stage */}
                        <div>
                          <div className="flex items-center justify-between border-b border-line pb-2 mb-4">
                            <div className="mono-label text-ink">
                              Stage 2: Tool Dispatch & Execution ({selectedTrace.tool_calls?.length || 0} calls)
                            </div>
                            <span className="font-mono text-[11px] text-muted">Execution</span>
                          </div>

                          {!selectedTrace.tool_calls || selectedTrace.tool_calls.length === 0 ? (
                            <p className="font-mono text-[12px] text-muted italic">
                              No tool calls dispatched.
                            </p>
                          ) : (
                            <div className="space-y-3">
                              {selectedTrace.tool_calls.map((call: ToolCall, idx: number) => {
                                const hasParams = call.parameters && Object.keys(call.parameters).length > 0;
                                return (
                                  <div
                                    key={idx}
                                    className="border border-line bg-page p-4 font-mono text-[12px]"
                                  >
                                    <div className="flex items-center justify-between">
                                      <div className="flex items-center gap-2">
                                        <span className="mono-label text-muted">
                                          #{idx + 1}
                                        </span>
                                        <span className="font-semibold text-ink text-[13px]">
                                          {call.action}
                                        </span>
                                      </div>
                                      <span className="mono-label !text-ok">Executed</span>
                                    </div>

                                    {hasParams && (
                                      <div className="mt-2.5">
                                        <div className="text-[10px] uppercase tracking-wider text-muted mb-1">
                                          Arguments:
                                        </div>
                                        <pre className="max-h-36 overflow-auto border border-line/60 bg-surface p-2.5 text-[11px] leading-relaxed text-ink">
                                          {JSON.stringify(call.parameters, null, 2)}
                                        </pre>
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>

                        {/* 3. Evidence Collection Stage */}
                        <div>
                          <div className="flex items-center justify-between border-b border-line pb-2 mb-4">
                            <div className="mono-label text-ink">
                              Stage 3: Evidence & Observation ({selectedTrace.evidence?.length || 0} records)
                            </div>
                            <span className="font-mono text-[11px] text-muted">Observation</span>
                          </div>

                          {!selectedTrace.evidence || selectedTrace.evidence.length === 0 ? (
                            <p className="font-mono text-[12px] text-muted italic">
                              No evidence records captured.
                            </p>
                          ) : (
                            <div className="space-y-3">
                              {selectedTrace.evidence.map((ev: EvidenceRecord, idx: number) => (
                                <div
                                  key={idx}
                                  className="border border-line bg-page p-4 font-mono text-[12px]"
                                >
                                  <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                      <span className="mono-label text-muted">
                                        EV-{idx + 1}
                                      </span>
                                      <span className="font-medium text-ink">
                                        {ev.operation}
                                      </span>
                                    </div>
                                    <span className="text-[10px] text-muted">
                                      {ev.timestamp ? formatDate(ev.timestamp) : "Recorded"}
                                    </span>
                                  </div>

                                  {ev.columns && ev.columns.length > 0 && (
                                    <div className="mt-1 text-[11px] text-muted">
                                      Columns: {ev.columns.join(", ")}
                                    </div>
                                  )}

                                  {ev.parameters && Object.keys(ev.parameters).length > 0 && (
                                    <div className="mt-2 text-[11px] text-muted truncate">
                                      Parameters: {JSON.stringify(ev.parameters)}
                                    </div>
                                  )}

                                  {ev.result !== undefined && (
                                    <div className="mt-2.5">
                                      <div className="text-[10px] uppercase tracking-wider text-muted mb-1">
                                        Observed Result:
                                      </div>
                                      <pre className="max-h-36 overflow-auto border border-line/60 bg-surface p-2 text-[11px] text-ink">
                                        {typeof ev.result === "string"
                                          ? ev.result
                                          : JSON.stringify(ev.result, null, 2)}
                                      </pre>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="p-12 text-center font-mono text-[13px] text-muted">
                      Select an execution trace from the left panel to inspect details.
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default function TracePage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-page font-mono text-[13px] text-muted">
          Loading traces...
        </div>
      }
    >
      <TraceContent />
    </Suspense>
  );
}