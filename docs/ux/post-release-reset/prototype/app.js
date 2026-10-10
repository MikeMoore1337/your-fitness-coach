import { icon } from "./approved-icons.js";

const directions = {
  a: "Command Stack",
  b: "Day Rail",
  c: "Signal Grid",
};

const params = new URLSearchParams(location.search);
let variant = params.get("variant") || "a";
let screen = params.get("screen") || "today-workout";
let frame = params.get("frame") || "mobile";
let theme = params.get("theme") || "light";
const presentation = params.get("presentation") === "1";

const root = document.documentElement;
const app = document.querySelector("#app");
const variantSelect = document.querySelector("#variantSelect");
const screenSelect = document.querySelector("#screenSelect");
const frameSelect = document.querySelector("#frameSelect");
const themeButton = document.querySelector("#themeButton");
const directionLabel = document.querySelector("#directionLabel");

function week() {
  return `<div class="week" role="group" aria-label="Неделя">
    ${["ПН 24", "ВТ 25", "СР 26", "ЧТ 27", "ПТ 28", "СБ 29", "ВС 30"]
      .map((day, index) => {
        const [label, date] = day.split(" ");
        return `<button type="button" aria-pressed="${index === 6}" ${index === 6 ? 'aria-current="date"' : ""}>${label}<span>${date}</span></button>`;
      })
      .join("")}
  </div>`;
}

function header(title = "Сегодня", subtitle = "Воскресенье, 30 августа") {
  return `<div class="screen-head">
    <div><div class="brand"><b>YFC</b> · Your Fitness Coach</div></div>
    <button class="avatar" type="button" data-screen="profile-compact" aria-label="Открыть профиль">${icon("nav-profile")}</button>
  </div>
  <div class="date-line"><div><span class="eyebrow">${subtitle}</span><h1>${title}</h1></div><button type="button" aria-label="Выбрать дату">${icon("chevron-down", 20)}</button></div>`;
}

function nav(active) {
  const items = [
    ["today", "today-workout", "nav-today", "Сегодня"],
    ["program", "program", "nav-plan", "Программа"],
    ["nutrition", "nutrition-empty", "nav-nutrition", "Питание"],
    ["progress", "progress-data", "nav-progress", "Прогресс"],
  ];
  return `<nav class="bottom-nav" aria-label="Основная навигация">${items
    .map(
      ([key, target, iconName, label]) =>
        `<button type="button" data-screen="${target}" ${active === key ? 'aria-current="page"' : ""}><span class="nav-icon">${icon(iconName)}</span><span class="nav-label">${label}</span></button>`,
    )
    .join("")}</nav>`;
}

function summaryCard(family, iconName, title, meta, action, target = "") {
  return `<section class="card ${family}"><div class="card-head">
    <span class="family-icon ${family}">${icon(iconName)}</span>
    <div><h2>${title}</h2><div class="meta">${meta}</div></div>
    <button class="quick" type="button" ${target ? `data-screen="${target}"` : ""}>${action}</button>
  </div></section>`;
}

function todayNew() {
  return `${header()}<div class="main-stack">
    ${week()}
    <section class="hero training"><span class="eyebrow">Первый шаг</span><h2 class="display">С чего начнём?</h2>
      <p class="hero-copy">Настройки можно заполнить позже. Начните с действия, которое полезно прямо сейчас.</p>
      <button class="primary" type="button" data-screen="program">Создать программу</button>
      <div class="action-row"><button class="secondary" type="button" data-screen="nutrition-search">Записать питание</button><button class="secondary" type="button" data-screen="active-cardio">Добавить активность</button></div>
    </section>
    ${summaryCard("progress", "nav-progress", "Прогресс", "Появится после первых записей", "Что учитывать", "progress-empty")}
    ${summaryCard("wellbeing", "nav-profile", "Профиль", "0 из 3 для персонализации", "Не сейчас", "profile-compact")}
  </div>${nav("today")}`;
}

function todayWorkout() {
  return `${header()}<div class="main-stack">
    ${week()}
    <section class="hero training"><span class="eyebrow">Сегодня · 18:30</span><span class="chip good">Запланирована</span><h2 class="display">Силовая база</h2>
      <p class="hero-copy">5 упражнений · около 55 минут</p>
      <button class="primary" type="button" data-screen="active-strength">Начать тренировку</button>
      <div class="action-row"><button class="ghost" type="button">Посмотреть состав</button><button class="ghost" type="button">Изменить</button></div>
    </section>
    ${summaryCard("nutrition", "nav-nutrition", "Питание", "1460 из 2100 ккал · белок 92 г", "Добавить", "nutrition-search")}
    ${summaryCard("progress", "nav-progress", "Прогресс", "3 тренировки за 7 дней · по плану", "Открыть", "progress-data")}
    ${summaryCard("wellbeing", "week-cardio", "Самочувствие", "Не отмечено · необязательно", "Отметить")}
  </div>${nav("today")}`;
}

