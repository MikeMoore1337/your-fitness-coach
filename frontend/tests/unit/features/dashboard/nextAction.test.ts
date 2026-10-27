import { describe, expect, it } from 'vitest';
import type {
  ProgressSummary,
  WeeklyCheckInCurrent,
  Workout,
  WorkoutComment,
  WorkoutRecoveryState,
  WorkoutScheduleItem,
} from '../../../../src/shared/api/types';
import { nextActionHref, selectNextAction } from '../../../../src/features/dashboard/nextAction';

const today = '2026-09-17';

function workout(status: string): Workout {
  return {
    id: 41,
    status,
  } as unknown as Workout;
}

function schedule(status: string): WorkoutScheduleItem {
  return {
    id: 42,
    scheduled_date: today,
    status,
    title: 'Тренировка A',
  } as unknown as WorkoutScheduleItem;
}

function comment(): WorkoutComment {
  return { id: 7, workout_id: 41 } as unknown as WorkoutComment;
}

function review(): WeeklyCheckInCurrent {
  return { existing: false } as unknown as WeeklyCheckInCurrent;
}

function nextWorkout(): NonNullable<ProgressSummary['training']['next_workout']> {
  return {
    id: 50,
    scheduled_date: '2026-09-19',
    title: 'Тренировка B',
  } as NonNullable<ProgressSummary['training']['next_workout']>;
}

function recoveryState(status: WorkoutRecoveryState['status'] = 'missed'): WorkoutRecoveryState {
  return {
    status,
    missed_workouts:
      status === 'missed' ? [{ ...schedule('missed'), id: 99, scheduled_date: '2026-09-16' }] : [],
    next_workout: null,
    paused_program_id: status === 'paused' ? 12 : null,
    paused_program_title: status === 'paused' ? 'Мой план' : null,
  } as unknown as WorkoutRecoveryState;
}

describe('selectNextAction', () => {
  it('keeps the active workout primary and feedback secondary', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: true,
      workout: workout('in_progress'),
      trainerComment: comment(),
      recovery: recoveryState(),
    });

    expect(plan.primary.kind).toBe('active_workout');
    expect(plan.secondary.map((item) => item.kind)).toEqual(['trainer_feedback']);
  });

  it('keeps the program prerequisite ahead of optional trainer feedback', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: false,
      trainerComment: comment(),
      weeklyReview: review(),
    });

    expect(plan.primary.kind).toBe('ready_program');
    expect(plan.secondary.map((item) => item.kind)).toEqual(['create_program']);
  });

  it('uses a planned schedule item when the detailed workout is not loaded', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: true,
      todayScheduleItem: schedule('planned'),
    });

    expect(plan.primary.kind).toBe('scheduled_workout');
    expect(plan.primary.target).toEqual({ type: 'today_workout', workoutId: 42 });
  });

  it('keeps actionable trainer feedback ahead of a planned workout', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: true,
      todayScheduleItem: schedule('planned'),
      trainerComment: comment(),
      weeklyReview: review(),
    });

    expect(plan.primary.kind).toBe('trainer_feedback');
    expect(plan.secondary.map((item) => item.kind)).toEqual(['scheduled_workout', 'weekly_review']);
  });

  it('puts missed-workout recovery ahead of optional feedback and rest actions', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: true,
      trainerComment: comment(),
      recovery: recoveryState(),
    });

    expect(plan.primary.kind).toBe('workout_recovery');
    expect(plan.primary.reason).toBe('missed_workout');
    expect(plan.primary.target).toEqual({ type: 'workout_recovery', workoutId: 99 });
  });

  it('offers resume for a paused program before creating a new plan', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: false,
      recovery: recoveryState('paused'),
    });

    expect(plan.primary.kind).toBe('resume_program');
    expect(plan.primary.target).toEqual({ type: 'programs', mode: 'assigned' });
  });

  it('puts a ready program first and the custom builder second after profile readiness', () => {
    const plan = selectNextAction({ today, hasActiveProgram: false });

    expect(plan.primary.kind).toBe('ready_program');
    expect(plan.primary.title).toBe('Выбрать готовую программу');
    expect(plan.secondary.map((item) => item.kind)).toEqual(['create_program']);
  });

  it('puts the profile prerequisite first even when a ready program exists', () => {
    const blocker = selectNextAction({
      today,
      hasActiveProgram: false,
      profileBlocksRecommendation: true,
      readyProgramAvailable: false,
    });
    expect(blocker.primary.kind).toBe('profile');
    expect(blocker.secondary).toEqual([]);

    const ready = selectNextAction({
      today,
      hasActiveProgram: false,
      profileBlocksRecommendation: true,
      readyProgramAvailable: true,
    });
    expect(ready.primary.kind).toBe('profile');
  });

  it('falls back to record-only actions on a rest day', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: true,
      nextWorkout: nextWorkout(),
    });

    expect(plan.primary.kind).toBe('nutrition');
    expect(plan.secondary.map((item) => item.kind)).toEqual(['activity']);
  });

  it('offers the review before the completed workout result', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: true,
      workout: workout('completed'),
      weeklyReview: review(),
      hasNutritionConfirmation: true,
    });

    expect(plan.primary.kind).toBe('weekly_review');
    expect(plan.secondary.map((item) => item.kind)).toEqual(['workout_result']);
  });

  it('asks for a persisted nutrition or hydration confirmation before review', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: true,
      workout: workout('completed'),
      weeklyReview: review(),
    });

    expect(plan.primary.kind).toBe('nutrition');
    expect(plan.secondary.map((item) => item.kind)).toEqual(['weekly_review', 'workout_result']);
  });

  it('surfaces the server-selected weekly action without replacing urgent Today actions', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: true,
      weeklyReview: {
        existing: { id: 1 },
        progress_action: {
          kind: 'measurement',
          status: 'available',
          target: 'body',
          reason: 'weight_trend_insufficient',
          title: 'Добавить замер',
          detail: 'Добавьте повторный замер веса.',
          completed_at: null,
        },
      } as unknown as WeeklyCheckInCurrent,
    });

    expect(plan.primary.kind).toBe('nutrition');
    expect(plan.secondary[0]?.kind).toBe('progress_weekly_action');
    expect(nextActionHref(plan.secondary[0]!.target)).toBe(
      '/app?section=progress&progress_view=body',
    );
  });

  it('keeps deep links typed and bounded to existing app routes', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: true,
      trainerComment: comment(),
      weeklyReview: review(),
    });

    expect(nextActionHref(plan.primary.target)).toBe(
      '/app?section=progress&workout_id=41&comment_id=7',
    );
    expect(nextActionHref({ type: 'programs', mode: 'templates' })).toBe(
      '/app?section=programs&start=templates',
    );
    expect(nextActionHref({ type: 'progress' })).toBe('/app?section=progress');
    expect(nextActionHref({ type: 'workout_recovery', workoutId: 99 })).toBe(
      '/app?section=today&recovery_workout_id=99',
    );
    expect(plan.secondary.length).toBeLessThanOrEqual(2);
  });
});
