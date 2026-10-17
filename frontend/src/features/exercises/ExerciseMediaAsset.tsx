import { useEffect, useState } from 'react';

type MediaSource = {
  url: string;
  mime_type: string;
  width: number;
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
  alt,
  className,
  height,
  thumbnailUrl,
  thumbnailSources = [],
  preferredMode,
  variant,
  width,
}: {
  animationUrl?: string | null;
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
  const [useAnimationFallback, setUseAnimationFallback] = useState(false);
  const animated =
    variant === 'animation' &&
    !reducedMotion &&
    Boolean(animationUrl) &&
    !usePosterFallback &&
    (preferredMode !== 'static' || useAnimationFallback);
  const src = animated ? animationUrl : thumbnailUrl;

  if (!src || failed) {
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

  const posterSources = responsiveSources(thumbnailSources, 'image/jpeg');
  const webpSources = responsiveSources(thumbnailSources, 'image/webp');
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
      onError={() => {
        if (animated && thumbnailUrl) {
          setUsePosterFallback(true);
          return;
        }
        if (!animated && animationUrl && preferredMode === 'static' && !reducedMotion) {
          setUseAnimationFallback(true);
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
