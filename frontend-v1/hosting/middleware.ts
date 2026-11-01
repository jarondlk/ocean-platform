import { NextResponse, type NextRequest } from "next/server";
import { hostSettings, requestAllowed } from "./lib/settings";

export function middleware(request: NextRequest) {
  try {
    if (!requestAllowed(request, hostSettings(process.env))) return new NextResponse("Invalid v1 origin", { status: 403 });
  } catch { return new NextResponse("V1 host configuration unavailable", { status: 503 }); }
  return NextResponse.next();
}
export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
