import { useEffect, useState } from 'react';
import { resolveExerciseMediaFrame } from './exerciseMediaFraming';

type MediaSource = {
  url: string;
  mime_type: string;
  width: number;
  height?: number;
};

function responsiveSources(sources: MediaSource[], mimeType?: string) {
  return sources
    .filter((source) => !mimeType || source.mime_type === mimeType)
    .slice()
    .sort((left, right) => left.width - right.width)
    .map((source) => `${source.url} ${source.width}w`)
    .join(', ');
}

export function usePrefersReducedMotion(): boolean {
  const [reducedMotion, setReducedMotion] = useState(
    () =>
      typeof window !== 'undefined' &&
      (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false),
  );

  useEffect(() => {
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!query) return undefined;
    const update = () => setReducedMotion(query.matches);
    query.addEventListener?.('change', update);
    return () => query.removeEventListener?.('change', update);
  }, []);

  return reducedMotion;
}

export function ExerciseMediaAsset({
  animationUrl,
  videoSources = [],
  alt,
  className,
  height,
  thumbnailUrl,
  thumbnailSources = [],

  variant,
  width,
}: {
  animationUrl?: string | null;
  videoSources?: MediaSource[];
  alt: string;
  className?: string;
  height?: number;
  thumbnailUrl?: string | null;
  thumbnailSources?: MediaSource[];
  preferredMode?: 'static' | 'animation' | null;
  variant: 'thumbnail' | 'animation';
  width?: number;
}) {
  const reducedMotion = usePrefersReducedMotion();
  const [failed, setFailed] = useState(false);
  const [usePosterFallback, setUsePosterFallback] = useState(false);
  const [videoFailed, setVideoFailed] = useState(false);
  const video =
    variant === 'animation' && !reducedMotion && !videoFailed && videoSources.length > 0;
  // In the full exercise view, motion always takes precedence over an HD poster.
  // When a video fails, preserve the licensed legacy GIF instead of freezing motion.
  const animated =
    variant === 'animation' && !reducedMotion && Boolean(animationUrl) && !usePosterFallback;
  const src = animated ? animationUrl : thumbnailUrl;

  if ((!src && !video) || failed) {
    return (
      <span
        className={
          className ? `${className} exercise-media-asset--missing` : 'exercise-media-asset--missing'
        }
        role={alt ? 'img' : undefined}
        aria-label={alt ? `${alt}. Изображение пока недоступно` : undefined}
        aria-hidden={alt ? undefined : true}
      >
        <span aria-hidden="true">Нет фото</span>
      </span>
    );
  }

  if (video) {
    const selected = [...videoSources].sort((a, b) => a.width - b.width).at(-1);
    const frame = selected
      ? resolveExerciseMediaFrame(selected)
      : resolveExerciseMediaFrame({ url: thumbnailUrl ?? '', width, height });
    return (
      <video
        className={className}
        src={selected?.url}
        poster={thumbnailUrl ?? undefined}
        autoPlay
        muted
        playsInline
        loop
        controls={false}
        preload="metadata"
        aria-label={alt}
        data-media-mode="video"
        onError={() => setVideoFailed(true)}
        data-media-frame={frame.policy}
        data-media-source-ratio={frame.sourceRatio ?? undefined}
        style={{ objectPosition: frame.objectPosition }}
      />
    );
  }
  const posterSources = responsiveSources(thumbnailSources, 'image/jpeg');
  const webpSources = responsiveSources(thumbnailSources, 'image/webp');
  const posterSource = thumbnailSources
    .slice()
    .sort((left, right) => right.width - left.width)
    .at(0);
  const frame = resolveExerciseMediaFrame({
    url: src ?? '',
    width: posterSource?.width ?? width,
    height: posterSource?.height ?? height,
  });
  const image = (
    <img
      className={className}
      src={src ?? undefined}
      srcSet={!animated ? posterSources || undefined : undefined}
      sizes={!animated ? '(max-width: 620px) 58px, 96px' : undefined}
      alt={alt}
      width={width}
      height={height}
      loading={variant === 'thumbnail' ? 'lazy' : undefined}
      decoding="async"
      data-media-mode={animated && !usePosterFallback ? 'animated' : 'static-poster'}
      data-media-frame={frame.policy}
      data-media-source-ratio={frame.sourceRatio ?? undefined}
      style={{ objectPosition: frame.objectPosition }}
      onError={() => {
        if (animated && thumbnailUrl) {
          setUsePosterFallback(true);
          return;
        }
        setFailed(true);
      }}
    />
  );
  return !animated && webpSources ? (
    <picture className="exercise-media-picture">
      <source type="image/webp" srcSet={webpSources} sizes="(max-width: 620px) 58px, 96px" />
      {image}
    </picture>
  ) : (
    image
  );
}
