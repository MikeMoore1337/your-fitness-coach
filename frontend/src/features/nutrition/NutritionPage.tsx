import { useEffect, useRef, useState } from 'react';
import type { NutritionTarget } from '../../shared/api/types';
import type { components } from '../../shared/api/schema';
import { dateInputValue } from '../../shared/dateTime';
import { AppLink } from '../../shared/navigation/router';
import { NutritionDiary } from './NutritionDiary';
import { NutritionTargets } from './NutritionTargets';
import type { MealType } from './FoodPickerDialog';
import { AiCoachContextualEntry } from '../ai/AiCoachContextualEntry';
import { MealPlanner } from './MealPlanner';
import { GroceryList } from './GroceryList';

export function NutritionPage({
  initial,
  initialDate,
  initialMealType,
  initialFoodQuickAdd = false,
  initialHydrationOpen = false,
  onSaved,
  demoSafeMode = false,
  readOnlyEntries = false,
  readOnlyTargets = false,
  returnPath,
  timeZone,
}: {
  initial?: NutritionTarget | null;
  initialDate?: string;
  initialMealType?: MealType;
  initialFoodQuickAdd?: boolean;
  initialHydrationOpen?: boolean;
  onSaved?: () => void | Promise<void>;
  demoSafeMode?: boolean;
  readOnlyEntries?: boolean;
  readOnlyTargets?: boolean;
  returnPath?: string;
  timeZone?: string | null;
}) {
  const [view, setView] = useState<'day' | 'settings' | 'override'>('day');
  const dayView = useRef<HTMLDivElement>(null);
  const [selectedDate, setSelectedDate] = useState(
    initialDate || dateInputValue(new Date(), timeZone || undefined),
  );
  const [dateTarget, setDateTarget] = useState<NutritionTarget | null>(null);
  const [dateDayType, setDateDayType] =
    useState<components['schemas']['NutritionResolvedTargetResponse']['day_type']>(null);
  useEffect(() => {
    const openFromHash = () => {
      if (window.location.hash === '#nutrition-target-settings') setView('settings');
    };
    openFromHash();
    window.addEventListener('hashchange', openFromHash);
    return () => window.removeEventListener('hashchange', openFromHash);
  }, []);

  return (
    <div className="nutrition-experience">
      {returnPath && (
        <nav aria-label="Возврат к отчёту по питанию" className="nutrition-report-return">
          <AppLink className="button-link secondary-link" to={returnPath}>
            К отчёту по питанию
          </AppLink>
        </nav>
      )}
      <div className="nutrition-day-content" ref={dayView} hidden={view !== 'day'}>
        <NutritionDiary
          initialDate={initialDate}
          selectedDate={selectedDate}
          initialFoodQuickAdd={initialFoodQuickAdd}
          initialMealType={initialMealType}
          initialHydrationOpen={initialHydrationOpen}
          demoSafeMode={demoSafeMode}
          readOnlyEntries={readOnlyEntries}
          readOnlyTargets={readOnlyTargets}
          onOpenSettings={() => setView('settings')}
          onDateChange={setSelectedDate}
          onOverride={(date, target, dayType) => {
            setSelectedDate(date);
            setDateTarget(target);
            setDateDayType(dayType);
            setView('override');
          }}
          timeZone={timeZone}
        />
        {!demoSafeMode && (
          <MealPlanner initialDate={initialDate} readOnly={readOnlyEntries} timeZone={timeZone} />
        )}
        {!demoSafeMode && (
          <GroceryList initialDate={initialDate} readOnly={readOnlyEntries} timeZone={timeZone} />
        )}
        <AiCoachContextualEntry
          context={{ surface: 'nutrition', periodDays: 7 }}
          entryPoint="nutrition"
        />
      </div>
      {view !== 'day' && (
        <NutritionTargets
          mode={view}
          date={selectedDate}
          initial={initial}
          dateTarget={dateTarget}
          initialDayType={dateDayType}
          timeZone={timeZone}
          readOnly={readOnlyTargets}
          onClose={(savedDate) => {
            const returnTo = view;
            if (savedDate) setSelectedDate(savedDate);
            setView('day');
            requestAnimationFrame(() =>
              dayView.current
                ?.querySelector<HTMLButtonElement>(`[data-nutrition-focus="${returnTo}"]`)
                ?.focus(),
            );
          }}
          onSaved={onSaved}
        />
      )}
    </div>
  );
}
