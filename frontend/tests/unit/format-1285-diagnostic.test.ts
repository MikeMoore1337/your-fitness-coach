import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { it } from 'vitest';

it('temporary print of exact Prettier output for issue 1285', () => {
  const file = 'tests/unit/features/programs/TemplatesList.test.tsx';
  const before = readFileSync(file, 'utf8');
  const after = execFileSync('npx', ['prettier', file, '--end-of-line', 'auto'], {
    encoding: 'utf8',
  });
  const anchor = "  it('shows ready-template actions";
  const stop = "  it('keeps template deletion on the template endpoint";
  const start = before.indexOf(anchor);
  const end = before.indexOf(stop, start);
  const nextStart = after.indexOf(anchor);
  const nextEnd = after.indexOf(stop, nextStart);
  console.log('PRETTIER_SOURCE_BEGIN\\n' + before.slice(start, end) + '\\nPRETTIER_SOURCE_END');
  console.log('PRETTIER_OUTPUT_BEGIN\\n' + after.slice(nextStart, nextEnd) + '\\nPRETTIER_OUTPUT_END');
});
