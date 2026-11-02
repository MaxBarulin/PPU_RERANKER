# Запуск на Linux-сервере

Батники из `scripts\windows` на Linux не работают — ниже то же самое командами.
Все команды выполняются из папки проекта `~/PPU_RERANKER`.

Нужно: Python 3.11+, собранный llama.cpp (`llama-server`), GGUF-файл `bge-m3`.

Порты ниже — **8091** для эмбеддингов и **8010** для веба. Если они заняты
(см. шаг 0), берите любые свободные и меняйте везде одинаково.

## 0. Подготовка

```bash
git clone https://github.com/MaxBarulin/PPU_RERANKER.git
cd ~/PPU_RERANKER
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env          # файл с точкой в начале: .env.example

mkdir -p logs data ~/models
pgrep -af ppu.web                        # что-то осталось от прошлых попыток — kill <PID>
ss -ltnp | grep -E ':(80[0-9][0-9])\b'   # какие порты уже заняты
```

## 1. Сервер эмбеддингов

Скопировать модель с Windows на сервер (команда — в `cmd` **на Windows**,
`scp` в Windows 10 уже есть):

```
scp F:\kobold_model\bge-m3-Q8_0.gguf <логин>@<сервер>:~/models/
```

На сервере найти `llama-server`:

```bash
ls ~/llama.cpp-new/build/bin/llama-server
# если не там:
find ~ -name llama-server -type f 2>/dev/null
```

Запуск:

```bash
nohup ~/llama.cpp-new/build/bin/llama-server -m ~/models/bge-m3-Q8_0.gguf \
  --embedding --pooling cls -ngl 0 -t 8 -c 8192 -b 8192 -ub 8192 -np 1 \
  --host 127.0.0.1 --port 8091 > logs/emb.log 2>&1 &

curl http://127.0.0.1:8091/health      # должно быть {"status":"ok"}
```

- `-ngl` — `99`, если `nvidia-smi` показывает видеокарту, иначе `0`.
- `-t` — число физических ядер (`lscpu`: Core(s) per socket × Socket(s)).
- `-c`, `-b`, `-ub` одинаковые: bge-m3 обрабатывает текст только целиком
  за один проход.

## 2. Файл `.env`

`nano .env`:

```
EMB_BASE_URL=http://127.0.0.1:8091/v1
EMB_MODEL=bge-m3
LLM_BASE_URL=
```

Пустой `LLM_BASE_URL` — судьи нет, кнопки «Уточнить у LLM» не будет.
Если на сервере уже работает OpenAI-совместимый LLM-сервер — впишите его
адрес (с `/v1` на конце) и имя модели в `LLM_MODEL`.

## 3. Индекс — одно из двух

**А. Индекс уже собран на Windows** — скопировать его. Модель та же, индекс
подойдёт. В `cmd` на Windows, из папки проекта:

```
scp -r data <логин>@<сервер>:~/PPU_RERANKER/
```

**Б. Собрать на сервере.** Реестр — с Windows:

```
scp "D:\путь\Реестр ППУ.xlsx" <логин>@<сервер>:~/PPU_RERANKER/data/registry.xlsx
```

На сервере:

```bash
venv/bin/python -m ppu.prepare data/registry.xlsx --out data/registry_clean.jsonl > data/prepare_report.txt
nohup venv/bin/python -m ppu.index data/registry_clean.jsonl --out data/index > logs/index.log 2>&1 &
tail -f logs/index.log      # ход сборки; Ctrl+C закрывает просмотр, сборка идёт дальше
```

Оборвалось — запустите ту же команду снова: посчитанное возьмётся из кэша.

> Индекс и запросы должны считаться одной и той же моделью эмбеддингов.
> Поменяли GGUF — пересоберите индекс.

## 4. Веб-интерфейс

Когда в `data/index` появился `meta.json`:

```bash
nohup venv/bin/python -m ppu.web --host 0.0.0.0 --port 8010 > logs/web.log 2>&1 &
```

Открыть `http://<сервер>:8010`.

Не открывается — скорее всего, порт закрыт сетевым экраном. Тогда на Windows:

```
ssh -L 8010:127.0.0.1:8010 <логин>@<сервер>
```

окно не закрывать, открыть http://127.0.0.1:8010.

`--host 0.0.0.0` — доступно всем в сети; `127.0.0.1` — только через ssh-туннель.

## Остановка и логи

```bash
pkill -f ppu.web                      # веб
pkill -f "llama-server.*bge-m3"       # только сервер эмбеддингов
tail -50 logs/web.log                 # ошибки веба
tail -50 logs/emb.log                 # ошибки сервера эмбеддингов
```

Не пишите просто `pkill llama-server` — остановятся и другие LLM-серверы на машине.

## Частые ошибки

| Сообщение | Что значит |
|---|---|
| `cp: cannot stat 'env.example'` | файл называется `.env.example` — с точкой в начале |
| `address already in use` | порт занят другой программой — возьмите свободный (шаг 0) |
| `Error while finding module specification for 'ppu.web:ppu'` | правильно `python -m ppu.web`, без `:ppu` |
| `Exit 3` у фонового процесса | веб не стартовал — смотрите `logs/web.log` |
| `nohup: ignoring input and appending output to 'nohup.out'` | команда без `&` и без `> файл` — работает в этом окне; Ctrl+C её остановит |
