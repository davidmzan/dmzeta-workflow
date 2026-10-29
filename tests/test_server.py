"""Pruebas del servidor local: seguridad (token, origen, carpetas, rutas) y flujo de trabajo de punta a punta."""
import http.client, json, os, threading, time, unittest, urllib.parse
from http.server import ThreadingHTTPServer
from _common import dj, TMP, make_track, have_ffmpeg, tiny_xml
import workflow_server as ws


class ServerBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), ws.H); cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.folder = os.path.join(TMP, 'srvfolder'); os.makedirs(cls.folder, exist_ok=True); ws.ALLOWED.add(os.path.normpath(cls.folder))
        cls.audio = 'Prueba Servidor (8 Bars MOE) (Aca Out) - 8A - 120.wav'
        if have_ffmpeg(): make_track(os.path.join(cls.folder, cls.audio), 120, 0.25, seconds=30)

    @classmethod
    def tearDownClass(cls): cls.srv.shutdown(); cls.srv.server_close()

    def req(self, method, path, body=None, headers=None, token=True, host=None):
        h = {'Host': host or f'127.0.0.1:{self.port}'}
        if token: h['X-WF-Token'] = ws.TOKEN
        if body is not None: h['Content-Type'] = 'application/json'
        h.update(headers or {})
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=20)
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in h.items(): c.putheader(k, v)
        data = json.dumps(body).encode() if body is not None else None
        if data is not None: c.putheader('Content-Length', str(len(data)))
        c.endheaders(data); r = c.getresponse(); raw = r.read(); c.close(); return r.status, dict(r.getheaders()), raw

    def js(self, *a, **k):
        st, _, raw = self.req(*a, **k)
        try: return st, json.loads(raw)
        except ValueError: return st, None


