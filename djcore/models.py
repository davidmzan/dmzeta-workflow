"""Regresión logística propia (NumPy), validación cruzada y carga de modelos entrenados."""
import sys, os, re, csv, json, time, shutil, hashlib, subprocess
import numpy as np
from .config import CVOX_MODEL, GENRE_MODEL, MARKS_MODEL, MODEL_PATH, TYPES

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

# ───────────────────────── analizar / aplicar ─────────────────────────
def load_models():
    if not os.path.exists(MODEL_PATH): return {}
    z = np.load(MODEL_PATH, allow_pickle=False)
    names = {k.split('__')[0] for k in z.files if k.endswith('__cl')}
    out = {}
    for n in names:
        mo = Softmax.load(n, z); mo.thr = float(z[f'{n}__thr'][0]) if f'{n}__thr' in z.files else 0.5; out[n] = mo
    return out

def load_marks_model():
    if not os.path.exists(MARKS_MODEL): return None
    z = np.load(MARKS_MODEL, allow_pickle=False)
    if 'start__off' in z.files and int(z['start__off'][0]) == 1: return None
    if 'start2__cl' not in z.files: return None
    return Softmax.load('start2', z)

def load_cvox():
    if not os.path.exists(CVOX_MODEL): return None
    z = np.load(CVOX_MODEL, allow_pickle=False)
    if 'cvox2__cl' not in z.files or ('cvox__off' in z.files and int(z['cvox__off'][0]) == 1): return None
    return Softmax.load('cvox2', z)

def load_genre_model():
    if not os.path.exists(GENRE_MODEL): return None
    z = np.load(GENRE_MODEL, allow_pickle=False)
    if 'genre__cl' not in z.files: return None
    return Softmax.load('genre', z)
