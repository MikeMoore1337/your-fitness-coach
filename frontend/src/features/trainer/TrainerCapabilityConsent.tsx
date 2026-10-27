import { useState } from 'react';

export function TrainerCapabilityConsent({
  pending = false,
  onCancel,
  onConfirm,
}: {
  pending?: boolean;
  onCancel?: () => void;
  onConfirm: () => void;
}) {
  const [acceptedTerms, setAcceptedTerms] = useState(false);

  return (
    <div className="trainer-capability top-gap">
      <ul className="trainer-capability__facts" aria-label="Возможности режима тренера">
        <li>Приглашать клиентов по персональной ссылке после их согласия.</li>
        <li>Создавать или переиспользовать программы и назначать их клиенту.</li>
        <li>Смотреть разрешённый прогресс и оставлять контекстные комментарии.</li>
      </ul>
      <ul className="trainer-capability__limits" aria-label="Ограничения режима тренера">
        <li>Режим не создаёт публичный профиль, платежи или маркетплейс.</li>
        <li>Сервис не проверяет образование, сертификацию или квалификацию тренера.</li>
        <li>Доступ к данным появляется только после подтверждения связи клиентом.</li>
      </ul>
      <label className="trainer-capability__terms">
        <input
          type="checkbox"
          checked={acceptedTerms}
          onChange={(event) => setAcceptedTerms(event.target.checked)}
        />
        <span>
          <strong>Принимаю условия использования режима тренера</strong>
          <small>
            Буду использовать доступ только для работы с подключёнными клиентами и не выдавать
            включение режима за проверку квалификации.
          </small>
        </span>
      </label>
      <div className="toolbar wrap">
        <button
          type="button"
          className="trainer-capability__activate"
          disabled={!acceptedTerms || pending}
          onClick={onConfirm}
        >
          {pending ? 'Включаем…' : 'Включить режим тренера'}
        </button>
        {onCancel && (
          <button type="button" className="secondary" onClick={onCancel} disabled={pending}>
            Не сейчас
          </button>
        )}
      </div>
    </div>
  );
}
