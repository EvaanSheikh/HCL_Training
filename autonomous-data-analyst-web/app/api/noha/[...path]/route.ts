import { NextRequest, NextResponse } from 'next/server';
import { auth0 } from '@/lib/auth0';
import { buildBffResponse } from '@/lib/bounded-response.mjs';
import { buildBackendApiUrl, getBackendBaseUrl, isAllowedOrigin } from '@/lib/backend-config';
import { checkAuth0Configuration } from '@/lib/auth-config';

const noStore = { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' };
const MAX_UPLOAD_BODY = 101 * 1024 * 1024;
const MAX_JSON_BODY = 2 * 1024 * 1024;
const UPSTREAM_TIMEOUT_MS = 120_000;

function boundedBody(body: ReadableStream<Uint8Array> | null, limit: number, onExceeded: () => void) {
  if (!body) return null;
  const reader = body.getReader();
  let total = 0;
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      const { done, value } = await reader.read();
      if (done) { controller.close(); return; }
      total += value.byteLength;
      if (total > limit) { onExceeded(); await reader.cancel(); controller.error(new Error('Request body too large.')); return; }
      controller.enqueue(value);
    },
    async cancel(reason) { await reader.cancel(reason); },
  });
}

function allowedPath(parts: string[], method: string) {
  const path = parts.join('/');
  if (path === 'upload') return method === 'POST';
  if (path === 'analyze') return method === 'POST';
  if (/^analysis\/[0-9a-f-]{36}$/.test(path)) return method === 'GET';
  if (/^analysis\/[0-9a-f-]{36}\/charts\/[0-9a-f-]{36}$/.test(path)) return method === 'GET';
  if (path === 'datasets') return method === 'GET';
  if (/^datasets\/[0-9a-f-]{36}$/.test(path)) return method === 'GET' || method === 'DELETE';
  if (/^datasets\/[0-9a-f-]{36}\/suggested-questions$/.test(path)) return method === 'GET';
  if (/^datasets\/[0-9a-f-]{36}\/replace$/.test(path)) return method === 'POST';
  if (path === 'sessions') return method === 'GET';
  if (path === 'reports') return method === 'GET';
  if (path === 'traces') return method === 'GET';
  if (path === 'evaluations') return method === 'GET';
  if (path === 'evaluations/run') return method === 'POST';
  return false;
}

async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const backendCheck = getBackendBaseUrl();
  if (!backendCheck.ok) {
    return NextResponse.json({ detail: backendCheck.error }, { status: 503, headers: noStore });
  }

  const originCheck = isAllowedOrigin(request.headers.get('origin'));
  if (!originCheck.configuredOrigin) {
    return NextResponse.json(
      { detail: 'Application base URL is not configured. Please set APP_BASE_URL.' },
      { status: 503, headers: noStore },
    );
  }

  const { path } = await context.params;
  if (!allowedPath(path, request.method)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404, headers: noStore });
  }

  // Reject oversized declared bodies before session/JWKS work. The streamed
  // byte counter below remains authoritative for absent or dishonest lengths.
  if (request.method !== 'GET') {
    const isUpload = path[0] === 'upload' || (path[0] === 'datasets' && path[2] === 'replace');
    const limit = isUpload ? MAX_UPLOAD_BODY : MAX_JSON_BODY;
    const rawLength = request.headers.get('content-length');
    if (rawLength !== null && (!/^\d+$/.test(rawLength) || Number(rawLength) > limit)) {
      return NextResponse.json({ detail: 'Request body exceeds the configured limit.' }, { status: 413, headers: noStore });
    }
  }

  // Check Auth0 configuration. If unconfigured in local development, report clearly.
  const authConfig = checkAuth0Configuration();
  if (!authConfig.isConfigured) {
    return NextResponse.json(
      {
        detail: 'Authentication is not configured. Configure Auth0 in your environment to perform this action.',
      },
      { status: 503, headers: noStore },
    );
  }

  let session;
  try {
    session = await auth0.getSession();
  } catch {
    return NextResponse.json({ detail: 'Authentication unavailable.' }, { status: 503, headers: noStore });
  }

  if (!session) {
    return NextResponse.json({ detail: 'Authentication required.' }, { status: 401, headers: noStore });
  }

  if (request.method !== 'GET') {
    const csrf = request.cookies.get('noha-csrf')?.value;
    if (!originCheck.allowed || !csrf || request.headers.get('x-csrf-token') !== csrf) {
      return NextResponse.json({ detail: 'Request rejected.' }, { status: 403, headers: noStore });
    }
  }

  let accessToken: string;
  try {
    accessToken = (await auth0.getAccessToken()).token;
  } catch {
    return NextResponse.json({ detail: 'Authentication expired. Please sign in again.' }, { status: 401, headers: noStore });
  }

  const headers = new Headers({ Authorization: `Bearer ${accessToken}` });
  const contentType = request.headers.get('content-type');
  if (contentType) headers.set('Content-Type', contentType);

  let targetPath = path.join('/');
  if (path.length === 2 && path[0] === 'datasets') {
    targetPath = `datasets/item/${path[1]}`;
  } else if (path.length === 3 && path[0] === 'datasets' && path[2] === 'replace') {
    targetPath = `datasets/replace/${path[1]}`;
  } else if (path.length === 3 && path[0] === 'datasets' && path[2] === 'suggested-questions') {
    targetPath = `datasets/suggested-questions/${path[1]}`;
  }

  const upstreamTarget = buildBackendApiUrl(targetPath, request.nextUrl.search);
  if (!upstreamTarget.ok) {
    return NextResponse.json({ detail: upstreamTarget.error }, { status: 503, headers: noStore });
  }

  let exceeded = false;
  let upstream: Response | null;
  const isUpload = path[0] === 'upload' || (path[0] === 'datasets' && path[2] === 'replace');
  try {
    upstream = await fetch(upstreamTarget.url, {
      method: request.method,
      headers,
      body: request.method === 'GET'
        ? undefined
        : boundedBody(
            request.body,
            isUpload ? MAX_UPLOAD_BODY : MAX_JSON_BODY,
            () => { exceeded = true; },
          ),
      cache: 'no-store',
      redirect: 'manual',
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(UPSTREAM_TIMEOUT_MS)]),
      duplex: 'half',
    } as RequestInit & { duplex: 'half' }).catch(() => null);
  } catch {
    upstream = null;
  }

  if (exceeded) {
    return NextResponse.json({ detail: 'Request body exceeds the configured limit.' }, { status: 413, headers: noStore });
  }
  if (!upstream) {
    return NextResponse.json({ detail: 'Analysis service unavailable.' }, { status: 502, headers: noStore });
  }

  return buildBffResponse(upstream);
}

export const GET = forward;
export const POST = forward;
export const DELETE = forward;
