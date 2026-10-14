import { useQuery } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { NutritionTarget, NutritionTargetHistory } from '../../shared/api/types';
import { addCalendarDays, formatCalendarDate } from '../../shared/dateTime';
import { queryKeys } from '../../shared/queryKeys';
import { DisclosureIcon, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';

const sourceLabels: Record<NutritionTarget['source'], string> = {
  calculated: 'Рассчитано',
  manual: 'Указано вручную',
  trainer: 'Назначено тренером',
  adaptive: 'Адаптивная калибровка',
};

function dateLabel(value: string): string {
  return formatCalendarDate(value, { day: 'numeric', month: 'long', year: 'numeric' });
}

function authorLabel(target: NutritionTarget): string {
  const author = target.created_by ?? target.assigned_by;
  return author?.full_name || (author?.username ? `@${author.username}` : 'Владелец цели');
}

function macroDiff(previous: NutritionTarget, current: NutritionTarget): string[] {
  return [
    `Калории ${previous.calories} → ${current.calories} ккал`,
    `Белки ${previous.protein_g} → ${current.protein_g} г`,
    `Жиры ${previous.fat_g} → ${current.fat_g} г`,
    `Углеводы ${previous.carbs_g} → ${current.carbs_g} г`,
  ];
}

export function NutritionTargetHistory({ targetTelegramId }: { targetTelegramId?: number | null }) {
  const history = useQuery({
    queryKey: queryKeys.nutrition.targetHistory(targetTelegramId),
    queryFn: () =>
      api<NutritionTargetHistory>(
        `/api/v1/nutrition/targets/history${
          targetTelegramId ? `?target_telegram_user_id=${targetTelegramId}` : ''
        }`,
      ),
  });
  const items = history.data?.items ?? [];
  const current = items.find((item) => item.effective_to == null) ?? null;

  return (
    <section className="nutrition-target-history" aria-labelledby="nutrition-target-history-title">
      <div className="nutrition-section-heading">
        <div>
          <h3 id="nutrition-target-history-title">История ориентиров</h3>
          <p className="muted">
            Отчёты сравнивают каждый день с целью, которая действовала в ту дату.
          </p>
        </div>
      </div>
      {history.isLoading ? (
        <LoadingState label="Загружаем историю целей…" />
      ) : history.isError ? (
        <ErrorState
          message={(history.error as Error).message}
          retry={() => void history.refetch()}
        />
      ) : !current ? (
        <EmptyState
          title="История пока пуста"
          text="Сохраните рассчитанные или ручные ориентиры — первая версия появится здесь."
        />
      ) : (
        <>
          <div className="nutrition-current-target" aria-label="Текущие ориентиры КБЖУ">
            <div className="nutrition-current-target__heading">
              <div>
                <span className="badge">Текущая цель</span>
                <strong>{sourceLabels[current.source]}</strong>
              </div>
              <span>с {dateLabel(current.effective_from)}</span>
            </div>
            <div className="nutrition-current-target__metrics">
              <span>
                <strong>{current.calories}</strong> ккал
              </span>
              <span>
                <strong>{current.protein_g}</strong> Б
              </span>
              <span>
                <strong>{current.fat_g}</strong> Ж
              </span>
              <span>
                <strong>{current.carbs_g}</strong> У
              </span>
            </div>
            <p className="muted">Изменил: {authorLabel(current)}</p>
            {current.note && <p className="nutrition-target-note">{current.note}</p>}
          </div>

          <ol className="nutrition-target-history__list">
            {items.map((item, index) => {
              const previous = items[index + 1];
              const periodEnd =
                item.effective_to == null
                  ? 'по настоящее время'
                  : item.effective_to === item.effective_from
                    ? 'заменена в тот же день'
                    : `по ${dateLabel(addCalendarDays(item.effective_to, -1))}`;
              return (
                <li key={item.id}>
                  <details>
                    <summary className="yfc-disclosure-summary">
                      <span>
                        <strong>{dateLabel(item.effective_from)}</strong>
                        <small>
                          {sourceLabels[item.source]} · {item.calories} ккал
                        </small>
                      </span>
                      <DisclosureIcon />
                    </summary>
                    <div className="nutrition-target-history__details">
                      {previous ? (
                        <ul aria-label="Изменение КБЖУ">
                          {macroDiff(previous, item).map((difference) => (
                            <li key={difference}>{difference}</li>
                          ))}
                        </ul>
                      ) : (
                        <p>Первая сохранённая цель.</p>
                      )}
                      <p>Изменил: {authorLabel(item)}</p>
                      <p>
                        Период: с {dateLabel(item.effective_from)}, {periodEnd}
                      </p>
                      {item.note && <p className="nutrition-target-note">{item.note}</p>}
                    </div>
                  </details>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </section>
  );
}
