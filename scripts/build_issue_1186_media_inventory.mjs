import { createHash } from 'node:crypto';
import { existsSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const assetRoot = join(repoRoot, 'backend', 'assets', 'exercise-guides');
const outputRoot = join(repoRoot, 'docs', 'ux-proposals', 'issue-1186');
const catalogPath = join(repoRoot, 'backend', 'fitminiapp_api', 'services', 'program_seed_data.py');
const metadataPath = join(
  repoRoot,
  'backend',
  'fitminiapp_api',
  'services',
  'exercise_catalog_metadata.py',
);
const manifestPath = join(assetRoot, 'manifest.json');

const catalogSource = readFileSync(catalogPath, 'utf8');
const catalogStart = catalogSource.indexOf('EXERCISE_CATALOG:');
const catalogEnd = catalogSource.indexOf('PPLF_4_DAYS:', catalogStart);
if (catalogStart < 0 || catalogEnd < 0) {
  throw new Error('Could not locate EXERCISE_CATALOG boundaries');
}
const catalogBlock = catalogSource.slice(catalogStart, catalogEnd);
const catalogEntries = [...catalogBlock.matchAll(/\(\s*"([^"]+)"\s*,\s*"([^"]+)"/g)].map(
  ([, slug, title]) => ({ slug, title }),
);

const metadataSource = readFileSync(metadataPath, 'utf8');
const redirectStart = metadataSource.indexOf('CANONICAL_EXERCISE_REDIRECTS = {');
const redirectEnd = metadataSource.indexOf('\n}', redirectStart);
const redirectBlock = metadataSource.slice(redirectStart, redirectEnd + 2);
const redirects = Object.fromEntries(
  [...redirectBlock.matchAll(/"([^"]+)"\s*:\s*"([^"]+)"/g)].map(([, from, to]) => [from, to]),
);

const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
const manifestExercises = manifest.exercises ?? {};
const manifestSlugs = Object.keys(manifestExercises);
const canonicalCatalog = new Map();
for (const entry of catalogEntries) {
  const canonicalSlug = redirects[entry.slug] ?? entry.slug;
  const aliases = canonicalCatalog.get(canonicalSlug) ?? [];
  aliases.push(entry);
  canonicalCatalog.set(canonicalSlug, aliases);
}

const hashCache = new Map();
function fileHash(path) {
  if (hashCache.has(path)) return hashCache.get(path);
  const hash = createHash('sha256').update(readFileSync(path)).digest('hex');
  hashCache.set(path, hash);
  return hash;
}

function inspectImageDimensions(path, mimeType) {
  const bytes = readFileSync(path);
  if (mimeType === 'image/gif' && bytes.toString('ascii', 0, 6) === 'GIF89a') {
    return { width: bytes.readUInt16LE(6), height: bytes.readUInt16LE(8), decoder: 'gif-header' };
  }
  if (mimeType === 'image/gif' && bytes.toString('ascii', 0, 6) === 'GIF87a') {
    return { width: bytes.readUInt16LE(6), height: bytes.readUInt16LE(8), decoder: 'gif-header' };
  }
  if (mimeType === 'image/jpeg' && bytes[0] === 0xff && bytes[1] === 0xd8) {
    let offset = 2;
    while (offset + 9 < bytes.length) {
      if (bytes[offset] !== 0xff) {
        offset += 1;
        continue;
      }
      const marker = bytes[offset + 1];
      offset += 2;
      if (marker === 0xd8 || marker === 0xd9) continue;
      if (offset + 2 > bytes.length) break;
      const length = bytes.readUInt16BE(offset);
      const isSof =
        (marker >= 0xc0 && marker <= 0xc3) ||
        (marker >= 0xc5 && marker <= 0xc7) ||
        (marker >= 0xc9 && marker <= 0xcb) ||
        (marker >= 0xcd && marker <= 0xcf);
      if (isSof && offset + 7 <= bytes.length) {
        return {
          width: bytes.readUInt16BE(offset + 5),
          height: bytes.readUInt16BE(offset + 3),
          decoder: 'jpeg-sof',
        };
      }
      if (length < 2) break;
      offset += length;
    }
  }
  if (
    mimeType === 'image/webp' &&
    bytes.toString('ascii', 0, 4) === 'RIFF' &&
    bytes.toString('ascii', 8, 12) === 'WEBP'
  ) {
    const chunk = bytes.toString('ascii', 12, 16);
    if (chunk === 'VP8X' && bytes.length >= 30) {
      return {
        width: 1 + bytes[24] + (bytes[25] << 8) + (bytes[26] << 16),
        height: 1 + bytes[27] + (bytes[28] << 8) + (bytes[29] << 16),
        decoder: 'webp-vp8x',
      };
    }
  }
  return null;
}

function dimensions(width, height) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || height === 0) return null;
  return {
    width,
    height,
    ratio: Number((width / height).toFixed(4)),
  };
}

