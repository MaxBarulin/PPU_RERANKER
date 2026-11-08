// node render.js stills <out_dir> t1 t2 ...   |   node render.js video <out.mp4> <frame_from> <frame_to>
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const FPS = 30, URL = 'http://127.0.0.1:18200/index.html';
(async () => {
  const [mode, out, ...rest] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => m.type() === 'error' && errs.push(m.text()));
  await p.goto(URL); await p.evaluate(() => window.ready()); await p.evaluate(() => window.seek(0)); await p.waitForTimeout(300);
  if (mode === 'stills') {
    for (const t of rest) {
      await p.evaluate((t) => window.seek(t), Number(t));
      await p.screenshot({ path: `${out}/s_${String(t).padStart(6, '0')}.png` });
    }
  } else {
    const [f0, f1] = rest.map(Number);
    const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', String(FPS), out], { stdio: ['pipe', 'inherit', 'inherit'] });
    for (let f = f0; f < f1; f++) {
      await p.evaluate((t) => window.seek(t), f / FPS);
      const buf = await p.screenshot({ type: 'jpeg', quality: 93 });
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
      if (f % 300 === 0) console.log(out, f, '/', f1);
    }
    ff.stdin.end(); await new Promise(r => ff.on('close', r));
  }
  console.log('errors', errs.slice(0, 5));
  await b.close();
})();
