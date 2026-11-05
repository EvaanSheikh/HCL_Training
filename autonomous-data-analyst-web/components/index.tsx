"use client";

import { primaryFinding } from "@/lib/format";
import type { AnalyzeResponse } from "@/lib/types";
import { Answer } from "./answer";
import { ChartSection } from "./chart";
import { EvidenceSection } from "./evidence";
import { ReportSection } from "./report";
import { TraceSection } from "./trace";
import { ValidationSection } from "./validation";

/** Order of importance: answer, visualization, evidence, validation, trace, report. */
export function Result({ result }: { result: AnalyzeResponse }) {
  const primary = primaryFinding(result.findings, result.user_query);
  const firstMessage = result.findings.find((f) => f.message)?.message;
  const chartLabel = primary ? `${primary.metric} by ${primary.entityKey}` : "Supporting visualization";

  return (
    <div className="space-y-14">
      <Answer result={result} primary={primary} />
      <ChartSection visualizations={result.visualizations} sessionId={result.session_id} label={chartLabel} />
      <EvidenceSection evidence={result.evidence} findingMessage={firstMessage} />
      <ValidationSection checks={result.validation_results} />
      <TraceSection calls={result.tool_calls} evidence={result.evidence} />
      <ReportSection report={result.final_report} />
    </div>
  );
}
