# Исходник руководства специалиста

`guide.html` и снимки экрана в `img/` собираются в `../rukovodstvo-specialista.pdf`.
Снимки сделаны на выдуманной демо-базе.

Собрать PDF после правок (Chromium через Playwright):

```js
// node build.js  (из корня проекта)
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://' + require('path').resolve('docs/guide/guide.html'), { waitUntil: 'networkidle' });
  await p.pdf({ path: 'docs/rukovodstvo-specialista.pdf', format: 'A4', printBackground: true,
    preferCSSPageSize: true, displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: '<div style="font:8px Inter,sans-serif;color:#8a94a6;width:100%;padding:0 17mm;'
      + 'display:flex;justify-content:space-between"><span>Проверка ППУ на повторы — руководство '
      + 'специалиста</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>' });
  await b.close();
})();
```
