const allowedGetPaths = [
  /^admin\/orders$/,
  /^admin\/conversations$/,
  /^admin\/conversations\/\d+$/,
  /^admin\/escalations$/,
  /^admin\/escalations\/\d+$/,
  /^admin\/analytics$/,
];

function readServerSetting(name: string): string | undefined {
  return process.env[name];
}

async function proxy(request: Request, pathParts: string[]) {
  const path = pathParts.join("/");
  const allowed = request.method === "GET"
    ? allowedGetPaths.some((pattern) => pattern.test(path))
    : request.method === "PATCH" && /^admin\/escalations\/\d+$/.test(path);
  if (!allowed) {
    return Response.json({ detail: "Unsupported support API route" }, { status: 404 });
  }

  const baseUrl = readServerSetting("SUPPORT_API_BASE_URL")?.replace(/\/$/, "");
  const apiKey = readServerSetting("SUPPORT_COMPANY_API_KEY");
  if (!baseUrl || !apiKey) {
    return Response.json(
      { detail: "Support service is not configured" },
      { status: 503 },
    );
  }

  try {
    const backendResponse = await fetch(`${baseUrl}/api/v1/${path}`, {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
      body: request.method === "GET" ? undefined : await request.text(),
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
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

export async function GET(request: Request, context: RouteContext) {
  return proxy(request, (await context.params).path);
}

export async function PATCH(request: Request, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
