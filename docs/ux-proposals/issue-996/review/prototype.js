const candidates = [
  { title: 'Жим гантелей лёжа', equipment: ['Гантели', 'Скамья'], reason: 'Та же схема движения', score: 'curated_pair · movement_pattern' },
  { title: 'Жим в тренажёре от груди', equipment: ['Тренажёр'], reason: 'Проверенная пара для жима', score: 'curated_pair · movement_pattern' },
  { title: 'Жим в тренажёре Смита', equipment: ['Тренажёр', 'Скамья'], reason: 'Совместимая схема движения', score: 'movement_pattern · machine_variant' },
  { title: 'Отжимания от пола', equipment: ['Без оборудования'], reason: 'Совместимость подтверждена сервисом', score: 'movement_pattern · primary_muscle' },
];

const equipmentFilters = ['Гантели', 'Скамья', 'Тренажёр', 'Без оборудования'];
const params = new URLSearchParams(window.location.search);
const initialDirection = params.get('direction') || 'quick';
const initialTheme = params.get('theme') || 'dark';
const initialState = params.get('state') || 'ready';
const directionSelect = document.querySelector('#direction-select');
const stateSelect = document.querySelector('#state-select');
const themeToggle = document.querySelector('#theme-toggle');

directionSelect.value = ['quick', 'sheet', 'compare'].includes(initialDirection) ? initialDirection : 'quick';
stateSelect.value = [...stateSelect.options].some((option) => option.value === initialState) ? initialState : 'ready';
document.body.dataset.theme = initialTheme === 'light' ? 'light' : 'dark';

function navigate() {
  const query = new URLSearchParams({ direction: directionSelect.value, state: stateSelect.value, theme: document.body.dataset.theme });
  window.history.replaceState({}, '', `${window.location.pathname}?${query}`);
  renderAll();
}

function visibleCandidates(search, activeFilters) {
  const query = search.trim().toLocaleLowerCase('ru');
  return candidates.filter((candidate) => {
    const matchesText = !query || `${candidate.title} ${candidate.equipment.join(' ')}`.toLocaleLowerCase('ru').includes(query);
    const matchesEquipment = !activeFilters.size || [...activeFilters].every((filter) => candidate.equipment.includes(filter));
    return matchesText && matchesEquipment;
  });
}

function noticeForState(state) {
  const notices = {
    error: '<div class="notice danger" role="alert"><strong>Не удалось получить варианты</strong><span>Проверьте соединение и повторите запрос. Preview не отправлялся.</span><button class="link-button" type="button" data-action="retry">Повторить</button></div>',
    offline: '<div class="notice warning" role="alert"><strong>Нет соединения</strong><span>Выбор и preview временно недоступны. Введённый поиск сохранён.</span></div>',
    conflict: '<div class="notice warning" role="alert"><strong>Тренировка изменилась</strong><span>Обновите preview перед применением. Старый preview-token не используется.</span></div>',
    pain: '<div class="notice warning" role="alert"><strong>Если есть боль или травма</strong><span>Замена не применяется автоматически. Остановитесь и выберите безопасный следующий шаг.</span></div>',
    started: '<div class="notice warning" role="alert"><strong>Замена недоступна</strong><span>У упражнения уже есть зафиксированные факты. Сохранённые подходы не меняются.</span></div>',
  };
  return notices[state] || '<div class="notice success"><strong>Только эта тренировка</strong><span>Программа и будущие тренировки не изменяются.</span></div>';
}

function candidateMarkup(candidate, direction, index) {
  const id = `${direction}-candidate-${index}`;
  return `<li class="candidate"><input id="${id}" type="radio" name="replacement-${direction}" value="${candidate.title}" ${index === 0 ? 'checked' : ''} /><label for="${id}"><span class="candidate-title">${candidate.title}</span><span class="candidate-meta">${candidate.equipment.map((item) => `<span class="tag">${item}</span>`).join('')}<span class="tag confirmed">Подтверждено сервером</span></span><span class="candidate-reason">${candidate.reason} · <code>${candidate.score}</code></span></label></li>`;
}

