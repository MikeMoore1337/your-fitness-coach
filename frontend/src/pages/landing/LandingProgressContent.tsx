import { TimeSeriesChart } from '../../shared/ui/DataViz';
import { Icon } from '../../shared/ui/Icon';

const LANDING_PROGRESS_PREVIEW = {
  latest_volume_kg: 6220,
  workouts_completed: 11,
  volume_change_percent: 4.2,
  summary: 'Итог использует только подтверждённые записи.',
} as const;

export default function LandingProgressContent({ href }: { href: string }) {
  // This is a static prepared preview. The interactive demo creates its own
  // session only after the visitor explicitly opens the demo flow.
  const progress = LANDING_PROGRESS_PREVIEW;
  return (
    <>
      <div className="landing-progress__heading">
        <Icon name="nav-progress" style={{ width: 64, height: 64 }} />
        <div>
          <small>ПОДГОТОВЛЕННЫЙ ДЕМО-СЦЕНАРИЙ</small>
          <h3>Объём тренировок</h3>
        </div>
      </div>
      <p className="landing-progress__value">
        <strong>{progress.latest_volume_kg.toLocaleString('ru-RU')}</strong> кг
      </p>
      <TimeSeriesChart
        ariaLabel="Динамика объёма в подготовленном демо"
        metric="Изменение объёма"
        period="Сводка демо"
        unit="%"
        note="Индекс: начало периода = 100%. Показаны две сводные точки, а не отдельные тренировки."
        points={[
          { key: 'start', label: 'Начало периода', value: 100 },
          { key: 'current', label: 'Сейчас', value: 100 + progress.volume_change_percent },
        ]}
      />
      <p>
        {progress.workouts_completed} тренировок · {progress.summary}
      </p>
      <a className="landing-button" href={href}>
        Открыть прогресс
      </a>
    </>
  );
}
