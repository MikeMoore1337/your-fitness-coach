import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import type { ExerciseSetupMemory, Workout } from '../../shared/api/types';
import { readStorage, removeStorage, writeStorage } from '../../shared/storage';
import { exerciseSetupMemoryDraftStorageKey } from '../../shared/userScopedStorage';
import { Button } from '../../shared/ui/common';

type DraftSnapshot = {
  body: string;
  expectedVersion: number | null;
};

type SetupMemoryStatus = {
  tone: 'success' | 'error' | 'offline';
  text: string;
};

function updateWorkoutSetupMemory(
  current: Workout | undefined,
  exerciseId: number,
  setupMemory: ExerciseSetupMemory | null,
): Workout | undefined {
  if (!current) return current;
  return {
    ...current,
    exercises: current.exercises.map((exercise) =>
      exercise.exercise_id === exerciseId ? { ...exercise, setup_memory: setupMemory } : exercise,
    ),
  };
}

export function ExerciseSetupMemory({
  canEdit,
  exerciseId,
  memory,
  userId,
}: {
  canEdit: boolean;
  exerciseId: number;
  memory: ExerciseSetupMemory | null;
  userId: number;
}) {
  const queryClient = useQueryClient();
  const storageKey = useMemo(
    () => exerciseSetupMemoryDraftStorageKey(userId, exerciseId),
    [exerciseId, userId],
  );
  const storedDraft = useMemo(
    () => readStorage<DraftSnapshot | null>(storageKey, null),
    [storageKey],
  );
  const [editing, setEditing] = useState(() => Boolean(storedDraft));
  const [displayMemory, setDisplayMemory] = useState(memory);
  const [draft, setDraft] = useState(() => storedDraft?.body ?? memory?.body ?? '');
  const [editingVersion, setEditingVersion] = useState<number | null>(
    () => storedDraft?.expectedVersion ?? memory?.version ?? null,
  );
  const [status, setStatus] = useState<SetupMemoryStatus | null>(null);

  useEffect(() => {
    if (editing) {
      writeStorage(storageKey, { body: draft, expectedVersion: editingVersion });
    }
  }, [draft, editing, editingVersion, storageKey]);

  const mutation = useMutation({
    mutationFn: async ({
      body,
      expectedVersion,
      method,
    }: {
      body?: string;
      expectedVersion: number | null;
      method: 'PUT' | 'DELETE';
    }) =>
      api<ExerciseSetupMemory | void>(
        `/api/v1/me/exercise-setup-memories/${exerciseId}${method === 'DELETE' ? `?expected_version=${expectedVersion}` : ''}`,
        {
          method,
          body: method === 'PUT' ? { body, expected_version: expectedVersion } : undefined,
        },
      ),
    onSuccess: (result, variables) => {
      const nextMemory = variables.method === 'DELETE' ? null : (result as ExerciseSetupMemory);
      setDisplayMemory(nextMemory);
      queryClient.setQueryData<Workout>(['workout', 'today'], (current) =>
        updateWorkoutSetupMemory(current, exerciseId, nextMemory),
      );
      removeStorage(storageKey);
      setEditing(false);
      setDraft(nextMemory?.body ?? '');
      setEditingVersion(nextMemory?.version ?? null);
      setStatus({
        tone: 'success',
        text: variables.method === 'DELETE' ? 'Настройка удалена.' : 'Настройка сохранена.',
      });
    },
    onError: (reason) => {
      if (reason instanceof ApiError && reason.status === 0) {
        setStatus({
          tone: 'offline',
          text: 'Черновик сохранён на устройстве. Сервер ещё не подтвердил сохранение.',
        });
        return;
      }
      if (reason instanceof ApiError && reason.status === 409) {
        setStatus({
          tone: 'error',
          text: 'Настройка уже изменилась. Обновите данные и проверьте черновик перед повтором.',
        });
        void queryClient.invalidateQueries({ queryKey: ['workout', 'today'] });
        return;
      }
      setStatus({
        tone: 'error',
        text: reason instanceof Error ? reason.message : 'Настройку не удалось сохранить.',
      });
    },
  });

  const openEditor = () => {
    setDraft(displayMemory?.body ?? '');
    setEditingVersion(displayMemory?.version ?? null);
    setStatus(null);
    setEditing(true);
  };

  const cancelEditing = () => {
    removeStorage(storageKey);
    setEditing(false);
    setStatus(null);
  };

  const save = () => {
    if (!draft.trim()) {
      setStatus({
        tone: 'error',
        text: 'Добавьте короткую настройку или отмените редактирование.',
      });
      return;
    }
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      setStatus({
        tone: 'offline',
        text: 'Черновик сохранён на устройстве. Сервер ещё не подтвердил сохранение.',
      });
      return;
    }
    mutation.mutate({
      body: draft,
      expectedVersion: editingVersion,
      method: 'PUT',
    });
  };

  if (!editing && !displayMemory && !status) {
    return (
      <section
        className="active-workout-setup-memory active-workout-setup-memory--empty"
        data-testid={`exercise-setup-memory-${exerciseId}`}
      >
        {canEdit ? (
          <Button type="button" variant="ghost" onClick={openEditor}>
            Добавить настройку
          </Button>
        ) : (
          <small>Личная настройка доступна после входа.</small>
        )}
      </section>
    );
  }

  return (
    <section
      className="active-workout-setup-memory"
      data-testid={`exercise-setup-memory-${exerciseId}`}
    >
      <div className="active-workout-setup-memory__head">
        <div>
          <span className="active-workout-setup-memory__label">Личная настройка</span>
          <p>Только для вас: например, положение сиденья, блок или хват.</p>
        </div>
        {!editing && canEdit && (
          <Button type="button" variant="secondary" onClick={openEditor}>
            {displayMemory ? 'Изменить настройку' : 'Добавить настройку'}
          </Button>
        )}
      </div>

      {editing ? (
        <div className="active-workout-setup-memory__editor">
          <label htmlFor={`exercise-setup-memory-${exerciseId}-input`}>Что важно настроить</label>
          <textarea
            id={`exercise-setup-memory-${exerciseId}-input`}
            maxLength={240}
            rows={2}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <span className="active-workout-setup-memory__counter">{draft.length}/240</span>
          <div className="active-workout-setup-memory__actions">
            <Button type="button" disabled={mutation.isPending} onClick={save}>
              Сохранить настройку
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={mutation.isPending}
              onClick={cancelEditing}
            >
              Отмена
            </Button>
            {displayMemory && (
              <Button
                type="button"
                variant="danger"
                disabled={mutation.isPending}
                onClick={() =>
                  mutation.mutate({ expectedVersion: editingVersion, method: 'DELETE' })
                }
              >
                Удалить
              </Button>
            )}
          </div>
        </div>
      ) : displayMemory ? (
        <div className="active-workout-setup-memory__value">
          <span>{displayMemory.body}</span>
          {!canEdit && <small>Изменение доступно после входа.</small>}
        </div>
      ) : (
        <p className="active-workout-setup-memory__empty">
          Пока не сохранено. Добавьте короткую подсказку, чтобы не вспоминать её в следующий раз.
          {!canEdit && ' Добавление доступно после входа.'}
        </p>
      )}

      {status && (
        <p
          className={`active-workout-setup-memory__status is-${status.tone}`}
          role={status.tone === 'error' ? 'alert' : 'status'}
          aria-live="polite"
        >
          {status.text}
        </p>
      )}
    </section>
  );
}
