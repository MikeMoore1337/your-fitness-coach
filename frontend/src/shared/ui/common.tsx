import { useId, useState, type ComponentPropsWithoutRef, type ReactNode } from 'react';
import { handleTabKeyDown } from './tabs';
import { Icon, type IconName } from './Icon';
import { glassProps, type GlassVariant } from './Glass';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type BadgeTone = 'neutral' | 'success' | 'warning' | 'danger';
export type SemanticCardFamily = 'training' | 'nutrition' | 'progress' | 'wellbeing' | 'neutral';
export type SemanticCardVariant = 'summary' | 'action' | 'section';

function semanticCardClassName(
  family: SemanticCardFamily | undefined,
  variant: SemanticCardVariant,
): string {
  return family ? ` semantic-card semantic-card--${variant} semantic-card--${family}` : '';
}

export function Button({
  className = '',
  fullWidth = false,
  variant = 'primary',
  glass,
  ...props
}: ComponentPropsWithoutRef<'button'> & {
  fullWidth?: boolean;
  variant?: ButtonVariant;
  glass?: GlassVariant;
}) {
  return (
    <button
      {...(glass ? glassProps(glass, true) : {})}
      {...props}
      className={`ui-button ui-button--${variant}${fullWidth ? ' ui-button--full' : ''} ${className}`.trim()}
    />
  );
}

export function IconButton({
  className = '',
  ...props
}: ComponentPropsWithoutRef<'button'> & { 'aria-label': string }) {
  return (
    <button
      {...glassProps('clear', true)}
      {...props}
      className={`ui-icon-button ${className}`.trim()}
    />
  );
}

export function Field({
  children,
  error,
  hint,
  label,
  labelFor,
}: {
  children: ReactNode;
  error?: string;
  hint?: string;
  label: string;
  labelFor: string;
}) {
  return (
    <div className="ui-field">
      <label className="ui-field__label" htmlFor={labelFor}>
        {label}
      </label>
      {children}
      {error ? (
        <span className="ui-field__error" role="alert">
          {error}
        </span>
      ) : (
        hint && <span className="ui-field__hint">{hint}</span>
      )}
    </div>
  );
}

export function Input({ className = '', ...props }: ComponentPropsWithoutRef<'input'>) {
  return <input {...props} className={`ui-input ${className}`.trim()} />;
}

export function Select({ className = '', ...props }: ComponentPropsWithoutRef<'select'>) {
  return (
    <select
      {...glassProps('tinted', true)}
      {...props}
      className={`ui-select ${className}`.trim()}
    />
  );
}

export function Surface({
  children,
  className = '',
  elevated = false,
  subtle = false,
  ...props
}: ComponentPropsWithoutRef<'section'> & { elevated?: boolean; subtle?: boolean }) {
  const variants = `${subtle ? ' ui-surface--subtle' : ''}${elevated ? ' ui-surface--raised' : ''}`;
  return (
    <section {...props} className={`ui-surface${variants} ${className}`.trim()}>
      {children}
    </section>
  );
}

