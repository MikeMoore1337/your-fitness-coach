const params = new URLSearchParams(location.search);
const variant = 'b';
const theme = params.get('theme') === 'light' ? 'light' : 'dark';
const screen = params.get('screen') || 'progress';
const sparse = params.get('data') === 'sparse';
const safe = params.get('safe') === '34' ? 34 : 0;
const sections = [['overview','Обзор'],['body','Тело'],['training','Тренировки'],['nutrition','Питание'],['cardio','Кардио'],['wellbeing','Самочувствие'],['history','История']];
let section = sections.some(([id]) => id === params.get('section')) ? params.get('section') : screen === 'body' ? 'body' : screen === 'history' ? 'history' : 'overview';
const svg = (body) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
// Existing YFC iconGlyphs only, including the current Phosphor dumbbell.
const icons = {
  today: svg('<path d="M8 2v3M16 2v3"/><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M8 13h.01M12 13h.01M16 13h.01M8 17h.01M12 17h.01M16 17h.01"/>'),
  plan: svg('<g transform="scale(0.09375)" fill="currentColor" stroke="none"><path d="M248,120h-8V88a16,16,0,0,0-16-16H208V64a16,16,0,0,0-16-16H168a16,16,0,0,0-16,16v56H104V64A16,16,0,0,0,88,48H64A16,16,0,0,0,48,64v8H32A16,16,0,0,0,16,88v32H8a8,8,0,0,0,0,16h8v32a16,16,0,0,0,16,16H48v8a16,16,0,0,0,16,16H88a16,16,0,0,0,16-16V136h48v56a16,16,0,0,0,16,16h24a16,16,0,0,0,16-16v-8h16a16,16,0,0,0,16-16V136h8a8,8,0,0,0,0-16ZM32,168V88H48v80Zm56,24H64V64H88V192Zm104,0H168V64h24V175.82c0,.06,0,.12,0,.18s0,.12,0,.18V192Zm32-24H208V88h16Z"/></g>'),
  nutrition: svg('<path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2M7 2v20M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/>'),
  progress: svg('<path d="M12 16v5M16 14.639V21M20 10.656V21m2-18-8.646 8.646a.5.5 0 0 1-.708 0L9.354 8.354a.5.5 0 0 0-.707 0L2 15M4 18.463V21M8 14.656V21"/>'),
  plus: svg('<path d="M12 5v14M5 12h14"/>'),
  close: svg('<path d="M18 6 6 18m0-12 12 12"/>'),
  water: svg('<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"/>'),
  cardio: svg('<path d="M2 9.5a5.5 5.5 0 0 1 9.591-3.676.56.56 0 0 0 .818 0A5.49 5.49 0 0 1 22 9.5c0 2.29-1.5 4-3 5.5l-5.492 5.313a2 2 0 0 1-3 .019L5 15c-1.5-1.5-3-3.2-3-5.5"/><path d="M3.22 13H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27"/>'),
  measurement: svg('<path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z"/><path d="m14.5 12.5 2-2"/><path d="m11.5 9.5 2-2"/><path d="m8.5 6.5 2-2"/><path d="m17.5 15.5 2-2"/>'),
  wellbeing: svg('<path d="M13 5h8M13 12h8M13 19h8m-18-2 2 2 4-4M3 7l2 2 4-4"/>'),
};
const localUrl = (values) => { const url = new URL(location.href); Object.entries(values).forEach(([key,value]) => url.searchParams.set(key,value)); url.searchParams.set('section', values.section || section); return url.href; };
const brand = (brandTheme=theme) => `<div class="brand-small" role="img" aria-label="Your Fitness Coach"><img src="assets/brand/yfc-logo-${brandTheme}.svg" alt=""><span>Your Fitness<br>Coach</span></div>`;
const metric = (label, value, unit = '', note = '') => `<div class="metric"><dt>${label}</dt><dd>${value}${unit ? ` <small>${unit}</small>` : ''}</dd>${note ? `<p>${note}</p>` : ''}</div>`;
const row = (title, detail, value = '') => `<div class="data-row"><div><strong>${title}</strong><small>${detail}</small></div>${value ? `<b>${value}</b>` : ''}</div>`;
const reportLink = () => `<a class="more-link" data-last-action href="${localUrl({screen:'report'})}"><span>Отчёт за период</span><span aria-hidden="true">↗</span></a>`;
const chart = () => `<div class="trend"><svg viewBox="0 0 300 110" role="img" aria-label="${sparse ? 'Один замер 80,9 килограмма, динамика не вычисляется' : 'Три замера массы: 82,4, 81,6 и 80,9 килограмма'}"><path d="M8 15H292M8 55H292M8 95H292" stroke="currentColor" stroke-width=".5" opacity=".22" fill="none"/>${sparse ? '<circle cx="150" cy="55" r="4" fill="currentColor"/>' : '<path d="M12 18L151 58L288 93" fill="none" stroke="currentColor" stroke-width="2"/><g fill="currentColor"><circle cx="12" cy="18" r="3"/><circle cx="151" cy="58" r="3"/><circle cx="288" cy="93" r="3"/></g>'}</svg><div class="chart-axis"><span>${sparse ? '' : '12 сент. · 82,4'}</span><span>${sparse ? '9 окт. · 80,9 кг' : '25 сент. · 81,6'}</span><span>${sparse ? '' : '9 окт. · 80,9'}</span></div></div>`;
const lowData = () => sparse ? '<p class="low-data">Один замер не образует тренд. Отсутствующие записи не считаются нулями.</p>' : '';
const rail = () => `<div class="section-rail"><button class="rail-edge rail-prev" type="button" aria-label="Предыдущие разделы прогресса" disabled>${svg('<path d="m14 6-6 6 6 6"/>')}</button><div class="rail-scroll" role="tablist" aria-label="Разделы прогресса" aria-describedby="rail-help">${sections.map(([id,label]) => `<button type="button" role="tab" id="tab-${id}" data-section="${id}" aria-controls="section-content" aria-selected="${id===section}" tabindex="${id===section ? 0 : -1}">${label}</button>`).join('')}</div><button class="rail-edge rail-next" type="button" aria-label="Следующие разделы прогресса">${svg('<path d="m10 6 6 6-6 6"/>')}</button></div><p id="rail-help" class="sr-only">Семь разделов. Прокрутите строку или используйте кнопки со стрелками. На клавиатуре: влево, вправо, Home и End.</p>`;
const dock = () => `<div class="dock dock-${variant}"><nav class="main-nav" aria-label="Основная навигация">${[['today','Сегодня','completed'],['plan','План','plan'],['nutrition','Питание','nutrition'],['progress','Прогресс','progress']].map(([id,label,target]) => `<a class="nav-item" ${id === 'progress' ? 'aria-current="page"' : ''} href="${id === 'progress' ? localUrl({screen:'progress'}) : `proposal-v1.html?capture=1&screen=${target}&theme=${theme}`}">${icons[id]}<span>${label}</span></a>`).join('')}</nav><div class="action-zone"><button class="add-trigger" type="button" aria-label="Быстро добавить" aria-haspopup="dialog" aria-expanded="false" aria-controls="quick-menu">${icons.plus}</button></div></div>`;
const actions = [
  ['nutrition','Еда','Быстрый ввод в дневник питания','nutrition','Добавить еду'],
  ['water','Вода','Сразу к трекеру жидкости','nutrition','Добавить воду'],
  ['cardio','Кардио','Записать ручную активность','cardio','Добавить кардио'],
  ['measurement','Замер','Вес или окружность тела','body','Добавить замер'],
  ['wellbeing','Самочувствие','Ежедневная отметка','wellbeing','Отметить самочувствие'],
];
const action = ([id,label,detail,target,full], compact = false) => `<a class="quick-action" aria-label="${full}" href="${id==='measurement' ? localUrl({screen:'body',section:'body',entry:'measurement'}) : `proposal-v1.html?capture=1&screen=${target}&theme=${theme}${id==='water'?'&hydration=quick':''}`}">${icons[id]}<div><strong>${variant==='a' ? full : label}</strong>${!compact && variant==='a' ? `<small>${detail}</small>` : ''}</div>${variant==='a' ? '<span class="chevron" aria-hidden="true">›</span>' : ''}</a>`;
const quickMenu = () => `<dialog class="quick-panel" id="quick-menu" aria-labelledby="quick-title"><header class="quick-header"><h2 id="quick-title">Что добавить?</h2><button type="button" class="close-menu" aria-label="Закрыть быстрое добавление" autofocus>${icons.close}</button></header><nav aria-label="Быстрые действия">${variant==='a' ? actions.map(item=>action(item)).join('') : `<div class="quick-primary">${actions.slice(0,2).map(item=>action(item,true)).join('')}</div><div class="quick-secondary">${actions.slice(2).map(item=>action(item,true)).join('')}</div>`}</nav></dialog>`;
function overview() {
  const values = variant==='a'
    ? `<dl class="metrics-grid">${metric('Тренировки',sparse?'Нет записей':'9 <small>/ 12</small>','',sparse?'За выбранный период':'Завершено из запланированных')}${metric('Масса тела','80,9','кг',sparse?'1 замер · без динамики':'−1,5 кг · 3 замера')}${metric('Питание',sparse?'2 <small>/ 30</small>':'24 <small>/ 30</small>','', 'Дней с записями')}${metric('Кардио',sparse?'Нет записей':'178',sparse?'':'мин','Записанная активность')}</dl>`
    : `<div class="lead-fact"><span class="eyebrow">Завершённые тренировки</span><div class="value">${sparse ? '—' : '9 <small>/ 12</small>'}</div><p class="subtle">${sparse ? 'Нет записей за период' : 'Из запланированных за 30 дней'}</p></div><dl class="compact-facts">${metric('Масса тела','80,9','кг',sparse?'1 замер':'−1,5 кг · 3 замера')}${metric('Дневник питания',sparse?'2 / 30':'24 / 30','','Дней с записями')}${metric('Кардио',sparse?'Нет записей':'178',sparse?'':'мин')}${metric('Окружность талии',sparse?'Нет записи':'84,2',sparse?'':'см')}</dl>`;
  return `<div class="section-heading"><h2>${variant==='a'?'За 30 дней':'Обзор'}</h2><span class="subtle">10 сент. — 9 окт.</span></div>${values}${lowData()}<section class="list-section"><h2>Последние записи</h2>${row('Замер тела',`9 октября · ${sparse?'1 замер':'3 измерения'}`,'80,9 кг')}${sparse ? '' : row('Силовая А','9 октября · завершена','6 упражнений')}</section><a class="more-link" href="${localUrl({screen:'progress',section:'wellbeing'})}"><span>Недельный обзор</span><span aria-hidden="true">›</span></a>${reportLink()}`;
}
function bodyContent() {
  return `<div class="section-heading"><h2>Тело</h2><button class="text-action" type="button" data-open-measurement>Добавить замер</button></div><p class="eyebrow">Масса тела · 9 октября</p><div class="body-value">80,9 <small>кг</small></div><div class="body-meta"><span>${sparse?'1 замер · без динамики':'−1,5 кг за период'}</span><span>${sparse?'':'3 замера'}</span></div>${chart()}${lowData()}<section class="list-section"><h2>Измерения</h2>${row('Талия',sparse?'Нет записи':'9 октября',sparse?'':'84,2 см')}${sparse?'':row('Предыдущая масса','25 сентября','81,6 кг')}</section><details class="input-disclosure" id="measurement-form"><summary>Новый замер</summary><div><label>Дата<input type="date" value="2026-10-09"></label><label>Масса, кг<input type="text" inputmode="decimal" enterkeyhint="next" value="80,9"></label><label>Талия, см<input type="text" inputmode="decimal" enterkeyhint="done" placeholder="Необязательно"></label></div></details>${reportLink()}`;
}
function historyContent() {
  return `<div class="section-heading"><h2>История</h2><span class="subtle">По дате</span></div><p class="subtle">Исходные записи за выбранный период.</p><section class="list-section"><h2>9 октября</h2>${row('Замер тела',sparse?'Масса тела':'Масса и окружность талии','80,9 кг')}${sparse?'':row('Силовая А','Завершена · подходы сохранены','6 упражнений')}${row('Дневник питания','Записано пользователем',sparse?'2 записи':'2 184 ккал')}</section>${sparse?'':`<section class="list-section"><h2>8 октября</h2>${row('Кардио','Ходьба · ручная запись','28 мин')}${row('Самочувствие','Ежедневная отметка','Есть запись')}</section>`}${reportLink()}`;
}
function focusedContent(id) {
  if(id==='overview') return overview(); if(id==='body') return bodyContent(); if(id==='history') return historyContent();
  const label = sections.find(([key])=>key===id)[1];
  const facts = {
    training:[row('Завершённые тренировки','Из 12 запланированных',sparse?'Нет записей':'9'),row('Рабочие подходы','Фактически записанные',sparse?'Нет записей':'84')],
    nutrition:[row('Дней с записями','Из 30 дней периода',sparse?'2':'24'),row('Последний записанный день','9 октября','2 184 ккал')],
    cardio:[row('Общее время','Только записанная активность',sparse?'Нет записей':'178 мин'),row('Последняя сессия','8 октября · ходьба',sparse?'Нет записи':'28 мин')],
    wellbeing:[row('Последняя отметка','9 октября','Есть запись'),row('Недельный обзор','Ещё не заполнен')],
  };
  return `<div class="section-heading"><h2>${label}</h2></div><section class="list-section">${facts[id].join('')}</section><p class="low-data">${id==='nutrition'?'Незаполненные дни не считаются нулями.':id==='wellbeing'?'Отметки пользователя не являются медицинской оценкой.':'Показаны только фактические записи за период.'}</p><details class="input-disclosure"><summary>Источники и подробности</summary><div><p class="subtle">История, исходные записи и ограничения показателя остаются доступны.</p></div></details>${reportLink()}`;
}
function progressPage() {
  const heading=variant==='a'?`<h1 class="page-heading">Прогресс</h1><div class="page-context"><p class="subtle">10 сентября — 9 октября</p><button class="period-button" type="button" data-period>30 дней</button></div>`:`<div class="page-context"><h1 class="context-title">Прогресс</h1><button class="period-button" type="button" data-period>30 дней</button></div>`;
  return `<div class="app-shell"><header class="app-header">${brand()}<a href="proposal-v1.html?capture=1&screen=profile&theme=${theme}" class="profile-button" aria-label="Профиль">АП</a></header>${heading}${rail()}<main class="content" id="section-content" role="tabpanel" aria-labelledby="tab-${section}">${focusedContent(section)}</main></div>${dock()}${quickMenu()}`;
}
const reportFacts = () => `<dl class="metrics-grid">${metric('Тренировки',sparse?'Нет записей':'9 / 12')}${metric('Масса тела','80,9','кг',sparse?'1 замер':'−1,5 кг')}${metric('Питание',sparse?'2 / 30':'24 / 30','','Дней с записями')}${metric('Кардио',sparse?'Нет записей':'178',sparse?'':'мин')}</dl>`;
const reportSections = () => `<section class="document-section"><h2>Измерения</h2>${chart()}<dl class="report-records"><dt class="record-title">Масса тела</dt><dt>${sparse?'Замер':'12 сентября 2026'}</dt><dd>${sparse?'80,9':'82,4'} кг</dd>${sparse?'':'<dt>9 октября 2026</dt><dd>80,9 кг</dd><dt>Изменение</dt><dd>−1,5 кг</dd>'}<dt class="record-title">Талия</dt><dt>${sparse?'Записи':'12 сентября 2026'}</dt><dd>${sparse?'Нет данных':'86,1 см'}</dd>${sparse?'':'<dt>9 октября 2026</dt><dd>84,2 см</dd><dt>Изменение</dt><dd>−1,9 см</dd>'}</dl></section><section class="document-section"><h2>Тренировки</h2><h3>Жим штанги лёжа с контролируемой паузой</h3><dl class="report-records"><dt>Сессии / подходы</dt><dd>${sparse?'Нет записей':'4 / 16'}</dd><dt>Максимальный вес</dt><dd>${sparse?'Нет записи':'92,5 кг'}</dd></dl><h3>Питание и самочувствие</h3><p>Только подтверждённые дни и фактические отметки. Незаполненные дни не считаются нулями. Приватные дневные заметки в отчёт не включены.</p><h3>Источники и полнота</h3><p>${sparse?'Один замер; данных для динамики недостаточно.':'9 завершённых тренировок, 24 дня с записями питания, 3 замера массы.'} Оценка усталости, диагностика и причинные выводы не добавляются.</p></section>`;
const reportTools = () => `<div class="report-tools"><details class="input-disclosure"><summary>Период и состав<span>30 дней</span></summary><div><label>Период отчёта<select id="report-period">${['7 дней','30 дней','90 дней','Этот месяц','Прошлый месяц','Свой период'].map(label=>`<option ${label==='30 дней'?'selected':''}>${label}</option>`).join('')}</select></label><div id="custom-dates" hidden><label>Начало<input type="date" value="2026-09-10"></label><label>Конец<input type="date" value="2026-10-09"></label></div><p class="subtle">До четырёх упражнений. Передача тренеру и публичный предпросмотр сохраняют существующие ограничения приватности.</p><a class="text-action" href="proposal-v1.html?capture=1&screen=report&theme=${theme}">Состав и передача</a></div></details></div>`;
function reportPage() {
  const masthead=variant==='b'?`<div class="report-masthead">${brand()}<span class="subtle">Личный отчёт</span></div>`:'';
  const summary=variant==='a'?`<section class="report-summary"><h2>Краткая сводка</h2>${reportFacts()}</section>`:`<section class="report-summary"><div class="lead-fact"><span class="eyebrow">Завершённые тренировки</span><div class="value">${sparse?'—':'9 <small>/ 12</small>'}</div><p class="subtle">${sparse?'Нет записей за период':'За выбранные 30 дней'}</p></div><dl class="compact-facts">${metric('Масса тела','80,9','кг',sparse?'1 замер':'−1,5 кг · 3 замера')}${metric('Питание',sparse?'2 / 30':'24 / 30','','Дней с записями')}${metric('Кардио',sparse?'Нет записей':'178',sparse?'':'мин')}${metric('Талия',sparse?'Нет записи':'84,2',sparse?'':'см')}</dl></section>`;
  return `<main class="app-shell report-shell content"><a class="report-back" href="${localUrl({screen:'progress'})}">‹ Прогресс</a>${masthead}<div class="report-heading"><div><h1>Отчёт</h1><p class="report-owner">Анна Петрова</p></div>${variant==='a'?brand():''}</div><p class="report-period">10 сентября — 9 октября 2026<br><span class="subtle">Часовой пояс: Europe/Moscow</span></p>${reportTools()}${summary}${lowData()}${reportSections()}<div class="report-downloads" data-last-action><a href="navigation-final/report.pdf" target="_blank" rel="noopener">Скачать PDF</a><a href="${localUrl({screen:'print-report'})}">Печать</a></div></main>${dock()}${quickMenu()}`;
}
const paperTable = (title, rows) => `<table class="paper-table"><caption>${title}</caption><tbody>${rows.map(([label,value])=>`<tr><th scope="row">${label}</th><td>${value}</td></tr>`).join('')}</tbody></table>`;
function printPage() {
  const measurements = paperTable('Масса тела', sparse ? [['9 октября 2026','80,9 кг']] : [['12 сентября 2026','82,4 кг'],['9 октября 2026','80,9 кг'],['Изменение','−1,5 кг']]) + paperTable('Окружность талии', sparse ? [['Записи','Нет данных']] : [['12 сентября 2026','86,1 см'],['9 октября 2026','84,2 см'],['Изменение','−1,9 см']]);
  const longFixture = params.get('print-data') === 'long' ? `<section class="document-section"><h2>Проверка длинного документа</h2><p>Техническая синтетическая выборка для проверки переносов: повторяются уже показанные факты, новые расчёты не выполняются.</p><table class="paper-table stress-table"><thead><tr><th scope="col">Упражнение / исходная запись</th><th scope="col">Значение</th></tr></thead><tbody>${Array.from({length:28},(_,i)=>`<tr><td>Контрольная строка ${i+1}. Жим штанги лёжа с контролируемой паузой и длинным уточнением названия упражнения</td><td>92,5 кг</td></tr>`).join('')}</tbody></table></section>` : '';
  return `<main class="print-shell"><header class="print-heading">${brand('light')}<div><h1>Отчёт за период</h1><p class="print-owner">Анна Петрова</p><p class="print-period">10 сентября — 9 октября 2026<br>Часовой пояс: Europe/Moscow</p></div></header>${reportFacts()}${lowData()}<div class="print-columns"><section class="document-section"><h2>Измерения</h2>${chart()}${measurements}</section><section class="document-section"><h2>Тренировки</h2><h3>Жим штанги лёжа с контролируемой паузой</h3>${paperTable('Исходные показатели', [['Сессии / подходы',sparse?'Нет записей':'4 / 16'],['Максимальный вес',sparse?'Нет записи':'92,5 кг']])}</section><section class="document-section"><h2>Питание и самочувствие</h2><p>Только подтверждённые дни и фактические отметки. Незаполненные дни не считаются нулями. Приватные дневные заметки в отчёт не включены.</p></section><section class="document-section"><h2>Источники и полнота</h2><p>${sparse?'Один замер; данных для динамики недостаточно.':'9 завершённых тренировок, 24 дня с записями питания, 3 замера массы.'} Оценка усталости, диагностика и причинные выводы не добавляются.</p></section>${longFixture}</div><footer class="paper-note">Синтетический пример для согласования компоновки. Только записанные факты; пропуски не заменяются предположениями. Your Fitness Coach · 9 октября 2026.</footer></main>`;
}
if(params.has('capture')) {
  document.getElementById('review').hidden=true;document.body.className=`capture ${theme} variant-${variant}`;
  document.body.style.setProperty('--safe-bottom',`${safe}px`);document.body.style.setProperty('--safe-top',safe?'24px':'0px');
  const app=document.getElementById('app');app.hidden=false;app.innerHTML=screen==='print-report'?printPage():screen==='report'?reportPage():progressPage();
  app.querySelector('.print-shell .trend svg')?.setAttribute('preserveAspectRatio','none');
  const railElement=app.querySelector('.rail-scroll');const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const tabs=railElement ? [...railElement.querySelectorAll('[data-section]')] : [];
  const prev=app.querySelector('.rail-prev');const next=app.querySelector('.rail-next');
  function clipEdges() {
    if(!railElement)return;
    const r=railElement.getBoundingClientRect();
    const full=tabs.map(tab=>tab.getBoundingClientRect()).filter(t=>t.left>=r.left+3&&t.right<=r.right-3);
    // Clip the entire partial item, including its hit area; all seven tabs remain semantic controls.
    const left=full.length?Math.max(0,full[0].left-r.left-3):0;
    const right=full.length?Math.max(0,r.right-full.at(-1).right-3):0;
    railElement.style.clipPath=`inset(0 ${right}px 0 ${left}px)`;
  }
  function updateCues() {
    if(!railElement)return;
    prev.disabled=railElement.scrollLeft<=2;
    next.disabled=railElement.scrollLeft+railElement.clientWidth>=railElement.scrollWidth-2;
    clipEdges();
  }
  function reveal(tab) {
    // Native horizontal scrolling remains available; selecting/arrowing always settles on a whole label.
    const r=railElement.getBoundingClientRect(),t=tab.getBoundingClientRect();
    if(t.left<r.left+4||t.right>r.right-4)railElement.scrollLeft+=t.left-r.left-(r.width-t.width)/2;
    updateCues();
    const after=railElement.getBoundingClientRect(),target=tab.getBoundingClientRect();
    if(target.left<after.left+4)railElement.scrollLeft+=target.left-after.left-4;
    else if(target.right>after.right-4)railElement.scrollLeft+=target.right-after.right+4;
    updateCues();
  }
  function selectSection(id,focus=false) {
    section=id;tabs.forEach(tab=>{const active=tab.dataset.section===id;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;});
    const panel=app.querySelector('#section-content');panel.innerHTML=focusedContent(id);panel.setAttribute('aria-labelledby',`tab-${id}`);
    const url=new URL(location.href);url.searchParams.set('section',id);history.replaceState({section:id},'',url);
    app.querySelector('.main-nav [aria-current="page"]').href=localUrl({screen:'progress'});
    reveal(tabs.find(tab=>tab.dataset.section===id));
    if(focus)tabs.find(tab=>tab.dataset.section===id).focus({preventScroll:true});
    app.querySelector('.app-shell').scrollTop=0;
  }
  if(railElement) {
    railElement.addEventListener('scroll',updateCues,{passive:true});
    railElement.addEventListener('click',event=>{const tab=event.target.closest('[data-section]');if(tab)selectSection(tab.dataset.section);});
    railElement.addEventListener('focusin',event=>{const tab=event.target.closest('[data-section]');if(tab)reveal(tab);});
    railElement.addEventListener('keydown',event=>{const tab=event.target.closest('[data-section]');if(!tab)return;const index=sections.findIndex(([id])=>id===tab.dataset.section);let target;if(event.key==='ArrowRight')target=(index+1)%sections.length;else if(event.key==='ArrowLeft')target=(index+sections.length-1)%sections.length;else if(event.key==='Home')target=0;else if(event.key==='End')target=sections.length-1;else return;event.preventDefault();selectSection(sections[target][0],true);});
    function moveRail(direction){const r=railElement.getBoundingClientRect();const candidate=direction>0?tabs.find(tab=>tab.getBoundingClientRect().right>r.right-4):tabs.findLast(tab=>tab.getBoundingClientRect().left<r.left+4);if(candidate)reveal(candidate);}
    prev.addEventListener('click',()=>moveRail(-1));next.addEventListener('click',()=>moveRail(1));
    document.fonts.ready.then(()=>reveal(tabs.find(tab=>tab.dataset.section===section)));
    addEventListener('resize',()=>reveal(tabs.find(tab=>tab.dataset.section===section)));
  }
  const dialog=app.querySelector('#quick-menu');const trigger=app.querySelector('.add-trigger');
  if(dialog) {
    trigger.addEventListener('click',()=>{dialog.showModal();trigger.setAttribute('aria-expanded','true');});dialog.querySelector('.close-menu').addEventListener('click',()=>dialog.close());
    dialog.addEventListener('close',()=>{trigger.setAttribute('aria-expanded','false');trigger.focus({preventScroll:true});});
    dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
    if(screen==='quick-add'){dialog.showModal();trigger.setAttribute('aria-expanded','true');}
  }
  function openMeasurement() {const form=app.querySelector('#measurement-form');if(!form)return;form.open=true;const field=form.querySelector('[inputmode="decimal"]');field.focus({preventScroll:true});field.scrollIntoView({block:'center',behavior:'instant'});}
  app.addEventListener('click',event=>{if(event.target.closest('[data-open-measurement]'))openMeasurement();if(event.target.closest('[data-period]'))location.href=localUrl({screen:'report'});});
  if(params.get('entry')==='measurement')openMeasurement();
  dialog?.addEventListener('keydown',event=>{if(event.key!=='Tab')return;const controls=[...dialog.querySelectorAll('button,a[href],input,select')];const first=controls[0],last=controls.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}});
  let maximumHeight=visualViewport?.height||innerHeight;
  function syncViewport() {
    const height=visualViewport?.height||innerHeight;maximumHeight=Math.max(maximumHeight,height);
    const editing=!!document.activeElement?.matches('input,textarea,[contenteditable="true"]');
    document.body.classList.toggle('keyboard-open',editing&&maximumHeight-height>120);
    document.body.style.setProperty('--app-height',`${height}px`);
    if(editing)requestAnimationFrame(()=>document.activeElement?.scrollIntoView({block:'nearest',behavior:'instant'}));
  }
  visualViewport?.addEventListener('resize',syncViewport);addEventListener('resize',syncViewport);app.addEventListener('focusin',syncViewport);app.addEventListener('focusout',()=>requestAnimationFrame(syncViewport));syncViewport();
  app.querySelector('#report-period')?.addEventListener('change',event=>{app.querySelector('#custom-dates').hidden=event.target.value!=='Свой период';});
} else {
  const controlIds=['screen','theme','width','safe','data'];controlIds.forEach(id=>{const value=params.get(id);if(value)document.getElementById(id).value=value;});
  const update=()=>{const values=Object.fromEntries(controlIds.map(id=>[id,document.getElementById(id).value]));const frame=document.getElementById('preview-b');frame.style.width=values.width+'px';frame.closest('.direction').style.width=values.width+'px';const url=new URL(location.href);url.search='';Object.entries({...values,capture:'1'}).forEach(([key,value])=>url.searchParams.set(key,value));frame.src=url;const current=new URL(location.href);Object.entries(values).forEach(([key,value])=>current.searchParams.set(key,value));history.replaceState(null,'',current);};
  controlIds.forEach(id=>document.getElementById(id).addEventListener('change',update));update();
}