const fileCache = new Map();
function inspectFile({ path, kind, mimeType, declared, expectedSha256, expectedBytes }) {
  const relativePath = path.replaceAll('\\', '/');
  const absolutePath = join(assetRoot, ...relativePath.split('/'));
  const cached = fileCache.get(relativePath);
  if (!existsSync(absolutePath)) {
    const missing = {
      path: relativePath,
      kind,
      mime_type: mimeType ?? null,
      declared_dimensions: declared ?? null,
      actual_dimensions: null,
      declared_bytes: expectedBytes ?? null,
      actual_bytes: null,
      exists: false,
      size_matches: false,
      sha256: null,
      sha256_matches: expectedSha256 ? false : null,
      dimension_check: 'MISSING',
    };
    fileCache.set(relativePath, missing);
    return missing;
  }
  const stat = statSync(absolutePath);
  const actualSha256 = cached?.sha256 ?? fileHash(absolutePath);
  const actualDimensions =
    cached?.actual_dimensions ?? inspectImageDimensions(absolutePath, mimeType);
  const result = {
    path: relativePath,
    kind,
    mime_type: mimeType ?? null,
    declared_dimensions: declared ?? null,
    actual_dimensions: actualDimensions,
    declared_bytes: expectedBytes ?? null,
    actual_bytes: stat.size,
    exists: true,
    size_matches: expectedBytes == null ? null : stat.size === expectedBytes,
    sha256: actualSha256,
    sha256_matches: expectedSha256 ? actualSha256 === expectedSha256 : null,
    dimension_check:
      declared && actualDimensions
        ? declared.width === actualDimensions.width && declared.height === actualDimensions.height
          ? 'PASS'
          : 'FAIL'
        : declared
          ? 'NOT_CHECKED_NO_IMAGE_HEADER'
          : 'NO_DECLARED_DIMENSIONS',
  };
  fileCache.set(relativePath, result);
  return result;
}

function mediaFileDescriptors(media) {
  const files = new Map();
  const add = (source, kind, fallbackExpectedSha256) => {
    if (!source?.path) return;
    const key = source.path.replaceAll('\\', '/');
    if (files.has(key)) return;
    files.set(key, {
      path: key,
      kind,
      mime_type: source.mime_type ?? null,
      declared: dimensions(source.width, source.height),
      expectedBytes: source.byte_size ?? null,
      expectedSha256: source.sha256 ?? fallbackExpectedSha256 ?? null,
    });
  };
  add(
    {
      path: media.path,
      mime_type: media.type === 'animation' ? 'image/gif' : 'image/jpeg',
      width: media.width,
      height: media.height,
      byte_size: media.byte_size,
    },
    media.type === 'animation' ? 'primary-gif' : 'primary-image',
    media.asset_sha256,
  );
  add(
    {
      path: media.poster_path,
      mime_type: 'image/jpeg',
      width: media.poster_dimensions?.width,
      height: media.poster_dimensions?.height,
      byte_size: media.poster_byte_size,
    },
    'poster-primary',
    media.poster_sha256,
  );
  for (const source of media.sources ?? []) add(source, 'primary-source', source.sha256);
  for (const source of media.poster_sources ?? []) add(source, 'poster-source', source.sha256);
  for (const source of media.video_sources ?? []) add(source, 'video-source', source.sha256);
  return [...files.values()].map(inspectFile);
}

