import { describe, expect, it } from 'vitest';
import { strengthFrame } from '../../../../src/pages/landing/StrengthScene';

describe('approved scroll sequence', () => {
  it('finishes the lift before recording the third repetition', () => {
    expect(strengthFrame(0)).toEqual({ phase: 0, lift: 0, count: 2, result: 0 });
    expect(strengthFrame(0.47).count).toBe(2);
    expect(strengthFrame(0.55)).toEqual({ phase: 1, lift: 1, count: 3, result: 0 });
  });

  it('reveals the saved result only after the recording stage', () => {
    expect(strengthFrame(0.79).phase).toBe(1);
    expect(strengthFrame(0.85).result).toBeCloseTo(0.5);
    expect(strengthFrame(1)).toEqual({ phase: 2, lift: 1, count: 3, result: 1 });
  });

  it('reverses continuously without inventing additional repetitions', () => {
    const frames = [1, 0.8, 0.55, 0.48, 0.3, 0.06, 0].map(strengthFrame);
    expect(frames.map((frame) => frame.count)).toEqual([3, 3, 3, 3, 2, 2, 2]);
    expect(frames.every((frame, index) => frame.lift <= (frames[index - 1]?.lift ?? 1))).toBe(true);
  });
});
