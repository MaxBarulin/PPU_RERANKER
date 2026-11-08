// Сцены ролика. build(root, B) создаёт элементы и возвращает update(t); B[k] - начало k-й фразы (с начала сцены).

const ICON = {
  store: `<svg viewBox="0 0 64 64" width="64" height="64" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linejoin="round">
    <path d="M6 26 32 10l26 16v30H6z"/><path d="M16 56V34h32v22"/><path d="M16 42h32M16 50h32"/></svg>`,
  vector: `<svg viewBox="0 0 64 64" width="64" height="64" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round">
    <path d="M10 54 52 22M10 54 38 10M10 54h44"/><circle cx="52" cy="22" r="4" fill="currentColor"/><circle cx="38" cy="10" r="4" fill="currentColor"/></svg>`,
  search: `<svg viewBox="0 0 64 64" width="64" height="64" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round">
    <circle cx="27" cy="27" r="17"/><path d="m40 40 16 16"/><path d="M19 27h16M27 19v16" opacity=".55"/></svg>`,
  gauge: `<svg viewBox="0 0 64 64" width="64" height="64" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round">
    <path d="M8 46a24 24 0 0 1 48 0"/><path d="M32 46 46 26"/><circle cx="32" cy="46" r="4" fill="currentColor"/><path d="M14 32l4 3M50 32l-4 3M32 22v5"/></svg>`,
  judge: `<svg viewBox="0 0 64 64" width="64" height="64" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M32 8v48M18 56h28M12 16h40"/><path d="M12 16 4 36h16zM52 16l-8 20h16z"/><path d="M4 36a8 6 0 0 0 16 0M44 36a8 6 0 0 0 16 0"/></svg>`,
  doc: `<svg viewBox="0 0 64 64" width="64" height="64" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linejoin="round">
    <path d="M14 6h26l12 12v40H14z"/><path d="M40 6v12h12M22 30h22M22 38h22M22 46h14"/></svg>`,
  answer: `<svg viewBox="0 0 64 64" width="64" height="64" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
    <rect x="6" y="10" width="52" height="44" rx="6"/><path d="m20 32 8 8 16-16"/></svg>`,
  pc: `<svg viewBox="0 0 120 100" width="180" height="150" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round">
    <rect x="6" y="6" width="108" height="66" rx="6"/><path d="M44 72v14M76 72v14M32 90h56"/><path d="M6 20h108" opacity=".5"/></svg>`,
  cloud: `<svg viewBox="0 0 120 80" width="170" height="113" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round">
    <path d="M30 70h62a20 20 0 0 0 0-40 28 28 0 0 0-54-6A22 22 0 0 0 30 70z"/></svg>`,
  lock: `<svg viewBox="0 0 64 64" width="64" height="64" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round">
    <rect x="12" y="28" width="40" height="28" rx="5"/><path d="M20 28v-8a12 12 0 0 1 24 0v8"/><circle cx="32" cy="42" r="3" fill="currentColor"/></svg>`,
  xls: `<svg viewBox="0 0 64 64" width="96" height="96" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linejoin="round">
    <path d="M14 6h26l12 12v40H14z"/><path d="M40 6v12h12"/><path d="m24 30 14 18M38 30 24 48"/></svg>`,
};
const ST_ICONS = ["store", "vector", "search", "gauge", "judge"];

function header(root, n, title, sub) {
  const el = h(root, "div", "abs", "left:120px; top:118px; width:1680px",
    `<div class="kicker">Участок ${n}</div><div class="title">${title}</div>${sub ? `<div class="txt" style="margin-top:8px">${sub}</div>` : ""}`);
  return (t, a = 0) => rise(el, t, a);
}

// ---------- конвейер (обзор и финал)
function conveyor(root, y) {
  const g = h(root, "div", "abs", `left:0; top:${y}px; width:1920px; height:300px`);
  const belt = h(g, "div", "abs", "left:180px; top:200px; width:1560px; height:14px; border-radius:7px; background:var(--steel)");
  const items = [];
  for (let k = 0; k < 7; k++) items.push(h(g, "div", "abs", "top:176px; width:30px; height:22px; border-radius:4px; background:var(--card); border:2px solid var(--steel)"));
  const xs = [430, 650, 870, 1090, 1310];
  const st = STATIONS.map((n, i) => h(g, "div", "abs card",
    `left:${xs[i] - 95}px; top:0px; width:190px; height:170px; text-align:center; padding-top:16px; color:var(--steel)`,
    `<div style="position:absolute; left:-14px; top:-14px; width:40px; height:40px; border-radius:50%; background:var(--red); color:#fff; font-weight:700; font-size:22px; display:grid; place-items:center">${i + 1}</div>
     ${ICON[ST_ICONS[i]]}<div style="font-size:24px; font-weight:700; color:var(--ink); margin-top:10px">${n}</div>`));
  const inp = h(g, "div", "abs", "left:40px; top:20px; width:200px; text-align:center; color:var(--blue)",
    `${ICON.doc}<div style="font-size:22px; font-weight:600; color:var(--ink)">Реестр<br>и новое ППУ</div>`);
  const out = h(g, "div", "abs", "left:1560px; top:20px; width:260px; text-align:center; color:var(--green)",
    `${ICON.answer}<div style="font-size:22px; font-weight:600; color:var(--ink)">Ответ: было ли<br>и на что похоже</div>`);
  return { g, st, inp, out, belt, items, xs,
    update(t, { stAt = 0, ioAt = 0, lit = -1, run = true } = {}) {
      put(belt, { o: P(t, stAt, 0.6) });
      st.forEach((el, i) => {
        pop(el, t, stAt + 0.25 * i);
        el.style.borderColor = i === lit ? "var(--red)" : "";
        el.style.boxShadow = i === lit ? "0 0 0 6px rgba(192,23,46,0.15)" : "";
      });
      put(inp, { o: P(t, ioAt, 0.5), y: (1 - P(t, ioAt, 0.5)) * 20 });
      put(out, { o: P(t, ioAt + 0.3, 0.5), y: (1 - P(t, ioAt + 0.3, 0.5)) * 20 });
      items.forEach((el, k) => {
        const x = 200 + ((t * 110 + k * 230) % 1520);
        put(el, { o: run ? P(t, stAt + 0.8, 0.6) * (x > 1680 ? 0 : 1) : 0, x });
      });
    } };
}

// ---------- карта смыслов (векторы и поиск)
const CLUSTERS = [
  { name: "сварка", x: 0.22, y: 0.28 }, { name: "окраска", x: 0.8, y: 0.22 }, { name: "инструмент", x: 0.27, y: 0.76 },
  { name: "документы и учёт", x: 0.76, y: 0.74 }, { name: "охрана труда", x: 0.52, y: 0.48 },
];
const MAP_POINTS = (() => {
  const r = rng(7), pts = [];
  CLUSTERS.forEach((c, ci) => {
    for (let k = 0; k < 70; k++) {
      const a = r() * Math.PI * 2, d = Math.pow(r(), 0.7) * 0.11;
      pts.push({ x: c.x + Math.cos(a) * d * 1.2, y: c.y + Math.sin(a) * d, c: ci, k: r() });
    }
  });
  for (let k = 0; k < 60; k++) pts.push({ x: 0.05 + r() * 0.9, y: 0.06 + r() * 0.88, c: -1, k: r() });
  return pts;
})();
const CL_COLORS = ["#c0172e", "#b9780a", "#2b5fb8", "#7340ad", "#2c8452"];

