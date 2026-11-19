import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Public AliExpress app callback, registered on openservice.aliexpress.com
 * so its URL is fixed. The backend exchanges the code (it holds the App
 * Secret). The aliexpress module endpoint is tried first, with the
 * imported-products one as fallback. */
const BACKEND_PATHS = [
  "/api/aliexpress/oauth/callback",
  "/api/imported-products/oauth/aliexpress/callback",
];

export async function GET(request: NextRequest) {
  let apiRes: Response | null = null;
  for (const path of BACKEND_PATHS) {
    apiRes = await fetch(`${API_INTERNAL_URL}${path}${request.nextUrl.search}`, {
      redirect: "manual",
      cache: "no-store",
    });
    if (apiRes.status !== 404) break;
  }
  if (!apiRes) return new NextResponse("Not found", { status: 404 });
  const location = apiRes.headers.get("location");
  if (location) return NextResponse.redirect(location, 302);
  return new NextResponse(await apiRes.text(), { status: apiRes.status });
}
