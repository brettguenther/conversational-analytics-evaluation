
import unittest
from unittest.mock import Mock
from evals.metrics.semantic_correctness_metric import semantic_correctness

class TestSemanticCorrectness(unittest.TestCase):

    def test_identical_queries(self):
        """Test that identical queries score 1.0"""
        query1 = Mock()
        query1.fields = ['a', 'b']
        query1.filters = [Mock(field='c', value='d')]

        query2 = {
            'fields': ['a', 'b'],
            'filters': {'c': 'd'}
        }

        score = semantic_correctness(query1, query2)
        self.assertEqual(score, 1.0)

    def test_different_limit(self):
        """Test that queries with different limits score 1.0"""
        query1 = Mock()
        query1.fields = ['a', 'b']
        query1.filters = [Mock(field='c', value='d')]
        query1.limit = 100

        query2 = {
            'fields': ['a', 'b'],
            'filters': {'c': 'd'},
            'limit': 500
        }

        score = semantic_correctness(query1, query2)
        self.assertEqual(score, 1.0)

if __name__ == '__main__':
    unittest.main()
