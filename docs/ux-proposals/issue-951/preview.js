// Interactive visual prototype with synthetic data; no network or diary writes.
const foods = [
  { id: 'y-a', name: 'Йогурт натуральный', brand: 'Марка А', source: 'Проверено YFC', basis: '100 г', unit: 'г', values: [60, 3.5, 3, 4, null] },
  { id: 'y-b', name: 'Йогурт натуральный', brand: 'Марка Б', source: 'Open Food Facts', basis: '100 г', unit: 'г', values: [72, 4, 3, 6, null] },
  { id: 'oat', name: 'Овсяные хлопья цельнозерновые длительной варки', brand: 'Северные поля', source: 'Сообщество', basis: '100 г', unit: 'г', values: [360, 12, 6, 62, 9] },
  { id: 'milk', name: 'Напиток овсяный без сахара', brand: 'Лесной берег', source: 'Проверено YFC', basis: '100 мл', unit: 'мл', values: [45, 1, 1.5, 7, 0.5] },
  { id: 'bread', name: 'Хлеб цельнозерновой нарезанный', brand: 'Пекарня 1', source: 'Мой продукт', basis: '100 г', unit: 'г', servingWeight: 40, values: [240, 8, 3, 45, 6] },
  { id: 'egg', name: 'Яйцо куриное варёное', brand: '', source: 'Проверено YFC', basis: 'порцию', unit: 'порц.', values: [75, 6, 5, 0.5, 0] },
  { id: 'rice', name: 'Рис белый отварной', brand: 'Марка В', source: 'USDA', basis: '100 г', unit: 'г', values: [130, 2.7, 0.3, 28, null] },
  { id: 'unknown', name: 'Соус томатный домашний', brand: 'Марка Г', source: 'Сообщество', basis: '100 г', unit: 'г', values: [40, null, null, 8, null] },
];
const params = new URLSearchParams(location.search);
const variant = params.get('variant') === 'b' ? 'b' : 'a';
const state = params.get('state') || 'selected';
if (params.get('dataset') === 'baseline') {
  foods.splice(0, foods.length, ...['Рис белый отварной', 'Рис бурый отварной', 'Гречка отварная', 'Куриная грудка запечённая', 'Творог натуральный', 'Яблоко свежее'].map((name, i) => ({ id: `baseline-${i}`, name, brand: '', source: 'Проверено YFC', basis: '100 г', unit: 'г', values: [100, 5, 2, 15, null] })));
}
document.body.dataset.variant = variant;
document.documentElement.dataset.theme = params.get('theme') === 'dark' ? 'dark' : 'light';
const el = (id) => document.getElementById(id);
const search = el('search');
let selected = new Map();
let trayOpen = state === 'editing' || state === 'invalid' || state === 'units';
let activeTab = trayOpen ? 'picked' : 'search';
let failure = state === 'network';
let viewState = state;
let singleFood = null;
let confirmed = false;
const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label = (food) => [food.name, food.brand, food.source].filter(Boolean).join(', ');
const defaultAmount = (food) => food.unit === 'порц.' || food.servingWeight ? 1 : 100;
const defaultUnit = (food) => food.unit === 'порц.' || food.servingWeight ? 'порц.' : food.unit;
function add(food) { selected.set(food.id, { amount: defaultAmount(food), unit: defaultUnit(food) }); }
if (['selected', 'editing', 'keyboard', 'network'].includes(state)) {
  [foods[0], foods[2], foods[3]].forEach(add);
  search.value = 'йогурт';
} else if (state === 'units') {
  [foods[3], foods[4], foods[5]].forEach(add);
} else if (state === 'unknown') {
  add(foods[7]);
  search.value = 'соус';
} else if (state === 'single' || state === 'invalid') {
  add(foods[0]);
  if (state === 'invalid') selected.get(foods[0].id).amount = 0;
  search.value = 'йогурт';
} else if (state === 'empty') search.value = 'несуществующий продукт';
else if (state === 'loading' || state === 'error') search.value = 'йогурт';
if (state === 'begin') el('overlay').hidden = true;
el('tabs').hidden = variant !== 'b';
function safeAmount(row) { const n = Number(String(row.amount).replace(',', '.')); return Number.isFinite(n) && n > 0; }
function format(n) { return new Intl.NumberFormat('ru-RU', {maximumFractionDigits:1}).format(n); }
function facts(food) { const v=food.values.map((n) => n === null ? '—' : format(n)); return `На ${food.basis}: ${v[0]} ккал · Б ${v[1]} · Ж ${v[2]} · У ${v[3]} · клетчатка ${v[4]}`; }
function sums() {
  if (!selected.size || [...selected.values()].some((row) => !safeAmount(row))) return null;
  return [0, 1, 2, 3, 4].map((key) => {
    let total = 0;
    for (const [id, row] of selected) {
      const food = foods.find((item) => item.id === id);
      if (food.values[key] === null) return null;
      const amount = Number(String(row.amount).replace(',', '.'));
      const factor = row.unit === 'порц.' ? (food.unit === 'порц.' ? amount : amount * food.servingWeight / 100) : amount / 100;
      total += food.values[key] * factor;
    }
    return total;
  });
}
function renderFooter() {
  const count = selected.size;
  const sum = sums();
  el('total-count').textContent = count ? `Выбрано: ${count}${sum && sum.slice(0, 4).includes(null) ? ' · есть неизвестные значения' : ''}` : 'Нет выбранных продуктов';
  const value = (i) => sum && sum[i] !== null ? format(sum[i]) : '—';
  el('total-values').innerHTML = count ? `<strong>${value(0)} ккал</strong>Б ${value(1)} · Ж ${value(2)} · У ${value(3)} г<br>Клетчатка ${value(4)} г` : '<span>КБЖУ появятся после выбора</span>';
  el('confirm').disabled = !sum || confirmed;
  el('footer-error').innerHTML = failure ? '<p class="error">Не удалось подтвердить добавление. Проверьте сеть и повторите. Результат предыдущей попытки нужно уточнить.</p>' : '';
  el('confirm').textContent = failure ? 'Повторить подтверждение' : 'Добавить в дневник';
  document.querySelectorAll('.count').forEach((node) => node.textContent = count);
}
function basketMarkup() {
  if (!selected.size) return '<div class="empty">Вы пока не выбрали продукты. Найдите нужный и нажмите «Выбрать».</div>';
  return `<div class="basket-intro"><strong>Выбрано: ${selected.size}</strong><span>Можно изменить или удалить</span></div>${[...selected].map(([id, row]) => {
    const food = foods.find((item) => item.id === id);
    const units = food.unit === 'порц.' ? ['порц.'] : food.servingWeight ? ['г', 'порц.'] : [food.unit];
    const invalid = !safeAmount(row);
    return `<div class="picked-row"><div class="picked-top"><div><strong class="item-name">${escapeHtml(food.name)}</strong><span class="item-sub">${escapeHtml([food.brand, food.source].filter(Boolean).join(' · '))}</span><span class="item-sub">${facts(food)}</span></div><button class="remove" data-remove="${id}" aria-label="Убрать ${escapeHtml(label(food))} из подборки">Убрать</button></div><div class="amount"><label for="amount-${id}">Количество</label><input id="amount-${id}" data-amount="${id}" aria-label="Количество: ${escapeHtml(label(food))}" inputmode="decimal" type="number" min="0.001" step="any" value="${row.amount}" aria-invalid="${invalid}"><select data-unit="${id}" aria-label="Единица: ${escapeHtml(label(food))}">${units.map((unit) => `<option ${row.unit === unit ? 'selected' : ''}>${unit}</option>`).join('')}</select></div>${food.servingWeight ? `<span class="item-sub">1 порция = ${food.servingWeight} г</span>` : ''}<p class="validation" ${invalid ? '' : 'hidden'}>Введите количество больше нуля.</p></div>`;
  }).join('')}`;
}
function renderResults() {
  const q = search.value.trim().toLocaleLowerCase('ru');
  const matched = foods.filter((food) => `${food.name} ${food.brand}`.toLocaleLowerCase('ru').includes(q));
  el('list-title').textContent = q ? 'Результаты поиска' : 'Недавние продукты';
  if (viewState === 'loading') { el('results').innerHTML = '<div class="empty" role="status">Ищем продукты…</div>'; return; }
  if (viewState === 'error') { el('results').innerHTML = '<div class="empty" role="alert">Не удалось загрузить продукты. Проверьте сеть и повторите поиск.<br><button class="secondary" id="retry-search">Повторить</button></div>'; return; }
  if (!matched.length) { el('results').innerHTML = '<div class="empty">Ничего не найдено. Попробуйте другое название или создайте свой продукт.</div>'; return; }
  el('results').innerHTML = matched.map((food) => `<div class="result ${selected.has(food.id) ? 'selected' : ''}"><button class="product" data-single="${food.id}" aria-label="Обычное добавление: ${escapeHtml(label(food))}"><strong>${escapeHtml(food.name)}</strong><span>${escapeHtml(food.brand || 'Без бренда')} · ${food.values[0] === null ? '—' : format(food.values[0])} ккал / ${food.basis}</span><span class="badge">${escapeHtml(food.source)}</span></button><button class="choose" data-choose="${food.id}" aria-pressed="${selected.has(food.id)}" aria-label="${selected.has(food.id) ? 'Убрать' : 'Выбрать'} ${escapeHtml(label(food))}">${selected.has(food.id) ? 'Выбрано' : 'Выбрать'}</button></div>`).join('');
}
function renderBasket() {
  if (variant === 'a') {
    el('tray').innerHTML = `<button class="tray-toggle" id="tray-toggle" aria-expanded="${trayOpen}">Подборка · ${selected.size}<span>${trayOpen ? 'Свернуть' : 'Изменить'}</span></button>${trayOpen ? `<div class="basket">${basketMarkup()}</div>` : ''}`;
    el('picked-pane').hidden = true;
  } else {
    el('tray').innerHTML = '';
    el('picked-pane').innerHTML = basketMarkup();
    el('picked-pane').hidden = activeTab !== 'picked';
    el('search-pane').hidden = activeTab === 'picked';
    el('tab-search').setAttribute('aria-selected', activeTab === 'search');
    el('tab-picked').setAttribute('aria-selected', activeTab === 'picked');
    el('tab-search').tabIndex = activeTab === 'search' ? 0 : -1;
    el('tab-picked').tabIndex = activeTab === 'picked' ? 0 : -1;
  }
}
function render() { renderResults(); renderBasket(); renderFooter(); }
search.addEventListener('input', () => { failure = false; viewState = ''; renderResults(); renderFooter(); });
el('clear').addEventListener('click', () => { search.value = ''; search.focus(); renderResults(); });
el('open').addEventListener('click', () => { if (confirmed) { selected.clear(); confirmed = false; search.value = ''; render(); } el('overlay').hidden = false; el('toast').hidden = true; search.focus(); });
el('close').addEventListener('click', () => { el('overlay').hidden = true; selected.clear(); confirmed = false; search.value = ''; trayOpen = false; activeTab = 'search'; failure = false; viewState = ''; el('single').hidden = true; el('multi').hidden = false; render(); el('open').focus(); });
el('tab-search').addEventListener('click', () => { activeTab = 'search'; renderBasket(); });
el('tab-picked').addEventListener('click', () => { activeTab = 'picked'; renderBasket(); });
el('tabs').addEventListener('keydown', (event) => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  activeTab = event.key === 'Home' ? 'search' : event.key === 'End' ? 'picked' : activeTab === 'search' ? 'picked' : 'search';
  renderBasket();
  el(activeTab === 'search' ? 'tab-search' : 'tab-picked').focus();
});
document.addEventListener('click', (event) => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.id === 'retry-search') { viewState = ''; renderResults(); return; }
  if (button.id === 'tray-toggle') { trayOpen = !trayOpen; renderBasket(); return; }
  if (button.dataset.choose) { const food = foods.find((x) => x.id === button.dataset.choose); selected.has(food.id) ? selected.delete(food.id) : add(food); failure = false; render(); return; }
  if (button.dataset.remove) { selected.delete(button.dataset.remove); render(); return; }
  if (button.dataset.single) { singleFood = foods.find((x) => x.id === button.dataset.single); showSingle(); return; }
  if (button.id === 'single-back') { singleFood = null; el('single').hidden = true; el('multi').hidden = false; return; }
  if (button.id === 'single-confirm') { el('single').hidden = true; el('multi').hidden = false; if (!selected.size) { el('overlay').hidden = true; confirmed = true; } el('toast').hidden = false; return; }
  if (button.id === 'quick') { el('toast').hidden = false; return; }
});
document.addEventListener('input', (event) => {
  const id = event.target.dataset.amount;
  if (!id) return;
  selected.get(id).amount = event.target.value;
  const invalid = !safeAmount(selected.get(id));
  event.target.setAttribute('aria-invalid', String(invalid));
  event.target.closest('.picked-row').querySelector('.validation').hidden = !invalid;
  renderFooter();
});
document.addEventListener('change', (event) => {
  const id = event.target.dataset.unit;
  if (!id) return;
  selected.get(id).unit = event.target.value;
  renderFooter();
});
el('confirm').addEventListener('click', () => { confirmed = true; el('overlay').hidden = true; el('toast').hidden = false; });
function showSingle() {
  const food = singleFood;
  el('multi').hidden = true;
  el('single').hidden = false;
  el('single').className = 'single-view';
  el('single').innerHTML = `<button class="secondary" id="single-back">К поиску</button><h3>${escapeHtml(food.name)}</h3><p class="metadata">${escapeHtml([food.brand,food.source].filter(Boolean).join(' · '))}</p><p class="metadata">${facts(food)}</p><div class="amount"><label for="single-amount">Количество</label><input id="single-amount" type="number" value="${defaultAmount(food)}"><select aria-label="Единица"><option>${defaultUnit(food)}</option></select></div><button class="primary" id="single-confirm">Добавить в дневник</button>`;
}
render();
if (state === 'single') { singleFood = foods[0]; showSingle(); }
