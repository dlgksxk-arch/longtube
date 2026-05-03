import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/signup"];
const PUBLIC_PREFIXES = ["/_next", "/favicon.ico"];

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (
    PUBLIC_PATHS.includes(pathname) ||
    PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix))
  ) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has("longtube_session");
  if (hasSession) return NextResponse.next();

  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = "/login";
  loginUrl.search = "";
  if (pathname !== "/") {
    loginUrl.searchParams.set("next", `${pathname}${search}`);
  }
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!api).*)"],
};
