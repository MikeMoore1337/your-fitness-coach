const fs = require('node:fs');
const path = require('node:path');

class PlaywrightCITiming {
  onBegin(config, suite) {
    this.plan = JSON.parse(fs.readFileSync(path.join(process.env.YFC_E2E_PLAN_DIR, 'plan.json'), 'utf8'));
    this.collected = suite.allTests().map((test) => test.id).sort();
    this.executed = new Set();
    this.duplicate = false;
  }

  onTestEnd(test, result) {
    console.log(`CI_PLAYWRIGHT_TIMING id=${test.id} duration_ms=${result.duration} retry=${result.retry}`);
    if (result.retry === 0 && this.executed.has(test.id)) this.duplicate = true;
    this.executed.add(test.id);
  }

  onEnd() {
    const selected = this.plan.selected;
    if (this.duplicate || JSON.stringify(this.collected) !== JSON.stringify(selected) ||
        JSON.stringify([...this.executed].sort()) !== JSON.stringify(selected)) {
      console.error('Playwright execution does not match its shard plan');
      return { status: 'failed' };
    }
    fs.writeFileSync(path.join(process.env.YFC_E2E_PLAN_DIR, 'receipt.json'), JSON.stringify(this.plan));
  }
}

module.exports = PlaywrightCITiming;
