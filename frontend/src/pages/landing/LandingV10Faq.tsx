import { Icon } from '../../shared/ui/Icon';
import { LandingChapter } from './LandingChapter';

const FAQ_ITEMS = [
  {
    question: 'Telegram обязателен?',
    answer:
      'Нет. Тренировки, питание и прогресс доступны в браузере. Мини-приложение Telegram — быстрый дополнительный вход к тем же основным сценариям.',
  },
  {
    question: 'Что произойдёт с изменениями в демо?',
    answer:
      'Они останутся только в подготовленной демо-сессии и не перенесутся в аккаунт. После входа вы начнёте настройку чистого профиля со своими данными.',
  },
  {
    question: 'Приложение само меняет программу или питание?',
    answer:
      'Нет. Приложение показывает план, факты и объяснимые ориентиры. Изменения программы и целей остаются явными действиями пользователя или его тренера.',
  },
  {
    question: 'Можно ли управлять своими данными?',
    answer:
      'В профиле доступны экспорт данных, отвязка способов входа и удаление аккаунта. Данные подготовленных демо-сценариев отделены от реальных аккаунтов.',
  },
] as const;

export function LandingV10Faq() {
  return (
    <LandingChapter
      id="faq"
      className="landing-assurance landing-v10-faq"
      aria-labelledby="landing-v10-faq-title"
    >
      <header>
        <p className="landing-kicker">ЧЕСТНЫЕ ОГРАНИЧЕНИЯ</p>
        <h2 id="landing-v10-faq-title">Перед тем как начать.</h2>
      </header>
      <div className="landing-faq-list">
        {FAQ_ITEMS.map((item) => (
          <details key={item.question}>
            <summary>
              {item.question}
              <Icon name="plus" size={20} />
            </summary>
            <p>{item.answer}</p>
          </details>
        ))}
      </div>
    </LandingChapter>
  );
}
