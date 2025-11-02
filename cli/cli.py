import os
import json
import uuid
import typer
import pandas as pd
import datetime
import logging
from google.cloud import geminidataanalytics
from utils.auth import check_gcloud_auth
from typing_extensions import Annotated

app = typer.Typer()

@app.command()
def looker(
    questions_file: Annotated[str, typer.Option(help="Path to the JSON file with evaluation questions.")] = "data/questions/questions.json",
    project_id: Annotated[str, typer.Option(help="Google Cloud project ID.")] = ...,
    location: Annotated[str, typer.Option(help="The location for the agent.")] = "global",
    looker_instance: Annotated[str, typer.Option(help="Looker instance URL.")] = ...,
    looker_model: Annotated[str, typer.Option(help="Looker model name.")] = ...,
    looker_explore: Annotated[str, typer.Option(help="Looker explore name.")] = ...,
    agent_id: Annotated[str, typer.Option(help="The ID for the data agent.")] = None,
    conversation_id: Annotated[str, typer.Option(help="The ID for the conversation.")] = None,
    system_instructions_file: Annotated[str, typer.Option(help="Path to a file containing system instructions.")] = None,
    looker_access_token: Annotated[str, typer.Option(help="Use a Looker access token to authenticate to Looker APIs.")] = None,
    skip_agent_use: Annotated[bool, typer.Option(help="Skip agent use and run evaluation using inline context (stateless chat) API.")] = False,
    generate_report: Annotated[bool, typer.Option(help="Generate a Markdown report of the evaluation results.")] = False,
    log_level: Annotated[str, typer.Option(help="Set the logging level.")] = "INFO",
    llm_eval: Annotated[bool, typer.Option(help="Enable LLM-based evaluation through Vertex AI Evaluation Service.")] = False,
):
    """Runs the evaluation of the Looker agent."""

    check_gcloud_auth()  # Check for valid gcloud credentials

    # Configure logging
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler("evaluation.log"),
            logging.StreamHandler(),
        ],
    )
    # TODO: add conditional for: vertexai.evaluation._evaluation
    logging.getLogger("datacompy").setLevel(logging.WARNING)
    logging.getLogger("absl").setLevel(logging.WARNING)
    logging.getLogger("vertexai.evaluation.metrics.metric_prompt_template").setLevel(logging.WARNING)
    logging.getLogger('rouge_score').setLevel(logging.WARNING)

    from utils.reporter import generate_markdown_report
    from dataclasses import asdict

    from agents.looker_agent_client import LookerAgentClient
    from evals.metrics.sql_metrics import (
        score_sql_text,
        SQLExactMatch,
    )
    from evals.metrics.dataframe_metrics import (
        score_dataframes,
        DataFrameMatch,
    )
    from evals.metrics.semantic_correctness_metric import semantic_correctness
    from utils.dataset_generator import EvalQuestion
    from evals.metrics.text_similarity_metric import calculate_rouge_score
    from evals.metrics.chart_metrics import ChartMetric
    from evals.metrics.llm_based_metrics import LLMBasedMetrics

    def parse_expected_result_to_df(question: EvalQuestion) -> pd.DataFrame | None:
        """Parses the expected result into a DataFrame."""
        if question.expected_result:
            return pd.DataFrame(question.expected_result)
        return None

    # 2. Initialize the appropriate client
    looker_client = LookerAgentClient(
        project_id=project_id,
        location=location,
        looker_access_token=looker_access_token,
    )

    if system_instructions_file:
        with open(system_instructions_file, "r") as f:
            system_instruction = f.read()
    else:
        system_instruction = "You are a helpful data assistant."

    if not skip_agent_use:
        if agent_id is None:
            agent_id = f"agent-{uuid.uuid4()}"
        logging.info(f"Creating data agent '{agent_id}'...")
        agent = looker_client.create_agent(
            agent_id=agent_id,
            system_instruction=system_instruction,
            looker_instance_uri=looker_instance,
            lookml_model=looker_model,
            explore=looker_explore,
        )

        if not agent:
            logging.error("Failed to create agent. Exiting.")
            return

        if conversation_id is None:
            conversation_id = f"conv-{uuid.uuid4()}"
        logging.info(f"Creating conversation '{conversation_id}'...")
        looker_client.create_conversation(agent_id, conversation_id)

    # 3. Load the evaluation questions
    with open(questions_file, "r") as f:
        questions_data = json.load(f)
        questions = [EvalQuestion(**q) for q in questions_data]

    # 4. Initialize metrics
    sql_text_metrics = [SQLExactMatch()]
    dataframe_metrics = [DataFrameMatch()]
    chart_metric = ChartMetric()
    if llm_eval:
        #TODO: provide alt region if global default used
        llm_metric = LLMBasedMetrics(project_id=project_id, location="us-central1")
    
    results = []
    correct_questions = 0

    # 5. Run evaluation for each question
    for i, question in enumerate(questions):
        logging.info(f"--- Running evaluation for question {question.id} ({i+1}/{len(questions)}) ---")
        logging.info(f"Question: {question.question}, Category: {question.category}")

        # Get the agent's response
        generated_sql, generated_df, generated_looker_query, generated_text, generated_chart, dimensions, measures = looker_client.chat(
            agent_id=agent_id,
            conversation_id=conversation_id,
            question=question.question,
            system_instruction=system_instruction,
            skip_agent_use=skip_agent_use,
        )

        # Parse expected result string into a DataFrame
        expected_df = parse_expected_result_to_df(question)

        # For this version, we assume expected_sql is not in the questions file.
        expected_sql = ""

        # Score the response
        sql_scores = {}

        dataframe_scores = score_dataframes(
            generated_df=generated_df,
            expected_df=expected_df,
            fields={"dimensions": dimensions, "measures": measures},
            metrics=dataframe_metrics,
        )

        text_score = {"RougeFMetric":calculate_rouge_score(generated_text, question.expected_result_text)}
        
        chart_score = None
        if question.expected_data_visualization:
            chart_score = chart_metric.evaluate(generated_chart, question.expected_data_visualization)

        scores = {**sql_scores, **dataframe_scores, **text_score}
        if chart_score is not None:
            scores["ChartCorrectness"] = chart_score

        if llm_eval:
            llm_scores = llm_metric.evaluate(question.question, generated_text, generated_df, generated_chart)
            scores["LLMBasedEvaluation"] = llm_scores

        if generated_looker_query and question.reference_query:
            semantic_score = semantic_correctness(generated_looker_query, question.reference_query)
            scores["Semantic Correctness"] = semantic_score

        is_correct = scores.get("Semantic Correctness", 0.0) == 1.0 or scores.get("DataFrameMatch", 0.0) == 1.0 or scores.get("RougeFMetric") == 1.0 or scores.get("ChartCorrectness", 0.0) == 1.0
        if is_correct:
            correct_questions += 1

        serialized_looker_query = geminidataanalytics.LookerQuery.to_dict(generated_looker_query)

        evaluation_metrics = {
            "semantic_correctness": {
                "correct": scores.get("Semantic Correctness", 0.0) == 1.0,
                "details": f"Score: {scores.get('Semantic Correctness', 0.0):.2f}",
            },
            "data_correctness": {
                "correct": scores.get("DataFrameMatch", 0.0) == 1.0,
                "details": f"Score: {scores.get('DataFrameMatch', 0.0):.2f}",
            },
            "text_correctness": {
                "correct": scores.get("RougeFMetric", 0.0) >= 0.8,
                "details": f"Score: {scores.get('RougeFMetric', 0.0):.2f}",
            },
            "llm_based_evaluation": scores.get("LLMBasedEvaluation", {}),
            "overall_correctness": is_correct,
        }

        if "ChartCorrectness" in scores:
            evaluation_metrics["chart_correctness"] = {
                "correct": scores.get("ChartCorrectness", 0.0) == 1.0,
                "details": f"Score: {scores.get('ChartCorrectness', 0.0):.2f}",
            }

        result = {
            "question_details": asdict(question),
            "agent_response": {
                "response_text": generated_text,
                "generated_query": serialized_looker_query,
                "data_result": generated_df.to_dict(orient="records") if generated_df is not None else [],
                "generated_chart": generated_chart,
            },
            "evaluation_metrics": evaluation_metrics,
        }
        results.append(result)
        logging.info(f"Result: {json.dumps(result['evaluation_metrics'], indent=2)}")

    # 6. Assemble the final evaluation results
    total_questions = len(questions)
    accuracy = correct_questions / total_questions if total_questions > 0 else 0.0
    evaluation_summary = {
        "agent_id": agent_id,
        "conversation_id": conversation_id,
        "total_questions": total_questions,
        "correct_questions": correct_questions,
        "incorrect_questions": total_questions - correct_questions,
        "accuracy": accuracy,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    evaluation_results = {
        "evaluation_summary": evaluation_summary,
        "results": results,
    }

    # 7. Output the results
    # Create results directory if it doesn't exist
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)

    # Generate unique filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    results_filename = os.path.join(results_dir, f"evaluation_results_{timestamp}.json")

    # Write results to JSON file
    with open(results_filename, "w") as f:
        json.dump(evaluation_results, f, indent=2)
    logging.info(f"Evaluation results saved to {results_filename}")

    if generate_report:
        generate_markdown_report(evaluation_results)
        logging.info("Evaluation report generated as evaluation_report.md")
    else:
        print(json.dumps(evaluation_results, indent=2))

if __name__ == "__main__":
    app()
