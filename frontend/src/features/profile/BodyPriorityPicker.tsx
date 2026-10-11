import { useQuery } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { ApiSchemas } from '../../shared/api/types';
import { ErrorState, LoadingState } from '../../shared/ui/common';

type BodyPriorityPreference = ApiSchemas['BodyPriorityPreference'];

export function isBodyPriorityComplete(value: BodyPriorityPreference | null | undefined): boolean {
  return value?.mode !== 'muscle_groups' || (value.muscle_group_ids?.length ?? 0) > 0;
}

export function BodyPriorityPicker({
  value,
  onChange,
}: {
  value: BodyPriorityPreference | null | undefined;
  onChange: (value: BodyPriorityPreference | null) => void;
}) {
  const options = useQuery({
    queryKey: ['body-priority-options'],
    queryFn: () =>
      api<ApiSchemas['BodyPriorityOptionsResponse']>('/api/v1/me/profile/body-priority-options'),
    staleTime: Number.POSITIVE_INFINITY,
  });
  const selected = new Set(value?.muscle_group_ids ?? []);

  return (
    <fieldset className="stack body-priority-picker">
      <legend>Приоритет развития</legend>
      <label className="field">
        <span>Как учитывать ваши предпочтения</span>
        <select
          value={value?.mode ?? ''}
          onChange={(event) => {
            if (!event.target.value) onChange(null);
            else if (event.target.value === 'balanced')
              onChange({ mode: 'balanced', muscle_group_ids: [] });
            else onChange({ mode: 'muscle_groups', muscle_group_ids: [] });
          }}
        >
          <option value="">Не указывать</option>
          <option value="balanced">Сбалансированное развитие</option>
          <option value="muscle_groups">Выбрать приоритетные группы</option>
        </select>
        <small className="field-hint">
          Это предпочтение для планирования и контекста прогресса, а не оценка «идеальных»
          пропорций.
        </small>
      </label>
      {value?.mode === 'muscle_groups' &&
        (options.isLoading ? (
          <LoadingState />
        ) : options.error ? (
          <ErrorState message={(options.error as Error).message} />
        ) : (
          <div className="body-priority-picker__grid" aria-label="Приоритетные мышечные группы">
            {options.data?.items.map((option) => (
              <label className="checkbox-row" data-yfc-choice="compact" key={option.id}>
                <input
                  type="checkbox"
                  checked={selected.has(option.id)}
                  onChange={(event) => {
                    const next = event.target.checked
                      ? [...selected, option.id]
                      : [...selected].filter((id) => id !== option.id);
                    onChange({ mode: 'muscle_groups', muscle_group_ids: next });
                  }}
                />
                <span>{option.name}</span>
              </label>
            ))}
          </div>
        ))}
      {value?.mode === 'muscle_groups' && (value.muscle_group_ids?.length ?? 0) === 0 && (
        <small className="field-error" role="alert">
          Выберите хотя бы одну мышечную группу.
        </small>
      )}
    </fieldset>
  );
}
