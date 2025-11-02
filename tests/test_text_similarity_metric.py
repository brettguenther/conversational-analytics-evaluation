import unittest
from evals.metrics.text_similarity_metric import calculate_rouge_score

class TestTextSimilarityMetric(unittest.TestCase):

    def test_identical_sentences(self):
        """Test that identical sentences have a high score"""
        sentence1 = "The quick brown fox jumps over the lazy dog"
        sentence2 = "The quick brown fox jumps over the lazy dog"
        score = calculate_rouge_score(sentence1, sentence2)
        self.assertGreater(score, 0.99)

    def test_completely_different_sentences(self):
        """Test that completely different sentences have a low score"""
        sentence1 = "The quick brown fox jumps over the lazy dog"
        sentence2 = "A completely unrelated sentence"
        score = calculate_rouge_score(sentence1, sentence2)
        self.assertLess(score, 0.2)

    def test_partial_overlap(self):
        """Test that partially overlapping sentences have an intermediate score"""
        sentence1 = "The quick brown fox jumps over the lazy dog"
        sentence2 = "A quick brown dog jumps high"
        score = calculate_rouge_score(sentence1, sentence2)
        self.assertTrue(0.2 < score < 0.8)

    def test_empty_strings(self):
        """Test that empty strings are handled correctly"""
        score = calculate_rouge_score("", "")
        self.assertEqual(score, 0.0)

if __name__ == '__main__':
    unittest.main()
