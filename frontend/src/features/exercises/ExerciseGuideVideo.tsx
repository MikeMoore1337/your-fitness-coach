import { useEffect, useRef, useState } from 'react';

type VideoSource = {
  url: string;
  mime_type: string;
  width: number;
  height: number;
  byte_size: number;
};

export function ExerciseGuideVideo({
  sources,
  poster,
  expanded = false,
  onError,
}: {
  sources: VideoSource[];
  poster: string;
  expanded?: boolean;
  onError: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [visible, setVisible] = useState(expanded);

  useEffect(() => {
    const node = videoRef.current;
    if (!node) return;
    let inViewport = expanded || typeof IntersectionObserver === 'undefined';
    const syncPlayback = () => {
      if (document.hidden || !inViewport) {
        node.pause();
      } else if (node.getAttribute('src')) {
        void node.play().catch(() => undefined);
      }
    };
    const observer =
      expanded || typeof IntersectionObserver === 'undefined'
        ? null
        : new IntersectionObserver(
            (entries) => {
              inViewport = entries.some((entry) => entry.isIntersecting);
              if (inViewport) setVisible(true);
              syncPlayback();
            },
            { rootMargin: '120px' },
          );
    observer?.observe(node);
    document.addEventListener('visibilitychange', syncPlayback);
    return () => {
      observer?.disconnect();
      document.removeEventListener('visibilitychange', syncPlayback);
    };
  }, [expanded]);

  const sorted = [...sources].sort((a, b) => a.width - b.width);
  const preferredSource = expanded ? sorted.at(-1) : sorted[0];
  const shouldLoad = expanded || visible || typeof IntersectionObserver === 'undefined';

  if (!preferredSource) return null;

  return (
    <video
      ref={videoRef}
      className="exercise-guide-video"
      src={shouldLoad ? preferredSource.url : undefined}
      poster={poster}
      preload={shouldLoad ? 'metadata' : 'none'}
      autoPlay
      loop
      muted
      playsInline
      controls={false}
      onError={onError}
      aria-hidden="true"
      data-media-mode="video"
    />
  );
}
