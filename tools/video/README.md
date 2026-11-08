# Ролик «Как устроена проверка ППУ на повторы»

Исходники видеоролика (6,5 мин, 1920×1080, озвучка и субтитры). Текстовая
пара к нему - `docs/kak-eto-ustroeno.md`. Сервису эта папка не нужна.

Как устроено: сцена - HTML-страница, каждый кадр которой - функция времени
(`stage/scenes.js`). Браузер (Playwright) снимает кадры, ffmpeg собирает
видео. Анимация привязана к фразам озвучки: тайминг берётся из длительности
синтезированной речи.

| Файл | Что делает |
|---|---|
| `script.py` | Текст озвучки по сценам, синтез речи (Piper, голос ru_RU-dmitri-medium), тайминг `stage/timeline.js`, субтитры `out/subs.srt` |
| `stage/` | Сцены, данные примера (`mock.js`), шрифт Golos Text (OFL) |
| `serve.py` | Локальный сервер для сцены и настоящей страницы сервиса внутри ролика |
| `render.js` | Снимает кадры: `stills` - стоп-кадры, `video` - кусок видео |
| `mix.py` | Сведение: голос, музыка с приглушением под речью, эффекты |
| `asr.py` | Проверка озвучки распознаванием речи (faster-whisper) |

## Сборка

```bash
cd tools/video
python3 -m venv venv && venv/bin/pip install piper-tts faster-whisper numpy
mkdir -p voices && for e in onnx onnx.json; do curl -sSL -o voices/ru_RU-dmitri-medium.$e \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.$e; done
cp ../../ppu/web/static/logo.png stage/ && mkdir -p stage/ui && cp ../../ppu/web/static/index.html ../../ppu/web/static/logo.png stage/ui/
venv/bin/python script.py                         # озвучка, тайминг, субтитры
venv/bin/python serve.py 18200 stage &            # сцена на 127.0.0.1:18200
node render.js stills /tmp 10 100 300             # стоп-кадры для проверки
node render.js video out/video.mp4 0 11617        # кадры 0..N (N = длительность × 30)
venv/bin/python mix.py <папка assets из скилла brag>   # музыка и эффекты
```

Склейка (видео + звук + обложка + субтитры) - ffmpeg, команда в истории
сессии; главное: `-af loudnorm=I=-16:TP=-1.5`, субтитры `-c:s mov_text`.

Музыка: Sascha Ende, ende.app, «Happy Beats / Business Moves» vol. 1, 11, 12
(CC BY 4.0, автор указан в титрах). Эффекты: Kenney (CC0). Голос: Piper
ru_RU-dmitri (датасет CC0).
