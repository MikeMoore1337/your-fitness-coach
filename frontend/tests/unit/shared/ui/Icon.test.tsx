import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Icon, type IconName } from '../../../../src/shared/ui/Icon';
import { iconGlyphs } from '../../../../src/shared/ui/iconGlyphs';
import { readFileSync } from 'node:fs';

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
    const points = container.querySelector('polyline')?.getAttribute('points');
    const css = readFileSync('src/styles/react.css', 'utf8');
    expect(css).toContain(`points='${points}'`);
    expect(css).toContain("stroke-width='1.8'");
  });
  it('fills only the explicit selected star state', () => {
    const { container, rerender } = render(<Icon name="star" />);
    expect(container.querySelector('svg')).toHaveAttribute('fill', 'none');
    rerender(<Icon name="star-filled" />);
    expect(container.querySelector('svg')).toHaveAttribute('fill', 'currentColor');
  });
});
