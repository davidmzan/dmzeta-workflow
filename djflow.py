#!/usr/bin/env python3
"""
djflow: prepara y nombra tu música ANTES de importarla a Rekordbox, aprendiendo de TU biblioteca.

  python3 djflow.py train       <carpeta> [<carpeta>...]   # aprende nombres de tus pistas ya ordenadas + informe
  python3 djflow.py train-marks <rekordbox.xml>            # aprende dónde pones START MIX (necesita los audios del XML)
  python3 djflow.py analyze     <carpeta> [rekordbox.xml]  # propone nombres (+duplicados, START MIX) -> review.csv
  python3 djflow.py apply       <carpeta>                  # renombra y limpia tags (solo filas con "final"); guarda copia
  python3 djflow.py undo                                   # deshace la última tanda aplicada
  python3 djflow.py cues        <rekordbox.xml> <carpeta>  # genera djflow_cues.xml (INTRO, hot cues A/B/C, START/END MIX, loop)
  python3 djflow.py clean       <carpeta>                  # solo limpia tags

Requisitos: Python 3 con tkinter (ventana), numpy y ffmpeg (brew install ffmpeg ; pip3 install numpy)
Nombre estándar:  Título (Mashup)(N Bars POE|MOE|FME | Aca Starter)(In Aca|In Hype)(Short Edit)(Aca Out) - TONO - BPM
"""
import sys, os, re, csv, json, time, shutil, hashlib, subprocess
import numpy as np

SR = 22050; N_FFT = 2048; HOP = 512
EXT = ('.mp3', '.m4a', '.flac', '.wav', '.aif', '.aiff')
CANDS = [4, 8, 16, 24, 32]
TYPES = ['MOE', 'POE', 'FME']
FR = np.fft.rfftfreq(N_FFT, 1 / SR)
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, 'model.npz')
LEARN_DIR = os.path.join(HERE, 'learned')
HIST_DIR = os.path.join(HERE, 'history')
BACKUP_DIR = os.path.join(HERE, 'backup')
MARKS_FILE = 'djflow_marks.json'
DONE_FILE = os.path.join(HERE, 'done.json')
PREFS_FILE = os.path.join(HERE, 'prefs.json')
LEARN_MARKS_DIR = os.path.join(HERE, 'learned_marks')

def load_prefs():
    try: return json.load(open(PREFS_FILE, encoding='utf-8'))
    except Exception: return {}

def _pref(kind, default, minn=3):
    """Valor más usado por ti (hueco START→END, duración del loop). Solo si hay al menos minn muestras."""
    d = load_prefs().get(kind) or {}
    if sum(d.values()) < minn: return default
    return int(max(d.items(), key=lambda x: x[1])[0])

def _fp(path):
    st = os.stat(path); return f'{st.st_size}:{int(st.st_mtime)}'

def load_done():
    try: return json.load(open(DONE_FILE, encoding='utf-8'))
    except Exception: return {}

def mark_done(paths):
    d = load_done()
    for p in paths:
        try: d[_fp(p)] = os.path.basename(p)
        except OSError: pass
    json.dump(d, open(DONE_FILE, 'w', encoding='utf-8'), ensure_ascii=False)

def is_done(path):
    try: return _fp(path) in load_done()
    except OSError: return False

def cmd_mark_done(folder):
    """Marca como ya procesados todos los audios de la carpeta (tu colección ya ordenada)."""
    fs = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(EXT)]
    mark_done(fs); print(f'{len(fs)} archivos marcados como ya procesados. No se volverán a analizar mientras no los modifiques.')
CACHE_DIR = os.path.join(HERE, 'cache')
NF = 7   # low, mid, hi, voc, kick, hat, tonal

# ───────────────────────── nombres ─────────────────────────
def parse_name(fname):
    """Extrae las etiquetas de un nombre ya estandarizado."""
    s = os.path.splitext(os.path.basename(fname))[0]
    key = bpm = None
    m = re.search(r'\s*-\s*(\d{1,2}[AB])\s*-\s*(\d+)\s*$', s)
    if m: key, bpm = m.group(1), float(m.group(2)); s = s[:m.start()]
    out = dict(mashup='(Mashup)' in s, open_show='(Open Show)' in s, bars=None, type=None, aca_starter='(Aca Starter)' in s,
               after=None, short_edit='(Short Edit)' in s, aca_out='(Aca Out)' in s, key=key, bpm=bpm)
    mb = re.search(r'\((\d+) Bars (POE|MOE|FME)\)', s)
    if mb: out['bars'], out['type'] = int(mb.group(1)), mb.group(2)
    ma = re.search(r'\((In Aca|In Hype)\)', s)
    if ma: out['after'] = ma.group(1)
    base = re.sub(r'\s*\((?:Mashup|Open Show|\d+ Bars (?:POE|MOE|FME)|Aca Starter|In Aca|In Hype|Short Edit|Aca Out)\)', '', s).strip()
    out['base'] = base
    return out

def build_name(base, key, bpm, mashup=False, bars=None, typ=None, aca_starter=False, after=None, short_edit=False, aca_out=False, open_show=False):
    p = base
    if mashup: p += ' (Mashup)'
    if open_show: p += ' (Open Show)'
    if aca_starter: p += ' (Aca Starter)'
    elif bars and typ: p += f' ({bars} Bars {typ})'
    if after: p += f' ({after})'
    if short_edit: p += ' (Short Edit)'
    if aca_out: p += ' (Aca Out)'
    return f'{p} - {key} - {int(round(bpm))}'

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

def guess_from_name(fname):
    """Último recurso: tono tipo (10A) y BPM tipo 74Bpm sacados del nombre del archivo."""
    b = os.path.basename(fname); key = bpm = None
    m = re.search(r'(?:^\(|\[|\s-\s)(\d{1,2}[AB])(?:\)|\]|\.|\s|$)', b)
    if m: key = m.group(1)
    m = re.search(r'(\d{2,3})\s*bpm', b, re.I) or re.search(r'\[(\d{2,3})\]', b) or re.search(r'\s(\d{2,3})(?:\s\d{2,3})?\.\w{3,4}$', b)
    if m: bpm = float(m.group(1))
    return bpm, key

# ───────────────────────── vectores para los modelos ─────────────────────────
def m(A, i, j): return A[max(i, 0):j].mean(0) if len(A[max(i, 0):j]) else np.zeros(NF, dtype=np.float32)

def boundary_x(A, k):
    d2 = m(A, k, k + 2) - m(A, k - 2, k); d1 = m(A, k, k + 1) - m(A, k - 1, k)
    oh = np.array([1.0 if k == c else 0.0 for c in CANDS], dtype=np.float32)
    return np.concatenate([d2, d1, m(A, k - 4, k), m(A, k, k + 4), oh])

def type_x(A, N): return np.concatenate([m(A, 0, N), m(A, 0, N) - m(A, N, N + 4)])
def after_x(A, N): return np.concatenate([m(A, N, N + 2), m(A, N, N + 2) - m(A, N + 2, N + 6), m(A, N + 2, N + 6)])
def starter_x(A): return np.concatenate([m(A, 0, 2), m(A, 0, 2) - m(A, 2, 6), m(A, 2, 6)])
def out_x(T): return np.concatenate([m(T, 6, 8), m(T, 6, 8) - m(T, 0, 4), m(T, 0, 4)]) if len(T) >= 8 else np.zeros(3 * NF, dtype=np.float32)
def short_x(f): return np.array([f['dur'] / 60, np.log(f['dur'] + 1), f['nbars'] / 100], dtype=np.float32)

# ───────────────────────── modelo: regresión logística multiclase en numpy ─────────────────────────
class Softmax:
    def __init__(self, classes): self.classes = list(classes)
    def fit(self, X, y, l2=0.05, iters=600, lr=0.05, w=None):
        X = np.asarray(X, dtype=np.float64); y = np.asarray(y)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-6
        Z = (X - self.mu) / self.sd; n, d = Z.shape; k = len(self.classes)
        Y = np.zeros((n, k)); idx = np.array([self.classes.index(v) for v in y]); Y[np.arange(n), idx] = 1
        cw = n / (k * np.maximum(Y.sum(0), 1)); sw = (Y * cw).sum(1)                      # pesos por clase (equilibra)
        if w is not None: sw = sw * np.asarray(w, dtype=np.float64) * (len(w) / max(np.sum(w), 1e-9))   # peso por muestra (revisadas pesan más)
        W = np.zeros((d, k)); b = np.zeros(k); mW = vW = np.zeros_like(W); mb = vb = np.zeros_like(b)
        for t in range(1, iters + 1):
            P = self._sm(Z @ W + b); G = (P - Y) * sw[:, None] / n
            gW, gb = Z.T @ G + l2 * W / n * 10, G.sum(0)
            mW = .9 * mW + .1 * gW; vW = .999 * vW + .001 * gW ** 2; mb = .9 * mb + .1 * gb; vb = .999 * vb + .001 * gb ** 2
            W -= lr * (mW / (1 - .9 ** t)) / (np.sqrt(vW / (1 - .999 ** t)) + 1e-8)
            b -= lr * (mb / (1 - .9 ** t)) / (np.sqrt(vb / (1 - .999 ** t)) + 1e-8)
        self.W, self.b = W, b; return self
    @staticmethod
    def _sm(z): z = z - z.max(1, keepdims=True); e = np.exp(z); return e / e.sum(1, keepdims=True)
    def proba(self, X): return self._sm(((np.asarray(X, dtype=np.float64) - self.mu) / self.sd) @ self.W + self.b)
    def dump(self, name, store):
        store[f'{name}__mu'], store[f'{name}__sd'], store[f'{name}__W'], store[f'{name}__b'] = self.mu, self.sd, self.W, self.b
        store[f'{name}__cl'] = np.array(self.classes, dtype=str)
    @classmethod
    def load(cls, name, z):
        o = cls(list(z[f'{name}__cl'])); o.mu, o.sd, o.W, o.b = z[f'{name}__mu'], z[f'{name}__sd'], z[f'{name}__W'], z[f'{name}__b']; return o

# ───────────────────────── dataset ─────────────────────────
def collect(folder):
    rows = []
    for root, _, files in os.walk(folder):
        for f in sorted(files):
            if not f.lower().endswith(EXT): continue
            p = parse_name(f)
            if not p['key'] or not p['bpm']: continue                      # solo pistas ya estandarizadas
            path = os.path.join(root, f); bpm, key = track_bpm_key(path)
            if not bpm: continue
            rows.append((path, p, bpm))
    return rows