function sourceList(media, key) {
  return (media?.[key] ?? []).map((source) => ({
    path: source.path,
    mime_type: source.mime_type,
    dimensions: dimensions(source.width, source.height),
    byte_size: source.byte_size,
    sha256: source.sha256 ?? null,
  }));
}

function compactProvenance(source) {
  if (!source) return null;
  return {
    name: source.name ?? null,
    url: source.url ?? null,
    source_revision: source.source_revision ?? null,
    source_path: source.source_path ?? null,
    source_slug: source.source_slug ?? null,
    rights_basis: source.rights_basis ?? null,
    transformation: source.transformation ?? null,
    source_sha256: source.source_sha256 ?? null,
    source_git_blob_sha1: source.git_blob_sha1 ?? source.source_git_blob_sha1 ?? null,
  };
}

function primaryAssessment(media) {
  if (!media) {
    return {
      current_1to1: 'EXCEPTION_NO_APPROVED_MEDIA',
      safe_square: 'EXCEPTION_SOURCE_GAP',
      current_issue: 'Нет одобренного source-backed media; нужен отдельный source/visual review.',
    };
  }
  const widePoster =
    media.poster_dimensions && media.poster_dimensions.width !== media.poster_dimensions.height;
  const widePrimary = media.width !== media.height;
  if (widePoster || widePrimary) {
    return {
      current_1to1: 'ISSUE_WIDE_POSTER_OR_STATIC_SURFACE',
      safe_square: 'PASS_WITH_CONTAIN_NO_CROP',
      current_issue:
        '16:9 source безопасен только в квадратной поверхности с contain; текущий picture fallback разрешает intrinsic height.',
    };
  }
  return {
    current_1to1: 'PASS_NATIVE_SQUARE_SOURCE',
    safe_square: 'PASS_NATIVE_SQUARE_OR_CONTAIN',
    current_issue: null,
  };
}

function buildRow(canonicalSlug, aliases) {
  const entry = manifestExercises[canonicalSlug];
  const media = entry?.media?.[0] ?? null;
  const assessment = primaryAssessment(media);
  const files = media ? mediaFileDescriptors(media) : [];
  const videoSources = sourceList(media, 'video_sources');
  const posterSources = sourceList(media, 'poster_sources');
  const primarySources = sourceList(media, 'sources');
  const primaryDimensions = media ? dimensions(media.width, media.height) : null;
  const posterDimensions = media?.poster_dimensions
    ? dimensions(media.poster_dimensions.width, media.poster_dimensions.height)
    : null;
  const videoDimensions = videoSources.map((source) => source.dimensions);
  const animation = media?.type === 'animation';
  return {
    canonical_id: canonicalSlug,
    canonical_slug: canonicalSlug,
    catalog_seed_slugs: aliases.map((alias) => alias.slug),
    catalog_titles: aliases.map((alias) => alias.title),
    manifest_status: entry?.status ?? 'NOT_IN_MANIFEST',
    blocked_reason: entry?.blocked_reason ?? null,
    primary_source_type: media?.type ?? 'none',
    primary_path: media?.path ?? null,
    primary_sha256: media?.asset_sha256 ?? null,
    primary_dimensions: primaryDimensions,
    primary_ratio: primaryDimensions?.ratio ?? null,
    primary_sources: primarySources,
    poster_path: media?.poster_path ?? null,
    poster_sha256: media?.poster_sha256 ?? null,
    poster_dimensions: posterDimensions,
    poster_ratio: posterDimensions?.ratio ?? null,
    poster_preferred: media?.poster_preferred ?? null,
    poster_sources: posterSources,
    mp4_sources: videoSources,
    license: entry?.source
      ? {
          name: entry.source.name,
          license: entry.source.license,
          license_url: entry.source.license_url ?? null,
          source_url: entry.source.url,
          source_revision: entry.source.source_revision ?? null,
          rights_basis: entry.source.rights_basis ?? null,
        }
      : null,
    source_variants: {
      poster: compactProvenance(media?.poster_source),
      video: compactProvenance(media?.video_provenance),
    },
    motion: media
      ? {
          animated: Boolean(media.animated || videoSources.length),
          gif_frame_count: media.frame_count ?? null,
          gif_duration_ms: media.duration_ms ?? null,
          mp4_source_count: videoSources.length,
          preservation_check:
            animation || videoSources.length
              ? 'NOT_PROVEN_SEMANTICALLY; manifest metadata and source integrity checked; first/middle/end visual review is a separate evidence step'
              : 'NOT_APPLICABLE_STATIC_ONLY',
        }
      : null,
    asset_integrity: {
      file_count: files.length,
      all_files_present: files.every((file) => file.exists),
      all_declared_sizes_match: files.every((file) => file.size_matches !== false),
      all_declared_hashes_match: files.every((file) => file.sha256_matches !== false),
      image_header_dimensions_match: files
        .filter((file) => file.mime_type?.startsWith('image/'))
        .every((file) => file.dimension_check === 'PASS'),
    },
    current_geometry: assessment,
    review_exception: media ? null : entry?.blocked_reason ?? 'Manifest gap',
  };
}

