import { useQuery } from '@tanstack/react-query';
import { TimeSeriesChart } from '../../shared/ui/DataViz';
import { ErrorState, LoadingState } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { landingDemoQuery } from './landingDemoQuery';

export function LandingProgress({ href }: { href: string }) {
  const session = useQuery(landingDemoQuery);
  const progress = session.data?.cabinet?.progress;
  return (
    <div className="landing-feature__progress">
      <div className="landing-progress__heading">
        <Icon name="nav-progress" style={{ width: 64, height: 64 }} />
        <div>
          <small>ПОДГОТОВЛЕННЫЙ ДЕМО-СЦЕНАРИЙ</small>
          <h3>Объём тренировок</h3>
        </div>
      </div>
      {session.isLoading ? (
        <LoadingState label="Загружаем пример прогресса…" />
      ) : session.isError ? (
        <ErrorState
          message="Не удалось загрузить демо-прогресс."
          retry={() => void session.refetch()}
        />
      ) : progress ? (
        <>
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
        </>
      ) : null}
      <a className="landing-button" href={href}>
        Открыть прогресс
      </a>
    </div>
  );
}
