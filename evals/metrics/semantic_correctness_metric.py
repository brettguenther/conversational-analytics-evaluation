import json

def semantic_correctness(generated_query, reference_query):
    """
    Compares a generated Looker query with a reference query and returns a score.
    """
    if reference_query is None:
        return None  # Or some other indicator that a reference is not available

    score = 0.0
    max_score = 2.0  # fields, filters

    # Compare fields
    generated_fields = set(generated_query.fields)
    reference_fields = set(reference_query.get('fields', []))
    if reference_fields:
        score += len(generated_fields.intersection(reference_fields)) / len(reference_fields)

    # Compare filters
    generated_filters_dict = {f.field: f.value for f in generated_query.filters}
    reference_filters = reference_query.get('filters') or {}

    if reference_filters:
        # Score for matching filter keys
        generated_filter_keys = set(generated_filters_dict.keys())
        reference_filter_keys = set(reference_filters.keys())
        key_match_score = len(generated_filter_keys.intersection(reference_filter_keys)) / len(reference_filter_keys)
        score += key_match_score * 0.5  # 50% of the filter score is for key matching

        # Score for matching filter values for the keys that matched
        value_match_score = 0
        matching_keys = generated_filter_keys.intersection(reference_filter_keys)
        if matching_keys:
            for key in matching_keys:
                if generated_filters_dict[key] == reference_filters[key]:
                    value_match_score += 1
            value_match_score /= len(matching_keys)
            score += value_match_score * 0.5 # 50% of the filter score is for value matching

    return score / max_score if max_score > 0 else 0
