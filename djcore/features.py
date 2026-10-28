"""Vectores de características para los modelos."""
import sys, os, re, csv, json, time, shutil, hashlib, subprocess
import numpy as np
from .config import CANDS, NF, START_KS_MAX

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

def cvox_x(A, N):
    """Una sola señal: cuánta voz hay en los 4 compases que siguen al extender (la que mejor separa rojo/lima en tus 36 pistas corregidas)."""
    return np.array([float(m(A, N, N + 4)[3])])

def genre_x(A, bpm):
    """Resumen de la pista para el género: timbre medio y variación (energía, graves, voz, hats…), estructura y zona de BPM."""
    n = len(A)
    if n < 4: A = np.vstack([A, np.zeros((4 - n, NF), dtype=np.float32)]) if n else np.zeros((4, NF), dtype=np.float32)
    bins = np.zeros(29, dtype=np.float32); bins[int(np.clip((bpm - 60) // 5, 0, 28))] = 1
    return np.concatenate([A.mean(0), A.std(0), m(A, 0, 8), m(A, 32, 64), bins, [np.log(max(bpm, 1.0)), bpm / 100.0]]).astype(np.float32)
