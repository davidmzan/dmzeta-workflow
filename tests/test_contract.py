"""Contrato entre Python y JavaScript: la gramática de nombres vive en dos sitios y no puede divergir."""
import json, os, re, shutil, subprocess, unittest
from _common import dj, ROOT, TMP

NAMES = ['Agua (8 Bars POE) - 5A - 133', 'Bebe (8 Bars MOE) (Aca Out) - 11A - 85', 'Coqueta (8 Bars MOE) (In Aca) - 12B - 90',
         'Beauty And A Beat x Danza Kuduro (Mashup) (8 Bars POE) - 8A - 130', 'Escapate Conmigo (Remix) (Aca Starter) - 1A - 92',
         'Otro Trago Remix (Halloween Open Show) (Short Edit) - 7A - 94', 'Hookah x Dile (Mashup)(8 Bars FME) - 2A - 105',
         'No Le Pare (8 Bars POE) (In Hype) - 3A - 116', 'Solo titulo', 'Titulo - 4A', 'Titulo (Open Show)(4 Bars FME)(In Aca)(Short Edit)(Aca Out) - 10B - 128']
FIELDS = ('mashup', 'open_show', 'bars', 'type', 'aca_starter', 'after', 'short_edit', 'aca_out', 'key', 'bpm', 'base')


def js_functions():
    s = open(os.path.join(ROOT, 'ui', 'js', '10-names.js'), encoding='utf-8').read()
    i = s.index('function parseName(n){'); j = s.index('const finalOf=')
    return s[i:j]


@unittest.skipUnless(shutil.which('node'), 'sin node')
class NamesParityTest(unittest.TestCase):
    def test_parse_and_build_match(self):
        prog = js_functions() + '\nconst names=' + json.dumps(NAMES) + ';\nconsole.log(JSON.stringify(names.map(n=>{const p=parseName(n+".mp3");return {p, b:(p.key&&p.bpm&&p.base)?buildName(p):""};})));'
        f = os.path.join(TMP, 'parity.js'); open(f, 'w').write(prog)
        out = subprocess.run(['node', f], capture_output=True, text=True); self.assertEqual(out.returncode, 0, out.stderr)
        for n, r in zip(NAMES, json.loads(out.stdout)):
            py = dj.parse_name(n + '.mp3'); js = r['p']
            for k in FIELDS: self.assertEqual(py.get(k), js.get(k), f'{n!r}: campo {k}')
            if py['key'] and py['bpm'] and py['base']:
                self.assertEqual(r['b'], dj.build_name(py['base'], py['key'], py['bpm'], py['mashup'], py['bars'], py['type'], py['aca_starter'], py['after'], py['short_edit'], py['aca_out'], py['open_show']), n)


class AtomicWriteTest(unittest.TestCase):
    def test_atomic_json_and_failure_keeps_old(self):
        p = os.path.join(TMP, 'a.json'); dj.atomic_write_json(p, {'a': 1}); self.assertEqual(json.load(open(p)), {'a': 1})
        class Boom:
            def __repr__(s): raise RuntimeError
        with self.assertRaises(Exception): dj.atomic_write_json(p, {'a': Boom()})
        self.assertEqual(json.load(open(p)), {'a': 1})                    # el archivo anterior queda intacto
        self.assertEqual([x for x in os.listdir(TMP) if x.startswith('a.json.tmp')], [])

    def test_atomic_savez_roundtrip(self):
        import numpy as np
        p = os.path.join(TMP, 'm.npz'); dj.atomic_savez(p, x=np.arange(5)); self.assertEqual(list(np.load(p)['x']), [0, 1, 2, 3, 4])


class ReleaseFilesTest(unittest.TestCase):
    def test_no_personal_data_tracked(self):
        if not shutil.which('git') or not os.path.isdir(os.path.join(ROOT, '.git')): self.skipTest('sin repositorio')
        files = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True).stdout.split()
        bad = [f for f in files if re.search(r'\.(mp3|wav|m4a|flac|aif+|npz|prev)$|rekordbox\.xml$|config\.json$|done\.json$|prefs\.json$|djflow_marks\.json$|models_log\.json$|bpm_fixes\.json$|usage_log\.json$', f)]
        self.assertEqual(bad, [], 'datos personales o generados dentro de git')
        for f in files:
            if f.endswith(('.py', '.html', '.md', '.command')) and not f.startswith('tests/'):
                txt = open(os.path.join(ROOT, f), encoding='utf-8', errors='ignore').read()
                self.assertNotIn('/Users/dmzeta', txt, f); self.assertNotIn('@gmail.com', txt, f)


class FacadeTest(unittest.TestCase):
    def test_everything_used_by_server_and_app_exists(self):
        """workflow_server.py y djflow_app.py llaman a dj.<nombre>: todos deben seguir existiendo en la fachada al mover código."""
        used = set()
        for f in ('workflow_server.py', 'djflow_app.py'):
            used |= set(re.findall(r'\bdj\.(\w+)', open(os.path.join(ROOT, f), encoding='utf-8').read()))
        missing = sorted(n for n in used if not hasattr(dj, n)); self.assertEqual(missing, [])

    def test_layers_only_import_lower_layers(self):
        order = ['config', 'storage', 'names', 'audio', 'grid', 'preview', 'features', 'models', 'prediction', 'training', 'cues', 'commands']
        for i, m in enumerate(order):
            src = open(os.path.join(ROOT, 'djcore', m + '.py'), encoding='utf-8').read()
            for imp in re.findall(r'^from \.(\w+) import', src, re.M):
                self.assertLess(order.index(imp), i, f'{m} importa de {imp}, que es una capa posterior (ciclo)')
