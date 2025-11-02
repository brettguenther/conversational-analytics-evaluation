import json
import logging
from proto.marshal.collections.repeated import RepeatedComposite

logger = logging.getLogger(__name__)

def semantic_correctness(generated_query, reference_query):
    """
    Compares a generated Looker query with a reference query and returns a score
    based on the similarity of their components.
    """
    if reference_query is None:
        return None
    
    equivalent_timeframes = {'time','second','minute','hour','date','week','month','year'}
    equivalent_fiscal_timeframes = {'fiscal_quarter','fiscal_year'}

    scores = {}

    def get_dimension_group_field_root(field_name):
        "remove trailing timeframe to do a comparison on the dimension group reference"
        parts = field_name.split('.')
        if len(parts) != 2:
            return field_name
        
        view, field = parts
        if '_' in field:
            field_parts = field.rsplit('_',1)
            if len(field_parts) == 2:
                base, suffix = field_parts
                if suffix in equivalent_timeframes or suffix in equivalent_fiscal_timeframes:
                    return f"{view}.{base}"
        return field_name


    ## TO DO: when CA support for multi model
    # 1. Compare Model
    # scores['model'] = 0.1 if generated_query.model == reference_query.get('model') else 0.0
    # logger.debug(f"Model Score: {scores['model']}")

    ## TO DO: when CA support for multi explore
    # 2. Compare Explore
    # scores['explore'] = 0.1 if generated_query.explore == reference_query.get('explore') else 0.0
    # logger.debug(f"Explore Score: {scores['explore']}")

    # 3. Compare Fields (Weight: 0.6)
    generated_fields = set(generated_query.fields)
    reference_fields = set(reference_query.get('fields', []))
    logger.debug(f"Generated Query Fields: {generated_fields}")
    logger.debug(f"Reference Query Fields: {reference_fields}")
    if not reference_fields:
        return None

    intersection = len(generated_fields.intersection(reference_fields))
    union = len(generated_fields.union(reference_fields))
    scores['fields'] = 0.6 * (intersection / union) if union > 0 else 0.0
    logger.debug(f"Semantic Fields Score: {scores['fields']}")

    # 4. Compare Filters (Weight: 0.4)
    def normalize_filters(filters):
        if isinstance(filters, (list, RepeatedComposite)):
            return {f.field: str(f.value).strip().lower().replace('%', '') for f in filters}
        elif isinstance(filters, dict):
            return {k: str(v).strip().lower().replace('%', '') for k, v in filters.items()}
        return {}

    generated_filters = normalize_filters(generated_query.filters)
    reference_filters = normalize_filters(reference_query.get('filters'))
    logger.debug(f"Generated Query Filters: {generated_filters}")
    logger.debug(f"Reference Query Filters: {reference_filters}")

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
                gen_key_root = get_dimension_group_field_root(gen_key)
                found_match = False
                for ref_key in ref_keys:
                    if ref_key not in matched_ref_keys:
                        ref_key_root = get_dimension_group_field_root(ref_key)
                        if gen_key_root == ref_key_root:
                            key_matches += 1  # Matching root of infered dimension group correct
                            matched_ref_keys.add(ref_key)
                            found_match = True
                            break
                # TODO: decide if partial credit to be given for matching field in different view
                # if not found_match:
                #     gen_key_field = gen_key.split('.')[-1]
                #     for ref_key in ref_keys:
                #         if ref_key not in matched_ref_keys and ref_key.split('.')[-1] == gen_key_field:
                #             key_matches += 0.5
                #             matched_ref_keys.add(ref_key)
                #             break
        
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
    logger.debug(f"Semantic Filter Score: {scores['filters']}")

    final_score = sum(scores.values())
    logger.debug(f"Final Semantic Correctness Score: {final_score}")
    return final_score