function todayRest() {
  return `${header()}<div class="main-stack">${week()}
    <section class="hero"><span class="eyebrow">День без силовой</span><h2 class="display">Сегодня можно восстановиться</h2><p class="hero-copy">План на месте. Выберите одно лёгкое действие — или ничего.</p>
      <button class="primary" type="button" data-screen="nutrition-search">Записать питание</button>
      <div class="action-row"><button class="secondary" type="button" data-screen="active-cardio">Добавить кардио</button><button class="secondary" type="button">Отметить самочувствие</button></div>
    </section>
    ${summaryCard("training", "week-cardio", "Кардио", "Записей за сегодня нет", "Добавить", "active-cardio")}
    ${summaryCard("progress", "body-weight", "Последний замер", "80,9 кг · 14 дней назад", "Обновить", "progress-data")}
  </div>${nav("today")}`;
}

function programScreen() {
  return `${header("Программа тренировок", "Текущий цикл · неделя 2")}<div class="main-stack">
    <section class="hero training"><span class="eyebrow">Активная программа</span><h2 class="display">Силовая база</h2><p class="hero-copy">3 дня · 14 упражнений · следующий день сегодня</p><button class="primary" type="button" data-screen="active-strength">Начать День 1</button></section>
    <div class="step-list">
      <article class="step current"><span class="step-number">1</span><div><strong>День 1 · База</strong><div class="meta">5 упражнений · ~55 мин</div></div><button class="quick" type="button">Открыть</button></article>
      <article class="step"><span class="step-number">2</span><div><strong>День 2 · Тяга</strong><div class="meta">4 упражнения · ~45 мин</div></div><button class="quick" type="button">Открыть</button></article>
      <article class="step"><span class="step-number">3</span><div><strong>День 3 · Объём</strong><div class="meta">5 упражнений · ~60 мин</div></div><button class="quick" type="button">Открыть</button></article>
    </div>
    ${summaryCard("training", "plus", "Создать свою программу", "Базовый путь: основа → день → упражнения", "Создать")}
    ${summaryCard("progress", "nav-plan", "Шаблоны и подбор", "Готовые варианты, история и дополнительные настройки", "Открыть")}
  </div>${nav("program")}`;
}

function activeStrength() {
  return `${header("Тренировка", "День 1 · начата 12 минут назад")}<div class="main-stack">
    <div class="timer"><span>Сейчас · подход 2 из 3</span><strong>Отдых 00:48</strong></div>
    <article class="exercise-card"><div class="exercise-title"><div><span class="eyebrow">Упражнение 1 из 5</span><h2 class="display">Жим штанги лёжа</h2><p>Предыдущий: 40 кг × 8</p></div><button class="quick" type="button">Техника</button></div>
      <div class="set-row"><span class="step-number">2</span><label>Вес, кг<input value="40" inputmode="decimal" aria-label="Вес, кг" /></label><label>Повторы<input value="8" inputmode="numeric" aria-label="Повторы" /></label><button class="set-done" type="button" aria-label="Завершить подход">${icon("check")}</button></div>
      <button class="ghost advanced-trigger" type="button" aria-expanded="false">Дополнительно · запас, тип, заметка</button>
    </article>
    ${summaryCard("training", "week-strength", "Дальше: тяга блока", "3 подхода · 10–12 повторов", "Посмотреть")}
    <button class="secondary" type="button">Завершить тренировку</button>
  </div>${nav("program")}`;
}

function activeCardio() {
  return `${header("Кардио", "Фактическая активность · сегодня")}<div class="main-stack">
    <section class="hero progress"><span class="eyebrow">Идёт сейчас · ходьба</span><h2 class="display">24:18</h2><p class="hero-copy">2,1 км · средний темп 11:34/км</p><button class="primary" type="button">Завершить кардио</button><div class="action-row"><button class="secondary" type="button">Пауза</button><button class="secondary" type="button">Отменить</button></div></section>
    ${summaryCard("progress", "week-cardio", "Пульс", "Средний 118 · диапазон 102–132", "Подробнее")}
    ${summaryCard("training", "timer", "Цель", "30 минут лёгкой активности", "Изменить")}
    <section class="card"><button class="ghost" type="button" aria-expanded="false">Дополнительно · дистанция, заметка</button></section>
  </div>${nav("today")}`;
}

