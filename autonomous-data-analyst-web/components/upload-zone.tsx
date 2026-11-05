"use client";

import { useEffect, useId, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { uploadDataset, ApiError } from "@/lib/api";
import { ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES } from "@/lib/config";
import { formatBytes } from "@/lib/format";
import type { UploadResponse } from "@/lib/types";

type State =
  | { kind: "idle" }
  | { kind: "uploading"; name: string; loaded: number; total: number }
  | { kind: "error"; message: string; status?: number };

function checkFile(file: File): string | null {
  const lower = file.name.toLowerCase();
  if (!ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    return `Unsupported file type: ${file.name}. Allowed formats: CSV, XLSX, JSON.`;
  }
  if (file.size === 0) return `${file.name} is empty.`;
  if (file.size > MAX_UPLOAD_BYTES) {
    return `${file.name} is ${formatBytes(file.size)}. The maximum upload limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`;
  }
  return null;
}

interface UploadZoneProps {
  onUploaded: (dataset: UploadResponse) => void;
  disabled?: boolean;
  disabledReason?: string;
}

export function UploadZone({ onUploaded, disabled = false, disabledReason }: UploadZoneProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [state, setState] = useState<State>({ kind: "idle" });

  useEffect(() => () => abortRef.current?.abort(), []);

  async function handleFile(file: File) {
    if (disabled) return;

    const problem = checkFile(file);
    if (problem) {
      setState({ kind: "error", message: problem });
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ kind: "uploading", name: file.name, loaded: 0, total: file.size });
    try {
      const dataset = await uploadDataset(
        file,
        ({ loaded, total }) => setState({ kind: "uploading", name: file.name, loaded, total }),
        controller.signal,
      );
      onUploaded(dataset);
    } catch (error) {
      if (error instanceof ApiError && error.kind === "aborted") return;
      setState({
        kind: "error",
        message: error instanceof Error ? error.message : "Upload failed.",
        status: error instanceof ApiError ? error.status : undefined,
      });
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  const busy = state.kind === "uploading";
  const fraction = state.kind === "uploading" && state.total > 0 ? Math.min(state.loaded / state.total, 1) : 0;

  return (
    <div>
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={ALLOWED_EXTENSIONS.join(",")}
        disabled={busy || disabled}
        className="peer sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void handleFile(file);
        }}
      />
      <label
        htmlFor={disabled ? undefined : inputId}
        onDragEnter={(event) => {
          if (disabled) return;
          event.preventDefault();
          dragDepth.current += 1;
          if (!busy) setDragging(true);
        }}
        onDragOver={(event) => {
          if (disabled) return;
          event.preventDefault();
        }}
        onDragLeave={() => {
          if (disabled) return;
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragging(false);
        }}
        onDrop={(event) => {
          if (disabled) return;
          event.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          const file = event.dataTransfer.files?.[0];
          if (file && !busy) void handleFile(file);
        }}
        className={[
          "group block border border-dashed px-6 py-10 transition-colors duration-200 sm:px-10 sm:py-14",
          "peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent",
          disabled ? "cursor-not-allowed opacity-60 bg-surface border-line" : busy ? "cursor-progress" : "cursor-pointer",
          !disabled && dragging
            ? "border-accent bg-accent/[0.04]"
            : !disabled
              ? "border-[#c9c9c4] bg-surface hover:border-ink"
              : "",
        ].join(" ")}
      >
        <AnimatePresence mode="wait" initial={false}>
          {state.kind === "uploading" ? (
            <motion.div
              key="uploading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
            >
              <p className="mono-label">{fraction >= 1 ? "Validating on server" : "Uploading"}</p>
              <p className="mt-3 break-all text-2xl font-medium tracking-tight sm:text-3xl">{state.name}</p>
              <div
                className="mt-8 h-px w-full bg-line"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(fraction * 100)}
              >
                <motion.div
                  className="h-px origin-left bg-ink"
                  animate={{ scaleX: fraction }}
                  transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
                />
              </div>
              <p className="mono-label mt-3 tabular-nums">
                {formatBytes(state.loaded)} / {formatBytes(state.total)} · {Math.round(fraction * 100)}%
              </p>
            </motion.div>
          ) : (
            <motion.div
              key="idle"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
            >
              <p className="text-2xl font-medium tracking-tight sm:text-3xl">
                {disabled
                  ? disabledReason || "Dataset upload requires authentication"
                  : dragging
                    ? "Release to upload"
                    : "Drop a CSV, XLSX or JSON file"}
              </p>
              <p className="mt-3 text-[15px] text-muted">
                {disabled ? (
                  <span>
                    Please{" "}
                    <a href="/auth/login" className="text-ink underline decoration-line underline-offset-4 hover:decoration-ink">
                      sign in
                    </a>{" "}
                    to upload datasets.
                  </span>
                ) : (
                  <>
                    or{" "}
                    <span className="text-ink underline decoration-line underline-offset-4 group-hover:decoration-ink">
                      browse your files
                    </span>
                    . Up to 100 MB.
                  </>
                )}
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </label>

      <AnimatePresence>
        {state.kind === "error" && (
          <motion.div
            key="error"
            role="alert"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
            className="mt-3 border-l-2 border-bad bg-bad/[0.04] p-3 text-[14px] leading-6 text-bad"
          >
            <p>{state.message}</p>
            {state.status === 401 && (
              <p className="mt-2 text-[12px]">
                <a
                  href="/auth/login"
                  className="inline-block border border-bad/30 bg-surface px-2.5 py-1 font-mono uppercase tracking-wider text-bad hover:bg-bad hover:text-white"
                >
                  Sign in to continue →
                </a>
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
