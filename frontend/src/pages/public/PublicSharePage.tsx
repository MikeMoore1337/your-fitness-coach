import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useOptionalAuth } from '../../app/AuthProvider';
import { ApiError, api } from '../../shared/api/client';
import type {
  PublicShare,
  PublicShareImportResponse,
  PublicShareProgramSnapshot,
  PublicShareProgressSnapshot,
} from '../../shared/api/types';
import { AppLink, useNavigation } from '../../shared/navigation/router';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';
import { PublicShell } from '../../shared/ui/PublicShell';
import './public-share.css';

const SHARE_ID_PATTERN = /^[A-Za-z0-9_-]{43}$/;

type ShareRequest =
  | { key: string; status: 'loading' }
  | { key: string; status: 'success'; share: PublicShare }
  | { key: string; status: 'error' };

const goalLabels: Record<string, string> = {
  muscle_gain: 'Набор мышечной массы',
  fat_loss: 'Снижение веса',
  maintenance: 'Поддержание формы',
  recomposition: 'Рекомпозиция',
  strength: 'Развитие силы',
};

const levelLabels: Record<string, string> = {
  beginner: 'Начальный уровень',
  intermediate: 'Средний уровень',
  advanced: 'Продвинутый уровень',
};

function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value == null) return 'Нет данных';
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(value);
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${value}T12:00:00Z`));
}

function qualityLabel(
  value: PublicShareProgressSnapshot['data_quality']['workout_logging'],
): string {
  return {
    sufficient: 'Достаточно данных',
    limited: 'Данные неполные',
    insufficient: 'Мало данных',
  }[value];
}

function ProgressSnapshot({ snapshot }: { snapshot: PublicShareProgressSnapshot }) {
  return (
    <>
      <header className="public-share__snapshot-heading">
        <span className="eyebrow">Фактическая сводка</span>
        <h1>Прогресс тренировок</h1>
        <p>
          {formatDate(snapshot.period_start)} — {formatDate(snapshot.period_end)}
        </p>
      </header>
      <div className="public-share__metrics" aria-label="Факты тренировок">
        <div>
          <span>Завершено</span>
          <strong>{snapshot.completed_workouts}</strong>
          <small>из {snapshot.planned_workouts} по плану</small>
        </div>
        <div>
          <span>Частота</span>
          <strong>{formatNumber(snapshot.frequency_per_week, 2)}</strong>
          <small>тренировок в неделю</small>
        </div>
        <div>
          <span>Рабочие подходы</span>
          <strong>{snapshot.completed_working_sets}</strong>
          <small>фактически записано</small>
        </div>
        <div>
          <span>Новые рекорды</span>
          <strong>{snapshot.new_personal_records}</strong>
          <small>за выбранный период</small>
        </div>
      </div>
      <section className="public-share__quality" aria-labelledby="public-share-quality-title">
        <div>
          <span className="eyebrow">Полнота</span>
          <h2 id="public-share-quality-title">Что вошло в снимок</h2>
        </div>
        <ul>
          <li>
            <Badge
              tone={snapshot.data_quality.workout_logging === 'sufficient' ? 'success' : 'warning'}
            >
              {qualityLabel(snapshot.data_quality.workout_logging)}
            </Badge>
            <span>Записи тренировок</span>
          </li>
          <li>
            <Badge
              tone={snapshot.data_quality.working_sets === 'sufficient' ? 'success' : 'warning'}
            >
              {qualityLabel(snapshot.data_quality.working_sets)}
            </Badge>
            <span>Рабочие подходы и нагрузка</span>
          </li>
        </ul>
        <div className="public-share__quality-notes">
          {snapshot.data_quality.notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
        </div>
      </section>
      <section aria-labelledby="public-share-exercises-title">
        <div className="public-share__section-heading">
          <span className="eyebrow">Упражнения</span>
          <h2 id="public-share-exercises-title">Записанная динамика</h2>
        </div>
        {snapshot.exercises.length ? (
          <div className="public-share__exercise-list">
            {snapshot.exercises.map((exercise) => (
              <article key={exercise.exercise_title}>
                <h3>{exercise.exercise_title}</h3>
                <dl>
                  <div>
                    <dt>Сессии</dt>
                    <dd>{exercise.performed_session_count}</dd>
                  </div>
                  <div>
                    <dt>Рабочие подходы</dt>
                    <dd>{exercise.completed_set_count}</dd>
                  </div>
                  <div>
                    <dt>Макс. внешний вес</dt>
                    <dd>{formatNumber(exercise.max_external_load_kg)} кг</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Упражнений пока нет" text="За этот период нет записанных фактов." />
        )}
      </section>
      <p className="public-share__limit">
        Это immutable-снимок фактически записанных тренировок на момент публикации. Он не содержит
        питания, замеров тела, заметок и другой частной истории.
      </p>
    </>
  );
}

function ProgramSnapshot({ snapshot }: { snapshot: PublicShareProgramSnapshot }) {
  return (
    <>
      <header className="public-share__snapshot-heading">
        <span className="eyebrow">Публичный снимок программы</span>
        <h1>{snapshot.title}</h1>
        <p>
          {goalLabels[snapshot.goal] ?? snapshot.goal} ·{' '}
          {levelLabels[snapshot.level] ?? snapshot.level} · {snapshot.duration_weeks} нед.
        </p>
      </header>
      <div className="public-share__program-days">
        {snapshot.days.map((day) => (
          <section className="public-share__program-day" key={day.day_number}>
            <div className="public-share__section-heading">
              <span className="eyebrow">День {day.day_number}</span>
              <h2>{day.title}</h2>
            </div>
            <ol>
              {day.exercises.map((exercise, index) => (
                <li key={`${exercise.exercise_title}-${index}`}>
                  <div>
                    <strong>{exercise.exercise_title}</strong>
                    <span>
                      {exercise.metric_type === 'cardio'
                        ? `${exercise.prescribed_duration_minutes ?? '—'} мин`
                        : `${exercise.prescribed_sets} подхода × ${exercise.prescribed_reps}`}
                    </span>
                  </div>
                  <small>Отдых: {exercise.rest_seconds} сек.</small>
                  {exercise.weekly_prescriptions.length > 0 && (
                    <small>Есть отдельные предписания по неделям.</small>
                  )}
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
      <p className="public-share__limit">
        Это immutable-снимок программы на момент публикации. Импорт создаёт отдельную копию и не
        меняется вслед за исходной программой.
      </p>
    </>
  );
}

function shareTitle(share: PublicShare): string {
  return share.share_type === 'program' && share.snapshot.kind === 'program'
    ? `${share.snapshot.title} — программа тренировок`
    : 'Прогресс тренировок — Your Fitness Coach';
}

function PublicShareContent({ share }: { share: PublicShare }) {
  const auth = useOptionalAuth();
  const { confirm, toast } = useFeedback();
  const [importResult, setImportResult] = useState<PublicShareImportResponse | null>(null);
  const sharePath = `${window.location.pathname}${window.location.search}`;
  const importMutation = useMutation({
    mutationFn: (replaceActive: boolean) =>
      api<PublicShareImportResponse>(`/api/v1/shares/${share.share_id}/import`, {
        method: 'POST',
        body: { preview_hash: share.preview_hash, replace_active: replaceActive },
      }),
    onSuccess: (result) => {
      setImportResult(result);
      if (result.status === 'imported') {
        trackProductEvent({ name: 'program_imported', surface: productEventSurface() });
      }
      toast(
        result.status === 'already_imported'
          ? 'Эта программа уже добавлена в ваш профиль.'
          : 'Программа добавлена отдельной копией.',
      );
    },
    onError: async (reason, replaceActive) => {
      if (
        reason instanceof ApiError &&
        reason.status === 409 &&
        !replaceActive &&
        reason.message.toLowerCase().includes('confirmation')
      ) {
        if (
          await confirm({
            title: 'Заменить активную программу?',
            message:
              'Текущая программа будет отправлена в архив. Тренировку, которая уже идёт, заменить нельзя.',
            confirmText: 'Заменить программу',
          })
        )
          importMutation.mutate(true);
        return;
      }
      toast(reason instanceof Error ? reason.message : 'Не удалось добавить программу', 'error');
    },
  });

  if (share.share_type !== 'program' || share.snapshot.kind !== 'program') return null;
  const loggedIn = Boolean(auth?.user);
  return (
    <>
      <ProgramSnapshot snapshot={share.snapshot} />
      <section className="public-share__import" aria-labelledby="public-share-import-title">
        <div>
          <span className="eyebrow">Отдельная копия</span>
          <h2 id="public-share-import-title">Добавить программу в свой профиль?</h2>
          <p>
            Сначала проверьте состав выше. Ничего не добавится без вашего явного подтверждения;
            исходная программа не изменится.
          </p>
        </div>
        {loggedIn ? (
          <Button
            disabled={importMutation.isPending || importResult?.status === 'already_imported'}
            onClick={() =>
              void confirm({
                title: 'Добавить копию программы?',
                message:
                  'Будет создана отдельная копия программы и запущен существующий процесс назначения. Исходник останется без изменений.',
                confirmText: 'Добавить программу',
              }).then((accepted) => {
                if (accepted) importMutation.mutate(false);
              })
            }
            type="button"
          >
            {importMutation.isPending ? 'Добавляем…' : 'Добавить программу'}
          </Button>
        ) : (
          <AppLink className="button-link" to={`/login?next=${encodeURIComponent(sharePath)}`}>
            Войти, чтобы добавить
          </AppLink>
        )}
        {importResult && (
          <p className="public-share__import-result" role="status">
            {importResult.status === 'already_imported'
              ? 'Копия уже есть в вашем профиле.'
              : 'Копия создана через стандартный процесс назначения программы.'}
          </p>
        )}
      </section>
    </>
  );
}

export default function PublicSharePage() {
  const { path } = useNavigation();
  const shareId = path.startsWith('/share/') ? path.slice('/share/'.length) : '';
  const openedRef = useRef(false);
  const [reloadToken, setReloadToken] = useState(0);
  const shareIdValid = SHARE_ID_PATTERN.test(shareId);
  const requestKey = `${shareId}:${reloadToken}`;
  const [shareRequest, setShareRequest] = useState<ShareRequest>(() => ({
    key: requestKey,
    status: shareIdValid ? 'loading' : 'error',
  }));
  useEffect(() => {
    let cancelled = false;
    if (!shareIdValid) return undefined;
    void api<PublicShare>(`/api/v1/public/shares/${encodeURIComponent(shareId)}`)
      .then((result) => {
        if (!cancelled) setShareRequest({ key: requestKey, status: 'success', share: result });
      })
      .catch(() => {
        if (!cancelled) setShareRequest({ key: requestKey, status: 'error' });
      });
    return () => {
      cancelled = true;
    };
  }, [requestKey, shareId, shareIdValid]);

  const currentRequest = shareRequest.key === requestKey ? shareRequest : null;
  const share = currentRequest?.status === 'success' ? currentRequest.share : null;
  const shareLoading = shareIdValid && (!currentRequest || currentRequest.status === 'loading');
  const shareError = shareIdValid && currentRequest?.status === 'error';

  useEffect(() => {
    if (!share || openedRef.current) return;
    openedRef.current = true;
    trackProductEvent({ name: 'share_opened', surface: productEventSurface() });
  }, [share]);

  useEffect(() => {
    let cancelled = false;
    void import('../../shared/seo/metadata').then(({ applyRouteMetadata }) => {
      if (cancelled || window.location.pathname !== path) return;
      applyRouteMetadata(path);
      if (share) document.title = shareTitle(share);
    });
    return () => {
      cancelled = true;
    };
  }, [path, share]);

  const loginPath = `/login?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`;
  return (
    <PublicShell
      headerAction={
        <AppLink className="landing-button landing-button--compact" to={loginPath}>
          Войти
        </AppLink>
      }
      skipTarget="public-share-content"
    >
      <main id="public-share-content" className="public-share" tabIndex={-1}>
        {shareLoading ? (
          <LoadingState label="Открываем публичный снимок…" />
        ) : shareError ? (
          <ErrorState
            message="Ссылка недоступна или больше не действует."
            retry={() => setReloadToken((value) => value + 1)}
          />
        ) : share ? (
          <Card className="public-share__card" collapsible={false}>
            {share.share_type === 'progress' && share.snapshot.kind === 'progress' ? (
              <ProgressSnapshot snapshot={share.snapshot} />
            ) : (
              <PublicShareContent share={share} />
            )}
          </Card>
        ) : (
          <EmptyState
            title="Снимок не найден"
            text="Проверьте ссылку или попросите создать новую."
          />
        )}
      </main>
    </PublicShell>
  );
}
