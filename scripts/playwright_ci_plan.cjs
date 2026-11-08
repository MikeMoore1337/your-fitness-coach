const fs = require('node:fs');
const path = require('node:path');
const costs = require('./playwright_ci_costs.json').duration_ms;

function plan(config, suite, index, count) {
  const tests = suite.allTests();
  if (!tests.length || !Number.isInteger(index) || !Number.isInteger(count) || index < 1 || index > count) throw Error('Invalid Playwright shard');
  const ids = tests.map((test) => test.id);
  if (new Set(ids).size !== ids.length) throw Error('Duplicate Playwright test IDs');
  const files = new Map();
  for (const test of tests) {
    const title = test.titlePath();
    const project = title[1];
    const file = path.relative(config.rootDir, test.location.file).replaceAll('\\', '/');
    if (!project || !file || /[›\r\n]/.test(project + file)) throw Error('Unsafe Playwright project or file name');
    const key = JSON.stringify([project, file]);
    if (!files.has(key)) files.set(key, []);
    files.get(key).push({ test, project, file, title: title.slice(3) });
  }
  const units = [];
  for (const entries of files.values()) {
    const unsafe = entries.some((entry) => {
      if (!entry.title.length || entry.title.some((part) => /[›\r\n]/.test(part) || part.trim() !== part)) return true;
      let parallel = false;
      for (let parent = entry.test.parent; parent; parent = parent.parent) {
        if (!['none', 'parallel'].includes(parent._parallelMode)) return true;
        parallel ||= parent._parallelMode === 'parallel';
      }
      if (!parallel) return true;
      return entries.some((other) => other !== entry && entry.title.length <= other.title.length && entry.title.every((part, i) => other.title[i] === part));
    });
    for (const group of unsafe ? [entries] : entries.map((entry) => [entry])) {
      const first = group[0];
      const selector = [`[${first.project}]`, first.file, ...(unsafe ? [] : first.title)].join(' › ');
      const weight = group.reduce((sum, entry) => {
        const duration = costs[entry.test.id] ?? 5000;
        if (!Number.isFinite(duration) || duration < 0) throw Error('Invalid Playwright timing');
        return sum + Math.max(1000, duration);
      }, 0);
      units.push({ selector, weight, ids: group.map((entry) => entry.test.id).sort() });
    }
  }
  units.sort((a, b) => b.weight - a.weight || (a.ids[0] < b.ids[0] ? -1 : a.ids[0] > b.ids[0] ? 1 : 0));
  const buckets = Array.from({ length: count }, () => ({ weight: 0, units: [] }));
  for (const unit of units) {
    const bucket = buckets.reduce((best, candidate) => candidate.weight < best.weight ? candidate : best);
    bucket.units.push(unit);
    bucket.weight += unit.weight;
  }
  const chosen = buckets[index - 1].units;
  if (!chosen.length) throw Error('Empty Playwright shard');
  return { all: ids.sort(), selected: chosen.flatMap((unit) => unit.ids).sort(), selectors: chosen.map((unit) => unit.selector) };
}

class Reporter {
  onBegin(config, suite) {
    const [index, count] = (process.env.YFC_E2E_SHARD || '').split('/').map(Number);
    const result = plan(config, suite, index, count);
    const directory = process.env.YFC_E2E_PLAN_DIR;
    fs.mkdirSync(directory, { recursive: true });
    fs.writeFileSync(path.join(directory, 'tests.txt'), `${result.selectors.join('\n')}\n`);
    fs.writeFileSync(path.join(directory, 'plan.json'), JSON.stringify({ shard: `${index}/${count}`, all: result.all, selected: result.selected }));
  }
}

module.exports = Reporter;
module.exports.plan = plan;
