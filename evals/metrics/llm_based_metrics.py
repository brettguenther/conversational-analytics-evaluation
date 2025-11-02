import json
from typing import Dict, Any
import pandas as pd
import vertexai
from vertexai.evaluation import EvalTask, PointwiseMetric, PointwiseMetricPromptTemplate

import logging

class LLMBasedMetrics:
    """A metric for evaluating agent responses using an LLM-based autorater."""

    def __init__(self, project_id: str, location: str, experiment_name: str = "llm-based-metrics-eval"):
        """
        Initializes the LLMBasedMetrics and Vertex AI.
        """
        self.project_id = project_id
        self.location = location
        self.experiment_name = experiment_name
        vertexai.init(project=self.project_id, location=self.location)
        self.logger = logging.getLogger(__name__)


    def evaluate(self, question: str, generated_text: str, generated_df: pd.DataFrame, generated_chart: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates the agent's response for intent resolution and completeness."""
        self.logger.debug(f"Starting LLM-based evaluation for question: {question}")
        self.logger.debug(f"Generated text: {generated_text}")
        self.logger.debug(f"Generated df: {generated_df}")
        self.logger.debug(f"Generated chart: {generated_chart}")

        generated_data_dict= generated_df.to_dict(orient="records") if generated_df is not None else None

        # Combine all parts of the response into a single JSON string
        full_response = {
            "text": generated_text,
            "query_result": generated_data_dict,
            "chart": generated_chart,
        }
        response_str = json.dumps(full_response, indent=2)
        
        intent_resolution_metric = PointwiseMetric(
            metric="intent_resolution",
            metric_prompt_template=PointwiseMetricPromptTemplate(
                criteria={
                    "intent_match": "Given the analytics question: '{instruction}', does the response: '{response}' directly and accurately address the user's question or instruction?"
                },
                rating_rubric={
                    "1": "The response fully matches the intent.",
                    "0.5": "The response partially matches the intent.",
                    "0": "The response does not match the intent.",
                },
            ),
        )

        completeness_metric = PointwiseMetric(
            metric="completeness",
            metric_prompt_template=PointwiseMetricPromptTemplate(
                criteria={
                    "completeness": "Given the analytics question: '{instruction}', does the response: '{response}' provide all the necessary information to be considered a complete answer, without leaving out important details?"
                },
                rating_rubric={
                    "1": "The response is fully complete.",
                    "0.5": "The response is partially complete.",
                    "0": "The response is incomplete.",
                },
            ),
        )

        chart_appropriateness_metric = PointwiseMetric(
            metric="chart_appropriateness",
            metric_prompt_template=PointwiseMetricPromptTemplate(
                criteria={
                    "chart_appropriateness": "Given the analytics question: '{instruction}' and the generated data: {generated_data}, is the chart type chosen in the response: '{chart_response}' an effective and appropriate way to visualize the answer?"
                },
                rating_rubric={
                    "1": "The chart type is highly appropriate for the data and question.",
                    "0.5": "The chart type is acceptable but not optimal.",
                    "0": "The chart type is inappropriate or misleading.",
                },
            ),
        )

        eval_dataset = pd.DataFrame(
            {
                "instruction": [question],
                "response": [response_str],
                "generated_data": [generated_data_dict],
                "chart_response": [generated_chart]

            }
        )

        try:
            metrics_list = [intent_resolution_metric, completeness_metric]
            if generated_chart:
                metrics_list.append(chart_appropriateness_metric)

            eval_task = EvalTask(
                dataset=eval_dataset,
                metrics=metrics_list,
                experiment=self.experiment_name,
            )
            eval_result = eval_task.evaluate()
            self.logger.debug(f"Successfully received eval result: {eval_result}")

            row = eval_result.metrics_table.iloc[0]

            results = {}
            if 'intent_resolution/score' in row:
                 results["intent_resolution"] = {
                    "score": row["intent_resolution/score"],
                    "explanation": row.get("intent_resolution/explanation", "")
                }

            if 'completeness/score' in row:
                results["completeness"] = {
                    "score": row["completeness/score"],
                    "explanation": row.get("completeness/explanation", "")
                }

            if 'chart_appropriateness/score' in row:
                results["chart_appropriateness"] = {
                    "score": row["chart_appropriateness/score"],
                    "explanation": row.get("chart_appropriateness/explanation", "")
                }

            self.logger.debug(f"LLM-based evaluation results: {results}")
            return results
        except Exception as e:
            self.logger.error(f"An error occurred during LLM-based evaluation: {e}", exc_info=True)
            return {"error": str(e)}
