import { NextResponse, type NextRequest } from "next/server";

/**
 * Signed-out visitors go straight to /login instead of flashing the dashboard shell.
 * The cookie is only checked for presence here; the API validates it on every call
 * and the client redirects on any 401.
 */
export function middleware(req: NextRequest) {
  const hasSession = req.cookies.has("gw_session");
  const { pathname, search } = req.nextUrl;
  if (!hasSession && pathname !== "/login") {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    if (pathname !== "/") url.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Everything except the proxied API surfaces, Next internals and static files.
  matcher: ["/((?!api/|v1/|health|readyz|docs|openapi\\.json|_next/|favicon|icon|.*\\.(?:svg|png|jpg|ico|webp|txt)$).*)"],
};
