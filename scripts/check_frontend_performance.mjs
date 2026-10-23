import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, relative, resolve } from "node:path";
import { gzipSync } from "node:zlib";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const frontendRoot = join(projectRoot, "frontend");
const distRoot = join(frontendRoot, "dist");
const publicRoot = join(frontendRoot, "public");
const manifest = JSON.parse(
  readFileSync(join(distRoot, ".vite", "manifest.json"), "utf8"),
);
const entry = manifest["index.html"];

if (!entry?.file) {
  throw new Error(
    "Vite manifest does not contain the index.html entry. Run npm run build first.",
  );
}

function byteMetrics(path) {
  const bytes = readFileSync(path);
  return { raw: bytes.byteLength, gzip: gzipSync(bytes).byteLength };
}

function filesUnder(root) {
  const files = [];
  for (const item of readdirSync(root, { withFileTypes: true })) {
    const path = join(root, item.name);
    if (item.isDirectory()) files.push(...filesUnder(path));
    else files.push(path);
  }
  return files;
}

const entryJsPath = join(distRoot, entry.file);
const entryJs = byteMetrics(entryJsPath);
const entryCss = (entry.css ?? []).reduce(
  (total, file) => {
    const metric = byteMetrics(join(distRoot, file));
    total.raw += metric.raw;
    total.gzip += metric.gzip;
    return total;
  },
  { raw: 0, gzip: 0 },
);
const publicFiles = filesUnder(publicRoot).map((path) => ({
  path,
  bytes: statSync(path).size,
}));
const publicAssets = {
  count: publicFiles.length,
  raw: publicFiles.reduce((total, file) => total + file.bytes, 0),
  largest: publicFiles.reduce(
    (largest, file) => (file.bytes > largest.bytes ? file : largest),
    { path: "", bytes: 0 },
  ),
};

// Budgets retain measured headroom over task 75 output and make future growth explicit.
const budgets = {
  entryJsRaw: 310_000,
  entryJsGzip: 96_000,
  entryCssRaw: 335_000,
  entryCssGzip: 52_500,
  publicAssetsRaw: 850_000,
  largestPublicAssetRaw: 120_000,
};
const failures = [];

function assertBudget(label, actual, maximum) {
  if (actual > maximum) failures.push(`${label}: ${actual} > ${maximum}`);
}

assertBudget("entry JS raw", entryJs.raw, budgets.entryJsRaw);
assertBudget("entry JS gzip", entryJs.gzip, budgets.entryJsGzip);
assertBudget("entry CSS raw", entryCss.raw, budgets.entryCssRaw);
assertBudget("entry CSS gzip", entryCss.gzip, budgets.entryCssGzip);
assertBudget("public assets raw", publicAssets.raw, budgets.publicAssetsRaw);
assertBudget(
  "largest public asset raw",
  publicAssets.largest.bytes,
  budgets.largestPublicAssetRaw,
);

const entrySource = readFileSync(entryJsPath, "utf8");
if (entrySource.includes("WHO Guidelines on Physical Activity")) {
  failures.push("initial JS contains the lazy public content manifest");
}
if (entrySource.includes("fit_demo_sessions_v1")) {
  failures.push("initial JS eagerly contains demo-only session state");
}
if ((entry.css ?? []).some((file) => file.includes("DataViz"))) {
  failures.push(
    "initial CSS eagerly contains the route-scoped DataViz stylesheet",
  );
}

for (const obsoleteAsset of [
  "assets/product/landing-nutrition-desktop-light.png",
  "assets/product/landing-progress-mobile-light.png",
]) {
  if (
    publicFiles.some(
      (file) =>
        relative(publicRoot, file.path).replaceAll("\\", "/") === obsoleteAsset,
    )
  ) {
    failures.push(
      `obsolete unreferenced asset is still shipped: ${obsoleteAsset}`,
    );
  }
}

for (const path of publicFiles
  .filter((file) => file.path.endsWith(".svg"))
  .map((file) => file.path)) {
  const source = readFileSync(path, "utf8");
  if (/<image\b|data:image|(?:href|src)=["']https?:\/\//i.test(source)) {
    failures.push(
      `brand SVG embeds raster data or an external dependency: ${relative(publicRoot, path)}`,
    );
  }
}

const report = {
  budgets,
  entry: {
    js: {
      file: relative(distRoot, entryJsPath).replaceAll("\\", "/"),
      ...entryJs,
    },
    css: { files: entry.css ?? [], ...entryCss },
  },
  publicAssets: {
    count: publicAssets.count,
    raw: publicAssets.raw,
    largest: {
      file: relative(publicRoot, publicAssets.largest.path).replaceAll(
        "\\",
        "/",
      ),
      raw: publicAssets.largest.bytes,
    },
  },
};

console.log(JSON.stringify(report, null, 2));
if (failures.length > 0) {
  throw new Error(
    `Frontend performance budget failed:\n- ${failures.join("\n- ")}`,
  );
}
