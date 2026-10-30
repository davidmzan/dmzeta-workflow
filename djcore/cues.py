"""Reglas de cues aprendidas y exportación del XML de Rekordbox."""
import os, re, subprocess
import numpy as np
from .config import CAT_HEX, EXT, LIME_C, RED_C
from .storage import _pref, atomic_write_text, load_marks
from .names import ext_cue_slot, parse_name
from .audio import ffprobe_tags, track_bpm_key
from .grid import detect_grid, mp3_delay
from .models import load_cvox
from .prediction import cue_c_color

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
        marks = []
        st = mk.get('start'); en = mk.get('end'); hot_o = mk.get('hot') or {}; ma = mk.get('memAuto') or {}
        if mk.get('noIntro'): ma = dict(ma, intro=False)
        if st is not None and en is None and not mk.get('noEnd'): en = st + X['end']
        # hot cues: A..H = 0..7, SIN nombre (como en tu colección). El G (6) queda libre salvo que lo pongas tú a mano.
        C4 = X['col']['4']; cD = X['col'].get('3') or rules['1'][1]; c6 = X['col'].get('6') or C4
        vA = hot_o.get('A'); baseA = float(vA) if isinstance(vA, (int, float)) and not isinstance(vA, bool) else rules['0'][0]      # B y C siguen al A si lo mueves
        hot = {'0': rules['0'][0], '1': baseA + (rules['1'][0] - rules['0'][0]), '2': baseA + (rules['2'][0] - rules['0'][0]), '3': None, '4': st, '5': (st + X['off5']) if st is not None else None, '6': None}
        hcol = {'0': rules['0'][1], '1': rules['1'][1], '2': rules['2'][1], '3': cD, '4': C4, '5': X['col']['5'], '6': c6}
        xs = ext_cue_slot(f); xl = 'B' if xs == '1' else 'C'         # el color rojo/lima va en el cue donde acaba el extender: B si son 4 compases, C en el resto
        cm = mk.get('ccol')
        if isinstance(cm, (list, tuple)) and len(cm) == 3: hcol[xs] = tuple(int(v) for v in cm); print(f'    cue {xl}: color elegido por ti {tuple(cm)}')
        else:
            cc = cue_c_color(path, bpm, t0, f, cvm)
            if cc: hcol[xs] = RED_C if cc == 'red' else LIME_C; print(f'    cue {xl}: {"rojo (voz antes del final del extender)" if cc == "red" else "verde lima (sin voz en el extender)"}')
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
    out = os.path.join(folder, 'djflow_cues.xml'); atomic_write_text(out, '\n'.join(xml))
    print(f'\n{len(tracks)} pistas con cues en {out}' + (f'\nSin BPM (pasa antes Mixed In Key): {len(skipped)}' if skipped else ''))
    nm = sum(1 for f in files if (allmarks.get(f) or {}).get('start') is not None)
    print(f'Con START/END MIX y hot cue 5: {nm} pistas.' + ('' if nm == len(tracks) else ' El resto: ponlas a mano (START MIX, END MIX, hot cues 4 y 5, loop final).'))
