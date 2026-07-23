import { NextResponse } from "next/server";

import { auth } from "@/auth";


export default auth((request) => {
  if (process.env.AUTH_MODE?.trim().toLowerCase() === "disabled") {
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
    return NextResponse.redirect(new URL("/", request.nextUrl.origin));
  }
  return NextResponse.next();
});

export const config = {
  runtime: "nodejs",
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
