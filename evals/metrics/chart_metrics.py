from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def _normalize_field_candidates(field_name: str | None) -> set[str]:
    """Returns normalized identifier candidates for a chart axis field or label."""
    if not field_name or not isinstance(field_name, str):
        return set()
    cleaned = field_name.strip().lower().replace(" ", "_")
    candidates = {cleaned.replace(".", "_")}
    if "." in cleaned:
        # Also include the field name without the Looker view prefix (e.g., 'sales.total_sales' -> 'total_sales')
        _, short_name = cleaned.split(".", 1)
        if short_name:
            candidates.add(short_name.replace(".", "_"))
    return candidates


class ChartMetric:
    """A metric for evaluating the correctness of a generated chart."""

    def evaluate(self, generated_chart: Dict[str, Any], expected_chart: Dict[str, Any]) -> float:
        """
        Evaluates the correctness of a generated chart against an expected chart.

        Args:
            generated_chart: The generated chart object.
            expected_chart: The expected chart object.

        Returns:
            A score from 0.0 to 1.0 indicating the correctness of the chart.
        """
        logger.debug(f"Generated chart: {generated_chart}")
        logger.debug(f"Expected chart: {expected_chart}")

        if (
            not isinstance(generated_chart, dict)
            or not isinstance(expected_chart, dict)
            or not generated_chart
            or not expected_chart
        ):
            return 0.0

        score = 0.0
        total_checks = 3.0

        # 1. Compare mark type (Vega-Lite 'mark' can be a string like 'bar' or a dict like {'type': 'bar'})
        raw_mark = generated_chart.get("mark")
        if isinstance(raw_mark, dict):
            generated_mark_type = raw_mark.get("type")
        elif isinstance(raw_mark, str):
            generated_mark_type = raw_mark
        else:
            generated_mark_type = None

        raw_expected_type = expected_chart.get("type")
        expected_mark_type = (
            raw_expected_type.replace(".", "_")
            if isinstance(raw_expected_type, str)
            else None
        )
        if generated_mark_type and expected_mark_type and generated_mark_type == expected_mark_type:
            score += 1
            logger.debug("Mark type matches.")
        else:
            logger.debug(f"Mark type mismatch: generated={generated_mark_type}, expected={expected_mark_type}")

        encoding = generated_chart.get("encoding")
        if not isinstance(encoding, dict):
            encoding = {}

        # 2. Compare x-axis field
        x_enc = encoding.get("x")
        generated_x_field = x_enc.get("field") if isinstance(x_enc, dict) else None
        expected_x_field = expected_chart.get("x-axis")
        gen_x_candidates = _normalize_field_candidates(generated_x_field)
        exp_x_candidates = _normalize_field_candidates(expected_x_field)
        if gen_x_candidates and exp_x_candidates and (gen_x_candidates & exp_x_candidates):
            score += 1
            logger.debug("X-axis field matches.")
        else:
            logger.debug(f"X-axis field mismatch: generated={generated_x_field}, expected={expected_x_field}")

        # 3. Compare y-axis field
        y_enc = encoding.get("y")
        generated_y_field = y_enc.get("field") if isinstance(y_enc, dict) else None
        expected_y_field = expected_chart.get("y-axis")
        gen_y_candidates = _normalize_field_candidates(generated_y_field)
        exp_y_candidates = _normalize_field_candidates(expected_y_field)
        if gen_y_candidates and exp_y_candidates and (gen_y_candidates & exp_y_candidates):
            score += 1
            logger.debug("Y-axis field matches.")
        else:
            logger.debug(f"Y-axis field mismatch: generated={generated_y_field}, expected={expected_y_field}")

        final_score = score / total_checks
        logger.debug(f"Final chart score: {final_score}")
        return final_score
