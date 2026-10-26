import framingConfig from './exerciseMediaFraming.json';

type MediaFramePolicy = 'native-square' | 'filled-square' | 'contain-exception';

type FramingOverride = {
  object_position?: string;
  reason: string;
};

const overrides = framingConfig.overrides as Record<string, FramingOverride>;
const exceptions = framingConfig.exceptions as Record<
  string,
  FramingOverride & { strategy: string }
>;

function exerciseSlugFromUrl(url: string): string | null {
  try {
    const path = new URL(url, 'https://yfc.local').pathname;
    const exercisesMediaMatch = path.match(/(?:^|\/)exercises-media\/(?!videos\/)([^/]+)\//);
    if (exercisesMediaMatch?.[1]) return exercisesMediaMatch[1];
    const fileName =
      path
        .split('/')
        .at(-1)
        ?.replace(/\.[^.]+$/, '') ?? '';
    const videoSlug = fileName.match(/^(.+?)-(?:480p|720p)-h264$/);
    if (videoSlug?.[1]) return videoSlug[1];
    return fileName.replace(/-\d{4}-[A-Za-z0-9]+$/, '') || null;
  } catch {
    return null;
  }
}

export function resolveExerciseMediaFrame({
  url,
  width,
  height,
}: {
  url: string;
  width?: number | null;
  height?: number | null;
}): {
  policy: MediaFramePolicy;
  objectPosition: string;
  sourceRatio: number | null;
  slug: string | null;
} {
  // Approved GIF media is 180×180 in the current manifest; workout preview dimensions describe
  // its poster and must not make the original square animation look wide.
  const isNativeGif = /\.gif(?:$|[?#])/i.test(url);
  const sourceRatio = isNativeGif
    ? 1
    : width && height && width > 0 && height > 0
      ? Number((width / height).toFixed(4))
      : null;
  const slug = exerciseSlugFromUrl(url);
  if (isNativeGif || !sourceRatio || Math.abs(width! - height!) <= 1) {
    return {
      policy: 'native-square',
      objectPosition: '50% 50%',
      sourceRatio,
      slug,
    };
  }

  const exception = slug ? exceptions[slug] : undefined;
  if (exception?.strategy === 'contain-exception') {
    return {
      policy: 'contain-exception',
      objectPosition: '50% 50%',
      sourceRatio,
      slug,
    };
  }

  return {
    policy: 'filled-square',
    objectPosition:
      (slug ? overrides[slug]?.object_position : undefined) ??
      framingConfig.default_object_position,
    sourceRatio,
    slug,
  };
}
