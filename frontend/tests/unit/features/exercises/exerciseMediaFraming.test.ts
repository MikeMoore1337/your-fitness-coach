import { describe, expect, it } from 'vitest';
import { resolveExerciseMediaFrame } from '../../../../src/features/exercises/exerciseMediaFraming';

describe('resolveExerciseMediaFrame', () => {
  it('keeps square GIF media native', () => {
    expect(
      resolveExerciseMediaFrame({
        url: '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.gif',
        width: 180,
        height: 180,
      }),
    ).toMatchObject({ policy: 'native-square', objectPosition: '50% 50%', sourceRatio: 1 });
  });

  it('does not apply poster dimensions to the original square GIF', () => {
    expect(
      resolveExerciseMediaFrame({
        url: '/static/exercise-guides/gymvisual/incline-bench-press-0047-3TZduzM.gif',
        width: 1280,
        height: 720,
      }),
    ).toMatchObject({ policy: 'native-square', sourceRatio: 1 });
  });

  it('fills wide media and applies its reviewed focal point', () => {
    expect(
      resolveExerciseMediaFrame({
        url: '/static/exercise-guides/exercises-media/incline-bench-press/poster-1280.jpg',
        width: 1280,
        height: 720,
      }),
    ).toMatchObject({ policy: 'filled-square', objectPosition: '46% 50%', sourceRatio: 1.7778 });
  });

  it('keeps a documented full-body exception out of unsafe cover crop', () => {
    expect(
      resolveExerciseMediaFrame({
        url: '/static/exercise-guides/exercises-media/plank/poster-1280.jpg',
        width: 1280,
        height: 720,
      }),
    ).toMatchObject({ policy: 'contain-exception', sourceRatio: 1.7778 });
  });
});
