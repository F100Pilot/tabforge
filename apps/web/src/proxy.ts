import { NextResponse, type NextRequest } from "next/server";

/**
 * Desktop build (ADR-0008): the browser talks to the API through the web server's own origin,
 * so neither port has to be fixed at build time. The launcher picks free ports at each start
 * and passes the API address here at run time. Without it (the online build) this does nothing.
 */
export function proxy(request: NextRequest) {
  const api = process.env.TABFORGE_API_INTERNAL_URL;
  if (!api) return NextResponse.next();
  const target = new URL(request.nextUrl.pathname + request.nextUrl.search, api);
  return NextResponse.rewrite(target);
}

export const config = {
  matcher: "/v1/:path*",
};
