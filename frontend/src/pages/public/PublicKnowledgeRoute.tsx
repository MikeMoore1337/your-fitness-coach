import { isTelegramLaunch } from '../../shared/telegram/launch';
import { isPublishedKnowledgePath } from '../../content/publicContent';
import KnowledgeHandoffPage from './KnowledgeHandoffPage';
import PublicContentPage from './PublicContentPage';
import NotFoundPage from '../NotFoundPage';

type PublicKnowledgeRouteProps = {
  articlePath: string;
  legacyRoute?: boolean;
};

function isMiniAppLaunch(): boolean {
  return Boolean(window.Telegram?.WebApp?.initData?.trim()) || isTelegramLaunch(window.location);
}

export default function PublicKnowledgeRoute({
  articlePath,
  legacyRoute = false,
}: PublicKnowledgeRouteProps) {
  const publishedKnowledgePath = isPublishedKnowledgePath(articlePath);

  if (legacyRoute && !publishedKnowledgePath) return <NotFoundPage />;
  if ((legacyRoute || isMiniAppLaunch()) && publishedKnowledgePath) {
    return <KnowledgeHandoffPage articlePath={articlePath} />;
  }
  return <PublicContentPage />;
}
