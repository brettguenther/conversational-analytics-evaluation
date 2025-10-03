"""Metrics for comparing dataframes."""

from abc import ABC, abstractmethod
import pandas as pd
import datacompy

class DataFrameMetric(ABC):
    """Abstract base class for a dataframe evaluation metric."""

    @abstractmethod
    def measure(
        self,
        generated_df: pd.DataFrame,
        expected_df: pd.DataFrame,
    ) -> float:
        """Measures the quality of the generated dataframe.

        Args:
            generated_df: The DataFrame resulting from the generated SQL.
            expected_df: The DataFrame resulting from the expected SQL.

        Returns:
            A score between 0.0 and 1.0, where 1.0 is a exact match.
        """
        pass


class DataFrameMatch(DataFrameMetric):
    """Measures the similarity between two dataframes, allowing for partial matches."""

    def measure(
        self, generated_df: pd.DataFrame, expected_df: pd.DataFrame, **kwargs
    ) -> float:
        """Compares two DataFrames, scoring based on column and data similarity."""
        if generated_df is None or expected_df is None:
            return 0.0
        
        if generated_df.empty and expected_df.empty:
            return None

        try:
            pd.testing.assert_frame_equal(
                generated_df, expected_df, check_dtype=False
            )
            column_score = 1.0
            data_score = 1.0
        except AssertionError:
            # 1. Column Similarity Score (Weight: 0.3)
            gen_cols = set(generated_df.columns)
            exp_cols = set(expected_df.columns)
            intersection = len(gen_cols.intersection(exp_cols))
            union = len(gen_cols.union(exp_cols))
            column_score = (intersection / union) if union > 0 else 0.0

            common_cols = list(gen_cols.intersection(exp_cols))
            if not common_cols:
                return 0.0 # No common columns, so no basis for data comparison

            # 2. Data Similarity Score on Common Columns (Weight: 0.7)
            gen_subset_df = generated_df[common_cols]
            exp_subset_df = expected_df[common_cols]
            compare = datacompy.Compare(
                gen_subset_df,
                exp_subset_df,
                join_columns=common_cols,
                abs_tol=0.01,
                ignore_spaces=True,
                ignore_case=True,
                df1_name="Generated",
                df2_name="Expected",
            )
            num_matching_rows = compare.intersect_rows.shape[0]
            total_rows = max(len(gen_subset_df), len(exp_subset_df))
            data_score = num_matching_rows / total_rows if total_rows > 0 else 0.0

        # 3. Combine Scores
        final_score = (0.3 * column_score) + (0.7 * data_score)
        return final_score

def score_dataframes(
    generated_df: pd.DataFrame,
    expected_df: pd.DataFrame,
    metrics: list[DataFrameMetric],
) -> dict[str, float]:
    """Scores a dataframe response using a list of metrics.

    Args:
        generated_df: The DataFrame from the Looker Query result.
        expected_df: The DataFrame from the expected result.
        metrics: A list of DataFrameMetric objects to use for scoring.

    Returns:
        A dictionary of metric names to scores.
    """
    scores = {}
    for metric in metrics:
        metric_name = metric.__class__.__name__
        scores[metric_name] = metric.measure(
            generated_df=generated_df,
            expected_df=expected_df,
        )
    return scores