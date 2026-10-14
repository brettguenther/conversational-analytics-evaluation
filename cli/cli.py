import datetime
import json
import logging
import os
from typing import List, Optional
import uuid

from google.cloud import geminidataanalytics_v1 as geminidataanalytics
import pandas as pd
import typer
from typing_extensions import Annotated
from utils.auth import check_gcloud_auth

app = typer.Typer()


def parse_comma_list(value: Optional[List[str]]) -> List[str]:
    if not value:
        return []

    items = []
    for v in value:
        # Split by comma and strip whitespace from each item
        split_items = [item.strip() for item in v.split(",")]
        items.extend(split_items)

    return items


@app.command()
def looker(
    questions_file: Annotated[
        str, typer.Option(help="Path to the JSON file with evaluation questions.")
    ] = "data/questions/questions.json",
    project_id: Annotated[str, typer.Option(help="Google Cloud project ID.")] = ...,
    location: Annotated[str, typer.Option(help="The location for the agent.")] = "global",
    looker_instance: Annotated[
        Optional[str], typer.Option(help="Looker instance URL.")
    ] = None,
    model_explore: Annotated[
        Optional[List[str]],
        typer.Option(
            "--model-explore",
            help="Model and explore pair. Supports comma separation (e.g., 'model/explore,model2/explore2') or repeated flags.",
            show_default=False,
            callback=parse_comma_list,
        ),
    ] = [],
    agent_id: Annotated[str, typer.Option(help="The ID for the data agent.")] = None,
    conversation_id: Annotated[
        str, typer.Option(help="The ID for the conversation.")
    ] = None,
    agent_file: Annotated[
        Optional[str],
        typer.Option(help="Path to a JSON file containing a full DataAgent or Context definition."),
    ] = None,
    system_instructions_file: Annotated[
        Optional[str],
        typer.Option(help="Path to a file containing free-form system instructions."),
    ] = None,
    golden_queries_file: Annotated[
        Optional[str],
        typer.Option(help="Path to a JSON file containing Looker golden queries."),
    ] = None,
    looker_access_token: Annotated[
        Optional[str],
        typer.Option(help="Use a Looker access token to authenticate to Looker APIs."),
    ] = None,
    looker_dev_mode: Annotated[
        bool,
        typer.Option(
            "--looker-dev-mode",
            help="Enable Looker Development Mode via LookerSettings.enable_dev_mode.",
        ),
    ] = False,
    skip_agent_use: Annotated[
        bool,
        typer.Option(
            help="Skip agent use and run evaluation using inline context (stateless chat) API."
        ),
    ] = False,
    generate_report: Annotated[
        bool,
        typer.Option(help="Generate a Markdown report of the evaluation results."),
    ] = False,
    log_level: Annotated[str, typer.Option(help="Set the logging level.")] = "INFO",
    llm_eval: Annotated[
        bool,
        typer.Option(
            help="Enable LLM-based evaluation through Vertex AI Evaluation Service."
        ),
    ] = False,
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
    logging.getLogger("vertexai.evaluation.metrics.metric_prompt_template").setLevel(
        logging.WARNING
    )
    logging.getLogger("rouge_score").setLevel(logging.WARNING)

    from dataclasses import asdict
    from agents.looker_agent_client import LookerAgentClient
    from evals.metrics.chart_metrics import ChartMetric
    from evals.metrics.dataframe_metrics import (
        DataFrameMatch,
        score_dataframes,
    )
    from evals.metrics.llm_based_metrics import LLMBasedMetrics
    from evals.metrics.semantic_correctness_metric import semantic_correctness
    from evals.metrics.sql_metrics import (
        SQLExactMatch,
        score_sql_text,
    )
    from evals.metrics.text_similarity_metric import calculate_rouge_score
    from utils.dataset_generator import EvalQuestion
    from utils.reporter import generate_markdown_report

    def parse_expected_result_to_df(question: EvalQuestion) -> pd.DataFrame | None:
        """Parses the expected result into a DataFrame."""
        if question.expected_result:
            return pd.DataFrame(question.expected_result)
        return None

    # 1. Load optional agent definition, system instructions, and golden queries
    agent_definition = None
    if agent_file:
        try:
            with open(agent_file, "r") as f:
                agent_definition = json.load(f)
        except FileNotFoundError:
            logging.error(f"Agent file not found: {agent_file}")
            return
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in agent file {agent_file}: {e}")
            return

    if system_instructions_file:
        try:
            with open(system_instructions_file, "r") as f:
                system_instruction = f.read()
        except FileNotFoundError:
            logging.error(
                f"System instructions file not found: {system_instructions_file}"
            )
            return
    elif agent_definition:
        system_instruction = None  # Use system_instruction from agent_definition
    else:
        system_instruction = "You are a helpful data assistant."

    looker_golden_queries = None
    if golden_queries_file:
        try:
            with open(golden_queries_file, "r") as f:
                looker_golden_queries = json.load(f)
        except FileNotFoundError:
            logging.error(f"Golden queries file not found: {golden_queries_file}")
            return
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in golden queries file {golden_queries_file}: {e}")
            return

    explores = []
    if model_explore:
        for pair in model_explore:
            try:
                model, explore = pair.split("/")
                explores.append((model, explore))
            except ValueError:
                logging.error(
                    f"Invalid format for --model-explore: {pair}. "
                    "Expected 'model_name/explore_name'."
                )
                return
    logging.debug(f"Final explores: {explores}")

    if not looker_instance and not agent_definition:
        logging.error(
            "Either --looker-instance or --agent-file (containing datasource_references) must be provided."
        )
        return

    # 2. Initialize the client
    looker_client = LookerAgentClient(
        project_id=project_id,
        location=location,
        looker_access_token=looker_access_token,
    )

    if not skip_agent_use:
        if agent_id is None:
            agent_id = f"agent-{uuid.uuid4()}"
        logging.info(f"Creating or updating data agent '{agent_id}'...")

        agent = looker_client.create_agent(
            agent_id=agent_id,
            system_instruction=system_instruction,
            looker_instance_uri=looker_instance,
            explores=explores,
            looker_golden_queries=looker_golden_queries,
            agent_definition=agent_definition,
        )

        if not agent:
            logging.error("Failed to create or update agent. Exiting.")
            return

        if conversation_id is None:
            conversation_id = f"conv-{uuid.uuid4()}"
        logging.info(f"Creating conversation '{conversation_id}'...")
        looker_client.create_conversation(agent_id, conversation_id)

    # 3. Load the evaluation questions
    try:
        with open(questions_file, "r") as f:
            questions_data = json.load(f)
            questions = [EvalQuestion(**q) for q in questions_data]
    except FileNotFoundError:
        logging.error(f"Questions file not found: {questions_file}")
        return

    # 4. Initialize metrics
    sql_text_metrics = [SQLExactMatch()]
    dataframe_metrics = [DataFrameMatch()]
    chart_metric = ChartMetric()
    if llm_eval:
        # TODO: provide alt region if global default used
        llm_metric = LLMBasedMetrics(project_id=project_id, location="us-central1")

    results = []
    correct_questions = 0

    # 5. Run evaluation for each question
    for i, question in enumerate(questions):
        logging.info(
            f"--- Running evaluation for question {question.id} ({i+1}/{len(questions)}) ---"
        )
        logging.info(f"Question: {question.question}, Category: {question.category}")

        # Get the agent's response
        (
            generated_sql,
            generated_df,
            generated_looker_query,
            generated_text,
            generated_chart,
            dimensions,
            measures,
        ) = looker_client.chat(
            agent_id=agent_id,
            conversation_id=conversation_id,
            question=question.question,
            system_instruction=system_instruction,
            skip_agent_use=skip_agent_use,
            enable_dev_mode=looker_dev_mode,
            looker_instance_uri=looker_instance,
            explores=explores,
            looker_golden_queries=looker_golden_queries,
            agent_definition=agent_definition,
        )

        # Parse expected result string into a DataFrame
        expected_df = parse_expected_result_to_df(question)

        # Score the response
        sql_scores = {}

        dataframe_scores = score_dataframes(
            generated_df=generated_df,
            expected_df=expected_df,
            fields={"dimensions": dimensions, "measures": measures},
            metrics=dataframe_metrics,
        )

        text_score = {
            "RougeFMetric": calculate_rouge_score(
                generated_text, question.expected_result_text
            )
        }

        chart_score = None
        if question.expected_data_visualization:
            chart_score = chart_metric.evaluate(
                generated_chart, question.expected_data_visualization
            )

        scores = {**sql_scores, **dataframe_scores, **text_score}
        if chart_score is not None:
            scores["ChartCorrectness"] = chart_score

        if llm_eval:
            llm_scores = llm_metric.evaluate(
                question.question, generated_text, generated_df, generated_chart
            )
            scores["LLMBasedEvaluation"] = llm_scores

        if generated_looker_query and question.reference_query:
            semantic_score = semantic_correctness(
                generated_looker_query, question.reference_query
            )
            scores["Semantic Correctness"] = semantic_score

        is_correct = (
            scores.get("Semantic Correctness", 0.0) == 1.0
            or scores.get("DataFrameMatch", 0.0) == 1.0
            or scores.get("RougeFMetric") == 1.0
            or scores.get("ChartCorrectness", 0.0) == 1.0
        )
        if is_correct:
            correct_questions += 1

        serialized_looker_query = None
        if generated_looker_query:
            serialized_looker_query = geminidataanalytics.LookerQuery.to_dict(
                generated_looker_query
            )

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
                "data_result": (
                    generated_df.to_dict(orient="records")
                    if generated_df is not None
                    else []
                ),
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
        "looker_dev_mode": looker_dev_mode,
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
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    results_filename = os.path.join(results_dir, f"evaluation_results_{timestamp}.json")

    with open(results_filename, "w") as f:
        json.dump(evaluation_results, f, indent=2)
    logging.info(f"Evaluation results saved to {results_filename}")

    if generate_report:
        generate_markdown_report(
            evaluation_results, filename=f"evaluation_report_{timestamp}.md"
        )
        logging.info(f"Evaluation report generated as reports/evaluation_report_{timestamp}.md")
    else:
        print(json.dumps(evaluation_results, indent=2))


if __name__ == "__main__":
    app()
