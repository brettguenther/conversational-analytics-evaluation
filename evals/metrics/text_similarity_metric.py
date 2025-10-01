"""Text similarity metrics."""
from rouge_score import rouge_scorer

def calculate_rouge_score(generated_text: str, expected_text: str) -> float:
    """Calculates the ROUGE-L F1 score between two texts."""
    if not generated_text or not expected_text:
        return 0.0
    
    scorer = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=True)
    scores = scorer.score(expected_text, generated_text)
    # rouge 1,2 or L? > start with LCS
    return scores['rougeL'].fmeasure
