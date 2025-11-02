
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from evals.metrics.llm_based_metrics import LLMBasedMetrics

class TestLLMBasedMetrics(unittest.TestCase):

    @patch('evals.metrics.llm_based_metrics.vertexai.init')
    @patch('evals.metrics.llm_based_metrics.EvalTask')
    def test_evaluate_success(self, mock_eval_task, mock_vertex_init):
        """
        Tests a successful evaluation call.
        """
        # Arrange
        mock_vertex_init.return_value = None

        # Mock the EvalResult and its metrics_table
        mock_eval_result = MagicMock()
        mock_metrics_data = {
            'intent_resolution_score': [1.0],
            'intent_resolution_explanation': ['The response directly answers the question.'],
            'completeness_score': [0.0],
            'completeness_explanation': ['The response is missing some details.']
        }
        mock_eval_result.metrics_table = pd.DataFrame(mock_metrics_data)
        
        # Mock the evaluate method of the EvalTask instance
        mock_eval_task_instance = mock_eval_task.return_value
        mock_eval_task_instance.evaluate.return_value = mock_eval_result

        # Act
        metric = LLMBasedMetrics(project_id="test-project", location="test-location")
        result = metric.evaluate(
            question="What are the total sales?",
            generated_text="The total sales are $1M.",
            generated_df=pd.DataFrame({'sales': [1000000]})
        )

        # Assert
        self.assertIn("intent_resolution", result)
        self.assertEqual(result["intent_resolution"]["score"], 1.0)
        self.assertEqual(result["intent_resolution"]["explanation"], "The response directly answers the question.")
        
        self.assertIn("completeness", result)
        self.assertEqual(result["completeness"]["score"], 0.0)
        self.assertEqual(result["completeness"]["explanation"], "The response is missing some details.")

        # Verify that vertexai.init and EvalTask were called
        mock_vertex_init.assert_called_once_with(project="test-project", location="test-location")
        mock_eval_task.assert_called_once()

    @patch('evals.metrics.llm_based_metrics.vertexai.init')
    @patch('evals.metrics.llm_based_metrics.EvalTask')
    def test_evaluate_api_error(self, mock_eval_task, mock_vertex_init):
        """
        Tests the handling of an exception from the Vertex AI API.
        """
        # Arrange
        mock_vertex_init.return_value = None
        
        # Configure the mock to raise an exception
        mock_eval_task_instance = mock_eval_task.return_value
        mock_eval_task_instance.evaluate.side_effect = Exception("API call failed")

        # Act
        metric = LLMBasedMetrics(project_id="test-project", location="test-location")
        result = metric.evaluate(
            question="What are the total sales?",
            generated_text="The total sales are $1M.",
            generated_df=pd.DataFrame({'sales': [1000000]})
        )

        # Assert
        self.assertIn("error", result)
        self.assertEqual(result["error"], "API call failed")

if __name__ == '__main__':
    unittest.main()
