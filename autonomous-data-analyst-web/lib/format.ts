import type { Finding, Json, Row } from "./types";

export function formatInt(value: number): string {
  return value.toLocaleString("en-US");
}

export function formatExact(value: number): string {
  if (Number.isInteger(value)) return formatInt(value);
  return value.toLocaleString("en-US", { maximumFractionDigits: Math.abs(value) >= 1 ? 2 : 4 });
}

export function formatCompact(value: number): { figure: string; suffix: string } {
  const units: Array<[number, string]> = [
    [1e12, "T"],
    [1e9, "B"],
    [1e6, "M"],
    [1e3, "K"],
  ];
  for (const [limit, suffix] of units) {
    if (Math.abs(value) >= limit) {
      return { figure: (value / limit).toFixed(2).replace(/\.?0+$/, ""), suffix };
    }
  }
  return { figure: formatExact(value), suffix: "" };
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let amount = bytes / 1024;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(amount >= 100 ? 0 : 1)} ${units[unit]}`;
}

export function humanize(key: string): string {
  const text = key.replace(/[_-]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}

export function formatDate(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

export function pluralize(word: string): string {
  if (/[^aeiou]y$/i.test(word)) return `${word.slice(0, -1)}ies`;
  if (/(s|x|z|ch|sh)$/i.test(word)) return `${word}es`;
  return `${word}s`;
}

export function isRow(value: Json | undefined): value is Row {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Only an ownership-checked same-origin asset route may be returned.
 * Bridges backend `/api/analysis/{session_id}/charts/{asset_id}` routes
 * to the frontend BFF route `/api/noha/analysis/{session_id}/charts/{asset_id}`.
 * Legacy filesystem paths are intentionally rejected.
 */
export function chartUrl(path: string, version?: string): string | null {
  let resolved: string | null = null;
  if (/^\/api\/noha\/analysis\/[0-9a-f-]{36}\/charts\/[0-9a-f-]{36}$/.test(path)) {
    resolved = path;
  } else if (/^\/api\/analysis\/[0-9a-f-]{36}\/charts\/[0-9a-f-]{36}$/.test(path)) {
    resolved = `/api/noha${path.slice(4)}`;
  }
  if (!resolved) return null;
  return version ? `${resolved}?v=${encodeURIComponent(version)}` : resolved;
}

export interface PrimaryFinding {
  entity: string;
  entityKey: string;
  metric: string;
  value: number;
  lowEntity?: string;
  lowValue?: number;
  message: string;
}

function splitRow(
  row: Row,
  metricHint: string | undefined,
): { entity: string; entityKey: string; metric: string; value: number } | null {
  const numeric = Object.keys(row).filter((key) => typeof row[key] === "number");
  if (numeric.length === 0) return null;
  const metric = metricHint && numeric.includes(metricHint) ? metricHint : numeric[numeric.length - 1];
  const entityKey = Object.keys(row).find((key) => key !== metric);
  if (!entityKey) return null;
  return { entity: String(row[entityKey]), entityKey, metric, value: row[metric] as number };
}

function parseFinding(finding: Finding): PrimaryFinding | null {
  if (isRow(finding.highest)) {
    const high = splitRow(finding.highest, finding.metric);
    if (high) {
      const low = isRow(finding.lowest) ? splitRow(finding.lowest, finding.metric) : null;
      return {
        entity: high.entity,
        entityKey: high.entityKey,
        metric: high.metric,
        value: high.value,
        lowEntity: low?.entity,
        lowValue: low?.value,
        message: finding.message ?? "",
      };
    }
  }
  if (finding.type === "descriptive_statistics" || (finding as any).stats || typeof (finding as any).mean === "number") {
    const metric = finding.metric ?? "metric";
    const stats = (finding as any).stats ?? {};
    const value = typeof (finding as any).value === "number"
      ? (finding as any).value
      : typeof (finding as any).mean === "number"
        ? (finding as any).mean
        : stats.mean ?? stats.value ?? 0;
    const count = stats.count ?? (finding as any).count;
    const entity = count ? `All ${count.toLocaleString()} records` : "All records";
    return {
      entity,
      entityKey: "Dataset",
      metric: `Average ${metric}`,
      value,
      lowEntity: stats.min !== undefined ? "Minimum observed" : undefined,
      lowValue: stats.min,
      message: finding.message ?? `Average ${metric}: ${value.toLocaleString()}.`,
    };
  }
  return null;
}

/** Reads the backend's group_aggregate or descriptive_statistics finding. Prioritizes metric matching queryHint if provided. */
export function primaryFinding(findings: Finding[], queryHint?: string): PrimaryFinding | null {
  if (!findings || findings.length === 0) return null;

  if (queryHint) {
    const q = queryHint.toLowerCase();
    // Try to find finding matching the query metric
    for (const finding of findings) {
      const m = finding.metric?.toLowerCase();
      if (m && (q.includes(m) || (m === "revenue" && q.includes("sales")) || (m === "sales" && q.includes("revenue")))) {
        const parsed = parseFinding(finding);
        if (parsed) return parsed;
      }
    }
  }

  for (const finding of findings) {
    const parsed = parseFinding(finding);
    if (parsed) return parsed;
  }
  return null;
}
