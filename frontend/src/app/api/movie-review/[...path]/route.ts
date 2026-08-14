import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND_BASE = process.env.LONGTUBE_BACKEND_URL || "http://127.0.0.1:8000";

async function proxyMovieReview(
  request: NextRequest,
  { params }: { params: { path: string[] } },
) {
  const suffix = (params.path || []).map(encodeURIComponent).join("/");
  const target = new URL(`/api/movie-review/${suffix}`, BACKEND_BASE);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  const cookie = request.headers.get("cookie");
  const contentType = request.headers.get("content-type");
  if (cookie) headers.set("cookie", cookie);
  if (contentType) headers.set("content-type", contentType);

  const body = request.method === "GET" || request.method === "HEAD"
    ? undefined
    : await request.arrayBuffer();

  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });
    const responseHeaders = new Headers();
    for (const name of [
      "content-type",
      "content-length",
      "content-disposition",
      "last-modified",
      "etag",
    ]) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return Response.json(
      { detail: `영화 예고 백엔드 연결 실패: ${detail}` },
      { status: 502 },
    );
  }
}

export const GET = proxyMovieReview;
export const POST = proxyMovieReview;
export const PUT = proxyMovieReview;
export const DELETE = proxyMovieReview;
