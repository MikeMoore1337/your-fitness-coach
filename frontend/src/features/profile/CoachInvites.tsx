import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { components } from '../../shared/api/schema';
import type { CoachInvitePreview } from '../../shared/api/types';
import { useAuth } from '../../app/AuthProvider';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Badge, Card } from '../../shared/ui/common';

type TrainerNutritionAccess = components['schemas']['TrainerNutritionAccess'];

export function tokenFromInvite(value: string): string {
  const trimmed = value.trim();
  try {
    const parsed = new URL(trimmed);
    const startParam =
      parsed.searchParams.get('startapp') ||
      parsed.searchParams.get('start') ||
      parsed.searchParams.get('tgWebAppStartParam');
    if (startParam) return startParam.replace(/^trainer_/, '');
    const pathToken = parsed.pathname.match(/\/join\/([A-Za-z0-9_-]{20,128})\/?$/)?.[1];
    if (pathToken) return pathToken;
  } catch {
    // A copied fallback code is expected not to be a URL.
  }
  return trimmed.replace(/^trainer_/, '');
}

export function CoachInvites({
  initialToken,
  onInitialTokenHandled,
}: {
  initialToken?: string | null;
  onInitialTokenHandled?: () => void;
}) {
  const { user, reloadUser } = useAuth();
  const { toast, confirm } = useFeedback();
  const queryClient = useQueryClient();
  const accessKey = ['me', 'trainer-nutrition-access', user?.trainer?.id] as const;
  const nutritionAccess = useQuery({
    queryKey: accessKey,
    enabled: Boolean(user?.trainer),
    queryFn: () => api<TrainerNutritionAccess>('/api/v1/me/trainer/nutrition-access'),
  });
  const updateNutritionAccess = useMutation({
    mutationFn: (nutrition_access: boolean) =>
      api<TrainerNutritionAccess>('/api/v1/me/trainer/nutrition-access', {
        method: 'PUT',
        body: { nutrition_access, relationship_id: nutritionAccess.data?.relationship_id },
      }),
    onSuccess: async (data) => {
      queryClient.setQueryData(accessKey, data);
      toast(data.nutrition_access ? 'Доступ к питанию открыт' : 'Доступ к питанию закрыт');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const handledInitialToken = useRef<string | null>(null);
  const [inviteInput, setInviteInput] = useState('');
  const [preview, setPreview] = useState<{ token: string; data: CoachInvitePreview } | null>(null);
  const mutation = useMutation({
    mutationFn: ({ path, method }: { path: string; method: string }) => api(path, { method }),
    onSuccess: async () => {
      await reloadUser();
      toast('Связь с тренером обновлена');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const previewMutation = useMutation({
    mutationFn: (value: string) => {
      const token = tokenFromInvite(value);
      if (!token) throw new Error('Введите код или ссылку приглашения');
      return api<CoachInvitePreview>('/api/v1/me/coach-invites/link/preview', {
        method: 'POST',
        body: { token },
      }).then((data) => ({ token, data }));
    },
    onSuccess: (result) => {
      setInviteInput('');
      setPreview(result);
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const confirmMutation = useMutation({
    mutationFn: (token: string) =>
      api('/api/v1/me/coach-invites/link/confirm', {
        method: 'POST',
        body: { token },
      }),
    onSuccess: async () => {
      setPreview(null);
      setInviteInput('');
      await reloadUser();
      toast('Тренер подключён');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  useEffect(() => {
    if (!initialToken || handledInitialToken.current === initialToken) return;
    handledInitialToken.current = initialToken;
    onInitialTokenHandled?.();
    previewMutation.mutate(initialToken);
    // The launch token is consumed in memory once per mounted profile panel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialToken, onInitialTokenHandled]);

  return (
    <Card
      title="Мой тренер"
      description="Подключение происходит только после того, как вы проверите имя и подтвердите приглашение."
      collapsible={false}
    >
      <div className="metric top-gap">
        <span>Текущий тренер</span>
        <strong>{user?.trainer?.full_name || user?.trainer?.username || 'Не назначен'}</strong>
      </div>
      {user?.trainer && (
        <div className="top-gap">
          {nutritionAccess.isError ? (
            <p role="alert">Не удалось загрузить доступ к питанию.</p>
          ) : (
            <label>
              <input
                type="checkbox"
                checked={nutritionAccess.data?.nutrition_access ?? false}
                disabled={!nutritionAccess.data || updateNutritionAccess.isPending}
                onChange={(event) => updateNutritionAccess.mutate(event.target.checked)}
              />{' '}
              Разрешить тренеру доступ к питанию
            </label>
          )}
          <p className="muted">
            Настройка не разрывает связь с тренером. При закрытом доступе недельные итоги и полные
            отчёты, содержащие питание, тренеру недоступны.
          </p>
        </div>
      )}
      <div className="toolbar wrap top-gap">
        {user?.trainer?.chat_url && (
          <a className="button-link" href={user.trainer.chat_url} target="_blank" rel="noreferrer">
            Написать тренеру
          </a>
        )}
        {user?.trainer && (
          <button
            type="button"
            className="btn-danger"
            onClick={async () => {
              if (
                await confirm({
                  title: 'Отвязаться от тренера?',
                  message: 'Тренер потеряет доступ к профилю и назначениям.',
                  confirmText: 'Отвязаться',
                })
              )
                mutation.mutate({ path: '/api/v1/me/trainer', method: 'DELETE' });
            }}
          >
            Отвязаться
          </button>
        )}
      </div>
      <form
        className="stack top-gap auth-notice"
        onSubmit={(event) => {
          event.preventDefault();
          previewMutation.mutate(inviteInput);
        }}
      >
        <label className="field">
          <span>Ссылка или код приглашения</span>
          <input
            value={inviteInput}
            onChange={(event) => setInviteInput(event.target.value)}
            placeholder="Вставьте приглашение от тренера"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            aria-invalid={previewMutation.isError}
            aria-describedby={previewMutation.isError ? 'coach-invite-error' : undefined}
            required
          />
          {previewMutation.isError && (
            <small className="field-error" id="coach-invite-error" role="alert">
              {(previewMutation.error as Error).message}
            </small>
          )}
        </label>
        <button disabled={previewMutation.isPending}>
          {previewMutation.isPending ? 'Проверяем…' : 'Проверить приглашение'}
        </button>
      </form>
      {preview && (
        <div className="auth-notice stack top-gap" role="status">
          <div>
            <span className="eyebrow">Приглашает тренер</span>
            <h3>
              {preview.data.coach.full_name ||
                (preview.data.coach.username ? `@${preview.data.coach.username}` : 'Тренер')}
            </h3>
          </div>
          {preview.data.expires_at && (
            <p className="muted">
              Приглашение действует до {new Date(preview.data.expires_at).toLocaleString('ru-RU')}.
            </p>
          )}
          {preview.data.requires_trainer_change && (
            <p className="field-error" role="alert">
              Сейчас у вас подключён{' '}
              {preview.data.current_trainer?.full_name ||
                preview.data.current_trainer?.username ||
                'другой тренер'}
              . После подтверждения он потеряет доступ к вашему профилю.
            </p>
          )}
          {preview.data.already_current_trainer ? (
            <Badge>Этот тренер уже подключён</Badge>
          ) : (
            <div className="toolbar wrap">
              <button
                type="button"
                disabled={confirmMutation.isPending}
                onClick={async () => {
                  if (
                    preview.data.requires_trainer_change &&
                    !(await confirm({
                      title: 'Сменить тренера?',
                      message: 'Предыдущий тренер потеряет доступ к профилю и назначениям.',
                      confirmText: 'Сменить тренера',
                    }))
                  )
                    return;
                  confirmMutation.mutate(preview.token);
                }}
              >
                {confirmMutation.isPending
                  ? 'Подключаем…'
                  : preview.data.requires_trainer_change
                    ? 'Сменить тренера'
                    : 'Подтвердить подключение'}
              </button>
              <button type="button" className="secondary" onClick={() => setPreview(null)}>
                Отмена
              </button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
