#!/usr/bin/env python3
"""Dmzeta Workflow · interfaz web local. Uso: python3 workflow_server.py  (abre el navegador solo)."""
import os, sys, io, re, csv, json, time, socket, threading, subprocess, webbrowser, mimetypes, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import djflow as dj

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, 'config.json')
UI = os.path.join(HERE, 'workflow_ui.html')
PING = [0.0]
LOCAL = threading.local(); JOBS = {}; JOB_LOCK = threading.Lock(); ALLOWED = set()

def load_cfg():
    try: c = json.load(open(CFG, encoding='utf-8'))
    except Exception: c = {}
    c.setdefault('train', []); c.setdefault('xml', ''); c.setdefault('folder', ''); c.setdefault('backup', True); c.setdefault('auto_learn', True); c.setdefault('export_offset_ms', 0); c.setdefault('auto_n', 10); return c

def save_cfg(c):
    try: json.dump(c, open(CFG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    except Exception: pass

class Tee(io.TextIOBase):
    def __init__(s, orig): s.orig = orig
    def write(s, t):
        j = getattr(LOCAL, 'job', None)
        if j is None:
            try: return s.orig.write(t)
            except Exception: return len(t)
        for line in t.replace('\r', '\n').split('\n'):
            if not line.strip(): continue
            j['log'].append(line.strip()[:300])
            m = re.match(r'\[(\d+)/(\d+)\]', line.strip())
            if m: j['progress'] = int(m.group(1)) / max(int(m.group(2)), 1)
        return len(t)
    def flush(s): pass
sys.stdout = Tee(sys.__stdout__); sys.stderr = Tee(sys.__stderr__)

RULES_CACHE = {}

def new_examples():
    try:
        if not os.path.isdir(dj.LEARN_DIR): return 0
        mt = os.path.getmtime(dj.MODEL_PATH) if os.path.exists(dj.MODEL_PATH) else 0
        return sum(1 for x in os.listdir(dj.LEARN_DIR) if x.endswith('.npz') and os.path.getmtime(os.path.join(dj.LEARN_DIR, x)) > mt)
    except Exception: return 0

def run_job(title, fn):
    jid = str(int(time.time() * 1000)); job = dict(id=jid, title=title, status='running', log=[], progress=None, error=None, result=None, t=time.time())
    with JOB_LOCK: JOBS[jid] = job
    def go():
        LOCAL.job = job
        try: job['result'] = fn()
        except BaseException as e: job['error'] = (str(e) or repr(e)); job['status'] = 'error'
        if job['status'] != 'error': job['status'] = 'done'; job['progress'] = 1.0
    threading.Thread(target=go, daemon=True).start(); return jid

def safe_path(folder, name):
    p = os.path.normpath(os.path.join(folder, name))
    if os.path.dirname(p) != os.path.normpath(folder) or not os.path.exists(p) or not p.lower().endswith(dj.EXT): return None
    if os.path.normpath(folder) not in ALLOWED: return None
    return p

def read_review(folder):
    f = os.path.join(folder, 'review.csv')
    if not os.path.exists(f): return []
    marks = dj.load_marks(folder); out = []
    for r in csv.DictReader(open(f, newline='', encoding='utf-8-sig')):
        final = (r.get('edit_final') or r.get('final') or r.get('proposed') or '').strip()
        try: conf = float(r.get('confidence') or 0)
        except ValueError: conf = 0.0
        fl = r.get('flags') or ''; dup = 'DUPLICADO' in fl
        checked = (r['checked'] == '1') if r.get('checked') in ('0', '1') else (bool((r.get('final') or '').strip()) and not dup)
        p = dj.parse_name(final + '.mp3') if final else dj.parse_name(r['original'])
        out.append(dict(original=r['original'], proposed=r.get('proposed') or '', final=final, artist=r.get('artist') or '', confidence=conf, flags=fl, dup=dup,
                        checked=checked, reviewed=(r.get('reviewed') == '1'), parsed=p, marks=marks.get(r['original'])))
    return out

def write_review(folder, rows, marks):
    with open(os.path.join(folder, 'review.csv'), 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh); w.writerow(['original', 'proposed', 'confidence', 'flags', 'final', 'artist', 'reviewed', 'edit_final', 'checked'])
        for r in rows:
            fin = r['final'] if r.get('checked') else ''
            w.writerow([r['original'], r['final'], r['confidence'], r['flags'], fin, r['artist'], '1' if r.get('reviewed') else '0', r['final'], '1' if r.get('checked') else '0'])
    dj.save_marks(folder, marks or {})

def pick(kind):
    if sys.platform != 'darwin': return None
    if kind == 'folder': body = 'POSIX path of (choose folder with prompt "Elige la carpeta")'
    else: body = 'POSIX path of (choose file with prompt "Elige el rekordbox.xml" of type {"xml","public.xml"})'
    script = 'tell application "System Events"\nactivate\nset p to ' + body + '\nend tell\nreturn p'
    r = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    return r.stdout.strip().rstrip('/') if r.returncode == 0 and r.stdout.strip() else None

class H(BaseHTTPRequestHandler):
    def log_message(s, *a): pass
    def send_json(s, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode('utf-8'); s.send_response(code); s.send_header('Content-Type', 'application/json; charset=utf-8'); s.send_header('Content-Length', str(len(b))); s.send_header('Cache-Control', 'no-store'); s.end_headers(); s.wfile.write(b)
    def body(s):
        n = int(s.headers.get('Content-Length') or 0); return json.loads(s.rfile.read(n).decode('utf-8') or '{}') if n else {}
    def host_ok(s): return (s.headers.get('Host') or '').split(':')[0] in ('127.0.0.1', 'localhost')

    def do_GET(s):
        if not s.host_ok(): return s.send_error(403)
        u = urllib.parse.urlparse(s.path); q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path in ('/', '/index.html'):
                b = open(UI, 'rb').read(); s.send_response(200); s.send_header('Content-Type', 'text/html; charset=utf-8'); s.send_header('Content-Length', str(len(b))); s.send_header('Cache-Control', 'no-store'); s.end_headers(); s.wfile.write(b); return
            if u.path == '/api/ping': PING[0] = time.time(); return s.send_json(dict(ok=True))
            if u.path == '/api/state':
                c = load_cfg(); h = dj.last_history(); return s.send_json(dict(genres=dj.xml_genres(c.get('xml', '')), genre_model=os.path.exists(dj.GENRE_MODEL), cfg=c, model=os.path.exists(dj.MODEL_PATH), marks_model=os.path.exists(dj.MARKS_MODEL), undo=bool(h), learned=len(os.listdir(dj.LEARN_DIR)) if os.path.isdir(dj.LEARN_DIR) else 0, new_examples=new_examples(), new_marks=dj._newer(dj.LEARN_MARKS_DIR, dj.MARKS_MODEL), loop_len=dj._pref('loops', 8), grid_bias_ms=round(dj.grid_bias() * 1000), grid_samples=len(dj.load_prefs().get('grid') or [])))
            if u.path == '/api/rules':
                x = load_cfg().get('xml', ''); base = dict(a=0, b=4, c=8, off5=4, gap=dj._pref('gaps', 8))
                if x and os.path.exists(x):
                    key = (x, os.path.getmtime(x))
                    if key not in RULES_CACHE:
                        try: r, _t, _n = dj.learn_cue_rules(x); RULES_CACHE[key] = dict(a=r['0'][0], b=r['1'][0], c=r['2'][0], off5=r['x']['off5'], end=r['x']['end'])
                        except BaseException: RULES_CACHE[key] = {}
                    base.update(RULES_CACHE[key]); base['gap'] = dj._pref('gaps', base.get('end', 8))
                return s.send_json(base)
            if u.path == '/api/folder':
                f = q.get('folder', ''); ALLOWED.add(os.path.normpath(f))
                fs = [x for x in os.listdir(f) if x.lower().endswith(dj.EXT)] if os.path.isdir(f) else []
                done = sum(1 for x in fs if dj.is_done(os.path.join(f, x))); cx = os.path.join(f, 'djflow_cues.xml'); nc = 0
                if os.path.exists(cx):
                    try: nc = open(cx, encoding='utf-8').read().count('<TRACK TrackID=')
                    except Exception: pass
                return s.send_json(dict(total=len(fs), done=done, pending=len(fs) - done, cues=nc, analyzed=os.path.exists(os.path.join(f, 'review.csv'))))
            if u.path == '/api/review':
                f = q.get('folder', ''); ALLOWED.add(os.path.normpath(f)); return s.send_json(dict(rows=read_review(f)))
            if u.path == '/api/job':
                j = JOBS.get(q.get('id')); return s.send_json(dict(j, log=j['log'][-60:]) if j else dict(status='missing'))
            if u.path == '/api/track':
                f = q.get('folder', ''); p = safe_path(f, q.get('name', ''))
                if not p: return s.send_json(dict(error='archivo no encontrado'), 404)
                bpm = float(q.get('bpm') or 0) or dj.track_bpm_key(p)[0] or (dj.guess_from_name(p)[0] or 0)
                if not bpm: return s.send_json(dict(error='sin BPM'), 200)
                t0, b, sc = dj.detect_grid(p, bpm, fresh=q.get('fresh') == '1')
                try: cc = dj.cue_c_color(p, b, t0, os.path.basename(p))
                except Exception: cc = None
                return s.send_json(dict(t0=t0, bpm=b, score=sc, ccol=cc))
            if u.path == '/audio':
                p = safe_path(q.get('folder', ''), q.get('name', ''))
                if not p: return s.send_error(404)
                size = os.path.getsize(p); ct = mimetypes.guess_type(p)[0] or 'audio/mpeg'; rng = s.headers.get('Range'); start, end = 0, size - 1
                if rng and rng.startswith('bytes='):
                    a, _, b = rng[6:].partition('-'); start = int(a or 0); end = int(b) if b else size - 1
                s.send_response(206 if rng else 200); s.send_header('Content-Type', ct); s.send_header('Accept-Ranges', 'bytes'); s.send_header('Content-Length', str(end - start + 1))
                if rng: s.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                s.end_headers()
                with open(p, 'rb') as fh:
                    fh.seek(start); left = end - start + 1
                    while left > 0:
                        chunk = fh.read(min(1 << 20, left))
                        if not chunk: break
                        s.wfile.write(chunk); left -= len(chunk)
                return
            s.send_error(404)
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception as e:
            try: s.send_json(dict(error=str(e)), 500)
            except Exception: pass

    def do_POST(s):
        if not s.host_ok(): return s.send_error(403)
        u = urllib.parse.urlparse(s.path)
        try:
            d = s.body(); c = load_cfg()
            if u.path == '/api/cfg': c.update({k: v for k, v in d.items() if k in c}); save_cfg(c); return s.send_json(dict(cfg=c))
            if u.path == '/api/pick':
                p = pick(d.get('kind', 'folder'))
                if p:
                    if d.get('kind') == 'folder': ALLOWED.add(os.path.normpath(p))
                return s.send_json(dict(path=p))
            if u.path == '/api/analyze':
                f = d['folder']; ALLOWED.add(os.path.normpath(f)); c['folder'] = f; save_cfg(c)
                return s.send_json(dict(job=run_job('Analizando', lambda: dj.cmd_analyze(f, c.get('xml') or None))))
            if u.path == '/api/review':
                f = d['folder']; ALLOWED.add(os.path.normpath(f)); write_review(f, d['rows'], d.get('marks')); return s.send_json(dict(ok=True))
            if u.path == '/api/apply':
                f = d['folder']; ALLOWED.add(os.path.normpath(f)); write_review(f, d['rows'], d.get('marks')); bk = bool(d.get('backup', True))
                def job():
                    dj.cmd_apply(f, bk)
                    if d.get('cues') and c.get('xml'): dj.cmd_cues(c['xml'], f, only=dj.LAST_APPLIED, offset_ms=c.get('export_offset_ms', 0))
                    if c.get('auto_learn', True): dj.auto_learn(c.get('xml', ''), c.get('train', []), c.get('auto_n', 10))
                return s.send_json(dict(job=run_job('Aplicando', job)))
            if u.path == '/api/cues':
                f = d['folder']; return s.send_json(dict(job=run_job('Generando cues', lambda: dj.cmd_cues(c['xml'], f, offset_ms=c.get('export_offset_ms', 0)))))
            if u.path == '/api/undo': return s.send_json(dict(job=run_job('Deshaciendo', lambda: dj.cmd_undo(d.get('folder') or None))))
            if u.path == '/api/train': return s.send_json(dict(job=run_job('Entrenando', lambda: (dj.cmd_train(*c['train']), open(os.path.join(HERE, 'informe.md'), encoding='utf-8').read())[1])))
            if u.path == '/api/train_marks': return s.send_json(dict(job=run_job('Aprendiendo START MIX', lambda: (None, dj.learn_from_xml(c['xml']))[1])))
            if u.path == '/api/reveal':
                subprocess.Popen(['open', '-R', d['path']] if os.path.exists(d.get('path', '')) else ['true']); return s.send_json(dict(ok=True))
            s.send_error(404)
        except Exception as e:
            s.send_json(dict(error=str(e)), 500)

def free_port(start=8765):
    for p in range(start, start + 30):
        with socket.socket() as k:
            if k.connect_ex(('127.0.0.1', p)) != 0: return p
    return start

def open_window(url):
    if sys.platform == 'darwin':
        for app in ('Google Chrome', 'Brave Browser', 'Microsoft Edge', 'Chromium'):
            if os.path.exists(f'/Applications/{app}.app'):
                subprocess.Popen(['open', '-na', app, '--args', f'--app={url}', '--window-size=1500,940']); return
    webbrowser.open(url)

def watchdog(srv):
    """Cierra el servidor cuando se cierra la ventana (sin pings ~30 s) y no hay trabajos en marcha."""
    while True:
        time.sleep(3)
        busy = any(j['status'] == 'running' for j in JOBS.values())
        if PING[0] and time.time() - PING[0] > float(os.environ.get('WF_IDLE', 30)) and not busy:
            print('Ventana cerrada: cerrando servidor.', file=sys.__stdout__); os._exit(0)

def already_running():
    import urllib.request
    for p in range(8765, 8795):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{p}/api/ping', timeout=0.6) as r:
                if r.status == 200: return p
        except Exception: pass
    return None

if __name__ == '__main__':
    other = already_running()
    if other and '--no-open' not in sys.argv:
        open_window(f'http://127.0.0.1:{other}/'); sys.exit(0)
    port = free_port(); srv = ThreadingHTTPServer(('127.0.0.1', port), H); url = f'http://127.0.0.1:{port}/'
    print(f'Dmzeta Workflow en {url}  (Ctrl+C para cerrar)', file=sys.__stdout__)
    threading.Thread(target=watchdog, args=(srv,), daemon=True).start()
    if '--no-open' not in sys.argv: threading.Timer(0.6, lambda: open_window(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
