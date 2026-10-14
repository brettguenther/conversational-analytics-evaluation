"""Metrics for comparing dataframes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging
import datacompy
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ComparisonResult:
    """Result of comparing two query result DataFrames."""

    is_equivalent: bool
    error: str | None = None
    column_map: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def success_result(
        is_equivalent: bool, column_map: dict[str, str] | None = None
    ) -> "ComparisonResult":
        return ComparisonResult(
            is_equivalent=is_equivalent,
            column_map=column_map or {},
        )

    @staticmethod
    def error_result(
        error: str, column_map: dict[str, str] | None = None
    ) -> "ComparisonResult":
        return ComparisonResult(
            is_equivalent=False,
            error=error,
            column_map=column_map or {},
        )


def _is_coercible_numeric(series: pd.Series) -> bool:
    """Returns True if a Series is numeric or an object Series of numeric strings."""
    if pd.api.types.is_numeric_dtype(series.dtype):
        return True
    if series.dtype == object and not series.empty:
        try:
            pd.to_numeric(series, errors="raise")
            return True
        except (ValueError, TypeError):
            return False
    return False


def map_columns_by_name_and_value(
    expected_df: pd.DataFrame,
    generated_df: pd.DataFrame,
    atol: float = 1e-5,
    rtol: float = 1e-5,
) -> dict[str, str]:
    """Maps generated_df column names to expected_df column names.

    Pass 1 maps columns by exact name match.
    Pass 2 maps remaining unmapped expected columns to unmapped generated columns
    by comparing sorted column values (with numeric coercion and float tolerance).

    Returns:
        A dict mapping {generated_column_name: expected_column_name}.
    """
    if expected_df is None or generated_df is None:
        return {}

    alphabetical_exp_columns = sorted(expected_df.columns)
    gen_to_exp_map: dict[str, str] = {}

    # Pass 1: Exact column name match
    for exp_col in alphabetical_exp_columns:
        if exp_col in generated_df.columns:
            gen_to_exp_map[exp_col] = exp_col
            logger.debug(f"  MAPPED by name: {exp_col!r} -> {exp_col!r}")

    # Pass 2: Value-based matching for unmapped columns (requires equal row counts)
    if len(expected_df) != len(generated_df) or expected_df.empty:
        return gen_to_exp_map

    for exp_col in alphabetical_exp_columns:
        if exp_col in gen_to_exp_map.values():
            continue

        exp_col_type = expected_df[exp_col].dtype
        if exp_col_type == object:
            exp_col_vals = (
                expected_df[exp_col]
                .astype(str)
                .sort_values()
                .reset_index(drop=True)
            )
        else:
            exp_col_vals = (
                expected_df[exp_col].sort_values().reset_index(drop=True)
            )
        is_exp_numeric = _is_coercible_numeric(expected_df[exp_col])

        for gen_col in generated_df.columns:
            if gen_col in gen_to_exp_map:
                continue

            gen_col_type = generated_df[gen_col].dtype
            if gen_col_type == object:
                gen_col_vals = (
                    generated_df[gen_col]
                    .astype(str)
                    .sort_values()
                    .reset_index(drop=True)
                )
            else:
                gen_col_vals = (
                    generated_df[gen_col].sort_values().reset_index(drop=True)
                )
            is_gen_numeric = _is_coercible_numeric(generated_df[gen_col])

            types_compatible = (gen_col_type == exp_col_type) or (
                is_exp_numeric and is_gen_numeric
            )
            if not types_compatible:
                continue

            match = exp_col_vals.equals(gen_col_vals)
            if not match and is_exp_numeric and is_gen_numeric:
                try:
                    pd.testing.assert_series_equal(
                        pd.to_numeric(exp_col_vals, errors="raise")
                        .astype(float)
                        .sort_values()
                        .reset_index(drop=True),
                        pd.to_numeric(gen_col_vals, errors="raise")
                        .astype(float)
                        .sort_values()
                        .reset_index(drop=True),
                        check_dtype=False,
                        check_names=False,
                        atol=atol,
                        rtol=rtol,
                    )
                    match = True
                except (AssertionError, ValueError, TypeError):
                    match = False

            if match:
                gen_to_exp_map[gen_col] = exp_col
                logger.debug(f"  MATCHED by value: {gen_col!r} -> {exp_col!r}")
                break

    return gen_to_exp_map


def compare_query_results(
    expected_df: pd.DataFrame,
    generated_df: pd.DataFrame,
    atol: float = 1e-5,
    rtol: float = 1e-5,
) -> ComparisonResult:
    """Compares expected (golden) results with generated query results.

    Matches columns by exact name first, then by column values if names differ,
    normalizes types, and checks for data equivalence.
    """
    if expected_df is None or generated_df is None:
        return ComparisonResult.error_result("One or both DataFrames are None.")

    if expected_df.empty and generated_df.empty:
        return ComparisonResult.success_result(True)

    if len(expected_df) != len(generated_df):
        return ComparisonResult.error_result(
            f"Row count mismatch: expected {len(expected_df)}, got {len(generated_df)}."
        )

    try:
        alphabetical_exp_columns = sorted(expected_df.columns)
        col_map = map_columns_by_name_and_value(
            expected_df=expected_df,
            generated_df=generated_df,
            atol=atol,
            rtol=rtol,
        )

        if len(col_map) != len(alphabetical_exp_columns):
            mapped_exp_cols = set(col_map.values())
            unmapped_cols = set(alphabetical_exp_columns) - mapped_exp_cols
            error_msg = f"Could not map all expected columns. Unmapped: {unmapped_cols}"
            logger.debug(f"Validation failed: {error_msg}")
            return ComparisonResult.error_result(error_msg, column_map=col_map)

        comp_df = generated_df.rename(columns=col_map)[alphabetical_exp_columns].copy()
        gold_df = expected_df.reindex(columns=alphabetical_exp_columns).copy()

        for col in alphabetical_exp_columns:
            is_gold_num = _is_coercible_numeric(gold_df[col])
            is_comp_num = _is_coercible_numeric(comp_df[col])
            if is_gold_num and is_comp_num:
                try:
                    gold_df[col] = pd.to_numeric(gold_df[col], errors="raise").astype(float)
                    comp_df[col] = pd.to_numeric(comp_df[col], errors="raise").astype(float)
                    continue
                except (ValueError, TypeError):
                    pass

            if gold_df[col].dtype == object:
                gold_df[col] = gold_df[col].astype(str)
            if comp_df[col].dtype == object:
                comp_df[col] = comp_df[col].astype(str)

        gold_df = gold_df.sort_values(by=alphabetical_exp_columns).reset_index(drop=True)
        comp_df = comp_df.sort_values(by=alphabetical_exp_columns).reset_index(drop=True)

        try:
            pd.testing.assert_frame_equal(
                gold_df,
                comp_df,
                check_dtype=False,
                atol=atol,
                rtol=rtol,
            )
            is_equivalent = True
        except AssertionError:
            is_equivalent = gold_df.equals(comp_df)

        return ComparisonResult.success_result(is_equivalent, column_map=col_map)
    except Exception as e:
        error_msg = f"Exception during comparison: {e!s}"
        logger.error(error_msg)
        return ComparisonResult.error_result(str(e))


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


class DataFrameValueEquivalence(DataFrameMetric):
    """Evaluates whether generated_df is value-equivalent to expected_df after 2-pass column mapping."""

    def measure(
        self,
        generated_df: pd.DataFrame,
        expected_df: pd.DataFrame,
        **kwargs,
    ) -> float:
        result = compare_query_results(
            expected_df=expected_df,
            generated_df=generated_df,
        )
        return 1.0 if result.is_equivalent else 0.0


class DataFrameMatch(DataFrameMetric):
    """Measures the similarity between two dataframes, allowing for partial matches and value-based column mapping."""

    def measure(
        self,
        generated_df: pd.DataFrame,
        expected_df: pd.DataFrame,
        fields: dict[str, list[str]] = None,
        **kwargs,
    ) -> float:
        """Compares two DataFrames, scoring based on column and data similarity."""
        if generated_df is None or expected_df is None:
            return 0.0

        if generated_df.empty and expected_df.empty:
            return 1.0

        if generated_df.empty or expected_df.empty:
            return 0.0

        # Map columns by exact name first, then by column values for renamed/aliased columns
        col_map = map_columns_by_name_and_value(
            expected_df=expected_df,
            generated_df=generated_df,
            atol=1e-2,
            rtol=1e-2,
        )
        if col_map:
            generated_df = generated_df.rename(columns=col_map)
            if fields:
                fields = {
                    k: [col_map.get(f, f) for f in (v or [])]
                    for k, v in fields.items()
                }

        # Check full value equivalence when column sets match
        if set(generated_df.columns) == set(expected_df.columns):
            eq_res = compare_query_results(
                expected_df=expected_df,
                generated_df=generated_df,
                atol=1e-2,
                rtol=1e-2,
            )
            if eq_res.is_equivalent:
                return 1.0

        # To allow for row-order differences, sort the dataframes before comparison.
        try:
            generated_df = generated_df.sort_values(
                by=list(generated_df.columns)
            ).reset_index(drop=True)
            expected_df = expected_df.sort_values(
                by=list(expected_df.columns)
            ).reset_index(drop=True)
        except Exception as e:
            logger.warning(
                f"Could not sort dataframes for comparison, proceeding with original order. Error: {e}"
            )

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
                return 0.0  # No common columns, so no basis for data comparison

            # 2. Data Similarity Score on Common Columns (Weight: 0.7)
            gen_subset_df = generated_df[common_cols].copy()
            exp_subset_df = expected_df[common_cols].copy()

            join_cols = common_cols
            if fields and fields.get("dimensions"):
                dims_in_common = list(set(fields.get("dimensions")) & set(common_cols))
                if dims_in_common:
                    join_cols = dims_in_common
            elif fields and fields.get("measures"):
                measures_in_common = list(set(fields.get("measures")) & set(common_cols))
                if measures_in_common:
                    join_cols = measures_in_common

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
