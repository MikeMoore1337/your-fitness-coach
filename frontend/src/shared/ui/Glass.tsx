import type { ComponentPropsWithRef } from 'react';

export type GlassVariant = 'clear' | 'regular' | 'tinted';

/** Opt in existing semantic elements without adding wrappers or changing geometry. */
export function glassProps(variant: GlassVariant = 'regular', interactive = false) {
  return {
    'data-glass': '',
    'data-glass-variant': variant,
    'data-glass-interactive': interactive ? '' : undefined,
  } as const;
}

/** Structural floating surface. Buttons, links and navigation use glassProps directly. */
export function Glass({
  variant = 'regular',
  interactive = false,
  ...props
}: ComponentPropsWithRef<'div'> & { variant?: GlassVariant; interactive?: boolean }) {
  return <div {...glassProps(variant, interactive)} {...props} />;
}
