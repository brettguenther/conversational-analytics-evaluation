# Example Eval Set

1. Load the model files into a LookML project adjusting the manifest file as needed and push to production.
2. Run the following command:

uv run ca-eval --project-id="{your-gcp-project-id}" --looker-instance={your-looker-instance} --model-explore=nyc_citibike_trips/trips --questions-file=./sample-data/nyc-citibike/questions/citibike-questions.json --generate-report --llm-eval --system-instructions-file=./sample-data/nyc-citibike/agent/bike_data_analyst_system_instructions.json
