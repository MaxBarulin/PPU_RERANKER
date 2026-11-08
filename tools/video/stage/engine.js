// Движок: каждый кадр - чистая функция времени. window.seek(t) рисует кадр t (секунды).
const W = 1920, H = 1080;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, k) => a + (b - a) * k;
const E = {
  out: (t) => 1 - Math.pow(1 - t, 3),
  inOut: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  back: (t) => { const c = 1.5; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); },
  lin: (t) => t,
};
// прогресс 0..1 от момента a длительностью d
const P = (t, a, d = 0.6, e = E.out) => e(clamp((t - a) / d));
// появление и исчезновение: in в момент a, out в момент b (если задан)
const vis = (t, a, b = Infinity, din = 0.5, dout = 0.4) => P(t, a, din) * (1 - P(t, b, dout, E.inOut));

function rng(seed) {  // детерминированный ГПСЧ
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

const stage = document.getElementById("stage");
function h(parent, tag, cls = "", style = "", html = "") {
  const el = tag === "svg" ? document.createElementNS("http://www.w3.org/2000/svg", "svg") : document.createElement(tag);
  if (cls) el.setAttribute("class", cls);
  if (style) el.setAttribute("style", style);
  if (html) el.innerHTML = html;
  parent.appendChild(el);
  return el;
}
// позиция и видимость элемента
function put(el, { o = 1, x = 0, y = 0, s = 1, r = 0 } = {}) {
  el.style.opacity = o;
  el.style.transform = `translate(${x}px, ${y}px) scale(${s}) rotate(${r}deg)`;
  el.style.visibility = o <= 0.001 ? "hidden" : "visible";
}
// типовое появление: снизу, с прозрачности
function rise(el, t, a, b = Infinity, dy = 30) {
  const k = P(t, a, 0.6), o = vis(t, a, b);
  put(el, { o, y: (1 - k) * dy });
}
function pop(el, t, a, b = Infinity) {
  const k = P(t, a, 0.5, E.back), o = vis(t, a, b, 0.3);
  put(el, { o, s: lerp(0.85, 1, k) });
}
function typed(text, t, a, cps = 28) {
  const n = Math.floor(clamp((t - a) * cps, 0, text.length));
  return text.slice(0, n);
}
function esc(s) { return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

// ---- сцены
const SCENES = {};
const TL = window.TIMELINE;
function scene(id, build) { SCENES[id] = { build }; }

// ---- общий слой: шапка, субтитры
const topBar = h(stage, "div", "", "", `<img src="logo.png" alt=""><div id="chapter"></div>`);
topBar.id = "top";
const chapter = topBar.querySelector("#chapter");
const STATIONS = ["Склад", "Векторы", "Поиск", "Быстрый вывод", "Судья"];
chapter.innerHTML = STATIONS.map((n, i) => `<div class="st">${i + 1}</div>`).join("") + `<div class="name"></div>`;
const subs = h(stage, "div", "", "", "<span></span>");
subs.id = "subs";

const CHAPTER_OF = { st1: 0, st2: 1, st3: 2, st4: 3, st5: 4 };

let built = false;
function buildAll() {
  for (const s of TL.scenes) {
    const def = SCENES[s.id];
    s.root = h(stage, "div", "scene");
    s.root.dataset.id = s.id;
    const B = s.beats.map((b) => b.t);
    B.end = s.dur;
    s.B = B;
    s.update = def ? def.build(s.root, B, s) : () => {};
  }
  stage.appendChild(topBar);
  stage.appendChild(subs);
  built = true;
}

window.seek = function (t) {
  if (!built) buildAll();
  subs.style.opacity = 1;
  for (const s of TL.scenes) {
    const lt = t - s.start;
    const on = lt >= -0.01 && lt < s.dur;
    if (!on) { s.root.style.display = "none"; continue; }
    s.root.style.display = "block";
    // переход через фон: исчезает в конце, появляется в начале
    const o = (s.id === "intro" ? 1 : P(lt, 0, 0.45)) * (s.id === "outro" ? 1 : 1 - P(lt, s.dur - 0.4, 0.4, E.inOut));
    s.root.style.opacity = o;
    s.update(lt);
  }
  // шапка
  const cur = TL.scenes.find((s) => t >= s.start && t < s.start + s.dur) || TL.scenes[TL.scenes.length - 1];
  const ci = CHAPTER_OF[cur.id];
  const showChapter = ci !== undefined;
  chapter.style.opacity = showChapter ? P(t - cur.start, 0, 0.5) : 0;
  [...chapter.querySelectorAll(".st")].forEach((el, i) => {
    el.classList.toggle("on", i === ci);
    el.classList.toggle("done", showChapter && i < ci);
  });
  chapter.querySelector(".name").textContent = showChapter ? STATIONS[ci] : "";
  topBar.style.opacity = cur.id === "intro" && t < 2.0 ? 0 : 1;
  // субтитры
  const sub = TL.subs.find(([a, b]) => t >= a && t < b + 0.15);
  const span = subs.firstChild;
  if (sub) { span.textContent = sub[2]; span.style.visibility = "visible"; } else span.style.visibility = "hidden";
};

window.ready = async function () {
  await document.fonts.ready;
  const imgs = [...document.images].filter((i) => !i.complete);
  await Promise.all(imgs.map((i) => new Promise((r) => { i.onload = i.onerror = r; })));
  if (window.uiReady) await window.uiReady;
  return true;
};
