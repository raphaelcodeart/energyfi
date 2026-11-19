import { NextRequest, NextResponse } from "next/server";
import { clientIpHeaders } from "@/lib/client-ip";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/**
 * Public, invite-only registration (referral_code from a promoter link).
 * The backend performs all validation.
 */
export async function POST(request: NextRequest) {
  const body = await request.json();
  const apiRes = await fetch(`${API_INTERNAL_URL}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...clientIpHeaders(request) },
    body: JSON.stringify(body),
  });

  const responseBody = await apiRes.text();
  return new NextResponse(responseBody, {
    status: apiRes.status,
    headers: { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" },
  });
}
