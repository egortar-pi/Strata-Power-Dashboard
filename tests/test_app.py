import unittest
from unittest.mock import patch
import app


class MetricsTests(unittest.TestCase):
    def test_strata_cumulative_paths(self):
        metrics = {'totals': {'prompt_tokens': 3783762, 'output_tokens': 46902, 'reused': 3675157}}
        self.assertEqual(app.find_tokens(metrics, [app.DEFAULT['input_path']])[0], 3783762)
        self.assertEqual(app.find_tokens(metrics, [app.DEFAULT['output_path']])[0], 46902)
        self.assertEqual(app.find_tokens(metrics, ['totals.reused'])[0], 3675157)

    def test_gpu_csv_multiple_cards(self):
        text = ('0, GPU-one, RTX A, 115.5, 80, 4000, 24000\n'
                '1, GPU-two, RTX B, 210.0, 95, 18000, 24000\n'
                '2, GPU-three, RTX C, 42.0, 1, 500, 12000\n')
        class Result:
            stdout = text
        with patch.object(app.subprocess, 'run', return_value=Result()):
            rows = app.gpu_read()
        self.assertEqual(len(rows), 3)
        self.assertEqual([x['uuid'] for x in rows], ['GPU-one', 'GPU-two', 'GPU-three'])
        self.assertAlmostEqual(sum(x['watts'] for x in rows), 367.5)

    def test_default_currency(self):
        self.assertEqual(app.DEFAULT["currency"], "EUR")

    def test_api_equivalent_and_electricity_same_units(self):
        inputs, outputs, kwh = 1_000_000, 100_000, 10
        input_price, output_price, rate = 2, 8, 0.25
        self.assertAlmostEqual((inputs*input_price + outputs*output_price)/1e6 - kwh*rate, 0.3)

    def test_bad_metric_is_not_a_number(self):
        self.assertIsNone(app.numeric('N/A'))
        self.assertIsNone(app.numeric('nan'))


if __name__ == '__main__':
    unittest.main()