const rows = [...canonicalCatalog.entries()]
  .sort(([left], [right]) => left.localeCompare(right))
  .map(([canonicalSlug, aliases]) => buildRow(canonicalSlug, aliases));

const catalogSlugs = [...canonicalCatalog.keys()].sort();
const catalogNotManifest = catalogSlugs.filter((slug) => !manifestExercises[slug]);
const manifestNotCatalog = manifestSlugs.filter((slug) => !canonicalCatalog.has(slug)).sort();
const uniqueFiles = new Map(fileCache);
const approvedRows = rows.filter((row) => row.manifest_status === 'approved');
const wideRows = rows.filter((row) => row.current_geometry.current_1to1 === 'ISSUE_WIDE_POSTER_OR_STATIC_SURFACE');
const blockedRows = rows.filter((row) => row.manifest_status === 'blocked');

const summary = {
  generated_from: {
    catalog: 'backend/fitminiapp_api/services/program_seed_data.py::EXERCISE_CATALOG',
    redirects: 'backend/fitminiapp_api/services/exercise_catalog_metadata.py::CANONICAL_EXERCISE_REDIRECTS',
    manifest: 'backend/assets/exercise-guides/manifest.json',
    source_revision: manifest.source_revision ?? null,
  },
  catalog_seed_records: catalogEntries.length,
  canonical_exercises: rows.length,
  manifest_exercises: manifestSlugs.length,
  catalog_not_manifest: catalogNotManifest,
  manifest_not_catalog: manifestNotCatalog,
  manifest_status: {
    approved: approvedRows.length,
    blocked: blockedRows.length,
  },
  primary_source_type: rows.reduce((counts, row) => {
    counts[row.primary_source_type] = (counts[row.primary_source_type] ?? 0) + 1;
    return counts;
  }, {}),
  primary_ratio: rows.reduce((counts, row) => {
    const key = row.primary_ratio == null ? 'none' : String(row.primary_ratio);
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {}),
  poster_dimensions: rows.reduce((counts, row) => {
    const key = row.poster_dimensions
      ? `${row.poster_dimensions.width}x${row.poster_dimensions.height}`
      : 'none';
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {}),
  animated_exercises: rows.filter((row) => row.motion?.animated).length,
  gif_source_count: rows.reduce(
    (count, row) =>
      count + row.primary_sources.filter((source) => source.mime_type === 'image/gif').length,
    0,
  ),
  mp4_exercises: rows.filter((row) => row.mp4_sources.length > 0).length,
  mp4_source_count: rows.reduce((count, row) => count + row.mp4_sources.length, 0),
  current_geometry: {
    pass_native_square: rows.filter((row) => row.current_geometry.current_1to1 === 'PASS_NATIVE_SQUARE_SOURCE').length,
    issue_wide_poster_or_static: wideRows.length,
    exceptions_no_media: blockedRows.length,
    safe_square_with_contain: approvedRows.length,
  },
  file_integrity: {
    unique_manifest_files: uniqueFiles.size,
    present: [...uniqueFiles.values()].filter((file) => file.exists).length,
    missing: [...uniqueFiles.values()].filter((file) => !file.exists).length,
    size_mismatches: [...uniqueFiles.values()].filter((file) => file.size_matches === false).length,
    hash_mismatches: [...uniqueFiles.values()].filter((file) => file.sha256_matches === false).length,
    image_header_dimension_mismatches: [...uniqueFiles.values()].filter(
      (file) => file.dimension_check === 'FAIL',
    ).length,
  },
  visual_motion_review: {
    first_middle_end_semantic_check: 'NOT_PROVEN_BY_INVENTORY; use the prototype evidence for owner review',
    ffprobe_available: false,
    note: 'No ffprobe executable was available in the worktree environment; MP4 dimensions remain manifest-declared and file-integrity checked.',
  },
  surface_contract: {
    active_workout_main:
      'ExerciseMediaAsset variant=animation; video -> original GIF -> poster -> missing placeholder',
    exercise_guide_card: 'ExerciseGuideMedia card; video/GIF/poster; inline source aspect ratio',
    exercise_guide_lightbox: 'ExerciseGuideMedia lightbox; largest video/source; poster on reduced motion',
    catalog_and_picker_thumbnails:
      'ExerciseCatalog/SearchableExercisePicker variant=thumbnail; fixed 52/58 px surfaces',
    public_guide: 'PublicContentPage -> ExerciseGuideMedia',
  },
  fallback_policy:
    'Playback/error: retain licensed GIF when available; reduced motion: poster/static; image failure: accessible missing state; blocked: no-media state',
};

if (
  summary.file_integrity.missing > 0 ||
  summary.file_integrity.size_mismatches > 0 ||
  summary.file_integrity.hash_mismatches > 0 ||
  summary.file_integrity.image_header_dimension_mismatches > 0
) {
  throw new Error(`Manifest integrity check failed: ${JSON.stringify(summary.file_integrity)}`);
}

const csvColumns = [
  'canonical_id',
  'canonical_slug',
  'catalog_seed_slugs',
  'catalog_titles',
  'manifest_status',
  'blocked_reason',
  'primary_source_type',
  'primary_path',
  'primary_sha256',
  'primary_dimensions',
  'primary_ratio',
  'gif_sources',
  'poster_path',
  'poster_sha256',
  'poster_dimensions',
  'poster_ratio',
  'poster_preferred',
  'mp4_sources',
  'active_workout_surface',
  'guide_surface',
  'thumbnail_surface',
  'fallback_policy',
  'source_name',
  'source_url',
  'source_revision',
  'license',
  'rights_basis',
  'motion_metadata',
  'motion_preservation_check',
  'current_1to1_status',
  'safe_square_assessment',
  'review_exception',
  'all_files_present',
  'all_declared_sizes_match',
  'all_declared_hashes_match',
  'image_header_dimensions_match',
];

const csvValue = (value) => {
  const text = value == null ? '' : typeof value === 'string' ? value : JSON.stringify(value);
  return `"${text.replaceAll('"', '""')}"`;
};
const csvRows = rows.map((row) => {
  const source = row.license;
  const values = {
    canonical_id: row.canonical_id,
    canonical_slug: row.canonical_slug,
    catalog_seed_slugs: row.catalog_seed_slugs,
    catalog_titles: row.catalog_titles,
    manifest_status: row.manifest_status,
    blocked_reason: row.blocked_reason,
    primary_source_type: row.primary_source_type,
    primary_path: row.primary_path,
    primary_sha256: row.primary_sha256,
    primary_dimensions: row.primary_dimensions,
    primary_ratio: row.primary_ratio,
    gif_sources: row.primary_sources.filter((source) => source.mime_type === 'image/gif'),
    poster_path: row.poster_path,
    poster_sha256: row.poster_sha256,
    poster_dimensions: row.poster_dimensions,
    poster_ratio: row.poster_ratio,
    poster_preferred: row.poster_preferred,
    mp4_sources: row.mp4_sources,
    active_workout_surface: summary.surface_contract.active_workout_main,
    guide_surface: summary.surface_contract.exercise_guide_card,
    thumbnail_surface: summary.surface_contract.catalog_and_picker_thumbnails,
    fallback_policy: summary.fallback_policy,
    source_name: source?.name,
    source_url: source?.source_url,
    source_revision: source?.source_revision,
    license: source?.license,
    rights_basis: source?.rights_basis,
    motion_metadata: row.motion,
    motion_preservation_check: row.motion?.preservation_check,
    current_1to1_status: row.current_geometry.current_1to1,
    safe_square_assessment: row.current_geometry.safe_square,
    review_exception: row.review_exception,
    all_files_present: row.asset_integrity.all_files_present,
    all_declared_sizes_match: row.asset_integrity.all_declared_sizes_match,
    all_declared_hashes_match: row.asset_integrity.all_declared_hashes_match,
    image_header_dimensions_match: row.asset_integrity.image_header_dimensions_match,
  };
  return csvColumns.map((column) => csvValue(values[column])).join(',');
});

const compactSources = (sources) =>
  sources.map((source) => ({
    path: source.path,
    mime_type: source.mime_type,
    dimensions: source.dimensions,
  }));

const compactRows = rows.map((row) => ({
  canonical_slug: row.canonical_slug,
  catalog_seed_slugs: row.catalog_seed_slugs,
  catalog_titles: row.catalog_titles,
  manifest_status: row.manifest_status,
  blocked_reason: row.blocked_reason,
  media: {
    type: row.primary_source_type,
    path: row.primary_path,
    sha256: row.primary_sha256,
    dimensions: row.primary_dimensions,
    sources: compactSources(row.primary_sources),
  },
  poster: {
    path: row.poster_path,
    sha256: row.poster_sha256,
    dimensions: row.poster_dimensions,
    preferred: row.poster_preferred,
    sources: compactSources(row.poster_sources),
  },
  video_sources: compactSources(row.mp4_sources),
  license: row.license,
  source_variants: row.source_variants,
  motion: row.motion,
  geometry: row.current_geometry,
  integrity: row.asset_integrity,
}));

const fileChecks = Object.fromEntries(
  [...uniqueFiles.entries()].map(([path, file]) => [
    path,
    {
      kind: file.kind,
      mime_type: file.mime_type,
      declared_dimensions: file.declared_dimensions,
      exists: file.exists,
      size_matches: file.size_matches,
      sha256_matches: file.sha256_matches,
      dimension_check: file.dimension_check,
    },
  ]),
);

const jsonOutput = {
  schema_version: 1,
  issue: 1186,
  file_checks: 'media-file-checks.json',
  summary,
  rows: compactRows,
};
writeFileSync(join(outputRoot, 'media-inventory.json'), `${JSON.stringify(jsonOutput)}\n`);
writeFileSync(
  join(outputRoot, 'media-file-checks.json'),
  `${JSON.stringify({ schema_version: 1, issue: 1186, file_checks: fileChecks }, null, 2)}\n`,
);
writeFileSync(join(outputRoot, 'media-inventory.csv'), `${csvColumns.join(',')}\n${csvRows.join('\n')}\n`);
console.log(
  JSON.stringify(
    {
      output: 'docs/ux-proposals/issue-1186/media-inventory.{json,csv}',
      catalog_seed_records: summary.catalog_seed_records,
      canonical_exercises: summary.canonical_exercises,
      approved: summary.manifest_status.approved,
      blocked: summary.manifest_status.blocked,
      wide_poster_or_static_issue: summary.current_geometry.issue_wide_poster_or_static,
      mp4_source_count: summary.mp4_source_count,
      missing_files: summary.file_integrity.missing,
      hash_mismatches: summary.file_integrity.hash_mismatches,
    },
    null,
    2,
  ),
);
