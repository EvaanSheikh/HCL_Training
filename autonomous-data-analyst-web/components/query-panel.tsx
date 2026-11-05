"use client";

import { useEffect, useRef, useState } from "react";
import { getSuggestedQuestions } from "@/lib/api";
import type { SuggestedQuestionItem } from "@/lib/types";

export const FALLBACK_QUESTIONS = [
  "Which category has the highest average value?",
  "Show changes over time.",
  "What is the correlation between key numeric measures?",
] as const;

export const EXAMPLE_QUESTIONS = FALLBACK_QUESTIONS;

interface QueryPanelProps {
  query: string;
  onQueryChange: (value: string) => void;
  onRun: () => void;
  running: boolean;
  hasDataset: boolean;
  datasetId?: string;
  disabled?: boolean;
  disabledReason?: string;
}

export function QueryPanel({
  query,
  onQueryChange,
  onRun,
  running,
  hasDataset,
  datasetId,
  disabled = false,
  disabledReason,
}: QueryPanelProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [suggestions, setSuggestions] = useState<SuggestedQuestionItem[]>([]);
  const [suggestionOffset, setSuggestionOffset] = useState(0);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);

  const hasQuery = query.trim().length > 0;
  const canRun = !disabled && hasDataset && hasQuery && !running;
  const hint = disabled
    ? disabledReason || "Sign in to run analysis."
    : !hasDataset
      ? "Upload a dataset to run an analysis."
      : !hasQuery
        ? "Enter a question."
        : "Cmd/Ctrl + Enter to run.";

  // Fetch schema-aware suggested questions whenever active dataset changes
  useEffect(() => {
    // Immediately clear suggestions to prevent stale cross-dataset contamination
    setSuggestions([]);
    setSuggestionOffset(0);
    setSuggestionError(null);

    if (!hasDataset || !datasetId) {
      setLoadingSuggestions(false);
      return;
    }

    const controller = new AbortController();
    setLoadingSuggestions(true);

    getSuggestedQuestions(datasetId, 0, controller.signal)
      .then((data) => {
        setSuggestions(data.suggestions || []);
        setSuggestionError(null);
      })
      .catch((err) => {
        if (err.name === "AbortError" || (err && err.kind === "aborted")) {
          return;
        }
        setSuggestionError("Could not load dynamic suggestions for this dataset.");
      })
      .finally(() => {
        setLoadingSuggestions(false);
      });

    return () => {
      controller.abort();
    };
  }, [hasDataset, datasetId]);

  function handleRegenerate() {
    if (!hasDataset || !datasetId || loadingSuggestions) return;
    const nextOffset = suggestionOffset + 4;
    setSuggestionOffset(nextOffset);
    setLoadingSuggestions(true);
    setSuggestionError(null);
    getSuggestedQuestions(datasetId, nextOffset)
      .then((data) => {
        setSuggestions(data.suggestions || []);
      })
      .catch(() => {
        setSuggestionError("Failed to regenerate suggestions.");
      })
      .finally(() => {
        setLoadingSuggestions(false);
      });
  }

  function formatCategoryBadge(category?: string) {
    switch (category) {
      case "group_comparison":
        return "Comparison";
      case "time_series":
        return "Trend";
      case "correlation":
        return "Correlation";
      case "outlier_detection":
        return "Outliers";
      case "descriptive_statistics":
        return "Summary";
      default:
        return "Analysis";
    }
  }

  return (
    <section aria-label="Question">
      <label htmlFor="question" className="mono-label block">
        Question
      </label>
      <p className="mt-2 text-2xl font-medium tracking-tight sm:text-3xl">What would you like to understand?</p>

      <textarea
        id="question"
        ref={textareaRef}
        value={query}
        maxLength={2000}
        rows={3}
        disabled={running}
        placeholder={
          hasDataset
            ? "Ask a question about your uploaded dataset in plain language."
            : "Upload a dataset first, then ask questions about it."
        }
        onChange={(event) => onQueryChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && canRun) {
            event.preventDefault();
            onRun();
          }
        }}
        className="mt-5 block w-full resize-y border border-[#c9c9c4] bg-surface px-5 py-4 text-lg leading-7 outline-none transition-colors duration-150 placeholder:text-[#a3a3a0] focus:border-ink disabled:opacity-60"
      />

      <div className="mt-4 flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <p className="mono-label" aria-live="polite">
          {hint}
        </p>
        <button
          type="button"
          onClick={onRun}
          disabled={!canRun}
          className="bg-ink px-7 py-3 text-[15px] font-medium text-white transition-[background-color,transform] duration-150 hover:bg-accent active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-[#c9c9c4] disabled:hover:bg-[#c9c9c4] disabled:active:scale-100"
        >
          {running ? "Running analysis" : "Run analysis"}
        </button>
      </div>

      <div className="mt-8">
        <div className="flex items-center justify-between">
          <p className="mono-label">
            {hasDataset ? "Suggested Questions for Dataset" : "Example Questions"}
          </p>
          {hasDataset && datasetId && (
            <button
              type="button"
              onClick={handleRegenerate}
              disabled={loadingSuggestions || running}
              className="text-[11px] font-mono uppercase tracking-wider text-[#737370] hover:text-ink disabled:opacity-40"
            >
              {loadingSuggestions ? "Generating..." : "↻ Regenerate"}
            </button>
          )}
        </div>

        {!hasDataset && (
          <div className="mt-3 border-t border-line py-4 text-sm text-[#737370]">
            Upload or select a dataset to discover schema-aware questions tailored to your data.
          </div>
        )}

        {hasDataset && loadingSuggestions && suggestions.length === 0 && (
          <div className="mt-3 border-t border-line py-4 text-sm text-[#737370] animate-pulse">
            Inspecting dataset schema and formulating analytical questions...
          </div>
        )}

        {hasDataset && suggestionError && suggestions.length === 0 && (
          <div className="mt-3 border-t border-line py-4 text-sm text-[#991b1b]">
            {suggestionError}
          </div>
        )}

        {hasDataset && suggestions.length > 0 && (
          <ul className="mt-3 border-t border-line">
            {suggestions.map((item) => (
              <li key={item.id} className="border-b border-line">
                <button
                  type="button"
                  disabled={running}
                  onClick={() => {
                    onQueryChange(item.question);
                    textareaRef.current?.focus();
                  }}
                  className="flex w-full items-baseline justify-between gap-4 py-3 text-left text-[16px] transition-colors duration-150 hover:text-accent disabled:opacity-50 disabled:hover:text-ink"
                >
                  <span className="flex-1">{item.question}</span>
                  <span className="mono-label shrink-0 text-[10px] uppercase tracking-wider text-[#888] bg-[#f0f0ee] px-2 py-0.5 rounded">
                    {formatCategoryBadge(item.category)}
                  </span>
                  <span className="mono-label shrink-0">Use</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
