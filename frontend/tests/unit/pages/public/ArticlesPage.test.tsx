import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ArticlesPage from '../../../../src/pages/public/ArticlesPage';
import { api } from '../../../../src/shared/api/client';
import type { WebArticle, WebArticleCard } from '../../../../src/shared/api/types';
import { NavigationProvider } from '../../../../src/shared/navigation/router';

vi.mock('../../../../src/shared/api/client', () => ({
  api: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;

    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

const mockedApi = vi.mocked(api);

const articleCard: WebArticleCard = {
  slug: 'strength-basics',
  title: 'Основы силовых тренировок',
  description: 'План, записи и ограничения для понятного старта.',
  lead: 'Начните с посильного плана и записывайте факты.',
  topics: ['training', 'strength_hypertrophy'],
  article_kind: 'evergreen_explainer',
  published_at: '2026-09-01T10:00:00Z',
  updated_at: '2026-09-02T10:00:00Z',
  canonical_url: 'https://your-fitness-coach.ru/articles/strength-basics',
};

const relatedCard: WebArticleCard = {
  ...articleCard,
  slug: 'recovery-basics',
  title: 'Восстановление после тренировки',
  canonical_url: 'https://your-fitness-coach.ru/articles/recovery-basics',
};

const sourceUrl = 'https://www.who.int/news-room/fact-sheets/detail/physical-activity';

const article: WebArticle = {
  ...articleCard,
  body_sections: [
    {
      heading: 'С чего начать',
      paragraphs: ['Выберите посильные движения и заранее определите дни занятий.'],
      points: ['Записывайте фактические подходы'],
    },
    {
      heading: 'Как читать записи',
      paragraphs: ['Сверяйте план и факт по нескольким занятиям.'],
      points: [],
    },
  ],
  search_intent: 'informational',
  primary_query: 'как начать силовые тренировки',
  secondary_queries: ['план силовых тренировок'],
  risk_level: 'low',
  evidence_level: 'moderate',
  claims: [
    {
      claim_id: 'plan-context',
      claim_text: 'Повторяемый план помогает сравнивать записи.',
      normalized_claim: 'repeatable plan supports comparison',
    },
  ],
  sources: [
    {
      source_id: 'source-guideline',
      title: 'Physical activity guidance',
      publisher: 'World Health Organization',
      url: 'https://www.who.int/news-room/fact-sheets/detail/physical-activity',
      source_type: 'official_organization',
      published_at: null,
      limitations: 'Общие рекомендации.',
    },
  ],
  claim_source_matrix: [
    {
      claim_id: 'plan-context',
      source_ids: ['source-guideline'],
      support_level: 'supports',
      limitations: 'Источник не задаёт индивидуальную программу.',
      review_status: 'verified',
    },
  ],
  author: { name: 'Your Fitness Coach', type: 'Organization' },
  editor: { name: 'YFC Editorial Desk', type: 'Organization' },
  domain_reviewer: null,
  related_slugs: ['recovery-basics'],
  cta: {
    destination: 'web',
    label: 'Открыть Your Fitness Coach',
    description: 'Сохраняйте план и фактические результаты.',
  },
  content_version: 1,
  generated_with_ai: true,
  research_assistance: true,
};

function renderPath(path: string) {
  window.history.replaceState({}, '', path);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <ArticlesPage />
      </NavigationProvider>
    </QueryClientProvider>,
  );
}

describe('ArticlesPage', () => {
  beforeEach(() => {
    mockedApi.mockImplementation((path: string) => {
      if (path === '/api/v1/public/articles') return Promise.resolve([articleCard, relatedCard]);
      if (path === '/api/v1/public/articles/strength-basics') return Promise.resolve(article);
      return Promise.reject(new Error(`Unexpected API path: ${path}`));
    });
  });

  afterEach(() => {
    cleanup();
    document.head
      .querySelectorAll(
        'meta[name="description"], meta[name="robots"], meta[name="yandex"], meta[name^="twitter:"], meta[property^="og:"], link[rel="canonical"], script[type="application/ld+json"]',
      )
      .forEach((element) => element.remove());
    window.history.replaceState({}, '', '/');
    vi.restoreAllMocks();
  });

  it('renders a crawlable article index with ordinary internal links', async () => {
    renderPath('/articles');

    expect(
      await screen.findByRole('heading', { name: 'Статьи, которые помогают разобраться.' }),
    ).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: /Основы силовых тренировок/ })).toHaveAttribute(
      'href',
      '/articles/strength-basics',
    );
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute(
      'content',
      'index, follow',
    );
  });

  it('renders article evidence, related links, CTA and route metadata', async () => {
    renderPath('/articles/strength-basics');

    expect(
      await screen.findByRole('heading', { level: 1, name: article.title }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Выберите посильные движения и заранее определите дни занятий.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Источники' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Physical activity guidance' })).toHaveAttribute(
      'href',
      sourceUrl,
    );
    expect(screen.getByRole('link', { name: /Восстановление после тренировки/ })).toHaveAttribute(
      'href',
      '/articles/recovery-basics',
    );
    expect(screen.getByRole('link', { name: 'Открыть Your Fitness Coach' })).toHaveAttribute(
      'href',
      '/app',
    );
    expect(document.querySelector('link[rel="canonical"]')).toHaveAttribute(
      'href',
      article.canonical_url,
    );
    expect(document.querySelector('meta[property="og:type"]')).toHaveAttribute(
      'content',
      'article',
    );
    const structuredData = document.querySelector<HTMLScriptElement>(
      'script[type="application/ld+json"][data-public-seo]',
    );
    expect(structuredData).not.toBeNull();
    expect(JSON.parse(structuredData?.textContent ?? '{}')).toMatchObject({
      '@type': 'Article',
      headline: article.title,
      datePublished: article.published_at.slice(0, 10),
      dateModified: article.updated_at.slice(0, 10),
    });
  });
});
