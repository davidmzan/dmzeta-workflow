#!/usr/bin/env python3
"""Dmzeta Workflow · ventana de Mac. Uso: python3 djflow_app.py"""
import os, sys, csv, json, time, shutil, subprocess, threading, tkinter as tk
import numpy as np
from tkinter import ttk, filedialog, messagebox
import djflow as dj

BG, PANEL, CARD, LINE = '#0e0e11', '#16161b', '#1d1d24', '#2a2a33'
TXT, MUTED, ACC, ACC2, OK, WARN = '#f2f2f5', '#9a9aa6', '#7c5cff', '#9b83ff', '#34d399', '#fbbf24'
FONT, FB = ('Helvetica Neue', 12), ('Helvetica Neue', 12, 'bold')
CFG = os.path.join(dj.HERE, 'config.json')

def load_cfg():
    try: return json.load(open(CFG, encoding='utf-8'))
    except Exception: return {'train': [], 'xml': '', 'folder': ''}

def save_cfg(c):
    try: json.dump(c, open(CFG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    except Exception: pass

class WaveView(tk.Canvas):
    """Onda de la pista con rejilla de compases, selección con arrastre y marca del corte del extender."""
    def __init__(s, parent, on_change):
        super().__init__(parent, height=150, bg='#0a0a0d', highlightthickness=0, cursor='crosshair')
        s.y = None; s.sr = 8000; s.t0 = 0.052; s.bpm = 0; s.bars = None; s.vs = 0.0; s.ve = 1.0
        s.cursor_t = None; s.sel = None; s.ph = None; s.anchor = None; s.on_change = on_change; s.marks = None
        s.bind('<Configure>', lambda e: s.draw()); s.bind('<ButtonPress-1>', s.down); s.bind('<B1-Motion>', s.drag); s.bind('<ButtonRelease-1>', s.up)

    @property
    def dur(s): return len(s.y) / s.sr if s.y is not None else 0.0
    def set_track(s, y, sr, t0, bpm, bars, keep_view=False):
        s.y, s.sr, s.t0, s.bpm, s.bars = y, sr, t0, bpm, bars
        if not keep_view: s.vs, s.ve = 0.0, max(s.dur, 1.0); s.cursor_t = None; s.sel = None
        s.draw()
    def set_view(s, a, b):
        a = max(0.0, a); b = min(s.dur, b)
        if b - a < 2: return
        s.vs, s.ve = a, b; s.draw()
    def t_of(s, x): return s.vs + max(0, min(x, s.winfo_width())) / max(s.winfo_width(), 1) * (s.ve - s.vs)
    def x_of(s, t): return (t - s.vs) / (s.ve - s.vs) * s.winfo_width()
    def down(s, e):
        if s.y is None: return
        s.anchor = e.x; s.cursor_t = s.t_of(e.x); s.sel = None; s.draw(); s.on_change()
    def drag(s, e):
        if s.anchor is None: return
        if abs(e.x - s.anchor) > 3: a, b = sorted((s.t_of(s.anchor), s.t_of(e.x))); s.sel = (a, b); s.draw(); s.on_change()
    def up(s, e): s.anchor = None
    def label(s):
        if s.cursor_t is None: return ''
        t = s.sel[0] if s.sel else s.cursor_t; bar = 240.0 / s.bpm if s.bpm else 0
        b = int(round((t - s.t0) / bar)) if bar else 0
        out = f'{int(t // 60)}:{t % 60:04.1f}' + (f'  ·  compás {b}' if bar else '')
        if s.sel: out += f'  ·  selección {s.sel[1] - s.sel[0]:.1f} s'
        return out

    def draw(s):
        s.delete('all'); w, h = s.winfo_width(), s.winfo_height()
        if s.y is None or w < 10: s.create_text(w // 2, h // 2, text='Selecciona una fila para ver la onda', fill=MUTED, font=('Helvetica Neue', 11)); return
        if s.sel: s.create_rectangle(s.x_of(s.sel[0]), 0, s.x_of(s.sel[1]), h, fill='#2b2350', outline='')
        i0, i1 = int(s.vs * s.sr), int(s.ve * s.sr); seg = np.abs(s.y[i0:i1])
        if len(seg) > w:
            edges = np.linspace(0, len(seg), w + 1).astype(int); edges[-1] = min(edges[-1], len(seg))
            pk = np.maximum.reduceat(seg, edges[:-1]) if len(seg) else np.zeros(w)
        else: pk = np.pad(seg, (0, max(0, w - len(seg))))
        mx = max(float(np.percentile(np.abs(s.y), 99.5)), 1e-4); mid = h / 2
        for x in range(min(w, len(pk))):
            a = min(1.0, pk[x] / mx) * (h / 2 - 14); s.create_line(x, mid - a, x, mid + a, fill=ACC)
        if s.bpm:
            bar = 240.0 / s.bpm; span = s.ve - s.vs
            if span / bar <= 220:
                b0 = max(0, int((s.vs - s.t0) // bar))
                b = b0
                while s.t0 + b * bar <= s.ve:
                    x = s.x_of(s.t0 + b * bar)
                    if 0 <= x <= w:
                        strong = b % 8 == 0
                        if strong or span / bar <= 70: s.create_line(x, 0, x, h, fill='#4a4a58' if strong else '#2a2a33')
                        if strong: s.create_text(x + 3, 8, text=str(b), fill=MUTED, anchor='w', font=('Helvetica Neue', 9))
                    b += 1
            if s.bars:
                x = s.x_of(s.t0 + s.bars * bar)
                if 0 <= x <= w: s.create_line(x, 0, x, h, fill=WARN, width=2); s.create_text(x + 4, h - 10, text=f'corte propuesto ({s.bars} compases)', fill=WARN, anchor='w', font=('Helvetica Neue', 10, 'bold'))
        mk = s.marks or {}
        if s.bpm and mk:
            bar = 240.0 / s.bpm
            def flag(b, col, text, dy=24):
                x = s.x_of(s.t0 + b * bar)
                if 0 <= x <= w: s.create_line(x, 0, x, h, fill=col, width=2); s.create_text(x + 4, dy, text=text, fill=col, anchor='w', font=('Helvetica Neue', 10, 'bold'))
            if mk.get('start') is not None: flag(mk['start'], '#fb923c', 'START MIX'); flag(mk['start'] + 4, '#fdba74', 'hot 5', 40)
            if mk.get('end') is not None: flag(mk['end'], '#ef4444', 'END MIX')
            if mk.get('loop'):
                ls, ll = mk['loop']; x1, x2 = s.x_of(s.t0 + ls * bar), s.x_of(s.t0 + (ls + ll) * bar)
                s.create_rectangle(max(0, x1), h - 26, min(w, x2), h - 4, outline='#ec4899', width=2); s.create_text(max(2, x1) + 4, h - 15, text='LOOP', fill='#ec4899', anchor='w', font=('Helvetica Neue', 10, 'bold'))
        if s.cursor_t is not None and s.vs <= s.cursor_t <= s.ve:
            x = s.x_of(s.cursor_t); s.create_line(x, 0, x, h, fill='white', width=1)
        s.create_text(w - 6, 8, text=s.label(), fill=TXT, anchor='e', font=('Helvetica Neue', 10))
        s.draw_ph()

    def draw_ph(s):
        s.delete('ph')
        if s.ph is not None and s.vs <= s.ph <= s.ve: x = s.x_of(s.ph); s.create_line(x, 0, x, s.winfo_height(), fill=OK, width=2, tags='ph')

class Btn(tk.Label):
    """Botón propio (los botones nativos de Mac ignoran los colores)."""
    def __init__(s, parent, text, cmd, primary=True):
        s.c1, s.c2 = (ACC, ACC2) if primary else (LINE, '#383844')
        super().__init__(parent, text=text, bg=s.c1, fg='white' if primary else TXT, font=FB, padx=14, pady=7, cursor='pointinghand')
        s.cmd = cmd; s.bind('<Button-1>', lambda e: s.cmd()); s.bind('<Enter>', lambda e: s.config(bg=s.c2)); s.bind('<Leave>', lambda e: s.config(bg=s.c1))

class Step(tk.Frame):
    """Tarjeta de un paso: número, título, botones y desplegable '¿Qué hace?'."""
    def __init__(s, parent, n, title, help_text):
        super().__init__(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        s.help_text = help_text; s.open = False
        head = tk.Frame(s, bg=CARD); head.pack(fill='x', padx=12, pady=(10, 4))
        tk.Label(head, text=str(n), bg=ACC, fg='white', font=FB, width=2).pack(side='left')
        tk.Label(head, text=title, bg=CARD, fg=TXT, font=('Helvetica Neue', 13, 'bold')).pack(side='left', padx=10)
        s.body = tk.Frame(s, bg=CARD); s.body.pack(fill='x', padx=12, pady=(2, 4))
        s.tg = tk.Label(s, text='▸  ¿Qué hace?', bg=CARD, fg=MUTED, font=('Helvetica Neue', 11), cursor='pointinghand', anchor='w')
        s.tg.pack(fill='x', padx=12, pady=(0, 8)); s.tg.bind('<Button-1>', lambda e: s.toggle())
        s.info = tk.Label(s, text=help_text, bg=CARD, fg=MUTED, font=('Helvetica Neue', 11), justify='left', wraplength=300, anchor='w')

    def toggle(s):
        s.open = not s.open
        if s.open: s.info.pack(fill='x', padx=12, pady=(0, 10)); s.tg.config(text='▾  ¿Qué hace?', fg=ACC2)
        else: s.info.pack_forget(); s.tg.config(text='▸  ¿Qué hace?', fg=MUTED)

class Log:
    def __init__(s, w): s.w = w
    def write(s, t):
        if t.strip(): s.w.after(0, lambda: (s.w.config(state='normal'), s.w.insert('end', t if t.endswith('\n') else t + '\n'), s.w.see('end'), s.w.config(state='disabled')))
    def flush(s): pass

class App(tk.Tk):
    def __init__(s):
        super().__init__(); s.title('Dmzeta Workflow'); s.geometry('1280x900'); s.minsize(1100, 680); s.configure(bg=BG)
        s.cfg = load_cfg(); s.folder = s.cfg.get('folder') or None
        st = ttk.Style(s); st.theme_use('clam')
        st.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TXT, rowheight=28, borderwidth=0, font=FONT)
        st.configure('Treeview.Heading', background=CARD, foreground=MUTED, borderwidth=0, font=FB, relief='flat')
        st.map('Treeview', background=[('selected', ACC)], foreground=[('selected', 'white')])
        st.configure('Vertical.TScrollbar', background=CARD, troughcolor=PANEL, borderwidth=0, arrowcolor=MUTED)
        st.configure('Horizontal.TScrollbar', background=CARD, troughcolor=PANEL, borderwidth=0, arrowcolor=MUTED)
        st.configure('Horizontal.TProgressbar', background=ACC, troughcolor=LINE, borderwidth=0)

        hd = tk.Frame(s, bg=BG); hd.pack(fill='x', padx=24, pady=(18, 8))
        tk.Label(hd, text='Dmzeta Workflow', bg=BG, fg=TXT, font=('Helvetica Neue', 26, 'bold')).pack(side='left')
        tk.Label(hd, text='  prepara, nombra y marca tu música antes de Rekordbox', bg=BG, fg=MUTED, font=('Helvetica Neue', 13)).pack(side='left', pady=(10, 0))
        s.status = tk.StringVar(value='Listo'); s.dot = tk.Label(hd, textvariable=s.status, bg=BG, fg=OK, font=FB); s.dot.pack(side='right')
        s.prog = ttk.Progressbar(s, mode='indeterminate', style='Horizontal.TProgressbar'); s.prog.pack(fill='x', padx=24)

        main = tk.Frame(s, bg=BG); main.pack(fill='both', expand=True, padx=24, pady=12)
        left = tk.Frame(main, bg=BG, width=340); left.pack(side='left', fill='y'); left.pack_propagate(False)
        right = tk.Frame(main, bg=BG); right.pack(side='left', fill='both', expand=True, padx=(16, 0))

        s.backup_on = True
        Btn(left, '▶  Procesar carpeta (todo en uno)', s.process).pack(fill='x', pady=(0, 10))
        # 1 Entrenar
        c1 = Step(left, 1, 'Aprender de mi biblioteca', 'Lee las pistas que ya tienes bien nombradas (Título (8 Bars POE) - 8B - 115) y aprende cómo las nombras: compases del extender, tipo POE/MOE/FME y avisos. Solo lee los archivos, no los toca. Además aprende solo de lo que revisas y aplicas en el paso 3 (tus correcciones). Repítelo de vez en cuando. La 1ª vez tarda; luego usa caché.')
        c1.pack(fill='x', pady=(0, 10)); s.lbl_train = tk.Label(c1.body, bg=CARD, fg=MUTED, font=('Helvetica Neue', 11), anchor='w', justify='left'); s.lbl_train.pack(fill='x', pady=(0, 6))
        r = tk.Frame(c1.body, bg=CARD); r.pack(fill='x'); Btn(r, 'Añadir carpeta', s.add_train, False).pack(side='left'); Btn(r, 'Entrenar', s.train).pack(side='left', padx=8); Btn(r, 'Vaciar', s.clear_train, False).pack(side='left')
        # 2 Analizar
        c2 = Step(left, 2, 'Analizar canciones nuevas', 'Elige la carpeta con las canciones nuevas (ya pasadas por Mixed In Key). Propone el nombre de cada una: compases, tipo, BPM y tono, y las ordena de más dudosas a más seguras. Mashup, In Aca, In Hype y Short Edit los añades tú.')
        c2.pack(fill='x', pady=(0, 10)); s.lbl_folder = tk.Label(c2.body, bg=CARD, fg=MUTED, font=('Helvetica Neue', 11), anchor='w', justify='left', wraplength=300); s.lbl_folder.pack(fill='x', pady=(0, 6))
        Btn(c2.body, 'Elegir carpeta y analizar', s.analyze).pack(anchor='w')
        # 3 Aplicar
        c3 = Step(left, 3, 'Aplicar nombres y limpiar tags', 'Renombra los archivos con la columna "Nombre final" y deja solo los tags: título (= nombre del archivo), artista (separados por comas: Artista 1, Artista 2), álbum (= carpeta), BPM y tono. Quita portada, comentarios y el resto. No recodifica el audio. Solo se aplican las filas marcadas con ☑. Con la copia de seguridad puedes deshacer la última tanda. No lo uses con pistas que ya estén en Rekordbox.')
        c3.pack(fill='x', pady=(0, 10)); r3 = tk.Frame(c3.body, bg=CARD); r3.pack(fill='x'); Btn(r3, 'Aplicar nombres', s.apply).pack(side='left'); Btn(r3, 'Deshacer última tanda', s.undo, False).pack(side='left', padx=8)
        s.btn_bk = Btn(c3.body, 'Copia de seguridad: sí', s.toggle_backup, False); s.btn_bk.pack(anchor='w', pady=(6, 0))
        # 4 Cues
        c4 = Step(left, 4, 'Generar cues para Rekordbox', 'Aprende de tu rekordbox.xml dónde pones INTRO y los hot cues A, B y C, y crea djflow_cues.xml en la carpeta nueva. Lo importas en Rekordbox (visor de rekordbox xml) y las pistas entran con cues y beat grid. START MIX, END MIX y el loop los propone el modelo si lo has entrenado (botón de abajo), y los ajustas sobre la onda. Con el XML también detecta duplicados al analizar.')
        c4.pack(fill='x'); s.lbl_xml = tk.Label(c4.body, bg=CARD, fg=MUTED, font=('Helvetica Neue', 11), anchor='w', justify='left', wraplength=300); s.lbl_xml.pack(fill='x', pady=(0, 6))
        r = tk.Frame(c4.body, bg=CARD); r.pack(fill='x'); Btn(r, 'Elegir rekordbox.xml', s.pick_xml, False).pack(side='left'); Btn(r, 'Generar cues', s.cues).pack(side='left', padx=8)
        Btn(c4.body, 'Aprender START MIX de mi colección', s.train_marks, False).pack(anchor='w', pady=(6, 0))

        # derecha: tabla + registro
        th = tk.Frame(right, bg=BG); th.pack(fill='x', pady=(0, 6))
        tk.Label(th, text='Nombres propuestos  ·  ☑ = se aplica  ·  doble clic para editar', bg=BG, fg=MUTED, font=FB, anchor='w').pack(side='left')
        Btn(th, 'Confirmar: aplicar + cues', s.confirm_all).pack(side='right')
        tf = tk.Frame(right, bg=PANEL, highlightbackground=LINE, highlightthickness=1); tf.pack(fill='both', expand=True)
        cols = ('original', 'final', 'artist', 'confidence', 'flags')
        s.tv = ttk.Treeview(tf, columns=cols, show=('tree', 'headings'))
        s.tv.column('#0', width=56, minwidth=56, stretch=False, anchor='center'); s.tv.heading('#0', text='Aplicar', command=s.toggle_all)
        for c, t, w in zip(cols, ('Original', 'Nombre final', 'Artista(s)', 'Confianza', 'Avisos'), (260, 420, 220, 80, 700)):
            s.tv.heading(c, text=t); s.tv.column(c, width=w, minwidth=w, anchor='w', stretch=False)
        sb = ttk.Scrollbar(tf, orient='vertical', command=s.tv.yview); sh = ttk.Scrollbar(tf, orient='horizontal', command=s.tv.xview)
        s.tv.configure(yscrollcommand=sb.set, xscrollcommand=sh.set)
        tf.grid_rowconfigure(0, weight=1); tf.grid_columnconfigure(0, weight=1)
        s.tv.grid(row=0, column=0, sticky='nsew'); sb.grid(row=0, column=1, sticky='ns'); sh.grid(row=1, column=0, sticky='ew')
        s.tv.bind('<Shift-MouseWheel>', lambda e: s.tv.xview_scroll(-1 * int(e.delta), 'units'))
        s.tv.tag_configure('dup', foreground='#f87171'); s.tv.bind('<Button-1>', s.click_cell, add='+'); s.tv.bind('<<TreeviewSelect>>', lambda e: s.select()); s.tv.tag_configure('low', foreground=WARN); s.tv.tag_configure('seen', foreground=OK); s.tv.tag_configure('ok', foreground=TXT); s.tv.bind('<Double-1>', s.edit)
        pl = tk.Frame(right, bg=CARD, highlightbackground=LINE, highlightthickness=1); pl.pack(fill='x', pady=(10, 0))
        s.now = tk.Label(pl, text='Selecciona una fila para ver la onda y escuchar', bg=CARD, fg=MUTED, font=('Helvetica Neue', 11), anchor='w')
        s.now.pack(fill='x', padx=12, pady=(8, 4))
        s.wave = WaveView(pl, lambda: None); s.wave.pack(fill='x', padx=12)
        pr = tk.Frame(pl, bg=CARD); pr.pack(fill='x', padx=12, pady=(6, 2))
        Btn(pr, '▶ Reproducir', s.play).pack(side='left'); Btn(pr, '■ Parar', s.stop, False).pack(side='left', padx=6)
        s.clicks_on = True; s.btn_clk = Btn(pr, 'Clics: sí', s.toggle_clicks, False); s.btn_clk.pack(side='left')
        Btn(pr, 'Todo', lambda: s.zoom('all'), False).pack(side='left', padx=(18, 6)); Btn(pr, 'Inicio', lambda: s.zoom('start'), False).pack(side='left')
        Btn(pr, 'Corte', lambda: s.zoom('cut'), False).pack(side='left', padx=6); Btn(pr, 'Final', lambda: s.zoom('end'), False).pack(side='left')
        Btn(pr, '+', lambda: s.zoom('in'), False).pack(side='left', padx=(18, 4)); Btn(pr, '−', lambda: s.zoom('out'), False).pack(side='left')
        pr2 = tk.Frame(pl, bg=CARD); pr2.pack(fill='x', padx=12, pady=(2, 2))
        for t, k in (('Grid −1 beat', ('beat', -1)), ('Grid +1 beat', ('beat', 1)), ('−10 ms', ('ms', -0.010)), ('+10 ms', ('ms', 0.010))): Btn(pr2, t, lambda k=k: s.nudge(*k), False).pack(side='left', padx=(0, 4))
        Btn(pr2, 'Grid detectado', lambda: s.nudge('reset', 0), False).pack(side='left', padx=(0, 14))
        for t, k in (('START MIX aquí', 'start'), ('END MIX aquí', 'end'), ('Loop aquí', 'loop'), ('Quitar marcas', 'clear')): Btn(pr2, t, lambda k=k: s.mark_here(k), False).pack(side='left', padx=(0, 4))
        tk.Label(pl, text='Clic en la onda = punto de inicio. Arrastra = seleccionar un fragmento. Sin selección suenan 20 s desde el punto. Línea amarilla = corte del extender. Las marcas START MIX / END MIX / Loop se colocan en el compás más cercano al punto marcado y van al XML de Rekordbox.', bg=CARD, fg=MUTED, font=('Helvetica Neue', 10), anchor='w', justify='left', wraplength=780).pack(fill='x', padx=12, pady=(2, 8))
        s.proc = None; s.cur = None; s.loaded = None; s.play_t0 = None; s.reviewed = set(); s.marks = {}
        tk.Label(right, text='Registro', bg=BG, fg=MUTED, font=FB, anchor='w').pack(fill='x', pady=(10, 6))
        s.log = tk.Text(right, height=8, bg=PANEL, fg=MUTED, bd=0, highlightbackground=LINE, highlightthickness=1, font=('Menlo', 11), state='disabled', wrap='word')
        s.log.pack(fill='x'); sys.stdout = Log(s.log); sys.stderr = Log(s.log)
        s.refresh()
        print('Siguiente paso: 1 Aprender (una vez), 2 Analizar, 3 Aplicar, 4 Cues.')

    def refresh(s):
        n = len(s.cfg.get('train', []))
        s.lbl_train.config(text=(f'{n} carpeta(s) añadidas:\n' + '\n'.join('· ' + os.path.basename(p) for p in s.cfg['train'][:6]) + ('\n…' if n > 6 else '')) if n else 'Aún no hay carpetas de entrenamiento.')
        s.lbl_folder.config(text=('Carpeta: ' + os.path.basename(s.folder)) if s.folder else 'Aún no has elegido carpeta.')
        s.lbl_xml.config(text=('XML: ' + os.path.basename(s.cfg['xml'])) if s.cfg.get('xml') else 'Aún no has elegido rekordbox.xml.')

    def busy(s, on, msg=''):
        s.status.set(msg if on else 'Listo'); s.dot.config(fg=WARN if on else OK)
        (s.prog.start(12) if on else s.prog.stop())

    def bg(s, msg, fn, done=None):
        s.busy(True, msg)
        def run():
            err = None
            try: fn()
            except BaseException as e: err = str(e) or repr(e)
            def fin():
                s.busy(False)
                if err: messagebox.showerror('Dmzeta Workflow', err)
                elif done: done()
            s.after(0, fin)
        threading.Thread(target=run, daemon=True).start()

    def cur_name(s): return os.path.basename(s.cur[0]) if s.cur else None

    def persist(s):
        if s.folder:
            try: dj.save_marks(s.folder, s.marks)
            except Exception as e: print('No se pudieron guardar las marcas:', e)

    def apply_marks_to_wave(s):
        o = s.cur_name(); mk = s.marks.get(o) or {}
        if mk.get('t0') is not None: s.wave.t0 = float(mk['t0'])
        s.wave.marks = mk; s.wave.draw()

    def nudge(s, kind, v):
        w = s.wave; o = s.cur_name()
        if w.y is None or not o or not w.bpm: return messagebox.showinfo('Dmzeta Workflow', 'Selecciona una fila y espera a que cargue la onda.')
        mk = s.marks.setdefault(o, {})
        if kind == 'reset': w.t0 = s.loaded[3] if s.loaded else w.t0; mk.pop('t0', None)
        else:
            w.t0 = max(0.0, w.t0 + (v * 60.0 / w.bpm if kind == 'beat' else v)); mk['t0'] = round(w.t0, 4)
        s.mark_seen(); s.persist(); w.marks = mk; w.draw()

    def mark_here(s, kind):
        w = s.wave; o = s.cur_name()
        if w.y is None or not o or not w.bpm: return messagebox.showinfo('Dmzeta Workflow', 'Selecciona una fila y espera a que cargue la onda.')
        mk = s.marks.setdefault(o, {})
        if kind == 'clear':
            for k in ('start', 'end', 'loop'): mk.pop(k, None)
        else:
            if w.cursor_t is None: return messagebox.showinfo('Dmzeta Workflow', 'Haz clic en la onda donde quieras la marca.')
            b = int(round((w.cursor_t - w.t0) / (240.0 / w.bpm)))
            if kind == 'start': mk['start'] = b; mk['end'] = b + 8; mk.pop('auto', None)
            elif kind == 'end': mk['end'] = b
            elif kind == 'loop': mk['loop'] = [b, 8]
        s.mark_seen(); s.persist(); w.marks = mk; w.draw()

    def select(s):
        it = s.tv.selection()
        if not it or not s.folder: return
        v = s.tv.item(it[0], 'values'); s.stop(); path = os.path.join(s.folder, v[0]); s.cur = (path, v[1])
        s.now.config(text='Seleccionada: ' + v[0][:110], fg=TXT)
        p = dj.parse_name(v[1])
        if s.loaded and s.loaded[0] == path:
            s.wave.set_track(s.loaded[1], s.loaded[2], s.loaded[3], s.loaded[4], p['bars'], keep_view=True); s.apply_marks_to_wave(); return
        if not os.path.exists(path): return
        def job():
            try:
                y, sr = dj.load_wave(path); bpm0 = p['bpm'] or dj.track_bpm_key(path)[0]; t0, bpm, _sc = dj.detect_grid(path, bpm0) if bpm0 else (0.052, 0, 0)
            except Exception as e: return s.after(0, lambda: messagebox.showerror('Dmzeta Workflow', str(e)))
            def go():
                if s.cur and s.cur[0] == path: s.loaded = (path, y, sr, t0, bpm); s.wave.set_track(y, sr, t0, bpm, p['bars']); s.apply_marks_to_wave()
            s.after(0, go)
        threading.Thread(target=job, daemon=True).start()

    def mark_seen(s, it=None):
        it = it or (s.tv.selection() or [None])[0]
        if not it: return
        o = s.tv.item(it, 'values')[0]; s.reviewed.add(o); tg = [t for t in s.tv.item(it, 'tags') if t != 'seen'] + ['seen']; s.tv.item(it, tags=tuple(tg))

    def toggle_clicks(s): s.clicks_on = not s.clicks_on; s.btn_clk.config(text='Clics: sí' if s.clicks_on else 'Clics: no')

    def zoom(s, mode):
        w = s.wave
        if w.y is None: return
        bar = 240.0 / w.bpm if w.bpm else 2.0
        if mode == 'all': w.set_view(0, w.dur)
        elif mode == 'start': w.set_view(0, min(w.dur, 24 * bar))
        elif mode == 'end': w.set_view(max(0, w.dur - 24 * bar), w.dur)
        elif mode == 'cut':
            c = w.t0 + (w.bars or 8) * bar; w.set_view(c - 12 * bar, c + 12 * bar)
        else:
            mid = w.cursor_t if w.cursor_t is not None else (w.vs + w.ve) / 2; half = (w.ve - w.vs) / 2 * (0.5 if mode == 'in' else 2)
            w.set_view(max(0, mid - half), min(w.dur, mid + half))

    def stop(s):
        if s.proc and s.proc.poll() is None: s.proc.terminate()
        s.proc = None; s.play_t0 = None
        try: s.wave.ph = None; s.wave.draw_ph()
        except Exception: pass

    def play(s):
        w = s.wave
        if not s.cur or w.y is None or not os.path.exists(s.cur[0]): return messagebox.showinfo('Dmzeta Workflow', 'Selecciona una fila y espera a que cargue la onda (el archivo debe seguir con su nombre original).')
        if not shutil.which('afplay'): return messagebox.showinfo('Dmzeta Workflow', 'No encuentro afplay (reproductor de macOS).')
        if not w.bpm: return messagebox.showinfo('Dmzeta Workflow', 'Esta pista no tiene BPM.')
        if w.sel: start, dur = w.sel[0], min(60.0, w.sel[1] - w.sel[0])
        else: start, dur = (w.cursor_t if w.cursor_t is not None else w.vs), 20.0
        dur = max(1.0, min(dur, w.dur - start)); path = s.cur[0]; s.mark_seen(); s.stop(); s.status.set('Preparando audio…'); s.dot.config(fg=WARN)
        def job():
            try: wav = dj.make_clip(path, w.bpm, w.bars, start, dur, s.clicks_on, w.t0)
            except Exception as e: return s.after(0, lambda: messagebox.showerror('Dmzeta Workflow', str(e)))
            def go():
                s.status.set('Listo'); s.dot.config(fg=OK); s.proc = subprocess.Popen(['afplay', wav]); s.play_t0 = (time.time(), start, dur); s.tick()
            s.after(0, go)
        threading.Thread(target=job, daemon=True).start()

    def tick(s):
        if not s.play_t0 or not s.proc or s.proc.poll() is not None: s.stop(); return
        t, st, du = s.play_t0; s.wave.ph = st + min(du, time.time() - t); s.wave.draw_ph(); s.after(40, s.tick)

    def add_train(s):
        d = filedialog.askdirectory(title='Carpeta con pistas ya bien nombradas')
        if d and d not in s.cfg['train']: s.cfg['train'].append(d); save_cfg(s.cfg); s.refresh()

    def clear_train(s): s.cfg['train'] = []; save_cfg(s.cfg); s.refresh()

    def train(s):
        if not s.cfg['train'] and not os.path.isdir(dj.LEARN_DIR): return messagebox.showinfo('Dmzeta Workflow', 'Primero añade al menos una carpeta.')
        ds = list(s.cfg['train'])
        def done():
            try: messagebox.showinfo('Entrenado', open(os.path.join(dj.HERE, 'informe.md'), encoding='utf-8').read())
            except Exception: pass
        s.bg('Aprendiendo…', lambda: dj.cmd_train(*ds), done)

    def analyze(s):
        d = filedialog.askdirectory(title='Carpeta con canciones nuevas')
        if not d: return
        s.folder = d; s.cfg['folder'] = d; save_cfg(s.cfg); s.refresh()
        s.bg('Analizando…', lambda: dj.cmd_analyze(d, s.cfg.get('xml') or None), s.load)

    def load(s):
        s.marks = dj.load_marks(s.folder); s.tv.delete(*s.tv.get_children())
        with open(os.path.join(s.folder, 'review.csv'), newline='', encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                try: low = float(r['confidence']) < 0.6
                except ValueError: low = True
                dup = 'DUPLICADO' in r['flags']; on = bool(r['final']) and not dup
                s.tv.insert('', 'end', text='☑' if on else '☐', values=(r['original'], r['final'], r.get('artist', ''), r['confidence'], r['flags']), tags=('dup',) if dup else ('low' if low else 'ok',))

    def edit(s, ev):
        it = s.tv.identify_row(ev.y)
        if not it: return
        v = list(s.tv.item(it, 'values')); top = tk.Toplevel(s); top.configure(bg=CARD); top.title('Editar nombre')
        tk.Label(top, text=v[0], bg=CARD, fg=MUTED, font=('Helvetica Neue', 11)).pack(anchor='w', padx=14, pady=(12, 4))
        e = tk.Entry(top, width=90, bg=PANEL, fg=TXT, insertbackground=TXT, bd=0, highlightthickness=1, highlightbackground=LINE, font=FONT); e.insert(0, v[1]); e.pack(padx=14, pady=(0, 6), ipady=6); e.focus()
        tk.Label(top, text='Artista(s), separados por comas', bg=CARD, fg=MUTED, font=('Helvetica Neue', 11)).pack(anchor='w', padx=14)
        ea = tk.Entry(top, width=90, bg=PANEL, fg=TXT, insertbackground=TXT, bd=0, highlightthickness=1, highlightbackground=LINE, font=FONT); ea.insert(0, v[2]); ea.pack(padx=14, pady=(0, 6), ipady=6)
        row = tk.Frame(top, bg=CARD); row.pack(padx=14, pady=(0, 12), anchor='w')
        def add(t): e.insert('end', ' ' + t if not e.get().endswith(' ') else t)
        def ok(_=None): changed = (v[1], v[2]) != tuple(s.tv.item(it, 'values')[1:3]); v[1] = e.get(); v[2] = ea.get(); s.tv.item(it, values=v); top.destroy(); s.mark_seen(it); s.select()
        for t in ('(Mashup)', '(In Aca)', '(In Hype)', '(Short Edit)', '(Aca Out)'):
            b = Btn(row, t, lambda t=t: add(t), False); b.pack(side='left', padx=(0, 6))
        Btn(row, 'Guardar', ok).pack(side='left', padx=(12, 0)); e.bind('<Return>', ok); ea.bind('<Return>', ok)

    def save_review(s):
        with open(os.path.join(s.folder, 'review.csv'), 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh); w.writerow(['original', 'proposed', 'confidence', 'flags', 'final', 'artist', 'reviewed'])
            for i in s.tv.get_children():
                o, f, ar, c, fl = s.tv.item(i, 'values'); f2 = f if s.tv.item(i, 'text') == '☑' else ''; w.writerow([o, f, c, fl, f2, ar, '1' if o in s.reviewed else '0'])

    def apply(s):
        if not s.folder or not s.tv.get_children(): return messagebox.showinfo('Dmzeta Workflow', 'Primero analiza una carpeta.')
        if not messagebox.askyesno('Aplicar nombres', 'Se renombrarán los archivos y se limpiarán sus tags.\nNo lo hagas con pistas que ya estén en Rekordbox.\n\n¿Continuar?'): return
        s.save_review(); s.persist(); s.bg('Aplicando…', lambda: dj.cmd_apply(s.folder, s.backup_on), lambda: (s.tv.delete(*s.tv.get_children()), setattr(s, 'marks', dj.load_marks(s.folder))))

    def click_cell(s, e):
        if s.tv.identify_region(e.x, e.y) == 'tree' or (s.tv.identify_column(e.x) == '#0' and s.tv.identify_row(e.y)):
            it = s.tv.identify_row(e.y)
            if it: s.tv.item(it, text='☐' if s.tv.item(it, 'text') == '☑' else '☑')

    def toggle_all(s):
        items = s.tv.get_children()
        if not items: return
        new = '☐' if all(s.tv.item(i, 'text') == '☑' for i in items) else '☑'
        for i in items: s.tv.item(i, text=new)

    def toggle_backup(s): s.backup_on = not s.backup_on; s.btn_bk.config(text='Copia de seguridad: sí' if s.backup_on else 'Copia de seguridad: no')

    def undo(s):
        if not messagebox.askyesno('Deshacer', 'Se restaurarán los archivos de la última tanda aplicada (nombre, tags y portada originales).\nSi ya los importaste a Rekordbox, tendrás que volver a localizarlos.\n\n¿Continuar?'): return
        s.bg('Deshaciendo…', lambda: dj.cmd_undo(s.folder), lambda: s.tv.delete(*s.tv.get_children()))

    def train_marks(s):
        if not s.cfg.get('xml'): s.pick_xml()
        if not s.cfg.get('xml'): return
        if not messagebox.askyesno('Aprender START MIX', 'Lee tus pistas del rekordbox.xml que ya tienen START MIX y analiza su audio (los archivos deben estar donde dice el XML).\nLa primera vez puede tardar 20-40 minutos; después usa caché.\n\n¿Empezar?'): return
        def done():
            try: messagebox.showinfo('START MIX aprendido', open(os.path.join(dj.HERE, 'informe_marks.md'), encoding='utf-8').read())
            except Exception: pass
        s.bg('Aprendiendo START MIX…', lambda: dj.cmd_train_marks(s.cfg['xml']), done)

    def process(s): s.analyze()

    def confirm_all(s):
        if not s.folder or not s.tv.get_children(): return messagebox.showinfo('Dmzeta Workflow', 'Primero analiza una carpeta (botón "Procesar carpeta").')
        n = sum(1 for i in s.tv.get_children() if s.tv.item(i, 'text') == '☑')
        if not n: return messagebox.showinfo('Dmzeta Workflow', 'No hay filas marcadas con ☑.')
        if not s.cfg.get('xml'): s.pick_xml()
        xml = s.cfg.get('xml')
        if not messagebox.askyesno('Confirmar', f'Se aplicarán {n} filas (renombrar + limpiar tags)' + (' y se generarán los cues.' if xml else ' (sin cues: falta elegir rekordbox.xml).') + '\nNo lo hagas con pistas que ya estén en Rekordbox.\n\n¿Continuar?'): return
        s.save_review(); s.persist()
        def job():
            dj.cmd_apply(s.folder, s.backup_on)
            if xml: dj.cmd_cues(xml, s.folder)
        def done():
            s.tv.delete(*s.tv.get_children()); s.marks = dj.load_marks(s.folder)
            if xml: messagebox.showinfo('Listo', 'Nombres, tags y cues listos.\n\nEn Rekordbox:\n1. Preferencias > Avanzado > Base de datos > Biblioteca importada: elige djflow_cues.xml de la carpeta.\n2. Panel rekordbox xml > djflow: arrastra las pistas a tu colección.')
        s.bg('Aplicando y generando cues…', job, done)

    def pick_xml(s):
        f = filedialog.askopenfilename(title='rekordbox.xml', filetypes=[('XML', '*.xml')])
        if f: s.cfg['xml'] = f; save_cfg(s.cfg); s.refresh()

    def cues(s):
        if not s.folder: return messagebox.showinfo('Dmzeta Workflow', 'Primero elige la carpeta de canciones nuevas (paso 2).')
        if not s.cfg.get('xml'): s.pick_xml()
        if not s.cfg.get('xml'): return
        s.bg('Generando cues…', lambda: dj.cmd_cues(s.cfg['xml'], s.folder), lambda: messagebox.showinfo('Cues listos', 'Creado djflow_cues.xml en la carpeta. Impórtalo en Rekordbox (visor de rekordbox xml).'))

if __name__ == '__main__': App().mainloop()
