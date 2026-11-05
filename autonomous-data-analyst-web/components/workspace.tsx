"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "motion/react";
import { analyze, ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { AnalyzeResponse, UploadResponse } from "@/lib/types";
import { DatasetSummary } from "./dataset-summary";
import { QueryPanel } from "./query-panel";
import { Result } from "./result";
import { RunStages, STAGES, type Stage } from "./run-stages";
import { UploadZone } from "./upload-zone";

type Run =
  | { kind: "idle" }
  | { kind: "running"; stage: Stage }
  | { kind: "done"; result: AnalyzeResponse }
  | { kind: "error"; stage: Stage; message: string; status?: number };

const STAGE_INTERVAL_MS = 2200;
const ease = [0.23, 1, 0.32, 1] as const;

export function Workspace() {
  const session = useSession();
  const [dataset, setDataset] = useState<UploadResponse | null>(null);
  const [query, setQuery] = useState("");
  const [run, setRun] = useState<Run>({ kind: "idle" });
  const abortRef = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    if (run.kind === "done") {
      resultRef.current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    }
  }, [run.kind, reduceMotion]);

  const running = run.kind === "running";
  const isAuthenticated = session.status === "authenticated";

  // Determine upload/query disabled reason based on session state
  const isActionDisabled = !isAuthenticated;
  let actionDisabledReason = "";
  if (session.status === "loading") {
    actionDisabledReason = "Checking session status...";
  } else if (session.status === "unconfigured") {
    actionDisabledReason = "Configure Auth0 in .env.local to enable upload and analysis.";
  } else if (session.status === "unavailable") {
    actionDisabledReason = "Authentication service is currently unavailable.";
  } else if (session.status === "unauthenticated") {
    actionDisabledReason = "Sign in required to upload datasets and run analysis.";
  }

  async function runAnalysis() {
    if (!dataset || query.trim() === "" || running) return;

    const controller = new AbortController();
    abortRef.current = controller;
    setRun({ kind: "running", stage: "planning" });

    // The backend replies once, so the stage advances on a timer and holds at
    // "validating" until the response arrives. It reflects the request, not backend events.
    const timer = window.setInterval(() => {
      setRun((current) => {
        if (current.kind !== "running") return current;
        const next = STAGES.indexOf(current.stage) + 1;
        return next <= STAGES.indexOf("validating") ? { kind: "running", stage: STAGES[next] } : current;
      });
    }, STAGE_INTERVAL_MS);

    try {
      // dataset_id is forwarded exactly as /upload returned it.
      const result = await analyze(query.trim(), dataset.dataset_id, controller.signal);
      setRun({ kind: "done", result });
    } catch (error) {
      if (error instanceof ApiError && error.kind === "aborted") return;
      setRun((current) => ({
        kind: "error",
        stage: current.kind === "running" ? current.stage : "planning",
        message: error instanceof Error ? error.message : "Analysis failed.",
        status: error instanceof ApiError ? error.status : undefined,
      }));
    } finally {
      window.clearInterval(timer);
    }
  }

  function replaceDataset() {
    abortRef.current?.abort();
    setDataset(null);
    setRun({ kind: "idle" });
  }

  const showStages = run.kind !== "idle";
  const stage: Stage = run.kind === "done" ? "complete" : run.kind === "idle" ? "planning" : run.stage;

  return (
    <MotionConfig reducedMotion="user">
      <div className="mx-auto w-full max-w-[1080px] px-5 py-10 sm:px-10 lg:px-14 lg:py-16">
        {/* Authentication Notice Banners */}
        {session.status === "unconfigured" && (
          <div className="mb-10 border border-line bg-surface p-5 sm:p-6" role="alert">
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <span className="size-2 rounded-full bg-amber-500" aria-hidden />
                <p className="mono-label text-ink">Auth0 Configuration Required</p>
              </div>
              <p className="text-sm leading-6 text-muted">
                Local development requires Auth0 environment variables in <code className="font-mono text-ink">.env.local</code> to authenticate requests.
                Upload and analysis endpoints are protected to ensure datasets and analyses remain securely isolated per user account.
              </p>
              {session.missing && session.missing.length > 0 && (
                <div className="mt-1 border-t border-line/60 pt-3">
                  <p className="font-mono text-[11px] uppercase tracking-wider text-muted">Missing in .env.local:</p>
                  <p className="mt-1 font-mono text-[12px] text-amber-800">
                    {session.missing.join(", ")}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {session.status === "unauthenticated" && (
          <div className="mb-10 border border-line bg-surface p-5 sm:p-6" role="alert">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="mono-label text-ink">Authentication Required</p>
                <p className="mt-1 text-sm leading-6 text-muted">
                  NOHA isolates datasets, execution traces, and private charts to authenticated accounts. Please sign in to upload datasets and run analysis.
                </p>
              </div>
              <a
                href="/auth/login"
                className="inline-flex shrink-0 items-center justify-center bg-ink px-5 py-2.5 font-mono text-[11px] uppercase tracking-wider text-white transition-colors hover:bg-accent"
              >
                Sign in →
              </a>
            </div>
          </div>
        )}

        {session.status === "unavailable" && (
          <div className="mb-10 border border-line bg-surface/60 p-5" role="alert">
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-red-500" aria-hidden />
              <p className="mono-label !text-red-700">Authentication Service Unavailable</p>
            </div>
            <p className="mt-2 text-sm text-muted">
              {session.error || "The authentication provider could not be reached. Please check your network and server configuration."}
            </p>
          </div>
        )}

        <motion.header
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease }}
        >
          <h1
            className={`font-medium leading-[0.98] tracking-[-0.04em] transition-[font-size] duration-300 ${
              dataset ? "text-[clamp(2rem,4vw,3rem)]" : "text-[clamp(2.75rem,7vw,5.5rem)]"
            }`}
          >
            Ask questions.
            <span className="block text-muted">Get answers.</span>
          </h1>
          {!dataset && (
            <p className="mt-6 max-w-xl text-lg leading-7 text-[#3b3b39]">
              Upload a dataset, ask a question in plain language, and let the analytical engine plan, execute, validate
              and document the work.
            </p>
          )}
        </motion.header>

        <div className="mt-12 space-y-12 lg:mt-14">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease, delay: 0.08 }}
          >
            <AnimatePresence mode="wait" initial={false}>
              {dataset ? (
                <DatasetSummary key={dataset.dataset_id} dataset={dataset} onReplace={replaceDataset} disabled={running} />
              ) : (
                <motion.div key="upload" exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
                  <p className="mono-label mb-3">Dataset</p>
                  <UploadZone
                    disabled={isActionDisabled}
                    disabledReason={actionDisabledReason}
                    onUploaded={(uploaded) => {
                      setDataset(uploaded);
                      setRun({ kind: "idle" });
                    }}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease, delay: 0.16 }}
          >
            <QueryPanel
              query={query}
              onQueryChange={setQuery}
              onRun={() => void runAnalysis()}
              running={running}
              hasDataset={dataset !== null}
              datasetId={dataset?.dataset_id}
              disabled={isActionDisabled}
              disabledReason={actionDisabledReason}
            />
          </motion.div>

          <AnimatePresence initial={false}>
            {showStages && (
              <motion.div
                key="stages"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25, ease }}
              >
                <RunStages stage={stage} failed={run.kind === "error"} />
                {run.kind === "error" && (
                  <div role="alert" className="mt-5 border-l-2 border-bad bg-bad/[0.04] p-4 text-[14px] leading-6 text-bad">
                    <p>{run.message}</p>
                    {run.status === 401 && (
                      <p className="mt-3">
                        <a
                          href="/auth/login"
                          className="inline-block border border-bad/30 bg-surface px-3 py-1 font-mono text-[11px] uppercase tracking-wider text-bad hover:bg-bad hover:text-white"
                        >
                          Sign in again →
                        </a>
                      </p>
                    )}
                    {run.status === 503 && (
                      <button
                        type="button"
                        onClick={() => void runAnalysis()}
                        className="mt-3 border border-bad/30 bg-surface px-3 py-1 font-mono text-[11px] uppercase tracking-wider text-bad hover:bg-bad hover:text-white"
                      >
                        Retry analysis ↻
                      </button>
                    )}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {run.kind === "done" && (
            <div ref={resultRef} className="scroll-mt-8 border-t border-ink pt-10">
              <Result result={run.result} />
            </div>
          )}
        </div>
      </div>
    </MotionConfig>
  );
}
