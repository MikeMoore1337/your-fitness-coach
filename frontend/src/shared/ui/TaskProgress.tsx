import { useSemanticMotion } from './useSemanticMotion';
import '../../styles/data-viz.css';

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

export function TaskProgress({
  completed,
  label,
  total,
}: {
  completed: number;
  label: string;
  total: number;
}) {
  const safeTotal = Math.max(total, 1);
  const motion = useSemanticMotion<HTMLDivElement>(`${label}|${safeTotal}|${completed}`, {
    animateInitial: false,
  });
  return (
    <div
      className="data-viz-progress"
      id={motion.elementId}
      data-motion-phase={motion.motionPhase}
      data-motion-revision={motion.motionRevision}
      data-progress-kind="task"
      onAnimationEnd={motion.onMotionAnimationEnd}
    >
      <div className="data-viz-progress__label">
        <span>{label}</span>
        <strong>
          {completed} из {total}
        </strong>
      </div>
      <div
        aria-label={`${label}: ${completed} из ${total}`}
        aria-valuemax={safeTotal}
        aria-valuemin={0}
        aria-valuenow={clamp(completed, 0, safeTotal)}
        className="data-viz-progress__track"
        role="progressbar"
      >
        <span style={{ width: `${clamp((completed / safeTotal) * 100, 0, 100)}%` }} />
      </div>
    </div>
  );
}
