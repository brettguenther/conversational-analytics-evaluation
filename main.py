"""Main CLI for running evaluations."""

import json
import click
import pandas as pd
from io import StringIO

from agents.looker_agent_client import LookerAgentClient
from evals.metrics.sql_metrics import (
    score_sql_response,
    SQLExactMatch,
    SQLResultMatch,
)
from evals.metrics.semantic_correctness_metric import semantic_correctness
from utils.dataset_generator import EvalQuestion

def parse_expected_result_to_df(result_str: str) -> pd.DataFrame | None:
    """Parses the expected result string into a DataFrame.

    This is a simple placeholder. A more robust implementation is needed to handle
    the various formats in the expected_result column.
    """
    try:
        # Attempt to treat the string as a CSV with flexible whitespace
        return pd.read_csv(StringIO(result_str), sep='\s\s+', engine='python')
    except Exception:
        # Return None if parsing fails
        return None


@click.group()
def cli():
    """A CLI tool for evaluating Looker's Conversational Analytics API."""
    pass


@cli.command()
@click.option(
    "--questions-file",
    default="data/questions/questions.json",
    help="Path to the JSON file with evaluation questions.",
)
@click.option("--project-id", required=True, help="Google Cloud project ID.")
@click.option("--looker-instance", required=True, help="Looker instance URL.")
@click.option("--looker-model", required=True, help="Looker model name.")
@click.option("--looker-explore", required=True, help="Looker explore name.")
@click.option(
    "--agent-id", default="sales-agent", help="The ID for the data agent."
)
@click.option(
    "--conversation-id",
    default="sales-eval-conversation",
    help="The ID for the conversation.",
)
@click.option(
    "--config-file",
    default="config.json",
    help="Path to the JSON file with configuration.",
)
def run_evaluation(
    questions_file: str,
    project_id: str,
    looker_instance: str,
    looker_model: str,
    looker_explore: str,
    agent_id: str,
    conversation_id: str,
    config_file: str,
):
    """Runs the evaluation of the Looker agent."""

    # 1. Load config
    with open(config_file, "r") as f:
        config = json.load(f)
        looker_client_id = config.get("looker_client_id")
        looker_client_secret = config.get("looker_client_secret")

    # 2. Initialize the Looker Agent Client
    looker_client = LookerAgentClient(
        project_id=project_id,
        looker_instance=looker_instance,
        looker_model=looker_model,
        looker_explore=looker_explore,
        looker_client_id=looker_client_id,
        looker_client_secret=looker_client_secret,
    )

    # 2. Create or get the data agent
    system_instruction = "You are a helpful data assistant."
    print(f"Creating data agent '{agent_id}'...")
    agent = looker_client.create_agent(agent_id, system_instruction)
    if not agent:
        print("Failed to create agent. Exiting.")
        return

    # 3. Load the evaluation questions
    with open(questions_file, "r") as f:
        questions_data = json.load(f)
        questions = [EvalQuestion(**q) for q in questions_data]

    # 4. Initialize metrics
    metrics = [SQLExactMatch(), SQLResultMatch()]

    # 5. Run evaluation for each question
    for i, question in enumerate(questions):
        print(f"\n--- Running evaluation for question {i+1}/{len(questions)} ---")
        print(f"Category: {question.category}")
        print(f"Question: {question.question}")

        # Create a new conversation for each question
        conv_id = f"{conversation_id}-{i}"
        looker_client.create_conversation(agent_id, conv_id)

        # Get the agent's response
        generated_sql, generated_df, generated_looker_query = looker_client.chat(
            agent_id, conv_id, question.question
        )

        print("\nAgent's Generated SQL:")
        print(generated_sql)

        print("\nAgent's Result:")
        print(generated_df)

        print("\nAgent's Generated Looker Query:")
        print(generated_looker_query)

        # Parse expected result string into a DataFrame
        expected_df = parse_expected_result_to_df(question.expected_result)

        # For this version, we assume expected_sql is not in the questions file.
        expected_sql = ""

        # Score the response
        scores = score_sql_response(
            generated_sql=generated_sql,
            expected_sql=expected_sql,
            generated_df=generated_df,
            expected_df=expected_df,
            metrics=metrics,
        )

        if generated_looker_query and question.reference_query:
            semantic_score = semantic_correctness(generated_looker_query, question.reference_query)
            scores["Semantic Correctness"] = semantic_score

        print("\nEvaluation Scores:")
        for metric_name, score in scores.items():
            print(f"  {metric_name}: {score:.2f}")


if __name__ == "__main__":
    cli()
