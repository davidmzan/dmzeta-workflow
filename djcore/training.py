"""Entrenamiento y aprendizaje automático a partir de tu colección y de tus correcciones."""
import sys, os, re, csv, json, time, shutil, hashlib, subprocess
import numpy as np
from .config import CANDS, CVOX_MODEL, DATA, EXT, GENRE_MODEL, HEX_CAT, LEARN_CVOX_DIR, LEARN_DIR, LEARN_MARKS_DIR, LEARN_META_DIR, LIME_C, MARKS_MODEL, MODEL_PATH, PREFS_FILE, RED_C, START_KS_MAX, W_CORRECTED
from .storage import _pref, atomic_savez, atomic_write_json, learn_weight, load_marks, load_prefs, log_model
from .names import parse_name
from .audio import get_features, struct_matrix, track_bpm_key
from .grid import detect_grid, grid_bias
from .features import after_x, boundary_x, cvox_x, genre_x, out_x, short_x, start_X, starter_x, type_x
from .models import Softmax, TASKS, best_threshold, cv_predict
from .prediction import cue_c_color

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
            bars_acc = hit / max(tot, 1)
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
    atomic_savez(MODEL_PATH, **store)
    log_model('names', n=len(rows), n_user=len(os.listdir(LEARN_DIR)) if os.path.isdir(LEARN_DIR) else 0, accuracy=round(float(locals().get('bars_acc') or 0), 3), note='acierto = compases exactos')
    with open(os.path.join(DATA, 'informe.md'), 'w', encoding='utf-8') as fh: fh.write('\n'.join(report) + '\n')
    print('\n' + '\n'.join(report) + f'\n\nModelo guardado en {MODEL_PATH}\nInforme en {os.path.join(DATA, "informe.md")}')

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
    store = {'start__off': np.array([0 if useful else 1])}; Softmax([0, 1]).fit(X, y, w=W).dump('start2', store); atomic_savez(MARKS_MODEL, **store)
    log_model('start_mix', n=int(tot), n_user=len(learned), accuracy=round(ex / max(tot, 1), 3), baseline=round(basepct / 100, 3), enabled=bool(useful))
    open(os.path.join(DATA, 'informe_marks.md'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n'); print('\n' + '\n'.join(rep) + f'\n\nModelo guardado en {MARKS_MODEL}')
    if xml_path and os.path.exists(xml_path):
        try: train_cvox(xml_path)
        except BaseException as e: print('No se pudo aprender el color del cue C:', e)

def train_cvox(xml_path=None, min_n=20):
    """Aprende el color del cue C SOLO de tus pistas corregidas (carpeta learned_cvox), no de la colección del XML."""
    learned = []
    if os.path.isdir(LEARN_CVOX_DIR):
        for fn in sorted(os.listdir(LEARN_CVOX_DIR)):
            if fn.endswith('.npz'): z = np.load(os.path.join(LEARN_CVOX_DIR, fn)); learned.append((z['A'], int(z['N']), int(z['y']), float(z['w']) if 'w' in z.files else W_CORRECTED))
    print(f'Color del cue C: {len(learned)} pistas corregidas por ti.')
    if len(learned) < min_n: print(f'Hacen falta al menos {min_n}; sin modelo el color del C no se propone (lo eliges tú).'); return
    X = np.array([cvox_x(A, N) for A, N, _, _ in learned]); y = np.array([l for _, _, l, _ in learned]); W = np.array([w for _, _, _, w in learned])
    if y.min() == y.max(): print('Todas las pistas tienen el mismo color: no se aprende.'); return
    P = cv_predict(X, y, list(range(len(y))), [0, 1], w=W); acc = float(((P[:, 1] >= .5) == (y == 1)).mean()); base = max(y.mean(), 1 - y.mean()); ok = acc >= base + 0.05
    rep = ['# Informe color del cue C', f'Pistas corregidas por ti: {len(y)} (rojas: {int(y.sum())})', f'- acierto (validación cruzada): {100 * acc:.0f} %  (referencia, elegir siempre lo más habitual: {100 * base:.0f} %)',
           '- ESTADO: ' + ('ACTIVO' if ok else 'DESACTIVADO (no supera a la referencia: eliges tú el color)')]
    store = {'cvox__off': np.array([0 if ok else 1])}; Softmax([0, 1]).fit(X, y, w=W).dump('cvox2', store); atomic_savez(CVOX_MODEL, **store)
    log_model('cvox', n=int(len(y)), n_user=int((W >= W_CORRECTED).sum()), accuracy=round(acc, 3), baseline=round(float(base), 3), enabled=bool(ok))
    open(os.path.join(DATA, 'informe_cvox.md'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n'); print('\n' + '\n'.join(rep))

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
    CY, SY, WY, WC, WS = [], [], [], [], []
    for ti, (loc, bpm, t0, g, cat_, st_) in enumerate(items):
        print(f'  [{ti + 1}/{len(items)}] {os.path.basename(loc)[:70]}', flush=True)
        try: A, _ = struct_matrix(loc, bpm, t0)
        except Exception as e: print('    error:', e); continue
        X.append(genre_x(A, bpm)); y.append(g); t.append(ti); CY.append(cat_); SY.append(st_); WY.append(1.0); WC.append(1.0); WS.append(1.0)
    n_user = 0
    if os.path.isdir(LEARN_META_DIR):                                    # tus correcciones: pesan más que la colección (W_CORRECTED) o menos si solo diste ✓ (W_ACCEPTED)
        for j, fn in enumerate(sorted(x for x in os.listdir(LEARN_META_DIR) if x.endswith('.npz'))):
            z = np.load(os.path.join(LEARN_META_DIR, fn)); X.append(z['x']); y.append(str(z['genre'])); CY.append(str(z['cat'])); SY.append(str(z['stars']))
            WY.append(float(z['gw'])); WC.append(float(z['cw'])); WS.append(float(z['sw'])); t.append(len(items) + j); n_user += 1
    print(f'Ejemplos tuyos (correcciones y ✓): {n_user}.')
    X = np.array(X); store = {}; rep = []
    gi = [i for i, v in enumerate(y) if v and WY[i] > 0]
    ya = np.array([y[i] for i in gi]); Xg = X[gi]; tg = [t[i] for i in gi]; wg = np.array([WY[i] for i in gi]); classes = sorted(set(ya))
    P = cv_predict(Xg, ya, tg, classes, w=wg)
    top1 = float((np.array(classes)[P.argmax(1)] == ya).mean()); top3 = float(np.mean([ya[i] in np.array(classes)[np.argsort(-P[i])[:3]] for i in range(len(ya))]))
    base = Counter(ya).most_common(1)[0]; dist = ', '.join(f'{g} {c}' for g, c in Counter(ya).most_common(6))
    rep = ['# Informe de género', f'Pistas: {len(ya)} (de ellas {n_user} tuyas) · géneros: {len(classes)}', f'- acierto del primero: {100 * top1:.0f} %', f'- el correcto entre los 3 primeros: {100 * top3:.0f} %',
           f'- referencia (siempre «{base[0]}»): {100 * base[1] / len(ya):.0f} %', f'- reparto: {dist}']
    Softmax(classes).fit(Xg, ya, w=wg).dump('genre', store)
    log_model('genre', n=int(len(ya)), n_user=n_user, accuracy=round(top1, 3), baseline=round(base[1] / len(ya), 3), enabled=True)
    for nm, lab, wl, nom in (('cat', CY, WC, 'categoría (color)'), ('star', SY, WS, 'estrellas')):     # mismas características de audio, sin volver a analizar
        idx = [i for i, v in enumerate(lab) if v and wl[i] > 0]
        if len(idx) < 150 or len(set(lab[i] for i in idx)) < 2: rep.append(f'- {nom}: pocas pistas con dato, no se aprende'); continue
        Xs, ys = X[idx], np.array([lab[i] for i in idx]); ws_ = np.array([wl[i] for i in idx]); cls = sorted(set(ys)); Ps = cv_predict(Xs, ys, [t[i] for i in idx], cls, w=ws_)
        acc = float((np.array(cls)[Ps.argmax(1)] == ys).mean()); b0 = Counter(ys).most_common(1)[0][1] / len(ys); ok = acc >= b0 + 0.05
        Softmax(cls).fit(Xs, ys, w=ws_).dump(nm, store); store[f'{nm}__off'] = np.array([0 if ok else 1])
        log_model(nm, n=int(len(idx)), n_user=int(sum(1 for i in idx if t[i] >= len(items))), accuracy=round(acc, 3), baseline=round(float(b0), 3), enabled=bool(ok))
        rep.append(f'- {nom}: acierto {100 * acc:.0f} % (siempre la más común: {100 * b0:.0f} %) → ' + ('se propone solo' if ok else 'NO supera al azar: se rellena a mano'))
    atomic_savez(GENRE_MODEL, **store)
    open(os.path.join(DATA, 'informe_genre.md'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n'); print('\n' + '\n'.join(rep))

def learn_from_xml(xml_path):
    """Todo lo que se aprende de tu rekordbox.xml: START MIX, color del cue C y género. Devuelve el informe junto."""
    out = []
    for fn, rf in ((cmd_train_marks, 'informe_marks.md'), (train_genre, 'informe_genre.md')):
        try: fn(xml_path)
        except BaseException as e: print('  (se salta:', e, ')')
        for r in (rf, 'informe_cvox.md') if rf == 'informe_marks.md' else (rf,):
            p = os.path.join(DATA, r)
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
        cm = mk.get('ccol'); cm_w = learn_weight(cm is not None, bool(mk.get('ok')))
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
                np.savez_compressed(os.path.join(LEARN_CVOX_DIR, hashlib.md5(f'{f}|{os.path.getsize(path)}'.encode()).hexdigest() + '.npz'), A=A, N=parse_name(f)['bars'], y=int(tuple(cm) == RED_C), w=cm_w); cfix += 1
            except Exception as e: print('  color del C no aprendido para', f, ':', e)
        gw = learn_weight(mk.get('genre_edit'), mk.get('ok') and mk.get('genre')) if mk.get('genre') else 0.0
        cw = learn_weight(mk.get('cat_edit'), mk.get('ok') and mk.get('cat')) if mk.get('cat') else 0.0
        sw = learn_weight(mk.get('stars') and not mk.get('stars_auto'), mk.get('ok') and mk.get('stars')) if mk.get('stars') else 0.0
        if gw or cw or sw:                                                                  # género, categoría o estrellas que has corregido (o dado por buenos con ✓)
            try:
                os.makedirs(LEARN_META_DIR, exist_ok=True); path = os.path.join(folder, f); bpm0, _ = track_bpm_key(path)
                t0m = float(mk['t0']) if mk.get('t0') is not None else detect_grid(path, bpm0)[0]; bpmm = float(mk.get('bpm') or bpm0)
                A, _ = struct_matrix(path, bpmm, t0m)
                np.savez_compressed(os.path.join(LEARN_META_DIR, hashlib.md5(f'{f}|{os.path.getsize(path)}'.encode()).hexdigest() + '.npz'), x=genre_x(A, bpmm), genre=str(mk.get('genre') or ''),
                                    cat=str(mk.get('cat') or ''), stars=str(mk.get('stars') or ''), gw=gw, cw=cw, sw=sw)
            except Exception as e: print('  género/categoría/estrellas no aprendidos para', f, ':', e)
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
    atomic_write_json(PREFS_FILE, prefs)
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
    nmeta = _newer(LEARN_META_DIR, GENRE_MODEL)
    if os.path.exists(GENRE_MODEL) and nmeta >= max(3, n // 3) and xml_path and os.path.exists(xml_path):
        print(f'{nmeta} correcciones de género/categoría/estrellas. Reentrenando…')
        try: train_genre(xml_path)
        except BaseException as e: print('No se pudo reentrenar género/categoría/estrellas:', e)
    elif os.path.exists(GENRE_MODEL): print(f'Género/categoría/estrellas: {nmeta}/{max(3, n // 3)} correcciones nuevas.')
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
