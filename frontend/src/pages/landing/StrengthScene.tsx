import { useState } from 'react';
import { Icon } from '../../shared/ui/Icon';
import { useSemanticMotion } from '../../shared/ui/useSemanticMotion';
import './strength-scene.css';

export function StrengthScene() {
  const [failed, setFailed] = useState(false);
  const motion = useSemanticMotion<HTMLDivElement>('strength-scene', { observe: true });

  return (
    <div
      className="strength-scene"
      id={motion.elementId}
      data-motion-phase={motion.motionPhase}
      onAnimationEnd={motion.onMotionAnimationEnd}
      role="group"
      aria-label="Движение спортсмена и пример записи подхода"
    >
      <figure className="strength-scene__photo">
        {failed ? (
          <p>Изображение недоступно. Тренировки и демо остаются доступны.</p>
        ) : (
          <img
            src="/assets/marketing/strength-protocol-960.webp"
            srcSet="/assets/marketing/strength-protocol-640.webp 640w, /assets/marketing/strength-protocol-960.webp 960w, /assets/marketing/strength-protocol-1536.webp 1536w"
            sizes="(max-width: 760px) calc(100vw - 32px), 64vw"
            width={1536}
            height={1024}
            alt="Атлет выполняет жим гантелей лёжа"
            fetchPriority="high"
            onError={() => setFailed(true)}
          />
        )}
      </figure>
      <div className="strength-scene__record">
        <p className="landing-kicker">Пример записи</p>
        <h2>Жим гантелей лёжа</h2>
        <dl>
          <div>
            <dt>Вес</dt>
            <dd>
              18 <small>кг</small>
            </dd>
          </div>
          <div>
            <dt>Повторы</dt>
            <dd>10</dd>
          </div>
          <div className="strength-scene__saved">
            <dt>
              <Icon name="check" size={24} />
            </dt>
            <dd>
              Подход
              <br />
              выполнен
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
