import { AppLink, safeTrainerReturnPath } from '../../shared/navigation/router';
import './trainer-capability.css';

export function TrainerModeSwitch({
  clientName,
  mode,
  returnTo,
  sticky = false,
}: {
  clientName?: string;
  mode: 'personal' | 'clients';
  returnTo?: string;
  sticky?: boolean;
}) {
  const safeReturnTo = safeTrainerReturnPath(returnTo) ?? '/coach';
  const personalPath = `/app?section=today&trainer_return=${encodeURIComponent(safeReturnTo)}`;
  return (
    <div className={`trainer-mode-context${sticky ? ' trainer-mode-context--sticky' : ''}`}>
      <div className="trainer-mode-context__copy">
        <span>Режим</span>
        <strong>{mode === 'clients' ? 'Клиенты' : 'Для себя'}</strong>
        {clientName && <small title={clientName}>Клиент: {clientName}</small>}
      </div>
      <nav className="trainer-mode-switch" aria-label="Режим работы">
        <AppLink
          className={mode === 'personal' ? 'is-active' : ''}
          aria-current={mode === 'personal' ? 'page' : undefined}
          to={mode === 'personal' ? '/app?section=today' : personalPath}
        >
          Для себя
        </AppLink>
        <AppLink
          className={mode === 'clients' ? 'is-active' : ''}
          aria-current={mode === 'clients' ? 'page' : undefined}
          to={mode === 'personal' ? safeReturnTo : '/coach'}
        >
          {mode === 'personal' ? 'В кабинет тренера' : 'Клиенты'}
        </AppLink>
      </nav>
    </div>
  );
}
