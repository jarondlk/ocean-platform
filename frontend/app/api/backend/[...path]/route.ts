import type { NextRequest } from "next/server";

import { auth } from "@/auth";
import { tokenForSession } from "@/lib/internal-auth";

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
  const session = await auth();
  if (!session) {
    return Response.json({ detail: "Authentication required" }, { status: 401 });
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
    const origin = request.headers.get("Origin");
    if (!origin || origin !== request.nextUrl.origin) {
      return Response.json(
        { detail: "Cross-origin state change rejected" },
        { status: 403 },
      );
    }
  }

  const { path } = await context.params;
  let internalToken: string;
  try {
    internalToken = await tokenForSession(session);
  } catch {
    return Response.json(
      { detail: "Authenticated identity is incomplete" },
      { status: 401 },
    );
  }
  const init: RequestInit = {
    method: request.method,
    headers: {
      "Content-Type": request.headers.get("Content-Type") || "application/json",
      Accept: request.headers.get("Accept") || "application/json",
      Authorization: `Bearer ${internalToken}`,
    },
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl(path, request), init);
  } catch {
    return Response.json({ detail: "Backend API is unavailable" }, { status: 502 });
  }
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

export function PUT(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}

export function PATCH(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}

export function DELETE(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}
