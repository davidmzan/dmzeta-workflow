"""Audio de prueba para escuchar el grid: clips con clics y vistas previas."""
import os, subprocess
import numpy as np
from .config import DATA
from .grid import first_beat

def make_preview(path, bpm, bars, start_bar=0, length_bars=16, clicks=True, out=None):
    """Audio de prueba para comprobar los compases: un clic por compás y un clic agudo doble donde djflow cree que acaba el extender."""
    import wave
    SRP = 44100; bar = 240.0 / bpm; t0 = first_beat(path, 0.052); start_bar = max(0, int(start_bar))
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t0 + start_bar * bar:.3f}', '-t', f'{length_bars * bar:.3f}', '-i', path,
                          '-ac', '2', '-ar', str(SRP), '-f', 'f32le', '-'], capture_output=True).stdout
    y = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()
    if clicks:
        def tone(f, d, a): t = np.arange(int(d * SRP)) / SRP; return (a * np.sin(2 * np.pi * f * t) * np.exp(-t * 40)).astype(np.float32)
        for k in range(length_bars):
            b = start_bar + k; pos = int(k * bar * SRP)
            if pos >= len(y): break
            c = tone(2600, 0.15, 0.7) if bars and b == bars else tone(1100, 0.06, 0.35)
            n = min(len(c), len(y) - pos); y[pos:pos + n] += c[:n, None]
    y = np.clip(y, -1, 1); out = out or os.path.join(DATA, 'preview.wav')
    with wave.open(out, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SRP); w.writeframes((y * 32767).astype('<i2').tobytes())
    return out

def load_wave(path, sr=8000):
    """Pista completa en mono a baja resolución, para dibujar la onda."""
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32), sr

def make_clip(path, bpm, bars, start, dur, clicks=True, t0=0.052, out=None):
    """Fragmento [start, start+dur] en segundos, con un clic por compás y clic agudo doble en el corte del extender."""
    import wave, math
    SRP = 44100; bar = 240.0 / bpm; start = max(0.0, start)
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{start:.3f}', '-t', f'{dur:.3f}', '-i', path, '-ac', '2', '-ar', str(SRP), '-f', 'f32le', '-'], capture_output=True).stdout
    y = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()
    if clicks:
        def tone(f, d, a): t = np.arange(int(d * SRP)) / SRP; return (a * np.sin(2 * np.pi * f * t) * np.exp(-t * 40)).astype(np.float32)
        b = max(0, math.ceil((start - t0) / bar))
        while t0 + b * bar < start + len(y) / SRP:
            pos = int((t0 + b * bar - start) * SRP)
            if pos >= 0:
                c = tone(2600, 0.15, 0.7) if bars and b == bars else tone(1100, 0.06, 0.35)
                n = min(len(c), len(y) - pos)
                if n > 0: y[pos:pos + n] += c[:n, None]
            b += 1
    y = np.clip(y, -1, 1); out = out or os.path.join(DATA, 'preview.wav')
    with wave.open(out, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SRP); w.writeframes((y * 32767).astype('<i2').tobytes())
    return out
