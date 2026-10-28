"""Aprendizaje: lo corregido pesa más que lo aceptado, lo no revisado no se aprende, y cada reentrenamiento queda anotado."""
import json, os, shutil, unittest
import numpy as np
from _common import dj, TMP, make_track, have_ffmpeg
import djcore.training as training


class WeightTest(unittest.TestCase):
    def test_weights_by_origin(self):
        self.assertEqual(dj.learn_weight(True, False), dj.W_CORRECTED)
        self.assertEqual(dj.learn_weight(False, True), dj.W_ACCEPTED)
        self.assertEqual(dj.learn_weight(False, False), 0.0)               # sin revisar: no se aprende
        self.assertEqual(dj.learn_weight(True, True), dj.W_CORRECTED)      # corregir manda sobre aceptar
        self.assertGreater(dj.W_CORRECTED, dj.W_ACCEPTED * 3)


@unittest.skipUnless(have_ffmpeg(), 'falta ffmpeg')
class RememberTest(unittest.TestCase):
    def test_what_gets_learned(self):
        folder = os.path.join(TMP, 'learnfolder'); os.makedirs(folder, exist_ok=True)
        names = [f'Aprende {k} (8 Bars MOE) - 8A - 120.wav' for k in 'ABCD']
        for n in names: make_track(os.path.join(folder, n), 120, 0.25, seconds=60)
        marks = {names[0]: dict(genre='Dembow', genre_edit=True, cat='Peak Time', cat_edit=True, stars=4, ok=True, ccol=[230, 40, 40], t0=0.25, bpm=120.0),      # corregido por ti
                 names[1]: dict(genre='Reggaeton', cat='Warm Up', stars=3, stars_auto=True, ok=True, t0=0.25, bpm=120.0),                                          # propuesta que aceptas con ✓
                 names[2]: dict(genre='Trap', cat='Build Up', stars=2, stars_auto=True, t0=0.25, bpm=120.0),                                                       # propuesta sin revisar
                 names[3]: dict(t0=0.25, bpm=120.0)}
        dj.atomic_write_json(os.path.join(folder, dj.MARKS_FILE), marks)
        shutil.rmtree(dj.LEARN_META_DIR, ignore_errors=True); shutil.rmtree(dj.LEARN_CVOX_DIR, ignore_errors=True)
        dj.remember_marks(folder, set(names))
        meta = {}
        for fn in os.listdir(dj.LEARN_META_DIR):
            z = np.load(os.path.join(dj.LEARN_META_DIR, fn)); meta[str(z['genre'])] = (float(z['gw']), float(z['cw']), float(z['sw']))
        self.assertEqual(meta['Dembow'], (dj.W_CORRECTED, dj.W_CORRECTED, dj.W_CORRECTED))        # editado por ti: peso alto
        self.assertEqual(meta['Reggaeton'], (dj.W_ACCEPTED, dj.W_ACCEPTED, dj.W_ACCEPTED))        # solo ✓: peso bajo
        self.assertNotIn('Trap', meta)                                                           # sin revisar: no se aprende
        self.assertEqual(len(meta), 2)
        ws = sorted(float(np.load(os.path.join(dj.LEARN_CVOX_DIR, f))['w']) for f in os.listdir(dj.LEARN_CVOX_DIR))
        self.assertIn(dj.W_CORRECTED, ws); self.assertTrue(all(w in (dj.W_ACCEPTED, dj.W_CORRECTED) for w in ws))     # el color corregido por ti pesa más que el aceptado


class RegistryTest(unittest.TestCase):
    def test_cvox_training_is_logged_and_weighted(self):
        shutil.rmtree(dj.LEARN_CVOX_DIR, ignore_errors=True); os.makedirs(dj.LEARN_CVOX_DIR)
        rs = np.random.RandomState(3)
        for i in range(30):
            y = i % 2; A = rs.rand(60, dj.NF).astype('f'); A[8:12, 3] += 2.0 * y
            np.savez_compressed(os.path.join(dj.LEARN_CVOX_DIR, f'{i}.npz'), A=A, N=8, y=y, w=dj.W_CORRECTED if i % 3 == 0 else dj.W_ACCEPTED)
        before = len(dj.load_model_log()); dj.train_cvox()
        log = dj.load_model_log(); self.assertEqual(len(log), before + 1)
        e = log[-1]; self.assertEqual(e['model'], 'cvox'); self.assertEqual(e['n'], 30); self.assertEqual(e['n_user'], 10)
        for k in ('when', 'accuracy', 'baseline', 'enabled'): self.assertIn(k, e)

    def test_genre_training_uses_user_examples_and_logs(self):
        rs = np.random.RandomState(0); gen = ['Reggaeton', 'House', 'Trap']; cats = ['00FF00', 'FFA500', 'FFFF00', '660099']; rows = []
        for i in range(400):
            rows.append(f'<TRACK TrackID="{i}" Genre="{gen[i % 3]}" AverageBpm="{90 + 10 * (i % 3)}" Colour="0x{cats[(i % 3 + i % 2) % 4]}" Rating="{51 * (1 + i % 5)}" Location="file://localhost{TMP}/x.mp3"></TRACK>')
        open(os.path.join(TMP, 'g.xml'), 'w').write('<DJ_PLAYLISTS><COLLECTION>' + ''.join(rows) + '</COLLECTION></DJ_PLAYLISTS>')
        open(os.path.join(TMP, 'x.mp3'), 'wb').write(b'x')
        orig = training.struct_matrix; training.struct_matrix = lambda p, b, t0, nbars=100: (rs.rand(100, dj.NF).astype('f') + (b - 100) / 50, None)
        shutil.rmtree(dj.LEARN_META_DIR, ignore_errors=True); os.makedirs(dj.LEARN_META_DIR)
        for j in range(5): np.savez_compressed(os.path.join(dj.LEARN_META_DIR, f'{j}.npz'), x=np.zeros(59, dtype='f'), genre='Afro', cat='Samples', stars='5', gw=dj.W_CORRECTED, cw=dj.W_CORRECTED, sw=0.0)
        try:
            dj.train_genre(os.path.join(TMP, 'g.xml'), min_n=5)
        finally: training.struct_matrix = orig
        log = {e['model']: e for e in dj.load_model_log()[-4:]}
        self.assertEqual(log['genre']['n_user'], 5); self.assertEqual(log['genre']['n'], 405)
        self.assertIn('Afro', list(np.load(dj.GENRE_MODEL)['genre__cl']))                      # la clase que solo viene de tus correcciones existe
        self.assertNotIn('star', log) if 'star' not in log else self.assertEqual(log['star']['n_user'], 0)   # sw=0: tus estrellas sin revisar no entran


if __name__ == '__main__': unittest.main(verbosity=2)
