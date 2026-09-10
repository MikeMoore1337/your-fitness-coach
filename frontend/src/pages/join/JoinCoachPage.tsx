import { AppShell } from '../../app/AppShell';
import '../../styles/react.css';
import '../../styles/design-v2.css';
import { CoachInvites } from '../../features/profile/CoachInvites';

export default function JoinCoachPage({ token }: { token: string }) {
  return (
    <AppShell narrow>
      <div className="page-stack">
        <header className="card hero-card">
          <div>
            <span className="eyebrow">Персональное приглашение</span>
            <h1>Подключение к тренеру</h1>
            <p className="muted">
              Проверьте имя тренера и подтвердите подключение. Без вашего согласия доступ не
              предоставляется.
            </p>
          </div>
        </header>
        <CoachInvites initialToken={token} />
      </div>
    </AppShell>
  );
}
