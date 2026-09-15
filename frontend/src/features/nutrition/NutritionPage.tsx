import type { NutritionTarget } from '../../shared/api/types';
import { AppLink } from '../../shared/navigation/router';
import { NutritionDiary } from './NutritionDiary';
import { NutritionForm } from './NutritionForm';
import type { MealType } from './FoodPickerDialog';

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
  return (
    <div className="nutrition-experience">
      {returnPath && (
        <nav aria-label="Возврат к отчёту по питанию" className="nutrition-report-return">
          <AppLink className="button-link secondary-link" to={returnPath}>
            К отчёту по питанию
          </AppLink>
        </nav>
      )}
      <NutritionDiary
        initialDate={initialDate}
        initialFoodQuickAdd={initialFoodQuickAdd}
        initialMealType={initialMealType}
        initialHydrationOpen={initialHydrationOpen}
        demoSafeMode={demoSafeMode}
        readOnlyEntries={readOnlyEntries}
        timeZone={timeZone}
      />
      <div id="nutrition-target-settings" className="nutrition-target-settings">
        <NutritionForm
          initial={initial}
          readOnly={readOnlyTargets}
          timeZone={timeZone}
          onSaved={onSaved}
        />
      </div>
    </div>
  );
}
