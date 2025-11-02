"""
This script converts a CSV file of evaluation questions into a JSON file
with a more structured format.
"""
import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Union, Dict


@dataclass
class EvalQuestion:
    """Represents a single evaluation question."""
    category: str
    question: str
    expected_result_text: str
    id: str | None = None
    expected_result: List[Dict] = field(default_factory=list)
    reference_query: dict | None = None
    expected_data_visualization: dict | None = None

def create_questions_json_from_csv(
    csv_path: Union[str, Path], json_path: Union[str, Path]
):
    """Converts a CSV file of evaluation questions to a JSON file."""
    questions: List[EvalQuestion] = []
    with open(csv_path, "r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            questions.append(
                EvalQuestion(
                    category=row["Category"],
                    question=row["Question"],
                    expected_result_text=row["Expected result"],
                )
            )

    with open(json_path, "w", encoding="utf-8") as jsonfile:
        json.dump([asdict(q) for q in questions], jsonfile, indent=2)


if __name__ == "__main__":
    # This allows the script to be run directly to perform the conversion
    csv_input_path = (
        Path(__file__).parent.parent / "context" / "eval_input.csv"
    )
    json_output_path = (
        Path(__file__).parent.parent / "data" / "questions" / "questions.json"
    )
    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    create_questions_json_from_csv(csv_input_path, json_output_path)
    print(f"Successfully converted {csv_input_path} to {json_output_path}")
