import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'experiments'))
from tune_ipopt import assess, candidates

class QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.data = {'ipopt_warm_' + k: [v, v] for k, v in {
            'cost': 5, 'eq_residual': 1e-6, 'ineq_violation': 0,
            'time_ms': 2, 'iterations': 20, 'success': 1, 'hit_max_iter': 0}.items()}
    def test_feasible_converged(self):
        self.assertTrue(assess(self.data, 'ipopt_warm', 1e-4)['eligible'])
    def test_reject_bad_rows(self):
        for key, value in [('cost', float('nan')), ('eq_residual', .1),
                           ('ineq_violation', float('inf')), ('success', 0),
                           ('hit_max_iter', 1), ('time_ms', -1)]:
            with self.subTest(key=key):
                data = copy.deepcopy(self.data)
                data['ipopt_warm_' + key][0] = value
                self.assertFalse(assess(data, 'ipopt_warm', 1e-4)['eligible'])
    def test_no_rows(self):
        with self.assertRaises(ValueError):
            assess({k: [] for k in self.data}, 'ipopt_warm', 1e-4)
    def test_ispd_unchanged(self):
        base = {'ipopt_settings': {'options': {'tol': .001}}, 'ispd_settings': {'tau': 1.6}}
        before = copy.deepcopy(base)
        runs = list(candidates(base))
        self.assertEqual(len(runs), 9)
        self.assertEqual(base, before)
        for _, cfg in runs:
            self.assertEqual(cfg['ispd_settings'], before['ispd_settings'])

if __name__ == '__main__':
    unittest.main()
