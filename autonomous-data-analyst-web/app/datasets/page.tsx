"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Sidebar, MobileBar } from "@/components/sidebar";
import { useSession } from "@/lib/session";
import {
  listDatasets,
  getDatasetDetails,
  deleteDataset,
  replaceDataset as apiReplaceDataset,
  uploadDataset,
  ApiError,
} from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/format";
import type { DatasetDetails, DatasetItem } from "@/lib/types";

export default function DatasetsPage() {
  const session = useSession();
  const [datasets, setDatasets] = useState<DatasetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [formatFilter, setFormatFilter] = useState<string>("all");

  // Inspect Modal
  const [selectedDataset, setSelectedDataset] = useState<DatasetDetails | null>(null);
  const [inspectLoading, setInspectLoading] = useState(false);
  const [inspectError, setInspectError] = useState<string | null>(null);

  // Upload / Replace Modal
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [replaceTargetId, setReplaceTargetId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Delete State
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const data = await listDatasets();
      setDatasets(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load datasets.");
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

  async function handleInspect(datasetId: string) {
    setInspectLoading(true);
    setInspectError(null);
    setSelectedDataset(null);
    try {
      const details = await getDatasetDetails(datasetId);
      setSelectedDataset(details);
    } catch (err) {
      setInspectError(err instanceof Error ? err.message : "Failed to inspect dataset.");
    } finally {
      setInspectLoading(false);
    }
  }

  async function handleDelete(dataset: DatasetItem) {
    const confirmed = window.confirm(
      `Are you sure you want to delete "${dataset.filename}" (${dataset.dataset_id})? This cannot be undone.`
    );
    if (!confirmed) return;

    setDeletingId(dataset.dataset_id);
    try {
      await deleteDataset(dataset.dataset_id);
      setDatasets((prev) => prev.filter((d) => d.dataset_id !== dataset.dataset_id));
      if (selectedDataset?.dataset_id === dataset.dataset_id) {
        setSelectedDataset(null);
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleFileSelect(file: File) {
    setUploading(true);
    setUploadError(null);
    try {
      if (replaceTargetId) {
        await apiReplaceDataset(replaceTargetId, file);
      } else {
        await uploadDataset(file, () => {});
      }
      setShowUploadModal(false);
      setReplaceTargetId(null);
      await loadData();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  const filtered = datasets.filter((d) => {
    const matchesSearch =
      d.filename.toLowerCase().includes(search.toLowerCase()) ||
      d.dataset_id.toLowerCase().includes(search.toLowerCase());
    const matchesFormat = formatFilter === "all" || d.extension.toLowerCase().includes(formatFilter);
    return matchesSearch && matchesFormat;
  });

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar active="Datasets" />
      <MobileBar active="Datasets" />
      <main className="min-w-0 bg-[var(--paper)]">
        <div className="mx-auto w-full max-w-[1180px] px-5 py-10 sm:px-10 lg:px-14 lg:py-14">
          {/* Header */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between border-b border-line pb-8">
            <div>
              <p className="mono-label !text-accent">Workspace / Data Assets</p>
              <h1 className="mt-2 text-3xl font-medium tracking-tight sm:text-4xl text-ink">Datasets</h1>
              <p className="mt-2 text-sm text-muted">
                Manage uploaded data assets, inspect columns and data quality, and initialize analytical workflows.
              </p>
            </div>
            {session.status === "authenticated" && (
              <button
                type="button"
                onClick={() => {
                  setReplaceTargetId(null);
                  setUploadError(null);
                  setShowUploadModal(true);
                }}
                className="inline-flex items-center gap-2 bg-ink px-5 py-2.5 font-mono text-[11px] uppercase tracking-wider text-white transition hover:bg-accent"
              >
                + Upload dataset
              </button>
            )}
          </div>

          {/* Auth Notice */}
          {session.status === "unauthenticated" && (
            <div className="mt-8 border border-line bg-surface p-6">
              <p className="mono-label text-ink">Authentication Required</p>
              <p className="mt-1 text-sm text-muted">
                Sign in to view, upload, and inspect your private datasets.
              </p>
              <a
                href="/auth/login"
                className="mt-4 inline-block bg-ink px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-white hover:bg-accent"
              >
                Sign in →
              </a>
            </div>
          )}

          {session.status === "authenticated" && (
            <>
              {/* Controls */}
              <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="relative flex-1 max-w-md">
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search by dataset name or ID..."
                    className="w-full border border-line bg-surface px-3 py-2 text-sm text-ink outline-none transition focus:border-accent"
                  />
                  {search && (
                    <button
                      onClick={() => setSearch("")}
                      className="absolute right-2.5 top-2 text-xs text-muted hover:text-ink"
                    >
                      ✕
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="mono-label text-xs">Format:</span>
                  {(["all", "csv", "xlsx", "json"] as const).map((fmt) => (
                    <button
                      key={fmt}
                      onClick={() => setFormatFilter(fmt)}
                      className={`px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider transition ${
                        formatFilter === fmt
                          ? "bg-ink text-white"
                          : "border border-line bg-surface text-muted hover:text-ink"
                      }`}
                    >
                      {fmt}
                    </button>
                  ))}
                </div>
              </div>

              {/* Status / Errors */}
              {loading && (
                <div className="mt-12 text-center py-16 text-sm text-muted font-mono">
                  Loading datasets...
                </div>
              )}

              {error && (
                <div className="mt-8 border-l-2 border-bad bg-bad/[0.04] p-4 text-sm text-bad">
                  {error}
                  <button onClick={loadData} className="ml-3 underline font-mono text-xs">
                    Retry
                  </button>
                </div>
              )}

              {/* Empty State */}
              {!loading && !error && filtered.length === 0 && (
                <div className="mt-12 border border-dashed border-line p-12 text-center">
                  <p className="font-medium text-ink">No datasets found</p>
                  <p className="mt-1 text-sm text-muted">
                    {search || formatFilter !== "all"
                      ? "Try adjusting your search or format filters."
                      : "Upload your first CSV, XLSX, or JSON dataset to begin."}
                  </p>
                  <button
                    onClick={() => {
                      setReplaceTargetId(null);
                      setUploadError(null);
                      setShowUploadModal(true);
                    }}
                    className="mt-5 inline-block bg-ink px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-white hover:bg-accent"
                  >
                    Upload dataset
                  </button>
                </div>
              )}

              {/* Datasets Table */}
              {!loading && filtered.length > 0 && (
                <div className="mt-6 overflow-x-auto border border-line bg-surface">
                  <table className="w-full border-collapse text-left text-sm">
                    <thead>
                      <tr className="border-b border-line bg-surface/80 font-mono text-[11px] uppercase tracking-wider text-muted">
                        <th className="px-4 py-3">Dataset Name & ID</th>
                        <th className="px-4 py-3">Format</th>
                        <th className="px-4 py-3">Records / Fields</th>
                        <th className="px-4 py-3">File Size</th>
                        <th className="px-4 py-3">Uploaded</th>
                        <th className="px-4 py-3">Status</th>
                        <th className="px-4 py-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/60">
                      {filtered.map((d) => (
                        <tr key={d.dataset_id} className="hover:bg-line/20 transition-colors">
                          <td className="px-4 py-3.5">
                            <div className="font-medium text-ink">{d.filename}</div>
                            <div className="font-mono text-[11px] text-muted">{d.dataset_id}</div>
                          </td>
                          <td className="px-4 py-3.5">
                            <span className="font-mono text-[11px] uppercase px-2 py-0.5 border border-line bg-paper">
                              {d.extension.replace(".", "")}
                            </span>
                          </td>
                          <td className="px-4 py-3.5 font-mono text-[12px]">
                            {d.row_count != null ? d.row_count.toLocaleString() : "—"} rows
                            <span className="text-muted"> · </span>
                            {d.col_count != null ? d.col_count : "—"} cols
                          </td>
                          <td className="px-4 py-3.5 font-mono text-[12px] text-muted">
                            {formatBytes(d.size_bytes)}
                          </td>
                          <td className="px-4 py-3.5 text-xs text-muted">
                            {formatDate(d.created_at)}
                          </td>
                          <td className="px-4 py-3.5">
                            <span className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase text-good">
                              <span className="size-1.5 rounded-full bg-good" />
                              {d.validation_status}
                            </span>
                          </td>
                          <td className="px-4 py-3.5 text-right space-x-2">
                            <button
                              type="button"
                              onClick={() => handleInspect(d.dataset_id)}
                              className="font-mono text-[11px] uppercase tracking-wider px-2.5 py-1 border border-line hover:border-ink transition"
                            >
                              Inspect
                            </button>
                            <Link
                              href={`/?dataset_id=${encodeURIComponent(d.dataset_id)}`}
                              className="font-mono text-[11px] uppercase tracking-wider px-2.5 py-1 bg-ink text-white hover:bg-accent transition"
                            >
                              Analyze →
                            </Link>
                            <button
                              type="button"
                              onClick={() => {
                                setReplaceTargetId(d.dataset_id);
                                setUploadError(null);
                                setShowUploadModal(true);
                              }}
                              className="font-mono text-[11px] uppercase tracking-wider px-2 py-1 text-muted hover:text-ink transition"
                            >
                              Replace
                            </button>
                            <button
                              type="button"
                              disabled={deletingId === d.dataset_id}
                              onClick={() => handleDelete(d)}
                              className="font-mono text-[11px] uppercase tracking-wider px-2 py-1 text-bad hover:underline disabled:opacity-40"
                            >
                              {deletingId === d.dataset_id ? "Deleting..." : "Delete"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          {/* Inspect Details Modal */}
          {(selectedDataset || inspectLoading || inspectError) && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
              <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto border border-line bg-surface p-6 sm:p-8 shadow-2xl">
                <div className="flex items-start justify-between border-b border-line pb-4">
                  <div>
                    <p className="mono-label !text-accent">Dataset Inspection</p>
                    <h2 className="mt-1 text-xl font-medium text-ink">
                      {selectedDataset ? selectedDataset.filename : "Loading details..."}
                    </h2>
                    {selectedDataset && (
                      <p className="font-mono text-[11px] text-muted">{selectedDataset.dataset_id}</p>
                    )}
                  </div>
                  <button
                    onClick={() => {
                      setSelectedDataset(null);
                      setInspectError(null);
                    }}
                    className="text-lg text-muted hover:text-ink"
                  >
                    ✕
                  </button>
                </div>

                {inspectLoading && (
                  <div className="py-12 text-center font-mono text-sm text-muted">
                    Extracting structural schema and statistics...
                  </div>
                )}

                {inspectError && (
                  <div className="mt-4 border-l-2 border-bad bg-bad/[0.04] p-4 text-sm text-bad">
                    {inspectError}
                  </div>
                )}

                {selectedDataset && (
                  <div className="mt-6 space-y-6">
                    {/* Summary metrics */}
                    <div className="grid grid-cols-2 gap-4 border-y border-line py-4 sm:grid-cols-4 font-mono text-xs">
                      <div>
                        <div className="text-muted">Total Rows</div>
                        <div className="mt-1 text-base font-medium text-ink">
                          {selectedDataset.row_count != null ? selectedDataset.row_count.toLocaleString() : "—"}
                        </div>
                      </div>
                      <div>
                        <div className="text-muted">Columns</div>
                        <div className="mt-1 text-base font-medium text-ink">
                          {selectedDataset.col_count}
                        </div>
                      </div>
                      <div>
                        <div className="text-muted">File Size</div>
                        <div className="mt-1 text-base font-medium text-ink">
                          {formatBytes(selectedDataset.size_bytes)}
                        </div>
                      </div>
                      <div>
                        <div className="text-muted">Duplicate Rows</div>
                        <div className="mt-1 text-base font-medium text-ink">
                          {selectedDataset.duplicate_rows}
                        </div>
                      </div>
                    </div>

                    {/* Columns breakdown */}
                    <div>
                      <h3 className="mono-label text-ink mb-3">Field Dictionary & Types</h3>
                      <div className="max-h-60 overflow-y-auto border border-line">
                        <table className="w-full text-left font-mono text-xs">
                          <thead className="border-b border-line bg-paper text-muted sticky top-0">
                            <tr>
                              <th className="px-3 py-2">#</th>
                              <th className="px-3 py-2">Column Name</th>
                              <th className="px-3 py-2">Data Type</th>
                              <th className="px-3 py-2">Missing Values</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-line/40">
                            {selectedDataset.column_names.map((col, idx) => (
                              <tr key={col} className="hover:bg-line/20">
                                <td className="px-3 py-1.5 text-muted">{idx + 1}</td>
                                <td className="px-3 py-1.5 font-medium text-ink">{col}</td>
                                <td className="px-3 py-1.5 text-muted">
                                  {selectedDataset.dtypes?.[col] ?? "unknown"}
                                </td>
                                <td className="px-3 py-1.5 text-muted">
                                  {selectedDataset.missing_values?.[col] ?? 0}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="flex justify-end gap-3 pt-4 border-t border-line">
                      <button
                        onClick={() => setSelectedDataset(null)}
                        className="px-4 py-2 border border-line font-mono text-[11px] uppercase tracking-wider"
                      >
                        Close
                      </button>
                      <Link
                        href={`/?dataset_id=${encodeURIComponent(selectedDataset.dataset_id)}`}
                        className="px-4 py-2 bg-ink text-white font-mono text-[11px] uppercase tracking-wider hover:bg-accent"
                      >
                        Start Analysis →
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Upload / Replace Modal */}
          {showUploadModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
              <div className="w-full max-w-lg border border-line bg-surface p-6 shadow-2xl">
                <div className="flex items-center justify-between border-b border-line pb-4">
                  <h3 className="text-lg font-medium text-ink">
                    {replaceTargetId ? "Replace Dataset" : "Upload Dataset"}
                  </h3>
                  <button onClick={() => setShowUploadModal(false)} className="text-muted hover:text-ink">
                    ✕
                  </button>
                </div>
                {replaceTargetId && (
                  <p className="mt-3 text-xs text-muted font-mono">
                    Replacing dataset ID: {replaceTargetId}. Historical references will remain intact.
                  </p>
                )}
                {uploadError && (
                  <div className="mt-4 border-l-2 border-bad bg-bad/[0.04] p-3 text-xs text-bad">
                    {uploadError}
                  </div>
                )}
                <div className="mt-5 border-2 border-dashed border-line p-8 text-center bg-paper">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.xlsx,.json"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void handleFileSelect(f);
                    }}
                  />
                  <p className="text-sm font-medium text-ink">Select a file from your computer</p>
                  <p className="mt-1 text-xs text-muted">Supports CSV, XLSX, and JSON up to 100 MB.</p>
                  <button
                    type="button"
                    disabled={uploading}
                    onClick={() => fileInputRef.current?.click()}
                    className="mt-4 inline-block bg-ink px-4 py-2 font-mono text-[11px] uppercase tracking-wider text-white hover:bg-accent disabled:opacity-50"
                  >
                    {uploading ? "Processing upload..." : "Choose file"}
                  </button>
                </div>
                <div className="mt-5 flex justify-end">
                  <button
                    type="button"
                    disabled={uploading}
                    onClick={() => setShowUploadModal(false)}
                    className="px-4 py-2 text-xs font-mono uppercase text-muted hover:text-ink"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}