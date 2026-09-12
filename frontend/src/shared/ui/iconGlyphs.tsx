import type { ReactNode } from 'react';

/** Общая геометрия YFC: только статические JSX-элементы, без внешнего SVG/HTML. */
const glyphs = {
  'arrow-left': (
    <>
      <line x1="4" y1="12" x2="20" y2="12" />
      <path d="M9 6l-6 6 6 6" />
    </>
  ),
  'arrow-right': (
    <>
      <line x1="4" y1="12" x2="20" y2="12" />
      <path d="M15 6l6 6-6 6" />
    </>
  ),
  check: (
    <>
      <path d="M5 12.5l4.2 4.2L19.5 6.5" />
    </>
  ),
  'chevron-down': (
    <>
      <polyline points="5,9 12,16 19,9" />
    </>
  ),
  'chevron-left': (
    <>
      <polyline points="15,5 8,12 15,19" />
    </>
  ),
  'chevron-right': (
    <>
      <polyline points="9,5 16,12 9,19" />
    </>
  ),
  'chevron-up': (
    <>
      <polyline points="5,15 12,8 19,15" />
    </>
  ),
  close: (
    <>
      <line x1="5" y1="5" x2="19" y2="19" />
      <line x1="19" y1="5" x2="5" y2="19" />
    </>
  ),
  'external-link': (
    <>
      <rect x="3" y="7" width="14" height="14" rx="2" />
      <line x1="10" y1="14" x2="21" y2="3" />
      <path d="M14 3h7v7" />
    </>
  ),
  logout: (
    <>
      <path d="M10 4H5.5A2.5 2.5 0 0 0 3 6.5v11A2.5 2.5 0 0 0 5.5 20H10" />
      <line x1="9" y1="12" x2="21" y2="12" />
      <path d="M17 8l4 4-4 4" />
    </>
  ),
  menu: (
    <>
      <line x1="4" y1="6" x2="20" y2="6" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="18" x2="20" y2="18" />
    </>
  ),
  'mini-app': (
    <>
      <rect x="3" y="4" width="18" height="14" rx="2.5" />
      <path d="M7 18v2.5l3.5-2.5H18" />
      <line x1="7" y1="9" x2="17" y2="9" />
      <line x1="7" y1="13" x2="13" y2="13" />
    </>
  ),
  minus: (
    <>
      <line x1="4" y1="12" x2="20" y2="12" />
    </>
  ),
  'more-horizontal': (
    <>
      <circle cx="6" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="18" cy="12" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  'move-down': (
    <>
      <line x1="12" y1="4" x2="12" y2="19" />
      <path d="M6.5 13.5L12 19l5.5-5.5" />
      <line x1="5" y1="2.5" x2="19" y2="2.5" />
    </>
  ),
  'move-up': (
    <>
      <line x1="12" y1="20" x2="12" y2="5" />
      <path d="M6.5 10.5L12 5l5.5 5.5" />
      <line x1="5" y1="21.5" x2="19" y2="21.5" />
    </>
  ),
  plus: (
    <>
      <line x1="12" y1="4" x2="12" y2="20" />
      <line x1="4" y1="12" x2="20" y2="12" />
    </>
  ),
  'star-filled': (
    <>
      <polygon points="12,3 14.7,8.5 20.8,9.4 16.4,13.7 17.4,20 12,17 6.6,20 7.6,13.7 3.2,9.4 9.3,8.5" />
    </>
  ),
  star: (
    <>
      <polygon points="12,3 14.7,8.5 20.8,9.4 16.4,13.7 17.4,20 12,17 6.6,20 7.6,13.7 3.2,9.4 9.3,8.5" />
    </>
  ),
  sync: (
    <>
      <path d="M5 7a8 8 0 0 1 13.2-1.6L20 7.2" />
      <path d="M20 3.8v3.4h-3.4" />
      <path d="M19 17a8 8 0 0 1-13.2 1.6L4 16.8" />
      <path d="M4 20.2v-3.4h3.4" />
    </>
  ),
  'theme-moon': (
    <>
      <path d="M18.7 15.5A7.8 7.8 0 0 1 8.5 5.3 8.1 8.1 0 1 0 18.7 15.5Z" />
    </>
  ),
  'theme-sun': (
    <>
      <circle cx="12" cy="12" r="3.5" />
      <line x1="12" y1="2.5" x2="12" y2="5" />
      <line x1="12" y1="19" x2="12" y2="21.5" />
      <line x1="2.5" y1="12" x2="5" y2="12" />
      <line x1="19" y1="12" x2="21.5" y2="12" />
      <line x1="5.3" y1="5.3" x2="7" y2="7" />
      <line x1="17" y1="17" x2="18.7" y2="18.7" />
      <line x1="18.7" y1="5.3" x2="17" y2="7" />
      <line x1="7" y1="17" x2="5.3" y2="18.7" />
    </>
  ),
  timer: (
    <>
      <circle cx="12" cy="13" r="7" />
      <line x1="12" y1="13" x2="15.3" y2="10.5" />
      <line x1="9.5" y1="3" x2="14.5" y2="3" />
      <line x1="12" y1="3" x2="12" y2="6" />
      <path d="M17.5 6.5l1.5-1.5" />
    </>
  ),
  trash: (
    <>
      <path d="M5 7h14M9 7V4.5h6V7M7 7l1 13h8l1-13M10 10.5v6M14 10.5v6" />
    </>
  ),
  'web-app': (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.8 9h16.4M3.8 15h16.4M12 3.5c2.2 2.2 3.4 5 3.4 8.5S14.2 18.3 12 20.5M12 3.5C9.8 5.7 8.6 8.5 8.6 12s1.2 6.3 3.4 8.5" />
    </>
  ),
  'confidence-insufficient': (
    <>
      <rect x="4" y="5" width="16" height="14" rx="3" />
      <circle cx="8" cy="13.5" r="1" />
      <circle cx="12" cy="9" r="1" />
      <circle cx="16" cy="13.5" r="1" />
      <line x1="6" y1="17" x2="9" y2="17" />
      <line x1="15" y1="17" x2="18" y2="17" />
    </>
  ),
  'confidence-limited': (
    <>
      <rect x="4" y="4" width="16" height="16" rx="3" />
      <line x1="7.5" y1="16" x2="7.5" y2="13" />
      <line x1="12" y1="16" x2="12" y2="9" />
      <line x1="16.5" y1="16" x2="16.5" y2="6" />
      <line x1="6" y1="18" x2="18" y2="18" />
    </>
  ),
  'confidence-stale': (
    <>
      <path d="M12 3l7 2.7v5.5c0 4.4-2.7 7.7-7 9.8-4.3-2.1-7-5.4-7-9.8V5.7Z" />
      <circle cx="12" cy="11.5" r="3.6" />
      <line x1="12" y1="11.5" x2="12" y2="9.2" />
      <line x1="12" y1="11.5" x2="14" y2="12.7" />
      <path d="M15.2 8.8h2.2v2.2" />
    </>
  ),
  'confidence-sufficient': (
    <>
      <path d="M12 3l7 2.7v5.5c0 4.4-2.7 7.7-7 9.8-4.3-2.1-7-5.4-7-9.8V5.7Z" />
      <path d="M8.3 11.6l2.3 2.4 5.1-5.2" />
    </>
  ),
  'nav-admin': (
    <>
      <path d="M12 2.8l7 2.8v5.5c0 4.7-2.7 8-7 10.1-4.3-2.1-7-5.4-7-10.1V5.6Z" />
      <circle cx="12" cy="11.2" r="2.2" />
      <path d="M12 7.6v1.2M12 13.6V15M8.4 11.2h1.2M14.4 11.2h1.2M9.5 8.7l.9.9M13.6 12.8l.9.9M14.5 8.7l-.9.9M10.4 12.8l-.9.9" />
    </>
  ),
  'nav-coach': (
    <>
      <circle cx="8" cy="7.5" r="2.7" />
      <path d="M3.6 15.6c.5-3 2-4.7 4.4-4.7s3.9 1.7 4.4 4.7" />
      <path d="M13.8 7.4h4.6c1.2 0 2.1.9 2.1 2.1v3.2c0 1.2-.9 2.1-2.1 2.1h-1.9l-2.7 2v-2h-.1c-1.2 0-2.1-.9-2.1-2.1V9.5c0-1.2.9-2.1 2.2-2.1Z" />
      <line x1="15" y1="10" x2="18" y2="10" />
      <line x1="15" y1="12" x2="17" y2="12" />
    </>
  ),
  'nav-exercise-catalog': (
    <>
      <path d="M3.5 8.2V18A2 2 0 0 0 5.5 20h13a2 2 0 0 0 2-2V9.5a2 2 0 0 0-2-2h-7.2L9.2 5.3H5.5a2 2 0 0 0-2 2v.9Z" />
      <rect x="6.5" y="11.5" width="2.5" height="5" rx="1" />
      <rect x="15" y="11.5" width="2.5" height="5" rx="1" />
      <line x1="9" y1="14" x2="15" y2="14" />
    </>
  ),
  'nav-knowledge': (
    <>
      <path d="M3.5 5.2c2.8-.9 5.6-.5 8.5 1.4v13c-2.9-1.9-5.7-2.3-8.5-1.4Z" />
      <path d="M20.5 5.2c-2.8-.9-5.6-.5-8.5 1.4v13c2.9-1.9 5.7-2.3 8.5-1.4Z" />
      <line x1="12" y1="6.6" x2="12" y2="19.6" />
    </>
  ),
  'nav-nutrition': (
    <>
      <path d="M4 12h16c-.7 5-3.3 8-8 8s-7.3-3-8-8Z" />
      <path d="M6 12c.4-2.5 2.2-4 4.5-4 1.3 0 2 .4 3 .8 1.2-1.5 2.5-2.3 4.3-2.3" />
      <path d="M16.2 7.7c.4-1.9 1.6-3.2 3.3-3.7-.1 1.9-1.1 3.2-3.3 3.7Z" />
      <line x1="7" y1="16" x2="17" y2="16" />
    </>
  ),
  'nav-profile': (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M4.5 21a7.5 7.5 0 0 1 15 0" />
    </>
  ),
  'nav-progress': (
    <>
      <line x1="4" y1="20" x2="4" y2="13" />
      <line x1="9" y1="20" x2="9" y2="9" />
      <line x1="14" y1="20" x2="14" y2="11" />
      <line x1="19" y1="20" x2="19" y2="5" />
      <line x1="2.5" y1="20" x2="21.5" y2="20" />
      <path d="M4 9.5l4-3 4 2 6-5" />
      <path d="M16.5 3.5H18.8V5.8" />
    </>
  ),
  'nav-today': (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M8 3v4M16 3v4M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01" />
    </>
  ),
  achievement: (
    <>
      <circle cx="12" cy="9" r="6" />
      <path d="m9 14-2 8 5-3 5 3-2-8M9 9l2 2 4-4" />
    </>
  ),
  'body-measurement': (
    <>
      <path d="M8.2 3.2c.4 1.7-.2 3.2-1.6 4.3C5.4 8.5 5 10 5 11.8v6.7M15.8 3.2c-.4 1.7.2 3.2 1.6 4.3 1.2 1 1.6 2.5 1.6 4.3v6.7M8 10.5c.7 1 1 2.2 1 3.7M16 10.5c-.7 1-1 2.2-1 3.7" />
      <rect x="4" y="15.2" width="16" height="4.3" rx="1" />
      <path d="M7 15.2v2.2M10 15.2v1.4M13 15.2v2.2M16 15.2v1.4M6 19.5v2M18 19.5v2" />
    </>
  ),
  'body-weight': (
    <>
      <rect x="4" y="5" width="16" height="15" rx="3" />
      <path d="M8 10a4 4 0 0 1 8 0" />
      <line x1="12" y1="10" x2="14.2" y2="8.2" />
      <line x1="8" y1="16" x2="16" y2="16" />
    </>
  ),
  calories: (
    <>
      <path d="M13 2c1 5-3 6-3 10 0 2 1 3 2 4-4-1-5-4-3-7-4 4-4 8-1 11a7 7 0 0 0 12-5c0-5-3-9-8-13Z" />
    </>
  ),
  checklist: (
    <>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M9 3V2h6v3H9ZM8 10l1.5 1.5L12 9M14 10h3M8 16l1.5 1.5L12 15M14 16h3" />
    </>
  ),
  download: (
    <>
      <path d="M12 3v12M7 10l5 5 5-5M4 20h16" />
    </>
  ),
  edit: (
    <>
      <path d="M4 20h4l11-11a2.8 2.8 0 0 0-4-4L4 16v4Z" />
      <path d="m13.5 6.5 4 4" />
    </>
  ),
  exercise: (
    <>
      <line x1="4" y1="9" x2="4" y2="15" />
      <line x1="7" y1="7" x2="7" y2="17" />
      <line x1="17" y1="7" x2="17" y2="17" />
      <line x1="20" y1="9" x2="20" y2="15" />
      <line x1="7" y1="12" x2="17" y2="12" />
    </>
  ),
  print: (
    <>
      <rect x="6" y="3" width="12" height="5" rx="1.5" />
      <rect x="6" y="15" width="12" height="6" rx="1.5" />
      <path d="M6 17H4.5A2.5 2.5 0 0 1 2 14.5v-4A2.5 2.5 0 0 1 4.5 8h15A2.5 2.5 0 0 1 22 10.5v4a2.5 2.5 0 0 1-2.5 2.5H18" />
      <circle cx="18.5" cy="11.5" r="0.7" fill="currentColor" stroke="none" />
    </>
  ),
  protein: (
    <>
      <path d="M8 3h8l1 4 3 3-2 11H6L4 10l3-3Z" />
      <path d="M9 12h6M10 16h4" />
    </>
  ),
  water: (
    <>
      <path d="M12 3.5s6.5 7.1 6.5 11.2A6.5 6.5 0 0 1 5.5 14.7C5.5 10.6 12 3.5 12 3.5Z" />
      <path d="M9 15.2c.7 1.3 1.7 2 3 2" />
    </>
  ),
  'workout-volume': (
    <>
      <line x1="4" y1="7" x2="4" y2="17" />
      <line x1="7" y1="5" x2="7" y2="19" />
      <line x1="17" y1="5" x2="17" y2="19" />
      <line x1="20" y1="7" x2="20" y2="17" />
      <line x1="7" y1="12" x2="17" y2="12" />
      <path d="M8 21l3-3 2 2 3-4" />
      <path d="M14.5 16H16v1.5" />
    </>
  ),
  error: (
    <>
      <polygon points="8,3 16,3 21,8 21,16 16,21 8,21 3,16 3,8" />
      <line x1="8.5" y1="8.5" x2="15.5" y2="15.5" />
      <line x1="15.5" y1="8.5" x2="8.5" y2="15.5" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="7.2" r="0.7" fill="currentColor" stroke="none" />
      <line x1="12" y1="10.5" x2="12" y2="16.8" />
      <line x1="10.5" y1="16.8" x2="13.5" y2="16.8" />
    </>
  ),
  loading: (
    <>
      <circle cx="6" cy="12" r="1.3" />
      <circle cx="12" cy="12" r="1.3" opacity="0.65" />
      <circle cx="18" cy="12" r="1.3" opacity="0.35" />
    </>
  ),
  'permission-denied': (
    <>
      <rect x="5" y="10" width="14" height="10" rx="2.3" />
      <path d="M8 10V7.5a4 4 0 0 1 7.3-2.2" />
      <line x1="4" y1="4" x2="20" y2="20" />
    </>
  ),
  'status-stale': (
    <>
      <circle cx="11" cy="12" r="7" />
      <line x1="11" y1="12" x2="11" y2="7.5" />
      <line x1="11" y1="12" x2="14.3" y2="13.8" />
      <path d="M16.5 5.7H20v3.5" />
      <path d="M20 5.7l-3 3" />
    </>
  ),
  success: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M7.5 12.2l3 3.1 6.2-6.5" />
    </>
  ),
  warning: (
    <>
      <polygon points="12,3 21,20 3,20" />
      <line x1="12" y1="8" x2="12" y2="13.5" />
      <circle cx="12" cy="17" r="0.7" fill="currentColor" stroke="none" />
    </>
  ),
  'week-cardio': (
    <>
      <path d="M12 20s-7-4.4-7-9.2C5 7.5 7 5.5 9.6 5.5c1.2 0 2 .5 2.4 1.4.4-.9 1.2-1.4 2.4-1.4 2.6 0 4.6 2 4.6 5.3C19 15.6 12 20 12 20Z" />
      <polyline points="7,12 10,12 11.2,9.5 13.3,14.5 14.5,12 17,12" />
    </>
  ),
  'week-completed': (
    <>
      <rect x="3" y="3" width="18" height="18" rx="4" />
      <path d="m7 12 3 3 7-7" />
    </>
  ),
  'week-in-progress': (
    <>
      <path d="M18.5 8A7.5 7.5 0 1 0 19 15.3" />
      <path d="M18.5 4.8V8h-3.2" />
      <line x1="10" y1="9" x2="10" y2="15" />
      <line x1="14" y1="9" x2="14" y2="15" />
    </>
  ),
  'week-nutrition-complete': (
    <>
      <path d="M4 12h16c-.6 4.8-3.2 7.5-8 7.5S4.6 16.8 4 12Z" />
      <line x1="6" y1="12" x2="18" y2="12" />
      <path d="M8.2 8.6l2 2 4-4.1" />
    </>
  ),
  'week-nutrition-fasted': (
    <>
      <path d="M4 10h16c-.6 5-3.3 8-8 8s-7.4-3-8-8Z" />
      <path d="M10 3v4M14 3v4" />
    </>
  ),
  'week-nutrition-incomplete': (
    <>
      <path d="M4 10h16c-.6 5-3.3 8-8 8s-7.4-3-8-8Z" />
      <path d="M9 5h6" />
    </>
  ),
  'week-nutrition-missing': (
    <>
      <path d="M4 12h6M14 12h6c-.6 4.8-3.2 7.5-8 7.5S4.6 16.8 4 12" />
      <circle cx="9" cy="8" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="12" cy="8" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="15" cy="8" r="0.8" fill="currentColor" stroke="none" />
    </>
  ),
  'week-planned': (
    <>
      <path d="M9.5 20H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v5" />
      <path d="M8 3v4M16 3v4M4 9h16" />
      <circle cx="17" cy="17" r="5" />
      <path d="M17 14.5V17l2 1.4" />
    </>
  ),
  'week-skipped': (
    <>
      <line x1="5" y1="6" x2="5" y2="18" />
      <path d="M8 7l6 5-6 5Z" />
      <line x1="17" y1="7" x2="17" y2="17" />
    </>
  ),
  'account-security': (
    <>
      <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6Z" />
      <rect x="9" y="10" width="6" height="6" rx="1" />
      <path d="M10 10V8a2 2 0 0 1 4 0v2" />
    </>
  ),
  'ai-coach': (
    <>
      <path d="M14 4H6a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h2v2l4-2h6a3 3 0 0 0 3-3v-5" />
      <path d="m18 2 1.3 3.7L23 7l-3.7 1.3L18 12l-1.3-3.7L13 7l3.7-1.3Z" />
      <path d="M7 12h4M7 16h9" />
    </>
  ),
} as const satisfies Record<string, ReactNode>;

export const iconGlyphs = {
  ...glyphs,
  'nav-plan': glyphs['exercise'],
  'week-strength': glyphs['exercise'],
  'nav-more': glyphs['more-horizontal'],
  'disclosure-closed': glyphs['chevron-right'],
  'disclosure-open': glyphs['chevron-down'],
  'week-rest': glyphs['theme-moon'],
  calendar: glyphs['nav-today'],
} as const;

export type IconName = keyof typeof iconGlyphs;
