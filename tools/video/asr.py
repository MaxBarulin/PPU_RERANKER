import json, subprocess, sys, numpy as np
from faster_whisper import WhisperModel
m = WhisperModel("small", device="cpu", compute_type="int8")
items = json.load(open("audio/voice.json"))
only = sys.argv[1:]  # фильтр по id сцены
for t, w in items:
    name = w.rsplit("/", 1)[1]
    if only and not any(name.startswith(o + "_") for o in only):
        continue
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", w, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    segs, _ = m.transcribe(a, language="ru", beam_size=5)
    print(name.rsplit("_", 1)[0], "|", " ".join(s.text.strip() for s in segs), flush=True)
