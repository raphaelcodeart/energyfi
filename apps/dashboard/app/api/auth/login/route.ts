import { NextRequest, NextResponse } from "next/server";
import { clientIpHeaders } from "@/lib/client-ip";
import { friendlyApiError } from "@/lib/api-error";
import { decodeRolesFromAccessToken, setSession } from "@/lib/session";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { email, password, organizationId } = body as {
    email: string;
    password: string;
    organizationId: string;
  };

  const apiRes = await fetch(`${API_INTERNAL_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...clientIpHeaders(request) },
    body: JSON.stringify({ email, password, organization_id: organizationId }),
  });

  if (!apiRes.ok) {
    const message = await friendlyApiError(apiRes, "Accesso non riuscito. Riprova.");
    return NextResponse.json({ error: message }, { status: apiRes.status });
  }

  const setCookieHeader = apiRes.headers.get("set-cookie") ?? "";
  const refreshMatch = /sosnet_refresh_token=([^;]+)/.exec(setCookieHeader);
  const refreshToken = refreshMatch?.[1] ?? "";

  const { access_token: accessToken } = (await apiRes.json()) as { access_token: string };

  await setSession({ accessToken, refreshToken, organizationId, email });

  // Return the roles from the access token (auth/service.py:authenticate) so
  // the client can route to the right dashboard.
  const roles = decodeRolesFromAccessToken(accessToken);

  return NextResponse.json({ ok: true, roles });
}
