# Conversational Analytics API Evaluation Framework

This framework is designed to evaluate the performance of Google's Gemini Data Analytics API, specifically for conversational agents built on Looker data models.

## Setup

1.  **Install dependencies:**
    This project uses `uv` for package management. To install the required dependencies, run:
    ```bash
    uv sync
    ```

2.  **Configure Looker API Credentials:**
    Create a `.env` file in the root of the project with your Looker API client ID and secret:
    ```bash
    touch .env
    echo "LOOKER_CLIENT_ID={myClientId}" >> .env
    echo "LOOKER_CLIENT_SECRET={mySecret}" >> .env
    ```

    Alternatively, a looker access token can be passed into the cli

3. **Provide a GCP Auth Token:**
    `gcloud auth application-default login`

## Running the Evaluation

The main entry point for running evaluations is the `cli/cli.py` script, which is exposed as the `ca-eval` command.

### Example Command

```bash
uv run ca-eval looker \
    --project-id="YOUR_PROJECT_ID" \
    --location="us-central1" \
    --looker-instance="https://your.looker.instance.com" \
    --looker-model="your_looker_model" \
    --looker-explore="your_looker_explore" \
    --questions-file=data/questions/questions.json \
    --llm-eval
```

### Command-line Options

-   `--project-id`: Your Google Cloud project ID.
-   `--location`: The GCP location for the agent (e.g., `us-central1`). Defaults to `global`.
-   `--looker-instance`: The URL of your Looker instance.
-   `--looker-model`: The LookML model to use.
-   `--looker-explore`: The Looker Explore to use.
-   `--questions-file`: Path to the JSON file containing evaluation questions.
-   `--system-instructions-file`: (Optional) Path to a file containing system instructions for the agent.
-   `--agent-id`: (Optional) The ID of the data agent to use. If not provided, a new agent with a unique ID will be created for the run.
-   `--conversation-id`: (Optional) The ID of the conversation to use. If not provided, a new conversation with a unique ID will be created for the run.
-   `--skip-agent-use`: (Optional) A boolean flag that, when present, skips the agent creation and uses the inline context API for a stateless evaluation.
-   `--generate-report`: (Optional) A boolean flag that, when present, generates a Markdown report of the evaluation results named `evaluation_report.md`.
-   `--log-level`: (Optional) Set the logging level (e.g., `DEBUG`, `INFO`, `WARNING`). Defaults to `INFO`.
-   `--llm-eval`: (Optional) A boolean flag that, when present, enables LLM-based evaluation through the Vertex AI Evaluation Service.

## Evaluation Questions

Evaluation questions are defined in JSON files in the `data/questions/` directory. Each question has the following structure:

```json
{
  "id": "S-4",
  "category": "Simple",
  "question": "What were monthly sales in 2024?",
  "expected_result_text": "",
  "expected_result": [
      {
        "sales.calendar_month": "2024-12",
        "sales.total_sales": 5705001.23
      }
  ],
  "expected_data_visualization": {
    "type": "line",
    "transformations": "",
    "x-axis": "sales.calendar_month",
    "y-axis": "sales.total_sales"
  },
  "reference_query": {
    "model": "ecomm",
    "explore": "sales",
    "fields": ["sales.calendar_month", "sales.total_sales"],
    "filters": { "sales.calendar_month": "2024" },
    "limit": "5000"
  }
}
```

-   `id`: A unique identifier for the question.
-   `category`: The category of the question (e.g., "Simple", "Medium", "Hard").
-   `question`: The natural language question to ask the agent.
-   `expected_result_text`: A string representation of the expected result.
-   `expected_result`: A structured representation of the expected result, used to create a pandas DataFrame for comparison.
-   `expected_data_visualization`: (Optional) A description of the expected chart visualization. This is used for the `ChartCorrectness` metric.
-   `reference_query`: The Looker query that represents the "golden" answer. Used for the `semantic_correctness` metric.

## Methodology

The evaluation process is centered around a set of questions defined in a JSON file. For each question, the framework performs the following steps:

1.  **Agent Interaction**: The agent is presented with a natural language question.
2.  **Query Generation**: The agent generates a Looker query based on its understanding of the question.
3.  **Data Retrieval**: The generated query is executed against the Looker instance to retrieve a dataframe.
4.  **Scoring**: The agent's response is evaluated against the reference data using a suite of metrics.

The final score for each question is a weighted average of the following metrics:

### Semantic Correctness

This metric compares the agent's generated Looker query to the `reference_query` provided in the question's data. The comparison is broken down into the following components, each with its own weight:

*   **Model and Explore (20%)**: Checks for an exact match of the Looker model and explore.
*   **Fields (40%)**: Compares the set of fields in the generated query with the reference query. Partial credit is awarded based on the Jaccard similarity between the two sets of fields.
*   **Filters (40%)**: Compares the filters applied in the queries. The scoring here is nuanced:
    *   **Filter Keys**: It checks for matches between the filter fields. Partial credit (50%) is given for using a field with the same base name but a different view (e.g., `users.age` vs. `customers.age`).
    *   **Filter Values**: For filters with matching keys, it compares the filter values.
    *   Wildcards (`%`) are ignored in value comparisons.

### DataFrame Correctness (`DataFrameMatch`)

This metric evaluates the similarity between the dataframe produced by the agent's query and the `expected_result` dataframe.

*   **Column Similarity (30%)**: It calculates the Jaccard similarity between the column names of the two dataframes.
*   **Data Similarity (70%)**: For the common columns, it performs a row-by-row comparison of the data using the `datacompy` library. This allows for tolerance in data types and floating-point precision.

The final `DataFrameMatch` score is a weighted average of the column and. data similarity scores.

### Text-based Similarity (`ROUGE`)

For questions categorized as "Simple", an additional `TextSimilarity` metric is used. This metric calculates the ROUGE score between the agent's natural language response and the `expected_result_text`. This is useful for evaluating answers that are simple facts or single values.

### LLM-based Metrics

This set of metrics leverages a large language model to evaluate the quality of the agent's response in two key areas:

*   **Intent Resolution**: This metric assesses whether the agent's response directly and accurately addresses the user's question or instruction. It uses a pointwise rating system where the LLM determines if the response fully matches, partially matches, or does not match the user's intent.
*   **Completeness**: This metric evaluates if the agent's response provides all the necessary information to be considered a complete answer, without leaving out important details. The LLM rates the response as fully complete, partially complete, or incomplete.

These metrics are particularly useful for understanding the nuances of the agent's conversational abilities beyond simple data correctness.

### Chart Correctness

This metric evaluates the correctness of charts generated by the agent. When a question expects a chart as part of the answer, this metric compares the generated chart's specification against a reference chart. The comparison is based on three key aspects:

*   **Mark Type**: Checks if the chart type (e.g., `bar`, `line`) matches the expected type.
*   **X-axis Field**: Verifies that the correct data field is used for the x-axis.
*   **Y-axis Field**: Verifies that the correct data field is used for the y-axis.

The final score is the average of these three checks, providing a quantitative measure of the chart's structural accuracy.
