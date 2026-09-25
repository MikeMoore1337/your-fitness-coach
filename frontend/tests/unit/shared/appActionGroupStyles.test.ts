import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('shared action-group spacing', () => {
  it('uses the shared spacing token on trainer, builder, workout, and nutrition actions', () => {
    const styles = readFileSync('src/styles/design-v2.css', 'utf8').replace(/\r\n/g, '\n');
    expect(styles).toMatch(/\.app-action-group\s*\{\s*gap:\s*var\(--v2-space-2\);\s*\}/);

    for (const source of [
      'src/features/coach/CoachOperationsPanel.tsx',
      'src/features/programs/ProgramBuilder.tsx',
      'src/features/workouts/TodayWorkout.tsx',
      'src/features/nutrition/FoodEditor.tsx',
    ]) {
      expect(readFileSync(source, 'utf8')).toContain('app-action-group');
    }
  });
});
