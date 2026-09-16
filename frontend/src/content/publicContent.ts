import manifest from './publicContent.json';

export interface PublicContentLink {
  path: string;
  label: string;
  description?: string;
}

export interface PublicContentSection {
  heading: string;
  paragraphs: string[];
  points?: string[];
}

export interface PublicContentSource {
  title: string;
  publisher: string;
  url: string;
  published?: string;
  sourceType?:
    | 'guideline'
    | 'systematic-review'
    | 'meta-analysis'
    | 'review'
    | 'primary-study'
    | 'domain-source';
}

export interface PublicContentPage {
  kind: 'landing' | 'product' | 'knowledge-index' | 'guide' | 'exercise-index' | 'exercise';
  id?: string;
  slug?: string;
  status?: 'draft' | 'review' | 'published' | 'archived';
  path: string;
  category?: string;
  tags?: string[];
  appContexts?: string[];
  title: string;
  description: string;
  ogDescription: string;
  eyebrow: string;
  heading: string;
  intro: string;
  highlights?: string[];
  sections: PublicContentSection[];
  interactive?: 'bmi-calculator' | 'kbju-calculator';
  related: PublicContentLink[];
  cta?: {
    label: string;
    description: string;
  };
  breadcrumbs: PublicContentLink[];
  updated?: string;
  published?: string;
  reviewed?: string;
  author?: {
    name: string;
    type: 'Organization' | 'Person';
  };
  reviewer?: {
    name: string;
    type: 'Organization' | 'Person';
  } | null;
  disclaimer?: string;
  sources?: PublicContentSource[];
}

export interface PublicContentCategory {
  slug: string;
  label: string;
  description: string;
}

interface PublicContentManifest {
  categories: PublicContentCategory[];
  pages: PublicContentPage[];
}

export const publicContent = manifest as PublicContentManifest;

function isPublished(page: PublicContentPage): boolean {
  return (page.status ?? 'published') === 'published';
}

export function getPublicContentPage(path: string): PublicContentPage | undefined {
  return publicContent.pages.find((page) => page.path === path && isPublished(page));
}

export function isPublicContentPath(path: string): boolean {
  const page = getPublicContentPage(path);
  return page !== undefined && page.kind !== 'landing';
}

export function isPublishedKnowledgePath(path: string): boolean {
  const page = getPublicContentPage(path);
  return page?.kind === 'knowledge-index' || page?.kind === 'guide';
}

export function publicGuides(): PublicContentPage[] {
  return publicContent.pages.filter((page) => page.kind === 'guide' && isPublished(page));
}

export function publicExercisePages(): PublicContentPage[] {
  return publicContent.pages.filter((page) => page.kind === 'exercise' && isPublished(page));
}

export function categoryForSlug(slug: string | undefined): PublicContentCategory | undefined {
  return publicContent.categories.find((category) => category.slug === slug);
}
