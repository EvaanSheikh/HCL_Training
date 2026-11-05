"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Sidebar, MobileBar } from "@/components/sidebar";
import { useSession } from "@/lib/session";
import { listReports } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { ReportItem } from "@/lib/types";

function downloadMarkdownFile(title: string, content: string, sessionId: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  const safeTitle = (title || "noha-report")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "-")
    .slice(0, 40);
  anchor.download = `${safeTitle}-${sessionId.slice(0, 8)}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function ReportsContent() {
  const session = useSession();
  const searchParams = useSearchParams();
  const preselectedSessionId = searchParams.get("session_id");

  const [reports, setReports] = useState<ReportItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");

  // Selected Report for Reader / Preview
  const [selectedReport, setSelectedReport] = useState<ReportItem | null>(null);
  const [copied, setCopied] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listReports();
      setReports(data);
      if (preselectedSessionId) {
        const match = data.find((r) => r.session_id === preselectedSessionId);
        if (match) setSelectedReport(match);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load reports.");
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

  async function handleCopy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  }

  const filteredReports = reports.filter((r) => {
    const term = search.toLowerCase();
    return (
      r.title.toLowerCase().includes(term) ||
      r.dataset_name.toLowerCase().includes(term) ||
      r.session_id.toLowerCase().includes(term) ||
      r.report_preview.toLowerCase().includes(term)
    );
  });

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar active="Reports" />
      <MobileBar active="Reports" />

      <main className="min-w-0 bg-[var(--paper)]">
        <div className="mx-auto w-full max-w-[1180px] px-5 py-10 sm:px-10 lg:px-14 lg:py-14">
          {/* Header */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between border-b border-line pb-8">
            <div>
              <p className="mono-label !text-accent">Workspace / Deliverables</p>
              <h1 className="mt-2 text-3xl font-medium tracking-tight sm:text-4xl text-ink">
                Reports
              </h1>
              <p className="mt-2 text-sm text-muted">
                Executive analysis summaries, statistical findings, and verifiable analytical reports.
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
                Sign in to view your executive analytical reports.
              </p>
              <a
                href="/auth/login"
                className="mt-4 inline-block bg-ink px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-white hover:bg-accent"
              >
                Sign in →
              </a>
            </div>
          )}

          {/* Controls: Search */}
          <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1">
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search reports by query, title, or dataset name..."
                className="w-full border border-line bg-surface px-3 py-2 font-mono text-[13px] text-ink placeholder:text-muted/60 focus:border-ink focus:outline-none"
              />
            </div>
            <div className="font-mono text-[12px] text-muted">
              {filteredReports.length} {filteredReports.length === 1 ? "report" : "reports"} found
            </div>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mt-6 border border-bad/30 bg-bad/5 p-4 text-[14px] text-bad">
              {error}
            </div>
          )}

          {/* Reports Grid / Cards */}
          <div className="mt-6">
            {loading ? (
              <div className="border border-line bg-surface p-12 text-center font-mono text-[13px] text-muted">
                Loading analytical reports...
              </div>
            ) : filteredReports.length === 0 ? (
              <div className="border border-line bg-surface p-12 text-center">
                <p className="font-serif text-lg font-light text-muted">
                  {reports.length === 0 ? "No reports generated yet." : "No reports match your search criteria."}
                </p>
                <p className="mt-1 text-[13px] text-muted">
                  {reports.length === 0
                    ? "Ask an analytical question in the Analysis workspace to produce an executive report."
                    : "Try adjusting your search terms."}
                </p>
                {reports.length === 0 && (
                  <Link
                    href="/"
                    className="mt-4 inline-block border border-line px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-ink transition-colors hover:border-ink"
                  >
                    Start Analysis
                  </Link>
                )}
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {filteredReports.map((report) => (
                  <div
                    key={report.session_id}
                    className="flex flex-col justify-between border border-line bg-surface p-5 transition-shadow hover:shadow-xs"
                  >
                    <div>
                      <div className="flex items-center justify-between text-muted text-[11px] font-mono">
                        <span className="truncate max-w-[130px]">{report.dataset_name}</span>
                        <div className="flex items-center gap-2">
                          <span
                            className={`inline-block border px-1.5 py-0.2 text-[9.5px] uppercase tracking-wider font-semibold ${
                              report.is_saved
                                ? "border-ok/30 bg-ok/10 text-ok"
                                : "border-warn/30 bg-warn/10 text-warn"
                            }`}
                          >
                            {report.is_saved ? "Saved" : "Ephemeral"}
                          </span>
                          <span>{formatDate(report.created_at)}</span>
                        </div>
                      </div>
                      <h2 className="mt-2 font-serif text-[17px] font-normal leading-snug text-ink line-clamp-2">
                        {report.title || report.user_query}
                      </h2>
                      <p className="mt-2 line-clamp-3 font-mono text-[11.5px] leading-relaxed text-muted">
                        {report.report_preview || "No preview available."}
                      </p>
                    </div>

                    <div className="mt-5 border-t border-line/60 pt-3">
                      <div className="flex items-center justify-between text-[11px] font-mono text-muted mb-3">
                        <span>{report.report_length.toLocaleString()} chars</span>
                        {report.chart_count > 0 && <span>{report.chart_count} chart(s)</span>}
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => setSelectedReport(report)}
                          className="border border-line bg-page px-3 py-1 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink"
                        >
                          Read Report
                        </button>
                        <button
                          type="button"
                          onClick={() => downloadMarkdownFile(report.title, report.final_report, report.session_id)}
                          className="border border-line px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider text-muted hover:border-ink hover:text-ink"
                          title="Download Markdown"
                        >
                          ↓ .md
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Report Reader / Preview Modal */}
      {selectedReport && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs"
          role="dialog"
          aria-modal="true"
        >
          <div className="relative flex max-h-[90vh] w-full max-w-4xl flex-col border border-line bg-page shadow-2xl">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-line p-5">
              <div>
                <div className="mono-label text-muted">Analytical Report Reader</div>
                <h2 className="mt-1 font-serif text-xl font-light text-ink">
                  {selectedReport.title || selectedReport.user_query}
                </h2>
                <div className="mt-1 flex flex-wrap items-center gap-3 font-mono text-[11px] text-muted">
                  <span>Dataset: {selectedReport.dataset_name}</span>
                  <span>·</span>
                  <span>Generated: {formatDate(selectedReport.created_at)}</span>
                  <span>·</span>
                  <span>Length: {selectedReport.report_length.toLocaleString()} chars</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedReport(null)}
                className="border border-line px-3 py-1 font-mono text-[12px] uppercase text-muted hover:border-ink hover:text-ink"
              >
                Close ✕
              </button>
            </div>

            {/* Modal Body / Report Display */}
            <div className="flex-1 overflow-y-auto p-6">
              <div className="border border-line bg-surface p-6">
                <pre className="whitespace-pre-wrap break-words font-mono text-[12.5px] leading-6 text-ink">
                  {selectedReport.final_report || "Report content is empty."}
                </pre>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between border-t border-line bg-[#fbfaf8] p-4">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleCopy(selectedReport.final_report)}
                  className="border border-line bg-surface px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink"
                >
                  {copied ? "Copied! ✓" : "Copy to Clipboard"}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    downloadMarkdownFile(
                      selectedReport.title,
                      selectedReport.final_report,
                      selectedReport.session_id
                    )
                  }
                  className="border border-line bg-surface px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-ink hover:border-ink"
                >
                  Download .md ↓
                </button>
              </div>

              <div className="flex items-center gap-3">
                <Link
                  href={`/trace?session_id=${encodeURIComponent(selectedReport.session_id)}`}
                  className="font-mono text-[11px] uppercase tracking-wider text-muted hover:text-ink hover:underline"
                >
                  View Trace →
                </Link>
                <button
                  type="button"
                  onClick={() => setSelectedReport(null)}
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

export default function ReportsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-page font-mono text-[13px] text-muted">
          Loading reports...
        </div>
      }
    >
      <ReportsContent />
    </Suspense>
  );
}