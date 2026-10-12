import { describe, expect, it } from 'vitest';
import {
  assertCanonicalProgressReportInvariants,
  makeCanonicalProgressReportFixture,
} from '../fixtures/progress-report';

describe('canonical progress report fixture', () => {
  it('keeps API, UI and PDF facts internally coherent', () => {
    const report = makeCanonicalProgressReportFixture();

    expect(() => assertCanonicalProgressReportInvariants(report)).not.toThrow();
    expect(report.data_sufficiency.working_sets.status).toBe('limited');
    expect(report.data_sufficiency.nutrition_coverage.status).toBe('limited');
    expect(report.data_sufficiency.weight_trend.status).toBe('limited');
    expect(report.adherence.overall_percent).toBe(50);
    expect(report.nutrition.daily).toHaveLength(30);
  });

  it('fails when a derived field is changed without its source facts', () => {
    const report = makeCanonicalProgressReportFixture();
    report.nutrition.summary.coverage_percent = 80;

    expect(() => assertCanonicalProgressReportInvariants(report)).toThrow(
      'nutrition coverage drift',
    );
  });
});
