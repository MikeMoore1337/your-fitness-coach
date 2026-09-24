import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ExerciseMediaAsset } from '../../../../src/features/exercises/ExerciseMediaAsset';

describe('ExerciseMediaAsset', () => {
  it('keeps a concise centered missing-media label with the full accessible meaning', () => {
    render(
      <ExerciseMediaAsset
        alt="Бёрд-дог: изображение упражнения"
        className="exercise-catalog-item__thumb"
        thumbnailUrl={null}
        variant="thumbnail"
      />,
    );

    const placeholder = screen.getByRole('img', {
      name: 'Бёрд-дог: изображение упражнения. Изображение пока недоступно',
    });
    expect(placeholder).toBeVisible();
    expect(screen.getByText('Нет фото')).toHaveAttribute('aria-hidden', 'true');
    expect(placeholder).toHaveClass(
      'exercise-catalog-item__thumb',
      'exercise-media-asset--missing',
    );
  });
});