function nutritionSearch() {
  return `${header("Питание", "Завтрак · добавить продукт")}<div class="main-stack">
    <section class="picker-panel"><button class="primary button-with-icon" type="button" data-screen="nutrition-barcode"><span class="button-icon">${icon("barcode", 20)}</span><span>Сканировать штрихкод</span></button><label><span class="eyebrow">Поиск по названию или бренду</span><input class="search" value="нутелла" aria-label="Поиск по названию или бренду" /></label>
      <div class="result-row"><div><strong>Nutella hazelnut spread</strong><div class="meta">Ferrero · 539 ккал / 100 г</div></div><button type="button">Выбрать</button></div>
      <div class="result-row"><div><strong>Ореховая паста</strong><div class="meta">Мои продукты · 612 ккал / 100 г</div></div><button type="button">Выбрать</button></div>
      <button class="secondary" type="button">Быстрый ввод</button><button class="ghost" type="button">Создать продукт</button>
    </section>
  </div>${nav("nutrition")}`;
}

function nutritionEmpty() {
  return `${header("Питание", "Сегодня · дневник")}<div class="main-stack">${week()}
    <section class="hero nutrition"><span class="eyebrow">Итоги дня</span><h2 class="display">Записей пока нет</h2><p class="hero-copy">Это не означает 0 ккал. Добавьте первый приём пищи или отметьте статус дня.</p><button class="primary" type="button" data-screen="nutrition-search">Добавить продукт</button></section>
    ${["Завтрак", "Обед", "Ужин", "Перекусы"].map((name) => `<section class="meal-row"><div><strong>${name}</strong><div class="meta">Нет записей</div></div><button type="button" data-screen="nutrition-search">+ Добавить</button></section>`).join("")}
    ${summaryCard("nutrition", "nav-progress", "Цели и отчёты", "2100 ккал · история и периоды", "Открыть")}
  </div>${nav("nutrition")}`;
}

function nutritionBarcode() {
  return `${header("Штрихкод", "Завтрак · новый продукт")}<div class="main-stack"><section class="picker-panel"><div class="barcode-box"><div><span class="eyebrow">Камера</span><h2>Наведите на штрихкод</h2><p>Код обрабатывается на устройстве, затем проверяется каталог.</p></div></div><button class="primary" type="button">Включить камеру</button><label><span class="eyebrow">Или введите вручную</span><input class="search" value="3017620422003" inputmode="numeric" aria-label="Штрихкод" /></label><button class="secondary" type="button">Найти</button></section></div>${nav("nutrition")}`;
}

function progressData() {
  return `${header("Прогресс", "Последние 30 дней")}<div class="main-stack"><section class="hero progress insight-hero"><span class="eyebrow">Главный вывод</span><h2 class="display">Вес снижается, силовые стабильны</h2><p class="hero-copy">−1,5 кг за 30 дней · 10 из 12 тренировок. Данных достаточно для общего вывода.</p><button class="primary" type="button">Открыть динамику</button></section>
    <div class="summary-grid"><article class="metric training" style="--value:.83"><span class="eyebrow">Тренировки</span><strong>10 / 12</strong><small>83% по плану</small></article><article class="metric progress" style="--value:.72"><span class="eyebrow">Вес</span><strong>80,9 кг</strong><small>−1,5 кг</small></article><article class="metric nutrition" style="--value:.61"><span class="eyebrow">Питание</span><strong>18 дней</strong><small>данные частичные</small></article><article class="metric wellbeing" style="--value:.34"><span class="eyebrow">Самочувствие</span><strong>Нет данных</strong><small>необязательно</small></article></div>
    ${summaryCard("progress", "body-weight", "Измерения", "4 записи · последняя сегодня", "История")}
    ${summaryCard("nutrition", "nav-nutrition", "Отчёт питания", "Средние и заполненность периода", "Открыть")}
  </div>${nav("progress")}`;
}

function progressEmpty() {
  return `${header("Прогресс", "Последние 30 дней")}<div class="main-stack"><section class="hero progress"><span class="eyebrow">Пока рано для вывода</span><h2 class="display">Добавьте первую точку</h2><p class="hero-copy">Отсутствие записей — не ноль. Один замер создаст baseline, повторный покажет изменение.</p><button class="primary" type="button">Добавить замер</button></section>
    <section class="card confidence"><div class="card-head"><span class="family-icon progress">${icon("info")}</span><div><h2>Достаточно ли данных</h2><div class="meta">0 замеров · нужно минимум 2 в разные даты</div></div><button class="quick" type="button">Почему?</button></div></section>
    ${summaryCard("training", "nav-plan", "Тренировки", "Пока нет завершённых", "Перейти в Программу", "program")}
    ${summaryCard("nutrition", "nav-nutrition", "Питание", "Нет заполненных дней", "Добавить", "nutrition-search")}
  </div>${nav("progress")}`;
}

