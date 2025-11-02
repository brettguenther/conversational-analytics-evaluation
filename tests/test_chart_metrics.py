import unittest
from evals.metrics.chart_metrics import ChartMetric

class TestChartMetric(unittest.TestCase):

    def setUp(self):
        """Set up the test cases"""
        self.metric = ChartMetric()
        self.generated_chart_perfect = {
            'mark': {'type': 'bar'},
            'encoding': {
                'x': {'field': 'sales_calendar_month'},
                'y': {'field': 'sales_total_sales'}
            }
        }
        self.expected_chart_perfect = {
            'type': 'bar',
            'x-axis': 'sales_calendar_month',
            'y-axis': 'sales_total_sales'
        }

    def test_exact_match(self):
        """Test that a exact match scores 1.0"""
        score = self.metric.evaluate(self.generated_chart_perfect, self.expected_chart_perfect)
        self.assertEqual(score, 1.0)

    def test_partial_match_mark_type(self):
        """Test that a partial match on mark type scores 0.33"""
        generated_chart = self.generated_chart_perfect.copy()
        generated_chart['encoding']['x']['field'] = 'other_field'
        generated_chart['encoding']['y']['field'] = 'another_field'
        score = self.metric.evaluate(generated_chart, self.expected_chart_perfect)
        self.assertAlmostEqual(score, 1/3)

    def test_partial_match_axes(self):
        """Test that a partial match on axes scores 0.66"""
        generated_chart = self.generated_chart_perfect.copy()
        generated_chart['mark']['type'] = 'line'
        score = self.metric.evaluate(generated_chart, self.expected_chart_perfect)
        self.assertAlmostEqual(score, 2/3)

    def test_complete_mismatch(self):
        """Test that a complete mismatch scores 0.0"""
        generated_chart = {
            'mark': {'type': 'line'},
            'encoding': {
                'x': {'field': 'other_field'},
                'y': {'field': 'another_field'}
            }
        }
        score = self.metric.evaluate(generated_chart, self.expected_chart_perfect)
        self.assertEqual(score, 0.0)

    def test_empty_inputs(self):
        """Test that empty or None inputs score 0.0"""
        score1 = self.metric.evaluate({}, {})
        score2 = self.metric.evaluate(None, None)
        score3 = self.metric.evaluate(self.generated_chart_perfect, {})
        self.assertEqual(score1, 0.0)
        self.assertEqual(score2, 0.0)
        self.assertEqual(score3, 0.0)

if __name__ == '__main__':
    unittest.main()
