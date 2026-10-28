"""Pruebas de regresión de Dmzeta Workflow.  Ejecuta:  python3 -m unittest discover -s tests -v
No tocan tus datos: todo (cachés, modelos, marcas) va a una carpeta temporal. Necesitan ffmpeg (el mismo que usa la app)."""
import json, os, re, shutil, subprocess, sys, unittest
import xml.etree.ElementTree as ET
import numpy as np
from _common import dj, TMP, ROOT, make_track, have_ffmpeg, tiny_xml


class NamesTest(unittest.TestCase):
    def test_roundtrip(self):
        cases = [dict(base='Agua', key='5A', bpm=133, bars=8, typ='POE'),
                 dict(base='Bebe', key='11A', bpm=85, bars=8, typ='MOE', aca_out=True),
                 dict(base='Coqueta', key='12B', bpm=90, bars=8, typ='MOE', after='In Aca'),
                 dict(base='A x B', key='1A', bpm=128, mashup=True, bars=4, typ='FME'),
                 dict(base='Escapate', key='1A', bpm=92, aca_starter=True),
                 dict(base='Otro', key='7A', bpm=94, open_show=True, short_edit=True),
                 dict(base='Hookah', key='2A', bpm=105, mashup=True, bars=8, typ='FME', after='In Hype', aca_out=True)]
        for c in cases:
            name = dj.build_name(**c); p = dj.parse_name(name + '.mp3')
            self.assertEqual(p['base'], c['base'], name); self.assertEqual(p['key'], c['key'], name); self.assertEqual(p['bpm'], c['bpm'], name)
            self.assertEqual(bool(p['aca_out']), bool(c.get('aca_out')), name); self.assertEqual(bool(p['mashup']), bool(c.get('mashup')), name)
            again = dj.build_name(p['base'], p['key'], p['bpm'], p['mashup'], p['bars'], p['type'], p['aca_starter'], p['after'], p['short_edit'], p['aca_out'], p['open_show'])
            self.assertEqual(again, name)

    def test_plain_name_has_no_tags(self):
        p = dj.parse_name('Titulo suelto.mp3'); self.assertIsNone(p['key']); self.assertIsNone(p['bars'])


class DoneTest(unittest.TestCase):
    def test_done_registry(self):
        f = os.path.join(TMP, 'x.wav'); open(f, 'wb').write(b'1234')
        self.assertFalse(dj.is_done(f)); dj.mark_done([f]); self.assertTrue(dj.is_done(f))
        open(f, 'ab').write(b'5'); self.assertFalse(dj.is_done(f))          # si el archivo cambia, vuelve a analizarse


@unittest.skipUnless(have_ffmpeg(), 'falta ffmpeg')
class GridTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = os.path.join(TMP, 'audio'); os.makedirs(cls.dir, exist_ok=True)

    def check(self, bpm, first, tol=0.025):
        f = os.path.join(self.dir, f'k_{int(bpm)}_{int(first * 1000)}.wav'); make_track(f, bpm, first)
        t0, b, _ = dj.detect_grid(f, bpm, raw=True)
        self.assertLess(abs(b - bpm), bpm * 0.012, f'BPM detectado {b}')
        beat = 60.0 / bpm; d = (t0 - first + beat / 2) % beat - beat / 2        # el grid puede caer en cualquier beat; lo importante es la fase
        self.assertLess(abs(d), tol, f'bpm {bpm} primer golpe {first}: grid {t0:.3f} (desvío {d * 1000:+.0f} ms)')

    def test_phase_various(self):
        for bpm, first in ((100, 0.20), (116, 0.037), (124, 0.37), (128, 1.0), (90, 0.5)): self.check(bpm, first)

    def test_fresh_bypasses_cache(self):
        f = os.path.join(self.dir, 'fresh.wav'); make_track(f, 120, 0.3)
        a = dj.detect_grid(f, 120.0, raw=True); self.assertEqual(a, dj.detect_grid(f, 120.0, raw=True, fresh=True))

    def test_mp3_delay_zero_for_wav(self):
        f = os.path.join(self.dir, 'fresh.wav'); make_track(f, 120, 0.3); self.assertEqual(dj.mp3_delay(f), 0.0)

    def test_mp3_delay_in_range(self):
        f = os.path.join(self.dir, 'e.wav'); make_track(f, 120, 0.3); m = os.path.join(self.dir, 'e.mp3')
        r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f, '-codec:a', 'libmp3lame', '-b:a', '192k', m])
        if r.returncode: self.skipTest('ffmpeg sin libmp3lame')
        d = dj.mp3_delay(m); self.assertTrue(0.0 <= d < 0.08, d)


