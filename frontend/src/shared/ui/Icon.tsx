import type { SVGProps } from 'react';
import { iconGlyphs, type IconName } from './iconGlyphs';
export type { IconName } from './iconGlyphs';

export interface IconProps extends Omit<
  SVGProps<SVGSVGElement>,
  'children' | 'dangerouslySetInnerHTML'
> {
  label?: string;
  name: IconName;
  size?: 16 | 20 | 24 | 56 | 80 | 110;
}

/** Единый векторный renderer для landing, приложения и TMA. */
export function Icon({ className = '', label, name, size = 24, ...props }: IconProps) {
  return (
    <svg
      {...props}
      className={`yfc-icon yfc-icon--${size} ${className}`.trim()}
      data-icon={name}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill={name === 'star-filled' ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {iconGlyphs[name]}
    </svg>
  );
}
