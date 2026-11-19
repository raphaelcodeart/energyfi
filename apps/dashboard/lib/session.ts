import "server-only";
import { cookies } from "next/headers";

const SESSION_COOKIE = "sosnet_session";

export type Session = {
  accessToken: string;
  refreshToken: string;
  organizationId: string;
  email: string;
};

/**
 * The BFF session cookie (HttpOnly, Secure, SameSite=Lax). It holds the API
 * access and refresh tokens so browser JS never sees either
 * (docs/security-model.md).
 */
export async function getSession(): Promise<Session | null> {
  const store = await cookies();
  const raw = store.get(SESSION_COOKIE)?.value;
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export async function setSession(session: Session): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE, JSON.stringify(session), {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
}

export async function clearSession(): Promise<void> {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
}

/** Roles from the access token's JWT payload: used after login to pick the
 *  dashboard and by /api/auth/me (e.g. the customer/promoter switcher). */
export function decodeRolesFromAccessToken(accessToken: string): string[] {
  try {
    const payload = accessToken.split(".")[1] ?? "";
    const json = Buffer.from(payload, "base64url").toString("utf-8");
    const { roles } = JSON.parse(json) as { roles?: string[] };
    return roles ?? [];
  } catch {
    return [];
  }
}

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/**
 * Silent refresh. The access token lives 15 minutes, the refresh token 30
 * days (the cookie's maxAge). The API reads the refresh token from a cookie
 * (auth/router.py REFRESH_COOKIE_NAME), so it is replayed as one here,
 * server-to-server. Returns the persisted new session, or null when the
 * refresh token is no longer valid and only a new login can help.
 */
export async function refreshSession(session: Session): Promise<Session | null> {
  const apiRes = await fetch(
    `${API_INTERNAL_URL}/api/auth/refresh?organization_id=${encodeURIComponent(session.organizationId)}`,
    {
      method: "POST",
      headers: { Cookie: `sosnet_refresh_token=${session.refreshToken}` },
      cache: "no-store",
    }
  );
  if (!apiRes.ok) return null;

  const setCookieHeader = apiRes.headers.get("set-cookie") ?? "";
  const refreshMatch = /sosnet_refresh_token=([^;]+)/.exec(setCookieHeader);
  const { access_token: accessToken } = (await apiRes.json()) as { access_token: string };

  const updated: Session = {
    ...session,
    accessToken,
    refreshToken: refreshMatch?.[1] ?? session.refreshToken,
  };
  await setSession(updated);
  return updated;
}
