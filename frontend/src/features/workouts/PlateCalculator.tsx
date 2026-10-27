import { useMemo, useState } from 'react';
import { Button } from '../../shared/ui/common';
import {
  calculatePlateLoad,
  DEFAULT_PLATE_INVENTORY,
  type PlateInventoryEntry,
} from './workoutExecution';

type PlateCalculatorProps = {
  disabled: boolean;
  initialTargetWeight: string;
};

type InventoryDraft = {
  weight: number;
  count: string;
};

const createInventoryDraft = (): InventoryDraft[] =>
  DEFAULT_PLATE_INVENTORY.map((entry) => ({ ...entry, count: String(entry.count) }));

function parseInput(value: string): number {
  return value.trim() === '' ? Number.NaN : Number(value);
}

function formatKilograms(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/\.?0+$/, '');
}

function formatSignedKilograms(value: number): string {
  if (value === 0) return '0 кг';
  return `${value > 0 ? '+' : '−'}${formatKilograms(Math.abs(value))} кг`;
}

export function PlateCalculator({ disabled, initialTargetWeight }: PlateCalculatorProps) {
  const [targetOverride, setTargetOverride] = useState<string | null>(null);
  const [barWeight, setBarWeight] = useState('20');
  const [inventoryDraft, setInventoryDraft] = useState(createInventoryDraft);
  const targetTotal = targetOverride ?? initialTargetWeight;

  const inventory = useMemo<PlateInventoryEntry[]>(
    () =>
      inventoryDraft.map((entry) => ({
        weight: entry.weight,
        count: parseInput(entry.count),
      })),
    [inventoryDraft],
  );
  const result = useMemo(
    () => calculatePlateLoad(parseInput(targetTotal), parseInput(barWeight), inventory),
    [barWeight, inventory, targetTotal],
  );

  const updateInventoryCount = (index: number, value: string) => {
    setInventoryDraft((current) =>
      current.map((entry, entryIndex) =>
        entryIndex === index ? { ...entry, count: value } : entry,
      ),
    );
  };

  return (
    <div className="active-workout-plate-calculator">
      <div className="active-workout-helper-inputs active-workout-plate-calculator__inputs">
        <label>
          <span>Целевой вес, кг</span>
          <input
            aria-label="Целевой вес, кг"
            disabled={disabled}
            inputMode="decimal"
            min="0"
            step="0.5"
            type="number"
            value={targetTotal}
            onChange={(event) => {
              setTargetOverride(event.target.value);
            }}
          />
        </label>
        <label>
          <span>Гриф, кг</span>
          <input
            aria-label="Гриф, кг"
            disabled={disabled}
            inputMode="decimal"
            min="0.5"
            step="0.5"
            type="number"
            value={barWeight}
            onChange={(event) => setBarWeight(event.target.value)}
          />
        </label>
      </div>

      <fieldset className="active-workout-plate-inventory">
        <legend>Доступные блины на сторону</legend>
        <Button
          className="active-workout-helper-chip"
          disabled={disabled}
          type="button"
          variant="secondary"
          onClick={() => setInventoryDraft(createInventoryDraft())}
        >
          Сбросить
        </Button>
        <p className="active-workout-helper-muted">
          Укажите количество каждого размера. Это временный расчёт только на текущем устройстве.
        </p>
        <div className="active-workout-plate-inventory__grid">
          {inventoryDraft.map((entry, index) => (
            <label key={entry.weight}>
              <span>{formatKilograms(entry.weight)} кг</span>
              <input
                aria-label={`Количество блинов ${formatKilograms(entry.weight)} кг на сторону`}
                disabled={disabled}
                inputMode="numeric"
                min="0"
                max="8"
                step="1"
                type="number"
                value={entry.count}
                onChange={(event) => updateInventoryCount(index, event.target.value)}
              />
            </label>
          ))}
        </div>
      </fieldset>

      {result.ok ? (
        <div
          className={`active-workout-plate-result ${result.calculation.exact ? 'is-exact' : 'is-nearest'}`}
          role="status"
          aria-live="polite"
        >
          <div className="active-workout-plate-result__state">
            <strong>
              {result.calculation.exact ? 'Точный результат' : 'Ближайший доступный результат'}
            </strong>
            {!result.calculation.exact && <span>Точного сочетания нет</span>}
          </div>
          <dl className="active-workout-plate-result__metrics">
            <div>
              <dt>Цель</dt>
              <dd>{formatKilograms(result.calculation.targetTotal)} кг</dd>
            </div>
            <div>
              <dt>Гриф</dt>
              <dd>{formatKilograms(result.calculation.barWeight)} кг</dd>
            </div>
            <div>
              <dt>Итог</dt>
              <dd>{formatKilograms(result.calculation.achievedTotal)} кг</dd>
            </div>
          </dl>
          <p>
            На сторону:{' '}
            <strong>
              {result.calculation.plates.length
                ? result.calculation.plates
                    .map((plate) => `${formatKilograms(plate)} кг`)
                    .join(' + ')
                : 'только гриф'}
            </strong>
          </p>
          <p>
            Разница к цели: <strong>{formatSignedKilograms(result.calculation.difference)}</strong>
          </p>
          {!result.calculation.exact && (
            <p className="active-workout-helper-muted">
              При равном расстоянии выбран меньший вес. Расчёт не меняет подход или историю.
            </p>
          )}
        </div>
      ) : (
        <p className="active-workout-plate-result active-workout-plate-result--error" role="alert">
          {result.error.message}
        </p>
      )}
    </div>
  );
}
