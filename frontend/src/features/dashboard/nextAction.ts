import type {
  ProgressSummary,
  WeeklyCheckInCurrent,
  Workout,
  WorkoutComment,
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
  | 'profile';

export type NextActionReason =
  | 'resume_active_workout'
  | 'trainer_feedback'
  | 'scheduled_workout'
  | 'weekly_review'
  | 'no_active_program'
  | 'completed_workout'
  | 'rest_day'
  | 'profile_blocker';

export type NextActionTarget =
  | { type: 'today_workout'; workoutId: number }
  | { type: 'trainer_feedback'; workoutId: number; commentId: number }
  | { type: 'progress_workout'; workoutId: number }
  | { type: 'progress' }
  | { type: 'weekly_review' }
  | { type: 'programs'; mode: 'templates' | 'create' }
  | { type: 'nutrition' }
  | { type: 'activity' }
  | { type: 'profile' };

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
}: NextActionInputs): NextActionPlan {
  const feedback = feedbackAction(
    trainerComment,
    trainerComment?.workout_id ?? workout?.id ?? todayScheduleItem?.id,
  );
  const review = weeklyReview && !weeklyReview.existing ? weeklyReviewAction() : null;
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

  if (feedback) {
    const completed = workout?.status === 'completed' || completedToday;
    return {
      primary: feedback,
      secondary: secondary([
        completed ? review : plannedAction,
        completed ? workoutResultAction(workout?.id ?? todayScheduleItem?.id) : review,
      ]),
    };
  }

  if (workout?.status === 'completed' || completedToday) {
    if (review) {
      return {
        primary: review,
        secondary: secondary([workoutResultAction(workout?.id ?? todayScheduleItem?.id)]),
      };
    }
    return {
      primary: workoutResultAction(workout?.id ?? todayScheduleItem?.id),
      secondary: [],
    };
  }

  if (plannedAction) {
    return { primary: plannedAction, secondary: secondary([review]) };
  }

  if (review) {
    return { primary: review, secondary: [] };
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
    if (profileBlocksRecommendation) {
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

  return {
    primary: action(
      'nutrition',
      'Добавить питание',
      nextWorkout ? 'Поддержать план между тренировками' : 'Записать питание за сегодня',
      'rest_day',
      { type: 'nutrition' },
    ),
    secondary: [
      action(
        'activity',
        'Добавить активность',
        'Записать кардио или другую активность',
        'rest_day',
        { type: 'activity' },
      ),
    ],
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
    case 'weekly_review':
      return '/app?section=progress&weekly_review=1';
    case 'programs':
      return `/app?section=programs&start=${target.mode}`;
    case 'nutrition':
      return '/app?section=nutrition';
    case 'activity':
      return '/app?section=today&cardio=1';
    case 'profile':
      return '/app?section=profile#profile-fitness';
  }
}
