import { NextResponse } from 'next/server';
import { buildBackendApiUrl } from '@/lib/backend-config';

export async function GET() {
  const resolved = buildBackendApiUrl('health');

  if (!resolved.ok) {
    return NextResponse.json(
      { status: 'unavailable', detail: resolved.error },
      { status: 503, headers: { 'Cache-Control': 'no-store' } },
    );
  }

  try {
    const upstream = await fetch(resolved.url, {
      cache: 'no-store',
      signal: AbortSignal.timeout(3000),
    });

    if (!upstream.ok) {
      return NextResponse.json(
        { status: 'unavailable', detail: `Upstream health check failed with HTTP ${upstream.status}.` },
        { status: 503, headers: { 'Cache-Control': 'no-store' } },
      );
    }

    const data = await upstream.json().catch(() => null);
    const isOk = data && (data.status === 'ok' || data.status === 'healthy');

    return NextResponse.json(
      { status: isOk ? 'ok' : 'unavailable' },
      { status: isOk ? 200 : 503, headers: { 'Cache-Control': 'no-store' } },
    );
  } catch {
    return NextResponse.json(
      { status: 'unavailable', detail: 'Upstream backend service is unreachable.' },
      { status: 503, headers: { 'Cache-Control': 'no-store' } },
    );
  }
}
