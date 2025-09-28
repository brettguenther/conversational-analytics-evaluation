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
            A score between 0.0 and 1.0, where 1.0 is a perfect match.
        """
        pass


class DataFrameMatch(DataFrameMetric):
    """Measures the similarity between two dataframes using datacompy."""

    def measure(
        self, generated_df: pd.DataFrame, expected_df: pd.DataFrame, **kwargs
    ) -> float:
        """Compares two DataFrames for equality."""
        if generated_df is None or expected_df is None:
            return 0.0
        
        if generated_df.empty and expected_df.empty:
            return 1.0

        try:
            # First, try a strict equality check with pandas testing
            pd.testing.assert_frame_equal(
                generated_df, expected_df, check_dtype=False
            )
            return 1.0
        except AssertionError:
            # If the strict check fails, fall back to datacompy for a more detailed comparison.
            if set(generated_df.columns) != set(expected_df.columns):
                return 0.0

            # Rationale for parameters:
            # - join_columns: Using all columns as join keys to ensure that rows are compared based on all their values.
            # - abs_tol: A small tolerance for numeric comparisons to account for floating point inaccuracies.
            # - ignore_spaces: True to ignore whitespace differences in string comparisons.
            # - ignore_case: True to ignore case differences in string comparisons.
            compare = datacompy.Compare(
                generated_df,
                expected_df,
                join_columns=list(generated_df.columns),
                abs_tol=0.0001,
                ignore_spaces=True,
                ignore_case=True,
                df1_name="Generated",
                df2_name="Expected",
            )

            # Get the columns that are for matching
            match_cols = [col for col in compare.intersect_rows.columns if col.endswith('_match')]
            
            # Count the number of rows where all compared columns match
            num_matching_rows = compare.intersect_rows[match_cols].all(axis=1).sum()

            if num_matching_rows == len(expected_df) and len(compare.df1_unq_rows) == 0 and len(compare.df2_unq_rows) == 0:
                return 1.0
            else:
                return num_matching_rows / len(expected_df)


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