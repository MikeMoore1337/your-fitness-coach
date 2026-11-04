// Local design preview; serves only this proposal and existing public YFC styles/assets.
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../../..");
const mounts = [
  ["/assets/", path.join(root, "frontend/public/assets")],
  ["/shared/", path.join(root, "frontend/src/styles")],
  ["/", __dirname],
];
const mime = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css",
  ".js": "text/javascript",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};
http
  .createServer((req, res) => {
    try {
      const pathname = decodeURIComponent(
        new URL(req.url, "http://localhost").pathname,
      );
      const [prefix, base] = mounts.find(([prefix]) =>
        pathname.startsWith(prefix),
      );
      const file = path.resolve(base, pathname.slice(prefix.length));
      if (
        !file.startsWith(base + path.sep) ||
        !fs.existsSync(file) ||
        !fs.statSync(file).isFile()
      ) {
        res.writeHead(404);
        res.end();
        return;
      }
      res.writeHead(200, {
        "content-type": mime[path.extname(file)] || "application/octet-stream",
        "cache-control": "no-store",
      });
      const stream = fs.createReadStream(file);
      stream.on("error", () => res.destroy());
      stream.pipe(res);
    } catch {
      res.writeHead(400);
      res.end();
    }
  })
  .listen(4827, "127.0.0.1", () =>
    process.stdout.write("http://127.0.0.1:4827/proposal.html\n"),
  );
