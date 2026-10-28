"""Lectura y escritura de estado en disco (atómica): marcas, preferencias, registro de pistas ya procesadas."""
import sys, os, re, csv, json, time, shutil, hashlib, subprocess
import numpy as np
from .config import DONE_FILE, EXT, MARKS_FILE, MODEL_LOG, PREFS_FILE

def atomic_write_bytes(path, data):
    """Escribe en un archivo temporal y lo renombra: si algo falla a medias, el archivo anterior queda intacto."""
    tmp = f'{path}.tmp{os.getpid()}'
    with open(tmp, 'wb') as fh: fh.write(data); fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, path)

def atomic_write_text(path, text, encoding='utf-8'): atomic_write_bytes(path, text.encode(encoding))

def atomic_savez(path, **arrays):
    import io as _io
    b = _io.BytesIO(); np.savez_compressed(b, **arrays); atomic_write_bytes(path, b.getvalue())

def atomic_write_json(path, obj, **kw): atomic_write_text(path, json.dumps(obj, ensure_ascii=False, **kw))

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
    atomic_write_json(DONE_FILE, d)

def is_done(path):
    try: return _fp(path) in load_done()
    except OSError: return False

def cmd_mark_done(folder):
    """Marca como ya procesados todos los audios de la carpeta (tu colección ya ordenada)."""
    fs = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(EXT)]
    mark_done(fs); print(f'{len(fs)} archivos marcados como ya procesados. No se volverán a analizar mientras no los modifiques.')

def load_marks(folder):
    try: return json.load(open(os.path.join(folder, MARKS_FILE), encoding='utf-8'))
    except Exception: return {}

def save_marks(folder, d):
    atomic_write_json(os.path.join(folder, MARKS_FILE), d, indent=1)


def load_model_log():
    try: return json.load(open(MODEL_LOG, encoding='utf-8'))
    except Exception: return []

def log_model(name, **info):
    """Anota cada reentrenamiento (cuándo, con cuántos ejemplos, cuántos tuyos, acierto y referencia) para ver si la app mejora de verdad."""
    log = load_model_log(); log.append(dict(model=name, when=time.strftime('%Y-%m-%d %H:%M:%S'), **info)); atomic_write_json(MODEL_LOG, log[-300:])

def learn_weight(edited, accepted):
    """Peso de un ejemplo: corregido por ti = alto; aceptado con ✓ = bajo; sin revisar = 0 (no se aprende)."""
    from .config import W_ACCEPTED, W_CORRECTED
    return W_CORRECTED if edited else (W_ACCEPTED if accepted else 0.0)
