import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { WebArticle, WebArticleCard } from '../../shared/api/types';
import { api, ApiError } from '../../shared/api/client';
import { appUrlForHostname } from '../../shared/navigation/appUrl';
import { AppLink, Redirect, useNavigation } from '../../shared/navigation/router';
import { applyArticleRouteMetadata, type PublicArticleSeoData } from '../../shared/seo/metadata';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { PUBLIC_TELEGRAM_LINKS } from '../../shared/telegram/publicLinks';
import { useWebTheme } from '../../shared/useWebTheme';
import { Icon } from '../../shared/ui/Icon';
import { PublicFooter, PublicHeader } from './PublicContentPage';
import NotFoundPage from '../NotFoundPage';
import '../../shared/ui/public-shell.css';
import '../landing/landing.css';
import './public-content.css';

const ARTICLE_KIND_LABELS: Record<WebArticleCard['article_kind'], string> = {
  evergreen_explainer: 'Объяснение',
  practical_guide: 'Практический разбор',
  evidence_review: 'Разбор evidence',
  myth_busting: 'Разбор мифов',
  research_update: 'Исследование',
  comparison: 'Сравнение',
  product_education: 'Возможности продукта',
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(value));
}

function ArticleCard({ article }: { article: WebArticleCard }) {
  return (
    <article className="public-guide-card article-card">
      <p>{ARTICLE_KIND_LABELS[article.article_kind]}</p>
      <h2>
        <AppLink to={`/articles/${article.slug}`}>{article.title}</AppLink>
      </h2>
      <p>{article.description}</p>
      <time dateTime={article.updated_at}>Обновлено {formatDate(article.updated_at)}</time>
      <AppLink className="public-inline-link" to={`/articles/${article.slug}`}>
        Читать статью <Icon name="arrow-right" size={16} />
      </AppLink>
    </article>
  );
}

function ArticleLayout({ children }: { children: React.ReactNode }) {
  const { colorScheme: theme } = useWebTheme();
  return (
    <div
      className={`public-shell public-shell--design-v2 public-shell--${theme} landing-page landing-page--${theme} public-page public-page--design-v2`}
    >
      <PublicHeader theme={theme} />
      {children}
      <PublicFooter theme={theme} />
    </div>
  );
}

function ArticlesIndex() {
  const articles = useQuery({
    queryKey: ['public', 'articles'],
    queryFn: () => api<WebArticleCard[]>('/api/v1/public/articles'),
  });

  useEffect(() => {
    applyArticleRouteMetadata('/articles');
  }, []);

  return (
    <ArticleLayout>
      <main id="public-content" className="public-main articles-index" tabIndex={-1}>
        <nav className="public-breadcrumbs" aria-label="Хлебные крошки">
          <ol>
            <li>
              <AppLink to="/">Главная</AppLink>
            </li>
            <li>
              <span aria-current="page">Статьи</span>
            </li>
          </ol>
        </nav>
        <header className="public-hero articles-index__hero">
          <div className="public-hero__copy">
            <p className="landing-kicker">Редакционные материалы</p>
            <h1>Статьи, которые помогают разобраться.</h1>
            <p className="public-hero__lead">
              Самостоятельные разборы о тренировках, питании и прогрессе. Сначала — понятный ответ
              на вопрос, затем источники, ограничения и следующий шаг.
            </p>
          </div>
          <aside className="public-hero__summary" aria-label="Подход к статьям">
            <span>Подход редакции</span>
            <strong>Меньше страниц. Больше полезного контекста.</strong>
            <p>
              Публикуем только материалы с понятным intent, источниками и человеческой проверкой.
            </p>
          </aside>
        </header>
        <section
          className="public-directory articles-index__directory"
          aria-labelledby="articles-title"
        >
          <div className="public-section-heading">
            <p className="landing-kicker">Опубликовано</p>
            <h2 id="articles-title">Выберите тему</h2>
          </div>
          {articles.isLoading && <p role="status">Загружаем статьи…</p>}
          {articles.error && (
            <div role="alert" className="public-inline-error">
              <p>Статьи временно недоступны. Попробуйте ещё раз.</p>
              <button
                type="button"
                className="landing-button"
                onClick={() => void articles.refetch()}
              >
                Повторить
              </button>
            </div>
          )}
          {articles.data && (
            <div className="public-guide-grid">
              {articles.data.map((article) => (
                <ArticleCard key={article.slug} article={article} />
              ))}
              {articles.data.length === 0 && (
                <p>
                  Новые материалы появятся здесь после проверки источников и редакторского review.
                </p>
              )}
            </div>
          )}
        </section>
      </main>
    </ArticleLayout>
  );
}