function profileCompact() {
  const rows = [
    ["nav-profile", "Личные данные", "Имя и часовой пояс"],
    ["sliders-horizontal", "Цели и параметры", "Заполнено 1 из 3"],
    ["coach-invite", "Тренер и приглашения", "Не подключён"],
    ["bell", "Уведомления", "Выключены"],
    ["shield-check", "Доступ и безопасность", "4 способа входа"],
  ];
  return `${header("Профиль", "Аккаунт и настройки")}<div class="main-stack"><section class="hero"><div class="card-head"><span class="avatar">${icon("nav-profile")}</span><div><span class="eyebrow">Анна Петрова · Клиент</span><h2>Профиль стоит дополнить</h2><p>1 из 3 для персонализации программы</p></div></div><button class="secondary" type="button" data-screen="profile-expanded">Дополнить профиль</button></section>
    ${rows.map(([iconName, title, meta], index) => `<section class="setting-row"><span class="family-icon">${icon(iconName)}</span><div><strong>${title}</strong><div class="meta">${meta}</div></div><button type="button" ${index === 1 ? 'data-screen="profile-expanded"' : ""} aria-label="Открыть ${title}">${icon("chevron-right", 20)}</button></section>`).join("")}
  </div>${nav("profile")}`;
}

function profileExpanded() {
  return `${header("Цели и параметры", "Профиль · detail")}<div class="main-stack"><section class="card profile-form"><span class="eyebrow">Основа рекомендаций</span><h2>Тренировочная цель</h2><label><span class="meta">Цель</span><select class="search" aria-label="Цель"><option>Поддерживать форму</option><option>Снижение жировой массы</option></select></label><label><span class="meta">Уровень подготовки</span><select class="search" aria-label="Уровень"><option>Начинаю или возвращаюсь</option></select></label><label><span class="meta">Силовых тренировок в неделю</span><input class="search" value="3" inputmode="numeric" aria-label="Силовых тренировок в неделю" /></label><button class="primary" type="button">Сохранить изменения</button></section><section class="card"><button class="ghost" type="button" aria-expanded="false">Дополнительно · пульсовые зоны и ограничения</button></section></div>${nav("profile")}`;
}

const renderers = {
  "today-new": todayNew,
  "today-workout": todayWorkout,
  "today-rest": todayRest,
  program: programScreen,
  "active-strength": activeStrength,
  "active-cardio": activeCardio,
  "nutrition-search": nutritionSearch,
  "nutrition-empty": nutritionEmpty,
  "nutrition-barcode": nutritionBarcode,
  "progress-data": progressData,
  "progress-empty": progressEmpty,
  "profile-compact": profileCompact,
  "profile-expanded": profileExpanded,
};

const tmaActions = document.querySelector(".tma-actions");
if (tmaActions) tmaActions.innerHTML = icon("more-horizontal", 20);

function syncUrl() {
  const next = new URL(location.href);
  next.searchParams.set("variant", variant);
  next.searchParams.set("screen", screen);
  next.searchParams.set("frame", frame);
  next.searchParams.set("theme", theme);
  if (presentation) next.searchParams.set("presentation", "1");
  history.replaceState(null, "", next);
}

function render() {
  const [screenName, renderScreen] = Object.entries(renderers).find(
    ([name]) => name === screen,
  ) || ["today-workout", todayWorkout];
  screen = screenName;
  if (!Object.hasOwn(directions, variant)) variant = "a";
  if (!["mobile", "tma", "desktop"].includes(frame)) frame = "mobile";
  if (!["light", "dark"].includes(theme)) theme = "light";
  root.dataset.variant = variant;
  root.dataset.frame = frame;
  root.dataset.theme = theme;
  root.dataset.presentation = String(presentation);
  variantSelect.value = variant;
  screenSelect.value = screen;
  frameSelect.value = frame;
  directionLabel.textContent = directions[variant];
  themeButton.textContent = theme === "light" ? "Тёмная тема" : "Светлая тема";
  app.innerHTML = `<section class="screen" data-screen-state="${screenName}">${renderScreen()}</section>`;
  const currentNavigation = app.querySelector(".bottom-nav");
  if (currentNavigation) app.append(currentNavigation);
  app.scrollTop = 0;
  syncUrl();
}

variantSelect.addEventListener("change", () => {
  variant = variantSelect.value;
  render();
});
screenSelect.addEventListener("change", () => {
  screen = screenSelect.value;
  render();
});
frameSelect.addEventListener("change", () => {
  frame = frameSelect.value;
  render();
});
themeButton.addEventListener("click", () => {
  theme = theme === "light" ? "dark" : "light";
  render();
});
app.addEventListener("click", (event) => {
  const selectedDay = event.target.closest(".week button");
  if (selectedDay) {
    selectedDay
      .closest(".week")
      .querySelectorAll("button")
      .forEach((day) =>
        day.setAttribute("aria-pressed", String(day === selectedDay)),
      );
    return;
  }
  const target = event.target.closest("[data-screen]");
  if (!target) return;
  screen = target.dataset.screen;
  render();
});

render();
