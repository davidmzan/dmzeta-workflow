"""Órdenes de alto nivel: analizar, aplicar, deshacer, limpiar y CLI."""
import sys, os, csv, json, time, shutil, subprocess
from .config import BACKUP_DIR, EXT, HIST_DIR, MARKS_MODEL
from .storage import cmd_mark_done, load_marks, mark_done, save_marks
from .names import normalize_artist, parse_name
from .audio import ffprobe_tags
from .grid import detect_grid
from .models import load_genre_model, load_marks_model, load_models
from .prediction import dup_check, dup_index, predict_meta, predict_track, propose_start
from .training import cmd_train, cmd_train_marks, remember_examples, remember_marks
from .cues import cmd_cues

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

LAST_APPLIED = None

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


def get_last_applied():
    """Archivos renombrados en la última tanda (para generar solo sus cues). Es una función porque el valor cambia en ejecución."""
    return LAST_APPLIED


def main(argv=None, doc=''):
    argv = list(sys.argv if argv is None else argv)
    cmds = {'train': cmd_train, 'analyze': cmd_analyze, 'apply': cmd_apply, 'clean': cmd_clean, 'cues': cmd_cues, 'undo': cmd_undo, 'train-marks': cmd_train_marks, 'mark-done': cmd_mark_done}
    need = {'train': (3, 99), 'analyze': (3, 4), 'apply': (3, 4), 'clean': (3, 3), 'cues': (4, 4), 'undo': (2, 3), 'train-marks': (3, 4), 'mark-done': (3, 3)}
    if len(argv) < 2 or argv[1] not in cmds or not (need[argv[1]][0] <= len(argv) <= need[argv[1]][1]): print(doc); sys.exit(1)
    cmds[argv[1]](*argv[2:])
