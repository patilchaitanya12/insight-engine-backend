
from difflib import get_close_matches


def correct_column_name(col_name: str, columns: list[str]):

    if not col_name:
        return None

    col_name = col_name.lower()

    normalized = {c.lower(): c for c in columns}

    # exact match
    if col_name in normalized:
        return normalized[col_name]

    # token match (handles "production" → "Production_Order")
    for key in normalized:
        if col_name in key or key in col_name:
            return normalized[key]

    # fuzzy match
    match = get_close_matches(
        col_name,
        normalized.keys(),
        n=1,
        cutoff=0.6
    )

    if match:
        return normalized[match[0]]

    return None
