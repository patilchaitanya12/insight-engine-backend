from difflib import get_close_matches

def correct_column_name(col_name, columns):

    if not col_name:
        return None

    # EXACT MATCH FIRST
    if col_name in columns:
        return col_name

    # case-insensitive match
    for col in columns:
        if col.lower() == col_name.lower():
            return col

    # fuzzy match
    match = get_close_matches(col_name, columns, n=1, cutoff=0.8)

    if match:
        return match[0]

    return None