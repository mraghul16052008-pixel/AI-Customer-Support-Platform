import { NextRequest } from "next/server";

const allowedRequests = new Set([
  "GET customers/1/orders",
  "POST orders",
  "POST chat",
  "POST chat/evidence",
]);

async function proxy(request: NextRequest, pathParts: string[]) {
  const path = pathParts.join("/");
  if (!allowedRequests.has(`${request.method} ${path}`)) {
    return Response.json({ detail: "Unsupported support API route" }, { status: 404 });
  }

  const baseUrl = process.env.SUPPORT_API_BASE_URL?.replace(/\/$/, "");
  const apiKey = process.env.SUPPORT_COMPANY_API_KEY;
  if (!baseUrl || !apiKey) {
    return Response.json(
      { detail: "Support service is not configured" },
      { status: 503 },
    );
  }

  try {
    const contentType = request.headers.get("content-type") ?? "application/json";
    const backendResponse = await fetch(`${baseUrl}/api/v1/${path}`, {
      method: request.method,
      headers: {
        "Content-Type": contentType,
        "X-API-Key": apiKey,
      },
      body: request.method === "GET" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
    return new Response(await backendResponse.text(), {
      status: backendResponse.status,
      headers: {
        "Content-Type": backendResponse.headers.get("Content-Type") ?? "application/json",
      },
    });
  } catch {
    return Response.json({ detail: "Support service is unavailable" }, { status: 502 });
  }
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
