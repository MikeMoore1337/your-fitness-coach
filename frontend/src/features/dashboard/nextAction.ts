import type {
  ProgressSummary,
  ProgressWeeklyAction,
  WeeklyCheckInCurrent,
  Workout,
  WorkoutComment,
  WorkoutRecoveryState,
  WorkoutScheduleItem,
} from '../../shared/api/types';

export type NextActionKind =
  | 'active_workout'
  | 'trainer_feedback'
  | 'scheduled_workout'
  | 'weekly_review'
  | 'ready_program'
  | 'create_program'
  | 'workout_result'
  | 'nutrition'
  | 'activity'
  | 'profile'
  | 'progress_weekly_action'
  | 'workout_recovery'
  | 'resume_program';

export type NextActionReason =
  | 'resume_active_workout'
  | 'trainer_feedback'
  | 'scheduled_workout'
  | 'weekly_review'
  | 'nutrition_confirmation'
  | 'no_active_program'
  | 'completed_workout'
  | 'rest_day'
  | 'profile_blocker'
  | 'missed_workout'
  | 'resume_program'
  | 'weekly_action';

export type NextActionTarget =
  | { type: 'today_workout'; workoutId: number }
  | { type: 'trainer_feedback'; workoutId: number; commentId: number }
  | { type: 'progress_workout'; workoutId: number }
  | { type: 'progress' }
  | { type: 'progress_weekly_action'; destination: 'today' | 'nutrition' | 'body' | 'progress' }
  | { type: 'weekly_review' }
  | { type: 'programs'; mode: 'templates' | 'create' | 'assigned' }
  | { type: 'nutrition' }
  | { type: 'activity' }
  | { type: 'profile' }
  | { type: 'workout_recovery'; workoutId: number };

export interface NextAction {
  kind: NextActionKind;
  title: string;
  context: string;
  reason: NextActionReason;
  target: NextActionTarget;
}

export interface NextActionPlan {
  primary: NextAction;
  secondary: NextAction[];
}

type NextWorkout = NonNullable<ProgressSummary['training']['next_workout']>;

export interface NextActionInputs {
  today: string;
  hasActiveProgram: boolean;
  workout?: Workout;
  todayScheduleItem?: WorkoutScheduleItem;
  trainerComment?: WorkoutComment;
  weeklyReview?: WeeklyCheckInCurrent;
  lastCompletedWorkoutOn?: string | null;
  nextWorkout?: NextWorkout | null;
  profileBlocksRecommendation?: boolean;
  readyProgramAvailable?: boolean;
  hasNutritionConfirmation?: boolean;
  recovery?: WorkoutRecoveryState | null;
}

function action(
  kind: NextActionKind,
  title: string,
  context: string,
  reason: NextActionReason,
  target: NextActionTarget,
): NextAction {
  return { kind, title, context, reason, target };
}

function feedbackAction(
  comment: WorkoutComment | undefined,
  workoutId: number | undefined,
): NextAction | null {
  if (!comment || workoutId == null) return null;
  return action(
    'trainer_feedback',
    'Открыть комментарий',
    'Новый комментарий к тренировке',
    'trainer_feedback',
    { type: 'trainer_feedback', workoutId, commentId: comment.id },
  );
}

function workoutResultAction(workoutId: number | undefined): NextAction {
  return action(
    'workout_result',
    'Посмотреть итог',
    'Результат сохранён в прогрессе',
    'completed_workout',
    workoutId == null ? { type: 'progress' } : { type: 'progress_workout', workoutId },
  );
}

function scheduledWorkoutAction(workout: { id: number }): NextAction {
  return action(
    'scheduled_workout',
    'Начать тренировку',
    'Запланированная тренировка на сегодня',
    'scheduled_workout',
    { type: 'today_workout', workoutId: workout.id },
  );
}

function weeklyReviewAction(): NextAction {
  return action(
    'weekly_review',
    'Пройти короткую проверку',
    'Нагрузка, восстановление и соблюдение плана',
    'weekly_review',
    { type: 'weekly_review' },
  );
}

function nutritionAction(nextWorkout: NextWorkout | null | undefined): NextAction {
  return action(
    'nutrition',
    'Добавить питание',
    nextWorkout ? 'Поддержать план между тренировками' : 'Записать питание или воду за сегодня',
    'nutrition_confirmation',
    { type: 'nutrition' },
  );
}

function progressWeeklyActionAction(
  actionData: ProgressWeeklyAction | undefined,
): NextAction | null {
  if (!actionData || actionData.status !== 'available' || actionData.kind === 'none') return null;
  if (
    actionData.target !== 'today' &&
    actionData.target !== 'nutrition' &&
    actionData.target !== 'body' &&
    actionData.target !== 'progress'
  ) {
    return null;
  }
  return action('progress_weekly_action', actionData.title, actionData.detail, 'weekly_action', {
    type: 'progress_weekly_action',
    destination: actionData.target,
  });
}

function recoveryAction(workout: WorkoutRecoveryState['missed_workouts'][number]): NextAction {
  return action(
    'workout_recovery',
    'Вернуться к тренировке',
    `«${workout.title}» осталась невыполненной — можно восстановить план`,
    'missed_workout',
    { type: 'workout_recovery', workoutId: workout.id },
  );
}

function secondary(actions: Array<NextAction | null>): NextAction[] {
  return actions.filter((item): item is NextAction => item !== null).slice(0, 2);
}

