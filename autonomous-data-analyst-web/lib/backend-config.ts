/**
 * Server-only backend URL and origin configuration helpers.
 *
 * Normalizes backend URLs to prevent duplicated `/api` segments,
 * trailing slash issues, and protocol mismatches.
 */

export interface BackendConfigResult {
  ok: boolean;
  url: string;
  error?: string;
}

/**
 * Resolves and normalizes the backend API base URL for server-side communication.
 * Canonical variable: NOHA_API_BASE_URL (server-only).
 * Backward-compatibility fallback: NEXT_PUBLIC_API_BASE_URL.
 *
 * Normalization removes trailing slashes and any trailing `/api` segment,
 * ensuring that joining with `/api/...` never produces `/api/api/...`.
 */
export function getBackendBaseUrl(): BackendConfigResult {
  const raw = process.env.NOHA_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL;

  if (!raw || raw.trim() === '') {
    return {
      ok: false,
      url: '',
      error: 'Backend API URL is not configured. Please set NOHA_API_BASE_URL in your environment.',
    };
  }

  const trimmed = raw.trim();
  // Remove trailing slashes, then remove trailing /api, then trailing slashes again.
  const cleaned = trimmed.replace(/\/+$/, '').replace(/\/api$/, '').replace(/\/+$/, '');

  try {
    const parsed = new URL(cleaned);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return {
        ok: false,
        url: '',
        error: `Invalid backend URL protocol: "${parsed.protocol}". Expected "http:" or "https:".`,
      };
    }
    return {
      ok: true,
      url: cleaned,
    };
  } catch {
    return {
      ok: false,
      url: '',
      error: `Malformed backend URL: "${raw}". Expected format: "http://127.0.0.1:8000".`,
    };
  }
}

/**
 * Builds a clean upstream backend API URL for a given path and query string.
 * Ensures the resulting URL always has exactly one `/api` segment.
 *
 * @example
 * buildBackendApiUrl('health') => 'http://127.0.0.1:8000/api/health'
 * buildBackendApiUrl('/upload') => 'http://127.0.0.1:8000/api/upload'
 * buildBackendApiUrl('analysis/123/charts/456', '?v=1') => 'http://127.0.0.1:8000/api/analysis/123/charts/456?v=1'
 */
export function buildBackendApiUrl(path: string, searchParams = ''): { ok: true; url: string } | { ok: false; error: string } {
  const config = getBackendBaseUrl();
  if (!config.ok) {
    return { ok: false, error: config.error! };
  }

  // Strip leading slashes and any leading 'api/' from the requested path.
  let subPath = path.replace(/^\/+/, '');
  if (subPath.startsWith('api/')) {
    subPath = subPath.slice(4);
  } else if (subPath === 'api') {
    subPath = '';
  }

  const query = searchParams ? (searchParams.startsWith('?') ? searchParams : `?${searchParams}`) : '';
  const joined = subPath ? `${config.url}/api/${subPath}${query}` : `${config.url}/api${query}`;

  return { ok: true, url: joined };
}

/**
 * Validates whether an incoming HTTP Origin matches the configured APP_BASE_URL.
 *
 * In production: strictly requires origin === APP_BASE_URL.
 * In development: allows localhost and 127.0.0.1 on the same configured port
 * so developers aren't blocked by switching hostnames locally.
 */
export function isAllowedOrigin(incomingOrigin: string | null): { allowed: boolean; configuredOrigin: string | null } {
  const configured = process.env.APP_BASE_URL ? process.env.APP_BASE_URL.trim().replace(/\/+$/, '') : null;
  if (!configured) {
    return { allowed: false, configuredOrigin: null };
  }

  if (!incomingOrigin) {
    return { allowed: false, configuredOrigin: configured };
  }

  const cleanIncoming = incomingOrigin.trim().replace(/\/+$/, '');

  if (cleanIncoming === configured) {
    return { allowed: true, configuredOrigin: configured };
  }

  // Development convenience: permit localhost <-> 127.0.0.1 interchange on matching port
  if (process.env.NODE_ENV !== 'production') {
    try {
      const parsedConfig = new URL(configured);
      const parsedIncoming = new URL(cleanIncoming);
      const isLoopbackConfig = parsedConfig.hostname === 'localhost' || parsedConfig.hostname === '127.0.0.1';
      const isLoopbackIncoming = parsedIncoming.hostname === 'localhost' || parsedIncoming.hostname === '127.0.0.1';

      if (
        isLoopbackConfig &&
        isLoopbackIncoming &&
        parsedConfig.port === parsedIncoming.port &&
        parsedConfig.protocol === parsedIncoming.protocol
      ) {
        return { allowed: true, configuredOrigin: configured };
      }
    } catch {
      // ignore URL parse errors
    }
  }

  return { allowed: false, configuredOrigin: configured };
}