def build_dataset(rows):
    D = {f'{p}_{k}': [] for p in ('bar', 'typ', 'aft', 'sta', 'out', 'sho') for k in ('X', 'y', 't', 'w')}; D['bar_k'] = []
    def add(pre, x, y, ti, w): D[pre + '_X'].append(x); D[pre + '_y'].append(y); D[pre + '_t'].append(ti); D[pre + '_w'].append(w)
    for ti, (path, p, bpm, *pre) in enumerate(rows):
        print(f'  [{ti + 1}/{len(rows)}] {os.path.basename(path)[:70]}', flush=True)
        try: f = pre[0] if pre and pre[0] else get_features(path, bpm)
        except Exception as e: print('    error:', e); continue
        w = float(pre[1]) if len(pre) > 1 else 1.0
        A = f['head']; N = p['bars']
        if N in CANDS and len(A) >= N + 4:
            for k in CANDS:
                if k + 4 <= len(A): add('bar', boundary_x(A, k), int(k == N), ti, w); D['bar_k'].append(k)
        if N and p['type'] and len(A) >= N + 4: add('typ', type_x(A, N), p['type'], ti, w)
        if N and len(A) >= N + 6: add('aft', after_x(A, N), p['after'] or 'none', ti, w)
        if len(A) >= 6: add('sta', starter_x(A), 'yes' if p['aca_starter'] else 'no', ti, w)
        if len(f['tail']) >= 8: add('out', out_x(f['tail']), 'yes' if p['aca_out'] else 'no', ti, w)
        add('sho', short_x(f), 'yes' if p['short_edit'] else 'no', ti, w)
    return {k: (np.array(v) if k.endswith('_X') else v) for k, v in D.items()}

TASKS = {  # nombre: (prefijo, clases)
    'bars': ('bar', [0, 1]), 'type': ('typ', TYPES), 'after': ('aft', ['none', 'In Aca', 'In Hype']),
    'starter': ('sta', ['no', 'yes']), 'aca_out': ('out', ['no', 'yes']), 'short': ('sho', ['no', 'yes'])}

def cv_predict(X, y, tr_ids, classes, K=5, w=None):
    """Validación cruzada por pista: devuelve probabilidades fuera de muestra."""
    ids = sorted(set(tr_ids)); rng = np.random.RandomState(0); rng.shuffle(ids)
    fold = {t: i % K for i, t in enumerate(ids)}; tf = np.array([fold[t] for t in tr_ids]); P = np.zeros((len(y), len(classes)))
    for k in range(K):
        tr, te = tf != k, tf == k
        if te.sum() == 0 or len(set(np.array(y)[tr])) < 2: continue
        sm = Softmax(classes).fit(X[tr], np.array(y)[tr], w=None if w is None else np.array(w)[tr]); P[te] = sm.proba(X[te])
    return P

def decide(classes, pr, thr):
    """Clase final: las raras ('yes', 'In Aca', 'In Hype') solo si superan el umbral."""
    if classes == TYPES: return classes[int(np.argmax(pr))]
    rare = [i for i, c in enumerate(classes) if c not in ('no', 'none')]
    common = [i for i, c in enumerate(classes) if c in ('no', 'none')][0]
    i = max(rare, key=lambda j: pr[j])
    return classes[i] if pr[i] >= thr else classes[common]

def best_threshold(task, classes, P, ya):
    if classes == TYPES: return 0.0, np.array(classes)[P.argmax(1)]
    rare = [c for c in classes if c not in ('no', 'none')]
    best = (-1, 0.5, None)
    for thr in np.arange(0.30, 0.97, 0.03):
        pred = np.array([decide(classes, p, thr) for p in P]); f = []
        for pos in rare:
            tp = ((pred == pos) & (ya == pos)).sum(); fp = ((pred == pos) & (ya != pos)).sum(); fn = ((pred != pos) & (ya == pos)).sum()
            f.append(2 * tp / max(2 * tp + fp + fn, 1))
        sc = float(np.mean(f))
        if sc > best[0]: best = (sc, float(thr), pred)
    return best[1], best[2]

def cmd_train(*folders):
    rows = [r for f in folders for r in collect(f)]; rows = rows + learned_rows(rows); print(f'{len(rows)} pistas con nombre estándar. Extrayendo características (la 1ª vez tarda; luego usa caché)...')
    if len(rows) < 6: print('Hacen falta más pistas.'); return
    D = build_dataset(rows); report = ['# Informe de entrenamiento djflow', f'Pistas: {len(rows)}', '']; store = {}
    for task, (pre, classes) in TASKS.items():
        X, y, t, wt = D[pre + '_X'], D[pre + '_y'], D[pre + '_t'], D[pre + '_w']
        if len(y) < 6 or len(set(y)) < 2: report.append(f'- **{task}**: sin datos suficientes'); continue
        npos = {c: int(np.sum(np.array(y) == c)) for c in classes}
        if task != 'bars' and min(v for c, v in npos.items() if c in set(y)) < 4 and len(set(y)) > 1 and task in ('starter', 'aca_out', 'short', 'after'):
            report.append(f'- **{task}**: muy pocos ejemplos positivos {npos}, no se entrena'); continue
        P = cv_predict(X, y, t, classes, w=wt); ya = np.array(y)
        if task == 'bars':
            hit = tot = 0; hi_hit = hi_tot = 0; kk = np.array(D['bar_k']); miss = {}
            for ti in sorted(set(t)):
                sel = np.array(t) == ti; pk = P[sel][:, 1]
                if pk.sum() == 0: continue
                ok = ya[sel][int(pk.argmax())] == 1; conf = pk.max() / pk.sum(); tot += 1; hit += ok
                if not ok and (ya[sel] == 1).any(): key = (int(kk[sel][ya[sel] == 1][0]), int(kk[sel][int(pk.argmax())])); miss[key] = miss.get(key, 0) + 1
                if conf >= .6: hi_tot += 1; hi_hit += ok
            report.append(f'- **barras del extender**: {hit}/{tot} exactas ({100 * hit / max(tot, 1):.0f} %). Con confianza ≥ 0,6: {hi_hit}/{hi_tot}')
            if miss: report.append('  - errores típicos (real → predicho): ' + ', '.join(f'{a}→{b} ({n})' for (a, b), n in sorted(miss.items(), key=lambda x: -x[1])[:5]))
        else:
            thr, pred = best_threshold(task, classes, P, ya)
            store[f'{task}__thr'] = np.array([thr])
            acc = (pred == ya).mean(); precs = []
            line = f'- **{task}**: acierto {100 * acc:.0f} % ({len(y)} muestras, reparto {npos}) · umbral {thr:.2f}'
            for pos in [c for c in classes if c in ('yes', 'In Aca', 'In Hype')]:
                tp = ((pred == pos) & (ya == pos)).sum(); fp = ((pred == pos) & (ya != pos)).sum(); fn = ((pred != pos) & (ya == pos)).sum()
                line += f' · {pos}: precisión {100 * tp / max(tp + fp, 1):.0f} %, recuperación {100 * tp / max(tp + fn, 1):.0f} %'
                precs.append(tp / max(tp + fp, 1))
            if precs and max(precs) < 0.30:
                store[f'{task}__thr'] = np.array([1.01]); line += ' · DESACTIVADO (demasiados falsos positivos; lo marcas tú)'
            report.append(line)
            if task in ('type', 'after'):
                cf = {}
                for a_, b_ in zip(ya, pred):
                    if a_ != b_: cf[(str(a_), str(b_))] = cf.get((str(a_), str(b_)), 0) + 1
                if cf: report.append(f'  - errores típicos en {task} (real → predicho): ' + ', '.join(f'{a}→{b} ({n})' for (a, b), n in sorted(cf.items(), key=lambda x: -x[1])[:5]))
        Softmax(classes).fit(X, y, w=wt).dump(task, store)
    np.savez_compressed(MODEL_PATH, **store)
    with open(os.path.join(HERE, 'informe.md'), 'w', encoding='utf-8') as fh: fh.write('\n'.join(report) + '\n')
    print('\n' + '\n'.join(report) + f'\n\nModelo guardado en {MODEL_PATH}\nInforme en {os.path.join(HERE, "informe.md")}')

# ───────────────────────── analizar / aplicar ─────────────────────────
def load_models():
    if not os.path.exists(MODEL_PATH): return {}
    z = np.load(MODEL_PATH, allow_pickle=False)
    names = {k.split('__')[0] for k in z.files if k.endswith('__cl')}
    out = {}
    for n in names:
        mo = Softmax.load(n, z); mo.thr = float(z[f'{n}__thr'][0]) if f'{n}__thr' in z.files else 0.5; out[n] = mo
    return out

def normalize_artist(a):
    """'Ozuna Ft Romeo Santos', 'A x B', 'A & B', 'A y B' -> 'Ozuna, Romeo Santos'."""
    parts = re.split(r'\s*(?:,|;|/|&|\+|\bfeat\.?|\bfeaturing\b|\bft\.?|\bwith\b|\s[xX]\s|\sY\s|\sy\s)\s*', a or '', flags=re.I)
    out = []
    for p in parts:
        p = re.sub(r'\s+', ' ', p).strip(' -_.')
        if p and p.lower() not in [o.lower() for o in out]: out.append(p)
    return ', '.join(out)

JUNK_SEG = re.compile(r'djtools|bpm|^\s*(cumbia|reggaeton|dembow|salsa|bachata|merengue|urbano|latino|pop|edm)\s*$|intro|outro|acapella|break|extended|clean|dirty|^\s*(6\d|[7-9]\d|1\d\d|200)\s*$|^\s*\d{1,2}[AB]\s*$|^\s*dj\s', re.I)

def _norm(t): return re.sub(r'[^a-z0-9 ]', '', t.lower()).strip()

