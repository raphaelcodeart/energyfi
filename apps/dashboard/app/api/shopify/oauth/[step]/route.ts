import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Public Shopify app install endpoints (install = app URL, callback =
 * allowed redirect URL). The backend does HMAC, state and code exchange;
 * this forwards the query and returns the backend's redirect. */
export async function GET(request: NextRequest, { params }: { params: Promise<{ step: string }> }) {
  const { step } = await params;
  if (step !== "install" && step !== "callback") {
    return new NextResponse("Not found", { status: 404 });
  }
  const apiRes = await fetch(`${API_INTERNAL_URL}/api/shopify/oauth/${step}${request.nextUrl.search}`, {
    redirect: "manual",
    cache: "no-store",
  });
  const location = apiRes.headers.get("location");
  if (location) return NextResponse.redirect(location, 302);
  return new NextResponse(await apiRes.text(), { status: apiRes.status });
}
