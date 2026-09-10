import { lazy, Suspense, useEffect, useRef, useState } from 'react';

const LandingProgressContent = lazy(() => import('./LandingProgressContent'));

export function LandingProgress({ href }: { href: string }) {
  const root = useRef<HTMLDivElement>(null);
  const [isNearViewport, setIsNearViewport] = useState(
    () => typeof IntersectionObserver === 'undefined',
  );

  useEffect(() => {
    const node = root.current;
    if (!node) return;
    if (typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        setIsNearViewport(true);
        observer.disconnect();
      },
      { rootMargin: '240px 0px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="landing-feature__progress" ref={root} aria-busy={!isNearViewport}>
      {isNearViewport ? (
        <Suspense fallback={<p role="status">Загружаем пример прогресса…</p>}>
          <LandingProgressContent href={href} />
        </Suspense>
      ) : (
        <p>Подготовленный демо-сценарий</p>
      )}
    </div>
  );
}
