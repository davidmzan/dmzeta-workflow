"""Lectura y escritura de estado en disco (atómica): marcas, preferencias, registro de pistas ya procesadas."""
import os, json, time
import numpy as np
from .config import BPM_FIX_LOG, DONE_FILE, EXT, MARKS_FILE, MODEL_LOG, PREFS_FILE, USAGE_LOG

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


def bpm_factor(detected, corrected):
    """2.0 si corregiste al doble, 0.5 si a la mitad (±3 %), None en cualquier otro caso."""
    try: d, c = float(detected), float(corrected)
    except (TypeError, ValueError): return None
    if d <= 0 or c <= 0: return None
    for f in (2.0, 0.5):
        if abs(c / d - f) / f < 0.03: return f
    return None

def load_bpm_fixes():
    try: return json.load(open(BPM_FIX_LOG, encoding='utf-8'))
    except Exception: return []

def log_bpm_fix(name, detected, corrected):
    """Anota una corrección de BPM. Una pista corregida varias veces solo cuenta la última; se guardan como máximo 500."""
    name = os.path.basename(str(name))
    try: d, c = float(detected), float(corrected)
    except (TypeError, ValueError): return False
    if not name or d <= 0 or c <= 0: return False
    fixes = [e for e in load_bpm_fixes() if e.get('name') != name]
    fixes.append(dict(name=name, when=time.strftime('%Y-%m-%d %H:%M:%S'), detected=round(float(detected), 2), corrected=round(float(corrected), 2), factor=bpm_factor(detected, corrected)))
    atomic_write_json(BPM_FIX_LOG, fixes[-500:]); return True

def bpm_fix_summary():
    fx = load_bpm_fixes()
    return dict(total=len(fx), double_half=sum(1 for e in fx if e.get('factor')), last=fx[-10:])


USAGE_FIELDS = ('name', 'grid', 'start_mix', 'cue_color', 'genre', 'category', 'stars', 'loop')

def load_usage():
    try: return json.load(open(USAGE_LOG, encoding='utf-8'))
    except Exception: return []

def log_usage(entries):
    """Una entrada por pista aplicada: {field: 1 si lo corregiste, 0 si lo dejaste como lo propuso la app, ausente si no aplica} y los segundos que le dedicaste."""
    if not entries: return
    log = load_usage() + [dict(e, when=time.strftime('%Y-%m-%d %H:%M:%S')) for e in entries]; atomic_write_json(USAGE_LOG, log[-2000:])

def usage_summary(last=200):
    """Porcentaje de pistas en las que corriges cada campo (sobre las últimas `last`) y tiempo mediano por pista."""
    log = load_usage()[-int(last):]; fields = {}
    for f in USAGE_FIELDS:
        vals = [e[f] for e in log if e.get(f) in (0, 1)]
        if vals: fields[f] = dict(n=len(vals), corrected=int(sum(vals)), rate=round(sum(vals) / len(vals), 3))
    secs = sorted(float(e['secs']) for e in log if e.get('secs'))
    return dict(tracks=len(log), fields=fields, median_secs=round(secs[len(secs) // 2], 1) if secs else None)
