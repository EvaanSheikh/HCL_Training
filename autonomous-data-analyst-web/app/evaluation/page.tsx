"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Sidebar, MobileBar } from "@/components/sidebar";
import { useSession } from "@/lib/session";
import { getEvaluations, runBenchmarkEvaluation } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type {
  EvaluationResponse,
  BenchmarkRun,
  PipelineValidationSummary,
  AvailableBenchmark,
} from "@/lib/types";

export default function EvaluationPage() {
  const session = useSession();
  const [data, setData] = useState<EvaluationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Tab State: "validations" | "benchmarks"
  const [activeTab, setActiveTab] = useState<"benchmarks" | "validations">("benchmarks");

  // Benchmark Execution State
  const [selectedBenchmarkId, setSelectedBenchmarkId] = useState<string>("stress_sales_500k");
  const [runningBenchmark, setRunningBenchmark] = useState(false);
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null);
  const [latestRunResult, setLatestRunResult] = useState<BenchmarkRun | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getEvaluations();
      setData(res);
      if (res.benchmark_runs && res.benchmark_runs.length > 0) {
        setLatestRunResult((prev) => (prev ? prev : res.benchmark_runs[0]));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load evaluation data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (session.status === "authenticated") {
      void loadData();
    } else if (session.status !== "loading") {
      setLoading(false);
    }
  }, [session.status, loadData]);

  async function handleRunBenchmark() {
    setRunningBenchmark(true);
    setBenchmarkError(null);
    try {
      const result = await runBenchmarkEvaluation(selectedBenchmarkId);
      setLatestRunResult(result);
      // Refresh list to include new run
      const res = await getEvaluations();
      setData(res);
    } catch (err) {
      setBenchmarkError(err instanceof Error ? err.message : "Benchmark execution failed.");
    } finally {
      setRunningBenchmark(false);
    }
  }

  const pipelineValidations: PipelineValidationSummary[] = data?.pipeline_validations || [];
  const benchmarkRuns: BenchmarkRun[] = data?.benchmark_runs || [];
  const availableBenchmarks: AvailableBenchmark[] = data?.available_benchmarks || [];

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar active="Evaluation" />
      <MobileBar active="Evaluation" />

      <main className="min-w-0 bg-[var(--paper)]">
        <div className="mx-auto w-full max-w-[1180px] px-5 py-10 sm:px-10 lg:px-14 lg:py-14">
          {/* Header */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between border-b border-line pb-8">
            <div>
              <p className="mono-label !text-accent">Workspace / Quality & Verification</p>
              <h1 className="mt-2 text-3xl font-medium tracking-tight sm:text-4xl text-ink">
                Evaluation & Benchmarks
              </h1>
              <p className="mt-2 text-sm text-muted">
                Deterministic mathematical accuracy benchmarks and automated pipeline integrity verification.
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
                Sign in to view pipeline validations and execute ground-truth accuracy benchmarks.
              </p>
              <a
                href="/auth/login"
                className="mt-4 inline-block bg-ink px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-white hover:bg-accent"
              >
                Sign in →
              </a>
            </div>
          )}

          {/* Tab Navigation */}
          <div className="mt-6 flex border-b border-line font-mono text-[12px] uppercase tracking-wider">
            <button
              type="button"
              onClick={() => setActiveTab("benchmarks")}
              className={`border-b-2 px-5 py-3 transition-colors ${
                activeTab === "benchmarks"
                  ? "border-ink text-ink font-semibold"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              Deterministic Accuracy Benchmarks ({benchmarkRuns.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("validations")}
              className={`border-b-2 px-5 py-3 transition-colors ${
                activeTab === "validations"
                  ? "border-ink text-ink font-semibold"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              Session Pipeline Validations ({pipelineValidations.length})
            </button>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mt-6 border border-bad/30 bg-bad/5 p-4 text-[14px] text-bad">
              {error}
            </div>
          )}

          {/* TAB 1: Deterministic Accuracy Benchmarks */}
          {activeTab === "benchmarks" && (
            <div className="mt-6 space-y-8">
              {/* Benchmark Launcher Card */}
              <div className="border border-line bg-surface p-6">
                <div className="mono-label text-muted">Execute Verification Suite</div>
                <h2 className="mt-1 font-serif text-2xl font-light text-ink">
                  Ground-Truth Accuracy Verification
                </h2>
                <p className="mt-1 text-[13.5px] text-muted leading-relaxed">
                  Executes exact mathematical computations across actual dataset files to verify statistical calculations, row counts, aggregations, and edge cases against verified ground truth.
                </p>

                <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-end">
                  <div className="flex-1">
                    <label className="mono-label text-muted block mb-1.5">
                      Select Benchmark Target
                    </label>
                    <select
                      value={selectedBenchmarkId}
                      onChange={(e) => setSelectedBenchmarkId(e.target.value)}
                      aria-label="Select Benchmark Target"
                      className="w-full border border-line bg-page px-3 py-2 font-mono text-[13px] text-ink focus:border-ink focus:outline-none"
                    >
                      {availableBenchmarks.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name} — {b.description} ({b.expected_assertions} assertions)
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleRunBenchmark()}
                    disabled={runningBenchmark}
                    className="border border-ink bg-ink px-6 py-2.5 font-mono text-[12px] uppercase tracking-wider text-page hover:opacity-90 disabled:opacity-50"
                  >
                    {runningBenchmark ? "Executing Assertions..." : "Run Benchmark Now ❯"}
                  </button>
                </div>

                {benchmarkError && (
                  <div className="mt-4 border border-bad/30 bg-bad/5 p-3 text-[13px] text-bad font-mono">
                    {benchmarkError}
                  </div>
                )}
              </div>

              {/* Latest Run Scorecard */}
              {latestRunResult && (
                <div className="border border-line bg-surface">
                  <div className="flex flex-col gap-2 border-b border-line bg-[#fbfaf8] p-5 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="mono-label text-muted">Latest Benchmark Scorecard</div>
                      <h2 className="mt-1 font-serif text-xl font-normal text-ink">
                        {latestRunResult.benchmark_name}
                      </h2>
                      <div className="mt-1 font-mono text-[11px] text-muted">
                        Dataset: {latestRunResult.details?.dataset_name || latestRunResult.dataset_id} · Run ID: {latestRunResult.run_id}
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <div className="mono-label text-muted">Execution Time</div>
                        <div className="font-mono text-[15px] font-semibold text-ink">
                          {latestRunResult.execution_time_ms} ms
                        </div>
                      </div>
                      <div className="text-right pl-4 border-l border-line">
                        <div className="mono-label text-muted">Accuracy Score</div>
                        <div className="font-mono text-2xl font-bold text-ok">
                          {latestRunResult.accuracy_score}%
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Assertion Breakdown Table */}
                  <div className="overflow-x-auto">
                    <table className="w-full text-left font-mono text-[12px]">
                      <thead>
                        <tr className="border-b border-line bg-page text-muted uppercase tracking-wider text-[11px]">
                          <th className="px-4 py-3">Status</th>
                          <th className="px-4 py-3">Assertion Target</th>
                          <th className="px-4 py-3">Category</th>
                          <th className="px-4 py-3">Expected Ground Truth</th>
                          <th className="px-4 py-3">Actual Value</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line">
                        {latestRunResult.details?.assertions?.map((a, idx) => (
                          <tr key={idx} className="hover:bg-[#f6f5f0]/60">
                            <td className="px-4 py-3 whitespace-nowrap">
                              <span
                                className={`inline-block border px-2 py-0.5 text-[10px] uppercase tracking-wider font-semibold ${
                                  a.passed
                                    ? "border-ok/30 bg-ok/10 text-ok"
                                    : "border-bad/30 bg-bad/10 text-bad"
                                }`}
                              >
                                {a.passed ? "PASS" : "FAIL"}
                              </span>
                            </td>
                            <td className="px-4 py-3 font-medium text-ink">
                              {a.name}
                            </td>
                            <td className="px-4 py-3 text-muted text-[11px]">
                              {a.category}
                            </td>
                            <td className="px-4 py-3 text-ink font-semibold">
                              {a.expected}
                            </td>
                            <td className="px-4 py-3 text-muted">
                              {a.actual}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {latestRunResult.details?.summary && (
                    <div className="border-t border-line bg-page p-4 font-mono text-[11.5px] text-muted">
                      {latestRunResult.details.summary}
                    </div>
                  )}
                </div>
              )}

              {/* Historical Benchmark Runs Table */}
              <div className="border border-line bg-surface">
                <div className="border-b border-line bg-[#fbfaf8] px-5 py-3 font-mono text-[11px] uppercase tracking-wider text-muted">
                  Historical Benchmark Runs ({benchmarkRuns.length})
                </div>
                {benchmarkRuns.length === 0 ? (
                  <div className="p-8 text-center font-mono text-[13px] text-muted">
                    No benchmark runs recorded. Click &quot;Run Benchmark Now&quot; above to generate your first verified run.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left font-mono text-[12px]">
                      <thead>
                        <tr className="border-b border-line bg-page text-muted uppercase tracking-wider text-[11px]">
                          <th className="px-4 py-3">Benchmark Name</th>
                          <th className="px-4 py-3">Status</th>
                          <th className="px-4 py-3">Score</th>
                          <th className="px-4 py-3">Assertions</th>
                          <th className="px-4 py-3">Duration</th>
                          <th className="px-4 py-3">Executed</th>
                          <th className="px-4 py-3 text-right">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line">
                        {benchmarkRuns.map((r) => (
                          <tr key={r.run_id} className="hover:bg-[#f6f5f0]/60">
                            <td className="px-4 py-3 font-medium text-ink">
                              {r.benchmark_name}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              <span
                                className={`inline-block border px-1.5 py-0.5 text-[9.5px] uppercase tracking-wider font-semibold ${
                                  r.status === "passed"
                                    ? "border-ok/30 bg-ok/10 text-ok"
                                    : "border-bad/30 bg-bad/10 text-bad"
                                }`}
                              >
                                {r.status}
                              </span>
                            </td>
                            <td className="px-4 py-3 font-bold text-ok">
                              {r.accuracy_score}%
                            </td>
                            <td className="px-4 py-3 text-muted">
                              {r.assertions_passed} / {r.assertions_total} passed
                            </td>
                            <td className="px-4 py-3 text-muted">
                              {r.execution_time_ms} ms
                            </td>
                            <td className="px-4 py-3 text-muted text-[11px]">
                              {formatDate(r.created_at)}
                            </td>
                            <td className="px-4 py-3 text-right">
                              <button
                                type="button"
                                onClick={() => setLatestRunResult(r)}
                                className="border border-line px-2.5 py-1 text-[11px] uppercase tracking-wider text-ink hover:border-ink"
                              >
                                View Scorecard
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: Session Pipeline Validations */}
          {activeTab === "validations" && (
            <div className="mt-6 border border-line bg-surface">
              <div className="border-b border-line bg-[#fbfaf8] px-5 py-3 font-mono text-[11px] uppercase tracking-wider text-muted">
                Runtime Session Validations ({pipelineValidations.length})
              </div>
              {pipelineValidations.length === 0 ? (
                <div className="p-8 text-center font-mono text-[13px] text-muted">
                  No session validations recorded yet. Ask a question in the Analysis workspace to record validations.
                </div>
              ) : (
                <div className="divide-y divide-line">
                  {pipelineValidations.map((v) => (
                    <div key={v.session_id} className="p-5 hover:bg-[#f6f5f0]/40 transition-colors">
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-baseline sm:justify-between">
                        <div>
                          <div className="flex items-center gap-3">
                            <span
                              className={`inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider font-semibold ${
                                v.all_passed
                                  ? "border-ok/30 bg-ok/10 text-ok"
                                  : "border-bad/30 bg-bad/10 text-bad"
                              }`}
                            >
                              {v.all_passed ? "ALL PASSED" : "FAILED CHECKS"}
                            </span>
                            <span className="font-serif text-[16px] text-ink font-normal">
                              {v.user_query}
                            </span>
                          </div>
                          <div className="mt-1 flex items-center gap-3 font-mono text-[11px] text-muted">
                            <span>Dataset: {v.dataset_name}</span>
                            <span>·</span>
                            <span>Session: {v.session_id}</span>
                            <span>·</span>
                            <span>{formatDate(v.created_at)}</span>
                          </div>
                        </div>

                        <div className="font-mono text-[12px] text-muted">
                          {v.passed_count} of {v.total_count} checks passed
                        </div>
                      </div>

                      {/* Checks List */}
                      {v.checks && v.checks.length > 0 && (
                        <div className="mt-4 divide-y divide-line/60 border border-line/60 bg-page font-mono text-[11.5px]">
                          {v.checks.map((chk, idx) => (
                            <div
                              key={idx}
                              className="flex items-center justify-between p-2.5"
                            >
                              <div className="flex items-center gap-2.5">
                                <span
                                  className={`font-semibold ${
                                    chk.passed ? "text-ok" : "text-bad"
                                  }`}
                                >
                                  {chk.passed ? "✓ PASS" : "✗ FAIL"}
                                </span>
                                <span className="text-ink">{chk.check}</span>
                              </div>
                              <span className="text-muted text-[11px]">
                                {chk.message}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}

                      <div className="mt-3 flex items-center gap-4 font-mono text-[11px]">
                        <Link
                          href={`/trace?session_id=${encodeURIComponent(v.session_id)}`}
                          className="text-ink hover:underline"
                        >
                          View Trace →
                        </Link>
                        <Link
                          href={`/sessions?session_id=${encodeURIComponent(v.session_id)}`}
                          className="text-muted hover:text-ink hover:underline"
                        >
                          View Session →
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}