import { Auth0Client } from '@auth0/nextjs-auth0/server';

const clientWithoutAudience = new Auth0Client({
  domain: 'dev-acg2z7ixw8t6hw8s.us.auth0.com',
  clientId: 'DdDDzO43jJbLvJ61zb3QSmmc4dcC1y3V',
  clientSecret: '01234567890123456789012345678901',
  appBaseUrl: 'http://localhost:3000',
  secret: '0123456789012345678901234567890101234567890123456789012345678901',
  authorizationParameters: {
    audience: undefined,
    scope: 'openid profile email offline_access noha:access'
  }
});

console.log('Testing login URL generation without audience...');
const req = new Request('http://localhost:3000/auth/login');
const res = await clientWithoutAudience.middleware(req);
const location = res.headers.get('location');
console.log('Location status:', res.status);
console.log('Has audience param:', location?.includes('audience='));
console.log('Location prefix:', location?.slice(0, 100));

// Test what Auth0 returns for this URL
const auth0Res = await fetch(location, { redirect: 'manual' });
console.log('Auth0 response status:', auth0Res.status);
console.log('Auth0 response location:', auth0Res.headers.get('location'));

const clientWithExampleAudience = new Auth0Client({
  domain: 'dev-acg2z7ixw8t6hw8s.us.auth0.com',
  clientId: 'DdDDzO43jJbLvJ61zb3QSmmc4dcC1y3V',
  clientSecret: '01234567890123456789012345678901',
  appBaseUrl: 'http://localhost:3000',
  secret: '0123456789012345678901234567890101234567890123456789012345678901',
  authorizationParameters: {
    audience: 'https://api.noha.example',
    scope: 'openid profile email offline_access noha:access'
  }
});

console.log('\nTesting login URL generation with audience=https://api.noha.example...');
const req2 = new Request('http://localhost:3000/auth/login');
const res2 = await clientWithExampleAudience.middleware(req2);
const location2 = res2.headers.get('location');
console.log('Location status:', res2.status);
console.log('Has audience param:', location2?.includes('audience='));
const auth0Res2 = await fetch(location2, { redirect: 'manual' });
console.log('Auth0 response status:', auth0Res2.status);
console.log('Auth0 response location:', auth0Res2.headers.get('location'));
