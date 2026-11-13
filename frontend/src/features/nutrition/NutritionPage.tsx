import { useCallback, useEffect, useRef, useState } from 'react';
import type { NutritionTarget } from '../../shared/api/types';
import type { components } from '../../shared/api/schema';
import { dateInputValue } from '../../shared/dateTime';
import { AppLink } from '../../shared/navigation/router';
import { Button, DisclosureIcon } from '../../shared/ui/common';
import { useTelegramOverlayBackButton } from '../../shared/telegram/useTelegramOverlayBackButton';
import { ClientNutritionProposals } from './CoachNutritionProposals';
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
  const [view, setView] = useState<'day' | 'settings' | 'override' | 'proposal'>('day');
  const root = useRef<HTMLDivElement>(null);
  const closeProposal = useCallback(() => {
    setView('day');
    requestAnimationFrame(() =>
      root.current?.querySelector<HTMLButtonElement>('.coach-nutrition-entry button')?.focus(),
    );
  }, []);
  useTelegramOverlayBackButton(view === 'proposal', closeProposal);
  const dayView = useRef<HTMLDivElement>(null);
  const extrasSettingsFocus = useRef(false);
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

  const openHydrationDestination = useCallback(
    (targetId: 'hydration-goal-details' | 'hydration-presets-details' | 'hydration-history-section') => {
      const target = dayView.current?.querySelector<HTMLElement>(`#${targetId}`);
      if (!target) return;
      if (target instanceof HTMLDetailsElement) target.open = true;
      requestAnimationFrame(() => {
        target.scrollIntoView({ block: 'center', behavior: 'instant' });
        target.querySelector<HTMLElement>('summary, h3')?.focus({ preventScroll: true });
      });
    },
    [],
  );

  return (
    <div className="nutrition-experience" ref={root}>
      {returnPath && (
        <nav aria-label="Возврат к отчёту по питанию" className="nutrition-report-return">
          <AppLink className="button-link secondary-link" to={returnPath}>
            К отчёту по питанию
          </AppLink>
        </nav>
      )}
      {!demoSafeMode && (view === 'day' || view === 'proposal') && (
        <ClientNutritionProposals
          focused={view === 'proposal'}
          onOpen={() => setView('proposal')}
          onClose={closeProposal}
        />
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
        <details className="nutrition-section-card nutrition-extras" data-testid="nutrition-extras">
          <summary className="nutrition-extras__summary yfc-disclosure-summary">
            <span className="nutrition-extras__label">
              <span className="eyebrow">Настройки и планирование</span>
              <strong>Дополнительно</strong>
            </span>
            <DisclosureIcon />
          </summary>
          <div className="nutrition-extras__body">
            <div
              className="nutrition-extras__links"
              role="group"
              aria-label="Дополнительные действия питания"
            >
              <Button
                data-nutrition-focus="extras-settings"
                type="button"
                variant="secondary"
                onClick={() => {
                  extrasSettingsFocus.current = true;
                  setView('settings');
                }}
              >
                Настройки КБЖУ
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => openHydrationDestination('hydration-goal-details')}
              >
                Личный ориентир
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => openHydrationDestination('hydration-presets-details')}
              >
                Мои кружки и бутылки
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => openHydrationDestination('hydration-history-section')}
              >
                История напитков
              </Button>
            </div>
            {!demoSafeMode && (
              <MealPlanner initialDate={initialDate} readOnly={readOnlyEntries} timeZone={timeZone} />
            )}
            {!demoSafeMode && (
              <GroceryList initialDate={initialDate} readOnly={readOnlyEntries} timeZone={timeZone} />
            )}
          </div>
        </details>
        <AiCoachContextualEntry
          context={{ surface: 'nutrition', periodDays: 7 }}
          entryPoint="nutrition"
        />
      </div>
      {view !== 'day' && view !== 'proposal' && (
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
            requestAnimationFrame(() => {
              const focusSelector =
                returnTo === 'settings' && extrasSettingsFocus.current
                  ? '[data-nutrition-focus="extras-settings"]'
                  : `[data-nutrition-focus="${returnTo}"]`;
              dayView.current?.querySelector<HTMLButtonElement>(focusSelector)?.focus();
              extrasSettingsFocus.current = false;
            });
          }}
          onSaved={onSaved}
        />
      )}
    </div>
  );
}
