"""Metrics for comparing dataframes."""

from abc import ABC, abstractmethod
import pandas as pd
import datacompy
import logging

logger = logging.getLogger(__name__)

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
        self, generated_df: pd.DataFrame, expected_df: pd.DataFrame, fields: dict[str, list[str]] = None, **kwargs
    ) -> float:
        """Compares two DataFrames, scoring based on column and data similarity."""
        if generated_df is None or expected_df is None:
            return 0.0
        
        if generated_df.empty and expected_df.empty:
            return 1.0
        
        # To allow for row-order differences, sort the dataframes before comparison.
        try:
            if not generated_df.empty:
                generated_df = generated_df.sort_values(by=list(generated_df.columns)).reset_index(drop=True)
            if not expected_df.empty:
                expected_df = expected_df.sort_values(by=list(expected_df.columns)).reset_index(drop=True)
        except Exception as e:
            logger.warning(f"Could not sort dataframes for comparison, proceeding with original order. Error: {e}")

        logger.debug(f"generated dataframe: {generated_df.to_string()}")
        logger.debug(f"expected dataframe: {expected_df.to_string()}")

        try:
            pd.testing.assert_frame_equal(
                generated_df, expected_df, check_dtype=False, rtol=1e-2
            )
            return 1.0
        except AssertionError as e:
            logger.debug(f"DataFrame match failed with error: {e}")
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

            join_cols = common_cols
            if fields and fields.get("dimensions"):
                dims_in_common = list(set(fields.get("dimensions")) & set(common_cols))
                if dims_in_common:
                    join_cols = dims_in_common

            compare = datacompy.Compare(
                gen_subset_df,
                exp_subset_df,
                join_columns=join_cols,
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
    fields: dict[str, list[str]] = None,
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
            fields=fields,
        )
    return scores
