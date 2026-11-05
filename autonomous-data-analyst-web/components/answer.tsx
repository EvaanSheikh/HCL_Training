"use client";

import { motion } from "motion/react";
import { formatCompact, formatExact, humanize, pluralize, type PrimaryFinding } from "@/lib/format";
import type { AnalyzeResponse } from "@/lib/types";

const ease = [0.23, 1, 0.32, 1] as const;

export function Answer({ result, primary }: { result: AnalyzeResponse; primary: PrimaryFinding | null }) {
  const failed = result.status === "failed";
  const messages = result.findings.map((f) => f.message).filter((m): m is string => Boolean(m));

  return (
    <section aria-label="Answer">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
        <p className="mono-label">Answer</p>
        <p className={`mono-label ${failed ? "!text-bad" : "!text-ok"}`}>{result.status}</p>
        <p className="mono-label break-all">Session {result.session_id}</p>
      </div>

      <p className="mt-4 max-w-3xl text-lg leading-7 text-muted">{result.user_query}</p>

      {primary ? <PrimaryAnswer primary={primary} /> : <NoPrimary messages={messages} failed={failed} />}

      {result.errors.length > 0 && (
        <ul className="mt-10 space-y-2" aria-label="Backend errors">
          {result.errors.map((error, index) => (
            <li
              key={`${error.type ?? "error"}-${index}`}
              className={`border-l-2 py-1 pl-3 text-[14px] leading-6 ${failed ? "border-bad text-bad" : "border-warn text-warn"}`}
            >
              <span className="mono-label mr-3 !text-current">{error.type ?? "error"}</span>
              {error.message}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PrimaryAnswer({ primary }: { primary: PrimaryFinding }) {
  const compact = formatCompact(primary.value);
  const low = primary.lowValue !== undefined ? formatCompact(primary.lowValue) : null;
  const metric = primary.metric.replace(/[_-]+/g, " ");

  return (
    <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_260px] lg:gap-16">
      <div>
        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease }}
          className="break-words text-[clamp(2.25rem,5vw,4rem)] font-medium leading-[1.04] tracking-[-0.03em]"
        >
          {primary.entity}
        </motion.p>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease, delay: 0.1 }}
          className="mt-2 text-[clamp(4.25rem,12vw,9rem)] font-medium leading-[0.95] tracking-[-0.05em] tabular-nums"
          aria-label={`${formatExact(primary.value)} ${metric}`}
        >
          {compact.figure}
          {compact.suffix && <span className="ml-[0.04em] text-muted">{compact.suffix}</span>}
        </motion.p>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.35, delay: 0.25 }}
        >
          {primary.entityKey.toLowerCase() === "dataset" ? (
            <>
              <p className="mt-6 text-[17px] font-medium">
                {humanize(metric)} across dataset
              </p>
              <p className="mt-1 max-w-xl text-xl leading-8 text-[#3b3b39]">
                Calculated across {primary.entity.toLowerCase()}.
              </p>
            </>
          ) : (
            <>
              <p className="mt-6 text-[17px] font-medium">
                {humanize(metric)} by {primary.entityKey.toLowerCase()}
              </p>
              <p className="mt-1 max-w-xl text-xl leading-8 text-[#3b3b39]">
                Peak {metric} among the analyzed {pluralize(primary.entityKey.toLowerCase())}.
              </p>
            </>
          )}
          <p className="mt-5 font-mono text-[13px] tabular-nums text-muted">Exact: {formatExact(primary.value)}</p>
          {primary.message && (
            <p className="mt-1 max-w-2xl break-words font-mono text-[12.5px] leading-5 text-muted">{primary.message}</p>
          )}
        </motion.div>
      </div>

      {low && primary.lowEntity !== undefined && (
        <motion.aside
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.35, delay: 0.35 }}
          className="border-t border-line pt-5 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-1"
        >
          <p className="mono-label">
            {primary.entityKey.toLowerCase() === "dataset" ? "Lowest recorded" : `Lowest ${primary.entityKey.toLowerCase()}`}
          </p>
          <p className="mt-2 break-words text-2xl font-medium tracking-tight">{primary.lowEntity}</p>
          <p className="mt-1 text-2xl tabular-nums tracking-tight text-muted">
            {low.figure}
            {low.suffix}
          </p>
          <p className="mt-1 font-mono text-[12.5px] tabular-nums text-muted">{formatExact(primary.lowValue ?? 0)}</p>
        </motion.aside>
      )}
    </div>
  );
}

function NoPrimary({ messages, failed }: { messages: string[]; failed: boolean }) {
  if (messages.length > 0) {
    return (
      <div className="mt-8 space-y-4">
        {messages.map((message, index) => (
          <motion.p
            key={index}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease, delay: index * 0.06 }}
            className="max-w-3xl text-[clamp(1.5rem,3vw,2.25rem)] font-medium leading-tight tracking-[-0.02em]"
          >
            {message}
          </motion.p>
        ))}
      </div>
    );
  }
  return (
    <p className={`mt-8 text-[clamp(1.5rem,3vw,2.25rem)] font-medium leading-tight tracking-[-0.02em] ${failed ? "text-bad" : ""}`}>
      {failed ? "The analysis did not produce a finding." : "The backend returned no findings for this question."}
    </p>
  );
}
