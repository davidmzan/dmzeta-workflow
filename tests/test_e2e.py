"""Flujo completo sobre audio sintético: analizar → revisar → aplicar (renombrar) → cues → deshacer."""
import csv, os, subprocess, unittest
from _common import dj, TMP, make_track, have_ffmpeg, tiny_xml


@unittest.skipUnless(have_ffmpeg(), 'falta ffmpeg')
class EndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = os.path.join(TMP, 'e2e'); os.makedirs(cls.folder, exist_ok=True)
        cls.names = ['Cancion Uno', 'Cancion Dos']
        for i, n in enumerate(cls.names):
            w = os.path.join(cls.folder, n + '.wav'); make_track(w, 100 + 10 * i, 0.3, seconds=40)
            m = os.path.join(cls.folder, n + '.mp3')
            r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', w, '-codec:a', 'libmp3lame', '-b:a', '160k', '-metadata', 'title=' + n, '-metadata', 'artist=Artista Test', '-metadata', 'initial_key=8A', m])
            if r.returncode: raise unittest.SkipTest('ffmpeg sin libmp3lame')
            os.remove(w)

    def test_full_flow(self):
        dj.cmd_analyze(self.folder)
        review = os.path.join(self.folder, 'review.csv'); self.assertTrue(os.path.exists(review))
        rows = list(csv.DictReader(open(review, newline='', encoding='utf-8-sig')))
        self.assertEqual(sorted(r['original'] for r in rows), sorted(n + '.mp3' for n in self.names))
        # revisión manual: damos un nombre final estándar a la primera pista y dejamos la segunda sin marcar
        first = rows[0]['original']
        final = 'Cancion Revisada (8 Bars MOE) - 8A - 100'
        with open(review, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh); w.writerow(['original', 'proposed', 'confidence', 'flags', 'final', 'artist', 'reviewed', 'edit_final', 'checked'])
            for r in rows: w.writerow([r['original'], final, '1', '', final if r['original'] == first else '', 'Artista Test', '1', final, '1' if r['original'] == first else '0'])
        dj.cmd_apply(self.folder, True)
        files = os.listdir(self.folder); self.assertIn(final + '.mp3', files)
        self.assertEqual(sum(f.endswith('.mp3') for f in files), 2)                     # solo se renombró la marcada
        self.assertNotIn(first, files)                                                  # el original ya no está con su nombre viejo
        self.assertIn([r['original'] for r in rows if r['original'] != first][0], files)  # la no marcada sigue como estaba
        xml = os.path.join(TMP, 'e2e_rb.xml'); tiny_xml(xml)
        dj.cmd_cues(xml, self.folder, only={final + '.mp3'})
        self.assertTrue(os.path.exists(os.path.join(self.folder, 'djflow_cues.xml')))
        self.assertTrue(dj.get_last_applied() and (final + '.mp3') in dj.get_last_applied())
        dj.cmd_undo(self.folder)
        self.assertEqual(sorted(f for f in os.listdir(self.folder) if f.endswith('.mp3')), sorted(n + '.mp3' for n in self.names))      # vuelve al estado original


if __name__ == '__main__': unittest.main(verbosity=2)
