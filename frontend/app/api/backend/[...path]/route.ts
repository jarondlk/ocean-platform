import type { NextRequest } from "next/server";

import { auth } from "@/auth";
import { tokenForSession } from "@/lib/internal-auth";
import { localAuthDisabled } from "@/lib/security-config";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

const API_BASE_URL = process.env.API_BASE_URL || "http://127.0.0.1:8000";
const MAX_REQUEST_BODY_BYTES = 1_048_576;

function targetUrl(path: string[], request: NextRequest): string {
  const pathname = path.join("/");
  const search = request.nextUrl.search || "";
  return `${API_BASE_URL}/${pathname}${search}`;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const session = await auth();
  if (!session && !localAuthDisabled()) {
    return Response.json(
      { detail: "Authentication required" },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
    const origin = request.headers.get("Origin");
    if (!origin || origin !== request.nextUrl.origin) {
      return Response.json(
        { detail: "Cross-origin state change rejected" },
        { status: 403, headers: { "Cache-Control": "no-store" } },
      );
    }
    const contentLength = Number(request.headers.get("Content-Length") || "0");
    if (
      !Number.isFinite(contentLength) ||
      contentLength < 0 ||
      contentLength > MAX_REQUEST_BODY_BYTES
    ) {
      return Response.json(
        { detail: "Request body is too large" },
        { status: 413, headers: { "Cache-Control": "no-store" } },
      );
    }
  }

  const { path } = await context.params;
  let internalToken: string | null = null;
  if (session) {
    try {
      internalToken = await tokenForSession(session);
    } catch {
      return Response.json(
        { detail: "Authenticated identity is incomplete" },
        { status: 401, headers: { "Cache-Control": "no-store" } },
      );
    }
  }
  const init: RequestInit = {
    method: request.method,
    headers: {
      "Content-Type": request.headers.get("Content-Type") || "application/json",
      Accept: request.headers.get("Accept") || "application/json",
      ...(internalToken
        ? { Authorization: `Bearer ${internalToken}` }
        : {}),
    },
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    const body = await request.text();
    if (new TextEncoder().encode(body).byteLength > MAX_REQUEST_BODY_BYTES) {
      return Response.json(
        { detail: "Request body is too large" },
        { status: 413, headers: { "Cache-Control": "no-store" } },
      );
    }
    init.body = body;
  }

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl(path, request), init);
  } catch {
    return Response.json(
      { detail: "Backend API is unavailable" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
  const headers = new Headers();
  headers.set("Cache-Control", "no-store");
  for (const headerName of [
    "Content-Type",
    "Content-Disposition",
    "X-Export-Truncated",
  ]) {
    const value = upstream.headers.get(headerName);
    if (value) headers.set(headerName, value);
  }

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
