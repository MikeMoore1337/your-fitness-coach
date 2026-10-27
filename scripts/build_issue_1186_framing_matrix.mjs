import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const issueRoot = join(repoRoot, "docs", "ux-proposals", "issue-1186");
const inventory = JSON.parse(
  readFileSync(join(issueRoot, "media-inventory.json"), "utf8"),
);
const framing = JSON.parse(
  readFileSync(
    join(
      repoRoot,
      "frontend",
      "src",
      "features",
      "exercises",
      "exerciseMediaFraming.json",
    ),
    "utf8",
  ),
);

const wide = (dimensions) =>
  Boolean(
    dimensions?.width &&
    dimensions?.height &&
    Math.abs(dimensions.width - dimensions.height) > 1,
  );

const sourceTypes = (row) => [
  ...(row.media?.type === "animation"
    ? ["gif"]
    : row.media?.type === "image"
      ? ["static"]
      : []),
  ...(row.video_sources.length ? ["mp4"] : []),
];

const rows = inventory.rows.map((row) => {
  const wideVideo = row.video_sources.some((source) => wide(source.dimensions));
  const widePoster = wide(row.poster?.dimensions);
  const widePrimary = wide(row.media?.dimensions);
  const hasWideSource = wideVideo || widePoster || widePrimary;
  const exception = framing.exceptions[row.canonical_slug];
  const override = framing.overrides[row.canonical_slug];
  const approved = row.manifest_status === "approved";
  const policy = !approved
    ? "no-media"
    : !hasWideSource
      ? "native-square"
      : exception
        ? "contain-exception"
        : "cover";
  return {
    canonical_id: row.canonical_id,
    canonical_slug: row.canonical_slug,
    catalog_seed_slugs: row.catalog_seed_slugs,
    manifest_status: row.manifest_status,
    source_types: sourceTypes(row),
    primary_dimensions: row.media?.dimensions ?? null,
    poster_dimensions: row.poster?.dimensions ?? null,
    video_dimensions: row.video_sources.map((source) => source.dimensions),
    surfaces: {
      active_workout: "ExerciseMediaAsset",
      guide: "ExerciseGuideMedia",
      lightbox: "ExerciseGuideMedia lightbox",
      thumbnails: "fixed 52/58px; unchanged",
    },
    policy,
    object_position:
      exception?.object_position ??
      override?.object_position ??
      framing.default_object_position,
    source_ratio_16_9_crop: hasWideSource
      ? "56.25% source width remains in a 1:1 cover"
      : null,
    motion_review: row.video_sources.length
      ? "reviewed start/middle/end in 720p MP4 sweep"
      : row.motion?.animated
        ? "native-square; no crop applied"
        : "static source",
    fallback:
      "MP4 -> licensed GIF -> poster/static -> accessible missing; reduced motion -> static fallback",
    provenance: row.license,
    safe_square: !approved
      ? "EXCEPTION_NO_APPROVED_MEDIA"
      : exception
        ? `EXCEPTION_${row.canonical_slug.toUpperCase().replaceAll("-", "_")}`
        : "PASS",
    review_reason: exception?.reason ?? null,
    review_evidence: exception?.evidence ?? null,
    integrity: row.integrity,
  };
});

const summary = {
  schema_version: 1,
  issue: 1186,
  generated_from:
    "docs/ux-proposals/issue-1186/media-inventory.json + exerciseMediaFraming.json",
  canonical_exercises: rows.length,
  approved: rows.filter((row) => row.manifest_status === "approved").length,
  blocked: rows.filter((row) => row.manifest_status === "blocked").length,
  pass: rows.filter((row) => row.safe_square === "PASS").length,
  issues: rows.filter((row) => row.safe_square === "ISSUE").length,
  exceptions: rows.filter((row) => row.safe_square.startsWith("EXCEPTION_"))
    .length,
  framing_exceptions: rows.filter((row) => row.policy === "contain-exception")
    .length,
  wide_sources: rows.filter((row) => row.source_ratio_16_9_crop !== null)
    .length,
  cover_sources: rows.filter((row) => row.policy === "cover").length,
  native_square_sources: rows.filter((row) => row.policy === "native-square")
    .length,
  contain_exceptions: rows.filter((row) => row.policy === "contain-exception")
    .length,
  no_media_exceptions: rows.filter((row) => row.policy === "no-media").length,
};

if (
  summary.canonical_exercises !== 206 ||
  summary.approved !== 171 ||
  summary.blocked !== 35
) {
  throw new Error(`Unexpected catalog counts: ${JSON.stringify(summary)}`);
}
if (
  summary.wide_sources !== 77 ||
  summary.cover_sources !== 73 ||
  summary.contain_exceptions !== 4
) {
  throw new Error(`Unexpected framing counts: ${JSON.stringify(summary)}`);
}

const output = { summary, rows };
writeFileSync(
  join(issueRoot, "media-framing-matrix.json"),
  `${JSON.stringify(output, null, 2)}\n`,
);
const columns = [
  "canonical_id",
  "canonical_slug",
  "manifest_status",
  "source_types",
  "primary_dimensions",
  "poster_dimensions",
  "video_dimensions",
  "policy",
  "object_position",
  "safe_square",
  "motion_review",
  "review_reason",
  "review_evidence",
];
const csvCell = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
const csv = [
  columns.join(","),
  ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(",")),
];
writeFileSync(
  join(issueRoot, "media-framing-matrix.csv"),
  `${csv.join("\n")}\n`,
);
console.log(JSON.stringify(summary, null, 2));