function ArticleMetadata({ article }: { article: WebArticle }) {
  return (
    <dl className="public-guide-meta">
      <div>
        <dt>Автор</dt>
        <dd>{article.author.name}</dd>
      </div>
      <div>
        <dt>Редактор</dt>
        <dd>{article.editor.name}</dd>
      </div>
      {article.domain_reviewer && (
        <div>
          <dt>Проверил</dt>
          <dd>{article.domain_reviewer.name}</dd>
        </div>
      )}
      <div>
        <dt>Опубликовано</dt>
        <dd>
          <time dateTime={article.published_at}>{formatDate(article.published_at)}</time>
        </dd>
      </div>
      <div>
        <dt>Обновлено</dt>
        <dd>
          <time dateTime={article.updated_at}>{formatDate(article.updated_at)}</time>
        </dd>
      </div>
    </dl>
  );
}

function ArticleDetail({ slug }: { slug: string }) {
  const article = useQuery({
    queryKey: ['public', 'article', slug],
    queryFn: () => api<WebArticle>(`/api/v1/public/articles/${slug}`),
  });
  const related = useQuery({
    queryKey: ['public', 'articles'],
    queryFn: () => api<WebArticleCard[]>('/api/v1/public/articles'),
  });

  useEffect(() => {
    if (!article.data) return;
    const seoData: PublicArticleSeoData = {
      slug: article.data.slug,
      title: article.data.title,
      description: article.data.description,
      canonical_url: article.data.canonical_url,
      published_at: article.data.published_at,
      updated_at: article.data.updated_at,
      author: article.data.author,
      editor: article.data.editor,
      domain_reviewer: article.data.domain_reviewer,
    };
    applyArticleRouteMetadata(`/articles/${slug}`, seoData);
    trackProductEvent(
      { name: 'article_viewed', surface: productEventSurface(), content_key: article.data.slug },
      { dedupe: 'session', dedupeKey: article.data.slug },
    );
  }, [article.data, slug]);

  if (article.isLoading)
    return (
      <ArticleLayout>
        <main className="public-main">
          <p role="status">Загружаем статью…</p>
        </main>
      </ArticleLayout>
    );
  if (article.error instanceof ApiError && article.error.status === 404) return <NotFoundPage />;
  if (article.error || !article.data) {
    return (
      <ArticleLayout>
        <main className="public-main">
          <div role="alert" className="public-inline-error">
            <p>Статья временно недоступна.</p>
          </div>
        </main>
      </ArticleLayout>
    );
  }

  const data = article.data;
  const relatedArticles =
    related.data?.filter((item) => data.related_slugs.includes(item.slug)) ?? [];
  const appUrl = appUrlForHostname(window.location.hostname);
  const ctaHref =
    data.cta.destination === 'landing'
      ? '/'
      : data.cta.destination === 'tma'
        ? PUBLIC_TELEGRAM_LINKS.miniApp
        : appUrl;

  return (
    <ArticleLayout>
      <main id="public-content" className="public-main" tabIndex={-1}>
        <nav className="public-breadcrumbs" aria-label="Хлебные крошки">
          <ol>
            <li>
              <AppLink to="/">Главная</AppLink>
            </li>
            <li>
              <AppLink to="/articles">Статьи</AppLink>
            </li>
            <li>
              <span aria-current="page">{data.title}</span>
            </li>
          </ol>
        </nav>
        <article className="public-article public-article--guide public-article--web-article">
          <header className="public-hero">
            <div className="public-hero__copy">
              <p className="landing-kicker">{data.topics.join(' · ')}</p>
              <h1>{data.title}</h1>
              <p className="public-hero__lead">{data.lead}</p>
              <ArticleMetadata article={data} />
            </div>
            <aside className="public-hero__summary" aria-label="Коротко о статье">
              <span>{ARTICLE_KIND_LABELS[data.article_kind]}</span>
              <strong>Ответ на intent — с источниками и ограничениями.</strong>
              <p>
                Материал не заменяет индивидуальную медицинскую помощь и не обещает гарантированный
                результат.
              </p>
            </aside>
          </header>
          <nav className="public-contents" aria-label="Оглавление">
            <strong>В этом материале</strong>
            <ol>
              {data.body_sections.map((section, index) => (
                <li key={section.heading}>
                  <a href={`#article-section-${index + 1}`}>{section.heading}</a>
                </li>
              ))}
            </ol>
          </nav>
          <div className="public-body">
            {data.body_sections.map((section, index) => (
              <section id={`article-section-${index + 1}`} key={section.heading}>
                <h2>{section.heading}</h2>
                {section.paragraphs.map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
                {section.points.length > 0 && (
                  <ul>
                    {section.points.map((point) => (
                      <li key={point}>{point}</li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
          </div>
          <section className="public-sources" aria-labelledby="article-sources-title">
            <div className="public-section-heading">
              <p className="landing-kicker">Проверяемые утверждения</p>
              <h2 id="article-sources-title">Источники</h2>
            </div>
            <ol>
              {data.sources.map((source) => (
                <li key={source.source_id}>
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.title}
                  </a>
                  <span>{source.publisher}</span>
                </li>
              ))}
            </ol>
          </section>
          {relatedArticles.length > 0 && (
            <section className="public-related" aria-labelledby="article-related-title">
              <div className="public-section-heading">
                <p className="landing-kicker">Продолжить</p>
                <h2 id="article-related-title">Связанные статьи</h2>
              </div>
              <div className="public-related-grid">
                {relatedArticles.map((item) => (
                  <AppLink
                    className="public-related-card"
                    key={item.slug}
                    to={`/articles/${item.slug}`}
                  >
                    <strong>{item.title}</strong>
                    <span>{item.description}</span>
                    <small>Открыть →</small>
                  </AppLink>
                ))}
              </div>
            </section>
          )}
          <section className="public-cta" aria-labelledby="article-cta-title">
            <div>
              <p className="landing-kicker">Следующий шаг</p>
              <h2 id="article-cta-title">{data.cta.label}</h2>
              <p>{data.cta.description}</p>
            </div>
            <a
              className="landing-button landing-action"
              href={ctaHref}
              onClick={() =>
                trackProductEvent({
                  name: 'article_cta_clicked',
                  surface: productEventSurface(),
                  content_key: data.slug,
                  destination: data.cta.destination,
                })
              }
            >
              {data.cta.label}
              <span className="landing-action__arrow" aria-hidden="true">
                <Icon name="external-link" size={16} />
              </span>
            </a>
          </section>
        </article>
      </main>
    </ArticleLayout>
  );
}

export default function ArticlesPage() {
  const { path } = useNavigation();
  if (window.Telegram?.WebApp?.initData) return <Redirect to="/app" />;
  if (path === '/articles') return <ArticlesIndex />;
  const slug = path.slice('/articles/'.length);
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) return <NotFoundPage />;
  return <ArticleDetail slug={slug} />;
}