def clean_title_pool(fname, artist_tag='', want_artist=False):
    """De un nombre de pool ('(10A) Artista - Canción (Extended Latino).mp3') deja solo el título."""
    s = os.path.splitext(os.path.basename(fname))[0]
    s = re.sub(r'^\s*\(\d{1,2}[AB]\)\s*', '', s); s = re.sub(r'^\s*\d{1,3}\.\s+', '', s)
    s = re.sub(r'\s*[-\s]\s*\d{1,2}[AB]\s*$', '', s)                     # tono al final
    remix = bool(re.search(r'\(\s*Remix\s*\)', s, re.I))
    s = re.sub(r'\([^)]*\)|\[[^\]]*\]', ' ', s)                          # fuera paréntesis y corchetes
    s = re.sub(r'\s+(6\d|[7-9]\d|1\d\d|200)(\s+\d{2,3})?\s*(bpm)?\s*$', '', s, flags=re.I)  # bpm suelto al final
    segs = [x.strip() for x in re.split(r'\s+-\s+', s) if x.strip()]
    def trim(x):
        m = re.search(r'\s+(acapella|intro|outro|hype|extended|bpm)\b', x, re.I)
        return x[:m.start()].strip() if m and m.start() > 2 else x
    segs = [trim(x) for x in segs]
    segs = [x for x in segs if not JUNK_SEG.search(x)] or segs
    at = {_norm(a) for a in re.split(r',|\bft\.?\b|\bfeat\.?\b|\bx\b|\by\b|&', artist_tag, flags=re.I) if a.strip()}
    def is_artist(x):
        parts = [_norm(a) for a in re.split(r',|\bft\.?\b|\bfeat\.?\b|&', x, flags=re.I) if a.strip()]
        if at and parts and sum(p in at or any(p in a or a in p for a in at if a) for p in parts) >= max(1, len(parts) // 2 + (len(parts) % 2)): return True
        return not at and (',' in x or re.search(r'\b(ft|feat)\b\.?', x, re.I) is not None)
    cand = [x for x in segs if not is_artist(x)]
    t = (cand[0] if len(cand) == len(segs) == 1 else (cand[0] if cand else segs[-1])) if len(segs) > 1 or cand else segs[0]
    if len(segs) == 2 and len(cand) == 2: t = segs[1]                        # 'Artista - Título' por defecto
    t = re.sub(r'\s+', ' ', t).strip(' -_')
    if t.isupper() and len(t) > 3: t = t.title()
    if remix and not re.search(r'remix', t, re.I): t += ' Remix'
    if want_artist:
        art = next((x for x in segs if x != re.sub(r'\s+', ' ', t).strip() and not JUNK_SEG.search(x) and x.lower() != t.lower()), '')
        return t, normalize_artist(art)
    return t

def predict_track(path, models):
    bpm, key = track_bpm_key(path); p = parse_name(path); guessed = False
    if not bpm or not key:
        gb, gk = guess_from_name(path); bpm, key = bpm or gb, key or gk; guessed = bool(bpm and key)
    if not bpm or not key: return dict(original=os.path.basename(path), proposed='', confidence=0, flags='sin BPM/tono: pasa antes Mixed In Key', final='', artist='')
    if is_done(path):
        nm = os.path.splitext(os.path.basename(path))[0]
        return dict(original=os.path.basename(path), proposed=nm, confidence=1.0, flags='ya procesada por Dmzeta Workflow: se respeta', final=nm, artist=normalize_artist(ffprobe_tags(path).get('artist', '')), bpm=bpm)
    # Ya renombrada antes (lleva etiquetas de la gramática): se respeta tal cual, no se vuelve a predecir
    if p['key'] and (p['bars'] or p['aca_starter'] or p['after'] or p['aca_out'] or p['short_edit'] or p['mashup'] or p['open_show']):
        nm = os.path.splitext(os.path.basename(path))[0]
        art = normalize_artist(ffprobe_tags(path).get('artist', ''))
        return dict(original=os.path.basename(path), proposed=nm, confidence=1.0, flags='ya renombrada: se respeta tu nombre', final=nm, artist=art, bpm=bpm)
    f = get_features(path, bpm); A = f['head']; flags = []; confs = []
    livem = 'live mashup' in os.path.basename(path).lower(); mashup = False
    atag = ffprobe_tags(path).get('artist', '')
    # Siempre se limpia: Mixed In Key ya añade ' - TONO - BPM' a nombres de pool sucios
    src = (p['base'] + os.path.splitext(path)[1]) if p['key'] else path
    base, art = clean_title_pool(src, atag, True); art = normalize_artist(atag) or art
    bars = typ = None; starter = False; after = None; short = False; aca_out = False
    if 'bars' in models:
        ks = [k for k in CANDS if k + 4 <= len(A)]
        if livem: ks = [k for k in ks if k in (4, 8)]
        if ks:
            pk = models['bars'].proba(np.array([boundary_x(A, k) for k in ks]))[:, 1]
            bars = ks[int(pk.argmax())]; c = float(pk.max() / max(pk.sum(), 1e-9)); confs.append(c)
            if c < .6: flags.append(f'barras dudosas ({bars})')
    if 'starter' in models and len(A) >= 6:
        mo = models['starter']; pr = mo.proba(starter_x(A)[None])[0]; starter = pr[1] >= mo.thr
        if abs(pr[1] - mo.thr) < .15: flags.append('¿Aca Starter?')
    if bars and 'type' in models and not starter:
        pr = models['type'].proba(type_x(A, bars)[None])[0]; typ = TYPES[int(pr.argmax())]; confs.append(float(pr.max()))
        if pr.max() < .6: flags.append(f'tipo dudoso ({typ})')
    if bars and 'after' in models and len(A) >= bars + 6:
        mo = models['after']; pr = mo.proba(after_x(A, bars)[None])[0]; a = decide(mo.classes, pr, mo.thr)
        after = None if a == 'none' else a
        if after: flags.append(f'¿{after}? (comprobar)')
    if 'short' in models and models['short'].proba(short_x(f)[None])[0][1] >= models['short'].thr: short = True; flags.append('¿Short Edit? (comprobar)')
    if 'aca_out' in models and len(f['tail']) >= 8 and models['aca_out'].proba(out_x(f['tail'])[None])[0][1] >= models['aca_out'].thr: aca_out = True; flags.append('¿Aca Out? (comprobar)')
    if re.search(r'\s[xX]\s', base):            # 'Título A x Título B' = mashup
        mashup = True; flags.insert(0, 'Título con "x": (Mashup) automático')
    if livem:                                   # regla fija: Live Mashup = 4/8 Bars MOE + Aca Out
        typ, starter, aca_out = 'MOE', False, True
        if not bars: bars = 8; flags.append('Live Mashup: compases por defecto (8), revisa 4 u 8')
        flags.insert(0, 'Live Mashup: regla fija (MOE, Aca Out)')
    proposed = build_name(base, key, bpm, mashup, None if starter else bars, typ, starter, after, short, aca_out)
    if not livem and 'mashup' in os.path.basename(path).lower(): flags.append('trae "Mashup" en el nombre: ¿(Mashup)?')
    gb, _gk = guess_from_name(path)
    if gb and bpm and (abs(bpm - 2 * gb) < 3 or abs(2 * bpm - gb) < 3): flags.append(f'BPM de Mixed In Key ({int(round(bpm))}) es el doble/mitad del del nombre ({int(gb)}): revisa')
    if guessed: flags.insert(0, 'BPM/tono sacados del NOMBRE, no de Mixed In Key')
    conf = round(min(confs) if confs else 0.0, 2)
    return dict(original=os.path.basename(path), proposed=proposed, confidence=conf, flags='; '.join(flags), final=proposed, artist=art, bpm=bpm)

def _tn(t): return re.sub(r'[^a-z0-9]', '', (t or '').lower())

def dup_index(xml_path):
    """Índice de tu colección (título limpio -> artistas y nombre completo) para avisar de duplicados."""
    import xml.etree.ElementTree as ET
    idx = {}
    for x in ET.parse(xml_path).getroot().find('COLLECTION').findall('TRACK'):
        nm = x.get('Name') or ''; base = _tn(parse_name(nm + '.mp3')['base'])
        if len(base) < 3: continue
        arts = {_tn(a) for a in re.split(r',|&|\bft\.?\b|\bfeat\.?\b', x.get('Artist') or '', flags=re.I) if a.strip()}
        idx.setdefault(base, []).append((arts, nm))
    return idx

def dup_check(idx, proposed, artist):
    if not idx or not proposed: return None
    base = _tn(parse_name(proposed + '.mp3')['base']); mine = {_tn(a) for a in re.split(r',', artist or '') if a.strip()}
    for arts, nm in idx.get(base, []):
        if not mine or not arts or (mine & arts) or any(a in b or b in a for a in mine for b in arts if a and b): return nm
    return None

def cmd_analyze(folder, xml=None):
    models = load_models()
    if not models: print('Aviso: no hay modelo entrenado (ejecuta "train" primero). Las barras/tipo no se proponen.')
    mm = load_marks_model(); gm = load_genre_model(); dups = None
    if xml and os.path.exists(xml):
        try: dups = dup_index(xml); print(f'Duplicados: comparando con {sum(len(v) for v in dups.values())} pistas de tu colección.')
        except Exception as e: print('No se pudo leer el XML para duplicados:', e)
    if not mm: print('Aviso: START MIX no se propone ' + ('(el modelo no supera al azar, lo marcas tú).' if os.path.exists(MARKS_MODEL) else '(sin modelo: usa «Aprender START MIX»).'))
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(EXT)); rows = []; marks = load_marks(folder)
    for i, f in enumerate(files, 1):
        print(f'[{i}/{len(files)}] {f}', flush=True)
        path = os.path.join(folder, f)
        try: r = predict_track(path, models)
        except Exception as e: rows.append(dict(original=f, proposed='', confidence=0, flags=f'error: {e}', final='', artist='')); continue
        d = dup_check(dups, r['proposed'], r.get('artist', ''))
        if d: r['flags'] = f'DUPLICADO: ya tienes "{d}"; ' + r['flags']
        old = marks.get(f) or {}
        if mm and r.get('bpm') and r['proposed'] and (not old or old.get('auto')):
            try:
                t0, bref, _ = detect_grid(path, r['bpm']); mk = propose_start(path, bref, t0, mm, parse_name(r['proposed'] + '.mp3')['bars'] or 0)
                if mk: marks[f] = mk; r['flags'] += f'; START MIX propuesto: compás {mk["start"]} (confianza {mk["conf"]})' + (' DUDOSO' if mk['conf'] < 0.35 else '')
            except Exception as e: print('   sin propuesta de START MIX:', e)
        if gm and r.get('bpm') and r['proposed']:
            try:
                t0g = detect_grid(path, r['bpm'])[0]; pm = predict_meta(path, r['bpm'], t0g); mk_ = marks.setdefault(f, {})
                if pm.get('genre') and not mk_.get('genre'): mk_['genre'], mk_['genre_conf'], mk_['genre_top'] = pm['genre'][0], round(pm['genre'][1], 2), pm['genre'][2]
                if pm.get('cat') and not mk_.get('cat'): mk_['cat'], mk_['cat_conf'], mk_['cat_top'] = pm['cat'][0], round(pm['cat'][1], 2), pm['cat'][2]
                if pm.get('stars') and not mk_.get('stars'): mk_['stars'] = int(pm['stars'][0]); mk_['stars_auto'] = True
            except Exception as e: print('   sin género:', e)
        rows.append(r)
    rows.sort(key=lambda r: r['confidence'])
    out = os.path.join(folder, 'review.csv')
    with open(out, 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh); w.writerow(['original', 'proposed', 'confidence', 'flags', 'final', 'artist'])
        for r in rows: w.writerow([r['original'], r['proposed'], r['confidence'], r['flags'], r['final'], r.get('artist', '')])
    if marks: save_marks(folder, marks)
    print(f'\nListo: {out}\nAbre el CSV: las dudosas salen primero. Corrige "final" (vacío = no renombrar). Después:\n  python3 djflow.py apply "{folder}"')

