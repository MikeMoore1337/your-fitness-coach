import { useEffect, useState } from 'react';

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
  variant,
  width,
}: {
  animationUrl?: string | null;
  alt: string;
  className?: string;
  height?: number;
  thumbnailUrl?: string | null;
  variant: 'thumbnail' | 'animation';
  width?: number;
}) {
  const reducedMotion = usePrefersReducedMotion();
  const [failed, setFailed] = useState(false);
  const animated = variant === 'animation' && !reducedMotion && Boolean(animationUrl);
  const src = animated ? animationUrl : thumbnailUrl;

  if (!src || failed) {
    return (
      <span
        className={
          className ? `${className} exercise-media-asset--missing` : 'exercise-media-asset--missing'
        }
        role="img"
        aria-label={`${alt}. Изображение пока недоступно`}
      >
        <span aria-hidden="true">Нет фото</span>
      </span>
    );
  }

  return (
    <img
      className={className}
      src={src}
      alt={alt}
      width={width}
      height={height}
      loading={variant === 'thumbnail' ? 'lazy' : undefined}
      decoding="async"
      data-media-mode={animated ? 'animated' : 'static-poster'}
      onError={() => setFailed(true)}
    />
  );
}
