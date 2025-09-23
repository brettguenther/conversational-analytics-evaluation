import json
import uuid
import click
import pandas as pd
from io import StringIO

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

def parse_expected_result_to_df(question: EvalQuestion) -> pd.DataFrame | None:
    """Parses the expected result into a DataFrame."""
    if question.expected_result:
        return pd.DataFrame(question.expected_result)
    return None


@click.group()
def cli():
    """A CLI tool for evaluating Google's Gemini Data Analytics API."""
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
    "--agent-id", default=None, help="The ID for the data agent."
)
@click.option(
    "--conversation-id",
    default=None,
    help="The ID for the conversation.",
)
@click.option(
    "--config-file",
    default="config.json",
    help="Path to the JSON file with configuration.",
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
def run_evaluation(
    questions_file: str,
    project_id: str,
    looker_instance: str,
    looker_model: str,
    looker_explore: str,
    agent_id: str | None,
    conversation_id: str | None,
    config_file: str,
    system_instructions_file: str | None,
    skip_agent_use: bool,
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

    if system_instructions_file:
        with open(system_instructions_file, "r") as f:
            system_instruction = f.read()
    else:
        system_instruction = "You are a helpful data assistant."

    if not skip_agent_use:
        if agent_id is None:
            agent_id = f"agent-{uuid.uuid4()}"
        print(f"Creating data agent '{agent_id}'...")
        agent = looker_client.create_agent(agent_id, system_instruction)
        if not agent:
            print("Failed to create agent. Exiting.")
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

    # 5. Run evaluation for each question
    for i, question in enumerate(questions):
        print(f"\n--- Running evaluation for question {i+1}/{len(questions)} ---")
        print(f"Category: {question.category}")
        print(f"Question: {question.question}")

        # Get the agent's response
        generated_sql, generated_df, generated_looker_query, generated_text = looker_client.chat(
            agent_id=agent_id, 
            conversation_id=conversation_id, 
            question=question.question,
            system_instruction=system_instruction,
            skip_agent_use=skip_agent_use,
        )

        print("\nAgent's Generated SQL:")
        print(generated_sql)

        print("\nAgent's Result:")
        print(generated_df)

        print("\nAgent's Generated Looker Query:")
        print(generated_looker_query)

        print("\nAgent's Generated Text:")
        print(generated_text)

        # Parse expected result string into a DataFrame
        expected_df = parse_expected_result_to_df(question)

        # For this version, we assume expected_sql is not in the questions file.
        expected_sql = ""

        # Score the response
        sql_scores = score_sql_text(
            generated_sql=generated_sql,
            expected_sql=expected_sql,
            metrics=sql_text_metrics,
        )
        dataframe_scores = score_dataframes(
            generated_df=generated_df,
            expected_df=expected_df,
            metrics=dataframe_metrics,
        )
        
        scores = {**sql_scores, **dataframe_scores}

        if generated_looker_query and question.reference_query:
            semantic_score = semantic_correctness(generated_looker_query, question.reference_query)
            scores["Semantic Correctness"] = semantic_score

        print("\nEvaluation Scores:")
        for metric_name, score in scores.items():
            print(f"  {metric_name}: {score:.2f}")


if __name__ == "__main__":
    cli()
