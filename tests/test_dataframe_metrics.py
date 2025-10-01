
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

if __name__ == '__main__':
    unittest.main()