def clean_tags(path, artist=None):
    """Deja solo: título (= nombre del archivo), artista, álbum (= carpeta), BPM y tono. Quita portada y el resto. Audio sin recodificar."""
    ext = os.path.splitext(path)[1].lower(); tg = ffprobe_tags(path); p = parse_name(path)
    bpm = tg.get('tbpm') or tg.get('bpm') or (str(int(p['bpm'])) if p['bpm'] else '')
    key = tg.get('tkey') or tg.get('initialkey') or p['key'] or ''
    if bpm:
        try: bpm = str(int(round(float(bpm))))
        except ValueError: pass
    title = os.path.splitext(os.path.basename(path))[0]
    artist = normalize_artist(artist if artist else tg.get('artist', '')); album = os.path.basename(os.path.dirname(os.path.abspath(path)))
    kb, kk = {'.mp3': ('TBPM', 'TKEY'), '.flac': ('BPM', 'INITIALKEY'), '.m4a': ('tmpo', 'initialkey')}.get(ext, ('BPM', 'INITIALKEY'))
    cmd = ['ffmpeg', '-v', 'error', '-y', '-i', path, '-map', '0:a:0', '-map_metadata', '-1', '-fflags', '+bitexact', '-c', 'copy',
           '-metadata', f'title={title}', '-metadata', f'artist={artist}', '-metadata', f'album={album}']
    if bpm: cmd += ['-metadata', f'{kb}={bpm}']
    if key: cmd += ['-metadata', f'{kk}={key}']
    if ext == '.mp3': cmd += ['-id3v2_version', '3', '-write_id3v1', '0']
    tmp = path + '.tmp' + ext; cmd.append(tmp)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 1000:
        if os.path.exists(tmp): os.remove(tmp)
        return False
    os.replace(tmp, path); return True

def cmd_clean(folder, artists=None, only=None):
    n = 0; artists = artists or {}
    for f in sorted(os.listdir(folder)):
        if only is not None and f not in only: continue
        if f.lower().endswith(EXT) and clean_tags(os.path.join(folder, f), artists.get(f)): n += 1
    print(f'{n} archivos con tags limpios (título, artista, álbum=carpeta, BPM, tono).')

# ───────────────────────── cues para Rekordbox (XML) ─────────────────────────
def learn_cue_rules(xml_path):
    """Aprende de tu colección: posición (en compases desde el primer beat) y color de INTRO y hot cues A, B, C."""
    import xml.etree.ElementTree as ET
    from collections import Counter
    root = ET.parse(xml_path).getroot(); offs = {n: Counter() for n in ('0', '1', '2')}; cols = {n: Counter() for n in ('0', '1', '2')}
    t0s = []; used = 0; mcol = {k: Counter() for k in ('intro', 'start', 'end', 'loop')}; o45, oend, olen = Counter(), Counter(), Counter(); xcol = {n: Counter() for n in ('3', '4', '5', '6', '7')}
    for x in root.find('COLLECTION').findall('TRACK'):
        nm = x.get('Name') or ''; m = re.search(r'- \d{1,2}[AB] - (\d+)$', nm)
        if not m: continue
        pm = x.findall('POSITION_MARK'); h = {p.get('Num'): p for p in pm if p.get('Type') == '0' and p.get('Num') in offs}
        bpm = float(x.get('AverageBpm') or 0) or float(m.group(1))
        if '0' not in h or bpm <= 0: continue
        used += 1; bar = 240.0 / bpm; t0 = float(h['0'].get('Start')); t0s.append(t0)
        hh = {p.get('Num'): p for p in pm if p.get('Num') in ('3', '4', '5', '6', '7')}
        for p in pm:
            if p.get('Num') == '-1' and p.get('Red'):
                nu = (p.get('Name') or '').strip().upper(); k = 'intro' if nu.startswith('INTRO') else 'start' if nu.startswith('START MIX') else 'end' if nu.startswith('END MIX') else 'loop' if nu.startswith('END LOOP') else None
                if k: mcol[k][(int(p.get('Red')), int(p.get('Green')), int(p.get('Blue')))] += 1
        for n, p in hh.items():
            if p.get('Red'): xcol[n][(int(p.get('Red')), int(p.get('Green')), int(p.get('Blue')))] += 1
        if '4' in hh and '5' in hh and hh['4'].get('Type') == '0': o45[round((float(hh['5'].get('Start')) - float(hh['4'].get('Start'))) / bar)] += 1
        sm = [p for p in pm if p.get('Num') == '-1' and (p.get('Name') or '').strip().startswith('START MIX')]; em = [p for p in pm if p.get('Num') == '-1' and (p.get('Name') or '').strip().startswith('END MIX')]
        if sm and em: oend[round((float(em[0].get('Start')) - float(sm[0].get('Start'))) / bar)] += 1
        if '7' in hh and hh['7'].get('End'): olen[round((float(hh['7'].get('End')) - float(hh['7'].get('Start'))) / bar)] += 1
        for p in pm:
            if p.get('Num') == '-1' and p.get('Type') == '4' and p.get('End') and (p.get('Name') or '').strip().upper().startswith('END LOOP'): olen[round((float(p.get('End')) - float(p.get('Start'))) / bar)] += 1
        for n, p in h.items():
            offs[n][round((float(p.get('Start')) - t0) / bar)] += 1
            if p.get('Red'): cols[n][(int(p.get('Red')), int(p.get('Green')), int(p.get('Blue')))] += 1
    if used < 20: raise SystemExit(f'Solo {used} pistas con nombre estándar y cues en el XML; hacen falta al menos 20.')
    rules = {n: (offs[n].most_common(1)[0][0] if offs[n] else d, cols[n].most_common(1)[0][0] if cols[n] else (40, 226, 20)) for n, d in (('0', 0), ('1', 4), ('2', 8))}
    rules['x'] = dict(off5=(o45.most_common(1)[0][0] if o45 else 4), end=(oend.most_common(1)[0][0] if oend else 8), loop=(olen.most_common(1)[0][0] if olen else 8),
                      mem={k: (c.most_common(1)[0][0] if c else None) for k, c in mcol.items()},
                      col={n: (xcol[n].most_common(1)[0][0] if xcol[n] else d) for n, d in (('3', None), ('4', (16, 177, 118)), ('5', (16, 177, 118)), ('6', None), ('7', (255, 18, 123)))})
    return rules, float(np.median(t0s)), used

GRID_N, GRID_HOP = 1024, 128
GRID_CACHE = os.path.join(HERE, 'cache')

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

_DELAY = {}
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

CAL = 0.040   # el pico del flujo llega ~30 ms antes del golpe (ventana de 46 ms)

def first_beat(path, default, bpm=None):
    """Primer beat detectado del audio (si hay BPM); si no, el valor por defecto."""
    if bpm:
        try: return round(detect_grid(path, bpm)[0], 3)
        except Exception: pass
    return default

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
    y = np.clip(y, -1, 1); out = out or os.path.join(HERE, 'preview.wav')
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
    y = np.clip(y, -1, 1); out = out or os.path.join(HERE, 'preview.wav')
    with wave.open(out, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SRP); w.writeframes((y * 32767).astype('<i2').tobytes())
    return out

# ───────────────────────── START MIX: aprender de tu colección ─────────────────────────
MARKS_MODEL = os.path.join(HERE, 'model_marks.npz')
START_KS_MAX = 80

