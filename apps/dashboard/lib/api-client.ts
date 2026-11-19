import "server-only";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/**
 * Server-side fetch to FastAPI, always carrying the caller's access token.
 * Authorization is enforced by the API, not by what the frontend renders.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const session = await getSession();
  if (!session) {
    throw new ApiError(401, "No active session");
  }

  const res = await fetch(`${API_INTERNAL_URL}/api${path}`, {
    ...init,
    headers: {
      ...init?.headers,
      Authorization: `Bearer ${session.accessToken}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

/**
 * apiFetch() for a page's initial Server Component fetch: a 401 (expired
 * access token) redirects to /login instead of surfacing as a 500 page.
 *
 * The stale cookie is left alone on purpose: Server Components cannot write
 * cookies, and the next successful login overwrites it anyway.
 */
export async function apiFetchOrRedirectToLogin<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    return await apiFetch<T>(path, init);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      redirect("/login");
    }
    throw err;
  }
}
