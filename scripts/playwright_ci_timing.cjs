class PlaywrightCITiming {
  onTestEnd(test, result) {
    console.log(`CI_PLAYWRIGHT_TIMING id=${test.id} duration_ms=${result.duration} retry=${result.retry}`);
  }
}

module.exports = PlaywrightCITiming;
