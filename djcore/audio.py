"""Decodificación, espectrograma, matrices por compás y utilidades de audio."""
import os, hashlib, subprocess
import numpy as np
from .config import CACHE_DIR, FR, HOP, N_FFT, SR
from .names import parse_name

# ───────────────────────── audio / características ─────────────────────────
def ffprobe_tags(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format_tags', '-of', 'default=nw=1', path],
                         capture_output=True, text=True).stdout
    d = {}
    for line in out.splitlines():
        if line.startswith('TAG:') and '=' in line:
            k, v = line[4:].split('=', 1); d[k.lower()] = v
    return d

def decode(path):
    out = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True).stdout
    return np.frombuffer(out, dtype=np.float32)

def stft(y):
    w = np.hanning(N_FFT).astype(np.float32)
    nf = 1 + (len(y) - N_FFT) // HOP
    if nf <= 0: return np.zeros((len(FR), 0), dtype=np.float32)
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(nf)[:, None]
    return np.abs(np.fft.rfft(y[idx] * w, axis=1)).T

def _band(S, lo, hi): return S[(FR >= lo) & (FR < hi)]

def bar_matrix(S, bpm, nbars, from_end=False):
    """Matriz (barras x NF) de características por compás."""
    fpb = (240.0 / bpm) * (SR / HOP); T = S.shape[1]
    low, mid, hi, voc = _band(S, 30, 130).sum(0), _band(S, 200, 1500).sum(0), _band(S, 3000, 9000).sum(0), _band(S, 300, 3400).sum(0)
    tm = _band(S, 200, 3000) + 1e-6
    flat = np.exp(np.log(tm).mean(0)) / tm.mean(0)
    rows = []
    for i in range(nbars):
        if from_end: a, c = int(T - (nbars - i) * fpb), int(T - (nbars - i - 1) * fpb)
        else: a, c = int(i * fpb), int((i + 1) * fpb)
        if a < 0 or c > T or c - a < 4: break
        L = low[a:c]
        k = np.maximum(0, np.diff(L)).mean() / (L.mean() + 1e-6)
        H = hi[a:c]; h = np.maximum(0, np.diff(H)).mean() / (H.mean() + 1e-6)
        rows.append([20 * np.log10(L.mean() + 1e-6), 20 * np.log10(mid[a:c].mean() + 1e-6), 20 * np.log10(H.mean() + 1e-6),
                     20 * np.log10(voc[a:c].mean() + 1e-6), 20 * k, 20 * h, 10 * (1 - flat[a:c].mean())])
    return np.array(rows, dtype=np.float32)

def extract(path, bpm):
    """Características de una pista: cabecera (64 barras), cola (8 barras), duración."""
    y = decode(path); dur = len(y) / SR; bar = 240.0 / bpm
    head = bar_matrix(stft(y[:int(min(len(y), 100 * SR))]), bpm, 64)
    tail = bar_matrix(stft(y[-int(min(len(y), 40 * SR)):]), bpm, 8, from_end=True)
    return dict(head=head, tail=tail, dur=dur, nbars=dur / bar)

def get_features(path, bpm):
    os.makedirs(CACHE_DIR, exist_ok=True)
    h = hashlib.md5(f'{os.path.abspath(path)}|{os.path.getsize(path)}|{int(os.path.getmtime(path))}|{bpm:.2f}'.encode()).hexdigest()
    fp = os.path.join(CACHE_DIR, h + '.npz')
    if os.path.exists(fp):
        z = np.load(fp); return dict(head=z['head'], tail=z['tail'], dur=float(z['dur']), nbars=float(z['nbars']))
    f = extract(path, bpm); np.savez_compressed(fp, **f); return f

def track_bpm_key(path):
    tg = ffprobe_tags(path); p = parse_name(path)
    bpm = 0
    for k in ('tbpm', 'bpm', 'tmpo', 'com.apple.itunes:bpm'):
        try: bpm = bpm or float(tg.get(k, 0) or 0)
        except ValueError: pass
    bpm = bpm or (p['bpm'] or 0)
    key = ''
    for k in ('tkey', 'initialkey', 'initial key', 'key', 'com.apple.itunes:initialkey'):
        key = key or (tg.get(k) or '').strip()
    return bpm, (key or (p['key'] or ''))

def struct_matrix(path, bpm, t0, nbars=100):
    """Características por compás desde el primer beat (hasta 100 compases) + duración. Con caché."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    fp = os.path.join(CACHE_DIR, 'st_' + hashlib.md5(f'{os.path.abspath(path)}|{os.path.getsize(path)}|{int(os.path.getmtime(path))}|{bpm:.2f}|{t0:.2f}'.encode()).hexdigest() + '.npz')
    if os.path.exists(fp): z = np.load(fp); return z['A'], float(z['dur'])
    y = decode(path); dur = len(y) / SR; a = int(max(0.0, t0) * SR); b = a + int(((nbars + 2) * 240.0 / bpm) * SR)
    A = bar_matrix(stft(y[a:b]), bpm, nbars); np.savez_compressed(fp, A=A, dur=dur); return A, dur
