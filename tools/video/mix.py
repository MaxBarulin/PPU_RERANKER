"""Сведение звука: голос по таймлайну, музыка с приглушением под речью, мягкие эффекты на сменах сцен.

    venv/bin/python mix.py <skill_assets_dir>   -> audio/mix.wav (48 кГц, стерео)
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
SR = 48000
ASSETS = Path(sys.argv[1])


def load(path, ch=2):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", str(ch), "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, ch).copy()


def db(x):
    return 10 ** (x / 20)


s = (HERE / "stage/timeline.js").read_text(encoding="utf-8")
tl = json.loads(s[s.index("=") + 1:].rstrip().rstrip(";"))
total = tl["total"]
n = int(total * SR) + SR
voice = np.zeros((n, 2), np.float32)
for t, w in json.loads((HERE / "audio/voice.json").read_text()):
    a = load(w)
    i = int(t * SR)
    voice[i:i + len(a)] += a[: n - i]
voice *= db(-2) / max(1e-6, np.abs(voice).max())

# огибающая речи -> приглушение музыки (скользящие окна через накопленную сумму)
def movavg(x, k):
    c = np.concatenate([[0.0], np.cumsum(x, dtype=np.float64)])
    out = (c[k:] - c[:-k]) / k
    return np.pad(out, (k // 2, len(x) - len(out) - k // 2), mode="edge")


def trailing_max(x, k):  # было ли что-то в последние k отсчётов
    c = np.concatenate([[0.0], np.cumsum(x, dtype=np.float64)])
    idx = np.arange(len(x)) + 1
    return (c[idx] - c[np.maximum(idx - k, 0)]) > 0


speaking = (movavg(np.abs(voice[:, 0]), int(0.05 * SR)) > 0.01).astype(np.float32)
held = trailing_max(speaking, int(0.6 * SR)).astype(np.float32)
duck = movavg(held, int(0.35 * SR)).astype(np.float32)

tracks = ["happy-beats-business-moves-vol-1-by-ende-dot-app.mp3", "happy-beats-business-moves-vol-11-by-ende-dot-app.mp3",
          "happy-beats-business-moves-vol-12-by-ende-dot-app.mp3"]
music = np.zeros((0, 2), np.float32)
xf = int(3.0 * SR)
for name in tracks:
    a = load(ASSETS / "music" / name)
    if not len(music):
        music = a
        continue
    fade = np.linspace(0, 1, xf, dtype=np.float32)[:, None]
    music[-xf:] = music[-xf:] * (1 - fade) + a[:xf] * fade
    music = np.concatenate([music, a[xf:]])
music = music[:n]
if len(music) < n:
    music = np.pad(music, ((0, n - len(music)), (0, 0)))
music *= db(-3) / max(1e-6, np.abs(music).max())
gain = (db(-17) * (1 - duck) + db(-29) * duck)[:, None]
music *= gain
# вход и выход музыки
fi, fo = int(1.0 * SR), int(4.0 * SR)
end = int(total * SR)
music[:fi] *= np.linspace(0, 1, fi)[:, None]
music[end - fo:end] *= np.linspace(1, 0, fo)[:, None]
music[end:] = 0

sfx = np.zeros_like(voice)
soft = load(ASSETS / "sfx/impact/impactSoft_medium_001.ogg")
click = load(ASSETS / "sfx/ui/click2.ogg")


def add(sample, t, g):
    i = int(t * SR)
    sfx[i:i + len(sample)] += sample[: n - i] * g


for sc in tl["scenes"][1:]:
    add(soft, sc["start"] + 0.05, db(-20))
ex = next(sc for sc in tl["scenes"] if sc["id"] == "example")
B = [b["t"] for b in ex["beats"]]
add(click, ex["start"] + B[1] + 4.6, db(-12))
add(click, ex["start"] + B[4] + 0.2, db(-12))

out = voice + music + sfx
out = out[:end]
peak = np.abs(out).max()
if peak > 0.98:
    out *= 0.98 / peak
pcm = (out * 32767).astype(np.int16)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-", str(HERE / "audio/mix.wav")],
               input=pcm.tobytes(), check=True)
print("mix", round(len(out) / SR, 2), "s; peak", round(float(np.abs(out).max()), 3))
