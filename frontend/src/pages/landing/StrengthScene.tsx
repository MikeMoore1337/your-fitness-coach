import { Icon } from '../../shared/ui/Icon';
import { useEffect, useRef } from 'react';
import './strength-scene.css';

const clamp = (value: number) => Math.min(1, Math.max(0, value));
export function strengthFrame(progress: number) {
  const lift = clamp((progress - 0.06) / 0.42);
  return {
    phase: progress < 0.55 ? 0 : progress < 0.8 ? 1 : 2,
    lift: lift * lift * (3 - 2 * lift),
    count: progress < 0.48 ? 2 : 3,
    result: clamp((progress - 0.8) / 0.1),
  };
}
export function StrengthScene() {
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    const node = root.current;
    if (!node) return;
    const sticky = node.querySelector<HTMLElement>('.strength-scene__sticky')!;
    const photo = node.querySelector<HTMLElement>('.strength-scene__raised')!;
    const count = node.querySelector<HTMLElement>('[data-reps]')!;
    const record = node.querySelector<HTMLElement>('[data-record]')!;
    const result = node.querySelector<HTMLElement>('.strength-scene__result')!;
    const indicators = node.querySelectorAll('[data-step]');
    const media = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    let frame = 0;
    let displayed: number | null = null;
    let previous: number | null = null;
    const schedule = () => {
      if (!frame && !document.hidden) frame = requestAnimationFrame(render);
    };
    function render(time: number) {
      frame = 0;
      const bounds = node!.getBoundingClientRect();
      const target = media?.matches
        ? 1
        : clamp(-bounds.top / Math.max(1, node!.offsetHeight - sticky.offsetHeight));
      const delta = previous === null ? 16 : Math.min(40, Math.max(0, time - previous));
      previous = time;
      if (displayed === null || media?.matches || bounds.bottom < 0 || bounds.top > innerHeight)
        displayed = target;
      const gap = target - displayed;
      displayed +=
        Math.sign(gap) * Math.min(Math.abs(gap) * (1 - Math.exp(-delta / 180)), delta * 0.0006);
      if (Math.abs(target - displayed) < 0.0005) displayed = target;
      const state = strengthFrame(displayed);
      photo.style.opacity = String(media?.matches ? Number(state.phase > 0) : state.lift);
      count.textContent = String(state.count);
      record.textContent = state.phase > 0 ? '18 кг × 3' : '18 кг × —';
      result.hidden = state.phase !== 2;
      result.style.opacity = String(media?.matches ? 1 : state.result);
      node!.dataset.phase = String(state.phase);
      indicators.forEach((indicator, index) => {
        if (index === state.phase) indicator.setAttribute('aria-current', 'step');
        else indicator.removeAttribute('aria-current');
      });
      if (displayed !== target) schedule();
      else previous = null;
    }
    const visibility = () => {
      cancelAnimationFrame(frame);
      frame = 0;
      previous = null;
      schedule();
    };
    const resize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(schedule);
    resize?.observe(sticky);
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    document.addEventListener('visibilitychange', visibility);
    media?.addEventListener('change', schedule);
    schedule();
    return () => {
      cancelAnimationFrame(frame);
      resize?.disconnect();
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      document.removeEventListener('visibilitychange', visibility);
      media?.removeEventListener('change', schedule);
    };
  }, []);
  return (
    <section className="strength-scene" ref={root} aria-labelledby="strength-title">
      <div className="strength-scene__sticky">
        <div className="strength-scene__copy">
          <p className="landing-kicker">01 / ОТ ДВИЖЕНИЯ К ЗАПИСИ</p>
          <h2 id="strength-title">
            Каждый подход
            <br /> имеет значение.
          </h2>
          <p>Сделай повторения. Запиши подход. Сохрани результат для следующей тренировки.</p>
        </div>
        <div className="strength-scene__visual">
          <div className="strength-scene__steps" aria-label="Этапы демонстрации">
            {['Усилие', 'Запись', 'Результат'].map((label) => (
              <span data-step key={label}>
                {label}
              </span>
            ))}
          </div>
          <div className="strength-scene__photo">
            <img
              src="/assets/marketing/strength-row-lowered.webp"
              alt="Начало тяги гантели"
              width="1536"
              height="1024"
              loading="lazy"
            />
            <img
              className="strength-scene__raised"
              src="/assets/marketing/strength-row.webp"
              alt="Гантель у пояса в конце тяги"
              width="1536"
              height="1024"
              loading="lazy"
            />
            <span className="strength-scene__caption">
              ТЯГА ГАНТЕЛИ · 18 КГ
              <br />
              <small>Демонстрационный подход</small>
            </span>
            <div className="strength-scene__count">
              <strong data-reps>2</strong>
              <span>
                / 3<br />
                повторения
              </span>
            </div>
            <div className="strength-scene__result" hidden>
              <Icon name="exercise" size={110} />
              <strong>Подход сохранён.</strong>
              <span>18 кг × 3 повторения</span>
            </div>
          </div>
          <div className="strength-scene__record">
            <Icon name="exercise" size={56} />
            <span>
              <small>ЗАПИСЬ ПОДХОДА</small>
              <br />
              Тяга гантели
            </span>
            <strong data-record>18 кг × —</strong>
          </div>
          <p className="strength-scene__disclosure">
            Иллюстрация движения. В приложении повторения записываешь ты.
          </p>
        </div>
      </div>
    </section>
  );
}
