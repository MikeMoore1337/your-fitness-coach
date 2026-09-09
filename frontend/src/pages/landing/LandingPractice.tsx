import { lazy, Suspense, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { applyDemoAction, type DemoSessionSnapshot } from '../../features/demo/demoApi';
import { Button, ErrorState, LoadingState } from '../../shared/ui/common';
import { landingDemoQuery } from './landingDemoQuery';
const TrainingScenario = lazy(() =>
  import('../demo/DemoPage').then((module) => ({ default: module.TrainingScenario })),
);
export function LandingPractice() {
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
  return (
    <div className="landing-practice__entry">
      <img
        src="/assets/marketing/practice-recording.webp"
        alt="Спортсменка записывает результат подхода в телефоне"
        width="1536"
        height="1024"
        loading="lazy"
      />
      {error && <ErrorState message={error} retry={() => void run()} />}
      {snapshot?.state.kind === 'self_training' ? (
        <Suspense fallback={<LoadingState label="Открываем тренировку" />}>
          <TrainingScenario
            state={snapshot.state}
            busy={busy}
            onAction={(action) => void run(action)}
          />
        </Suspense>
      ) : (
        <Button fullWidth disabled={busy} onClick={() => void run()}>
          {busy ? 'Открываем…' : 'Попробовать тренировку'}
        </Button>
      )}
    </div>
  );
}
