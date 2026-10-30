/* Review-only UI. All counters and comparisons are read from service-generated fixtures.json. */
"use strict";
const q = (selector) => document.querySelector(selector);
const args = new URLSearchParams(location.search);
let days = Number(args.get("days"));
if (![7, 30, 90].includes(days)) days = 7;
let state = [
  "populated",
  "incomplete",
  "empty",
  "all_unmapped",
  "loading",
  "error",
].includes(args.get("state"))
  ? args.get("state")
  : "populated";
let selected = args.get("group") || "triceps";
const number = (value) =>
  new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value);
const date = (value) =>
  new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value + "T12:00:00Z"));
const escapeText = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const plural = (value, one, few, many) =>
  new Intl.PluralRules("ru").select(value) === "one"
    ? one
    : new Intl.PluralRules("ru").select(value) === "few"
      ? few
      : many;
// Exact shared iconGlyphs.tsx paths; existing Lucide/Phosphor notices apply.
const glyphs = {
  today:
    '<path d="M8 2v3"></path><path d="M16 2v3"></path><rect x="3" y="3" width="18" height="18" rx="2"></rect><path d="M3 9h18"></path><path d="M8 13h.01"></path><path d="M12 13h.01"></path><path d="M16 13h.01"></path><path d="M8 17h.01"></path><path d="M12 17h.01"></path><path d="M16 17h.01"></path>',
  plan: '<g transform="scale(0.09375)" fill="currentColor" stroke="none"><path d="M248,120h-8V88a16,16,0,0,0-16-16H208V64a16,16,0,0,0-16-16H168a16,16,0,0,0-16,16v56H104V64A16,16,0,0,0,88,48H64A16,16,0,0,0,48,64v8H32A16,16,0,0,0,16,88v32H8a8,8,0,0,0,0,16h8v32a16,16,0,0,0,16,16H48v8a16,16,0,0,0,16,16H88a16,16,0,0,0,16-16V136h48v56a16,16,0,0,0,16,16h24a16,16,0,0,0,16-16v-8h16a16,16,0,0,0,16-16V136h8a8,8,0,0,0,0-16ZM32,168V88H48v80Zm56,24H64V64H88V192Zm104,0H168V64h24V175.82c0,.06,0,.12,0,.18s0,.12,0,.18V192Zm32-24H208V88h16Z"></path></g>',
  nutrition:
    '<path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"></path><path d="M7 2v20"></path><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"></path>',
  progress:
    '<path d="M12 16v5"></path><path d="M16 14.639V21"></path><path d="M20 10.656V21"></path><path d="m22 3-8.646 8.646a.5.5 0 0 1-.708 0L9.354 8.354a.5.5 0 0 0-.707 0L2 15"></path><path d="M4 18.463V21"></path><path d="M8 14.656V21"></path>',
  plus: '<path d="M5 12h14"></path><path d="M12 5v14"></path>',
  info: '<circle cx="12" cy="12" r="10"></circle><path d="M12 16v-4"></path><path d="M12 8h.01"></path>',
  chevron: '<path d="m9 18 6-6-6-6"></path>',
};
const icon = (name) =>
  `<svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${glyphs[name]}</svg>`;
const nav = [
  ["today", "Сегодня"],
  ["plan", "План"],
  ["nutrition", "Питание"],
  ["progress", "Прогресс"],
  ["plus", "Добавить"],
]
  .map(
    ([key, label]) =>
      `<span class="nav-item" ${key === "progress" ? 'data-yfc-choice aria-current="page"' : ""}>${icon(key)}${label}</span>`,
  )
  .join("");
q(".desktop-nav").innerHTML = nav;
q(".dock").innerHTML = nav;
function theme(value) {
  document.documentElement.dataset.colorScheme = value;
  document
    .querySelectorAll(".logo")
    .forEach((el) => (el.src = `/assets/brand/yfc-logo-${value}.svg`));
  q("#theme").textContent = value === "dark" ? "Светлая тема" : "Тёмная тема";
}
theme(args.get("theme") === "light" ? "light" : "dark");
q("#theme").onclick = () =>
  theme(
    document.documentElement.dataset.colorScheme === "dark" ? "light" : "dark",
  );
