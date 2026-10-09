import { Icon } from '../../shared/ui/Icon';
import { LandingChapter } from './LandingChapter';

const FAQ_ITEMS = [
  {
    question: 'Telegram обязателен?',
    answer:
      'Нет. Тренировки, питание и прогресс доступны в браузере. Мини-приложение Telegram — быстрый дополнительный вход к тем же основным сценариям.',
  },
  {
    question: 'Кто меняет программу?',
    answer:
      'Изменения программы и целей остаются явными действиями пользователя или его тренера. Подготовленные демо-данные не относятся к реальным аккаунтам.',
  },
  {
    question: 'Сообщения отправляются автоматически?',
    answer:
      'Нет. Черновик сообщения остаётся под контролем тренера до отдельного подтверждения. Публичные сцены ничего не отправляют.',
  },
  {
    question: 'Кто оказывает тренерские услуги?',
    answer:
      'Тренер — независимый пользователь сервиса. YFC не является стороной договора между тренером и клиентом и не подменяет медицинскую помощь.',
  },
  {
    question: 'Что происходит с данными?',
    answer:
      'В профиле доступны экспорт данных, отвязка способов входа и удаление аккаунта. Данные подготовленных демо-сценариев отделены от реальных аккаунтов.',
  },
] as const;

export function LandingV10Faq() {
  return (
    <LandingChapter
      id="faq"
      className="ref-section ref-faq"
      aria-labelledby="landing-v10-faq-title"
    >
      <header>
        <p className="landing-kicker">ПЕРЕД ТЕМ КАК НАЧАТЬ</p>
        <h2 id="landing-v10-faq-title">Понятные правила.</h2>
      </header>
      <div className="landing-faq-list">
        {FAQ_ITEMS.map((item) => (
          <details
            key={item.question}
            id={item.question === 'Что происходит с данными?' ? 'privacy' : undefined}
          >
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
