import { useState } from 'react';
import { Icon } from '../../shared/ui/Icon';
import { glassProps } from '../../shared/ui/Glass';
import { LandingChapter } from './LandingChapter';
import { SectionTitle } from './LandingV10Scenes';

// Restore the six synthetic chapters from the owner-reviewed #852 prototype.
export function LandingV10CoachJourney() {
  const [connected, setConnected] = useState(false);
  const [assigned, setAssigned] = useState(false);
  const [version, setVersion] = useState(1);
  const [client, setClient] = useState(false);
  const [review, setReview] = useState(false);
  const [checked, setChecked] = useState(false);
  const [selected, setSelected] = useState(['Алексей', 'Марина']);
  const [preview, setPreview] = useState(false);
  const [applied, setApplied] = useState(false);
  const [draft, setDraft] = useState(false);
  const [sent, setSent] = useState(false);
  const example = (
    <p className="ref-caption">
      Интерактивный пример · синтетические данные. Действия меняют только эту сцену.
    </p>
  );
  return (
    <>
      <LandingChapter id="coach-connect" tabIndex={-1} className="ref-section ref-coach-connect">
        <SectionTitle
          index="01 / ПОДКЛЮЧЕНИЕ КЛИЕНТА"
          title={
            <>
              Знакомство.
              <br />
              <em>С продолжением.</em>
            </>
          }
        >
          <p>
            Приглашение начинает связь. Клиент принимает её сам. Версия плана подключения помогает
            сохранить последовательность дальнейших шагов.
          </p>
          {example}
        </SectionTitle>
        <div className="ref-product">
          <div className="ref-product-head">
            <span>Подключение / шаблон «Первый месяц»</span>
            <Icon name="nav-coach" />
          </div>
          <h3>Начать вместе</h3>
          <ol className="ref-template-path">
            {['Приглашение', 'Назначение программы', 'Первая проверка'].map((x, i) => (
              <li key={x}>
                <span>0{i + 1}</span>
                <div>
                  <h3>{x}</h3>
                  <p>
                    {i === 0
                      ? connected
                        ? 'Приглашение принято в примере'
                        : 'Связь ждёт согласия клиента'
                      : 'Отдельное действие тренера'}
                  </p>
                </div>
              </li>
            ))}
          </ol>
          <button
            className="landing-button"
            disabled={connected}
            onClick={() => setConnected(true)}
          >
            {connected ? 'Связь подтверждена в примере' : 'Показать принятое приглашение'}
          </button>
          <p className="ref-caption">
            Шаблон не назначает программу автоматически. Здесь показаны независимые этапы рабочего
            процесса.
          </p>
        </div>
      </LandingChapter>
      <LandingChapter id="coach-program" className="ref-section ref-coach-program">
        <SectionTitle
          index="02 / ПРОГРАММА И ВЕРСИЯ"
          title={
            <>
              Ваш план.
              <br />
              Для конкретного человека.
            </>
          }
        >
          <p>
            Выберите программу для подключённого клиента. Версия и история назначения дают опору для
            последующих изменений.
          </p>
          {example}
        </SectionTitle>
        <div className="ref-product">
          <div className="ref-product-head">
            <span>Программа / Алексей</span>
            <Icon name="nav-plan" />
          </div>
          <nav className="ref-tabs" aria-label="Версия программы">
            {[1, 2].map((value) => (
              <button
                key={value}
                {...glassProps('clear', true)}
                aria-pressed={version === value}
                disabled={assigned}
                onClick={() => setVersion(value)}
              >
                Версия {value}
              </button>
            ))}
          </nav>
          <small>ШАБЛОН · ВЕРСИЯ {version}</small>
          <h3>Силовая база</h3>
          <ul className="ref-list">
            <li>
              Тренировка А <b>Понедельник</b>
            </li>
            <li>
              Тренировка Б <b>Среда</b>
            </li>
            <li>
              Тренировка А <b>Пятница</b>
            </li>
          </ul>
          <p>
            Синтетический подключённый клиент. План — пример интерфейса, не тренировочная
            рекомендация.
          </p>
          <button className="landing-button" disabled={assigned} onClick={() => setAssigned(true)}>
            {assigned ? 'Назначение показано' : 'Показать назначение программы'}
          </button>
          <p role="status">
            {assigned
              ? `Версия ${version} → программа Алексея. История назначения сохранена только в сцене.`
              : 'Посмотрите, как версия становится назначением клиента.'}
          </p>
        </div>
      </LandingChapter>
      <LandingChapter id="coach-facts" className="ref-section ref-coach-facts">
        <div className="ref-photo-copy">
          <img
            src="/assets/marketing/trainer-photo.webp"
            width="1024"
            height="1024"
            alt="Тренер разбирает план со спортсменкой"
            loading="lazy"
          />
          <div>
            <p className="landing-kicker">03 / ВНИМАНИЕ → КОНТЕКСТ</p>
            <h2>
              За цифрами —<br />
              <em>ваш клиент.</em>
            </h2>
            <p>
              Coach Today показывает поводы вернуться к человеку. Обзор клиента связывает программу
              и выполненные тренировки.
            </p>
          </div>
        </div>
        <div className="ref-coach-facts-body">
          <div className="ref-product">
            <div className="ref-product-head">
              <span>{client ? 'Client 360 / обзор клиента' : 'Обзор клиента / входящие'}</span>
              <Icon name="nav-coach" />
            </div>
            <h3>{client ? 'Алексей · факты недели' : 'Есть повод вернуться'}</h3>
            {client ? (
              <>
                <dl className="ref-facts">
                  <div>
                    <dt>Выполнено</dt>
                    <dd>2 тренировки</dd>
                  </div>
                  <div>
                    <dt>Запланировано</dt>
                    <dd>3 тренировки</dd>
                  </div>
                  <div>
                    <dt>Программа</dt>
                    <dd>Силовая база · версия 1</dd>
                  </div>
                  <div>
                    <dt>Проверка недели</dt>
                    <dd>Новый ответ</dd>
                  </div>
                </dl>
                <button className="ref-text-control" onClick={() => setClient(false)}>
                  Вернуться во входящие
                </button>
              </>
            ) : (
              <>
                <div className="ref-client">
                  <span className="ref-avatar">А</span>
                  <div>
                    <b>Алексей</b>
                    <p>Ответил на проверку недели</p>
                  </div>
                </div>
                <button className="landing-button" onClick={() => setClient(true)}>
                  Открыть обзор клиента
                </button>
              </>
            )}
            {example}
            <p className="ref-caption">
              Только доступный тренеру контекст связанного клиента. Приватные заметки не
              показываются.
            </p>
          </div>
        </div>
      </LandingChapter>
      <LandingChapter id="coach-review" className="ref-section ref-coach-review">
        <SectionTitle
          index="04 / ПРОВЕРКА СОСТОЯНИЯ"
          title={
            <>
              Сначала факты.
              <br />
              <em>Потом вывод.</em>
            </>
          }
        >
          <p>
            Проверка недели и рабочее место проверки помогают сопоставить ответ клиента с
            тренировками. Отсутствие данных остаётся видимым.
          </p>
          {example}
        </SectionTitle>
        <div className="ref-product">
          <div className="ref-product-head">
            <span>Рабочее место проверки / Алексей</span>
            <Icon name="nav-progress" />
          </div>
          <nav className="ref-tabs" aria-label="Пример проверки клиента">
            <button
              {...glassProps('clear', true)}
              aria-pressed={!review}
              onClick={() => setReview(false)}
            >
              Факты
            </button>
            <button
              {...glassProps('clear', true)}
              aria-pressed={review}
              onClick={() => setReview(true)}
            >
              Изменения
            </button>
          </nav>
          {review ? (
            <>
              <h3>Без поспешного вывода</h3>
              <p>
                Сопоставимых изменений результатов пока нет. Для вывода о динамике нужны
                дополнительные записи.
              </p>
            </>
          ) : (
            <>
              <h3>Неделя в контексте</h3>
              <dl className="ref-facts">
                <div>
                  <dt>Выполнение</dt>
                  <dd>2 из 3 тренировок</dd>
                </div>
                <div>
                  <dt>Ответ о восстановлении</dt>
                  <dd>3 из 5</dd>
                </div>
              </dl>
              <p className="ref-caption">Ответ клиента — самооценка, не медицинское заключение.</p>
            </>
          )}
          <button className="landing-button" disabled={checked} onClick={() => setChecked(true)}>
            {checked ? 'Итог проверен в примере' : 'Отметить итог проверенным'}
          </button>
          <p role="status">
            {checked
              ? 'Программа не изменилась. Следующее решение принимает тренер.'
              : 'Проверка не меняет программу автоматически.'}
          </p>
        </div>
      </LandingChapter>
      <LandingChapter id="coach-decision" className="ref-section ref-coach-decision">
        <SectionTitle
          index="05 / РЕШЕНИЕ И БЕЗОПАСНОЕ ИЗМЕНЕНИЕ"
          title={
            <>
              Общая версия.
              <br />
              Личное применение.
            </>
          }
        >
          <p>
            Проверьте, что изменится у каждого выбранного клиента. Применение шаблона касается
            будущих запланированных тренировок; выполненная история остаётся фактом.
          </p>
          {example}
        </SectionTitle>
        <div className="ref-product">
          <div className="ref-product-head">
            <span>Силовая база / версия 1 → 2</span>
            <Icon name="exercise" />
          </div>
          <h3>
            {applied
              ? 'Изменения подтверждены'
              : preview
                ? 'Просмотр по клиентам'
                : 'Выберите получателей'}
          </h3>
          <fieldset className="ref-coach-targets" disabled={applied}>
            <legend>Подключённые клиенты · пример</legend>
            {['Алексей', 'Марина'].map((name) => (
              <label key={name}>
                <input
                  type="checkbox"
                  checked={selected.includes(name)}
                  onChange={() => {
                    setSelected(
                      selected.includes(name)
                        ? selected.filter((x) => x !== name)
                        : [...selected, name],
                    );
                    setPreview(false);
                  }}
                />
                {name}
              </label>
            ))}
          </fieldset>
          {preview && (
            <ul className="ref-list">
              {selected.map((name) => (
                <li key={name}>
                  <span>
                    {name}
                    <small>Будущая тренировка · тяга гантели</small>
                  </span>
                  <b>3 → 2 подхода</b>
                </li>
              ))}
            </ul>
          )}
          <p className="ref-caption">
            Иллюстрация изменения, не рекомендация. В продукте доступность и конфликты проверяются
            отдельно для каждого клиента.
          </p>
          <button
            className="landing-button"
            disabled={!selected.length || applied}
            onClick={() => (preview ? setApplied(true) : setPreview(true))}
          >
            {applied
              ? 'Подтверждено в примере'
              : preview
                ? `Подтвердить для ${selected.length} ${selected.length === 1 ? 'клиента' : 'клиентов'}`
                : 'Посмотреть изменения по клиентам'}
          </button>
          <p role="status">
            {applied
              ? `Показано применение для ${selected.join(', ')}. Реальные программы не изменены.`
              : 'Без предварительного просмотра применение недоступно.'}
          </p>
        </div>
      </LandingChapter>
      <LandingChapter id="coach-followup" className="ref-section ref-coach-followup">
        <SectionTitle
          index="06 / СОПРОВОЖДЕНИЕ И СЛЕДУЮЩИЙ ШАГ"
          title={
            <>
              Внимание
              <br />
              <em>продолжается.</em>
            </>
          }
        >
          <p>
            Шаблон помогает начать сообщение. Вы редактируете черновик и отдельно подтверждаете
            отправку. Следующая проверка остаётся вашим решением.
          </p>
          {example}
        </SectionTitle>
        <div className="ref-product">
          <div className="ref-product-head">
            <span>Сообщение / Алексей</span>
            <Icon name="nav-today" />
          </div>
          <h3>{sent ? 'Подтверждено в макете' : 'От шаблона к разговору'}</h3>
          {draft ? (
            <>
              <label className="ref-draft-label">
                Черновик сопровождения
                <textarea
                  disabled={sent}
                  defaultValue="Алексей, посмотрел итог недели. Давайте обсудим следующую тренировку."
                />
              </label>
              <p className="ref-caption">
                До подтверждения уведомление не создаётся. В этой сцене отправки нет вообще.
              </p>
              <button className="landing-button" disabled={sent} onClick={() => setSent(true)}>
                {sent ? 'Подтверждено' : 'Подтвердить отправку в примере'}
              </button>
            </>
          ) : (
            <>
              <p>Шаблон «После проверки недели» · версия 1.</p>
              <button className="landing-button" onClick={() => setDraft(true)}>
                Создать черновик в примере
              </button>
            </>
          )}
          <p role="status">
            {sent
              ? 'Показан результат явного подтверждения. Никому ничего не отправлено.'
              : 'Сообщение остаётся под контролем тренера.'}
          </p>
        </div>
      </LandingChapter>
    </>
  );
}
