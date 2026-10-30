"""Interfaz dividida en css/ y js/: referencias, sintaxis, servidor de estáticos y arranque en modo demo (sin navegador)."""
import http.client, os, re, shutil, subprocess, threading, unittest
from http.server import ThreadingHTTPServer
from _common import ROOT
import workflow_server as ws

UI = os.path.join(ROOT, 'ui')
INDEX = open(os.path.join(UI, 'index.html'), encoding='utf-8').read()
JS = re.findall(r'<script src="/ui/(js/[^"]+)"', INDEX)
CSS = re.findall(r'<link rel="stylesheet" href="/ui/(css/[^"]+)"', INDEX)


class StructureTest(unittest.TestCase):
    def test_index_references_exist_and_nothing_is_orphaned(self):
        self.assertTrue(JS and CSS)
        for f in JS + CSS: self.assertTrue(os.path.isfile(os.path.join(UI, f)), f + ' no existe')
        on_disk = {f'{d}/{x}' for d in ('js', 'css') for x in os.listdir(os.path.join(UI, d)) if x.endswith(('.js', '.css'))}
        self.assertEqual(sorted(on_disk - set(JS + CSS)), [], 'archivos en ui/ que index.html no carga')
        self.assertIn('__WF_TOKEN__', INDEX)

    def test_each_script_is_strict_and_parses(self):
        if not shutil.which('node'): self.skipTest('sin node')
        for f in JS:
            src = open(os.path.join(UI, f), encoding='utf-8').read(); self.assertTrue(src.startswith("'use strict';"), f)
            r = subprocess.run(['node', '--check', os.path.join(UI, f)], capture_output=True, text=True); self.assertEqual(r.returncode, 0, f + ': ' + r.stderr)

    def test_bpm_scale_buttons_wired(self):
        src = open(os.path.join(UI, 'js', '40-inspector.js'), encoding='utf-8').read()
        for k in ('id="fBpmH"', 'id="fBpmD"', "$('#fBpmH').onclick", "$('#fBpmD').onclick", 'scaleBpm(0.5)', 'scaleBpm(2)'): self.assertIn(k, src)

    def test_4bar_colour_slot_and_sticky_drawer_header(self):
        deck = open(os.path.join(UI, 'js', '50-deck.js'), encoding='utf-8').read()
        for k in ("r.p.bars===4?'B':'C'", "xs==='B'?cColor()", "xs==='C'?cColor()", "'COLOR '+L"): self.assertIn(k, deck)
        css = open(os.path.join(UI, 'css', '05-overlays.css'), encoding='utf-8').read()
        self.assertRegex(css, r'\.drawer h3\{[^}]*position:sticky')

    def test_no_inline_script_left_in_index(self):
        self.assertIsNone(re.search(r'<script>(?!\s*</script>)', INDEX)); self.assertNotIn('<style>', INDEX)

    def test_demo_boot_runs_without_errors(self):
        if not shutil.which('node'): self.skipTest('sin node')
        r = subprocess.run(['node', os.path.join(ROOT, 'tests', 'ui_smoke.js'), UI], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn('OK', r.stdout)


class StaticServingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), ws.H); cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls): cls.srv.shutdown(); cls.srv.server_close()

    def get(self, path, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10); c.request('GET', path, headers=headers or {}); r = c.getresponse(); b = r.read(); h = dict(r.getheaders()); c.close(); return r.status, h, b

    def test_every_referenced_file_is_served(self):
        for f in JS + CSS:
            st, h, b = self.get('/ui/' + f); self.assertEqual(st, 200, f)
            self.assertIn('javascript' if f.endswith('.js') else 'css', h['Content-Type']); self.assertEqual(b, open(os.path.join(UI, f), 'rb').read())

    def test_static_route_is_locked_down(self):
        for p in ('/ui/../workflow_server.py', '/ui/js/../../djflow.py', '/ui/index.html', '/ui/js/', '/ui/js/nope.js', '/ui/css/x.py', '/ui/%2e%2e/djflow.py', '/ui/js/%2e%2e/%2e%2e/djflow.py', '/ui//etc/passwd'):
            self.assertEqual(self.get(p)[0], 404, p)
        self.assertEqual(self.get('/ui/js/00-core.js', {'Host': 'evil.example'})[0], 403)

    def test_index_served_with_token_and_scripts(self):
        st, h, b = self.get('/'); self.assertEqual(st, 200); html = b.decode()
        self.assertIn(ws.TOKEN, html); self.assertNotIn('__WF_TOKEN__', html); self.assertIn('/ui/js/00-core.js', html)
        self.assertIn("script-src 'self'", h['Content-Security-Policy'])


if __name__ == '__main__': unittest.main(verbosity=2)
