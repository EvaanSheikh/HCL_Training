import { randomBytes } from 'node:crypto';
import { NextResponse } from 'next/server';
import { auth0 } from '@/lib/auth0';
import { checkAuth0Configuration } from '@/lib/auth-config';

export async function GET() {
  const config = checkAuth0Configuration();

  // If Auth0 is not configured in this development environment, return an explicit
  // unconfigured response so the UI can provide actionable instructions rather than
  // hanging in a loading state or failing with an ambiguous 503.
  if (!config.isConfigured) {
    return NextResponse.json(
      {
        authenticated: false,
        configured: false,
        missing: config.missingVariables,
      },
      { headers: { 'Cache-Control': 'no-store' } },
    );
  }

  let session;
  try {
    session = await auth0.getSession();
  } catch {
    return NextResponse.json(
      { detail: 'Authentication unavailable.' },
      { status: 503, headers: { 'Cache-Control': 'no-store' } },
    );
  }

  const response = NextResponse.json(
    session
      ? {
          authenticated: true,
          configured: true,
          user: { name: session.user.name, email: session.user.email },
        }
      : { authenticated: false },
  );

  if (session) {
    response.cookies.set('noha-csrf', randomBytes(32).toString('base64url'), {
      httpOnly: false,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'strict',
      path: '/',
      maxAge: 1800,
    });
  }

  response.headers.set('Cache-Control', 'no-store');
  return response;
}
