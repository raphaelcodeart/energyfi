import { NextRequest, NextResponse } from "next/server";
import { clientIpHeaders } from "@/lib/client-ip";
import { getSession, refreshSession, type Session } from "@/lib/session";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** True only for the API's invalid/expired-token 401 (messages from
 * foundation/deps.py get_current_user), so a refresh is attempted only when
 * it can help. */
async function isExpiredTokenResponse(apiRes: Response): Promise<boolean> {
  if (apiRes.status !== 401) return false;
  const body = await apiRes.clone().text().catch(() => "");
  return /Invalid or expired token|Missing bearer token|Wrong token type/.test(body);
}

/**
 * Same-origin BFF proxy for client components. The session cookie stays
 * here: the access token is attached server-side and never reaches client JS.
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { path } = await params;
  const search = request.nextUrl.search;
  const url = `${API_INTERNAL_URL}/api/${path.join("/")}${search}`;

  let apiRes = await fetch(url, {
    headers: { Authorization: `Bearer ${session.accessToken}`, ...clientIpHeaders(request) },
    cache: "no-store",
  });

  if (await isExpiredTokenResponse(apiRes)) {
    const refreshed: Session | null = await refreshSession(session);
    if (refreshed) {
      apiRes = await fetch(url, {
        headers: { Authorization: `Bearer ${refreshed.accessToken}`, ...clientIpHeaders(request) },
        cache: "no-store",
      });
    }
  }

  // arrayBuffer(), not text(): binary downloads (e.g. the contract dossier
  // zip) would be corrupted by UTF-8 decoding.
  const body = await apiRes.arrayBuffer();
  const headers = new Headers({
    "Content-Type": apiRes.headers.get("content-type") ?? "application/json",
  });
  // Carries the download file name; without it the browser derives one from the path.
  const disposition = apiRes.headers.get("content-disposition");
  if (disposition) headers.set("Content-Disposition", disposition);

  if (apiRes.status === 204 || apiRes.status === 205 || apiRes.status === 304) {
    return new NextResponse(null, { status: apiRes.status, headers });
  }
  return new NextResponse(body, { status: apiRes.status, headers });
}

/** Forwarding for every body-carrying method. Multipart uploads are passed
 * as raw bytes with the original content-type, boundary included. */
async function proxyWithBody(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
  method: string
) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { path } = await params;
  const search = request.nextUrl.search;
  const requestContentType = request.headers.get("content-type") ?? "";
  const isMultipart = requestContentType.startsWith("multipart/form-data");
  // Read the body once: a retry after a token refresh must resend the same bytes.
  const requestBody = isMultipart ? await request.arrayBuffer() : await request.text().catch(() => undefined);

  const url = `${API_INTERNAL_URL}/api/${path.join("/")}${search}`;
  const upstreamHeaders = (token: string) => ({
    Authorization: `Bearer ${token}`,
    "Content-Type": isMultipart ? requestContentType : "application/json",
    ...clientIpHeaders(request),
  });

  let apiRes = await fetch(url, {
    method,
    headers: upstreamHeaders(session.accessToken),
    body: requestBody,
    cache: "no-store",
  });

  if (await isExpiredTokenResponse(apiRes)) {
    const refreshed: Session | null = await refreshSession(session);
    if (refreshed) {
      apiRes = await fetch(url, {
        method,
        headers: upstreamHeaders(refreshed.accessToken),
        body: requestBody,
        cache: "no-store",
      });
    }
  }

  const body = await apiRes.text();
  const headers = { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" };
  // Null-body statuses: the Response constructor throws if given any body,
  // even an empty string.
  if (apiRes.status === 204 || apiRes.status === 205 || apiRes.status === 304) {
    return new NextResponse(null, { status: apiRes.status, headers });
  }
  return new NextResponse(body, { status: apiRes.status, headers });
}

export async function POST(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody(request, ctx, "POST");
}

export async function PATCH(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody(request, ctx, "PATCH");
}

export async function PUT(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody(request, ctx, "PUT");
}

export async function DELETE(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody(request, ctx, "DELETE");
}
