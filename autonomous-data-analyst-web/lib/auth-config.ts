/**
 * Server-only helper to inspect Auth0 configuration status.
 *
 * Checks required environment variables and identifies missing or placeholder
 * values without ever exposing or printing secrets.
 */

export interface Auth0ConfigurationStatus {
  isConfigured: boolean;
  missingVariables: string[];
}

const REQUIRED_AUTH0_VARS: readonly string[] = [
  'AUTH0_DOMAIN',
  'AUTH0_CLIENT_ID',
  'AUTH0_CLIENT_SECRET',
  'AUTH0_SECRET',
  'APP_BASE_URL',
] as const;

const PLACEHOLDER_PREFIXES = [
  'your-',
  'replace-',
  'change-me',
  'example',
  'placeholder',
  'xxx',
  '<',
  'TODO',
];

export function checkAuth0Configuration(): Auth0ConfigurationStatus {
  const missingVariables: string[] = [];

  for (const name of REQUIRED_AUTH0_VARS) {
    const value = process.env[name];
    if (!value || value.trim() === '') {
      missingVariables.push(name);
      continue;
    }
    const lower = value.trim().toLowerCase();
    if (PLACEHOLDER_PREFIXES.some((prefix) => lower.startsWith(prefix.toLowerCase()))) {
      missingVariables.push(name);
    }
  }

  return {
    isConfigured: missingVariables.length === 0,
    missingVariables,
  };
}
