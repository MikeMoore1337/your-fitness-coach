import { useState } from 'react';
import type { ExerciseGuide } from '../../shared/api/types';
import { ChevronIcon, CloseIcon } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { usePrefersReducedMotion } from './ExerciseMediaAsset';
import { ExerciseGuideVideo } from './ExerciseGuideVideo';
import { resolveExerciseMediaFrame } from './exerciseMediaFraming';

type GuideMediaItem = ExerciseGuide['media'][number];

const cardSizes = '(max-width: 620px) calc(100vw - 48px), (max-width: 1040px) 44vw, 470px';
const lightboxSizes = '(max-width: 620px) calc(100vw - 24px), min(92vw, 1280px)';

function responsiveSources(sources: GuideMediaItem['sources'], mimeType?: string) {
  return sources
    .slice()
    .filter((source) => !mimeType || source.mime_type === mimeType)
    .sort((left, right) => left.width - right.width)
    .map((source) => `${source.url} ${source.width}w`)
    .join(', ');
}

function MediaPicture({
  src,
  sources,
  sizes,
  alt,
  width,
  height,
  loading,
  mode,
  onError,
}: {
  src: string;
  sources: GuideMediaItem['sources'];
  sizes: string;
  alt: string;
  width: number;
  height: number;
  loading?: 'lazy';
  mode: string;
  onError: () => void;
}) {
  const webp = responsiveSources(sources, 'image/webp');
  const jpeg = responsiveSources(sources, 'image/jpeg');
  const responsive = jpeg || responsiveSources(sources);
  const largest = sources
    .slice()
    .sort(
      (left, right) => right.width - left.width || left.mime_type.localeCompare(right.mime_type),
    )
    .at(0)?.url;
  const frame = resolveExerciseMediaFrame({ url: src, width, height });
  const image = (
    <img
      src={largest ?? src}
      srcSet={responsive || undefined}
      sizes={responsive ? sizes : undefined}
      alt={alt}
      width={width}
      height={height}
      loading={loading}
      decoding="async"
      data-media-mode={mode}
      data-media-frame={frame.policy}
      data-media-source-ratio={frame.sourceRatio ?? undefined}
      style={{ objectPosition: frame.objectPosition }}
      onError={onError}
    />
  );
  return webp ? (
    <picture className="exercise-media-picture">
      <source type="image/webp" srcSet={webp} sizes={sizes} />
      {image}
    </picture>
  ) : (
    image
  );
}

