"""Aprendizaje: lo corregido pesa más que lo aceptado, lo no revisado no se aprende, y cada reentrenamiento queda anotado."""
import os, shutil, unittest
import numpy as np
from _common import dj, TMP, make_track, have_ffmpeg


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

    def _meta(self, n, genres=('Reggaeton', 'House', 'Trap'), sw=0.0):
        shutil.rmtree(dj.LEARN_META_DIR, ignore_errors=True); os.makedirs(dj.LEARN_META_DIR); rs = np.random.RandomState(1)
        for j in range(n):
            g = genres[j % len(genres)]; x = rs.rand(59).astype('f') * .2; x[(j % len(genres)) * 5] += 1.0           # el género deja una huella clara en las características
            np.savez_compressed(os.path.join(dj.LEARN_META_DIR, f'{j}.npz'), x=x, genre=g, cat='Peak Time' if j % 2 else 'Warm Up', stars='5', gw=dj.W_CORRECTED, cw=dj.W_CORRECTED, sw=sw)

    def test_genre_training_uses_only_user_examples(self):
        """Aprende solo de tus ejemplos: no lee el XML (ni siquiera existe), registra el resultado y no usa estrellas sin revisar."""
        if os.path.exists(dj.GENRE_MODEL): os.remove(dj.GENRE_MODEL)
        self._meta(60); dj.train_genre(os.path.join(TMP, 'no_existe.xml'))
        log = {e['model']: e for e in dj.load_model_log()[-4:]}
        self.assertEqual((log['genre']['n'], log['genre']['n_user']), (60, 60)); self.assertTrue(log['genre']['enabled'])
        self.assertEqual(sorted(np.load(dj.GENRE_MODEL)['genre__cl']), ['House', 'Reggaeton', 'Trap'])
        self.assertNotIn('star', log)                                                              # sw=0: tus estrellas sin revisar no entran

    def test_genre_needs_enough_own_examples(self):
        if os.path.exists(dj.GENRE_MODEL): os.remove(dj.GENRE_MODEL)
        self._meta(30); dj.train_genre(); self.assertFalse(os.path.exists(dj.GENRE_MODEL))          # menos de 40 pistas tuyas: no se entrena
        self._meta(60, genres=('Solo',)); dj.train_genre(); self.assertFalse(os.path.exists(dj.GENRE_MODEL))   # un único género: tampoco

    def test_start_mix_trains_from_own_marks_only(self):
        os.makedirs(dj.LEARN_MARKS_DIR, exist_ok=True); [os.remove(os.path.join(dj.LEARN_MARKS_DIR, f)) for f in os.listdir(dj.LEARN_MARKS_DIR)]
        rs = np.random.RandomState(2)
        for i in range(45): np.savez_compressed(os.path.join(dj.LEARN_MARKS_DIR, f'{i}.npz'), A=rs.rand(120, dj.NF).astype('f'), target=24 + 4 * (i % 8), weight=dj.W_CORRECTED, N=8)
        if os.path.exists(dj.MARKS_MODEL): os.remove(dj.MARKS_MODEL)
        dj.cmd_train_marks(os.path.join(TMP, 'no_existe.xml')); self.assertTrue(os.path.exists(dj.MARKS_MODEL))
        e = [x for x in dj.load_model_log() if x['model'] == 'start_mix'][-1]; self.assertEqual((e['n'], e['n_user']), (45, 45))     # ni una pista del XML


if __name__ == '__main__': unittest.main(verbosity=2)
