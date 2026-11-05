"use client";

import { useCallback, useEffect, useState } from "react";

export interface UserProfile {
  name?: string;
  email?: string;
}

export type SessionState =
  | { status: "loading"; user: null; error: null; missing?: string[] }
  | { status: "authenticated"; user: UserProfile; error: null; missing?: string[] }
  | { status: "unauthenticated"; user: null; error: null; missing?: string[] }
  | { status: "unconfigured"; user: null; error: string; missing: string[] }
  | { status: "unavailable"; user: null; error: string; missing?: string[] };

function extractCsrfToken(): string {
  if (typeof document === "undefined") return "";
  return (
    document.cookie
      .split("; ")
      .find((row) => row.startsWith("noha-csrf="))
      ?.split("=")[1] ?? ""
  );
}

export function useSession() {
  const [session, setSession] = useState<SessionState>({
    status: "loading",
    user: null,
    error: null,
  });

  const checkSession = useCallback(async () => {
    try {
      const response = await fetch("/api/auth/session", {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });

      if (response.status === 503) {
        const errorData = await response.json().catch(() => null);
        setSession({
          status: "unavailable",
          user: null,
          error: errorData?.detail || "Authentication service is temporarily unavailable.",
        });
        return;
      }

      if (!response.ok) {
        setSession({
          status: "unavailable",
          user: null,
          error: `Failed to check session (HTTP ${response.status}).`,
        });
        return;
      }

      const data = (await response.json()) as {
        authenticated?: boolean;
        configured?: boolean;
        user?: UserProfile;
        missing?: string[];
      };

      if (data && data.configured === false) {
        setSession({
          status: "unconfigured",
          user: null,
          error: "Authentication is not configured in this environment.",
          missing: data.missing || [],
        });
        return;
      }

      if (data && data.authenticated && data.user) {
        setSession({
          status: "authenticated",
          user: data.user,
          error: null,
        });
      } else {
        setSession({
          status: "unauthenticated",
          user: null,
          error: null,
        });
      }
    } catch {
      setSession({
        status: "unavailable",
        user: null,
        error: "Unable to reach session service.",
      });
    }
  }, []);

  useEffect(() => {
    void checkSession();
  }, [checkSession]);

  const signOut = useCallback(async () => {
    const csrf = extractCsrfToken();
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
      });
    } finally {
      if (typeof window !== "undefined") {
        window.location.assign("/");
      }
    }
  }, []);

  return {
    ...session,
    csrfToken: extractCsrfToken,
    refresh: checkSession,
    signOut,
  };
}
