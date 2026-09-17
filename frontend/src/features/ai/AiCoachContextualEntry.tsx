import type { MouseEvent } from 'react';
import { AppLink } from '../../shared/navigation/router';
import {
  productEventSurface,
  trackProductEvent,
  type AiCoachEntryPoint,
} from '../../shared/analytics/productEvents';
import { Icon } from '../../shared/ui/Icon';
import { useOptionalAiCoachWorkspace } from './AiCoachWorkspaceContext';
import { useAiCoachStatus } from './AiCoachExperience';
import { aiCoachContextLabel, type AiCoachContextDescriptor } from './aiCoachContext';

const AI_COACH_FALLBACK_PATH = '/app?section=profile#profile-ai-coach';

export function AiCoachContextualEntry({
  context,
  entryPoint,
  actionLabel = 'Открыть AI Coach',
}: {
  context: AiCoachContextDescriptor;
  entryPoint: AiCoachEntryPoint;
  actionLabel?: string;
}) {
  const status = useAiCoachStatus();
  const workspace = useOptionalAiCoachWorkspace();
  if (!status.data?.ui_enabled) return null;

  const label = aiCoachContextLabel(context);
  const handleOpen = (event: MouseEvent<HTMLAnchorElement>) => {
    if (workspace) {
      event.preventDefault();
      workspace.open(event.currentTarget, 'chat', context);
    }
    trackProductEvent({
      name: 'ai_coach_entry_opened',
      surface: productEventSurface(),
      entry_point: entryPoint,
    });
  };

  return (
    <aside
      className="ai-coach-contextual-entry"
      data-testid={`ai-coach-contextual-entry-${entryPoint}`}
    >
      <div className="ai-coach-contextual-entry__copy">
        <span className="eyebrow">
          <Icon name="ai-coach" size={16} /> AI Coach
        </span>
        <strong>Разобрать: {label.toLocaleLowerCase('ru-RU')}</strong>
        <p>Откроем чат рядом с этим экраном. Вопрос можно изменить перед отправкой.</p>
      </div>
      <AppLink
        className="button-link secondary-link"
        to={AI_COACH_FALLBACK_PATH}
        onClick={handleOpen}
      >
        {actionLabel}
      </AppLink>
    </aside>
  );
}