class SecurityTest(ServerBase):
    def test_index_has_token_and_headers(self):
        st, h, raw = self.req('GET', '/', token=False); self.assertEqual(st, 200)
        self.assertIn(ws.TOKEN.encode(), raw); self.assertNotIn(b'__WF_TOKEN__', raw)
        self.assertIn("default-src 'none'", h['Content-Security-Policy']); self.assertEqual(h['X-Content-Type-Options'], 'nosniff'); self.assertEqual(h['X-Frame-Options'], 'DENY')

    def test_api_needs_token(self):
        self.assertEqual(self.req('GET', '/api/state', token=False)[0], 401)
        self.assertEqual(self.req('POST', '/api/cfg', {}, token=False)[0], 401)
        self.assertEqual(self.req('GET', '/api/state', headers={'X-WF-Token': 'otro'}, token=False)[0], 401)
        self.assertEqual(self.req('GET', '/api/state')[0], 200)

    def test_cross_site_requests_blocked(self):
        self.assertEqual(self.req('POST', '/api/cfg', {}, headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.req('GET', '/api/state', headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertEqual(self.req('GET', '/api/state', host='evil.example')[0], 403)                 # DNS rebinding
        self.assertEqual(self.req('POST', '/api/cfg', {}, headers={'Origin': f'http://127.0.0.1:{self.port}'})[0], 200)

    def test_post_requires_json_content_type(self):
        st, _, _ = self.req('POST', '/api/cfg', {}, headers={'Content-Type': 'text/plain'}); self.assertEqual(st, 415)

    def test_unlisted_folder_is_refused(self):
        other = os.path.join(TMP, 'otra'); os.makedirs(other, exist_ok=True)
        self.assertEqual(self.js('GET', '/api/review?folder=' + urllib.parse.quote(other))[0], 403)
        self.assertEqual(self.js('GET', '/api/folder?folder=' + urllib.parse.quote(other))[0], 403)
        self.assertEqual(self.js('POST', '/api/apply', {'folder': other, 'rows': []})[0], 403)
        self.assertEqual(self.js('POST', '/api/review', {'folder': '/', 'rows': []})[0], 403)
        self.assertEqual(self.js('GET', '/api/folder?folder=' + urllib.parse.quote(self.folder))[0], 200)

    def test_audio_path_traversal(self):
        for name in ('../x.wav', '/etc/passwd', 'a/b.wav', '..', '', 'nope.wav', self.audio + '\x00'):
            self.assertIn(self.req('GET', '/audio?folder=' + urllib.parse.quote(self.folder) + '&name=' + urllib.parse.quote(name))[0], (400, 404), name)
        self.assertEqual(self.req('GET', '/audio?folder=/&name=etc')[0], 404)

    def test_audio_ranges(self):
        if not have_ffmpeg(): self.skipTest('sin ffmpeg')
        u = '/audio?folder=' + urllib.parse.quote(self.folder) + '&name=' + urllib.parse.quote(self.audio)
        st, h, raw = self.req('GET', u, headers={'Range': 'bytes=0-99'}); self.assertEqual((st, len(raw)), (206, 100))
        self.assertEqual(self.req('GET', u, headers={'Range': 'bytes=abc-'})[0], 416)
        self.assertEqual(self.req('GET', u, headers={'Range': 'bytes=999999999-'})[0], 416)
        self.assertEqual(self.req('GET', u)[0], 200)

    def test_cfg_is_validated(self):
        st, d = self.js('POST', '/api/cfg', {'export_offset_ms': 99999, 'xml': 'malo.txt', 'auto_n': 'x', 'inventada': 1, 'backup': 0})
        self.assertEqual(st, 200); c = d['cfg']
        self.assertEqual(c['export_offset_ms'], 200.0); self.assertNotEqual(c['xml'], 'malo.txt'); self.assertNotIn('inventada', c); self.assertIs(c['backup'], False)
        self.js('POST', '/api/cfg', {'export_offset_ms': 0, 'backup': True})

    def test_quality_endpoint(self):
        dj.log_model('prueba', n=10, n_user=2, accuracy=0.5, baseline=0.4, enabled=True)
        st, d = self.js('GET', '/api/quality'); self.assertEqual(st, 200)
        self.assertIn('prueba', [e['model'] for e in d['latest']]); self.assertEqual(self.req('GET', '/api/quality', token=False)[0], 401)

    def test_oversized_body_rejected(self):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        c.putrequest('POST', '/api/cfg', skip_host=True); c.putheader('Host', f'127.0.0.1:{self.port}'); c.putheader('X-WF-Token', ws.TOKEN)
        c.putheader('Content-Type', 'application/json'); c.putheader('Content-Length', str(ws.MAX_BODY + 1)); c.endheaders()
        r = c.getresponse(); self.assertNotEqual(r.status, 200); c.close()


@unittest.skipUnless(have_ffmpeg(), 'falta ffmpeg')
class WorkflowTest(ServerBase):
    def test_cues_job_end_to_end(self):
        xml = os.path.join(TMP, 'srv_rb.xml'); tiny_xml(xml)
        self.assertEqual(self.js('POST', '/api/cfg', {'xml': xml})[0], 200)
        st, d = self.js('POST', '/api/cues', {'folder': self.folder}); self.assertEqual(st, 200)
        for _ in range(120):
            st, j = self.js('GET', '/api/job?id=' + d['job'])
            if j['status'] != 'running': break
            time.sleep(0.25)
        self.assertEqual(j['status'], 'done', j.get('error')); self.assertTrue(os.path.exists(os.path.join(self.folder, 'djflow_cues.xml')))

    def test_watchdog_decision(self):
        """El servidor solo se cierra si la ventana lleva > idle sin pings y no hay trabajo ni diálogo abierto (causa del 'Failed to fetch' al elegir otra carpeta)."""
        sc = ws.should_close
        self.assertFalse(sc(1000, 0, False, 90))                    # aún no hubo ningún ping
        self.assertFalse(sc(1000, 950, False, 90))                  # 50 s: pestaña en segundo plano, sigue vivo
        self.assertFalse(sc(1000, 100, True, 90))                   # trabajo o diálogo en curso
        self.assertTrue(sc(1000, 100, False, 90))                   # ventana cerrada de verdad
        self.assertGreaterEqual(ws.IDLE_DEFAULT, 300)

    def test_pick_keeps_server_alive(self):
        orig = ws.subprocess.run; seen = []
        def fake(*a, **k): seen.append(ws.PICKING[0]); return type('R', (), dict(returncode=0, stdout='/tmp/x/\n'))()
        ws.subprocess.run = fake; plat = ws.sys.platform; ws.sys.platform = 'darwin'
        try: path = ws.pick('folder')
        finally: ws.subprocess.run = orig; ws.sys.platform = plat
        self.assertEqual(path, '/tmp/x'); self.assertEqual(seen, [1]); self.assertEqual(ws.PICKING[0], 0)

    def test_bpm_fix_log(self):
        """Contador de correcciones de BPM: cuenta ×2 / ×0.5, una pista cuenta una vez, y rechaza basura."""
        if os.path.exists(dj.BPM_FIX_LOG): os.remove(dj.BPM_FIX_LOG)
        self.assertEqual(dj.bpm_factor(82, 164), 2.0); self.assertEqual(dj.bpm_factor(170, 85), 0.5); self.assertIsNone(dj.bpm_factor(120, 128)); self.assertIsNone(dj.bpm_factor('x', 1))
        self.assertTrue(self.js('POST', '/api/bpmfix', {'name': 'a.mp3', 'detected': 82, 'corrected': 164})[1]['ok'])
        self.assertTrue(self.js('POST', '/api/bpmfix', {'name': 'a.mp3', 'detected': 82, 'corrected': 164})[1]['ok'])       # misma pista: no se duplica
        self.assertTrue(self.js('POST', '/api/bpmfix', {'name': '../../b.mp3', 'detected': 120, 'corrected': 125})[1]['ok'])
        for bad in ({'name': 'c.mp3', 'detected': -5, 'corrected': 100}, {'name': 'c.mp3', 'detected': 'x', 'corrected': 100}, {'name': 5, 'detected': 80, 'corrected': 160}, {'name': 'c.mp3', 'detected': True, 'corrected': 100}, {'name': 'c.mp3', 'detected': 80, 'corrected': 9999}):
            self.assertFalse(self.js('POST', '/api/bpmfix', bad)[1]['ok'], bad)
        sm = self.js('GET', '/api/quality')[1]['bpm_fixes']; self.assertEqual((sm['total'], sm['double_half']), (2, 1))
        self.assertEqual([e['name'] for e in sm['last']], ['a.mp3', 'b.mp3'])                                                 # el nombre se reduce a basename
        self.assertEqual(self.js('POST', '/api/bpmfix', {'name': 'a.mp3', 'detected': 1, 'corrected': 2}, token=False)[0], 401)

    def test_track_endpoint(self):
        st, d = self.js('GET', '/api/track?folder=' + urllib.parse.quote(self.folder) + '&name=' + urllib.parse.quote(self.audio) + '&bpm=120')
        self.assertEqual(st, 200); self.assertAlmostEqual(d['bpm'], 120, delta=2); self.assertGreaterEqual(d['t0'], 0)

    def test_old_jobs_are_pruned(self):
        for i in range(ws.MAX_JOBS + 10): ws.run_job('x', lambda: None)
        time.sleep(0.5); ws.run_job('y', lambda: None)
        self.assertLessEqual(len(ws.JOBS), ws.MAX_JOBS + 12)


if __name__ == '__main__': unittest.main(verbosity=2)
