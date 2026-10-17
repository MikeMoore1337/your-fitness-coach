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
    if (expanded || typeof IntersectionObserver === 'undefined') return;
    const node = videoRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: '120px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
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
