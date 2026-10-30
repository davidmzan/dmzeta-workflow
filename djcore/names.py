"""Gramática de nombres de archivo y limpieza de títulos y artistas."""
import os, re

# ───────────────────────── nombres ─────────────────────────
def parse_name(fname):
    """Extrae las etiquetas de un nombre ya estandarizado."""
    s = os.path.splitext(os.path.basename(fname))[0]
    key = bpm = None
    m = re.search(r'\s*-\s*(\d{1,2}[AB])\s*-\s*(\d+)\s*$', s)
    if m: key, bpm = m.group(1), float(m.group(2)); s = s[:m.start()]
    out = dict(mashup='(Mashup)' in s, open_show='(Open Show)' in s, bars=None, type=None, aca_starter='(Aca Starter)' in s,
               after=None, short_edit='(Short Edit)' in s, aca_out='(Aca Out)' in s, key=key, bpm=bpm)
    mb = re.search(r'\((\d+) Bars (POE|MOE|FME)\)', s)
    if mb: out['bars'], out['type'] = int(mb.group(1)), mb.group(2)
    ma = re.search(r'\((In Aca|In Hype)\)', s)
    if ma: out['after'] = ma.group(1)
    base = re.sub(r'\s*\((?:Mashup|Open Show|\d+ Bars (?:POE|MOE|FME)|Aca Starter|In Aca|In Hype|Short Edit|Aca Out)\)', '', s).strip()
    out['base'] = base
    return out

def build_name(base, key, bpm, mashup=False, bars=None, typ=None, aca_starter=False, after=None, short_edit=False, aca_out=False, open_show=False):
    p = base
    if mashup: p += ' (Mashup)'
    if open_show: p += ' (Open Show)'
    if aca_starter: p += ' (Aca Starter)'
    elif bars and typ: p += f' ({bars} Bars {typ})'
    if after: p += f' ({after})'
    if short_edit: p += ' (Short Edit)'
    if aca_out: p += ' (Aca Out)'
    return f'{p} - {key} - {int(round(bpm))}'

def ext_cue_slot(fname):
    """Hot cue donde acaba el extender y que lleva el color rojo/lima: '1' (B) si son 4 compases, '2' (C) en cualquier otro caso."""
    return '1' if parse_name(fname)['bars'] == 4 else '2'

_TAG_OR_TAIL = re.compile(r'\s*\((?:Mashup|Open Show|\d+ Bars (?:POE|MOE|FME)|Aca Starter|In Aca|In Hype|Short Edit|Aca Out)\)|\s*-\s*\d{1,2}[AB]\s*-\s*\d+\s*$')

def with_suffix(final, n):
    """Añade ' (n)' al título sin romper la gramática: 'Agua (8 Bars POE) - 5A - 133' -> 'Agua (2) (8 Bars POE) - 5A - 133'."""
    m = _TAG_OR_TAIL.search(final)
    return final[:m.start()] + f' ({n})' + final[m.start():] if m else f'{final} ({n})'

def guess_from_name(fname):
    """Último recurso: tono tipo (10A) y BPM tipo 74Bpm sacados del nombre del archivo."""
    b = os.path.basename(fname); key = bpm = None
    m = re.search(r'(?:^\(|\[|\s-\s)(\d{1,2}[AB])(?:\)|\]|\.|\s|$)', b)
    if m: key = m.group(1)
    m = re.search(r'(\d{2,3})\s*bpm', b, re.I) or re.search(r'\[(\d{2,3})\]', b) or re.search(r'\s(\d{2,3})(?:\s\d{2,3})?\.\w{3,4}$', b)
    if m: bpm = float(m.group(1))
    return bpm, key

def normalize_artist(a):
    """'Ozuna Ft Romeo Santos', 'A x B', 'A & B', 'A y B' -> 'Ozuna, Romeo Santos'."""
    parts = re.split(r'\s*(?:,|;|/|&|\+|\bfeat\.?|\bfeaturing\b|\bft\.?|\bwith\b|\s[xX]\s|\sY\s|\sy\s)\s*', a or '', flags=re.I)
    out = []
    for p in parts:
        p = re.sub(r'\s+', ' ', p).strip(' -_.')
        if p and p.lower() not in [o.lower() for o in out]: out.append(p)
    return ', '.join(out)

JUNK_SEG = re.compile(r'djtools|bpm|^\s*(cumbia|reggaeton|dembow|salsa|bachata|merengue|urbano|latino|pop|edm)\s*$|intro|outro|acapella|break|extended|clean|dirty|^\s*(6\d|[7-9]\d|1\d\d|200)\s*$|^\s*\d{1,2}[AB]\s*$|^\s*dj\s', re.I)

def _norm(t): return re.sub(r'[^a-z0-9 ]', '', t.lower()).strip()

def clean_title_pool(fname, artist_tag='', want_artist=False):
    """De un nombre de pool ('(10A) Artista - Canción (Extended Latino).mp3') deja solo el título."""
    s = os.path.splitext(os.path.basename(fname))[0]
    s = re.sub(r'^\s*\(\d{1,2}[AB]\)\s*', '', s); s = re.sub(r'^\s*\d{1,3}\.\s+', '', s)
    s = re.sub(r'\s*[-\s]\s*\d{1,2}[AB]\s*$', '', s)                     # tono al final
    remix = bool(re.search(r'\(\s*Remix\s*\)', s, re.I))
    s = re.sub(r'\([^)]*\)|\[[^\]]*\]', ' ', s)                          # fuera paréntesis y corchetes
    s = re.sub(r'\s+(6\d|[7-9]\d|1\d\d|200)(\s+\d{2,3})?\s*(bpm)?\s*$', '', s, flags=re.I)  # bpm suelto al final
    segs = [x.strip() for x in re.split(r'\s+-\s+', s) if x.strip()]
    def trim(x):
        m = re.search(r'\s+(acapella|intro|outro|hype|extended|bpm)\b', x, re.I)
        return x[:m.start()].strip() if m and m.start() > 2 else x
    segs = [trim(x) for x in segs]
    segs = [x for x in segs if not JUNK_SEG.search(x)] or segs
    at = {_norm(a) for a in re.split(r',|\bft\.?\b|\bfeat\.?\b|\bx\b|\by\b|&', artist_tag, flags=re.I) if a.strip()}
    def is_artist(x):
        parts = [_norm(a) for a in re.split(r',|\bft\.?\b|\bfeat\.?\b|&', x, flags=re.I) if a.strip()]
        if at and parts and sum(p in at or any(p in a or a in p for a in at if a) for p in parts) >= max(1, len(parts) // 2 + (len(parts) % 2)): return True
        return not at and (',' in x or re.search(r'\b(ft|feat)\b\.?', x, re.I) is not None)
    cand = [x for x in segs if not is_artist(x)]
    t = (cand[0] if len(cand) == len(segs) == 1 else (cand[0] if cand else segs[-1])) if len(segs) > 1 or cand else segs[0]
    if len(segs) == 2 and len(cand) == 2: t = segs[1]                        # 'Artista - Título' por defecto
    t = re.sub(r'\s+', ' ', t).strip(' -_')
    if t.isupper() and len(t) > 3: t = t.title()
    if remix and not re.search(r'remix', t, re.I): t += ' Remix'
    if want_artist:
        art = next((x for x in segs if x != re.sub(r'\s+', ' ', t).strip() and not JUNK_SEG.search(x) and x.lower() != t.lower()), '')
        return t, normalize_artist(art)
    return t

def _tn(t): return re.sub(r'[^a-z0-9]', '', (t or '').lower())
