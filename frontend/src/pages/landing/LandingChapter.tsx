import type { ComponentPropsWithoutRef } from 'react';
import { useSemanticMotion } from '../../shared/ui/useSemanticMotion';

export function LandingChapter({
  id,
  className = '',
  ...props
}: ComponentPropsWithoutRef<'section'>) {
  const motion = useSemanticMotion<HTMLElement>(id ?? className, { elementId: id, observe: true });
  return (
    <section
      {...props}
      id={motion.elementId}
      className={`landing-chapter ${className}`}
      data-motion-phase={motion.motionPhase}
    />
  );
}