@unittest.skipUnless(have_ffmpeg(), 'falta ffmpeg')
class CuesXmlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = os.path.join(TMP, 'folder'); os.makedirs(cls.folder, exist_ok=True)
        cls.name = 'Cancion Test (8 Bars MOE) (Aca Out) - 8A - 120.wav'
        make_track(os.path.join(cls.folder, cls.name), 120, 0.25, seconds=90)
        cls.xml = os.path.join(TMP, 'rb.xml'); tiny_xml(cls.xml)
        json.dump({cls.name: dict(start=24, end=32, loop=[40, 8], genre='Afro House', cat='Peak Time', stars=4, t0=0.25, bpm=120.0, ccol=[230, 40, 40],
                                  mname=dict(A='INTRO'))}, open(os.path.join(cls.folder, 'djflow_marks.json'), 'w'))
        dj.cmd_cues(cls.xml, cls.folder)
        cls.root = ET.parse(os.path.join(cls.folder, 'djflow_cues.xml')).getroot()
        cls.t = cls.root.find('COLLECTION').findall('TRACK')[0]

    def test_fields(self):
        t = self.t
        self.assertEqual(t.get('Genre'), 'Afro House'); self.assertEqual(t.get('Grouping'), 'Peak Time'); self.assertEqual(t.get('Colour'), '0x00FF00')
        self.assertEqual(t.get('Rating'), '204')
        self.assertEqual(t.get('Comments'), 'MOE · Aca Out')                  # sustituye al comentario de Mixed In Key
        self.assertEqual(t.get('AverageBpm'), '120.00')

    def test_hot_cues_positions_and_colours(self):
        pm = {(p.get('Num'), p.get('Type')): p for p in self.t.findall('POSITION_MARK')}
        a, b, c = pm[('0', '0')], pm[('1', '0')], pm[('2', '0')]
        self.assertAlmostEqual(float(a.get('Start')), 0.25, places=2)
        self.assertAlmostEqual(float(b.get('Start')) - float(a.get('Start')), 8.0, places=2)      # +4 compases a 120 bpm
        self.assertEqual((c.get('Red'), c.get('Green'), c.get('Blue')), ('230', '40', '40'))     # color del C elegido por ti
        self.assertNotIn(('6', '0'), pm)                                                         # el hot G queda libre

    def test_memory_cues_and_loop(self):
        mem = [p for p in self.t.findall('POSITION_MARK') if p.get('Num') == '-1']
        names = [m.get('Name') for m in mem]
        for n in ('INTRO', 'START MIX 8', 'END MIX', 'END LOOP'): self.assertIn(n, names)
        loop = [p for p in mem if p.get('Name') == 'END LOOP'][0]
        self.assertEqual(loop.get('Type'), '4'); self.assertGreater(float(loop.get('End')), float(loop.get('Start')))

    def test_golden_snapshot(self):
        """Foto completa de los cues exportados: si cambia algo (posición, color, nombre, tipo), la prueba avisa. Para aceptar un cambio a propósito: UPDATE_GOLDEN=1."""
        snap = dict(track={k: self.t.get(k) for k in ('Name', 'Genre', 'Grouping', 'Colour', 'Rating', 'Comments', 'AverageBpm', 'Tonality')},
                    marks=sorted([[p.get('Num'), p.get('Type'), p.get('Name'), p.get('Start'), p.get('End'), p.get('Red'), p.get('Green'), p.get('Blue')] for p in self.t.findall('POSITION_MARK')], key=lambda m: (int(m[0]), m[1], m[3])),
                    tempo=[dict(x.attrib) for x in self.t.findall('TEMPO')])
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'golden', 'cues.json'); os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.environ.get('UPDATE_GOLDEN') or not os.path.exists(path): json.dump(snap, open(path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
        self.assertEqual(snap, json.load(open(path, encoding='utf-8')))

    def test_offset_only_mp3(self):
        dj.cmd_cues(self.xml, self.folder, offset_ms=40)
        t = ET.parse(os.path.join(self.folder, 'djflow_cues.xml')).getroot().find('COLLECTION').findall('TRACK')[0]
        a = [p for p in t.findall('POSITION_MARK') if p.get('Num') == '0'][0]
        self.assertAlmostEqual(float(a.get('Start')), 0.25, places=2)          # WAV: no se compensa
        dj.cmd_cues(self.xml, self.folder)


class ModelTest(unittest.TestCase):
    def test_softmax_roundtrip(self):
        rs = np.random.RandomState(0); y = np.array(['a', 'b', 'c'] * 30); X = rs.randn(90, 4); X[:, 0] += (y == 'b') * 3
        m = dj.Softmax(['a', 'b', 'c']).fit(X, y); st = {}; m.dump('t', st); m2 = dj.Softmax.load('t', st)
        self.assertTrue(np.allclose(m.proba(X), m2.proba(X))); self.assertGreater(np.mean(np.array(m.classes)[m.proba(X).argmax(1)] == y), 0.5)

    def test_cvox_needs_samples_and_gate(self):
        os.makedirs(dj.LEARN_CVOX_DIR, exist_ok=True)
        dj.train_cvox(); self.assertFalse(os.path.exists(dj.CVOX_MODEL))      # con pocas pistas no se entrena
        rs = np.random.RandomState(0)
        for i in range(30):
            y = i % 2; A = rs.rand(60, dj.NF).astype('f'); A[8:12, 3] += 2.0 * y
            np.savez_compressed(os.path.join(dj.LEARN_CVOX_DIR, f'{i}.npz'), A=A, N=8, y=y)
        dj.train_cvox(); self.assertTrue(os.path.exists(dj.CVOX_MODEL)); self.assertIsNotNone(dj.load_cvox())
        z = dict(np.load(dj.CVOX_MODEL)); z['cvox__off'] = np.array([1]); np.savez(dj.CVOX_MODEL, **z)
        self.assertIsNone(dj.load_cvox())                                       # el interruptor apaga el modelo

    def test_cvox_feature_is_single_value(self):
        self.assertEqual(dj.cvox_x(np.random.rand(60, dj.NF).astype('f'), 8).shape, (1,))


class FilesTest(unittest.TestCase):
    def test_ui_script_syntax(self):
        if not shutil.which('node'): self.skipTest('sin node')
        s = open(os.path.join(ROOT, 'workflow_ui.html'), encoding='utf-8').read(); js = re.search(r'<script>([\s\S]*)</script>', s).group(1)
        p = os.path.join(TMP, 'ui.js'); open(p, 'w').write(js)
        r = subprocess.run(['node', '--check', p], capture_output=True, text=True); self.assertEqual(r.returncode, 0, r.stderr)

    def test_server_compiles(self):
        import py_compile; py_compile.compile(os.path.join(ROOT, 'workflow_server.py'), doraise=True)


if __name__ == '__main__': unittest.main(verbosity=2)
