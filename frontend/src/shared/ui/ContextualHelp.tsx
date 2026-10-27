import { useState, type ReactNode } from 'react';
import { PublicWebLink } from '../navigation/PublicWebLink';
import { Icon } from './Icon';
import { DisclosureIcon } from './common';

export function ContextualHelp({
  children,
  articlePath,
  summary = 'Что это?',
}: {
  children: ReactNode;
  articlePath?: string;
  summary?: string;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <details
      className="contextual-help"
      onToggle={(event) => setExpanded(event.currentTarget.open)}
    >
      <summary
        aria-expanded={expanded}
        className="yfc-disclosure-summary"
        onClick={() => setExpanded((value) => !value)}
        onKeyDown={(event) => {
          if (event.key !== 'Escape') return;
          const details = event.currentTarget.parentElement;
          if (!(details instanceof HTMLDetailsElement) || !details.open) return;
          event.preventDefault();
          details.open = false;
          setExpanded(false);
        }}
      >
        {summary}
        <DisclosureIcon />
      </summary>
      <div className="contextual-help__body">
        <div>{children}</div>
        {articlePath ? (
          <PublicWebLink className="contextual-help__link" path={articlePath}>
            Подробнее на сайте <Icon name="external-link" size={16} />
          </PublicWebLink>
        ) : (
          <p className="contextual-help__source-fallback">Источник: нет ссылки.</p>
        )}
      </div>
    </details>
  );
}
