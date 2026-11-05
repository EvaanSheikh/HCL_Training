import { NextRequest } from 'next/server';
import { auth0 } from '@/lib/auth0';

export async function POST(request: NextRequest) {
  if (request.headers.get('origin') !== process.env.APP_BASE_URL || !request.cookies.get('noha-csrf')?.value || request.headers.get('x-csrf-token') !== request.cookies.get('noha-csrf')?.value) {
    return Response.json({ detail: 'Request rejected.' }, { status: 403, headers: { 'Cache-Control': 'no-store' } });
  }
  // The SDK's logout handler is GET-only. The externally reachable route is
  // POST+CSRF protected; convert internally so the browser cannot trigger it cross-site.
  const sdkRequest = new NextRequest(new URL('/api/auth/logout', request.url), { method: 'GET', headers: request.headers });
  return auth0.middleware(sdkRequest);
}
