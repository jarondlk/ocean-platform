import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

const API_BASE_URL = process.env.API_BASE_URL || "http://127.0.0.1:8000";

function targetUrl(path: string[], request: NextRequest): string {
  const pathname = path.join("/");
  const search = request.nextUrl.search || "";
  return `${API_BASE_URL}/${pathname}${search}`;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const init: RequestInit = {
    method: request.method,
    headers: {
      "Content-Type": request.headers.get("Content-Type") || "application/json",
    },
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

  const upstream = await fetch(targetUrl(path, request), init);
  const headers = new Headers();
  const contentType = upstream.headers.get("Content-Type");
  if (contentType) headers.set("Content-Type", contentType);

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers,
  });
}

export function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}

export function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}
