import { createRoot } from 'react-dom/client';
import { ActivityHeatmap, type ActivityDay } from './ActivityHeatmap';

const params = new URLSearchParams(window.location.search);
const isLight = params.get('theme') === 'light';
const isEmpty = params.get('state') === 'empty';
document.body.style.cssText = `margin:0;padding:24px;font:16px Arial,sans-serif;background:${isLight ? '#f5f5f2' : '#0c0e0d'};--color-text:${isLight ? '#1b1e1a' : '#f4f5f1'};--color-text-muted:${isLight ? '#596057' : '#aeb5aa'};--color-surface:${isLight ? '#fff' : '#191c1a'};--color-surface-subtle:${isLight ? '#e5e8e2' : '#303630'};--color-border:${isLight ? '#c7cec2' : '#4c554a'};--color-accent:#b8ef5f;--color-accent-subtle:${isLight ? '#dcecbf' : '#455833'};color:var(--color-text)`;
const days: ActivityDay[] = Array.from({ length: 365 }, (_, index) => {
  const date = new Date(Date.UTC(2025, 9, 30 + index)).toISOString().slice(0, 10);
  const count = isEmpty ? 0 : index < 45 ? null : index % 7 === 0 ? 2 : index % 3 === 0 ? 1 : 0;
  return { date, completed_workouts: count, working_sets: count === null ? null : count * 4 };
});

createRoot(document.getElementById('root')!).render(
  <main style={{ maxWidth: 900, margin: 'auto' }}>
    <p>YOUR FITNESS COACH</p>
    <h1>Прогресс</h1>
    <p>Предложение #835 · демонстрационные данные</p>
    <ActivityHeatmap
      data={{
        timezone: 'Europe/Moscow',
        history_complete: isEmpty,
        undated_workouts: isEmpty ? 0 : 3,
        days,
      }}
      variant={params.get('variant') === 'months' ? 'months' : 'year'}
    />
  </main>,
);
