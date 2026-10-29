import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../../styles/fonts.css';
import '../../styles/design-system.css';
import { ActivityHeatmap, type ActivityDay } from './ActivityHeatmap';

const params = new URLSearchParams(window.location.search);
const isLight = params.get('theme') === 'light';
const hasNoActivity = params.get('state') === 'empty';
document.body.style.cssText = `margin:0;padding:12px;font:16px Inter,sans-serif;--font-display:Oswald,sans-serif;background:${isLight ? '#f5f5f2' : '#0c0e0d'};--color-text:${isLight ? '#1b1e1a' : '#f4f5f1'};--color-text-muted:${isLight ? '#596057' : '#aeb5aa'};--color-surface:${isLight ? '#fff' : '#191c1a'};--color-surface-subtle:${isLight ? '#e5e8e2' : '#303630'};--color-border:${isLight ? '#c7cec2' : '#4c554a'};--color-accent:#b8ef5f;--color-accent-subtle:${isLight ? '#dcecbf' : '#455833'};color:var(--color-text)`;
function Preview() {
  const [year, setYear] = useState(2026);
  const countDays = (Date.UTC(year + 1, 0, 1) - Date.UTC(year, 0, 1)) / 86400000;
  const days: ActivityDay[] = Array.from({ length: countDays }, (_, index) => {
    const date = new Date(Date.UTC(year, 0, 1 + index)).toISOString().slice(0, 10);
    const isFuture = date > '2026-10-29';
    const count = isFuture
      ? null
      : hasNoActivity
        ? 0
        : index < 45
          ? null
          : index % 7 === 0
            ? 2
            : index % 3 === 0
              ? 1
              : 0;
    return {
      date,
      is_future: isFuture,
      completed_workouts: count,
      working_sets: count === null ? null : count * 4,
    };
  });

  return (
    <main style={{ maxWidth: 900, margin: 'auto' }}>
      <p>Your Fitness Coach</p>
      <h1 style={{ fontFamily: 'var(--font-display)' }}>Прогресс</h1>
      <p>Предложение #835 · демонстрационные данные</p>
      <ActivityHeatmap
        key={year}
        year={year}
        onYearChange={setYear}
        data={{
          timezone: 'Europe/Moscow',
          history_complete: hasNoActivity,
          undated_workouts: hasNoActivity ? 0 : 3,
          days,
        }}
      />
    </main>
  );
}
createRoot(document.getElementById('root')!).render(<Preview />);
