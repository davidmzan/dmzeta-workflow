"""Beat grid: detección de fase y BPM, golpe fuerte, inicio del ataque y retraso del MP3."""
import os, hashlib, subprocess
import numpy as np
from .config import CAL, GRID_CACHE, GRID_HOP, GRID_N, SR
from .storage import load_prefs
from .audio import decode

def _env(y):
    """Curva de onsets con 5,8 ms de resolución: 70 % graves (bombo, 30-160 Hz) + 30 % banda completa, para no engancharse a hats o contratiempos."""
    w = np.hanning(GRID_N).astype(np.float32); nf = 1 + (len(y) - GRID_N) // GRID_HOP
    fq = np.fft.rfftfreq(GRID_N, 1 / SR); full = (fq >= 30) & (fq <= 6000); low = (fq >= 30) & (fq <= 160); cf, cl = [], []
    for a in range(0, nf, 1500):
        idx = np.arange(GRID_N)[None, :] + GRID_HOP * np.arange(a, min(nf, a + 1500))[:, None]
        S = np.abs(np.fft.rfft(y[idx] * w, axis=1)); cf.append(np.log1p(10 * S[:, full])); cl.append(np.log1p(10 * S[:, low]))
    def flux(chunks):
        L = np.vstack(chunks); f = np.concatenate([[0], np.maximum(0, L[1:] - L[:-1]).sum(1)]).astype(np.float32); return f / (np.percentile(f, 95) + 1e-9)
    return (0.7 * flux(cl) + 0.3 * flux(cf)).astype(np.float32)

def _lp_env(y, fc=150, sm_ms=3):
    n = 257; t = np.arange(n) - (n - 1) / 2; h = np.sinc(2 * fc / SR * t) * np.hanning(n); h /= h.sum()
    return np.convolve(np.abs(np.convolve(y, h, mode='same')), np.ones(max(1, int(SR * sm_ms / 1000))) / max(1, int(SR * sm_ms / 1000)), mode='same')

def _strong_shift(y, t0, bpm, nmax=12):
    """Cuántos beats hay que avanzar para caer en el primer golpe fuerte de bombo (>= 60 % de la fuerza mediana). 0 si ya está."""
    try:
        e = _lp_env(y); P = 60.0 / bpm; pk = []
        for k in range(0, 48):
            a, c = max(0, int((t0 + k * P - 0.04) * SR)), int((t0 + k * P + 0.04) * SR)
            if c >= len(e) or c <= a: pk.append(0.0); continue
            pk.append(float(e[a:c].max()))
        pk = np.array(pk); ref = np.median(pk[8:40]) if len(pk) >= 40 else 0
        if ref <= 0: return 0
        for k in range(0, nmax + 1):
            if pk[k] >= 0.6 * ref: return k
    except Exception: pass
    return 0

_DELAY: dict = {}

def mp3_delay(path):
    """Segundos que Rekordbox ve el MP3 más tarde que yo. ffmpeg recorta el retardo del codificador (start_time ~25 ms) en los MP3 con cabecera LAME
    y Rekordbox no; además suma 576 muestras. Medido en tu pista: ~38 ms. Los MP3 sin ese recorte (start_time 0) coinciden y devuelven 0."""
    k = (path, os.path.getmtime(path))
    if k in _DELAY: return _DELAY[k]
    v = 0.0
    try:
        o = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=start_time,sample_rate', '-of', 'csv=p=0', path], capture_output=True, text=True, timeout=20).stdout.split()[0].split(',')
        sr, st = float(o[0]), float(o[1])
        if st > 0.001: v = st + 576.0 / sr
    except Exception: v = 0.0
    _DELAY[k] = v; return v

def _attack_start(y, t0, frac=0.2, lo=0.04, hi=0.15):
    """Instante (-40/+150 ms alrededor de t0) donde la envolvente del golpe supera el 20 % de su pico: el comienzo del ataque."""
    a = max(0, int((t0 - lo) * SR)); b = min(len(y), int((t0 + hi) * SR))
    if b - a < 200: return t0
    k = max(1, int(0.003 * SR)); e = np.convolve(np.abs(y[a:b]), np.ones(k) / k, 'same'); pk = int(e.argmax())
    if e[pk] < 1e-4: return t0
    idx = np.where(e[:pk + 1] >= frac * e[pk])[0]
    return float((a + idx[0]) / SR) if len(idx) else t0

