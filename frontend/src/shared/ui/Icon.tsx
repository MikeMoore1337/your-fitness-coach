import type { HTMLAttributes } from 'react';
export type IconName =
  | 'arrow-left'
  | 'arrow-right'
  | 'check'
  | 'chevron-down'
  | 'chevron-left'
  | 'chevron-right'
  | 'chevron-up'
  | 'close'
  | 'disclosure-closed'
  | 'disclosure-open'
  | 'external-link'
  | 'logout'
  | 'account-security'
  | 'ai-coach'
  | 'menu'
  | 'mini-app'
  | 'minus'
  | 'more-horizontal'
  | 'move-down'
  | 'move-up'
  | 'plus'
  | 'star-filled'
  | 'star'
  | 'sync'
  | 'theme-moon'
  | 'theme-sun'
  | 'timer'
  | 'trash'
  | 'web-app'
  | 'confidence-insufficient'
  | 'confidence-limited'
  | 'confidence-stale'
  | 'confidence-sufficient'
  | 'nav-admin'
  | 'nav-coach'
  | 'nav-exercise-catalog'
  | 'nav-knowledge'
  | 'nav-more'
  | 'nav-nutrition'
  | 'nav-plan'
  | 'nav-profile'
  | 'nav-progress'
  | 'nav-today'
  | 'achievement'
  | 'body-measurement'
  | 'body-weight'
  | 'calories'
  | 'checklist'
  | 'download'
  | 'edit'
  | 'exercise'
  | 'print'
  | 'protein'
  | 'water'
  | 'workout-volume'
  | 'error'
  | 'info'
  | 'loading'
  | 'permission-denied'
  | 'status-stale'
  | 'success'
  | 'warning'
  | 'week-cardio'
  | 'week-completed'
  | 'week-in-progress'
  | 'week-nutrition-complete'
  | 'week-nutrition-fasted'
  | 'week-nutrition-incomplete'
  | 'week-nutrition-missing'
  | 'week-planned'
  | 'week-rest'
  | 'week-skipped'
  | 'week-strength';
export interface IconProps extends Omit<HTMLAttributes<HTMLSpanElement>, 'children'> {
  label?: string;
  name: IconName;
  size?: 16 | 20 | 24;
}
const objects: Partial<Record<IconName, string>> = {
  'nav-today': 'calendar',
  'nav-plan': 'dumbbell',
  'week-strength': 'dumbbell',
  exercise: 'dumbbell',
  'nav-exercise-catalog': 'dumbbell',
  'nav-nutrition': 'nutrition',
  'nav-progress': 'progress',
  'nav-profile': 'profile',
  'nav-coach': 'profile',
  'nav-admin': 'profile',
  'nav-knowledge': 'ai',
  achievement: 'progress',
  'account-security': 'security',
  'ai-coach': 'ai',
  'theme-sun': 'sun',
  'theme-moon': 'moon',
  logout: 'logout',
};
/** Растровые объекты и локальные растровые версии прежних авторских служебных пиктограмм. */
export function Icon({ className = '', label, name, size = 24, ...props }: IconProps) {
  const object = objects[name];
  const src = (theme: string) =>
    object
      ? '/assets/icons/flat-' + object + '.webp'
      : '/assets/icons/action-' + name + '-' + theme + '.png';
  return (
    <span
      {...props}
      className={`yfc-icon yfc-icon--${size} ${object ? 'yfc-icon--object' : ''} ${className}`}
      data-icon={name}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      style={{ width: size, height: size, ...props.style }}
    >
      <img className="yfc-icon__light" src={src('light')} alt="" width={size} height={size} />
      <img className="yfc-icon__dark" src={src('dark')} alt="" width={size} height={size} />
    </span>
  );
}
