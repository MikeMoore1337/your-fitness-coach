import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  categoryForSlug,
  getPublicContentPage,
  publicContent,
  publicGuides,
  publicExercisePages,
  type PublicContentPage as PublicContentPageData,
} from '../../content/publicContent';
import { api } from '../../shared/api/client';
import type { PublicExerciseDetail, PublicExerciseSummary } from '../../shared/api/types';
import { appUrlForHostname } from '../../shared/navigation/appUrl';
import { AppLink, Redirect, useNavigation } from '../../shared/navigation/router';
import { BrandLockup } from '../../shared/ui/BrandLogo';
import { AppThemeToggle } from '../../shared/ui/AppThemeToggle';
import { Icon } from '../../shared/ui/Icon';
import { useWebTheme } from '../../shared/useWebTheme';
import { applyRouteMetadata } from '../../shared/seo/metadata';
import PublicBmiCalculator from './PublicBmiCalculator';
import '../../shared/ui/public-shell.css';
import '../landing/landing.css';
import './public-content.css';
import NotFoundPage from '../NotFoundPage';
import '../../styles/react.css';
import '../../styles/design-v2.css';

export function PublicHeader({ theme }: { theme: 'light' | 'dark' }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);

  useEffect(() => {
    if (!menuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [menuOpen]);

  return (
    <header className="public-shell__header landing-header public-header">
      <AppLink
        className="public-shell__brand landing-brand"
        to="/"
        aria-label="Your Fitness Coach — на главную"
      >
        <BrandLockup
          className="public-shell__lockup public-header__lockup"
          markClassName="public-shell__logo landing-brand__mark"
          surface={theme}
        />
      </AppLink>
      <nav
        id="public-navigation"
        className={`landing-nav${menuOpen ? ' is-open' : ''}`}
        aria-label="Публичные разделы"
      >
        <AppLink to="/training" onClick={closeMenu}>
          Тренировки
        </AppLink>
        <AppLink to="/nutrition" onClick={closeMenu}>
          Питание
        </AppLink>
        <AppLink to="/progress" onClick={closeMenu}>
          Прогресс
        </AppLink>
        <AppLink to="/knowledge" onClick={closeMenu}>
          База знаний
        </AppLink>
        <AppLink to="/articles" onClick={closeMenu}>
          Статьи
        </AppLink>
        <AppLink to="/exercises" onClick={closeMenu}>
          Упражнения
        </AppLink>
        <AppLink to="/for-trainers" onClick={closeMenu}>
          Тренерам
        </AppLink>
      </nav>
      <div className="public-shell__header-actions landing-header__actions">
        <AppThemeToggle landing />
        <a
          className="landing-button landing-button--compact"
          href={appUrlForHostname(window.location.hostname)}
        >
          Войти
        </a>
        <button
          type="button"
          className={`landing-menu-toggle${menuOpen ? ' is-open' : ''}`}
          aria-label={menuOpen ? 'Закрыть меню' : 'Открыть меню'}
          aria-expanded={menuOpen}
          aria-controls="public-navigation"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <Icon name={menuOpen ? 'close' : 'menu'} />
        </button>
      </div>
    </header>
  );
}

function Breadcrumbs({ page }: { page: PublicContentPageData }) {
  if (page.breadcrumbs.length < 2) return null;
  return (
    <nav className="public-breadcrumbs" aria-label="Хлебные крошки">
      <ol>
        {page.breadcrumbs.map((item, index) => (
          <li key={item.path}>
            {index === page.breadcrumbs.length - 1 ? (
              <span aria-current="page">{item.label}</span>
            ) : (
              <AppLink to={item.path}>{item.label}</AppLink>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

function GuideMetadata({ page }: { page: PublicContentPageData }) {
  if (page.kind !== 'guide' || !page.author || !page.updated) return null;
  const formatDate = (value: string) =>
    new Intl.DateTimeFormat('ru-RU', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(new Date(`${value}T00:00:00Z`));
  return (
    <dl className="public-guide-meta">
      <div>
        <dt>Автор</dt>
        <dd>{page.author.name}</dd>
      </div>
      {page.reviewer && (
        <div>
          <dt>Проверил</dt>
          <dd>{page.reviewer.name}</dd>
        </div>
      )}
      {page.published && (
        <div>
          <dt>Опубликовано</dt>
          <dd>
            <time dateTime={page.published}>{formatDate(page.published)}</time>
          </dd>
        </div>
      )}
      <div>
        <dt>Обновлено</dt>
        <dd>
          <time dateTime={page.updated}>{formatDate(page.updated)}</time>
        </dd>
      </div>
      {page.reviewed && (
        <div>
          <dt>Источники проверены</dt>
          <dd>
            <time dateTime={page.reviewed}>{formatDate(page.reviewed)}</time>
          </dd>
        </div>
      )}
    </dl>
  );
}

function sectionId(page: PublicContentPageData, index: number): string {
  return `${page.id ?? page.slug ?? 'public-section'}-${index + 1}`;
}

function GuideContents({ page }: { page: PublicContentPageData }) {
  if (page.kind !== 'guide' || page.sections.length < 2) return null;
  return (
    <nav className="public-contents" aria-label="Оглавление">
      <strong>В этом материале</strong>
      <ol>
        {page.sections.map((section, index) => (
          <li key={section.heading}>
            <a href={`#${sectionId(page, index)}`}>{section.heading}</a>
          </li>
        ))}
        {page.interactive === 'bmi-calculator' && (
          <li>
            <a href="#public-bmi-calculator">Калькулятор ИМТ</a>
          </li>
        )}
        {page.sources && page.sources.length > 0 && (
          <li>
            <a href="#public-sources-title">Источники</a>
          </li>
        )}
      </ol>
    </nav>
  );
}

function KnowledgeDirectory() {
  const guides = publicGuides();
  return (
    <section className="public-directory" aria-labelledby="knowledge-directory-title">
      <div className="public-section-heading">
        <p className="landing-kicker">Опубликованные руководства</p>
        <h2 id="knowledge-directory-title">Небольшая база без пустых страниц</h2>
      </div>
      <div className="public-guide-grid">
        {guides.map((guide) => {
          const category = categoryForSlug(guide.category);
          return (
            <article className="public-guide-card" key={guide.path}>
              <p>{category?.label ?? 'Руководство'}</p>
              <h3>
                <AppLink to={guide.path}>{guide.heading}</AppLink>
              </h3>
              <p>{guide.description}</p>
              <AppLink className="public-inline-link" to={guide.path}>
                Читать руководство <Icon name="arrow-right" size={16} />
              </AppLink>
            </article>
          );
        })}
      </div>
      <div className="public-category-list" aria-label="Категории базы знаний">
        {publicContent.categories.map((category) => {
          const count =
            category.slug === 'exercises'
              ? publicExercisePages().length
              : guides.filter((guide) => guide.category === category.slug).length;
          return (
            <div key={category.slug}>
              <strong>{category.label}</strong>
              <span>{category.description}</span>
              <small>
                {count > 0 ? `Опубликовано: ${count}` : 'Новые страницы — только после проверки'}
              </small>
            </div>
          );
        })}
      </div>
    </section>
  );
}

const difficultyLabels: Record<PublicExerciseSummary['difficulty_level'], string> = {
  beginner: 'Начальный уровень',
  intermediate: 'Средний уровень',
  advanced: 'Продвинутый уровень',
};

function PublicExerciseDirectory() {
  const pages = publicExercisePages();
  const exercises = useQuery({
    queryKey: ['public', 'exercises'],
    queryFn: () => api<PublicExerciseSummary[]>('/api/v1/public/exercises'),
  });
  const records = new Map(exercises.data?.map((exercise) => [exercise.slug, exercise]));

  return (
    <section className="public-directory" aria-labelledby="exercise-directory-title">
      <div className="public-section-heading">
        <p className="landing-kicker">Опубликованные карточки</p>
        <h2 id="exercise-directory-title">Техника из общего каталога упражнений</h2>
      </div>
      {exercises.isLoading && <p role="status">Загружаем карточки упражнений…</p>}
      {exercises.error && (
        <div role="alert" className="public-inline-error">
          <p>Карточки временно недоступны. Попробуйте ещё раз.</p>
          <button type="button" className="landing-button" onClick={() => void exercises.refetch()}>
            Повторить
          </button>
        </div>
      )}
      {exercises.data && (
        <div className="public-guide-grid">
          {pages.map((page) => {
            const exercise = page.slug ? records.get(page.slug) : undefined;
            if (!exercise) return null;
            return (
              <article className="public-guide-card" key={page.path}>
                <p>
                  {exercise.primary_muscle} · {exercise.equipment}
                </p>
                <h3>
                  <AppLink to={page.path}>{exercise.title}</AppLink>
                </h3>
                <p>
                  {difficultyLabels[exercise.difficulty_level]}. Пошаговая техника и частые ошибки.
                </p>
                <AppLink className="public-inline-link" to={page.path}>
                  Открыть карточку <Icon name="arrow-right" size={16} />
                </AppLink>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function PublicExerciseDetails({ page }: { page: PublicContentPageData }) {
  const details = useQuery({
    queryKey: ['public', 'exercises', page.slug],
    queryFn: () => api<PublicExerciseDetail>(`/api/v1/public/exercises/${page.slug}`),
    enabled: Boolean(page.slug),
  });

  if (details.isLoading) return <p role="status">Загружаем технику упражнения…</p>;
  if (details.error || !details.data) {
    return (
      <div role="alert" className="public-inline-error">
        <p>Техника временно недоступна. Попробуйте ещё раз.</p>
        <button type="button" className="landing-button" onClick={() => void details.refetch()}>
          Повторить
        </button>
      </div>
    );
  }

  const exercise = details.data;
  return (
    <div className="public-body public-exercise-body">
      <section>
        <h2>Краткие сведения</h2>
        <dl className="public-exercise-facts">
          <div>
            <dt>Основная группа</dt>
            <dd>{exercise.primary_muscle}</dd>
          </div>
          <div>
            <dt>Оборудование</dt>
            <dd>{exercise.equipment}</dd>
          </div>
          <div>
            <dt>Сложность</dt>
            <dd>{difficultyLabels[exercise.difficulty_level]}</dd>
          </div>
        </dl>
        {exercise.secondary_muscles.length > 0 && (
          <p>Дополнительно работают: {exercise.secondary_muscles.join(', ')}.</p>
        )}
      </section>
      <section>
        <h2>Техника выполнения</h2>
        <ol>
          {exercise.technique_steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>
      <section>
        <h2>Дыхание</h2>
        <p>{exercise.breathing}</p>
      </section>
      <section>
        <h2>Частые ошибки</h2>
        <ul>
          {exercise.common_mistakes.map((mistake) => (
            <li key={mistake}>{mistake}</li>
          ))}
        </ul>
      </section>
      <section>
        <h2>Что важно для безопасности</h2>
        <ul>
          {exercise.safety_notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </section>
      <footer className="public-exercise-source">
        <strong>Источник данных и лицензия</strong>
        <p>
          <a href={exercise.source_url} target="_blank" rel="noreferrer">
            {exercise.source_name}
          </a>
          {' · '}
          {exercise.source_license_url ? (
            <a href={exercise.source_license_url} target="_blank" rel="noreferrer">
              {exercise.source_license}
            </a>
          ) : (
            exercise.source_license
          )}
        </p>
      </footer>
    </div>
  );
}

function RelatedContent({ page }: { page: PublicContentPageData }) {
  return (
    <section className="public-related" aria-labelledby="public-related-title">
      <div className="public-section-heading">
        <p className="landing-kicker">Продолжить</p>
        <h2 id="public-related-title">Связанные материалы и возможности</h2>
      </div>
      <div className="public-related-grid">
        {page.related.map((item) => (
          <AppLink className="public-related-card" to={item.path} key={item.path}>
            <strong>{item.label}</strong>
            {item.description && <span>{item.description}</span>}
            <small>
              Открыть <Icon name="arrow-right" size={16} />
            </small>
          </AppLink>
        ))}
      </div>
    </section>
  );
}

export function PublicFooter({ theme }: { theme: 'light' | 'dark' }) {
  return (
    <footer className="landing-footer public-footer">
      <AppLink className="landing-brand" to="/" aria-label="Your Fitness Coach — на главную">
        <BrandLockup
          className="public-footer__lockup"
          markClassName="landing-brand__mark"
          surface={theme}
        />
      </AppLink>
      <nav aria-label="Разделы в подвале">
        <AppLink to="/training">Тренировки</AppLink>
        <AppLink to="/nutrition">Питание</AppLink>
        <AppLink to="/knowledge">База знаний</AppLink>
        <AppLink to="/articles">Статьи</AppLink>
        <AppLink to="/exercises">Упражнения</AppLink>
        <AppLink to="/for-trainers">Тренерам</AppLink>
      </nav>
      <span>© {new Date().getFullYear()}</span>
    </footer>
  );
}

export default function PublicContentPage() {
  const { path } = useNavigation();
  const page = getPublicContentPage(path);
  const { colorScheme: theme } = useWebTheme();

  useEffect(() => {
    applyRouteMetadata(path, page);
  }, [page, path]);

  useEffect(() => {
    document.body.classList.add('public-shell-mode');
    document.body.classList.toggle('public-shell-dark-mode', theme === 'dark');
    return () => {
      document.body.classList.remove('public-shell-mode', 'public-shell-dark-mode');
    };
  }, [theme]);

  if (!page || page.kind === 'landing') return <NotFoundPage />;
  if (window.Telegram?.WebApp?.initData) return <Redirect to="/app" />;

  const appUrl = appUrlForHostname(window.location.hostname);

  return (
    <div
      className={`public-shell public-shell--design-v2 public-shell--${theme} landing-page landing-page--${theme} public-page public-page--design-v2`}
    >
      <a
        className="landing-skip-link"
        href="#public-content"
        onClick={() => document.querySelector<HTMLElement>('#public-content')?.focus()}
      >
        К содержимому
      </a>
      <PublicHeader theme={theme} />
      <main id="public-content" className="public-main" tabIndex={-1}>
        <Breadcrumbs page={page} />
        <article className={`public-article public-article--${page.kind}`}>
          <header className="public-hero">
            <div className="public-hero__copy">
              <p className="landing-kicker">{page.eyebrow}</p>
              <h1>{page.heading}</h1>
              <p className="public-hero__lead">{page.intro}</p>
              <GuideMetadata page={page} />
            </div>
            <aside className="public-hero__summary" aria-label="Коротко о странице">
              {page.highlights ? (
                <ul>
                  {page.highlights.map((highlight) => (
                    <li key={highlight}>{highlight}</li>
                  ))}
                </ul>
              ) : (
                <>
                  <span>Подход редакции</span>
                  <strong>Факты, ограничения и понятный следующий шаг</strong>
                  <p>Без гарантированных результатов, скрытой рекламы и выдуманной экспертизы.</p>
                </>
              )}
            </aside>
          </header>

          {page.disclaimer && <aside className="public-disclaimer">{page.disclaimer}</aside>}

          <GuideContents page={page} />

          <div className="public-body">
            {page.sections.map((section, index) => (
              <section id={sectionId(page, index)} key={section.heading}>
                <h2>{section.heading}</h2>
                {section.paragraphs.map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
                {section.points && (
                  <ul>
                    {section.points.map((point) => (
                      <li key={point}>{point}</li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
            {page.interactive === 'bmi-calculator' && <PublicBmiCalculator />}
          </div>

          {page.kind === 'knowledge-index' && <KnowledgeDirectory />}
          {page.kind === 'exercise-index' && <PublicExerciseDirectory />}
          {page.kind === 'exercise' && <PublicExerciseDetails page={page} />}

          {page.sources && page.sources.length > 0 && (
            <section className="public-sources" aria-labelledby="public-sources-title">
              <div className="public-section-heading">
                <p className="landing-kicker">Проверяемые утверждения</p>
                <h2 id="public-sources-title">Источники</h2>
              </div>
              <ol>
                {page.sources.map((source) => (
                  <li key={source.url}>
                    <a href={source.url} target="_blank" rel="noreferrer">
                      {source.title}
                    </a>
                    <span>{source.publisher}</span>
                  </li>
                ))}
              </ol>
            </section>
          )}

          <RelatedContent page={page} />

          {page.cta && (
            <section className="public-cta" aria-labelledby="public-cta-title">
              <div>
                <p className="landing-kicker">Следующий шаг</p>
                <h2 id="public-cta-title">{page.cta.label}</h2>
                <p>{page.cta.description}</p>
              </div>
              <a className="landing-button landing-action" href={appUrl}>
                {page.cta.label}
                <span className="landing-action__arrow" aria-hidden="true">
                  <Icon name="external-link" size={16} />
                </span>
              </a>
            </section>
          )}
        </article>
      </main>
      <PublicFooter theme={theme} />
    </div>
  );
}
