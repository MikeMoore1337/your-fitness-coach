import { describe, expect, it } from 'vitest';
import type {
  ProgressSummary,
  WeeklyCheckInCurrent,
  Workout,
  WorkoutComment,
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

describe('selectNextAction', () => {
  it('keeps the active workout primary and feedback secondary', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: true,
      workout: workout('in_progress'),
      trainerComment: comment(),
    });

    expect(plan.primary.kind).toBe('active_workout');
    expect(plan.secondary.map((item) => item.kind)).toEqual(['trainer_feedback']);
  });

  it('promotes trainer feedback ahead of a no-program recommendation', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: false,
      trainerComment: comment(),
      weeklyReview: review(),
    });

    expect(plan.primary.kind).toBe('trainer_feedback');
    expect(plan.secondary.map((item) => item.kind)).toEqual(['weekly_review']);
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

  it('puts a ready program first and the custom builder second', () => {
    const plan = selectNextAction({ today, hasActiveProgram: false });

    expect(plan.primary.kind).toBe('ready_program');
    expect(plan.primary.title).toBe('Выбрать готовую программу');
    expect(plan.secondary.map((item) => item.kind)).toEqual(['create_program']);
  });

  it('uses a profile blocker only when no ready program path remains', () => {
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
    expect(ready.primary.kind).toBe('ready_program');
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
    });

    expect(plan.primary.kind).toBe('weekly_review');
    expect(plan.secondary.map((item) => item.kind)).toEqual(['workout_result']);
  });

  it('keeps deep links typed and bounded to existing app routes', () => {
    const plan = selectNextAction({
      today,
      hasActiveProgram: false,
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
    expect(plan.secondary.length).toBeLessThanOrEqual(2);
  });
});
