import { useEffect } from 'react';

/** Вступление из утверждённого прототипа; не блокирует ссылки и ввод. */
export function useLandingHeroMotion() {
  useEffect(() => {
    const media = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    const animations: Animation[] = [];
    let disposed = false;
    const cancel = () => animations.forEach((animation) => animation.cancel());
    const visibility = () => {
      if (document.hidden || media?.matches) cancel();
    };
    const start = () => {
      if (disposed || document.hidden || media?.matches) return;
      const photo = document.querySelector('.landing-hero__image');
      if (!photo?.animate) return;
      animations.push(
        photo.animate([{ transform: 'scale(1.075)' }, { transform: 'scale(1)' }], {
          duration: 1700,
          easing: 'cubic-bezier(.23,1,.32,1)',
        }),
      );
      document.querySelectorAll('.landing-hero h1 span').forEach((line, index) => {
        animations.push(
          line.animate(
            [
              { clipPath: 'inset(0 0 100% 0)', transform: 'translateY(35px)' },
              { clipPath: 'inset(0)', transform: 'translateY(0)' },
            ],
            { duration: 850, delay: index * 110, easing: 'cubic-bezier(.23,1,.32,1)' },
          ),
        );
      });
    };
    void document.fonts?.ready.then(start);
    document.addEventListener('visibilitychange', visibility);
    media?.addEventListener('change', visibility);
    return () => {
      disposed = true;
      cancel();
      document.removeEventListener('visibilitychange', visibility);
      media?.removeEventListener('change', visibility);
    };
  }, []);
}