function mapView(root, x, y, w, hgt) {
  const box = h(root, "div", "abs card", `left:${x}px; top:${y}px; width:${w}px; height:${hgt}px; overflow:hidden`);
  const cv = h(box, "canvas", "abs", `left:0; top:0; width:${w}px; height:${hgt}px`);
  cv.width = w * 2; cv.height = hgt * 2;
  const ctx = cv.getContext("2d");
  const labels = CLUSTERS.map((c, i) => h(box, "div", "abs", `left:${c.x * w - 120}px; top:${c.y * hgt - 104}px; width:240px; text-align:center; font-size:24px; font-weight:700; color:${CL_COLORS[i]}`, c.name));
  return {
    box, labels, w, hgt,
    px: (p) => [p.x * w, p.y * hgt],
    draw(t, { dotsAt = 0, dim = 0, near = null, nearK = 0 } = {}) {
      ctx.setTransform(2, 0, 0, 2, 0, 0);
      ctx.clearRect(0, 0, w, hgt);
      for (const p of MAP_POINTS) {
        const appear = P(t, dotsAt + (p.c < 0 ? 1.2 : p.c * 0.35) + p.k * 0.6, 0.4);
        if (appear <= 0) continue;
        let a = appear * (1 - dim * 0.75);
        let rad = 5;
        if (near) {
          const d = Math.hypot((p.x - near.x) * 1.3, p.y - near.y);
          if (d < near.r) { a = appear; rad = lerp(5, 8, nearK); } else a *= 1 - 0.6 * nearK;
        }
        ctx.globalAlpha = a;
        ctx.fillStyle = p.c < 0 ? "#9aa3ad" : CL_COLORS[p.c];
        ctx.beginPath(); ctx.arc(p.x * w, p.y * hgt, rad, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;
      labels.forEach((el, i) => put(el, { o: P(t, dotsAt + 0.35 * i + 0.3, 0.5) * (1 - dim * 0.6) }));
      return ctx;
    },
  };
}

// ---------- 0. вступление
scene("intro", (root, B) => {
  const title = h(root, "div", "abs center", "top:330px",
    `<img src="logo.png" style="height:72px; margin-bottom:56px"><div class="title" style="font-size:84px">Проверка ППУ на повторы</div>
     <div class="mid" style="color:var(--muted); margin-top:18px">как это устроено</div>`);
  const counter = h(root, "div", "abs center", "top:150px", `<div class="title num" style="font-size:120px; color:var(--steel)"></div><div class="mid" style="color:var(--muted)">предложений по улучшению в реестре</div>`);
  const num = counter.querySelector(".num");
  const cv = h(root, "canvas", "abs", "left:160px; top:430px; width:1600px; height:440px");
  cv.width = 3200; cv.height = 880;
  const ctx = cv.getContext("2d");
  const r = rng(3), cells = Array.from({ length: 11200 }, () => r());
  const card = h(root, "div", "abs card", "left:1180px; top:470px; width:520px; height:330px; padding:30px 34px; border-color:var(--red); border-width:3px",
    `<div class="label" style="color:var(--red)">Новое ППУ</div><div style="height:16px; width:80%; background:var(--paper-2); border-radius:8px; margin:22px 0 14px"></div>
     <div style="height:12px; width:92%; background:var(--paper-2); border-radius:6px; margin-bottom:10px"></div><div style="height:12px; width:70%; background:var(--paper-2); border-radius:6px"></div>
     <div style="position:absolute; right:34px; bottom:6px; font-size:170px; font-weight:700; color:var(--red); line-height:1">?</div>`);
  const q = h(root, "div", "abs", "left:220px; top:560px; width:880px", `<div class="big">А не было ли такого раньше?</div>`);
  return (t) => {
    put(title, { o: 1 - P(t, 1.9, 0.4, E.inOut), y: -P(t, 1.9, 0.4) * 20 });
    const b0 = B[0];
    const k = P(t, b0, 3.2, E.inOut);
    put(counter, { o: P(t, b0 - 0.2, 0.5) });
    num.textContent = Math.round(k * 11000).toLocaleString("ru-RU") + (k >= 1 ? "+" : "");
    ctx.setTransform(2, 0, 0, 2, 0, 0); ctx.clearRect(0, 0, 1600, 440);
    const dim = P(t, B[1], 0.8);
    const shown = Math.floor(k * cells.length);
    for (let i = 0; i < shown; i++) {
      const c = i % 160, rr = Math.floor(i / 160);
      ctx.globalAlpha = (0.35 + 0.5 * cells[i]) * (1 - 0.7 * dim);
      ctx.fillStyle = cells[i] > 0.97 ? "#c0172e" : "#3d4b59";
      ctx.fillRect(c * 10, rr * 6.3, 8, 4.6);
    }
    ctx.globalAlpha = 1;
    const kc = P(t, B[1] + 0.2, 0.8, E.back);
    put(card, { o: P(t, B[1] + 0.2, 0.4), x: (1 - kc) * 500, r: (1 - kc) * 6 });
    rise(q, t, B[1] + 1.4);
  };
});

// ---------- 1. проблема
scene("problem", (root, B) => {
  const left = h(root, "div", "abs", "left:120px; top:150px; width:760px",
    `<div class="kicker">Прочитать всё</div>
     <div class="big" style="margin-top:20px">11 000 карточек × 1 минута</div>
     <div class="big l2" style="margin-top:22px">= 183 часа</div>
     <div class="big l3" style="margin-top:22px; color:var(--red)">≈ 23 рабочих дня</div>
     <div class="txt l4" style="margin-top:22px">больше месяца, чтобы ответить на один вопрос</div>`);
  const [l2, l3, l4] = [".l2", ".l3", ".l4"].map((s) => left.querySelector(s));
  const right = h(root, "div", "abs", "left:1000px; top:150px; width:800px", `<div class="kicker">Искать по словам</div>`);
  const cardA = h(root, "div", "abs card", "left:1000px; top:240px; width:800px; padding:24px 30px",
    `<div class="label">ППУ из реестра</div><div class="mid" style="margin-top:6px">Треснули ручки напильников</div>`);
  const cardB = h(root, "div", "abs card", "left:1000px; top:390px; width:800px; padding:24px 30px",
    `<div class="label">Новое ППУ</div><div class="mid" style="margin-top:6px">Разваливаются рукоятки инструмента</div>`);
  const zero = h(root, "div", "abs", "left:1000px; top:545px; width:800px", `<span class="chip c-red" style="font-size:28px">общих слов: 0</span> <span class="txt" style="margin-left:12px">а проблема одна и та же</span>`);
  const search = h(root, "div", "abs card", "left:1000px; top:640px; width:800px; padding:18px 26px; display:flex; align-items:center; gap:18px",
    `<span style="color:var(--muted)">${ICON.search.replace('width="64" height="64"', 'width="40" height="40"')}</span><span class="mid mono q" style="font-size:30px"></span>`);
  const qEl = search.querySelector(".q");
  const miss = h(root, "div", "abs", "left:1000px; top:760px; width:800px", `<span class="chip c-red" style="font-size:28px">рукоятки инструмента - пропущено</span>`);
  return (t) => {
    rise(left.firstElementChild, t, B[0]);
    rise(left.children[1], t, B[0] + 0.5);
    rise(l2, t, B[0] + 2.4); rise(l3, t, B[0] + 3.6); rise(l4, t, B[0] + 4.6);
    rise(right, t, B[1]);
    rise(cardA, t, B[1] + 1.4); rise(cardB, t, B[1] + 3.0);
    pop(zero, t, B[1] + 6.8);
    rise(search, t, B[2] - 0.6);
    qEl.textContent = typed("ручки напильников", t, B[2] - 0.3, 30) + (P(t, B[2] - 0.3, 0.01) && Math.floor(t * 2) % 2 ? "|" : "");
    const hit = P(t, B[2] + 0.4, 0.4);
    cardA.style.borderColor = hit ? `rgba(44,132,82,${hit})` : "";
    cardB.style.opacity = 1 - 0.55 * hit;
    if (t < B[1] + 3.0) cardB.style.opacity = vis(t, B[1] + 3.0);
    pop(miss, t, B[2] + 0.8);
  };
});

// ---------- 2. обзор конвейера
scene("overview", (root, B) => {
  const ttl = h(root, "div", "abs center", "top:150px", `<div class="title">Завод по проверке ППУ</div>`);
  const cv = conveyor(root, 380);
  const note = h(root, "div", "abs center", "top:760px", `<div class="mid" style="color:var(--muted)">пять участков - пройдём по каждому</div>`);
  return (t) => {
    rise(ttl, t, B[0]);
    const lit = t > B[2] + 1.2 ? Math.floor((t - B[2] - 1.2) / 0.5) % 6 : -1;
    cv.update(t, { stAt: B[0] + 0.6, ioAt: B[1], lit: lit < 5 ? lit : -1 });
    rise(note, t, B[2]);
  };
});

// ---------- участок 1: склад
scene("st1", (root, B) => {
  const hd = header(root, 1, "Склад");
  const rows = [
    ["1201", "Ручки для напильников", "В цехе №12 ручки…", "Новые ручки…", "Изготовить…"],
    ["1218", "Подставка для ног сварщика", "Устают ноги…", "Сделана подставка…", "Сварить…"],
    ["1222", "Замена ручек у напильников", "В цехе №5 ручки…", "Деревянные ручки…", "См.вложение"],
    ["1240", "Пов-ие пр-ти уч. 5", "Детали моют вручную…", "Моечная машина…", "Установить…"],
    ["1251", "Вытяжка на сварочном посту", "Дым на посту…", "Местная вытяжка…", "Смонтировать…"],
  ];
  const table = h(root, "div", "abs card", "left:120px; top:300px; width:840px; padding:0; overflow:hidden; font-size:19px",
    `<div style="display:grid; grid-template-columns:70px 250px 180px 170px 170px; background:#2c6e49; color:#fff; font-weight:600; padding:12px 16px">
      <span>№</span><span>Наименование</span><span>До улучшения</span><span>После улучш.</span><span>Предложения</span></div>` +
    rows.map((r, i) => `<div class="row r${i}" style="display:grid; grid-template-columns:70px 250px 180px 170px 170px; padding:12px 16px; border-top:1px solid var(--rule); white-space:nowrap; overflow:hidden">
      ${r.map((c) => `<span style="overflow:hidden; text-overflow:ellipsis; padding-right:10px">${c}</span>`).join("")}</div>`).join(""));
  const xlsLabel = h(root, "div", "abs", "left:120px; top:250px", `<span class="label">Реестр ППУ.xlsx</span>`);
  const row2 = table.querySelector(".r2");
  const card = h(root, "div", "abs card", "left:1040px; top:250px; width:760px; padding:26px 32px",
    `<div class="label">№ 1222</div><div class="mid">Замена ручек у напильников</div>
     <div style="display:grid; gap:14px; margin-top:20px">
      <div class="part p1" style="border-left:6px solid var(--blue); padding:6px 16px"><div class="label" style="color:var(--blue)">Проблема · до улучшения</div>
        <div class="txt" style="font-size:25px">В <span class="place">цехе №5</span> ручки напильников треснули, можно поранить руки.</div></div>
      <div class="part p2" style="border-left:6px solid var(--green); padding:6px 16px"><div class="label" style="color:var(--green)">Решение · после улучшения и предложения</div>
        <div class="txt" style="font-size:25px">Новые деревянные ручки с кольцами. <span class="stub" style="color:var(--red)">См.вложение</span></div></div>
     </div>`);
  const [p1, p2] = [".p1", ".p2"].map((s) => card.querySelector(s));
  const stub = card.querySelector(".stub");
  const place = card.querySelector(".place");
  const clean = h(root, "div", "abs card", "left:1040px; top:640px; width:760px; padding:20px 30px",
    `<div class="label">Чистка текста</div>
     <div class="txt" style="margin-top:6px"><span class="mono" style="color:var(--red)">Пов-ие пр-ти уч. 5</span> → Повышение производительности участка 5</div>
     <div class="txt"><span class="mono" style="color:var(--red)">См.вложение</span> → заглушка убрана</div>`);
  const chip = h(root, "div", "abs", "left:1040px; top:640px; width:760px",
    `<div class="card" style="padding:20px 30px"><div class="label">Место</div>
     <div style="display:flex; gap:16px; align-items:center; margin-top:10px"><span class="chip c-amber" style="font-size:28px">цех 5</span>
     <span class="txt">поможет отличить повтор от той же идеи в другом цехе</span></div></div>`);
  return (t) => {
    hd(t, B[0]);
    rise(xlsLabel, t, B[1]); rise(table, t, B[1]);
    const lift = P(t, B[1] + 2.0, 0.6);
    row2.style.background = lift ? `rgba(192,23,46,${0.12 * lift})` : "";
    rise(card, t, B[1] + 2.6, Infinity, 0);
    put(card, { o: P(t, B[1] + 2.6, 0.5), x: (1 - P(t, B[1] + 2.6, 0.7)) * -200 });
    rise(p1, t, B[1] + 4.6); rise(p2, t, B[1] + 6.8);
    rise(clean, t, B[2], B[3] - 0.2);
    stub.style.textDecoration = P(t, B[2] + 2.5, 0.1) ? "line-through" : "none";
    stub.style.opacity = 1 - 0.7 * P(t, B[2] + 2.5, 0.6);
    rise(chip, t, B[3]);
    const pk = P(t, B[3] + 0.6, 0.4);
    place.style.background = pk ? `rgba(185,120,10,${0.22 * pk})` : "";
    place.style.borderRadius = "6px";
  };
});

// ---------- участок 2: векторы
scene("st2", (root, B) => {
  const hd = header(root, 2, "Векторы: текст превращается в числа");
  const map = mapView(root, 120, 290, 900, 600);
  const phrases = [
    { text: "Треснули ручки напильников", x: 0.23, y: 0.72, c: "c-blue", dx: -60, dy: -56 },
    { text: "Разваливаются рукоятки инструмента", x: 0.33, y: 0.8, c: "c-blue", dx: -40, dy: 22 },
    { text: "Покраска корпуса", x: 0.82, y: 0.2, c: "c-amber", dx: -190, dy: -56 },
  ];
  const chips = phrases.map((p) => h(root, "div", `abs chip ${p.c}`, "left:0; top:0; font-size:22px", p.text));
  const lines = h(root, "svg", "abs", "left:120px; top:290px; width:900px; height:600px; pointer-events:none");
  lines.setAttribute("viewBox", "0 0 900 600");
  lines.innerHTML = `<line class="ln1" stroke="#2b5fb8" stroke-width="4"/><line class="ln2" stroke="#9aa3ad" stroke-width="3" stroke-dasharray="10 9"/>
    <text class="tx1" font-size="26" font-weight="700" fill="#2b5fb8" stroke="#fff" stroke-width="7" paint-order="stroke">рядом</text><text class="tx2" font-size="26" font-weight="700" fill="#6c7682" stroke="#fff" stroke-width="7" paint-order="stroke">далеко</text>`;
  const [ln1, ln2, tx1, tx2] = [".ln1", ".ln2", ".tx1", ".tx2"].map((s) => lines.querySelector(s));
  // вектор: 1024 числа
  const vec = h(root, "div", "abs", "left:1090px; top:290px; width:720px",
    `<div class="big"><span class="dims">2</span> направления → <span style="color:var(--red)">1024</span></div>
     <div class="txt" style="margin-top:8px">адрес точки = вектор, 1024 числа</div>`);
  const vcv = h(root, "canvas", "abs", "left:1090px; top:420px; width:704px; height:220px");
  vcv.width = 1408; vcv.height = 440;
  const vctx = vcv.getContext("2d");
  const vr = rng(11), vals = Array.from({ length: 1024 }, () => (vr() + vr() + vr() - 1.5) / 1.5);
  const nums = h(root, "div", "abs mono", "left:1090px; top:652px; width:720px; font-size:22px; color:var(--ink-2)",
    `[ 0.021, −0.113, 0.087, 0.004, −0.052, … ]`);
  const model = h(root, "div", "abs card", "left:1090px; top:700px; width:720px; padding:20px 28px",
    `<div style="display:flex; align-items:baseline; gap:16px"><span class="mid mono">bge-m3</span><span class="small">модель, которая переводит текст в вектор</span></div>
     <div class="txt" style="font-size:24px; margin-top:8px">обучена на огромном количестве текстов на сотне языков: похожие ситуации → похожий смысл</div>`);
  // угол между стрелками
  const angle = h(root, "svg", "abs", "left:200px; top:280px; width:1520px; height:640px");
  angle.setAttribute("viewBox", "0 0 1520 640");
  angle.innerHTML = `
    <circle cx="160" cy="560" r="9" fill="#1b232c"/>
    <line class="aA" x1="160" y1="560" stroke="#2b5fb8" stroke-width="7" stroke-linecap="round"/>
    <line class="aB" x1="160" y1="560" stroke="#2b5fb8" stroke-width="7" stroke-linecap="round" opacity=".65"/>
    <line class="aC" x1="160" y1="560" stroke="#9aa3ad" stroke-width="7" stroke-linecap="round"/>
    <path class="arc1" fill="none" stroke="#2b5fb8" stroke-width="4"/><path class="arc2" fill="none" stroke="#9aa3ad" stroke-width="4" stroke-dasharray="8 8"/>
    <text class="lA" font-size="28" font-weight="700" fill="#2b5fb8">Треснули ручки напильников</text>
    <text class="lB" font-size="28" font-weight="700" fill="#2b5fb8" opacity=".75">Разваливаются рукоятки инструмента</text>
    <text class="lC" font-size="28" font-weight="700" fill="#6c7682">Покраска корпуса</text>
    <text class="k1" font-size="30" font-weight="700" fill="#2b5fb8">маленький угол - смысл близко</text>
    <text class="k2" font-size="30" font-weight="700" fill="#6c7682">большой угол - далеко</text>`;
  const q = (s) => angle.querySelector(s);
  const formula = h(root, "div", "abs", "left:1060px; top:300px; width:700px", `<div class="big">Похожесть = угол<br>между стрелками</div>`);
  // весь реестр - один раз
  const views = ["название", "проблема", "решение", "всё вместе"];
  const store = h(root, "div", "abs", "left:120px; top:300px; width:1680px",
    `<div class="big">11 000 ППУ × 4 вектора ≈ 44 000 векторов</div>
     <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:24px; margin-top:34px">${views.map((v, i) => `
      <div class="card vv" style="padding:20px 24px"><div class="mid" style="font-size:28px">${v}</div>
       <div style="height:26px; margin-top:14px; border-radius:6px; background:linear-gradient(90deg, ${["#c0172e,#2b5fb8,#b9780a,#2c8452,#7340ad,#c0172e", "#2b5fb8,#7340ad,#2c8452,#c0172e,#b9780a", "#2c8452,#b9780a,#2b5fb8,#7340ad,#c0172e", "#7340ad,#c0172e,#2c8452,#2b5fb8,#b9780a"][i]}); opacity:.55"></div></div>`).join("")}</div>
     <div style="display:flex; gap:40px; margin-top:44px; align-items:center">
      <span class="chip c-green once" style="font-size:28px">считаются один раз</span>
      <span class="chip c-blue upd" style="font-size:28px">при обновлении - только новые и изменённые</span></div>`);
  const vv = [...store.querySelectorAll(".vv")];
  const [once, upd] = [".once", ".upd"].map((s) => store.querySelector(s));
  return (t) => {
    hd(t, B[0]);
    const mapOut = vis(t, -1, B[5] - 0.2);
    map.box.style.opacity = mapOut * P(t, B[1] - 0.2, 0.5);
    map.box.style.visibility = map.box.style.opacity > 0 ? "visible" : "hidden";
    map.draw(t, { dotsAt: B[1] });
    phrases.forEach((p, i) => {
      const a = B[2] + i * 1.6, k = P(t, a, 0.9, E.inOut);
      const [px, py] = map.px(p);
      const sx = 1100, sy = 330 + i * 70;
      const el = chips[i];
      const x = lerp(sx, 120 + px + p.dx, k), y = lerp(sy, 290 + py + p.dy, k);
      put(el, { o: vis(t, a - 0.4, B[3] - 0.1) * mapOut, x, y, s: lerp(1, 0.86, k) });
    });
    const [ax, ay] = map.px(phrases[0]), [bx, by] = map.px(phrases[1]), [cx, cy] = map.px(phrases[2]);
    const l1 = P(t, B[2] + 3.6, 0.6), l2 = P(t, B[2] + 5.8, 0.8);
    lines.style.opacity = mapOut;
    ln1.setAttribute("x1", ax); ln1.setAttribute("y1", ay); ln1.setAttribute("x2", lerp(ax, bx, l1)); ln1.setAttribute("y2", lerp(ay, by, l1));
    ln2.setAttribute("x1", bx); ln2.setAttribute("y1", by); ln2.setAttribute("x2", lerp(bx, cx, l2)); ln2.setAttribute("y2", lerp(by, cy, l2));
    ln1.style.opacity = l1 ? 1 : 0; ln2.style.opacity = l2 ? 1 : 0;
    tx1.setAttribute("x", ax - 150); tx1.setAttribute("y", ay + 30); tx1.style.opacity = P(t, B[2] + 4.0, 0.4);
    tx2.setAttribute("x", (bx + cx) / 2 + 30); tx2.setAttribute("y", (by + cy) / 2 + 40); tx2.style.opacity = P(t, B[2] + 6.4, 0.4);
    // вектор
    rise(vec, t, B[3], B[5] - 0.2);
    vec.querySelector(".dims").textContent = t > B[3] + 2.0 ? "не 2" : "2";
    const vk = P(t, B[3] + 2.4, 2.0, E.inOut);
    vcv.style.opacity = vis(t, B[3] + 2.3, B[5] - 0.2);
    vctx.setTransform(2, 0, 0, 2, 0, 0); vctx.clearRect(0, 0, 704, 220);
    const n = Math.floor(vk * 1024);
    for (let i = 0; i < n; i++) {
      const v = vals[i], c = i % 64, r = Math.floor(i / 64);
      vctx.fillStyle = v >= 0 ? `rgba(43,95,184,${0.15 + 0.85 * Math.min(1, v)})` : `rgba(192,23,46,${0.15 + 0.85 * Math.min(1, -v)})`;
      vctx.fillRect(c * 11, r * 13.7, 9.5, 12);
    }
    rise(nums, t, B[3] + 4.0, B[4] - 0.1);
    rise(model, t, B[4], B[5] - 0.2);
    // угол
    const ak = P(t, B[5], 0.9, E.inOut), ao = vis(t, B[5], B[6] - 0.2);
    angle.style.opacity = ao; formula.style.opacity = ao;
    put(formula, { o: ao, y: (1 - P(t, B[5] + 0.3, 0.6)) * 20 });
    const L = 560 * ak, ang = (deg) => [160 + Math.cos(deg * Math.PI / 180) * L, 560 - Math.sin(deg * Math.PI / 180) * L];
    const [Ax, Ay] = ang(20), [Bx, By] = ang(30), [Cx, Cy] = ang(80);
    for (const [cls, X, Y] of [[".aA", Ax, Ay], [".aB", Bx, By], [".aC", Cx, Cy]]) { q(cls).setAttribute("x2", X); q(cls).setAttribute("y2", Y); }
    const arc = (r, a1, a2) => { const p = (d) => [160 + Math.cos(d * Math.PI / 180) * r, 560 - Math.sin(d * Math.PI / 180) * r];
      const [x1, y1] = p(a1), [x2, y2] = p(a2); return `M${x1} ${y1} A${r} ${r} 0 0 0 ${x2} ${y2}`; };
    q(".arc1").setAttribute("d", arc(300, 20, 30)); q(".arc2").setAttribute("d", arc(200, 30, 80));
    q(".arc1").style.opacity = P(t, B[5] + 1.2, 0.4); q(".arc2").style.opacity = P(t, B[5] + 2.0, 0.4);
    const lab = (cls, X, Y, dx, dy) => { q(cls).setAttribute("x", X + dx); q(cls).setAttribute("y", Y + dy); q(cls).style.opacity = P(t, B[5] + 0.7, 0.4); };
    lab(".lA", Ax, Ay, 18, 26); lab(".lB", Bx, By, 18, -10); lab(".lC", Cx, Cy, 18, 0);
    q(".k1").setAttribute("x", 520); q(".k1").setAttribute("y", 470); q(".k1").style.opacity = P(t, B[5] + 1.4, 0.4);
    q(".k2").setAttribute("x", 250); q(".k2").setAttribute("y", 230); q(".k2").style.opacity = P(t, B[5] + 2.2, 0.4);
    // весь реестр
    put(store, { o: P(t, B[6], 0.5) });
    store.firstElementChild.style.opacity = P(t, B[6], 0.5);
    vv.forEach((el, i) => pop(el, t, B[6] + 1.0 + 0.4 * i));
    pop(once, t, B[6] + 4.4); pop(upd, t, B[6] + 6.6);
  };
});

// ---------- участок 3: поиск
scene("st3", (root, B) => {
  const hd = header(root, 3, "Поиск: по смыслу и по словам");
  const map = mapView(root, 120, 290, 820, 470);
  const star = h(root, "div", "abs", "left:0; top:0; width:44px; height:44px",
    `<svg viewBox="0 0 44 44" width="44" height="44"><path d="M22 2l6 13 14 2-10 10 3 14-13-7-13 7 3-14L2 17l14-2z" fill="#c0172e" stroke="#fff" stroke-width="2"/></svg>`);
  const ring = h(root, "div", "abs", "left:0; top:0; border:4px solid #c0172e; border-radius:50%; opacity:.7");
  const NEW = { x: 0.29, y: 0.75 };
  const weights = h(root, "div", "abs", "left:120px; top:780px; width:820px",
    `<div class="label">Из чего складывается сходство по смыслу</div>
     <div style="display:flex; height:46px; margin-top:8px; border-radius:8px; overflow:hidden; font-size:20px; font-weight:600; color:#fff">
      <div style="flex:40; background:#2b5fb8; display:grid; place-items:center">весь текст 40%</div>
      <div style="flex:20; background:#5a80c6; display:grid; place-items:center">название 20%</div>
      <div style="flex:20; background:#7d9bd2; display:grid; place-items:center">проблема 20%</div>
      <div style="flex:20; background:#9db4dd; display:grid; place-items:center">решение 20%</div></div>`);
  const words = h(root, "div", "abs card", "left:1010px; top:290px; width:790px; padding:22px 30px",
    `<div class="label">По словам: начальная форма</div>
     ${[["ручек", "ручка"], ["ручкой", "ручка"], ["ручки", "ручка"], ["треснули", "треснуть"]].map(([a, b], i) =>
      `<div class="w w${i} txt" style="margin-top:6px"><span class="mono" style="color:var(--muted)">${a}</span> → <b style="color:var(--ink)">${b}</b></div>`).join("")}
     <div class="stop" style="margin-top:14px; display:flex; gap:10px; align-items:center"><span class="small">служебные:</span>
      ${["и", "в", "на", "для", "по"].map((w) => `<span class="chip c-grey" style="text-decoration:line-through">${w}</span>`).join("")}</div>`);
  const ws = [...words.querySelectorAll(".w")], stop = words.querySelector(".stop");
  const rare = h(root, "div", "abs card", "left:1010px; top:620px; width:790px; padding:22px 30px",
    `<div class="label">Вес слова: редкое важнее частого</div>
     <div style="display:grid; grid-template-columns:200px 1fr; gap:12px 18px; align-items:center; margin-top:12px">
      <span class="mid" style="font-size:28px">работа</span><div style="height:22px; border-radius:6px; background:var(--grey-wash)"><div class="b1" style="height:100%; width:0; border-radius:6px; background:#9aa3ad"></div></div>
      <span class="mid" style="font-size:28px">напильник</span><div style="height:22px; border-radius:6px; background:var(--grey-wash)"><div class="b2" style="height:100%; width:0; border-radius:6px; background:var(--amber)"></div></div></div>
     <div class="small" style="margin-top:10px">встречается почти везде - почти ничего не говорит</div>`);
  const [b1, b2] = [".b1", ".b2"].map((s) => rare.querySelector(s));
  const exact = h(root, "div", "abs", "left:1010px; top:620px; width:790px",
    `<div class="card" style="padding:22px 30px"><div class="label">Ловит точные совпадения</div>
     <div style="display:flex; flex-wrap:wrap; gap:12px; margin-top:12px">${["SCV-400", "каплеструйный принтер", "цех 5", "инв. № 4410"].map((w) =>
      `<span class="chip c-amber mono" style="font-size:26px">${w}</span>`).join("")}</div></div>`);
  // слияние двух списков
  const A = ["№ 1201", "№ 1222", "№ 1180", "№ 1305", "№ 1090"], Bw = ["№ 1222", "№ 1412", "№ 1201", "№ 1377", "№ 1180"];
  const M = ["№ 1222", "№ 1201", "№ 1180", "№ 1412", "№ 1305"];
  const merge = h(root, "div", "abs", "left:120px; top:290px; width:1680px; height:600px");
  const col = (x, title, items, cls) => h(merge, "div", "abs", `left:${x}px; top:0; width:360px`,
    `<div class="mid" style="font-size:28px; margin-bottom:14px">${title}</div>` + items.map((it, i) =>
      `<div class="card it ${cls}" data-id="${it}" style="padding:12px 18px; margin-bottom:12px; display:flex; gap:16px; font-size:26px; font-weight:600">
       <span style="color:var(--muted); width:28px">${i + 1}</span>${it}</div>`).join(""));
  const cA = col(0, "По смыслу", A, "ca"), cB = col(460, "По словам", Bw, "cb"), cM = col(1180, "Итог", M, "cm");
  const arrow = h(merge, "div", "abs", "left:880px; top:200px; width:260px; text-align:center",
    `<div style="font-size:80px; color:var(--red); line-height:1">→</div><div class="small">высоко в обоих списках - наверх</div>`);
  const hundred = h(merge, "div", "abs", "left:1180px; top:500px; width:520px", `<span class="chip c-red" style="font-size:28px">дальше идёт первая сотня</span>`);
  return (t) => {
    hd(t, B[0]);
    const mo = vis(t, B[1] - 0.3, B[5] - 0.2);
    map.box.style.opacity = mo;
    const nk = P(t, B[1] + 3.2, 0.8);
    map.draw(t, { dotsAt: B[1] - 2.2, near: { x: NEW.x, y: NEW.y, r: 0.14 }, nearK: nk });
    const [sx, sy] = map.px(NEW);
    const drop = P(t, B[1] + 1.2, 0.8, E.back);
    put(star, { o: P(t, B[1] + 1.2, 0.3) * mo, x: 120 + sx - 22, y: 290 + sy - 22 - (1 - drop) * 200 });
    const rr = 0.14 * 820 * P(t, B[1] + 3.2, 1.0);
    ring.style.width = ring.style.height = rr * 2 + "px";
    put(ring, { o: (rr > 1 ? 0.7 : 0) * mo, x: 120 + sx - rr, y: 290 + sy - rr });
    rise(weights, t, B[1] + 6.0, B[5] - 0.2);
    rise(words, t, B[2], B[5] - 0.2);
    ws.forEach((el, i) => rise(el, t, B[2] + 3.2 + 0.7 * i, Infinity, 12));
    rise(stop, t, B[2] + 7.4, Infinity, 12);
    rise(rare, t, B[3], B[4] - 0.2);
    b1.style.width = 12 * P(t, B[3] + 2.4, 1.0) + "%";
    b2.style.width = 92 * P(t, B[3] + 6.0, 1.0) + "%";
    rise(exact, t, B[4], B[5] - 0.2);
    put(merge, { o: P(t, B[5], 0.5) });
    rise(cA, t, B[5] + 0.3); rise(cB, t, B[5] + 0.9); rise(arrow, t, B[5] + 3.2); rise(cM, t, B[5] + 3.8);
    const hlk = P(t, B[5] + 2.2, 0.4);
    merge.querySelectorAll(".it").forEach((el) => {
      const both = A.includes(el.dataset.id) && Bw.includes(el.dataset.id) && el.dataset.id !== "№ 1180";
      el.style.borderColor = both && hlk ? "var(--red)" : "";
    });
    pop(hundred, t, B[5] + 6.4);
  };
});

// ---------- участок 4: быстрый вывод
scene("st4", (root, B) => {
  const hd = header(root, 4, "Быстрый вывод: пороги");
  const X0 = 200, X1 = 1720, sw = X1 - X0, Y = 330;
  const zones = [[0, 0.42, "далеко", "#d9d5cc", "var(--muted)"], [0.42, 0.62, "похоже", "#c9d7ef", "var(--blue)"], [0.62, 1, "повтор", "#f2c8cc", "var(--red)"]];
  const scale = h(root, "div", "abs", `left:${X0}px; top:${Y}px; width:${sw}px; height:150px`,
    `<div class="label" style="margin-bottom:10px">близость</div>
     <div style="position:relative; height:44px; border-radius:10px; overflow:hidden">${zones.map(([a, b, n, c]) =>
      `<div style="position:absolute; left:${a * 100}%; width:${(b - a) * 100}%; top:0; bottom:0; background:${c}"></div>`).join("")}
      <div class="gray" style="position:absolute; left:56%; width:14%; top:0; bottom:0; background:repeating-linear-gradient(45deg, rgba(60,70,80,.35) 0 8px, transparent 8px 16px)"></div></div>
     <div style="position:relative; height:40px; margin-top:8px">${zones.map(([a, b, n, , ink]) =>
      `<div style="position:absolute; left:${a * 100}%; width:${(b - a) * 100}%; text-align:center; font-size:26px; font-weight:700; color:${ink}">${n}</div>`).join("")}</div>`);
  const gray = scale.querySelector(".gray");
  const marker = h(root, "div", "abs", "left:0; top:0; width:4px; height:70px; background:var(--ink); border-radius:2px");
  const flag = h(root, "div", "abs", `left:${X0 + 0.63 * sw - 120}px; top:${Y + 160}px; width:240px; text-align:center`,
    `<span class="chip" style="border:2px dashed var(--muted); color:var(--ink-2); background:var(--card); font-size:26px">Спорный случай</span>`);
  const colStyle = "width:500px; padding:22px 28px";
  const c1 = h(root, "div", "abs card", `left:${X0}px; top:520px; ${colStyle}`,
    `<span class="chip c-red">повтор</span><div class="txt" style="margin-top:12px">та же идея, место то же или не указано</div>`);
  const c2 = h(root, "div", "abs card", `left:${X0 + 510}px; top:520px; ${colStyle}`,
    `<span class="chip c-amber">другое подразделение</span><div style="display:flex; gap:12px; align-items:center; margin-top:14px">
     <span class="chip c-grey">цех 5</span><span style="font-size:30px">⇄</span><span class="chip c-grey">цех 12</span></div>
     <div class="small" style="margin-top:8px">та же идея в другом цехе - тиражирование</div>`);
  const c3 = h(root, "div", "abs card", `left:${X0 + 1020}px; top:520px; ${colStyle}`,
    `<span class="chip c-violet">та же проблема, другое решение</span>
     <div style="display:grid; grid-template-columns:130px 1fr; gap:8px 12px; align-items:center; margin-top:14px; font-size:22px">
      <span>проблемы</span><div style="height:16px; background:var(--grey-wash); border-radius:5px"><div class="pb" style="height:100%; width:0; background:var(--violet); border-radius:5px"></div></div>
      <span>решения</span><div style="height:16px; background:var(--grey-wash); border-radius:5px"><div class="sb" style="height:100%; width:0; background:#9aa3ad; border-radius:5px"></div></div></div>`);
  const [pb, sb] = [".pb", ".sb"].map((s) => c3.querySelector(s));
  const ladder = h(root, "div", "abs", `left:${X0}px; top:520px; width:1520px; display:flex; gap:30px; align-items:center`,
    `<div style="display:flex; gap:12px; align-items:center">${["c-red|повтор", "c-amber|другое подразделение", "c-violet|та же проблема", "c-blue|похоже"].map((x, i) => {
      const [c, n] = x.split("|"); return `${i ? '<span style="font-size:26px; color:var(--muted)">›</span>' : ""}<span class="chip ${c}">${n}</span>`; }).join("")}</div>
     <div class="txt">вывод - по самому серьёзному</div>`);
  const uniq = h(root, "div", "abs card", `left:${X0}px; top:630px; width:900px; padding:22px 30px`,
    `<div class="mid" style="color:var(--red)">Такое ППУ уже было</div>
     <div style="height:10px; width:480px; background:var(--grey-wash); border-radius:5px; margin:14px 0 8px"><div class="ub" style="height:100%; width:18%; background:var(--red); border-radius:5px"></div></div>
     <div class="txt" style="font-size:24px">Уникальность <b>18%</b> = насколько новое ППУ далеко от ближайшего</div>`);
  const calib = h(root, "div", "abs", `left:${X0}px; top:600px; width:1520px; display:grid; grid-template-columns:1fr 1fr 1fr; gap:24px`,
    ["Повтор", "Не связаны", "Та же проблема, другое решение"].map((lab, i) => `
     <div class="card cal" style="padding:18px 24px"><div style="display:flex; gap:10px"><div style="flex:1; height:54px; background:var(--paper-2); border-radius:8px"></div>
      <div style="flex:1; height:54px; background:var(--paper-2); border-radius:8px"></div></div>
      <div style="margin-top:12px; display:flex; align-items:center; gap:10px"><span class="chip c-green" style="font-size:22px">✓ ${lab}</span><span class="small">отметил человек</span></div></div>`).join(""));
  const cals = [...calib.querySelectorAll(".cal")];
  return (t) => {
    hd(t, B[0]);
    rise(scale, t, B[1] - 0.2);
    // маркер едет по шкале
    let pos = lerp(0.2, 0.86, P(t, B[1] + 2.0, 2.2, E.inOut));
    pos = lerp(pos, 0.66, P(t, B[5], 1.2, E.inOut));
    put(marker, { o: P(t, B[1] + 1.6, 0.4), x: X0 + pos * sw - 2, y: Y + 30 });
    gray.style.opacity = P(t, B[5] + 0.4, 0.6);
    pop(flag, t, B[5] + 3.0);
    rise(c1, t, B[1] + 4.0, B[4] - 0.2); rise(c2, t, B[2], B[4] - 0.2); rise(c3, t, B[3], B[4] - 0.2);
    pb.style.width = 88 * P(t, B[3] + 0.8, 0.8) + "%"; sb.style.width = 26 * P(t, B[3] + 1.6, 0.8) + "%";
    rise(ladder, t, B[4], B[6] - 0.2); rise(uniq, t, B[4] + 4.6, B[6] - 0.2);
    put(calib, { o: P(t, B[6], 0.4) });
    cals.forEach((el, i) => rise(el, t, B[6] + 1.6 + 0.8 * i));
  };
});

// ---------- участок 5: судья
scene("st5", (root, B) => {
  const hd = header(root, 5, "Судья: большая языковая модель");
  const vs = h(root, "div", "abs", "left:120px; top:300px; width:1680px; display:flex; gap:30px; align-items:center",
    `<div class="card" style="padding:24px 32px; width:560px"><div class="mid">Векторы</div>
      <div class="txt" style="margin-top:8px"><span style="color:var(--green)">✓</span> чувствуют тему</div>
      <div class="txt"><span style="color:var(--red)">?</span> не всегда видят суть</div></div>
     <div style="font-size:70px; color:var(--muted)">→</div>
     <div class="card" style="padding:24px 32px; width:660px; border-color:var(--red)"><div class="mid">Большая языковая модель</div>
      <div class="txt" style="margin-top:8px">по-английски <b class="mono">LLM</b></div></div>`);
  const phone = h(root, "div", "abs", "left:160px; top:290px; width:340px; height:600px; border-radius:46px; background:#1b232c; padding:16px",
    `<div style="background:#f6f4f0; border-radius:34px; height:100%; position:relative; overflow:hidden">
      <div style="position:absolute; left:20px; right:20px; top:150px; padding:16px 18px; background:#fff; border-radius:18px; font-size:26px" class="msg"></div>
      <div style="position:absolute; left:0; right:0; bottom:0; height:240px; background:#dcd8d0">
       <div class="sug" style="display:flex; justify-content:space-around; padding:14px 6px; font-size:24px; color:var(--ink); border-bottom:1px solid #c9c2b5">
        <b style="color:var(--blue)">минут</b><span>секунд</span><span>дней</span></div>
       <div style="display:grid; grid-template-columns:repeat(8,1fr); gap:6px; padding:12px">${"йцукенгшщзхфывапролджэячсмитьб".slice(0, 24).split("").map((c) =>
        `<span style="background:#f6f4f0; border-radius:6px; text-align:center; padding:8px 0; font-size:18px">${c}</span>`).join("")}</div></div></div>`);
  const msg = phone.querySelector(".msg"), sug = phone.querySelector(".sug");
  const lib = h(root, "canvas", "abs", "left:600px; top:300px; width:620px; height:420px");
  lib.width = 1240; lib.height = 840;
  const lctx = lib.getContext("2d");
  const br = rng(5), books = Array.from({ length: 900 }, () => [br(), br(), br()]);
  const libText = h(root, "div", "abs", "left:1260px; top:330px; width:540px",
    `<div class="mid">прочитала гигантскую библиотеку текстов</div>
     <div class="txt step2" style="margin-top:20px">продолжает фразу → <b style="color:var(--red)">выполняет задания</b></div>`);
  const step2 = libText.querySelector(".step2");
  const qwen = h(root, "div", "abs card", "left:600px; top:740px; width:1200px; padding:20px 30px; display:flex; align-items:center; gap:30px",
    `<span class="mid mono">Qwen</span><span class="big num" style="color:var(--steel)">35 000 000 000</span><span class="txt">параметров - настроечных чисел</span>`);
  const qnum = qwen.querySelector(".num");
  const PROMPT = "Ты эксперт комиссии по ППУ. Вот новое ППУ и найденные в реестре. Для каждого определи связь: повтор, другое подразделение, та же проблема - другое решение, похоже, не связаны. Объясни в нескольких словах.";
  const task = h(root, "div", "abs card", "left:120px; top:290px; width:1000px; height:330px; padding:26px 32px",
    `<div class="label">Задание судье</div><div class="txt mono pt" style="font-size:24px; margin-top:10px; line-height:1.5"></div>`);
  const pt = task.querySelector(".pt");
  const judgeBox = h(root, "div", "abs card", "left:1340px; top:300px; width:460px; height:300px; display:grid; place-items:center; text-align:center; border-color:var(--steel); border-width:3px",
    `<div style="color:var(--steel)">${ICON.judge.replace('width="64" height="64"', 'width="110" height="110"')}<div class="mid">Судья</div></div>`);
  const batch = Array.from({ length: 12 }, (_, i) => h(root, "div", "abs card", "left:0; top:0; width:120px; height:64px; padding:8px 10px; font-size:18px; font-weight:600",
    `№ ${1201 + i * 17}`));
  const batchNote = h(root, "div", "abs", "left:120px; top:660px; width:1100px",
    `<span class="chip c-blue" style="font-size:26px">по 4 за раз</span> <span class="chip c-green" style="font-size:26px; margin-left:10px">тексты целиком, без обрезки</span>`);
  const slow = h(root, "div", "abs", "left:120px; top:660px; width:1680px; display:flex; gap:36px; align-items:center",
    `<div class="card" style="padding:16px 34px; background:var(--blue); color:#fff; border-color:var(--blue); font-size:30px; font-weight:700">Проверить подробнее</div>
     <div class="mid tm" style="color:var(--steel)"></div><div class="txt">от десятков секунд до нескольких минут</div>`);
  const tm = slow.querySelector(".tm");
  const answer = h(root, "div", "abs card", "left:120px; top:660px; width:1680px; padding:22px 30px; display:flex; gap:24px; align-items:center",
    `<span class="chip c-red" style="font-size:28px">повтор</span><span class="mid">«та же подставка для ног»</span>
     <span class="txt" style="margin-left:auto">решение принимает <b>комиссия</b></span>`);
  return (t) => {
    hd(t, B[0]);
    rise(vs, t, B[1], B[2] - 0.2);
    put(phone, { o: vis(t, B[2] - 0.1, B[5] - 0.2), y: (1 - P(t, B[2] - 0.1, 0.6)) * 40 });
    msg.textContent = typed("Буду через пять", t, B[2] + 0.8, 12) + (Math.floor(t * 2) % 2 ? "|" : "");
    sug.style.opacity = P(t, B[2] + 2.6, 0.4);
    sug.firstElementChild.style.background = P(t, B[2] + 3.6, 0.2) ? "#e2eaf7" : "";
    // библиотека
    const lk = P(t, B[3], 4.0, E.inOut), lo = vis(t, B[3], B[5] - 0.2);
    lib.style.opacity = lo;
    lctx.setTransform(2, 0, 0, 2, 0, 0); lctx.clearRect(0, 0, 620, 420);
    const nb = Math.floor(lk * books.length);
    for (let i = 0; i < nb; i++) {
      const [a, b, c] = books[i], col = i % 60, row = Math.floor(i / 60);
      lctx.fillStyle = ["#3d4b59", "#c0172e", "#2b5fb8", "#b9780a", "#2c8452", "#7340ad"][Math.floor(a * 6)];
      lctx.globalAlpha = 0.35 + 0.5 * b;
      lctx.fillRect(col * 10.3, row * 28 + (1 - c) * 8, 8, 18 + c * 8);
    }
    lctx.globalAlpha = 1;
    put(libText, { o: lo * P(t, B[3] + 0.6, 0.5) });
    step2.style.opacity = P(t, B[3] + 5.5, 0.5);
    rise(qwen, t, B[4], B[5] - 0.2);
    const qk = P(t, B[4] + 1.0, 2.2, E.out);
    qnum.textContent = Math.round(qk * 35e9).toLocaleString("ru-RU");
    // задание
    rise(task, t, B[5], B[7] - 0.2);
    pt.textContent = typed(PROMPT, t, B[5] + 0.4, 22);
    rise(judgeBox, t, B[5] + 0.6, B[7] - 0.2);
    batch.forEach((el, i) => {
      const g = Math.floor(i / 4), a = B[6] + 0.3 + g * 1.4, k = P(t, a, 1.0, E.inOut);
      const x0 = 150 + (i % 4) * 135 + g * 560 * 0, y0 = 690 + g * 0;
      const x = lerp(140 + (i % 4) * 135 + g * 20, 1440 + (i % 4) * 20, k), y = lerp(760 + g * 14, 420 + (i % 4) * 8, k);
      put(el, { o: vis(t, B[6] + 0.1, B[7] - 0.2) * (1 - P(t, a + 0.9, 0.3)), x, y, s: lerp(1, 0.7, k) });
    });
    rise(batchNote, t, B[6] + 0.4, B[7] - 0.2);
    rise(slow, t, B[7], B[8] - 0.2);
    tm.textContent = `Читаю тексты… ${Math.max(0, Math.floor((t - B[7] - 1.0) * 4))} с`;
    rise(answer, t, B[8]);
  };
});

// ---------- пример: настоящий сервис
scene("example", (root, B) => {
  const ttl = h(root, "div", "abs", "left:120px; top:112px; width:1680px",
    `<div class="kicker">Завод в работе</div><div class="big">Сервис проверили им же</div>`);
  const FX = 260, FY = 228, FW = 1400, FH = 660, SCALE = 0.8, IW = Math.round(FW / SCALE), IH = Math.round((FH - 46) / SCALE);
  const frame = h(root, "div", "browser", `left:${FX}px; top:${FY}px; width:${FW}px; height:${FH}px`,
    `<div class="bar"><i></i><i></i><i></i><div class="url">srv-ai: проверка ППУ</div></div>`);
  frame.querySelector(".url").textContent = "сервер предприятия - проверка ППУ";
  const ifr = h(frame, "iframe", "", `width:${IW}px; height:${IH}px; transform:scale(${SCALE})`);
  ifr.src = "ui/index.html";
  window.uiReady = new Promise((res) => {
    ifr.onload = () => {
      const w = ifr.contentWindow, d = ifr.contentDocument;
      const st = d.createElement("style");
      st.textContent = "body{font-family:Inter,'Segoe UI',sans-serif !important}";
      d.head.appendChild(st);
      // ждём, пока страница получит /api/info
      const wait = () => (w.llmAvailable ? res() : setTimeout(wait, 50));
      wait();
    };
  });
  const cursor = h(root, "div", "", "", `<svg viewBox="0 0 24 24" width="34" height="34"><path d="M3 2l7 19 2.6-7.6L20 11z" fill="#1b232c" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>`);
  cursor.id = "cursor";
  const ring = h(root, "div", "abs", "width:60px; height:60px; border-radius:50%; border:4px solid var(--red)");
  const hl = h(root, "div", "hl");
  const caption = h(root, "div", "abs", "left:260px; top:830px; width:1400px; text-align:center",
    `<span class="chip c-red" style="font-size:30px">повтор или развитие идеи - решает комиссия</span>`);
  let state = "";
  const Q = window.QUERY;
  // координаты элемента внутри iframe -> на сцене
  const rect = (sel, idx = 0) => {
    const d = ifr.contentDocument; if (!d) return null;
    const el = d.querySelectorAll(sel)[idx]; if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: FX + r.left * SCALE, y: FY + 46 + r.top * SCALE, w: r.width * SCALE, h: r.height * SCALE };
  };
  function setUI(t) {
    const w = ifr.contentWindow, d = ifr.contentDocument;
    if (!w || !w.render || !d.querySelector("#name")) return;
    const info = d.querySelector("#info");
    if (info) info.textContent = "в реестре больше 11 000 ППУ";
    const T1 = B[1] + 0.2;  // ввод
    const fields = ["name", "before", "after", "proposal"];
    fields.forEach((f, i) => { d.querySelector("#" + f).value = typed(Q[f], t, T1 + i * 1.15, 80); });
    const go = d.querySelector("#go");
    let want;
    if (t < B[2] - 0.6) want = t > B[1] + 5.2 ? "checking" : "form";
    else if (t < B[4] + 1.0) want = "fast";
    else if (t < B[5] - 0.2) want = "wait";
    else want = "llm";
    if (want !== state) {
      if (want === "form" || want === "checking") {
        d.querySelector("#out").innerHTML = '<div class="panel empty">Заполните ППУ и нажмите «Проверить»</div>';
      } else if (want === "fast") {
        w.render(window.RES_FAST);
      } else if (want === "llm") {
        w.render(window.RES_LLM);
        const first = d.querySelector(".cand"); if (first) first.open = false;
      }
      if (want === "wait" && state !== "wait") { if (state !== "fast") w.render(window.RES_FAST); }
      state = want;
    }
    go.disabled = want === "checking"; go.textContent = want === "checking" ? "Проверяю…" : "Проверить";
    if (want === "wait") {
      const btn = d.querySelector("#ask-llm");
      if (btn) { btn.disabled = true; btn.textContent = `Читаю тексты… ${Math.floor((t - B[4] - 1.0) * 3 + 1)} с`; }
      const stl = d.querySelector("#llm-status");
      if (stl && !stl.querySelector("button")) stl.innerHTML = '<button type="button" class="link">отменить</button>';
    }
  }
  return (t) => {
    rise(ttl, t, B[0]);
    put(frame, { o: P(t, B[0] + 0.3, 0.6), y: (1 - P(t, B[0] + 0.3, 0.8)) * 40 });
    setUI(t);
    // курсор: к кнопке «Проверить», потом к «Проверить подробнее»
    const goR = rect("#go"), askR = rect("#ask-llm") || rect(".v-side .done");
    let cx = 1500, cy = 960, co = 0;
    const c1 = B[1] + 4.6, c2 = B[4] + 0.2;
    if (goR && t < B[2]) {
      const k = P(t, c1 - 1.0, 0.9, E.inOut);
      cx = lerp(1500, goR.x + goR.w / 2, k); cy = lerp(960, goR.y + goR.h / 2, k); co = vis(t, c1 - 1.2, B[2] - 0.3);
    } else if (askR && t >= B[3]) {
      const k = P(t, c2 - 1.2, 1.0, E.inOut);
      cx = lerp(1300, askR.x + askR.w / 2, k); cy = lerp(900, askR.y + askR.h / 2, k); co = vis(t, c2 - 1.4, B[5] - 0.2);
    }
    put(cursor, { o: co, x: cx - 6, y: cy - 4 });
    const click = (a) => { const k = clamp((t - a) / 0.5); return k > 0 && k < 1 ? k : 0; };
    const ck = click(c1) || click(c2);
    ring.style.opacity = ck ? 1 - ck : 0;
    put(ring, { o: ck ? 1 - ck : 0, x: cx - 30, y: cy - 30, s: lerp(0.3, 1.3, ck) });
    // подсветки
    let box = null, ho = 0;
    if (t >= B[2] + 0.6 && t < B[3] - 0.2) {
      const a = rect(".cand .score", 0), b = rect(".cand .score", 2);
      if (a && b) { box = { x: a.x - 8, y: a.y - 8, w: a.w + 16, h: b.y + b.h - a.y + 16 }; ho = vis(t, B[2] + 0.6, B[3] - 0.2); }
    } else if (t >= B[3] && t < B[4] - 0.1) {
      const a = rect(".topic");
      if (a) { box = { x: a.x - 6, y: a.y - 6, w: a.w + 12, h: a.h + 12 }; ho = vis(t, B[3], B[4] - 0.1); }
    } else if (t >= B[5] + 0.6) {
      const a = rect(".cand", 0), v = rect(".verdict");
      const target = t < B[5] + 4.5 ? v : a;
      if (target) { box = { x: target.x - 6, y: target.y - 6, w: target.w + 12, h: target.h + 12 }; ho = P(t, B[5] + 0.6, 0.4); }
    }
    if (box) {
      hl.style.left = box.x + "px"; hl.style.top = box.y + "px"; hl.style.width = box.w + "px"; hl.style.height = box.h + "px";
    }
    hl.style.opacity = box ? ho : 0;
    pop(caption, t, B[6]);
  };
});

// ---------- где это работает
scene("server", (root, B) => {
  const ttl = h(root, "div", "abs", "left:120px; top:112px; width:1680px", `<div class="kicker">Где это работает</div><div class="big">На сервере внутри заводской сети</div>`);
  const pc = h(root, "div", "abs", "left:150px; top:400px; width:280px; text-align:center; color:var(--steel)",
    `${ICON.pc}<div class="mid" style="font-size:28px; color:var(--ink)">Ваш компьютер</div><div class="small">обычный браузер</div>`);
  const net = h(root, "div", "abs", "left:440px; top:470px; width:640px; height:8px; border-radius:4px; background:var(--steel)");
  const netLabel = h(root, "div", "abs", "left:440px; top:500px; width:640px; text-align:center", `<span class="label">заводская сеть</span>`);
  const packets = Array.from({ length: 4 }, () => h(root, "div", "abs", "width:22px; height:22px; border-radius:6px; background:var(--red)"));
  const server = h(root, "div", "abs card", "left:1110px; top:300px; width:690px; padding:26px 30px; border-color:var(--steel); border-width:3px",
    `<div class="label">Сервер предприятия</div>
     <div style="display:grid; gap:14px; margin-top:16px">${[["Сервис проверки", "страница и поиск", "c-grey"], ["Модель векторов", "bge-m3", "c-blue"], ["Судья", "Qwen", "c-red"]].map(([a, b, c]) =>
      `<div class="blk" style="display:flex; justify-content:space-between; align-items:center; padding:16px 20px; border-radius:10px; background:var(--paper)">
        <span class="mid" style="font-size:28px">${a}</span><span class="chip ${c}">${b}</span></div>`).join("")}</div>`);
  const blks = [...server.querySelectorAll(".blk")];
  const cloud = h(root, "div", "abs", "left:630px; top:250px; width:260px; text-align:center; color:var(--muted)",
    `${ICON.cloud}<div class="mid" style="font-size:26px">Интернет</div>
     <div style="position:absolute; left:40px; top:40px; width:180px; height:6px; background:var(--red); transform:rotate(-28deg); border-radius:3px"></div>`);
  const lock = h(root, "div", "abs", "left:1110px; top:690px; width:690px; display:flex; gap:16px; align-items:center; color:var(--green)",
    `${ICON.lock}<span class="mid" style="color:var(--ink)">тексты ППУ не покидают предприятие</span>`);
  const admin = h(root, "div", "abs", "left:150px; top:640px; width:900px",
    `<div style="display:flex; gap:24px; align-items:center"><span style="color:#2c6e49">${ICON.xls}</span>
      <div style="flex:1"><div class="mid" style="font-size:28px">Свежий реестр → пересборка базы</div>
       <div style="height:14px; background:var(--grey-wash); border-radius:7px; margin-top:12px; overflow:hidden"><div class="pg" style="height:100%; width:0; background:var(--blue)"></div></div>
       <div class="small" style="margin-top:8px">пока идёт сборка, проверка работает по старой базе</div></div></div>`);
  const pg = admin.querySelector(".pg");
  return (t) => {
    rise(ttl, t, B[0] - 0.4);
    pop(cloud, t, B[0] + 0.3);
    rise(pc, t, B[1]); put(net, { o: P(t, B[1] + 1.0, 0.5) }); rise(netLabel, t, B[1] + 1.2);
    rise(server, t, B[1] + 2.4);
    blks.forEach((el, i) => rise(el, t, B[1] + 6.2 + 0.7 * i, Infinity, 14));
    packets.forEach((el, k) => {
      const ph = ((t - B[1] - 3.0) * 0.45 + k * 0.25) % 1;
      const fwd = k % 2 === 0;
      const x = fwd ? lerp(440, 1060, ph) : lerp(1060, 440, ph);
      put(el, { o: t > B[1] + 3.0 ? Math.sin(ph * Math.PI) : 0, x, y: 463 });
      el.style.background = fwd ? "var(--red)" : "var(--green)";
    });
    rise(lock, t, B[2] + 0.4);
    rise(admin, t, B[3]);
    pg.style.width = 100 * P(t, B[3] + 3.0, 5.0, E.inOut) + "%";
  };
});

// ---------- финал
scene("outro", (root, B, s) => {
  const cv = conveyor(root, 250);
  const t1 = h(root, "div", "abs center", "top:640px", `<div class="big">Секунды вместо недель чтения реестра</div>`);
  const t2 = h(root, "div", "abs center", "top:720px", `<div class="mid" style="color:var(--red)">Последнее слово - за людьми</div>`);
  const fin = h(root, "div", "abs", "inset:0; background:var(--paper); text-align:center; padding-top:300px",
    `<img src="logo.png" style="height:72px; margin-bottom:50px"><div class="title" style="font-size:80px">Проверка ППУ на повторы</div>
     <div class="txt" style="margin-top:22px">склад · векторы · поиск · быстрый вывод · судья</div>
     <div class="small" style="position:absolute; left:0; right:0; bottom:60px; font-size:20px">Музыка: Sascha Ende, ende.app (CC BY 4.0). Голос: синтез речи Piper. Шрифт: Golos Text.</div>`);
  const endA = B[2] + s.beats[2].d + 0.8;
  return (t) => {
    const words = [0.15, 0.45, 0.62, 0.78, 0.9].map((f) => B[0] + f * s.beats[0].d);
    const lit = words.reduce((acc, w, i) => (t >= w ? i : acc), -1);
    cv.update(t, { stAt: -2, ioAt: -2, lit });
    rise(t1, t, B[1]); rise(t2, t, B[2]);
    put(fin, { o: P(t, endA, 0.8, E.inOut) });
    document.getElementById("subs").style.opacity = 1 - P(t, endA, 0.4);
  };
});
