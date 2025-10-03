from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

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

        if not generated_chart or not expected_chart:
            return 0.0

        score = 0.0
        total_checks = 3.0

        # 1. Compare mark type
        generated_mark_type = generated_chart.get("mark", {}).get("type")
        expected_mark_type = expected_chart.get("type").replace(".","_")
        if generated_mark_type and expected_mark_type and generated_mark_type == expected_mark_type:
            score += 1
            logger.debug("Mark type matches.")
        else:
            logger.debug(f"Mark type mismatch: generated={generated_mark_type}, expected={expected_mark_type}")

        # 2. Compare x-axis field
        generated_x_field = generated_chart.get("encoding", {}).get("x", {}).get("field")
        expected_x_field = expected_chart.get("x-axis")
        if generated_x_field and expected_x_field and generated_x_field == expected_x_field:
            score += 1
            logger.debug("X-axis field matches.")
        else:
            logger.debug(f"X-axis field mismatch: generated={generated_x_field}, expected={expected_x_field}")

        # 3. Compare y-axis field
        generated_y_field = generated_chart.get("encoding", {}).get("y", {}).get("field")
        expected_y_field = expected_chart.get("y-axis")
        if generated_y_field and expected_y_field and generated_y_field == expected_y_field:
            score += 1
            logger.debug("Y-axis field matches.")
        else:
            logger.debug(f"Y-axis field mismatch: generated={generated_y_field}, expected={expected_y_field}")

        final_score = score / total_checks
        logger.debug(f"Final chart score: {final_score}")
        return final_score
