import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ExerciseGuideMedia } from '../../../../src/features/exercises/ExerciseGuideMedia';
import type { ExerciseGuide } from '../../../../src/shared/api/types';

const media = [
  {
    type: 'image',
    url: '/static/exercise-guides/human-v1/example/concentric_end-480w.webp',
    poster: '/static/exercise-guides/human-v1/example/concentric_end-480w.webp',
    phase_id: 'concentric_end',
    phase: 'Фаза усилия',
    alt: 'Пример: конечное положение усилия',
    asset_id: 'example:canonical:concentric_end:120e-v1',
    asset_version: '120e-v1',
    variant_key: 'canonical',
    source_name: 'Your Fitness Coach',
    source_url: '/',
    source_license: 'Иллюстрация создана для приложения',
    source_license_url: null,
    width: 480,
    height: 320,
    byte_size: 12_000,
    sort_order: 0,
    sources: [
      {
        url: '/static/exercise-guides/human-v1/example/concentric_end-480w.webp',
        mime_type: 'image/webp',
        width: 480,
        height: 320,
        byte_size: 12_000,
      },
      {
        url: '/static/exercise-guides/human-v1/example/concentric_end-1280w.webp',
        mime_type: 'image/webp',
        width: 1280,
        height: 853,
        byte_size: 42_000,
      },
    ],
  },
  {
    type: 'image',
    url: '/static/exercise-guides/human-v1/example/eccentric_end-480w.webp',
    poster: '/static/exercise-guides/human-v1/example/eccentric_end-480w.webp',
    phase_id: 'eccentric_end',
    phase: 'Фаза возврата',
    alt: 'Пример: конечное положение возврата',
    asset_id: 'example:canonical:eccentric_end:120e-v1',
    asset_version: '120e-v1',
    variant_key: 'canonical',
    source_name: 'Your Fitness Coach',
    source_url: '/',
    source_license: 'Иллюстрация создана для приложения',
    source_license_url: null,
    width: 480,
    height: 320,
    byte_size: 11_000,
    sort_order: 1,
    sources: [
      {
        url: '/static/exercise-guides/human-v1/example/eccentric_end-480w.webp',
        mime_type: 'image/webp',
        width: 480,
        height: 320,
        byte_size: 11_000,
      },
    ],
  },
] satisfies ExerciseGuide['media'];

describe('ExerciseGuideMedia', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('uses the approved animation by default and the local poster for reduced motion', () => {
    const animated: ExerciseGuide['media'] = [
      {
        type: 'animation',
        url: '/static/exercise-guides/gymvisual/bench-press.gif',
        poster: '/static/exercise-guides/gymvisual/bench-press.jpg',
        phase_id: 'movement',
        phase: 'Движение',
        alt: 'Пример: движение',
        source_name: 'Gym visual',
        source_url: 'https://github.com/hasaneyldrm/exercises-dataset',
        source_license: 'Owner-purchased GymVisual license',
        source_license_url: 'https://gymvisual.com/',
        width: 180,
        height: 180,
        byte_size: 120_000,
        sort_order: 0,
        sources: [
          {
            url: '/static/exercise-guides/gymvisual/bench-press.gif',
            mime_type: 'image/gif',
            width: 180,
            height: 180,
            byte_size: 120_000,
          },
        ],
      },
    ];
    vi.stubGlobal('matchMedia', () => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));

    render(<ExerciseGuideMedia items={animated} />);

    const image = screen.getByAltText('Пример: движение');
    expect(image).toHaveAttribute('src', '/static/exercise-guides/gymvisual/bench-press.jpg');
    expect(image).toHaveAttribute('data-media-mode', 'static-poster');
  });

  it('keeps the GIF as the default animation source instead of selecting the poster', () => {
    const animated: ExerciseGuide['media'] = [
      {
        type: 'animation',
        url: '/static/exercise-guides/gymvisual/bench-press.gif',
        poster: '/static/exercise-guides/gymvisual/bench-press.jpg',
        phase_id: 'movement',
        phase: 'Движение',
        alt: 'Пример: движение',
        source_name: 'Gym visual',
        source_url: 'https://github.com/hasaneyldrm/exercises-dataset',
        source_license: 'Owner-purchased GymVisual license',
        source_license_url: 'https://gymvisual.com/',
        width: 180,
        height: 180,
        byte_size: 120_000,
        sort_order: 0,
        sources: [
          {
            url: '/static/exercise-guides/gymvisual/bench-press.gif',
            mime_type: 'image/gif',
            width: 180,
            height: 180,
            byte_size: 120_000,
          },
          {
            url: '/static/exercise-guides/gymvisual/bench-press.jpg',
            mime_type: 'image/jpeg',
            width: 180,
            height: 180,
            byte_size: 12_000,
          },
        ],
      },
    ];

    vi.stubGlobal('matchMedia', () => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    render(<ExerciseGuideMedia items={animated} />);

    const image = screen.getByAltText('Пример: движение');
    expect(image).toHaveAttribute('src', '/static/exercise-guides/gymvisual/bench-press.gif');
    expect(image).not.toHaveAttribute('srcset');
    expect(image).toHaveAttribute('data-media-mode', 'animation');
  });

  it('uses explicit phase ids and responsive sources without eagerly opening the lightbox', () => {
    render(<ExerciseGuideMedia items={media} />);

    expect(screen.getByText(/Изображение показывает положение/)).toBeVisible();
    const image = screen.getByAltText('Пример: конечное положение усилия');
    expect(image).toHaveAttribute('loading', 'lazy');
    expect(image).toHaveAttribute('decoding', 'async');
    expect(image).toHaveAttribute(
      'srcset',
      expect.stringContaining('concentric_end-1280w.webp 1280w'),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('selects the large source only after opening and preserves keyboard-accessible navigation', () => {
    render(<ExerciseGuideMedia items={media} />);
    fireEvent.click(screen.getByRole('button', { name: 'Увеличить: Фаза усилия' }));

    const dialog = screen.getByRole('dialog', { name: 'Увеличенное изображение: Фаза усилия' });
    expect(dialog).toBeVisible();
    expect(dialog.querySelector('img[alt="Пример: конечное положение усилия"]')).toHaveAttribute(
      'src',
      '/static/exercise-guides/human-v1/example/concentric_end-1280w.webp',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Следующее изображение' }));
    expect(
      screen.getByRole('dialog', { name: 'Увеличенное изображение: Фаза возврата' }),
    ).toBeVisible();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps an accessible text fallback when an image fails', () => {
    render(<ExerciseGuideMedia items={media} />);
    fireEvent.error(screen.getByAltText('Пример: конечное положение усилия'));

    expect(
      screen.getByRole('img', { name: 'Пример: конечное положение усилия' }),
    ).toHaveTextContent('Изображение недоступно');
  });
});
