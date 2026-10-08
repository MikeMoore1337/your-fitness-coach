import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const guardPath = path.resolve(process.cwd(), 'scripts/russian_user_facing_ui.mjs');

function runGuard(source: string) {
  return spawnSync(process.execPath, [guardPath, '--stdin'], {
    encoding: 'utf8',
    input: source,
  });
}

describe('RUSSIAN_USER_FACING_UI guard', () => {
  it.each([
    '<span>Следующий review</span>',
    '<label>Follow-up, если нужен</label>',
    '<p>Nutrition Planning</p>',
    '<Button>Schedule follow-up</Button>',
    '<input aria-label="Review date" />',
    'const message = `Schedule follow-up for ${clientName}`;',
  ])('rejects new English user-facing copy: %s', (source) => {
    const result = runGuard(source);
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('Russian user-facing UI guard failed');
  });

  it.each([
    '<span>Следующая проверка</span>',
    'const reviewMutation = createMutation();',
    "const path = 'rollout_preview';",
    '<span>Your Fitness Coach</span>',
    '<span>Как работает Coach OS</span>',
    '<input aria-label="Дата проверки" />',
  ])('allows Russian copy, identifiers, and documented exceptions: %s', (source) => {
    const result = runGuard(source);
    expect(result.status).toBe(0);
    expect(result.stdout).toContain('Russian user-facing UI guard passed');
  });
});
