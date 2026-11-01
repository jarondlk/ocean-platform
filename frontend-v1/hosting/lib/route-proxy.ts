import "server-only";
import { auth } from "./auth";
import { proxyRequest } from "./proxy";
import { hostSettings } from "./settings";

export async function hostProxy(request: Request) {
  try { return await proxyRequest(request, hostSettings(process.env), () => auth()); }
  catch { return Response.json({ error: { code: "host_unavailable", message: "The v1 host is unavailable" } }, { status: 503, headers: { "Cache-Control": "no-store" } }); }
}
