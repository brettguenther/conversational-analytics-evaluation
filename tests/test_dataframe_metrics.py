
import unittest
import pandas as pd
from evals.metrics.dataframe_metrics import DataFrameMatch

class TestDataFrameMatch(unittest.TestCase):

    def setUp(self):
        """Set up the test cases"""
        self.metric = DataFrameMatch()
        self.df1 = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
        self.df2 = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
        self.df3 = pd.DataFrame({'b': [4, 5, 6], 'a': [1, 2, 3]})
        self.df4 = pd.DataFrame({'a': [3, 1, 2], 'b': [6, 4, 5]})

    def test_identical_dataframes(self):
        """Test that identical dataframes score 1.0"""
        score = self.metric.measure(self.df1, self.df2)
        self.assertEqual(score, 1.0)

    def test_reordered_columns(self):
        """Test that dataframes with reordered columns score 1.0"""
        score = self.metric.measure(self.df1, self.df3)
        self.assertEqual(score, 1.0)

    def test_reordered_rows(self):
        """Test that dataframes with reordered rows score 1.0"""
        score = self.metric.measure(self.df1, self.df4)
        self.assertEqual(score, 1.0)

    def test_with_only_measures(self):
        """Test dataframe matching with only measures specified in fields."""
        expected_df = pd.DataFrame({
            'measure1': [10, 20, 30],
            'measure2': [100, 200, 300]
        })
        generated_df = pd.DataFrame({
            'measure1': [10, 20, 30],
            'measure2': [100, 200, 300]
        })
        fields = {'measures': ['measure1', 'measure2']}
        
        # column_score = 1.0 (all columns match)
        # data_score = 2 matching rows / 3 total rows = 0.666...
        # final_score = (0.3 * 1.0) + (0.7 * 0.666...) = 0.3 + 0.4666... = 0.7666...
        expected_score = (0.3 * 1.0) + (0.7 * 1.0)
        
        score = self.metric.measure(generated_df, expected_df, fields=fields)
        self.assertAlmostEqual(score, expected_score, places=5)

    def test_with_only_dimensions(self):
        """Test dataframe matching with only dimensions specified in fields."""
        expected_df = pd.DataFrame({
            'dim1': ['A', 'B', 'C'],
            'dim2': ['X', 'Y', 'Z'],
        })
        generated_df = pd.DataFrame({
            'dim1': ['A', 'B', 'C'],
            'dim2': ['X', 'Y', 'Z'],
        })
        fields = {'dimensions': ['dim1', 'dim2']}

        # column_score = 1.0
        # data_score = 2 matching rows / 3 total rows = 0.666...
        # final_score = (0.3 * 1.0) + (0.7 * 0.666...) = 0.7666...
        expected_score = (0.3 * 1.0) + (0.7 * 1.0)

        score = self.metric.measure(generated_df, expected_df, fields=fields)
        self.assertAlmostEqual(score, expected_score, places=5)

    def test_with_mixed_fields(self):
        """Test dataframe matching with a mix of dimensions and measures."""
        expected_df = pd.DataFrame({
            'dim1': ['A', 'B', 'C'],
            'measure1': [10, 20, 30]
        })
        generated_df = pd.DataFrame({
            'dim1': ['A', 'B', 'C'],
            'measure1': [10, 20, 30]
        })
        fields = {'dimensions': ['dim1'], 'measures': ['measure1']}

        # Dimensions take precedence for join_cols.
        # column_score = 1.0
        # data_score = 2 matching rows on 'dim1' / 3 total rows = 0.666...
        # final_score = (0.3 * 1.0) + (0.7 * 0.666...) = 0.7666...
        expected_score = (0.3 * 1.0) + (0.7 * (1.0))

        score = self.metric.measure(generated_df, expected_df, fields=fields)
        self.assertAlmostEqual(score, expected_score, places=5)

if __name__ == '__main__':
    unittest.main()
