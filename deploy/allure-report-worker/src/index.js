const MAX_PATH_LENGTH = 16 * 1024;
const ALLOWED_METHODS = "GET, HEAD";
const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/;

function errorResponse(status, message) {
  return new Response(message, {
    status,
    headers: {
      "cache-control": "private, no-store",
      "content-type": "text/plain; charset=utf-8",
      "x-content-type-options": "nosniff",
    },
  });
}

function contentTypeForKey(key) {
  const extension = key.slice(key.lastIndexOf(".")).toLowerCase();
  return {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".webm": "video/webm",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
  }[extension] ?? "application/octet-stream";
}

function objectKeyForPath(pathname) {
  if (pathname.length > MAX_PATH_LENGTH || !pathname.startsWith("/")) {
    throw new TypeError("invalid report path");
  }
  if (pathname === "/") return "index.html";

  const trailingSlash = pathname.endsWith("/");
  const rawSegments = pathname.split("/");
  const segmentEnd = trailingSlash ? rawSegments.length - 1 : rawSegments.length;
  if (rawSegments.slice(1, segmentEnd).some((segment) => segment === "")) {
    throw new TypeError("invalid report path");
  }

  const segments = rawSegments.slice(1, segmentEnd).map((segment) => {
    let decoded;
    try {
      decoded = decodeURIComponent(segment);
    } catch {
      throw new TypeError("invalid report path");
    }
    if (
      !decoded ||
      decoded === "." ||
      decoded === ".." ||
      decoded.includes("/") ||
      decoded.includes("\\") ||
      CONTROL_CHARACTERS.test(decoded)
    ) {
      throw new TypeError("invalid report path");
    }
    return decoded;
  });
  if (segments.length === 0) throw new TypeError("invalid report path");
  const key = segments.join("/");
  return trailingSlash ? `${key}/index.html` : key;
}

function responseHeaders(object, key) {
  const headers = new Headers();
  if (typeof object.writeHttpMetadata === "function") object.writeHttpMetadata(headers);
  if (!headers.has("content-type")) headers.set("content-type", contentTypeForKey(key));
  if (object.httpEtag) headers.set("etag", object.httpEtag);
  headers.set("cache-control", "private, no-store");
  headers.set("x-content-type-options", "nosniff");
  return headers;
}

export default {
  async fetch(request, env) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response(null, {
        status: 405,
        headers: {
          allow: ALLOWED_METHODS,
          "cache-control": "private, no-store",
          "x-content-type-options": "nosniff",
        },
      });
    }

    let key;
    try {
      key = objectKeyForPath(new URL(request.url).pathname);
    } catch {
      return errorResponse(400, "Invalid report path");
    }

    if (!env?.REPORTS || typeof env.REPORTS.get !== "function") {
      return errorResponse(500, "Report origin is not configured");
    }

    try {
      const object = await env.REPORTS.get(key);
      if (!object) return errorResponse(404, "Report not found");
      return new Response(request.method === "HEAD" ? null : object.body, {
        headers: responseHeaders(object, key),
      });
    } catch {
      return errorResponse(502, "Report origin is unavailable");
    }
  },
};

export { objectKeyForPath };
