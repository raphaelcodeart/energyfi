import { NextRequest, NextResponse } from "next/server";
import { clientIpHeaders } from "@/lib/client-ip";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/**
 * Public referral link resolver: checks the promoter code and forwards the
 * backend's attribution cookie, used if the visitor registers.
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const organizationId = request.nextUrl.searchParams.get("org");
  if (!organizationId) {
    return NextResponse.json({ error: "Missing organization" }, { status: 400 });
  }

  const apiRes = await fetch(
    `${API_INTERNAL_URL}/api/r/${encodeURIComponent(code)}?organization_id=${encodeURIComponent(organizationId)}`,
    { cache: "no-store", headers: clientIpHeaders(request) }
  );

  const body = await apiRes.text();
  const response = new NextResponse(body, {
    status: apiRes.status,
    headers: { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" },
  });
  const setCookieHeader = apiRes.headers.get("set-cookie");
  if (setCookieHeader) {
    response.headers.set("set-cookie", setCookieHeader);
  }
  return response;
}
