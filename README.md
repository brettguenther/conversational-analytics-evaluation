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

3. **Provide a GCP Auth Token:**
    `gcloud auth application-default login`

## Running the Evaluation

The main entry point for running evaluations is the `main.py` script.

### Example Command

```bash
uv run main.py run-evaluation \
    --project-id="YOUR_PROJECT_ID" \
    --looker-instance="https://your.looker.instance.com" \
    --looker-model="your_looker_model" \
    --looker-explore="your_looker_explore" \
    --config-file=config.json \
    --questions-file=data/questions/questions.json
```

### Command-line Options

-   `--project-id`: Your Google Cloud project ID.
-   `--looker-instance`: The URL of your Looker instance.
-   `--looker-model`: The LookML model to use.
-   `--looker-explore`: The Looker Explore to use.
-   `--config-file`: Path to the `config.json` file.
-   `--questions-file`: Path to the JSON file containing evaluation questions.
-   `--system-instructions-file`: (Optional) Path to a file containing system instructions for the agent.
-   `--agent-id`: (Optional) The ID of the data agent to use. If not provided, a new agent with a unique ID will be created for the run.
-   `--conversation-id`: (Optional) The ID of the conversation to use. If not provided, a new conversation with a unique ID will be created for the run.
-   `--skip-agent-use`: (Optional) A boolean flag that, when present, skips the agent creation and uses the inline context API for a stateless evaluation.

## Evaluation Questions

Evaluation questions are defined in JSON files in the `data/questions/` directory. Each question has the following structure:

```json
{
  "category": "Simple",
  "question": "What were the total sales in the Seattle store in October 2021?",
  "expected_result_text": "The total sales in the Seattle store in October 2021 were $993774.45.",
  "expected_result": [
    {
      "sales.total_sales": 993774.45
    }
  ],
  "reference_query": {
    "model": "ecomm",
    "explore": "sales",
    "fields": ["sales.total_sales"],
    "filters": {
      "sites.site_description": "Downtown Seattle Flagship",
      "sales.calendar_month": "2021-10"
    },
    "limit": "500"
  }
}
```

-   `category`: The category of the question (e.g., "Simple", "Medium", "Hard").
-   `question`: The natural language question to ask the agent.
-   `expected_result_text`: A string representation of the expected result.
-   `expected_result`: A structured representation of the expected result, used to create a pandas DataFrame for comparison.
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

The final `DataFrameMatch` score is a weighted average of the column and data similarity scores.

### Text-based Similarity (`ROUGE`)

For questions categorized as "Simple", an additional `TextSimilarity` metric is used. This metric calculates the ROUGE score between the agent's natural language response and the `expected_result_text`. This is useful for evaluating answers that are simple facts or single values.