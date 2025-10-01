import json
import uuid
import click
import pandas as pd
from io import StringIO
import datetime
import logging
from google.cloud import geminidataanalytics

@click.group()
def cli():
    """A CLI tool for evaluating the Gemini Data Analytics API."""
    pass


@cli.command()
@click.option(
    "--questions-file",
    default="data/questions/questions.json",
    help="Path to the JSON file with evaluation questions.",
)
@click.option("--project-id", required=True, help="Google Cloud project ID.")
@click.option("--location", default="global", help="The location for the agent.")
@click.option("--looker-instance", required=True, help="Looker instance URL.")
@click.option("--looker-model", required=True, help="Looker model name.")
@click.option("--looker-explore", required=True, help="Looker explore name.")
@click.option(
    "--agent-id", default=None, help="The ID for the data agent."
)
@click.option(
    "--conversation-id",
    default=None,
    help="The ID for the conversation.",
)
@click.option(
    "--system-instructions-file",
    default=None,
    help="Path to a file containing system instructions.",
)
@click.option(
    "--skip-agent-use",
    is_flag=True,
    default=False,
    help="Skip agent use and run evaluation using inline context API.",
)
@click.option(
    "--client",
    type=click.Choice(["sdk", "http"]),
    default="sdk",
    help="The client to use for the evaluation.",
)
@click.option(
    "--generate-report",
    is_flag=True,
    default=False,
    help="Generate a Markdown report of the evaluation results.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    default="INFO",
    help="Set the logging level.",
)
def run_evaluation(
    questions_file: str,
    project_id: str,
    location: str,
    looker_instance: str,
    looker_model: str,
    looker_explore: str,
    agent_id: str | None,
    conversation_id: str | None,
    system_instructions_file: str | None,
    skip_agent_use: bool,
    client: str,
    generate_report: bool,
    log_level: str,
):
    """Runs the evaluation of the Looker agent."""

    # Configure logging
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("evaluation.log"),
            logging.StreamHandler(),
        ],
    )
    from utils.reporter import generate_markdown_report
    from dataclasses import asdict

    from agents.looker_agent_client import LookerAgentClient
    from agents.looker_agent_http_client import LookerAgentHttpClient
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

    def parse_expected_result_to_df(question: EvalQuestion) -> pd.DataFrame | None:
        """Parses the expected result into a DataFrame."""
        if question.expected_result:
            return pd.DataFrame(question.expected_result)
        return None

    # 2. Initialize the appropriate client
    if client == "sdk":
        looker_client = LookerAgentClient(
            project_id=project_id,
            location=location,
        )
    else:
        looker_client = LookerAgentHttpClient(
            project=project_id,
            location=location,
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
        looker_client.create_conversation(agent_id, conversation_id)

    # 3. Load the evaluation questions
    with open(questions_file, "r") as f:
        questions_data = json.load(f)
        questions = [EvalQuestion(**q) for q in questions_data]

    # 4. Initialize metrics
    sql_text_metrics = [SQLExactMatch()]
    dataframe_metrics = [DataFrameMatch()]
    
    results = []
    correct_questions = 0

    # 5. Run evaluation for each question
    for i, question in enumerate(questions):
        logging.info(f"--- Running evaluation for question {i+1}/{len(questions)} ---")
        logging.info(f"Question: {question.question}, Category: {question.category}")

        # Get the agent's response
        generated_sql, generated_df, generated_looker_query, generated_text = looker_client.chat(
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
            metrics=dataframe_metrics,
        )

        text_score = {"RougeFMetric":calculate_rouge_score(generated_text, question.expected_result_text)}
    
        
        scores = {**sql_scores, **dataframe_scores, **text_score}

        if generated_looker_query and question.reference_query:
            semantic_score = semantic_correctness(generated_looker_query, question.reference_query)
            scores["SemanticCorrectness"] = semantic_score

        is_correct = scores.get("SemanticCorrectness", 0.0) == 1.0 or scores.get("DataFrameMatch", 0.0) == 1.0 or scores.get("RougeFMetric") == 1.0
        if is_correct:
            correct_questions += 1

        serialized_looker_query = geminidataanalytics.LookerQuery.to_dict(generated_looker_query)

        result = {
            "question_details": asdict(question),
            "agent_response": {
                "response_text": generated_text,
                "generated_query": serialized_looker_query,
                "data_result": generated_df.to_dict(orient="records") if generated_df is not None else [],
            },
            "evaluation_metrics": {
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
                "overall_correctness": is_correct,
            },
        }
        results.append(result)

    # 6. Assemble the final evaluation results
    total_questions = len(questions)
    accuracy = correct_questions / total_questions if total_questions > 0 else 0.0
    evaluation_summary = {
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
    if generate_report:
        generate_markdown_report(evaluation_results)
        logging.info("Evaluation report generated as evaluation_report.md")
    else:
        print(json.dumps(evaluation_results, indent=2))


if __name__ == "__main__":
    cli()