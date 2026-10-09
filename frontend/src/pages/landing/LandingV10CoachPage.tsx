import { LandingV10Shell } from './LandingV10Shell';
import { LandingV10Hero, LandingV10Cycle } from './LandingV10Hero';
import { ArchiveCoachWork } from './LandingV10Scenes';
import { LandingV10SharedSections } from './LandingV10SharedSections';
import { LandingChapter } from './LandingChapter';
import { useLandingHeroMotion } from './useLandingHeroMotion';
import './landing.css';
export default function LandingV10CoachPage() {
  useLandingHeroMotion();
  return (
    <LandingV10Shell audience="coach">
      <LandingV10Hero audience="coach" />
      <LandingV10Cycle audience="coach" />
      <ArchiveCoachWork />
      <LandingChapter className="ref-section ref-onboarding" id="coach-process">
        <div className="ref-copy">
          <p className="landing-kicker">Coach OS / ВАШ МЕТОД — ПОСЛЕДОВАТЕЛЬНО</p>
          <h2>
            Повторяемый процесс.
            <br />
            Личное сопровождение.
          </h2>
          <p>
            Шаблоны подключения, программ и проверок помогают выстроить рабочий путь. Назначения и
            сообщения остаются под контролем тренера.
          </p>
        </div>
        <ol className="ref-template-path">
          {[
            ['Приглашение', 'Клиент явно принимает связь с тренером.'],
            ['Программа и проверка', 'Шаблон получает назначение и версию.'],
            ['Факты и обзор', 'Результаты доступны в контексте клиента.'],
            ['Следующий шаг', 'Изменение или черновик ждёт подтверждения.'],
          ].map(([title, text], i) => (
            <li key={title}>
              <span>0{i + 1}</span>
              <div>
                <h3>{title}</h3>
                <p>{text}</p>
              </div>
            </li>
          ))}
        </ol>
      </LandingChapter>
      <LandingV10SharedSections audience="coach" includeDifference={false} />
    </LandingV10Shell>
  );
}
