import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { ApiError, api } from '../../shared/api/client';
import type { ProgramTemplate, PublicShare, PublicSharePreview } from '../../shared/api/types';
import { trackGrowthEvent } from '../../shared/analytics/productEvents';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Button } from '../../shared/ui/common';
import { PublicShareOwnerList } from '../sharing/PublicShareOwnerList';
import '../sharing/public-share-owner.css';

type PublicProgramSharePanelProps = { showList?: boolean; template: ProgramTemplate };

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

export function PublicProgramSharePanel({
  showList = true,
  template,
}: PublicProgramSharePanelProps) {
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
      const result = await api<PublicSharePreview>('/api/v1/shares/program/preview', {
        method: 'POST',
        body: { template_id: template.id },
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
        title: 'Создать публичный снимок программы?',
        message:
          'Будет опубликован только точный состав из предпросмотра выше. Ссылка не содержит внутренних идентификаторов и не станет live-ссылкой на исходник.',
        confirmText: 'Создать ссылку',
      }))
    )
      return;
    setLoading(true);
    setError(null);
    try {
      const result = await api<PublicShare>('/api/v1/shares/program', {
        method: 'POST',
        body: { template_id: template.id, preview_hash: preview.preview_hash },
      });
      setCreated(result);
      trackGrowthEvent('share_created');
      await queryClient.invalidateQueries({ queryKey: ['public-shares'] });
    } catch (reason) {
      setError(
        reason instanceof ApiError && reason.status === 409
          ? 'Программа изменилась. Сначала обновите предпросмотр.'
          : reason instanceof Error
            ? reason.message
            : 'Не удалось создать ссылку',
      );
    } finally {
      setLoading(false);
    }
  };

  const snapshot = preview?.snapshot.kind === 'program' ? preview.snapshot : null;
  return (
    <section className="public-share-owner-panel" aria-label="Поделиться программой">
      <div className="public-share-owner-panel__actions">
        {!preview && !created && (
          <Button
            disabled={loading}
            onClick={() => void showPreview()}
            type="button"
            variant="secondary"
          >
            {loading ? 'Собираем…' : 'Поделиться программой'}
          </Button>
        )}
      </div>
      {snapshot && !created && (
        <div className="public-share-owner-panel__preview">
          <span className="eyebrow">Предпросмотр публикации</span>
          <h3 id={`public-program-share-${template.id}`}>{snapshot.title}</h3>
          <dl className="public-share-owner-panel__facts">
            <div>
              <dt>Длительность</dt>
              <dd>{snapshot.duration_weeks} нед.</dd>
            </div>
            <div>
              <dt>Тренировочные дни</dt>
              <dd>{snapshot.days.length}</dd>
            </div>
            <div>
              <dt>Упражнения</dt>
              <dd>{snapshot.days.reduce((total, day) => total + day.exercises.length, 0)}</dd>
            </div>
          </dl>
          <p>
            Проверьте дни и упражнения. В публичный снимок не войдут владелец, внутренние ID и
            приватные заметки.
          </p>
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
              Закрыть предпросмотр
            </Button>
          </div>
        </div>
      )}
      {created && (
        <div className="public-share-owner-panel__preview" role="status">
          <h3>Снимок программы создан</h3>
          <p>Получатель увидит этот состав и сможет отдельно подтвердить импорт копии.</p>
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
              Закрыть
            </Button>
          </div>
        </div>
      )}
      {error && (
        <p className="progress-report-handoff__error" role="alert">
          {error}
        </p>
      )}
      {showList && <PublicShareOwnerList shareType="program" />}
    </section>
  );
}