function listMarkup(direction, state, expanded, search, activeFilters) {
  if (state === 'loading') return '<div class="skeleton-list" aria-label="Загрузка вариантов"><span class="skeleton"></span><span class="skeleton"></span><span class="skeleton"></span></div>';
  if (['empty', 'error', 'offline', 'pain', 'started'].includes(state)) {
    if (state === 'empty') return '<div class="empty-state"><strong>Подходящих вариантов нет</strong><span>Сервис не подтвердил замену для выбранного оборудования.</span></div>';
    if (state === 'pain' || state === 'started') return '<div class="empty-state"><strong>Выбор заблокирован</strong><span>Безопасность и сохранённые факты важнее быстрого действия.</span></div>';
    if (state === 'offline') return '<div class="empty-state"><strong>Список недоступен офлайн</strong><span>Повторите после восстановления соединения.</span></div>';
    return '<div class="empty-state"><strong>Список не загружен</strong><span>Повторите запрос. Кандидаты не подставляются из локального каталога.</span></div>';
  }
  const shown = visibleCandidates(search, activeFilters);
  const compact = direction === 'quick' && !expanded ? shown.slice(0, 3) : shown;
  if (!compact.length) return '<div class="empty-state"><strong>Ничего не найдено</strong><span>Поиск работает только внутри подтверждённого ответа сервиса.</span></div>';
  return `<ul class="candidate-list">${compact.map((candidate, index) => candidateMarkup(candidate, direction, index)).join('')}</ul>`;
}

function previewMarkup(state) {
  if (!['preview', 'apply-disabled', 'conflict'].includes(state)) return '';
  return `<section class="preview-card" aria-live="polite" aria-labelledby="preview-title"><p class="card-label">Предпросмотр · без записи</p><strong id="preview-title">Изменение проверено</strong><div class="preview-line"><span>Сегодня</span><span>Жим штанги лёжа → Жим гантелей лёжа</span></div><div class="preview-line"><span>Программа</span><span>Без изменений</span></div><div class="preview-line"><span>Дальше</span><span>${state === 'conflict' ? 'Обновить предпросмотр' : 'Применить отдельно'}</span></div></section>`;
}

function renderPrototype(direction, state) {
  const root = document.querySelector(`[data-prototype="${direction}"]`);
  const expandedByState = state === 'expanded';
  const allDisabled = ['loading', 'empty', 'error', 'offline', 'pain', 'started', 'conflict'].includes(state);
  const activeFilters = new Set();
  root.innerHTML = `<div class="app-frame"><div class="app-top"><strong>Сегодня · тренировка</strong><small>синтетическая фикстура</small></div><div class="dialog" role="dialog" aria-labelledby="${direction}-title" aria-describedby="${direction}-description"><header class="dialog-header"><div><h3 id="${direction}-title">Заменить только в этой тренировке</h3><p id="${direction}-description">Исходная программа и будущие тренировки не меняются.</p></div><button class="close-button" type="button" aria-label="Закрыть">×</button></header><div class="dialog-body">${noticeForState(state)}<div class="original-card"><p class="card-label">Меняем</p><strong>Жим штанги лёжа</strong><p class="subline">Подходы не начаты · 4 × 8 · штанга, скамья</p></div>${direction === 'sheet' ? '<div class="sheet-peek"><div class="handle" aria-hidden="true"></div><p class="card-label">Быстрый выбор</p><strong>Жим гантелей лёжа</strong><p class="subline">Гантели · скамья · подтверждено сервисом</p></div>' : ''}${direction === 'compare' ? '<div class="compare-grid"><div class="compare-cell"><p class="card-label">Сейчас</p><strong>Жим штанги лёжа</strong><span>Штанга · скамья</span></div><div class="compare-cell selected"><p class="card-label">Выбрано</p><strong>Жим гантелей лёжа</strong><span>Гантели · скамья</span></div></div>' : ''}<section aria-labelledby="${direction}-choices-title"><div class="choice-head"><div><h4 id="${direction}-choices-title">Проверенные варианты</h4><p>Показаны только результаты текущего GET-запроса.</p></div><button class="link-button" type="button" data-action="toggle-all" ${allDisabled ? 'disabled' : ''}>${expandedByState ? 'Свернуть' : 'Все подходящие'}</button></div>${expandedByState || direction !== 'quick' ? `<div class="search-row"><label class="sr-only" for="${direction}-search">Поиск по подтверждённым вариантам</label><input id="${direction}-search" type="search" placeholder="Поиск по этому списку" value="" autocomplete="off" /></div><div class="filter-row" aria-label="Фильтр по оборудованию">${equipmentFilters.map((item) => `<button class="filter-chip" type="button" aria-pressed="false" data-filter="${item}">${item}</button>`).join('')}</div>` : ''}<div class="candidate-results" data-results>${listMarkup(direction, state, expandedByState, '', activeFilters)}</div></section>${previewMarkup(state)}<p class="small-status" aria-live="polite">${state === 'conflict' ? 'Применение остановлено до нового предпросмотра.' : state === 'offline' ? 'Сеть недоступна · действия заблокированы.' : 'Предпросмотр и применение — разные действия.'}</p></div><footer class="dialog-footer"><button type="button">Отмена</button><button class="primary preview-button" type="button" ${['loading', 'offline', 'error', 'empty', 'pain', 'started', 'conflict'].includes(state) ? 'disabled' : ''}>${['preview', 'apply-disabled'].includes(state) ? 'Обновить изменения' : 'Показать изменения'}</button>${['preview', 'apply-disabled'].includes(state) ? `<button class="primary apply-button" type="button" ${state === 'apply-disabled' ? 'disabled' : ''}>Применить только сегодня</button>` : ''}</footer></div></div>`;
  bindPrototype(root, direction, state);
}

