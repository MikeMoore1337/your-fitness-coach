import { useCallback, useEffect, useRef, useState } from 'react';
import type { NutritionTarget } from '../../shared/api/types';
import type { components } from '../../shared/api/schema';
import { dateInputValue } from '../../shared/dateTime';
import { AppLink } from '../../shared/navigation/router';
import { Button } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useSemanticMotion } from '../../shared/ui/useSemanticMotion';
import { useTelegramOverlayBackButton } from '../../shared/telegram/useTelegramOverlayBackButton';
import { ClientNutritionProposals } from './CoachNutritionProposals';
import { NutritionDiary } from './NutritionDiary';
import { NutritionTargets, type NutritionTargetsDraft } from './NutritionTargets';
import type { MealType } from './FoodPickerDialog';
import { AiCoachContextualEntry } from '../ai/AiCoachContextualEntry';
import { MealPlanner } from './MealPlanner';
import { GroceryList } from './GroceryList';
import { NutritionImport } from './NutritionImport';

export function NutritionPage({
  initial,
  initialDate,
  initialMealType,
  initialFoodQuickAdd = false,
  initialHydrationOpen = false,
  onSelectedDateChange,
  initialTargetsDraft,
  onTargetsDraftChange,
  initialMealExpansion,
  onMealExpansionChange,
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
  onSelectedDateChange?: (date: string) => void;
  initialMealExpansion?: Partial<Record<MealType, boolean>>;
  onMealExpansionChange?: (value: Partial<Record<MealType, boolean>>) => void;
  initialTargetsDraft?: Record<string, NutritionTargetsDraft | undefined>;
  onTargetsDraftChange?: (
    mode: 'settings' | 'override',
    date: string,
    draft: NutritionTargetsDraft | null,
  ) => void;
  onSaved?: () => void | Promise<void>;
  demoSafeMode?: boolean;
  readOnlyEntries?: boolean;
  readOnlyTargets?: boolean;
  returnPath?: string;
  timeZone?: string | null;
}) {
  const [view, setView] = useState<'day' | 'settings' | 'override' | 'proposal' | 'import'>('day');
  const viewMotion = useSemanticMotion<HTMLDivElement>(view, { animateInitial: false });
  const rememberTargetsDraft = useCallback(
    (draft: NutritionTargetsDraft) => {
      onTargetsDraftChange?.(draft.mode, draft.contextDate, draft);
    },
    [onTargetsDraftChange],
  );
  const root = useRef<HTMLDivElement>(null);
  const dayScroll = useRef<number | null>(null);
  const restoreFrame = useRef<number | null>(null);
  const openLocal = useCallback((next: 'settings' | 'override' | 'proposal' | 'import') => {
    if (restoreFrame.current !== null) window.cancelAnimationFrame(restoreFrame.current);
    restoreFrame.current = null;
    dayScroll.current = window.scrollY;
    setView(next);
  }, []);
  const restoreDay = useCallback((after?: () => void) => {
    if (restoreFrame.current !== null) window.cancelAnimationFrame(restoreFrame.current);
    setView('day');
    restoreFrame.current = window.requestAnimationFrame(() => {
      if (dayScroll.current !== null)
        window.scrollTo({ top: dayScroll.current, behavior: 'instant' });
      dayScroll.current = null;
      restoreFrame.current = null;
      after?.();
    });
  }, []);
  useEffect(
    () => () => {
      if (restoreFrame.current !== null) window.cancelAnimationFrame(restoreFrame.current);
    },
    [],
  );
  const closeProposal = useCallback(() => {
    restoreDay(() =>
      root.current
        ?.querySelector<HTMLButtonElement>('.coach-nutrition-entry button')
        ?.focus({ preventScroll: true }),
    );
  }, [restoreDay]);
  useTelegramOverlayBackButton(view === 'proposal', closeProposal);
  const dayView = useRef<HTMLDivElement>(null);
  const extrasSettingsFocus = useRef(false);
  const [selectedDate, setSelectedDate] = useState(
    initialDate || dateInputValue(new Date(), timeZone || undefined),
  );
  useEffect(() => {
    onSelectedDateChange?.(selectedDate);
  }, [onSelectedDateChange, selectedDate]);
  const [dateTarget, setDateTarget] = useState<NutritionTarget | null>(null);
  const [dateDayType, setDateDayType] =
    useState<components['schemas']['NutritionResolvedTargetResponse']['day_type']>(null);
  useEffect(() => {
    const openFromHash = () => {
      if (window.location.hash === '#nutrition-target-settings') openLocal('settings');
    };
    openFromHash();
    window.addEventListener('hashchange', openFromHash);
    return () => window.removeEventListener('hashchange', openFromHash);
  }, [openLocal]);

  return (
    <div
      className="nutrition-experience"
      ref={root}
      id={viewMotion.elementId}
      data-motion-phase={viewMotion.motionPhase}
      data-motion-revision={viewMotion.motionRevision}
      onAnimationEnd={viewMotion.onMotionAnimationEnd}
    >
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
          onOpen={() => openLocal('proposal')}
          onClose={closeProposal}
        />
      )}
      <div className="nutrition-day-content" ref={dayView} hidden={view !== 'day'}>
        <NutritionDiary
          initialDate={initialDate}
          selectedDate={selectedDate}
          initialFoodQuickAdd={initialFoodQuickAdd}
          initialMealType={initialMealType}
          initialMealExpansion={initialMealExpansion}
          onMealExpansionChange={onMealExpansionChange}
          initialHydrationOpen={initialHydrationOpen}
          demoSafeMode={demoSafeMode}
          readOnlyEntries={readOnlyEntries}
          readOnlyTargets={readOnlyTargets}
          onOpenSettings={() => openLocal('settings')}
          onDateChange={setSelectedDate}
          onOverride={(date, target, dayType) => {
            setSelectedDate(date);
            setDateTarget(target);
            setDateDayType(dayType);
            openLocal('override');
          }}
          timeZone={timeZone}
        />
        <section
          className="nutrition-extras"
          data-testid="nutrition-extras"
          aria-labelledby="nutrition-extras-title"
        >
          <header className="nutrition-extras__label">
            <span className="eyebrow">Настройки и инструменты</span>
            <h2 id="nutrition-extras-title">Дополнительно</h2>
          </header>
          <div className="nutrition-extras__body">
            <Button
              className="nutrition-extras__setting"
              data-nutrition-focus="extras-settings"
              type="button"
              variant="secondary"
              onClick={() => {
                extrasSettingsFocus.current = true;
                openLocal('settings');
              }}
            >
              <span>
                <strong>Настройки КБЖУ</strong>
                <small>Рассчитать ориентиры или указать вручную</small>
              </span>
              <Icon name="chevron-right" size={20} />
            </Button>
            {!demoSafeMode && !readOnlyEntries && (
              <Button
                className="nutrition-extras__setting"
                type="button"
                variant="secondary"
                onClick={() => openLocal('import')}
              >
                <span>
                  <strong>Импорт питания</strong>
                  <small>Добавить продукты из экспорта FatSecret</small>
                </span>
                <Icon name="chevron-right" size={20} />
              </Button>
            )}
            {!demoSafeMode && (
              <MealPlanner
                initialDate={initialDate}
                readOnly={readOnlyEntries}
                timeZone={timeZone}
              />
            )}
            {!demoSafeMode && (
              <GroceryList
                initialDate={initialDate}
                readOnly={readOnlyEntries}
                timeZone={timeZone}
              />
            )}
          </div>
        </section>
        <AiCoachContextualEntry
          context={{ surface: 'nutrition', periodDays: 7 }}
          entryPoint="nutrition"
        />
      </div>
      {view === 'import' && (
        <div className="nutrition-local-context">
          <NutritionImport diaryDate={selectedDate} onClose={() => restoreDay()} />
        </div>
      )}
      {view !== 'day' && view !== 'proposal' && view !== 'import' && (
        <div className="nutrition-local-context">
          <NutritionTargets
            mode={view}
            date={selectedDate}
            initial={initial}
            dateTarget={dateTarget}
            initialDayType={dateDayType}
            timeZone={timeZone}
            readOnly={readOnlyTargets}
            initialDraft={initialTargetsDraft?.[`${view}:${selectedDate}`]}
            onDraftChange={rememberTargetsDraft}
            onClose={(savedDate) => {
              const returnTo = view;
              if (savedDate) setSelectedDate(savedDate);
              restoreDay(() => {
                const focusSelector =
                  returnTo === 'settings' && extrasSettingsFocus.current
                    ? '[data-nutrition-focus="extras-settings"]'
                    : `[data-nutrition-focus="${returnTo}"]`;
                dayView.current
                  ?.querySelector<HTMLButtonElement>(focusSelector)
                  ?.focus({ preventScroll: true });
                extrasSettingsFocus.current = false;
              });
            }}
            onSaved={async () => {
              onTargetsDraftChange?.(view, selectedDate, null);
              await onSaved?.();
            }}
          />
        </div>
      )}
    </div>
  );
}