def _detect_grid_raw(path, bpm, seconds=50, fresh=False):
    """Beat grid real: primer beat, BPM refinado (+-1,2 %) y confianza. Se apoya en los golpes del audio, no en un valor fijo."""
    os.makedirs(GRID_CACHE, exist_ok=True)
    key = hashlib.md5(f'grid6|{os.path.abspath(path)}|{os.path.getsize(path)}|{int(os.path.getmtime(path))}|{bpm:.3f}'.encode()).hexdigest()
    fp = os.path.join(GRID_CACHE, key + '.npy')
    if os.path.exists(fp) and not fresh: r = np.load(fp); return float(r[0]), float(r[1]), float(r[2])
    y = decode(path)[:int(seconds * SR)]; y0 = y
    if len(y) < SR * 5: return 0.052, bpm, 0.0
    y = np.concatenate([np.zeros(GRID_N, dtype=np.float32), y])        # relleno para no perder un golpe en el instante 0
    env = _env(y); fps = SR / GRID_HOP; env = env / (np.percentile(env, 95) + 1e-9)
    sm = np.max(np.stack([np.roll(env, k) for k in (-2, -1, 0, 1, 2)]), axis=0); T = len(env)
    def best_phase(b):
        P = 60.0 / b * fps; phi = np.arange(0, P, 1.0); k = np.arange(0, int((T - 2) / P))
        idx = np.rint(phi[:, None] + k[None, :] * P).astype(int); ok = idx < T
        sc = np.where(ok, sm[np.minimum(idx, T - 1)], 0).sum(1) / np.maximum(ok.sum(1), 1)
        m = int(np.argmax(sc)); return float(sc[m]), float(phi[m]), P
    base = best_phase(bpm); best = (base[0], bpm, base[1], base[2])
    for f in np.arange(-0.012, 0.0121, 0.0004):
        if abs(f) < 1e-9: continue
        b = bpm * (1 + f); sc, phi, P = best_phase(b)
        if sc > best[0] * 1.04: best = (sc, b, phi, P)          # solo cambia el BPM si mejora claramente
    sc, b, phi, P = best
    # afinado del desfase: mediana de la desviación real de cada beat
    offs = []
    for k in range(int((T - 2) / P)):
        c = int(round(phi + k * P)); lo, hi = max(0, c - 3), min(T, c + 4)
        if hi - lo >= 5 and env[lo:hi].max() > 0.4: offs.append(int(np.argmax(env[lo:hi])) + lo - c)
    if offs: phi += float(np.median(offs))
    # primer beat con música real
    kf = 0
    for k in range(int((T - 2) / P)):
        c = int(round(phi + k * P)); lo, hi = max(0, c - 2), min(T, c + 3)
        if hi > lo and env[lo:hi].max() > 0.30: kf = k; break
    t0 = (phi + kf * P) / fps + CAL - GRID_N / SR
    sh = _strong_shift(y0, max(0.0, t0), b)                # el compás 1 empieza en el primer golpe FUERTE, no en un beat flojo anterior
    if sh: t0 = max(0.0, t0) + sh * 60.0 / b
    t0 = _attack_start(y0, max(0.0, t0))                  # afina al INICIO del ataque del golpe (donde lo ve el ojo y donde pone el grid Rekordbox)
    r = (max(0.0, t0), b, float(sc)); np.save(fp, np.array(r)); return r

def grid_bias():
    """Corrección sistemática (s) aprendida de tus ajustes de grid: mediana de tus desvíos finos, con al menos 8 muestras."""
    g = load_prefs().get('grid2') or []
    return float(np.clip(np.median(g) / 1000.0, -0.04, 0.04)) if len(g) >= 8 else 0.0

def detect_grid(path, bpm, seconds=50, raw=False, fresh=False):
    t0, b, sc = _detect_grid_raw(path, bpm, seconds, fresh)
    if not raw and t0 > 0: t0 = max(0.0, t0 + grid_bias())
    return t0, b, sc

def first_beat(path, default, bpm=None):
    """Primer beat detectado del audio (si hay BPM); si no, el valor por defecto."""
    if bpm:
        try: return round(detect_grid(path, bpm)[0], 3)
        except Exception: pass
    return default