export function ExerciseGuideMedia({
  items,
  onExpandedChange,
}: {
  items: GuideMediaItem[];
  onExpandedChange?: (expanded: boolean) => void;
}) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [posterFallbackUrls, setPosterFallbackUrls] = useState<Set<string>>(() => new Set());
  const [animationFallbackUrls, setAnimationFallbackUrls] = useState<Set<string>>(() => new Set());
  const [failedPosterUrls, setFailedPosterUrls] = useState<Set<string>>(() => new Set());
  const [failedUrls, setFailedUrls] = useState<Set<string>>(() => new Set());
  const [failedVideoUrls, setFailedVideoUrls] = useState<Set<string>>(() => new Set());
  const reducedMotion = usePrefersReducedMotion();
  const close = () => {
    setExpandedIndex(null);
    onExpandedChange?.(false);
  };
  const lightboxRef = useModalA11y<HTMLDivElement>(expandedIndex !== null, close);
  const activeItem = expandedIndex === null ? null : items[expandedIndex];
  const activeItemUsesVideo = Boolean(
    activeItem?.video_sources?.length && !reducedMotion && !failedVideoUrls.has(activeItem.url),
  );
  const activeItemUsesPoster = Boolean(
    activeItem?.type === 'animation' &&
    !failedPosterUrls.has(activeItem.url) &&
    (reducedMotion ||
      posterFallbackUrls.has(activeItem.url) ||
      (activeItem.poster_preferred &&
        !animationFallbackUrls.has(activeItem.url) &&
        !failedVideoUrls.has(activeItem.url))),
  );
  const activeItemDisplayUrl = activeItem
    ? activeItemUsesPoster
      ? activeItem.poster
      : activeItem.type === 'animation'
        ? activeItem.url
        : activeItem.url
    : null;
  const activeItemSources = activeItem
    ? activeItemUsesPoster
      ? (activeItem.poster_sources ?? [])
      : activeItem.type === 'image'
        ? activeItem.sources
        : []
    : [];
  const availableItemsCount = items.filter((item) => !failedUrls.has(item.url)).length;
  const hasStrengthPhases = items.some(
    (item) => item.phase_id === 'concentric_end' || item.phase_id === 'eccentric_end',
  );

  const showAdjacent = (direction: -1 | 1) => {
    if (expandedIndex === null) return;
    for (let offset = 1; offset < items.length; offset += 1) {
      const nextIndex = (expandedIndex + direction * offset + items.length) % items.length;
      const nextItem = items[nextIndex];
      if (nextItem && !failedUrls.has(nextItem.url)) {
        setExpandedIndex(nextIndex);
        return;
      }
    }
    close();
  };

  const markImageError = (item: GuideMediaItem, sourceUrl: string) => {
    if (item.type === 'animation' && sourceUrl === item.poster) {
      if (!reducedMotion && item.url !== item.poster && !failedPosterUrls.has(item.url)) {
        setFailedPosterUrls((current) => new Set(current).add(item.url));
        setAnimationFallbackUrls((current) => new Set(current).add(item.url));
        return;
      }
      setFailedUrls((current) => new Set(current).add(item.url));
      if (activeItem?.url === item.url) close();
      return;
    }
    if (item.type === 'animation' && !failedPosterUrls.has(item.url)) {
      setPosterFallbackUrls((current) => new Set(current).add(item.url));
      return;
    }
    const url = item.url;
    setFailedUrls((current) => new Set(current).add(url));
    if (activeItem?.url === url) close();
  };

  return (
    <>
      {hasStrengthPhases && (
        <p className="exercise-guide-images__legend">
          Изображение показывает положение в конце движения. <strong>Фаза усилия</strong>{' '}
          (концентрическая) — преодоление нагрузки. <strong>Фаза возврата</strong> (эксцентрическая)
          — контролируемое обратное движение.
        </p>
      )}
      <div className="exercise-guide-images" aria-label="Положения упражнения">
        {items.map((item, index) => {
          const failed = failedUrls.has(item.url);
          const showPoster =
            item.type === 'animation' &&
            !failedPosterUrls.has(item.url) &&
            (reducedMotion ||
              posterFallbackUrls.has(item.url) ||
              (item.poster_preferred &&
                !animationFallbackUrls.has(item.url) &&
                !failedVideoUrls.has(item.url)));
          const displayUrl = showPoster ? item.poster : item.url;
          const displaySources = showPoster
            ? (item.poster_sources ?? [])
            : item.type === 'image'
              ? item.sources
              : [];
          const useVideo = Boolean(
            item.video_sources?.length && !reducedMotion && !failedVideoUrls.has(item.url),
          );
          return (
            <figure className="exercise-guide-image" key={item.asset_id ?? item.url}>
              {failed ? (
                <div
                  className="exercise-guide-image__frame exercise-guide-image__fallback"
                  role="img"
                  aria-label={item.alt}
                >
                  <span aria-hidden="true">Изображение недоступно</span>
                </div>
              ) : (
                <button
                  className="exercise-guide-image__frame"
                  type="button"
                  aria-label={`Увеличить: ${item.phase}`}
                  onClick={() => {
                    setExpandedIndex(index);
                    onExpandedChange?.(true);
                  }}
                >
                  {useVideo ? (
                    <ExerciseGuideVideo
                      sources={item.video_sources ?? []}
                      poster={item.poster}
                      onError={() =>
                        setFailedVideoUrls((current) => new Set(current).add(item.url))
                      }
                    />
                  ) : (
                    <MediaPicture
                      src={displayUrl}
                      sources={displaySources}
                      sizes={cardSizes}
                      alt={item.alt}
                      width={showPoster ? (item.poster_width ?? item.width) : item.width}
                      height={showPoster ? (item.poster_height ?? item.height) : item.height}
                      loading="lazy"
                      mode={showPoster ? 'static-poster' : item.type}
                      onError={() => markImageError(item, displayUrl)}
                    />
                  )}
                  <span className="exercise-guide-image__zoom" aria-hidden="true">
                    <Icon name="maximize" size={16} />
                  </span>
                </button>
              )}
              <figcaption>{item.phase}</figcaption>
            </figure>
          );
        })}
      </div>
      {activeItem && !failedUrls.has(activeItem.url) && (
        <div
          className="exercise-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label={`Увеличенное изображение: ${activeItem.phase}`}
          ref={lightboxRef}
          tabIndex={-1}
        >
          <button
            type="button"
            className="exercise-lightbox__backdrop"
            aria-label="Закрыть увеличенное изображение"
            onClick={close}
          />
          <button
            type="button"
            className="exercise-lightbox__close"
            aria-label="Закрыть"
            onClick={close}
          >
            <CloseIcon />
          </button>
          {availableItemsCount > 1 && (
            <button
              type="button"
              className="exercise-lightbox__arrow exercise-lightbox__arrow--prev"
              aria-label="Предыдущее изображение"
              onClick={() => showAdjacent(-1)}
            >
              <ChevronIcon direction="left" />
            </button>
          )}
          <figure>
            <div className="exercise-lightbox__media">
              {activeItemUsesVideo ? (
                <ExerciseGuideVideo
                  sources={activeItem.video_sources ?? []}
                  poster={activeItem.poster}
                  expanded
                  onError={() =>
                    setFailedVideoUrls((current) => new Set(current).add(activeItem.url))
                  }
                />
              ) : (
                <MediaPicture
                  src={activeItemDisplayUrl ?? ''}
                  sources={activeItemSources}
                  sizes={lightboxSizes}
                  alt={activeItem.alt}
                  width={
                    activeItemUsesPoster
                      ? (activeItem.poster_width ?? activeItem.width)
                      : activeItem.width
                  }
                  height={
                    activeItemUsesPoster
                      ? (activeItem.poster_height ?? activeItem.height)
                      : activeItem.height
                  }
                  mode={activeItemUsesPoster ? 'static-poster' : activeItem.type}
                  onError={() => markImageError(activeItem, activeItemDisplayUrl ?? '')}
                />
              )}
            </div>
            <figcaption>{activeItem.phase}</figcaption>
          </figure>
          {availableItemsCount > 1 && (
            <button
              type="button"
              className="exercise-lightbox__arrow exercise-lightbox__arrow--next"
              aria-label="Следующее изображение"
              onClick={() => showAdjacent(1)}
            >
              <ChevronIcon />
            </button>
          )}
        </div>
      )}
    </>
  );
}