export function SectionHeader({
  actions,
  description,
  title,
}: {
  actions?: ReactNode;
  description?: string;
  title: string;
}) {
  return (
    <div className="ui-section-header">
      <div className="ui-section-header__copy">
        <h2 className="ui-section-header__title">{title}</h2>
        {description && <p className="ui-section-header__description">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

export function Metric({ hint, label, value }: { hint?: string; label: string; value: ReactNode }) {
  return (
    <div className="ui-metric">
      <span className="ui-metric__label">{label}</span>
      <strong className="ui-metric__value">{value}</strong>
      {hint && <span className="ui-metric__hint">{hint}</span>}
    </div>
  );
}

export function SegmentedControl({
  ariaLabel,
  onChange,
  options,
  value,
}: {
  ariaLabel: string;
  onChange: (value: string) => void;
  options: readonly { label: string; value: string; disabled?: boolean }[];
  value: string;
}) {
  return (
    <div {...glassProps()} aria-label={ariaLabel} className="ui-tabs" role="tablist">
      {options.map((option) => (
        <button
          aria-selected={option.value === value}
          {...(option.value === value ? glassProps('clear', true) : {})}
          className="ui-tab"
          disabled={option.disabled}
          key={option.value}
          onClick={() => onChange(option.value)}
          onKeyDown={handleTabKeyDown}
          role="tab"
          type="button"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Skeleton({
  className = '',
  height,
  width,
}: {
  className?: string;
  height?: string;
  width?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={`ui-skeleton ${className}`.trim()}
      style={{ height, width }}
    />
  );
}

export function Card({
  id,
  title,
  description,
  actions,
  children,
  className = '',
  collapsible = true,
  defaultOpen = false,
  family,
  summary,
  variant = 'section',
}: {
  id?: string;
  title?: ReactNode;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Application cards start collapsed to keep long pages easy to scan. */
  collapsible?: boolean;
  /** Contextual deep links may reveal one disclosure without expanding the rest. */
  defaultOpen?: boolean;
  /** Shared visual meaning; omitted for dense forms and utility containers. */
  family?: SemanticCardFamily;
  /** One key fact that keeps the collapsed state useful. */
  summary?: ReactNode;
  variant?: SemanticCardVariant;
}) {
  if (collapsible && (title || description)) {
    return (
      <ExpandableCard
        actions={actions}
        className={className}
        defaultOpen={defaultOpen}
        description={description}
        family={family}
        id={id}
        summary={summary}
        title={title}
        variant={variant}
      >
        {children}
      </ExpandableCard>
    );
  }

  const semanticClasses = semanticCardClassName(family, variant);
  return (
    <section
      className={`card${semanticClasses} ${className}`.trim()}
      data-card-variant={family ? variant : undefined}
      data-semantic-family={family}
      id={id}
    >
      {(title || description || actions) && (
        <div className="section-head">
          <div>
            {title && <h2>{title}</h2>}
            {description && <p className="muted top-gap">{description}</p>}
            {summary && <div className="semantic-card__summary">{summary}</div>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function ExpandableCard({
  actions,
  children,
  className = '',
  defaultOpen = false,
  description,
  family,
  id,
  summary,
  title,
  variant = 'section',
}: {
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  defaultOpen?: boolean;
  description?: string;
  family?: SemanticCardFamily;
  id?: string;
  summary?: ReactNode;
  title?: ReactNode;
  variant?: SemanticCardVariant;
}) {
  const generatedId = useId();
  const [disclosureOpen, setDisclosureOpen] = useState(defaultOpen);
  const bodyId = `${id ?? `semantic-card-${generatedId}`}-details`;
  const semanticClasses = semanticCardClassName(family, variant);

  return (
    <details
      className={`card card-disclosure${semanticClasses} ${className}`.trim()}
      data-card-variant={family ? variant : undefined}
      data-semantic-family={family}
      id={id}
      onToggle={(event) => setDisclosureOpen(event.currentTarget.open)}
      open={disclosureOpen}
    >
      <summary
        aria-controls={bodyId}
        aria-expanded={disclosureOpen}
        onClick={(event) => {
          event.preventDefault();
          setDisclosureOpen((current) => !current);
        }}
      >
        <span>
          {title && <h2>{title}</h2>}
          {summary && <span className="semantic-card__summary">{summary}</span>}
          {description && <small>{description}</small>}
        </span>
        <DisclosureIcon />
      </summary>
      <div className="card-disclosure__body" id={bodyId}>
        {actions && <div className="card-disclosure__actions">{actions}</div>}
        {children}
      </div>
    </details>
  );
}

export function SemanticCard({
  action,
  children,
  className = '',
  eyebrow,
  family,
  icon,
  summary,
  title,
  variant = 'summary',
}: {
  action?: ReactNode;
  children?: ReactNode;
  className?: string;
  eyebrow?: string;
  family: SemanticCardFamily;
  icon?: IconName;
  summary: ReactNode;
  title: ReactNode;
  variant?: SemanticCardVariant;
}) {
  const titleId = useId();

  return (
    <article
      aria-labelledby={titleId}
      className={`semantic-card semantic-card--compact semantic-card--${variant} semantic-card--${family} ${className}`.trim()}
      data-card-variant={variant}
      data-semantic-family={family}
    >
      {icon && (
        <span aria-hidden="true" className="semantic-card__icon">
          <Icon name={icon} size={20} />
        </span>
      )}
      <div className="semantic-card__copy">
        {eyebrow && <span className="semantic-card__eyebrow">{eyebrow}</span>}
        <h2 id={titleId}>{title}</h2>
        <div className="semantic-card__summary">{summary}</div>
      </div>
      {action && <div className="semantic-card__action">{action}</div>}
      {children && <div className="semantic-card__body">{children}</div>}
    </article>
  );
}

export function LoadingState({ label = 'Загрузка…' }: { label?: string }) {
  return (
    <div aria-busy="true" className="empty-state ui-state" role="status">
      <Icon className="ui-state__icon ui-state__icon--loading" name="loading" size={24} />
      <p className="ui-state__text">{label}</p>
    </div>
  );
}

export function EmptyState({ title, text }: { title: string; text?: string }) {
  return (
    <div className="empty-state ui-state">
      <p className="empty-state__title ui-state__title">{title}</p>
      {text && <p className="empty-state__text ui-state__text">{text}</p>}
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="empty-state error-state ui-state ui-state--error" role="alert">
      <Icon className="ui-state__icon" name="error" size={24} />
      <p className="empty-state__title ui-state__title">Не удалось загрузить данные</p>
      <p className="muted ui-state__text">{message}</p>
      {retry && (
        <Button onClick={retry} type="button" variant="secondary">
          Повторить
        </Button>
      )}
    </div>
  );
}

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: BadgeTone | 'badge-danger';
}) {
  const normalizedTone = tone === 'badge-danger' ? 'danger' : tone;
  return (
    <span
      className={`badge ui-badge ui-badge--${normalizedTone} ${tone === 'badge-danger' ? tone : ''}`.trim()}
    >
      {children}
    </span>
  );
}

export function CloseIcon({ className = '' }: { className?: string }) {
  return <Icon className={`ui-icon ${className}`.trim()} name="close" size={16} />;
}

export function TrashIcon({ className = '' }: { className?: string }) {
  return <Icon className={`ui-icon ${className}`.trim()} name="trash" size={16} />;
}

export function ChevronIcon({
  direction = 'right',
  className = '',
}: {
  direction?: 'left' | 'right' | 'down';
  className?: string;
}) {
  return <Icon className={`ui-icon ${className}`.trim()} name={`chevron-${direction}`} size={16} />;
}

export function CheckIcon({ className = '' }: { className?: string }) {
  return <Icon className={`ui-icon ${className}`.trim()} name="check" size={16} />;
}

export function DisclosureIcon() {
  return (
    <span className="disclosure-icon" aria-hidden="true">
      <Icon name="disclosure-closed" size={16} />
    </span>
  );
}
