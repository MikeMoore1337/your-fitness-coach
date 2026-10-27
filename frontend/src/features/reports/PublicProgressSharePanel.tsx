import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { ApiError, api } from '../../shared/api/client';
import type {
  NutritionReportPeriod,
  PublicShare,
  PublicSharePreview,
} from '../../shared/api/types';
import { trackGrowthEvent } from '../../shared/analytics/productEvents';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Button } from '../../shared/ui/common';
import { PublicShareOwnerList } from '../sharing/PublicShareOwnerList';
import '../sharing/public-share-owner.css';

type PublicProgressSharePanelProps = {
  dateFrom: string;
  dateTo: string;
  period: NutritionReportPeriod;
};

function periodPayload(period: NutritionReportPeriod, dateFrom: string, dateTo: string) {
  return {
    period,
    ...(period === 'custom' ? { date_from: dateFrom, date_to: dateTo } : {}),
  };
}

function copyLink(value: string, toast: (message: string, type?: 'success' | 'error') => void) {
  if (!navigator.clipboard) {
    toast('Скопируйте ссылку вручную.', 'error');
    return;
  }
  void navigator.clipboard.writeText(value).then(
    () => toast('Ссылка скопирована.'),
    () => toast('Скопируйте ссылку вручную.', 'error'),
  );
}

export function PublicProgressSharePanel({
  dateFrom,
  dateTo,
  period,
}: PublicProgressSharePanelProps) {
  const { confirm, toast } = useFeedback();
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<PublicSharePreview | null>(null);
  const [created, setCreated] = useState<PublicShare | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showPreview = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api<PublicSharePreview>('/api/v1/shares/progress/preview', {
        method: 'POST',
        body: periodPayload(period, dateFrom, dateTo),
      });
      setPreview(result);
      setCreated(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось собрать предпросмотр');
    } finally {
      setLoading(false);
    }
  };

  const createShare = async () => {
    if (!preview) return;
    if (
      !(await confirm({
        title: 'Создать публичный снимок?',
        message:
          'Будут опубликованы только факты тренировок из точного предпросмотра выше. Питание, замеры тела, заметки и другая частная история не попадут в ссылку.',
        confirmText: 'Создать ссылку',
      }))
    )
      return;
    setLoading(true);
    setError(null);
    try {
      const result = await api<PublicShare>('/api/v1/shares/progress', {
        method: 'POST',
        body: { ...periodPayload(period, dateFrom, dateTo), preview_hash: preview.preview_hash },
      });
      setCreated(result);
      trackGrowthEvent('share_created');
      await queryClient.invalidateQueries({ queryKey: ['public-shares'] });
    } catch (reason) {
      setError(
        reason instanceof ApiError && reason.status === 409
          ? 'Данные изменились. Сначала обновите предпросмотр.'
          : reason instanceof Error
            ? reason.message
            : 'Не удалось создать ссылку',
      );
    } finally {
      setLoading(false);
    }
  };

  const snapshot = preview?.snapshot.kind === 'progress' ? preview.snapshot : null;
  return (
    <section
      className="public-share-owner-panel card report-screen-only"
      aria-labelledby="public-progress-share-title"
    >
      <div className="public-share-owner-panel__heading">
        <span className="eyebrow">Осознанная отправка</span>
        <h2 id="public-progress-share-title">Поделиться фактическим прогрессом</h2>
        <p>
          Сначала покажем точный снимок за выбранный период. Ссылка будет immutable и не включит
          данные питания, тела, заметки или историю тренера.
        </p>
      </div>
      {!preview && (
        <Button disabled={loading} onClick={() => void showPreview()} type="button">
          {loading ? 'Собираем предпросмотр…' : 'Показать предпросмотр'}
        </Button>
      )}
      {snapshot && !created && (
        <div className="public-share-owner-panel__preview">
          <h3>В этот снимок попадёт</h3>
          <dl className="public-share-owner-panel__facts">
            <div>
              <dt>Период</dt>
              <dd>
                {snapshot.period_start} — {snapshot.period_end}
              </dd>
            </div>
            <div>
              <dt>Тренировки</dt>
              <dd>
                {snapshot.completed_workouts} из {snapshot.planned_workouts}
              </dd>
            </div>
            <div>
              <dt>Рабочие подходы</dt>
              <dd>{snapshot.completed_working_sets}</dd>
            </div>
            <div>
              <dt>Полнота</dt>
              <dd>
                {snapshot.data_quality.workout_logging === 'sufficient'
                  ? 'Достаточно данных'
                  : 'Данные неполные'}
              </dd>
            </div>
          </dl>
          <p>{snapshot.data_quality.notes.join(' ')}</p>
          <div className="public-share-owner-panel__actions">
            <Button disabled={loading} onClick={() => void createShare()} type="button">
              Создать публичную ссылку
            </Button>
            <Button
              disabled={loading}
              onClick={() => {
                setPreview(null);
                setError(null);
              }}
              type="button"
              variant="secondary"
            >
              Изменить период
            </Button>
          </div>
        </div>
      )}
      {created && (
        <div className="public-share-owner-panel__preview" role="status">
          <h3>Снимок создан</h3>
          <p>Публичная ссылка содержит только подтверждённый предпросмотр.</p>
          <a className="public-share-owner-panel__link" href={created.public_url}>
            {created.public_url}
          </a>
          <div className="public-share-owner-panel__actions">
            <Button onClick={() => copyLink(created.public_url, toast)} type="button">
              Скопировать ссылку
            </Button>
            <Button
              onClick={() => {
                setCreated(null);
                setPreview(null);
              }}
              type="button"
              variant="secondary"
            >
              Создать другой снимок
            </Button>
          </div>
        </div>
      )}
      {error && (
        <p className="progress-report-handoff__error" role="alert">
          {error}
        </p>
      )}
      <PublicShareOwnerList shareType="progress" />
    </section>
  );
}
