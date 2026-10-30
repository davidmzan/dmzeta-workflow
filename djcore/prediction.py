"""Predicciones con los modelos cargados: nombre, START MIX, color del C, género y duplicados."""
import os, re
import numpy as np
from .config import CANDS, GENRE_MODEL, TYPES
from .storage import _pref, is_done
from .names import _tn, build_name, clean_title_pool, guess_from_name, normalize_artist, parse_name
from .audio import ffprobe_tags, get_features, struct_matrix, track_bpm_key
from .features import after_x, boundary_x, cvox_x, genre_x, out_x, short_x, start_X, starter_x, type_x
from .models import Softmax, decide, load_cvox, load_genre_model

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

def propose_start(path, bpm, t0, model, N=0):
    """Compás propuesto para START MIX, END MIX (+8) y loop final. Devuelve dict de marcas o None."""
    if model is None: return None
    A, dur = struct_matrix(path, bpm, t0); ks, XX = start_X(A, N)
    if len(ks) < 3: return None
    p = model.proba(XX)[:, 1]; i = int(p.argmax()); k = ks[i]; conf = float(p[i] / max(p.sum(), 1e-9))
    gap, ll = _pref('gaps', 8), _pref('loops', 8)
    alts = []                                                      # top-3 candidatos separados ≥ 8 compases: con tus marcas el correcto está entre ellos el 57 % de las veces (el primero solo el 38 %)
    for j in np.argsort(-p):
        if all(abs(ks[j] - a) >= 8 for a in alts): alts.append(int(ks[j]))
        if len(alts) == 3: break
    out = dict(start=k, end=k + gap, conf=round(conf, 2), auto=True, alts=alts)
    total = int((dur - t0) / (240.0 / bpm)); ls = total - ll - 1
    if ls > k + gap: out['loop'] = [ls, ll]
    return out

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

def predict_genre(path, bpm, t0=0.0, model=None):
    """Devuelve (genero, confianza, top3) o None."""
    model = model or load_genre_model()
    if model is None: return None
    try:
        A, _ = struct_matrix(path, bpm, t0); pr = model.proba(genre_x(A, bpm)[None])[0]; o = np.argsort(-pr)
        return str(model.classes[o[0]]), float(pr[o[0]]), [str(model.classes[i]) for i in o[:3]]
    except Exception: return None