export function selectNextAction({
  today,
  hasActiveProgram,
  workout,
  todayScheduleItem,
  trainerComment,
  weeklyReview,
  lastCompletedWorkoutOn,
  nextWorkout,
  profileBlocksRecommendation = false,
  readyProgramAvailable = !hasActiveProgram,
  hasNutritionConfirmation = false,
  recovery,
}: NextActionInputs): NextActionPlan {
  const feedback = feedbackAction(
    trainerComment,
    trainerComment?.workout_id ?? workout?.id ?? todayScheduleItem?.id,
  );
  const review = weeklyReview && !weeklyReview.existing ? weeklyReviewAction() : null;
  const weeklyAction = progressWeeklyActionAction(weeklyReview?.progress_action);
  const completedToday = !workout && lastCompletedWorkoutOn === today;
  const plannedWorkout =
    workout?.status === 'planned'
      ? workout
      : todayScheduleItem?.status === 'planned'
        ? todayScheduleItem
        : undefined;
  const plannedAction = plannedWorkout ? scheduledWorkoutAction(plannedWorkout) : null;

  if (workout?.status === 'in_progress') {
    return {
      primary: action(
        'active_workout',
        'Продолжить тренировку',
        'Вернуться к текущему подходу',
        'resume_active_workout',
        { type: 'today_workout', workoutId: workout.id },
      ),
      secondary: secondary([feedback]),
    };
  }

  if (recovery?.status === 'paused' && recovery.paused_program_id) {
    return {
      primary: action(
        'resume_program',
        'Продолжить программу',
        recovery.paused_program_title
          ? `Программа «${recovery.paused_program_title}» приостановлена`
          : 'Программа приостановлена',
        'resume_program',
        { type: 'programs', mode: 'assigned' },
      ),
      secondary: [],
    };
  }

  if (!hasActiveProgram && profileBlocksRecommendation) {
    return {
      primary: action(
        'profile',
        'Заполнить профиль',
        'Параметры нужны, чтобы подобрать программу',
        'profile_blocker',
        { type: 'profile' },
      ),
      secondary: [],
    };
  }

  if (!hasActiveProgram) {
    if (readyProgramAvailable) {
      return {
        primary: action(
          'ready_program',
          'Выбрать готовую программу',
          'Готовый план можно выбрать в разделе «План»',
          'no_active_program',
          { type: 'programs', mode: 'templates' },
        ),
        secondary: [
          action(
            'create_program',
            'Создать свою программу',
            'Собрать план под свой график',
            'no_active_program',
            { type: 'programs', mode: 'create' },
          ),
        ],
      };
    }
    return {
      primary: action(
        'create_program',
        'Создать свою программу',
        'Собрать план под свой график',
        'no_active_program',
        { type: 'programs', mode: 'create' },
      ),
      secondary: [],
    };
  }

  const missedWorkout = recovery?.status === 'missed' ? recovery.missed_workouts[0] : undefined;
  if (missedWorkout) {
    return { primary: recoveryAction(missedWorkout), secondary: secondary([feedback]) };
  }

  if (feedback) {
    const completed = workout?.status === 'completed' || completedToday;
    return {
      primary: feedback,
      secondary: secondary([
        completed ? weeklyAction : plannedAction,
        completed ? workoutResultAction(workout?.id ?? todayScheduleItem?.id) : review,
        completed ? review : weeklyAction,
      ]),
    };
  }

  if (workout?.status === 'completed' || completedToday) {
    if (!hasNutritionConfirmation) {
      return {
        primary: nutritionAction(nextWorkout),
        secondary: secondary([
          weeklyAction,
          review,
          workoutResultAction(workout?.id ?? todayScheduleItem?.id),
        ]),
      };
    }
    if (review) {
      return {
        primary: review,
        secondary: secondary([
          weeklyAction,
          workoutResultAction(workout?.id ?? todayScheduleItem?.id),
        ]),
      };
    }
    return {
      primary: workoutResultAction(workout?.id ?? todayScheduleItem?.id),
      secondary: secondary([weeklyAction]),
    };
  }

  if (plannedAction) {
    return { primary: plannedAction, secondary: secondary([weeklyAction, review]) };
  }

  if (review) {
    if (!hasNutritionConfirmation) {
      return {
        primary: nutritionAction(nextWorkout),
        secondary: secondary([weeklyAction, review]),
      };
    }
    return { primary: review, secondary: [] };
  }

  return {
    primary: nutritionAction(nextWorkout),
    secondary: secondary([
      weeklyAction,
      action(
        'activity',
        'Добавить активность',
        'Записать кардио или другую активность',
        'rest_day',
        { type: 'activity' },
      ),
    ]),
  };
}

export function nextActionHref(target: NextActionTarget): string {
  switch (target.type) {
    case 'today_workout':
      return '/app?section=today';
    case 'trainer_feedback':
      return `/app?section=progress&workout_id=${target.workoutId}&comment_id=${target.commentId}`;
    case 'progress_workout':
      return `/app?section=progress&workout_id=${target.workoutId}`;
    case 'progress':
      return '/app?section=progress';
    case 'progress_weekly_action':
      return target.destination === 'today'
        ? '/app?section=today'
        : target.destination === 'nutrition'
          ? '/app?section=nutrition'
          : target.destination === 'body'
            ? '/app?section=progress&progress_view=body'
            : '/app?section=progress';
    case 'weekly_review':
      return '/app?section=progress&weekly_review=1';
    case 'programs':
      return target.mode === 'assigned'
        ? '/app?section=programs'
        : `/app?section=programs&start=${target.mode}`;
    case 'nutrition':
      return '/app?section=nutrition';
    case 'activity':
      return '/app?section=today&cardio=1';
    case 'profile':
      return '/app?section=profile#profile-fitness';
    case 'workout_recovery':
      return `/app?section=today&recovery_workout_id=${target.workoutId}`;
  }
}
