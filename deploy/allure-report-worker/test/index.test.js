import assert from "node:assert/strict";
import test from "node:test";
import worker from "../src/index.js";

function stream(text) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    },
  });
}

function object(body, contentType = "text/html; charset=utf-8") {
  return {
    body: stream(body),
    httpEtag: '"test-etag"',
    writeHttpMetadata(headers) {
      headers.set("content-type", contentType);
    },
  };
}

function bucket(objects) {
  const calls = [];
  return {
    calls,
    async get(key) {
      calls.push(key);
      return objects[key] ?? null;
    },
  };
}

async function request(path, { method = "GET", objects = {} } = {}) {
  const reports = bucket(objects);
  const response = await worker.fetch(
    new Request(`https://allure.your-fitness-coach.ru${path}`, { method }),
    { REPORTS: reports },
  );
  return { response, calls: reports.calls };
}

test("serves root and directory index objects without a listing", async () => {
  const root = await request("/", { objects: { "index.html": object("root") } });
  assert.equal(root.response.status, 200);
  assert.equal(await root.response.text(), "root");
  assert.deepEqual(root.calls, ["index.html"]);
  assert.equal(root.response.headers.get("cache-control"), "private, no-store");

  const latest = await request("/daily/latest/", {
    objects: { "daily/latest/index.html": object("latest") },
  });
  assert.equal(latest.response.status, 200);
  assert.equal(await latest.response.text(), "latest");
  assert.deepEqual(latest.calls, ["daily/latest/index.html"]);
});

test("serves exact assets and keeps HEAD bodies empty", async () => {
  const asset = await request("/daily/2026-09-07/123/app.js", {
    objects: { "daily/2026-09-07/123/app.js": object("console.log(1)", "text/javascript") },
  });
  assert.equal(asset.response.status, 200);
  assert.equal(await asset.response.text(), "console.log(1)");
  assert.deepEqual(asset.calls, ["daily/2026-09-07/123/app.js"]);

  const head = await request("/daily/2026-09-07/123/app.js", {
    method: "HEAD",
    objects: { "daily/2026-09-07/123/app.js": object("console.log(1)", "text/javascript") },
  });
  assert.equal(head.response.status, 200);
  assert.equal(await head.response.text(), "");
  assert.deepEqual(head.calls, ["daily/2026-09-07/123/app.js"]);
});

test("rejects traversal and malformed paths before touching R2", async () => {
  const normalizedTraversal = await request("/daily/%2e%2e/secret");
  assert.equal(normalizedTraversal.response.status, 404);
  assert.deepEqual(normalizedTraversal.calls, ["secret"]);

  for (const path of ["/daily/%2Fsecret", "/daily//latest/"]) {
    const result = await request(path);
    assert.equal(result.response.status, 400);
    assert.deepEqual(result.calls, []);
  }
});

test("returns controlled 404 and rejects unsupported methods", async () => {
  const missing = await request("/missing/");
  assert.equal(missing.response.status, 404);
  assert.deepEqual(missing.calls, ["missing/index.html"]);

  const post = await request("/", { method: "POST" });
  assert.equal(post.response.status, 405);
  assert.equal(post.response.headers.get("allow"), "GET, HEAD");
  assert.deepEqual(post.calls, []);
});
