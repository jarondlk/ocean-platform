import { NextResponse } from "next/server";

import { auth } from "@/auth";
import { localAuthDisabled } from "@/lib/security-config";

const legacyAdminRoutes: Record<string, string> = {
  "/pipeline": "/admin/pipeline",
  "/database": "/admin/database",
  "/system": "/admin/system",
  "/debug": "/admin/debug",
};

const cop17Demo = process.env.NEXT_PUBLIC_COP17_DEMO === "true";

export default auth((request) => {
  if (cop17Demo && request.nextUrl.pathname === "/") {
    const destination = request.nextUrl.clone();
    destination.pathname = "/chat";
    return NextResponse.redirect(destination);
  }
  const adminRoute = legacyAdminRoutes[request.nextUrl.pathname];
  if (adminRoute) {
    const destination = request.nextUrl.clone();
    destination.pathname = adminRoute;
    return NextResponse.redirect(destination);
  }
  if (localAuthDisabled()) {
    return NextResponse.next();
  }
  const isLogin = request.nextUrl.pathname === "/login";
  if (!request.auth && !isLogin) {
    const loginUrl = new URL("/login", request.nextUrl.origin);
    loginUrl.searchParams.set(
      "returnTo",
      `${request.nextUrl.pathname}${request.nextUrl.search}`,
    );
    return NextResponse.redirect(loginUrl);
  }
  if (request.auth && isLogin && !request.nextUrl.searchParams.has("error")) {
    return NextResponse.redirect(new URL(cop17Demo ? "/chat" : "/", request.nextUrl.origin));
  }
  return NextResponse.next();
});

export const config = {
  runtime: "nodejs",
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|manifest.webmanifest).*)",
  ],
};
