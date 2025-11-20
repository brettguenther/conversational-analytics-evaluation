import json
import os
import altair as alt

def generate_markdown_report(evaluation_results, filename="evaluation_report.md"):
    """Generates a Markdown report from the evaluation results."""
    
    # Create a directory for images if it doesn't exist
    if not os.path.exists("images"):
        os.makedirs("images")

    with open(filename, "w") as f:
        summary = evaluation_results.get("evaluation_summary", {})
        f.write("# Evaluation Report\n\n")
        f.write("## Summary\n\n")
        f.write(f"- **Agent ID:** {summary.get('agent_id', 'N/A')}\n")
        f.write(f"- **Conversation ID:** {summary.get('conversation_id', 'N/A')}\n")
        f.write(f"- **Total Questions:** {summary.get('total_questions', 0)}\n")
        f.write(f"- **Correct Questions:** {summary.get('correct_questions', 0)}\n")
        f.write(f"- **Incorrect Questions:** {summary.get('incorrect_questions', 0)}\n")
        f.write(f"- **Accuracy:** {summary.get('accuracy', 0.0):.2f}\n")
        f.write(f"- **Timestamp:** {summary.get('timestamp', 'N/A')}\n\n")

        results = evaluation_results.get("results", [])
        
        # Prepare data for the summary table
        table_data = []
        metric_names = []
        if results:
            all_metric_names = set()
            for result in results:
                metrics = result.get("evaluation_metrics", {})
                for metric, value in metrics.items():
                    if metric == 'llm_based_evaluation' and isinstance(value, dict):
                        for llm_metric in value.keys():
                            all_metric_names.add(llm_metric)
                    elif metric != 'overall_correctness':
                        all_metric_names.add(metric)
            metric_names = sorted(list(all_metric_names))
        
        for result in results:
            question_details = result.get("question_details", {})
            evaluation_metrics = result.get("evaluation_metrics", {})
            row = {
                "Question ID": question_details.get("id", "N/A"),
                "Category": question_details.get("category", "N/A"),
                "Overall Score": "Correct" if evaluation_metrics.get("overall_correctness", False) else "Incorrect"
            }
            for metric in metric_names:
                score = "N/A"
                if metric in evaluation_metrics:
                    metric_value = evaluation_metrics[metric]
                    if isinstance(metric_value, dict) and 'details' in metric_value:
                        try:
                            score = float(metric_value['details'].split(': ')[1])
                        except (ValueError, IndexError):
                            score = "N/A"
                    elif isinstance(metric_value, dict) and 'score' in metric_value:
                        score = metric_value.get('score', 'N/A')

                elif 'llm_based_evaluation' in evaluation_metrics and metric in evaluation_metrics['llm_based_evaluation']:
                    llm_metric_value = evaluation_metrics['llm_based_evaluation'][metric]
                    if isinstance(llm_metric_value, dict):
                        score = llm_metric_value.get('score', 'N/A')
                
                row[metric] = f"{score:.2f}" if isinstance(score, float) else score

            table_data.append(row)

        # Write the summary table
        if table_data:
            header = ["Question ID", "Category", "Overall Score"] + metric_names
            f.write("| " + " | ".join(header) + " |\n")
            f.write("|" + "---|" * len(header) + "\n")
            for row in table_data:
                f.write("| " + " | ".join(str(row.get(h, "N/A")) for h in header) + " |\n")
            f.write("\n")


        f.write("## Detailed Results\n\n")

        for i, result in enumerate(results):
            question_details = result.get("question_details", {})
            agent_response = result.get("agent_response", {})
            evaluation_metrics = result.get("evaluation_metrics", {})
            overall_correctness = evaluation_metrics.get("overall_correctness", False)

            f.write(f"### Question {question_details.get('id', i+1)}: {question_details.get('question', 'N/A')}\n\n")
            f.write(f"**Category:** {question_details.get('category', 'N/A')}\n\n")
            f.write(f"**Expected Result:** {question_details.get('expected_result_text', 'N/A')}\n\n")
            f.write(f"**Overall Correctness:** {'Correct' if overall_correctness else 'Incorrect'}\n\n")

            f.write("#### Agent Response\n\n")
            f.write(f"**Response Text:** `{agent_response.get('response_text', 'N/A')}`\n\n")
            f.write("**Generated Looker Query:**\n")
            f.write("```json\n")
            f.write(json.dumps(agent_response.get("generated_query", {}), indent=2))
            f.write("\n```\n\n")

            generated_chart = agent_response.get("generated_chart")
            if generated_chart:
                try:
                    chart = alt.Chart.from_json(json.dumps(generated_chart))
                    chart_path = f"images/chart_{question_details.get('id', i+1)}.png"
                    chart.save(chart_path,'png')
                    f.write("**Generated Chart:**\n\n")
                    f.write(f"![Generated Chart]({chart_path})\n\n")
                except Exception as e:
                    f.write("**Generated Chart:**\n\n")
                    f.write(f"_Could not generate chart image: {e}_\n\n")
                f.write("**Generated Chart JSON:**\n")
                f.write("```json\n")
                f.write(json.dumps(agent_response.get("generated_chart", {}), indent=2))
                f.write("\n```\n\n")

            f.write("#### Evaluation Metrics\n\n")
            for metric, value in evaluation_metrics.items():
                if metric == 'llm_based_evaluation':
                    f.write(f"- **{metric.replace('_', ' ').title()}:**\n")
                    if isinstance(value, dict) and 'error' in value:
                        f.write(f"  - **Error:** {value['error']}\n")
                    elif isinstance(value, dict):
                        for llm_metric, llm_value in value.items():
                            f.write(f"  - **{llm_metric.replace('_', ' ').title()}:**\n")
                            if isinstance(llm_value, dict):
                                f.write(f"    - **Score:** {llm_value.get('score', 'N/A')}\n")
                                f.write(f"    - **Explanation:** {llm_value.get('explanation', 'N/A')}\n")
                            else:
                                f.write(f"    - {llm_value}\n")
                elif isinstance(value, dict):
                    f.write(f"- **{metric.replace('_', ' ').title()}:** {'Correct' if value.get('correct') else 'Incorrect'}\n")
                    f.write(f"- **Details:** {value.get('details', 'N/A')}\n")
            f.write("\n---\n\n")