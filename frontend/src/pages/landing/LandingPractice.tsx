import { lazy, Suspense, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { applyDemoAction, type DemoSessionSnapshot } from '../../features/demo/demoApi';
import { Button, ErrorState, LoadingState } from '../../shared/ui/common';
import { landingDemoQuery } from './landingDemoQuery';
const TrainingScenario = lazy(() =>
  import('../demo/DemoPage').then((module) => ({ default: module.TrainingScenario })),
);

function V10TrainingPreview({ busy, onStart }: { busy: boolean; onStart: () => void }) {
  return (
    <div className="landing-v10-training-preview" data-testid="landing-v10-training-preview">
      <div className="landing-v10-training-preview__topline">
        <strong>Сегодня / Тренировка</strong>
        <span>Сбросить пример</span>
      </div>
      <div className="landing-v10-training-preview__rule" />
      <span className="landing-v10-training-preview__badge">Сегодня</span>
      <h3>Силовая А</h3>
      <p>Программа на неделю · пример данных</p>
      <div className="landing-v10-training-preview__progress">
        <span>Выполнено подходов</span>
        <strong>0 из 3</strong>
      </div>
      <div className="landing-v10-training-preview__track" aria-hidden="true">
        <span />
      </div>
      <div className="landing-v10-training-preview__exercise">
        <div>
          <strong>Тяга гантели</strong>
          <span>18 кг × 3 повторения · демонстрационный подход</span>
        </div>
        <span>Сейчас</span>
      </div>
      <Button fullWidth disabled={busy} onClick={onStart}>
        {busy ? 'Открываем…' : 'Начать тренировку'}
      </Button>
    </div>
  );
}

export function LandingPractice({ approvedPreview = false }: { approvedPreview?: boolean }) {
  const queryClient = useQueryClient();
  const [snapshot, setSnapshot] = useState<DemoSessionSnapshot>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef(false);
  async function run(action?: string) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      const next = await (action
        ? applyDemoAction('self_training', action)
        : queryClient.fetchQuery({ ...landingDemoQuery, staleTime: 0 }));
      setSnapshot(next);
      queryClient.setQueryData(landingDemoQuery.queryKey, next);
    } catch {
      setError('Демо сейчас недоступно. Попробуйте ещё раз.');
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  const hasSelfTrainingSnapshot = snapshot?.state.kind === 'self_training';
  return (
    <div className="landing-practice__entry">
      {approvedPreview ? (
        hasSelfTrainingSnapshot ? null : (
          <V10TrainingPreview busy={busy} onStart={() => void run()} />
        )
      ) : (
        <img
          src="/assets/marketing/practice-recording.webp"
          alt="Спортсменка записывает результат подхода в телефоне"
          width="1536"
          height="1024"
          loading="lazy"
        />
      )}
      {error && <ErrorState message={error} retry={() => void run()} />}
      {snapshot?.state.kind === 'self_training' ? (
        <Suspense fallback={<LoadingState label="Открываем тренировку" />}>
          <TrainingScenario
            state={snapshot.state}
            busy={busy}
            onAction={(action) => void run(action)}
          />
        </Suspense>
      ) : approvedPreview ? null : (
        <Button fullWidth disabled={busy} onClick={() => void run()}>
          {busy ? 'Открываем…' : 'Попробовать тренировку'}
        </Button>
      )}
    </div>
  );
}
