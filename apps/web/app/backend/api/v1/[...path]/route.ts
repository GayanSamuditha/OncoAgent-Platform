import { NextRequest } from "next/server";

const backendApiOrigin = (
  process.env.BACKEND_API_ORIGIN ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const requestHeadersToRemove = [
  "connection",
  "content-length",
  "host",
  "x-actor-id",
  "x-actor-role",
  "x-forwarded-host",
  "x-forwarded-port",
  "x-forwarded-proto",
];

const responseHeadersToRemove = [
  "connection",
  "content-encoding",
  "content-length",
  "transfer-encoding",
];

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxyRequest(
  request: NextRequest,
  context: RouteContext,
): Promise<Response> {
  const { path } = await context.params;
  const safePath = path.map((segment) => encodeURIComponent(segment)).join("/");
  const target = new URL(`/api/v1/${safePath}`, backendApiOrigin);
  target.search = request.nextUrl.search;

  const headers = new Headers(request.headers);
  for (const name of requestHeadersToRemove) headers.delete(name);
  if (!headers.get("authorization")?.trim()) headers.delete("authorization");

  const hasBody = !["GET", "HEAD"].includes(request.method);
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "manual",
    });
    const responseHeaders = new Headers(upstream.headers);
    for (const name of responseHeadersToRemove) responseHeaders.delete(name);
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { detail: "The upstream API could not be reached." },
      { status: 502 },
    );
  }
}

export const GET = proxyRequest;
export const HEAD = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
export const OPTIONS = proxyRequest;
