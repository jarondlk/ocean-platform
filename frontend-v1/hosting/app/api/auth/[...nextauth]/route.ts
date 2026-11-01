import { handlers } from "../../../../lib/auth";
import { hostSettings, requestAllowed } from "../../../../lib/settings";
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
async function handle(request: NextRequest) {
  try {
    if (!requestAllowed(request, hostSettings(process.env))) return new Response("Invalid v1 origin", { status: 403 });
    const response = await handlers[request.method === "POST" ? "POST" : "GET"](request);
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch { return new Response("V1 sign-in unavailable", { status: 503, headers: { "Cache-Control": "no-store" } }); }
}
export { handle as GET, handle as POST };
