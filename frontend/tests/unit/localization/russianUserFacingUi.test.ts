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
    '<span>Client overview</span>',
    '<Button>Schedule follow-up</Button>',
    '<input aria-label="Review date" />',
    'const message = `Schedule follow-up for ${clientName}`;',
    "<span>{status === 'pending' ? 'Review' : 'Готово'}</span>",
    "<span>{status === 'pending' && 'Review'}</span>",
    "<input aria-label={status === 'pending' ? 'Review' : 'Готово'} />",
    "<span>{'pending' === status ? 'Готово' : 'Review'}</span>",
    '<span>RPE review</span>',
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
    '<span>Client 360 / обзор клиента</span>',
    '<input aria-label="Дата проверки" />',
    "<span>{status === 'pending' ? 'Ожидает' : 'Готово'}</span>",
    "<span>{status !== 'confirmed' && <b>Черновик</b>}</span>",
    "<span>{'pending' === status ? 'Ожидает' : 'Готово'}</span>",
    '<p>RPE: 8</p>',
  ])('allows Russian copy, identifiers, and documented exceptions: %s', (source) => {
    const result = runGuard(source);
    expect(result.status).toBe(0);
    expect(result.stdout).toContain('Russian user-facing UI guard passed');
  });
});