let snapshots;
function detail(group) {
  const c = group.current,
    p = group.previous;
  const count = (v) =>
    v
      ? `${number(v.completed_set_count)} <span class="context-note">подх.</span>`
      : '<span class="context-note">Нет данных</span>';
  return `<section class="detail" id="selected-group-detail" aria-label="Подробности: ${escapeText(group.muscle_name)}"><p class="eyebrow">Выбранная группа</p><h3 class="detail-title">${escapeText(group.muscle_name)}</h3><div class="detail-meta">${c ? `${number(c.completed_session_count)} ${plural(c.completed_session_count, "тренировка", "тренировки", "тренировок")} · ${number(c.frequency_per_week)} в неделю` : "Нет данных за текущий период"}</div><div class="comparison"><div><small>Текущие ${days} дней</small><strong>${count(c)}</strong>${c ? `<p>Основное: ${c.primary_completed_set_count}<br>Вспомогательное: ${c.secondary_completed_set_count}</p>` : ""}</div><div><small>Предыдущие ${days} дней</small><strong>${count(p)}</strong>${p ? `<p>Основное: ${p.primary_completed_set_count}<br>Вспомогательное: ${p.secondary_completed_set_count}</p>` : ""}</div></div><p class="delta">${group.completed_set_count_change === null ? "Нет данных для сравнения" : `Изменение: ${group.completed_set_count_change > 0 ? "+" : ""}${group.completed_set_count_change} ${plural(Math.abs(group.completed_set_count_change), "подход", "подхода", "подходов")}`}</p><h4 class="source-head">Упражнения-источники</h4>${group.contributing_exercises.length ? group.contributing_exercises.map((e) => `<div class="contributor"><p class="source-title">${escapeText(e.exercise_title)}</p><p class="source-role">${e.contribution_roles.map((r) => (r === "primary" ? "Основное участие" : "Вспомогательное участие")).join(" · ")}</p><p class="source-values">${e.completed_set_count} ${plural(e.completed_set_count, "подход", "подхода", "подходов")} · ${e.performed_session_count} ${plural(e.performed_session_count, "тренировка", "тренировки", "тренировок")}</p>${e.history_truncated ? '<p class="source-role">Показана часть истории</p>' : ""}</div>`).join("") : '<p class="muted">В текущем периоде нет записей с этой группой.</p>'}<p class="detail-foot">Роли взяты из каталога упражнений. Частота относится к тренировкам с учтёнными подходами этой группы.</p></section>`;
}
function render() {
  const d =
    snapshots[["loading", "error"].includes(state) ? "empty" : state][days];
  q("#state").value = state;
  document.querySelectorAll("[data-days]").forEach((el) => {
    el.setAttribute("aria-selected", String(Number(el.dataset.days) === days));
    el.tabIndex = Number(el.dataset.days) === days ? 0 : -1;
  });
  q("#period-range").textContent =
    `Период: ${date(d.period_start)} — ${date(d.period_end)}`;
  const pending = ["loading", "error"].includes(state);
  q("#total-sets").textContent = pending ? "—" : number(d.completed_set_count);
  q("#sessions").textContent = pending
    ? "—"
    : number(d.completed_workout_count);
  q("#frequency").textContent = pending ? "—" : number(d.frequency_per_week);
  q("#previous-global").textContent = pending
    ? "Данные периода недоступны"
    : `Предыдущие ${days} дней: ${number(d.previous_completed_workout_count)} ${plural(d.previous_completed_workout_count, "тренировка", "тренировки", "тренировок")} · ${number(d.previous_frequency_per_week)} в неделю`;
  q("#quality").innerHTML = d.completed_sets_without_muscle_metadata
    ? `<div class="notice">${icon("info")}<div><b>Неполные сведения о мышцах</b>${d.completed_sets_without_muscle_metadata} ${plural(d.completed_sets_without_muscle_metadata, "подход", "подхода", "подходов")} без мышечных связей. Они входят в общее число подходов, но не распределены по группам.</div></div>`
    : "";
  const rows = d.muscle_group_workload;
  if (pending || !rows.length) {
    q("#workload").className = "";
    q("#workload").innerHTML =
      `<div class="empty" ${state === "loading" ? 'role="status" aria-busy="true"' : ""}><h3>${state === "loading" ? "Собираем тренировочные записи…" : state === "error" ? "Не удалось загрузить данные" : state === "all_unmapped" ? "Распределение пока недоступно" : "Нет записанных подходов"}</h3><p>${state === "loading" ? "Показатели появятся после загрузки выбранного периода." : state === "error" ? "Проверьте соединение и повторите загрузку." : state === "all_unmapped" ? "Подходы записаны, но у упражнений нет сведений о мышцах. Отсутствие связей не означает, что мышцы не участвовали." : "За выбранный период нет записанных завершённых рабочих подходов. Здесь появятся группы и упражнения из вашего журнала."}</p>${state === "error" ? '<button type="button" id="retry" style="margin-top:16px">Повторить</button>' : ""}</div>`;
    q(".legend").hidden = true;
    q(".chart-caption").hidden = true;
    if (q("#retry"))
      q("#retry").onclick = () => {
        state = "populated";
        render();
      };
    return;
  }
  q(".legend").hidden = false;
  q(".chart-caption").hidden = false;
  if (!rows.some((g) => g.muscle_id === selected)) selected = rows[0].muscle_id;
  const scale = Math.max(
    1,
    ...rows.flatMap((g) =>
      g.current
        ? [
            g.current.primary_completed_set_count,
            g.current.secondary_completed_set_count,
          ]
        : [],
    ),
  );
  const bars = (c) =>
    [
      ["Основное", c.primary_completed_set_count, "primary"],
      ["Вспомогательное", c.secondary_completed_set_count, "secondary"],
    ]
      .map(
        ([label, value, kind]) =>
          `<span class="role-line"><span>${label}</span><span class="track" aria-hidden="true"><i class="${kind}-fill" style="width:${(value / scale) * 100}%"></i></span><b>${value}</b></span>`,
      )
      .join("");
  const picked = rows.find((g) => g.muscle_id === selected);
  q("#workload").className = "workload";
  q("#workload").innerHTML =
    '<div class="groups">' +
    rows
      .map(
        (g) =>
          `<div class="group-row"><button type="button" class="group-button" data-group="${g.muscle_id}" aria-pressed="${g.muscle_id === selected}" aria-controls="selected-group-detail"><span class="group-heading"><span class="group-name">${escapeText(g.muscle_name)}</span><span class="group-total">${g.current ? `Всего ${g.current.completed_set_count}` : "Нет данных"}</span></span>${g.current ? bars(g.current) : '<span class="row-null">Нет записей с этой группой за период</span>'}<span class="row-meta"><span>${g.current ? `${g.current.completed_session_count} ${plural(g.current.completed_session_count, "тренировка", "тренировки", "тренировок")} · ${number(g.current.frequency_per_week)} / нед.` : "Ранее: " + g.previous.completed_set_count + " подх."}</span><span class="open-label">${g.muscle_id === selected ? "Выбрана" : "Подробнее"}${g.muscle_id === selected ? "" : icon("chevron")}</span></span></button>${g.muscle_id === selected && innerWidth < 1180 ? detail(g) : ""}</div>`,
      )
      .join("") +
    "</div>" +
    (innerWidth >= 1180 ? detail(picked) : "");
  document.querySelectorAll("[data-group]").forEach(
    (el) =>
      (el.onclick = () => {
        selected = el.dataset.group;
        render();
        const button = document.querySelector(`[data-group="${selected}"]`);
        button.focus({ preventScroll: true });
        q("#announcement").textContent =
          `Выбрана группа: ${rows.find((g) => g.muscle_id === selected).muscle_name}`;
      }),
  );
}
document.querySelectorAll("[data-days]").forEach((el) => {
  el.onclick = () => {
    days = Number(el.dataset.days);
    render();
    el.focus();
    q("#announcement").textContent =
      `Период ${days} дней. Пример данных обновлён.`;
  };
  el.onkeydown = (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const tabs = [...document.querySelectorAll("[data-days]")],
      index = tabs.indexOf(el);
    tabs[
      e.key === "Home"
        ? 0
        : e.key === "End"
          ? 2
          : (index + (e.key === "ArrowLeft" ? -1 : 1) + 3) % 3
    ].click();
  };
});
q("#state").onchange = (e) => {
  state = e.target.value;
  render();
};
let wide = innerWidth >= 1180;
addEventListener("resize", () => {
  const next = innerWidth >= 1180;
  if (next !== wide && snapshots) {
    wide = next;
    render();
  }
});
fetch("fixtures.json")
  .then((r) => {
    if (!r.ok) throw Error("Fixture unavailable");
    return r.json();
  })
  .then((data) => {
    snapshots = data.snapshots;
    render();
    document.body.dataset.ready = "true";
    q(".categories [aria-current]").scrollIntoView({
      block: "nearest",
      inline: "center",
    });
  })
  .catch(() => {
    q("#workload").innerHTML =
      '<p role="alert">Не удалось открыть данные макета.</p>';
  });
