import { auth0 } from './lib/auth0.ts';
import { NextRequest } from 'next/server';

console.log('Testing auth0.getSession()...');
try {
  // getSession without arguments gets the session from the current async storage / cookies
  const session = await auth0.getSession();
  console.log('Current session from auth0:', session ? { user: session.user.email, sub: session.user.sub } : null);
} catch (e) {
  console.log('Error:', e.message);
}
