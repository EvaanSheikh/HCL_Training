"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Sidebar, MobileBar } from "@/components/sidebar";
import { useSession } from "@/lib/session";
import { listSessions, getSession } from "@/lib/api";
import { formatDate, primaryFinding, formatCompact } from "@/lib/format";
import type { SessionItem, AnalyzeResponse } from "@/lib/types";

export default function SessionsPage() {
  const session = useSession();
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Inspect Modal
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionDetail, setSessionDetail] = useState<AnalyzeResponse | null>(null);
  const [inspectLoading, setInspectLoading] = useState(false);
  const [inspectError, setInspectError] = useState<string | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const data = await listSessions();
      setSessions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sessions.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (session.status === "authenticated") {
      void loadData();
    } else if (session.status !== "loading") {
      setLoading(false);
    }
  }, [session.status]);

  async function handleInspect(sessionId: string) {
    setSelectedSessionId(sessionId);
    setInspectLoading(true);
    setInspectError(null);
    setSessionDetail(null);
    try {
      const detail = await getSession(sessionId);
      setSessionDetail(detail);
    } catch (err) {
      setInspectError(err instanceof Error ? err.message : "Failed to load session details.");
    } finally {
      setInspectLoading(false);
    }
  }

  // Filtered list
  const filteredSessions = sessions.filter((s) => {
    const queryMatch =
      s.user_query.toLowerCase().includes(search.toLowerCase()) ||
      s.dataset_name.toLowerCase().includes(search.toLowerCase()) ||
      s.session_id.toLowerCase().includes(search.toLowerCase());
    const statusMatch =
      statusFilter === "all" || s.status.toLowerCase() === statusFilter.toLowerCase();
    return queryMatch && statusMatch;
  });

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar active="Sessions" />
      <MobileBar active="Sessions" />

      <main className="min-w-0 bg-[var(--paper)]">
        <div className="mx-auto w-full max-w-[1180px] px-5 py-10 sm:px-10 lg:px-14 lg:py-14">
          {/* Header */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between border-b border-line pb-8">
            <div>
              <p className="mono-label !text-accent">Workspace / Execution History</p>
              <h1 className="mt-2 text-3xl font-medium tracking-tight sm:text-4xl text-ink">
                Sessions
              </h1>
              <p className="mt-2 text-sm text-muted">
                Audit trail of autonomous analysis sessions, queries executed, and runtime verification status.
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
              <Link
                href="/"
                className="inline-flex items-center gap-2 bg-ink px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-white hover:bg-accent"
              >
                + New Analysis
              </Link>
            </div>
          </div>

          {/* Auth Guard Banner */}
          {session.status === "unauthenticated" && (
            <div className="mt-8 border border-line bg-surface p-6">
              <p className="mono-label text-ink">Authentication Required</p>
              <p className="mt-1 text-sm text-muted">
                Sign in to view your historical analysis sessions.
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
                placeholder="Search by query, dataset name, or session ID..."
                className="w-full border border-line bg-surface px-3 py-2 font-mono text-[13px] text-ink placeholder:text-muted/60 focus:border-ink focus:outline-none"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="mono-label text-muted">Status:</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Filter sessions by status"
                className="border border-line bg-surface px-3 py-2 font-mono text-[12px] uppercase tracking-wider text-ink focus:border-ink focus:outline-none"
              >
                <option value="all">All Statuses</option>
                <option value="analyzed">Analyzed (Success)</option>
                <option value="failed">Failed</option>
              </select>
            </div>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mt-6 border border-bad/30 bg-bad/5 p-4 text-[14px] text-bad">
              {error}
            </div>
          )}

          {/* Sessions Table */}
          <div className="mt-6 border border-line bg-surface">
            {loading ? (
              <div className="p-8 text-center font-mono text-[13px] text-muted">
                Loading analysis sessions...
              </div>
            ) : filteredSessions.length === 0 ? (
              <div className="p-12 text-center">
                <p className="font-serif text-lg font-light text-muted">
                  {sessions.length === 0
                    ? "No analysis sessions found."
                    : "No sessions match your search criteria."}
                </p>
                <p className="mt-1 text-[13px] text-muted">
                  {sessions.length === 0
                    ? "Ask a question in the Analysis workspace to run your first session."
                    : "Try adjusting your search terms or filter."}
                </p>
                {sessions.length === 0 && (
                  <Link
                    href="/"
                    className="mt-4 inline-block border border-line px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-ink transition-colors hover:border-ink"
                  >
                    Go to Analysis
                  </Link>
                )}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left font-mono text-[12px]">
                  <thead>
                    <tr className="border-b border-line bg-[#fbfaf8] text-muted uppercase tracking-wider text-[11px]">
                      <th className="px-4 py-3">Session & Query</th>
                      <th className="px-4 py-3">Dataset</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Activity</th>
                      <th className="px-4 py-3">Validations</th>
                      <th className="px-4 py-3">Executed</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {filteredSessions.map((s) => (
                      <tr
                        key={s.session_id}
                        className="transition-colors hover:bg-[#f6f5f0]/60"
                      >
                        <td className="px-4 py-3.5 max-w-[320px]">
                          <div className="truncate font-sans text-[14px] font-normal text-ink">
                            {s.user_query || "(No query text recorded)"}
                          </div>
                          <div className="mt-0.5 truncate text-[11px] text-muted">
                            {s.session_id}
                          </div>
                        </td>
                        <td className="px-4 py-3.5">
                          <span className="font-mono text-[12px] text-ink">
                            {s.dataset_name || s.dataset_id}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap">
                          <span
                            className={`inline-block border px-2 py-0.5 text-[10px] uppercase tracking-wider font-semibold ${
                              s.status === "analyzed"
                                ? "border-ok/30 bg-ok/10 text-ok"
                                : "border-bad/30 bg-bad/10 text-bad"
                            }`}
                          >
                            {s.status}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap text-muted">
                          <span>{s.tool_calls_count} tools</span>
                          <span className="mx-1.5 opacity-40">·</span>
                          <span>{s.evidence_count} evidence</span>
                          {s.chart_count > 0 && (
                            <>
                              <span className="mx-1.5 opacity-40">·</span>
                              <span className="text-ink">{s.chart_count} chart</span>
                            </>
                          )}
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap">
                          {s.validation_count > 0 ? (
                            <span
                              className={`mono-label ${
                                s.all_validations_passed ? "!text-ok" : "!text-bad"
                              }`}
                            >
                              {s.all_validations_passed ? "PASSED" : "FAILED"} (
                              {s.validation_count})
                            </span>
                          ) : (
                            <span className="text-muted">None</span>
                          )}
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap text-muted text-[11px]">
                          {formatDate(s.created_at)}
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => void handleInspect(s.session_id)}
                              className="border border-line px-2.5 py-1 text-[11px] uppercase tracking-wider text-ink transition-colors hover:border-ink hover:bg-page"
                            >
                              Inspect
                            </button>
                            <Link
                              href={`/trace?session_id=${encodeURIComponent(s.session_id)}`}
                              className="border border-line px-2.5 py-1 text-[11px] uppercase tracking-wider text-muted transition-colors hover:border-ink hover:text-ink hover:bg-page"
                            >
                              Trace
                            </Link>
                            {s.has_report && (
                              <Link
                                href={`/reports?session_id=${encodeURIComponent(s.session_id)}`}
                                className="border border-line px-2.5 py-1 text-[11px] uppercase tracking-wider text-muted transition-colors hover:border-ink hover:text-ink hover:bg-page"
                              >
                                Report
                              </Link>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Inspect Session Modal */}
      {selectedSessionId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs"
          role="dialog"
          aria-modal="true"
        >
          <div className="relative flex max-h-[90vh] w-full max-w-4xl flex-col border border-line bg-page shadow-2xl">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-line p-5">
              <div>
                <div className="mono-label text-muted">Analysis Session Details</div>
                <h2 className="mt-1 font-serif text-xl font-light text-ink">
                  {sessions.find((s) => s.session_id === selectedSessionId)?.user_query ||
                    selectedSessionId}
                </h2>
                <p className="mt-0.5 font-mono text-[11px] text-muted">
                  ID: {selectedSessionId}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSelectedSessionId(null);
                  setSessionDetail(null);
                }}
                className="border border-line px-3 py-1 font-mono text-[12px] uppercase text-muted hover:border-ink hover:text-ink"
              >
                Close ✕
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {inspectLoading ? (
                <div className="py-12 text-center font-mono text-[13px] text-muted">
                  Loading session details and verification results...
                </div>
              ) : inspectError ? (
                <div className="border border-bad/30 bg-bad/5 p-4 text-[14px] text-bad">
                  {inspectError}
                </div>
              ) : sessionDetail ? (
                <>
                  {/* Primary Answer & Headline */}
                  {(() => {
                    const primary = primaryFinding(sessionDetail.findings, sessionDetail.user_query);
                    return (
                      <div className="border border-line bg-surface p-4">
                        <div className="mono-label text-muted">Analytical Finding</div>
                        {primary ? (
                          <div className="mt-2">
                            <div className="font-mono text-[11px] uppercase tracking-wider text-muted">
                              {primary.metric} · {primary.entity}
                            </div>
                            <div className="mt-1 font-mono text-3xl font-light text-ink">
                              {formatCompact(primary.value).figure}
                              {formatCompact(primary.value).suffix && (
                                <span className="text-xl ml-0.5 text-muted">
                                  {formatCompact(primary.value).suffix}
                                </span>
                              )}
                            </div>
                            {primary.message && (
                              <p className="mt-2 text-[14px] text-muted leading-relaxed">
                                {primary.message}
                              </p>
                            )}
                          </div>
                        ) : (
                          <div className="mt-2 text-[14px] leading-relaxed text-muted">
                            {sessionDetail.findings[0]?.message || "Statistical analysis completed."}
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {/* Findings */}
                  {sessionDetail.findings && sessionDetail.findings.length > 0 && (
                    <div className="space-y-3">
                      <div className="mono-label text-muted">Structured Findings</div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {sessionDetail.findings.map((finding, idx) => (
                          <div
                            key={idx}
                            className="border border-line bg-surface p-3 font-mono text-[12px]"
                          >
                            <div className="font-semibold text-ink">
                              {finding.metric || finding.type || `Finding #${idx + 1}`}
                            </div>
                            <div className="mt-1 text-muted leading-relaxed">
                              {finding.message || JSON.stringify(finding)}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Validations */}
                  {sessionDetail.validation_results &&
                    sessionDetail.validation_results.length > 0 && (
                      <div className="space-y-2">
                        <div className="mono-label text-muted">
                          Pipeline Validations ({sessionDetail.validation_results.length})
                        </div>
                        <div className="divide-y divide-line border border-line bg-surface font-mono text-[12px]">
                          {sessionDetail.validation_results.map((v, idx) => (
                            <div
                              key={idx}
                              className="flex items-center justify-between p-3"
                            >
                              <div className="flex items-center gap-3">
                                <span
                                  className={`inline-block border px-1.5 py-0.5 text-[10px] uppercase tracking-wider font-semibold ${
                                    v.passed
                                      ? "border-ok/30 bg-ok/10 text-ok"
                                      : "border-bad/30 bg-bad/10 text-bad"
                                  }`}
                                >
                                  {v.passed ? "PASS" : "FAIL"}
                                </span>
                                <span className="text-ink">{v.check}</span>
                              </div>
                              <span className="text-muted text-[11px]">
                                {v.message}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                  {/* Tool Calls Summary */}
                  {sessionDetail.tool_calls && sessionDetail.tool_calls.length > 0 && (
                    <div className="space-y-2">
                      <div className="mono-label text-muted">
                        Tool Execution Trace ({sessionDetail.tool_calls.length} calls)
                      </div>
                      <div className="max-h-48 overflow-y-auto border border-line bg-surface p-3 font-mono text-[11.5px] leading-relaxed">
                        {sessionDetail.tool_calls.map((tc, idx) => (
                          <div key={idx} className="border-b border-line/50 py-1.5 last:border-0">
                            <span className="text-muted mr-2">[{idx + 1}]</span>
                            <span className="font-semibold text-ink">{tc.action}</span>
                            <span className="ml-2 text-muted">
                              {JSON.stringify(tc.parameters || {})}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Report Excerpt */}
                  {sessionDetail.final_report && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="mono-label text-muted">Report Preview</div>
                        <Link
                          href={`/reports?session_id=${encodeURIComponent(selectedSessionId)}`}
                          className="font-mono text-[11px] uppercase tracking-wider text-ink hover:underline"
                        >
                          View Full Report →
                        </Link>
                      </div>
                      <pre className="max-h-48 overflow-auto whitespace-pre-wrap border border-line bg-surface p-3 font-mono text-[11.5px] leading-5 text-muted">
                        {sessionDetail.final_report}
                      </pre>
                    </div>
                  )}
                </>
              ) : null}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between border-t border-line bg-[#fbfaf8] p-4">
              <span className="font-mono text-[11px] text-muted">
                NOHA Autonomous Data Analyst
              </span>
              <div className="flex items-center gap-3">
                <Link
                  href={`/trace?session_id=${encodeURIComponent(selectedSessionId)}`}
                  className="border border-line bg-surface px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink"
                >
                  Inspect Full Trace
                </Link>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedSessionId(null);
                    setSessionDetail(null);
                  }}
                  className="border border-ink bg-ink px-4 py-1.5 font-mono text-[11px] uppercase tracking-wider text-page hover:opacity-90"
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}