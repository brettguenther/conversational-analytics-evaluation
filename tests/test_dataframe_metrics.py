
import unittest
import pandas as pd
from evals.metrics.dataframe_metrics import (
    DataFrameMatch,
    DataFrameValueEquivalence,
    compare_query_results,
    map_columns_by_name_and_value,
)


class TestDataFrameMatch(unittest.TestCase):

    def setUp(self):
        """Set up the test cases"""
        self.metric = DataFrameMatch()
        self.eq_metric = DataFrameValueEquivalence()
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
        expected_score = (0.3 * 1.0) + (0.7 * (1.0))

        score = self.metric.measure(generated_df, expected_df, fields=fields)
        self.assertAlmostEqual(score, expected_score, places=5)

    def test_renamed_columns_matched_by_value(self):
        """Test that renamed/aliased columns with identical values score 1.0."""
        expected_df = pd.DataFrame({
            'station_name': ['E 17 St', '8 Ave', 'W 21 St'],
            'trip_count': [291615, 291577, 275348],
        })
        generated_df = pd.DataFrame({
            'trips.start_station_name': ['8 Ave', 'E 17 St', 'W 21 St'],
            'trips.count': [291577, 291615, 275348],
        })

        col_map = map_columns_by_name_and_value(expected_df, generated_df)
        self.assertEqual(
            col_map,
            {
                'trips.start_station_name': 'station_name',
                'trips.count': 'trip_count',
            },
        )
        self.assertEqual(self.metric.measure(generated_df, expected_df), 1.0)
        self.assertEqual(self.eq_metric.measure(generated_df, expected_df), 1.0)

    def test_numeric_string_coercion_and_float_tolerance(self):
        """Test that numeric strings and float rounding differences match via value mapping."""
        expected_df = pd.DataFrame({
            'category': ['Apparel', 'Footwear'],
            'total_sales': [100.50, 250.75],
        })
        generated_df = pd.DataFrame({
            'sales.category': ['Footwear', 'Apparel'],
            'sales.total_revenue': ['250.750001', '100.500000'],
        })

        comp = compare_query_results(expected_df, generated_df)
        self.assertTrue(comp.is_equivalent)
        self.assertEqual(self.metric.measure(generated_df, expected_df), 1.0)

    def test_extra_columns_in_generated_dataframe(self):
        """Test that extra generated columns are ignored by equivalence and partially scored by DataFrameMatch."""
        expected_df = pd.DataFrame({
            'station': ['A', 'B'],
            'trips': [10, 20],
        })
        generated_df = pd.DataFrame({
            'trips.station': ['A', 'B'],
            'trips.count': [10, 20],
            'trips.extra_col': ['X', 'Y'],
        })

        self.assertEqual(self.eq_metric.measure(generated_df, expected_df), 1.0)
        match_score = self.metric.measure(generated_df, expected_df)
        # 2 of 3 columns match (column_score = 2/3) and all rows match (data_score = 1.0)
        self.assertAlmostEqual(match_score, (0.3 * (2 / 3)) + (0.7 * 1.0), places=5)


if __name__ == '__main__':
    unittest.main()
