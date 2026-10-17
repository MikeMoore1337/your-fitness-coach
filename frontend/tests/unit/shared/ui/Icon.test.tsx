import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Icon, type IconName } from '../../../../src/shared/ui/Icon';
import { iconGlyphs } from '../../../../src/shared/ui/iconGlyphs';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

describe('Icon', () => {
  it('renders every semantic glyph without images or opaque glass patches', () => {
    const names = Object.keys(iconGlyphs) as IconName[];
    expect(names.length).toBeGreaterThan(70);
    for (const name of names) {
      const { container, unmount } = render(<Icon name={name} />);
      const icon = container.querySelector('svg');
      expect(icon).toHaveAttribute('viewBox', '0 0 24 24');
      expect(icon).toHaveAttribute('stroke', 'currentColor');
      expect(icon).toHaveAttribute('stroke-width', '1.8');
      expect(icon?.children.length).toBeGreaterThan(0);
      expect(icon?.querySelector('img, image, foreignObject, script')).toBeNull();
      for (const element of icon?.querySelectorAll('[fill]') ?? []) {
        expect(['none', 'currentColor']).toContain(element.getAttribute('fill'));
      }
      unmount();
    }
  });
  it('keeps decorative glyphs out of accessible names and keyboard focus', () => {
    render(
      <button aria-label="Удалить запись">
        <Icon name="trash" size={20} />
      </button>,
    );
    const button = screen.getByRole('button', { name: 'Удалить запись' });
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    const icon = button.querySelector('svg');
    expect(icon).toHaveAttribute('focusable', 'false');
    expect(icon).toHaveAttribute('aria-hidden', 'true');
    expect(icon).toHaveAttribute('width', '20');
    expect(icon).toHaveAttribute('height', '20');
  });
  it('exposes a standalone meaningful icon name', () => {
    render(<Icon label="Нет доступа" name="permission-denied" />);
    expect(screen.getByRole('img', { name: 'Нет доступа' })).not.toHaveAttribute('aria-hidden');
  });
  it('shares entity geometry across landing, navigation, disclosures and week', () => {
    expect(iconGlyphs['nav-plan']).toBe(iconGlyphs.exercise);
    expect(iconGlyphs['week-strength']).toBe(iconGlyphs.exercise);
    expect(iconGlyphs['disclosure-closed']).toBe(iconGlyphs['chevron-right']);
    expect(iconGlyphs['nav-more']).toBe(iconGlyphs['more-horizontal']);
    expect(iconGlyphs.calendar).toBe(iconGlyphs['nav-today']);
  });
  it('keeps native select geometry synchronized with the shared chevron', () => {
    const { container } = render(<Icon name="chevron-down" />);
    const geometry = container.querySelector('path')?.getAttribute('d');
    expect(geometry).toBeTruthy();
    const css = readFileSync('src/styles/design-system.css', 'utf8');
    expect(css).toContain(`d='${geometry}'`);
    expect(css).toContain("stroke-width='1.8'");
  });
  it('keeps the native search clear resource synchronized with the shared close glyph', () => {
    const { container } = render(<Icon name="close" />);
    const css = readFileSync('src/styles/design-system.css', 'utf8');
    for (const path of container.querySelectorAll('path')) {
      expect(css).toContain(`d='${path.getAttribute('d')}'`);
    }
    expect(css).toContain("input[type='search']::-webkit-search-cancel-button");
  });
  it('requires canonical glyph renderer for functional SVG across the frontend', () => {
    const allowed = new Set([
      'src/shared/ui/Icon.tsx',
      'src/shared/ui/iconGlyphs.tsx',
      'src/shared/ui/DataViz.tsx',
      'src/features/auth/OAuthButtons.tsx',
    ]);
    const visit = (directory: string): string[] =>
      readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
        const filename = join(directory, entry.name);
        if (entry.isDirectory()) return visit(filename);
        return entry.name.endsWith('.tsx') ? [filename] : [];
      });

    for (const filename of visit('src')) {
      const normalized = filename.replaceAll('\\', '/');
      if (allowed.has(normalized)) continue;
      const source = readFileSync(filename, 'utf8');
      expect(source, `Non-canonical functional SVG in ${normalized}`).not.toMatch(
        /<(?:svg|path|circle|rect|line|polyline|polygon)\b/,
      );
    }
  });
  it('uses the shared Lucide chevron in the workout summary', () => {
    const source = readFileSync('src/features/workouts/ActiveSessionSummary.tsx', 'utf8');
    expect(source).toContain("name={open ? 'chevron-up' : 'chevron-down'}");
    expect(iconGlyphs['chevron-down']).toBeTruthy();
    expect(iconGlyphs['chevron-up']).toBeTruthy();
  });
  it('fills only the explicit selected star state', () => {
    const { container, rerender } = render(<Icon name="star" />);
    expect(container.querySelector('svg')).toHaveAttribute('fill', 'none');
    rerender(<Icon name="star-filled" />);
    expect(container.querySelector('svg')).toHaveAttribute('fill', 'currentColor');
  });
});
