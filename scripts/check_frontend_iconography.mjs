import { readFile } from "node:fs/promises";
import { glob } from "node:fs/promises";

const sourceRoot = new URL("../frontend/src/", import.meta.url);
const allowedInlineSvgFiles = new Set([
  "features/auth/OAuthButtons.tsx",
  "shared/ui/DataViz.tsx",
  "shared/ui/Icon.tsx",
  "shared/ui/iconGlyphs.tsx",
]);
const uiUnicodePattern = /[✓⛶✅❌⚠️ℹ️✕✖]/u;
const failures = [];

for await (const entry of glob("**/*.{ts,tsx}", { cwd: sourceRoot })) {
  const relativePath = entry.replaceAll("\\", "/");
  const content = await readFile(new URL(relativePath, sourceRoot), "utf8");
  if (
    uiUnicodePattern.test(content) &&
    relativePath !== "shared/account/AccountIdentity.tsx"
  ) {
    failures.push(
      `${relativePath}: UI icon-like Unicode character; use the shared Icon registry`,
    );
  }
  if (content.includes("<svg") && !allowedInlineSvgFiles.has(relativePath)) {
    failures.push(
      `${relativePath}: inline SVG outside the approved icon/brand/data-viz boundary`,
    );
  }
}

if (failures.length) {
  console.error(failures.join("\n"));
  process.exitCode = 1;
} else {
  console.log("Frontend iconography guard passed");
}
