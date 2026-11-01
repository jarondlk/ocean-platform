export const dynamic = "force-dynamic";
export function GET() {
  return Response.json({ version: "ocean-v1-mode-v1", mode: "service" }, { headers: { "Cache-Control": "no-store" } });
}
