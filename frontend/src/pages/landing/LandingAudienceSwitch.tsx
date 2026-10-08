import { landingAudienceHref, type LandingAudience, type LandingLocation } from './landingAudience';
import './landing-v10.css';

type LandingAudienceSwitchProps = {
  audience: LandingAudience;
  location?: LandingLocation;
  onNavigate?: () => void;
  showLabel?: boolean;
};

const AUDIENCES: ReadonlyArray<{ id: LandingAudience; label: string }> = [
  { id: 'athlete', label: 'Для себя' },
  { id: 'coach', label: 'Для тренера' },
];

export function LandingAudienceSwitch({
  audience,
  location,
  onNavigate,
  showLabel = true,
}: LandingAudienceSwitchProps) {
  return (
    <nav className="landing-v10-audience-switch" aria-label="Выбор аудитории">
      {showLabel && <span className="landing-v10-audience-switch__label">Сценарий</span>}
      <div className="landing-v10-audience-switch__links">
        {AUDIENCES.map((item) => (
          <a
            key={item.id}
            className="landing-v10-audience-switch__link"
            href={landingAudienceHref(item.id, location)}
            aria-current={item.id === audience ? 'page' : undefined}
            data-audience={item.id}
            onClick={onNavigate}
          >
            {item.label}
          </a>
        ))}
      </div>
    </nav>
  );
}
