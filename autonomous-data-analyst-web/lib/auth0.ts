import { Auth0Client } from '@auth0/nextjs-auth0/server';
import { authSessionStore } from './auth-session-store';
// Run startup validation before constructing the Auth0Client.
// In production this throws on misconfiguration; in development it warns.
import './startup-validation';

export const auth0 = new Auth0Client({
  domain: process.env.AUTH0_DOMAIN,
  clientId: process.env.AUTH0_CLIENT_ID,
  clientSecret: process.env.AUTH0_CLIENT_SECRET,
  appBaseUrl: process.env.APP_BASE_URL,
  secret: process.env.AUTH0_SECRET,
  sessionStore: authSessionStore,
  authorizationParameters: {
    ...(process.env.AUTH0_AUDIENCE ? { audience: process.env.AUTH0_AUDIENCE } : {}),
    scope: 'openid profile email offline_access noha:access',
  },
  enableAccessTokenEndpoint: false,
  routes: { logout: '/api/auth/logout' },
  session: {
    rolling: true,
    absoluteDuration: 8 * 60 * 60,
    inactivityDuration: 30 * 60,
    cookie: { name: process.env.NODE_ENV === 'production' ? '__Host-noha-session' : 'noha-session', secure: process.env.NODE_ENV === 'production', sameSite: 'lax', path: '/' },
  },
});
