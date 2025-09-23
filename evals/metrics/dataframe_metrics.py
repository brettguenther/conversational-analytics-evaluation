"""Metrics for comparing dataframes."""

from abc import ABC, abstractmethod
import pandas as pd

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
    """Measures the similarity between two dataframes."""

    def measure(
        self, generated_df: pd.DataFrame, expected_df: pd.DataFrame, **kwargs
    ) -> float:
        """Compares two DataFrames for equality."""
        if generated_df is None or expected_df is None:
            return 0.0
        # This is a simple check. More sophisticated checks can be added,
        # e.g., ignoring column order or row order.
        try:
            pd.testing.assert_frame_equal(
                generated_df, expected_df, check_dtype=False
            )
            return 1.0
        except AssertionError:
            return 0.0

def score_dataframes(
    generated_df: pd.DataFrame,
    expected_df: pd.DataFrame,
    metrics: list[DataFrameMetric],
) -> dict[str, float]:
    """Scores a dataframe response using a list of metrics.

    Args:
        generated_df: The DataFrame from the generated SQL.
        expected_df: The DataFrame from the expected SQL.
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
