
import json

def generate_markdown_report(evaluation_results, filename="evaluation_report.md"):
    """Generates a Markdown report from the evaluation results."""
    with open(filename, "w") as f:
        summary = evaluation_results.get("evaluation_summary", {})
        f.write("# Evaluation Report\n\n")
        f.write("## Summary\n\n")
        f.write(f"- **Total Questions:** {summary.get('total_questions', 0)}\n")
        f.write(f"- **Correct Questions:** {summary.get('correct_questions', 0)}\n")
        f.write(f"- **Incorrect Questions:** {summary.get('incorrect_questions', 0)}\n")
        f.write(f"- **Accuracy:** {summary.get('accuracy', 0.0):.2f}\n")
        f.write(f"- **Timestamp:** {summary.get('timestamp', 'N/A')}\n\n")

        f.write("## Detailed Results\n\n")

        results = evaluation_results.get("results", [])
        for i, result in enumerate(results):
            question_details = result.get("question_details", {})
            agent_response = result.get("agent_response", {})
            evaluation_metrics = result.get("evaluation_metrics", {})
            overall_correctness = evaluation_metrics.get("overall_correctness", False)

            f.write(f"### Question {i+1}: {question_details.get('question', 'N/A')}\n\n")
            f.write(f"**Category:** {question_details.get('category', 'N/A')}\n")
            f.write(f"**Expected Result:** {question_details.get('expected_result_text', 'N/A')}\n")
            f.write(f"**Overall Correctness:** {'Correct' if overall_correctness else 'Incorrect'}\n\n")

            f.write("#### Agent Response\n\n")
            f.write(f"**Response Text:** `{agent_response.get('response_text', 'N/A')}`\n\n")
            f.write("**Generated Looker Query:**\n")
            f.write("```json\n")
            f.write(json.dumps(agent_response.get("generated_query", {}), indent=2))
            f.write("\n```\n\n")

            f.write("#### Evaluation Metrics\n\n")
            for metric, value in evaluation_metrics.items():
                if isinstance(value, dict):
                    f.write(f"- **{metric.replace('_', ' ').title()}:** {'Correct' if value.get('correct') else 'Incorrect'}\n")
                    f.write(f"  - **Details:** {value.get('details', 'N/A')}\n")
            f.write("\n---\n\n")