def struct_matrix(path, bpm, t0, nbars=100):
    """Características por compás desde el primer beat (hasta 100 compases) + duración. Con caché."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    fp = os.path.join(CACHE_DIR, 'st_' + hashlib.md5(f'{os.path.abspath(path)}|{os.path.getsize(path)}|{int(os.path.getmtime(path))}|{bpm:.2f}|{t0:.2f}'.encode()).hexdigest() + '.npz')
    if os.path.exists(fp): z = np.load(fp); return z['A'], float(z['dur'])
    y = decode(path); dur = len(y) / SR; a = int(max(0.0, t0) * SR); b = a + int(((nbars + 2) * 240.0 / bpm) * SR)
    A = bar_matrix(stft(y[a:b]), bpm, nbars); np.savez_compressed(fp, A=A, dur=dur); return A, dur

def start_x(A, k):
    d4 = m(A, k, k + 4) - m(A, k - 4, k); d8 = m(A, k, k + 8) - m(A, k - 8, k)
    return np.concatenate([m(A, k - 4, k), m(A, k, k + 4), d4, d8, [k / 64.0, 1.0 if k % 8 == 0 else 0.0]])

def start_X(A, N=0):
    """Candidatos a START MIX con características de ESTRUCTURA: ordinal del subidón de energía (¿es el 1.º, 2.º…?), parecido con secciones anteriores (el 2.º coro repite al 1.º) y distancia al final del extender."""
    ks = start_candidates(A)
    if not ks: return [], np.zeros((0, 1))
    Z = (A - A.mean(0)) / (A.std(0) + 1e-6); n = len(Z); e = Z[:, :3].mean(1); v = Z[:, 3]
    def rise(j, col):
        a, b = col[max(j - 4, 0):j], col[j:j + 4]
        return float(b.mean() - a.mean()) if len(a) and len(b) else 0.0
    rows = []
    for k in ks:
        prior = sum(1 for j in range(8, k, 4) if rise(j, e) > 0.6); ordv = np.zeros(4, dtype=np.float32); ordv[min(prior, 3)] = 1
        wk = Z[k:k + 8].ravel(); L = len(wk); sims = []
        for j in range(8, k - 7, 4):
            wj = Z[j:j + 8].ravel()
            if len(wj) == L and L: sims.append(float(wk @ wj / (np.linalg.norm(wk) * np.linalg.norm(wj) + 1e-9)))
        r0 = rise(k, e); loc = r0 - max(rise(k - 4, e), rise(k + 4, e))
        extra = [r0, rise(k, v), loc, max(sims) if sims else 0.0, float(np.mean(sims)) if sims else 0.0, (k - N) / 64.0 if N else 0.0, 1.0 if N else 0.0, prior / 4.0]
        rows.append(np.concatenate([start_x(A, k), ordv, np.array(extra, dtype=np.float32)]))
    return ks, np.array(rows)

def start_candidates(A): return [k for k in range(16, START_KS_MAX + 1, 4) if k + 4 <= len(A)]

def propose_start(path, bpm, t0, model, N=0):
    """Compás propuesto para START MIX, END MIX (+8) y loop final. Devuelve dict de marcas o None."""
    if model is None: return None
    A, dur = struct_matrix(path, bpm, t0); ks, XX = start_X(A, N)
    if len(ks) < 3: return None
    p = model.proba(XX)[:, 1]; i = int(p.argmax()); k = ks[i]; conf = float(p[i] / max(p.sum(), 1e-9))
    gap, ll = _pref('gaps', 8), _pref('loops', 8)
    out = dict(start=k, end=k + gap, conf=round(conf, 2), auto=True)
    total = int((dur - t0) / (240.0 / bpm)); ls = total - ll - 1
    if ls > k + gap: out['loop'] = [ls, ll]
    return out

def load_marks_model():
    if not os.path.exists(MARKS_MODEL): return None
    z = np.load(MARKS_MODEL, allow_pickle=False)
    if 'start__off' in z.files and int(z['start__off'][0]) == 1: return None
    if 'start2__cl' not in z.files: return None
    return Softmax.load('start2', z)

def cmd_train_marks(xml_path, limit=1200):
    """Aprende dónde pones START MIX mirando tus pistas en rekordbox.xml (necesita los archivos de audio en las rutas del XML)."""
    import xml.etree.ElementTree as ET
    from urllib.parse import unquote
    limit = int(limit); items = []
    root = ET.parse(xml_path).getroot() if xml_path and os.path.exists(xml_path) else None
    for x in (root.find('COLLECTION').findall('TRACK') if root is not None else []):
        nm = x.get('Name') or ''; mm = re.search(r'- \d{1,2}[AB] - (\d+)$', nm)
        if not mm: continue
        loc = unquote((x.get('Location') or '').replace('file://localhost', '').replace('file://', ''))
        if not os.path.exists(loc): continue
        pm = x.findall('POSITION_MARK'); h0 = [p for p in pm if p.get('Num') == '0' and p.get('Type') == '0']
        st = [p for p in pm if p.get('Num') == '4' and p.get('Type') == '0'] or [p for p in pm if p.get('Num') == '-1' and (p.get('Name') or '').strip().startswith('START MIX')]
        bpm = float(x.get('AverageBpm') or 0) or float(mm.group(1))
        if not (h0 and st) or bpm <= 0: continue
        t0 = float(h0[0].get('Start')); sb = round((float(st[0].get('Start')) - t0) / (240.0 / bpm))
        if 16 <= sb <= START_KS_MAX: items.append((loc, bpm, t0, int(round(sb / 4.0) * 4), parse_name(nm + '.mp3')['bars'] or 0))
    learned = []
    if os.path.isdir(LEARN_MARKS_DIR):
        for fn in sorted(os.listdir(LEARN_MARKS_DIR)):
            if fn.endswith('.npz'): z = np.load(os.path.join(LEARN_MARKS_DIR, fn)); learned.append((z['A'], int(z['target']), float(z['weight']), int(z['N']) if 'N' in z.files else 0))
    print(f'{len(items)} pistas con START MIX en el XML + {len(learned)} marcas tuyas aprendidas.')
    if len(items) + len(learned) < 40: raise SystemExit('Hacen falta al menos 40 pistas con START MIX (de tu XML y de tus marcas). Revisa que las rutas del XML existan.')
    rng = np.random.RandomState(0); rng.shuffle(items); items = items[:limit]
    X, y, t, tg, W = [], [], [], [], []
    for ti, (loc, bpm, t0, target, N) in enumerate(items):
        print(f'  [{ti + 1}/{len(items)}] {os.path.basename(loc)[:70]}', flush=True)
        try: A, _ = struct_matrix(loc, bpm, t0)
        except Exception as e: print('    error:', e); continue
        ks_, XX = start_X(A, N)
        for k, xr in zip(ks_, XX): X.append(xr); y.append(int(k == target)); t.append(ti); W.append(1.0)
        tg.append(target)
    TG = [it[3] for it in items]
    for j, (A, target, wt, N) in enumerate(learned):
        ti = len(items) + j; TG.append(target); ks_, XX = start_X(A, N)
        for k, xr in zip(ks_, XX): X.append(xr); y.append(int(k == target)); t.append(ti); W.append(wt)
    X = np.array(X); P = cv_predict(X, y, t, [0, 1], w=W); ya = np.array(y); ex = w4 = w8 = tot = 0; ks_all = {}
    for ti in sorted(set(t)):
        sel = np.array(t) == ti; pk = P[sel][:, 1]
        if pk.sum() == 0: continue
        tgt = TG[ti]; cand = [x for x in range(16, START_KS_MAX + 1, 4)][:int(sel.sum())]; pred = cand[int(pk.argmax())]
        tot += 1; ex += pred == tgt; w4 += abs(pred - tgt) <= 4; w8 += abs(pred - tgt) <= 8
    from collections import Counter
    base = Counter(TG).most_common(1)[0]; basepct = 100 * base[1] / max(len(TG), 1)
    rep = ['# Informe START MIX', f'Pistas: {tot}', f'- exacto (±0 compases): {100 * ex / max(tot, 1):.0f} %', f'- a ±4 compases: {100 * w4 / max(tot, 1):.0f} %', f'- a ±8 compases: {100 * w8 / max(tot, 1):.0f} %',
           f'- referencia (siempre el compás {base[0]}): {basepct:.0f} %']
    useful = tot > 0 and ex / tot >= basepct / 100 + 0.08
    if not useful: rep.append('- ESTADO: DESACTIVADO. No supera claramente a elegir siempre el mismo compás, así que no se propone START MIX; lo marcas tú. Se reintentará al juntar más marcas tuyas.')
    else: rep.append('- ESTADO: ACTIVO (supera a la referencia).')
    store = {'start__off': np.array([0 if useful else 1])}; Softmax([0, 1]).fit(X, y, w=W).dump('start2', store); np.savez_compressed(MARKS_MODEL, **store)
    open(os.path.join(HERE, 'informe_marks.md'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n'); print('\n' + '\n'.join(rep) + f'\n\nModelo guardado en {MARKS_MODEL}')
    if xml_path and os.path.exists(xml_path):
        try: train_cvox(xml_path)
        except BaseException as e: print('No se pudo aprender el color del cue C:', e)

CVOX_MODEL = os.path.join(HERE, 'model_cvox2.npz')
LEARN_CVOX_DIR = os.path.join(HERE, 'learned_cvox')
RED_C, LIME_C = (230, 40, 40), (165, 225, 22)

def cvox_x(A, N):
    """Una sola señal: cuánta voz hay en los 4 compases que siguen al extender (la que mejor separa rojo/lima en tus 36 pistas corregidas)."""
    return np.array([float(m(A, N, N + 4)[3])])

def load_cvox():
    if not os.path.exists(CVOX_MODEL): return None
    z = np.load(CVOX_MODEL, allow_pickle=False)
    if 'cvox2__cl' not in z.files or ('cvox__off' in z.files and int(z['cvox__off'][0]) == 1): return None
    return Softmax.load('cvox2', z)

def cue_c_color(path, bpm, t0, fname, model=None):
    """Color del hot cue C: rojo si entra voz antes de acabar el extender (o empieza con acapella), verde lima si no. None = sin modelo."""
    p = parse_name(fname)
    if p['aca_starter']: return 'red'
    model = model or load_cvox()
    if model is None or not p['bars']: return None
    try:
        A, _ = struct_matrix(path, bpm, t0)
        return 'red' if model.proba(cvox_x(A, p['bars'])[None])[0][1] >= 0.5 else 'lime'
    except Exception: return None

def train_cvox(xml_path=None, min_n=20):
    """Aprende el color del cue C SOLO de tus pistas corregidas (carpeta learned_cvox), no de la colección del XML."""
    learned = []
    if os.path.isdir(LEARN_CVOX_DIR):
        for fn in sorted(os.listdir(LEARN_CVOX_DIR)):
            if fn.endswith('.npz'): z = np.load(os.path.join(LEARN_CVOX_DIR, fn)); learned.append((z['A'], int(z['N']), int(z['y'])))
    print(f'Color del cue C: {len(learned)} pistas corregidas por ti.')
    if len(learned) < min_n: print(f'Hacen falta al menos {min_n}; sin modelo el color del C no se propone (lo eliges tú).'); return
    X = np.array([cvox_x(A, N) for A, N, _ in learned]); y = np.array([l for _, _, l in learned])
    if y.min() == y.max(): print('Todas las pistas tienen el mismo color: no se aprende.'); return
    P = cv_predict(X, y, list(range(len(y))), [0, 1]); acc = float(((P[:, 1] >= .5) == (y == 1)).mean()); base = max(y.mean(), 1 - y.mean()); ok = acc >= base + 0.05
    rep = ['# Informe color del cue C', f'Pistas corregidas por ti: {len(y)} (rojas: {int(y.sum())})', f'- acierto (validación cruzada): {100 * acc:.0f} %  (referencia, elegir siempre lo más habitual: {100 * base:.0f} %)',
           '- ESTADO: ' + ('ACTIVO' if ok else 'DESACTIVADO (no supera a la referencia: eliges tú el color)')]
    store = {'cvox__off': np.array([0 if ok else 1])}; Softmax([0, 1]).fit(X, y).dump('cvox2', store); np.savez_compressed(CVOX_MODEL, **store)
    open(os.path.join(HERE, 'informe_cvox.md'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n'); print('\n' + '\n'.join(rep))

LAST_APPLIED = None

# ───────────────────────── género ─────────────────────────
GENRE_MODEL = os.path.join(HERE, 'model_genre.npz')

def genre_x(A, bpm):
    """Resumen de la pista para el género: timbre medio y variación (energía, graves, voz, hats…), estructura y zona de BPM."""
    n = len(A)
    if n < 4: A = np.vstack([A, np.zeros((4 - n, NF), dtype=np.float32)]) if n else np.zeros((4, NF), dtype=np.float32)
    bins = np.zeros(29, dtype=np.float32); bins[int(np.clip((bpm - 60) // 5, 0, 28))] = 1
    return np.concatenate([A.mean(0), A.std(0), m(A, 0, 8), m(A, 32, 64), bins, [np.log(max(bpm, 1.0)), bpm / 100.0]]).astype(np.float32)

_GEN_CACHE = {}
def xml_genres(xml_path):
    """Géneros de tu colección, del más al menos usado (para el desplegable)."""
    from collections import Counter
    import xml.etree.ElementTree as ET
    if not xml_path or not os.path.exists(xml_path): return []
    k = (xml_path, os.path.getmtime(xml_path))
    if k not in _GEN_CACHE:
        try: _GEN_CACHE[k] = [g for g, _ in Counter((x.get('Genre') or '').strip() for x in ET.parse(xml_path).getroot().find('COLLECTION').findall('TRACK')).most_common(60) if g]
        except Exception: _GEN_CACHE[k] = []
    return _GEN_CACHE[k]

CATS = [('Pink', 'FF007F'), ('Review', 'FF0000'), ('Build Up', 'FFA500'), ('Warm Up', 'FFFF00'), ('Peak Time', '00FF00'), ('Chill Out', '25FDE9'), ('Samples', '0000FF'), ('Closing', '660099')]
CAT_HEX = {n: h for n, h in CATS}; HEX_CAT = {h: n for n, h in CATS}

def predict_meta(path, bpm, t0=0.0):
    """Género, categoría (color de Rekordbox) y estrellas propuestos; solo lo que el modelo entrenado supera al azar."""
    if not os.path.exists(GENRE_MODEL): return {}
    z = np.load(GENRE_MODEL, allow_pickle=False); out = {}
    try:
        A, _ = struct_matrix(path, bpm, t0); x = genre_x(A, bpm)[None]
        for nm, key in (('genre', 'genre'), ('cat', 'cat'), ('star', 'stars')):
            if f'{nm}__cl' not in z.files or (f'{nm}__off' in z.files and int(z[f'{nm}__off'][0]) == 1): continue
            mo = Softmax.load(nm, z); pr = mo.proba(x)[0]; o = np.argsort(-pr)
            out[key] = (str(mo.classes[o[0]]), float(pr[o[0]]), [str(mo.classes[i]) for i in o[:3]])
    except Exception as e: print('   sin meta:', e)
    return out

def load_genre_model():
    if not os.path.exists(GENRE_MODEL): return None
    z = np.load(GENRE_MODEL, allow_pickle=False)
    if 'genre__cl' not in z.files: return None
    return Softmax.load('genre', z)

def predict_genre(path, bpm, t0=0.0, model=None):
    """Devuelve (genero, confianza, top3) o None."""
    model = model or load_genre_model()
    if model is None: return None
    try:
        A, _ = struct_matrix(path, bpm, t0); pr = model.proba(genre_x(A, bpm)[None])[0]; o = np.argsort(-pr)
        return str(model.classes[o[0]]), float(pr[o[0]]), [str(model.classes[i]) for i in o[:3]]
    except Exception: return None

def train_genre(xml_path, limit=2500, min_n=25):
    """Aprende el género de tu colección (campo Genre de rekordbox.xml) a partir del audio y el BPM."""
    import xml.etree.ElementTree as ET
    from urllib.parse import unquote
    from collections import Counter
    items = []
    for x in ET.parse(xml_path).getroot().find('COLLECTION').findall('TRACK'):
        g = (x.get('Genre') or '').strip(); bpm = float(x.get('AverageBpm') or 0)
        if not g or bpm <= 0: continue
        loc = unquote((x.get('Location') or '').replace('file://localhost', '').replace('file://', ''))
        if not os.path.exists(loc): continue
        h0 = [q for q in x.findall('POSITION_MARK') if q.get('Num') == '0' and q.get('Type') == '0']
        cat = HEX_CAT.get((x.get('Colour') or '').replace('0x', '').upper(), ''); st = str(round(int(x.get('Rating') or 0) / 51)) if int(x.get('Rating') or 0) > 0 else ''
        items.append((loc, bpm, float(h0[0].get('Start')) if h0 else 0.0, g, cat, st))
    cnt = Counter(it[3] for it in items); keep = {g for g, c in cnt.items() if c >= int(min_n)}
    items = [it for it in items if it[3] in keep]
    print(f'Género: {len(items)} pistas con género y archivo accesible, {len(keep)} géneros con al menos {min_n} pistas.')
    if len(items) < 150 or len(keep) < 3: print('Hacen falta al menos 150 pistas con género; no se entrena el género.'); return
    rng = np.random.RandomState(0); rng.shuffle(items); items = items[:int(limit)]; X, y, t = [], [], []
    CY, SY = [], []
    for ti, (loc, bpm, t0, g, cat_, st_) in enumerate(items):
        print(f'  [{ti + 1}/{len(items)}] {os.path.basename(loc)[:70]}', flush=True)
        try: A, _ = struct_matrix(loc, bpm, t0)
        except Exception as e: print('    error:', e); continue
        X.append(genre_x(A, bpm)); y.append(g); t.append(ti); CY.append(cat_); SY.append(st_)
    X = np.array(X); ya = np.array(y); classes = sorted(set(y)); P = cv_predict(X, ya, t, classes)
    top1 = float((np.array(classes)[P.argmax(1)] == ya).mean()); top3 = float(np.mean([ya[i] in np.array(classes)[np.argsort(-P[i])[:3]] for i in range(len(ya))]))
    base = Counter(y).most_common(1)[0]; dist = ', '.join(f'{g} {c}' for g, c in Counter(y).most_common(6))
    rep = ['# Informe de género', f'Pistas: {len(y)} · géneros: {len(classes)}', f'- acierto del primero: {100 * top1:.0f} %', f'- el correcto entre los 3 primeros: {100 * top3:.0f} %',
           f'- referencia (siempre «{base[0]}»): {100 * base[1] / len(y):.0f} %', f'- reparto: {dist}']
    store = {}; Softmax(classes).fit(X, ya).dump('genre', store)
    for nm, lab, nom in (('cat', CY, 'categoría (color)'), ('star', SY, 'estrellas')):                  # mismas características de audio, sin volver a analizar
        idx = [i for i, v in enumerate(lab) if v]
        if len(idx) < 150 or len(set(lab[i] for i in idx)) < 2: rep.append(f'- {nom}: pocas pistas con dato, no se aprende'); continue
        Xs, ys = X[idx], np.array([lab[i] for i in idx]); cls = sorted(set(ys)); Ps = cv_predict(Xs, ys, [t[i] for i in idx], cls)
        acc = float((np.array(cls)[Ps.argmax(1)] == ys).mean()); b0 = Counter(ys).most_common(1)[0][1] / len(ys); ok = acc >= b0 + 0.05
        Softmax(cls).fit(Xs, ys).dump(nm, store); store[f'{nm}__off'] = np.array([0 if ok else 1])
        rep.append(f'- {nom}: acierto {100 * acc:.0f} % (siempre la más común: {100 * b0:.0f} %) → ' + ('se propone solo' if ok else 'NO supera al azar: se rellena a mano'))
    np.savez_compressed(GENRE_MODEL, **store)
    open(os.path.join(HERE, 'informe_genre.md'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n'); print('\n' + '\n'.join(rep))

def learn_from_xml(xml_path):
    """Todo lo que se aprende de tu rekordbox.xml: START MIX, color del cue C y género. Devuelve el informe junto."""
    out = []
    for fn, rf in ((cmd_train_marks, 'informe_marks.md'), (train_genre, 'informe_genre.md')):
        try: fn(xml_path)
        except BaseException as e: print('  (se salta:', e, ')')
        for r in (rf, 'informe_cvox.md') if rf == 'informe_marks.md' else (rf,):
            p = os.path.join(HERE, r)
            if os.path.exists(p): out.append(open(p, encoding='utf-8').read())
    return '\n'.join(out)

def remember_marks(folder, applied):
    """Aprende de tus marcas manuales (START/END MIX, loop): guarda la estructura de la pista y tus preferencias de hueco y duración."""
    marks = load_marks(folder); prefs = load_prefs(); gaps = prefs.setdefault('gaps', {}); loops = prefs.setdefault('loops', {}); made = 0
    os.makedirs(LEARN_MARKS_DIR, exist_ok=True)
    gl = prefs.setdefault('grid2', []); gfix = 0; cfix = 0
    os.makedirs(LEARN_CVOX_DIR, exist_ok=True)
    for f in sorted(applied):
        mk = marks.get(f) or {}
        if mk.get('t0') is not None:                       # grid corregido por ti: aprende el desvío respecto al detectado
            try:
                path = os.path.join(folder, f); bpm0, _ = track_bpm_key(path)
                if bpm0:
                    raw_t0 = detect_grid(path, bpm0, raw=True)[0]; beat = 60.0 / bpm0; dlt = float(mk['t0']) - raw_t0
                    fold = (dlt + beat / 2) % beat - beat / 2
                    if abs(fold) <= 0.08: gl.append(round(fold * 1000, 1)); gfix += 1
            except Exception as e: print('  grid no aprendido para', f, ':', e)
        cm = mk.get('ccol')
        if cm is None and mk.get('ok') and parse_name(f)['bars']:                       # color automático que diste por bueno con ✓
            try:
                path_ = os.path.join(folder, f); b_ = track_bpm_key(path_)[0]; t_ = float(mk['t0']) if mk.get('t0') is not None else detect_grid(path_, b_)[0]
                cc_ = cue_c_color(path_, float(mk.get('bpm') or b_), t_, f)
                cm = {'red': RED_C, 'lime': LIME_C}.get(cc_)
            except Exception: cm = None
        if isinstance(cm, (list, tuple)) and tuple(cm) in (RED_C, LIME_C) and parse_name(f)['bars']:   # color del C corregido por ti: ejemplo para el modelo
            try:
                path = os.path.join(folder, f); bpm0, _ = track_bpm_key(path)
                t0c = float(mk['t0']) if mk.get('t0') is not None else detect_grid(path, bpm0)[0]
                A, _ = struct_matrix(path, float(mk.get('bpm') or bpm0), t0c)
                np.savez_compressed(os.path.join(LEARN_CVOX_DIR, hashlib.md5(f'{f}|{os.path.getsize(path)}'.encode()).hexdigest() + '.npz'), A=A, N=parse_name(f)['bars'], y=int(tuple(cm) == RED_C)); cfix += 1
            except Exception as e: print('  color del C no aprendido para', f, ':', e)
        if mk.get('start') is None or (mk.get('auto') and not mk.get('ok')): continue      # propuesta automática sin confirmar: no se aprende
        if mk.get('end') is not None: g = str(int(mk['end'] - mk['start'])); gaps[g] = gaps.get(g, 0) + 1
        if mk.get('loop') and not mk.get('loopAuto'): l = str(int(mk['loop'][1])); loops[l] = loops.get(l, 0) + 1
        path = os.path.join(folder, f)
        try:
            bpm, _ = track_bpm_key(path)
            if not bpm: continue
            if mk.get('t0') is not None: t0 = float(mk['t0'])
            else: t0, bpm, _ = detect_grid(path, bpm)
            if mk.get('bpm'): bpm = float(mk['bpm'])
            target = int(round(mk['start'] / 4.0) * 4)
            if not 16 <= target <= START_KS_MAX: continue
            A, _ = struct_matrix(path, bpm, t0)
            fp = os.path.join(LEARN_MARKS_DIR, hashlib.md5(f'{f}|{os.path.getsize(path)}'.encode()).hexdigest() + '.npz')
            np.savez_compressed(fp, A=A, target=target, weight=1.0 if mk.get('auto') else 2.0, N=parse_name(f)['bars'] or 0); made += 1
        except Exception as e: print('  marcas no guardadas para', f, ':', e)
    if cfix: print(f'{cfix} correcciones tuyas del color del cue C guardadas para aprender.')
    prefs['grid2'] = gl[-200:]
    json.dump(prefs, open(PREFS_FILE, 'w', encoding='utf-8'))
    if gfix: print(f'{gfix} ajustes de grid tuyos aprendidos (corrección actual: {grid_bias() * 1000:+.0f} ms' + ('' if len(prefs['grid2']) >= 8 else f'; se activa con 8, llevas {len(prefs["grid2"])}') + ').')
    print(f'{made} marcas tuyas guardadas para aprender (hueco START→END habitual: {_pref("gaps", 8)} compases, loop: {_pref("loops", 8)}).')
    return made

def _newer(dirpath, ref):
    if not os.path.isdir(dirpath): return 0
    mt = os.path.getmtime(ref) if os.path.exists(ref) else 0
    return sum(1 for x in os.listdir(dirpath) if x.endswith('.npz') and os.path.getmtime(os.path.join(dirpath, x)) > mt)

def auto_learn(xml_path='', folders=(), n=10):
    """Reentrena solo cuando hay n ejemplos nuevos. Guarda copia del modelo anterior por si el nuevo sale peor."""
    n = int(n); nn = _newer(LEARN_DIR, MODEL_PATH)
    if nn >= n:
        print(f'\nAprendizaje automático: {nn} ejemplos nuevos de nombres. Reentrenando…')
        if os.path.exists(MODEL_PATH): shutil.copy2(MODEL_PATH, MODEL_PATH + '.prev')
        try: cmd_train(*[f for f in folders if os.path.isdir(f)])
        except BaseException as e:
            print('Reentrenamiento fallido, se mantiene el modelo anterior:', e)
            if os.path.exists(MODEL_PATH + '.prev'): shutil.copy2(MODEL_PATH + '.prev', MODEL_PATH)
    else: print(f'\nAprendizaje automático: {nn}/{n} ejemplos nuevos de nombres (reentrena al llegar a {n}).')
    nc = _newer(LEARN_CVOX_DIR, CVOX_MODEL)
    if nc >= max(3, n // 3):
        print(f'{nc} correcciones del color del C. Reentrenando…')
        try: train_cvox(xml_path)
        except BaseException as e: print('No se pudo reentrenar el color del C:', e)
    nm = _newer(LEARN_MARKS_DIR, MARKS_MODEL); tot = len([x for x in os.listdir(LEARN_MARKS_DIR) if x.endswith('.npz')]) if os.path.isdir(LEARN_MARKS_DIR) else 0
    have = os.path.exists(MARKS_MODEL); xml_ok = bool(xml_path) and os.path.exists(xml_path)
    if have and nm >= n:
        print(f'{nm} marcas nuevas. Reentrenando START MIX…'); shutil.copy2(MARKS_MODEL, MARKS_MODEL + '.prev')
        try: cmd_train_marks(xml_path if xml_ok else None)
        except BaseException as e:
            print('Reentrenamiento de START MIX fallido, se mantiene el anterior:', e); shutil.copy2(MARKS_MODEL + '.prev', MARKS_MODEL)
    elif not have and tot >= 40:
        print(f'Aún no había modelo de START MIX y ya tienes {tot} marcas tuyas. Entrenando con ellas (sin usar el XML)…')
        try: cmd_train_marks(None)
        except BaseException as e: print('No se pudo entrenar START MIX todavía:', e)
    else: print(f'Marcas START MIX: {nm}/{n} nuevas' + ('' if have else f' · {tot}/40 para crear el modelo con tus marcas') + '.')

def cmd_cues(xml_path, folder, only=None, offset_ms=0):
    from xml.sax.saxutils import quoteattr
    from urllib.parse import quote
    rules, t0_default, used = learn_cue_rules(xml_path)
    print(f'Aprendido de {used} pistas: ' + ', '.join(f'hot {"ABC"[int(n)]} = +{r[0]} compases' for n, r in sorted(rules.items()) if n in '012') + f'; primer beat típico {t0_default:.3f}s')
    rules['x']['end'] = _pref('gaps', rules['x']['end']); rules['x']['loop'] = _pref('loops', rules['x']['loop'])
    cvm = load_cvox()
    X0 = rules['x']; print('Colores aprendidos (RGB) · hot A/B/C: ' + ' / '.join(str(rules[n][1]) for n in '012') + f' · hot START {X0["col"]["4"]} · hot END MIX {X0["col"]["5"]} · hot loop {X0["col"]["7"]} · memory: ' + (', '.join(f'{k} {v}' for k, v in X0.get('mem', {}).items() if v) or 'sin color en tu colección'))
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(EXT) and (only is None or f in only)); tracks = []; skipped = []; allmarks = load_marks(folder)
    for i, f in enumerate(files, 1):
        path = os.path.abspath(os.path.join(folder, f)); bpm, key = track_bpm_key(path)
        if not bpm: skipped.append(f); continue
        tg = ffprobe_tags(path); dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path], capture_output=True, text=True).stdout.strip() or 0)
        try: t0, bpm, sc = detect_grid(path, bpm)
        except Exception: t0, sc = t0_default, 0.0
        name = os.path.splitext(f)[0]
        print(f'[{i}/{len(files)}] {name[:55]}: primer beat {t0:.3f} s, BPM {bpm:.2f}' + ('  <- grid dudoso, revísalo' if sc < 1.2 else ''), flush=True)
        mk = allmarks.get(f) or {}
        if mk.get('t0') is not None: t0 = float(mk['t0'])
        if mk.get('bpm'): bpm = float(mk['bpm'])
        bar = 240.0 / bpm; X = rules['x']
        eo = ((mp3_delay(path) + float(offset_ms or 0) / 1000.0) if f.lower().endswith('.mp3') else 0.0)           # desfase de exportación (compensa el que añada Rekordbox al leer el archivo)
        def at(b): return t0 + eo + b * bar
        def col(c): return f' Red="{c[0]}" Green="{c[1]}" Blue="{c[2]}"' if c else ''
        M = X.get('mem', {})
        marks = []
        st = mk.get('start'); en = mk.get('end'); hot_o = mk.get('hot') or {}; ma = mk.get('memAuto') or {}
        if mk.get('noIntro'): ma = dict(ma, intro=False)
        if st is not None and en is None and not mk.get('noEnd'): en = st + X['end']
        # hot cues: A..H = 0..7, SIN nombre (como en tu colección). El G (6) queda libre salvo que lo pongas tú a mano.
        C4 = X['col']['4']; cD = X['col'].get('3') or rules['1'][1]; c6 = X['col'].get('6') or C4
        vA = hot_o.get('A'); baseA = float(vA) if isinstance(vA, (int, float)) and not isinstance(vA, bool) else rules['0'][0]      # B y C siguen al A si lo mueves
        hot = {'0': rules['0'][0], '1': baseA + (rules['1'][0] - rules['0'][0]), '2': baseA + (rules['2'][0] - rules['0'][0]), '3': None, '4': st, '5': (st + X['off5']) if st is not None else None, '6': None}
        hcol = {'0': rules['0'][1], '1': rules['1'][1], '2': rules['2'][1], '3': cD, '4': C4, '5': X['col']['5'], '6': c6}
        cm = mk.get('ccol')
        if isinstance(cm, (list, tuple)) and len(cm) == 3: hcol['2'] = tuple(int(v) for v in cm); print(f'    cue C: color elegido por ti {tuple(cm)}')
        else:
            cc = cue_c_color(path, bpm, t0, f, cvm)
            if cc: hcol['2'] = RED_C if cc == 'red' else LIME_C; print(f'    cue C: {"rojo (voz antes del final del extender)" if cc == "red" else "verde lima (sin voz en el extender)"}')
        for L, num in zip('ABCDFG', '012356'):
            v = hot_o.get(L)
            if v is False: hot[num] = None
            elif isinstance(v, (int, float)) and not isinstance(v, bool): hot[num] = float(v)
        for num in '0123456':
            if hot[num] is not None: marks.append(f'<POSITION_MARK Name="" Type="0" Start="{at(hot[num]):.3f}" Num="{num}"{col(hcol[num])}/>')
        lp = mk.get('loop')
        if not lp and not mk.get('noLoop'):                    # bucle final automático: como en tu colección, todas las pistas llevan END LOOP al final
            ll_ = int(X['loop'] or 8); tb = int((dur - t0) / bar)
            if ll_ >= 1 and tb > ll_ + 8: lp = [tb - ll_, ll_]
        if lp: marks.append(f'<POSITION_MARK Name="" Type="4" Start="{at(lp[0]):.3f}" End="{at(lp[0] + lp[1]):.3f}" Num="7"{col(X["col"]["7"])}/>')
        # memory cues automáticos (INTRO verde en el hot A, START MIX naranja en el E, END MIX naranja, END LOOP rojo) · cada uno se puede mover o quitar (memAuto)
        GREEN_M, ORANGE_M, RED_M = rules['0'][1] or (40, 226, 20), (224, 100, 27), (230, 40, 40)
        mc = mk.get('mcol') or {}; mn_ = mk.get('mname') or {}
        def mcol(slot, default):
            v = mc.get(slot)
            return tuple(int(x) for x in v) if isinstance(v, (list, tuple)) and len(v) == 3 else default
        def mem(key, default):
            v = ma.get(key)
            if v is False: return None
            if isinstance(v, (int, float)) and not isinstance(v, bool): return float(v)
            return default
        p_i = mem('intro', hot['0'] if hot['0'] is not None else 0.0)
        if p_i is not None: marks.append(f'<POSITION_MARK Name={quoteattr(str(mn_.get("A") or "INTRO"))} Type="0" Start="{at(p_i):.3f}" Num="-1"{col(mcol("A", GREEN_M))}/>')
        p_s = mem('start', st)
        if p_s is not None:
            gap = int(round((en if en is not None else st + X['end']) - st)) if st is not None else 8; nm_s = f'START MIX {gap}' if gap in (8, 16) else 'START MIX'
            marks.append(f'<POSITION_MARK Name={quoteattr(str(mn_.get("E") or nm_s))} Type="0" Start="{at(p_s):.3f}" Num="-1"{col(mcol("E", ORANGE_M))}/>')
        p_e = mem('end', en)
        if p_e is not None: marks.append(f'<POSITION_MARK Name={quoteattr(str(mn_.get("G") or "END MIX"))} Type="0" Start="{at(p_e):.3f}" Num="-1"{col(mcol("G", (180, 190, 4) if mk.get("endWarn") else ORANGE_M))}/>')       # amarillo = acaba empezando otra frase: cortar antes
        p_l = mem('loop', lp[0] if lp else None)
        if p_l is not None and lp: marks.append(f'<POSITION_MARK Name={quoteattr(str(mn_.get("H") or "END LOOP"))} Type="4" Start="{at(p_l):.3f}" End="{at(p_l + lp[1]):.3f}" Num="-1"{col(mcol("H", RED_M))}/>')
        for mm_ in (mk.get('mem') or []):                      # memory cues extra puestos a mano
            try: marks.append(f'<POSITION_MARK Name={quoteattr(str(mm_.get("n") or ""))} Type="0" Start="{at(float(mm_["b"])):.3f}" Num="-1"{col(mcol(mm_.get("s"), None))}/>')
            except Exception: pass
        pn_ = parse_name(f); tg_ = [x_ for x_ in ('Open Show' if pn_['open_show'] else '', 'Aca Starter' if pn_['aca_starter'] else '', pn_['type'] or '', pn_['after'] or '', 'Short Edit' if pn_['short_edit'] else '', 'Aca Out' if pn_['aca_out'] else '', 'Mashup' if pn_['mashup'] else '', 'Live Mashup' if 'live mashup' in f.lower() else '') if x_]
        gattr = (f'Genre={quoteattr(str(mk.get("genre")))} ' if mk.get('genre') else '') + (f'Grouping={quoteattr(mk["cat"])} Colour="0x{CAT_HEX[mk["cat"]]}" ' if mk.get('cat') in CAT_HEX and mk['cat'] != 'Pink' else (f'Colour="0x{CAT_HEX["Pink"]}" ' if mk.get('cat') == 'Pink' else '')) + (f'Rating="{int(mk["stars"]) * 51}" ' if str(mk.get('stars') or '').isdigit() and int(mk['stars']) > 0 else '') + f'Comments={quoteattr(" · ".join(tg_))} '
        tracks.append((i, f'<TRACK TrackID="{i}" Name={quoteattr(name)} Artist={quoteattr(tg.get("artist", ""))} Album={quoteattr(os.path.basename(os.path.dirname(path)))} '
                          f'{gattr}Kind="{os.path.splitext(f)[1][1:].upper()} File" TotalTime="{int(dur)}" AverageBpm="{bpm:.2f}" Tonality={quoteattr(key)} Location={quoteattr("file://localhost" + quote(path))}>'
                          f'<TEMPO Inizio="{t0 + eo:.3f}" Bpm="{bpm:.2f}" Metro="4/4" Battito="1"/>' + ''.join(marks) + '</TRACK>'))
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<DJ_PLAYLISTS Version="1.0.0">', '<PRODUCT Name="rekordbox" Version="6.0.0" Company="AlphaTheta"/>',
           f'<COLLECTION Entries="{len(tracks)}">'] + [t for _, t in tracks] + ['</COLLECTION>', '<PLAYLISTS><NODE Type="0" Name="ROOT" Count="1">',
           f'<NODE Name="djflow" Type="1" KeyType="0" Entries="{len(tracks)}">'] + [f'<TRACK Key="{i}"/>' for i, _ in tracks] + ['</NODE></NODE></PLAYLISTS>', '</DJ_PLAYLISTS>']
    out = os.path.join(folder, 'djflow_cues.xml'); open(out, 'w', encoding='utf-8').write('\n'.join(xml))
    print(f'\n{len(tracks)} pistas con cues en {out}' + (f'\nSin BPM (pasa antes Mixed In Key): {len(skipped)}' if skipped else ''))
    nm = sum(1 for f in files if (allmarks.get(f) or {}).get('start') is not None)
    print(f'Con START/END MIX y hot cue 5: {nm} pistas.' + ('' if nm == len(tracks) else ' El resto: ponlas a mano (START MIX, END MIX, hot cues 4 y 5, loop final).'))

def remember_examples(folder, reviewed=None, only=None):
    """Guarda como ejemplos de entrenamiento las pistas que acabas de revisar y aplicar (con tus correcciones)."""
    os.makedirs(LEARN_DIR, exist_ok=True); n = 0; made = []
    for f in sorted(os.listdir(folder)):
        if not f.lower().endswith(EXT) or (only is not None and f not in only): continue
        p = parse_name(f)
        if not p['key'] or not p['bpm']: continue
        path = os.path.join(folder, f); bpm, _ = track_bpm_key(path)
        if not bpm: continue
        fp = os.path.join(LEARN_DIR, hashlib.md5(f'{f}|{os.path.getsize(path)}'.encode()).hexdigest() + '.npz')
        if os.path.exists(fp): continue
        try: ft = get_features(path, bpm)
        except Exception: continue
        wt = 1.0 if (reviewed is None or f in reviewed) else 0.3
        np.savez_compressed(fp, head=ft['head'], tail=ft['tail'], dur=ft['dur'], nbars=ft['nbars'], name=os.path.splitext(f)[0], bpm=bpm, weight=wt); n += 1; made.append(fp)
    print(f'{n} pistas guardadas como ejemplos (las revisadas o corregidas pesan más que las aceptadas sin mirar).')
    return made

def learned_rows(rows):
    """Ejemplos guardados al aplicar nombres, sin repetir los que ya vienen de las carpetas de entrenamiento."""
    if not os.path.isdir(LEARN_DIR): return []
    seen = {os.path.splitext(os.path.basename(r[0]))[0] for r in rows}; out = []
    for fn in sorted(os.listdir(LEARN_DIR)):
        if not fn.endswith('.npz'): continue
        z = np.load(os.path.join(LEARN_DIR, fn)); name = str(z['name'])
        if name in seen: continue
        out.append((name + '.mp3', parse_name(name), float(z['bpm']), dict(head=z['head'], tail=z['tail'], dur=float(z['dur']), nbars=float(z['nbars'])), float(z['weight']) if 'weight' in z.files else 1.0))
    if out: print(f'{len(out)} ejemplos extra de tus correcciones anteriores.')
    return out

def load_marks(folder):
    try: return json.load(open(os.path.join(folder, MARKS_FILE), encoding='utf-8'))
    except Exception: return {}

def save_marks(folder, d):
    json.dump(d, open(os.path.join(folder, MARKS_FILE), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def _prune_backups(keep=3):
    if not os.path.isdir(BACKUP_DIR): return
    for d in sorted(os.listdir(BACKUP_DIR))[:-keep]: shutil.rmtree(os.path.join(BACKUP_DIR, d), ignore_errors=True)

def cmd_apply(folder, backup=True):
    """Renombra y limpia SOLO las filas con nombre final. Guarda copia de los originales para poder deshacer."""
    backup = backup not in (False, '0', 'no'); stamp = time.strftime('%Y%m%d-%H%M%S'); entries = []; artists = {}; reviewed = set(); applied = set(); mapping = {}
    bdir = os.path.join(BACKUP_DIR, stamp)
    with open(os.path.join(folder, 'review.csv'), newline='', encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh):
            final = (r['final'] or '').strip()
            if not final: continue
            src = os.path.join(folder, r['original']); ext = os.path.splitext(src)[1]
            dst = os.path.join(folder, final if final.lower().endswith(ext.lower()) else final + ext)
            if not os.path.exists(src): continue
            if src != dst and os.path.exists(dst): print(f'Ya existe {os.path.basename(dst)}; se salta {r["original"]}'); continue
            bk = None
            if backup:
                os.makedirs(bdir, exist_ok=True); bk = os.path.join(bdir, r['original']); shutil.copy2(src, bk)
            if src != dst: os.rename(src, dst)
            entries.append(dict(src=src, dst=dst, backup=bk)); applied.add(os.path.basename(dst)); mapping[r['original']] = os.path.basename(dst)
            if (r.get('artist') or '').strip(): artists[os.path.basename(dst)] = r['artist'].strip()
            if (r.get('reviewed') or '') == '1' or final != (r.get('proposed') or '').strip(): reviewed.add(os.path.basename(dst))
    global LAST_APPLIED; LAST_APPLIED = set(applied)
    print(f'{len(entries)} archivos renombrados.'); cmd_clean(folder, artists, only=applied)
    mark_done([os.path.join(folder, a) for a in applied])
    marks = load_marks(folder)
    if marks: save_marks(folder, {mapping.get(k, k): v for k, v in marks.items()})
    made = remember_examples(folder, reviewed, only=applied)
    try: remember_marks(folder, applied)
    except Exception as e: print('No se pudieron guardar las marcas:', e)
    os.makedirs(HIST_DIR, exist_ok=True)
    json.dump(dict(stamp=stamp, folder=folder, entries=entries, learned=made, backup=backup), open(os.path.join(HIST_DIR, stamp + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    _prune_backups(); print('Ya puedes importar a Rekordbox.' + (' Si te equivocas: botón Deshacer (hasta 3 tandas).' if backup else ''))

def last_history(folder=None):
    if not os.path.isdir(HIST_DIR): return None
    for f in sorted(os.listdir(HIST_DIR), reverse=True):
        if f.endswith('.json') and not f.endswith('.undone.json'):
            h = json.load(open(os.path.join(HIST_DIR, f), encoding='utf-8')); h['_file'] = os.path.join(HIST_DIR, f)
            if folder is None or os.path.abspath(h['folder']) == os.path.abspath(folder): return h
    return None

def cmd_undo(folder=None):
    """Deshace la última tanda: vuelve a poner los originales (nombre, tags y portada) desde la copia de seguridad."""
    h = last_history(folder)
    if not h: print('No hay ninguna tanda que deshacer.'); return
    n = 0; missing = 0
    for e in reversed(h['entries']):
        if e.get('backup') and os.path.exists(e['backup']):
            if os.path.exists(e['dst']) and e['dst'] != e['src']: os.remove(e['dst'])
            shutil.copy2(e['backup'], e['src']); n += 1
        elif os.path.exists(e['dst']) and e['dst'] != e['src']: os.rename(e['dst'], e['src']); n += 1; missing += 1
    for fp in h.get('learned', []):
        try: os.remove(fp)
        except OSError: pass
    os.replace(h['_file'], h['_file'].replace('.json', '.undone.json'))
    print(f'{n} archivos restaurados' + (f' ({missing} solo con el nombre: sin copia de seguridad, los tags no se recuperan)' if missing else '') + '. Si ya los importaste a Rekordbox, hay que volver a localizarlos.')

if __name__ == '__main__':
    cmds = {'train': cmd_train, 'analyze': cmd_analyze, 'apply': cmd_apply, 'clean': cmd_clean, 'cues': cmd_cues, 'undo': cmd_undo, 'train-marks': cmd_train_marks, 'mark-done': cmd_mark_done}
    need = {'train': (3, 99), 'analyze': (3, 4), 'apply': (3, 4), 'clean': (3, 3), 'cues': (4, 4), 'undo': (2, 3), 'train-marks': (3, 4), 'mark-done': (3, 3)}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds or not (need[sys.argv[1]][0] <= len(sys.argv) <= need[sys.argv[1]][1]): print(__doc__); sys.exit(1)
    cmds[sys.argv[1]](*sys.argv[2:])
