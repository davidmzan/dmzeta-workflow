"""Candidatos de START MIX, ordenar y aprobar seguras, y medición de cuánto corriges (uso)."""
import csv, json, os, unittest
import numpy as np
from _common import dj, TMP
import workflow_server as ws

UI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ui')
rd = lambda *p: open(os.path.join(UI, *p), encoding='utf-8').read()


class AltsTest(unittest.TestCase):
    def test_propose_start_returns_three_separated_candidates(self):
        import djcore.prediction as pr
        class M:                                       # modelo de juguete: prefiere el compás 40, luego 44, luego 56
            def proba(self, XX): p = np.array([{40: .9, 44: .8, 56: .6}.get(int(x[0]), .1) for x in XX]); return np.c_[1 - p, p]
        orig = (pr.struct_matrix, pr.start_X)
        pr.struct_matrix = lambda path, bpm, t0, nbars=100: (np.zeros((120, dj.NF), 'f'), 400.0)
        pr.start_X = lambda A, N: (list(range(16, 81, 4)), np.array([[k] for k in range(16, 81, 4)], 'f'))
        try: out = pr.propose_start('x', 120.0, 0.0, M())
        finally: pr.struct_matrix, pr.start_X = orig
        self.assertEqual(out['start'], 40); self.assertEqual(out['alts'], [40, 56, 16])               # 44 queda fuera: a menos de 8 compases del 40
        self.assertTrue(all(abs(a - b) >= 8 for i, a in enumerate(out['alts']) for b in out['alts'][i + 1:]))


class UsageTest(unittest.TestCase):
    def setUp(self):
        if os.path.exists(dj.USAGE_LOG): os.remove(dj.USAGE_LOG)

    def test_record_and_summary(self):
        d = os.path.join(TMP, 'usage'); os.makedirs(d, exist_ok=True)
        json.dump({'a.mp3': dict(start=40, auto=True, ok=True, genre='Reggaeton', genre_edit=False, stars=5, stars_auto=True, secs=30),
                   'b.mp3': dict(start=44, genre='Dembow', genre_edit=True, t0=0.2, ccol=[1, 2, 3], secs=90)}, open(os.path.join(d, 'djflow_marks.json'), 'w'))
        dj.record_usage(d, [('a.mp3', dict(proposed='x', orig_proposed='a', final='a')), ('b.mp3', dict(proposed='y', orig_proposed='b', final='b2'))])
        s = dj.usage_summary(); f = s['fields']
        self.assertEqual(s['tracks'], 2); self.assertEqual((f['name']['corrected'], f['name']['n']), (1, 2))              # b.mp3 cambió el nombre propuesto
        self.assertEqual((f['start_mix']['corrected'], f['start_mix']['n']), (1, 2)); self.assertEqual((f['genre']['corrected'], f['genre']['n']), (1, 2))
        self.assertEqual(f['grid']['corrected'], 1); self.assertEqual(f['stars']['n'], 1); self.assertEqual(f['stars']['corrected'], 0)
        self.assertEqual(s['median_secs'], 90.0)

    def test_review_keeps_original_proposal(self):
        d = os.path.join(TMP, 'review_keep'); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'review.csv'), 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh); w.writerow(['original', 'proposed', 'confidence', 'flags', 'final', 'artist']); w.writerow(['o.mp3', 'Propuesta - 8A - 120', 0.9, '', 'Propuesta - 8A - 120', ''])
        row = dict(original='o.mp3', final='Editada - 8A - 120', artist='', confidence=.9, flags='', checked=True, reviewed=True)
        ws.write_review(d, [row], {}); ws.write_review(d, [row], {})                                          # guardar dos veces no pierde el original
        r = list(csv.DictReader(open(os.path.join(d, 'review.csv'), newline='', encoding='utf-8-sig')))[0]
        self.assertEqual(r['orig_proposed'], 'Propuesta - 8A - 120'); self.assertEqual(r['final'], 'Editada - 8A - 120')


class UiWiringTest(unittest.TestCase):
    def test_candidates_keys_sort_bulk_and_panel(self):
        deck, keys, lst, pb = rd('js', '50-deck.js'), rd('js', '90-keys-init.js'), rd('js', '30-list.js'), rd('js', '60-playback.js')
        for k in ('function altStarts', 'function pickStart', 'function startHintHTML', "candidatos de START MIX"): self.assertIn(k, deck)
        for k in ("k==='1'||k==='2'||k==='3'", 'pickStart(+k-1)', 'function trackSecs'): self.assertIn(k, keys)
        for k in ('S.sortConf', "data-bulk=\"sort\""): self.assertIn(k, lst)
        for k in ('safeRow', "data-bulk=\"safe\"", "m==='safe'"): self.assertNotIn(k, lst)                 # no hay aprobación en bloque: se revisa todo
        self.assertIn('Cuánto corriges', pb); self.assertIn('trackSecs();', rd('js', '70-actions.js')); self.assertIn('startHintHTML()', rd('js', '40-inspector.js'))

    def test_quality_endpoint_exposes_usage(self):
        self.assertIn('usage', open(os.path.join(os.path.dirname(UI), 'workflow_server.py'), encoding='utf-8').read())


if __name__ == '__main__': unittest.main(verbosity=2)
