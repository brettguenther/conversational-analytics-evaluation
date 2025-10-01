import json
import logging

logger = logging.getLogger(__name__)

def semantic_correctness(generated_query, reference_query):
    """
    Compares a generated Looker query with a reference query and returns a score
    based on the similarity of their components.
    """
    if reference_query is None:
        return None

    scores = {}

    # 1. Compare Model (Weight: 0.1)
    scores['model'] = 0.1 if generated_query.model == reference_query.get('model') else 0.0
    logger.debug(f"Model Score: {scores['model']}")

    # 2. Compare Explore (Weight: 0.1)
    scores['explore'] = 0.1 if generated_query.explore == reference_query.get('explore') else 0.0
    logger.debug(f"Explore Score: {scores['explore']}")

    # 3. Compare Fields (Weight: 0.4)
    generated_fields = set(generated_query.fields)
    reference_fields = set(reference_query.get('fields', []))
    logger.debug(f"Generated Fields: {generated_fields}")
    logger.debug(f"Reference Fields: {reference_fields}")
    if reference_fields:
        intersection = len(generated_fields.intersection(reference_fields))
        union = len(generated_fields.union(reference_fields))
        scores['fields'] = 0.4 * (intersection / union) if union > 0 else 0.0
    else:
        scores['fields'] = 0.4 # No reference fields to compare against
    logger.debug(f"Fields Score: {scores['fields']}")

    # 4. Compare Filters (Weight: 0.4)
    def normalize_filters(filters):
        if isinstance(filters, list):
            return {f.field: str(f.value).strip().lower().replace('%', '') for f in filters}
        elif isinstance(filters, dict):
            return {k: str(v).strip().lower().replace('%', '') for k, v in filters.items()}
        return {}

    generated_filters = normalize_filters(generated_query.filters)
    reference_filters = normalize_filters(reference_query.get('filters'))
    logger.debug(f"Generated Filters: {generated_filters}")
    logger.debug(f"Reference Filters: {reference_filters}")

    if reference_filters:
        gen_keys = set(generated_filters.keys())
        ref_keys = set(reference_filters.keys())

        key_matches = 0
        matched_ref_keys = set()
        for gen_key in gen_keys:
            if gen_key in ref_keys:
                key_matches += 1
                matched_ref_keys.add(gen_key)
            else:
                gen_key_field = gen_key.split('.')[-1]
                for ref_key in ref_keys:
                    if ref_key not in matched_ref_keys and ref_key.split('.')[-1] == gen_key_field:
                        key_matches += 0.5
                        matched_ref_keys.add(ref_key)
                        break
        
        key_score = key_matches / len(ref_keys) if ref_keys else 1.0

        value_matches = 0
        exact_matching_keys = gen_keys.intersection(ref_keys)
        if exact_matching_keys:
            for key in exact_matching_keys:
                if generated_filters[key] == reference_filters[key]:
                    value_matches += 1
            value_score = value_matches / len(exact_matching_keys) if exact_matching_keys else 1.0
        else:
            value_score = 0.0

        filter_score = 0.5 * key_score + 0.5 * value_score
        scores['filters'] = 0.4 * filter_score
    else:
        scores['filters'] = 0.4
    logger.debug(f"Filter Score: {scores['filters']}")

    final_score = sum(scores.values())
    logger.debug(f"Final Score: {final_score}")
    return final_score