function bindPrototype(root, direction, initialState) {
  const search = root.querySelector('input[type="search"]');
  const results = root.querySelector('[data-results]');
  const activeFilters = new Set();
  const refreshResults = () => {
    if (!search || !results) return;
    results.innerHTML = listMarkup(direction, initialState, true, search.value, activeFilters);
    search.focus();
    search.setSelectionRange(search.value.length, search.value.length);
  };
  search?.addEventListener('input', refreshResults);
  root.querySelectorAll('[data-filter]').forEach((button) => button.addEventListener('click', () => {
    const filter = button.dataset.filter;
    if (activeFilters.has(filter)) activeFilters.delete(filter); else activeFilters.add(filter);
    button.setAttribute('aria-pressed', String(activeFilters.has(filter)));
    refreshResults();
  }));
  root.querySelector('[data-action="toggle-all"]')?.addEventListener('click', () => {
    stateSelect.value = stateSelect.value === 'expanded' ? 'ready' : 'expanded';
    navigate();
  });
  root.querySelector('[data-action="retry"]')?.addEventListener('click', () => {
    stateSelect.value = 'ready';
    navigate();
  });
  root.querySelector('.preview-button')?.addEventListener('click', () => {
    stateSelect.value = 'preview';
    navigate();
  });
}

function renderAll() {
  const direction = directionSelect.value;
  const state = stateSelect.value;
  document.body.dataset.theme = document.body.dataset.theme === 'light' ? 'light' : 'dark';
  document.querySelectorAll('[data-direction-card]').forEach((card) => card.dataset.active = String(card.dataset.directionCard === direction));
  document.querySelectorAll('[data-prototype]').forEach((root) => renderPrototype(root.dataset.prototype, state));
  themeToggle.textContent = document.body.dataset.theme === 'dark' ? 'Светлая тема' : 'Тёмная тема';
  themeToggle.setAttribute('aria-pressed', String(document.body.dataset.theme === 'dark'));
}

directionSelect.addEventListener('change', navigate);
stateSelect.addEventListener('change', navigate);
themeToggle.addEventListener('click', () => {
  document.body.dataset.theme = document.body.dataset.theme === 'dark' ? 'light' : 'dark';
  navigate();
});
renderAll();
